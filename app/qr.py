import io

import qrcode
import qrcode.image.svg


def generate_qr_svg(data: str) -> str:
    """Genera un QR como SVG inline (sin depender de Pillow)."""
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")
