from flask import request, Response, jsonify, render_template_string, stream_with_context
from lxml import etree
import logging
import sqlite3
import uuid
import os
import json
import requests
from datetime import datetime
from io import StringIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chat_ia.db")

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def _get_openai_config():
    """Lê dinamicamente das variáveis de ambiente (Render / Docker / .env)."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    return api_key, model


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessoes (
                chat_id TEXT PRIMARY KEY,
                task_num TEXT,
                tecnico TEXT,
                contexto_form TEXT,
                mensagens_json TEXT,
                resumo_final TEXT DEFAULT '',
                criado_em TEXT,
                atualizado_em TEXT
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


def iniciar_chat_ia():
    """
    1º Passo (Botão no OfficeTrack):
    Extrai dados do contexto do formulário, inicia uma sessão de chat com o GPT-4o-mini
    e responde <Action>OpenUrl</Action> abrindo o Chatbot interativo no celular do técnico.
    Ao fechar a tela do chat, o OfficeTrack chama /finalizar_chat_ia/<chat_id>.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        task_num = "N/A"
        tecnico = "Técnico"
        campos_contexto = []

        if xml_data:
            try:
                parser = etree.XMLParser(recover=True)
                tree = etree.parse(StringIO(xml_data), parser)
                root = tree.getroot()

                task_num = root.findtext(".//Task/TaskNum") or "N/A"
                tecnico = root.findtext(".//Employee/EmployeeNumber") or "Técnico"

                # Captura campos relevantes preenchidos no form para dar contexto inicial à IA
                for f in root.findall(".//Field"):
                    fid = f.findtext("Id") or f.findtext("ID")
                    fval = f.findtext("Value")
                    if fid and fval and fid not in ("BTN_CHAT", "CHAT_RESUMO_IA", "CHAT_HISTORICO_IA", "CHAT_ID"):
                        campos_contexto.append(f"{fid}: {fval.strip()}")
            except Exception as ex:
                logging.warning(f"Erro ao extrair contexto XML para chat: {ex}")

        contexto_str = "\n".join(campos_contexto[:15]) if campos_contexto else "Atendimento de campo geral."

        system_prompt = (
            "Você é um Assistente Técnico Especialista em Operações de Campo (manutenção, engenharia, checklists e suporte técnico). "
            "Responda de forma clara, prática, objetiva e em português do Brasil, ideal para leitura rápida na tela do celular do técnico em campo.\n\n"
            f"Contexto da Ordem de Serviço atual (OS Nº {task_num}, Técnico: {tecnico}):\n{contexto_str}"
        )

        mensagens_iniciais = [
            {"role": "system", "content": system_prompt},
            {
                "role": "assistant",
                "content": f"Olá, {tecnico}! Sou seu assistente de IA (GPT-4o-mini) para a OS {task_num}. Como posso te ajudar neste atendimento agora?"
            }
        ]

        chat_id = str(uuid.uuid4())[:8].upper()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO chat_sessoes (chat_id, task_num, tecnico, contexto_form, mensagens_json, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (chat_id, task_num, tecnico, contexto_str, json.dumps(mensagens_iniciais, ensure_ascii=False), agora, agora)
            )
            conn.commit()

        base_url = _obter_base_url()
        url_chat = f"{base_url}/chat_ia/{chat_id}"
        url_finalizar = f"{base_url}/finalizar_chat_ia/{chat_id}"

        response = etree.Element("Response")
        ret = etree.SubElement(response, "ReturnValue")
        etree.SubElement(ret, "ShortText").text = "Chat IA"
        etree.SubElement(ret, "LongText").text = f"Sessão {chat_id}"
        etree.SubElement(ret, "Value").text = "OK"
        etree.SubElement(ret, "Action").text = "OpenUrl"
        etree.SubElement(ret, "Url").text = url_chat
        etree.SubElement(ret, "WebService").text = url_finalizar

        xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return Response(xml_str, content_type="application/xml; charset=utf-8")

    except Exception as e:
        logging.error(f"Erro em iniciar_chat_ia: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao iniciar chat IA: {str(e)}")


