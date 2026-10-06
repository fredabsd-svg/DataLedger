"""DL-066, etapa 2 — a porta de classificação da DFC
(`classificar_conta_na_dfc`) e a guarda de período fechado da DL-065
estendida aos três campos da conta.

Cobre os critérios de aceite 14 e 15 da etapa 2
(`docs/planos/DL-066-dfc.md`):

- 14: a classificação grava com trava (`select_for_update`), trilha
  antes/depois na mesma transação, e recusa de período fechado (encerrada E
  entregue) com mensagem verdadeira — nunca "reabra a competência" para
  competência entregue (achado A3 da DL-065);
- 15: a recusa vale também pelo caminho validado do admin — a regra mora em
  `Conta.clean()`, não só na porta de serviço.

Mais: a primeira marcação continua livre em período fechado (o caminho que
limpa o veto da própria DFC), sem-operação não grava nem registra, e a
guarda de coerência (caixa **e** atividade na mesma conta) continua valendo
na porta nova.

Dados 100% sintéticos. Datas em 2026, no passado.
"""

import threading
from datetime import date

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.admin import ContaAdmin
from apps.contabilidade.models import (
    CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO,
    ClassificacaoFluxoCaixa,
    Conta,
    NaturezaConta,
    TipoConta,
)
from apps.contabilidade.services import (
    ClassificacaoAlteraPeriodoFechado,
    classificar_conta_na_dfc,
    encerrar_competencia,
    marcar_competencia_como_entregue,
)
from apps.contabilidade.tests import test_dl061_dmpl as _base

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA
ATIVO = TipoConta.ATIVO
RECEITA = TipoConta.RECEITA
DESPESA = TipoConta.DESPESA

ATIV = ClassificacaoFluxoCaixa.OPERACIONAL
INVEST = ClassificacaoFluxoCaixa.INVESTIMENTO

ANO = 2026
MES = 3


def _cenario(nome="dl066c"):
    """Empresa com a caixa já marcada e uma conta de resultado sem nenhuma
    classificação — o estado em que a porta nova costuma ser usada pela
    primeira vez."""
    empresa = _base._empresa(f"Empresa {nome}")
    contas = _base._plano_basico(empresa)
    gestor = _base._gestor(empresa, f"gestor-{nome}-{empresa.pk}")
    # A caixa do plano base ("1.1") é a conta de caixa marcada do cenário, e a
    # receita do plano base ("4.1") é a conta de resultado a classificar — o
    # plano básico já cria as duas, e recriá-las com os mesmos códigos colidia
    # na constraint única (empresa, codigo).
    caixa = contas["caixa"]
    caixa.caixa_e_equivalentes = True
    caixa.full_clean()
    caixa.save()
    receita = contas["receita"]
    return empresa, contas, gestor, caixa, receita


def _trilhas(acao="conta.classificacao_dfc_alterada"):
    return list(RegistroAuditoria.objects.filter(acao=acao))


def _movimentar(empresa, contas, conta, valor="1000.00"):
    """Lançamento balanceado que toca a conta — é o movimento que a guarda de
    período fechado considera."""
    return _base._lancar(empresa, date(2026, 3, 15), "Movimento", contas["caixa"], conta, valor)


# ---------------------------------------------------------------------------
# Critério 14 — gravação, trava e trilha
# ---------------------------------------------------------------------------


def test_classifica_os_tres_campos_e_registra_antes_e_depois():
    empresa, contas, gestor, caixa, receita = _cenario("grava")

    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=True,
        usuario=gestor,
    )

    receita.refresh_from_db()
    assert receita.classificacao_dfc == ATIV
    assert receita.item_de_resultado_sem_caixa is True
    assert receita.caixa_e_equivalentes is False

    registros = _trilhas()
    assert len(registros) == 1
    detalhes = registros[0].detalhes
    # A trilha registra SÓ os campos que mudaram, com antes/depois de cada um.
    assert detalhes == {
        "classificacao_dfc": {"antes": None, "depois": ATIV},
        "item_de_resultado_sem_caixa": {"antes": False, "depois": True},
    }


