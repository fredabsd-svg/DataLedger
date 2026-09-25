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

  - Classe **Conferência**: HI-12 do `docs/projeto/requisitos.md`. Nenhuma
    norma contábil fixa o cabeçalho; o que vai é o que o escritório
    pedir. A proposta da HI-12 está marcada como hipótese até o Fred
    confirmar, mas **precisa** ser declarável em código — e o teste
    abaixo travar o conjunto declarado.

  - Classe **Demonstração**: RC-95 do `requisitos.md`, NBC TG 26 (R5)
    item 51 — nome da entidade, alteração desde período anterior,
    individual/grupo, data/período, moeda, nível de arredondamento.
    O item 52 obriga a repetir "em cada página".

  - Classe **Livro**: RC-96 do `requisitos.md`, NBC ITG 2000 (R1)
    itens 5, 9, 10, 13. Esta função **não emite** livro contábil —
    PE-52 ainda não foi respondida —, mas devolve o bloco declarado
    para que a guarda da `views.py` saiba o que PROTEGER.
"""

from __future__ import annotations

import pytest

from apps.documentos.escolhas import ClasseDocumento
from apps.documentos.identificacao import (
    BlocoIdentificacao,
    CampoIdentificacao,
    IdentificacaoContexto,
    bloco_obrigatorio_para,
)


@pytest.fixture
def ctx_minimo():
    """Contexto com o mínimo para a função não levantar.

    Os testes individuais sobreescrevem o que precisam variar; o
    fixture existe só para não repetir a montagem em cada teste.
    """
    return IdentificacaoContexto(
        empresa_razao_social="Padaria Exemplo Ltda.",
        empresa_cnpj="11444777000161",
        empresa_nire=None,
        empresa_nivel_arredondamento="2 casas decimais",
        periodo_coberto="novembro de 2026",
        moeda="BRL",
        data_emissao="19/09/2026 14:32",
        relatorio_nome="Balancete de verificação",
        escritorio_razao_social="Escritório Contábil Modelo S/S",
        escritorio_crc="CRC SP 12345/O-0",
        profissional_nome="Maria da Silva",
        profissional_crc="CRC SP 98765/O-1",
        folha_atual=1,
        folha_total=3,
    )


class TestBlocoIdentificacaoConferencia:
    """Classe 1 — relatório de conferência/gerencial.

    Nenhuma norma fixa o cabeçalho; o que sai é o declarado em HI-12.
    A função pode ser **ampla** aqui, segundo o catálogo de
    personalização (RC-94), mas o **núcleo** destes cinco campos sai
    sempre, mesmo em personalização máxima, porque são os que
    identificam o documento:

      - Razão social da empresa
      - CNPJ
      - NIRE (se informado)
      - Período coberto
      - Nome do relatório

    Os campos "úteis" do produto (data/hora de emissão, escritório,
    profissional, folha N de M) **não** são obrigatórios por norma,
    mas o produto os emite sempre que a personalização não desligar —
    e a decisão do que desligar é da fatia B (preferências), não
    desta.
    """

    def test_bloco_classe_conferencia_traz_os_cinco_campos_obrigatorios(self, ctx_minimo):
        bloco = bloco_obrigatorio_para(ClasseDocumento.CONFERENCIA, ctx_minimo)
        labels = [campo.label for campo in bloco.campos]
        # O núcleo obrigatório:
        assert "Razão social" in labels
        assert "CNPJ" in labels
        assert "NIRE" in labels
        assert "Período" in labels
        assert "Relatório" in labels

    def test_nire_aparece_mesmo_vazio_quando_empresa_nao_tem(self, ctx_minimo):
        """Empresa sem NIRE ainda assim mostra o rótulo `NIRE` marcado
        como `(não informado)` — omitir silenciosamente é a forma
        errada de tratar campo obrigatório (RC-93: a identificação
        é obrigação, não personalização).

        Esta é a **regra do vazio** declarada pelo plano: campo
        obrigatório que aparece vazio tem marcador visível.
        """
        assert ctx_minimo.empresa_nire is None
        bloco = bloco_obrigatorio_para(ClasseDocumento.CONFERENCIA, ctx_minimo)
        campo_nire = next(c for c in bloco.campos if c.label == "NIRE")
        assert "(não informado)" in campo_nire.valor

    def test_nire_preenchido_aparece_sem_marcador(self, ctx_minimo):
        """`dataclasses.replace()` é a forma idiomática de criar
        uma cópia com um campo diferente, em `dataclass(frozen=True)`.
        `_replace` é de `NamedTuple` e não existe aqui."""
        from dataclasses import replace

        ctx = replace(ctx_minimo, empresa_nire="35200000000")
        bloco = bloco_obrigatorio_para(ClasseDocumento.CONFERENCIA, ctx)
        campo_nire = next(c for c in bloco.campos if c.label == "NIRE")
        assert campo_nire.valor == "35200000000"
        assert "não informado" not in campo_nire.valor

    def test_ordem_dos_campos_e_estavel(self, ctx_minimo):
        """A ordem é parte do contrato — o template depende dela para
        saber onde cada campo vai. Mudar a ordem é mudança de
        contrato visual."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.CONFERENCIA, ctx_minimo)
        labels = [campo.label for campo in bloco.campos]
        assert labels[0] == "Razão social"
        assert labels[1] == "CNPJ"
        assert labels[2] == "NIRE"
        assert labels[3] == "Período"
        assert labels[4] == "Relatório"

    def test_data_e_hora_de_emissao_e_incluida(self, ctx_minimo):
        """Data/hora de emissão entra no bloco de identificação por
        dois motivos: (a) dois balancetes do mesmo período podem
        divergir se houve lançamento entre as emissões, e sem
        carimbo não se sabe qual é qual; (b) é o que a direção de
        arte chama de "momento da verdade" do documento."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.CONFERENCIA, ctx_minimo)
        labels = [campo.label for campo in bloco.campos]
        assert any("emissão" in label.lower() or "emissao" in label.lower() for label in labels)


class TestBlocoIdentificacaoDemonstracao:
    """Classe 2 — demonstração contábil (Balanço, DRE, DMPL, DFC, notas).

    NBC TG 26 (R5) item 51 é **norma**, não hipótese. A função não
    decide se esses campos vão ou não — eles vão, e a personalização
    não pode retirá-los.
    """

    def test_bloco_classe_demonstracao_traz_nome_da_entidade_individual_e_periodo(self, ctx_minimo):
        """Item 51(a) — nome da entidade. Item 51(c) — data de
        encerramento ou período coberto. Item 51(b) — se é
        individual ou de grupo (default: individual, por ser o caso
        comum no DataLedger hoje)."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.DEMONSTRACAO, ctx_minimo)
        labels = [campo.label for campo in bloco.campos]
        assert "Razão social" in labels
        assert "Período" in labels
        # Item 51(b): individual ou de grupo.
        assert any(
            "individual" in label.lower() or "abrangência" in label.lower() for label in labels
        )

    def test_bloco_classe_demonstracao_traz_moeda_e_nivel_de_arredondamento(self, ctx_minimo):
        """Item 51(d) — moeda de apresentação. Item 51(e) — nível de
        arredondamento usado. Ambos DEVEM ser explícitos: relatório
        que não diz a moeda ou o arredondamento não é reproduzível,
        e o projeto exige conciliação com os lançamentos de origem
        (RC-19)."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.DEMONSTRACAO, ctx_minimo)
        labels = [campo.label for campo in bloco.campos]
        assert "Moeda" in labels
        assert any("arredondamento" in label.lower() for label in labels)

    def test_nivel_de_arredondamento_aparece_como_texto_do_motor(self, ctx_minimo):
        """O texto do nível vem do motor determinístico (escala e
        arredondamento explícitos, conforme DE-010) — o template só
        imprime. O teste prova que o valor passado pelo contexto é
        o que sai, sem reformatação."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.DEMONSTRACAO, ctx_minimo)
        campo = next(c for c in bloco.campos if "arredondamento" in c.label.lower())
        assert campo.valor == "2 casas decimais"

    def test_demonstracao_repeticao_em_cada_pagina_e_marcada_no_bloco(self, ctx_minimo):
        """Item 52 da NBC TG 26 exige que o bloco saia "em cada
        página". A função sinaliza isso no próprio bloco para que o
        template saiba renderizar em todos os cabeçalhos, não só no
        primeiro. A repetição não é só no template — é também
        decisão do motor."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.DEMONSTRACAO, ctx_minimo)
        assert bloco.repetir_em_cada_pagina is True

    def test_demonstracao_nao_pode_receber_classe_errada(self, ctx_minimo):
        """A função é por classe — passar LIVRO aqui é erro de
        programação (a fronteira LIVRO é da fatia A mas a emissão é
        proibida por PE-52). Qualquer troca silenciosa entre classes
        é exatamente o tipo de erro que a auditoria mediu na DL-026."""
        with pytest.raises(ValueError):
            bloco_obrigatorio_para("demonstracao", ctx_minimo)  # type: ignore[arg-type]


class TestBlocoIdentificacaoLivro:
    """Classe 3 — livro contábil (Diário/Razão na forma de livro).

    NBC ITG 2000 (R1). Esta função DEVOLVE o bloco declarado para que
    a guarda saiba o que proteger, mas o sistema **não emite**
    documentos desta classe até `PE-52` ser respondida — ver o
    comentário no topo do arquivo.
    """

    def test_bloco_classe_livro_existe_mas_nao_e_emitido(self, ctx_minimo):
        """A enum LIVRO existe agora para poder ser **proibida** —
        `views.py` recusa personalização em documento declarado como
        livro. Saber o que o livro carrega é parte dessa proteção."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.LIVRO, ctx_minimo)
        assert bloco is not None
        assert isinstance(bloco, BlocoIdentificacao)

    def test_bloco_livro_traz_idioma_e_moeda_nacionais(self, ctx_minimo):
        """Item 5(a) da ITG 2000: escrituração em **idioma e moeda
        nacionais**. O idioma é fixo (português brasileiro) por
        construção do sistema; a moeda vem do contexto."""
        bloco = bloco_obrigatorio_para(ClasseDocumento.LIVRO, ctx_minimo)
        labels = [campo.label for campo in bloco.campos]
        assert "Idioma" in labels
        assert "Moeda" in labels

    def test_bloco_livro_e_imutavel(self, ctx_minimo):
        """Item 5(d) da ITG 2000: 'com ausência de espaços em branco,
        entrelinhas, borrões, rasuras ou emendas'. O sistema impõe
        isso declarando o bloco `read-only` na fronteira — qualquer
        tentativa de mutar o bloco levantado é erro de programação.

        `campos` é `tuple`: `tuple.append` não existe, então a
        exceção é `AttributeError`. O teste é específico
        (`B017` proíbe `pytest.raises(Exception)` cego) porque a
        guarda precisa de **um** motivo para falhar, não de qualquer
        um — silencia o sinal quando se generaliza.
        """
        bloco = bloco_obrigatorio_para(ClasseDocumento.LIVRO, ctx_minimo)
        with pytest.raises(AttributeError):
            bloco.campos.append(  # type: ignore[attr-defined]
                CampoIdentificacao(label="x", valor="y")
            )


