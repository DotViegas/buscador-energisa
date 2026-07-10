@echo off
echo ========================================
echo   COLETAR CODIGOS ANEEL - ENERGISA
echo ========================================
echo.
echo Iniciando coleta de codigos ANEEL...
echo.

REM Ativar ambiente virtual se existir
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Executar o script Python
python coletar_codigos_aneel.py

echo.
echo ========================================
echo   EXECUCAO FINALIZADA
echo ========================================
pause
