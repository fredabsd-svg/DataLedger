"""Testes da fatia 1 da DL-043 (BL-474, RC-104/RC-105) — parâmetro contábil
por empresa COM VIGÊNCIA: `registrar_parametro_contabil`,
`encerrar_vigencia_de_parametro_contabil` e as duas rotas de API
(`ParametrosContabeisListCreateView`/`EncerrarVigenciaParametroContabilView`).

Fora do escopo deste arquivo: `zerar_resultado` (fatia 2 do plano
DL-043) — a periodicidade e as contas de destino são só CADASTRADAS aqui,
nunca aplicadas a um zeramento de fato, exceto no critério 10, em que um
`LancamentoContabil` com a chave de idempotência do PREFIXO de zeramento é
gravado só para servir de "zeramento já existe" ao teste de retroatividade
— nenhuma chamada a `zerar_resultado` acontece neste arquivo.

Cada teste está numerado pelo critério de aceite que cobre (ver o pedido da
tarefa). Dados 100% sintéticos, criados nos próprios testes.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import (
    Conta,
    NaturezaConta,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    ParametroContabilInvalido,
    VigenciaParametroContabilConflitante,
    criar_lancamento,
    registrar_parametro_contabil,
)
from apps.empresas.models import Empresa, ModoEscrituracao
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


def _conta(empresa, codigo, nome, tipo, natureza, aceita_lancamento=True):
    return Conta.objects.create(
        empresa=empresa,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        aceita_lancamento=aceita_lancamento,
    )


@pytest.fixture
def cenario():
    """Uma empresa em modo contabilidade, com plano de contas mínimo para o
    parâmetro de zeramento: as três contas de destino VÁLIDAS (Patrimônio
    Líquido, analíticas, distintas — a de prejuízos com natureza devedora,
    RC-61) e mais três contas que só servem para os cenários de RECUSA
    (outro tipo, sintética, natureza errada)."""
    escritorio = Escritorio.objects.create(nome="Escritório DL-043", cnpj="12312312000199")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="ACME Zeramento DL-043 LTDA", cnpj="11444777000161"
    )
    caixa = _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)
    capital = _conta(
        empresa, "2.1", "Capital Social", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA
    )
    resultado = _conta(
        empresa,
        "2.2",
        "Resultado do Exercício",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.CREDORA,
    )
    lucros = _conta(
        empresa, "2.3", "Lucros Acumulados", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA
    )
    prejuizos = _conta(
        empresa,
        "2.4",
        "(-) Prejuízos Acumulados",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.DEVEDORA,
    )
    sintetica_pl = _conta(
        empresa,
        "2.5",
        "Grupo PL sintético",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.CREDORA,
        aceita_lancamento=False,
    )
    prejuizos_natureza_errada = _conta(
        empresa,
        "2.6",
        "Prejuízos com natureza errada",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.CREDORA,
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "caixa": caixa,
        "capital": capital,
        "resultado": resultado,
        "lucros": lucros,
        "prejuizos": prejuizos,
        "sintetica_pl": sintetica_pl,
        "prejuizos_natureza_errada": prejuizos_natureza_errada,
    }


def _url_parametros(empresa_id):
    return reverse("contabilidade:parametros-contabeis", args=[empresa_id])


def _url_encerrar(empresa_id):
    return reverse("contabilidade:parametros-contabeis-encerrar", args=[empresa_id])


def _corpo_valido(cenario, **overrides):
    corpo = {
        "periodicidade_zeramento": PeriodicidadeZeramento.MENSAL,
        "conta_resultado_do_exercicio": cenario["resultado"].id,
        "conta_lucros_acumulados": cenario["lucros"].id,
        "conta_prejuizos_acumulados": cenario["prejuizos"].id,
        "vigencia_inicio": "2026-01-01",
    }
    corpo.update(overrides)
    return corpo


def _registrar(cenario, **overrides):
    """Chama `registrar_parametro_contabil` com os três destinos válidos do
    `cenario`, exceto o que `overrides` substituir — reduz repetição nos
    testes que exercitam o SERVIÇO diretamente (critérios 8, 9 e 10)."""
    kwargs = {
        "empresa": cenario["empresa"],
        "periodicidade_zeramento": PeriodicidadeZeramento.MENSAL,
        "conta_resultado_do_exercicio": cenario["resultado"],
        "conta_lucros_acumulados": cenario["lucros"],
        "conta_prejuizos_acumulados": cenario["prejuizos"],
        "vigencia_inicio": date(2026, 1, 1),
    }
    kwargs.update(overrides)
    return registrar_parametro_contabil(**kwargs)


# ---------------------------------------------------------------------------
# Critério 1 — criar vigência válida (mensal) com sucesso, 201, campos
# corretos na resposta.
# ---------------------------------------------------------------------------


def test_criterio1_criar_vigencia_valida_e_sucesso_com_201_e_campos_corretos(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c1-gestor")

    resposta = client.post(
        _url_parametros(empresa.id), data=_corpo_valido(cenario), content_type="application/json"
    )

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["empresa"] == empresa.id
    assert corpo["periodicidade_zeramento"] == PeriodicidadeZeramento.MENSAL
    assert corpo["conta_resultado_do_exercicio"] == cenario["resultado"].id
    assert corpo["conta_lucros_acumulados"] == cenario["lucros"].id
    assert corpo["conta_prejuizos_acumulados"] == cenario["prejuizos"].id
    assert corpo["vigencia_inicio"] == "2026-01-01"
    assert corpo["vigencia_fim"] is None
    assert ParametroContabilEmpresa.objects.filter(empresa=empresa).count() == 1


# ---------------------------------------------------------------------------
# Critério 2 — as quatro causas de recusa das contas: todas 400, nada
# gravado.
# ---------------------------------------------------------------------------


def test_criterio2a_conta_de_outra_empresa_e_400_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Outra Empresa DL-043 Ltda",
        cnpj="22333444000199",
    )
    conta_de_fora = _conta(
        outra_empresa,
        "2.1",
        "PL de outra empresa",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.CREDORA,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c2a-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        data=_corpo_valido(cenario, conta_lucros_acumulados=conta_de_fora.id),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


def test_criterio2b_conta_sintetica_e_400_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c2b-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        data=_corpo_valido(cenario, conta_resultado_do_exercicio=cenario["sintetica_pl"].id),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


def test_criterio2c_conta_fora_do_patrimonio_liquido_e_400_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c2c-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        data=_corpo_valido(cenario, conta_lucros_acumulados=cenario["caixa"].id),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


def test_criterio2d_duas_contas_repetidas_e_400_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c2d-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        # `conta_lucros_acumulados` repete a mesma conta de
        # `conta_resultado_do_exercicio` — duas das três iguais.
        data=_corpo_valido(cenario, conta_lucros_acumulados=cenario["resultado"].id),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 3 — conta de prejuízos com natureza CREDORA (errada) — 400, nada
# gravado.
# ---------------------------------------------------------------------------


def test_criterio3_conta_de_prejuizos_com_natureza_credora_e_400_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c3-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        data=_corpo_valido(
            cenario, conta_prejuizos_acumulados=cenario["prejuizos_natureza_errada"].id
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 4 — periodicidade inválida (fora de mensal/trimestral/anual) —
# 400.
# ---------------------------------------------------------------------------


def test_criterio4_periodicidade_invalida_e_400(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c4-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        data=_corpo_valido(cenario, periodicidade_zeramento="semanal"),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 5 — empresa em modo livro-caixa: recusada, seja pela API, seja
# chamando o serviço diretamente, sem gravar.
# ---------------------------------------------------------------------------


def test_criterio5_empresa_livro_caixa_e_recusada_pela_api_sem_gravar(client, cenario):
    empresa_livro_caixa = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Fulano Livro-Caixa DL-043",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c5-gestor-api")

    resposta = client.post(
        _url_parametros(empresa_livro_caixa.id),
        # Os ids de conta abaixo pertencem a OUTRA empresa (a do `cenario`)
        # de propósito: a recusa por livro-caixa acontece em
        # `EmpresaEscopadaContabilMixin.get_empresa()`, ANTES de qualquer
        # leitura dos campos do corpo — não importa o que os ids apontem.
        data=_corpo_valido(cenario),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa_livro_caixa).exists()


def test_criterio5_empresa_livro_caixa_e_recusada_pelo_servico_direto_sem_gravar(cenario):
    empresa_livro_caixa = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Fulano Livro-Caixa DL-043 B",
        cnpj="11122233000184",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )

    with pytest.raises(ParametroContabilInvalido):
        _registrar(cenario, empresa=empresa_livro_caixa)

    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa_livro_caixa).exists()


# ---------------------------------------------------------------------------
# Critério 6 — segunda vigência ABERTA simultânea para a MESMA empresa,
# criada por fora do serviço (bypass, ORM direto): a SEGUNDA gravação viola
# a `UniqueConstraint` do banco (camada 1). Teste de MODELO.
# ---------------------------------------------------------------------------


def test_criterio6_segunda_vigencia_aberta_simultanea_viola_unique_constraint_do_banco(cenario):
    empresa = cenario["empresa"]
    ParametroContabilEmpresa.objects.create(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=cenario["resultado"],
        conta_lucros_acumulados=cenario["lucros"],
        conta_prejuizos_acumulados=cenario["prejuizos"],
        vigencia_inicio=date(2026, 1, 1),
    )

    # `transaction.atomic()` aninhado (SAVEPOINT): sem ele, o `IntegrityError`
    # deixaria a transação do teste inteira quebrada para a consulta de
    # conferência abaixo — mesmo padrão de
    # test_dl023_regime_tributario_periodo_unico.py.
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            ParametroContabilEmpresa.objects.create(
                empresa=empresa,
                periodicidade_zeramento=PeriodicidadeZeramento.TRIMESTRAL,
                conta_resultado_do_exercicio=cenario["resultado"],
                conta_lucros_acumulados=cenario["lucros"],
                conta_prejuizos_acumulados=cenario["prejuizos"],
                vigencia_inicio=date(2026, 7, 1),
            )

    # ACHADO (não é bug, é consequência medida da defesa em DUAS camadas):
    # duas vigências ABERTAS (`vigencia_fim=None` nas duas) SEMPRE se
    # sobrepõem também pela leitura do GATILHO — `daterange(inicio,
    # 'infinity', '[]')` de uma vigência aberta cobre qualquer data futura,
    # então ela sempre cruza com a outra vigência aberta, não importa a
    # data de início de nenhuma das duas. No PostgreSQL, o gatilho (BEFORE
    # INSERT) executa ANTES da checagem do índice único da
    # `UniqueConstraint` (ordem de execução do próprio motor: gatilhos BEFORE
    # ROW rodam antes da inserção da linha, e é a inserção que aciona a
    # checagem do índice) — por isso a exceção que chega aqui é SEMPRE a do
    # gatilho (`parametro_contabil_sem_sobreposicao`), nunca a da
    # `UniqueConstraint` (`um_periodo_de_parametro_contabil_aberto_por_
    # empresa`), quando as DUAS defesas estão ativas (produção/este banco de
    # teste, PostgreSQL). A `UniqueConstraint` continua sendo a única
    # barreira em SQLite (desenvolvimento local, DE-014, sem o gatilho) —
    # cenário que este teste, rodando em PostgreSQL, não alcança. Medido:
    # ver o relatório de entrega deste arquivo.
    assert erro.value.__cause__.diag.constraint_name in {
        "um_periodo_de_parametro_contabil_aberto_por_empresa",
        "parametro_contabil_sem_sobreposicao",
    }
    assert (
        ParametroContabilEmpresa.objects.filter(empresa=empresa, vigencia_fim__isnull=True).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Critério 7 — sobreposição entre uma vigência JÁ FECHADA e outra nova cujas
# datas se cruzam, por fora do serviço (bypass, ORM direto): viola o GATILHO
# (camada 2) — a UniqueConstraint não alcança este caso porque nenhuma das
# duas está aberta. Teste de MODELO.
# ---------------------------------------------------------------------------


def test_criterio7_sobreposicao_entre_vigencia_fechada_e_nova_viola_o_gatilho(cenario):
    empresa = cenario["empresa"]
    ParametroContabilEmpresa.objects.create(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=cenario["resultado"],
        conta_lucros_acumulados=cenario["lucros"],
        conta_prejuizos_acumulados=cenario["prejuizos"],
        vigencia_inicio=date(2026, 1, 1),
        vigencia_fim=date(2026, 6, 30),
    )

    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            ParametroContabilEmpresa.objects.create(
                empresa=empresa,
                periodicidade_zeramento=PeriodicidadeZeramento.TRIMESTRAL,
                conta_resultado_do_exercicio=cenario["resultado"],
                conta_lucros_acumulados=cenario["lucros"],
                conta_prejuizos_acumulados=cenario["prejuizos"],
                # Sobrepõe o intervalo fechado acima: [2026-03-01, 2026-04-30]
                # cruza com [2026-01-01, 2026-06-30].
                vigencia_inicio=date(2026, 3, 1),
                vigencia_fim=date(2026, 4, 30),
            )

    assert erro.value.__cause__.diag.constraint_name == "parametro_contabil_sem_sobreposicao"
    assert ParametroContabilEmpresa.objects.filter(empresa=empresa).count() == 1


# ---------------------------------------------------------------------------
# Critério 8 — fluxo normal pelo SERVIÇO: a segunda vigência fecha a
# primeira automaticamente no dia anterior ao novo início.
# ---------------------------------------------------------------------------


def test_criterio8_segunda_vigencia_fecha_a_primeira_automaticamente(cenario):
    vigencia1 = _registrar(cenario, vigencia_inicio=date(2026, 1, 1))

    vigencia2 = _registrar(
        cenario,
        periodicidade_zeramento=PeriodicidadeZeramento.TRIMESTRAL,
        vigencia_inicio=date(2026, 7, 1),
    )

    vigencia1.refresh_from_db()
    assert vigencia1.vigencia_fim == date(2026, 6, 30)
    assert vigencia2.vigencia_fim is None
    abertas = ParametroContabilEmpresa.objects.filter(
        empresa=cenario["empresa"], vigencia_fim__isnull=True
    )
    assert list(abertas) == [vigencia2]


# ---------------------------------------------------------------------------
# Critério 9 — nova vigência com `vigencia_inicio` <= início da vigência
# aberta atual: 400 (`ParametroContabilInvalido`), nada gravado.
# ---------------------------------------------------------------------------


def test_criterio9_vigencia_inicio_anterior_ou_igual_a_atual_e_recusada_sem_gravar(cenario):
    _registrar(cenario, vigencia_inicio=date(2026, 1, 1))

    with pytest.raises(ParametroContabilInvalido):
        _registrar(
            cenario,
            periodicidade_zeramento=PeriodicidadeZeramento.TRIMESTRAL,
            # Igual ao início da vigência aberta atual — não é "depois".
            vigencia_inicio=date(2026, 1, 1),
        )

    assert ParametroContabilEmpresa.objects.filter(empresa=cenario["empresa"]).count() == 1


# ---------------------------------------------------------------------------
# Critério 10 — vigência retroativa cobrindo zeramento já gravado: recusada
# com `VigenciaParametroContabilConflitante`; a mesma vigência com início
# POSTERIOR ao zeramento é aceita (controle positivo).
# ---------------------------------------------------------------------------


def test_criterio10_vigencia_retroativa_cobrindo_zeramento_gravado_e_recusada(cenario):
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 31),
        historico="Zeramento sintético de teste (DL-043, critério 10)",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
        chave_idempotencia=f"zeramento:{empresa.pk}:2026-03:etapa1:0",
        # DE-078 item 6 (B4, correção da rodada 1 de auditoria): o prefixo
        # "zeramento:" passou a ser RESERVADO em `criar_lancamento` — só
        # `zerar_resultado` pode usá-lo (`permitir_prefixo_reservado`).
        # Este teste SIMULA um zeramento já gravado (para testar a
        # retroatividade do parâmetro, não a segurança da chave), então
        # precisa do mesmo escape que o próprio sistema usaria.
        permitir_prefixo_reservado=True,
    )

    with pytest.raises(VigenciaParametroContabilConflitante):
        _registrar(cenario, vigencia_inicio=date(2026, 3, 1))
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()

    # Controle positivo: início POSTERIOR à data do zeramento (2026-03-31)
    # é aceito.
    aceita = _registrar(cenario, vigencia_inicio=date(2026, 4, 1))
    assert aceita.pk is not None


# ---------------------------------------------------------------------------
# Critério 11 — encerrar vigência aberta com sucesso (via API): `vigencia_fim`
# fica preenchido com a data de hoje.
# ---------------------------------------------------------------------------


def test_criterio11_encerrar_vigencia_aberta_grava_vigencia_fim_de_hoje(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c11-gestor")
    _registrar(cenario, vigencia_inicio=date(2020, 1, 1))

    resposta = client.post(_url_encerrar(empresa.id))

    assert resposta.status_code == 200, resposta.content
    parametro = ParametroContabilEmpresa.objects.get(empresa=empresa)
    assert parametro.vigencia_fim == timezone.localdate()


# ---------------------------------------------------------------------------
# Critério 12 — encerrar sem nenhuma vigência aberta: 409, nada alterado.
# ---------------------------------------------------------------------------


def test_criterio12_encerrar_sem_vigencia_aberta_e_409_sem_alterar_nada(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c12-gestor")

    resposta = client.post(_url_encerrar(empresa.id))

    assert resposta.status_code == 409, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 13 — permissão: ANALISTA, sem vínculo e CLIENTE recebem 403 nas
# duas rotas (criar e encerrar), sem gravar nada.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "papel,rotulo",
    [(Papel.ANALISTA, "analista"), (None, "sem-vinculo"), (Papel.CLIENTE, "cliente")],
)
def test_criterio13_papel_sem_permissao_recebe_403_nas_duas_rotas_sem_gravar(
    client, cenario, papel, rotulo
):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], papel, f"c13-{rotulo}")

    resposta_criar = client.post(
        _url_parametros(empresa.id), data=_corpo_valido(cenario), content_type="application/json"
    )
    resposta_encerrar = client.post(_url_encerrar(empresa.id))

    assert resposta_criar.status_code == 403, (rotulo, resposta_criar.content)
    assert resposta_encerrar.status_code == 403, (rotulo, resposta_encerrar.content)
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 14 — isolamento entre escritórios: empresa de OUTRO escritório dá
# 404 (GET e POST), nunca 403 nem dado da outra empresa.
# ---------------------------------------------------------------------------


def test_criterio14_empresa_de_outro_escritorio_e_404_no_get_e_no_post(client, cenario):
    outro_escritorio = Escritorio.objects.create(
        nome="Outro Escritório DL-043", cnpj="99888777000166"
    )
    empresa_de_fora = Empresa.objects.create(
        escritorio=outro_escritorio,
        razao_social="Empresa de Fora DL-043 Ltda",
        cnpj="55666777000188",
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c14-gestor")

    resposta_get = client.get(_url_parametros(empresa_de_fora.id))
    resposta_post = client.post(
        _url_parametros(empresa_de_fora.id),
        data=_corpo_valido(cenario),
        content_type="application/json",
    )

    assert resposta_get.status_code == 404, resposta_get.content
    assert resposta_post.status_code == 404, resposta_post.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa_de_fora).exists()


# ---------------------------------------------------------------------------
# Critério 15 — isolamento entre empresas do MESMO escritório: listar
# vigências da empresa A não mostra vigências da empresa B.
# ---------------------------------------------------------------------------


def test_criterio15_listagem_de_uma_empresa_nao_mostra_vigencia_de_outra_do_mesmo_escritorio(
    client, cenario
):
    empresa_a = cenario["empresa"]
    empresa_b = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Outra Empresa DL-043 B Ltda",
        cnpj="22333444000100",
    )
    resultado_b = _conta(
        empresa_b, "2.1", "Resultado B", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA
    )
    lucros_b = _conta(
        empresa_b, "2.2", "Lucros B", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA
    )
    prejuizos_b = _conta(
        empresa_b, "2.3", "Prejuízos B", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.DEVEDORA
    )
    _registrar(cenario, vigencia_inicio=date(2026, 1, 1))
    registrar_parametro_contabil(
        empresa=empresa_b,
        periodicidade_zeramento=PeriodicidadeZeramento.ANUAL,
        conta_resultado_do_exercicio=resultado_b,
        conta_lucros_acumulados=lucros_b,
        conta_prejuizos_acumulados=prejuizos_b,
        vigencia_inicio=date(2026, 1, 1),
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c15-gestor")

    resposta = client.get(_url_parametros(empresa_a.id))

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert len(corpo) == 1
    assert corpo[0]["empresa"] == empresa_a.id


# ---------------------------------------------------------------------------
# Critério 16 — campo extra no corpo do POST (política dos cinco
# dicionários, BL-196): 400, nada gravado.
# ---------------------------------------------------------------------------


def test_criterio16_campo_extra_no_corpo_e_400_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "c16-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        data=_corpo_valido(cenario, empresa=999),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()
