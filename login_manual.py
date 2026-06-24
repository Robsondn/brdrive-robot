"""
Execute este script UMA VEZ para salvar a sessão do JMS.
O Edge vai abrir — resolva o CAPTCHA e faça login normalmente.
Depois feche o terminal. O robô vai reutilizar a sessão salva.

USO:
    py login_manual.py
"""

import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options

ROBOT_PROFILE = r"C:\Users\Robo Transporte\AppData\Local\Microsoft\Edge\RobotProfile"
JMS_URL       = "https://jmsbr.jtjms-br.com/login"
DOWNLOAD_DIR  = str(Path.home() / "Downloads" / "JMS_Exports")

Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

options = Options()
options.add_argument("--start-maximized")
options.add_argument(f"--user-data-dir={ROBOT_PROFILE}")
options.add_experimental_option("prefs", {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
})

print("=" * 55)
print("  BRDrive Robot — Login Manual")
print("=" * 55)
print()
print("  O Edge vai abrir agora.")
print("  1. Resolva o CAPTCHA manualmente")
print("  2. Faça login com seu usuário e senha")
print("  3. Quando estiver na página principal do JMS,")
print("     volte aqui e pressione ENTER para salvar a sessão.")
print()

driver = webdriver.Edge(options=options)
driver.get(JMS_URL)

# Aguarda o usuário fazer login — verifica a cada 5 segundos por até 5 minutos
print("  Aguardando você fazer login no Edge (até 5 minutos)...")
print()

logado = False
for i in range(60):
    time.sleep(5)
    url_atual = driver.current_url
    if "login" not in url_atual.lower():
        logado = True
        break
    if i % 6 == 5:
        print(f"  ... Ainda aguardando login... ({(i+1)*5}s)")

if logado:
    print()
    print("  ✅ Login detectado! Salvando sessão...")
    time.sleep(3)
    print("  ✅ Sessão salva! O robô vai reutilizá-la nas próximas execuções.")
else:
    print()
    print("  ⚠️  Tempo esgotado. Tente novamente.")

driver.quit()
print()
print("  ✅ Pronto! Agora rode:")
print("     py main_teste.py --agora")
