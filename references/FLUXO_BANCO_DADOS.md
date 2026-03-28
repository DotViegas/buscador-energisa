# 🔄 Fluxo Detalhado do Sistema com Banco de Dados

## Diagrama do Fluxo

```
┌─────────────────────────────────────────────────────────────────┐
│                    INÍCIO DA EXECUÇÃO                            │
│                   python robo.py [--force]                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              1. INICIALIZAR BANCO DE DADOS                       │
│                  inicializar_banco()                             │
│         Cria tabelas se não existirem                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              2. BUSCAR FATURAS DA API                            │
│                  buscar_faturas()                                │
│         - Faz requisição GET na API GEUS                         │
│         - Recebe lista de faturas                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         3. ORGANIZAR E SALVAR NO BANCO                           │
│         organizar_faturas_por_geradora()                         │
│         salvar_json_por_geradora()                               │
│                                                                  │
│   Para cada fatura da API:                                       │
│   ┌──────────────────────────────────────────┐                  │
│   │ Verifica se já existe no banco           │                  │
│   │   ├─ SIM: Mantém status atual            │                  │
│   │   └─ NÃO: Insere com status 'a_verificar'│                  │
│   └──────────────────────────────────────────┘                  │
│                                                                  │
│   Salva JSON em media/json/{cnpj}.json                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         4. PROCESSAR CADA GERADORA                               │
│         processar_geradora(cnpj, force)                          │
│                                                                  │
│   ┌──────────────────────────────────────────┐                  │
│   │ Carrega JSON da geradora                 │                  │
│   │ Faz login no portal Energisa             │                  │
│   └──────────────────────────────────────────┘                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         5. PROCESSAR CADA UC                                     │
│         Para cada UC da geradora:                                │
│                                                                  │
│   ┌──────────────────────────────────────────┐                  │
│   │ Navega para listagem de UCs              │                  │
│   │ Seleciona a UC                            │                  │
│   │ Acessa página de faturas                  │                  │
│   └──────────────────────────────────────────┘                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         6. PROCESSAR CADA FATURA DA UC                           │
│         processar_faturas_do_json()                              │
│                                                                  │
│   Para cada fatura:                                              │
│   ┌──────────────────────────────────────────┐                  │
│   │ CONSULTA BANCO DE DADOS                  │                  │
│   │ verificar_status_fatura(id, force)       │                  │
│   │                                           │                  │
│   │ Status = 'sucesso'?                       │                  │
│   │   └─ SIM: ⏭️ PULA (não reprocessa)       │                  │
│   │                                           │                  │
│   │ Status = 'erro' E force = False?          │                  │
│   │   └─ SIM: ⏭️ PULA (precisa --force)      │                  │
│   │                                           │                  │
│   │ Status = 'erro' E force = True?           │                  │
│   │   └─ SIM: ✅ PROCESSA                     │                  │
│   │                                           │                  │
│   │ Status = 'a_verificar'?                   │                  │
│   │   └─ SIM: ✅ PROCESSA                     │                  │
│   └──────────────────────────────────────────┘                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         7. PROCESSAR FATURA (se não pulou)                       │
│                                                                  │
│   ┌──────────────────────────────────────────┐                  │
│   │ Busca card da fatura no portal           │                  │
│   │ Extrai dados (valor, vencimento, status) │                  │
│   │ Faz download do PDF (se necessário)      │                  │
│   │ Envia para API GEUS                       │                  │
│   └──────────────────────────────────────────┘                  │
│                                                                  │
│   Resultado:                                                     │
│   ├─ ✅ SUCESSO: atualiza_status('sucesso')                     │
│   └─ ❌ ERRO: atualiza_status('erro', mensagem)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         8. REGISTRAR EXECUÇÃO DA UC                              │
│         registrar_execucao_uc()                                  │
│                                                                  │
│   Salva em execucoes_diarias:                                    │
│   - Data de execução                                             │
│   - UC processada                                                │
│   - Total de faturas                                             │
│   - Sucessos, erros, puladas                                     │
│   - Status: completo/parcial/falha                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         9. PRÓXIMA UC / GERADORA                                 │
│         Repete processo até finalizar todas                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FIM DA EXECUÇÃO                               │
│         Relatório final com estatísticas                         │
└─────────────────────────────────────────────────────────────────┘
```

## 🔍 Decisões de Processamento

### Matriz de Decisão

