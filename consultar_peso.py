from flask import request, Response
from lxml import etree
import logging
import random
from io import StringIO
from utils.gerar_erro import gerar_erro_xml
from utils.adicionar_campo import adicionar_campo

def consultar_peso():
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

        # ADICIONAR ESTE BLOCO: Tenta fazer o parsing do XML com recuperação de erros
        try:
            # Configurar o parser para recuperar de erros
            parser = etree.XMLParser(recover=True)
            
            # Ler o XML a partir da string
            tree = etree.parse(StringIO(xml_data), parser)

            # Obter o elemento raiz (o <Form>)
            root = tree.getroot()

        except etree.XMLSyntaxError as e:
            logging.error(f"Erro ao processar o XML: {e}")
            return gerar_erro_xml("Erro ao processar o XML recebido.")

        # Processa os campos do XML uma única vez
        campos = processar_campos_peso(root)

        # Localizar o campo TSTPESO
        tstpeso = campos.get("TSTPESO")
        if not tstpeso:
            return gerar_erro_xml("Campo TSTPESO não encontrado no XML.")

        # Verificar se o campo TSTPESO é 0 ou 1
        if tstpeso not in ["0", "1"]:
            return gerar_erro_xml("Campo TSTPESO deve ser 0 ou 1.")

        # Gerar números aleatórios com base no valor de TSTPESO
        if tstpeso == "1":
            peso = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')  # Número aleatório entre 0,5 e 500
            pesobalanca = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')  # Outro número aleatório
        else:
            valor_comum = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')  # Mesmo número para ambos
            peso = pesobalanca = valor_comum

        # Retornar o XML com os campos preenchidos
        return gerar_resposta_xml_peso(peso, pesobalanca)

    except Exception as e:
        logging.error(f"Erro ao processar requisição: {e}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")

def processar_campos_peso(root):
    """Processa os campos do XML e retorna um dicionário com os valores."""
    campos = {}
    # Primeiro, tenta encontrar os campos usando Id
    for field in root.findall(".//Field"):
        id = field.findtext("Id")
        value = field.findtext("Value")
        if id and value:
            campos[id] = value
    
    # Se não encontrar muitos campos, tenta com o ID maiúsculo
    if len(campos) < 2:
        for field in root.findall(".//Field"):
            id = field.findtext("ID")
            value = field.findtext("Value")
            if id and value:
                campos[id] = value
    
    return campos

def gerar_resposta_xml_peso(peso, pesobalanca):
    """Gera a resposta XML com os dados de peso."""
    # Definir namespaces
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    # Criar o elemento raiz com namespaces
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Adicionar seção de mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    
    # Criar seção ReturnValueV2
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    
    # Adiciona os campos PESO e PESOBALANCA
    adicionar_campo(fields, "PESO", peso)
    adicionar_campo(fields, "PESOBALANCA", pesobalanca)
    
    # Adicionar campos adicionais do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")  # Vazio
    etree.SubElement(return_value, "Value").text = "58"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    logging.debug(f"XML de Resposta Peso: {xml_str}")  # Depuração no console
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")