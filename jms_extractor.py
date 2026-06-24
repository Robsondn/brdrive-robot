"""
╔══════════════════════════════════════════════════════════╗
║         JMS BR - Robô de Extração Automática             ║
║  Faz login > exporta relatório > salva no OneDrive       ║
╚══════════════════════════════════════════════════════════╝
"""

import os, time, shutil, logging
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import cv2
import numpy as np

# ── CONFIGURAÇÕES ─────────────────────────────────────────────────────────────
JMS_URL       = "https://jmsbr.jtjms-br.com/login"
RELATORIO_URL = (
    "https://jmsbr.jtjms-br.com/app/transportPlatformIndex/"
    "transportSynthesizeReport?title=Relat%C3%B3rio%20consolidado"
    "%20da%20linha%20secund%C3%A1ria&moduleCode="
)

JMS_USER     = os.getenv("JMS_USER",     "01813143")
JMS_PASSWORD = os.getenv("JMS_PASSWORD", "Ju14jo04@")

DOWNLOAD_DIR = str(Path.home() / "Downloads" / "JMS_Exports")
ONEDRIVE_BASE = r"C:\Users\Robo Transporte\OneDrive - J&T EXPRESS - FILIAL SP"
ONEDRIVE_DIR  = os.getenv("ONEDRIVE_DIR", str(Path(ONEDRIVE_BASE) / "Power BI Gus"))
LOG_DIR      = str(Path(__file__).parent / "logs")

Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(ONEDRIVE_DIR).mkdir(parents=True, exist_ok=True)

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            f"{LOG_DIR}/extractor_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("JMS_Extractor")


