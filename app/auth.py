from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import settings

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def require_user(request: Request):
    """FastAPI dependency: returns the logged-in user or a redirect to /login."""
    user = current_user(request)
    if not user:
        return None
    return user


def is_allowed_domain(email: str) -> bool:
    domain = settings.allowed_email_domain.lower().strip()
    return email.lower().endswith("@" + domain)


def login_redirect(next_path: str = "/") -> RedirectResponse:
    resp = RedirectResponse(url=f"/login?next={next_path}")
    return resp
