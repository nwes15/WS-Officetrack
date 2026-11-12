from flask import request, Response, jsonify, render_template_string
from lxml import etree
import logging
import sqlite3
import uuid
import os
import re
import json
from datetime import datetime
from io import BytesIO
from utils.xml_da_requisicao import obter_xml_da_requisicao
from utils.adicionar_campo import adicionar_campo

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "dashboards_tabelas.db")


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessoes_dashboard (
                tx_id TEXT PRIMARY KEY,
                task_num TEXT,
                tecnico TEXT,
                nome_tecnico TEXT,
                id_tabela TEXT,
                total_linhas INTEGER DEFAULT 0,
                resumo_json TEXT,
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


def _parse_xml(xml_data):
    """Faz parse seguro de XML recebido em string."""
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
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _classificar_status(status_raw):
    s = (status_raw or "").strip().upper()
    if any(k in s for k in ("CRIT", "INOP", "QUEBR", "PARAD", "DEFEIT", "REPROV", "FALH", "RUIM", "URGENT", "NOK", "NAO")):
        return "CRÍTICO", "#ef4444", "🚨"
    if any(k in s for k in ("ATEN", "PARCIAL", "ALERT", "AJUST", "MANUT", "PECA", "PENDENT", "REGULAR", "AVISO")):
        return "ATENÇÃO", "#f59e0b", "⚠️"
    return "OPERACIONAL", "#10b981", "✅"


def _classificar_manutencao(manut_raw):
    m = (manut_raw or "").strip().upper()
    if "PREV" in m:
        return "Preventiva"
    if "CORR" in m or "REPAR" in m or "CONCERT" in m:
        return "Corretiva"
    if "CALIB" in m or "PRED" in m or "AFER" in m:
        return "Preditiva / Calibração"
    if "INSTAL" in m or "TROCA" in m or "SUBST" in m:
        return "Troca / Instalação"
    if "LIMP" in m or "LUBRIF" in m or "HIGIEN" in m:
        return "Limpeza / Lubrificação"
    if "INSP" in m or "VIST" in m or "CHECK" in m:
        return "Inspeção / Vistoria"
    return "Geral / Outros"


def processar_linhas_tabela(rows):
    """
    Mapeia de forma inteligente as colunas da tabela dinâmica
    e calcula agregações estatísticas para o Dashboard.
    """
    itens = []
    total_custo = 0.0

    for idx, row in enumerate(rows, start=1):
        campos = {}
        for f in row.findall(".//Field"):
            fid = f.findtext("Id") or f.findtext("ID") or f.findtext("id")
            fval = f.findtext("Value") or ""
            if fid:
                campos[fid.strip().upper()] = fval.strip()

        # 1. Equipamento / Ativo
        equipamento = (
            campos.get("EQUIPAMENTO")
            or campos.get("ATIVO")
            or campos.get("MAQUINA")
            or campos.get("ITEM")
            or campos.get("DISPOSITIVO")
            or campos.get("NOME")
            or f"Equipamento #{idx}"
        )

        # 2. Sistema / Categoria / Setor
        sistema = (
            campos.get("SISTEMA")
            or campos.get("CATEGORIA")
            or campos.get("SETOR")
            or campos.get("TIPO")
            or campos.get("LOCAL")
            or campos.get("GRUPO")
            or "Geral"
        )

        # 3. Manutenção / Ação Realizada
        manutencao_raw = (
            campos.get("MANUTENCAO")
            or campos.get("SERVICO")
            or campos.get("ACAO")
            or campos.get("TIPO_MANUTENCAO")
            or campos.get("INTERVENCAO")
            or "Preventiva"
        )
        manutencao = _classificar_manutencao(manutencao_raw)

        # 4. Status / Condição
        status_raw = (
            campos.get("STATUS")
            or campos.get("CONDICAO")
            or campos.get("SITUACAO")
            or campos.get("ESTADO")
            or campos.get("CONFORMIDADE")
            or campos.get("RESULTADO")
            or "OPERACIONAL"
        )
        status_norm, status_cor, status_emoji = _classificar_status(status_raw)

        # 5. Custo / Horas / Valor
        custo_raw = (
            campos.get("CUSTO")
            or campos.get("VALOR")
            or campos.get("PRECO")
            or campos.get("VALOR_ESTIMADO")
            or campos.get("ORCAMENTO")
            or campos.get("HORAS")
            or "0"
        )
        custo = _extrair_float(custo_raw)
        total_custo += custo

        # 6. Observação / Defeito
        obs = (
            campos.get("OBS")
            or campos.get("DEFEITO")
            or campos.get("OBSERVACAO")
            or campos.get("DETALHES")
            or campos.get("DESCRICAO")
            or "Sem observações adicionais."
        )

        itens.append({
            "idx": idx,
            "equipamento": equipamento,
            "sistema": sistema,
            "manutencao": manutencao,
            "manutencao_raw": manutencao_raw,
            "status": status_norm,
            "status_raw": status_raw,
            "status_cor": status_cor,
            "status_emoji": status_emoji,
            "custo": custo,
            "custo_fmt": f"R$ {_formatar_br(custo)}",
            "obs": obs,
        })

    total = len(itens)
    if total == 0:
        return {
            "total": 0,
            "operacionais": 0,
            "atencao": 0,
            "criticos": 0,
            "indice_saude": 0,
            "status_geral": "SEM DADOS",
            "custo_total": 0.0,
            "custo_total_fmt": "R$ 0,00",
            "itens": [],
            "sistemas": {},
            "manutencoes": {},
            "sistema_mais_critico": "Nenhum",
        }

    operacionais = sum(1 for i in itens if i["status"] == "OPERACIONAL")
    atencao = sum(1 for i in itens if i["status"] == "ATENÇÃO")
    criticos = sum(1 for i in itens if i["status"] == "CRÍTICO")

    # Índice de Saúde: 100% peso para Operacional, 50% para Atenção, 0% para Crítico
    score = ((operacionais * 1.0 + atencao * 0.5) / total) * 100
    indice_saude = int(round(score))

    if indice_saude >= 85 and criticos == 0:
        status_geral = "PARQUE SAUDÁVEL"
        status_geral_cor = "#10b981"
        status_geral_badge = "CONFORME"
    elif indice_saude >= 60:
        status_geral = "ATENÇÃO REQUERIDA"
        status_geral_cor = "#f59e0b"
        status_geral_badge = "ALERTA"
    else:
        status_geral = "RISCO OPERACIONAL"
        status_geral_cor = "#ef4444"
        status_geral_badge = "CRÍTICO"

    # Agregação por Sistema/Categoria
    sistemas = {}
    for i in itens:
        sis = i["sistema"]
        if sis not in sistemas:
            sistemas[sis] = {"total": 0, "operacional": 0, "atencao": 0, "critico": 0, "custo": 0.0}
        sistemas[sis]["total"] += 1
        sistemas[sis]["custo"] += i["custo"]
        if i["status"] == "OPERACIONAL":
            sistemas[sis]["operacional"] += 1
        elif i["status"] == "ATENÇÃO":
            sistemas[sis]["atencao"] += 1
        else:
            sistemas[sis]["critico"] += 1

    # Identificar sistema mais crítico
    sistema_mais_critico = "Nenhum"
    max_criticos = -1
    for sis, dados in sistemas.items():
        if dados["critico"] > max_criticos and dados["critico"] > 0:
            max_criticos = dados["critico"]
            sistema_mais_critico = sis

    # Agregação por Tipo de Manutenção
    manutencoes = {}
    for i in itens:
        m = i["manutencao"]
        manutencoes[m] = manutencoes.get(m, 0) + 1

    return {
        "total": total,
        "operacionais": operacionais,
        "atencao": atencao,
        "criticos": criticos,
        "indice_saude": indice_saude,
        "status_geral": status_geral,
        "status_geral_cor": status_geral_cor,
        "status_geral_badge": status_geral_badge,
        "custo_total": total_custo,
        "custo_total_fmt": f"R$ {_formatar_br(total_custo)}",
        "sistema_mais_critico": sistema_mais_critico,
        "itens": itens,
        "sistemas": sistemas,
        "manutencoes": manutencoes,
    }


def iniciar_dashboard_tabela():
    """
    1º Passo: Botão fora da Tabela no OfficeTrack.
    Lê a tabela dinâmica preenchida na OS, calcula as métricas e retorna <Action>OpenUrl</Action>.
    """
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("Não foi possível ler os dados XML do formulário.")

        root = _parse_xml(xml_data)

        task_num = root.findtext(".//Task/TaskNum") or "DEMO-OS"
        tecnico = root.findtext(".//Employee/EmployeeNumber") or "TECNICO"

        campos_form = {}
        for f in root.findall(".//Field"):
            fid = f.findtext("Id") or f.findtext("ID") or f.findtext("id")
            fval = f.findtext("Value") or ""
            if fid:
                campos_form[fid.strip().upper()] = fval.strip()

        nome_tecnico = campos_form.get("NOME_TECNICO") or campos_form.get("TECNICO") or tecnico

        # Localiza qualquer TableField que tenha linhas
        tabelas = root.xpath(".//TableField[.//Rows/Row]")
        if not tabelas:
            # Fallback se a tabela ainda estiver vazia no form
            tabelas = root.xpath(".//TableField")

        if not tabelas:
            return _resposta_v2_erro(
                "Nenhuma tabela encontrada no formulário.\nAdicione a Tabela Dinâmica de Equipamentos antes de gerar o Dashboard."
            )

        tabela_alvo = tabelas[0]
        id_tabela = tabela_alvo.findtext("Id") or tabela_alvo.findtext("ID") or "TABELA_EQUIPAMENTOS"
        rows = tabela_alvo.xpath(".//Rows/Row")

        if not rows:
            return _resposta_v2_erro(
                "A tabela está sem linhas cadastradas.\nInsira pelo menos um equipamento na tabela antes de gerar o Dashboard."
            )

        resumo = processar_linhas_tabela(rows)

        tx_id = str(uuid.uuid4())[:8].upper()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO sessoes_dashboard
                   (tx_id, task_num, tecnico, nome_tecnico, id_tabela, total_linhas, resumo_json, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tx_id, task_num, tecnico, nome_tecnico, id_tabela, len(rows), json.dumps(resumo, ensure_ascii=False), agora, agora),
            )
            conn.commit()

        base_url = _obter_base_url()
        url_dash = f"{base_url}/dashboard_tabela/{tx_id}"
        url_retorno = f"{base_url}/finalizar_dashboard_tabela/{tx_id}"

        response = etree.Element("Response")
        ret = etree.SubElement(response, "ReturnValue")
        etree.SubElement(ret, "ShortText").text = "Dashboard Gerado"
        etree.SubElement(ret, "LongText").text = f"Sessão {tx_id}"
        etree.SubElement(ret, "Value").text = "OK"
        etree.SubElement(ret, "Action").text = "OpenUrl"
        etree.SubElement(ret, "Url").text = url_dash
        etree.SubElement(ret, "WebService").text = url_retorno

        xml_str = etree.tostring(response, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return Response(xml_str, content_type="application/xml; charset=utf-8")

    except Exception as e:
        logging.error(f"Erro em iniciar_dashboard_tabela: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao processar tabela: {str(e)}")


def tela_dashboard_tabela(tx_id):
    """Exibe o Dashboard visual responsivo gerado a partir da tabela dinâmica."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM sessoes_dashboard WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
        if not row:
            return "<h2>Dashboard não encontrado ou sessão expirada.</h2>", 404

    dados = json.loads(row["resumo_json"])
    dados["tx_id"] = row["tx_id"]
    dados["task_num"] = row["task_num"]
    dados["tecnico"] = row["nome_tecnico"] or row["tecnico"]
    dados["id_tabela"] = row["id_tabela"]
    dados["criado_em"] = row["criado_em"]

    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Dashboard de Manutenção • OfficeTrack</title>
<style>
  :root {
    --bg: #090d16;
    --card: #131a2b;
    --card2: #1c263d;
    --border: rgba(255,255,255,0.08);
    --gold: #fbbf24;
    --green: #10b981;
    --yellow: #f59e0b;
    --red: #ef4444;
    --blue: #3b82f6;
    --purple: #8b5cf6;
    --text: #f8fafc;
    --muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg) 65%);
    color: var(--text);
    min-height: 100vh;
    padding: 14px 14px 36px;
    overflow-x: hidden;
  }
  .container { max-width: 520px; margin: 0 auto; }

  /* Top Bar */
  .topbar {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 18px; padding: 12px 16px; margin-bottom: 14px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.4);
  }
  .top-left h1 { font-size: 16px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
  .top-left p { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .badge-health {
    font-size: 12px; font-weight: 800; padding: 6px 12px; border-radius: 999px;
    letter-spacing: 0.4px; text-transform: uppercase;
  }

  /* KPI Grid */
  .kpi-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px;
  }
  .kpi-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 16px; padding: 14px; position: relative; overflow: hidden;
  }
  .kpi-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: var(--kpi-color, var(--blue));
  }
  .kpi-title { font-size: 12px; color: var(--muted); font-weight: 600; text-transform: uppercase; margin-bottom: 6px; }
  .kpi-val { font-size: 26px; font-weight: 900; line-height: 1.1; }
  .kpi-sub { font-size: 11px; color: var(--muted); margin-top: 4px; }

  /* Section Card */
  .section-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 20px; padding: 18px 16px; margin-bottom: 14px;
    box-shadow: 0 12px 30px rgba(0,0,0,0.35);
  }
  .sec-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 14px;
  }
  .sec-title { font-size: 15px; font-weight: 800; display: flex; align-items: center; gap: 8px; }
  .sec-sub { font-size: 12px; color: var(--muted); }

  /* Donut Central */
  .donut-wrap {
    display: flex; align-items: center; justify-content: space-around; gap: 14px;
    padding: 10px 0;
  }
  .donut-svg-box { position: relative; width: 140px; height: 140px; flex-shrink: 0; }
  .donut-center-text {
    position: absolute; inset: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    pointer-events: none;
  }
  .donut-center-val { font-size: 28px; font-weight: 900; color: var(--text); }
  .donut-center-lbl { font-size: 10px; color: var(--muted); text-transform: uppercase; font-weight: 700; }

  .legend-list { display: flex; flex-direction: column; gap: 8px; flex: 1; }
  .legend-item {
    display: flex; align-items: center; justify-content: space-between;
    font-size: 13px; font-weight: 600;
  }
  .legend-tag { display: flex; align-items: center; gap: 8px; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; }

  /* Barras Horizontais por Sistema */
  .bar-list { display: flex; flex-direction: column; gap: 12px; }
  .bar-item-head {
    display: flex; justify-content: space-between; font-size: 13px; font-weight: 700; margin-bottom: 4px;
  }
  .bar-item-head span small { color: var(--muted); font-weight: normal; margin-left: 4px; }
  .bar-track {
    height: 10px; background: rgba(255,255,255,0.06); border-radius: 999px; overflow: hidden;
    display: flex;
  }
  .bar-seg { height: 100%; transition: width 0.8s ease-out; }

  /* Tags de Tipos de Manutenção */
  .pills-cloud { display: flex; flex-wrap: wrap; gap: 8px; }
  .pill-badge {
    background: var(--card2); border: 1px solid var(--border);
    padding: 6px 12px; border-radius: 12px; font-size: 12px; font-weight: 700;
    display: flex; align-items: center; gap: 6px;
  }
  .pill-count {
    background: rgba(255,255,255,0.1); padding: 2px 7px; border-radius: 999px; font-size: 11px;
  }

  /* Filtros da Tabela */
  .filter-tabs {
    display: flex; gap: 6px; overflow-x: auto; margin-bottom: 12px; padding-bottom: 4px;
  }
  .filter-btn {
    border: none; background: var(--card2); color: var(--muted);
    padding: 7px 12px; border-radius: 10px; font-size: 12px; font-weight: 700;
    white-space: nowrap; cursor: pointer; transition: all 0.2s;
  }
  .filter-btn.active {
    background: var(--blue); color: #fff;
  }

  /* Lista de Itens */
  .items-list { display: flex; flex-direction: column; gap: 10px; }
  .item-card {
    background: var(--card2); border: 1px solid var(--border);
    border-radius: 14px; padding: 12px; transition: transform 0.15s;
  }
  .item-card-top {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 10px;
    margin-bottom: 6px;
  }
  .item-name { font-size: 14px; font-weight: 800; color: #fff; }
  .item-sys { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .item-status-pill {
    padding: 4px 9px; border-radius: 8px; font-size: 11px; font-weight: 800;
    white-space: nowrap; display: inline-flex; align-items: center; gap: 4px;
  }
  .item-meta {
    display: flex; align-items: center; justify-content: space-between;
    font-size: 12px; color: #cbd5e1; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.06);
  }
  .item-obs { font-size: 11px; color: var(--muted); margin-top: 4px; font-style: italic; }

  /* Alerta Crítico Destacado */
  .critical-box {
    background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 16px; padding: 14px; margin-bottom: 14px;
  }
  .critical-title { color: #fca5a5; font-size: 13px; font-weight: 800; display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
  .critical-desc { font-size: 12px; color: #fecaca; line-height: 1.4; }

  /* Rodapé com Instrução */
  .return-tip {
    background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 14px; padding: 12px 14px; font-size: 13px; color: #a7f3d0;
    text-align: center; line-height: 1.45; margin-top: 8px;
  }
  .return-tip strong { color: #fff; }
</style>
</head>
<body>
<div class="container">

  <!-- Top Bar -->
  <div class="topbar">
    <div class="top-left">
      <h1>📊 Dashboard de Manutenção</h1>
      <p>OS #<span id="txtTask"></span> • <span id="txtTecnico"></span></p>
    </div>
    <div class="badge-health" id="badgeHealth"></div>
  </div>

  <!-- Alerta Crítico (se houver itens críticos) -->
  <div class="critical-box" id="boxCritical" style="display:none;">
    <div class="critical-title">🚨 ATENÇÃO: Equipamentos Críticos Encontrados</div>
    <div class="critical-desc" id="txtCriticalDesc"></div>
  </div>

  <!-- KPI Grid -->
  <div class="kpi-grid">
    <div class="kpi-card" style="--kpi-color: var(--blue);">
      <div class="kpi-title">Total de Ativos</div>
      <div class="kpi-val" id="kpiTotal">0</div>
      <div class="kpi-sub">Linhas na tabela</div>
    </div>
    <div class="kpi-card" style="--kpi-color: var(--green);">
      <div class="kpi-title">Saúde do Parque</div>
      <div class="kpi-val" id="kpiSaude" style="color:var(--green);">0%</div>
      <div class="kpi-sub">Índice ponderado</div>
    </div>
    <div class="kpi-card" style="--kpi-color: var(--yellow);">
      <div class="kpi-title">Requer Atenção</div>
      <div class="kpi-val" id="kpiAtencao" style="color:var(--yellow);">0</div>
      <div class="kpi-sub">Ajustes pendentes</div>
    </div>
    <div class="kpi-card" style="--kpi-color: var(--red);">
      <div class="kpi-title">Críticos / Parados</div>
      <div class="kpi-val" id="kpiCriticos" style="color:var(--red);">0</div>
      <div class="kpi-sub">Risco imediato</div>
    </div>
  </div>

  <!-- Gráfico de Donut: Saúde Operacional -->
  <div class="section-card">
    <div class="sec-head">
      <div class="sec-title">🎯 Saúde Operacional</div>
      <div class="sec-sub">Status dos Equipamentos</div>
    </div>
    <div class="donut-wrap">
      <div class="donut-svg-box">
        <svg viewBox="0 0 100 100" width="100%" height="100%" style="transform: rotate(-90deg);">
          <circle cx="50" cy="50" r="38" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="14"></circle>
          <circle id="circleOk" cx="50" cy="50" r="38" fill="none" stroke="#10b981" stroke-width="14" stroke-dasharray="0 238.7"></circle>
          <circle id="circleWarn" cx="50" cy="50" r="38" fill="none" stroke="#f59e0b" stroke-width="14" stroke-dasharray="0 238.7"></circle>
          <circle id="circleCrit" cx="50" cy="50" r="38" fill="none" stroke="#ef4444" stroke-width="14" stroke-dasharray="0 238.7"></circle>
        </svg>
        <div class="donut-center-text">
          <div class="donut-center-val" id="txtDonutScore">0%</div>
          <div class="donut-center-lbl">Saúde</div>
        </div>
      </div>
      <div class="legend-list">
        <div class="legend-item">
          <span class="legend-tag"><span class="legend-dot" style="background:#10b981;"></span>Operacionais</span>
          <span id="legOk">0</span>
        </div>
        <div class="legend-item">
          <span class="legend-tag"><span class="legend-dot" style="background:#f59e0b;"></span>Atenção</span>
          <span id="legWarn">0</span>
        </div>
        <div class="legend-item">
          <span class="legend-tag"><span class="legend-dot" style="background:#ef4444;"></span>Críticos</span>
          <span id="legCrit">0</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Barras por Sistema / Categoria -->
  <div class="section-card">
    <div class="sec-head">
      <div class="sec-title">🏢 Distribuição por Sistema / Categoria</div>
      <div class="sec-sub" id="txtCustoTotal"></div>
    </div>
    <div class="bar-list" id="listSistemas"></div>
  </div>

  <!-- Tipos de Manutenção -->
  <div class="section-card">
    <div class="sec-head">
      <div class="sec-title">🔧 Tipos de Intervenção / Ação</div>
      <div class="sec-sub">Serviços executados</div>
    </div>
    <div class="pills-cloud" id="cloudManutencao"></div>
  </div>

  <!-- Tabela Interativa de Linhas Coletadas -->
  <div class="section-card">
    <div class="sec-head">
      <div class="sec-title">📋 Itens Coletados na Tabela</div>
      <div class="sec-sub"><span id="txtFiltrados">0</span> itens</div>
    </div>
    <div class="filter-tabs">
      <button class="filter-btn active" onclick="filtrar('TODOS', this)">Todos (<span id="cntTodos">0</span>)</button>
      <button class="filter-btn" onclick="filtrar('CRÍTICO', this)">🚨 Críticos (<span id="cntCrit">0</span>)</button>
      <button class="filter-btn" onclick="filtrar('ATENÇÃO', this)">⚠️ Atenção (<span id="cntWarn">0</span>)</button>
      <button class="filter-btn" onclick="filtrar('OPERACIONAL', this)">✅ OK (<span id="cntOk">0</span>)</button>
    </div>
    <div class="items-list" id="listItens"></div>
  </div>

  <!-- Dica de Retorno -->
  <div class="return-tip">
    ✅ <strong>Resumo pronto para o formulário!</strong><br>
    Ao fechar esta janela no <strong>X</strong> ou Voltar, o OfficeTrack preencherá automaticamente os campos com o total de ativos, percentual de saúde e status do parque.
  </div>

</div>

<script>
const DADOS = {{ dados_json | safe }};

// Inicialização Topo
document.getElementById('txtTask').textContent = DADOS.task_num;
document.getElementById('txtTecnico').textContent = DADOS.tecnico;
document.getElementById('kpiTotal').textContent = DADOS.total;
document.getElementById('kpiSaude').textContent = DADOS.indice_saude + '%';
document.getElementById('kpiSaude').style.color = DADOS.status_geral_cor;
document.getElementById('kpiAtencao').textContent = DADOS.atencao;
document.getElementById('kpiCriticos').textContent = DADOS.criticos;
document.getElementById('txtDonutScore').textContent = DADOS.indice_saude + '%';

const badge = document.getElementById('badgeHealth');
badge.textContent = DADOS.status_geral_badge;
badge.style.background = DADOS.status_geral_cor + '22';
badge.style.color = DADOS.status_geral_cor;
badge.style.border = '1px solid ' + DADOS.status_geral_cor + '66';

// Alerta de Críticos
if (DADOS.criticos > 0) {
  const boxCrit = document.getElementById('boxCritical');
  boxCrit.style.display = 'block';
  const critNames = DADOS.itens.filter(i => i.status === 'CRÍTICO').map(i => i.equipamento).slice(0, 3).join(', ');
  document.getElementById('txtCriticalDesc').textContent =
    `Foram identificados ${DADOS.criticos} ativo(s) em estado crítico (${critNames}). O sistema mais afetado é '${DADOS.sistema_mais_critico}'.`;
}

// Donut SVG Math (Circunferência r=38 -> ~238.76)
const C = 2 * Math.PI * 38;
const total = Math.max(1, DADOS.total);
const lenOk = (DADOS.operacionais / total) * C;
const lenWarn = (DADOS.atencao / total) * C;
const lenCrit = (DADOS.criticos / total) * C;

const circOk = document.getElementById('circleOk');
const circWarn = document.getElementById('circleWarn');
const circCrit = document.getElementById('circleCrit');

circOk.setAttribute('stroke-dasharray', `${lenOk} ${C}`);
circOk.setAttribute('stroke-dashoffset', '0');

circWarn.setAttribute('stroke-dasharray', `${lenWarn} ${C}`);
circWarn.setAttribute('stroke-dashoffset', `${-lenOk}`);

circCrit.setAttribute('stroke-dasharray', `${lenCrit} ${C}`);
circCrit.setAttribute('stroke-dashoffset', `${-(lenOk + lenWarn)}`);

document.getElementById('legOk').textContent = `${DADOS.operacionais} (${Math.round(DADOS.operacionais/total*100)}%)`;
document.getElementById('legWarn').textContent = `${DADOS.atencao} (${Math.round(DADOS.atencao/total*100)}%)`;
document.getElementById('legCrit').textContent = `${DADOS.criticos} (${Math.round(DADOS.criticos/total*100)}%)`;

// Custo Total se houver
if (DADOS.custo_total > 0) {
  document.getElementById('txtCustoTotal').textContent = `Total: ${DADOS.custo_total_fmt}`;
}

// Sistemas (Barras Horizontais)
const listSis = document.getElementById('listSistemas');
const sisEntries = Object.entries(DADOS.sistemas);
if (sisEntries.length === 0) {
  listSis.innerHTML = '<div style="font-size:12px;color:var(--muted)">Nenhum sistema identificado.</div>';
} else {
  listSis.innerHTML = sisEntries.map(([nome, s]) => {
    const pctOk = (s.operacional / s.total) * 100;
    const pctWarn = (s.atencao / s.total) * 100;
    const pctCrit = (s.critico / s.total) * 100;
    const custoStr = s.custo > 0 ? ` • R$ ${s.custo.toLocaleString('pt-BR', {minimumFractionDigits:2})}` : '';
    return `
      <div>
        <div class="bar-item-head">
          <span>${escapeHtml(nome)} <small>(${s.total} ativos${custoStr})</small></span>
          <span>${Math.round(pctOk)}% OK</span>
        </div>
        <div class="bar-track">
          <div class="bar-seg" style="width:${pctOk}%; background:#10b981;"></div>
          <div class="bar-seg" style="width:${pctWarn}%; background:#f59e0b;"></div>
          <div class="bar-seg" style="width:${pctCrit}%; background:#ef4444;"></div>
        </div>
      </div>
    `;
  }).join('');
}

// Nuvem de Manutenções
const cloud = document.getElementById('cloudManutencao');
const mEntries = Object.entries(DADOS.manutencoes);
if (mEntries.length === 0) {
  cloud.innerHTML = '<div style="font-size:12px;color:var(--muted)">Sem manutenções informadas.</div>';
} else {
  cloud.innerHTML = mEntries.map(([nome, qtd]) => `
    <div class="pill-badge">
      <span>${escapeHtml(nome)}</span>
      <span class="pill-count">${qtd}</span>
    </div>
  `).join('');
}

// Filtros da Tabela
document.getElementById('cntTodos').textContent = DADOS.total;
document.getElementById('cntCrit').textContent = DADOS.criticos;
document.getElementById('cntWarn').textContent = DADOS.atencao;
document.getElementById('cntOk').textContent = DADOS.operacionais;

let filtroAtual = 'TODOS';

function renderizarItens() {
  const lista = document.getElementById('listItens');
  const filtrados = DADOS.itens.filter(i => {
    if (filtroAtual === 'TODOS') return true;
    return i.status === filtroAtual;
  });
  document.getElementById('txtFiltrados').textContent = filtrados.length;

  if (filtrados.length === 0) {
    lista.innerHTML = '<div style="font-size:12px;color:var(--muted);text-align:center;padding:12px;">Nenhum item com este filtro.</div>';
    return;
  }

  lista.innerHTML = filtrados.map(i => {
    const bgPill = i.status_cor + '22';
    return `
      <div class="item-card">
        <div class="item-card-top">
          <div>
            <div class="item-name">${escapeHtml(i.equipamento)}</div>
            <div class="item-sys">${escapeHtml(i.sistema)} • ${escapeHtml(i.manutencao)}</div>
          </div>
          <div class="item-status-pill" style="background:${bgPill}; color:${i.status_cor}; border:1px solid ${i.status_cor}55;">
            ${i.status_emoji} ${i.status}
          </div>
        </div>
        <div class="item-meta">
          <span>${i.custo > 0 ? i.custo_fmt : 'Sem custo informado'}</span>
          <span>Linha #${i.idx}</span>
        </div>
        ${i.obs && i.obs !== 'Sem observações adicionais.' ? `<div class="item-obs">Obs: ${escapeHtml(i.obs)}</div>` : ''}
      </div>
    `;
  }).join('');
}

function filtrar(status, btn) {
  filtroAtual = status;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderizarItens();
}

renderizarItens();

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
</script>
</body>
</html>
"""
    return render_template_string(html, dados_json=json.dumps(dados, ensure_ascii=False))


def finalizar_dashboard_tabela(tx_id):
    """
    2º Passo Automático: chamado pelo OfficeTrack ao fechar a tela do Dashboard.
    Devolve os campos de resumo consolidados da tabela para a OS.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessoes_dashboard WHERE tx_id = ?", (tx_id.upper(),)).fetchone()
            if not row:
                return _resposta_v2_erro(f"Sessão de dashboard {tx_id} não encontrada.")

        dados = json.loads(row["resumo_json"])

        campos = {
            "TXID_DASHBOARD": tx_id,
            "TOTAL_EQUIPAMENTOS": str(dados["total"]),
            "TOTAL_OPERACIONAIS": str(dados["operacionais"]),
            "TOTAL_ATENCAO": str(dados["atencao"]),
            "TOTAL_CRITICOS": str(dados["criticos"]),
            "INDICE_SAUDE": f"{dados['indice_saude']}%",
            "STATUS_GERAL_PARQUE": dados["status_geral"],
            "CUSTO_TOTAL_MANUTENCAO": dados["custo_total_fmt"],
            "SISTEMA_MAIS_CRITICO": dados["sistema_mais_critico"],
        }

        msg = (
            f"Dashboard Consolidado com Sucesso!\n\n"
            f"Total de Ativos: {dados['total']}\n"
            f"Saúde do Parque: {dados['indice_saude']}% ({dados['status_geral']})\n"
            f"Operacionais: {dados['operacionais']} | Atenção: {dados['atencao']} | Críticos: {dados['criticos']}\n"
            f"Custo Total: {dados['custo_total_fmt']}"
        )

        return _resposta_v2_sucesso(
            sucesso=True,
            mensagem=msg,
            short_text=f"{dados['indice_saude']}% Saúde",
            campos=campos,
        )

    except Exception as e:
        logging.error(f"Erro em finalizar_dashboard_tabela: {e}", exc_info=True)
        return _resposta_v2_erro(f"Erro ao finalizar dashboard: {str(e)}")


def consultar_dashboard_manual():
    """Plano B para consultar manualmente usando o campo TXID_DASHBOARD."""
    try:
        xml_data = obter_xml_da_requisicao()
        if not xml_data:
            return _resposta_v2_erro("XML não encontrado.")
        root = _parse_xml(xml_data)
        tx_node = root.xpath(".//Field[Id='TXID_DASHBOARD' or ID='TXID_DASHBOARD']/Value")
        tx_id = tx_node[0].text.strip().upper() if tx_node and tx_node[0].text else ""
        if not tx_id:
            return _resposta_v2_erro("Campo TXID_DASHBOARD não encontrado ou vazio.")
        return finalizar_dashboard_tabela(tx_id)
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

