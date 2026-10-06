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
from urllib.parse import urlparse

from config import MINUTOS_ENTRE_TENTATIVAS
from function.codigo_sms import obter_codigo_email_com_reenvio_automatico, ultimo_id_email_sms
from function.erros_navegador import TIMEOUT_ERRORS
from robo import aguardar_antes_de_retentar, _pausa, _digitar

URL_LOGIN = "https://servicos.energisa.com.br/login"
DOMINIO = "servicos.energisa.com.br"
PERFIL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "perfil_chrome")
BOTAO_TELEFONE = "ícone de um celular azul 67*****2038"
PREFIXOS_COOKIE_AKAMAI = ("_abck", "bm_", "ak_bmsc")
ORIGEM_PORTAL = "https://servicos.energisa.com.br"
# Tudo menos cookies (esses são tratados à parte, para preservar os do Akamai).
STORAGE_PORTAL = "local_storage,indexeddb,cache_storage,service_workers,websql,file_systems"

MAX_ENVIOS_CNPJ = 4
ESPERA_TELEFONE_S = 20
# Logins que deram certo tiveram no máximo 2 respostas 403 seguidas (padrão
# "403, 403, sem resposta, aceito"); os que falharam tiveram 4. Com 3 seguidas o
# IP está punido: insistir só aumenta a punição (28/09/2026).
MAX_403_SEGUIDOS = 3
MINUTOS_ESPERA_MAX = 120

# Contadores da execução inteira, lidos no resumo final do robo_v2.
ESTATISTICAS = {"logins_ok": 0, "logins_falhos": 0, "auth_403": 0, "minutos_espera": 0}
# ucs_no_cookie: UCs consultadas com o cookie atual do Akamai (zera com perfil novo);
# a cota observada é de 62-65 UCs por cookie (17 de 17 casos, 25-28/09/2026).
# falhas_seguidas: esperas longas desde o último login bom (espera crescente).
ESTADO = {"ucs_no_cookie": 0, "falhas_seguidas": 0}


class IpPunidoError(Exception):
    """O /api/auth recusou o CNPJ várias vezes seguidas: a punição é do IP, não
    do perfil - tentar de novo na hora, mesmo com perfil novo, só piora."""


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
    """Espera longa e crescente entre tentativas: MINUTOS_ENTRE_TENTATIVAS × falhas
    seguidas (30, 60, 90...), até MINUTOS_ESPERA_MAX. Zera no próximo login bom."""
    ESTADO["falhas_seguidas"] += 1
    minutos = min(MINUTOS_ENTRE_TENTATIVAS * ESTADO["falhas_seguidas"], MINUTOS_ESPERA_MAX)
    ESTATISTICAS["minutos_espera"] += minutos
    aguardar_antes_de_retentar(minutos=minutos, motivo=motivo)


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
    ESTADO["ucs_no_cookie"] = 0
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


def _limpar_sessao(context, page, manter_akamai, origem=ORIGEM_PORTAL):
    """Apaga cookies e storage do portal para trocar de geradora sem herdar a
    sessão anterior. Com manter_akamai=True preserva os cookies do Akamai."""
    manter = []
    if manter_akamai:
        manter = [c for c in context.cookies() if c["name"].startswith(PREFIXOS_COOKIE_AKAMAI)]
    context.clear_cookies()
    if manter:
        context.add_cookies(manter)
    # Storage do portal apagado pelo navegador (CDP), não pela página: com o
    # portal logado, /login redireciona sozinho para /home e o evaluate falhava
    # em silêncio no meio do redirecionamento - o robô abria já logado
    # (28/09/2026, perfil que sobrou de um Chrome derrubado).
    try:
        cdp = context.new_cdp_session(page)
        cdp.send("Storage.clearDataForOrigin", {"origin": origem, "storageTypes": STORAGE_PORTAL})
        cdp.detach()
    except Exception as e:
        print(f"⚠️ Não foi possível limpar o storage do portal via CDP: {str(e).splitlines()[0]}")
    try:
        page.evaluate("() => sessionStorage.clear()")
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
    """Preenche o CNPJ e clica em Entrar até a tela de telefone aparecer.

    Raises:
        IpPunidoError: MAX_403_SEGUIDOS recusas seguidas no /api/auth.
    """
    recusas_seguidas = 0
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
        recusas_seguidas = recusas_seguidas + 1 if resultado == "403" else 0
        if recusas_seguidas >= MAX_403_SEGUIDOS:
            raise IpPunidoError(f"{recusas_seguidas} recusas seguidas no /api/auth - IP provavelmente punido "
                                f"(/api/auth: {monitor.status_auth})")
        time.sleep(random.uniform(3, 6))
    # O aceite (200) às vezes chega depois do prazo do último envio: dar uma folga
    # antes de desistir (28/09/2026: 200 chegou tarde e o robô entrou na espera).
    if monitor.status_auth and monitor.status_auth[-1] == 200:
        try:
            page.locator("button:has-text('67')").first.wait_for(state="visible", timeout=20000)
            print("✅ CNPJ aceito (resposta do portal chegou depois do último envio)")
            return
        except TIMEOUT_ERRORS:
            pass
    raise Exception(f"CNPJ não avançou após {MAX_ENVIOS_CNPJ} envios (/api/auth: {monitor.status_auth})")


