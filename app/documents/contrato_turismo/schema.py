from pydantic import BaseModel, Field


class Pago(BaseModel):
    fecha: str = ""
    valor: str = ""


class PasajeroAdicional(BaseModel):
    nombre: str = ""
    cedula: str = ""


class PasajeroReserva(BaseModel):
    nombre: str = ""
    documento: str = ""


class ContratoTurismo(BaseModel):
    asesor_comercial: str = Field("", description="Nombre del asesor comercial de Apple Travel que atendio al cliente")
    cliente_nombre: str = Field("", description="Nombre completo del cliente / tomador del contrato")
    cliente_cedula: str = Field("", description="Cedula de ciudadania o NIT del cliente")
    cliente_direccion: str = Field("", description="Direccion de residencia del cliente")
    cliente_telefono: str = Field("", description="Telefono (celular o fijo) del cliente")
    cliente_correo: str = Field("", description="Correo electronico del cliente")
    destino: str = Field("", description="Destino del viaje")
    confirmacion_reserva: str = Field("", description="Numero o codigo de confirmacion de reserva")

    valor_total: str = Field("", description="Valor total del plan turistico, solo el numero/monto, ej. 8.500.000")
    fecha_limite_pago: str = Field("", description="Fecha limite de pago del plan turistico")
    pagos: list[Pago] = Field(default_factory=list, description="Cronograma de pagos: lista de fecha + valor a pagar en cada abono. Puede haber 1 o varios pagos.")

    pasajeros_adicionales: list[PasajeroAdicional] = Field(
        default_factory=list,
        description="Otros viajeros/beneficiarios adicionales al cliente (nombre + cedula). Puede estar vacia si el cliente viaja solo.",
    )

    programa: str = Field("", description="Nombre del programa o plan turistico reservado")
    fecha_reserva: str = Field("", description="Fecha(s) del viaje / de la reserva")
    hotel: str = Field("", description="Hotel(es) donde se hospedara")
    check_in: str = Field("15:00", description="Hora de check in del hotel. Si no se menciona, usar 15:00")
    check_out: str = Field("12:00", description="Hora de check out del hotel. Si no se menciona, usar 12:00")
    pasajeros_reserva: list[PasajeroReserva] = Field(
        default_factory=list,
        description="Lista de todos los pasajeros que viajan (nombre + documento de identidad), incluyendo al cliente.",
    )
    incluye: str = Field("", description="Que incluye el programa. Texto libre, puede tener varias lineas/items.")
    no_incluye: str = Field("", description="Que NO incluye el programa. Texto libre, puede tener varias lineas/items.")


# (field, etiqueta visible)
REQUIRED_SIMPLE_FIELDS = [
    ("asesor_comercial", "Asesor comercial"),
    ("cliente_nombre", "Nombre del cliente"),
    ("cliente_cedula", "Cedula de ciudadania o NIT del cliente"),
    ("cliente_direccion", "Direccion del cliente"),
    ("cliente_telefono", "Telefono del cliente"),
    ("cliente_correo", "Correo electronico del cliente"),
    ("destino", "Destino del viaje"),
    ("confirmacion_reserva", "Confirmacion de reserva"),
    ("valor_total", "Valor total"),
    ("fecha_limite_pago", "Fecha limite de pago"),
    ("programa", "Programa"),
    ("fecha_reserva", "Fecha de la reserva"),
    ("hotel", "Hotel"),
]


def missing_fields(data: ContratoTurismo) -> list[str]:
    missing: list[str] = []
    for field, label in REQUIRED_SIMPLE_FIELDS:
        if not (getattr(data, field) or "").strip():
            missing.append(label)

    if not data.pagos:
        missing.append("Al menos una fecha y valor de pago")
    else:
        for i, p in enumerate(data.pagos, start=1):
            if not p.fecha.strip() or not p.valor.strip():
                missing.append(f"Pago #{i}: fecha y valor")

    if not data.pasajeros_reserva:
        missing.append("Al menos un pasajero (nombre + documento)")
    else:
        for i, p in enumerate(data.pasajeros_reserva, start=1):
            if not p.nombre.strip() or not p.documento.strip():
                missing.append(f"Pasajero #{i}: nombre y documento")

    return missing


SYSTEM_PROMPT = """Eres un asistente que extrae datos estructurados para generar un contrato de turismo \
de la agencia Apple Travel (Colombia), a partir de un texto pegado libremente por un asesor comercial \
(puede venir en cualquier orden, formato, mayusculas/minusculas, como notas, chat de WhatsApp, o un formulario).

Debes llamar SIEMPRE a la herramienta `extraer_datos_contrato` con los datos que logres identificar en el texto.

Reglas importantes:
- NO inventes datos que no esten en el texto. Si un campo no aparece, dejalo vacio ("" o lista vacia []).
- "valor_total", los "valor" de cada pago, deben ser solo el monto (numeros, puntos/comas), sin el simbolo $ (ya esta impreso en la plantilla).
- Si el texto menciona varios abonos/cuotas/pagos con sus fechas y valores, inclúyelos TODOS en la lista "pagos" (puede haber 1, 2, 3 o mas).
- "pasajeros_reserva" debe incluir a TODOS los que viajan (incluido el cliente titular) con su nombre y documento de identidad, si estan disponibles.
- "pasajeros_adicionales" son las personas distintas al cliente titular que tambien viajan (beneficiarios). Si el cliente viaja solo, dejar la lista vacia.
- check_in y check_out: si no se mencionan, usa los valores por defecto 15:00 y 12:00.
- Normaliza nombres propios a mayusculas/minusculas tipo titulo cuando sea razonable, pero no alteres cedulas, telefonos, correos ni montos.
"""
