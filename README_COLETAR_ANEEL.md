# 🔍 Coletor de Códigos ANEEL - Energisa

## 📋 Descrição

Este script automatiza a coleta de **códigos ANEEL** (Número da UC) de todas as unidades consumidoras cadastradas no portal da Energisa e envia essas informações via webhook para atualização no sistema GEUS.

## 🎯 Funcionalidade

O script realiza as seguintes operações:

1. **Busca dados da API** para obter lista de UCs pendentes
2. **Login automático** no portal Energisa usando o CNPJ da geradora
3. **Navegação** para a página de listagem de UCs
4. **Para cada UC da API**:
   - Usa o **campo de busca** para localizar a UC específica
   - Extrai o **Código do Cliente** (nova_uc completo)
   - Extrai o **Número da UC** (código ANEEL formatado) diretamente do botão
   - Envia os dados via webhook para a API
   - **Limpa o campo de busca** e processa a próxima UC (sem recarregar página)
5. **Estatísticas** de processamento ao final

## 🆕 Diferenças entre `coletar_codigos_aneel.py` e `robo_aneel.py`

| Característica | coletar_codigos_aneel.py | robo_aneel.py |
|----------------|--------------------------|---------------|
| **Método** | Lista todas UCs visíveis na página | Busca cada UC individualmente |
| **Cobertura** | Apenas UCs visíveis (limitado) | **Todas as UCs da API** ✅ |
| **Performance** | Mais rápido (menos requisições) | Mais lento (uma busca por UC) |
| **Precisão** | Pode perder UCs não visíveis | **100% das UCs da API** ✅ |
| **Recomendado** | Testes rápidos | **Produção** ✅ |

## 🔧 Configuração

### Pré-requisitos

- Python 3.8+
- Playwright instalado
- Arquivo `.env` configurado com:
  - `DEBUG_MODE`: Define se usa DEV ou PROD (`True` = DEV, `False` = PROD)
  - `GEUS_APIKEY`: Token de autenticação da API
  - `API_DOMAIN_FATURAS_PROD`: URL da API de produção
  - `API_DOMAIN_FATURAS_DEV`: URL da API de desenvolvimento

### Arquivo `.env` - Exemplo

```env
# Modo de execução (True = DEV, False = PROD)
DEBUG_MODE=False

# URLs da API (base sem /faturas/)
API_DOMAIN_FATURAS_PROD=https://geus.energiaa.com.br/api/
API_DOMAIN_FATURAS_DEV=http://127.0.0.1:8000/api/

# Token de autenticação
GEUS_APIKEY=geus-server-f3a1ca61cf5ba4d3e94e41f41c9cf4a0d3104de03b7a31f4de7a95f561b602af
```

### 🔄 Alternar entre DEV e PROD

Edite o arquivo `.env`:

```env
# Para usar DESENVOLVIMENTO (localhost)
DEBUG_MODE=True

# Para usar PRODUÇÃO (servidor real)
DEBUG_MODE=False
```

O script automaticamente escolherá a URL correta baseado nessa configuração!

### Instalação

```bash
# Instalar dependências (se ainda não instalou)
pip install -r requirements.txt

# Instalar navegadores do Playwright
playwright install chromium
```

## 🚀 Como Usar

### 🧪 Passo 1: Testar o Webhook (RECOMENDADO)

Antes de executar o script completo, teste se o webhook está funcionando:

```bash
# Windows
teste_webhook_aneel.bat

# Linux/Mac
python teste_webhook_aneel.py
```

O teste mostrará:
- ✅ Se está usando DEV ou PROD
- ✅ Se o token está carregado
- ✅ A URL completa do endpoint
- ✅ O resultado da requisição

**Exemplo de saída:**
```
🔧 Modo de execução: PRODUÇÃO (PROD)
✅ Token carregado: geus-server-f3a1ca61cf5ba4...
📍 URL completa: https://geus.energiaa.com.br/api/faturas/atualizar_numero_uc/
📤 Enviando requisição...
📥 Status Code: 200
✅ SUCESSO! Webhook enviado com sucesso!
```

### 🚀 Passo 2: Executar o Script

#### Opção 1: Processar Todas as Geradoras (RECOMENDADO)

```bash
# Windows
robo_aneel.bat

# Linux/Mac
python robo_aneel.py
```

#### Opção 2: Processar Geradora Específica

```bash
python robo_aneel.py "47.278.309/0001-01"
```

#### Opção 3: Teste Rápido (apenas UCs visíveis)

```bash
python coletar_codigos_aneel.py
```

## 📡 Webhook - Especificações Técnicas

### Endpoint

```
POST {API_DOMAIN}/atualizar_numero_uc/
```

**URLs por Ambiente:**
- **PROD**: `https://geus.energiaa.com.br/api/atualizar_numero_uc/`
- **DEV**: `http://127.0.0.1:8000/api/atualizar_numero_uc/`

