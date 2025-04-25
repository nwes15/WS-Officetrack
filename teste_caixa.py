from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO
from utils.gerar_erro import gerar_erro_xml 

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---
def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
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


def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    if not xml_bytes: return "0"
    try:
        parser = etree.XMLParser(recover=True); tree = etree.parse(BytesIO(xml_bytes), parser); root = tree.getroot()
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"; tabela_elements = root.xpath(xpath_tabela)
        if not tabela_elements: return "0"
        tabela_element = tabela_elements[0]; linha_alvo = None
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows: linha_alvo = current_rows[0]
        else:
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list: linha_alvo = primeira_linha_list[0]
        if linha_alvo is None: return "0"
        xpath_tstpeso = f".//Field[Id='{tstpeso_id_alvo}']/Value"; tstpeso_elements = linha_alvo.xpath(xpath_tstpeso)
        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None: value_text = value_text.strip(); return value_text if value_text in ["0", "1"] else "0"
        return "0"
    except Exception: logging.exception("Erro ao extrair TSTPESO"); return "0"

def gerar_valores_peso(tstpeso_valor, balanca):
    def formatar_numero(): return "{:.2f}".format(random.uniform(0.5, 500)).replace('.', ',')

    if tstpeso_valor == "0":
        valor = formatar_numero()
        return valor, valor
    else:
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca:
            pesobalanca = formatar_numero()
        return peso, pesobalanca

