import logging
import random
from io import BytesIO
from flask import Flask, request, Response
from lxml import etree

# --- Configuração do Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Funções Auxiliares (gerar_erro_xml_padrao, extrair_tstpeso_da_tabela, gerar_valores_peso) ---
# [MANTENHA AS FUNÇÕES AUXILIARES EXATAMENTE COMO NO CÓDIGO ANTERIOR]
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

        # *** CORREÇÃO XPath AQUI também na função auxiliar ***
        xpath_tstpeso = f".//Fields/Field[Id='{tstpeso_id_alvo}']/Value"
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
        num = random.uniform(0.5, 500.0)
        return "{:.3f}".format(num).replace('.', ',')

    if tstpeso_valor == "0":
        valor = formatar_numero()
        logging.debug(f"Modo Normal (TSTPESO=0): Peso={valor}, PesoBalanca={valor}")
        return valor, valor
    elif tstpeso_valor == "1":
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        while peso == pesobalanca:
            logging.debug("Peso e PesoBalanca gerados iguais no modo TSTPESO=1, regerando PesoBalanca...")
            pesobalanca = formatar_numero()
        logging.debug(f"Modo Teste (TSTPESO=1): Peso={peso}, PesoBalanca={pesobalanca}")
        return peso, pesobalanca
    else:
        logging.warning(f"Valor TSTPESO inesperado ('{tstpeso_valor}'). Assumindo modo normal.")
        valor = formatar_numero()
        logging.debug(f"Modo Fallback: Peso={valor}, PesoBalanca={valor}")
        return valor, valor




