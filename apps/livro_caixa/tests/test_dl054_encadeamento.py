"""DL-054 (RC-148) — mês encerrado congelado contra o encadeamento do carnê-leão.

O carnê-leão se encadeia de janeiro a dezembro (excesso de livro-caixa,
crédito do exterior e saldo abaixo de R$ 10,00 passam de um mês para o
seguinte). Lançar ou estornar em mês M mudaria o resultado de um mês POSTERIOR
já encerrado do mesmo ano (achado E1 da auditoria da DL-053). Este arquivo
cobre o SERVIDOR (serviço + API); a tela é do `especialista-frontend`:

1. lançar/estornar em M recusado se houver mês encerrado depois, no mesmo
   ano (409, banco inalterado, mensagem nomeia o primeiro mês encerrado);
   só meses anteriores encerrados, ou mês encerrado de outro ano, aceita;
2. o cenário do E1: a apuração do mês encerrado não muda;
3. reabrir M com encerrados depois: sem cascata recusado; com cascata abre
   todos, com um motivo e um registro de trilha por mês, numa transação;
4. papéis, isolamento e motivo obrigatório na cascata, pela API;
5. concorrência com duas conexões: lançar em M x encerrar mês posterior.

Dados 100% sintéticos, datas no passado. A concorrência segue a DL-050: todo
`join` tem `timeout` e há asserção de que as threads terminaram.
"""

# ruff: noqa: F811
# (a fixture `cenario` importada é usada como parâmetro, o padrão do repositório)
import json
import re
import threading
import time
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client

from apps.auditoria.models import RegistroAuditoria
from apps.livro_caixa import services
from apps.livro_caixa.carne_leao import apurar_carne_leao_mensal
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    EstadoMesCaixa,
    FechamentoMesCaixa,
    LancamentoCaixa,
    NaturezaCaixa,
    OrigemRecebimento,
)
from apps.livro_caixa.services import (
    FechamentoMesCaixaInvalido,
    FechamentoMesCaixaRecusado,
    FechamentoMesCaixaTravado,
    MesCaixaEncerrado,
    MesCaixaOcupado,
    ReaberturaExigeCascata,
    criar_lancamento_caixa,
    encerrar_mes_caixa,
    estornar_lancamento_caixa,
    reabrir_mes_caixa,
    reabrir_mes_caixa_em_cascata,
)
from apps.livro_caixa.tests.test_dl053_fechamento_do_mes import (  # noqa: F401
    _PAUSA_CURTA,
    _PODEM_FECHAR,
    _cenario_commitado,
    _cliente_logado,
    _corpo_lancamento,
    _encerrar,
    _esperar,
    _fotografia,
    _lancar,
    _pausando,
    _rodar_em_thread,
    _segurar_lock_do_mes,
    _url,
    _usuario,
    cenario,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

_MOTIVO = "Corrigir despesa de janeiro lançada a menos"
# Identificadores internos (requisito, decisão, backlog, demanda) não podem
# aparecer em mensagem ao contador.
_IDENTIFICADOR_INTERNO = re.compile(r"\b(RC|DE|BL|DL|PE|DT)-\d+")


# A razão social sintética do cenário da DL-053 carrega "DL-053" no nome; é dado
# de teste, não identificador vazando para a mensagem.
_NOME_SINTETICO_DO_CENARIO = re.compile(r"(Fulano|Beltrano|Ciclano) DL-053")


def _sem_identificador_interno(texto):
    sem_nome_de_teste = _NOME_SINTETICO_DO_CENARIO.sub("", texto)
    assert not _IDENTIFICADOR_INTERNO.search(sem_nome_de_teste), texto


@pytest.fixture
def carne(cenario):
    """A empresa do cenário da DL-053 ganha as duas contas do cenário do E1:
    receita de trabalho (R01.001.001) e despesa dedutível do livro-caixa
    (P10.001). A vigência da tabela e da redução vem da migração."""
    empresa = cenario["empresa"]
    cenario["conta_trabalho"] = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="RT",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    cenario["conta_p10"] = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="D10",
        nome="Despesa dedutível (livro-caixa)",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P10.001",
    )
    return cenario


def _receita(c, data, valor):
    return criar_lancamento_caixa(
        empresa=c["empresa"],
        conta=c["conta_trabalho"],
        data=data,
        valor=valor,
        historico="Honorários DL-054",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento="11144477735",
        cpf_beneficiario_nao_informado=True,
        criado_por=c["gestor"],
    )


def _despesa(c, data, valor):
    return criar_lancamento_caixa(
        empresa=c["empresa"],
        conta=c["conta_p10"],
        data=data,
        valor=valor,
        historico="Despesa DL-054",
        criado_por=c["gestor"],
    )


def _encerrados_posteriores(empresa, mes, ano=2026):
    """O que a tela mostraria agora: (ano, mes) dos encerrados depois de `mes`."""
    return frozenset(
        (ano, f.mes)
        for f in FechamentoMesCaixa.objects.filter(
            empresa=empresa, ano=ano, mes__gt=mes, estado=EstadoMesCaixa.ENCERRADO
        )
    )


def _cascata(c, *, mes=1, motivo=_MOTIVO, usuario=None, empresa=None, meses_confirmados=None):
    """Reabre em cascata. DL-060: a cascata exige a lista confirmada; por padrão
    ela é a lista EXATA do momento (quem viu a tela e confirmou), e quem testa a
    divergência passa `meses_confirmados` explícito."""
    empresa = empresa or c["empresa"]
    if meses_confirmados is None:
        meses_confirmados = _encerrados_posteriores(empresa, mes)
    return reabrir_mes_caixa_em_cascata(
        empresa=empresa,
        ano=2026,
        mes=mes,
        usuario=usuario or c["gestor"],
        motivo=motivo,
        meses_confirmados=meses_confirmados,
    )


def _confirmados(*meses, ano=2026):
    """Corpo `meses_confirmados` da API (DL-060)."""
    return [{"ano": ano, "mes": mes} for mes in meses]


def _estados(empresa, ano=2026):
    return {f.mes: f.estado for f in FechamentoMesCaixa.objects.filter(empresa=empresa, ano=ano)}


