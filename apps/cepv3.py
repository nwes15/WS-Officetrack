from flask import request, Response
import requests
from lxml import etree
import logging
from utils.gerar_erro import gerar_erro_xml
from utils.adicionar_campo import adicionar_campo
from utils.adicionar_table_field import adicionar_table_field

def consultar_cepv3():
    try:
        content_type = request.headers.get("Content-Type", "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")
        
        # Tenta extrair o XML de várias fontes possíveis
        xml_data = None
        
        # Tenta do form primeiro (com vários nomes possíveis)
        if request.form:
            for possible_name in ["TextXML", "textxml", "xmldata", "xml", "application/x-www-form-urlencoded"]:
                if possible_name in request.form:
                    xml_data = request.form.get(possible_name)
                    logging.debug(f"XML encontrado no campo {possible_name}")
                    break
            
            # Se não encontrou por nome específico, tenta o primeiro campo do form
            if not xml_data and len(request.form) > 0:
                first_key = next(iter(request.form))
                xml_data = request.form.get(first_key)
                logging.debug(f"Usando primeiro campo do form: {first_key}")
        
        # Se não encontrou no form, tenta do corpo da requisição
        if not xml_data and request.data:
            try:
                xml_data = request.data.decode('utf-8')
                logging.debug("Usando dados brutos do corpo da requisição")
            except:
                pass
        
        if not xml_data:
            return gerar_erro_xml("Não foi possível encontrar dados XML na requisição", "Erro")
        
        logging.debug(f"XML para processar: {xml_data}")

        # Tenta fazer o parse do XML
        try:
            root = etree.fromstring(xml_data.encode("utf-8"))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("Erro ao processar o XML recebido.", "Erro")

        # Processa os campos do XML
        campos = processar_campos(root)

        # Faz a requisição à API ViaCEP
        cep = campos.get("CEP")
        if not cep:
            return gerar_erro_xml("Erro: CEP não informado no campo CEP.", "CEP invalido")

        # Primeira tentativa: API padrão do ViaCEP
        response = requests.get(f"https://viacep.com.br/ws/{cep}/json/")
        if response.status_code != 200:
            return gerar_erro_xml("Erro ao consultar o CEP - Verifique e tente novamente.", "Erro")

        data = response.json()
        if "erro" in data:
            return gerar_erro_xml("Erro: CEP inválido ou não encontrado.", "Erro")

        # Verifica se há múltiplos endereços para este CEP
        # Você pode implementar a lógica aqui baseada na sua fonte de dados
        enderecos_multiplos = verificar_enderecos_multiplos(cep)
        
        if enderecos_multiplos and len(enderecos_multiplos) > 1:
            # Retorna Value Selection se há múltiplas opções
            return gerar_value_selection(enderecos_multiplos)
        else:
            # Retorna o formato normal ResponseV2 se há apenas um endereço
            return gerar_resposta_xml_v2(data)

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}", "Erro")

def deve_buscar_multiplos_enderecos(data, cep):
    """
    Verifica se o CEP/endereço indica que pode haver múltiplos endereços.
    Baseado em características como CEP terminado em 000, complemento vazio, etc.
    """
    
    # CEPs que terminam em 000 geralmente são de logradouros grandes
    if cep.replace("-", "").endswith("000"):
        logging.debug(f"CEP {cep} termina em 000 - pode ter múltiplos endereços")
        return True
    
    # Se o complemento está vazio, pode indicar que há várias opções
    if not data.get("complemento") or data.get("complemento").strip() == "":
        logging.debug(f"CEP {cep} sem complemento - pode ter múltiplos endereços")
        return True
    
    # Logradouros muito genéricos (avenidas, ruas principais)
    logradouro = data.get("logradouro", "").lower()
    logradouros_genericos = [
        "avenida", "rodovia", "estrada", "via", "marginal", 
        "alameda principal", "rua principal"
    ]
    
    for generico in logradouros_genericos:
        if generico in logradouro:
            logging.debug(f"Logradouro genérico detectado: {logradouro}")
            return True
    
    return False

