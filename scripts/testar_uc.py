"""Roda o robô da Energisa para UMA única UC.

Uso (a partir da raiz do projeto, com o venv ativo):
    python scripts/testar_uc.py                       # UC padrão: 3877388
    python scripts/testar_uc.py 3874681               # outra UC
    python scripts/testar_uc.py 3877388 --sem-force   # não reprocessa faturas já marcadas com erro hoje
    python scripts/testar_uc.py 3877388 --atualizar-api  # baixa os JSONs da API antes de rodar
    python scripts/testar_uc.py 3877388 --limite-minutos 60  # encerra sozinho após 60 min (padrão: 120)

Executa exatamente o mesmo fluxo do robô diário (login com código por e-mail,
seleção da UC, download das faturas, gravação no banco e envio para a API),
apenas restrito à UC informada. Por padrão usa force=True, porque a fatura que
falhou hoje já está marcada como 'erro' no banco e sem force seria pulada.

O log vai para logs/teste_uc_<UC>_<data-hora>.txt. Se o clique em "Baixar 2ª
via" for interceptado, o diagnóstico do DOM aparece no log e o screenshot em
logs/clique_bloqueado_<UC>_<mês>_t<tentativa>.png.

O veredito final (e o código de saída) vem do banco, comparando o status das
faturas da UC antes e depois: 0 = todas as faturas processadas nesta execução
ficaram 'sucesso'; 1 = alguma ficou 'erro' (ou houve exceção); 2 = nenhuma
fatura foi processada; 3 = limite de tempo; 130 = Ctrl+C.

NÃO rode enquanto o robô diário (robo.py / ea_manager) estiver em execução:
duas sessões simultâneas disputam o mesmo código de verificação por e-mail.
O script recusa iniciar se encontrar outro robo.py/testar_uc.py rodando, mas
a proteção é só nesta direção: o agendador do ea_manager dispara o robo.py no
horário marcado (SCHEDULER_HORA, padrão 08:00) mesmo com um teste em andamento.
Por isso o limite de tempo (padrão 120 min) — cada falha de login custa 30 min
de espera — e por isso não inicie um teste a menos de 2 h desse horário.
"""
import argparse
import glob
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import traceback
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)  # media/json, logs/ e database/ são caminhos relativos à raiz

from robo import processar_geradora, LogDuplo  # noqa: E402
from database import inicializar_banco  # noqa: E402
from function.buscar_dados_api import buscar_faturas, extrair_numero_fatura  # noqa: E402

UC_PADRAO = "3877388"
DB_PATH = os.path.join(PROJECT_DIR, "database", "faturas.db")
LIMITE_MINUTOS_PADRAO = 120


def outras_instancias_do_robo():
    """Lista (pid, linha de comando) de outros robo.py/testar_uc.py em execução.

    Usa o WMI via PowerShell (sem depender de psutil). Se a consulta falhar,
    avisa e devolve lista vazia — o chamador segue por conta própria.
    """
    comando = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
        "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
    )
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
            capture_output=True, timeout=30,
        )
    except Exception as e:
        print(f"⚠️ Não foi possível verificar processos em execução: {e}")
        return []
    saida = resultado.stdout.decode("utf-8", errors="replace")
    if resultado.returncode != 0 or not saida.strip():
        # Sem "fail-open" silencioso: este próprio processo deveria aparecer na lista.
        erro = resultado.stderr.decode("utf-8", errors="replace").strip()
        print(f"⚠️ Consulta de processos falhou (código {resultado.returncode}): {erro or 'sem saída'}")
        return []
    # O python.exe do venv é um launcher que roda o interpretador real como
    # filho: os dois aparecem com a mesma linha de comando, daí ignorar o pai.
    proprios = {os.getpid(), os.getppid()}
    # Além de "robo.py"/"testar_uc.py" como script, cobre o ea_manager rodando
    # uma geradora específica: python -c "from robo import processar_geradora_especifica ...".
    padrao = re.compile(
        r'(?i)(^|[\\/"\s])(robo|testar_uc)\.py(["\s]|$)'
        r'|\b(from\s+robo\s+import|import\s+robo)\b'
    )
    encontrados = []
    for linha in saida.splitlines():
        pid, _, cmd = linha.partition("\t")
        if not pid.strip().isdigit() or int(pid) in proprios:
            continue
        if padrao.search(cmd):
            encontrados.append((int(pid), cmd.strip()))
    return encontrados


