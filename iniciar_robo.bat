@echo off
title BRDrive Robot - J&T Express
color 0A
cls

echo.
echo  ============================================
echo    BRDrive Robot - J^&T Express
echo  ============================================
echo.
echo  PASSO 1: Abrindo Edge no JMS...
echo.

start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="C:\Users\Robo Transporte\AppData\Local\Microsoft\Edge\RobotDebug" ^
    --no-first-run ^
    "https://jmsbr.jtjms-br.com/login"

echo  Edge aberto! Faca login no JMS agora.
echo.
echo  --------------------------------------------
echo  PASSO 2: Apos fazer o login no JMS,
echo           pressione ENTER para iniciar o robo.
echo  --------------------------------------------
echo.
pause >nul

cls
echo.
echo  ============================================
echo    BRDrive Robot - Iniciando...
echo  ============================================
echo.
echo  O robo vai verificar a cada 20 minutos.
echo  Alertas serao enviados por e-mail.
echo.
echo  Para parar o robo: pressione CTRL+C
echo.
echo  ============================================
echo.

REM Impede o PC de dormir enquanto o robo esta rodando
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0

cd /d "C:\Users\Robo Transporte\OneDrive - J&T EXPRESS - FILIAL SP\BRDrive_Robot"
py main_teste.py

REM Restaura o tempo de espera padrao (30 min) ao encerrar
powercfg /change standby-timeout-ac 30
powercfg /change monitor-timeout-ac 15

echo.
echo  Robo encerrado. Pressione qualquer tecla para fechar.
pause >nul