def encaixotar_v2():
    logging.info("--- Nova Requisição POST para /teste_caixa ---")
    try:
        # 1. Obter Dados
        if 'Data' not in request.form:
             logging.error("Campo 'Data' não encontrado no formulário.")
             return gerar_erro_xml_padrao("Campo 'Data' ausente na requisição.", "Erro Requisição", 400)
        xml_str = request.form['Data']
        try:
            xml_bytes = xml_str.encode('utf-16')
            logging.debug(f"XML Recebido (bytes decodificados para log): \n{xml_bytes.decode('utf-16')[:500]}...")
        except Exception as e:
             logging.error(f"Erro ao codificar XML de entrada para UTF-16: {e}")
             return gerar_erro_xml_padrao("Erro ao processar encoding do XML de entrada.", "Erro Encoding", 400)

        balanca = request.args.get("balanca", "balanca1").lower()
        logging.info(f"Balança selecionada: {balanca}")

        # 2. Parsear XML de Entrada (<Form>)
        try:
            parser = etree.XMLParser(recover=True, encoding='utf-16')
            tree = etree.parse(BytesIO(xml_bytes), parser)
            root_form = tree.getroot() # Raiz do XML de entrada <Form>
            logging.debug("XML de entrada <Form> parseado com sucesso.")
        except Exception as e:
            logging.exception("Erro ao parsear XML de entrada <Form>")
            return gerar_erro_xml_padrao("Erro interno ao parsear XML de entrada.", "Erro Parse", 500)

        # 3. Determinar IDs Alvo
        if balanca == "balanca1":
            tabela_id, peso_id, pesobalanca_id, tstpeso_id = "TABCAIXA1", "CX1PESO", "CX1PESOBALANCA", "TSTPESO1"
        elif balanca == "balanca2":
             tabela_id, peso_id, pesobalanca_id, tstpeso_id = "TABCAIXA2", "CX2PESO", "CX2PESOBALANCA", "TSTPESO2"
        else:
            logging.error(f"Parâmetro 'balanca' inválido: {balanca}")
            return gerar_erro_xml_padrao(f"Valor inválido para 'balanca': {balanca}", "Erro Parâmetro", 400)
        logging.debug(f"IDs alvo: Tabela={tabela_id}, Peso={peso_id}, PesoBalanca={pesobalanca_id}, TstPeso={tstpeso_id}")

        # 4. Encontrar Tabela no XML de Entrada
        tabela_elements = root_form.xpath(f".//TableField[Id='{tabela_id}']")
        if not tabela_elements:
            logging.error(f"Tabela '{tabela_id}' não encontrada no XML de entrada.")
            return gerar_erro_xml_padrao(f"Tabela '{tabela_id}' não encontrada.", "Erro Estrutura", 400)
        tabela_modificar = tabela_elements[0] # Referência ao elemento <TableField> que VAMOS MODIFICAR
        logging.debug(f"Tabela '{tabela_id}' encontrada para modificação.")

        # 5. Encontrar Linha Atual na Tabela
        current_row_elements = tabela_modificar.xpath(".//Row[@IsCurrentRow='True']")
        if not current_row_elements:
            logging.error(f"Nenhuma linha IsCurrentRow='True' encontrada em '{tabela_id}'.")
            return gerar_erro_xml_padrao(f"Linha atual não encontrada na tabela '{tabela_id}'.", "Erro Estrutura", 400)
        current_row = current_row_elements[0]
        logging.debug("Linha atual (IsCurrentRow='True') encontrada.")

        # 6. Extrair Valor Atual TSTPESO* da Linha Atual
        tstpeso_valor_atual = "0"
        # *** CORREÇÃO XPath para encontrar o campo DENTRO de <Fields> ***
        tstpeso_value_elem = current_row.xpath(f".//Fields/Field[Id='{tstpeso_id}']/Value")
        if tstpeso_value_elem and tstpeso_value_elem[0].text is not None:
             valor_lido = tstpeso_value_elem[0].text.strip()
             tstpeso_valor_atual = valor_lido if valor_lido in ["0", "1"] else "0"
        else:
             logging.warning(f"Campo '{tstpeso_id}' ou valor não encontrado na linha atual. Usando default '0'.")
        logging.info(f"Valor atual de '{tstpeso_id}' extraído: '{tstpeso_valor_atual}'")

        # 7. Gerar Novos Valores de Peso
        peso_novo, pesobalanca_novo = gerar_valores_peso(tstpeso_valor_atual, balanca)
        logging.info(f"Valores gerados - Peso: {peso_novo}, Peso Balança: {pesobalanca_novo}")
        tstpeso_valor_a_definir = "0" # Mantendo a lógica de setar para '0'
        logging.debug(f"Valor a ser definido para '{tstpeso_id}': '{tstpeso_valor_a_definir}'")

        # 8. MODIFICAR os Valores na Linha Atual (current_row)
        modificacoes = 0
        # *** CORREÇÃO XPath para iterar nos Fields CORRETOS ***
        for field in current_row.xpath(".//Fields/Field"):
            field_id_elem = field.find("ID")
            if field_id_elem is None or field_id_elem.text is None: continue
            field_id = field_id_elem.text.strip()
            value_elem = field.find("Value")
            if value_elem is None: continue # Ignora se não houver <Value>

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

        if modificacoes == 3:
            logging.info("Todos os 3 campos alvo foram atualizados na linha atual.")
        elif modificacoes > 0:
             logging.warning(f"Apenas {modificacoes} de 3 campos alvo foram atualizados.")
        else:
            # Este warning não deve mais ocorrer com o XPath corrigido, mas mantemos por segurança
             logging.error("ERRO CRÍTICO: Nenhum campo alvo foi encontrado para atualização, mesmo com XPath corrigido.")
             # Considerar retornar erro se modificacoes == 0, pois algo está errado.
             return gerar_erro_xml_padrao(f"Nenhum campo ({peso_id}, {pesobalanca_id}, {tstpeso_id}) encontrado para atualizar.", "Erro Interno", 500)


        # 9. Construir a Resposta <ResponseV2>
        logging.debug("Construindo a resposta no formato <ResponseV2>")
        nsmap_resp = {'xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        response_root = etree.Element("ResponseV2", nsmap=nsmap_resp)

        # Mensagem (opcional, pode customizar)
        msg = etree.SubElement(response_root, "MessageV2")
        etree.SubElement(msg, "Text").text = "Operação concluída com sucesso." # Mensagem de exemplo

        # ReturnValue
        return_value = etree.SubElement(response_root, "ReturnValueV2")
        fields_resp = etree.SubElement(return_value, "Fields")

        # *** INSERIR A TABELA MODIFICADA ***
        # Adiciona a tabela que foi modificada (tabela_modificar) DENTRO de <Fields>
        # A tabela já contém a linha com os valores atualizados.
        fields_resp.append(tabela_modificar)
        logging.debug(f"Tabela '{tabela_id}' modificada foi anexada à resposta <ResponseV2>.")

        # Adicionar outros <Field> se necessário (ex: Test1, Num1 do seu exemplo)
        # Exemplo:
        # field_test1 = etree.SubElement(fields_resp, "Field")
        # etree.SubElement(field_test1, "ID").text = "Test1"
        # etree.SubElement(field_test1, "Value").text = "ValorFixoOuDinamico"

        # Outros campos de ReturnValue (ajuste conforme necessário)
        etree.SubElement(return_value, "ShortText").text = "SUCESSO"
        etree.SubElement(return_value, "LongText") # Vazio ou com mais detalhes
        etree.SubElement(return_value, "Value").text = "1" # Ou outro valor indicando sucesso

        # 10. Serializar <ResponseV2> e Retornar
        xml_declaracao = '<?xml version="1.0" encoding="utf-16"?>\n'
        try:
            # Serializa a nova raiz <ResponseV2>
            response_body_bytes = etree.tostring(response_root, encoding="utf-16", xml_declaration=False)
            response_final_str = xml_declaracao + response_body_bytes.decode('utf-16')
            logging.debug(f"XML Final <ResponseV2> a ser retornado (parcial): \n{response_final_str[:500]}...")

            # Codifica a string final para bytes UTF-16
            response_bytes = response_final_str.encode('utf-16')

        except Exception as e:
            logging.exception("Erro ao serializar a resposta <ResponseV2>.")
            return gerar_erro_xml_padrao("Erro interno ao gerar resposta XML final.", "Erro Serialização", 500)

        return Response(response_bytes, content_type="application/xml; charset=utf-16", status=200)

    except Exception as e:
        logging.exception("Erro inesperado na rota /teste_caixa")
        return gerar_erro_xml_padrao("Erro interno inesperado no servidor.", "Erro Servidor", 500)
