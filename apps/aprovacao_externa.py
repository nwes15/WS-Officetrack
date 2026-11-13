from flask import request, Response, jsonify, render_template_string
from lxml import etree
import logging
import sqlite3
import uuid
import os
import re
import json
import requests
from datetime import datetime
from io import BytesIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "aprovacoes_externas.db")

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL") or os.getenv("EVOLUTION_URL") or "https://whatsapp.cloudwesns.com.br"
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
                cargo_respondente TEXT DEFAULT '',
                observacao TEXT DEFAULT '',
                criado_em TEXT,
                respondido_em TEXT DEFAULT '',
                diagnostico_wa TEXT DEFAULT '',
                detalhes_json TEXT DEFAULT '{}'
            )
        """)
        # Migrações seguras de colunas
        for col, tipo in [
            ("diagnostico_wa", "TEXT DEFAULT ''"),
            ("detalhes_json", "TEXT DEFAULT '{}'"),
            ("cargo_respondente", "TEXT DEFAULT ''")
        ]:
            try:
                conn.execute(f"ALTER TABLE transacoes ADD COLUMN {col} {tipo}")
            except Exception:
                pass
        conn.commit()
    try:
        os.chmod(DB_PATH, 0o666)
    except Exception:
        pass


_init_db()


def _parse_xml(xml_data):
    """Parse seguro de XML removendo declarações incompatíveis."""
    limpo = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", xml_data, count=1, flags=re.IGNORECASE)
    parser = etree.XMLParser(recover=True)
    return etree.parse(BytesIO(limpo.encode("utf-8")), parser).getroot()


def _obter_base_url():
    """Detecta automaticamente o domínio (Cloudflare HTTPS ou local HTTP)."""
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    if "trycloudflare" in host or "onrender.com" in host or (
        "127.0.0.1" not in host and "localhost" not in host and not host.startswith("192.168.")
    ):
        if not request.headers.get("X-Forwarded-Proto"):
            proto = "https"
    return f"{proto}://{host}"


def _extrair_float(valor_str):
    if not valor_str:
        return 0.0
    limpo = str(valor_str).replace("R$", "").replace(" ", "").strip()
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    try:
        return float(limpo)
    except Exception:
        return 0.0


def _formatar_br(num):
    try:
        val = float(num)
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


def _extrair_detalhes_completos(root, campos_form):
    """
    Extrai informações ricas do XML de OS do OfficeTrack:
    - Contexto: Cliente, Local/Endereço, Equipamento/Ativo, Sistema
    - Diagnóstico: Defeito constatado, Sintoma, Solução/Serviço executado
    - Tabelas: Peças utilizadas, serviços executados, quantidades e custos
    - Fotos/Evidências
    - Totalizadores financeiros
    """
    # 1. Identificação de Cliente
    cliente = (
        campos_form.get("CLIENTE")
        or campos_form.get("NOME_CLIENTE")
        or campos_form.get("RAZAO_SOCIAL")
        or campos_form.get("EMPRESA")
        or campos_form.get("NOME_FANTASIA")
        or root.findtext(".//Task/CustomerName")
        or "Cliente Não Informado"
    )

    # 2. Localização / Unidade
    local = (
        campos_form.get("LOCAL")
        or campos_form.get("ENDERECO")
        or campos_form.get("UNIDADE")
        or campos_form.get("FILIAL")
        or campos_form.get("SETOR")
        or campos_form.get("CIDADE")
        or root.findtext(".//Task/Address")
        or "Atendimento em Campo"
    )

    # 3. Equipamento / Máquina / Ativo
    equipamento = (
        campos_form.get("EQUIPAMENTO")
        or campos_form.get("ATIVO")
        or campos_form.get("MAQUINA")
        or campos_form.get("DISPOSITIVO")
        or campos_form.get("MODELO")
        or campos_form.get("TAG")
        or "Equipamento / Sistema Geral"
    )
    serie = (
        campos_form.get("NUMERO_SERIE")
        or campos_form.get("SERIAL")
        or campos_form.get("SERIE")
        or campos_form.get("TAG_ATIVO")
        or ""
    )

    # 4. Defeito e Serviço Executado
    defeito = (
        campos_form.get("DEFEITO_CONSTATADO")
        or campos_form.get("DEFEITO")
        or campos_form.get("PROBLEMA")
        or campos_form.get("SINTOMA")
        or campos_form.get("DIAGNOSTICO")
        or campos_form.get("RECLAMACAO")
        or campos_form.get("MOTIVO_SOLICITACAO")
        or "Manutenção e revisão técnica preventiva/corretiva."
    )

    servico = (
        campos_form.get("SERVICO_EXECUTADO")
        or campos_form.get("SERVICO")
        or campos_form.get("RESUMO_SERVICO")
        or campos_form.get("SOLUCAO")
        or campos_form.get("ACAO_REALIZADA")
        or campos_form.get("DESCRICAO_SERVICO")
        or "Serviço técnico realizado conforme especificação de trabalho."
    )

    observacoes = (
        campos_form.get("OBS_TECNICA")
        or campos_form.get("OBSERVACOES")
        or campos_form.get("OBS")
        or campos_form.get("PARECER_TECNICO")
        or ""
    )

    # 5. Itens e Peças (via Tabelas Dinâmicas ou campos lineares)
    itens = []
    total_itens_calculado = 0.0

    # Busca em todas as tabelas dinâmicas <TableField>
    for table in root.findall(".//TableField"):
        table_id = (table.findtext("Id") or table.findtext("ID") or "TABELA").upper()
        for idx, row in enumerate(table.findall(".//Row"), start=1):
            row_campos = {}
            for f in row.findall(".//Field"):
                fid = f.findtext("Id") or f.findtext("ID") or f.findtext("id")
                fval = f.findtext("Value") or ""
                if fid:
                    row_campos[fid.strip().upper()] = fval.strip()

            nome_item = (
                row_campos.get("ITEM")
                or row_campos.get("PECA")
                or row_campos.get("SERVICO")
                or row_campos.get("DESCRICAO")
                or row_campos.get("PRODUTO")
                or row_campos.get("EQUIPAMENTO")
                or f"Item #{idx}"
            )

            qtd_str = (
                row_campos.get("QTD")
                or row_campos.get("QUANTIDADE")
                or row_campos.get("QTDE")
                or "1"
            )
            try:
                qtd = float(qtd_str.replace(",", "."))
            except Exception:
                qtd = 1.0

            unit_str = (
                row_campos.get("VALOR_UNIT")
                or row_campos.get("PRECO_UNIT")
                or row_campos.get("VALOR")
                or row_campos.get("UNITARIO")
                or row_campos.get("PRECO")
                or "0"
            )
            unit = _extrair_float(unit_str)

            total_str = (
                row_campos.get("TOTAL")
                or row_campos.get("VALOR_TOTAL")
                or row_campos.get("SUBTOTAL")
            )
            if total_str:
                total_linha = _extrair_float(total_str)
            else:
                total_linha = round(qtd * unit, 2)

            tipo_item = "Peça" if "PECA" in table_id or "MATERIAL" in table_id else "Item"
            if any(k in nome_item.upper() for k in ("HORA", "SERVICO", "MAO DE OBRA", "VISITA", "TAXA")):
                tipo_item = "Serviço"

            itens.append({
                "nome": nome_item,
                "qtd": qtd,
                "unitario": unit,
                "total": total_linha,
                "tipo": tipo_item
            })
            total_itens_calculado += total_linha

    # Se não houver tabela mas houver campos lineares de peças/itens
    if not itens:
        for i in range(1, 10):
            peca_nome = campos_form.get(f"PECA_{i}") or campos_form.get(f"ITEM_{i}")
            if peca_nome:
                qtd_i = _extrair_float(campos_form.get(f"QTD_{i}") or "1") or 1.0
                val_i = _extrair_float(campos_form.get(f"VALOR_{i}") or campos_form.get(f"PRECO_{i}") or "0")
                tot_i = round(qtd_i * val_i, 2)
                itens.append({
                    "nome": peca_nome,
                    "qtd": qtd_i,
                    "unitario": val_i,
                    "total": tot_i,
                    "tipo": "Peça"
                })
                total_itens_calculado += tot_i

    # 6. Valores Financeiros
    subtotal = _extrair_float(campos_form.get("SUBTOTAL") or campos_form.get("VALOR_SUBTOTAL"))
    desconto = _extrair_float(campos_form.get("DESCONTO") or campos_form.get("VALOR_DESCONTO"))
    valor_total = _extrair_float(
        campos_form.get("VALOR_TOTAL")
        or campos_form.get("TOTAL")
        or campos_form.get("VALOR")
        or campos_form.get("VALOR_FINAL")
    )

    if not valor_total and total_itens_calculado > 0:
        valor_total = total_itens_calculado
    if not subtotal and total_itens_calculado > 0:
        subtotal = total_itens_calculado

    # 7. Fotos e Evidências
    fotos = []
    for k, v in campos_form.items():
        if any(term in k for term in ("FOTO", "IMG", "FOTO_ANTES", "FOTO_DEPOIS", "EVIDENCIA")) and v:
            titulo = k.replace("_", " ").title()
            # Se for link HTTP ou Data URI
            if v.startswith("http://") or v.startswith("https://") or v.startswith("data:image/"):
                fotos.append({"titulo": titulo, "url": v})

    return {
        "cliente": cliente,
        "local": local,
        "equipamento": equipamento,
        "serie": serie,
        "defeito": defeito,
        "servico": servico,
        "observacoes": observacoes,
        "itens": itens,
        "tem_itens": len(itens) > 0,
        "subtotal": subtotal,
        "subtotal_fmt": _formatar_br(subtotal),
        "desconto": desconto,
        "desconto_fmt": _formatar_br(desconto),
        "valor_total": valor_total,
        "valor_total_fmt": _formatar_br(valor_total),
        "fotos": fotos,
        "tem_fotos": len(fotos) > 0,
    }


def iniciar_aprovacao_externa():
    """
    1º Passo (Botão no OfficeTrack):
    Gera a transação (txId), extrai todos os dados da OS (equipamentos, laudo, itens e custos),
    envia o link via WhatsApp (com resumo executivo) e abre a Sala de Espera no app.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("Não foi possível obter os dados XML do formulário.")

        root = _parse_xml(xml_data)

        task_num = root.findtext(".//Task/TaskNum") or "N/A"
        tecnico = root.findtext(".//Employee/EmployeeNumber") or "Técnico de Campo"

        # Extrai todos os campos em dicionário
        campos_form = {}
        for f in root.findall(".//Field"):
            fid = f.findtext("Id") or f.findtext("ID") or f.findtext("id")
            fval = f.findtext("Value") or ""
            if fid:
                campos_form[fid.strip().upper()] = fval.strip()

        logging.info(f"[APROVACAO] Iniciando OS {task_num} - Campos recebidos: {len(campos_form)}")

        # Extrai o resumo estruturado completo da OS
        detalhes = _extrair_detalhes_completos(root, campos_form)

        nome_aprovador = (
            campos_form.get("NOME_APROVADOR")
            or campos_form.get("NOME_CLIENTE")
            or campos_form.get("APROVADOR")
            or detalhes["cliente"]
            or "Cliente / Supervisor"
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
        if not tel_bruto:
            for k, v in campos_form.items():
                if v and any(p in k for p in ("TEL", "WHATS", "CEL", "FONE")):
                    tel_bruto = v
                    break
        tel_limpo = re.sub(r"\D", "", tel_bruto)

        motivo = detalhes["servico"] or "Aprovação e validação de ordem de serviço em campo."

        tx_id = str(uuid.uuid4())[:8].upper()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        base_url = _obter_base_url()
        url_responder = f"{base_url}/responder/{tx_id}"
        url_espera = f"{base_url}/espera/{tx_id}"
        url_webservice_retorno = f"{base_url}/finalizar_aprovacao/{tx_id}"

        evo_url = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/") or EVOLUTION_API_URL.strip().rstrip("/")
        evo_key = os.getenv("EVOLUTION_API_KEY", "").strip() or EVOLUTION_API_KEY.strip()

        diagnostico_wa = ""

        # Envio automático WhatsApp com resumo executivo de alto impacto
        if tel_limpo and len(tel_limpo) >= 10 and evo_key:
            num_wa = tel_limpo if tel_limpo.startswith("55") else f"55{tel_limpo}"

            # Monta resumo do serviço em poucas palavras para WhatsApp
            servico_resumo = detalhes["servico"]
            if len(servico_resumo) > 120:
                servico_resumo = servico_resumo[:117] + "..."

            msg_wa = (
                f"📋 *SOLICITAÇÃO DE APROVAÇÃO TÉCNICA*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Olá, *{nome_aprovador}*!\n\n"
                f"O técnico *{tecnico}* finalizou os serviços da *OS #{task_num}* e solicita sua revisão e validação digital:\n\n"
                f"🏢 *Cliente / Local:* {detalhes['cliente']}\n"
                f"⚙️ *Equipamento:* {detalhes['equipamento']}\n"
                f"🔧 *Serviço:* {servico_resumo}\n"
            )

            if detalhes["valor_total"] > 0:
                msg_wa += f"💰 *Valor Total:* R$ {detalhes['valor_total_fmt']}\n"

            msg_wa += (
                f"\n👉 *Acesse o resumo completo com itens e fotos para aprovar:*\n"
                f"{url_responder}\n\n"
                f"_Protocolo de Validação: #{tx_id}_"
            )

            try:
                resp_wa = requests.post(
                    f"{evo_url}/send/text",
                    headers={"apikey": evo_key, "Content-Type": "application/json"},
                    json={"number": num_wa, "text": msg_wa, "linkPreview": False},
                    timeout=10
                )
                logging.info(f"[APROVACAO] WhatsApp enviado para {num_wa}: HTTP {resp_wa.status_code}")
                if resp_wa.status_code in (200, 201):
                    diagnostico_wa = f"✅ WhatsApp disparado para +{num_wa}"
                else:
                    diagnostico_wa = f"⚠️ Erro Evolution HTTP {resp_wa.status_code}: {resp_wa.text[:120]}"
            except Exception as ex:
                logging.warning(f"[APROVACAO] Falha ao enviar WhatsApp: {ex}")
                diagnostico_wa = f"⚠️ Falha conexão ({evo_url}): {str(ex)[:120]}"
        else:
            campos_keys = list(campos_form.keys())
            diagnostico_wa = f"⚠️ Link gerado (WhatsApp não disparado: tel='{tel_limpo}')"

        # Salva a transação com os detalhes completos em JSON
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO transacoes (tx_id, task_num, tecnico, nome_aprovador, tel_aprovador, motivo, status, criado_em, diagnostico_wa, detalhes_json)
                   VALUES (?, ?, ?, ?, ?, ?, 'AGUARDANDO', ?, ?, ?)""",
                (tx_id, task_num, tecnico, nome_aprovador, tel_limpo, motivo, agora, diagnostico_wa, json.dumps(detalhes, ensure_ascii=False))
            )
            conn.commit()

        # Retorna Action=OpenUrl para abrir a Sala de Espera no app
        response = etree.Element("Response")
        ret = etree.SubElement(response, "ReturnValue")
        etree.SubElement(ret, "ShortText").text = "Aguardando"
        etree.SubElement(ret, "LongText").text = f"Sessão {tx_id}"
        etree.SubElement(ret, "Value").text = "OK"
        etree.SubElement(ret, "Action").text = "OpenUrl"
        etree.SubElement(ret, "Url").text = url_espera
        etree.SubElement(ret, "WebService").text = url_webservice_retorno

        xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return Response(xml_str, content_type="application/xml; charset=utf-8")

    except Exception as e:
        logging.error(f"Erro em iniciar_aprovacao_externa: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao iniciar aprovação: {str(e)}")


def sala_espera(tx_id):
    """
    Sala de Espera aberta pelo app OfficeTrack do técnico via OpenUrl.
    Exibe status em tempo real, permite reenviar link no WhatsApp ou copiar.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM transacoes WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return "<h3>Transação não encontrada.</h3>", 404

    base_url = _obter_base_url()
    url_responder = f"{base_url}/responder/{tx_id}"

    detalhes = {}
    if row["detalhes_json"]:
        try:
            detalhes = json.loads(row["detalhes_json"])
        except Exception:
            pass

    cliente = detalhes.get("cliente") or row["nome_aprovador"]
    valor_fmt = detalhes.get("valor_total_fmt") or ""

    texto_wa = f"Olá {row['nome_aprovador']}! Por favor, revise e confirme o laudo da OS #{row['task_num']} através deste link seguro: {url_responder}"
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
            body { margin: 0; padding: 20px; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
            .card { background: #1e293b; border: 1px solid #334155; border-radius: 20px; padding: 26px; max-width: 440px; width: 100%; box-shadow: 0 20px 40px rgba(0,0,0,0.4); text-align: center; }
            .badge { display: inline-flex; align-items: center; gap: 6px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 700; padding: 6px 14px; border-radius: 999px; font-size: 12px; margin-bottom: 16px; border: 1px solid rgba(56, 189, 248, 0.3); }
            h2 { margin: 0 0 8px 0; font-size: 22px; font-weight: 700; color: #ffffff; }
            p { color: #94a3b8; font-size: 14px; line-height: 1.5; margin: 6px 0; }
            .spinner { width: 52px; height: 52px; border: 5px solid rgba(56, 189, 248, 0.2); border-top-color: #38bdf8; border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto; }
            @keyframes spin { to { transform: rotate(360deg); } }
            .summary-box { background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 14px; margin: 16px 0; text-align: left; font-size: 13px; }
            .summary-item { display: flex; justify-content: space-between; margin-bottom: 6px; color: #cbd5e1; }
            .summary-item strong { color: #f1f5f9; }
            .box-link { background: #0f172a; border: 1px dashed #475569; border-radius: 10px; padding: 10px; margin: 14px 0; word-break: break-all; font-size: 12px; color: #94a3b8; }
            .btn { display: block; width: 100%; padding: 14px; border-radius: 12px; border: none; font-weight: 700; font-size: 15px; cursor: pointer; text-decoration: none; margin-top: 10px; transition: all 0.2s; }
            .btn-wa { background: #22c55e; color: white; }
            .btn-wa:hover { background: #16a34a; }
            .btn-copy { background: #334155; color: white; }
            .btn-copy:hover { background: #475569; }
            .success-box { display: none; background: #064e3b; border: 2px solid #10b981; border-radius: 16px; padding: 20px; margin-top: 16px; }
            .success-box h3 { color: #34d399; margin: 0 0 8px 0; font-size: 20px; }
            .obs-result { background: rgba(0,0,0,0.3); padding: 12px; border-radius: 10px; text-align: left; font-size: 13px; margin-top: 12px; border: 1px solid #059669; color: #e2e8f0; }
            .alert-close { background: #10b981; color: #022c22; padding: 14px; border-radius: 10px; font-weight: 800; margin-top: 16px; font-size: 14px; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3); }
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">
                <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#38bdf8;"></span>
                SESSÃO ATIVA #{{ tx_id }}
            </span>
            
            <div id="waiting-section">
                <div class="spinner"></div>
                <h2>Aguardando Aprovação</h2>
                <p>O link com o laudo executivo e itens foi disponibilizado para <strong>{{ nome_aprovador }}</strong>.</p>
                
                <div class="summary-box">
                    <div class="summary-item"><span>OS Número:</span> <strong>#{{ task_num }}</strong></div>
                    <div class="summary-item"><span>Cliente:</span> <strong>{{ cliente }}</strong></div>
                    {% if valor_fmt %}
                    <div class="summary-item"><span>Valor Total:</span> <strong style="color:#34d399;">R$ {{ valor_fmt }}</strong></div>
                    {% endif %}
                </div>

                <div class="box-link" id="link-texto">{{ url_responder }}</div>
                
                <a href="{{ wa_link }}" target="_blank" class="btn btn-wa">📲 Abrir e Enviar no WhatsApp</a>
                <button onclick="copiarLink()" class="btn btn-copy" id="btn-copy">📋 Copiar Link de Aprovação</button>
                
                <div style="margin-top:12px; font-size:11px; color:#64748b; background:#0f172a; padding:8px; border-radius:8px; word-break:break-word;">
                    {{ diagnostico_wa }}
                </div>
            </div>

            <div id="success-section" class="success-box">
                <div style="font-size: 44px; margin-bottom: 8px;">✅</div>
                <h3>Resposta Recebida!</h3>
                <p style="color:#a7f3d0; margin: 4px 0;"><strong>Decisão:</strong> <span id="res-decisao" style="font-weight:bold; color:white;"></span></p>
                <p style="color:#a7f3d0; margin: 4px 0;"><strong>Assinado por:</strong> <span id="res-nome" style="color:white;"></span></p>
                <div class="obs-result">
                    <strong>Observações / Parecer:</strong><br>
                    <span id="res-obs"></span>
                </div>
                <div class="alert-close">
                    👇 Toque no botão [X] ou VOLTAR desta janela para preencher o formulário automaticamente!
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
                        document.getElementById("res-obs").innerText = data.observacao || "Sem observações registradas.";
                        return;
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
        cliente=cliente,
        valor_fmt=valor_fmt,
        url_responder=url_responder,
        wa_link=wa_link,
        diagnostico_wa=row["diagnostico_wa"] if "diagnostico_wa" in row.keys() else ""
    )


def responder_externo(tx_id):
    """
    Página Web Pública Premium que o Supervisor / Cliente abre pelo WhatsApp.
    Apresenta o resumo executivo completo da OS com:
    - Contexto da OS (Cliente, Local, Equipamento, Técnico, Data/Hora)
    - Laudo Técnico (Defeito Constatado vs. Solução Executada)
    - Tabela de Peças e Itens Utilizados com quantidades e valores
    - Resumo Financeiro (Subtotal, Desconto e Total em destaque)
    - Galeria de Fotos / Evidências do serviço
    - Decisão digital (Aprovar / Reprovar com justificativa)
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM transacoes WHERE tx_id = ?", (tx_id,)).fetchone()

    if not row:
        return "<h3>Link de aprovação inválido ou expirado.</h3>", 404

    detalhes = {}
    if row["detalhes_json"]:
        try:
            detalhes = json.loads(row["detalhes_json"])
        except Exception:
            pass

    if request.method == "POST":
        decisao = request.form.get("decisao", "APROVADO").strip().upper()
        nome_resp = request.form.get("nome_respondente", "").strip() or row["nome_aprovador"]
        cargo_resp = request.form.get("cargo_respondente", "").strip()
        obs = request.form.get("observacao", "").strip()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """UPDATE transacoes 
                   SET status = 'RESPONDIDO', decisao = ?, nome_respondente = ?, cargo_respondente = ?, observacao = ?, respondido_em = ?
                   WHERE tx_id = ?""",
                (decisao, nome_resp, cargo_resp, obs, agora, tx_id)
            )
            conn.commit()

        is_aprovado = (decisao == "APROVADO")

        html_pos = """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Parecer Registrado - OS {{ task_num }}</title>
            <style>
                * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
                body { background: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
                .card { background: white; border-radius: 20px; padding: 36px 28px; max-width: 460px; width: 100%; text-align: center; box-shadow: 0 15px 35px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }
                .icon { font-size: 58px; margin-bottom: 12px; }
                h2 { color: #0f172a; margin: 0 0 10px 0; font-size: 24px; font-weight: 800; }
                .badge-decisao { display: inline-block; padding: 8px 18px; border-radius: 999px; font-weight: 800; font-size: 14px; margin-bottom: 16px; letter-spacing: 0.5px; }
                .badge-aprovado { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
                .badge-reprovado { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
                p { color: #475569; font-size: 14px; line-height: 1.6; margin: 6px 0; }
                .audit-box { background: #f1f5f9; border-radius: 12px; padding: 14px; margin-top: 24px; text-align: left; font-size: 13px; color: #334155; }
                .audit-item { display: flex; justify-content: space-between; margin-bottom: 6px; }
                .audit-item span { color: #64748b; }
                .audit-item strong { color: #0f172a; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">{% if is_aprovado %}🎉{% else %}📋{% endif %}</div>
                <div class="badge-decisao {% if is_aprovado %}badge-aprovado{% else %}badge-reprovado{% endif %}">
                    {% if is_aprovado %}✔ SERVIÇO APROVADO{% else %}✖ REPROVADO COM APONTAMENTO{% endif %}
                </div>
                <h2>Parecer Enviado com Sucesso!</h2>
                <p>Sua validação eletrônica foi sincronizada em tempo real com o aplicativo do técnico em campo.</p>
                
                <div class="audit-box">
                    <div class="audit-item"><span>Protocolo:</span> <strong>#{{ tx_id }}</strong></div>
                    <div class="audit-item"><span>Ordem de Serviço:</span> <strong>OS #{{ task_num }}</strong></div>
                    <div class="audit-item"><span>Assinado por:</span> <strong>{{ nome_resp }}</strong></div>
                    {% if cargo_resp %}
                    <div class="audit-item"><span>Cargo / Documento:</span> <strong>{{ cargo_resp }}</strong></div>
                    {% endif %}
                    <div class="audit-item"><span>Data e Hora:</span> <strong>{{ agora }}</strong></div>
                    {% if obs %}
                    <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #cbd5e1; font-size: 12px;">
                        <span style="color:#64748b;">Parecer Registrado:</span><br>
                        <em>"{{ obs }}"</em>
                    </div>
                    {% endif %}
                </div>

                <p style="font-size: 12px; color: #94a3b8; margin-top: 24px;">Você já pode fechar esta página com segurança.</p>
            </div>
        </body>
        </html>
        """
        return render_template_string(
            html_pos,
            is_aprovado=is_aprovado,
            task_num=row["task_num"],
            tx_id=tx_id,
            nome_resp=nome_resp,
            cargo_resp=cargo_resp,
            agora=agora,
            obs=obs
        )

    # Se já foi respondido anteriormente, avisa o usuário
    if row["status"] == "RESPONDIDO":
        decisao = row["decisao"]
        is_aprovado = (decisao == "APROVADO")
        html_ja_respondido = """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Sessão Concluída - OS {{ task_num }}</title>
            <style>
                body { font-family: -apple-system, sans-serif; background: #f8fafc; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
                .card { background: white; padding: 32px; border-radius: 16px; max-width: 440px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }
                h2 { color: #0f172a; margin: 12px 0 8px 0; }
                p { color: #64748b; font-size: 14px; line-height: 1.5; }
            </style>
        </head>
        <body>
            <div class="card">
                <div style="font-size: 48px;">🔒</div>
                <h2>Aprovação Já Registrada</h2>
                <p>Esta solicitação referente à <strong>OS #{{ task_num }}</strong> já foi respondida anteriormente.</p>
                <p><strong>Decisão registrada:</strong> {{ decisao }}<br><strong>Por:</strong> {{ nome_resp }} em {{ data_resp }}</p>
                <p style="font-size: 12px; color: #94a3b8; margin-top: 20px;">Protocolo #{{ tx_id }}</p>
            </div>
        </body>
        </html>
        """
        return render_template_string(
            html_ja_respondido,
            task_num=row["task_num"],
            decisao=decisao,
            nome_resp=row["nome_respondente"],
            data_resp=row["respondido_em"],
            tx_id=tx_id
        )

    # Renderiza o Template Executivo com todo o Laudo e Resumo dos Serviços
    html_resumo_executivo = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Resumo e Aprovação da OS #{{ task_num }}</title>
        <style>
            :root {
                --primary: #0284c7;
                --primary-dark: #0369a1;
                --success: #10b981;
                --success-dark: #059669;
                --danger: #ef4444;
                --slate-50: #f8fafc;
                --slate-100: #f1f5f9;
                --slate-200: #e2e8f0;
                --slate-600: #475569;
                --slate-800: #1e293b;
                --slate-900: #0f172a;
            }
            * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
            body { margin: 0; padding: 20px 14px; background: #f1f5f9; color: var(--slate-900); display: flex; justify-content: center; }
            .container { max-width: 640px; width: 100%; margin: 0 auto; }
            
            /* Topo da Ordem de Serviço */
            .header-card {
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                color: white;
                border-radius: 20px;
                padding: 24px;
                box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15);
                margin-bottom: 16px;
                position: relative;
                overflow: hidden;
            }
            .header-card::after {
                content: "";
                position: absolute;
                top: -30px;
                right: -30px;
                width: 120px;
                height: 120px;
                background: radial-gradient(circle, rgba(56, 189, 248, 0.25) 0%, transparent 70%);
                border-radius: 50%;
            }
            .os-tag {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.2);
                padding: 4px 12px;
                border-radius: 999px;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                margin-bottom: 12px;
            }
            .header-title { font-size: 22px; font-weight: 800; margin: 0 0 6px 0; }
            .header-subtitle { color: #94a3b8; font-size: 13px; margin: 0; }

            /* Cartões de Seção */
            .section-card {
                background: white;
                border-radius: 18px;
                padding: 20px;
                margin-bottom: 16px;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.04);
                border: 1px solid var(--slate-200);
            }
            .section-title {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 15px;
                font-weight: 700;
                color: var(--slate-800);
                margin: 0 0 14px 0;
                padding-bottom: 10px;
                border-bottom: 1px solid var(--slate-100);
            }
            
            /* Grid de Dados Básicos */
            .data-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px;
            }
            @media (max-width: 480px) {
                .data-grid { grid-template-columns: 1fr; }
            }
            .data-item {
                background: var(--slate-50);
                padding: 10px 12px;
                border-radius: 10px;
                border: 1px solid var(--slate-200);
            }
            .data-label {
                font-size: 11px;
                font-weight: 600;
                color: var(--slate-600);
                text-transform: uppercase;
                letter-spacing: 0.4px;
                margin-bottom: 3px;
            }
            .data-value {
                font-size: 13px;
                font-weight: 700;
                color: var(--slate-900);
                word-break: break-word;
            }

            /* Laudo Técnico (Diagnóstico vs Solução) */
            .diag-box {
                background: #fffbeb;
                border: 1px solid #fde68a;
                border-left: 4px solid #f59e0b;
                border-radius: 12px;
                padding: 12px 14px;
                margin-bottom: 10px;
            }
            .diag-box .label { font-size: 11px; font-weight: 800; color: #b45309; text-transform: uppercase; margin-bottom: 4px; display: flex; align-items: center; gap: 5px; }
            .diag-box .text { font-size: 13px; color: #78350f; line-height: 1.5; }

            .solution-box {
                background: #f0fdf4;
                border: 1px solid #bbf7d0;
                border-left: 4px solid #10b981;
                border-radius: 12px;
                padding: 12px 14px;
                margin-bottom: 10px;
            }
            .solution-box .label { font-size: 11px; font-weight: 800; color: #15803d; text-transform: uppercase; margin-bottom: 4px; display: flex; align-items: center; gap: 5px; }
            .solution-box .text { font-size: 13px; color: #14532d; line-height: 1.5; }

            /* Tabela de Itens e Peças */
            .table-container {
                overflow-x: auto;
                margin: 10px 0;
                border-radius: 12px;
                border: 1px solid var(--slate-200);
            }
            table {
                width: 100%;
                border-collapse: collapse;
                text-align: left;
                font-size: 13px;
            }
            th {
                background: var(--slate-100);
                color: var(--slate-600);
                font-weight: 700;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                padding: 10px 12px;
            }
            td {
                padding: 10px 12px;
                border-top: 1px solid var(--slate-200);
                color: var(--slate-800);
            }
            tr:nth-child(even) { background: #fafafa; }
            .badge-item {
                font-size: 10px;
                font-weight: 700;
                padding: 2px 6px;
                border-radius: 4px;
                background: #e2e8f0;
                color: #334155;
            }

            /* Resumo Financeiro */
            .financial-card {
                background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
                border-radius: 14px;
                padding: 16px;
                border: 1px solid var(--slate-200);
                margin-top: 10px;
            }
            .financial-row {
                display: flex;
                justify-content: space-between;
                font-size: 13px;
                color: var(--slate-600);
                margin-bottom: 6px;
            }
            .financial-total {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 16px;
                font-weight: 800;
                color: var(--slate-900);
                padding-top: 10px;
                margin-top: 8px;
                border-top: 2px dashed var(--slate-200);
            }
            .total-badge {
                font-size: 20px;
                color: #059669;
                font-weight: 900;
            }

            /* Galeria de Fotos */
            .photos-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
                gap: 10px;
                margin-top: 10px;
            }
            .photo-card {
                border-radius: 10px;
                overflow: hidden;
                border: 1px solid var(--slate-200);
                background: var(--slate-50);
                text-align: center;
            }
            .photo-card img {
                width: 100%;
                height: 100px;
                object-fit: cover;
                display: block;
            }
            .photo-caption {
                padding: 6px;
                font-size: 11px;
                font-weight: 600;
                color: var(--slate-600);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            /* Formulário de Decisão */
            .decision-container {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px;
                margin-bottom: 16px;
            }
            .decision-option {
                position: relative;
                cursor: pointer;
            }
            .decision-option input[type="radio"] {
                position: absolute;
                opacity: 0;
            }
            .decision-card {
                border: 2px solid var(--slate-200);
                border-radius: 14px;
                padding: 16px 12px;
                text-align: center;
                transition: all 0.2s ease;
                background: white;
            }
            .decision-icon { font-size: 28px; margin-bottom: 6px; }
            .decision-label { font-size: 14px; font-weight: 800; }
            
            /* Estilo selecionado Aprovar */
            .decision-option input[type="radio"]:checked + .card-approve {
                border-color: #10b981;
                background: #ecfdf5;
                box-shadow: 0 4px 12px rgba(16, 185, 129, 0.2);
            }
            .card-approve .decision-label { color: #047857; }

            /* Estilo selecionado Reprovar */
            .decision-option input[type="radio"]:checked + .card-reject {
                border-color: #ef4444;
                background: #fef2f2;
                box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
            }
            .card-reject .decision-label { color: #b91c1c; }

            label {
                display: block;
                font-size: 12px;
                font-weight: 700;
                color: var(--slate-700);
                margin: 12px 0 6px 0;
                text-transform: uppercase;
                letter-spacing: 0.3px;
            }
            input[type="text"], textarea {
                width: 100%;
                padding: 12px 14px;
                border: 1px solid var(--slate-200);
                border-radius: 10px;
                font-size: 14px;
                outline: none;
                transition: border 0.2s;
                background: var(--slate-50);
            }
            input[type="text"]:focus, textarea:focus {
                border-color: var(--primary);
                background: white;
            }

            .btn-confirm {
                width: 100%;
                background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
                color: white;
                border: none;
                padding: 16px;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 800;
                cursor: pointer;
                box-shadow: 0 6px 16px rgba(2, 132, 199, 0.3);
                margin-top: 20px;
                transition: transform 0.1s;
            }
            .btn-confirm:active { transform: scale(0.99); }
            
            .security-notice {
                text-align: center;
                font-size: 11px;
                color: var(--slate-600);
                margin-top: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Cabeçalho Executivo -->
            <div class="header-card">
                <span class="os-tag">
                    <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:#38bdf8;"></span>
                    ORDEM DE SERVIÇO #{{ task_num }}
                </span>
                <h1 class="header-title">Resumo do Atendimento</h1>
                <p class="header-subtitle">Validação de serviços técnicos em campo • Protocolo #{{ tx_id }}</p>
            </div>

            <!-- Dados Gerais do Atendimento -->
            <div class="section-card">
                <div class="section-title">🏢 Dados do Atendimento e Local</div>
                <div class="data-grid">
                    <div class="data-item">
                        <div class="data-label">Cliente / Unidade</div>
                        <div class="data-value">{{ detalhes.cliente }}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">Local / Setor</div>
                        <div class="data-value">{{ detalhes.local }}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">Equipamento / Ativo</div>
                        <div class="data-value">{{ detalhes.equipamento }} {% if detalhes.serie %}(S/N: {{ detalhes.serie }}){% endif %}</div>
                    </div>
                    <div class="data-item">
                        <div class="data-label">Técnico Responsável</div>
                        <div class="data-value">{{ tecnico }}</div>
                    </div>
                </div>
            </div>

            <!-- Laudo Técnico do Serviço -->
            <div class="section-card">
                <div class="section-title">🔧 Diagnóstico e Execução Técnica</div>
                
                <div class="diag-box">
                    <div class="label">⚠️ Defeito Constatado / Sintoma</div>
                    <div class="text">{{ detalhes.defeito }}</div>
                </div>

                <div class="solution-box">
                    <div class="label">🛠️ Serviço Executado / Solução Aplicada</div>
                    <div class="text">{{ detalhes.servico }}</div>
                </div>

                {% if detalhes.observacoes %}
                <div style="background:var(--slate-50); border:1px solid var(--slate-200); border-radius:10px; padding:10px 12px; margin-top:10px; font-size:12px; color:var(--slate-600);">
                    <strong style="color:var(--slate-800);">Observações Técnicas Adicionais:</strong><br>
                    {{ detalhes.observacoes }}
                </div>
                {% endif %}
            </div>

            <!-- Tabela de Itens e Peças (Se Houver) -->
            {% if detalhes.tem_itens %}
            <div class="section-card">
                <div class="section-title">📦 Peças, Materiais e Serviços Utilizados</div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Item / Descrição</th>
                                <th style="text-align: center;">Qtd</th>
                                <th style="text-align: right;">Unitário</th>
                                <th style="text-align: right;">Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for it in detalhes.itens %}
                            <tr>
                                <td>
                                    <strong>{{ it.nome }}</strong>
                                    <span class="badge-item">{{ it.tipo }}</span>
                                </td>
                                <td style="text-align: center;">{{ it.qtd }}</td>
                                <td style="text-align: right;">R$ {{ "%.2f"|format(it.unitario) }}</td>
                                <td style="text-align: right; font-weight:700;">R$ {{ "%.2f"|format(it.total) }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <!-- Resumo Financeiro -->
                <div class="financial-card">
                    {% if detalhes.subtotal > 0 %}
                    <div class="financial-row">
                        <span>Subtotal de Peças e Serviços:</span>
                        <strong>R$ {{ detalhes.subtotal_fmt }}</strong>
                    </div>
                    {% endif %}

                    {% if detalhes.desconto > 0 %}
                    <div class="financial-row" style="color: #ef4444;">
                        <span>Desconto Concedido:</span>
                        <strong>- R$ {{ detalhes.desconto_fmt }}</strong>
                    </div>
                    {% endif %}

                    <div class="financial-total">
                        <span>VALOR TOTAL AUTORIZADO:</span>
                        <span class="total-badge">R$ {{ detalhes.valor_total_fmt }}</span>
                    </div>
                </div>
            </div>
            {% elif detalhes.valor_total > 0 %}
            <!-- Caso não tenha tabela mas tenha valor total -->
            <div class="section-card">
                <div class="section-title">💰 Valor do Atendimento</div>
                <div class="financial-card">
                    <div class="financial-total">
                        <span>VALOR TOTAL DO SERVIÇO:</span>
                        <span class="total-badge">R$ {{ detalhes.valor_total_fmt }}</span>
                    </div>
                </div>
            </div>
            {% endif %}

            <!-- Evidências Fotográficas (Se Houver) -->
            {% if detalhes.tem_fotos %}
            <div class="section-card">
                <div class="section-title">📷 Evidências Fotográficas de Campo</div>
                <div class="photos-grid">
                    {% for foto in detalhes.fotos %}
                    <div class="photo-card">
                        <a href="{{ foto.url }}" target="_blank">
                            <img src="{{ foto.url }}" alt="{{ foto.titulo }}" loading="lazy">
                        </a>
                        <div class="photo-caption">{{ foto.titulo }}</div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            <!-- Formulário de Decisão e Assinatura Digital -->
            <div class="section-card" style="border-top: 4px solid var(--primary);">
                <div class="section-title">✍️ Parecer e Assinatura Digital</div>

                <form method="POST" id="form-aprovacao" onsubmit="return validarEnvio()">
                    <div class="decision-container">
                        <label class="decision-option">
                            <input type="radio" name="decisao" value="APROVADO" checked onchange="toggleJustificativa()">
                            <div class="decision-card card-approve">
                                <div class="decision-icon">✅</div>
                                <div class="decision-label">Aprovar Serviço</div>
                            </div>
                        </label>

                        <label class="decision-option">
                            <input type="radio" name="decisao" value="REPROVADO" onchange="toggleJustificativa()">
                            <div class="decision-card card-reject">
                                <div class="decision-icon">❌</div>
                                <div class="decision-label">Reprovar / Ajustes</div>
                            </div>
                        </label>
                    </div>

                    <label for="nome_respondente">Seu Nome Completo *</label>
                    <input type="text" id="nome_respondente" name="nome_respondente" value="{{ nome_aprovador }}" required placeholder="Ex: Roberto Carlos da Silva">

                    <label for="cargo_respondente">Cargo / Documento (CPF ou Matrícula)</label>
                    <input type="text" id="cargo_respondente" name="cargo_respondente" placeholder="Ex: Supervisor Operacional ou 123.456.789-00">

                    <label for="observacao" id="label-obs">Observações / Parecer Técnico</label>
                    <textarea id="observacao" name="observacao" rows="3" placeholder="Insira aqui observações, notas de liberação ou apontamentos técnicos..."></textarea>

                    <button type="submit" class="btn-confirm" id="btn-submit">
                        Confirmar e Transmitir para o Técnico
                    </button>

                    <div class="security-notice">
                        🔒 Assinatura digital com trilha de auditoria e registro de IP
                    </div>
                </form>
            </div>
        </div>

        <script>
            function toggleJustificativa() {
                const isReprovado = document.querySelector('input[name="decisao"]:checked').value === "REPROVADO";
                const labelObs = document.getElementById("label-obs");
                const txtObs = document.getElementById("observacao");
                const btnSubmit = document.getElementById("btn-submit");

                if (isReprovado) {
                    labelObs.innerHTML = "Justificativa da Reprovação (Obrigatória) *";
                    labelObs.style.color = "#dc2626";
                    txtObs.required = true;
                    txtObs.placeholder = "Descreva detalhadamente o motivo da reprovação para que o técnico possa corrigir...";
                    btnSubmit.style.background = "linear-gradient(135deg, #dc2626 0%, #991b1b 100%)";
                    btnSubmit.innerText = "Registrar Reprovação da OS";
                } else {
                    labelObs.innerHTML = "Observações / Parecer Técnico";
                    labelObs.style.color = "var(--slate-700)";
                    txtObs.required = false;
                    txtObs.placeholder = "Insira aqui observações, notas de liberação ou apontamentos técnicos...";
                    btnSubmit.style.background = "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)";
                    btnSubmit.innerText = "Confirmar e Transmitir para o Técnico";
                }
            }

            function validarEnvio() {
                const nome = document.getElementById("nome_respondente").value.trim();
                if (!nome) {
                    alert("Por favor, preencha o seu nome completo.");
                    return false;
                }
                const isReprovado = document.querySelector('input[name="decisao"]:checked').value === "REPROVADO";
                const obs = document.getElementById("observacao").value.trim();
                if (isReprovado && !obs) {
                    alert("Para reprovar a ordem de serviço, é obrigatório preencher a justificativa.");
                    document.getElementById("observacao").focus();
                    return false;
                }
                document.getElementById("btn-submit").disabled = true;
                document.getElementById("btn-submit").innerText = "Transmitindo decisão...";
                return true;
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(
        html_resumo_executivo,
        tx_id=tx_id,
        task_num=row["task_num"],
        tecnico=row["tecnico"],
        nome_aprovador=row["nome_aprovador"],
        detalhes=detalhes
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
        "cargo_respondente": row["cargo_respondente"] if "cargo_respondente" in row.keys() else "",
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
        cargo_resp = row["cargo_respondente"] if "cargo_respondente" in row.keys() else ""
        obs = row["observacao"] or "Sem observações."
        data_resp = row["respondido_em"]

        detalhes = {}
        if row["detalhes_json"]:
            try:
                detalhes = json.loads(row["detalhes_json"])
            except Exception:
                pass

        valor_aprovado = detalhes.get("valor_total_fmt") or ""

        campos = {
            "TXID_EXTERNO": tx_id,
            "STATUS_EXTERNO": decisao,
            "NOME_APROVADOR_EXT": nome_resp,
            "CARGO_APROVADOR_EXT": cargo_resp,
            "OBS_EXTERNA": obs,
            "DATA_HORA_EXT": data_resp,
        }
        if valor_aprovado:
            campos["VALOR_APROVADO_EXT"] = valor_aprovado

        sucesso = (decisao == "APROVADO")
        msg_popup = (
            f"Retorno da Aprovação Recebido!\n\n"
            f"Decisão: {decisao}\n"
            f"Por: {nome_resp}"
            + (f" ({cargo_resp})" if cargo_resp else "") + "\n"
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

        root = _parse_xml(xml_data)

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
