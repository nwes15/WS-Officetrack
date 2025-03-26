from flask import Flask, request, Response
import logging
from lxml import etree

def resgate_xml():
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
        
        if not xml_data:
            logging.error("Nenhum XML encontrado na requisição")
            return gerar_resposta_erro("Nenhum XML encontrado")
        
        # Log do XML completo recebido
        logging.debug(f"XML COMPLETO RECEBIDO: {xml_data}")
        
        # Tenta fazer parse do XML
        try:
            root = etree.fromstring(xml_data.encode('utf-8'))
            logging.debug("XML parseado com sucesso")
        except etree.XMLSyntaxError as e:
            logging.error(f"Erro de sintaxe no XML: {e}")
            return gerar_resposta_erro(f"Erro de sintaxe no XML: {e}")
        
        # Se chegou aqui, é um XML válido
        return gerar_resposta_sucesso()
    
    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_resposta_erro(f"Erro interno: {str(e)}")

def gerar_resposta_sucesso():
    """Gera resposta de sucesso com XML"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("Response", nsmap=nsmap)
    
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = "XML Processado com Sucesso"
    etree.SubElement(message, "Icon").text = "Info"
    etree.SubElement(message, "ButtonText").text = "OK"
    
    return_value = etree.SubElement(response, "ReturnValue")
    etree.SubElement(return_value, "ShortText").text = "XML Válido"
    etree.SubElement(return_value, "LongText").text = "XML foi capturado e validado"
    etree.SubElement(return_value, "Value").text = "OK"
    etree.SubElement(return_value, "Action").text = "Continue"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def gerar_resposta_erro(mensagem):
    """Gera resposta de erro com XML"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("Response", nsmap=nsmap)
    
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = mensagem
    etree.SubElement(message, "Icon").text = "Warning"
    etree.SubElement(message, "ButtonText").text = "OK"
    
    return_value = etree.SubElement(response, "ReturnValue")
    etree.SubElement(return_value, "ShortText").text = "Erro no Processamento"
    etree.SubElement(return_value, "LongText").text = mensagem
    etree.SubElement(return_value, "Value").text = "Erro"
    etree.SubElement(return_value, "Action").text = "Stop"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")