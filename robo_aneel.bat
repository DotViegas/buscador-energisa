@echo off
echo ========================================
echo   ROBO ANEEL - COLETAR CODIGOS ANEEL
echo ========================================
echo.
echo Iniciando coleta de codigos ANEEL...
echo.

REM Ativar ambiente virtual se existir
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Executar o script Python
python robo_aneel.py

echo.
echo ========================================
echo   EXECUCAO FINALIZADA
echo ========================================
pause