### Headers

```
Authorization: Bearer {GEUS_APIKEY}
Content-Type: application/json
```

### Body (JSON)

```json
{
  "nova_uc": "3622059",
  "numero_da_uc": "1.234.567.890.123-45"
}
```

### Campos

| Campo | Tipo | Descrição | Exemplo |
|-------|------|-----------|---------|
| `nova_uc` | String | Código da UC para localizar o endereço | `"3622059"` ou `"10/3622059-8"` |
| `numero_da_uc` | String | Código ANEEL (9 a 15 dígitos formatados) | `"1.234.567.890.123-45"` |

### Formatos Aceitos para `numero_da_uc`

| Dígitos | Formato | Exemplo |
|---------|---------|---------|
| 9 | X.XXX.XXX-XX | 1.234.567-89 |
| 10 | XX.XXX.XXX-XX | 12.345.678-90 |
| 11 | XXX.XXX.XXX-XX | 123.456.789-01 |
| 12 | X.XXX.XXX.XXX-XX | 1.234.567.890-12 |
| 13 | XX.XXX.XXX.XXX-XX | 12.345.678.901-23 |
| 14 | XXX.XXX.XXX.XXX-XX | 123.456.789.012-34 |
| 15 | X.XXX.XXX.XXX.XXX-XX | 1.234.567.890.123-45 |

**Regras de Formatação:**
- Blocos de 3 dígitos separados por pontos (`.`)
- Primeiro bloco pode ter 1, 2 ou 3 dígitos
- Sempre termina com traço e 2 dígitos verificadores (`-XX`)

## 📊 Logs

Os logs são salvos automaticamente na pasta `logs/` com o formato:

```
logs/aneel_DDMMYYYY-HHMMSS.txt
```

Exemplo: `logs/aneel_30042026-143025.txt`

## 🔒 Segurança

- O script utiliza o token `GEUS_APIKEY` do arquivo `.env` para autenticação
- Todas as requisições são feitas via HTTPS
- O token nunca é exposto nos logs

## ⚠️ Tratamento de Erros

O script possui tratamento robusto de erros:

- **Access Denied**: Para a execução automaticamente se detectar bloqueio
- **Timeout de Login**: Aguarda 30 minutos e tenta novamente automaticamente
- **Erro em UC específica**: Registra o erro e continua para a próxima UC
- **Erro de Webhook**: Registra o erro mas continua o processamento

## 📈 Estatísticas

Ao final da execução, o script exibe:

- Total de UCs processadas
- Total de webhooks enviados com sucesso
- Total de erros
- Taxa de sucesso (%)

## 🔄 Diferenças do `robo.py`

| Característica | robo.py | coletar_codigos_aneel.py |
|----------------|---------|--------------------------|
| **Objetivo** | Baixar faturas | Coletar códigos ANEEL |
| **Página** | Página de faturas | Listagem de UCs |
| **Ação** | Clica e baixa PDF | Extrai código e envia webhook |
| **Loop** | Por fatura | Por UC |
| **Webhook** | Não envia | Envia para cada UC |

## 🛠️ Manutenção

### Adicionar Nova Geradora

Edite o arquivo `geradoras.py` e adicione o CNPJ:

```python
USINA_NOVA_CNPJ = "12.345.678/0001-90"
```

Depois, adicione na lista em `coletar_codigos_aneel.py`:

```python
geradoras_cnpjs = [
    USINA_ENERGIAA_CNPJ,
    USINA_SULINA_CNPJ,
    # ... outras geradoras
    USINA_NOVA_CNPJ,  # Nova geradora
]
```

## 📞 Suporte

Em caso de dúvidas ou problemas:

1. Verifique os logs na pasta `logs/`
2. Confirme que o arquivo `.env` está configurado corretamente
3. Verifique se o token `GEUS_APIKEY` está válido
4. Teste o endpoint da API manualmente usando curl ou Postman

## 📝 Exemplo de Uso da API

```python
import requests

url = "https://geus.energiaa.com.br/api/faturas/atualizar_numero_uc/"
headers = {
    "Authorization": "Bearer geus-server-f3a1ca61cf5ba4d3e94e41f41c9cf4a0d3104de03b7a31f4de7a95f561b602af",
    "Content-Type": "application/json"
}
data = {
    "nova_uc": "3622059",
    "numero_da_uc": "1.234.567.890.123-45"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

## ✅ Checklist de Execução

Antes de executar o script, verifique:

- [ ] Arquivo `.env` configurado
- [ ] Token `GEUS_APIKEY` válido
- [ ] Playwright instalado (`playwright install chromium`)
- [ ] Dependências instaladas (`pip install -r requirements.txt`)
- [ ] Credenciais de email SMS configuradas no `.env`
- [ ] Conexão com internet estável

## 🎉 Pronto!

Agora você pode executar o script e coletar todos os códigos ANEEL automaticamente!
