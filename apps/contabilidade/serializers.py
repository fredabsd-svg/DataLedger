from rest_framework import serializers

from apps.contabilidade.models import (
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA,
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE,
    ClassificacaoDlpa,
    ClassificacaoDre,
    Conta,
    ItemLancamento,
    LancamentoContabil,
    TipoConta,
)
from apps.core.identificadores import IdentificadorInvalido, para_id

# DL-058/B1: UMA mensagem só para "a conta pai não é utilizável aqui", seja
# o id de outra empresa (de outro escritório, inclusive) ou inexistente.
# Antes, o id alheio recebia "deve pertencer à mesma empresa" e o
# inexistente recebia 'Invalid pk "N" - object does not exist.' — a
# diferença entre as duas respostas dizia a quem testava ids que o id
# existia em algum lugar (enumeração de contas de outros escritórios).
MENSAGEM_CONTA_PAI_INVALIDA = "A conta pai deve pertencer à mesma empresa."


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

    DL-058/B1: o queryset é restrito à empresa do escopo da requisição, e a
    mensagem de "não existe" é a MESMA da conta de outra empresa — ver
    `MENSAGEM_CONTA_PAI_INVALIDA`.
    """

    default_error_messages = {
        **serializers.PrimaryKeyRelatedField.default_error_messages,
        "does_not_exist": MENSAGEM_CONTA_PAI_INVALIDA,
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        empresa = self.context.get("empresa")
        if empresa is None:
            # Sem empresa no contexto NÃO se restringe aqui: quem falha
            # fechado nesse caso é `validate_conta_pai` (erro de uso do
            # serializer, 400 explícito). Restringir a "nenhuma conta"
            # esconderia o esquecimento atrás da mensagem de id inválido.
            return queryset
        return queryset.filter(empresa=empresa)

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
            # DL-048 (fatia D8): linha da DLPA — exposta e aceita pela MESMA
            # porta e a MESMA autorização de `classificacao_dre`, porque é o
            # mesmo molde (CTB-12: campo fixo na conta, classificado pelo
            # contador, nunca inferido). A compatibilidade com `tipo` é
            # verificada em `validate`, na fonte única
            # `TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA` — igual à da DRE, e pelo
            # mesmo motivo: o DRF nunca chama `full_clean()` (BL-40/DE-008),
            # então `Conta.clean()` não roda neste caminho.
            "classificacao_dlpa",
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

    def validate_classificacao_dlpa(self, value):
        """Mesma normalização do achado A4 da DL-045, pelo mesmo motivo: o
        `ChoiceField` do `ModelSerializer` aceita `""` e a guarda de
        transição de `Conta.clean()` trataria `""` como "já classificada",
        travando a conta para uma classificação REAL posterior.

        ⚠️ `"remover a classificação"` é operação NORMAL nesta API, não
        erro: `null` e `""` significam a mesma coisa e ambos gravam `None`
        (é assim que `classificar_conta_na_dlpa` normaliza)."""
        return value or None

    def validate(self, attrs):
        """Compatibilidade da classificação × `tipo` — mesma regra de
        `Conta.clean()`, repetida aqui porque o DRF NUNCA chama
        `full_clean()` (achado BL-40/DE-008, o mesmo motivo de
        `validate_conta_pai`). Cross-field: mora em `validate()`, não em
        `validate_<campo>`, porque depende de `tipo`, outro campo do mesmo
        payload.

        Duas classificações, DUAS fontes de verdade, e é proposital: a DRE
        vem do art. 187 da Lei 6.404/76 e a DLPA do art. 186 (mesma lei) —
        classificações de linhas diferentes não podem compartilhar a mesma
        tabela de tipos aceitos. Cada uma consulta a sua, e a validação do
        tipo da conta é a MESMA (`tipo`), porque é a mesma conta.
        """
        tipo = attrs.get("tipo")
        if tipo is None and self.instance is not None:
            tipo = self.instance.tipo

        classificacao = attrs.get("classificacao_dre")
        if self.instance is not None and "classificacao_dre" not in attrs:
            classificacao = self.instance.classificacao_dre
        if classificacao:
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

        # DL-048 (fatia D8) — mesma checagem, fonte `TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA`
        # (models.py), que é a fonte ÚNICA do que cada linha da DLPA aceita.
        classificacao = attrs.get("classificacao_dlpa")
        if self.instance is not None and "classificacao_dlpa" not in attrs:
            classificacao = self.instance.classificacao_dlpa
        if classificacao:
            tipos_aceitos = TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA.get(classificacao)
            if tipos_aceitos is not None and tipo not in tipos_aceitos:
                rotulo_classificacao = ClassificacaoDlpa(classificacao).label
                rotulos_tipos_aceitos = " ou ".join(TipoConta(t).label for t in tipos_aceitos)
                raise serializers.ValidationError(
                    {
                        "classificacao_dlpa": (
                            f'A linha da DLPA "{rotulo_classificacao}" não é compatível com o '
                            f"tipo desta conta: só se aplica a contas de tipo "
                            f"{rotulos_tipos_aceitos}."
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
        contra um `empresa_id` que o cliente possa enviar. O `queryset` declarado
        no campo continua `Conta.objects.all()` (a empresa só existe no
        contexto da requisição), mas `_ContaPaiField.get_queryset` o restringe
        à empresa do contexto (DL-058/B1) — esta checagem fica como segunda
        camada, e a fail-closed de contexto sem empresa mora aqui.
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
            # Defesa em profundidade: o campo já restringe o queryset à
            # empresa (DL-058/B1), então este ramo só alcança quem chamar
            # o validador com uma instância já resolvida. Mesma mensagem.
            raise serializers.ValidationError(MENSAGEM_CONTA_PAI_INVALIDA)

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


class ClassificacaoDrePatchSerializer(serializers.Serializer):
    """R3 (auditoria DL-045, reconferência): valida o CORPO do `PATCH` de
    `ContaClassificacaoDreView` (views.py) ANTES de chegar ao serviço —
    sem isto, um corpo malformado vazava como 500, mudo, em dois pontos
    diferentes: `request.data.get("classificacao_dre")`, na view, quebra
    com `AttributeError` quando o corpo TODO é uma lista (`["x"]`, não
    tem `.get`); e `TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE.get(valor)`, em
    `Conta.clean()` (models.py), quebra com `TypeError: unhashable type`
    quando `valor` é um `dict` ou uma `list` (`{"classificacao_dre": {"a":
    1}}` ou `{"classificacao_dre": ["receita_bruta"]}`).

    `ChoiceField` sozinho já cobre os dois casos: um corpo que não é
    `Mapping` (`Serializer.to_internal_value`) recusa com 400 antes de
    examinar qualquer campo; um valor não-`str` que não bate com nenhuma
    chave de `ClassificacaoDre.choices` (`choice_strings_to_values`, que
    compara por `str(data)`) recusa com `invalid_choice`, nunca estoura
    `TypeError`/`KeyError` cru. `allow_null`/`allow_blank` continuam
    aceitando "sem classificação" (`None`/`""`, achado A4) — só o TIPO do
    valor é a preocupação nova aqui; a compatibilidade com `Conta.tipo`
    continua sendo decidida só por `Conta.clean()`, via
    `classificar_conta_na_dre` (nunca duplicada aqui)."""

    classificacao_dre = serializers.ChoiceField(
        choices=ClassificacaoDre.choices, allow_null=True, allow_blank=True, required=False
    )


class ClassificacaoDlpaPatchSerializer(serializers.Serializer):
    """DL-048 (fatia D8): valida o CORPO do `PATCH` de
    `ContaClassificacaoDlpaView` ANTES de chegar ao serviço.

    É a MESMA defesa de `ClassificacaoDrePatchSerializer` (R3 da auditoria
    DL-045), e pelos mesmos motivos: sem isto, um corpo malformado vazaria
    como 500 mudo em dois pontos — `request.data.get("classificacao_dlpa")`
    na view quebra com `AttributeError` quando o corpo TODO é uma lista
    (`["x"]`, não tem `.get`), e `TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA.get`
    em `Conta.clean()` quebra com `TypeError: unhashable type` quando o
    valor é `dict` ou `list`.

    `ChoiceField` cobre os dois: corpo que não é `Mapping` recusa com 400
    antes de examinar campo algum; valor não-`str` que não bate com nenhuma
    chave de `ClassificacaoDlpa.choices` recusa com `invalid_choice`.
    `allow_null`/`allow_blank` continuam aceitando "remover a classificação"
    — REMOVER é operação normal, não erro.
    """

    classificacao_dlpa = serializers.ChoiceField(
        choices=ClassificacaoDlpa.choices, allow_null=True, allow_blank=True, required=False
    )


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