class TestIdentificacaoContexto:
    """`IdentificacaoContexto` é o objeto leve que a view monta e
    passa para a função pura. Validar aqui é garantir que o
    compartilhamento de dados com a função não vaza regra de negócio
    (o contexto carrega **texto**, não objetos Django)."""

    def test_contexto_e_imutavel(self):
        """Contexto é `dataclass(frozen=True)`: a função pura não
        deve mutar o que recebe, e a `view` também não — se algum
        lugar precisar do contexto modificado, é porque há regra
        faltando antes da função."""
        from dataclasses import FrozenInstanceError

        ctx = IdentificacaoContexto(
            empresa_razao_social="x",
            empresa_cnpj="y",
            empresa_nire=None,
            empresa_nivel_arredondamento="z",
            periodo_coberto="w",
            moeda="BRL",
            data_emissao="01/01/2026",
            relatorio_nome="Balancete",
            escritorio_razao_social="e",
            escritorio_crc="c",
            profissional_nome="p",
            profissional_crc="pc",
            folha_atual=1,
            folha_total=1,
        )
        with pytest.raises(FrozenInstanceError):
            ctx.empresa_razao_social = "outra"  # type: ignore[misc]

    def test_empresa_rotulo_inscricao_tem_default_cnpj_por_compatibilidade(self):
        """DL-038: `empresa_rotulo_inscricao` é campo novo, com valor
        padrão `"CNPJ"` — o único rótulo que existia antes desta etapa.
        Sem chamador de produção nesta camada ainda (só este arquivo de
        teste), o default garante que a assinatura continua construível
        exatamente como antes, sem passar o campo novo."""
        ctx = IdentificacaoContexto(
            empresa_razao_social="x",
            empresa_cnpj="y",
            empresa_nire=None,
            empresa_nivel_arredondamento="z",
            periodo_coberto="w",
            moeda="BRL",
            data_emissao="01/01/2026",
            relatorio_nome="Balancete",
            escritorio_razao_social="e",
            escritorio_crc="c",
            profissional_nome="p",
            profissional_crc="pc",
            folha_atual=1,
            folha_total=1,
        )
        assert ctx.empresa_rotulo_inscricao == "CNPJ"


