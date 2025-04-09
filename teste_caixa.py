# -*- coding: utf-8 -*-

from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO
from utils.gerar_erro import gerar_erro_xml

# --- Configuração Básica ---
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---

def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    # (Mantida)
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def adicionar_campo_com_ID_resposta(parent_element, field_id, value):
    # (Mantida - ID Maiúsculo)
    field = etree.SubElement(parent_element, "Field"); etree.SubElement(field, "ID").text = field_id; etree.SubElement(field, "Value").text = value if value is not None else ""

def gerar_valores_peso(tstpeso_valor, balanca_id):
    # (Mantida)
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero(); 
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

# --- Função de Geração de Resposta (Padrão Officetrack Exato - Mantida) ---
def gerar_resposta_officetrack_exata(root_original, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id_usado, tstpeso_valor_usado):
    """
    Gera ResponseV2 exatamente como o padrão Officetrack:
    - Inclui campos de nível superior originais (ID ajustado, EXCETO TSTPESO).
    - Inclui TableField alvo com linhas ATÉ a IsCurrentRow.
    - Linhas ANTERIORES copiadas integralmente (ID ajustado).
    - Linha IsCurrentRow incluída com APENAS 3 campos essenciais atualizados (ID ajustado).
    - Linhas POSTERIORES omitidas.
    - NENHUM IsCurrentRow na resposta.
    - Usa ID maiúsculo na resposta.
    """
    logging.debug(f"Gerando resposta PADRÃO OFFICETRACK EXATO para balanca '{balanca_id}'")
    if root_original is None: return gerar_erro_xml_padrao("Erro interno: Árvore XML original não fornecida.")

    try:
        # --- Cria a estrutura da resposta ---
        nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        response = etree.Element("ResponseV2", nsmap=nsmap)
        message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
        return_value = etree.SubElement(response, "ReturnValueV2"); response_fields_container = etree.SubElement(return_value, "Fields")

        # --- Identificadores ---
        tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
        # tstpeso_id_usado é 'TSTPESO1' ou 'TSTPESO2'

        # --- 1. Copia Campos de Nível Superior (EXCETO TSTPESO1/2) ---
        main_fields_original = root_original.find("./Fields") or root_original.find(".//Form/Fields")
        if main_fields_original is not None:
            logging.debug("Copiando campos de nível superior (exceto TSTPESOx) para a resposta...")
            for field_original in main_fields_original.xpath("./Field"): # Filhos diretos
                original_id_elem = field_original.find("Id")
                if original_id_elem is not None and original_id_elem.text:
                    original_id = original_id_elem.text.strip()
                    # NÃO copia os campos TSTPESO de nível superior para a resposta
                    if original_id.upper() not in ["TSTPESO1", "TSTPESO2"]:
                        original_value = field_original.findtext("Value", default="")
                        adicionar_campo_com_ID_resposta(response_fields_container, original_id.upper(), original_value)
                        logging.debug(f"  Campo Nível Sup. Copiado: ID={original_id.upper()}, Value='{original_value}'")
                    else:
                        logging.debug(f"  Campo Nível Sup. '{original_id}' ignorado (será incluído na linha da tabela).")
        else:
            logging.warning("Container <Fields> principal não encontrado no XML original.")

        # --- 2. Processa e Adiciona a TableField Alvo ---
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']" # Id minúsculo input
        tabela_elements = root_original.xpath(xpath_tabela)

        if not tabela_elements:
            logging.warning(f"Tabela '{tabela_id_alvo}' não encontrada.")
        else:
            tabela_element_original = tabela_elements[0]
            response_table = etree.SubElement(response_fields_container, "TableField")
            etree.SubElement(response_table, "ID").text = tabela_id_alvo # ID Maiúsculo resposta
            response_rows_container = etree.SubElement(response_table, "Rows")

            logging.debug(f"Processando linhas da tabela '{tabela_id_alvo}' para resposta...")
            for row_original in tabela_element_original.xpath(".//Row"):
                is_current = row_original.get("IsCurrentRow", "").lower() == 'true'
                response_row = etree.SubElement(response_rows_container, "Row") # SEM IsCurrentRow
                response_row_fields = etree.SubElement(response_row, "Fields")
                original_fields_container = row_original.find(".//Fields")

                if original_fields_container is None:
                     logging.warning("Linha original sem <Fields> encontrada.");
                     if is_current: break
                     else: continue

                if is_current:
                    logging.info(f"Processando linha IsCurrentRow='True'. Adicionando 3 campos atualizados.")
                    adicionar_campo_com_ID_resposta(response_row_fields, tstpeso_id_usado, tstpeso_valor_usado)
                    adicionar_campo_com_ID_resposta(response_row_fields, peso_field_id, peso_novo)
                    adicionar_campo_com_ID_resposta(response_row_fields, pesobalanca_field_id, pesobalanca_novo)
                    logging.info("Linha IsCurrentRow processada e adicionada. Interrompendo loop.")
                    break
                else:
                    logging.debug("Copiando TODOS os campos da linha anterior.")
                    for field_original in original_fields_container.xpath("./Field"):
                        original_id_elem = field_original.find("Id")
                        if original_id_elem is not None and original_id_elem.text:
                            original_id = original_id_elem.text.strip()
                            original_value = field_original.findtext("Value", default="")
                            adicionar_campo_com_ID_resposta(response_row_fields, original_id.upper(), original_value)
                        else: logging.warning("Campo sem 'Id' encontrado na linha anterior.")

            logging.debug(f"Tabela '{tabela_id_alvo}' adicionada à resposta com linhas ATÉ a atual.")

        # --- Partes estáticas ---
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "58"

        # --- Serialização ---
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
        logging.debug("XML de Resposta PADRÃO OT EXATO (UTF-16):\n%s", xml_str_final)
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.exception("Erro fatal ao gerar resposta padrão OT exato")
        return gerar_erro_xml(f"Erro interno ao gerar resposta: {str(e)}", "Erro Servidor", 500)


