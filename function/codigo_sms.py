import imaplib
import email
import email.utils
import re
import time
from datetime import datetime
from config import EMAIL_LOGIN, EMAIL_PASSWORD, SERVER_HOST


def obter_codigo_email():
    try:
        # Conectar ao Gmail
        mail = imaplib.IMAP4_SSL(SERVER_HOST)
        mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        mail.select("inbox")
        
        # Buscar emails com o assunto específico
        _, messages = mail.search(None, 'SUBJECT "[SMSForwarder] New message from 28115"')
        
        if not messages[0]:
            return None
            
        # Pegar o ID do email mais recente
        latest_email_id = messages[0].split()[-1]
        
        # Buscar o conteúdo do email
        _, msg_data = mail.fetch(latest_email_id, "(RFC822)")
        email_body = msg_data[0][1]
        email_message = email.message_from_bytes(email_body)
        
        # Verificar se o email é recente (últimos 30 segundos)
        email_date = email.utils.parsedate_to_datetime(email_message['Date'])
        if (datetime.now(email_date.tzinfo) - email_date).total_seconds() > 30:
            return None
        
        # Extrair o código do corpo do email
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode()
                match = re.search(r'Codigo de seguranca: (\d+)', body)
                if match:
                    codigo = match.group(1)
                    print(f"Código encontrado: {codigo}")
                    return codigo
        
        return None
    except Exception as e:
        print(f"Erro ao obter código do email: {str(e)}")
        # Adicionar mais detalhes do erro para debug
        import traceback
        traceback.print_exc()
        return None

def obter_codigo_email_com_reenvio_automatico(page, timeout):
    """
    Aguarda o código de email com sistema de reenvio automático.
    Clica no botão "REENVIAR CÓDIGO" a cada 180 segundos para garantir o envio do SMS.
    """
    import time
    
    print(f"Aguardando novo email por {timeout} segundos com reenvio automático a cada 180 segundos...")
    start_time = time.time()
    ultimo_reenvio = start_time
    
    while time.time() - start_time < timeout:
        try:
            # Verificar se é hora de reenviar o código (a cada 180 segundos)
            tempo_atual = time.time()
            if tempo_atual - ultimo_reenvio >= 180:
                try:
                    print("\n🔄 Tentando reenviar código SMS...")
                    # Procurar pelo botão de reenviar código usando Playwright
                    page.get_by_role("button", name="Recarregar REENVIAR CÓDIGO").click()
                    ultimo_reenvio = tempo_atual
                    print("✅ Botão de reenvio clicado com sucesso")

                except Exception as reenvio_error:
                    print(f"⚠️ Erro ao tentar clicar no botão de reenvio: {str(reenvio_error)}")
                    # Se não conseguir encontrar/clicar no botão, continue normalmente
                    ultimo_reenvio = tempo_atual  # Atualiza o tempo para evitar tentativas consecutivas
            
            # Tentar obter o código do email
            codigo = obter_codigo_email()
            if codigo:
                print(f"✅ Código recebido: {codigo}")
                return codigo
            
            # Se não encontrou código, esperar um pouco antes da próxima tentativa
            segundos_restantes = int(timeout - (time.time() - start_time))
            proxima_tentativa_reenvio = int(180 - (tempo_atual - ultimo_reenvio))
            
            print(f"⏳ Aguardando... {segundos_restantes}s restantes | Próximo reenvio em: {max(0, proxima_tentativa_reenvio)}s", end='\r')
            time.sleep(5)  # Esperar 5 segundos entre tentativas de busca do email
            
        except Exception as e:
            print(f"\n❌ Erro ao tentar obter código: {str(e)}")
            print("🔄 Tentando novamente em 5 segundos...")
            time.sleep(5)
    
    print("\n⏰ Tempo esgotado para receber o código de verificação.")
    return None