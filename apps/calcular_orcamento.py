from flask import request, Response
from lxml import etree
import logging
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

def calcular_orcamento():
    """
    Calculadora automática de orçamento e peças em tabela.
    Localiza a tabela de itens/serviços, lê QTD e VALOR_UNIT de cada linha,
    calcula o total da linha e totaliza no formulário:
    - SUBTOTAL
    - DESCONTO
    - VALOR_TOTAL_GERAL
    - TOTAL_ITENS
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro XML")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        # Localiza tabela que possua campos de quantidade ou valor
        tabelas = root.xpath(".//TableField[.//Field[Id='QTD' or Id='QUANTIDADE' or Id='VALOR_UNIT' or Id='PRECO']]")

        desconto_nodes = root.xpath(".//Field[Id='DESCONTO' or ID='DESCONTO']/Value")
        desconto_str = desconto_nodes[0].text if desconto_nodes and desconto_nodes[0].text else "0"
        desconto = extrair_float(desconto_str)

        linhas_calculadas = []
        subtotal = 0.0
        total_qtd = 0.0

        if tabelas:
            tabela = tabelas[0]
            id_tabela = tabela.findtext("Id") or tabela.findtext("ID") or "TABELA_ITENS"
            rows = tabela.xpath(".//Rows/Row")

            for idx, row in enumerate(rows, start=1):
                item_nome_node = row.xpath(".//Field[Id='ITEM' or Id='PRODUTO' or Id='DESCRICAO' or Id='SERVICO']/Value")
                item_nome = item_nome_node[0].text if item_nome_node and item_nome_node[0].text else f"Item {idx}"

                qtd_node = row.xpath(".//Field[Id='QTD' or Id='QUANTIDADE']/Value")
                qtd_str = qtd_node[0].text if qtd_node and qtd_node[0].text else "1"
                qtd = extrair_float(qtd_str)
                if qtd == 0:
                    qtd = 1.0

                unit_node = row.xpath(".//Field[Id='VALOR_UNIT' or Id='PRECO_UNIT' or Id='VALOR' or Id='PRECO']/Value")
                unit_str = unit_node[0].text if unit_node and unit_node[0].text else "0"
                unit = extrair_float(unit_str)

                total_linha = qtd * unit
                subtotal += total_linha
                total_qtd += qtd

                linhas_calculadas.append({
                    "ITEM": item_nome,
                    "QTD": formatar_br(qtd),
                    "VALOR_UNIT": formatar_br(unit),
                    "VALOR_TOTAL_ITEM": formatar_br(total_linha)
                })
        else:
            id_tabela = None

        total_geral = max(0.0, subtotal - desconto)

        campos_retorno = {
            "SUBTOTAL": f"R$ {formatar_br(subtotal)}",
            "DESCONTO": f"R$ {formatar_br(desconto)}",
            "VALOR_TOTAL_GERAL": f"R$ {formatar_br(total_geral)}",
            "TOTAL_ITENS": str(int(total_qtd))
        }

        msg_popup = f"Orçamento Calculado com Sucesso!\n\nItens: {int(total_qtd)}\nSubtotal: R$ {formatar_br(subtotal)}\nDesconto: R$ {formatar_br(desconto)}\nTOTAL: R$ {formatar_br(total_geral)}"

        return gerar_resposta_xml(
            sucesso=True,
            mensagem=msg_popup,
            short_text="Calculado",
            campos=campos_retorno,
            id_tabela=id_tabela,
            linhas_tabela=linhas_calculadas,
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro em calcular_orcamento: {e}", exc_info=True)
        return gerar_resposta_xml(sucesso=False, mensagem=f"Erro interno: {str(e)}", short_text="Erro")


def extrair_float(valor_str):
    if not valor_str:
        return 0.0
    limpo = str(valor_str).replace("R$", "").replace(" ", "").strip()
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    try:
        return float(limpo)
    except:
        return 0.0

def formatar_br(num):
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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

    # Atualiza a tabela com os totais de linha calculados se aplicável
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

