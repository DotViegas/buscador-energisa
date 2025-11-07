import requests
import base64
from datetime import datetime
from playwright.sync_api import sync_playwright
from config import DEBUG_MODE, API_CRIAR_FATURA_DEV, API_CRIAR_FATURA_PROD, API_ATUALIZAR_FATURA_DEV , API_ATUALIZAR_FATURA_PROD, GEUS_APIKEY

debug_mode = DEBUG_MODE

def fazer_download_com_retry(page, download_button, nova_uc, mes_referencia, primeira_fatura=False):
    """
    Função auxiliar para fazer download da fatura com retry em caso de erro de modal
    
    Args:
        page: Instância da página do Playwright
        download_button: Elemento do botão de download
        nova_uc (str): UC no formato "10/xxxxxxx-1x"
        mes_referencia (str): Mês de referência no formato "MM/AAAA"
        primeira_fatura (bool): Parâmetro mantido para compatibilidade (não usado)
    
    Returns:
        str: Arquivo em base64 se sucesso, None se falha
    """
    from function.notificar_gestor import fatura_nao_baixada
    
    max_tentativas = 5
    tentativa_atual = 0
    download_sucesso = False
    arquivo_base64 = None
    
    while tentativa_atual < max_tentativas and not download_sucesso:
        tentativa_atual += 1
        print(f"Tentativa {tentativa_atual} de {max_tentativas} para download da fatura")
        
        try:
            # Clicar no botão de download
            download_button.click()
            
            # Aguardar o download ou modal de erro com verificação periódica
            download = None
            modal_detectado = False
            tempo_espera = 0
            max_tempo_espera = 30000  # 30 segundos
            intervalo_verificacao = 1000  # 1 segundo
            
            while tempo_espera < max_tempo_espera and not download and not modal_detectado:
                try:
                    # Tentar capturar download com timeout curto
                    with page.expect_download(timeout=intervalo_verificacao) as download_info:
                        pass
                    download = download_info.value
                    break
                except:
                    # Verificar se modal de erro apareceu
                    try:
                        modal_erro = page.locator('text="Houve um erro na sua tentativa de download"')
                        if modal_erro.is_visible():
                            modal_detectado = True
                            print("🔍 Modal de erro detectado durante o download!")
                            break
                    except:
                        pass  # Continuar verificando
                    
                    tempo_espera += intervalo_verificacao
            
            if modal_detectado:
                # Fechar modal de erro
                print("🔍 Tentando fechar modal de erro...")
                botao_ok = page.locator('button:has-text("OK")')
                
                if botao_ok.is_visible():
                    botao_ok.click()
                    print("✅ Modal fechado com sucesso")
                    page.wait_for_timeout(1000)
                else:
                    # Tentar outros seletores comuns para botão OK
                    botoes_alternativos = [
                        'button[type="button"]:has-text("OK")',
                        '.btn:has-text("OK")',
                        '[role="button"]:has-text("OK")',
                        'button:text-is("OK")'
                    ]
                    
                    for seletor in botoes_alternativos:
                        try:
                            botao_alt = page.locator(seletor)
                            if botao_alt.is_visible():
                                botao_alt.click()
                                print(f"✅ Modal fechado usando seletor alternativo: {seletor}")
                                page.wait_for_timeout(1000)
                                break
                        except:
                            continue
                    else:
                        print("⚠️ Não foi possível encontrar botão OK para fechar modal")
                
                # Continuar para próxima tentativa
                raise Exception("Modal de erro detectado durante download")
            
            if not download:
                print(f"⚠️ Download não detectado após {max_tempo_espera/1000} segundos")
                print("🔄 Fazendo refresh da página para tentar novamente...")
                page.reload()
                page.wait_for_timeout(3000)  # Aguardar página carregar
                raise Exception(f"Timeout de {max_tempo_espera/1000} segundos excedido - página recarregada")
            
            # Salvar arquivo temporariamente e converter para base64
            temp_path = f"temp_fatura_{nova_uc.replace('/', '_')}_{mes_referencia.replace('/', '_')}.pdf"
            download.save_as(temp_path)
            
            # Converter para base64
            with open(temp_path, 'rb') as file:
                arquivo_base64 = base64.b64encode(file.read()).decode('utf-8')
            
            # Remover arquivo temporário
            import os
            os.remove(temp_path)
            
            download_sucesso = True
            print(f"✅ Download realizado com sucesso na tentativa {tentativa_atual}")
            
        except Exception as download_error:
            print(f"❌ Erro no download (tentativa {tentativa_atual}): {str(download_error)}")
            
            # Se não é a última tentativa, aguardar antes da próxima
            if tentativa_atual < max_tentativas:
                print(f"⏳ Aguardando antes da próxima tentativa...")
                page.wait_for_timeout(3000)
    
    # Verificar se o download foi bem-sucedido
    if not download_sucesso or arquivo_base64 is None:
        print(f"❌ Falha no download após {max_tentativas} tentativas")
        print("📞 Chamando função de notificação do gestor...")
        fatura_nao_baixada()
        return None
    
    return arquivo_base64

