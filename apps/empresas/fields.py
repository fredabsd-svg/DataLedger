"""Campos de formulário, modelo e serializer para CNPJ (DL-011).

Ponto único de integração de ``normalizar_cnpj``/``validar_cnpj`` com os três
lugares que o Django e o DRF geram formulário/campo automaticamente a partir
do modelo: ``ModelForm`` (tela e Django admin, inclusive *inline*) e
``ModelSerializer`` (API). Existe por causa do achado 2 da rodada 1 e do R2
da reauditoria (rodada 2) da etapa DL-011: normalizar só dentro de um
``clean_cnpj`` ou de um ``to_internal_value`` escrito à mão resolve **um**
formulário por vez — e o Django admin, que gera o seu próprio ``ModelForm``
a partir do campo do modelo, ficou de fora, recusando CNPJ mascarado com a
mesma mensagem literal do achado 2 original.

Apontar ``Empresa.cnpj``/``Estabelecimento.cnpj`` para ``CNPJModelField``
resolve isso na raiz: qualquer ``ModelForm`` — o da tela, o do admin, o
*inline*, ou um que alguém crie depois — herda ``CNPJFormField`` através de
``Field.formfield()``, que é o método que o Django chama para construir o
campo de formulário a partir do campo de modelo.
"""

from django import forms
from django.db import models
from rest_framework import serializers

from apps.empresas.validators import normalizar_cnpj, normalizar_cpf, validar_cnpj, validar_cpf


class CNPJFormField(forms.CharField):
    """CharField de formulário que normaliza CNPJ antes dos validadores.

    ``to_python`` roda ANTES de ``validate()``/``run_validators()`` no
    ``Field.clean()`` do Django — inclusive antes de qualquer
    ``MaxLengthValidator``. Por isso o valor que chega aos validadores já
    está canônico (14 caracteres, maiúsculo, sem máscara): um
    ``MaxLengthValidator`` baseado no ``max_length=14`` do banco (o
    canônico) nunca vê o texto cru de até 18 caracteres que o usuário
    digitou com máscara.

    Não valida o dígito verificador aqui — isso é responsabilidade de
    ``validar_cnpj``, acionado pelo ``full_clean()`` do model (chamado pelo
    ``ModelForm`` em ``_post_clean()``) sobre o valor já canonizado. Uma
    regra, um lugar: este campo só normaliza.
    """

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            # Vazio/só espaço: devolve como está, para o required() do
            # próprio campo dar "Este campo é obrigatório." — não a
            # mensagem de formato do CNPJ (R10 da reauditoria da etapa
            # DL-011: a tela já fazia isso certo; preservar).
            return value
        return normalizar_cnpj(value)


class CNPJModelField(models.CharField):
    """CharField de modelo cujo formulário automático usa CNPJFormField.

    ``formfield()`` é o método que ``ModelForm._meta.model``/Django admin
    chamam para construir o campo de formulário a partir deste campo de
    modelo — inclusive para o formulário automático do admin e do
    *inline*, que não passam por ``EmpresaForm`` nenhum. Fixamos
    ``max_length=None`` no formulário (não confundir com o ``max_length``
    da COLUNA do banco, que continua 14 e não muda): dispensamos o
    ``MaxLengthValidator`` genérico do form porque ``normalizar_cnpj``
    (dentro do ``CNPJFormField.to_python``) já impõe o tamanho certo, com
    mensagem específica — em vez da mensagem sem sentido para quem digita
    CNPJ ("no máximo 32 caracteres"), que era o achado R10 da reauditoria.
    """

    def formfield(self, **kwargs):
        defaults = {"form_class": CNPJFormField, "max_length": None}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class CNPJSerializerField(serializers.CharField):
    """CharField do DRF que normaliza e valida CNPJ dentro do laço por-campo.

    ``to_internal_value`` roda dentro de ``Serializer.to_internal_value()``,
    que já captura ``django.core.exceptions.ValidationError`` por campo e
    continua para os demais — em vez de abortar a requisição inteira no
    primeiro erro. A versão anterior desta etapa normalizava no
    ``to_internal_value`` do SERIALIZER (antes de chamar ``super()``), fora
    desse laço: um payload com dois defeitos (CNPJ malformado e
    ``razao_social`` ausente) devolvia só o erro do CNPJ (R7 da reauditoria).

    Aceita CNPJ enviado como número JSON (ex.: ``11222333000181`` sem
    aspas): ``CharField.to_internal_value`` do DRF já converte ``int``/
    ``float`` para string antes de chegar aqui. Decisão do
    `arquiteto-senior`, registrada na reauditoria (R9/M18): cliente de API
    em linguagem sem tipagem forte manda número sem perceber, e recusar
    isso é atrito sem ganho.

    Não define ``max_length``: ``validar_cnpj`` já impõe o tamanho e o
    formato certos, com mensagem específica, antes de qualquer
    ``MaxLengthValidator`` genérico entrar em jogo.
    """

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        validar_cnpj(data)
        return normalizar_cnpj(data)


class CPFFormField(forms.CharField):
    """CharField de formulário que normaliza CPF antes dos validadores —
    mesmo molde de `CNPJFormField` (DL-038, R2). `to_python` roda ANTES de
    `validate()`/`run_validators()`, então o valor que chega aos
    validadores já está canônico (11 dígitos, sem máscara).
    """

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            # Vazio: devolve como está — quem decide se CPF é obrigatório
            # (tipo de inscrição CPF ou CNPJ) é a validação cruzada de
            # `Empresa`/`EmpresaSerializer`, não este campo isoladamente.
            return value
        return normalizar_cpf(value)


class CPFModelField(models.CharField):
    """CharField de modelo cujo formulário automático usa CPFFormField —
    mesmo molde de `CNPJModelField`."""

    def formfield(self, **kwargs):
        defaults = {"form_class": CPFFormField, "max_length": None}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class CPFSerializerField(serializers.CharField):
    """CharField do DRF que normaliza e valida CPF dentro do laço por-campo
    — mesmo molde de `CNPJSerializerField`. Só roda a validação quando o
    valor NÃO é vazio: `allow_blank=True` faz o DRF pular `to_internal_
    value` inteiramente para entrada em branco (contrato de `Field.
    validate_empty_values`), então uma empresa CNPJ que não envie `cpf`
    nunca aciona `validar_cpf` — a obrigatoriedade cruzada com o tipo de
    inscrição é responsabilidade de `EmpresaSerializer.validate`.
    """

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        validar_cpf(data)
        return normalizar_cpf(data)
