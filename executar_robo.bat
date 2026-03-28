@echo off
REM Script para executar o robo.py com ambiente virtual ativado
REM Criado para agendamento no Task Scheduler do Windows

title Energisa - Busca de Faturas
color 0A

echo ========================================
echo Iniciando Busca de Faturas Energisa
echo Data/Hora: %date% %time%
echo ========================================

REM Navegar para o diretório do projeto
cd /d "%~dp0"

REM Ativar ambiente virtual
echo Ativando ambiente virtual...
call venv\Scripts\activate.bat

REM Verificar se a ativação foi bem-sucedida
if errorlevel 1 (
    echo ERRO: Falha ao ativar ambiente virtual
    pause
    exit /b 1
)

echo Ambiente virtual ativado com sucesso!

REM Executar o script Python
echo Executando robo.py...
python robo.py %*

REM Capturar código de saída
set EXIT_CODE=%errorlevel%

REM Desativar ambiente virtual
call deactivate

echo ========================================
echo Execucao finalizada
echo Codigo de saida: %EXIT_CODE%
echo Data/Hora: %date% %time%
echo ========================================
echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul

REM Sair com o código de saída do Python
exit /b %EXIT_CODE%
