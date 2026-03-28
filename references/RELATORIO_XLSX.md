# Gerador de Relatório XLSX

Script para gerar relatórios em Excel com os resultados do processamento de faturas.

## Instalação

A biblioteca `openpyxl` será instalada automaticamente na primeira execução, ou você pode instalar manualmente:

```bash
pip install openpyxl
```

## Como Usar

### Gerar relatório do dia atual

```bash
python gerar_relatorio_xlsx.py
```

### Gerar relatório de uma data específica

```bash
python gerar_relatorio_xlsx.py 2026-03-27
```

O formato da data deve ser: `YYYY-MM-DD`

## Estrutura do Relatório

O arquivo XLSX gerado contém 4 abas:

### 1. Resumo

Visão geral do processamento:
- **Estatísticas Gerais**: Total de faturas, sucessos, erros, taxa de sucesso
- **Por Tipo de Operação**: Distribuição de nao_encontrada, criada, atualizada, etc.
- **Por Geradora**: Estatísticas detalhadas por CNPJ

### 2. Faturas Processadas

Lista completa de todas as faturas processadas no dia com:
- ID, UC, Mês de Referência
- CNPJ da Geradora
- Status (sucesso/erro)
- Tipo de Operação
- Valor, Data de Vencimento, Situação de Pagamento
- Data de Processamento
- Número de Tentativas
- Mensagem de Erro (se houver)

**Cores:**
- 🟢 Verde: Sucesso
- 🔴 Vermelho: Erro

### 3. Execuções por UC

Resumo do processamento por UC:
- CNPJ e UC
- Total de faturas, sucessos, erros, puladas
- Status da execução (completo/parcial/falha)
- Hora de início e fim
- Duração do processamento

**Cores:**
- 🟢 Verde: Completo
- 🟡 Amarelo: Parcial
- 🔴 Vermelho: Falha

### 4. Logs Detalhados

Log completo da execução de cada fatura:
- ID, UC, Mês
- Tipo de Operação
- Status
- **Log Completo**: Todo o output do processamento

Esta aba é útil para debug e auditoria detalhada.

## Exemplo de Saída

```
✅ Relatório gerado com sucesso: relatorio_faturas_27032026.xlsx
📊 Total de faturas: 561
✅ Sucesso: 560
❌ Erro: 1
📈 Taxa de sucesso: 99.8%
```

## Nome do Arquivo

O arquivo é gerado com o padrão:
```
relatorio_faturas_DDMMYYYY.xlsx
```

Exemplo: `relatorio_faturas_27032026.xlsx`

## Tipos de Operação no Relatório

| Tipo | Significado |
|------|-------------|
| `nao_encontrada` | Fatura não existe no portal |
| `criada` | Fatura nova enviada para API |
| `atualizada` | Fatura com múltiplas mudanças |
| `situacao_alterada` | Apenas situação de pagamento mudou |
| `sem_alteracao` | Verificada mas sem mudanças |
| `erro` | Erro no processamento |

## Dicas

- Execute o relatório após cada execução do robô para ter registro histórico
- Use a aba "Logs Detalhados" para investigar problemas específicos
- A aba "Resumo" é ideal para apresentações gerenciais
- Os arquivos podem ser abertos no Excel, LibreOffice ou Google Sheets
