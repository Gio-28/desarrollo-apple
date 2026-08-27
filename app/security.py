import datetime
import secrets

import bcrypt
import pyotp

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 10


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


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, username: str, issuer: str = "Apple Travel Contratos") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    return pyotp.TOTP(secret).verify(code, valid_window=1)


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
