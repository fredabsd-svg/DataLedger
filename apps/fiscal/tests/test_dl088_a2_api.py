"""DL-088, frente A2: a API da opção de regime de IBS/CBS e do IPI mantido, e o pré-DAS liberado.
Aqui também o CANCELAMENTO da opção do semestre (correção do achado A1 da auditoria da DL-088,
Res. CGSN 194/2026 e arts. 40-C/40-D): serviço com a janela legal citada, trilha com o motivo,
re-registro liberado depois do cancelamento, e a API do ato com permissão e isolamento.

Critério 5 da DL-088: isolamento e permissão no servidor nos caminhos novos de escrita. O molde é
`test_dl084_parametros.py` (parâmetros do presumido): GET consulta, POST escritura, papel checado
no servidor, empresa de outro escritório responde 404 e campo fora do contrato responde 400. A
regra fica no serviço (`apps.fiscal.receita`), com trilha; aqui se testa o caminho completo.
"""

import json
from datetime import date

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    EnquadramentoAtividade,
    OpcaoRegimeIbsCbsSimples,
    RegimeIbsCbsSimples,
    SituacaoIpiMantido,
)
from apps.fiscal.tests.suporte_dl088 import (
    confirmar_janela_de_2027_01,
    receber_pa_2027_01,
)
from apps.fiscal.tests.test_dl074_suporte import fixar_hoje
from apps.fiscal.tests.test_dl075_suporte import atividade_padrao, cenario_simples
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    """Relógio de Brasília em 15/03/2028 (só se confirma mês completo), como na A1/A2."""
    fixar_hoje(monkeypatch, date(2028, 3, 15))


@pytest.fixture
def empresa(empresa_a):
    """Empresa do Simples: a opção de regime de IBS/CBS só se registra para quem é do Simples
    (mesma regra da opção pelo regime de caixa)."""
    return cenario_simples(empresa_a)


def _usuario(escritorio, papel, username):
    from django.contrib.auth import get_user_model

    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _url_opcao(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}/opcao-regime-ibs-cbs/"


def _url_ipi(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}/ipi-mantido/"


FONTE = "Declaração do cliente sobre a Zona Franca de Manaus (10/2026)"


# ---------------------------------------------------------------------------
# Serviço: o contrato da opção, a trilha e o isolamento por empresa
# ---------------------------------------------------------------------------


def test_sem_linha_a_opcao_nao_esta_informada_e_o_dado_de_ipi_tambem_nao(empresa):
    """Sem linha, `None` nos dois: a opção não informada mantém o pré-DAS de 2027 recusando, e o
    IPI mantido não informado não presume ZFM."""
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is None
    assert servico_receita.ipi_mantido_da_empresa(empresa) is None


def test_a_opcao_registrada_alimenta_o_motor_e_fica_na_trilha(empresa, usuario_gestor_a):
    """`regime_unico` vira `False` e `regime_regular` vira `True` no vocabulário do motor
    (`regime_regular_ibs_cbs` de `pre_das._calcular_pre_das`), e o ato fica registrado."""
    servico_receita.registrar_opcao_regime_ibs_cbs(
        empresa, 2027, 1, RegimeIbsCbsSimples.REGIME_UNICO, usuario_gestor_a
    )
    servico_receita.registrar_opcao_regime_ibs_cbs(
        empresa, 2027, 2, RegimeIbsCbsSimples.REGIME_REGULAR, usuario_gestor_a
    )

    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 2) is True
    registros = RegistroAuditoria.objects.filter(acao="regime_ibs_cbs.opcao_registrada")
    assert registros.count() == 2
    assert {r.detalhes["regime"] for r in registros} == {
        RegimeIbsCbsSimples.REGIME_UNICO,
        RegimeIbsCbsSimples.REGIME_REGULAR,
    }


def test_a_opcao_do_semestre_nao_se_altera_depois_de_registrada(empresa, usuario_gestor_a):
    """A escolha do semestre é do regime fiscal: registrada uma vez, a segunda tentativa é recusada
    pela restrição única, com mensagem de negócio (409 na API)."""
    servico_receita.registrar_opcao_regime_ibs_cbs(
        empresa, 2027, 1, RegimeIbsCbsSimples.REGIME_UNICO, usuario_gestor_a
    )
    with pytest.raises(servico_receita.ReceitaErro, match="já foi registrada"):
        servico_receita.registrar_opcao_regime_ibs_cbs(
            empresa, 2027, 1, RegimeIbsCbsSimples.REGIME_REGULAR, usuario_gestor_a
        )
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False


