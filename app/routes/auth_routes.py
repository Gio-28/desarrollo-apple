import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    current_user,
    get_csrf_token,
    get_user_by_id,
    get_user_by_username,
    register_failed_attempt,
    reset_failed_attempts,
    set_email,
    set_password,
)
from app.security import (
    OTP_TTL_MINUTES,
    constant_time_eq,
    email_is_valid,
    generate_otp_code,
    is_locked,
    lockout_remaining_seconds,
    password_is_strong,
    verify_password,
)
from app.services.email_client import send_otp_email
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
    for key in ("pending_user_id", "pending_otp_code", "pending_otp_expires"):
        request.session.pop(key, None)
    next_path = request.session.pop("post_login_redirect", "/") or "/"
    return RedirectResponse(url=next_path, status_code=303)


def _send_login_code(request: Request, user: dict) -> str | None:
    """Genera y envia el codigo de verificacion. Devuelve un mensaje de error, o None si fue bien."""
    code = generate_otp_code()
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=OTP_TTL_MINUTES)
    request.session["pending_otp_code"] = code
    request.session["pending_otp_expires"] = expires.isoformat()
    try:
        send_otp_email(user["email"], code)
    except Exception as exc:  # noqa: BLE001
        return f"No se pudo enviar el codigo por correo ({exc}). Contacta a un administrador."
    return None


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
    if not user["email"]:
        return RedirectResponse(url="/configurar-correo", status_code=303)

    err = _send_login_code(request, user)
    if err:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "next": next, "error": err, "csrf_token": get_csrf_token(request)},
            status_code=502,
        )
    return RedirectResponse(url="/verificar-codigo", status_code=303)


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
        if not fresh["email"]:
            return RedirectResponse(url="/configurar-correo", status_code=303)
        err = _send_login_code(request, fresh)
        if err:
            return templates.TemplateResponse("cambiar_clave.html", {"request": request, "error": err, "csrf_token": get_csrf_token(request)}, status_code=502)
        return RedirectResponse(url="/verificar-codigo", status_code=303)

    return templates.TemplateResponse(
        "cambiar_clave.html",
        {"request": request, "error": None, "success": True, "csrf_token": get_csrf_token(request)},
    )


@router.get("/configurar-correo")
async def configurar_correo_page(request: Request, error: str | None = None):
    user = _pending_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "configurar_correo.html",
        {"request": request, "error": error, "csrf_token": get_csrf_token(request)},
    )


@router.post("/configurar-correo")
async def configurar_correo_submit(
    request: Request,
    email: str = Form(...),
    confirmar_email: str = Form(...),
    csrf_token: str = Form(...),
):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request)
    if not user or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    email = email.strip().lower()
    if email != confirmar_email.strip().lower() or not email_is_valid(email):
        return templates.TemplateResponse(
            "configurar_correo.html",
            {"request": request, "error": "Los correos no coinciden o no son validos.", "csrf_token": get_csrf_token(request)},
            status_code=400,
        )

    set_email(user["id"], email)
    fresh = get_user_by_id(user["id"])
    err = _send_login_code(request, fresh)
    if err:
        return templates.TemplateResponse(
            "configurar_correo.html",
            {"request": request, "error": err, "csrf_token": get_csrf_token(request)},
            status_code=502,
        )
    return RedirectResponse(url="/verificar-codigo", status_code=303)


@router.get("/verificar-codigo")
async def verificar_codigo_page(request: Request, error: str | None = None):
    user = _pending_user(request)
    if not user or not request.session.get("pending_otp_code"):
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "verificar_codigo.html",
        {"request": request, "error": error, "email": user["email"], "csrf_token": get_csrf_token(request)},
    )


@router.post("/verificar-codigo")
async def verificar_codigo_submit(request: Request, code: str = Form(...), csrf_token: str = Form(...)):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request)
    pending_code = request.session.get("pending_otp_code")
    if not user or not pending_code or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    if is_locked(user):
        request.session.pop("pending_user_id", None)
        return RedirectResponse(url="/login?error=" + "Cuenta bloqueada temporalmente.")

    expires_raw = request.session.get("pending_otp_expires")
    expired = not expires_raw or datetime.datetime.now(datetime.timezone.utc) > datetime.datetime.fromisoformat(expires_raw)

    if expired or not constant_time_eq(code.strip(), pending_code):
        register_failed_attempt(user["id"])
        return templates.TemplateResponse(
            "verificar_codigo.html",
            {"request": request, "error": "Codigo incorrecto o vencido.", "email": user["email"], "csrf_token": get_csrf_token(request)},
            status_code=401,
        )

    return _finish_login(request, user)


@router.post("/verificar-codigo/reenviar")
async def verificar_codigo_reenviar(request: Request, csrf_token: str = Form(...)):
    session_csrf = request.session.get("csrf_token")
    user = _pending_user(request)
    if not user or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    err = _send_login_code(request, user)
    return templates.TemplateResponse(
        "verificar_codigo.html",
        {
            "request": request,
            "error": err,
            "ok": None if err else "Se envio un nuevo codigo.",
            "email": user["email"],
            "csrf_token": get_csrf_token(request),
        },
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
