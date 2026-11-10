"""Operaciones de agenda con autorizaciÃ³n por negocio y auditorÃ­a de cambios."""

from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from psycopg import errors

from turnos.api import BusinessDep
from turnos.db import ConnDep


router = APIRouter(prefix="/turnos", tags=["turnos"])


class TurnoInput(BaseModel):
    profesional_id: UUID
    cliente_id: UUID
    inicio: datetime
    duracion_minutos: int | None = Field(default=None, ge=1, le=1439)
    motivo: str | None = Field(default=None, max_length=2000)
    recordatorio_minutos_antes: int | None = Field(default=None, ge=1, le=43200)
    recordatorio_email: bool = False


class ReprogramarInput(BaseModel):
    profesional_id: UUID
    inicio: datetime
    duracion_minutos: int | None = Field(default=None, ge=1, le=1439)


def _permiso(conn: ConnDep, business: BusinessDep, profesional_id: UUID,
             *, bloquear: bool = False) -> dict:
    row = conn.execute(
        "SELECT id, usuario_id, duracion_predeterminada_minutos FROM profesional "
        "WHERE negocio_id = %s AND id = %s AND activo" + (" FOR UPDATE" if bloquear else ""),
        (business.negocio_id, profesional_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Profesional inexistente o inactivo")
    if business.rol == "profesional" and row["usuario_id"] != business.usuario_id:
        raise HTTPException(403, "Solo podÃ©s gestionar tu propia agenda")
    if business.rol not in {"admin", "recepcionista", "profesional"}:
        raise HTTPException(403, "Permiso insuficiente")
    return row


def _intervalo(conn: ConnDep, negocio_id: UUID, profesional_id: UUID,
               inicio: datetime, duracion: int) -> datetime:
    if inicio.tzinfo is None or inicio.utcoffset() is None:
        raise HTTPException(422, "El inicio debe incluir zona horaria")
    if inicio.second or inicio.microsecond:
        raise HTTPException(422, "El inicio debe tener precisiÃ³n de minutos")
    fin = inicio + timedelta(minutes=duracion)
    zone = conn.execute(
        "SELECT zona_horaria FROM negocio WHERE id = %s", (negocio_id,)
    ).fetchone()
    if zone is None:
        raise HTTPException(404, "Negocio inexistente")
    try:
        tz = ZoneInfo(zone["zona_horaria"])
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(500, "Zona horaria del negocio invÃ¡lida") from exc
    local_start = inicio.astimezone(tz)
    local_end = fin.astimezone(tz)
    if local_start.date() != local_end.date():
        raise HTTPException(422, "El turno debe estar en una sola jornada local")
    # Los horarios son intervalos [inicio, fin]; se permite terminar exactamente al cierre.
    if not conn.execute(
        "SELECT 1 FROM horario_profesional WHERE negocio_id = %s "
        "AND profesional_id = %s AND dia_semana = %s "
        "AND hora_inicio <= %s AND hora_fin >= %s LIMIT 1",
        (negocio_id, profesional_id, local_start.weekday(),
         local_start.time().replace(tzinfo=None), local_end.time().replace(tzinfo=None)),
    ).fetchone():
        raise HTTPException(422, "El turno queda fuera del horario profesional")
    return fin


def _cliente(conn: ConnDep, business: BusinessDep, cliente_id: UUID,
             email: bool, *, permitir_archivado: bool = False) -> None:
    row = conn.execute(
        "SELECT email FROM cliente "
        "WHERE negocio_id = %s AND id = %s" +
        ("" if permitir_archivado else " AND archivado_en IS NULL"),
        (business.negocio_id, cliente_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Cliente inexistente o archivado")
    if email and not row["email"]:
        raise HTTPException(422, "El cliente no tiene email")


def _evento(conn: ConnDep, business: BusinessDep, turno_id: UUID, accion: str) -> None:
    conn.execute(
        "INSERT INTO evento_turno (negocio_id, turno_id, actor_usuario_id, accion) "
        "VALUES (%s, %s, %s, %s)",
        (business.negocio_id, turno_id, business.usuario_id, accion),
    )


@router.post("", status_code=201)
def crear_turno(data: TurnoInput, business: BusinessDep, conn: ConnDep) -> dict:
    profesional = _permiso(conn, business, data.profesional_id, bloquear=True)
    _cliente(conn, business, data.cliente_id, data.recordatorio_email)
    duracion = data.duracion_minutos or profesional["duracion_predeterminada_minutos"]
    fin = _intervalo(conn, business.negocio_id, data.profesional_id, data.inicio, duracion)
    try:
        row = conn.execute(
            "INSERT INTO turno (negocio_id, profesional_id, cliente_id, inicio, fin, "
            "motivo, recordatorio_minutos_antes, recordatorio_email, "
            "creado_por_usuario_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (business.negocio_id, data.profesional_id, data.cliente_id, data.inicio,
             fin, data.motivo, data.recordatorio_minutos_antes,
             data.recordatorio_email, business.usuario_id),
        ).fetchone()
        _evento(conn, business, row["id"], "creado")
        conn.commit()
    except errors.ExclusionViolation as exc:
        conn.rollback()
        raise HTTPException(409, "El horario ya estÃ¡ ocupado") from exc
    return {"id": row["id"], "inicio": data.inicio, "fin": fin, "estado": "programado"}


@router.get("")
def listar_turnos(business: BusinessDep, conn: ConnDep,
                  desde: Annotated[datetime, Query()],
                  hasta: Annotated[datetime, Query()],
                  profesional_id: UUID | None = None) -> list[dict]:
    if desde.tzinfo is None or hasta.tzinfo is None or desde >= hasta:
        raise HTTPException(422, "Rango invÃ¡lido o sin zona horaria")
    if hasta - desde > timedelta(days=31):
        raise HTTPException(422, "El rango no puede superar 31 dÃ­as")
    if profesional_id:
        _permiso(conn, business, profesional_id)
    rows = conn.execute(
        "SELECT t.id, t.profesional_id, t.cliente_id, t.inicio, t.fin, t.estado, "
        "t.motivo FROM turno t JOIN profesional p ON p.negocio_id = t.negocio_id "
        "AND p.id = t.profesional_id WHERE t.negocio_id = %s "
        "AND t.inicio < %s AND t.fin > %s AND (%s::uuid IS NULL OR t.profesional_id = %s) "
        "AND t.estado = 'programado' "
        "AND (%s <> 'profesional' OR p.usuario_id = %s) ORDER BY t.inicio LIMIT 500",
        (business.negocio_id, hasta, desde, profesional_id, profesional_id,
         business.rol, business.usuario_id),
    ).fetchall()
    return list(rows)


@router.get("/calendario")
def calendario_turnos(
    business: BusinessDep,
    conn: ConnDep,
    mes: Annotated[str, Query(pattern=r"^(19|20|21)\d{2}-(0[1-9]|1[0-2])$")],
    profesional_id: UUID | None = None,
) -> list[dict]:
    """Conteos de turnos vigentes por fecha local del negocio."""
    if profesional_id:
        _permiso(conn, business, profesional_id)
    first = date.fromisoformat(f"{mes}-01")
    next_month = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)
    zone_row = conn.execute(
        "SELECT zona_horaria FROM negocio WHERE id = %s", (business.negocio_id,)
    ).fetchone()
    if zone_row is None:
        raise HTTPException(404, "Negocio inexistente")
    try:
        zone = ZoneInfo(zone_row["zona_horaria"])
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(500, "Zona horaria del negocio inválida") from exc
    start = datetime.combine(first, datetime.min.time(), zone)
    end = datetime.combine(next_month, datetime.min.time(), zone)
    rows = conn.execute(
        "SELECT (t.inicio AT TIME ZONE %s)::date AS fecha, count(*)::int AS cantidad "
        "FROM turno t JOIN profesional p ON p.negocio_id = t.negocio_id AND p.id = t.profesional_id "
        "WHERE t.negocio_id = %s AND t.inicio >= %s AND t.inicio < %s "
        "AND t.estado = 'programado' "
        "AND (%s::uuid IS NULL OR t.profesional_id = %s) "
        "AND (%s <> 'profesional' OR p.usuario_id = %s) "
        "GROUP BY fecha ORDER BY fecha",
        (zone_row["zona_horaria"], business.negocio_id, start, end,
         profesional_id, profesional_id, business.rol, business.usuario_id),
    ).fetchall()
    return list(rows)


@router.post("/{turno_id}/cancelar")
def cancelar_turno(turno_id: UUID, business: BusinessDep, conn: ConnDep) -> dict:
    row = conn.execute(
        "SELECT profesional_id, estado FROM turno WHERE negocio_id = %s AND id = %s FOR UPDATE",
        (business.negocio_id, turno_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Turno inexistente")
    _permiso(conn, business, row["profesional_id"])
    if row["estado"] != "programado":
        raise HTTPException(409, "Solo se puede cancelar un turno programado")
    conn.execute(
        "UPDATE turno SET estado = 'cancelado', actualizado_en = now() "
        "WHERE negocio_id = %s AND id = %s", (business.negocio_id, turno_id),
    )
    _evento(conn, business, turno_id, "cancelado")
    conn.commit()
    return {"id": turno_id, "estado": "cancelado"}


@router.post("/{turno_id}/reprogramar", status_code=201)
def reprogramar_turno(turno_id: UUID, data: ReprogramarInput,
                      business: BusinessDep, conn: ConnDep) -> dict:
    original = conn.execute(
        "SELECT * FROM turno WHERE negocio_id = %s AND id = %s FOR UPDATE",
        (business.negocio_id, turno_id),
    ).fetchone()
    if original is None:
        raise HTTPException(404, "Turno inexistente")
    _permiso(conn, business, original["profesional_id"])
    profesional = _permiso(conn, business, data.profesional_id, bloquear=True)
    if original["estado"] != "programado":
        raise HTTPException(409, "Solo se puede reprogramar un turno programado")
    _cliente(conn, business, original["cliente_id"], original["recordatorio_email"])
    duracion = data.duracion_minutos or int(
        (original["fin"] - original["inicio"]).total_seconds() // 60
    )
    fin = _intervalo(conn, business.negocio_id, data.profesional_id, data.inicio, duracion)
    try:
        # Una Ãºnica transacciÃ³n: si la nueva reserva falla, tambiÃ©n se revierte el estado anterior.
        conn.execute(
            "UPDATE turno SET estado = 'reprogramado', actualizado_en = now() "
            "WHERE negocio_id = %s AND id = %s", (business.negocio_id, turno_id),
        )
        nuevo = conn.execute(
            "INSERT INTO turno (negocio_id, profesional_id, cliente_id, inicio, fin, motivo, "
            "recordatorio_minutos_antes, recordatorio_email, "
            "creado_por_usuario_id, reprogramado_desde_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (business.negocio_id, data.profesional_id, original["cliente_id"],
             data.inicio, fin, original["motivo"], original["recordatorio_minutos_antes"],
             original["recordatorio_email"],
             business.usuario_id, turno_id),
        ).fetchone()
        _evento(conn, business, turno_id, "reprogramado")
        _evento(conn, business, nuevo["id"], "creado")
        conn.commit()
    except errors.ExclusionViolation as exc:
        conn.rollback()
        raise HTTPException(409, "El nuevo horario ya estÃ¡ ocupado") from exc
    return {"id": nuevo["id"], "reprogramado_desde_id": turno_id,
            "inicio": data.inicio, "fin": fin}


@router.get("/clientes/{cliente_id}/historial")
def historial_cliente(cliente_id: UUID, business: BusinessDep, conn: ConnDep) -> list[dict]:
    _cliente(conn, business, cliente_id, False, permitir_archivado=True)
    rows = conn.execute(
        "SELECT t.id, t.profesional_id, t.inicio, t.fin, t.estado, t.motivo, "
        "t.reprogramado_desde_id FROM turno t "
        "JOIN profesional p ON p.negocio_id = t.negocio_id AND p.id = t.profesional_id "
        "WHERE t.negocio_id = %s AND t.cliente_id = %s "
        "AND (%s <> 'profesional' OR p.usuario_id = %s) "
        "ORDER BY t.inicio DESC LIMIT 500",
        (business.negocio_id, cliente_id, business.rol, business.usuario_id),
    ).fetchall()
    return list(rows)


@router.get("/profesionales/{profesional_id}/historial")
def historial_profesional(profesional_id: UUID, business: BusinessDep,
                          conn: ConnDep) -> list[dict]:
    """Historial completo de una agenda; la agenda diaria solo muestra programados."""
    _permiso(conn, business, profesional_id)
    rows = conn.execute(
        "SELECT t.id, t.cliente_id, t.inicio, t.fin, t.estado, t.motivo, "
        "t.reprogramado_desde_id FROM turno t "
        "WHERE t.negocio_id = %s AND t.profesional_id = %s "
        "ORDER BY t.inicio DESC LIMIT 500",
        (business.negocio_id, profesional_id),
    ).fetchall()
    return list(rows)


