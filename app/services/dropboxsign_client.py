import httpx

from app.config import settings

API_URL = "https://api.hellosign.com/v3/signature_request/send"


def send_for_signature(
    docx_bytes: bytes,
    filename: str,
    title: str,
    signer_email: str,
    signer_name: str,
    cc_email_addresses: list[str] | None = None,
    subject: str = "Contrato de turismo Apple Travel",
    message: str = "Por favor revisa y firma el contrato adjunto.",
) -> dict:
    """Envia el documento (con text-tags ya incrustados) a Dropbox Sign para firma."""

    files = {"file[0]": (filename, docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    data = {
        "title": title,
        "subject": subject,
        "message": message,
        "signers[0][email_address]": signer_email,
        "signers[0][name]": signer_name,
        "use_text_tags": "1",
        "hide_text_tags": "1",
        "test_mode": "0",
    }
    for i, cc_email in enumerate(cc_email_addresses or []):
        data[f"cc_email_addresses[{i}]"] = cc_email

    with httpx.Client(timeout=60) as client:
        response = client.post(
            API_URL,
            auth=(settings.dropbox_sign_api_key, ""),
            data=data,
            files=files,
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Dropbox Sign error {response.status_code}: {response.text}")

    return response.json()
