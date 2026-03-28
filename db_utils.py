"""
Utilitário para gerenciar o banco de dados de faturas
Uso: python db_utils.py [comando] [argumentos]

Comandos disponíveis:
  init                    - Inicializa o banco de dados
  stats [cnpj]           - Mostra estatísticas (geral ou por geradora)
  reset-errors [cnpj]    - Reseta faturas com erro para reprocessamento
  execucoes [data]       - Lista execuções do dia (formato: YYYY-MM-DD)
  clean [dias]           - Remove faturas antigas (padrão: 90 dias)
"""

import sys
from datetime import date, datetime
from database import DatabaseManager, inicializar_banco

def comando_init():
    """Inicializa o banco de dados"""
    print("💾 Inicializando banco de dados...")
    inicializar_banco()
    print("✅ Banco de dados inicializado com sucesso!")

def comando_stats(cnpj_geradora=None):
    """Mostra estatísticas de processamento"""
    db = DatabaseManager()
    
    if cnpj_geradora:
        print(f"\n📊 Estatísticas da geradora: {cnpj_geradora}")
        stats = db.obter_estatisticas_geradora(cnpj_geradora)
    else:
        print("\n📊 Estatísticas gerais de todas as geradoras")
        # Buscar estatísticas gerais
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'a_verificar' THEN 1 ELSE 0 END) as a_verificar,
                SUM(CASE WHEN status = 'sucesso' THEN 1 ELSE 0 END) as sucesso,
                SUM(CASE WHEN status = 'erro' THEN 1 ELSE 0 END) as erro
            FROM faturas
        """)
        
        row = cursor.fetchone()
        stats = dict(row) if row else {}
        conn.close()
    
    print(f"  Total de faturas: {stats.get('total', 0)}")
    print(f"  A verificar: {stats.get('a_verificar', 0)}")
    print(f"  Sucesso: {stats.get('sucesso', 0)}")
    print(f"  Erro: {stats.get('erro', 0)}")

def comando_reset_errors(cnpj_geradora=None):
    """Reseta faturas com erro para reprocessamento"""
    db = DatabaseManager()
    
    if cnpj_geradora:
        print(f"\n🔄 Resetando faturas com erro da geradora: {cnpj_geradora}")
        resetados = db.resetar_status_erro(cnpj_geradora=cnpj_geradora)
    else:
        print("\n🔄 Resetando TODAS as faturas com erro")
        resetados = db.resetar_status_erro()
    
    print(f"✅ {resetados} faturas resetadas para reprocessamento")

def comando_execucoes(data_str=None):
    """Lista execuções de um dia específico"""
    db = DatabaseManager()
    
    if data_str:
        try:
            data_execucao = datetime.strptime(data_str, "%Y-%m-%d").date()
        except ValueError:
            print("❌ Formato de data inválido. Use: YYYY-MM-DD")
            return
    else:
        data_execucao = date.today()
    
    print(f"\n📅 Execuções do dia: {data_execucao}")
    execucoes = db.obter_execucoes_do_dia(data_execucao)
    
    if not execucoes:
        print("  Nenhuma execução encontrada para esta data")
        return
    
    for exec in execucoes:
        print(f"\n  UC: {exec['nova_uc']} | Geradora: {exec['cnpj_geradora']}")
        print(f"  Status: {exec['status_execucao']}")
        print(f"  Total: {exec['total_faturas']} | Sucesso: {exec['faturas_sucesso']} | Erro: {exec['faturas_erro']} | Puladas: {exec['faturas_puladas']}")
        print(f"  Início: {exec['data_hora_inicio']} | Fim: {exec['data_hora_fim']}")

def comando_clean(dias=90):
    """Remove faturas antigas do banco"""
    db = DatabaseManager()
    
    print(f"\n🗑️ Removendo faturas com sucesso processadas há mais de {dias} dias...")
    removidos = db.limpar_faturas_antigas(dias)
    print(f"✅ {removidos} registros removidos")

def mostrar_ajuda():
    """Mostra ajuda de uso"""
    print(__doc__)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        mostrar_ajuda()
        sys.exit(0)
    
    comando = sys.argv[1].lower()
    
    if comando == "init":
        comando_init()
    
    elif comando == "stats":
        cnpj = sys.argv[2] if len(sys.argv) > 2 else None
        comando_stats(cnpj)
    
    elif comando == "reset-errors":
        cnpj = sys.argv[2] if len(sys.argv) > 2 else None
        comando_reset_errors(cnpj)
    
    elif comando == "execucoes":
        data = sys.argv[2] if len(sys.argv) > 2 else None
        comando_execucoes(data)
    
    elif comando == "clean":
        dias = int(sys.argv[2]) if len(sys.argv) > 2 else 90
        comando_clean(dias)
    
    else:
        print(f"❌ Comando desconhecido: {comando}")
        mostrar_ajuda()
        sys.exit(1)
