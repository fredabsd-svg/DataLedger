"""Formulários de entrada do acesso: bootstrap do primeiro escritório e convite.

DL-070 (BL-645, BL-646, BL-647). Por que existem: entrada de CNPJ e de e-mail
chega do navegador sem garantia nenhuma, e antes deles a view gravava o valor
cru. Com isso, `cnpj='abc'` entrava no banco, uma máscara de 18 caracteres dava
500 na coluna de 14, e e-mail malformado virava convite. A validação fica aqui,
na fronteira, e reusa as mesmas funções do cadastro público — não há regra de
CNPJ nova.
"""

from django import forms
from django.core.exceptions import ValidationError

from apps.empresas.validators import normalizar_cnpj, validar_cnpj
from apps.tenancy.models import Escritorio

# Limites das colunas de `apps.tenancy.models`. Iguais aos do modelo, porque
# valor acima deles é exatamente o que o PostgreSQL recusava com 500.
LIMITE_NOME_ESCRITORIO = 200
# A máscara `XX.XXX.XXX/XXXX-XX` tem 18 caracteres. Texto acima disso não pode
# ser um CNPJ com máscara, então é recusado com mensagem de tamanho antes de
# chegar à normalização.
LIMITE_CNPJ_COM_MASCARA = 18
# Mesmo limite do `EmailField` padrão da coluna `ConviteEscritorio.email`.
LIMITE_EMAIL = 254

# Mensagem única de CNPJ já cadastrado. O formulário a usa na checagem prévia e
# a view a usa quando a corrida chega ao banco (IntegrityError), para o usuário
# ver o mesmo texto nos dois caminhos.
MENSAGEM_CNPJ_JA_CADASTRADO = (
    "Este CNPJ já está cadastrado. Entre com sua conta ou procure o administrador."
)


class PrimeiroEscritorioForm(forms.Form):
    """Nome e CNPJ do primeiro escritório, validados como no cadastro público.

    `clean_cnpj` faz o mesmo que `CadastroForm.clean_cnpj`
    (apps/accounts/forms.py): normaliza, valida os dígitos verificadores e
    recusa CNPJ já cadastrado. Ficou duplicado de propósito e não importado
    porque aquele método depende de `self` do formulário de cadastro; a regra
    de CNPJ continua a mesma, só a mensagem de duplicidade é repetida.
    """

    nome = forms.CharField(
        max_length=LIMITE_NOME_ESCRITORIO,
        error_messages={
            "max_length": (
                f"O nome do escritório pode ter no máximo {LIMITE_NOME_ESCRITORIO} caracteres."
            ),
        },
    )
    cnpj = forms.CharField(
        max_length=LIMITE_CNPJ_COM_MASCARA,
        error_messages={
            "max_length": (
                f"CNPJ inválido: use no máximo {LIMITE_CNPJ_COM_MASCARA} caracteres, "
                "com ou sem máscara."
            ),
        },
    )

    def clean_cnpj(self):
        cnpj = normalizar_cnpj(self.cleaned_data["cnpj"])
        validar_cnpj(cnpj)
        # Checagem prévia, só para dar a mensagem sem ir ao banco. Ela NÃO basta
        # sozinha: duas requisições simultâneas com o mesmo CNPJ podem passar
        # aqui ao mesmo tempo. A segunda é recusada pela unicidade do banco no
        # INSERT, e a view `bootstrap_primeiro_acesso` converte esse
        # IntegrityError na mesma mensagem (BL-645, DL-070), sem 500.
        if Escritorio.objects.filter(cnpj=cnpj).exists():
            raise ValidationError(MENSAGEM_CNPJ_JA_CADASTRADO)
        return cnpj


class ConviteEmailForm(forms.Form):
    """E-mail do convidado. `forms.EmailField` usa `validate_email` como
    validador padrão, o mesmo de `django.core.validators`; o `max_length`
    acrescenta o limite de tamanho que a coluna impõe.
    """

    email = forms.EmailField(
        max_length=LIMITE_EMAIL,
        error_messages={
            "required": "E-mail do convidado é obrigatório.",
            "invalid": "E-mail do convidado inválido.",
            "max_length": f"E-mail do convidado pode ter no máximo {LIMITE_EMAIL} caracteres.",
        },
    )
