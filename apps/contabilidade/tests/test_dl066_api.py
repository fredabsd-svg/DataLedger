"""DL-066, etapa 2 — as portas de API da DFC (`DfcView` e
`ContaClassificacaoDfcView`).

Cobre o critério de aceite 19 da etapa 2 (`docs/planos/DL-066-dfc.md`): a
API GET e a de classificação espelham as irmãs (DLPA/DMPL), com 409 em
período fechado e isolamento entre empresas — mais as bordas que só a porta
tem: corpo malformado vira 400 (nunca 500), chave fora do contrato é
recusada por NOME, PATCH parcial não mexe no que não veio, e as coerências do
modelo (caixa × atividade) vêm pela mesma fonte (`Conta.clean()`).

O contrato do GET é o MESMO dicionário que a tela consome
(`_para_json_da_apuracao`: dinheiro como texto de duas casas, DL-030).

Dados 100% sintéticos. Datas em 2026.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    ClassificacaoDre,
    ClassificacaoFluxoCaixa,
    Conta,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento, encerrar_competencia
from apps.contabilidade.tests import test_dl048_dlpa as _dlpa
from apps.contabilidade.tests import test_dl061_dmpl as _base
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA
ATIVO = TipoConta.ATIVO
RECEITA = TipoConta.RECEITA
DESPESA = TipoConta.DESPESA

ATIV = ClassificacaoFluxoCaixa.OPERACIONAL
INVEST = ClassificacaoFluxoCaixa.INVESTIMENTO
FINANC = ClassificacaoFluxoCaixa.FINANCIAMENTO

ANO = 2026
MES = 3


def _dec(valor):
    return Decimal(valor)


def _cenario(nome="api-dfc"):
    """Caixa marcada e uma conta de resultado já classificada — o estado em
    que a porta é usada pelo integrador."""
    empresa = _base._empresa(f"Empresa {nome}")
    contas = _base._plano_basico(empresa)
    gestor = _base._gestor(empresa, f"gestor-{nome}-{empresa.pk}")
    caixa = contas["caixa"]
    caixa.caixa_e_equivalentes = True
    caixa.full_clean()
    caixa.save()
    receita = contas["receita"]
    receita.classificacao_dfc = ATIV
    # Linha da DRE necessária: o lucro do método indireto vem do MESMO motor
    # que publica a DRE (DE-020), e sem linha a conta cai no resíduo — a
    # identidade do item 20A veta a emissão com razão.
    receita.classificacao_dre = ClassificacaoDre.RECEITA_BRUTA
    receita.full_clean()
    receita.save()
    return empresa, contas, gestor, caixa, receita


def _lancar(empresa, data, historico, debito, credito, valor):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": _dec(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": _dec(valor)},
        ],
        criado_por=None,
    )


def _url_da_dfc(empresa, ano=ANO, mes=MES):
    return reverse("contabilidade:dfc", args=[empresa.id, ano, mes])


def _url_da_classificacao(empresa, conta):
    return reverse("contabilidade:conta-classificacao-dfc", args=[empresa.id, conta.id])


# ---------------------------------------------------------------------------
# GET da apuração
# ---------------------------------------------------------------------------


def test_get_apresenta_a_apuracao_com_o_indireto_em_texto(client):
    """O corpo é o MESMO da tela, e dinheiro viaja como texto (DL-030)."""
    empresa, contas, gestor, caixa, receita = _cenario("get-ok")
    _lancar(empresa, date(2026, 3, 10), "Venda a vista", caixa, receita, "85000.00")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-get-ok")

    resposta = client.get(_url_da_dfc(empresa))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["pode_emitir"] is True
    assert corpo["atividades"]["operacional"] == "85000.00"
    indireto = corpo["operacional_indireto"]
    assert indireto["fluxo_operacional"] == "85000.00"
    assert indireto["fluxo_operacional_pelo_direto"] == "85000.00"
    assert indireto["confere"] is True
    assert indireto["lucro_liquido"] == "85000.00"


def test_get_responde_409_com_o_corpo_inteiro_quando_vetado(client):
    """409 informa o veto, não substitui a apuração: o integrador vê o que
    falta, nomeado (mesmo desenho de `DmplView`)."""
    empresa, contas, gestor, caixa, receita = _cenario("get-veto")
    # Contraparte SEM atividade: pendência que veta e nomeia a conta.
    imobilizado = _base._conta(empresa, "1.3", "Veículos", ATIVO, D)
    _lancar(empresa, date(2026, 3, 10), "Compra de veículo", imobilizado, caixa, "30000.00")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-get-veto")

    resposta = client.get(_url_da_dfc(empresa))

    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["pode_emitir"] is False
    assert any("contrapartida não tem atividade" in motivo for motivo in corpo["motivos"])
    assert corpo["pendencias"]["lancamentos_sem_atividade"], (
        "o corpo inteiro da apuração continua no 409"
    )


def test_get_recusa_periodo_fora_da_faixa_com_400(client):
    empresa, contas, gestor, caixa, receita = _cenario("get-400")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-get-400")

    assert client.get(_url_da_dfc(empresa, ano=2026, mes=13)).status_code == 400


def test_get_e_isolado_por_empresa(client):
    """Empresa de OUTRO escritório é 404/403 pela fronteira do mixin — nunca
    a apuração dela (critério 10)."""
    empresa, contas, gestor, caixa, receita = _cenario("get-iso")
    outra = _base._empresa("Empresa de outro escritório")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-get-iso")

    resposta = client.get(_url_da_dfc(outra))

    assert resposta.status_code in (403, 404)


# ---------------------------------------------------------------------------
# PATCH da classificação
# ---------------------------------------------------------------------------


def test_patch_classifica_os_tres_campos_e_registra_trilha(client):
    empresa, contas, gestor, caixa, receita = _cenario("patch-ok")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-patch-ok")

    resposta = client.patch(
        _url_da_classificacao(empresa, receita),
        data={
            "caixa_e_equivalentes": False,
            "classificacao_dfc": ATIV,
            "item_de_resultado_sem_caixa": True,
        },
        content_type="application/json",
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["classificacao_dfc"] == ATIV
    assert corpo["item_de_resultado_sem_caixa"] is True
    assert corpo["caixa_e_equivalentes"] is False
    registros = list(RegistroAuditoria.objects.filter(acao="conta.classificacao_dfc_alterada"))
    assert len(registros) == 1
    assert registros[0].detalhes["item_de_resultado_sem_caixa"] == {"antes": False, "depois": True}


def test_patch_parcial_nao_mexe_no_que_nao_veio(client):
    """⚠️ A1 (GRAVE) da auditoria da etapa 2: este teste nasceu CEGO — o
    cenário partia com os campos ausentes já em `False`, igual ao default
    destrutivo, e a mutação "campo ausente vira default" derrubava zero
    testes. Agora os campos ausentes têm valores DIFERENTES do default
    (`item_de_resultado_sem_caixa=True` numa conta, `caixa_e_equivalentes=
    True` em outra), de modo que um PATCH que apague o que não veio morre
    aqui. O PATCH é parcial: a fusão acontece na view, e o que não veio no
    corpo permanece como estava — sem isso, mandar só a atividade apagaria
    as outras marcações em silêncio (BL-196)."""
    empresa, contas, gestor, caixa, receita = _cenario("patch-parcial")
    despesa = _base._conta(empresa, "5.2", "Depreciação", DESPESA, D)
    despesa.item_de_resultado_sem_caixa = True
    despesa.classificacao_dfc = FINANC
    despesa.full_clean()
    despesa.save()
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-patch-parcial")

    # (a) Só a atividade muda numa conta cuja marcação "sem caixa" é True —
    # se o PATCH a destruir, o assert pega.
    resposta = client.patch(
        _url_da_classificacao(empresa, despesa),
        data={"classificacao_dfc": ATIV},
        content_type="application/json",
    )

    assert resposta.status_code == 200
    despesa.refresh_from_db()
    assert despesa.classificacao_dfc == ATIV
    assert despesa.item_de_resultado_sem_caixa is True, (
        "o campo que não veio no PATCH não pode voltar ao default"
    )
    registros = list(RegistroAuditoria.objects.filter(acao="conta.classificacao_dfc_alterada"))
    assert len(registros) == 1
    assert registros[0].detalhes == {"classificacao_dfc": {"antes": FINANC, "depois": ATIV}}, (
        "a trilha registra SÓ o campo que mudou"
    )

    # (b) Só a atividade (nula) numa conta de caixa marcada — se o PATCH
    # destruir a marca de caixa, o assert pega.
    resposta = client.patch(
        _url_da_classificacao(empresa, caixa),
        data={"classificacao_dfc": None},
        content_type="application/json",
    )

    assert resposta.status_code == 200
    caixa.refresh_from_db()
    assert caixa.caixa_e_equivalentes is True, (
        "o campo que não veio no PATCH não pode voltar ao default"
    )


def test_patch_responde_409_e_nao_grava_em_periodo_fechado(client):
    empresa, contas, gestor, caixa, receita = _cenario("patch-409")
    _lancar(empresa, date(2026, 3, 15), "Movimento", caixa, receita, "1000.00")
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-patch-409")

    resposta = client.patch(
        _url_da_classificacao(empresa, receita),
        data={"classificacao_dfc": INVEST},
        content_type="application/json",
    )

    assert resposta.status_code == 409
    assert "03/2026" in resposta.json()["detail"]
    receita.refresh_from_db()
    assert receita.classificacao_dfc == ATIV
    assert not RegistroAuditoria.objects.filter(acao="conta.classificacao_dfc_alterada").exists()


def test_patch_responde_400_para_corpo_malformado_nunca_500(client):
    """R3 (auditoria DL-045) levada aos três campos: corpo que não é `Mapping`
    e valor que não é `str`/`bool` recusam com 400 antes de tocar em qualquer
    regra."""
    empresa, contas, gestor, caixa, receita = _cenario("patch-400")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-patch-400")

    corpo_lista = client.patch(
        _url_da_classificacao(empresa, receita),
        data=["classificacao_dfc"],
        content_type="application/json",
    )
    valor_dict = client.patch(
        _url_da_classificacao(empresa, receita),
        data={"classificacao_dfc": {"a": 1}},
        content_type="application/json",
    )
    booleano_cru = client.patch(
        _url_da_classificacao(empresa, receita),
        data={"item_de_resultado_sem_caixa": "talvez"},
        content_type="application/json",
    )

    assert corpo_lista.status_code == 400
    assert valor_dict.status_code == 400
    assert booleano_cru.status_code == 400


def test_patch_recusa_chave_fora_do_contrato_por_nome(client):
    """A política recusa chave desconhecida por NOME: um corpo com
    `classificacao_dmpl` neste PATCH não pode ser aplicado à classificação
    errada em silêncio."""
    empresa, contas, gestor, caixa, receita = _cenario("patch-contrato")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-patch-contrato")

    resposta = client.patch(
        _url_da_classificacao(empresa, receita),
        data={"classificacao_dmpl": "capital_social"},
        content_type="application/json",
    )

    assert resposta.status_code == 400


def test_patch_recusa_caixa_e_atividade_na_mesma_conta(client):
    """A coerência vem de `Conta.clean()` (uma fonte só): a porta não pode
    gravar o par que a apuração trata como papel duplo."""
    empresa, contas, gestor, caixa, receita = _cenario("patch-coerencia")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-patch-coerencia")

    resposta = client.patch(
        _url_da_classificacao(empresa, caixa),
        data={"caixa_e_equivalentes": True, "classificacao_dfc": ATIV},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    caixa.refresh_from_db()
    assert caixa.classificacao_dfc is None


def test_patch_e_isolado_por_empresa(client):
    """Conta de OUTRA empresa é 404 — a consulta é sempre `filter(empresa=
    empresa)`, e a guarda de período fechado nem chega a disparar."""
    empresa, contas, gestor, caixa, receita = _cenario("patch-iso")
    outra = _base._empresa("Empresa alheia do PATCH")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-patch-iso")

    resposta = client.patch(
        _url_da_classificacao(outra, receita),
        data={"classificacao_dfc": INVEST},
        content_type="application/json",
    )

    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# A3 (MÉDIO) da auditoria da etapa 2 — as permissões das portas novas, MEDIDAS
# ---------------------------------------------------------------------------


def test_a3_o_get_da_dfc_nao_e_de_cliente(client):
    """A3: os docstrings afirmavam a permissão sem medição — a mutação que
    zera `permission_classes` derrubava zero testes. CLIENTE nunca lê a
    contabilidade (`PodeLerContabilidade`), e este teste mata essa mutação."""
    empresa, contas, gestor, caixa, receita = _cenario("perm-get")
    _dlpa._autenticar(client, empresa.escritorio, username="cliente-get", papel=Papel.CLIENTE)

    resposta = client.get(_url_da_dfc(empresa))

    assert resposta.status_code == 403


def test_a3_o_patch_da_classificacao_nao_e_de_cliente(client):
    """CLIENTE também não escreve (`PodeEscriturar`) — e nada pode ser
    gravado por esta porta sem o papel de quem escritura."""
    empresa, contas, gestor, caixa, receita = _cenario("perm-patch")
    _dlpa._autenticar(client, empresa.escritorio, username="cliente-patch", papel=Papel.CLIENTE)

    resposta = client.patch(
        _url_da_classificacao(empresa, receita),
        data={"classificacao_dfc": INVEST},
        content_type="application/json",
    )

    assert resposta.status_code == 403
    receita.refresh_from_db()
    assert receita.classificacao_dfc == ATIV
    assert not RegistroAuditoria.objects.filter(acao="conta.classificacao_dfc_alterada").exists()


# ---------------------------------------------------------------------------
# A5 (MÉDIO) da auditoria da etapa 2 — dado enviado nunca é descartado em
# silêncio (BL-196)
# ---------------------------------------------------------------------------


def test_a5_os_campos_da_dfc_no_cadastro_sao_recusados_nunca_descartados(client):
    """A5/BL-196: dado enviado nunca é descartado em silêncio. A recusa aqui
    vem da PRIMEIRA porta — o contrato de requisição do cadastro
    (`CONTRATO_POST_CONTA`), que recusa a chave desconhecida por NOME com 400
    e lista os campos aceitos. A segunda porta é a recusa no próprio
    `ContaSerializer` (que além de nomear aponta o PATCH da classificação),
    defesa em profundidade para quando uma rota futura aceitar o corpo sem
    contrato. O que NÃO pode acontecer é o campo chegar, ser descartado e a
    conta gravar sem ele — por isso o assert de que nada foi criado."""
    empresa, contas, gestor, caixa, receita = _cenario("post-dfc")
    _dlpa._autenticar(client, empresa.escritorio, username="gestor-post-dfc")

    resposta = client.post(
        reverse("contabilidade:contas", args=[empresa.id]),
        data={
            "codigo": "9.9",
            "nome": "Conta Nova do Teste",
            "tipo": "ativo",
            "natureza": "devedora",
            "classificacao_dfc": "operacional",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 400
    corpo = str(resposta.json())
    assert "classificacao_dfc" in corpo, "a chave recusada é nomeada"
    assert not Conta.objects.filter(empresa=empresa, codigo="9.9").exists(), (
        "nada pode ser gravado quando a chave é recusada"
    )
