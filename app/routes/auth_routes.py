from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.auth import is_allowed_domain, oauth
from app.config import settings
from app.templating import templates

router = APIRouter()


@router.get("/login")
async def login_page(request: Request, next: str = "/", error: str | None = None):
    if request.session.get("user"):
        return RedirectResponse(url=next or "/")
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "next": next,
            "error": error,
            "allowed_domain": settings.allowed_email_domain,
        },
    )


@router.get("/auth/google")
async def auth_google(request: Request, next: str = "/"):
    request.session["post_login_redirect"] = next
    redirect_uri = f"{settings.base_url}/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri, hd=settings.allowed_email_domain)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").strip()
    email_verified = userinfo.get("email_verified", False)

    if not email or not email_verified or not is_allowed_domain(email):
        qs = urlencode({"error": "Tu cuenta no pertenece al dominio autorizado de la empresa."})
        return RedirectResponse(url=f"/login?{qs}")

    request.session["user"] = {
        "email": email,
        "name": userinfo.get("name") or email,
        "picture": userinfo.get("picture"),
    }
    next_path = request.session.pop("post_login_redirect", "/") or "/"
    return RedirectResponse(url=next_path)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
