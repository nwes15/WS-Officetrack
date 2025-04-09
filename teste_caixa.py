# -*- coding: utf-8 -*-

from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---
# (gerar_erro_xml_adaptado, adicionar_campo_com_ID_resposta, extrair_tstpeso_da_tabela, gerar_valores_peso - MANTIDAS)
def gerar_erro_xml_adaptado(mensagem, short_text="Erro", status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo_com_ID_resposta(parent_element, field_id, value):
    field = etree.SubElement(parent_element, "Field"); etree.SubElement(field, "ID").text = field_id; etree.SubElement(field, "Value").text = value if value is not None else ""

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
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); 
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

# --- Função de Resposta AJUSTADA para Padrão Officetrack ---
def gerar_resposta_final_corrigida(xml_bytes_original, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id_usado, tstpeso_valor_usado):
    """
    Gera ResponseV2 no padrão Officetrack: inclui campos de nível superior
    e a TableField alvo com linhas ATÉ a atual (atualizada com 3 campos).
    """
    logging.debug(f"Gerando resposta FINAL CORRIGIDA (Padrão OT) para balanca '{balanca_id}'")
    if not xml_bytes_original: return gerar_erro_xml_adaptado("Erro interno: XML original não fornecido.")

    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes_original), parser)
        root_original = tree.getroot()

        # --- Cria a estrutura da resposta ---
        nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        response = etree.Element("ResponseV2", nsmap=nsmap)
        message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
        return_value = etree.SubElement(response, "ReturnValueV2"); response_fields_container = etree.SubElement(return_value, "Fields")

        # --- Identificadores ---
        tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

        # --- 1. Copia Campos de Nível Superior (se houver <Fields> principal) ---
        main_fields_original = root_original.find("./Fields") # Busca <Fields> direto sob a raiz (ou <Form>)
        if main_fields_original is not None:
            logging.debug("Copiando campos de nível superior para a resposta...")
            # Itera apenas sobre os <Field> diretos dentro do <Fields> principal
            for field_original in main_fields_original.xpath("./Field"): # XPath './Field' para filhos diretos
                original_id = field_original.findtext("Id") # Id minúsculo input
                original_value = field_original.findtext("Value", default="")
                if original_id:
                    # Adiciona à resposta com ID Maiúsculo
                    adicionar_campo_com_ID_resposta(response_fields_container, original_id.upper(), original_value)
                    logging.debug(f"  Campo Nível Sup. Copiado: ID={original_id.upper()}, Value='{original_value}'")
        else:
            logging.warning("Container <Fields> principal não encontrado no XML original.")


        # --- 2. Processa e Adiciona a TableField Alvo ---
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']" # Id minúsculo input
        tabela_elements = root_original.xpath(xpath_tabela)

        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_alvo}' não encontrada para adicionar à resposta.")
            # A resposta irá sem a tabela, mas com os campos de nível sup. (se houver)
        else:
            tabela_element_original = tabela_elements[0]
            logging.debug(f"Processando tabela '{tabela_id_alvo}' para resposta...")

            # Cria a TableField na resposta
            response_table = etree.SubElement(response_fields_container, "TableField")
            etree.SubElement(response_table, "ID").text = tabela_id_alvo # ID Maiúsculo resposta
            response_rows_container = etree.SubElement(response_table, "Rows")

            # Itera pelas linhas ORIGINAIS e copia/atualiza seletivamente
            for row_original in tabela_element_original.xpath(".//Row"):
                is_current = row_original.get("IsCurrentRow", "").lower() == 'true'
                response_row = etree.SubElement(response_rows_container, "Row")
                response_row_fields = etree.SubElement(response_row, "Fields")

                original_fields_container = row_original.find(".//Fields")
                if original_fields_container is None:
                     if is_current: break # Para se a linha atual não tem fields
                     else: continue      # Pula linha anterior vazia

                if is_current:
                    logging.info(f"Processando linha IsCurrentRow='True'. Adicionando 3 campos atualizados.")
                    adicionar_campo_com_ID_resposta(response_row_fields, tstpeso_id_usado, tstpeso_valor_usado)
                    adicionar_campo_com_ID_resposta(response_row_fields, peso_field_id, peso_novo)
                    adicionar_campo_com_ID_resposta(response_row_fields, pesobalanca_field_id, pesobalanca_novo)
                    break # PARA após processar a linha atual
                else:
                    logging.debug("Copiando 3 campos essenciais da linha anterior.")
                    def get_original_value(fields_cont, field_id_orig):
                        elem = fields_cont.xpath(f"./Field[Id='{field_id_orig}']/Value") # Id minúsculo input
                        return elem[0].text.strip() if elem and elem[0].text is not None else ""

                    original_tstpeso = get_original_value(original_fields_container, tstpeso_id_usado)
                    original_peso = get_original_value(original_fields_container, peso_field_id)
                    original_pesobalanca = get_original_value(original_fields_container, pesobalanca_field_id)

                    adicionar_campo_com_ID_resposta(response_row_fields, tstpeso_id_usado, original_tstpeso)
                    adicionar_campo_com_ID_resposta(response_row_fields, peso_field_id, original_peso)
                    adicionar_campo_com_ID_resposta(response_row_fields, pesobalanca_field_id, original_pesobalanca)

            logging.debug(f"Tabela '{tabela_id_alvo}' adicionada à resposta com linhas ATÉ a atual (apenas 3 campos por linha).")

        # --- Partes estáticas ---
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"

        # --- Serializa ---
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
        logging.debug("XML de Resposta FINAL CORRIGIDO (Padrão OT - UTF-16):\n%s", xml_str_final)
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.exception("Erro fatal ao gerar resposta final corrigida (Padrão OT)")
        return gerar_erro_xml_adaptado(f"Erro interno ao gerar resposta: {str(e)}", "Erro Servidor", 500)


# --- Rota Principal ---
# Use a URL que o cliente chama! Ex: /teste_caixa

def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    # 1. Obtenção Robusta do XML
    content_type = request.headers.get("Content-Type", "").lower(); xml_data_str = None; xml_data_bytes = None
    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form: xml_data_str = request.form.get(name); break
        if not xml_data_str and request.form: first_key = next(iter(request.form)); xml_data_str = request.form.get(first_key)
        if xml_data_str: logging.info("XML obtido de request.form.")
    if not xml_data_str and request.data:
        try: xml_data_bytes = request.data; xml_data_str = xml_data_bytes.decode('utf-8'); logging.info("XML obtido de request.data (UTF-8).")
        except UnicodeDecodeError:
             try: xml_data_str = request.data.decode('latin-1'); xml_data_bytes = request.data; logging.info("XML obtido de request.data (Latin-1).")
             except UnicodeDecodeError: return gerar_erro_xml_adaptado("Encoding inválido.", "Erro Encoding", 400)
    if not xml_data_bytes and xml_data_str:
        try: xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e: return gerar_erro_xml_adaptado(f"Erro codificando form data: {e}", "Erro Encoding", 500)
    if not xml_data_bytes: return gerar_erro_xml_adaptado("XML não encontrado.", "Erro Input", 400)
    logging.debug("XML Data (início):\n%s", xml_data_str[:500] if xml_data_str else "N/A")

    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml_adaptado("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair TSTPESO (da linha 'atual')
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído: '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML no Padrão Officetrack
        return gerar_resposta_final_corrigida( # Chama a função ajustada
            xml_bytes_original=xml_data_bytes,
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id_usado=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml_adaptado(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)
