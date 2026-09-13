"""Impede que a documentação de estado volte a divergir da realidade.

Motivo destes testes, registrado porque a intenção importa mais que o código:
em 2026-09-13 o Fred encontrou o README afirmando, no topo, que existia
apenas "um esqueleto executável mínimo, sem nenhum módulo de negócio",
enquanto o mesmo arquivo, mais abaixo, documentava a contabilidade
funcionando. A afirmação obsoleta estava em quatro lugares diferentes.

A causa não foi distração: foi **duplicação**. O estado do projeto vivia
espalhado pelo README, e texto duplicado diverge assim que alguém atualiza um
lugar e esquece os outros. Quem lê um README que se contradiz não sabe em qual
metade acreditar — e isso vale tanto para uma pessoa nova quanto para um agente
de IA que use o arquivo como contexto.

A correção principal foi estrutural: o estado passou a morar em
``docs/agents/estado.md``, e o README aponta para lá. Estes testes são a rede
de proteção, para que a próxima etapa não reintroduza a divergência em
silêncio. Eles não verificam se o texto está *bem escrito* — verificam se ele
está **completo** e se não afirma o que o repositório desmente.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
README = RAIZ / "README.md"
ESTADO = RAIZ / "docs" / "agents" / "estado.md"
PLANOS = RAIZ / "docs" / "planos"


def _texto(caminho):
    return caminho.read_text(encoding="utf-8")


def test_todo_plano_de_etapa_aparece_no_readme():
    """Etapa nova sem menção no README faz a verificação falhar.

    É o caso concreto que originou estes testes: etapas foram sendo
    entregues e o README ficou parado na DL-006. Só o identificador é
    exigido (``DL-007``, por exemplo), não uma frase específica — a
    verificação garante que ninguém *esqueceu* da etapa, e não dita como
    ela deve ser descrita.
    """
    identificadores = sorted(
        {
            correspondencia.group(0)
            for arquivo in PLANOS.glob("DL-*.md")
            if (correspondencia := re.match(r"DL-\d+", arquivo.name))
        }
    )
    assert identificadores, "nenhum plano encontrado em docs/planos/ — caminho errado?"

    readme = _texto(README)
    ausentes = [dl for dl in identificadores if dl not in readme]
    assert not ausentes, (
        "Etapas com plano em docs/planos/ que o README não menciona: "
        f"{', '.join(ausentes)}. Atualize a seção 'Estado atual e continuidade'."
    )


def test_estado_dos_agentes_cita_todas_as_etapas_do_readme():
    """A fonte única do estado não pode estar atrás do README.

    ``docs/agents/estado.md`` é para onde o README manda quem retoma o
    projeto. Se ele não conhecer uma etapa que o README cita, o ponteiro
    leva a um documento incompleto — pior que não ter ponteiro.
    """
    identificadores = sorted(
        {
            correspondencia.group(0)
            for arquivo in PLANOS.glob("DL-*.md")
            if (correspondencia := re.match(r"DL-\d+", arquivo.name))
        }
    )
    estado = _texto(ESTADO)
    ausentes = [dl for dl in identificadores if dl not in estado]
    assert not ausentes, (
        "Etapas ausentes em docs/agents/estado.md: "
        f"{', '.join(ausentes)}. É a fonte única do estado; mantenha-a completa."
    )


def test_readme_aponta_para_a_fonte_unica_do_estado():
    """Se o ponteiro sumir, a duplicação volta.

    Este teste existe para proteger a *correção estrutural*, não o texto:
    sem o ponteiro, nada impede alguém de reescrever o estado inteiro
    dentro do README e recriar o problema de 2026-09-13.
    """
    assert "docs/agents/estado.md" in _texto(README), (
        "O README precisa apontar para docs/agents/estado.md como fonte única "
        "do estado do projeto. Sem esse ponteiro, o estado volta a ser "
        "duplicado e a divergir."
    )


@pytest.mark.parametrize(
    ("afirmacao", "por_que_e_falsa"),
    [
        (
            "sem nenhum módulo de negócio",
            "apps/contabilidade/ implementa plano de contas e partidas dobradas",
        ),
        (
            "Ainda não há módulo de negócio implementado",
            "apps/contabilidade/ e apps/empresas/ existem e estão integrados",
        ),
        (
            "esqueleto executável mínimo",
            "a fundação foi entregue e auditada; não é mais um esqueleto",
        ),
    ],
)
def test_readme_nao_repete_afirmacoes_ja_desmentidas(afirmacao, por_que_e_falsa):
    """Afirmações que já foram falsas uma vez não podem voltar.

    Lista deliberadamente pequena e específica: cada item é uma frase que
    **esteve** no README descrevendo um estado que o repositório já tinha
    superado. Não é uma tentativa de validar prosa em geral — é memória de
    defeito, no mesmo espírito de um teste de regressão.

    A ocorrência dentro da nota histórica do README (que *explica* o
    episódio) usa outra redação de propósito, para não disparar aqui.
    """
    readme = _texto(README)
    ocorrencias = readme.count(afirmacao)
    assert ocorrencias == 0, (
        f"O README voltou a afirmar {afirmacao!r}, o que é falso: {por_que_e_falsa}. "
        "Se a frase for necessária para contar o histórico, reescreva-a."
    )
