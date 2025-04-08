from flask import Flask, request, Response
import xml.etree.ElementTree as ET
import random
import logging # Adicionado para melhor depuração
from io import StringIO # Necessário para ET.parse

# --- Configuração Básica ---
app = Flask(__name__)
# Use INFO ou DEBUG
logging.basicConfig(level=logging.DEBUG)

# Função de erro simples (substitua pela sua se 'utils' não estiver disponível)
def gerar_erro(mensagem, status_code=400):
    logging.error(f"Gerando erro: {mensagem}")
    xml_erro = f"<Error><Message>{mensagem}</Message></Error>"
    return Response(xml_erro.encode('utf-8'), status=status_code, content_type='application/xml; charset=utf-8')

# --- Funções Auxiliares ---

def gerar_valores_peso(tstpeso):
    """Gera peso e pesobalanca baseado no valor de TSTPESO."""
    def formatar_numero():
        return "{:.3f}".format(random.uniform(0.5, 500)).replace('.', ',')
    logging.debug(f"Gerando peso com TSTPESO = '{tstpeso}'")
    if tstpeso == "0":
        valor = formatar_numero(); return valor, valor
    elif tstpeso == "1":
        peso = formatar_numero(); pesobalanca = formatar_numero()
        while peso == pesobalanca: pesobalanca = formatar_numero()
        return peso, pesobalanca
    else: # Fallback
        valor = formatar_numero(); return valor, valor

def find_field_value_element(fields_container, field_id):
    """Encontra o elemento <Value> de um <Field> com um <Id> específico."""
    if fields_container is None:
        return None
    for field in fields_container.findall("./Field"):
        id_elem = field.find("Id") # Busca pelo elemento Id
        if id_elem is not None and id_elem.text == field_id:
            return field.find("Value") # Retorna o elemento Value
    return None

def get_field_value_text(fields_container, field_id):
    """Obtém o texto do elemento <Value> de um <Field> com um <Id> específico."""
    value_elem = find_field_value_element(fields_container, field_id)
    # Retorna o texto se existir, senão string vazia
    return value_elem.text.strip() if value_elem is not None and value_elem.text is not None else ""

def set_field_value_text(fields_container, field_id, new_value):
    """Define o texto do elemento <Value> de um <Field> com um <Id> específico."""
    value_elem = find_field_value_element(fields_container, field_id)
    if value_elem is not None:
        value_elem.text = new_value
        logging.debug(f"  -> Valor do campo '{field_id}' atualizado para '{new_value}'")
        return True
    else:
        # Opcional: Criar o campo se não existir? Por ora, apenas loga.
        logging.warning(f"  -> Campo '{field_id}' não encontrado para atualização.")
        return False

