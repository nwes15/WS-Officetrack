from flask import Flask, request, Response
import requests
from lxml import etree
import logging
from zeep import Client

app = Flask(__name__)

GUID_FIXO = "7a2fb530-87b2-4f66-963a-bc231f624ac7"

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

@app.route("/consulta_cep", methods=["POST"])
def consulta_cep():
    try:
        # Lendo o XML recebido
        xml_data = request.data.decode("utf-8")
        logging.debug(f"XML recebido: {xml_data}")

        if not xml_data.strip():
            return gerar_erro_xml("XML recebido está vazio.", GUID_FIXO)

        root = etree.fromstring(xml_data.encode("utf-8"))

        # Pegando o GUID do formulário
        guid = root.findtext("Guid")
        logging.debug(f"GUID: {guid}")

        # Pegando o CEP enviado
        cep = None
        for field in root.findall(".//Field"):
            if field.findtext("Id") == "CEP":
                cep = field.findtext("Value")
                logging.debug(f"CEP encontrado: {cep}")
                break

        if not cep:
            return gerar_erro_xml("CEP não informado.", guid)

        # Usando Zeep para consumir o serviço ViaCEP
        client = Client("https://viacep.com.br/ws/{{CEP}}/xml/")  # Substitua {{CEP}} por uma string vazia inicialmente
        response = client.service.consultaCEP(cep)

        # Construindo XML de resposta com os dados do Zeep
        xml_response = gerar_resposta_xml_zeep(guid, response)
        return Response(xml_response, content_type="application/xml")

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return gerar_erro_xml(f"Erro interno: {str(e)}", GUID_FIXO)

def gerar_resposta_xml_zeep(guid, data):
    """Gera a resposta XML com os dados do Zeep."""
    response = etree.Element("ResponseV2", xmlns_xsi="http://www.w3.org/2001/XMLSchema-instance", xmlns_xsd="http://www.w3.org/2001/XMLSchema")

    # Mensagem de sucesso
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "CEP encontrado com sucesso"

    # Retorno dos valores
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    # Adicionando os campos do endereço do Zeep
    adicionar_campo(fields, "LOGRADOURO", data.logradouro)
    adicionar_campo(fields, "COMPLEMENTO", data.complemento)
    adicionar_campo(fields, "BAIRRO", data.bairro)
    adicionar_campo(fields, "CIDADE", data.cidade)
    adicionar_campo(fields, "ESTADO", data.uf)

    # Texto curto
    etree.SubElement(return_value, "ShortText").text = "Endereço retornado com sucesso"
    etree.SubElement(return_value, "LongText").text = ""
    etree.SubElement(return_value, "Value").text = "1"

    # Incluindo o GUID fixo na resposta
    etree.SubElement(return_value, "Guid").text = guid

    return etree.tostring(response, encoding="utf-16", xml_declaration=True)

def gerar_erro_xml(mensagem, guid):
    """Gera um XML de erro com mensagem personalizada."""
    response = etree.Element("ResponseV2", xmlns_xsi="http://www.w3.org/2001/XMLSchema-instance", xmlns_xsd="http://www.w3.org/2001/XMLSchema")

    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem

    # Incluindo o GUID fixo na resposta de erro
    etree.SubElement(response, "Guid").text = guid

    return Response(etree.tostring(response, encoding="utf-16", xml_declaration=True), content_type="application/xml")

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML."""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value


# ... (restante do código: gerar_erro_xml, adicionar_campo)

if __name__ == "__main__":
    app.run(debug=True)
