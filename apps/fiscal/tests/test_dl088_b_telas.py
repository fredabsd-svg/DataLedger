"""DL-088, frente B — telas da virada de 2027 no Simples e o portão de efetivação da NF-e.

- **Opção de regime de IBS/CBS por semestre (escopo 6):** consulta e registro na tela, insert-only —
  a segunda tentativa mostra a recusa nomeada do SERVIÇO, em linguagem de escritório; antes de
  gravar, a última etapa nomeia o alvo (direção de arte §2, arquétipo E). Permissão no servidor
  (`papel_pode_escriturar_fiscal` para registrar); a trilha vem do serviço.
- **IPI mantido (Zona Franca) (escopos 3 e 6):** cadastro corrigível com a fonte OBRIGATÓRIA; sem
  linha, a tela diz "não informado" (o produto não presume ZFM) e explica o efeito: produção
  própria em 2027 vai ao Anexo I; com IPI mantido, ao Anexo II.
- **Pré-DAS de 2027 na tela (escopo 6):** CBS e IBS por segmento, a primeira faixa do RBT12 quando
  for o caso e a opção do semestre que valeu; sem a opção, a recusa nomeada com o link para a tela
  dela.
- **RBT12 (pendência da frente A1):** "não apurável" passa a dizer o motivo CERTO quando o real é a
  primeira faixa (início de atividade), e não "há meses da janela sem confirmação".
- **Calendário da virada (escopo 5, PE-92):** prazos COM FONTE na tela do Simples, informativo.
- **Portão de efetivação de NF-e de 2027:** o botão "Efetivar" segue o REGIME, com o motivo real
  (três recusas nomeadas + regime único habilitado).
- **Permissão no servidor e isolamento entre escritórios.**

MUTAÇÃO (critério 9): inverter a checagem de permissão de uma tela nova derruba
`test_cliente_recebe_403_nas_telas_novas_e_nada_grava`; ignorar o regime no botão de efetivar
(remover a `empresa` do portão) derruba os três testes de recusa nomeada.

Dados 100% sintéticos. Os números de 2027 dos cenários de pré-DAS são os mesmos casos de referência
escritos à mão em `test_dl088_pre_das_2027.py` (serviço, Anexo III, RBT12 300.000, PA 10.000).
"""

import re
from datetime import date
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    EnquadramentoAtividade,
    IpiMantidoZfmEmpresa,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    OpcaoRegimeIbsCbsSimples,
    RegimeIbsCbsSimples,
    SituacaoIpiMantido,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.suporte_dl088 import confirmar_janela_de_2027_01, receber_pa_2027_01
from apps.fiscal.tests.test_dl074_suporte import fixar_hoje
from apps.fiscal.tests.test_dl075_suporte import atividade_padrao, cenario_simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_ALFANUMERICO, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
ANEXO_III = EnquadramentoAtividade.ANEXO_III


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    """Relógio de Brasília em 15/03/2028: os meses de 2027 dos cenários são confirmáveis, e o
    resultado não depende do dia da execução (AGENTS.md §7)."""
    fixar_hoje(monkeypatch, date(2028, 3, 15))


# ---------------------------------------------------------------------------
# Auxiliares: usuários, URLs, HTML e a checagem de referências de id
# ---------------------------------------------------------------------------


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio-fiscal-teste.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _url(nome, *args, **consulta):
    url = reverse(f"fiscal_web:{nome}", args=list(args))
    return url + ("?" + urlencode(consulta) if consulta else "")


def _html(resposta):
    return resposta.content.decode("utf-8")


