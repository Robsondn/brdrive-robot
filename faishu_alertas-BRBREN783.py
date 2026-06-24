"""
╔══════════════════════════════════════════════════════════╗
║         BRDrive - Alertas (E-mail + Feishu)             ║
║  Envia alertas via e-mail Gmail E via Feishu Bot         ║
╚══════════════════════════════════════════════════════════╝

CONFIGURAÇÃO:
    - USAR_FEISHU = True   → envia pelo Feishu Bot
    - USAR_EMAIL  = True   → envia pelo Gmail (mantido como backup)
    - Pode usar os dois ao mesmo tempo

TESTE:
    python faishu_alertas.py
"""

import io
import os
import smtplib
import logging
import requests
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("BRDrive_Alertas")

# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÕES — lidas do arquivo .env
# ══════════════════════════════════════════════════════════

# ── Feishu ────────────────────────────────────────────────
USAR_FEISHU = True
APP_ID      = os.getenv("FEISHU_APP_ID",     "")
APP_SECRET  = os.getenv("FEISHU_APP_SECRET", "")

# E-mail corporativo para receber os alertas de teste
EMAIL_TESTE_FEISHU = os.getenv("FEISHU_EMAIL_TESTE", "robson.noberto@jtexpress.com.br")

# Quando tiver os grupos, substitua por Chat IDs (oc_xxxxxxxx):
DESTINOS_FEISHU_POR_CATEGORIA = {
    "Coleta PA":   EMAIL_TESTE_FEISHU,
    "Coleta Base": EMAIL_TESTE_FEISHU,
    "Devolução":   EMAIL_TESTE_FEISHU,
    "Secundária":  EMAIL_TESTE_FEISHU,
}

# ── E-mail (backup) ───────────────────────────────────────
USAR_EMAIL      = False
EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE", "")
NOME_REMETENTE  = "BRDrive Robot - JT Express"
SENHA_APP       = os.getenv("EMAIL_SENHA_APP", "")
EMAIL_DESTINOS  = [os.getenv("EMAIL_DESTINO", "robson.noberto@jtexpress.com.br")]

# ══════════════════════════════════════════════════════════
#  FEISHU — autenticação e envio
# ══════════════════════════════════════════════════════════

BASE_URL = "https://open.feishu.cn/open-apis"
_token_cache = {"token": None, "expires": 0}


