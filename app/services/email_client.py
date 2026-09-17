import httpx

from app.config import settings
from app.security import OTP_TTL_MINUTES

API_URL = "https://api.resend.com/emails"


def send_otp_email(to_email: str, code: str) -> None:
    body = (
        f"Tu codigo de verificacion para el Creador de contratos de Apple Travel es:\n\n"
        f"    {code}\n\n"
        f"Vence en {OTP_TTL_MINUTES} minutos. Si tu no intentaste iniciar sesion, ignora este mensaje."
    )
    response = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={
            "from": settings.resend_from,
            "to": [to_email],
            "subject": "Codigo de verificacion - Apple Travel",
            "text": body,
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Resend error {response.status_code}: {response.text}")
