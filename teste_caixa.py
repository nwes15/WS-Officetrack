import logging
import random
from io import BytesIO
from flask import Flask, request, Response
from lxml import etree

# --- Configuração do Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares Fornecidas ---

def gerar_erro_xml_padrao(mensagem, short_text="Erro", status_code=400):
    """Gera uma resposta de erro XML padrão."""
    logging.error(f"Gerando erro XML: {mensagem}")
    nsmap = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance','xsd': 'http://www.w3.org/2001/XMLSchema'}
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "Fields") # Campos podem ficar vazios no erro
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0" # Valor de retorno padrão em caso de erro

    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str_final = xml_declaration + xml_body
    return Response(xml_str_final.encode("utf-16"), status=status_code, content_type="application/xml; charset=utf-16")

def extrair_tstpeso_da_tabela(xml_bytes, tabela_id_alvo, tstpeso_id_alvo):
    """Extrai o valor TSTPESO da linha atual (ou primeira linha) da tabela especificada.
       NOTA: Esta função re-parseia o XML. É mais eficiente extrair da árvore já parseada."""
    if not xml_bytes: return "0"
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(BytesIO(xml_bytes), parser)
        root = tree.getroot()
        xpath_tabela = f".//TableField[Id='{tabela_id_alvo}']"
        tabela_elements = root.xpath(xpath_tabela)
        if not tabela_elements: return "0"

        tabela_element = tabela_elements[0]
        linha_alvo = None
        # Prioriza IsCurrentRow='True'
        current_rows = tabela_element.xpath(".//Row[@IsCurrentRow='True']")
        if current_rows:
            linha_alvo = current_rows[0]
        else:
            # Fallback para a primeira linha se não houver IsCurrentRow='True'
            primeira_linha_list = tabela_element.xpath(".//Row[1]")
            if primeira_linha_list:
                linha_alvo = primeira_linha_list[0]

        if linha_alvo is None: return "0" # Nenhuma linha encontrada

        xpath_tstpeso = f".//Field[Id='{tstpeso_id_alvo}']/Value"
        tstpeso_elements = linha_alvo.xpath(xpath_tstpeso)

        if tstpeso_elements and tstpeso_elements[0].text is not None:
             value_text = tstpeso_elements[0].text.strip()
             # Garante que o valor retornado seja "0" ou "1"
             return value_text if value_text in ["0", "1"] else "0"
        return "0" # Campo ou valor não encontrado, retorna default "0"

    except Exception as e:
        logging.exception(f"Erro ao extrair TSTPESO da tabela {tabela_id_alvo}: {e}")
        return "0" # Retorna default em caso de erro

def gerar_valores_peso(tstpeso_valor, balanca_id):
    """Gera valores de peso (e pesobalanca se necessário) baseado em TSTPESO."""
    logging.debug(f"Gerando peso com TSTPESO='{tstpeso_valor}' para balança '{balanca_id}'")
    def formatar_numero():
        # Gera um número entre 0.500 e 500.000
        num = random.uniform(0.5, 500.0)
        # Formata para 3 casas decimais com vírgula
        return "{:.3f}".format(num).replace('.', ',')

    if tstpeso_valor == "0":
        # Modo normal: Peso e Peso Balança são iguais
        valor = formatar_numero()
        logging.debug(f"Modo Normal (TSTPESO=0): Peso={valor}, PesoBalanca={valor}")
        return valor, valor
    elif tstpeso_valor == "1":
        # Modo teste: Peso e Peso Balança são diferentes
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        # Garante que sejam diferentes
        while peso == pesobalanca:
            logging.debug("Peso e PesoBalanca gerados iguais no modo TSTPESO=1, regerando PesoBalanca...")
            pesobalanca = formatar_numero()
        logging.debug(f"Modo Teste (TSTPESO=1): Peso={peso}, PesoBalanca={pesobalanca}")
        return peso, pesobalanca
    else:
        # Caso inesperado (TSTPESO diferente de "0" ou "1"), assume modo normal
        logging.warning(f"Valor TSTPESO inesperado ('{tstpeso_valor}'). Assumindo modo normal.")
        valor = formatar_numero()
        logging.debug(f"Modo Fallback: Peso={valor}, PesoBalanca={valor}")
        return valor, valor


