from flask import Flask, request, Response
from utils.gerar_erro import gerar_erro_xml
from lxml import etree
import random
import logging
from io import BytesIO
import copy

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

def gerar_valores_peso(tstpeso_valor, balanca_id):
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
    Gera ResponseV2 usando lxml, preservando a estrutura original do XML de entrada e
    atualizando apenas a linha marcada como IsCurrentRow="True" na tabela correta.
    """
    logging.debug(f"Gerando resposta XML com lxml para balanca '{balanca_id}'")

    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_data_bytes), parser)
        root = tree.getroot()

        # Determina IDs
        tabela_id_resp = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_id_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_id_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

        # Localiza a tabela alvo
        xpath_tabela = f".//TableField[Id='{tabela_id_resp}']"
        tabela_elements = root.xpath(xpath_tabela)

        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_resp}' não encontrada no XML de entrada.")
            return gerar_erro_xml_padrao(f"Tabela '{tabela_id_resp}' não encontrada.", "Erro XML")

        tabela_element = tabela_elements[0]  # Pega a primeira tabela encontrada com o ID

        # Itera sobre as linhas da tabela
        for row in tabela_element.xpath("./Rows/Row"):
            is_current_row = row.get("IsCurrentRow") == "True"  # Verifica se é a linha atual

            if is_current_row:
                logging.debug(f"Atualizando linha com IsCurrentRow='True' na tabela '{tabela_id_resp}'.")

                # Atualiza os campos com os novos valores
                for field in row.xpath("./Fields/Field"):
                    field_id = field.find("ID").text if field.find("ID") is not None else None

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

            else: #Not current row
                for field in row.xpath("./Fields/Field"):
                    override_data_element = field.find("OverrideData")
                    if override_data_element is None:
                        override_data_element = etree.SubElement(field, "OverrideData")
                    override_data_element.text = "0"



        # Garante a declaração XML e codificação UTF-16
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_string = etree.tostring(root, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_final = xml_declaration + xml_string

        logging.debug("XML de Resposta (lxml, UTF-16):\n%s", xml_final)

        return Response(xml_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

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
    if not xml_data_str and request.data:
        try: xml_data_bytes = request.data; xml_data_str = xml_data_bytes.decode('utf-8'); logging.info("XML obtido de request.data (UTF-8).")
        except UnicodeDecodeError:
             try: xml_data_str = request.data.decode('latin-1'); xml_data_bytes = request.data; logging.info("XML obtido de request.data (Latin-1).")
             except UnicodeDecodeError: return gerar_erro_xml("Encoding inválido.", "Erro Encoding", 400)
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
        return gerar_resposta_xml(
            xml_data_bytes=xml_data_bytes,
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)