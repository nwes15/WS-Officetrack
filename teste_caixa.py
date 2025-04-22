from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---
def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    if not xml_bytes: return "0"
    try:
        parser = etree.XMLParser(recover=True); tree = etree.parse(BytesIO(xml_bytes), parser); root = tree.getroot()
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"; tabela_elements = root.xpath(xpath_tabela)
        if not tabela_elements: return "0"
        tabela_element = tabela_elements[0]; linha_alvo = None
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows: linha_alvo = current_rows[0]
        else:
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list: linha_alvo = primeira_linha_list[0]
        if linha_alvo is None: return "0"
        xpath_tstpeso = f".//Field[Id='{tstpeso_id_alvo}']/Value"; tstpeso_elements = linha_alvo.xpath(xpath_tstpeso)
        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None: value_text = value_text.strip(); return value_text if value_text in ["0", "1"] else "0"
        return "0"
    except Exception: logging.exception("Erro ao extrair TSTPESO"); return "0"

def gerar_valores_peso(tstpeso_valor, balanca):
    def formatar_numero(): return "{:.2f}".format(random.uniform(0.5, 500)).replace('.', ',')

    if tstpeso_valor == "0":
        valor = formatar_numero()
        return valor, valor
    else:
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca:
            pesobalanca = formatar_numero()
        return peso, pesobalanca