def test_a_opcao_exige_empresa_do_simples(empresa_a, usuario_gestor_a):
    """Como a opção pelo regime de caixa: empresa sem período do Simples no ano é recusada antes
    de gravar."""
    with pytest.raises(servico_receita.ReceitaErro, match="Simples Nacional"):
        servico_receita.registrar_opcao_regime_ibs_cbs(
            empresa_a, 2027, 1, RegimeIbsCbsSimples.REGIME_UNICO, usuario_gestor_a
        )
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa_a, 2027, 1) is None


def test_o_ipi_mantido_e_cadastro_corrigivel_com_trilha_de_antes_e_depois(
    empresa, usuario_gestor_a
):
    """Diferente da opção do semestre, o dado de IPI mantido se corrige: a trilha guarda as duas
    situações e a fonte."""
    servico_receita.definir_ipi_mantido(
        empresa, SituacaoIpiMantido.SEM_IPI_MANTIDO, FONTE, usuario_gestor_a
    )
    servico_receita.definir_ipi_mantido(
        empresa,
        SituacaoIpiMantido.IPI_MANTIDO,
        "Ato de incentivo à ZFM (correção, 11/2026)",
        usuario_gestor_a,
    )

    assert servico_receita.ipi_mantido_da_empresa(empresa) is True
    registro = RegistroAuditoria.objects.filter(acao="ipi_mantido.definido").order_by("pk").last()
    assert registro.detalhes["antes"]["situacao"] == SituacaoIpiMantido.SEM_IPI_MANTIDO
    assert registro.detalhes["depois"]["situacao"] == SituacaoIpiMantido.IPI_MANTIDO


def test_a_fonte_do_ipi_mantido_e_obrigatoria(empresa, usuario_gestor_a):
    """O dado é do escritório e precisa dizer de onde veio (o Fred confirma quais clientes)."""
    with pytest.raises(servico_receita.EntradaInvalidaReceita, match="fonte"):
        servico_receita.definir_ipi_mantido(
            empresa, SituacaoIpiMantido.IPI_MANTIDO, "   ", usuario_gestor_a
        )
    assert servico_receita.ipi_mantido_da_empresa(empresa) is None


def test_dados_de_uma_empresa_nao_aparecem_em_outra_do_mesmo_escritorio(
    empresa, empresa_a2, usuario_gestor_a
):
    """Isolamento por empresa nos caminhos novos de leitura (AGENTS.md §11)."""
    servico_receita.registrar_opcao_regime_ibs_cbs(
        empresa, 2027, 1, RegimeIbsCbsSimples.REGIME_UNICO, usuario_gestor_a
    )
    servico_receita.definir_ipi_mantido(
        empresa, SituacaoIpiMantido.IPI_MANTIDO, FONTE, usuario_gestor_a
    )

    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa_a2, 2027, 1) is None
    assert servico_receita.ipi_mantido_da_empresa(empresa_a2) is None


# ---------------------------------------------------------------------------
# API: permissão no servidor, isolamento de escritório e entrada
# ---------------------------------------------------------------------------


def test_gestor_registra_e_le_a_opcao_pela_api(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    gravou = client.post(
        _url_opcao(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "regime": "regime_unico"}),
        content_type="application/json",
    )
    assert gravou.status_code == 201
    corpo = gravou.json()
    assert corpo["regime"] == "regime_unico"
    assert corpo["informada"] is True
    assert corpo["registrada_em"] is not None

    lido = client.get(f"{_url_opcao(empresa)}?ano=2027&semestre=1").json()
    assert lido == corpo


