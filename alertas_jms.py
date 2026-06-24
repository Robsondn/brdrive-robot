"""
Verifica o relatório JMS e gera alertas 1 hora antes da saída planejada.
Filtros: Status = Programado | Regional = SPS ou SPE
Categorias:
  - Coleta PA    → Nome de estação de partida começa com "PA"
  - Devolução    → Tipo de linha = Coleta, saída planejada 00:00–13:00
  - Coleta Base  → Tipo de linha = Coleta, saída planejada 13:00–00:00
  - Secundária   → Tipo de linha = Entrega
"""

import logging
import pandas as pd
from datetime import datetime, timedelta

log = logging.getLogger("AlertasJMS")

REGIONAIS_ALVO   = {"SPS"}
ANTECEDENCIA_MIN = 60

COL_ID       = "Número do ID"
COL_STATUS   = "Status"
COL_VIAGEM   = "Nome da viagem"
COL_TIPO     = "Tipo de linha"
COL_CONDUTOR = "Condutor"
COL_ORIGEM   = "Nome de estação de partida"
COL_DESTINO  = "Nome de estação de chegada"
COL_REGIONAL = "Regional de saída do carro"
COL_PLAN     = "Tempo de partida planejada"
COL_REAL     = "Horário real de saída"
COL_PLACA    = "Placa do carro"
COL_TRANSP   = "Abreviatura de transportador"
COL_LACRE    = "Hora de Lacre"
COL_TELEFONE = "Telefone do Carro"


def verificar_lacre_df(df: "pd.DataFrame") -> list[dict]:
    """
    Retorna viagens Coleta Base (SPS) que receberam lacre hoje.
    Usado para monitorar e alertar para dar baixa no ID.
    """
    hoje = datetime.now().date()
    resultado = []

    for _, r in df.iterrows():
        # Só regional SPS
        regional = str(r.get(COL_REGIONAL, "")).strip().upper()
        if regional not in REGIONAIS_ALVO:
            continue

        # Deve ter hora de lacre preenchida com data de hoje
        hora_lacre_raw = r.get(COL_LACRE, "")
        if not hora_lacre_raw or str(hora_lacre_raw).strip() in ["", "-", "nan", "NaT"]:
            continue
        try:
            lacre_dt = pd.to_datetime(hora_lacre_raw)
            if lacre_dt.date() != hoje:
                continue
        except Exception:
            continue

        origem     = str(r.get(COL_ORIGEM, "")).strip().upper()
        tipo       = str(r.get(COL_TIPO,   "")).strip().upper()
        saida_plan = pd.to_datetime(r.get(COL_PLAN), errors="coerce")

        if "COLETA" in tipo:
            if origem.startswith("PA"):
                categoria = "Coleta PA"
            elif pd.isna(saida_plan) or saida_plan.hour >= 13:
                categoria = "Coleta Base"
            else:
                categoria = "Devolução"
        elif "ENTREGA" in tipo:
            categoria = "Secundária"
        else:
            continue

        resultado.append({
            "id":         str(r.get(COL_ID,       "")),
            "viagem":     str(r.get(COL_VIAGEM,   "")),
            "condutor":   str(r.get(COL_CONDUTOR, "")),
            "telefone":   str(r.get(COL_TELEFONE, "") or ""),
            "origem":     str(r.get(COL_ORIGEM,   "")),
            "destino":    str(r.get(COL_DESTINO,  "")),
            "categoria":  categoria,
            "hora_lacre": lacre_dt.strftime("%H:%M"),
        })

    log.info(f"Lacres encontrados: {len(resultado)}")
    return resultado


def _categorizar(tipo_linha: str, origem: str, hora_plan: datetime) -> str | None:
    """
    Retorna a categoria da viagem ou None se não se enquadrar.
    Prioridade: Coleta PA > Devolução > Coleta Base > Secundária
    """
    origem_upper = str(origem).strip().upper()
    tipo_upper   = str(tipo_linha).strip().upper()

    # 1° Coleta PA — estação de partida começa com "PA"
    if origem_upper.startswith("PA"):
        return "Coleta PA"

    if "COLETA" in tipo_upper:
        # 2° Devolução — saída entre 00:00 e 13:00
        if hora_plan.hour < 13:
            return "Devolução"
        # 3° Coleta Base — saída entre 13:00 e 00:00
        return "Coleta Base"

    if "ENTREGA" in tipo_upper:
        return "Secundária"

    return None  # outros tipos ignorados


