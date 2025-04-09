from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    """Gera um XML de erro no formato ResponseV2 (UTF-16)."""
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo_resposta_ID(parent_element, field_id, value):
    """Cria <Field><ID>...</ID><Value>...</Value></Field> para resposta."""
    field = etree.SubElement(parent_element, "Field"); etree.SubElement(field, "ID").text = field_id; etree.SubElement(field, "Value").text = value if value is not None else ""

def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """Extrai TSTPESO da linha relevante (Current ou Primeira). Retorna '0' ou '1'."""
    if not xml_bytes: return "0"
    try:
        parser = etree.XMLParser(recover=True); tree = etree.parse(BytesIO(xml_bytes), parser); root = tree.getroot()
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"; tabela_elements = root.xpath(xpath_tabela) # Id minúsculo input
        if not tabela_elements: return "0"
        tabela_element = tabela_elements[0]; linha_alvo = None
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows: linha_alvo = current_rows[0]; logging.info("Lendo TSTPESO da CurrentRow")
        else:
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list: linha_alvo = primeira_linha_list[0]; logging.info("Lendo TSTPESO da Primeira Linha")
            else: return "0"
        if linha_alvo is None: return "0"
        xpath_tstpeso = f".//Field[Id='{tstpeso_id_alvo}']/Value"; tstpeso_elements = linha_alvo.xpath(xpath_tstpeso) # Id minúsculo input
        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None: value_text = value_text.strip(); return value_text if value_text in ["0", "1"] else "0"
        logging.warning(f"TSTPESO '{tstpeso_id_alvo}' não encontrado/inválido. Usando '0'.")
        return "0"
    except Exception: logging.exception("Erro ao extrair TSTPESO"); return "0"

def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera peso e pesobalanca."""
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); 
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

# --- Função de Resposta FINAL (Retorna ResponseV2 com 1 Row na TableField) ---
def gerar_resposta_final_uma_linha(peso_novo, pesobalanca_novo, balanca_id, tstpeso_id_usado, tstpeso_valor_usado):
    """
    Gera ResponseV2 no padrão Officetrack, incluindo campos de nível superior
    (se existirem no input - esta versão NÃO os inclui para simplificar)
    e a TableField alvo contendo APENAS UMA Row com os 3 campos essenciais atualizados.
    """
    logging.debug(f"Gerando resposta UMA LINHA para balanca '{balanca_id}'")

    try:
        # --- Cria a estrutura da resposta ---
        nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        response = etree.Element("ResponseV2", nsmap=nsmap)
        message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
        return_value = etree.SubElement(response, "ReturnValueV2"); response_fields_container = etree.SubElement(return_value, "Fields")

        # --- Identificadores ---
        tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
        # tstpeso_id_usado é 'TSTPESO1' ou 'TSTPESO2'


        # --- Cria a TableField Alvo ---
        response_table = etree.SubElement(response_fields_container, "TableField")
        etree.SubElement(response_table, "ID").text = tabela_id_alvo # ID Maiúsculo resposta
        response_rows_container = etree.SubElement(response_table, "Rows")

        # --- Cria a ÚNICA Linha (Row) ---
        response_row = etree.SubElement(response_rows_container, "Row") # SEM IsCurrentRow
        response_row_fields = etree.SubElement(response_row, "Fields")

        # --- Adiciona os 3 Campos Essenciais ATUALIZADOS ---
        logging.info(f"Adicionando campos à única linha da resposta: TST={tstpeso_valor_usado}, PESO={peso_novo}, BALANCA={pesobalanca_novo}")
        adicionar_campo_resposta_ID(response_row_fields, tstpeso_id_usado, tstpeso_valor_usado)
        adicionar_campo_resposta_ID(response_row_fields, peso_field_id, peso_novo)
        adicionar_campo_resposta_ID(response_row_fields, pesobalanca_field_id, pesobalanca_novo)

        logging.debug(f"TableField '{tabela_id_alvo}' adicionada à resposta com UMA linha atualizada.")

        # --- Partes estáticas ---
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"

        # --- Serializa ---
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
        logging.debug("XML de Resposta UMA LINHA (UTF-16):\n%s", xml_str_final)
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.exception("Erro fatal ao gerar resposta (uma linha)")
        return gerar_erro_xml_padrao(f"Erro interno ao gerar resposta: {str(e)}", "Erro Servidor", 500)



def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /encaixotar ---")
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
             except UnicodeDecodeError: return gerar_erro_xml_padrao("Encoding inválido.", "Erro Encoding", 400)
    if not xml_data_bytes and xml_data_str:
        try: xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e: return gerar_erro_xml_padrao(f"Erro codificando form data: {e}", "Erro Encoding", 500)
    if not xml_data_bytes: return gerar_erro_xml_padrao("XML não encontrado.", "Erro Input", 400)

    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml_padrao("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair TSTPESO (da linha 'atual')
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído da linha 'atual': '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML FINAL (Apenas 1 Linha na Tabela)
        return gerar_resposta_final_uma_linha( # Chama a função SIMPLIFICADA
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id_usado=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml_padrao(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)