# 📅 Guia de Agendamento - Busca de Faturas Energisa

## 📦 Arquivos Criados

### 🤖 Para Execução AUTOMÁTICA (Agendador de Tarefas)
1. **executar_robo_automatico.bat** - ⭐ **RECOMENDADO** - Finaliza sozinho
2. **executar_robo_automatico.vbs** - Versão VBS que finaliza sozinho

### 👀 Para Execução MANUAL (com pause para ver resultado)
3. **executar_robo.bat** - Com pause no final
4. **executar_robo_visivel.vbs** - Com pause no final
5. **executar_robo.ps1** - PowerShell com pause no final

## 🪟 Qual Script Usar?

### ⭐ executar_robo_automatico.bat (RECOMENDADO para Agendador)
- ✅ **Finaliza automaticamente** sem travar
- ✅ Perfeito para execução agendada
- ✅ Não precisa pressionar tecla
- ✅ Permite múltiplas execuções sem conflito
- 🎯 **USE ESTE no Agendador de Tarefas!**

### executar_robo_automatico.vbs (Alternativa com janela visível)
- ✅ Finaliza automaticamente
- ✅ Mostra a janela durante execução
- ✅ Fecha sozinho ao terminar
- 🎯 Use se quiser VER a execução mas ainda assim finalizar automaticamente

### executar_robo.bat (Apenas para testes manuais)
- ⚠️ **NÃO use no Agendador** - fica travado esperando tecla
- ✅ Bom para testes manuais
- ✅ Permite ver o resultado antes de fechar

### executar_robo_visivel.vbs (Apenas para testes manuais)
- ⚠️ **NÃO use no Agendador** - fica travado esperando tecla
- ✅ Força janela a aparecer
- ✅ Bom para debug manual

## ✅ Pré-requisitos

1. Ambiente virtual Python configurado na pasta `venv`
2. Todas as dependências instaladas (`pip install -r requirements.txt`)
3. Arquivo `.env` configurado corretamente
4. Scripts de execução criados (já estão prontos!)

## 🕐 Horários Configurados

- **Manhã**: 07:00 (GMT-4 / Horário de Brasília)
- **Tarde**: 18:00 (GMT-4 / Horário de Brasília)

## 📋 Passo a Passo - Agendador de Tarefas do Windows

### 1. Abrir o Agendador de Tarefas

- Pressione `Win + R`
- Digite: `taskschd.msc`
- Pressione Enter

### 2. Criar Nova Tarefa

1. No painel direito, clique em **"Criar Tarefa..."** (não use "Criar Tarefa Básica")
2. Na janela que abrir, configure as abas conforme abaixo:

### 3. Aba "Geral"

- **Nome**: `Energisa - Busca Faturas`
- **Descrição**: `Busca automática de faturas no portal Energisa`
- **Opções de segurança**:
  - ✅ Marque: "Executar estando o usuário conectado ou não"
  - ⚠️ **NÃO marque** "Executar com privilégios mais altos" (para a janela aparecer)
  - ⚠️ **IMPORTANTE**: Você precisará digitar sua senha do Windows ao salvar

> **💡 DICA**: Se você marcar "Executar com privilégios mais altos", a janela não aparecerá por questões de segurança do Windows. Deixe desmarcado se quiser ver a execução.

### 4. Aba "Disparadores"

Você precisa criar **DOIS disparadores** (um para manhã, outro para tarde):

#### Disparador 1 - Manhã (07:00)

1. Clique em **"Novo..."**
2. Configure:
   - **Iniciar a tarefa**: "Segundo um agendamento"
   - **Configurações**: "Diariamente"
   - **Recorrência**: A cada 1 dia
   - **Hora**: `07:00:00`
   - ✅ Marque: "Habilitado"
3. Clique em **"OK"**

#### Disparador 2 - Tarde (18:00)

1. Clique em **"Novo..."** novamente
2. Configure:
   - **Iniciar a tarefa**: "Segundo um agendamento"
   - **Configurações**: "Diariamente"
   - **Recorrência**: A cada 1 dia
   - **Hora**: `18:00:00`
   - ✅ Marque: "Habilitado"
3. Clique em **"OK"**

### 5. Aba "Ações"

1. Clique em **"Novo..."**
2. Configure:
   - **Ação**: "Iniciar um programa"
   
   **⭐ RECOMENDADO - Execução Automática (finaliza sozinho):**
   - **Programa/script**: Selecione `executar_robo_automatico.bat`
   - **Iniciar em (opcional)**: Coloque o caminho completo da pasta do projeto
     - Exemplo: `C:\Users\SeuUsuario\projetos\energisa-busca`
   
   **Alternativa - Com janela visível mas automático:**
   - **Programa/script**: Selecione `executar_robo_automatico.vbs`
   - **Iniciar em (opcional)**: Deixe em branco
   
   > **⚠️ IMPORTANTE**: Use os arquivos com "_automatico" no nome! Os outros ficam travados esperando você pressionar uma tecla.

3. Clique em **"OK"**

### 6. Aba "Condições"

Configure para garantir execução mesmo em bateria (se for notebook):

- **Energia**:
  - ❌ Desmarque: "Iniciar a tarefa apenas se o computador estiver conectado à energia CA"
  - ❌ Desmarque: "Parar se o computador passar a ser alimentado por bateria"

### 7. Aba "Configurações"

- ✅ Marque: "Permitir que a tarefa seja executada sob demanda"
- ✅ Marque: "Executar tarefa assim que possível após uma inicialização agendada ter sido perdida"
- **Se a tarefa já estiver em execução**: Selecione "Não iniciar uma nova instância"
- ❌ Desmarque: "Ocultar" (para ver a janela de execução)