def processar_faturas_do_json(json_data, page):
    """
    Processa as faturas do JSON e chama as funções apropriadas
    
    Args:
        json_data (dict): Dados do JSON com as faturas organizadas
        page: Instância da página do Playwright
    """
    try:
        geradora = json_data.get("geradora")
        lista_ucs = json_data.get("lista_ucs", {})
        
        print(f"Processando geradora: {geradora}")
        print(f"Total de UCs: {len(lista_ucs)}")
        
        resultados = []
        primeira_fatura_processada = False
        
        for nova_uc, faturas in lista_ucs.items():
            print(f"\n--- Processando UC: {nova_uc} ---")
            
            for fatura in faturas:
                fatura_id = fatura.get("id")
                mes_referencia = fatura.get("data_referencia")
                tarefa = fatura.get("tarefa")
                
                print(f"Processando fatura ID: {fatura_id}, Mês: {mes_referencia}, Tarefa: {tarefa}")
                
                # Determinar se é a primeira fatura da geradora
                eh_primeira_fatura = not primeira_fatura_processada
                
                if tarefa == "fatura_pendente":
                    resultado = executar_fatura_pendente(nova_uc, mes_referencia, page, fatura_id, eh_primeira_fatura)
                    resultados.append({
                        "id": fatura_id,
                        "uc": nova_uc,
                        "mes": mes_referencia,
                        "tarefa": tarefa,
                        "sucesso": resultado
                    })
                    
                elif tarefa == "fatura_vencida":
                    resultado = executar_fatura_vencida(nova_uc, mes_referencia, page, fatura_id, fatura, eh_primeira_fatura)
                    resultados.append({
                        "id": fatura_id,
                        "uc": nova_uc,
                        "mes": mes_referencia,
                        "tarefa": tarefa,
                        "sucesso": resultado
                    })
                    
                elif tarefa == "fatura_a_vencer":
                    # Usar a função de fatura vencida para faturas a vencer (com verificação de mudanças)
                    resultado = executar_fatura_vencida(nova_uc, mes_referencia, page, fatura_id, fatura, eh_primeira_fatura)
                    resultados.append({
                        "id": fatura_id,
                        "uc": nova_uc,
                        "mes": mes_referencia,
                        "tarefa": tarefa,
                        "sucesso": resultado
                    })
                
                else:
                    print(f"⚠️ Tarefa desconhecida: {tarefa}")
                
                # Marcar que já processamos a primeira fatura (independente do sucesso)
                if not primeira_fatura_processada:
                    primeira_fatura_processada = True
        
        # Resumo dos resultados
        sucessos = sum(1 for r in resultados if r["sucesso"])
        total = len(resultados)
        print(f"\n📊 Resumo do processamento:")
        print(f"Total de faturas processadas: {total}")
        print(f"Sucessos: {sucessos}")
        print(f"Falhas: {total - sucessos}")
        
        return resultados
        
    except Exception as e:
        print(f"❌ Erro durante processamento do JSON: {str(e)}")
        return []

