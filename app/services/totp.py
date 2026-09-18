import base64
from io import BytesIO

import pyotp
import qrcode
import qrcode.image.svg

from app.security import TOTP_ISSUER


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=TOTP_ISSUER)


def qr_data_uri(uri: str) -> str:
    """QR como imagen SVG embebida (data URI), para no depender de servicios externos."""
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buffer = BytesIO()
    img.save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def verify(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    # valid_window=1 tolera un desfase de +-30 s entre el reloj del celular y el servidor
    return pyotp.TOTP(secret).verify(code, valid_window=1)
