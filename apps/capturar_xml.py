from flask import Flask, request, Response
import logging
from lxml import etree

app = Flask(__name__)

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

def capturar_xml():
    try:
        content_type = request.headers.get("Content-Type", "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")
        
        xml_data = None
        
        # Tenta extrair o XML do formulário
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
        
        # Se não encontrou no form, tenta do corpo da requisição
        if not xml_data and request.data:
            try:
                xml_data = request.data.decode('utf-8')
                logging.debug("Usando dados brutos do corpo da requisição")
            except:
                pass
        
        if xml_data:
            logging.debug(f"XML recebido: {xml_data}")
            
            # Retorna a resposta XML no formato V2
            return gerar_resposta_xml_v2()
        else:
            return "Nenhum XML encontrado na requisição.", 400

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return f"Erro interno no servidor: {str(e)}", 500

def gerar_resposta_xml_v2():
    """Gera a resposta XML no formato V2."""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("Response", nsmap=nsmap)
    
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = "Invalid data"
    etree.SubElement(message, "Icon").text = "Warning/Critical/Info"
    etree.SubElement(message, "ButtonText").text = "OK"
    
    return_value = etree.SubElement(response, "ReturnValue")
    etree.SubElement(return_value, "ShortText").text = "Capturado com sucesso"
    etree.SubElement(return_value, "LongText").text = "Seu XML está disponivel nas logs"
    etree.SubElement(return_value, "Value").text = "OK"
    etree.SubElement(return_value, "Action").text = "SendEntry"
    
    fields = etree.SubElement(return_value, "Fields")

    #Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")
