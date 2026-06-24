"""
BRDrive Robot — Alertas JMS
Extrai o relatório do JMS a cada 20 min e alerta 1h antes da saída planejada.
Regionais monitoradas: SPS e SPE.

PRE-REQUISITO:
    1. Rode iniciar_edge.bat
    2. Faca login no JMS no Edge que abriu
    3. Deixe o Edge aberto

USO:
    py main_teste.py            # roda continuamente a cada 20min
    py main_teste.py --agora    # roda uma vez agora
"""

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

from jms_api import extrair
from alertas_jms import verificar_alertas_df, verificar_status_anteriores, verificar_lacre_df
from faishu_alertas import enviar_ciclo, enviar_consolidado, enviar_alerta_sistema, enviar_lacre, EMAIL_TESTE_FEISHU
from controle_alertas import filtrar_novos, get_pendentes, marcar_bateu, marcar_nao_bateu_alertado, get_periodo_consolidado, filtrar_novos_lacre

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
INTERVALO_MIN = 10
LOG_DIR       = str(Path(__file__).parent / "logs")

# Destinos por categoria — grupos Feishu oficiais
DESTINOS_POR_CATEGORIA = {
    "Coleta PA":   ["oc_1556816c77234f5529f1fccb4db3894a"],  # COMUNICAÇÃO DE COLETA PA
    "Coleta Base": ["https://open.feishu.cn/open-apis/bot/v2/hook/657a4391-96f1-4265-9318-3bcb20e3f016"],  # SPS Comunicado de Coleta SPS-揽收沟通群组
    "Devolução":   ["https://open.feishu.cn/open-apis/bot/v2/hook/6792e216-070f-4eaf-b516-956b5287895e"],
    "Secundária":  ["https://open.feishu.cn/open-apis/bot/v2/hook/6792e216-070f-4eaf-b516-956b5287895e"],
}

# Grupo principal — consolidado às 17h, 23h, 05h, 11h
WEBHOOK_LACRE        = "https://open.feishu.cn/open-apis/bot/v2/hook/077815d5-8b39-4249-9e3d-77cdd0cf2039"  # Coleta PA + Coleta Base
WEBHOOK_LACRE_SD     = "https://open.feishu.cn/open-apis/bot/v2/hook/0fca0c24-6b2d-401e-b627-e4685ef21650"  # Secundária + Devolução
GRUPO_CAPACITY       = "oc_fa69c6ad9e23492413590bdb9fba7079"  # SP Capacity Team
HORARIOS_CONSOLIDADO = {17, 23, 5, 11}
# Janela de cada horário: hora_inicio → hora_fim
_JANELA = {17: (11, 17), 23: (17, 23), 5: (23, 5), 11: (5, 11)}

# ── LOGGING ───────────────────────────────────────────────────────────────────
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            f"{LOG_DIR}/teste_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("BRDrive_Teste")

_ciclo_num               = 0
_ultima_hora_consolidado = -1  # evita enviar 2x na mesma hora


