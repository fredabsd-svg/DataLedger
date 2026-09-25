"""DL-023, critérios 6 a 11 (BL-211/A2, achado A2 da auditoria DL-020
rodada 1).

O defeito medido: `HistoricoRegimeTributarioInline` gravava direto por
`ModelForm`/formset, sem passar por
`apps.empresas.services.registrar_regime_tributario` — medido pelo
auditor: `302` e `periodos ABERTOS simultaneos: 2`. O "último regime" —
justamente o que o RC-86/DE-039 autoriza apagar — deixava de ser único.

A ordem obrigatória de execução da etapa começa pela RESTRIÇÃO DE BANCO
(critério 1 do plano geral, critério 7 aqui): é a única defesa que vale em
TODAS as portas, inclusive ORM direto, shell e importação futura.
"""

import threading
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.empresas.services import (
    excluir_ultimo_regime_tributario,
    registrar_regime_tributario,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL-023-R", cnpj="60606060000133")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-023-R Ltda", cnpj="11444777000161"
    )
    gestor = get_user_model().objects.create_user(
        username="gestor-dl023r", email="gestor-dl023r@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=gestor, escritorio=escritorio, papel=Papel.GESTOR
    )
    admin = get_user_model().objects.create_superuser(
        username="admin-dl023r", email="admin-dl023r@escritorio.com.br", password=SENHA
    )
    return {"escritorio": escritorio, "empresa": empresa, "gestor": gestor, "admin": admin}


# ---------------------------------------------------------------------------
# Critério 7: a invariante vale por ORM DIRETO — sem passar pelo admin nem
# pelo serviço — provada por UniqueConstraint em migração.
# ---------------------------------------------------------------------------


def test_orm_direto_recusa_segundo_periodo_aberto_da_mesma_empresa(cenario):
    HistoricoRegimeTributario.objects.create(
        empresa=cenario["empresa"],
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio=date(2024, 1, 1),
    )

    # A criação em si roda dentro de um SAVEPOINT (`transaction.atomic()`
    # aninhado, já que o pytest-django envolve o teste inteiro numa
    # transação): sem ele, o `IntegrityError` deixaria a transação de
    # teste inteira "quebrada" (`TransactionManagementError` na consulta
    # de conferência logo abaixo) — não é um cuidado do PRODUTO, é do
    # próprio teste tentar consultar depois de um erro de banco.
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            HistoricoRegimeTributario.objects.create(
                empresa=cenario["empresa"],
                regime=RegimeTributario.LUCRO_PRESUMIDO,
                vigencia_inicio=date(2025, 1, 1),
            )

    assert "um_periodo_de_regime_aberto_por_empresa" in str(erro.value)
    assert (
        HistoricoRegimeTributario.objects.filter(
            empresa=cenario["empresa"], vigencia_fim__isnull=True
        ).count()
        == 1
    )


def test_orm_direto_aceita_segundo_periodo_quando_o_primeiro_esta_fechado(cenario):
    """Controle positivo: a constraint restringe só o período ABERTO — duas
    linhas FECHADAS (histórico) continuam coexistindo sem violar nada."""
    HistoricoRegimeTributario.objects.create(
        empresa=cenario["empresa"],
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio=date(2024, 1, 1),
        vigencia_fim=date(2024, 12, 31),
    )

    segundo = HistoricoRegimeTributario.objects.create(
        empresa=cenario["empresa"],
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2025, 1, 1),
    )

    assert HistoricoRegimeTributario.objects.filter(empresa=cenario["empresa"]).count() == 2
    assert segundo.vigencia_fim is None


