"""Create the first business and administrator using the migration role."""

import os

import psycopg
from pwdlib import PasswordHash


def main() -> None:
    business_name = os.environ["BOOTSTRAP_BUSINESS_NAME"].strip()
    admin_name = os.environ["BOOTSTRAP_ADMIN_NAME"].strip()
    admin_email = os.environ["BOOTSTRAP_ADMIN_EMAIL"].strip().lower()
    admin_password = os.environ["BOOTSTRAP_ADMIN_PASSWORD"]
    if not business_name or not admin_name or not admin_email:
        raise ValueError("Los datos de bootstrap no pueden estar vacíos")
    if len(admin_password) < 12:
        raise ValueError("BOOTSTRAP_ADMIN_PASSWORD debe tener al menos 12 caracteres")

    password_hash = PasswordHash.recommended().hash(admin_password)
    with psycopg.connect(
        os.environ["MIGRATION_DATABASE_URL"],
        password=os.environ["MIGRATION_DB_PASSWORD"],
    ) as conn:
        if conn.execute("SELECT 1 FROM usuario WHERE email = %s", (admin_email,)).fetchone():
            raise ValueError("Ya existe un usuario con ese email")
        business_id = conn.execute(
            "INSERT INTO negocio (nombre) VALUES (%s) RETURNING id", (business_name,)
        ).fetchone()[0]
        user_id = conn.execute(
            "INSERT INTO usuario (email, password_hash, nombre) "
            "VALUES (%s, %s, %s) RETURNING id",
            (admin_email, password_hash, admin_name),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO membresia (negocio_id, usuario_id, rol) "
            "VALUES (%s, %s, 'admin')",
            (business_id, user_id),
        )
    print(f"Negocio creado: {business_id}")
    print(f"Administrador creado: {admin_email}")


if __name__ == "__main__":
    main()
