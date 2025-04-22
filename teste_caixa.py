from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO
import copy  # Importar apenas uma vez


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
    if not xml_bytes:
        return "0"
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        
        xpath_tabela = f".//TableField[ID='{tabela_id_alvo}']"
        tabela_elements = root.xpath(xpath_tabela)
        
        if not tabela_elements:
            return "0"
        
        tabela_element = tabela_elements[0]
        linha_alvo = None
        
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows:
            linha_alvo = current_rows[0]
        else:
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list:
                linha_alvo = primeira_linha_list[0]
        
        if linha_alvo is None:
            return "0"
        
        xpath_tstpeso = f".//Field[ID='{tstpeso_id_alvo}']/Value"
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
    def formatar_numero():
        return "{:.2f}".format(random.uniform(0.5, 500)).replace('.', ',')
    
    if tstpeso_valor == "0":
        valor = formatar_numero()
        return valor, valor
    else:
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca:
            pesobalanca = formatar_numero()
        return peso, pesobalanca

def gerar_resposta_preservando_estrutura(xml_bytes, peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera ResponseV2 preservando a estrutura original do XML,
    atualizando apenas os campos na linha marcada como IsCurrentRow="True"
    """
    logging.debug(f"Gerando resposta preservando estrutura para balanca '{balanca_id}'")
    
    try:
        # Determina IDs
        tabela_id_resp = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
        peso_id_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
        pesobalanca_id_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
        
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
        
        if tabelas_originais:
            # Copiar a tabela original
            tabela_original = tabelas_originais[0]
            tabela = etree.SubElement(fields, "TableField")
            
            # Copiar atributos da tabela original (ID e OverrideData)
            tabela.set("ID", tabela_original.get("ID"))  # Copia o atributo ID
           # tabela.set("OverrideData", tabela_original.get("OverrideData"))

            
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
                
                # Se for a linha atual, atualizar com os novos valores
                if is_current:
                    # Campo TSTPESO
                    field = etree.SubElement(row_fields, "Field")
                    etree.SubElement(field, "ID").text = tstpeso_id
                    etree.SubElement(field, "OverrideData").text = "1"
                    etree.SubElement(field, "Value").text = tstpeso_valor_usado
                    
                    # Campo PESO
                    field = etree.SubElement(row_fields, "Field")
                    etree.SubElement(field, "ID").text = peso_id_resp
                    etree.SubElement(field, "OverrideData").text = "1"
                    etree.SubElement(field, "Value").text = peso_novo
                    
                    # Campo PESOBALANCA
                    field = etree.SubElement(row_fields, "Field")
                    etree.SubElement(field, "ID").text = pesobalanca_id_resp
                    etree.SubElement(field, "OverrideData").text = "1"
                    etree.SubElement(field, "Value").text = pesobalanca_novo
                    
                    # Campo WS (mensagem)
                    field = etree.SubElement(row_fields, "Field")
                    etree.SubElement(field, "ID").text = "WS"
                    etree.SubElement(field, "OverrideData").text = "1"
                    etree.SubElement(field, "Value").text = "Pressione Lixeira para nova consulta"
                else:
                     # Para linhas não-atuais, copiar os campos originais
                     for field_original in row_original.xpath(".//Field"):
                        field = etree.SubElement(row_fields, "Field")
                        
                        # Copiar ID
                        id_element = field_original.find("ID")
                        if id_element is not None:
                           id_copy = etree.SubElement(field, "ID")
                           id_copy.text = id_element.text
                           
                        # Copiar OverrideData apenas se existir
                        override_element = field_original.find("OverrideData")
                        if override_element is not None:
                           override_copy = etree.SubElement(field, "OverrideData")
                           override_copy.text = override_element.text
                           
                        # Copiar Value
                        value_element = field_original.find("Value")
                        if value_element is not None:
                           value_copy = etree.SubElement(field, "Value")
                           value_copy.text = value_element.text

        else:
            # Se não encontrou a tabela, criar uma nova com apenas a linha atual
            tabela = etree.SubElement(fields, "TableField")
            etree.SubElement(tabela, "ID").text = tabela_id_resp
           # etree.SubElement(tabela, "OverrideData").text = "1"
            
            rows = etree.SubElement(tabela, "Rows")
            row = etree.SubElement(rows, "Row")
            row.set("IsCurrentRow", "True")
            
            row_fields = etree.SubElement(row, "Fields")
            
            # Campo TSTPESO
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = tstpeso_id
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = tstpeso_valor_usado
            
            # Campo PESO
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = peso_id_resp
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = peso_novo
            
            # Campo PESOBALANCA
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = pesobalanca_id_resp
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = peso_novo
            
            # Campo WS (mensagem)
            field = etree.SubElement(row_fields, "Field")
            etree.SubElement(field, "ID").text = "WS"
            etree.SubElement(field, "OverrideData").text = "1"
            etree.SubElement(field, "Value").text = "Pressione Lixeira para nova consulta"
        
        # Adicionar elementos restantes
        etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
        etree.SubElement(return_value, "LongText")
        etree.SubElement(return_value, "Value").text = "58"
        
        # Gerar a string XML final
        xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
        xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
        xml_str_final = xml_declaration + xml_body
        
        logging.debug("XML de Resposta preservando estrutura (UTF-16):\n%s", xml_str_final)
        return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")
        
    except Exception as e:
        logging.exception("Erro ao gerar resposta preservando estrutura")
        return gerar_erro_xml_padrao(f"Erro ao processar XML: {str(e)}", "Erro Processamento", 500)


def gerar_resposta_string_template(peso_novo, pesobalanca_novo, balanca_id, tstpeso_id, tstpeso_valor_usado):
    """
    Gera um XML de resposta usando um template de string formatada.
    Esta função é usada como fallback quando não se encontra a tabela no XML original.
    """
    logging.debug(f"Gerando resposta com template para balanca '{balanca_id}'")
    
    # Determina IDs
    tabela_id_resp = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_id_resp = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_id_resp = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    
    # Cria o template XML
    xml_template = f'''<?xml version="1.0" encoding="utf-16"?>
<ResponseV2 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <MessageV2>
    <Text>Consulta realizada com sucesso.</Text>
  </MessageV2>
  <ReturnValueV2>
    <Fields>
      <TableField>
        <ID>{tabela_id_resp}</ID>
        <OverrideData>1</OverrideData>
        <Rows>
          <Row IsCurrentRow="True">
            <Fields>
              <Field>
                <ID>{tstpeso_id}</ID>
                <OverrideData>1</OverrideData>
                <Value>{tstpeso_valor_usado}</Value>
              </Field>
              <Field>
                <ID>{peso_id_resp}</ID>
                <OverrideData>1</OverrideData>
                <Value>{peso_novo}</Value>
              </Field>
              <Field>
                <ID>{pesobalanca_id_resp}</ID>
                <OverrideData>1</OverrideData>
                <Value>{pesobalanca_novo}</Value>
              </Field>
              <Field>
                <ID>WS</ID>
                <OverrideData>1</OverrideData>
                <Value>Pressione Lixeira para nova consulta</Value>
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
</ResponseV2>'''
    
    logging.debug("XML de Resposta com template (UTF-16):\n%s", xml_template)
    return Response(xml_template.encode("utf-16"), content_type="application/xml; charset=utf-16")


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
        return gerar_resposta_preservando_estrutura(
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