# ✅ Checklist de Validação do Sistema de Banco de Dados

Use este checklist para validar que o sistema está funcionando corretamente.

## 🔧 Instalação e Configuração

- [ ] Banco de dados inicializado
  ```bash
  python db_utils.py init
  ```
  Resultado esperado: "✅ Banco de dados inicializado com sucesso!"

- [ ] Arquivo `database/faturas.db` foi criado
  ```bash
  ls database/faturas.db
  ```

- [ ] Exemplo de uso executado com sucesso
  ```bash
  python exemplo_uso_db.py
  ```
  Resultado esperado: "✅ EXEMPLO CONCLUÍDO COM SUCESSO!"

## 📊 Testes de Funcionalidade

### Teste 1: Estatísticas
- [ ] Comando de estatísticas funciona
  ```bash
  python db_utils.py stats
  ```
  Resultado esperado: Mostra total, a_verificar, sucesso, erro

### Teste 2: Visualização de Faturas
- [ ] Visualizador de faturas funciona
  ```bash
  python visualizar_banco.py faturas
  ```
  Resultado esperado: Lista de faturas formatada

### Teste 3: Visualização de Erros
- [ ] Visualizador de erros funciona
  ```bash
  python visualizar_banco.py erros
  ```
  Resultado esperado: Lista de faturas com erro

### Teste 4: Execuções Diárias
- [ ] Comando de execuções funciona
  ```bash
  python db_utils.py execucoes
  ```
  Resultado esperado: Lista de execuções do dia

## 🔄 Testes de Integração

### Teste 5: Busca de API com Banco
- [ ] Buscar faturas salva no banco
  ```python
  from function.buscar_dados_api import buscar_faturas
  buscar_faturas()
  ```
  Resultado esperado: Faturas inseridas no banco com status `a_verificar`

### Teste 6: Processamento com Verificação
- [ ] Sistema verifica banco antes de processar
  ```bash
  python robo.py
  ```
  Resultado esperado: 
  - Faturas com sucesso são puladas
  - Faturas com erro são puladas (sem --force)
  - Faturas a_verificar são processadas

### Teste 7: Parâmetro --force
- [ ] Sistema reprocessa erros com --force
  ```bash
  python robo.py --force
  ```
  Resultado esperado: Faturas com erro são reprocessadas

## 🎯 Testes de Regras de Negócio

### Teste 8: Fatura com Sucesso
- [ ] Fatura processada com sucesso não é reprocessada
  1. Processar uma fatura (deve ter sucesso)
  2. Executar novamente
  3. Verificar que foi pulada

### Teste 9: Fatura com Erro (sem --force)
- [ ] Fatura com erro não é reprocessada sem --force
  1. Simular erro em uma fatura
  2. Executar sem --force
  3. Verificar que foi pulada

### Teste 10: Fatura com Erro (com --force)
- [ ] Fatura com erro é reprocessada com --force
  1. Ter uma fatura com erro no banco
  2. Executar com --force
  3. Verificar que foi processada

### Teste 11: Reset de Erros
- [ ] Reset de erros funciona
  ```bash
  python db_utils.py reset-errors
  ```
  Resultado esperado: Faturas com erro voltam para `a_verificar`

### Teste 12: Registro de Execução
- [ ] Execução é registrada por UC
  1. Processar uma UC
  2. Verificar registro em execucoes_diarias
  ```bash
  python db_utils.py execucoes
  ```

## 🧹 Testes de Manutenção

### Teste 13: Limpeza de Dados Antigos
- [ ] Limpeza remove apenas sucessos antigos
  ```bash
  python db_utils.py clean 0
  ```
  Resultado esperado: Remove faturas com sucesso, mantém erros e pendentes

### Teste 14: Estatísticas por Geradora
- [ ] Estatísticas por geradora funcionam
  ```bash
  python db_utils.py stats "47.278.309/0001-01"
  ```
  Resultado esperado: Estatísticas específicas da geradora

## 🔍 Validação de Dados

### Teste 15: Integridade dos Dados
- [ ] Dados no banco correspondem aos JSONs
  1. Verificar quantidade de faturas no JSON
  2. Verificar quantidade no banco
  3. Devem ser iguais

### Teste 16: Status Corretos
- [ ] Status são atualizados corretamente
  1. Processar fatura com sucesso → status = `sucesso`
  2. Processar fatura com erro → status = `erro`
  3. Nova fatura da API → status = `a_verificar`

## 📝 Checklist de Produção

Antes de usar em produção:

- [ ] Banco de dados inicializado
- [ ] Todos os testes acima passaram
- [ ] Documentação revisada
- [ ] Backup do banco configurado (opcional)
- [ ] Agendamento configurado (Task Scheduler)
- [ ] Monitoramento configurado (visualizar_banco.py)
- [ ] Equipe treinada no uso do --force
- [ ] Processo de reset de erros documentado

## 🎉 Validação Final

Execute este comando para validar tudo de uma vez:

```bash
# 1. Inicializar
python db_utils.py init

# 2. Testar exemplo
python exemplo_uso_db.py

# 3. Ver estatísticas
python db_utils.py stats

# 4. Ver faturas
python visualizar_banco.py faturas

# 5. Ver erros
python visualizar_banco.py erros

# 6. Ver execuções
python db_utils.py execucoes
```

Se todos os comandos acima executarem sem erro, o sistema está pronto para uso! ✅

## 🆘 Troubleshooting

### Erro: "No module named 'database'"
**Solução:** Certifique-se que a pasta `database/` existe e tem `__init__.py`

### Erro: "unable to open database file"
**Solução:** Execute `python db_utils.py init` para criar o banco

### Erro: "no such table: faturas"
**Solução:** Execute `python db_utils.py init` para criar as tabelas

### Banco corrompido
**Solução:** 
```bash
# Backup (se necessário)
copy database\faturas.db database\faturas.db.backup

# Deletar e recriar
del database\faturas.db
python db_utils.py init
```
