import datetime

from fastapi import Request

from app.db import ensure_db, get_conn
from app.security import (
    LOGIN_APPROVAL_TTL_MINUTES,
    MAX_FAILED_ATTEMPTS,
    LOCKOUT_MINUTES,
    hash_password,
    new_csrf_token,
)

# ---------------------------------------------------------------------------
# Acceso a datos de usuarios
# ---------------------------------------------------------------------------


def get_user_by_username(username: str) -> dict | None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        return cur.fetchone()


def get_user_by_id(user_id: int) -> dict | None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def list_users() -> list[dict]:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM users ORDER BY created_at ASC")
        return cur.fetchall()


def count_admins() -> int:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE is_admin = TRUE")
        return cur.fetchone()["n"]


def create_user(username: str, password: str, is_admin: bool, created_by: str | None, email: str = "") -> dict:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO users (username, password_hash, is_admin, email, must_change_password, created_by)
               VALUES (%s, %s, %s, %s, TRUE, %s) RETURNING *""",
            (username, hash_password(password), is_admin, email or None, created_by),
        )
        row = cur.fetchone()
        conn.commit()
        return row


def set_email(user_id: int, email: str) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET email = %s WHERE id = %s", (email, user_id))
        conn.commit()


def set_totp_secret(user_id: int, secret: str) -> None:
    """Guarda un secreto TOTP pendiente de confirmar (totp_enabled sigue en FALSE)."""
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET totp_secret = %s, totp_enabled = FALSE WHERE id = %s", (secret, user_id))
        conn.commit()


def enable_totp(user_id: int) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET totp_enabled = TRUE WHERE id = %s", (user_id,))
        conn.commit()


def reset_totp(user_id: int) -> None:
    """Borra el Authenticator del usuario: en su proximo ingreso tendra que configurarlo de nuevo."""
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET totp_secret = NULL, totp_enabled = FALSE WHERE id = %s", (user_id,))
        conn.commit()
    revoke_trusted_devices(user_id)


def delete_user(user_id: int) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def reset_password(user_id: int, new_password: str) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s, must_change_password = TRUE, failed_attempts = 0, locked_until = NULL WHERE id = %s",
            (hash_password(new_password), user_id),
        )
        conn.commit()
    revoke_trusted_devices(user_id)


def set_password(user_id: int, new_password: str) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s, must_change_password = FALSE WHERE id = %s",
            (hash_password(new_password), user_id),
        )
        conn.commit()
    revoke_trusted_devices(user_id)


def register_failed_attempt(user_id: int) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT failed_attempts FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        attempts = (row["failed_attempts"] if row else 0) + 1
        locked_until = None
        if attempts >= MAX_FAILED_ATTEMPTS:
            locked_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=LOCKOUT_MINUTES)
            attempts = 0
        cur.execute(
            "UPDATE users SET failed_attempts = %s, locked_until = COALESCE(%s, locked_until) WHERE id = %s",
            (attempts, locked_until, user_id),
        )
        conn.commit()


def reset_failed_attempts(user_id: int) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = %s", (user_id,))
        conn.commit()


def bootstrap_admin(username: str, password: str) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users")
        if cur.fetchone()["n"] == 0:
            cur.execute(
                """INSERT INTO users (username, password_hash, is_admin, must_change_password, created_by)
                   VALUES (%s, %s, TRUE, TRUE, 'bootstrap')""",
                (username, hash_password(password)),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Dispositivos de confianza (omitir codigo de verificacion)
# ---------------------------------------------------------------------------


def add_trusted_device(user_id: int, token_hash: str, expires_at, user_agent: str = "") -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO trusted_devices (user_id, token_hash, expires_at, user_agent) VALUES (%s, %s, %s, %s)",
            (user_id, token_hash, expires_at, user_agent[:255]),
        )
        conn.commit()


def is_trusted_device(user_id: int, token_hash: str) -> bool:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM trusted_devices WHERE user_id = %s AND token_hash = %s AND expires_at > now()",
            (user_id, token_hash),
        )
        return cur.fetchone() is not None


def revoke_trusted_devices(user_id: int) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM trusted_devices WHERE user_id = %s", (user_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Solicitudes de acceso (los asesores esperan la aprobacion de un administrador)
# ---------------------------------------------------------------------------


def create_login_request(user_id: int, user_agent: str = "", ip: str = "") -> int:
    ensure_db()
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=LOGIN_APPROVAL_TTL_MINUTES)
    with get_conn() as conn, conn.cursor() as cur:
        # una sola solicitud viva por usuario: las anteriores pendientes quedan sin efecto
        cur.execute("UPDATE login_requests SET status = 'denied' WHERE user_id = %s AND status IN ('pending', 'approved')", (user_id,))
        cur.execute(
            "INSERT INTO login_requests (user_id, expires_at, user_agent, ip) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, expires, user_agent[:255], ip[:64]),
        )
        request_id = cur.fetchone()["id"]
        conn.commit()
        return request_id


def get_login_request(request_id: int, user_id: int) -> dict | None:
    """Devuelve la solicitud solo si pertenece a ese usuario."""
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM login_requests WHERE id = %s AND user_id = %s", (request_id, user_id))
        return cur.fetchone()


def list_pending_login_requests() -> list[dict]:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT r.id, r.created_at, r.user_agent, r.ip, u.username
               FROM login_requests r JOIN users u ON u.id = r.user_id
               WHERE r.status = 'pending' AND r.expires_at > now()
               ORDER BY r.created_at ASC"""
        )
        return cur.fetchall()


def decide_login_request(request_id: int, approve: bool, decided_by: str) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE login_requests SET status = %s, decided_by = %s, decided_at = now()
               WHERE id = %s AND status = 'pending' AND expires_at > now()""",
            ("approved" if approve else "denied", decided_by, request_id),
        )
        conn.commit()


def consume_login_request(request_id: int) -> None:
    """Marca la solicitud aprobada como usada, para que no sirva para entrar dos veces."""
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE login_requests SET status = 'used' WHERE id = %s", (request_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# Sesion
# ---------------------------------------------------------------------------


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def require_admin(request: Request) -> dict | None:
    user = current_user(request)
    if not user or not user.get("is_admin"):
        return None
    return user


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = new_csrf_token()
        request.session["csrf_token"] = token
    return token
