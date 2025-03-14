# utils/adicionar_campo.py
from lxml import etree

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML."""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value