def localizar_geradoras(uc):
    """Procura a UC nos JSONs da API (media/json).

    A entrada é normalizada como as chaves de lista_ucs (extrair_numero_fatura:
    "10/3877388-6" → "3877388") e comparada por igualdade exata — nada de
    substring, para um dígito a mais ou a menos não cair em outra UC.

    Returns:
        tuple: (nova_uc normalizada, [(cnpj, faturas, caminho_json), ...]) —
            uma entrada por geradora em que a UC aparece.
    """
    nova_uc = extrair_numero_fatura(uc.strip())
    encontradas = []
    for caminho in sorted(glob.glob(os.path.join("media", "json", "*.json"))):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception as e:
            print(f"⚠️ Não foi possível ler {caminho}: {e}")
            continue
        faturas = dados.get("lista_ucs", {}).get(nova_uc)
        if faturas is not None and dados.get("geradora"):
            encontradas.append((dados["geradora"], faturas, caminho))
    return nova_uc, encontradas


def status_no_banco(faturas):
    """Lê o status atual das faturas da UC (conexão read-only, sem alterar nada).

    Returns:
        dict: {id: dict(linha)}; vazio se não houver ids ou se a leitura falhar.
    """
    ids = [f.get("id") for f in faturas if f.get("id") is not None]
    if not ids:
        print("   (nenhuma fatura com id)")
        return {}
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        marcadores = ",".join("?" * len(ids))
        linhas = conn.execute(
            f"SELECT id, mes_referencia, status, tentativas, tipo_operacao, "
            f"data_processamento, mensagem_erro FROM faturas WHERE id IN ({marcadores}) "
            f"ORDER BY mes_referencia",
            ids,
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"   ⚠️ Não foi possível ler o banco: {e}")
        return {}
    if not linhas:
        print("   (faturas ainda não registradas no banco)")
    for r in linhas:
        erro = f" | erro: {r['mensagem_erro']}" if r["mensagem_erro"] else ""
        print(f"   id {r['id']} | {r['mes_referencia']} | status={r['status']} | "
              f"tentativas={r['tentativas']} | operacao={r['tipo_operacao']} | "
              f"processada={r['data_processamento']}{erro}")
    return {r["id"]: dict(r) for r in linhas}


def avaliar_resultado(antes, depois):
    """Compara o banco antes/depois e devolve (processadas, com_erro).

    Uma fatura conta como processada nesta execução quando tentativas ou
    data_processamento mudaram (atualizar_status_fatura sempre altera ambos).
    """
    processadas, com_erro = [], []
    for fid, linha in depois.items():
        anterior = antes.get(fid)
        mudou = anterior is None or (
            anterior["tentativas"], anterior["data_processamento"]
        ) != (linha["tentativas"], linha["data_processamento"])
        if not mudou:
            continue
        processadas.append(fid)
        if linha["status"] != "sucesso":
            com_erro.append(fid)
    return processadas, com_erro


