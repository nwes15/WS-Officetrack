from flask import request, Response, jsonify, render_template_string
from lxml import etree
import logging
import sqlite3
import uuid
import os
import re
import base64
import hashlib
import urllib.parse
import requests
from datetime import datetime
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "assinaturas_remotas.db")

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:18080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assinaturas (
                tx_id TEXT PRIMARY KEY,
                task_num TEXT,
                tecnico TEXT,
                nome_cliente TEXT,
                tel_cliente TEXT,
                resumo_servico TEXT,
                status TEXT DEFAULT 'AGUARDANDO',
                assinante_nome TEXT DEFAULT '',
                assinante_doc TEXT DEFAULT '',
                imagem_base64 TEXT DEFAULT '',
                ip_assinante TEXT DEFAULT '',
                hash_validacao TEXT DEFAULT '',
                criado_em TEXT,
                assinado_em TEXT DEFAULT ''
            )
        """)
        conn.commit()
    try:
        os.chmod(DB_PATH, 0o666)
    except Exception:
        pass


_init_db()


def _obter_base_url():
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    if "trycloudflare" in host or "onrender.com" in host or (
        "127.0.0.1" not in host and "localhost" not in host and not host.startswith("192.168.")
    ):
        if not request.headers.get("X-Forwarded-Proto"):
            proto = "https"
    return f"{proto}://{host}"


def iniciar_assinatura_remota():
    """
    1º Passo (Botão no OfficeTrack):
    Cria uma sessão de assinatura remota, envia o link via WhatsApp (se Evolution conectada)
    e retorna <Action>OpenUrl</Action> abrindo a Sala de Espera com prévia da assinatura em tempo real.
    Ao fechar a janela, o OfficeTrack chama /finalizar_assinatura/<tx_id> e preenche o LINK_ASSINATURA (.png direto)
    para o Report Designer!
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

        nome_node = root.xpath(".//Field[Id='NOME_CLIENTE' or ID='NOME_CLIENTE' or Id='NOME_APROVADOR' or ID='NOME_APROVADOR']/Value")
        nome_cliente = nome_node[0].text.strip() if nome_node and nome_node[0].text else "Cliente"

        tel_node = root.xpath(".//Field[Id='TEL_CLIENTE' or ID='TEL_CLIENTE' or Id='TEL_APROVADOR' or ID='TELEFONE']/Value")
        tel_bruto = tel_node[0].text.strip() if tel_node and tel_node[0].text else ""
        tel_limpo = re.sub(r"\D", "", tel_bruto)

        resumo_node = root.xpath(".//Field[Id='RESUMO_SERVICO' or ID='RESUMO_SERVICO' or Id='OBS_TECNICA' or ID='OBS' or Id='MOTIVO_SOLICITACAO']/Value")
        resumo = resumo_node[0].text.strip() if resumo_node and resumo_node[0].text else "Confirmação de execução dos serviços técnicos."

        tx_id = str(uuid.uuid4())[:8].upper()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO assinaturas (tx_id, task_num, tecnico, nome_cliente, tel_cliente, resumo_servico, status, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?, 'AGUARDANDO', ?)""",
                (tx_id, task_num, tecnico, nome_cliente, tel_limpo, resumo, agora)
            )
            conn.commit()

        base_url = _obter_base_url()
        url_assinar = f"{base_url}/assinar/{tx_id}"
        url_espera = f"{base_url}/espera_assinatura/{tx_id}"
        url_retorno = f"{base_url}/finalizar_assinatura/{tx_id}"

        # Tenta disparo automático pelo Evolution Go se configurado
        if tel_limpo and len(tel_limpo) >= 10 and EVOLUTION_API_KEY:
            num_wa = tel_limpo if tel_limpo.startswith("55") else f"55{tel_limpo}"
            msg_wa = (
                f"Olá *{nome_cliente}*!\n\n"
                f"O atendimento técnico da *OS Nº {task_num}* foi concluído por *{tecnico}*.\n\n"
                f"*Resumo:* {resumo}\n\n"
                f"Por favor, revise e assine digitalmente no link seguro abaixo:\n{url_assinar}"
            )
            try:
                requests.post(
                    f"{EVOLUTION_API_URL}/send/text",
                    headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"},
                    json={"number": num_wa, "text": msg_wa, "linkPreview": False},
                    timeout=5
                )
            except Exception as ex:
                logging.warning(f"Falha ao enviar link de assinatura via Evolution: {ex}")

        response = etree.Element("Response")
        ret = etree.SubElement(response, "ReturnValue")
        etree.SubElement(ret, "ShortText").text = "Aguardando Assinatura"
        etree.SubElement(ret, "LongText").text = f"Sessão {tx_id}"
        etree.SubElement(ret, "Value").text = "OK"
        etree.SubElement(ret, "Action").text = "OpenUrl"
        etree.SubElement(ret, "Url").text = url_espera
        etree.SubElement(ret, "WebService").text = url_retorno

        xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return Response(xml_str, content_type="application/xml; charset=utf-8")

    except Exception as e:
        logging.error(f"Erro em iniciar_assinatura_remota: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao iniciar assinatura: {str(e)}")


def sala_espera_assinatura(tx_id):
    """
    Tela aberta DENTRO do OfficeTrack via OpenUrl.
    Exibe o link para compartilhar e mostra a imagem da assinatura AO VIVO assim que o cliente assinar!
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assinaturas WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return "<h3>Sessão de assinatura não encontrada.</h3>", 404

    base_url = _obter_base_url()
    url_assinar = f"{base_url}/assinar/{tx_id}"

    texto_wa = f"Olá {row['nome_cliente']}! Por favor, revise e assine a OS {row['task_num']} neste link: {url_assinar}"
    tel = row["tel_cliente"]
    if tel:
        num_wa = tel if tel.startswith("55") else f"55{tel}"
        wa_link = f"https://wa.me/{num_wa}?text={urllib.parse.quote(texto_wa)}"
    else:
        wa_link = f"https://wa.me/?text={urllib.parse.quote(texto_wa)}"

    html = r"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Aguardando Assinatura - {{ tx_id }}</title>
        <style>
            * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            body { margin: 0; padding: 20px; background: #f0f4f8; color: #1e293b; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .card { background: white; border-radius: 16px; padding: 24px; max-width: 440px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.08); text-align: center; }
            .badge { display: inline-block; background: #e0f2fe; color: #0369a1; font-weight: 700; padding: 4px 12px; border-radius: 999px; font-size: 12px; margin-bottom: 12px; }
            h2 { margin: 0 0 8px 0; font-size: 20px; }
            p { color: #64748b; font-size: 14px; line-height: 1.5; }
            .spinner { width: 44px; height: 44px; border: 5px solid #e2e8f0; border-top-color: #0284c7; border-radius: 50%; animation: spin 1s linear infinite; margin: 18px auto; }
            @keyframes spin { to { transform: rotate(360deg); } }
            .box-link { background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 10px; padding: 12px; margin: 14px 0; word-break: break-all; font-size: 12px; color: #334155; }
            .btn { display: block; width: 100%; padding: 14px; border-radius: 10px; border: none; font-weight: 700; font-size: 15px; cursor: pointer; text-decoration: none; margin-top: 10px; }
            .btn-wa { background: #25D366; color: white; }
            .btn-copy { background: #0f172a; color: white; }
            .success-box { display: none; background: #ecfdf5; border: 2px solid #10b981; border-radius: 12px; padding: 16px; margin-top: 14px; }
            .success-box h3 { color: #047857; margin: 6px 0; }
            .sig-preview { background: white; border: 1px solid #a7f3d0; border-radius: 8px; padding: 8px; margin: 12px 0; }
            .sig-preview img { max-width: 100%; max-height: 140px; display: block; margin: 0 auto; }
            .alert-close { background: #047857; color: white; padding: 12px; border-radius: 8px; font-weight: bold; margin-top: 12px; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">ASSINATURA DIGITAL #{{ tx_id }}</span>

            <div id="waiting-section">
                <div class="spinner"></div>
                <h2>Aguardando Assinatura do Cliente</h2>
                <p>Envie o link abaixo para <strong>{{ nome_cliente }}</strong> revisar e assinar a OS {{ task_num }}.</p>

                <div class="box-link" id="link-texto">{{ url_assinar }}</div>

                <a href="{{ wa_link }}" target="_blank" class="btn btn-wa">📲 Enviar Link via WhatsApp</a>
                <button type="button" onclick="copiarLink()" class="btn btn-copy" id="btn-copy">📋 Copiar Link de Assinatura</button>
            </div>

            <div id="success-section" class="success-box">
                <div style="font-size: 36px;">✍️✅</div>
                <h3>Assinatura Recebida!</h3>
                <p style="color:#065f46; margin: 4px 0;"><strong>Assinante:</strong> <span id="res-nome"></span></p>
                <p style="color:#065f46; margin: 4px 0; font-size:12px;"><strong>Doc:</strong> <span id="res-doc"></span></p>
                <div class="sig-preview">
                    <img id="res-img" src="" alt="Assinatura">
                </div>
                <div class="alert-close">
                    Tudo certo! Agora toque em FECHAR (X) ou VOLTAR para gravar o link da assinatura no formulário!
                </div>
            </div>
        </div>

        <script>
            function copiarLink() {
                const texto = document.getElementById("link-texto").innerText;
                navigator.clipboard.writeText(texto).then(() => {
                    document.getElementById("btn-copy").innerText = "✔ Link Copiado!";
                    setTimeout(() => { document.getElementById("btn-copy").innerText = "📋 Copiar Link de Assinatura"; }, 2500);
                });
            }

            async function checarStatus() {
                try {
                    const resp = await fetch("/api/status_assinatura/{{ tx_id }}");
                    const data = await resp.json();
                    if (data.status === "ASSINADO") {
                        document.getElementById("waiting-section").style.display = "none";
                        document.getElementById("success-section").style.display = "block";
                        document.getElementById("res-nome").innerText = data.assinante_nome;
                        document.getElementById("res-doc").innerText = data.assinante_doc || "Não informado";
                        document.getElementById("res-img").src = "/assinatura_img/{{ tx_id }}.png?t=" + Date.now();
                        return;
                    }
                } catch (e) {}
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
        nome_cliente=row["nome_cliente"],
        task_num=row["task_num"],
        url_assinar=url_assinar,
        wa_link=wa_link
    )


def tela_assinar_externo(tx_id):
    """
    Página Pública com Canvas de Assinatura para o cliente revisar o atendimento e assinar com o dedo.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assinaturas WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return "<h3>Link de assinatura inválido ou expirado.</h3>", 404

    if request.method == "POST":
        assinante_nome = request.form.get("assinante_nome", "").strip() or row["nome_cliente"]
        assinante_doc = request.form.get("assinante_doc", "").strip()
        img_data_url = request.form.get("assinatura_b64", "").strip()

        if not img_data_url or "base64," not in img_data_url:
            return "<h3>Erro: Assinatura não desenhada. Volte e assine no quadro.</h3>", 400

        b64_puro = img_data_url.split("base64,", 1)[1]
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        ip_cliente = request.headers.get("X-Forwarded-For", request.remote_addr or "0.0.0.0").split(",")[0].strip()

        hash_raw = f"{tx_id}|{assinante_nome}|{assinante_doc}|{agora}|{ip_cliente}|{b64_puro[:50]}"
        hash_validacao = hashlib.sha256(hash_raw.encode("utf-8")).hexdigest()[:16].upper()

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """UPDATE assinaturas
                   SET status = 'ASSINADO', assinante_nome = ?, assinante_doc = ?,
                       imagem_base64 = ?, ip_assinante = ?, hash_validacao = ?, assinado_em = ?
                   WHERE tx_id = ?""",
                (assinante_nome, assinante_doc, b64_puro, ip_cliente, hash_validacao, agora, tx_id)
            )
            conn.commit()

        html_ok = r"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Assinatura Confirmada</title>
            <style>
                body { font-family: -apple-system, sans-serif; background: #ecfdf5; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
                .card { background: white; padding: 28px; border-radius: 16px; max-width: 420px; width: 100%; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.08); }
                h2 { color: #047857; margin: 10px 0 8px 0; }
                p { color: #475569; font-size: 14px; line-height: 1.5; }
                .sig-box { border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px; margin: 16px 0; background: #f8fafc; }
                .sig-box img { max-width: 100%; max-height: 130px; }
                .hash { font-family: monospace; font-size: 11px; color: #64748b; background: #f1f5f9; padding: 8px; border-radius: 6px; }
            </style>
        </head>
        <body>
            <div class="card">
                <div style="font-size: 48px;">✅</div>
                <h2>Assinatura Registrada!</h2>
                <p>Obrigado, <strong>{{ assinante_nome }}</strong>. Sua assinatura foi validada e enviada para o relatório da OS {{ task_num }}.</p>
                <div class="sig-box">
                    <img src="/assinatura_img/{{ tx_id }}.png" alt="Sua assinatura">
                </div>
                <div class="hash">
                    Protocolo: #{{ tx_id }}<br>
                    Autenticação: {{ hash_validacao }}<br>
                    Data/Hora: {{ agora }}
                </div>
            </div>
        </body>
        </html>
        """
        return render_template_string(
            html_ok,
            assinante_nome=assinante_nome,
            task_num=row["task_num"],
            tx_id=tx_id,
            hash_validacao=hash_validacao,
            agora=agora
        )

    html_form = r"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Revisar e Assinar - OS {{ task_num }}</title>
        <style>
            * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            body { margin: 0; padding: 16px; background: #f1f5f9; color: #1e293b; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .card { background: white; border-radius: 16px; padding: 22px; max-width: 480px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.08); }
            .badge { background: #dbeafe; color: #1d4ed8; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 999px; }
            h2 { margin: 8px 0 12px 0; font-size: 20px; }
            .info-box { background: #f8fafc; padding: 12px; border-radius: 10px; font-size: 13px; margin-bottom: 14px; border-left: 4px solid #0284c7; line-height: 1.5; }
            label { display: block; font-weight: 600; font-size: 13px; margin-bottom: 5px; margin-top: 12px; color: #334155; }
            input { width: 100%; padding: 11px 12px; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 15px; outline: none; }
            input:focus { border-color: #0284c7; }
            .canvas-wrapper { position: relative; border: 2px dashed #94a3b8; border-radius: 12px; background: #ffffff; margin-top: 6px; touch-action: none; overflow: hidden; }
            canvas { display: block; width: 100%; height: 200px; cursor: crosshair; }
            .canvas-guide { position: absolute; bottom: 38px; left: 20px; right: 20px; border-bottom: 1px solid #cbd5e1; pointer-events: none; }
            .canvas-hint { position: absolute; bottom: 14px; width: 100%; text-align: center; font-size: 11px; color: #94a3b8; pointer-events: none; }
            .actions-row { display: flex; gap: 10px; margin-top: 14px; }
            .btn-clear { flex: 1; background: #e2e8f0; color: #334155; border: none; padding: 13px; border-radius: 10px; font-weight: 700; font-size: 14px; cursor: pointer; }
            .btn-submit { flex: 2; background: #0284c7; color: white; border: none; padding: 13px; border-radius: 10px; font-weight: 700; font-size: 15px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">PROTOCOLO #{{ tx_id }}</span>
            <h2>Revisão e Assinatura Digital</h2>

            <div class="info-box">
                <strong>OS Nº:</strong> {{ task_num }}<br>
                <strong>Técnico:</strong> {{ tecnico }}<br>
                <strong>Resumo do Serviço:</strong> {{ resumo_servico }}
            </div>

            <form method="POST" id="form-assinatura" onsubmit="return prepararEnvio()">
                <label>Nome Completo do Responsável *</label>
                <input type="text" name="assinante_nome" value="{{ nome_cliente }}" required>

                <label>CPF ou Documento (Opcional)</label>
                <input type="text" name="assinante_doc" placeholder="Ex: 123.456.789-00">

                <label>Assine no quadro abaixo com o dedo *</label>
                <div class="canvas-wrapper">
                    <canvas id="sig-canvas"></canvas>
                    <div class="canvas-guide"></div>
                    <div class="canvas-hint">Assine acima desta linha</div>
                </div>

                <input type="hidden" name="assinatura_b64" id="assinatura_b64">

                <div class="actions-row">
                    <button type="button" class="btn-clear" onclick="limparCanvas()">🗑️ Limpar</button>
                    <button type="submit" class="btn-submit">✅ Confirmar Assinatura</button>
                </div>
            </form>
        </div>

        <script>
            const canvas = document.getElementById("sig-canvas");
            const ctx = canvas.getContext("2d");
            let desenhando = false;
            let temTraco = false;

            function ajustarTamanho() {
                const ratio = Math.max(window.devicePixelRatio || 1, 1);
                const rect = canvas.getBoundingClientRect();
                canvas.width = rect.width * ratio;
                canvas.height = rect.height * ratio;
                ctx.scale(ratio, ratio);
                // Preenche fundo branco sólido para ficar perfeito no PDF do Report Designer
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, rect.width, rect.height);
                ctx.strokeStyle = "#0f172a";
                ctx.lineWidth = 2.8;
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
            }

            ajustarTamanho();

            function getPos(e) {
                const rect = canvas.getBoundingClientRect();
                const clientX = e.touches ? e.touches[0].clientX : e.clientX;
                const clientY = e.touches ? e.touches[0].clientY : e.clientY;
                return { x: clientX - rect.left, y: clientY - rect.top };
            }

            function iniciar(e) {
                desenhando = true;
                temTraco = true;
                const pos = getPos(e);
                ctx.beginPath();
                ctx.moveTo(pos.x, pos.y);
            }

            function mover(e) {
                if (!desenhando) return;
                e.preventDefault();
                const pos = getPos(e);
                ctx.lineTo(pos.x, pos.y);
                ctx.stroke();
            }

            function parar() { desenhando = false; }

            canvas.addEventListener("mousedown", iniciar);
            canvas.addEventListener("mousemove", mover);
            window.addEventListener("mouseup", parar);

            canvas.addEventListener("touchstart", iniciar, { passive: false });
            canvas.addEventListener("touchmove", mover, { passive: false });
            canvas.addEventListener("touchend", parar);

            function limparCanvas() {
                const rect = canvas.getBoundingClientRect();
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, rect.width, rect.height);
                temTraco = false;
            }

            function prepararEnvio() {
                if (!temTraco) {
                    alert("Por favor, desenhe sua assinatura no quadro antes de confirmar.");
                    return false;
                }
                document.getElementById("assinatura_b64").value = canvas.toDataURL("image/png");
                return true;
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(
        html_form,
        tx_id=tx_id,
        task_num=row["task_num"],
        tecnico=row["tecnico"],
        resumo_servico=row["resumo_servico"],
        nome_cliente=row["nome_cliente"]
    )


def servir_imagem_assinatura(tx_id):
    """
    URL DIRETA DA IMAGEM PNG para ser usada no campo de Imagem do Report Designer do OfficeTrack!
    Ex: https://seu-dominio/assinatura_img/C17D8C4A.png
    """
    tx_id_limpo = tx_id.replace(".png", "").strip().upper()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT imagem_base64 FROM assinaturas WHERE tx_id = ?", (tx_id_limpo,)).fetchone()

    if not row or not row["imagem_base64"]:
        return "Imagem não encontrada", 404

    img_bytes = base64.b64decode(row["imagem_base64"])
    return Response(img_bytes, content_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


def ver_comprovante_assinatura(tx_id):
    """Página web com a auditoria completa (assinatura + nome + documento + IP + SHA256)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assinaturas WHERE tx_id = ?", (tx_id.upper(),)).fetchone()

    if not row or row["status"] != "ASSINADO":
        return "<h3>Assinatura ainda não realizada ou não encontrada.</h3>", 404

    html = r"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Comprovante de Assinatura #{{ row.tx_id }}</title>
        <style>
            body { font-family: -apple-system, sans-serif; background: #f8fafc; padding: 20px; display: flex; justify-content: center; }
            .card { background: white; border: 1px solid #cbd5e1; border-radius: 12px; padding: 24px; max-width: 520px; width: 100%; }
            h2 { margin-top: 0; color: #0f172a; border-bottom: 2px solid #0284c7; padding-bottom: 10px; }
            .sig-box { border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; margin: 16px 0; text-align: center; }
            .sig-box img { max-width: 100%; max-height: 180px; }
            .meta { font-size: 13px; color: #334155; line-height: 1.7; background: #f1f5f9; padding: 14px; border-radius: 8px; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Comprovante de Assinatura Digital</h2>
            <div class="sig-box">
                <img src="/assinatura_img/{{ row.tx_id }}.png" alt="Assinatura Digital">
            </div>
            <div class="meta">
                <strong>Protocolo:</strong> #{{ row.tx_id }}<br>
                <strong>OS Nº:</strong> {{ row.task_num }} | <strong>Técnico:</strong> {{ row.tecnico }}<br>
                <strong>Assinante:</strong> {{ row.assinante_nome }}<br>
                <strong>Documento:</strong> {{ row.assinante_doc or 'Não informado' }}<br>
                <strong>Data/Hora:</strong> {{ row.assinado_em }}<br>
                <strong>IP de Origem:</strong> {{ row.ip_assinante }}<br>
                <strong>Hash SHA-256:</strong> <code>{{ row.hash_validacao }}</code>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, row=row)


def status_assinatura_api(tx_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT tx_id, status, assinante_nome, assinante_doc, assinado_em FROM assinaturas WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


def finalizar_assinatura(tx_id):
    """
    2º Passo Automático (Chamado pelo OfficeTrack quando o técnico fecha a Sala de Espera).
    Devolve o link direto da imagem PNG (LINK_ASSINATURA) para o Report Designer imprimir no relatório!
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM assinaturas WHERE tx_id = ?", (tx_id.upper(),)).fetchone()

        if not row:
            return _resposta_v2_erro(f"Sessão {tx_id} não encontrada.")

        if row["status"] != "ASSINADO":
            campos = {
                "TXID_ASSINATURA": tx_id,
                "STATUS_ASSINATURA": "AGUARDANDO ASSINATURA"
            }
            return _resposta_v2_sucesso(
                sucesso=False,
                mensagem=f"O cliente ainda não concluiu a assinatura!\n\nProtocolo: {tx_id}\nQuando ele assinar, use o botão de consulta com este protocolo.",
                short_text="Pendente",
                long_text="Aguardando assinatura. Toque na lixeira para tentar de novo",
                campos=campos
            )

        base_url = _obter_base_url()
        link_direto_png = f"{base_url}/assinatura_img/{tx_id}.png"
        link_comprovante = f"{base_url}/ver_assinatura/{tx_id}"

        campos = {
            "TXID_ASSINATURA": tx_id,
            "STATUS_ASSINATURA": "ASSINADO DIGITALMENTE",
            "ASSINANTE_NOME": row["assinante_nome"],
            "ASSINANTE_DOC": row["assinante_doc"] or "Não informado",
            "LINK_ASSINATURA": link_direto_png,
            "LINK_COMPROVANTE": link_comprovante,
            "HASH_AUDITORIA": f"{row['hash_validacao']} ({row['assinado_em']} • IP {row['ip_assinante']})"
        }

        msg_popup = (
            f"Assinatura Digital Importada!\n\n"
            f"Assinante: {row['assinante_nome']}\n"
            f"Horário: {row['assinado_em']}\n"
            f"Link da imagem salvo em LINK_ASSINATURA para o seu Report Designer!"
        )

        return _resposta_v2_sucesso(
            sucesso=True,
            mensagem=msg_popup,
            short_text="Assinado",
            campos=campos
        )

    except Exception as e:
        logging.error(f"Erro em finalizar_assinatura: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao finalizar assinatura: {str(e)}")


def consultar_assinatura_manual():
    """Plano B: caso tenha fechado a janela antes do cliente assinar, busca pelo TXID_ASSINATURA."""
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("XML não encontrado.")

        parser = etree.XMLParser(recover=True)
        tree = etree.parse(StringIO(xml_data), parser)
        root = tree.getroot()

        tx_node = root.xpath(".//Field[Id='TXID_ASSINATURA' or ID='TXID_ASSINATURA']/Value")
        tx_id = tx_node[0].text.strip().upper() if tx_node and tx_node[0].text else ""

        if not tx_id:
            return _resposta_v2_erro("Campo TXID_ASSINATURA não encontrado ou vazio.")

        return finalizar_assinatura(tx_id)
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

