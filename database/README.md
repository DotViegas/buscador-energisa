# Sistema de Banco de Dados SQLite - Controle de Faturas

## Visão Geral

Sistema de controle de processamento de faturas usando SQLite para evitar reprocessamento desnecessário e manter histórico de execuções.

## Estrutura do Banco

### Tabela: `faturas`
Controla o status de processamento de cada fatura.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | INTEGER | ID da fatura (chave primária) |
| nova_uc | TEXT | Número da UC |
| mes_referencia | TEXT | Mês no formato MM/AAAA |
| cnpj_geradora | TEXT | CNPJ da geradora |
| status | TEXT | Status: 'a_verificar', 'sucesso', 'erro' |
| data_criacao | DATETIME | Quando foi criado no banco |
| data_processamento | DATETIME | Quando foi processado |
| tentativas | INTEGER | Número de tentativas |
| mensagem_erro | TEXT | Mensagem de erro (se houver) |
| valor | TEXT | Valor da fatura |
| data_vencimento | TEXT | Data de vencimento |
| situacao_pagamento | TEXT | Situação: paga, vencida, a_vencer |

### Tabela: `execucoes_diarias`
Registra execuções diárias por UC para controle de tarefas.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| id | INTEGER | ID auto-incremento |
| data_execucao | DATE | Data da execução |
| cnpj_geradora | TEXT | CNPJ da geradora |
| nova_uc | TEXT | UC processada |
| total_faturas | INTEGER | Total de faturas |
| faturas_sucesso | INTEGER | Faturas com sucesso |
| faturas_erro | INTEGER | Faturas com erro |
| faturas_puladas | INTEGER | Faturas puladas |
| status_execucao | TEXT | 'completo', 'parcial', 'falha' |
| data_hora_inicio | DATETIME | Início do processamento |
| data_hora_fim | DATETIME | Fim do processamento |

## Status de Faturas

### `a_verificar`
- Faturas que ainda não foram processadas
- Serão processadas na próxima execução

### `sucesso`
- Faturas processadas com sucesso
- **NÃO serão reprocessadas** automaticamente

### `erro`
- Faturas que falharam no processamento
- **NÃO serão reprocessadas** automaticamente
- Use `--force` para reprocessar

## Fluxo de Funcionamento

### 1. Busca de Dados da API
```python
# Em buscar_dados_api.py
buscar_faturas()  # Busca da API e salva no banco com status 'a_verificar'
```

### 2. Processamento
```python
# Em robo.py
processar_geradora(cnpj)  # Processa apenas faturas com status 'a_verificar'
```

### 3. Atualização de Status
- Sucesso → status = 'sucesso'
- Erro → status = 'erro'
- Pulada → mantém status anterior

## Uso do Parâmetro --force

Para reprocessar faturas com erro:

```bash
# Reprocessar todas as faturas com erro
python robo.py --force

# Ou via batch
executar_robo.bat --force
```

## Utilitários de Gerenciamento

Use o script `db_utils.py` para gerenciar o banco:

### Inicializar banco
```bash
python db_utils.py init
```

### Ver estatísticas
```bash
# Estatísticas gerais
python db_utils.py stats

# Estatísticas de uma geradora específica
python db_utils.py stats "47.278.309/0001-01"
```

### Resetar faturas com erro
```bash
# Resetar todas as faturas com erro
python db_utils.py reset-errors

# Resetar erros de uma geradora específica
python db_utils.py reset-errors "47.278.309/0001-01"
```

### Ver execuções do dia
```bash
# Execuções de hoje
python db_utils.py execucoes

# Execuções de uma data específica
python db_utils.py execucoes 2026-03-27
```

### Limpar faturas antigas
```bash
# Remover faturas com sucesso há mais de 90 dias
python db_utils.py clean

# Remover faturas com sucesso há mais de 30 dias
python db_utils.py clean 30
```

## Localização do Banco

O arquivo do banco de dados fica em:
```
database/faturas.db
```

## Vantagens

✅ Evita reprocessamento de faturas já processadas com sucesso
✅ Não reprocessa faturas com erro automaticamente (evita loops)
✅ Mantém histórico de tentativas e erros
✅ Permite análise de performance diária por UC
✅ Controle fino com parâmetro --force
✅ Leve e sem dependências externas
