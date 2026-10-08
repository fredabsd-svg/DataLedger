"""DL-060 (achado H1 da auditoria da DL-054) — a reabertura em cascata
confirma EXATAMENTE os meses que a pessoa viu.

Antes: a tela mostrava "02/2026 e 03/2026", mas o POST só dizia "confirmo a
cascata". Se outra pessoa encerrasse abril entre a tela e o clique, abril era
reaberto junto, sem ter constado da confirmação (mês encerrado, possivelmente
já pago ou entregue, reaberto sem consentimento). Agora:

* a tela envia, em campo oculto, os meses que mostrou (`meses_confirmados`,
  `AAAA-MM,AAAA-MM`); a API exige `meses_confirmados` (lista de `{ano, mes}`)
  junto de `cascata: true`;
* o serviço compara esse conjunto com o dos encerrados posteriores lido SOB
  LOCK; divergência, a mais OU a menos, é 409 com a lista atual e nada muda;
* sem a lista (API) ou com lista malformada, 400.

Dados 100% sintéticos, datas em 2026, no passado.
"""

# ruff: noqa: F811
# (a fixture `cenario` importada é usada como parâmetro, o padrão do repositório)
import json
import time

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.livro_caixa.models import EstadoMesCaixa, FechamentoMesCaixa
from apps.livro_caixa.services import (
    FechamentoMesCaixaInvalido,
    ReaberturaExigeCascata,
    encerrar_mes_caixa,
    reabrir_mes_caixa,
    reabrir_mes_caixa_em_cascata,
)
from apps.livro_caixa.tests.test_dl053_fechamento_do_mes import (
    _PAUSA_CURTA,
    _cenario_commitado,
    _esperar,
    _pausando,
    _rodar_em_thread,
)
from apps.livro_caixa.tests.test_dl054_tela_cascata import (  # noqa: F401
    _MOTIVO,
    _cliente,
    _encerrar,
    _estados,
    _fotografia,
    _mensagens,
    _post_reabrir,
    _texto,
    _url,
    cenario,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

_ENCERRADOS = {1: "encerrado", 2: "encerrado", 3: "encerrado"}


def _gestor(cenario):
    return _cliente(Papel.GESTOR, cenario["escritorio_a"])


def _abrir_a_tela(cliente, cenario, mes=1):
    """GET da tela de reabertura; devolve o texto e o valor do campo oculto."""
    resposta = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=mes))
    assert resposta.status_code == 200
    return _texto(resposta)


def _post_da_tela(cliente, cenario, valor, *, mes=1, **extra):
    """O POST que o navegador enviaria: a caixa marcada e o campo oculto com o
    `valor` que a tela mostrou ao ser aberta."""
    return _post_reabrir(cliente, cenario, mes=mes, meses_confirmados=valor, **extra)


# ---------------------------------------------------------------------------
# A tela mostra o que será reaberto E envia o que mostrou
# ---------------------------------------------------------------------------


def test_a_tela_envia_em_campo_oculto_exatamente_os_meses_que_mostra(cenario):
    _encerrar(cenario, 1, 2, 3)
    _encerrar(cenario, 12, ano=2025)  # outro ano: não entra
    texto = _abrir_a_tela(_gestor(cenario), cenario)

    assert '<input type="hidden" name="meses_confirmados" value="2026-02,2026-03">' in texto
    assert "<strong>02/2026</strong> — encerrado" in texto
    assert "<strong>03/2026</strong> — encerrado" in texto


def test_sem_posteriores_a_tela_nao_oferece_cascata_nem_campo_oculto(cenario):
    _encerrar(cenario, 1)
    texto = _abrir_a_tela(_gestor(cenario), cenario)

    assert "meses_confirmados" not in texto
    assert "confirmar_cascata" not in texto


# ---------------------------------------------------------------------------
# Critério 1 — H1 pela tela: mês encerrado ENTRE o GET e o POST
# ---------------------------------------------------------------------------


