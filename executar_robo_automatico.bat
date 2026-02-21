@echo off
REM Script para executar o robo.py com ambiente virtual ativado
REM Versao AUTOMATICA - Finaliza sozinho sem esperar tecla
REM Criado para agendamento no Task Scheduler do Windows

title Energisa - Busca de Faturas [AUTOMATICO]
color 0A

echo ========================================
echo Iniciando Busca de Faturas Energisa
echo Data/Hora: %date% %time%
echo Modo: AUTOMATICO (finaliza sozinho)
echo ========================================

REM Navegar para o diretório do projeto
cd /d "%~dp0"

REM Ativar ambiente virtual
echo Ativando ambiente virtual...
call venv\Scripts\activate.bat

REM Verificar se a ativação foi bem-sucedida
if errorlevel 1 (
    echo ERRO: Falha ao ativar ambiente virtual
    exit /b 1
)

echo Ambiente virtual ativado com sucesso!

REM Executar o script Python
echo Executando robo.py...
python robo.py

REM Capturar código de saída
set EXIT_CODE=%errorlevel%

REM Desativar ambiente virtual
call deactivate

echo ========================================
echo Execucao finalizada AUTOMATICAMENTE
echo Codigo de saida: %EXIT_CODE%
echo Data/Hora: %date% %time%
echo ========================================

REM Sair com o código de saída do Python (SEM PAUSE)
exit /b %EXIT_CODE%
