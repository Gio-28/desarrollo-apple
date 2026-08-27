from anthropic import Anthropic
from pydantic import BaseModel

from app.config import settings

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def extract_structured_data(
    pasted_text: str,
    system_prompt: str,
    schema_model: type[BaseModel],
    tool_name: str = "extraer_datos",
) -> dict:
    """Llama a Claude con tool-use forzado para extraer datos estructurados
    desde texto pegado libremente, siguiendo el JSON schema del modelo Pydantic."""

    input_schema = schema_model.model_json_schema()
    # Anthropic no acepta "$defs" sueltos como top-level sin resolver referencias anidadas,
    # pero los soporta dentro del schema tal cual los genera Pydantic v2, asi que se envia completo.

    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=system_prompt,
        tools=[
            {
                "name": tool_name,
                "description": "Registra los datos extraidos del texto pegado por el asesor comercial.",
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[
            {
                "role": "user",
                "content": f"Texto pegado por el asesor:\n\n{pasted_text}",
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input

    raise RuntimeError("Claude no devolvio una extraccion estructurada valida.")
