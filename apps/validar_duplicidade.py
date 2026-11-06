from flask import request, Response
from lxml import etree
import logging
from io import StringIO
from collections import Counter
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

def validar_duplicidade():
    """
    Validação genérica de duplicidade de registros na tabela do formulário OfficeTrack.
    Independente do ID da tabela (funciona para qualquer tabela), ele localiza
    as linhas que contêm o campo IDLOCAL e verifica se há itens repetidos.
    Se houver duplicidade: emite pop-up (MessageV2) detalhando os itens e linhas, RETORNO='NOK' e ShortText='NOK'.
    Se estiver OK: emite pop-up de sucesso, RETORNO='OK' e ShortText='OK' sem fechar o formulário.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            logging.error("Nenhum XML encontrado na requisição")
            return gerar_resposta_xml(
                sucesso=False,
                mensagem="Não foi possível encontrar dados XML na requisição.",
                short_text="Erro XML",
                retorno="Erro: Dados XML não encontrados"
            )

        logging.debug(f"XML recebido para validação genérica de duplicidade (tamanho: {len(xml_data)} caracteres)")

        # Parsing do XML com recuperação de erros sintáticos
        try:
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(StringIO(xml_data), parser)
            root = tree.getroot()
        except Exception as e:
            logging.error(f"Erro ao parsear XML: {e}")
            return gerar_resposta_xml(
                sucesso=False,
                mensagem=f"Erro ao processar estrutura do XML: {e}",
                short_text="Erro XML",
                retorno="Erro ao parsear XML"
            )

        # Localiza qualquer tabela (TableField) que possua o campo IDLOCAL em suas linhas
        tabelas = root.xpath(".//TableField[.//Field[Id='IDLOCAL' or ID='IDLOCAL']]")

        if not tabelas:
            logging.warning("Nenhuma tabela contendo o campo IDLOCAL foi encontrada no XML")
            return gerar_resposta_xml(
                sucesso=False,
                mensagem="Tabela contendo o campo IDLOCAL não foi encontrada no formulário.",
                short_text="Sem Tabela",
                retorno="Tabela não encontrada"
            )

        # Seleciona as linhas da tabela onde está o IDLOCAL
        tabela_alvo = tabelas[0]
        id_tabela_encontrada = tabela_alvo.findtext("Id") or tabela_alvo.findtext("ID") or "Tabela"
        rows = tabela_alvo.xpath(".//Rows/Row")
        logging.debug(f"Tabela detectada: '{id_tabela_encontrada}' com {len(rows)} linhas")

        if not rows:
            return gerar_resposta_xml(
                sucesso=True,
                mensagem="Nenhuma linha cadastrada na tabela para validar.",
                short_text="Tabela Vazia",
                retorno="Tabela vazia"
            )

        # Percorre as linhas e coleta o campo IDLOCAL
        lista_itens = []
        itens_por_linha = {}

        for idx, row in enumerate(rows, start=1):
            idlocal_nodes = row.xpath(".//Field[Id='IDLOCAL' or ID='IDLOCAL']/Value")
            val = idlocal_nodes[0].text if idlocal_nodes and idlocal_nodes[0].text else ""
            val_limpo = val.strip()

            if val_limpo:
                lista_itens.append(val_limpo)
                itens_por_linha.setdefault(val_limpo, []).append(idx)

        logging.debug(f"Itens coletados em {id_tabela_encontrada}: {lista_itens}")

        # Identifica duplicidades
        contagem = Counter(lista_itens)
        duplicados = [item for item, qtd in contagem.items() if qtd > 1]

        if duplicados:
            detalhes = []
            for d in duplicados:
                linhas_str = ", ".join(str(n) for n in itens_por_linha[d])
                detalhes.append(f"• {d} (Linhas: {linhas_str})")

            mensagem_alerta = "NOK! Duplicidades encontradas, por favor, verifique e corrija!\n\n" + "\n".join(detalhes)
            logging.info(f"Duplicidades encontradas: {mensagem_alerta}")

            return gerar_resposta_xml(
                sucesso=False,
                mensagem=mensagem_alerta,
                short_text="NOK",
                retorno="NOK",
                long_text="Toque na lixeira para nova consulta após correção"
            )

        # Se não há duplicidades: sucesso!
        msg_sucesso = "OK! Pode continuar o preenchimento e envio do formulário;"
        logging.info(f"Validação concluída: {msg_sucesso}")
        return gerar_resposta_xml(
            sucesso=True,
            mensagem=msg_sucesso,
            short_text="OK",
            retorno="OK",
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro inesperado em validar_duplicidade: {e}", exc_info=True)
        return gerar_resposta_xml(
            sucesso=False,
            mensagem=f"Erro interno no servidor: {str(e)}",
            short_text="Erro",
            retorno=f"Erro interno: {str(e)}"
        )


def gerar_resposta_xml(sucesso, mensagem, short_text, retorno="", long_text=""):
    """
    Gera o XML no padrão ResponseV2 em UTF-16 exigido pelo OfficeTrack.
    Não inclui a tag <Action>SendEntry</Action>, mantendo o formulário aberto.
    """
    nsmap = {
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsd': 'http://www.w3.org/2001/XMLSchema'
    }

    response = etree.Element("ResponseV2", nsmap=nsmap)

    # Pop-up no aplicativo móvel
    message = etree.SubElement(response, "MessageV2")
    etree.SubElement(message, "Text").text = mensagem

    # Retorno e campos do formulário
    return_value = etree.SubElement(response, "ReturnValueV2")
    fields = etree.SubElement(return_value, "Fields")

    # Atualiza apenas o campo RETORNO no formulário
    if retorno:
        adicionar_campo(fields, "RETORNO", str(retorno))

    etree.SubElement(return_value, "ShortText").text = short_text
    if long_text:
        etree.SubElement(return_value, "LongText").text = long_text
    etree.SubElement(return_value, "Value").text = "1" if sucesso else "0"

    # Declaração e encoding UTF-16 obrigatório
    xml_header = '<?xml version="1.0" encoding="utf-16"?>\n'
    xml_body = etree.tostring(response, encoding="utf-16", xml_declaration=False).decode("utf-16")
    xml_final = xml_header + xml_body

    return Response(xml_final.encode("utf-16"), content_type="application/xml; charset=utf-16")

