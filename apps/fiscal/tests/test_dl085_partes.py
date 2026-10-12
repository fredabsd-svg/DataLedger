"""DL-085 (frente A), critério 4: interromper o lote no meio e repetir completa sem duplicar.

As partes são uma transação por nota. Cada teste força uma situação de falha e confere que o
lote termina certo: nenhuma escrituração órfã, nenhuma nota efetivada duas vezes, e a trilha
de cada nota igual à da efetivação individual.
"""

from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    EstadoNotaDoLoteNFe,
    ItemNFe,
    LoteEscrituracaoNFeNota,
)
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import confirmar_tudo, nfce, previa_lida, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a)


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _sete_notas(escritorio, usuario):
    for numero in range(1, 8):
        nfce(escritorio, usuario, numero=numero, valor=str(10 * numero) + ".00")


def _pendentes_em_ordem(lote_gravado):
    return list(
        lote_gravado.notas.filter(estado=EstadoNotaDoLoteNFe.PENDENTE)
        .order_by("vinculo_id", "pk")
        .values_list("vinculo_id", flat=True)
    )


def _uma_escrituracao_por_nota(empresa):
    """Cada vínculo tem no máximo uma escrituração não estornada, e nenhuma órfã (rascunho sem
    nota)."""
    ativas = EscrituracaoNFe.objects.filter(
        empresa=empresa, estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA]
    )
    return list(ativas.values_list("vinculo_id", flat=True))


def test_queda_no_meio_da_parte_e_repeticao_completa_sem_duplicar(
    escritorio_a, gestor, empresa, monkeypatch
):
    """Critério 4. A 2ª efetivação da parte cai (RuntimeError, como uma queda do processo). A nota
    que caiu não deixa rascunho para trás. Repetir até o fim efetiva as 7 notas, UMA vez cada."""
    _sete_notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=2)
    assert primeira.efetivadas_total == 2

    original = servico.efetivar
    chamadas = {"n": 0}

    def cai_na_segunda(escrituracao, usuario, request=None):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise RuntimeError("queda simulada no meio da parte")
        return original(escrituracao, usuario, request=request)

    monkeypatch.setattr(servico, "efetivar", cai_na_segunda)
    with pytest.raises(RuntimeError):
        lote.confirmar_lote(
            empresa, None, None, None, None, gestor, lote_id=primeira.lote_id, limite=3
        )
    monkeypatch.setattr(servico, "efetivar", original)

    # A parte que caiu: a 3ª nota ficou efetivada, a 4ª não deixou rascunho, e a linha continua
    # pendente. Nenhuma escrituração órfã.
    assert EscrituracaoNFe.objects.filter(empresa=empresa).count() == 3
    assert (
        EscrituracaoNFe.objects.filter(empresa=empresa)
        .exclude(estado__in=[EstadoEscrituracao.EFETIVADA])
        .count()
        == 0
    )

    progresso = confirmar_tudo(empresa, gestor, 2026, 3, previa, limite=2)

    assert progresso.terminou
    assert progresso.efetivadas_total == 7
    assert progresso.falhas_total == 0
    vinculos = _uma_escrituracao_por_nota(empresa)
    assert len(vinculos) == 7 and len(set(vinculos)) == 7
    assert (
        RegistroAuditoria.objects.filter(
            acao="escrituracao_nfe.efetivada", objeto_tipo="EscrituracaoNFe"
        ).count()
        == 7
    )


def test_a_parte_respeita_o_limite_e_informa_o_que_resta(escritorio_a, gestor, empresa):
    """Com 7 notas e limite 2: cada chamada efetiva até 2 e devolve o que resta."""
    _sete_notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    progresso = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=2)
    assert (progresso.efetivadas_nesta_chamada, progresso.restantes) == (2, 5)

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, lote_id=progresso.lote_id, limite=2
    )
    assert (progresso.efetivadas_nesta_chamada, progresso.restantes) == (2, 3)

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, lote_id=progresso.lote_id, limite=2
    )
    assert (progresso.efetivadas_nesta_chamada, progresso.restantes) == (2, 1)
    assert not progresso.terminou