def _encerrar_varios(c, meses, ano=2026):
    for mes in meses:
        _encerrar(c, ano=ano, mes=mes)


# ---------------------------------------------------------------------------
# Critérios 1 e 2 — lançar e estornar com mês posterior encerrado
# ---------------------------------------------------------------------------


def test_cenario_do_e1_lancar_em_janeiro_com_fevereiro_encerrado_e_recusado_e_a_apuracao_nao_muda(
    carne,
):
    """O caso medido pela auditoria da DL-053: sem a regra, uma despesa P10 de
    R$ 2.000,00 em janeiro baixava o imposto de fevereiro encerrado de
    R$ 1.016,27 para R$ 466,27."""
    c = carne
    _receita(c, date(2026, 1, 10), "3000.00")
    _despesa(c, date(2026, 1, 12), "5000.00")
    _receita(c, date(2026, 2, 10), "9000.00")
    _encerrar(c, mes=2)  # janeiro continua ABERTO: fechar fora de ordem é permitido

    antes = apurar_carne_leao_mensal(empresa=c["empresa"], ano=2026, mes=2)
    # Valores de referência da auditoria (conferidos à mão: excesso de janeiro
    # 5.000 - 3.000 = 2.000 deduz de fevereiro, base 9.000 - 2.000 = 7.000).
    assert antes["excesso_livro_caixa_anterior"] == Decimal("2000.00")
    assert antes["base_de_calculo"] == Decimal("7000.00")
    assert antes["imposto_devido_no_mes"] == Decimal("1016.27")
    fotografia = _fotografia(c["empresa"])

    with pytest.raises(MesCaixaEncerrado) as erro:
        _despesa(c, date(2026, 1, 20), "2000.00")

    assert "02/2026" in str(erro.value)
    assert "01/2026" in str(erro.value)
    _sem_identificador_interno(str(erro.value))
    assert _fotografia(c["empresa"]) == fotografia
    depois = apurar_carne_leao_mensal(empresa=c["empresa"], ano=2026, mes=2)
    assert depois == antes
    assert depois["imposto_devido_no_mes"] == Decimal("1016.27")


def test_depois_de_reabrir_fevereiro_o_mesmo_lancamento_e_aceito(carne):
    c = carne
    _encerrar(c, mes=2)
    with pytest.raises(MesCaixaEncerrado):
        _despesa(c, date(2026, 1, 20), "2000.00")

    reabrir_mes_caixa(empresa=c["empresa"], ano=2026, mes=2, usuario=c["gestor"], motivo=_MOTIVO)

    assert _despesa(c, date(2026, 1, 20), "2000.00").pk


def test_mensagem_nomeia_o_primeiro_mes_encerrado_alcancado(cenario):
    _encerrar_varios(cenario, [5, 3])  # fora de ordem, de propósito

    with pytest.raises(MesCaixaEncerrado) as erro:
        _lancar(cenario, date(2026, 1, 20))

    mensagem = str(erro.value)
    assert "03/2026" in mensagem
    assert "05/2026" not in mensagem
    _sem_identificador_interno(mensagem)


def test_so_meses_anteriores_encerrados_aceita_lancamento_e_estorno(cenario):
    _encerrar_varios(cenario, [1, 2])
    original = _lancar(cenario, date(2026, 3, 10))

    # Março e agosto estão abertos e nenhum mês encerrado vem depois deles.
    assert _lancar(cenario, date(2026, 3, 20)).pk
    assert _lancar(cenario, date(2026, 8, 31)).pk
    assert estornar_lancamento_caixa(original, criado_por=cenario["gestor"]).pk


def test_mes_encerrado_de_outro_ano_nao_recusa_nem_posterior_nem_anterior(cenario):
    """O encadeamento é anual: a virada do ano isola."""
    _encerrar(cenario, ano=2025, mes=12)
    _encerrar(cenario, ano=2027, mes=1)
    _encerrar(cenario, ano=2025, mes=1)
    original = _lancar(cenario, date(2026, 1, 10))

    assert _lancar(cenario, date(2026, 6, 10)).pk
    assert _lancar(cenario, date(2026, 8, 31)).pk
    assert estornar_lancamento_caixa(original, criado_por=cenario["gestor"]).pk


def test_estorno_em_mes_aberto_com_posterior_encerrado_e_recusado_sem_efeito(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, mes=2)
    fotografia = _fotografia(cenario["empresa"])

    with pytest.raises(MesCaixaEncerrado) as erro:
        estornar_lancamento_caixa(original, criado_por=cenario["gestor"])

    assert "02/2026" in str(erro.value)
    assert "estornar" in str(erro.value)
    _sem_identificador_interno(str(erro.value))
    assert _fotografia(cenario["empresa"]) == fotografia

    reabrir_mes_caixa(
        empresa=cenario["empresa"], ano=2026, mes=2, usuario=cenario["gestor"], motivo=_MOTIVO
    )
    assert estornar_lancamento_caixa(original, criado_por=cenario["gestor"]).pk


def test_a_mensagem_do_proprio_mes_encerrado_continua_a_da_regra_anterior(cenario):
    _encerrar(cenario, mes=1)
    with pytest.raises(MesCaixaEncerrado) as erro:
        _lancar(cenario, date(2026, 1, 20))
    assert "01/2026" in str(erro.value)
    assert "gravar lançamento nele" in str(erro.value)


def test_a_regra_vale_so_dentro_da_propria_empresa(cenario):
    """Fevereiro encerrado na empresa A não trava janeiro da empresa irmã."""
    _encerrar(cenario, mes=2)
    assert _lancar(
        cenario, date(2026, 1, 20), empresa=cenario["empresa_irma"], conta=cenario["conta_irma"]
    ).pk
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 20))


def test_api_lancamento_em_janeiro_com_fevereiro_encerrado_da_409_e_nao_grava(cenario):
    _encerrar(cenario, mes=2)
    fotografia = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))

    resposta = cliente.post(
        _url("lancamentos", cenario["empresa"].id),
        data=_corpo_lancamento(cenario, "2026-01-20"),
        content_type="application/json",
    )

    assert resposta.status_code == 409
    assert "02/2026" in resposta.json()["detail"]
    _sem_identificador_interno(resposta.json()["detail"])
    assert _fotografia(cenario["empresa"]) == fotografia


