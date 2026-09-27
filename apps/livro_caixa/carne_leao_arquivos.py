"""Geração dos arquivos de importação do Carnê-Leão Web (DL-046, fatia 3 —
RC-127): dois CSV, um de rendimentos e um de pagamentos, no leiaute oficial
(instruções dos modelos de importação, Receita Federal, 2025 — os seis
arquivos-modelo oficiais, reproduzidos como fixture de teste em
`apps/livro_caixa/tests/fixtures/carne_leao_modelos/`, com README próprio
citando a origem).

⚠️ **Nunca gera arquivo parcial.** Se houver QUALQUER lançamento que o
leiaute recusaria — ocupação ausente, competência da previdência ausente,
histórico longo demais ou com caractere que rompe a estrutura do CSV,
código fora das tabelas confirmadas — a função levanta
`GeracaoArquivoCarneLeaoBloqueada` com a lista COMPLETA de pendências
(lançamento, campo, motivo), como o veto da DRE e do Balanço
(`apps.contabilidade`). Nada é truncado nem corrigido em silêncio.

⚠️ **Fora do arquivo, sempre** (critério 3 do plano): o lançamento
ESTORNADO e o próprio ESTORNO (o Carnê-Leão Web não aceita valor negativo,
e o estorno fica sempre no mesmo mês do original — RC-130, já garantido por
`apps.livro_caixa.services.estornar_lancamento_caixa` — então omitir os
DOIS tem o mesmo efeito líquido de importar os dois com sinal invertido,
sem nunca escrever um valor negativo); e lançamento de conta SEM código do
Carnê-Leão Web (legado, gravado por ORM direto — `full_clean()` sempre
exige o código nas contas criadas pelo serviço). Estes dois casos são
EXCLUSÃO silenciosa, não pendência — a linha simplesmente não pertence ao
arquivo, por desenho do próprio leiaute.

⚠️ **Encoding e leitura**: ISO-8859-1 (latin-1) com quebra de linha CRLF
(HI-41 — os arquivos-modelo oficiais estão nesse formato); leitura dos
lançamentos sob `REPEATABLE READ`, mesmo padrão de `apps.livro_caixa.
carne_leao._sob_snapshot` (não reaproveitado daqui de propósito: é uma
função PRIVADA daquele módulo, e duplicar dez linhas é mais simples e mais
seguro do que importar um nome privado entre módulos).
"""

from collections import defaultdict
from decimal import Decimal
from typing import NamedTuple

from django.db import connection, transaction

from apps.auditoria.services import registrar
from apps.livro_caixa.models import LancamentoCaixa, NaturezaCaixa
from apps.livro_caixa.services import apurar_livro_caixa
from apps.livro_caixa.validators import (
    CODIGO_OCUPACAO_NOTARIAL,
    CODIGO_PAGAMENTO_PREVIDENCIA_OFICIAL,
    MODELO_ALUGUEL_OUTROS,
    MODELO_NOTARIAL,
    MODELO_PAGAMENTO_FORA_DE_ESCOPO,
    MODELO_PAGAMENTO_GERAL_SIMPLES,
    MODELO_PAGAMENTO_PLANO_DE_CONTAS,
    MODELO_PAGAMENTO_PREVIDENCIA_OFICIAL,
    MODELO_TRABALHO_NAO_ASSALARIADO,
    modelo_do_codigo_de_pagamento,
    modelo_do_codigo_de_rendimento,
)

_ZERO = Decimal("0.00")

# Leiaute oficial: campos separados por `;`; histórico com até 255
# caracteres ("Formato do arquivo de Escrituração", Receita Federal,
# publicada em 10/07/2023, atualizada em 21/10/2025).
_TAMANHO_MAXIMO_HISTORICO = 255


class Pendencia(NamedTuple):
    """Uma linha que o leiaute oficial recusaria — a tela lista cada uma,
    com o lançamento, o campo e o motivo, como o veto da DRE/Balanço."""

    lancamento_id: int
    campo: str
    motivo: str


