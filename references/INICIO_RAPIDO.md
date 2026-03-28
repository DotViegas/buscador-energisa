# 🚀 Início Rápido - Sistema de Banco de Dados

## ⚡ 3 Passos para Começar

### 1️⃣ Inicializar Banco (Primeira Vez)
```bash
python db_utils.py init
```

### 2️⃣ Executar Robô
```bash
python robo.py
```

### 3️⃣ Monitorar
```bash
python db_utils.py stats
```

Pronto! O sistema está funcionando. 🎉

---

## 📚 Quer Saber Mais?

### Guias por Nível

**🟢 Iniciante**
- `GUIA_BANCO_DADOS.md` - Como usar o sistema
- `COMANDOS_RAPIDOS.md` - Referência de comandos

**🟡 Intermediário**
- `EXEMPLOS_USO.md` - 10 cenários práticos
- `FLUXO_BANCO_DADOS.md` - Como funciona por dentro

**🔴 Avançado**
- `database/README.md` - Documentação técnica
- `IMPLEMENTACAO_BD.md` - Detalhes da implementação

**🔧 Gestão**
- `RESUMO_EXECUTIVO.md` - Visão executiva
- `CHECKLIST_VALIDACAO.md` - Validação e testes

---

## 🎯 Comandos Essenciais

```bash
# Ver estatísticas
python db_utils.py stats

# Ver erros
python visualizar_banco.py erros

# Reprocessar erros
python robo.py --force

# Ver execuções de hoje
python db_utils.py execucoes
```

---

## ❓ Perguntas Frequentes

**Preciso inicializar o banco toda vez?**
Não, apenas na primeira vez.

**O que é o --force?**
Permite reprocessar faturas que falharam.

**Faturas com sucesso são reprocessadas?**
Não, nunca. Isso economiza tempo.

**Como ver o que foi processado hoje?**
`python db_utils.py execucoes`

---

## 🎊 Tudo Pronto!

O sistema está implementado e testado. Comece com os 3 passos acima e explore a documentação conforme necessário.

**Boa sorte!** 🚀
