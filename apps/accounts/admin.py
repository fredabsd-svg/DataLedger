from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin do usuário da plataforma.

    DL-052 (decisão do Fred, 30/09/2026): **usuário se desativa, não se
    apaga.** Um usuário que já escriturou é autor de lançamento efetivado
    (`LancamentoContabil.criado_por`, `Competencia.fechada_por`/
    `entregue_por` — `on_delete=PROTECT`) e figura na trilha de auditoria;
    apagá-lo seria apagar ou quebrar essa autoria. Por isso o admin não
    oferece exclusão — nem pela tela individual, nem pela ação em massa
    "Excluir selecionados" (o Django só lista a ação quando
    `has_delete_permission` permite). `has_delete_permission` devolve False
    também para superusuário: a restrição é do produto, não do papel.

    Para tirar o acesso de alguém, desmarque "Ativo" (`is_active=False`): o
    login passa a ser recusado, e o histórico do usuário permanece.
    """

    def has_delete_permission(self, request, obj=None):
        return False
