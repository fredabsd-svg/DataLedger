"""DL-088, frente A2: a migração 0017 aplicada, revertida e reaplicada pelo `migrate` do Django.

- Volta com a opção de regime de IBS/CBS registrada ou com o dado de IPI mantido gravado: RECUSA,
  e nada muda no banco (instantâneo antes/depois; a guarda roda PRIMEIRO na reversão).
- Volta sem esses dados: passa, e a reaplicação recria as duas tabelas.

Usa `transaction=True`: a reversão precisa rodar fora de transação de teste. Cada teste termina no
head, como estava. A aplicação em banco vazio é a própria criação do banco de teste, que migra do
zero até o head antes da primeira chamada.
"""

import pytest
from django.core.management import call_command
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal.models import (
    IpiMantidoZfmEmpresa,
    OpcaoRegimeIbsCbsSimples,
    RegimeIbsCbsSimples,
    SituacaoIpiMantido,
)

ULTIMA_ANTES = "0016_dl084_escopo_do_escritorio_feriados"
ULTIMA = "0017_dl088_opcao_regime_ibs_cbs_e_ipi_mantido"

_TABELAS = ("fiscal_opcaoregimeibscbssimples", "fiscal_ipimantidozfmempresa")


def _tabelas_existem() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT to_regclass('{_TABELAS[0]}') IS NOT NULL "
            f"AND to_regclass('{_TABELAS[1]}') IS NOT NULL"
        )
        return cursor.fetchone()[0]


def _usuario_gestor(escritorio, username):
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


@pytest.mark.django_db(transaction=True)
def test_ida_volta_e_ida_sem_dado():
    """Sem dado gravado, a reversão só tira as duas tabelas, e a reaplicação as recria."""
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert _tabelas_existem() is True
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert _tabelas_existem() is True


def _cenario_opcao(empresa, usuario):
    return OpcaoRegimeIbsCbsSimples.objects.create(
        empresa=empresa,
        ano=2027,
        semestre=1,
        regime=RegimeIbsCbsSimples.REGIME_UNICO,
        registrada_por=usuario,
    )


def _cenario_ipi_mantido(empresa, usuario):
    return IpiMantidoZfmEmpresa.objects.create(
        empresa=empresa,
        situacao=SituacaoIpiMantido.IPI_MANTIDO,
        fonte="Ato de incentivo à Zona Franca de Manaus (dado sintético de teste)",
        registrada_por=usuario,
    )


_CENARIOS = [
    ("opcao_regime_ibs_cbs", _cenario_opcao),
    ("ipi_mantido", _cenario_ipi_mantido),
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("caso,criar", _CENARIOS, ids=[caso for caso, _ in _CENARIOS])
def test_volta_recusa_com_dado_gravado_e_nao_altera_nada(caso, criar, escritorio_a):
    """A reversão com dado gravado recusa ANTES de qualquer tabela sair: o instantâneo do banco
    (antes/depois) fica idêntico, e a opção — que decide se CBS e IBS entram no DAS — não some."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente migração DL088 Ltda", cnpj="77888999000177"
    )
    usuario = _usuario_gestor(escritorio_a, f"gestor-migracao-{caso}-dl088")
    dado = criar(empresa, usuario)

    antes = (
        OpcaoRegimeIbsCbsSimples.objects.count(),
        IpiMantidoZfmEmpresa.objects.count(),
        type(dado).objects.filter(pk=dado.pk).exists(),
    )
    with pytest.raises(RuntimeError, match="Reversão da DL-088 recusada"):
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)

    # Recusou ANTES de qualquer coisa mudar (a guarda é a última operação, e roda primeiro na
    # reversão): as tabelas seguem no banco e o instantâneo não mudou um registro sequer.
    assert _tabelas_existem() is True
    assert (
        OpcaoRegimeIbsCbsSimples.objects.count(),
        IpiMantidoZfmEmpresa.objects.count(),
        type(dado).objects.filter(pk=dado.pk).exists(),
    ) == antes


@pytest.mark.django_db(transaction=True)
def test_volta_sem_dado_passa_e_a_reaplicacao_recria_as_tabelas(escritorio_a):
    """Sem a opção nem o IPI gravados, a reversão passa (as tabelas saem) e nada de dado se perde,
    porque não há dado. Depois, a reaplicação devolve o estado do head."""
    Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Cliente migração DL088 vazio Ltda",
        cnpj="77888999000178",
    )
    assert OpcaoRegimeIbsCbsSimples.objects.count() == 0
    assert IpiMantidoZfmEmpresa.objects.count() == 0

    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert _tabelas_existem() is True
