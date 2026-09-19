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
REQUISITOS = RAIZ / "docs" / "projeto" / "requisitos.md"


def _texto(caminho):
    return caminho.read_text(encoding="utf-8")


def _identificadores_de_requisito_duplicados(texto):
    """Retorna só IDs definidos em linhas de tabela mais de uma vez.

    BL-242: citações a um requisito dentro da explicação são legítimas; o que
    torna o contrato ambíguo é haver duas linhas que definem o mesmo RC ou PE.
    Por isso a expressão ancora no começo da linha e no primeiro campo da
    tabela, em vez de contar todas as ocorrências no documento.
    """
    definidos = re.findall(r"^\|\s*((?:RC|PE)-\d+)\s*\|", texto, flags=re.MULTILINE)
    return sorted(
        {identificador for identificador in definidos if definidos.count(identificador) > 1}
    )


def test_requisitos_e_pendencias_tem_identificadores_unicos():
    """Um RC/PE nunca pode voltar a nomear dois contratos diferentes."""
    duplicados = _identificadores_de_requisito_duplicados(_texto(REQUISITOS))
    assert not duplicados, (
        "Identificadores definidos mais de uma vez em docs/projeto/requisitos.md: "
        f"{', '.join(duplicados)}. Renumere a definição mais nova e atualize "
        "suas referências sem reescrever auditorias históricas (BL-242)."
    )


def test_guarda_de_ids_distingue_definicao_de_citacao():
    """Prova a classe: duas definições colidem; citações no texto não."""
    exemplo = """\
| RC-01 | Primeira definição |
| RC-02 | Cita RC-01 sem redefini-lo |
| RC-01 | Segunda definição conflitante |
| PE-01 | Pergunta que cita RC-01 |
"""
    assert _identificadores_de_requisito_duplicados(exemplo) == ["RC-01"]


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


# ---------------------------------------------------------------------------
# BL-315 (achado B1 da rodada 3 da auditoria da DL-026)
#
# A instrução permanente do Fred, de 2026-09-13, tratou a duplicação ENTRE
# arquivos: o mesmo fato em quatro lugares do README, já divergido. Os testes
# acima nasceram disso. O auditor achou a mesma doença numa forma que eles não
# alcançavam — duplicação DENTRO de um arquivo só:
#
#   - o cabeçalho afirmava `main` em `8235635`; ela estava em `bfe9814`,
#     mesclada 22 minutos depois PELO PR QUE INTEGROU ESTE ARQUIVO. Quando fui
#     corrigir, já estava em `b588af9`. A afirmação nasceu falsa e envelhecia
#     sozinha;
#   - a tabela de etapas descrevia a DL-026 como "rodada 1 REPROVADA" enquanto
#     o "Próximo passo", no mesmo documento, registrava a rodada 4.
#
# Os dois guardas abaixo são contra a CAUSA, não contra as duas ocorrências:
# estado volátil só pode morar em um lugar, e revisão de branch se lê do Git.
# ---------------------------------------------------------------------------


# Os seis estados do AGENTS.md §3. Lista fechada de propósito: é o vocabulário
# que o projeto já decidiu, não uma invenção deste teste.
ESTADOS_CANONICOS = (
    "planejada",
    "em desenvolvimento",
    "em validação",
    "bloqueada",
    "em revisão",
    "integrada",
)
APONTADOR_PARA_O_PROXIMO_PASSO = "Próximo passo"


def _cabecalho(texto):
    """O bloco antes da primeira seção `## ` — onde o defeito morava."""
    return texto.split("\n## ", 1)[0]


def _sem_citacoes(texto):
    """Remove linhas de citação (`> `).

    A distinção é a mesma que `_identificadores_de_requisito_duplicados` já faz
    entre definir e citar: narrar um erro passado ("dizia X, estava em Y") é
    legítimo e fica em bloco de citação; afirmar em texto corrido é declarar
    estado.
    """
    return "\n".join(linha for linha in texto.split("\n") if not linha.lstrip().startswith(">"))


# BL-324: a versão anterior casava DUAS PREPOSIÇÕES ("em", "está em") e só o
# cabeçalho — isto é, a FRASE do relatório que a originou. O auditor mediu:
# com `"(hoje no commit \`8235635\`)"` o defeito voltava com 10 passed.
#
# A regra verdadeira não fala de preposição: **revisão de branch não se
# escreve aqui**, em nenhuma redação, porque ela muda a cada merge — inclusive
# pelo merge deste documento. Então: qualquer hash entre crases no mesmo
# PERÍODO que a palavra `main`, em texto corrido, no arquivo inteiro.
PADRAO_REVISAO_DA_MAIN = re.compile(
    r"`main`[^.\n]{0,80}`[0-9a-f]{7,40}`|`[0-9a-f]{7,40}`[^.\n]{0,80}`main`"
)


def test_cabecalho_do_estado_nao_fixa_a_revisao_da_main():
    """SHA da `main` não se escreve aqui: ele muda a cada merge, inclusive pelo
    merge deste próprio documento, e envelhece antes de ser lido.

    Quem precisa da revisão lê da fonte que não diverge: `git rev-parse
    origin/main`.
    """
    afirmacoes = PADRAO_REVISAO_DA_MAIN.findall(_sem_citacoes(_cabecalho(_texto(ESTADO))))
    assert not afirmacoes, (
        "O cabeçalho de docs/agents/estado.md voltou a fixar a revisão da "
        f"`main`: {afirmacoes}. Ela muda a cada merge — inclusive pelo merge "
        "deste arquivo, que foi como a afirmação anterior nasceu falsa (B1 da "
        "rodada 3 da DL-026). Quem precisa dela usa `git rev-parse origin/main`. "
        "Narrar o erro passado é permitido, em bloco de citação."
    )


