from rest_framework import serializers

from apps.contabilidade.models import Conta, ItemLancamento, LancamentoContabil


class ContaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conta
        fields = [
            "id",
            "codigo",
            "nome",
            "tipo",
            "natureza",
            "conta_pai",
            "aceita_lancamento",
            "ativo",
        ]


class ItemLancamentoSerializer(serializers.ModelSerializer):
    conta_codigo = serializers.CharField(source="conta.codigo", read_only=True)

    class Meta:
        model = ItemLancamento
        fields = ["id", "conta", "conta_codigo", "tipo", "valor"]


class LancamentoContabilSerializer(serializers.ModelSerializer):
    itens = ItemLancamentoSerializer(many=True, read_only=True)

    class Meta:
        model = LancamentoContabil
        fields = ["id", "data", "historico", "estorno_de", "criado_em", "itens"]
