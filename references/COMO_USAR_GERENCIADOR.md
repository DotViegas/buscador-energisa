# Como Usar o Gerenciador de Faturas

## Script Único para Todas as Operações

Execute o script:

```bash
python gerenciar_faturas.py
```

## Menu de Opções

```
═══════════════════════════════════════════════════════════════════════════════
GERENCIAMENTO DE FATURAS - SISTEMA DE RELATÓRIOS
═══════════════════════════════════════════════════════════════════════════════

Você gostaria de fazer qual operação?

1 - Salvar relatório de hoje
2 - Salvar relatório com intervalo específico
3 - Verificar se existem faturas a_verificar
0 - Sair
```

## Opção 1: Relatório de Hoje

Gera automaticamente um arquivo XLSX com todas as faturas processadas hoje.

**Arquivo gerado:** `relatorio_faturas_DDMMYYYY.xlsx`

**Exemplo:** `relatorio_faturas_27032026.xlsx`

## Opção 2: Relatório com Intervalo

Permite escolher um período específico:

```
Data inicial: 20/03/2026
Data final: 27/03/2026
```

**Arquivo gerado:** `relatorio_faturas_20032026_a_27032026.xlsx`

## Opção 3: Verificar Faturas Pendentes

Mostra estatísticas de faturas que ainda precisam ser processadas:

- Total de faturas por status
- Faturas pendentes por geradora
- Opção de ver lista completa
- Alerta sobre faturas com erro

**Exemplo de saída:**

```
📊 DISTRIBUIÇÃO POR STATUS:
   a_verificar: 22 faturas
   erro: 1 faturas
   sucesso: 560 faturas

⚠️ Existem 22 faturas com status 'a_verificar'

📋 FATURAS PENDENTES POR GERADORA:
   250.262.911-04: 15 faturas
   58.179.054/0001-46: 7 faturas
```

## Estrutura do Relatório XLSX

Cada relatório contém 3 abas:

### 1. Resumo
- Estatísticas gerais (total, sucesso, erro, taxa)
- Distribuição por tipo de operação
- Estatísticas por geradora

### 2. Faturas Processadas
- Lista completa com todos os detalhes
- Cores: Verde (sucesso) / Vermelho (erro)

### 3. Execuções por UC
- Resumo do processamento por UC
- Duração de cada execução
- Cores: Verde (completo) / Amarelo (parcial) / Vermelho (falha)

## Requisitos

O script instala automaticamente a biblioteca `openpyxl` se necessário.

## Dicas

- Execute a opção 1 após cada execução do robô para ter histórico diário
- Use a opção 2 para relatórios semanais ou mensais
- Use a opção 3 antes de executar o robô para saber o que precisa processar
