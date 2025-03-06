from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)

@app.route('/busca-cep', methods=['POST'])
def busca_cep():
    try:
        # Lê o corpo da requisição como XML
        xml_data = request.data.decode("utf-8")
        logging.debug(f"XML recebido: {xml_data}")

        if not xml_data.strip():
            return Response('<error>XML recebido está vazio</error>', content_type='application/xml'), 400

        # Parse do XML
        root = ET.fromstring(xml_data)

        # Procura o campo CEP no XML
        cep = None
        for field in root.findall(".//Field"):
            if field.find("Id").text == "CEP":
                cep = field.find("Value").text
                break

        if not cep:
            return Response('<error>CEP não informado</error>', content_type='application/xml'), 400

        # Faz a requisição à API ViaCEP
        response = requests.get(f'https://viacep.com.br/ws/{cep}/xml/')

        if response.status_code != 200:
            return Response('<error>Erro ao buscar CEP</error>', content_type='application/xml'), 500

        # Parse da resposta da API ViaCEP
        viacep_root = ET.fromstring(response.content)

        # Extrai os dados do endereço
        logradouro = viacep_root.find('logradouro').text if viacep_root.find('logradouro') is not None else ''
        complemento = viacep_root.find('complemento').text if viacep_root.find('complemento') is not None else ''
        bairro = viacep_root.find('bairro').text if viacep_root.find('bairro') is not None else ''
        cidade = viacep_root.find('localidade').text if viacep_root.find('localidade') is not None else ''
        estado = viacep_root.find('uf').text if viacep_root.find('uf') is not None else ''

        # Monta a resposta em XML
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

    except Exception as e:
        logging.error(f"Erro interno: {str(e)}")
        return Response('<error>Erro interno no servidor</error>', content_type='application/xml'), 500

if __name__ == '__main__':
    app.run(debug=True)