def _texto(html):
    """Texto do HTML com as tags tiradas e o espaçamento normalizado — para asserções de prosa que o
    template quebra em várias linhas (a renderização não pode decidir o resultado do teste)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html))


def _ids_referenciados_existem(html):
    """Todo `aria-describedby` e todo `for` aponta para um `id` que existe na própria página."""
    existentes = set(re.findall(r'\bid="([^"]+)"', html))
    referencias = set()
    for bloco in re.findall(r'aria-describedby="([^"]+)"', html):
        referencias.update(bloco.split())
    referencias.update(re.findall(r'\bfor="([^"]+)"', html))
    return referencias - existentes


@pytest.fixture
def simples(empresa_a):
    """Empresa do Simples desde 2018: a opção do semestre e o IPI mantido são dados dela, e a
    opção de 2027 exige período do Simples no ano (`receita.registrar_opcao_regime_ibs_cbs`)."""
    return cenario_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


@pytest.fixture
def paralegal(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl088b")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-dl088b")


# ---------------------------------------------------------------------------
# 1. Opção de regime de IBS/CBS por semestre (escopo 6)
# ---------------------------------------------------------------------------


def test_tela_opcao_regime_ibs_cbs_e_acessivel(client, simples, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(_url("opcao_regime_ibs_cbs", empresa=simples.pk))
    assert resposta.status_code == 200
    assert "fiscal/opcao_regime_ibs_cbs.html" in [t.name for t in resposta.templates]
    html = _html(resposta)
    assert_moldura_acessivel(html)
    assert not _ids_referenciados_existem(html), _ids_referenciados_existem(html)
    # Os dois regimes, com a consequência dita em linguagem de escritório.
    assert "CBS e IBS ficam no DAS" in html
    assert "CBS e IBS são deduzidos do DAS, art. 22-A" in html
    # Sem opção registrada: estado vazio completo (direção de arte §8.4c), sem fingir registro.
    assert "Nenhuma opção de regime de IBS/CBS registrada." in html


def test_tela_opcao_regime_ibs_cbs_sem_empresa_pede_a_escolha(client, simples, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = _html(client.get(_url("opcao_regime_ibs_cbs")))
    assert "Escolha uma empresa para ver a opção de regime de IBS/CBS." in html


def test_registrar_opcao_pela_tela_confirma_nomeando_o_alvo_e_e_insert_only(
    client, simples, usuario_gestor_a
):
    """O registro tem a última etapa que nomeia o alvo antes de gravar (arquétipo E), e a trilha
    vem do SERVIÇO (`regime_ibs_cbs.opcao_registrada`) — a tela não grava nada por conta própria."""
    client.force_login(usuario_gestor_a)
    dados = {"ano": "2027", "semestre": "1", "regime": RegimeIbsCbsSimples.REGIME_UNICO}

    revisao = client.post(
        _url("opcao_regime_ibs_cbs_registrar", simples.pk), {**dados, "acao": "revisar"}
    )
    assert revisao.status_code == 200
    html = _html(revisao)
    # A confirmação nomeia o alvo (empresa, semestre) e a consequência, e diz que nada foi gravado.
    assert simples.razao_social in html
    assert "para o 1º semestre de 2027" in html
    assert "CBS e IBS ficam no DAS" in html
    assert "uma única vez" in html
    assert "Nada foi gravado ainda" in html
    assert OpcaoRegimeIbsCbsSimples.objects.filter(empresa=simples).count() == 0

    confirmacao = client.post(
        _url("opcao_regime_ibs_cbs_registrar", simples.pk), {**dados, "acao": "confirmar"}
    )
    assert confirmacao.status_code == 302
    opcao = OpcaoRegimeIbsCbsSimples.objects.get(empresa=simples)
    assert (opcao.ano, opcao.semestre, opcao.regime) == (2027, 1, RegimeIbsCbsSimples.REGIME_UNICO)
    assert opcao.registrada_por == usuario_gestor_a
    # Trilha do serviço, com o carimbo de quem registrou.
    registro = RegistroAuditoria.objects.get(acao="regime_ibs_cbs.opcao_registrada")
    assert registro.usuario == usuario_gestor_a
    assert registro.detalhes["regime"] == RegimeIbsCbsSimples.REGIME_UNICO
    # O que já está registrado aparece como registrado, com a consequência.
    html = _html(client.get(_url("opcao_regime_ibs_cbs", empresa=simples.pk)))
    assert "1º semestre" in html and "2027" in html
    assert "Regime único" in html
    assert "CBS e IBS ficam no DAS" in html


def test_opcao_ja_registrada_mostra_a_recusa_nomeada_do_servico(client, simples, usuario_gestor_a):
    """Insert-only: a segunda tentativa mostra a recusa nomeada do serviço, como ela é escrita
    ("... já foi registrada; a opção do semestre é registrada uma única vez."), e nada muda."""
    servico_receita.registrar_opcao_regime_ibs_cbs(
        simples, 2027, 1, RegimeIbsCbsSimples.REGIME_UNICO, usuario_gestor_a
    )
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url("opcao_regime_ibs_cbs_registrar", simples.pk),
        {
            "ano": "2027",
            "semestre": "1",
            "regime": RegimeIbsCbsSimples.REGIME_REGULAR,
            "acao": "confirmar",
        },
    )

    assert resposta.status_code == 409
    html = _html(resposta)
    assert "A opção de regime de IBS/CBS do 1º semestre de 2027 já foi registrada" in html
    assert "a opção do semestre é registrada uma única vez" in html
    assert OpcaoRegimeIbsCbsSimples.objects.filter(empresa=simples).count() == 1
    # A opção original não mudou: é registro uma única vez, não cadastro corrigível.
    assert (
        OpcaoRegimeIbsCbsSimples.objects.get(empresa=simples).regime
        == RegimeIbsCbsSimples.REGIME_UNICO
    )


def test_opcao_com_dados_de_formulario_invalidos_e_recusada_campo_a_campo(
    client, simples, usuario_gestor_a
):
    """Erros campo a campo, em linguagem de escritório, sem tocar no serviço (nada é gravado)."""
    client.force_login(usuario_gestor_a)
    casos = [
        (
            {"ano": "2026", "semestre": "1", "regime": RegimeIbsCbsSimples.REGIME_UNICO},
            "erro_ano",
            "a opção de regime de IBS/CBS só existe a partir de 2027",
        ),
        (
            {"ano": "2027", "semestre": "3", "regime": RegimeIbsCbsSimples.REGIME_UNICO},
            "erro_semestre",
            "escolha o 1º semestre (janeiro a junho) ou o 2º semestre",
        ),
        (
            {"ano": "2027", "semestre": "1", "regime": "regime_do_mes"},
            "erro_regime",
            "escolha regime único (CBS e IBS ficam no DAS) ou regime regular",
        ),
        (
            {"ano": "vinte", "semestre": "1", "regime": RegimeIbsCbsSimples.REGIME_UNICO},
            "erro_ano",
            "informe o ano com quatro dígitos",
        ),
    ]
    for dados, id_do_erro, trecho in casos:
        resposta = client.post(
            _url("opcao_regime_ibs_cbs_registrar", simples.pk), {**dados, "acao": "revisar"}
        )
        assert resposta.status_code == 400, dados
        html = _html(resposta)
        assert f'id="{id_do_erro}"' in html, dados
        assert trecho in html, dados
        assert not _ids_referenciados_existem(html), dados
    assert OpcaoRegimeIbsCbsSimples.objects.count() == 0


# ---------------------------------------------------------------------------
# 2. IPI mantido (Zona Franca) (escopos 3 e 6)
# ---------------------------------------------------------------------------


def test_ipi_mantido_nao_informado_aparece_como_nao_informado(client, simples, usuario_gestor_a):
    """Sem linha gravada, a tela diz "não informado" — o produto NÃO presume Zona Franca — e explica
    o efeito do dado (produção própria em 2027 vai ao Anexo I; com IPI mantido, ao Anexo II)."""
    client.force_login(usuario_gestor_a)
    html = _html(client.get(_url("ipi_mantido", empresa=simples.pk)))
    assert "Não informado (o produto não presume Zona Franca)" in html
    assert "produção própria vai ao Anexo I; com IPI mantido, vai ao Anexo II" in html
    # A fonte da regra, com a data da leitura (AGENTS.md §10).
    assert "Res. CGSN 190/2026, art. 25, § 1º, II" in html
    assert "09/10/2026" in html


def test_tela_ipi_mantido_e_acessivel(client, simples, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = _html(client.get(_url("ipi_mantido", empresa=simples.pk)))
    assert_moldura_acessivel(html)
    assert not _ids_referenciados_existem(html), _ids_referenciados_existem(html)


def test_tela_ipi_mantido_sem_empresa_pede_a_escolha(client, simples, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = _html(client.get(_url("ipi_mantido")))
    assert "Escolha uma empresa para ver o dado de IPI mantido." in html


def test_gravar_ipi_mantido_pela_tela_exige_a_fonte(client, simples, usuario_gestor_a):
    """A fonte é obrigatória: sem ela, a recusa cai no campo certo e nada é gravado."""
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("ipi_mantido_gravar", simples.pk),
        {"situacao": SituacaoIpiMantido.IPI_MANTIDO, "fonte": "   "},
    )
    assert resposta.status_code == 400
    html = _html(resposta)
    assert 'id="erro_fonte"' in html
    assert "A fonte do dado de IPI mantido é obrigatória" in html
    assert not _ids_referenciados_existem(html), _ids_referenciados_existem(html)
    assert IpiMantidoZfmEmpresa.objects.count() == 0


def test_gravar_ipi_mantido_pela_tela_grava_corrige_e_trilha(client, simples, usuario_gestor_a):
    """Cadastro CORRIGÍVEL: registrar de novo com outro valor atualiza a linha, e a trilha do
    serviço guarda antes e depois (`ipi_mantido.definido`)."""
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("ipi_mantido_gravar", simples.pk),
        {
            "situacao": SituacaoIpiMantido.IPI_MANTIDO,
            "fonte": "Declaração do cliente de 05/10/2026.",
        },
    )
    assert resposta.status_code == 302
    linha = IpiMantidoZfmEmpresa.objects.get(empresa=simples)
    assert linha.situacao == SituacaoIpiMantido.IPI_MANTIDO
    assert linha.fonte == "Declaração do cliente de 05/10/2026."

    # Correção para o outro valor: a MESMA linha é atualizada (não há segunda linha).
    client.post(
        _url("ipi_mantido_gravar", simples.pk),
        {"situacao": SituacaoIpiMantido.SEM_IPI_MANTIDO, "fonte": "Sem ato de incentivo."},
    )
    assert IpiMantidoZfmEmpresa.objects.filter(empresa=simples).count() == 1
    linha.refresh_from_db()
    assert linha.situacao == SituacaoIpiMantido.SEM_IPI_MANTIDO
    registro = RegistroAuditoria.objects.filter(acao="ipi_mantido.definido").order_by("pk").last()
    assert registro.detalhes["antes"] == {
        "situacao": SituacaoIpiMantido.IPI_MANTIDO,
        "fonte": "Declaração do cliente de 05/10/2026.",
    }
    assert registro.detalhes["depois"]["situacao"] == SituacaoIpiMantido.SEM_IPI_MANTIDO
    # A tela mostra o dado registrado, com a fonte.
    html = _html(client.get(_url("ipi_mantido", empresa=simples.pk)))
    assert "Sem IPI mantido" in html
    assert "Sem ato de incentivo." in html


# ---------------------------------------------------------------------------
# 3. Pré-DAS de 2027 na tela (escopo 6) e a primeira faixa do RBT12
# ---------------------------------------------------------------------------


def _cenario_de_2027(empresa, usuario, *, valor_mensal=25000, valor_mes_anterior=900000, pa=10000):
    """Serviço, Anexo III, Simples desde 2018, PA 01/2027 com `pa` de receita interna.

    A janela defasada de 01/2027 (12/2025 a 11/2026) é confirmada com `valor_mensal` cada — RBT12
    300.000 com 25.000 — e 12/2026 recebe `valor_mes_anterior` FORA da janela: se o cálculo usasse a
    janela antiga, o resultado mudaria (é o que os testes da frente A1 guardam).
    """
    empresa = cenario_simples(empresa)
    atividade_padrao(empresa, usuario, ANEXO_III)
    confirmar_janela_de_2027_01(
        empresa, usuario, valor_mensal, valor_mes_anterior=valor_mes_anterior
    )
    receber_pa_2027_01(empresa, usuario, pa)
    return empresa


def _opcao(empresa, usuario, regime, semestre=1):
    return servico_receita.registrar_opcao_regime_ibs_cbs(empresa, 2027, semestre, regime, usuario)


def test_pre_das_2027_na_tela_mostra_cbs_ibs_e_a_opcao_do_semestre(
    client, empresa_a, usuario_gestor_a
):
    """Regime único: CBS e IBS aparecem por segmento (serviço, Anexo III, PA 10.000, efetiva 8,08%:
    CBS 136,63 · IBS 1,54) e a tela diz a opção do semestre que valeu, com a consequência."""
    empresa = _cenario_de_2027(empresa_a, usuario_gestor_a)
    _opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_UNICO)
    client.force_login(usuario_gestor_a)

    resposta = client.get(_url("pre_das", empresa=empresa.pk, ano=2027, mes=1))

    assert resposta.status_code == 200
    html = _html(resposta)
    assert "CBS" in html and "IBS" in html
    assert "136,63" in html and "1,54" in html
    assert "Opção de regime de IBS/CBS do 1º semestre de 2027" in html
    assert "Regime único" in html
    assert "CBS e IBS ficam no DAS" in html
    # Sem estado de primeira faixa neste cenário (abertura de 2015).
    assert "Primeira faixa (início de atividade)" not in html


def test_pre_das_2027_com_regime_regular_mostra_a_deducao_do_art_22a(
    client, empresa_a, usuario_gestor_a
):
    """Regime regular: as parcelas de CBS e IBS saem do DAS (art. 22-A) e a tela mostra a dedução,
    nunca um zero digitado. Total 808,00 − 138,17 = 669,83 (contas em test_dl088_pre_das_2027)."""
    empresa = _cenario_de_2027(empresa_a, usuario_gestor_a)
    _opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_REGULAR)
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("pre_das", empresa=empresa.pk, ano=2027, mes=1)))

    assert "Regime regular" in html
    assert "CBS e IBS são deduzidos do DAS, art. 22-A" in html
    assert "Deduzido do DAS, art. 22-A" in html
    assert "deduzido (136,63)" in html
    assert "deduzido (1,54)" in html
    assert "669,83" in html


def test_pre_das_2027_primeira_faixa_aparece_como_primeira_faixa(
    client, empresa_a, usuario_gestor_a
):
    """Abertura em 15/01/2027 (mês 1 de atividade): o RBT12 está no estado "1ª faixa", e a tela do
    pré-DAS diz isso — com o dispositivo — em vez de qualquer motivo de mês pendente."""
    empresa = cenario_simples(
        empresa_a, abertura=date(2027, 1, 15), inicio_simples=date(2027, 1, 15)
    )
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III, inicio=date(2027, 1, 1))
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000)
    _opcao(empresa, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_UNICO)
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("pre_das", empresa=empresa.pk, ano=2027, mes=1)))

    assert "Primeira faixa (início de atividade)" in html
    assert "não há RBT12 numérico" in html
    assert "Res. CGSN 190/2026, art. 22, § 2º, I" in html
    assert "Faltam meses confirmados" not in html
    # O cálculo da 1ª faixa sai mesmo assim: nominal 6% sobre 10.000 = 600,00.
    assert "600,00" in html


def test_pre_das_2027_sem_a_opcao_mostra_a_recusa_nomeada_e_o_link(
    client, empresa_a, usuario_gestor_a
):
    """Sem a opção do semestre informada, o pré-DAS de 2027 não é calculado: a tela mostra a recusa
    nomeada do serviço e o link para a tela da opção (o dado que falta se registra ali)."""
    empresa = _cenario_de_2027(empresa_a, usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("pre_das", empresa=empresa.pk, ano=2027, mes=1)))

    assert "falta a opção pelo regime regular de IBS/CBS" in html
    assert "Registrar a opção de regime de IBS/CBS" in html
    assert _url("opcao_regime_ibs_cbs", empresa=empresa.pk) in html, (
        "o link da recusa leva à tela da opção"
    )


def test_receita_do_mes_primeira_faixa_mostra_o_motivo_certo(client, empresa_a, usuario_gestor_a):
    """Pendência da frente A1: a tela do RBT12 dizia "há meses da janela sem confirmação" quando o
    motivo real era a primeira faixa (início de atividade). Agora o motivo certo aparece, na
    célula e no aviso — e o motivo antigo não aparece junto."""
    empresa = cenario_simples(
        empresa_a, abertura=date(2027, 1, 15), inicio_simples=date(2027, 1, 15)
    )
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III, inicio=date(2027, 1, 1))
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000)
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("receita_do_mes", empresa=empresa.pk, ano=2027, mes=1)))

    assert "Primeira faixa (início de atividade)" in html
    assert "Não apurado: 1ª faixa (1º e 2º mês de atividade), sem RBT12 numérico" in html
    assert "há meses da janela sem confirmação" not in html
    assert "Faltam meses confirmados" not in html


def test_receita_do_mes_com_mes_pendente_continua_dizendo_o_motivo_de_sempre(
    client, empresa_a, usuario_gestor_a
):
    """Regressão do caso vizinho: mês da janela SEM confirmação continua dizendo "há meses da janela
    sem confirmação" — a correção mudou o motivo da primeira faixa, não o do mês pendente."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000)
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("receita_do_mes", empresa=empresa.pk, ano=2027, mes=1)))

    assert "há meses da janela sem confirmação" in html
    assert "Primeira faixa (início de atividade)" not in html


