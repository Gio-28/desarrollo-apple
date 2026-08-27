import datetime

from fastapi import Request

from app.db import ensure_db, get_conn
from app.security import (
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


def create_user(username: str, password: str, is_admin: bool, created_by: str | None) -> dict:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO users (username, password_hash, is_admin, must_change_password, created_by)
               VALUES (%s, %s, %s, TRUE, %s) RETURNING *""",
            (username, hash_password(password), is_admin, created_by),
        )
        row = cur.fetchone()
        conn.commit()
        return row


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


def set_password(user_id: int, new_password: str) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s, must_change_password = FALSE WHERE id = %s",
            (hash_password(new_password), user_id),
        )
        conn.commit()


def set_totp_secret(user_id: int, secret: str) -> None:
    ensure_db()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET totp_secret = %s, totp_enabled = TRUE WHERE id = %s",
            (secret, user_id),
        )
        conn.commit()


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