def test_api_de_opcao_nao_informada_devolve_regime_nulo(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    lido = client.get(f"{_url_opcao(empresa)}?ano=2027&semestre=1").json()
    assert lido == {
        "ano": 2027,
        "semestre": 1,
        "regime": None,
        "informada": False,
        "registrada_em": None,
    }


def test_gestor_define_e_le_o_ipi_mantido_pela_api(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    gravou = client.post(
        _url_ipi(empresa),
        data=json.dumps({"situacao": "ipi_mantido", "fonte": FONTE}),
        content_type="application/json",
    )
    assert gravou.status_code == 200
    assert gravou.json()["situacao"] == "ipi_mantido"
    assert gravou.json()["fonte"] == FONTE

    lido = client.get(_url_ipi(empresa)).json()
    assert lido["informado"] is True
    assert lido["fonte"] == FONTE


def test_api_do_ipi_mantido_sem_fonte_e_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url_ipi(empresa),
        data=json.dumps({"situacao": "ipi_mantido", "fonte": ""}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert servico_receita.ipi_mantido_da_empresa(empresa) is None


def test_segunda_opcao_do_mesmo_semestre_responde_409(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    primeiro = client.post(
        _url_opcao(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "regime": "regime_unico"}),
        content_type="application/json",
    )
    assert primeiro.status_code == 201
    segundo = client.post(
        _url_opcao(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "regime": "regime_regular"}),
        content_type="application/json",
    )
    assert segundo.status_code == 409
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False


def test_opcao_antes_de_2027_e_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url_opcao(empresa),
        data=json.dumps({"ano": 2026, "semestre": 1, "regime": "regime_unico"}),
        content_type="application/json",
    )
    assert resposta.status_code == 400


def test_paralegal_le_mas_nao_grava(client, empresa, escritorio_a):
    paralegal = _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-opcao-dl088")
    client.force_login(paralegal)
    assert client.get(f"{_url_opcao(empresa)}?ano=2027&semestre=1").status_code == 200
    assert client.get(_url_ipi(empresa)).status_code == 200
    negado_opcao = client.post(
        _url_opcao(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "regime": "regime_unico"}),
        content_type="application/json",
    )
    negado_ipi = client.post(
        _url_ipi(empresa),
        data=json.dumps({"situacao": "ipi_mantido", "fonte": FONTE}),
        content_type="application/json",
    )
    assert negado_opcao.status_code == 403
    assert negado_ipi.status_code == 403
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is None
    assert servico_receita.ipi_mantido_da_empresa(empresa) is None


def test_cliente_nem_le_os_dados_da_virada(client, empresa, escritorio_a):
    cliente = _usuario(escritorio_a, Papel.CLIENTE, "cliente-opcao-dl088")
    client.force_login(cliente)
    assert client.get(f"{_url_opcao(empresa)}?ano=2027&semestre=1").status_code == 403
    assert client.get(_url_ipi(empresa)).status_code == 403


def test_empresa_de_outro_escritorio_responde_404(client, escritorio_b, empresa):
    intruso = _usuario(escritorio_b, Papel.GESTOR, "gestor-intruso-dl088")
    client.force_login(intruso)
    assert client.get(f"{_url_opcao(empresa)}?ano=2027&semestre=1").status_code == 404
    assert client.get(_url_ipi(empresa)).status_code == 404
    negado = client.post(
        _url_opcao(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "regime": "regime_unico"}),
        content_type="application/json",
    )
    assert negado.status_code == 404


def test_campo_fora_do_contrato_e_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url_opcao(empresa),
        data=json.dumps({"campo_inventado": "x"}),
        content_type="application/json",
    )
    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# O pré-DAS da API deixa de recusar 2027 nas mesmas condições do serviço
# ---------------------------------------------------------------------------


