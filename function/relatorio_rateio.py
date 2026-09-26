"""Relatório em PDF (identidade ENERGIA A) dos rateios de um mês.

Capa com os números do mês, resumo por usina (situação, protocolo, data do envio,
beneficiárias, removidas, ajustes) e o demonstrativo de cada usina com os percentuais
efetivamente enviados, fechando em 100%.

Fontes: rateio/lista/<mes>/ (planilhas) e rateio/resultados/<mes>/resultado-*.json (execuções
do robo_rateio). Para cada usina vale o resultado de maior prioridade (enviado pelo portal >
enviado a conferir > formulário > ensaio/erro) e, no empate, o mais recente.
"""
import glob
import html
import json
import os
import re
from datetime import datetime

from function import rateio_lista

PASTA_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "templates", "relatorio_rateio")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro")
PRIORIDADE = {"portal_enviado": 4, "enviado_conferir": 3, "formulario": 2, "portal_ensaio": 1, "erro": 0}
SITUACOES = {
    "portal_enviado": ("Enviado pelo portal", "ok"),
    "enviado_conferir": ("Enviado — conferir", "alerta"),
    "formulario": ("Formulário (envio manual)", "info"),
    "portal_ensaio": ("Somente ensaio", "alerta"),
    "erro": ("Erro", "erro"),
    None: ("Não processado", "erro"),
}
RE_AJUSTE = re.compile(r"^(?P<ucs>.+?) não encontrada\(s\) no portal.*?: (?P<pct>[\d.,]+)% transferido\(s\) "
                       r"para a bateria (?P<bateria>\S+)")


def _esc(texto):
    return html.escape(str(texto if texto is not None else ""))


def _pct(valor):
    texto = f"{round(float(valor), 2):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") + "%"


def _mes_extenso(mes):
    ano, numero = mes.split("-")
    return f"{MESES[int(numero) - 1].capitalize()}/{ano}"


def carregar_resultados(mes):
    """{usina: (registro, datahora da execução)} com o resultado que vale para cada usina."""
    escolhidos = {}
    pasta = os.path.join(rateio_lista.PASTA_RATEIO, "resultados", mes)
    for arquivo in sorted(glob.glob(os.path.join(pasta, "resultado-*.json"))):
        m = re.search(r"resultado-(\d{8}-\d{6})\.json$", arquivo)
        quando = datetime.strptime(m.group(1), "%d%m%Y-%H%M%S") if m else datetime.fromtimestamp(os.path.getmtime(arquivo))
        with open(arquivo, encoding="utf-8") as f:
            for registro in json.load(f):
                atual = escolhidos.get(registro["usina"])
                chave = (PRIORIDADE.get(registro.get("situacao"), 0), quando)
                if atual is None or chave >= (PRIORIDADE.get(atual[0].get("situacao"), 0), atual[1]):
                    escolhidos[registro["usina"]] = (registro, quando)
    return escolhidos


def rateio_enviado(usina, registro, uc_bateria):
    """[(uc, cliente, %, observação)] como foi enviado: a planilha, sem as UCs que não
    apareceram no portal e com o % delas na bateria (regra de distribuição do robô)."""
    linhas = [[b.uc, b.cliente, b.percentual, ""] for b in usina.beneficiarias]
    for b, linha in zip(usina.beneficiarias, linhas):
        if b.bateria:
            linha[1], linha[3] = "Endereço-bateria (sobra da usina)", "bateria"
    for ajuste in (registro or {}).get("ajustes", []):
        m = RE_AJUSTE.match(ajuste)
        if not m:
            continue
        fora = [u.strip() for u in m.group("ucs").split(",")]
        linhas = [l for l in linhas if l[0] not in fora]
        bateria = m.group("bateria")
        transferido = float(m.group("pct").replace(",", "."))
        alvo = next((l for l in linhas if l[0] == bateria), None)
        if alvo is None:
            alvo = [bateria, "Endereço-bateria (sobra da usina)", 0.0, "bateria"]
            linhas.append(alvo)
        alvo[2] = round(alvo[2] + transferido, 2)
        alvo[3] = f"bateria (+{_pct(transferido)} de UC desligada)"
    return [tuple(l) for l in linhas]


