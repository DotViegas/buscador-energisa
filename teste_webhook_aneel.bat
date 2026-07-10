@echo off
echo ========================================
echo   TESTE DE WEBHOOK - CODIGO ANEEL
echo ========================================
echo.

REM Ativar ambiente virtual se existir
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Executar o script de teste
python teste_webhook_aneel.py

echo.
pause