def test_pre_das_da_api_de_2027_sai_com_a_opcao_informada(client, empresa, usuario_gestor_a):
    """Serviço, Anexo III, RBT12 300.000, PA 01/2027 de 10.000, regime ÚNICO: a API devolve 200
    com os 808,00 ao centavo. Sem a opção, a mesma chamada devolve 409 com o bloqueio nomeado.
    """
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    confirmar_janela_de_2027_01(empresa, usuario_gestor_a, 25000, valor_mes_anterior=900000)
    receber_pa_2027_01(empresa, usuario_gestor_a, 10000)
    client.force_login(usuario_gestor_a)

    sem_opcao = client.get(f"/fiscal/api/empresas/{empresa.pk}/pre-das/?ano=2027&mes=1")
    assert sem_opcao.status_code == 409
    bloqueios = sem_opcao.json()["bloqueios"]
    assert [b["codigo"] for b in bloqueios] == ["opcao_regime_regular_nao_informada"]

    client.post(
        _url_opcao(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "regime": "regime_unico"}),
        content_type="application/json",
    )
    calculado = client.get(f"/fiscal/api/empresas/{empresa.pk}/pre-das/?ano=2027&mes=1")
    assert calculado.status_code == 200
    corpo = calculado.json()
    assert corpo["total"] == "808.00"
    assert corpo["total_por_tributo"] == {
        "IRPJ": "32.32",
        "CSLL": "28.28",
        "CBS": "136.63",
        "CPP": "350.67",
        "ISS": "258.56",
        "IBS": "1.54",
    }


# ---------------------------------------------------------------------------
# Cancelamento da opção do semestre (DL-088, correção do achado A1 — Res. CGSN 194/2026)
# ---------------------------------------------------------------------------

MOTIVO = "Cliente cancelou a opção no Portal em 30/11/2026 (Res. CGSN 194/2026)."


def _url_cancelar(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}/opcao-regime-ibs-cbs/cancelar/"


def _cancelar(empresa, usuario, *, ano=2027, semestre=1, motivo=MOTIVO):
    return servico_receita.cancelar_opcao_regime_ibs_cbs(empresa, ano, semestre, motivo, usuario)


def _registrar(empresa, usuario, *, ano=2027, semestre=1, regime=RegimeIbsCbsSimples.REGIME_UNICO):
    return servico_receita.registrar_opcao_regime_ibs_cbs(empresa, ano, semestre, regime, usuario)


def test_cancelamento_na_janela_e_feliz_com_trilha(empresa, usuario_gestor_a, monkeypatch):
    """Cancelamento dentro da janela da Res. CGSN 194/2026 (03/11 a 20/12/2026 para o 1º semestre
    de 2027): a linha NÃO é apagada — ganha `cancelada_em`/`cancelada_por`/`motivo_cancelamento` —
    a opção volta a estar NÃO informada para o motor, e a trilha guarda antes, depois e o motivo.
    """
    _registrar(empresa, usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))

    linha = _cancelar(empresa, usuario_gestor_a)

    assert linha.cancelada_em is not None
    assert linha.cancelada_por == usuario_gestor_a
    assert linha.motivo_cancelamento == MOTIVO
    assert OpcaoRegimeIbsCbsSimples.objects.count() == 1
    assert servico_receita.opcao_regime_ibs_cbs_registrada(empresa, 2027, 1) is None
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is None
    registro = RegistroAuditoria.objects.get(acao="regime_ibs_cbs.opcao_cancelada")
    assert registro.usuario == usuario_gestor_a
    assert registro.detalhes["motivo_cancelamento"] == MOTIVO
    assert registro.detalhes["antes"] == {
        "ativa": True,
        "regime": RegimeIbsCbsSimples.REGIME_UNICO,
        "cancelada_em": None,
        "cancelada_por": None,
        "motivo_cancelamento": None,
    }
    assert registro.detalhes["depois"]["ativa"] is False
    assert registro.detalhes["depois"]["motivo_cancelamento"] == MOTIVO


def test_cancelamento_fora_da_janela_e_recusado_citando_o_prazo(
    empresa, usuario_gestor_a, monkeypatch
):
    """A janela do 1º semestre de 2027 é a da fonte citada: de 03/11 a 20/12/2026 (Res. CGSN
    194/2026). Antes e depois, a recusa nomeia o prazo — e nada muda. Nas bordas da janela, passa.
    """
    _registrar(empresa, usuario_gestor_a)
    for hoje in (date(2026, 11, 2), date(2026, 12, 21)):
        fixar_hoje(monkeypatch, hoje)
        with pytest.raises(servico_receita.ReceitaErro) as exc:
            _cancelar(empresa, usuario_gestor_a)
        assert "03/11/2026 a 20/12/2026" in exc.value.mensagem
        assert "Res. CGSN 194/2026" in exc.value.mensagem
        assert f"Hoje é {hoje:%d/%m/%Y}" in exc.value.mensagem
        assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False

    # 20/12/2026 é o último dia da janela: cancelar é admitido.
    fixar_hoje(monkeypatch, date(2026, 12, 20))
    linha = _cancelar(empresa, usuario_gestor_a)
    assert linha.cancelada_em is not None


