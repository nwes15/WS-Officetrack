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