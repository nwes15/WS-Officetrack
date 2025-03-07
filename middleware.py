from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)

# Guid fixo
GUID_FIXO = "f113c885-2d76-4f08-acda-40138b028050"

@app.route('/consultar-cep', methods=['POST'])
def consultar_cep():
    try:
        # Recebe o XML do corpo da requisição
        xml_recebido = request.data

        # Log para depuração (opcional)
        print("XML Recebido:", xml_recebido.decode('utf-8'))

        # Parseia o XML recebido
        root = ET.fromstring(xml_recebido)

        # Extrai o valor do campo CEP
        cep = None
        for field in root.findall('.//Field'):
            if field.find('Id').text == 'CEP':
                cep = field.find('Value').text
                break

        if not cep:
            # Se o CEP não for encontrado, retorna uma mensagem de erro
            resposta_erro = '''
            <Response>
                <Message>
                    <Text>CEP não encontrado no XML recebido</Text>
                </Message>
            </Response>
            '''
            return Response(resposta_erro, content_type='application/xml'), 400

        # Faz a requisição à API do ViaCEP
        url = f'https://viacep.com.br/ws/{cep}/json/'
        response = requests.get(url)
        if response.status_code != 200:
            # Se a API do ViaCEP retornar um erro, retorna uma mensagem de erro
            resposta_erro = '''
            <Response>
                <Message>
                    <Text>Erro ao consultar o CEP na API do ViaCEP</Text>
                </Message>
            </Response>
            '''
            return Response(resposta_erro, content_type='application/xml'), 500

        dados_cep = response.json()

        # Cria o XML de resposta
        root_resposta = ET.Element('Response')

        # Mensagem de sucesso
        mensagem = ET.SubElement(root_resposta, 'Message')
        texto_mensagem = ET.SubElement(mensagem, 'Text')
        texto_mensagem.text = 'CEP encontrado com sucesso'

        # Valor de retorno
        return_value = ET.SubElement(root_resposta, 'ReturnValue')

        # Campos de retorno
        fields = ET.SubElement(return_value, 'Fields')

        # Adiciona os campos do endereço
        campos_endereco = {
            'LOGRADOURO': dados_cep.get('logradouro', ''),
            'COMPLEMENTO': dados_cep.get('complemento', ''),
            'BAIRRO': dados_cep.get('bairro', ''),
            'CIDADE': dados_cep.get('localidade', ''),
            'ESTADO': dados_cep.get('uf', '')
        }

        for id_campo, valor_campo in campos_endereco.items():
            field = ET.SubElement(fields, 'Field')
            field_id = ET.SubElement(field, 'Id')
            field_id.text = id_campo
            field_value = ET.SubElement(field, 'Value')
            field_value.text = valor_campo

        # Usa o Guid fixo no XML de resposta
        guid_element = ET.SubElement(return_value, 'Guid')
        guid_element.text = GUID_FIXO

        # Converte o XML para string
        xml_resposta = ET.tostring(root_resposta, encoding='utf-8', method='xml')

        # Retorna o XML como resposta
        return Response(xml_resposta, content_type='application/xml')

    except ET.ParseError as e:
        # Se o XML estiver malformado, retorna uma mensagem de erro
        resposta_erro = f'''
        <Response>
            <Message>
                <Text>Erro ao processar o XML recebido: {str(e)}</Text>
            </Message>
        </Response>
        '''
        return Response(resposta_erro, content_type='application/xml'), 400

if __name__ == '__main__':
    app.run(debug=True)
