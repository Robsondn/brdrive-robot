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
COL_PLAN_CHEG = "Tempo de chegada planejado"
COL_DESLACRE  = "Hora de Deslacre"


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


def _categoria_viagem(tipo: str, origem: str, saida_plan) -> str | None:
    """Mesma regra de categoria usada em verificar_lacre_df - Coleta PA /
    Coleta Base / Devolução / Secundária. None quando nao se enquadra."""
    tipo_upper = (tipo or "").strip().upper()
    origem_upper = (origem or "").strip().upper()
    if "COLETA" in tipo_upper:
        if origem_upper.startswith("PA"):
            return "Coleta PA"
        if saida_plan is None or pd.isna(saida_plan) or saida_plan.hour >= 13:
            return "Coleta Base"
        return "Devolução"
    if "ENTREGA" in tipo_upper:
        return "Secundária"
    return None


def _dc_base_sentido(origem: str, chegada: str) -> tuple[str, str, str]:
    """SP BRE sempre vira grupo proprio nos dois sentidos (saindo ou
    chegando), mesmo quando o outro lado e um DC de verdade - pedido em
    19/11/2026, diferente da regra do relatorio_pontualidade.py/
    processador.py (onde SP BRE so vira DC quando o outro lado NAO e um DC).
    Fora isso, o lado que comeca com "DC " e o DC da viagem, o outro lado e
    a "base"."""
    o = (origem or "").strip()
    c = (chegada or "").strip()
    if o == "SP BRE":
        return o, c, "DC -> Base"
    if c == "SP BRE":
        return c, o, "Base -> DC"
    if o.upper().startswith("DC "):
        return o, c, "DC -> Base"
    if c.upper().startswith("DC "):
        return c, o, "Base -> DC"
    return "SEM DC E SEM SP BRE", f"{o} -> {c}", "Direto (sem DC)"


def verificar_atraso_lacre_df(df: "pd.DataFrame") -> list[dict]:
    """Retorna viagens (SPS) onde o lacre e/ou o deslacre aconteceram DEPOIS
    do planejado - mesmo que so por 1 minuto. Diferente de verificar_lacre_df
    (que so avisa "lacre feito", sem checar atraso): aqui a viagem so entra
    se tiver prova concreta de atraso (lacre/deslacre registrado e atrasado),
    pra operacao poder cobrar o responsavel. Pedido em 19/11/2026."""
    hoje = datetime.now().date()
    resultado = []

    for _, r in df.iterrows():
        regional = str(r.get(COL_REGIONAL, "")).strip().upper()
        if regional not in REGIONAIS_ALVO:
            continue

        saida_plan = pd.to_datetime(r.get(COL_PLAN), errors="coerce")
        cheg_plan  = pd.to_datetime(r.get(COL_PLAN_CHEG), errors="coerce")

        lacre_dt = pd.to_datetime(r.get(COL_LACRE), errors="coerce")
        if pd.notna(lacre_dt) and lacre_dt.date() != hoje:
            lacre_dt = pd.NaT
        deslacre_dt = pd.to_datetime(r.get(COL_DESLACRE), errors="coerce")
        if pd.notna(deslacre_dt) and deslacre_dt.date() != hoje:
            deslacre_dt = pd.NaT

        atraso_lacre_min = (
            (lacre_dt - saida_plan).total_seconds() / 60
            if pd.notna(lacre_dt) and pd.notna(saida_plan) else None
        )
        atraso_deslacre_min = (
            (deslacre_dt - cheg_plan).total_seconds() / 60
            if pd.notna(deslacre_dt) and pd.notna(cheg_plan) else None
        )

        lacre_atrasado    = atraso_lacre_min is not None and atraso_lacre_min > 0
        deslacre_atrasado = atraso_deslacre_min is not None and atraso_deslacre_min > 0
        if not (lacre_atrasado or deslacre_atrasado):
            continue

        tipo = str(r.get(COL_TIPO, "")).strip().upper()
        origem  = str(r.get(COL_ORIGEM, ""))
        destino = str(r.get(COL_DESTINO, ""))
        dc, base, sentido = _dc_base_sentido(origem, destino)
        categoria = _categoria_viagem(tipo, origem, saida_plan)

        resultado.append({
            "id":                   str(r.get(COL_ID, "")),
            "viagem":               str(r.get(COL_VIAGEM, "")),
            "condutor":             str(r.get(COL_CONDUTOR, "")),
            "telefone":             str(r.get(COL_TELEFONE, "") or ""),
            "transportador":        str(r.get(COL_TRANSP, "") or ""),
            "tipo_linha":           tipo,
            "categoria":            categoria,
            "dc":                   dc,
            "base":                 base,
            "sentido":              sentido,
            "saida_plan":           saida_plan.strftime("%H:%M") if pd.notna(saida_plan) else None,
            "hora_lacre":           lacre_dt.strftime("%H:%M") if pd.notna(lacre_dt) else None,
            "atraso_lacre_min":     int(atraso_lacre_min) if lacre_atrasado else None,
            "cheg_plan":            cheg_plan.strftime("%H:%M") if pd.notna(cheg_plan) else None,
            "hora_deslacre":        deslacre_dt.strftime("%H:%M") if pd.notna(deslacre_dt) else None,
            "atraso_deslacre_min":  int(atraso_deslacre_min) if deslacre_atrasado else None,
        })

    log.info(f"Atrasos de lacre/deslacre encontrados: {len(resultado)}")
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
            "telefone":      str(r.get(COL_TELEFONE, "") or ""),
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
