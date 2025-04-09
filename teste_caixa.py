from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO

# Configuração Básica
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# Colar as funções auxiliares aqui:
# - gerar_erro_xml_adaptado(...)
# - adicionar_campo_com_ID(...)
# - gerar_valores_peso(...)
# - gerar_resposta_com_linha_alvo(...) # Importante: Esta usa o dict da linha
# (Cole as definições completas dessas funções aqui, como na resposta anterior)
def gerar_erro_xml_adaptado(mensagem, short_text="Erro", status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    try: xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body; return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")
    except Exception as e: logging.exception("Erro XML erro"); return Response(f"Erro interno: {e}".encode('utf-8'), status=500)

def adicionar_campo_com_ID(parent_element, field_id, value):
    field = etree.SubElement(parent_element, "Field"); etree.SubElement(field, "ID").text = field_id; etree.SubElement(field, "Value").text = value if value is not None else ""

def gerar_valores_peso(tstpeso_valor, balanca_id):
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); 
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

def gerar_resposta_com_linha_alvo(linha_alvo_dict, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id):
    if linha_alvo_dict is None: return gerar_erro_xml_adaptado("Falha interna: Dados da linha alvo não encontrados.", "Erro Interno")
    tstpeso_valor_original = linha_alvo_dict.get(tstpeso_id, "0")
    logging.debug(f"Gerando resposta com linha alvo para balanca '{balanca_id}' (TST original: '{tstpeso_valor_original}')")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    return_value = etree.SubElement(response, "ReturnValueV2"); fields_container = etree.SubElement(return_value, "Fields")
    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"; peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"; pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    response_table = etree.SubElement(fields_container, "TableField"); etree.SubElement(response_table, "ID").text = tabela_id_alvo
    response_rows = etree.SubElement(response_table, "Rows"); response_row = etree.SubElement(response_rows, "Row")
    row_fields = etree.SubElement(response_row, "Fields")
    adicionar_campo_com_ID(row_fields, tstpeso_id, tstpeso_valor_original); adicionar_campo_com_ID(row_fields, peso_field_id, peso_novo); adicionar_campo_com_ID(row_fields, pesobalanca_field_id, pesobalanca_novo)
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    logging.debug("XML de Resposta com Linha Alvo Gerado (UTF-16):\n%s", xml_str_final)
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")


