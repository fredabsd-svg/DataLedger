"""DL-074 (frente B) — telas da receita mensal do Simples Nacional.

Telas: painel do mês (receita por mercado, composição, confirmação, receitas informadas,
RBT12 com a regra, pendentes e avisos), lançar, confirmar e estornar receita informada,
confirmar e reabrir o mês, e o regime de caixa. A regra é a da frente A (`apps.fiscal.
receita` e `apps.fiscal.rbt12`): aqui se prova que a TELA mostra e recusa o que o serviço
decide, e que a autorização e o isolamento são verificados no servidor.

- Dados 100% sintéticos (xml_sinteticos.py e test_dl074_suporte.py). Sem dado real.
- Moldura de acessibilidade: a mesma guarda das outras telas do produto.
- Pré-apuração para conferência (classe 1): o painel diz isso e não transmite nada.
"""

import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
    assert_moldura_acessivel,
)
from apps.fiscal import receita as servico
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    EstadoReceitaInformada,
    OpcaoRegimeCaixaSimples,
    ReceitaInformada,
)
from apps.fiscal.tests.test_dl074_suporte import (
    NATUREZA_EXPORTACAO,
    ORIGEM_OUTRAS,
    confirmar_meses,
    escriturar,
    fixar_inicio_de_uso,
    informar_e_confirmar,
    preparar_simples,
    sequencia,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fábrica e URLs
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


@pytest.fixture
def empresa(empresa_a):
    # Início de uso do sistema em 01/2024; abertura em 2015; Simples desde 2018.
    fixar_inicio_de_uso(empresa_a, 2024, 1)
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


@pytest.fixture
def paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl074-telas")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-dl074-telas")


def _url_painel():
    return reverse("fiscal_web:receita_do_mes")


def _painel_de(empresa, ano, mes):
    return {"empresa": empresa.pk, "ano": ano, "mes": mes}


def _url_confirmar(empresa, ano, mes):
    return reverse("fiscal_web:receita_mes_confirmar", args=[empresa.pk, ano, mes])


def _url_reabrir(empresa, ano, mes):
    return reverse("fiscal_web:receita_mes_reabrir", args=[empresa.pk, ano, mes])


def _url_lancar(empresa):
    return reverse("fiscal_web:receita_informada_nova", args=[empresa.pk])


def _url_confirmar_receita(empresa, receita):
    return reverse("fiscal_web:receita_informada_confirmar", args=[empresa.pk, receita.pk])


def _url_estornar_receita(empresa, receita):
    return reverse("fiscal_web:receita_informada_estornar", args=[empresa.pk, receita.pk])


def _url_regime(empresa):
    return reverse("fiscal_web:regime_caixa", args=[empresa.pk])


def _confirmacao(empresa, ano, mes):
    return ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=ano, mes=mes)


def _lancamento_valido(**sobrescritas):
    """Dados de um POST válido do formulário de lançamento. Sobrescreva o que o teste muda."""
    dados = {
        "ano": "2024",
        "mes": "03",
        "mercado": "interno",
        "situacao_iss": "proprio_municipio",
        "valor": "100,00",
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "Extrato sintético de teste.",
        "acao": "rascunho",
    }
    dados.update(sobrescritas)
    return dados


# ---------------------------------------------------------------------------
# Telas (200) e moldura de acessibilidade
# ---------------------------------------------------------------------------


def test_tela_receita_do_mes_e_acessivel(client, escritorio_a, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_painel(), _painel_de(empresa, 2026, 3))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fiscal/receita_do_mes.html" in [t.name for t in resposta.templates]
    # Aviso de classe 1 e de que não transmite nada: o painel não se passa por documento oficial.
    assert "Pré-apuração para conferência." in html
    assert "não transmite nada" in html
    assert_moldura_acessivel(html)


