from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.auth import current_user
from app.documents import get, list_enabled
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


@router.post("/api/{slug}/descargar")
async def api_descargar(request: Request, slug: str):
    # Nota: el envio automatico a firma por Dropbox Sign ya esta implementado
    # (app/services/dropboxsign_client.py, doc_type.signer_fn/cc_fn/document_title_fn) pero
    # esta desactivado porque requiere un plan de API de pago en Dropbox Sign. Para reactivarlo,
    # llamar a send_for_signature(...) aqui en vez de devolver el archivo directamente.
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
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"No se pudo generar el documento: {exc}"}, status_code=500)

    filename = doc_type.document_title_fn(data).strip() or doc_type.slug
    filename = "".join(c for c in filename if c not in '<>:"/\\|?*') + ".docx"

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
