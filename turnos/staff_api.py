"""Alta de personal mediante invitaciones efímeras entregadas por el administrador."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from psycopg import Error
from pwdlib import PasswordHash

from turnos.api import BusinessDep, CurrentUserDep
from turnos.db import ConnDep
from turnos.security import client_ip, enforce_rate_limit


router = APIRouter(prefix="/personal", tags=["personal"])
password_hasher = PasswordHash.recommended()


class InvitationInput(BaseModel):
    email: EmailStr
    rol: Literal["recepcionista", "profesional"]


class InvitationIssued(BaseModel):
    id: UUID
    email: EmailStr
    rol: str
    expira_en: datetime
    token: str  # Se devuelve una única vez; nunca se persiste en claro.


class AcceptInput(BaseModel):
    token: str = Field(min_length=40, max_length=256)
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("nombre")
    @classmethod
    def nombre_valido(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío")
        return value


class AcceptedView(BaseModel):
    usuario_id: UUID


class ExistingAcceptInput(BaseModel):
    token: str = Field(min_length=40, max_length=256)


class ExistingAcceptedView(BaseModel):
    negocio_id: UUID


def _admin(business: BusinessDep) -> None:
    if business.rol != "admin":
        raise HTTPException(status_code=403, detail="Permiso insuficiente")


@router.post("/invitaciones", response_model=InvitationIssued, status_code=201)
def invite(data: InvitationInput, business: BusinessDep, conn: ConnDep, response: Response, request: Request) -> InvitationIssued:
    _admin(business)
    enforce_rate_limit(request, "invite-issue", str(business.usuario_id), max_attempts=30, window_seconds=3600)
    email = str(data.email).strip().lower()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=48)
    row = conn.execute(
        "INSERT INTO invitacion_personal "
        "(negocio_id, email, rol, token_hash, creado_por_usuario_id, expira_en) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, email, rol, expira_en",
        (business.negocio_id, email, data.rol, sha256(token.encode()).digest(), business.usuario_id, expires),
    ).fetchone()
    conn.commit()
    response.headers["Cache-Control"] = "no-store"
    return InvitationIssued(**row, token=token)


@router.post("/invitaciones/{invitation_id}/revocar", status_code=204)
def revoke(
    invitation_id: Annotated[UUID, Path()], business: BusinessDep, conn: ConnDep
) -> None:
    _admin(business)
    row = conn.execute(
        "UPDATE invitacion_personal SET revocado_en = now() "
        "WHERE id = %s AND negocio_id = %s AND usado_en IS NULL "
        "AND revocado_en IS NULL RETURNING id",
        (invitation_id, business.negocio_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Invitación no disponible")
    conn.commit()


@router.post("/invitaciones/aceptar", response_model=AcceptedView, status_code=201)
def accept(data: AcceptInput, conn: ConnDep, response: Response, request: Request) -> AcceptedView:
    # Ruta pública. El middleware de la aplicación exige Origin coincidente
    # para toda escritura, incluso ésta. No inicia sesión automáticamente.
    email = str(data.email).strip().lower()
    enforce_rate_limit(request, "invite-ip", client_ip(request), max_attempts=60, window_seconds=900)
    enforce_rate_limit(request, "invite-token", data.token, max_attempts=8, window_seconds=900)
    token_hash = sha256(data.token.encode()).digest()
    valid = conn.execute(
        "SELECT validar_invitacion_personal(%s, %s) AS valido",
        (token_hash, email),
    ).fetchone()["valido"]
    if not valid:
        raise HTTPException(status_code=400, detail="Invitación inválida o vencida")
    try:
        row = conn.execute(
            "SELECT aceptar_invitacion_personal(%s, %s, %s, %s) AS usuario_id",
            (token_hash, email, data.nombre,
             password_hasher.hash(data.password)),
        ).fetchone()
        conn.commit()
    except Error as exc:
        conn.rollback()
        if exc.sqlstate == "P0002":
            raise HTTPException(status_code=409, detail="La cuenta ya existe; iniciá sesión") from exc
        if exc.sqlstate == "P0001":
            raise HTTPException(status_code=400, detail="Invitación inválida o vencida") from exc
        raise
    response.headers["Cache-Control"] = "no-store"
    return AcceptedView(usuario_id=row["usuario_id"])


@router.post("/invitaciones/aceptar-existente", response_model=ExistingAcceptedView, status_code=201)
def accept_existing(
    data: ExistingAcceptInput, user: CurrentUserDep, conn: ConnDep, response: Response, request: Request
) -> ExistingAcceptedView:
    # current_user valida la sesión y establece app.usuario_id en esta transacción.
    # La función compara nuevamente ese ID y el email persistido con la invitación.
    token_hash = sha256(data.token.encode()).digest()
    enforce_rate_limit(request, "invite-existing", str(user.id), max_attempts=30, window_seconds=900)
    try:
        row = conn.execute(
            "SELECT aceptar_invitacion_personal_existente(%s) AS negocio_id",
            (token_hash,),
        ).fetchone()
        conn.commit()
    except Error as exc:
        conn.rollback()
        if exc.sqlstate == "P0002":
            raise HTTPException(status_code=409, detail="La membresía ya existe") from exc
        if exc.sqlstate in {"P0001", "P0003"}:
            raise HTTPException(status_code=400, detail="Invitación inválida o vencida") from exc
        raise
    response.headers["Cache-Control"] = "no-store"
    return ExistingAcceptedView(negocio_id=row["negocio_id"])
