"""Bloco de identificação obrigatória por classe de documento.

Esta é a função pura central da **Fatia A** do DL-027 — o mecanismo
de plataforma que vale para todos os módulos (RC-94). Ela recebe uma
classe de documento e o contexto mínimo (empresa, período, profissional
responsável, escritório) e devolve a lista **ordenada e estável** de
campos que aquele tipo de documento precisa mostrar.

A função é **pura** deliberadamente:
  - Não lê do banco. Recebe um objeto leve (`IdentificacaoContexto`)
    montado pela `view`.
  - Não toca em `Decimal`. Recebe a string do nível de arredondamento
    já pronta — a escolha de escala e arredondamento é do motor
    determinístico, conforme o AGENTS.md §10.
  - Não conhece `request`. Não verifica permissão. É função de **forma**,
    não de **operação**.

Os campos devolvidos vêm das **normas citadas**, não de cópia de
concorrente:
  - Classe **Conferência**: HI-12 do `docs/projeto/requisitos.md`.
  - Classe **Demonstração**: RC-95 do `requisitos.md`, NBC TG 26 (R5)
    item 51.
  - Classe **Livro**: RC-96 do `requisitos.md`, NBC ITG 2000 (R1)
    itens 5, 9, 10, 13.

⚠️ **Esta etapa NÃO emite documento de classe LIVRO** até `PE-52` ser
respondida (legislação específica do livro digital). A função
**devolve** o bloco declarado para que a guarda da `views.py` saiba o
que proteger — saber o que o livro carrega é parte da proteção.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apps.documentos.escolhas import ClasseDocumento


@dataclass(frozen=True)
class CampoIdentificacao:
    """Um par `(label, valor)` que vai sair no cabeçalho do documento.

    `label` é a chave humana do que está sendo identificado (ex.:
    `"Razão social"`, `"CNPJ"`, `"NIRE"`). `valor` é o texto já
    formatado para impressão — esta camada **não formata** valor
    nenhum, só recebe pronto (a formatação é da camada que monta o
    contexto: a `view`, em geral).

    O `dataclass(frozen=True)` é parte do contrato: o bloco devolvido
    por `bloco_obrigatorio_para` não pode ser mutado pela camada de
    template. Mutação escondida é o tipo de erro que destrói a
    invariante contábil sem aparecer na conferência.
    """

    label: str
    valor: str


@dataclass(frozen=True)
class BlocoIdentificacao:
    """O conjunto de campos de identificação que um documento DEVE
    mostrar, para uma dada classe.

    `repetir_em_cada_pagina` (NBC TG 26 item 52): quando `True`, o
    template tem que renderizar o bloco em **toda** folha, não só na
    primeira. É parte da função pura porque é regra de norma — não
    é decisão do template.

    `campos` é uma `tuple` (e não `list`) deliberadamente: a ordem
    é parte do contrato visual (teste `test_ordem_dos_campos_e_estavel`
    trava a ordem), e o template depende dela para saber onde cada
    campo vai. `tuple` torna a ordem imutável também do lado de
    quem lê.
    """

    classe: ClasseDocumento
    campos: tuple[CampoIdentificacao, ...]
    repetir_em_cada_pagina: bool = False


@dataclass(frozen=True)
class IdentificacaoContexto:
    """Tudo o que a função pura precisa para montar o bloco.

    É `frozen=True` por dois motivos:
      1. A função pura não muta o que recebe — em parte nenhuma.
      2. A `view` que monta o contexto também não deve mutar
         depois de construído. Se algum lugar precisar do contexto
         modificado, é porque há regra faltando antes da função.

    Os campos são **texto** (não objetos Django, não `Decimal`): a
    regra do projeto é que a camada de forma não conhece a camada de
    dados. Isso simplifica o teste (não precisa de `pytest.mark.django_db`)
    e protege a função de qualquer mudança de modelo — o dia em que
    `Empresa` ganhar um campo novo de CNPJ, a `view` que monta o
    contexto é que muda, não esta função.
    """

    empresa_razao_social: str
    empresa_cnpj: str
    empresa_nire: Optional[str]
    empresa_nivel_arredondamento: str
    periodo_coberto: str
    moeda: str
    data_emissao: str
    relatorio_nome: str
    escritorio_razao_social: str
    escritorio_crc: str
    profissional_nome: str
    profissional_crc: str
    folha_atual: int
    folha_total: int
    # DL-038: `Empresa` passou a admitir cliente pessoa física (CPF), além
    # de CNPJ. `empresa_cnpj` continua sendo o texto do NÚMERO da
    # inscrição (venha ela de CNPJ ou de CPF — quem monta o contexto
    # decide qual valor formatado passar); este campo novo é só o
    # RÓTULO do campo de identificação impresso, para o bloco mostrar
    # "CPF" em vez de "CNPJ" quando for o caso. Tem valor padrão "CNPJ"
    # (o único rótulo que existia antes desta etapa) de propósito: nenhum
    # chamador existente — hoje esta classe não tem nenhum chamador de
    # produção, só `apps/documentos/tests/test_identificacao.py` — precisa
    # mudar para continuar funcionando.
    empresa_rotulo_inscricao: str = "CNPJ"


def _campo_obrigatorio(label: str, valor: str) -> CampoIdentificacao:
    """Atalho para criar um campo do bloco. Existe só para o chamador
    não ter que escrever `CampoIdentificacao(label=..., valor=...)` a
    cada linha — clareza visual do que é obrigatório."""
    return CampoIdentificacao(label=label, valor=valor)


def _marcador_de_vazio(valor: Optional[str]) -> str:
    """Regra do vazio para campo obrigatório.

    O plano DL-027 §critérios-de-aceite 5 diz: *NIRE e nível de
    arredondamento existem no cadastro, com a regra do vazio escrita
    — empresa sem NIRE imprime exatamente o que a regra disser, e a
    regra é do Fred, não minha.*

    A regra que está em código é a mais conservadora: campo
    obrigatório vazio aparece marcado como `(não informado)` em vez
    de ser omitido em silêncio. A razão está em **RC-93** — a
    identificação é obrigação, e omitir o rótulo é a forma errada de
    cumprir "identificação obrigatória". Se o Fred quiser outra
    regra (omitir, ou barra, ou "—"), é uma linha só — `tests/
    test_identificacao.py::TestBlocoIdentificacaoConferencia::
    test_nire_aparece_mesmo_vazio_quando_empresa_nao_tem` trava
    este comportamento para troca ser decisão registrada.
    """
    if valor is None or valor.strip() == "":
        return "(não informado)"
    return valor


def _campos_conferencia(ctx: IdentificacaoContexto) -> tuple[CampoIdentificacao, ...]:
    """Bloco para classe 1 — relatório de conferência/gerencial.

    HI-12 (a confirmar pelo Fred): núcleo de cinco campos do
    RC-93 + data/hora de emissão. O conjunto declarado é o que
    personalização **não pode desligar**; os campos "úteis"
    (escritório, profissional, folha N de M) entram na fatia B
    (preferências), não aqui.
    """
    return (
        _campo_obrigatorio("Razão social", ctx.empresa_razao_social),
        _campo_obrigatorio(ctx.empresa_rotulo_inscricao, ctx.empresa_cnpj),
        _campo_obrigatorio("NIRE", _marcador_de_vazio(ctx.empresa_nire)),
        _campo_obrigatorio("Período", ctx.periodo_coberto),
        _campo_obrigatorio("Relatório", ctx.relatorio_nome),
        _campo_obrigatorio("Data de emissão", ctx.data_emissao),
    )


def _campos_demonstracao(ctx: IdentificacaoContexto) -> tuple[CampoIdentificacao, ...]:
    """Bloco para classe 2 — demonstração contábil.

    NBC TG 26 (R5) item 51, cada alínea vira um campo:
      (a) nome da entidade — já temos em "Razão social".
      (b) se individual ou de grupo — default individual.
      (c) data de encerramento ou período coberto — "Período".
      (d) moeda de apresentação.
      (e) nível de arredondamento usado.

    Item 52 obriga a repetição em cada página — controlado por
    `BlocoIdentificacao.repetir_em_cada_pagina = True`.

    O nível de arredondamento **vem pronto** do contexto (texto). O
    motor determinístico (DE-010) é o que escolhe a política; esta
    camada só imprime.
    """
    return (
        _campo_obrigatorio("Razão social", ctx.empresa_razao_social),
        _campo_obrigatorio(ctx.empresa_rotulo_inscricao, ctx.empresa_cnpj),
        _campo_obrigatorio("NIRE", _marcador_de_vazio(ctx.empresa_nire)),
        _campo_obrigatorio("Período", ctx.periodo_coberto),
        _campo_obrigatorio("Abrangência", "Demonstração individual"),  # item 51(b)
        _campo_obrigatorio("Moeda", ctx.moeda),  # item 51(d)
        _campo_obrigatorio(
            "Nível de arredondamento", ctx.empresa_nivel_arredondamento
        ),  # item 51(e)
        _campo_obrigatorio("Data de emissão", ctx.data_emissao),
        _campo_obrigatorio("Relatório", ctx.relatorio_nome),
    )


def _campos_livro(ctx: IdentificacaoContexto) -> tuple[CampoIdentificacao, ...]:
    """Bloco para classe 3 — livro contábil.

    NBC ITG 2000 (R1):
      - Item 5(a): idioma e moeda nacionais.
      - Item 5(b): forma cronológica (não é campo, é estrutura — a
        cronologia vem do modelo `LancamentoContabil`, não do
        template).
      - Item 5(d): ausência de espaços em branco, entrelinhas,
        borrões, rasuras, emendas — **invariante do template**, não
        campo. A função sinaliza isso por *não devolver* campos de
        espaçamento: o template, ao renderizar, tem que preencher
        com asterisco ou traço (vide observação em RC-96 sobre
        asterisco = ausência de espaço em branco).

    Esta função devolve o bloco declarado mas o sistema **não emite**
    documentos desta classe (PE-52). A existência deste bloco é
    proteção, não entrega.
    """
    return (
        _campo_obrigatorio("Razão social", ctx.empresa_razao_social),
        _campo_obrigatorio(ctx.empresa_rotulo_inscricao, ctx.empresa_cnpj),
        _campo_obrigatorio("NIRE", _marcador_de_vazio(ctx.empresa_nire)),
        _campo_obrigatorio("Idioma", "Português (Brasil)"),  # item 5(a)
        _campo_obrigatorio("Moeda", ctx.moeda),  # item 5(a)
        _campo_obrigatorio("Período", ctx.periodo_coberto),
        _campo_obrigatorio(
            "Profissional responsável",
            f"{ctx.profissional_nome} — {ctx.profissional_crc}",
        ),
        _campo_obrigatorio("Relatório", ctx.relatorio_nome),
    )


def bloco_obrigatorio_para(classe, ctx: IdentificacaoContexto) -> BlocoIdentificacao:
    """Devolve o bloco de identificação obrigatória para `classe`.

    O tipo de `classe` é `ClasseDocumento`. Passar string solta é
    erro de programação — a enum é o vocabulário do produto.
    """
    if not isinstance(classe, ClasseDocumento):
        # Não usar `TypeError` direto: a mensagem precisa nomear o
        # erro e apontar para a enum correta, para a próxima pessoa
        # ver o que se esperava.
        raise ValueError(
            f"classe deve ser apps.documentos.escolhas.ClasseDocumento, "
            f"recebido {type(classe).__name__}: {classe!r}."
        )
    if classe is ClasseDocumento.CONFERENCIA:
        return BlocoIdentificacao(
            classe=classe,
            campos=_campos_conferencia(ctx),
            repetir_em_cada_pagina=False,
        )
    if classe is ClasseDocumento.DEMONSTRACAO:
        return BlocoIdentificacao(
            classe=classe,
            campos=_campos_demonstracao(ctx),
            # Item 52 da NBC TG 26 (R5): repetição em cada página.
            repetir_em_cada_pagina=True,
        )
    if classe is ClasseDocumento.LIVRO:
        return BlocoIdentificacao(
            classe=classe,
            campos=_campos_livro(ctx),
            repetir_em_cada_pagina=False,
        )
    # O `if`/`elif`/retorno cobre os três valores da enum — qualquer
    # adição na `ClasseDocumento` precisa entrar aqui, e este ponto
    # só é alcançado se alguém modificou a enum sem atualizar esta
    # função. `RuntimeError` sinaliza "estado inconsistente" — é
    # defeito de programação, não entrada do usuário.
    raise RuntimeError(
        f"ClasseDocumento tem um valor novo sem tratamento aqui: {classe!r}. "
        "Atualize apps.documentos.identificacao antes de prosseguir."
    )
