"""Fixtures compartilhadas dos testes de `apps.fiscal`.

Os CNPJs de `empresa_a` (prestador) e `empresa_a2` (tomador) coincidem de
propósito com `CNPJ_PRESTADOR_PADRAO`/`CNPJ_TOMADOR_PADRAO` de
`xml_sinteticos.py`: assim o caso de sucesso PADRÃO (`xml_nfse()`, sem
sobrescrever nada) já gera dois vínculos dentro do MESMO escritório
("os dois clientes" do plano), sem precisar repetir CNPJ em cada teste.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.empresas.models import Empresa
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO, CNPJ_TOMADOR_PADRAO
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio


@pytest.fixture
def escritorio_a():
    return Escritorio.objects.create(nome="Escritório Fiscal A", cnpj="11111111000111")


@pytest.fixture
def escritorio_b():
    return Escritorio.objects.create(nome="Escritório Fiscal B", cnpj="22222222000122")


@pytest.fixture
def empresa_a(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Prestadora A Ltda", cnpj=CNPJ_PRESTADOR_PADRAO
    )


@pytest.fixture
def empresa_a2(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Tomadora A2 Ltda", cnpj=CNPJ_TOMADOR_PADRAO
    )


@pytest.fixture
def empresa_b(escritorio_b):
    return Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B Ltda", cnpj="77888999000155"
    )


def _criar_usuario_com_papel(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    if escritorio is not None and papel is not None:
        VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def usuario_gestor_a(escritorio_a):
    return _criar_usuario_com_papel("gestor-fiscal-a", escritorio_a, Papel.GESTOR)


@pytest.fixture
def usuario_analista_a(escritorio_a):
    return _criar_usuario_com_papel("analista-fiscal-a", escritorio_a, Papel.ANALISTA)


@pytest.fixture
def usuario_cliente_a(escritorio_a):
    return _criar_usuario_com_papel("cliente-fiscal-a", escritorio_a, Papel.CLIENTE)


@pytest.fixture
def usuario_sem_vinculo():
    return _criar_usuario_com_papel("sem-vinculo-fiscal", None, None)
