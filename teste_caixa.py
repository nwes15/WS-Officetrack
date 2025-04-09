# -*- coding: utf-8 -*-

from flask import Flask, request, Response
from lxml import etree # Ainda necessário para PARSEAR o input
import random
import logging
from io import BytesIO, StringIO # StringIO pode ser útil se o input vier do form como string


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares ---

def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    # (Função mantida da nossa versão anterior)
    logging.error(f"Gerando erro: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap); message = etree.SubElement(response, "MessageV2"); etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2"); etree.SubElement(return_value, "Fields"); etree.SubElement(return_value, "ShortText").text = short_text; etree.SubElement(return_value, "LongText"); etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'; xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16"); xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

# --- Função de Extração MODIFICADA para buscar TSTPESO específico ---
def extrair_campo_nivel_superior(xml_bytes, field_id_alvo):
    """Extrai o valor de um campo específico no nível superior."""
    if not xml_bytes: return None
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        # Busca o container <Fields> principal
        main_fields = root.find("./Fields") or root.find(".//Form/Fields")
        if main_fields is not None:
            # Busca o campo pelo Id minúsculo
            field_element = main_fields.xpath(f"./Field[Id='{field_id_alvo}']")
            if field_element:
                value_elem = field_element[0].find("Value")
                if value_elem is not None and value_elem.text is not None:
                    return value_elem.text.strip()
                else:
                    return "" # Retorna vazio se <Value> existe mas está vazia
            else:
                 logging.debug(f"Campo '{field_id_alvo}' não encontrado no nível superior.")
                 return None # Retorna None se o campo <Field> não existe
        else:
             logging.debug("Container <Fields> principal não encontrado.")
             return None # Retorna None se <Fields> não existe

    except Exception as e:
        logging.exception(f"Erro ao extrair campo de nível superior '{field_id_alvo}'")
        return None

def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera peso e pesobalanca (formato string com vírgula)."""
    def formatar_numero():
        return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0":
        valor = formatar_numero()
        logging.debug(f"  -> Peso/Balanca (TST=0): {valor}")
        return valor, valor # Retorna tupla
    else: # Assume 1 ou fallback
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca:
            logging.debug("  -> Valores gerados eram iguais, regerando pesobalanca...") # Log adicional
            pesobalanca = formatar_numero()
        logging.debug(f"  -> Peso (TST=1): {peso}, Balanca: {pesobalanca}")
        # *** ADICIONAR ESTA LINHA ***
        return peso, pesobalanca # Retorna a tupla com os valores diferentes

# --- Função de Resposta com STRING TEMPLATE (Mantida) ---
def gerar_resposta_string_template(peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    # (Mantida como antes)
    logging.debug(f"Gerando resposta STRING TEMPLATE para balanca '{balanca_id}'")
    tabela_id_resp = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_id_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_id_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    tstpeso_id_resp = tstpeso_id
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
    return Response(xml_final_string.encode("utf-16"), content_type="application/xml; charset=utf-16")



def encaixotar_v2():
    logging.info(f"--- Nova Requisição {request.method} para /teste_caixa ---")
    try:
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
                 except UnicodeDecodeError: return gerar_erro_xml_padrao("Encoding inválido.", "Erro Encoding", 400)
        if not xml_data_bytes and xml_data_str:
            try: xml_data_bytes = xml_data_str.encode('utf-8')
            except Exception as e: return gerar_erro_xml_padrao(f"Erro codificando form data: {e}", "Erro Encoding", 500)
        if not xml_data_bytes: return gerar_erro_xml_padrao("XML não encontrado.", "Erro Input", 400)
        logging.debug("XML Data (início):\n%s", xml_data_str[:500] if xml_data_str else "N/A")

        # 2. Obter parâmetro 'balanca'
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]: return gerar_erro_xml_padrao("Parâmetro 'balanca' inválido.", "Erro Param", 400)

        # *** 3. Extrair TSTPESO do Nível Superior (usando nova helper) ***
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tstpeso_valor_extraido = extrair_campo_nivel_superior(xml_data_bytes, tstpeso_id_a_usar)

        # Trata caso onde TSTPESO não foi encontrado ou é inválido
        if tstpeso_valor_extraido is None or tstpeso_valor_extraido not in ["0", "1"]:
            if tstpeso_valor_extraido is not None: # Loga se era inválido
                 logging.warning(f"Valor TSTPESO inválido '{tstpeso_valor_extraido}' encontrado. Usando default '0'.")
            # Se não foi encontrado (None) ou inválido, usa '0'
            tstpeso_valor_extraido = "0"

        logging.info(f"TSTPESO extraído (nível superior): '{tstpeso_valor_extraido}'")

        # 4. Gerar Novos Pesos
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_extraido, balanca)
        # ultimo_valor[balanca] = peso_novo # Removido - estado global não parecia necessário

        # 5. Gerar Resposta XML usando STRING TEMPLATE
        return gerar_resposta_string_template(
            peso_novo=peso_novo,
            pesobalanca_novo=pesobalanca_novo,
            balanca_id=balanca,
            tstpeso_id=tstpeso_id_a_usar,
            tstpeso_valor_usado=tstpeso_valor_extraido
        )

    except Exception as e:
        logging.exception("Erro GERAL fatal na rota /teste_caixa (adaptado)")
        # Usa a função de erro padronizada
        return gerar_erro_xml_padrao(f"Erro interno inesperado: {str(e)}", "Erro Servidor", 500)
