from flask import Flask, request, Response
import random
from lxml import etree

app = Flask(__name__)

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML."""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = f"{float(value):.1f}"

def extract_xml_from_request():
    """Extrai o XML da requisição de várias fontes possíveis"""
    xml_data = None
    
    # Tenta do form primeiro (com vários nomes possíveis)
    if request.form:
        for possible_name in ["TextXML", "textxml", "xmldata", "xml"]:
            if possible_name in request.form:
                xml_data = request.form.get(possible_name)
                break
        
        # Se não encontrou por nome específico, tenta o primeiro campo do form
        if not xml_data and len(request.form) > 0:
            first_key = next(iter(request.form))
            xml_data = request.form.get(first_key)
    
    # Se não encontrou no form, tenta do corpo da requisição
    if not xml_data and request.data:
        try:
            xml_data = request.data.decode('utf-8')
        except:
            pass
    
    return xml_data

def gerar_resposta_xml(quantidade_linhas):
    """Gera a resposta XML com as 11 tabelas e a quantidade especificada de linhas cada."""
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
    
    # Gerar as 11 tabelas
    for i in range(1, 12):
        # Criar TableField
        table_field = etree.SubElement(fields, "TableField")
        etree.SubElement(table_field, "ID").text = f"{i}TESTE_ELETRICO"
        rows = etree.SubElement(table_field, "Rows")
        
        # Gerar linhas para cada tabela (quantidade baseada no valor extraído)
        for j in range(1, quantidade_linhas + 1):
            row = etree.SubElement(rows, "Row")
            # Adicionar atributo IsCurrentRow="True" apenas na primeira linha
            if j == 1:
                row.set("IsCurrentRow", "True")
            
            row_fields = etree.SubElement(row, "Fields")
            
            # Adicionar o campo de resultado com valor decimal aleatório entre 1,0 e 2,1
            valor_decimal = round(random.uniform(1.0, 2.1), 1)
            adicionar_campo(row_fields, f"{i}RESULTADO_TESTEELETRICO", valor_decimal)
    
    # Adicionar campos adicionais do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "Pressione Lixeira para nova consulta"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "58"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return xml_str


def sempre_sistema():
    """Endpoint para processar a requisição e retornar dados do formulário"""
    try:
        # Extrai o XML da requisição
        xml_data = extract_xml_from_request()
        
        # Define um valor padrão para quantidade_linhas
        quantidade_linhas = 60  # Valor padrão
        
        # Se conseguiu extrair o XML, tenta obter o valor de BATERIA_QUANTIDADE
        if xml_data:
            try:
                # Parse do XML
                root = etree.fromstring(xml_data.encode("utf-8"))
                
                # Extração do valor do campo BATERIA_QUANTIDADE
                bateria_quantidade = root.findtext('BATERIA_QUANTIDADE')
                
                # Converter para inteiro se existir
                if bateria_quantidade is not None:
                    quantidade_linhas = int(bateria_quantidade)
            except:
                # Em caso de erro no parsing, mantém o valor padrão
                pass
        
        # Gera a resposta XML com a quantidade de linhas especificada
        xml_str = gerar_resposta_xml(quantidade_linhas)
        return Response(xml_str.encode("utf-16"), content_type="application/xml; charset=utf-16")
    except Exception as e:
        # Em caso de erro, retorna uma mensagem simples
        error_response = f"""<?xml version="1.0" encoding="utf-16"?>
<ResponseV2 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <MessageV2>
    <Text>Erro: {str(e)}</Text>
  </MessageV2>
  <ReturnValueV2>
    <Fields/>
    <ShortText>ERRO</ShortText>
    <LongText/>
    <Value>0</Value>
  </ReturnValueV2>
</ResponseV2>"""
        return Response(error_response.encode("utf-16"), content_type="application/xml; charset=utf-16")