# ── CICLO ─────────────────────────────────────────────────────────────────────
def executar():
    global _ciclo_num
    _ciclo_num += 1

    log.info("━" * 55)
    log.info(f"🔄 Verificando — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} (ciclo #{_ciclo_num})")

    # 1. Extrair dados do JMS via API
    df = extrair()
    if df is None or df.empty:
        log.error("❌ Falha na extracao — verifique se o Edge esta aberto e logado no JMS")
        enviar_alerta_sistema(
            "❌ **Falha na extração JMS**\n\nO robô não conseguiu buscar os dados.\n"
            "Verifique se o Edge está aberto e logado no JMS.\n\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            destinos=[EMAIL_TESTE_FEISHU],
        )
        return

    # 2. Verificar status das viagens anteriores que ainda não bateram
    pendentes = get_pendentes()
    status    = []
    if pendentes:
        log.info(f"🔍 Verificando {len(pendentes)} viagem(ns) anterior(es)...")
        status = verificar_status_anteriores(df, pendentes)
        for s in status:
            if s["bateu"]:
                marcar_bateu(s["id"], s["saida_plan"], s["bateu_em"])
                log.info(f"   ✅ [{s['regional']}] {s['viagem']} — Bateu às {s['bateu_em']}")
            else:
                log.info(f"   ❌ [{s['regional']}] {s['viagem']} — Não bateu (planejado {s['saida_plan']})")

    # 3. Verificar novas viagens saindo em até 1h
    alertas = verificar_alertas_df(df)
    novos   = filtrar_novos(alertas) if alertas else []
    if novos:
        log.info(f"🚨 {len(novos)} nova(s) viagem(ns) saindo em até 1h!")
        for a in novos:
            log.info(f"   [{a['regional']}] {a['viagem']} — {a['categoria']} — saída {a['saida_plan']} (faltam {a['min_restantes']}min)")
    elif alertas:
        log.info("🔁 Todas as viagens próximas já foram alertadas")
    else:
        log.info("✅ Nenhuma saída planejada na próxima hora")

    # 4. Enviar por categoria para os grupos específicos
    for cat, destinos in DESTINOS_POR_CATEGORIA.items():
        status_cat = [s for s in status if s.get("categoria") == cat]
        novos_cat  = [a for a in novos  if a.get("categoria") == cat]
        if (status_cat or novos_cat) and destinos:
            log.info(f"📨 Enviando [{cat}] — {len(status_cat)} anterior(es), {len(novos_cat)} novo(s)")
            enviar_ciclo(status_cat, novos_cat, destinos=destinos, categoria=cat)
            # Marca os que não bateram para não alertar novamente
            for s in status_cat:
                if not s.get("bateu"):
                    marcar_nao_bateu_alertado(s["id"], s["saida_plan"])

    # 5. Monitoramento de lacre
    lacres      = verificar_lacre_df(df)
    novos_lacre = filtrar_novos_lacre(lacres) if lacres else []
    if novos_lacre:
        log.info(f"🔒 {len(novos_lacre)} lacre(s) novo(s) — enviando alertas")
        cats_coleta = [l for l in novos_lacre if l.get("categoria") in ("Coleta PA", "Coleta Base")]
        cats_sd     = [l for l in novos_lacre if l.get("categoria") in ("Secundária", "Devolução")]
        if cats_coleta:
            enviar_lacre(cats_coleta, destinos=[WEBHOOK_LACRE])
        if cats_sd:
            enviar_lacre(cats_sd, destinos=[WEBHOOK_LACRE_SD])
    elif lacres:
        log.info(f"🔒 {len(lacres)} lacre(s) já alertado(s) hoje")
    else:
        log.info("🔒 Nenhum lacre encontrado neste ciclo")

    # 6. Consolidado para SP Capacity Team às 17h, 23h, 05h, 11h
    global _ultima_hora_consolidado
    hora_atual = datetime.now().hour
    if hora_atual in HORARIOS_CONSOLIDADO and hora_atual != _ultima_hora_consolidado:
        h_ini, h_fim = _JANELA[hora_atual]
        periodo = get_periodo_consolidado(h_ini, h_fim)
        log.info(f"📊 Enviando consolidado SP Capacity Team — janela {h_ini:02d}h→{h_fim:02d}h — {len(periodo)} viagem(ns)")
        enviar_consolidado(periodo, destinos=[GRUPO_CAPACITY])
        _ultima_hora_consolidado = hora_atual

    log.info("━" * 55)


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BRDrive Robot — Teste")
    parser.add_argument("--agora", action="store_true", help="Rodar uma vez agora")
    args = parser.parse_args()

    if args.agora:
        executar()
    else:
        log.info("🚀 BRDrive Robot iniciado!")
        log.info(f"⏱️  Intervalo: {INTERVALO_MIN} minutos")
        log.info("Pressione CTRL+C para parar\n")
        while True:
            try:
                executar()
            except KeyboardInterrupt:
                log.info("\n🛑 Encerrado")
                break
            except Exception as e:
                log.error(f"❌ Erro: {e}")
            log.info(f"⏳ Próxima verificação em {INTERVALO_MIN} minutos...\n")
            time.sleep(INTERVALO_MIN * 60)