class GeracaoArquivoCarneLeaoBloqueada(Exception):
    """Levantada quando há pendências — nenhum arquivo é gerado enquanto
    elas não forem corrigidas. `.pendencias` é a lista completa
    (`list[Pendencia]`)."""

    def __init__(self, pendencias):
        self.pendencias = pendencias
        super().__init__(
            f"{len(pendencias)} pendência(s) impedem a geração do arquivo do Carnê-Leão Web."
        )


class PeriodoInvalidoParaArquivoCarneLeaoWeb(Exception):
    """`inicio`/`fim` fora de ordem, ou fora de um único ano-calendário —
    ver o docstring de `gerar_arquivos_carne_leao` para a fonte da segunda
    regra."""


# ---------------------------------------------------------------------------
# Formatação de campo — DD/MM/AAAA, vírgula decimal sem separador de
# milhar, MM/AAAA — exatamente como os arquivos-modelo oficiais.


def _data_csv(valor):
    return valor.strftime("%d/%m/%Y")


def _valor_csv(valor):
    # `valor` já chega arredondado a 2 casas (campo `DecimalField` do
    # modelo) — `quantize` aqui é só defesa contra um `Decimal` com
    # expoente diferente vindo de algum caminho não previsto (nunca deveria
    # acontecer, mas o formato do arquivo é o contrato com a Receita: mais
    # vale uma segunda garantia redundante do que um "999,999" na linha).
    texto = f"{valor.quantize(Decimal('0.01')):.2f}"
    return texto.replace(".", ",")


def _competencia_csv(valor):
    return f"{valor.month:02d}/{valor.year:04d}"


def _linha_csv(campos):
    return ";".join(campos)


def _bytes_csv(linhas):
    """`linhas`: lista de listas de campos (cada uma já truncada no
    formato certo — ver os `_campos_*` abaixo). Uma linha por lançamento,
    juntas por CRLF (HI-41); sem CRLF final (mesmo padrão da maioria dos
    arquivos-modelo oficiais — só um dos seis termina com CRLF extra, e
    isso não muda o conteúdo para quem lê)."""
    texto = "\r\n".join(_linha_csv(campos) for campos in linhas)
    return texto.encode("iso-8859-1")


def _erro_de_historico(historico):
    """`None` quando o histórico é seguro para o leiaute; senão, a
    mensagem da pendência. Três checagens, nesta ordem: tamanho (255,
    "Formato do arquivo de Escrituração"), representável em ISO-8859-1
    (HI-41 — nunca substituir um caractere em silêncio) e ausência de `;`/
    quebra de linha (decisão do `desenvolvedor-pleno`, DE-093 — o leiaute
    não tem mecanismo de escape para o separador de campo; deixar passar
    romperia a estrutura da linha no Carnê-Leão Web sem nenhum aviso)."""
    if len(historico) > _TAMANHO_MAXIMO_HISTORICO:
        return (
            f"histórico com {len(historico)} caracteres — o leiaute do "
            f"Carnê-Leão Web aceita no máximo {_TAMANHO_MAXIMO_HISTORICO}."
        )
    try:
        historico.encode("iso-8859-1")
    except UnicodeEncodeError as exc:
        trecho = historico[exc.start : exc.end]
        return (
            "histórico contém caractere não representável em ISO-8859-1 "
            f"(posição {exc.start}: {trecho!r}) — o Carnê-Leão Web importa o "
            "arquivo nessa codificação (HI-41); nada é substituído em silêncio."
        )
    if ";" in historico or "\r" in historico or "\n" in historico:
        return (
            "histórico contém ';', retorno de carro ou quebra de linha — "
            "romperia a estrutura do arquivo (campos separados por ';', uma "
            "linha por lançamento)."
        )
    return None


def _ocupacao_efetiva(empresa, conta):
    """Conta sobrepõe cadastro (HI-34) — vazio quando nenhum dos dois tem
    valor."""
    return conta.codigo_ocupacao or empresa.codigo_ocupacao or ""


