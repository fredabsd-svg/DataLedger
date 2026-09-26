from rest_framework import serializers

from apps.contabilidade.models import (
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE,
    ClassificacaoDre,
    Conta,
    ItemLancamento,
    LancamentoContabil,
    TipoConta,
)
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
            # DL-045/RC-118: linha da DRE — exposta e aceita pela MESMA
            # porta e a MESMA autorização de hoje (nenhuma permission_class
            # nova; `ContaListCreateView` já exige `PodeEscriturar` no
            # POST e `PodeLerContabilidade` no GET, ver views.py). Ao
            # contrário de `classificacao_patrimonial` (DL-033, que nunca
            # ganhou porta de API — só admin), este campo é a primeira vez
            # que uma classificação de conta é aceita por aqui; ver
            # `validate` abaixo para a checagem de compatibilidade com
            # `tipo` (o `Conta.clean()` não roda neste caminho — DRF não
            # chama `full_clean()`, achado BL-40/DE-008).
            "classificacao_dre",
        ]

    def validate_classificacao_dre(self, value):
        """A4 (auditoria DL-045, rodada 1): normaliza `""` para `None` —
        NUNCA recusa. O `ChoiceField` que o `ModelSerializer` gera por
        padrão para este campo (`blank=True` no modelo) aceita `""` e
        gravava do jeito que chegou; a guarda de transição de `Conta.
        clean()` tratava `""` como "já classificada" (`is not None`), o
        que travava a conta para sempre — a primeira classificação REAL,
        depois do `""`, era recusada como reclassificação. `validate_
        <campo>` roda ANTES de `validate()` (objeto), então `attrs.get(
        "classificacao_dre")` já chega `None` quando o cliente mandou
        `""` — a checagem de compatibilidade com `tipo`, abaixo, nem
        examina o valor branco."""
        return value or None

    def validate(self, attrs):
        """Compatibilidade `classificacao_dre` × `tipo` (Lei 6.404/76, art.
        187) — mesma regra de `Conta.clean()`, repetida aqui porque o DRF
        NUNCA chama `full_clean()` (achado BL-40/DE-008, o mesmo motivo de
        `validate_conta_pai`). Cross-field: mora em `validate()`, não em
        `validate_classificacao_dre`, porque depende de `tipo`, outro
        campo do mesmo payload.
        """
        classificacao = attrs.get("classificacao_dre")
        if self.instance is not None and "classificacao_dre" not in attrs:
            classificacao = self.instance.classificacao_dre
        if not classificacao:
            return attrs

        tipo = attrs.get("tipo")
        if tipo is None and self.instance is not None:
            tipo = self.instance.tipo

        tipos_aceitos = TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE.get(classificacao)
        if tipos_aceitos is not None and tipo not in tipos_aceitos:
            rotulo_classificacao = ClassificacaoDre(classificacao).label
            rotulos_tipos_aceitos = " ou ".join(TipoConta(t).label for t in tipos_aceitos)
            raise serializers.ValidationError(
                {
                    "classificacao_dre": (
                        f'A linha da DRE "{rotulo_classificacao}" não é compatível com o '
                        f"tipo desta conta: só se aplica a contas de tipo "
                        f"{rotulos_tipos_aceitos} (Lei 6.404/76, art. 187)."
                    )
                }
            )
        return attrs

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
