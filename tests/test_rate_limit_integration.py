"""Concurrencia real del límite de intentos; requiere RUN_DB_INTEGRATION_TESTS=1."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from uuid import uuid4

import psycopg


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION_TESTS") == "1", "requiere PostgreSQL de integración")
class RateLimitIntegrationTests(unittest.TestCase):
    def test_concurrent_attempts_never_exceed_quota(self) -> None:
        bucket = sha256(f"integration:{uuid4()}".encode()).digest()

        def attempt() -> bool:
            with psycopg.connect(
                os.environ["MIGRATION_DATABASE_URL"],
                password=os.environ["MIGRATION_DB_PASSWORD"],
            ) as conn:
                conn.execute("SET ROLE turnos_app")
                return conn.execute(
                    "SELECT consumir_limite_seguridad(%s, %s, %s)",
                    (bucket, 4, 900),
                ).fetchone()[0]

        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(lambda _: attempt(), range(12)))
            self.assertEqual(sum(results), 4)
        finally:
            with psycopg.connect(
                os.environ["MIGRATION_DATABASE_URL"],
                password=os.environ["MIGRATION_DB_PASSWORD"],
            ) as conn:
                conn.execute("DELETE FROM security_rate_limit WHERE bucket = %s", (bucket,))


if __name__ == "__main__":
    unittest.main()
