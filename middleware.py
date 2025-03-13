from flask import Flask
from dotenv import load_dotenv
import logging
from consultar_cep import consultar_cep
from consultar_groq import consultar_groq
from consultar_peso import consultar_peso
from capturar_xml import capturar_xml


load_dotenv()

app = Flask(__name__)

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

# Registrar as rotas de cada serviço
app.add_url_rule("/consultar_cep", methods=["POST"], view_func=consultar_cep)
app.add_url_rule("/consultar_groq", methods=['POST'], view_func=consultar_groq)
app.add_url_rule("/consultar_peso", methods=['POST'], view_func=consultar_peso)
app.add_url_rule("/capturar_xml", methods=['POST'], view_func=capturar_xml)


if __name__ == '__main__':
    app.run(debug=True, port=5000)