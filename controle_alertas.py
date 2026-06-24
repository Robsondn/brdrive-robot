"""
Controla quais viagens já receberam alerta hoje e rastreia se bateram no app.
Salva em JSON por data — reseta automaticamente a cada novo dia.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ControleAlertas")

ARQUIVO = Path(__file__).parent / "logs" / "alertas_enviados.json"


def _carregar() -> dict:
    try:
        if ARQUIVO.exists():
            with open(ARQUIVO, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _salvar(dados: dict):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def _dados_hoje() -> dict:
    hoje  = datetime.now().strftime("%Y-%m-%d")
    dados = _carregar()
    if dados.get("data") != hoje:
        dados = {"data": hoje, "alertas": {}}
    return dados


def filtrar_novos(alertas: list[dict]) -> list[dict]:
    """
    Recebe lista de alertas e retorna apenas os que ainda NÃO foram enviados hoje.
    Registra os novos automaticamente com bateu=False.
    """
    dados    = _dados_hoje()
    enviados = dados.get("alertas", {})
    novos    = []

    for a in alertas:
        chave = f"{a['id']}_{a['saida_plan']}"
        if chave not in enviados:
            novos.append(a)
            enviados[chave] = {
                "enviado_em": datetime.now().strftime("%H:%M"),
                "bateu":      False,
                "bateu_em":   None,
                "id":         a["id"],
                "viagem":     a.get("viagem", ""),
                "regional":   a.get("regional", ""),
                "categoria":  a.get("categoria", ""),
                "saida_plan": a.get("saida_plan", ""),
                "origem":     a.get("origem", ""),
            }

    dados["alertas"] = enviados
    _salvar(dados)

    ja_enviados = len(alertas) - len(novos)
    if ja_enviados:
        log.info(f"🔁 {ja_enviados} alerta(s) já enviado(s) hoje — ignorados")
    if novos:
        log.info(f"🆕 {len(novos)} alerta(s) novo(s) para enviar")

    return novos


def get_pendentes() -> list[dict]:
    """
    Retorna alertas de hoje cujo horário planejado JÁ PASSOU e ainda não bateram.
    Viagens cujo horário ainda não chegou não aparecem como anteriores.
    Viagens que já foram alertadas como "não bateu" são ignoradas.
    """
    agora    = datetime.now()
    dados    = _dados_hoje()
    enviados = dados.get("alertas", {})
    resultado = []
    for v in enviados.values():
        if v.get("bateu", False):
            continue
        if v.get("nao_bateu_alertado", False):
            continue
        try:
            h, m  = v["saida_plan"].split(":")
            saida = agora.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
            if saida <= agora:
                resultado.append(v)
        except Exception:
            resultado.append(v)
    return resultado


def marcar_nao_bateu_alertado(id_viagem: str, saida_plan: str):
    """Marca que o alerta de 'não bateu' já foi enviado — não repete mais."""
    dados    = _dados_hoje()
    enviados = dados.get("alertas", {})
    chave    = f"{id_viagem}_{saida_plan}"
    if chave in enviados:
        enviados[chave]["nao_bateu_alertado"] = True
    dados["alertas"] = enviados
    _salvar(dados)


def get_todos_hoje() -> list[dict]:
    """Retorna todos os registros do dia — bateu e não bateu."""
    dados = _dados_hoje()
    return list(dados.get("alertas", {}).values())


def get_periodo_consolidado(hora_inicio: int, hora_fim: int) -> list[dict]:
    """Retorna registros com saida_plan dentro da janela hora_inicio até hora_fim."""
    dados = _dados_hoje()
    resultado = []
    for t in dados.get("alertas", {}).values():
        try:
            h = int(t.get("saida_plan", "99:00").split(":")[0])
            if hora_inicio <= h < hora_fim:
                resultado.append(t)
        except Exception:
            pass
    return resultado


def filtrar_novos_lacre(lacres: list[dict]) -> list[dict]:
    """Retorna lacres ainda não alertados hoje."""
    dados    = _dados_hoje()
    enviados = dados.setdefault("lacres_alertados", {})
    novos    = []
    for l in lacres:
        if l["id"] not in enviados:
            novos.append(l)
            enviados[l["id"]] = {"hora_lacre": l["hora_lacre"], "enviado_em": datetime.now().strftime("%H:%M")}
    dados["lacres_alertados"] = enviados
    _salvar(dados)
    if novos:
        log.info(f"🔒 {len(novos)} lacre(s) novo(s) para alertar")
    return novos


def marcar_bateu(id_viagem: str, saida_plan: str, horario_real: str):
    """Marca uma viagem como bateu no app."""
    dados    = _dados_hoje()
    enviados = dados.get("alertas", {})
    chave    = f"{id_viagem}_{saida_plan}"
    if chave in enviados:
        enviados[chave]["bateu"]    = True
        enviados[chave]["bateu_em"] = horario_real
    dados["alertas"] = enviados
    _salvar(dados)
