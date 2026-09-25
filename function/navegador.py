"""Navegador e login do robo_v2: Patchright + Chrome instalado + perfil persistente.

Por que (teste de 24/09/2026): o Akamai Bot Manager do portal responde
403 "Access Denied" no POST /api/auth quando o navegador tem cara de automação.
O Chromium embutido do Playwright (v140) era barrado na maioria das sessões;
o Chrome real controlado pelo Patchright passou em todas. O perfil persistente
guarda os cookies do Akamai (_abck, bm_*) já validados entre execuções.

O 1º envio do CNPJ costuma receber 403 mesmo no navegador bom (também acontece
no acesso manual) e o 2º passa: por isso reenviamos o CNPJ ao ver o 403.
"""
import glob
import os
import re
import shutil
import random
import time
from datetime import datetime

from config import MINUTOS_ENTRE_TENTATIVAS
from function.codigo_sms import obter_codigo_email_com_reenvio_automatico
from function.erros_navegador import TIMEOUT_ERRORS
from robo import aguardar_antes_de_retentar, _pausa, _digitar

URL_LOGIN = "https://servicos.energisa.com.br/login"
DOMINIO = "servicos.energisa.com.br"
PERFIL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "perfil_chrome")
BOTAO_TELEFONE = "ícone de um celular azul 67*****2038"
PREFIXOS_COOKIE_AKAMAI = ("_abck", "bm_", "ak_bmsc")

MAX_ENVIOS_CNPJ = 4
ESPERA_TELEFONE_S = 20

# Contadores da execução inteira, lidos no resumo final do robo_v2.
ESTATISTICAS = {"logins_ok": 0, "logins_falhos": 0, "auth_403": 0, "minutos_espera": 0}


class MonitorRespostas:
    """Listener de respostas do contexto.

    - Guarda o status de cada POST /api/auth (para reagir ao 403 no login).
    - Após o login, qualquer 403 do portal com corpo "Access Denied" (página
      de erro do Akamai) marca a sessão como bloqueada.
    """

    def __init__(self):
        self.status_auth = []
        self.login_ok = False
        self.bloqueio = None
        self.chamadas_api = []  # (status, método, caminho, corpo resumido) - diagnóstico do envio do SMS

    def __call__(self, resposta):
        try:
            if DOMINIO not in resposta.url:
                return
            if not self.login_ok and "/api/" in resposta.url and "/api/auth" not in resposta.url:
                caminho = resposta.url.split(DOMINIO, 1)[1].split("?")[0]
                try:
                    corpo = re.sub(r"[A-Za-z0-9_\-\.]{40,}", "<token>", resposta.text())[:200]
                except Exception:
                    corpo = ""
                self.chamadas_api.append((resposta.status, resposta.request.method, caminho, corpo))
            if "/api/auth" in resposta.url and resposta.request.method == "POST":
                self.status_auth.append(resposta.status)
                if resposta.status == 403:
                    ESTATISTICAS["auth_403"] += 1
            if self.login_ok and resposta.status == 403 and self.bloqueio is None:
                if "Access Denied" in resposta.text():
                    self.bloqueio = f"403 Access Denied em {resposta.url[:120]}"
        except Exception:
            pass  # corpo indisponível / página fechada: não derruba o robô


def esperar(motivo):
    """Espera longa entre tentativas (MINUTOS_ENTRE_TENTATIVAS), contabilizada."""
    ESTATISTICAS["minutos_espera"] += MINUTOS_ENTRE_TENTATIVAS
    aguardar_antes_de_retentar(motivo=motivo)


def fechar_navegador(context):
    if context is None:
        return
    try:
        context.close()
        print("🔒 Navegador fechado")
    except Exception:
        pass


def _salvar_crash_dumps():
    """Move os crash dumps do Chrome para logs/crash_chrome antes de limpar o perfil."""
    dumps = glob.glob(os.path.join(PERFIL_DIR, "Crashpad", "reports", "*.dmp"))
    if not dumps:
        return
    destino = os.path.join(os.path.dirname(PERFIL_DIR), "logs", "crash_chrome")
    os.makedirs(destino, exist_ok=True)
    for dump in dumps:
        shutil.move(dump, os.path.join(destino, f"{datetime.now():%d%m%Y-%H%M%S}_{os.path.basename(dump)}"))
    print(f"💾 {len(dumps)} crash dump(s) do Chrome salvos em {destino}")


