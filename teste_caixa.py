from flask import Flask, request, Response
from lxml import etree # Usar lxml como nos exemplos
import random
import logging
from io import BytesIO, StringIO # Usar BytesIO ou StringIO dependendo do input para etree


logging.basicConfig(level=logging.DEBUG) # Use DEBUG para ver detalhes

# --- Funções Auxiliares (Adaptadas dos exemplos) ---

def gerar_erro_xml_adaptado(mensagem, short_text="Erro", status_code=400):
    """Gera um XML de erro no formato ResponseV2 (UTF-16)."""
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "Fields") # Container vazio
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0" # Valor padrão para erro

    # Geração manual da declaração + tostring (padrão dos exemplos)
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    # Decodifica para string Python antes de concatenar
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + "\n" + xml_body

    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo_com_ID(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field>."""
    # Usa ID maiúsculo como visto nos helpers dos exemplos
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value if value is not None else ""

def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """Extrai TSTPESO da linha relevante da tabela alvo usando lxml."""
    # (Função mantida da resposta anterior - parece robusta)
    try:
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        tree = etree.parse(BytesIO(xml_data_bytes), parser) # lxml com BytesIO
        root = tree.getroot()
        tabela_element = root.xpath(f".//TableField[Id='{tabela_id_alvo}']") # Busca por Id (minúsculo do input)
        if not tabela_element: return "0" # Default
        tabela_element = tabela_element[0]
        linha_alvo = None
        current_row = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_row: linha_alvo = current_row[0]
        else:
            primeira_linha = tabela_element.xpath(".//Row[1]")
            if primeira_linha: linha_alvo = primeira_linha[0]
        if linha_alvo is None: return "0" # Default
        # Busca por Id (minúsculo do input)
        tstpeso_element = linha_alvo.xpath(f".//Field[Id='{tstpeso_id_alvo}']/Value")
        if tstpeso_element:
            tstpeso_valor = tstpeso_element[0].text
            if tstpeso_valor is not None:
                tstpeso_valor = tstpeso_valor.strip()
                if tstpeso_valor in ["0", "1"]: return tstpeso_valor
        return "0" # Default
    except Exception as e:
        logging.exception(f"Erro ao extrair {tstpeso_id_alvo} da tabela {tabela_id_alvo}")
        return "0"

def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera peso e pesobalanca (formato string com vírgula)."""
    # (Função mantida)
    def formatar_numero():
        return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0":
        valor = formatar_numero(); return valor, valor
    else:
        peso = formatar_numero(); pesobalanca = formatar_numero()
        while peso == pesobalanca: pesobalanca = formatar_numero()
        return peso, pesobalanca

def gerar_resposta_balanca_final(peso, pesobalanca, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """Gera ResponseV2 com TableField mínima (1 linha, 3 campos). UTF-16."""
    # (Adaptada para seguir padrão dos exemplos)
    logging.debug(f"Gerando resposta final (balanca) para balanca '{balanca_id}'")
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    return_value = etree.SubElement(response, "ReturnValueV2")
    response_fields_container = etree.SubElement(return_value, "Fields")

    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

    # Cria a TableField na resposta
    response_table = etree.SubElement(response_fields_container, "TableField")
    etree.SubElement(response_table, "ID").text = tabela_id_alvo # ID maiúsculo na resposta

    # Cria Rows e a única Row
    response_rows_container = etree.SubElement(response_table, "Rows")
    response_row = etree.SubElement(response_rows_container, "Row")
    # Adicionar atributos à Row se necessário (ex: IsCurrentRow="True"?)

    # Adiciona Fields dentro da Row
    response_row_fields_container = etree.SubElement(response_row, "Fields")

    # Adiciona os 3 campos essenciais usando a helper que gera ID maiúsculo
    adicionar_campo_com_ID(response_row_fields_container, tstpeso_id, tstpeso_valor_usado)
    adicionar_campo_com_ID(response_row_fields_container, peso_field_id, peso)
    adicionar_campo_com_ID(response_row_fields_container, pesobalanca_field_id, pesobalanca)

    # Partes estáticas do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"

    # Serialização manual UTF-16 + Declaração
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    # Decodifica para string python antes de concatenar
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + "\n" + xml_body

    logging.debug("XML de Resposta Balança Final (UTF-16):\n%s", xml_str_final)
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

# --- Rota Principal (Adaptada) ---
 # Rota POST, nome descritivo
def encaxotar_v2():
    logging.info(f"Recebida requisição {request.method} para /balanca_simulador")
    try:
        # --- Obter XML (lógica robusta dos exemplos) ---
        content_type = request.headers.get("Content-Type", "").lower()
        logging.debug(f"Content-Type recebido: {content_type}")
        xml_data_str = None
        xml_data_bytes = None

        # Prioriza form data (como nos exemplos)
        if request.form:
            for possible_name in ["TextXML", "textxml", "xmldata", "xml"]:
                if possible_name in request.form:
                    xml_data_str = request.form.get(possible_name)
                    logging.debug(f"XML encontrado no campo form '{possible_name}'")
                    break
            if not xml_data_str and len(request.form) > 0: # Fallback para primeiro campo do form
                first_key = next(iter(request.form))
                xml_data_str = request.form.get(first_key)
                logging.debug(f"Usando primeiro campo do form: '{first_key}'")

        # Se não encontrou no form, tenta o corpo bruto (request.data)
        if not xml_data_str and request.data:
            try:
                # Tenta decodificar como UTF-8 (comum)
                xml_data_bytes = request.data # Mantem como bytes para lxml
                xml_data_str = xml_data_bytes.decode('utf-8') # String para logging
                logging.debug("Usando dados brutos do corpo da requisição (request.data)")
            except UnicodeDecodeError:
                 logging.warning("Falha ao decodificar request.data como UTF-8, tentando latin-1")
                 try:
                     xml_data_str = request.data.decode('latin-1')
                     xml_data_bytes = request.data # Ainda usa bytes originais para lxml
                 except UnicodeDecodeError:
                     return gerar_erro_xml_adaptado("Não foi possível decodificar o corpo da requisição. Use UTF-8 ou Latin-1.", "Erro Encoding", 400)

        if not xml_data_bytes and xml_data_str: # Se pegou do form, codifica para bytes
            xml_data_bytes = xml_data_str.encode('utf-8')

        if not xml_data_bytes:
            return gerar_erro_xml_adaptado("Não foi possível encontrar dados XML na requisição.", "Erro Input", 400)

        logging.debug("XML Data (início):\n%s", xml_data_str[:500] if xml_data_str else "N/A") # Log do início do XML

        # --- Obter parâmetro 'balanca' ---
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]:
            return gerar_erro_xml_adaptado("Parâmetro 'balanca' inválido na URL.", "Erro Param", 400)

        # --- Extrair TSTPESO ---
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        # Passa os bytes para a função de extração
        tstpeso_valor_usado = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        # A função já valida e retorna '0' como default

        # --- Gerar Pesos ---
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_usado, balanca)

        # --- Gerar Resposta Final ---
        return gerar_resposta_balanca_final(
            peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar, tstpeso_valor_usado
        )

    except Exception as e:
        logging.exception("Erro fatal na rota /balanca_simulador")
        return gerar_erro_xml_adaptado(f"Erro interno inesperado no servidor: {str(e)}", "Erro Servidor", 500)