# ---------------------------------------------------------------------------
# 4. Calendário de prazos da virada (escopo 5, PE-92)
# ---------------------------------------------------------------------------


_PRAZOS_DA_VIRADA = (
    "15/10/2026",
    "30/10/2026",
    "20/12/2026",
    "20/01/2027",
    "janeiro a março",
)


def test_calendario_da_virada_cita_as_fontes_na_receita_do_mes(client, simples, usuario_gestor_a):
    """O bloco do calendário traz os quatro prazos do escopo, cada um com o dispositivo, e a fonte
    com a DATA DA LEITURA. Nada além do que a fonte diz (AGENTS.md §10)."""
    client.force_login(usuario_gestor_a)
    texto = _texto(_html(client.get(_url("receita_do_mes", empresa=simples.pk, ano=2027, mes=1))))
    for prazo in _PRAZOS_DA_VIRADA:
        assert prazo in texto, prazo
    assert "Res. CGSN 194/2026" in texto
    assert "Res. CGSN 190/2026, arts. 144-D e 144-E" in texto
    assert "Res. CGSN 190/2026, art. 38-B" in texto
    assert "leitura de 09/10/2026" in texto
    assert "2026-10-09-contador-senior-virada-2027-simples.md" in texto
    # Só informativo: a tela não registra nem transmite nada das obrigações.
    assert "não registra nem transmite nada" in texto


