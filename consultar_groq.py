from flask import request, Response
from lxml import etree
import logging
import requests
import os
from utils.gerar_erro import gerar_erro_xml
from utils.adicionar_campo import adicionar_campo
from utils.adicionar_table_field import adicionar_table_field

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

def consultar_groq():
    try:
        content_type = request.headers.get('Content-Type', "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")

        xml_data = None

        if request.form:
            for possible_name in ["TextXML", "textxml", "xmldata", "xml"]:
                if possible_name in request.form:
                    xml_data = request.form.get(possible_name)
                    logging.debug(f"XML encontrado no campo {possible_name}")
                    break

            if not xml_data and len(request.form) > 0:
                first_key = next(iter(request.form))
                xml_data = request.form.get(first_key)
                logging.debug(f"Usando primeiro campo do form: {first_key}")

        if not xml_data and request.data:
            try:
                xml_data = request.data.decode('utf-8')
                logging.debug("Usando dados brutos do corpo da requisição")
            except:
                pass

        if not xml_data:
            return gerar_erro_xml("Não foi possível encontrar dados XML na requisição")

        logging.debug(f"XML para processar: {xml_data}")

        try:
            root = etree.fromstring(xml_data.encode('utf-8'))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("XML inválido.")

        campos = processar_campos_groq(root)

        pergunta = campos.get("PERGUNTA")
        if not pergunta:
            return gerar_erro_xml("Pergunta não encontrada no campo PERGUNTA.")

        resposta_groq = consultar_groq_api(pergunta)
        if not resposta_groq:
            return gerar_erro_xml("Erro ao consultar a API do Groq.")

        return gerar_resposta_xml_v2_groq(resposta_groq)

    except Exception as e:
        logging.error(f"Erro ao processar requisição: {e}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")

def consultar_groq_api(pergunta):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "user", "content": pergunta}
        ]
    }
    
    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=data)
        if response.status_code == 200:
            return response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            logging.error(f"Erro ao consultar API do Groq: {response.text}")
            return None
    except Exception as e:
        logging.error(f"Erro ao consultar API do Groq: {e}")
        return None

def processar_campos_groq(root):
    campos = {}
    # Tenta encontrar os campos usando diferentes caminhos e formatos
    for field in root.findall(".//Field"):
        id = field.findtext("ID") or field.findtext("Id")
        value = field.findtext("Value")
        if id and value:
            campos[id] = value
    
    # Se não encontrar usando Field, tenta com field (minúsculo)
    if not campos:
        for field in root.findall(".//field"):
            id = field.findtext("ID") or field.findtext("Id") or field.findtext("id")
            value = field.findtext("Value") or field.findtext("value")
            if id and value:
                campos[id] = value
    
    return campos

def gerar_resposta_xml_v2_groq(resposta_groq):
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }

    response = etree.Element("ResponseV2", nsmap=nsmap)

    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Resposta obtida com sucesso."

    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    adicionar_campo(fields, "RESPOSTA", resposta_groq)

    adicionar_table_field(fields)

    etree.SubElement(return_value, "ShortText").text = "Segue a resposta."
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"

    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    logging.debug(f"Resposta gerada: {xml_str}")
    return Response(xml_str.encode('utf-16'), content_type="application/xml; charset=utf-16")