def _limpar_historico_downloads():
    """Apaga o histórico de downloads do perfil (mantém cookies).

    O Chrome travava (crash em Download.Start / LEGACY_DOWNLOAD) no 1º download
    de uma nova abertura sempre que o perfil trazia downloads de uma abertura
    anterior - cujos arquivos o Playwright já apagou da pasta temporária. Com o
    histórico vazio isso não acontecia (5 de 5 casos em 25/09/2026).
    """
    padrao = os.path.join(PERFIL_DIR, "Default")
    for nome in ("History", "History-journal"):
        try:
            os.remove(os.path.join(padrao, nome))
        except FileNotFoundError:
            pass
    shutil.rmtree(os.path.join(padrao, "Download Service"), ignore_errors=True)


def _resetar_perfil():
    """Apaga o perfil persistente. Após um Access Denied o bloqueio fica preso
    aos cookies/perfil (não ao IP): com perfil novo a página de login volta a
    abrir na hora (verificado em 25/09/2026)."""
    _salvar_crash_dumps()
    shutil.rmtree(PERFIL_DIR, ignore_errors=True)
    print("🗑️ Perfil do Chrome apagado (recomeçando sem cookies do Akamai)")


def _abrir_navegador(p):
    """Chrome instalado com perfil persistente, sem flags nem scripts de "stealth"
    (eles deixam o fingerprint mais suspeito, não menos)."""
    _salvar_crash_dumps()
    _limpar_historico_downloads()
    print(f"🌐 Iniciando Chrome (Patchright) com perfil {PERFIL_DIR}...")
    # Maximizado: um perfil novo abre a janela pequena (~1036x647) e, com pouca
    # altura, o botão de download cai mais vezes sob o degradê da lista de faturas.
    return p.chromium.launch_persistent_context(
        PERFIL_DIR, channel="chrome", headless=False, no_viewport=True, accept_downloads=True,
        args=["--start-maximized"],
    )


def _limpar_sessao(context, page, manter_akamai):
    """Apaga cookies e storage do portal para trocar de geradora sem herdar a
    sessão anterior. Com manter_akamai=True preserva os cookies do Akamai."""
    manter = []
    if manter_akamai:
        manter = [c for c in context.cookies() if c["name"].startswith(PREFIXOS_COOKIE_AKAMAI)]
    context.clear_cookies()
    if manter:
        context.add_cookies(manter)
    try:
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        pass
    print(f"🧹 Sessão limpa ({'mantendo' if manter_akamai else 'SEM'} cookies do Akamai: {len(manter)})")


def mexer_mouse(page, movimentos=4):
    for _ in range(movimentos):
        page.mouse.move(random.randint(200, 1000), random.randint(150, 600),
                        steps=random.randint(8, 25))
        time.sleep(random.uniform(0.2, 0.7))


def _aguardar_resultado_cnpj(page, monitor, auth_antes):
    """Espera a tela de telefone ou um 403 novo no /api/auth.

    Returns:
        str: 'ok', '403' ou 'timeout'.
    """
    botao = page.locator("button:has-text('67')").first
    limite = time.time() + ESPERA_TELEFONE_S
    while time.time() < limite:
        try:
            if botao.is_visible():
                return "ok"
        except Exception:
            pass
        if len(monitor.status_auth) > auth_antes and monitor.status_auth[-1] == 403:
            return "403"
        time.sleep(0.5)
    return "timeout"


def _enviar_cnpj(page, monitor, cnpj):
    """Preenche o CNPJ e clica em Entrar até a tela de telefone aparecer."""
    for envio in range(1, MAX_ENVIOS_CNPJ + 1):
        campo = page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ")
        try:
            campo.wait_for(state="visible", timeout=15000)
        except TIMEOUT_ERRORS:
            print("   ↩️ Campo de CNPJ não visível - recarregando a tela de login")
            page.goto(URL_LOGIN, wait_until="load", timeout=60000)
            _pausa(3)
            campo.wait_for(state="visible", timeout=15000)
        campo.click()
        campo.fill("")
        _digitar(campo, cnpj)
        mexer_mouse(page, 2)
        auth_antes = len(monitor.status_auth)
        page.get_by_role("button", name="Entrar").click()

        resultado = _aguardar_resultado_cnpj(page, monitor, auth_antes)
        if resultado == "ok":
            print(f"✅ CNPJ aceito no envio {envio}/{MAX_ENVIOS_CNPJ}")
            return
        print(f"⚠️ Envio {envio}/{MAX_ENVIOS_CNPJ} do CNPJ não avançou "
              f"({'403 no /api/auth' if resultado == '403' else f'sem resposta em {ESPERA_TELEFONE_S}s'})")
        time.sleep(random.uniform(3, 6))
    raise Exception(f"CNPJ não avançou após {MAX_ENVIOS_CNPJ} envios (/api/auth: {monitor.status_auth})")