def test_api_estorno_em_janeiro_com_fevereiro_encerrado_da_409_e_nao_grava(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, mes=2)
    fotografia = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(_usuario(Papel.FINANCEIRO, cenario["escritorio_a"]))

    resposta = cliente.post(_url("estornar", cenario["empresa"].id, original.id))

    assert resposta.status_code == 409
    assert "02/2026" in resposta.json()["detail"]
    assert _fotografia(cenario["empresa"]) == fotografia


def test_api_lancamento_com_so_mes_anterior_encerrado_da_201(cenario):
    _encerrar(cenario, mes=1)
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))
    resposta = cliente.post(
        _url("lancamentos", cenario["empresa"].id),
        data=_corpo_lancamento(cenario, "2026-02-20"),
        content_type="application/json",
    )
    assert resposta.status_code == 201


# ---------------------------------------------------------------------------
# Critério 3 — reabrir: sem cascata recusado; em cascata reabre tudo
# ---------------------------------------------------------------------------


def test_reabrir_janeiro_com_fevereiro_e_marco_encerrados_sem_cascata_e_recusado(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    fotografia = _fotografia(cenario["empresa"])

    with pytest.raises(ReaberturaExigeCascata) as erro:
        reabrir_mes_caixa(
            empresa=cenario["empresa"],
            ano=2026,
            mes=1,
            usuario=cenario["gestor"],
            motivo=_MOTIVO,
        )

    # É uma recusa de ESTADO (409), como toda transição recusada.
    assert isinstance(erro.value, FechamentoMesCaixaRecusado)
    assert erro.value.ano == 2026
    assert erro.value.meses == (2, 3)
    mensagem = str(erro.value)
    assert "02/2026" in mensagem and "03/2026" in mensagem
    _sem_identificador_interno(mensagem)
    assert _fotografia(cenario["empresa"]) == fotografia


def test_reabrir_do_ultimo_para_o_primeiro_sem_cascata_tambem_funciona(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    for mes in (3, 2, 1):
        reabrir_mes_caixa(
            empresa=cenario["empresa"],
            ano=2026,
            mes=mes,
            usuario=cenario["gestor"],
            motivo=_MOTIVO,
        )
    assert set(_estados(cenario["empresa"]).values()) == {EstadoMesCaixa.ABERTO}


def test_reabrir_com_encerrado_so_em_outro_ano_nao_exige_cascata(cenario):
    _encerrar(cenario, ano=2026, mes=1)
    _encerrar(cenario, ano=2027, mes=6)
    _encerrar(cenario, ano=2025, mes=6)

    reabrir_mes_caixa(
        empresa=cenario["empresa"], ano=2026, mes=1, usuario=cenario["gestor"], motivo=_MOTIVO
    )

    assert _estados(cenario["empresa"], 2026)[1] == EstadoMesCaixa.ABERTO


def test_reabrir_com_posterior_so_anterior_encerrado_nao_exige_cascata(cenario):
    """Mês encerrado ANTES do reaberto não depende dele."""
    _encerrar_varios(cenario, [1, 2])
    reabrir_mes_caixa(
        empresa=cenario["empresa"], ano=2026, mes=2, usuario=cenario["gestor"], motivo=_MOTIVO
    )
    estados = _estados(cenario["empresa"])
    assert estados[1] == EstadoMesCaixa.ENCERRADO
    assert estados[2] == EstadoMesCaixa.ABERTO


def test_cascata_reabre_os_tres_com_um_motivo_e_uma_trilha_por_mes(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    _encerrar(cenario, ano=2027, mes=1)  # outro ano: não entra
    _encerrar(cenario, mes=1, empresa=cenario["empresa_irma"])  # outra empresa: não entra
    outro = _usuario(Papel.ADMINISTRADOR, cenario["escritorio_a"])

    reabertos = _cascata(cenario, usuario=outro, motivo=f"  {_MOTIVO}  ")

    assert [f.mes for f in reabertos] == [1, 2, 3]
    estados = _estados(cenario["empresa"])
    assert [estados[m] for m in (1, 2, 3)] == [EstadoMesCaixa.ABERTO] * 3
    assert _estados(cenario["empresa"], 2027)[1] == EstadoMesCaixa.ENCERRADO
    assert _estados(cenario["empresa_irma"])[1] == EstadoMesCaixa.ENCERRADO

    for linha in FechamentoMesCaixa.objects.filter(empresa=cenario["empresa"], ano=2026):
        assert linha.motivo_reabertura == _MOTIVO
        assert linha.reaberto_por == outro
        assert linha.reaberto_em is not None
    # Um instante só para o ato inteiro.
    assert len({f.reaberto_em for f in reabertos}) == 1

    trilha = list(
        RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").order_by("id")
    )
    assert len(trilha) == 3
    assert [r.detalhes["mes"] for r in trilha] == [1, 2, 3]
    for registro in trilha:
        assert registro.usuario == outro
        assert registro.escritorio == cenario["escritorio_a"]
        assert registro.detalhes["motivo"] == _MOTIVO
        assert registro.detalhes["cascata"] is True
        assert registro.detalhes["mes_de_origem"] == 1
        assert registro.detalhes["ano"] == 2026
        assert registro.detalhes["empresa_id"] == cenario["empresa"].id
        assert registro.detalhes["fechado_por_anterior"] == cenario["gestor"].id
        assert registro.detalhes["fechado_em_anterior"]


def test_reabertura_simples_nao_marca_a_trilha_como_cascata(cenario):
    _encerrar(cenario, mes=1)
    reabrir_mes_caixa(
        empresa=cenario["empresa"], ano=2026, mes=1, usuario=cenario["gestor"], motivo=_MOTIVO
    )
    registro = RegistroAuditoria.objects.get(acao="fechamento_mes_caixa.reaberto")
    assert "cascata" not in registro.detalhes
    assert "mes_de_origem" not in registro.detalhes


def test_depois_da_cascata_lancar_em_janeiro_e_aceito(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 20))
    _cascata(cenario)
    assert _lancar(cenario, date(2026, 1, 20)).pk


def test_cascata_a_partir_de_fevereiro_nao_toca_janeiro_encerrado(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    reabertos = _cascata(cenario, mes=2)
    assert [f.mes for f in reabertos] == [2, 3]
    estados = _estados(cenario["empresa"])
    assert estados[1] == EstadoMesCaixa.ENCERRADO
    assert estados[2] == estados[3] == EstadoMesCaixa.ABERTO


def test_cascata_so_reabre_os_encerrados_e_deixa_os_abertos_como_estao(cenario):
    _encerrar_varios(cenario, [1, 4])  # fevereiro e março nunca foram fechados
    reabertos = _cascata(cenario)
    assert [f.mes for f in reabertos] == [1, 4]
    assert not FechamentoMesCaixa.objects.filter(
        empresa=cenario["empresa"], ano=2026, mes__in=[2, 3]
    ).exists()
    assert RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").count() == 2


def test_cascata_sem_posteriores_encerrados_reabre_so_o_mes(cenario):
    _encerrar(cenario, mes=1)
    reabertos = _cascata(cenario)
    assert [f.mes for f in reabertos] == [1]
    assert RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").count() == 1


def test_cascata_de_mes_aberto_e_recusada_mesmo_com_posteriores_encerrados(cenario):
    _encerrar(cenario, mes=3)
    fotografia = _fotografia(cenario["empresa"])
    with pytest.raises(FechamentoMesCaixaRecusado) as erro:
        _cascata(cenario, mes=1)
    assert not isinstance(erro.value, ReaberturaExigeCascata)
    assert _fotografia(cenario["empresa"]) == fotografia


def test_cascata_com_a_trilha_falhando_no_terceiro_mes_nao_muda_nada(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    fotografia = _fotografia(cenario["empresa"])
    original = services.registrar
    chamadas = []

    def _registrar_que_falha_no_terceiro(*args, **kwargs):
        chamadas.append(kwargs["detalhes"]["mes"])
        if len(chamadas) == 3:
            raise RuntimeError("trilha indisponível")
        return original(*args, **kwargs)

    with mock.patch.object(services, "registrar", _registrar_que_falha_no_terceiro):
        with pytest.raises(RuntimeError):
            _cascata(cenario)

    assert chamadas == [1, 2, 3]  # as duas primeiras chegaram a gravar dentro da transação
    assert _fotografia(cenario["empresa"]) == fotografia
    assert set(_estados(cenario["empresa"]).values()) == {EstadoMesCaixa.ENCERRADO}
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 20))


@pytest.mark.parametrize("motivo", [None, "", "   ", "\n\t", "a\x00b", "x" * 1001, 42])
def test_cascata_exige_motivo_valido_e_nao_muda_nada_quando_recusada(cenario, motivo):
    _encerrar_varios(cenario, [1, 2])
    fotografia = _fotografia(cenario["empresa"])
    with pytest.raises(FechamentoMesCaixaInvalido):
        _cascata(cenario, motivo=motivo)
    assert _fotografia(cenario["empresa"]) == fotografia


def test_cascata_de_empresa_em_modo_contabilidade_e_recusada(cenario):
    with pytest.raises(FechamentoMesCaixaInvalido):
        _cascata(cenario, empresa=cenario["empresa_contabilidade"])
    assert not FechamentoMesCaixa.objects.exists()


def test_cascata_sem_usuario_e_recusada_sem_efeito(cenario):
    _encerrar_varios(cenario, [1, 2])
    fotografia = _fotografia(cenario["empresa"])
    with pytest.raises(FechamentoMesCaixaInvalido):
        reabrir_mes_caixa_em_cascata(
            empresa=cenario["empresa"],
            ano=2026,
            mes=1,
            usuario=None,
            motivo=_MOTIVO,
            meses_confirmados={(2026, 2)},
        )
    assert _fotografia(cenario["empresa"]) == fotografia


def test_reencerrar_depois_da_cascata_funciona_e_guarda_a_reabertura(cenario):
    _encerrar_varios(cenario, [1, 2])
    _cascata(cenario)
    _encerrar_varios(cenario, [1, 2])
    estados = _estados(cenario["empresa"])
    assert estados[1] == estados[2] == EstadoMesCaixa.ENCERRADO
    assert FechamentoMesCaixa.objects.get(empresa=cenario["empresa"], mes=2).motivo_reabertura == (
        _MOTIVO
    )


# ---------------------------------------------------------------------------
# Critério 4 — pela API: contrato, papéis, isolamento, motivo
# ---------------------------------------------------------------------------


def _reabrir_api(cliente, empresa_id, corpo, mes=1, ano=2026):
    return cliente.post(
        _url("reabrir-mes", empresa_id, ano, mes),
        data=json.dumps(corpo),
        content_type="application/json",
    )


def test_api_sem_cascata_da_409_com_a_lista_dos_meses_e_nao_muda_nada(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    fotografia = _fotografia(cenario["empresa"])
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))

    for corpo in ({"motivo": _MOTIVO}, {"motivo": _MOTIVO, "cascata": False}):
        resposta = _reabrir_api(gestor, cenario["empresa"].id, corpo)
        assert resposta.status_code == 409, resposta.content
        dados = resposta.json()
        assert dados["meses_encerrados_posteriores"] == [
            {"ano": 2026, "mes": 2},
            {"ano": 2026, "mes": 3},
        ]
        assert "02/2026" in dados["detail"] and "03/2026" in dados["detail"]
        _sem_identificador_interno(dados["detail"])
    assert _fotografia(cenario["empresa"]) == fotografia


def test_api_com_cascata_reabre_tudo_e_devolve_o_contrato(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    usuario = _usuario(Papel.ADMINISTRADOR, cenario["escritorio_a"])
    cliente = _cliente_logado(usuario)

    resposta = _reabrir_api(
        cliente,
        cenario["empresa"].id,
        {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": _confirmados(2, 3)},
    )

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    # O corpo continua sendo o estado do mês pedido (compatível com a reabertura
    # simples) e ganha a lista de todos os meses reabertos, em ordem crescente.
    assert corpo["mes"] == 1 and corpo["ano"] == 2026
    assert corpo["estado"] == "aberto"
    assert corpo["motivo_reabertura"] == _MOTIVO
    assert corpo["reaberto_por"] == usuario.id
    assert [m["mes"] for m in corpo["meses_reabertos"]] == [1, 2, 3]
    for mes in corpo["meses_reabertos"]:
        assert mes["estado"] == "aberto"
        assert mes["motivo_reabertura"] == _MOTIVO
        assert mes["reaberto_por"] == usuario.id
    assert (
        RegistroAuditoria.objects.filter(
            acao="fechamento_mes_caixa.reaberto", usuario=usuario
        ).count()
        == 3
    )
    assert set(_estados(cenario["empresa"]).values()) == {EstadoMesCaixa.ABERTO}


def test_api_reabertura_simples_devolve_uma_lista_de_um_mes(cenario):
    _encerrar(cenario, mes=1)
    cliente = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    resposta = _reabrir_api(cliente, cenario["empresa"].id, {"motivo": _MOTIVO})
    assert resposta.status_code == 200
    assert [m["mes"] for m in resposta.json()["meses_reabertos"]] == [1]


@pytest.mark.parametrize("papel", Papel.values)
def test_api_cascata_por_papel_e_banco_inalterado_quando_negado(cenario, papel):
    _encerrar_varios(cenario, [1, 2, 3])
    usuario = _usuario(papel, cenario["escritorio_a"])
    cliente = _cliente_logado(usuario)
    fotografia = _fotografia(cenario["empresa"])

    resposta = _reabrir_api(
        cliente,
        cenario["empresa"].id,
        {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": _confirmados(2, 3)},
    )

    if papel in _PODEM_FECHAR:
        assert resposta.status_code == 200, resposta.content
        assert set(_estados(cenario["empresa"]).values()) == {EstadoMesCaixa.ABERTO}
        assert (
            RegistroAuditoria.objects.filter(
                acao="fechamento_mes_caixa.reaberto", usuario=usuario
            ).count()
            == 3
        )
    else:
        assert resposta.status_code == 403
        assert _fotografia(cenario["empresa"]) == fotografia
        assert set(_estados(cenario["empresa"]).values()) == {EstadoMesCaixa.ENCERRADO}


def test_api_cascata_sem_login_e_recusada(cenario):
    _encerrar_varios(cenario, [1, 2])
    fotografia = _fotografia(cenario["empresa"])
    anonimo = Client(raise_request_exception=False)
    resposta = _reabrir_api(
        anonimo,
        cenario["empresa"].id,
        {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": _confirmados(2)},
    )
    assert resposta.status_code in (401, 403)
    assert _fotografia(cenario["empresa"]) == fotografia


def test_api_cascata_de_outro_escritorio_da_404_e_nao_muda_nada(cenario):
    _encerrar_varios(cenario, [1, 2, 3])
    fotografia = _fotografia(cenario["empresa"])
    intruso = _cliente_logado(_usuario(Papel.ADMINISTRADOR, cenario["escritorio_b"]))

    resposta = _reabrir_api(
        intruso,
        cenario["empresa"].id,
        {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": _confirmados(2, 3)},
    )

    assert resposta.status_code == 404
    assert "02/2026" not in resposta.content.decode()
    assert _fotografia(cenario["empresa"]) == fotografia


def test_api_cascata_de_uma_empresa_nao_reabre_a_irma_do_mesmo_escritorio(cenario):
    _encerrar_varios(cenario, [1, 2])
    _encerrar(cenario, mes=1, empresa=cenario["empresa_irma"])
    _encerrar(cenario, mes=2, empresa=cenario["empresa_irma"])
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))

    resposta = _reabrir_api(
        gestor,
        cenario["empresa"].id,
        {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": _confirmados(2)},
    )

    assert resposta.status_code == 200
    assert set(_estados(cenario["empresa_irma"]).values()) == {EstadoMesCaixa.ENCERRADO}
    assert set(_estados(cenario["empresa"]).values()) == {EstadoMesCaixa.ABERTO}


def test_api_cascata_de_empresa_em_modo_contabilidade_da_400(cenario):
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    resposta = _reabrir_api(
        gestor,
        cenario["empresa_contabilidade"].id,
        {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": []},
    )
    assert resposta.status_code == 400
    assert not FechamentoMesCaixa.objects.exists()


@pytest.mark.parametrize(
    "corpo",
    [
        {"meses_confirmados": _confirmados(2, 3), "cascata": True},
        {"meses_confirmados": _confirmados(2, 3), "cascata": True, "motivo": ""},
        {"meses_confirmados": _confirmados(2, 3), "cascata": True, "motivo": "   "},
        {"meses_confirmados": _confirmados(2, 3), "cascata": True, "motivo": None},
        {"meses_confirmados": _confirmados(2, 3), "cascata": True, "motivo": ["a"]},
        {"meses_confirmados": _confirmados(2, 3), "cascata": True, "motivo": "x" * 1001},
        {"meses_confirmados": _confirmados(2, 3), "cascata": True, "motivo": "a\x00b"},
    ],
)
def test_api_cascata_sem_motivo_valido_da_400_e_nao_muda_nada(cenario, corpo):
    _encerrar_varios(cenario, [1, 2, 3])
    fotografia = _fotografia(cenario["empresa"])
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))

    resposta = _reabrir_api(gestor, cenario["empresa"].id, corpo)

    assert resposta.status_code == 400, corpo
    assert _fotografia(cenario["empresa"]) == fotografia


@pytest.mark.parametrize("cascata", ["true", "sim", 1, 0, None, [], {}, "false"])
def test_api_cascata_que_nao_e_booleano_da_400_e_nao_muda_nada(cenario, cascata):
    """Reabrir vários meses encerrados não pode nascer de coerção de tipo."""
    _encerrar_varios(cenario, [1, 2, 3])
    fotografia = _fotografia(cenario["empresa"])
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))

    resposta = _reabrir_api(gestor, cenario["empresa"].id, {"motivo": _MOTIVO, "cascata": cascata})

    assert resposta.status_code == 400
    assert _fotografia(cenario["empresa"]) == fotografia


def test_api_continua_recusando_campo_nao_contratado_junto_com_cascata(cenario):
    _encerrar_varios(cenario, [1, 2])
    fotografia = _fotografia(cenario["empresa"])
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))

    resposta = _reabrir_api(
        gestor,
        cenario["empresa"].id,
        {
            "motivo": _MOTIVO,
            "cascata": True,
            "meses_confirmados": _confirmados(2),
            "meses": [1, 2, 3, 4],
        },
    )

    assert resposta.status_code == 400
    assert _fotografia(cenario["empresa"]) == fotografia


