from lxml import etree
from utils.adicionar_campo import adicionar_campo

def adicionar_table_field(parent, field_id, idcampo, value):
    """Adiciona um TableField com duas linhas de exemplo."""
    table_field = etree.SubElement(parent, "TableField")
    etree.SubElement(table_field, "ID").text = field_id
    rows = etree.SubElement(table_field, "Rows")
    row1 = etree.SubElement(rows, "Row")
    fields1 = etree.SubElement(row1, "Fields")
    adicionar_campo(fields1, idcampo, value)
    adicionar_campo(fields1, idcampo, value)

def adicionar_table_field(parent, field_id, rows_data):
    """Adiciona um TableField com linhas dinâmicas."""
    table_field = etree.SubElement(parent, "TableField")
    etree.SubElement(table_field, "ID").text = field_id
    rows_element = etree.SubElement(table_field, "Rows")

    for row_data in rows_data:
        create_row(rows_element, row_data)

def create_row(parent, fields_data):
    """Cria um elemento Row com campos."""
    row = etree.SubElement(parent, "Row")
    fields_element = etree.SubElement(row, "Fields")

    for field_id, value in fields_data.items():
        adicionar_campo(fields_element, field_id, value)