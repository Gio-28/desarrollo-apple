"""
Rellena la plantilla Word (template.docx) con los datos de un ContratoTurismo.

La plantilla se preserva intacta (logos, tablas, las 21 clausulas legales, firmas):
solo se escribe texto en las celdas/parrafos que en el documento original estan en blanco,
mas algunas filas nuevas insertadas en la tabla de confirmacion de reserva (habitacion,
numero de personas, resumen de pagos) que no existian en la plantilla original.
Este modulo conoce la estructura EXACTA de esas celdas (fue inspeccionada a mano), por lo que
si algun dia se edita el template.docx en Word, estos indices deben revisarse.
"""

import copy
import datetime
from io import BytesIO
from pathlib import Path

import docx
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from app.documents.contrato_turismo.schema import ContratoTurismo

TEMPLATE_PATH = Path(__file__).parent / "template.docx"

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

PASAJERO_TAB_STOP = Inches(3.4)


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


def _remove_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._p
    element.getparent().remove(element)


def _replace_everywhere(doc, old_text: str, new_text: str) -> None:
    """Reemplaza el texto de TODOS los <w:t> que coincidan exactamente, en cualquier
    parte del documento (incluye cuadros de texto/formas, que python-docx no expone
    como parrafos normales)."""
    for t in doc.element.body.iter(qn("w:t")):
        if (t.text or "").strip() == old_text:
            t.text = new_text


def _clone_row_after(table: Table, template_row_index: int, after_row_index: int):
    """Clona la fila template_row_index y la inserta despues de after_row_index.
    Devuelve el nuevo elemento <w:tr>."""
    tbl = table._tbl
    trs = tbl.tr_lst
    new_tr = copy.deepcopy(trs[template_row_index])
    trs[after_row_index].addnext(new_tr)
    return new_tr


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
    cc_p = _find_paragraph(doc.paragraphs, "C.C 1152683639")
    if cc_p:
        _append_to_last_run(cc_p, data.cliente_cedula)

    # ancla en "Gerente y R. Legal" (unico en el documento) para no confundir con el
    # encabezado "EL CLIENTE O CONTRATANTE" que aparece mucho antes, en la tabla de datos
    el_cliente_p = _find_paragraph(doc.paragraphs, "Gerente y R. Legal")
    if el_cliente_p:
        for run in el_cliente_p.runs:
            if "EL CLIENTE" in run.text:
                run.text = run.text.replace("EL CLIENTE", data.cliente_nombre)

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

    # Nota: el codigo de reserva vive en un cuadro de texto sobre esta tabla (no es una
    # celda normal); se reemplaza a nivel de documento completo en fill_contract().

    row0 = res_table.rows[0]
    _append_to_last_run(row0.cells[0].paragraphs[0], data.programa)
    _set_cell_text(row0.cells[1], data.fecha_reserva, paragraph_index=1)

    # filas nuevas: HABITACION / N. DE PERSONAS, y resumen de PAGOS -- clonadas de filas
    # existentes de la misma tabla para heredar bordes/estilo, insertadas despues de
    # "RESERVADO A" (fila 1) y antes de "HOTEL / CHECK IN / CHECK OUT" (fila 2 original).
    # ojo con los indices: cada insercion corre las filas siguientes, por eso el
    # template_row_index de cada paso se recalcula segun el estado DESPUES del paso anterior.
    _clone_row_after(res_table, template_row_index=0, after_row_index=1)  # -> HABITACION en indice 2
    _clone_row_after(res_table, template_row_index=4, after_row_index=2)  # -> PAGOS header en indice 3
    _clone_row_after(res_table, template_row_index=0, after_row_index=3)  # -> PAGOS valores en indice 4

    # las filas originales HOTEL/CHECKIN/CHECKOUT y DATOS DE PASAJEROS ahora quedaron
    # corridas 3 posiciones (se insertaron 3 filas nuevas antes de ellas)
    # cells[1] de estas filas se clono del patron "FECHA" (2 parrafos: etiqueta + valor);
    # se usa el primer parrafo para el texto y se ELIMINA el segundo (si no, queda una
    # linea en blanco sobrante en la celda).
    row_habitacion = res_table.rows[2]
    _set_cell_text(row_habitacion.cells[0], f"HABITACIÓN: {data.habitacion}")
    _set_cell_text(row_habitacion.cells[1], f"N° DE PERSONAS: {data.cantidad_personas}", paragraph_index=0)
    if len(row_habitacion.cells[1].paragraphs) > 1:
        _remove_paragraph(row_habitacion.cells[1].paragraphs[1])

    row_pagos_header = res_table.rows[3]
    _set_cell_text(row_pagos_header.cells[0], "PAGOS")

    row_pagos_valores = res_table.rows[4]
    _set_cell_text(row_pagos_valores.cells[0], f"VALOR TOTAL: $ {data.valor_total}")
    _set_cell_text(
        row_pagos_valores.cells[1],
        f"VALOR ABONADO: $ {data.valor_abonado}          VALOR RESTANTE: $ {data.valor_restante}",
        paragraph_index=0,
    )
    if len(row_pagos_valores.cells[1].paragraphs) > 1:
        _remove_paragraph(row_pagos_valores.cells[1].paragraphs[1])

    row2 = res_table.rows[5]
    _append_to_last_run(row2.cells[0].paragraphs[0], data.hotel)
    _set_cell_text(row2.cells[2], f"CHECK IN: {data.check_in}")
    _set_cell_text(row2.cells[3], f"CHECK OUT: {data.check_out}")

    # fila 8: celda unica (combinada) con un parrafo por pasajero "NOMBRE [tab] Doc: XXXX"
    pax_row = res_table.rows[8]
    cell = pax_row.cells[0]
    existing = cell.paragraphs
    last_p = existing[-1] if existing else None
    pasajeros = data.pasajeros_reserva

    while len(existing) < len(pasajeros):
        last_p = _insert_paragraph_after(last_p, "")
        existing = cell.paragraphs

    for i, p in enumerate(existing):
        p.paragraph_format.tab_stops.clear_all()
        p.paragraph_format.tab_stops.add_tab_stop(PASAJERO_TAB_STOP, WD_TAB_ALIGNMENT.LEFT)
        if i < len(pasajeros):
            pax = pasajeros[i]
            _set_paragraph_text(p, f"{pax.nombre}\tDoc: {pax.documento}")
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
    _replace_everywhere(doc, "T-XXX", data.confirmacion_reserva)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