def buscar_enderecos_multiplos(data_viacep, cep):
    """
    Busca múltiplos endereços baseado nos dados retornados pelo ViaCEP.
    Faz buscas por logradouro na mesma cidade para encontrar variações.
    """
    
    try:
        logradouro = data_viacep.get("logradouro", "")
        cidade = data_viacep.get("localidade", "")
        uf = data_viacep.get("uf", "")
        
        if not logradouro or not cidade or not uf:
            return []
        
        # Busca por logradouro similar na mesma cidade usando a API do ViaCEP
        # Formato: https://viacep.com.br/ws/UF/Cidade/Logradouro/json/
        
        # Limpa o logradouro para a busca (remove números, remove palavras genéricas)
        logradouro_busca = limpar_logradouro_para_busca(logradouro)
        
        if not logradouro_busca:
            return []
        
        # Monta URL de busca
        url_busca = f"https://viacep.com.br/ws/{uf}/{cidade}/{logradouro_busca}/json/"
        
        logging.debug(f"Buscando múltiplos endereços em: {url_busca}")
        
        response = requests.get(url_busca, timeout=10)
        
        if response.status_code != 200:
            logging.error(f"Erro na busca de múltiplos endereços: {response.status_code}")
            return []
        
        resultados = response.json()
        
        # Se não é uma lista ou está vazia, não há múltiplos endereços
        if not isinstance(resultados, list) or len(resultados) <= 1:
            return []
        
        # Processa os resultados para o formato esperado
        enderecos = []
        for i, resultado in enumerate(resultados[:10]):  # Limita a 10 resultados
            endereco_completo = montar_endereco_completo(resultado)
            
            endereco = {
                "id": str(i + 1),
                "endereco_completo": endereco_completo,
                "cep": resultado.get("cep", ""),
                "logradouro": resultado.get("logradouro", ""),
                "complemento": resultado.get("complemento", ""),
                "bairro": resultado.get("bairro", ""),
                "cidade": resultado.get("localidade", ""),
                "uf": resultado.get("uf", ""),
                "ibge": resultado.get("ibge", ""),
                "gia": resultado.get("gia", ""),
                "ddd": resultado.get("ddd", ""),
                "siafi": resultado.get("siafi", "")
            }
            enderecos.append(endereco)
        
        logging.debug(f"Encontrados {len(enderecos)} endereços múltiplos")
        return enderecos
        
    except requests.RequestException as e:
        logging.error(f"Erro na requisição para buscar múltiplos endereços: {str(e)}")
        return []
    except Exception as e:
        logging.error(f"Erro ao processar múltiplos endereços: {str(e)}")
        return []

def limpar_logradouro_para_busca(logradouro):
    """
    Limpa o logradouro para fazer a busca na API do ViaCEP.
    Remove números, palavras muito específicas, etc.
    """
    
    import re
    
    # Remove números do logradouro
    logradouro_limpo = re.sub(r'\d+', '', logradouro).strip()
    
    # Remove palavras muito específicas que podem não dar match
    palavras_remover = ['de', 'da', 'do', 'das', 'dos', 'e', '&']
    palavras = logradouro_limpo.split()
    palavras_filtradas = [p for p in palavras if p.lower() not in palavras_remover and len(p) > 2]
    
    # Se sobrou pelo menos uma palavra, usa ela
    if palavras_filtradas:
        return ' '.join(palavras_filtradas[:3])  # Pega no máximo 3 palavras
    
    # Se não sobrou nada útil, retorna o original
    return logradouro

