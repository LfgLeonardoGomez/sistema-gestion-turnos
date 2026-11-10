"""Pruebas contra PostgreSQL real; activar con RUN_DB_INTEGRATION_TESTS=1.

Cada caso crea datos aislados en una transacción que siempre termina en ROLLBACK.
Ejecutar con el usuario migrador; las consultas bajo prueba usan SET LOCAL ROLE
turnos_app para ejercitar los permisos y RLS de producción.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
from psycopg.errors import InsufficientPrivilege


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION_TESTS") == "1", "requiere PostgreSQL de integración")
class ClientRlsIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = psycopg.connect(
            os.environ["MIGRATION_DATABASE_URL"],
            password=os.environ["MIGRATION_DB_PASSWORD"],
            autocommit=True,
        )
        self.conn.execute("BEGIN")
        self.business_a, self.business_b = uuid4(), uuid4()
        self.admin_a, self.reception_a = uuid4(), uuid4()
        self.professional_user_a, self.professional_user_b = uuid4(), uuid4()
        self.admin_b = uuid4()
        self.professional_a, self.professional_b = uuid4(), uuid4()
        self.client_a, self.client_b, self.client_other_business = uuid4(), uuid4(), uuid4()

        for business in (self.business_a, self.business_b):
            self.conn.execute("INSERT INTO negocio (id, nombre) VALUES (%s, %s)",
                              (business, f"RLS test {business}"))
        memberships = (
            (self.business_a, self.admin_a, "admin"),
            (self.business_a, self.reception_a, "recepcionista"),
            (self.business_a, self.professional_user_a, "profesional"),
            (self.business_a, self.professional_user_b, "profesional"),
            (self.business_b, self.admin_b, "admin"),
        )
        for business, user, role in memberships:
            self.conn.execute(
                "INSERT INTO usuario (id, email, password_hash, nombre) VALUES (%s, %s, %s, %s)",
                (user, f"{user}@example.invalid", "integration-only", "Test"),
            )
            self.conn.execute(
                "INSERT INTO membresia (negocio_id, usuario_id, rol) VALUES (%s, %s, %s)",
                (business, user, role),
            )
        for professional, user in (
            (self.professional_a, self.professional_user_a),
            (self.professional_b, self.professional_user_b),
        ):
            self.conn.execute(
                "INSERT INTO profesional (id, negocio_id, usuario_id, nombre) VALUES (%s, %s, %s, %s)",
                (professional, self.business_a, user, "Profesional"),
            )
        for client, business, owner in (
            (self.client_a, self.business_a, self.admin_a),
            (self.client_b, self.business_a, self.admin_a),
            (self.client_other_business, self.business_b, self.admin_b),
        ):
            self.conn.execute(
                "INSERT INTO cliente (id, negocio_id, nombre, email, creado_por_usuario_id) "
                "VALUES (%s, %s, %s, %s, %s)",
                (client, business, "Cliente", f"{client}@example.invalid", owner),
            )
        start = datetime(2030, 1, 2, 12, tzinfo=timezone.utc)
        for client, professional, offset in (
            (self.client_a, self.professional_a, 0),
            (self.client_b, self.professional_b, 1),
        ):
            self.conn.execute(
                "INSERT INTO turno (negocio_id, profesional_id, cliente_id, inicio, fin, "
                "estado, creado_por_usuario_id) VALUES (%s, %s, %s, %s, %s, 'completado', %s)",
                (self.business_a, professional, client, start + timedelta(hours=offset),
                 start + timedelta(hours=offset + 1), self.admin_a),
            )

    def tearDown(self) -> None:
        try:
            self.conn.execute("ROLLBACK")
        finally:
            self.conn.close()

    def context(self, business, user, role) -> None:
        self.conn.execute("RESET ROLE")
        for key, value in (
            ("app.negocio_id", business),
            ("app.usuario_id", user),
            ("app.rol", role),
        ):
            self.conn.execute("SELECT set_config(%s, %s, true)", (key, str(value)))
        self.conn.execute("SET LOCAL ROLE turnos_app")

    def visible_clients(self) -> set:
        return {row[0] for row in self.conn.execute("SELECT id FROM cliente")}

    def test_admin_and_reception_see_only_their_business(self) -> None:
        for user, role in ((self.admin_a, "admin"), (self.reception_a, "recepcionista")):
            with self.subTest(role=role):
                self.context(self.business_a, user, role)
                self.assertEqual(self.visible_clients(), {self.client_a, self.client_b})
                self.assertEqual(self.conn.execute("SELECT count(*) FROM turno").fetchone()[0], 2)
        self.context(self.business_b, self.admin_b, "admin")
        self.assertEqual(self.visible_clients(), {self.client_other_business})
        self.assertEqual(self.conn.execute("SELECT count(*) FROM turno").fetchone()[0], 0)

    def test_professionals_only_see_own_historical_clients(self) -> None:
        self.context(self.business_a, self.professional_user_a, "profesional")
        self.assertEqual(self.visible_clients(), {self.client_a})
        self.assertEqual(self.conn.execute("SELECT count(*) FROM turno").fetchone()[0], 1)
        self.context(self.business_a, self.professional_user_b, "profesional")
        self.assertEqual(self.visible_clients(), {self.client_b})
        self.assertEqual(self.conn.execute("SELECT count(*) FROM turno").fetchone()[0], 1)

    def test_match_cannot_switch_to_another_business(self) -> None:
        self.context(self.business_a, self.admin_a, "admin")
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM detectar_coincidencias_cliente(%s, %s, NULL, NULL)",
            (self.business_b, f"{self.client_other_business}@example.invalid"),
        ).fetchone()[0], 0)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM detectar_coincidencias_cliente(%s, %s, NULL, NULL)",
            (self.business_a, f"{self.client_other_business}@example.invalid"),
        ).fetchone()[0], 0)

    def test_match_does_not_reveal_hidden_client_until_admin_shares(self) -> None:
        email = f"{self.client_b}@example.invalid"
        self.context(self.business_a, self.professional_user_a, "profesional")
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM detectar_coincidencias_cliente(%s, %s, NULL, NULL)",
            (self.business_a, email),
        ).fetchone()[0], 0)
        self.context(self.business_a, self.admin_a, "admin")
        self.conn.execute(
            "INSERT INTO cliente_profesional "
            "(negocio_id, cliente_id, profesional_id, creado_por_usuario_id) "
            "VALUES (%s, %s, %s, %s)",
            (self.business_a, self.client_b, self.professional_a, self.admin_a),
        )
        self.context(self.business_a, self.professional_user_a, "profesional")
        self.assertEqual(self.visible_clients(), {self.client_a, self.client_b})
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM detectar_coincidencias_cliente(%s, %s, NULL, NULL)",
            (self.business_a, email),
        ).fetchone()[0], 1)

    def test_professional_cannot_self_link_hidden_client(self) -> None:
        self.context(self.business_a, self.professional_user_a, "profesional")
        self.conn.execute("SAVEPOINT denied_link")
        try:
            with self.assertRaises(InsufficientPrivilege):
                self.conn.execute(
                    "INSERT INTO cliente_profesional "
                    "(negocio_id, cliente_id, profesional_id, creado_por_usuario_id) "
                    "VALUES (%s, %s, %s, %s)",
                    (self.business_a, self.client_b, self.professional_a, self.professional_user_a),
                )
        finally:
            self.conn.execute("ROLLBACK TO SAVEPOINT denied_link")


if __name__ == "__main__":
    unittest.main()
