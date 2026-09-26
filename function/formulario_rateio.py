"""Gera o formulário Energisa "Alteração e cadastro de unidades consumidoras no sistema de
compensação" (réplica fiel da versão 2026-01) com quantas beneficiárias forem precisas.

O modelo oficial (PDF do Word) tem só 5 linhas na tabela e, como cada formulário
"cancela e substitui qualquer solicitação anterior" da geradora, não dá para dividir uma
usina em vários formulários. Este gerador usa o template em
templates/formulario_compensacao/ (mesmo timbrado, textos e fontes do original): a tabela
cresce, o cabeçalho dela se repete a cada página e o texto segue abaixo normalmente.

Uso:
    from function.formulario_rateio import Beneficiaria, Titular, gerar_formulario
    gerar_formulario("saida.pdf", uc_geradora="1.259.175.051-07",
                     beneficiarias=[Beneficiaria("110.633.051-81", "10/3895028-3", ..., 30), ...],
                     titular=Titular(nome=..., cnpj=...))
"""
import html
import os
import string
from dataclasses import dataclass
from datetime import date

PASTA_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "templates", "formulario_compensacao")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro")
VAZIO_CURTO = "____________"
VAZIO_LONGO = "_______________"


@dataclass
class Beneficiaria:
    numero_uc: str          # número da UC (formato ANEEL, ex. 839.239.051-35)
    codigo_cliente: str     # código do cliente Energisa (ex. 10/3702627-5)
    titular: str
    cpf_cnpj: str
    endereco: str
    percentual: float


@dataclass
class Titular:
    nome: str
    cnpj: str = ""
    cpf: str = ""
    email_1: str = ""
    email_2: str = ""
    telefone_residencial: str = ""
    telefone_comercial: str = ""


def titular_padrao():
    """Titular configurado no .env (FORM_TITULAR_*), usado quando nenhum é informado."""
    import config
    return Titular(
        nome=config.FORM_TITULAR_NOME, cnpj=config.FORM_TITULAR_CNPJ, cpf=config.FORM_TITULAR_CPF,
        email_1=config.FORM_TITULAR_EMAIL_1, email_2=config.FORM_TITULAR_EMAIL_2,
        telefone_residencial=config.FORM_TITULAR_TELEFONE_RESIDENCIAL,
        telefone_comercial=config.FORM_TITULAR_TELEFONE_COMERCIAL,
    )


def _esc(texto):
    return html.escape(str(texto or ""))


def _campo(valor, vazio):
    """Valor sublinhado no texto corrido; sem valor, os sublinhados do original."""
    return f'<span class="campo">{_esc(valor)}</span>' if valor not in (None, "") else vazio


def formatar_percentual(valor):
    """Até duas casas decimais, vírgula como separador (regra do formulário: ex. 6,75%)."""
    texto = f"{round(float(valor), 2):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") + "%"


def _linhas_tabela(beneficiarias):
    linhas = []
    for b in beneficiarias:
        uc = "<br>".join(_esc(v) for v in (b.numero_uc, b.codigo_cliente) if v)
        linhas.append(
            f'    <tr><td>{uc}</td><td class="tit">{_esc(b.titular)}</td><td>{_esc(b.cpf_cnpj)}</td>'
            f'<td class="end">{_esc(b.endereco)}</td><td class="pct">{formatar_percentual(b.percentual)}</td></tr>')
    return "\n".join(linhas)


def montar_html(uc_geradora, beneficiarias, titular, percentual_geradora=0, uc_saldo_residual="",
                cidade="Campo Grande", data=None):
    soma = round(sum(float(b.percentual) for b in beneficiarias) + float(percentual_geradora or 0), 2)
    if soma > 100:
        raise ValueError(f"Soma dos percentuais = {soma}% (o formulário aceita no máximo 100%)")
    data = data or date.today()
    with open(os.path.join(PASTA_TEMPLATE, "formulario.html"), encoding="utf-8") as f:
        modelo = string.Template(f.read())
    return modelo.substitute(
        uc_geradora=_campo(uc_geradora, VAZIO_CURTO),
        linhas_tabela=_linhas_tabela(beneficiarias),
        # o rótulo já diz "(%)": só o número
        percentual_geradora=_campo(formatar_percentual(percentual_geradora).rstrip("%")
                                   if percentual_geradora is not None else "", "______"),
        uc_saldo_residual=_campo(uc_saldo_residual, VAZIO_LONGO),
        titular_nome=_esc(titular.nome), titular_cpf=_esc(titular.cpf), titular_cnpj=_esc(titular.cnpj),
        email_1=_esc(titular.email_1), email_2=_esc(titular.email_2),
        telefone_residencial=_esc(titular.telefone_residencial),
        telefone_comercial=_esc(titular.telefone_comercial),
        cidade=_campo(cidade, VAZIO_LONGO), dia=f"{data.day:02d}", mes=MESES[data.month - 1], ano=data.year,
    )


def gerar_formulario(caminho_pdf, uc_geradora, beneficiarias, titular=None, **opcoes):
    """Gera o PDF do formulário. Sem `titular`, usa o do .env (titular_padrao).
    `opcoes`: percentual_geradora, uc_saldo_residual, cidade, data."""
    from weasyprint import HTML  # import tardio: só quem gera formulário precisa do weasyprint

    conteudo = montar_html(uc_geradora, beneficiarias, titular or titular_padrao(), **opcoes)
    os.makedirs(os.path.dirname(os.path.abspath(caminho_pdf)), exist_ok=True)
    HTML(string=conteudo, base_url=PASTA_TEMPLATE + os.sep).write_pdf(caminho_pdf)
    return caminho_pdf
