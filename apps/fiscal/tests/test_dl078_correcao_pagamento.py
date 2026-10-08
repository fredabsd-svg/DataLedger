"""DL-078, correção da auditoria rodada 1, achado A1 (HI-98): janela da data de pagamento.

Regras testadas, nas três portas (serviço, API e tela):
- data de pagamento só entre `data_emissao − 366 dias` e hoje; a recusa NOMEIA a janela;
- data ANTES da emissão é aceita e gera aviso de adiantamento nas retenções federais;
- a data pode ser LIMPA, com motivo e trilha; a retenção volta a "pendente";
- limpar sem motivo, ou nota não efetivada, é recusado; o banco continua recusando o resto.

Relógio fixo: `DIA_DE_HOJE_NO_TESTE` (15/12/2026). Emissão padrão do XML sintético: 05/10/2026,
então
a janela aceita vai de 04/10/2025 a 15/12/2026. Sintéticos, sem dado real.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import tomadas as servico
from apps.fiscal.escrituracao import EntradaInvalidaEscrituracao, EscrituracaoErro
from apps.fiscal.models import EscrituracaoTomada, EstadoEscrituracao
from apps.fiscal.retencoes import retencoes_federais
from apps.fiscal.tests.suporte_tomada_dl078 import (
    DIA_DE_HOJE_NO_TESTE,
    T1,
    T2,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("relogio_do_teste")]

INICIO_DA_JANELA = date(2025, 10, 4)  # emissão 05/10/2026 − 366 dias
AMANHA = DIA_DE_HOJE_NO_TESTE + timedelta(days=1)
FORA_DA_JANELA = [
    date(1, 1, 1),
    date(1900, 1, 1),
    date(2062, 10, 10),
    date(9999, 12, 31),
    AMANHA,
]
ACAO_INFORMAR = "escrituracao_tomada.data_pagamento_informada"
ACAO_LIMPAR = "escrituracao_tomada.data_pagamento_limpa"


def _br(dia: date) -> str:
    """dd/mm/aaaa, com ano de 4 dígitos (o formulário da tela digita assim)."""
    return f"{dia.day:02d}/{dia.month:02d}/{dia.year:04d}"


def _trilha(acao):
    return list(RegistroAuditoria.objects.filter(acao=acao).order_by("id"))


@pytest.fixture
def nota(escritorio_a, usuario_gestor_a, empresa_a2):
    """Nota T1 efetivada, emitida em 05/10/2026, com IRRF e ISS retido."""
    escrituracao = tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8101,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_ret_irrf="15.00",
        d_compet="2026-10-05",
    )
    assert escrituracao.data_emissao == date(2026, 10, 5)
    return escrituracao


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dia", FORA_DA_JANELA, ids=lambda d: d.isoformat())
def test_servico_recusa_data_fora_da_janela_e_nomeia_a_janela(nota, usuario_gestor_a, dia):
    with pytest.raises(EntradaInvalidaEscrituracao) as excinfo:
        servico.informar_data_pagamento(nota, dia, "Digitação sintética", usuario_gestor_a)

    mensagem = excinfo.value.mensagem
    assert "fora da janela aceita" in mensagem
    assert "de 04/10/2025" in mensagem
    assert "366 dias antes da emissão" in mensagem
    assert "até 15/12/2026 (hoje)" in mensagem
    nota.refresh_from_db()
    assert nota.data_pagamento is None
    assert _trilha(ACAO_INFORMAR) == []


def test_limites_da_janela_sao_aceitos_e_um_dia_antes_do_inicio_e_recusado(nota, usuario_gestor_a):
    assert nota.data_emissao - timedelta(days=366) == INICIO_DA_JANELA

    with pytest.raises(EntradaInvalidaEscrituracao, match="fora da janela aceita"):
        servico.informar_data_pagamento(
            nota, INICIO_DA_JANELA - timedelta(days=1), "Um dia antes", usuario_gestor_a
        )

    servico.informar_data_pagamento(nota, INICIO_DA_JANELA, "Limite inferior", usuario_gestor_a)
    nota.refresh_from_db()
    assert nota.data_pagamento == INICIO_DA_JANELA

    servico.informar_data_pagamento(nota, DIA_DE_HOJE_NO_TESTE, "Limite superior", usuario_gestor_a)
    nota.refresh_from_db()
    assert nota.data_pagamento == DIA_DE_HOJE_NO_TESTE


def test_data_antes_da_emissao_e_aceita_e_gera_aviso_nas_retencoes(
    nota, usuario_gestor_a, empresa_a2
):
    servico.informar_data_pagamento(
        nota, date(2026, 10, 1), "Adiantamento sintético", usuario_gestor_a
    )

    nota.refresh_from_db()
    assert nota.data_pagamento == date(2026, 10, 1)
    avisos = [
        aviso
        for escrituracao, aviso in retencoes_federais(empresa_a2, 2026, 10).avisos
        if aviso.codigo == "PAGAMENTO_ANTES_DA_EMISSAO"
    ]
    assert len(avisos) == 1
    assert "pagamento anterior à emissão (adiantamento) — conferir" in avisos[0].texto
    assert "01/10/2026" in avisos[0].texto and "05/10/2026" in avisos[0].texto


def test_pagamento_no_proprio_dia_da_emissao_nao_gera_aviso(nota, usuario_gestor_a, empresa_a2):
    servico.informar_data_pagamento(nota, date(2026, 10, 5), "Mesmo dia", usuario_gestor_a)

    avisos = [
        aviso.codigo
        for _, aviso in retencoes_federais(empresa_a2, 2026, 10).avisos
        if aviso.codigo == "PAGAMENTO_ANTES_DA_EMISSAO"
    ]
    assert avisos == []


def test_limpar_devolve_a_retencao_a_pendente_e_grava_a_trilha(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    # Nota só com IRRF (sem ISS): a retenção aparece em "pendente" enquanto não há data.
    retida = tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8110,
        T2,
        tp_ret_issqn="1",
        v_ret_irrf="15.00",
        d_compet="2026-10-05",
    )
    assert retida.pk in {
        e.pk for e in retencoes_federais(empresa_a2, 2026, 10).pendentes_de_pagamento
    }
    servico.informar_data_pagamento(
        retida, date(2026, 10, 6), "Pagamento sintético", usuario_gestor_a
    )
    assert retida.pk not in {
        e.pk for e in retencoes_federais(empresa_a2, 2026, 10).pendentes_de_pagamento
    }

    limpa = servico.limpar_data_pagamento(retida, "Data digitada por engano", usuario_gestor_a)

    assert limpa.criada_agora is True
    assert limpa.data_pagamento is None
    assert limpa.pagamento_informado_em is None
    assert limpa.pagamento_informado_por_id is None
    assert limpa.motivo_pagamento == ""
    assert limpa.estado == EstadoEscrituracao.EFETIVADA
    assert retida.pk in {
        e.pk for e in retencoes_federais(empresa_a2, 2026, 10).pendentes_de_pagamento
    }

    trilha = _trilha(ACAO_LIMPAR)
    assert len(trilha) == 1
    assert trilha[0].usuario_id == usuario_gestor_a.pk
    assert trilha[0].detalhes["motivo"] == "Data digitada por engano"
    assert trilha[0].detalhes["antes"]["data_pagamento"] == "2026-10-06"
    assert trilha[0].detalhes["antes"]["motivo_pagamento"] == "Pagamento sintético"
    assert trilha[0].detalhes["depois"]["data_pagamento"] is None
    assert trilha[0].detalhes["depois"]["estado"] == EstadoEscrituracao.EFETIVADA


@pytest.mark.parametrize("motivo", ["", "   "])
def test_limpar_sem_motivo_e_recusado_e_nada_muda(nota, usuario_gestor_a, motivo):
    servico.informar_data_pagamento(
        nota, date(2026, 10, 6), "Pagamento sintético", usuario_gestor_a
    )

    with pytest.raises(EntradaInvalidaEscrituracao, match="Informe o motivo da limpeza"):
        servico.limpar_data_pagamento(nota, motivo, usuario_gestor_a)

    nota.refresh_from_db()
    assert nota.data_pagamento == date(2026, 10, 6)
    assert _trilha(ACAO_LIMPAR) == []


def test_limpar_nota_nao_efetivada_e_recusado(escritorio_a, usuario_gestor_a, empresa_a2):
    documento = receber_tomada(
        escritorio_a, usuario_gestor_a, 8120, tomador_documento=empresa_a2.cnpj, tp_ret_issqn="2"
    )
    rascunho = servico.salvar_rascunho(vinculo_tomador(documento, empresa_a2), T1, usuario_gestor_a)

    with pytest.raises(EscrituracaoErro, match="só é limpa em escrituração efetivada"):
        servico.limpar_data_pagamento(rascunho, "Motivo sintético", usuario_gestor_a)


def test_limpar_nota_sem_data_e_no_op_sem_trilha(nota, usuario_gestor_a):
    limpa = servico.limpar_data_pagamento(nota, "Nada a limpar", usuario_gestor_a)

    assert limpa.criada_agora is False
    assert _trilha(ACAO_LIMPAR) == []


def test_depois_de_limpar_o_banco_continua_recusando_alteracao_fora_do_grupo(
    nota, usuario_gestor_a
):
    servico.informar_data_pagamento(
        nota, date(2026, 10, 6), "Pagamento sintético", usuario_gestor_a
    )
    servico.limpar_data_pagamento(nota, "Data digitada por engano", usuario_gestor_a)

    # SQL direto, fora do Python: o gatilho da migração 0008 recusa qualquer coluna fora do grupo.
    with transaction.atomic(), pytest.raises(IntegrityError):
        EscrituracaoTomada.objects.filter(pk=nota.pk).update(v_iss_qn=Decimal("777.77"))
    nota.refresh_from_db()
    assert nota.v_iss_qn == Decimal("50.00")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _url_pagamento_api(empresa, escrituracao):
    return (
        f"/fiscal/api/empresas/{empresa.pk}/tomadas/escrituracoes/{escrituracao.pk}/data-pagamento/"
    )


def _url_limpar_api(empresa, escrituracao):
    return f"{_url_pagamento_api(empresa, escrituracao)}limpar/"


@pytest.mark.parametrize("dia", FORA_DA_JANELA, ids=lambda d: d.isoformat())
def test_api_recusa_data_fora_da_janela_com_400_e_nomeia_a_janela(
    client, empresa_a2, usuario_gestor_a, nota, dia
):
    _logar(client, usuario_gestor_a)

    resposta = _post(
        client,
        _url_pagamento_api(empresa_a2, nota),
        {"data_pagamento": dia.isoformat(), "motivo": "Digitação sintética"},
    )

    assert resposta.status_code == 400
    assert "fora da janela aceita" in resposta.content.decode()
    nota.refresh_from_db()
    assert nota.data_pagamento is None


def test_api_aceita_o_limite_inferior_e_limpa_com_motivo(
    client, empresa_a2, usuario_gestor_a, nota
):
    _logar(client, usuario_gestor_a)

    informada = _post(
        client,
        _url_pagamento_api(empresa_a2, nota),
        {"data_pagamento": INICIO_DA_JANELA.isoformat(), "motivo": "Limite sintético"},
    )
    assert informada.status_code == 201
    assert informada.json()["data_pagamento"] == INICIO_DA_JANELA.isoformat()

    sem_motivo = _post(client, _url_limpar_api(empresa_a2, nota), {"motivo": "   "})
    assert sem_motivo.status_code == 400
    assert "Informe o motivo da limpeza da data de pagamento." in sem_motivo.content.decode()
    nota.refresh_from_db()
    assert nota.data_pagamento == INICIO_DA_JANELA

    limpa = _post(client, _url_limpar_api(empresa_a2, nota), {"motivo": "Digitado por engano"})
    assert limpa.status_code == 200
    assert limpa.json()["data_pagamento"] is None
    assert limpa.json()["estado"] == EstadoEscrituracao.EFETIVADA
    nota.refresh_from_db()
    assert nota.data_pagamento is None
    assert len(_trilha(ACAO_LIMPAR)) == 1


def test_api_limpar_nota_de_outra_empresa_responde_404(
    client, escritorio_a, empresa_a, usuario_gestor_a, nota, empresa_a2
):
    # A nota é de `empresa_a2`; pedir pela `empresa_a` (mesmo escritório) não a encontra.
    _logar(client, usuario_gestor_a)

    resposta = _post(client, _url_limpar_api(empresa_a, nota), {"motivo": "Motivo sintético"})

    assert resposta.status_code == 404
    nota.refresh_from_db()
    assert nota.data_pagamento is None


# ---------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------


def _url_pagamento_tela(empresa, escrituracao):
    return reverse("fiscal_web:tomada_data_pagamento", args=[empresa.pk, escrituracao.pk])


def _url_limpar_tela(empresa, escrituracao):
    return reverse("fiscal_web:tomada_data_pagamento_limpar", args=[empresa.pk, escrituracao.pk])


@pytest.mark.parametrize("dia", FORA_DA_JANELA, ids=lambda d: d.isoformat())
def test_tela_recusa_data_fora_da_janela_com_mensagem_e_nada_gravado(
    client, empresa_a2, usuario_gestor_a, nota, dia
):
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_pagamento_tela(empresa_a2, nota),
        {"data_pagamento": _br(dia), "motivo": "Digitação sintética"},
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fora da janela aceita" in html
    assert "de 04/10/2025" in html
    nota.refresh_from_db()
    assert nota.data_pagamento is None


def test_tela_mostra_a_janela_e_aceita_os_limites(client, empresa_a2, usuario_gestor_a, nota):
    _logar(client, usuario_gestor_a)

    pagina = client.get(_url_pagamento_tela(empresa_a2, nota)).content.decode()
    assert "Aceita de 04/10/2025 até 15/12/2026 (hoje)" in pagina

    inferior = client.post(
        _url_pagamento_tela(empresa_a2, nota),
        {"data_pagamento": _br(INICIO_DA_JANELA), "motivo": "Limite sintético"},
    )
    assert inferior.status_code == 302
    superior = client.post(
        _url_pagamento_tela(empresa_a2, nota),
        {"data_pagamento": _br(DIA_DE_HOJE_NO_TESTE), "motivo": "Limite sintético"},
    )
    assert superior.status_code == 302
    nota.refresh_from_db()
    assert nota.data_pagamento == DIA_DE_HOJE_NO_TESTE


def test_tela_limpa_com_motivo_recusa_sem_motivo_e_mostra_a_trilha(
    client, empresa_a2, usuario_gestor_a, nota
):
    _logar(client, usuario_gestor_a)
    client.post(
        _url_pagamento_tela(empresa_a2, nota),
        {"data_pagamento": "06/10/2026", "motivo": "Pagamento sintético"},
    )

    sem_motivo = client.post(_url_limpar_tela(empresa_a2, nota), {"motivo": ""})
    assert sem_motivo.status_code == 200
    assert "Informe o motivo da limpeza da data de pagamento." in sem_motivo.content.decode()
    nota.refresh_from_db()
    assert nota.data_pagamento == date(2026, 10, 6)

    limpa = client.post(
        _url_limpar_tela(empresa_a2, nota),
        {"motivo": "Digitado por engano"},
        follow=True,
    )
    html = limpa.content.decode()
    nota.refresh_from_db()
    assert nota.data_pagamento is None
    assert "Nenhuma data de pagamento foi informada" not in html
    assert "Data limpa" in html
    assert "Digitado por engano" in html


def test_tela_limpar_so_aceita_post(client, empresa_a2, usuario_gestor_a, nota):
    _logar(client, usuario_gestor_a)

    assert client.get(_url_limpar_tela(empresa_a2, nota)).status_code == 405


def test_tela_limpar_de_outra_empresa_responde_404(
    client, empresa_a, usuario_gestor_a, nota, empresa_a2
):
    _logar(client, usuario_gestor_a)

    resposta = client.post(_url_limpar_tela(empresa_a, nota), {"motivo": "Motivo sintético"})

    assert resposta.status_code == 404
    nota.refresh_from_db()
    assert nota.data_pagamento is None


def test_efetivada_nasce_sem_data_de_pagamento(escritorio_a, usuario_gestor_a, empresa_a2):
    # Ponto de partida de todo teste desta página: efetivada, e sem data até alguém informar.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8130,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="10.00",
        v_liq="990.00",
        c_loc_incid="1721000",
    )
    escrituracao = servico.efetivar_escrituracao_tomada(
        vinculo_tomador(documento, empresa_a2), T1, usuario_gestor_a
    )
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA
    assert escrituracao.data_pagamento is None