def test_api_cascata_de_mes_aberto_da_409_sem_lista_de_posteriores(cenario):
    _encerrar(cenario, mes=3)
    fotografia = _fotografia(cenario["empresa"])
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))

    resposta = _reabrir_api(
        gestor,
        cenario["empresa"].id,
        {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": _confirmados(3)},
    )

    assert resposta.status_code == 409
    assert "meses_encerrados_posteriores" not in resposta.json()
    assert _fotografia(cenario["empresa"]) == fotografia


# ---------------------------------------------------------------------------
# Locks — ordem crescente, alcance e estouro
# ---------------------------------------------------------------------------


def _registrando_os_locks_de_mes():
    """Envolve `_adquirir_lock_do_mes` para registrar (mês, exclusivo) na ordem
    em que são pedidos, sem trocar o comportamento real."""
    pedidos = []
    original = services._adquirir_lock_do_mes

    def _registrador(**kwargs):
        pedidos.append((kwargs["ano"], kwargs["mes"], kwargs["exclusivo"]))
        return original(**kwargs)

    return pedidos, mock.patch.object(services, "_adquirir_lock_do_mes", _registrador)


def test_lancamento_toma_o_lock_compartilhado_do_mes_e_dos_posteriores_em_ordem_crescente(cenario):
    pedidos, patch = _registrando_os_locks_de_mes()
    with patch:
        _lancar(cenario, date(2026, 10, 5))
    assert pedidos == [(2026, 10, False), (2026, 11, False), (2026, 12, False)]


def test_lancamento_em_janeiro_trava_os_doze_meses_do_ano_e_so_ele(cenario):
    pedidos, patch = _registrando_os_locks_de_mes()
    with patch:
        _lancar(cenario, date(2026, 1, 5))
    assert pedidos == [(2026, mes, False) for mes in range(1, 13)]


def test_reabertura_toma_o_lock_exclusivo_do_mes_e_dos_posteriores_em_ordem_crescente(cenario):
    _encerrar_varios(cenario, [3, 4])
    pedidos, patch = _registrando_os_locks_de_mes()
    with patch:
        _cascata(cenario, mes=3)
    assert pedidos == [(2026, mes, True) for mes in range(3, 13)]

    _encerrar_varios(cenario, [3])
    pedidos.clear()
    with patch:
        reabrir_mes_caixa(
            empresa=cenario["empresa"], ano=2026, mes=3, usuario=cenario["gestor"], motivo=_MOTIVO
        )
    assert pedidos == [(2026, mes, True) for mes in range(3, 13)]


@pytest.mark.django_db(transaction=True)
def test_espera_por_mes_posterior_que_estoura_o_lock_timeout_vira_409_e_nao_grava_nada():
    """Lançar em janeiro espera o lock de MARÇO (posterior) e estoura: 409 de
    domínio, nada gravado — nunca 500."""
    c = _cenario_commitado()
    preso, liberar = threading.Event(), threading.Event()
    segurando, res_segurando = _segurar_lock_do_mes(c["empresa"].id, 2026, 3, preso, liberar)
    try:
        assert preso.wait(timeout=30)
        with pytest.raises(MesCaixaOcupado) as ocupado:
            criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 1, 10),
                valor="10.00",
                historico="Espera por mês posterior",
                recebido_de="PJ",
            )
        assert "Tente novamente" in str(ocupado.value)
        with pytest.raises(FechamentoMesCaixaTravado):
            reabrir_mes_caixa_em_cascata(
                empresa=c["empresa"],
                ano=2026,
                mes=1,
                usuario=c["gestor"],
                motivo=_MOTIVO,
                meses_confirmados=frozenset(),
            )
    finally:
        liberar.set()
        _esperar(segurando)
    assert "erro" not in res_segurando, res_segurando
    assert not LancamentoCaixa.objects.filter(empresa=c["empresa"]).exists()
    assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).exists()


