# -*- coding: utf-8 -*-

from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO, StringIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')



def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    """Gera um XML de erro no formato ResponseV2 (UTF-16)."""
    # (Usando a versão robusta)
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo_com_ID_resposta(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field> (ID maiúsculo)."""
    # (Usando a versão que garante ID maiúsculo)
    field = etree.SubElement(parent_element, "Field"); etree.SubElement(field, "ID").text = field_id; etree.SubElement(field, "Value").text = value if value is not None else ""

def extrair_campo_nivel_superior(xml_bytes, field_id_alvo):
    """Extrai o valor de um campo específico no nível superior."""
    # (Usando a versão robusta que busca Id minúsculo)
    if not xml_bytes: return None
    try:
        parser = etree.XMLParser(recover=True); tree = etree.parse(BytesIO(xml_bytes), parser); root = tree.getroot()
        main_fields = root.find("./Fields") or root.find(".//Form/Fields")
        if main_fields is not None:
            field_element = main_fields.xpath(f"./Field[Id='{field_id_alvo}']") # Id minúsculo
            if field_element:
                value_elem = field_element[0].find("Value")
                if value_elem is not None and value_elem.text is not None: return value_elem.text.strip()
                else: return ""
        return None
    except Exception: logging.exception(f"Erro ao extrair '{field_id_alvo}'"); return None

# --- Função gerar_valores_peso CORRIGIDA ---
def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera peso e pesobalanca, respeitando TSTPESO."""
    def formatar_numero():
        # 3 casas decimais
        return "{:.3f}".format(random.uniform(0.5, 500.0)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")

    # Normaliza para '0' ou '1'
    tstpeso_normalizado = "1" if str(tstpeso_valor).strip() == "1" else "0"
    if tstpeso_normalizado != tstpeso_valor: logging.warning(f"TSTPESO original '{tstpeso_valor}' normalizado para '{tstpeso_normalizado}'.")

    if tstpeso_normalizado == "0":
        valor = formatar_numero()
        logging.debug(f"  -> Peso/Balanca (TST=0): {valor}")
        return valor, valor
    else: # tstpeso_normalizado == "1"
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        retry_count = 0; max_retries = 10
        # *** LOOP WHILE ADICIONADO ***
        while peso == pesobalanca and retry_count < max_retries:
            logging.debug("  -> Regerando pesobalanca...")
            pesobalanca = formatar_numero()
            retry_count += 1
        # ****************************
        if peso == pesobalanca: logging.warning("Não gerou pesos diferentes!")
        logging.debug(f"  -> Peso (TST=1): {peso}, Balanca: {pesobalanca}")
        return peso, pesobalanca # Retorna valores (quase sempre) diferentes

# --- Função de Resposta SIMPLES (Estilo CEP / Balanca Consulta) ---
def gerar_resposta_campos_simples(peso_val, pesobalanca_val, balanca_id, tstpeso_id, tstpeso_val):
    """Gera ResponseV2 apenas com os campos PESOn, PESOBALANCAn e TSTPESOn."""
    logging.debug(f"Gerando resposta CAMPOS SIMPLES para balanca '{balanca_id}'")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    return_value = etree.SubElement(response, "ReturnValueV2"); fields_container = etree.SubElement(return_value, "Fields")

    # IDs da Resposta (maiúsculos)
    peso_id_resp = "PESO1" if balanca_id == "balanca1" else "PESO2"
    pesobalanca_id_resp = "PESOBALANCA1" if balanca_id == "balanca1" else "PESOBALANCA2"
    # tstpeso_id já é TSTPESO1 ou TSTPESO2

    # Adiciona os 3 campos diretamente
    adicionar_campo_com_ID_resposta(fields_container, peso_id_resp, peso_val)
    adicionar_campo_com_ID_resposta(fields_container, pesobalanca_id_resp, pesobalanca_val)
    adicionar_campo_com_ID_resposta(fields_container, tstpeso_id, tstpeso_val) # Inclui o TSTPESO usado

    # Partes estáticas
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"

    # Serialização
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    logging.debug("XML Resp Campos Simples (UTF-16):\n%s", xml_str_final)
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")



def encaixotar_v3():
    logging.info(f"--- Nova Requisição {request.method} para {request.path} ---")
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

        # *** 3. Extrair TSTPESO do Nível Superior CORRETAMENTE ***
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tstpeso_valor_extraido = extrair_campo_nivel_superior(xml_data_bytes, tstpeso_id_a_usar)
        # A função gerar_valores_peso trata None/inválido
        logging.info(f"TSTPESO extraído (nível superior) para {tstpeso_id_a_usar}: '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos (usando função CORRIGIDA)
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML SIMPLES (sem tabela)
        # Normaliza o TSTPESO para resposta
        tstpeso_resp = "1" if str(tstpeso_valor_extraido).strip() == "1" else "0"
        return gerar_resposta_campos_simples(
            peso_val=peso_novo,
            pesobalanca_val=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar, # TSTPESO1 ou TSTPESO2
            tstpeso_val=tstpeso_resp     # 0 ou 1
        )

    except Exception as e:
        logging.exception(f"Erro GERAL fatal na rota {request.path}")
        return gerar_erro_xml_padrao(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)

