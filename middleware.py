from flask import Flask, request, Response
import requests
import xmltodict

app = Flask(__name__)

@app.route('/busca-cep', methods=['POST'])
def busca_cep():
    # Recebe a requisição SOAP em XML
    soap_request = request.data
    print("Recebendo SOAP Request:")
    print(soap_request)  # Exibe o XML recebido

    try:
        # Faz o parsing do XML recebido
        data = xmltodict.parse(soap_request)
        print("XML Parsed:", data)

        # Extraindo o CEP do XML
        cep = None
        for field in data['soapenv:Envelope']['soapenv:Body']['web:consultaCep']['Field']:
            if field['Id'] == 'CEP':
                cep = field['Value']
                break
        print("CEP Extraído:", cep)

    except (KeyError, xmltodict.expat.ExpatError) as e:
        print(f"Erro ao processar o XML: {e}")
        return Response("<error>Formato SOAP inválido</error>", status=400, content_type='text/xml')

    if not cep:
        return Response("<error>CEP não informado</error>", status=400, content_type='text/xml')

    try:
        # Fazendo a requisição ao ViaCEP no formato XML
        response = requests.get(f'https://viacep.com.br/ws/{cep}/xml/')
        dados = xmltodict.parse(response.text)
        print("Dados do ViaCEP:", dados)

        # Se o CEP não for encontrado, retornamos erro
        if 'erro' in dados['xmlcep']:
            return Response("<error>CEP não encontrado</error>", status=404, content_type='text/xml')

        # Montando a resposta XML em formato esperado pela documentação
        resposta_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <ReturnValue>
                <Items>
                    <Item>
                        <Text>LOGRADOURO</Text>
                        <Value>{dados['xmlcep']['logradouro']}</Value>
                    </Item>
                    <Item>
                        <Text>COMPLEMENTO</Text>
                        <Value>{dados['xmlcep']['complemento']}</Value>
                    </Item>
                    <Item>
                        <Text>BAIRRO</Text>
                        <Value>{dados['xmlcep']['bairro']}</Value>
                    </Item>
                    <Item>
                        <Text>CIDADE</Text>
                        <Value>{dados['xmlcep']['localidade']}</Value>
                    </Item>
                    <Item>
                        <Text>ESTADO</Text>
                        <Value>{dados['xmlcep']['uf']}</Value>
                    </Item>
                </Items>
            </ReturnValue>
        </Response>
        """

        print("Resposta XML:", resposta_xml)  # Exibe a resposta XML

        return Response(resposta_xml, content_type='text/xml')

    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar CEP: {e}")
        return Response("<error>Erro ao buscar CEP</error>", status=500, content_type='text/xml')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
