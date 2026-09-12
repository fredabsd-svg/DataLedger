from django import forms

from apps.empresas.models import Empresa


class EmpresaForm(forms.ModelForm):
    # Não precisa mais declarar nem normalizar o campo "cnpj" aqui: o campo
    # do modelo agora é CNPJModelField (apps/empresas/fields.py), cujo
    # formfield() já devolve um CNPJFormField com a normalização embutida
    # em to_python() e sem o MaxLengthValidator baseado no max_length=14 do
    # banco. É a correção estrutural do achado R2 da reauditoria da etapa
    # DL-011: antes, só este formulário normalizava (em clean_cnpj); o
    # Django admin gerava seu próprio ModelForm a partir do model e
    # continuava recusando CNPJ mascarado. Apontar o campo do MODELO para
    # CNPJModelField faz qualquer ModelForm — este, o do admin, o inline —
    # herdar o comportamento certo, sem duplicar lógica.
    class Meta:
        model = Empresa
        fields = ["razao_social", "nome_fantasia", "cnpj"]