def hora_envio(registro, quando):
    """Hora real do envio: a do PDF do protocolo (gravado logo após o Finalizar); sem ele,
    a do início da execução."""
    for arquivo in (registro or {}).get("arquivos", []):
        if os.path.basename(arquivo).startswith("PROTOC") and os.path.exists(arquivo):
            return datetime.fromtimestamp(os.path.getmtime(arquivo))
    return quando


def ajuste_curto(ajuste):
    """'10/3850650-7 desligada → 3% para a bateria 10/3669135-0 (agora 3%)'."""
    m = RE_AJUSTE.match(ajuste)
    if not m:
        return ajuste
    agora = re.search(r"\(agora ([\d.,]+%)\)", ajuste)
    return (f"{m.group('ucs')} desligada/fora da titularidade → {m.group('pct')}% para a bateria "
            f"{m.group('bateria')}" + (f" (agora {agora.group(1)})" if agora else ""))


def _chip(situacao):
    rotulo, classe = SITUACOES.get(situacao, SITUACOES[None])
    return f'<span class="chip {classe}">{_esc(rotulo)}</span>'


def montar_html(mes, planilhas, resultados, emitido_em):
    usinas = [(p, u) for p in planilhas for u in p.usinas]
    enviados = [r for r, _ in resultados.values() if r.get("situacao") == "portal_enviado"]
    total_benef = sum(len(rateio_enviado(u, resultados.get(u.nome, (None,))[0], p.uc_bateria)) for p, u in usinas)
    total_remov = sum(len(r.get("removidas", [])) for r, _ in resultados.values())
    geradoras = ", ".join(dict.fromkeys(p.geradora for p in planilhas))
    rodape = f"ENERGIA A · Relatório de rateios · {_mes_extenso(mes)}"

    capa = f"""
<section class="capa"><div class="conteudo">
  <img class="logo" src="logo_light.png">
  <div class="chip">RELATÓRIO DE RATEIO · GERAÇÃO DISTRIBUÍDA</div>
  <div class="kicker">Rateio de créditos das usinas</div>
  <h1>Rateios de<br><em>{_esc(_mes_extenso(mes))}</em></h1>
  <div class="barra"></div>
  <div class="sub">Resumo das alterações de beneficiárias enviadas à Energisa e o demonstrativo de cada
  usina com os percentuais distribuídos.</div>
  <div class="numeros">
    <div class="numero"><b>{len(usinas)}</b><span>usinas no mês</span></div>
    <div class="numero"><b>{len(enviados)}</b><span>enviadas com protocolo</span></div>
    <div class="numero"><b>{total_benef}</b><span>beneficiárias</span></div>
    <div class="numero"><b>{total_remov}</b><span>removidas do portal</span></div>
  </div>
</div>
<div class="meta">
  <div><small>Emissor</small><p>ENERGIA A</p></div>
  <div><small>Geradoras</small><p>{_esc(geradoras)}</p></div>
  <div><small>Mês de referência</small><p>{_esc(_mes_extenso(mes))}</p></div>
  <div><small>Emitido em</small><p>{emitido_em:%d/%m/%Y %H:%M}</p></div>
</div></section>"""

    linhas_resumo, ajustes_todos = [], []
    for p, u in usinas:
        registro, quando = resultados.get(u.nome, (None, None))
        quando = hora_envio(registro, quando)
        situacao = (registro or {}).get("situacao")
        benef = rateio_enviado(u, registro, p.uc_bateria)
        linhas_resumo.append(
            f"<tr><td class='nw'><b>{_esc(u.nome)}</b></td>"
            f"<td class='uc'>{_esc(u.uc_geradora)}</td><td>{_chip(situacao)}</td>"
            f"<td class='uc'>{_esc((registro or {}).get('protocolo', '—'))}</td>"
            f"<td class='cen nw'>{f'{quando:%d/%m %H:%M}' if quando else '—'}</td>"
            f"<td class='num'>{len(benef)}</td><td class='num'>{len((registro or {}).get('removidas', []))}</td>"
            f"<td class='num pct'>{_pct(sum(b[2] for b in benef))}</td></tr>")
        ajustes_todos += [f"<b>{_esc(u.nome)}:</b> {_esc(ajuste_curto(a))}" for a in (registro or {}).get("ajustes", [])]

    resumo = f"""
<section class="secao">
  <div class="eyebrow">Visão geral</div><h2 class="titulo">Resumo dos rateios</h2><div class="regra"></div>
  <p class="intro">Situação de cada usina no mês de referência, conforme as execuções do robô de rateio
  no portal da Energisa.</p>
  <table><thead><tr><th>Usina</th><th>UC da usina</th><th>Situação</th><th>Protocolo</th>
  <th class="cen">Enviado em</th><th class="num">Benef.</th><th class="num">Removidas</th><th class="num">Soma</th></tr></thead>
  <tbody>{''.join(linhas_resumo)}</tbody></table>
  {('<div class="nota"><b>Ajustes de distribuição</b> (UC desligada ou fora da titularidade: o percentual vai '
    'para a bateria da geradora)<br>' + '<br>'.join(ajustes_todos) + '</div>') if ajustes_todos else ''}
</section>"""

    demonstrativos = []
    for p, u in usinas:
        registro, quando = resultados.get(u.nome, (None, None))
        quando = hora_envio(registro, quando)
        benef = rateio_enviado(u, registro, p.uc_bateria)
        linhas = "".join(
            f"<tr><td class='cen mini'>{i}</td><td class='uc'>{_esc(uc)}</td>"
            f"<td>{_esc(cliente)}{f'<div class=mini>{_esc(obs)}</div>' if obs else ''}</td>"
            f"<td class='num pct'>{_pct(pct)}</td></tr>"
            for i, (uc, cliente, pct, obs) in enumerate(benef, 1))
        removidas = (registro or {}).get("removidas", [])
        demonstrativos.append(f"""
<section class="secao">
  <div class="eyebrow">Demonstrativo · {_esc(p.geradora)}</div>
  <h2 class="titulo">{_esc(u.nome)}</h2><div class="regra"></div>
  <div class="cards">
    <div class="card"><small>UC da usina</small><b>{_esc(u.uc_geradora)}</b></div>
    <div class="card"><small>Classe</small><b>{_esc(u.classe)}</b></div>
    <div class="card"><small>Enviado em</small><b>{f'{quando:%d/%m/%Y %H:%M}' if quando else '—'}</b></div>
    <div class="card"><small>Protocolo</small><b>{_esc((registro or {}).get('protocolo', '—'))}</b></div>
    <div class="card"><small>Situação</small><b>{_chip((registro or {}).get('situacao'))}</b></div>
  </div>
  <table><thead><tr><th class="cen">#</th><th>UC beneficiária</th><th>Cliente</th><th class="num">%</th></tr></thead>
  <tbody>{linhas}
  <tr class="total"><td></td><td colspan="2">Total distribuído ({len(benef)} beneficiárias)</td>
  <td class="num">{_pct(sum(b[2] for b in benef))}</td></tr></tbody></table>
  {f'<div class="removidas"><b>Removidas no portal ({len(removidas)}):</b> {_esc(", ".join(removidas))}</div>' if removidas else ''}
</section>""")

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório de rateios {_esc(_mes_extenso(mes))}</title>
<link rel="stylesheet" href="estilo.css">
<style>@page {{ @bottom-left {{ content: "{_esc(rodape)}"; }} }}</style></head>
<body>{capa}{resumo}{''.join(demonstrativos)}</body></html>"""


def gerar_relatorio(mes, caminho_pdf=None):
    """Gera o PDF do mês e devolve o caminho."""
    from weasyprint import HTML  # import tardio: só quem gera relatório precisa do weasyprint

    planilhas = [rateio_lista.ler_planilha(c) for c in rateio_lista.listar_planilhas(mes)]
    if not planilhas:
        raise ValueError(f"nenhuma planilha em rateio/lista/{mes}/")
    resultados = carregar_resultados(mes)
    caminho_pdf = caminho_pdf or os.path.join(rateio_lista.PASTA_RATEIO, "relatorios", f"Relatorio_rateios_{mes}.pdf")
    os.makedirs(os.path.dirname(caminho_pdf), exist_ok=True)
    conteudo = montar_html(mes, planilhas, resultados, datetime.now())
    HTML(string=conteudo, base_url=PASTA_TEMPLATE + os.sep).write_pdf(caminho_pdf)
    return caminho_pdf
