from flask import Flask, request, Response
import requests
from lxml import etree
import logging

app = Flask(__name__)

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

# GUID fixo
GUID_FIXO = "96d3454f-5c5f-41fd-b0ad-616753b22d8b"

@app.route("/consultar_cep", methods=["POST"])
def consulta_cep():
    try:
        content_type = request.headers.get("Content-Type", "").lower()
        logging.debug(f"Tipo de conteúdo recebido: {content_type}")

        # Se os dados vierem como "application/x-www-form-urlencoded"
        if "application/x-www-form-urlencoded" in content_type:
            xml_data = request.form.get("TextXML", "")  # Captura o valor do campo "TextXML"
            logging.debug(f"XML extraído do formulário: {xml_data}")

        # Se os dados vierem como "application/xml" ou "text/xml"
        elif "application/xml" in content_type or "text/xml" in content_type:
            if not request.data or request.data.strip() == b'':
                return gerar_erro_xml("Erro: Requisição XML sem corpo.")

            xml_data = request.data.decode("utf-8").strip()
            logging.debug(f"XML recebido: {xml_data}")

        else:
            return gerar_erro_xml("Erro: Formato não suportado. Use XML ou Form-urlencoded.")

        # Tenta fazer o parse do XML
        try:
            root = etree.fromstring(xml_data.encode("utf-8"))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("Erro ao processar o XML recebido.")

        # Procura o campo CEP no XML
        cep = None
        for field in root.findall(".//Field"):
            if field.findtext("Id") == "CEP":
                cep = field.findtext("Value")
                break

        if not cep:
            return gerar_erro_xml("Erro: CEP não informado no XML.")

        # Faz a requisição à API ViaCEP
        response = requests.get(f"https://viacep.com.br/ws/{cep}/json/")
        if response.status_code != 200:
            return gerar_erro_xml("Erro ao consultar o CEP na API ViaCEP.")

        data = response.json()
        if "erro" in data:
            return gerar_erro_xml("Erro: CEP inválido ou não encontrado.")

        # Retorna os dados do endereço
        return gerar_resposta_xml(data)

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")

def gerar_resposta_xml(data):
    """Gera a resposta XML com os dados do endereço."""
    response = etree.Element("Response")

    # Mensagem de sucesso
    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = "CEP encontrado com sucesso"

    # Retorno dos valores
    return_value = etree.SubElement(response, "ReturnValue")
    fields = etree.SubElement(return_value, "Fields")

    # Adiciona os campos do endereço em maiúsculo
    adicionar_campo(fields, "LOGRADOURO", data.get("logradouro", ""))
    adicionar_campo(fields, "COMPLEMENTO", data.get("complemento", ""))
    adicionar_campo(fields, "BAIRRO", data.get("bairro", ""))
    adicionar_campo(fields, "CIDADE", data.get("localidade", ""))
    adicionar_campo(fields, "ESTADO", data.get("uf", ""))

    # Inclui o GUID fixo na resposta
    etree.SubElement(return_value, "Guid").text = GUID_FIXO

    xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode()
    logging.debug(f"XML de Resposta: {xml_str}")  # Depuração no console

    return Response(xml_str, content_type="application/xml")

def gerar_erro_xml(mensagem):
    """Gera um XML de erro com mensagem personalizada."""
    response = etree.Element("Response")

    message = etree.SubElement(response, "Message")
    etree.SubElement(message, "Text").text = mensagem

    return Response(etree.tostring(response, encoding="utf-8", xml_declaration=True), content_type="application/xml")

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML."""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "Id").text = field_id
    etree.SubElement(field, "Value").text = value

if __name__ == "__main__":
    app.run(debug=True, port=5000)
