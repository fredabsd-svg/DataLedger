"""DL-065 (BL-550) — as PORTAS da trava: API, tela, admin, e a prova de que a
classificação da DRE continua livre (DE-086).

A REGRA em si está em `test_dl065_periodo_fechado.py`. Este arquivo cobre o
que só aparece na borda, e é onde o defeito original era pior — o
`ContaAdmin` grava os quatro campos de classificação **por fora** dos três
serviços, então uma trava colocada só nos serviços deixaria o admin
funcionando como antes, sem ninguém perceber.

- 8: o admin não escapa — o `ModelForm` que ele gera recusa, e o campo
  continua VISÍVEL (esconder o campo calaria o admin sem fechar a regra, e
  isso é um defeito diferente);
- 10: a classificação da DRE **continua livre** com movimento em período
  encerrado — a DE-086 (26/09/2026) não foi revogada por esta demanda. O
  teste existe porque o dano de um vazamento aqui é o pior possível: fechar a
  DRE tiraria do contador a ÚNICA saída do veto do A2 e tornaria a DRE de um
  período inemitível sem SQL;
- 11: isolamento — conta de outro escritório dá 404 e não dispara a guarda;
- e a tradução: 409 na API (não 400), recusa no formulário da tela (não 500).
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import models
from django.test import RequestFactory
from django.urls import reverse

from apps.contabilidade.admin import ContaAdmin
from apps.contabilidade.models import ClassificacaoDlpa, ClassificacaoDmpl, ClassificacaoDre, Conta
from apps.contabilidade.services import classificar_conta_na_dre, encerrar_competencia
from apps.contabilidade.tests import test_dl048_dlpa as _dlpa
from apps.contabilidade.tests import test_dl061_dmpl as _base
from apps.contabilidade.tests.test_dl065_periodo_fechado import _cenario, _movimentar
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

ANO = 2026
MES = 3


def _url_da_api(demonstracao, empresa, conta):
    return reverse(f"contabilidade:conta-classificacao-{demonstracao}", args=[empresa.id, conta.id])


def _url_da_tela(demonstracao, empresa, conta):
    return reverse(
        f"contabilidade_web:conta_classificacao_{demonstracao}", args=[empresa.id, conta.id]
    )


# ---------------------------------------------------------------------------
# A tradução: 409 na API
# ---------------------------------------------------------------------------


def test_a_api_da_dlpa_responde_409_e_nao_400(client):
    """400 diria ao cliente que o corpo está errado e que basta corrigir o
    corpo enviado. O corpo está certo: o que impede é o ESTADO da
    competência."""
    empresa, contas, gestor, conta_dlpa, _ = _cenario("api-dlpa")
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-api-dlpa")

    resposta = client.patch(
        _url_da_api("dlpa", empresa, conta_dlpa),
        data={"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL.value},
        content_type="application/json",
    )

    assert resposta.status_code == 409
    assert "03/2026" in resposta.json()["detail"]
    conta_dlpa.refresh_from_db()
    assert conta_dlpa.classificacao_dlpa == ClassificacaoDlpa.DIVIDENDO


def test_a_api_da_dmpl_responde_409(client):
    empresa, contas, gestor, _, conta_dmpl = _cenario("api-dmpl")
    _movimentar(empresa, contas, conta_dmpl)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-api-dmpl")

    resposta = client.patch(
        _url_da_api("dmpl", empresa, conta_dmpl),
        data={"classificacao_dmpl": ClassificacaoDmpl.RESERVA_LEGAL.value},
        content_type="application/json",
    )

    assert resposta.status_code == 409
    assert "03/2026" in resposta.json()["detail"]


def test_a_api_aceita_quando_o_periodo_esta_aberto(client):
    """O caminho normal não pode virar 409: seria a trava funcionando às
    avessas, fechando o produto para o uso legítimo."""
    empresa, contas, gestor, conta_dlpa, _ = _cenario("api-aberta")
    _movimentar(empresa, contas, conta_dlpa)
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-api-aberta")

    resposta = client.patch(
        _url_da_api("dlpa", empresa, conta_dlpa),
        data={"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL.value},
        content_type="application/json",
    )

    assert resposta.status_code == 200
    assert resposta.json()["classificacao_dlpa"] == ClassificacaoDlpa.RESERVA_LEGAL.value


# ---------------------------------------------------------------------------
# A tradução: recusa no formulário da tela, nunca 500
# ---------------------------------------------------------------------------


def test_a_tela_mostra_a_recusa_no_formulario_e_nao_grava(client):
    empresa, contas, gestor, conta_dlpa, _ = _cenario("tela-dlpa")
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-tela-dlpa")

    resposta = client.post(
        _url_da_tela("dlpa", empresa, conta_dlpa),
        data={"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL.value},
    )

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "03/2026" in html
    conta_dlpa.refresh_from_db()
    assert conta_dlpa.classificacao_dlpa == ClassificacaoDlpa.DIVIDENDO


# ---------------------------------------------------------------------------
# Critério 8 — o admin
# ---------------------------------------------------------------------------


def _para_o_formulario(valor):
    if valor is None:
        return ""
    if isinstance(valor, models.Model):
        return str(valor.pk)
    if isinstance(valor, bool):
        return "on" if valor else ""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return str(valor)


def _formulario_do_admin(conta, **mudancas):
    """Instancia o MESMO `ModelForm` que o admin gera, preenchido com os
    valores atuais da conta e com as classificações trocadas.

    Não é um atalho para `full_clean()`: é o caminho que o Django percorre de
    verdade ao salvar pelo admin (`_post_clean` → `instance.full_clean()`), e
    é por isso que a regra do modelo fecha o admin sem código nenhum aqui.
    """
    admin = ContaAdmin(Conta, AdminSite())
    request = RequestFactory().get("/admin/contabilidade/conta/")
    request.user = _base._gestor(conta.empresa, f"gestor-admin-{conta.pk}")
    classe = admin.get_form(request)
    # TODOS os campos, não só os obrigatórios: um `BooleanField` do Django
    # tem `required=False` porque o widget é um checkbox, e checkbox
    # desmarcado chega como `False`. Deixar o campo de fora do `data` mudaria
    # a conta para sintética — e o formulário ficaria inválido por um motivo
    # que não tem nada com a trava, que é exatamente o tipo de falso
    # positivo que faz um teste deadmin passar a Assertar qualquer coisa.
    dados = {nome: _para_o_formulario(getattr(conta, nome, None)) for nome in classe.base_fields}
    dados.update(mudancas)
    return classe(instance=conta, data=dados)


def test_criterio8_o_admin_nao_escapa_da_trava():
    empresa, contas, gestor, conta_dlpa, _ = _cenario("admin")
    _movimentar(empresa, contas, conta_dlpa)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    form = _formulario_do_admin(
        conta_dlpa, classificacao_dlpa=ClassificacaoDlpa.RESERVA_LEGAL.value
    )

    assert not form.is_valid()
    assert any(
        "03/2026" in mensagem for mensagens in form.errors.values() for mensagem in mensagens
    )


def test_criterio8_o_campo_continua_visivel_no_admin():
    """O caminho do defeito é o campo exposto. Esconder a classificação
    calaria o admin, mas trocaria um defeito (reclassificação silenciosa)
    por outro (o contador sem porta nenhuma para classificar) — a trava tem
    de ser a regra, não o sumiço."""
    form = _formulario_do_admin(
        _cenario("admin-visivel")[3], classificacao_dlpa=ClassificacaoDlpa.DIVIDENDO.value
    )
    assert "classificacao_dlpa" in form.fields
    assert "classificacao_dmpl" in form.fields


# ---------------------------------------------------------------------------
# Critério 10 — a DRE continua livre (DE-086)
# ---------------------------------------------------------------------------


def test_criterio10_a_dre_continua_livre_com_periodo_encerrado():
    """A DE-086 (26/09/2026) decidiu que a linha da DRE é propriedade de
    apresentação e muda com movimento, sempre. Esta demanda é de 05/10/2026 e
    o Fred manteve essa decisão: a trava é para a DLPA e a DMPL."""
    empresa, contas, gestor, _, _ = _cenario("dre")
    receita = contas["receita"]
    _movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    classificar_conta_na_dre(
        conta=receita,
        classificacao=ClassificacaoDre.RECEITA_BRUTA,
        usuario=gestor,
    )

    receita.refresh_from_db()
    assert receita.classificacao_dre == ClassificacaoDre.RECEITA_BRUTA


# ---------------------------------------------------------------------------
# Critério 11 — isolamento
# ---------------------------------------------------------------------------


def test_criterio11_conta_de_outro_escritorio_da_404_e_nao_dispara_a_guarda(client):
    """A guarda consulta movimento por empresa; se rodasse ANTES do
    `get_object_or_404`, a resposta seria 409 para uma conta que nem pertence
    a quem pergunta — e o 409 confirmaria a existência do registro, que é
    informação de outro escritório."""
    empresa, _, _, conta_dlpa, _ = _cenario("isolamento")
    outro = _base._empresa("Outro Escritório DL-065")
    _dlpa._autenticar(client, outro.escritorio, username="gestor-isolamento")
    assert Papel.GESTOR

    resposta = client.patch(
        _url_da_api("dlpa", empresa, conta_dlpa),
        data={"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL.value},
        content_type="application/json",
    )

    assert resposta.status_code == 404


def test_criterio11_a_tela_da_dlpa_tambem_da_404(client):
    """O critério 11 era testado só na API. A tela tem o próprio
    `get_object_or_404`, e porta que não é testada é porta que ninguém sabe
    que fecha (achado A7 da auditoria)."""
    empresa, _, _, conta_dlpa, _ = _cenario("isolamento-tela")
    outro = _base._empresa("Outro Escritório DL-065 Tela")
    _dlpa._autenticar(client, outro.escritorio, username="gestor-isolamento-tela")

    resposta = client.post(
        _url_da_tela("dlpa", empresa, conta_dlpa),
        data={"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL.value},
    )

    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# A7 — as duas portas que faltavam: tela da DMPL e admin da coluna da DMPL
# ---------------------------------------------------------------------------


def test_a7_a_tela_da_dmpl_mostra_a_recusa_e_nao_grava(client):
    empresa, contas, gestor, _, conta_dmpl = _cenario("tela-dmpl")
    _movimentar(empresa, contas, conta_dmpl)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-tela-dmpl")

    resposta = client.post(
        _url_da_tela("dmpl", empresa, conta_dmpl),
        data={"classificacao_dmpl": ClassificacaoDmpl.RESERVA_LEGAL.value},
    )

    assert resposta.status_code == 200
    assert "03/2026" in resposta.content.decode()
    conta_dmpl.refresh_from_db()
    assert conta_dmpl.classificacao_dmpl == ClassificacaoDmpl.RESERVA_DE_LUCROS_A_REALIZAR


def test_a7_o_admin_tambem_recusa_a_coluna_da_dmpl():
    """A guarda de modelo é uma só, mas a prova precisa existir para as DUAS
    classificações: um `code` escrito para `classificacao_dlpa` e não para
    `classificacao_dmpl` passaria em todos os testes de um e deixaria o
    outro aberto."""
    empresa, contas, gestor, _, conta_dmpl = _cenario("admin-dmpl")
    _movimentar(empresa, contas, conta_dmpl)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)

    form = _formulario_do_admin(
        conta_dmpl, classificacao_dmpl=ClassificacaoDmpl.RESERVA_LEGAL.value
    )

    assert not form.is_valid()
    assert any(
        "03/2026" in mensagem for mensagens in form.errors.values() for mensagem in mensagens
    )
