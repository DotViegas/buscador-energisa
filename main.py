from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
import asyncio
from robo import processar_todas_geradoras, processar_geradora, processar_multiplas_geradoras, geradoras_cnpjs

app = FastAPI(title="Energisa Busca API", description="Microserviço para processamento de faturas Energisa")

@app.post('/start-search')
async def iniciar_busca_todas_geradoras(background_tasks: BackgroundTasks):
    """Inicia o processamento de todas as geradoras em background"""
    background_tasks.add_task(processar_todas_geradoras)
    return JSONResponse(
        content={
            "message": "Processamento iniciado em background",
            "total_geradoras": len(geradoras_cnpjs),
            "geradoras": geradoras_cnpjs
        }
    )

@app.post('/start-search/{cnpjs}')
async def iniciar_busca_geradoras(cnpjs: str, background_tasks: BackgroundTasks):
    """Inicia o processamento de uma ou múltiplas geradoras pelos CNPJs
    
    Formatos aceitos:
    - Um CNPJ: /start-search/47.278.309/0001-01
    - Múltiplos CNPJs: /start-search/47.278.309/0001-01AND58.179.054/0001-46
    """
    # Separar os CNPJs usando "AND" como delimitador
    cnpjs_solicitados = cnpjs.split("AND")
    geradoras_encontradas = []
    cnpjs_nao_encontrados = []
    
    # Validar cada CNPJ
    for cnpj in cnpjs_solicitados:
        cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
        
        # Procura o CNPJ na lista de geradoras
        geradora_encontrada = None
        for geradora_cnpj in geradoras_cnpjs:
            if geradora_cnpj.replace(".", "").replace("/", "").replace("-", "") == cnpj_limpo:
                geradora_encontrada = geradora_cnpj
                break
        
        if geradora_encontrada:
            geradoras_encontradas.append(geradora_encontrada)
        else:
            cnpjs_nao_encontrados.append(cnpj)
    
    # Se algum CNPJ não foi encontrado, retornar erro
    if cnpjs_nao_encontrados:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"CNPJs não encontrados: {', '.join(cnpjs_nao_encontrados)}",
                "geradoras_validas": geradoras_encontradas
            }
        )
    
    # Se apenas uma geradora, usar função específica
    if len(geradoras_encontradas) == 1:
        background_tasks.add_task(processar_geradora, geradoras_encontradas[0])
        return JSONResponse(
            content={
                "message": f"Processamento da geradora {geradoras_encontradas[0]} iniciado em background"
            }
        )
    
    # Se múltiplas geradoras, usar função de processamento múltiplo
    background_tasks.add_task(processar_multiplas_geradoras, geradoras_encontradas)
    return JSONResponse(
        content={
            "message": f"Processamento de {len(geradoras_encontradas)} geradoras iniciado em background",
            "geradoras": geradoras_encontradas
        }
    )

@app.get('/geradoras')
async def listar_geradoras():
    """Lista todas as geradoras disponíveis"""
    return JSONResponse(
        content={
            "total": len(geradoras_cnpjs),
            "geradoras": geradoras_cnpjs
        }
    )

@app.get('/')
async def root():
    """Endpoint raiz com informações da API"""
    return JSONResponse(
        content={
            "message": "Energisa Busca API",
            "version": "1.0.0",
            "endpoints": {
                "POST /start-search": "Inicia processamento de todas as geradoras",
                "POST /start-search/{cnpj}": "Inicia processamento de uma geradora específica",
                "POST /start-search/{cnpj}AND{cnpj2}": "Inicia processamento de múltiplas geradoras (use AND como separador)",
                "GET /geradoras": "Lista todas as geradoras disponíveis"
            },
            "exemplos": {
                "uma_geradora": "/start-search/47.278.309/0001-01",
                "multiplas_geradoras": "/start-search/47.278.309/0001-01AND58.179.054/0001-46AND48.174.641/0001-99"
            }
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)