from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---

def gerar_erro_xml_adaptado(mensagem, short_text="Erro", status_code=400):
    """Gera uma resposta de erro padronizada em XML"""
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def extrair_linha_alvo_e_tstpeso_v2(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """
    Encontra a linha alvo (Current ou Primeira) e extrai TSTPESO
    """
    if not xml_bytes: 
        logging.error("extrair_linha_alvo_v2 recebeu xml_bytes vazio.")
        return None, None
    
    try:
        logging.debug(f"--- Iniciando extrair_linha_alvo_v2 para Tabela '{tabela_id_alvo}', Campo '{tstpeso_id_alvo}' ---")
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()

        # Busca pela tabela (case insensitive para maior compatibilidade)
        xpath_tabela = f".//TableField[translate(Id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{tabela_id_alvo.lower()}']"
        tabela_elements = root.xpath(xpath_tabela)
        
        if not tabela_elements: 
            logging.warning(f"Tabela '{tabela_id_alvo}' NÃO encontrada.")
            return None, None
            
        tabela_element = tabela_elements[0]

        # Busca pela linha alvo
        linha_alvo_element = None
        linha_alvo_info = "Nenhuma"
        
        # 1. Tenta IsCurrentRow="True"
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows: 
            linha_alvo_element = current_rows[0]
            linha_alvo_info = "IsCurrentRow='True'"
        else: 
            # 2. Fallback para primeira linha
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list: 
                linha_alvo_element = primeira_linha_list[0]
                linha_alvo_info = "Primeira Linha"

        if linha_alvo_element is None: 
            logging.warning(f"Nenhuma linha encontrada em '{tabela_id_alvo}'.")
            return None, None
            
        logging.info(f"Linha Alvo encontrada: {linha_alvo_info}")

        # 3. Extrai o TSTPESO da linha_alvo_element (case insensitive)
        tstpeso_valor = "0"  # Default
        xpath_tstpeso = f".//Field[translate(Id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{tstpeso_id_alvo.lower()}']/Value"
        tstpeso_elements = linha_alvo_element.xpath(xpath_tstpeso)
        
        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None:
                value_text = value_text.strip()
                if value_text in ["0", "1"]: 
                    tstpeso_valor = value_text
                else: 
                    logging.warning(f"Valor TSTPESO inválido '{value_text}'. Usando '0'.")
            else: 
                logging.warning(f"Tag <Value> TSTPESO vazia. Usando '0'.")
        else: 
            logging.warning(f"Campo TSTPESO '{tstpeso_id_alvo}' não encontrado na linha. Usando '0'.")

        logging.info(f"TSTPESO extraído da linha alvo: '{tstpeso_valor}'")
        return tstpeso_valor, linha_alvo_element

    except Exception as e:
        logging.exception("Erro EXCEPCIONAL ao extrair linha alvo e TSTPESO v2")
        return None, None


def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera valores de peso aleatórios para balança"""
    def formatar_numero(): 
        return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    
    if tstpeso_valor == "0": 
        valor = formatar_numero()
        return valor, valor
    else: 
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca: 
            pesobalanca = formatar_numero()
        return peso, pesobalanca


# --- Função de Resposta SIMPLIFICADA: Cria uma resposta básica ---
def gerar_resposta_final_corrigida(peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado, xml_bytes):
    """
    Preserva exatamente a estrutura original do XML,
    atualizando apenas a linha com IsCurrentRow="True"
    """
    logging.debug(f"Gerando resposta com estrutura preservada para balanca '{balanca_id}'")
    try:
        # Parse do XML original para preservar sua estrutura
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root_original = tree.getroot()
        
        # Criar resposta com mesmo formato
        nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        response = etree.Element("ResponseV2", nsmap=nsmap)
        message = etree.SubElement(response, "MessageV2")
        etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
        return_value = etree.SubElement(response, "ReturnValueV2")
        fields_container = etree.SubElement(return_value, "Fields")
        
        # Identificar tabela e campos corretos
        tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
        
        # Obter a tabela original para replicar exatamente sua estrutura
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"  # Id minúsculo para input
        tabela_elements = root_original.xpath(xpath_tabela)
        
        if tabela_elements:
            tabela_original = tabela_elements[0]
            
            # Criar a TableField na resposta
            response_table = etree.SubElement(fields_container, "TableField")
            etree.SubElement(response_table, "ID").text = tabela_id_alvo  # ID Maiúsculo
            
            # Criar Rows
            response_rows = etree.SubElement(response_table, "Rows")
            
            # Replicar exatamente as linhas originais
            rows_original = tabela_original.xpath(".//Row")
            
            for row_original in rows_original:
                is_current = row_original.get("IsCurrentRow") == "True"
                
                # Copiar todos os atributos da linha original
                attrs = dict(row_original.attrib)
                response_row = etree.SubElement(response_rows, "Row", **attrs)
                
                # Adicionar Fields
                row_fields = etree.SubElement(response_row, "Fields")
                
                # Se esta é a linha marcada com IsCurrentRow="True", atualizar campos
                if is_current:
                    # Adicionar os campos atualizados
                    adicionar_campo_com_ID_resposta(row_fields, tstpeso_id, tstpeso_valor_usado)
                    adicionar_campo_com_ID_resposta(row_fields, peso_field_id, peso_novo)
                    adicionar_campo_com_ID_resposta(row_fields, pesobalanca_field_id, pesobalanca_novo)
                    
                    # Preservar outros campos originais que não são os 3 que atualizamos
                    for field_original in row_original.xpath(".//Field"):
                        field_id_elem = field_original.find("Id")
                        if field_id_elem is not None:
                            field_id = field_id_elem.text
                            if field_id.upper() not in [tstpeso_id.upper(), peso_field_id.upper(), pesobalanca_field_id.upper()]:
                                value_elem = field_original.find("Value")
                                value = value_elem.text if value_elem is not None and value_elem.text else ""
                                adicionar_campo_com_ID_resposta(row_fields, field_id.upper(), value)
                else:
                    # Preservar todos os campos originais como estavam
                    for field_original in row_original.xpath(".//Field"):
                        field_id_elem = field_original.find("Id")
                        if field_id_elem is not None:
                            field_id = field_id_elem.text
                            value_elem = field_original.find("Value")
                            value = value_elem.text if value_elem is not None and value_elem.text else ""
                            adicionar_campo_com_ID_resposta(row_fields, field_id.upper(), value)
        else:
            # Fallback se não encontrar a tabela (caso raro)
            response_table = etree.SubElement(fields_container, "TableField")
            etree.SubElement(response_table, "ID").text = tabela_id_alvo
            response_rows = etree.SubElement(response_table, "Rows")
            response_row = etree.SubElement(response_rows, "Row", IsCurrentRow="True")
            row_fields = etree.SubElement(response_row, "Fields")
            adicionar_campo_com_ID_resposta(row_fields, tstpeso_id, tstpeso_valor_usado)
            adicionar_campo_com_ID_resposta(row_fields, peso_field_id, peso_novo)
            adicionar_campo_com_ID_resposta(row_fields, pesobalanca_field_id, pesobalanca_novo)
        
        # Partes estáticas
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText")
        etree.SubElement(return_value, "Value").text = "58"
        
        # Serialização
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body
        logging.debug("XML de Resposta com Estrutura Preservada (UTF-16, resumo):\n%s", xml_str_final[:500])
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")
    
    except Exception as e:
        logging.exception("Erro ao gerar resposta final")
        return gerar_erro_xml_adaptado(f"Erro ao gerar resposta final: {str(e)}", "Erro Processamento", 500)


def adicionar_campo_com_ID_resposta(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field> para a RESPOSTA."""
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id  # ID Maiúsculo
    etree.SubElement(field, "Value").text = value if value is not None else ""



def encaxotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /simulador_balanca_corrigido ---")
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
        if balanca not in ["balanca1", "balanca2"]: 
            return gerar_erro_xml_adaptado("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair TSTPESO e a Linha Alvo (usando a v2)
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        logging.debug(f"Chamando extrair_linha_alvo_e_tstpeso_v2(tabela='{tabela_id_a_usar}', campo='{tstpeso_id_a_usar}')")
        tstpeso_valor_extraido, _ = extrair_linha_alvo_e_tstpeso_v2(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)

        # Verifica se a extração falhou (embora a função já retorne '0' como default)
        if tstpeso_valor_extraido is None: # Checagem extra de segurança
             return gerar_erro_xml_adaptado("Falha ao processar linha/TSTPESO no XML.", "Erro XML Proc")

        logging.info(f"TSTPESO extraído da linha alvo: '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML Final PRESERVANDO ESTRUTURA ORIGINAL
        logging.debug(f"Chamando gerar_resposta_final_corrigida com preservação de estrutura...")
        return gerar_resposta_final_corrigida(
            peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar, 
            tstpeso_valor_extraido, xml_data_bytes
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /simulador_balanca_corrigido")
        return gerar_erro_xml_adaptado(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)