| Status no BD | --force | Ação | Motivo |
|--------------|---------|------|--------|
| `a_verificar` | Não | ✅ Processa | Fatura nova ou pendente |
| `a_verificar` | Sim | ✅ Processa | Fatura nova ou pendente |
| `sucesso` | Não | ⏭️ Pula | Já foi processada |
| `sucesso` | Sim | ⏭️ Pula | Já foi processada |
| `erro` | Não | ⏭️ Pula | Evita loop de erro |
| `erro` | Sim | ✅ Processa | Forçar reprocessamento |
| `nao_encontrada` | Não | ✅ Processa | Primeira vez |
| `nao_encontrada` | Sim | ✅ Processa | Primeira vez |

## 📊 Exemplo de Execução

### Primeira Execução (Banco Vazio)

```
📡 Buscando dados da API...
📊 Total de faturas encontradas: 240

💾 Salvando no banco de dados...
   ✅ Fatura ID 1001 inserida no banco (status: a_verificar)
   ✅ Fatura ID 1002 inserida no banco (status: a_verificar)
   ... (240 faturas)

🔄 Processando geradora 1/6: 47.278.309/0001-01
--- Processando UC: 3622059 ---
Processando fatura ID: 1001, Mês: 03/2026, Tarefa: fatura_pendente
   🔍 Status no BD: a_verificar - PROCESSANDO
   ✅ Fatura processada com sucesso
   ✅ Status atualizado para: sucesso

Processando fatura ID: 1002, Mês: 02/2026, Tarefa: fatura_vencida
   🔍 Status no BD: a_verificar - PROCESSANDO
   ✅ Fatura processada com sucesso
   ✅ Status atualizado para: sucesso

📊 Execução da UC 3622059 registrada: completo
```

### Segunda Execução (Banco Populado)

```
📡 Buscando dados da API...
📊 Total de faturas encontradas: 245 (5 novas)

💾 Salvando no banco de dados...
   ℹ️ Fatura ID 1001 já existe no banco com status: sucesso
   ℹ️ Fatura ID 1002 já existe no banco com status: sucesso
   ✅ Fatura ID 1246 inserida no banco (status: a_verificar)
   ... (5 novas faturas)

🔄 Processando geradora 1/6: 47.278.309/0001-01
--- Processando UC: 3622059 ---
Processando fatura ID: 1001, Mês: 03/2026, Tarefa: fatura_pendente
   ⏭️ Fatura ID 1001 já processada com SUCESSO - pulando

Processando fatura ID: 1002, Mês: 02/2026, Tarefa: fatura_vencida
   ⏭️ Fatura ID 1002 já processada com SUCESSO - pulando

Processando fatura ID: 1246, Mês: 04/2026, Tarefa: fatura_pendente
   🔍 Status no BD: a_verificar - PROCESSANDO
   ✅ Fatura processada com sucesso
   ✅ Status atualizado para: sucesso

📊 Resumo do processamento:
Total de faturas: 3
Processadas com sucesso: 1
Puladas: 2
Falhas: 0
```

### Execução com Erro e --force

```
# Primeira tentativa (fatura falha)
Processando fatura ID: 1247, Mês: 05/2026
   🔍 Status no BD: a_verificar - PROCESSANDO
   ❌ Erro ao fazer download
   ❌ Status atualizado para: erro

# Segunda execução SEM --force
python robo.py

Processando fatura ID: 1247, Mês: 05/2026
   ⏭️ Fatura ID 1247 com ERRO anterior - pulando (use --force para reprocessar)

# Terceira execução COM --force
python robo.py --force

⚠️ Modo FORCE ativado - faturas com erro serão reprocessadas

Processando fatura ID: 1247, Mês: 05/2026
   🔍 Status no BD: erro - REPROCESSANDO (force ativado)
   ✅ Fatura processada com sucesso
   ✅ Status atualizado para: sucesso
```

## 🎯 Benefícios do Sistema

### Eficiência
- ✅ Não reprocessa faturas já processadas
- ✅ Economiza tempo e recursos
- ✅ Reduz carga no portal Energisa

### Confiabilidade
- ✅ Não entra em loop de erros
- ✅ Mantém histórico de tentativas
- ✅ Permite reprocessamento controlado

### Rastreabilidade
- ✅ Histórico completo de execuções
- ✅ Estatísticas por geradora
- ✅ Controle diário de tarefas

### Manutenção
- ✅ Fácil identificar problemas
- ✅ Resetar erros seletivamente
- ✅ Limpar dados antigos