def test_h1_mes_encerrado_entre_a_tela_e_o_clique_nao_e_reaberto_junto(cenario):
    _encerrar(cenario, 1, 2, 3)
    cliente = _gestor(cenario)
    texto_aberto = _abrir_a_tela(cliente, cenario)
    assert 'name="meses_confirmados" value="2026-02,2026-03"' in texto_aberto
    assert "04/2026" not in texto_aberto

    _encerrar(cenario, 4)  # outra pessoa, depois de a tela ser aberta
    antes = _fotografia(cenario["empresa"])

    resposta = _post_da_tela(cliente, cenario, "2026-02,2026-03", motivo="Motivo que não some")

    assert resposta.status_code == 409  # conflito de ESTADO, nunca 500
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == {**_ENCERRADOS, 4: "encerrado"}
    assert not RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").exists()
    mensagem = _mensagens(resposta)
    assert "Nada foi alterado" in mensagem
    assert "04/2026" in mensagem
    assert "confirme de novo" in mensagem
    # O formulário volta com a lista ATUAL, a caixa desmarcada e o motivo.
    texto = _texto(resposta)
    assert 'name="meses_confirmados" value="2026-02,2026-03,2026-04"' in texto
    assert "<strong>04/2026</strong> — encerrado" in texto
    assert 'name="confirmar_cascata" value="1" required' in texto
    assert "checked" not in texto.split('name="confirmar_cascata"')[1].split(">")[0]
    assert "Motivo que não some" in texto

    # Confirmando a lista nova, reabre exatamente os quatro.
    resposta = _post_da_tela(cliente, cenario, "2026-02,2026-03,2026-04")
    assert resposta.status_code == 302
    assert _estados(cenario) == {1: "aberto", 2: "aberto", 3: "aberto", 4: "aberto"}


def test_mes_anterior_encerrado_depois_da_tela_nao_faz_a_lista_divergir(cenario):
    """Mês ANTERIOR ao reaberto não entra na lista (não depende dele): encerrá-lo
    depois de a tela ser aberta não invalida a confirmação."""
    _encerrar(cenario, 2, 3)
    cliente = _gestor(cenario)
    texto = _abrir_a_tela(cliente, cenario, mes=2)
    assert 'name="meses_confirmados" value="2026-03"' in texto
    _encerrar(cenario, 1)  # anterior: irrelevante
    resposta = _post_da_tela(cliente, cenario, "2026-03", mes=2)
    assert resposta.status_code == 302
    assert _estados(cenario) == {1: "encerrado", 2: "aberto", 3: "aberto"}


# ---------------------------------------------------------------------------
# Critério 1 — lista a MENOS: um mês mostrado foi reaberto por outra pessoa
# ---------------------------------------------------------------------------


def test_mes_mostrado_reaberto_por_outra_pessoa_diverge_e_nada_e_alterado(cenario):
    _encerrar(cenario, 1, 2, 3)
    cliente = _gestor(cenario)
    _abrir_a_tela(cliente, cenario)
    reabrir_mes_caixa(
        empresa=cenario["empresa"],
        ano=2026,
        mes=3,
        usuario=cenario["autor"],
        motivo="Outra pessoa reabriu março",
    )
    antes = _fotografia(cenario["empresa"])

    resposta = _post_da_tela(cliente, cenario, "2026-02,2026-03")

    assert resposta.status_code == 409
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == {1: "encerrado", 2: "encerrado", 3: "aberto"}
    texto = _texto(resposta)
    assert 'name="meses_confirmados" value="2026-02"' in texto
    assert "03/2026" not in texto.split('name="meses_confirmados"')[1].split(">")[0]
    assert "Nada foi alterado" in _mensagens(resposta)


def test_todos_os_posteriores_reabertos_devolve_o_formulario_simples_com_409(cenario):
    _encerrar(cenario, 1, 2)
    cliente = _gestor(cenario)
    _abrir_a_tela(cliente, cenario)
    reabrir_mes_caixa(
        empresa=cenario["empresa"], ano=2026, mes=2, usuario=cenario["autor"], motivo="Outra"
    )
    antes = _fotografia(cenario["empresa"])

    resposta = _post_da_tela(cliente, cenario, "2026-02")

    assert resposta.status_code == 409
    assert _fotografia(cenario["empresa"]) == antes
    texto = _texto(resposta)
    assert "meses_confirmados" not in texto  # agora é reabertura simples
    assert "Reabrir mês 01/2026" in texto
    assert "Agora: nenhum mês." in _mensagens(resposta)


# ---------------------------------------------------------------------------
# Critério 1 — lista exata: reabre exatamente os mostrados
# ---------------------------------------------------------------------------


