"""DL-079 — testes da reconferência (R1, R2 e R4), integrados pelo arquiteto.

Pela regra de parada do §3.1 não há nova rodada de correção. Os resíduos da reconferência
(docs/auditorias/2026-10-09-dl-079-reconferencia.md) fecham assim:

- R1 (caractere substituto solitário em texto da API dava 500) e R2 (a soma das receitas
  integrais acima do teto do campo dava 500 ao declarar): ajuste pontual em `presumido._texto`
  e em `declarar_receitas_integrais`, com os testes T-R1 e T-R2 propostos pelo auditor.
- R4 (lacunas de teste): T-R4a (a guarda de duplicidade não bloqueia receita legítima de outra
  atividade, de outro trimestre nem de outra empresa — mutantes N13, N14, N15), T-R4b (o
  gatilho da atividade recusa `fim` junto com outra coluna — N26) e T-R4c (identificador acima
  do inteiro de 64 bits — N33).

Dados sintéticos; valores escritos à mão.
"""

import json
from datetime import date
from decimal import Decimal as D

import pytest
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import (
    AtividadePresuncaoEmpresa,
    DeclaracaoReceitasIntegrais,
    ReceitaTrimestralPresumido,
)

pytestmark = pytest.mark.django_db

COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
SERVICOS = tab.SERVICOS_GERAIS
TETO = "9999999999999.99"


def _presumida(empresa, usuario, codigo_padrao=COMERCIO):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    servico.definir_criterio(empresa, 2026, "competencia", usuario)
    return servico.criar_atividade(
        empresa, {"atividade": codigo_padrao, "inicio": date(2026, 1, 1), "padrao": True}, usuario
    )


def _receita(empresa, usuario, trimestre, atividade, valor="1000.00", suporte="Contrato 12"):
    return servico.criar_receita(
        empresa,
        2026,
        trimestre,
        {
            "tipo": "presuncao",
            "valor": valor,
            "atividade_id": atividade.pk,
            "descricao": "Receita informada",
            "suporte": suporte,
        },
        usuario,
    )


def _integral(empresa, usuario, trimestre, valor):
    return servico.criar_receita(
        empresa,
        2026,
        trimestre,
        {"tipo": "integral", "valor": valor, "descricao": "Aplicação", "suporte": "Extrato"},
        usuario,
    )


# ---------- R1: caractere substituto solitário vira 400 ----------


