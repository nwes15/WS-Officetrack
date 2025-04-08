from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG) # Mantenha DEBUG

# --- Funções Auxiliares ---

def gerar_erro(mensagem, status_code=400):
    # (Função mantida)
    logging.error(f"Gerando erro: {mensagem}")
    xml_erro = f"<Error><Message>{mensagem}</Message></Error>"
    return Response(xml_erro.encode('utf-8'), status=status_code, content_type='application/xml; charset=utf-8')

def adicionar_campo_xml_com_ID(parent_element, field_id, value):
    # (Função mantida - usa ID maiúsculo na resposta)
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value if value is not None else ""

# --- Função de Extração com LOGGING DETALHADO ---
def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """Extrai TSTPESO com logging detalhado para diagnóstico."""
    if not xml_bytes:
        logging.error("extrair_tstpeso_da_tabela recebeu xml_bytes vazio.")
        return "0"
    try:
        logging.debug(f"--- Iniciando extrair_tstpeso_da_tabela para Tabela '{tabela_id_alvo}', Campo '{tstpeso_id_alvo}' ---")
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()

        # Encontra a tabela específica
        tabela_elements = root.xpath(f".//TableField[Id='{tabela_id_alvo}']") # Busca por Id minúsculo do input
        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_alvo}' NÃO encontrada.")
            logging.debug("--- Finalizando extrair_tstpeso_da_tabela (Tabela não encontrada) ---")
            return "0"
        tabela_element = tabela_elements[0]
        logging.debug(f"Tabela '{tabela_id_alvo}' encontrada.")

        linha_alvo = None
        linha_alvo_index = -1

        # 1. Tenta encontrar a linha com IsCurrentRow="True"
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows:
            linha_alvo = current_rows[0]
            # Tenta obter o índice original se o guardamos (útil para debug)
            try:
                 linha_alvo_index = int(linha_alvo.xpath("string(./@_row_index)")) # Exemplo, se guardássemos índice
            except: pass # Ignora se não conseguir
            logging.info(f"Linha Alvo encontrada: Marcada como IsCurrentRow='True' (Índice aprox. {linha_alvo_index if linha_alvo_index != -1 else '?'})")
        else:
            # 2. Se não houver CurrentRow, pega a primeira linha
            logging.debug("Nenhuma linha com IsCurrentRow='True'. Tentando a primeira linha...")
            primeira_linha_list = tabela_element.xpath(".//Row[1]") # XPath [1] para primeira
            if primeira_linha_list:
                linha_alvo = primeira_linha_list[0]
                linha_alvo_index = 0 # É a primeira
                logging.info(f"Linha Alvo encontrada: Primeira linha (Índice {linha_alvo_index})")
            else:
                logging.warning(f"Nenhuma linha (nem Current, nem Primeira) encontrada na tabela '{tabela_id_alvo}'.")
                logging.debug("--- Finalizando extrair_tstpeso_da_tabela (Nenhuma linha encontrada) ---")
                return "0" # Default se não há linhas

        # 3. Extrai o TSTPESO da linha_alvo
        tstpeso_valor = "0" # Default inicial
        # Busca pelo Id minúsculo do input dentro da linha_alvo
        tstpeso_elements = linha_alvo.xpath(f".//Field[Id='{tstpeso_id_alvo}']/Value")
        if tstpeso_elements:
            logging.debug(f"Elemento(s) Field[Id='{tstpeso_id_alvo}']/Value encontrado(s).")
            value_text = tstpeso_elements[0].text
            if value_text is not None:
                value_text = value_text.strip()
                logging.debug(f"Texto encontrado em <Value>: '{value_text}'")
                if value_text in ["0", "1"]:
                    tstpeso_valor = value_text
                    logging.info(f"VALOR FINAL de {tstpeso_id_alvo} extraído da linha alvo: '{tstpeso_valor}'")
                else:
                    logging.warning(f"Valor '{value_text}' é inválido para {tstpeso_id_alvo}. Usando default '0'.")
            else:
                logging.warning(f"Tag <Value> para {tstpeso_id_alvo} está vazia (None). Usando default '0'.")
        else:
            logging.warning(f"Campo <Field> com Id='{tstpeso_id_alvo}' ou sua tag <Value> NÃO encontrados na linha alvo (Índice {linha_alvo_index}). Usando default '0'.")

        logging.debug(f"--- Finalizando extrair_tstpeso_da_tabela --- Retornando: '{tstpeso_valor}'")
        return tstpeso_valor

    except Exception as e:
        logging.exception(f"Erro EXCEPCIONAL ao extrair {tstpeso_id_alvo}")
        logging.debug("--- Finalizando extrair_tstpeso_da_tabela (Exceção) ---")
        return "0" # Default seguro

