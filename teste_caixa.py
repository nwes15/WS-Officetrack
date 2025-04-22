from flask import Flask, request, Response
from utils.gerar_erro import gerar_erro_xml
from lxml import etree
import random
import logging
from io import BytesIO

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    if not xml_bytes: return "0"
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"
        tabela_elements = root.xpath(xpath_tabela)
        if not tabela_elements: return "0"

        tabela_element = tabela_elements[0]
        linha_alvo = None
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")

        if current_rows:
            linha_alvo = current_rows[0]
        else:
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list:
                linha_alvo = primeira_linha_list[0]

        if linha_alvo is None: return "0"

        xpath_tstpeso = f".//Field[Id='{tstpeso_id_alvo}']/Value"
        tstpeso_elements = linha_alvo.xpath(xpath_tstpeso)

        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None:
                value_text = value_text.strip()
                return value_text if value_text in ["0", "1"] else "0"

        return "0"
    except Exception as e:
        logging.exception(f"Erro ao extrair TSTPESO: {e}")
        return "0"

def gerar_valores_peso(tstpeso_valor, balanca_id):
    def formatar_numero():
        return "{:.2f}".format(random.uniform(0.5, 500)).replace('.', ',')

    if tstpeso_valor == "0":
        valor = formatar_numero()
        return valor, valor
    else:
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca:
            pesobalanca = formatar_numero()
        return peso, pesobalanca

def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    content_type = request.headers.get("Content-Type", "").lower()
    xml_data_str = None
    xml_data_bytes = None

    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form:
                xml_data_str = request.form.get(name)
                break
        if not xml_data_str and request.form:
            first_key = next(iter(request.form))
            xml_data_str = request.form.get(first_key)
        if xml_data_str:
            logging.info("XML obtido de request.form.")

    if not xml_data_str and request.data:
        try:
            xml_data_bytes = request.data
            xml_data_str = xml_data_bytes.decode('utf-8')
            logging.info("XML obtido de request.data (UTF-8).")
        except UnicodeDecodeError:
            try:
                xml_data_str = request.data.decode('latin-1')
                xml_data_bytes = request.data
                logging.info("XML obtido de request.data (Latin-1).")
            except UnicodeDecodeError:
                return gerar_erro_xml("Encoding inválido.", "Erro Encoding", 400)

    if not xml_data_bytes and xml_data_str:
        try:
            xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e:
            return gerar_erro_xml(f"Erro codificando form data: {e}", "Erro Encoding", 500)

    if not xml_data_bytes:
        return gerar_erro_xml("XML não encontrado.", "Erro Input", 400)

    try:
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]:
            return gerar_erro_xml("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # Preparar para adicionar nova linha
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_data_bytes), parser)
        root = tree.getroot()
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        xpath_tabela = f".//TableField[Id='{tabela_id_a_usar}']"
        tabela_elements = root.xpath(xpath_tabela)

        if not tabela_elements:
            return gerar_erro_xml(f"Tabela com ID {tabela_id_a_usar} não encontrada.", "Erro XML", 400)
        tabela_element = tabela_elements[0]

        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tstpeso_valor = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor, balanca)
        override_data_value = "1"  # Valor padrão para OverrideData

        # Criar nova linha
        new_row = etree.Element("Row")
        new_row.set("IsCurrentRow", "True")
        fields = etree.SubElement(new_row, "Fields")

        # Criar campos da nova linha
        def add_field(parent, id, value, override_data="1"): #overide como 1 default
            field = etree.SubElement(parent, "Field")
            field_id = etree.SubElement(field, "ID")
            field_id.text = str(id)  # Garantir que é string

            field_override = etree.SubElement(field, "OverrideData") #adicionado tag overideData
            field_override.text = str(override_data)   #garantir que é string

            field_value = etree.SubElement(field, "Value")
            field_value.text = str(value)  # Garantir que é string
            return field #retornar o field

        add_field(fields, tstpeso_id_a_usar, tstpeso_valor, override_data_value) #adiciona os fields a linha
        add_field(fields, "CX1PESO" if balanca == "balanca1" else "CX2PESO", peso_novo, override_data_value)
        add_field(fields, "CX1PESOBALANCA" if balanca == "balanca1" else "CX2PESOBALANCA", pesobalanca_novo, override_data_value)

        # Adicionar a nova linha à tabela
        tabela_element.find("Rows").append(new_row)

        # Gerar XML de resposta
        response_xml = etree.tostring(root, encoding="utf-16", xml_declaration=True).decode("utf-16")
        return Response(response_xml.encode("utf-16le"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.exception(f"Erro GERAL fatal na rota /teste_caixa: {e}")
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)