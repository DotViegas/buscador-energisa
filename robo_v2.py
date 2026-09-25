"""Robô Energisa v2 - busca de faturas com Patchright + Chrome instalado.

Diferenças para o robo.py (que continua disponível para comparação):
  - Navegador: Chrome real via Patchright com perfil persistente (function/navegador.py),
    que passa pelo Akamai Bot Manager; o Chromium embutido do Playwright era barrado.
  - Login: até 4 envios do CNPJ, reenvio imediato ao ver 403 no /api/auth.
  - Sem relogin forçado a cada 50 UCs: a sessão segue até o Access Denied.
  - Access Denied: relogin imediato; espera MINUTOS_ENTRE_TENTATIVAS só se ele falhar.
    Faturas que falharam por causa do bloqueio são refeitas após o relogin.
  - Métricas por sessão (UCs e faturas por login) para medir a eficiência.

Uso: python robo_v2.py [--force] [--reprocessar-tudo]
"""
import os
import re
import sys
import time
from datetime import datetime

from patchright.sync_api import sync_playwright

from robo import (
    geradoras_cnpjs, LogDuplo, AccessDeniedError, SemCorrespondenciaError,
    verificar_access_denied, marcar_uc_nao_encontrada, selecionar_card_uc,
    _pausa, _pausa_entre_ucs, _digitar,
)
from function.navegador import (
    ESTATISTICAS, esperar, fechar_navegador, fazer_login_com_retry, relogar,
)
from function.erros_navegador import TIMEOUT_ERRORS
from function.tarefa import processar_faturas_do_json
from function.buscar_dados_api import buscar_faturas, criar_json_filtrado_por_status
from database import DatabaseManager, inicializar_banco

URL_LISTAGEM = "https://servicos.energisa.com.br/login/listagem-ucs"
URL_FATURAS = "https://servicos.energisa.com.br/faturas"
MAX_TENTATIVAS_UC = 3
MAX_RELOGINS_SUCESSO_FALSO = 2  # após isso, UCs sem correspondência são tratadas como mal cadastradas

HISTORICO_SESSOES = []


class BloqueioDuranteFaturas(AccessDeniedError):
    """Access Denied no meio dos downloads: guarda as faturas que falharam
    para refazê-las (com force) depois do relogin."""

    def __init__(self, motivo, faturas_restantes):
        super().__init__(motivo)
        self.faturas_restantes = faturas_restantes


class NavegadorFechadoError(Exception):
    """O Chrome caiu. Em 25/09/2026 o Chrome 153 travou (crash dump em
    Download.Start/SafeBrowsing) sempre ao baixar a fatura 6342: a fatura que
    derrubou o navegador fica com erro e NÃO é refeita (evita derrubá-lo em loop);
    as faturas seguintes da mesma UC, que falharam só porque o navegador já tinha
    caído, são refeitas após o relogin."""

    def __init__(self, fatura_culpada=None, faturas_restantes=None):
        super().__init__(f"Chrome fechou/travou (fatura {fatura_culpada})")
        self.fatura_culpada = fatura_culpada
        self.faturas_restantes = faturas_restantes or []


class Sessao:
    """Uma sessão = um login até o próximo relogin (ou fim da geradora)."""
    contador = 0

    def __init__(self, cnpj):
        Sessao.contador += 1
        self.numero = Sessao.contador
        self.cnpj = cnpj
        self.inicio = datetime.now()
        self.ucs = 0
        self.faturas_ok = 0
        self.faturas_erro = 0

    def registrar_uc(self, ok, erro):
        self.ucs += 1
        self.faturas_ok += ok
        self.faturas_erro += erro

    def encerrar(self, motivo):
        minutos = (datetime.now() - self.inicio).total_seconds() / 60
        print(f"\n📊 SESSÃO #{self.numero} encerrada ({motivo}): {self.ucs} UCs, "
              f"{self.faturas_ok} faturas ok, {self.faturas_erro} com erro, {minutos:.1f} min")
        HISTORICO_SESSOES.append({
            "numero": self.numero, "cnpj": self.cnpj, "motivo": motivo, "ucs": self.ucs,
            "faturas_ok": self.faturas_ok, "faturas_erro": self.faturas_erro, "minutos": minutos,
        })


