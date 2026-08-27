"""
Parser determinista (sin IA / sin API externa) del texto pegado por el asesor.

Soporta DOS formatos, detectados automaticamente:

1) "Hoja de calculo": el asesor pega (con Ctrl+C/Ctrl+V desde Excel/Sheets) la fila de
   su hoja de seguimiento de reservas -- con o sin la fila de encabezados encima -- y
   debajo, en lineas sueltas: los pasajeros ("Nombre - CC 123"), que incluye / no incluye
   el programa, y por ultimo el correo del asesor solo en su propia linea.
   Las columnas de la hoja se identifican por POSICION (ver COL_* abajo), porque la hoja
   siempre tiene el mismo formato interno de la agencia.

2) "Etiquetas": una linea por dato, "Etiqueta: valor" (ver mas abajo). Util para pegar
   los datos a mano sin tener la hoja de calculo a la vista.

Ejemplo formato de etiquetas:
    Asesor: Juan Perez
    Cliente: Maria Gomez
    Cedula: 1020304050
    ...
    Pago: 20 de agosto de 2026 - 2000000
    Pasajero: Maria Gomez - 1020304050
"""

import csv
import io
import re
import unicodedata

# ---------------------------------------------------------------------------
# Formato 1: fila de la hoja de calculo interna (posiciones fijas, 0-indexadas)
# ---------------------------------------------------------------------------
# Ver columnas completas de la hoja "NUMERO SOLICITUD ... FECHA ACUERDO PAGO 4".
# Si algun dia cambia el orden de columnas de esa hoja, solo hay que actualizar
# estos indices.

COL_ASESOR = 5
COL_NUMERO_RESERVA = 10
COL_NOMBRE = 11
COL_DOCUMENTO = 12
COL_TELEFONO = 13
COL_DIRECCION = 14
COL_CIUDAD_DIRECCION = 15
COL_CORREO = 16
COL_DESTINO = 17
COL_FECHA_SALIDA = 18
COL_FECHA_REGRESO = 19
COL_SERVICIO = 20
COL_VALOR_TOTAL = 22
COL_HOTEL = 35
COL_ACUERDOS_PAGO_START = 72  # 4 pares (valor, fecha) desde aqui: 72/73, 74/75, 76/77, 78/79

MIN_TABS_SHEET_ROW = 40  # umbral para reconocer una fila de la hoja (tiene ~79 tabs)

