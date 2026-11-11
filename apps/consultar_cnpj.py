from flask import request, Response
from lxml import etree
import logging
import requests
import re
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

def consultar_cnpj():
    """
    Consulta dados cadastrais de pessoa jurídica via BrasilAPI a partir do campo CNPJ.
    Preenche automaticamente no formulário:
    - RAZAO_SOCIAL
    - NOME_FANTASIA
    - SITUACAO
    - LOGRADOURO
    - NUMERO
    - BAIRRO
    - CIDADE
    - ESTADO
    - CEP
    - TELEFONE
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro XML")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        # Extrai o campo CNPJ
        cnpj_nodes = root.xpath(".//Field[Id='CNPJ' or ID='CNPJ']/Value")
        cnpj_bruto = cnpj_nodes[0].text if cnpj_nodes and cnpj_nodes[0].text else ""
        cnpj_limpo = re.sub(r"\D", "", cnpj_bruto)

        if not cnpj_limpo or len(cnpj_limpo) != 14:
            return gerar_resposta_xml(
                sucesso=False,
                mensagem=f"CNPJ inválido ou incompleto: '{cnpj_bruto}'. Digite os 14 dígitos.",
                short_text="CNPJ Inválido",
                long_text="Toque na lixeira e informe um CNPJ válido com 14 dígitos"
            )

        logging.debug(f"Consultando CNPJ: {cnpj_limpo} na BrasilAPI...")
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 404:
            return gerar_resposta_xml(
                sucesso=False,
                mensagem=f"CNPJ {cnpj_bruto} não encontrado na Receita Federal.",
                short_text="Não Encontrado",
                long_text="Toque na lixeira para nova consulta após correção"
            )
        elif resp.status_code != 200:
            return gerar_resposta_xml(
                sucesso=False,
                mensagem="Erro de comunicação com a base da Receita Federal. Tente novamente.",
                short_text="Erro API",
                long_text="Toque na lixeira e tente novamente em instantes"
            )

        dados = resp.json()

        razao = dados.get("razao_social") or ""
        fantasia = dados.get("nome_fantasia") or razao
        situacao = dados.get("descricao_situacao_cadastral") or "ATIVA"
        logradouro = dados.get("logradouro") or ""
        numero = dados.get("numero") or ""
        bairro = dados.get("bairro") or ""
        municipio = dados.get("municipio") or ""
        uf = dados.get("uf") or ""
        cep = dados.get("cep") or ""
        ddd = dados.get("ddd_telefone_1") or ""

        campos_retorno = {
            "RAZAO_SOCIAL": razao,
            "NOME_FANTASIA": fantasia,
            "SITUACAO": situacao,
            "LOGRADOURO": logradouro,
            "NUMERO": numero,
            "BAIRRO": bairro,
            "CIDADE": municipio,
            "ESTADO": uf,
            "CEP": cep,
            "TELEFONE": ddd
        }

        msg_popup = f"CNPJ Validado com Sucesso!\n\nRazão: {razao}\nSituação: {situacao}\nCidade/UF: {municipio}/{uf}"

        return gerar_resposta_xml(
            sucesso=True,
            mensagem=msg_popup,
            short_text="OK",
            campos=campos_retorno,
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro em consultar_cnpj: {e}", exc_info=True)
        return gerar_resposta_xml(sucesso=False, mensagem=f"Erro interno: {str(e)}", short_text="Erro")


def gerar_resposta_xml(sucesso, mensagem, short_text, campos=None, long_text=""):
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }
    response = etree.Element("ResponseV2", nsmap=nsmap)

    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem

    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    if campos:
        for k, v in campos.items():
            adicionar_campo(fields, k, str(v))

    etree.SubElement(return_value, "ShortText").text = short_text
    if long_text:
        etree.SubElement(return_value, "LongText").text = long_text
    etree.SubElement(return_value, "Value").text = "1" if sucesso else "0"

    xml_header = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    return Response((xml_header + xml_body).encode("utf-16"), content_type="application/xml; charset=utf-16")