def test_tela_receita_do_mes_sem_empresa_e_acessivel(client, escritorio_a, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_painel())

    assert resposta.status_code == 200
    assert "Escolha uma empresa para ver a receita do mês." in resposta.content.decode()
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_lancar_receita_e_acessivel(client, escritorio_a, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lancar(empresa), {"ano": "2026", "mes": "3"})

    assert resposta.status_code == 200
    assert "fiscal/receita_informada_nova.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_reabrir_mes_e_acessivel(client, escritorio_a, empresa, usuario_gestor_a):
    servico.confirmar_mes(empresa, 2026, 3, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_reabrir(empresa, 2026, 3))

    assert resposta.status_code == 200
    assert "fiscal/receita_mes_reabrir.html" in [t.name for t in resposta.templates]
    assert "Reabrir receita de 03/2026" in resposta.content.decode()
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_estornar_receita_e_acessivel(client, escritorio_a, empresa, usuario_gestor_a):
    receita = informar_e_confirmar(empresa, usuario_gestor_a, 2026, 3, Decimal("200"))
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_estornar_receita(empresa, receita))

    assert resposta.status_code == 200
    assert "fiscal/receita_informada_estornar.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_regime_caixa_e_acessivel(client, escritorio_a, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_regime(empresa))

    assert resposta.status_code == 200
    assert "fiscal/regime_caixa.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


# ---------------------------------------------------------------------------
# Painel: composição, confirmação, RBT12 com regra, pendentes e avisos
# ---------------------------------------------------------------------------


def test_painel_mostra_documento_informado_e_total_por_mercado(
    client, escritorio_a, empresa, usuario_gestor_a
):
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=901, competencia=(2026, 3), valor="1000"
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 3, Decimal("500"))
    escriturar(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=902,
        competencia=(2026, 3),
        valor="300",
        natureza=NATUREZA_EXPORTACAO,
    )
    _logar(client, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 3)).content.decode()

    # Colunas: NFS-e, NF-e de saída, receita informada, devolução deduzida e total (DL-081, A7: as
    # colunas de NF-e e de devolução foram acrescentadas, e valem zero neste cenário).
    # Interno: 1.000 de documento + 500 informado = 1.500. Exportação nunca soma no interno.
    assert re.search(
        r'Mercado interno</th>\s*<td class="valor-monetario">1\.000,00</td>\s*'
        r'<td class="valor-monetario">0,00</td>\s*'
        r'<td class="valor-monetario">500,00</td>\s*<td class="valor-monetario">0,00</td>\s*'
        r'<td class="valor-monetario">1\.500,00</td>',
        html,
    )
    assert re.search(
        r'Mercado externo[^<]*</th>\s*<td class="valor-monetario">300,00</td>\s*'
        r'<td class="valor-monetario">0,00</td>\s*<td class="valor-monetario">0,00</td>\s*'
        r'<td class="valor-monetario">0,00</td>\s*<td class="valor-monetario">300,00</td>',
        html,
    )


def test_painel_mostra_a_situacao_e_reabrir_quando_confirmado(
    client, escritorio_a, empresa, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)
    client.post(_url_confirmar(empresa, 2026, 3))

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 3)).content.decode()

    assert "Situação: Confirmado." in html
    assert _url_reabrir(empresa, 2026, 3) in html
    assert _url_confirmar(empresa, 2026, 3) not in html


def test_mes_a_retificar_oferece_reabrir_e_nao_confirmar_de_novo(
    client, escritorio_a, empresa, usuario_gestor_a
):
    # Efetivar em mês confirmado reabre o mês "a retificar" (ajuste de domínio, DL-074).
    servico.confirmar_mes(empresa, 2026, 3, usuario_gestor_a)
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=911, competencia=(2026, 3), valor="50"
    )
    _logar(client, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 3)).content.decode()

    # Reaberto pela efetivação: o mês volta a ser confirmado por um ato NOVO (não há reabrir).
    assert "Situação: A retificar." in html
    assert _url_confirmar(empresa, 2026, 3) in html
    assert "Confirmar receita de 03/2026 completa" in html
    assert _url_reabrir(empresa, 2026, 3) not in html


