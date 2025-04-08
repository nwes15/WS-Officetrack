from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---

def gerar_erro_xml_adaptado(mensagem, short_text="Erro", status_code=400):
    # (Função mantida)
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    try:
        xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body
        return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")
    except Exception as e:
        logging.exception("Erro ao gerar/codificar XML de erro")
        return Response(f"Erro interno ao gerar XML de erro: {e}".encode('utf-8'), status=500, content_type="text/plain")

def adicionar_campo_com_ID(parent_element, field_id, value):
    # (Função mantida - ID maiúsculo)
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value if value is not None else ""

# --- Função de Extração com LOGGING e CORREÇÃO ---
def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """Extrai TSTPESO com logging detalhado e correção de variável."""
    if not xml_bytes:
        logging.error("extrair_tstpeso_da_tabela recebeu xml_bytes vazio ou None.")
        return "0"
    try:
        logging.debug(f"--- Iniciando extrair_tstpeso_da_tabela para Tabela '{tabela_id_alvo}', Campo '{tstpeso_id_alvo}' ---")
        parser = etree.XMLParser(recover=True) # Deixa lxml detectar encoding dos bytes
        # *** CORREÇÃO APLICADA AQUI ***
        tree = etree.parse(BytesIO(xml_bytes), parser) # Usa o argumento xml_bytes
        root = tree.getroot()

        # Encontra a tabela específica (Busca por Id minúsculo do input XML)
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"
        logging.debug(f"Executando XPath para tabela: {xpath_tabela}")
        tabela_elements = root.xpath(xpath_tabela)

        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_alvo}' NÃO encontrada via XPath.")
            logging.debug("--- Finalizando extrair_tstpeso_da_tabela (Tabela não encontrada) ---")
            return "0" # Default se tabela não existe

        tabela_element = tabela_elements[0]
        logging.debug(f"Tabela '{tabela_id_alvo}' encontrada.")

        linha_alvo = None
        linha_alvo_info = "Nenhuma"

        # 1. Tenta IsCurrentRow="True"
        xpath_current = ".//Row[@IsCurrentRow='True']"
        logging.debug(f"Executando XPath para CurrentRow: {xpath_current} (dentro da tabela)")
        current_rows = tabela_element.xpath(xpath_current)
        if current_rows:
            linha_alvo = current_rows[0]
            linha_alvo_info = "IsCurrentRow='True'"
            logging.info(f"Linha Alvo encontrada: {linha_alvo_info}")
        else:
            # 2. Fallback para primeira linha
            logging.debug("Nenhuma linha com IsCurrentRow='True'. Tentando a primeira linha (XPath: .//Row[1])...")
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list:
                linha_alvo = primeira_linha_list[0]
                linha_alvo_info = "Primeira Linha"
                logging.info(f"Linha Alvo encontrada: {linha_alvo_info}")
            else:
                logging.warning(f"Nenhuma linha encontrada na tabela '{tabela_id_alvo}'.")
                logging.debug("--- Finalizando extrair_tstpeso_da_tabela (Nenhuma linha encontrada) ---")
                return "0"

        # LOG Campos da linha selecionada
        if linha_alvo is not None:
            try:
                fields_container_log = linha_alvo.find('.//Fields')
                if fields_container_log is not None:
                    fields_text = etree.tostring(fields_container_log, encoding='unicode', pretty_print=True)
                    logging.debug(f"Campos encontrados na '{linha_alvo_info}':\n{fields_text}")
                else:
                    logging.debug(f"Container <Fields> não encontrado na '{linha_alvo_info}'.")
            except Exception as log_err:
                logging.debug(f"Não foi possível logar campos da '{linha_alvo_info}': {log_err}")

        # 3. Extrai o TSTPESO da linha_alvo
        tstpeso_valor_final = "0"
        # Busca por Id minúsculo do input
        xpath_tstpeso = f".//Field[Id='{tstpeso_id_alvo}']/Value"
        logging.debug(f"Executando XPath para TSTPESO: {xpath_tstpeso} (dentro da linha alvo)")
        tstpeso_elements = linha_alvo.xpath(xpath_tstpeso)

        if tstpeso_elements:
            value_element = tstpeso_elements[0]
            value_text = value_element.text
            if value_text is not None:
                value_text = value_text.strip()
                logging.debug(f"Texto bruto encontrado em <Value> para {tstpeso_id_alvo}: '{value_text}'")
                if value_text == "1": tstpeso_valor_final = "1"; logging.info(f"-> VALOR '1' DETECTADO.")
                elif value_text == "0": tstpeso_valor_final = "0"; logging.info(f"-> VALOR '0' DETECTADO.")
                else: logging.warning(f"Valor '{value_text}' INVÁLIDO para {tstpeso_id_alvo}. Usando default '0'.")
            else: logging.warning(f"Tag <Value> para {tstpeso_id_alvo} VAZIA. Usando default '0'.")
        else: logging.warning(f"Campo <Field> com Id='{tstpeso_id_alvo}' / <Value> NÃO encontrado na linha alvo ({linha_alvo_info}). Usando default '0'.")

        logging.debug(f"--- Finalizando extrair_tstpeso_da_tabela --- Retornando: '{tstpeso_valor_final}'")
        return tstpeso_valor_final

    except etree.XMLSyntaxError as e:
        logging.error(f"Erro de Sintaxe XML ao extrair TSTPESO: {e}")
        return "0"
    except Exception as e:
        logging.exception(f"Erro EXCEPCIONAL ao extrair {tstpeso_id_alvo}")
        return "0"

