# -*- coding: utf-8 -*-

from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO

# --- Configuração Básica ---
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---

def gerar_erro_xml(mensagem, short_text="Erro", status_code=400):
    """Gera um XML de erro no formato ResponseV2 (UTF-16)."""
    # (Função mantida - parece correta)
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

def adicionar_campo_xml_com_ID(parent_element, field_id, value):
    """Cria e adiciona <Field><ID>...</ID><Value>...</Value></Field>."""
    # (Função mantida - ID maiúsculo)
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value if value is not None else ""

# --- NOVA Função de Extração: Retorna a Linha Alvo Completa ---
def extrair_linha_alvo_e_tstpeso(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """
    Encontra a linha alvo (Current ou Primeira) na tabela especificada
    dentro do <Form>, extrai o TSTPESO dela e retorna o valor do TSTPESO
    e o DICIONÁRIO de dados dessa linha alvo.

    Retorna: (tstpeso_valor, dicionario_linha_alvo) ou (None, None) se erro.
    """
    if not xml_bytes:
        logging.error("extrair_linha_alvo recebeu xml_bytes vazio.")
        return None, None
    try:
        logging.debug(f"--- Iniciando extrair_linha_alvo para Tabela '{tabela_id_alvo}', Campo TST '{tstpeso_id_alvo}' ---")
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()

        # Encontra <Form>
        form_elements = root.xpath('.//Form[1]')
        if not form_elements:
            logging.error("Tag <Form> não encontrada.")
            return None, None
        form_element = form_elements[0]

        # Encontra a tabela dentro de <Form>
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']" # Id minúsculo input
        tabela_elements = form_element.xpath(xpath_tabela)
        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_alvo}' NÃO encontrada dentro de <Form>.")
            return None, None
        tabela_element = tabela_elements[0]

        linha_alvo_element = None
        linha_alvo_info = "Nenhuma"

        # Prioriza IsCurrentRow="True"
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows:
            linha_alvo_element = current_rows[0]
            linha_alvo_info = "IsCurrentRow='True'"
        else: # Fallback para primeira linha
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list:
                linha_alvo_element = primeira_linha_list[0]
                linha_alvo_info = "Primeira Linha"

        if linha_alvo_element is None:
            logging.warning(f"Nenhuma linha encontrada (Current ou Primeira) na tabela '{tabela_id_alvo}'.")
            return None, None

        logging.info(f"Linha Alvo encontrada: {linha_alvo_info}")

        # Extrai TODOS os campos da linha alvo para um dicionário
        linha_alvo_dict = {}
        fields_container = linha_alvo_element.find('.//Fields')
        if fields_container is not None:
            for field in fields_container.findall('.//Field'):
                field_id = field.findtext("Id") # Id minúsculo input
                if field_id:
                    linha_alvo_dict[field_id] = field.findtext("Value", default="").strip()
            logging.debug(f"Dados extraídos da Linha Alvo ({linha_alvo_info}): {linha_alvo_dict}")
        else:
            logging.warning(f"Container <Fields> não encontrado na linha alvo {linha_alvo_info}. A linha será retornada vazia.")

        # Extrai e valida o TSTPESO especificamente deste dicionário
        tstpeso_valor = linha_alvo_dict.get(tstpeso_id_alvo, "0") # Default '0'
        if tstpeso_valor not in ["0", "1"]:
            logging.warning(f"Valor TSTPESO inválido '{tstpeso_valor}' na linha alvo. Usando default '0'.")
            tstpeso_valor = "0"
        else:
            logging.info(f"Valor TSTPESO '{tstpeso_valor}' confirmado para a linha alvo.")

        return tstpeso_valor, linha_alvo_dict # Retorna o valor e o dicionário da linha

    except Exception as e:
        logging.exception("Erro EXCEPCIONAL ao extrair linha alvo e TSTPESO")
        return None, None


