"""Carga datos demo idempotentes para una instalacion local.

El seed usa la cuenta de migraciones porque crea usuarios, membresias y
perfiles profesionales. Nunca se ejecuta automaticamente al iniciar la API.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg
from pwdlib import PasswordHash


BUSINESS_NAME_ENV = "SEED_BUSINESS_NAME"
PROFESSIONAL_PASSWORD_ENV = "SEED_PROFESSIONAL_PASSWORD"

PROFESSIONALS = (
    {
        "email": "sofia.martinez@example.com",
        "nombre": "Sofia",
        "apellido": "Martinez",
        "especialidad": "Odontologia general",
        "telefono": "+54 9 11 5555-0101",
        "whatsapp": "+54 9 11 5555-0101",
        "notas": "Profesional demo para pruebas de agenda.",
        "duracion": 45,
    },
    {
        "email": "lucas.ferreyra@example.com",
        "nombre": "Lucas",
        "apellido": "Ferreyra",
        "especialidad": "Peluqueria",
        "telefono": "+54 9 11 5555-0102",
        "whatsapp": "+54 9 11 5555-0102",
        "notas": "Profesional demo para pruebas de agenda.",
        "duracion": 60,
    },
)

CLIENTS = (
    ("Valentina Rossi", "valentina.rossi@example.com", "+54 9 11 5555-0201", "DNI 40111222"),
    ("Matias Gomez", "matias.gomez@example.com", "+54 9 11 5555-0202", "DNI 40111223"),
    ("Camila Sosa", "camila.sosa@example.com", "+54 9 11 5555-0203", "DNI 40111224"),
    ("Nicolas Diaz", "nicolas.diaz@example.com", "+54 9 11 5555-0204", "DNI 40111225"),
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Definir {name} antes de ejecutar el seed")
    return value


def _next_weekday(start: date, offset: int) -> date:
    """Returns a weekday (Monday=0) at least offset days after start."""
    candidate = start + timedelta(days=max(offset, 1))
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _upsert_user(conn: psycopg.Connection, item: dict, password_hash: str) -> str:
    row = conn.execute("SELECT id FROM usuario WHERE email = %s", (item["email"],)).fetchone()
    if row:
        user_id = row[0]
        conn.execute(
            "UPDATE usuario SET nombre = %s, activo = true WHERE id = %s",
            (f"{item['nombre']} {item['apellido']}", user_id),
        )
    else:
        user_id = conn.execute(
            "INSERT INTO usuario (email, password_hash, nombre) VALUES (%s, %s, %s) RETURNING id",
            (item["email"], password_hash, f"{item['nombre']} {item['apellido']}"),
        ).fetchone()[0]
    return user_id


def _upsert_client(conn: psycopg.Connection, business_id: str, item: tuple[str, ...]) -> str:
    name, email, phone, document = item
    row = conn.execute(
        "SELECT id FROM cliente WHERE negocio_id = %s AND email = %s ORDER BY creado_en LIMIT 1",
        (business_id, email),
    ).fetchone()
    if row:
        client_id = row[0]
        conn.execute(
            "UPDATE cliente SET nombre = %s, telefono = %s, documento = %s, archivado_en = NULL "
            "WHERE id = %s",
            (name, phone, document, client_id),
        )
        return client_id
    return conn.execute(
        "INSERT INTO cliente (negocio_id, nombre, email, telefono, documento, notas) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (business_id, name, email, phone, document, "Cliente demo para pruebas."),
    ).fetchone()[0]


def main() -> None:
    business_name = _required(BUSINESS_NAME_ENV)
    professional_password = _required(PROFESSIONAL_PASSWORD_ENV)
    if len(professional_password) < 12:
        raise ValueError(f"{PROFESSIONAL_PASSWORD_ENV} debe tener al menos 12 caracteres")
    database_url = _required("MIGRATION_DATABASE_URL")
    database_password = _required("MIGRATION_DB_PASSWORD")

    with psycopg.connect(database_url, password=database_password) as conn:
        with conn.transaction():
            business = conn.execute(
                "SELECT id, zona_horaria FROM negocio WHERE nombre = %s AND archivado_en IS NULL "
                "ORDER BY creado_en LIMIT 1",
                (business_name,),
            ).fetchone()
            if not business:
                raise ValueError(f"No existe un negocio activo llamado {business_name!r}; ejecutar bootstrap primero")
            business_id, timezone_name = business
            admin = conn.execute(
                "SELECT m.usuario_id FROM membresia m WHERE m.negocio_id = %s AND m.rol = 'admin' "
                "AND m.activo ORDER BY m.creado_en LIMIT 1",
                (business_id,),
            ).fetchone()
            if not admin:
                raise ValueError("El negocio no tiene un administrador activo")
            admin_id = admin[0]
            password_hash = PasswordHash.recommended().hash(professional_password)
            professionals: list[str] = []
            for item in PROFESSIONALS:
                user_id = _upsert_user(conn, item, password_hash)
                conn.execute(
                    "INSERT INTO membresia (negocio_id, usuario_id, rol) VALUES (%s, %s, 'profesional') "
                    "ON CONFLICT (negocio_id, usuario_id) DO UPDATE SET rol = 'profesional', activo = true",
                    (business_id, user_id),
                )
                profile = conn.execute(
                    "SELECT id FROM profesional WHERE negocio_id = %s AND usuario_id = %s",
                    (business_id, user_id),
                ).fetchone()
                if profile:
                    professional_id = profile[0]
                    conn.execute(
                        "UPDATE profesional SET nombre = %s, apellido = %s, especialidad = %s, "
                        "telefono = %s, whatsapp = %s, notas = %s, duracion_predeterminada_minutos = %s, activo = true "
                        "WHERE id = %s",
                        (item["nombre"], item["apellido"], item["especialidad"], item["telefono"],
                         item["whatsapp"], item["notas"], item["duracion"], professional_id),
                    )
                else:
                    professional_id = conn.execute(
                        "INSERT INTO profesional (negocio_id, usuario_id, nombre, apellido, especialidad, telefono, whatsapp, notas, duracion_predeterminada_minutos) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (business_id, user_id, item["nombre"], item["apellido"], item["especialidad"],
                         item["telefono"], item["whatsapp"], item["notas"], item["duracion"]),
                    ).fetchone()[0]
                conn.execute("DELETE FROM horario_profesional WHERE negocio_id = %s AND profesional_id = %s", (business_id, professional_id))
                for day, start, end in (
                    [(day, time(9), time(13)) for day in range(5)]
                    + [(day, time(14), time(18)) for day in range(5)]
                ):
                    conn.execute(
                        "INSERT INTO horario_profesional (negocio_id, profesional_id, dia_semana, hora_inicio, hora_fin) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (business_id, professional_id, day, start, end),
                    )
                professionals.append(professional_id)

            clients = [_upsert_client(conn, business_id, item) for item in CLIENTS]
            zone = ZoneInfo(timezone_name)
            base = datetime.now(zone).date()
            for index, client_id in enumerate(clients):
                professional_id = professionals[index % len(professionals)]
                local_start = datetime.combine(
                    _next_weekday(base, index + 1), time(10 + (index % 2), 0), tzinfo=zone
                )
                existing = conn.execute(
                    "SELECT id FROM turno WHERE negocio_id = %s AND cliente_id = %s AND profesional_id = %s "
                    "AND motivo = 'Demo seed' LIMIT 1",
                    (business_id, client_id, professional_id),
                ).fetchone()
                if existing:
                    continue
                end = local_start + timedelta(minutes=45 if index % 2 == 0 else 60)
                appointment_id = conn.execute(
                    "INSERT INTO turno (negocio_id, profesional_id, cliente_id, inicio, fin, motivo, "
                    "recordatorio_minutos_antes, recordatorio_email, creado_por_usuario_id) "
                    "VALUES (%s,%s,%s,%s,%s,'Demo seed',1440,true,%s) RETURNING id",
                    (business_id, professional_id, client_id, local_start, end, admin_id),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO evento_turno (negocio_id, turno_id, actor_usuario_id, accion, detalle) "
                    "VALUES (%s,%s,%s,'creado',jsonb_build_object('origen','seed'))",
                    (business_id, appointment_id, admin_id),
                )
    print(f"Seed demo aplicado a {business_name}: 2 profesionales, 4 clientes y hasta 4 turnos nuevos.")


if __name__ == "__main__":
    main()