# ---------------------------------------------------------------------------
# Critério 5 — concorrência com duas conexões (transaction=True)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_lancamento_em_janeiro_em_andamento_faz_o_fechamento_de_fevereiro_esperar():
    """O lançamento chegou primeiro e segura o lock compartilhado de fevereiro.
    O fechamento de fevereiro espera e, ao entrar, encerra o mês JÁ com o
    lançamento de janeiro dentro — ordem legítima."""
    c = _cenario_commitado()

    with _pausando("lancamento_caixa.criado") as (dentro, liberar):
        lancar, res_lancar = _rodar_em_thread(
            lambda: criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 1, 20),
                valor="10.00",
                historico="Janeiro em voo",
                recebido_de="PJ",
            )
        )
        assert dentro.wait(timeout=30), "lançamento nunca chegou à pausa"

        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=2, usuario=c["gestor"])
        )
        time.sleep(_PAUSA_CURTA)
        assert fechar.is_alive(), "o fechamento de fevereiro não esperou o lançamento de janeiro"
        assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).exists()

        liberar.set()
        _esperar(lancar, fechar)

    assert "erro" not in res_lancar, res_lancar
    assert "erro" not in res_fechar, res_fechar
    assert LancamentoCaixa.objects.filter(empresa=c["empresa"]).count() == 1
    assert FechamentoMesCaixa.objects.get(empresa=c["empresa"], mes=2).estado == (
        EstadoMesCaixa.ENCERRADO
    )


