"""Vigia de travamento do robo_v2.

Em 05/10/2026 o Chrome e o driver do Patchright sumiram às 08:16 e o Python
ficou 4 h parado esperando uma resposta que nunca vinha - sem erro e sem uma
linha de log. O robô escreve no log o tempo todo (também nas esperas, uma
linha por minuto, e aguardando o SMS, a cada 5 s); se ele ficar em silêncio
por mais que o limite, o vigia encerra o Chrome/driver do robô e o próprio
processo com CODIGO_TRAVADO. O executar_robo_automatico.bat vê esse código e
recomeça a execução - as faturas já feitas ficam no banco.
"""
import os
import subprocess
import threading
import time
from datetime import datetime

CODIGO_TRAVADO = 5
LIMITE_MINUTOS = int(os.getenv("VIGIA_MINUTOS", "20"))


class Vigia:
    def __init__(self, perfil_dir, limite_s=LIMITE_MINUTOS * 60, intervalo_s=30):
        self.perfil_dir = perfil_dir
        self.limite_s = limite_s
        self.intervalo_s = intervalo_s
        self._ultimo = time.monotonic()

    def tocar(self):
        """Sinal de vida: chamado a cada escrita no log."""
        self._ultimo = time.monotonic()

    def iniciar(self):
        threading.Thread(target=self._vigiar, name="vigia", daemon=True).start()
        return self

    def _vigiar(self):
        while True:
            time.sleep(self.intervalo_s)
            parado = time.monotonic() - self._ultimo
            if parado > self.limite_s:
                self._disparar(parado)

    def _disparar(self, parado_s):
        try:
            print(f"\n🚨 VIGIA: robô sem nenhuma saída há {parado_s / 60:.0f} min "
                  f"({datetime.now():%H:%M:%S}) - travado. Encerrando o Chrome e o "
                  f"processo (código {CODIGO_TRAVADO}) para a tarefa recomeçar.", flush=True)
        except Exception:
            pass
        _encerrar_navegador_do_robo(self.perfil_dir)
        os._exit(CODIGO_TRAVADO)


def _encerrar_navegador_do_robo(perfil_dir):
    """Mata o driver (filho deste processo) e o Chrome que usa o perfil do robô,
    para a nova execução conseguir abrir o mesmo perfil. O próprio PowerShell
    também é filho deste processo e tem o perfil na linha de comando: fica de fora."""
    comando = (
        f"Get-CimInstance Win32_Process | Where-Object {{ $_.ProcessId -ne $PID -and "
        f"($_.ParentProcessId -eq {os.getpid()} -or $_.CommandLine -like '*{perfil_dir}*') }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", comando], timeout=60,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
