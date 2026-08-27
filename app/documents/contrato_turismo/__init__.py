from app.documents import DocumentType, register
from app.documents.contrato_turismo.filler import fill_contract
from app.documents.contrato_turismo.schema import ContratoTurismo, missing_fields
from app.documents.contrato_turismo.text_parser import parse_pasted_text


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
            parse_fn=parse_pasted_text,
            fill_fn=fill_contract,
            signer_fn=_signer,
            missing_fields_fn=missing_fields,
        )
    )
