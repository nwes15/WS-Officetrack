from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---

def gerar_erro_xml_adaptado(mensagem, short_text="Erro", status_code=400):
    # (Mantida como na versão anterior)
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo_com_ID_resposta(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field> para a RESPOSTA."""
    # Garante ID maiúsculo na resposta
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id # ID Maiúsculo
    etree.SubElement(field, "Value").text = value if value is not None else ""

# --- Função de Extração MODIFICADA (com fallback e retorno de elemento) ---
def extrair_linha_alvo_e_tstpeso_v2(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """
    Encontra a linha alvo (Current ou Primeira), extrai TSTPESO e retorna
    (tstpeso_valor, elemento_linha_alvo) ou (None, None).
    """
    if not xml_bytes: logging.error("extrair_linha_alvo_v2 recebeu xml_bytes vazio."); return None, None
    try:
        logging.debug(f"--- Iniciando extrair_linha_alvo_v2 para Tabela '{tabela_id_alvo}', Campo '{tstpeso_id_alvo}' ---")
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()

        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']" # Id minúsculo input
        tabela_elements = root.xpath(xpath_tabela)
        if not tabela_elements: logging.warning(f"Tabela '{tabela_id_alvo}' NÃO encontrada."); return None, None
        tabela_element = tabela_elements[0]

        linha_alvo_element = None
        linha_alvo_info = "Nenhuma"
        # 1. Tenta IsCurrentRow="True"
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows: linha_alvo_element = current_rows[0]; linha_alvo_info = "IsCurrentRow='True'"
        else: # 2. Fallback para primeira linha
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list: linha_alvo_element = primeira_linha_list[0]; linha_alvo_info = "Primeira Linha"

        if linha_alvo_element is None: logging.warning(f"Nenhuma linha encontrada em '{tabela_id_alvo}'."); return None, None
        logging.info(f"Linha Alvo encontrada: {linha_alvo_info}")

        # 3. Extrai o TSTPESO da linha_alvo_element
        tstpeso_valor = "0" # Default
        xpath_tstpeso = f".//Field[Id='{tstpeso_id_alvo}']/Value" # Id minúsculo input
        tstpeso_elements = linha_alvo_element.xpath(xpath_tstpeso)
        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None:
                value_text = value_text.strip()
                if value_text in ["0", "1"]: tstpeso_valor = value_text
                else: logging.warning(f"Valor TSTPESO inválido '{value_text}'. Usando '0'.")
            else: logging.warning(f"Tag <Value> TSTPESO vazia. Usando '0'.")
        else: logging.warning(f"Campo TSTPESO '{tstpeso_id_alvo}' não encontrado na linha. Usando '0'.")

        logging.info(f"TSTPESO extraído da linha alvo: '{tstpeso_valor}'")
        # Retorna o valor e o ELEMENTO lxml da linha alvo
        return tstpeso_valor, linha_alvo_element

    except Exception as e:
        logging.exception("Erro EXCEPCIONAL ao extrair linha alvo e TSTPESO v2"); return None, None


def gerar_valores_peso(tstpeso_valor, balanca_id):
    # (Função mantida)
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); 
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca


# --- NOVA Função para obtenção/criação da tabela no XML de entrada ---
def obter_ou_criar_tabela(xml_bytes, tabela_id):
    """
    Localiza ou cria a tabela no XML de entrada.
    Retorna (tree, root, tabela_element)
    """
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        
        # Procurar pela tabela existente
        xpath_tabela = f".//TableField[Id='{tabela_id}']"  # Id minúsculo input
        tabela_elements = root.xpath(xpath_tabela)
        
        if tabela_elements:
            return tree, root, tabela_elements[0]
        
        # Se não encontrou a tabela, precisamos criá-la no XML
        # Primeiro vamos procurar o Fields container
        fields_container = root.xpath(".//Fields")
        if not fields_container:
            # Se não tiver container Fields, criar na estrutura básica
            return_value = root.xpath(".//ReturnValueV2")
            if not return_value:
                # Criar toda estrutura básica se não existir
                return_value = etree.SubElement(root, "ReturnValueV2")
            else:
                return_value = return_value[0]
            fields_container = etree.SubElement(return_value, "Fields")
        else:
            fields_container = fields_container[0]
        
        # Criar a tabela
        tabela_element = etree.SubElement(fields_container, "TableField")
        etree.SubElement(tabela_element, "Id").text = tabela_id
        etree.SubElement(tabela_element, "Rows")
        
        return tree, root, tabela_element
        
    except Exception as e:
        logging.exception(f"Erro ao obter/criar tabela {tabela_id}")
        return None, None, None

# --- NOVA Função: Processar tabela XML e adicionar/atualizar linha ---
def processar_tabela_xml(xml_bytes, tabela_id, peso_field_id, pesobalanca_field_id, tstpeso_id, peso_novo, pesobalanca_novo, tstpeso_valor):
    """
    Processa a tabela XML:
    1. Mantém linhas existentes
    2. Atualiza a linha atual (IsCurrentRow="True") ou cria uma nova
    3. Retorna XML processado
    """
    try:
        tree, root, tabela_element = obter_ou_criar_tabela(xml_bytes, tabela_id)
        if tabela_element is None:
            raise Exception(f"Não foi possível localizar ou criar a tabela {tabela_id}")
        
        # Obter elemento Rows (deve existir)
        rows_elements = tabela_element.xpath("./Rows")
        if not rows_elements:
            rows_element = etree.SubElement(tabela_element, "Rows")
        else:
            rows_element = rows_elements[0]
            
        # Verificar se existe linha atual (IsCurrentRow="True")
        current_rows = rows_element.xpath("./Row[@IsCurrentRow='True']")
        
        if current_rows:
            # Atualizar a linha atual existente
            linha_atual = current_rows[0]
            logging.info("Atualizando linha atual existente com IsCurrentRow=True")
        else:
            # Criar nova linha e marcar como atual
            linha_atual = etree.SubElement(rows_element, "Row")
            linha_atual.set("IsCurrentRow", "True")
            fields_element = etree.SubElement(linha_atual, "Fields")
            logging.info("Criando nova linha com IsCurrentRow=True")
        
        # Garantir que a linha tem elemento Fields
        fields_elements = linha_atual.xpath("./Fields")
        if not fields_elements:
            fields_element = etree.SubElement(linha_atual, "Fields")
        else:
            fields_element = fields_elements[0]
        
        # Atualizar/criar campos na linha atual
        # 1. TSTPESO
        atualizar_ou_criar_campo(fields_element, tstpeso_id, tstpeso_valor)
        # 2. PESO
        atualizar_ou_criar_campo(fields_element, peso_field_id, peso_novo)
        # 3. PESOBALANCA
        atualizar_ou_criar_campo(fields_element, pesobalanca_field_id, pesobalanca_novo)
        
        # Serializar resposta
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(root, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body
        logging.debug("XML de Resposta Processado (UTF-16):\n%s", xml_str_final)
        
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")
        
    except Exception as e:
        logging.exception("Erro ao processar tabela XML")
        return gerar_erro_xml_adaptado(f"Erro ao processar tabela XML: {str(e)}", "Erro XML Proc", 500)

def atualizar_ou_criar_campo(fields_element, field_id, value):
    """
    Atualiza o valor de um campo existente ou cria um novo na estrutura Fields
    """
    # Procurar pelo campo (CASE INSENSITIVE para compatibilidade)
    field_elements = fields_element.xpath(f"./Field[translate(Id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{field_id.lower()}']")
    
    if field_elements:
        # Atualizar campo existente
        field_element = field_elements[0]
        value_elements = field_element.xpath("./Value")
        if value_elements:
            value_elements[0].text = value
        else:
            etree.SubElement(field_element, "Value").text = value
    else:
        # Criar novo campo
        field_element = etree.SubElement(fields_element, "Field")
        etree.SubElement(field_element, "Id").text = field_id  # Manter case original
        etree.SubElement(field_element, "Value").text = value

# --- NOVA Função de Resposta (mantendo estrutura do XML original) ---
def gerar_resposta_final_preservando_estrutura(xml_bytes, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera resposta XML mantendo a estrutura original e apenas atualizando/adicionando a linha necessária
    """
    tabela_id_a_usar = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    
    return processar_tabela_xml(
        xml_bytes, 
        tabela_id_a_usar,
        peso_field_id,
        pesobalanca_field_id,
        tstpeso_id,
        peso_novo,
        pesobalanca_novo,
        tstpeso_valor_usado
    )


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
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml_adaptado("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair TSTPESO e a Linha Alvo (usando a v2)
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        logging.debug(f"Chamando extrair_linha_alvo_e_tstpeso_v2(tabela='{tabela_id_a_usar}', campo='{tstpeso_id_a_usar}')")
        tstpeso_valor_extraido, _ = extrair_linha_alvo_e_tstpeso_v2(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)

        # Verifica se a extração falhou (embora a função já retorne '0' como default)
        if tstpeso_valor_extraido is None: 
            tstpeso_valor_extraido = "0"  # Fallback seguro
            logging.warning("Usando TSTPESO='0' como fallback após falha na extração")

        logging.info(f"TSTPESO a ser usado: '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML Final NOVA (preservando estrutura)
        logging.debug(f"Chamando gerar_resposta_final_preservando_estrutura(...)")
        return gerar_resposta_final_preservando_estrutura(
            xml_data_bytes, peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar, tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /simulador_balanca_corrigido")
        return gerar_erro_xml_adaptado(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)