def _get_token() -> str:
    import time
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]
    url  = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Erro ao obter token Feishu: {data}")
    import time
    _token_cache["token"]   = data["tenant_access_token"]
    _token_cache["expires"] = time.time() + data.get("expire", 7200) - 60
    log.info("✅ Token Feishu obtido")
    return _token_cache["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _open_id_por_email(token: str, email: str) -> str | None:
    """Busca o Open ID do usuário pelo e-mail corporativo."""
    url  = f"{BASE_URL}/contact/v3/users/batch_get_id?user_id_type=open_id"
    resp = requests.post(url, headers=_headers(token), json={"emails": [email]}, timeout=10)
    data = resp.json()
    if data.get("code") != 0:
        log.error(f"❌ Erro ao buscar usuário: {data}")
        return None
    users = data.get("data", {}).get("user_list", [])
    if not users or not users[0].get("user_id"):
        log.warning(f"⚠️  Usuário não encontrado: {email}")
        return None
    return users[0]["user_id"]


def _enviar_card_feishu(token: str, receive_id: str, card: dict, id_type: str = "open_id"):
    url  = f"{BASE_URL}/im/v1/messages?receive_id_type={id_type}"
    body = {"receive_id": receive_id, "msg_type": "interactive", "content": json.dumps(card)}
    resp = requests.post(url, headers=_headers(token), json=body, timeout=10)
    data = resp.json()
    if data.get("code") != 0:
        log.error(f"❌ Feishu erro: {data}")
    else:
        log.info(f"✅ Card Feishu enviado para {receive_id}")
    return data


def _enviar_webhook(url: str, card: dict):
    """Envia card via webhook de bot Feishu (não usa token)."""
    resp = requests.post(url, json={"msg_type": "interactive", "card": card}, timeout=10)
    data = resp.json()
    if data.get("code", data.get("StatusCode", 0)) != 0:
        log.error(f"❌ Webhook erro: {data}")
    else:
        log.info(f"✅ Card enviado via webhook")
    return data


def _resolver_destino(token: str, destino: str) -> tuple[str, str]:
    """
    Retorna (receive_id, id_type) resolvendo automaticamente:
    - oc_xxx  → chat_id (grupo)
    - ou_xxx  → open_id (usuário)
    - email   → busca open_id pelo e-mail
    """
    if destino.startswith("oc_"):
        return destino, "chat_id"
    if destino.startswith("ou_"):
        return destino, "open_id"
    # É um e-mail — busca o open_id
    open_id = _open_id_por_email(token, destino)
    if open_id:
        return open_id, "open_id"
    raise ValueError(f"Não foi possível resolver destino: {destino}")


# ══════════════════════════════════════════════════════════
#  CARDS FEISHU
# ══════════════════════════════════════════════════════════

_COR_CAT = {
    "Coleta PA":   "purple",
    "Devolução":   "orange",
    "Coleta Base": "green",
    "Secundária":  "red",
}
_EMOJI_CAT = {
    "Coleta PA":   "🟣",
    "Devolução":   "🟠",
    "Coleta Base": "🟢",
    "Secundária":  "🔴",
}
_ORDEM_CAT = ["Coleta PA", "Devolução", "Coleta Base", "Secundária"]


def _card_alertas_operacionais(alertas: list[dict]) -> dict:
    """Card para alertas de saída/chegada atrasada."""
    agora    = datetime.now().strftime("%d/%m/%Y %H:%M")
    saidas   = [a for a in alertas if "SAÍDA"   in a.get("tipo", "")]
    chegadas = [a for a in alertas if "CHEGADA" in a.get("tipo", "")]
    elements = []

    if saidas:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**🔴 Saídas Não Realizadas**"}})
        for a in saidas:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": (
                f"**{a.get('subtipo','')}** | {a.get('transp','')} | {a.get('condutor','—')}\n"
                f"📍 {a.get('origem','')} → {a.get('destino','')}\n"
                f"🕐 Planejado: **{a.get('planejado','')}** | Atraso: **{a.get('atraso_min','')} min**"
            )}})
            elements.append({"tag": "hr"})

    if chegadas:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "**🟡 Chegadas Não Realizadas**"}})
        for a in chegadas:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": (
                f"**{a.get('subtipo','')}** | {a.get('transp','')} | {a.get('condutor','—')}\n"
                f"📍 {a.get('origem','')} → {a.get('destino','')}\n"
                f"🕐 Planejado: **{a.get('planejado','')}** | Atraso: **{a.get('atraso_min','')} min**"
            )}})
            elements.append({"tag": "hr"})

    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": f"BRDrive Robot — JT Express | {agora}"}
    ]})

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text",
                              "content": f"🚨 BRDrive — {len(alertas)} Alertas Operacionais"},
                   "template": "red"},
        "elements": elements,
    }


def _card_ciclo(status: list[dict], novos: list[dict], categoria: str | None = None) -> dict:
    """Card para ciclo JMS (verificação anterior + novas saídas em 1h)."""
    agora       = datetime.now().strftime("%d/%m/%Y %H:%M")
    nao_bateram = [s for s in status if not s.get("bateu")]
    elements    = []

    if status:
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                          "content": "**🔍 Verificação — Viagens Anteriores**"}})
        for s in status:
            icone = "✅" if s.get("bateu") else "❌"
            extra = f"Bateu às **{s['bateu_em']}**" if s.get("bateu") else "⚠️ Não bateu no app"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": (
                f"{icone} **[{s.get('regional','')}]** {s.get('viagem','')} "
                f"| Saída plan.: {s.get('saida_plan','')} | {extra}"
            )}})
        elements.append({"tag": "hr"})

    if novos:
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                          "content": "**🚨 Novas Saídas — próxima 1h**"}})
        for regional in ["SPS", "SPE"]:
            grupo_reg = [a for a in novos if a.get("regional") == regional]
            if not grupo_reg:
                continue
            elements.append({"tag": "div", "text": {"tag": "lark_md",
                              "content": f"**🚛 Regional {regional}**"}})
            for cat in _ORDEM_CAT:
                for a in [x for x in grupo_reg if x.get("categoria") == cat]:
                    emoji = _EMOJI_CAT.get(cat, "⚪")
                    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": (
                        f"{emoji} **[{regional}] {cat}** — {a.get('viagem','')}\n"
                        f"📍 {a.get('origem','')} → {a.get('destino','')}\n"
                        f"👤 {a.get('condutor','—')} | 🚛 {a.get('transp','')}\n"
                        f"🕐 Saída: **{a.get('saida_plan','')}** (faltam **{a.get('min_restantes','')} min**)"
                    )}})
                    elements.append({"tag": "hr"})

    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": f"BRDrive Robot — JT Express | {agora}"}
    ]})

    titulo = f"🚛 BRDrive — {categoria or 'Monitoramento'}"
    if nao_bateram:
        titulo += f" | ⚠️ {len(nao_bateram)} não bateu"
    if novos:
        titulo += f" | 🆕 {len(novos)} nova(s)"

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": titulo},
                   "template": _COR_CAT.get(categoria, "blue") if categoria else "blue"},
        "elements": elements,
    }


