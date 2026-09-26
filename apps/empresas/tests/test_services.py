from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, Estabelecimento, RegimeTributario, TipoEstabelecimento
from apps.empresas.services import (
    CNPJDuplicado,
    erro_de_cnpj_duplicado_como_400,
    mensagem_se_cnpj_duplicado,
    registrar_regime_tributario,
)
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )


def test_novo_regime_fecha_o_periodo_anterior(empresa):
    primeiro = registrar_regime_tributario(
        empresa, RegimeTributario.SIMPLES_NACIONAL, date(2024, 1, 1)
    )

    segundo = registrar_regime_tributario(
        empresa, RegimeTributario.LUCRO_PRESUMIDO, date(2025, 1, 1)
    )

    primeiro.refresh_from_db()
    assert primeiro.vigencia_fim == date(2024, 12, 31)
    assert segundo.vigencia_fim is None
    assert segundo.regime == RegimeTributario.LUCRO_PRESUMIDO


def test_nao_permite_vigencia_anterior_ao_periodo_atual(empresa):
    registrar_regime_tributario(empresa, RegimeTributario.SIMPLES_NACIONAL, date(2024, 6, 1))

    with pytest.raises(ValueError):
        registrar_regime_tributario(empresa, RegimeTributario.LUCRO_REAL, date(2024, 1, 1))


# --- A3/N8: a guarda de mensagem_se_cnpj_duplicado contra a armadilha da
# DL-007 (converter TODO IntegrityError em erro de cliente) existia só como
# código, sem teste. O mutante que troca "if modelo is None: return None"
# por "modelo = Empresa" traduziria qualquer IntegrityError — de FK, de
# outra unique constraint, da própria CheckConstraint de canonicidade — em
# "CNPJ já existe", mascarando defeito de sistema como erro do cliente.
# Estes três testes fixam, para cada origem de IntegrityError que não é a
# unicidade do CNPJ, que a função devolve None (reauditoria etapa DL-011,
# rodada 3).


def test_mensagem_se_cnpj_duplicado_ignora_violacao_de_outra_unique_constraint(empresa):
    Estabelecimento.objects.create(
        empresa=empresa, tipo=TipoEstabelecimento.MATRIZ, nome="Matriz", cnpj="44455566000183"
    )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        # uma_matriz_por_empresa: unique constraint real, mas não é a de
        # cnpj — cada empresa só pode ter uma matriz.
        Estabelecimento.objects.create(
            empresa=empresa,
            tipo=TipoEstabelecimento.MATRIZ,
            nome="Outra matriz",
            cnpj="44455566000264",
        )

    assert "uma_matriz_por_empresa" in str(excinfo.value)
    # DL-038: mensagem_se_cnpj_duplicado passou a devolver a tupla
    # (campo, mensagem) — (None, None) para IntegrityError que não é
    # nenhuma das constraints de unicidade mapeadas (mesmo contrato de
    # antes, só que agora com CPF também no mapa).
    assert mensagem_se_cnpj_duplicado(excinfo.value) == (None, None)


def test_mensagem_se_cnpj_duplicado_ignora_violacao_da_check_constraint_canonica(empresa):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        # empresa_cnpj_canonico (R1): outra constraint do mesmo campo cnpj,
        # mas não é a de UNICIDADE — é a que exige maiúsculas/A-Z0-9.
        Empresa.objects.bulk_create(
            [
                Empresa(
                    escritorio=empresa.escritorio,
                    razao_social="Empresa Lote Ltda",
                    cnpj="ab123cde000155",
                )
            ]
        )

    assert "empresa_cnpj_canonico" in str(excinfo.value)
    # DL-038: mensagem_se_cnpj_duplicado passou a devolver a tupla
    # (campo, mensagem) — (None, None) para IntegrityError que não é
    # nenhuma das constraints de unicidade mapeadas (mesmo contrato de
    # antes, só que agora com CPF também no mapa).
    assert mensagem_se_cnpj_duplicado(excinfo.value) == (None, None)


def test_mensagem_se_cnpj_duplicado_ignora_violacao_de_chave_estrangeira():
    from django.db import connection

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Estabelecimento.objects.create(
            empresa_id=999999,
            tipo=TipoEstabelecimento.MATRIZ,
            nome="Matriz Órfã",
            cnpj="44455566000183",
        )
        # A FK do Django é DEFERRABLE INITIALLY DEFERRED por padrão: sem
        # forçar a checagem aqui, o IntegrityError só apareceria no COMMIT
        # (ou, neste ambiente de teste, na desmontagem do banco de teste,
        # tarde demais para o pytest.raises acima capturar).
        connection.check_constraints()

    # DL-038: mensagem_se_cnpj_duplicado passou a devolver a tupla
    # (campo, mensagem) — (None, None) para IntegrityError que não é
    # nenhuma das constraints de unicidade mapeadas (mesmo contrato de
    # antes, só que agora com CPF também no mapa).
    assert mensagem_se_cnpj_duplicado(excinfo.value) == (None, None)


# --- B2 (auditoria da etapa DL-011, rodada 4): os três testes acima prendem
# mensagem_se_cnpj_duplicado ISOLADA, como função — mas nada exercitava o
# próprio gerenciador erro_de_cnpj_duplicado_como_400(). Um mutante de uma
# linha nele (`mensagem_se_cnpj_duplicado(exc) or "CNPJ ja existe."`)
# reintroduz a DL-007 inteira, nos quatro caminhos de uma vez, sem que a
# suíte acusasse. Os dois testes abaixo prendem o gerenciador diretamente.


def test_gerenciador_deixa_subir_integrityerror_de_outra_constraint(empresa):
    Estabelecimento.objects.create(
        empresa=empresa, tipo=TipoEstabelecimento.MATRIZ, nome="Matriz", cnpj="44455566000183"
    )

    with (
        pytest.raises(IntegrityError) as excinfo,
        transaction.atomic(),
        erro_de_cnpj_duplicado_como_400(),
    ):
        Estabelecimento.objects.create(
            empresa=empresa,
            tipo=TipoEstabelecimento.MATRIZ,
            nome="Outra matriz",
            cnpj="44455566000264",
        )

    # Com o mutante `or "CNPJ ja existe."`, isto viraria CNPJDuplicado (400)
    # em vez de subir como o IntegrityError original de
    # uma_matriz_por_empresa — a mesma armadilha da DL-007, agora dentro do
    # próprio gerenciador.
    assert "uma_matriz_por_empresa" in str(excinfo.value)


def test_gerenciador_traduz_apenas_a_unique_de_cnpj(empresa):
    Empresa.objects.create(
        escritorio=empresa.escritorio, razao_social="Empresa B Ltda", cnpj="AB123CDE000155"
    )

    with (
        pytest.raises(CNPJDuplicado) as excinfo,
        transaction.atomic(),
        erro_de_cnpj_duplicado_como_400(),
    ):
        Empresa.objects.bulk_create(
            [
                Empresa(
                    escritorio=empresa.escritorio,
                    razao_social="Empresa C Ltda",
                    cnpj="AB123CDE000155",
                )
            ]
        )

    assert excinfo.value.message_dict == {"cnpj": ["empresa com este CNPJ já existe."]}
