from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import re
import sys
from datetime import datetime, timedelta

from function.codigo_sms import obter_codigo_email, obter_codigo_email_com_reenvio_automatico
from geradoras import (
    USINA_LUNA_CNPJ,
    USINA_SULINA_CNPJ,
    USINA_LB_CNPJ,
    USINA_ENERGIAA_CNPJ,
    USINA_LUZDIVINA_CNPJ,
    USINA_G114_CNPJ,
    USINA_SLLG,
    USINA_EVIC_CNPJ
)
from function.tarefa import executar_fatura_pendente, executar_fatura_vencida, processar_faturas_do_json
from function.buscar_dados_api import buscar_faturas
from database import DatabaseManager, inicializar_banco
import json
import os
import random
from config import HUMANIZAR, DELAY_UC_MIN, DELAY_UC_MAX, MINUTOS_ENTRE_TENTATIVAS

# Lista com todos os CNPJs das geradoras
geradoras_cnpjs = [
    USINA_ENERGIAA_CNPJ,
    USINA_SULINA_CNPJ,
    USINA_LUNA_CNPJ,
    USINA_LB_CNPJ,
    USINA_LUZDIVINA_CNPJ,
    USINA_G114_CNPJ,
    USINA_SLLG,
    USINA_EVIC_CNPJ
]

class LogDuplo:
    """Classe para duplicar prints no console e em arquivo"""
    def __init__(self, arquivo_log):
        self.terminal = sys.stdout
        self.log = open(arquivo_log, 'w', encoding='utf-8')

    def write(self, mensagem):
        self.terminal.write(mensagem)
        self.log.write(mensagem)
        # Grava na hora: sem isso o arquivo só recebe o texto a cada ~8 KB e
        # parece "parado" no meio de uma UC enquanto o robô espera 30 min.
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()