def test_o_2_semestre_de_2027_vale_a_regra_geral_ate_31_05(empresa, usuario_gestor_a, monkeypatch):
    """A Res. 194/2026 só trata do primeiro ciclo (jan-jun/2027); no 2º semestre de 2027 vale a
    regra geral dos arts. 40-C/40-D: cancelável ATÉ 31/05/2027. Em 01/06/2027 a recusa cita o
    prazo; em 31/05/2027, o cancelamento é admitido.
    """
    _registrar(empresa, usuario_gestor_a, semestre=2)
    fixar_hoje(monkeypatch, date(2027, 6, 1))
    with pytest.raises(servico_receita.ReceitaErro) as exc:
        _cancelar(empresa, usuario_gestor_a, semestre=2)
    assert "até 31/05/2027" in exc.value.mensagem
    assert "arts. 40-C e 40-D" in exc.value.mensagem

    fixar_hoje(monkeypatch, date(2027, 5, 31))
    linha = _cancelar(empresa, usuario_gestor_a, semestre=2)
    assert linha.cancelada_em is not None


def test_cancelamento_sem_opcao_ativa_e_recusado(empresa, usuario_gestor_a, monkeypatch):
    """Sem opção registrada no semestre, não há o que cancelar: a recusa nomeada vem do serviço."""
    fixar_hoje(monkeypatch, date(2026, 12, 1))
    with pytest.raises(servico_receita.ReceitaErro) as exc:
        _cancelar(empresa, usuario_gestor_a)
    assert exc.value.mensagem == servico_receita.mensagem_cancelamento_sem_opcao(2027, 1)
    assert "registre a opção primeiro" in exc.value.mensagem


def test_cancelar_duas_vezes_e_recusado(empresa, usuario_gestor_a, monkeypatch):
    """O cancelamento é ato único: a segunda tentativa é recusada como conflito de estado, e a
    linha cancelada continua no banco, do jeito que ficou."""
    _registrar(empresa, usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))
    _cancelar(empresa, usuario_gestor_a)

    with pytest.raises(servico_receita.ReceitaErro) as exc:
        _cancelar(empresa, usuario_gestor_a)
    assert exc.value.mensagem == servico_receita.mensagem_opcao_ja_cancelada(2027, 1)

    linha = OpcaoRegimeIbsCbsSimples.objects.get(empresa=empresa)
    assert linha.motivo_cancelamento == MOTIVO


def test_re_registro_depois_do_cancelamento_aceito_e_vira_a_unica_ativa(
    empresa, usuario_gestor_a, monkeypatch
):
    """O cancelamento LIBERA o (empresa, ano, semestre): registrar de novo é aceito, e a nova
    linha vira a única ativa (a restrição única é parcial em `cancelada_em__isnull=True`). A
    segunda ATIVA continua impossível — é o que o insert-only protegia.
    """
    _registrar(empresa, usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))
    _cancelar(empresa, usuario_gestor_a)

    nova = _registrar(empresa, usuario_gestor_a, regime=RegimeIbsCbsSimples.REGIME_REGULAR)

    assert nova.cancelada_em is None
    assert OpcaoRegimeIbsCbsSimples.objects.filter(empresa=empresa).count() == 2
    assert (
        OpcaoRegimeIbsCbsSimples.objects.filter(empresa=empresa, cancelada_em__isnull=True).count()
        == 1
    )
    # A nova opção é a que vale para o motor.
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is True
    # E a segunda opção ATIVA do mesmo semestre continua recusada (insert-only enquanto ativa).
    with pytest.raises(servico_receita.ReceitaErro, match="já foi registrada"):
        _registrar(empresa, usuario_gestor_a)


