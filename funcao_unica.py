from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import StringIO
from utils import gerar_erro

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

xml_logger = logging.getLogger('XML_LOGGER')
xml_logger.setLevel(logging.DEBUG)


ultimo_valor = {
    'balanca1': None,
    'balanca2': None
}

def extrair_campos_xml(xml_data):
    """Extrai campos relevantes do XML de entrada"""
    try:
        logging.debug(f"Iniciando extração de campos do XML (tamanho: {len(xml_data)} bytes)")
        xml_logger.debug("\n=== XML RECEBIDO ===\n%s\n=== FIM XML ===", xml_data)

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        campos = {}
        for field in root.findall(".//Field"):
            field_id = field.findtext("ID") or field.findtext("Id")
            if field_id:
                campos[field_id] = field.findtext("Value")
        
        logging.debug(f"Campos extraídos: {campos}")
        return campos
    except Exception as e:
        logging.error(f"Erro ao processar XML: {e}")
        return None

def gerar_valores_peso(tstpeso, balanca):
    """Gera valores de peso conforme a lógica especificada"""
    def formatar_numero():
        return str(round(random.uniform(0.5, 500), 2)).replace('.', ',')

    if tstpeso == "0":
        # Para TSTPESO = 0, peso e pesobalanca devem ser iguais
        valor = formatar_numero()
        return valor, valor
    else:
        # Para TSTPESO = 1, valores devem ser diferentes
        peso = formatar_numero()
        pesobalanca = formatar_numero()
        return peso, pesobalanca

def gerar_resposta_xml(peso, pesobalanca, balanca, tstpeso):
    """Gera a resposta XML formatada corretamente"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }

    response = etree.Element("ResponseV2", nsmap=nsmap)

    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."

    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    if balanca == "balanca1":
        adicionar_campo(fields, "PESO1", peso)
        adicionar_campo(fields, "PESOBALANCA1", pesobalanca)
    else:
        adicionar_campo(fields, "PESO2", peso)
        adicionar_campo(fields, "PESOBALANCA2", pesobalanca)

    adicionar_campo(fields, "TSTPESO", tstpeso)

    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"

    xml_bytes = etree.tostring(response, encoding="utf-16", xml_declaration=True)
    return xml_bytes

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML de resposta"""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value

@app.route("/funcao_unica", methods=['GET', 'POST'])
def consultar_peso_unico():
    """Endpoint principal para consulta de peso"""
    try:
        # Verifica se o parâmetro balanca está na URL
        balanca = request.args.get('balanca', 'balanca1')  # Padrão é balanca1 caso não seja especificado
        
        # Validar se o valor de balanca é válido
        if balanca not in ["balanca1", "balanca2"]:
            return gerar_erro("Valor de 'balanca' inválido. Deve ser 'balanca1' ou 'balanca2'")

        # Obter XML da requisição
        if request.content_type == 'application/xml':
            xml_data = request.data.decode('utf-8')
        else:
            xml_data = request.form.get('xml') or request.form.get('TextXML') or next(iter(request.form.values()))
        
        if not xml_data:
            return gerar_erro("Nenhum dado XML encontrado na requisição")
        
        # Extrair campos do XML
        campos = extrair_campos_xml(xml_data)
        if not campos:
            return gerar_erro("Não foi possível extrair campos do XML")

        tstpeso = campos.get("TSTPESO", "0")
        if tstpeso not in ["0", "1"]:
            return gerar_erro("Campo TSTPESO deve ser 0 ou 1")

        peso, pesobalanca = gerar_valores_peso(tstpeso, balanca)
        ultimo_valor[balanca] = peso

        xml_resposta = gerar_resposta_xml(peso, pesobalanca, balanca, tstpeso)
        return Response(xml_resposta, content_type='application/xml; charset=utf-16')

    except Exception as e:
        logging.error(f"Erro no processamento: {str(e)}")
        return gerar_erro(f"Erro interno: {str(e)}")
