# utils/gerar_erro.py
from lxml import etree
from flask import Response

def gerar_erro_xml(mensagem, short_text, root_element="ResponseV2", namespaces=None):
    if namespaces is None:
        namespaces = {
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xsd': 'http://www.w3.org/2001/XMLSchema'
        }

    response = etree.Element(root_element, nsmap=namespaces)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")