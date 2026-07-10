"""
Script de teste para verificar se o webhook de atualização de código ANEEL está funcionando
"""
import os
import requests
from dotenv import load_dotenv
from config import DEBUG_MODE

# Carregar variáveis de ambiente
load_dotenv()

def teste_webhook():
    """Testa o envio do webhook com dados de exemplo"""
    
    # Obter configurações do .env
    api_key = os.getenv('GEUS_APIKEY')
    
    # Escolher URL baseado no modo DEBUG
    debug_mode = DEBUG_MODE
    if debug_mode:
        api_domain_faturas = os.getenv('API_DOMAIN_FATURAS_DEV', 'http://127.0.0.1:8000/api/faturas/')
        modo = "DESENVOLVIMENTO (DEV)"
    else:
        api_domain_faturas = os.getenv('API_DOMAIN_FATURAS_PROD', 'https://geus.energiaa.com.br/api/faturas/')
        modo = "PRODUÇÃO (PROD)"
    
    print("=" * 80)
    print("🧪 TESTE DE WEBHOOK - ATUALIZAR CÓDIGO ANEEL")
    print("=" * 80)
    print()
    print(f"🔧 Modo de execução: {modo}")
    print()
    
    # Verificar se o token foi carregado
    if not api_key:
        print("❌ ERRO: Token GEUS_APIKEY não encontrado no arquivo .env")
        return False
    
    print(f"✅ Token carregado: {api_key[:30]}...")
    print(f"🌐 API Domain (faturas): {api_domain_faturas}")
    
    # Extrair a URL base (remover /faturas/ do final)
    # Ex: https://geus.energiaa.com.br/api/faturas/ -> https://geus.energiaa.com.br/api/
    api_base = api_domain_faturas.replace('/faturas/', '/').rstrip('/')
    
    # Construir URL do endpoint (rota correta: api/atualizar_numero_uc/)
    url = f"{api_base}/atualizar_numero_uc/"
    
    print(f"🌐 API Base: {api_base}")
    print(f"📍 URL completa: {url}")
    print()
    
    # Headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Dados de teste
    data = {
        "nova_uc": "10/3738052-4",
        "numero_da_uc": "1.899.274.051-74"
    }
    
    print("📦 Dados de teste:")
    print(f"   nova_uc: {data['nova_uc']}")
    print(f"   numero_da_uc: {data['numero_da_uc']}")
    print()
    
    print("📋 Headers:")
    print(f"   Authorization: Bearer {api_key[:30]}...")
    print(f"   Content-Type: application/json")
    print()
    
    try:
        print("📤 Enviando requisição...")
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        print(f"📥 Status Code: {response.status_code}")
        print()
        
        if response.status_code in [200, 201]:
            print("✅ SUCESSO! Webhook enviado com sucesso!")
            print()
            print("📄 Resposta:")
            try:
                print(response.json())
            except:
                print(response.text)
            return True
        else:
            print(f"❌ ERRO: Status {response.status_code}")
            print()
            print("📄 Resposta:")
            print(response.text)
            print()
            
            # Diagnóstico adicional
            print("🔍 DIAGNÓSTICO:")
            if response.status_code == 403:
                print("   - Erro 403: Forbidden - Problema de autenticação")
                print("   - Verifique se o token GEUS_APIKEY está correto")
                print("   - Verifique se o token tem permissão para acessar este endpoint")
            elif response.status_code == 404:
                print("   - Erro 404: Not Found - Endpoint não encontrado")
                print("   - Verifique se a URL está correta")
                print(f"   - URL testada: {url}")
            elif response.status_code == 400:
                print("   - Erro 400: Bad Request - Dados inválidos")
                print("   - Verifique o formato dos dados enviados")
            
            return False
            
    except requests.exceptions.Timeout:
        print("⏱️ TIMEOUT: A requisição demorou mais de 30 segundos")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"🔌 ERRO DE CONEXÃO: {str(e)}")
        if debug_mode:
            print()
            print("💡 DICA: Você está em modo DEV. Verifique se o servidor local está rodando!")
            print(f"   URL base: {api_base}")
        return False
    except Exception as e:
        print(f"❌ ERRO INESPERADO: {str(e)}")
        return False

if __name__ == "__main__":
    resultado = teste_webhook()
    print()
    print("=" * 80)
    if resultado:
        print("✅ TESTE CONCLUÍDO COM SUCESSO!")
    else:
        print("❌ TESTE FALHOU - Verifique os erros acima")
    print("=" * 80)
