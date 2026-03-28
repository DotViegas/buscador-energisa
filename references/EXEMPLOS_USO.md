# 📚 Exemplos Práticos de Uso do Sistema

## Cenário 1: Primeira Execução do Dia

```bash
# 1. Executar o robô normalmente
python robo.py
```

**O que acontece:**
- Busca faturas da API
- Salva novas faturas no banco com status `a_verificar`
- Processa apenas faturas novas ou pendentes
- Pula faturas já processadas com sucesso
- Pula faturas com erro anterior

**Resultado esperado:**
```
📡 Buscando dados da API...
📊 Total de faturas encontradas: 245

💾 Salvando no banco de dados...
   ℹ️ Fatura ID 1001 já existe no banco com status: sucesso
   ✅ Fatura ID 1246 inserida no banco (status: a_verificar)

🔄 Processando geradora 1/6
   ⏭️ Fatura ID 1001 já processada com SUCESSO - pulando
   ✅ Fatura ID 1246 processada com sucesso

📊 Resumo: 1 processada, 1 pulada
```

---

## Cenário 2: Fatura Falhou - Tentar Novamente

```bash
# 1. Ver quais faturas estão com erro
python visualizar_banco.py erros

# Saída:
# 🔴 FATURAS COM ERRO
# ID: 1247 | UC: 3622061 | Erro: Timeout no download

# 2. Reprocessar com --force
python robo.py --force
```

**O que acontece:**
- Processa faturas novas (`a_verificar`)
- **Também processa** faturas com erro (`erro`)
- Pula faturas com sucesso

---

## Cenário 3: Resetar Erros Específicos

```bash
# 1. Ver estatísticas de uma geradora
python db_utils.py stats "47.278.309/0001-01"

# Saída:
# Total: 45
# A verificar: 2
# Sucesso: 40
# Erro: 3

# 2. Resetar apenas erros desta geradora
python db_utils.py reset-errors "47.278.309/0001-01"

# Saída:
# 🔄 3 faturas resetadas para reprocessamento

# 3. Executar normalmente (sem --force)
python robo.py
```

**O que acontece:**
- As 3 faturas com erro foram resetadas para `a_verificar`
- Serão processadas normalmente na próxima execução

---

## Cenário 4: Monitorar Execuções Diárias

```bash
# Ver o que foi processado hoje
python db_utils.py execucoes

# Ver execuções de ontem
python db_utils.py execucoes 2026-03-26

# Ver execuções de uma semana atrás
python db_utils.py execucoes 2026-03-20
```

**Saída exemplo:**
```
📅 Execuções do dia: 2026-03-27

  UC: 3622059 | Geradora: 47.278.309/0001-01
  Status: completo
  Total: 4 | Sucesso: 4 | Erro: 0 | Puladas: 0
  Início: 2026-03-27 07:00:03 | Fim: 2026-03-27 07:15:42

  UC: 3622060 | Geradora: 47.278.309/0001-01
  Status: parcial
  Total: 3 | Sucesso: 2 | Erro: 1 | Puladas: 0
  Início: 2026-03-27 07:15:45 | Fim: 2026-03-27 07:25:12
```

---

## Cenário 5: Manutenção do Banco

```bash
# 1. Ver tamanho atual do banco
python db_utils.py stats

# Saída:
# Total de faturas: 5.240

# 2. Limpar faturas antigas (mantém últimos 90 dias)
python db_utils.py clean

# Saída:
# 🗑️ 3.120 faturas antigas removidas do banco

# 3. Verificar novamente
python db_utils.py stats

# Saída:
# Total de faturas: 2.120
```

---

## Cenário 6: Processar Geradora Específica

```bash
# Editar robo.py para processar apenas uma geradora
# Descomentar e ajustar:

# processar_geradora_especifica(USINA_LUNA_CNPJ)

python robo.py
```

---

## Cenário 7: Análise de Problemas

```bash
# 1. Ver todas as faturas com erro
python visualizar_banco.py erros

# 2. Ver detalhes de todas as faturas
python visualizar_banco.py faturas

# 3. Ver estatísticas por geradora
python db_utils.py stats "47.278.309/0001-01"
python db_utils.py stats "58.179.054/0001-46"
python db_utils.py stats "48.174.641/0001-99"
```

---

## Cenário 8: Agendamento Automático (Windows Task Scheduler)

