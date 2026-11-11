from flask import request, Response
from lxml import etree
import logging
import requests
import os
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def diagnostico_ia():
    """
    Assistente técnico inteligente de diagnóstico em campo.
    Lê:
    - EQUIPAMENTO (ex: 'Chiller Trane', 'Bomba Centrífuga', 'Motor Trifásico')
    - SINTOMA_DEFEITO (ex: 'vibração excessiva', 'desarme térmico', 'ruído de rolamento')
    Preenche no formulário:
    - DIAGNOSTICO_SUGERIDO (Prováveis causas raiz)
    - PASSO_A_PASSO_TESTES (Checklist de testes recomendados para o técnico fazer no local)
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro XML")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        equip_nodes = root.xpath(".//Field[Id='EQUIPAMENTO' or ID='EQUIPAMENTO']/Value")
        equipamento = equip_nodes[0].text if equip_nodes and equip_nodes[0].text else "Equipamento Industrial Geral"

        sintoma_nodes = root.xpath(".//Field[Id='SINTOMA_DEFEITO' or ID='SINTOMA_DEFEITO' or Id='DEFEITO' or ID='DEFEITO']/Value")
        sintoma = sintoma_nodes[0].text if sintoma_nodes and sintoma_nodes[0].text else ""

        if not sintoma:
            return gerar_resposta_xml(
                sucesso=False,
                mensagem="Por favor, descreva o sintoma ou defeito no campo SINTOMA_DEFEITO.",
                short_text="Sem Sintoma",
                long_text="Preencha o campo SINTOMA_DEFEITO e toque na lixeira para consultar"
            )

        prompt = f"""Você é um Engenheiro Especialista em Diagnóstico de Falhas de Campo.
Equipamento: {equipamento}
Sintoma relatado pelo técnico: {sintoma}

Forneça um guia rápido de diagnóstico em campo estruturado em 2 blocos:
[CAUSAS]
As 3 causas prováveis mais comuns para essa falha em tópicos curtos.
[TESTES]
Passo a passo com 3 a 5 medições/testes práticos rápidos que o técnico deve realizar agora no local com instrumentos (ex: multímetro, termômetro, manômetro)."""

        causas = ""
        testes = ""

        if GROQ_API_KEY:
            try:
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama3-70b-8192",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }
                resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=20)
                if resp.status_code == 200:
                    conteudo = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    if "[CAUSAS]" in conteudo and "[TESTES]" in conteudo:
                        partes = conteudo.split("[TESTES]")
                        causas = partes[0].replace("[CAUSAS]", "").strip()
                        testes = partes[1].strip()
                    else:
                        causas = conteudo.strip()
                        testes = "Verificar alimentação elétrica e condições mecânicas."
            except Exception as e:
                logging.error(f"Erro chamando Groq no diagnostico: {e}")

        if not causas:
            causas = f"1. Sobrecarga mecânica ou desalinhamento.\n2. Variação de tensão ou falta de fase.\n3. Desgaste prematuro de mancais/rolamentos."
            testes = f"1. Medir tensão entre fases e corrente operacional (A).\n2. Checar aquecimento nos bornes com termovisor.\n3. Testar isolamento com megômetro.\n4. Checar fixação e alinhamento mecânico."

        campos_retorno = {
            "DIAGNOSTICO_SUGERIDO": causas,
            "PASSO_A_PASSO_TESTES": testes
        }

        msg_popup = f"Diagnóstico Sugerido para: {equipamento}\n\nPrincipais Causas:\n{causas[:250]}...\n\nConsulte os campos para ver o passo a passo completo dos testes!"

        return gerar_resposta_xml(
            sucesso=True,
            mensagem=msg_popup,
            short_text="OK",
            campos=campos_retorno,
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro em diagnostico_ia: {e}", exc_info=True)
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

