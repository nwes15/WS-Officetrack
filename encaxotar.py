from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import StringIO

app = Flask(__name__)

# Use INFO para menos logs em produção, DEBUG para mais detalhes
logging.basicConfig(level=logging.DEBUG)


def gerar_erro(mensagem, status_code=400):
    """Retorna uma resposta XML de erro simples."""
    logging.error(f"Gerando erro: {mensagem}")
    # Garante codificação UTF-8 para o erro
    xml_erro = f"<Error><Message>{mensagem}</Message></Error>"
    return Response(xml_erro.encode('utf-8'), status=status_code, content_type='application/xml; charset=utf-8')

def extrair_dados_estruturados_xml(xml_data):
    """Extrai dados do XML preservando a estrutura para encontrar TSTPESO."""
    # (Função que preserva a estrutura de tabelas/linhas)
    extracted_data = {"metadata": {}, "top_level_fields": {}, "table_fields": {}}
    try:
        logging.debug(f"Iniciando extração estruturada (tamanho: {len(xml_data)} bytes)")
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        # Garante que temos uma string para StringIO
        xml_string = xml_data if isinstance(xml_data, str) else xml_data.decode('utf-8')
        tree = etree.parse(StringIO(xml_string), parser)
        root = tree.getroot()
        # Opcional: Extrair metadados
        # extracted_data["metadata"]["EmployeeNumber"] = root.findtext("./Employee/EmployeeNumber")

        main_fields_container = root.find("./Fields")
        if main_fields_container is not None:
            for element in main_fields_container.iterchildren():
                element_id = element.findtext("Id")
                if not element_id: continue

                if element.tag == "Field":
                    extracted_data["top_level_fields"][element_id] = element.findtext("Value", default="").strip()

                elif element.tag == "TableField": # Foco em extrair tabelas
                    table_rows_data = []
                    rows_container = element.find("./Rows")
                    if rows_container is not None:
                        for row_idx, row in enumerate(rows_container.findall("./Row")):
                            # Guarda dados da linha e atributos
                            row_fields_data = {'_attributes': dict(row.attrib), '_row_index': row_idx}
                            nested_fields_container = row.find("./Fields")
                            if nested_fields_container is not None:
                                for nested_field in nested_fields_container.findall("./Field"):
                                    nested_field_id = nested_field.findtext("Id")
                                    if nested_field_id:
                                        row_fields_data[nested_field_id] = nested_field.findtext("Value", default="").strip()
                            # Adiciona a linha apenas se tiver campos além dos metadados internos
                            if len(row_fields_data) > 2:
                                table_rows_data.append(row_fields_data)
                        extracted_data["table_fields"][element_id] = table_rows_data
        # Log para depuração (opcional)
        # try:
        #     import json
        #     logging.debug(f"Extração Estruturada Concluída:\n{json.dumps(extracted_data, indent=2)}")
        # except ImportError:
        #     logging.debug(f"Extração Estruturada Concluída: {extracted_data}")
        return extracted_data
    except Exception as e:
        logging.exception("Erro ao processar XML na extração estruturada")
        return None