# --- Função de Resposta com lxml ---
def gerar_resposta_xml(xml_data_bytes, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera ResponseV2 usando lxml, preservando a estrutura original do XML de entrada,
    atualizando apenas a linha marcada como IsCurrentRow="True" na tabela correta e
    organizando a resposta no formato correto (campos fixos seguidos pela tabela).
    """
    logging.debug(f"Gerando resposta XML com lxml para balanca '{balanca_id}'")

    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_data_bytes), parser)
        root_form = tree.getroot()

        # Determina IDs
        tabela_id_resp = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_id_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_id_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

        # Localiza a tabela alvo
        xpath_tabela = f".//TableField[Id='{tabela_id_resp}']"
        tabela_elements = root_form.xpath(xpath_tabela)

        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_resp}' não encontrada no XML de entrada.")
            return gerar_erro_xml_padrao(f"Tabela '{tabela_id_resp}' não encontrada.", "Erro XML")

        tabela_element = tabela_elements[0]

        # Itera sobre as linhas da tabela
        for row in tabela_element.xpath("./Rows/Row"):
            is_current_row = row.get("IsCurrentRow") == "True"

            if is_current_row:
                logging.debug(f"Atualizando linha com IsCurrentRow='True' na tabela '{tabela_id_resp}'.")

                # Atualiza os campos com os novos valores
                for field in row.xpath("./Fields/Field"):
                    field_id = field.find("Id").text if field.find("Id") is not None else None

                    if field_id == tstpeso_id:
                        value_element = field.find("Value")
                        if value_element is None:
                            value_element = etree.SubElement(field, "Value")
                        value_element.text = tstpeso_valor_usado
                        override_data_element = field.find("OverrideData")
                        if override_data_element is None:
                            override_data_element = etree.SubElement(field, "OverrideData")
                        override_data_element.text = "1"
                    elif field_id == peso_id_resp:
                        value_element = field.find("Value")
                        if value_element is None:
                            value_element = etree.SubElement(field, "Value")
                        value_element.text = peso_novo
                        override_data_element = field.find("OverrideData")
                        if override_data_element is None:
                            override_data_element = etree.SubElement(field, "OverrideData")
                        override_data_element.text = "1"

                    elif field_id == pesobalanca_id_resp:
                        value_element = field.find("Value")
                        if value_element is None:
                            value_element = etree.SubElement(field, "Value")
                        value_element.text = pesobalanca_novo
                        override_data_element = field.find("OverrideData")
                        if override_data_element is None:
                            override_data_element = etree.SubElement(field, "OverrideData")
                        override_data_element.text = "1"
                    elif field_id == "WS":
                        value_element = field.find("Value")
                        if value_element is None:
                            value_element = etree.SubElement(field, "Value")
                        value_element.text = "Pressione Lixeira para nova consulta"
                        override_data_element = field.find("OverrideData")
                        if override_data_element is None:
                            override_data_element = etree.SubElement(field, "OverrideData")
                        override_data_element.text = "1"
                    else:
                        override_data_element = field.find("OverrideData")
                        if override_data_element is None:
                            override_data_element = etree.SubElement(field, "OverrideData")
                        override_data_element.text = "0"

            else:  # Not current row
                # Certifica-se de que OverrideData esteja definido como 0 para as outras linhas
                for field in row.xpath("./Fields/Field"):
                    override_data_element = field.find("OverrideData")
                    if override_data_element is None:
                        override_data_element = etree.SubElement(field, "OverrideData")
                    override_data_element.text = "0"

        # Cria o novo XML no formato <ResponseV2>
        nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        root_response = etree.Element("ResponseV2", nsmap=nsmap)
        message_v2 = etree.SubElement(root_response, "MessageV2")
        text_element = etree.SubElement(message_v2, "Text")
        text_element.text = "Consulta realizada com sucesso."

        return_value_v2 = etree.SubElement(root_response, "ReturnValueV2")
        fields_element = etree.SubElement(return_value_v2, "Fields")

        # Adiciona os campos fixos *antes* da tabela
        # Adapte os XPaths para extrair os valores corretos do XML de entrada
        def add_field(parent, id_text, xpath):
            field_element = etree.SubElement(parent, "Field")
            id_element = etree.SubElement(field_element, "ID")
            id_element.text = id_text
            override_element = etree.SubElement(field_element, "OverrideData")
            override_element.text = "0"
            value_element = etree.SubElement(field_element, "Value")
            element = root_form.find(xpath)
            value_element.text = element.text if element is not None else ""

        add_field(fields_element, "StationID", "./Employee/EmployeeNumber")  # Adapte o XPath
        add_field(fields_element, "CN", "./Guid")  # Adapte o XPath
        add_field(fields_element, "VC", "./Id")  # Adapte o XPath
        add_field(fields_element, "VC2", "./Employee/EmployeeNumber")  # Adapte o XPath
        add_field(fields_element, "Date", "./Guid")  # Adapte o XPath

        # Adiciona a tabela modificada *depois* dos campos fixos
        fields_element.append(tabela_element)

        short_text_element = etree.SubElement(return_value_v2, "ShortText")
        short_text_element.text = "Pressione Lixeira para nova consulta"
        long_text_element = etree.SubElement(return_value_v2, "LongText")
        value_element_rv = etree.SubElement(return_value_v2, "Value")
        value_element_rv.text = "17"

        # Garante a declaração XML
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'

        # Transforma a árvore XML em uma string, com indentação e quebras de linha
        xml_string = etree.tostring(root_response, encoding="utf-16", xml_declaration=False, pretty_print=True).decode("utf-16")

        # Codifica a string final para UTF-16
        xml_final = xml_declaration + xml_string

        logging.debug("XML de Resposta (lxml, UTF-16):\n%s", xml_final)

        # Cria a resposta Flask com o tipo de conteúdo e codificação corretos
        response = Response(xml_final.encode("utf-16"), content_type="application/xml; charset=utf-16")
        return response

    except etree.XMLSyntaxError as e:
        logging.exception("Erro de sintaxe XML")
        return gerar_erro_xml_padrao(f"Erro de sintaxe XML: {str(e)}", "Erro XML")
    except Exception as e:
        logging.exception("Erro ao gerar XML com lxml")
        return gerar_erro_xml_padrao(f"Erro ao processar XML: {str(e)}", "Erro XML")


def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    # 1. Obtenção Robusta do XML
    content_type = request.headers.get("Content-Type", "").lower(); xml_data_str = None; xml_data_bytes = None
    # ... (código de obtenção mantido) ...
    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form: xml_data_str = request.form.get(name); break
        if not xml_data_str and request.form: first_key = next(iter(request.form)); xml_data_str = request.form.get(first_key)
        if xml_data_str: logging.info("XML obtido de request.form.")
    if not xml_data_bytes and xml_data_str:
        try: xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e: return gerar_erro_xml(f"Erro codificando form data: {e}", "Erro Encoding", 500)
    if not xml_data_bytes: return gerar_erro_xml("XML não encontrado.", "Erro Input", 400)

    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair TSTPESO (da linha 'atual')
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído da linha 'atual': '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML usando lxml e preservando o XML original
        response = gerar_resposta_xml(
            xml_data_bytes=xml_data_bytes,
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )
        return response

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)