# ══════════════════════════════════════════════════════════
#  E-MAIL — funções originais mantidas
# ══════════════════════════════════════════════════════════

def _enviar_email_smtp(assunto: str, html: str, texto: str,
                       destinos: list[str], excel_bytes: bytes | None = None,
                       nome_excel: str = "relatorio.xlsx"):
    msg = MIMEMultipart("mixed")
    msg["From"]    = f"{NOME_REMETENTE} <{EMAIL_REMETENTE}>"
    msg["To"]      = ", ".join(destinos)
    msg["Subject"] = assunto
    corpo = MIMEMultipart("alternative")
    corpo.attach(MIMEText(texto, "plain", "utf-8"))
    corpo.attach(MIMEText(html,  "html",  "utf-8"))
    msg.attach(corpo)
    if excel_bytes:
        anexo = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        anexo.set_payload(excel_bytes)
        encoders.encode_base64(anexo)
        anexo.add_header("Content-Disposition", "attachment", filename=nome_excel)
        msg.attach(anexo)
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_REMETENTE, SENHA_APP)
        server.sendmail(EMAIL_REMETENTE, destinos, msg.as_string())


def _gerar_excel(status: list[dict], novos: list[dict], categoria: str | None) -> bytes:
    linhas = []
    for s in status:
        linhas.append({"Tipo": "Verificação Anterior", "Viagem": s.get("viagem",""),
                        "Regional": s.get("regional",""), "Categoria": s.get("categoria",""),
                        "Estação Partida": s.get("origem",""), "Saída Planejada": s.get("saida_plan",""),
                        "Registro App": f"Bateu às {s['bateu_em']}" if s.get("bateu") else "Não bateu"})
    for a in novos:
        linhas.append({"Tipo": "Nova Saída (próxima 1h)", "Viagem": a.get("viagem",""),
                        "Regional": a.get("regional",""), "Categoria": a.get("categoria",""),
                        "Estação Partida": a.get("origem",""), "Saída Planejada": a.get("saida_plan",""),
                        "Registro App": f"Faltam {a.get('min_restantes','')} min"})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(linhas).to_excel(writer, index=False, sheet_name=categoria or "Relatório")
    return buf.getvalue()


# ══════════════════════════════════════════════════════════
#  FUNÇÕES PÚBLICAS
# ══════════════════════════════════════════════════════════

def enviar_alertas(alertas: list[dict]):
    """Alertas de saída/chegada atrasada — chamado pelo main.py"""
    if not alertas:
        log.info("✅ Nenhum alerta para enviar")
        return

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    if USAR_FEISHU:
        try:
            token = _get_token()
            card  = _card_alertas_operacionais(alertas)
            rid, rtype = _resolver_destino(token, EMAIL_TESTE_FEISHU)
            _enviar_card_feishu(token, rid, card, rtype)
        except Exception as e:
            log.error(f"❌ Feishu falhou: {e}")

    if USAR_EMAIL:
        try:
            from faishu_alertas import gerar_html, gerar_texto_plain
            assunto = f"🚨 BRDrive — {len(alertas)} Alertas ({agora})"
            _enviar_email_smtp(assunto, gerar_html(alertas), gerar_texto_plain(alertas), EMAIL_DESTINOS)
            log.info("✅ E-mail enviado!")
        except Exception as e:
            log.error(f"❌ E-mail falhou: {e}")