def test_calendario_da_virada_tambem_no_pre_das(client, simples, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    texto = _texto(_html(client.get(_url("pre_das", empresa=simples.pk, ano=2027, mes=1))))
    for prazo in _PRAZOS_DA_VIRADA:
        assert prazo in texto, prazo
    assert "leitura de 09/10/2026" in texto


# ---------------------------------------------------------------------------
# 5. Portão de efetivação de NF-e de 2027: o botão segue o REGIME
# ---------------------------------------------------------------------------


def _nota_de_2027(numero=1, emitente_cnpj=CNPJ_EMITENTE_A) -> bytes:
    """NF-e de saída emitida em 10/02/2027, UM item: vProd 100,00 e frete 10,00 (caso da frente A2:
    pela regra de 2027 a receita é o `vProd`, 100,00)."""
    return xml.nfe(
        dets=[xml.det(1, vprod="100.00", vfrete="10.00", icms_xml=xml.icms(csosn="102"))],
        vnf="110.00",
        totais={"vProd": "100.00"},
        numero=str(numero),
        dh_emi="2027-02-10T10:00:00-03:00",
        emitente=("CNPJ", emitente_cnpj),
    )


@pytest.fixture
def empresa_nfe_simples(escritorio_a):
    """Empresa do Simples desde 2018, com o CNPJ do emitente da nota sintética."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Simples 2027 DL088B Ltda", cnpj=CNPJ_EMITENTE_A
    )
    return cenario_simples(empresa, abertura=date(2015, 1, 1), inicio_simples=date(2018, 1, 1))


@pytest.fixture
def empresa_nfe_presumida(escritorio_a):
    """Empresa do Lucro Presumido em 2027: a receita de NF-e de 2027 continua bloqueada (HI-149)."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Presumida 2027 DL088B Ltda", cnpj=CNPJ_ALFANUMERICO
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    return empresa


def _rascunho_com_naturezas(escritorio, usuario, empresa, *, emitente_cnpj, numero):
    """Recebe a nota, cria o rascunho e confirma a natureza de todos os itens: o ÚNICO bloqueio que
    sobra para a efetivação é o portão de 2027 (o de data e de regime)."""
    documento = receber(escritorio, usuario, _nota_de_2027(numero, emitente_cnpj))
    vinculo_nfe = vinculo(documento, empresa)
    escrituracao = servico_nfe.criar_rascunho(vinculo_nfe, usuario=usuario)
    ids = list(
        NaturezaItemNFe.objects.filter(escrituracao=escrituracao).values_list("item_id", flat=True)
    )
    servico_nfe.definir_natureza(escrituracao, NaturezaOperacaoNFe.REVENDA, ids, usuario=usuario)
    return vinculo_nfe


_BOTAO_HABILITADO = (
    '<button type="submit" class="botao botao--primario">Efetivar escrituração</button>'
)
_BOTAO_DESABILITADO = (
    '<button type="submit" class="botao botao--primario" disabled '
    'aria-describedby="id_motivo_efetivar">Efetivar escrituração</button>'
)


def test_efetivar_de_2027_sem_a_opcao_fica_desabilitado_com_o_motivo_nomeado(
    client, escritorio_a, usuario_gestor_a, empresa_nfe_simples
):
    """Simples SEM a opção do semestre: o botão fica desabilitado com o motivo nomeado da opção —
    não com o motivo genérico da data. MUTANTE que este teste derruba: ignorar o regime (deixar de
    passar a empresa ao portão), que mostraria a mensagem genérica."""
    vinculo_nfe = _rascunho_com_naturezas(
        escritorio_a, usuario_gestor_a, empresa_nfe_simples, emitente_cnpj=CNPJ_EMITENTE_A, numero=1
    )
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("nfe_escriturar", empresa_nfe_simples.pk, vinculo_nfe.pk)))

    assert _BOTAO_DESABILITADO in html
    assert servico_nfe.MENSAGEM_RECEITA_2027_SEM_OPCAO in html
    assert servico_nfe.MENSAGEM_RECEITA_2027_PENDENTE not in html


