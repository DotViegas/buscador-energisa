"""Robô de rateio: aplica no portal Energisa a planilha do mês (rateio/lista/AAAA-MM/).

Para cada usina da planilha:
  1. login com o CNPJ da geradora (mesmo login do robo_v2) e seleção da UC da usina;
  2. gerenciamento-gd → Editar unidades beneficiárias → Iniciar solicitação;
  3. etapa 1: adiciona cada UC da planilha, guardando o número da UC e o endereço
     que o portal mostra (fonte mais atualizada). REGRA DE DISTRIBUIÇÃO: UC que não
     aparece na busca (desligada/inativa ou fora da titularidade) não pode receber
     crédito; o percentual dela vai para a bateria da geradora (aba "Configuração
     MCP" da planilha), que é incluída na usina se ainda não estiver, mantendo 100%;
  4. etapa 2: se o portal tem beneficiária que não está na planilha, seria preciso
     removê-la, e a Finalização do portal quebra com remoções (bug da Energisa):
     a usina sai do portal e o robô gera o formulário oficial de alteração;
  5. sem remoções: preenche os %, envia documentos e abre a Finalização, salvando a
     prova em PDF (como Ctrl+P). Só com --enviar marca o aceite, clica em Finalizar
     e salva o protocolo;
  6. qualquer outra falha do portal também leva ao formulário.

Modo padrão é ENSAIO (não finaliza nada). A Energisa só aceita UMA alteração por
período de faturamento por usina.

Uso: python robo_rateio.py [--mes AAAA-MM] [--usina "ENERGIA A 3" [--usina ...]] [--enviar]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

from patchright.sync_api import sync_playwright

import robo_v2
from function import portal_rateio as portal
from function import rateio_lista
from function.formulario_rateio import Beneficiaria, gerar_formulario, titular_padrao
from function.navegador import fazer_login_com_retry, fechar_navegador, relogar
from robo import AccessDeniedError, LogDuplo

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_USINAS = os.path.join(rateio_lista.PASTA_RATEIO, "usinas.json")


def slug_usina(nome):
    """'ENERGIA A 6' -> 'ENERGIA_A_06' (ordena bem na pasta)."""
    m = re.match(r"(.*?)\s*(\d+)$", nome.strip())
    base, numero = (m.group(1), f"{int(m.group(2)):02d}") if m else (nome, "")
    return re.sub(r"\W+", "_", f"{base} {numero}".strip()).strip("_")


def cnpj_da_geradora(nome):
    from ea_manager import GERADORAS_NOMES
    for cnpj, apelido in GERADORAS_NOMES.items():
        if apelido.upper() == nome.upper():
            return cnpj
    raise ValueError(f"geradora '{nome}' sem CNPJ em ea_manager.GERADORAS_NOMES")


def uc_da_usina(usina):
    """UC (código do cliente) da usina: da planilha ou, enquanto ela não trouxer,
    de rateio/usinas.json ({"ENERGIA A 1": "10/2562433-9", ...})."""
    if usina.uc_geradora:
        return usina.uc_geradora
    if os.path.exists(ARQUIVO_USINAS):
        with open(ARQUIVO_USINAS, encoding="utf-8") as f:
            uc = json.load(f).get(usina.nome, "")
        if uc:
            return uc
    raise ValueError(f"{usina.nome}: UC da usina não está na planilha nem em {ARQUIVO_USINAS}")


def documentos(geradora):
    """Arquivos de rateio/documents/<GERADORA>: cartão CNPJ + RG (frente/verso) ou CNH."""
    arquivos = rateio_lista.listar_documentos(geradora)
    achar = lambda chave: next((a for a in arquivos if chave in os.path.basename(a).lower()), None)
    docs = {"cartao_cnpj": achar("cartao-cnpj")}
    if achar("rg-frente") and achar("rg-verso"):
        docs.update(tipo="RG", frente=achar("rg-frente"), verso=achar("rg-verso"))
    elif achar("cnh"):
        docs.update(tipo="CNH", frente=achar("cnh"))
    faltando = [k for k in ("cartao_cnpj", "tipo") if not docs.get(k)]
    if faltando:
        raise ValueError(f"rateio/documents/{geradora}/ sem {faltando} (esperado 01-cartao-cnpj, "
                         "02-rg-frente e 03-rg-verso ou 02-cnh)")
    return docs


def gerar_formulario_usina(planilha, usina, numero_uc_usina, rateio, dados_ucs):
    """`rateio`: {uc: %} já com os ajustes (ordem da planilha, bateria incluída)."""
    titular = titular_padrao()
    beneficiarias = [
        Beneficiaria(dados_ucs.get(uc, {}).get("numero_uc", ""), uc, titular.nome, titular.cnpj,
                     dados_ucs.get(uc, {}).get("endereco", ""), percentual)
        for uc, percentual in rateio.items()
    ]
    caminho = os.path.join(rateio_lista.PASTA_RATEIO, "formularios", planilha.mes_referencia,
                           f"Formulario_{slug_usina(usina.nome)}_{planilha.mes_referencia}.pdf")
    return gerar_formulario(caminho, numero_uc_usina, beneficiarias, titular, percentual_geradora=0)


def transferir_para_bateria(page, planilha, rateio, dados_ucs, nao_encontradas, resultado):
    """Regra de distribuição: o % das UCs que não aparecem no portal (desligadas ou fora da
    titularidade) vai para a bateria da geradora, incluída na usina se preciso. Altera
    `rateio` e `dados_ucs` e registra em resultado['ajustes']. Retorna mensagem de erro ou None."""
    bateria = planilha.uc_bateria
    if not bateria:
        return f"UCs não encontradas no portal ({', '.join(nao_encontradas)}) e a planilha não indica bateria"
    if bateria in nao_encontradas:
        return f"a bateria {bateria} não foi encontrada no portal"
    transferido = round(sum(rateio.pop(uc) for uc in nao_encontradas), 2)
    if bateria not in rateio:
        situacao, dados = portal.adicionar_uc(page, bateria)
        print(f"   [bateria] {bateria}: {situacao}")
        if situacao == "nao_encontrada":
            return f"a bateria {bateria} não foi encontrada no portal"
        dados_ucs[bateria] = dados
        rateio[bateria] = 0
    rateio[bateria] = round(rateio[bateria] + transferido, 2)
    ajuste = (f"{', '.join(nao_encontradas)} não encontrada(s) no portal (desligada/fora da titularidade): "
              f"{transferido:g}% transferido(s) para a bateria {bateria} (agora {rateio[bateria]:g}%)")
    resultado.setdefault("ajustes", []).append(ajuste)
    print(f"   🔋 {ajuste}")
    return None


def processar_usina(context, page, monitor, planilha, usina, docs, enviar, pasta_saida):
    """Executa o fluxo de uma usina. Retorna dict com situação e arquivos gerados."""
    uc_usina = uc_da_usina(usina)
    rateio = {b.uc: b.percentual for b in usina.beneficiarias}
    resultado = {"usina": usina.nome, "uc_usina": uc_usina, "arquivos": []}
    numero_uc_usina, dados_ucs = "", {}
    try:
        robo_v2.checar_bloqueio(page, monitor)
        robo_v2.selecionar_uc(page, monitor, uc_usina)
        robo_v2.aguardar_saida_listagem(page, monitor, uc_usina)
        numero_uc_usina = portal.abrir_cadastro(page, uc_usina)
        print(f"   📝 Solicitação iniciada (UC da usina {uc_usina} / {numero_uc_usina})")

        nao_encontradas = []
        for n, uc in enumerate(list(rateio), 1):
            situacao, dados = portal.adicionar_uc(page, uc)
            dados_ucs[uc] = dados
            print(f"   [{n}/{len(rateio)}] {uc}: {situacao}")
            if situacao == "nao_encontrada":
                nao_encontradas.append(uc)
        if nao_encontradas:
            erro = transferir_para_bateria(page, planilha, rateio, dados_ucs, nao_encontradas, resultado)
            if erro:
                resultado.update(situacao="erro", detalhe=erro)
                return resultado

        ucs_portal = portal.ir_para_configuracao(page)
        remover = [uc for uc in ucs_portal if uc not in rateio]
        if remover:
            raise portal.RemocaoNecessaria(remover)
        total = portal.preencher_percentuais(page, rateio)
        print(f"   🔢 Percentuais preenchidos: {total}")
        if not total.startswith("100"):
            raise portal.PortalFalhou(f"total distribuído {total} (esperado 100/100)")

        portal.enviar_documentos(page, docs)
        portal.abrir_finalizacao(page)
        sufixo = "" if enviar else "_ENSAIO"
        prova = portal.imprimir_pdf(context, page, os.path.join(pasta_saida, f"{slug_usina(usina.nome)}_finalizacao{sufixo}.pdf"))
        resultado["arquivos"].append(prova)
        if not enviar:
            resultado.update(situacao="portal_ensaio", detalhe="chegou à Finalização (não finalizado)")
            return resultado

        texto = portal.finalizar(page)
        protocolo = portal.extrair_protocolo(texto)
        resultado["arquivos"].append(portal.imprimir_pdf(
            context, page, os.path.join(pasta_saida, f"{slug_usina(usina.nome)}_protocolo.pdf")))
        resultado.update(situacao="portal_enviado", detalhe=f"protocolo {protocolo or '(não identificado)'}")
        return resultado

    except (portal.RemocaoNecessaria, portal.PortalFalhou) as e:
        print(f"   ↪️ {e}")
        if not numero_uc_usina or len(dados_ucs) < len(rateio):
            resultado.update(situacao="erro", detalhe=f"{e} (sem dados do portal para o formulário)")
            return resultado
        resultado["arquivos"].append(gerar_formulario_usina(planilha, usina, numero_uc_usina, rateio, dados_ucs))
        motivo = "remoções" if isinstance(e, portal.RemocaoNecessaria) else "falha no portal"
        resultado.update(situacao="formulario", detalhe=f"{motivo}: {e}")
        return resultado


def imprimir_resumo(resultados, enviar):
    print(f"\n{'=' * 80}\n📊 RESUMO DO RATEIO ({'ENVIO' if enviar else 'ENSAIO'})\n{'=' * 80}")
    icones = {"portal_ensaio": "🧪", "portal_enviado": "✅", "formulario": "📄", "erro": "❌"}
    for r in resultados:
        print(f"{icones.get(r['situacao'], '?')} {r['usina']:14} {r['situacao']:15} {r.get('detalhe', '')}")
        for ajuste in r.get("ajustes", []):
            print(f"      🔋 {ajuste}")
        for a in r["arquivos"]:
            print(f"      {os.path.relpath(a, PROJECT_DIR)}")


def main():
    ap = argparse.ArgumentParser(description="Aplica o rateio do mês no portal Energisa")
    ap.add_argument("--mes", help="AAAA-MM (padrão: o mais recente com planilha)")
    ap.add_argument("--usina", action="append",
                    help='processa só esta usina (ex.: "ENERGIA A 3"); pode repetir')
    ap.add_argument("--enviar", action="store_true", help="FINALIZA no portal (sem isto é ensaio)")
    args = ap.parse_args()

    meses = [m for m in rateio_lista.listar_meses() if rateio_lista.listar_planilhas(m)]
    mes = args.mes or (meses[0] if meses else None)
    if not mes or not rateio_lista.listar_planilhas(mes):
        print(f"❌ Nenhuma planilha em rateio/lista/{mes or 'AAAA-MM'}/")
        sys.exit(2)

    trava = robo_v2.travar_instancia()
    if trava is None:
        print("⛔ Já existe um robô usando o perfil do Chrome (robo_v2/robo_rateio) - abortando.")
        sys.exit(1)

    os.makedirs("logs", exist_ok=True)
    inicio = datetime.now()
    log = LogDuplo(os.path.join("logs", inicio.strftime("rateio-%d%m%Y-%H%M%S.txt")))
    sys.stdout = log
    resultados = []
    try:
        print(f"📝 ROBÔ DE RATEIO - {inicio:%d/%m/%Y %H:%M:%S} - mês {mes} - "
              f"{'ENVIO (finaliza no portal)' if args.enviar else 'ENSAIO (não finaliza)'}")
        for caminho in rateio_lista.listar_planilhas(mes):
            planilha = rateio_lista.ler_planilha(caminho)
            filtro = {n.upper() for n in args.usina or []}
            usinas = [u for u in planilha.usinas if not filtro or u.nome.upper() in filtro]
            if not usinas:
                continue
            erros_planilha = [a for a in planilha.avisos if "UC da usina" not in a]
            if erros_planilha:
                print("❌ Planilha com problemas, corrija antes de rodar:\n   " + "\n   ".join(erros_planilha))
                continue
            docs = documentos(planilha.geradora)
            pasta_saida = os.path.join(rateio_lista.PASTA_RATEIO, "resultados", mes)
            os.makedirs(pasta_saida, exist_ok=True)
            cnpj = cnpj_da_geradora(planilha.geradora)
            print(f"\n🏭 {planilha.geradora} ({cnpj}) - {len(usinas)} usina(s)")

            with sync_playwright() as p:
                context, page, monitor = fazer_login_com_retry(p, cnpj)
                try:
                    for usina in usinas:
                        print(f"\n⚡ {usina.nome} - {len(usina.beneficiarias)} beneficiária(s)")
                        for tentativa in (1, 2):
                            try:
                                r = processar_usina(context, page, monitor, planilha, usina, docs,
                                                    args.enviar, pasta_saida)
                                break
                            except AccessDeniedError as e:
                                r = {"usina": usina.nome, "arquivos": [], "situacao": "erro",
                                     "detalhe": f"bloqueio do portal: {e}"}
                                if tentativa == 1:
                                    print(f"   🚫 Bloqueio: {e} - relogando e repetindo a usina")
                                    context, page, monitor = relogar(p, cnpj, context)
                            except Exception as e:
                                r = {"usina": usina.nome, "arquivos": [], "situacao": "erro",
                                     "detalhe": (str(e).splitlines() or [repr(e)])[0]}
                                break
                        print(f"   ➡️ {r['situacao']}: {r.get('detalhe', '')}")
                        resultados.append(r)
                finally:
                    fechar_navegador(context)
    finally:
        imprimir_resumo(resultados, args.enviar)
        if resultados:
            arq = os.path.join(rateio_lista.PASTA_RATEIO, "resultados", mes,
                               inicio.strftime("resultado-%d%m%Y-%H%M%S.json"))
            with open(arq, "w", encoding="utf-8") as f:
                json.dump(resultados, f, ensure_ascii=False, indent=1)
        print(f"Duração: {(datetime.now() - inicio).total_seconds() / 60:.1f} min")
        log.close()
        sys.stdout = log.terminal


if __name__ == "__main__":
    main()