def test_orm_direto_aceita_periodo_aberto_de_outra_empresa(cenario):
    """Controle: a constraint é POR EMPRESA — cada empresa pode ter o
    próprio período aberto."""
    outra = Empresa.objects.create(
        escritorio=cenario["escritorio"], razao_social="Outra DL-023-R Ltda", cnpj="22333444000181"
    )
    HistoricoRegimeTributario.objects.create(
        empresa=cenario["empresa"],
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio=date(2024, 1, 1),
    )

    HistoricoRegimeTributario.objects.create(
        empresa=outra, regime=RegimeTributario.LUCRO_REAL, vigencia_inicio=date(2024, 1, 1)
    )

    assert HistoricoRegimeTributario.objects.filter(vigencia_fim__isnull=True).count() == 2


# ---------------------------------------------------------------------------
# Critério 6: gravação passa pelo serviço em qualquer porta, ou a porta
# deixa de existir — o inline foi REMOVIDO do EmpresaAdmin (ver o
# docstring de apps/empresas/admin.py). Provado por requisição: o admin
# não cria HistoricoRegimeTributario nenhum, mesmo recebendo os campos do
# antigo formset.
# ---------------------------------------------------------------------------


def test_admin_nao_cria_regime_tributario_mesmo_recebendo_os_campos_do_antigo_inline(
    client, cenario
):
    """BL-254 (achado A1, auditoria DL-023 rodada 1): status EXATO (302,
    não "in (200, 302)") e `razao_social` como controle positivo NO MESMO
    POST — sem isso, um payload quebrado por qualquer outro motivo (CNPJ
    inválido, por exemplo) também daria "200 ou 302" + "nada de regime
    criado", e o teste não distinguiria "a porta está fechada" de "o
    formulário quebrou"."""
    empresa = cenario["empresa"]
    assert client.login(username="admin-dl023r", password=SENHA)

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        {
            "escritorio": cenario["escritorio"].pk,
            "razao_social": "Empresa DL-023-R renomeada Ltda",
            "nome_fantasia": "",
            # DL-038: campos novos do ModelForm automático do admin.
            "tipo_inscricao": empresa.tipo_inscricao,
            "cnpj": empresa.cnpj,
            "cpf": empresa.cpf,
            "modo_escrituracao": empresa.modo_escrituracao,
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
            # Campos do formset que existia: sem o inline registrado, o
            # admin não os reconhece — não formam mais nenhum formset.
            "historico_regime_tributario-TOTAL_FORMS": "1",
            "historico_regime_tributario-INITIAL_FORMS": "0",
            "historico_regime_tributario-MIN_NUM_FORMS": "0",
            "historico_regime_tributario-MAX_NUM_FORMS": "1000",
            "historico_regime_tributario-0-regime": "simples_nacional",
            "historico_regime_tributario-0-vigencia_inicio": "2024-03-01",
            "historico_regime_tributario-0-vigencia_fim": "",
            "_continue": "Salvar e continuar editando",
        },
    )

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.razao_social == "Empresa DL-023-R renomeada Ltda"
    assert not HistoricoRegimeTributario.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 10 (RC-85), também "no admin": como o admin não tem mais NENHUMA
# porta de escrita para regime tributário (item acima), uma vigência futura
# enviada por ali nunca é aceita — é o caso particular do teste acima,
# repetido aqui com data futura para deixar a intenção literal do critério
# explícita.
# ---------------------------------------------------------------------------


def test_admin_nao_cria_regime_tributario_com_vigencia_futura(client, cenario):
    """BL-254: mesmo cuidado do teste acima — status exato e controle
    positivo de `razao_social` no mesmo POST."""
    empresa = cenario["empresa"]
    assert client.login(username="admin-dl023r", password=SENHA)

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        {
            "escritorio": cenario["escritorio"].pk,
            "razao_social": "Empresa DL-023-R renomeada de novo Ltda",
            "nome_fantasia": "",
            # DL-038: campos novos do ModelForm automático do admin.
            "tipo_inscricao": empresa.tipo_inscricao,
            "cnpj": empresa.cnpj,
            "cpf": empresa.cpf,
            "modo_escrituracao": empresa.modo_escrituracao,
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
            "historico_regime_tributario-TOTAL_FORMS": "1",
            "historico_regime_tributario-INITIAL_FORMS": "0",
            "historico_regime_tributario-MIN_NUM_FORMS": "0",
            "historico_regime_tributario-MAX_NUM_FORMS": "1000",
            "historico_regime_tributario-0-regime": "simples_nacional",
            "historico_regime_tributario-0-vigencia_inicio": "9999-12-31",
            "historico_regime_tributario-0-vigencia_fim": "",
            "_continue": "Salvar e continuar editando",
        },
    )

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.razao_social == "Empresa DL-023-R renomeada de novo Ltda"
    assert not HistoricoRegimeTributario.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 10 (RC-86/DE-039), exclusão — já implementada antes desta etapa