def test_lista_exata_reabre_exatamente_os_mostrados_e_so_eles(cenario):
    _encerrar(cenario, 1, 2, 3, 5)  # abril aberto fica como está
    _encerrar(cenario, 1, ano=2027)  # outro ano não entra
    cliente = _gestor(cenario)
    _abrir_a_tela(cliente, cenario)

    resposta = _post_da_tela(cliente, cenario, "2026-02,2026-03,2026-05")

    assert resposta.status_code == 302
    assert _estados(cenario) == {1: "aberto", 2: "aberto", 3: "aberto", 5: "aberto"}
    assert FechamentoMesCaixa.objects.get(empresa=cenario["empresa"], ano=2027, mes=1).estado == (
        EstadoMesCaixa.ENCERRADO
    )
    assert RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").count() == 4


def test_a_ordem_dos_meses_no_campo_nao_muda_o_conjunto(cenario):
    """O que se confirma é um CONJUNTO: a ordem em que a lista chega não conta."""
    _encerrar(cenario, 1, 2, 3)
    resposta = _post_da_tela(_gestor(cenario), cenario, "2026-03,2026-02")
    assert resposta.status_code == 302
    assert _estados(cenario) == {1: "aberto", 2: "aberto", 3: "aberto"}


# ---------------------------------------------------------------------------
# Contrato do POST da tela: campo novo permitido; o resto continua recusado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor",
    [
        "2026-13",  # mês inexistente
        "2026-00",
        "2026-2",  # sem zero à esquerda
        "26-02",
        "abc",
        "2026/02",
        "2026-02,",  # item vazio
        ",2026-02",
        "2026-02,,2026-03",
        "2026-02,2026-02",  # repetido
        " 2026-02",  # espaço
        "2026-02, 2026-03",
        "2026-02;2026-03",
        "２０２６-02",  # dígitos Unicode de largura inteira
        "0000-01",  # ano fora da faixa da API (1970 a 2999): adulteração, não divergência
        "9999-12",
        "1969-12",
        "3000-01",
        "2026-02\n",
    ],
)
def test_campo_oculto_malformado_da_400_e_nao_altera_nada(cenario, valor):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])

    resposta = _post_da_tela(_gestor(cenario), cenario, valor)

    assert resposta.status_code == 400
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == _ENCERRADOS
    assert "Nada foi alterado" in _mensagens(resposta)
    # Volta ao formulário com a lista atual, para confirmar de novo.
    assert 'name="meses_confirmados" value="2026-02,2026-03"' in _texto(resposta)


def test_cascata_confirmada_sem_o_campo_oculto_da_400_e_nao_altera_nada(cenario):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])
    cliente = _gestor(cenario)

    resposta = cliente.post(
        _url("mes_reabrir", cenario["empresa"]),
        {"ano": "2026", "mes": "1", "motivo": _MOTIVO, "confirmar_cascata": "1"},
    )

    assert resposta.status_code == 400
    assert _fotografia(cenario["empresa"]) == antes


def test_campo_oculto_sem_a_caixa_marcada_nao_confirma_a_cascata(cenario):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])

    resposta = _post_reabrir(
        _gestor(cenario), cenario, cascata=False, meses_confirmados="2026-02,2026-03"
    )

    assert resposta.status_code == 409
    assert "não pode ser reaberto sozinho" in _mensagens(resposta)
    assert _fotografia(cenario["empresa"]) == antes


def test_a_tela_continua_recusando_qualquer_outro_campo_extra(cenario):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _post_da_tela(_gestor(cenario), cenario, "2026-02", meses="2026-02,2026-03")

    assert resposta.status_code == 302  # recusa do dado não contratado, volta ao painel
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == {1: "encerrado", 2: "encerrado"}


@pytest.mark.parametrize(
    "papel", [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE]
)
def test_quem_nao_fecha_mes_continua_com_403_mesmo_com_a_lista_certa(cenario, papel):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _post_da_tela(_cliente(papel, cenario["escritorio_a"]), cenario, "2026-02")

    assert resposta.status_code == 403
    assert _fotografia(cenario["empresa"]) == antes


# ---------------------------------------------------------------------------
# API — critério 2
# ---------------------------------------------------------------------------


def _api(cliente, cenario, corpo, mes=1):
    return cliente.post(
        reverse("livro_caixa:reabrir-mes", args=[cenario["empresa"].id, 2026, mes]),
        data=json.dumps(corpo),
        content_type="application/json",
    )


def _meses(*meses, ano=2026):
    return [{"ano": ano, "mes": mes} for mes in meses]


def _corpo(meses_confirmados, **extra):
    return {"motivo": _MOTIVO, "cascata": True, "meses_confirmados": meses_confirmados, **extra}


