from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/busca-cep', methods=['GET'])
def busca_cep():
    cep = request.args.get('CEP')

    if not cep:
        return jsonify({'error': 'CEP não informado'}), 400
    
    try:
        response = requests.get(f'https://viacep.com.br/ws/{cep}/json/')
        dados = response.json()

        if "erro" in dados:
            return jsonify({'error': 'CEP não encontrado'}), 404
        
        return jsonify({
            'RUA': dados.get('logradouro', ''),
            'COMPLEMENTO': dados.get('complemento', ''),
            'BAIRRO': dados.get('bairro', ''),
            'CIDADE': dados.get('localidade', ''),
            'ESTADO': dados.get('uf', ''),
        })
    except requests.exceptions.RequestException as e:
        return jsonify({'error': 'Erro ao buscar CEP'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