# Colar a função extrair_linha_alvo_e_tstpeso MODIFICADA aqui
def extrair_linha_alvo_e_tstpeso(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """
    Encontra a linha alvo (Current ou Primeira) na tabela especificada
    BUSCANDO A PARTIR DA RAIZ do XML, extrai o TSTPESO dela e retorna
    o valor do TSTPESO e o DICIONÁRIO de dados dessa linha alvo.

    Retorna: (tstpeso_valor, dicionario_linha_alvo) ou (None, None) se erro.
    """
    if not xml_bytes:
        logging.error("extrair_linha_alvo recebeu xml_bytes vazio.")
        return None, None
    try:
        logging.debug(f"--- Iniciando extrair_linha_alvo para Tabela '{tabela_id_alvo}', Campo TST '{tstpeso_id_alvo}' (buscando da raiz) ---")
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot() # Obtém o elemento raiz do XML recebido

        # *** REMOVIDO: Busca por <Form> ***

        # Encontra a tabela específica a partir da raiz
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']" # Id minúsculo input
        logging.debug(f"Executando XPath a partir da raiz para tabela: {xpath_tabela}")
        tabela_elements = root.xpath(xpath_tabela)

        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_alvo}' NÃO encontrada no XML.")
            logging.debug("--- Finalizando extrair_linha_alvo (Tabela não encontrada) ---")
            return None, None # Indica falha

        tabela_element = tabela_elements[0]
        logging.debug(f"Tabela '{tabela_id_alvo}' encontrada.")

        linha_alvo_element = None
        linha_alvo_info = "Nenhuma"

        # 1. Tenta IsCurrentRow="True"
        xpath_current = ".//Row[@IsCurrentRow='True']"
        current_rows = tabela_element.xpath(xpath_current)
        if current_rows:
            linha_alvo_element = current_rows[0]; linha_alvo_info = "IsCurrentRow='True'"; logging.info(f"Linha Alvo encontrada: {linha_alvo_info}")
        else: # 2. Fallback para primeira linha
            logging.debug("Nenhuma CurrentRow. Tentando a primeira linha...")
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list:
                linha_alvo_element = primeira_linha_list[0]; linha_alvo_info = "Primeira Linha"; logging.info(f"Linha Alvo encontrada: {linha_alvo_info}")
            else:
                logging.warning(f"Nenhuma linha encontrada na tabela '{tabela_id_alvo}'."); return None, None # Indica falha

        # Extrai TODOS os campos da linha alvo para um dicionário
        linha_alvo_dict = {}
        fields_container = linha_alvo_element.find('.//Fields')
        if fields_container is not None:
            for field in fields_container.findall('.//Field'):
                field_id = field.findtext("Id") # Id minúsculo input
                if field_id: linha_alvo_dict[field_id] = field.findtext("Value", default="").strip()
            logging.debug(f"Dados extraídos da Linha Alvo ({linha_alvo_info}): {linha_alvo_dict}")
        else: logging.warning(f"Container <Fields> não encontrado na linha alvo {linha_alvo_info}.")

        # Extrai e valida o TSTPESO deste dicionário
        tstpeso_valor = linha_alvo_dict.get(tstpeso_id_alvo, "0") # Default '0'
        if tstpeso_valor not in ["0", "1"]: tstpeso_valor = "0"; logging.warning(f"TSTPESO inválido '{linha_alvo_dict.get(tstpeso_id_alvo)}'. Usando '0'.")
        else: logging.info(f"Valor TSTPESO '{tstpeso_valor}' confirmado para a linha alvo.")

        logging.debug(f"--- Finalizando extrair_linha_alvo --- Retornando: ('{tstpeso_valor}', {{...dados...}})")
        return tstpeso_valor, linha_alvo_dict

    except Exception as e:
        logging.exception("Erro EXCEPCIONAL ao extrair linha alvo e TSTPESO"); return None, None


# --- Rota Principal (Ajustada para nova extração) ---

def encaxotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /balanca_simulador_final ---")
    # 1. Obtenção Robusta do XML
    content_type = request.headers.get("Content-Type", "").lower(); xml_data_str = None; xml_data_bytes = None
    # ... (código de obtenção mantido - tentar form, depois data) ...
    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form: xml_data_str = request.form.get(name); break
        if not xml_data_str and request.form: first_key = next(iter(request.form)); xml_data_str = request.form.get(first_key)
    if not xml_data_str and request.data:
        try: xml_data_bytes = request.data; xml_data_str = xml_data_bytes.decode('utf-8')
        except UnicodeDecodeError:
             try: xml_data_str = request.data.decode('latin-1'); xml_data_bytes = request.data
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
        logging.debug(f"Parâmetro 'balanca': '{balanca}'")

        # 3. Extrair LINHA ALVO e TSTPESO (usando a função modificada)
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        logging.debug(f"Chamando extrair_linha_alvo_e_tstpeso(tabela='{tabela_id_a_usar}', campo='{tstpeso_id_a_usar}')")
        tstpeso_valor_extraido, linha_alvo_extraida_dict = extrair_linha_alvo_e_tstpeso(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)

        # Verifica se a extração da linha falhou
        if linha_alvo_extraida_dict is None:
             # O erro específico já foi logado dentro da função de extração
             return gerar_erro_xml_adaptado("Falha ao processar a linha alvo no XML de entrada.", "Erro XML Linha")
        logging.info(f"TSTPESO extraído da linha alvo: '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        logging.debug(f"Chamando gerar_valores_peso(tstpeso='{tstpeso_valor_extraido}', balanca='{balanca}')")
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta com a Linha Alvo Atualizada
        logging.debug(f"Chamando gerar_resposta_com_linha_alvo(...)")
        # Passa o dicionário da linha original e os novos pesos
        return gerar_resposta_com_linha_alvo(
            linha_alvo_extraida_dict, peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /balanca_simulador_final")
        return gerar_erro_xml_adaptado(f"Erro interno inesperado no servidor: {str(e)}", "Erro Servidor", 500)