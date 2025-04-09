from flask import Flask, request, Response
import xml.etree.ElementTree as ET
import random


def gerar_peso():
    return f"{random.uniform(0.5, 500.0):.2f}".replace(".", ",")


def encaxotar():
    xml_data = request.data.decode('utf-8')
    balanca = request.args.get('balanca')  # 'balanca1' ou 'balanca2'

    root = ET.fromstring(xml_data)
    namespace = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }

    table_id = 'TABCAIXA1' if balanca == 'balanca1' else 'TABCAIXA2'
    peso_id = 'CX1PESO' if balanca == 'balanca1' else 'CX2PESO'
    pesobalanca_id = 'CX1PESOBALANCA' if balanca == 'balanca1' else 'CX2PESOBALANCA'

    rows = root.find('.//TableField[ID="{}"]/Rows'.format(table_id))
    if rows is None:
        return Response("Tabela não encontrada", status=400)

    nova_rows = ET.Element("Rows")
    encontrou = False

    for row in rows.findall('Row'):
        nova_row = ET.SubElement(nova_rows, 'Row')
        if row.get('IsCurrentRow') == 'True' and not encontrou:
            nova_row.set('IsCurrentRow', 'True')
            encontrou = True
        elif row.get('IsCurrentRow') == 'True':
            continue  # ignorar qualquer linha marcada como IsCurrentRow depois da primeira

        campos_origem = row.find('Fields')
        campos_novos = ET.SubElement(nova_row, 'Fields')

        for field in campos_origem.findall('Field'):
            novo_field = ET.SubElement(campos_novos, 'Field')
            for tag in field:
                ET.SubElement(novo_field, tag.tag).text = tag.text

            # preencher apenas se for a linha com IsCurrentRow
            if row.get('IsCurrentRow') == 'True':
                id_tag = field.find('ID')
                if id_tag is not None and id_tag.text == peso_id:
                    field.find('Value').text = gerar_peso()
                if id_tag is not None and id_tag.text == pesobalanca_id:
                    field.find('Value').text = gerar_peso()

        if encontrou:
            break  # para de processar após a linha com IsCurrentRow

    # Montar o XML de resposta
    response_root = ET.Element("ResponseV2", {
        'xmlns:xsi': namespace['xsi'],
        'xmlns:xsd': namespace['xsd']
    })

    message = ET.SubElement(response_root, "MessageV2")
    ET.SubElement(message, "Text").text = "Consulta realizada com sucesso."

    return_value = ET.SubElement(response_root, "ReturnValueV2")
    fields = ET.SubElement(return_value, "Fields")

    table_field = ET.SubElement(fields, "TableField")
    ET.SubElement(table_field, "ID").text = table_id
    table_field.append(nova_rows)

    ET.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    ET.SubElement(return_value, "LongText").text = ""
    ET.SubElement(return_value, "Value").text = "58"

    xml_str = ET.tostring(response_root, encoding='utf-16', xml_declaration=True)
    return Response(xml_str, mimetype='application/xml')