def test_efetivar_de_2027_no_regime_regular_fica_desabilitado_com_o_motivo_nomeado(
    client, escritorio_a, usuario_gestor_a, empresa_nfe_simples
):
    """Quem optou pelo regime REGULAR (art. 22-A): recusa nomeada do regime regular, não a
    genérica."""
    _opcao(empresa_nfe_simples, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_REGULAR)
    vinculo_nfe = _rascunho_com_naturezas(
        escritorio_a, usuario_gestor_a, empresa_nfe_simples, emitente_cnpj=CNPJ_EMITENTE_A, numero=1
    )
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("nfe_escriturar", empresa_nfe_simples.pk, vinculo_nfe.pk)))

    assert _BOTAO_DESABILITADO in html
    assert servico_nfe.MENSAGEM_RECEITA_2027_REGIME_REGULAR in html
    assert servico_nfe.MENSAGEM_RECEITA_2027_PENDENTE not in html


def test_efetivar_de_2027_no_presumido_fica_desabilitado_com_o_motivo_nomeado(
    client, escritorio_a, usuario_gestor_a, empresa_nfe_presumida
):
    """Lucro Presumido: a recusa de 2027 continua, com o motivo nomeado do Presumido."""
    vinculo_nfe = _rascunho_com_naturezas(
        escritorio_a,
        usuario_gestor_a,
        empresa_nfe_presumida,
        emitente_cnpj=CNPJ_ALFANUMERICO,
        numero=2,
    )
    client.force_login(usuario_gestor_a)

    html = _html(client.get(_url("nfe_escriturar", empresa_nfe_presumida.pk, vinculo_nfe.pk)))

    assert _BOTAO_DESABILITADO in html
    assert servico_nfe.MENSAGEM_RECEITA_2027_PRESUMIDO in html
    assert servico_nfe.MENSAGEM_RECEITA_2027_PENDENTE not in html


