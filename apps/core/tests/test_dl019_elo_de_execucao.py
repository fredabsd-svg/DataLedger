"""Controles positivos do elo de execução — BL-171 (achado A5 da auditoria
DL-019 rodada 1).

O mecanismo em si mora em `conftest.py` (ver o docstring de lá para o que ele
fecha e por quê). Este arquivo existe por causa da **ressalva do
`arquiteto-senior`**, que é condição para adotar o desenho:

> Instrumentação `autouse` que embrulha função de produção **falha em
> silêncio** se o embrulho deixar de ser aplicado — e aí o mecanismo passa a
> aprovar tudo, que é o mesmo defeito da varredura sobre lista vazia. O
> próprio embrulho precisa de controle positivo: um teste que prove que o
> registro registra.

São quatro perguntas, e nenhuma delas é respondida pelo mecanismo sobre si
mesmo:

1. **O embrulho foi aplicado?** Em todo módulo de produção que importou a
   política pelo nome — `from ... import ...` copia a referência, e patchear
   só a origem não alcançaria nenhum deles.
2. **O registro registra?** Uma requisição HTTP real a uma superfície
   conhecida tem de fazer o nome dela aparecer no registro.
3. **A conferência sabe reprovar?** Com uma superfície que ninguém
   exercitou, ela tem de nomeá-la.
4. **A conferência chega a rodar?** A regra de "quando conferir" é a parte
   que pode desligar o mecanismo inteiro, e ela é medida com entradas
   sintéticas.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

import conftest
from apps.core.requisicao import recusar_dado_nao_contratado
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio


def test_o_embrulho_esta_aplicado_na_origem():
    """Pergunta 1, primeira metade. Se esta asserção cair, o registro fica
    vazio e a conferência final reprovaria TUDO — alto, não em silêncio —,
    mas é aqui que se lê o motivo em uma linha."""
    assert getattr(recusar_dado_nao_contratado, conftest._ATRIBUTO_DE_INSTRUMENTACAO, False)


def test_o_embrulho_esta_aplicado_em_toda_superficie_que_importou_a_politica():
    """Pergunta 1, segunda metade — e é a que pega o defeito real.

    `apps.contabilidade.views_web`, `apps.empresas.views` e
    `apps.tenancy.views` fazem `from apps.core.requisicao import
    recusar_dado_nao_contratado` no topo do módulo. Essa referência é uma
    CÓPIA: trocar o atributo em `apps.core.requisicao` depois do import não
    alcança nenhuma delas. Um mecanismo que patcheasse só a origem passaria
    neste projeto sem registrar uma única chamada.
    """
    importadores = conftest.modulos_de_producao_que_importaram_a_politica()

    # Controle de que a própria busca enxerga algo: se ela devolver pouco,
    # a asserção seguinte ficaria verdadeira por vácuo.
    assert len(importadores) >= 4, sorted(importadores)

    sem_embrulho = sorted(
        nome
        for nome, alvo in importadores.items()
        if not getattr(alvo, conftest._ATRIBUTO_DE_INSTRUMENTACAO, False)
    )
    assert not sem_embrulho, (
        "Estes módulos de produção têm a política ligada a um nome próprio que "
        f"NÃO passou pelo embrulho do elo de execução: {sem_embrulho}. O "
        "registro não veria nenhuma chamada vinda deles."
    )


@pytest.mark.django_db
def test_o_registro_registra_uma_superficie_exercitada_por_requisicao(client):
    """Pergunta 2, medida por efeito: uma requisição HTTP de verdade a uma
    superfície de escrita conhecida faz o nome dela aparecer no registro.

    `ativar_escritorio` é a superfície que o auditor usou na demonstração
    proposta em A5, e é a mais simples de exercitar de ponta a ponta.
    """
    Usuario = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório do teste", cnpj="11111111000111")
    usuario = Usuario.objects.create_user(
        username="controle-bl171",
        email="controle-bl171@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    client.force_login(usuario)

    superficie = "apps.tenancy.views.ativar_escritorio"
    conftest.CHAMADORES_DA_POLITICA.discard(superficie)

    resposta = client.post(reverse("tenancy:ativar"), {"escritorio_id": escritorio.id})

    assert resposta.status_code == 302
    assert superficie in conftest.CHAMADORES_DA_POLITICA, (
        "A requisição passou pela superfície e o registro não a viu. O embrulho "
        "da política não está alcançando esta superfície — e sem isso a "
        "conferência final aprova por vácuo."
    )


def test_a_conferencia_sabe_reprovar_nomeando_a_superficie_que_ninguem_exercitou():
    """Pergunta 3, no molde da BL-150: o mutante é "o registro está vazio".

    Com o conjunto de chamadores VAZIO, toda superfície da varredura tem de
    ser reportada, e o relatório tem de conter a superfície pelo nome — que é
    a exigência do auditor ("nomeando a que faltar"). Não mexe em registro
    nenhum: a função recebe os chamadores por parâmetro exatamente para isto.
    """
    faltando = conftest.superficies_nao_exercitadas(set())

    assert "apps.tenancy.views.ativar_escritorio.post" in faltando
    assert "apps.contabilidade.views_web.lancamento_novo.post" in faltando
    assert len(faltando) >= 14, sorted(faltando)


def test_a_conferencia_aprova_quando_o_registro_cobre_a_superficie():
    """Par do teste acima: sem ele, uma conferência que reprovasse SEMPRE
    também passaria na metade de cima. Controle positivo e controle negativo
    do mesmo mecanismo, a lição da BL-150."""
    from apps.core.tests.test_dl019_varredura_de_contratos import (
        _alvos_alcancaveis,
        superficies_de_escrita,
    )

    superficies, _ = superficies_de_escrita(_alvos_alcancaveis())
    # Todo caminho, sem o método no fim: é a forma em que uma view de função
    # aparece na pilha.
    chamadores = {nome.rsplit(".", 1)[0] for nome in superficies}

    assert conftest.superficies_nao_exercitadas(chamadores) == {}


@pytest.mark.parametrize(
    ("argumentos", "palavra_chave", "marca", "esperado"),
    [
        # `pytest` puro, que é o que a integração contínua executa.
        (["/repo"], "", "", True),
        ([], "", "", True),
        # Execução parcial, por caminho, por -k ou por -m.
        (["/repo/apps/core"], "", "", False),
        (["/repo"], "varredura", "", False),
        (["/repo"], "", "slow", False),
        # Opções não contam como seleção de alvo.
        (["-q", "-rs", "/repo"], "", "", True),
    ],
)
def test_a_regra_de_quando_conferir_e_a_que_esta_escrita(
    argumentos, palavra_chave, marca, esperado
):
    """Pergunta 4. Esta regra é a única parte do mecanismo capaz de desligá-lo
    por inteiro, e um mecanismo desligado que ninguém percebe é indistinguível
    de um mecanismo que aprova.

    Por isso ela é função pura, medida aqui com entradas sintéticas, e por
    isso o `conftest.py` ANUNCIA em toda sessão o que decidiu fazer — inclusive
    quando decide não conferir.
    """
    assert (
        conftest.conferencia_de_execucao_se_aplica(argumentos, palavra_chave, marca, "/repo")
        is esperado
    )