def executar_fatura_pendente(nova_uc, mes_referencia, page, fatura_id, primeira_fatura=False):
    """
    Executa o processamento de fatura pendente
    
    Args:
        nova_uc (str): UC no formato "10/xxxxxxx-1x"
        mes_referencia (str): Mês de referência no formato "MM/AAAA"
        page: Instância da página do Playwright
        fatura_id (int): ID da fatura do JSON
        primeira_fatura (bool): Se é a primeira fatura da geradora
    """
    try:
        print(f"Iniciando processamento de fatura pendente para UC: {nova_uc}, Mês: {mes_referencia}")
        
        # 1. Buscar o mês de referência da nova_uc processada no formato MM/AAAA
        mes_busca = mes_referencia
        print(f"Buscando fatura para o mês: {mes_busca}")
        
        # 2. Listar todos os cards da página usando o seletor preciso "card-billing__date"
        cards_date = page.locator('.card-billing__date')
        cards_count = cards_date.count()
        print(f"Encontrados {cards_count} cards de fatura na página")
        
        fatura_encontrada = False
        dados_fatura = {}
        
        # 3. Verificar se existe o card referente ao mês buscado
        for i in range(cards_count):
            card_date = cards_date.nth(i)
            
            # Extrair mês e ano do card
            mes_element = card_date.locator('p').first
            ano_element = card_date.locator('p').last
            
            mes_texto = mes_element.text_content().strip()
            ano_texto = ano_element.text_content().strip()
            
            # Converter mês para número
            meses = {
                'Janeiro': '01', 'Fevereiro': '02', 'Março': '03', 'Abril': '04',
                'Maio': '05', 'Junho': '06', 'Julho': '07', 'Agosto': '08',
                'Setembro': '09', 'Outubro': '10', 'Novembro': '11', 'Dezembro': '12'
            }
            
            mes_numero = meses.get(mes_texto, '00')
            mes_card = f"{mes_numero}/{ano_texto}"
            
            print(f"Card {i+1}: {mes_texto} {ano_texto} ({mes_card})")
            
            # Verificar se é o mês que estamos buscando
            if mes_card == mes_busca:
                print(f"✓ Fatura encontrada para {mes_texto} {ano_texto}")
                fatura_encontrada = True
                
                # Buscar o card completo que contém todas as informações
                # Navegar para o elemento pai que contém todo o card da fatura
                card_completo = card_date.locator('xpath=ancestor::*[contains(@class, "card-billing") or contains(@class, "card")]').first
                
                # Verificar situação de pagamento baseada na classe CSS do card-billing__top
                situacao_element = card_completo.locator('.card-billing__top')
                situacao_class = situacao_element.get_attribute('class')
                
                # Determinar situação de pagamento
                if 'card-billing__top--green' in situacao_class:
                    situacao_pagamento = "paga"
                elif 'card-billing__top--orange' in situacao_class:
                    situacao_pagamento = "a_vencer"
                elif 'card-billing__top--red' in situacao_class:
                    situacao_pagamento = "vencida"
                else:
                    situacao_pagamento = "desconhecida"
                
                print(f"Situação de pagamento detectada: {situacao_pagamento}")
                
                # Extrair valor da fatura
                valor_element = card_completo.locator('.card-billing__price .min-w-\\[200px\\]')
                valor_texto = valor_element.text_content().strip()
                valor = valor_texto.replace('R$', '').replace(' ', '').replace(',', '.')
                
                # Extrair data de vencimento
                vencimento_element = card_completo.locator('.font-bold').last
                vencimento_texto = vencimento_element.text_content().strip()
                
                # Converter data de vencimento para formato AAAA-MM-DD
                dia, mes, ano = vencimento_texto.split('/')
                data_vencimento = f"{ano}-{mes}-{dia}"
                
                print(f"Valor: R$ {valor}")
                print(f"Vencimento: {vencimento_texto} -> {data_vencimento}")
                
                # Fazer download da fatura com retry
                download_button = card_completo.locator('button[data-pix="false"]')
                arquivo_base64 = fazer_download_com_retry(page, download_button, nova_uc, mes_referencia, primeira_fatura)
                
                if arquivo_base64 is None:
                    print("❌ Falha no download da fatura após todas as tentativas")
                    return False
                
                dados_fatura = {
                    "valor": valor,
                    "data_vencimento": data_vencimento,
                    "data_referencia": mes_referencia,
                    "arquivo_fatura": arquivo_base64,
                    "nome_arquivo_fatura": f"fatura_{nova_uc}_{mes_referencia}.pdf",
                    "situacao_pagamento": situacao_pagamento
                }
                
                break
        
        if not fatura_encontrada:
            print(f"❌ Fatura não encontrada para o mês {mes_busca}")
            return False
        
        # 4. Enviar requisição para a API
        if debug_mode:
            url = API_CRIAR_FATURA_DEV
        else:
            url = API_CRIAR_FATURA_PROD
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEUS_APIKEY}"
        }
        
        body = {
            "id": fatura_id,
            "nova_uc": nova_uc,
            "data_vencimento": dados_fatura["data_vencimento"],
            "data_referencia": dados_fatura["data_referencia"],
            "valor": dados_fatura["valor"],
            "arquivo_fatura": dados_fatura["arquivo_fatura"],
            "nome_arquivo_fatura": dados_fatura["nome_arquivo_fatura"],
            "data_encontrada": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "situacao_pagamento": dados_fatura["situacao_pagamento"],
            "situacao_energia_a": "sem_injecao",
            "tipo_tensao": None,
            "tipo_gd": None
        }
        
        print(f"Enviando dados para API: {url}")
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code == 200:
            print("✅ Fatura enviada com sucesso para a API")
            return True
        else:
            print(f"❌ Erro ao enviar fatura para API: {response.status_code}")
            print(f"Resposta: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro durante processamento da fatura pendente: {str(e)}")
        return False


