"""DL-078, correção da auditoria rodada 1, achados A2 e A7: a tela de escriturar.

A2: o motivo da recusa da nota (tpEmit 2 ou 3) aparece na tela E na lista, antes de qualquer outra
coisa; sem natureza escolhida, os botões ficam habilitados e o servidor recusa a natureza vazia com
mensagem; nota sem sugestão (tpRetISSQN 3) é escriturável pela tela, com a natureza no POST.

A7: o motivo mostrado na tela é o que o SERVIÇO devolveu para cada sinal do XML (a tela não repete
a ordem das regras em texto).

Relógio: o `autouse` abaixo fixa "hoje" (ver `DIA_DE_HOJE_NO_TESTE`), por consistência com a suíte.
"""

import re
from html import escape

import pytest
from django.urls import reverse

from apps.fiscal import tomadas as servico
from apps.fiscal import views_web
from apps.fiscal.models import EscrituracaoTomada, EstadoEscrituracao, NaturezaTomada
from apps.fiscal.tests.suporte_tomada_dl078 import (
    OUTRO_MUNICIPIO,
    PALMAS,
    T1,
    T2,
    T3,
    T5,
    T6,
    T7,
    receber_tomada,
    vinculo_tomador,
)
from apps.fiscal.tests.xml_tomada_dl078 import CPF_PRESTADOR_SINTETICO

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("relogio_do_teste")]

ANO, MES = 2026, 10


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _botao(html, acao):
    casamento = re.search(rf'<button [^>]*value="{acao}"[^>]*>', html)
    assert casamento, f"botão {acao!r} não encontrado na tela"
    return casamento.group(0)


def _desabilitado(html, acao):
    return " disabled" in _botao(html, acao)


def _url_escriturar(empresa, vinculo):
    return reverse("fiscal_web:tomada_escriturar", args=[empresa.pk, vinculo.pk])


def _url_lista(empresa):
    return reverse("fiscal_web:tomadas_lista") + f"?empresa={empresa.pk}&ano={ANO}&mes={MES}"


def test_tela_mostra_o_motivo_da_recusa_antes_de_qualquer_natureza(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    # tpEmit 2 e nenhuma natureza escolhida: a tela precisa dizer POR QUE não pode escriturar.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8301,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="10.00",
        v_liq="990.00",
        c_loc_incid=PALMAS,
        tp_emit="2",
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_escriturar(empresa_a2, vinculo))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert "emitida pelo tomador ou pelo intermediário (tpEmit 2 ou 3)" in html
    assert "Escolha a natureza da operação antes" not in html
    assert _desabilitado(html, "rascunho")
    assert _desabilitado(html, "efetivar")
    assert not EscrituracaoTomada.objects.filter(vinculo=vinculo).exists()


def test_lista_mostra_o_motivo_da_recusa_de_tpemit(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8302,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="10.00",
        v_liq="990.00",
        c_loc_incid=PALMAS,
        tp_emit="3",
    )
    _logar(client, usuario_gestor_a)

    html = client.get(_url_lista(empresa_a2)).content.decode()

    assert "(tpEmit 2 ou 3)" in html


def test_nota_com_tpretissqn_3_tem_botoes_habilitados_e_escritura_pelo_post(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    # tpRetISSQN 3 não tem sugestão de natureza. A tela não tem JavaScript: os botões precisam
    # estar habilitados, e a natureza vem no POST.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8303,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="3",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    html = client.get(_url_escriturar(empresa_a2, vinculo)).content.decode()
    assert not _desabilitado(html, "rascunho")
    assert not _desabilitado(html, "efetivar")

    resposta = client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": T6, "acao": "efetivar"},
    )

    assert resposta.status_code == 302
    escrituracao = EscrituracaoTomada.objects.get(vinculo=vinculo)
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA
    assert escrituracao.natureza == T6
    assert escrituracao.tp_ret_issqn == "3"


def test_sem_natureza_escolhida_os_botoes_ficam_habilitados_e_o_servidor_recusa_com_mensagem(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8304,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="3",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    html = client.get(_url_escriturar(empresa_a2, vinculo)).content.decode()
    assert not _desabilitado(html, "efetivar")
    assert "Efetivar indisponível" not in html

    recusada = client.post(
        _url_escriturar(empresa_a2, vinculo), {"natureza": "", "acao": "efetivar"}
    )
    assert recusada.status_code == 200
    assert "Escolha a natureza da operação." in recusada.content.decode()
    assert not EscrituracaoTomada.objects.filter(vinculo=vinculo).exists()


# A7: um XML para cada sinal da ordem de `sugerir_natureza_com_motivo`.
SINAIS = {
    "tpRetISSQN 2": dict(tp_ret_issqn="2", natureza=T1),
    "opSimpNac 2 (MEI)": dict(tp_ret_issqn="1", op_simp_nac="2", natureza=T5),
    "opSimpNac 3 (ME/EPP)": dict(tp_ret_issqn="1", op_simp_nac="3", natureza=T6),
    "prestador CPF": dict(
        tp_ret_issqn="1",
        prestador_tipo="CPF",
        prestador_documento=CPF_PRESTADOR_SINTETICO,
        federal=False,
        natureza=T7,
    ),
    "município diferente": dict(
        tp_ret_issqn="1", c_loc_incid=PALMAS, c_loc_prestacao=OUTRO_MUNICIPIO, natureza=T3
    ),
    "tpRetISSQN 1, sem outro sinal": dict(
        tp_ret_issqn="1", c_loc_incid=PALMAS, c_loc_prestacao=PALMAS, natureza=T2
    ),
}


@pytest.mark.parametrize("sinal", list(SINAIS), ids=list(SINAIS))
def test_motivo_da_tela_e_o_que_o_servico_devolveu_para_cada_sinal(
    client, escritorio_a, empresa_a2, usuario_gestor_a, sinal
):
    xml = dict(SINAIS[sinal])
    esperada = xml.pop("natureza")
    xml.setdefault("c_loc_incid", PALMAS)
    xml.setdefault("v_liq", "1000.00")
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8320 + list(SINAIS).index(sinal),
        tomador_documento=empresa_a2.cnpj,
        **xml,
    )
    sugestao = servico.sugerir_natureza_com_motivo(documento)
    assert sugestao.natureza == esperada
    assert sugestao.motivo, "sinal sem motivo: a tela ficaria sem a razão"
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    html = client.get(_url_escriturar(empresa_a2, vinculo)).content.decode()

    assert f"Porque {escape(sugestao.motivo)} A sugestão" in html
    assert f"Sugestão do XML: {NaturezaTomada(esperada).label}." in html


def test_sugerir_natureza_continua_devolvendo_so_a_natureza(
    escritorio_a, usuario_gestor_a, empresa_a2
):
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8350,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_liq="990.00",
        c_loc_incid=PALMAS,
    )

    assert servico.sugerir_natureza(documento) == T1
    assert servico.sugerir_natureza_com_motivo(documento).motivo.startswith(
        "o XML traz tpRetISSQN 2"
    )


def test_sem_sugestao_o_motivo_e_vazio(escritorio_a, usuario_gestor_a, empresa_a2):
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8351,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="3",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
    )

    sugestao = servico.sugerir_natureza_com_motivo(documento)
    assert sugestao.natureza is None
    assert sugestao.motivo == ""


def test_recusa_de_natureza_e_publica_e_a_tela_nao_repete_a_ordem():
    assert callable(servico.recusa_de_natureza)
    assert not hasattr(views_web, "_PORQUE_DA_SUGESTAO_TOMADA")
