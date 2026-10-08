"""DL-074 (frente A) — receita do mês por mercado e receita informada.

Critérios do plano cobertos aqui: 1 (receita do mês = escriturações efetivadas + informadas
confirmadas, por mercado; exportação nunca soma no interno), 3 (receita informada com
origem, motivo, suporte e ciclo rascunho → confirmada → estornada) e 7 (origem "histórico"
recusada em mês a partir do início de uso do sistema).

Os valores são sintéticos e os totais esperados estão escritos à mão nos testes.
"""

from decimal import Decimal

import pytest

from apps.fiscal import escrituracao as servico_escrituracao
from apps.fiscal import receita as servico
from apps.fiscal.models import (
    EstadoReceitaInformada,
    MercadoReceita,
    NaturezaOperacao,
    OrigemReceitaInformada,
)
from apps.fiscal.tests.test_dl074_suporte import (
    NATUREZA_EXPORTACAO,
    NATUREZA_INTERNA,
    escriturar,
    fixar_inicio_de_uso,
    informar_e_confirmar,
    sequencia,
)

pytestmark = pytest.mark.django_db

INTERNO = MercadoReceita.INTERNO
EXTERNO = MercadoReceita.EXTERNO


def _lancar(
    empresa, usuario, mercado, valor, *, ano=2026, mes=5, origem="outras_receitas_atividade"
):
    return servico.lancar_receita_informada(
        empresa,
        ano,
        mes,
        mercado,
        valor,
        origem,
        "Motivo sintético.",
        "Suporte sintético.",
        usuario,
    )


# ---------------------------------------------------------------------------
# Critério 1 — composição do mês por mercado
# ---------------------------------------------------------------------------


def test_receita_do_mes_soma_efetivadas_e_informadas_confirmadas_por_mercado(
    empresa_a, escritorio_a, usuario_gestor_a
):
    # Maio/2026. Interno: escriturada 1.000,00 + informada confirmada 200,00 = 1.200,00.
    # Externo: exportação escriturada 500,00 + informada confirmada 300,00 = 800,00.
    # Não entram: rascunho (999,00), informada estornada (888,00) e escrituração estornada (777,00).
    escriturar(
        escritorio_a, empresa_a, usuario_gestor_a, sufixo=101, competencia=(2026, 5), valor="1000"
    )
    escriturar(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=102,
        competencia=(2026, 5),
        valor="500",
        natureza=NATUREZA_EXPORTACAO,
    )
    informar_e_confirmar(empresa_a, usuario_gestor_a, 2026, 5, "200")
    informar_e_confirmar(empresa_a, usuario_gestor_a, 2026, 5, "300", mercado=EXTERNO)
    _lancar(empresa_a, usuario_gestor_a, INTERNO, "999")  # rascunho
    estornada = informar_e_confirmar(empresa_a, usuario_gestor_a, 2026, 5, "888")
    servico.estornar_receita_informada(estornada, "Lançado em duplicidade.", usuario_gestor_a)
    escrituracao = escriturar(
        escritorio_a, empresa_a, usuario_gestor_a, sufixo=103, competencia=(2026, 5), valor="777"
    )
    servico_escrituracao.estornar_escrituracao(
        escrituracao, "Nota cancelada na prefeitura.", usuario_gestor_a
    )

    dados = servico.receita_do_mes(empresa_a, 2026, 5)

    interno = dados.composicao.de(INTERNO)
    externo = dados.composicao.de(EXTERNO)
    assert (interno.documento, interno.informado, interno.total) == (
        Decimal("1000.00"),
        Decimal("200.00"),
        Decimal("1200.00"),
    )
    assert (externo.documento, externo.informado, externo.total) == (
        Decimal("500.00"),
        Decimal("300.00"),
        Decimal("800.00"),
    )


def test_exportacao_nunca_soma_no_interno(empresa_a, escritorio_a, usuario_gestor_a):
    # Só exportação escriturada (2.000,00): o interno fica em zero e o externo recebe tudo.
    escriturar(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=111,
        competencia=(2026, 5),
        valor="2000",
        natureza=NATUREZA_EXPORTACAO,
    )

    dados = servico.receita_do_mes(empresa_a, 2026, 5)

    assert dados.composicao.de(INTERNO).total == Decimal("0.00")
    assert dados.composicao.de(EXTERNO).total == Decimal("2000.00")


