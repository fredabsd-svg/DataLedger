"""DL-088: as migrações 0017 e 0018 aplicadas, revertidas e reaplicadas pelo `migrate` do Django.

0017 (a opção de regime e o IPI mantido):
- volta com a opção registrada ou com o dado de IPI mantido gravado: RECUSA, e nada muda no banco
  (instantâneo antes/depois; a guarda roda PRIMEIRO na reversão);
- volta sem esses dados: passa, e a reaplicação recria as duas tabelas.

0018 (o cancelamento da opção — correção do achado A1; Res. CGSN 194/2026):
- a unicidade do semestre vira PARCIAL (`cancelada_em__isnull=True`) e a opção ganha
  `cancelada_em`/`cancelada_por`/`motivo_cancelamento`;
- volta com dado do contador (opção registrada, com ou sem cancelamento, ou IPI mantido): RECUSA,
  sem alterar nada — a guarda é ampliada como a da 0016, porque as duas migrações da DL-088 se
  revertem juntas e cada uma tem a sua transação;
- volta sem dado: só os campos de cancelamento saem (e a unicidade total volta), e a reaplicação
  os devolve.

Usa `transaction=True`: a reversão precisa rodar fora de transação de teste. Cada teste termina no
HEAD, como estava. A aplicação em banco vazio é a própria criação do banco de teste, que migra do
zero até o head antes da primeira chamada.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.fiscal.models import (
    IpiMantidoZfmEmpresa,
    OpcaoRegimeIbsCbsSimples,
    RegimeIbsCbsSimples,
    SituacaoIpiMantido,
)

ULTIMA_ANTES = "0016_dl084_escopo_do_escritorio_feriados"
ULTIMA = "0017_dl088_opcao_regime_ibs_cbs_e_ipi_mantido"
HEAD = "0018_dl088_cancelamento_da_opcao_de_regime"

_TABELAS = ("fiscal_opcaoregimeibscbssimples", "fiscal_ipimantidozfmempresa")


def _tabelas_existem() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT to_regclass('{_TABELAS[0]}') IS NOT NULL "
            f"AND to_regclass('{_TABELAS[1]}') IS NOT NULL"
        )
        return cursor.fetchone()[0]


def _campos_de_cancelamento_existem() -> bool:
    """Os três campos da 0018 na tabela da opção (o `cancelada_em` é a marca de cancelada; a FK
    `cancelada_por` vira coluna `cancelada_por_id`)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'fiscal_opcaoregimeibscbssimples' "
            "AND column_name IN ('cancelada_em', 'cancelada_por_id', 'motivo_cancelamento')"
        )
        return cursor.fetchone()[0] == 3


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
    """Sem dado gravado, a reversão só tira as tabelas/campos, e a reaplicação os recria. O teste
    termina no HEAD (0018), como estava antes da execução."""
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert _tabelas_existem() is True
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert _tabelas_existem() is True
    call_command("migrate", "fiscal", HEAD, verbosity=0)
    assert _campos_de_cancelamento_existem() is True


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
    call_command("migrate", "fiscal", HEAD, verbosity=0)
    assert _campos_de_cancelamento_existem() is True


def _cenario_cancelada(empresa, usuario):
    """Opção registrada e CANCELADA (dado direto: o teste é de migração, não do serviço)."""
    opcao = _cenario_opcao(empresa, usuario)
    OpcaoRegimeIbsCbsSimples.objects.filter(pk=opcao.pk).update(
        cancelada_em=timezone.now(),
        cancelada_por=usuario,
        motivo_cancelamento="Cancelamento sintético de teste.",
    )
    opcao.refresh_from_db()
    return opcao


@pytest.mark.django_db(transaction=True)
def test_volta_da_0018_recusa_com_o_cancelamento_gravado(escritorio_a):
    """Achado A1: o cancelamento é dado do contador (quem, quando e por quê). Com ele gravado, a
    reversão da 0018 é recusada ANTES de qualquer campo sair: sem isso, a opção cancelada voltaria
    a valer como ativa (a unicidade total seria restaurada e os campos de cancelamento apagados).
    """
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Cliente migração DL088 cancelada Ltda",
        cnpj="77888999000179",
    )
    usuario = _usuario_gestor(escritorio_a, "gestor-migracao-cancelada-dl088")
    opcao = _cenario_cancelada(empresa, usuario)

    antes = (
        OpcaoRegimeIbsCbsSimples.objects.count(),
        opcao.cancelada_em,
        opcao.motivo_cancelamento,
    )
    with pytest.raises(RuntimeError, match="Reversão da DL-088 recusada"):
        call_command("migrate", "fiscal", ULTIMA, verbosity=0)

    assert _campos_de_cancelamento_existem() is True
    opcao.refresh_from_db()
    assert (
        OpcaoRegimeIbsCbsSimples.objects.count(),
        opcao.cancelada_em,
        opcao.motivo_cancelamento,
    ) == antes


@pytest.mark.django_db(transaction=True)
def test_volta_da_0018_recusa_com_a_opcao_registrada_mesmo_sem_cancelamento(escritorio_a):
    """A guarda da 0018 é ampliada no padrão da 0016 (que contou as cinco classes da DL-084): as
    duas migrações da DL-088 se revertem juntas em `migrate fiscal 0016`, cada uma com a sua
    transação, e sem contar as classes da 0017 a 0018 sairia (com os campos de cancelamento) antes
    de a guarda da 0017 ver a opção gravada — "sem alterar nada" seria mentira.
    """
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Cliente migração DL088 ativa Ltda",
        cnpj="77888999000180",
    )
    usuario = _usuario_gestor(escritorio_a, "gestor-migracao-ativa-dl088")
    opcao = _cenario_opcao(empresa, usuario)

    with pytest.raises(RuntimeError, match="Reversão da DL-088 recusada"):
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)

    assert _tabelas_existem() is True
    assert _campos_de_cancelamento_existem() is True
    assert OpcaoRegimeIbsCbsSimples.objects.filter(pk=opcao.pk).exists()
