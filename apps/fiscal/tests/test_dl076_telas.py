"""DL-076 (frente B) — telas do ISS por município: apuração do ISS próprio, ISS retido sofrido,
ISS devido a outros municípios, alíquotas do escritório, regime por exercício e regras (leitura).

A regra é a da frente A (`apps.fiscal.iss_municipal`): aqui se prova que a TELA mostra o que o
serviço calcula, recusa e não grava o que o serviço recusa, e que a autorização e o isolamento são
verificados no servidor.

- Dados 100% sintéticos (`suporte_iss_dl076`, `xml_iss_dl076`). Nenhum dado de cliente.
- Os valores esperados estão escritos À MÃO, com a aritmética do cenário de Palmas (ver o quadro em
  `suporte_iss_dl076.cenario_outubro` e em `test_dl076_apuracao`). A tela não é a fonte do número.
- Conferência (classe 1): nada é gerado nem transmitido, e a tela diz isso.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
    NOMES_DE_TELA_FISCAL_FORA_DA_CONTABILIDADE,
    assert_moldura_acessivel,
)
from apps.fiscal import views_web
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    RegimeIss,
    RegimeIssEmpresa,
)
from apps.fiscal.tests.suporte_iss_dl076 import (
    DEVIDO,
    OUTRO_MUNICIPIO,
    PALMAS,
    cenario_outubro,
    receber,
    regime_aliquota,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 10
TEXTO_DE_CONFERENCIA = (
    "Conferência para emissão da guia no portal do município — o DataLedger não gera guia nem "
    "transmite."
)


# ---------------------------------------------------------------------------
# Fábrica, URLs e linhas de tabela
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


def _linha(html, rotulo):
    """O `<tr>` que começa com a célula de cabeçalho `rotulo` (o número da nota, por exemplo)."""
    casamento = re.search(
        rf'<tr>\s*<th scope="row">{re.escape(rotulo)}</th>.*?</tr>', html, re.DOTALL
    )
    assert casamento, f"linha {rotulo!r} não encontrada na tela"
    return casamento.group(0)


def _celulas_monetarias(linha):
    return re.findall(r'<td class="valor-monetario">([^<]*)</td>', linha)


@pytest.fixture
def paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl076-telas")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-dl076-telas")


@pytest.fixture
def cenario(escritorio_a, usuario_gestor_a, empresa_a):
    """Palmas, regime por alíquota em 2026, alíquotas 17.01 (5%) e 07.02 (3%), notas de 10/2026."""
    return cenario_outubro(escritorio_a, usuario_gestor_a, empresa_a)


def _url_apuracao(empresa, ano=ANO, mes=MES):
    return reverse("fiscal_web:iss_apuracao") + f"?empresa={empresa.pk}&ano={ano}&mes={mes}"


def _url_retido(empresa, ano=ANO, mes=MES):
    return reverse("fiscal_web:iss_retido_sofrido") + f"?empresa={empresa.pk}&ano={ano}&mes={mes}"


def _url_outros(empresa, ano=ANO, mes=MES):
    return (
        reverse("fiscal_web:iss_outros_municipios") + f"?empresa={empresa.pk}&ano={ano}&mes={mes}"
    )


def _url_regimes(empresa=None):
    url = reverse("fiscal_web:iss_regimes")
    return f"{url}?empresa={empresa.pk}" if empresa is not None else url


def _url_aliquotas(municipio=None):
    url = reverse("fiscal_web:iss_aliquotas")
    return f"{url}?municipio={municipio}" if municipio else url


def _url_nova_aliquota():
    return reverse("fiscal_web:iss_aliquota_nova")


def _url_editar_aliquota(aliquota_obj):
    return reverse("fiscal_web:iss_aliquota_editar", args=[aliquota_obj.pk])


def _url_encerrar_aliquota(aliquota_obj):
    return reverse("fiscal_web:iss_aliquota_encerrar", args=[aliquota_obj.pk])


def _url_regime_novo(empresa):
    return reverse("fiscal_web:iss_regime_novo", args=[empresa.pk])


def _url_regime_editar(empresa, regime):
    return reverse("fiscal_web:iss_regime_editar", args=[empresa.pk, regime.pk])


def _aliquota_valida(**sobrescritas):
    """Dados de um POST válido do cadastro de alíquota. Sobrescreva o que o teste muda."""
    dados = {
        "municipio_ibge": PALMAS,
        "subitem": "17.02",
        "percentual": "4,00",
        "fonte": "Lei municipal sintética de teste (DL-076), consulta de 08/10/2026",
        "inicio": "01/01/2027",
        "fim": "",
    }
    dados.update(sobrescritas)
    return dados


def _regime_valido(**sobrescritas):
    dados = {"exercicio": "2027", "regime": RegimeIss.FIXO_AUTONOMO, "municipio_ibge": PALMAS}
    dados.update(sobrescritas)
    return dados


# ---------------------------------------------------------------------------
# Formatação pt-BR (apresentação; o cálculo não passa por aqui)
# ---------------------------------------------------------------------------


def test_formatacao_pt_br_de_aliquota_memoria_e_municipio():
    # Alíquota em pontos, com 4 casas e '%': 5 vira 5,0000% (nunca 5% nem 0,05).
    assert views_web._aliquota_ptbr(Decimal("5.00")) == "5,0000%"
    assert views_web._aliquota_ptbr(Decimal("4.5")) == "4,5000%"
    assert views_web._aliquota_ptbr(None) == "—"
    # Dinheiro com milhar e vírgula decimal.
    assert views_web._dinheiro_ptbr(Decimal("1000.00")) == "1.000,00"
    assert views_web._dinheiro_ptbr(Decimal("237.70")) == "237,70"
    # A memória troca só o valor monetário ('237.70'), nunca dispositivo, data ou código.
    assert views_web._valor_da_memoria_na_tela("237.70") == "237,70"
    assert views_web._valor_da_memoria_na_tela("1234.56") == "1.234,56"
    assert views_web._valor_da_memoria_na_tela("3") == "3"
    assert views_web._valor_da_memoria_na_tela("1721000") == "1721000"
    assert views_web._valor_da_memoria_na_tela("Decreto 1.667/2018") == "Decreto 1.667/2018"
    # Município: nome da regra mais o código; sem regra, o código cru, sem nome inventado.
    assert views_web._rotulo_do_municipio(PALMAS, {PALMAS: "Palmas (TO)"}) == (
        "Palmas (TO) (1721000)"
    )
    assert views_web._rotulo_do_municipio("1100205", {}) == (
        "Código 1100205 (sem regra cadastrada)"
    )


# ---------------------------------------------------------------------------
# Apuração do ISS próprio (tela 1)
# ---------------------------------------------------------------------------


def test_tela_iss_apuracao_e_acessivel(client, cenario, empresa_a, usuario_gestor_a):
    """Competência 10/2026 de Palmas, com os valores escritos à mão.

    Total = 50,00 + 6,00 + 16,67 + 40,00 + 50,01 + 50,02 + 25,00 = 237,70.
    Pendências: 1004 (ISS 40,00 contra 50,00 esperado) e 1006 (diferença 0,02). Conferida: 1005,
    diferença 0,01, dentro da tolerância. Vencimento: 10/11/2026 (próprio) e 15/11/2026 (retido).
    """
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_apuracao(empresa_a))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fiscal/iss_apuracao.html" in [t.name for t in resposta.templates]
    assert TEXTO_DE_CONFERENCIA in html
    assert "Total a recolher de 10/2026" in html
    assert re.search(
        r'Total a recolher \(soma do vISSQN[^<]*</dt>\s*<dd class="valor-monetario">237,70</dd>',
        html,
    )
    assert "10/11/2026" in html and "15/11/2026" in html
    assert "primeiro dia útil seguinte" in html  # regra do dia não útil, como texto
    assert "Decreto 1.667/2018" in html
    assert "Pendências de conferência: 2" in html

    # Conferência nota a nota: base, alíquota da nota, ISS, alíquota cadastrada, esperado, dif.
    nota_1004 = _linha(html, "1004")
    assert _celulas_monetarias(nota_1004) == [
        "1.000,00",
        "5,0000%",
        "40,00",
        "5,0000%",
        "50,0000",
        "-10,0000",
    ]
    assert "Pendência: o ISS da nota difere" in nota_1004

    nota_1006 = _linha(html, "1006")
    assert _celulas_monetarias(nota_1006)[-1] == "0,0200"
    assert "50,02" in _celulas_monetarias(nota_1006)

    nota_1005 = _linha(html, "1005")
    assert "Conferida" in nota_1005 and "Pendência" not in nota_1005

    # Alíquota da nota vem do XML (1002 foi escriturada com 3%); cadastrada, do escritório.
    nota_1002 = _linha(html, "1002")
    assert _celulas_monetarias(nota_1002)[1] == "3,0000%"
    assert _celulas_monetarias(nota_1002)[3] == "3,0000%"

    # Memória: o passo 4 traz o total já em pt-BR, com o dispositivo do passo.
    assert re.search(
        r"<td>Total a recolher[^<]*</td>\s*<td class=\"valor-monetario\">237,70</td>", html
    )

    # Nota de outro município escriturada como devida aparece no aviso, nunca no total.
    assert "Nota 7001" in html and "cLocIncid 1100205" in html

    assert_moldura_acessivel(html)


def test_tela_iss_apuracao_recusada_lista_bloqueios_com_caminho(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    """Sem alíquota do subitem 17.01, a apuração recusa e a tela lista o bloqueio, com o link para
    cadastrar a alíquota já com o município do estabelecimento. Nada é gravado."""
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1001,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_apuracao(empresa_a))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "ISS próprio não apurado em 10/2026" in html
    assert "Sem alíquota cadastrada que cubra 10/2026 inteiro" in html
    assert "subitem(ns): 17.01 (notas 1001)" in html
    assert "Cadastrar a alíquota do subitem" in html
    assert f"{_url_nova_aliquota()}?municipio={PALMAS}" in html
    assert "Total a recolher de 10/2026" not in html
    assert AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a).count() == 0
    assert_moldura_acessivel(html)


def test_tela_iss_apuracao_sem_regime_aponta_o_cadastro_do_regime(
    client, empresa_a, usuario_gestor_a
):
    """Sem regime no exercício não se presume regime: a tela manda cadastrar o regime."""
    _logar(client, usuario_gestor_a)

    html = client.get(_url_apuracao(empresa_a)).content.decode()

    assert "Não há regime do ISS cadastrado para 2026." in html
    assert "Ver ou cadastrar o regime do ISS" in html
    assert _url_regimes(empresa_a) in html


def test_tela_iss_apuracao_regime_fixo_lista_notas_para_conferencia(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    """Regime fixo de autônomo: não há apuração por alíquota. A tela lista as notas da competência
    para conferência, sem nenhum total."""
    RegimeIssEmpresa.objects.create(
        empresa=empresa_a,
        exercicio=ANO,
        regime=RegimeIss.FIXO_AUTONOMO,
        municipio_ibge=PALMAS,
        criado_por=usuario_gestor_a,
    )
    receber(escritorio_a, usuario_gestor_a, 1101, DEVIDO, v_bc="800.00", v_iss_qn="40.00")
    _logar(client, usuario_gestor_a)

    html = client.get(_url_apuracao(empresa_a)).content.decode()

    assert "Regime fixo (Fixo de autônomo) em 2026" in html
    assert "São 1 nota(s) escrituradas em 10/2026 para conferência." in html
    assert "Notas escrituradas na competência, sem apuração por alíquota" in html
    nota = _linha(html, "1101")
    assert _celulas_monetarias(nota) == ["800,00", "40,00"]
    assert "Total a recolher de 10/2026" not in html
    assert_moldura_acessivel(html)


def test_tela_iss_apuracao_sem_empresa_pede_a_escolha_e_nao_lista_as_outras(
    client, cenario, empresa_a, empresa_a2, usuario_gestor_a
):
    """Sem empresa, a tela pede a escolha; com uma escolhida, não repete o nome das outras
    (direção de arte §8.1)."""
    _logar(client, usuario_gestor_a)

    sem_empresa = client.get(reverse("fiscal_web:iss_apuracao")).content.decode()
    assert "Escolha uma empresa para ver a apuração do ISS do mês." in sem_empresa
    assert "Tomadora A2 Ltda" in sem_empresa

    com_empresa = client.get(_url_apuracao(empresa_a)).content.decode()
    assert "Prestadora A Ltda" in com_empresa
    assert "Tomadora A2 Ltda" not in com_empresa


def test_tela_iss_apuracao_competencia_invalida_responde_400(
    client, cenario, empresa_a, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(
        reverse("fiscal_web:iss_apuracao"), {"empresa": empresa_a.pk, "ano": "2026", "mes": "13"}
    )

    assert resposta.status_code == 400
    assert "Competência inválida" in resposta.content.decode()


# ---------------------------------------------------------------------------
# ISS retido sofrido (tela 2) e ISS devido a outros municípios (tela 3)
# ---------------------------------------------------------------------------


def test_tela_iss_retido_sofrido_totais_por_municipio(client, cenario, empresa_a, usuario_gestor_a):
    """Retido sofrido de 10/2026: a nota 2001 (ISS 30,00, base 1.000,00, retida pelo tomador) é o
    único valor; o total de Palmas é 30,00, e o vencimento informativo do retido é 15/11/2026.
    A nota de outro município (3001) não entra: é do relatório de outros municípios."""
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_retido(empresa_a))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "ISS retido sofrido" in html
    assert "Palmas (TO) (1721000)" in html
    assert re.search(
        r'<th scope="row">Palmas \(TO\) \(1721000\)</th>\s*<td class="valor-monetario">30,00</td>',
        html,
    )
    assert re.search(r'<td class="valor-monetario">15/11/2026</td>', html)
    nota = _linha(html, "2001")
    assert _celulas_monetarias(nota) == ["1.000,00", "5,0000%", "30,00"]
    assert "Retido pelo tomador" in nota
    # A nota de outro município (3001) não é linha do retido sofrido.
    assert '<th scope="row">3001</th>' not in html
    assert TEXTO_DE_CONFERENCIA in html
    assert_moldura_acessivel(html)


def test_tela_iss_outros_municipios_totais_por_municipio(
    client, cenario, empresa_a, usuario_gestor_a
):
    """Outros municípios de 10/2026: a nota 3001 (ISS 99,00 para o município 1100205, sem regra
    cadastrada) é o único valor. Como o subitem 17.01 não está nas exceções do art. 3º da LC 116 e a
    incidência não é em Palmas, a tela mostra o aviso com o dispositivo."""
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_outros(empresa_a))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "ISS devido a outros municípios" in html
    assert re.search(
        r'<th scope="row">Código 1100205 \(sem regra cadastrada\)</th>\s*'
        r'<td class="valor-monetario">99,00</td>',
        html,
    )
    assert _celulas_monetarias(_linha(html, "3001")) == ["1.000,00", "5,0000%", "99,00"]
    assert "Nota 3001: subitem 17.01 não está nas exceções do art. 3º da LC 116" in html
    # O retido (2001) não é linha de outros municípios.
    assert '<th scope="row">2001</th>' not in html
    assert_moldura_acessivel(html)


def test_relatorios_municipais_exigem_empresa_de_outro_escritorio_404(
    client, cenario, empresa_a, gestor_b
):
    """Empresa de OUTRO escritório é 404 nos dois relatórios, e a tela não confirma que existe."""
    _logar(client, gestor_b)

    assert client.get(_url_retido(empresa_a)).status_code == 404
    assert client.get(_url_outros(empresa_a)).status_code == 404
    assert client.get(_url_apuracao(empresa_a)).status_code == 404


# ---------------------------------------------------------------------------
# Alíquotas do escritório (tela 4): listar, cadastrar, alterar e encerrar
# ---------------------------------------------------------------------------


def test_tela_iss_aliquotas_lista_vigencia_fonte_e_autor(client, cenario, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_aliquotas())

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Alíquotas do ISS do escritório" in html
    # O subitem é célula comum (não cabeçalho de linha): confere pelo marcado da célula.
    assert "<td>17.01</td>" in html
    assert "<td>07.02</td>" in html
    assert "5,0000%" in html and "3,0000%" in html
    assert "desde 01/01/2026, em aberto" in html
    assert "Alíquota sintética de teste (DL-076)" in html
    assert "gestor-fiscal-a" in html
    # Faixa e exceção do art. 8º-A § 1º: texto da lei, lido do serviço.
    assert "Faixa de 2% a 5% (LC 116/2003, art. 8º, II, e art. 8º-A)" in html
    assert "07.02, 07.05, 16.01" in html
    assert_moldura_acessivel(html)


def test_tela_iss_aliquotas_filtra_por_municipio_e_recusa_codigo_invalido(
    client, cenario, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    sem_resultado = client.get(_url_aliquotas("1100205")).content.decode()
    assert "Nenhuma alíquota cadastrada para o município 1100205." in sem_resultado

    invalido = client.get(reverse("fiscal_web:iss_aliquotas"), {"municipio": "172"})
    assert invalido.status_code == 400
    assert "Município: informe o código IBGE com 7 dígitos." in invalido.content.decode()


def test_tela_iss_aliquota_nova_e_acessivel(client, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_nova_aliquota(), {"municipio": PALMAS})

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fiscal/iss_aliquota_form.html" in [t.name for t in resposta.templates]
    assert 'value="1721000"' in html
    assert "Fonte (dispositivo, documento e data de consulta)" in html
    assert "Início da vigência" in html
    assert_moldura_acessivel(html)


def test_cadastrar_aliquota_pela_tela(client, cenario, escritorio_a, usuario_gestor_a):
    """O caminho feliz grava com trilha; cada recusa responde 200 ou 400 e NÃO grava."""
    _logar(client, usuario_gestor_a)
    antes = AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a).count()

    # Caminho feliz: 17.02 a 4,00% a partir de 2027. Grava e volta para a lista.
    feliz = client.post(_url_nova_aliquota(), _aliquota_valida())
    assert feliz.status_code == 302
    criada = AliquotaIssMunicipal.objects.get(escritorio=escritorio_a, subitem="17.02")
    assert criada.percentual == Decimal("4.0000")
    assert criada.inicio_vigencia == date(2027, 1, 1)
    assert criada.fim_vigencia is None
    assert criada.criada_por == usuario_gestor_a
    assert AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a).count() == antes + 1

    # Abaixo de 2% em subitem que não é exceção: recusa com a faixa, nada gravado.
    abaixo = client.post(_url_nova_aliquota(), _aliquota_valida(subitem="17.03", percentual="1,50"))
    assert abaixo.status_code == 200
    assert "Alíquota de 1.5000% abaixo do mínimo de 2%" in abaixo.content.decode()

    # Acima de 5%: recusa com o máximo, nada gravado.
    acima = client.post(_url_nova_aliquota(), _aliquota_valida(subitem="17.04", percentual="5,01"))
    assert acima.status_code == 200
    assert "acima do máximo de 5%" in acima.content.decode()

    # Vigência sobreposta à alíquota de 17.01 (em aberto desde 01/01/2026): recusa.
    sobreposta = client.post(
        _url_nova_aliquota(),
        _aliquota_valida(subitem="17.01", percentual="5,00", inicio="01/06/2026"),
    )
    assert sobreposta.status_code == 200
    assert "vigência sobreposta" in sobreposta.content.decode()

    # Percentual com ponto de milhar ambíguo: a tela pede a vírgula.
    ambiguo = client.post(
        _url_nova_aliquota(), _aliquota_valida(subitem="17.05", percentual="1.000")
    )
    assert ambiguo.status_code == 200
    assert "Valor ambíguo" in ambiguo.content.decode()

    # Data inválida: recusa, nada gravado.
    data_invalida = client.post(
        _url_nova_aliquota(), _aliquota_valida(subitem="17.06", inicio="31/02/2027")
    )
    assert data_invalida.status_code == 200
    assert "início da vigência é uma data inválida" in data_invalida.content.decode()

    # Campo fora do contrato: 400, nada gravado.
    fora_do_contrato = client.post(
        _url_nova_aliquota(), _aliquota_valida(subitem="17.07", extra="x")
    )
    assert fora_do_contrato.status_code == 400

    assert AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a).count() == antes + 1
    assert not AliquotaIssMunicipal.objects.filter(
        subitem__in=["17.03", "17.04", "17.05", "17.06", "17.07"]
    ).exists()


def test_cadastro_de_excecao_do_art_8a_grava_com_aviso_visivel(
    client, cenario, escritorio_a, usuario_gestor_a
):
    """07.02 a 1,50% é exceção do § 1º do art. 8º-A: entra, e o aviso aparece na lista."""
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_nova_aliquota(),
        _aliquota_valida(subitem="07.05", percentual="1,50", inicio="01/01/2027"),
        follow=True,
    )

    assert resposta.redirect_chain
    html = resposta.content.decode()
    assert "Atenção:" in html
    assert (
        "O subitem 07.05 está na exceção do § 1º do art. 8º-A da LC 116: entra, com este aviso."
        in html
    )
    assert AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a, subitem="07.05").exists()


def test_alterar_aliquota_pela_tela(client, cenario, escritorio_a, usuario_gestor_a):
    alterada = AliquotaIssMunicipal.objects.get(escritorio=escritorio_a, subitem="17.01")
    _logar(client, usuario_gestor_a)

    formulario = client.get(_url_editar_aliquota(alterada))
    assert formulario.status_code == 200
    # Percentual volta em pt-BR, como o contador digita: 5,0000, não 5.0000.
    assert 'value="5,0000"' in formulario.content.decode()

    # Altera a fonte e a alíquota; a vigência continua valendo.
    feliz = client.post(
        _url_editar_aliquota(alterada),
        _aliquota_valida(
            subitem="17.01",
            percentual="4,50",
            fonte="Lei municipal sintética revisada (DL-076)",
            inicio="01/01/2026",
        ),
    )
    assert feliz.status_code == 302
    alterada.refresh_from_db()
    assert alterada.percentual == Decimal("4.5000")
    assert alterada.fonte == "Lei municipal sintética revisada (DL-076)"
    assert alterada.alterada_por == usuario_gestor_a

    # Recusa de faixa na alteração: nada muda.
    recusada = client.post(
        _url_editar_aliquota(alterada),
        _aliquota_valida(subitem="17.01", percentual="0,50", inicio="01/01/2026"),
    )
    assert recusada.status_code == 200
    assert "abaixo do mínimo de 2%" in recusada.content.decode()
    alterada.refresh_from_db()
    assert alterada.percentual == Decimal("4.5000")


def test_encerrar_aliquota_pela_tela(client, cenario, escritorio_a, usuario_gestor_a):
    """Encerrar é informar o fim da vigência: a alíquota vale até essa data, inclusive, e o
    registro continua no histórico. Fim anterior ao início, ou em branco, não grava."""
    alvo = AliquotaIssMunicipal.objects.get(escritorio=escritorio_a, subitem="07.02")
    _logar(client, usuario_gestor_a)

    assert client.get(_url_encerrar_aliquota(alvo)).status_code == 200

    em_branco = client.post(_url_encerrar_aliquota(alvo), {"fim": ""})
    assert em_branco.status_code == 200
    assert "Informe o fim da vigência em dd/mm/aaaa" in em_branco.content.decode()

    antes_do_inicio = client.post(_url_encerrar_aliquota(alvo), {"fim": "31/12/2025"})
    assert antes_do_inicio.status_code == 200
    assert "O fim da vigência é anterior ao início." in antes_do_inicio.content.decode()
    alvo.refresh_from_db()
    assert alvo.fim_vigencia is None

    feliz = client.post(_url_encerrar_aliquota(alvo), {"fim": "31/12/2026"})
    assert feliz.status_code == 302
    alvo.refresh_from_db()
    assert alvo.fim_vigencia == date(2026, 12, 31)
    assert AliquotaIssMunicipal.objects.filter(pk=alvo.pk).exists()  # sem exclusão


# ---------------------------------------------------------------------------
# Regime do ISS por empresa e exercício (tela 5)
# ---------------------------------------------------------------------------


def test_tela_iss_regimes_e_acessivel(client, cenario, empresa_a, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_regimes(empresa_a))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Alíquota (apuração por nota)" in html
    assert "Palmas (TO) (1721000)" in html
    assert reverse("fiscal_web:iss_regime_novo", args=[empresa_a.pk]) in html
    assert "Regime por exercício." in html
    assert_moldura_acessivel(html)


def test_regimes_sem_empresa_pedem_a_escolha(client, cenario, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    html = client.get(_url_regimes()).content.decode()

    assert "Escolha uma empresa para ver o regime do ISS." in html


def test_cadastrar_regime_pela_tela(client, cenario, empresa_a, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    assert client.get(_url_regime_novo(empresa_a)).status_code == 200

    feliz = client.post(_url_regime_novo(empresa_a), _regime_valido())
    assert feliz.status_code == 302
    assert feliz["Location"].endswith(f"/iss/regimes/?empresa={empresa_a.pk}")
    criado = RegimeIssEmpresa.objects.get(empresa=empresa_a, exercicio=2027)
    assert criado.regime == RegimeIss.FIXO_AUTONOMO
    assert criado.criado_por == usuario_gestor_a

    # Segundo regime no mesmo exercício: recusa com o motivo, nada gravado.
    duplicado = client.post(_url_regime_novo(empresa_a), _regime_valido(exercicio="2027"))
    assert duplicado.status_code == 200
    assert (
        "Já há regime do ISS cadastrado para esta empresa neste exercício"
        in duplicado.content.decode()
    )

    # Regime fora do catálogo, e exercício com dígitos faltando: recusa, nada gravado.
    fora = client.post(_url_regime_novo(empresa_a), _regime_valido(exercicio="2028", regime="xyz"))
    assert fora.status_code == 200
    assert "Regime do ISS fora do catálogo" in fora.content.decode()

    sem_ano = client.post(_url_regime_novo(empresa_a), _regime_valido(exercicio="20x8"))
    assert sem_ano.status_code == 200
    assert "Informe o exercício com quatro dígitos (AAAA)." in sem_ano.content.decode()

    # Campo fora do contrato: 400.
    fora_do_contrato = client.post(
        _url_regime_novo(empresa_a), _regime_valido(exercicio="2029", extra="x")
    )
    assert fora_do_contrato.status_code == 400

    assert RegimeIssEmpresa.objects.filter(empresa=empresa_a).count() == 2  # 2026 (cenário) e 2027
    assert not RegimeIssEmpresa.objects.filter(
        empresa=empresa_a, exercicio__in=[2028, 2029]
    ).exists()


def test_alterar_regime_pela_tela(client, cenario, empresa_a, usuario_gestor_a):
    regime = RegimeIssEmpresa.objects.get(empresa=empresa_a, exercicio=ANO)
    _logar(client, usuario_gestor_a)

    formulario = client.get(_url_regime_editar(empresa_a, regime))
    assert formulario.status_code == 200
    assert f'value="{PALMAS}"' in formulario.content.decode()

    feliz = client.post(
        _url_regime_editar(empresa_a, regime),
        _regime_valido(
            exercicio=str(ANO), regime=RegimeIss.ALIQUOTA, municipio_ibge=OUTRO_MUNICIPIO
        ),
    )
    assert feliz.status_code == 302
    regime.refresh_from_db()
    assert regime.municipio_ibge == OUTRO_MUNICIPIO
    assert regime.alterado_por == usuario_gestor_a


# ---------------------------------------------------------------------------
# Regras do município (tela 6, só leitura)
# ---------------------------------------------------------------------------


def test_tela_iss_regras_municipio_e_acessivel(client, usuario_gestor_a):
    """A regra de Palmas vem da migração 0006 (Decreto 1.667/2018, art. 86 § 3º): dia 10, dia 15."""
    _logar(client, usuario_gestor_a)

    resposta = client.get(reverse("fiscal_web:iss_regras_municipio"))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Somente leitura." in html
    assert "Palmas (TO) (1721000)" in html
    assert "Dia 10" in html and "Dia 15" in html
    assert "Decreto 1.667/2018 (RCTM de Palmas), art. 86 § 3º" in html
    assert "desde 01/01/2019, em aberto" in html
    assert_moldura_acessivel(html)


def test_regras_do_municipio_nao_aceitam_escrita(client, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    assert client.post(reverse("fiscal_web:iss_regras_municipio"), {}).status_code == 405


# ---------------------------------------------------------------------------
# Permissões: CLIENTE não lê; PARALEGAL lê e não escreve; anônimo vai ao login
# ---------------------------------------------------------------------------


def test_cliente_e_recusado_em_todas_as_telas_do_iss(
    client, cenario, empresa_a, usuario_cliente_a, usuario_gestor_a
):
    alvo = AliquotaIssMunicipal.objects.get(escritorio=empresa_a.escritorio, subitem="17.01")
    regime = RegimeIssEmpresa.objects.get(empresa=empresa_a, exercicio=ANO)
    _logar(client, usuario_cliente_a)

    assert client.get(_url_apuracao(empresa_a)).status_code == 403
    assert client.get(_url_retido(empresa_a)).status_code == 403
    assert client.get(_url_outros(empresa_a)).status_code == 403
    assert client.get(_url_aliquotas()).status_code == 403
    assert client.get(_url_regimes(empresa_a)).status_code == 403
    assert client.get(reverse("fiscal_web:iss_regras_municipio")).status_code == 403
    assert client.get(_url_nova_aliquota()).status_code == 403
    assert client.post(_url_nova_aliquota(), _aliquota_valida()).status_code == 403
    assert client.post(_url_encerrar_aliquota(alvo), {"fim": "31/12/2026"}).status_code == 403
    assert client.post(_url_regime_novo(empresa_a), _regime_valido()).status_code == 403
    assert client.post(_url_regime_editar(empresa_a, regime), _regime_valido()).status_code == 403

    alvo.refresh_from_db()
    assert alvo.fim_vigencia is None
    assert AliquotaIssMunicipal.objects.filter(subitem="17.02").count() == 0


def test_paralegal_le_as_telas_e_nao_escreve(
    client, cenario, empresa_a, paralegal_a, usuario_gestor_a
):
    alvo = AliquotaIssMunicipal.objects.get(escritorio=empresa_a.escritorio, subitem="17.01")
    regime = RegimeIssEmpresa.objects.get(empresa=empresa_a, exercicio=ANO)
    _logar(client, paralegal_a)

    assert client.get(_url_apuracao(empresa_a)).status_code == 200
    assert client.get(_url_retido(empresa_a)).status_code == 200
    assert client.get(_url_outros(empresa_a)).status_code == 200
    assert client.get(_url_aliquotas()).status_code == 200
    assert client.get(_url_regimes(empresa_a)).status_code == 200
    assert client.get(reverse("fiscal_web:iss_regras_municipio")).status_code == 200

    # Quem só consulta vê o botão desabilitado com o motivo, e o POST é recusado no servidor.
    html = client.get(_url_aliquotas()).content.decode()
    assert "disabled" in html
    assert "não cadastra nem altera alíquota ou regime" in html

    assert client.get(_url_nova_aliquota()).status_code == 403
    assert client.post(_url_nova_aliquota(), _aliquota_valida()).status_code == 403
    assert client.post(_url_encerrar_aliquota(alvo), {"fim": "31/12/2026"}).status_code == 403
    assert client.post(_url_regime_novo(empresa_a), _regime_valido()).status_code == 403
    assert client.post(_url_regime_editar(empresa_a, regime), _regime_valido()).status_code == 403

    # Nada foi gravado pelas tentativas.
    alvo.refresh_from_db()
    assert alvo.fim_vigencia is None
    regime.refresh_from_db()
    assert regime.regime == RegimeIss.ALIQUOTA
    assert not AliquotaIssMunicipal.objects.filter(subitem="17.02").exists()
    assert not RegimeIssEmpresa.objects.filter(empresa=empresa_a, exercicio=2027).exists()


@pytest.mark.parametrize(
    "nome_rota,argumentos",
    [
        ("fiscal_web:iss_apuracao", []),
        ("fiscal_web:iss_retido_sofrido", []),
        ("fiscal_web:iss_outros_municipios", []),
        ("fiscal_web:iss_aliquotas", []),
        ("fiscal_web:iss_aliquota_nova", []),
        ("fiscal_web:iss_regimes", []),
        ("fiscal_web:iss_regras_municipio", []),
    ],
)
def test_anonimo_e_redirecionado_ao_login_nas_telas_do_iss(client, nome_rota, argumentos):
    resposta = client.get(reverse(nome_rota, args=argumentos))

    assert resposta.status_code == 302
    assert "login" in resposta["Location"]


def test_menu_iss_aparece_a_quem_consulta_e_nao_ao_cliente(
    client, paralegal_a, usuario_cliente_a, empresa_a
):
    _logar(client, paralegal_a)
    html = client.get(reverse("tenancy:painel")).content.decode()
    assert "ISS municipal" in html
    assert reverse("fiscal_web:iss_apuracao") in html
    assert reverse("fiscal_web:iss_regimes") in html

    _logar(client, usuario_cliente_a)
    assert (
        reverse("fiscal_web:iss_apuracao")
        not in client.get(reverse("tenancy:painel")).content.decode()
    )


def test_home_do_fiscal_tem_atalho_para_a_apuracao_do_iss(client, empresa_a, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(reverse("module_home:home", args=["fiscal"]))

    atalhos = resposta.context["home"]["atalhos"]
    assert resposta.status_code == 200
    assert any(
        atalho["rotulo"] == "ISS do município (apuração)"
        and atalho["url"].startswith(reverse("fiscal_web:iss_apuracao"))
        for atalho in atalhos
    )


# ---------------------------------------------------------------------------
# Isolamento: outro escritório e outra empresa do mesmo escritório recebem 404
# ---------------------------------------------------------------------------


def test_outro_escritorio_recebe_404_e_nao_altera_as_aliquotas(
    client, cenario, empresa_a, gestor_b, escritorio_a
):
    alvo = AliquotaIssMunicipal.objects.get(escritorio=escritorio_a, subitem="17.01")
    regime = RegimeIssEmpresa.objects.get(empresa=empresa_a, exercicio=ANO)
    _logar(client, gestor_b)

    assert client.get(_url_editar_aliquota(alvo)).status_code == 404
    assert client.post(_url_editar_aliquota(alvo), _aliquota_valida()).status_code == 404
    assert client.get(_url_encerrar_aliquota(alvo)).status_code == 404
    assert client.post(_url_encerrar_aliquota(alvo), {"fim": "31/12/2026"}).status_code == 404
    assert client.get(_url_regimes(empresa_a)).status_code == 404
    assert client.get(_url_regime_editar(empresa_a, regime)).status_code == 404
    assert client.get(_url_apuracao(empresa_a)).status_code == 404

    alvo.refresh_from_db()
    assert alvo.fim_vigencia is None


def test_regime_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, cenario, empresa_a, empresa_a2, usuario_gestor_a
):
    """A empresa A2 é do mesmo escritório, mas o regime de A não se edita pelo caminho de A2."""
    regime = RegimeIssEmpresa.objects.get(empresa=empresa_a, exercicio=ANO)
    _logar(client, usuario_gestor_a)

    assert client.get(_url_regime_editar(empresa_a2, regime)).status_code == 404
    assert client.post(_url_regime_editar(empresa_a2, regime), _regime_valido()).status_code == 404
    regime.refresh_from_db()
    assert regime.regime == RegimeIss.ALIQUOTA


def test_empresa_de_outro_escritorio_no_caminho_de_cadastro_recebe_404(
    client, empresa_b, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    assert client.get(_url_regime_novo(empresa_b)).status_code == 404
    assert client.post(_url_regime_novo(empresa_b), _regime_valido()).status_code == 404
    assert not RegimeIssEmpresa.objects.filter(empresa=empresa_b).exists()


# ---------------------------------------------------------------------------
# Inventário DL-024: cada rota nova tem uma linha
# ---------------------------------------------------------------------------


def test_rotas_do_iss_estao_no_inventario_do_dl024():
    """Cada rota nova tem uma linha no inventário: a guarda de cobertura reprova rota sem
    classificação, e este teste nomeia a que faltar."""
    rotas = {
        "fiscal_web:iss_apuracao",
        "fiscal_web:iss_retido_sofrido",
        "fiscal_web:iss_outros_municipios",
        "fiscal_web:iss_aliquotas",
        "fiscal_web:iss_aliquota_nova",
        "fiscal_web:iss_aliquota_editar",
        "fiscal_web:iss_aliquota_encerrar",
        "fiscal_web:iss_regimes",
        "fiscal_web:iss_regime_novo",
        "fiscal_web:iss_regime_editar",
        "fiscal_web:iss_regras_municipio",
    }
    assert rotas <= set(NOMES_DE_TELA_FISCAL_FORA_DA_CONTABILIDADE)
