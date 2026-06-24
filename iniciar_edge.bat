@echo off
echo ============================================
echo   BRDrive Robot - Iniciando Edge
echo ============================================
echo.
echo  Abrindo Edge com porta de depuracao...
echo  Faca login no JMS e deixe este Edge aberto.
echo  O robo vai se conectar automaticamente.
echo.
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\robson.noberto\AppData\Local\Microsoft\Edge\RobotDebug" --no-first-run "https://jmsbr.jtjms-br.com/login"
echo  Edge iniciado! Faca login no JMS agora.
pause

