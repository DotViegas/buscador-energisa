import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://servicos.energisa.com.br/login")
    page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").click()
    page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").click()
    page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").click()
    page.get_by_role("textbox", name="Digite o seu CPF ou CNPJ").fill("29.698.168/0001-02")
    page.get_by_role("button", name="Entrar").click()
    page.get_by_role("button", name="ícone de um celular azul 67*****2038").click()
    page.get_by_role("textbox", name="Dígito 1 do código").click()
    page.get_by_role("textbox", name="Dígito 1 do código").fill("7")
    page.get_by_role("textbox", name="Dígito 2 do código").fill("0")
    page.get_by_role("textbox", name="Dígito 3 do código").fill("0")
    page.get_by_role("textbox", name="Dígito 4 do código").fill("3")
    page.goto("https://servicos.energisa.com.br/login/listagem-ucs")

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)

# <div class="max-h-[40vh] space-y-2 overflow-y-auto border-t border-gray-300 py-4"><div><button class="flex w-full items-center justify-between rounded-lg border border-gray-300 bg-white p-4 text-left transition-all hover:border-gray-600 disabled:cursor-wait disabled:opacity-50"><div class="flex h-full w-full flex-col items-start justify-center gap-3 pr-2"><div class="flex flex-col-reverse items-start gap-2 sm:flex-row sm:items-center"><span class="font-semibold text-gray-900">MAR COMERCIO DE CALCADOS E CONFECCOES LTDA</span><span class="h-fit rounded-full border-1 border-solid border-gray-800 px-[4px] py-[2px] text-ds-xxs font-normal leading-none text-gray-900">TITULAR</span></div><div class="flex flex-col items-start gap-2 xs:flex-row xs:items-center"><span class="font-semibold text-gray-900">Código do Cliente:</span><span class="font-normal text-gray-900">10/3702471-8</span></div><span class="mt-1 text-ds-sm font-normal text-gray-700">AVE DOS CAFEZAIS, 1421, SALAO, CAMPO GRANDE / MS</span></div><div class="flex items-center justify-end"><svg data-testid="icon-chevron-right" width="24" height="24" xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" fill="currentColor" class="text-gray-800"><path d="M517.85-480 354.92-642.92q-8.3-8.31-8.5-20.89-.19-12.57 8.5-21.27 8.7-8.69 21.08-8.69 12.38 0 21.08 8.69l179.77 179.77q5.61 5.62 7.92 11.85 2.31 6.23 2.31 13.46t-2.31 13.46q-2.31 6.23-7.92 11.85L397.08-274.92q-8.31 8.3-20.89 8.5-12.57.19-21.27-8.5-8.69-8.7-8.69-21.08 0-12.38 8.69-21.08L517.85-480Z"></path></svg></div></button></div></div>