from playwright.sync_api import sync_playwright
import time
import sys
import os
import re
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

from function.codigo_sms import obter_codigo_email_com_reenvio_automatico
from function.buscar_dados_api import buscar_faturas, extrair_numero_fatura
from config import DEBUG_MODE
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

# Carregar variáveis de ambiente
load_dotenv()

# Verificar modo de debug
debug_mode = DEBUG_MODE
print(f"🔧 Modo de execução: {'DESENVOLVIMENTO (DEV)' if debug_mode else 'PRODUÇÃO (PROD)'}")

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
    nome_arquivo = f"aneel_{agora.strftime('%d%m%Y-%H%M%S')}.txt"
    caminho_log = os.path.join('logs', nome_arquivo)
    
    # Redirecionar stdout para o sistema de log duplo
    log_duplo = LogDuplo(caminho_log)
    sys.stdout = log_duplo
    
    print(f"📝 Log iniciado: {caminho_log}")
    print(f"🕐 Data/Hora: {agora.strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 80)
    
    return log_duplo

class AccessDeniedError(Exception):
    """Sinaliza bloqueio 'Access Denied'. Em vez de encerrar o robô, é
    tratado no laço de coleta aguardando 15 minutos e refazendo o login.
    """
    pass


class SemCorrespondenciaError(Exception):
    """Sinaliza que a busca da UC retornou "Não encontramos nenhuma
    correspondência para a sua busca".

    Pode indicar UC mal cadastrada (login OK) ou login com sucesso falso.
    A distinção é feita no laço de coleta das UCs.
    """
    pass


def verificar_access_denied(page):
    """Verifica se a página contém bloqueio 'Access Denied'

    Raises:
        AccessDeniedError: Se Access Denied for detectado (tratado com espera
            de 15 minutos e novo login, sem parar o robô).
    """
    try:
        if page.locator('text=Access Denied').count() > 0:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied'")
            raise AccessDeniedError("Access Denied detectado")

        titulo = page.title().lower()
        if 'access denied' in titulo or 'acesso negado' in titulo:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied' no título da página")
            raise AccessDeniedError("Access Denied detectado no título")

        current_url = page.url
        if '/logout' in current_url:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied' - URL de logout")
            raise AccessDeniedError("Access Denied detectado (logout)")

        return False
    except AccessDeniedError:
        raise
    except Exception as e:
        print(f"⚠️ Erro ao verificar Access Denied: {str(e)}")
        return False


def aguardar_antes_de_retentar(minutos=15, motivo="Erro detectado"):
    """Aguarda (com contagem regressiva) antes de uma nova tentativa."""
    proxima_tentativa = datetime.now() + timedelta(minutes=minutos)
    print(f"\n{'='*80}")
    print(f"⏳ {motivo}: aguardando {minutos} minutos antes de tentar novamente...")
    print(f"🕐 Próxima tentativa às: {proxima_tentativa.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*80}\n")

    for minutos_restantes in range(minutos, 0, -1):
        print(f"⏰ {minutos_restantes} minuto(s) restante(s)...")
        time.sleep(60)

    print("\n🔄 Retomando processamento após espera...\n")


def verificar_sem_correspondencia(page):
    """Retorna True se a busca da UC mostrar o aviso de "sem correspondência"."""
    try:
        aviso = page.get_by_text("Não encontramos nenhuma correspondência", exact=False)
        return aviso.count() > 0 and aviso.first.is_visible()
    except Exception:
        return False

def fazer_login(p, geradora_cnpj):
    """Realiza o processo de login e retorna browser, context e page"""
    print("🔐 Iniciando processo de Login")
    
    browser = None
    context = None
    page = None
    
    try:
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
        time.sleep(5)
        
        page.screenshot(path="debug_login.png")
        print("📸 Screenshot salvo: debug_login.png")
        
        print("✏️ Preenchendo CNPJ...")
        page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").click()
        page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").fill(geradora_cnpj)
        page.get_by_role("button", name="Entrar").click()
        
        page.wait_for_selector("button:has-text('67')", timeout=30000)
        page.get_by_role("button", name="ícone de um celular azul 67*****2038").click()
        
        codigo = obter_codigo_email_com_reenvio_automatico(page, 600)
        
        if not codigo:
            raise Exception("Não foi possível obter o código de verificação")
        
        input1 = codigo[0] if len(codigo) > 0 else ""
        input2 = codigo[1] if len(codigo) > 1 else ""
        input3 = codigo[2] if len(codigo) > 2 else ""
        input4 = codigo[3] if len(codigo) > 3 else ""
        
        page.wait_for_selector("input[type='text']", state="visible", timeout=10000)
        
        page.get_by_role("textbox", name="Dígito 1 do código").click()
        page.get_by_role("textbox", name="Dígito 1 do código").fill(input1)
        page.get_by_role("textbox", name="Dígito 2 do código").click()
        page.get_by_role("textbox", name="Dígito 2 do código").fill(input2)
        page.get_by_role("textbox", name="Dígito 3 do código").click()
        page.get_by_role("textbox", name="Dígito 3 do código").fill(input3)
        page.get_by_role("textbox", name="Dígito 4 do código").click()
        page.get_by_role("textbox", name="Dígito 4 do código").fill(input4)

        time.sleep(10)
        
        print("✅ Login feito com sucesso!")
        return browser, context, page
        
    except Exception as e:
        print(f"❌ Erro durante login: {str(e)}")
        if browser:
            try:
                browser.close()
                print("🔒 Navegador fechado devido ao erro")
            except:
                pass
        raise

def fazer_login_com_retry(p, geradora_cnpj):
    """Wrapper que tenta fazer login infinitamente com intervalo de 30 minutos entre falhas"""
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
            
            try:
                if 'browser' in locals() and browser:
                    browser.close()
                    print("🔒 Browser fechado")
            except:
                pass
            
            tempo_espera = 30 * 60
            proxima_tentativa = datetime.now() + timedelta(seconds=tempo_espera)
            
            print(f"\n⏳ Aguardando 30 minutos antes da próxima tentativa...")
            print(f"🕐 Próxima tentativa às: {proxima_tentativa.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"{'='*80}\n")
            
            for minutos_restantes in range(30, 0, -1):
                print(f"⏰ {minutos_restantes} minuto(s) restante(s)...")
                time.sleep(60)
            
            print("\n🔄 Reiniciando tentativa de login...\n")

def enviar_webhook_codigo_aneel(nova_uc, numero_da_uc):
    """Envia o código ANEEL via webhook para a API"""
    api_key = os.getenv('GEUS_APIKEY')
    
    # Escolher URL baseado no modo DEBUG
    if debug_mode:
        api_domain_faturas = os.getenv('API_DOMAIN_FATURAS_DEV', 'http://127.0.0.1:8000/api/faturas/')
        print(f"🔧 Usando API de DESENVOLVIMENTO")
    else:
        api_domain_faturas = os.getenv('API_DOMAIN_FATURAS_PROD', 'https://geus.energiaa.com.br/api/faturas/')
        print(f"🚀 Usando API de PRODUÇÃO")
    
    if not api_key:
        print("❌ ERRO: Token GEUS_APIKEY não encontrado no arquivo .env")
        return False
    
    # Extrair a URL base (remover /faturas/ do final)
    # Ex: https://geus.energiaa.com.br/api/faturas/ -> https://geus.energiaa.com.br/api/
    api_base = api_domain_faturas.replace('/faturas/', '/').rstrip('/')
    
    # Construir URL do endpoint (rota correta: api/atualizar_numero_uc/)
    url = f"{api_base}/atualizar_numero_uc/"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "nova_uc": nova_uc,
        "numero_da_uc": numero_da_uc
    }
    
    try:
        print(f"📤 Enviando webhook para: {url}")
        print(f"📦 Dados: nova_uc={nova_uc}, numero_da_uc={numero_da_uc}")
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        if response.status_code in [200, 201]:
            print(f"✅ Webhook enviado com sucesso!")
            try:
                print(f"📥 Resposta: {response.json()}")
            except:
                print(f"📥 Resposta (texto): {response.text}")
            return True
        else:
            print(f"❌ Erro ao enviar webhook: Status {response.status_code}")
            print(f"📥 Resposta: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"⏱️ Timeout ao enviar webhook (30s)")
        return False
    except Exception as e:
        print(f"❌ Erro ao enviar webhook: {str(e)}")
        return False

def carregar_ucs_disponiveis_da_api(geradora_cnpj):
    """Carrega as UCs disponíveis da API para uma geradora específica"""
    def extrair_numeros_cnpj(cnpj):
        return ''.join(filter(str.isdigit, cnpj))
    
    nome_arquivo_numerico = extrair_numeros_cnpj(geradora_cnpj)
    caminho_arquivo = f"media/json/{nome_arquivo_numerico}.json"
    
    if not os.path.exists(caminho_arquivo):
        print(f"⚠️ Arquivo JSON não encontrado: {caminho_arquivo}")
        return set()
    
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as file:
            dados = json.load(file)
            
        ucs_disponiveis = set(dados.get("lista_ucs", {}).keys())
        print(f"📋 UCs disponíveis na API para {geradora_cnpj}: {len(ucs_disponiveis)}")
        
        return ucs_disponiveis
        
    except Exception as e:
        print(f"❌ Erro ao carregar JSON: {str(e)}")
        return set()

def coletar_codigos_aneel_geradora(geradora_cnpj):
    """Coleta todos os códigos ANEEL de uma geradora específica"""
    print(f"\n{'='*80}")
    print(f"🔍 Iniciando coleta de códigos ANEEL para geradora: {geradora_cnpj}")
    print(f"{'='*80}\n")
    
    print("📡 Carregando UCs disponíveis da API...")
    ucs_disponiveis = carregar_ucs_disponiveis_da_api(geradora_cnpj)
    
    if not ucs_disponiveis:
        print("⚠️ Nenhuma UC disponível na API para esta geradora")
        return False
    
    print(f"✅ {len(ucs_disponiveis)} UCs encontradas na API")
    print(f"📝 UCs: {', '.join(sorted(ucs_disponiveis))}")
    print()
    
    with sync_playwright() as p:
        browser, context, page = fazer_login_com_retry(p, geradora_cnpj)
        
        if not browser or not page:
            print("❌ Falha no login inicial")
            return False
        
        try:
            print("✅ Login concluído com sucesso!")
            print("🔄 Iniciando loop de coleta de códigos ANEEL...")
            
            print("🌐 Navegando para listagem de UCs...")
            page.goto("https://servicos.energisa.com.br/login/listagem-ucs", wait_until="load", timeout=60000)
            time.sleep(3)
            
            verificar_access_denied(page)
            
            ucs_processadas = 0
            ucs_enviadas = 0
            ucs_erro = 0
            ucs_nao_encontradas = 0
            
            # Converter para lista ordenada para processar sequencialmente
            lista_ucs = sorted(ucs_disponiveis)
            total_ucs = len(lista_ucs)
            
            print(f"\n📊 Total de UCs da API para processar: {total_ucs}")
            
            # Controle de "sucesso falso de login": índices das UCs cuja busca
            # não retornou correspondência em sequência. 1 isolada = UC mal
            # cadastrada (conta e segue); 2+ seguidas = login deu falso positivo
            # (espera 15 min, refaz login e reprocessa).
            indices_sem_correspondencia = []
            relogins_sucesso_falso = 0
            MAX_RELOGINS_SUCESSO_FALSO = 2

            # Processar cada UC da API usando o campo de busca
            i = 0
            while i < len(lista_ucs):
                nova_uc_numero = lista_ucs[i]
                avancar_indice = True
                uc_encontrada = False
                try:
                    print(f"\n{'─'*80}")
                    print(f"🔄 Processando UC {i+1}/{total_ucs}: {nova_uc_numero}")
                    
                    # Verificar se há bloqueio
                    verificar_access_denied(page)
                    
                    # Aguardar input de busca estar disponível
                    print("🔍 Localizando campo de busca...")
                    input_busca = page.get_by_role("textbox", name="Busque pelo número da UC ou")
                    input_busca.wait_for(state="visible", timeout=15000)
                    input_busca.wait_for(state="attached", timeout=5000)
                    
                    # Garantir que o campo está pronto para interação
                    time.sleep(1)
                    
                    # Clicar e limpar o campo primeiro
                    print(f"✏️ Preenchendo campo de busca com: {nova_uc_numero}")
                    input_busca.click(timeout=10000)
                    input_busca.fill("")  # Limpar primeiro
                    time.sleep(0.5)
                    
                    # Preencher com a UC
                    input_busca.fill(nova_uc_numero)
                    time.sleep(2)  # Aguardar resultados da busca
                    
                    # Verificar se existe botão de "Inativos" e clicar se necessário
                    try:
                        botao_inativos = page.get_by_role("button", name=re.compile(r"Inativos", re.IGNORECASE))
                        if botao_inativos.is_visible(timeout=2000):
                            print(f"   ℹ️ Encontrado botão de Inativos, clicando...")
                            botao_inativos.click()
                            time.sleep(1)
                    except:
                        # Se não encontrar o botão de inativos, continua normalmente
                        pass
                    
                    # Localizar o botão da UC nos resultados da busca
                    print("🔍 Buscando UC nos resultados...")
                    botoes_uc = page.locator("button").filter(has_text="Código do Cliente:")
                    
                    # Aguardar um pouco para os resultados carregarem
                    time.sleep(1)
                    
                    total_botoes = botoes_uc.count()
                    
                    # Busca SEM correspondência: pode ser UC mal cadastrada OU
                    # login com sucesso falso. A distinção é feita nos excepts
                    # (1 isolada = UC errada; 2 seguidas = login falso).
                    if verificar_sem_correspondencia(page) or total_botoes == 0:
                        raise SemCorrespondenciaError(nova_uc_numero)

                    uc_encontrada = True  # login OK e a UC apareceu na listagem
                    
                    # Pegar o primeiro resultado (deve ser o único após a busca)
                    botao_atual = botoes_uc.first
                    
                    # Extrair informações do botão SEM clicar
                    texto_botao = botao_atual.inner_text()
                    print(f"📄 Texto do botão:\n{texto_botao}")
                    
                    # Extrair o código do cliente completo
                    match_codigo = re.search(r'Código do Cliente:\s*([0-9/\-]+)', texto_botao, re.IGNORECASE)
                    
                    if not match_codigo:
                        match_codigo = re.search(r'UC\s+([0-9/\-]+)', texto_botao, re.IGNORECASE)
                    
                    if not match_codigo:
                        # Sem código extraível: trata como erro (best-effort) no except
                        raise Exception("Não foi possível extrair o código do cliente do botão")
                    
                    nova_uc_completa = match_codigo.group(1).strip()
                    print(f"🔑 Código do Cliente (completo): {nova_uc_completa}")
                    
                    # Extrair o "NOVO NÚMERO DA UC" ou "Número da UC" (código ANEEL)
                    match_numero = re.search(r'NOVO NÚMERO DA UC:\s*([0-9.\-]+)', texto_botao, re.IGNORECASE)
                    
                    if not match_numero:
                        # Tentar formato alternativo
                        match_numero = re.search(r'Número da UC:\s*([0-9.\-]+)', texto_botao, re.IGNORECASE)
                    
                    if match_numero:
                        numero_da_uc = match_numero.group(1).strip()
                        print(f"🎯 Número da UC (código ANEEL): {numero_da_uc}")
                        
                        # Validar formato do número da UC
                        digitos = re.sub(r'\D', '', numero_da_uc)
                        if len(digitos) >= 9 and len(digitos) <= 15:
                            # Enviar webhook usando o código completo
                            print(f"📤 Enviando webhook...")
                            sucesso = enviar_webhook_codigo_aneel(nova_uc_completa, numero_da_uc)
                            
                            if sucesso:
                                ucs_enviadas += 1
                                print(f"✅ UC processada e enviada com sucesso!")
                            else:
                                ucs_erro += 1
                                print(f"❌ Erro ao enviar webhook")
                        else:
                            print(f"⚠️ Número da UC inválido (deve ter 9-15 dígitos): {numero_da_uc}")
                            ucs_erro += 1
                    else:
                        print("⚠️ Nenhum formato de número da UC encontrado no botão")
                        ucs_nao_encontradas += 1
                    
                except AccessDeniedError as e:
                    # Acesso negado: em vez de parar tudo, aguardar 15 min,
                    # refazer login e repetir a MESMA UC.
                    print(f"🛑 Acesso negado ao processar UC {nova_uc_numero}: {str(e)}")
                    try:
                        browser.close()
                        print("🔒 Navegador fechado após acesso negado")
                    except:
                        pass
                    aguardar_antes_de_retentar(15, "Acesso negado")
                    print("🔐 Refazendo login após acesso negado...")
                    browser, context, page = fazer_login_com_retry(p, geradora_cnpj)
                    try:
                        page.goto("https://servicos.energisa.com.br/login/listagem-ucs", wait_until="load", timeout=60000)
                        time.sleep(3)
                    except:
                        pass
                    avancar_indice = False  # repetir a mesma UC

                except SemCorrespondenciaError:
                    print(f"⚠️ UC {nova_uc_numero}: 'Não encontramos nenhuma correspondência para a sua busca'.")
                    if i not in indices_sem_correspondencia:
                        indices_sem_correspondencia.append(i)

                    if len(indices_sem_correspondencia) >= 2:
                        if relogins_sucesso_falso >= MAX_RELOGINS_SUCESSO_FALSO:
                            # Já refez login e as mesmas UCs seguem sem correspondência:
                            # são realmente mal cadastradas. Contabilizar e seguir.
                            print(f"⚠️ Após {relogins_sucesso_falso} relogin(s) as UCs seguem sem correspondência. Tratando como não encontradas.")
                            for idx in indices_sem_correspondencia:
                                print(f"❌ UC {lista_ucs[idx]} não encontrada na listagem (provável cadastro errado).")
                                ucs_nao_encontradas += 1
                            i = indices_sem_correspondencia[-1] + 1
                            indices_sem_correspondencia = []
                            relogins_sucesso_falso = 0
                            avancar_indice = False
                        else:
                            # Duas UCs consecutivas sem correspondência → login falso.
                            print("🚫 Duas UCs consecutivas sem correspondência → login com sucesso falso detectado.")
                            try:
                                browser.close()
                                print("🔒 Navegador fechado após sucesso falso de login")
                            except:
                                pass
                            aguardar_antes_de_retentar(15, "Login com sucesso falso (UCs não carregaram)")
                            print("🔐 Refazendo login após sucesso falso...")
                            browser, context, page = fazer_login_com_retry(p, geradora_cnpj)
                            relogins_sucesso_falso += 1
                            try:
                                page.goto("https://servicos.energisa.com.br/login/listagem-ucs", wait_until="load", timeout=60000)
                                time.sleep(3)
                            except:
                                pass
                            # Reprocessar desde a primeira UC afetada (eram válidas)
                            i = indices_sem_correspondencia[0]
                            indices_sem_correspondencia = []
                            avancar_indice = False
                    else:
                        # Primeira ocorrência: pode ser UC mal cadastrada. Ir para a
                        # próxima UC para confirmar (se a próxima for encontrada,
                        # esta era realmente errada e será contabilizada).
                        print("➡️ Indo para a próxima UC para confirmar (UC errada × login falso)...")
                        avancar_indice = True

                except Exception as e:
                    print(f"❌ Erro ao processar UC {nova_uc_numero}: {str(e)}")
                    ucs_erro += 1
                    
                    # Tentar recarregar a página em caso de erro
                    try:
                        print("🔄 Tentando recarregar a página de listagem...")
                        page.goto("https://servicos.energisa.com.br/login/listagem-ucs", wait_until="load", timeout=60000)
                        time.sleep(2)
                    except:
                        print("❌ Erro ao recarregar página")

                # Se esta UC foi encontrada (login OK) e havia UCs anteriores sem
                # correspondência, elas eram mal cadastradas → contabilizar.
                if uc_encontrada and indices_sem_correspondencia:
                    relogins_sucesso_falso = 0
                    for idx in indices_sem_correspondencia:
                        print(f"❌ UC {lista_ucs[idx]} não encontrada na listagem (login OK; provável cadastro errado).")
                        ucs_nao_encontradas += 1
                    indices_sem_correspondencia = []

                # Avançar para a próxima UC, exceto quando o índice já foi ajustado
                # (reprocessamento após sucesso falso de login ou marcação em lote).
                if avancar_indice:
                    i += 1

            # Registrar eventuais UCs sem correspondência ainda não confirmadas
            # (ex.: a última UC da lista deu o aviso e não houve UC seguinte).
            if indices_sem_correspondencia:
                for idx in indices_sem_correspondencia:
                    print(f"❌ UC {lista_ucs[idx]} sem correspondência (não confirmada por UC seguinte).")
                    ucs_nao_encontradas += 1
                indices_sem_correspondencia = []

            ucs_processadas = ucs_enviadas + ucs_erro + ucs_nao_encontradas

            print(f"\n{'='*80}")
            print(f"🎉 Coleta de códigos ANEEL concluída!")
            print(f"📊 Estatísticas finais:")
            print(f"   - Total de UCs da API: {total_ucs}")
            print(f"   - Processadas: {ucs_processadas}")
            print(f"   - Enviadas com sucesso: {ucs_enviadas}")
            print(f"   - Não encontradas na listagem: {ucs_nao_encontradas}")
            print(f"   - Erros: {ucs_erro}")
            if ucs_processadas > 0:
                print(f"   - Taxa de sucesso: {(ucs_enviadas/ucs_processadas*100):.1f}%")
            print(f"{'='*80}\n")
            
        except SystemExit:
            print("🛑 Execução interrompida por Access Denied")
            raise
            
        except Exception as e:
            print(f"❌ Erro durante coleta: {str(e)}")
            
        finally:
            try:
                browser.close()
                print("🔒 Navegador fechado")
            except:
                pass

def coletar_todas_geradoras():
    """Coleta códigos ANEEL de todas as geradoras"""
    print(f"\n{'='*80}")
    print(f"🚀 Iniciando coleta de códigos ANEEL para {len(geradoras_cnpjs)} geradoras")
    print(f"{'='*80}\n")
    
    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()
    
    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False
    
    sucessos = 0
    falhas = 0
    
    for i, geradora_cnpj in enumerate(geradoras_cnpjs, 1):
        print(f"\n{'='*80}")
        print(f"🔄 Processando geradora {i}/{len(geradoras_cnpjs)}: {geradora_cnpj}")
        print(f"{'='*80}\n")
        
        try:
            coletar_codigos_aneel_geradora(geradora_cnpj)
            sucessos += 1
            print(f"✅ SUCESSO: Geradora {geradora_cnpj} processada com sucesso")
        except SystemExit:
            print("🛑 Execução interrompida por Access Denied")
            break
        except Exception as e:
            falhas += 1
            print(f"❌ ERRO: Erro ao processar geradora {geradora_cnpj}: {str(e)}")
        
        if i < len(geradoras_cnpjs):
            print("⏳ Aguardando 5 segundos antes do próximo processamento...")
            time.sleep(5)
    
    print(f"\n{'='*80}")
    print(f"📊 Coleta de todas as geradoras concluída!")
    print(f"✅ Sucessos: {sucessos}")
    print(f"❌ Falhas: {falhas}")
    if sucessos + falhas > 0:
        print(f"📈 Taxa de sucesso: {(sucessos/(sucessos+falhas)*100):.1f}%")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    load_dotenv()
    
    api_key = os.getenv('GEUS_APIKEY')
    if not api_key:
        print("❌ ERRO CRÍTICO: Token GEUS_APIKEY não encontrado no arquivo .env")
        print("📝 Verifique se o arquivo .env existe e contém a linha:")
        print("   GEUS_APIKEY=seu-token-aqui")
        sys.exit(1)
    else:
        print(f"✅ Token GEUS_APIKEY carregado: {api_key[:20]}...{api_key[-10:] if len(api_key) > 30 else ''}")
    
    log_duplo = iniciar_log()
    
    try:
        if len(sys.argv) > 1:
            geradora_cnpj = sys.argv[1]
            print(f"🎯 Modo específico: processando apenas geradora {geradora_cnpj}")
            
            print("📡 Buscando dados atualizados da API...")
            diretorio_json = buscar_faturas()
            
            if not diretorio_json:
                print("❌ Falha ao buscar dados da API. Abortando processamento.")
            else:
                coletar_codigos_aneel_geradora(geradora_cnpj)
        else:
            print("🚀 Modo completo: processando todas as geradoras")
            coletar_todas_geradoras()
        
        print("=" * 80)
        print(f"✅ Execução finalizada com sucesso!")
        print(f"🕐 Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        
    except SystemExit:
        print("=" * 80)
        print(f"🛑 Execução interrompida por Access Denied")
        print(f"🕐 Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        
    except Exception as e:
        print("=" * 80)
        print(f"❌ Erro durante execução: {str(e)}")
        print(f"🕐 Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    finally:
        log_duplo.close()
        sys.stdout = log_duplo.terminal
