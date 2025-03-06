from flask import Flask, request, Response
import requests
import os
import dicttoxml

app = Flask(__name__)

@app.route('/busca-cep', methods=['GET'])
def busca_cep():
    cep = request.args.get('CEP')

    if not cep:
        return Response('<error>CEP não informado</error>', status=400, mimetype='application/xml')

    try:
        # Fazendo a requisição à API ViaCep
        response = requests.get(f'https://viacep.com.br/ws/{cep}/json/')
        
        # Checando o status da requisição
        if response.status_code != 200:
            return Response('<error>Erro na requisição</error>', status=500, mimetype='application/xml')
        
        dados = response.json()

        # Verificando se o CEP retornou erro
        if "erro" in dados:
            return Response('<error>CEP não encontrado</error>', status=404, mimetype='application/xml')

        # Organizando os dados para conversão para XML
        result = {
            'LOGRADOURO': dados.get('logradouro', ''),
            'COMPLEMENTO': dados.get('complemento', ''),
            'BAIRRO': dados.get('bairro', ''),
            'CIDADE': dados.get('localidade', ''),
            'ESTADO': dados.get('uf', ''),
        }

        # Convertendo para XML
        xml_response = dicttoxml.dicttoxml(result, custom_root='xmlcep', ids=False)

        return Response(xml_response, mimetype='application/xml')
    
    except requests.exceptions.RequestException as e:
        return Response(f'<error>Erro ao buscar CEP: {str(e)}</error>', status=500, mimetype='application/xml')

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