def tela_chat_ia(chat_id):
    """
    Interface Web Mobile-First do Chatbot IA aberta dentro do app OfficeTrack via OpenUrl.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM chat_sessoes WHERE chat_id = ?", (chat_id,)).fetchone()

    if not row:
        return "<h3>Sessão de chat não encontrada.</h3>", 404

    mensagens = json.loads(row["mensagens_json"])
    # Filtra a mensagem system da exibição visual
    mensagens_visiveis = [m for m in mensagens if m["role"] != "system"]

    html = r"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Assistente IA - OS {{ task_num }}</title>
        <style>
            * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            html, body { margin: 0; padding: 0; height: 100%; background: #f1f5f9; color: #0f172a; }
            .app-container { display: flex; flex-direction: column; height: 100dvh; max-width: 600px; margin: 0 auto; background: #ffffff; box-shadow: 0 0 20px rgba(0,0,0,0.08); }
            .header { background: linear-gradient(135deg, #0f172a, #1e293b); color: white; padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; }
            .header-title { font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
            .header-sub { font-size: 11px; color: #94a3b8; margin-top: 2px; }
            .btn-resumo { background: #10b981; color: white; border: none; padding: 8px 12px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer; }
            .btn-resumo:disabled { opacity: 0.6; }
            .chat-box { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; background: #f8fafc; }
            .msg { max-width: 85%; padding: 12px 14px; border-radius: 14px; font-size: 14px; line-height: 1.45; white-space: pre-wrap; word-wrap: break-word; }
            .msg-user { align-self: flex-end; background: #0284c7; color: white; border-bottom-right-radius: 4px; }
            .msg-assistant { align-self: flex-start; background: white; color: #1e293b; border: 1px solid #e2e8f0; border-bottom-left-radius: 4px; box-shadow: 0 2px 5px rgba(0,0,0,0.03); }
            .typing { align-self: flex-start; font-size: 12px; color: #64748b; font-style: italic; display: none; padding: 4px 10px; }
            .banner-ok { display: none; background: #ecfdf5; border-top: 2px solid #10b981; border-bottom: 2px solid #10b981; color: #065f46; padding: 12px 16px; font-size: 13px; text-align: center; font-weight: 600; flex-shrink: 0; }
            .input-area { padding: 10px 12px; background: white; border-top: 1px solid #e2e8f0; display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
            .input-area textarea { flex: 1; border: 1px solid #cbd5e1; border-radius: 20px; padding: 10px 14px; font-size: 15px; resize: none; height: 44px; max-height: 100px; outline: none; font-family: inherit; }
            .input-area textarea:focus { border-color: #0284c7; }
            .btn-send { background: #0284c7; color: white; border: none; width: 44px; height: 44px; border-radius: 50%; font-size: 18px; cursor: pointer; display: flex; justify-content: center; align-items: center; flex-shrink: 0; }
            .btn-send:disabled { background: #94a3b8; }
        </style>
    </head>
    <body>
        <div class="app-container">
            <div class="header">
                <div>
                    <div class="header-title">🤖 Assistente IA • GPT-4o-mini</div>
                    <div class="header-sub">OS {{ task_num }} • Sessão #{{ chat_id }}</div>
                </div>
                <button class="btn-resumo" id="btn-resumo" onclick="gerarResumo()">📌 Salvar p/ Form</button>
            </div>

            <div class="banner-ok" id="banner-ok">
                ✅ Resumo salvo! Agora toque em <strong>FECHAR (X)</strong> para enviar automaticamente para o formulário!
            </div>

            <div class="chat-box" id="chat-box">
                {% for m in mensagens %}
                    <div class="msg {{ 'msg-user' if m.role == 'user' else 'msg-assistant' }}">{{ m.content }}</div>
                {% endfor %}
                <div class="typing" id="typing">GPT-4o-mini está analisando e escrevendo...</div>
            </div>

            <div class="input-area">
                <textarea id="msg-input" placeholder="Digite sua pergunta técnica..." onkeydown="checarEnter(event)"></textarea>
                <button type="button" class="btn-send" id="btn-send" onclick="enviarMensagem()">➤</button>
            </div>
        </div>

        <script>
            const chatBox = document.getElementById("chat-box");
            const msgInput = document.getElementById("msg-input");
            const btnSend = document.getElementById("btn-send");
            const typing = document.getElementById("typing");

            function rolarParaBaixo() {
                chatBox.scrollTop = chatBox.scrollHeight;
            }
            rolarParaBaixo();

            function checarEnter(e) {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    enviarMensagem();
                }
            }

            function adicionarBalao(role, texto) {
                const div = document.createElement("div");
                div.className = "msg " + (role === "user" ? "msg-user" : "msg-assistant");
                div.textContent = texto;
                chatBox.insertBefore(div, typing);
                rolarParaBaixo();
                return div;
            }

            async function enviarMensagem() {
                const texto = msgInput.value.trim();
                if (!texto) return;

                msgInput.value = "";
                adicionarBalao("user", texto);

                msgInput.disabled = true;
                btnSend.disabled = true;
                typing.style.display = "block";
                rolarParaBaixo();

                let balaoIA = null;

                try {
                    const resp = await fetch("/api/chat_ia/{{ chat_id }}/mensagem", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ mensagem: texto })
                    });

                    if (!resp.ok) {
                        const errData = await resp.json().catch(() => ({}));
                        adicionarBalao("assistant", "⚠️ Erro: " + (errData.error || "Não foi possível obter resposta."));
                        return;
                    }

                    typing.style.display = "none";
                    balaoIA = adicionarBalao("assistant", "");

                    if (resp.body && typeof resp.body.getReader === "function") {
                        const reader = resp.body.getReader();
                        const decoder = new TextDecoder("utf-8");
                        let buffer = "";

                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;

                            buffer += decoder.decode(value, { stream: true });
                            const linhas = buffer.split("\n\n");
                            buffer = linhas.pop();

                            for (const linha of linhas) {
                                if (linha.startsWith("data: ")) {
                                    try {
                                        const payload = JSON.parse(linha.slice(6));
                                        if (payload.chunk) {
                                            balaoIA.textContent += payload.chunk;
                                            rolarParaBaixo();
                                        } else if (payload.error) {
                                            balaoIA.textContent += "\n⚠️ " + payload.error;
                                        }
                                    } catch (e) {}
                                }
                            }
                        }
                    } else {
                        // Fallback para WebViews antigas sem ReadableStream
                        const textoBruto = await resp.text();
                        const linhas = textoBruto.split("\n\n");
                        for (const linha of linhas) {
                            if (linha.startsWith("data: ")) {
                                try {
                                    const payload = JSON.parse(linha.slice(6));
                                    if (payload.chunk) balaoIA.textContent += payload.chunk;
                                    else if (payload.error) balaoIA.textContent += "\n⚠️ " + payload.error;
                                } catch (e) {}
                            }
                        }
                        rolarParaBaixo();
                    }
                } catch (err) {
                    if (balaoIA) {
                        balaoIA.textContent += "\n⚠️ Falha de conexão com o servidor.";
                    } else {
                        adicionarBalao("assistant", "⚠️ Falha de conexão com o servidor.");
                    }
                } finally {
                    typing.style.display = "none";
                    msgInput.disabled = false;
                    btnSend.disabled = false;
                    msgInput.focus();
                }
            }

            async function gerarResumo() {
                const btn = document.getElementById("btn-resumo");
                btn.disabled = true;
                btn.innerText = "Gerando...";
                typing.style.display = "block";

                try {
                    const resp = await fetch("/api/chat_ia/{{ chat_id }}/resumir", { method: "POST" });
                    const data = await resp.json();
                    if (data.resumo) {
                        adicionarBalao("assistant", "📌 RESUMO PREPARADO PARA O FORMULÁRIO:\n\n" + data.resumo);
                        document.getElementById("banner-ok").style.display = "block";
                        btn.innerText = "✔ Salvo!";
                    } else {
                        alert("Erro ao gerar resumo: " + (data.error || "Tente novamente"));
                        btn.disabled = false;
                        btn.innerText = "📌 Salvar p/ Form";
                    }
                } catch (err) {
                    alert("Erro de conexão ao gerar resumo.");
                    btn.disabled = false;
                    btn.innerText = "📌 Salvar p/ Form";
                } finally {
                    typing.style.display = "none";
                }
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(
        html,
        chat_id=chat_id,
        task_num=row["task_num"],
        mensagens=mensagens_visiveis
    )


def enviar_mensagem_chat_ia(chat_id):
    """Recebe a mensagem do técnico, chama a API OpenAI (gpt-4o-mini) em STREAM e salva o histórico."""
    api_key, model = _get_openai_config()
    if not api_key:
        return jsonify({"error": "Variável OPENAI_API_KEY não configurada no servidor (Render)."}), 500

    dados = request.get_json(silent=True) or {}
    texto_usuario = (dados.get("mensagem") or "").strip()
    if not texto_usuario:
        return jsonify({"error": "Mensagem vazia."}), 400

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM chat_sessoes WHERE chat_id = ?", (chat_id,)).fetchone()

    if not row:
        return jsonify({"error": "Sessão não encontrada."}), 404

    mensagens = json.loads(row["mensagens_json"])
    mensagens.append({"role": "user", "content": texto_usuario})

    def gerar_stream():
        resposta_completa = []
        try:
            resp = requests.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": mensagens,
                    "temperature": 0.5,
                    "stream": True
                },
                stream=True,
                timeout=45
            )

            if resp.status_code != 200:
                logging.error(f"Erro OpenAI ({resp.status_code}): {resp.text}")
                yield f"data: {json.dumps({'error': f'Erro da API OpenAI ({resp.status_code}). Verifique a chave.'})}\n\n"
                return

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(data_str)
                    choices = chunk_json.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            resposta_completa.append(content)
                            yield f"data: {json.dumps({'chunk': content})}\n\n"
                except Exception:
                    continue

            texto_final = "".join(resposta_completa).strip()
            if texto_final:
                mensagens.append({"role": "assistant", "content": texto_final})
                agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(
                        "UPDATE chat_sessoes SET mensagens_json = ?, atualizado_em = ? WHERE chat_id = ?",
                        (json.dumps(mensagens, ensure_ascii=False), agora, chat_id)
                    )
                    conn.commit()

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            logging.error(f"Erro no stream OpenAI: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': f'Falha na comunicação com a OpenAI: {str(e)}'})}\n\n"

    return Response(
        stream_with_context(gerar_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


def resumir_chat_ia(chat_id):
    """Pede ao GPT-4o-mini um resumo técnico conciso de toda a conversa para enviar ao formulário."""
    api_key, model = _get_openai_config()
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY não configurada."}), 500

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM chat_sessoes WHERE chat_id = ?", (chat_id,)).fetchone()

    if not row:
        return jsonify({"error": "Sessão não encontrada."}), 404

    mensagens = json.loads(row["mensagens_json"])
    mensagens_resumo = mensagens + [
        {
            "role": "user",
            "content": "Resuma de forma direta e técnica (em no máximo 2 parágrafos curtos) a conclusão, diagnóstico ou orientação obtida nesta conversa, para ser anexada diretamente no formulário da Ordem de Serviço."
        }
    ]

    try:
        resp = requests.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": mensagens_resumo,
                "temperature": 0.3
            },
            timeout=25
        )
        if resp.status_code != 200:
            return jsonify({"error": f"Erro OpenAI ({resp.status_code})"}), 500

        resumo = resp.json()["choices"][0]["message"]["content"].strip()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE chat_sessoes SET resumo_final = ?, atualizado_em = ? WHERE chat_id = ?",
                (resumo, agora, chat_id)
            )
            conn.commit()

        return jsonify({"resumo": resumo})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def finalizar_chat_ia(chat_id):
    """
    2º Passo Automático (Chamado pelo OfficeTrack quando o técnico fecha a janela do Chat):
    Retorna o resumo (ou a última resposta da IA) e o histórico da conversa para os campos do formulário.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM chat_sessoes WHERE chat_id = ?", (chat_id,)).fetchone()

        if not row:
            return _resposta_v2_erro(f"Sessão de chat {chat_id} não encontrada.")

        mensagens = json.loads(row["mensagens_json"])
        # Monta transcrição legível ignorando system prompt e saudação inicial se houve conversa
        interacoes = [m for m in mensagens if m["role"] != "system"]
        historico_linhas = []
        ultima_resposta_ia = ""

        for m in interacoes:
            if m["role"] == "user":
                historico_linhas.append(f"Técnico: {m['content']}")
            else:
                historico_linhas.append(f"IA: {m['content']}")
                ultima_resposta_ia = m["content"]

        # Se o técnico não clicou no botão de resumo, usa a última resposta da IA automaticamente
        resumo = row["resumo_final"].strip() if row["resumo_final"] else ultima_resposta_ia
        historico_texto = "\n\n".join(historico_linhas)

        campos = {
            "CHAT_ID": chat_id,
            "CHAT_RESUMO_IA": resumo,
            "CHAT_HISTORICO_IA": historico_texto
        }

        msg_popup = "Conversa com Assistente IA importada para o formulário com sucesso!"

        return _resposta_v2_sucesso(
            sucesso=True,
            mensagem=msg_popup,
            short_text="IA OK",
            campos=campos
        )

    except Exception as e:
        logging.error(f"Erro em finalizar_chat_ia: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao finalizar chat IA: {str(e)}")


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
        short_text="Erro IA",
        long_text="Toque na lixeira para tentar novamente"
    )

