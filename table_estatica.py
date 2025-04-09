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

# --- Função de Resposta com STRING TEMPLATE ---
def gerar_resposta_string_template(peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera ResponseV2 usando string formatada, contendo APENAS
    a TableField relevante com uma única Row e 3 campos essenciais. UTF-16.
    """
    logging.debug(f"Gerando resposta STRING TEMPLATE para balanca '{balanca_id}'")

    # Determina IDs
    tabela_id_resp = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_id_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_id_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    tstpeso_id_resp = tstpeso_id # Já é TSTPESO1 ou TSTPESO2

    # Monta o template XML usando f-string
    # Atenção à indentação e aos IDs maiúsculos na resposta
    xml_template = f"""<?xml version="1.0" encoding="utf-16"?>
<ResponseV2 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <MessageV2>
    <Text>Consulta realizada com sucesso.</Text>
  </MessageV2>
  <ReturnValueV2>
    <Fields>
      <TableField>
        <ID>{tabela_id_resp}</ID>
        <Rows>
          <Row IsCurrentRow="True">
            <Id>Linha 1</Id>
            <Fields>
              <Field>
                <ID>{tstpeso_id_resp}</ID>
                <Value>{tstpeso_valor_usado}</Value>
              </Field>
              <Field>
                <ID>{peso_id_resp}</ID>
                <Value>{peso_novo}</Value>
              </Field>
              <Field>
                <ID>{pesobalanca_id_resp}</ID>
                <Value>{pesobalanca_novo}</Value>
              </Field>
            </Fields>
          </Row>
          <Row>
            <Id>Linha 2</Id>
            <Fields>
              <Field>
                <ID>{tstpeso_id_resp}</ID>
                <Value>{tstpeso_valor_usado}</Value>
              </Field>
              <Field>
                <ID>{peso_id_resp}</ID>
                <Value>{peso_novo}</Value>
              </Field>
              <Field>
                <ID>{pesobalanca_id_resp}</ID>
                <Value>{pesobalanca_novo}</Value>
              </Field>
            </Fields>
          </Row>
          <Row>
            <Id>Linha 3</Id>
            <Fields>
              <Field>
                <ID>{tstpeso_id_resp}</ID>
                <Value>{tstpeso_valor_usado}</Value>
              </Field>
              <Field>
                <ID>{peso_id_resp}</ID>
                <Value>{peso_novo}</Value>
              </Field>
              <Field>
                <ID>{pesobalanca_id_resp}</ID>
                <Value>{pesobalanca_novo}</Value>
              </Field>
            </Fields>
          </Row>
        </Rows>
      </TableField>
    </Fields>
    <ShortText>Pressione Lixeira para nova consulta</ShortText>
    <LongText/>
    <Value>58</Value>
  </ReturnValueV2>
</ResponseV2>"""


    xml_final_string = xml_template # Manter indentação original por enquanto

    logging.debug("XML de Resposta STRING TEMPLATE (UTF-16):\n%s", xml_final_string)
    # Codifica a string final para UTF-16 para a resposta
    return Response(xml_final_string.encode("utf-16le"), content_type="application/xml; charset=utf-16")


def encaixotar_v4():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    # 1. Obtenção Robusta do XML
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

    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair TSTPESO (da linha 'atual')
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor_extraido = extrair_tstpeso_da_tabela(xml_data_bytes, tabela_id_a_usar, tstpeso_id_a_usar)
        logging.info(f"TSTPESO extraído da linha 'atual': '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)

        # 5. Gerar Resposta XML usando STRING TEMPLATE
        return gerar_resposta_string_template( # Chama a nova função de template
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)