def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera peso e pesobalanca (formato string com vírgula)."""
    # (Função mantida)
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

# --- Função de Resposta: Usa a Linha Alvo ---
def gerar_resposta_com_linha_alvo(linha_alvo_dict, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id):
    """
    Gera ResponseV2 com TableField mínima contendo a linha alvo
    com TSTPESO original e os NOVOS pesos calculados (apenas 3 campos). UTF-16.
    """
    if linha_alvo_dict is None:
        logging.error("gerar_resposta_com_linha_alvo recebeu linha_alvo_dict=None")
        return gerar_erro_xml("Falha interna: Dados da linha alvo não encontrados.", "Erro Interno")

    tstpeso_valor_original = linha_alvo_dict.get(tstpeso_id, "0") # Pega o TSTPESO original da linha

    logging.debug(f"Gerando resposta com linha alvo para balanca '{balanca_id}' (TST original: '{tstpeso_valor_original}')")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    return_value = etree.SubElement(response, "ReturnValueV2"); fields_container = etree.SubElement(return_value, "Fields")

    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

    response_table = etree.SubElement(fields_container, "TableField"); etree.SubElement(response_table, "ID").text = tabela_id_alvo
    response_rows = etree.SubElement(response_table, "Rows"); response_row = etree.SubElement(response_rows, "Row")
    # Poderia adicionar atributos da linha original se necessário:
    # original_attrs = linha_alvo_dict.get('_attributes', {})
    # for k, v in original_attrs.items(): response_row.set(k, v)

    row_fields = etree.SubElement(response_row, "Fields")

    # Adiciona os 3 campos essenciais: TSTPESO (original da linha), PESO (novo), PESOBALANCA (novo)
    adicionar_campo_xml_com_ID(row_fields, tstpeso_id, tstpeso_valor_original)
    adicionar_campo_xml_com_ID(row_fields, peso_field_id, peso_novo)
    adicionar_campo_xml_com_ID(row_fields, pesobalanca_field_id, pesobalanca_novo)

    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"

    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    logging.debug("XML de Resposta com Linha Alvo Gerado (UTF-16):\n%s", xml_str_final)
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")


# --- Rota Principal (Focada e Usando Novas Funções) ---
@app.route("/balanca_simulador_focado", methods=['POST'])
def simular_balanca_focado():
    logging.info(f"--- Nova Requisição {request.method} para /balanca_simulador_focado ---")
    # 1. Obtenção Robusta do XML (mantida)
    content_type = request.headers.get("Content-Type", "").lower(); xml_data_str = None; xml_data_bytes = None
    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form: xml_data_str = request.form.get(name); break
        if not xml_data_str and request.form: first_key = next(iter(request.form)); xml_data_str = request.form.get(first_key)
    if not xml_data_str and request.data:
        try: xml_data_bytes = request.data; xml_data_str = xml_data_bytes.decode('utf-8')
        except UnicodeDecodeError:
             try: xml_data_str = request.data.decode('latin-1'); xml_data_bytes = request.data
             except UnicodeDecodeError: return gerar_erro_xml("Encoding inválido.", "Erro Encoding", 400)
    if not xml_data_bytes and xml_data_str:
        try: xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e: return gerar_erro_xml(f"Erro codificando form data: {e}", "Erro Encoding", 500)
    if not xml_data_bytes: return gerar_erro_xml("XML não encontrado.", "Erro Input", 400)
    logging.debug("XML Data (início):\n%s", xml_data_str[:500] if xml_data_str else "N/A")

    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml("Parâmetro 'balanca' inválido.", "Erro Param", 400)
        logging.debug(f"Parâmetro 'balanca': '{balanca}'")

        # 3. Extrair LINHA ALVO e TSTPESO
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        logging.debug(f"Chamando extrair_linha_alvo_e_tstpeso(tabela='{tabela_id_a_usar}', campo='{tstpeso_id_a_usar}')")
        tstpeso_valor_extraido, linha_alvo_extraida_dict = extrair_linha_alvo_e_tstpeso(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)

        # Verifica se a extração da linha falhou
        if linha_alvo_extraida_dict is None:
             # O erro específico já foi logado dentro da função de extração
             return gerar_erro_xml("Falha ao processar a linha alvo no XML de entrada.", "Erro XML Linha")
        logging.info(f"TSTPESO extraído da linha alvo: '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos (baseado no TSTPESO extraído)
        logging.debug(f"Chamando gerar_valores_peso(tstpeso='{tstpeso_valor_extraido}', balanca='{balanca}')")
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta com a Linha Alvo Atualizada
        logging.debug(f"Chamando gerar_resposta_com_linha_alvo(...)")
        return gerar_resposta_com_linha_alvo(
            linha_alvo_extraida_dict, peso_novo, pesobalanca_novo, balanca, tstpeso_id_a_usar
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /balanca_simulador_focado")
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)

# --- Execução ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)