from flask import Flask, Response, request
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Middleware para capturar TODAS as requisições
@app.before_request
def log_request_info():
    app.logger.debug('=== ANTES DA REQUISIÇÃO ===')
    app.logger.debug('Headers: %s', request.headers)
    app.logger.debug('Body: %s', request.get_data())
    app.logger.debug('Method: %s', request.method)
    app.logger.debug('URL: %s', request.url)
    app.logger.debug('=============================')

# Rota que aceita QUALQUER método
@app.route('/simple-xml', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def simple_xml():
    try:
        print(f"FUNÇÃO CHAMADA! Método: {request.method}")
        
        xml_data = '''<?xml version="1.0" encoding="utf-8"?>
<Response>
    <ReturnValue>
        <Items>
            <Item>
                <Text>Option One</Text>
                <Value>1</Value>
            </Item>
            <Item>
                <Text>Option Two</Text>
                <Value>2</Value>
            </Item>
            <Item>
                <Text>Option Three</Text>
                <Value>3</Value>
            </Item>
        </Items>
    </ReturnValue>
</Response>'''
        
        print("Enviando resposta XML...")
        return Response(xml_data, mimetype='text/xml')
        
    except Exception as e:
        print(f"ERRO na função: {str(e)}")
        return Response("Erro", status=500)

# Rota catch-all para debug
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    print(f"CATCH ALL: {request.method} /{path}")
    return f"Rota não encontrada: {request.method} /{path}"

if __name__ == '__main__':
    print("=== INICIANDO SERVIDOR ===")
    print("Testando rotas:")
    with app.test_client() as client:
        # Teste interno
        response = client.post('/simple-xml')
        print(f"Teste interno POST: {response.status_code}")
    
    print("Servidor rodando em http://localhost:5000")
    print("=============================")
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)