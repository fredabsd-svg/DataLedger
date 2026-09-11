from rest_framework.permissions import BasePermission


class TemEscritorioAtivo(BasePermission):
    """Exige um escritório ativo já resolvido pelo EscritorioAtivoMiddleware.

    Sem um escritório ativo não há como saber a qual escritório uma
    operação de negócio (empresa, lançamento, tarefa etc.) pertence.
    """

    message = "Nenhum escritório ativo selecionado."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, "escritorio", None) is not None
        )
