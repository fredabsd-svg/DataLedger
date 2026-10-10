"""DL-089, correção da rodada 1 da auditoria: o que é "automático" para o estorno (BL-73).

A permissão de estornar lançamento automático era decidida só por `origem != manual`. Ficavam
de fora dois caminhos que o próprio sistema gera e que estão gravados como `manual`:

- A1: a importação efetivada ANTES da migração 0026. A coluna nova recebeu o default `manual`,
  mas a chave `importacao:` e o vínculo com `LancamentoImportado` continuam dizendo de onde veio.
- A2: o zeramento do resultado. Ele é ação de ADMINISTRADOR e GESTOR (RC-102), mas o estorno
  dele era aberto a quem só escritura (ANALISTA e FINANCEIRO), e o estorno do zeramento infla
  Lucros e Prejuízos (R2 da DL-043).

A8: a tentativa de estorno negada pela BL-73 (403) também fica na trilha.

Dados sintéticos. Os testes de chave e de vínculo rodam em qualquer banco; a migração de dado
anterior fica em `test_dl089_correcao_migracao.py`.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.models import (
    Conta,
    LancamentoContabil,
    NaturezaConta,
    OrigemLancamento,
    PeriodicidadeZeramento,
    TipoConta,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.services import (
    EstornoDeOrigemAutomaticaNaoPermitido,
    criar_lancamento,
    estornar_lancamento,
    exige_permissao_de_estorno_automatico,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
LOTE = TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS
SHA_SINTETICO = "a" * 64

# Quem estorna automático (BL-73): só ADMINISTRADOR e GESTOR.
PAPEIS_QUE_ESTORNAM_AUTOMATICO = [Papel.ADMINISTRADOR, Papel.GESTOR]
# Quem não estorna automático: os que lançam (ANALISTA, FINANCEIRO) e os que não lançam.
PAPEIS_QUE_NAO_ESTORNAM_AUTOMATICO = [
    Papel.ANALISTA,
    Papel.FINANCEIRO,
    Papel.PARALEGAL,
    Papel.CLIENTE,
]


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório DL-089 correção", "89899000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 Correção Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    return {"escritorio": escritorio, "empresa": empresa, "contas": criar_plano(empresa)}


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _itens(contas, valor="100.00"):
    return [
        {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
        {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
    ]


def _lancar(cenario, *, chave=None, **permissoes):
    """Lançamento manual (sem origem automática), com chave de idempotência opcional.

    `permissoes` são os parâmetros de exceção do serviço (`permitir_prefixo_*`). Com eles, o
    teste grava a MESMA chave que a efetivação de importação ou o zeramento gravaria, mas sem
    a origem automática: é o estado que as importações anteriores à 0026 deixaram no banco.
    """
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Lançamento de correção (sintético)",
        itens=_itens(cenario["contas"]),
        chave_idempotencia=chave,
        **permissoes,
    )


def _automatico(cenario, identificador=1):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Compra importada (sintética)",
        itens=_itens(cenario["contas"]),
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(LOTE, identificador),
    )


def _lote_de_importacao(cenario):
    """Lote recebido de verdade, em conferência (arquivo sintético). Serve de documento."""
    conteudo = (
        "numero;data;historico;conta;lado;valor\r\n"
        "1;2026-03-10;Compra sintética;1.1.1;D;100.00\r\n"
        "1;2026-03-10;Compra sintética;5.1;C;100.00\r\n"
    ).encode("utf-8")
    return servico.receber(
        empresa=cenario["empresa"],
        formato="proprio",
        conteudo=conteudo,
        nome_arquivo="sintetico-dl089-correcao.txt",
        usuario=None,
    )


def _url_estorno(cenario, lancamento):
    return reverse("contabilidade:estornar", args=[cenario["empresa"].id, lancamento.id])


def _estornos_de(lancamento):
    return LancamentoContabil.objects.filter(estorno_de=lancamento).count()


# ---------------------------------------------------------------------------
# A1: importação gravada antes da 0026 (coluna `manual`, chave `importacao:`)
# ---------------------------------------------------------------------------


def test_a1_predicado_reconhece_chave_de_importacao_mesmo_com_origem_manual(cenario):
    original = _lancar(
        cenario, chave=f"importacao:{SHA_SINTETICO}:1", permitir_prefixo_da_importacao=True
    )

    assert original.origem == OrigemLancamento.MANUAL
    assert exige_permissao_de_estorno_automatico(original) is True


@pytest.mark.parametrize("papel", PAPEIS_QUE_NAO_ESTORNAM_AUTOMATICO)
def test_a1_importacao_anterior_a_0026_recusa_quem_nao_estorna_automatico(cenario, papel):
    original = _lancar(
        cenario, chave=f"importacao:{SHA_SINTETICO}:1", permitir_prefixo_da_importacao=True
    )

    with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido):
        estornar_lancamento(original, papel=papel)

    assert _estornos_de(original) == 0


@pytest.mark.parametrize("papel", PAPEIS_QUE_ESTORNAM_AUTOMATICO)
def test_a1_importacao_anterior_a_0026_estornada_por_quem_tem_permissao(cenario, papel):
    original = _lancar(
        cenario, chave=f"importacao:{SHA_SINTETICO}:1", permitir_prefixo_da_importacao=True
    )

    estorno = estornar_lancamento(original, papel=papel)

    assert estorno.estorno_de_id == original.pk


@pytest.mark.parametrize("papel", PAPEIS_QUE_NAO_ESTORNAM_AUTOMATICO)
def test_a1_lancamento_vinculado_a_importacao_recusa_quem_nao_estorna_automatico(cenario, papel):
    """O segundo sinal de A1: o vínculo com `LancamentoImportado`, mesmo sem chave `importacao:`."""
    original = _lancar(cenario)
    # O lote já traz o lançamento importado de número "1" (ainda não efetivado): só o aponto
    # para o lançamento do Diário, como faz a efetivação.
    importado = _lote_de_importacao(cenario).lancamentos.get(numero_origem="1")
    importado.lancamento = original
    importado.save()

    assert exige_permissao_de_estorno_automatico(original) is True
    with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido):
        estornar_lancamento(original, papel=papel)


def test_a1_manual_sem_chave_e_sem_vinculo_continua_livre_para_quem_lanca(cenario):
    """Sem regressão: o digitado à mão segue estornável por quem lança (ANALISTA)."""
    original = _lancar(cenario)

    assert exige_permissao_de_estorno_automatico(original) is False
    estorno = estornar_lancamento(original, papel=Papel.ANALISTA)

    assert estorno.origem == OrigemLancamento.MANUAL


@pytest.mark.parametrize(
    "chave, esperado",
    [
        (f"importacao:{SHA_SINTETICO}:1", True),
        (f"IMPORTACAO:{SHA_SINTETICO}:1", True),
        ("zeramento:7:2026:3:1", True),
        ("ZERAMENTO:7:2026:3:1", True),
        ("importacao_x", False),
        ("minha-chave-de-cliente", False),
        (None, False),
    ],
)
def test_a1_a2_predicado_compara_prefixo_sem_diferenciar_caixa(cenario, chave, esperado):
    """A mesma regra de caixa da recusa de chave em `criar_lancamento`: um prefixo que a recusa
    deixaria passar não pode escapar da permissão de estorno."""
    original = _lancar(
        cenario,
        chave=chave,
        permitir_prefixo_da_importacao=True,
        permitir_prefixo_reservado=True,
    )

    assert exige_permissao_de_estorno_automatico(original) is esperado


# ---------------------------------------------------------------------------
# A2: estorno do zeramento do resultado
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_com_resultado(db):
    """Empresa com plano mínimo de resultado e parâmetro contábil vigente (como a DL-043)."""
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-089 zeramento", cnpj="11333555000199"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="ACME Zeramento DL-089 Ltda", cnpj="11444777000161"
    )
    contas = {
        "caixa": Conta.objects.create(
            empresa=empresa,
            codigo="1.1",
            nome="Caixa",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
        ),
        "receita": Conta.objects.create(
            empresa=empresa,
            codigo="3.1",
            nome="Receita de Serviços",
            tipo=TipoConta.RECEITA,
            natureza=NaturezaConta.CREDORA,
        ),
        "resultado": Conta.objects.create(
            empresa=empresa,
            codigo="2.9.1",
            nome="Resultado do Exercício",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=NaturezaConta.CREDORA,
        ),
        "lucros": Conta.objects.create(
            empresa=empresa,
            codigo="2.9.2",
            nome="Lucros Acumulados",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=NaturezaConta.CREDORA,
        ),
        "prejuizos": Conta.objects.create(
            empresa=empresa,
            codigo="2.9.3",
            nome="(-) Prejuízos Acumulados",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=NaturezaConta.DEVEDORA,
        ),
    }
    gestor = _usuario(escritorio, Papel.GESTOR, "gestor-zeramento-dl089")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 1, 15),
        historico="Venda de teste (sintética)",
        itens=[
            {"conta": contas["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": contas["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    zeramento = resultado["lancamento_etapa1"]
    assert zeramento is not None and zeramento.chave_idempotencia.startswith("zeramento:")
    return {"escritorio": escritorio, "empresa": empresa, "zeramento": zeramento}


def test_a2_zeramento_e_automatico_para_o_estorno_mesmo_com_origem_manual(cenario_com_resultado):
    zeramento = cenario_com_resultado["zeramento"]

    assert zeramento.origem == OrigemLancamento.MANUAL
    assert exige_permissao_de_estorno_automatico(zeramento) is True


@pytest.mark.parametrize("papel", PAPEIS_QUE_NAO_ESTORNAM_AUTOMATICO)
def test_a2_estorno_de_zeramento_recusado_por_quem_so_escritura(
    client, cenario_com_resultado, papel
):
    cenario = cenario_com_resultado
    zeramento = cenario["zeramento"]
    _usuario(cenario["escritorio"], papel, f"sem-permissao-zeramento-{papel}")
    assert client.login(username=f"sem-permissao-zeramento-{papel}", password=SENHA)
    antes = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()

    response = client.post(
        reverse("contabilidade:estornar", args=[cenario["empresa"].id, zeramento.id])
    )

    assert response.status_code == 403
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == antes
    assert _estornos_de(zeramento) == 0


@pytest.mark.parametrize("papel", PAPEIS_QUE_ESTORNAM_AUTOMATICO)
def test_a2_estorno_de_zeramento_permitido_a_administrador_e_gestor(
    client, cenario_com_resultado, papel
):
    cenario = cenario_com_resultado
    zeramento = cenario["zeramento"]
    _usuario(cenario["escritorio"], papel, f"com-permissao-zeramento-{papel}")
    assert client.login(username=f"com-permissao-zeramento-{papel}", password=SENHA)

    response = client.post(
        reverse("contabilidade:estornar", args=[cenario["empresa"].id, zeramento.id])
    )

    assert response.status_code == 201
    assert _estornos_de(zeramento) == 1


def test_a2_servico_recusa_estorno_de_zeramento_sem_papel(cenario_com_resultado):
    zeramento = cenario_com_resultado["zeramento"]

    with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido):
        estornar_lancamento(zeramento)

    assert _estornos_de(zeramento) == 0


# ---------------------------------------------------------------------------
# A8: a tentativa negada (403 da BL-73) fica na trilha, sem segredo
# ---------------------------------------------------------------------------


def test_a8_tentativa_negada_de_estorno_automatico_grava_trilha(client, cenario):
    original = _automatico(cenario)
    analista = _usuario(cenario["escritorio"], Papel.ANALISTA, "analista-negado-dl089")
    assert client.login(username="analista-negado-dl089", password=SENHA)

    response = client.post(_url_estorno(cenario, original))

    assert response.status_code == 403
    negativa = RegistroAuditoria.objects.get(acao="lancamento.estorno_negado")
    assert negativa.objeto_tipo == "LancamentoContabil"
    assert negativa.objeto_id == str(original.pk)
    assert negativa.usuario == analista
    assert negativa.escritorio == cenario["escritorio"]
    # Só o papel e os identificadores: nada sensível, nem o corpo da requisição.
    assert negativa.detalhes == {
        "papel": Papel.ANALISTA,
        "origem": OrigemLancamento.IMPORTACAO,
        "motivo": "origem_automatica_sem_permissao",
    }
    assert not RegistroAuditoria.objects.filter(acao="lancamento.estornado").exists()
    assert _estornos_de(original) == 0


def test_a8_estorno_permitido_nao_grava_negativa(client, cenario):
    original = _automatico(cenario)
    _usuario(cenario["escritorio"], Papel.GESTOR, "gestor-permitido-dl089")
    assert client.login(username="gestor-permitido-dl089", password=SENHA)

    response = client.post(_url_estorno(cenario, original))

    assert response.status_code == 201
    assert not RegistroAuditoria.objects.filter(acao="lancamento.estorno_negado").exists()
    assert RegistroAuditoria.objects.filter(acao="lancamento.estornado").count() == 1


def test_a8_estorno_manual_negado_por_regra_de_estado_nao_grava_negativa(client, cenario):
    """A trilha da negativa é só para a BL-73. Um 400 de outra regra não entra nela."""
    original = _lancar(cenario)
    estornar_lancamento(original, papel=Papel.ANALISTA)
    _usuario(cenario["escritorio"], Papel.ANALISTA, "analista-repetido-dl089")
    assert client.login(username="analista-repetido-dl089", password=SENHA)

    response = client.post(_url_estorno(cenario, original))

    assert response.status_code == 400
    assert not RegistroAuditoria.objects.filter(acao="lancamento.estorno_negado").exists()
