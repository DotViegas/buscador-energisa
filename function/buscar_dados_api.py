import os
import json
import requests
from config import API_DOMAIN_FATURAS_PROD, API_DOMAIN_FATURAS_DEV, API_CREDENTIAL_LOGIN, API_CREDENTIAL_PASSWORD, DEBUG_MODE
from geradoras import (
    USINA_LUNA_CNPJ, USINA_SULINA_CNPJ, USINA_LB_CNPJ, 
    USINA_ENERGIAA_CNPJ, USINA_LUZDIVINA_CNPJ, USINA_G114_CNPJ, USINA_SLLG
)

debug_mode = DEBUG_MODE

def extrair_numero_fatura(nova_uc):
    """Extrai o número da fatura removendo tudo antes de '/' e depois de '-'
    Exemplo: 10/3622059-8 => 3622059
    """
    if not nova_uc:
        return nova_uc
    
    # Remove tudo antes do "/" (inclusive o "/")
    if "/" in nova_uc:
        nova_uc = nova_uc.split("/", 1)[1]
    
    # Remove tudo depois do "-" (inclusive o "-")
    if "-" in nova_uc:
        nova_uc = nova_uc.split("-", 1)[0]
    
    return nova_uc.strip()

def mapear_situacao_para_tarefa(situacao_pagamento):
    """Mapeia a situação de pagamento para o nome da tarefa"""
    mapeamento = {
        "pendente": "fatura_pendente",
        "a_vencer": "fatura_a_vencer", 
        "vencida": "fatura_vencida",
        "agendado": "fatura_agendado"
    }
    return mapeamento.get(situacao_pagamento, f"fatura_{situacao_pagamento}")

def organizar_faturas_por_geradora(faturas):
    """Organiza as faturas por geradora e nova_uc conforme estrutura solicitada"""
    geradoras_organizadas = {}
    
    for fatura in faturas:
        cnpj_geradora = fatura.get("cnpj_geradora")
        nova_uc_original = fatura.get("nova_uc")
        situacao_pagamento = fatura.get("situacao_pagamento")
        
        # Pular faturas sem dados essenciais
        if not cnpj_geradora or not nova_uc_original or not situacao_pagamento:
            continue
            
        # Filtrar apenas as situações que nos interessam
        if situacao_pagamento not in ["pendente", "a_vencer", "vencida", "agendado"]:
            continue
        
        # Extrair apenas o número da fatura (ex: 10/3622059-8 => 3622059)
        nova_uc = extrair_numero_fatura(nova_uc_original)
        
        # Inicializar estrutura da geradora se não existir
        if cnpj_geradora not in geradoras_organizadas:
            geradoras_organizadas[cnpj_geradora] = {
                "geradora": cnpj_geradora,
                "lista_ucs": {}
            }
        
        # Inicializar lista da UC se não existir
        if nova_uc not in geradoras_organizadas[cnpj_geradora]["lista_ucs"]:
            geradoras_organizadas[cnpj_geradora]["lista_ucs"][nova_uc] = []
        
        # Adicionar tarefa baseada na situação de pagamento
        fatura_com_tarefa = fatura.copy()
        fatura_com_tarefa["tarefa"] = mapear_situacao_para_tarefa(situacao_pagamento)
        # Atualizar o campo nova_uc com o valor processado
        fatura_com_tarefa["nova_uc"] = nova_uc
        
        # Adicionar fatura à lista da UC
        geradoras_organizadas[cnpj_geradora]["lista_ucs"][nova_uc].append(fatura_com_tarefa)
    
    return geradoras_organizadas

def salvar_json_por_geradora(geradoras_organizadas, diretorio="media/json"):
    """Salva um JSON para cada geradora usando apenas os números do CNPJ"""
    
    def extrair_numeros_cnpj(cnpj):
        """Extrai apenas os números do CNPJ"""
        return ''.join(filter(str.isdigit, cnpj))
    
    arquivos_salvos = []
    
    for cnpj_geradora, dados_geradora in geradoras_organizadas.items():
        # Usar apenas os números do CNPJ como nome do arquivo
        nome_arquivo_numerico = extrair_numeros_cnpj(cnpj_geradora)
        nome_arquivo = f"{nome_arquivo_numerico}.json"
        caminho_arquivo = os.path.join(diretorio, nome_arquivo)
        
        # Contar total de faturas para esta geradora
        total_faturas = sum(len(faturas_uc) for faturas_uc in dados_geradora["lista_ucs"].values())
        
        with open(caminho_arquivo, "w", encoding="utf-8") as json_file:
            json.dump(dados_geradora, json_file, indent=4, ensure_ascii=False)
        
        print(f"✓ {nome_arquivo} salvo com {total_faturas} faturas em {len(dados_geradora['lista_ucs'])} UCs")
        arquivos_salvos.append(caminho_arquivo)
    
    return arquivos_salvos

def buscar_faturas():
    """Função principal para buscar e organizar faturas"""
    if debug_mode:
        url = API_DOMAIN_FATURAS_DEV
    else:
        url = API_DOMAIN_FATURAS_PROD
        
    headers = {
        "Accept": "application/json"
    }
    auth = (API_CREDENTIAL_LOGIN, API_CREDENTIAL_PASSWORD)
    
    try:
        response = requests.get(url, headers=headers, auth=auth)
        
        if response.status_code == 200:
            faturas = response.json()
            print(f"\n📊 Total de faturas encontradas na API: {len(faturas)}")
            
            # Criar diretório media/json se não existir
            os.makedirs("media/json", exist_ok=True)
            print("📁 Arquivos JSON serão salvos em: media/json/")
            
            # Filtrar faturas com nova_uc vazia
            faturas_filtradas = [fatura for fatura in faturas if fatura.get("nova_uc") and fatura.get("nova_uc").strip()]
            print(f"🔍 Total de faturas após filtrar UCs vazias: {len(faturas_filtradas)}")
            
            # Organizar faturas por geradora
            geradoras_organizadas = organizar_faturas_por_geradora(faturas_filtradas)
            print(f"🏭 Geradoras encontradas: {len(geradoras_organizadas)}")
            
            # Salvar JSONs organizados
            arquivos_salvos = salvar_json_por_geradora(geradoras_organizadas)
            
            print(f"\n✅ Processamento concluído! {len(arquivos_salvos)} arquivos salvos.")
            return "media/json"
            
        else:
            print(f"❌ Erro ao buscar faturas: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Erro durante o processamento: {str(e)}")
        return None