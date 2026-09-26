"""Testes da CheckConstraint de FORMATO do CNPJ (DL-010, etapa BL-54).

Relação com `test_canonizacao_constraint.py`: aquele arquivo prova que a
CheckConstraint `empresa_cnpj_canonico`/`estabelecimento_cnpj_canonico` barra
valores NÃO CANÔNICOS (minúsculo, caractere fora de A-Z0-9) por
``bulk_create``/``bulk_update``/``QuerySet.update()``, que não passam por
``Model.save()``/``normalizar_cnpj``/``validar_cnpj``. Este arquivo é novo (em
vez de acrescentar casos ao arquivo existente) para não misturar com aquele
teste, mas prova a mesma família de defeito por um ângulo diferente: antes da
BL-54, a condição da constraint garantia CANONICIDADE mas não FORMATO — um
valor como ``"AB123CDE0001AA"`` (13 caracteres alfanuméricos + letra no lugar
do segundo dígito verificador) já é canônico (só A-Z0-9, maiúsculo) e passava
pela constraint antiga sem ser CNPJ nenhum. A BL-54 combinou a condição de
canonicidade com uma exigência de formato (regex do Anexo I da NT 2025.001,
``^[A-Z0-9]{12}[0-9]{2}$`` — mesma regex de ``apps.empresas.validators.
_FORMATO_CNPJ``, expressa como ``Q`` porque a constraint roda no banco).

IMPORTANTE, e repetido do módulo de origem: esta constraint confere FORMATO,
não o dígito verificador (módulo 11). ``"AB123CDE000199"`` tem formato válido
(14 caracteres, 2 últimos numéricos) mas pode ter DV incorreto — a
constraint aceita porque não recalcula módulo 11 em SQL; só
``apps.empresas.validators.validar_cnpj`` faz essa conferência, e só nos
caminhos que chamam ``full_clean()``/serializer, não em ``bulk_create``.

Todas as asserções prendem a constraint pelo NOME
(``empresa_cnpj_canonico``/``estabelecimento_cnpj_canonico``), no mesmo
padrão do arquivo irmão: uma renomeação ou remoção futura da constraint deve
ser notada por estes testes, não silenciada por outro IntegrityError
qualquer.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.empresas.tests.test_validators import CNPJ_ALFANUMERICO_VALIDO
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

# Os três valores de CNPJ malformado que o critério 23 do plano (DL-010,
# BL-54) exige cobrir por `bulk_create`, todos já canônicos (só A-Z0-9,
# maiúsculo) e por isso já aceitos pela condição ANTIGA da constraint — só a
# exigência de FORMATO (acrescentada nesta etapa) os recusa:
CASOS_CNPJ_FORMATO_INVALIDO = [
    pytest.param("", id="vazio"),
    pytest.param("ABC", id="curto_nao_alfanumerico_no_tamanho_certo"),
    # 13 caracteres alfanuméricos + "A" no lugar do segundo dígito
    # verificador: o caso que distingue formato de canonicidade — é
    # canônico (só A-Z0-9) mas não tem os 2 últimos caracteres numéricos.
    pytest.param("AB123CDE0001AA", id="letra_no_lugar_do_digito_verificador"),
]


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório BL-54", cnpj="11111111000111")


@pytest.mark.parametrize("cnpj_invalido", CASOS_CNPJ_FORMATO_INVALIDO)
def test_bulk_create_empresa_com_formato_invalido_e_barrado_pelo_banco(escritorio, cnpj_invalido):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Empresa.objects.bulk_create(
            [
                Empresa(
                    escritorio=escritorio,
                    razao_social="Empresa Formato Invalido Ltda",
                    cnpj=cnpj_invalido,
                )
            ]
        )

    assert "empresa_cnpj_canonico" in str(excinfo.value)


@pytest.mark.parametrize("cnpj_invalido", CASOS_CNPJ_FORMATO_INVALIDO)
def test_bulk_create_estabelecimento_com_formato_invalido_e_barrado_pelo_banco(
    escritorio, cnpj_invalido
):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Estabelecimento.objects.bulk_create(
            [
                Estabelecimento(
                    empresa=empresa,
                    tipo=TipoEstabelecimento.MATRIZ,
                    nome="Matriz Formato Invalido",
                    cnpj=cnpj_invalido,
                )
            ]
        )

    assert "estabelecimento_cnpj_canonico" in str(excinfo.value)


def test_bulk_create_empresa_com_cnpj_alfanumerico_valido_continua_aceito(escritorio):
    # Não-regressão: CNPJ alfanumérico canônico E de formato válido (mesma
    # constante usada em apps/empresas/tests/test_validators.py como
    # CNPJ_ALFANUMERICO_VALIDO) precisa continuar passando pela constraint
    # reforçada — a BL-54 soma uma exigência, não deve recusar dado que já
    # era válido.
    Empresa.objects.bulk_create(
        [
            Empresa(
                escritorio=escritorio,
                razao_social="Empresa Alfanumerica Valida Ltda",
                cnpj=CNPJ_ALFANUMERICO_VALIDO,
            )
        ]
    )

    assert Empresa.objects.filter(cnpj=CNPJ_ALFANUMERICO_VALIDO).exists()


def test_bulk_create_estabelecimento_com_cnpj_numerico_valido_continua_aceito(escritorio):
    # Não-regressão com CNPJ puramente numérico e DV correto (mesmo valor
    # usado como CNPJ válido em vários outros testes do projeto, ex.
    # apps/empresas/tests/test_validators.py).
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa B Ltda", cnpj="11122233000183"
    )

    Estabelecimento.objects.bulk_create(
        [
            Estabelecimento(
                empresa=empresa,
                tipo=TipoEstabelecimento.MATRIZ,
                nome="Matriz Numerica Valida",
                cnpj="11222333000181",
            )
        ]
    )

    assert Estabelecimento.objects.filter(cnpj="11222333000181").exists()