# ── CAPTCHA SOLVER (OpenCV Slider) ────────────────────────────────────────────
class SliderCaptchaSolver:
    """
    Resolve o CAPTCHA 'Deslize para completar o quebra-cabeça'
    usando OpenCV para detectar posição + ActionChains para mover.
    """

    def calcular_distancia(self, driver) -> int:
        # Tenta pegar a posição do slot pelo elemento CSS do Tencent CAPTCHA
        try:
            slot = driver.find_element(By.CSS_SELECTOR,
                ".tencent-captcha-dy__bg-placeholder--slider, "
                "[class*='bg-placeholder--slider']"
            )
            rect_slot   = driver.execute_script(
                "var r=arguments[0].getBoundingClientRect(); return {x:r.x,w:r.width};", slot)
            rect_slider = driver.find_element(By.CSS_SELECTOR,
                ".tencent-captcha-dy__slider-block, [class*='slider-block']"
            )
            rect_btn = driver.execute_script(
                "var r=arguments[0].getBoundingClientRect(); return {x:r.x,w:r.width};", rect_slider)
            distancia = int(rect_slot["x"] - rect_btn["x"])
            distancia = max(distancia, 40)
            log.info(f"[CAPTCHA] Distância via DOM: {distancia}px")
            return distancia
        except Exception:
            pass

        # Fallback: OpenCV
        try:
            ss_path = str(Path(LOG_DIR) / "captcha_ss.png")
            driver.save_screenshot(ss_path)
            img   = cv2.imread(ss_path)
            gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            h, w  = gray.shape
            region = edges[int(h*0.25):int(h*0.65), int(w*0.25):int(w*0.75)]
            cols   = np.sum(region, axis=0)
            gap_local   = int(np.argmax(cols))
            gap_global  = int(w * 0.25) + gap_local
            slider_x    = int(w * 0.28)
            distancia   = max(gap_global - slider_x, 40)
            log.info(f"[CAPTCHA] Distância OpenCV: {distancia}px")
            return distancia
        except Exception as e:
            log.warning(f"[CAPTCHA] Cálculo falhou ({e}), usando 170px padrão")
            return 170

    def resolver(self, driver, wait) -> bool:
        try:
            log.info("[CAPTCHA] Aguardando imagem do puzzle carregar...")
            # Espera até a imagem do puzzle estar visível (spinner sumiu)
            for _ in range(15):
                time.sleep(1)
                imgs = driver.find_elements(By.CSS_SELECTOR,
                    ".tencent-captcha-dy__image-area img, "
                    "[class*='tencent'][class*='image'] img, "
                    "[class*='tencent'][class*='fg-item']"
                )
                if imgs and any(
                    driver.execute_script(
                        "var r=arguments[0].getBoundingClientRect();"
                        "return r.width>0 && r.height>0;", img
                    ) for img in imgs
                ):
                    log.info("[CAPTCHA] Imagem carregada!")
                    break
            else:
                log.warning("[CAPTCHA] Imagem não carregou em 15s, tentando mesmo assim...")

            time.sleep(1.5)
            log.info("[CAPTCHA] Localizando slider Tencent...")
            time.sleep(1)

            # Geetest v3/v4 — vários seletores possíveis
            seletores = [
                ".geetest_btn_click",
                ".geetest_slider_button",
                "[class*='geetest_btn']",
                "[class*='geetest_arrow']",
                "div[class*='geetest'] button",
                "div[class*='geetest'] div[class*='btn']",
                ".geetest_wind",
                # Fallback genérico: botão dentro do modal do captcha
                "div[class*='captcha'] button",
                "div[class*='slider'] div[class*='btn']",
            ]

            # Salvar HTML do CAPTCHA para diagnóstico
            with open(f"{LOG_DIR}/captcha_html.txt", "w", encoding="utf-8") as f:
                f.write(driver.page_source)

            # Tencent CAPTCHA (o usado pelo JMS)
            seletores_tencent = [
                ".tencent-captcha-dy__slider-block",
                "[class*='tencent-captcha-dy__slider-block']",
                "[class*='tencent'][class*='slider']",
            ] + seletores  # fallback para outros CAPTCHAs

            slider = None
            for sel in seletores_tencent:
                try:
                    elementos = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in elementos:
                        tamanho = driver.execute_script(
                            "var r=arguments[0].getBoundingClientRect();"
                            "return {w:r.width,h:r.height,x:r.x,y:r.y};", el
                        )
                        if tamanho["w"] > 0 and tamanho["h"] > 0:
                            slider = el
                            log.info(f"[CAPTCHA] Slider Tencent: {sel} ({tamanho['w']}x{tamanho['h']}px @ {tamanho['x']},{tamanho['y']})")
                            break
                    if slider:
                        break
                except Exception:
                    continue

            if slider is None:
                log.error("[CAPTCHA] Slider não encontrado — verifique captcha_html.txt")
                return False

            distancia = self.calcular_distancia(driver)
            actions   = ActionChains(driver)
            actions.click_and_hold(slider).pause(0.4)

            # Movimento humano: aceleração + desaceleração + micro-ajuste
            passos = [0.08]*10 + [0.03]*5 + [0.01]*3
            for p in passos:
                jitter = np.random.uniform(-0.8, 0.8)
                actions.move_by_offset(distancia * p, jitter)
                actions.pause(np.random.uniform(0.01, 0.03))

            actions.move_by_offset(-2, 0).pause(0.1)
            actions.move_by_offset(2,  0).pause(0.1)
            actions.release().perform()

            time.sleep(2)
            log.info("[CAPTCHA] Slider executado!")
            return True

        except Exception as e:
            log.error(f"[CAPTCHA] Erro: {e}")
            return False


# ── DRIVER ────────────────────────────────────────────────────────────────────
# Conecta ao Edge já aberto via iniciar_edge.bat (porta 9222)
def criar_driver() -> webdriver.Edge:
    options = Options()
    options.add_experimental_option("debuggerAddress", "localhost:9222")
    driver = webdriver.Edge(options=options)
    # Define pasta de download via CDP (única forma disponível em sessão remota)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": DOWNLOAD_DIR,
        })
    except Exception:
        pass
    return driver


# ── LOGIN ─────────────────────────────────────────────────────────────────────
def _digitar_campo(driver, elemento, texto: str):
    """Clica no campo, seleciona tudo e digita — funciona em inputs Vue/Element UI."""
    from selenium.webdriver.common.keys import Keys
    elemento.click()
    time.sleep(0.3)
    elemento.send_keys(Keys.CONTROL + "a")
    time.sleep(0.1)
    elemento.send_keys(Keys.DELETE)
    time.sleep(0.1)
    for c in texto:
        elemento.send_keys(c)
        time.sleep(0.04)


