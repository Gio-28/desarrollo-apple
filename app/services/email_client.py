import smtplib
import ssl
from email.mime.text import MIMEText

from app.config import settings
from app.security import OTP_TTL_MINUTES


def send_otp_email(to_email: str, code: str) -> None:
    body = (
        f"Tu codigo de verificacion para el Creador de contratos de Apple Travel es:\n\n"
        f"    {code}\n\n"
        f"Vence en {OTP_TTL_MINUTES} minutos. Si tu no intentaste iniciar sesion, ignora este mensaje."
    )
    msg = MIMEText(body)
    msg["Subject"] = "Codigo de verificacion - Apple Travel"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls(context=context)
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from or settings.smtp_user, [to_email], msg.as_string())