# ---------------------------------------------------------------------------
# Campos por MODELO de rendimento — reproduzem exatamente a estrutura dos
# arquivos-modelo oficiais, inclusive o truncamento de campos VAZIOS no
# FINAL da linha (um campo vazio no MEIO da linha preserva o `;`; vazio no
# fim da linha nunca aparece — comportamento medido nos seis arquivos-
# modelo, citado no README da fixture de teste).


def _campos_rendimento_trabalho_nao_assalariado(lancamento, ocupacao):
    base = [
        _data_csv(lancamento.data),
        lancamento.conta.codigo_carne_leao,
        ocupacao,
        _valor_csv(lancamento.valor),
        "",  # valor de dedução — sempre vazio neste modelo (instrução oficial)
        lancamento.historico,
        lancamento.recebido_de,
    ]
    if lancamento.recebido_de == "PF":
        campos = base + [lancamento.cpf_titular_pagamento]
        if lancamento.cpf_beneficiario_nao_informado:
            campos += [lancamento.cpf_beneficiario_servico, "S"]
        else:
            campos += [lancamento.cpf_beneficiario_servico]
        return campos
    if lancamento.recebido_de == "PJ":
        campos = base + ["", "", "", lancamento.cnpj_pagador]
        if lancamento.valor_irrf and lancamento.valor_irrf > 0:
            campos += ["S", _valor_csv(lancamento.valor_irrf)]
        else:
            campos += ["N"]
        return campos
    return base  # EX — só os 7 campos comuns


def _campos_rendimento_notarial(lancamento):
    base = [
        _data_csv(lancamento.data),
        lancamento.conta.codigo_carne_leao,
        CODIGO_OCUPACAO_NOTARIAL,
        _valor_csv(lancamento.valor),
        "",
        lancamento.historico,
        lancamento.recebido_de,
    ]
    if lancamento.recebido_de == "PF":
        return base + [lancamento.cpf_titular_pagamento]
    if lancamento.recebido_de == "PJ":
        campos = base + ["", "", "", lancamento.cnpj_pagador]
        if lancamento.valor_irrf and lancamento.valor_irrf > 0:
            campos += ["S", _valor_csv(lancamento.valor_irrf)]
        else:
            campos += ["N"]
        return campos
    return base  # EX


def _campos_rendimento_aluguel_outros(lancamento):
    # HI-39: o "valor da dedução" (art. 42, parcelas do aluguel) fica fora
    # desta fatia — sempre vazio. Sempre 7 campos, nunca truncado (o
    # último campo, "recebido de", é sempre preenchido).
    return [
        _data_csv(lancamento.data),
        lancamento.conta.codigo_carne_leao,
        "",  # código de ocupação — sempre vazio neste modelo
        _valor_csv(lancamento.valor),
        "",  # valor de dedução — HI-39, fora do escopo desta fatia
        lancamento.historico,
        lancamento.recebido_de,
    ]


# ---------------------------------------------------------------------------
# Campos por MODELO de pagamento.


def _campos_pagamento_plano_de_contas(lancamento):
    return [
        _data_csv(lancamento.data),
        lancamento.conta.codigo_carne_leao,
        _valor_csv(lancamento.valor),
        lancamento.historico,
    ]


def _campos_pagamento_geral(lancamento):
    """P20 — sempre 7 campos, mesmo quando multa/juros/competência estão
    vazios (comportamento medido nos arquivos-modelo oficiais de
    pagamentos gerais: diferente dos modelos de rendimento, aqui os
    campos finais vazios NÃO são truncados)."""
    codigo = lancamento.conta.codigo_carne_leao
    if codigo == CODIGO_PAGAMENTO_PREVIDENCIA_OFICIAL:
        multa = _valor_csv(lancamento.multa_previdencia) if lancamento.multa_previdencia else ""
        juros = _valor_csv(lancamento.juros_previdencia) if lancamento.juros_previdencia else ""
        competencia = (
            _competencia_csv(lancamento.competencia_previdencia)
            if lancamento.competencia_previdencia
            else ""
        )
    else:
        multa = juros = competencia = ""
    return [
        _data_csv(lancamento.data),
        codigo,
        _valor_csv(lancamento.valor),
        lancamento.historico,
        multa,
        juros,
        competencia,
    ]


