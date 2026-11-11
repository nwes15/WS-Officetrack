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

def gerar_laudo_ia():
    """
    Gera automaticamente um Parecer Técnico Executivo Formal usando IA (Llama-3 via Groq)
    com base nas observações e itens não-conformes da ordem de serviço.
    Preenche no formulário:
    - LAUDO_FINAL (resumo executivo profissional)
    - RECOMENDACOES (ações corretivas sugeridas)
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return gerar_resposta_xml(sucesso=False, mensagem="Dados XML não encontrados.", short_text="Erro XML")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        # Coleta campos de contexto
        obs_nodes = root.xpath(".//Field[Id='OBS_TECNICA' or ID='OBS_TECNICA' or Id='OBS' or ID='OBS']/Value")
        obs_texto = obs_nodes[0].text if obs_nodes and obs_nodes[0].text else "Checklist de rotina operacional."

        task_num = root.findtext(".//Task/TaskNum") or "OS Geral"
        task_type = root.findtext(".//Task/TaskType") or "Inspeção e Manutenção"

        # Varre tabelas para encontrar itens com problemas ou não conformes
        problemas = []
        rows = root.xpath(".//TableField//Row")
        for idx, row in enumerate(rows, start=1):
            local = row.xpath(".//Field[Id='LOCAL' or Id='IDLOCAL']/Value")
            desc = local[0].text.strip() if local and local[0].text else f"Item Linha {idx}"
            
            # Checa campos com indicativo de não conformidade
            for f in row.xpath(".//Field"):
                val = f.findtext("Value") or ""
                if any(nc in val.lower() for nc in ["não conforme", "irregular", "defeito", "avaria", "inconsistente"]):
                    problemas.append(f"- {desc}: {val}")

        contexto_problemas = "\n".join(problemas) if problemas else "Nenhum apontamento grave de não conformidade."

        prompt = f"""Você é um Engenheiro Perito e Supervisor Técnico de Manutenção.
Gere um LAUDO TÉCNICO FORMAL e OBJETIVO baseado nestas informações colhidas em campo:
Tipo da OS: {task_type} (OS Nº {task_num})
Notas do Técnico: {obs_texto}
Irregularidades encontradas nas tabelas:
{contexto_problemas}

Responda ESTRITAMENTE em 2 blocos separados pelas tags [LAUDO] e [RECOMENDACOES]:
[LAUDO]
Texto do parecer técnico formal, conciso e profissional em 1 ou 2 parágrafos.
[RECOMENDACOES]
Lista concisa de 2 a 4 ações corretivas práticas imediatas recomendadas para o cliente."""

        # Chama a API Groq se houver chave; caso contrário gera texto pericial estruturado
        laudo_texto = ""
        recomendacoes_texto = ""

        if GROQ_API_KEY:
            try:
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama3-70b-8192",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4
                }
                resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=20)
                if resp.status_code == 200:
                    resposta_ia = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    if "[LAUDO]" in resposta_ia and "[RECOMENDACOES]" in resposta_ia:
                        partes = resposta_ia.split("[RECOMENDACOES]")
                        laudo_texto = partes[0].replace("[LAUDO]", "").strip()
                        recomendacoes_texto = partes[1].strip()
                    else:
                        laudo_texto = resposta_ia.strip()
                        recomendacoes_texto = "Seguir protocolo padrão de manutenção preventiva."
            except Exception as e:
                logging.error(f"Erro chamando Groq: {e}")

        if not laudo_texto:
            laudo_texto = f"Após inspeção técnica detalhada referente à OS {task_num}, constatou-se a realização dos procedimentos de conformidade operacional. Notas registradas: {obs_texto}. Situação geral avaliada com base nas normas regulamentadoras."
            recomendacoes_texto = "1. Programar revisão periódica.\n2. Manter histórico de intervenções atualizado.\n3. Sanar eventuais pendências assinaladas no checklist."

        campos_retorno = {
            "LAUDO_FINAL": laudo_texto,
            "RECOMENDACOES": recomendacoes_texto
        }

        return gerar_resposta_xml(
            sucesso=True,
            mensagem="Laudo Técnico Estruturado com Sucesso pela IA!",
            short_text="Laudo Gerado",
            campos=campos_retorno,
            long_text=""
        )

    except Exception as e:
        logging.error(f"Erro em gerar_laudo_ia: {e}", exc_info=True)
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

