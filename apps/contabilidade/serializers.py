from rest_framework import serializers

from apps.contabilidade.models import (
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA,
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL,
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE,
    ClassificacaoDlpa,
    ClassificacaoDmpl,
    ClassificacaoDre,
    ClassificacaoFluxoCaixa,
    Conta,
    ItemLancamento,
    LancamentoContabil,
    TipoConta,
    divergencia_entre_dlpa_e_dmpl,
)
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import DadoNaoContratado, recusar_campos_nao_contratados

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
            # DL-063 (BL-606): coluna da DMPL passa a ser **gravável** por
            # aqui, pela MESMA porta e com a MESMA autorização de
            # `classificacao_dre` e `classificacao_dlpa`. Até 04/10/2026 o
            # campo era exposto e `read_only`: a tela de conta nova não o
            # oferecia, e quem integrava por API não tinha **porta nenhuma**
            # para dizer em que coluna a conta entra — a porta própria de
            # classificação (`ContaClassificacaoDmplView`) reclassifica conta
            # EXISTENTE, e não serve para quem está criando a conta. A
            # assimetria saiu por decisão do Fred em 04/10/2026.
            #
            # A porta própria CONTINUA existindo, e não é redundância: ela
            # grava **com trilha antes/depois na mesma transação**, que é o
            # que reclassificar conta com movimento exige. O POST é cadastro
            # INICIAL, que não tem histórico a preservar — são operações
            # diferentes, com contratos diferentes (D2 do plano da DL-063).
            "classificacao_dmpl",
            # DL-066 (etapa 2): os três campos da DFC — EXPPOSTOS para leitura
            # (quem integra precisa ver o que está marcado) e marcados
            # `read_only`, o que significa que **POST e PUT não os gravam**.
            # A escrita destes campos é a porta própria
            # `ContaClassificacaoDfcView`, que grava pelo serviço
            # `classificar_conta_na_dfc` — com `full_clean()` (as coerências
            # de `Conta.clean()`) e trilha antes/depois. Gravá-los por aqui
            # exigiria replicar essas coerências neste serializer (BL-40/
            # DE-008: o DRF não chama `full_clean()`), e a duplicata teria de
            # ser COMPLETA para não virar furo (a lição da DL-063).
            #
            # ⚠️ **A5 (MÉDIO) da auditoria da etapa 2:** `read_only` puro
            # DESCARTAVA em silêncio o que o cliente mandasse (BL-196: dado
            # enviado nunca é ignorado em silêncio). Agora `validate()`
            # RECUSA a chave com 400 e aponta a porta certa. O que permanece
            # em aberto é aceitar a escrita no cadastro inicial, como a
            # decisão D2 da DL-063 fez para `classificacao_dmpl` — decisão do
            # Fred, registrada como BL-631 no backlog.
            "caixa_e_equivalentes",
            "classificacao_dfc",
            "item_de_resultado_sem_caixa",
        ]
        read_only_fields = [
            "caixa_e_equivalentes",
            "classificacao_dfc",
            "item_de_resultado_sem_caixa",
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

    def validate_classificacao_dmpl(self, value):
        """Mesma normalização do achado A4 da DL-045, pelo mesmo motivo, e com
        a mesma ressalva da DLPA: `"remover a classificação"` é operação
        NORMAL, não erro — `null` e `""` significam a mesma coisa e ambos
        gravam `None`. Sem isto, o `ChoiceField` gravaria `""` e a guarda de
        transição de `Conta.clean()` a trataria como "já classificada",
        travando a conta para uma classificação REAL posterior."""
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
        # A5 (MÉDIO) da auditoria da etapa 2 / BL-196: os três campos da DFC
        # são `read_only`, e `read_only` sozinho DESCARTA em silêncio o que
        # chega no corpo. Hoje a PRIMEIRA porta já recusa a chave por nome —
        # o contrato de requisição do cadastro (`CONTRATO_POST_CONTA`), medido
        # em `test_a5_os_campos_da_dfc_no_cadastro_sao_recusados_nunca_
        # descartados` —, e esta é a SEGUNDA: defesa em profundidade para
        # quando uma rota aceitar o corpo sem contrato, e a única que aponta a
        # porta que grava (o PATCH da classificação). Dado enviado nunca é
        # ignorado em silêncio. A checagem é no `initial_data` (o corpo CRÚ)
        # porque o DRF já teria descartado os campos antes de `validate`
        # receber os `attrs`.
        if self.initial_data:
            for campo in (
                "caixa_e_equivalentes",
                "classificacao_dfc",
                "item_de_resultado_sem_caixa",
            ):
                if campo in self.initial_data:
                    raise serializers.ValidationError(
                        {
                            campo: (
                                f'O campo "{campo}" não é gravado por esta porta: '
                                "a classificação da DFC tem porta própria "
                                "(PATCH em "
                                "empresas/<empresa_id>/contas/<conta_id>/"
                                "classificacao-dfc/), que grava com trilha e "
                                "validação da conta. Remova a chave do corpo "
                                "deste POST/PUT e use a porta certa."
                            )
                        }
                    )

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

        # DL-063 (BL-606) — a MESMA checagem para a coluna da DMPL, na fonte
        # única `TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL` (models.py), pelo mesmo
        # motivo das duas de cima: o DRF nunca chama `full_clean()`
        # (BL-40/DE-008), então `Conta.clean()` não roda neste caminho.
        classificacao = attrs.get("classificacao_dmpl")
        if self.instance is not None and "classificacao_dmpl" not in attrs:
            classificacao = self.instance.classificacao_dmpl
        if classificacao:
            tipos_aceitos = TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL.get(classificacao)
            if tipos_aceitos is not None and tipo not in tipos_aceitos:
                rotulo_classificacao = ClassificacaoDmpl(classificacao).label
                rotulos_tipos_aceitos = " ou ".join(TipoConta(t).label for t in tipos_aceitos)
                raise serializers.ValidationError(
                    {
                        "classificacao_dmpl": (
                            f'A coluna "{rotulo_classificacao}" da DMPL não é compatível com o '
                            f"tipo desta conta: só se aplica a contas de tipo "
                            f"{rotulos_tipos_aceitos}."
                        )
                    }
                )

        # DL-063 (BL-606), achado A1 da auditoria: a COERÊNCIA ENTRE AS DUAS
        # CLASSIFICAÇÕES — `divergencia_entre_dlpa_e_dmpl`, a mesma regra que
        # `Conta.clean()` aplica — também precisa ser replicada aqui, e só
        # apareceu depois que a porta abriu. `Conta.clean()` não roda neste
        # caminho (BL-40/DE-008), então, sem estas linhas, a API gravava em
        # silêncio exatamente o par que o modelo proíbe: linha da DLPA
        # "Reserva legal" com coluna da DMPL "Capital social". Na base isso
        # era INALCANÇÁVEL — o contrato recusava a chave —; a porta nova
        # tornou o caminho real, e o buraco nasceu com ela.
        #
        # A apuração nomeia e VETA o par assim gravado (medido na auditoria:
        # `pode_emitir = False`), então o dano é nomeado, não silencioso. Mas
        # gravar pela porta o que a outra porta proíbe é a classe de defeito
        # que o §8 do AGENTS.md manda evitar: aqui a regra é duplicada por
        # necessidade técnica — e duplicata por necessidade precisa ser
        # COMPLETA, senão a duplicata vira furo.
        #
        # Cada classificação é lida do payload ou, num PATCH parcial, da
        # conta — mesmo padrão das checagens acima, porque a divergência é
        # entre as DUAS, e cada uma pode vir só de um lado do payload.
        divergencia = divergencia_entre_dlpa_e_dmpl(
            self._classificacao_do_payload(attrs, "classificacao_dlpa"),
            self._classificacao_do_payload(attrs, "classificacao_dmpl"),
        )
        if divergencia:
            raise serializers.ValidationError({"classificacao_dmpl": divergencia})
        return attrs

    def _classificacao_do_payload(self, attrs, campo):
        """O valor de um campo de classificação no payload **ou**, quando o
        payload não o traz e é uma atualização, o da conta já gravada — sem
        isto, um PATCH que mexesse só na linha da DLPA seria julgado contra
        um `classificacao_dmpl` inexistente e deixaria a coerência de fora."""
        if campo in attrs:
            return attrs[campo]
        if self.instance is not None:
            return getattr(self.instance, campo, None)
        return None

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


class ClassificacaoDmplPatchSerializer(serializers.Serializer):
    """DL-061 (fatia 2, E18): valida o CORPO do `PATCH` de
    `ContaClassificacaoDmplView` ANTES de chegar ao serviço — o espelho
    EXATO de `ClassificacaoDlpaPatchSerializer` (R3 da auditoria DL-045),
    pelos mesmos motivos: corpo malformado não pode vazar como 500 mudo, e
    `ChoiceField` recusa o corpo que não é `Mapping` e o valor que não é uma
    chave do enum.

    O contrato é SEPARADO do da DLPA: a política recusa chave desconhecida
    por NOME, e um corpo com `classificacao_dlpa` neste PATCH tem de ser
    recusado, não aplicado à linha errada em silêncio. `allow_null`/
    `allow_blank` aceitam "remover a coluna" (None), como nas irmãs.
    """

    classificacao_dmpl = serializers.ChoiceField(
        choices=ClassificacaoDmpl.choices, allow_null=True, allow_blank=True, required=False
    )


class ClassificacaoDfcPatchSerializer(serializers.Serializer):
    """DL-066 (etapa 2): valida o CORPO do `PATCH` de
    `ContaClassificacaoDfcView` — os TRÊS campos da DFC de uma conta
    existente, no mesmo molde das irmãs (R3 da auditoria DL-045): corpo
    malformado não vaza como 500 mudo, `ChoiceField` recusa o corpo que não é
    `Mapping` e o valor que não é chave de `ClassificacaoFluxoCaixa`, e
    `BooleanField` recusa `"true"`/`1` crus.

    Aqui só FORMA. As regras — caixa × atividade na mesma conta, item sem
    caixa só em resultado, a guarda de período fechado da DL-065 — são de
    `Conta.clean()`, rodado pelo `classificar_conta_na_dfc` (uma fonte só,
    mesma divisão das irmãs: o serializer julga o tipo; o serviço julga a
    regra). Os campos são `required=False` porque o PATCH é parcial: quem não
    veio no corpo não muda (a fusão acontece na view, que conhece o serviço).
    """

    caixa_e_equivalentes = serializers.BooleanField(required=False)
    classificacao_dfc = serializers.ChoiceField(
        choices=ClassificacaoFluxoCaixa.choices,
        allow_null=True,
        allow_blank=True,
        required=False,
    )
    item_de_resultado_sem_caixa = serializers.BooleanField(required=False)


# DL-061 (fatia 2, BL-605): o corpo do PUT de `MarcacaoDmplView` é o
# CONJUNTO inteiro de marcações de um lançamento — `{linha, coluna, valor}`,
# um por evento, nada além disso (BL-196: dado enviado nunca é ignorado em
# silêncio).
CAMPOS_PERMITIDOS_MARCACAO_DMPL = frozenset({"linha", "coluna", "valor"})


class MarcacaoDmplSerializer(serializers.Serializer):
    """UMA marcação da DMPL no corpo do PUT de `MarcacaoDmplView` (E18).

    Só FORMA é decidida aqui (as três chaves, sem nenhuma a mais; tipos).
    Os enums (`linha` é chave de `_TITULOS_DAS_LINHAS_DA_DMPL`,
    `coluna` é `ClassificacaoDmpl`) e o `valor ≠ 0` são regra de DOMÍNIO e
    moram em `MarcacaoDmpl.clean()` (models.py), rodados por
    `salvar_marcacoes_da_dmpl` — uma fonte só, mesma divisão de
    `ClassificacaoDlpaPatchSerializer` (aqui se julga o tipo; o serviço
    julga a regra).

    `valor` é `JSONField` + checagem de FORMA de envio por um motivo
    específico (DE-030, achado R3-3): dinheiro nesta API viaja como TEXTO.
    Um número JSON (int ou float) é recusado ANTES de qualquer conversão —
    o parser JSON já perdeu a precisão do float antes de o servidor ver o
    valor —, com a mesma orientação do POST de lançamento.
    """

    linha = serializers.CharField(max_length=60)
    coluna = serializers.CharField(max_length=60)
    valor = serializers.JSONField()

    def validate(self, dados):
        # `initial_data` é o item CRÚ: é nele que vivem as chaves não
        # declaradas (o DRF as ignora em silêncio sem esta checagem).
        try:
            recusar_campos_nao_contratados(
                dict(self.initial_data),
                CAMPOS_PERMITIDOS_MARCACAO_DMPL,
                contexto="em uma marcação da DMPL",
            )
        except DadoNaoContratado as exc:
            raise serializers.ValidationError(exc.mensagem) from exc
        return dados

    def validate_valor(self, valor):
        if not isinstance(valor, str):
            raise serializers.ValidationError(
                f"Valor inválido em uma marcação: {valor!r} precisa ser "
                'enviado como TEXTO (ex.: "100.00"), nunca como número JSON — '
                "um número perde precisão ao ser decodificado pelo parser JSON, "
                "antes mesmo de chegar a este servidor."
            )
        try:
            return para_decimal(valor)
        except ValorMonetarioInvalido as exc:
            raise serializers.ValidationError(f"Valor inválido em uma marcação: {exc}") from exc


class MarcacaoDmplGravacaoSerializer(serializers.Serializer):
    """Corpo do PUT de `MarcacaoDmplView` (E18): `{"marcacoes": [...]}`, com
    o CONJUNTO completo — o PUT substitui tudo de uma vez (substituição
    atômica, `salvar_marcacoes_da_dmpl`), e lista VAZIA limpa as marcações.

    A lista é `ListField` (não `many=True` no item) para que "corpo sem a
    chave `marcacoes`", "`marcacoes` que não é lista" e "item malformado"
    tenham cada um a sua recusa de 400, nunca 500 (R3/R8 da auditoria
    DL-045)."""

    marcacoes = serializers.ListField(allow_empty=True)

    def validate_marcacoes(self, itens):
        validadas = []
        for indice, item in enumerate(itens, start=1):
            entrada = MarcacaoDmplSerializer(data=item)
            try:
                entrada.is_valid(raise_exception=True)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({f"marcacoes[{indice}]": exc.detail}) from exc
            validadas.append(entrada.validated_data)
        return validadas


class ItemLancamentoSerializer(serializers.ModelSerializer):
    conta_codigo = serializers.CharField(source="conta.codigo", read_only=True)

    class Meta:
        model = ItemLancamento
        fields = ["id", "conta", "conta_codigo", "tipo", "valor"]


class LancamentoContabilSerializer(serializers.ModelSerializer):
    """Saída do lançamento. Só leitura: a origem é decidida pelo servidor (DL-089).

    `documento_de_origem` sai como objeto `{tipo, identificador}` ou `null` (manual). O
    identificador é o do app de origem, em texto, e não expõe nenhum dado do documento.
    """

    itens = ItemLancamentoSerializer(many=True, read_only=True)
    documento_de_origem = serializers.SerializerMethodField()

    class Meta:
        model = LancamentoContabil
        fields = [
            "id",
            "data",
            "historico",
            "estorno_de",
            "criado_em",
            "origem",
            "documento_de_origem",
            "itens",
        ]
        read_only_fields = ["origem"]

    def get_documento_de_origem(self, lancamento):
        if lancamento.documento_origem_tipo is None:
            return None
        return {
            "tipo": lancamento.documento_origem_tipo,
            "identificador": lancamento.documento_origem_id,
        }