# ---------------------------------------------------------------------------
# Pendências + montagem das linhas — uma passada só sobre os lançamentos já
# filtrados (excluídos estorno/estornado/conta-sem-código).


def _pendencias_e_linhas(empresa, lancamentos):
    pendencias = []
    linhas_rendimentos = []
    linhas_pagamentos = []
    totais_rendimentos = defaultdict(lambda: _ZERO)
    totais_pagamentos = defaultdict(lambda: _ZERO)

    for lancamento in lancamentos:
        erro_historico = _erro_de_historico(lancamento.historico)
        if erro_historico is not None:
            pendencias.append(Pendencia(lancamento.id, "historico", erro_historico))
            continue

        conta = lancamento.conta
        codigo = conta.codigo_carne_leao

        if conta.natureza == NaturezaCaixa.RECEITA:
            modelo = modelo_do_codigo_de_rendimento(codigo)
            if modelo == MODELO_TRABALHO_NAO_ASSALARIADO:
                ocupacao = _ocupacao_efetiva(empresa, conta)
                if not ocupacao:
                    pendencias.append(
                        Pendencia(
                            lancamento.id,
                            "codigo_ocupacao",
                            "código de ocupação ausente — obrigatório na linha de "
                            "rendimento de trabalho não assalariado (cadastre no "
                            "cliente ou na conta).",
                        )
                    )
                    continue
                campos = _campos_rendimento_trabalho_nao_assalariado(lancamento, ocupacao)
            elif modelo == MODELO_NOTARIAL:
                campos = _campos_rendimento_notarial(lancamento)
            elif modelo == MODELO_ALUGUEL_OUTROS:
                campos = _campos_rendimento_aluguel_outros(lancamento)
            else:
                pendencias.append(
                    Pendencia(
                        lancamento.id,
                        "conta.codigo_carne_leao",
                        f"código de rendimento '{codigo}' fora das tabelas confirmadas "
                        "para importação no Carnê-Leão Web (PE-71).",
                    )
                )
                continue
            linhas_rendimentos.append(campos)
            totais_rendimentos[codigo] += lancamento.valor
        else:
            modelo_pagamento = modelo_do_codigo_de_pagamento(codigo)
            if modelo_pagamento == MODELO_PAGAMENTO_PLANO_DE_CONTAS:
                campos = _campos_pagamento_plano_de_contas(lancamento)
            elif modelo_pagamento == MODELO_PAGAMENTO_PREVIDENCIA_OFICIAL:
                if lancamento.competencia_previdencia is None:
                    pendencias.append(
                        Pendencia(
                            lancamento.id,
                            "competencia_previdencia",
                            "competência ausente — obrigatória no pagamento de "
                            "previdência oficial (P20.01.00001).",
                        )
                    )
                    continue
                campos = _campos_pagamento_geral(lancamento)
            elif modelo_pagamento == MODELO_PAGAMENTO_GERAL_SIMPLES:
                campos = _campos_pagamento_geral(lancamento)
            elif modelo_pagamento == MODELO_PAGAMENTO_FORA_DE_ESCOPO:
                pendencias.append(
                    Pendencia(
                        lancamento.id,
                        "conta.codigo_carne_leao",
                        f"código '{codigo}' (pagamento do próprio carnê-leão) está "
                        "fora do escopo desta funcionalidade — o Carnê-Leão Web "
                        "importa esse valor automaticamente após a confirmação do "
                        "pagamento nos sistemas da Receita, a partir de 2026.",
                    )
                )
                continue
            else:
                pendencias.append(
                    Pendencia(
                        lancamento.id,
                        "conta.codigo_carne_leao",
                        f"código de pagamento '{codigo}' fora das tabelas "
                        "confirmadas para importação no Carnê-Leão Web.",
                    )
                )
                continue
            linhas_pagamentos.append(campos)
            totais_pagamentos[codigo] += lancamento.valor

    return (
        pendencias,
        linhas_rendimentos,
        linhas_pagamentos,
        dict(totais_rendimentos),
        dict(totais_pagamentos),
    )


