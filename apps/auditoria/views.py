from rest_framework import generics

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.serializers import RegistroAuditoriaSerializer
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo, papel_permitido


class RegistroAuditoriaListView(generics.ListAPIView):
    """Lista os registros de auditoria do escritório ativo.

    Restrito a administrador/gestor: auditoria pode conter informação
    operacional sensível sobre a atuação de outros usuários do escritório.
    """

    serializer_class = RegistroAuditoriaSerializer
    permission_classes = [TemEscritorioAtivo, papel_permitido(Papel.ADMINISTRADOR, Papel.GESTOR)]

    def get_queryset(self):
        # BL-649 (DL-070): `usuario` é serializado por `StringRelatedField`, que
        # chama `str(usuario)`. Sem `select_related`, cada registro de um usuário
        # diferente fazia uma consulta própria. O filtro por escritório é o
        # isolamento desta rota e continua exatamente igual.
        return RegistroAuditoria.objects.filter(escritorio=self.request.escritorio).select_related(
            "usuario"
        )
