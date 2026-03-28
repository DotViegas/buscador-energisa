# 💾 Guia Rápido - Sistema de Banco de Dados

## Como Funciona?

O sistema agora usa SQLite para controlar quais faturas já foram processadas, evitando reprocessamento desnecessário.

## 🚀 Início Rápido

### 1. Primeira vez? Inicialize o banco

```bash
python db_utils.py init
```

### 2. Execute normalmente

```bash
python robo.py
```

O sistema vai:
- ✅ Buscar faturas da API
- ✅ Salvar no banco com status `a_verificar`
- ✅ Processar apenas faturas novas ou pendentes
- ✅ Pular faturas já processadas com sucesso
- ✅ Pular faturas com erro (sem --force)

## 📊 Status das Faturas

### `a_verificar` (🟡)
Faturas que serão processadas na próxima execução

### `sucesso` (🟢)
Faturas processadas com sucesso - **não serão reprocessadas**

**Nota:** Inclui também UCs sem faturas no portal (marcadas com mensagem "UC sem faturas no portal")

### `erro` (🔴)
Faturas que falharam - **não serão reprocessadas sem --force**

## 🔄 Reprocessar Faturas com Erro

Se uma fatura falhou e você quer tentar novamente:

```bash
python robo.py --force
```

Ou via batch:
```bash
executar_robo.bat --force
```

## 🛠️ Comandos Úteis

### Ver estatísticas

```bash
# Estatísticas gerais
python db_utils.py stats

# Estatísticas de uma geradora específica
python db_utils.py stats "47.278.309/0001-01"
```

**Exemplo de saída:**
```
📊 Estatísticas gerais de todas as geradoras
  Total de faturas: 240
  A verificar: 15
  Sucesso: 220
  Erro: 5
```

### Resetar erros manualmente

Se você corrigiu um problema e quer reprocessar erros:

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

**Exemplo de saída:**
```
📅 Execuções do dia: 2026-03-27

  UC: 3622059 | Geradora: 47.278.309/0001-01
  Status: completo
  Total: 4 | Sucesso: 4 | Erro: 0 | Puladas: 0
  Início: 2026-03-27 07:00:03 | Fim: 2026-03-27 07:15:42
```

### Limpar banco de dados

Remove faturas antigas com sucesso (mantém erros e pendentes):

```bash
# Remover faturas com sucesso há mais de 90 dias
python db_utils.py clean

# Remover faturas com sucesso há mais de 30 dias
python db_utils.py clean 30
```

## 📝 Cenários Comuns

### Cenário 1: Execução Normal Diária

```bash
python robo.py
```

- Processa apenas faturas novas (`a_verificar`)
- Pula faturas já processadas
- Pula faturas com erro

### Cenário 2: Reprocessar Erros

```bash
python robo.py --force
```

- Processa faturas novas (`a_verificar`)
- Processa faturas com erro (`erro`)
- Pula faturas com sucesso

### Cenário 3: Resetar Erros Específicos

```bash
# 1. Resetar erros de uma geradora
python db_utils.py reset-errors "47.278.309/0001-01"

# 2. Executar normalmente (sem --force)
python robo.py
```

### Cenário 4: Monitorar Execuções

```bash
# Ver o que foi processado hoje
python db_utils.py execucoes

# Ver estatísticas atuais
python db_utils.py stats
```

## ⚠️ Importante

### Faturas com Sucesso
- **Nunca** serão reprocessadas automaticamente
- Isso evita downloads e processamentos desnecessários
- Se precisar reprocessar, remova do banco manualmente

### Faturas com Erro
- **Não** serão reprocessadas sem `--force`
- Isso evita loops infinitos de erro
- Use `--force` quando corrigir o problema
- Ou use `db_utils.py reset-errors` para resetar manualmente

### Primeira Execução
- Todas as faturas da API serão marcadas como `a_verificar`
- Serão processadas normalmente
- Após processamento, status será atualizado

## 🔍 Troubleshooting

### Banco não existe?
```bash
python db_utils.py init
```

### Muitas faturas com erro?
```bash
# Ver quais estão com erro
python db_utils.py stats

# Resetar para tentar novamente
python db_utils.py reset-errors
python robo.py
```

### Quer ver o histórico?
```bash
# Execuções de hoje
python db_utils.py execucoes

# Execuções de ontem
python db_utils.py execucoes 2026-03-26
```

### Banco muito grande?
```bash
# Limpar faturas antigas (mantém últimos 90 dias)
python db_utils.py clean
```

## 📍 Localização do Banco

```
database/faturas.db
```

Você pode abrir este arquivo com qualquer cliente SQLite para consultas avançadas.
