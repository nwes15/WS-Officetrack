from flask import Flask, request, Response
import random
from lxml import etree

app = Flask(__name__)

def adicionar_campo(parent, field_id, value):
    """Adiciona um campo ao XML."""
    field = etree.SubElement(parent, "Field")
    etree.SubElement(field, "ID").text = field_id
    etree.SubElement(field, "Value").text = str(value)

def gerar_resposta_xml():
    """Gera a resposta XML com as 11 tabelas e 60 linhas cada."""
    # Definir namespaces
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    
    # Criar o elemento raiz com namespaces
    response = etree.Element("ResponseV2", nsmap=nsmap)
    
    # Adicionar seção de mensagem
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = "Dados gerados com sucesso"
    
    # Criar seção ReturnValueV2
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")
    
    # Adicionar campos de exemplo
    adicionar_campo(fields, "Test1", "Teste Elétrico")
    adicionar_campo(fields, "Num1", "123")
    
    # Gerar as 11 tabelas
    for i in range(1, 12):
        # Criar TableField
        table_field = etree.SubElement(fields, "TableField")
        etree.SubElement(table_field, "ID").text = f"{i}TESTE_ELETRICO"
        rows = etree.SubElement(table_field, "Rows")
        
        # Gerar 60 linhas para cada tabela
        for j in range(1, 61):
            row = etree.SubElement(rows, "Row")
            row_fields = etree.SubElement(row, "Fields")
            
            # Adicionar o campo de resultado com valor decimal aleatório
            valor_decimal = round(random.uniform(10, 100), 2)
            adicionar_campo(row_fields, f"{i}RESULTADO_TESTEELETRICO", valor_decimal)
    
    # Adicionar campos adicionais do ReturnValueV2
    etree.SubElement(return_value, "ShortText").text = "DADOS GERADOS COM SUCESSO"
    etree.SubElement(return_value, "LongText")
    etree.SubElement(return_value, "Value").text = "1"
    
    # Gerar XML com declaração e encoding utf-16
    xml_declaration = '<?xml version="1.0" encoding="utf-16"?>'
    xml_str = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_str = xml_declaration + "\n" + xml_str
    
    return xml_str

@app.route('/dados_sempre', methods=['POST'])
def sempre_sistema():
    """Endpoint para processar a requisição e retornar dados do formulário"""
    try:
        # Gera a resposta XML
        xml_str = gerar_resposta_xml()
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