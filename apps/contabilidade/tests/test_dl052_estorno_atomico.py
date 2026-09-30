"""DL-052 (M1) — gravação do livro e trilha de auditoria na MESMA transação.

O defeito medido em 30/09/2026: `EstornarLancamentoView.post` chamava
`estornar_lancamento` (`@transaction.atomic`) e só DEPOIS `registrar`. Como
`ATOMIC_REQUESTS` está desligado, o serviço era a transação mais externa e
comitava sozinho; com a trilha falhando, a resposta era 500, o estorno ficava
gravado SEM registro de auditoria e o lançamento passava a constar como "já
estornado" — o contador não conseguia refazer. A varredura desta etapa achou
o MESMO padrão em `LancamentoListCreateView.post` (API de criação de
lançamento): o comentário do BL-14 dizia que o `with transaction.atomic()`
cobria o `criar_lancamento`, mas o `with` só cobria o `registrar`.

Critério 6 do plano: com `registrar` forçado a falhar → nada gravado, e a
operação pode ser refeita depois. Cada rota da API contábil que GRAVA e audita
tem um teste abaixo; as de competência, parâmetro, zeramento e classificação
já tinham o `registrar` dentro do serviço atômico, e os testes travam isso.

`registrar` é forçado a falhar com `RuntimeError` (falha de infraestrutura, não
de negócio). A exceção propaga pelo cliente de teste, como o 500 real. Dados
sintéticos.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    Competencia,
    Conta,
    EstadoCompetencia,
    LancamentoContabil,
    NaturezaConta,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    criar_lancamento,
    encerrar_competencia,
    registrar_parametro_contabil,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
REGISTRAR_NO_SERVICO = "apps.contabilidade.services.registrar"
REGISTRAR_NA_VIEW = "apps.contabilidade.views.registrar"


def _falha_da_trilha():
    return RuntimeError("trilha de auditoria indisponível (simulado)")


@pytest.fixture
def cenario(client):
    escritorio = Escritorio.objects.create(nome="Escritório DL-052", cnpj="20202020000120")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-052 Ltda", cnpj="20212223000190"
    )

    def conta(codigo, nome, tipo, natureza):
        return Conta.objects.create(
            empresa=empresa, codigo=codigo, nome=nome, tipo=tipo, natureza=natureza
        )

    caixa = conta("1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)
    receita = conta("3.1", "Receita de Serviços", TipoConta.RECEITA, NaturezaConta.CREDORA)
    resultado = conta(
        "2.9.1", "Resultado do Exercício", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA
    )
    lucros = conta(
        "2.9.2", "Lucros Acumulados", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA
    )
    prejuizos = conta(
        "2.9.3", "(-) Prejuízos Acumulados", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.DEVEDORA
    )
    gestor = get_user_model().objects.create_user(
        username="gestor-dl052", email="gestor-dl052@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=gestor, escritorio=escritorio, papel=Papel.GESTOR
    )
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=resultado,
        conta_lucros_acumulados=lucros,
        conta_prejuizos_acumulados=prejuizos,
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    assert client.login(username="gestor-dl052", password=SENHA)
    return {
        "empresa": empresa,
        "caixa": caixa,
        "receita": receita,
        "resultado": resultado,
        "lucros": lucros,
        "prejuizos": prejuizos,
        "gestor": gestor,
    }


def _lancar(cenario, data=date(2026, 1, 15), valor=Decimal("100.00")):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=data,
        historico="Receita de teste",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": valor},
            {"conta": cenario["receita"], "tipo": TipoPartida.CREDITO, "valor": valor},
        ],
        criado_por=cenario["gestor"],
    )


def _trilha(acao):
    return RegistroAuditoria.objects.filter(acao=acao).count()


# ---------------------------------------------------------------------------
# Estorno (o defeito M1 original)
# ---------------------------------------------------------------------------


def test_estorno_com_trilha_falhando_nao_grava_e_pode_ser_refeito(client, cenario):
    original = _lancar(cenario)
    url = reverse("contabilidade:estornar", args=[cenario["empresa"].id, original.id])

    with patch(REGISTRAR_NA_VIEW, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url)

    assert LancamentoContabil.objects.filter(estorno_de=original).count() == 0
    assert LancamentoContabil.objects.count() == 1
    assert _trilha("lancamento.estornado") == 0

    # Refazer: o lançamento NÃO consta como "já estornado".
    depois = client.post(url)

    assert depois.status_code == 201
    assert LancamentoContabil.objects.filter(estorno_de=original).count() == 1
    assert _trilha("lancamento.estornado") == 1


def test_estorno_bem_sucedido_continua_gravando_estorno_e_trilha_juntos(client, cenario):
    original = _lancar(cenario)

    resposta = client.post(
        reverse("contabilidade:estornar", args=[cenario["empresa"].id, original.id])
    )

    assert resposta.status_code == 201
    estorno = LancamentoContabil.objects.get(estorno_de=original)
    assert resposta.json()["id"] == estorno.id
    trilha = RegistroAuditoria.objects.get(acao="lancamento.estornado")
    assert trilha.detalhes["lancamento_original_id"] == original.id


def test_estorno_recusado_por_regra_de_negocio_continua_400_e_sem_trilha(client, cenario):
    original = _lancar(cenario)
    url = reverse("contabilidade:estornar", args=[cenario["empresa"].id, original.id])
    assert client.post(url).status_code == 201

    repetido = client.post(url)

    assert repetido.status_code == 400
    assert LancamentoContabil.objects.filter(estorno_de=original).count() == 1
    assert _trilha("lancamento.estornado") == 1


# ---------------------------------------------------------------------------
# Criação de lançamento pela API (mesmo padrão, achado na varredura)
# ---------------------------------------------------------------------------


def _corpo_do_lancamento(cenario):
    return {
        "data": "2026-01-20",
        "historico": "Lançamento pela API",
        "itens": [
            {"conta": cenario["caixa"].id, "tipo": "debito", "valor": "50.00"},
            {"conta": cenario["receita"].id, "tipo": "credito", "valor": "50.00"},
        ],
    }


def test_criacao_de_lancamento_com_trilha_falhando_nao_grava_e_retentativa_cria(client, cenario):
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa"].id])
    chave = {"headers": {"Idempotency-Key": "chave-dl052-0001"}}

    with patch(REGISTRAR_NA_VIEW, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(
                url, data=_corpo_do_lancamento(cenario), content_type="application/json", **chave
            )

    assert LancamentoContabil.objects.count() == 0
    assert _trilha("lancamento.criado") == 0

    # A retentativa com a MESMA chave de idempotência cria de verdade (201) — e
    # não "reaproveita" um lançamento órfão de trilha respondendo 200.
    depois = client.post(
        url, data=_corpo_do_lancamento(cenario), content_type="application/json", **chave
    )

    assert depois.status_code == 201
    assert LancamentoContabil.objects.count() == 1
    assert _trilha("lancamento.criado") == 1


def test_criacao_de_lancamento_recusada_por_negocio_continua_400(client, cenario):
    corpo = _corpo_do_lancamento(cenario)
    corpo["itens"][1]["valor"] = "49.00"  # desbalanceado

    resposta = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data=corpo,
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0


def test_criacao_de_conta_com_trilha_falhando_nao_grava(client, cenario):
    url = reverse("contabilidade:contas", args=[cenario["empresa"].id])
    corpo = {"codigo": "1.9", "nome": "Conta nova", "tipo": "ativo", "natureza": "devedora"}

    with patch(REGISTRAR_NA_VIEW, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url, data=corpo, content_type="application/json")

    assert not Conta.objects.filter(empresa=cenario["empresa"], codigo="1.9").exists()
    assert client.post(url, data=corpo, content_type="application/json").status_code == 201


# ---------------------------------------------------------------------------
# Rotas cuja trilha mora no serviço (já atômicas): travadas por teste
# ---------------------------------------------------------------------------


def _competencia(cenario, mes=1):
    return Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=mes)


def test_encerrar_competencia_com_trilha_falhando_nao_encerra(client, cenario):
    _lancar(cenario)
    url = reverse("contabilidade:encerrar-competencia", args=[cenario["empresa"].id, 2026, 1])

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url)

    assert _competencia(cenario).estado == EstadoCompetencia.ABERTA
    assert client.post(url).status_code == 200
    assert _competencia(cenario).estado == EstadoCompetencia.ENCERRADA


def test_reabrir_competencia_com_trilha_falhando_continua_encerrada(client, cenario):
    _lancar(cenario)
    encerrar_competencia(empresa=cenario["empresa"], ano=2026, mes=1, usuario=cenario["gestor"])
    url = reverse("contabilidade:reabrir-competencia", args=[cenario["empresa"].id, 2026, 1])
    corpo = {"motivo": "Correção de lançamento esquecido"}

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url, data=corpo, content_type="application/json")

    competencia = _competencia(cenario)
    assert competencia.estado == EstadoCompetencia.ENCERRADA
    assert competencia.fechada_em is not None
    assert client.post(url, data=corpo, content_type="application/json").status_code == 200


def test_entregar_competencia_com_trilha_falhando_nao_marca_entrega(client, cenario):
    _lancar(cenario)
    encerrar_competencia(empresa=cenario["empresa"], ano=2026, mes=1, usuario=cenario["gestor"])
    url = reverse("contabilidade:entregar-competencia", args=[cenario["empresa"].id, 2026, 1])

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url)

    assert _competencia(cenario).entregue_em is None
    assert client.post(url).status_code == 200
    assert _competencia(cenario).entregue_em is not None


def test_novo_parametro_contabil_com_trilha_falhando_nao_grava_nem_fecha_a_vigencia(
    client, cenario
):
    url = reverse("contabilidade:parametros-contabeis", args=[cenario["empresa"].id])
    corpo = {
        "periodicidade_zeramento": PeriodicidadeZeramento.ANUAL,
        "conta_resultado_do_exercicio": cenario["resultado"].id,
        "conta_lucros_acumulados": cenario["lucros"].id,
        "conta_prejuizos_acumulados": cenario["prejuizos"].id,
        "vigencia_inicio": "2027-01-01",
    }

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url, data=corpo, content_type="application/json")

    parametro = ParametroContabilEmpresa.objects.get(empresa=cenario["empresa"])
    assert parametro.vigencia_fim is None  # a vigência anterior NÃO foi fechada
    assert client.post(url, data=corpo, content_type="application/json").status_code == 201
    assert ParametroContabilEmpresa.objects.filter(empresa=cenario["empresa"]).count() == 2


def test_encerrar_vigencia_do_parametro_com_trilha_falhando_continua_aberta(client, cenario):
    url = reverse("contabilidade:parametros-contabeis-encerrar", args=[cenario["empresa"].id])

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url)

    assert ParametroContabilEmpresa.objects.get(empresa=cenario["empresa"]).vigencia_fim is None
    assert client.post(url).status_code == 200


def test_zeramento_com_trilha_falhando_nao_grava_lancamento_e_pode_ser_refeito(client, cenario):
    _lancar(cenario, data=date(2026, 1, 31), valor=Decimal("300.00"))
    url = reverse("contabilidade:zeramento", args=[cenario["empresa"].id, 2026, 1])

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.post(url)

    assert LancamentoContabil.objects.count() == 1  # só o de teste; nenhum zeramento
    assert client.post(url).status_code == 200
    # Etapa 1 (receitas/despesas → resultado) e etapa 2 (resultado → lucros).
    assert LancamentoContabil.objects.count() == 3


def test_classificacao_dre_com_trilha_falhando_nao_altera_a_conta(client, cenario):
    url = reverse(
        "contabilidade:conta-classificacao-dre", args=[cenario["empresa"].id, cenario["receita"].id]
    )
    corpo = {"classificacao_dre": "receita_bruta"}

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.patch(url, data=corpo, content_type="application/json")

    cenario["receita"].refresh_from_db()
    assert not cenario["receita"].classificacao_dre
    assert client.patch(url, data=corpo, content_type="application/json").status_code == 200
    cenario["receita"].refresh_from_db()
    assert cenario["receita"].classificacao_dre == "receita_bruta"


def test_classificacao_dlpa_com_trilha_falhando_nao_altera_a_conta(client, cenario):
    url = reverse(
        "contabilidade:conta-classificacao-dlpa", args=[cenario["empresa"].id, cenario["lucros"].id]
    )
    corpo = {"classificacao_dlpa": "lucros_ou_prejuizos_acumulados"}

    with patch(REGISTRAR_NO_SERVICO, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            client.patch(url, data=corpo, content_type="application/json")

    cenario["lucros"].refresh_from_db()
    assert not cenario["lucros"].classificacao_dlpa
    assert client.patch(url, data=corpo, content_type="application/json").status_code == 200


# ---------------------------------------------------------------------------
# Tela web de lançamento (antes só inspecionada): mesma garantia da API
# ---------------------------------------------------------------------------

REGISTRAR_NA_VIEW_WEB = "apps.contabilidade.views_web.registrar"


def _post_web_de_lancamento(client, cenario, chave):
    return client.post(
        reverse("contabilidade_web:lancamento_novo", args=[cenario["empresa"].id]),
        {
            "acao": "gravar",
            "num_linhas": "4",
            "data": "2026-01-20",
            "historico": "Lançamento pela tela",
            "chave_idempotencia": chave,
            "conta_1": str(cenario["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "50,00",
            "conta_2": str(cenario["receita"].id),
            "tipo_2": "credito",
            "valor_2": "50,00",
        },
    )


def test_tela_de_lancamento_com_trilha_falhando_nao_grava_e_retentativa_grava(client, cenario):
    with patch(REGISTRAR_NA_VIEW_WEB, side_effect=_falha_da_trilha()):
        with pytest.raises(RuntimeError):
            _post_web_de_lancamento(client, cenario, "chave-web-dl052")

    assert LancamentoContabil.objects.count() == 0
    assert _trilha("lancamento.criado") == 0

    depois = _post_web_de_lancamento(client, cenario, "chave-web-dl052")

    assert depois.status_code == 302
    assert LancamentoContabil.objects.count() == 1
    assert _trilha("lancamento.criado") == 1
