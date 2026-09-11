from django import forms

from apps.empresas.models import Empresa


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = ["razao_social", "nome_fantasia", "cnpj"]