class TestRotuloDeInscricaoPessoaFisica:
    """DL-038: quando o contexto vem de uma empresa cliente pessoa física
    (CPF), o bloco de identificação mostra o rótulo `"CPF"` em vez de
    `"CNPJ"` — nas três classes de documento, já que as três reaproveitam
    a mesma linha `_campo_obrigatorio(ctx.empresa_rotulo_inscricao, ...)`.
    """

    @pytest.mark.parametrize(
        "classe",
        [ClasseDocumento.CONFERENCIA, ClasseDocumento.DEMONSTRACAO, ClasseDocumento.LIVRO],
    )
    def test_rotulo_cpf_substitui_cnpj_em_todas_as_classes(self, ctx_minimo, classe):
        from dataclasses import replace

        ctx = replace(ctx_minimo, empresa_cnpj="12345678909", empresa_rotulo_inscricao="CPF")
        bloco = bloco_obrigatorio_para(classe, ctx)
        labels = [campo.label for campo in bloco.campos]
        assert "CPF" in labels
        assert "CNPJ" not in labels
        campo = next(c for c in bloco.campos if c.label == "CPF")
        assert campo.valor == "12345678909"

    def test_rotulo_default_continua_cnpj_quando_nao_informado(self, ctx_minimo):
        # ctx_minimo não passa `empresa_rotulo_inscricao` — confirma que o
        # comportamento de ANTES da DL-038 não mudou por omissão.
        bloco = bloco_obrigatorio_para(ClasseDocumento.CONFERENCIA, ctx_minimo)
        labels = [campo.label for campo in bloco.campos]
        assert "CNPJ" in labels
        assert "CPF" not in labels
