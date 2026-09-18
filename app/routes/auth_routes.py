import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    add_trusted_device,
    consume_login_request,
    create_login_request,
    current_user,
    enable_totp,
    get_csrf_token,
    get_login_request,
    get_user_by_id,
    get_user_by_username,
    is_trusted_device,
    register_failed_attempt,
    reset_failed_attempts,
    set_password,
    set_totp_secret,
)
from app.config import settings
from app.security import (
    TRUSTED_DEVICE_COOKIE,
    TRUSTED_DEVICE_DAYS,
    constant_time_eq,
    generate_device_token,
    hash_device_token,
    is_locked,
    lockout_remaining_seconds,
    password_is_strong,
    safe_next_path,
    verify_password,
)
from app.services import totp
from app.templating import templates

router = APIRouter()

IS_HTTPS = settings.base_url.startswith("https://")


def _trusted_device_cookie_matches(request: Request, user_id: int) -> bool:
    raw = request.cookies.get(TRUSTED_DEVICE_COOKIE, "")
    if not raw or ":" not in raw:
        return False
    cookie_user_id, _, token = raw.partition(":")
    if cookie_user_id != str(user_id) or not token:
        return False
    return is_trusted_device(user_id, hash_device_token(token))


def _set_trusted_device_cookie(response: RedirectResponse, request: Request, user_id: int) -> None:
    token = generate_device_token()
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=TRUSTED_DEVICE_DAYS)
    add_trusted_device(user_id, hash_device_token(token), expires, request.headers.get("user-agent", ""))
    response.set_cookie(
        TRUSTED_DEVICE_COOKIE,
        f"{user_id}:{token}",
        max_age=TRUSTED_DEVICE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=IS_HTTPS,
        samesite="strict",
        path="/",
    )


