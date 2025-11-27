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

def processar_ucs(geradora_cnpj, page, lista_ucs):
    """Processa uma lista de UCs usando uma página já logada
    
    Args:
        geradora_cnpj (str): CNPJ da geradora
        page: Instância da página do Playwright já logada
        lista_ucs (dict): Dicionário com UCs e suas faturas
    
    Returns:
        dict: Dicionário com resultados do processamento por UC
    """
    resultados_por_uc = {}
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
                resultados_por_uc[nova_uc] = {
                    "sucesso": True,
                    "erro": None,
                    "faturas": []
                }
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
            
            # Armazenar resultado
            resultados_por_uc[nova_uc] = {
                "sucesso": True,
                "erro": None,
                "faturas": resultados_uc
            }
            
        except Exception as e:
            erro_msg = str(e)
            print(f"❌ Erro ao processar UC {nova_uc}: {erro_msg}")
            resultados_por_uc[nova_uc] = {
                "sucesso": False,
                "erro": erro_msg,
                "faturas": []
            }
            continue
    
    return resultados_por_uc

def processar_geradora(geradora_cnpj, ucs_especificas=None):
    """Processa uma geradora específica usando seu CNPJ
    
    Args:
        geradora_cnpj (str): CNPJ da geradora
        ucs_especificas (list): Lista de UCs específicas para reprocessar (opcional)
    
    Returns:
        dict: Dicionário com resultados do processamento por UC
    """
    print(f"Processando geradora com CNPJ: {geradora_cnpj}")
    
    # 1. Carregar dados do JSON da geradora
    dados_geradora = carregar_json_geradora(geradora_cnpj)
    if not dados_geradora:
        print(f"❌ Não foi possível carregar dados da geradora {geradora_cnpj}")
        return {}
    
    # 2. Extrair lista de UCs e suas tarefas
    lista_ucs = dados_geradora.get("lista_ucs", {})
    if not lista_ucs:
        print(f"❌ Nenhuma UC encontrada para a geradora {geradora_cnpj}")
        return {}
    
    # Se foram especificadas UCs para reprocessar, filtrar apenas essas
    if ucs_especificas:
        lista_ucs = {uc: faturas for uc, faturas in lista_ucs.items() if uc in ucs_especificas}
        print(f"📋 Reprocessando {len(lista_ucs)} UCs específicas")
    else:
        print(f"📋 Encontradas {len(lista_ucs)} UCs para processar")
    
    if not lista_ucs:
        print("❌ Nenhuma UC válida para processar")
        return {}
    
    # Dicionário para armazenar resultados por UC
    resultados_por_uc = {}
    
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
            return {}

        print("✅ Login feito com sucesso!")
        
        # 4. Processar UCs
        resultados_por_uc = processar_ucs(geradora_cnpj, page, lista_ucs)
        
        # 5. Verificar se houve falhas e oferecer reprocessamento
        ucs_com_falha = sum(1 for r in resultados_por_uc.values() if not r["sucesso"])
        
        if ucs_com_falha > 0:
            print(f"\n⚠️ {ucs_com_falha} UC(s) falharam durante o processamento")
            # Oferecer reprocessamento usando a mesma sessão
            reprocessar_ucs_com_falha_na_sessao(geradora_cnpj, page, resultados_por_uc)
        
        print(f"\n🎉 Processamento da geradora {geradora_cnpj} concluído!")
        print(f"📈 Total de UCs processadas: {len(resultados_por_uc)}/{len(lista_ucs)}")
        
        browser.close()
        return resultados_por_uc

