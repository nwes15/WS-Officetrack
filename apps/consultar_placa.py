from flask import request, Response
from lxml import etree
import logging
import re
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

def consultar_placa():
    """
    Valida e consulta veículo pela PLACA (Mercosul e formato clássico).
    Preenche automaticamente no formulário:
    - MARCA
    - MODELO
    - ANO
    - COR
    - TIPO_VEICULO
    - STATUS_VEICULO
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro XML")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        placa_nodes = root.xpath(".//Field[Id='PLACA' or ID='PLACA']/Value")
        placa_bruta = placa_nodes[0].text if placa_nodes and placa_nodes[0].text else ""
        placa_limpa = re.sub(r"[^A-Za-z0-9]", "", placa_bruta).upper()

        # Validação de formato de placa brasileira (Antiga: ABC1234 ou Mercosul: ABC1D23)
        padrao_placa = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
        if not padrao_placa.match(placa_limpa):
            return gerar_resposta_xml(
                sucesso=False,
                mensagem=f"Formato de placa inválido: '{placa_bruta}'. Use o formato padrão (ex: ABC1234 ou ABC1D23).",
                short_text="Placa Inválida",
                long_text="Toque na lixeira para corrigir a placa digitada"
            )

        # Base de frota / simulação inteligente de identificação veicular
        # Pode ser conectada a uma API de frota corporativa, DETRAN ou tabela interna
        tipo_placa = "Mercosul" if placa_limpa[4].isalpha() else "Padrão Antigo"

        # Simulação de dados com base na placa para testes ou integração com banco
        campos_retorno = {
            "PLACA": placa_limpa,
            "MARCA": "RENAULT",
            "MODELO": "MASTER CHASSI 2.3 DCI",
            "ANO": "2023/2024",
            "COR": "BRANCA",
            "TIPO_VEICULO": "UTILITÁRIO CARGA",
            "STATUS_VEICULO": "REGULAR / FROTA ATIVA"
        }

        msg_popup = f"Veículo Localizado!\n\nPlaca: {placa_limpa} ({tipo_placa})\nModelo: {campos_retorno['MODELO']}\nAno/Cor: {campos_retorno['ANO']} - {campos_retorno['COR']}\nStatus: {campos_retorno['STATUS_VEICULO']}"

        return gerar_resposta_xml(
            sucesso=True,
            mensagem=msg_popup,
            short_text="OK",
            campos=campos_retorno,
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro em consultar_placa: {e}", exc_info=True)
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

