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

        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://servicos.energisa.com.br/login")
        page.get_by_role("textbox").click()
        page.get_by_role("textbox").fill(geradora_cnpj)
        page.get_by_role("button", name="ENTRAR").click()
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
                time.sleep(1)
                # Navegar para seleção de UC
                page.goto("https://servicos.energisa.com.br/login/listagem-ucs")
                page.get_by_test_id("input-nome").click()
                page.get_by_test_id("input-nome").fill(nova_uc)
                page.get_by_role("main").locator("span").click()
                page.get_by_role("button", name="AVANÇAR").click()
                
                page.wait_for_url("**/login/login**", timeout=10000)  # Espera chegar no /home
                
                # Ir para página de faturas
                page.goto("https://servicos.energisa.com.br/faturas")

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
    
    # Outras opções (comentadas):
    # Para processar geradoras específicas:
    # processar_multiplas_geradoras([USINA_LUNA_CNPJ, USINA_SULINA_CNPJ])
    
    # Para processar uma única geradora (útil para testes):
    # processar_geradora_especifica(USINA_LUNA_CNPJ)