def reprocessar_ucs_com_falha_na_sessao(geradora_cnpj, page, resultados_por_uc):
    """
    Identifica UCs com falha e permite reprocessamento seletivo usando a sessão já logada
    
    Args:
        geradora_cnpj (str): CNPJ da geradora
        page: Instância da página do Playwright já logada
        resultados_por_uc (dict): Dicionário com resultados do processamento
    
    Returns:
        bool: True se reprocessamento foi bem-sucedido
    """
    # Carregar dados do JSON da geradora
    dados_geradora = carregar_json_geradora(geradora_cnpj)
    if not dados_geradora:
        print(f"❌ Não foi possível carregar dados da geradora {geradora_cnpj}")
        return False
    
    lista_ucs_completa = dados_geradora.get("lista_ucs", {})
    
    # Separar UCs com falha
    ucs_com_falha = []
    for uc, resultado in resultados_por_uc.items():
        if not resultado["sucesso"]:
            ucs_com_falha.append({
                "uc": uc,
                "erro": resultado["erro"]
            })
    
    if not ucs_com_falha:
        print("\n✅ Todas as UCs foram processadas com sucesso! Nenhum reprocessamento necessário.")
        return True
    
    # Exibir UCs com falha
    print("\n" + "="*60)
    print(f"❌ {len(ucs_com_falha)} UC(s) falharam durante o processamento:")
    print("="*60)
    
    for i, uc_info in enumerate(ucs_com_falha, 1):
        print(f"\n{i}. UC: {uc_info['uc']}")
        print(f"   Erro: {uc_info['erro']}")
    
    print("\n" + "="*60)
    
    # Perguntar ao usuário quais reprocessar
    print("\nOpções de reprocessamento:")
    print("  - Digite os números das UCs separados por vírgula (ex: 1,3,5)")
    print("  - Digite 'todas' para reprocessar todas as UCs com falha")
    print("  - Digite 'nenhuma' ou deixe em branco para não reprocessar")
    
    escolha = input("\nSua escolha: ").strip().lower()
    
    if not escolha or escolha == "nenhuma":
        print("\n⏭️ Reprocessamento cancelado pelo usuário.")
        return False
    
    # Determinar quais UCs reprocessar
    ucs_para_reprocessar = []
    
    if escolha == "todas":
        ucs_para_reprocessar = [uc_info["uc"] for uc_info in ucs_com_falha]
        print(f"\n🔄 Reprocessando todas as {len(ucs_para_reprocessar)} UCs com falha...")
    else:
        try:
            indices = [int(x.strip()) for x in escolha.split(",")]
            for idx in indices:
                if 1 <= idx <= len(ucs_com_falha):
                    ucs_para_reprocessar.append(ucs_com_falha[idx-1]["uc"])
                else:
                    print(f"⚠️ Índice {idx} inválido, ignorando...")
            
            if not ucs_para_reprocessar:
                print("\n❌ Nenhuma UC válida selecionada.")
                return False
            
            print(f"\n🔄 Reprocessando {len(ucs_para_reprocessar)} UC(s) selecionada(s)...")
        except ValueError:
            print("\n❌ Entrada inválida. Reprocessamento cancelado.")
            return False
    
    # Exibir UCs que serão reprocessadas
    print("\nUCs que serão reprocessadas:")
    for uc in ucs_para_reprocessar:
        print(f"  - {uc}")
    
    # Confirmar reprocessamento
    confirmacao = input("\nConfirmar reprocessamento? (s/n): ").strip().lower()
    if confirmacao != 's':
        print("\n⏭️ Reprocessamento cancelado pelo usuário.")
        return False
    
    # Reprocessar UCs selecionadas usando a mesma sessão
    print("\n" + "="*60)
    print("🚀 Iniciando reprocessamento (usando sessão já logada)...")
    print("="*60 + "\n")
    
    # Filtrar apenas as UCs selecionadas
    lista_ucs_reprocessar = {uc: lista_ucs_completa[uc] for uc in ucs_para_reprocessar if uc in lista_ucs_completa}
    
    # Reprocessar usando a mesma página
    resultados_reprocessamento = processar_ucs(geradora_cnpj, page, lista_ucs_reprocessar)
    
    # Atualizar resultados originais
    for uc, resultado in resultados_reprocessamento.items():
        resultados_por_uc[uc] = resultado
    
    # Analisar resultados do reprocessamento
    sucessos = sum(1 for r in resultados_reprocessamento.values() if r["sucesso"])
    falhas = len(resultados_reprocessamento) - sucessos
    
    print("\n" + "="*60)
    print("📊 RESULTADO DO REPROCESSAMENTO")
    print("="*60)
    print(f"✅ Sucessos: {sucessos}/{len(resultados_reprocessamento)}")
    print(f"❌ Falhas: {falhas}/{len(resultados_reprocessamento)}")
    
    if falhas > 0:
        print("\n❌ UCs que ainda falharam:")
        for uc, resultado in resultados_reprocessamento.items():
            if not resultado["sucesso"]:
                print(f"  - {uc}: {resultado['erro']}")
        
        # Perguntar se deseja tentar novamente
        tentar_novamente = input("\nDeseja tentar reprocessar as UCs que falharam novamente? (s/n): ").strip().lower()
        if tentar_novamente == 's':
            return reprocessar_ucs_com_falha_na_sessao(geradora_cnpj, page, resultados_por_uc)
    else:
        print("\n🎉 Todas as UCs foram reprocessadas com sucesso!")
    
    print("="*60 + "\n")
    return sucessos > 0

def processar_multiplas_geradoras(cnpjs_lista):
    """Processa uma lista específica de geradoras pelos CNPJs com opção de reprocessamento"""
    print(f"🚀 Iniciando processamento de {len(cnpjs_lista)} geradoras específicas")
    
    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()
    
    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False
    
    resultados_geradoras = {}
    
    for i, geradora_cnpj in enumerate(cnpjs_lista, 1):
        print(f"\n🔄 Processando geradora {i}/{len(cnpjs_lista)}: {geradora_cnpj}")
        try:
            resultados = processar_geradora(geradora_cnpj)
            resultados_geradoras[geradora_cnpj] = resultados
            
            if resultados:
                ucs_com_falha = sum(1 for r in resultados.values() if not r["sucesso"])
                if ucs_com_falha == 0:
                    print(f"✅ SUCESSO: Geradora {geradora_cnpj} processada com sucesso")
            else:
                print(f"❌ FALHA: Erro ao processar geradora {geradora_cnpj}")
                
        except Exception as e:
            print(f"❌ ERRO: Erro ao processar geradora {geradora_cnpj}: {str(e)}")
            resultados_geradoras[geradora_cnpj] = {}
        
        # Pausa entre processamentos para evitar sobrecarga
        if i < len(cnpjs_lista):
            print("⏳ Aguardando 5 segundos antes do próximo processamento...")
            time.sleep(5)
    
    # Resumo geral
    print("\n" + "="*60)
    print("📊 RESUMO GERAL DO PROCESSAMENTO")
    print("="*60)
    
    total_ucs = 0
    total_sucessos = 0
    total_falhas = 0
    
    for geradora_cnpj, resultados in resultados_geradoras.items():
        if resultados:
            total_ucs += len(resultados)
            sucessos = sum(1 for r in resultados.values() if r["sucesso"])
            falhas = len(resultados) - sucessos
            total_sucessos += sucessos
            total_falhas += falhas
    
    print(f"Total de UCs processadas: {total_ucs}")
    print(f"✅ Sucessos: {total_sucessos}")
    print(f"❌ Falhas: {total_falhas}")
    if total_ucs > 0:
        print(f"📈 Taxa de sucesso: {(total_sucessos/total_ucs*100):.1f}%")
    print("="*60)
    
    return total_sucessos > 0

