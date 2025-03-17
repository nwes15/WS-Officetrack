 #WS simples, mocada tb conforme haviamos feito dos pesos, so com alguns pontos adicionais
 # nessa teremos aquele xml que vc leu que tem os itens de catalogo, vamos criar um campo tipo TSTWS, onde vai estar ligado ou desligado (como o TSTPES)…..
 # se o TSTWS for 0 vai retornar messagev2 com sucesso e ao dar OK vai ter um action que vai fechar o formulario, para isso, tem uma tag - Action que tem que ser adicionada para enviar o form….
 # se TSTWS for 1, entao vai retornar algo do tipo no messagev2 - Itens verificados inconsistente, favor verificar novamente…..e no shorttext, aquele de pressione lixeira para novo processamento…

from flask import request, Response
import requests
from lxml import etree
import logging

def validar_item():
    try:
        content_type = request.headers.get("Content-Type", "").lower()
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
            return gerar_resposta_xml(mensagem="Não foi possível encontrar dados XML na requisição", value = "Erro", shorttext= "Erro", icon = "Critical")

        logging.debug(f"XML para processar: {xml_data}")

        try:
            root = etree.fromstring(xml_data.encode('utf-8'))
        except etree.XMLSyntaxError as e:
            logging.error(f"Erro ao processar o XML: {e}")
            return gerar_resposta_xml(mensagem=f"Erro ao processar o XML recebido: {e}", value = "Erro", shorttext= "Erro", icon = "Critical")

        campos = processar_campos(root)

        tstws = campos.get("TSTWS")
        if not tstws:
            return gerar_resposta_xml(mensagem="Campo TSTWS não encontrado no XML.",  value = "Erro", shorttext= "Erro", icon = "Critical")
        
        if tstws not in ["0", "1"]:
            return gerar_resposta_xml(mensagem="Valor inválido para o campo TSTWS. Deve ser 0 ou 1.", value = "Erro", shorttext= "Erro", icon = "Critical")

        #Processa a resposta de acordo com o valor de TSTWS
        if tstws == "0":
            mensagem = "Item verificado com sucesso."
            value = "Sucesso"
            shorttext = "Validado"
            icon = "Success"
            action = "SendEntry"
            #data = {"Mensagem": mensagem, "Valor": value, "ShortText": shorttext}
        elif tstws == "1":
            mensagem = "Item verificado inconsistente, favor verificar novamente."
            value = "Inconsistente"
            shorttext = "Pressione lixeira para novo processamento."
            icon = "Critical"
            action = ""
        
        return gerar_resposta_xml(
            mensagem=mensagem,
            value=value,
            shorttext=shorttext,
            icon = icon,
            action=action
        )

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_resposta_xml(mensagem=f"Erro interno no servidor: {str(e)}", value = "Erro", shorttext= "Erro", icon = "Critical")

def processar_campos(root):
    """Processa os campos do XML e retorna um dicionário com os valores."""
    campos = {}
    for field in root.findall(".//Field"):
        id = field.findtext("ID") or field.findtext("Id")  # Tenta ambos os formatos
        value = field.findtext("Value")
        if id and value:
            campos[id] = value
    return campos

def gerar_resposta_xml(mensagem, value, icon, shorttext="", button_text="OK", action=""):
    # Cria o XML de resposta
    response = etree.Element("Response")
    
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = mensagem
    etree.SubElement(message, "Icon").text = icon
    etree.SubElement(message, "ButtonText").text = button_text

    return_value = etree.SubElement(response, "ReturnValue")
    etree.SubElement(return_value, "ShortText").text = shorttext
    etree.SubElement(return_value, "LongText").text = ""
    etree.SubElement(return_value, "Value").text = value
    etree.SubElement(return_value, "Action").text = action

    xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode()
    logging.debug(f"XML de Resposta: {xml_str}")
    return Response(xml_str, content_type="application/xml; charset=utf-8")