"""
JMS API Extractor — sem downloads, sem cliques.
Busca dados direto da API usando o YL_TOKEN do Edge já aberto.
"""

import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

log = logging.getLogger("JMS_API")

API_BASE  = "https://gw.jtjms-br.com"
PAGE_SIZE = 100

# Token manual de fallback — usado se o Edge não estiver acessível
TOKEN_MANUAL = "4bbe8fb9cc694263b6c1a46ac5186541"

_ESTADO_MAP = {1: "Programado", 4: "Em andamento", 5: "Programado"}
_TIPO_MAP   = {1: "Coleta", 2: "Entrega"}


def _obter_token() -> str | None:
    """Extrai YL_TOKEN do Edge aberto na porta 9222. Usa TOKEN_MANUAL como fallback."""
    try:
        options = Options()
        options.add_experimental_option("debuggerAddress", "localhost:9222")
        driver = webdriver.Edge(options=options)
        token = driver.execute_script("return localStorage.getItem('YL_TOKEN')")
        if token:
            log.info("✅ YL_TOKEN obtido do navegador")
            _salvar_token_db(token)
            return token
        log.warning("⚠️ YL_TOKEN não encontrado no localStorage — usando token manual")
    except Exception as e:
        log.warning(f"⚠️ Erro ao conectar ao Edge: {e} — usando token manual")

    if TOKEN_MANUAL:
        log.info("✅ Usando TOKEN_MANUAL")
        _salvar_token_db(TOKEN_MANUAL)
        return TOKEN_MANUAL

    log.error("❌ Nenhum token disponível")
    return None


def _headers(token: str) -> dict:
    return {
        "Accept":           "application/json, text/plain, */*",
        "Accept-Encoding":  "gzip, deflate, br, zstd",
        "Accept-Language":  "pt-BR,pt;q=0.9,en;q=0.8",
        "Authtoken":        token,
        "Content-Type":     "application/json;charset=utf-8",
        "Lang":             "PT",
        "Langtype":         "PT",
        "Origin":           "https://jmsbr.jtjms-br.com",
        "Referer":          "https://jmsbr.jtjms-br.com/",
        "Routename":        "transportSynthesizeReport",
        "Timezone":         "GMT-0300",
    }


def _salvar_token_db(token: str):
    """Salva o token no PostgreSQL compartilhado para uso pelo extrator JMS no Render."""
    try:
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            return
        from sqlalchemy import create_engine, text
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS jms_config (
                    chave TEXT PRIMARY KEY,
                    valor TEXT,
                    atualizado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                INSERT INTO jms_config (chave, valor, atualizado)
                VALUES ('YL_TOKEN', :v, CURRENT_TIMESTAMP)
                ON CONFLICT (chave) DO UPDATE SET valor = :v, atualizado = CURRENT_TIMESTAMP
            """), {"v": token})
            conn.commit()
        log.info("Token salvo no banco compartilhado (Render)")
    except Exception as e:
        log.warning(f"Nao foi possivel salvar token no banco: {e}")


def _verificar_token(token: str) -> bool:
    try:
        url  = f"{API_BASE}/transportation/checkToken"
        resp = requests.get(url, headers=_headers(token), timeout=10)
        return resp.json().get("data") is True
    except Exception:
        return False


def _buscar_todos(token: str) -> list[dict]:
    hoje     = datetime.now()
    data_ini = hoje.strftime("%Y-%m-%d") + " 00:00:00"
    data_fim = hoje.strftime("%Y-%m-%d") + " 23:59:59"
    url      = f"{API_BASE}/transportation/tmsBranchShipmentEvent/report"

    registros     = []
    pagina        = 1
    total_paginas = 1
    total         = 0

    while pagina <= total_paginas:
        params = {
            "current":                    pagina,
            "size":                       PAGE_SIZE,
            "plannedDepartureStartTime":  data_ini,
            "plannedDepartureEndTime":    data_fim,
            "source":                     1,
        }
        resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
        data = resp.json()

        if not data.get("succ"):
            log.error(f"❌ Erro na API: {data.get('msg')}")
            break

        pd_data  = data.get("data", {})
        records  = pd_data.get("records", [])

        # Só atualiza o total de páginas se a API retornar valor válido (>= página atual)
        pages_resp = pd_data.get("pages", 0)
        if pages_resp and pages_resp >= pagina:
            total_paginas = pages_resp
        total_resp = pd_data.get("total", 0)
        if total_resp:
            total = total_resp

        registros.extend(records)
        log.info(f"   Página {pagina}/{total_paginas} — {len(registros)}/{total} registros")

        pagina += 1
        if pagina <= total_paginas:
            time.sleep(0.3)

    return registros


def _para_df(registros: list[dict]) -> pd.DataFrame:
    """Converte registros JSON para DataFrame com colunas no formato de alertas_jms.py."""
    linhas = []
    for r in registros:
        linhas.append({
            "Número do ID":                 r.get("shipmentNo", ""),
            "Status":                       _ESTADO_MAP.get(r.get("shipmentState"), "Outro"),
            "Nome da viagem":               r.get("shipmentSimpleName", ""),
            "Tipo de linha":                _TIPO_MAP.get(r.get("distributionType"), ""),
            "Condutor":                     r.get("driverName") or "",
            "Nome de estação de partida":   r.get("sendNetworkName", ""),
            "Nome de estação de chegada":   r.get("arriveNetworkName", ""),
            "Regional de saída do carro":   r.get("sendRegionalAgent", ""),
            "Tempo de partida planejada":   r.get("plannedDepartureTime", ""),
            "Horário real de saída":        r.get("actualDepartureTime") or "",
            "Placa do carro":               r.get("plateNumber") or "",
            "Abreviatura de transportador": r.get("carrierShortName") or "",
            "Hora de Lacre":               r.get("scanTime") or "",
            "Telefone do Carro":            r.get("driverContact") or "",
        })
    return pd.DataFrame(linhas)


def extrair() -> pd.DataFrame | None:
    """Extrai todos os dados do dia via API e retorna DataFrame."""
    log.info("=" * 55)
    log.info(f"🤖 Extração via API — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log.info("=" * 55)

    token = _obter_token()
    if not token:
        return None

    registros = _buscar_todos(token)
    if not registros:
        log.error("❌ Nenhum dado retornado pela API")
        return None

    df = _para_df(registros)
    log.info(f"✅ {len(df)} registros obtidos via API")
    return df
