from flask import request, Response
import requests
from lxml import etree
import logging
import time

def consultar_endereco():
    try:
        content_type = request.headers.get("Content-Type", "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")

        # Tenta extrair o XML de várias fontes possíveis
        xml_data = None

        # Tenta do form primeiro (com vários nomes possíveis)
        if request.form:
            for possible_name in ["TextXML", "textxml", "xmldata", "xml"]:
                if possible_name in request.form:
                    xml_data = request.form.get(possible_name)
                    logging.debug(f"XML encontrado no campo {possible_name}")
                    break

            # Se não encontrou no form, tenta o primeiro campo do form
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
            return gerar_erro_xml("Não foi possível encontrar dados XML na requisição")

        logging.debug(f"XML para processar: {xml_data}")

        # Tenta fazer o parse do XML
        try:
            root = etree.fromstring(xml_data.encode("utf-8"))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("Erro ao processar o XML recebido.")

        # Processa os campos do XML
        campos = processar_campos(root)

        # Extrai as coordenadas do XML
        latlong = campos.get("LATLONG") or campos.get("local") or campos.get("coordenadas")
        if not latlong:
            return gerar_erro_xml("Erro: Campo 'local' (LATLONG) não encontrado no XML.")

        # Extrai latitude e longitude da string
        try:
            latitude, longitude, _ = latlong.split(",", 2)  # Dividir em duas partes
            latitude = latitude.strip()
            longitude = longitude.strip()

            # Converte para float
            latitude = float(latitude)
            longitude = float(longitude)

            # Converte para float e verifica os limites
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return gerar_erro_xml("Erro: Latitude ou Longitude fora dos limites válidos.")

            logging.debug(f"Latitude extraída: {latitude}")
            logging.debug(f"Longitude extraída: {longitude}")
        except ValueError as e:
            return gerar_erro_xml(f"Erro: Formato inválido para o campo 'local'. Erro de conversão: {e}")

        # Faz a requisição à API Nominatim
        url = f"https://nominatim.openstreetmap.org/reverse?lat={latitude}&lon={longitude}&format=json&addressdetails=1"

        logging.debug(f"URL da requisição: {url}")

        # Adiciona o header User-Agent
        headers = {
            'User-Agent': 'MinhaAplicacao/1.0 (meuemail@exemplo.com)'  # Substitua com informações reais
        }
        time.sleep(1) #Adicionando delay
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return gerar_erro_xml(f"Erro ao consultar a API Nominatim. Status code: {response.status_code}")

        data = response.json()
        if not data: # Verifica se a lista está vazia
            return gerar_erro_xml(f"Nenhum resultado encontrado para as coordenadas fornecidas.")
        
        # Retorna os dados do endereço no novo formato
        return gerar_resposta_xml_v2(data)

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")

def processar_campos(root):
    """Processa os campos do XML e retorna um dicionário com os valores."""
    campos = {}
    for field in root.findall(".//Field"):
        id_field = field.findtext("ID") or field.findtext("Id")  # Tenta ambos os formatos
        value = field.findtext("Value")
        if id_field and value:
            campos[id_field] = value

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
    etree.SubElement(message, "Text").text = "Endereço encontrado com sucesso"

    # Criar seção ReturnValueV2
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    # Mapear dados do Nominatim para os novos campos
    address = data.get("address", {})
    adicionar_campo_v2(fields, "CEP", address.get("postcode", ""))
    adicionar_campo_v2(fields, "LOGRADOURO", address.get("road", ""))
    adicionar_campo_v2(fields, "COMPLEMENTO", address.get("house_number", ""))  # Ou outro campo apropriado
    adicionar_campo_v2(fields, "BAIRRO", address.get("neighbourhood", "") or address.get("suburb", ""))
    adicionar_campo_v2(fields, "CIDADE", address.get("city", "") or address.get("town", ""))
    adicionar_campo_v2(fields, "ESTADO", address.get("state", ""))
    adicionar_campo_v2(fields, "UF", address.get("country_code", ""))
    
    

    # Adicionar campos adicionais do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "ENDERECO ENCONTRADO"
    etree.SubElement(return_value, "LongText")  # Vazio
    etree.SubElement(return_value, "Value").text = "58"

    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    logging.debug(f"XML de Resposta V2: {xml_str}")  # Depuração no console

    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def adicionar_campo_v2(parent, field_id, value):
    """Adiciona um campo ao XML no formato V2."""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value

def gerar_erro_xml(mensagem):
    """Gera um XML de erro com mensagem personalizada no formato V2."""
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
    fields = etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = "DEU ERRO"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"

    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")