def navegador_vivo(page):
    """False se o Chrome caiu. page.is_closed() continua False após um crash do
    navegador (verificado), então testamos com uma operação barata."""
    try:
        page.title()
        return True
    except Exception as e:
        return "has been closed" not in str(e)


def checar_bloqueio(page, monitor):
    """Lança AccessDeniedError se o listener viu 403 do Akamai ou a página mostra bloqueio."""
    if monitor.bloqueio:
        raise AccessDeniedError(monitor.bloqueio)
    verificar_access_denied(page)


def selecionar_uc(page, monitor, nova_uc):
    """Busca a UC na listagem e clica no card (3 tentativas com backoff)."""
    for tentativa in range(1, 4):
        try:
            checar_bloqueio(page, monitor)
            print(f"   🔄 Tentativa {tentativa} de seleção da UC...")
            page.goto(URL_LISTAGEM, wait_until="load", timeout=30000)
            _pausa(2)
            busca = page.get_by_role("textbox", name="Busque pelo número da UC ou")
            busca.wait_for(state="visible", timeout=15000)
            _pausa(1)
            busca.click(timeout=10000)
            busca.fill("")
            _pausa(0.5)
            _digitar(busca, nova_uc)
            _pausa(2)
            selecionar_card_uc(page, nova_uc)
            _pausa(1)
            print("   ✅ UC selecionada com sucesso")
            return
        except (SemCorrespondenciaError, AccessDeniedError):
            raise
        except Exception as e:
            print(f"   ⚠️ Tentativa {tentativa} falhou: {str(e).splitlines()[0]}")
            if tentativa == 3:
                raise Exception(f"Falha ao selecionar UC {nova_uc} após 3 tentativas")
            time.sleep(tentativa * 2)


def aguardar_saida_listagem(page, monitor, nova_uc):
    """Confirma que o clique no card trocou de UC (saiu da listagem)."""
    for tentativa in range(1, 4):
        try:
            page.wait_for_url("**/login/login**", timeout=15000)
            print(f"   ✅ Navegação bem-sucedida para UC {nova_uc}")
            return
        except TIMEOUT_ERRORS:
            checar_bloqueio(page, monitor)
            url = page.url
            print(f"   🔍 URL atual: {url}")
            if "listagem-ucs" not in url and any(p in url for p in ("/login", "/home", "/faturas")):
                print(f"   ✅ Navegação OK - URL válida: {url}")
                return
            print(f"   ⚠️ Ainda sem trocar de UC (tentativa {tentativa})")
            time.sleep(3)
    raise Exception(f"Navegação falhou para UC {nova_uc} (URL: {page.url})")


def abrir_pagina_faturas(page, monitor):
    for tentativa in range(1, 4):
        try:
            print(f"   📄 Carregando página de faturas (tentativa {tentativa})...")
            page.goto(URL_FATURAS, wait_until="load", timeout=30000)
            _pausa(3)
            checar_bloqueio(page, monitor)
            print("   ✅ Página de faturas carregada")
            return
        except AccessDeniedError:
            raise
        except Exception as e:
            print(f"   ⚠️ Falha ao carregar faturas: {str(e).splitlines()[0]}")
            if tentativa == 3:
                raise Exception("Falha ao carregar página de faturas após 3 tentativas")
            time.sleep(2)


def registrar_uc_sem_faturas(cnpj, nova_uc, faturas_uc):
    db = DatabaseManager()
    db.registrar_execucao_uc(
        cnpj_geradora=cnpj, nova_uc=nova_uc, total_faturas=len(faturas_uc),
        faturas_sucesso=0, faturas_erro=0, faturas_puladas=len(faturas_uc),
        data_hora_inicio=datetime.now(),
    )
    for fatura in faturas_uc:
        db.atualizar_status_fatura(
            fatura_id=fatura.get("id"), status='sucesso', mensagem_erro='UC sem faturas no portal',
            tipo_operacao='nao_encontrada',
            log_execucao=f"UC {nova_uc} sem faturas geradas no portal Energisa",
        )
        print(f"   ✅ Fatura ID {fatura.get('id')} marcada como sucesso (UC sem faturas)")