def test_efetivar_de_2027_no_regime_unico_fica_habilitado(
    client, escritorio_a, usuario_gestor_a, empresa_nfe_simples
):
    """Regime ÚNICO do semestre: o portão libera — botão habilitado, e a efetivação acontece."""
    _opcao(empresa_nfe_simples, usuario_gestor_a, RegimeIbsCbsSimples.REGIME_UNICO)
    vinculo_nfe = _rascunho_com_naturezas(
        escritorio_a, usuario_gestor_a, empresa_nfe_simples, emitente_cnpj=CNPJ_EMITENTE_A, numero=1
    )
    client.force_login(usuario_gestor_a)

    resposta = client.get(_url("nfe_escriturar", empresa_nfe_simples.pk, vinculo_nfe.pk))

    html = _html(resposta)
    assert _BOTAO_HABILITADO in html
    assert _BOTAO_DESABILITADO not in html
    assert "Confere: a receita dos itens bate com o valor da nota" in html

    efetivacao = client.post(
        _url("nfe_escriturar", empresa_nfe_simples.pk, vinculo_nfe.pk), {"acao": "efetivar"}
    )
    assert efetivacao.status_code == 302


# ---------------------------------------------------------------------------
# 6. Permissão no servidor e isolamento entre escritórios
# ---------------------------------------------------------------------------


