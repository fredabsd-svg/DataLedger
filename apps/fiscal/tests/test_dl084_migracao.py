"""DL-084: migrações 0015 e 0016 aplicadas, revertidas e reaplicadas pelo `migrate` do Django.

- Ida: a carga de Palmas/TO entra com lei e data da leitura.
- Volta com dado do contador (parâmetro, competência, encerramento, feriado ou exceção do
  escritório): RECUSA, e nada muda no banco (A5 da auditoria: as cinco classes).
- Volta da 0016 (só o escopo do escritório, DE-106): recusa com linha do escritório e passa sem
  elas.
- Volta sem dado do contador: passa, e a reaplicação recria a carga.

Usa `transaction=True`: a reversão precisa rodar fora de transação de teste. Cada teste termina no
head, como estava.
"""

from datetime import date
from decimal import Decimal as D

import pytest
from django.core.management import call_command
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal.models import (
    EncerramentoMedidaJudicialLC224,
    ExcecaoFeriadoLocal,
    FeriadoLocal,
    MedidaJudicialLC224,
    ParametrosPresumidoEmpresa,
    ReceitaTrimestralPresumido,
)

ULTIMA_ANTES = "0014_dl082_pre_das_comercio"
ULTIMA_0015 = "0015_dl084_rotina_do_presumido"
ULTIMA = "0016_dl084_escopo_do_escritorio_feriados"


def _tabelas_existem():
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('fiscal_feriadolocal') IS NOT NULL")
        return cursor.fetchone()[0]


def _coluna_escritorio_existe(tabela: str) -> bool:
    with connection.cursor() as cursor:
        colunas = connection.introspection.get_table_description(cursor, tabela)
    return any(coluna.name == "escritorio_id" for coluna in colunas)


@pytest.mark.django_db(transaction=True)
def test_ida_volta_e_ida_com_a_carga_de_palmas():
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert FeriadoLocal.objects.filter(uf="TO", municipio="PALMAS").count() == 5
    call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert _tabelas_existem() is False
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)
    assert FeriadoLocal.objects.filter(uf="TO").count() == 8
    assert all(
        f.fundamento and f.data_leitura == date(2026, 10, 9) for f in FeriadoLocal.objects.all()
    )


def _usuario_gestor(escritorio, username, papel):
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import VinculoUsuarioEscritorio

    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


# ---------------------------------------------------------------------------
# A5: a guarda de reversão recusa nas CINCO classes de dado do contador
# ---------------------------------------------------------------------------


def _cenario_parametro(empresa, usuario, escritorio):
    return ParametrosPresumidoEmpresa.objects.create(
        empresa=empresa, forma_recolhimento="quota_unica", atualizado_por=usuario
    )


def _cenario_competencia(empresa, usuario, escritorio):
    return ReceitaTrimestralPresumido.objects.create(
        empresa=empresa,
        ano=2026,
        trimestre=1,
        tipo="integral",
        descricao="Receita sintética com competência",
        valor=D("100.00"),
        suporte="Documento sintético",
        competencia="2026-01",
        criada_por=usuario,
    )


def _cenario_encerramento(empresa, usuario, escritorio):
    medida = MedidaJudicialLC224.objects.create(
        empresa=empresa,
        tributo="irpj",
        ano_inicial=2026,
        trimestre_inicial=1,
        numero_processo="PROCESSO-SINTETICO-MIGRACAO",
        orgao="Juízo sintético",
        data_decisao=date(2026, 1, 15),
        suporte="Decisão sintética",
        criada_por=usuario,
    )
    return EncerramentoMedidaJudicialLC224.objects.create(
        medida=medida,
        ano=2026,
        trimestre=2,
        motivo="encerramento sintético",
        encerrada_por=usuario,
    )


def _cenario_feriado_do_escritorio(empresa, usuario, escritorio):
    return FeriadoLocal.objects.create(
        escritorio=escritorio,
        uf="TO",
        municipio="PALMAS",
        esfera="municipal",
        mes=1,
        dia=2,
        descricao="Feriado sintético do escritório",
        fundamento="Lei sintética nº 1/2026",
        data_leitura=date(2026, 10, 9),
        vigencia_inicio=date(2026, 1, 1),
    )


def _cenario_excecao_do_escritorio(empresa, usuario, escritorio):
    # Sem supor a carga (o teste transacional limpa o banco): a exceção do escritório pendura numa
    # linha da BASE criada aqui, como a tela faz quando o feriado é da base.
    feriado = FeriadoLocal.objects.create(
        uf="TO",
        municipio="",
        esfera="estadual",
        mes=10,
        dia=5,
        descricao="Feriado da base sintético",
        fundamento="Lei estadual sintética nº 2/2026",
        data_leitura=date(2026, 10, 9),
        vigencia_inicio=date(1989, 11, 17),
    )
    return ExcecaoFeriadoLocal.objects.create(
        escritorio=escritorio,
        feriado=feriado,
        ano=2030,
        data_observada=date(2030, 10, 7),
        fundamento="Decreto sintético nº 1/2030",
        data_leitura=date(2026, 10, 9),
    )