# ---------------------------------------------------------------------------
# Camada ORM.


def _sob_snapshot(func, **kwargs):
    """Mesma técnica de `apps.livro_caixa.carne_leao._sob_snapshot` (DE-067/
    A5 da auditoria DL-045) — não reaproveitada de lá de propósito: é uma
    função PRIVADA daquele módulo (não faz parte do contrato público entre
    os dois), e duplicar dez linhas evita acoplar dois módulos por um nome
    que pode mudar sem aviso."""
    ja_estava_em_transacao = connection.in_atomic_block
    with transaction.atomic():
        if not ja_estava_em_transacao:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return func(**kwargs)


def _lancamentos_incluidos(empresa, inicio, fim):
    """Lançamentos do período, MENOS estornado/estorno e conta sem código
    (critério 3 do plano) — devolve `(incluidos, excluidos_estorno,
    excluidos_sem_codigo)`.

    A checagem de "foi estornado?" NÃO se limita ao período pedido: um
    lançamento do início da janela pode ter sido estornado numa data que
    caiu FORA dela (a estornar-se sempre no mesmo MÊS do original —
    `estornar_lancamento_caixa` — mas um período pedido menor que um mês
    inteiro ainda assim pode cortar o par ao meio). Por isso a segunda
    consulta busca por `estorno_de_id`, sem filtro de data.
    """
    lancamentos = list(
        LancamentoCaixa.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        .select_related("conta")
        .order_by("data", "id")
    )
    ids_do_periodo = [lancamento.id for lancamento in lancamentos]
    ids_estornados = set(
        LancamentoCaixa.objects.filter(estorno_de_id__in=ids_do_periodo).values_list(
            "estorno_de_id", flat=True
        )
    )

    incluidos = []
    excluidos_estorno = 0
    excluidos_sem_codigo = 0
    for lancamento in lancamentos:
        if lancamento.estorno_de_id is not None or lancamento.id in ids_estornados:
            excluidos_estorno += 1
            continue
        if not lancamento.conta.codigo_carne_leao:
            excluidos_sem_codigo += 1
            continue
        incluidos.append(lancamento)
    return incluidos, excluidos_estorno, excluidos_sem_codigo


