"""
╔══════════════════════════════════════════════════════════╗
║         BRDrive Robot — Setup Inicial                    ║
║  Execute este arquivo UMA VEZ antes de usar o robô       ║
║                                                          ║
║  O que ele faz:                                          ║
║  ✅ Cria a pasta BRDrive_Robot no OneDrive               ║
║  ✅ Verifica se Python está OK                           ║
║  ✅ Verifica dependências instaladas                     ║
║  ✅ Envia e-mail de teste para confirmar                 ║
╚══════════════════════════════════════════════════════════╝

USO:
    python setup.py
"""

import os
import sys
from pathlib import Path

# ── CAMINHO ONEDRIVE ──────────────────────────────────────────────────────────
ONEDRIVE_BASE  = r"C:\Users\Robo Transporte\OneDrive - J&T EXPRESS - FILIAL SP"
PASTA_ROBOT    = "Power BI Gus"
ONEDRIVE_DIR   = str(Path(ONEDRIVE_BASE) / PASTA_ROBOT)

SUBPASTAS = [
    ONEDRIVE_DIR,
    str(Path(ONEDRIVE_DIR) / "exports"),   # arquivos exportados do JMS
    str(Path(ONEDRIVE_DIR) / "logs"),      # logs do robô
    str(Path(ONEDRIVE_DIR) / "backup"),    # backup dos Excel antes de atualizar
]

print("=" * 55)
print("  BRDrive Robot — Setup Inicial")
print("=" * 55)


# ── 1. CRIAR PASTAS ───────────────────────────────────────────────────────────
print("\n📁 Criando estrutura de pastas no OneDrive...")

onedrive_ok = Path(ONEDRIVE_BASE).exists()
if not onedrive_ok:
    print(f"  ⚠️  Pasta do OneDrive não encontrada:")
    print(f"      {ONEDRIVE_BASE}")
    print("  Verifique se o OneDrive está sincronizado e tente novamente.")
    sys.exit(1)

for pasta in SUBPASTAS:
    Path(pasta).mkdir(parents=True, exist_ok=True)
    print(f"  ✅ {pasta}")

print("\n  Estrutura criada com sucesso!")
print(f"""
  📂 {ONEDRIVE_BASE}
  └── 📂 {PASTA_ROBOT}/
      ├── 📂 exports/     ← arquivos exportados do JMS
      ├── 📂 logs/        ← logs automáticos
      └── 📂 backup/      ← backup dos Excel
""")


# ── 2. VERIFICAR DEPENDÊNCIAS ─────────────────────────────────────────────────
print("📦 Verificando dependências Python...\n")

deps = {
    "pandas":    "pandas",
    "openpyxl":  "openpyxl",
    "selenium":  "selenium",
    "cv2":       "opencv-python",
    "numpy":     "numpy",
}

faltando = []
for modulo, pacote in deps.items():
    try:
        __import__(modulo)
        print(f"  ✅ {pacote}")
    except ImportError:
        print(f"  ❌ {pacote} — NÃO INSTALADO")
        faltando.append(pacote)

if faltando:
    print(f"\n  ⚠️  Execute o comando abaixo para instalar:")
    print(f"      pip install {' '.join(faltando)}")
    sys.exit(1)
else:
    print("\n  ✅ Todas as dependências instaladas!")


# ── 3. VERIFICAR EDGE DRIVER ──────────────────────────────────────────────────
print("\n🌐 Verificando Edge WebDriver...")

driver_encontrado = False
paths_verificados = [
    Path(__file__).parent / "msedgedriver.exe",
    Path("C:/Windows/System32/msedgedriver.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedgedriver.exe"),
]

for p in paths_verificados:
    if p.exists():
        print(f"  ✅ Driver encontrado: {p}")
        driver_encontrado = True
        break

if not driver_encontrado:
    # Tentar webdriver-manager
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
        options = Options()
        options.add_argument("--headless")
        driver = webdriver.Edge(options=options)
        driver.quit()
        print("  ✅ Edge WebDriver OK (encontrado no PATH do sistema)")
        driver_encontrado = True
    except Exception:
        print("  ⚠️  Edge WebDriver não encontrado automaticamente")
        print("  Baixe em: https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/")
        print("  Coloque o msedgedriver.exe na mesma pasta do projeto")


# ── 4. VERIFICAR ARQUIVOS EXCEL ───────────────────────────────────────────────
print("\n📊 Verificando arquivos Excel no OneDrive...")

arquivos = {
    "Database_-_Power_bi.xlsx": "Database principal",
    "BRDrive_BI_Novo.xlsx":     "BRDrive (alimenta o dashboard)",
}

todos_ok = True
for nome, descricao in arquivos.items():
    caminho = Path(ONEDRIVE_DIR) / nome
    if caminho.exists():
        print(f"  ✅ {nome} ({descricao})")
    else:
        print(f"  ⚠️  {nome} ({descricao}) — não encontrado")
        print(f"      Coloque o arquivo em: {ONEDRIVE_DIR}")
        todos_ok = False

if not todos_ok:
    print("\n  ⚠️  Copie os arquivos Excel para a pasta BRDrive_Robot no OneDrive antes de rodar!")


# ── 5. TESTE DE E-MAIL ────────────────────────────────────────────────────────
print("\n📧 Enviando e-mail de teste...")

resposta = input("  Deseja enviar e-mail de teste agora? (s/n): ").strip().lower()
if resposta == "s":
    try:
        from faishu_alertas import enviar_alertas
        import logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

        alertas_teste = [
            {
                "tipo":       "SAÍDA NÃO REALIZADA",
                "id":         "SRTR22601607300",
                "subtipo":    "BRE-S18-0000-1",
                "transp":     "JET SP",
                "condutor":   "Carlos Alberto Aparecido",
                "planejado":  "00:00",
                "atraso_min": 45,
                "origem":     "SP BRE",
                "destino":    "DC SBN-SP",
            },
            {
                "tipo":       "CHEGADA NÃO REALIZADA",
                "id":         "SRTR22601616251",
                "subtipo":    "BRE-S111-0000-2",
                "transp":     "JET SP",
                "condutor":   "VALDECIR GOMES DE BRITO",
                "planejado":  "02:30",
                "atraso_min": 60,
                "origem":     "SC BRE 01",
                "destino":    "S-JAB-SP",
            },
        ]

        enviar_alertas(alertas_teste)
        print("  ✅ E-mail enviado! Verifique: robson.noberto@jtexpress.com.br")

    except Exception as e:
        print(f"  ❌ Erro ao enviar e-mail: {e}")
else:
    print("  ⏭️  Teste de e-mail pulado")


# ── RESUMO FINAL ──────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  ✅ Setup concluído!")
print("=" * 55)
print(f"""
  Próximos passos:
  1. Copie os arquivos Excel para:
     {ONEDRIVE_DIR}

  2. Configure seu usuário/senha do JMS em:
     jms_extractor.py  →  JMS_USER / JMS_PASSWORD

  3. Teste a extração:
     python main.py --agora

  4. Inicie o robô contínuo (a cada 25 min):
     python main.py
""")
