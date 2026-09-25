from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.empresas.fields import CNPJSerializerField, CPFSerializerField
from apps.empresas.models import (
    Empresa,
    Estabelecimento,
    HistoricoRegimeTributario,
    ModoEscrituracao,
    TipoInscricao,
)
from apps.empresas.services import (
    erros_de_consistencia_de_inscricao,
    modo_escrituracao_sugerido,
    recusar_transicao_para_cpf_com_estabelecimento,
    recusar_transicao_para_livro_caixa_com_movimento,
)
from apps.empresas.services import mensagem_cnpj_duplicado as _mensagem_cnpj_duplicado

# CNPJSerializerField é declarado explicitamente nos dois serializers abaixo
# (não é o CharField automático do ModelSerializer), então precisa repor à
# mão o UniqueValidator que o ModelSerializer geraria sozinho para um campo
# unique=True. A mensagem vem de apps.empresas.services.mensagem_cnpj_duplicado
# — a mesma usada por views.py para o caso de corrida (R4 da reauditoria da
# etapa DL-011), para as duas rotas darem exatamente o mesmo texto.


class HistoricoRegimeTributarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricoRegimeTributario
        fields = ["id", "regime", "vigencia_inicio", "vigencia_fim"]
        read_only_fields = ["vigencia_fim"]


class EstabelecimentoSerializer(serializers.ModelSerializer):
    # Declarado explicitamente (não o CharField automático do
    # ModelSerializer): CNPJSerializerField normaliza e valida dentro do
    # laço por-campo do DRF, o que preserva a agregação de erros com os
    # demais campos (R7 da reauditoria da etapa DL-011). UniqueValidator
    # precisa ser reposto à mão pelo mesmo motivo — campo explícito não
    # herda os validadores que o ModelSerializer geraria sozinho.
    cnpj = CNPJSerializerField(
        validators=[
            UniqueValidator(
                queryset=Estabelecimento.objects.all(),
                message=_mensagem_cnpj_duplicado(Estabelecimento),
            )
        ]
    )

    class Meta:
        model = Estabelecimento
        fields = [
            "id",
            "tipo",
            "nome",
            "cnpj",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "municipio",
            "uf",
            "cep",
            "ativo",
        ]


