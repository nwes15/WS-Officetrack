from flask import Flask, request, Response
import requests
from lxml import etree
import logging

app = Flask(__name__)

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

@app.route("/consulta_cep", methods=["POST"])
def consulta_cep():
    try:
        # Verifica se o corpo da requisição está vazio
        if not request.data:
            return gerar_erro_xml("Requisição sem corpo.")

        # Lê o corpo da requisição como XML
        xml_data = request.data.decode("utf-8").strip()
        logging.debug(f"XML recebido: {xml_data}")

        if not xml_data:
            return gerar_erro_xml("XML recebido está vazio.")

        # Tenta fazer o parse do XML
        try:
            root = etree.fromstring(xml_data.encode("utf-8"))
        except etree.XMLSyntaxError:
            return gerar_erro_xml("Erro ao processar o XML recebido.")

        # Extrai o GUID do formulário
        guid = root.findtext("Guid")
        if not guid:
            return gerar_erro_xml("GUID não encontrado no XML.")

        # Procura o campo CEP no XML
        cep = None
        for field in root.findall(".//Field"):
            if field.findtext("Id") == "CEP":
                cep = field.findtext("Value")
                break

        if not cep:
            return gerar_erro_xml("CEP não informado no XML.")

        # Faz a requisição à API ViaCEP
        response = requests.get(f"https://viacep.com.br/ws/{cep}/json/")
        if response.status_code != 200:
            return gerar_erro_xml("Erro ao consultar o CEP na API ViaCEP.")

        data = response.json()
        if "erro" in data:
            return gerar_erro_xml("CEP inválido ou não encontrado.")

        # Retorna os dados do endereço
        return gerar_resposta_xml(guid, data)

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_erro_xml(f"Erro interno no servidor: {str(e)}")

def gerar_resposta_xml(guid, data):
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

    # Inclui o GUID na resposta
    etree.SubElement(return_value, "f113c885-2d76-4f08-acda-40138b028050").text = guid

    # Depuração: Imprimir XML antes de retornar
    xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode()
    print("XML de Resposta:", xml_str)

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