def montar_endereco_completo(dados_endereco):
    """
    Monta o endereço completo para exibição na lista de seleção.
    """
    
    partes = []
    
    # Logradouro
    if dados_endereco.get("logradouro"):
        partes.append(dados_endereco["logradouro"])
    
    # Complemento (se houver)
    if dados_endereco.get("complemento") and dados_endereco["complemento"].strip():
        partes.append(f"({dados_endereco['complemento']})")
    
    # Bairro
    if dados_endereco.get("bairro"):
        partes.append(f"- {dados_endereco['bairro']}")
    
    # Cidade e UF
    cidade = dados_endereco.get("localidade", "")
    uf = dados_endereco.get("uf", "")
    if cidade and uf:
        partes.append(f", {cidade} - {uf}")
    
    # CEP
    if dados_endereco.get("cep"):
        partes.append(f" (CEP: {dados_endereco['cep']})")
    
    return " ".join(partes)

def gerar_value_selection(enderecos):
    """Gera XML no formato Value Selection para múltiplos endereços."""
    
    # Criar o elemento Response
    response = etree.Element("Response")
    
    # Adicionar mensagem opcional
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = "Múltiplos endereços encontrados. Selecione um:"
    etree.SubElement(message, "Icon").text = "Info"
    
    # Criar ReturnValue com Items
    return_value = etree.SubElement(response, "ReturnValue")
    items = etree.SubElement(return_value, "Items")
    
    # Adicionar cada endereço como um Item
    for endereco in enderecos:
        item = etree.SubElement(items, "Item")
        etree.SubElement(item, "Text").text = endereco["endereco_completo"]
        etree.SubElement(item, "Value").text = endereco["id"]
    
    # Gerar XML com encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    logging.debug(f"XML Value Selection: {xml_str}")
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def processar_campos(root):
    """Processa os campos do XML e retorna um dicionário com os valores."""
    campos = {}
    for field in root.findall(".//Field"):
        id = field.findtext("ID") or field.findtext("Id")  # Tenta ambos os formatos
        value = field.findtext("Value")
        if id and value:
            campos[id] = value

    for table_field in root.findall(".//TableField"):
        table_id = table_field.findtext("ID")
        rows = []
        for row in table_field.findall(".//Row"):
            row_data = {}
            for field in row.findall(".//Field"):
                id = field.findtext("ID")
                value = field.findtext("Value")
                if id and value:
                    row_data[id] = value
            rows.append(row_data)
        campos[table_id] = rows

    return campos

def gerar_resposta_xml_v2(data):
    """Gera a resposta XML V2 com os dados do endereço."""
    # Definir namespaces
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    # Criar o elemento raiz com namespaces
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Adicionar seção de mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "CEP encontrado com sucesso"
    
    # Criar seção ReturnValueV2
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    
    # Mapear dados do CEP para os novos campos
    adicionar_campo(fields, "LOGRADOURO", data.get("logradouro", ""))
    adicionar_campo(fields, "COMPLEMENTO", data.get("complemento", ""))
    adicionar_campo(fields, "BAIRRO", data.get("bairro", ""))
    adicionar_campo(fields, "CIDADE", data.get("localidade", ""))
    adicionar_campo(fields, "ESTADO", data.get("estado", ""))
    adicionar_campo(fields, "UF", data.get("uf", ""))
    
    # Adicionar TableField exemplo
    table_field_id = "TABCAIXA1"
    rows_data = [
        {"TextTable": "Y", "CX1PESO": "9,0"},
        {"TextTable": "X", "CX1PESO": "8,0"},
    ]
    adicionar_table_field(fields, table_field_id, rows_data)
    
    # Adicionar campos adicionais do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "CEP ENCONTRADO - INFOS ABAIXO"
    etree.SubElement(return_value, "LongText")  # Vazio
    etree.SubElement(return_value, "Value").text = "58"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    logging.debug(f"XML de Resposta V2: {xml_str}")
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def gerar_erro_xml(mensagem, short_text):
    """Gera um XML de erro com mensagem personalizada."""
    # Definir namespaces
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    # Criar o elemento raiz com namespaces
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Adicionar seção de mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    
    # Criar seção ReturnValueV2 vazia
    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = short_text
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")