### Execução Diária às 7h

```batch
REM Criar tarefa no Task Scheduler
REM Ação: executar_robo_automatico.bat
REM Gatilho: Diariamente às 7:00
```

**O que acontece:**
- Sistema executa automaticamente
- Processa apenas faturas novas
- Não reprocessa sucessos
- Não reprocessa erros (precisa intervenção manual)

### Execução com Force às 12h (se houver erros)

```batch
REM Criar segunda tarefa no Task Scheduler
REM Ação: executar_robo_automatico.bat --force
REM Gatilho: Diariamente às 12:00
REM Condição: Apenas se houver erros
```

---

## Cenário 9: Visualização Interativa

```bash
# Executar menu interativo
python visualizar_banco.py
```

**Menu:**
```
💾 VISUALIZADOR DO BANCO DE DADOS

Escolha uma opção:
  1 - Ver todas as faturas (últimas 50)
  2 - Ver apenas faturas a verificar
  3 - Ver apenas faturas com sucesso
  4 - Ver apenas faturas com erro
  5 - Ver execuções de hoje
  6 - Ver execuções de outra data
  0 - Sair
```

---

## Cenário 10: Integração com API

```bash
# Iniciar servidor FastAPI
python main.py

# Em outro terminal ou via Postman/curl:

# Processar todas as geradoras
curl -X POST http://localhost:8000/start-search

# Processar geradora específica
curl -X POST http://localhost:8000/start-search/47.278.309/0001-01

# Processar múltiplas geradoras
curl -X POST http://localhost:8000/start-search/47.278.309/0001-01AND58.179.054/0001-46
```

**Nota:** A API não suporta --force via endpoint. Use o script direto para isso.

---

## 🎯 Dicas e Boas Práticas

### Execução Diária
- Execute sem `--force` na primeira execução do dia
- Deixe o sistema pular faturas já processadas
- Monitore erros com `visualizar_banco.py erros`

### Tratamento de Erros
- Não use `--force` indiscriminadamente
- Investigue o motivo do erro antes de reprocessar
- Use `reset-errors` para resetar seletivamente

### Manutenção
- Execute `clean` mensalmente para manter banco leve
- Monitore estatísticas semanalmente
- Verifique execuções diárias para garantir que tarefas foram cumpridas

### Performance
- Banco SQLite é leve e rápido
- Índices otimizam consultas
- Limpeza periódica mantém performance

---

## ❓ FAQ

**P: O que acontece se eu executar sem inicializar o banco?**
R: O sistema inicializa automaticamente na primeira execução.

**P: Posso deletar o banco e começar do zero?**
R: Sim, delete `database/faturas.db` e execute `python db_utils.py init`.

**P: Como saber se uma fatura foi processada hoje?**
R: Use `python db_utils.py execucoes` para ver execuções de hoje.

**P: Faturas com sucesso podem ser reprocessadas?**
R: Não automaticamente. Você precisaria remover do banco manualmente.

**P: O --force reprocessa sucessos também?**
R: Não, apenas faturas com erro. Sucessos nunca são reprocessados.

**P: Posso usar o banco em produção?**
R: Sim, SQLite é adequado para este caso de uso. Para alta concorrência, considere PostgreSQL.


---

## Cenário 11: UC Sem Faturas no Portal

```bash
python robo.py
```

**O que acontece quando uma UC não tem faturas:**

```
🔄 Processando UC 1/180: 3761699
📊 Faturas para processar: 2
🔍 Verificando bloqueio de acesso...
✅ UC selecionada com sucesso
✅ Página de faturas carregada
UC sem faturas geradas no momento.

💾 Registrando no banco de dados...
   ✅ Fatura ID 1001 marcada como sucesso (UC sem faturas)
   ✅ Fatura ID 1002 marcada como sucesso (UC sem faturas)

📊 Execução da UC 3761699 registrada: completo
```

**Por que marcar como sucesso?**
- Não há nada para processar no portal
- Evita que fiquem como `a_verificar` eternamente
- Mensagem no banco indica o motivo: "UC sem faturas no portal"
- Permite identificar UCs novas ou inativas

**Como identificar no banco:**
```bash
# Ver faturas desta UC
python visualizar_banco.py faturas

# Saída:
# ID: 1001 | UC: 3761699 | Status: 🟢 sucesso
#    └─ Mensagem: UC sem faturas no portal
```
