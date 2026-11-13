from flask import request, Response, jsonify, render_template_string
from lxml import etree
import logging
import sqlite3
import os
import re
import uuid
import json
from datetime import datetime
from io import BytesIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "crachas_autorizados.db")


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS crachas (
                codigo TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                cargo TEXT,
                empresa TEXT,
                nivel_acesso TEXT,
                areas_permitidas TEXT,
                status TEXT DEFAULT 'ATIVO',
                validade TEXT,
                foto_avatar TEXT,
                criado_em TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS log_acessos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_cracha TEXT,
                task_num TEXT,
                tecnico_app TEXT,
                resultado TEXT,
                motivo TEXT,
                data_hora TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessoes_scanner (
                tx_id TEXT PRIMARY KEY,
                task_num TEXT,
                tecnico_app TEXT,
                status_leitura TEXT DEFAULT 'AGUARDANDO',
                codigo_lido TEXT DEFAULT '',
                flag_liberacao INTEGER DEFAULT 0,
                dados_resposta_json TEXT DEFAULT '{}',
                criado_em TEXT,
                lido_em TEXT DEFAULT ''
            )
        """)

        # Insere dados de demonstração se a tabela estiver vazia
        cursor = conn.execute("SELECT COUNT(*) FROM crachas")
        if cursor.fetchone()[0] == 0:
            crachas_demo = [
                ("CR-1001", "Wesley Novais", "Especialista de Sistemas", "OfficeTrack Brasil", "Nível 4 (Acesso Total)", "Todas as Áreas, Subestações, CPD, Painéis", "ATIVO", "31/12/2027", "👨‍💻"),
                ("CR-1002", "Carlos Eduardo Silva", "Técnico de Manutenção Jr.", "ClimaTech Engenharia", "Nível 2 (Supervisionado)", "Chillers, Bombas, Climatização", "ATIVO", "15/10/2027", "👷‍♂️"),
                ("CR-1003", "Mariana Souza Santos", "Auditora de Segurança SESMT", "Safety Pro Consultoria", "Nível 3 (Auditoria / Vistoria)", "Todas as Áreas Operacionais", "ATIVO", "20/08/2027", "👩‍💼"),
                ("CR-2001", "Roberto Mendes", "Eletricista Terceirizado", "Volt Facilities", "Nível 2 (Acompanhado)", "Subestação e Painéis Elétricos", "BLOQUEADO", "10/05/2027", "⚠️"),
                ("CR-2002", "Paulo Henrique Lima", "Auxiliar de Instalações", "Alpha Serviços", "Nível 1 (Básico)", "Áreas Comuns", "VENCIDO", "01/01/2026", "❌"),
            ]
            conn.executemany(
                """INSERT INTO crachas (codigo, nome, cargo, empresa, nivel_acesso, areas_permitidas, status, validade, foto_avatar, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                crachas_demo,
            )
        conn.commit()
    try:
        os.chmod(DB_PATH, 0o666)
    except Exception:
        pass


_init_db()


def _parse_xml(xml_data):
    """Faz parse seguro do XML aceitando utf-8 e utf-16 com declaração."""
    limpo = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", xml_data, count=1, flags=re.IGNORECASE)
    parser = etree.XMLParser(recover=True)
    return etree.parse(BytesIO(limpo.encode("utf-8")), parser).getroot()


def _obter_base_url():
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    if "trycloudflare" in host or "onrender.com" in host or (
        "127.0.0.1" not in host and "localhost" not in host and not host.startswith("192.168.")
    ):
        if not request.headers.get("X-Forwarded-Proto"):
            proto = "https"
    return f"{proto}://{host}"


def _consultar_cracha_no_banco(codigo_cracha, task_num="N/A", tecnico_app="N/A"):
    """
    Função central que consulta o crachá e devolve dicionário padronizado.
    """
    codigo_limpo = (codigo_cracha or "").strip().upper()
    # Se vier uma URL ou texto longo de QR code (ex.: https://.../CR-1001), extrai o código
    match_cr = re.search(r"CR-\d{4}", codigo_limpo)
    if match_cr:
        codigo_limpo = match_cr.group(0)

    agora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM crachas WHERE UPPER(codigo) = ?", (codigo_limpo,)).fetchone()

        if not row:
            conn.execute(
                """INSERT INTO log_acessos (codigo_cracha, task_num, tecnico_app, resultado, motivo, data_hora)
                   VALUES (?, ?, ?, 'BLOQUEADO', 'Crachá não cadastrado', ?)""",
                (codigo_limpo, task_num, tecnico_app, agora_str),
            )
            conn.commit()
            return {
                "autorizado": False,
                "codigo": codigo_limpo,
                "status": "NÃO AUTORIZADO",
                "flag_liberacao": "0",
                "nome": "",
                "cargo": "",
                "empresa": "",
                "nivel": "",
                "areas": "",
                "validade": "",
                "avatar": "❌",
                "motivo": f"Crachá '{codigo_limpo}' não encontrado na base de credenciais autorizadas.",
                "validado_em": agora_str,
            }

        status_cracha = row["status"].upper()
        nome = row["nome"]
        cargo = row["cargo"]
        empresa = row["empresa"]
        nivel = row["nivel_acesso"]
        validade = row["validade"]
        areas = row["areas_permitidas"]
        avatar = row["foto_avatar"] or "👤"

        if status_cracha != "ATIVO":
            motivo = f"Crachá inativo: {status_cracha} (Validade: {validade})"
            conn.execute(
                """INSERT INTO log_acessos (codigo_cracha, task_num, tecnico_app, resultado, motivo, data_hora)
                   VALUES (?, ?, ?, 'BLOQUEADO', ?, ?)""",
                (codigo_limpo, task_num, tecnico_app, motivo, agora_str),
            )
            conn.commit()
            return {
                "autorizado": False,
                "codigo": codigo_limpo,
                "status": status_cracha,
                "flag_liberacao": "0",
                "nome": nome,
                "cargo": cargo,
                "empresa": empresa,
                "nivel": nivel,
                "areas": areas,
                "validade": validade,
                "avatar": avatar,
                "motivo": f"Crachá bloqueado ou vencido: {status_cracha} em {validade}.",
                "validado_em": agora_str,
            }

        # AUTORIZADO!
        conn.execute(
            """INSERT INTO log_acessos (codigo_cracha, task_num, tecnico_app, resultado, motivo, data_hora)
               VALUES (?, ?, ?, 'LIBERADO', 'Autorizado com sucesso', ?)""",
            (codigo_limpo, task_num, tecnico_app, agora_str),
        )
        conn.commit()
        return {
            "autorizado": True,
            "codigo": codigo_limpo,
            "status": "AUTORIZADO",
            "flag_liberacao": "1",
            "nome": nome,
            "cargo": cargo,
            "empresa": empresa,
            "nivel": nivel,
            "areas": areas,
            "validade": validade,
            "avatar": avatar,
            "motivo": "Nenhum (Credencial Regular e Ativa)",
            "validado_em": agora_str,
        }


# ==========================================================
# 1. MODO OPENURL: SCANNER DE QR CODE PELA CÂMERA DO CELULAR
# ==========================================================

def iniciar_scanner_cracha():
    """
    Botão no OfficeTrack: 'Escanear Crachá' (Web Service Call)
    Abre o leitor de QR Code usando a câmera do celular via <Action>OpenUrl</Action>.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        task_num = "DEMO-OS"
        tecnico_app = "TECNICO"

        if xml_data:
            root = _parse_xml(xml_data)
            task_num = root.findtext(".//Task/TaskNum") or "DEMO-OS"
            tecnico_app = root.findtext(".//Employee/EmployeeNumber") or "TECNICO"

        tx_id = str(uuid.uuid4())[:8].upper()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO sessoes_scanner (tx_id, task_num, tecnico_app, criado_em)
                   VALUES (?, ?, ?, ?)""",
                (tx_id, task_num, tecnico_app, agora),
            )
            conn.commit()

        base_url = _obter_base_url()
        url_scanner = f"{base_url}/scanner_cracha/{tx_id}"
        url_retorno = f"{base_url}/finalizar_scanner_cracha/{tx_id}"

        response = etree.Element("Response")
        ret = etree.SubElement(response, "ReturnValue")
        etree.SubElement(ret, "ShortText").text = "Abrir Scanner"
        etree.SubElement(ret, "LongText").text = f"Sessão {tx_id}"
        etree.SubElement(ret, "Value").text = "OK"
        etree.SubElement(ret, "Action").text = "OpenUrl"
        etree.SubElement(ret, "Url").text = url_scanner
        etree.SubElement(ret, "WebService").text = url_retorno

        xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return Response(xml_str, content_type="application/xml; charset=utf-8")

    except Exception as e:
        logging.error(f"Erro em iniciar_scanner_cracha: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao abrir scanner de crachá: {str(e)}")


