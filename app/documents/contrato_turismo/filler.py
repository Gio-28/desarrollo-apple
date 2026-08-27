"""
Rellena la plantilla Word (template.docx) con los datos de un ContratoTurismo.

La plantilla se preserva intacta (logos, tablas, las 21 clausulas legales, firmas):
solo se escribe texto en las celdas/parrafos que en el documento original estan en blanco.
Este modulo conoce la estructura EXACTA de esas celdas (fue inspeccionada a mano), por lo que
si algun dia se edita el template.docx en Word, estos indices deben revisarse.
"""

import copy
import datetime
from io import BytesIO
from pathlib import Path

import docx
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from app.documents.contrato_turismo.schema import ContratoTurismo

TEMPLATE_PATH = Path(__file__).parent / "template.docx"

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# --------------------------------------------------------------------------
# Helpers genericos de edicion de un .docx ya cargado
# --------------------------------------------------------------------------

def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = text
        for r in paragraph.runs[1:]:
            r.text = ""
    else:
        paragraph.add_run(text)


def _set_cell_text(cell: _Cell, value: str, paragraph_index: int = 0) -> None:
    paragraphs = cell.paragraphs
    if paragraph_index >= len(paragraphs):
        return
    _set_paragraph_text(paragraphs[paragraph_index], value)


def _append_to_last_run(paragraph: Paragraph, extra_text: str) -> None:
    if paragraph.runs:
        paragraph.runs[-1].text = (paragraph.runs[-1].text or "") + extra_text
    else:
        paragraph.add_run(extra_text)


def _insert_paragraph_after(paragraph: Paragraph, text: str = "") -> Paragraph:
    new_p_elm = copy.deepcopy(paragraph._p)
    paragraph._p.addnext(new_p_elm)
    new_paragraph = Paragraph(new_p_elm, paragraph._parent)
    _set_paragraph_text(new_paragraph, text)
    return new_paragraph


def _fill_multiline_cell(cell: _Cell, text: str) -> None:
    lines = [line.strip() for line in text.split("\n") if line.strip()] or [""]
    existing = cell.paragraphs
    last_p = existing[-1]
    while len(existing) < len(lines):
        last_p = _insert_paragraph_after(last_p, "")
        existing = cell.paragraphs
    for i, p in enumerate(existing):
        _set_paragraph_text(p, lines[i] if i < len(lines) else "")


def _find_paragraph(paragraphs: list[Paragraph], contains: str) -> Paragraph | None:
    for p in paragraphs:
        if contains in p.text:
            return p
    return None


# --------------------------------------------------------------------------
# Bloques especificos del contrato
# --------------------------------------------------------------------------

def _fill_empresa_cliente_tables(tables: list[Table], data: ContratoTurismo) -> None:
    empresa_table, cliente_table = tables[0], tables[1]

    # EMPRESA -> fila 7 (ASESOR COMERCIAL) columna valor
    _set_cell_text(empresa_table.rows[7].cells[1], data.asesor_comercial)

    # CLIENTE -> filas 0..6
    _set_cell_text(cliente_table.rows[0].cells[1], data.cliente_nombre)
    _set_cell_text(cliente_table.rows[1].cells[1], data.cliente_cedula)
    _set_cell_text(cliente_table.rows[2].cells[1], data.cliente_direccion)
    _set_cell_text(cliente_table.rows[3].cells[1], data.cliente_telefono)
    _set_cell_text(cliente_table.rows[4].cells[1], data.cliente_correo)
    _set_cell_text(cliente_table.rows[5].cells[1], data.destino)
    _set_cell_text(cliente_table.rows[6].cells[1], data.confirmacion_reserva)


def _fill_payment_table(tables: list[Table], data: ContratoTurismo) -> None:
    pay_table = tables[2]

    # fila 0: VALOR TOTAL (parrafo 2) / FECHA LIMITE DE PAGO (parrafo 2, celda combinada col1-2)
    _set_cell_text(pay_table.rows[0].cells[0], f"$ {data.valor_total}", paragraph_index=1)
    _set_cell_text(pay_table.rows[0].cells[1], data.fecha_limite_pago, paragraph_index=1)

    # filas 2 y 3 son la plantilla de cada abono (fecha | $valor). Se clona segun # de pagos.
    tbl = pay_table._tbl
    trs = tbl.tr_lst
    template_tr = copy.deepcopy(trs[2])
    tbl.remove(trs[2])
    tbl.remove(trs[3])

    for pago in data.pagos:
        new_tr = copy.deepcopy(template_tr)
        tbl.append(new_tr)

    # ahora que las filas estan en el arbol, usamos la API normal de python-docx para escribir texto
    for i, pago in enumerate(data.pagos):
        row = pay_table.rows[2 + i]
        _set_cell_text(row.cells[0], pago.fecha)
        _set_cell_text(row.cells[1], f"$ {pago.valor}")