def verificar_alertas(caminho_excel: str) -> list[dict]:
    """
    Lê o arquivo Excel do JMS e retorna alertas para viagens:
    - Status contém "Programado"
    - Regional SPS ou SPE
    - Saída planejada entre agora e agora + 60 min
    - Ainda não saíram
    """
    agora  = datetime.now()
    limite = agora + timedelta(minutes=ANTECEDENCIA_MIN)

    try:
        df = pd.read_excel(caminho_excel)
    except Exception as e:
        log.error(f"Erro ao ler {caminho_excel}: {e}")
        return []

    log.info(f"Arquivo lido: {len(df)} linhas")

    alertas = []
    for _, r in df.iterrows():

        # ── Filtro 1: Status deve conter "Programado" ─────────────────
        status = str(r.get(COL_STATUS, "")).strip()
        if "programado" not in status.lower():
            continue

        # ── Filtro 2: Regional SPS ou SPE ─────────────────────────────
        regional = str(r.get(COL_REGIONAL, "")).strip().upper()
        if regional not in REGIONAIS_ALVO:
            continue

        # ── Filtro 3: Ainda não saiu ───────────────────────────────────
        saida_real = r.get(COL_REAL)
        if pd.notna(saida_real) and str(saida_real).strip() not in ["", "-", "nan"]:
            continue

        # ── Filtro 4: Saída planejada dentro de 1h ─────────────────────
        saida_plan = pd.to_datetime(r.get(COL_PLAN), errors="coerce")
        if pd.isna(saida_plan):
            continue
        saida_plan_dt = saida_plan.to_pydatetime()
        if not (agora <= saida_plan_dt <= limite):
            continue

        # ── Categorizar ────────────────────────────────────────────────
        categoria = _categorizar(
            r.get(COL_TIPO, ""),
            r.get(COL_ORIGEM, ""),
            saida_plan_dt,
        )
        if categoria is None:
            continue

        minutos_restantes = int((saida_plan_dt - agora).total_seconds() / 60)

        alertas.append({
            "id":            str(r.get(COL_ID, "")),
            "status":        status,
            "categoria":     categoria,
            "viagem":        str(r.get(COL_VIAGEM, "")),
            "regional":      regional,
            "origem":        str(r.get(COL_ORIGEM, "")),
            "destino":       str(r.get(COL_DESTINO, "")),
            "condutor":      str(r.get(COL_CONDUTOR, "")),
            "transp":        str(r.get(COL_TRANSP, "")),
            "placa":         str(r.get(COL_PLACA, "")),
            "saida_plan":    saida_plan_dt.strftime("%H:%M"),
            "min_restantes": minutos_restantes,
        })

    log.info(f"Alertas gerados: {len(alertas)}")
    return alertas


def verificar_alertas_df(df: pd.DataFrame) -> list[dict]:
    """Igual a verificar_alertas mas recebe DataFrame diretamente (sem Excel)."""
    agora  = datetime.now()
    limite = agora + timedelta(minutes=ANTECEDENCIA_MIN)
    alertas = []
    for _, r in df.iterrows():
        status = str(r.get(COL_STATUS, "")).strip()
        if "programado" not in status.lower():
            continue
        regional = str(r.get(COL_REGIONAL, "")).strip().upper()
        if regional not in REGIONAIS_ALVO:
            continue
        saida_real = r.get(COL_REAL)
        if pd.notna(saida_real) and str(saida_real).strip() not in ["", "-", "nan"]:
            continue
        saida_plan = pd.to_datetime(r.get(COL_PLAN), errors="coerce")
        if pd.isna(saida_plan):
            continue
        saida_plan_dt = saida_plan.to_pydatetime()
        if not (agora <= saida_plan_dt <= limite):
            continue
        categoria = _categorizar(r.get(COL_TIPO, ""), r.get(COL_ORIGEM, ""), saida_plan_dt)
        if categoria is None:
            continue
        minutos_restantes = int((saida_plan_dt - agora).total_seconds() / 60)
        alertas.append({
            "id":            str(r.get(COL_ID, "")),
            "status":        status,
            "categoria":     categoria,
            "viagem":        str(r.get(COL_VIAGEM, "")),
            "regional":      regional,
            "origem":        str(r.get(COL_ORIGEM, "")),
            "destino":       str(r.get(COL_DESTINO, "")),
            "condutor":      str(r.get(COL_CONDUTOR, "")),
            "transp":        str(r.get(COL_TRANSP, "")),
            "placa":         str(r.get(COL_PLACA, "")),
            "saida_plan":    saida_plan_dt.strftime("%H:%M"),
            "min_restantes": minutos_restantes,
        })
    log.info(f"Alertas gerados: {len(alertas)}")
    return alertas


def verificar_status_anteriores(df: "pd.DataFrame", pendentes: list[dict]) -> list[dict]:
    """
    Para cada alerta pendente verifica se o 'Horário real de saída' foi preenchido.
    Retorna lista com campo 'bateu' (bool) e 'bateu_em' (str HH:MM ou None).
    """
    resultados = []
    for p in pendentes:
        linhas = df[df[COL_ID].astype(str) == str(p["id"])]
        if linhas.empty:
            resultados.append({**p, "bateu": False, "bateu_em": None})
            continue

        horario_real = linhas.iloc[0].get(COL_REAL)
        bateu = (
            pd.notna(horario_real)
            and str(horario_real).strip() not in {"", "-", "nan", "NaT"}
        )
        bateu_em = None
        if bateu:
            try:
                bateu_em = pd.to_datetime(horario_real).strftime("%H:%M")
            except Exception:
                bateu_em = str(horario_real)[:5]

        resultados.append({**p, "bateu": bateu, "bateu_em": bateu_em})

    return resultados
