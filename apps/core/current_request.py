"""Thread-local que mantém a `HttpRequest` corrente acessível de signals.

`pre_save`/`post_save`/`pre_delete` do ORM recebem só o `sender` e a
`instance` — não recebem `request`. Sem um jeito de saber qual a
requisição que causou a gravação, o handler de admin da BL-244 não tem
como distinguir uma gravação do painel administrativo de uma gravação
interna (ex.: um management command). A solução padrão Django é uma
thread-local preenchida por middleware e lida pelos signals.

`apps.core.middleware.CurrentRequestMiddleware` (registrada em
`settings.MIDDLEWARE`) chama `set_current_request(request)` no início do
request e `clear_current_request()` no fim. Signals e código que precisa
da request chamam `get_current_request()`, que devolve `None` fora de um
request (ex.: testes, scripts, `manage.py shell`).

Por que um módulo separado:
- `apps/core/middleware.py` importa daqui para evitar ciclo
  (middleware -> signals -> ?).
- `apps/auditoria/signals.py` lê daqui sem importar o middleware
  diretamente, e o teste que prova a presença do thread-local
  (`apps/core/tests/test_dl244_*`) também.
"""

import threading

_state = threading.local()


def set_current_request(request):
    """Define a request corrente na thread. Chamado pelo middleware."""
    _state.request = request


def get_current_request():
    """Devolve a request corrente ou `None` se não há uma em curso.

    `None` é a resposta correta fora de um request — testes, scripts
    e `manage.py shell` operam sem request, e o signal handler da BL-244
    usa isso como sinal de "não é uma gravação do admin" e cai fora.
    """
    return getattr(_state, "request", None)


def clear_current_request():
    """Limpa a thread-local no fim do request. Chamado pelo middleware."""
    _state.request = None