@pytest.mark.django_db(transaction=True)
def test_fechamento_de_fevereiro_em_andamento_faz_o_lancamento_de_janeiro_esperar_e_ser_recusado():
    """O inverso, partindo de fevereiro SEM registro: o fechamento chegou
    primeiro. O lançamento de janeiro espera; ao entrar vê fevereiro encerrado
    e é recusado — fevereiro nunca termina encerrado e alterado."""
    c = _cenario_commitado()

    with _pausando("fechamento_mes_caixa.encerrado") as (dentro, liberar):
        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=2, usuario=c["gestor"])
        )
        assert dentro.wait(timeout=30), "fechamento nunca chegou à pausa"

        lancar, res_lancar = _rodar_em_thread(
            lambda: criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 1, 20),
                valor="10.00",
                historico="Janeiro depois do fechamento de fevereiro",
                recebido_de="PJ",
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert lancar.is_alive(), "o lançamento de janeiro não esperou o fechamento de fevereiro"
        assert not LancamentoCaixa.objects.filter(empresa=c["empresa"]).exists()

        liberar.set()
        _esperar(fechar, lancar)

    assert "erro" not in res_fechar, res_fechar
    assert isinstance(res_lancar.get("erro"), MesCaixaEncerrado), res_lancar
    assert "02/2026" in str(res_lancar["erro"])
    assert not LancamentoCaixa.objects.filter(empresa=c["empresa"]).exists()
    assert FechamentoMesCaixa.objects.get(empresa=c["empresa"], mes=2).estado == (
        EstadoMesCaixa.ENCERRADO
    )