def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera peso e pesobalanca baseado no valor de TSTPESO."""
    # (Função mantida como estava)
    def formatar_numero():
        return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso para balanca '{balanca_id}' com TSTPESO = '{tstpeso_valor}'")
    if tstpeso_valor == "0":
        valor = formatar_numero(); return valor, valor
    elif tstpeso_valor == "1":
        peso = formatar_numero(); pesobalanca = formatar_numero()
        while peso == pesobalanca: pesobalanca = formatar_numero()
        return peso, pesobalanca
    else: # Fallback
        valor = formatar_numero(); return valor, valor

def adicionar_campo_xml(parent_element, field_id, value):
    """Cria e adiciona um elemento <Field> com <Id> e <Value>."""
    # (Função mantida como estava)
    field = etree.SubElement(parent_element, "Field")
    etree.SubElement(field, "Id").text = field_id
    etree.SubElement(field, "Value").text = value if value is not None else ""


def gerar_resposta_xml_final(peso, pesobalanca, balanca_id, tstpeso_id, tstpeso_valor):
    """
    Gera a resposta XML completa (ResponseV2) contendo APENAS
    a TableField relevante (com uma linha e 3 campos essenciais).
    """
    # (Função que gera a resposta mínima desejada, como na resposta anterior)
    logging.debug(f"Gerando resposta FINAL para balanca '{balanca_id}'")
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    return_value = etree.SubElement(response, "ReturnValueV2")
    response_fields_container = etree.SubElement(return_value, "Fields")
    tabela_id_alvo = "TABCAIXA1" if balanca_id == "balanca1" else "TABCAIXA2"
    peso_field_id = "CX1PESO" if balanca_id == "balanca1" else "CX2PESO"
    pesobalanca_field_id = "CX1PESOBALANCA" if balanca_id == "balanca1" else "CX2PESOBALANCA"
    response_table = etree.SubElement(response_fields_container, "TableField")
    etree.SubElement(response_table, "Id").text = tabela_id_alvo
    response_rows_container = etree.SubElement(response_table, "Rows")
    response_row = etree.SubElement(response_rows_container, "Row")
    response_row_fields_container = etree.SubElement(response_row, "Fields")
    adicionar_campo_xml(response_row_fields_container, tstpeso_id, tstpeso_valor)
    adicionar_campo_xml(response_row_fields_container, peso_field_id, peso)
    adicionar_campo_xml(response_row_fields_container, pesobalanca_field_id, pesobalanca)
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"
    xml_bytes = etree.tostring(response, encoding="utf-16", xml_declaration=True, pretty_print=True)
    logging.debug("XML de Resposta FINAL Gerado (UTF-16):\n%s", xml_bytes.decode('utf-16', errors='ignore'))
    return xml_bytes, 'application/xml; charset=utf-16'

# --- Rota Principal ---
# Renomeando a função da rota para evitar conflito se você colar junto

def encaxotar():
    logging.info(f"Recebida requisição {request.method} para /funcao_unica_corrigida")
    try:
        balanca = request.args.get('balanca', 'balanca1').lower()
        if balanca not in ["balanca1", "balanca2"]:
            return gerar_erro("Valor de 'balanca' inválido na URL.")

        # --- Obter XML ---
        content_type = request.content_type or ''
        xml_data_bytes = None
        if 'xml' in content_type.lower():
            if request.data: xml_data_bytes = request.data
            else: return gerar_erro("Corpo XML vazio.")
        else: # Fallback para form data
            xml_data_str = request.form.get('xml') or request.form.get('TextXML') or next(iter(request.form.values()), None)
            if xml_data_str: xml_data_bytes = xml_data_str.encode('utf-8')
            else: return gerar_erro("Nenhum dado XML encontrado.")
        if not xml_data_bytes: return gerar_erro("Dados XML não obtidos.")

        # --- Processar XML com a função CORRETA ---
        extracted_data = extrair_dados_estruturados_xml(xml_data_bytes)
        if extracted_data is None:
            return gerar_erro("Falha ao processar estrutura XML.")

        # --- Determinar TSTPESO da estrutura CORRETA ---
        tstpeso_id_a_usar = "TSTPESO1" if balanca == "balanca1" else "TSTPESO2"
        tabela_id_a_usar = "TABCAIXA1" if balanca == "balanca1" else "TABCAIXA2"
        tstpeso_valor = "0" # Default

        # Acessa a estrutura extraída corretamente
        tabela_alvo_data = extracted_data.get("table_fields", {}).get(tabela_id_a_usar, [])
        if tabela_alvo_data:
            linha_alvo = None
            # Prioriza linha com IsCurrentRow=True
            for row in tabela_alvo_data:
                 if row.get('_attributes', {}).get('IsCurrentRow', '').lower() == 'true':
                      linha_alvo = row
                      logging.debug(f"Usando linha 'CurrentRow' da tabela {tabela_id_a_usar}")
                      break
            # Senão, usa a primeira linha se existir
            if linha_alvo is None and tabela_alvo_data:
                 linha_alvo = tabela_alvo_data[0]
                 logging.debug(f"Usando primeira linha da tabela {tabela_id_a_usar}")

            if linha_alvo: # Verifica se encontramos uma linha alvo
                # Pega TSTPESO da linha alvo (que é um dicionário)
                tstpeso_valor = linha_alvo.get(tstpeso_id_a_usar, "0")
                logging.debug(f"Valor de {tstpeso_id_a_usar} encontrado na linha alvo: '{tstpeso_valor}'")
            else:
                logging.warning(f"Nenhuma linha (Current ou primeira) encontrada na tabela '{tabela_id_a_usar}'. Usando TSTPESO padrão '0'.")
        else:
            logging.warning(f"Tabela alvo '{tabela_id_a_usar}' não encontrada ou vazia. Usando TSTPESO padrão '0'.")

        # Validação final do TSTPESO
        if tstpeso_valor not in ["0", "1"]:
            logging.warning(f"Valor TSTPESO inválido '{tstpeso_valor}' encontrado, usando padrão '0'.")
            tstpeso_valor = "0"

        # --- Gerar Pesos ---
        peso, pesobalanca = gerar_valores_peso(tstpeso_valor, balanca)

        # --- Gerar Resposta XML FINAL (com a função correta) ---
        xml_resposta_bytes, content_type_resp = gerar_resposta_xml_final(
            peso, pesobalanca, balanca, tstpeso_id_a_usar, tstpeso_valor
        )
        return Response(xml_resposta_bytes, content_type=content_type_resp)

    except Exception as e:
        logging.exception("Erro fatal na rota /funcao_unica_corrigida")
        return gerar_erro(f"Erro interno inesperado: {str(e)}", 500)