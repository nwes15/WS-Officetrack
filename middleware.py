from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)

@app.route('/busca-cep', methods=['POST'])
def busca_cep():
    cep = request.args.get('CEP')

    if not cep:
        return Response('<error>CEP não informado</error>', content_type='application/xml'), 400
    
    try:
        response = requests.get(f'https://viacep.com.br/ws/{cep}/xml/')

        if response.status_code != 200:
            return Response('<error>Erro ao buscar CEP</error>', content_type='application/xml'), 500
        
        root = ET.fromstring(response.content)

        logradouro = root.find('logradouro').text if root.find('logradouro') is not None else ''
        complemento = root.find('complemento').text if root.find('complemento') is not None else ''
        bairro = root.find('bairro').text if root.find('bairro') is not None else ''
        cidade = root.find('localidade').text if root.find('localidade') is not None else ''
        estado = root.find('uf').text if root.find('uf') is not None else ''

        xml_response = f'''
        <response>
            <LOGRADOURO>{logradouro}</LOGRADOURO>
            <COMPLEMENTO>{complemento}</COMPLEMENTO>
            <BAIRRO>{bairro}</BAIRRO>
            <CIDADE>{cidade}</CIDADE>
            <ESTADO>{estado}</ESTADO>
        </response>
        '''
        return Response(xml_response, content_type='application/xml')

    except requests.exceptions.RequestException as e:
        return Response('<error>Erro ao buscar CEP</error>', content_type='application/xml'), 500

if __name__ == '__main__':
    app.run(debug=True)
