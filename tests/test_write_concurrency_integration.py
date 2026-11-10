"""Carreras reales en una base temporal propia; requiere RUN_DB_INTEGRATION_TESTS=1."""

import asyncio
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import Barrier
from uuid import uuid4
from unittest.mock import patch

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from turnos import api as api_module, migrate
from turnos.appointments_api import TurnoInput, crear_turno
from turnos.api import BusinessContext
from turnos.db import get_connection


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION_TESTS") == "1", "requiere PostgreSQL de integración")
class WriteConcurrencyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_name = f"turnos_verify_{uuid4().hex[:12]}"
        original_url = os.environ["MIGRATION_DATABASE_URL"]
        cls.database_url = original_url.rsplit("/", 1)[0] + "/" + cls.database_name
        server_url = original_url.rsplit("/", 1)[0] + "/postgres"
        cls.server_url = server_url
        with psycopg.connect(server_url, password=os.environ["MIGRATION_DB_PASSWORD"], autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{cls.database_name}"')
        try:
            os.environ["MIGRATION_DATABASE_URL"] = cls.database_url
            migrate.main()
        except BaseException:
            cls.drop_database()
            raise
        finally:
            os.environ["MIGRATION_DATABASE_URL"] = original_url

    @classmethod
    def drop_database(cls) -> None:
        # El nombre se genera internamente y se valida antes de eliminarlo.
        if not cls.database_name.startswith("turnos_verify_") or len(cls.database_name) != 26:
            raise ValueError("Nombre de base temporal inesperado")
        with psycopg.connect(cls.server_url, password=os.environ["MIGRATION_DB_PASSWORD"], autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{cls.database_name}" WITH (FORCE)')

    @classmethod
    def tearDownClass(cls) -> None:
        cls.drop_database()

    def connect(self):
        return psycopg.connect(self.database_url, password=os.environ["MIGRATION_DB_PASSWORD"])

    def http_request(self, method: str, path: str, *, token: str | None = None,
                     business=None) -> int:
        headers = [(b"host", b"localhost:8000")]
        if token:
            headers.append((b"cookie", f"turnos_session={token}".encode()))
        if business:
            headers.append((b"x-business-id", str(business).encode()))
        if method == "POST":
            headers.append((b"origin", b"http://localhost:8000"))

        def test_connection():
            with psycopg.connect(
                self.database_url.replace("postgres@", "turnos_app@"),
                password=os.environ["APP_DB_PASSWORD"], row_factory=dict_row,
            ) as conn:
                yield conn

        async def run_request() -> int:
            messages = []
            sent_body = False

            async def receive():
                nonlocal sent_body
                if not sent_body:
                    sent_body = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                await asyncio.sleep(3600)

            async def send(message):
                messages.append(message)

            scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
                "query_string": b"", "root_path": "", "headers": headers,
                "client": ("127.0.0.1", 12345), "server": ("localhost", 8000),
            }
            await api_module.app(scope, receive, send)
            return next(message["status"] for message in messages if message["type"] == "http.response.start")

        original = api_module.app.dependency_overrides.get(get_connection)
        api_module.app.dependency_overrides[get_connection] = test_connection
        try:
            with patch.object(api_module, "get_settings", return_value=type("Settings", (), {
                "app_origin": "http://localhost:8000", "cookie_secure": False,
            })()):
                return asyncio.run(run_request())
        finally:
            if original is None:
                api_module.app.dependency_overrides.pop(get_connection, None)
            else:
                api_module.app.dependency_overrides[get_connection] = original

    def test_http_authorization_across_roles_and_businesses(self) -> None:
        business_a, business_b = uuid4(), uuid4()
        admin, reception, professional_user, professional, client_visible, client_hidden = (
            uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        )
        admin_token, reception_token, professional_token = uuid4().hex, uuid4().hex, uuid4().hex
        with self.connect() as conn:
            for business in (business_a, business_b):
                conn.execute("INSERT INTO negocio (id, nombre) VALUES (%s, 'HTTP auth test')", (business,))
            for user in (admin, reception, professional_user):
                conn.execute(
                    "INSERT INTO usuario (id, email, nombre, password_hash) VALUES (%s, %s, 'Test', 'hash')",
                    (user, f"{user}@example.com"),
                )
            conn.execute("INSERT INTO membresia (negocio_id, usuario_id, rol) VALUES (%s, %s, 'admin')", (business_a, admin))
            conn.execute("INSERT INTO membresia (negocio_id, usuario_id, rol) VALUES (%s, %s, 'recepcionista')", (business_a, reception))
            conn.execute("INSERT INTO membresia (negocio_id, usuario_id, rol) VALUES (%s, %s, 'profesional')", (business_a, professional_user))
            conn.execute(
                "INSERT INTO profesional (id, negocio_id, usuario_id, nombre) VALUES (%s, %s, %s, 'Profesional')",
                (professional, business_a, professional_user),
            )
            for client, creator in ((client_visible, professional_user), (client_hidden, admin)):
                conn.execute(
                    "INSERT INTO cliente (id, negocio_id, nombre, creado_por_usuario_id) VALUES (%s, %s, 'Cliente', %s)",
                    (client, business_a, creator),
                )
            for user, token in ((admin, admin_token), (reception, reception_token),
                                (professional_user, professional_token)):
                conn.execute(
                    "INSERT INTO sesion (token_hash, usuario_id, expira_en) VALUES (%s, %s, now() + interval '1 hour')",
                    (sha256(token.encode()).digest(), user),
                )

        hidden_path = f"/clientes/{client_hidden}"
        self.assertEqual(self.http_request("GET", hidden_path), 401)
        self.assertEqual(self.http_request("GET", hidden_path, token=admin_token, business=business_b), 403)
        self.assertEqual(self.http_request("GET", hidden_path, token=reception_token, business=business_a), 200)
        self.assertEqual(self.http_request("GET", hidden_path, token=professional_token, business=business_a), 404)
        self.assertEqual(self.http_request("GET", f"/clientes/{client_visible}", token=professional_token, business=business_a), 200)
        share_path = f"/clientes/{client_hidden}/profesionales/{professional}"
        self.assertEqual(self.http_request("POST", share_path, token=professional_token, business=business_a), 403)
        self.assertEqual(self.http_request("POST", share_path, token=admin_token, business=business_b), 403)
        self.assertEqual(self.http_request("POST", share_path, token=reception_token, business=business_a), 200)
        self.assertEqual(self.http_request("POST", share_path, token=admin_token, business=business_a), 200)
        self.assertEqual(self.http_request("GET", hidden_path, token=professional_token, business=business_a), 200)

    def test_invitation_can_only_be_accepted_once_concurrently(self) -> None:
        business, admin, recipient = uuid4(), uuid4(), uuid4()
        token_hash = sha256(uuid4().bytes).digest()
        recipient_email = f"{recipient}@example.invalid"
        with self.connect() as conn:
            conn.execute("INSERT INTO negocio (id, nombre) VALUES (%s, 'Carrera invitación')", (business,))
            for user, email in ((admin, f"{admin}@example.invalid"), (recipient, recipient_email)):
                conn.execute("INSERT INTO usuario (id, email, nombre, password_hash) VALUES (%s, %s, 'Test', 'hash')", (user, email))
            conn.execute("INSERT INTO membresia (negocio_id, usuario_id, rol) VALUES (%s, %s, 'admin')", (business, admin))
            conn.execute(
                "INSERT INTO invitacion_personal "
                "(negocio_id, email, rol, token_hash, creado_por_usuario_id, expira_en) "
                "VALUES (%s, %s, 'profesional', %s, %s, now() + interval '1 hour')",
                (business, recipient_email, token_hash, admin),
            )

        barrier = Barrier(2)

        def accept() -> str:
            with self.connect() as conn:
                conn.execute("SET ROLE turnos_app")
                conn.execute("SELECT set_config('app.usuario_id', %s, true)", (str(recipient),))
                barrier.wait(timeout=10)
                try:
                    conn.execute("SELECT aceptar_invitacion_personal_existente(%s)", (token_hash,))
                    return "accepted"
                except psycopg.Error as exc:
                    conn.rollback()
                    return exc.sqlstate or "error"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: accept(), range(2)))
        self.assertEqual(outcomes.count("accepted"), 1)
        self.assertEqual(outcomes.count("P0001"), 1)
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM membresia WHERE negocio_id = %s AND usuario_id = %s",
                (business, recipient),
            ).fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM profesional WHERE negocio_id = %s AND usuario_id = %s",
                (business, recipient),
            ).fetchone()[0], 1)

    def test_overlapping_appointments_cannot_both_commit(self) -> None:
        business, admin, professional, client = uuid4(), uuid4(), uuid4(), uuid4()
        with self.connect() as conn:
            conn.execute("INSERT INTO negocio (id, nombre) VALUES (%s, 'Carrera turnos')", (business,))
            conn.execute(
                "INSERT INTO usuario (id, email, nombre, password_hash) VALUES (%s, %s, 'Test', 'hash')",
                (admin, f"{admin}@example.invalid"),
            )
            conn.execute("INSERT INTO membresia (negocio_id, usuario_id, rol) VALUES (%s, %s, 'admin')", (business, admin))
            conn.execute("INSERT INTO profesional (id, negocio_id, nombre) VALUES (%s, %s, 'Profesional')", (professional, business))
            conn.execute("INSERT INTO cliente (id, negocio_id, nombre) VALUES (%s, %s, 'Cliente')", (client, business))
            conn.execute(
                "INSERT INTO horario_profesional (negocio_id, profesional_id, dia_semana, hora_inicio, hora_fin) "
                "VALUES (%s, %s, 2, '08:00', '18:00')",
                (business, professional),
            )

        start = datetime(2030, 1, 2, 12, tzinfo=timezone.utc)
        barrier = Barrier(2)

        def book() -> str:
            with psycopg.connect(
                self.database_url.replace("postgres@", "turnos_app@"),
                password=os.environ["APP_DB_PASSWORD"], row_factory=dict_row,
            ) as conn:
                for key, value in (("app.negocio_id", business), ("app.usuario_id", admin), ("app.rol", "admin")):
                    conn.execute("SELECT set_config(%s, %s, true)", (key, str(value)))
                barrier.wait(timeout=10)
                try:
                    crear_turno(
                        TurnoInput(profesional_id=professional, cliente_id=client,
                                   inicio=start, duracion_minutos=30),
                        BusinessContext(negocio_id=business, usuario_id=admin, rol="admin"),
                        conn,
                    )
                    return "booked"
                except HTTPException as exc:
                    return str(exc.status_code)

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: book(), range(2)))
        self.assertEqual(outcomes.count("booked"), 1)
        self.assertEqual(outcomes.count("409"), 1, outcomes)
        with self.connect() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM turno WHERE negocio_id = %s", (business,)
            ).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
