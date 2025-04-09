from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---
# (gerar_erro_xml_adaptado, adicionar_campo_com_ID, gerar_valores_peso - mantidas)
def gerar_erro_xml_adaptado(mensagem, short_text="Erro", status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo_com_ID(parent_element, field_id, value):
    field = etree.SubElement(parent_element, "Field"); etree.SubElement(field, "ID").text = field_id; etree.SubElement(field, "Value").text = value if value is not None else ""

def gerar_valores_peso(tstpeso_valor, balanca_id):
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); 
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

# --- Função de Extração de TSTPESO (Mantida - só precisamos do valor) ---
def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    # (Função mantida como na versão anterior - retorna '0' ou '1')
    if not xml_bytes: return "0"
    try:
        parser = etree.XMLParser(recover=True); tree = etree.parse(BytesIO(xml_bytes), parser); root = tree.getroot()
        tabela_elements = root.xpath(f".//TableField[Id='{tabela_id_alvo}']")
        if not tabela_elements: return "0"
        tabela_element = tabela_elements[0]; linha_alvo = None
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows: linha_alvo = current_rows[0]
        else:
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list: linha_alvo = primeira_linha_list[0]
        if linha_alvo is None: return "0"
        tstpeso_elements = linha_alvo.xpath(f".//Field[Id='{tstpeso_id_alvo}']/Value")
        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None: value_text = value_text.strip(); return value_text if value_text in ["0", "1"] else "0"
        return "0"
    except Exception: logging.exception("Erro ao extrair TSTPESO"); return "0"

# --- NOVA Função de Resposta: Retorna Tabela Completa Modificada ---
def gerar_resposta_com_tabela_modificada(xml_bytes_original, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id_usado, tstpeso_valor_usado):
    """
    Gera ResponseV2 contendo a TableField alvo COMPLETA do input,
    mas com os campos de peso atualizados na primeira linha vazia encontrada.
    """
    logging.debug(f"Gerando resposta com tabela MODIFICADA para balanca '{balanca_id}'")
    if not xml_bytes_original: return gerar_erro_xml("Erro interno: XML original não fornecido para gerar resposta.")

    try:
        # Parseia o XML original novamente para poder modificá-lo e usá-lo
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes_original), parser)
        root_original = tree.getroot()

        # --- Cria a estrutura da resposta ---
        nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        response = etree.Element("ResponseV2", nsmap=nsmap)
        message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
        return_value = etree.SubElement(response, "ReturnValueV2"); fields_container = etree.SubElement(return_value, "Fields")

        # --- Encontra e Modifica a Tabela Alvo ---
        tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']" # Id minúsculo do input
        tabela_elements = root_original.xpath(xpath_tabela)

        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_alvo}' não encontrada no XML original para incluir na resposta.")
            # O que fazer? Retornar erro ou resposta sem a tabela? Vamos retornar sem a tabela por ora.
        else:
            tabela_element_original = tabela_elements[0]
            logging.debug(f"Encontrada tabela '{tabela_id_alvo}' original. Modificando e adicionando à resposta...")

            # Modifica a linha correta DENTRO da árvore original parseada
            update_realizado = False
            rows_container = tabela_element_original.find(".//Rows")
            if rows_container is not None:
                for row in rows_container.findall(".//Row"):
                    fields_in_row = row.find(".//Fields")
                    if fields_in_row is None: continue

                    # Verifica se esta linha é a primeira vazia
                    peso_val_elem = fields_in_row.xpath(f"./Field[Id='{peso_field_id}']/Value")
                    balanca_val_elem = fields_in_row.xpath(f"./Field[Id='{pesobalanca_field_id}']/Value")

                    # Condição: Primeira linha onde PESO ou PESOBALANCA não tem valor (texto vazio ou ausente)
                    is_empty = (not peso_val_elem or peso_val_elem[0].text is None or peso_val_elem[0].text.strip() == "") or \
                               (not balanca_val_elem or balanca_val_elem[0].text is None or balanca_val_elem[0].text.strip() == "")

                    if not update_realizado and is_empty:
                        logging.info(f"Encontrada primeira linha vazia na tabela '{tabela_id_alvo}'. Atualizando com novos pesos.")

                        # Função helper para atualizar ou criar campo/valor
                        def update_or_create_field_value(parent_fields, field_id, new_value):
                            field_elem = parent_fields.xpath(f"./Field[Id='{field_id}']")
                            if field_elem: # Campo existe
                                field_elem = field_elem[0]
                                value_elem = field_elem.find("./Value")
                                if value_elem is None: value_elem = etree.SubElement(field_elem, "Value")
                                value_elem.text = new_value
                            else: # Campo não existe, cria Field/Id/Value
                                field = etree.SubElement(parent_fields, "Field")
                                etree.SubElement(field, "Id").text = field_id
                                etree.SubElement(field, "Value").text = new_value

                        # Atualiza os campos nesta linha
                        update_or_create_field_value(fields_in_row, peso_field_id, peso_novo)
                        update_or_create_field_value(fields_in_row, pesobalanca_field_id, pesobalanca_novo)
                        update_or_create_field_value(fields_in_row, tstpeso_id_usado, tstpeso_valor_usado) # Garante que TST usado esteja lá

                        update_realizado = True
                        # NÃO DÊ BREAK se precisar retornar a tabela inteira

            if not update_realizado:
                logging.warning(f"Nenhuma linha vazia encontrada em '{tabela_id_alvo}' para preencher.")

            # Limpa atributos indesejados ANTES de adicionar
            for row_elem in tabela_element_original.xpath('.//Row'):
                 # Remove IsCurrentRow da resposta, pode confundir o cliente
                 if 'IsCurrentRow' in row_elem.attrib: del row_elem.attrib['IsCurrentRow']
                 # Muda Id para ID nos Fields
                 for field_elem in row_elem.xpath('.//Field/Id'): field_elem.tag = "ID"


            # Adiciona a TableField (agora modificada) à resposta
            fields_container.append(tabela_element_original) # Adiciona o elemento lxml modificado

        # --- Adiciona partes estáticas ---
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText")
        etree.SubElement(return_value, "Value").text = "58"

        # --- Serializa ---
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body
        logging.debug("XML de Resposta com Tabela MODIFICADA Gerado (UTF-16):\n%s", xml_str_final)
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.exception("Erro fatal ao gerar resposta com tabela modificada")
        return gerar_erro_xml_adaptado(f"Erro interno ao gerar resposta: {str(e)}", "Erro Servidor", 500)


# --- Rota Principal (Usando a Nova Função de Resposta) ---

def encaxotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /balanca_simulador_completo ---")
    # 1. Obtenção Robusta do XML
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
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml_adaptado("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair TSTPESO (da linha 'atual' - Current ou Primeira)
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído da linha 'atual': '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML com a Tabela COMPLETA Modificada
        # Passa os BYTES ORIGINAIS para a função de resposta poder re-parsear e modificar
        return gerar_resposta_com_tabela_modificada(
            xml_bytes_original=xml_data_bytes,
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id_usado=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /balanca_simulador_completo")
        return gerar_erro_xml_adaptado(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)