def test_escrituracao_de_outro_mes_nao_entra_no_mes(empresa_a, escritorio_a, usuario_gestor_a):
    # Nota com dCompet em junho não aparece em maio, mesmo com emissão em maio (HI-57).
    escriturar(
        escritorio_a, empresa_a, usuario_gestor_a, sufixo=121, competencia=(2026, 6), valor="700"
    )

    assert servico.receita_do_mes(empresa_a, 2026, 5).composicao.de(INTERNO).total == Decimal(
        "0.00"
    )
    assert servico.receita_do_mes(empresa_a, 2026, 6).composicao.de(INTERNO).total == Decimal(
        "700.00"
    )


def test_rascunho_nao_entra_e_so_a_confirmacao_da_receita_informada_conta(
    empresa_a, usuario_gestor_a
):
    receita = _lancar(empresa_a, usuario_gestor_a, INTERNO, "450.50")
    assert servico.receita_do_mes(empresa_a, 2026, 5).composicao.de(INTERNO).total == Decimal(
        "0.00"
    )

    servico.confirmar_receita_informada(receita, usuario_gestor_a)

    assert servico.receita_do_mes(empresa_a, 2026, 5).composicao.de(INTERNO).total == Decimal(
        "450.50"
    )


# ---------------------------------------------------------------------------
# Critério 3 — receita informada: campos, catálogo e ciclo de vida
# ---------------------------------------------------------------------------


def test_receita_informada_nasce_em_rascunho_com_valor_decimal_exato(empresa_a, usuario_gestor_a):
    receita = _lancar(empresa_a, usuario_gestor_a, INTERNO, "100.50")

    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.RASCUNHO
    assert receita.valor == Decimal("100.50")
    assert receita.confirmada_em is None


@pytest.mark.parametrize("valor", ["0", "-10", "10.005", "abc", 10.5, "nan"])
def test_valor_invalido_e_recusado_antes_de_gravar(empresa_a, usuario_gestor_a, valor):
    # Zero, negativo, mais de duas casas, não numérico e float (binário) são recusados.
    with pytest.raises(servico.EntradaInvalidaReceita):
        _lancar(empresa_a, usuario_gestor_a, INTERNO, valor)

    assert empresa_a.receitas_informadas.count() == 0


@pytest.mark.parametrize("campo", ["motivo", "documento_suporte"])
def test_motivo_e_documento_de_suporte_sao_obrigatorios(empresa_a, usuario_gestor_a, campo):
    argumentos = {"motivo": "Motivo sintético.", "documento_suporte": "Suporte sintético."}
    argumentos[campo] = "   "

    with pytest.raises(servico.EntradaInvalidaReceita, match="Informe"):
        servico.lancar_receita_informada(
            empresa_a,
            2026,
            5,
            INTERNO,
            "10",
            "ajuste",
            argumentos["motivo"],
            argumentos["documento_suporte"],
            usuario_gestor_a,
        )


def test_mercado_e_origem_fora_do_catalogo_sao_recusados(empresa_a, usuario_gestor_a):
    with pytest.raises(servico.EntradaInvalidaReceita, match="Mercado desconhecido"):
        servico.lancar_receita_informada(
            empresa_a, 2026, 5, "misto", "10", "ajuste", "M.", "S.", usuario_gestor_a
        )
    with pytest.raises(servico.EntradaInvalidaReceita, match="Origem fora do catálogo"):
        servico.lancar_receita_informada(
            empresa_a, 2026, 5, INTERNO, "10", "palpite", "M.", "S.", usuario_gestor_a
        )


def test_so_rascunho_pode_ser_confirmado_e_so_confirmada_pode_ser_estornada(
    empresa_a, usuario_gestor_a
):
    receita = _lancar(empresa_a, usuario_gestor_a, INTERNO, "10")
    with pytest.raises(servico.ReceitaErro, match="Só receita confirmada"):
        servico.estornar_receita_informada(receita, "Motivo.", usuario_gestor_a)

    confirmada = servico.confirmar_receita_informada(receita, usuario_gestor_a)
    with pytest.raises(servico.ReceitaErro, match="Só receita em rascunho"):
        servico.confirmar_receita_informada(confirmada, usuario_gestor_a)


