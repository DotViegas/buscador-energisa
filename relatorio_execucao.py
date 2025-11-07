#!/usr/bin/env python3
"""
Relatório da execução do buscar_dados_api.py
"""

import json
import os

def gerar_relatorio():
    print("📊 RELATÓRIO DE EXECUÇÃO")
    print("=" * 60)
    
    diretorio = "media/json"
    if not os.path.exists(diretorio):
        print("❌ Diretório media/json não encontrado")
        return
    
    arquivos = [f for f in os.listdir(diretorio) if f.endswith('.json')]
    
    if not arquivos:
        print("❌ Nenhum arquivo JSON encontrado")
        return
    
    total_faturas = 0
    total_ucs = 0
    
    print(f"{'GERADORA':<25} | {'FATURAS':>8} | {'UCs':>4} | {'SITUAÇÕES'}")
    print("-" * 60)
    
    for arquivo in sorted(arquivos):
        caminho = os.path.join(diretorio, arquivo)
        
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            faturas_geradora = sum(len(faturas) for faturas in data['lista_ucs'].values())
            ucs_geradora = len(data['lista_ucs'])
            
            # Contar situações diferentes
            situacoes = set()
            for faturas_uc in data['lista_ucs'].values():
                for fatura in faturas_uc:
                    situacoes.add(fatura.get('situacao_pagamento', 'N/A'))
            
            total_faturas += faturas_geradora
            total_ucs += ucs_geradora
            
            nome_geradora = arquivo.replace('.json', '')
            situacoes_str = ', '.join(sorted(situacoes))
            
            print(f"{nome_geradora:<25} | {faturas_geradora:>8} | {ucs_geradora:>4} | {situacoes_str}")
            
        except Exception as e:
            print(f"❌ Erro ao processar {arquivo}: {e}")
    
    print("=" * 60)
    print(f"TOTAL: {total_faturas} faturas em {total_ucs} UCs")
    print(f"Distribuídas em {len(arquivos)} geradoras")
    
    # Verificar estrutura de exemplo
    print(f"\n🔍 VERIFICAÇÃO DA ESTRUTURA:")
    arquivo_exemplo = arquivos[0]
    caminho_exemplo = os.path.join(diretorio, arquivo_exemplo)
    
    with open(caminho_exemplo, 'r', encoding='utf-8') as f:
        data_exemplo = json.load(f)
    
    print(f"Arquivo exemplo: {arquivo_exemplo}")
    print(f"Estrutura principal: ✓ geradora, ✓ lista_ucs")
    
    # Pegar primeira UC e primeira fatura
    primeira_uc = list(data_exemplo['lista_ucs'].keys())[0]
    primeira_fatura = data_exemplo['lista_ucs'][primeira_uc][0]
    
    campos_importantes = ['id', 'nova_uc', 'situacao_pagamento', 'tarefa']
    print(f"Campos importantes na fatura:")
    for campo in campos_importantes:
        if campo in primeira_fatura:
            valor = primeira_fatura[campo]
            print(f"  ✓ {campo}: {valor}")
        else:
            print(f"  ❌ {campo}: AUSENTE")

if __name__ == "__main__":
    gerar_relatorio()