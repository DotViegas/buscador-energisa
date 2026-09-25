"""Exceções de timeout do navegador, compatíveis com Playwright e Patchright.

O Patchright (usado pelo robo_v2.py) lança patchright._impl._errors.TimeoutError,
que NÃO herda do TimeoutError do Playwright. Quem trata timeout deve usar
`except TIMEOUT_ERRORS` para funcionar com os dois robôs.
"""
from playwright.sync_api import TimeoutError as _PlaywrightTimeoutError

try:
    from patchright.sync_api import TimeoutError as _PatchrightTimeoutError
    TIMEOUT_ERRORS = (_PlaywrightTimeoutError, _PatchrightTimeoutError)
except ImportError:  # patchright não instalado: só o robo.py antigo roda
    TIMEOUT_ERRORS = (_PlaywrightTimeoutError,)
