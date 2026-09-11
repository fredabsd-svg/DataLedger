from django.shortcuts import get_object_or_404

from apps.empresas.models import Empresa


class EmpresaEscopadaMixin:
    """Resolve a empresa da URL restrita ao escritório ativo da requisição.

    Reaproveitável por qualquer app que opere sobre uma empresa específica
    (contabilidade e os módulos de negócio futuros). Uma empresa de outro
    escritório resulta em 404, não em 403: não confirma nem a existência do
    registro para quem não tem acesso.
    """

    def get_empresa(self):
        return get_object_or_404(
            Empresa, pk=self.kwargs["empresa_id"], escritorio=self.request.escritorio
        )