@pytest.mark.parametrize("campo", ["descricao", "suporte"])
def test_r1_api_recusa_caractere_substituto_na_receita(client, empresa_a, usuario_gestor_a, campo):
    atividade = _presumida(empresa_a, usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    corpo = {
        "ano": 2026,
        "trimestre": 1,
        "tipo": "presuncao",
        "valor": "1000.00",
        "atividade_id": atividade.pk,
        "descricao": "Receita",
        "suporte": "Contrato",
    }
    # O JSON cru com "\ud800" chega ao Python como um substituto solitário.
    bruto = json.dumps(corpo).replace(f'"{corpo[campo]}"', '"\\ud800"')
    resposta = client.post(
        reverse("fiscal_api:presumido_receitas", kwargs={"empresa_id": empresa_a.pk}),
        data=bruto,
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert not ReceitaTrimestralPresumido.objects.filter(empresa=empresa_a).exists()


def test_r1_servico_recusa_substituto_no_motivo_do_estorno(empresa_a, usuario_gestor_a):
    atividade = _presumida(empresa_a, usuario_gestor_a)
    receita = _receita(empresa_a, usuario_gestor_a, 1, atividade)
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.estornar_receita(empresa_a, receita.pk, "\ud800", usuario_gestor_a)
    receita.refresh_from_db()
    assert receita.estado == "ativa"


# ---------- R2: a soma das integrais acima do teto não chega ao banco ----------


def test_r2_declaracao_com_soma_acima_do_teto_e_recusada(empresa_a, usuario_gestor_a):
    _presumida(empresa_a, usuario_gestor_a)
    _integral(empresa_a, usuario_gestor_a, 1, TETO)
    _integral(empresa_a, usuario_gestor_a, 1, "0.01")
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.declarar_receitas_integrais(empresa_a, 2026, 1, "", usuario_gestor_a)
    assert not DeclaracaoReceitasIntegrais.objects.filter(empresa=empresa_a).exists()


def test_r2_declaracao_no_teto_exato_passa(empresa_a, usuario_gestor_a):
    _presumida(empresa_a, usuario_gestor_a)
    _integral(empresa_a, usuario_gestor_a, 1, TETO)
    declaracao = servico.declarar_receitas_integrais(empresa_a, 2026, 1, "", usuario_gestor_a)
    assert declaracao.total == D(TETO)


# ---------- R4a: a guarda de duplicidade não bloqueia o legítimo (N13, N14, N15) ----------


def test_r4a_receita_igual_em_outra_atividade_passa(empresa_a, usuario_gestor_a):
    comercio = _presumida(empresa_a, usuario_gestor_a)
    servicos = servico.criar_atividade(
        empresa_a,
        {"atividade": SERVICOS, "inicio": date(2026, 1, 1), "padrao": False},
        usuario_gestor_a,
    )
    _receita(empresa_a, usuario_gestor_a, 1, comercio)
    _receita(empresa_a, usuario_gestor_a, 1, servicos)
    assert ReceitaTrimestralPresumido.objects.filter(empresa=empresa_a).count() == 2


def test_r4a_receita_igual_em_outro_trimestre_passa(empresa_a, usuario_gestor_a):
    comercio = _presumida(empresa_a, usuario_gestor_a)
    _receita(empresa_a, usuario_gestor_a, 1, comercio)
    _receita(empresa_a, usuario_gestor_a, 2, comercio)
    assert ReceitaTrimestralPresumido.objects.filter(empresa=empresa_a).count() == 2


def test_r4a_receita_igual_em_outra_empresa_passa_e_nao_cita_a_alheia(
    empresa_a, empresa_a2, usuario_gestor_a
):
    # Receita INTEGRAL não tem atividade: é o caso em que só o filtro de empresa separa as duas.
    _presumida(empresa_a, usuario_gestor_a)
    _presumida(empresa_a2, usuario_gestor_a)
    receita_a = _integral(empresa_a, usuario_gestor_a, 1, "500.00")
    receita_a2 = _integral(empresa_a2, usuario_gestor_a, 1, "500.00")
    assert ReceitaTrimestralPresumido.objects.filter(empresa=empresa_a2).count() == 1
    # Repetir na empresa A2 é recusado, e a mensagem cita a receita de A2, nunca a de A.
    with pytest.raises(servico.PresumidoConflito) as erro:
        _integral(empresa_a2, usuario_gestor_a, 1, "500.00")
    assert f"nº {receita_a2.pk}" in str(erro.value)
    assert f"nº {receita_a.pk}" not in str(erro.value)


# ---------- R4b: o gatilho da atividade recusa `fim` junto com outra coluna (N26) ----------


@pytest.mark.parametrize(
    "extra", ["padrao = false", "inicio = '2026-02-01'"], ids=["com-padrao", "com-inicio"]
)
def test_r4b_gatilho_recusa_fim_junto_com_outra_coluna(empresa_a, usuario_gestor_a, extra):
    atividade = _presumida(empresa_a, usuario_gestor_a)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE fiscal_atividadepresuncaoempresa SET fim = '2026-06-30', {extra} "
            "WHERE id = %s",
            [atividade.pk],
        )
    atividade.refresh_from_db()
    assert atividade.fim is None
    assert AtividadePresuncaoEmpresa.objects.get(pk=atividade.pk).padrao is True


# ---------- R4c: identificador acima do inteiro de 64 bits vira 400 (N33) ----------


@pytest.mark.parametrize("identificador", [2**63, 10**30])
def test_r4c_identificador_gigante_e_recusado(empresa_a, usuario_gestor_a, identificador):
    _presumida(empresa_a, usuario_gestor_a)
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.inteiro_de_entrada(identificador, "a receita")