def test_estorno_exige_motivo_e_guarda_o_motivo(empresa_a, usuario_gestor_a):
    confirmada = informar_e_confirmar(empresa_a, usuario_gestor_a, 2026, 5, "10")
    with pytest.raises(servico.EntradaInvalidaReceita, match="motivo"):
        servico.estornar_receita_informada(confirmada, "   ", usuario_gestor_a)

    estornada = servico.estornar_receita_informada(
        confirmada, "Valor digitado errado.", usuario_gestor_a
    )

    estornada.refresh_from_db()
    assert estornada.estado == EstadoReceitaInformada.ESTORNADA
    assert estornada.motivo_estorno == "Valor digitado errado."


# ---------------------------------------------------------------------------
# Critério 7 — origem "histórico" só antes do início de uso do sistema
# ---------------------------------------------------------------------------


def test_historico_e_recusado_a_partir_do_mes_de_inicio_de_uso(empresa_a, usuario_gestor_a):
    # Início de uso = mês do cadastro (março/2026). Histórico em março é recusado;
    # em fevereiro, não.
    fixar_inicio_de_uso(empresa_a, 2026, 3)

    with pytest.raises(servico.EntradaInvalidaReceita, match="início de uso"):
        _lancar(
            empresa_a,
            usuario_gestor_a,
            INTERNO,
            "10",
            ano=2026,
            mes=3,
            origem=OrigemReceitaInformada.HISTORICO_PRE_SISTEMA,
        )
    with pytest.raises(servico.EntradaInvalidaReceita, match="início de uso"):
        _lancar(
            empresa_a,
            usuario_gestor_a,
            INTERNO,
            "10",
            ano=2026,
            mes=4,
            origem=OrigemReceitaInformada.HISTORICO_PRE_SISTEMA,
        )

    anterior = _lancar(
        empresa_a,
        usuario_gestor_a,
        INTERNO,
        "10",
        ano=2026,
        mes=2,
        origem=OrigemReceitaInformada.HISTORICO_PRE_SISTEMA,
    )
    assert anterior.origem == OrigemReceitaInformada.HISTORICO_PRE_SISTEMA


def test_inicio_de_uso_e_o_mes_local_do_cadastro(empresa_a):
    # 28/02/2026 às 23h30 em Brasília é 01/03/2026 02h30 em UTC. O mês de início de uso é
    # fevereiro (horário local), e não março: o cálculo tem de usar o fuso de Brasília.
    from datetime import datetime

    from django.utils import timezone

    from apps.empresas.models import Empresa

    quando = timezone.make_aware(datetime(2026, 2, 28, 23, 30), timezone.get_current_timezone())
    Empresa.objects.filter(pk=empresa_a.pk).update(criado_em=quando)
    empresa_a.refresh_from_db()

    assert servico.inicio_de_uso(empresa_a) == (2026, 2)


def test_origem_que_nao_e_historico_aceita_mes_de_inicio_de_uso(empresa_a, usuario_gestor_a):
    fixar_inicio_de_uso(empresa_a, 2026, 3)

    receita = _lancar(
        empresa_a,
        usuario_gestor_a,
        INTERNO,
        "10",
        ano=2026,
        mes=3,
        origem=OrigemReceitaInformada.AJUSTE,
    )

    assert receita.mes == 3


# ---------------------------------------------------------------------------
# Lista de competências (sanidade do utilitário de teste)
# ---------------------------------------------------------------------------


def test_sequencia_de_competencias_cruza_o_ano():
    assert sequencia(2025, 11, 4) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_natureza_interna_e_exportacao_tem_mercados_distintos():
    from apps.fiscal.models import mercado_da_natureza

    assert mercado_da_natureza(NATUREZA_INTERNA) == INTERNO
    assert mercado_da_natureza(NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO) == EXTERNO
