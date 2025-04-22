from flask import Flask, request, Response
from utils.gerar_erro import gerar_erro_xml # Supondo que você tenha este módulo
from lxml import etree
import random
import logging
from io import BytesIO
import copy # Para fazer uma cópia profunda da árvore XML

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---
def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response_xml_root = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response_xml_root, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response_xml_root, "ReturnValueV2")
    etree.SubElement(return_value, "Fields") # Adiciona Fields, mesmo que vazio, para estrutura
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response_xml_root, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16le"), status=status_code, content_type="application/xml; charset=utf-16")

def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    if not xml_bytes: return "0"
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        xpath_tabela = f".//TableField[ID='{tabela_id_alvo}']" # Corrigido: Id para ID
        tabela_elements = root.xpath(xpath_tabela)
        if not tabela_elements: return "0"
        tabela_element = tabela_elements[0]
        linha_alvo = None
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows:
            linha_alvo = current_rows[0]
        else:
            # Se não houver IsCurrentRow="True", pode pegar a primeira linha como fallback
            # ou retornar erro, dependendo do comportamento desejado.
            # Por enquanto, vamos manter a lógica de pegar a primeira se não houver IsCurrentRow.
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list:
                linha_alvo = primeira_linha_list[0]

        if linha_alvo is None: return "0"

        xpath_tstpeso = f".//Field[ID='{tstpeso_id_alvo}']/Value" # Corrigido: Id para ID
        tstpeso_elements = linha_alvo.xpath(xpath_tstpeso)
        if tstpeso_elements:
            value_text = tstpeso_elements[0].text
            if value_text is not None:
                value_text = value_text.strip()
                return value_text if value_text in ["0", "1"] else "0"
        return "0"
    except Exception:
        logging.exception("Erro ao extrair TSTPESO")
        return "0"

def gerar_valores_peso(tstpeso_valor, balanca_id):
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

