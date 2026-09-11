from rest_framework import serializers

from apps.auditoria.models import RegistroAuditoria


class RegistroAuditoriaSerializer(serializers.ModelSerializer):
    usuario = serializers.StringRelatedField()

    class Meta:
        model = RegistroAuditoria
        fields = ["id", "usuario", "acao", "objeto_tipo", "objeto_id", "detalhes", "criado_em"]
