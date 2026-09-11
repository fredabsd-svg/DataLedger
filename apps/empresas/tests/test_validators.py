import pytest
from django.core.exceptions import ValidationError

from apps.empresas.validators import validar_cnpj


def test_cnpj_valido_nao_levanta_erro():
    validar_cnpj("11122233000183")


def test_cnpj_valido_com_mascara_nao_levanta_erro():
    validar_cnpj("11.122.233/0001-83")


def test_cnpj_com_tamanho_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("123")


def test_cnpj_com_todos_digitos_iguais_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("11111111111111")


def test_cnpj_com_digito_verificador_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("11122233000184")
