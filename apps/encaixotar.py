from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---
def gerar_erro_xml(mensagem, short_text="Erro", status_code=400):
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

def extrair_valores_do_xml(xml_bytes, balanca_id):
    """
    Extrai valores de PESO e PESOBALANCA do XML (não da tabela)
    """
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        
        # Determina os IDs dos campos com base no balanca_id
        if balanca_id == "balanca1":
            peso_id = "PESO1"
            pesobalanca_id = "PESOBALANCA1"
            tstpeso_id = "TSTPESO1"
        else:  # balanca2
            peso_id = "PESO2"
            pesobalanca_id = "PESOBALANCA2"
            tstpeso_id = "TSTPESO2"
        
        # Extrair valores diretamente dos campos
        valores = {}
        
        # Procura todos os campos no XML
        for field in root.findall(".//Field"):
            field_id = field.findtext("ID") or field.findtext("Id")
            if field_id in [peso_id, pesobalanca_id, tstpeso_id]:
                valores[field_id] = field.findtext("Value", "").strip()
        
        peso_valor = valores.get(peso_id)
        pesobalanca_valor = valores.get(pesobalanca_id)
        tstpeso_valor = valores.get(tstpeso_id, "0")
        
        # Valida TSTPESO
        if tstpeso_valor not in ["0", "1"]:
            tstpeso_valor = "0"
            
        logging.debug(f"Valores extraídos: {peso_id}={peso_valor}, {pesobalanca_id}={pesobalanca_valor}, {tstpeso_id}={tstpeso_valor}")
        return peso_valor, pesobalanca_valor, tstpeso_valor
        
    except Exception as e:
        logging.exception(f"Erro ao extrair valores do XML: {e}")
        return None, None, "0"

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
          <Row>
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

    xml_final_string = xml_template

    logging.debug("XML de Resposta STRING TEMPLATE (UTF-16):\n%s", xml_final_string)
    # Codifica a string final para UTF-16 para a resposta
    return Response(xml_final_string.encode("utf-16"), content_type="application/xml; charset=utf-16")

def encaixotar_v3():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    # 1. Obtenção Robusta do XML
    content_type = request.headers.get("Content-Type", "").lower()
    xml_data_str = None
    xml_data_bytes = None
    
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
                return gerar_erro_xml("Encoding inválido.", "Erro Encoding", 400)
    
    if not xml_data_bytes and xml_data_str:
        try:
            xml_data_bytes = xml_data_str.encode('utf-8')
        except Exception as e:
            return gerar_erro_xml(f"Erro codificando form data: {e}", "Erro Encoding", 500)
    
    if not xml_data_bytes:
        return gerar_erro_xml("XML não encontrado.", "Erro Input", 400)

    try:
        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]:
            return gerar_erro_xml("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # 3. Extrair valores dos campos (não da tabela)
        peso_valor, pesobalanca_valor, tstpeso_valor = extrair_valores_do_xml(xml_data_bytes, balanca)
        
        # Se não conseguiu extrair os valores, gera erro
        if peso_valor is None or pesobalanca_valor is None:
            logging.error("Valores necessários não encontrados no XML")
            return gerar_erro_xml("Valores de peso não encontrados no XML", "Erro Dados", 400)

        # 4. Gerar Resposta XML usando STRING TEMPLATE
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        return gerar_resposta_string_template(
            peso_novo=peso_valor,
            pesobalanca_novo=pesobalanca_valor,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa")
        return gerar_erro_xml(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)