def enviar_ciclo(status: list[dict], novos: list[dict],
                 destinos: list[str] | None = None, categoria: str | None = None):
    """Ciclo JMS — chamado pelo main_teste.py"""
    if not status and not novos:
        log.info("✅ Nenhum dado para enviar")
        return

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    alvos = destinos if destinos else [EMAIL_TESTE_FEISHU]

    if USAR_FEISHU:
        try:
            card = _card_ciclo(status, novos, categoria=categoria)
            for alvo in alvos:
                if alvo.startswith("https://"):
                    _enviar_webhook(alvo, card)
                else:
                    token = _get_token()
                    rid, rtype = _resolver_destino(token, alvo)
                    _enviar_card_feishu(token, rid, card, rtype)
        except Exception as e:
            log.error(f"❌ Feishu falhou: {e}")

    if USAR_EMAIL:
        try:
            nao_bat = len([s for s in status if not s.get("bateu")])
            partes  = []
            if status: partes.append(f"{len(status)} verificados ({nao_bat} não bateram)")
            if novos:  partes.append(f"{len(novos)} nova(s)")
            prefixo = f"[{categoria}] " if categoria else ""
            assunto = f"🚛 BRDrive — {prefixo}{' | '.join(partes)} ({agora})"
            excel   = _gerar_excel(status, novos, categoria)
            nome_ex = f"BRDrive_{(categoria or 'Geral').replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            email_alvos = [a for a in alvos if "@" in a] or EMAIL_DESTINOS
            _enviar_email_smtp(assunto, "", "", email_alvos, excel, nome_ex)
            log.info("✅ E-mail enviado!")
        except Exception as e:
            log.error(f"❌ E-mail falhou: {e}")


def enviar_alertas_jms(alertas: list[dict], destinos: list[str] | None = None):
    """Alias de compatibilidade."""
    enviar_ciclo([], alertas, destinos=destinos)


def _card_consolidado(todos: list[dict]) -> dict:
    """Card do consolidado 6h para o SP Capacity Team — todas as bases, PT + 中文."""
    agora   = datetime.now().strftime("%d/%m/%Y %H:%M")
    bateram = [t for t in todos if t.get("bateu")]
    nao_bat = [t for t in todos if not t.get("bateu")]
    elements = []

    # Resumo geral / 总览
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": (
        f"**Total / 总计:** {len(todos)} viagem(ns) / 行程\n"
        f"✅ {len(bateram)} bateram / 已打卡　　❌ {len(nao_bat)} não bateram / 未打卡"
    )}})
    elements.append({"tag": "hr"})

    if nao_bat:
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": "**❌ Não Bateram no App / 未在App打卡**"}})
        for t in sorted(nao_bat, key=lambda x: x.get("saida_plan", "")):
            emoji = _EMOJI_CAT.get(t.get("categoria", ""), "⚪")
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": (
                f"{emoji} **[{t.get('regional','')}] {t.get('categoria','')}** — {t.get('viagem','')}\n"
                f"📍 {t.get('origem','')} | 🕐 Saída plan. / 计划发车: **{t.get('saida_plan','')}**"
            )}})
        elements.append({"tag": "hr"})

    if bateram:
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": "**✅ Bateram no App / 已在App打卡**"}})
        for t in sorted(bateram, key=lambda x: x.get("saida_plan", "")):
            emoji = _EMOJI_CAT.get(t.get("categoria", ""), "⚪")
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": (
                f"{emoji} **[{t.get('regional','')}] {t.get('categoria','')}** — {t.get('viagem','')}\n"
                f"📍 {t.get('origem','')} | 🕐 Saída plan. / 计划发车: **{t.get('saida_plan','')}** "
                f"| Bateu / 打卡: **{t.get('bateu_em','')}**"
            )}})

    elements.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": f"BRDrive Robot — JT Express | {agora}"}
    ]})

    cor = "red" if nao_bat else "green"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text",
                              "content": f"📊 BRDrive — Consolidado {datetime.now().strftime('%H:%M')} | Todas as Bases / 所有基地"},
                   "template": cor},
        "elements": elements,
    }