# --- Função de Resposta com lxml ---
def gerar_resposta_com_linhas_preservadas(xml_bytes, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera ResponseV2 preservando a estrutura original do XML,
    atualizando os campos na linha marcada como IsCurrentRow="True"
    e adicionando OverrideData=1 para todos os campos dessa linha,
    exceto para o campo EVFOTO
    """
    logging.debug(f"Gerando resposta preservando estrutura para balanca '{balanca_id}'")
    
    try:
        # Determina IDs
        tabela_id_resp = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_id_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_id_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
        evfoto_id_resp = "CX1EVFOTO" if balanca_id == "balanca1" else "CX2EVFOTO"
        
        # Parse do XML original
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        
        # Criar a estrutura base da resposta
        response = etree.Element("ResponseV2", nsmap={
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xsd': 'http://www.w3.org/2001/XMLSchema'
        })
        
        # Adicionar MessageV2
        message = etree.SubElement(response, "MessageV2")
        etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
        
        # Adicionar ReturnValueV2
        return_value = etree.SubElement(response, "ReturnValueV2")
        fields = etree.SubElement(return_value, "Fields")
        
        # Encontrar a tabela no XML original
        xpath_tabela = f".//TableField[ID='{tabela_id_resp}']"
        tabelas_originais = root.xpath(xpath_tabela)
        
        # Tente com "Id" se não encontrar com "ID"
        if not tabelas_originais:
            xpath_tabela = f".//TableField[Id='{tabela_id_resp}']"
            tabelas_originais = root.xpath(xpath_tabela)
        
        if tabelas_originais:
            # Copiar a tabela original
            tabela_original = tabelas_originais[0]
            tabela = etree.SubElement(fields, "TableField")
            
            # Adicionar ID da tabela
            etree.SubElement(tabela, "ID").text = tabela_id_resp
            
            # Adicionar OverrideData à tabela
            etree.SubElement(tabela, "OverrideData").text = "1"
            
            # Copiar as linhas
            rows = etree.SubElement(tabela, "Rows")
            
            # Processar cada linha da tabela original
            for row_original in tabela_original.xpath(".//Row"):
                row = etree.SubElement(rows, "Row")
                
                # Verificar se é a linha atual
                is_current = row_original.get("IsCurrentRow") == "True"
                if is_current:
                    row.set("IsCurrentRow", "True")
                
                # Adicionar campos
                row_fields = etree.SubElement(row, "Fields")
                
                # Processar campos com base em se é linha atual ou não
                if is_current:
                    # Para a linha atual, adicione todos os campos originais com OverrideData=1
                    # exceto para o campo EVFOTO
                    for field_original in row_original.xpath(".//Field"):
                        field = etree.SubElement(row_fields, "Field")
                        
                        # Obter ID do campo original
                        field_id = field_original.findtext("ID") or field_original.findtext("Id")
                        if field_id is not None:
                            etree.SubElement(field, "ID").text = field_id
                            
                            # Adicionar IsVisible se existir no original
                            is_visible = field_original.findtext("IsVisible")
                            if is_visible is not None:
                                etree.SubElement(field, "IsVisible").text = is_visible
                            
                            # Verificar se é o campo de foto (CX1EVFOTO ou CX2EVFOTO)
                            if field_id == evfoto_id_resp:
                                # Para o campo de foto, não adicionar OverrideData
                                # Apenas copiar o valor original se existir
                                value = field_original.findtext("Value")
                                if value is not None:
                                    etree.SubElement(field, "Value").text = value
                            else:
                                # Adicionar OverrideData=1 para todos os outros campos
                                etree.SubElement(field, "OverrideData").text = "1"
                                
                                # Define valor com base no campo
                                if field_id == tstpeso_id:
                                    # Campo TSTPESO - use o valor extraído
                                    etree.SubElement(field, "Value").text = tstpeso_valor_usado
                                elif field_id == peso_id_resp:
                                    # Campo PESO - use o novo valor gerado
                                    etree.SubElement(field, "Value").text = peso_novo
                                elif field_id == pesobalanca_id_resp:
                                    # Campo PESOBALANCA - use o novo valor gerado
                                    etree.SubElement(field, "Value").text = pesobalanca_novo
                                else:
                                    # Para todos os outros campos, mantenha o valor original
                                    value = field_original.findtext("Value")
                                    if value is not None:
                                        etree.SubElement(field, "Value").text = value
                    
                    # Adicionar o campo WS se ainda não existir
                    ws_fields = row_fields.xpath(".//Field[ID='WS' or Id='WS']")
                    if not ws_fields:
                        field = etree.SubElement(row_fields, "Field")
                        etree.SubElement(field, "ID").text = "WS"
                        etree.SubElement(field, "OverrideData").text = "1"
                        etree.SubElement(field, "IsVisible").text = "1"
                        etree.SubElement(field, "Value").text = "Pressione Lixeira para nova consulta"
                else:
                    # Para linhas não-atuais, copiar os campos originais sem OverrideData
                    for field_original in row_original.xpath(".//Field"):
                        field = etree.SubElement(row_fields, "Field")
                        
                        # Copiar o ID
                        id_value = field_original.findtext("ID") or field_original.findtext("Id")
                        if id_value is not None:
                            etree.SubElement(field, "ID").text = id_value
                        
                        # Copiar IsVisible se existir
                        is_visible = field_original.findtext("IsVisible")
                        if is_visible is not None:
                            etree.SubElement(field, "IsVisible").text = is_visible
                        
                        # Copiar o Value se existir
                        value = field_original.findtext("Value")
                        if value is not None:
                            etree.SubElement(field, "Value").text = value
        else:
            # Se não encontrou a tabela, criar uma nova com apenas a linha atual
            tabela = etree.SubElement(fields, "TableField")
            etree.SubElement(tabela, "ID").text = tabela_id_resp
            etree.SubElement(tabela, "OverrideData").text = "1"
            
            rows = etree.SubElement(tabela, "Rows")
            row = etree.SubElement(rows, "Row")
            row.set("IsCurrentRow", "True")
            
            row_fields = etree.SubElement(row, "Fields")
            
            # Campos básicos para a nova tabela
            # Campo TSTPESO
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = tstpeso_id
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "IsVisible").text = "1"
            etree.SubElement(field, "Value").text = tstpeso_valor_usado
            
            # Campo PESO
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = peso_id_resp
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "IsVisible").text = "1"
            etree.SubElement(field, "Value").text = peso_novo
            
            # Campo PESOBALANCA
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = pesobalanca_id_resp
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "IsVisible").text = "1"
            etree.SubElement(field, "Value").text = pesobalanca_novo
            
            # Campo EVFOTO (sem OverrideData)
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = evfoto_id_resp
            etree.SubElement(field, "OverrideData").text = "0"
            
            
            # Campo WS (mensagem)
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = "WS"
            etree.SubElement(field, "OverrideData").text = "0"
            etree.SubElement(field, "Value").text = "Pressione Lixeira para nova consulta"
        
        # Adicionar elementos restantes
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText")
        etree.SubElement(return_value, "Value").text = "17"
        
        # Gerar a string XML final
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body
        
        logging.debug("XML de Resposta preservando estrutura (UTF-16):\n%s", xml_str_final)
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")
        
    except Exception as e:
        logging.exception("Erro ao gerar resposta preservando estrutura")
        return gerar_erro_xml_padrao(f"Erro ao processar XML: {str(e)}", "Erro Processamento", 500)



def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    # 1. Obtenção Robusta do XML
    content_type = request.headers.get("Content-Type", "").lower()
    xml_data_str = None
    xml_data_bytes = None
    
    # Tenta obter o XML de várias fontes possíveis
    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form:
                xml_data_str = request.form.get(name)
                break
        if not xml_data_str and request.form:
            first_key = next(iter(request.form))
            xml_data_str = request.form.get(first_key)
        if xml_data_str:
            logging.info("XML obtido de request.form.")
    
    if not xml_data_str and request.data:
        try:
            xml_data_bytes = request.data
            xml_data_str = xml_data_bytes.decode('utf-8')
            logging.info("XML obtido de request.data (UTF-8).")
        except UnicodeDecodeError:
            try:
                xml_data_str = request.data.decode('latin-1')
                xml_data_bytes = request.data
                logging.info("XML obtido de request.data (Latin-1).")
            except UnicodeDecodeError:
                return gerar_erro_xml_padrao("Encoding inválido.", "Erro Encoding", 400)
    
    if not xml_data_bytes and xml_data_str:
        try:
            xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e:
            return gerar_erro_xml_padrao(f"Erro codificando form data: {e}", "Erro Encoding", 500)
    
    if not xml_data_bytes:
        return gerar_erro_xml_padrao("XML não encontrado.", "Erro Input", 400)
    
    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]:
            return gerar_erro_xml_padrao("Parâmetro 'balanca' inválido.", "Erro Param", 400)
        
        # 3. Extrair TSTPESO (da linha 'atual')
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído da linha 'atual': '{tstpeso_valor_extraido}'")
        
        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)
        
        # 5. Gerar Resposta XML preservando a estrutura original
        return gerar_resposta_com_linhas_preservadas(
            xml_bytes=xml_data_bytes,
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )
    
    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml_padrao(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)