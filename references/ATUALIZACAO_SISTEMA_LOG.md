# Atualização do Sistema de Log de Operações

## Resumo das Mudanças

O sistema foi atualizado para registrar **detalhadamente** todas as operações realizadas em cada fatura, incluindo:

1. **Tipo de operação** realizada
2. **Log completo** da execução

## Novos Campos no Banco de Dados

### Tabela `faturas`

Foram adicionados 2 novos campos:

- **`tipo_operacao`** (TEXT): Registra qual operação foi realizada
- **`log_execucao`** (TEXT): Armazena o output completo do processamento

## Tipos de Operação

O campo `tipo_operacao` pode ter os seguintes valores:

| Tipo | Descrição |
|------|-----------|
| `nao_encontrada` | Fatura não foi localizada no portal da Energisa |
| `criada` | Fatura foi encontrada e enviada para API pela primeira vez |
| `atualizada` | Fatura existente teve múltiplos campos atualizados (valor, vencimento, situação) |
| `situacao_alterada` | Apenas a situação de pagamento foi alterada (ex: a_vencer → paga) |
| `sem_alteracao` | Fatura verificada mas sem mudanças detectadas |
| `erro` | Ocorreu erro durante o processamento |

## O que é Salvo no Log

O campo `log_execucao` contém **todo o output** do processamento da fatura, incluindo:

- UC processada
- ID e mês da fatura
- Cards encontrados na página
- Dados extraídos (valor, vencimento, situação)
- Resultado do download (se aplicável)
- Resposta da API
- Mensagens de erro (se houver)

### Exemplo de Log Salvo:

```
--- Processando UC: 3557293 ---
Processando fatura ID: 3505, Mês: 03/2026, Tarefa: fatura_pendente
Iniciando processamento de fatura pendente para UC: 3557293, Mês: 03/2026
Buscando fatura para o mês: 03/2026
Encontrados 9 cards de fatura na página
Card 1: Fevereiro 2026 (02/2026)
Card 2: Janeiro 2026 (01/2026)
Card 3: Dezembro 2025 (12/2025)
...
ℹ️ Fatura não localizada para o mês 03/2026 - situação normal
✅ Status da fatura ID 3505 atualizado para: sucesso | Operação: nao_encontrada
```

## Como Consultar os Logs

### Opção 1: Script de Consulta Interativo

```bash
python consultar_logs_faturas.py
```

Menu com opções para:
- Consultar fatura específica por ID
- Listar distribuição por tipo de operação
- Filtrar por tipo específico

### Opção 2: Consulta Direta por ID

```bash
python consultar_logs_faturas.py 3505
```

### Opção 3: SQL Direto

```python
import sqlite3

conn = sqlite3.connect('database/faturas.db')
cursor = conn.cursor()

# Consultar fatura específica
cursor.execute("""
    SELECT id, tipo_operacao, log_execucao 
    FROM faturas 
    WHERE id = ?
""", (3505,))

row = cursor.fetchone()
print(f"ID: {row[0]}")
print(f"Operação: {row[1]}")
print(f"Log:\n{row[2]}")

conn.close()
```

## Arquivos Modificados

1. **`database/models.py`**: Adicionados campos `tipo_operacao` e `log_execucao` na tabela
2. **`database/db_manager.py`**: Função `atualizar_status_fatura` atualizada para receber novos parâmetros
3. **`function/tarefa.py`**: 
   - Funções de processamento agora retornam tupla `(sucesso, tipo_operacao, dados_fatura)`
   - Sistema de captura de log implementado usando `io.StringIO`
4. **`robo.py`**: Atualizado para passar `tipo_operacao` e `log_execucao` ao marcar UCs sem faturas

## Arquivos Criados

1. **`migrar_banco.py`**: Script de migração para adicionar as novas colunas
2. **`consultar_logs_faturas.py`**: Script para consultar logs de forma fácil
3. **`testar_novo_sistema_log.py`**: Script de teste do novo sistema

## Como Usar

### 1. Migração (já executada)

```bash
python migrar_banco.py
```

### 2. Executar o Robô Normalmente

O robô agora salvará automaticamente:
- Tipo de operação realizada
- Log completo de cada fatura processada

### 3. Consultar Resultados

```bash
# Ver log de uma fatura específica
python consultar_logs_faturas.py 3505

# Menu interativo
python consultar_logs_faturas.py
```

## Benefícios

✅ **Rastreabilidade completa**: Cada fatura tem histórico detalhado do que aconteceu  
✅ **Debug facilitado**: Log completo disponível para análise de problemas  
✅ **Estatísticas precisas**: Saber quantas faturas foram criadas vs atualizadas vs não encontradas  
✅ **Auditoria**: Registro permanente de todas as operações realizadas  

## Tipos de Operação por Cenário

| Cenário | Tipo de Operação |
|---------|------------------|
| Fatura pendente não encontrada no portal | `nao_encontrada` |
| Fatura pendente encontrada e enviada | `criada` |
| Fatura vencida com mudança de valor/vencimento | `atualizada` |
| Fatura que mudou de "a_vencer" para "paga" | `situacao_alterada` |
| Fatura agendada que foi paga | `situacao_alterada` |
| Fatura verificada sem mudanças | `sem_alteracao` |
| Qualquer erro durante processamento | `erro` |