# --- Restante das Funções Auxiliares e Rota Flask ---
# Colar aqui as funções:
# - gerar_valores_peso(...)
# - gerar_resposta_balanca_final(...)
# - A rota @app.route("/balanca_simulador", methods=['POST']) def simular_balanca(): ...
# - O bloco if __name__ == '__main__': ...
# (Exatamente como estavam na resposta anterior, pois a chamada a extrair_tstpeso_da_tabela já estava correta lá)

# Exemplo resumido do que colar aqui:
def gerar_valores_peso(tstpeso_valor, balanca_id):
    # ... (código mantido) ...
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); 
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

def gerar_resposta_balanca_final(peso, pesobalanca, balanca_id, tstpeso_id, tstpeso_valor_usado):
    # ... (código mantido) ...
    logging.debug(f"Gerando resposta FINAL para balanca '{balanca_id}' com TST={tstpeso_valor_usado}, Peso={peso}, Balanca={pesobalanca}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    return_value = etree.SubElement(response, "ReturnValueV2"); fields_container = etree.SubElement(return_value, "Fields")
    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"; peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"; pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    response_table = etree.SubElement(fields_container, "TableField"); etree.SubElement(response_table, "ID").text = tabela_id_alvo
    response_rows = etree.SubElement(response_table, "Rows"); response_row = etree.SubElement(response_rows, "Row")
    row_fields = etree.SubElement(response_row, "Fields")
    adicionar_campo_com_ID(row_fields, tstpeso_id, tstpeso_valor_usado); adicionar_campo_com_ID(row_fields, peso_field_id, peso); adicionar_campo_com_ID(row_fields, pesobalanca_field_id, pesobalanca)
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    logging.debug("XML de Resposta MÍNIMA Gerado (UTF-16):\n%s", xml_str_final)
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")


def encaxotar_v2():
    # ... (código da rota mantido, ele já chama extrair_tstpeso_da_tabela corretamente com xml_data_bytes) ...
    logging.info(f"--- Nova Requisição {request.method} para /balanca_simulador ---")
    content_type = request.headers.get("Content-Type", "").lower(); xml_data_str = None; xml_data_bytes = None
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
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml_adaptado("Parâmetro 'balanca' inválido.", "Erro Param", 400)
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        logging.debug(f"Chamando extrair_tstpeso_da_tabela(tabela='{tabela_id_a_usar}', campo='{tstpeso_id_a_usar}')")
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído: '{tstpeso_valor_extraido}'")
        logging.debug(f"Chamando gerar_valores_peso(tstpeso='{tstpeso_valor_extraido}', balanca='{balanca}')")
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)
        logging.debug(f"Chamando gerar_resposta_balanca_final(...)")
        return gerar_resposta_balanca_final(peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar, tstpeso_valor_extraido)
    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /balanca_simulador")
        return gerar_erro_xml_adaptado(f"Erro interno: {str(e)}", "Erro Servidor", 500)