"""Worker SMTP de recordatorios. Entrega al menos una vez, nunca exactamente una vez.

El bloqueo de la fila de entrega se mantiene durante SMTP: dos workers no envían
simultáneamente el mismo turno. Un crash después de SMTP y antes del commit puede
producir un duplicado; SMTP no ofrece idempotencia transaccional con PostgreSQL.
"""

import logging
import os
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row


LOG = logging.getLogger(__name__)


def _settings() -> dict:
    env = os.environ
    required = ("REMINDER_DATABASE_URL", "REMINDER_DB_PASSWORD", "SMTP_HOST", "SMTP_FROM")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise ValueError("Faltan variables de recordatorios: " + ", ".join(missing))
    security = env.get("SMTP_SECURITY", "starttls").lower()
    if security not in {"starttls", "ssl"}:
        raise ValueError("SMTP_SECURITY debe ser starttls o ssl")
    port = int(env.get("SMTP_PORT", "465" if security == "ssl" else "587"))
    interval = int(env.get("REMINDER_POLL_SECONDS", "60"))
    if interval < 1 or port < 1 or port > 65535:
        raise ValueError("Configuración de recordatorios inválida")
    if bool(env.get("SMTP_USER")) != bool(env.get("SMTP_PASSWORD")):
        raise ValueError("SMTP_USER y SMTP_PASSWORD deben configurarse juntos")
    return {
        "url": env["REMINDER_DATABASE_URL"],
        "password": env["REMINDER_DB_PASSWORD"],
        "smtp_host": env["SMTP_HOST"],
        "smtp_port": port,
        "smtp_from": env["SMTP_FROM"],
        "smtp_user": env.get("SMTP_USER"),
        "smtp_password": env.get("SMTP_PASSWORD"),
        "smtp_security": security,
        "poll_seconds": interval,
    }


def _enqueue_due(conn: psycopg.Connection) -> None:
    # No se encola hasta el momento de envío. Así, cambios en la anticipación
    # predeterminada del negocio se reflejan antes de la primera entrega.
    conn.execute(
        "INSERT INTO recordatorio_email_entrega (turno_id) "
        "SELECT t.id FROM turno t JOIN negocio n ON n.id = t.negocio_id "
        "JOIN cliente c ON c.id = t.cliente_id AND c.negocio_id = t.negocio_id "
        "WHERE t.estado = 'programado' AND t.recordatorio_email "
        "AND t.inicio > now() AND t.inicio - make_interval(mins => "
        "COALESCE(t.recordatorio_minutos_antes, n.recordatorio_predeterminado_minutos)) <= now() "
        "AND c.email IS NOT NULL AND btrim(c.email) <> '' "
        "AND NOT EXISTS (SELECT 1 FROM recordatorio_email_entrega d WHERE d.turno_id = t.id) "
        "ORDER BY t.inicio LIMIT 100 ON CONFLICT (turno_id) DO NOTHING"
    )


def _claim(conn: psycopg.Connection) -> dict | None:
    return conn.execute(
        "SELECT id, turno_id, intentos FROM recordatorio_email_entrega "
        "WHERE estado = 'pendiente' AND proximo_intento_en <= now() "
        "ORDER BY proximo_intento_en, id FOR UPDATE SKIP LOCKED LIMIT 1"
    ).fetchone()


def _appointment(conn: psycopg.Connection, turno_id) -> dict | None:
    # Bloquea el turno y el cliente hasta finalizar SMTP. Una cancelación o
    # cambio de email concurrente espera, evitando una lectura obsoleta.
    return conn.execute(
        "SELECT t.estado, t.recordatorio_email, t.inicio, "
        "COALESCE(t.recordatorio_minutos_antes, n.recordatorio_predeterminado_minutos) "
        "AS anticipacion, n.nombre AS negocio, n.zona_horaria, "
        "c.nombre AS cliente, c.email, p.nombre AS profesional "
        "FROM turno t JOIN negocio n ON n.id = t.negocio_id "
        "JOIN cliente c ON c.id = t.cliente_id AND c.negocio_id = t.negocio_id "
        "JOIN profesional p ON p.id = t.profesional_id AND p.negocio_id = t.negocio_id "
        "WHERE t.id = %s FOR SHARE OF t, c, n, p", (turno_id,)
    ).fetchone()