def processar_todas_geradoras():
    """Processa todas as geradoras da lista com opção de reprocessamento"""
    print(f"🚀 Iniciando processamento de {len(geradoras_cnpjs)} geradoras")
    
    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()
    
    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False
    
    resultados_geradoras = {}
    
    for i, geradora_cnpj in enumerate(geradoras_cnpjs, 1):
        print(f"\n🔄 Processando geradora {i}/{len(geradoras_cnpjs)}: {geradora_cnpj}")
        try:
            resultados = processar_geradora(geradora_cnpj)
            resultados_geradoras[geradora_cnpj] = resultados
            
            if resultados:
                ucs_com_falha = sum(1 for r in resultados.values() if not r["sucesso"])
                if ucs_com_falha == 0:
                    print(f"✅ SUCESSO: Geradora {geradora_cnpj} processada com sucesso")
            else:
                print(f"❌ FALHA: Erro ao processar geradora {geradora_cnpj}")
                
        except Exception as e:
            print(f"❌ ERRO: Erro ao processar geradora {geradora_cnpj}: {str(e)}")
            resultados_geradoras[geradora_cnpj] = {}
        
        # Pausa entre processamentos para evitar sobrecarga
        if i < len(geradoras_cnpjs):
            print("⏳ Aguardando 5 segundos antes do próximo processamento...")
            time.sleep(5)
    
    # Resumo geral
    print("\n" + "="*60)
    print("📊 RESUMO GERAL DO PROCESSAMENTO")
    print("="*60)
    
    total_ucs = 0
    total_sucessos = 0
    total_falhas = 0
    
    for geradora_cnpj, resultados in resultados_geradoras.items():
        if resultados:
            total_ucs += len(resultados)
            sucessos = sum(1 for r in resultados.values() if r["sucesso"])
            falhas = len(resultados) - sucessos
            total_sucessos += sucessos
            total_falhas += falhas
    
    print(f"Total de UCs processadas: {total_ucs}")
    print(f"✅ Sucessos: {total_sucessos}")
    print(f"❌ Falhas: {total_falhas}")
    if total_ucs > 0:
        print(f"📈 Taxa de sucesso: {(total_sucessos/total_ucs*100):.1f}%")
    print("="*60)
    
    return total_sucessos > 0

def processar_geradora_especifica(geradora_cnpj):
    """Processa uma única geradora específica com opção de reprocessamento"""
    print(f"🎯 Processamento específico da geradora: {geradora_cnpj}")
    
    # Primeiro, buscar dados atualizados da API
    print("📡 Buscando dados atualizados da API...")
    diretorio_json = buscar_faturas()
    
    if not diretorio_json:
        print("❌ Falha ao buscar dados da API. Abortando processamento.")
        return False
    
    try:
        resultados = processar_geradora(geradora_cnpj)
        
        if not resultados:
            print(f"❌ FALHA: Erro ao processar geradora {geradora_cnpj}")
            return False
        
        # Verificar se houve falhas
        ucs_com_falha = sum(1 for r in resultados.values() if not r["sucesso"])
        
        if ucs_com_falha == 0:
            print(f"✅ SUCESSO: Geradora {geradora_cnpj} processada com sucesso")
        
        return True
        
    except Exception as e:
        print(f"❌ ERRO: Erro ao processar geradora {geradora_cnpj}: {str(e)}")
        return False

if __name__ == "__main__":
    # Processar todas as geradoras em loop
    print("🚀 Iniciando processamento de todas as geradoras...")
    processar_todas_geradoras()
    
    # Para processar geradoras específicas:
    # processar_usinas = [
    #    #USINA_SULINA_CNPJ,
    #    USINA_LB_CNPJ,
    #    USINA_ENERGIAA_CNPJ,
    #    USINA_LUZDIVINA_CNPJ,
    #    USINA_G114_CNPJ
    # ]
    # print(f"🚀 Iniciando processamento das usinas {processar_usinas}...")
    # processar_multiplas_geradoras(processar_usinas)
