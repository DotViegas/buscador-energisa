"""
Módulo de gerenciamento de banco de dados SQLite para controle de faturas
"""

from .db_manager import DatabaseManager
from .models import inicializar_banco

__all__ = ['DatabaseManager', 'inicializar_banco']