def _send(settings: dict, appointment: dict) -> None:
    local = appointment["inicio"].astimezone(ZoneInfo(appointment["zona_horaria"]))
    date = local.strftime("%d/%m/%Y a las %H:%M")
    message = EmailMessage()
    message["From"] = settings["smtp_from"]
    message["To"] = appointment["email"]
    message["Subject"] = f"Recordatorio de turno - {appointment['negocio']}"
    message.set_content(
        f"Hola {appointment['cliente']},\n\n"
        f"Te recordamos tu turno con {appointment['profesional']} en "
        f"{appointment['negocio']} el {date}.\n\n"
        "Si necesitás cambiarlo o cancelarlo, comunicate con el establecimiento.\n"
    )
    context = ssl.create_default_context()
    if settings["smtp_security"] == "ssl":
        smtp = smtplib.SMTP_SSL(settings["smtp_host"], settings["smtp_port"],
                                timeout=20, context=context)
    else:
        smtp = smtplib.SMTP(settings["smtp_host"], settings["smtp_port"], timeout=20)
    with smtp:
        if settings["smtp_security"] == "starttls":
            smtp.starttls(context=context)
        if settings["smtp_user"]:
            smtp.login(settings["smtp_user"], settings["smtp_password"])
        smtp.send_message(message)


def _process_one(conn: psycopg.Connection, settings: dict) -> bool:
    with conn.transaction():
        delivery = _claim(conn)
        if delivery is None:
            return False
        appointment = _appointment(conn, delivery["turno_id"])
        now = datetime.now(timezone.utc)
        if (appointment is None or appointment["estado"] != "programado"
                or not appointment["recordatorio_email"]
                or appointment["inicio"] <= now
                or not appointment["email"]):
            conn.execute(
                "UPDATE recordatorio_email_entrega SET estado = 'omitido', "
                "actualizado_en = now() WHERE id = %s", (delivery["id"],)
            )
            return True
        due = appointment["inicio"] - timedelta(minutes=appointment["anticipacion"])
        if due > now:
            conn.execute(
                "UPDATE recordatorio_email_entrega SET proximo_intento_en = %s, "
                "actualizado_en = now() WHERE id = %s", (due, delivery["id"])
            )
            return True
        try:
            _send(settings, appointment)
        except (OSError, smtplib.SMTPException, ValueError) as exc:
            attempts = delivery["intentos"] + 1
            delay = min(3600, 60 * (2 ** min(attempts - 1, 6)))
            conn.execute(
                "UPDATE recordatorio_email_entrega SET intentos = %s, "
                "proximo_intento_en = now() + make_interval(secs => %s), "
                "ultimo_error = %s, actualizado_en = now() WHERE id = %s",
                (attempts, delay, str(exc)[:500], delivery["id"]),
            )
            LOG.warning("Falló el email para el turno %s: %s", delivery["turno_id"], exc)
        else:
            conn.execute(
                "UPDATE recordatorio_email_entrega SET estado = 'enviado', "
                "intentos = intentos + 1, enviado_en = now(), ultimo_error = NULL, "
                "actualizado_en = now() WHERE id = %s", (delivery["id"],)
            )
            LOG.info("Recordatorio enviado para turno %s", delivery["turno_id"])
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = _settings()
    while True:
        try:
            with psycopg.connect(settings["url"], password=settings["password"],
                                 row_factory=dict_row) as conn:
                _enqueue_due(conn)
                conn.commit()
                for _ in range(100):
                    if not _process_one(conn, settings):
                        break
        except (OSError, psycopg.Error) as exc:
            LOG.exception("Worker de recordatorios sin conexión: %s", exc)
        time.sleep(settings["poll_seconds"])


if __name__ == "__main__":
    main()
