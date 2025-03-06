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
        response = requests.get(f'https://viacep.com.br/ws/{cep}/xml/')

        # Verifica se a resposta não é vazia
        if response.text:
            root = ET.fromstring(response.text)  # Faz o parsing do XML
            
            # Extrai os dados do XML
            dados = {
                'LOGRADOURO': root.find('logradouro').text if root.find('logradouro') is not None else '',
                'COMPLEMENTO': root.find('complemento').text if root.find('complemento') is not None else '',
                'BAIRRO': root.find('bairro').text if root.find('bairro') is not None else '',
                'CIDADE': root.find('localidade').text if root.find('localidade') is not None else '',
                'ESTADO': root.find('uf').text if root.find('uf') is not None else ''
            }

            return jsonify(dados)
        else:
            return jsonify({'error': 'CEP não encontrado'}), 404
        
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Erro ao buscar CEP'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
    app.run(debug=True, host='0.0.0.0', port=port)