# --- Rota Principal ---
# (Não precisa ser uma função separada se for usada apenas aqui)
@app.route("/encaxotar_v2", methods=['POST']) # Assume que é POST para receber XML
def encaxotar_v2_route():
    logging.info(f"Recebida requisição {request.method} para /encaxotar_v2")
    if not request.data or 'xml' not in (request.content_type or '').lower():
         return gerar_erro("Requisição inválida. Content-Type deve ser XML e corpo não vazio.", 400)

    try:
        # Obter parâmetro 'balanca' da URL (MAIS SEGURO!)
        balanca_param = request.args.get('balanca', 'balanca1').lower()
        if balanca_param not in ["balanca1", "balanca2"]:
            return gerar_erro("Parâmetro 'balanca' inválido na URL.")

        xml_data_str = request.data.decode('utf-8')
        logging.debug("--- XML Recebido --- \n%s\n--------------------", xml_data_str)
        # Usar StringIO para ET.parse
        tree = ET.parse(StringIO(xml_data_str))
        root = tree.getroot() # Este é o elemento que será modificado

        # Determina os IDs baseado no parâmetro da URL
        table_id_alvo = "TABCAIXA1" if balanca_param == "balanca1" else "TABCAIXA2"
        peso_field_id = "CX1PESO" if balanca_param == "balanca1" else "CX2PESO"
        balanca_field_id = "CX1PESOBALANCA" if balanca_param == "balanca1" else "CX2PESOBALANCA"
        tstpeso_field_id = "TSTPESO1" if balanca_param == "balanca1" else "TSTPESO2"
        logging.debug(f"Processando para: balanca={balanca_param}, tabela={table_id_alvo}")

        # Encontra a TableField específica
        target_table_element = root.find(f".//TableField[Id='{table_id_alvo}']")

        if target_table_element is None:
             logging.error(f"TableField com Id '{table_id_alvo}' não encontrada no XML.")
             return gerar_erro(f"Tabela '{table_id_alvo}' não encontrada.")

        rows_container = target_table_element.find("./Rows")
        if rows_container is None:
             logging.error(f"Tabela '{table_id_alvo}' não possui a tag <Rows>.")
             return gerar_erro(f"Estrutura inválida para tabela '{table_id_alvo}'.")

        primeira_vazia_encontrada = False

        # Itera APENAS nas linhas da tabela alvo
        for row in rows_container.findall("./Row"):
            fields_container = row.find('Fields')
            if fields_container is None:
                 logging.warning("Linha encontrada sem container <Fields>, pulando.")
                 continue

            # Obtém os valores atuais de forma segura
            peso_atual = get_field_value_text(fields_container, peso_field_id)
            balanca_atual = get_field_value_text(fields_container, balanca_field_id)
            tstpeso_atual = get_field_value_text(fields_container, tstpeso_field_id)
            # Default para TSTPESO se não encontrado
            if tstpeso_atual == "":
                 tstpeso_atual = "0"
                 logging.warning(f"Campo '{tstpeso_field_id}' não encontrado ou vazio na linha, usando default '0'.")
            elif tstpeso_atual not in ["0", "1"]:
                 logging.warning(f"Valor inválido '{tstpeso_atual}' para '{tstpeso_field_id}', usando default '0'.")
                 tstpeso_atual = "0"


            logging.debug(f"  Verificando linha: Peso='{peso_atual}', Balanca='{balanca_atual}', TST='{tstpeso_atual}'")

            # Verifica se esta é a primeira linha vazia
            if not primeira_vazia_encontrada and (peso_atual == "" or balanca_atual == ""):
                logging.info(f"  Encontrada primeira linha vazia. TSTPESO a usar: '{tstpeso_atual}'")
                novo_peso, novo_balanca = gerar_valores_peso(tstpeso_atual)
                logging.info(f"  Novos valores gerados: Peso={novo_peso}, Balanca={novo_balanca}")

                # Modifica os elementos Value DENTRO da árvore 'root'
                set_field_value_text(fields_container, peso_field_id, novo_peso)
                set_field_value_text(fields_container, balanca_field_id, novo_balanca)
                # Garante que o TSTPESO usado esteja refletido (caso tenha sido default)
                set_field_value_text(fields_container, tstpeso_field_id, tstpeso_atual)

                primeira_vazia_encontrada = True
                # NÃO DÊ BREAK AQUI se você precisar que o XML de resposta
                # contenha TODAS as linhas originais (com a primeira vazia atualizada).
                # Se você só quisesse retornar a linha atualizada, daria break.

        if not primeira_vazia_encontrada:
            logging.warning(f"Nenhuma linha com '{peso_field_id}' ou '{balanca_field_id}' vazios foi encontrada na tabela '{table_id_alvo}'.")
            # Decide o que fazer: retornar erro ou o XML original?
            # Por ora, vamos retornar o XML como está, mas sem modificações.

        # --- Construir XML de resposta REUTILIZANDO a árvore modificada ---
        # A árvore 'root' foi modificada in-place.
        # Precisamos agora extrair a TableField modificada e colocá-la na estrutura de resposta.

        response_root = ET.Element('ResponseV2', {
            'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
            'xmlns:xsd': "http://www.w3.org/2001/XMLSchema"
        })
        message = ET.SubElement(response_root, 'MessageV2')
        ET.SubElement(message, 'Text').text = 'Consulta realizada com sucesso.'

        return_value = ET.SubElement(response_root, 'ReturnValueV2')
        response_fields_container = ET.SubElement(return_value, 'Fields')

        # Encontra a TableField modificada na árvore 'root'
        modified_table_element = root.find(f".//TableField[Id='{table_id_alvo}']")
        if modified_table_element is not None:
            # Limpa atributos indesejados ANTES de adicionar à resposta
            for row_elem in modified_table_element.findall('.//Row'):
                if 'IsCurrentRow' in row_elem.attrib:
                    del row_elem.attrib['IsCurrentRow']
            # Adiciona a TableField (agora modificada) à resposta
            response_fields_container.append(modified_table_element)
            logging.debug(f"TableField '{table_id_alvo}' (modificada) adicionada à resposta.")
        else:
            # Isso não deveria acontecer se a encontramos antes, mas por segurança
             logging.error(f"Falha ao re-encontrar TableField '{table_id_alvo}' após modificação.")

        ET.SubElement(return_value, 'ShortText').text = 'Pressione Lixeira para nova consulta'
        ET.SubElement(return_value, 'LongText')
        ET.SubElement(return_value, 'Value').text = '58'

        # Serializa a NOVA árvore de resposta
        xml_str = ET.tostring(response_root, encoding='utf-16', xml_declaration=True)
        logging.debug("--- XML de Resposta (UTF-16) ---\n%s\n---------------------------", xml_str.decode('utf-16', errors='ignore'))
        return Response(xml_str, content_type='application/xml; charset=utf-16')

    except ET.ParseError as e:
        logging.error(f"Erro de Parse XML: {e}")
        return gerar_erro(f"XML mal formatado: {e}", 400)
    except Exception as e:
        logging.exception("Erro inesperado no processamento") # Loga o traceback completo
        return gerar_erro(f"Erro interno no servidor: {str(e)}", 500)


# --- Execução ---
if __name__ == '__main__':
    # debug=True é útil, mas desative em produção
    app.run(debug=True, host='0.0.0.0', port=5001)