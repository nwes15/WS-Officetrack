from flask import Flask, Response, request
import logging

app = Flask(__name__)
app.url_map.strict_slashes = False
logging.basicConfig(level=logging.DEBUG)

@app.route('/simple-xml', methods=['GET', 'POST'])  # Aceita ambos os métodos
def simple_xml():
    try:
        # Log detalhado para debug
        app.logger.info(f"=== REQUISIÇÃO RECEBIDA ===")
        app.logger.info(f"Método: {request.method}")
        app.logger.info(f"URL: {request.url}")
        app.logger.info(f"Headers: {dict(request.headers)}")
        app.logger.info(f"Data: {request.data}")
        app.logger.info(f"========================")
        
        xml_data = '''<?xml version="1.0" encoding="utf-16"?>
<Response>
    <ReturnValue>
        <Items>
            <Item>
                <Text>One</Text>
                <Value>1</Value>
            </Item>
            <Item>
                <Text>Two</Text>
                <Value>2</Value>
            </Item>
            <Item>
                <Text>Three</Text>
                <Value>3</Value>
            </Item>
        </Items>
    </ReturnValue>
</Response>'''
        
        app.logger.info("Enviando resposta XML...")
        return Response(xml_data.encode('utf-16'), mimetype='application/xml')
        
    except Exception as e:
        app.logger.error(f"ERRO: {str(e)}")
        error_xml = '''<?xml version="1.0" encoding="utf-16"?>
<Response>
    <Message>
        <Text>Erro interno</Text>
        <Icon>Critical</Icon>
    </Message>
</Response>'''
        return Response(error_xml.encode('utf-16'), mimetype='application/xml')

# Rota de teste para verificar se Flask está funcionando
@app.route('/test', methods=['GET'])
def test():
    return "Flask está funcionando!"

# Rota para listar todas as rotas disponíveis
@app.route('/routes', methods=['GET'])
def show_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule)
        })
    return {'routes': routes}

if __name__ == '__main__':
    print("=== INICIANDO FLASK ===")
    print("Rotas disponíveis:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule} - Métodos: {list(rule.methods)}")
    print("=====================")
    
    app.run(debug=True, host='0.0.0.0', port=5000)