@pytest.mark.django_db(transaction=True)
def test_corrida_repetida_de_lancar_em_m_e_encerrar_o_mes_seguinte_nunca_fura_a_trava():
    """Onze corridas sem pausa artificial (lançar em m x encerrar m+1). O que
    identifica a violação: o fechamento, já com o lock do mês, conta os
    lançamentos do mês ANTERIOR; o total final tem de ser IGUAL a essa
    contagem. Se fosse maior, um lançamento teria comitado DEPOIS de o mês
    seguinte ser encerrado — mês posterior encerrado e alterado."""
    c = _cenario_commitado()
    original_registrar = services.registrar
    visto_pelo_fechamento = {}

    def _registrar(*args, **kwargs):
        if kwargs.get("acao") == "fechamento_mes_caixa.encerrado":
            mes = kwargs["detalhes"]["mes"]
            visto_pelo_fechamento[mes - 1] = LancamentoCaixa.objects.filter(
                empresa=c["empresa"], data__year=2025, data__month=mes - 1
            ).count()
        return original_registrar(*args, **kwargs)

    with mock.patch.object(services, "registrar", _registrar):
        for mes in range(1, 12):
            barreira = threading.Barrier(2)

            def _lancar_em_m(mes=mes, barreira=barreira):
                barreira.wait(timeout=30)
                return criar_lancamento_caixa(
                    empresa=c["empresa"],
                    conta=c["conta"],
                    data=date(2025, mes, 15),
                    valor="10.00",
                    historico=f"Corrida do mês {mes}",
                    recebido_de="PJ",
                )

            def _fechar_seguinte(mes=mes, barreira=barreira):
                barreira.wait(timeout=30)
                return encerrar_mes_caixa(
                    empresa=c["empresa"], ano=2025, mes=mes + 1, usuario=c["gestor"]
                )

            tl, rl = _rodar_em_thread(_lancar_em_m)
            tf, rf = _rodar_em_thread(_fechar_seguinte)
            _esperar(tl, tf)

            assert "erro" not in rf, (mes, rf)
            assert "erro" not in rl or isinstance(rl["erro"], MesCaixaEncerrado), (mes, rl)
            final = LancamentoCaixa.objects.filter(
                empresa=c["empresa"], data__year=2025, data__month=mes
            ).count()
            assert final == visto_pelo_fechamento[mes], (mes, final, visto_pelo_fechamento)
            assert final == (0 if "erro" in rl else 1), (mes, rl)


@pytest.mark.django_db(transaction=True)
def test_cascata_em_andamento_faz_o_lancamento_em_janeiro_esperar_e_depois_ser_aceito():
    c = _cenario_commitado()
    for mes in (1, 2, 3):
        encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=mes, usuario=c["gestor"])

    with _pausando("fechamento_mes_caixa.reaberto") as (dentro, liberar):
        reabrir, res_reabrir = _rodar_em_thread(
            lambda: reabrir_mes_caixa_em_cascata(
                empresa=c["empresa"],
                ano=2026,
                mes=1,
                usuario=c["gestor"],
                motivo=_MOTIVO,
                meses_confirmados={(2026, 2), (2026, 3)},
            )
        )
        assert dentro.wait(timeout=30)
        lancar, res_lancar = _rodar_em_thread(
            lambda: criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 1, 20),
                valor="10.00",
                historico="Depois da cascata",
                recebido_de="PJ",
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert lancar.is_alive(), "o lançamento não esperou a cascata em andamento"
        liberar.set()
        _esperar(reabrir, lancar)

    assert "erro" not in res_reabrir, res_reabrir
    assert "erro" not in res_lancar, res_lancar
    assert LancamentoCaixa.objects.filter(empresa=c["empresa"]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_duas_cascatas_e_um_fechamento_simultaneos_terminam_sem_deadlock():
    """A ordem crescente dos locks é o que impede o deadlock: duas cascatas
    (janeiro e março) e um encerramento de fevereiro ao mesmo tempo. A janela
    de intercalação é de microssegundos, então este teste só prova a ausência
    de deadlock e de estouro de lock; o ESTADO FINAL é afirmado, sem depender
    de sorte, em `test_duas_cascatas_com_fevereiro_pausado_terminam_em_estado_unico`."""
    c = _cenario_commitado()
    for mes in (1, 3, 5):
        encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=mes, usuario=c["gestor"])
    barreira = threading.Barrier(3)

    def _cascata_de(mes, confirmados):
        def _corpo():
            barreira.wait(timeout=30)
            return reabrir_mes_caixa_em_cascata(
                empresa=c["empresa"],
                ano=2026,
                mes=mes,
                usuario=c["gestor"],
                motivo=_MOTIVO,
                meses_confirmados=confirmados,
            )

        return _corpo

    def _fechar_fevereiro():
        barreira.wait(timeout=30)
        return encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=2, usuario=c["gestor"])

    t1, r1 = _rodar_em_thread(_cascata_de(1, {(2026, 3), (2026, 5)}))
    t2, r2 = _rodar_em_thread(_cascata_de(3, {(2026, 5)}))
    t3, r3 = _rodar_em_thread(_fechar_fevereiro)
    _esperar(t1, t2, t3)

    for resultado in (r1, r2, r3):
        erro = resultado.get("erro")
        # Só recusa de estado é aceitável (mês já reaberto pela outra cascata);
        # deadlock ou estouro de lock não.
        assert erro is None or isinstance(erro, FechamentoMesCaixaRecusado), resultado
        assert not isinstance(erro, FechamentoMesCaixaTravado), resultado


