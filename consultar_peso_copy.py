import logging
import random
from io import StringIO
from flask import request, Response
from lxml import etree

def consultar_peso_copy():
    try:
        content_type = request.headers.get('Content-Type', "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")

        xml_data = None

        # Obtenção do XML da requisição (mantido igual)
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
            return gerar_erro_xml("Não foi possível encontrar dados XML na requisição", "Pressione lixeira para nova consulta.")

        logging.debug(f"XML para processar: {xml_data}")

        # Processamento do XML
        try:
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(StringIO(xml_data), parser)
            root = tree.getroot()
        except etree.XMLSyntaxError as e:
            logging.error(f"Erro ao processar o XML: {e}")
            return gerar_erro_xml("Erro ao processar o XML recebido.")

        # Processa os campos do XML
        campos = processar_campos_peso(root)

        # Verificação do campo TSTPESO (mantido igual)
        tstpeso = campos.get("TSTPESO")
        if not tstpeso:
            return gerar_erro_xml("Campo TSTPESO não encontrado no XML.")

        if tstpeso not in ["0", "1"]:
            return gerar_erro_xml("Campo TSTPESO deve ser 0 ou 1.")

        # Geração dos valores de peso (mantido igual)
        if tstpeso == "1":
            peso = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')
            pesobalanca = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')
        else:
            valor_comum = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')
            peso = pesobalanca = valor_comum

        # Identificação do botão acionado (NOVA LÓGICA)
        botao_acionado = identificar_botao(campos)
        
        # Retorno da resposta apropriada
        if botao_acionado == "VALIDAPESO1":
            return gerar_resposta_xml_peso(peso, pesobalanca)
        else:
            return gerar_resposta_xml_peso2(peso, pesobalanca)

    except Exception as e:
        logging.error(f"Erro ao processar requisição: {e}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")

def identificar_botao(campos):
    """Identifica qual botão foi acionado com base em múltiplos critérios"""
    # Critério 1: Campos específicos modificados
    if campos.get("PESO1") and not campos.get("PESO2"):
        return "VALIDAPESO1"
    if campos.get("PESO2") and not campos.get("PESO1"):
        return "VALIDAPESO2"
    
    # Critério 2: Valores dos botões de validação
    if campos.get("VALIDAPESO1") == "Valida Peso Caixa":
        return "VALIDAPESO1"
    if campos.get("VALIDAPESO2") == "Valida Peso Caixa 2":
        return "VALIDAPESO2"
    
    # Critério 3: Visibilidade dos campos
    if campos.get("VALIDAPESO1_IsVisible") == "1":
        return "VALIDAPESO1"
    if campos.get("VALIDAPESO2_IsVisible") == "1":
        return "VALIDAPESO2"
    
    # Fallback: Usa CX2 como antes (para compatibilidade)
    if campos.get("CX2") == "1":
        return "VALIDAPESO2"
    return "VALIDAPESO1"

def processar_campos_peso(root):
    """Processa os campos do XML e retorna um dicionário com os valores."""
    campos = {}
    for field in root.findall(".//Field"):
        id = field.findtext("Id") or field.findtext("ID")  # Suporta ambos "Id" e "ID"
        if id:
            campos[id] = field.findtext("Value")
            campos[f"{id}_IsVisible"] = field.findtext("IsVisible") or "0"
    return campos

def gerar_resposta_xml_peso(peso, pesobalanca):
    """Gera a resposta XML para o botão VALIDAPESO1"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    
    adicionar_campo(fields, "PESO1", peso)
    adicionar_campo(fields, "PESOBALANCA1", pesobalanca)
    
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"
    
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    logging.debug(f"XML de Resposta Peso: {xml_str}")
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def gerar_resposta_xml_peso2(peso, pesobalanca):
    """Gera a resposta XML para o botão VALIDAPESO2"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    
    adicionar_campo(fields, "PESO2", peso)
    adicionar_campo(fields, "PESOBALANCA2", pesobalanca)
    
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"
    
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    logging.debug(f"XML de Resposta Peso2: {xml_str}")
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML de resposta"""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "Id").text = field_id
    etree.SubElement(field, "Value").text = value

def gerar_erro_xml(mensagem, texto_curto="Erro no processamento"):
    """Gera uma resposta de erro em XML"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    
    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "ShortText").text = texto_curto
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "-1"
    
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")