def tela_scanner_cracha(tx_id):
    """
    Tela responsiva de Scanner de QR Code com mira animada, câmera traseira e áudio tátil.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        sessao = conn.execute("SELECT * FROM sessoes_scanner WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
        if not sessao:
            return "<h2>Sessão de scanner não encontrada.</h2>", 404

    base_url = _obter_base_url()

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Leitor de Crachá • OfficeTrack</title>
<!-- Biblioteca rápida e confiável de leitura de QR Code / Código de Barras -->
<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<style>
  :root {{
    --bg: #090d16;
    --card: #131a2b;
    --border: rgba(255,255,255,0.1);
    --green: #10b981;
    --red: #ef4444;
    --blue: #3b82f6;
    --gold: #fbbf24;
    --text: #f8fafc;
    --muted: #94a3b8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg) 70%);
    color: var(--text);
    min-height: 100vh;
    padding: 14px 14px 30px;
    display: flex; flex-direction: column; align-items: center;
  }}
  .container {{ width: 100%; max-width: 440px; }}

  .topbar {{
    display: flex; align-items: center; justify-content: space-between;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 16px; padding: 12px 16px; margin-bottom: 14px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.4);
  }}
  .topbar h1 {{ font-size: 15px; font-weight: 800; display: flex; align-items: center; gap: 8px; }}
  .topbar p {{ font-size: 11px; color: var(--muted); }}

  /* Área da Câmera e Mira */
  .scanner-box {{
    position: relative; width: 100%; height: 320px;
    background: #000; border-radius: 22px; overflow: hidden;
    border: 2px solid rgba(255,255,255,0.15);
    box-shadow: 0 16px 36px rgba(0,0,0,0.55);
    margin-bottom: 14px;
  }}
  #reader {{ width: 100%; height: 100%; }}
  #reader video {{ object-fit: cover; width: 100% !important; height: 100% !important; }}

  /* Overlay de Mira */
  .reticle {{
    position: absolute; inset: 24px; pointer-events: none;
    border: 2px dashed rgba(255,255,255,0.25); border-radius: 18px;
    display: flex; align-items: center; justify-content: center;
  }}
  .reticle-corner {{
    position: absolute; width: 28px; height: 28px;
    border: 4px solid var(--blue);
  }}
  .c-tl {{ top: -2px; left: -2px; border-right: none; border-bottom: none; border-top-left-radius: 14px; }}
  .c-tr {{ top: -2px; right: -2px; border-left: none; border-bottom: none; border-top-right-radius: 14px; }}
  .c-bl {{ bottom: -2px; left: -2px; border-right: none; border-top: none; border-bottom-left-radius: 14px; }}
  .c-br {{ bottom: -2px; right: -2px; border-left: none; border-top: none; border-bottom-right-radius: 14px; }}

  /* Linha laser de scan */
  .laser {{
    position: absolute; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, #38bdf8, #818cf8, transparent);
    box-shadow: 0 0 12px #38bdf8;
    animation: scanAnim 2.2s ease-in-out infinite alternate;
  }}
  @keyframes scanAnim {{
    0% {{ top: 10%; opacity: 0.3; }}
    50% {{ opacity: 1; }}
    100% {{ top: 90%; opacity: 0.3; }}
  }}

  /* Instrução */
  .hint {{
    text-align: center; font-size: 13px; color: var(--muted); margin-bottom: 14px;
  }}

  /* Card de Resultado da Leitura */
  .result-card {{
    display: none;
    background: var(--card); border: 2px solid var(--border);
    border-radius: 20px; padding: 18px; text-align: center;
    margin-bottom: 14px;
    animation: popIn 0.35s cubic-bezier(.17,.89,.32,1.28);
  }}
  .result-card.show {{ display: block; }}
  @keyframes popIn {{
    from {{ opacity: 0; transform: scale(0.92); }}
    to {{ opacity: 1; transform: scale(1); }}
  }}

  .res-avatar {{ font-size: 48px; margin-bottom: 6px; }}
  .res-title {{ font-size: 18px; font-weight: 900; color: #fff; margin-bottom: 2px; }}
  .res-cargo {{ font-size: 13px; color: #38bdf8; font-weight: 700; margin-bottom: 8px; }}
  .res-badge {{
    display: inline-block; padding: 5px 14px; border-radius: 999px;
    font-size: 12px; font-weight: 900; letter-spacing: 0.5px; margin-bottom: 12px;
  }}
  .res-info {{
    background: rgba(0,0,0,0.3); border-radius: 12px; padding: 10px 14px;
    font-size: 12px; text-align: left; line-height: 1.6; color: #cbd5e1; margin-bottom: 12px;
  }}
  .res-info strong {{ color: #fff; }}

  /* Botão de Concluir */
  .btn-confirm {{
    width: 100%; border: none; border-radius: 14px; padding: 14px;
    font-size: 15px; font-weight: 800; cursor: pointer;
    background: linear-gradient(135deg, #10b981, #059669); color: #fff;
    box-shadow: 0 6px 18px rgba(16,185,129,0.35); margin-bottom: 8px;
  }}

  /* Digitação Manual Alternativa */
  .manual-box {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 16px; padding: 14px; text-align: center;
  }}
  .manual-box p {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
  .manual-row {{ display: flex; gap: 8px; }}
  .manual-input {{
    flex: 1; background: #0f172a; border: 1px solid var(--border);
    color: #fff; padding: 10px 12px; border-radius: 10px; font-size: 14px;
    text-transform: uppercase; font-family: monospace;
  }}
  .manual-btn {{
    background: var(--blue); border: none; color: #fff; font-weight: 700;
    padding: 0 16px; border-radius: 10px; cursor: pointer; font-size: 13px;
  }}

  .status-tag {{
    font-size: 11px; color: var(--muted); margin-top: 10px; text-align: center;
  }}
</style>
</head>
<body>
<div class="container">

  <!-- Top Bar -->
  <div class="topbar">
    <div>
      <h1>📷 Validador de Crachá</h1>
      <p>OS #{sessao['task_num']} • Sessão {tx_id}</p>
    </div>
    <div style="font-size:22px;">🪪</div>
  </div>

  <!-- Leitor / Câmera -->
  <div class="scanner-box" id="scannerWrap">
    <div id="reader"></div>
    <div class="reticle">
      <div class="reticle-corner c-tl"></div>
      <div class="reticle-corner c-tr"></div>
      <div class="reticle-corner c-bl"></div>
      <div class="reticle-corner c-br"></div>
      <div class="laser"></div>
    </div>
  </div>

  <div class="hint" id="txtHint">
    Aponte a câmera para o <strong>QR Code do crachá</strong> do profissional
  </div>

  <!-- Card de Resultado (aparece após leitura) -->
  <div class="result-card" id="cardResult">
    <div class="res-avatar" id="resAvatar">👤</div>
    <div class="res-title" id="resNome">Nome do Titular</div>
    <div class="res-cargo" id="resCargo">Cargo / Função</div>
    <div class="res-badge" id="resBadge">STATUS</div>

    <div class="res-info">
      <div><strong>Código:</strong> <span id="resCodigo" style="color:var(--gold);font-family:monospace;">-</span></div>
      <div><strong>Empresa:</strong> <span id="resEmpresa">-</span></div>
      <div><strong>Nível:</strong> <span id="resNivel">-</span></div>
      <div><strong>Validade:</strong> <span id="resValidade">-</span></div>
      <div id="resMotivoLinha" style="display:none; color:#fca5a5;"><strong>Motivo:</strong> <span id="resMotivo"></span></div>
    </div>

    <button class="btn-confirm" id="btnConfirmar" onclick="concluir()">
      ✅ Liberar Formulário no OfficeTrack
    </button>
  </div>

  <!-- Alternativa Manual -->
  <div class="manual-box" id="boxManual">
    <p>Sem câmera? Digite o código do crachá para testar:</p>
    <div class="manual-row">
      <input type="text" class="manual-input" id="inpManual" placeholder="Ex: CR-1001" value="CR-1001">
      <button class="manual-btn" onclick="validarManual()">Validar</button>
    </div>
  </div>

  <div class="status-tag">
    Ao fechar a tela, o OfficeTrack preencherá os dados e a flag de liberação automaticamente.
  </div>

</div>

<script>
const TX_ID = "{tx_id}";
let scannerAtivo = true;
let html5QrCode = null;

// Áudio tátil sintético (sem arquivos externos)
function playBeep(sucesso) {{
  try {{
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = sucesso ? 'sine' : 'sawtooth';
    osc.frequency.setValueAtTime(sucesso ? 987.77 : 220, ctx.currentTime);
    if (sucesso) {{
      osc.frequency.exponentialRampToValueAtTime(1318.51, ctx.currentTime + 0.08);
    }}
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + (sucesso ? 0.18 : 0.35));
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start(); osc.stop(ctx.currentTime + (sucesso ? 0.19 : 0.36));
  }} catch(e) {{}}
}}

async function processarCodigoDetectado(codigo) {{
  if (!scannerAtivo) return;
  scannerAtivo = false;

  document.getElementById('txtHint').innerHTML = '⏳ Validando crachá no sistema...';

  try {{
    if (html5QrCode && html5QrCode.isScanning) {{
      await html5QrCode.stop().catch(() => {{}});
    }}
  }} catch (e) {{}}

  try {{
    const resp = await fetch(`/api/scanner_cracha/${{TX_ID}}/validar`, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{codigo: codigo}})
    }});
    const res = await resp.json();
    exibirResultado(res);
  }} catch (err) {{
    alert('Erro de conexão ao validar o crachá: ' + err);
    scannerAtivo = true;
  }}
}}

function exibirResultado(res) {{
  playBeep(res.autorizado);

  document.getElementById('scannerWrap').style.display = 'none';
  document.getElementById('txtHint').style.display = 'none';
  document.getElementById('boxManual').style.display = 'none';

  const card = document.getElementById('cardResult');
  card.classList.add('show');

  document.getElementById('resAvatar').textContent = res.avatar || (res.autorizado ? '👷‍♂️' : '⛔');
  document.getElementById('resNome').textContent = res.nome || 'Titular Não Encontrado';
  document.getElementById('resCargo').textContent = res.cargo || (res.autorizado ? 'Profissional Autorizado' : 'Acesso Não Permitido');
  document.getElementById('resCodigo').textContent = res.codigo;
  document.getElementById('resEmpresa').textContent = res.empresa || '-';
  document.getElementById('resNivel').textContent = res.nivel || '-';
  document.getElementById('resValidade').textContent = res.validade || '-';

  const badge = document.getElementById('resBadge');
  const btn = document.getElementById('btnConfirmar');

  if (res.autorizado) {{
    badge.textContent = '● AUTORIZADO / LIBERADO';
    badge.style.background = '#10b98122';
    badge.style.color = '#10b981';
    badge.style.border = '1px solid #10b98166';
    btn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
    btn.textContent = '✅ Liberar Formulário no OfficeTrack';
    document.getElementById('resMotivoLinha').style.display = 'none';
  }} else {{
    badge.textContent = '● ' + (res.status || 'NÃO AUTORIZADO');
    badge.style.background = '#ef444422';
    badge.style.color = '#ef4444';
    badge.style.border = '1px solid #ef444466';
    btn.style.background = 'linear-gradient(135deg, #ef4444, #b91c1c)';
    btn.textContent = '⚠️ Bloqueio Registrado (Fechar)';
    document.getElementById('resMotivoLinha').style.display = 'block';
    document.getElementById('resMotivo').textContent = res.motivo;
  }}
}}

function concluir() {{
  // No OfficeTrack, fechar a janela no X/Voltar dispara o WebService de retorno
  alert('Perfeito! Agora feche esta janela no X (ou Voltar) para o OfficeTrack preencher os dados automaticamente.');
}}

function validarManual() {{
  const cod = document.getElementById('inpManual').value.trim();
  if (!cod) return;
  processarCodigoDetectado(cod);
}}

// Iniciar Câmera Traseira
window.addEventListener('DOMContentLoaded', () => {{
  if (typeof Html5Qrcode === 'undefined') {{
    document.getElementById('txtHint').innerHTML = '⚠️ Use o campo abaixo para validar o crachá manualmente.';
    return;
  }}

  html5QrCode = new Html5Qrcode("reader");
  const config = {{ fps: 15, qrbox: {{ width: 230, height: 230 }} }};

  html5QrCode.start(
    {{ facingMode: "environment" }},
    config,
    (decodedText) => {{
      processarCodigoDetectado(decodedText);
    }},
    (errorMessage) => {{
      // varrendo frames...
    }}
  ).catch(err => {{
    console.warn("Câmera não iniciada (permissão ou dispositivo sem câmera):", err);
    document.getElementById('txtHint').innerHTML =
      '💡 Câmera não disponível no momento. Use o campo abaixo para validar:';
  }});
}});
</script>
</body>
</html>"""
    return render_template_string(html)