def _fill_beneficiarios_adicionales(doc, data: ContratoTurismo) -> None:
    blanks = [p for p in doc.paragraphs if p.text and set(p.text.strip()) == {"_"}]
    if not blanks:
        return

    pasajeros = data.pasajeros_adicionales
    for i, p in enumerate(blanks):
        if i < len(pasajeros):
            b = pasajeros[i]
            _set_paragraph_text(p, f"{b.nombre}          C.C. {b.cedula}")

    last_p = blanks[-1]
    for i in range(len(blanks), len(pasajeros)):
        b = pasajeros[i]
        last_p = _insert_paragraph_after(last_p, f"{b.nombre}          C.C. {b.cedula}")


def _fill_signature_block(doc, data: ContratoTurismo) -> None:
    empresa_rep_p = _find_paragraph(doc.paragraphs, "YERICA LONDOÑO AGUIRRE")
    if empresa_rep_p:
        _append_to_last_run(empresa_rep_p, data.cliente_nombre)

    cc_p = _find_paragraph(doc.paragraphs, "C.C 1152683639")
    if cc_p:
        _append_to_last_run(cc_p, data.cliente_cedula)
        # tag de texto que Dropbox Sign convierte en el campo de firma del cliente
        _insert_paragraph_after(cc_p, "[sig|req|signer1]")

    fecha_p = _find_paragraph(doc.paragraphs, "Una vez leído en su integridad")
    if fecha_p and len(fecha_p.runs) >= 6:
        hoy = datetime.date.today()
        fecha_p.runs[1].text = f" {hoy.day}"
        fecha_p.runs[2].text = " de "
        fecha_p.runs[3].text = MESES_ES[hoy.month - 1]
        fecha_p.runs[4].text = " de "
        fecha_p.runs[5].text = str(hoy.year)


def _fill_reservation_table(tables: list[Table], data: ContratoTurismo) -> None:
    res_table = tables[4]

    row0 = res_table.rows[0]
    _append_to_last_run(row0.cells[0].paragraphs[0], data.programa)
    _set_cell_text(row0.cells[1], data.fecha_reserva, paragraph_index=1)

    row2 = res_table.rows[2]
    _append_to_last_run(row2.cells[0].paragraphs[0], data.hotel)
    _set_cell_text(row2.cells[2], f"CHECK IN: {data.check_in}")
    _set_cell_text(row2.cells[3], f"CHECK OUT: {data.check_out}")

    # fila 5: celda unica (combinada) con un parrafo por pasajero "NOMBRE   Doc: XXXX"
    pax_row = res_table.rows[5]
    cell = pax_row.cells[0]
    existing = cell.paragraphs
    last_p = existing[-1] if existing else None
    pasajeros = data.pasajeros_reserva

    while len(existing) < len(pasajeros):
        last_p = _insert_paragraph_after(last_p, "")
        existing = cell.paragraphs

    for i, p in enumerate(existing):
        if i < len(pasajeros):
            pax = pasajeros[i]
            _set_paragraph_text(p, f"{pax.nombre}          Doc: {pax.documento}")
        else:
            _set_paragraph_text(p, "")


def _fill_incluye_no_incluye(tables: list[Table], data: ContratoTurismo) -> None:
    incluye_table, no_incluye_table = tables[5], tables[6]
    _fill_multiline_cell(incluye_table.rows[1].cells[0], data.incluye)
    _fill_multiline_cell(no_incluye_table.rows[1].cells[0], data.no_incluye)


# --------------------------------------------------------------------------
# Punto de entrada
# --------------------------------------------------------------------------

def fill_contract(data: ContratoTurismo) -> bytes:
    doc = docx.Document(str(TEMPLATE_PATH))
    tables = doc.tables

    _fill_empresa_cliente_tables(tables, data)
    _fill_payment_table(tables, data)
    _fill_beneficiarios_adicionales(doc, data)
    _fill_signature_block(doc, data)
    _fill_reservation_table(tables, data)
    _fill_incluye_no_incluye(tables, data)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