def _pending_user(request: Request) -> dict | None:
    user_id = request.session.get("pending_user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def _finish_login(request: Request, user: dict) -> RedirectResponse:
    reset_failed_attempts(user["id"])
    request.session["user"] = {"id": user["id"], "username": user["username"], "is_admin": user["is_admin"]}
    for key in ("pending_user_id", "pending_request_id"):
        request.session.pop(key, None)
    next_path = request.session.pop("post_login_redirect", "/") or "/"
    return RedirectResponse(url=next_path, status_code=303)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _continue_login(request: Request, user: dict) -> RedirectResponse:
    """Decide el siguiente paso despues de validar la contraseña.
    - Administradores: verificacion con Google Authenticator (TOTP).
    - Asesores: esperan a que un administrador apruebe el ingreso."""
    if user["must_change_password"]:
        return RedirectResponse(url="/cambiar-clave", status_code=303)

    if user["is_admin"]:
        if not user["totp_enabled"]:
            return RedirectResponse(url="/configurar-2fa", status_code=303)
        if _trusted_device_cookie_matches(request, user["id"]):
            return _finish_login(request, user)
        return RedirectResponse(url="/verificar-2fa", status_code=303)

    request.session["pending_request_id"] = create_login_request(
        user["id"], request.headers.get("user-agent", ""), _client_ip(request)
    )
    return RedirectResponse(url="/esperando-aprobacion", status_code=303)


@router.get("/login")
async def login_page(request: Request, next: str = "/", error: str | None = None):
    next = safe_next_path(next)
    if current_user(request):
        return RedirectResponse(url=next)
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
    next = safe_next_path(next)
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
    return _continue_login(request, user)


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
        return _continue_login(request, get_user_by_id(user["id"]))

    return templates.TemplateResponse(
        "cambiar_clave.html",
        {"request": request, "error": None, "success": True, "csrf_token": get_csrf_token(request)},
    )


# --------------------------------------------------------------------------
# Administradores: Google Authenticator (TOTP)
# --------------------------------------------------------------------------

@router.get("/configurar-2fa")
async def configurar_2fa_page(request: Request, error: str | None = None):
    user = _pending_user(request)
    if not user or not user["is_admin"] or user["must_change_password"]:
        return RedirectResponse(url="/login")
    if user["totp_enabled"]:
        return RedirectResponse(url="/verificar-2fa", status_code=303)

    secret = user["totp_secret"]
    if not secret:
        secret = totp.new_secret()
        set_totp_secret(user["id"], secret)
    uri = totp.provisioning_uri(secret, user["username"])
    return templates.TemplateResponse(
        "configurar_2fa.html",
        {
            "request": request,
            "error": error,
            "secret": secret,
            "qr": totp.qr_data_uri(uri),
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/configurar-2fa")
async def configurar_2fa_submit(request: Request, code: str = Form(...), csrf_token: str = Form(...)):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request)
    if not user or not user["is_admin"] or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")
    if user["totp_enabled"] or not user["totp_secret"]:
        return RedirectResponse(url="/login")

    if is_locked(user):
        request.session.pop("pending_user_id", None)
        return RedirectResponse(url="/login?error=" + "Cuenta bloqueada temporalmente.", status_code=303)

    if not totp.verify(user["totp_secret"], code):
        register_failed_attempt(user["id"])
        return RedirectResponse(
            url="/configurar-2fa?error=" + "Codigo incorrecto. Usa el codigo actual que muestra la app.",
            status_code=303,
        )

    enable_totp(user["id"])
    return _finish_login(request, user)


@router.get("/verificar-2fa")
async def verificar_2fa_page(request: Request, error: str | None = None):
    user = _pending_user(request)
    if not user or not user["is_admin"] or user["must_change_password"]:
        return RedirectResponse(url="/login")
    if not user["totp_enabled"]:
        return RedirectResponse(url="/configurar-2fa", status_code=303)
    return templates.TemplateResponse(
        "verificar_2fa.html",
        {"request": request, "error": error, "csrf_token": get_csrf_token(request)},
    )


@router.post("/verificar-2fa")
async def verificar_2fa_submit(
    request: Request,
    code: str = Form(...),
    csrf_token: str = Form(...),
    recordar_dispositivo: str = Form(""),
):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request)
    if not user or not user["is_admin"] or not user["totp_enabled"] or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    if is_locked(user):
        request.session.pop("pending_user_id", None)
        return RedirectResponse(url="/login?error=" + "Cuenta bloqueada temporalmente.", status_code=303)

    if not totp.verify(user["totp_secret"], code):
        register_failed_attempt(user["id"])
        return templates.TemplateResponse(
            "verificar_2fa.html",
            {"request": request, "error": "Codigo incorrecto o vencido.", "csrf_token": get_csrf_token(request)},
            status_code=401,
        )

    response = _finish_login(request, user)
    if recordar_dispositivo:
        _set_trusted_device_cookie(response, request, user["id"])
    return response


# --------------------------------------------------------------------------
# Asesores: aprobacion del ingreso por un administrador
# --------------------------------------------------------------------------

@router.get("/esperando-aprobacion")
async def esperando_aprobacion(request: Request):
    user = _pending_user(request)
    request_id = request.session.get("pending_request_id")
    if not user or not request_id or user["is_admin"]:
        return RedirectResponse(url="/login")

    login_request = get_login_request(request_id, user["id"])
    now = datetime.datetime.now(datetime.timezone.utc)
    if not login_request or login_request["status"] in ("denied", "used") or login_request["expires_at"] < now:
        for key in ("pending_user_id", "pending_request_id"):
            request.session.pop(key, None)
        if login_request and login_request["status"] == "denied":
            message = "Un administrador rechazo tu solicitud de ingreso."
        else:
            message = "La solicitud de ingreso vencio. Inicia sesion de nuevo."
        return RedirectResponse(url="/login?error=" + message, status_code=303)

    if login_request["status"] == "approved":
        consume_login_request(request_id)
        return _finish_login(request, user)

    return templates.TemplateResponse(
        "esperando_aprobacion.html",
        {"request": request, "username": user["username"]},
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