def gerar_valores_peso(tstpeso_valor, balanca_id):
    # (Função mantida - sem alterações necessárias aqui)
    def formatar_numero():
        return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0":
        valor = formatar_numero(); logging.debug(f"  -> Peso/Balanca (TST=0): {valor}"); return valor, valor
    else:
        peso = formatar_numero(); pesobalanca = formatar_numero()
        while peso == pesobalanca: pesobalanca = formatar_numero()
        logging.debug(f"  -> Peso (TST=1): {peso}, Balanca: {pesobalanca}"); return peso, pesobalanca

def gerar_resposta_xml_minima(peso, pesobalanca, balanca_id, tstpeso_id, tstpeso_valor_usado):
    # (Função mantida - gera a resposta mínima com ID maiúsculo)
    logging.debug(f"Gerando resposta MÍNIMA para balanca '{balanca_id}' com TST={tstpeso_valor_usado}, Peso={peso}, Balanca={pesobalanca}")
    nsmap = { 'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema' }
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    return_value = etree.SubElement(response, "ReturnValueV2"); fields_container = etree.SubElement(return_value, "Fields")
    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    response_table = etree.SubElement(fields_container, "TableField"); etree.SubElement(response_table, "ID").text = tabela_id_alvo
    response_rows = etree.SubElement(response_table, "Rows"); response_row = etree.SubElement(response_rows, "Row")
    row_fields = etree.SubElement(response_row, "Fields")
    adicionar_campo_xml_com_ID(row_fields, tstpeso_id, tstpeso_valor_usado)
    adicionar_campo_xml_com_ID(row_fields, peso_field_id, peso)
    adicionar_campo_xml_com_ID(row_fields, pesobalanca_field_id, pesobalanca)
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    logging.debug("XML de Resposta MÍNIMA Gerado (UTF-16):\n%s", xml_str_final)
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")



def encaxotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /balanca_simulador_debug ---")
    # 1. Validação da Requisição
    if not request.data or 'xml' not in (request.content_type or '').lower():
         logging.error(f"Falha na validação: Content-Type='{request.content_type}', request.data is empty={not request.data}")
         return gerar_erro("Requisição inválida. Content-Type XML e corpo são necessários.", 400)

    balanca = request.args.get('balanca', 'balanca1').lower()
    logging.debug(f"Parâmetro 'balanca' da URL: '{balanca}'")
    if balanca not in ["balanca1", "balanca2"]:
        return gerar_erro("Parâmetro 'balanca' inválido na URL.")

    try:
        xml_data_bytes = request.data
        logging.debug("XML Recebido (bytes, início): %s", xml_data_bytes[:500]) # Log do início

        # 2. Extrair TSTPESO (com logging detalhado)
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        logging.debug(f"Chamando extrair_tstpeso_da_tabela(tabela='{tabela_id_a_usar}', campo='{tstpeso_id_a_usar}')")
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        # A função já valida internamente e retorna '0' por default

        # 3. Gerar Pesos
        logging.debug(f"Chamando gerar_valores_peso(tstpeso='{tstpeso_valor_extraido}', balanca='{balanca}')")
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 4. Gerar Resposta XML Mínima
        logging.debug(f"Chamando gerar_resposta_xml_minima(peso='{peso_novo}', pesobalanca='{pesobalanca_novo}', balanca='{balanca}', tstpeso_id='{tstpeso_id_a_usar}', tstpeso_valor='{tstpeso_valor_extraido}')")
        return gerar_resposta_xml_minima(
            peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar, tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /balanca_simulador_debug")
        return gerar_erro(f"Erro interno inesperado no servidor: {str(e)}", 500)