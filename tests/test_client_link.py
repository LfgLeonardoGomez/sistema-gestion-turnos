import unittest
from unittest.mock import Mock
from uuid import uuid4

from fastapi import HTTPException

from turnos.api import BusinessContext
from turnos.people_api import compartir_cliente_con_profesional


class ClientLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.business_id = uuid4()
        self.user_id = uuid4()
        self.client_id = uuid4()
        self.professional_id = uuid4()
        self.conn = Mock()

    def context(self, role: str) -> BusinessContext:
        return BusinessContext(negocio_id=self.business_id, usuario_id=self.user_id, rol=role)

    def test_professional_cannot_share_hidden_client(self) -> None:
        with self.assertRaises(HTTPException) as error:
            compartir_cliente_con_profesional(
                self.client_id, self.professional_id, self.conn, self.context("profesional")
            )
        self.assertEqual(error.exception.status_code, 403)
        self.conn.execute.assert_not_called()

    def test_rejects_professional_without_active_account(self) -> None:
        client = {
            "id": self.client_id, "nombre": "Cliente", "telefono": None,
            "email": None, "documento": None, "notas": None,
        }
        self.conn.execute.return_value.fetchone.side_effect = [client, None]
        with self.assertRaises(HTTPException) as error:
            compartir_cliente_con_profesional(
                self.client_id, self.professional_id, self.conn, self.context("admin")
            )
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.conn.execute.call_count, 2)

    def test_admin_can_share_visible_client(self) -> None:
        client = {
            "id": self.client_id, "nombre": "Cliente", "telefono": None,
            "email": None, "documento": None, "notas": None,
        }
        self.conn.execute.return_value.fetchone.side_effect = [client, {"exists": 1}]
        result = compartir_cliente_con_profesional(
            self.client_id, self.professional_id, self.conn, self.context("admin")
        )
        self.assertEqual(result.id, self.client_id)
        self.assertEqual(self.conn.execute.call_count, 3)
        sql, params = self.conn.execute.call_args.args
        self.assertIn("INSERT INTO cliente_profesional", sql)
        self.assertEqual(params, (
            self.business_id, self.client_id, self.professional_id, self.user_id,
        ))


if __name__ == "__main__":
    unittest.main()
