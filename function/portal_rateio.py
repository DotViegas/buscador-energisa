"""Passos do portal Energisa para alterar as beneficiárias de uma usina (rateio).

Fluxo mapeado e validado ao vivo em 25/09/2026 (ENERGIA A 6), até a etapa 4:
gerenciamento-gd → Ver detalhes da geradora → Editar unidades beneficiárias →
Iniciar solicitação → 1 Procurar imóveis → 2 Configurar imóveis → 3 Envio de
documentos → 4 Finalização.

Armadilhas do portal:
- Ele renderiza uma CÓPIA do formulário presa no cabeçalho fixo: os mesmos
  botões/campos aparecem duas vezes e só um recebe clique. `clicavel` escolhe o
  elemento que está de fato no ponto de clique (elementFromPoint).
- Na etapa 2, imóvel com 0% vai sozinho para "Unidades que serão removidas", e a
  Finalização quebra ("Application error", ReferenceError numeroUCAneel no JS da
  Energisa) sempre que há removida. Por isso usinas que exigem remoção não passam
  pelo portal: `RemocaoNecessaria` sinaliza para o robô gerar o formulário.
- Checkbox "Li e estou de acordo", botão "Finalizar" e a tela do protocolo nunca
  foram exercitados (o teste parou antes de finalizar): seletores a validar no
  primeiro envio real.
"""
import base64
import re
import time

from function.erros_navegador import TIMEOUT_ERRORS

URL_GERENCIAMENTO = "https://servicos.energisa.com.br/gerenciamento-gd"
TEXTO_ERRO_PORTAL = "Application error"

JS_HIT = r"""e => { e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); if (!r.width) return false;
  const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !!(top && (e.contains(top) || top.contains(e))) }"""
# O input do react-select é estreito: testa a borda esquerda do controle que o envolve.
JS_HIT_COMBO = r"""e => { e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect();
  const top = document.elementFromPoint(r.left + 2, r.top + r.height / 2);
  const ctrl = e.closest('[class*="control"]') || e.parentElement;
  return !!(top && (ctrl.contains(top) || top.contains(e))) }"""


class RemocaoNecessaria(Exception):
    """A usina tem beneficiárias no portal que não estão na planilha."""

    def __init__(self, ucs):
        super().__init__(f"{len(ucs)} beneficiária(s) precisariam ser removidas: {', '.join(ucs)}")
        self.ucs = ucs


class PortalFalhou(Exception):
    """O portal não permitiu concluir o fluxo (tela com erro, passo que não abriu...)."""


# ==================== utilidades ====================

def clicavel(loc, js=JS_HIT):
    for el in loc.all():
        if el.is_visible() and el.evaluate(js):
            return el
    raise PortalFalhou(f"nenhum elemento clicável para {loc}")


def clicar(loc):
    clicavel(loc).click()


def tem_texto(page, texto):
    return page.evaluate("t => document.body.innerText.includes(t)", texto)


def esperar_texto(page, texto, timeout=45000):
    try:
        page.wait_for_function("t => document.body && document.body.innerText.includes(t)",
                               arg=texto, timeout=timeout)
    except TIMEOUT_ERRORS:
        raise PortalFalhou(f"texto não apareceu em {timeout // 1000}s: {texto!r} (URL {page.url})")


def imprimir_pdf(context, page, caminho):
    """Salva a página como no Ctrl+P → Salvar como PDF (cabeçalho com data/hora e título,
    rodapé com URL e páginas). Funciona com o Chrome visível."""
    cdp = context.new_cdp_session(page)
    try:
        pdf = cdp.send("Page.printToPDF", {"printBackground": True, "displayHeaderFooter": True})
    finally:
        cdp.detach()
    with open(caminho, "wb") as f:
        f.write(base64.b64decode(pdf["data"]))
    return caminho


def _numero_uc(texto):
    m = re.search(r"Número da UC:?\s*([\d.]+-\d{2})", texto)
    return m.group(1) if m else ""


# ==================== etapas ====================

