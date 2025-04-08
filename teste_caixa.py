from flask import Flask, request, Response
from lxml import etree # Usar lxml
import random
import logging
from io import BytesIO # Usar BytesIO com lxml


logging.basicConfig(level=logging.DEBUG) # DEBUG para detalhes


def gerar_erro(mensagem, status_code=400):
    """Retorna uma resposta XML de erro simples (UTF-8)."""
    logging.error(f"Gerando erro: {mensagem}")
    xml_erro = f"<Error><Message>{mensagem}</Message></Error>"
    return Response(xml_erro.encode('utf-8'), status=status_code, content_type='application/xml; charset=utf-8')

def extrair_dados_estruturados_xml(xml_data_bytes):
    """Extrai dados do XML preservando a estrutura das tabelas."""
    # (Função mantida da versão anterior com lxml)
    extracted_data = {"metadata": {}, "top_level_fields": {}, "table_fields": {}}
    try:
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        tree = etree.parse(BytesIO(xml_data_bytes), parser)
        root = tree.getroot()
        main_fields_container = root.find("./Fields")
        if main_fields_container is not None:
            for element in main_fields_container.iterchildren():
                element_id = element.findtext("Id") # Usa 'Id' como no input
                if not element_id: continue
                if element.tag == "Field":
                    extracted_data["top_level_fields"][element_id] = element.findtext("Value", default="").strip()
                elif element.tag == "TableField":
                    table_rows_data = []
                    rows_container = element.find("./Rows")
                    if rows_container is not None:
                        for row_idx, row in enumerate(rows_container.findall("./Row")):
                            row_fields_data = {'_attributes': dict(row.attrib), '_row_index': row_idx}
                            nested_fields_container = row.find("./Fields")
                            if nested_fields_container is not None:
                                for nested_field in nested_fields_container.findall("./Field"):
                                    nested_field_id = nested_field.findtext("Id")
                                    if nested_field_id:
                                        row_fields_data[nested_field_id] = nested_field.findtext("Value", default="").strip()
                            if len(row_fields_data) > 2: table_rows_data.append(row_fields_data)
                        extracted_data["table_fields"][element_id] = table_rows_data
        return extracted_data
    except Exception as e:
        logging.exception("Erro ao processar XML na extração estruturada")
        return None

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

