from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')


# --- Funções Auxiliares (gerar_valores_peso e gerar_erro_xml_simples permanecem as mesmas) ---

def gerar_valores_peso(tstpeso_valor):
    """Gera valores de peso aleatórios para balança, considerando TSTPESO."""
    def formatar_numero():
        return "{:.2f}".format(random.uniform(0.5, 500)).replace('.', ',')

    logging.debug(f"Gerando peso com TSTPESO = '{tstpeso_valor}'")
    if str(tstpeso_valor).strip() == "0":
        valor = formatar_numero()
        logging.debug(f"TSTPESO=0, gerado PESO={valor}, PESOBALANCA={valor}")
        return valor, valor
    else:
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca:
            pesobalanca = formatar_numero()
        logging.debug(f"TSTPESO!=0, gerado PESO={peso}, PESOBALANCA={pesobalanca}")
        return peso, pesobalanca

def gerar_erro_xml_responsev2(mensagem, short_text="Erro", status_code=400):
    """Gera uma resposta de erro padronizada no formato ResponseV2."""
    logging.error(f"Gerando erro ResponseV2: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2")
    # Adiciona um Fields vazio no erro, conforme alguns sistemas esperam
    etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    # O valor 0 geralmente indica falha ou erro na lógica do OT
    etree.SubElement(return_value, "Value").text = "0"
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

# --- Função para Construir a Resposta CORRETA ---

def construir_resposta_responsev2(target_table_id, peso_id, balanca_id, peso_novo, pesobalanca_novo, target_table_element, target_row_index):
    """
    Constrói o XML de resposta no formato ResponseV2, incluindo apenas as linhas
    até a target_row_index e preenchendo os pesos corretamente.
    """
    logging.debug("Construindo resposta no formato ResponseV2...")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
    response_root = etree.Element("ResponseV2", nsmap=nsmap)

    # Mensagem de Sucesso
    message = etree.SubElement(response_root, "MessageV2")
    etree.SubElement(message, "Text").text = "Pesos atualizados com sucesso." # Ou outra mensagem apropriada

    # ReturnValue
    return_value = etree.SubElement(response_root, "ReturnValueV2")
    fields_container = etree.SubElement(return_value, "Fields") # Container principal para campos e tabelas

    # Cria o TableField dentro do Fields container
    # Importante: O ID da tabela e dos campos na RESPOSTA deve ser MAIÚSCULO (<ID>)
    response_table = etree.SubElement(fields_container, "TableField")
    etree.SubElement(response_table, "ID").text = target_table_id.upper() # ID Maiúsculo

    response_rows_container = etree.SubElement(response_table, "Rows")

    # Itera pelas linhas ORIGINAIS da tabela alvo, ATÉ a linha atual (inclusive)
    original_rows = target_table_element.xpath(".//Row")
    for idx, original_row in enumerate(original_rows):
        if idx > target_row_index:
            logging.debug(f"Parando de adicionar linhas no índice {idx}. Limite ({target_row_index}) atingido.")
            break

        # Cria a Row na resposta. O exemplo não mostra atributos na Row da resposta,
        # então vamos omitir IsCurrentRow aqui. Se necessário, adicione **original_row.attrib
        response_row = etree.SubElement(response_rows_container, "Row")
        # Cria o container Fields (plural) para a linha da resposta
        response_row_fields = etree.SubElement(response_row, "Fields")

        # --- Lógica de preenchimento dos Fields dentro da Row ---
        if idx == target_row_index:
            # É a linha atual: Adiciona APENAS os campos de peso NOVOS
            logging.debug(f"Adicionando campos de peso GERADOS à linha índice {idx} na resposta.")

            # Campo PESO (ex: CX1PESO)
            field_peso = etree.SubElement(response_row_fields, "Field")
            etree.SubElement(field_peso, "ID").text = peso_id.upper() # ID Maiúsculo
            etree.SubElement(field_peso, "Value").text = peso_novo

            # Campo PESOBALANCA (ex: CX1PESOBALANCA)
            field_balanca = etree.SubElement(response_row_fields, "Field")
            etree.SubElement(field_balanca, "ID").text = balanca_id.upper() # ID Maiúsculo
            etree.SubElement(field_balanca, "Value").text = pesobalanca_novo
        else:
            # É uma linha ANTERIOR: Adiciona APENAS o campo de peso ORIGINAL (CXnPESO)
            logging.debug(f"Adicionando campo de peso ORIGINAL ({peso_id}) à linha índice {idx} na resposta.")
            original_peso_field_value = "" # Default
            # Busca o valor do campo de peso na linha original do INPUT (<Id>)
            original_peso_value_elem = original_row.xpath(f".//Field[Id='{peso_id}']/Value") # Busca no input pelo <Id> minúsculo
            if original_peso_value_elem and original_peso_value_elem[0].text is not None:
                original_peso_field_value = original_peso_value_elem[0].text.strip()

            # Adiciona o campo de peso original à resposta (<ID>)
            field_peso = etree.SubElement(response_row_fields, "Field")
            etree.SubElement(field_peso, "ID").text = peso_id.upper() # ID Maiúsculo na resposta
            etree.SubElement(field_peso, "Value").text = original_peso_field_value

    # Adiciona os campos finais em ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta" # Ou outra mensagem
    etree.SubElement(return_value, "LongText") # Geralmente vazio
    etree.SubElement(return_value, "Value").text = "58" # Código de sucesso comum para validação/preenchimento

    # Serialização
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response_root, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body

    logging.debug("XML de Resposta ResponseV2 (Início):\n%s", xml_str_final[:500])
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")