def abrir_cadastro(page, uc_usina):
    """Do gerenciamento-gd até a etapa 1 da solicitação. Retorna o número da UC (ANEEL) da usina."""
    page.goto(URL_GERENCIAMENTO, wait_until="domcontentloaded", timeout=45000)
    botao = page.locator(f"xpath=//p[normalize-space()='Código do cliente {uc_usina}']"
                         "/ancestor::div[.//button[@data-testid='btn-mostrarDetalhes']][1]"
                         "//button[@data-testid='btn-mostrarDetalhes']").first
    try:
        botao.wait_for(state="visible", timeout=60000)
    except TIMEOUT_ERRORS:
        raise PortalFalhou(f"geradora {uc_usina} não apareceu em 'Minhas unidades geradoras'")
    card = botao.locator("xpath=ancestor::div[.//p[contains(., 'Número da UC')]][1]")
    numero_usina = _numero_uc(card.inner_text().replace("Número da UC ", "Número da UC: "))
    botao.evaluate("e => e.scrollIntoView({block: 'center'})")
    botao.click()
    page.wait_for_url("**/gerenciamento-gd/detalhes**", timeout=45000)

    editar = page.get_by_role("button", name="Editar unidades beneficiárias")
    editar.first.wait_for(state="attached", timeout=45000)
    clicar(editar)
    page.wait_for_url("**/gerenciamento-gd/cadastro", timeout=45000)
    iniciar = page.get_by_role("button", name="Iniciar solicitação")
    iniciar.first.wait_for(state="attached", timeout=45000)
    clicar(iniciar)
    page.wait_for_function("() => document.body.innerText.includes('Informe o percentual de compensação')"
                           " || document.body.innerText.includes('Imóveis para cadastrar')", timeout=45000)

    if tem_texto(page, "Informe o percentual de compensação"):
        # Passo do guia do usuário (não apareceu em autoconsumo remoto): 0% na geradora.
        clicavel(page.get_by_placeholder("de 0 a 100")).fill("0")
        page.get_by_role("button", name="Entendi").first.wait_for(state="visible", timeout=15000)
        clicar(page.get_by_role("button", name="Entendi"))
        esperar_texto(page, "Imóveis para cadastrar")
    page.locator("input[role='combobox']").first.wait_for(state="attached", timeout=30000)
    return numero_usina


def _campo_busca(page):
    for campo in page.locator("input[role='combobox']").all():
        if campo.is_visible() and campo.evaluate(JS_HIT_COMBO):
            return campo
    raise PortalFalhou("campo de busca de imóveis não encontrado")


def adicionar_uc(page, uc):
    """Etapa 1: busca a UC, guarda os dados do cartão (número da UC e endereço, como o
    portal mostra) e a adiciona. Retorna (situação, dados); situação é 'nova',
    'ja_beneficiaria' ou 'nao_encontrada'."""
    numero = uc.split("/")[-1].split("-")[0]
    campo = _campo_busca(page)
    campo.click()
    campo.press("Control+A")
    campo.press("Backspace")
    campo.press_sequentially(uc, delay=40)
    cartao = page.locator(f"[role='listbox'] [data-testid='uc-card'][data-cdc='{numero}']").first
    try:
        cartao.wait_for(state="visible", timeout=15000)
    except TIMEOUT_ERRORS:
        return "nao_encontrada", {}
    linhas = [l.strip() for l in cartao.inner_text().split("\n") if l.strip()]
    dados = {
        "numero_uc": _numero_uc(" ".join(linhas)),
        "endereco": next((l for l in linhas if not l.startswith(("Número da UC", "Código do cliente"))), ""),
    }
    cartao.click()
    aviso = page.locator(".new-modal__body").filter(has_text="já é sua beneficiária")
    try:
        aviso.first.wait_for(state="visible", timeout=3000)
    except TIMEOUT_ERRORS:
        return "nova", dados
    page.get_by_role("button", name="Entendi").click()
    aviso.first.wait_for(state="hidden", timeout=5000)
    return "ja_beneficiaria", dados


def ir_para_configuracao(page):
    """Da etapa 1 para a 2 (Configurar imóveis). Retorna as UCs listadas pelo portal."""
    campo = _campo_busca(page)
    campo.click()
    campo.press("Control+A")
    campo.press("Backspace")
    page.keyboard.press("Escape")
    clicar(page.get_by_role("button", name="Avançar"))
    page.wait_for_url("**/distribuicao-beneficiarias**", timeout=45000)
    page.locator("input[type='number']").first.wait_for(state="attached", timeout=45000)
    time.sleep(1)
    return [_uc_do_card(c) for c in _cards_visiveis(page)]


def _cards_visiveis(page):
    todos = (page.locator("div.mb-4.rounded-lg").filter(has=page.locator("input[type='number']"))
             .filter(has_text="Remover este imóvel"))
    return [c for c in todos.all()
            if c.locator("input[type='number']").is_visible() and c.locator("input[type='number']").evaluate(JS_HIT)]


def _uc_do_card(card):
    m = re.search(r"Código do cliente\s*(\d{2}/\d{7}-\d)", card.inner_text())
    return m.group(1) if m else None


