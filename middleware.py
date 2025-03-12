from flask import Flask, request, Response
import requests
from lxml import etree
import logging
from dotenv import load_dotenv
import os
import json
import random

load_dotenv()

app = Flask(__name__)


GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

# GUID fixo
GUID_FIXO = "a4b72440-b2f6-407b-80fd-57a0ad39a337"

@app.route("/consultar_cep", methods=["POST"])
def consulta_cep():
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
            return gerar_erro_xml("Não foi possível encontrar dados XML na requisição")
        
        logging.debug(f"XML para processar: {xml_data}")

        # Tenta fazer o parse do XML
        try:
            root = etree.fromstring(xml_data.encode("utf-8"))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("Erro ao processar o XML recebido.")

        # Processa os campos do XML
        campos = processar_campos(root)

        # Faz a requisição à API ViaCEP
        cep = campos.get("CEP")
        if not cep:
            return gerar_erro_xml("Erro: CEP não informado no campo CEP.")

        response = requests.get(f"https://viacep.com.br/ws/{cep}/json/")
        if response.status_code != 200:
            return gerar_erro_xml("Erro ao consultar o CEP - Verifique e tente novamente.")

        data = response.json()
        if "erro" in data:
            return gerar_erro_xml("Erro: CEP inválido ou não encontrado.")

        # Retorna os dados do endereço no novo formato
        return gerar_resposta_xml_v2(data)

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")

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
                id = field.findtext("ID") or field.findtext("Id")
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
    # Você pode ajustar este mapeamento conforme necessário
    adicionar_campo_v2(fields, "LOGRADOURO", data.get("logradouro", ""))
    adicionar_campo_v2(fields, "COMPLEMENTO", data.get("complemento", ""))
    adicionar_campo_v2(fields, "BAIRRO", data.get("bairro", ""))
    adicionar_campo_v2(fields, "CIDADE", data.get("localidade", ""))
    adicionar_campo_v2(fields, "ESTADO", data.get("estado", ""))
    adicionar_campo_v2(fields, "UF", data.get("uf", ""))
    
    # Adiciona campos exemplo conforme solicitado
    adicionar_campo_v2(fields, "Test1", "ZZZ")
    adicionar_campo_v2(fields, "Num1", "777")
    
    # Adicionar TableField exemplo
    adicionar_table_field(fields)
    
    # Adicionar campos adicionais do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "CEP ENCONTRADO - INFOS ABAIXO"
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

def adicionar_table_field(parent):
    """Adiciona um TableField com duas linhas de exemplo."""
    table_field = etree.SubElement(parent, "TableField")
    etree.SubElement(table_field, "ID").text = "Table1"
    rows = etree.SubElement(table_field, "Rows")
    
    # Primeira linha
    row1 = etree.SubElement(rows, "Row")
    fields1 = etree.SubElement(row1, "Fields")
    adicionar_campo_v2(fields1, "TextTable", "Y")
    adicionar_campo_v2(fields1, "NumTable", "9")
    

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
    etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = "DEU ERRO WES"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")


@app.route('/consultar_groq', methods=['POST'])
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
            return gerar_erro_xml_groq("Não foi possível encontrar dados XML na requisição")

        logging.debug(f"XML para processar: {xml_data}")

        try:
            root = etree.fromstring(xml_data.encode('utf-8'))
        except etree.XMLSyntaxError:
            return gerar_erro_xml_groq("XML inválido.")

        campos = processar_campos_groq(root)

        pergunta = campos.get("PERGUNTA")
        if not pergunta:
            return gerar_erro_xml_groq("Pergunta não encontrada no campo PERGUNTA.")

        resposta_groq = consultar_groq_api(pergunta)
        if not resposta_groq:
            return gerar_erro_xml_groq("Erro ao consultar a API do Groq.")

        return gerar_resposta_xml_v2_groq(resposta_groq)

    except Exception as e:
        logging.error(f"Erro ao processar requisição: {e}")
        return gerar_erro_xml_groq(f"Erro interno no servidor: {str(e)}")

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

    adicionar_campo_v2_groq(fields, "RESPOSTA", resposta_groq)

    adicionar_table_field_groq(fields)

    etree.SubElement(return_value, "ShortText").text = "Segue a resposta."
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"

    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    logging.debug(f"Resposta gerada: {xml_str}")
    return Response(xml_str.encode('utf-16'), content_type="application/xml; charset=utf-16")

def adicionar_campo_v2_groq(parent, field_id, value):
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value

def adicionar_table_field_groq(parent):
    table_field = etree.SubElement(parent, "TableField")
    etree.SubElement(table_field, "ID").text = "Table1"
    rows = etree.SubElement(table_field, "Rows")
    
    # Primeira linha
    row1 = etree.SubElement(rows, "Row")
    fields1 = etree.SubElement(row1, "Fields")
    adicionar_campo_v2_groq(fields1, "TextTable", "Y")
    adicionar_campo_v2_groq(fields1, "NumTable", "9")
    
    # Segunda linha
    row2 = etree.SubElement(rows, "Row")
    fields2 = etree.SubElement(row2, "Fields")
    adicionar_campo_v2_groq(fields2, "TextTable", "X")
    adicionar_campo_v2_groq(fields2, "NumTable", "8")

