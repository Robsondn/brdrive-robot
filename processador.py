"""
╔══════════════════════════════════════════════════════════╗
║         BRDrive - Processador de Dados                   ║
║  Lê o Excel do JMS e aplica todas as lógicas de negócio  ║
╚══════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

log = logging.getLogger("Processador")


# ── HELPERS ───────────────────────────────────────────────────────────────────
def is_valid(val) -> bool:
    """Verifica se o valor é uma data/hora válida (não é '-', 'OFF', vazio)"""
    if pd.isna(val):
        return False
    return str(val).strip() not in ["-", "OFF", "", "nan"]


def to_ts(val):
    try:
        return pd.Timestamp(val)
    except Exception:
        return None


# ── LÓGICAS POR COLUNA ────────────────────────────────────────────────────────
def calc_status_lacre(lacre) -> str:
    return "OK" if is_valid(lacre) else "OFF"


def calc_status_deslacre(deslacre) -> str:
    return "OK" if is_valid(deslacre) else "OFF"


def calc_tempo_saida_off(saida_real) -> str:
    return "OK" if is_valid(saida_real) else "OFF"


def calc_tempo_chegada_off(cheg_real) -> str:
    return "OK" if is_valid(cheg_real) else "OFF"


def calc_status_tempo(saida_real, cheg_real) -> str:
    t_s = is_valid(saida_real)
    t_c = is_valid(cheg_real)
    if t_s and t_c:
        return "OK"
    if not t_s:
        return "OFF SAIDA"
    return "OFF CHEGADA"


def calc_saida_prazo(saida_real, saida_plan, lacre) -> str:
    """No Prazo / Atrasado para saída"""
    ref = to_ts(saida_real) if is_valid(saida_real) else to_ts(lacre) if is_valid(lacre) else None
    if ref is None:
        return "Atrasado"
    plan = to_ts(saida_plan)
    if plan is None:
        return "No Prazo"
    return "No Prazo" if ref <= plan else "Atrasado"


def calc_chegada_prazo(cheg_real, cheg_plan, deslacre) -> str:
    """No Prazo / Atrasado para chegada"""
    ref = to_ts(cheg_real) if is_valid(cheg_real) else to_ts(deslacre) if is_valid(deslacre) else None
    if ref is None:
        return "Atrasado"
    plan = to_ts(cheg_plan)
    if plan is None:
        return "No Prazo"
    return "No Prazo" if ref <= plan else "Atrasado"


# Para o BRDrive usa terminologia diferente
def calc_pontualidade_saida(saida_real, saida_plan, lacre) -> str | None:
    ref = to_ts(saida_real) if is_valid(saida_real) else to_ts(lacre) if is_valid(lacre) else None
    if ref is None:
        return None  # Sem registro = NaN no BRDrive
    plan = to_ts(saida_plan)
    if plan is None:
        return "No prazo"
    return "No prazo" if ref <= plan else "Fora do prazo"


def calc_pontualidade_chegada(cheg_real, cheg_plan, deslacre) -> str | None:
    ref = to_ts(cheg_real) if is_valid(cheg_real) else to_ts(deslacre) if is_valid(deslacre) else None
    if ref is None:
        return None
    plan = to_ts(cheg_plan)
    if plan is None:
        return "No prazo"
    return "No prazo" if ref <= plan else "Fora do prazo"


def calc_execucao_saida(saida_real) -> str:
    return "Fez" if is_valid(saida_real) else "Não fez"


# ── COLUNAS DO DATABASE ───────────────────────────────────────────────────────
DB_COLS = {
    "id":          "Número do ID\nID编号",
    "status":      "Status\n状态",
    "tipo_linha":  "Tipo de linha\n线路类型",
    "subtipo":     "Subtipo de linha\n线路子类型",
    "transp":      "Transportador\n承运商",
    "data":        "DATA\n日期",
    "hora":        "HORA",
    "origem":      "ORIGEM\n出发地",
    "chegada":     "Chegada\n到达",
    "tipo_op":     "TIPO DE OPERAÇÃO\n操作类型",
    "saida_plan":  "Tempo de partida planejada\n计划出发时间",
    "saida_real":  "Horário real de saída\n实际出发时间",
    "cheg_plan":   "Tempo de chegada planejado\n计划到达时间",
    "cheg_real":   "Tempo real de chegada\n实际到达时间",
    "condutor":    "CONDUTOR",
    "lacre":       "Horário de lacração do veículo",
    "deslacre":    "Horário de deslacração do veículo",
    "st_lacre":    "STATUS LACRE  SAIDA ",
    "st_deslacre": "STATUS DESLACRE CHEGADA ",
    "responsavel": "RESPONSAVEL ",
    "mes":         "MÊS",
    "t_saida_off": "Tempo Saida OFF",
    "t_cheg_off":  "Tempo chegada OFF",
    "st_tempo":    "STATUS TEMPO ON/OFF",
    "motivos":     "Status  Motivos ",
    "saida_prazo": "SAIDA NO PRAZO. ATRASADO, ",
    "cheg_prazo":  "CHEGADA NO PRAZO. ATRASADO, ",
    "base_pa":     "BASE/PA",
    "se_ba_dev":   "SE/BA/DEV",
    "filial":      "Filial/Regional de Origem",
    "ano":         "ano",
}

# ── PROCESSADOR PRINCIPAL ─────────────────────────────────────────────────────
def processar_database(df: pd.DataFrame, datas_alvo: list[str]) -> pd.DataFrame:
    """
    Recebe o DataFrame do Database e preenche as colunas
    das datas especificadas.
    """
    df["_data"] = pd.to_datetime(df[DB_COLS["data"]], errors="coerce")
    mask = df["_data"].dt.date.astype(str).isin(datas_alvo)
    idx  = df[mask].index

    log.info(f"Processando {len(idx)} linhas para: {datas_alvo}")

    subset = df.loc[idx]

    df.loc[idx, DB_COLS["st_lacre"]]    = subset[DB_COLS["lacre"]].apply(calc_status_lacre)
    df.loc[idx, DB_COLS["st_deslacre"]] = subset[DB_COLS["deslacre"]].apply(calc_status_deslacre)
    df.loc[idx, DB_COLS["t_saida_off"]] = subset[DB_COLS["saida_real"]].apply(calc_tempo_saida_off)
    df.loc[idx, DB_COLS["t_cheg_off"]]  = subset[DB_COLS["cheg_real"]].apply(calc_tempo_chegada_off)

    df.loc[idx, DB_COLS["st_tempo"]] = subset.apply(
        lambda r: calc_status_tempo(r[DB_COLS["saida_real"]], r[DB_COLS["cheg_real"]]), axis=1
    )
    df.loc[idx, DB_COLS["saida_prazo"]] = subset.apply(
        lambda r: calc_saida_prazo(r[DB_COLS["saida_real"]], r[DB_COLS["saida_plan"]], r[DB_COLS["lacre"]]), axis=1
    )
    df.loc[idx, DB_COLS["cheg_prazo"]] = subset.apply(
        lambda r: calc_chegada_prazo(r[DB_COLS["cheg_real"]], r[DB_COLS["cheg_plan"]], r[DB_COLS["deslacre"]]), axis=1
    )

    df.drop(columns=["_data"], inplace=True)
    log.info("✅ Database processado!")
    return df


def processar_brdrive(df_br: pd.DataFrame, df_db: pd.DataFrame, datas_alvo: list[str]) -> pd.DataFrame:
    """
    Monta as linhas novas para o BRDrive a partir do Database
    e as adiciona ao final do arquivo existente.
    """
    df_db["_data"] = pd.to_datetime(df_db[DB_COLS["data"]], errors="coerce")
    novos = df_db[df_db["_data"].dt.date.astype(str).isin(datas_alvo)].copy()

    log.info(f"Adicionando {len(novos)} linhas ao BRDrive...")

    rows = []
    for _, r in novos.iterrows():
        sr  = r[DB_COLS["saida_real"]]
        cr  = r[DB_COLS["cheg_real"]]
        lac = r[DB_COLS["lacre"]]
        des = r[DB_COLS["deslacre"]]
        rows.append({
            "Número do ID":                     r[DB_COLS["id"]],
            "Status":                           r[DB_COLS["status"]],
            "Tipo de linha":                    r[DB_COLS["tipo_linha"]],
            "Subtipo de linha":                 r[DB_COLS["subtipo"]],
            "Transportador":                    r[DB_COLS["transp"]],
            "DATA":                             r[DB_COLS["data"]],
            "MÊS":                              r[DB_COLS["mes"]],
            "ORIGEM":                           r[DB_COLS["origem"]],
            "Chegada":                          r[DB_COLS["chegada"]],
            "TIPO DE OPERAÇÃO":                 r[DB_COLS["tipo_op"]],
            "Tempo de partida planejada":        r[DB_COLS["saida_plan"]],
            "Horário real de saída":             sr,
            "Tempo de chegada planejado":        r[DB_COLS["cheg_plan"]],
            "Tempo real de chegada":             cr,
            "Tempo Saida OFF":                  calc_tempo_saida_off(sr),
            "Tempo chegada OFF":                calc_tempo_chegada_off(cr),
            "BASE/PA":                          r[DB_COLS["base_pa"]],
            "CONDUTOR":                         r[DB_COLS["condutor"]],
            "RESPONSAVEL":                      r[DB_COLS["responsavel"]],
            "PONTUALIDADE SAÍDA":               calc_pontualidade_saida(sr, r[DB_COLS["saida_plan"]], lac),
            "PONTUALIDADE CHEGADA":             calc_pontualidade_chegada(cr, r[DB_COLS["cheg_plan"]], des),
            "EXECUÇÃO SAÍDA":                   calc_execucao_saida(sr),
            "Horário de lacração do veículo":   lac,
            "Horário de deslacração do veículo": des,
            "STATUS LACRE SAIDA":               calc_status_lacre(lac),
            "STATUS DESLACRE CHEGADA":          calc_status_deslacre(des),
        })

    df_novos = pd.DataFrame(rows, columns=df_br.columns)
    df_final = pd.concat([df_br, df_novos], ignore_index=True)

    df_db.drop(columns=["_data"], inplace=True)
    log.info(f"✅ BRDrive: {len(df_br)} + {len(df_novos)} = {len(df_final)} linhas")
    return df_final


# ── DETECTAR DATAS NOVAS ──────────────────────────────────────────────────────
def detectar_datas_novas(df_db: pd.DataFrame, df_br: pd.DataFrame) -> list[str]:
    """
    Retorna as datas que existem no Database mas ainda não
    foram adicionadas ao BRDrive.
    """
    datas_db = set(
        pd.to_datetime(df_db[DB_COLS["data"]], errors="coerce")
        .dt.date.astype(str).dropna().unique()
    )
    datas_br = set(
        pd.to_datetime(df_br["DATA"], errors="coerce")
        .dt.date.astype(str).dropna().unique()
    )
    novas = sorted(datas_db - datas_br)
    log.info(f"📅 Datas novas detectadas: {novas}")
    return novas


# ── GERAR ALERTAS ─────────────────────────────────────────────────────────────
def gerar_alertas(df_db: pd.DataFrame, data_hoje: str) -> list[dict]:
    """
    Retorna lista de viagens que precisam de alerta:
    - Saída planejada passou e não houve saída real
    - Chegada planejada passou e não houve chegada real
    """
    df_db["_data"] = pd.to_datetime(df_db[DB_COLS["data"]], errors="coerce")
    hoje = df_db[df_db["_data"].dt.date.astype(str) == data_hoje].copy()
    agora = datetime.now()
    alertas = []

    for _, r in hoje.iterrows():
        saida_plan = to_ts(r[DB_COLS["saida_plan"]])
        cheg_plan  = to_ts(r[DB_COLS["cheg_plan"]])
        saida_real = r[DB_COLS["saida_real"]]
        cheg_real  = r[DB_COLS["cheg_real"]]

        # Alerta de saída: planejado passou há mais de 30min e não saiu
        if saida_plan and saida_plan < pd.Timestamp(agora):
            atraso = (pd.Timestamp(agora) - saida_plan).total_seconds() / 60
            if atraso > 30 and not is_valid(saida_real):
                alertas.append({
                    "tipo": "SAÍDA NÃO REALIZADA",
                    "id": r[DB_COLS["id"]],
                    "subtipo": r[DB_COLS["subtipo"]],
                    "transp": r[DB_COLS["transp"]],
                    "condutor": r[DB_COLS["condutor"]],
                    "planejado": saida_plan.strftime("%H:%M"),
                    "atraso_min": int(atraso),
                    "origem": r[DB_COLS["origem"]],
                    "destino": r[DB_COLS["chegada"]],
                })

        # Alerta de chegada: planejado passou há mais de 30min e não chegou
        if cheg_plan and cheg_plan < pd.Timestamp(agora):
            atraso = (pd.Timestamp(agora) - cheg_plan).total_seconds() / 60
            if atraso > 30 and not is_valid(cheg_real):
                alertas.append({
                    "tipo": "CHEGADA NÃO REALIZADA",
                    "id": r[DB_COLS["id"]],
                    "subtipo": r[DB_COLS["subtipo"]],
                    "transp": r[DB_COLS["transp"]],
                    "condutor": r[DB_COLS["condutor"]],
                    "planejado": cheg_plan.strftime("%H:%M"),
                    "atraso_min": int(atraso),
                    "origem": r[DB_COLS["origem"]],
                    "destino": r[DB_COLS["chegada"]],
                })

    df_db.drop(columns=["_data"], inplace=True)
    log.info(f"🚨 {len(alertas)} alertas gerados para {data_hoje}")
    return alertas
