"""Apply SQL migrations with an administrative PostgreSQL connection."""

import os
from pathlib import Path

import psycopg
from psycopg import sql


MIGRATIONS = Path(__file__).resolve().parent.parent / "db"
APP_ROLE = "turnos_app"
INVITE_ROLE = "turnos_invite_executor"
REMINDER_ROLE = "turnos_reminder"


def main() -> None:
    database_url = os.environ["MIGRATION_DATABASE_URL"]
    app_password = os.environ["APP_DB_PASSWORD"]
    reminder_password = os.environ["REMINDER_DB_PASSWORD"]
    if len(app_password) < 16:
        raise ValueError("APP_DB_PASSWORD debe tener al menos 16 caracteres")
    if len(reminder_password) < 16:
        raise ValueError("REMINDER_DB_PASSWORD debe tener al menos 16 caracteres")

    applied: list[str] = []
    with psycopg.connect(
        database_url, password=os.environ["MIGRATION_DB_PASSWORD"]
    ) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migration "
            "(filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        # Algunas migraciones conceden EXECUTE/SELECT al rol de runtime.
        # En una base vacía debe existir antes de ejecutar esos archivos.
        if not conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)
        ).fetchone():
            conn.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN NOBYPASSRLS").format(sql.Identifier(APP_ROLE))
            )
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            exists = conn.execute(
                "SELECT 1 FROM schema_migration WHERE filename = %s", (path.name,)
            ).fetchone()
            if exists:
                continue
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migration (filename) VALUES (%s)", (path.name,)
            )
            applied.append(path.name)

        role_exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)
        ).fetchone()
        password_sql = sql.Literal(app_password)
        role_sql = sql.Identifier(APP_ROLE)
        if role_exists:
            conn.execute(
                sql.SQL("ALTER ROLE {} LOGIN NOBYPASSRLS PASSWORD {}").format(
                    role_sql, password_sql
                )
            )
        else:
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOBYPASSRLS PASSWORD {}").format(
                    role_sql, password_sql
                )
            )
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role_sql))
        # Mínimo privilegio: solo tablas y operaciones usadas por las rutas actuales.
        conn.execute(
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(role_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT ON usuario, negocio, membresia TO {}").format(role_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON sesion TO {}").format(role_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE ON cliente, profesional, turno TO {}")
            .format(role_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON horario_profesional TO {}")
            .format(role_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT ON cliente_profesional TO {}")
            .format(role_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT ON evento_turno TO {}").format(role_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE ON invitacion_personal TO {}")
            .format(role_sql)
        )
        reminder_sql = sql.Identifier(REMINDER_ROLE)
        reminder_password_sql = sql.Literal(reminder_password)
        if conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (REMINDER_ROLE,)
        ).fetchone():
            conn.execute(
                sql.SQL("ALTER ROLE {} LOGIN BYPASSRLS PASSWORD {}")
                .format(reminder_sql, reminder_password_sql)
            )
        else:
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN BYPASSRLS PASSWORD {}")
                .format(reminder_sql, reminder_password_sql)
            )
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(reminder_sql))
        conn.execute(
            sql.SQL("GRANT SELECT ON turno, cliente, negocio, profesional TO {}")
            .format(reminder_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE ON recordatorio_email_entrega TO {}")
            .format(reminder_sql)
        )
        executor_sql = sql.Identifier(INVITE_ROLE)
        if not conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (INVITE_ROLE,)
        ).fetchone():
            conn.execute(
                sql.SQL("CREATE ROLE {} NOLOGIN BYPASSRLS").format(executor_sql)
            )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(executor_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, UPDATE ON invitacion_personal TO {}")
            .format(executor_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT ON negocio TO {}").format(executor_sql)
        )
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT ON usuario, membresia, profesional TO {}")
            .format(executor_sql)
        )
        conn.execute(
            sql.SQL(
                "ALTER FUNCTION aceptar_invitacion_personal(bytea, text, text, text) "
                "OWNER TO {}"
            ).format(executor_sql)
        )
        conn.execute(
            sql.SQL(
                "ALTER FUNCTION validar_invitacion_personal(bytea, text) OWNER TO {}"
            ).format(executor_sql)
        )
        conn.execute(
            sql.SQL(
                "ALTER FUNCTION aceptar_invitacion_personal_existente(bytea) OWNER TO {}"
            ).format(executor_sql)
        )
        conn.execute(
            sql.SQL(
                "GRANT EXECUTE ON FUNCTION "
                "aceptar_invitacion_personal(bytea, text, text, text) TO {}"
            ).format(role_sql)
        )
        conn.execute(
            sql.SQL(
                "GRANT EXECUTE ON FUNCTION "
                "validar_invitacion_personal(bytea, text) TO {}"
            ).format(role_sql)
        )
        conn.execute(
            sql.SQL(
                "GRANT EXECUTE ON FUNCTION "
                "aceptar_invitacion_personal_existente(bytea) TO {}"
            ).format(role_sql)
        )
    for filename in applied:
        print(f"Migración aplicada: {filename}")


if __name__ == "__main__":
    main()