def gerar_erro_xml_groq(mensagem):
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }

    response = etree.Element("ResponseV2", nsmap=nsmap)

    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem

    return_value = etree.SubElement(response, "ReturnValueV2")
    etree.SubElement(return_value, "Fields")
    etree.SubElement(return_value, "ShortText").text = "Deu Erro"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "0"

    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    return Response(xml_str.encode('utf-16'), content_type="application/xml; charset=utf-16")


@app.route("/capturar_xml", methods=["POST"])
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
            return gerar_resposta_xml_v3()
        else:
            return "Nenhum XML encontrado na requisição.", 400

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return f"Erro interno no servidor: {str(e)}", 500

def gerar_resposta_xml_v3():
    """Gera a resposta XML no formato V2."""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("Response", nsmap=nsmap)
    
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = "XML disponível nas logs"
    etree.SubElement(message, "Icon").text = "Warning/Critical/Info"
    etree.SubElement(message, "ButtonText").text = "OK"
    
    return_value = etree.SubElement(response, "ReturnValue")
    etree.SubElement(return_value, "ShortText").text = "Capturado com sucesso"
    etree.SubElement(return_value, "LongText").text = "Seu XML está disponivel nas logs"
    etree.SubElement(return_value, "Value").text = "OK"
    etree.SubElement(return_value, "Action").text = "Entry"
    
    fields = etree.SubElement(return_value, "Fields")

    #Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")


@app.route("/consultar_peso", methods=["POST"])
def consultar_peso():
    try:
        content_type = request.headers.get("Content-Type", "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")

        xml_data = request.data.decode("utf-8") if request.data else None
        if not xml_data:
            return gerar_erro_xml("Nenhum XML foi encontrado na requisição.")

        logging.debug(f"XML recebido: {xml_data}")

        try:
            root = etree.fromstring(xml_data.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            logging.error(f"Erro ao processar XML: {e}")
            return gerar_erro_xml(f"Erro ao processar o XML recebido: {e}")

        # Verificar a tag TSTPESO
        tstpeso_element = root.find(".//Field[Id='TSTPESO']/Value")
        tst_peso = tstpeso_element.text.strip() if tstpeso_element is not None else "0"

        logging.debug(f"TSTPESO encontrado: {tst_peso}")

        # Gerar os valores com base no TSTPESO
        peso1, peso2 = gerar_pesos(tst_peso == "1")  # True = valores diferentes, False = iguais

        logging.debug(f"Valores gerados: PESO={peso1}, PESOBALANCA={peso2}")

        # Criar XML de resposta no formato ResponseV2
        response_xml = criar_resposta_xml(peso1, peso2)

        logging.debug(f"XML de resposta:\n{response_xml}")

        return Response(response_xml.encode("utf-16"), content_type="application/xml; charset=utf-16")

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")


def gerar_pesos(diferentes):
    """Gera números aleatórios entre 0,5 e 500 para PESO e PESOBALANCA."""
    peso1 = round(random.uniform(0.5, 500), 2)
    peso2 = peso1 if not diferentes else round(random.uniform(0.5, 500), 2)
    while diferentes and abs(peso1 - peso2) < 0.1:
        peso2 = round(random.uniform(0.5, 500), 2)
    return peso1, peso2


def criar_resposta_xml(peso1, peso2):
    """Cria o XML de resposta no formato ResponseV2 esperado."""
    response = etree.Element("ResponseV2", attrib={
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xmlns:xsd": "http://www.w3.org/2001/XMLSchema"
    })

    message = etree.SubElement(response, "MessageV2")
    message_text = etree.SubElement(message, "Text")
    message_text.text = "Consulta de peso realizada com sucesso."

    return_value = etree.SubElement(response, "ReturnValueV2")

    fields = etree.SubElement(return_value, "Fields")

    peso_field = etree.SubElement(fields, "Field")
    etree.SubElement(peso_field, "ID").text = "PESO"
    etree.SubElement(peso_field, "Value").text = str(peso1)

    pesobalanca_field = etree.SubElement(fields, "Field")
    etree.SubElement(pesobalanca_field, "ID").text = "PESOBALANCA"
    etree.SubElement(pesobalanca_field, "Value").text = str(peso2)

    return etree.tostring(response, encoding="utf-16", xml_declaration=True).decode("utf-16")


def gerar_erro_xml(mensagem):
    """Gera um XML de erro com formato ResponseV2."""
    response = etree.Element("ResponseV2", attrib={
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xmlns:xsd": "http://www.w3.org/2001/XMLSchema"
    })

    message = etree.SubElement(response, "MessageV2")
    message_text = etree.SubElement(message, "Text")
    message_text.text = mensagem

    return Response(etree.tostring(response, encoding="utf-16", xml_declaration=True).decode("utf-16"),
                    content_type="application/xml; charset=utf-16",
                    status=500)
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