def executar_fatura_vencida(nova_uc, mes_referencia, page, fatura_id, fatura_existente=None, primeira_fatura=False):
    """
    Executa o processamento de fatura vencida
    
    Args:
        nova_uc (str): UC no formato "10/xxxxxxx-1x"
        mes_referencia (str): Mês de referência no formato "MM/AAAA"
        page: Instância da página do Playwright
        fatura_id (int): ID da fatura do JSON
        fatura_existente (dict): Dados da fatura existente para comparação (opcional)
        primeira_fatura (bool): Se é a primeira fatura da geradora
    """
    try:
        print(f"Iniciando processamento de fatura vencida para UC: {nova_uc}, Mês: {mes_referencia}")
        
        # 1. Buscar o mês de referência da nova_uc processada no formato MM/AAAA
        mes_busca = mes_referencia
        print(f"Buscando fatura para o mês: {mes_busca}")
        
        # 2. Listar todos os cards da página usando o seletor preciso "card-billing__date"
        cards_date = page.locator('.card-billing__date')
        cards_count = cards_date.count()
        print(f"Encontrados {cards_count} cards de fatura na página")
        
        fatura_encontrada = False
        dados_fatura = {}
        
        # 3. Verificar se existe o card referente ao mês buscado
        for i in range(cards_count):
            card_date = cards_date.nth(i)
            
            # Extrair mês e ano do card
            mes_element = card_date.locator('p').first
            ano_element = card_date.locator('p').last
            
            mes_texto = mes_element.text_content().strip()
            ano_texto = ano_element.text_content().strip()
            
            # Converter mês para número
            meses = {
                'Janeiro': '01', 'Fevereiro': '02', 'Março': '03', 'Abril': '04',
                'Maio': '05', 'Junho': '06', 'Julho': '07', 'Agosto': '08',
                'Setembro': '09', 'Outubro': '10', 'Novembro': '11', 'Dezembro': '12'
            }
            
            mes_numero = meses.get(mes_texto, '00')
            mes_card = f"{mes_numero}/{ano_texto}"
            
            print(f"Card {i+1}: {mes_texto} {ano_texto} ({mes_card})")
            
            # Verificar se é o mês que estamos buscando
            if mes_card == mes_busca:
                print(f"✓ Fatura encontrada para {mes_texto} {ano_texto}")
                fatura_encontrada = True
                
                # Buscar o card completo que contém todas as informações
                # Navegar para o elemento pai que contém todo o card da fatura
                card_completo = card_date.locator('xpath=ancestor::*[contains(@class, "card-billing") or contains(@class, "card")]').first
                
                # Verificar situação de pagamento baseada na classe CSS do card-billing__top
                situacao_element = card_completo.locator('.card-billing__top')
                situacao_class = situacao_element.get_attribute('class')
                
                # Determinar situação de pagamento
                if 'card-billing__top--green' in situacao_class:
                    situacao_pagamento = "paga"
                elif 'card-billing__top--orange' in situacao_class:
                    situacao_pagamento = "a_vencer"
                elif 'card-billing__top--red' in situacao_class:
                    situacao_pagamento = "vencida"
                else:
                    situacao_pagamento = "desconhecida"
                
                print(f"Situação de pagamento detectada: {situacao_pagamento}")
                
                # Extrair valor da fatura
                valor_element = card_completo.locator('.card-billing__price .min-w-\\[200px\\]')
                valor_texto = valor_element.text_content().strip()
                valor = valor_texto.replace('R$', '').replace(' ', '').replace(',', '.')

                if valor == "0":
                    valor = "0.00"
                
                # Extrair data de vencimento
                vencimento_element = card_completo.locator('.font-bold').last
                vencimento_texto = vencimento_element.text_content().strip()
                
                # Converter data de vencimento para formato AAAA-MM-DD
                dia, mes, ano = vencimento_texto.split('/')
                data_vencimento = f"{ano}-{mes}-{dia}"
                
                print(f"Valor: R$ {valor}")
                print(f"Vencimento: {vencimento_texto} -> {data_vencimento}")
                
                # Armazenar referência do botão de download para uso posterior
                download_button = card_completo.locator('button[data-pix="false"]')
                
                # Inicializar dados básicos da fatura (sem arquivo ainda)
                dados_fatura = {
                    "valor": valor,
                    "data_vencimento": data_vencimento,
                    "data_referencia": mes_referencia,
                    "arquivo_fatura": None,
                    "nome_arquivo_fatura": f"fatura_{nova_uc}_{mes_referencia}.pdf",
                    "situacao_pagamento": situacao_pagamento
                }
                
                break
        
        if not fatura_encontrada:
            print(f"❌ Fatura não encontrada para o mês {mes_busca}")
            return False
        
        # 4. Verificar se houve mudanças além da situação de pagamento
        apenas_situacao_mudou = False
        precisa_download = True  # Por padrão, assume que precisa fazer download
        
        if fatura_existente:
            # Comparar dados atuais com os existentes
            valor_mudou = dados_fatura["valor"] != fatura_existente.get("valor")
            vencimento_mudou = dados_fatura["data_vencimento"] != fatura_existente.get("data_vencimento")
            situacao_mudou = dados_fatura["situacao_pagamento"] != fatura_existente.get("situacao_pagamento")
            
            print(f"Comparação com fatura existente:")
            print(f"  Valor mudou: {valor_mudou} ({dados_fatura['valor']} vs {fatura_existente.get('valor')})")
            print(f"  Vencimento mudou: {vencimento_mudou} ({dados_fatura['data_vencimento']} vs {fatura_existente.get('data_vencimento')})")
            print(f"  Situação mudou: {situacao_mudou} ({dados_fatura['situacao_pagamento']} vs {fatura_existente.get('situacao_pagamento')})")
            
            # Se apenas a situação mudou (valor e vencimento não mudaram)
            if situacao_mudou and not valor_mudou and not vencimento_mudou:
                apenas_situacao_mudou = True
                precisa_download = False  # Não precisa fazer download se só a situação mudou
                print("📋 Detectado: Apenas situação de pagamento foi alterada - download não necessário")
            elif situacao_mudou or valor_mudou or vencimento_mudou:
                print("📋 Detectado: Múltiplos campos foram alterados - download necessário")
            else:
                print("📋 Nenhuma alteração detectada")
                return True  # Não há necessidade de atualizar
        
        # 5. Fazer download apenas se necessário
        if precisa_download:
            print("📥 Iniciando download da fatura...")
            arquivo_base64 = fazer_download_com_retry(page, download_button, nova_uc, mes_referencia, primeira_fatura)
            
            if arquivo_base64 is None:
                print("❌ Falha no download da fatura após todas as tentativas")
                return False
            
            # Atualizar dados da fatura com o arquivo
            dados_fatura["arquivo_fatura"] = arquivo_base64
            print("✅ Download concluído com sucesso")
        else:
            print("⏭️ Download pulado - apenas situação de pagamento mudou")
        
        # 5. Enviar requisição baseada no tipo de mudança
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GEUS_APIKEY}"
        }
        
        if apenas_situacao_mudou:
            # Cenário 1: Apenas situação de pagamento mudou - usar API de atualização
            if debug_mode:
                url = API_ATUALIZAR_FATURA_DEV
            else:
                url = API_ATUALIZAR_FATURA_PROD
            
            body = {
                "id": fatura_id,
                "situacao_pagamento": dados_fatura["situacao_pagamento"]
            }
            
            print(f"Enviando atualização de situação para API: {url}")
            print(f"Atualizando apenas situação para: {dados_fatura['situacao_pagamento']}")
            
        else:
            # Cenário 2: Múltiplos campos mudaram - usar API de criação completa
            if debug_mode:
                url = API_CRIAR_FATURA_DEV
            else:
                url = API_CRIAR_FATURA_PROD
            
            # Verificar se o arquivo foi baixado
            if dados_fatura["arquivo_fatura"] is None:
                print("❌ Erro: Tentativa de enviar dados completos sem arquivo da fatura")
                return False
            
            body = {
                "id": fatura_id,
                "nova_uc": nova_uc,
                "data_vencimento": dados_fatura["data_vencimento"],
                "data_referencia": dados_fatura["data_referencia"],
                "valor": dados_fatura["valor"],
                "arquivo_fatura": dados_fatura["arquivo_fatura"],
                "nome_arquivo_fatura": dados_fatura["nome_arquivo_fatura"],
                "data_encontrada": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "situacao_pagamento": dados_fatura["situacao_pagamento"],
                "situacao_energia_a": "sem_injecao",
                "tipo_tensao": None,
                "tipo_gd": None
            }
            
            print(f"Enviando dados completos para API: {url}")
        
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code == 200:
            if apenas_situacao_mudou:
                print("✅ Situação de pagamento atualizada com sucesso")
            else:
                print("✅ Fatura enviada com sucesso para a API")
            return True
        else:
            print(f"❌ Erro ao enviar para API: {response.status_code}")
            print(f"Resposta: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro durante processamento da fatura vencida: {str(e)}")
        return False
