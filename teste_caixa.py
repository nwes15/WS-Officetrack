from flask import Flask, request, Response
from utils.gerar_erro import gerar_erro_xml
from lxml import etree # Ainda usamos para PARSE do input
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---
# (gerar_erro_xml_padrao, extrair_tstpeso_da_tabela, gerar_valores_peso - MANTIDAS)
def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
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

def gerar_valores_peso(tstpeso_valor, balanca_id):
    def formatar_numero(): return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    if tstpeso_valor == "0": valor = formatar_numero(); return valor, valor
    else: peso = formatar_numero(); pesobalanca = formatar_numero();
    while peso == pesobalanca: pesobalanca = formatar_numero(); return peso, pesobalanca

# --- Função de Resposta com STRING TEMPLATE ---
def gerar_resposta_com_linha_atuais(xml_bytes, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()

        # Qual tabela usar
        tabela_id = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"

        # Localiza a tabela
        tabela_element = root.xpath(f".//TableField[Id='{tabela_id}']")[0]
        rows_element = tabela_element.find(".//Rows")

        encontrou = False
        nova_lista_rows = []

        for row in rows_element.findall(".//Row"):
            nova_lista_rows.append(row)
            if row.attrib.get("IsCurrentRow") == "True":
                encontrou = True

                # Atualiza campos dentro da linha atual
                for field in row.findall(".//Field"):
                    field_id = field.findtext("ID")
                    valor = field.find("Value")

                    if field_id == tstpeso_id:
                        valor.text = tstpeso_valor_usado
                    elif field_id == peso_id:
                        valor.text = peso_novo
                    elif field_id == pesobalanca_id:
                        valor.text = pesobalanca_novo

                break  # Depois da linha atual, não queremos incluir mais linhas

        # Substitui as linhas por apenas até a atual
        if encontrou:
            for r in list(rows_element):
                rows_element.remove(r)
            for r in nova_lista_rows:
                rows_element.append(r)

        # Monta a resposta
        xml_declaracao = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(root, encoding="utf-16", xml_declaration=False).decode("utf-16")
        return Response((xml_declaracao + xml_body).encode("utf-16"), content_type="application/xml; charset=utf-16")

    except Exception:
        logging.exception("Erro ao gerar resposta com linha atual")
        return gerar_erro_xml("Erro ao montar resposta final.", "Erro Resposta", 500)



# --- Rota Principal ---
# ** Use a URL que o cliente chama! Ex: /teste_caixa **

def encaixotar_v2():
    logging.info("--- Nova Requisição POST para /teste_caixa ---")

    try:
        xml_str = request.form['Data']
        xml_bytes = xml_str.encode('utf-16')  # Entrada está em UTF-16
        balanca = request.args.get("balanca", "balanca1")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()

        tabela_id = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        peso_id = "CX1PESO" if balanca == "balanca1" else "CX2PESO"
        pesobalanca_id = "CX1PESOBALANCA" if balanca == "balanca1" else "CX2PESOBALANCA"
        tstpeso_id = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"

        tabela = root.xpath(f".//TableField[Id='{tabela_id}']")
        if not tabela:
            logging.error("Tabela não encontrada no XML.")
            return Response("Tabela não encontrada", status=400)

        rows = tabela[0].xpath(".//Row[@IsCurrentRow='True']")
        if not rows:
            logging.error("Nenhuma linha marcada como IsCurrentRow='True'.")
            return Response("Linha atual não encontrada", status=400)

        row = rows[0]
        peso_valor = "{:.2f}".format(random.uniform(0.5, 500.0)).replace('.', ',')
        pesobalanca_valor = "{:.2f}".format(random.uniform(0.5, 500.0)).replace('.', ',')

        for field in row.xpath(".//Field"):
            field_id = field.findtext("ID")
            value_elem = field.find("Value")
            if value_elem is not None:
                if field_id == peso_id:
                    value_elem.text = peso_valor
                elif field_id == pesobalanca_id:
                    value_elem.text = pesobalanca_valor
                elif field_id == tstpeso_id:
                    value_elem.text = "0"  # ou "1", depende da lógica

        xml_declaracao = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(root, encoding="utf-16", xml_declaration=False).decode("utf-16")
        return Response((xml_declaracao + xml_body).encode("utf-16"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.exception("Erro na rota /teste_caixa")
        return Response("Erro interno", status=500)