# (`excluir_ultimo_regime_tributario`); teste NOVO aqui só para deixar a
# cobertura do critério auto-contida no pacote de testes da DL-023, sem
# reescrever `test_dl019_regime_tributario.py` (fora do escopo do
# desenvolvedor-pleno).
# ---------------------------------------------------------------------------


def test_exclusao_do_ultimo_periodo_devolve_o_anterior_a_vigente_e_grava_trilha(cenario):
    empresa = cenario["empresa"]
    primeiro = registrar_regime_tributario(
        empresa, RegimeTributario.SIMPLES_NACIONAL, date(2024, 1, 1)
    )
    segundo = registrar_regime_tributario(
        empresa, RegimeTributario.LUCRO_PRESUMIDO, date(2025, 1, 1)
    )
    primeiro.refresh_from_db()
    assert primeiro.vigencia_fim == date(2024, 12, 31)

    excluir_ultimo_regime_tributario(empresa=empresa, registro=segundo, usuario=cenario["gestor"])

    primeiro.refresh_from_db()
    assert primeiro.vigencia_fim is None
    assert not HistoricoRegimeTributario.objects.filter(pk=segundo.pk).exists()
    # A UniqueConstraint continua satisfeita: exatamente um período aberto.
    assert (
        HistoricoRegimeTributario.objects.filter(empresa=empresa, vigencia_fim__isnull=True).count()
        == 1
    )
    registro_auditoria = RegistroAuditoria.objects.filter(acao="regime_tributario.excluido").first()
    assert registro_auditoria is not None
    assert registro_auditoria.usuario_id == cenario["gestor"].pk


# ---------------------------------------------------------------------------
# Critério 9: desempate determinístico entre dois períodos de MESMO
# vigencia_inicio — a consulta do "último regime"
# (`excluir_ultimo_regime_tributario`, `order_by("-vigencia_inicio", "-id")`)
# devolve sempre o mesmo registro, em execuções repetidas.
# ---------------------------------------------------------------------------


def test_desempate_por_id_e_deterministico_em_execucoes_repetidas(cenario):
    empresa = cenario["empresa"]
    # Os dois têm o MESMO vigencia_inicio — não faz sentido de negócio
    # legítimo (registrar_regime_tributario nunca produz isso: ele recusa
    # vigencia_inicio <= a do período vigente), mas é exatamente o estado
    # que a auditoria da DL-020 apontou como possível pelo caminho antigo
    # (inline sem desempate) e que dado herdado/importado pode reproduzir.
    # Os dois precisam estar FECHADOS (vigencia_fim preenchido): só um
    # período pode estar aberto por vez (critério 7).
    mais_antigo = HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio=date(2024, 1, 1),
        vigencia_fim=date(2024, 6, 30),
    )
    mais_novo = HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2024, 1, 1),
        vigencia_fim=date(2024, 12, 31),
    )
    assert mais_novo.pk > mais_antigo.pk

    def _ultimo():
        return (
            HistoricoRegimeTributario.objects.filter(empresa=empresa)
            .order_by("-vigencia_inicio", "-id")
            .first()
        )

    resultados = [_ultimo().pk for _ in range(20)]

    # Sempre o MESMO registro — e é o de maior id (o desempate declarado).
    assert set(resultados) == {mais_novo.pk}


