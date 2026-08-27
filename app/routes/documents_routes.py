from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import current_user
from app.documents import get, list_enabled
from app.services.dropboxsign_client import send_for_signature
from app.templating import templates

router = APIRouter()


@router.get("/")
async def home(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login?next=/")
    return templates.TemplateResponse(
        "home.html", {"request": request, "user": user, "document_types": list_enabled()}
    )


@router.get("/crear/{slug}")
async def crear_documento(request: Request, slug: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/crear/{slug}")

    doc_type = get(slug)
    if not doc_type:
        raise HTTPException(404, "Tipo de documento no encontrado")

    return templates.TemplateResponse(
        "crear_contrato.html",
        {"request": request, "user": user, "doc_type": doc_type},
    )


@router.post("/api/{slug}/parse")
async def api_parse(request: Request, slug: str):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    doc_type = get(slug)
    if not doc_type:
        raise HTTPException(404, "Tipo de documento no encontrado")

    body = await request.json()
    pasted_text = (body.get("text") or "").strip()
    if not pasted_text:
        return JSONResponse({"error": "El texto pegado esta vacio."}, status_code=400)

    try:
        raw = doc_type.parse_fn(pasted_text)
        data = doc_type.schema_model.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"No se pudo interpretar el texto: {exc}"}, status_code=422)

    missing = doc_type.missing_fields_fn(data)
    return JSONResponse({"data": data.model_dump(), "missing": missing})


@router.post("/api/{slug}/generar")
async def api_generar(request: Request, slug: str):
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    doc_type = get(slug)
    if not doc_type:
        raise HTTPException(404, "Tipo de documento no encontrado")

    body = await request.json()
    try:
        data = doc_type.schema_model.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"Datos invalidos: {exc}"}, status_code=422)

    missing = doc_type.missing_fields_fn(data)
    if missing:
        return JSONResponse({"error": "Faltan datos obligatorios", "missing": missing}, status_code=422)

    try:
        docx_bytes = doc_type.fill_fn(data)
        signer_email, signer_name = doc_type.signer_fn(data)
        result = send_for_signature(
            docx_bytes=docx_bytes,
            filename=f"{doc_type.slug}-{signer_name}.docx",
            title=f"{doc_type.title} - {signer_name}",
            signer_email=signer_email,
            signer_name=signer_name,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"No se pudo enviar a firma: {exc}"}, status_code=502)

    return JSONResponse({"ok": True, "result": result})
