from flask import Flask, request, Response
import requests
import xmltodict

app = Flask(__name__)

@app.route('/busca-cep', methods=['POST'])
def busca_cep():
    # Recebe a requisição SOAP em XML
    soap_request = request.data

    try:
        # Faz o parsing do XML recebido
        data = xmltodict.parse(soap_request)
        
        # Extraindo o CEP do XML (agora vem no campo <Value> dentro de <Field>)
        cep = None
        for field in data['soapenv:Envelope']['soapenv:Body']['web:consultaCep']['Field']:
            if field['Id'] == 'CEP':
                cep = field['Value']
                break

    except (KeyError, xmltodict.expat.ExpatError):
        return Response("<error>Formato SOAP inválido</error>", status=400, content_type='text/xml')

    if not cep:
        return Response("<error>CEP não informado</error>", status=400, content_type='text/xml')

    try:
        # Fazendo a requisição ao ViaCEP no formato XML
        response = requests.get(f'https://viacep.com.br/ws/{cep}/xml/')
        dados = xmltodict.parse(response.text)

        # Se o CEP não for encontrado, retornamos erro
        if 'erro' in dados['xmlcep']:
            return Response("<error>CEP não encontrado</error>", status=404, content_type='text/xml')

        # Montando a resposta SOAP em XML para o Officetrack
        resposta_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Body>
                <response>
                    <LOGRADOURO>{dados['xmlcep']['logradouro']}</LOGRADOURO>
                    <COMPLEMENTO>{dados['xmlcep']['complemento']}</COMPLEMENTO>
                    <BAIRRO>{dados['xmlcep']['bairro']}</BAIRRO>
                    <CIDADE>{dados['xmlcep']['localidade']}</CIDADE>
                    <ESTADO>{dados['xmlcep']['uf']}</ESTADO>
                </response>
            </soapenv:Body>
        </soapenv:Envelope>
        """

        return Response(resposta_xml, content_type='text/xml')

    except requests.exceptions.RequestException:
        return Response("<error>Erro ao buscar CEP</error>", status=500, content_type='text/xml')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    app.run(debug=True, host='0.0.0.0', port=port)