def iniciar_log():
    """Inicia o sistema de logging com nome baseado em data e hora"""
    # Criar pasta logs se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Gerar nome do arquivo: dia-hora.txt (formato: 11012026-134530.txt)
    agora = datetime.now()
    nome_arquivo = agora.strftime("%d%m%Y-%H%M%S.txt")
    caminho_log = os.path.join('logs', nome_arquivo)

    # Redirecionar stdout para o sistema de log duplo
    log_duplo = LogDuplo(caminho_log)
    sys.stdout = log_duplo

    print(f"📝 Log iniciado: {caminho_log}")
    print(f"🕐 Data/Hora: {agora.strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 80)

    return log_duplo

class AccessDeniedError(Exception):
    """Sinaliza que o portal retornou bloqueio 'Access Denied'.

    Em vez de encerrar o robô, esse erro é capturado no laço de
    processamento para aguardar (MINUTOS_ENTRE_TENTATIVAS) e tentar novamente.
    """
    pass


class SemCorrespondenciaError(Exception):
    """Sinaliza que a busca da UC retornou "Não encontramos nenhuma
    correspondência para a sua busca".

    Pode indicar UC mal cadastrada (login OK) ou login com sucesso falso.
    A distinção é feita no laço de processamento das UCs.
    """
    pass


def verificar_access_denied(page):
    """Verifica se a página contém bloqueio 'Access Denied'

    Returns:
        bool: False se não detectou bloqueio.

    Raises:
        AccessDeniedError: Se Access Denied for detectado. O laço de
            processamento trata esse erro aguardando (MINUTOS_ENTRE_TENTATIVAS)
            e refazendo o login, sem parar o robô.
    """
    try:
        # Verificar se existe texto "Access Denied" na página
        if page.locator('text=Access Denied').count() > 0:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied'")
            raise AccessDeniedError("Access Denied detectado")

        # Verificar também no título da página
        titulo = page.title().lower()
        if 'access denied' in titulo or 'acesso negado' in titulo:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied' no título da página")
            raise AccessDeniedError("Access Denied detectado no título")

        # Verificar se a URL atual é de logout (indicativo de Access Denied)
        current_url = page.url
        if '/logout' in current_url:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied' - URL de logout")
            raise AccessDeniedError("Access Denied detectado (logout)")

        return False
    except AccessDeniedError:
        # Re-lançar para ser tratado pelo laço de processamento (espera + retry)
        raise
    except Exception as e:
        print(f"⚠️ Erro ao verificar Access Denied: {str(e)}")
        return False


def aguardar_antes_de_retentar(minutos=MINUTOS_ENTRE_TENTATIVAS, motivo="Erro detectado"):
    """Aguarda (com contagem regressiva) antes de uma nova tentativa.

    Usado tanto para bloqueio de acesso quanto para falhas de
    navegação/carregamento, para que o robô não pare nem pule a UC.

    Args:
        minutos (int): Minutos a aguardar antes da nova tentativa.
        motivo (str): Texto exibido para indicar o que disparou a espera.
    """
    proxima_tentativa = datetime.now() + timedelta(minutes=minutos)
    print(f"\n{'='*80}")
    print(f"⏳ {motivo}: aguardando {minutos} minutos antes de tentar novamente...")
    print(f"🕐 Próxima tentativa às: {proxima_tentativa.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*80}\n")

    # Contagem regressiva com atualização a cada minuto
    for minutos_restantes in range(minutos, 0, -1):
        print(f"⏰ {minutos_restantes} minuto(s) restante(s)...")
        time.sleep(60)

    print("\n🔄 Retomando processamento após espera...\n")


def verificar_sem_correspondencia(page):
    """Verifica se a busca da UC não retornou correspondência.

    O portal mostra "Não encontramos nenhuma correspondência para a sua busca"
    tanto quando a nova_uc está mal cadastrada quanto quando o login deu um
    "sucesso falso" (nenhuma UC carregou). A distinção é feita no laço de
    processamento (1 UC isolada = cadastro errado; 2+ seguidas = login falso).

    Desde 04/09/2026 a listagem sempre mostra as seções "Ativos (N)" e
    "Inativos (N)", e a seção "Inativos (0)" expandida exibe o MESMO aviso.
    Por isso este retorno só significa "UC não encontrada" quando não há card
    da UC na página — quem decide isso é selecionar_card_uc. O aviso precisa
    estar VISÍVEL: recolhido dentro de "Inativos (0)" ele existe em toda busca.

    Returns:
        bool: True se o aviso de "sem correspondência" está visível.
    """
    try:
        aviso = page.get_by_text("Não encontramos nenhuma correspondência", exact=False)
        return aviso.count() > 0 and aviso.first.is_visible()
    except Exception:
        return False


def marcar_uc_nao_encontrada(geradora_cnpj, nova_uc, faturas_uc):
    """Registra no banco que a UC não foi encontrada no portal (busca sem
    correspondência), sinalizando provável erro de cadastro da nova_uc.
    """
    try:
        db = DatabaseManager()
        db.registrar_execucao_uc(
            cnpj_geradora=geradora_cnpj,
            nova_uc=nova_uc,
            total_faturas=len(faturas_uc),
            faturas_sucesso=0,
            faturas_erro=len(faturas_uc),
            faturas_puladas=0,
            data_hora_inicio=datetime.now()
        )
        for fatura in faturas_uc:
            fatura_id = fatura.get("id")
            db.atualizar_status_fatura(
                fatura_id=fatura_id,
                status='erro',
                mensagem_erro='UC não encontrada no portal (busca sem correspondência - verificar cadastro da nova_uc)',
                tipo_operacao='nao_encontrada',
                log_execucao=f"UC {nova_uc}: 'Não encontramos nenhuma correspondência para a sua busca'"
            )
            print(f"   📝 Fatura ID {fatura_id} marcada como erro (UC não encontrada)")
    except Exception as e:
        print(f"⚠️ Erro ao registrar UC não encontrada {nova_uc}: {str(e)}")


# Espera pelo card da UC após digitar a busca (a listagem filtra conforme se
# digita; o card costuma aparecer em menos de 2 s). 10 s repõe a margem do
# código antigo (2 s de pausa + 10 s de clique).
ESPERA_CARD_UC_MS = 10000

# Cabeçalhos-acordeão da listagem. Ancorados em ^ porque o nome acessível de
# um card é todo o seu texto (número, badge, código, endereço) e "Inativos"
# sem âncora casaria um card cujo endereço contenha a palavra.
SECAO_ATIVOS = r"^\s*Ativos"
SECAO_INATIVOS = r"^\s*Inativos"


def _aguardar_visivel(locator, timeout_ms):
    """True se o locator ficou visível dentro do prazo; False se estourou."""
    try:
        locator.wait_for(state="visible", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def _cabecalho_secao(page, nome):
    """Botão-acordeão "Ativos (N)"/"Inativos (N)" da listagem de UCs.

    Returns:
        tuple: (locator do botão ou None se não existir/visível,
                contagem N ou None se o nome não trouxer "(N)").
    """
    botao = page.get_by_role("button", name=re.compile(nome, re.IGNORECASE))
    if botao.count() == 0 or not botao.first.is_visible():
        return None, None
    contagem = re.search(r"\((\d+)\)", botao.first.inner_text())
    return botao.first, (int(contagem.group(1)) if contagem else None)


def _expandir_secao_listagem(page, nome):
    """Expande a seção "Ativos (N)"/"Inativos (N)" da listagem de UCs, se fizer sentido.

    Uma seção vazia ("Inativos (0)") NÃO é expandida: aberta, ela mostra o
    mesmo aviso "Não encontramos nenhuma correspondência" da busca sem
    resultado, que era confundido com UC não encontrada (04/09/2026). Uma
    seção já expandida (aria-expanded="true") também não: o clique é um
    toggle e a recolheria. Sem contagem no nome (layout até 03/09, em que
    "Inativos" só aparecia quando a UC era inativa), expande como antes.

    Returns:
        bool: True se clicou para expandir.
    """
    try:
        botao, contagem = _cabecalho_secao(page, nome)
        if botao is None:
            return False
        texto = botao.inner_text().strip()
        if contagem == 0:
            print(f"   ℹ️ Seção '{texto}' vazia - não expandir")
            return False
        if botao.get_attribute("aria-expanded") == "true":
            print(f"   ℹ️ Seção '{texto}' já está expandida")
            return False
        print(f"   ℹ️ Expandindo seção '{texto}'...")
        botao.click(timeout=5000)
        _pausa(1)
        return True
    except Exception as e:
        print(f"   ⚠️ Não foi possível expandir a seção {nome}: {str(e)}")
        return False


def _listagem_vazia(page):
    """True se a listagem tem cabeçalhos de seção e todos marcam "(0)".

    É o sinal de "UC não encontrada" no layout novo mesmo quando o aviso de
    sem correspondência está recolhido (fora da tela ou fora do DOM).
    """
    try:
        contagens = [c for _, c in (_cabecalho_secao(page, SECAO_ATIVOS),
                                    _cabecalho_secao(page, SECAO_INATIVOS)) if c is not None]
        return bool(contagens) and all(c == 0 for c in contagens)
    except Exception:
        return False


def selecionar_card_uc(page, nova_uc):
    """Localiza e clica no card da UC na listagem, após a busca ter sido digitada.

    O card é um <button> com "Código do Cliente: 10/<nova_uc>-D". O número é
    casado ancorado ao rótulo — o texto do card inclui o endereço, que também
    traz sequências de 6-7 dígitos — e com fronteira de dígito à direita, para
    386212 não casar 3862127; zeros à esquerda são tolerados. has_text com
    regex casa o textContent bruto do botão (sem espaço entre elementos e sem
    normalização) e só aceita as flags I/S/M.

    Ordem: card visível → clica. Senão, expande "Inativos (N)" (UC inativa) e
    procura de novo; card presente mas oculto → expande "Ativos". Sem nenhum
    card da UC: aviso de sem correspondência VISÍVEL ou cabeçalhos "(0)"/"(0)"
    significam UC não encontrada; nada disso, a busca não carregou e o retry
    da navegação decide.

    Raises:
        SemCorrespondenciaError: nenhum card da UC e (aviso visível ou listagem vazia).
        Exception: nenhum card da UC sem esses sinais, ou card apenas oculto.
    """
    padrao_uc = re.compile(rf"Código do Cliente:\s*(?:\d+/)?0*{re.escape(nova_uc)}(?!\d)", re.IGNORECASE)
    cards = page.locator("button").filter(has_text=padrao_uc)  # inclui ocultos
    card = cards.filter(visible=True)

    if not _aguardar_visivel(card.first, ESPERA_CARD_UC_MS):
        # UC inativa: o card fica na seção "Inativos (N)", recolhida.
        if _expandir_secao_listagem(page, SECAO_INATIVOS):
            _aguardar_visivel(card.first, 5000)
    if card.count() == 0 and cards.count() > 0:
        # Card existe mas está oculto: seção "Ativos" recolhida.
        if _expandir_secao_listagem(page, SECAO_ATIVOS):
            _aguardar_visivel(card.first, 3000)

    if card.count() > 0:
        card.first.click(timeout=10000)
        return
    if cards.count() > 0:
        raise Exception(f"Card da UC {nova_uc} existe na listagem mas está oculto (seção recolhida)")
    if verificar_sem_correspondencia(page) or _listagem_vazia(page):
        raise SemCorrespondenciaError(nova_uc)
    raise Exception(f"Card da UC {nova_uc} não apareceu na listagem (sem aviso de 'sem correspondência')")

def _pausa(segundos):
    """Espera 'segundos' com jitter humano quando HUMANIZAR; senão, fixo."""
    if HUMANIZAR:
        time.sleep(random.uniform(segundos * 0.6, segundos * 1.6))
    else:
        time.sleep(segundos)


def _pausa_entre_ucs():
    """Pausa aleatória entre UCs — quebra o ritmo de máquina do scraping."""
    if HUMANIZAR:
        s = random.uniform(DELAY_UC_MIN, DELAY_UC_MAX)
        print(f"⏳ Pausa de {s:.1f}s antes da próxima UC...")
        time.sleep(s)


def _digitar(locator, texto):
    """Digita caractere a caractere com delay humano (quando HUMANIZAR)."""
    if HUMANIZAR and texto:
        locator.press_sequentially(texto, delay=random.uniform(60, 160))
    else:
        locator.fill(texto)


def fazer_login(p, geradora_cnpj):
    """Realiza o processo de login e retorna browser, context e page"""
    print("🔐 Iniciando processo de Login")

    browser = None
    context = None
    page = None

    try:
        # Usar Chromium como padrão
        print("🌐 Iniciando Chromium...")
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )

        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            locale='pt-BR',
            timezone_id='America/Sao_Paulo',
            permissions=['geolocation']
        )

        # Adicionar script para mascarar automação
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['pt-BR', 'pt', 'en-US', 'en']
            });
            window.chrome = {
                runtime: {}
            };
        """)

        print("🌐 Navegando para página de login...")
        page.goto("https://servicos.energisa.com.br/login", wait_until="load", timeout=60000)
        _pausa(5)  # Aguardar carregamento completo e possíveis scripts (com jitter)

        # Tirar screenshot para debug
        page.screenshot(path="debug_login.png")
        print("📸 Screenshot salvo: debug_login.png")

        # Selecionar campo de CNPJ (com retry: às vezes o portal volta para a
        # mesma tela de CPF/CNPJ logo após o "Entrar". Reenviar os mesmos dados
        # costuma resolver, então tentamos até MAX_TENTATIVAS_CNPJ vezes antes
        # de deixar cair no retry completo de login.)
        print("✏️ Preenchendo CNPJ...")
        MAX_TENTATIVAS_CNPJ = 2
        for tentativa_cnpj in range(1, MAX_TENTATIVAS_CNPJ + 1):
            campo_cnpj = page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ")
            campo_cnpj.click()
            _digitar(campo_cnpj, geradora_cnpj)
            _pausa(0.6)
            page.get_by_role("button", name="Entrar").click()

            # Se a seleção de telefone aparecer, o login avançou. Se o portal
            # voltar para a tela de CPF/CNPJ, esse botão não aparece dentro do
            # tempo → reenviamos os dados na próxima iteração.
            try:
                page.wait_for_selector("button:has-text('67')", timeout=30000)
                break  # avançou para a seleção de telefone
            except PlaywrightTimeoutError:
                if tentativa_cnpj >= MAX_TENTATIVAS_CNPJ:
                    raise  # esgotou as tentativas → cai no retry completo de login
                print(f"⚠️ Portal voltou para a tela de CPF/CNPJ. Reenviando "
                      f"dados (tentativa {tentativa_cnpj + 1}/{MAX_TENTATIVAS_CNPJ})...")
                _pausa(1)

        page.get_by_role("button", name="ícone de um celular azul 67*****2038").click()

        # Aguardar código SMS
        codigo = obter_codigo_email_com_reenvio_automatico(page, 600)

        if not codigo:
            raise Exception("Não foi possível obter o código de verificação")

        # Separar o código em 4 dígitos
        input1 = codigo[0] if len(codigo) > 0 else ""
        print(f"Input 1 bloco: {input1}")
        input2 = codigo[1] if len(codigo) > 1 else ""
        print(f"Input 2 bloco: {input2}")
        input3 = codigo[2] if len(codigo) > 2 else ""
        print(f"Input 3 bloco: {input3}")
        input4 = codigo[3] if len(codigo) > 3 else ""
        print(f"Input 4 bloco: {input4}")

        # Preencher os campos com o código
        page.wait_for_selector("input[type='text']", state="visible", timeout=10000)

        for _campo, _valor in [
            ("Dígito 1 do código", input1),
            ("Dígito 2 do código", input2),
            ("Dígito 3 do código", input3),
            ("Dígito 4 do código", input4),
        ]:
            page.get_by_role("textbox", name=_campo).click()
            page.get_by_role("textbox", name=_campo).fill(_valor)
            _pausa(0.4)  # hesitação humana entre os dígitos

        time.sleep(10)

        print("✅ Login feito com sucesso!")
        return browser, context, page

    except Exception as e:
        # Em caso de erro, fechar o navegador antes de propagar a exceção
        print(f"❌ Erro durante login: {str(e)}")
        if browser:
            try:
                browser.close()
                print("🔒 Navegador fechado devido ao erro")
            except:
                pass
        raise  # Re-lançar a exceção para ser tratada pelo retry

def fazer_login_com_retry(p, geradora_cnpj):
    """Wrapper que tenta fazer login infinitamente com intervalo de MINUTOS_ENTRE_TENTATIVAS entre falhas

    Args:
        p: Playwright instance
        geradora_cnpj: CNPJ da geradora

    Returns:
        browser, context, page (sempre retorna valores válidos, nunca None)
    """
    tentativa = 0

    while True:
        tentativa += 1
        print(f"\n{'='*80}")
        print(f"🔐 TENTATIVA DE LOGIN #{tentativa}")
        print(f"🕐 Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"{'='*80}\n")

        try:
            browser, context, page = fazer_login(p, geradora_cnpj)

            if browser and context and page:
                print("✅ Login realizado com sucesso!")
                return browser, context, page
            else:
                raise Exception("Login retornou valores None")

        except Exception as e:
            print(f"\n❌ FALHA NO LOGIN (tentativa {tentativa})")
            print(f"📝 Erro: {str(e)}")

            # Fechar browser se foi aberto
            try:
                if 'browser' in locals() and browser:
                    browser.close()
                    print("🔒 Browser fechado")
            except:
                pass

            # Aguardar antes da próxima tentativa
            tempo_espera = MINUTOS_ENTRE_TENTATIVAS * 60
            proxima_tentativa = datetime.now() + timedelta(seconds=tempo_espera)

            print(f"\n⏳ Aguardando {MINUTOS_ENTRE_TENTATIVAS} minutos antes da próxima tentativa...")
            print(f"🕐 Próxima tentativa às: {proxima_tentativa.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"{'='*80}\n")

            # Countdown com atualização a cada minuto
            for minutos_restantes in range(MINUTOS_ENTRE_TENTATIVAS, 0, -1):
                print(f"⏰ {minutos_restantes} minuto(s) restante(s)...")
                time.sleep(60)

            print("\n🔄 Reiniciando tentativa de login...\n")

def carregar_json_geradora(geradora_cnpj):
    """Carrega o JSON correspondente à geradora usando apenas os números do CNPJ"""
    # Extrair apenas os números do CNPJ
    cnpj_numerico = ''.join(filter(str.isdigit, geradora_cnpj))

    # Caminho do arquivo JSON
    caminho_json = f"media/json/{cnpj_numerico}.json"

    if not os.path.exists(caminho_json):
        print(f"❌ Arquivo JSON não encontrado: {caminho_json}")
        return None

    try:
        with open(caminho_json, 'r', encoding='utf-8') as file:
            dados = json.load(file)
            print(f"✅ JSON carregado: {caminho_json}")
            return dados
    except Exception as e:
        print(f"❌ Erro ao carregar JSON {caminho_json}: {str(e)}")
        return None

def processar_geradora(geradora_cnpj, force=False, apenas_ucs=None, reprocessar_tudo=False):
    """Processa uma geradora específica usando seu CNPJ

    Args:
        geradora_cnpj (str): CNPJ da geradora
        force (bool): Se True, reprocessa faturas com erro
        apenas_ucs (list[str] | None): Se informado, processa somente essas
            nova_uc (mesmo fluxo de login/seleção/download). Usado por
            scripts/testar_uc.py para testar uma UC isolada.
        reprocessar_tudo (bool): Se True, ignora a janela diária e refaz TODAS as faturas
            que a API trouxer, inclusive as já baixadas com sucesso hoje.
    """
    print(f"Processando geradora com CNPJ: {geradora_cnpj}")
    if reprocessar_tudo:
        print("♻️ Modo RERRODADA ativado - TODAS as faturas do dia serão refeitas (inclusive as com sucesso)")
    elif force:
        print("⚠️ Modo FORCE ativado - faturas com erro serão reprocessadas")
    # "is not None" de propósito: uma lista vazia significa "nenhuma UC", e
    # não "sem restrição" (evita processar a geradora inteira por engano).
    if apenas_ucs is not None:
        apenas_ucs = set(apenas_ucs)
        print(f"🎯 Processamento restrito às UCs: {', '.join(sorted(apenas_ucs))}")

    # 1. Criar JSON filtrado apenas com faturas a_verificar (ou com erro se force=True)
    from function.buscar_dados_api import criar_json_filtrado_por_status

    dados_geradora = criar_json_filtrado_por_status(
        geradora_cnpj, force=force, reprocessar_tudo=reprocessar_tudo
    )

    if not dados_geradora:
        print(f"✅ Nenhuma fatura pendente para processar na geradora {geradora_cnpj}")
        return True

    # 2. Extrair lista de UCs filtradas
    lista_ucs = dados_geradora.get("lista_ucs", {})

    if apenas_ucs is not None:
        lista_ucs = {uc: f for uc, f in lista_ucs.items() if uc in apenas_ucs}
        if not lista_ucs:
            print(f"✅ Nenhuma fatura pendente para as UCs {sorted(apenas_ucs)} na geradora {geradora_cnpj}")
            return True

    total_ucs = len(lista_ucs)
    total_faturas = sum(len(f) for f in lista_ucs.values())

    print(f"📋 UCs a processar: {total_ucs}")
    print(f"📊 Faturas a processar: {total_faturas}")

    # 3. Iniciar processo de login e navegação
    with sync_playwright() as p:
        # Fazer login inicial com retry automático
        browser, context, page = fazer_login_com_retry(p, geradora_cnpj)

        if not browser or not page:
            print("❌ Falha no login inicial")
            return False

        # 4. Processar cada UC com sistema de retry e renovação de login a cada 30 UCs
        ucs_processadas = 0
        total_ucs = len(lista_ucs)
        lista_ucs_items = list(lista_ucs.items())  # Converter para lista para controle de índice

        # Controle de "sucesso falso de login": índices das UCs cuja busca não
        # retornou correspondência em sequência. 1 isolada = UC mal cadastrada
        # (marca e pula); 2+ seguidas = login deu falso positivo (relogin + reprocessa).
        indices_sem_correspondencia = []
        relogins_sucesso_falso = 0
        MAX_RELOGINS_SUCESSO_FALSO = 2  # após isso, trata as UCs como mal cadastradas

        i = 0  # Índice atual da UC
        while i < len(lista_ucs_items):
            nova_uc, faturas_uc = lista_ucs_items[i]
            ucs_processadas = i + 1
            print(f"\n🔄 Processando UC {ucs_processadas}/{total_ucs}: {nova_uc}")
            print(f"📊 Faturas para processar: {len(faturas_uc)}")

            if i > 0:
                _pausa_entre_ucs()

            # Verificar se precisa renovar login a cada 50 UCs
            if ucs_processadas > 1 and (ucs_processadas - 1) % 50 == 0:
                print(f"\n🔄 50 UCs processadas! Renovando login...")
                try:
                    browser.close()
                    print("✅ Navegador fechado")
                except:
                    pass

                time.sleep(3)
                print("🔐 Fazendo novo login com retry automático...")
                browser, context, page = fazer_login_com_retry(p, geradora_cnpj)

                print("✅ Login renovado com sucesso! Continuando processamento...")

            max_tentativas_uc = 3  # Máximo de tentativas para cada UC
            tentativa_uc = 0
            uc_processada_com_sucesso = False
            avancar_indice = True  # controla o avanço do índice ao fim da iteração

            while tentativa_uc < max_tentativas_uc and not uc_processada_com_sucesso:
                tentativa_uc += 1
                if tentativa_uc > 1:
                    print(f"🔄 Tentativa {tentativa_uc}/{max_tentativas_uc} para UC {nova_uc}")

                try:
                    # Verificar se há bloqueio "Access Denied" antes de processar
                    # Esta função agora para a execução automaticamente se detectar bloqueio
                    print("🔍 Verificando bloqueio de acesso...")
                    verificar_access_denied(page)

                    # Navegar para seleção de UC com retry robusto
                    tentativas_navegacao = 0
                    max_tentativas_navegacao = 3
                    uc_selecionada = False

                    while tentativas_navegacao < max_tentativas_navegacao and not uc_selecionada:
                        try:
                            tentativas_navegacao += 1
                            print(f"   🔄 Tentativa {tentativas_navegacao} de seleção da UC...")

                            # Verificar novamente se há bloqueio antes de navegar
                            # Esta função agora para a execução automaticamente se detectar bloqueio
                            verificar_access_denied(page)

                            # Navegar para listagem
                            page.goto("https://servicos.energisa.com.br/login/listagem-ucs", wait_until="load", timeout=30000)

                            # Aguardar página carregar completamente
                            page.wait_for_load_state("domcontentloaded")
                            _pausa(2)  # Aguardar scripts JS carregarem (com jitter)

                            # Aguardar input de busca estar disponível
                            input_busca = page.get_by_role("textbox", name="Busque pelo número da UC ou")
                            input_busca.wait_for(state="visible", timeout=15000)
                            input_busca.wait_for(state="attached", timeout=5000)

                            # Garantir que o campo está pronto para interação
                            _pausa(1)

                            # Clicar e preencher com a UC
                            input_busca.click(timeout=10000)
                            input_busca.fill("")  # Limpar primeiro
                            _pausa(0.5)

                            # Preencher com a UC
                            _digitar(input_busca, nova_uc)
                            _pausa(2)  # aguardar a busca responder (resultado ou aviso)

                            # Localizar e clicar no card da UC. Trata as seções
                            # "Ativos"/"Inativos" da listagem e só considera o aviso
                            # de "sem correspondência" (UC mal cadastrada OU login com
                            # sucesso falso; 1 isolada = UC errada, 2 seguidas = login
                            # falso) quando não existe card da UC na página.
                            selecionar_card_uc(page, nova_uc)
                            _pausa(1)

                            uc_selecionada = True
                            print(f"   ✅ UC selecionada com sucesso")

                        except SemCorrespondenciaError:
                            # Não adianta repetir a busca: a UC não apareceu.
                            # Deixar subir para a lógica da UC decidir (UC errada x login falso).
                            raise

                        except Exception as e:
                            print(f"   ⚠️ Tentativa {tentativas_navegacao} falhou: {str(e)}")

                            if tentativas_navegacao >= max_tentativas_navegacao:
                                raise Exception(f"Falha ao selecionar UC {nova_uc} após {max_tentativas_navegacao} tentativas")

                            # Aguardar antes de tentar novamente (backoff progressivo)
                            tempo_espera = tentativas_navegacao * 2
                            print(f"   ⏳ Aguardando {tempo_espera}s antes de tentar novamente...")
                            time.sleep(tempo_espera)

                    # Aguardar navegação com validação rigorosa
                    navegacao_sucesso = False
                    tentativas_validacao = 0
                    max_tentativas_validacao = 3

                    while tentativas_validacao < max_tentativas_validacao and not navegacao_sucesso:
                        tentativas_validacao += 1

                        try:
                            # Aguardar mudança de URL
                            page.wait_for_url("**/login/login**", timeout=15000)
                            navegacao_sucesso = True
                            print(f"   ✅ Navegação bem-sucedida para UC {nova_uc}")

                        except:
                            # Verificar URL atual
                            current_url = page.url
                            print(f"   🔍 URL atual: {current_url}")

                            # Verificar se é Access Denied. A função lança
                            # AccessDeniedError, tratado abaixo com espera
                            # longa, novo login e nova tentativa da UC.
                            verificar_access_denied(page)

                            # Se ainda está na listagem, a troca falhou
                            if "listagem-ucs" in current_url:
                                print(f"   ⚠️ Ainda na página de listagem (tentativa {tentativas_validacao})")

                                if tentativas_validacao >= max_tentativas_validacao:
                                    raise Exception(f"Falha ao sair da listagem após {max_tentativas_validacao} tentativas")

                                # Aguardar um pouco mais
                                time.sleep(3)

                            # Se saiu da listagem mas não chegou no /login/login
                            elif "/login" in current_url or "/home" in current_url or "/faturas" in current_url:
                                navegacao_sucesso = True
                                print(f"   ✅ Navegação OK - URL válida: {current_url}")

                            else:
                                # URL inesperada
                                if tentativas_validacao >= max_tentativas_validacao:
                                    raise Exception(f"URL inesperada após seleção: {current_url}")

                                print(f"   ⚠️ URL inesperada, aguardando...")
                                time.sleep(3)

                    if not navegacao_sucesso:
                        raise Exception(f"Navegação falhou para UC {nova_uc}")

                    # Ir para página de faturas com retry
                    tentativas_faturas = 0
                    max_tentativas_faturas = 3
                    faturas_carregadas = False

                    while tentativas_faturas < max_tentativas_faturas and not faturas_carregadas:
                        try:
                            tentativas_faturas += 1
                            print(f"   📄 Carregando página de faturas (tentativa {tentativas_faturas})...")

                            page.goto("https://servicos.energisa.com.br/faturas", wait_until="load", timeout=30000)
                            page.wait_for_load_state("domcontentloaded")

                            # Aguardar conteúdo carregar
                            _pausa(3)

                            faturas_carregadas = True
                            print(f"   ✅ Página de faturas carregada")

                        except Exception as e:
                            print(f"   ⚠️ Tentativa {tentativas_faturas} falhou ao carregar faturas: {str(e)}")

                            if tentativas_faturas >= max_tentativas_faturas:
                                raise Exception(f"Falha ao carregar página de faturas após {max_tentativas_faturas} tentativas")

                            time.sleep(2)

                    # Verifica se é UC sem faturas
                    if page.locator('text=Bem-vindo à esta nova conta com a Energisa.').count() > 0:
                        print("UC sem faturas geradas no momento.")

                        # Registrar no banco que a UC foi verificada mas não tem faturas
                        from database import DatabaseManager
                        from datetime import datetime
                        db = DatabaseManager()

                        # Registrar execução da UC sem faturas
                        db.registrar_execucao_uc(
                            cnpj_geradora=geradora_cnpj,
                            nova_uc=nova_uc,
                            total_faturas=len(faturas_uc),
                            faturas_sucesso=0,
                            faturas_erro=0,
                            faturas_puladas=len(faturas_uc),
                            data_hora_inicio=datetime.now()
                        )

                        # Marcar todas as faturas desta UC como sucesso (não há nada para processar)
                        for fatura in faturas_uc:
                            fatura_id = fatura.get("id")
                            db.atualizar_status_fatura(
                                fatura_id=fatura_id,
                                status='sucesso',
                                mensagem_erro='UC sem faturas no portal',
                                tipo_operacao='nao_encontrada',
                                log_execucao=f"UC {nova_uc} sem faturas geradas no portal Energisa"
                            )
                            print(f"   ✅ Fatura ID {fatura_id} marcada como sucesso (UC sem faturas)")

                        uc_processada_com_sucesso = True  # Marcar como sucesso para prosseguir
                        break

                    # Espera os cards renderizarem antes de contá-los (o clique
                    # incondicional em "Mostrar mais faturas" fazia esse papel).
                    try:
                        page.locator('.card-billing__date').first.wait_for(state="visible", timeout=15000)
                    except PlaywrightTimeoutError:
                        print("   ⚠️ Nenhum card de fatura visível após 15s - seguindo mesmo assim")

                    # O portal removeu o botão "Mostrar mais faturas" em 28/08/2026
                    # (ele só revelava o 13º card). Só clica se ele existir; a
                    # checagem é instantânea para não custar 5s por UC.
                    botao_mostrar_mais = page.locator("div").filter(
                        has_text=re.compile(r"^Mostrar mais faturas$")
                    ).first
                    if botao_mostrar_mais.count() > 0:
                        try:
                            botao_mostrar_mais.click(timeout=10000)
                            print("   ✅ Botão 'Mostrar mais faturas' clicado")
                        except Exception as e:
                            print(f"   ⚠️ Botão 'Mostrar mais faturas' existe mas o clique falhou: {str(e).splitlines()[0]}")
                    else:
                        print("   ℹ️ Botão 'Mostrar mais faturas' ausente - seguindo com as faturas visíveis")

                    # Processar faturas desta UC usando a função do tarefa.py
                    print(f"🎯 Iniciando processamento das faturas da UC {nova_uc}")

                    # Criar estrutura temporária para processar apenas esta UC
                    dados_uc_temp = {
                        "geradora": geradora_cnpj,
                        "lista_ucs": {nova_uc: faturas_uc}
                    }

                    # Processar faturas da UC atual com parâmetro force
                    resultados_uc = processar_faturas_do_json(
                        dados_uc_temp, page, force=force, reprocessar_tudo=reprocessar_tudo
                    )

                    # Log dos resultados
                    sucessos_uc = sum(1 for r in resultados_uc if r["sucesso"])
                    print(f"✅ UC {nova_uc} processada: {sucessos_uc}/{len(resultados_uc)} faturas com sucesso")

                    uc_processada_com_sucesso = True  # Marcar como sucesso

                except AccessDeniedError as e:
                    # Access Denied detectado: em vez de parar tudo, aguardar
                    # a espera longa, refazer o login e tentar a MESMA UC novamente.
                    print(f"🛑 Acesso negado ao processar UC {nova_uc}: {str(e)}")

                    # Fechar o navegador atual (a sessão foi derrubada)
                    try:
                        browser.close()
                        print("🔒 Navegador fechado após acesso negado")
                    except:
                        pass

                    # Aguardar antes de uma nova tentativa
                    aguardar_antes_de_retentar(motivo="Acesso negado")

                    # Refazer login (com retry automático entre falhas)
                    print("🔐 Refazendo login após acesso negado...")
                    browser, context, page = fazer_login_com_retry(p, geradora_cnpj)

                    # Não contar como tentativa da UC: repetir a mesma UC
                    tentativa_uc -= 1
                    continue

                except SemCorrespondenciaError:
                    # Busca não retornou a UC. Pode ser:
                    #  - UC mal cadastrada (login OK): ocorrência isolada → marca e pula;
                    #  - login com sucesso falso: 2+ UCs seguidas sem correspondência.
                    print(f"⚠️ UC {nova_uc}: 'Não encontramos nenhuma correspondência para a sua busca'.")
                    if i not in indices_sem_correspondencia:
                        indices_sem_correspondencia.append(i)

                    # Com a lista restrita a 1 UC (scripts/testar_uc.py) não existe
                    # UC seguinte para confirmar: trata a ocorrência como possível
                    # sucesso falso e refaz o login antes de marcar como mal cadastrada.
                    # O robô diário (apenas_ucs=None) mantém a regra das 2 UCs seguidas.
                    minimo_para_relogin = 1 if (apenas_ucs is not None and len(lista_ucs_items) == 1) else 2
                    if len(indices_sem_correspondencia) >= minimo_para_relogin:
                        if relogins_sucesso_falso >= MAX_RELOGINS_SUCESSO_FALSO:
                            # Já refez login e as mesmas UCs seguem sem correspondência:
                            # são realmente mal cadastradas. Marcar todas e seguir adiante.
                            print(f"⚠️ Após {relogins_sucesso_falso} relogin(s) as UCs seguem sem correspondência. Tratando como mal cadastradas.")
                            for idx in indices_sem_correspondencia:
                                uc_errada, faturas_erradas = lista_ucs_items[idx]
                                marcar_uc_nao_encontrada(geradora_cnpj, uc_errada, faturas_erradas)
                            i = indices_sem_correspondencia[-1] + 1
                            indices_sem_correspondencia = []
                            relogins_sucesso_falso = 0
                            avancar_indice = False
                            break

                        # Duas UCs consecutivas sem correspondência → login com sucesso falso.
                        if minimo_para_relogin == 1:
                            print("🚫 Única UC da lista sem correspondência → possível login com sucesso falso. Refazendo login antes de marcar.")
                        else:
                            print("🚫 Duas UCs consecutivas sem correspondência → login com sucesso falso detectado.")
                        try:
                            browser.close()
                            print("🔒 Navegador fechado após sucesso falso de login")
                        except:
                            pass

                        aguardar_antes_de_retentar(motivo="Login com sucesso falso (UCs não carregaram)")
                        print("🔐 Refazendo login após sucesso falso...")
                        browser, context, page = fazer_login_com_retry(p, geradora_cnpj)
                        relogins_sucesso_falso += 1

                        # Reprocessar desde a primeira UC afetada (eram válidas)
                        i = indices_sem_correspondencia[0]
                        indices_sem_correspondencia = []
                        avancar_indice = False
                        break

                    # Primeira ocorrência: pode ser UC mal cadastrada. Ir para a
                    # próxima UC pendente para confirmar (se a próxima carregar,
                    # esta era realmente errada e será marcada como tal).
                    print("➡️ Indo para a próxima UC pendente para confirmar (UC errada × login falso)...")
                    avancar_indice = True
                    break

                except Exception as e:
                    print(f"❌ Erro ao processar UC {nova_uc} (tentativa {tentativa_uc}): {str(e)}")

                    # Esgotou as tentativas rápidas. Em vez de pular a UC,
                    # aguardar a espera longa, refazer o login e tentar a MESMA
                    # UC novamente (infinitamente), pois normalmente é um erro
                    # transitório de carregamento/sessão.
                    if tentativa_uc >= max_tentativas_uc:
                        print(f"⚠️ UC {nova_uc} falhou após {max_tentativas_uc} tentativas rápidas (não carregou/não prosseguiu).")

                        # Fechar o navegador atual (sessão pode ter caído / página travada)
                        try:
                            browser.close()
                            print("🔒 Navegador fechado após falhas de carregamento")
                        except:
                            pass

                        # Aguardar antes de uma nova rodada
                        aguardar_antes_de_retentar(motivo=f"Falha ao carregar/processar a UC {nova_uc}")

                        # Refazer login (com retry automático entre falhas)
                        print("🔐 Refazendo login após falhas de carregamento...")
                        browser, context, page = fazer_login_com_retry(p, geradora_cnpj)

                        # Reiniciar o ciclo de tentativas rápidas para a MESMA UC
                        tentativa_uc = 0
                        continue

                    # Ainda há tentativas rápidas: aguardar um pouco antes da próxima
                    time.sleep(3)

            # UC processada com sucesso: se havia UCs anteriores sem correspondência,
            # o login está OK e elas eram realmente mal cadastradas → registrar.
            if uc_processada_com_sucesso:
                relogins_sucesso_falso = 0  # login saudável, zera a proteção
                if indices_sem_correspondencia:
                    for idx in indices_sem_correspondencia:
                        uc_errada, faturas_erradas = lista_ucs_items[idx]
                        print(f"❌ UC {uc_errada} confirmada como mal cadastrada (sem correspondência, login OK). Registrando e pulando.")
                        marcar_uc_nao_encontrada(geradora_cnpj, uc_errada, faturas_erradas)
                    indices_sem_correspondencia = []

            # Avançar para a próxima UC, exceto quando o índice já foi ajustado
            # (reprocessamento após sucesso falso de login ou marcação em lote).
            if avancar_indice:
                i += 1

        # Registrar eventuais UCs sem correspondência ainda não confirmadas
        # (ex.: a última UC da lista deu o aviso e não houve UC seguinte).
        if indices_sem_correspondencia:
            for idx in indices_sem_correspondencia:
                uc_errada, faturas_erradas = lista_ucs_items[idx]
                print(f"❌ UC {uc_errada} sem correspondência (não confirmada por UC seguinte). Registrando como não encontrada.")
                marcar_uc_nao_encontrada(geradora_cnpj, uc_errada, faturas_erradas)
            indices_sem_correspondencia = []

        print(f"\n🎉 Processamento da geradora {geradora_cnpj} concluído!")
        print(f"📈 Total de UCs processadas: {total_ucs}/{total_ucs}")

        browser.close()
        return True


def processar_multiplas_geradoras(cnpjs_lista, force=False):
    """Processa uma lista específica de geradoras pelos CNPJs

    Args:
        cnpjs_lista (list): Lista de CNPJs para processar
        force (bool): Se True, reprocessa faturas com erro
    """
    print(f"🚀 Iniciando processamento de {len(cnpjs_lista)} geradoras específicas")
    if force:
        print("⚠️ Modo FORCE ativado - faturas com erro serão reprocessadas")

    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()

    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False

    sucessos = 0
    falhas = 0

    for i, geradora_cnpj in enumerate(cnpjs_lista, 1):
        print(f"\n🔄 Processando geradora {i}/{len(cnpjs_lista)}: {geradora_cnpj}")
        try:
            resultado = processar_geradora(geradora_cnpj, force=force)
            if resultado:
                sucessos += 1
                print(f"✅ SUCESSO: Geradora {geradora_cnpj} processada com sucesso")
            else:
                falhas += 1
                print(f"❌ FALHA: Erro ao processar geradora {geradora_cnpj}")
        except Exception as e:
            falhas += 1
            print(f"❌ ERRO: Erro ao processar geradora {geradora_cnpj}: {str(e)}")

        # Pausa entre processamentos para evitar sobrecarga
        if i < len(cnpjs_lista):
            print("⏳ Aguardando 5 segundos antes do próximo processamento...")
            time.sleep(5)

    print(f"\n📊 Processamento das geradoras selecionadas concluído!")
    print(f"✅ Sucessos: {sucessos}")
    print(f"❌ Falhas: {falhas}")
    print(f"📈 Taxa de sucesso: {(sucessos/(sucessos+falhas)*100):.1f}%")

    return sucessos > 0

def processar_todas_geradoras(force=False, reprocessar_tudo=False):
    """Processa todas as geradoras da lista

    Args:
        force (bool): Se True, reprocessa faturas com erro
        reprocessar_tudo (bool): Se True, ignora a janela diária e refaz TODAS as faturas
            da API, inclusive as já baixadas com sucesso hoje
    """
    print(f"🚀 Iniciando processamento de {len(geradoras_cnpjs)} geradoras")
    if reprocessar_tudo:
        print("♻️ Modo RERRODADA ativado - TODAS as faturas do dia serão refeitas (inclusive as com sucesso)")
    elif force:
        print("⚠️ Modo FORCE ativado - faturas com erro serão reprocessadas")

    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()

    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False

    sucessos = 0
    falhas = 0

    for i, geradora_cnpj in enumerate(geradoras_cnpjs, 1):
        print(f"\n🔄 Processando geradora {i}/{len(geradoras_cnpjs)}: {geradora_cnpj}")
        try:
            resultado = processar_geradora(
                geradora_cnpj, force=force, reprocessar_tudo=reprocessar_tudo
            )
            if resultado:
                sucessos += 1
                print(f"✅ SUCESSO: Geradora {geradora_cnpj} processada com sucesso")
            else:
                falhas += 1
                print(f"❌ FALHA: Erro ao processar geradora {geradora_cnpj}")
        except Exception as e:
            falhas += 1
            print(f"❌ ERRO: Erro ao processar geradora {geradora_cnpj}: {str(e)}")

        # Pausa entre processamentos para evitar sobrecarga
        if i < len(geradoras_cnpjs):
            print("⏳ Aguardando 5 segundos antes do próximo processamento...")
            time.sleep(5)

    print(f"\n📊 Processamento de todas as geradoras concluído!")
    print(f"✅ Sucessos: {sucessos}")
    print(f"❌ Falhas: {falhas}")
    print(f"📈 Taxa de sucesso: {(sucessos/(sucessos+falhas)*100):.1f}%")

    return sucessos > 0

def processar_geradora_especifica(geradora_cnpj, force=False):
    """Processa uma única geradora específica

    Args:
        geradora_cnpj (str): CNPJ da geradora
        force (bool): Se True, reprocessa faturas com erro
    """
    print(f"🎯 Processamento específico da geradora: {geradora_cnpj}")
    if force:
        print("⚠️ Modo FORCE ativado - faturas com erro serão reprocessadas")

    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()

    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False

    try:
        resultado = processar_geradora(geradora_cnpj, force=force)
        if resultado:
            print(f"✅ SUCESSO: Geradora {geradora_cnpj} processada com sucesso")
            return True
        else:
            print(f"❌ FALHA: Erro ao processar geradora {geradora_cnpj}")
            return False
    except Exception as e:
        print(f"❌ ERRO: Erro ao processar geradora {geradora_cnpj}: {str(e)}")
        return False

if __name__ == "__main__":
    # Verificar se foi passado o parâmetro --force / --reprocessar-tudo
    import sys
    force_mode = '--force' in sys.argv
    # --reprocessar-tudo é superconjunto de --force: refaz até o que deu sucesso hoje
    reprocessar_tudo_mode = '--reprocessar-tudo' in sys.argv

    # Inicializar banco de dados
    print("💾 Inicializando banco de dados...")
    inicializar_banco()

    # Iniciar sistema de logging
    log_duplo = iniciar_log()

    try:
        # Processar todas as geradoras em loop
        print("🚀 Iniciando processamento de todas as geradoras...")
        processar_todas_geradoras(force=force_mode, reprocessar_tudo=reprocessar_tudo_mode)

        # # Para processar geradoras específicas:
        # processar_usinas = [
        #     USINA_SULINA_CNPJ
        # ]
        # print(f"🚀 Iniciando processamento das usinas {processar_usinas}...")
        # processar_multiplas_geradoras(processar_usinas, force=force_mode)

        print("=" * 80)
        print(f"✅ Execução finalizada com sucesso!")
        print(f"🕐 Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    except Exception as e:
        print("=" * 80)
        print(f"❌ Erro durante execução: {str(e)}")
        print(f"🕐 Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    finally:
        # Fechar arquivo de log
        log_duplo.close()
        sys.stdout = log_duplo.terminal
