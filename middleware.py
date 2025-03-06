from flask import Flask, request, Response
import requests
import xmltodict

app = Flask(__name__)

@app.route('/busca-cep', methods=['POST'])
def busca_cep():
    # Recebe a requisição SOAP e faz o parsing
    soap_request = request.data
    
    # Converte o XML de entrada para dicionário
    try:
        data = xmltodict.parse(soap_request)
        cep = data['soapenv:Envelope']['soapenv:Body']['web:consultaCep']['cep']
    except KeyError:
        return Response("<error>Formato SOAP inválido</error>", status=400, content_type='text/xml')

    if not cep:
        return Response("<error>CEP não informado</error>", status=400, content_type='text/xml')

    try:
        # Acessa o ViaCEP para buscar as informações do CEP
        response = requests.get(f'https://viacep.com.br/ws/{cep}/xml/')
        dados = response.text

        # Se o CEP não for encontrado, retornamos erro
        if "<erro>" in dados:
            return Response("<error>CEP não encontrado</error>", status=404, content_type='text/xml')

        # Formata a resposta com as informações desejadas no formato XML
        return Response(f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <response>
            <LOGRADOURO>{dados['logradouro']}</LOGRADOURO>
            <COMPLEMENTO>{dados['complemento']}</COMPLEMENTO>
            <BAIRRO>{dados['bairro']}</BAIRRO>
            <CIDADE>{dados['localidade']}</CIDADE>
            <ESTADO>{dados['uf']}</ESTADO>
        </response>
        """, content_type='text/xml')

    except requests.exceptions.RequestException as e:
        return Response("<error>Erro ao buscar CEP</error>", status=500, content_type='text/xml')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    app.run(debug=True, host='0.0.0.0', port=port)