def _gerar_arquivos_sob_snapshot(*, empresa, inicio, fim, usuario, request):
    incluidos, excluidos_estorno, excluidos_sem_codigo = _lancamentos_incluidos(
        empresa, inicio, fim
    )

    pendencias, linhas_rend, linhas_pag, totais_rend, totais_pag = _pendencias_e_linhas(
        empresa, incluidos
    )
    if pendencias:
        raise GeracaoArquivoCarneLeaoBloqueada(pendencias)

    rendimentos_bytes = _bytes_csv(linhas_rend)
    pagamentos_bytes = _bytes_csv(linhas_pag)

    total_rendimentos = sum(totais_rend.values(), _ZERO)
    total_pagamentos = sum(totais_pag.values(), _ZERO)

    # Conferência (critério 5 do plano): os totais do arquivo, e os mesmos
    # totais do relatório Livro Caixa do MESMO período, para a tela mostrar
    # os dois lado a lado. Só podem divergir por lançamento de conta SEM
    # código (excluído do arquivo, mas presente no Livro Caixa) — a
    # diferença fica exposta, nunca escondida.
    livro = apurar_livro_caixa(empresa=empresa, inicio=inicio, fim=fim)

    conferencia = {
        "empresa_id": empresa.id,
        "periodo_inicio": inicio,
        "periodo_fim": fim,
        "linhas_rendimentos": len(linhas_rend),
        "linhas_pagamentos": len(linhas_pag),
        "totais_rendimentos_por_codigo": totais_rend,
        "totais_pagamentos_por_codigo": totais_pag,
        "total_rendimentos": total_rendimentos,
        "total_pagamentos": total_pagamentos,
        "total_entradas_livro_caixa": livro["total_entradas"],
        "total_saidas_livro_caixa": livro["total_saidas"],
        "diferenca_rendimentos": livro["total_entradas"] - total_rendimentos,
        "diferenca_pagamentos": livro["total_saidas"] - total_pagamentos,
        "lancamentos_excluidos_estorno": excluidos_estorno,
        "lancamentos_excluidos_sem_codigo": excluidos_sem_codigo,
    }

    # Trilha do arquivo gerado (período, linhas, totais — NUNCA o conteúdo:
    # nenhum histórico, CPF/CNPJ ou valor por lançamento entra em
    # `detalhes`, só agregados).
    registrar(
        acao="carne_leao_arquivo.gerado",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=empresa,
        request=request,
        detalhes={
            "empresa_id": empresa.id,
            "periodo_inicio": inicio.isoformat(),
            "periodo_fim": fim.isoformat(),
            "linhas_rendimentos": len(linhas_rend),
            "linhas_pagamentos": len(linhas_pag),
            "total_rendimentos": str(total_rendimentos),
            "total_pagamentos": str(total_pagamentos),
        },
    )

    return rendimentos_bytes, pagamentos_bytes, conferencia


def gerar_arquivos_carne_leao(*, empresa, inicio, fim, usuario, request=None):
    """Gera os dois arquivos de importação do Carnê-Leão Web (rendimentos e
    pagamentos) para `[inicio, fim]`, dentro de um único ano-calendário.

    Devolve `(rendimentos_bytes, pagamentos_bytes, conferencia)` — os dois
    primeiros já em ISO-8859-1 com CRLF (HI-41), prontos para servir como
    anexo; `conferencia` é um `dict` com os totais por código e a
    comparação com o Livro Caixa do período.

    Levanta `PeriodoInvalidoParaArquivoCarneLeaoWeb` se `inicio > fim` ou
    se o período cruzar mais de um ano-calendário (o manual do sistema de
    referência descreve rendimentos/pagamentos e a importação da
    escrituração sempre "no ano selecionado", sem exigir arquivo mensal —
    ver a resposta à segunda dúvida da fatia 3 no plano DL-046). Levanta
    `GeracaoArquivoCarneLeaoBloqueada` com a lista de pendências quando
    houver qualquer linha que o leiaute recusaria.

    Autorização, isolamento e modo de escrituração são responsabilidade de
    QUEM CHAMA — mesmo limite declarado de `apurar_livro_caixa`/
    `apurar_carne_leao_mensal`: as views deste app aplicam essa verificação
    via `EmpresaEscopadaLivroCaixaMixin`/`PodeLerLivroCaixa`, ANTES de
    chegar aqui.
    """
    if inicio > fim:
        raise PeriodoInvalidoParaArquivoCarneLeaoWeb(
            f"'inicio' ({inicio.isoformat()}) não pode ser posterior a 'fim' ({fim.isoformat()})."
        )
    if inicio.year != fim.year:
        raise PeriodoInvalidoParaArquivoCarneLeaoWeb(
            "O período deve ficar dentro de um único ano-calendário — o "
            f"início ({inicio.isoformat()}) e o fim ({fim.isoformat()}) "
            "estão em anos diferentes."
        )

    return _sob_snapshot(
        _gerar_arquivos_sob_snapshot,
        empresa=empresa,
        inicio=inicio,
        fim=fim,
        usuario=usuario,
        request=request,
    )
