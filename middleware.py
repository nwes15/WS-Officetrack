from flask import Flask
from dotenv import load_dotenv
import logging
from consultar_cep import consultar_cep
from consultar_groq import consultar_groq
from consultar_peso import consultar_peso
from capturar_xml import capturar_xml
from consultar_endereco import consultar_endereco
from validar_item import validar_item

load_dotenv()

app = Flask(__name__)

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

# Registrar as rotas de cada serviço
app.add_url_rule("/consultar_cep", methods=["POST"], view_func=consultar_cep)
app.add_url_rule("/consultar_groq", methods=['POST'], view_func=consultar_groq)
app.add_url_rule("/consultar_peso", methods=['POST'], view_func=consultar_peso)
app.add_url_rule("/capturar_xml", methods=['POST'], view_func=capturar_xml)
app.add_url_rule("/consultar_endereco", methods=['POST'], view_func=consultar_endereco)
app.add_url_rule("/validar_item", methods=['POST'], view_func=validar_item)


if __name__ == '__main__':
    app.run(debug=True, port=5000)