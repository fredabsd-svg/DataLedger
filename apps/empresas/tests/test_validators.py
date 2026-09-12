"""Testes de validar_cnpj (DL-011: CNPJ alfanumérico, NT 2025.001 / IN RFB 2.229).

Cobre os critérios de aceite 1-9 do plano
docs/planos/DL-011-cnpj-alfanumerico.md. Os critérios 10-13 (revisão de
outros pontos de normalização, persistência no modelo, comentário de fonte e
ausência de regressão) estão registrados no relatório de entrega da etapa;
o critério 11 (persistência sem truncar) tem teste próprio abaixo, que exige
banco de dados.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.empresas.models import Empresa
from apps.empresas.validators import validar_cnpj
from apps.tenancy.models import Escritorio

# CNPJ alfanumérico de referência para os testes: base "AB123CDE0001" com
# DV "55" calculado pelo próprio algoritmo do Anexo I da NT 2025.001 (módulo
# 11, ASCII - 48). Não é um CNPJ real; é dado sintético só para teste.
CNPJ_ALFANUMERICO_VALIDO = "AB123CDE000155"


# Critério 1: os cinco CNPJs numéricos da NT 2025.001 (tabela de
# compatibilidade retroativa) continuam válidos pelo algoritmo novo.
@pytest.mark.parametrize(
    "cnpj",
    [
        "11222333000181",
        "11444777000161",
        "34028316000103",
        "00000000000191",
        "19131243000197",
    ],
)
def test_cnpj_numerico_conhecido_continua_valido(cnpj):
    validar_cnpj(cnpj)


def test_cnpj_valido_nao_levanta_erro():
    validar_cnpj("11122233000183")


def test_cnpj_valido_com_mascara_nao_levanta_erro():
    validar_cnpj("11.122.233/0001-83")


def test_cnpj_com_tamanho_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("123")


def test_cnpj_com_todos_digitos_iguais_e_invalido():
    # Não é uma regra explícita da NT; o DV calculado para "111...1" não
    # confere com os dígitos informados, então é recusado pelo próprio
    # cálculo do módulo 11 (sem exceção especial para dígitos repetidos).
    #
    # Verificação exaustiva (arquiteto-senior, revisão da etapa DL-011): das
    # 36 sequências possíveis de 14 caracteres iguais (dígitos 0-9 e letras
    # A-Z), só "00000000000000" tem o DV calculado coincidindo com os dois
    # últimos caracteres da própria sequência — por isso é a única que
    # precisa de rejeição explícita (ver test_cnpj_zerado_e_invalido); todas
    # as demais, incluindo repetições de letras, já falham naturalmente no
    # cálculo do módulo 11. Não reintroduzir uma exceção genérica para
    # "dígitos repetidos": ela seria redundante e menos fiel à norma.
    with pytest.raises(ValidationError):
        validar_cnpj("11111111111111")


def test_cnpj_com_digito_verificador_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("11122233000184")


# Critério 2: CNPJ alfanumérico com DV correto é aceito.
def test_cnpj_alfanumerico_valido_nao_levanta_erro():
    validar_cnpj(CNPJ_ALFANUMERICO_VALIDO)


# Critério 3: CNPJ alfanumérico com DV incorreto é recusado.
def test_cnpj_alfanumerico_com_digito_verificador_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("AB123CDE000156")


# Critério 4: letras nas posições 13-14 são recusadas (DV é sempre numérico),
# mesmo que o restante do CNPJ seja uma base alfanumérica válida.
def test_cnpj_com_letra_no_digito_verificador_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("AB123CDE00A1B5")


# Critério 5: 13 ou 15 caracteres são recusados.
@pytest.mark.parametrize(
    "cnpj",
    [
        "AB123CDE00015",  # 13 caracteres
        "AB123CDE0001555",  # 15 caracteres
    ],
)
def test_cnpj_com_tamanho_diferente_de_14_e_invalido(cnpj):
    with pytest.raises(ValidationError):
        validar_cnpj(cnpj)


# Critério 6: CNPJ zerado é recusado (o cálculo do módulo 11 daria DV "00"
# por acidente, que coincidiria com os dígitos informados).
def test_cnpj_zerado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("00000000000000")


# Critério 7: máscara aceita e removida, tanto em CNPJ numérico (já coberto
# acima) quanto em alfanumérico.
def test_cnpj_alfanumerico_com_mascara_nao_levanta_erro():
    validar_cnpj("AB.123.CDE/0001-55")


# Critério 8: entrada em minúsculas é normalizada e validada corretamente.
def test_cnpj_alfanumerico_em_minusculas_nao_levanta_erro():
    validar_cnpj(CNPJ_ALFANUMERICO_VALIDO.lower())


def test_cnpj_numerico_em_minusculas_nao_levanta_erro():
    # CNPJ puramente numérico não tem letras, mas o texto pode vir com
    # máscara e outras variações de digitação; garante que a normalização
    # não depende de haver letra alguma no valor.
    validar_cnpj("11.122.233/0001-83".lower())


# Critério 9: caractere fora de [A-Z0-9./-] é recusado com mensagem útil.
def test_cnpj_com_caractere_invalido_e_invalido():
    with pytest.raises(ValidationError, match="alfanuméricos"):
        validar_cnpj("AB123CDE00#155")


# Critério 11: o campo do modelo persiste CNPJ alfanumérico sem truncar
# (max_length=14 já comporta letras; este teste evita regressão silenciosa
# se o campo for alterado no futuro).
@pytest.mark.django_db
def test_empresa_persiste_cnpj_alfanumerico_sem_truncar():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Alfanumérica Ltda",
        cnpj=CNPJ_ALFANUMERICO_VALIDO,
    )

    empresa.refresh_from_db()

    assert empresa.cnpj == CNPJ_ALFANUMERICO_VALIDO
    assert len(empresa.cnpj) == 14
