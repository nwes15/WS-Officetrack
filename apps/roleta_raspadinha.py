from flask import request, Response, jsonify, render_template_string
from lxml import etree
import logging
import sqlite3
import uuid
import os
import re
import random
import requests
from datetime import datetime
from io import BytesIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "premios_gamificacao.db")


def _parse_xml(xml_data):
    """Faz parse seguro de XML vindo como str (com ou sem declaração <?xml ...?>)."""
    limpo = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", xml_data, count=1, flags=re.IGNORECASE)
    parser = etree.XMLParser(recover=True)
    return etree.parse(BytesIO(limpo.encode("utf-8")), parser).getroot()

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL") or os.getenv("EVOLUTION_URL") or "https://whatsapp.cloudwesns.com.br"
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")

PREMIOS = [
    {"id": "cafe",     "label": "Vale-Café",      "xp": 30,  "peso": 22, "cor": "#f59e0b", "emoji": "☕", "raridade": "Comum"},
    {"id": "turbo",    "label": "+100 XP Turbo",  "xp": 100, "peso": 18, "cor": "#3b82f6", "emoji": "⚡", "raridade": "Raro"},
    {"id": "almoco",   "label": "Vale-Lanche",    "xp": 50,  "peso": 15, "cor": "#10b981", "emoji": "🍔", "raridade": "Incomum"},
    {"id": "epico",    "label": "+250 XP Épico",  "xp": 250, "peso": 8,  "cor": "#8b5cf6", "emoji": "💎", "raridade": "Épico"},
    {"id": "combo",    "label": "+75 XP Combo",   "xp": 75,  "peso": 18, "cor": "#ec4899", "emoji": "🔥", "raridade": "Incomum"},
    {"id": "folga",    "label": "Saída 1h Cedo",  "xp": 120, "peso": 5,  "cor": "#ef4444", "emoji": "🎁", "raridade": "Lendário"},
    {"id": "ouro",     "label": "+150 XP Ouro",   "xp": 150, "peso": 10, "cor": "#eab308", "emoji": "🌟", "raridade": "Raro"},
    {"id": "bonus50",  "label": "Bônus R$ 50",    "xp": 200, "peso": 4,  "cor": "#06b6d4", "emoji": "🏆", "raridade": "Lendário"},
]


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rodadas_premio (
                tx_id TEXT PRIMARY KEY,
                task_num TEXT,
                tecnico TEXT,
                nome_tecnico TEXT,
                tel_whatsapp TEXT DEFAULT '',
                status TEXT DEFAULT 'PENDENTE',
                modo TEXT DEFAULT '',
                premio_id TEXT DEFAULT '',
                premio_label TEXT DEFAULT '',
                premio_emoji TEXT DEFAULT '',
                premio_raridade TEXT DEFAULT '',
                fatia_index INTEGER DEFAULT 0,
                xp_ganho INTEGER DEFAULT 0,
                voucher_code TEXT DEFAULT '',
                criado_em TEXT,
                jogado_em TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ranking_tecnicos (
                tecnico TEXT PRIMARY KEY,
                nome_tecnico TEXT,
                xp_total INTEGER DEFAULT 0,
                jogadas INTEGER DEFAULT 0,
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


def _calcular_nivel(xp_total):
    if xp_total >= 1500:
        return "Diamante", "💠", xp_total, 2000
    if xp_total >= 800:
        return "Ouro", "🥇", xp_total, 1500
    if xp_total >= 300:
        return "Prata", "🥈", xp_total, 800
    return "Bronze", "🥉", xp_total, 300


def _obter_ranking_e_perfil(conn, tecnico):
    conn.row_factory = sqlite3.Row
    perfil = conn.execute(
        "SELECT * FROM ranking_tecnicos WHERE tecnico = ?", (tecnico,)
    ).fetchone()
    xp_total = perfil["xp_total"] if perfil else 0
    jogadas = perfil["jogadas"] if perfil else 0

    top = conn.execute(
        "SELECT tecnico, nome_tecnico, xp_total, jogadas FROM ranking_tecnicos ORDER BY xp_total DESC, jogadas DESC LIMIT 5"
    ).fetchall()
    top_list = []
    for idx, r in enumerate(top, start=1):
        niv, emo, _, _ = _calcular_nivel(r["xp_total"])
        top_list.append({
            "pos": idx,
            "tecnico": r["tecnico"],
            "nome": r["nome_tecnico"] or r["tecnico"],
            "xp_total": r["xp_total"],
            "nivel": f"{emo} {niv}",
            "is_me": r["tecnico"] == tecnico,
        })

    nivel, emoji, _, meta_prox = _calcular_nivel(xp_total)
    return {
        "xp_total": xp_total,
        "jogadas": jogadas,
        "nivel": nivel,
        "nivel_emoji": emoji,
        "meta_prox": meta_prox,
        "ranking": top_list,
    }


def _notificar_whatsapp_premio(tel_limpo, nome_tecnico, task_num, premio_texto, voucher_code, xp_ganho, xp_total):
    evo_url = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/") or EVOLUTION_API_URL.strip().rstrip("/")
    evo_key = os.getenv("EVOLUTION_API_KEY", "").strip() or EVOLUTION_API_KEY.strip()
    if not (tel_limpo and len(tel_limpo) >= 10 and evo_key):
        return False

    num_wa = tel_limpo if tel_limpo.startswith("55") else f"55{tel_limpo}"
    msg = (
        f"🎉 *Parabéns, {nome_tecnico}!*\n\n"
        f"Você acabou de girar/raspar na OS *#{task_num}* e ganhou:\n"
        f"🏆 *{premio_texto}*\n\n"
        f"🎟️ *Voucher:* `{voucher_code}`\n"
        f"⚡ *XP da rodada:* +{xp_ganho} XP\n"
        f"📊 *XP Total acumulado:* {xp_total} XP"
    )
    try:
        resp = requests.post(
            f"{evo_url}/send/text",
            headers={"apikey": evo_key, "Content-Type": "application/json"},
            json={"number": num_wa, "text": msg, "linkPreview": False},
            timeout=8,
        )
        logging.info(f"[PREMIO] WhatsApp enviado para {num_wa}: HTTP {resp.status_code}")
        return resp.status_code in (200, 201)
    except Exception as ex:
        logging.warning(f"[PREMIO] Falha ao enviar WhatsApp: {ex}")
        return False


def iniciar_premio():
    """
    1º Passo (Botão no OfficeTrack):
    Abre a tela gamificada (Roleta da Sorte + Raspadinha) via <Action>OpenUrl</Action>.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("Não foi possível ler o XML do formulário.")

        root = _parse_xml(xml_data)

        task_num = root.findtext(".//Task/TaskNum") or "DEMO"
        tecnico = root.findtext(".//Employee/EmployeeNumber") or "TECNICO_DEMO"

        campos_form = {}
        for f in root.findall(".//Field"):
            fid = f.findtext("Id") or f.findtext("ID") or f.findtext("id")
            fval = f.findtext("Value") or ""
            if fid:
                campos_form[fid.strip().upper()] = fval.strip()

        nome_tecnico = (
            campos_form.get("NOME_TECNICO")
            or campos_form.get("TECNICO")
            or campos_form.get("NOME")
            or tecnico
        )

        tel_bruto = (
            campos_form.get("TEL_TECNICO")
            or campos_form.get("WHATSAPP")
            or campos_form.get("TELEFONE")
            or campos_form.get("CELULAR")
            or campos_form.get("TEL_CLIENTE")
            or ""
        )
        tel_limpo = re.sub(r"\D", "", tel_bruto)

        tx_id = str(uuid.uuid4())[:8].upper()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO rodadas_premio
                   (tx_id, task_num, tecnico, nome_tecnico, tel_whatsapp, status, criado_em)
                   VALUES (?, ?, ?, ?, ?, 'PENDENTE', ?)""",
                (tx_id, task_num, tecnico, nome_tecnico, tel_limpo, agora),
            )
            conn.commit()

        base_url = _obter_base_url()
        url_jogo = f"{base_url}/premio/{tx_id}"
        url_retorno = f"{base_url}/finalizar_premio/{tx_id}"

        response = etree.Element("Response")
        ret = etree.SubElement(response, "ReturnValue")
        etree.SubElement(ret, "ShortText").text = "Prêmio Liberado"
        etree.SubElement(ret, "LongText").text = f"Sessão {tx_id}"
        etree.SubElement(ret, "Value").text = "OK"
        etree.SubElement(ret, "Action").text = "OpenUrl"
        etree.SubElement(ret, "Url").text = url_jogo
        etree.SubElement(ret, "WebService").text = url_retorno

        xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return Response(xml_str, content_type="application/xml; charset=utf-8")

    except Exception as e:
        logging.error(f"Erro em iniciar_premio: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao abrir gamificação: {str(e)}")


def tela_premio(tx_id):
    """Tela mobile gamificada com Roleta da Sorte + Raspadinha Instantânea."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM rodadas_premio WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
        if not row:
            return "<h2>Sessão de prêmio não encontrada.</h2>", 404
        perfil = _obter_ranking_e_perfil(conn, row["tecnico"])

    dados_iniciais = {
        "tx_id": row["tx_id"],
        "task_num": row["task_num"],
        "tecnico": row["tecnico"],
        "nome_tecnico": row["nome_tecnico"],
        "status": row["status"],
        "modo": row["modo"],
        "premio_label": row["premio_label"],
        "premio_emoji": row["premio_emoji"],
        "premio_raridade": row["premio_raridade"],
        "fatia_index": row["fatia_index"],
        "xp_ganho": row["xp_ganho"],
        "voucher_code": row["voucher_code"],
        "premios": [{"label": p["label"], "xp": p["xp"], "cor": p["cor"], "emoji": p["emoji"], "raridade": p["raridade"]} for p in PREMIOS],
        "perfil": perfil,
    }

    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>OfficeTrack Rewards • Roleta & Raspadinha</title>
<style>
  :root {
    --bg: #0b0d17;
    --card: #15192b;
    --card2: #1c223b;
    --border: rgba(255,255,255,0.09);
    --gold: #fbbf24;
    --gold-dark: #d97706;
    --accent: #8b5cf6;
    --green: #10b981;
    --text: #f8fafc;
    --muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(circle at top, #1e1b4b 0%, var(--bg) 55%);
    color: var(--text);
    min-height: 100vh;
    padding: 14px 14px 28px;
    overflow-x: hidden;
  }
  #confetti {
    position: fixed; inset: 0; pointer-events: none; z-index: 99;
  }
  .container { max-width: 440px; margin: 0 auto; position: relative; z-index: 2; }

  .topbar {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 16px; padding: 12px 14px; margin-bottom: 12px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.35);
  }
  .user-info .name { font-weight: 700; font-size: 15px; display: flex; align-items: center; gap: 6px; }
  .user-info .sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .xp-badge {
    background: linear-gradient(135deg, #f59e0b, #ea580c);
    color: #fff; font-weight: 800; font-size: 13px;
    padding: 7px 12px; border-radius: 999px;
    box-shadow: 0 4px 12px rgba(245,158,11,0.35);
    white-space: nowrap;
  }

  .xp-bar-wrap {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 10px 14px; margin-bottom: 14px;
  }
  .xp-bar-head {
    display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-bottom: 6px;
  }
  .xp-bar-head strong { color: var(--gold); }
  .xp-track { height: 8px; background: #0f172a; border-radius: 999px; overflow: hidden; }
  .xp-fill {
    height: 100%; width: 0%;
    background: linear-gradient(90deg, #fbbf24, #f97316, #ec4899);
    border-radius: 999px; transition: width 0.8s cubic-bezier(.22,1,.36,1);
  }

  .tabs {
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
    background: var(--card); padding: 6px; border-radius: 14px;
    border: 1px solid var(--border); margin-bottom: 14px;
  }
  .tab-btn {
    border: none; border-radius: 10px; padding: 11px 8px;
    font-weight: 700; font-size: 14px; cursor: pointer;
    background: transparent; color: var(--muted); transition: all 0.2s;
  }
  .tab-btn.active {
    background: linear-gradient(135deg, #7c3aed, #db2777);
    color: #fff; box-shadow: 0 4px 14px rgba(124,58,237,0.4);
  }

  .stage {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 22px; padding: 18px 14px; text-align: center;
    box-shadow: 0 18px 40px rgba(0,0,0,0.45);
    margin-bottom: 14px;
  }
  .stage-title { font-size: 18px; font-weight: 800; margin-bottom: 4px; }
  .stage-sub { font-size: 13px; color: var(--muted); margin-bottom: 16px; }

  /* ROLETA */
  .wheel-wrap {
    position: relative; width: 290px; height: 290px; margin: 0 auto 16px;
  }
  .wheel-pointer {
    position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
    width: 0; height: 0; z-index: 5;
    border-left: 14px solid transparent;
    border-right: 14px solid transparent;
    border-top: 26px solid var(--gold);
    filter: drop-shadow(0 4px 6px rgba(0,0,0,0.6));
  }
  .wheel-ring {
    width: 100%; height: 100%; border-radius: 50%;
    padding: 8px;
    background: conic-gradient(from 0deg, #fbbf24, #f59e0b, #fde68a, #d97706, #fbbf24);
    box-shadow: 0 0 32px rgba(251,191,36,0.28), inset 0 0 10px rgba(0,0,0,0.5);
    position: relative;
  }
  #wheelCanvas { width: 100%; height: 100%; border-radius: 50%; display: block; }
  .wheel-hub {
    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 52px; height: 52px; border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, #fff, #fbbf24 55%, #b45309);
    border: 4px solid #15192b;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.6); z-index: 4;
  }

  .btn-play {
    width: 100%; border: none; border-radius: 14px; padding: 15px;
    font-size: 16px; font-weight: 800; letter-spacing: 0.4px;
    color: #111827; cursor: pointer;
    background: linear-gradient(135deg, #fde047, #f59e0b);
    box-shadow: 0 8px 22px rgba(245,158,11,0.4);
    transition: transform 0.12s, opacity 0.2s;
  }
  .btn-play:active { transform: scale(0.97); }
  .btn-play:disabled { opacity: 0.55; cursor: not-allowed; }

  /* RASPADINHA */
  .scratch-card {
    position: relative; width: 100%; max-width: 310px; height: 185px;
    margin: 0 auto 12px; border-radius: 18px; overflow: hidden;
    border: 2px solid rgba(251,191,36,0.45);
    background: radial-gradient(circle at center, #312e81, #1e1b4b);
    box-shadow: 0 12px 26px rgba(0,0,0,0.45);
    user-select: none;
  }
  .scratch-under {
    position: absolute; inset: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 16px;
  }
  .scratch-emoji { font-size: 46px; margin-bottom: 6px; }
  .scratch-prize { font-size: 21px; font-weight: 900; color: var(--gold); }
  .scratch-sub { font-size: 12px; color: #cbd5e1; margin-top: 4px; }
  #scratchCanvas {
    position: absolute; inset: 0; width: 100%; height: 100%;
    touch-action: none; cursor: crosshair; transition: opacity 0.45s;
  }
  .scratch-hint { font-size: 12px; color: var(--muted); }

  /* RESULTADO */
  .result-card {
    display: none;
    background: linear-gradient(145deg, #1e1b4b, #311042);
    border: 1px solid rgba(251,191,36,0.5);
    border-radius: 20px; padding: 18px 14px; text-align: center;
    margin-bottom: 14px;
    animation: popIn 0.45s cubic-bezier(.17,.89,.32,1.28);
  }
  .result-card.show { display: block; }
  @keyframes popIn {
    from { opacity: 0; transform: scale(0.88); }
    to { opacity: 1; transform: scale(1); }
  }
  .res-badge {
    display: inline-block; font-size: 11px; font-weight: 800; text-transform: uppercase;
    padding: 4px 10px; border-radius: 999px; background: rgba(251,191,36,0.2); color: var(--gold);
    margin-bottom: 8px;
  }
  .res-emoji { font-size: 48px; margin-bottom: 4px; }
  .res-title { font-size: 22px; font-weight: 900; color: #fff; margin-bottom: 4px; }
  .res-xp { font-size: 14px; color: #34d399; font-weight: 700; margin-bottom: 12px; }
  .voucher-box {
    background: rgba(0,0,0,0.35); border: 1px dashed rgba(251,191,36,0.6);
    border-radius: 12px; padding: 10px; margin-bottom: 12px;
  }
  .voucher-box span { display: block; font-size: 11px; color: var(--muted); }
  .voucher-box strong { font-size: 18px; letter-spacing: 1.5px; color: var(--gold); }
  .close-tip {
    background: rgba(16,185,129,0.14); border: 1px solid rgba(16,185,129,0.4);
    color: #a7f3d0; font-size: 13px; border-radius: 12px; padding: 10px 12px; line-height: 1.45;
  }

  /* RANKING */
  .rank-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 18px; padding: 14px;
  }
  .rank-title { font-size: 14px; font-weight: 800; margin-bottom: 10px; display: flex; justify-content: space-between; }
  .rank-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 10px; border-radius: 10px; font-size: 13px; margin-bottom: 6px;
    background: var(--card2);
  }
  .rank-row.me { border: 1px solid rgba(251,191,36,0.5); background: rgba(251,191,36,0.08); }
  .rank-left { display: flex; align-items: center; gap: 8px; }
  .rank-pos { width: 22px; font-weight: 800; color: var(--gold); }
  .rank-xp { font-weight: 800; color: #34d399; }

  .hidden { display: none !important; }
</style>
</head>
<body>
<canvas id="confetti"></canvas>

<div class="container">
  <div class="topbar">
    <div class="user-info">
      <div class="name"><span id="lvlEmoji">🥉</span> <span id="userName"></span></div>
      <div class="sub">OS #<span id="taskNum"></span> • Sessão <span id="txLabel"></span></div>
    </div>
    <div class="xp-badge" id="xpBadge">0 XP</div>
  </div>

  <div class="xp-bar-wrap">
    <div class="xp-bar-head">
      <span>Nível: <strong id="lvlName">Bronze</strong></span>
      <span id="xpProgressText">0 / 300 XP</span>
    </div>
    <div class="xp-track"><div class="xp-fill" id="xpFill"></div></div>
  </div>

  <div class="tabs" id="modeTabs">
    <button class="tab-btn active" id="tabRoleta" onclick="trocarModo('roleta')">🎡 Roleta da Sorte</button>
    <button class="tab-btn" id="tabRaspadinha" onclick="trocarModo('raspadinha')">🪙 Raspadinha</button>
  </div>

  <!-- PAINEL ROLETA -->
  <div class="stage" id="panelRoleta">
    <div class="stage-title">Gire e Ganhe na Hora!</div>
    <div class="stage-sub">Meta concluída na OS — toque abaixo para sortear</div>
    <div class="wheel-wrap">
      <div class="wheel-pointer"></div>
      <div class="wheel-ring">
        <canvas id="wheelCanvas" width="560" height="560"></canvas>
      </div>
      <div class="wheel-hub">⚡</div>
    </div>
    <button class="btn-play" id="btnGirar" onclick="girarRoleta()">🎡 GIRAR ROLETA</button>
  </div>

  <!-- PAINEL RASPADINHA -->
  <div class="stage hidden" id="panelRaspadinha">
    <div class="stage-title">Raspadinha Instantânea</div>
    <div class="stage-sub">Passe o dedo na área prateada para revelar seu prêmio</div>
    <div class="scratch-card">
      <div class="scratch-under">
        <div class="scratch-emoji" id="scEmoji">🎁</div>
        <div class="scratch-prize" id="scPrize">Carregando...</div>
        <div class="scratch-sub" id="scSub">Sorteando seu prêmio...</div>
      </div>
      <canvas id="scratchCanvas" width="310" height="185"></canvas>
    </div>
    <div class="scratch-hint" id="scratchHint">Raspe pelo menos 45% para resgatar • <span id="scratchPct">0%</span></div>
  </div>

  <!-- RESULTADO -->
  <div class="result-card" id="resultCard">
    <div class="res-badge" id="resRaridade">PRÊMIO</div>
    <div class="res-emoji" id="resEmoji">🏆</div>
    <div class="res-title" id="resTitle">-</div>
    <div class="res-xp" id="resXp">+0 XP adicionados ao seu perfil</div>
    <div class="voucher-box">
      <span>CÓDIGO DO VOUCHER</span>
      <strong id="resVoucher">OT-0000</strong>
    </div>
    <div class="close-tip">
      ✅ <strong>Tudo salvo no OfficeTrack!</strong><br>
      Agora é só fechar esta janela (no <strong>X</strong> ou Voltar) que o prêmio e o voucher vão aparecer preenchidos direto no formulário.
    </div>
  </div>

  <!-- RANKING -->
  <div class="rank-card">
    <div class="rank-title">
      <span>🏅 Ranking da Equipe (Ao Vivo)</span>
      <span style="color:var(--muted);font-weight:600;font-size:12px;">Top 5</span>
    </div>
    <div id="rankList"></div>
  </div>
</div>

<script>
const INIT = {{ dados_json | safe }};
let state = {
  modo: INIT.modo || 'roleta',
  jogado: INIT.status === 'JOGADO',
  girando: false,
  anguloAtual: 0,
  raspadinhaPronta: false,
  raspadinhaRevelada: false,
  sorteioRaspadinha: null,
  sorteandoRaspadinha: false,
};

document.getElementById('userName').textContent = INIT.nome_tecnico;
document.getElementById('taskNum').textContent = INIT.task_num;
document.getElementById('txLabel').textContent = INIT.tx_id;

function atualizarPerfilUI(perfil) {
  document.getElementById('lvlEmoji').textContent = perfil.nivel_emoji;
  document.getElementById('lvlName').textContent = perfil.nivel;
  document.getElementById('xpBadge').textContent = perfil.xp_total + ' XP';
  document.getElementById('xpProgressText').textContent = perfil.xp_total + ' / ' + perfil.meta_prox + ' XP';
  const pct = Math.min(100, Math.round((perfil.xp_total / perfil.meta_prox) * 100));
  document.getElementById('xpFill').style.width = pct + '%';

  const list = document.getElementById('rankList');
  if (!perfil.ranking || perfil.ranking.length === 0) {
    list.innerHTML = '<div style="font-size:12px;color:#94a3b8;">Jogue para estrear o ranking da equipe!</div>';
    return;
  }
  list.innerHTML = perfil.ranking.map(r => `
    <div class="rank-row ${r.is_me ? 'me' : ''}">
      <div class="rank-left">
        <span class="rank-pos">#${r.pos}</span>
        <span>${escapeHtml(r.nome)} <small style="color:#94a3b8">(${escapeHtml(r.nivel)})</small></span>
      </div>
      <span class="rank-xp">${r.xp_total} XP</span>
    </div>
  `).join('');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

atualizarPerfilUI(INIT.perfil);

// Web Audio API (cliques e fanfarra sem arquivos externos)
let audioCtx = null;
function playTick() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.type = 'triangle';
    o.frequency.setValueAtTime(680, audioCtx.currentTime);
    o.frequency.exponentialRampToValueAtTime(220, audioCtx.currentTime + 0.03);
    g.gain.setValueAtTime(0.08, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.035);
    o.connect(g); g.connect(audioCtx.destination);
    o.start(); o.stop(audioCtx.currentTime + 0.04);
  } catch (e) {}
}

function playWin() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) => {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.type = 'sine';
      const t = audioCtx.currentTime + i * 0.09;
      o.frequency.setValueAtTime(freq, t);
      g.gain.setValueAtTime(0.12, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.35);
      o.connect(g); g.connect(audioCtx.destination);
      o.start(t); o.stop(t + 0.36);
    });
  } catch (e) {}
}

// Desenho da Roleta
const premios = INIT.premios;
const numFatias = premios.length;
const arc = (Math.PI * 2) / numFatias;

function desenharRoleta(rotacaoRad) {
  const canvas = document.getElementById('wheelCanvas');
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  const cx = w / 2, cy = h / 2, r = cx - 4;
  ctx.clearRect(0, 0, w, h);

  premios.forEach((p, i) => {
    const start = rotacaoRad + i * arc - Math.PI / 2;
    const end = start + arc;

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, start, end);
    ctx.closePath();
    ctx.fillStyle = p.cor;
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#0f172a';
    ctx.stroke();

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(start + arc / 2);
    ctx.textAlign = 'right';
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 21px sans-serif';
    ctx.shadowColor = 'rgba(0,0,0,0.55)';
    ctx.shadowBlur = 4;
    ctx.fillText(p.emoji + ' ' + p.label, r - 24, 7);
    ctx.restore();
  });
}

desenharRoleta(0);

function trocarModo(modo) {
  if (state.girando || state.jogado) return;
  state.modo = modo;
  document.getElementById('tabRoleta').classList.toggle('active', modo === 'roleta');
  document.getElementById('tabRaspadinha').classList.toggle('active', modo === 'raspadinha');
  document.getElementById('panelRoleta').classList.toggle('hidden', modo !== 'roleta');
  document.getElementById('panelRaspadinha').classList.toggle('hidden', modo !== 'raspadinha');
  if (modo === 'raspadinha' && !state.raspadinhaPronta) {
    inicializarRaspadinha();
  }
}

async function solicitarSorteio(modo) {
  const res = await fetch(`/api/premio/${INIT.tx_id}/jogar`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({modo})
  });
  return await res.json();
}

async function girarRoleta() {
  if (state.girando || state.jogado) return;
  state.girando = true;
  document.getElementById('btnGirar').disabled = true;

  let data;
  try {
    data = await solicitarSorteio('roleta');
  } catch (e) {
    state.girando = false;
    document.getElementById('btnGirar').disabled = false;
    alert('Erro de conexão ao sortear. Tente novamente.');
    return;
  }

  // O ponteiro fica no topo (-PI/2). O centro da fatia i começa em i*arc + arc/2 - PI/2.
  // Para alinhar a fatia i no topo, rotacaoFinal deve satisfazer: rotacaoFinal + i*arc + arc/2 == 0 (mod 2*PI).
  const targetIdx = data.fatia_index;
  const voltas = 6 * Math.PI * 2;
  const jitter = (Math.random() - 0.5) * (arc * 0.45);
  const targetMod = (-targetIdx * arc - arc / 2 + jitter) % (Math.PI * 2);
  const destino = voltas + (targetMod < 0 ? targetMod + Math.PI * 2 : targetMod);

  const duracao = 4600;
  const inicio = performance.now();
  let lastSlice = -1;

  function animar(agora) {
    const t = Math.min(1, (agora - inicio) / duracao);
    const ease = 1 - Math.pow(1 - t, 4.5);
    const ang = destino * ease;
    state.anguloAtual = ang;
    desenharRoleta(ang);

    const sliceNow = Math.floor(((ang % (Math.PI * 2)) / arc));
    if (sliceNow !== lastSlice) {
      lastSlice = sliceNow;
      playTick();
    }

    if (t < 1) {
      requestAnimationFrame(animar);
    } else {
      state.girando = false;
      state.jogado = true;
      mostrarResultado(data);
    }
  }
  requestAnimationFrame(animar);
}

// RASPADINHA
function inicializarRaspadinha() {
  state.raspadinhaPronta = true;
  const canvas = document.getElementById('scratchCanvas');
  const ctx = canvas.getContext('2d');

  // Camada metálica
  const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
  grad.addColorStop(0, '#94a3b8');
  grad.addColorStop(0.5, '#e2e8f0');
  grad.addColorStop(1, '#64748b');
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = '#1e293b';
  ctx.font = 'bold 18px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('✨ RASPE AQUI ✨', canvas.width / 2, canvas.height / 2 - 4);
  ctx.font = '13px sans-serif';
  ctx.fillText('Descubra seu prêmio instantâneo', canvas.width / 2, canvas.height / 2 + 20);

  let raspando = false;

  async function garantirSorteio() {
    if (state.sorteioRaspadinha || state.sorteandoRaspadinha) return;
    state.sorteandoRaspadinha = true;
    try {
      const data = await solicitarSorteio('raspadinha');
      state.sorteioRaspadinha = data;
      document.getElementById('scEmoji').textContent = data.premio_emoji;
      document.getElementById('scPrize').textContent = data.premio_label;
      document.getElementById('scSub').textContent = `${data.premio_raridade} • +${data.xp_ganho} XP`;
    } finally {
      state.sorteandoRaspadinha = false;
    }
  }

  function raspar(clientX, clientY) {
    if (state.raspadinhaRevelada) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * canvas.width;
    const y = ((clientY - rect.top) / rect.height) * canvas.height;
    ctx.globalCompositeOperation = 'destination-out';
    ctx.beginPath();
    ctx.arc(x, y, 22, 0, Math.PI * 2);
    ctx.fill();
  }

  function checarProgresso() {
    if (state.raspadinhaRevelada) return;
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let apagados = 0;
    const totalAmostras = Math.floor(img.length / 16);
    for (let i = 3; i < img.length; i += 16) {
      if (img[i] < 128) apagados++;
    }
    const pct = Math.min(100, Math.round((apagados / totalAmostras) * 100));
    document.getElementById('scratchPct').textContent = pct + '%';
    if (pct >= 45 && state.sorteioRaspadinha) {
      state.raspadinhaRevelada = true;
      state.jogado = true;
      canvas.style.opacity = '0';
      setTimeout(() => canvas.style.display = 'none', 450);
      document.getElementById('scratchHint').textContent = '🎉 Prêmio revelado!';
      mostrarResultado(state.sorteioRaspadinha);
    }
  }

  canvas.addEventListener('pointerdown', (e) => {
    raspando = true;
    canvas.setPointerCapture(e.pointerId);
    garantirSorteio();
    raspar(e.clientX, e.clientY);
    checarProgresso();
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!raspando) return;
    raspar(e.clientX, e.clientY);
    checarProgresso();
  });
  canvas.addEventListener('pointerup', () => { raspando = false; checarProgresso(); });
  canvas.addEventListener('pointercancel', () => { raspando = false; });
}

function mostrarResultado(data) {
  playWin();
  soltarConfetes();
  document.getElementById('modeTabs').classList.add('hidden');
  document.getElementById('resRaridade').textContent = (data.premio_raridade || 'PRÊMIO').toUpperCase();
  document.getElementById('resEmoji').textContent = data.premio_emoji || '🏆';
  document.getElementById('resTitle').textContent = data.premio_label;
  document.getElementById('resXp').textContent = `+${data.xp_ganho} XP adicionados ao seu perfil!`;
  document.getElementById('resVoucher').textContent = data.voucher_code;
  document.getElementById('resultCard').classList.add('show');
  if (data.perfil) atualizarPerfilUI(data.perfil);
}

// CONFETES
function soltarConfetes() {
  const c = document.getElementById('confetti');
  c.width = window.innerWidth;
  c.height = window.innerHeight;
  const ctx = c.getContext('2d');
  const cores = ['#fbbf24', '#ec4899', '#8b5cf6', '#10b981', '#38bdf8'];
  const pecas = Array.from({length: 90}, () => ({
    x: Math.random() * c.width,
    y: -20 - Math.random() * 140,
    vx: (Math.random() - 0.5) * 4,
    vy: 2.5 + Math.random() * 4.5,
    s: 5 + Math.random() * 6,
    r: Math.random() * Math.PI * 2,
    vr: (Math.random() - 0.5) * 0.2,
    cor: cores[Math.floor(Math.random() * cores.length)]
  }));
  let frames = 0;
  function tick() {
    ctx.clearRect(0, 0, c.width, c.height);
    pecas.forEach(p => {
      p.x += p.vx; p.y += p.vy; p.r += p.vr; p.vy += 0.05;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.r);
      ctx.fillStyle = p.cor;
      ctx.fillRect(-p.s/2, -p.s/2, p.s, p.s * 0.65);
      ctx.restore();
    });
    frames++;
    if (frames < 170) requestAnimationFrame(tick);
    else ctx.clearRect(0, 0, c.width, c.height);
  }
  requestAnimationFrame(tick);
}

// Se reabrir já jogado, restaura estado na hora
if (state.jogado) {
  if (INIT.modo === 'raspadinha') {
    document.getElementById('tabRaspadinha').classList.add('active');
    document.getElementById('tabRoleta').classList.remove('active');
    document.getElementById('panelRoleta').classList.add('hidden');
    document.getElementById('panelRaspadinha').classList.remove('hidden');
    document.getElementById('scEmoji').textContent = INIT.premio_emoji;
    document.getElementById('scPrize').textContent = INIT.premio_label;
    document.getElementById('scSub').textContent = `${INIT.premio_raridade} • +${INIT.xp_ganho} XP`;
    document.getElementById('scratchCanvas').style.display = 'none';
    document.getElementById('scratchHint').textContent = '🎉 Prêmio já resgatado nesta rodada!';
  } else {
    document.getElementById('btnGirar').disabled = true;
    document.getElementById('btnGirar').textContent = '✅ RODADA CONCLUÍDA';
  }
  mostrarResultado(INIT);
}
</script>
</body>
</html>
"""
    import json
    return render_template_string(html, dados_json=json.dumps(dados_iniciais, ensure_ascii=False))


def jogar_premio_api(tx_id):
    """Sorteia o prêmio no servidor e registra XP/voucher no SQLite."""
    payload = request.get_json(silent=True) or {}
    modo = (payload.get("modo") or "roleta").strip().lower()
    if modo not in ("roleta", "raspadinha"):
        modo = "roleta"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM rodadas_premio WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
        if not row:
            return jsonify({"error": "Sessão não encontrada"}), 404

        if row["status"] == "JOGADO":
            perfil = _obter_ranking_e_perfil(conn, row["tecnico"])
            return jsonify({
                "tx_id": row["tx_id"],
                "modo": row["modo"],
                "premio_label": row["premio_label"],
                "premio_emoji": row["premio_emoji"],
                "premio_raridade": row["premio_raridade"],
                "fatia_index": row["fatia_index"],
                "xp_ganho": row["xp_ganho"],
                "voucher_code": row["voucher_code"],
                "perfil": perfil,
            })

        pesos = [p["peso"] for p in PREMIOS]
        indice = random.choices(range(len(PREMIOS)), weights=pesos, k=1)[0]
        escolhido = PREMIOS[indice]
        voucher = f"OT-{tx_id[:4].upper()}-{random.randint(1000, 9999)}"
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        conn.execute(
            """UPDATE rodadas_premio
               SET status='JOGADO', modo=?, premio_id=?, premio_label=?, premio_emoji=?,
                   premio_raridade=?, fatia_index=?, xp_ganho=?, voucher_code=?, jogado_em=?
               WHERE tx_id=?""",
            (
                modo,
                escolhido["id"],
                escolhido["label"],
                escolhido["emoji"],
                escolhido["raridade"],
                indice,
                escolhido["xp"],
                voucher,
                agora,
                tx_id.upper(),
            ),
        )

        conn.execute(
            """INSERT INTO ranking_tecnicos (tecnico, nome_tecnico, xp_total, jogadas, atualizado_em)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(tecnico) DO UPDATE SET
                 nome_tecnico = COALESCE(NULLIF(excluded.nome_tecnico, ''), ranking_tecnicos.nome_tecnico),
                 xp_total = ranking_tecnicos.xp_total + excluded.xp_total,
                 jogadas = ranking_tecnicos.jogadas + 1,
                 atualizado_em = excluded.atualizado_em""",
            (row["tecnico"], row["nome_tecnico"], escolhido["xp"], agora),
        )
        conn.commit()
        perfil = _obter_ranking_e_perfil(conn, row["tecnico"])

    if row["tel_whatsapp"]:
        _notificar_whatsapp_premio(
            row["tel_whatsapp"],
            row["nome_tecnico"],
            row["task_num"],
            f"{escolhido['emoji']} {escolhido['label']}",
            voucher,
            escolhido["xp"],
            perfil["xp_total"],
        )

    return jsonify({
        "tx_id": tx_id.upper(),
        "modo": modo,
        "premio_label": escolhido["label"],
        "premio_emoji": escolhido["emoji"],
        "premio_raridade": escolhido["raridade"],
        "fatia_index": indice,
        "xp_ganho": escolhido["xp"],
        "voucher_code": voucher,
        "perfil": perfil,
    })


def finalizar_premio(tx_id):
    """
    2º Passo Automático (chamado pelo OfficeTrack quando fecha a janela OpenUrl).
    Devolve o prêmio sorteado, XP e voucher diretamente nos campos do formulário.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM rodadas_premio WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
            if not row:
                return _resposta_v2_erro(f"Sessão {tx_id} não encontrada.")
            perfil = _obter_ranking_e_perfil(conn, row["tecnico"])

        if row["status"] != "JOGADO":
            return _resposta_v2_sucesso(
                sucesso=False,
                mensagem=f"Você fechou antes de girar/raspar!\n\nProtocolo: {tx_id}",
                short_text="Não jogado",
                long_text="Abra novamente para girar a roleta ou raspar",
                campos={"TXID_PREMIO": tx_id, "STATUS_PREMIO": "PENDENTE"},
            )

        campos = {
            "TXID_PREMIO": tx_id,
            "STATUS_PREMIO": "RESGATADO",
            "MODO_JOGO": row["modo"].upper(),
            "PREMIO_GANHO": f"{row['premio_emoji']} {row['premio_label']}",
            "XP_GANHO": str(row["xp_ganho"]),
            "XP_TOTAL": str(perfil["xp_total"]),
            "NIVEL_TECNICO": f"{perfil['nivel_emoji']} {perfil['nivel']}",
            "CODIGO_VOUCHER": row["voucher_code"],
        }

        msg = (
            f"Parabéns, {row['nome_tecnico']}!\n\n"
            f"Prêmio: {row['premio_emoji']} {row['premio_label']}\n"
            f"Voucher: {row['voucher_code']}\n"
            f"XP Ganho: +{row['xp_ganho']} XP (Total: {perfil['xp_total']} XP • {perfil['nivel']})"
        )
        return _resposta_v2_sucesso(sucesso=True, mensagem=msg, short_text=row["premio_label"], campos=campos)

    except Exception as e:
        logging.error(f"Erro em finalizar_premio: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao finalizar prêmio: {str(e)}")


def consultar_premio_manual():
    """Plano B caso queira consultar um protocolo TXID_PREMIO manualmente."""
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("XML não encontrado.")
        root = _parse_xml(xml_data)
        tx_node = root.xpath(".//Field[Id='TXID_PREMIO' or ID='TXID_PREMIO']/Value")
        tx_id = tx_node[0].text.strip().upper() if tx_node and tx_node[0].text else ""
        if not tx_id:
            return _resposta_v2_erro("Campo TXID_PREMIO não encontrado ou vazio.")
        return finalizar_premio(tx_id)
    except Exception as e:
        return _resposta_v2_erro(str(e))


def _resposta_v2_sucesso(sucesso, mensagem, short_text, long_text="", campos=None):
    nsmap = {
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsd": "http://www.w3.org/2001/XMLSchema",
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
        long_text="Toque na lixeira para tentar novamente",
    )