# --- Rota Principal (Usa a nova função de resposta) ---


def encaixotar_v2():
    xml_data = request.data
    if not xml_data:
        # Usa a função de erro ResponseV2
        return gerar_erro_xml_responsev2("Request body vazio.", "Erro Requisição", 400)

    logging.debug("--- Iniciando processamento /teste_caixa ---")
    logging.debug("XML Recebido (início):\n%s", xml_data[:500].decode('utf-16', errors='ignore'))

    try:
        parser = etree.XMLParser(recover=True, encoding='utf-16')
        root = etree.fromstring(xml_data, parser=parser)
    except etree.XMLSyntaxError as e:
        logging.exception("Erro ao parsear XML de entrada (UTF-16).")
        return gerar_erro_xml_responsev2(f"Erro de sintaxe no XML: {e}", "XML Inválido", 400)
    except Exception as e:
         logging.exception("Erro inesperado ao parsear XML.")
         return gerar_erro_xml_responsev2(f"Erro inesperado no parse XML: {e}. Verifique o encoding.", "Erro Interno", 500)

    target_table_element = None
    target_row_element = None
    target_table_id = None # ID da tabela encontrada (ex: TABCAIXA1)
    target_row_index = -1

    # 1. Encontrar a Tabela e a Linha com IsCurrentRow="True"
    found_current = False
    # Atenção ao XPath: Busca TableField que é filho de Fields
    table_fields = root.xpath(".//Fields/TableField") # Mais específico
    if not table_fields:
         logging.warning("Nenhum elemento <TableField> encontrado dentro de <Fields>.")
         # Procura em qualquer lugar como fallback
         table_fields = root.xpath(".//TableField")
         if not table_fields:
              logging.warning("Nenhum elemento <TableField> encontrado no XML.")
              return gerar_erro_xml_responsev2("Nenhum TableField encontrado no XML.", "XML Inválido", 400)


    for table_field in table_fields:
        table_id_elem = table_field.find("Id") # Input usa <Id> minúsculo
        current_table_id = table_id_elem.text.strip() if table_id_elem is not None and table_id_elem.text else None
        if not current_table_id:
             logging.warning("Encontrado TableField sem <Id> filho. Ignorando.")
             continue

        rows = table_field.xpath(".//Row")
        logging.debug(f"Verificando Tabela '{current_table_id}' com {len(rows)} linhas.")
        for idx, row in enumerate(rows):
            if row.get("IsCurrentRow") == "True":
                target_table_element = table_field
                target_row_element = row
                target_row_index = idx
                target_table_id = current_table_id
                logging.info(f"Encontrada linha IsCurrentRow='True' na tabela '{target_table_id}' no índice {target_row_index}.")
                found_current = True
                break
        if found_current:
            break

    if not found_current:
        logging.warning("Nenhuma linha com IsCurrentRow='True' encontrada em nenhuma tabela.")
        return gerar_erro_xml_responsev2("Nenhuma linha com IsCurrentRow='True' encontrada.", "Dado Não Encontrado", 400)

    # 2. Determinar IDs dos campos
    if target_table_id.upper() == "TABCAIXA1": # Comparação mais robusta
        peso_id = "CX1PESO"
        balanca_id = "CX1PESOBALANCA"
        tstpeso_id = "TSTPESO1"
    elif target_table_id.upper() == "TABCAIXA2":
        peso_id = "CX2PESO"
        balanca_id = "CX2PESOBALANCA"
        tstpeso_id = "TSTPESO2"
    else:
        logging.error(f"ID de tabela '{target_table_id}' não esperado.")
        return gerar_erro_xml_responsev2(f"ID de tabela desconhecido: {target_table_id}", "Erro Configuração", 400)

    # 3. Extrair TSTPESO da linha alvo
    tstpeso_valor = "0"
    # Busca Field por <Id> minúsculo no input
    tstpeso_field_value_elem = target_row_element.xpath(f".//Field[Id='{tstpeso_id}']/Value")
    if tstpeso_field_value_elem and tstpeso_field_value_elem[0].text is not None:
        value_text = tstpeso_field_value_elem[0].text.strip()
        if value_text in ["0", "1"]:
            tstpeso_valor = value_text
            logging.debug(f"Valor TSTPESO ('{tstpeso_id}') extraído: '{tstpeso_valor}'")
        else:
            logging.warning(f"Valor TSTPESO ('{tstpeso_id}') inválido ('{value_text}'). Usando '0'.")
    else:
        logging.warning(f"Campo TSTPESO ('{tstpeso_id}') não encontrado/vazio na linha atual. Usando '0'.")

    # 4. Gerar novos valores de peso
    peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor)
    logging.info(f"Valores gerados para Tabela '{target_table_id}': {peso_id}={peso_novo}, {balanca_id}={pesobalanca_novo}")

    # 5. Construir e retornar a resposta no formato ResponseV2
    return construir_resposta_responsev2(
        target_table_id=target_table_id,
        peso_id=peso_id,
        balanca_id=balanca_id,
        peso_novo=peso_novo,
        pesobalanca_novo=pesobalanca_novo,
        target_table_element=target_table_element,
        target_row_index=target_row_index
    )