def fazer_login(driver, wait) -> bool:
    log.info("📌 Acessando JMS...")
    driver.get(JMS_URL)
    time.sleep(4)

    # Se já está logado (sessão salva no perfil), a URL muda para o dashboard
    if "login" not in driver.current_url.lower():
        log.info("✅ Sessão ativa detectada — já logado!")
        return True

    log.info("🔐 Sessão expirada — fazendo login...")
    time.sleep(1)

    # Screenshot para diagnóstico
    driver.save_screenshot(f"{LOG_DIR}/login_pagina.png")
    log.info(f"📸 Screenshot salvo: {LOG_DIR}/login_pagina.png")

    # Logar todos os inputs encontrados na página
    inputs = driver.find_elements(By.TAG_NAME, "input")
    log.info(f"🔍 Inputs encontrados na página: {len(inputs)}")
    for i, inp in enumerate(inputs):
        log.info(f"   [{i}] type={inp.get_attribute('type')} "
                 f"name={inp.get_attribute('name')} "
                 f"placeholder={inp.get_attribute('placeholder')} "
                 f"id={inp.get_attribute('id')}")

    try:
        # Campo usuário — placeholder em chinês: 请输入员工编号 (número do funcionário)
        campo_user = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//input[contains(@placeholder,'员工编号') or "
            "contains(@placeholder,'账号') or "
            "contains(@placeholder,'用户') or "
            "contains(@placeholder,'login') or "
            "contains(@placeholder,'Login')]"
            " | (//input[@type='text'])[2]"
        )))
        _digitar_campo(driver, campo_user, JMS_USER)

        # Campo senha
        campo_senha = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
            "input[type='password']"
        )))
        _digitar_campo(driver, campo_senha, JMS_PASSWORD)
        time.sleep(0.5)

        # Botão login — tenta vários seletores
        btn = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//button[@type='submit'] | "
            "//button[contains(@class,'login')] | "
            "//button[contains(.,'登录') or contains(.,'Login') or contains(.,'Entrar')]"
        )))
        btn.click()
        time.sleep(3)

        # Screenshot após clicar no login para ver o estado da página
        driver.save_screenshot(f"{LOG_DIR}/login_apos_click.png")

        # Checar CAPTCHA — só detecta se tiver elementos específicos visíveis
        src = driver.page_source.lower()
        captcha_keywords = ["geetest", "deslize para completar", "验证码", "滑动", "quebra-cabeça"]
        if any(k in src for k in captcha_keywords):
            log.info("🔒 CAPTCHA detectado, resolvendo...")
            driver.save_screenshot(f"{LOG_DIR}/captcha_detectado.png")
            if not SliderCaptchaSolver().resolver(driver, wait):
                log.warning("⚠️  CAPTCHA falhou — tentando continuar mesmo assim...")
            time.sleep(2)
        else:
            log.info("✅ Sem CAPTCHA — continuando...")

        time.sleep(3)
        ok = "login" not in driver.current_url.lower()
        log.info("✅ Login OK!" if ok else "❌ Login falhou — verifique login_apos_click.png")
        return ok

    except Exception as e:
        log.error(f"❌ Erro login: {e}")
        driver.save_screenshot(f"{LOG_DIR}/login_erro.png")
        log.info(f"📸 Screenshot erro salvo: {LOG_DIR}/login_erro.png")
        return False



# ── PREENCHER FILTRO DE DATA ──────────────────────────────────────────────────
def _preencher_data(driver, campo, valor: str):
    """
    Preenche um campo de data/hora do JMS (Element UI DateTimePicker).
    Usa JavaScript para forçar o valor e dispara os eventos necessários.
    """
    try:
        driver.execute_script("""
            var el = arguments[0];
            var valor = arguments[1];
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(el, valor);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur',   { bubbles: true }));
        """, campo, valor)
        time.sleep(0.4)
    except Exception as e:
        log.warning(f"[FILTRO] Erro ao preencher campo: {e}")