def test_rbt12_mostra_a_regra_aplicada_e_os_meses_pendentes(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    # Abertura em 10/03/2026 e Simples no mesmo ano: PA 04/2026 usa o § 3º, com a janela em 03/2026.
    empresa = preparar_simples(
        empresa_a2, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _logar(client, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 4)).content.decode()

    assert "§ 3º (2º ao 12º mês de atividade, abertura no ano da opção)" in html
    assert "10/03/2026" in html
    assert "03/2026 (Não confirmado)" in html
    assert "Não apurável." in html

    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 3, Decimal("240000"))
    servico.confirmar_mes(empresa, 2026, 3, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 4)).content.decode()

    # Um mês de 240.000 confirmado: média × 12 = 2.880.000,00. Não há mais pendência da janela.
    assert "2.880.000,00" in html
    assert "Não apurável." not in html


def test_rbt12_sem_data_de_abertura_mostra_a_recusa_nomeada(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    empresa = preparar_simples(empresa_a2, abertura=None, inicio_simples=date(2018, 1, 1))
    _logar(client, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 3)).content.decode()

    assert "RBT12 não apurado:" in html
    assert "Informe a data de abertura no CNPJ" in html


def test_rbt12_de_2027_mostra_a_recusa_com_a_resolucao_190(
    client, escritorio_a, empresa, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2027, 1)).content.decode()

    assert "RBT12 não apurado:" in html
    assert "190/2026" in html


def test_avisos_de_sublimite_citam_o_dispositivo(client, escritorio_a, empresa, usuario_gestor_a):
    # Interno acumulado em 2026 de 3.700.000: passa do sublimite de 3.600.000 (Portaria CGSN
    # 54/2025), em excesso de até 20% (art. 81). Os 12 meses de 2025 são declarados completos
    # com zero, para que a janela do RBT12 seja apurável.
    confirmar_meses(empresa, usuario_gestor_a, sequencia(2025, 1, 12))
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 1, Decimal("3700000"))
    servico.confirmar_mes(empresa, 2026, 1, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 1)).content.decode()

    assert "passou do sublimite de 3600000.00" in html
    assert "excesso até 20%" in html
    # O dispositivo que motiva o aviso vai junto, como o texto do próprio serviço (rbt12.py).
    assert "Dispositivo:" in html
    assert "LC 123, art. 3º, §§ 11 e 13" in html
    assert "Res. CGSN 140, art. 12" in html
    # R5: o dispositivo da faixa do sublimite é o da HI-70 (art. 12, §§ 1º e 4º), não o art. 81.
    assert "Res. CGSN 140, art. 12, §§ 1º e 4º (HI-70, hipótese a confirmar)" in html
    assert "por analogia" not in html


def test_painel_com_receita_de_outro_mes_nao_entra_no_mes_pedido(
    client, escritorio_a, empresa, usuario_gestor_a
):
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 2, Decimal("700"))
    _logar(client, usuario_gestor_a)

    html = client.get(_url_painel(), _painel_de(empresa, 2026, 3)).content.decode()

    # A receita de 02/2026 não aparece na composição de 03/2026 (ela está só na janela do RBT12).
    assert "Nenhuma receita informada em 03/2026." in html
    assert re.search(
        r'Mercado interno</th>\s*<td class="valor-monetario">0,00</td>\s*'
        r'<td class="valor-monetario">0,00</td>\s*<td class="valor-monetario">0,00</td>',
        html,
    )


# ---------------------------------------------------------------------------
# Confirmação e reabertura do mês pela tela
# ---------------------------------------------------------------------------


