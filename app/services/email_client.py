import httpx

from app.config import settings
from app.security import OTP_TTL_MINUTES

API_URL = "https://api.sendgrid.com/v3/mail/send"


def send_otp_email(to_email: str, code: str) -> None:
    body = (
        f"Tu codigo de verificacion para el Creador de contratos de Apple Travel es:\n\n"
        f"    {code}\n\n"
        f"Vence en {OTP_TTL_MINUTES} minutos. Si tu no intentaste iniciar sesion, ignora este mensaje."
    )
    response = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
        json={
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": settings.sendgrid_from},
            "subject": "Codigo de verificacion - Apple Travel",
            "content": [{"type": "text/plain", "value": body}],
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid error {response.status_code}: {response.text}")
