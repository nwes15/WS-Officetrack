from flask import request, Response
from lxml import etree
import logging
import requests
import os
from utils import adicionar_campo
from cepv2 import gerar_erro_xml

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

def consultar_groqv2():
    try:
        content_type = request.headers.get('Content-Type').lower()
        xml_data = None

        if request.form:
            for possible_name in ['TextXML', 'TextXML', 'textxml', 'xml']:
                if possible_name in request.form:
                    xml_data = request.form.get(possible_name)
                    break
            if not xml_data and len(request.form) > 0:
                first_key = next(iter(request.form))
                xml_data = request.form.get(first_key)

        if not xml_data and request.data:
            try:
                xml_data = request.data.decode('utf-8')
            except Exception as e:
                pass

        if not xml_data:
            return gerar_erro_xml("XML não encontrado", "Erro", root_element="ResponseV2", namespaces=None)

        try:
            root = etree.fromstring(xml_data.encode('utf-8'))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("XML mal formado", "Erro", root_element="ResponseV2", namespaces=None)
        
        campos = processar_campos_groq(root)
        texto_original = campos.get("TALK_TEXT")
        if not texto_original:
            return gerar_erro_xml("TEXTO FALADO não encontrado", "Erro", root_element="ResponseV2", namespaces=None)
        
        prompt = f"Revise o texto abaixo, corrija erros ortográficos, gramaticais e de concordância, e retorne o texto corrigido:\n\n{texto_original}"
        texto_corrigido = consultar_groq_api(prompt)
        if not texto_corrigido:
            return gerar_erro_xml("Erro ao consultar a API Groq", "Erro", root_element="ResponseV2", namespaces=None)
        
        return gerar_resposta_xml_v2_talk_text_corrigido(texto_corrigido)
    except Exception as e:
        logging.error(f"Erro ao processar a requisição: {e}")
        return gerar_erro_xml("Erro interno do servidor", "Erro", root_element="ResponseV2", namespaces=None)
    

def processar_campos_groq(root):
    campos = {}
    for field in root.findall('.//Field'):
        id = field.findtext('ID') or field.findtext('id') or field.findtext('Id')
        value = field.findtext('Value') or field.findtext('value')
        if id and value:
            campos[id] = value
    if not campos:
        for field in root.findall('.//field'):
            id = field.findtext('ID') or field.findtext('id') or field.findtext('Id')
            value = field.findtext('Value') or field.findtext('value') or field.findtext('Value')
            if id and value:
                campos[id] = value
    return campos

def consultar_groq_api(prompt):
    headers = {
        'Authorization': f'Bearer {GROQ_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': 'llama3-70b-8192',
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }
    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=data)
        if response.status_code == 200:
            return response.json().get('choices', [{}])[0].get('message', {}).get('content', '')
        else:
            logging.error(f"Erro na API Groq: {response.status_code} - {response.text}")
            return None
    except requests as e:
        logging.error(f"Erro ao chamar a API Groq: {e}")
        return None
    

def gerar_resposta_xml_v2_talk_text_corrigido(texto_corrigido):
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    response = etree.Element('ResponseV2', nsmap=nsmap)
    message = etree.SubElement(response, 'MessageV2')
    etree.SubElement(message, 'Text').text = 'Texto corrigido com sucesso'

    return_value = etree.SubElement(response, 'ReturnValueV2')
    fields = etree.SubElement(return_value, 'Fields')
    adicionar_campo(fields, 'TALK_TEXT', texto_corrigido)

    etree.SubElement(return_value, "ShortText").text = "Segue texto revisado"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"

    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    return Response(xml_str.encode('utf-16'), content_type="application/xml; charset=utf-16")