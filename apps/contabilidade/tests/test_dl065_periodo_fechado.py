"""DL-065 (BL-550) — reclassificação de conta com movimento em competência
encerrada ou entregue: a REGRA, no modelo e nos dois serviços de
classificação das demonstrações anuais.

Este arquivo cobre os critérios 1 a 7 e o 9 do plano
(`docs/planos/DL-065-reclassificacao-em-periodo-fechado.md`). As portas
(HTTP, API e admin) e a prova de que a DRE continua livre são do arquivo
`test_dl065_portas.py`.

- 1: trocar a linha da DLPA com movimento em competência ABERTA é aceito, e a
  trilha registra antes/depois;
- 2: o mesmo em competência ENCERRADA é recusado, e a mensagem NOMEIA o
  período;
- 3: o mesmo para a coluna da DMPL;
- 4: a PRIMEIRA classificação é livre mesmo com movimento em período
  encerrado — sem isso o plano de contas de uma empresa em operação não
  poderia ser classificado;
- 5: REMOVER a classificação é troca, e é recusado;
- 6: movimento de DESCENDENTE bloqueia a conta sintética;
- 7: competência ENTREGUE produz mensagem própria;
- 9: a recusa não grava — valor intacto e NENHUM registro na trilha.

Limites: competência do mês seguinte (o caso que a reclassificação de hoje
quebra em silêncio), mais de uma competência fechada, período REABERTO
(a regra acompanha o estado), e conta sem movimento no período fechado.

Dados 100% sintéticos. Datas em 2026, no passado.
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO,
    ClassificacaoDlpa,
    ClassificacaoDmpl,
    NaturezaConta,
    TipoConta,
)
from apps.contabilidade.services import (
    ClassificacaoAlteraPeriodoFechado,
    classificar_conta_na_dlpa,
    classificar_conta_na_dmpl,
    encerrar_competencia,
    marcar_competencia_como_entregue,
    reabrir_competencia,
)
from apps.contabilidade.tests import test_dl061_dmpl as _base

pytestmark = pytest.mark.django_db

C = NaturezaConta.CREDORA
PL = TipoConta.PATRIMONIO_LIQUIDO

ANO = 2026
MES = 3


def _cenario(nome="dl065"):
    """Empresa com duas contas de PL já classificadas — uma só na DLPA e outra
    só na DMPL.

    Cada uma fica classificada em **uma** das demonstrações de propósito: a
    guarda de consistência `divergencia_entre_dlpa_e_dmpl` (E1 da DL-061) só
    compara quando as DUAS existem, e um par completo faria o teste medir
    essa regra em vez da nova.
    """
    empresa = _base._empresa(f"Empresa {nome}")
    contas = _base._plano_basico(empresa)
    gestor = _base._gestor(empresa, f"gestor-{nome}-{empresa.pk}")
    conta_dlpa = _base._conta(
        empresa,
        "3.7",
        "Dividendos a Pagar DL-065",
        PL,
        C,
        dlpa=ClassificacaoDlpa.DIVIDENDO,
        pai=contas["pl"],
    )
    conta_dmpl = _base._conta(
        empresa,
        "3.8",
        "Reserva de Lucros a Realizar DL-065",
        PL,
        C,
        dmpl=ClassificacaoDmpl.RESERVA_DE_LUCROS_A_REALIZAR,
        pai=contas["pl"],
    )
    return empresa, contas, gestor, conta_dlpa, conta_dmpl


def _movimentar(empresa, contas, conta, data=date(2026, 3, 15), valor="1000.00"):
    """Lançamento balanceado que toca a conta — é o movimento que a guarda
    considera, e ele precisa existir para a regra ter o que proteger."""
    return _base._lancar(empresa, data, "Constituição", contas["caixa"], conta, valor)


def _trilhas(acao):
    return list(RegistroAuditoria.objects.filter(acao=acao))


# ---------------------------------------------------------------------------
# Critério 1 — período ABERTO: a troca continua sendo o caminho normal
# ---------------------------------------------------------------------------


def test_criterio1_trocar_a_linha_da_dlpa_em_periodo_aberto_e_aceito():
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)

    classificar_conta_na_dlpa(
        conta=conta_dlpa,
        classificacao=ClassificacaoDlpa.RESERVA_LEGAL,
        usuario=gestor,
    )

    conta_dlpa.refresh_from_db()
    assert conta_dlpa.classificacao_dlpa == ClassificacaoDlpa.RESERVA_LEGAL
    registros = _trilhas("conta.classificacao_dlpa_alterada")
    assert len(registros) == 1
    assert registros[0].detalhes["classificacao_dlpa_antes"] == ClassificacaoDlpa.DIVIDENDO
    assert registros[0].detalhes["classificacao_dlpa_depois"] == ClassificacaoDlpa.RESERVA_LEGAL


# ---------------------------------------------------------------------------
# Critério 2 — competência ENCERRADA: recusado, e nomeando o período
# ---------------------------------------------------------------------------


def test_criterio2_trocar_a_linha_da_dlpa_em_periodo_encerrado_e_recusado():
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dlpa(
            conta=conta_dlpa,
            classificacao=ClassificacaoDlpa.RESERVA_LEGAL,
            usuario=gestor,
        )

    mensagem = str(erro.value)
    assert "03/2026" in mensagem, "a recusa tem de dizer QUAL competência impede a troca"
    assert "encerrada" in mensagem


# ---------------------------------------------------------------------------
# Critério 3 — a coluna da DMPL, mesma regra
# ---------------------------------------------------------------------------


def test_criterio3_trocar_a_coluna_da_dmpl_em_periodo_encerrado_e_recusado():
    empresa, contas, gestor, _, conta_dmpl = _cenario()
    _movimentar(empresa, contas, conta_dmpl)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dmpl(
            conta=conta_dmpl,
            classificacao=ClassificacaoDmpl.RESERVA_LEGAL,
            usuario=gestor,
        )

    assert "coluna da DMPL" in str(erro.value)
    assert "03/2026" in str(erro.value)


# ---------------------------------------------------------------------------
# Critério 4 — a PRIMEIRA classificação é livre
# ---------------------------------------------------------------------------


def test_criterio4_primeira_classificacao_e_livre_com_periodo_encerrado():
    """Sem este critério o produto ficaria inutilizável: nenhuma migração
    classificou conta alguma, então uma empresa já em operação tem o plano
    inteiro por classificar — e quase toda conta real já tem movimento."""
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    sem_classificacao = _base._conta(
        empresa, "3.9", "Reserva de Contingência DL-065", PL, C, pai=contas["pl"]
    )
    _movimentar(empresa, contas, sem_classificacao)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    classificar_conta_na_dlpa(
        conta=sem_classificacao,
        classificacao=ClassificacaoDlpa.RESERVA_PARA_CONTINGENCIAS,
        usuario=gestor,
    )

    sem_classificacao.refresh_from_db()
    assert sem_classificacao.classificacao_dlpa == ClassificacaoDlpa.RESERVA_PARA_CONTINGENCIAS


# ---------------------------------------------------------------------------
# Critério 5 — remover é troca
# ---------------------------------------------------------------------------


def test_criterio5_remover_a_classificacao_em_periodo_encerrado_e_recusado():
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado):
        classificar_conta_na_dlpa(conta=conta_dlpa, classificacao=None, usuario=gestor)

    conta_dlpa.refresh_from_db()
    assert conta_dlpa.classificacao_dlpa == ClassificacaoDlpa.DIVIDENDO


# ---------------------------------------------------------------------------
# Critério 6 — descendente
# ---------------------------------------------------------------------------


def test_criterio6_movimento_de_descendente_bloqueia_a_conta_sintetica():
    """Reclassificar um GRUPO cujo movimento vem das filhas reescreveria a
    demonstração do grupo do mesmo jeito — é o que o BL-245 já mediu para
    natureza e tipo."""
    empresa, contas, gestor, _, conta_dmpl = _cenario()
    grupo = _base._conta(
        empresa,
        "3.10",
        "Reservas DL-065",
        PL,
        C,
        dmpl=ClassificacaoDmpl.RESERVA_ESTATUTARIA,
        pai=contas["pl"],
    )
    filha = _base._conta(empresa, "3.10.1", "Reserva Filha DL-065", PL, C, pai=grupo)
    _movimentar(empresa, contas, filha)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dmpl(
            conta=grupo, classificacao=ClassificacaoDmpl.RESERVA_LEGAL, usuario=gestor
        )

    assert "descendente" in str(erro.value)


# ---------------------------------------------------------------------------
# Critério 7 — competência ENTREGUE
# ---------------------------------------------------------------------------


def test_criterio7_competencia_entregue_tem_mensagem_propria():
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    marcar_competencia_como_entregue(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dlpa(
            conta=conta_dlpa, classificacao=ClassificacaoDlpa.RESERVA_LEGAL, usuario=gestor
        )

    mensagem = str(erro.value)
    assert "entregue" in mensagem
    assert "lançamento na competência aberta" in mensagem, (
        "período entregue não tem volta: a mensagem precisa dizer onde se corrige"
    )


# ---------------------------------------------------------------------------
# Critério 9 — a recusa não grava NADA
# ---------------------------------------------------------------------------


def test_criterio9_a_recusa_nao_grava_valor_nem_trilha():
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    trilhas_antes = len(_trilhas("conta.classificacao_dlpa_alterada"))

    with pytest.raises(ClassificacaoAlteraPeriodoFechado):
        classificar_conta_na_dlpa(
            conta=conta_dlpa, classificacao=ClassificacaoDlpa.RESERVA_LEGAL, usuario=gestor
        )

    conta_dlpa.refresh_from_db()
    assert conta_dlpa.classificacao_dlpa == ClassificacaoDlpa.DIVIDENDO
    assert len(_trilhas("conta.classificacao_dlpa_alterada")) == trilhas_antes


# ---------------------------------------------------------------------------
# Limites
# ---------------------------------------------------------------------------


def test_limite_competencia_do_mes_seguinte_tambem_bloqueia():
    """O caso silencioso: o lançamento é de março, a reclassificação é feita
    em abril, e a DLPA de MARCHÇO — já fechada — é a que muda. Uma guarda que
    olhasse só a competência "atual" deixaria passar exatamente este caso."""
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dlpa(
            conta=conta_dlpa, classificacao=ClassificacaoDlpa.RESERVA_LEGAL, usuario=gestor
        )

    assert "03/2026" in str(erro.value)


def test_limite_a_mensagem_nomeia_a_competencia_mais_recente():
    """Duas competências fechadas com movimento: as duas continuam barradas,
    e a que é nomeada é a mais recente — é a que o contador precisa ver
    primeiro."""
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa, data=date(2026, 3, 15))
    _movimentar(empresa, contas, conta_dlpa, data=date(2026, 4, 20), valor="200.00")
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=4, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dlpa(
            conta=conta_dlpa, classificacao=ClassificacaoDlpa.RESERVA_LEGAL, usuario=gestor
        )

    assert "04/2026" in str(erro.value)


def test_limite_periodo_reaberto_deixa_de_barrar():
    """A regra acompanha o ESTADO da competência, não o registro de que houve
    recusa: reabrir o período é o caminho que o próprio produto oferece para
    corrigir o cadastro, e ele precisa funcionar."""
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    reabrir_competencia(
        empresa=empresa, ano=ANO, mes=MES, usuario=gestor, motivo="correção de cadastro"
    )

    classificar_conta_na_dlpa(
        conta=conta_dlpa, classificacao=ClassificacaoDlpa.RESERVA_LEGAL, usuario=gestor
    )

    conta_dlpa.refresh_from_db()
    assert conta_dlpa.classificacao_dlpa == ClassificacaoDlpa.RESERVA_LEGAL


def test_limite_conta_sem_movimento_no_periodo_fechado_pode_ser_trocada():
    """Nada do que já foi apurado muda, então a trava não tem o que proteger:
    barrar aqui só criaria atrito sem dano."""
    empresa, _, gestor, conta_dlpa, _ = _cenario()
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    classificar_conta_na_dlpa(
        conta=conta_dlpa, classificacao=ClassificacaoDlpa.RESERVA_LEGAL, usuario=gestor
    )

    conta_dlpa.refresh_from_db()
    assert conta_dlpa.classificacao_dlpa == ClassificacaoDlpa.RESERVA_LEGAL


# ---------------------------------------------------------------------------
# O `code` que faz a tradução para 409 — a assinatura entre modelo e serviço
# ---------------------------------------------------------------------------


def test_o_codigo_do_modelo_e_o_que_o_servico_reconhece():
    """Se alguém trocar o `code` em `Conta.clean()` sem atualizar o serviço, a
    regra continua valendo no admin e **some na API**, que voltaria a
    responder 400. Este teste prende as duas pontas."""
    empresa, contas, gestor, conta_dlpa, _ = _cenario()
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    conta_dlpa.classificacao_dlpa = ClassificacaoDlpa.RESERVA_LEGAL
    with pytest.raises(ValidationError) as erro:
        conta_dlpa.full_clean()

    codigos = {
        erro.code
        for erros in erro.value.error_dict.values()
        for erro in erros
        if getattr(erro, "code", None)
    }
    assert CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO in codigos
