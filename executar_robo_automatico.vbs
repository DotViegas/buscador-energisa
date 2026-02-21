' Script VBS para executar o robo.py automaticamente (sem pause)
' Versao AUTOMATICA - Finaliza sozinho
' Este script executa o .bat automatico e fecha a janela ao terminar

Set objShell = CreateObject("WScript.Shell")

' Obter o diretório do script
strScriptPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Executar o arquivo .bat AUTOMATICO
' 1 = janela visível, 0 = oculta
' True = aguarda conclusão antes de continuar
objShell.Run """" & strScriptPath & "\executar_robo_automatico.bat""", 1, True

' Script finaliza automaticamente após o .bat terminar
