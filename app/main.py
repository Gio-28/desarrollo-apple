from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routes.auth_routes import router as auth_router
from app.routes.documents_routes import router as documents_router

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="Apple Travel - Creador de contratos")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or "dev-secret-cambia-esto",
    same_site="lax",
    https_only=settings.base_url.startswith("https://"),
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth_router)
app.include_router(documents_router)
