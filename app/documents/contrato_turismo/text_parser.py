"""
Parser determinista (sin IA / sin API externa) del texto pegado por el asesor.

Soporta DOS formatos, detectados automaticamente:

1) "Hoja de calculo": el asesor pega (con Ctrl+C/Ctrl+V desde Excel/Sheets) la fila de
   su hoja de seguimiento de reservas -- con o sin la fila de encabezados encima -- y
   debajo, en lineas sueltas: los pasajeros acompañantes ("Nombre - CC 123"), opcionalmente
   la habitacion ("Habitacion: Estandar"), que incluye / no incluye el programa, y
   opcionalmente el itinerario dia a dia (la palabra "Itinerario" sola en su linea marca
   donde empieza esa seccion, que se toma hasta el final del texto).
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

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

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
COL_CANTIDAD_PERSONAS = 21
COL_VALOR_TOTAL = 22
COL_ABONO = 23
COL_DEBE = 24
COL_HOTEL = 35
COL_ACUERDOS_PAGO_START = 72  # 4 pares (valor, fecha) desde aqui: 72/73, 74/75, 76/77, 78/79

MIN_TABS_SHEET_ROW = 40  # umbral para reconocer una fila de la hoja (tiene ~79 tabs)

_PASAJERO_RE = re.compile(
    r"^\s*(?P<nombre>.+?)\s*-\s*c\.?\s*c\.?\s*[:.]?\s*(?P<doc>[\d.]{4,})\s*$", re.IGNORECASE
)
_HABITACION_RE = re.compile(r"^\s*habitaci[oó]n\s*:?\s*(?P<valor>.+)$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[\s•\-\*•]+")
_DDMMYYYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _clean_money(value: str) -> str:
    return value.replace("$", "").strip().strip("-").strip()


def _split_sheet_row(line: str) -> list[str]:
    reader = csv.reader(io.StringIO(line), delimiter="\t", quotechar='"')
    return next(reader, [])


def _col(cells: list[str], idx: int) -> str:
    return cells[idx].strip() if idx < len(cells) else ""


def _format_fecha_es(day: int, month: int, year: int) -> str:
    return f"{day} de {MESES_ES[month - 1]} de {year}"


def format_fecha_reserva(raw: str) -> str:
    """Convierte 'DD/MM/AAAA al DD/MM/AAAA' (o una sola fecha) a texto en español.
    Si el formato no es reconocido, devuelve el texto tal cual."""
    raw = raw.strip()
    if not raw:
        return raw

    if " al " in raw:
        left, right = raw.split(" al ", 1)
        m1 = _DDMMYYYY_RE.match(left.strip())
        m2 = _DDMMYYYY_RE.match(right.strip())
        if m1 and m2:
            d1, mo1, y1 = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
            d2, mo2, y2 = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            if (mo1, y1) == (mo2, y2):
                return f"{d1} al {d2} de {MESES_ES[mo1 - 1]} de {y1}"
            if y1 == y2:
                return f"{d1} de {MESES_ES[mo1 - 1]} al {d2} de {MESES_ES[mo2 - 1]} de {y1}"
            return f"{_format_fecha_es(d1, mo1, y1)} al {_format_fecha_es(d2, mo2, y2)}"
        return raw

    m = _DDMMYYYY_RE.match(raw)
    if m:
        return _format_fecha_es(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return raw


def _parse_sheet_row(cells: list[str]) -> dict:
    data: dict = {
        "asesor_comercial": _col(cells, COL_ASESOR),
        "confirmacion_reserva": _col(cells, COL_NUMERO_RESERVA),
        "cliente_nombre": _col(cells, COL_NOMBRE),
        "cliente_cedula": _col(cells, COL_DOCUMENTO),
        "cliente_telefono": _col(cells, COL_TELEFONO),
        "cliente_correo": _col(cells, COL_CORREO),
        "destino": _col(cells, COL_DESTINO),
        "programa": _col(cells, COL_DESTINO),
        "valor_total": _clean_money(_col(cells, COL_VALOR_TOTAL)),
        "valor_abonado": _clean_money(_col(cells, COL_ABONO)),
        "valor_restante": _clean_money(_col(cells, COL_DEBE)),
        "cantidad_personas": _col(cells, COL_CANTIDAD_PERSONAS),
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
        raw_fecha = f"{fecha_salida} al {fecha_regreso}"
    else:
        raw_fecha = fecha_salida or fecha_regreso
    data["fecha_reserva"] = format_fecha_reserva(raw_fecha)

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

    acompanantes: list[dict] = []
    incluye_lines: list[str] = []
    no_incluye_lines: list[str] = []
    itinerario_lines: list[str] = []
    habitacion = ""

    tail_lines = lines[row_idx + 1 :]

    # 1) lineas de pasajeros acompañantes, consecutivas al inicio (se ignoran lineas vacias
    # de por medio, pero preservamos el resto de tail_lines intacto para el itinerario)
    i = 0
    while i < len(tail_lines):
        stripped = tail_lines[i].strip()
        if not stripped:
            i += 1
            continue
        m = _PASAJERO_RE.match(stripped)
        if not m:
            break
        acompanantes.append({"nombre": m.group("nombre").strip(), "doc": m.group("doc").strip()})
        i += 1

    # 2) resto: habitacion / incluye / no incluye / itinerario. Las lineas en blanco se
    # descartan en incluye/no_incluye (cada item es una linea), pero se PRESERVAN dentro
    # del itinerario para mantener los saltos de parrafo entre dias.
    section = "incluye"
    for line in tail_lines[i:]:
        stripped = line.strip()
        if not stripped:
            if section == "itinerario":
                itinerario_lines.append("")
            continue

        lowered = stripped.lower().rstrip(":")
        if lowered == "no incluye":
            section = "no_incluye"
            continue
        if lowered == "itinerario":
            section = "itinerario"
            continue
        if section != "itinerario":
            m = _HABITACION_RE.match(stripped)
            if m:
                habitacion = m.group("valor").strip()
                continue

        if section == "itinerario":
            itinerario_lines.append(_BULLET_RE.sub("", line).rstrip())
            continue

        clean = _BULLET_RE.sub("", line).strip()
        if section == "incluye":
            incluye_lines.append(clean)
        else:
            no_incluye_lines.append(clean)

    # el titular (cliente) siempre viaja + los acompañantes = todos los pasajeros de la reserva
    data["pasajeros_reserva"] = [
        {"nombre": data["cliente_nombre"], "documento": data["cliente_cedula"]},
        *[{"nombre": a["nombre"], "documento": a["doc"]} for a in acompanantes],
    ]
    # los "adicionales" (clausula 16) son solo los acompañantes, no el titular
    data["pasajeros_adicionales"] = [{"nombre": a["nombre"], "cedula": a["doc"]} for a in acompanantes]
    data["habitacion"] = habitacion
    data["incluye"] = "\n".join(incluye_lines)
    data["no_incluye"] = "\n".join(no_incluye_lines)
    data["itinerario"] = "\n".join(itinerario_lines).strip("\n")
    return data


# ---------------------------------------------------------------------------
# Formato 2: "Etiqueta: valor"
# ---------------------------------------------------------------------------

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
    "valor abonado": "valor_abonado",
    "abonado": "valor_abonado",
    "abono": "valor_abonado",
    "valor restante": "valor_restante",
    "restante": "valor_restante",
    "saldo": "valor_restante",
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
    "habitacion": "habitacion",
    "tipo de habitacion": "habitacion",
    "cantidad de personas": "cantidad_personas",
    "numero de personas": "cantidad_personas",
    "personas": "cantidad_personas",
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
    "itinerario": "itinerario",
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
    itinerario_lines: list[str] = []
    in_itinerario = False

    for raw_line in text.splitlines():
        # una vez que empieza "Itinerario:", el resto del texto se toma completo
        # (dia a dia, con saltos de linea), sin exigir "Etiqueta: valor" por linea.
        if in_itinerario:
            itinerario_lines.append(raw_line.rstrip())
            continue

        match = _LINE_RE.match(raw_line)
        if not match:
            continue
        label_raw, value = match.groups()
        label = _normalize_label(label_raw)
        if not value:
            continue

        if label in SCALAR_LABELS:
            field = SCALAR_LABELS[label]
            if field == "fecha_reserva":
                value = format_fecha_reserva(value)
            scalars[field] = value
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
            elif kind == "itinerario":
                in_itinerario = True
                itinerario_lines.append(value)

    data = dict(scalars)
    data["pagos"] = pagos
    data["pasajeros_reserva"] = pasajeros
    data["pasajeros_adicionales"] = adicionales
    if incluye_lines:
        data["incluye"] = "\n".join(incluye_lines)
    if no_incluye_lines:
        data["no_incluye"] = "\n".join(no_incluye_lines)
    if itinerario_lines:
        data["itinerario"] = "\n".join(itinerario_lines).strip("\n")
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