def preencher_percentuais(page, rateio):
    """Etapa 2: digita o % de cada UC. Localiza o card pela UC a cada vez e usa o
    element_handle, porque o portal re-renderiza a lista ao focar um campo."""
    for uc, percentual in rateio.items():
        encontrado = None
        for card in (page.locator("div.mb-4.rounded-lg").filter(has=page.locator("input[type='number']"))
                     .filter(has_text=f"Código do cliente {uc}")).all():
            campo = card.locator("input[type='number']")
            if campo.is_visible() and campo.evaluate(JS_HIT):
                encontrado = campo.element_handle()
                break
        if encontrado is None:
            raise PortalFalhou(f"card da UC {uc} não encontrado na etapa 2")
        valor = f"{percentual:g}"
        encontrado.click()
        encontrado.press("Control+A")
        encontrado.type(valor, delay=30)
        encontrado.press("Tab")
    total = re.search(r"Total do percentual distribuído \(%\)\s*(\S+)", page.evaluate("document.body.innerText"))
    return total.group(1) if total else "?"


def enviar_documentos(page, docs):
    """Etapas 2→3: avança e envia cartão CNPJ (duas vezes se pedir o comprovante de
    associação civil) e RG (frente/verso) ou CNH. `docs`: cartao_cnpj, tipo ('RG'/'CNH'),
    frente, verso (só RG)."""
    clicar(page.get_by_role("button", name="Avançar"))
    esperar_texto(page, "Centralize e enquadre")
    clicar(page.get_by_role("button", name="Avançar"))
    page.wait_for_function("() => /cart[aã]o CNPJ|associa[cç][aã]o civil/i.test(document.body.innerText)",
                           timeout=45000)
    if tem_texto(page, "associação civil"):
        _enviar_foto(page, docs["cartao_cnpj"], "A foto ficou boa")
        clicar(page.get_by_role("button", name="Avançar"))
        esperar_texto(page, "Envie uma foto do cartão CNPJ")
    _enviar_foto(page, docs["cartao_cnpj"], "A foto ficou boa")
    clicar(page.get_by_role("button", name="Avançar"))
    esperar_texto(page, "Qual documento você quer usar?")

    clicar(page.get_by_test_id(f"tipo-documento-{docs['tipo']}"))
    esperar_texto(page, "Envie a foto da frente")
    _enviar_foto(page, docs["frente"], "Verifique se a foto possui")
    if docs["tipo"] == "RG":
        clicar(page.get_by_role("button", name="Avançar"))
        esperar_texto(page, "Envie a foto do verso")
        _enviar_foto(page, docs["verso"], "Verifique se a foto possui")


def _enviar_foto(page, caminho, texto_previa):
    with page.expect_file_chooser(timeout=15000) as escolha:
        clicar(page.get_by_text("Buscar em seus arquivos"))
    escolha.value.set_files(caminho)
    esperar_texto(page, texto_previa)


def abrir_finalizacao(page):
    """Último Avançar da etapa 3 e espera a etapa 4 carregar sem o erro do portal."""
    clicar(page.get_by_role("button", name="Avançar"))
    try:
        page.wait_for_function(
            "e => document.body && (document.body.innerText.includes('Li e estou de acordo')"
            " || document.body.innerText.includes(e))", arg=TEXTO_ERRO_PORTAL, timeout=60000)
    except TIMEOUT_ERRORS:
        raise PortalFalhou(f"a tela de Finalização não abriu (URL {page.url})")
    time.sleep(2)  # a exceção do portal aparece logo depois da tela renderizar
    if tem_texto(page, TEXTO_ERRO_PORTAL):
        raise PortalFalhou("a tela de Finalização quebrou (Application error do portal)")


class EnvioIncerto(Exception):
    """O clique em Finalizar aconteceu, mas a tela seguinte não é a esperada. A
    solicitação PODE ter sido registrada: nunca gerar formulário nesse caso."""


def finalizar(page):
    """Aceite + Finalizar + espera o protocolo. NÃO VALIDADO ao vivo: conferir no 1º envio.

    Falha ANTES do clique em Finalizar levanta PortalFalhou (nada foi enviado).
    Depois do clique, levanta EnvioIncerto. Retorna o texto da tela do protocolo."""
    clicar(page.get_by_text(re.compile("Li e estou de acordo")))
    botao = page.get_by_role("button", name="Finalizar")
    botao.first.wait_for(state="attached", timeout=15000)
    clicar(botao)
    try:
        page.wait_for_function("() => /protocolo/i.test(document.body.innerText)", timeout=90000)
    except TIMEOUT_ERRORS:
        raise EnvioIncerto(f"Finalizar clicado, mas a tela do protocolo não apareceu (URL {page.url})")
    time.sleep(3)
    return page.evaluate("document.body.innerText")


def extrair_protocolo(texto):
    m = re.search(r"protocolo[^\d]{0,40}(\d[\d./-]{4,})", texto, re.IGNORECASE)
    return m.group(1) if m else ""
