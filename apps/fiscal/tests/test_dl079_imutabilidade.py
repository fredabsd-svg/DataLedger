"""DL-079, critério 9 (banco): gatilhos de imutabilidade e leitura de retenção e desconto do XML.

Os gatilhos (migração fiscal 0009) recusam o que escapa do Python: UPDATE e DELETE por SQL direto.
Cada tentativa roda num SAVEPOINT, para a transação de teste continuar utilizável.
"""

from datetime import date
from decimal import Decimal as D

import pytest
from django.db import IntegrityError, connection, transaction

from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.presumido import proposta_de_retencao
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada
from apps.fiscal.tomadas_campos import campos_tomada_do_documento

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def base(empresa_a, usuario_gestor_a, escritorio_a):
    """Empresa presumida com receita, declaração, medida e confirmação de retenção."""
    if connection.vendor != "postgresql":
        pytest.skip("gatilhos de PostgreSQL: a guarda do Python cobre o SQLite")
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    atividade = servico.criar_atividade(
        empresa_a,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": False},
        usuario_gestor_a,
    )
    receita = servico.criar_receita(
        empresa_a,
        2026,
        1,
        {
            "tipo": "presuncao",
            "valor": "1000.00",
            "descricao": "x",
            "suporte": "y",
            "atividade_id": atividade.pk,
        },
        usuario_gestor_a,
    )
    integral = servico.criar_receita(
        empresa_a,
        2026,
        1,
        {"tipo": "integral", "valor": "50.00", "descricao": "x", "suporte": "y"},
        usuario_gestor_a,
    )
    declaracao = servico.declarar_receitas_integrais(empresa_a, 2026, 1, "", usuario_gestor_a)
    medida = servico.cadastrar_medida(
        empresa_a,
        {
            "tributo": "irpj",
            "ano_inicial": 2026,
            "trimestre_inicial": 1,
            "numero_processo": "processo-ficticio-2",
            "orgao": "Vara fictícia",
            "data_decisao": "2026-03-01",
            "suporte": "decisão sintética",
        },
        usuario_gestor_a,
    )
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=701,
        v_serv="20000.00",
        d_compet="2026-01-10",
        ret_irrf="200.00",
    )
    confirmacao = servico.confirmar_retencao(
        empresa_a, escrituracao.pk, "200.00", None, "", usuario_gestor_a
    )
    return {
        "receita": receita,
        "integral": integral,
        "declaracao": declaracao,
        "medida": medida,
        "confirmacao": confirmacao,
        "empresa": empresa_a,
    }


def _sql(sql, params):
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_receita_nao_muda_valor_por_sql_direto(base):
    with pytest.raises(IntegrityError):
        _sql(
            "UPDATE fiscal_receitatrimestralpresumido SET valor = 1 WHERE id = %s",
            [base["receita"].pk],
        )


def test_receita_nao_se_apaga_por_sql_direto(base):
    with pytest.raises(IntegrityError):
        _sql("DELETE FROM fiscal_receitatrimestralpresumido WHERE id = %s", [base["receita"].pk])


def test_receita_so_muda_pelo_estorno_via_sql_com_motivo(base):
    # O estorno é a única alteração: ativa → estornada, com motivo e quem estornou.
    # Outras colunas não mudam.
    _sql(
        "UPDATE fiscal_receitatrimestralpresumido SET estado = 'estornada', motivo_estorno = 'x', "
        "estornada_em = now(), estornada_por_id = %s WHERE id = %s",
        [base["receita"].criada_por_id, base["receita"].pk],
    )
    base["receita"].refresh_from_db()
    assert base["receita"].estado == "estornada"
    with pytest.raises(IntegrityError):
        _sql(
            "UPDATE fiscal_receitatrimestralpresumido SET descricao = 'trocada' WHERE id = %s",
            [base["receita"].pk],
        )


def test_receita_de_outra_empresa_na_atividade_e_recusada_pelo_banco(
    base, empresa_b, usuario_gestor_a
):
    from apps.fiscal.models import AtividadePresuncaoEmpresa

    outra_atividade = AtividadePresuncaoEmpresa.objects.create(
        empresa=empresa_b,
        atividade=tab.SERVICOS_GERAIS,
        inicio=date(2026, 1, 1),
        criada_por=usuario_gestor_a,
    )
    with pytest.raises(IntegrityError):
        _sql(
            "INSERT INTO fiscal_receitatrimestralpresumido (empresa_id, ano, trimestre, tipo, "
            "atividade_id, "
            "descricao, valor, suporte, estado, motivo_estorno, criada_em, criada_por_id) "
            "VALUES (%s, 2026, 2, 'presuncao', %s, 'x', 10, 'y', 'ativa', '', now(), %s)",
            [base["empresa"].pk, outra_atividade.pk, usuario_gestor_a.pk],
        )


def test_declaracao_de_integrais_nao_muda_nem_se_apaga(base):
    with pytest.raises(IntegrityError):
        _sql(
            "UPDATE fiscal_declaracaoreceitasintegrais SET total = 0 WHERE id = %s",
            [base["declaracao"].pk],
        )
    with pytest.raises(IntegrityError):
        _sql(
            "DELETE FROM fiscal_declaracaoreceitasintegrais WHERE id = %s", [base["declaracao"].pk]
        )