class EmpresaSerializer(serializers.ModelSerializer):
    # DL-038: `cnpj`/`cpf` deixam de ser sempre obrigatórios — exatamente
    # um dos dois é exigido, conforme `tipo_inscricao` (checado em
    # `validate`, porque é regra ENTRE campos, e o DRF só garante que os
    # dois já passaram pela normalização individual antes de `validate`
    # rodar). `allow_blank=True` é o que faz o DRF pular `to_internal_
    # value` (e os `validators`, inclusive o `UniqueValidator` abaixo) para
    # entrada vazia — ver a docstring de `CPFSerializerField`.
    cnpj = CNPJSerializerField(
        required=False,
        allow_blank=True,
        default="",
        validators=[
            UniqueValidator(
                queryset=Empresa.objects.all(), message=_mensagem_cnpj_duplicado(Empresa)
            )
        ],
    )
    cpf = CPFSerializerField(
        required=False,
        allow_blank=True,
        default="",
        validators=[
            UniqueValidator(
                queryset=Empresa.objects.all(),
                message=_mensagem_cnpj_duplicado(Empresa, "CPF"),
            )
        ],
    )
    # `required=False`/`default=`: cliente de API existente, que não manda
    # estes dois campos, continua criando empresa CNPJ/contabilidade
    # exatamente como antes de DL-038 (R1/R4) — o `default` do CAMPO do
    # serializer (não só o da coluna do banco) é o que garante isso mesmo
    # quando o campo está ausente do payload.
    tipo_inscricao = serializers.ChoiceField(
        choices=TipoInscricao.choices, required=False, default=TipoInscricao.CNPJ
    )
    # Achado B5 (auditoria rodada 1): SEM `default=` fixo — um `default=`
    # de campo sempre preencheria `modo_escrituracao` em `attrs`, mesmo
    # quando o cliente não mandou nada, e `validate()` não teria como
    # distinguir "cliente pediu contabilidade" de "cliente não disse
    # nada". A SUGESTÃO de HI-23 (livro-caixa para CPF novo) é aplicada
    # explicitamente em `validate()`, com `apps.empresas.services.modo_
    # escrituracao_sugerido` — a MESMA função que `EmpresaForm` (tela)
    # chama, para a tela e a API nunca mais decidirem diferente para o
    # mesmo pedido.
    modo_escrituracao = serializers.ChoiceField(choices=ModoEscrituracao.choices, required=False)
    regime_atual = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = [
            "id",
            "razao_social",
            "nome_fantasia",
            "tipo_inscricao",
            "cnpj",
            "cpf",
            "modo_escrituracao",
            "ativo",
            "regime_atual",
        ]

    def get_regime_atual(self, empresa):
        vigente = empresa.historico_regime_tributario.filter(vigencia_fim__isnull=True).first()
        return vigente.regime if vigente else None

    def validate(self, attrs):
        # DL-038 (R1/R2/R7): consistência CRUZADA entre tipo_inscricao,
        # cnpj e cpf — a MESMA invariante que a CheckConstraint
        # "empresa_inscricao_consistente_com_tipo" (apps/empresas/models.py)
        # garante no banco, checada aqui ANTES da gravação para devolver
        # 400 com mensagem por campo em vez de um IntegrityError genérico.
        # `getattr(self.instance, ...)` é o valor ATUAL em PATCH parcial —
        # um PATCH que só envia `{"nome_fantasia": "..."}` não deve exigir
        # que o cliente reenvie cnpj/cpf/tipo_inscricao. A REGRA em si mora
        # só em `apps.empresas.services.erros_de_consistencia_de_inscricao`
        # (achado B1 da auditoria: fonte única, também usada pelo admin).
        tipo = attrs.get("tipo_inscricao", getattr(self.instance, "tipo_inscricao", None))
        cnpj = attrs.get("cnpj", getattr(self.instance, "cnpj", ""))
        cpf = attrs.get("cpf", getattr(self.instance, "cpf", ""))

        erros = erros_de_consistencia_de_inscricao(tipo, cnpj, cpf)
        if erros:
            raise serializers.ValidationError(erros)

        # HI-23 (achado B5 da auditoria): só se aplica na CRIAÇÃO
        # (`self.instance is None`) e só quando o cliente OMITIU
        # `modo_escrituracao` de verdade (nunca sobrescreve uma escolha
        # explícita, mesmo igual à sugestão) — mesmo contrato de
        # `EmpresaForm.clean()`. PATCH que omite o campo mantém o valor
        # ATUAL sem mudança nenhuma (semântica de atualização parcial);
        # não é papel desta sugestão reabrir esse caso.
        if self.instance is None and "modo_escrituracao" not in attrs:
            attrs["modo_escrituracao"] = modo_escrituracao_sugerido(tipo)

        # R6: transição PARA livro-caixa com movimento existente. Só se
        # aplica em ATUALIZAÇÃO (`self.instance` existe) — uma empresa
        # nova nunca tem plano de contas nem lançamento ainda. A REGRA
        # (condição + mensagem) mora só em `apps.empresas.services.
        # recusar_transicao_para_livro_caixa_com_movimento` — aqui só se
        # traduz o `ValidationError` do Django para o formato do DRF.
        if self.instance is not None and "modo_escrituracao" in attrs:
            try:
                recusar_transicao_para_livro_caixa_com_movimento(
                    self.instance,
                    modo_anterior=self.instance.modo_escrituracao,
                    modo_novo=attrs["modo_escrituracao"],
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"modo_escrituracao": exc.messages}) from exc

        # R7 (achado B2 da auditoria): mesmo padrão do R6 acima, agora para
        # `tipo_inscricao` — trocar para CPF com estabelecimento gravado
        # deixaria o cadastro inconsistente. A REGRA mora só em
        # `apps.empresas.services.recusar_transicao_para_cpf_com_
        # estabelecimento`.
        if self.instance is not None and "tipo_inscricao" in attrs:
            try:
                recusar_transicao_para_cpf_com_estabelecimento(
                    self.instance,
                    tipo_anterior=self.instance.tipo_inscricao,
                    tipo_novo=attrs["tipo_inscricao"],
                )
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"tipo_inscricao": exc.messages}) from exc

        return attrs

    def create(self, validated_data):
        # Isolamento: a empresa criada pertence sempre ao escritório ativo
        # da requisição, nunca a um escritório informado pelo cliente.
        validated_data["escritorio"] = self.context["request"].escritorio
        return super().create(validated_data)
