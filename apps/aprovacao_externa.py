from flask import request, Response, jsonify, render_template_string
from lxml import etree
import logging
import sqlite3
import uuid
import os
import re
import requests
from datetime import datetime
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "aprovacoes_externas.db")

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:18080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "default")


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transacoes (
                tx_id TEXT PRIMARY KEY,
                task_num TEXT,
                tecnico TEXT,
                nome_aprovador TEXT,
                tel_aprovador TEXT,
                motivo TEXT,
                status TEXT DEFAULT 'AGUARDANDO',
                decisao TEXT DEFAULT '',
                nome_respondente TEXT DEFAULT '',
                observacao TEXT DEFAULT '',
                criado_em TEXT,
                respondido_em TEXT DEFAULT ''
            )
        """)
        conn.commit()


_init_db()


def _obter_base_url():
    """Detecta automaticamente o domínio (Cloudflare HTTPS ou local HTTP)."""
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    if "trycloudflare" in host or ("127.0.0.1" not in host and "localhost" not in host and not host.startswith("192.168.")):
        # Em túneis/domínios externos, priorizar https se X-Forwarded-Proto não veio
        if not request.headers.get("X-Forwarded-Proto"):
            proto = "https"
    return f"{proto}://{host}"


def iniciar_aprovacao_externa():
    """
    1º Passo (Botão no OfficeTrack):
    Gera a transação (txId), envia o link para o aprovador remoto (WhatsApp se disponível)
    e retorna <Action>OpenUrl</Action> abrindo a Sala de Espera em Tempo Real no app.
    Quando o técnico fechar a Sala de Espera, o OfficeTrack chama automaticamente /finalizar_aprovacao/<tx_id>.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("Não foi possível obter os dados XML do formulário.")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        task_num = root.findtext(".//Task/TaskNum") or "N/A"
        tecnico = root.findtext(".//Employee/EmployeeNumber") or "Técnico"

        # Extrai todos os campos em dicionário case-insensitive (aceita Id, ID, id)
        campos_form = {}
        for f in root.findall(".//Field"):
            fid = f.findtext("Id") or f.findtext("ID") or f.findtext("id")
            fval = f.findtext("Value") or ""
            if fid:
                campos_form[fid.strip().upper()] = fval.strip()

        logging.info(f"[APROVACAO] Campos recebidos do XML: {campos_form}")

        nome_aprovador = (
            campos_form.get("NOME_APROVADOR")
            or campos_form.get("NOME_CLIENTE")
            or campos_form.get("CLIENTE")
            or campos_form.get("APROVADOR")
            or "Aprovador / Cliente"
        )

        tel_bruto = (
            campos_form.get("TEL_APROVADOR")
            or campos_form.get("TEL_CLIENTE")
            or campos_form.get("TELEFONE")
            or campos_form.get("WHATSAPP")
            or campos_form.get("CELULAR")
            or campos_form.get("FONE")
            or campos_form.get("TEL")
            or ""
        )
        tel_limpo = re.sub(r"\D", "", tel_bruto)

        motivo = (
            campos_form.get("MOTIVO_SOLICITACAO")
            or campos_form.get("RESUMO_SERVICO")
            or campos_form.get("OBS_TECNICA")
            or campos_form.get("OBS")
            or "Validação e aprovação externa de atendimento em campo."
        )

        tx_id = str(uuid.uuid4())[:8].upper()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO transacoes (tx_id, task_num, tecnico, nome_aprovador, tel_aprovador, motivo, status, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?, 'AGUARDANDO', ?)""",
                (tx_id, task_num, tecnico, nome_aprovador, tel_limpo, motivo, agora)
            )
            conn.commit()

        base_url = _obter_base_url()
        url_responder = f"{base_url}/responder/{tx_id}"
        url_espera = f"{base_url}/espera/{tx_id}"
        url_webservice_retorno = f"{base_url}/finalizar_aprovacao/{tx_id}"

        evo_url = os.getenv("EVOLUTION_API_URL", EVOLUTION_API_URL).strip().rstrip("/")
        evo_key = os.getenv("EVOLUTION_API_KEY", EVOLUTION_API_KEY).strip()

        logging.info(f"[APROVACAO] tel_limpo='{tel_limpo}' | evo_url='{evo_url}' | has_key={bool(evo_key)}")

        # Se tiver Evolution API configurada e telefone válido, tenta enviar automaticamente via WhatsApp
        if tel_limpo and len(tel_limpo) >= 10 and evo_key:
            num_wa = tel_limpo if tel_limpo.startswith("55") else f"55{tel_limpo}"
            msg_wa = (
                f"Olá *{nome_aprovador}*!\n\n"
                f"O técnico *{tecnico}* (OS Nº *{task_num}*) solicita sua confirmação/preenchimento externo.\n\n"
                f"*Motivo:* {motivo}\n\n"
                f"Acesse o link seguro para responder agora:\n{url_responder}"
            )
            try:
                resp_wa = requests.post(
                    f"{evo_url}/send/text",
                    headers={"apikey": evo_key, "Content-Type": "application/json"},
                    json={"number": num_wa, "text": msg_wa, "linkPreview": False},
                    timeout=10
                )
                logging.info(f"[APROVACAO] Evolution Go envio para {num_wa}: HTTP {resp_wa.status_code} - {resp_wa.text}")
            except Exception as ex:
                logging.warning(f"[APROVACAO] Falha ao enviar WhatsApp automático (Evolution): {ex}")
        else:
            logging.warning(f"[APROVACAO] Envio WhatsApp ignorado! tel_limpo='{tel_limpo}', has_key={bool(evo_key)}")

        # Retorna Action=OpenUrl conforme Página 167 e 171 do manual OfficeTrack
        response = etree.Element("Response")
        ret = etree.SubElement(response, "ReturnValue")
        etree.SubElement(ret, "ShortText").text = "Aguardando"
        etree.SubElement(ret, "LongText").text = f"Sessão {tx_id}"
        etree.SubElement(ret, "Value").text = "OK"
        etree.SubElement(ret, "Action").text = "OpenUrl"
        etree.SubElement(ret, "Url").text = url_espera
        etree.SubElement(ret, "WebService").text = url_webservice_retorno

        xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode("utf-8")
        logging.debug(f"OpenUrl gerado para tx_id={tx_id}: {xml_str}")
        return Response(xml_str, content_type="application/xml; charset=utf-8")

    except Exception as e:
        logging.error(f"Erro em iniciar_aprovacao_externa: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao iniciar aprovação externa: {str(e)}")


def sala_espera(tx_id):
    """
    Tela aberta DENTRO do app OfficeTrack via OpenUrl.
    Exibe o link para compartilhar caso necessário e faz polling em tempo real
    até a pessoa externa responder.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM transacoes WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return "<h3>Transação não encontrada.</h3>", 404

    base_url = _obter_base_url()
    url_responder = f"{base_url}/responder/{tx_id}"

    # Monta link wa.me para o técnico poder compartilhar com 1 toque pelo próprio celular caso não use API automática
    texto_wa = f"Olá {row['nome_aprovador']}! Por favor, confirme a solicitação da OS {row['task_num']} neste link: {url_responder}"
    import urllib.parse
    tel = row["tel_aprovador"]
    if tel:
        num_wa = tel if tel.startswith("55") else f"55{tel}"
        wa_link = f"https://wa.me/{num_wa}?text={urllib.parse.quote(texto_wa)}"
    else:
        wa_link = f"https://wa.me/?text={urllib.parse.quote(texto_wa)}"

    html = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sala de Espera - {{ tx_id }}</title>
        <style>
            * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            body { margin: 0; padding: 20px; background: #f0f4f8; color: #1e293b; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .card { background: white; border-radius: 16px; padding: 24px; max-width: 440px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.08); text-align: center; }
            .badge { display: inline-block; background: #e0f2fe; color: #0369a1; font-weight: 700; padding: 4px 12px; border-radius: 999px; font-size: 12px; margin-bottom: 12px; }
            h2 { margin: 0 0 8px 0; font-size: 20px; }
            p { color: #64748b; font-size: 14px; line-height: 1.5; }
            .spinner { width: 48px; height: 48px; border: 5px solid #e2e8f0; border-top-color: #0284c7; border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto; }
            @keyframes spin { to { transform: rotate(360deg); } }
            .box-link { background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 10px; padding: 12px; margin: 16px 0; word-break: break-all; font-size: 12px; color: #334155; }
            .btn { display: block; width: 100%; padding: 14px; border-radius: 10px; border: none; font-weight: 700; font-size: 15px; cursor: pointer; text-decoration: none; margin-top: 10px; }
            .btn-wa { background: #25D366; color: white; }
            .btn-copy { background: #0f172a; color: white; }
            .success-box { display: none; background: #ecfdf5; border: 2px solid #10b981; border-radius: 12px; padding: 18px; margin-top: 16px; }
            .success-box h3 { color: #047857; margin: 0 0 8px 0; }
            .obs-result { background: white; padding: 10px; border-radius: 8px; text-align: left; font-size: 13px; margin-top: 10px; border: 1px solid #a7f3d0; }
            .alert-close { background: #047857; color: white; padding: 12px; border-radius: 8px; font-weight: bold; margin-top: 14px; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">PROTOCOLO #{{ tx_id }}</span>
            
            <div id="waiting-section">
                <div class="spinner"></div>
                <h2>Aguardando Resposta Externa</h2>
                <p>Aguardando <strong>{{ nome_aprovador }}</strong> abrir o link e confirmar os dados (OS {{ task_num }}).</p>
                
                <div class="box-link" id="link-texto">{{ url_responder }}</div>
                
                <a href="{{ wa_link }}" target="_blank" class="btn btn-wa">📲 Enviar Link via WhatsApp</a>
                <button onclick="copiarLink()" class="btn btn-copy" id="btn-copy">📋 Copiar Link de Aprovação</button>
            </div>

            <div id="success-section" class="success-box">
                <div style="font-size: 40px;">✅</div>
                <h3>Resposta Recebida!</h3>
                <p style="color:#065f46; margin: 4px 0;"><strong>Decisão:</strong> <span id="res-decisao"></span></p>
                <p style="color:#065f46; margin: 4px 0;"><strong>Respondido por:</strong> <span id="res-nome"></span></p>
                <div class="obs-result">
                    <strong>Observação:</strong><br>
                    <span id="res-obs"></span>
                </div>
                <div class="alert-close">
                    Agora toque no botão FECHAR (X) ou VOLTAR desta janela para importar os dados para o formulário!
                </div>
            </div>
        </div>

        <script>
            function copiarLink() {
                const texto = document.getElementById("link-texto").innerText;
                navigator.clipboard.writeText(texto).then(() => {
                    document.getElementById("btn-copy").innerText = "✔ Link Copiado!";
                    setTimeout(() => { document.getElementById("btn-copy").innerText = "📋 Copiar Link de Aprovação"; }, 2500);
                });
            }

            async function checarStatus() {
                try {
                    const resp = await fetch("/api/status_aprovacao/{{ tx_id }}");
                    const data = await resp.json();
                    if (data.status === "RESPONDIDO") {
                        document.getElementById("waiting-section").style.display = "none";
                        document.getElementById("success-section").style.display = "block";
                        document.getElementById("res-decisao").innerText = data.decisao;
                        document.getElementById("res-nome").innerText = data.nome_respondente;
                        document.getElementById("res-obs").innerText = data.observacao || "Sem observações.";
                        return; // para o polling
                    }
                } catch (e) { console.error(e); }
                setTimeout(checarStatus, 2000);
            }
            setTimeout(checarStatus, 1500);
        </script>
    </body>
    </html>
    """
    return render_template_string(
        html,
        tx_id=tx_id,
        nome_aprovador=row["nome_aprovador"],
        task_num=row["task_num"],
        url_responder=url_responder,
        wa_link=wa_link
    )


def responder_externo(tx_id):
    """
    Página Web Pública que a pessoa remota (Cliente/Supervisor) abre pelo WhatsApp.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM transacoes WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return "<h3>Link inválido ou expirado.</h3>", 404

    if request.method == "POST":
        decisao = request.form.get("decisao", "APROVADO")
        nome_resp = request.form.get("nome_respondente", "").strip() or row["nome_aprovador"]
        obs = request.form.get("observacao", "").strip()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """UPDATE transacoes 
                   SET status = 'RESPONDIDO', decisao = ?, nome_respondente = ?, observacao = ?, respondido_em = ?
                   WHERE tx_id = ?""",
                (decisao, nome_resp, obs, agora, tx_id)
            )
            conn.commit()

        html_ok = """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Confirmação Registrada</title>
            <style>
                body { font-family: -apple-system, sans-serif; background: #ecfdf5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; padding: 20px; }
                .card { background: white; padding: 32px; border-radius: 16px; max-width: 400px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.08); }
                h2 { color: #047857; margin: 12px 0 8px 0; }
                p { color: #475569; font-size: 14px; line-height: 1.5; }
            </style>
        </head>
        <body>
            <div class="card">
                <div style="font-size: 54px;">✅</div>
                <h2>Resposta Confirmada!</h2>
                <p>Sua decisão (<strong>{{ decisao }}</strong>) foi enviada em tempo real para o aplicativo do técnico em campo.</p>
                <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">Protocolo #{{ tx_id }} - Já pode fechar esta aba.</p>
            </div>
        </body>
        </html>
        """
        return render_template_string(html_ok, decisao=decisao, tx_id=tx_id)

    html_form = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Aprovação Externa - OS {{ task_num }}</title>
        <style>
            * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            body { margin: 0; padding: 20px; background: #f1f5f9; color: #1e293b; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .card { background: white; border-radius: 16px; padding: 24px; max-width: 450px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.08); }
            .header { border-bottom: 1px solid #e2e8f0; padding-bottom: 14px; margin-bottom: 16px; }
            .badge { background: #dbeafe; color: #1d4ed8; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 999px; }
            h2 { margin: 8px 0 4px 0; font-size: 20px; }
            .info-box { background: #f8fafc; padding: 12px; border-radius: 10px; font-size: 13px; margin-bottom: 18px; border-left: 4px solid #0284c7; }
            label { display: block; font-weight: 600; font-size: 13px; margin-bottom: 6px; margin-top: 14px; color: #334155; }
            input, select, textarea { width: 100%; padding: 12px; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 15px; outline: none; }
            input:focus, select:focus, textarea:focus { border-color: #0284c7; }
            .btn-submit { width: 100%; background: #0284c7; color: white; border: none; padding: 15px; border-radius: 10px; font-size: 16px; font-weight: 700; margin-top: 20px; cursor: pointer; }
            .btn-submit:hover { background: #0369a1; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <span class="badge">SOLICITAÇÃO EM CAMPO #{{ tx_id }}</span>
                <h2>Confirmação Externa</h2>
            </div>

            <div class="info-box">
                <strong>OS Nº:</strong> {{ task_num }}<br>
                <strong>Técnico Solicitante:</strong> {{ tecnico }}<br>
                <strong>Motivo:</strong> {{ motivo }}
            </div>

            <form method="POST">
                <label>Seu Nome Completo *</label>
                <input type="text" name="nome_respondente" value="{{ nome_aprovador }}" required>

                <label>Decisão / Parecer *</label>
                <select name="decisao" required>
                    <option value="APROVADO">✅ APROVADO / AUTORIZADO</option>
                    <option value="REPROVADO">❌ REPROVADO / NÃO AUTORIZADO</option>
                </select>

                <label>Observações ou Instruções ao Técnico</label>
                <textarea name="observacao" rows="3" placeholder="Digite aqui detalhes, código de autorização ou observações..."></textarea>

                <button type="submit" class="btn-submit">Confirmar e Enviar para o App</button>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(
        html_form,
        tx_id=tx_id,
        task_num=row["task_num"],
        tecnico=row["tecnico"],
        motivo=row["motivo"],
        nome_aprovador=row["nome_aprovador"]
    )


def status_aprovacao_api(tx_id):
    """API JSON consumida pelo JavaScript da Sala de Espera"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM transacoes WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return jsonify({"error": "Not found"}), 404

    return jsonify({
        "tx_id": row["tx_id"],
        "status": row["status"],
        "decisao": row["decisao"],
        "nome_respondente": row["nome_respondente"],
        "observacao": row["observacao"],
        "respondido_em": row["respondido_em"]
    })


def finalizar_aprovacao(tx_id):
    """
    2º Passo Automático (Chamado pelo OfficeTrack quando o técnico fecha a tela OpenUrl).
    Lê a resposta salva pelo usuário externo e preenche os campos no formulário do app!
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM transacoes WHERE tx_id = ?", (tx_id,)).fetchone()

        if not row:
            return _resposta_v2_erro(f"Sessão {tx_id} não encontrada.")

        if row["status"] != "RESPONDIDO":
            # Técnico fechou a tela antes da pessoa externa responder
            campos = {
                "TXID_EXTERNO": tx_id,
                "STATUS_EXTERNO": "AGUARDANDO RESPOSTA"
            }
            return _resposta_v2_sucesso(
                sucesso=False,
                mensagem=f"A pessoa ainda não concluiu o preenchimento do link!\n\nProtocolo: {tx_id}\nQuando ela confirmar, você pode consultar novamente usando este protocolo.",
                short_text="Pendente",
                long_text="Aguardando resposta externa. Toque na lixeira para tentar de novo",
                campos=campos
            )

        decisao = row["decisao"]
        nome_resp = row["nome_respondente"]
        obs = row["observacao"] or "Sem observações."
        data_resp = row["respondido_em"]

        campos = {
            "TXID_EXTERNO": tx_id,
            "STATUS_EXTERNO": decisao,
            "NOME_APROVADOR_EXT": nome_resp,
            "OBS_EXTERNA": obs,
            "DATA_HORA_EXT": data_resp
        }

        sucesso = (decisao == "APROVADO")
        msg_popup = (
            f"Retorno Externo Recebido!\n\n"
            f"Decisão: {decisao}\n"
            f"Por: {nome_resp}\n"
            f"Obs: {obs}\n"
            f"Horário: {data_resp}"
        )

        return _resposta_v2_sucesso(
            sucesso=sucesso,
            mensagem=msg_popup,
            short_text=decisao,
            long_text="" if sucesso else "Solicitação reprovada externamente",
            campos=campos
        )

    except Exception as e:
        logging.error(f"Erro em finalizar_aprovacao: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao finalizar aprovação: {str(e)}")


def consultar_aprovacao_manual():
    """
    Endpoint de fallback: caso o técnico tenha fechado a sala de espera antes da pessoa responder,
    ele pode consultar depois passando o TXID_EXTERNO do formulário.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("XML não encontrado.")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        tx_node = root.xpath(".//Field[Id='TXID_EXTERNO' or ID='TXID_EXTERNO']/Value")
        tx_id = tx_node[0].text.strip().upper() if tx_node and tx_node[0].text else ""

        if not tx_id:
            return _resposta_v2_erro("Campo TXID_EXTERNO não encontrado ou vazio no formulário.")

        return finalizar_aprovacao(tx_id)

    except Exception as e:
        return _resposta_v2_erro(str(e))


def _resposta_v2_sucesso(sucesso, mensagem, short_text, long_text="", campos=None):
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


def _resposta_v2_erro(mensagem):
    return _resposta_v2_sucesso(
        sucesso=False,
        mensagem=mensagem,
        short_text="Erro",
        long_text="Toque na lixeira para tentar novamente"
    )