def enviar_consolidado(todos: list[dict], destinos: list[str]):
    """Envia o consolidado 6h para o SP Capacity Team."""
    if not todos:
        log.info("📊 Consolidado — nenhum registro hoje ainda")
        return
    if USAR_FEISHU:
        try:
            token = _get_token()
            card  = _card_consolidado(todos)
            for alvo in destinos:
                rid, rtype = _resolver_destino(token, alvo)
                _enviar_card_feishu(token, rid, card, rtype)
        except Exception as e:
            log.error(f"❌ Feishu consolidado falhou: {e}")


# ══════════════════════════════════════════════════════════
#  TESTE DIRETO
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=" * 55)
    print("  BRDrive Robot — Teste de Envio")
    print("=" * 55)

    # ── 1. Token ───────────────────────────────────────────
    print("\n1️⃣  Testando autenticação Feishu...")
    try:
        token = _get_token()
        print(f"   ✅ Token: {token[:25]}...")
    except Exception as e:
        print(f"   ❌ Falha: {e}")
        exit(1)

    # ── 2. Buscar Open ID ──────────────────────────────────
    print(f"\n2️⃣  Buscando Open ID de {EMAIL_TESTE_FEISHU}...")
    try:
        open_id = _open_id_por_email(token, EMAIL_TESTE_FEISHU)
        if open_id:
            print(f"   ✅ Open ID: {open_id}")
        else:
            print("   ❌ Usuário não encontrado — verifique a permissão contact:user.base:readonly")
            exit(1)
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        exit(1)

    # ── 3. Mensagem simples ────────────────────────────────
    print("\n3️⃣  Enviando mensagem simples de teste...")
    url  = f"{BASE_URL}/im/v1/messages?receive_id_type=open_id"
    body = {"receive_id": open_id, "msg_type": "text",
            "content": '{"text": "🤖 BRDrive Robot conectado! Teste de integração Feishu ✅"}'}
    resp = requests.post(url, headers=_headers(token), json=body, timeout=10)
    data = resp.json()
    if data.get("code") == 0:
        print("   ✅ Mensagem enviada! Verifique o Feishu.")
    else:
        print(f"   ❌ Erro: {data}")
        exit(1)

    # ── 4. Card de alertas ─────────────────────────────────
    print("\n4️⃣  Enviando card de alertas operacionais...")
    alertas_teste = [
        {"tipo": "SAÍDA NÃO REALIZADA", "id": "SRTR22601607300", "subtipo": "BRE-S18-0000-1",
         "transp": "JET SP", "condutor": "Carlos Alberto", "planejado": "14:00",
         "atraso_min": 45, "origem": "SP BRE", "destino": "DC SBN-SP"},
        {"tipo": "CHEGADA NÃO REALIZADA", "id": "SRTR22601616251", "subtipo": "BRE-S111-0000-2",
         "transp": "JET SP", "condutor": "Valdecir Gomes", "planejado": "16:30",
         "atraso_min": 60, "origem": "SC BRE 01", "destino": "S-JAB-SP"},
    ]
    enviar_alertas(alertas_teste)

    # ── 5. Card de ciclo JMS ───────────────────────────────
    print("\n5️⃣  Enviando card de ciclo JMS...")
    status_teste = [
        {"regional": "SPS", "viagem": "BRE-SPS-0001-1", "saida_plan": "10:00",
         "bateu": True, "bateu_em": "10:03", "categoria": "Coleta Base", "origem": "SP BRE"},
        {"regional": "SPE", "viagem": "BRE-SPE-0002-1", "saida_plan": "09:30",
         "bateu": False, "bateu_em": None, "categoria": "Secundária", "origem": "SJC-SP"},
    ]
    novos_teste = [
        {"regional": "SPS", "categoria": "Coleta PA", "viagem": "BRE-SPS-0003-1",
         "origem": "PA-Centro-SP", "destino": "DC SBN-SP", "condutor": "José da Silva",
         "transp": "JET SP", "saida_plan": "15:30", "min_restantes": 40},
    ]
    enviar_ciclo(status_teste, novos_teste, categoria="Coleta PA")

    print("\n" + "=" * 55)
    print("  ✅ Todos os testes concluídos!")
    print("  Verifique o Feishu — as mensagens devem ter chegado.")
    print("=" * 55)
