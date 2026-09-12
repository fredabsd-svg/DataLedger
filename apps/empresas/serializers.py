from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.empresas.fields import CNPJSerializerField
from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario


def _mensagem_cnpj_duplicado(model):
    # Mesmo texto que o DRF geraria sozinho para um CharField unique=True
    # gerado automaticamente (ver rest_framework.utils.field_mapping),
    # construído aqui porque CNPJSerializerField é declarado explicitamente
    # nos dois serializers abaixo — e um campo declarado explicitamente não
    # herda o UniqueValidator automático do ModelSerializer. Usar
    # model._meta.verbose_name em vez de escrever "empresa"/"estabelecimento"
    # à mão mantém a mensagem em sincronia se o verbose_name mudar.
    return f"{model._meta.verbose_name} com este CNPJ já existe."


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
    cnpj = CNPJSerializerField(
        validators=[
            UniqueValidator(
                queryset=Empresa.objects.all(), message=_mensagem_cnpj_duplicado(Empresa)
            )
        ]
    )
    regime_atual = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = ["id", "razao_social", "nome_fantasia", "cnpj", "ativo", "regime_atual"]

    def get_regime_atual(self, empresa):
        vigente = empresa.historico_regime_tributario.filter(vigencia_fim__isnull=True).first()
        return vigente.regime if vigente else None

    def create(self, validated_data):
        # Isolamento: a empresa criada pertence sempre ao escritório ativo
        # da requisição, nunca a um escritório informado pelo cliente.
        validated_data["escritorio"] = self.context["request"].escritorio
        return super().create(validated_data)
