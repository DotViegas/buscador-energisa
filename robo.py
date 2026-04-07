from playwright.sync_api import sync_playwright
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

# Lista com todos os CNPJs das geradoras
geradoras_cnpjs = [
    USINA_LUNA_CNPJ,
    USINA_SULINA_CNPJ,
    USINA_LB_CNPJ,
    USINA_ENERGIAA_CNPJ,
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
    """Verifica se a página contém bloqueio 'Access Denied'
    
    Returns:
        bool: True se detectou Access Denied, False caso contrário
    
    Raises:
        SystemExit: Interrompe a execução do robô se Access Denied for detectado
    """
    try:
        # Verificar se existe texto "Access Denied" na página
        if page.locator('text=Access Denied').count() > 0:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied'")
            print("🛑 PARANDO EXECUÇÃO DO ROBÔ CONFORME CONFIGURADO")
            raise SystemExit("Execução interrompida: Access Denied detectado")
        
        # Verificar também no título da página
        titulo = page.title().lower()
        if 'access denied' in titulo or 'acesso negado' in titulo:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied' no título da página")
            print("🛑 PARANDO EXECUÇÃO DO ROBÔ CONFORME CONFIGURADO")
            raise SystemExit("Execução interrompida: Access Denied detectado no título")
        
        # Verificar se a URL atual é de logout (indicativo de Access Denied)
        current_url = page.url
        if '/logout' in current_url:
            print("🚫 BLOQUEIO DETECTADO: 'Access Denied' - URL de logout")
            print("🛑 PARANDO EXECUÇÃO DO ROBÔ CONFORME CONFIGURADO")
            raise SystemExit("Execução interrompida: Access Denied detectado (logout)")
            
        return False
    except SystemExit:
        # Re-lançar SystemExit para parar a execução
        raise
    except Exception as e:
        print(f"⚠️ Erro ao verificar Access Denied: {str(e)}")
        return False

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
        time.sleep(5)  # Aguardar carregamento completo e possíveis scripts
        
        # Tirar screenshot para debug
        page.screenshot(path="debug_login.png")
        print("📸 Screenshot salvo: debug_login.png")
        
        # Selecionar campo de CNPJ
        print("✏️ Preenchendo CNPJ...")
        page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").click()
        page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").fill(geradora_cnpj)
        page.get_by_role("button", name="Entrar").click()
        
        # Aguardar seleção de telefone aparecer
        page.wait_for_selector("button:has-text('67')", timeout=30000)
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
    """Wrapper que tenta fazer login infinitamente com intervalo de 15 minutos entre falhas
    
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
            
            # Aguardar 15 minutos
            tempo_espera = 15 * 60  # 15 minutos em segundos
            proxima_tentativa = datetime.now() + timedelta(seconds=tempo_espera)
            
            print(f"\n⏳ Aguardando 15 minutos antes da próxima tentativa...")
            print(f"🕐 Próxima tentativa às: {proxima_tentativa.strftime('%d/%m/%Y %H:%M:%S')}")
            print(f"{'='*80}\n")
            
            # Countdown com atualização a cada minuto
            for minutos_restantes in range(15, 0, -1):
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

def processar_geradora(geradora_cnpj, force=False):
    """Processa uma geradora específica usando seu CNPJ
    
    Args:
        geradora_cnpj (str): CNPJ da geradora
        force (bool): Se True, reprocessa faturas com erro
    """
    print(f"Processando geradora com CNPJ: {geradora_cnpj}")
    if force:
        print("⚠️ Modo FORCE ativado - faturas com erro serão reprocessadas")

    # 1. Criar JSON filtrado apenas com faturas a_verificar (ou com erro se force=True)
    from function.buscar_dados_api import criar_json_filtrado_por_status
    
    dados_geradora = criar_json_filtrado_por_status(geradora_cnpj, force=force)
    
    if not dados_geradora:
        print(f"✅ Nenhuma fatura pendente para processar na geradora {geradora_cnpj}")
        return True

    # 2. Extrair lista de UCs filtradas
    lista_ucs = dados_geradora.get("lista_ucs", {})
    
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

        i = 0  # Índice atual da UC
        while i < len(lista_ucs_items):
            nova_uc, faturas_uc = lista_ucs_items[i]
            ucs_processadas = i + 1
            print(f"\n🔄 Processando UC {ucs_processadas}/{total_ucs}: {nova_uc}")
            print(f"📊 Faturas para processar: {len(faturas_uc)}")
            
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

                    page.locator("div").filter(has_text=re.compile(r"^Mostrar mais faturas$")).click()

                    # Processar faturas desta UC usando a função do tarefa.py
                    print(f"🎯 Iniciando processamento das faturas da UC {nova_uc}")

                    # Criar estrutura temporária para processar apenas esta UC
                    dados_uc_temp = {
                        "geradora": geradora_cnpj,
                        "lista_ucs": {nova_uc: faturas_uc}
                    }

                    # Processar faturas da UC atual com parâmetro force
                    resultados_uc = processar_faturas_do_json(dados_uc_temp, page, force=force)

                    # Log dos resultados
                    sucessos_uc = sum(1 for r in resultados_uc if r["sucesso"])
                    print(f"✅ UC {nova_uc} processada: {sucessos_uc}/{len(resultados_uc)} faturas com sucesso")

                    uc_processada_com_sucesso = True  # Marcar como sucesso

                except SystemExit:
                    # Access Denied detectado - propagar exceção para parar tudo
                    print("🛑 Propagando interrupção por Access Denied...")
                    raise
                    
                except Exception as e:
                    print(f"❌ Erro ao processar UC {nova_uc} (tentativa {tentativa_uc}): {str(e)}")
                    
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

def processar_todas_geradoras(force=False):
    """Processa todas as geradoras da lista
    
    Args:
        force (bool): Se True, reprocessa faturas com erro
    """
    print(f"🚀 Iniciando processamento de {len(geradoras_cnpjs)} geradoras")
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
    
    for i, geradora_cnpj in enumerate(geradoras_cnpjs, 1):
        print(f"\n🔄 Processando geradora {i}/{len(geradoras_cnpjs)}: {geradora_cnpj}")
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
    # Verificar se foi passado o parâmetro --force
    import sys
    force_mode = '--force' in sys.argv
    
    # Inicializar banco de dados
    print("💾 Inicializando banco de dados...")
    inicializar_banco()
    
    # Iniciar sistema de logging
    log_duplo = iniciar_log()
    
    try:
        # Processar todas as geradoras em loop
        print("🚀 Iniciando processamento de todas as geradoras...")
        processar_todas_geradoras(force=force_mode)
        
        # # Para processar geradoras específicas:
        # processar_usinas = [
        #     USINA_ENERGIAA_CNPJ
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
