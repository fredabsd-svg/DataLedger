from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario
from apps.empresas.validators import normalizar_cnpj


def _normalizar_cnpj_do_payload(data):
    """Normaliza ``data["cnpj"]`` antes da validação de campo do DRF.

    O CharField gerado automaticamente pelo ModelSerializer herda
    max_length=14 do model (o CNPJ já canonizado). Sem esta normalização
    prévia, um CNPJ mascarado (até 18 caracteres) é recusado pelo
    MaxLengthValidator antes mesmo de chegar em validar_cnpj — o mesmo
    defeito do formulário (achado 2 da auditoria da etapa DL-011), só que na
    API. ``data`` pode ser um dict comum (JSON) ou um QueryDict imutável
    (form-encoded); ``.copy()`` cobre os dois casos.
    """
    if not (hasattr(data, "get") and isinstance(data.get("cnpj"), str)):
        return data
    data = data.copy()
    try:
        data["cnpj"] = normalizar_cnpj(data["cnpj"])
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"cnpj": exc.messages}) from exc
    return data


class HistoricoRegimeTributarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricoRegimeTributario
        fields = ["id", "regime", "vigencia_inicio", "vigencia_fim"]
        read_only_fields = ["vigencia_fim"]


class EstabelecimentoSerializer(serializers.ModelSerializer):
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

    def to_internal_value(self, data):
        return super().to_internal_value(_normalizar_cnpj_do_payload(data))


class EmpresaSerializer(serializers.ModelSerializer):
    regime_atual = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = ["id", "razao_social", "nome_fantasia", "cnpj", "ativo", "regime_atual"]

    def get_regime_atual(self, empresa):
        vigente = empresa.historico_regime_tributario.filter(vigencia_fim__isnull=True).first()
        return vigente.regime if vigente else None

    def to_internal_value(self, data):
        return super().to_internal_value(_normalizar_cnpj_do_payload(data))

    def create(self, validated_data):
        # Isolamento: a empresa criada pertence sempre ao escritório ativo
        # da requisição, nunca a um escritório informado pelo cliente.
        validated_data["escritorio"] = self.context["request"].escritorio
        return super().create(validated_data)
