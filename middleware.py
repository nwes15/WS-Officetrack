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
from apps.cepv2 import consultar_cepv2
from apps.talk_descript import consultar_groqv2
from apps.rota import simple_xml
from apps.cepv3 import consultar_cepv3
from apps.validar_extintores import validar_extintores
from apps.validar_duplicidade import validar_duplicidade
from apps.consultar_cnpj import consultar_cnpj
from apps.consultar_placa import consultar_placa
from apps.gerar_laudo_ia import gerar_laudo_ia
from apps.diagnostico_ia import diagnostico_ia
from apps.calcular_orcamento import calcular_orcamento
from apps.historico_equipamento import historico_equipamento
from apps.validar_conformidade_nr import validar_conformidade_nr
from apps.notificar_whatsapp import notificar_whatsapp
from apps.aprovacao_externa import (
    iniciar_aprovacao_externa,
    sala_espera,
    responder_externo,
    status_aprovacao_api,
    finalizar_aprovacao,
    consultar_aprovacao_manual,
)
from apps.chat_ia_openurl import (
    iniciar_chat_ia,
    tela_chat_ia,
    enviar_mensagem_chat_ia,
    resumir_chat_ia,
    finalizar_chat_ia,
)
from apps.assinatura_remota import (
    iniciar_assinatura_remota,
    sala_espera_assinatura,
    tela_assinar_externo,
    servir_imagem_assinatura,
    ver_comprovante_assinatura,
    status_assinatura_api,
    finalizar_assinatura,
    consultar_assinatura_manual,
)
from apps.roleta_raspadinha import (
    iniciar_premio,
    tela_premio,
    jogar_premio_api,
    finalizar_premio,
    consultar_premio_manual,
)
from apps.dashboard_tabela import (
    iniciar_dashboard_tabela,
    tela_dashboard_tabela,
    finalizar_dashboard_tabela,
    consultar_dashboard_manual,
)
from apps.validar_cracha import (
    validar_cracha,
    cracha_digital,
    iniciar_scanner_cracha,
    tela_scanner_cracha,
    api_validar_scanner,
    finalizar_scanner_cracha,
)


load_dotenv()

app = Flask(__name__)

# Configuração do logger
logging.basicConfig(level=logging.DEBUG)

