"""DL-075 (frente A) — serviços e persistência: atividades, folha, FS12, imutabilidade.

Cobre os itens 2 e 3 do plano e o critério 12 (imutabilidade no banco, como na DL-074).
Valores de folha e de receita são sintéticos; os esperados são escritos à mão.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.fiscal import folha_fator_r as folha_servico
from apps.fiscal import pre_das as servico
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    AtividadeEmpresa,
    EnquadramentoAtividade,
    FolhaFatorR,
    FolhaImutavel,
    NaturezaOperacao,
)
from apps.fiscal.tests.test_dl074_suporte import escriturar, informar_e_confirmar
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    cenario_simples,
    folha_confirmada,
    folhas_dos_12_meses,
    sequencia_anterior,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Atividades (item 2): vigência, enquadramento, padrão única
# ---------------------------------------------------------------------------


def _dados(**mudancas):
    base = {
        "descricao": "Consultoria sintética",
        "codigo_subitem": "17.01",
        "enquadramento": EnquadramentoAtividade.ANEXO_III,
        "inicio": date(2018, 1, 1),
        "fim": None,
        "padrao": False,
    }
    base.update(mudancas)
    return base


def test_atividade_fim_antes_do_inicio_recusada(empresa_a, usuario_gestor_a):
    with pytest.raises(servico.EntradaInvalidaAtividade):
        servico.cadastrar_atividade(
            empresa_a, _dados(inicio=date(2026, 5, 1), fim=date(2026, 4, 30)), usuario_gestor_a
        )


def test_enquadramento_fora_do_catalogo_recusado(empresa_a, usuario_gestor_a):
    with pytest.raises(servico.EntradaInvalidaAtividade) as excecao:
        servico.cadastrar_atividade(empresa_a, _dados(enquadramento="anexo_i"), usuario_gestor_a)
    assert "fora do catálogo" in excecao.value.mensagem


def test_codigo_do_subitem_so_aceita_digitos_e_pontos(empresa_a, usuario_gestor_a):
    with pytest.raises(servico.EntradaInvalidaAtividade):
        servico.cadastrar_atividade(empresa_a, _dados(codigo_subitem="17.01a"), usuario_gestor_a)
    ok = servico.cadastrar_atividade(empresa_a, _dados(codigo_subitem="17.01"), usuario_gestor_a)
    assert ok.codigo_subitem == "17.01"


def test_segunda_padrao_com_vigencia_sobreposta_recusada(empresa_a, usuario_gestor_a):
    servico.cadastrar_atividade(empresa_a, _dados(padrao=True), usuario_gestor_a)
    with pytest.raises(servico.AtividadeConflito):
        servico.cadastrar_atividade(
            empresa_a,
            _dados(inicio=date(2026, 1, 1), padrao=True, enquadramento="anexo_iv"),
            usuario_gestor_a,
        )


def test_padrao_nova_depois_de_encerrada_a_anterior_e_permitida(empresa_a, usuario_gestor_a):
    antiga = servico.cadastrar_atividade(
        empresa_a, _dados(padrao=True, fim=date(2025, 12, 31)), usuario_gestor_a
    )
    nova = servico.cadastrar_atividade(
        empresa_a, _dados(inicio=date(2026, 1, 1), padrao=True), usuario_gestor_a
    )
    assert antiga.pk != nova.pk
    assert servico.atividade_padrao_do_mes(empresa_a, 2026, 3)[0].pk == nova.pk


def test_padrao_em_aberto_dupla_recusada_pelo_servico(empresa_a, usuario_gestor_a):
    servico.cadastrar_atividade(empresa_a, _dados(padrao=True), usuario_gestor_a)
    with pytest.raises(servico.AtividadeConflito):
        servico.cadastrar_atividade(
            empresa_a, _dados(inicio=date(2030, 1, 1), padrao=True), usuario_gestor_a
        )


def test_atividade_em_uso_por_receita_informada_nao_se_exclui(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade = servico.cadastrar_atividade(empresa, _dados(), usuario_gestor_a)
    servico_receita.lancar_receita_informada(
        empresa,
        2026,
        5,
        "interno",
        "1000.00",
        "outras_receitas_atividade",
        "Motivo sintético.",
        SUPORTE_SINTETICO,
        usuario_gestor_a,
        atividade=atividade,
    )
    with pytest.raises(servico.AtividadeConflito):
        servico.excluir_atividade(atividade, usuario_gestor_a)
    assert AtividadeEmpresa.objects.filter(pk=atividade.pk).exists()


def test_receita_informada_recusa_atividade_de_outra_empresa(
    empresa_a, empresa_a2, usuario_gestor_a
):
    """Isolamento no serviço: atividade de outra empresa é recusada (400), não gravada."""
    empresa = cenario_simples(empresa_a)
    outra = servico.cadastrar_atividade(empresa_a2, _dados(), usuario_gestor_a)
    with pytest.raises(servico_receita.EntradaInvalidaReceita) as excecao:
        servico_receita.lancar_receita_informada(
            empresa,
            2026,
            5,
            "interno",
            "1000.00",
            "outras_receitas_atividade",
            "Motivo sintético.",
            SUPORTE_SINTETICO,
            usuario_gestor_a,
            atividade=outra,
        )
    assert "não pertence a esta empresa" in excecao.value.mensagem


def test_receita_informada_exige_atividade_vigente_no_mes_inteiro(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    encerrada = servico.cadastrar_atividade(
        empresa, _dados(fim=date(2026, 5, 15)), usuario_gestor_a
    )
    with pytest.raises(servico_receita.EntradaInvalidaReceita):
        servico_receita.lancar_receita_informada(
            empresa,
            2026,
            5,
            "interno",
            "1000.00",
            "outras_receitas_atividade",
            "Motivo sintético.",
            SUPORTE_SINTETICO,
            usuario_gestor_a,
            atividade=encerrada,
        )


# ---------------------------------------------------------------------------
# Folha (item 3): lançamento, confirmação, estorno, imutabilidade
# ---------------------------------------------------------------------------


def _componentes(**mudancas):
    base = {
        "remuneracao_empregados_avulsos": "1000.00",
        "pro_labore_autonomos": "0",
        "decimo_terceiro": "0",
        "cpp_recolhida": "0",
        "fgts_recolhido": "0",
    }
    base.update(mudancas)
    return base


def test_folha_componente_negativo_recusado_nomeando_o_componente(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    with pytest.raises(folha_servico.EntradaInvalidaFolha) as excecao:
        folha_servico.lancar_folha(
            empresa,
            2026,
            5,
            _componentes(fgts_recolhido="-1.00"),
            SUPORTE_SINTETICO,
            usuario_gestor_a,
        )
    assert "fgts_recolhido" in excecao.value.mensagem


def test_folha_float_recusado(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    with pytest.raises(folha_servico.EntradaInvalidaFolha):
        folha_servico.lancar_folha(
            empresa, 2026, 5, _componentes(cpp_recolhida=0.1), SUPORTE_SINTETICO, usuario_gestor_a
        )


def test_folha_sem_componente_recusada_nomeando_a_chave(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    componentes = _componentes()
    del componentes["decimo_terceiro"]
    with pytest.raises(folha_servico.EntradaInvalidaFolha) as excecao:
        folha_servico.lancar_folha(
            empresa, 2026, 5, componentes, SUPORTE_SINTETICO, usuario_gestor_a
        )
    assert "decimo_terceiro" in excecao.value.mensagem


def test_folha_sem_documento_de_suporte_recusada(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    with pytest.raises(folha_servico.EntradaInvalidaFolha):
        folha_servico.lancar_folha(empresa, 2026, 5, _componentes(), "   ", usuario_gestor_a)


def test_segundo_lancamento_no_mes_recusado_enquanto_o_primeiro_esta_ativo(
    empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    folha_servico.lancar_folha(
        empresa, 2026, 5, _componentes(), SUPORTE_SINTETICO, usuario_gestor_a
    )
    with pytest.raises(folha_servico.FolhaErro):
        folha_servico.lancar_folha(
            empresa, 2026, 5, _componentes(), SUPORTE_SINTETICO, usuario_gestor_a
        )


def test_folha_estornada_libera_novo_lancamento_do_mes(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    primeira = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    folha_servico.estornar_folha(primeira, "Valor digitado errado.", usuario_gestor_a)
    nova = folha_servico.lancar_folha(
        empresa, 2026, 5, _componentes(), SUPORTE_SINTETICO, usuario_gestor_a
    )
    assert nova.estado == "rascunho"
    assert FolhaFatorR.objects.filter(empresa=empresa, ano=2026, mes=5).count() == 2


def test_so_rascunho_confirma_e_so_confirmada_estorna(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    folha = folha_servico.lancar_folha(
        empresa, 2026, 5, _componentes(), SUPORTE_SINTETICO, usuario_gestor_a
    )
    with pytest.raises(folha_servico.FolhaErro):
        folha_servico.estornar_folha(folha, "Motivo.", usuario_gestor_a)
    confirmada = folha_servico.confirmar_folha(folha, usuario_gestor_a)
    with pytest.raises(folha_servico.FolhaErro):
        folha_servico.confirmar_folha(confirmada, usuario_gestor_a)


def test_estorno_exige_motivo(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    with pytest.raises(folha_servico.EntradaInvalidaFolha):
        folha_servico.estornar_folha(folha, "   ", usuario_gestor_a)


def test_folha_confirmada_nao_muda_pelo_python(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    folha.remuneracao_empregados_avulsos = Decimal("9999.00")
    with pytest.raises(FolhaImutavel):
        folha.save()
    with pytest.raises(FolhaImutavel):
        folha.delete()


def test_banco_recusa_update_direto_de_folha_confirmada(empresa_a, usuario_gestor_a):
    """O gatilho da migração 0004 recusa o que escapa do Python (QuerySet.update)."""
    empresa = cenario_simples(empresa_a)
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FolhaFatorR.objects.filter(pk=folha.pk).update(
                remuneracao_empregados_avulsos=Decimal("9999.00")
            )


def test_banco_recusa_delete_de_folha_confirmada(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FolhaFatorR.objects.filter(pk=folha.pk).delete()


def test_total_da_folha_e_a_soma_dos_componentes(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    folha = folha_servico.lancar_folha(
        empresa,
        2026,
        5,
        {
            "remuneracao_empregados_avulsos": "1000.00",
            "pro_labore_autonomos": "200.00",
            "decimo_terceiro": "100.00",
            "cpp_recolhida": "300.00",
            "fgts_recolhido": "80.50",
        },
        SUPORTE_SINTETICO,
        usuario_gestor_a,
    )
    assert folha.total == Decimal("1680.50")


# ---------------------------------------------------------------------------
# FS12 (item 3): janela do art. 22 no ano de início, e mês pendente
# ---------------------------------------------------------------------------


def test_fs12_com_12_meses_e_a_soma_da_folha(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [Decimal("1000")] * 12)

    fs = folha_servico.fs12(empresa, 2026, 6)

    assert (fs.regra, fs.valor, fs.divisor) == ("§ 1º", Decimal("12000"), 12)


def test_fs12_no_ano_de_inicio_usa_media_vezes_12_dos_meses_de_atividade(
    empresa_a, usuario_gestor_a
):
    """Abertura em 10/03/2026, Simples em 01/03/2026 (ano da opção 2026), PA 06/2026.

    Pelo art. 22 § 3º: meses de atividade anteriores ao PA = 03, 04 e 05 (3 meses);
    FS12 = (soma / 3) × 12. Com 30.000 por mês: FS12 = 360.000. Não exige folha de
    antes da abertura.
    """
    empresa = cenario_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 1)
    )
    for mes in (3, 4, 5):
        folha_confirmada(empresa, usuario_gestor_a, 2026, mes, remuneracao="30000")

    fs = folha_servico.fs12(empresa, 2026, 6)

    assert (fs.regra, fs.divisor) == ("§ 3º", 3)
    assert fs.valor == Decimal("360000")


def test_fs12_de_mes_com_folha_so_em_rascunho_fica_pendente(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    for ano, mes in sequencia_anterior(2026, 6)[:-1]:
        folha_confirmada(empresa, usuario_gestor_a, ano, mes, remuneracao="1000")
    folha_servico.lancar_folha(
        empresa, 2026, 5, _componentes(), SUPORTE_SINTETICO, usuario_gestor_a
    )

    fs = folha_servico.fs12(empresa, 2026, 6)

    assert fs.valor is None
    assert fs.pendentes == ((2026, 5, "rascunho"),)


def test_fs12_de_empresa_sem_data_de_abertura_recusa_como_o_rbt12(empresa_a):
    empresa = cenario_simples(empresa_a)
    empresa.data_abertura_cnpj = None
    empresa.save(update_fields=["data_abertura_cnpj"])
    with pytest.raises(apuracao.ApuracaoRecusada):
        folha_servico.fs12(empresa, 2026, 6)


# ---------------------------------------------------------------------------
# Consistência entre a composição do mês e a leitura por natureza (item 4)
# ---------------------------------------------------------------------------


def test_lancamentos_do_mes_batem_com_a_composicao(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9301,
        competencia=(2026, 6),
        valor="700.00",
        natureza=NaturezaOperacao.PRESTADO_ISS_RETIDO,
    )
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9302,
        competencia=(2026, 6),
        valor="300.00",
        natureza=NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO,
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 6, "1000.00")
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 6, "50.00", mercado="externo")

    composicao = servico_receita.composicao_do_mes(empresa, 2026, 6)
    lancamentos = servico_receita.lancamentos_do_mes(empresa, 2026, 6)

    por_mercado_documento = {"interno": Decimal("0"), "externo": Decimal("0")}
    for natureza, valor in lancamentos.documento_por_natureza.items():
        por_mercado_documento[servico_receita.mercado_da_natureza(natureza)] += valor
    assert por_mercado_documento["interno"] == composicao.de("interno").documento
    assert por_mercado_documento["externo"] == composicao.de("externo").documento
    informado = {"interno": Decimal("0"), "externo": Decimal("0")}
    for linha in lancamentos.informados:
        informado[linha.mercado] += linha.valor
    assert informado["interno"] == composicao.de("interno").informado
    assert informado["externo"] == composicao.de("externo").informado


def test_toda_natureza_tem_destino_no_pre_das():
    """Nenhuma natureza do catálogo fica sem segmento ou sem recusa (HI-68)."""
    cobertas = set(servico.SEGMENTO_DA_NATUREZA) | set(servico.MOTIVO_FORA_DO_CORTE)
    assert cobertas == set(NaturezaOperacao.values)
    assert not (set(servico.SEGMENTO_DA_NATUREZA) & set(servico.MOTIVO_FORA_DO_CORTE))