def fazer_login(p, cnpj, manter_akamai=True):
    """Abre o Chrome, faz o login completo (CNPJ → telefone → código SMS).

    Returns:
        tuple: (context, page, monitor)
    """
    print("🔐 Iniciando processo de Login (v2)")
    if not manter_akamai:
        _resetar_perfil()
    context = _abrir_navegador(p)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        monitor = MonitorRespostas()
        context.on("response", monitor)

        page.goto(URL_LOGIN, wait_until="load", timeout=60000)
        _limpar_sessao(context, page, manter_akamai)
        page.goto(URL_LOGIN, wait_until="load", timeout=60000)
        _pausa(4)
        mexer_mouse(page)

        print("✏️ Preenchendo CNPJ...")
        _enviar_cnpj(page, monitor, cnpj)
        chamadas_antes = len(monitor.chamadas_api)
        page.get_by_role("button", name=BOTAO_TELEFONE).click()
        time.sleep(6)
        print("📨 Respostas do portal ao pedido de SMS:")
        for status, metodo, caminho, corpo in monitor.chamadas_api[chamadas_antes:] or [("-", "-", "nenhuma chamada /api/ capturada", "")]:
            print(f"   {status} {metodo} {caminho} {corpo!r}")

        codigo = obter_codigo_email_com_reenvio_automatico(page, 600)
        if not codigo or len(codigo) < 4:
            raise Exception("Não foi possível obter o código de verificação")

        page.get_by_role("textbox", name="Dígito 1 do código").wait_for(state="visible", timeout=10000)
        for posicao, digito in enumerate(codigo[:4], 1):
            campo = page.get_by_role("textbox", name=f"Dígito {posicao} do código")
            campo.click()
            campo.fill(digito)
            _pausa(0.4)

        time.sleep(10)
        monitor.login_ok = True
        ESTATISTICAS["logins_ok"] += 1
        print("✅ Login feito com sucesso!")
        return context, page, monitor
    except Exception as e:
        ESTATISTICAS["logins_falhos"] += 1
        print(f"❌ Erro durante login: {str(e).splitlines()[0]}")
        try:
            os.makedirs("logs", exist_ok=True)
            page.screenshot(path=os.path.join("logs", f"v2_login_falha_{datetime.now():%H%M%S}.png"))
        except Exception:
            pass
        fechar_navegador(context)
        raise


def fazer_login_com_retry(p, cnpj, manter_akamai_inicial=True):
    """Tenta logar até conseguir, esperando MINUTOS_ENTRE_TENTATIVAS entre falhas.

    A 1ª tentativa preserva os cookies do Akamai (se manter_akamai_inicial). Se
    ela falhar, o perfil pode estar bloqueado: a 2ª vem na hora, com perfil novo.
    Daí em diante, espera longa entre tentativas, sempre com perfil novo.
    """
    tentativa = 0
    while True:
        tentativa += 1
        manter = tentativa == 1 and manter_akamai_inicial
        print(f"\n{'=' * 80}\n🔐 TENTATIVA DE LOGIN #{tentativa} - {datetime.now():%d/%m/%Y %H:%M:%S}\n{'=' * 80}\n")
        try:
            return fazer_login(p, cnpj, manter_akamai=manter)
        except Exception:
            if manter:
                print("↪️ Falhou com o perfil atual - tentando já com perfil novo")
                continue
            esperar(f"Falha no login (tentativa {tentativa})")


def relogar(p, cnpj, context):
    """Relogin após bloqueio: na hora e com perfil novo (os cookies do Akamai
    da sessão bloqueada mantêm o bloqueio); espera longa só se falhar."""
    fechar_navegador(context)
    _pausa(5)
    print("🔐 Relogin imediato após bloqueio (perfil novo)...")
    try:
        return fazer_login(p, cnpj, manter_akamai=False)
    except Exception:
        print("⚠️ Relogin imediato falhou - entrando no ciclo de espera + nova tentativa")
        esperar("Relogin imediato falhou")
        return fazer_login_com_retry(p, cnpj, manter_akamai_inicial=False)