def test_h1_api_mes_encerrado_depois_da_consulta_da_409_com_a_lista_atual(cenario):
    _encerrar(cenario, 1, 2, 3)
    cliente = _gestor(cenario)
    _encerrar(cenario, 4)  # depois de o cliente da API ter visto [2, 3]
    antes = _fotografia(cenario["empresa"])

    resposta = _api(cliente, cenario, _corpo(_meses(2, 3)))

    assert resposta.status_code == 409, resposta.content
    assert resposta.json()["meses_encerrados_posteriores"] == _meses(2, 3, 4)
    assert "04/2026" in resposta.json()["detail"]
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == {**_ENCERRADOS, 4: "encerrado"}


def test_api_mes_reaberto_por_outra_pessoa_da_409_com_a_lista_atual(cenario):
    _encerrar(cenario, 1, 2, 3)
    cliente = _gestor(cenario)
    reabrir_mes_caixa(
        empresa=cenario["empresa"], ano=2026, mes=3, usuario=cenario["autor"], motivo="Outra"
    )
    antes = _fotografia(cenario["empresa"])

    resposta = _api(cliente, cenario, _corpo(_meses(2, 3)))

    assert resposta.status_code == 409, resposta.content
    assert resposta.json()["meses_encerrados_posteriores"] == _meses(2)
    assert _fotografia(cenario["empresa"]) == antes


def test_api_lista_exata_reabre_e_a_ordem_nao_importa(cenario):
    _encerrar(cenario, 1, 2, 3)

    resposta = _api(_gestor(cenario), cenario, _corpo(_meses(3, 2)))

    assert resposta.status_code == 200, resposta.content
    assert [m["mes"] for m in resposta.json()["meses_reabertos"]] == [1, 2, 3]
    assert _estados(cenario) == {1: "aberto", 2: "aberto", 3: "aberto"}


def test_api_lista_vazia_confirma_que_nao_ha_posteriores(cenario):
    _encerrar(cenario, 1)
    resposta = _api(_gestor(cenario), cenario, _corpo([]))
    assert resposta.status_code == 200, resposta.content
    assert _estados(cenario) == {1: "aberto"}


def test_api_lista_vazia_com_posteriores_encerrados_da_409(cenario):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, _corpo([]))

    assert resposta.status_code == 409
    assert resposta.json()["meses_encerrados_posteriores"] == _meses(2)
    assert _fotografia(cenario["empresa"]) == antes


def test_api_lista_com_mes_aberto_a_mais_da_409(cenario):
    """Confirmar março, que está ABERTO, também diverge (lista a mais)."""
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, _corpo(_meses(2, 3)))

    assert resposta.status_code == 409
    assert resposta.json()["meses_encerrados_posteriores"] == _meses(2)
    assert _fotografia(cenario["empresa"]) == antes


def test_api_lista_de_outro_ano_nao_confirma_os_meses_do_ano_pedido(cenario):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, _corpo(_meses(2, ano=2025)))

    assert resposta.status_code == 409
    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize(
    ("mes_pedido", "confirmados"),
    [
        (1, _meses(1, 2)),  # o próprio mês pedido não é "posterior"
        (1, _meses(1)),
        (2, _meses(1, 3)),  # mês anterior ao pedido, no mesmo ano
        (2, _meses(12, ano=2025) + _meses(3)),  # anterior, na virada do ano
        (1, _meses(2) + _meses(2, ano=2027)),  # mesmo mês em outro ano
        (1, _meses(1, 2, 3)),  # lista certa (2 e 3) mais o próprio mês pedido
    ],
    ids=[
        "proprio_mes_e_posterior",
        "so_o_proprio_mes",
        "anterior_do_ano",
        "anterior_2025",
        "ano_2027",
        "lista_certa_mais_proprio_mes",
    ],
)
def test_api_lista_forjada_com_proprio_mes_ou_anterior_da_409_e_nao_altera_nada(
    cenario, mes_pedido, confirmados
):
    """A comparação é de IGUALDADE com os encerrados posteriores: nem o mês
    pedido nem um anterior a ele podem entrar na lista confirmada."""
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, _corpo(confirmados), mes=mes_pedido)

    assert resposta.status_code == 409, resposta.content
    esperado = _meses(2, 3) if mes_pedido == 1 else _meses(3)
    assert resposta.json()["meses_encerrados_posteriores"] == esperado
    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize(
    "item",
    [
        {"ano": 10**40, "mes": 2},
        {"ano": 2026, "mes": 10**40},
        {"ano": 2**70, "mes": 2**70},
        {"ano": -1, "mes": 2},
        {"ano": 2026, "mes": -1},
    ],
    ids=repr,
)
def test_api_inteiro_gigante_ou_negativo_da_400_sem_500_e_nao_altera_nada(cenario, item):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, _corpo([item]))

    assert resposta.status_code == 400, resposta.content
    assert _fotografia(cenario["empresa"]) == antes