def test_o_motivo_do_cancelamento_e_obrigatorio(empresa, usuario_gestor_a, monkeypatch):
    """Motivo vazio, só com espaços, curto demais ou longo demais é recusado (padrão dos estornos
    da casa, mais o piso de `MOTIVO_CANCELAMENTO_MINIMO`), e nada muda."""
    _registrar(empresa, usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))
    for motivo in ("", "   ", "x", "m" * (servico_receita.MOTIVO_MAXIMO + 1)):
        with pytest.raises(servico_receita.EntradaInvalidaReceita):
            _cancelar(empresa, usuario_gestor_a, motivo=motivo)
        assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False

    # O motivo do tamanho do teto é aceito.
    linha = _cancelar(empresa, usuario_gestor_a, motivo="m" * servico_receita.MOTIVO_MAXIMO)
    assert linha.cancelada_em is not None


# ---------------------------------------------------------------------------
# API do cancelamento: permissão, isolamento, entrada e o efeito no GET
# ---------------------------------------------------------------------------


def test_gestor_cancela_pela_api_e_o_dado_volta_a_nao_informado(
    client, empresa, usuario_gestor_a, monkeypatch
):
    """POST cancela e devolve o ato (com o motivo); depois dele, o GET de leitura volta a dizer
    "opção não informada" — o contrato da leitura é o estado ATIVO, e a opção cancelada não é
    ativa."""
    _registrar(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))

    resposta = client.post(
        _url_cancelar(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "motivo": MOTIVO}),
        content_type="application/json",
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ano"] == 2027 and corpo["semestre"] == 1
    assert corpo["regime"] == RegimeIbsCbsSimples.REGIME_UNICO
    assert corpo["cancelada"] is True
    assert corpo["cancelada_em"] is not None
    assert corpo["motivo_cancelamento"] == MOTIVO
    lido = client.get(f"{_url_opcao(empresa)}?ano=2027&semestre=1").json()
    assert lido == {
        "ano": 2027,
        "semestre": 1,
        "regime": None,
        "informada": False,
        "registrada_em": None,
    }


def test_api_de_cancelamento_sem_motivo_e_400(client, empresa, usuario_gestor_a, monkeypatch):
    _registrar(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))
    resposta = client.post(
        _url_cancelar(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "motivo": "  "}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert "motivo" in resposta.json()[0]
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False


def test_api_de_cancelamento_fora_da_janela_e_409_com_o_prazo(
    client, empresa, usuario_gestor_a, monkeypatch
):
    _registrar(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 21))
    resposta = client.post(
        _url_cancelar(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "motivo": MOTIVO}),
        content_type="application/json",
    )
    assert resposta.status_code == 409
    assert "03/11/2026 a 20/12/2026" in resposta.json()["detail"]
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False


def test_api_de_cancelamento_campo_fora_do_contrato_e_400(
    client, empresa, usuario_gestor_a, monkeypatch
):
    _registrar(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))
    resposta = client.post(
        _url_cancelar(empresa),
        data=json.dumps({"ano": 2027, "semestre": 1, "motivo": MOTIVO, "extra": "x"}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False


def test_cancelamento_pela_api_respeita_permissao_e_isolamento(
    client, empresa, escritorio_a, escritorio_b, usuario_gestor_a, monkeypatch
):
    """CLIENTE e PARALEGAL não cancelam (403); a empresa de OUTRO escritório é 404 sem confirmar
    o id. Em todos os casos, nada é gravado (AGENTS §11)."""
    _registrar(empresa, usuario_gestor_a)
    fixar_hoje(monkeypatch, date(2026, 12, 1))
    corpo = json.dumps({"ano": 2027, "semestre": 1, "motivo": MOTIVO})

    paralegal = _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-cancela-dl088")
    cliente = _usuario(escritorio_a, Papel.CLIENTE, "cliente-cancela-dl088")
    intruso = _usuario(escritorio_b, Papel.GESTOR, "gestor-intruso-cancela-dl088")
    for usuario, esperado in ((paralegal, 403), (cliente, 403), (intruso, 404)):
        client.force_login(usuario)
        resposta = client.post(_url_cancelar(empresa), data=corpo, content_type="application/json")
        assert resposta.status_code == esperado, usuario.username
    assert servico_receita.opcao_regime_ibs_cbs_do_semestre(empresa, 2027, 1) is False
