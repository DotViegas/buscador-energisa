from playwright.sync_api import sync_playwright
import time
import re
import sys
from datetime import datetime

from function.codigo_sms import obter_codigo_email, obter_codigo_email_com_reenvio_automatico
from geradoras import (
    USINA_LUNA_CNPJ,
    USINA_SULINA_CNPJ,
    USINA_LB_CNPJ,
    USINA_ENERGIAA_CNPJ,
    USINA_LUZDIVINA_CNPJ,
    USINA_G114_CNPJ,
    USINA_SLLG
)
from function.tarefa import executar_fatura_pendente, executar_fatura_vencida, processar_faturas_do_json
from function.buscar_dados_api import buscar_faturas
import json
import os

# Lista com todos os CNPJs das geradoras
geradoras_cnpjs = [
    USINA_LUNA_CNPJ,
    USINA_SULINA_CNPJ,
    USINA_LB_CNPJ,
    USINA_ENERGIAA_CNPJ,
    USINA_LUZDIVINA_CNPJ,
    USINA_G114_CNPJ,
    USINA_SLLG
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
    nome_arquivo = agora.strftime("%d%m%Y-%H%M%S.txt")
    caminho_log = os.path.join('logs', nome_arquivo)
    
    # Redirecionar stdout para o sistema de log duplo
    log_duplo = LogDuplo(caminho_log)
    sys.stdout = log_duplo
    
    print(f"📝 Log iniciado: {caminho_log}")
    print(f"🕐 Data/Hora: {agora.strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 80)
    
    return log_duplo

def verificar_access_denied(page):
    """Verifica se a página contém bloqueio 'Access Denied'"""
    try:
        # Verificar se existe texto "Access Denied" na página
        if page.locator('text=Access Denied').count() > 0:
            print("🚫 Detectado bloqueio 'Access Denied'")
            return True
        
        # Verificar também no título da página
        titulo = page.title().lower()
        if 'access denied' in titulo or 'acesso negado' in titulo:
            print("🚫 Detectado bloqueio no título da página")
            return True
        
        # Verificar se a URL atual é de logout (indicativo de Access Denied)
        current_url = page.url
        if '/logout' in current_url:
            print("🚫 Detectado bloqueio 'Access Denied' - URL de logout")
            return True
            
        return False
    except Exception as e:
        print(f"⚠️ Erro ao verificar Access Denied: {str(e)}")
        return False

def fazer_login(p, geradora_cnpj):
    """Realiza o processo de login e retorna browser, context e page"""
    print("🔐 Iniciando processo de Login")
    
    # Tentar Firefox primeiro (menos detectado)
    try:
        print("🦊 Tentando com Firefox...")
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                'dom.webdriver.enabled': False,
                'useAutomationExtension': False,
                'general.useragent.override': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0'
            }
        )
    except:
        print("⚠️ Firefox não disponível, usando Chromium...")
        browser = p.chromium.launch(
            headless=True,
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
        viewport={'width': 1920, 'height': 1080},
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
    try:
        page.goto("https://servicos.energisa.com.br/login", wait_until="load", timeout=60000)
        time.sleep(5)  # Aguardar carregamento completo e possíveis scripts
        
        # Tirar screenshot para debug
        page.screenshot(path="debug_login.png")
        print("📸 Screenshot salvo: debug_login.png")
        
    except Exception as e:
        print(f"⚠️ Erro ao carregar página: {e}")
        page.screenshot(path="debug_erro.png")
        print("📸 Screenshot de erro salvo: debug_erro.png")
    
    # Tentar múltiplos seletores para o campo de CNPJ
    print("🔍 Procurando campo de CNPJ...")
    cnpj_input = None
    
    # Lista de seletores para tentar
    seletores = [
        "input[placeholder*='CPF']",
        "input[placeholder*='CNPJ']", 
        "input[type='text']",
        "input[type='tel']",
        "input.input",
        "input",
        "[role='textbox']"
    ]
    
    cnpj_input = None
    tentativas_reload = 0
    max_tentativas = 3
    
    # Sistema de retry caso não encontre os seletores (página não carregou)
    while tentativas_reload < max_tentativas:
        tentativas_reload += 1
        print(f"🔄 Tentativa {tentativas_reload}/{max_tentativas} para encontrar campo de CNPJ...")
        
        for seletor in seletores:
            try:
                print(f"   Tentando seletor: {seletor}")
                cnpj_input = page.locator(seletor).first
                cnpj_input.wait_for(state="visible", timeout=5000)
                print(f"   ✅ Encontrado com: {seletor}")
                break
            except:
                continue
        
        # Se encontrou, sair do loop
        if cnpj_input:
            break
        
        # Se não encontrou e ainda tem tentativas, recarregar
        if tentativas_reload < max_tentativas:
            print(f"⚠️ Página não carregou corretamente. Recarregando...")
            page.reload(wait_until="networkidle")
            time.sleep(3)
    
    if not cnpj_input:
        print(f"❌ Nenhum campo de input encontrado após {max_tentativas} tentativas!")
        page.screenshot(path="debug_sem_input.png")
        print("📸 Screenshot salvo: debug_sem_input.png")
        print("🔍 HTML da página:")
        print(page.content()[:1000])  # Primeiros 1000 caracteres
        browser.close()
        return None, None, None
    
    print("✏️ Preenchendo CNPJ...")
    cnpj_input.click()
    cnpj_input.fill(geradora_cnpj)
    page.get_by_role("button", name="ENTRAR").click()
    
    # Aguardar seleção de telefone aparecer
    page.wait_for_selector("button:has-text('67')", timeout=30000)
    page.get_by_role("button", name="ícone de um celular azul 67*****2038").click()
    
    # Aguardar código SMS
    codigo = obter_codigo_email_com_reenvio_automatico(page, 600)
    
    if codigo:
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
        
        page.get_by_role("textbox", name="Dígito 1 do código").click()
        page.get_by_role("textbox", name="Dígito 1 do código").fill(input1)
        page.get_by_role("textbox", name="Dígito 2 do código").click()
        page.get_by_role("textbox", name="Dígito 2 do código").fill(input2)
        page.get_by_role("textbox", name="Dígito 3 do código").click()
        page.get_by_role("textbox", name="Dígito 3 do código").fill(input3)
        page.get_by_role("textbox", name="Dígito 4 do código").click()
        page.get_by_role("textbox", name="Dígito 4 do código").fill(input4)

        time.sleep(10)
    else:
        print("❌ ERRO: Não foi possível obter o código de verificação")
        browser.close()
        return None, None, None

    print("✅ Login feito com sucesso!")
    return browser, context, page

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

def processar_geradora(geradora_cnpj):
    """Processa uma geradora específica usando seu CNPJ"""
    print(f"Processando geradora com CNPJ: {geradora_cnpj}")

    # 1. Carregar dados do JSON da geradora
    dados_geradora = carregar_json_geradora(geradora_cnpj)
    if not dados_geradora:
        print(f"❌ Não foi possível carregar dados da geradora {geradora_cnpj}")
        return False

    # 2. Extrair lista de UCs e suas tarefas
    lista_ucs = dados_geradora.get("lista_ucs", {})
    if not lista_ucs:
        print(f"❌ Nenhuma UC encontrada para a geradora {geradora_cnpj}")
        return False

    print(f"📋 Encontradas {len(lista_ucs)} UCs para processar")

    # 3. Iniciar processo de login e navegação
    with sync_playwright() as p:
        # Fazer login inicial
        browser, context, page = fazer_login(p, geradora_cnpj)

        if not browser or not page:
            print("❌ Falha no login inicial")
            return False

        # 4. Processar cada UC com sistema de retry
        ucs_processadas = 0
        total_ucs = len(lista_ucs)
        lista_ucs_items = list(lista_ucs.items())  # Converter para lista para controle de índice

        i = 0  # Índice atual da UC
        while i < len(lista_ucs_items):
            nova_uc, faturas_uc = lista_ucs_items[i]
            ucs_processadas = i + 1
            print(f"\n🔄 Processando UC {ucs_processadas}/{total_ucs}: {nova_uc}")
            print(f"📊 Faturas para processar: {len(faturas_uc)}")

            max_tentativas_uc = 3  # Máximo de tentativas para cada UC
            tentativa_uc = 0
            uc_processada_com_sucesso = False

            while tentativa_uc < max_tentativas_uc and not uc_processada_com_sucesso:
                tentativa_uc += 1
                if tentativa_uc > 1:
                    print(f"🔄 Tentativa {tentativa_uc}/{max_tentativas_uc} para UC {nova_uc}")

                try:
                    # Verificar se há bloqueio "Access Denied" antes de processar
                    print("🔍 Verificando bloqueio de acesso...")
                    if verificar_access_denied(page):
                        print("🔄 Detectado bloqueio! Reiniciando sessão...")

                        # Fechar navegador atual
                        try:
                            browser.close()
                            print("✅ Navegador fechado")
                        except:
                            pass

                        # Aguardar um pouco antes de reconectar
                        time.sleep(5)

                        # Fazer login novamente
                        print("🔐 Refazendo login...")
                        browser, context, page = fazer_login(p, geradora_cnpj)

                        if not browser or not page:
                            print("❌ Falha ao refazer login. Abortando processamento.")
                            return False

                        print("✅ Login refeito com sucesso! Continuando processamento...")

                    # Navegar para seleção de UC com retry robusto
                    tentativas_navegacao = 0
                    max_tentativas_navegacao = 3
                    uc_selecionada = False

                    while tentativas_navegacao < max_tentativas_navegacao and not uc_selecionada:
                        try:
                            tentativas_navegacao += 1
                            print(f"   🔄 Tentativa {tentativas_navegacao} de seleção da UC...")

                            # Verificar novamente se há bloqueio antes de navegar
                            if verificar_access_denied(page):
                                print("🔄 Bloqueio detectado durante navegação! Reiniciando sessão...")

                                try:
                                    browser.close()
                                except:
                                    pass

                                time.sleep(5)
                                browser, context, page = fazer_login(p, geradora_cnpj)

                                if not browser or not page:
                                    raise Exception("Falha ao refazer login durante navegação")

                                print("✅ Sessão reiniciada, continuando...")

                            # Navegar para listagem
                            page.goto("https://servicos.energisa.com.br/login/listagem-ucs", wait_until="load", timeout=30000)

                            # Aguardar página carregar completamente
                            page.wait_for_load_state("domcontentloaded")
                            time.sleep(2)  # Aguardar scripts JS carregarem

                            # Aguardar input de busca estar disponível
                            input_busca = page.get_by_role("textbox", name="Busque pelo número da UC ou")
                            input_busca.wait_for(state="visible", timeout=15000)
                            input_busca.wait_for(state="attached", timeout=5000)

                            # Garantir que o campo está pronto para interação
                            time.sleep(1)

                            # Clicar e preencher com a UC
                            input_busca.click(timeout=10000)
                            input_busca.fill("")  # Limpar primeiro
                            time.sleep(0.5)

                            # Preencher com a UC
                            input_busca.fill(nova_uc)
                            time.sleep(1)

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

                            # Clicar no botão do resultado (button dentro do container de resultados)
                            page.locator("button").filter(has_text="Código do Cliente:").first.click(timeout=10000)
                            time.sleep(1)

                            uc_selecionada = True
                            print(f"   ✅ UC selecionada com sucesso")

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
                            
                            # Verificar se é Access Denied usando a função atualizada
                            if verificar_access_denied(page):
                                # Se detectou Access Denied (incluindo URL /logout), forçar reinício da sessão
                                raise Exception(f"Access Denied detectado - URL: {current_url}")
                            
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
                            time.sleep(3)

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
                        uc_processada_com_sucesso = True  # Marcar como sucesso para prosseguir
                        break

                    page.locator("div").filter(has_text=re.compile(r"^Mostrar mais faturas$")).click()

                    # Processar faturas desta UC usando a função do tarefa.py
                    print(f"🎯 Iniciando processamento das faturas da UC {nova_uc}")

                    # Criar estrutura temporária para processar apenas esta UC
                    dados_uc_temp = {
                        "geradora": geradora_cnpj,
                        "lista_ucs": {nova_uc: faturas_uc}
                    }

                    # Processar faturas da UC atual
                    resultados_uc = processar_faturas_do_json(dados_uc_temp, page)

                    # Log dos resultados
                    sucessos_uc = sum(1 for r in resultados_uc if r["sucesso"])
                    print(f"✅ UC {nova_uc} processada: {sucessos_uc}/{len(resultados_uc)} faturas com sucesso")

                    uc_processada_com_sucesso = True  # Marcar como sucesso

                except Exception as e:
                    print(f"❌ Erro ao processar UC {nova_uc} (tentativa {tentativa_uc}): {str(e)}")

                    # Se foi erro de Access Denied, URL inesperada ou logout, tentar reiniciar sessão
                    if ("Access Denied" in str(e) or "URL inesperada" in str(e) or 
                        "logout" in str(e).lower() or "/logout" in str(e)):
                        print("🔄 Detectado problema de acesso (Access Denied), reiniciando sessão...")
                        try:
                            browser.close()
                        except:
                            pass
                        
                        time.sleep(5)
                        browser, context, page = fazer_login(p, geradora_cnpj)
                        
                        if not browser or not page:
                            print("❌ Falha ao refazer login. Tentativa será repetida.")
                            continue
                        
                        print("✅ Sessão reiniciada, tentando novamente...")
                    
                    # Se não conseguiu após todas as tentativas, pular para próxima UC
                    if tentativa_uc >= max_tentativas_uc:
                        print(f"❌ UC {nova_uc} falhou após {max_tentativas_uc} tentativas. Prosseguindo para próxima UC.")
                        break
                    
                    # Aguardar antes da próxima tentativa
                    time.sleep(3)

            # Avançar para próxima UC apenas se processou com sucesso ou esgotou tentativas
            i += 1

        print(f"\n🎉 Processamento da geradora {geradora_cnpj} concluído!")
        print(f"📈 Total de UCs processadas: {total_ucs}/{total_ucs}")

        browser.close()
        return True


def processar_multiplas_geradoras(cnpjs_lista):
    """Processa uma lista específica de geradoras pelos CNPJs"""
    print(f"🚀 Iniciando processamento de {len(cnpjs_lista)} geradoras específicas")
    
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
            resultado = processar_geradora(geradora_cnpj)
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

def processar_todas_geradoras():
    """Processa todas as geradoras da lista"""
    print(f"🚀 Iniciando processamento de {len(geradoras_cnpjs)} geradoras")
    
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
            resultado = processar_geradora(geradora_cnpj)
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

def processar_geradora_especifica(geradora_cnpj):
    """Processa uma única geradora específica"""
    print(f"🎯 Processamento específico da geradora: {geradora_cnpj}")
    
    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()
    
    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False
    
    try:
        resultado = processar_geradora(geradora_cnpj)
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
    # Iniciar sistema de logging
    log_duplo = iniciar_log()
    
    try:
        # Processar todas as geradoras em loop
        print("🚀 Iniciando processamento de todas as geradoras...")
        processar_todas_geradoras()
        
        # # Para processar geradoras específicas:
        # processar_usinas = [
        #    USINA_ENERGIAA_CNPJ,
        #    USINA_LUZDIVINA_CNPJ,
        #    USINA_G114_CNPJ
        # ]
        # print(f"🚀 Iniciando processamento das usinas {processar_usinas}...")
        # processar_multiplas_geradoras(processar_usinas)
        
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