def test_nota_com_desvio_desde_a_confirmacao_falha_e_as_outras_seguem(
    escritorio_a, gestor, empresa
):
    """A nota muda depois da confirmação (o item é relido, a sugestão deixa de bater): ela FALHA com
    o motivo de desvio, e as outras são efetivadas. Nada é efetivado com a natureza de uma leitura
    que o contador não viu."""
    _sete_notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=1)
    alvo = (
        LoteEscrituracaoNFeNota.objects.filter(
            lote_id=primeira.lote_id, estado=EstadoNotaDoLoteNFe.PENDENTE
        )
        .order_by("vinculo_id", "pk")
        .first()
    )
    ItemNFe.objects.filter(documento=alvo.vinculo.documento).update(cfop="5949")

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, lote_id=primeira.lote_id, limite=50
    )

    assert progresso.terminou
    assert progresso.falhas_total == 1
    assert progresso.efetivadas_total == 6
    alvo.refresh_from_db()
    assert alvo.estado == EstadoNotaDoLoteNFe.FALHOU
    assert alvo.motivo == lote.MENSAGEM_DESVIO
    assert (
        not EscrituracaoNFe.objects.filter(vinculo=alvo.vinculo)
        .exclude(estado=EstadoEscrituracao.RASCUNHO)
        .exists()
    )


def test_nota_estornada_depois_da_confirmacao_nao_e_reefetivada_pelo_lote(
    escritorio_a, gestor, empresa
):
    """O contador efetiva uma nota do lote por fora e a ESTORNA (com motivo). A parte não a
    reefetiva: ela falha com o motivo, e a decisão do estorno prevalece."""
    _sete_notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=1)
    alvo = (
        LoteEscrituracaoNFeNota.objects.filter(
            lote_id=primeira.lote_id, estado=EstadoNotaDoLoteNFe.PENDENTE
        )
        .order_by("vinculo_id", "pk")
        .first()
    )
    documento = alvo.vinculo.documento
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    servico.definir_natureza(
        esc,
        "combustivel",
        list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True)),
        usuario=gestor,
    )
    servico.efetivar(esc, usuario=gestor)
    servico.estornar(esc, "natureza errada, refazer", usuario=gestor)

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, lote_id=primeira.lote_id, limite=50
    )

    assert progresso.terminou
    alvo.refresh_from_db()
    assert alvo.estado == EstadoNotaDoLoteNFe.FALHOU
    assert alvo.motivo == lote.MENSAGEM_ESTORNADA_DEPOIS
    assert EscrituracaoNFe.objects.filter(vinculo=alvo.vinculo).count() == 1
    assert EscrituracaoNFe.objects.get(vinculo=alvo.vinculo).estado == EstadoEscrituracao.ESTORNADA


def test_nota_efetivada_por_fora_do_lote_e_pulada_sem_duplicar(escritorio_a, gestor, empresa):
    """O contador efetiva uma nota do lote pela escrituração individual. O lote a PULA (já
    efetivada)
    e não cria escrituração nova: nenhuma nota duplicada."""
    _sete_notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=1)
    alvo = (
        LoteEscrituracaoNFeNota.objects.filter(
            lote_id=primeira.lote_id, estado=EstadoNotaDoLoteNFe.PENDENTE
        )
        .order_by("vinculo_id", "pk")
        .first()
    )
    documento = alvo.vinculo.documento
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    servico.definir_natureza(
        esc,
        "combustivel",
        list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True)),
        usuario=gestor,
    )
    servico.efetivar(esc, usuario=gestor)

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, lote_id=primeira.lote_id, limite=50
    )

    assert progresso.terminou
    # 7 notas: 1 pulada (feita por fora), 6 efetivadas pelo lote (1 na primeira parte, 5 aqui).
    assert progresso.ja_efetivadas_total == 1
    assert progresso.efetivadas_total == 6
    assert EscrituracaoNFe.objects.filter(vinculo=alvo.vinculo).count() == 1
    alvo.refresh_from_db()
    assert alvo.estado == EstadoNotaDoLoteNFe.JA_EFETIVADA
    assert alvo.escrituracao_id == esc.pk


def test_repetir_a_parte_concluida_nao_processa_nem_registra_nada_novo(
    escritorio_a, gestor, empresa
):
    _sete_notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    concluido = confirmar_tudo(empresa, gestor, 2026, 3, previa, limite=3)
    antes = RegistroAuditoria.objects.count()

    repetido = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, lote_id=concluido.lote_id
    )

    assert repetido.terminou
    assert repetido.efetivadas_nesta_chamada == 0
    assert RegistroAuditoria.objects.count() == antes
    assert EscrituracaoNFe.objects.filter(empresa=empresa).count() == 7


def test_valor_das_notas_efetivadas_bate_com_a_soma_escrita_a_mao(escritorio_a, gestor, empresa):
    """Cada escrituração guarda o vNF da nota. As 7 notas valem 10 + 20 + ... + 70 = 280,00,
    escrito à
    mão. Nenhuma nota ficou de fora nem entrou duas vezes."""
    _sete_notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    confirmar_tudo(empresa, gestor, 2026, 3, previa, limite=3)

    total_vnf = sum(
        (e.valor_nf for e in EscrituracaoNFe.objects.filter(empresa=empresa)), D("0.00")
    )
    assert total_vnf == D("280.00")