_CENARIOS = [
    ("parametro", _cenario_parametro),
    ("competencia", _cenario_competencia),
    ("encerramento", _cenario_encerramento),
    ("feriado_escritorio", _cenario_feriado_do_escritorio),
    ("excecao_escritorio", _cenario_excecao_do_escritorio),
]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("caso,criar", _CENARIOS, ids=[caso for caso, _ in _CENARIOS])
def test_volta_recusa_com_dado_do_contador_e_nao_altera_nada(caso, criar, escritorio_a):
    from apps.tenancy.models import Papel

    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente migração Ltda", cnpj="77888999000170"
    )
    usuario = _usuario_gestor(escritorio_a, f"gestor-migracao-{caso}-dl084", Papel.GESTOR)
    dado = criar(empresa, usuario, escritorio_a)
    # Instantâneo do banco ANTES do pedido de reversão: o teste transacional não supõe a carga.
    antes = (
        FeriadoLocal.objects.count(),
        ExcecaoFeriadoLocal.objects.count(),
        type(dado).objects.filter(pk=dado.pk).exists(),
    )
    with pytest.raises(RuntimeError, match="Reversão da DL-084 recusada"):
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    # Recusou ANTES de qualquer coisa mudar (a guarda da 0016 roda primeiro na reversão): o banco
    # segue no head, com as colunas do escopo no lugar, e nada do instantâneo mudou.
    assert _tabelas_existem() is True
    assert _coluna_escritorio_existe("fiscal_feriadolocal")
    assert (
        FeriadoLocal.objects.count(),
        ExcecaoFeriadoLocal.objects.count(),
        type(dado).objects.filter(pk=dado.pk).exists(),
    ) == antes


# ---------------------------------------------------------------------------
# DE-106: a reversão da 0016 (só o escopo do escritório) e o contra-seguro da 0015
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_reversao_da_0016_recusa_com_linha_do_escritorio_e_passa_sem_elas(escritorio_a):
    """Reverter a 0016 com linha do escritório faria a linha virar base e valer para todos os
    escritórios — a reversão recusa, e nada muda. Sem linha do escritório, ela passa e só o escopo
    sai: a linha da base continua intacta."""
    from apps.tenancy.models import Papel

    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente migração 0016 Ltda", cnpj="77888999000171"
    )
    usuario = _usuario_gestor(escritorio_a, "gestor-migracao-0016-dl084", Papel.GESTOR)
    # Sem supor a carga (o teste transacional limpa o banco): uma linha da base e uma do escritório.
    linha_base = FeriadoLocal.objects.create(
        uf="TO",
        municipio="",
        esfera="estadual",
        mes=10,
        dia=5,
        descricao="Feriado da base sintético",
        fundamento="Lei estadual sintética nº 3/2026",
        data_leitura=date(2026, 10, 9),
        vigencia_inicio=date(1989, 11, 17),
    )
    linha = _cenario_feriado_do_escritorio(empresa, usuario, escritorio_a)
    with pytest.raises(RuntimeError, match="Reversão da DL-084 recusada"):
        call_command("migrate", "fiscal", ULTIMA_0015, verbosity=0)
    assert FeriadoLocal.objects.get(pk=linha.pk).escritorio_id == escritorio_a.pk  # nada alterado

    linha.delete()
    call_command("migrate", "fiscal", ULTIMA_0015, verbosity=0)
    assert not _coluna_escritorio_existe("fiscal_feriadolocal")
    assert not _coluna_escritorio_existe("fiscal_excecaoferiadolocal")
    # A linha da base saiu intacta da reversão do escopo (é dado da lei, e pode sair com ela).
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM fiscal_feriadolocal WHERE id = %s", [linha_base.pk])
        assert cursor.fetchone()[0] == 1
    call_command("migrate", "fiscal", ULTIMA, verbosity=0)  # devolve ao head
    assert _coluna_escritorio_existe("fiscal_feriadolocal")
    assert FeriadoLocal.objects.get(pk=linha_base.pk).escritorio_id is None


@pytest.mark.django_db(transaction=True)
def test_a_guarda_da_0015_conta_a_linha_do_escritorio_com_a_coluna_ainda_no_banco(escritorio_a):
    """Contra-seguro da A2: na cadeia normal a 0016 recusa primeiro (e remove as colunas) antes de
    a guarda da 0015 rodar. Aqui a reversão da 0016 é FALSIFICADA (`--fake`, o registro muda e o
    banco não) e a reversão da 0015 roda com as colunas no lugar: a guarda dela tem de recusar pelo
    MESMO motivo. Dado do contador não sai com a reversão em caminho nenhum."""
    from apps.tenancy.models import Papel

    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente migração 0015 Ltda", cnpj="77888999000172"
    )
    usuario = _usuario_gestor(escritorio_a, "gestor-migracao-0015-dl084", Papel.GESTOR)
    linha = _cenario_feriado_do_escritorio(empresa, usuario, escritorio_a)
    call_command("migrate", "fiscal", ULTIMA_0015, fake=True, verbosity=0)
    with pytest.raises(RuntimeError, match="Reversão da DL-084 recusada"):
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
    assert FeriadoLocal.objects.get(pk=linha.pk).escritorio_id == escritorio_a.pk  # nada alterado
    call_command("migrate", "fiscal", ULTIMA, fake=True, verbosity=0)  # devolve o registro ao head
