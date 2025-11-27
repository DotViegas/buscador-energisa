from playwright.sync_api import sync_playwright
import time
import re

from function.codigo_sms import obter_codigo_email, obter_codigo_email_com_reenvio_automatico
from geradoras import (
    USINA_LUNA_CNPJ,
    USINA_SULINA_CNPJ,
    USINA_LB_CNPJ,
    USINA_ENERGIAA_CNPJ,
    USINA_LUZDIVINA_CNPJ,
    USINA_G114_CNPJ
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
    USINA_G114_CNPJ
]

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
        print("🔐 Iniciando a etapa de Login")

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
        
        for seletor in seletores:
            try:
                print(f"   Tentando seletor: {seletor}")
                cnpj_input = page.locator(seletor).first
                cnpj_input.wait_for(state="visible", timeout=5000)
                print(f"   ✅ Encontrado com: {seletor}")
                break
            except:
                continue
        
        if not cnpj_input:
            print("❌ Nenhum campo de input encontrado!")
            page.screenshot(path="debug_sem_input.png")
            print("📸 Screenshot salvo: debug_sem_input.png")
            print("🔍 HTML da página:")
            print(page.content()[:1000])  # Primeiros 1000 caracteres
            browser.close()
            return False
        
        print("✏️ Preenchendo CNPJ...")
        cnpj_input.click()
        cnpj_input.fill(geradora_cnpj)
        page.get_by_role("button", name="ENTRAR").click()
        
        # Aguardar seleção de telefone aparecer
        page.wait_for_selector("div:has-text('67')", timeout=30000)
        page.locator("div").filter(has_text=re.compile(r"^67\*\*\*\*\*2038$")).click()
        page.get_by_role("button", name="AVANÇAR").click()
        
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
            page.wait_for_selector("input[name='input1']", state="visible", timeout=10000)
            
            page.locator("input[name=\"input1\"]").fill(input1)
            page.locator("input[name=\"input2\"]").fill(input2)
            page.locator("input[name=\"input3\"]").fill(input3)
            page.locator("input[name=\"input4\"]").fill(input4)
            page.get_by_role("button", name="AVANÇAR").click()

            time.sleep(10)

        else:
            print("❌ ERRO: Não foi possível obter o código de verificação")
            browser.close()
            return False

        print("✅ Login feito com sucesso!")
        
        # 4. Processar cada UC
        ucs_processadas = 0
        total_ucs = len(lista_ucs)
        
        for nova_uc, faturas_uc in lista_ucs.items():
            ucs_processadas += 1
            print(f"\n🔄 Processando UC {ucs_processadas}/{total_ucs}: {nova_uc}")
            print(f"📊 Faturas para processar: {len(faturas_uc)}")
            
            try:
                # Navegar para seleção de UC com retry
                tentativas = 0
                max_tentativas = 3
                
                while tentativas < max_tentativas:
                    try:
                        page.goto("https://servicos.energisa.com.br/login/listagem-ucs", wait_until="load", timeout=30000)
                        page.wait_for_selector("[data-testid='input-nome']", state="visible", timeout=15000)
                        break
                    except Exception as e:
                        tentativas += 1
                        if tentativas >= max_tentativas:
                            raise e
                        print(f"   ⚠️ Tentativa {tentativas} falhou, tentando novamente...")
                
                page.get_by_test_id("input-nome").click()
                page.get_by_test_id("input-nome").fill(nova_uc)
                page.get_by_role("main").locator("span").click()
                page.get_by_role("button", name="AVANÇAR").click()
                
                # Aguardar navegação com validação rigorosa
                navegacao_sucesso = False
                try:
                    page.wait_for_url("**/login/login**", timeout=30000)
                    navegacao_sucesso = True
                except:
                    # Se timeout, verificar se realmente saiu da listagem
                    current_url = page.url
                    
                    # Se ainda está na listagem, a troca de UC falhou
                    if "listagem-ucs" in current_url:
                        print(f"   ❌ ERRO: Troca de UC falhou - ainda na página de listagem")
                        print(f"   🔄 Tentando novamente a seleção da UC {nova_uc}...")
                        
                        # Tentar novamente
                        page.get_by_test_id("input-nome").click()
                        page.get_by_test_id("input-nome").clear()
                        page.get_by_test_id("input-nome").fill(nova_uc)
                        page.get_by_role("main").locator("span").click()
                        page.get_by_role("button", name="AVANÇAR").click()
                        
                        # Aguardar novamente
                        try:
                            page.wait_for_url("**/login/login**", timeout=30000)
                            navegacao_sucesso = True
                            print(f"   ✅ Troca de UC bem-sucedida na segunda tentativa")
                        except:
                            current_url = page.url
                            if "listagem-ucs" not in current_url:
                                navegacao_sucesso = True
                                print(f"   ⚠️ Timeout mas saiu da listagem: {current_url}")
                            else:
                                raise Exception(f"Falha ao trocar para UC {nova_uc} após 2 tentativas")
                    
                    # Se saiu da listagem mas não chegou no /login/login, pode estar ok
                    elif "/login" in current_url or "/home" in current_url or "/faturas" in current_url:
                        navegacao_sucesso = True
                        print(f"   ⚠️ Timeout na navegação, mas URL atual parece válida: {current_url}")
                    else:
                        raise
                
                if not navegacao_sucesso:
                    raise Exception(f"Navegação falhou para UC {nova_uc}")
                
                # Ir para página de faturas com retry
                tentativas = 0
                while tentativas < max_tentativas:
                    try:
                        page.goto("https://servicos.energisa.com.br/faturas", wait_until="load", timeout=30000)
                        page.wait_for_load_state("domcontentloaded")
                        break
                    except Exception as e:
                        tentativas += 1
                        if tentativas >= max_tentativas:
                            raise e
                        print(f"   ⚠️ Tentativa {tentativas} falhou ao carregar faturas, tentando novamente...")

                # Verifica se é UC sem faturas
                if page.locator('text=Bem-vindo à esta nova conta com a Energisa.').count() > 0:
                    print("UC sem faturas geradas no momento.")
                    continue

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
                
            except Exception as e:
                print(f"❌ Erro ao processar UC {nova_uc}: {str(e)}")
                continue
        
        print(f"\n🎉 Processamento da geradora {geradora_cnpj} concluído!")
        print(f"📈 Total de UCs processadas: {ucs_processadas}/{total_ucs}")
        
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
    # Processar todas as geradoras em loop
    print("🚀 Iniciando processamento de todas as geradoras...")
    processar_todas_geradoras()
    
    # Para processar geradoras específicas:
    #processar_usinas = [
    #    USINA_SULINA_CNPJ
    #]
    #print(f"🚀 Iniciando processamento das usinas {processar_usinas}...")
    #processar_multiplas_geradoras(processar_usinas)
