"""
Definição das tabelas e estrutura do banco de dados
"""

import sqlite3
from datetime import datetime

def inicializar_banco(db_path="database/faturas.db"):
    """
    Cria as tabelas do banco de dados se não existirem
    
    Args:
        db_path (str): Caminho para o arquivo do banco de dados
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Tabela de faturas - controle de processamento
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faturas (
            id INTEGER PRIMARY KEY,
            nova_uc TEXT NOT NULL,
            mes_referencia TEXT NOT NULL,
            cnpj_geradora TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'a_verificar',
            data_criacao DATETIME NOT NULL,
            data_processamento DATETIME,
            tentativas INTEGER DEFAULT 0,
            mensagem_erro TEXT,
            valor TEXT,
            data_vencimento TEXT,
            situacao_pagamento TEXT,
            UNIQUE(id)
        )
    """)
    
    # Índices para melhorar performance de consultas
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_faturas_status 
        ON faturas(status)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_faturas_uc_mes 
        ON faturas(nova_uc, mes_referencia)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_faturas_geradora 
        ON faturas(cnpj_geradora)
    """)
    
    # Tabela de execuções diárias - controle de tarefas por dia
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS execucoes_diarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_execucao DATE NOT NULL,
            cnpj_geradora TEXT NOT NULL,
            nova_uc TEXT NOT NULL,
            total_faturas INTEGER DEFAULT 0,
            faturas_sucesso INTEGER DEFAULT 0,
            faturas_erro INTEGER DEFAULT 0,
            faturas_puladas INTEGER DEFAULT 0,
            status_execucao TEXT NOT NULL,
            data_hora_inicio DATETIME NOT NULL,
            data_hora_fim DATETIME,
            UNIQUE(data_execucao, cnpj_geradora, nova_uc)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_execucoes_data 
        ON execucoes_diarias(data_execucao)
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ Banco de dados inicializado com sucesso")