def api_validar_scanner(tx_id):
    """
    Chamada AJAX interna da tela do scanner ao detectar o QR code.
    Valida e salva o resultado na sessão para quando o técnico fechar a tela.
    """
    data = request.get_json(silent=True) or {}
    codigo = data.get("codigo") or ""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        sessao = conn.execute("SELECT * FROM sessoes_scanner WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
        task_num = sessao["task_num"] if sessao else "N/A"
        tecnico_app = sessao["tecnico_app"] if sessao else "N/A"

    res = _consultar_cracha_no_banco(codigo, task_num, tecnico_app)

    base_url = _obter_base_url()
    res["link_cracha"] = f"{base_url}/cracha_digital/{res['codigo']}"

    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    flag_int = 1 if res["autorizado"] else 0

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """UPDATE sessoes_scanner
               SET status_leitura = ?, codigo_lido = ?, flag_liberacao = ?,
                   dados_resposta_json = ?, lido_em = ?
               WHERE tx_id = ?""",
            (res["status"], res["codigo"], flag_int, json.dumps(res, ensure_ascii=False), agora, tx_id.upper()),
        )
        conn.commit()

    return jsonify(res)


def finalizar_scanner_cracha(tx_id):
    """
    2º Passo Automático:
    Chamado pelo OfficeTrack quando o técnico fecha o scanner.
    Preenche no formulário os dados do profissional e a FLAG_LIBERACAO.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessoes_scanner WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
            if not row:
                return _resposta_v2_erro(f"Sessão de scanner {tx_id} não encontrada.")

        if row["status_leitura"] == "AGUARDANDO":
            # Fechou antes de escanear
            campos = {
                "STATUS_AUTORIZACAO": "PENDENTE",
                "FLAG_LIBERACAO": "0",
                "COD_CRACHA": "",
                "MOTIVO_BLOQUEIO": "Leitor fechado antes de escanear o crachá.",
            }
            return _resposta_v2_sucesso(
                sucesso=False,
                mensagem="Você fechou o leitor antes de escanear o crachá!\nO formulário continua bloqueado.",
                short_text="Pendente",
                long_text="Toque na lixeira para abrir o scanner novamente",
                campos=campos,
            )

        dados = json.loads(row["dados_resposta_json"])
        autorizado = (row["flag_liberacao"] == 1)

        campos = {
            "COD_CRACHA": row["codigo_lido"],
            "FLAG_LIBERACAO": str(row["flag_liberacao"]),
            "STATUS_AUTORIZACAO": dados.get("status", "NÃO AUTORIZADO"),
            "NOME_AUTORIZADO": dados.get("nome", ""),
            "CARGO_AUTORIZADO": dados.get("cargo", ""),
            "EMPRESA_AUTORIZADO": dados.get("empresa", ""),
            "NIVEL_ACESSO": dados.get("nivel", ""),
            "VALIDADE_CRACHA": dados.get("validade", ""),
            "MOTIVO_BLOQUEIO": dados.get("motivo", ""),
            "LINK_CRACHA_DIGITAL": dados.get("link_cracha", ""),
            "VALIDADO_EM": row["lido_em"],
        }

        if autorizado:
            msg = (
                f"✅ CRACHÁ AUTORIZADO COM SUCESSO!\n\n"
                f"Titular: {dados.get('nome')}\n"
                f"Cargo: {dados.get('cargo')}\n"
                f"Empresa: {dados.get('empresa')}\n"
                f"Nível: {dados.get('nivel')}\n\n"
                f"O preenchimento do formulário foi LIBERADO!"
            )
            return _resposta_v2_sucesso(
                sucesso=True,
                mensagem=msg,
                short_text="Autorizado",
                campos=campos,
            )
        else:
            msg = (
                f"⛔ CRACHÁ BLOQUEADO!\n\n"
                f"Código: {row['codigo_lido']}\n"
                f"Motivo: {dados.get('motivo')}\n\n"
                f"Preenchimento do formulário BLOQUEADO."
            )
            return _resposta_v2_sucesso(
                sucesso=False,
                mensagem=msg,
                short_text="Bloqueado",
                long_text=dados.get("motivo", "Crachá não autorizado"),
                campos=campos,
            )

    except Exception as e:
        logging.error(f"Erro em finalizar_scanner_cracha: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao finalizar scanner: {str(e)}")


# ==========================================================
# 2. MODO DIRETO: VALIDAÇÃO SEM TELA (VIA CAMPO DO FORM)
# ==========================================================

def validar_cracha():
    """
    Modo Direto: o operador bipa ou digita o crachá no campo COD_CRACHA
    e clica no botão sem abrir tela web.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("Não foi possível ler os dados XML do formulário.")

        root = _parse_xml(xml_data)
        task_num = root.findtext(".//Task/TaskNum") or "DEMO-OS"
        tecnico_app = root.findtext(".//Employee/EmployeeNumber") or "TECNICO"

        campos_form = {}
        for f in root.findall(".//Field"):
            fid = f.findtext("Id") or f.findtext("ID") or f.findtext("id")
            fval = f.findtext("Value") or ""
            if fid:
                campos_form[fid.strip().upper()] = fval.strip()

        codigo_cracha = (
            campos_form.get("COD_CRACHA")
            or campos_form.get("CRACHA")
            or campos_form.get("MATRICULA_CRACHA")
            or campos_form.get("QR_CRACHA")
            or campos_form.get("CARTAO")
            or campos_form.get("CODIGO_CRACHA")
            or ""
        ).strip().upper()

        if not codigo_cracha:
            return _resposta_v2_erro(
                "Nenhum crachá informado.\nPor favor, digite ou bipe o código do crachá no campo correspondente."
            )

        res = _consultar_cracha_no_banco(codigo_cracha, task_num, tecnico_app)
        base_url = _obter_base_url()
        link_cracha = f"{base_url}/cracha_digital/{res['codigo']}"

        campos = {
            "COD_CRACHA": res["codigo"],
            "FLAG_LIBERACAO": res["flag_liberacao"],
            "STATUS_AUTORIZACAO": res["status"],
            "NOME_AUTORIZADO": res["nome"],
            "CARGO_AUTORIZADO": res["cargo"],
            "EMPRESA_AUTORIZADO": res["empresa"],
            "NIVEL_ACESSO": res["nivel"],
            "VALIDADE_CRACHA": res["validade"],
            "MOTIVO_BLOQUEIO": res["motivo"],
            "LINK_CRACHA_DIGITAL": link_cracha,
            "VALIDADO_EM": res["validado_em"],
        }

        if res["autorizado"]:
            msg = (
                f"✅ PROFISSIONAL AUTORIZADO!\n\n"
                f"Titular: {res['avatar']} {res['nome']}\n"
                f"Cargo: {res['cargo']}\n"
                f"Empresa: {res['empresa']}\n"
                f"Permissão: {res['nivel']}\n\n"
                f"Formulário liberado para preenchimento!"
            )
            return _resposta_v2_sucesso(sucesso=True, mensagem=msg, short_text="Autorizado", campos=campos)
        else:
            msg = (
                f"⛔ ACESSO RECUSADO!\n\n"
                f"Crachá: {res['codigo']}\n"
                f"Situação: {res['status']}\n"
                f"Motivo: {res['motivo']}\n\n"
                f"Preenchimento do formulário BLOQUEADO."
            )
            return _resposta_v2_sucesso(sucesso=False, mensagem=msg, short_text="Bloqueado", campos=campos)

    except Exception as e:
        logging.error(f"Erro em validar_cracha: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao validar crachá: {str(e)}")


