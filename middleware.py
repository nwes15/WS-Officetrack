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


# consultar peso começa aqui

@app.route('/consultar_peso', methods=['POST'])
def processar_peso():
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
            return gerar_erro_xml("Erro ao processar o XML recebido.")


        campos = processar_campos(root)

        # Localizar o campo TSTPESO
        tstpeso = campos.get("TSTPESO")
        if not tstpeso:
            return gerar_erro_xml("Campo TSTPESO não encontrado no XML.")

        # Verificar se o campo TSTPESO é 0 ou 1
        for field in root.findall(".//Field"):
            field_id = field.findtext("ID")
            if field_id == "TSTPESO":
                tstpeso = field.findtext("Value")
                break

        # Verificar se o campo TSTPESO foi encontrado e é válido
        if tstpeso is None:
            return gerar_erro_xml("Campo TSTPESO não encontrado no XML.")

        if tstpeso not in ["0", "1"]:
            return gerar_erro_xml("Campo TSTPESO deve ser 0 ou 1.")

        # Gerar números aleatórios com base no valor de TSTPESO
        if tstpeso == "1":
            peso = str(round(random.uniform(0.5, 500), 2))  # Número aleatório entre 0,5 e 500
            pesobalanca = str(round(random.uniform(0.5, 500), 2))  # Outro número aleatório
        else:
            valor_comum = str(round(random.uniform(0.5, 500), 2))  # Mesmo número para ambos
            peso = pesobalanca = valor_comum

        # Retornar o XML com os campos preenchidos
        return gerar_resposta_xml(peso, pesobalanca)

    except Exception as e:
        logging.error(f"Erro ao processar requisição: {e}")
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


def gerar_resposta_xml(peso, pesobalanca):
    # Cria o XML de resposta
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }

    response = etree.Element("ResponseV2", nsmap=nsmap)

    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Resposta obtida com sucesso."

    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    # Adiciona os campos PESO e PESOBALANCA
    adicionar_campo_v5(fields, "PESO", peso)
    adicionar_campo_v5(fields, "PESOBALANCA", pesobalanca)

    etree.SubElement(return_value, "ShortText").text = "Segue a resposta."
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"

    # Converte o XML para string
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    logging.debug(f"Resposta gerada: {xml_str}")
    return Response(xml_str.encode('utf-16'), content_type="application/xml; charset=utf-16")

def adicionar_campo_v5(parent, field_id, value):
    # Adiciona um campo ao XML
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value

def gerar_erro_xml(mensagem):
    # Cria um XML de erro
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

    # Converte o XML para string
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str

    return Response(xml_str.encode('utf-16'), content_type="application/xml; charset=utf-16")

    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
