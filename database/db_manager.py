"""
Gerenciador de operações do banco de dados
"""

import sqlite3
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

class DatabaseManager:
    """Classe para gerenciar operações no banco de dados SQLite"""
    
    def __init__(self, db_path="database/faturas.db"):
        """
        Inicializa o gerenciador do banco de dados
        
        Args:
            db_path (str): Caminho para o arquivo do banco de dados
        """
        self.db_path = db_path
    
    def _get_connection(self):
        """Retorna uma conexão com o banco de dados"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Permite acessar colunas por nome
        return conn
    
    # ==================== OPERAÇÕES COM FATURAS ====================
    
    def inserir_ou_atualizar_fatura(self, fatura_data: Dict) -> bool:
        """
        Insere uma nova fatura ou atualiza se já existir
        Mantém o status existente se a fatura já estiver no banco
        
        Args:
            fatura_data (dict): Dados da fatura contendo:
                - id: ID da fatura
                - nova_uc: Número da UC
                - mes_referencia: Mês no formato MM/AAAA
                - cnpj_geradora: CNPJ da geradora
        
        Returns:
            bool: True se inseriu/atualizou, False se erro
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Verificar se a fatura já existe
            cursor.execute("""
                SELECT status FROM faturas WHERE id = ?
            """, (fatura_data['id'],))
            
            resultado = cursor.fetchone()
            
            if resultado:
                # Fatura já existe - não atualiza nada, mantém status atual
                print(f"   ℹ️ Fatura ID {fatura_data['id']} já existe no banco com status: {resultado['status']}")
                conn.close()
                return True
            else:
                # Fatura nova - inserir com status 'a_verificar'
                cursor.execute("""
                    INSERT INTO faturas (
                        id, nova_uc, mes_referencia, cnpj_geradora, 
                        status, data_criacao, tentativas
                    ) VALUES (?, ?, ?, ?, 'a_verificar', ?, 0)
                """, (
                    fatura_data['id'],
                    fatura_data['nova_uc'],
                    fatura_data['mes_referencia'],
                    fatura_data['cnpj_geradora'],
                    datetime.now()
                ))
                
                conn.commit()
                print(f"   ✅ Fatura ID {fatura_data['id']} inserida no banco")
            
            conn.close()
            return True
            
        except Exception as e:
            print(f"   ❌ Erro ao inserir/atualizar fatura: {str(e)}")
            return False
    
    def verificar_status_fatura(self, fatura_id: int, force: bool = False) -> Tuple[str, bool]:
        """
        Verifica o status de uma fatura e determina se deve ser processada
        
        Args:
            fatura_id (int): ID da fatura
            force (bool): Se True, permite reprocessar faturas com erro
        
        Returns:
            tuple: (status, deve_processar)
                - status: 'a_verificar', 'sucesso', 'erro', 'nao_encontrada'
                - deve_processar: True se deve processar, False caso contrário
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT status, tentativas FROM faturas WHERE id = ?
            """, (fatura_id,))
            
            resultado = cursor.fetchone()
            conn.close()
            
            if not resultado:
                return ('nao_encontrada', True)
            
            status = resultado['status']
            
            # Regras de processamento
            if status == 'sucesso':
                return (status, False)  # Não reprocessar sucessos
            elif status == 'erro':
                return (status, force)  # Só reprocessa com --force
            else:  # 'a_verificar'
                return (status, True)  # Sempre processa
                
        except Exception as e:
            print(f"   ❌ Erro ao verificar status da fatura: {str(e)}")
            return ('erro', False)
    
    def atualizar_status_fatura(self, fatura_id: int, status: str, 
                                mensagem_erro: Optional[str] = None,
                                valor: Optional[str] = None,
                                data_vencimento: Optional[str] = None,
                                situacao_pagamento: Optional[str] = None,
                                tipo_operacao: Optional[str] = None,
                                log_execucao: Optional[str] = None) -> bool:
        """
        Atualiza o status de uma fatura após processamento
        
        Args:
            fatura_id (int): ID da fatura
            status (str): Novo status ('sucesso' ou 'erro')
            mensagem_erro (str): Mensagem de erro se houver
            valor (str): Valor da fatura
            data_vencimento (str): Data de vencimento
            situacao_pagamento (str): Situação de pagamento
            tipo_operacao (str): Tipo de operação realizada (nao_encontrada, criada, atualizada, situacao_alterada, erro)
            log_execucao (str): Log completo da execução da fatura
        
        Returns:
            bool: True se atualizou, False se erro
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Incrementar tentativas
            cursor.execute("""
                UPDATE faturas 
                SET status = ?,
                    data_processamento = ?,
                    tentativas = tentativas + 1,
                    mensagem_erro = ?,
                    valor = ?,
                    data_vencimento = ?,
                    situacao_pagamento = ?,
                    tipo_operacao = ?,
                    log_execucao = ?
                WHERE id = ?
            """, (
                status,
                datetime.now(),
                mensagem_erro,
                valor,
                data_vencimento,
                situacao_pagamento,
                tipo_operacao,
                log_execucao,
                fatura_id
            ))
            
            conn.commit()
            conn.close()
            
            if tipo_operacao:
                print(f"   ✅ Status da fatura ID {fatura_id} atualizado para: {status} | Operação: {tipo_operacao}")
            else:
                print(f"   ✅ Status da fatura ID {fatura_id} atualizado para: {status}")
            return True
            
        except Exception as e:
            print(f"   ❌ Erro ao atualizar status da fatura: {str(e)}")
            return False
    
    def obter_faturas_para_processar(self, cnpj_geradora: str, force: bool = False) -> List[Dict]:
        """
        Obtém lista de faturas que devem ser processadas para uma geradora
        
        Args:
            cnpj_geradora (str): CNPJ da geradora
            force (bool): Se True, inclui faturas com erro
        
        Returns:
            list: Lista de faturas para processar
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if force:
                # Com --force, processa 'a_verificar' e 'erro'
                cursor.execute("""
                    SELECT * FROM faturas 
                    WHERE cnpj_geradora = ? 
                    AND status IN ('a_verificar', 'erro')
                    ORDER BY nova_uc, mes_referencia
                """, (cnpj_geradora,))
            else:
                # Sem --force, processa apenas 'a_verificar'
                cursor.execute("""
                    SELECT * FROM faturas 
                    WHERE cnpj_geradora = ? 
                    AND status = 'a_verificar'
                    ORDER BY nova_uc, mes_referencia
                """, (cnpj_geradora,))
            
            faturas = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return faturas
            
        except Exception as e:
            print(f"   ❌ Erro ao obter faturas para processar: {str(e)}")
            return []
    
    # ==================== OPERAÇÕES COM EXECUÇÕES DIÁRIAS ====================
    
    def registrar_execucao_uc(self, cnpj_geradora: str, nova_uc: str, 
                              total_faturas: int, faturas_sucesso: int, 
                              faturas_erro: int, faturas_puladas: int,
                              data_hora_inicio: datetime) -> bool:
        """
        Registra a execução de uma UC no dia
        
        Args:
            cnpj_geradora (str): CNPJ da geradora
            nova_uc (str): UC processada
            total_faturas (int): Total de faturas
            faturas_sucesso (int): Faturas com sucesso
            faturas_erro (int): Faturas com erro
            faturas_puladas (int): Faturas puladas
            data_hora_inicio (datetime): Hora de início do processamento
        
        Returns:
            bool: True se registrou, False se erro
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            data_hoje = date.today()
            
            # Determinar status da execução
            if faturas_sucesso == total_faturas:
                status_execucao = 'completo'
            elif faturas_sucesso > 0:
                status_execucao = 'parcial'
            else:
                status_execucao = 'falha'
            
            # Inserir ou substituir registro do dia
            cursor.execute("""
                INSERT OR REPLACE INTO execucoes_diarias (
                    data_execucao, cnpj_geradora, nova_uc,
                    total_faturas, faturas_sucesso, faturas_erro, faturas_puladas,
                    status_execucao, data_hora_inicio, data_hora_fim
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data_hoje,
                cnpj_geradora,
                nova_uc,
                total_faturas,
                faturas_sucesso,
                faturas_erro,
                faturas_puladas,
                status_execucao,
                data_hora_inicio,
                datetime.now()
            ))
            
            conn.commit()
            conn.close()
            
            print(f"   📊 Execução da UC {nova_uc} registrada: {status_execucao}")
            return True
            
        except Exception as e:
            print(f"   ❌ Erro ao registrar execução: {str(e)}")
            return False
    
    def obter_execucoes_do_dia(self, data_execucao: Optional[date] = None) -> List[Dict]:
        """
        Obtém todas as execuções de um dia específico
        
        Args:
            data_execucao (date): Data para consultar (padrão: hoje)
        
        Returns:
            list: Lista de execuções do dia
        """
        try:
            if data_execucao is None:
                data_execucao = date.today()
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM execucoes_diarias 
                WHERE data_execucao = ?
                ORDER BY cnpj_geradora, nova_uc
            """, (data_execucao,))
            
            execucoes = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return execucoes
            
        except Exception as e:
            print(f"   ❌ Erro ao obter execuções do dia: {str(e)}")
            return []
    
    # ==================== RELATÓRIOS E ESTATÍSTICAS ====================
    
    def obter_estatisticas_geradora(self, cnpj_geradora: str) -> Dict:
        """
        Obtém estatísticas de processamento de uma geradora
        
        Args:
            cnpj_geradora (str): CNPJ da geradora
        
        Returns:
            dict: Estatísticas da geradora
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'a_verificar' THEN 1 ELSE 0 END) as a_verificar,
                    SUM(CASE WHEN status = 'sucesso' THEN 1 ELSE 0 END) as sucesso,
                    SUM(CASE WHEN status = 'erro' THEN 1 ELSE 0 END) as erro
                FROM faturas
                WHERE cnpj_geradora = ?
            """, (cnpj_geradora,))
            
            resultado = dict(cursor.fetchone())
            conn.close()
            
            return resultado
            
        except Exception as e:
            print(f"   ❌ Erro ao obter estatísticas: {str(e)}")
            return {}
    
    def limpar_faturas_antigas(self, dias: int = 90) -> int:
        """
        Remove faturas processadas com sucesso há mais de X dias
        
        Args:
            dias (int): Número de dias para manter no histórico
        
        Returns:
            int: Número de registros removidos
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM faturas 
                WHERE status = 'sucesso' 
                AND data_processamento < datetime('now', '-' || ? || ' days')
            """, (dias,))
            
            removidos = cursor.rowcount
            conn.commit()
            conn.close()
            
            print(f"   🗑️ {removidos} faturas antigas removidas do banco")
            return removidos
            
        except Exception as e:
            print(f"   ❌ Erro ao limpar faturas antigas: {str(e)}")
            return 0
    
    def resetar_status_erro(self, fatura_id: Optional[int] = None, 
                           cnpj_geradora: Optional[str] = None) -> int:
        """
        Reseta status de faturas com erro para 'a_verificar'
        Usado com o parâmetro --force
        
        Args:
            fatura_id (int): ID específico da fatura (opcional)
            cnpj_geradora (str): CNPJ da geradora para resetar todas (opcional)
        
        Returns:
            int: Número de faturas resetadas
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if fatura_id:
                cursor.execute("""
                    UPDATE faturas 
                    SET status = 'a_verificar', mensagem_erro = NULL
                    WHERE id = ? AND status = 'erro'
                """, (fatura_id,))
            elif cnpj_geradora:
                cursor.execute("""
                    UPDATE faturas 
                    SET status = 'a_verificar', mensagem_erro = NULL
                    WHERE cnpj_geradora = ? AND status = 'erro'
                """, (cnpj_geradora,))
            else:
                cursor.execute("""
                    UPDATE faturas 
                    SET status = 'a_verificar', mensagem_erro = NULL
                    WHERE status = 'erro'
                """)
            
            resetados = cursor.rowcount
            conn.commit()
            conn.close()
            
            print(f"   🔄 {resetados} faturas com erro resetadas para reprocessamento")
            return resetados
            
        except Exception as e:
            print(f"   ❌ Erro ao resetar status: {str(e)}")
            return 0