def cracha_digital(codigo):
    """Página web com badge/cartão digital do titular com foto."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM crachas WHERE UPPER(codigo) = ?", (codigo.upper(),)).fetchone()
        if not row:
            return "<h2>Crachá não encontrado.</h2>", 404

    dados = dict(row)
    cor_status = "#10b981" if dados["status"] == "ATIVO" else "#ef4444"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Crachá Digital • {dados['nome']}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b0f19; color: #f8fafc;
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    padding: 16px;
  }}
  .badge-card {{
    width: 100%; max-width: 360px;
    background: linear-gradient(165deg, #1e293b 0%, #0f172a 100%);
    border: 2px solid rgba(255,255,255,0.1);
    border-radius: 24px; padding: 24px 20px; text-align: center;
    box-shadow: 0 20px 40px rgba(0,0,0,0.6); position: relative; overflow: hidden;
  }}
  .badge-card::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 6px;
    background: {cor_status};
  }}
  .badge-header {{ font-size: 11px; color: #94a3b8; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }}
  .avatar-circle {{
    width: 86px; height: 86px; border-radius: 50%; margin: 0 auto 12px;
    background: #1e293b; border: 3px solid {cor_status};
    display: flex; align-items: center; justify-content: center; font-size: 44px;
    box-shadow: 0 0 20px {cor_status}44;
  }}
  .name {{ font-size: 19px; font-weight: 900; color: #fff; margin-bottom: 4px; }}
  .cargo {{ font-size: 13px; color: #38bdf8; font-weight: 600; margin-bottom: 2px; }}
  .empresa {{ font-size: 12px; color: #94a3b8; margin-bottom: 16px; }}

  .status-pill {{
    display: inline-block; padding: 6px 16px; border-radius: 999px;
    font-size: 12px; font-weight: 900; letter-spacing: 0.5px;
    background: {cor_status}22; color: {cor_status}; border: 1px solid {cor_status}66;
    margin-bottom: 18px;
  }}

  .info-box {{
    background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px; padding: 12px; text-align: left; margin-bottom: 16px;
    font-size: 12px; line-height: 1.6;
  }}
  .info-box strong {{ color: #cbd5e1; }}
  .code-tag {{ font-family: monospace; font-size: 14px; color: #fbbf24; font-weight: 800; letter-spacing: 1px; }}
</style>
</head>
<body>
  <div class="badge-card">
    <div class="badge-header">Credencial Digital de Acesso</div>
    <div class="avatar-circle">{dados['foto_avatar']}</div>
    <div class="name">{dados['nome']}</div>
    <div class="cargo">{dados['cargo']}</div>
    <div class="empresa">{dados['empresa']}</div>

    <div class="status-pill">● {dados['status']}</div>

    <div class="info-box">
      <div><strong>Código:</strong> <span class="code-tag">{dados['codigo']}</span></div>
      <div><strong>Nível:</strong> {dados['nivel_acesso']}</div>
      <div><strong>Permissão:</strong> {dados['areas_permitidas']}</div>
      <div><strong>Validade:</strong> {dados['validade']}</div>
    </div>

    <div style="font-size:11px;color:#64748b;">
      Autenticado pelo Web Service OfficeTrack
    </div>
  </div>
</body>
</html>"""
    return render_template_string(html)


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