def test_api_cascata_sem_meses_confirmados_da_400_e_nao_altera_nada(cenario):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, {"motivo": _MOTIVO, "cascata": True})

    assert resposta.status_code == 400
    assert "meses_confirmados" in json.dumps(resposta.json())
    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize(
    "malformado",
    [
        None,
        "2026-02",
        5,
        {"ano": 2026, "mes": 2},
        [2],
        ["2026-02"],
        [[2026, 2]],
        [{"ano": 2026}],
        [{"mes": 2}],
        [{"ano": 2026, "mes": 2, "extra": 1}],
        [{"ano": "2026", "mes": 2}],
        [{"ano": 2026, "mes": "2"}],
        [{"ano": 2026.0, "mes": 2}],
        [{"ano": 2026, "mes": True}],
        [{"ano": True, "mes": 2}],
        [{"ano": 2026, "mes": None}],
        [{"ano": 2026, "mes": 0}],
        [{"ano": 2026, "mes": 13}],
        [{"ano": 1969, "mes": 2}],
        [{"ano": 3000, "mes": 2}],
        [{"ano": 2026, "mes": 2}, {"ano": 2026, "mes": 2}],  # repetido
        [{"ano": 2026, "mes": 2}, "x"],
    ],
    ids=repr,
)
def test_api_meses_confirmados_malformado_da_400_e_nao_altera_nada(cenario, malformado):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, _corpo(malformado))

    assert resposta.status_code == 400, resposta.content
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == _ENCERRADOS


@pytest.mark.parametrize("cascata", [False, None])
def test_api_meses_confirmados_sem_cascata_verdadeira_da_400(cenario, cascata):
    _encerrar(cenario, 1)
    antes = _fotografia(cenario["empresa"])
    corpo = {"motivo": _MOTIVO, "meses_confirmados": _meses(2)}
    if cascata is not None:
        corpo["cascata"] = cascata

    resposta = _api(_gestor(cenario), cenario, corpo)

    assert resposta.status_code == 400
    assert _fotografia(cenario["empresa"]) == antes


def test_api_reabertura_simples_continua_igual_sem_o_campo(cenario):
    _encerrar(cenario, 1)
    resposta = _api(_gestor(cenario), cenario, {"motivo": _MOTIVO})
    assert resposta.status_code == 200
    assert _estados(cenario) == {1: "aberto"}


def test_api_continua_recusando_campo_nao_contratado(cenario):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_gestor(cenario), cenario, _corpo(_meses(2), meses=[2]))

    assert resposta.status_code == 400
    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize(
    "papel", [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE]
)
def test_api_quem_nao_fecha_mes_continua_com_403_com_a_lista_certa(cenario, papel):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _api(_cliente(papel, cenario["escritorio_a"]), cenario, _corpo(_meses(2)))

    assert resposta.status_code == 403
    assert _fotografia(cenario["empresa"]) == antes


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------


def _cascata_do_servico(cenario, meses_confirmados, mes=1):
    return reabrir_mes_caixa_em_cascata(
        empresa=cenario["empresa"],
        ano=2026,
        mes=mes,
        usuario=cenario["autor"],
        motivo=_MOTIVO,
        meses_confirmados=meses_confirmados,
    )


def test_servico_exige_o_argumento_meses_confirmados(cenario):
    _encerrar(cenario, 1, 2)
    with pytest.raises(TypeError):
        reabrir_mes_caixa_em_cascata(
            empresa=cenario["empresa"], ano=2026, mes=1, usuario=cenario["autor"], motivo=_MOTIVO
        )