def processar_uc(page, monitor, cnpj, nova_uc, faturas_uc, force, reprocessar_tudo):
    """Seleciona a UC, abre as faturas e processa. Retorna (faturas_ok, faturas_erro)."""
    checar_bloqueio(page, monitor)
    selecionar_uc(page, monitor, nova_uc)
    aguardar_saida_listagem(page, monitor, nova_uc)
    abrir_pagina_faturas(page, monitor)

    if page.locator('text=Bem-vindo à esta nova conta com a Energisa.').count() > 0:
        print("UC sem faturas geradas no momento.")
        registrar_uc_sem_faturas(cnpj, nova_uc, faturas_uc)
        return 0, 0

    try:
        page.locator('.card-billing__date').first.wait_for(state="visible", timeout=15000)
    except TIMEOUT_ERRORS:
        checar_bloqueio(page, monitor)
        print("   ⚠️ Nenhum card de fatura visível após 15s - seguindo mesmo assim")

    # Botão removido do portal em 28/08/2026; só clica se ainda existir.
    mostrar_mais = page.locator("div").filter(has_text=re.compile(r"^Mostrar mais faturas$")).first
    if mostrar_mais.count() > 0:
        try:
            mostrar_mais.click(timeout=10000)
        except Exception as e:
            print(f"   ⚠️ Clique em 'Mostrar mais faturas' falhou: {str(e).splitlines()[0]}")

    print(f"🎯 Iniciando processamento das faturas da UC {nova_uc}")
    resultados = processar_faturas_do_json(
        {"geradora": cnpj, "lista_ucs": {nova_uc: faturas_uc}}, page,
        force=force, reprocessar_tudo=reprocessar_tudo,
    )
    falhas = [r["id"] for r in resultados if not r["sucesso"] and not r.get("pulada")]
    ok = sum(1 for r in resultados if r["sucesso"])

    if not navegador_vivo(page):
        # A 1ª falha derrubou o Chrome; as seguintes foram vítimas da queda.
        restantes = [f for f in faturas_uc if f.get("id") in falhas[1:]]
        raise NavegadorFechadoError(falhas[0] if falhas else None, restantes)

    if monitor.bloqueio and falhas:
        # As falhas vieram do bloqueio: refazer só elas depois do relogin.
        restantes = [f for f in faturas_uc if f.get("id") in falhas]
        raise BloqueioDuranteFaturas(monitor.bloqueio, restantes)

    print(f"✅ UC {nova_uc} processada: {ok}/{len(resultados)} faturas com sucesso")
    return ok, len(falhas)


