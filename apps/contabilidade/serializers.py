from rest_framework import serializers

from apps.contabilidade.models import Conta, ItemLancamento, LancamentoContabil
from apps.core.identificadores import IdentificadorInvalido, para_id


class _ContaPaiField(serializers.PrimaryKeyRelatedField):
    """`PrimaryKeyRelatedField` que julga o identificador com `para_id`
    ANTES de qualquer consulta ao banco (achado R5-3 da auditoria DL-017
    rodada 5, BL-142 / DE-034).

    O `PrimaryKeyRelatedField` padrão do DRF (o que o `ModelSerializer`
    geraria sozinho para `conta_pai`) faz `self.get_queryset().get(pk=data)`
    direto — mesma classe de defeito que `_extrair_itens` tinha para
    `item["conta"]` (`apps/contabilidade/views.py`): `1.9` (número JSON)
    resolvia para a conta 1, `"٢"`/`"２"` (dígito Unicode) resolviam para a
    conta 2, sempre com 201 e sem aviso. `to_internal_value` é o ÚNICO
    ponto onde isso pode ser interceptado: `validate_conta_pai` (abaixo)
    já recebe o valor DEPOIS de resolvido para uma instância de `Conta` —
    tarde demais para julgar o texto/número original.
    """

    def to_internal_value(self, data):
        try:
            data = para_id(data)
        except IdentificadorInvalido as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return super().to_internal_value(data)


class ContaSerializer(serializers.ModelSerializer):
    # Declarado explicitamente (não deixado para o `ModelSerializer` gerar
    # sozinho) só para trocar a classe do campo por `_ContaPaiField` — os
    # demais atributos (`queryset`, `required`, `allow_null`) espelham
    # exatamente o que o `ModelSerializer` geraria a partir de
    # `Conta.conta_pai` (`null=True, blank=True`), para não mudar nenhum
    # outro comportamento do campo.
    conta_pai = _ContaPaiField(queryset=Conta.objects.all(), required=False, allow_null=True)

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

        # Impede o ciclo NA ORIGEM também nesta camada (achado 6, DE-008:
        # invariante contábil não mora só em `Model.clean()`, porque o DRF
        # não chama `full_clean()`). Só relevante quando esta validação
        # ocorre sobre uma conta JÁ existente (`self.instance`, uma futura
        # rota de atualização) — uma conta em criação não tem filhos ainda e
        # não pode ser ancestral de nada. O `visitado` evita loop infinito
        # se a cadeia percorrida tiver um ciclo PRÉ-EXISTENTE não relacionado
        # a esta conta (defesa redundante, mesmo espírito do limite de
        # profundidade em `Conta.clean()`).
        if self.instance is not None:
            ancestral = value
            visitado = set()
            while ancestral is not None:
                if ancestral.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        "A conta pai não pode ser a própria conta nem uma conta descendente dela."
                    )
                if ancestral.pk in visitado:
                    break
                visitado.add(ancestral.pk)
                ancestral = ancestral.conta_pai
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