def test_servico_divergencia_levanta_a_excecao_com_a_lista_atual_e_nada_muda(cenario):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(ReaberturaExigeCascata) as erro:
        _cascata_do_servico(cenario, {(2026, 2)})

    assert erro.value.ano == 2026
    assert erro.value.meses == (2, 3)
    mensagem = str(erro.value)
    assert "Confirmado: 02/2026." in mensagem
    assert "Agora: 02/2026, 03/2026." in mensagem
    assert "03/2026" in mensagem and "Nada foi alterado" in mensagem
    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize(
    "malformado",
    [
        "2026-02",
        None,
        [2],
        [(2026,)],
        [(2026, 2, 1)],
        [("2026", 2)],
        [(2026, True)],
        [(2026.0, 2)],
        [(2026, None)],
    ],
    ids=repr,
)
def test_servico_meses_confirmados_malformado_e_erro_de_entrada_e_nao_muda_nada(
    cenario, malformado
):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(FechamentoMesCaixaInvalido):
        _cascata_do_servico(cenario, malformado)

    assert _fotografia(cenario["empresa"]) == antes


def test_servico_aceita_lista_e_tupla_alem_de_conjunto(cenario):
    _encerrar(cenario, 1, 2, 3, 4)
    _cascata_do_servico(cenario, [(2026, 2), (2026, 3), (2026, 4)])
    assert _estados(cenario) == {1: "aberto", 2: "aberto", 3: "aberto", 4: "aberto"}


# ---------------------------------------------------------------------------
# Concorrência — a comparação acontece DEPOIS dos locks (L1 da auditoria)
# ---------------------------------------------------------------------------
#
# Se a leitura dos encerrados posteriores e a comparação viessem ANTES de travar,
# uma operação concorrente ainda não comitada seria invisível e a cascata
# reabriria o mês que acabou de ser encerrado (o dano do H1 pela janela da
# corrida). Nos dois testes a operação concorrente segura o lock, a cascata
# chega durante a pausa e precisa ESPERAR; só depois de liberada ela lê o estado
# comitado, diverge e não altera nada.


@pytest.mark.django_db(transaction=True)
def test_encerramento_de_abril_em_andamento_faz_a_cascata_esperar_e_depois_divergir():
    c = _cenario_commitado()
    for mes in (1, 2, 3):
        encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=mes, usuario=c["gestor"])

    with _pausando("fechamento_mes_caixa.encerrado") as (dentro, liberar):
        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=4, usuario=c["gestor"])
        )
        assert dentro.wait(timeout=30), "o encerramento de abril nunca chegou à pausa"
        cascata, res_cascata = _rodar_em_thread(
            lambda: reabrir_mes_caixa_em_cascata(
                empresa=c["empresa"],
                ano=2026,
                mes=1,
                usuario=c["gestor"],
                motivo=_MOTIVO,
                meses_confirmados={(2026, 2), (2026, 3)},
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert cascata.is_alive(), "a cascata não esperou o encerramento de abril"
        liberar.set()
        _esperar(fechar, cascata)

    assert "erro" not in res_fechar, res_fechar
    assert isinstance(res_cascata.get("erro"), ReaberturaExigeCascata), res_cascata
    assert res_cascata["erro"].meses == (2, 3, 4)
    assert _estados(c, c["empresa"]) == {mes: "encerrado" for mes in (1, 2, 3, 4)}
    assert not RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").exists()


@pytest.mark.django_db(transaction=True)
def test_reabertura_de_marco_em_andamento_faz_a_cascata_esperar_e_depois_divergir_a_menos():
    c = _cenario_commitado()
    for mes in (1, 2, 3):
        encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=mes, usuario=c["gestor"])

    with _pausando("fechamento_mes_caixa.reaberto") as (dentro, liberar):
        simples, res_simples = _rodar_em_thread(
            lambda: reabrir_mes_caixa(
                empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"], motivo=_MOTIVO
            )
        )
        assert dentro.wait(timeout=30), "a reabertura de março nunca chegou à pausa"
        cascata, res_cascata = _rodar_em_thread(
            lambda: reabrir_mes_caixa_em_cascata(
                empresa=c["empresa"],
                ano=2026,
                mes=1,
                usuario=c["gestor"],
                motivo=_MOTIVO,
                meses_confirmados={(2026, 2), (2026, 3)},
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert cascata.is_alive(), "a cascata não esperou a reabertura de março"
        liberar.set()
        _esperar(simples, cascata)

    assert "erro" not in res_simples, res_simples
    assert isinstance(res_cascata.get("erro"), ReaberturaExigeCascata), res_cascata
    assert res_cascata["erro"].meses == (2,)
    assert _estados(c, c["empresa"]) == {1: "encerrado", 2: "encerrado", 3: "aberto"}
    # Só a reabertura simples de março deixou rastro; a cascata recusada, nenhum.
    trilha = RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto")
    assert [r.detalhes["mes"] for r in trilha] == [3]
