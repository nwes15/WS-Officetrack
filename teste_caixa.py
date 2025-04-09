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
def gerar_resposta_minima_com_valores(peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera uma resposta XML básica mas funcional com os valores de peso necessários
    """
    logging.debug(f"Gerando resposta MÍNIMA para balanca '{balanca_id}'")
    
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    
    # ReturnValue
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields_container = etree.SubElement(return_value, "Fields")
    
    # Determina IDs com base na balança
    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    
    # Cria a TableField na resposta
    table_field = etree.SubElement(fields_container, "TableField")
    etree.SubElement(table_field, "ID").text = tabela_id_alvo  # ID Maiúsculo
    
    # Cria Rows e Row com IsCurrentRow
    rows = etree.SubElement(table_field, "Rows")
    row = etree.SubElement(rows, "Row")
    row.set("IsCurrentRow", "True")
    
    # Adiciona Fields dentro da Row
    row_fields = etree.SubElement(row, "Fields")
    
    # Adiciona os 3 campos essenciais
    adicionar_campo_com_ID_resposta(row_fields, tstpeso_id, tstpeso_valor_usado)
    adicionar_campo_com_ID_resposta(row_fields, peso_field_id, peso_novo)
    adicionar_campo_com_ID_resposta(row_fields, pesobalanca_field_id, pesobalanca_novo)
    
    # Partes estáticas
    etree.SubElement(return_value, "ShortText").text = "Processado com sucesso"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "1"  # Indica sucesso
    
    # Serialização
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    
    logging.debug("XML de Resposta MÍNIMA (UTF-16):\n%s", xml_str_final)
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")


def adicionar_campo_com_ID_resposta(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field> para a RESPOSTA."""
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id  # ID Maiúsculo
    etree.SubElement(field, "Value").text = value if value is not None else ""


# --- Rota Principal (Corrigida) ---
app = Flask(__name__)

@app.route('/simulador_balanca_corrigido', methods=['POST'])
@app.route('/teste_caixa', methods=['POST'])  # Rota adicional para compatibilidade
def encaxotar_v2():
    """
    Função principal que processa o XML de entrada e retorna uma resposta com valores de peso
    """
    try:
        logging.info(f"--- Nova Requisição {request.method} ---")
        
        # 1. Obtenção do XML
        xml_data_bytes = None
        
        # Tenta obter de form-data
        if request.form:
            for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
                if name in request.form:
                    xml_data_str = request.form.get(name)
                    xml_data_bytes = xml_data_str.encode('utf-8')
                    break
            
            # Se não encontrou nas chaves conhecidas, tenta a primeira chave
            if not xml_data_bytes and request.form:
                first_key = next(iter(request.form))
                xml_data_str = request.form.get(first_key)
                xml_data_bytes = xml_data_str.encode('utf-8')
        
        # Tenta obter de request.data se ainda não encontrou
        if not xml_data_bytes and request.data:
            xml_data_bytes = request.data
            
        # Verifica se tem dados
        if not xml_data_bytes:
            logging.error("XML não encontrado na requisição")
            return gerar_erro_xml_adaptado("XML não encontrado.", "Erro Input", 400)
            
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]:
            return gerar_erro_xml_adaptado("Parâmetro 'balanca' inválido.", "Erro Param", 400)
            
        # 3. Configurar IDs baseados na balança
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        
        # 4. Extrair TSTPESO
        logging.debug(f"Extração para tabela='{tabela_id_a_usar}', campo='{tstpeso_id_a_usar}'")
        tstpeso_valor_extraido, _ = extrair_linha_alvo_e_tstpeso_v2(
            xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar
        )
        
        # Se falhar, usa valor default
        if tstpeso_valor_extraido is None:
            tstpeso_valor_extraido = "0"
            logging.warning(f"Usando valor default TSTPESO='0' após falha na extração")
            
        # 5. Gerar valores de peso
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)
        logging.info(f"Valores gerados: peso={peso_novo}, pesobalanca={pesobalanca_novo}")
        
        # 6. Gerar resposta mínima (mais simples e robusta)
        return gerar_resposta_minima_com_valores(
            peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar, tstpeso_valor_extraido
        )
        
    except Exception as e:
        logging.exception("ERRO FATAL no processamento da requisição")
        return gerar_erro_xml_adaptado(
            f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500
        )


if __name__ == '__main__':
    app.run(debug=True, port=5000)