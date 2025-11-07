# 🤖 Sistema de Processamento de Faturas Energisa

Microserviço automatizado para buscar, processar e atualizar faturas da Energisa no portal GEUS, utilizando web scraping com Playwright e integração via API REST.

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Tecnologias](#tecnologias)
- [Arquitetura](#arquitetura)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Como Usar](#como-usar)
- [API Endpoints](#api-endpoints)
- [Módulos e Funções](#módulos-e-funções)
- [Fluxo de Processamento](#fluxo-de-processamento)
- [Tipos de Tarefas](#tipos-de-tarefas)
- [Tratamento de Erros](#tratamento-de-erros)
- [Utilitários](#utilitários)

## 🎯 Visão Geral

Este sistema automatiza o processamento de faturas da Energisa, realizando:

1. Busca de faturas via API do GEUS
2. Organização de dados por geradora e UC
3. Login automático no portal Energisa com verificação SMS
4. Navegação e extração de dados das faturas
5. Download de PDFs das faturas
6. Atualização dos dados no sistema GEUS

## 🛠️ Tecnologias

- **Python 3.x**: Linguagem principal
- **FastAPI**: Framework web assíncrono para API REST
- **Playwright**: Automação de navegador para web scraping
- **Requests**: Cliente HTTP para integração com APIs
- **python-dotenv**: Gerenciamento de variáveis de ambiente
- **IMAP**: Protocolo para recebimento de códigos SMS via email

## 🏗️ Arquitetura

### Fluxo Principal

```
API GEUS → Busca Faturas → Organiza por Geradora → Login Energisa
    ↓
Processa UCs → Extrai Dados → Download PDFs → Atualiza GEUS
```

### Componentes

- **API REST (FastAPI)**: Interface para iniciar processamentos
- **Robô (Playwright)**: Automação de navegação e extração
- **Integração API**: Comunicação com sistema GEUS
- **Processador de Tarefas**: Lógica de negócio para cada tipo de fatura

## 📁 Estrutura do Projeto

```
.
├── main.py                          # Servidor FastAPI com endpoints
├── robo.py                          # Orquestrador principal do processamento
├── config.py                        # Configurações e variáveis de ambiente
├── geradoras.py                     # CNPJs das geradoras cadastradas
├── mapeamento_cnpj_arquivos.py      # Utilitário de mapeamento
├── relatorio_execucao.py            # Gerador de relatórios
├── requirements.txt                 # Dependências do projeto
├── .env                             # Variáveis de ambiente (não versionado)
├── function/
│   ├── buscar_dados_api.py          # Busca e organização de faturas da API
│   ├── codigo_sms.py                # Obtenção de códigos SMS via email
│   ├── notificar_gestor.py          # Notificações de erro
│   └── tarefa.py                    # Processamento de faturas por tipo
└── media/
    └── json/                        # JSONs organizados por geradora (CNPJ)
```

## 🚀 Instalação

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd <nome-do-projeto>
```

### 2. Criar ambiente virtual

```bash
python -m venv venv
```

### 3. Ativar ambiente virtual

```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 4. Instalar dependências

```bash
pip install -r requirements.txt
```

### 5. Instalar navegadores do Playwright

```bash
playwright install chromium
```

## ⚙️ Configuração

### Variáveis de Ambiente (.env)

Crie um arquivo `.env` na raiz do projeto:

```env
# Modo de desenvolvimento
DEBUG_MODE=True

# Credenciais para receber SMS via email
CREDENTIAL_EMAIL_SMS=seu_email@exemplo.com
CREDENTIAL_PASSWORD_SMS=sua_senha
SERVER_HOST=imap.gmail.com

# API GEUS - Buscar Faturas
API_DOMAIN_FATURAS_PROD=https://api.geus.com.br/faturas
API_DOMAIN_FATURAS_DEV=https://api-dev.geus.com.br/faturas
API_CREDENTIAL_LOGIN=usuario_api
API_CREDENTIAL_PASSWORD=senha_api

# API GEUS - Criar/Atualizar Faturas
API_CRIAR_FATURA_DEV=https://api-dev.geus.com.br/criar-fatura
API_CRIAR_FATURA_PROD=https://api.geus.com.br/criar-fatura
API_ATUALIZAR_FATURA_DEV=https://api-dev.geus.com.br/atualizar-fatura
API_ATUALIZAR_FATURA_PROD=https://api.geus.com.br/atualizar-fatura
GEUS_APIKEY=sua_api_key_aqui
```

### Geradoras Cadastradas

As geradoras são definidas em `geradoras.py`:

```python
USINA_LUNA_CNPJ = "47.278.309/0001-01"
USINA_SULINA_CNPJ = "58.179.054/0001-46"
USINA_LB_CNPJ = "48.174.641/0001-99"
USINA_ENERGIAA_CNPJ = "29.698.168/0001-02"
USINA_LUZDIVINA_CNPJ = "59.981.267/0001-50"
USINA_G114_CNPJ = "52.028.408/0001-75"
```

## 💻 Como Usar

### Iniciar o Servidor FastAPI

```bash
python main.py
```

O servidor estará disponível em `http://localhost:8000`

### Executar Processamento Direto

```python
# Processar todas as geradoras
python robo.py

# Ou importar e usar funções específicas
from robo import processar_geradora_especifica
from geradoras import USINA_LUNA_CNPJ

processar_geradora_especifica(USINA_LUNA_CNPJ)
```

## 🌐 API Endpoints

### GET `/`
Informações da API e endpoints disponíveis

**Resposta:**
```json
{
  "message": "Energisa Busca API",
  "version": "1.0.0",
  "endpoints": {...}
}
```

### GET `/geradoras`
Lista todas as geradoras cadastradas

**Resposta:**
```json
{
  "total": 6,
  "geradoras": [
    "47.278.309/0001-01",
    "58.179.054/0001-46",
    ...
  ]
}
```

### POST `/start-search`
Inicia processamento de todas as geradoras em background

**Resposta:**
```json
{
  "message": "Processamento iniciado em background",
  "total_geradoras": 6,
  "geradoras": [...]
}
```

### POST `/start-search/{cnpjs}`
Inicia processamento de geradoras específicas

**Exemplos:**
- Uma geradora: `/start-search/47.278.309/0001-01`
- Múltiplas: `/start-search/47.278.309/0001-01AND58.179.054/0001-46`

**Resposta:**
```json
{
  "message": "Processamento de 2 geradoras iniciado em background",
  "geradoras": [...]
}
```

## 📦 Módulos e Funções

### `main.py` - Servidor FastAPI

**Funções principais:**
- `iniciar_busca_todas_geradoras()`: Endpoint para processar todas
- `iniciar_busca_geradoras(cnpjs)`: Endpoint para processar específicas
- `listar_geradoras()`: Lista geradoras disponíveis

### `robo.py` - Orquestrador

**Funções principais:**
- `processar_todas_geradoras()`: Processa todas as geradoras cadastradas
- `processar_multiplas_geradoras(cnpjs_lista)`: Processa lista específica
- `processar_geradora(geradora_cnpj)`: Processa uma geradora
- `processar_geradora_especifica(geradora_cnpj)`: Wrapper com busca de API
- `carregar_json_geradora(geradora_cnpj)`: Carrega dados do JSON

### `function/buscar_dados_api.py` - Integração API

**Funções principais:**
- `buscar_faturas()`: Busca faturas da API GEUS
- `organizar_faturas_por_geradora(faturas)`: Organiza dados por geradora/UC
- `salvar_json_por_geradora(geradoras_organizadas)`: Salva JSONs individuais
- `mapear_situacao_para_tarefa(situacao)`: Mapeia situação para tipo de tarefa

**Estrutura do JSON gerado:**
```json
{
  "geradora": "47278309000101",
  "lista_ucs": {
    "10/3463378-4": [
      {
        "id": 1263,
        "nova_uc": "10/3463378-4",
        "cnpj_geradora": "47.278.309/0001-01",
        "data_vencimento": "2025-08-31",
        "data_referencia": "08/2025",
        "valor": "182.19",
        "situacao_pagamento": "pendente",
        "tarefa": "fatura_pendente"
      }
    ]
  }
}
```

### `function/codigo_sms.py` - Códigos SMS

**Funções principais:**
- `obter_codigo_email()`: Busca código SMS no email via IMAP
- `obter_codigo_email_com_reenvio_automatico(page, timeout)`: Aguarda código com reenvio automático a cada 180s

**Funcionamento:**
1. Conecta ao servidor IMAP (Gmail)
2. Busca emails com assunto específico do SMSForwarder
3. Extrai código de 4 dígitos do corpo do email
4. Valida se o email é recente (últimos 30 segundos)
5. Reenvio automático se não receber em 180s

### `function/tarefa.py` - Processamento de Faturas

**Funções principais:**
- `processar_faturas_do_json(json_data, page)`: Processa todas as faturas do JSON
- `executar_fatura_pendente(nova_uc, mes_referencia, page, fatura_id)`: Processa fatura pendente
- `executar_fatura_vencida(nova_uc, mes_referencia, page, fatura_id, fatura_existente)`: Processa fatura vencida/a vencer
- `fazer_download_com_retry(page, download_button, nova_uc, mes_referencia)`: Download com retry e tratamento de erros

**Lógica de processamento:**
1. Busca card da fatura pelo mês de referência
2. Extrai dados (valor, vencimento, situação)
3. Detecta situação pelo CSS class
4. Faz download do PDF (com retry em caso de erro)
5. Converte PDF para base64
6. Envia para API GEUS

### `function/notificar_gestor.py` - Notificações

**Funções principais:**
- `fatura_nao_baixada()`: Notifica quando download falha após todas as tentativas

### `config.py` - Configurações

Carrega e disponibiliza todas as variáveis de ambiente do arquivo `.env`

### `geradoras.py` - CNPJs

Define constantes com CNPJs de todas as geradoras cadastradas

## 🔄 Fluxo de Processamento

### 1. Busca de Dados (API)

```python
buscar_faturas()
  ↓
organizar_faturas_por_geradora()
  ↓
salvar_json_por_geradora()
  ↓
media/json/{cnpj_numerico}.json
```

### 2. Login Automático

```python
Acessa portal Energisa
  ↓
Preenche CNPJ
  ↓
Seleciona telefone
  ↓
Aguarda SMS (com reenvio automático)
  ↓
Preenche código
  ↓
Login concluído
```

### 3. Processamento por UC

```python
Para cada UC:
  ↓
Navega para listagem de UCs
  ↓
Busca e seleciona UC
  ↓
Acessa página de faturas
  ↓
Expande "Mostrar mais faturas"
  ↓
Processa cada fatura da UC
  ↓
Próxima UC
```

### 4. Processamento de Fatura

```python
Busca card pelo mês de referência
  ↓
Extrai dados (valor, vencimento, situação)
  ↓
Verifica se precisa download (compara com dados existentes)
  ↓
Faz download do PDF (se necessário)
  ↓
Converte para base64
  ↓
Envia para API GEUS (criar ou atualizar)
```

## 🎯 Tipos de Tarefas

### Fatura Pendente (`fatura_pendente`)

**Situação:** Faturas com status "pendente" (primeira vez no sistema)

**Ação:**
1. Busca fatura no portal
2. Extrai todos os dados
3. Faz download do PDF
4. Envia dados completos para API

**Endpoint:** `API_CRIAR_FATURA`

**Payload:**
```json
{
  "id": 1263,
  "nova_uc": "10/3463378-4",
  "data_vencimento": "2025-08-31",
  "data_referencia": "08/2025",
  "valor": "182.19",
  "arquivo_fatura": "base64...",
  "nome_arquivo_fatura": "fatura_10_3463378-4_08_2025.pdf",
  "data_encontrada": "2025-11-07 14:30:00",
  "situacao_pagamento": "pendente",
  "situacao_energia_a": "sem_injecao",
  "tipo_tensao": null,
  "tipo_gd": null
}
```

### Fatura A Vencer (`fatura_a_vencer`)

**Situação:** Faturas com status "a_vencer"

**Ação:** Mesmo processamento de fatura pendente (verifica mudanças e atualiza)

**Endpoint:** `API_CRIAR_FATURA` ou `API_ATUALIZAR_FATURA`

### Fatura Vencida (`fatura_vencida`)

**Situação:** Faturas com status "vencida"

**Ação:**
1. Compara dados atuais com existentes
2. Se apenas situação mudou: atualiza só o status (sem download)
3. Se valor/vencimento mudou: faz download e envia dados completos

**Endpoint:** 
- `API_ATUALIZAR_FATURA` (só situação)
- `API_CRIAR_FATURA` (dados completos)

**Payload (só situação):**
```json
{
  "id": 1263,
  "situacao_pagamento": "paga"
}
```

## 🔍 Detecção de Status

O sistema identifica o status das faturas através das classes CSS do portal:

| Status | Classe CSS | Cor |
|--------|-----------|-----|
| Paga | `card-billing__top--green` | Verde |
| A Vencer | `card-billing__top--orange` | Laranja |
| Vencida | `card-billing__top--red` | Vermelho |

## ⚠️ Tratamento de Erros

### Retry de Download

O sistema tenta até 5 vezes fazer o download de uma fatura:

1. Clica no botão de download
2. Aguarda download ou modal de erro
3. Se modal de erro: fecha e tenta novamente
4. Se timeout: recarrega página e tenta novamente
5. Após 5 falhas: notifica gestor

### Erros Comuns

| Erro | Tratamento |
|------|-----------|
| JSON não encontrado | Pula para próxima geradora |
| Falha no login | Aborta processamento da geradora |
| UC não encontrada | Continua com próxima UC |
| Fatura não encontrada | Registra falha e continua |
| Erro na API | Registra falha mas continua |
| Modal de erro no download | Fecha modal e tenta novamente |

### Logs

O sistema fornece logs detalhados:

```
🚀 Iniciando processamento de 6 geradoras
📡 Buscando dados atualizados da API...
📊 Total de faturas encontradas na API: 245
🔍 Total de faturas após filtrar UCs vazias: 240
🏭 Geradoras encontradas: 6
✅ JSON carregado: media/json/47278309000101.json
📋 Encontradas 3 UCs para processar
🔐 Iniciando a etapa de Login
✅ Código recebido: 1234
✅ Login feito com sucesso!
🔄 Processando UC 1/3: 10/3463378-4
📊 Faturas para processar: 4
🎯 Iniciando processamento das faturas da UC 10/3463378-4
✓ Fatura encontrada para Agosto 2025
Situação de pagamento detectada: pendente
Valor: R$ 182.19
Vencimento: 31/08/2025 -> 2025-08-31
📥 Iniciando download da fatura...
✅ Download realizado com sucesso na tentativa 1
✅ Fatura enviada com sucesso para a API
✅ UC 10/3463378-4 processada: 4/4 faturas com sucesso
📊 Processamento de todas as geradoras concluído!
✅ Sucessos: 5
❌ Falhas: 1
📈 Taxa de sucesso: 83.3%
```

## 🛠️ Utilitários

### `mapeamento_cnpj_arquivos.py`

Exibe o mapeamento entre CNPJs e arquivos JSON gerados:

```bash
python mapeamento_cnpj_arquivos.py
```

**Saída:**
```
🏭 MAPEAMENTO CNPJ → ARQUIVO JSON
======================================================================
NOME                 | CNPJ                 | ARQUIVO JSON
----------------------------------------------------------------------
Usina Luna           | 47.278.309/0001-01   | 47278309000101.json
Usina Sulina         | 58.179.054/0001-46   | 58179054000146.json
...
```

### `relatorio_execucao.py`

Gera relatório detalhado da última execução:

```bash
python relatorio_execucao.py
```

**Saída:**
```
📊 RELATÓRIO DE EXECUÇÃO
============================================================
GERADORA                  | FATURAS |  UCs | SITUAÇÕES
------------------------------------------------------------
47278309000101            |      45 |   12 | pendente, vencida
58179054000146            |      38 |    9 | a_vencer, paga
...
============================================================
TOTAL: 240 faturas em 65 UCs
Distribuídas em 6 geradoras
```

## 🔐 Segurança

- Credenciais armazenadas em variáveis de ambiente (`.env`)
- Arquivo `.env` não versionado (incluído no `.gitignore`)
- Arquivos temporários de PDF removidos após conversão para base64
- Pausas entre processamentos para evitar sobrecarga do portal
- Tratamento seguro de erros sem exposição de dados sensíveis
- Autenticação via API Key para endpoints GEUS

## 📝 Manutenção

### Adicionar Nova Geradora

1. Adicione o CNPJ em `geradoras.py`:
```python
USINA_NOVA_CNPJ = "12.345.678/0001-90"
```

2. Adicione à lista em `robo.py`:
```python
geradoras_cnpjs = [
    USINA_LUNA_CNPJ,
    USINA_SULINA_CNPJ,
    # ...
    USINA_NOVA_CNPJ  # Nova geradora
]
```

3. Certifique-se que a geradora está cadastrada na API GEUS

### Debugging

- Use `DEBUG_MODE=True` no `.env` para ambiente de desenvolvimento
- Use `processar_geradora_especifica()` para testes individuais
- Verifique logs detalhados durante execução
- Use `headless=False` no Playwright para ver o navegador em ação

### Atualizar Seletores CSS

Se o portal Energisa mudar a estrutura HTML, atualize os seletores em `function/tarefa.py`:

```python
# Exemplo de seletores atuais
cards_date = page.locator('.card-billing__date')
situacao_element = card_completo.locator('.card-billing__top')
valor_element = card_completo.locator('.card-billing__price .min-w-\\[200px\\]')
```