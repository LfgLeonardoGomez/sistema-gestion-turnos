"""Controles transversales para operaciones sensibles."""

from hashlib import sha256

from fastapi import HTTPException, Request
from starlette.responses import Response


class RequestBodyLimitMiddleware:
    """Rechaza cuerpos grandes antes de que FastAPI analice el JSON."""

    def __init__(self, app, max_bytes: int = 65536):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > self.max_bytes:
            await Response(status_code=413)(scope, receive, send)
            return

        buffered = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                await Response(status_code=413)(scope, receive, send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay, send)


def enforce_rate_limit(
    request: Request, scope: str, identity: str, *, max_attempts: int, window_seconds: int
) -> None:
    """Consume un cupo en PostgreSQL, independiente del proceso de API.

    Nunca se confía en X-Forwarded-For: sólo un proxy configurado como confiable
    debería modificar request.client. Se usa otra conexión para que un 4xx
    posterior no revierta el consumo del cupo.
    """
    key = sha256(f"{scope}\0{identity}".encode("utf-8")).digest()
    with request.app.state.pool.connection() as conn:
        allowed = conn.execute(
            "SELECT consumir_limite_seguridad(%s, %s, %s) AS allowed",
            (key, max_attempts, window_seconds),
        ).fetchone()["allowed"]
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos. Probá de nuevo más tarde.",
            headers={"Retry-After": str(window_seconds)},
        )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