_PASAJERO_RE = re.compile(
    r"^\s*(?P<nombre>.+?)\s*-\s*c\.?\s*c\.?\s*[:.]?\s*(?P<doc>[\d.]{4,})\s*$", re.IGNORECASE
)
_EMAIL_LINE_RE = re.compile(r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$")
_BULLET_RE = re.compile(r"^[\s•\-\*•]+")


def _clean_money(value: str) -> str:
    return value.replace("$", "").strip().strip("-").strip()


def _split_sheet_row(line: str) -> list[str]:
    reader = csv.reader(io.StringIO(line), delimiter="\t", quotechar='"')
    return next(reader, [])


def _col(cells: list[str], idx: int) -> str:
    return cells[idx].strip() if idx < len(cells) else ""


def _parse_sheet_row(cells: list[str]) -> dict:
    data: dict = {
        "asesor_comercial": _col(cells, COL_ASESOR),
        "confirmacion_reserva": _col(cells, COL_NUMERO_RESERVA),
        "cliente_nombre": _col(cells, COL_NOMBRE),
        "cliente_cedula": _col(cells, COL_DOCUMENTO),
        "cliente_telefono": _col(cells, COL_TELEFONO),
        "cliente_correo": _col(cells, COL_CORREO),
        "destino": _col(cells, COL_DESTINO),
        "valor_total": _clean_money(_col(cells, COL_VALOR_TOTAL)),
        "hotel": _col(cells, COL_HOTEL),
    }

    direccion = _col(cells, COL_DIRECCION)
    ciudad_direccion = _col(cells, COL_CIUDAD_DIRECCION)
    if ciudad_direccion and ciudad_direccion.upper() not in direccion.upper():
        direccion = f"{direccion}, {ciudad_direccion}" if direccion else ciudad_direccion
    data["cliente_direccion"] = direccion

    fecha_salida = _col(cells, COL_FECHA_SALIDA)
    fecha_regreso = _col(cells, COL_FECHA_REGRESO)
    if fecha_salida and fecha_regreso:
        data["fecha_reserva"] = f"{fecha_salida} al {fecha_regreso}"
    else:
        data["fecha_reserva"] = fecha_salida or fecha_regreso

    servicio = _col(cells, COL_SERVICIO)
    destino = data["destino"]
    data["programa"] = " - ".join(p for p in [destino, servicio] if p)

    pagos = []
    for i in range(4):
        idx_valor = COL_ACUERDOS_PAGO_START + i * 2
        idx_fecha = idx_valor + 1
        valor = _clean_money(_col(cells, idx_valor))
        fecha = _col(cells, idx_fecha)
        if valor or fecha:
            pagos.append({"fecha": fecha, "valor": valor})
    data["pagos"] = pagos
    data["fecha_limite_pago"] = pagos[-1]["fecha"] if pagos else ""

    return data


def _is_sheet_row(line: str) -> bool:
    return line.count("\t") >= MIN_TABS_SHEET_ROW


def _parse_sheet_format(lines: list[str]) -> dict | None:
    row_idx = next((i for i, l in enumerate(lines) if _is_sheet_row(l)), None)
    if row_idx is None:
        return None

    # si la linea siguiente TAMBIEN parece fila de datos, la primera era el encabezado
    if row_idx + 1 < len(lines) and _is_sheet_row(lines[row_idx + 1]):
        row_idx += 1

    cells = _split_sheet_row(lines[row_idx])
    data = _parse_sheet_row(cells)

    pasajeros: list[dict] = []
    incluye_lines: list[str] = []
    no_incluye_lines: list[str] = []
    asesor_correo = ""

    remaining = [l for l in lines[row_idx + 1 :] if l.strip()]
    i = 0
    # 1) lineas de pasajeros consecutivas al inicio
    while i < len(remaining):
        m = _PASAJERO_RE.match(remaining[i])
        if not m:
            break
        pasajeros.append({"nombre": m.group("nombre").strip(), "documento": m.group("doc").strip()})
        i += 1

    # 2) resto: incluye / no incluye / correo del asesor
    section = "incluye"
    for line in remaining[i:]:
        stripped = line.strip()
        if stripped.lower().rstrip(":") == "no incluye":
            section = "no_incluye"
            continue
        if _EMAIL_LINE_RE.match(stripped):
            asesor_correo = stripped
            continue
        clean = _BULLET_RE.sub("", line).strip()
        if not clean:
            continue
        if section == "incluye":
            incluye_lines.append(clean)
        else:
            no_incluye_lines.append(clean)

    data["pasajeros_reserva"] = pasajeros
    data["pasajeros_adicionales"] = pasajeros
    data["incluye"] = "\n".join(incluye_lines)
    data["no_incluye"] = "\n".join(no_incluye_lines)
    data["asesor_correo"] = asesor_correo
    return data


# ---------------------------------------------------------------------------
# Formato 2: "Etiqueta: valor"
# ---------------------------------------------------------------------------

SCALAR_LABELS = {
    "asesor": "asesor_comercial",
    "asesor comercial": "asesor_comercial",
    "asesora": "asesor_comercial",
    "asesor correo": "asesor_correo",
    "correo asesor": "asesor_correo",
    "correo del asesor": "asesor_correo",
    "email asesor": "asesor_correo",
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


def _parse_labeled_format(text: str) -> dict:
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


# ---------------------------------------------------------------------------
# Punto de entrada: detecta el formato y delega
# ---------------------------------------------------------------------------


def parse_pasted_text(text: str) -> dict:
    lines = text.splitlines()
    sheet_data = _parse_sheet_format(lines)
    if sheet_data is not None:
        return sheet_data
    return _parse_labeled_format(text)
