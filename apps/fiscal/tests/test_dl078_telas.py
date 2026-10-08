"""DL-078 (frente B) — telas dos serviços TOMADOS: escriturar, estornar, data de pagamento,
ISS retido a recolher e retenções federais.

A regra é a da frente A (`apps.fiscal.tomadas` e `apps.fiscal.retencoes`). Aqui se prova que a
TELA mostra o que o serviço calcula, mostra a recusa sem gravar nada, e que a permissão e o
isolamento são verificados no SERVIDOR (AGENTS.md §11), e não só escondidos na interface.

- Dados 100% sintéticos (`suporte_tomada_dl078`, `xml_tomada_dl078`). Nenhum dado de cliente.
- Os valores esperados estão escritos À MÃO, com a aritmética de cada cenário. A tela não é a fonte
  do número: o teste compara o texto pt-BR com o que foi somado aqui.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
    NOMES_DE_TELA_DOS_SERVICOS_TOMADOS,
    assert_moldura_acessivel,
)
from apps.fiscal.models import EscrituracaoTomada, EstadoEscrituracao
from apps.fiscal.tests.suporte_tomada_dl078 import (
    PALMAS,
    T1,
    T2,
    T5,
    T6,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)
from apps.fiscal.tests.xml_tomada_dl078 import CPF_PRESTADOR_SINTETICO
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 10
TEXTO_DE_CONFERENCIA_DO_RETIDO = (
    "Conferência para a guia do ISS retido — o DataLedger não gera DAM nem transmite."
)


# ---------------------------------------------------------------------------
# Fábrica, URLs e leitura do HTML
# ---------------------------------------------------------------------------


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _botao(html, acao):
    """A tag `<button>` do formulário de escriturar que submete `acao` (rascunho ou efetivar)."""
    casamento = re.search(rf'<button [^>]*value="{acao}"[^>]*>', html)
    assert casamento, f"botão {acao!r} não encontrado na tela"
    return casamento.group(0)


def _desabilitado(html, acao):
    return " disabled" in _botao(html, acao)


def _url_lista(empresa, ano=ANO, mes=MES):
    return reverse("fiscal_web:tomadas_lista") + f"?empresa={empresa.pk}&ano={ano}&mes={mes}"


def _url_iss(empresa, ano=ANO, mes=MES):
    return (
        reverse("fiscal_web:iss_retido_a_recolher") + f"?empresa={empresa.pk}&ano={ano}&mes={mes}"
    )


def _url_federais(empresa, ano=ANO, mes=MES):
    return reverse("fiscal_web:retencoes_federais") + f"?empresa={empresa.pk}&ano={ano}&mes={mes}"


def _url_escriturar(empresa, vinculo):
    return reverse("fiscal_web:tomada_escriturar", args=[empresa.pk, vinculo.pk])


def _url_estornar(empresa, escrituracao):
    return reverse("fiscal_web:tomada_estornar", args=[empresa.pk, escrituracao.pk])


def _url_pagamento(empresa, escrituracao):
    return reverse("fiscal_web:tomada_data_pagamento", args=[empresa.pk, escrituracao.pk])


@pytest.fixture
def paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl078-telas")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-dl078-telas")


@pytest.fixture
def cenario(escritorio_a, usuario_gestor_a, empresa_a2):
    """Competência 10/2026 da tomadora de Palmas, com ISS retido e um caso a escriturar.

    ISS retido a recolher em Palmas: 50,00 (T1) + 7,00 (T6, Simples, item 0) = 57,00.
    Fora do total: a nota T1 sem vISSQN (vai para conferir, nunca como zero) e a nota a escriturar.
    """
    c = {}
    c["t1"] = tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9301,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_liq="950.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-05",
    )
    c["t6"] = tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9302,
        T6,
        tp_ret_issqn="2",
        v_iss_qn="7.00",
        v_liq="993.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-07",
        op_simp_nac="3",
    )
    c["t1_sem_valor"] = tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9303,
        T1,
        tp_ret_issqn="2",
        v_liq="1000.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-10",
    )
    c["a_escriturar"] = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9304,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="1",
        c_loc_incid=PALMAS,
        c_loc_prestacao=PALMAS,
        d_compet="2026-10-08",
    )
    return c


@pytest.fixture
def cenario_federal(escritorio_a, usuario_gestor_a, empresa_a2):
    """Uma nota T1 efetivada com IRRF (15,00) e CSRF (20,00) e SEM data de pagamento: pendente.

    vLiq = 1000,00 − (15,00 + 20,00 + 30,00) = 935,00, para não disparar o aviso A1.
    """
    return tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        9311,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="30.00",
        v_liq="935.00",
        v_ret_irrf="15.00",
        v_ret_csll="20.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-09",
    )


# ---------------------------------------------------------------------------
# Permissão e isolamento
# ---------------------------------------------------------------------------


def test_cliente_e_recusado_nas_telas_de_tomadas(client, cenario, empresa_a2, usuario_cliente_a):
    vinculo = vinculo_tomador(cenario["a_escriturar"], empresa_a2)
    _logar(client, usuario_cliente_a)

    assert client.get(_url_lista(empresa_a2)).status_code == 403
    assert client.get(_url_iss(empresa_a2)).status_code == 403
    assert client.get(_url_federais(empresa_a2)).status_code == 403
    assert client.get(_url_escriturar(empresa_a2, vinculo)).status_code == 403
    assert (
        client.post(
            _url_escriturar(empresa_a2, vinculo),
            {"natureza": T2, "acao": "efetivar"},
        ).status_code
        == 403
    )
    assert EscrituracaoTomada.objects.filter(estado=EstadoEscrituracao.EFETIVADA).count() == 3


def test_paralegal_le_as_telas_e_nao_escreve(client, cenario, empresa_a2, paralegal_a):
    vinculo = vinculo_tomador(cenario["a_escriturar"], empresa_a2)
    _logar(client, paralegal_a)

    lista = client.get(_url_lista(empresa_a2))
    assert lista.status_code == 200
    # Quem só consulta não tem o botão de escriturar: o link nem aparece na tela.
    assert _url_escriturar(empresa_a2, vinculo) not in lista.content.decode()
    assert client.get(_url_iss(empresa_a2)).status_code == 200
    assert client.get(_url_federais(empresa_a2)).status_code == 200

    assert client.get(_url_escriturar(empresa_a2, vinculo)).status_code == 403
    assert (
        client.post(
            _url_escriturar(empresa_a2, vinculo),
            {"natureza": T2, "acao": "efetivar"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            _url_escriturar(empresa_a2, vinculo),
            {"natureza": T2, "acao": "rascunho"},
        ).status_code
        == 403
    )
    # Nada foi gravado pelas tentativas: a nota continua a escriturar.
    assert not EscrituracaoTomada.objects.filter(vinculo=vinculo).exists()


def test_outro_escritorio_e_outra_empresa_recebem_404(
    client, cenario, empresa_a2, empresa_a, empresa_b, usuario_gestor_a, gestor_b
):
    vinculo = vinculo_tomador(cenario["a_escriturar"], empresa_a2)
    escrituracao = cenario["t1"]

    _logar(client, gestor_b)
    assert client.get(_url_lista(empresa_a2)).status_code == 404
    assert client.get(_url_iss(empresa_a2)).status_code == 404
    assert client.get(_url_federais(empresa_a2)).status_code == 404
    assert client.get(_url_escriturar(empresa_a2, vinculo)).status_code == 404

    _logar(client, usuario_gestor_a)
    # Empresa de OUTRO escritório no caminho e no filtro: 404, nunca a lista da outra empresa.
    assert client.get(_url_lista(empresa_b)).status_code == 404
    assert client.get(_url_iss(empresa_b)).status_code == 404
    assert client.get(_url_escriturar(empresa_b, vinculo)).status_code == 404
    # Vínculo de OUTRA empresa do mesmo escritório, pelo caminho de empresa_a: 404.
    assert client.get(_url_escriturar(empresa_a, vinculo)).status_code == 404
    assert client.get(_url_estornar(empresa_a, escrituracao)).status_code == 404
    assert client.get(_url_pagamento(empresa_a, escrituracao)).status_code == 404
    assert (
        client.post(
            _url_escriturar(empresa_a, vinculo),
            {"natureza": T2, "acao": "efetivar"},
        ).status_code
        == 404
    )
    assert EscrituracaoTomada.objects.filter(vinculo=vinculo).count() == 0


@pytest.mark.parametrize(
    "nome_rota",
    [
        "fiscal_web:tomadas_lista",
        "fiscal_web:iss_retido_a_recolher",
        "fiscal_web:retencoes_federais",
    ],
)
def test_anonimo_e_redirecionado_ao_login(client, nome_rota):
    resposta = client.get(reverse(nome_rota))

    assert resposta.status_code == 302
    assert "login" in resposta["Location"]


def test_menu_e_home_do_fiscal_mostram_servicos_tomados(
    client, empresa_a2, usuario_gestor_a, usuario_cliente_a
):
    _logar(client, usuario_gestor_a)
    html = client.get(reverse("tenancy:painel")).content.decode()
    assert "Serviços tomados" in html
    assert reverse("fiscal_web:tomadas_lista") in html
    assert reverse("fiscal_web:iss_retido_a_recolher") in html
    assert reverse("fiscal_web:retencoes_federais") in html

    resposta = client.get(reverse("module_home:home", args=["fiscal"]))
    atalhos = resposta.context["home"]["atalhos"]
    assert any(
        atalho["rotulo"] == "Serviços tomados"
        and atalho["url"].startswith(reverse("fiscal_web:tomadas_lista"))
        for atalho in atalhos
    )

    _logar(client, usuario_cliente_a)
    assert (
        reverse("fiscal_web:tomadas_lista")
        not in client.get(reverse("tenancy:painel")).content.decode()
    )


# ---------------------------------------------------------------------------
# Serviços tomados do mês — lista (arquétipo A)
# ---------------------------------------------------------------------------


def test_tela_tomadas_lista_e_acessivel(client, cenario, empresa_a2, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(empresa_a2))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert_moldura_acessivel(html)
    assert "Prestadora Sintética Ltda" in html
    # Valor de serviço de 1000,00 em pt-BR (milhar com ponto, decimal com vírgula).
    assert "1.000,00" in html
    # Escriturada: natureza GRAVADA. Não escriturada: natureza SUGERIDA pelo XML, dito assim.
    assert "Tomado — ISS retido pelo cliente tomador (T1)" in html
    assert "Escriturada" in html
    assert "Sugerida pelo XML, não escriturada" in html
    assert "A escriturar" in html


def test_tela_tomadas_lista_sem_empresa_pede_a_escolha(
    client, cenario, empresa_b, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(reverse("fiscal_web:tomadas_lista"))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert "Escolha uma empresa para ver os serviços tomados." in html
    assert "Prestadora Sintética Ltda" not in html
    # Empresa de OUTRO escritório não aparece na escolha nem em nenhum rótulo.
    assert empresa_b.razao_social not in html


# ---------------------------------------------------------------------------
# Escriturar uma nota tomada (arquétipo B)
# ---------------------------------------------------------------------------


def test_tela_escriturar_tomada_e_acessivel(client, cenario, empresa_a2, usuario_gestor_a):
    vinculo = vinculo_tomador(cenario["a_escriturar"], empresa_a2)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_escriturar(empresa_a2, vinculo))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert_moldura_acessivel(html)
    # A sugestão aparece DESTACADA, com o porquê (o sinal do XML que a produziu).
    assert "Sugestão do XML: Tomado — ISS do prestador, sem retenção (T2)." in html
    assert "o XML traz tpRetISSQN 1, sem outro sinal de natureza." in html
    # O catálogo explica cada natureza.
    assert "Exige tpRetISSQN 1 no XML." in html
    # Natureza compatível com o XML: os dois botões estão habilitados.
    assert not _desabilitado(html, "efetivar")
    assert not _desabilitado(html, "rascunho")


def test_efetivar_tomada_pela_tela(client, escritorio_a, empresa_a2, usuario_gestor_a):
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9321,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="40.00",
        v_liq="960.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-12",
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    primeira = client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": T1, "acao": "efetivar"},
        follow=True,
    )
    assert "Nota tomada escriturada com a natureza confirmada." in primeira.content.decode()
    escrituracao = EscrituracaoTomada.objects.get(vinculo=vinculo)
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA
    assert escrituracao.natureza == T1
    assert escrituracao.v_iss_qn == Decimal("40.00")

    # Repetir o clique não grava nada e avisa: idempotência (mesma decisão da DL-072).
    repetida = client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": T1, "acao": "efetivar"},
        follow=True,
    )
    assert "Nada foi alterado." in repetida.content.decode()
    assert EscrituracaoTomada.objects.filter(vinculo=vinculo).count() == 1


def test_natureza_incompativel_nao_grava_e_desabilita_efetivar(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    # tpRetISSQN 1 (sem retenção): T1 é incompatível. A efetivação recusa, e a tela
    # desabilita o botão.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9331,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="1",
        c_loc_incid=PALMAS,
        c_loc_prestacao=PALMAS,
        d_compet="2026-10-13",
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    recusada = client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": T1, "acao": "efetivar"},
    )
    html = recusada.content.decode()

    assert recusada.status_code == 200
    assert "exige tpRetISSQN 2 no XML" in html
    assert "Nada foi gravado." in html
    assert not EscrituracaoTomada.objects.filter(vinculo=vinculo).exists()
    # Com a natureza incompatível escolhida, o botão Efetivar aparece DESABILITADO, com o motivo.
    assert _desabilitado(html, "efetivar")
    assert "Efetivar indisponível:" in html
    assert "(T1) exige tpRetISSQN 2 no XML" in html
    # Rascunho aceita qualquer natureza do catálogo (a compatibilidade só é cobrada na efetivação).
    assert not _desabilitado(html, "rascunho")

    rascunho = client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": T1, "acao": "rascunho"},
    )
    assert rascunho.status_code == 302
    assert EscrituracaoTomada.objects.get(vinculo=vinculo).estado == EstadoEscrituracao.RASCUNHO


def test_emissao_pelo_tomador_e_recusada_sem_gravar(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    # tpEmit 2 (emissão pelo tomador): fora do catálogo. A recusa é nomeada e nada é gravado.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9341,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="10.00",
        v_liq="990.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-14",
        tp_emit="2",
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": T1, "acao": "efetivar"},
    )
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert "tpEmit 2 ou 3" in html
    assert _desabilitado(html, "efetivar")
    assert _desabilitado(html, "rascunho")
    assert not EscrituracaoTomada.objects.filter(vinculo=vinculo).exists()


def test_natureza_nao_escolhida_nao_grava(client, escritorio_a, empresa_a2, usuario_gestor_a):
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9351,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="10.00",
        v_liq="990.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-15",
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": "", "acao": "efetivar"},
    )

    assert resposta.status_code == 200
    assert "Escolha a natureza da operação." in resposta.content.decode()
    assert not EscrituracaoTomada.objects.filter(vinculo=vinculo).exists()


# ---------------------------------------------------------------------------
# Estornar e informar a data de pagamento (com trilha)
# ---------------------------------------------------------------------------


def test_tela_estornar_tomada_e_acessivel(client, cenario, empresa_a2, usuario_gestor_a):
    escrituracao = cenario["t1"]
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_estornar(empresa_a2, escrituracao))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert_moldura_acessivel(html)
    assert "O que vai acontecer" in html
    assert "Motivo do estorno" in html


def test_estornar_tomada_pela_tela_exige_motivo(client, cenario, empresa_a2, usuario_gestor_a):
    escrituracao = cenario["t6"]
    _logar(client, usuario_gestor_a)

    sem_motivo = client.post(_url_estornar(empresa_a2, escrituracao), {"motivo": ""})
    assert sem_motivo.status_code == 200
    assert "Informe o motivo do estorno." in sem_motivo.content.decode()
    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA

    com_motivo = client.post(
        _url_estornar(empresa_a2, escrituracao),
        {"motivo": "Lançada em duplicidade"},
    )
    assert com_motivo.status_code == 302
    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.ESTORNADA
    assert escrituracao.motivo_estorno == "Lançada em duplicidade"


def test_tela_data_pagamento_e_acessivel(client, cenario_federal, empresa_a2, usuario_gestor_a):
    escrituracao = cenario_federal
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_pagamento(empresa_a2, escrituracao))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert_moldura_acessivel(html)
    assert "Data de pagamento informada" in html
    assert "Nenhuma data de pagamento foi informada para esta nota." in html


def test_informar_data_pagamento_pela_tela(client, cenario_federal, empresa_a2, usuario_gestor_a):
    escrituracao = cenario_federal
    _logar(client, usuario_gestor_a)

    sem_motivo = client.post(
        _url_pagamento(empresa_a2, escrituracao),
        {"data_pagamento": "20/10/2026", "motivo": ""},
    )
    assert sem_motivo.status_code == 200
    assert "Informe o motivo da data de pagamento." in sem_motivo.content.decode()
    escrituracao.refresh_from_db()
    assert escrituracao.data_pagamento is None

    data_invalida = client.post(
        _url_pagamento(empresa_a2, escrituracao),
        {"data_pagamento": "31/02/2026", "motivo": "Pagamento creditado"},
    )
    assert data_invalida.status_code == 400
    escrituracao.refresh_from_db()
    assert escrituracao.data_pagamento is None

    informada = client.post(
        _url_pagamento(empresa_a2, escrituracao),
        {"data_pagamento": "20/10/2026", "motivo": "Pagamento creditado ao prestador"},
        follow=True,
    )
    html = informada.content.decode()
    escrituracao.refresh_from_db()
    assert escrituracao.data_pagamento == date(2026, 10, 20)
    # A trilha mostra a data anterior ("—", porque não havia), a nova e o motivo.
    assert "20/10/2026" in html
    assert "Pagamento creditado ao prestador" in html

    repetida = client.post(
        _url_pagamento(empresa_a2, escrituracao),
        {"data_pagamento": "20/10/2026", "motivo": "Pagamento creditado ao prestador"},
        follow=True,
    )
    assert "Nada foi alterado." in repetida.content.decode()


# ---------------------------------------------------------------------------
# ISS retido a recolher e retenções federais (totais)
# ---------------------------------------------------------------------------


def test_tela_iss_retido_a_recolher_e_acessivel(client, cenario, empresa_a2, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_iss(empresa_a2))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert_moldura_acessivel(html)
    assert TEXTO_DE_CONFERENCIA_DO_RETIDO in html
    # 50,00 (T1) + 7,00 (T6, item 0) = 57,00, em pt-BR.
    assert "57,00" in html
    # Vencimento de Palmas para a competência 10/2026: 15/11/2026, domingo (regra da DL-076).
    assert "15/11/2026 (domingo)" in html
    # Retida sem vISSQN: aparece para conferir, e não como zero.
    assert "1 nota(s): conferir" in html
    assert "Retida sem valor destacado: conferir" in html
    # A nota a escriturar não entra no total.
    assert "Tomado — ISS do prestador, sem retenção (T2)" not in html


def test_fluxo_por_natureza_chega_ao_iss_retido(client, escritorio_a, empresa_a2, usuario_gestor_a):
    # MEI com tpRetISSQN 2: o XML sugere T1 (a retenção vem antes do porte). O contador confirma T5.
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9361,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="20.00",
        v_liq="980.00",
        c_loc_incid=PALMAS,
        d_compet="2026-10-16",
        op_simp_nac="2",
    )
    vinculo = vinculo_tomador(documento, empresa_a2)
    _logar(client, usuario_gestor_a)

    antes = client.get(_url_escriturar(empresa_a2, vinculo)).content.decode()
    assert "Sugestão do XML: Tomado — ISS retido pelo cliente tomador (T1)." in antes
    assert (
        "Nenhuma nota com ISS retido na competência."
        in client.get(_url_iss(empresa_a2)).content.decode()
    )

    client.post(
        _url_escriturar(empresa_a2, vinculo),
        {"natureza": T5, "acao": "efetivar"},
    )

    html = client.get(_url_iss(empresa_a2)).content.decode()
    # Efetivada como MEI, a nota SOMA (item 0) e leva o aviso de conferência, sem alterar o valor.
    assert "20,00" in html
    assert "MEI não sofre retenção de ISS em regra — conferir." in html
    assert "LC 123, art. 18-A" in html
    assert "inferência" in html


def test_tela_retencoes_federais_e_acessivel(client, cenario_federal, empresa_a2, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_federais(empresa_a2))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert_moldura_acessivel(html)
    assert "CSRF retida (PIS + COFINS + CSLL)" in html
    assert "Contribuição previdenciária retida (INSS)" in html
    assert "Mês de emissão da nota" in html
    assert "o DataLedger não gera guia, não transmite EFD-Reinf nem DCTFWeb" in html
    assert TEXTO_DE_CONFERENCIA_DO_RETIDO not in html
    # IRRF e CSRF sem data de pagamento ficam PENDENTES, com o link para informar.
    assert "Pendente de data de pagamento" in html
    assert "Informar data de pagamento" in html
    assert "Nenhuma CSRF com data de pagamento informada no mês." in html


def test_data_de_pagamento_move_irrf_e_csrf_do_pendente_para_o_grupo(
    client, cenario_federal, empresa_a2, usuario_gestor_a
):
    escrituracao = cenario_federal
    _logar(client, usuario_gestor_a)

    antes = client.get(_url_federais(empresa_a2)).content.decode()
    assert "Nenhum IRRF com data de pagamento informada no mês." in antes
    assert "Nenhuma retenção pendente de data de pagamento na competência." not in antes

    client.post(
        _url_pagamento(empresa_a2, escrituracao),
        {"data_pagamento": "20/10/2026", "motivo": "Pagamento creditado ao prestador"},
    )

    depois = client.get(_url_federais(empresa_a2)).content.decode()
    # O IRRF e a CSRF saem de "pendente" e entram no grupo da data informada.
    assert "Nenhuma retenção pendente de data de pagamento na competência." in depois
    assert "Nenhum IRRF com data de pagamento informada no mês." not in depois
    assert "Nenhuma CSRF com data de pagamento informada no mês." not in depois
    grupo_csrf = depois[
        depois.index("CSRF por data de pagamento") : depois.index("IRRF por data de pagamento")
    ]
    grupo_irrf = depois[
        depois.index("IRRF por data de pagamento") : depois.index("Pendente de data de pagamento")
    ]
    assert "20/10/2026" in grupo_irrf and "15,00" in grupo_irrf
    assert "20/10/2026" in grupo_csrf and "20,00" in grupo_csrf
    # Os totais por tributo não mudam com a data: é a mesma retenção, só mudou o grupo.
    assert "15,00" in depois and "20,00" in depois


# ---------------------------------------------------------------------------
# Formatação pt-BR e inventário
# ---------------------------------------------------------------------------


def test_valores_em_pt_br_escritos_a_mao(client, cenario, empresa_a2, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    html = client.get(_url_iss(empresa_a2)).content.decode()

    # Valores esperados escritos à mão: 57,00 e 1.000,00. Ponto como decimal não aparece.
    assert "57,00" in html and "1.000,00" in html
    assert "57.00" not in html
    assert "1000.00" not in html


def test_rotas_de_tomadas_estao_no_inventario_do_dl024():
    """Cada rota nova tem uma linha no inventário: a guarda de cobertura reprova rota sem
    classificação, e este teste nomeia a que faltar."""
    assert set(NOMES_DE_TELA_DOS_SERVICOS_TOMADOS) == {
        "fiscal_web:tomadas_lista",
        "fiscal_web:tomada_escriturar",
        "fiscal_web:tomada_estornar",
        "fiscal_web:tomada_data_pagamento",
        "fiscal_web:iss_retido_a_recolher",
        "fiscal_web:retencoes_federais",
    }


def test_pessoa_fisica_sem_sinal_de_mei_ou_simples_e_sugerida_como_t7(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    """A sugestão exibida segue o XML: prestador CPF, sem MEI nem Simples, sugere T7."""
    documento = receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        9371,
        tomador_documento=empresa_a2.cnpj,
        prestador_documento=CPF_PRESTADOR_SINTETICO,
        prestador_tipo="CPF",
        tp_ret_issqn="1",
        c_loc_incid=PALMAS,
        c_loc_prestacao=PALMAS,
        d_compet="2026-10-17",
    )
    _logar(client, usuario_gestor_a)

    url = _url_escriturar(empresa_a2, vinculo_tomador(documento, empresa_a2))
    html = client.get(url).content.decode()

    assert "Sugestão do XML: Tomado de pessoa física (T7)." in html
    assert "o prestador é pessoa física (CPF)" in html
