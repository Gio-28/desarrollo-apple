from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    current_user,
    get_csrf_token,
    get_user_by_id,
    get_user_by_username,
    register_failed_attempt,
    reset_failed_attempts,
    set_password,
    set_totp_secret,
)
from app.security import (
    constant_time_eq,
    is_locked,
    lockout_remaining_seconds,
    new_totp_secret,
    password_is_strong,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.qr import generate_qr_svg
from app.templating import templates

router = APIRouter()


def _pending_user(request: Request) -> dict | None:
    user_id = request.session.get("pending_user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def _finish_login(request: Request, user: dict) -> RedirectResponse:
    reset_failed_attempts(user["id"])
    request.session["user"] = {"id": user["id"], "username": user["username"], "is_admin": user["is_admin"]}
    for key in ("pending_user_id", "pending_totp_secret"):
        request.session.pop(key, None)
    next_path = request.session.pop("post_login_redirect", "/") or "/"
    return RedirectResponse(url=next_path, status_code=303)


@router.get("/login")
async def login_page(request: Request, next: str = "/", error: str | None = None):
    if current_user(request):
        return RedirectResponse(url=next or "/")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next": next, "error": error, "csrf_token": get_csrf_token(request)},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    website: str = Form(""),
    csrf_token: str = Form(...),
    next: str = Form("/"),
):
    session_csrf = request.session.get("csrf_token")
    generic_error = "Usuario o contraseña incorrectos."

    if website.strip() or not constant_time_eq(csrf_token, session_csrf or ""):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "next": next, "error": generic_error, "csrf_token": get_csrf_token(request)},
            status_code=400,
        )

    user = get_user_by_username(username.strip())
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "next": next, "error": generic_error, "csrf_token": get_csrf_token(request)},
            status_code=401,
        )

    if is_locked(user):
        minutes = max(1, lockout_remaining_seconds(user) // 60)
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "next": next,
                "error": f"Cuenta bloqueada temporalmente por demasiados intentos fallidos. Intenta de nuevo en {minutes} min.",
                "csrf_token": get_csrf_token(request),
            },
            status_code=423,
        )

    if not verify_password(password, user["password_hash"]):
        register_failed_attempt(user["id"])
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "next": next, "error": generic_error, "csrf_token": get_csrf_token(request)},
            status_code=401,
        )

    request.session["pending_user_id"] = user["id"]
    request.session["post_login_redirect"] = next or "/"

    if user["must_change_password"]:
        return RedirectResponse(url="/cambiar-clave", status_code=303)
    if not user["totp_enabled"]:
        return RedirectResponse(url="/2fa/configurar", status_code=303)
    return RedirectResponse(url="/2fa/verificar", status_code=303)


@router.get("/cambiar-clave")
async def cambiar_clave_page(request: Request, error: str | None = None):
    user = _pending_user(request) or current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "cambiar_clave.html",
        {"request": request, "error": error, "csrf_token": get_csrf_token(request)},
    )


@router.post("/cambiar-clave")
async def cambiar_clave_submit(
    request: Request,
    password: str = Form(...),
    confirmar: str = Form(...),
    csrf_token: str = Form(...),
):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request) or current_user(request)
    if not user or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    if password != confirmar:
        return templates.TemplateResponse(
            "cambiar_clave.html",
            {"request": request, "error": "Las contraseñas no coinciden.", "csrf_token": get_csrf_token(request)},
            status_code=400,
        )
    err = password_is_strong(password)
    if err:
        return templates.TemplateResponse(
            "cambiar_clave.html",
            {"request": request, "error": err, "csrf_token": get_csrf_token(request)},
            status_code=400,
        )

    set_password(user["id"], password)

    if request.session.get("pending_user_id"):
        fresh = get_user_by_id(user["id"])
        if not fresh["totp_enabled"]:
            return RedirectResponse(url="/2fa/configurar", status_code=303)
        return RedirectResponse(url="/2fa/verificar", status_code=303)

    return templates.TemplateResponse(
        "cambiar_clave.html",
        {"request": request, "error": None, "success": True, "csrf_token": get_csrf_token(request)},
    )


@router.get("/2fa/configurar")
async def totp_setup_page(request: Request, error: str | None = None):
    user = _pending_user(request)
    if not user:
        return RedirectResponse(url="/login")

    secret = request.session.get("pending_totp_secret")
    if not secret:
        secret = new_totp_secret()
        request.session["pending_totp_secret"] = secret

    uri = totp_provisioning_uri(secret, user["username"])
    qr_svg = generate_qr_svg(uri)

    return templates.TemplateResponse(
        "2fa_setup.html",
        {
            "request": request,
            "error": error,
            "secret": secret,
            "qr_svg": qr_svg,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/2fa/configurar")
async def totp_setup_submit(request: Request, code: str = Form(...), csrf_token: str = Form(...)):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request)
    secret = request.session.get("pending_totp_secret")
    if not user or not secret or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    if not verify_totp(secret, code):
        uri = totp_provisioning_uri(secret, user["username"])
        return templates.TemplateResponse(
            "2fa_setup.html",
            {
                "request": request,
                "error": "Codigo incorrecto, intenta de nuevo.",
                "secret": secret,
                "qr_svg": generate_qr_svg(uri),
                "csrf_token": get_csrf_token(request),
            },
            status_code=400,
        )

    set_totp_secret(user["id"], secret)
    return _finish_login(request, user)


@router.get("/2fa/verificar")
async def totp_verify_page(request: Request, error: str | None = None):
    user = _pending_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "2fa_verify.html",
        {"request": request, "error": error, "csrf_token": get_csrf_token(request)},
    )


@router.post("/2fa/verificar")
async def totp_verify_submit(request: Request, code: str = Form(...), csrf_token: str = Form(...)):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request)
    if not user or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    if is_locked(user):
        request.session.pop("pending_user_id", None)
        return RedirectResponse(url="/login?error=" + "Cuenta bloqueada temporalmente.")

    if not verify_totp(user["totp_secret"], code):
        register_failed_attempt(user["id"])
        return templates.TemplateResponse(
            "2fa_verify.html",
            {"request": request, "error": "Codigo incorrecto.", "csrf_token": get_csrf_token(request)},
            status_code=401,
        )

    return _finish_login(request, user)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
