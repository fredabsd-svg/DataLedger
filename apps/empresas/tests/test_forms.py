"""Testes de formulário para CNPJ (DL-011, reauditoria rodada 2).

Cobre:

- R2 (média): o Django admin gera seu próprio ModelForm a partir do campo
  do modelo (inclusive o *inline* de Estabelecimento, que não tem tela
  própria) e recusava CNPJ mascarado com a mesma mensagem literal do achado
  2 da rodada 1. A correção estrutural aponta ``Empresa.cnpj``/
  ``Estabelecimento.cnpj`` para ``CNPJModelField`` (apps/empresas/fields.py),
  cujo ``formfield()`` devolve um ``CNPJFormField`` — herdado por QUALQUER
  ``ModelForm``, não só ``EmpresaForm``. Testado aqui com
  ``modelform_factory``, a mesma reprodução do auditor.
- R10 (baixa), lado da tela: mensagens de erro para CNPJ vazio, só espaço e
  acima do tamanho válido.
"""

import pytest
from django import forms

from apps.empresas.forms import EmpresaForm
from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


# --- R2: o ModelForm AUTOMÁTICO (o que o admin gera) precisa herdar --------


def test_modelform_automatico_de_empresa_aceita_cnpj_mascarado():
    # Não usa EmpresaForm: modelform_factory gera exatamente o formulário
    # automático que o Django admin usaria, direto do campo do modelo — a
    # mesma reprodução que a auditoria fez para encontrar o R2.
    Form = forms.modelform_factory(Empresa, fields=["razao_social", "nome_fantasia", "cnpj"])
    form = Form(
        data={
            "razao_social": "Empresa do Admin Ltda",
            "nome_fantasia": "",
            "cnpj": "11.122.233/0001-83",
        }
    )

    assert form.is_valid(), form.errors
    empresa = form.save(commit=False)
    assert empresa.cnpj == "11122233000183"


def test_modelform_automatico_de_empresa_aceita_cnpj_alfanumerico_minusculo():
    Form = forms.modelform_factory(Empresa, fields=["razao_social", "nome_fantasia", "cnpj"])
    form = Form(
        data={
            "razao_social": "Empresa Alfanumérica do Admin Ltda",
            "nome_fantasia": "",
            "cnpj": "ab.123.cde/0001-55",
        }
    )

    assert form.is_valid(), form.errors
    empresa = form.save(commit=False)
    assert empresa.cnpj == "AB123CDE000155"


def test_modelform_automatico_de_estabelecimento_aceita_cnpj_mascarado(escritorio):
    # Estabelecimento não tem tela própria: o inline do admin é a única
    # interface humana desse modelo (achado citado explicitamente no R2).
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    Form = forms.modelform_factory(Estabelecimento, fields=["tipo", "nome", "cnpj"])
    form = Form(
        data={
            "tipo": TipoEstabelecimento.MATRIZ,
            "nome": "Matriz",
            "cnpj": "ab.123.cde/0001-55",
        }
    )

    assert form.is_valid(), form.errors
    estabelecimento = form.save(commit=False)
    estabelecimento.empresa = empresa
    assert estabelecimento.cnpj == "AB123CDE000155"


def test_modelform_automatico_de_empresa_recusa_dv_invalido():
    # A correção estrutural não pode abrir mão da validação: continua
    # recusando dígito verificador incorreto, agora sobre o valor
    # canonizado (full_clean() do model roda validar_cnpj).
    Form = forms.modelform_factory(Empresa, fields=["razao_social", "nome_fantasia", "cnpj"])
    form = Form(
        data={
            "razao_social": "Empresa Invalida Ltda",
            "nome_fantasia": "",
            "cnpj": "11.122.233/0001-84",
        }
    )

    assert not form.is_valid()
    assert "cnpj" in form.errors


# --- R10: mensagens de erro na tela ---------------------------------------


def test_empresa_form_cnpj_vazio_da_mensagem_de_obrigatorio():
    form = EmpresaForm(data={"razao_social": "Empresa Ltda", "nome_fantasia": "", "cnpj": ""})

    assert not form.is_valid()
    assert form.errors["cnpj"] == ["Este campo é obrigatório."]


def test_empresa_form_cnpj_so_espaco_da_mensagem_de_obrigatorio():
    form = EmpresaForm(data={"razao_social": "Empresa Ltda", "nome_fantasia": "", "cnpj": "   "})

    assert not form.is_valid()
    assert form.errors["cnpj"] == ["Este campo é obrigatório."]


def test_empresa_form_cnpj_longo_da_mensagem_de_formato_nao_de_tamanho_maximo():
    # Antes (R10, reauditoria rodada 2): "Certifique-se de que o valor
    # tenha no máximo 32 caracteres (ele possui 33)." — número arbitrário
    # que não diz nada para quem digita CNPJ. CNPJFormField não tem
    # MaxLengthValidator (max_length=None): normalizar_cnpj é quem recusa,
    # com a mensagem de formato do CNPJ.
    form = EmpresaForm(data={"razao_social": "Empresa Ltda", "nome_fantasia": "", "cnpj": "A" * 33})

    assert not form.is_valid()
    (mensagem,) = form.errors["cnpj"]
    assert "máximo" not in mensagem
    assert "alfanuméricos" in mensagem
