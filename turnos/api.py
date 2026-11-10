"""API mínima: infraestructura, login y contexto de autorización."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from psycopg import Connection

from turnos.config import get_settings
from turnos.db import ConnDep, create_pool
from turnos.security import RequestBodyLimitMiddleware, client_ip, enforce_rate_limit


def _cookie_name() -> str:
    # __Host- impide Domain y requiere Secure + Path=/ en navegadores modernos.
    return "__Host-turnos_session" if get_settings().cookie_secure else "turnos_session"
password_hash = PasswordHash.recommended()
# Evita una diferencia obvia de tiempo entre email inexistente y clave errónea.
dummy_hash = password_hash.hash("contraseña-no-utilizable")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = create_pool(settings.app_database_url, settings.app_db_password)
    pool.open(wait=True)
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


_dev_docs = os.getenv("APP_ENV", "production") == "development"
app = FastAPI(
    title="Gestión de turnos", lifespan=lifespan,
    docs_url="/docs" if _dev_docs else None,
    redoc_url="/redoc" if _dev_docs else None,
    openapi_url="/openapi.json" if _dev_docs else None,
)
app.add_middleware(RequestBodyLimitMiddleware)


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != get_settings().app_origin:
            return Response(status_code=status.HTTP_403_FORBIDDEN)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class UserView(BaseModel):
    id: UUID
    nombre: str
    email: EmailStr


class BusinessView(BaseModel):
    id: UUID
    nombre: str
    rol: str
    zona_horaria: str


class MeView(BaseModel):
    usuario: UserView
    negocios: list[BusinessView]


class BusinessContext(BaseModel):
    negocio_id: UUID
    usuario_id: UUID
    rol: str


def _session_hash(token: str) -> bytes:
    return sha256(token.encode("utf-8")).digest()


def current_user(request: Request, conn: ConnDep) -> UserView:
    token = request.cookies.get(_cookie_name())
    if not token:
        raise HTTPException(status_code=401, detail="Sesión requerida")
    row = conn.execute(
        "SELECT u.id, u.nombre, u.email FROM sesion s "
        "JOIN usuario u ON u.id = s.usuario_id "
        "WHERE s.token_hash = %s AND s.expira_en > now() "
        "AND s.revocado_en IS NULL AND u.activo",
        (_session_hash(token),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o vencida")
    conn.execute("SELECT set_config('app.usuario_id', %s, true)", (str(row["id"]),))
    return UserView.model_validate(row)


CurrentUserDep = Annotated[UserView, Depends(current_user)]


def current_business(
    conn: ConnDep,
    user: CurrentUserDep,
    business_id: Annotated[UUID, Header(alias="X-Business-Id")],
) -> BusinessContext:
    row = conn.execute(
        "SELECT m.rol FROM membresia AS m "
        "JOIN negocio AS n ON n.id = m.negocio_id "
        "WHERE m.negocio_id = %s AND m.usuario_id = %s "
        "AND m.activo AND n.archivado_en IS NULL",
        (business_id, user.id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=403, detail="Sin acceso a ese negocio")
    conn.execute("SELECT set_config('app.usuario_id', %s, true)", (str(user.id),))
    conn.execute("SELECT set_config('app.negocio_id', %s, true)", (str(business_id),))
    conn.execute("SELECT set_config('app.rol', %s, true)", (row["rol"],))
    return BusinessContext(negocio_id=business_id, usuario_id=user.id, rol=row["rol"])


BusinessDep = Annotated[BusinessContext, Depends(current_business)]


def require_roles(*roles: str):
    """Autorización reusable; toda operación futura debe usar este contexto."""

    def check(context: BusinessDep) -> BusinessContext:
        if context.rol not in roles:
            raise HTTPException(status_code=403, detail="Permiso insuficiente")
        return context

    return check


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(conn: ConnDep) -> dict[str, str]:
    conn.execute("SELECT 1")
    return {"status": "ready"}


@app.post("/auth/login", response_model=UserView)
def login(data: LoginInput, request: Request, response: Response, conn: ConnDep) -> UserView:
    enforce_rate_limit(request, "login-ip", client_ip(request), max_attempts=60, window_seconds=900)
    enforce_rate_limit(request, "login-account", str(data.email).lower(), max_attempts=8, window_seconds=900)
    row = conn.execute(
        "SELECT id, nombre, email, password_hash FROM usuario "
        "WHERE email = %s AND activo",
        (str(data.email).lower(),),
    ).fetchone()
    known_hash = row["password_hash"] if row else dummy_hash
    valid = password_hash.verify(data.password, known_hash)
    if row is None or not valid:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=get_settings().session_hours)
    conn.execute(
        "INSERT INTO sesion (token_hash, usuario_id, expira_en) VALUES (%s, %s, %s)",
        (_session_hash(token), row["id"], expires),
    )
    # Confirmar la sesión antes de enviar la cookie al navegador.
    conn.commit()
    response.set_cookie(
        key=_cookie_name(),
        value=token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        max_age=get_settings().session_hours * 3600,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return UserView.model_validate(row)


@app.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, conn: ConnDep) -> None:
    token = request.cookies.get(_cookie_name())
    if token:
        conn.execute(
            "UPDATE sesion SET revocado_en = now() "
            "WHERE token_hash = %s AND revocado_en IS NULL",
            (_session_hash(token),),
        )
        conn.commit()
    response.delete_cookie(key=_cookie_name(), path="/", secure=get_settings().cookie_secure)
    response.headers["Cache-Control"] = "no-store"


@app.get("/auth/me", response_model=MeView)
def me(conn: ConnDep, user: CurrentUserDep) -> MeView:
    rows = conn.execute(
        "SELECT n.id, n.nombre, n.zona_horaria, m.rol FROM membresia m "
        "JOIN negocio n ON n.id = m.negocio_id "
        "WHERE m.usuario_id = %s AND m.activo AND n.archivado_en IS NULL "
        "ORDER BY n.nombre",
        (user.id,),
    ).fetchall()
    return MeView(usuario=user, negocios=[BusinessView.model_validate(row) for row in rows])


@app.get("/auth/context", response_model=BusinessContext)
def context(business: BusinessDep) -> BusinessContext:
    return business


# Los routers dependen de BusinessDep; importarlos después de declararla evita
# acoplar sus módulos al orden de importación de la aplicación.
from turnos.people_api import clientes_router, profesionales_router  # noqa: E402
from turnos.appointments_api import router as turnos_router  # noqa: E402
from turnos.staff_api import router as personal_router  # noqa: E402

app.include_router(clientes_router)
app.include_router(profesionales_router)
app.include_router(turnos_router)
app.include_router(personal_router)
