"""
Parser determinista (sin IA / sin API externa) del texto pegado por el asesor.

Formato esperado: una linea por dato, "Etiqueta: valor". El orden no importa.
Las etiquetas que representan listas (Pago, Pasajero, Adicional, Incluye, No incluye)
pueden repetirse en varias lineas, una por cada elemento.

Ejemplo:
    Asesor: Juan Perez
    Cliente: Maria Gomez
    Cedula: 1020304050
    ...
    Pago: 20 de agosto de 2026 - 2000000
    Pago: 15 de septiembre de 2026 - 6500000
    Pasajero: Maria Gomez - 1020304050
    Pasajero: Carlos Gomez - 1020304051
"""

import re
import unicodedata

# etiqueta normalizada -> nombre de campo simple, o marcador de lista
SCALAR_LABELS = {
    "asesor": "asesor_comercial",
    "asesor comercial": "asesor_comercial",
    "asesora": "asesor_comercial",
    "cliente": "cliente_nombre",
    "nombre": "cliente_nombre",
    "nombre cliente": "cliente_nombre",
    "nombre del cliente": "cliente_nombre",
    "cedula": "cliente_cedula",
    "cedula cliente": "cliente_cedula",
    "cc": "cliente_cedula",
    "nit": "cliente_cedula",
    "documento": "cliente_cedula",
    "documento cliente": "cliente_cedula",
    "direccion": "cliente_direccion",
    "telefono": "cliente_telefono",
    "celular": "cliente_telefono",
    "tel": "cliente_telefono",
    "correo": "cliente_correo",
    "correo electronico": "cliente_correo",
    "email": "cliente_correo",
    "destino": "destino",
    "confirmacion": "confirmacion_reserva",
    "confirmacion reserva": "confirmacion_reserva",
    "confirmacion de reserva": "confirmacion_reserva",
    "reserva": "confirmacion_reserva",
    "valor total": "valor_total",
    "valor": "valor_total",
    "total": "valor_total",
    "fecha limite pago": "fecha_limite_pago",
    "fecha limite de pago": "fecha_limite_pago",
    "fecha limite": "fecha_limite_pago",
    "limite pago": "fecha_limite_pago",
    "programa": "programa",
    "plan": "programa",
    "fecha reserva": "fecha_reserva",
    "fecha de la reserva": "fecha_reserva",
    "fecha del viaje": "fecha_reserva",
    "fecha viaje": "fecha_reserva",
    "fechas": "fecha_reserva",
    "hotel": "hotel",
    "check in": "check_in",
    "checkin": "check_in",
    "check out": "check_out",
    "checkout": "check_out",
}

LIST_LABELS = {
    "pago": "pagos",
    "abono": "pagos",
    "adicional": "adicionales",
    "beneficiario": "adicionales",
    "viajero adicional": "adicionales",
    "pasajero": "pasajeros",
    "viajero": "pasajeros",
    "incluye": "incluye",
    "no incluye": "no_incluye",
}

_LINE_RE = re.compile(r"^\s*([^:]{2,40}?)\s*:\s*(.+?)\s*$")


def _normalize_label(label: str) -> str:
    label = label.strip().lower()
    label = unicodedata.normalize("NFKD", label)
    label = "".join(c for c in label if not unicodedata.combining(c))
    label = re.sub(r"\s+", " ", label)
    return label


def _split_pair(value: str) -> tuple[str, str]:
    """Divide 'A - B' usando el ULTIMO guion rodeado de espacios como separador."""
    parts = re.split(r"\s-\s", value)
    if len(parts) >= 2:
        return " - ".join(parts[:-1]).strip(), parts[-1].strip()
    return value.strip(), ""


def parse_pasted_text(text: str) -> dict:
    scalars: dict[str, str] = {}
    pagos: list[dict] = []
    pasajeros: list[dict] = []
    adicionales: list[dict] = []
    incluye_lines: list[str] = []
    no_incluye_lines: list[str] = []

    for raw_line in text.splitlines():
        match = _LINE_RE.match(raw_line)
        if not match:
            continue
        label_raw, value = match.groups()
        label = _normalize_label(label_raw)
        if not value:
            continue

        if label in SCALAR_LABELS:
            scalars[SCALAR_LABELS[label]] = value
            continue

        if label in LIST_LABELS:
            kind = LIST_LABELS[label]
            if kind == "pagos":
                fecha, valor = _split_pair(value)
                pagos.append({"fecha": fecha, "valor": valor})
            elif kind == "pasajeros":
                nombre, doc = _split_pair(value)
                pasajeros.append({"nombre": nombre, "documento": doc})
            elif kind == "adicionales":
                nombre, cedula = _split_pair(value)
                adicionales.append({"nombre": nombre, "cedula": cedula})
            elif kind == "incluye":
                incluye_lines.append(value)
            elif kind == "no_incluye":
                no_incluye_lines.append(value)

    data = dict(scalars)
    data["pagos"] = pagos
    data["pasajeros_reserva"] = pasajeros
    data["pasajeros_adicionales"] = adicionales
    if incluye_lines:
        data["incluye"] = "\n".join(incluye_lines)
    if no_incluye_lines:
        data["no_incluye"] = "\n".join(no_incluye_lines)
    return data
