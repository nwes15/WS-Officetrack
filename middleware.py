from flask import Flask
from dotenv import load_dotenv
import logging
from apps.consultar_cep import consultar_cep
from apps.consultar_groq import consultar_groq
from apps.consultar_peso import consultar_peso
from apps.consultar_endereco import consultar_endereco
from apps.validar_item import validar_item
from apps.resgate_xml import resgate_xml
from apps.consultar_peso2 import consultar_peso2
from apps.funcao_unica import consultar_peso_unico
from apps.encaixotar import encaixotar_v3
from apps.teste_caixa import encaixotar_v2
from apps.table_estatica import encaixotar_v4
from apps.dados_sempre import sempre_sistema
from cepv2 import consultar_cepv2


load_dotenv()

app = Flask(__name__)

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

# Registrar as rotas de cada serviço
app.add_url_rule("/consultar_cep", methods=["POST"], view_func=consultar_cep)
app.add_url_rule("/consultar_groq", methods=['POST'], view_func=consultar_groq)
app.add_url_rule("/consultar_peso", methods=['POST'], view_func=consultar_peso)
app.add_url_rule("/consultar_endereco", methods=['POST'], view_func=consultar_endereco)
app.add_url_rule("/validar_item", methods=['POST'], view_func=validar_item)
app.add_url_rule("/resgate_xml", methods=['POST'], view_func=resgate_xml)
app.add_url_rule("/consultar_peso2", methods=['POST'], view_func=consultar_peso2)
app.add_url_rule("/funcao_unica", methods=['POST'], view_func=consultar_peso_unico)
app.add_url_rule("/encaixotar", methods=['POST'], view_func=encaixotar_v3)
app.add_url_rule("/teste_caixa", methods=['POST'], view_func=encaixotar_v2)
app.add_url_rule("/table_estatica", methods=['POST'], view_func=encaixotar_v4)
app.add_url_rule("/dados_sempre", methods=['POST'], view_func=sempre_sistema)
app.add_url_rule("/consultar_cepv2", methods=['POST'], view_func=consultar_cepv2)


if __name__ == '__main__':
    app.run(debug=True, port=5001)