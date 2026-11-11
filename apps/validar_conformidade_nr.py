from flask import request, Response
from lxml import etree
import logging
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

def validar_conformidade_nr():
    """
    Validação de Segurança e Saúde Ocupacional (SESMT).
    Verifica se o técnico (EmployeeNumber) possui ASO e certificações válidas
    (NR-10 Elétrica, NR-35 Altura, NR-33 Espaço Confinado) para o TIPO_SERVICO solicitado.
    Preenche no formulário:
    - STATUS_LIBERACAO (LIBERADO ou BLOQUEADO)
    - VALIDADE_ASO
    - CERTIFICADO_NR
    - MENSAGEM_SESMT
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro XML")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        # Obtém técnico e tipo de serviço
        matricula = root.findtext(".//Employee/EmployeeNumber") or "WH3"

        tipo_servico_node = root.xpath(".//Field[Id='TIPO_SERVICO' or ID='TIPO_SERVICO' or Id='ATIVIDADE' or ID='ATIVIDADE']/Value")
        tipo_servico = tipo_servico_node[0].text.strip().upper() if tipo_servico_node and tipo_servico_node[0].text else "GERAL"

        # Matriz simulada de conformidade de colaboradores (integrável com RH/SESMT)
        # Exemplo: Técnico WH3 tem NR-35 em dia, mas NR-33 vencida
        certificacoes_tecnico = {
            "ASO": "VÁLIDO até 20/12/2026",
            "NR-10": "VÁLIDO até 15/08/2026",
            "NR-35": "VÁLIDO até 10/11/2026",
            "NR-33": "VENCIDO em 01/10/2026"
        }

        bloqueado = False
        motivo = ""
        norma_exigida = "GERAL"

        if "ALTURA" in tipo_servico or "NR-35" in tipo_servico:
            norma_exigida = "NR-35 (Trabalho em Altura)"
            if "VENCIDO" in certificacoes_tecnico.get("NR-35", ""):
                bloqueado = True
                motivo = "Treinamento de NR-35 está VENCIDO."
        elif "ELETRIC" in tipo_servico or "NR-10" in tipo_servico:
            norma_exigida = "NR-10 (Segurança em Eletricidade)"
            if "VENCIDO" in certificacoes_tecnico.get("NR-10", ""):
                bloqueado = True
                motivo = "Treinamento de NR-10 está VENCIDO."
        elif "CONFINADO" in tipo_servico or "NR-33" in tipo_servico:
            norma_exigida = "NR-33 (Espaço Confinado)"
            if "VENCIDO" in certificacoes_tecnico.get("NR-33", ""):
                bloqueado = True
                motivo = "Treinamento de NR-33 está VENCIDO! Atividade não autorizada."

        if bloqueado:
            campos_retorno = {
                "STATUS_LIBERACAO": "BLOQUEADO",
                "VALIDADE_ASO": certificacoes_tecnico["ASO"],
                "CERTIFICADO_NR": "IRREGULAR",
                "MENSAGEM_SESMT": f"BLOQUEIO SESMT: {motivo}"
            }
            return gerar_resposta_xml(
                sucesso=False,
                mensagem=f"BLOQUEIO DE SEGURANÇA (SESMT)!\n\nColaborador: {matricula}\nAtividade: {norma_exigida}\nMotivo: {motivo}\n\nO início do trabalho de risco está bloqueado até a regularização do certificado.",
                short_text="BLOQUEADO",
                campos=campos_retorno,
                long_text="Atividade de risco não liberada pelo SESMT"
            )

        # Se liberado
        campos_retorno = {
            "STATUS_LIBERACAO": "LIBERADO",
            "VALIDADE_ASO": certificacoes_tecnico["ASO"],
            "CERTIFICADO_NR": f"{norma_exigida} - OK",
            "MENSAGEM_SESMT": "Colaborador apto para execução da atividade conforme NR vigentes."
        }

        msg_popup = f"Atividade Liberada pelo SESMT!\n\nTécnico: {matricula}\nAtividade: {norma_exigida}\nASO: {certificacoes_tecnico['ASO']}\n\nTrabalho autorizado com uso obrigatório de todos os EPIs aplicáveis!"

        return gerar_resposta_xml(
            sucesso=True,
            mensagem=msg_popup,
            short_text="LIBERADO",
            campos=campos_retorno,
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro em validar_conformidade_nr: {e}", exc_info=True)
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

