"""Cadastro público restrito à criação de um novo ambiente isolado."""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.empresas.validators import normalizar_cnpj, validar_cnpj
from apps.tenancy.models import Escritorio


class CadastroForm(forms.Form):
    nome = forms.CharField(label="Nome do responsável", max_length=150)
    email = forms.EmailField(
        label="E-mail", max_length=150, help_text="Você usará este e-mail para entrar."
    )
    nome_escritorio = forms.CharField(label="Nome do escritório", max_length=200)
    cnpj = forms.CharField(label="CNPJ", max_length=18, help_text="Com ou sem pontuação.")
    password1 = forms.CharField(
        label="Senha",
        strip=False,
        max_length=128,
        widget=forms.PasswordInput,
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = forms.CharField(
        label="Confirme a senha", strip=False, max_length=128, widget=forms.PasswordInput
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        autocomplete = {
            "nome": "name",
            "email": "username",
            "nome_escritorio": "organization",
            "cnpj": "off",
            "password1": "new-password",
            "password2": "new-password",
        }
        for name, field in self.fields.items():
            field.widget.attrs["autocomplete"] = autocomplete[name]
            ids = []
            if field.help_text:
                ids.append(f"id_{name}_helptext")
            if self.is_bound and name in self.errors:
                field.widget.attrs["aria-invalid"] = "true"
                ids.append(f"id_{name}_error")
            if ids:
                field.widget.attrs["aria-describedby"] = " ".join(ids)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if (
            get_user_model()
            .objects.filter(Q(email__iexact=email) | Q(username__iexact=email))
            .exists()
        ):
            raise ValidationError("Este e-mail já está em uso. Entre com sua conta.")
        return email

    def clean_cnpj(self):
        cnpj = normalizar_cnpj(self.cleaned_data["cnpj"])
        validar_cnpj(cnpj)
        if Escritorio.objects.filter(cnpj=cnpj).exists():
            raise ValidationError(
                "Este CNPJ já está cadastrado. Entre com sua conta ou procure o administrador."
            )
        return cnpj

    def clean(self):
        data = super().clean()
        password = data.get("password1")
        if password and data.get("password2") and password != data["password2"]:
            self.add_error("password2", "As senhas não conferem.")
        if password:
            usuario = get_user_model()(
                username=data.get("email", ""),
                email=data.get("email", ""),
                first_name=data.get("nome", ""),
            )
            try:
                password_validation.validate_password(password, usuario)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return data


class LoginForm(AuthenticationForm):
    """Preserva usuários legados e aceita variação de caixa do novo login por e-mail."""

    def clean(self):
        username = self.cleaned_data.get("username", "")
        Usuario = get_user_model()
        # O nome exato legado sempre prevalece. Só normalizar quando a conta
        # usa o próprio e-mail canônico como username (contrato do cadastro).
        if "@" in username and not Usuario.objects.filter(username=username).exists():
            canonical = username.lower()
            if Usuario.objects.filter(username=canonical, email__iexact=canonical).exists():
                self.cleaned_data["username"] = canonical
        return super().clean()
