from django import forms

from apps.empresas.models import Empresa
from apps.empresas.validators import normalizar_cnpj


class EmpresaForm(forms.ModelForm):
    # Campo declarado explicitamente, não o gerado automaticamente pelo
    # ModelForm a partir do model. O campo do model tem max_length=14 (o
    # CNPJ já canonizado); se usássemos o campo automático, o
    # MaxLengthValidator(14) rodaria sobre o valor CRU digitado pelo usuário
    # — que com máscara tem até 18 caracteres — e bloquearia antes de
    # normalizar_cnpj tirar a máscara. Era exatamente isso que a auditoria
    # da etapa DL-011 reproduziu (achado 2): CNPJ mascarado, o uso normal,
    # sendo recusado com "no máximo 14 caracteres". Ao normalizar aqui, em
    # clean_cnpj, o valor que chega ao full_clean() do model (chamado pelo
    # ModelForm) já está canônico, com 14 caracteres, e o MaxLengthValidator
    # do model passa a validar o valor certo.
    cnpj = forms.CharField(label="CNPJ", max_length=32)

    class Meta:
        model = Empresa
        fields = ["razao_social", "nome_fantasia", "cnpj"]

    def clean_cnpj(self):
        return normalizar_cnpj(self.cleaned_data["cnpj"])
