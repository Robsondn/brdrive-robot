"""
Limpeza automática dos arquivos Excel baixados do JMS.
Apaga arquivos com mais de 1 dia em Downloads/JMS_Exports.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("BRDrive_Limpeza")

DOWNLOAD_DIR = Path.home() / "Downloads" / "JMS_Exports"
EXTENSOES    = {".xls", ".xlsx"}
DIAS_MANTER  = 1  # apaga arquivos mais velhos que isso


def limpar():
    if not DOWNLOAD_DIR.exists():
        return

    corte = datetime.now() - timedelta(days=DIAS_MANTER)
    apagados = 0

    for arquivo in DOWNLOAD_DIR.iterdir():
        if arquivo.suffix.lower() not in EXTENSOES:
            continue
        modificado = datetime.fromtimestamp(arquivo.stat().st_mtime)
        if modificado < corte:
            try:
                arquivo.unlink()
                log.info(f"🗑️  Apagado: {arquivo.name} (de {modificado.strftime('%d/%m %H:%M')})")
                apagados += 1
            except Exception as e:
                log.warning(f"⚠️  Não foi possível apagar {arquivo.name}: {e}")

    if apagados:
        log.info(f"✅ Limpeza concluída — {apagados} arquivo(s) apagado(s)")
    else:
        log.info("✅ Limpeza — nenhum arquivo antigo encontrado")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    limpar()