# --- Rota Principal ---
# ** Use a URL que o cliente chama! **

def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    # 1. Obtenção Robusta do XML (mantida)
    content_type = request.headers.get("Content-Type", "").lower(); xml_data_str = None; xml_data_bytes = None
    # ... (código de obtenção mantido) ...
    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form: xml_data_str = request.form.get(name); break
        if not xml_data_str and request.form: first_key = next(iter(request.form)); xml_data_str = request.form.get(first_key)
        if xml_data_str: logging.info("XML obtido de request.form.")
    if not xml_data_str and request.data:
        try: xml_data_bytes = request.data; xml_data_str = xml_data_bytes.decode('utf-8'); logging.info("XML obtido de request.data (UTF-8).")
        except UnicodeDecodeError:
             try: xml_data_str = request.data.decode('latin-1'); xml_data_bytes = request.data; logging.info("XML obtido de request.data (Latin-1).")
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

        # *** 3. Extrair TSTPESO do NÍVEL SUPERIOR ***
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tstpeso_valor_extraido = "0" # Default

        # Parseia o XML para buscar o TSTPESO de nível superior
        try:
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(BytesIO(xml_data_bytes), parser)
            root_original = tree.getroot()
            # Busca o campo TSTPESO direto sob <Fields> ou <Form><Fields>
            main_fields = root_original.find("./Fields") or root_original.find(".//Form/Fields")
            if main_fields is not None:
                # Busca por Id minúsculo no input
                tstpeso_field = main_fields.xpath(f"./Field[Id='{tstpeso_id_a_usar}']")
                if tstpeso_field:
                    value_elem = tstpeso_field[0].find("Value")
                    if value_elem is not None and value_elem.text is not None:
                        valor = value_elem.text.strip()
                        if valor in ["0", "1"]:
                            tstpeso_valor_extraido = valor
                        else:
                            logging.warning(f"Valor inválido '{valor}' para TSTPESO de nível sup. Usando '0'.")
                    else:
                        logging.warning(f"Tag Value vazia ou ausente para TSTPESO de nível sup. Usando '0'.")
                else:
                    logging.warning(f"Campo TSTPESO '{tstpeso_id_a_usar}' não encontrado no nível sup. Usando '0'.")
            else:
                logging.warning("Container <Fields> principal não encontrado para buscar TSTPESO. Usando '0'.")
        except Exception as parse_err:
            logging.exception("Erro ao parsear XML para buscar TSTPESO de nível sup.")
            # Continua com default '0'

        logging.info(f"TSTPESO extraído (nível superior): '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML no Padrão Officetrack Exato
        # Passa a árvore já parseada para evitar re-parse
        return gerar_resposta_officetrack_exata(
            root_original=root_original, # Passa a árvore parseada
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id_usado=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido # O valor lido do nível superior
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)

#