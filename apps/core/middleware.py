"""Middleware do DataLedger.

`CurrentRequestMiddleware`: preenche a thread-local de
`apps.core.current_request` para que signals do ORM (que não recebem
`request` como argumento) possam distinguir uma gravação feita pelo
painel administrativo de uma gravação por management command, teste ou
outro caminho. O signal handler de BL-244 lê essa thread-local para
decidir se a operação veio do admin e qual a `acao` registrar.

Instalada em `settings.MIDDLEWARE` logo após
`django.contrib.auth.middleware.AuthenticationMiddleware`, para que o
`request.user` já esteja populado quando a view rodar (e os signals
tenham `request.user` disponível). É puramente observacional: não
altera a request, não muda resposta, não bloqueia nada.
"""

from apps.core.current_request import clear_current_request, set_current_request


class CurrentRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            return self.get_response(request)
        finally:
            # Limpar no `finally` cobre exceções no `get_response`
            # também — sem isso, a próxima request na mesma thread
            # herdaria a request anterior.
            clear_current_request()
