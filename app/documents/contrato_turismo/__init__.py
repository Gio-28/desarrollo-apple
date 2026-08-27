from app.documents import DocumentType, register
from app.documents.contrato_turismo.filler import fill_contract
from app.documents.contrato_turismo.schema import SYSTEM_PROMPT, ContratoTurismo, missing_fields


def _signer(data: ContratoTurismo) -> tuple[str, str]:
    return data.cliente_correo, data.cliente_nombre


def register_contrato_turismo() -> None:
    register(
        DocumentType(
            slug="contrato-turismo",
            title="Crear contrato",
            description="Contrato de turismo + confirmacion de reserva, listo para enviar a firma.",
            icon="document",
            schema_model=ContratoTurismo,
            system_prompt=SYSTEM_PROMPT,
            fill_fn=fill_contract,
            signer_fn=_signer,
            missing_fields_fn=missing_fields,
        )
    )