def encaixotar_v2():
    logging.info("--- Nova Requisição POST para /teste_caixa ---")

    try:
        # 1. Obter Dados da Requisição
        if 'Data' not in request.form:
             logging.error("Campo 'Data' não encontrado no formulário da requisição.")
             return gerar_erro_xml_padrao("Campo 'Data' ausente na requisição.", "Erro Requisição", 400)

        xml_str = request.form['Data']
        # A entrada é UTF-16, então codificamos para bytes UTF-16 para o parser lxml
        try:
            xml_bytes = xml_str.encode('utf-16')
            logging.debug(f"XML Recebido (bytes decodificados para log): \n{xml_bytes.decode('utf-16')[:500]}...") # Log inicial do XML
        except Exception as e:
             logging.error(f"Erro ao codificar XML de entrada para UTF-16: {e}")
             return gerar_erro_xml_padrao("Erro ao processar encoding do XML de entrada.", "Erro Encoding", 400)

        balanca = request.args.get("balanca", "balanca1").lower() # Default para balanca1 se não especificado
        logging.info(f"Balança selecionada: {balanca}")

        # 2. Parsear o XML
        try:
            parser = etree.XMLParser(recover=True, encoding='utf-16') # Especifica encoding aqui também
            # Usar BytesIO para parsear a string de bytes
            tree = etree.parse(BytesIO(xml_bytes), parser)
            root = tree.getroot()
            logging.debug("XML parseado com sucesso.")
        except etree.XMLSyntaxError as e:
            logging.error(f"Erro de sintaxe ao parsear XML: {e}")
            return gerar_erro_xml_padrao(f"Erro de sintaxe no XML recebido: {e}", "Erro XML", 400)
        except Exception as e:
            logging.exception("Erro inesperado ao parsear XML")
            return gerar_erro_xml_padrao("Erro interno ao parsear XML.", "Erro Parse", 500)


        # 3. Determinar IDs Alvo
        if balanca == "balanca1":
            tabela_id = "TABCAIXA1"
            peso_id = "CX1PESO"
            pesobalanca_id = "CX1PESOBALANCA"
            tstpeso_id = "TSTPESO1"
        elif balanca == "balanca2":
            tabela_id = "TABCAIXA2"
            peso_id = "CX2PESO"
            pesobalanca_id = "CX2PESOBALANCA"
            tstpeso_id = "TSTPESO2"
        else:
            logging.error(f"Parâmetro 'balanca' inválido: {balanca}")
            return gerar_erro_xml_padrao(f"Valor inválido para o parâmetro 'balanca': {balanca}", "Erro Parâmetro", 400)
        logging.debug(f"IDs alvo definidos: Tabela={tabela_id}, Peso={peso_id}, PesoBalanca={pesobalanca_id}, TstPeso={tstpeso_id}")

        # 4. Encontrar a Tabela Alvo
        tabela_elements = root.xpath(f".//TableField[Id='{tabela_id}']")
        if not tabela_elements:
            logging.error(f"Tabela com ID '{tabela_id}' não encontrada no XML.")
            # Tenta retornar o XML original como resposta neutra ou um erro? Vamos retornar erro.
            return gerar_erro_xml_padrao(f"Tabela '{tabela_id}' não encontrada.", "Erro Estrutura", 400)
        tabela = tabela_elements[0] # Pega a primeira tabela encontrada com esse ID
        logging.debug(f"Tabela '{tabela_id}' encontrada.")

        # 5. Encontrar a Linha Atual (IsCurrentRow='True') DENTRO da tabela encontrada
        # O '.' no início do XPath torna a busca relativa ao elemento 'tabela'
        current_row_elements = tabela.xpath(".//Row[@IsCurrentRow='True']")
        if not current_row_elements:
            logging.error(f"Nenhuma linha com IsCurrentRow='True' encontrada dentro da tabela '{tabela_id}'.")
            # Poderia tentar pegar a primeira linha como fallback, ou retornar erro. Retornando erro.
            return gerar_erro_xml_padrao(f"Linha atual (IsCurrentRow='True') não encontrada na tabela '{tabela_id}'.", "Erro Estrutura", 400)
        current_row = current_row_elements[0] # Pega a primeira linha encontrada marcada como atual
        logging.debug("Linha atual (IsCurrentRow='True') encontrada.")

        # 6. Extrair o valor ATUAL de TSTPESO* da linha atual encontrada
        tstpeso_valor_atual = "0" # Valor default caso não encontre
        tstpeso_value_elem = current_row.xpath(f".//Field[Id='{tstpeso_id}']/Value")
        if tstpeso_value_elem and tstpeso_value_elem[0].text is not None:
             valor_lido = tstpeso_value_elem[0].text.strip()
             if valor_lido in ["0", "1"]:
                  tstpeso_valor_atual = valor_lido
             else:
                 logging.warning(f"Valor TSTPESO lido ('{valor_lido}') inválido na linha atual. Usando default '0'.")
        else:
             logging.warning(f"Campo '{tstpeso_id}' ou seu valor não encontrado na linha atual. Usando default '0'.")
        logging.info(f"Valor atual de '{tstpeso_id}' extraído: '{tstpeso_valor_atual}'")

        # 7. Gerar os Novos Valores de Peso usando a função auxiliar
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_atual, balanca)
        logging.info(f"Valores gerados - Peso: {peso_novo}, Peso Balança: {pesobalanca_novo}")

        # Defina aqui qual valor você quer ESCREVER no campo TSTPESO*.
        # O código original em encaixotar_v2 fixava em "0". Vamos manter isso.
        tstpeso_valor_a_definir = "0"
        logging.debug(f"Valor a ser definido para '{tstpeso_id}': '{tstpeso_valor_a_definir}'")

        # 8. Modificar os Valores na Linha Atual (current_row)
        modificacoes = 0
        for field in current_row.xpath(".//Field"): # Itera sobre os Fields DENTRO da linha atual
            field_id_elem = field.find("ID") # Procura pelo elemento ID
            if field_id_elem is None or field_id_elem.text is None:
                continue # Pula Field sem ID

            field_id = field_id_elem.text.strip() # Pega o texto do ID

            # Encontra o elemento Value DENTRO do Field atual
            value_elem = field.find("Value")
            if value_elem is None:
                # Se o campo Value não existe, podemos criá-lo ou ignorar
                # Vamos ignorar por segurança, assumindo que ele deveria existir
                logging.warning(f"Campo '{field_id}' na linha atual não possui tag <Value>. Ignorando.")
                continue

            # Atualiza o texto do elemento Value se o ID corresponder
            if field_id == peso_id:
                value_elem.text = peso_novo
                logging.debug(f"Campo '{peso_id}' atualizado para '{peso_novo}'")
                modificacoes += 1
            elif field_id == pesobalanca_id:
                value_elem.text = pesobalanca_novo
                logging.debug(f"Campo '{pesobalanca_id}' atualizado para '{pesobalanca_novo}'")
                modificacoes += 1
            elif field_id == tstpeso_id:
                value_elem.text = tstpeso_valor_a_definir
                logging.debug(f"Campo '{tstpeso_id}' atualizado para '{tstpeso_valor_a_definir}'")
                modificacoes += 1

        if modificacoes == 0:
            logging.warning("Nenhum dos campos alvo foi encontrado ou atualizado na linha atual.")
        elif modificacoes < 3:
             logging.warning(f"Apenas {modificacoes} de 3 campos alvo foram encontrados/atualizados na linha atual.")
        else:
            logging.info("Campos de peso atualizados com sucesso na linha atual.")


        # 9. Serializar o XML Modificado para a Resposta
        xml_declaracao = '<?xml version="1.0" encoding="utf-16"?>\n'
        # Serializa a árvore inteira (root) modificada
        try:
            xml_body_bytes = etree.tostring(root, encoding="utf-16", xml_declaration=False)
            xml_body_str = xml_body_bytes.decode("utf-16")
            xml_final_str = xml_declaracao + xml_body_str
            logging.debug(f"XML Final a ser retornado (parcial): \n{xml_final_str[:500]}...")

            # Codifica a string final de volta para bytes UTF-16 para a Response
            response_bytes = xml_final_str.encode('utf-16')

        except Exception as e:
            logging.exception("Erro ao serializar o XML modificado.")
            return gerar_erro_xml_padrao("Erro interno ao gerar resposta XML final.", "Erro Serialização", 500)

        # 10. Retornar a Resposta Flask
        return Response(response_bytes, content_type="application/xml; charset=utf-16", status=200)

    except Exception as e:
        # Captura geral para erros não esperados no fluxo principal
        logging.exception("Erro inesperado na rota /teste_caixa")
        return gerar_erro_xml_padrao("Erro interno inesperado no servidor.", "Erro Servidor", 500)