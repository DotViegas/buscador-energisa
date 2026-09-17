import os
from dotenv import load_dotenv

load_dotenv()

DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() in ('true', '1', 'yes')
EMAIL_LOGIN = os.getenv('CREDENTIAL_EMAIL_SMS')
EMAIL_PASSWORD = os.getenv('CREDENTIAL_PASSWORD_SMS')
SERVER_HOST = os.getenv('SERVER_HOST')
API_DOMAIN_FATURAS_PROD = os.getenv('API_DOMAIN_FATURAS_PROD')
API_DOMAIN_FATURAS_DEV = os.getenv('API_DOMAIN_FATURAS_DEV')
API_CREDENTIAL_LOGIN = os.getenv('API_CREDENTIAL_LOGIN')
API_CREDENTIAL_PASSWORD = os.getenv('API_CREDENTIAL_PASSWORD')
API_CRIAR_FATURA_DEV = os.getenv('API_CRIAR_FATURA_DEV')
API_CRIAR_FATURA_PROD = os.getenv('API_CRIAR_FATURA_PROD')
API_ATUALIZAR_FATURA_DEV = os.getenv('API_ATUALIZAR_FATURA_DEV')
API_ATUALIZAR_FATURA_PROD = os.getenv('API_ATUALIZAR_FATURA_PROD')
GEUS_APIKEY = os.getenv('GEUS_APIKEY')

# Minutos de espera entre tentativas após falha de login, acesso negado ou
# falhas repetidas de carregamento (retry longo).
MINUTOS_ENTRE_TENTATIVAS = int(os.getenv('MINUTOS_ENTRE_TENTATIVAS', '30'))

# --- Humanização do scraping (comportamento menos robótico) ---
# HUMANIZAR=False desliga tudo e volta ao comportamento antigo (sleeps fixos, fill direto).
HUMANIZAR = os.getenv('HUMANIZAR', 'True').lower() in ('true', '1', 'yes')
# Pausa aleatória (segundos) entre uma UC e a próxima.
DELAY_UC_MIN = float(os.getenv('DELAY_UC_MIN', '3'))
DELAY_UC_MAX = float(os.getenv('DELAY_UC_MAX', '10'))