> **💡 IMPORTANTE**: Para ver a janela durante a execução, você precisa:
> 1. Estar logado no Windows no momento da execução
> 2. NÃO marcar "Executar com privilégios mais altos" na aba Geral
> 3. NÃO marcar "Ocultar" na aba Configurações

### 8. Salvar

1. Clique em **"OK"**
2. Digite sua senha do Windows quando solicitado
3. Confirme

## 🧪 Testar o Agendamento

### Teste Manual

1. No Agendador de Tarefas, localize sua tarefa na lista
2. Clique com botão direito sobre ela
3. Selecione **"Executar"**
4. Verifique se o script está rodando corretamente
5. Confira os logs na pasta `logs/`

## 🪟 Visualizar a Janela de Execução

Para ver a janela CMD/PowerShell durante a execução automática:

### ✅ Configurações Necessárias:

1. **Na aba "Geral"**:
   - ❌ NÃO marque "Executar com privilégios mais altos"
   - ✅ Marque "Executar somente quando o usuário estiver conectado"

2. **Na aba "Configurações"**:
   - ❌ NÃO marque "Ocultar"

3. **Você precisa estar logado** no Windows no horário da execução

### ⚠️ Limitações:

- Se você marcar "Executar estando o usuário conectado ou não", a janela NÃO aparecerá (é uma limitação de segurança do Windows)
- Se você não estiver logado, a tarefa executará em segundo plano (mas ainda gerará logs)

### 💡 Recomendação:

**Opção 1 - Ver a janela (requer estar logado)**:
- Marque: "Executar somente quando o usuário estiver conectado"
- Não marque: "Executar com privilégios mais altos"
- Não marque: "Ocultar"
- **Vantagem**: Você vê tudo acontecendo em tempo real
- **Desvantagem**: Só funciona se você estiver logado

**Opção 2 - Execução silenciosa (funciona sempre)**:
- Marque: "Executar estando o usuário conectado ou não"
- Marque: "Executar com privilégios mais altos"
- **Vantagem**: Funciona mesmo se você não estiver logado
- **Desvantagem**: Não mostra janela (mas gera logs completos)

### Verificar Logs

Os logs são salvos automaticamente em:
```
logs/DDMMAAAA-HHMMSS.txt
```

Exemplo: `logs/12012026-070015.txt` (executado em 12/01/2026 às 07:00:15)

## 🔍 Verificar Status da Tarefa

1. Abra o Agendador de Tarefas
2. Localize sua tarefa
3. Na parte inferior, veja a aba **"Histórico"**
4. Verifique:
   - ✅ Última execução
   - ✅ Próxima execução
   - ✅ Status (Êxito/Falha)

## ⚠️ Solução de Problemas

### ❌ Tarefa fica travada e não executa novamente

**Sintoma**: A tarefa executa uma vez mas não roda nos próximos horários agendados.

**Causa**: Você está usando o script COM pause (`executar_robo.bat` ou `executar_robo_visivel.vbs`), que fica esperando você pressionar uma tecla.

**Solução**:
1. Abra o Agendador de Tarefas
2. Clique com botão direito na tarefa > Propriedades
3. Vá na aba "Ações"
4. Edite a ação e troque para: `executar_robo_automatico.bat` ou `executar_robo_automatico.vbs`
5. Clique OK

**Como verificar se está travada**:
- Abra o Gerenciador de Tarefas (Ctrl+Shift+Esc)
- Procure por processos `python.exe` ou `cmd.exe` rodando há muito tempo
- Se encontrar, finalize-os antes de testar novamente

### Tarefa não executa

1. **Verifique se o computador está ligado** nos horários agendados
2. **Verifique as credenciais**: Clique com botão direito na tarefa > Propriedades > Geral
3. **Teste manual**: Execute a tarefa manualmente para ver se há erros

### Erro ao executar

1. **Verifique o caminho**: Certifique-se que o caminho do `.bat` está correto
2. **Teste o .bat manualmente**: Dê duplo clique no `executar_robo.bat` e veja se funciona
3. **Verifique o ambiente virtual**: Certifique-se que a pasta `venv` existe

### Logs não são gerados

1. Verifique se a pasta `logs/` existe
2. Execute o script manualmente para testar
3. Verifique permissões de escrita na pasta

## 📝 Comandos Úteis

### Testar o script manualmente

Abra o CMD na pasta do projeto e execute:
```cmd
executar_robo.bat
```

### Ver tarefas agendadas via CMD

```cmd
schtasks /query /tn "Energisa - Busca Faturas" /v /fo list
```

### Desabilitar tarefa temporariamente

```cmd
schtasks /change /tn "Energisa - Busca Faturas" /disable
```

### Habilitar tarefa novamente

```cmd
schtasks /change /tn "Energisa - Busca Faturas" /enable
```

## 🎯 Dicas Importantes

1. **Mantenha o computador ligado** nos horários agendados
2. **Não mova a pasta do projeto** após configurar o agendamento
3. **Verifique os logs regularmente** para garantir que está funcionando
4. **Teste antes de confiar**: Execute manualmente algumas vezes antes de depender do agendamento
5. **Backup do .env**: Mantenha backup das suas credenciais

## 🔄 Atualizar Horários

Se precisar mudar os horários:

1. Abra o Agendador de Tarefas
2. Clique com botão direito na tarefa
3. Selecione **"Propriedades"**
4. Vá na aba **"Disparadores"**
5. Selecione o disparador que quer editar
6. Clique em **"Editar..."**
7. Altere o horário
8. Clique em **"OK"** em todas as janelas

## 📞 Suporte

Se tiver problemas:

1. Verifique os logs em `logs/`
2. Execute o `.bat` manualmente para ver erros
3. Verifique se todas as dependências estão instaladas
4. Confirme que o `.env` está configurado corretamente
