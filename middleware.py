from flask import Flask, request, jsonify
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)

@app.route('/busca-cep', methods=['GET'])
def busca_cep():
    cep = request.args.get('CEP')

    if not cep:
        return jsonify({'error': 'CEP não informado'}), 400
    
    try:
        # Alterar para URL XML
        response = requests.get(f'https://viacep.com.br/ws/{cep}/xml/')

        # Verifica se a resposta foi bem-sucedida
        if response.status_code != 200:
            return jsonify({'error': 'Erro ao buscar CEP'}), 500
        
        # Parsea o XML
        root = ET.fromstring(response.content)

        # Extrai os dados do XML
        logradouro = root.find('logradouro').text if root.find('logradouro') is not None else ''
        complemento = root.find('complemento').text if root.find('complemento') is not None else ''
        bairro = root.find('bairro').text if root.find('bairro') is not None else ''
        cidade = root.find('localidade').text if root.find('localidade') is not None else ''
        estado = root.find('uf').text if root.find('uf') is not None else ''

        return jsonify({
            'LOGRADOURO': logradouro,
            'COMPLEMENTO': complemento,
            'BAIRRO': bairro,
            'CIDADE': cidade,
            'ESTADO': estado,
        })
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Erro ao buscar CEP'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