def _contagens_de_dado():
    return (
        OpcaoRegimeIbsCbsSimples.objects.count(),
        IpiMantidoZfmEmpresa.objects.count(),
    )


def _post_confirmar_opcao():
    return {
        "ano": "2027",
        "semestre": "1",
        "regime": RegimeIbsCbsSimples.REGIME_UNICO,
        "acao": "confirmar",
    }


def _post_ipi_mantido():
    return {"situacao": SituacaoIpiMantido.IPI_MANTIDO, "fonte": "Declaração do cliente."}


def test_cliente_recebe_403_nas_telas_novas_e_nada_grava(client, simples, usuario_cliente_a):
    """MUTANTE (critério 9): inverter a checagem de permissão de qualquer tela nova derruba este
    teste — o CLIENTE não consulta nem escreve, e nada é gravado."""
    client.force_login(usuario_cliente_a)
    antes = _contagens_de_dado()
    for nome in ("opcao_regime_ibs_cbs", "ipi_mantido"):
        assert client.get(_url(nome, empresa=simples.pk)).status_code == 403, nome
    for nome, args, corpo in (
        ("opcao_regime_ibs_cbs_registrar", [simples.pk], _post_confirmar_opcao()),
        ("ipi_mantido_gravar", [simples.pk], _post_ipi_mantido()),
    ):
        # Rotas só de POST: o GET é 405 para todo mundo, e o POST do CLIENTE é 403 no servidor.
        assert client.get(_url(nome, *args)).status_code == 405, nome
        assert client.post(_url(nome, *args), corpo).status_code == 403, nome
    assert _contagens_de_dado() == antes


