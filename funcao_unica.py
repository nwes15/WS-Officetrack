from flask import Flask, request, Response
from lxml import etree
import random
import logging
from io import StringIO

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Dicionário global para controle dos valores
valores_gerados = {
    'tstpeso0': set(),  # Armazena todos os valores gerados com TSTPESO=0
    'ultimos_valores': {
        'balanca1': None,
        'balanca2': None
    }
}

def gerar_valor_unico():
    """Gera um valor único quando TSTPESO=0"""
    while True:
        valor = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')
        if valor not in valores_gerados['tstpeso0']:
            valores_gerados['tstpeso0'].add(valor)
            return valor

def gerar_valores_peso(tstpeso, balanca):
    """Gera valores de peso garantindo não repetição quando TSTPESO=0"""
    if tstpeso == "0":
        # Para TSTPESO=0, gera valores iguais mas únicos entre balanças
        valor_comum = gerar_valor_unico()
        valores_gerados['ultimos_valores'][balanca] = valor_comum
        return valor_comum, valor_comum
    else:
        # Para TSTPESO=1, gera valores independentes
        peso = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')
        pesobalanca = str(round(random.uniform(0.5, 500), 2)).replace('.', ',')
        valores_gerados['ultimos_valores'][balanca] = peso
        return peso, pesobalanca

def extrair_campos_xml(xml_data):
    """Extrai campos relevantes do XML de entrada"""
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()
        
        campos = {}
        for field in root.findall(".//Field"):
            field_id = field.findtext("Id") or field.findtext("ID")
            if field_id:
                campos[field_id] = field.findtext("Value")
        
        return campos
    except Exception as e:
        logging.error(f"Erro ao processar XML: {e}")
        return None

def determinar_balanca(campos):
    """Determina qual balança foi acionada baseada nos campos do XML"""
    # Verifica se VALIDAPESO1 está ativo
    if campos.get("VALIDAPESO1") == "Valida Peso Caixa" or campos.get("VALIDAPESO1_IsVisible") == "1":
        return "balanca1"
    
    # Verifica se VALIDAPESO2 está ativo
    if campos.get("VALIDAPESO2") == "Valida Peso Caixa 2" or campos.get("VALIDAPESO2_IsVisible") == "1":
        return "balanca2"
    
    # Fallback: Verifica CX2
    if campos.get("CX2") == "1":
        return "balanca2"
    
    # Padrão: balanca1
    return "balanca1"

def gerar_resposta_xml(peso, pesobalanca, balanca):
    """Gera a resposta XML formatada corretamente"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Seção de mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Consulta realizada com sucesso."
    
    # Seção ReturnValueV2
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    
    # Adiciona campos específicos da balança
    if balanca == "balanca1":
        adicionar_campo(fields, "PESO1", peso)
        adicionar_campo(fields, "PESOBALANCA1", pesobalanca)
        adicionar_campo(fields, "CX2", "0")
    else:
        adicionar_campo(fields, "PESO2", peso)
        adicionar_campo(fields, "PESOBALANCA2", pesobalanca)
        adicionar_campo(fields, "CX2", "1")
    
    # Campos comuns
    adicionar_campo(fields, "TSTPESO", "1")
    
    # Textos padrão
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"
    
    # Gerar XML final
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    return xml_declaration + "\n" + xml_str

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML de resposta"""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = value

@app.route("/consultar_peso", methods=['POST'])
def consultar_peso_unico():
    try:
        # Obter XML da requisição
        if request.content_type == 'application/xml':
            xml_data = request.data.decode('utf-8')  # Lê os dados XML da requisição
        else:
            xml_data = request.form.get('xml') or request.form.get('TextXML') or next(iter(request.form.values()))

        if not xml_data:
            return gerar_erro("Nenhum dado XML encontrado na requisição")
        
        # Extrair campos do XML
        campos = extrair_campos_xml(xml_data)
        if not campos:
            return gerar_erro("Não foi possível extrair campos do XML")
        
        # Determinar qual balança foi acionada
        balanca = determinar_balanca(campos)
        
        # Verificar TSTPESO
        tstpeso = campos.get("TSTPESO", "0")
        if tstpeso not in ["0", "1"]:
            return gerar_erro("Campo TSTPESO deve ser 0 ou 1")
        
        # Gerar valores de peso
        peso, pesobalanca = gerar_valores_peso(tstpeso, balanca)
        
        # Gerar resposta
        xml_resposta = gerar_resposta_xml(peso, pesobalanca, balanca)
        
        return Response(xml_resposta.encode('utf-16'), content_type='application/xml; charset=utf-16')
    
    except Exception as e:
        logging.error(f"Erro no processamento: {str(e)}")
        return gerar_erro(f"Erro interno: {str(e)}")

def gerar_erro(mensagem):
    """Gera uma resposta de erro em formato XML"""
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    response = etree.Element("ResponseV2", nsmap=nsmap)
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem
    
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    return xml_declaration + "\n" + xml_str