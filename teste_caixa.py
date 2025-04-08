from flask import Flask, request, Response
import xml.etree.ElementTree as ET
import random


def gerar_valores_peso(tstpeso):
    """Gera valores de peso conforme a lógica especificada"""
    def formatar_numero():
        return str(round(random.uniform(0.5, 500), 2)).replace('.', ',')

    if tstpeso == "0":
        valor = formatar_numero()
        return valor, valor
    else:
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        return peso, pesobalanca


def encaxotar_v2():
    xml_data = request.data
    root = ET.fromstring(xml_data)

    # Detecta se é TABCAIXA1 ou TABCAIXA2
    table_id = root.find('.//TableField/Id').text
    peso_field = 'CX1PESO' if '1' in table_id else 'CX2PESO'
    balanca_field = 'CX1PESOBALANCA' if '1' in table_id else 'CX2PESOBALANCA'
    tstpeso_field = 'TSTPESO1' if '1' in table_id else 'TSTPESO2'

    rows = root.findall('.//TableField/Rows/Row')
    primeira_vazia = True

    for row in rows:
        fields = row.find('Fields')
        peso = fields.find(f"./Field[Id='{peso_field}']/Value")
        balanca = fields.find(f"./Field[Id='{balanca_field}']/Value")
        tstpeso_el = fields.find(f"./Field[Id='{tstpeso_field}']/Value")
        tstpeso_val = tstpeso_el.text.strip() if tstpeso_el is not None else "0"

        if primeira_vazia and ((peso is None or peso.text.strip() == '') or (balanca is None or balanca.text.strip() == '')):
            novo_peso, novo_balanca = gerar_valores_peso(tstpeso_val)

            if peso is not None:
                peso.text = novo_peso
            if balanca is not None:
                balanca.text = novo_balanca

            primeira_vazia = False  # só altera a primeira vazia

    # Construir XML de resposta
    response = ET.Element('ResponseV2', {
        'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
        'xmlns:xsd': "http://www.w3.org/2001/XMLSchema"
    })
    message = ET.SubElement(response, 'MessageV2')
    ET.SubElement(message, 'Text').text = 'Consulta realizada com sucesso.'

    return_value = ET.SubElement(response, 'ReturnValueV2')
    fields = ET.SubElement(return_value, 'Fields')
    table_field = ET.SubElement(fields, 'TableField')
    ET.SubElement(table_field, 'Id').text = table_id

    rows_element = ET.SubElement(table_field, 'Rows')
    for row in rows:
        rows_element.append(row)

    ET.SubElement(return_value, 'ShortText').text = 'Pressione Lixeira para nova consulta'
    ET.SubElement(return_value, 'LongText')
    ET.SubElement(return_value, 'Value').text = '58'

    for row in response.findall('.//Row'):
        if 'IsCurrentRow' in row.attrib:
            del row.attrib['IsCurrentRow']

    xml_str = ET.tostring(response, encoding='utf-16', xml_declaration=True)
    return Response(xml_str, content_type='application/xml; charset=utf-16')