def test_sem_mudanca_nao_grava_e_nao_registra():
    empresa, contas, gestor, caixa, receita = _cenario("sem-mudanca")
    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=False,
        usuario=gestor,
    )

    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=False,
        usuario=gestor,
    )

    assert len(_trilhas()) == 1, "a repetição do mesmo estado não pode registrar trilha"


def test_guarda_de_coerencia_caixa_e_atividade_continua_valendo_na_porta():
    """A conta não pode ser caixa E ter atividade ao mesmo tempo (o achado A5
    da fatia 1: o par some da DFC sem veto). A regra mora em `Conta.clean()`
    e a porta nova não pode contorná-la."""
    empresa, contas, gestor, caixa, receita = _cenario("coerencia")

    with pytest.raises(ValidationError) as erro:
        classificar_conta_na_dfc(
            conta=caixa,
            caixa_e_equivalentes=True,
            classificacao_dfc=ATIV,
            item_de_resultado_sem_caixa=False,
            usuario=gestor,
        )

    assert "caixa" in str(erro.value).lower()
    assert _trilhas() == [], "recusa não grava nem registra"


# ---------------------------------------------------------------------------
# Critério 14/15 — período fechado: recusa, nomeia o período, diz o caminho
# ---------------------------------------------------------------------------


def test_trocar_a_atividade_com_movimento_em_periodo_encerrado_e_recusado():
    empresa, contas, gestor, caixa, receita = _cenario("encerrado")
    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=False,
        usuario=gestor,
    )
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dfc(
            conta=receita,
            caixa_e_equivalentes=False,
            classificacao_dfc=INVEST,
            item_de_resultado_sem_caixa=False,
            usuario=gestor,
        )

    mensagem = str(erro.value)
    assert "03/2026" in mensagem, "a recusa tem de dizer QUAL competência impede a troca"
    assert "encerrada" in mensagem
    assert "atividade da DFC" in mensagem


def test_competencia_entregue_nao_manda_reabrir_e_orienta_o_ajuste():
    """Achado A3 da DL-065 levado aos campos da DFC: competência ENTREGUE não
    se reabre (`reabrir_competencia` recusa sempre, RC-101). A mensagem que
    manda "reabra a competência" aqui envia o contador para uma porta que o
    próprio produto fecha — a frase é proibida neste caso."""
    empresa, contas, gestor, caixa, receita = _cenario("entregue")
    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=False,
        usuario=gestor,
    )
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    marcar_competencia_como_entregue(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dfc(
            conta=receita,
            caixa_e_equivalentes=False,
            classificacao_dfc=INVEST,
            item_de_resultado_sem_caixa=False,
            usuario=gestor,
        )

    mensagem = str(erro.value)
    assert "reabra a competência" not in mensagem.lower(), (
        "competência entregue não se reabre — a mensagem não pode mandar reabrir"
    )
    assert "entregue" in mensagem
    assert "ajuste" in mensagem, "a recusa tem de dizer o caminho que existe (lançamento de ajuste)"


def test_desmarcar_caixa_e_quem_ja_estava_marcado_em_periodo_encerrado_e_recusado():
    """DESmarcar (`True` -> `False`) é reescrita retroativa da DFC — a conta
    sairia da conciliação do item 45 de um período já fechado. Recusado."""
    empresa, contas, gestor, caixa, receita = _cenario("desmarcar")
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dfc(
            conta=caixa,
            caixa_e_equivalentes=False,
            classificacao_dfc=None,
            item_de_resultado_sem_caixa=False,
            usuario=gestor,
        )

    assert "caixa e equivalentes" in str(erro.value)
    caixa.refresh_from_db()
    assert caixa.caixa_e_equivalentes is True, "a recusa não pode deixar rastro"


def test_desmarcar_item_sem_caixa_em_periodo_encerrado_e_recusado():
    empresa, contas, gestor, caixa, receita = _cenario("item-sem-caixa")
    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=True,
        usuario=gestor,
    )
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dfc(
            conta=receita,
            caixa_e_equivalentes=False,
            classificacao_dfc=ATIV,
            item_de_resultado_sem_caixa=False,
            usuario=gestor,
        )

    assert "item de resultado sem caixa" in str(erro.value)
    receita.refresh_from_db()
    assert receita.item_de_resultado_sem_caixa is True, "a recusa não pode deixar rastro"


