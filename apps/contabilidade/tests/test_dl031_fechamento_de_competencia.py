"""Testes da fatia 2 da DL-016 (DL-031) — a TELA do fechamento de competência.

Cada teste referencia o critério de aceite numerado do plano
docs/planos/DL-031-fatia-2-a-tela-do-fechamento.md. NENHUMA regra contábil é
testada de novo aqui — `encerrar_competencia`/`reabrir_competencia`/
`marcar_competencia_como_entregue` (services.py) já são cobertos por
`apps/contabilidade/tests/test_dl016_fatia1_fechamento_reabertura_entrega.py`,
auditado em duas rodadas. O que este arquivo mede é a PORTA: a tela chama o
serviço certo, traduz cada exceção em mensagem de português (nunca 500 —
critério 5, com controle positivo no MESMO caso), mostra a conferência do
RC-58 ANTES do botão (critério 2), trata "sem permissão" como estado
(critério 1) e nunca oferece reabertura de mês já entregue (critério 6).

Dados 100% sintéticos, criados nos próprios testes. Usa o `ROOT_URLCONF`
REAL do produto (`config/urls.py`, sem `pytest.mark.urls`): as rotas de
`apps.contabilidade.urls_web` já estão costuradas lá sob
"contabilidade/painel/" — mesma escolha de
`test_dl016_fatia1_fechamento_reabertura_entrega.py`.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    Competencia,
    Conta,
    EstadoCompetencia,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    criar_lancamento,
    encerrar_competencia,
    marcar_competencia_como_entregue,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    if papel is not None:
        VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel, username):
    usuario = _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")
    return usuario


@pytest.fixture
def cenario():
    """Uma empresa com plano de contas mínimo, pronta para lançar — mesmo
    formato de `test_dl016_fatia1_fechamento_reabertura_entrega.cenario`."""
    escritorio = Escritorio.objects.create(nome="Escritório DL-031", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="ACME Fechamento LTDA", cnpj="11444777000161"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "capital": capital}


def _lancar(empresa, caixa, capital, data, criado_por=None):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico="Lançamento de teste",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
        criado_por=criado_por,
    )


def _lote_desbalanceado(empresa, caixa, ano, mes):
    """Grava um lote TORTO por fora de `criar_lancamento` — o único caminho
    que `localizar_lotes_desbalanceados` existe para achar (ver o docstring
    dela em services.py). Mesmo padrão de
    `test_criterio3_encerrar_recusa_com_lote_desbalanceado_na_base`."""
    competencia, _ = Competencia.objects.get_or_create(empresa=empresa, ano=ano, mes=mes)
    lancamento = LancamentoContabil.objects.create(
        empresa=empresa,
        data=date(ano, mes, 10),
        historico="Lote torto (só débito, sem contrapartida)",
        competencia=competencia,
    )
    ItemLancamento.objects.create(
        lancamento=lancamento, conta=caixa, tipo=TipoPartida.DEBITO, valor=Decimal("10.00")
    )
    return lancamento


def _url_fechamento(empresa_id):
    return reverse("contabilidade_web:fechamento", args=[empresa_id])


def _url_fechar(empresa_id, ano=None, mes=None):
    base = reverse("contabilidade_web:competencia_fechar", args=[empresa_id])
    return base if ano is None else f"{base}?ano={ano}&mes={mes}"


def _url_reabrir(empresa_id, ano=None, mes=None):
    base = reverse("contabilidade_web:competencia_reabrir", args=[empresa_id])
    return base if ano is None else f"{base}?ano={ano}&mes={mes}"


def _url_entregar(empresa_id, ano=None, mes=None):
    base = reverse("contabilidade_web:competencia_entregar", args=[empresa_id])
    return base if ano is None else f"{base}?ano={ano}&mes={mes}"


# ---------------------------------------------------------------------------
# Critério 1 — "sem permissão" é ESTADO, não erro: o analista VÊ o painel e
# NÃO VÊ os botões de ação; a tela explica por quê. Forçando a requisição de
# ação, o servidor recusa com 403 e o banco continua intacto.
# ---------------------------------------------------------------------------


def test_criterio1_analista_ve_o_painel_mas_nao_ve_os_botoes_de_acao(client, cenario):
    empresa = cenario["empresa"]
    _lancar(empresa, cenario["caixa"], cenario["capital"], timezone.localdate())
    _autenticar(client, cenario["escritorio"], Papel.ANALISTA, "c1-analista")

    resposta = client.get(_url_fechamento(empresa.id))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    # O painel inteiro continua visível — trilha, estados, competências.
    assert "ACME Fechamento LTDA" in corpo
    # A explicação aparece EM VEZ do botão, nunca em silêncio.
    assert "exige administrador ou gestor" in corpo
    assert "RC-102" in corpo
    # Nenhum link de ação some SEM explicação — os rótulos não aparecem.
    assert ">Fechar<" not in corpo
    assert ">Reabrir<" not in corpo
    assert ">Marcar como entregue<" not in corpo


def test_criterio1_analista_forcando_a_acao_recebe_403_e_banco_intacto(client, cenario):
    empresa = cenario["empresa"]
    hoje = timezone.localdate()
    _lancar(empresa, cenario["caixa"], cenario["capital"], hoje)
    _autenticar(client, cenario["escritorio"], Papel.ANALISTA, "c1-analista-forca")

    resposta = client.post(
        _url_fechar(empresa.id, hoje.year, hoje.month), data={"ano": hoje.year, "mes": hoje.month}
    )

    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    assert "RC-102" in resposta.content.decode()
    competencia = Competencia.objects.get(empresa=empresa, ano=hoje.year, mes=hoje.month)
    assert competencia.estado == EstadoCompetencia.ABERTA


# ---------------------------------------------------------------------------
# Critério 2 — a conferência (RC-58) aparece ANTES do botão de fechar. Nunca
# um clique para descobrir: nem no painel, nem na tela de ação.
# ---------------------------------------------------------------------------


def test_criterio2_painel_bloqueia_o_link_de_fechar_e_aponta_para_a_conferencia(client, cenario):
    empresa, caixa = cenario["empresa"], cenario["caixa"]
    _lote_desbalanceado(empresa, caixa, 2026, 3)
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c2-painel")

    resposta = client.get(_url_fechamento(empresa.id))

    corpo = resposta.content.decode()
    assert "RC-58" in corpo
    assert reverse("contabilidade_web:conferencia", args=[empresa.id]) in corpo
    assert ">Fechar<" not in corpo
    assert "Bloqueado pela conferência" in corpo


def test_criterio2_tela_de_fechar_nao_oferece_o_botao_quando_ha_lote_desbalanceado(client, cenario):
    empresa, caixa = cenario["empresa"], cenario["caixa"]
    _lote_desbalanceado(empresa, caixa, 2026, 3)
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c2-tela")

    resposta = client.get(_url_fechar(empresa.id, 2026, 3))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "RC-58" in corpo
    # Nenhum formulário de POST para a AÇÃO de fechar — o título da página
    # ("Fechar competência 03/2026") continua legítimo, é só rótulo de tela.
    assert f'action="{_url_fechar(empresa.id)}"' not in corpo
    assert ">Fechar competência 03/2026</button>" not in corpo


# ---------------------------------------------------------------------------
# Critério 3 — reabrir exige motivo NA TELA. Motivo vazio não chega ao
# servidor gravado — e, se chegar, o serviço recusa (o formulário volta,
# nunca some).
# ---------------------------------------------------------------------------


def test_criterio3_reabrir_com_motivo_vazio_reexibe_o_formulario_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c3-vazio")
    encerrar_competencia(empresa=empresa, ano=2026, mes=4, usuario=gestor)

    resposta = client.post(_url_reabrir(empresa.id), data={"ano": 2026, "mes": 4, "motivo": "   "})

    assert resposta.status_code == 400
    corpo = resposta.content.decode()
    assert "motivo" in corpo.lower()
    assert "não pode ficar em branco" in corpo
    # O formulário continua lá — não sumiu.
    assert "<form" in corpo
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=4)
    assert competencia.estado == EstadoCompetencia.ENCERRADA


def test_criterio3_reabrir_com_motivo_grava_e_fica_na_trilha(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c3-motivo")
    encerrar_competencia(empresa=empresa, ano=2026, mes=4, usuario=gestor)

    resposta = client.post(
        _url_reabrir(empresa.id),
        data={"ano": 2026, "mes": 4, "motivo": "corrigir lançamento de aluguel"},
    )

    assert resposta.status_code == 302
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=4)
    assert competencia.estado == EstadoCompetencia.ABERTA
    registro = RegistroAuditoria.objects.filter(acao="competencia.reaberta").latest("criado_em")
    assert registro.detalhes["motivo"] == "corrigir lançamento de aluguel"


# ---------------------------------------------------------------------------
# Critério 4 — entregar avisa que não tem volta, com o texto do RC-101: a
# ação exige confirmação EXPLÍCITA, não um único clique.
# ---------------------------------------------------------------------------


def test_criterio4_tela_de_entregar_avisa_que_nao_tem_volta(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c4-aviso")
    encerrar_competencia(empresa=empresa, ano=2026, mes=5, usuario=gestor)

    resposta = client.get(_url_entregar(empresa.id, 2026, 5))

    corpo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "sem volta pelo produto" in corpo
    # `\s+` porque o template quebra a frase em duas linhas de HTML —
    # o texto visível no navegador é contínuo, o texto-fonte não.
    assert re.search(r"não pode mais ser\s+reaberta", corpo)
    assert re.search(r"mês\s+<strong>aberto</strong>", corpo)
    assert 'name="confirmar_entrega"' in corpo


def test_criterio4_entregar_sem_confirmar_a_caixa_nao_grava_nada(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c4-sem-confirmar")
    encerrar_competencia(empresa=empresa, ano=2026, mes=5, usuario=gestor)

    resposta = client.post(_url_entregar(empresa.id), data={"ano": 2026, "mes": 5})

    assert resposta.status_code == 400
    assert "Confirme a caixa de seleção" in resposta.content.decode()
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=5)
    assert competencia.entregue_em is None


def test_criterio4_entregar_confirmando_grava_entregue_em(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c4-confirma")
    encerrar_competencia(empresa=empresa, ano=2026, mes=5, usuario=gestor)

    resposta = client.post(
        _url_entregar(empresa.id), data={"ano": 2026, "mes": 5, "confirmar_entrega": "1"}
    )

    assert resposta.status_code == 302
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=5)
    assert competencia.entregue_em is not None


# ---------------------------------------------------------------------------
# Critério 5 — toda recusa do servidor vira mensagem em português, nunca
# 500. CONTROLE POSITIVO no mesmo caso: a mesma requisição, sem o motivo da
# recusa, tem que ter sucesso — senão o código certo passaria pelo motivo
# errado (a lição do BL-457, medida na tela de lançamento).
# ---------------------------------------------------------------------------


def test_criterio5_post_fechar_com_lote_desbalanceado_recusa_em_portugues_sem_500(client, cenario):
    empresa, caixa = cenario["empresa"], cenario["caixa"]
    _lote_desbalanceado(empresa, caixa, 2026, 6)
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c5-fechar-negativo")

    resposta = client.post(_url_fechar(empresa.id), data={"ano": 2026, "mes": 6})

    assert resposta.status_code == 302  # nunca 500
    resposta_seguida = client.get(resposta.url)
    assert "RC-58" in resposta_seguida.content.decode()
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=6)
    assert competencia.estado == EstadoCompetencia.ABERTA


def test_criterio5_controle_positivo_post_fechar_sem_lote_desbalanceado_funciona(client, cenario):
    """CONTROLE POSITIVO do teste acima: MESMO fluxo, base balanceada — tem
    que fechar. Prova que a recusa medida acima é do RC-58, não de outro
    defeito que faria qualquer fechamento falhar."""
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c5-fechar-positivo")

    resposta = client.post(_url_fechar(empresa.id), data={"ano": 2026, "mes": 6})

    assert resposta.status_code == 302
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=6)
    assert competencia.estado == EstadoCompetencia.ENCERRADA


def test_criterio5_post_reabrir_competencia_entregue_recusa_em_portugues_sem_500(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c5-reabrir-negativo")
    encerrar_competencia(empresa=empresa, ano=2026, mes=7, usuario=gestor)
    marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=7, usuario=gestor)

    resposta = client.post(
        _url_reabrir(empresa.id), data={"ano": 2026, "mes": 7, "motivo": "tentando mesmo assim"}
    )

    assert resposta.status_code == 302  # nunca 500
    resposta_seguida = client.get(resposta.url)
    assert "já foi entregue" in resposta_seguida.content.decode()
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=7)
    assert competencia.estado == EstadoCompetencia.ENCERRADA


def test_criterio5_controle_positivo_post_reabrir_competencia_nao_entregue_funciona(
    client, cenario
):
    """CONTROLE POSITIVO: mesmo fluxo, sem a entrega — tem que reabrir."""
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c5-reabrir-positivo")
    encerrar_competencia(empresa=empresa, ano=2026, mes=8, usuario=gestor)

    resposta = client.post(
        _url_reabrir(empresa.id), data={"ano": 2026, "mes": 8, "motivo": "ajuste legítimo"}
    )

    assert resposta.status_code == 302
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=8)
    assert competencia.estado == EstadoCompetencia.ABERTA


def test_criterio5_post_entregar_mes_aberto_recusa_em_portugues_sem_500(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c5-entregar-negativo")

    resposta = client.post(
        _url_entregar(empresa.id), data={"ano": 2026, "mes": 9, "confirmar_entrega": "1"}
    )

    assert resposta.status_code == 302  # nunca 500
    resposta_seguida = client.get(resposta.url)
    assert "encerrada" in resposta_seguida.content.decode().lower()
    assert not Competencia.objects.filter(
        empresa=empresa, ano=2026, mes=9, entregue_em__isnull=False
    ).exists()


def test_criterio5_controle_positivo_post_entregar_mes_encerrado_funciona(client, cenario):
    """CONTROLE POSITIVO: mesmo fluxo, competência encerrada — tem que
    entregar."""
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c5-entregar-positivo")
    encerrar_competencia(empresa=empresa, ano=2026, mes=9, usuario=gestor)

    resposta = client.post(
        _url_entregar(empresa.id), data={"ano": 2026, "mes": 9, "confirmar_entrega": "1"}
    )

    assert resposta.status_code == 302
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=9)
    assert competencia.entregue_em is not None


# ---------------------------------------------------------------------------
# Critério 6 — mês entregue NUNCA oferece reabertura (BL-468): nem no
# painel, nem na tela de ação (que redireciona com a mensagem certa em vez
# de mostrar um formulário sem sentido).
# ---------------------------------------------------------------------------


def test_criterio6_painel_nao_mostra_link_de_reabrir_para_competencia_entregue(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c6-painel")
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=1, usuario=gestor)

    resposta = client.get(_url_fechamento(empresa.id))

    corpo = resposta.content.decode()
    assert ">Reabrir<" not in corpo
    assert ">Marcar como entregue<" in corpo  # entrega pode se repetir


def test_criterio6_get_reabrir_competencia_entregue_redireciona_com_a_mensagem_certa(
    client, cenario
):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c6-get")
    encerrar_competencia(empresa=empresa, ano=2026, mes=2, usuario=gestor)
    marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=2, usuario=gestor)

    resposta = client.get(_url_reabrir(empresa.id, 2026, 2))

    assert resposta.status_code == 302
    resposta_seguida = client.get(resposta.url)
    corpo = resposta_seguida.content.decode()
    assert "já foi entregue" in corpo
    assert "mês aberto" in corpo


# ---------------------------------------------------------------------------
# Critério 7 — densidade e legibilidade: cor nunca sozinha (o TEXTO
# "Aberta"/"Encerrada" está sempre presente, não só a classe CSS) e pt-BR em
# toda data exibida. Tabulação de algarismo e contraste calculado — ver o
# relatório de entrega para as medições (esta tela não exibe valor
# monetário: não há coluna a tabular).
# ---------------------------------------------------------------------------


def test_criterio7_estado_da_competencia_e_sempre_texto_nunca_so_cor(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c7-texto")
    _lancar(empresa, cenario["caixa"], cenario["capital"], date(2026, 1, 15), criado_por=gestor)
    encerrar_competencia(empresa=empresa, ano=2026, mes=2, usuario=gestor)

    resposta = client.get(_url_fechamento(empresa.id))

    corpo = resposta.content.decode()
    assert ">Aberta<" in corpo
    assert ">Encerrada</strong>" in corpo


def test_criterio7_datas_aparecem_em_formato_pt_br(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c7-data")
    encerrar_competencia(empresa=empresa, ano=2026, mes=3, usuario=gestor)

    resposta = client.get(_url_fechamento(empresa.id))

    corpo = resposta.content.decode()
    # dd/mm/aaaa — nunca ISO na tela.
    assert "2026-03" not in corpo
    assert re.search(r"\d{2}/\d{2}/\d{4}", corpo)


def test_criterio7_nenhuma_dependencia_externa_nas_quatro_telas_novas(client, cenario):
    """DE-011: sem CDN, sem biblioteca visual, sem fonte remota. Varre as
    quatro telas desta fatia por qualquer `src`/`href` apontando para fora
    do próprio host."""
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c7-sem-cdn")
    encerrar_competencia(empresa=empresa, ano=2026, mes=10, usuario=gestor)

    urls = [
        _url_fechamento(empresa.id),
        _url_fechar(empresa.id, 2026, 11),
        _url_reabrir(empresa.id, 2026, 10),
        _url_entregar(empresa.id, 2026, 10),
    ]
    for url in urls:
        corpo = client.get(url).content.decode()
        assert "http://" not in corpo
        assert "https://" not in corpo


# ---------------------------------------------------------------------------
# Extras: RC-53 (fechar mês sem nenhum lançamento ainda) e isolamento entre
# empresas/escritórios — fora dos oito critérios numerados, mas parte do
# escopo do plano ("painel de competências da empresa").
# ---------------------------------------------------------------------------


def test_rc53_fecha_um_mes_que_nunca_teve_lancamento(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.ADMINISTRADOR, "rc53")
    assert not Competencia.objects.filter(empresa=empresa, ano=1999, mes=12).exists()

    resposta = client.post(_url_fechar(empresa.id), data={"ano": 1999, "mes": 12})

    assert resposta.status_code == 302
    competencia = Competencia.objects.get(empresa=empresa, ano=1999, mes=12)
    assert competencia.estado == EstadoCompetencia.ENCERRADA


def test_isolamento_painel_de_uma_empresa_nao_mostra_competencia_de_outra(client, cenario):
    escritorio = cenario["escritorio"]
    empresa_a = cenario["empresa"]
    empresa_b = Empresa.objects.create(
        escritorio=escritorio, razao_social="Outra Empresa LTDA", cnpj="22333444000199"
    )
    gestor = _autenticar(client, escritorio, Papel.GESTOR, "isolamento-empresa")
    encerrar_competencia(empresa=empresa_a, ano=2026, mes=1, usuario=gestor)
    encerrar_competencia(empresa=empresa_b, ano=2026, mes=1, usuario=gestor)

    resposta = client.get(_url_fechamento(empresa_a.id))

    assert "Outra Empresa LTDA" not in resposta.content.decode()


def test_isolamento_empresa_de_outro_escritorio_e_404(client, cenario):
    outro_escritorio = Escritorio.objects.create(nome="Outro Escritório", cnpj="99888777000166")
    empresa_de_fora = Empresa.objects.create(
        escritorio=outro_escritorio, razao_social="Empresa de Fora LTDA", cnpj="55666777000188"
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "isolamento-escritorio")

    resposta = client.get(_url_fechamento(empresa_de_fora.id))

    assert resposta.status_code == 404


def test_idempotencia_mensagem_distingue_fechar_agora_de_ja_estava_fechada(client, cenario):
    empresa = cenario["empresa"]
    gestor = _autenticar(client, cenario["escritorio"], Papel.ADMINISTRADOR, "idempotencia")
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)

    resposta = client.post(_url_fechar(empresa.id), data={"ano": 2026, "mes": 1})

    assert resposta.status_code == 302
    resposta_seguida = client.get(resposta.url)
    assert "já estava fechada" in resposta_seguida.content.decode()
