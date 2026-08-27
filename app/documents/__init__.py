"""
Registro de tipos de documento disponibles en la herramienta.

Para anadir un nuevo tipo de documento en el futuro (ej. "cotizacion"):
  1. Crear una carpeta nueva en app/documents/<slug>/ con:
       - schema.py   -> modelo de datos (Pydantic) + lista de campos requeridos
       - filler.py   -> funcion fill(data) -> bytes  (rellena el .docx base)
       - template.docx -> plantilla Word original de ese documento
  2. Registrar un DocumentType() en este archivo (ver "contrato_turismo" abajo).
  3. Automaticamente aparecera como tarjeta en la pagina principal y tendra
     sus propias rutas /crear/<slug>, /api/<slug>/parse, /api/<slug>/generar.

Nada del resto de la aplicacion (auth, layout, envio a firma) necesita tocarse.
"""

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel


@dataclass
class DocumentType:
    slug: str
    title: str
    description: str
    icon: str
    schema_model: type[BaseModel]
    system_prompt: str
    fill_fn: Callable[[BaseModel], bytes]
    signer_fn: Callable[[BaseModel], tuple[str, str]]
    missing_fields_fn: Callable[[BaseModel], list[str]]
    enabled: bool = True


REGISTRY: dict[str, DocumentType] = {}


def register(doc_type: DocumentType) -> DocumentType:
    REGISTRY[doc_type.slug] = doc_type
    return doc_type


def get(slug: str) -> DocumentType | None:
    return REGISTRY.get(slug)


def list_enabled() -> list[DocumentType]:
    return [d for d in REGISTRY.values() if d.enabled]


# Importar aqui cada tipo de documento para que se registre al arrancar la app.
from app.documents.contrato_turismo import register_contrato_turismo  # noqa: E402

register_contrato_turismo()
