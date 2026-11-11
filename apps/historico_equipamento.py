from flask import request, Response
from lxml import etree
import logging
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

def historico_equipamento():
    """
    Busca o histórico de manutenções de um equipamento a partir do COD_EQUIPAMENTO
    e injeta as últimas intervenções diretamente em uma tabela TAB_HISTORICO no formulário.
    Preenche também:
    - FABRICANTE
    - MODELO_EQUIPAMENTO
    - STATUS_GARANTIA
    - ULTIMA_REVISAO
    - Tabela TAB_HISTORICO com 3 a 5 linhas
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro XML")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        cod_nodes = root.xpath(".//Field[Id='COD_EQUIPAMENTO' or ID='COD_EQUIPAMENTO' or Id='NUM_SERIE' or ID='NUM_SERIE']/Value")
        cod_equipamento = cod_nodes[0].text.strip() if cod_nodes and cod_nodes[0].text else ""

        if not cod_equipamento:
            return gerar_resposta_xml(
                sucesso=False,
                mensagem="Por favor, informe ou escaneie o código do equipamento no campo COD_EQUIPAMENTO.",
                short_text="Sem Código",
                long_text="Preencha o COD_EQUIPAMENTO e toque na lixeira para consultar"
            )

        # Base de histórico simulada (integrável com banco de dados de ativos)
        campos_retorno = {
            "FABRICANTE": "SCHNEIDER ELECTRIC",
            "MODELO_EQUIPAMENTO": "QUADRO DE DISTRIBUIÇÃO QGBT-04",
            "STATUS_GARANTIA": "FORA DA GARANTIA (CONTRATO MANUTENÇÃO)",
            "ULTIMA_REVISAO": "15/09/2026"
        }

        # Linhas de histórico que serão injetadas na tabela TAB_HISTORICO
        historico_linhas = [
            {
                "DATA": "15/09/2026",
                "TECNICO": "Carlos Silva",
                "SERVICO": "Reaperto de barramentos e termografia",
                "STATUS": "CONCLUÍDO SEM ANOMALIA"
            },
            {
                "DATA": "10/06/2026",
                "TECNICO": "Marcos Oliveira",
                "SERVICO": "Troca de disjuntor bipolar 32A circuito 04",
                "STATUS": "PEÇA SUBSTITUÍDA"
            },
            {
                "DATA": "18/03/2026",
                "TECNICO": "Wesley Novais",
                "SERVICO": "Inspeção semestral preventiva e limpeza interna",
                "STATUS": "CONCLUÍDO"
            }
        ]

        msg_popup = f"Equipamento Localizado!\n\nAtivo: {cod_equipamento}\nModelo: {campos_retorno['MODELO_EQUIPAMENTO']}\nÚltima Revisão: {campos_retorno['ULTIMA_REVISAO']}\n\nA tabela TAB_HISTORICO foi carregada com as últimas manutenções!"

        return gerar_resposta_xml(
            sucesso=True,
            mensagem=msg_popup,
            short_text="OK",
            campos=campos_retorno,
            id_tabela="TAB_HISTORICO",
            linhas_tabela=historico_linhas,
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro em historico_equipamento: {e}", exc_info=True)
        return gerar_resposta_xml(sucesso=False, mensagem=f"Erro interno: {str(e)}", short_text="Erro")


def gerar_resposta_xml(sucesso, mensagem, short_text, campos=None, id_tabela=None, linhas_tabela=None, long_text=""):
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

    if id_tabela and linhas_tabela:
        table_field = etree.SubElement(fields, "TableField")
        etree.SubElement(table_field, "ID").text = id_tabela
        rows_elem = etree.SubElement(table_field, "Rows")
        for linha in linhas_tabela:
            row_elem = etree.SubElement(rows_elem, "Row")
            f_elem = etree.SubElement(row_elem, "Fields")
            for col_id, col_val in linha.items():
                adicionar_campo(f_elem, col_id, col_val)

    etree.SubElement(return_value, "ShortText").text = short_text
    if long_text:
        etree.SubElement(return_value, "LongText").text = long_text
    etree.SubElement(return_value, "Value").text = "1" if sucesso else "0"

    xml_header = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    return Response((xml_header + xml_body).encode("utf-16"), content_type="application/xml; charset=utf-16")