def adicionar_campo_xml_com_ID(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field>."""
    # *** Modificado para usar ID maiúsculo na resposta ***
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id # ID maiúsculo
    etree.SubElement(field, "Value").text = value if value is not None else ""

# --- Função de Resposta com Linhas Anteriores + Atualizada ---
def gerar_resposta_com_linhas_relevantes(extracted_data, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera ResponseV2 incluindo linhas preenchidas ANTES da primeira vazia
    e a primeira linha vazia AGORA preenchida, com apenas 3 campos essenciais.
    """
    logging.debug(f"Gerando resposta com linhas relevantes para balanca '{balanca_id}'")
    # Namespaces como no exemplo de retorno desejado
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    # Raiz SEM namespace padrão explícito
    response = etree.Element("ResponseV2", nsmap=nsmap)

    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."

    return_value = etree.SubElement(response, "ReturnValueV2")
    response_fields_container = etree.SubElement(return_value, "Fields")

    # --- Identificadores ---
    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    # tstpeso_id já vem como argumento ('TSTPESO1' ou 'TSTPESO2')

    original_rows_data = extracted_data.get("table_fields", {}).get(tabela_id_alvo, [])

    if not original_rows_data:
        logging.warning(f"Tabela alvo '{tabela_id_alvo}' não encontrada ou vazia. Retornando estrutura vazia.")
        # Opcionalmente adicionar campos simples como fallback?
    else:
        logging.debug(f"Processando linhas da tabela '{tabela_id_alvo}' para resposta...")
        response_table = etree.SubElement(response_fields_container, "TableField")
        # Usa 'ID' maiúsculo na resposta como no exemplo
        etree.SubElement(response_table, "ID").text = tabela_id_alvo

        response_rows_container = etree.SubElement(response_table, "Rows")
        update_realizado = False

        for row_data in original_rows_data:
            # Pega os valores originais dos campos chave desta linha
            original_peso = row_data.get(peso_field_id, "")
            original_pesobalanca = row_data.get(pesobalanca_field_id, "")
            original_tstpeso = row_data.get(tstpeso_id, "0") # Default se ausente

            # Determina se a linha original estava preenchida (ambos pesos presentes)
            is_originally_filled = original_peso != "" and original_pesobalanca != ""

            # Determina se esta é a primeira linha que encontramos que estava vazia
            is_first_empty_to_fill = (
                not update_realizado and
                (original_peso == "" or original_pesobalanca == "")
            )

            row_to_add = None # Elemento <Row> a ser adicionado na resposta

            if is_originally_filled and not update_realizado:
                # Inclui linha original preenchida (ANTES da atualização)
                logging.debug(f"  Incluindo linha original preenchida (índice {row_data.get('_row_index','?')})")
                row_to_add = etree.SubElement(response_rows_container, "Row")
                # Copia atributos se necessário (ex: IsCurrentRow, embora talvez não devesse ir na resposta?)
                # for attr, val in row_data.get('_attributes', {}).items(): row_to_add.set(attr, val)
                fields_in_row = etree.SubElement(row_to_add, "Fields")
                # Adiciona apenas os 3 campos essenciais com valores ORIGINAIS
                adicionar_campo_xml_com_ID(fields_in_row, tstpeso_id, original_tstpeso)
                adicionar_campo_xml_com_ID(fields_in_row, peso_field_id, original_peso)
                adicionar_campo_xml_com_ID(fields_in_row, pesobalanca_field_id, original_pesobalanca)

            elif is_first_empty_to_fill:
                # Inclui a linha que estava vazia, AGORA preenchida com novos valores
                logging.debug(f"  Preenchendo e incluindo primeira linha vazia (índice {row_data.get('_row_index','?')})")
                row_to_add = etree.SubElement(response_rows_container, "Row")
                # Copia atributos se necessário
                # for attr, val in row_data.get('_attributes', {}).items(): row_to_add.set(attr, val)
                fields_in_row = etree.SubElement(row_to_add, "Fields")
                # Adiciona os 3 campos essenciais com valores NOVOS/CALCULADOS
                adicionar_campo_xml_com_ID(fields_in_row, tstpeso_id, tstpeso_valor_usado) # O TSTPESO que foi USADO
                adicionar_campo_xml_com_ID(fields_in_row, peso_field_id, peso_novo)
                adicionar_campo_xml_com_ID(fields_in_row, pesobalanca_field_id, pesobalanca_novo)
                update_realizado = True # Marca que já fizemos a atualização

            # Se a linha for posterior à atualizada (update_realizado == True),
            # ou se estava vazia mas não era a primeira, ela é ignorada e não adicionada à resposta.

            # Se row_to_add foi criado, ele já está adicionado a response_rows_container

        if not update_realizado:
             logging.warning(f"Nenhuma linha vazia encontrada em '{tabela_id_alvo}' para preencher.")

    # --- Adicionar partes estáticas da resposta ---
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText") # Vazio
    etree.SubElement(return_value, "Value").text = "58" # Fixo

    # --- Serializar com UTF-16 e declaração XML ---
    xml_bytes = etree.tostring(response, encoding="utf-16", xml_declaration=True, pretty_print=True)
    logging.debug("XML de Resposta com Linhas Relevantes Gerado (UTF-16):\n%s", xml_bytes.decode('utf-16', errors='ignore'))
    return xml_bytes, 'application/xml; charset=utf-16'



def encaxotar_v2():
    logging.info(f"Recebida requisição {request.method} para /funcao_unica_lxml_v2")
    # 1. Validações Iniciais (Content-Type, Body, Parâmetro balanca)
    if not request.data or 'xml' not in (request.content_type or '').lower():
         return gerar_erro("Requisição inválida. Content-Type XML e corpo são necessários.", 400)
    balanca = request.args.get('balanca', 'balanca1').lower()
    if balanca not in ["balanca1", "balanca2"]:
        return gerar_erro("Parâmetro 'balanca' inválido na URL.")

    try:
        xml_data_bytes = request.data

        # 2. Extrair Estrutura Completa
        extracted_data = extrair_dados_estruturados_xml(xml_data_bytes)
        if extracted_data is None:
            return gerar_erro("Falha ao processar estrutura XML de entrada.")

        # 3. Determinar TSTPESO (da linha relevante da tabela alvo)
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_usado = "0" # Default

        tabela_alvo_data = extracted_data.get("table_fields", {}).get(tabela_id_a_usar, [])
        if tabela_alvo_data:
            linha_alvo_para_tstpeso = None
            # Prioriza CurrentRow para buscar TSTPESO
            for row in tabela_alvo_data:
                 if row.get('_attributes', {}).get('IsCurrentRow', '').lower() == 'true':
                      linha_alvo_para_tstpeso = row; break
            # Senão, usa a primeira linha
            if linha_alvo_para_tstpeso is None and tabela_alvo_data:
                 linha_alvo_para_tstpeso = tabela_alvo_data[0]

            if linha_alvo_para_tstpeso:
                tstpeso_valor_usado = linha_alvo_para_tstpeso.get(tstpeso_id_a_usar, "0")
            else:
                logging.warning(f"Nenhuma linha encontrada em {tabela_id_a_usar} para obter TSTPESO.")
        else:
            logging.warning(f"Tabela {tabela_id_a_usar} não encontrada/vazia para obter TSTPESO.")

        # Validação final do TSTPESO a ser usado
        if tstpeso_valor_usado not in ["0", "1"]:
            logging.warning(f"Valor TSTPESO inválido '{tstpeso_valor_usado}', usando padrão '0'.")
            tstpeso_valor_usado = "0"

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_usado, balanca)

        # 5. Gerar Resposta XML com Linhas Relevantes
        # Passa os dados extraídos COMPLETOS para a função de resposta
        xml_resposta_bytes, content_type_resp = gerar_resposta_com_linhas_relevantes(
            extracted_data, peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar, tstpeso_valor_usado
        )
        return Response(xml_resposta_bytes, content_type=content_type_resp)

    except Exception as e:
        logging.exception("Erro fatal na rota /funcao_unica_lxml_v2")
        return gerar_erro(f"Erro interno inesperado no servidor: {str(e)}", 500)