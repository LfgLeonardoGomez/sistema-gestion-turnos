"""Clientes compartidos y agendas profesionales, siempre dentro del negocio activo."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from psycopg.errors import UniqueViolation
from datetime import time
from zoneinfo import ZoneInfo

from turnos.api import BusinessContext, BusinessDep
from turnos.db import ConnDep
from turnos.phone import normalizar_telefono
from turnos.security import enforce_rate_limit


clientes_router = APIRouter(prefix="/clientes", tags=["clientes"])
profesionales_router = APIRouter(prefix="/profesionales", tags=["profesionales"])


class ClienteInput(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    telefono: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    documento: str | None = Field(default=None, max_length=100)
    notas: str | None = Field(default=None, max_length=5000)

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacÃ­o")
        return value


class ClienteView(ClienteInput):
    id: UUID


class ClienteCoincidencia(BaseModel):
    id: UUID
    nombre: str
    telefono: str | None = None
    email: str | None = None
    documento: str | None = None


class ProfesionalInput(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    apellido: str | None = Field(default=None, max_length=200)
    especialidad: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=50)
    whatsapp: str | None = Field(default=None, max_length=50)
    notas: str | None = Field(default=None, max_length=5000)
    usuario_id: UUID | None = None
    duracion_predeterminada_minutos: int = Field(default=30, ge=1, le=1439)
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacÃ­o")
        return value

    @field_validator("apellido", "especialidad", "telefono", "whatsapp", "notas")
    @classmethod
    def texto_opcional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProfesionalView(ProfesionalInput):
    id: UUID


class HorarioInput(BaseModel):
    dia_semana: int = Field(ge=0, le=6)
    hora_inicio: time
    hora_fin: time

    @field_validator("hora_fin")
    @classmethod
    def hora_fin_valida(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("La hora no debe incluir zona horaria")
        return value

    @field_validator("hora_inicio")
    @classmethod
    def hora_inicio_valida(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("La hora no debe incluir zona horaria")
        return value


class HorarioView(HorarioInput):
    id: UUID


def _editable(business: BusinessContext) -> None:
    if business.rol not in {"admin", "recepcionista"}:
        raise HTTPException(status_code=403, detail="Permiso insuficiente")


def _puede_crear_cliente(business: BusinessContext) -> None:
    if business.rol not in {"admin", "recepcionista", "profesional"}:
        raise HTTPException(status_code=403, detail="Permiso insuficiente")


def _admin(business: BusinessContext) -> None:
    if business.rol != "admin":
        raise HTTPException(status_code=403, detail="Permiso insuficiente")


def _professional_or_admin(
    conn: ConnDep, business: BusinessContext, profesional_id: UUID
) -> None:
    """Allow admins to manage any agenda and professionals only their own."""
    if business.rol == "admin":
        return
    if business.rol != "profesional" or profesional_id != _own_professional_id(conn, business):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")


def _own_professional_id(conn: ConnDep, business: BusinessContext) -> UUID:
    row = conn.execute(
        "SELECT id FROM profesional WHERE negocio_id = %s AND usuario_id = %s AND activo",
        (business.negocio_id, business.usuario_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=403, detail="No tenÃ©s una agenda activa en este negocio")
    return row["id"]


@clientes_router.get("", response_model=list[ClienteView])
def list_clientes(
    conn: ConnDep,
    business: BusinessDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[ClienteView]:
    _puede_crear_cliente(business)
    filtro_profesional = ""
    params: list[object] = [business.negocio_id]
    if business.rol == "profesional":
        # La agenda profesional no expone el directorio completo del negocio.
        # Un cliente se vuelve visible cuando existe cualquier turno histÃ³rico
        # suyo con ese profesional, incluso si luego fue cancelado o reprogramado.
        filtro_profesional = (
            " AND (cliente.creado_por_usuario_id = %s OR EXISTS "
            "(SELECT 1 FROM turno t WHERE t.negocio_id = cliente.negocio_id "
            "AND t.cliente_id = cliente.id AND t.profesional_id = %s) OR EXISTS "
            "(SELECT 1 FROM cliente_profesional cp WHERE cp.negocio_id = cliente.negocio_id "
            "AND cp.cliente_id = cliente.id AND cp.profesional_id = %s))"
        )
        params.append(business.usuario_id)
        own_professional_id = _own_professional_id(conn, business)
        params.extend([own_professional_id, own_professional_id])
    filtro_busqueda = ""
    if q and q.strip():
        filtro_busqueda = (
            " AND (cliente.nombre ILIKE %s OR cliente.email ILIKE %s "
            "OR cliente.telefono ILIKE %s OR cliente.documento ILIKE %s)"
        )
        params.extend([f"%{q.strip()}%"] * 4)
    params.extend([limit, offset])
    rows = conn.execute(
        "SELECT id, nombre, telefono, email, documento, notas FROM cliente "
        "WHERE negocio_id = %s AND archivado_en IS NULL " + filtro_profesional + filtro_busqueda +
        "ORDER BY nombre, id LIMIT %s OFFSET %s",
        params,
    ).fetchall()
    return [ClienteView.model_validate(row) for row in rows]


@clientes_router.get("/{cliente_id}", response_model=ClienteView)
def get_cliente(
    cliente_id: Annotated[UUID, Path()], conn: ConnDep, business: BusinessDep
) -> ClienteView:
    _puede_crear_cliente(business)
    filtro_profesional = ""
    params: list[object] = [business.negocio_id, cliente_id]
    if business.rol == "profesional":
        filtro_profesional = (
            " AND (cliente.creado_por_usuario_id = %s OR EXISTS "
            "(SELECT 1 FROM turno t WHERE t.negocio_id = cliente.negocio_id "
            "AND t.cliente_id = cliente.id AND t.profesional_id = %s) OR EXISTS "
            "(SELECT 1 FROM cliente_profesional cp WHERE cp.negocio_id = cliente.negocio_id "
            "AND cp.cliente_id = cliente.id AND cp.profesional_id = %s))"
        )
        params.append(business.usuario_id)
        own_professional_id = _own_professional_id(conn, business)
        params.extend([own_professional_id, own_professional_id])
    row = conn.execute(
        "SELECT id, nombre, telefono, email, documento, notas FROM cliente "
        "WHERE negocio_id = %s AND id = %s AND archivado_en IS NULL " + filtro_profesional,
        params,
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return ClienteView.model_validate(row)


@clientes_router.post("", response_model=ClienteView, status_code=201)
def create_cliente(data: ClienteInput, conn: ConnDep, business: BusinessDep) -> ClienteView:
    _puede_crear_cliente(business)
    row = conn.execute(
        "INSERT INTO cliente (negocio_id, nombre, telefono, email, documento, notas, creado_por_usuario_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id, nombre, telefono, email, documento, notas",
        (business.negocio_id, data.nombre.strip(), normalizar_telefono(data.telefono),
         str(data.email) if data.email else None, data.documento, data.notas, business.usuario_id),
    ).fetchone()
    return ClienteView.model_validate(row)


@clientes_router.post("/coincidencias", response_model=list[ClienteCoincidencia])
def coincidencias_cliente(data: ClienteInput, conn: ConnDep, business: BusinessDep, request: Request) -> list[ClienteCoincidencia]:
    _puede_crear_cliente(business)
    enforce_rate_limit(
        request, "client-match", f"{business.negocio_id}:{business.usuario_id}",
        max_attempts=60, window_seconds=3600,
    )
    rows = conn.execute(
        "SELECT id, nombre, telefono, email, documento FROM detectar_coincidencias_cliente(%s, %s, %s, %s)",
        (business.negocio_id, str(data.email) if data.email else None,
         normalizar_telefono(data.telefono), data.documento),
    ).fetchall()
    return [ClienteCoincidencia.model_validate(row) for row in rows]


@clientes_router.post("/{cliente_id}/vincular", response_model=ClienteView)
def vincular_cliente(cliente_id: Annotated[UUID, Path()], conn: ConnDep, business: BusinessDep) -> ClienteView:
    _puede_crear_cliente(business)
    row = conn.execute(
        "SELECT id, nombre, telefono, email, documento, notas FROM cliente "
        "WHERE negocio_id = %s AND id = %s AND archivado_en IS NULL",
        (business.negocio_id, cliente_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if business.rol == "profesional":
        profesional_id = _own_professional_id(conn, business)
        conn.execute(
            "INSERT INTO cliente_profesional (negocio_id, cliente_id, profesional_id, creado_por_usuario_id) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (business.negocio_id, cliente_id, profesional_id, business.usuario_id),
        )
    return ClienteView.model_validate(row)


@clientes_router.post("/{cliente_id}/profesionales/{profesional_id}", response_model=ClienteView)
def compartir_cliente_con_profesional(
    cliente_id: Annotated[UUID, Path()],
    profesional_id: Annotated[UUID, Path()],
    conn: ConnDep,
    business: BusinessDep,
) -> ClienteView:
    """Administración/recepción comparte una ficha, sin exponerla en búsquedas profesionales."""
    _editable(business)
    cliente = conn.execute(
        "SELECT id, nombre, telefono, email, documento, notas FROM cliente "
        "WHERE negocio_id = %s AND id = %s AND archivado_en IS NULL",
        (business.negocio_id, cliente_id),
    ).fetchone()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    profesional = conn.execute(
        "SELECT 1 FROM profesional WHERE negocio_id = %s AND id = %s AND activo "
        "AND usuario_id IS NOT NULL",
        (business.negocio_id, profesional_id),
    ).fetchone()
    if profesional is None:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    conn.execute(
        "INSERT INTO cliente_profesional "
        "(negocio_id, cliente_id, profesional_id, creado_por_usuario_id) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (business.negocio_id, cliente_id, profesional_id, business.usuario_id),
    )
    return ClienteView.model_validate(cliente)


@clientes_router.put("/{cliente_id}", response_model=ClienteView)
def update_cliente(
    cliente_id: Annotated[UUID, Path()], data: ClienteInput,
    conn: ConnDep, business: BusinessDep,
) -> ClienteView:
    _editable(business)
    row = conn.execute(
        "UPDATE cliente SET nombre = %s, telefono = %s, email = %s, "
        "documento = %s, notas = %s "
        "WHERE negocio_id = %s AND id = %s "
        "AND archivado_en IS NULL "
        "RETURNING id, nombre, telefono, email, documento, notas",
        (data.nombre.strip(), normalizar_telefono(data.telefono), str(data.email) if data.email else None,
         data.documento, data.notas,
         business.negocio_id, cliente_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return ClienteView.model_validate(row)


@clientes_router.delete("/{cliente_id}", status_code=204)
def archive_cliente(
    cliente_id: Annotated[UUID, Path()], conn: ConnDep, business: BusinessDep
) -> None:
    _editable(business)
    row = conn.execute(
        "UPDATE cliente SET archivado_en = now() WHERE negocio_id = %s "
        "AND id = %s AND archivado_en IS NULL RETURNING id",
        (business.negocio_id, cliente_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")


@profesionales_router.get("", response_model=list[ProfesionalView])
def list_profesionales(conn: ConnDep, business: BusinessDep) -> list[ProfesionalView]:
    if business.rol == "profesional":
        own_id = _own_professional_id(conn, business)
        rows = conn.execute(
            "SELECT id, nombre, apellido, especialidad, telefono, whatsapp, notas, "
            "usuario_id, duracion_predeterminada_minutos, activo "
            "FROM profesional WHERE negocio_id = %s AND id = %s",
            (business.negocio_id, own_id),
        ).fetchall()
    else:
        _editable(business)
        rows = conn.execute(
            "SELECT id, nombre, apellido, especialidad, telefono, whatsapp, notas, "
            "usuario_id, duracion_predeterminada_minutos, activo "
            "FROM profesional WHERE negocio_id = %s ORDER BY nombre, id",
            (business.negocio_id,),
        ).fetchall()
    return [ProfesionalView.model_validate(row) for row in rows]


@profesionales_router.post("", response_model=ProfesionalView, status_code=201)
def create_profesional(
    data: ProfesionalInput, conn: ConnDep, business: BusinessDep
) -> ProfesionalView:
    _admin(business)
    telefono = normalizar_telefono(data.telefono)
    whatsapp = normalizar_telefono(data.whatsapp)
    if whatsapp is not None and whatsapp != telefono:
        raise HTTPException(422, "WhatsApp debe coincidir con el teléfono del profesional")
    if data.usuario_id is not None:
        member = conn.execute(
            "SELECT 1 FROM membresia WHERE negocio_id = %s AND usuario_id = %s "
            "AND activo AND rol = 'profesional'",
            (business.negocio_id, data.usuario_id),
        ).fetchone()
        if member is None:
            raise HTTPException(status_code=422, detail="Usuario profesional no pertenece al negocio")
    try:
        with conn.transaction():
            row = conn.execute(
                "INSERT INTO profesional (negocio_id, usuario_id, nombre, apellido, especialidad, telefono, whatsapp, notas, "
                "duracion_predeterminada_minutos, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id, usuario_id, nombre, apellido, especialidad, telefono, whatsapp, notas, duracion_predeterminada_minutos, activo",
                (business.negocio_id, data.usuario_id, data.nombre.strip(), data.apellido,
                 data.especialidad, telefono, whatsapp, data.notas,
                 data.duracion_predeterminada_minutos, data.activo),
            ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Usuario ya tiene agenda en este negocio") from exc
    return ProfesionalView.model_validate(row)


@profesionales_router.put("/{profesional_id}", response_model=ProfesionalView)
def update_profesional(
    profesional_id: Annotated[UUID, Path()], data: ProfesionalInput,
    conn: ConnDep, business: BusinessDep,
) -> ProfesionalView:
    _professional_or_admin(conn, business, profesional_id)
    telefono = normalizar_telefono(data.telefono)
    whatsapp = normalizar_telefono(data.whatsapp)
    if whatsapp is not None and whatsapp != telefono:
        raise HTTPException(422, "WhatsApp debe coincidir con el teléfono del profesional")
    if business.rol == "profesional" and data.usuario_id not in {None, business.usuario_id}:
        raise HTTPException(status_code=403, detail="No podés reasignar tu agenda")
    usuario_id = business.usuario_id if business.rol == "profesional" else data.usuario_id
    if data.usuario_id is not None and business.rol != "profesional":
        member = conn.execute(
            "SELECT 1 FROM membresia WHERE negocio_id = %s AND usuario_id = %s "
            "AND activo AND rol = 'profesional'",
            (business.negocio_id, data.usuario_id),
        ).fetchone()
        if member is None:
            raise HTTPException(status_code=422, detail="Usuario profesional no pertenece al negocio")
    try:
        with conn.transaction():
            predicate = "AND usuario_id = %s" if business.rol == "profesional" else ""
            params = (usuario_id, data.nombre.strip(), data.duracion_predeterminada_minutos,
                      data.activo, business.negocio_id, profesional_id)
            if business.rol == "profesional":
                params += (business.usuario_id,)
            row = conn.execute(
                "UPDATE profesional SET usuario_id = %s, nombre = %s, apellido = %s, especialidad = %s, "
                "telefono = %s, whatsapp = %s, notas = %s, duracion_predeterminada_minutos = %s, activo = %s "
                "WHERE negocio_id = %s AND id = %s " + predicate + " "
                "RETURNING id, usuario_id, nombre, apellido, especialidad, telefono, whatsapp, notas, duracion_predeterminada_minutos, activo",
                (params[0], params[1], data.apellido, data.especialidad, telefono,
                 whatsapp, data.notas, params[2], params[3], params[4], params[5], *params[6:]),
            ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Usuario ya tiene agenda en este negocio") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    return ProfesionalView.model_validate(row)


@profesionales_router.get("/{profesional_id}/horarios", response_model=list[HorarioView])
def list_horarios(
    profesional_id: Annotated[UUID, Path()], conn: ConnDep, business: BusinessDep
) -> list[HorarioView]:
    if business.rol == "profesional" and profesional_id != _own_professional_id(conn, business):
        raise HTTPException(status_code=404, detail="Agenda no encontrada")
    elif business.rol not in {"admin", "recepcionista", "profesional"}:
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    exists = conn.execute(
        "SELECT 1 FROM profesional WHERE negocio_id = %s AND id = %s",
        (business.negocio_id, profesional_id),
    ).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="Agenda no encontrada")
    rows = conn.execute(
        "SELECT id, dia_semana, hora_inicio, hora_fin FROM horario_profesional "
        "WHERE negocio_id = %s AND profesional_id = %s "
        "ORDER BY dia_semana, hora_inicio, id",
        (business.negocio_id, profesional_id),
    ).fetchall()
    return [HorarioView.model_validate(row) for row in rows]


@profesionales_router.put("/{profesional_id}/horarios", response_model=list[HorarioView])
def replace_horarios(
    profesional_id: Annotated[UUID, Path()], horarios: list[HorarioInput],
    conn: ConnDep, business: BusinessDep,
) -> list[HorarioView]:
    _professional_or_admin(conn, business, profesional_id)
    if len(horarios) > 21:
        raise HTTPException(status_code=422, detail="Demasiados tramos horarios")
    for horario in horarios:
        if horario.hora_fin <= horario.hora_inicio:
            raise HTTPException(status_code=422, detail="La hora de fin debe ser posterior al inicio")
    for dia in range(7):
        tramos = sorted(
            (h for h in horarios if h.dia_semana == dia),
            key=lambda h: h.hora_inicio,
        )
        if any(a.hora_fin > b.hora_inicio for a, b in zip(tramos, tramos[1:])):
            raise HTTPException(status_code=422, detail="Los horarios no pueden solaparse")
    with conn.transaction():
        exists = conn.execute(
            "SELECT 1 FROM profesional WHERE negocio_id = %s AND id = %s FOR UPDATE",
            (business.negocio_id, profesional_id),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Agenda no encontrada")
        negocio = conn.execute(
            "SELECT zona_horaria FROM negocio WHERE id = %s",
            (business.negocio_id,),
        ).fetchone()
        if negocio is None:
            raise HTTPException(status_code=404, detail="Negocio no encontrado")
        zona = ZoneInfo(negocio["zona_horaria"])
        futuros = conn.execute(
            "SELECT inicio, fin FROM turno WHERE negocio_id = %s "
            "AND profesional_id = %s AND estado = 'programado' AND fin > now()",
            (business.negocio_id, profesional_id),
        ).fetchall()
        for turno in futuros:
            inicio_local = turno["inicio"].astimezone(zona)
            fin_local = turno["fin"].astimezone(zona)
            # Los horarios semanales no representan intervalos nocturnos.
            if inicio_local.date() != fin_local.date() or not any(
                h.dia_semana == inicio_local.weekday()
                and h.hora_inicio <= inicio_local.time().replace(tzinfo=None)
                and fin_local.time().replace(tzinfo=None) <= h.hora_fin
                for h in horarios
            ):
                raise HTTPException(
                    status_code=409,
                    detail="La nueva jornada deja turnos futuros programados fuera de horario",
                )
        conn.execute(
            "DELETE FROM horario_profesional WHERE negocio_id = %s AND profesional_id = %s",
            (business.negocio_id, profesional_id),
        )
        rows = [
            conn.execute(
                "INSERT INTO horario_profesional "
                "(negocio_id, profesional_id, dia_semana, hora_inicio, hora_fin) "
                "VALUES (%s, %s, %s, %s, %s) "
                "RETURNING id, dia_semana, hora_inicio, hora_fin",
                (business.negocio_id, profesional_id, h.dia_semana, h.hora_inicio, h.hora_fin),
            ).fetchone()
            for h in horarios
        ]
    return [HorarioView.model_validate(row) for row in rows]