def _campos_do_codigo(page, espera_s=30):
    """Os 4 campos do código SMS.

    Em 04/10 e 05/10/2026 a busca por get_by_role("textbox", name="Dígito 1 do
    código") falhou com a tela do código visível. Aqui vale qualquer campo cujo
    rótulo seja "Dígito N" (textbox, spinbutton...) e, na falta, os 4 primeiros
    inputs visíveis de 1 caractere. Sem nada em `espera_s`, registra os inputs
    da tela no log (para ajustar o seletor) e falha.
    """
    limite = time.time() + espera_s
    while time.time() < limite:
        try:
            por_rotulo = [page.get_by_label(re.compile(rf"d[ií]gito\s*{n}\b", re.IGNORECASE)).first
                          for n in range(1, 5)]
            if all(c.is_visible() for c in por_rotulo):
                return por_rotulo
            curtos = page.locator("input[maxlength='1']:visible")
            if curtos.count() >= 4:
                print("ℹ️ Campos do código achados pelo tamanho (sem rótulo 'Dígito N')")
                return [curtos.nth(i) for i in range(4)]
        except Exception:
            pass
        time.sleep(0.5)
    try:
        inputs = page.evaluate("() => Array.from(document.querySelectorAll('input'))"
                               ".slice(0, 8).map(i => i.outerHTML.slice(0, 200))")
        print(f"🔎 Inputs da tela do código: {inputs}")
    except Exception:
        pass
    raise Exception(f"Campos do código não encontrados em {espera_s}s")


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

        # Limpa ANTES do 1º acesso: cookies/sessão antigos nunca chegam ao portal.
        _limpar_sessao(context, page, manter_akamai)
        page.goto(URL_LOGIN, wait_until="load", timeout=60000)
        _pausa(4)
        if urlparse(page.url).path.rstrip("/") != "/login":
            # Ainda logado (/home, /login/listagem-ucs...): falhar já, para a próxima tentativa vir com perfil novo.
            raise Exception(f"Portal continuou logado após limpar a sessão (URL: {page.url})")
        mexer_mouse(page)

        print("✏️ Preenchendo CNPJ...")
        _enviar_cnpj(page, monitor, cnpj)
        chamadas_antes = len(monitor.chamadas_api)
        email_antes = ultimo_id_email_sms()
        page.get_by_role("button", name=BOTAO_TELEFONE).click()
        time.sleep(6)
        print("📨 Respostas do portal ao pedido de SMS:")
        for status, metodo, caminho, corpo in monitor.chamadas_api[chamadas_antes:] or [("-", "-", "nenhuma chamada /api/ capturada", "")]:
            print(f"   {status} {metodo} {caminho} {corpo!r}")

        codigo = obter_codigo_email_com_reenvio_automatico(page, 600, apos_id=email_antes)
        if not codigo or len(codigo) < 4:
            raise Exception("Não foi possível obter o código de verificação")

        campos = _campos_do_codigo(page)
        primeiro_digito = campos[0]
        for campo, digito in zip(campos, codigo[:4]):
            campo.click()
            campo.fill(digito)
            _pausa(0.4)

        # Código aceito = o portal sai da tela do código. Se os campos continuam
        # lá, o código foi recusado (antes o robô declarava sucesso mesmo assim).
        try:
            primeiro_digito.wait_for(state="hidden", timeout=30000)
        except TIMEOUT_ERRORS:
            raise Exception(f"Portal não aceitou o código {codigo} (tela do código ainda aberta após 30s)")
        time.sleep(5)
        monitor.login_ok = True
        ESTATISTICAS["logins_ok"] += 1
        ESTADO["falhas_seguidas"] = 0
        if manter_akamai:
            ESTADO["ucs_no_cookie"] += 1  # um login a mais no mesmo cookie também gasta a cota
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
    ela falhar - inclusive com 403 seguidos - o problema pode ser só o cookie:
    a 2ª vem na hora, com perfil novo (28/09/2026: cookie mantido com ~38 UCs de
    cota levou 3×403 enquanto perfis novos no mesmo IP passavam). Com perfil novo
    recusado, o IP está punido: espera longa e crescente entre as tentativas.
    """
    tentativa = 0
    repeticao_rapida_usada = False
    while True:
        tentativa += 1
        manter = tentativa == 1 and manter_akamai_inicial
        print(f"\n{'=' * 80}\n🔐 TENTATIVA DE LOGIN #{tentativa} - {datetime.now():%d/%m/%Y %H:%M:%S}\n{'=' * 80}\n")
        try:
            return fazer_login(p, cnpj, manter_akamai=manter)
        except Exception as e:
            if manter:
                print("↪️ Falhou com o cookie mantido - tentando já com perfil novo")
                continue
            if isinstance(e, IpPunidoError):
                esperar(f"IP punido pelo Akamai (tentativa {tentativa})")
            elif not repeticao_rapida_usada:
                # Falha que não é do Akamai (tela demorou, SMS atrasou...): uma nova
                # tentativa na hora costuma passar; a espera longa vem só depois.
                repeticao_rapida_usada = True
                print("↪️ Falha no login que não é do Akamai - tentando de novo na hora")
            else:
                esperar(f"Falha no login (tentativa {tentativa})")


def relogar(p, cnpj, context):
    """Relogin na hora com perfil novo - após bloqueio (os cookies do Akamai da
    sessão bloqueada mantêm o bloqueio) ou na troca preventiva de perfil antes de
    estourar a cota. Espera longa só se falhar."""
    fechar_navegador(context)
    _pausa(5)
    print("🔐 Relogin imediato com perfil novo...")
    try:
        return fazer_login(p, cnpj, manter_akamai=False)
    except IpPunidoError:
        pass
    except Exception:
        # Não é do Akamai (tela demorou, SMS atrasou...): mais uma vez na hora.
        print("↪️ Relogin falhou por motivo que não é do Akamai - tentando de novo na hora")
        try:
            return fazer_login(p, cnpj, manter_akamai=False)
        except Exception:
            pass
    print("⚠️ Relogin imediato falhou - entrando no ciclo de espera + nova tentativa")
    esperar("Relogin imediato falhou")
    return fazer_login_com_retry(p, cnpj, manter_akamai_inicial=False)