def test_tabela_de_etapas_nao_descreve_estado_de_etapa_em_andamento():
    """A tabela de etapas diz O QUE cada etapa é; em que pé ela está vive no
    "Próximo passo", e só lá.

    Sem isto, as duas descrições divergem no dia em que alguém atualiza uma —
    que foi exatamente o que aconteceu com a DL-026 entre a rodada 1 e a 4.
    """
    # BL-324: a versão anterior procurava a string "Em desenvolvimento" — a
    # FRASE do relatório. Qualquer outra redação ("Em validação — rodada 2
    # REPROVADA") passava, e havia um caso vivo no arquivo.
    #
    # A regra verdadeira: a célula de estado de uma etapa OU diz um dos estados
    # canônicos do AGENTS.md §3, e nada mais, OU aponta para o "Próximo passo".
    # Narrar rodada, parecer e pendência ali é descrever estado em segundo
    # lugar — que é a duplicação que a instrução permanente de 2026-09-13
    # proíbe.
    texto = _texto(ESTADO)
    # As etapas que o "Próximo passo" descreve — e que, por isso, NÃO podem
    # ser descritas também na tabela. Para uma etapa concluída não há segundo
    # lugar, e prosa na célula é legítima.
    # "Em curso" é a etapa que o bloco **AGORA** nomeia — não toda etapa que
    # o "Próximo passo" cita de passagem ao contar o histórico. Narrar uma
    # etapa antiga ali é legítimo; o que não pode é a MESMA etapa ser descrita
    # nos dois lugares.
    proximo_passo = texto.split("## Próximo passo", 1)[-1]
    bloco_agora = re.search(r"\*\*AGORA.*?(?=\n\*\*|\n---|\Z)", proximo_passo, re.S)
    em_curso = set(re.findall(r"\bDL-\d{3}\b", bloco_agora.group(0) if bloco_agora else ""))

    ofensoras = []
    for linha in texto.split("\n"):
        if not linha.startswith("| [DL-"):
            continue
        etapa = re.match(r"\| \[(DL-\d{3})\]", linha)
        if not etapa or etapa.group(1) not in em_curso:
            continue
        celula = linha.split(" | ")[-1].strip("| ").strip()
        if APONTADOR_PARA_O_PROXIMO_PASSO in celula:
            continue
        # Estado canônico SOZINHO — não como prefixo. "Em validação — rodada
        # 2 REPROVADA, com BL-274/275/276 abertos" começa com um estado
        # canônico e mesmo assim descreve estado em segundo lugar: foi essa
        # redação que o auditor usou para provar que a guarda anterior casava
        # a frase do relatório, não a regra.
        sem_marcacao = re.sub(r"[*_`\[\]]", "", celula).strip().lower().rstrip(".")
        if sem_marcacao in ESTADOS_CANONICOS:
            continue
        ofensoras.append(etapa.group(1))
    assert not ofensoras, (
        "Linhas da tabela de etapas descrevendo estado em andamento: "
        f"{ofensoras}. O estado de uma etapa muda a cada rodada e mora só no "
        '"Próximo passo" — descrevê-lo aqui também é a duplicação que a '
        "instrução permanente de 2026-09-13 proíbe, dentro de um arquivo só. "
        "A linha da tabela deve APONTAR para o Próximo passo."
    )


# ---------------------------------------------------------------------------
# BL-326 — identificador de DECISÃO único.
#
# O registro de requisitos já tinha esta guarda (BL-242). O de decisões, não —
# e na junção da DL-026 com a `main` apareceu o resultado: as duas linhas de
# trabalho criaram, cada uma, uma **DE-042** diferente (primeiro acesso via
# produto, de um lado; identidade visual, do outro). Nenhum dos dois lados
# errou: cada um pegou o próximo número livre **que via**.
#
# É a razão pela qual numeração de documento fiscal não é controlada por cada
# emissor isoladamente: a unicidade não é propriedade de nenhuma das partes,
# é do conjunto. O Git não acusa, porque a colisão é semântica, não textual.
# ---------------------------------------------------------------------------

DECISOES = RAIZ / "docs" / "projeto" / "decisoes.md"


def _decisoes_definidas_mais_de_uma_vez(texto):
    """Só títulos de seção definem uma decisão; citações no corpo não.

    Mesma distinção de `_identificadores_de_requisito_duplicados`: o que torna
    o registro ambíguo é haver duas DEFINIÇÕES do mesmo identificador.
    """
    definidas = re.findall(r"^##\s+(DE-\d+)\b", texto, flags=re.MULTILINE)
    return sorted({d for d in definidas if definidas.count(d) > 1})


def test_decisoes_tem_identificadores_unicos():
    """Uma DE nunca pode nomear duas decisões diferentes."""
    duplicadas = _decisoes_definidas_mais_de_uma_vez(_texto(DECISOES))
    assert not duplicadas, (
        "Decisões definidas mais de uma vez em docs/projeto/decisoes.md: "
        f"{', '.join(duplicadas)}. Renumere a definição mais nova e atualize "
        "suas referências **sem reescrever auditorias históricas** (BL-242, "
        "aplicado à DE-042 na junção com a main em 2026-09-19)."
    )


def test_guarda_de_decisoes_distingue_definicao_de_citacao():
    """Prova a classe: dois títulos colidem; citação no corpo não."""
    exemplo = """\
## DE-001 — Primeira decisão

Texto que cita DE-001 e DE-002 sem redefinir nenhuma.

## DE-002 — Outra decisão

## DE-001 — Definição conflitante, criada por outra frente
"""
    assert _decisoes_definidas_mais_de_uma_vez(exemplo) == ["DE-001"]