# ---------------------------------------------------------------------------
# Critério 8: concorrência em PostgreSQL — duas requisições simultâneas que
# abririam período de regime para a mesma empresa resultam em UM período
# aberto, sem 5xx.
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_duas_requisicoes_simultaneas_abrindo_regime_resultam_em_um_periodo_sem_5xx():
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-023-R Corrida", cnpj="70707070000144"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DL-023-R Corrida Ltda",
        cnpj="33444555000262",
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-dl023r-corrida",
        email="gestor-dl023r-corrida@escritorio.com.br",
        password=SENHA,
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    barreira = threading.Barrier(2)
    resultados = {}

    def _postar(chave):
        try:
            cliente = Client(raise_request_exception=False)
            cliente.login(username="gestor-dl023r-corrida", password=SENHA)
            barreira.wait()
            resposta = cliente.post(
                reverse("empresas:api-regime-tributario", args=[empresa.id]),
                {"regime": "simples_nacional", "vigencia_inicio": "2024-06-01"},
                content_type="application/json",
            )
            resultados[chave] = resposta.status_code
        finally:
            connection.close()

    threads = [threading.Thread(target=_postar, args=(chave,)) for chave in "AB"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Nenhum 5xx: as duas respostas são 201 (criou) ou 400 (recusado com
    # mensagem de negócio) — nunca um erro de servidor cru.
    assert set(resultados.values()) <= {201, 400}, resultados
    assert list(resultados.values()).count(201) == 1, resultados
    assert (
        HistoricoRegimeTributario.objects.filter(empresa=empresa, vigencia_fim__isnull=True).count()
        == 1
    )


# ---------------------------------------------------------------------------
# BL-246 (achado P2 da auditoria DL-023 rodada 1): a etapa introduziu um
# 500 alcançável por cliente — `DELETE` de regime concorrente com `POST`
# reproduzia 500 em 6 de 8 execuções sem sincronização artificial. A
# tradução do `IntegrityError` passou a ser um PONTO ÚNICO
# (`_e_violacao_de_periodo_unico`, apps/empresas/services.py), usado pelos
# DOIS caminhos que podem violar a constraint: `registrar_regime_tributario`
# (já medido acima) e `excluir_ultimo_regime_tributario` (aqui).
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_post_e_delete_de_regime_concorrentes_nunca_dao_5xx():
    """Reproduz o entrelaçamento do achado P2: um DELETE do período ABERTO
    (que reabriria o período ANTERIOR) concorrente com um POST que abre um
    período NOVO. Repetido em várias rodadas — o auditor mediu 6 de 8 sem
    nenhuma sincronização artificial — porque o entrelaçamento depende da
    ordem em que o PostgreSQL libera os locks, e uma única rodada pode não
    pegá-lo."""
    escritorio = Escritorio.objects.create(nome="Escritório DL-023-R BL-246", cnpj="80808080000155")
    usuario = get_user_model().objects.create_user(
        username="gestor-dl023r-bl246",
        email="gestor-dl023r-bl246@escritorio.com.br",
        password=SENHA,
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    status_vistos = set()
    RODADAS = 15
    cnpjs_base = 90000000000100  # avança a cada rodada para CNPJ único

    for rodada in range(RODADAS):
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social=f"Empresa DL-023-R BL-246 {rodada}",
            cnpj=str(cnpjs_base + rodada * 111),
        )
        # Período FECHADO (o "anterior" que a exclusão vai reabrir) e
        # período ABERTO (o "último", alvo do DELETE).
        registrar_regime_tributario(empresa, RegimeTributario.SIMPLES_NACIONAL, date(2024, 1, 1))
        ultimo = registrar_regime_tributario(
            empresa, RegimeTributario.LUCRO_PRESUMIDO, date(2025, 1, 1)
        )

        barreira = threading.Barrier(2)
        resultados = {}

        # `empresa`/`ultimo`/`resultados` como PARÂMETRO PADRÃO — não como
        # variável livre do laço — para cada thread capturar o valor desta
        # ITERAÇÃO, não o da última (B023: closure sobre variável de laço
        # é um bug clássico, mesmo aqui, onde as threads são unidas antes
        # da próxima iteração começar).
        def _deletar(empresa=empresa, ultimo=ultimo, resultados=resultados, barreira=barreira):
            try:
                cliente = Client(raise_request_exception=False)
                cliente.login(username="gestor-dl023r-bl246", password=SENHA)
                barreira.wait()
                resposta = cliente.delete(
                    reverse(
                        "empresas:api-regime-tributario-detalhe",
                        args=[empresa.id, ultimo.pk],
                    )
                )
                resultados["delete"] = resposta.status_code
            finally:
                connection.close()

        def _postar(empresa=empresa, resultados=resultados, barreira=barreira):
            try:
                cliente = Client(raise_request_exception=False)
                cliente.login(username="gestor-dl023r-bl246", password=SENHA)
                barreira.wait()
                resposta = cliente.post(
                    reverse("empresas:api-regime-tributario", args=[empresa.id]),
                    {"regime": "lucro_real", "vigencia_inicio": "2025-06-01"},
                    content_type="application/json",
                )
                resultados["post"] = resposta.status_code
            finally:
                connection.close()

        threads = [threading.Thread(target=_deletar), threading.Thread(target=_postar)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        status_vistos.update(resultados.values())
        # Nenhum 5xx NESTA rodada — a asserção fica DENTRO do laço para que
        # a mensagem de falha aponte a rodada exata, não só o agregado.
        assert set(resultados.values()) <= {200, 201, 400, 409}, (rodada, resultados)
        # Estado final consistente: no máximo 1 período aberto (a
        # constraint de banco é a rede debaixo de tudo, mesmo se a
        # tradução falhasse).
        assert (
            HistoricoRegimeTributario.objects.filter(
                empresa=empresa, vigencia_fim__isnull=True
            ).count()
            <= 1
        )

    # Controle de que o teste testou alguma coisa: pelo menos um 400 (ou
    # 409) apareceu em alguma rodada — senão as duas operações nunca
    # colidiram em rodada nenhuma, e o teste não teria exercitado a defesa.
    assert status_vistos & {400, 409}, status_vistos


# ---------------------------------------------------------------------------
# BL-251 (achado P7 da auditoria DL-023 rodada 1): o desempate
# `(-vigencia_inicio, -id)` precisa valer também pela ROTA DE LISTAGEM, não
# só dentro de `excluir_ultimo_regime_tributario`.
# ---------------------------------------------------------------------------


def test_listagem_desempata_periodos_de_mesmo_inicio_de_forma_deterministica(client, cenario):
    empresa = cenario["empresa"]
    mais_antigo = HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio=date(2024, 1, 1),
        vigencia_fim=date(2024, 6, 30),
    )
    mais_novo = HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2024, 1, 1),
        vigencia_fim=date(2024, 12, 31),
    )
    assert client.login(username="gestor-dl023r", password=SENHA)

    ordens = []
    for _ in range(10):
        resposta = client.get(reverse("empresas:api-regime-tributario", args=[empresa.id]))
        assert resposta.status_code == 200, resposta.status_code
        ordens.append([item["id"] for item in resposta.json()])

    # Sempre a MESMA ordem em execuções repetidas, e o mais novo (maior id)
    # sempre primeiro — mesmo desempate que `excluir_ultimo_regime_
    # tributario` já usava, agora também pela rota de listagem.
    assert all(ordem == [mais_novo.pk, mais_antigo.pk] for ordem in ordens), ordens


def test_meta_ordering_tem_desempate_por_id(cenario):
    """Unidade direta do `Meta`, matavelmente distinta da consulta com
    `order_by()` explícito que `excluir_ultimo_regime_tributario` usa —
    prova que o DESEMPATE mora no lugar que TODOS os caminhos leem."""
    assert HistoricoRegimeTributario._meta.ordering == ["-vigencia_inicio", "-id"]
