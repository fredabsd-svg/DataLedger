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

    def validate_conta_pai(self, value):
        """`conta_pai` deve pertencer à mesma empresa do escopo da requisição.

        O DRF não chama `Model.full_clean()`, então `Conta.clean()` (que faz
        esta mesma checagem) nunca executa neste caminho — é a causa raiz do
        achado BL-40 (DE-008). A validação precisa ser repetida aqui, na
        fronteira da API, contra a empresa resolvida pela view a partir do
        escopo da requisição (`EmpresaEscopadaMixin.get_empresa()`), nunca
        contra um `empresa_id` que o cliente possa enviar. O queryset do campo
        continua sem restrição (`Conta.objects.all()`, padrão do
        `ModelSerializer`) porque a comparação depende do contexto da
        requisição, não é algo expressável só pelo dado do formulário.
        """
        if value is None:
            return value

        empresa = self.context.get("empresa")
        if empresa is None:
            # Falha FECHADA, de propósito: isto é um controle de isolamento
            # entre empresas (BL-40), não uma conveniência de UX. Se alguma
            # view futura reaproveitar este serializer e esquecer de popular
            # `context["empresa"]`, o vazamento entre empresas voltaria de
            # forma silenciosa — sem nenhum teste acusando, porque nenhuma
            # requisição real chegaria a esse estado hoje. Recusar aqui torna
            # o esquecimento visível (400 na hora, e não um vazamento mudo).
            raise serializers.ValidationError(
                "Não foi possível validar a empresa de 'conta_pai': "
                "contexto sem empresa. Isto é um erro de uso do serializer, "
                "não do cliente da API — reporte ao desenvolvedor."
            )
        if value.empresa_id != empresa.id:
            raise serializers.ValidationError("A conta pai deve pertencer à mesma empresa.")
        return value


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