def processar_geradora(p, cnpj, force=False, reprocessar_tudo=False):
    print(f"\nProcessando geradora com CNPJ: {cnpj}")
    dados = criar_json_filtrado_por_status(cnpj, force=force, reprocessar_tudo=reprocessar_tudo)
    if not dados or not dados.get("lista_ucs"):
        print(f"✅ Nenhuma fatura pendente para processar na geradora {cnpj}")
        return True

    itens = list(dados["lista_ucs"].items())
    print(f"📋 UCs a processar: {len(itens)} | 📊 Faturas: {sum(len(f) for _, f in itens)}")

    context, page, monitor = fazer_login_com_retry(p, cnpj)
    sessao = Sessao(cnpj)

    def novo_login(motivo, imediato):
        """Encerra a sessão atual e loga de novo (imediato = relogin pós-bloqueio)."""
        nonlocal context, page, monitor, sessao
        sessao.encerrar(motivo)
        if imediato:
            context, page, monitor = relogar(p, cnpj, context)
        else:
            fechar_navegador(context)
            esperar(motivo)
            context, page, monitor = fazer_login_com_retry(p, cnpj)
        sessao = Sessao(cnpj)

    # UC mal cadastrada × login com sucesso falso: 1 UC isolada sem correspondência
    # = cadastro errado; 2 seguidas = login falso (relogin e reprocessa).
    sem_correspondencia = []
    relogins_sucesso_falso = 0

    try:
        i = 0
        while i < len(itens):
            nova_uc, faturas_uc = itens[i]
            print(f"\n🔄 Processando UC {i + 1}/{len(itens)}: {nova_uc} "
                  f"(sessão #{sessao.numero}, UC {sessao.ucs + 1} da sessão)")
            print(f"📊 Faturas para processar: {len(faturas_uc)}")
            if i > 0:
                _pausa_entre_ucs()

            pendentes, force_uc = faturas_uc, force
            tentativa, sucesso, avancar = 0, False, True
            while True:
                tentativa += 1
                try:
                    ok, erro = processar_uc(page, monitor, cnpj, nova_uc, pendentes, force_uc, reprocessar_tudo)
                    sessao.registrar_uc(ok, erro)
                    sucesso = True
                    break

                except AccessDeniedError as e:
                    print(f"🛑 Acesso negado na UC {nova_uc}: {e}")
                    ESTATISTICAS["access_denied"] = ESTATISTICAS.get("access_denied", 0) + 1
                    if isinstance(e, BloqueioDuranteFaturas):
                        pendentes, force_uc = e.faturas_restantes, True
                        print(f"   ♻️ {len(pendentes)} fatura(s) afetada(s) pelo bloqueio serão refeitas")
                    novo_login(f"Access Denied na UC {nova_uc}", imediato=True)
                    tentativa -= 1  # bloqueio não conta como tentativa da UC

                except NavegadorFechadoError as e:
                    print(f"💥 {e} na UC {nova_uc} - fatura mantida com erro para não travar de novo")
                    ESTATISTICAS["navegador_caiu"] = ESTATISTICAS.get("navegador_caiu", 0) + 1
                    novo_login(f"Chrome caiu na UC {nova_uc}", imediato=True)
                    if not e.faturas_restantes:
                        sucesso = True  # nada mais a fazer nesta UC
                        break
                    pendentes, force_uc = e.faturas_restantes, True
                    tentativa -= 1

                except SemCorrespondenciaError:
                    print(f"⚠️ UC {nova_uc}: 'Não encontramos nenhuma correspondência para a sua busca'.")
                    if i not in sem_correspondencia:
                        sem_correspondencia.append(i)
                    if len(sem_correspondencia) < 2:
                        print("➡️ Indo para a próxima UC para confirmar (UC errada × login falso)...")
                        break
                    if relogins_sucesso_falso >= MAX_RELOGINS_SUCESSO_FALSO:
                        print(f"⚠️ Após {relogins_sucesso_falso} relogin(s) as UCs seguem sem correspondência. "
                              "Tratando como mal cadastradas.")
                        for idx in sem_correspondencia:
                            marcar_uc_nao_encontrada(cnpj, *itens[idx])
                        i = sem_correspondencia[-1] + 1
                        relogins_sucesso_falso = 0
                    else:
                        print("🚫 Duas UCs consecutivas sem correspondência → login com sucesso falso.")
                        novo_login("Login com sucesso falso", imediato=False)
                        relogins_sucesso_falso += 1
                        i = sem_correspondencia[0]  # reprocessa desde a 1ª UC afetada
                    sem_correspondencia = []
                    avancar = False
                    break

                except Exception as e:
                    print(f"❌ Erro ao processar UC {nova_uc} (tentativa {tentativa}): {str(e).splitlines()[0]}")
                    if not navegador_vivo(page):
                        # Chrome caiu fora dos downloads: relogar já, sem gastar as tentativas.
                        print("💥 Chrome fechou/travou - relogin imediato")
                        ESTATISTICAS["navegador_caiu"] = ESTATISTICAS.get("navegador_caiu", 0) + 1
                        novo_login(f"Chrome caiu na UC {nova_uc}", imediato=True)
                        tentativa -= 1
                    elif tentativa >= MAX_TENTATIVAS_UC:
                        print(f"⚠️ UC {nova_uc} falhou após {MAX_TENTATIVAS_UC} tentativas rápidas.")
                        novo_login(f"UC {nova_uc} falhou {MAX_TENTATIVAS_UC}x", imediato=False)
                        tentativa = 0
                    else:
                        time.sleep(3)

            if sucesso:
                relogins_sucesso_falso = 0
                for idx in sem_correspondencia:
                    print(f"❌ UC {itens[idx][0]} confirmada como mal cadastrada (login OK). Registrando.")
                    marcar_uc_nao_encontrada(cnpj, *itens[idx])
                sem_correspondencia = []
            if avancar:
                i += 1

        for idx in sem_correspondencia:
            print(f"❌ UC {itens[idx][0]} sem correspondência (não confirmada). Registrando como não encontrada.")
            marcar_uc_nao_encontrada(cnpj, *itens[idx])

        sessao.encerrar("geradora concluída")
        print(f"\n🎉 Processamento da geradora {cnpj} concluído! ({len(itens)} UCs)")
        return True
    finally:
        fechar_navegador(context)