def test_paralegal_le_e_nao_escreve_nas_telas_novas(client, simples, paralegal):
    client.force_login(paralegal)
    antes = _contagens_de_dado()
    for nome in ("opcao_regime_ibs_cbs", "ipi_mantido"):
        assert client.get(_url(nome, empresa=simples.pk)).status_code == 200, nome
    assert (
        client.post(
            _url("opcao_regime_ibs_cbs_registrar", simples.pk), _post_confirmar_opcao()
        ).status_code
        == 403
    )
    assert (
        client.post(_url("ipi_mantido_gravar", simples.pk), _post_ipi_mantido()).status_code == 403
    )
    assert _contagens_de_dado() == antes
    # Quem só consulta vê a ação desabilitada com o motivo, nunca sumindo (§2B).
    html = _html(client.get(_url("opcao_regime_ibs_cbs", empresa=simples.pk)))
    assert "Seu papel consulta a opção de regime de IBS/CBS, mas não a registra" in html
    assert 'class="botao botao--primario" disabled aria-describedby="ajuda_sem_permissao"' in html


def test_outro_escritorio_recebe_404_nas_telas_novas(client, simples, gestor_b):
    """Isolamento entre escritórios: a empresa do escritório A é 404 para o gestor do escritório B,
    nas consultas e nos atos — e nada é gravado."""
    client.force_login(gestor_b)
    antes = _contagens_de_dado()
    for nome in ("opcao_regime_ibs_cbs", "ipi_mantido"):
        assert client.get(_url(nome, empresa=simples.pk)).status_code == 404, nome
    assert (
        client.post(
            _url("opcao_regime_ibs_cbs_registrar", simples.pk), _post_confirmar_opcao()
        ).status_code
        == 404
    )
    assert (
        client.post(_url("ipi_mantido_gravar", simples.pk), _post_ipi_mantido()).status_code == 404
    )
    assert _contagens_de_dado() == antes