def aplicar_filtro_data(driver, wait):
    """
    Preenche os campos 'Hora de partida planejada' com hoje 00:00:00 ~ 23:59:59
    e clica em Consulta para filtrar os dados do dia atual.
    """
    hoje       = datetime.now().strftime("%Y-%m-%d")
    data_ini   = f"{hoje} 00:00:00"
    data_fim   = f"{hoje} 23:59:59"

    log.info(f"📅 Aplicando filtro: {data_ini} → {data_fim}")

    try:
        # Localiza os dois inputs de data/hora planejada (início e fim)
        inputs = driver.find_elements(By.CSS_SELECTOR,
            "input.el-input__inner[placeholder*='00:00:00'], "
            "input.el-input__inner[placeholder*='23:59:59'], "
            "input.el-input__inner[type='text']"
        )

        # Filtra apenas os inputs que estão dentro dos campos de data planejada
        # Busca pelo label "Hora de partida planejada"
        campos_data = driver.find_elements(By.XPATH,
            "//label[contains(., 'Hora de partida planejada') or "
            "contains(., '计划发车')]"
            "/following-sibling::div//input | "
            "//div[contains(@class,'el-form-item')]"
            "[.//label[contains(., 'Hora de partida planejada') or contains(., '计划发车')]]"
            "//input"
        )

        if len(campos_data) >= 2:
            _preencher_data(driver, campos_data[0], data_ini)
            time.sleep(0.3)
            _preencher_data(driver, campos_data[1], data_fim)
        else:
            # Fallback: pegar os primeiros dois datetime pickers da página
            log.warning("[FILTRO] Buscando datetime pickers pelo fallback...")
            dt_inputs = driver.find_elements(By.CSS_SELECTOR,
                ".el-date-editor input.el-input__inner"
            )
            if len(dt_inputs) >= 2:
                _preencher_data(driver, dt_inputs[0], data_ini)
                time.sleep(0.3)
                _preencher_data(driver, dt_inputs[1], data_fim)
            else:
                log.warning("[FILTRO] Campos de data não encontrados — exportando sem filtro")
                return

        # Fechar qualquer calendário aberto via JS e garantir janela visível
        driver.execute_script("""
            document.querySelectorAll('.el-picker-panel, .el-date-picker, .el-date-range-picker')
                .forEach(function(el){ el.style.display='none'; });
        """)
        try:
            driver.maximize_window()
        except Exception:
            pass
        time.sleep(0.5)

        # Buscar o botão "Consulta" no DOM (sem checar visibilidade) e clicar via JS
        btn_consulta = wait.until(EC.presence_of_element_located((By.XPATH,
            "//button[contains(., 'Consulta') or contains(., '查询') or "
            "contains(., 'Buscar') or contains(., 'Pesquisar')]"
        )))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn_consulta)
        log.info("🔍 Filtro aplicado — aguardando resultado...")
        time.sleep(3)

        # Aguardar a tabela recarregar
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
            "table, .el-table, .ant-table, .vxe-table"
        )))
        time.sleep(1.5)
        log.info("✅ Resultados filtrados carregados!")

    except Exception as e:
        log.warning(f"[FILTRO] Erro ao aplicar filtro de data: {e}")
        driver.save_screenshot(f"{LOG_DIR}/erro_filtro.png")


# ── NAVEGAÇÃO PELO MENU ───────────────────────────────────────────────────────
def _navegar_pelo_menu(driver, wait):
    """
    Navega pelo menu lateral:
    1. Transporte de linha secundária
    2. Relatório de dados de linha secundária
    3. Aba: Relatório consolidado da linha secundária
    """
    try:
        # 1. Clicar em "Transporte de linha secundária"
        log.info("📂 Menu: Transporte de linha secundária...")
        menu_transp = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//*[contains(text(),'Transporte de linha secundária') or "
            "contains(text(),'次级线路运输') or "
            "contains(text(),'线路次级')]"
        )))
        menu_transp.click()
        time.sleep(1.5)

        # 2. Clicar em "Relatório de dados de linha secundária"
        log.info("📂 Submenu: Relatório de dados...")
        submenu = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//*[contains(text(),'Relatório de dados de linha') or "
            "contains(text(),'次级线路数据报表')]"
        )))
        submenu.click()
        time.sleep(2)

        # 3. Clicar na aba "Relatório consolidado da linha secundária"
        log.info("📑 Aba: Relatório consolidado...")
        aba = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//*[contains(text(),'Relatório consolidado da linha') or "
            "contains(text(),'次级线路综合报表')]"
        )))
        aba.click()
        time.sleep(2)

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
            "table, .el-table, .ant-table, .vxe-table"
        )))
        log.info("✅ Tabela carregada via menu!")

    except Exception as e:
        log.error(f"❌ Erro na navegação pelo menu: {e}")
        driver.save_screenshot(f"{LOG_DIR}/erro_menu.png")


