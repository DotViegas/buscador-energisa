@echo off
REM Script para executar o robo_v2.py com ambiente virtual ativado
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
REM Robo v2 (Patchright + Chrome instalado). Para voltar ao antigo: python robo.py
REM Codigo 5 = o vigia detectou travamento (robo sem escrever no log por 20 min)
REM e encerrou a execucao: recomeca ate 3 vezes (as faturas feitas ficam no banco).
set REINICIOS=0
:rodar_robo
echo Executando robo_v2.py...
python robo_v2.py

REM Capturar código de saída
set EXIT_CODE=%errorlevel%
if not "%EXIT_CODE%"=="5" goto fim_robo
set /a REINICIOS+=1
if %REINICIOS% GTR 3 goto fim_robo
echo robo_v2.py travou - recomecando em 30 s ^(reinicio %REINICIOS% de 3^)...
timeout /t 30 /nobreak >nul
goto rodar_robo
:fim_robo

REM Demonstrativos de compensação das usinas: só baixa para o backup local
REM (demonstrativos/AAAA-MM/); o envio ao GEUS passa pela conferência.
REM Só roda depois que o robo_v2 terminou de verdade (código 0): se ele foi
REM interrompido, abortou ou travou, os demonstrativos não começam fora de ordem.
if "%EXIT_CODE%"=="0" (
    echo Executando robo_demonstrativos.py...
    python robo_demonstrativos.py
) else (
    echo robo_v2.py nao terminou ^(codigo %EXIT_CODE%^) - demonstrativos NAO executados
)

REM Desativar ambiente virtual
call deactivate

echo ========================================
echo Execucao finalizada AUTOMATICAMENTE
echo Codigo de saida: %EXIT_CODE%
echo Data/Hora: %date% %time%
echo ========================================

REM Sair com o código de saída do Python (SEM PAUSE)
exit /b %EXIT_CODE%
