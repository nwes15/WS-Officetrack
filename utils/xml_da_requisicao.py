from flask import request
from lxml import etree
import logging

def obter_xml_da_requisicao():
    """Tenta obter o XML da requisição a partir de diferentes fontes."""
    logging.debug("Obtendo XML da requisição...")
    
    # 1. Tenta obter do form (vários nomes possíveis)
    if request.form:
        for possible_name in ["TextXML", "textxml", "xmldata", "xml"]:
            if possible_name in request.form:
                xml_data = request.form.get(possible_name)
                logging.debug(f"XML encontrado no campo {possible_name} do form")
                return xml_data
        # Se não encontrou por nome específico, tenta o primeiro campo do form
        if len(request.form) > 0:
            first_key = next(iter(request.form))
            xml_data = request.form.get(first_key)
            logging.debug(f"Usando primeiro campo do form: {first_key}")
            return xml_data
    
    # 2. Tenta obter do corpo da requisição
    if request.data:
        try:
            xml_data = request.data.decode('utf-8')
            logging.debug("Usando dados brutos do corpo da requisição")
            return xml_data
        except Exception as e:
            logging.error(f"Erro ao decodificar dados do corpo: {e}")
            return None  # Indica que não foi possível obter o XML
        
    

    logging.warning("Nenhum dado XML encontrado na requisição")
    return None  # Indica que não foi possível obter o XML