# ── EXPORTAR RELATÓRIO ────────────────────────────────────────────────────────
def _fechar_abas_extras(driver, janela_principal: str):
    """Fecha abas extras que abriram e volta para a janela principal."""
    for handle in driver.window_handles:
        if handle != janela_principal:
            try:
                driver.switch_to.window(handle)
                driver.close()
            except Exception:
                pass
    # Só volta para a janela principal se ela ainda existir
    if janela_principal in driver.window_handles:
        driver.switch_to.window(janela_principal)
    elif driver.window_handles:
        driver.switch_to.window(driver.window_handles[0])


def _tentar_exportar(driver, wait, janela_principal: str) -> str | None:
    """Tentativa única de navegar, filtrar e exportar o relatório."""
    try:
        driver.maximize_window()
    except Exception:
        pass
    log.info("📊 Navegando para o relatório...")
    driver.get(RELATORIO_URL)
    time.sleep(4)

    tabela_css = "table, .el-table, .ant-table, .vxe-table"
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, tabela_css)))
        log.info("✅ Tabela carregada!")
    except Exception:
        log.warning("⚠️  Tabela não carregou — navegando pelo menu...")
        driver.save_screenshot(f"{LOG_DIR}/nav_menu_antes.png")
        _navegar_pelo_menu(driver, wait)

    time.sleep(2)
    driver.save_screenshot(f"{LOG_DIR}/relatorio_carregado.png")

    aplicar_filtro_data(driver, wait)

    log.info("📤 Clicando em 'Exportação'...")
    btn_exp = wait.until(EC.element_to_be_clickable((By.XPATH,
        "//button[normalize-space()='Exportação' or "
        "normalize-space()='Exportar' or "
        "normalize-space()='导出']"
    )))
    btn_exp.click()
    time.sleep(1.5)
    _fechar_abas_extras(driver, janela_principal)

    log.info("✔️  Confirmando popup...")
    btn_ok = wait.until(EC.element_to_be_clickable((By.XPATH,
        "//button[contains(., 'Confirmar') or contains(., '确定') or "
        "contains(., 'OK') or contains(., 'Sim')]"
    )))
    driver.execute_script("arguments[0].click();", btn_ok)
    log.info("📨 Tarefa de exportação enviada ao servidor!")
    time.sleep(6)

    log.info("📋 Abrindo 'Exportar Log'...")
    btn_log = wait.until(EC.presence_of_element_located((By.XPATH,
        "//button[contains(., 'Exportar Log') or contains(., '导出日志')]"
    )))
    driver.execute_script("arguments[0].click();", btn_log)
    time.sleep(2)

    log.info("⏳ Aguardando tabela de log carregar...")
    for tentativa in range(3):
        botoes_dl = driver.find_elements(By.CSS_SELECTOR, ".el-table__row .row-icon")
        if botoes_dl:
            break
        log.info(f"   Sem dados no log — atualizando... (tentativa {tentativa + 1}/3)")
        try:
            btn_q = driver.find_element(By.CSS_SELECTOR, ".el-dialog .btn-query")
            driver.execute_script("arguments[0].click();", btn_q)
        except Exception:
            pass
        time.sleep(5)
    else:
        raise Exception("Exportar Log não retornou dados após 3 tentativas")

    time.sleep(1)
    log.info("⬇️  Clicando no botão de download (1ª linha)...")
    btn_dl = driver.find_elements(By.CSS_SELECTOR, ".el-table__row .row-icon")[0]
    driver.execute_script("arguments[0].click();", btn_dl)
    time.sleep(1)
    _fechar_abas_extras(driver, janela_principal)
    log.info("⏳ Aguardando download do arquivo...")

    arquivo = aguardar_download(DOWNLOAD_DIR, timeout=90)
    if arquivo:
        log.info(f"✅ Download concluído: {Path(arquivo).name}")
        return arquivo
    else:
        log.error("❌ Timeout: arquivo não baixado em 90s")
        driver.save_screenshot(f"{LOG_DIR}/timeout_download.png")
        return None


