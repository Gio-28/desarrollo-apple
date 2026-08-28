import datetime
import hashlib
import re
import secrets

import bcrypt

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 10
OTP_TTL_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 30
TRUSTED_DEVICE_DAYS = 30
TRUSTED_DEVICE_COOKIE = "trusted_device"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def password_is_strong(password: str) -> str | None:
    """Devuelve un mensaje de error si la contraseña es debil, o None si es valida."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        return "La contraseña debe combinar mayusculas, minusculas, numeros o simbolos (al menos 3 tipos)."
    return None


def generate_temp_password() -> str:
    return secrets.token_urlsafe(12)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_is_valid(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def is_locked(user: dict) -> bool:
    locked_until = user.get("locked_until")
    if not locked_until:
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    return locked_until > now


def lockout_remaining_seconds(user: dict) -> int:
    locked_until = user.get("locked_until")
    if not locked_until:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(0, int((locked_until - now).total_seconds()))


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_eq(a: str, b: str) -> bool:
    return secrets.compare_digest(a or "", b or "")


def safe_next_path(path: str | None) -> str:
    """Evita un 'open redirect': solo permite redirigir despues del login a una ruta
    relativa DENTRO del propio sitio. Rechaza cualquier cosa que no empiece exactamente
    con un solo '/' -- en particular '//evil.com' o '/\\evil.com', que los navegadores
    tratan como una URL absoluta a otro dominio aunque empiecen con '/'."""
    if not path or not path.startswith("/") or path.startswith("//") or path.startswith("/\\"):
        return "/"
    return path


def generate_device_token() -> str:
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
