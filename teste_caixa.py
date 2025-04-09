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
        return "{:.2f}".format(random.uniform(0.5, 500)).replace('.', ',')
    
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
    Preserva exatamente a estrutura original do XML e atualiza APENAS os 3 campos
    na linha com IsCurrentRow="True", garantindo que não sejam criadas linhas extras.
    """
    logging.debug(f"Gerando resposta com estrutura exatamente preservada para balanca '{balanca_id}'")
    try:
        # Parse do XML original
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        
        # Identificar tabela e campos para esta balança
        tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
        
        # Localizar a tabela no XML original
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"  # Id minúsculo no input
        tabelas = root.xpath(xpath_tabela)
        
        if not tabelas:
            logging.warning(f"Tabela '{tabela_id_alvo}' não encontrada no XML original.")
            return gerar_erro_xml_adaptado(f"Tabela '{tabela_id_alvo}' não encontrada.", "XML Inválido", 400)
        
        tabela = tabelas[0]
        
        # Localizar a linha com IsCurrentRow="True" ou usar a primeira se não encontrar
        row_atual = None
        rows = tabela.xpath(".//Row")
        for row in rows:
            if row.get("IsCurrentRow") == "True":
                row_atual = row
                break
        
        # Se não encontrou nenhuma linha com IsCurrentRow, use a primeira
        if row_atual is None and rows:
            row_atual = rows[0]
            
        if row_atual is None:
            logging.warning("Nenhuma linha encontrada na tabela.")
            return gerar_erro_xml_adaptado("Nenhuma linha encontrada na tabela.", "XML Inválido", 400)
            
        # Atualizar os campos na linha atual
        # 1. TSTPESO
        xpath_tstpeso = f".//Field[Id='{tstpeso_id}']/Value"  # Id minúsculo no input
        tstpeso_elements = row_atual.xpath(xpath_tstpeso)
        if tstpeso_elements:
            tstpeso_elements[0].text = tstpeso_valor_usado
        else:
            # Se não encontrar, criar o campo
            fields = row_atual.find(".//Fields")
            if fields is not None:
                field = etree.SubElement(fields, "Field")
                etree.SubElement(field, "Id").text = tstpeso_id
                etree.SubElement(field, "Value").text = tstpeso_valor_usado
                
        # 2. PESO
        xpath_peso = f".//Field[Id='{peso_field_id.lower()}']/Value"  # Id minúsculo no input
        peso_elements = row_atual.xpath(xpath_peso)
        if peso_elements:
            peso_elements[0].text = peso_novo
        else:
            # Se não encontrar, criar o campo
            fields = row_atual.find(".//Fields")
            if fields is not None:
                field = etree.SubElement(fields, "Field")
                etree.SubElement(field, "Id").text = peso_field_id.lower()
                etree.SubElement(field, "Value").text = peso_novo
                
        # 3. PESOBALANCA
        xpath_pesobalanca = f".//Field[Id='{pesobalanca_field_id.lower()}']/Value"  # Id minúsculo no input
        pesobalanca_elements = row_atual.xpath(xpath_pesobalanca)
        if pesobalanca_elements:
            pesobalanca_elements[0].text = pesobalanca_novo
        else:
            # Se não encontrar, criar o campo
            fields = row_atual.find(".//Fields")
            if fields is not None:
                field = etree.SubElement(fields, "Field")
                etree.SubElement(field, "Id").text = pesobalanca_field_id.lower()
                etree.SubElement(field, "Value").text = pesobalanca_novo
        
        # Definir o formato da resposta
        response = etree.Element("ResponseV2", nsmap={'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 
                                                   'xsd': 'http://www.w3.org/2001/XMLSchema'})
        message = etree.SubElement(response, "MessageV2")
        etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
        
        return_value = etree.SubElement(response, "ReturnValueV2")
        fields_container = etree.SubElement(return_value, "Fields")
        
        # Adicionar uma cópia exata da tabela MODIFICADA à resposta
        # Convertendo IDs minúsculos para maiúsculos na resposta
        new_table = etree.SubElement(fields_container, "TableField")
        # Usar ID maiúsculo na resposta
        etree.SubElement(new_table, "ID").text = tabela_id_alvo.upper()
        
        # Copiar Rows e cada Row mantendo atributos
        new_rows = etree.SubElement(new_table, "Rows")
        for row_original in tabela.xpath(".//Row"):
            attrs = {k:v for k,v in row_original.attrib.items()}
            new_row = etree.SubElement(new_rows, "Row", **attrs)
            
            # Copiar Fields
            orig_fields = row_original.find(".//Fields")
            if orig_fields is not None:
                new_fields = etree.SubElement(new_row, "Fields")
                
                # Copiar cada Field convertendo Id->ID
                for field_original in orig_fields.findall("Field"):
                    new_field = etree.SubElement(new_fields, "Field")
                    
                    # Converter Id para ID na resposta
                    id_elem = field_original.find("Id")
                    if id_elem is not None:
                        etree.SubElement(new_field, "ID").text = id_elem.text.upper()
                    
                    # Copiar Value
                    value_elem = field_original.find("Value")
                    if value_elem is not None:
                        etree.SubElement(new_field, "Value").text = value_elem.text
        
        # Partes estáticas
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText")
        etree.SubElement(return_value, "Value").text = "58"
        
        # Serialização
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body
        
        logging.debug("XML de Resposta (UTF-16, início):\n%s", xml_str_final[:500])
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")
        
    except Exception as e:
        logging.exception("Erro fatal ao gerar resposta XML")
        return gerar_erro_xml_adaptado(f"Erro ao gerar resposta: {str(e)}", "Erro Interno", 500)

def adicionar_campo_com_ID_resposta(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field> para a RESPOSTA."""
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id  # ID Maiúsculo
    etree.SubElement(field, "Value").text = value if value is not None else ""



def encaixotar_v2():
    xml_data = request.data
    root = etree.fromstring(xml_data)

    table_field = root.find('.//TableField')
    if table_field is None:
        return Response("Nenhuma tabela encontrada", status=400)

    nome_tabela = table_field.attrib.get('Name', 'UnknownTable')
    linhas = table_field.findall('Row')

    nova_table = etree.Element('TableField', Name=nome_tabela)

    for linha in linhas:
        nova_row = etree.Element('Row', linha.attrib)

        # Copia os campos da linha
        for field in linha.findall('Field'):
            novo_field = etree.SubElement(nova_row, 'Field', Name=field.attrib['Name'])
            novo_field.text = field.text

        nova_table.append(nova_row)

        # Quando encontrar a linha atual, preenche os pesos e para
        if linha.attrib.get('IsCurrentRow') == 'True':
            for field in nova_row.findall('Field'):
                nome = field.attrib['Name'].upper()
                if nome in ['CX1PESO', 'CX2PESO']:
                    field.text = gerar_valores_peso()
                elif nome in ['CX1PESOBALANCA', 'CX2PESOBALANCA']:
                    field.text = gerar_valores_peso()
            break  # parar após a linha atual

    resposta = etree.Element('Response')
    resposta.append(nova_table)

    xml_final = etree.tostring(resposta, encoding='utf-16', xml_declaration=True)

    return Response(xml_final, mimetype='application/xml; charset=utf-16')