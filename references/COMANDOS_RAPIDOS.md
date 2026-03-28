# ⚡ Comandos Rápidos - Referência

## 🚀 Execução

```bash
# Execução normal
python robo.py

# Reprocessar erros
python robo.py --force

# Via batch
executar_robo.bat
executar_robo.bat --force
```

## 📊 Monitoramento

```bash
# Estatísticas gerais
python db_utils.py stats

# Estatísticas de uma geradora
python db_utils.py stats "47.278.309/0001-01"

# Ver faturas
python visualizar_banco.py faturas

# Ver apenas sucessos
python visualizar_banco.py sucesso

# Ver apenas pendentes
python visualizar_banco.py a_verificar

# Ver apenas erros
python visualizar_banco.py erros

# Execuções de hoje
python db_utils.py execucoes

# Execuções de data específica
python db_utils.py execucoes 2026-03-27
```

## 🔧 Manutenção

```bash
# Inicializar banco
python db_utils.py init

# Resetar todos os erros
python db_utils.py reset-errors

# Resetar erros de uma geradora
python db_utils.py reset-errors "47.278.309/0001-01"

# Limpar faturas antigas (90 dias)
python db_utils.py clean

# Limpar faturas antigas (30 dias)
python db_utils.py clean 30
```

## 🎮 Menu Interativo

```bash
# Abrir menu interativo
python visualizar_banco.py
```

## 🧪 Testes

```bash
# Testar sistema completo
python exemplo_uso_db.py

# Testar inicialização
python db_utils.py init

# Testar estatísticas
python db_utils.py stats
```

## 📖 Documentação

```bash
# Guia rápido
cat GUIA_BANCO_DADOS.md

# Exemplos práticos
cat EXEMPLOS_USO.md

# Fluxo detalhado
cat FLUXO_BANCO_DADOS.md

# Checklist de validação
cat CHECKLIST_VALIDACAO.md

# Resumo da implementação
cat IMPLEMENTACAO_BD.md

# Documentação técnica
cat database/README.md
```

## 🔍 Consultas SQL Diretas

```bash
# Abrir banco SQLite
sqlite3 database/faturas.db

# Consultas úteis:
SELECT COUNT(*) FROM faturas WHERE status = 'erro';
SELECT * FROM faturas WHERE nova_uc = '3622059';
SELECT * FROM execucoes_diarias WHERE data_execucao = '2026-03-27';
```

## 🆘 Troubleshooting Rápido

```bash
# Banco não existe?
python db_utils.py init

# Muitos erros?
python visualizar_banco.py erros
python db_utils.py reset-errors
python robo.py

# Banco muito grande?
python db_utils.py clean

# Ver o que aconteceu hoje?
python db_utils.py execucoes
```

## 📱 Atalhos Úteis

### Ver status geral rapidamente
```bash
python db_utils.py stats && python visualizar_banco.py erros
```

### Resetar e executar
```bash
python db_utils.py reset-errors && python robo.py
```

### Monitoramento completo
```bash
python db_utils.py stats && python db_utils.py execucoes && python visualizar_banco.py erros
```

---

💡 **Dica:** Salve este arquivo nos favoritos para acesso rápido aos comandos!