def gerar_resposta_com_linhas_preservadas(xml_bytes_entrada, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera ResponseV2 preservando todas as linhas do XML de entrada.
    Atualiza apenas a linha IsCurrentRow="True" com novos valores e OverrideData="1".
    As outras linhas são mantidas como estavam (sem OverrideData, a menos que já tivessem).
    """
    logging.debug(f"Gerando resposta COM LINHAS PRESERVADAS para balanca '{balanca_id}'")

    try:
        parser = etree.XMLParser(recover=True)
        tree_entrada = etree.parse(BytesIO(xml_bytes_entrada), parser)
        root_entrada = tree_entrada.getroot()

        # Criar a estrutura base da resposta (pode copiar partes do root_entrada se quiser manter outros elementos)
        # Por simplicidade, vamos recriar o ResponseV2 aqui
        nsmap_resp = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        root_resposta = etree.Element("ResponseV2", nsmap=nsmap_resp)
        message_resp = etree.SubElement(root_resposta, "MessageV2")
        etree.SubElement(message_resp, "Text").text = "Consulta realizada com sucesso."
        return_value_resp = etree.SubElement(root_resposta, "ReturnValueV2")
        fields_resp_container = etree.SubElement(return_value_resp, "Fields") # Container para TableFields

        tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_id_campo_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_id_campo_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

        # Encontrar a TableField original no XML de entrada
        xpath_tabela_entrada = f".//TableField[ID='{tabela_id_alvo}']" # Corrigido: Id para ID
        tabela_original_elements = root_entrada.xpath(xpath_tabela_entrada)

        if not tabela_original_elements:
            # Se a tabela não existir no XML de entrada, criamos uma com a linha atual
            logging.warning(f"Tabela {tabela_id_alvo} não encontrada no XML de entrada. Criando nova tabela apenas com linha atual.")
            tabela_resp = etree.SubElement(fields_resp_container, "TableField")
            etree.SubElement(tabela_resp, "ID").text = tabela_id_alvo
            # etree.SubElement(tabela_resp, "OverrideData").text = "1" # Adicionado à TableField (opcional, dependendo do requisito)
            rows_resp = etree.SubElement(tabela_resp, "Rows")
            row_atual_resp = etree.SubElement(rows_resp, "Row")
            row_atual_resp.set("IsCurrentRow", "True")
            fields_atual_resp = etree.SubElement(row_atual_resp, "Fields")

            # Campo TSTPESO
            field = etree.SubElement(fields_atual_resp, "Field")
            etree.SubElement(field, "ID").text = tstpeso_id
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = tstpeso_valor_usado
            # Campo PESO
            field = etree.SubElement(fields_atual_resp, "Field")
            etree.SubElement(field, "ID").text = peso_id_campo_resp
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = peso_novo
            # Campo PESOBALANCA
            field = etree.SubElement(fields_atual_resp, "Field")
            etree.SubElement(field, "ID").text = pesobalanca_id_campo_resp
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = pesobalanca_novo
            # Campo WS
            field = etree.SubElement(fields_atual_resp, "Field")
            etree.SubElement(field, "ID").text = "WS"
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = "Pressione Lixeira para nova consulta"

        else:
            tabela_original = tabela_original_elements[0]
            # Criar a TableField na resposta
            tabela_resp = etree.SubElement(fields_resp_container, "TableField")
            etree.SubElement(tabela_resp, "ID").text = tabela_id_alvo
            # OverrideData para a TableField, se necessário, copiar do original ou definir
            # override_data_tabela_original = tabela_original.find('OverrideData')
            # if override_data_tabela_original is not None and override_data_tabela_original.text == '1':
            #    etree.SubElement(tabela_resp, "OverrideData").text = "1"
            # Ou fixar para a tabela, se o comportamento esperado for sempre override na tabela:
            # etree.SubElement(tabela_resp, "OverrideData").text = "1"


            rows_resp = etree.SubElement(tabela_resp, "Rows")

            for row_original in tabela_original.xpath(".//Row"):
                row_resp = etree.SubElement(rows_resp, "Row")
                fields_resp_na_row = etree.SubElement(row_resp, "Fields")

                # Copia o atributo IsCurrentRow se existir no original
                is_current_original = row_original.get("IsCurrentRow")
                if is_current_original == "True":
                    row_resp.set("IsCurrentRow", "True")

                    # Se for a linha atual, insira os novos valores
                    # Campo TSTPESO
                    field = etree.SubElement(fields_resp_na_row, "Field")
                    etree.SubElement(field, "ID").text = tstpeso_id
                    etree.SubElement(field, "OverrideData").text = "1" # OverrideData na linha atual
                    etree.SubElement(field, "Value").text = tstpeso_valor_usado
                    # Campo PESO
                    field = etree.SubElement(fields_resp_na_row, "Field")
                    etree.SubElement(field, "ID").text = peso_id_campo_resp
                    etree.SubElement(field, "OverrideData").text = "1" # OverrideData na linha atual
                    etree.SubElement(field, "Value").text = peso_novo
                    # Campo PESOBALANCA
                    field = etree.SubElement(fields_resp_na_row, "Field")
                    etree.SubElement(field, "ID").text = pesobalanca_id_campo_resp
                    etree.SubElement(field, "OverrideData").text = "1" # OverrideData na linha atual
                    etree.SubElement(field, "Value").text = pesobalanca_novo
                    # Campo WS
                    field = etree.SubElement(fields_resp_na_row, "Field")
                    etree.SubElement(field, "ID").text = "WS"
                    etree.SubElement(field, "OverrideData").text = "1" # OverrideData na linha atual
                    etree.SubElement(field, "Value").text = "Pressione Lixeira para nova consulta"
                else:
                    # Para as outras linhas, copie os campos originais como estão
                    for field_original in row_original.xpath(".//Fields/Field"):
                        # Copiar o elemento Field inteiro (com subelementos ID, Value, OverrideData se existir)
                        field_copiado = copy.deepcopy(field_original)
                        fields_resp_na_row.append(field_copiado)
        
        # Adicionar os demais elementos ao ReturnValueV2
        etree.SubElement(return_value_resp, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value_resp, "LongText")
        etree.SubElement(return_value_resp, "Value").text = "17" # Ou outro valor conforme necessidade

        # Gerar a string XML final
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(root_resposta, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body

        logging.debug("XML de Resposta COM LINHAS PRESERVADAS (UTF-16):\n%s", xml_str_final)
        return Response(xml_str_final.encode("utf-16le"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.exception("Erro ao gerar resposta COM LINHAS PRESERVADAS")
        # Chamar gerar_erro_xml_padrao aqui em vez de gerar_erro_xml (que não existe no escopo)
        return gerar_erro_xml_padrao(f"Erro ao processar XML para preservação: {str(e)}", "Erro Processamento", 500)


# --- Função de Resposta com STRING TEMPLATE ---
# Esta função não será mais o padrão, mas pode ser mantida para fallback se necessário.
# REMOVI A FUNÇÃO gerar_resposta_string_template() ORIGINAL DA SUA PERGUNTA
# PORQUE ELA FOI SUBSTITUÍDA POR gerar_resposta_com_linhas_preservadas()
# SE PRECISAR DELA COMO FALLBACK OU PARA OUTRO PROPÓSITO, PODE REINSERI-LA.


def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    # 1. Obtenção Robusta do XML
    content_type = request.headers.get("Content-Type", "").lower(); xml_data_str = None; xml_data_bytes = None
    if 'form' in content_type.lower() and request.form:
        for name in ["TextXML", "textxml", "XMLData", "xmldata", "xml"]:
            if name in request.form: xml_data_str = request.form.get(name); break
        if not xml_data_str and request.form: first_key = next(iter(request.form)); xml_data_str = request.form.get(first_key)
        if xml_data_str: logging.info("XML obtido de request.form.")
    if not xml_data_str and request.data:
        try: xml_data_bytes = request.data; xml_data_str = xml_data_bytes.decode('utf-8'); logging.info("XML obtido de request.data (UTF-8).")
        except UnicodeDecodeError:
             try: xml_data_str = request.data.decode('latin-1'); xml_data_bytes = request.data; logging.info("XML obtido de request.data (Latin-1).")
             except UnicodeDecodeError: return gerar_erro_xml_padrao("Encoding inválido.", "Erro Encoding", 400) # Corrigido para chamar gerar_erro_xml_padrao
    if not xml_data_bytes and xml_data_str:
        try: xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e: return gerar_erro_xml_padrao(f"Erro codificando form data: {e}", "Erro Encoding", 500) # Corrigido para chamar gerar_erro_xml_padrao
    if not xml_data_bytes: return gerar_erro_xml_padrao("XML não encontrado.", "Erro Input", 400) # Corrigido para chamar gerar_erro_xml_padrao

    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml_padrao("Parâmetro 'balanca' inválido.", "Erro Param", 400) # Corrigido

        # 3. Extrair TSTPESO (da linha 'atual')
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído da linha 'atual': '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML usando a nova função que preserva linhas
        return gerar_resposta_com_linhas_preservadas(
            xml_bytes_entrada=xml_data_bytes, # Passa o XML original
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml_padrao(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500) # Corrigido