@pytest.mark.django_db(transaction=True)
def test_reabrir_simples_em_andamento_faz_o_encerramento_posterior_esperar():
    """H2 da auditoria da DL-054: a reabertura SIMPLES de janeiro (março ainda
    sem registro) segura o lock exclusivo de janeiro a dezembro. O encerramento
    de março, que chega durante a reabertura, espera esse lock e só então
    encerra: nunca há março encerrado "por baixo" de uma reabertura que já
    decidiu que não havia posteriores."""
    c = _cenario_commitado()
    encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"])

    with _pausando("fechamento_mes_caixa.reaberto") as (dentro, liberar):
        reabrir, res_reabrir = _rodar_em_thread(
            lambda: reabrir_mes_caixa(
                empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"], motivo=_MOTIVO
            )
        )
        assert dentro.wait(timeout=30), "a reabertura nunca chegou à pausa"

        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"])
        )
        time.sleep(_PAUSA_CURTA)
        assert fechar.is_alive(), "o encerramento de março não esperou a reabertura de janeiro"
        assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"], mes=3).exists()

        liberar.set()
        _esperar(reabrir, fechar)

    assert "erro" not in res_reabrir, res_reabrir
    assert "erro" not in res_fechar, res_fechar
    assert _estados(c["empresa"]) == {1: EstadoMesCaixa.ABERTO, 3: EstadoMesCaixa.ENCERRADO}


@pytest.mark.django_db(transaction=True)
def test_encerramento_posterior_em_andamento_faz_a_reabertura_simples_ser_recusada():
    """H2, o inverso: o encerramento de março chegou primeiro e segura o lock
    de março. A reabertura simples de janeiro espera esse lock e, ao entrar,
    LÊ março encerrado: é recusada com `ReaberturaExigeCascata` e janeiro
    continua encerrado. Sem o lock dos posteriores ela leria "sem posteriores"
    antes do commit de março e reabriria janeiro por baixo de março."""
    c = _cenario_commitado()
    encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"])

    with _pausando("fechamento_mes_caixa.encerrado") as (dentro, liberar):
        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"])
        )
        assert dentro.wait(timeout=30), "o encerramento de março nunca chegou à pausa"

        reabrir, res_reabrir = _rodar_em_thread(
            lambda: reabrir_mes_caixa(
                empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"], motivo=_MOTIVO
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert reabrir.is_alive(), "a reabertura de janeiro não esperou o encerramento de março"
        assert _estados(c["empresa"]) == {1: EstadoMesCaixa.ENCERRADO}

        liberar.set()
        _esperar(fechar, reabrir)

    assert "erro" not in res_fechar, res_fechar
    assert isinstance(res_reabrir.get("erro"), ReaberturaExigeCascata), res_reabrir
    assert res_reabrir["erro"].meses == (3,)
    assert _estados(c["empresa"]) == {1: EstadoMesCaixa.ENCERRADO, 3: EstadoMesCaixa.ENCERRADO}
    assert not RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").exists()


@pytest.mark.django_db(transaction=True)
def test_duas_cascatas_com_fevereiro_pausado_terminam_em_estado_unico():
    """Estado final determinístico (L2 da auditoria da DL-060). O encerramento
    de fevereiro é pausado com o lock de fevereiro na mão; a cascata de janeiro
    (que travou janeiro e espera fevereiro) fica presa; a de março, que não
    depende de fevereiro, termina ENQUANTO as outras duas esperam (`_esperar(b)`
    é a âncora: o `join` com timeout falha se ela ficar presa). Liberado o
    fechamento, a cascata de janeiro lê fevereiro encerrado, vê a lista
    confirmada ({março, maio}) diferente da atual ({fevereiro}) e é recusada.
    O desfecho é um só, sem sorte de escalonamento."""
    c = _cenario_commitado()
    for mes in (1, 3, 5):
        encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=mes, usuario=c["gestor"])

    with _pausando("fechamento_mes_caixa.encerrado") as (dentro, liberar):
        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=2, usuario=c["gestor"])
        )
        assert dentro.wait(timeout=30), "o encerramento de fevereiro nunca chegou à pausa"
        cascata_a, res_a = _rodar_em_thread(
            lambda: reabrir_mes_caixa_em_cascata(
                empresa=c["empresa"],
                ano=2026,
                mes=1,
                usuario=c["gestor"],
                motivo=_MOTIVO,
                meses_confirmados={(2026, 3), (2026, 5)},
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert cascata_a.is_alive(), "a cascata de janeiro deveria esperar o lock de fevereiro"
        cascata_b, res_b = _rodar_em_thread(
            lambda: reabrir_mes_caixa_em_cascata(
                empresa=c["empresa"],
                ano=2026,
                mes=3,
                usuario=c["gestor"],
                motivo=_MOTIVO,
                meses_confirmados={(2026, 5)},
            )
        )
        _esperar(cascata_b)  # termina enquanto fevereiro e janeiro esperam
        assert cascata_a.is_alive() and fechar.is_alive()
        liberar.set()
        _esperar(fechar, cascata_a)

    assert "erro" not in res_fechar, res_fechar
    assert "erro" not in res_b, res_b
    assert isinstance(res_a.get("erro"), ReaberturaExigeCascata), res_a
    assert res_a["erro"].meses == (2,)
    assert _estados(c["empresa"]) == {
        1: EstadoMesCaixa.ENCERRADO,
        2: EstadoMesCaixa.ENCERRADO,
        3: EstadoMesCaixa.ABERTO,
        5: EstadoMesCaixa.ABERTO,
    }
    trilha = RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto")
    assert sorted(r.detalhes["mes"] for r in trilha) == [3, 5]
