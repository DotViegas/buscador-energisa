#!/usr/bin/env python3
"""
Mostra o mapeamento entre CNPJs das geradoras e os arquivos JSON gerados
"""

from geradoras import (
    USINA_LUNA_CNPJ, USINA_SULINA_CNPJ, USINA_LB_CNPJ, 
    USINA_ENERGIAA_CNPJ, USINA_LUZDIVINA_CNPJ, USINA_G114_CNPJ
)

def extrair_numeros_cnpj(cnpj):
    """Extrai apenas os números do CNPJ"""
    return ''.join(filter(str.isdigit, cnpj))

def mostrar_mapeamento():
    print("🏭 MAPEAMENTO CNPJ → ARQUIVO JSON")
    print("=" * 70)
    
    geradoras = {
        "Usina Luna": USINA_LUNA_CNPJ,
        "Usina Sulina": USINA_SULINA_CNPJ,
        "Usina LB": USINA_LB_CNPJ,
        "Usina Energiaa": USINA_ENERGIAA_CNPJ,
        "Usina Luzdivina": USINA_LUZDIVINA_CNPJ,
        "Usina G114": USINA_G114_CNPJ
    }
    
    print(f"{'NOME':<20} | {'CNPJ':<20} | {'ARQUIVO JSON'}")
    print("-" * 70)
    
    for nome, cnpj in geradoras.items():
        arquivo = f"{extrair_numeros_cnpj(cnpj)}.json"
        print(f"{nome:<20} | {cnpj:<20} | {arquivo}")
    
    print("=" * 70)
    print("📝 Agora os arquivos JSON usam apenas os números do CNPJ!")

if __name__ == "__main__":
    mostrar_mapeamento()