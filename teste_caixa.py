from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import BytesIO

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
app = Flask(__name__)

# --- Funções Auxiliares (Mantidas e/ou Adaptadas) ---

def gerar_valores_peso(tstpeso_valor):
    """Gera valores de peso aleatórios para balança, considerando TSTPESO."""
    def formatar_numero():
        # Gera número com 2 casas decimais e vírgula como separador
        return "{:.2f}".format(random.uniform(0.5, 500)).replace('.', ',')

    logging.debug(f"Gerando peso com TSTPESO = '{tstpeso_valor}'")
    # Garante que a comparação funcione mesmo se tstpeso_valor for None ou não for string
    if str(tstpeso_valor).strip() == "0":
        valor = formatar_numero()
        logging.debug(f"TSTPESO=0, gerado PESO={valor}, PESOBALANCA={valor}")
        return valor, valor
    else:
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        # Garante que os pesos sejam diferentes se TSTPESO não for "0"
        while peso == pesobalanca:
            pesobalanca = formatar_numero()
        logging.debug(f"TSTPESO!=0, gerado PESO={peso}, PESOBALANCA={pesobalanca}")
        return peso, pesobalanca

def gerar_erro_xml_simples(mensagem, status_code=400):
    """Gera uma resposta de erro simples em XML UTF-16."""
    logging.error(f"Gerando erro XML simples: {mensagem}")
    # Cria um XML simples para o erro
    root = etree.Element("Error")
    etree.SubElement(root, "Message").text = mensagem
    # Serializa com declaração UTF-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(root, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

# --- Rota Principal Corrigida ---


