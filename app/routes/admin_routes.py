from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import (
    count_admins,
    create_user,
    delete_user,
    get_csrf_token,
    get_user_by_id,
    get_user_by_username,
    list_users,
    require_admin,
    reset_password,
)
from app.security import constant_time_eq, email_is_valid, generate_temp_password, password_is_strong
from app.templating import templates

router = APIRouter()


@router.get("/admin/usuarios")
async def admin_usuarios_page(request: Request, error: str | None = None, ok: str | None = None):
    admin = require_admin(request)
    if not admin:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(
        "admin_usuarios.html",
        {
            "request": request,
            "user": admin,
            "usuarios": list_users(),
            "error": error,
            "ok": ok,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/admin/usuarios")
async def admin_crear_usuario(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    es_admin: str = Form(""),
    csrf_token: str = Form(...),
):
    admin = require_admin(request)
    session_csrf = request.session.get("csrf_token")
    if not admin or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    username = username.strip()
    email = email.strip().lower()
    if not username:
        return RedirectResponse(url="/admin/usuarios?error=" + "El usuario no puede estar vacio.", status_code=303)
    if not email_is_valid(email):
        return RedirectResponse(url="/admin/usuarios?error=" + "El correo no es valido.", status_code=303)
    if get_user_by_username(username):
        return RedirectResponse(url="/admin/usuarios?error=" + "Ya existe un usuario con ese nombre.", status_code=303)

    temp_password = generate_temp_password()
    create_user(username=username, password=temp_password, is_admin=bool(es_admin), created_by=admin["username"], email=email)

    return templates.TemplateResponse(
        "admin_usuarios.html",
        {
            "request": request,
            "user": admin,
            "usuarios": list_users(),
            "error": None,
            "ok": None,
            "nuevo_usuario": username,
            "nueva_clave": temp_password,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/admin/usuarios/{user_id}/eliminar")
async def admin_eliminar_usuario(request: Request, user_id: int, csrf_token: str = Form(...)):
    admin = require_admin(request)
    session_csrf = request.session.get("csrf_token")
    if not admin or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    target = get_user_by_id(user_id)
    if not target:
        return RedirectResponse(url="/admin/usuarios", status_code=303)
    if target["is_admin"] and count_admins() <= 1:
        return RedirectResponse(url="/admin/usuarios?error=" + "No puedes eliminar al ultimo administrador.", status_code=303)
    if target["id"] == admin["id"]:
        return RedirectResponse(url="/admin/usuarios?error=" + "No puedes eliminar tu propia cuenta.", status_code=303)

    delete_user(user_id)
    return RedirectResponse(url="/admin/usuarios?ok=" + "Usuario eliminado.", status_code=303)


@router.post("/admin/usuarios/{user_id}/resetear-clave")
async def admin_resetear_clave(request: Request, user_id: int, csrf_token: str = Form(...)):
    admin = require_admin(request)
    session_csrf = request.session.get("csrf_token")
    if not admin or not constant_time_eq(csrf_token, session_csrf or ""):
        return RedirectResponse(url="/login")

    target = get_user_by_id(user_id)
    if not target:
        return RedirectResponse(url="/admin/usuarios", status_code=303)

    temp_password = generate_temp_password()
    reset_password(user_id, temp_password)

    return templates.TemplateResponse(
        "admin_usuarios.html",
        {
            "request": request,
            "user": admin,
            "usuarios": list_users(),
            "error": None,
            "ok": None,
            "nuevo_usuario": target["username"],
            "nueva_clave": temp_password,
            "reseteo": True,
            "csrf_token": get_csrf_token(request),
        },
    )
