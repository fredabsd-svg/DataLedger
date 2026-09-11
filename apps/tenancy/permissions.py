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


def papel_permitido(*papeis):
    """Cria uma permissão DRF que exige um dos papéis informados.

    O papel vem de request.papel, resolvido pelo EscritorioAtivoMiddleware a
    partir do vínculo do usuário com o escritório ativo — nunca de um valor
    enviado pelo cliente. Usar sempre junto de TemEscritorioAtivo, já que
    sem escritório ativo request.papel é None.
    """

    class PapelPermitido(BasePermission):
        message = f"Papel sem permissão para esta operação (requer: {', '.join(papeis)})."

        def has_permission(self, request, view):
            return getattr(request, "papel", None) in papeis

    return PapelPermitido