# Rota de healthcheck / raiz para Cloudflare e verificações
@app.route("/", methods=["GET"])
def home():
    return {
        "status": "online",
        "service": "WS-Officetrack Middleware",
        "message": "Serviços ativos e operacionais."
    }, 200

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
app.add_url_rule("/consultar_groqv2", methods=['POST'], view_func=consultar_groqv2)
app.add_url_rule("/simple-xml", methods=['GET'], view_func=simple_xml)
app.add_url_rule("/consultar_cepv3", methods=['POST'], view_func=consultar_cepv3)
app.add_url_rule("/validar_extintores", methods=['POST'], view_func=validar_extintores)
app.add_url_rule("/validar_duplicidade", methods=['POST'], view_func=validar_duplicidade)
app.add_url_rule("/consultar_cnpj", methods=['POST'], view_func=consultar_cnpj)
app.add_url_rule("/consultar_placa", methods=['POST'], view_func=consultar_placa)
app.add_url_rule("/gerar_laudo_ia", methods=['POST'], view_func=gerar_laudo_ia)
app.add_url_rule("/diagnostico_ia", methods=['POST'], view_func=diagnostico_ia)
app.add_url_rule("/calcular_orcamento", methods=['POST'], view_func=calcular_orcamento)
app.add_url_rule("/historico_equipamento", methods=['POST'], view_func=historico_equipamento)
app.add_url_rule("/validar_conformidade_nr", methods=['POST'], view_func=validar_conformidade_nr)
app.add_url_rule("/notificar_whatsapp", methods=['POST'], view_func=notificar_whatsapp)
app.add_url_rule("/iniciar_aprovacao_externa", methods=['POST'], view_func=iniciar_aprovacao_externa)
app.add_url_rule("/espera/<tx_id>", methods=['GET'], view_func=sala_espera)
app.add_url_rule("/responder/<tx_id>", methods=['GET', 'POST'], view_func=responder_externo)
app.add_url_rule("/api/status_aprovacao/<tx_id>", methods=['GET'], view_func=status_aprovacao_api)
app.add_url_rule("/finalizar_aprovacao/<tx_id>", methods=['POST', 'GET'], view_func=finalizar_aprovacao)
app.add_url_rule("/consultar_aprovacao_manual", methods=['POST'], view_func=consultar_aprovacao_manual)
app.add_url_rule("/iniciar_chat_ia", methods=['POST'], view_func=iniciar_chat_ia)
app.add_url_rule("/chat_ia/<chat_id>", methods=['GET'], view_func=tela_chat_ia)
app.add_url_rule("/api/chat_ia/<chat_id>/mensagem", methods=['POST'], view_func=enviar_mensagem_chat_ia)
app.add_url_rule("/api/chat_ia/<chat_id>/resumir", methods=['POST'], view_func=resumir_chat_ia)
app.add_url_rule("/finalizar_chat_ia/<chat_id>", methods=['POST', 'GET'], view_func=finalizar_chat_ia)
app.add_url_rule("/iniciar_assinatura_remota", methods=['POST'], view_func=iniciar_assinatura_remota)
app.add_url_rule("/espera_assinatura/<tx_id>", methods=['GET'], view_func=sala_espera_assinatura)
app.add_url_rule("/assinar/<tx_id>", methods=['GET', 'POST'], view_func=tela_assinar_externo)
app.add_url_rule("/assinatura_img/<tx_id>", methods=['GET', 'HEAD'], view_func=servir_imagem_assinatura)
app.add_url_rule("/ver_assinatura/<tx_id>", methods=['GET'], view_func=ver_comprovante_assinatura)
app.add_url_rule("/api/status_assinatura/<tx_id>", methods=['GET'], view_func=status_assinatura_api)
app.add_url_rule("/finalizar_assinatura/<tx_id>", methods=['POST', 'GET'], view_func=finalizar_assinatura)
app.add_url_rule("/consultar_assinatura_manual", methods=['POST'], view_func=consultar_assinatura_manual)
app.add_url_rule("/iniciar_premio", methods=['POST'], view_func=iniciar_premio)
app.add_url_rule("/premio/<tx_id>", methods=['GET'], view_func=tela_premio)
app.add_url_rule("/api/premio/<tx_id>/jogar", methods=['POST'], view_func=jogar_premio_api)
app.add_url_rule("/finalizar_premio/<tx_id>", methods=['POST', 'GET'], view_func=finalizar_premio)
app.add_url_rule("/consultar_premio_manual", methods=['POST'], view_func=consultar_premio_manual)
app.add_url_rule("/iniciar_dashboard_tabela", methods=['POST'], view_func=iniciar_dashboard_tabela)
app.add_url_rule("/dashboard_tabela/<tx_id>", methods=['GET'], view_func=tela_dashboard_tabela)
app.add_url_rule("/finalizar_dashboard_tabela/<tx_id>", methods=['POST', 'GET'], view_func=finalizar_dashboard_tabela)
app.add_url_rule("/consultar_dashboard_manual", methods=['POST'], view_func=consultar_dashboard_manual)
app.add_url_rule("/validar_cracha", methods=['POST'], view_func=validar_cracha)
app.add_url_rule("/cracha_digital/<codigo>", methods=['GET'], view_func=cracha_digital)
app.add_url_rule("/iniciar_scanner_cracha", methods=['POST'], view_func=iniciar_scanner_cracha)
app.add_url_rule("/scanner_cracha/<tx_id>", methods=['GET'], view_func=tela_scanner_cracha)
app.add_url_rule("/api/scanner_cracha/<tx_id>/validar", methods=['POST'], view_func=api_validar_scanner)
app.add_url_rule("/finalizar_scanner_cracha/<tx_id>", methods=['POST', 'GET'], view_func=finalizar_scanner_cracha)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)