def exportar_relatorio(driver, wait) -> str | None:
    """
    Fluxo:
    1. Abrir relatório
    2. Aplicar filtro de data (hoje 00:00 ~ 23:59)
    3. Clicar "Exportação" → confirmar popup "Dicas gentis"
    4. Clicar "Exportar Log" → clicar setinha ↓ na 1ª linha
    5. Aguardar download
    Tenta 2 vezes automaticamente — na falha recarrega a página.
    """
    janela_principal = driver.current_window_handle
    for tentativa in range(1, 3):
        try:
            return _tentar_exportar(driver, wait, janela_principal)
        except Exception as e:
            msg = str(e)
            log.warning(f"⚠️  Tentativa {tentativa}/2 falhou: {msg[:120]}")
            # Se o Edge fechou não adianta tentar novamente
            if "no such window" in msg or "web view not found" in msg or "no such session" in msg:
                log.error("❌ Edge foi fechado — reinicie o bat para reconectar")
                return None
            try:
                driver.save_screenshot(f"{LOG_DIR}/erro_exportacao_t{tentativa}.png")
            except Exception:
                pass
            if tentativa < 2:
                log.info("🔄 Recarregando página e tentando novamente...")
                time.sleep(3)
    log.error("❌ Exportação falhou após 2 tentativas")
    return None



# ── AGUARDAR DOWNLOAD ─────────────────────────────────────────────────────────
def aguardar_download(pasta: str, timeout: int = 90) -> str | None:
    inicio = time.time()
    while time.time() - inicio < timeout:
        arquivos = [
            f for f in Path(pasta).iterdir()
            if f.suffix.lower() in {".xls", ".xlsx"}
            and not f.name.endswith(".crdownload")
            and not f.name.startswith("~$")
        ]
        if arquivos:
            recente = max(arquivos, key=lambda f: f.stat().st_mtime)
            time.sleep(1.5)
            if recente.stat().st_size > 1000:
                return str(recente)
        time.sleep(2)
    return None


# ── SALVAR NO ONEDRIVE ────────────────────────────────────────────────────────
def salvar_onedrive(arquivo: str) -> str:
    ext     = Path(arquivo).suffix.lower()
    nome    = f"JMS_Export_{datetime.now().strftime('%Y%m%d_%H%M')}{ext}"
    destino = str(Path(ONEDRIVE_DIR) / nome)
    shutil.copy2(arquivo, destino)
    os.remove(arquivo)
    log.info(f"📁 Salvo no OneDrive: {destino}")
    return destino


# ── EXECUÇÃO PRINCIPAL ────────────────────────────────────────────────────────
def extrair() -> str | None:
    log.info("=" * 55)
    log.info(f"🤖 Extração iniciada — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log.info("=" * 55)

    driver = criar_driver()
    wait   = WebDriverWait(driver, 20)

    try:
        # Restaura a janela caso esteja minimizada
        try:
            driver.maximize_window()
        except Exception:
            pass

        # Garante que a pasta de download existe
        Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

        # Limpar downloads antigos antes de começar
        for f in Path(DOWNLOAD_DIR).iterdir():
            if f.suffix.lower() in {".xls", ".xlsx"} and not f.name.startswith("~$"):
                f.unlink(missing_ok=True)

        # Verifica sessão JMS acessando a home sem navegar direto ao relatório
        log.info(f"🌐 URL atual: {driver.current_url}")
        log.info("🔍 Verificando sessão JMS...")
        driver.get("https://jmsbr.jtjms-br.com/index")
        time.sleep(2)
        if "login" in driver.current_url.lower():
            log.error("❌ Sessão expirada — faça login no JMS e tente novamente.")
            return None

        log.info("✅ Sessão JMS ativa — iniciando extração...")

        arquivo = exportar_relatorio(driver, wait)
        if not arquivo:
            return None

        return salvar_onedrive(arquivo)

    except Exception as e:
        log.error(f"❌ Erro geral: {e}")
        driver.save_screenshot(f"{LOG_DIR}/erro_geral.png")
        return None

    # Não fecha o navegador — o usuário o deixou aberto intencionalmente


if __name__ == "__main__":
    resultado = extrair()
    if resultado:
        log.info(f"🎉 Arquivo pronto: {resultado}")
    else:
        log.error("💥 Extração falhou — verifique os logs")