def main():
    parser = argparse.ArgumentParser(description="Roda o robô da Energisa para uma única UC.")
    parser.add_argument("uc", nargs="?", default=UC_PADRAO, help=f"nova_uc a testar (padrão: {UC_PADRAO})")
    parser.add_argument("--sem-force", action="store_true",
                        help="não reprocessa faturas já marcadas com erro hoje (padrão: reprocessa)")
    parser.add_argument("--atualizar-api", action="store_true",
                        help="baixa os JSONs da API (media/json) antes de rodar")
    parser.add_argument("--limite-minutos", type=float, default=LIMITE_MINUTOS_PADRAO,
                        help=f"encerra o teste após N minutos (padrão: {LIMITE_MINUTOS_PADRAO}; 0 = sem limite)")
    args = parser.parse_args()
    force = not args.sem_force

    os.makedirs("logs", exist_ok=True)
    agora = datetime.now()
    nome_uc = "".join(c if c.isalnum() else "_" for c in args.uc.strip())
    caminho_log = os.path.join("logs", f"teste_uc_{nome_uc}_{agora.strftime('%d%m%Y-%H%M%S')}.txt")
    log_duplo = LogDuplo(caminho_log)
    sys.stdout = log_duplo

    # Limite de duração: dispara um Ctrl+C sintético. raise_signal (e não
    # _thread.interrupt_main) porque só ele acorda o time.sleep de 30 min dos
    # retries do robô e as esperas do Playwright no Windows.
    limite = {"atingido": False}

    def _estourar_limite():
        limite["atingido"] = True
        signal.raise_signal(signal.SIGINT)

    temporizador = None
    if args.limite_minutos > 0:
        temporizador = threading.Timer(args.limite_minutos * 60, _estourar_limite)
        temporizador.daemon = True

    try:
        print(f"📝 Log iniciado: {caminho_log}")
        print(f"🕐 Data/Hora: {agora.strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"🎯 Teste restrito à UC {args.uc} (force={force}, limite={args.limite_minutos:g} min)")
        print("=" * 80)

        outras = outras_instancias_do_robo()
        if outras:
            print("❌ Já existe outra instância do robô em execução - abortando para não disputar o código por e-mail:")
            for pid, cmd in outras:
                print(f"   PID {pid}: {cmd}")
            return 1

        if temporizador:
            temporizador.start()

        inicializar_banco()

        if args.atualizar_api:
            print("📡 Buscando dados atualizados da API...")
            if not buscar_faturas():
                print("❌ Falha ao buscar dados da API. Abortando.")
                return 1

        nova_uc, geradoras = localizar_geradoras(args.uc)
        if not geradoras:
            print(f"❌ UC {nova_uc} não encontrada em media/json/*.json "
                  f"(rode com --atualizar-api ou confira o número).")
            return 1
        if len(geradoras) > 1:
            print(f"ℹ️ UC {nova_uc} aparece em {len(geradoras)} geradoras - todas serão processadas em sequência")

        antes, depois = {}, {}
        ok = True
        for cnpj, faturas, caminho_json in geradoras:
            mtime = datetime.fromtimestamp(os.path.getmtime(caminho_json)).strftime('%d/%m/%Y %H:%M:%S')
            print(f"🏭 Geradora: {cnpj} | nova_uc: {nova_uc} | faturas na API: {len(faturas)}")
            print(f"📄 JSON usado: {caminho_json} (atualizado em {mtime})")
            for f in faturas:
                print(f"   - id {f.get('id')} | ref {f.get('data_referencia')} | venc {f.get('data_vencimento')} "
                      f"| tarefa {f.get('tarefa')}")
            print("💾 Status no banco ANTES:")
            antes.update(status_no_banco(faturas))
            print("=" * 80)

            ok = processar_geradora(cnpj, force=force, apenas_ucs=[nova_uc]) and ok

            print("=" * 80)
            print("💾 Status no banco DEPOIS:")
            depois.update(status_no_banco(faturas))

        processadas, com_erro = avaliar_resultado(antes, depois)
        fim = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        if not processadas:
            print(f"⚠️ Nenhuma fatura da UC {nova_uc} foi processada nesta execução às {fim} "
                  f"(nada pendente para force={force}; veja o status acima).")
            codigo = 2
        elif com_erro or not ok:
            print(f"❌ Teste da UC {nova_uc} finalizado com FALHA às {fim}: "
                  f"{len(com_erro)}/{len(processadas)} fatura(s) processada(s) ficaram sem sucesso "
                  f"(ids {com_erro}). Procure 'Diagnóstico do clique bloqueado' no log.")
            codigo = 1
        else:
            print(f"✅ Teste da UC {nova_uc} finalizado com SUCESSO às {fim}: "
                  f"{len(processadas)} fatura(s) processada(s) com status 'sucesso' (ids {processadas}).")
            codigo = 0
        print(f"📝 Log completo: {caminho_log}")
        return codigo

    except KeyboardInterrupt:
        if limite["atingido"]:
            print(f"\n⏱️ Limite de {args.limite_minutos:g} min atingido - teste encerrado "
                  f"(não deixe o teste atravessar a execução diária das 08:00)")
            return 3
        print("\n⛔ Teste interrompido pelo usuário")
        return 130
    except Exception as e:
        print(f"❌ Erro durante o teste: {e}")
        traceback.print_exc(file=sys.stdout)
        return 1
    finally:
        if temporizador:
            temporizador.cancel()
        sys.stdout = log_duplo.terminal
        log_duplo.close()


if __name__ == "__main__":
    sys.exit(main())
