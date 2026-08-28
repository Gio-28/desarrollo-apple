from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.auth import bootstrap_admin
from app.config import settings
from app.db import ensure_db
from app.routes.admin_routes import router as admin_router
from app.routes.auth_routes import router as auth_router
from app.routes.documents_routes import router as documents_router

BASE_DIR = Path(__file__).resolve().parent.parent
IS_HTTPS = settings.base_url.startswith("https://")

app = FastAPI(title="Apple Travel - Creador de contratos")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if IS_HTTPS:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

if not settings.session_secret:
    # Sin SESSION_SECRET no hay forma segura de firmar las sesiones. Antes esto caia en
    # un secreto fijo ("dev-secret-cambia-esto") visible en el propio repositorio, lo que
    # le permitiria a cualquiera fabricar una cookie de sesion valida (incluida una de
    # administrador) sin usuario ni clave. Mejor que la app no arranque a que arranque
    # insegura: definila en las variables de entorno (ver .env.example) con
    # python -c "import secrets; print(secrets.token_hex(32))"
    raise RuntimeError(
        "Falta la variable de entorno SESSION_SECRET. La aplicacion no puede arrancar sin "
        "ella (ver .env.example)."
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="strict",
    https_only=IS_HTTPS,
    max_age=8 * 60 * 60,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(documents_router)


@app.on_event("startup")
async def on_startup() -> None:
    ensure_db()
    if settings.admin_username and settings.admin_password:
        bootstrap_admin(settings.admin_username, settings.admin_password)