def test_confirmacao_so_vai_de_ativa_a_substituida(base):
    with pytest.raises(IntegrityError):
        _sql(
            "UPDATE fiscal_confirmacaoretencaopresumido SET irrf_confirmado = 1 WHERE id = %s",
            [base["confirmacao"].pk],
        )
    with pytest.raises(IntegrityError):
        _sql(
            "DELETE FROM fiscal_confirmacaoretencaopresumido WHERE id = %s",
            [base["confirmacao"].pk],
        )
    _sql(
        "UPDATE fiscal_confirmacaoretencaopresumido SET estado = 'substituida' WHERE id = %s",
        [base["confirmacao"].pk],
    )
    base["confirmacao"].refresh_from_db()
    assert base["confirmacao"].estado == "substituida"


def test_medida_so_muda_pela_revogacao(base):
    with pytest.raises(IntegrityError):
        _sql(
            "UPDATE fiscal_medidajudiciallc224 SET numero_processo = 'outro' WHERE id = %s",
            [base["medida"].pk],
        )
    with pytest.raises(IntegrityError):
        _sql("DELETE FROM fiscal_medidajudiciallc224 WHERE id = %s", [base["medida"].pk])
    _sql(
        "UPDATE fiscal_medidajudiciallc224 SET ativa = false, revogada_em = now(), "
        "motivo_revogacao = 'cassada' WHERE id = %s",
        [base["medida"].pk],
    )
    base["medida"].refresh_from_db()
    assert base["medida"].ativa is False


def test_confirmacao_nao_nasce_em_nota_que_nao_esta_efetivada(
    base, empresa_a, escritorio_a, usuario_gestor_a
):
    # Nota recebida e só em RASCUNHO: o gatilho recusa a confirmação, mesmo por SQL direto.
    from apps.fiscal import escrituracao as escrituracao_servico
    from apps.fiscal.models import NaturezaOperacao, PapelDocumento, VinculoDocumentoEmpresa
    from apps.fiscal.tests.suporte_presumido_dl079 import receber_prestada

    documento = receber_prestada(
        escritorio_a, usuario_gestor_a, 707, v_serv="500.00", d_compet="2026-01-12"
    )
    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa_a, papel=PapelDocumento.PRESTADOR
    )
    rascunho = escrituracao_servico.salvar_rascunho(
        vinculo, NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR, usuario_gestor_a
    )
    assert rascunho.estado == "rascunho"
    with pytest.raises(IntegrityError):
        _sql(
            "INSERT INTO fiscal_confirmacaoretencaopresumido (escrituracao_id, irrf_confirmado, "
            "motivo, estado, confirmada_em, confirmada_por_id) "
            "VALUES (%s, 1, '', 'ativa', now(), %s)",
            [rascunho.pk, base["confirmacao"].confirmada_por_id],
        )


# ---------------------------------------------------------------------------
# Retenção proposta a partir do XML: regra de `tpRetPisCofins` (HI-103)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_proposta_csll_ausente_nunca_vira_zero(escritorio_a, usuario_gestor_a, empresa_a):
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=702,
        v_serv="1000.00",
        d_compet="2026-01-10",
        tp_ret="8",
    )
    campos = campos_tomada_do_documento(escrituracao.vinculo.documento)
    proposta = proposta_de_retencao(campos)
    assert proposta.csll is None
    assert proposta.csll_situacao == "a_classificar"
    assert proposta.csll_motivo == "vRetCSLL ausente na nota"


@pytest.mark.django_db
def test_proposta_com_pis_cofins_preenchidos_junto_com_codigo_e_ambigua(
    escritorio_a, usuario_gestor_a, empresa_a
):
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=703,
        v_serv="1000.00",
        d_compet="2026-01-10",
        ret_csll="90.00",
        tp_ret="8",
        v_pis="5.00",
        v_cofins="20.00",
    )
    proposta = proposta_de_retencao(campos_tomada_do_documento(escrituracao.vinculo.documento))
    assert proposta.csll is None and proposta.csll_situacao == "a_classificar"
    assert "ambíguo" in proposta.csll_motivo


@pytest.mark.django_db
def test_proposta_exata_com_codigo_8_e_sem_pis_cofins(escritorio_a, usuario_gestor_a, empresa_a):
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=704,
        v_serv="1000.00",
        d_compet="2026-01-10",
        ret_csll="90.00",
        tp_ret="8",
    )
    proposta = proposta_de_retencao(campos_tomada_do_documento(escrituracao.vinculo.documento))
    assert proposta.csll == D("90.00") and proposta.csll_situacao == "exata"


@pytest.mark.django_db
def test_desconto_incondicional_lido_do_xml_e_nao_do_valor_da_nota(
    escritorio_a, usuario_gestor_a, empresa_a
):
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=705,
        v_serv="1000.00",
        d_compet="2026-01-10",
        desc_incond="250.00",
    )
    campos = campos_tomada_do_documento(escrituracao.vinculo.documento)
    assert campos.v_desc_incond == D("250.00")
    assert campos.invalidos == ()


@pytest.mark.django_db
def test_desconto_ausente_no_xml_e_zero_e_nao_o_valor_da_nota(
    escritorio_a, usuario_gestor_a, empresa_a
):
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=706,
        v_serv="1000.00",
        d_compet="2026-01-10",
    )
    campos = campos_tomada_do_documento(escrituracao.vinculo.documento)
    assert campos.v_desc_incond is None  # ausente, e não 1.000,00
    assert any("vDescIncond" in caminho for caminho in campos.ausentes)