def encaixotar_v2():
    xml_data = request.data
    if not xml_data:
        return gerar_erro_xml_simples("Request body vazio.", 400)

    logging.debug("--- Iniciando processamento /teste_caixa ---")
    logging.debug("XML Recebido (início):\n%s", xml_data[:500].decode('utf-16', errors='ignore')) # Log seguro

    try:
        # Tenta parsear como UTF-16, comum em ambientes .NET/Officetrack
        parser = etree.XMLParser(recover=True, encoding='utf-16')
        root = etree.fromstring(xml_data, parser=parser)
    except etree.XMLSyntaxError as e:
        logging.exception("Erro ao parsear XML de entrada (UTF-16).")
        return gerar_erro_xml_simples(f"Erro de sintaxe no XML: {e}", 400)
    except Exception as e:
         logging.exception("Erro inesperado ao parsear XML.")
         # Pode ser um problema de encoding ou outro erro
         return gerar_erro_xml_simples(f"Erro inesperado no parse XML: {e}. Verifique o encoding.", 500)

    target_table_element = None
    target_row_element = None
    target_table_id = None
    target_row_index = -1 # Índice da linha alvo dentro de sua tabela

    # 1. Encontrar a Tabela e a Linha com IsCurrentRow="True"
    found_current = False
    table_fields = root.xpath(".//TableField") # Busca TableField em qualquer lugar dentro de Fields
    if not table_fields:
         logging.warning("Nenhum elemento <TableField> encontrado no XML de entrada.")
         return gerar_erro_xml_simples("Nenhum TableField encontrado no XML de entrada.", 400)

    for table_field in table_fields:
        # Encontra o ID da tabela (elemento filho <Id>)
        table_id_elem = table_field.find("Id")
        current_table_id = table_id_elem.text.strip() if table_id_elem is not None and table_id_elem.text else None
        if not current_table_id:
             logging.warning("Encontrado TableField sem elemento <Id> filho. Ignorando.")
             continue # Pula esta tabela se não tiver ID

        rows = table_field.xpath(".//Row")
        logging.debug(f"Verificando Tabela '{current_table_id}' com {len(rows)} linhas.")
        for idx, row in enumerate(rows):
            if row.get("IsCurrentRow") == "True":
                target_table_element = table_field
                target_row_element = row
                target_row_index = idx
                target_table_id = current_table_id # Armazena o ID da tabela correta
                logging.info(f"Encontrada linha IsCurrentRow='True' na tabela '{target_table_id}' no índice {target_row_index}.")
                found_current = True
                break # Para de procurar linhas nesta tabela
        if found_current:
            break # Para de procurar em outras tabelas

    if not found_current:
        logging.warning("Nenhuma linha com IsCurrentRow='True' encontrada em nenhuma tabela.")
        return gerar_erro_xml_simples("Nenhuma linha com IsCurrentRow='True' encontrada.", 400)

    # 2. Determinar IDs dos campos com base na tabela encontrada
    if target_table_id == "TABCAIXA1":
        peso_id = "CX1PESO"
        balanca_id = "CX1PESOBALANCA"
        tstpeso_id = "TSTPESO1"
    elif target_table_id == "TABCAIXA2":
        peso_id = "CX2PESO"
        balanca_id = "CX2PESOBALANCA"
        tstpeso_id = "TSTPESO2"
    else:
        logging.error(f"ID de tabela '{target_table_id}' não esperado para campos de peso.")
        return gerar_erro_xml_simples(f"ID de tabela desconhecido encontrado: {target_table_id}", 400)

    # 3. Extrair TSTPESO da linha alvo
    tstpeso_valor = "0" # Valor padrão
    # Busca o Field com o Id correto DENTRO da target_row_element
    tstpeso_field_value_elem = target_row_element.xpath(f".//Field[Id='{tstpeso_id}']/Value")
    if tstpeso_field_value_elem and tstpeso_field_value_elem[0].text is not None:
        value_text = tstpeso_field_value_elem[0].text.strip()
        if value_text in ["0", "1"]:
            tstpeso_valor = value_text
            logging.debug(f"Valor TSTPESO ('{tstpeso_id}') extraído da linha alvo: '{tstpeso_valor}'")
        else:
            logging.warning(f"Valor TSTPESO ('{tstpeso_id}') inválido ('{value_text}') na linha atual. Usando '0'.")
    else:
        logging.warning(f"Campo TSTPESO ('{tstpeso_id}') não encontrado ou vazio na linha atual. Usando '0'.")

    # 4. Gerar novos valores de peso
    peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor)
    logging.info(f"Valores gerados para Tabela '{target_table_id}': {peso_id}={peso_novo}, {balanca_id}={pesobalanca_novo}")

    # 5. Construir o XML de Resposta (<DynamicTask>)
    NSMAP_DYNAMIC_TASK = {None: "http://tempuri.org/"} # Namespace padrão
    response_root = etree.Element("DynamicTask", nsmap=NSMAP_DYNAMIC_TASK)
    table_fields_container = etree.SubElement(response_root, "TableFields")

    # Cria a TableField na resposta com o ID correto como atributo
    response_table = etree.SubElement(table_fields_container, "TableField", Id=target_table_id)
    response_rows_container = etree.SubElement(response_table, "Rows")

    # Itera pelas linhas ORIGINAIS da tabela alvo, ATÉ a linha atual (inclusive)
    original_rows = target_table_element.xpath(".//Row")
    for idx, original_row in enumerate(original_rows):
        if idx > target_row_index:
            logging.debug(f"Parando de adicionar linhas no índice {idx}. Limite ({target_row_index}) atingido.")
            break # Não inclui linhas após a atual

        # Cria a linha na resposta, copiando atributos da original
        response_row = etree.SubElement(response_rows_container, "Row", **original_row.attrib)
        # Cria o container Fields para a linha da resposta
        response_fields = etree.SubElement(response_row, "Fields")

        if idx == target_row_index:
            # É a linha atual: Adiciona APENAS os campos de peso NOVOS
            logging.debug(f"Adicionando campos de peso GERADOS à linha índice {idx} (IsCurrentRow=True).")
            field_peso = etree.SubElement(response_fields, "Field")
            etree.SubElement(field_peso, "Id").text = peso_id
            etree.SubElement(field_peso, "Value").text = peso_novo

            field_balanca = etree.SubElement(response_fields, "Field")
            etree.SubElement(field_balanca, "Id").text = balanca_id
            etree.SubElement(field_balanca, "Value").text = pesobalanca_novo
        else:
            # É uma linha ANTERIOR: Adiciona APENAS o campo de peso ORIGINAL (CXnPESO)
            logging.debug(f"Adicionando campo de peso ORIGINAL à linha índice {idx}.")
            original_peso_field_value = "" # Default para caso não encontre
            # Busca o valor do campo de peso na linha original
            original_peso_value_elem = original_row.xpath(f".//Field[Id='{peso_id}']/Value")
            if original_peso_value_elem and original_peso_value_elem[0].text is not None:
                original_peso_field_value = original_peso_value_elem[0].text

            # Adiciona o campo de peso original à resposta
            field_peso = etree.SubElement(response_fields, "Field")
            etree.SubElement(field_peso, "Id").text = peso_id
            etree.SubElement(field_peso, "Value").text = original_peso_field_value

    # 6. Serializar e retornar a resposta
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    # `tostring` com default namespace requer atenção especial, mas lxml geralmente lida bem.
    xml_body = etree.tostring(response_root, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body

    logging.debug("XML de Resposta Final (Início):\n%s", xml_str_final[:500])
    logging.info("--- Processamento /teste_caixa concluído com sucesso ---")
    return Response(xml_str_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

