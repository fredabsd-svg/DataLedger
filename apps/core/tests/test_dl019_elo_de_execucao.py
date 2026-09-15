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
    # O nome EFETIVO de cada superfície: `modulo.Classe.atributo` para classe,
    # `modulo.funcao` para view de função. É a forma em que a superfície
    # aparece na pilha depois da BL-179/B6 — a classe da instância, não o
    # qualname do código, que pode ser de um mixin compartilhado.
    chamadores = {superficie.nome_efetivo for superficie in superficies.values()}

    assert conftest.superficies_nao_exercitadas(chamadores) == {}


# ---------------------------------------------------------------------------
# BL-179 (achado B6): o registro distingue quem compartilha handler
# ---------------------------------------------------------------------------

# Construído por `exec` com um `__globals__` próprio porque o que está sob
# medição é o QUADRO DA PILHA, e o quadro herda o `__name__` do módulo em que a
# função foi definida. Definidas aqui, estas classes teriam `__name__` de
# módulo de teste e o registro as descartaria — o teste mediria o descarte, não
# o mecanismo. Com o espaço de nomes fictício, o quadro é indistinguível de um
# quadro de produção, que é o caso que interessa.
_FONTE_DO_MODULO_FICTICIO = """
class MixinDeImportacao:
    def post(self, request):
        return espiar()


class ImportarXmlView(MixinDeImportacao):
    pass


class ImportarSpedView(MixinDeImportacao):
    pass
"""


def _espiar_o_quadro_do_chamador():
    """Devolve os nomes com que o quadro de quem chamou entraria no registro —
    é o mesmo `_nomes_registraveis_do_quadro` que a política instrumentada usa,
    lido do mesmo lugar (`sys._getframe(1)`)."""
    import sys

    return conftest._nomes_registraveis_do_quadro(sys._getframe(1))


def _modulo_ficticio_de_producao():
    espaco = {"__name__": "apps.ficticio.views", "espiar": _espiar_o_quadro_do_chamador}
    exec(compile(_FONTE_DO_MODULO_FICTICIO, "<apps.ficticio.views>", "exec"), espaco)
    return espaco


def test_o_registro_nomeia_a_classe_da_instancia_e_nao_so_a_do_mixin():
    """B6: duas superfícies que compartilham o handler de um mixin
    compartilhavam o único nome que o registro guardava, e exercitar uma
    marcava a outra como exercitada.

    Não havia instância viva (os 14 handlers de hoje não se repetem), e é
    desenho provável para a DL-010 — duas rotas de importação com o mesmo
    `post`. Agora o quadro registra também o nome EFETIVO, lido de
    `self.__class__`, e os dois são distintos.
    """
    ficticio = _modulo_ficticio_de_producao()

    nomes_do_xml = ficticio["ImportarXmlView"]().post(None)
    nomes_do_sped = ficticio["ImportarSpedView"]().post(None)

    # O nome do CÓDIGO é o mesmo nos dois: é ele que produzia o falso positivo.
    assert "apps.ficticio.views.MixinDeImportacao.post" in nomes_do_xml
    assert "apps.ficticio.views.MixinDeImportacao.post" in nomes_do_sped

    # O nome EFETIVO distingue, e é o único que a conferência aceita: exercitar
    # a rota do XML não pode marcar a do SPED.
    assert "apps.ficticio.views.ImportarXmlView.post" in nomes_do_xml
    assert "apps.ficticio.views.ImportarSpedView.post" not in nomes_do_xml
    assert "apps.ficticio.views.ImportarSpedView.post" in nomes_do_sped
    assert "apps.ficticio.views.ImportarXmlView.post" not in nomes_do_sped


def test_o_registro_ignora_quadro_de_modulo_de_teste():
    """Par do teste acima, e a fronteira do BL-181/B7: um quadro de código de
    teste não entra no registro — senão a conferência ficaria satisfeita por
    alguém ter chamado a política dentro de um teste unitário dela."""
    import sys

    assert conftest._nomes_registraveis_do_quadro(sys._getframe(0)) == ()
    assert conftest.e_codigo_de_teste("apps.foo.tests") is True
    assert conftest.e_codigo_de_teste("apps.foo.tests.test_bar") is True
    assert conftest.e_codigo_de_teste("apps.foo.test_bar") is True
    assert conftest.e_codigo_de_teste("apps.foo.views") is False


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
