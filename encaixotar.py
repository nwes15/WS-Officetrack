# -*- coding: utf-8 -*-

from flask import Flask, request, Response
from lxml import etree
import logging
from io import BytesIO, StringIO # Usaremos BytesIO para lxml


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---

def gerar_erro_xml(mensagem, short_text="Erro", status_code=400):
    """Gera um XML de erro padronizado (UTF-16)."""
    # (Adaptado da sua versão)
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo <Field><ID>...</ID><Value>...</Value></Field> à resposta."""
    # (Adaptado da sua versão - usa ID maiúsculo)
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    # Garante que o valor seja string e trata None
    etree.SubElement(field, "Value").text = str(value) if value is not None else ""

def extrair_campo_nivel_superior(xml_bytes, field_id_alvo):
    """Extrai o valor de um campo específico no nível superior."""
    # (Mantida da versão anterior - busca por Id minúsculo no input)
    if not xml_bytes: return None
    try:
        parser = etree.XMLParser(recover=True); tree = etree.parse(BytesIO(xml_bytes), parser); root = tree.getroot()
        main_fields = root.find("./Fields") or root.find(".//Form/Fields")
        if main_fields is not None:
            field_element = main_fields.xpath(f"./Field[Id='{field_id_alvo}']")
            if field_element:
                value_elem = field_element[0].find("Value")
                if value_elem is not None and value_elem.text is not None: return value_elem.text.strip()
                else: return "" # Retorna vazio se <Value> existe mas está vazia
        return None # Campo ou container não encontrado
    except Exception: logging.exception(f"Erro ao extrair '{field_id_alvo}'"); return None

# --- Função de Geração de Resposta (Estilo CEP) ---
def gerar_resposta_pesos_lidos(peso_lido, pesobalanca_lido, balanca_id):
    """Gera a resposta XML V2 apenas com os dados de peso lidos."""
    logging.debug(f"Gerando resposta de consulta para balanca '{balanca_id}'")
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Pesos consultados com sucesso" # Mensagem apropriada
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields") # Container principal de campos

    # Determina os IDs para a RESPOSTA (maiúsculos)
    peso_id_resp = "PESO1" if balanca_id == "balanca1" else "PESO2"
    pesobalanca_id_resp = "PESOBALANCA1" if balanca_id == "balanca1" else "PESOBALANCA2"

    # Adiciona os DOIS campos lidos diretamente em <Fields>
    adicionar_campo(fields, peso_id_resp, peso_lido)
    adicionar_campo(fields, pesobalanca_id_resp, pesobalanca_lido)
    logging.info(f"Retornando: {peso_id_resp}='{peso_lido}', {pesobalanca_id_resp}='{pesobalanca_lido}'")

    # Adicionar campos adicionais estáticos do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "PESOS ATUAIS" # Texto apropriado
    etree.SubElement(return_value, "LongText")  # Vazio
    etree.SubElement(return_value, "Value").text = "58" # Valor fixo padrão

    # Gerar XML com declaração e encoding utf-16 (padrão dos exemplos)
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body

    logging.debug(f"XML de Resposta Consulta Pesos (UTF-16):\n{xml_str_final}")
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

# --- Rota Principal (Adaptada para Consulta Simples) ---
# ** Use a URL que o cliente chama para esta ação específica! **
@app.route("/consultar_peso_existente", methods=['POST']) # Exemplo de URL
def rota_consultar_peso_existente():
    logging.info(f"--- Nova Requisição {request.method} para /consultar_peso_existente ---")
    try:
        # --- 1. Obtenção Robusta do XML (adaptada dos exemplos) ---
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
                 except UnicodeDecodeError: return gerar_erro_xml("Encoding inválido.", "Erro Encoding", 400) # Usa a func de erro local
        if not xml_data_bytes and xml_data_str:
            try: xml_data_bytes = xml_data_str.encode('utf-8')
            except Exception as e: return gerar_erro_xml(f"Erro codificando form data: {e}", "Erro Encoding", 500)
        if not xml_data_bytes: return gerar_erro_xml("XML não encontrado.", "Erro Input", 400)
        logging.debug("XML Data (início):\n%s", xml_data_str[:500] if xml_data_str else "N/A")

        # --- 2. Obter parâmetro 'balanca' ---
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # --- 3. Extrair PESO e PESOBALANCA do Nível Superior ---
        peso_id_a_ler = "PESO1" if balanca == "balanca1" else "PESO2"
        pesobalanca_id_a_ler = "PESOBALANCA1" if balanca == "balanca1" else "PESOBALANCA2"

        # Chama a função de extração (que busca por Id minúsculo)
        peso_lido = extrair_campo_nivel_superior(xml_data_bytes, peso_id_a_ler)
        pesobalanca_lido = extrair_campo_nivel_superior(xml_data_bytes, pesobalanca_id_a_ler)

        # Log dos valores lidos (pode ser None ou "" se não encontrado/vazio)
        logging.info(f"Valores consultados nível sup: {peso_id_a_ler}='{peso_lido}', {pesobalanca_id_a_ler}='{pesobalanca_lido}'")

        # --- 4. Gerar Resposta XML SIMPLES com os valores lidos ---
        return gerar_resposta_pesos_lidos(
            peso_lido=peso_lido,
            pesobalanca_lido=pesobalanca_lido,
            balanca_id=balanca
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /consultar_peso_existente")
        # Usa a função de erro local
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)