def imprimir_resumo(inicio):
    print("\n" + "=" * 80)
    print("📊 RESUMO DE EFICIÊNCIA (robo_v2)")
    print("=" * 80)
    print(f"{'Sessão':>6} | {'Geradora':<20} | {'UCs':>4} | {'Fat.ok':>6} | {'Fat.erro':>8} | {'Min':>6} | Motivo")
    for s in HISTORICO_SESSOES:
        print(f"{s['numero']:>6} | {s['cnpj']:<20} | {s['ucs']:>4} | {s['faturas_ok']:>6} | "
              f"{s['faturas_erro']:>8} | {s['minutos']:>6.1f} | {s['motivo']}")
    total_ucs = sum(s["ucs"] for s in HISTORICO_SESSOES)
    bloqueadas = [s for s in HISTORICO_SESSOES if s["motivo"].startswith("Access Denied")]
    print("-" * 80)
    print(f"Sessões: {len(HISTORICO_SESSOES)} | UCs: {total_ucs} | "
          f"Faturas ok: {sum(s['faturas_ok'] for s in HISTORICO_SESSOES)} | "
          f"Faturas erro: {sum(s['faturas_erro'] for s in HISTORICO_SESSOES)}")
    if bloqueadas:
        media = sum(s["ucs"] for s in bloqueadas) / len(bloqueadas)
        print(f"UCs por sessão até o Access Denied (média): {media:.1f}")
    print(f"Logins ok: {ESTATISTICAS['logins_ok']} | Logins falhos: {ESTATISTICAS['logins_falhos']} | "
          f"403 no /api/auth: {ESTATISTICAS['auth_403']} | Access Denied: {ESTATISTICAS.get('access_denied', 0)} | "
          f"Chrome caiu: {ESTATISTICAS.get('navegador_caiu', 0)} | Minutos em espera: {ESTATISTICAS['minutos_espera']}")
    print(f"Duração total: {(datetime.now() - inicio).total_seconds() / 60:.1f} min")


def travar_instancia():
    """Impede duas execuções simultâneas: elas disputam o mesmo perfil do Chrome
    e uma derruba o navegador da outra no meio dos downloads.

    Returns:
        arquivo aberto (manter vivo até o fim do processo) ou None se já há outra execução.
    """
    arquivo = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "robo_v2.lock"), "a+")
    arquivo.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        arquivo.close()
        return None
    return arquivo


def main():
    force = '--force' in sys.argv
    reprocessar_tudo = '--reprocessar-tudo' in sys.argv

    trava = travar_instancia()
    if trava is None:
        print("⛔ Já existe um robo_v2.py em execução - abortando para não disputar o perfil do Chrome.")
        sys.exit(1)

    print("💾 Inicializando banco de dados...")
    inicializar_banco()
    os.makedirs('logs', exist_ok=True)
    inicio = datetime.now()
    log = LogDuplo(os.path.join('logs', inicio.strftime("v2-%d%m%Y-%H%M%S.txt")))
    sys.stdout = log
    print(f"📝 ROBÔ V2 (Patchright + Chrome) - {inicio:%d/%m/%Y %H:%M:%S}")
    print("=" * 80)

    try:
        if reprocessar_tudo:
            print("♻️ Modo RERRODADA ativado - TODAS as faturas do dia serão refeitas")
        elif force:
            print("⚠️ Modo FORCE ativado - faturas com erro serão reprocessadas")
        print("📡 Buscando dados atualizados da API...")
        if not buscar_faturas():
            print("❌ Falha ao buscar dados da API. Abortando.")
            return

        with sync_playwright() as p:
            for n, cnpj in enumerate(geradoras_cnpjs, 1):
                print(f"\n🔄 Geradora {n}/{len(geradoras_cnpjs)}: {cnpj}")
                try:
                    processar_geradora(p, cnpj, force=force, reprocessar_tudo=reprocessar_tudo)
                    print(f"✅ SUCESSO: Geradora {cnpj} processada")
                except Exception as e:
                    print(f"❌ ERRO: Geradora {cnpj}: {e}")
                if n < len(geradoras_cnpjs):
                    time.sleep(5)
        print(f"\n✅ Execução finalizada - {datetime.now():%d/%m/%Y %H:%M:%S}")
    except Exception as e:
        print(f"❌ Erro durante execução: {e}")
    finally:
        imprimir_resumo(inicio)
        log.close()
        sys.stdout = log.terminal


if __name__ == "__main__":
    main()