def test_primeira_marcacao_continua_livre_em_periodo_encerrado():
    """A PRIMEIRA marcação é o caminho que limpa o veto da própria DFC (a
    pendência "lançamento sem atividade" e a ausência de conta de caixa).
    Bloqueá-la deixaria a DFC de uma empresa em operação inemitível para
    sempre — mesmo motivo pelo qual a DLPA e a DMPL a mantêm livre."""
    empresa, contas, gestor, caixa, receita = _cenario("primeira")
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=True,
        usuario=gestor,
    )

    receita.refresh_from_db()
    assert receita.classificacao_dfc == ATIV
    assert receita.item_de_resultado_sem_caixa is True


def test_movimento_de_descendente_tambem_protege_a_conta_pai():
    """A guarda considera a subárvore inteira (mesma regra da DLPA/DMPL):
    reclassificar o pai reescreveria a DFC do período fechado do mesmo jeito
    que reclassificar a filha."""
    empresa, contas, gestor, caixa, receita = _cenario("descendente")
    sintetica = _base._conta(empresa, "4", "Receitas", RECEITA, C)
    filha = _base._conta(empresa, "4.9", "Receita Filha DL-066", RECEITA, C, pai=sintetica)
    # A primeira classificação é livre e acontece no período ABERTO — o que o
    # teste mede é a RECLASSIFICAÇÃO depois do fechamento.
    classificar_conta_na_dfc(
        conta=sintetica,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=False,
        usuario=gestor,
    )
    _movimentar(empresa, contas, filha)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        classificar_conta_na_dfc(
            conta=sintetica,
            caixa_e_equivalentes=False,
            classificacao_dfc=INVEST,
            item_de_resultado_sem_caixa=False,
            usuario=gestor,
        )

    assert "descendente" in str(erro.value)


# ---------------------------------------------------------------------------
# Critério 15 — a regra mora no modelo: o caminho do admin (full_clean)
# ---------------------------------------------------------------------------


def test_o_full_clean_puro_tambem_recusa_e_carrega_o_codigo_da_dl065():
    """O admin grava os campos POR FORA dos serviços — é por isso que a regra
    mora em `Conta.clean()` (DL-065, E1). Quem chama `full_clean()` sem passar
    pelo serviço recebe o MESMO `ValidationError`, com o código que a
    tradução para 409 conhece."""
    empresa, contas, gestor, caixa, receita = _cenario("admin")
    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=False,
        usuario=gestor,
    )
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    receita.classificacao_dfc = INVEST
    with pytest.raises(ValidationError) as erro:
        receita.full_clean()

    codigos = {
        item.code
        for erros in getattr(erro.value, "error_dict", {}).values()
        for item in erros
        if getattr(item, "code", None)
    }
    assert CODIGO_CLASSIFICACAO_DE_PERIODO_FECHADO in codigos
    receita.refresh_from_db()
    assert receita.classificacao_dfc == ATIV


# ---------------------------------------------------------------------------
# B1 (BAIXO) da auditoria da etapa 2 — o critério 15 pelo caminho do admin
# ---------------------------------------------------------------------------


def _para_o_formulario(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "on" if valor else ""
    return str(valor)


def _formulario_do_admin(conta, **mudancas):
    """Instancia o MESMO `ModelForm` que o admin gera — o caminho que o
    Django percorre de verdade ao salvar pelo admin (`_post_clean` →
    `instance.full_clean()`). Molde de `test_dl065_portas.py`."""
    admin = ContaAdmin(Conta, AdminSite())
    request = RequestFactory().get("/admin/contabilidade/conta/")
    request.user = _base._gestor(conta.empresa, f"gestor-admin-{conta.pk}")
    classe = admin.get_form(request)
    dados = {nome: _para_o_formulario(getattr(conta, nome, None)) for nome in classe.base_fields}
    dados.update(mudancas)
    return classe(instance=conta, data=dados)


def test_b1_o_modelo_do_admin_recusa_a_mudanca_em_periodo_fechado():
    """Critério 15 pelo caminho de verdade do admin: o `ModelForm` que ele
    gera recusa a mudança dos campos da DFC com movimento em competência
    fechada — não só o `full_clean()` puro."""
    empresa, contas, gestor, caixa, receita = _cenario("admin-form")
    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=True,
        usuario=gestor,
    )
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    form = _formulario_do_admin(receita, classificacao_dfc=INVEST.value)

    assert not form.is_valid()
    assert any(
        "03/2026" in mensagem for mensagens in form.errors.values() for mensagem in mensagens
    )


