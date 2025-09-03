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

def verificar_enderecos_multiplos(cep):
    """
    Verifica se há múltiplos endereços para um CEP.
    Você deve implementar sua lógica específica aqui.
    
    Exemplos de fontes:
    - Banco de dados próprio
    - API alternativa
    - Arquivo CSV/JSON
    """
    
    # EXEMPLO: Simulando múltiplos endereços para alguns CEPs
    enderecos_exemplo = {
        "01310-100": [
            {
                "id": "1",
                "endereco_completo": "Av. Paulista, 1000 - Bela Vista, São Paulo - SP",
                "logradouro": "Avenida Paulista",
                "numero": "1000",
                "bairro": "Bela Vista",
                "cidade": "São Paulo",
                "uf": "SP"
            },
            {
                "id": "2", 
                "endereco_completo": "Av. Paulista, 1100 - Bela Vista, São Paulo - SP",
                "logradouro": "Avenida Paulista",
                "numero": "1100",
                "bairro": "Bela Vista",
                "cidade": "São Paulo",
                "uf": "SP"
            },
            {
                "id": "3",
                "endereco_completo": "Av. Paulista, 1200 - Bela Vista, São Paulo - SP", 
                "logradouro": "Avenida Paulista",
                "numero": "1200",
                "bairro": "Bela Vista",
                "cidade": "São Paulo",
                "uf": "SP"
            }
        ]
    }
    
    # Aqui você implementaria sua lógica real:
    # - Consulta ao banco de dados
    # - Chamada para API específica
    # - Leitura de arquivo com endereços
    
    return enderecos_exemplo.get(cep, [])

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