def test_confirmar_mes_pela_tela_grava_e_recusa_sem_gravar(
    client, escritorio_a, empresa, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    primeira = client.post(_url_confirmar(empresa, 2026, 3))
    assert primeira.status_code == 302
    assert ConfirmacaoReceitaMensal.objects.filter(empresa=empresa, ano=2026, mes=3).count() == 1
    assert _confirmacao(empresa, 2026, 3).estado == "confirmada"

    # Repetir o ato: o serviço recusa, a mensagem aparece no painel, e nada muda.
    segunda = client.post(_url_confirmar(empresa, 2026, 3))
    assert segunda.status_code == 302
    html = client.get(_url_painel(), _painel_de(empresa, 2026, 3)).content.decode()
    assert "já está confirmada" in html
    assert ConfirmacaoReceitaMensal.objects.filter(empresa=empresa, ano=2026, mes=3).count() == 1


def test_reabrir_mes_pela_tela_exige_motivo(client, escritorio_a, empresa, usuario_gestor_a):
    servico.confirmar_mes(empresa, 2026, 3, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    sem_motivo = client.post(_url_reabrir(empresa, 2026, 3), {"motivo": "   "})

    assert sem_motivo.status_code == 200
    assert "Informe o motivo" in sem_motivo.content.decode()
    assert _confirmacao(empresa, 2026, 3).estado == "confirmada"

    com_motivo = client.post(
        _url_reabrir(empresa, 2026, 3), {"motivo": "Retificação do mês 03/2026."}
    )

    assert com_motivo.status_code == 302
    confirmacao = _confirmacao(empresa, 2026, 3)
    assert confirmacao.estado == "reaberta"
    assert confirmacao.motivo_reabertura == "Retificação do mês 03/2026."


# ---------------------------------------------------------------------------
# Receita informada: lançar, confirmar e estornar pela tela
# ---------------------------------------------------------------------------


def test_lancar_receita_pela_tela_recusa_historico_sem_gravar(
    client, escritorio_a, empresa, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    # Início de uso em 01/2024: "histórico" em 03/2024 é recusado (critério 7), sem gravar.
    recusada = client.post(
        _url_lancar(empresa),
        _lancamento_valido(origem="historico_pre_sistema", mes="03", ano="2024"),
    )

    assert recusada.status_code == 200
    assert "só vale para competência anterior" in recusada.content.decode()
    assert ReceitaInformada.objects.count() == 0


def test_lancar_receita_pela_tela_grava_rascunho_e_confirma_com_valor_em_pt_br(
    client, escritorio_a, empresa, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    rascunho = client.post(_url_lancar(empresa), _lancamento_valido(valor="100,00"))
    assert rascunho.status_code == 302
    assert ReceitaInformada.objects.get().estado == EstadoReceitaInformada.RASCUNHO

    confirmada = client.post(
        _url_lancar(empresa),
        _lancamento_valido(mes="05", valor="1.234,56", acao="confirmar"),
    )
    assert confirmada.status_code == 302
    receita = ReceitaInformada.objects.get(mes=5)
    assert receita.estado == EstadoReceitaInformada.CONFIRMADA
    assert receita.valor == Decimal("1234.56")


@pytest.mark.parametrize(
    "valor_recusado",
    ["10,555", "0", "-5,00", "12,3a", "1e3", "1.2.3", "1,2,3", ""],
)
def test_lancar_receita_pela_tela_recusa_valor_invalido_sem_gravar(
    client, escritorio_a, empresa, usuario_gestor_a, valor_recusado
):
    _logar(client, usuario_gestor_a)

    resposta = client.post(_url_lancar(empresa), _lancamento_valido(valor=valor_recusado))

    assert resposta.status_code == 200
    assert ReceitaInformada.objects.count() == 0


def test_lancar_confirmar_em_mes_confirmado_nao_grava_nada(
    client, escritorio_a, empresa, usuario_gestor_a
):
    servico.confirmar_mes(empresa, 2024, 3, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_lancar(empresa), _lancamento_valido(mes="03", ano="2024", acao="confirmar")
    )

    # O lançamento é um ato só com a confirmação: recusada a confirmação, nada é gravado.
    assert resposta.status_code == 200
    assert "já está confirmada" in resposta.content.decode()
    assert ReceitaInformada.objects.count() == 0


def test_confirmar_receita_informada_pela_tela(client, escritorio_a, empresa, usuario_gestor_a):
    receita = servico.lancar_receita_informada(
        empresa,
        2026,
        6,
        "interno",
        "50",
        ORIGEM_OUTRAS,
        "Lançamento sintético de teste.",
        "Extrato sintético de teste.",
        usuario_gestor_a,
        situacao_iss="proprio_municipio",
    )
    _logar(client, usuario_gestor_a)

    resposta = client.post(_url_confirmar_receita(empresa, receita))

    assert resposta.status_code == 302
    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.CONFIRMADA


def test_estornar_receita_pela_tela_exige_motivo(client, escritorio_a, empresa, usuario_gestor_a):
    receita = informar_e_confirmar(empresa, usuario_gestor_a, 2026, 8, Decimal("200"))
    servico.confirmar_mes(empresa, 2026, 8, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    sem_motivo = client.post(_url_estornar_receita(empresa, receita), {"motivo": ""})

    assert sem_motivo.status_code == 200
    assert "Informe o motivo" in sem_motivo.content.decode()
    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.CONFIRMADA

    com_motivo = client.post(
        _url_estornar_receita(empresa, receita), {"motivo": "Lançado em duplicidade."}
    )

    assert com_motivo.status_code == 302
    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.ESTORNADA
    # Mês confirmado: o estorno reabre e marca "a retificar" (Res. CGSN 140, art. 18).
    assert _confirmacao(empresa, 2026, 8).a_retificar is True


# ---------------------------------------------------------------------------
# Regime de caixa: só até 2026, com a fonte na recusa
# ---------------------------------------------------------------------------


def test_regime_caixa_pela_tela_recusa_2027(client, escritorio_a, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    recusada = client.post(_url_regime(empresa), {"ano": "2027"})

    html = recusada.content.decode()
    assert recusada.status_code == 200
    assert "2027 não é aceito" in html
    assert "HI-66" in html
    assert OpcaoRegimeCaixaSimples.objects.count() == 0


def test_regime_caixa_pela_tela_registra_2026_e_recusa_repetido(
    client, escritorio_a, empresa, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    primeira = client.post(_url_regime(empresa), {"ano": "2026"})
    assert primeira.status_code == 302
    assert OpcaoRegimeCaixaSimples.objects.filter(empresa=empresa, ano_calendario=2026).count() == 1

    repetida = client.post(_url_regime(empresa), {"ano": "2026"})
    assert repetida.status_code == 200
    assert "já foi registrada em 2026" in repetida.content.decode()
    assert OpcaoRegimeCaixaSimples.objects.filter(empresa=empresa, ano_calendario=2026).count() == 1


# ---------------------------------------------------------------------------
# Autorização: PARALEGAL consulta e não escreve; CLIENTE nada; anônimo, login
# ---------------------------------------------------------------------------


def test_paralegal_consulta_e_nao_escreve(client, paralegal_a, empresa, usuario_gestor_a):
    receita = servico.lancar_receita_informada(
        empresa,
        2026,
        9,
        "interno",
        "70",
        ORIGEM_OUTRAS,
        "Lançamento sintético de teste.",
        "Extrato sintético de teste.",
        usuario_gestor_a,
        situacao_iss="proprio_municipio",
    )
    _logar(client, paralegal_a)

    painel = client.get(_url_painel(), _painel_de(empresa, 2026, 9))

    html = painel.content.decode()
    assert painel.status_code == 200
    # Sem formulário de confirmação para quem não escritura: o botão aparece desabilitado,
    # com o motivo ao lado (direção de arte §2.B).
    assert _url_confirmar(empresa, 2026, 9) not in html
    assert "disabled" in html
    assert "não confirma" in html

    assert client.post(_url_confirmar(empresa, 2026, 9)).status_code == 403
    assert client.post(_url_reabrir(empresa, 2026, 9), {"motivo": "x"}).status_code == 403
    assert client.get(_url_lancar(empresa)).status_code == 403
    assert client.post(_url_lancar(empresa), _lancamento_valido()).status_code == 403
    assert client.post(_url_confirmar_receita(empresa, receita)).status_code == 403
    assert client.post(_url_estornar_receita(empresa, receita), {"motivo": "x"}).status_code == 403
    assert client.post(_url_regime(empresa), {"ano": "2026"}).status_code == 403

    # Nada foi gravado pelas tentativas: a receita continua em rascunho e sem confirmação.
    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.RASCUNHO
    assert not ConfirmacaoReceitaMensal.objects.filter(empresa=empresa, ano=2026, mes=9).exists()
    assert OpcaoRegimeCaixaSimples.objects.count() == 0


def test_paralegal_consulta_o_regime_de_caixa(client, paralegal_a, empresa):
    _logar(client, paralegal_a)

    assert client.get(_url_regime(empresa)).status_code == 200


def test_cliente_e_recusado_em_todas_as_telas(client, usuario_cliente_a, empresa, escritorio_a):
    receita = informar_e_confirmar(empresa, usuario_cliente_a, 2026, 10, Decimal("10"))
    _logar(client, usuario_cliente_a)

    assert client.get(_url_painel(), _painel_de(empresa, 2026, 10)).status_code == 403
    assert client.post(_url_confirmar(empresa, 2026, 10)).status_code == 403
    assert client.get(_url_regime(empresa)).status_code == 403
    assert client.post(_url_regime(empresa), {"ano": "2026"}).status_code == 403
    assert client.get(_url_estornar_receita(empresa, receita)).status_code == 403
    assert not ConfirmacaoReceitaMensal.objects.filter(empresa=empresa, ano=2026, mes=10).exists()


@pytest.mark.parametrize(
    "nome_rota,argumentos",
    [
        ("fiscal_web:receita_do_mes", []),
        ("fiscal_web:regime_caixa", [1]),
        ("fiscal_web:receita_informada_nova", [1]),
    ],
)
def test_anonimo_e_redirecionado_ao_login(client, nome_rota, argumentos):
    resposta = client.get(reverse(nome_rota, args=argumentos))

    assert resposta.status_code == 302
    assert "login" in resposta["Location"]


# ---------------------------------------------------------------------------
# Isolamento: outro escritório e outra empresa do mesmo escritório recebem 404
# ---------------------------------------------------------------------------


def test_outro_escritorio_recebe_404_nas_telas_da_empresa(
    client, gestor_b, empresa, usuario_gestor_a
):
    _logar(client, gestor_b)

    assert client.get(_url_painel(), _painel_de(empresa, 2026, 3)).status_code == 404
    assert client.post(_url_confirmar(empresa, 2026, 3)).status_code == 404
    assert client.post(_url_reabrir(empresa, 2026, 3), {"motivo": "x"}).status_code == 404
    assert client.get(_url_lancar(empresa)).status_code == 404
    assert client.post(_url_lancar(empresa), _lancamento_valido()).status_code == 404
    assert client.get(_url_regime(empresa)).status_code == 404
    assert client.post(_url_regime(empresa), {"ano": "2026"}).status_code == 404
    assert not ReceitaInformada.objects.exists()
    assert not ConfirmacaoReceitaMensal.objects.exists()


def test_receita_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, empresa, empresa_a2, usuario_gestor_a
):
    receita = servico.lancar_receita_informada(
        empresa,
        2026,
        4,
        "interno",
        "30",
        ORIGEM_OUTRAS,
        "Lançamento sintético de teste.",
        "Extrato sintético de teste.",
        usuario_gestor_a,
        situacao_iss="proprio_municipio",
    )
    _logar(client, usuario_gestor_a)

    # A receita é da `empresa`; pedida pela URL de `empresa_a2` (mesmo escritório): 404.
    assert client.post(_url_confirmar_receita(empresa_a2, receita)).status_code == 404
    assert client.get(_url_estornar_receita(empresa_a2, receita)).status_code == 404
    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.RASCUNHO


# ---------------------------------------------------------------------------
# Menu e atalho da home
# ---------------------------------------------------------------------------


def test_menu_fiscal_mostra_receita_do_mes_a_quem_consulta(client, paralegal_a, usuario_cliente_a):
    _logar(client, paralegal_a)
    html = client.get(reverse("tenancy:painel")).content.decode()
    assert "Simples Nacional" in html
    assert _url_painel() in html

    _logar(client, usuario_cliente_a)
    assert _url_painel() not in client.get(reverse("tenancy:painel")).content.decode()


def test_home_do_fiscal_tem_atalho_para_a_receita_do_mes(
    client, escritorio_a, empresa, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(reverse("module_home:home", args=["fiscal"]))

    atalhos = resposta.context["home"]["atalhos"]
    assert resposta.status_code == 200
    assert any(
        atalho["url"].startswith(_url_painel()) and atalho["rotulo"] == "Receita do mês (Simples)"
        for atalho in atalhos
    )
    assert urlencode({"empresa": empresa.pk}) in next(
        atalho["url"] for atalho in atalhos if atalho["rotulo"] == "Receita do mês (Simples)"
    )