def test_b1_os_tres_campos_continuam_visiveis_no_admin():
    """Esconder o campo calaria o admin sem fechar a regra — a trava tem de
    ser a regra, não o sumiço (mesma lição do critério 8 da DL-065)."""
    empresa, contas, gestor, caixa, receita = _cenario("admin-visivel")

    form = _formulario_do_admin(receita)

    assert "caixa_e_equivalentes" in form.fields
    assert "classificacao_dfc" in form.fields
    assert "item_de_resultado_sem_caixa" in form.fields


# ---------------------------------------------------------------------------
# A4 (MÉDIO) da auditoria da etapa 2 — a trava da porta, com prova de corrida
# ---------------------------------------------------------------------------


def test_a4_corrida_na_classificacao_da_dfc_serializa_e_a_trilha_fica_coerente(monkeypatch):
    """Espelho do R4 da DRE (`test_dl045_dre.py`): sem o
    `select_for_update()` do serviço, duas classificações concorrentes da
    MESMA conta leem o valor gravado ao mesmo tempo, e a segunda registra na
    trilha um "antes" que já não era o valor real. A barreira força a
    intercalação determinística: a primeira thread para em `full_clean()` já
    com a trava adquirida; a segunda só chega ao `full_clean()` depois de
    adquirir a MESMA trava — o que exige a primeira comitar. Sem a trava, a
    segunda chega sem esperar e a coerência da trilha reprova.

    ⚠️ Vale como prova de corrida só em PostgreSQL (a CI): em SQLite a
    trava degrada para leitura em memória e este teste é da classe de
    ambiente — o mesmo destino do R4 na linha de base local."""
    primeira_travou = threading.Event()
    pode_comitar_a_primeira = threading.Event()
    original_full_clean = Conta.full_clean

    def full_clean_com_barreira(self, *args, **kwargs):
        resultado = original_full_clean(self, *args, **kwargs)
        if not primeira_travou.is_set():
            primeira_travou.set()
            assert pode_comitar_a_primeira.wait(timeout=5), (
                "a segunda thread não chegou a tempo — sem a trava, ela nem precisaria esperar."
            )
        return resultado

    # O cenário é montado ANTES de instalar a barreira: o próprio cadastro das
    # contas de teste passa por `full_clean()`, e pararia na barreira (foi
    # assim que a primeira versão deste teste falhou — o R4 da DRE monta as
    # contas antes pelo mesmo motivo).
    empresa, contas, gestor, caixa, receita = _cenario("corrida")
    monkeypatch.setattr(Conta, "full_clean", full_clean_com_barreira)

    def classificar(atividade):
        conta_local = Conta.objects.get(pk=receita.pk)
        classificar_conta_na_dfc(
            conta=conta_local,
            caixa_e_equivalentes=False,
            classificacao_dfc=atividade,
            item_de_resultado_sem_caixa=False,
            usuario=gestor,
        )
        connection.close()

    t1 = threading.Thread(target=classificar, args=(ATIV,))
    t2 = threading.Thread(target=classificar, args=(INVEST,))
    t1.start()
    assert primeira_travou.wait(timeout=5), "a primeira thread não chegou à barreira a tempo"
    t2.start()
    pode_comitar_a_primeira.set()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive()
    assert not t2.is_alive()

    receita.refresh_from_db()
    assert receita.classificacao_dfc in (ATIV, INVEST)
    registros = _trilhas()
    assert len(registros) == 2, "as duas classificações registraram"
    for registro in registros:
        antes = registro.detalhes["classificacao_dfc"]["antes"]
        depois = registro.detalhes["classificacao_dfc"]["depois"]
        assert antes != depois, "o 'antes' da trilha é sempre o valor real sob a trava"
