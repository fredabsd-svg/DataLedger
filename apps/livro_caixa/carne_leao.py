"""Apuração mensal e anual do carnê-leão (DL-046, fatia 2 — RC-131/RC-132/
RC-133/RC-134, HI-32 a HI-40).

⚠️ **Correção da RODADA 1 da auditoria da fatia 2, em 2026-09-27** (DE-091):
esta versão do módulo incorpora as dez decisões da DE-091 — o limite da
dedução do livro-caixa passa a somar a receita da atividade (trabalho não
assalariado **e** notarial) recebida de PF, PJ **ou** exterior (item 1); a
forma de dedução (real/simplificado) passa a ser escolhida pela MAIOR
DEDUÇÃO, antes da redução, com empate para o simplificado (item 2); a
compensação do imposto pago no exterior segue leitura LITERAL da Perguntas e
Respostas 267 — a parte acima do limite do mês nunca compensa nem carrega
(item 3); o estorno de um lançamento de caixa passa a ter a data do ORIGINAL
como padrão, recusando data explícita de outro mês (item 4); a tabela
progressiva de janeiro a abril de 2025 é semeada por migração de dados, e a
ausência de vigência de REDUÇÃO antes de 2026 passa a ser tratada como
ausência LEGÍTIMA (item 5); a quantidade de dependentes ganha retificação
(PATCH) rastreável (item 6); o contrato da API ganha os campos `rendimentos`,
`imposto_com_exterior`/`imposto_sem_exterior`, `vencimento`, `alertas` e
`criterio_escolha_forma` (item 7); o percentual do desconto simplificado
passa a morar na vigência da tabela, com fonte (item 8, B-1); e as correções
pontuais B-2 a B-5 (ver `docs/projeto/requisitos.md`/`decisoes.md`).

⚠️ **Correção da RECONFERÊNCIA da fatia 2, em 2026-09-27** (DE-092, sobre
`docs/auditorias/2026-09-27-dl-046-fatia2-reconferencia.md`): a HI-38
(imposto pago no exterior sem rendimento do exterior no mês) deixou de
BLOQUEAR a apuração — bloqueava o resto do ano-calendário inteiro, porque a
apuração de qualquer mês encadeia desde janeiro, e a Perguntas e Respostas
IRPF 2026 prevê justamente esse caso como compensável no mês do próprio
pagamento (R-M4/item 1); o alerta de rendimento líquido negativo passou a
disparar só quando o RENDIMENTO SUJEITO do mês é negativo, não mais quando a
dedução supera o rendimento — a versão anterior disparava em quase todo mês
comum (R-M1/item 2); mensagens ao usuário (motor e serviço) pararam de citar
identificador interno do projeto ou jargão técnico (R-M2/item 3); a ausência
de vigência de redução virou erro a partir de 2026-01-01 — só é ausência
legítima ANTES disso (R-B3); a memória do mês ganhou `deducao_aplicada`,
`valor_por_dependente`, `reducao_vigente` e `imposto_exterior_nao_
compensavel` (R-B4/B5); e `retificar_dependentes_carne_leao` trava a linha
da empresa (R-B6).

⚠️ **RC-133 foi CORRIGIDA em 2026-09-27** (ordem do arquiteto-senior): a
redução da Lei 15.270/2025 usa o RENDIMENTO BRUTO (antes de qualquer
dedução), NUNCA a base de cálculo — a versão original deste módulo usava a
base, o que não reproduzia os exemplos oficiais da Receita Federal (ver
`_reducao_bruta`, abaixo, e docs/planos/DL-046-livro-caixa-e-carne-leao.md,
"Correção da RC-133").

Motor de cálculo PURO (funções privadas `_pipeline`/`_imposto_pela_tabela`/
`_reducao_bruta`/`_agregados_do_mes`) separado da camada ORM
(`apurar_carne_leao_mensal`/`apurar_carne_leao_anual`), no mesmo espírito de
`apps.contabilidade.services` (DE-034 item 2): regra de cálculo testável sem
banco, agregação testável com banco.

⚠️ **Nunca grava resultado.** A apuração é sempre recalculada a partir dos
LANÇAMENTOS de origem (RC-130, critério 3 do plano): corrigir um lançamento
de um mês passado (por estorno, já que lançamento efetivado é imutável) muda
o resultado desta função na PRÓXIMA chamada, sem nenhuma tabela de resultado
para reconciliar ou invalidar — o "banco de dados" da apuração é
`LancamentoCaixa` mais as quatro tabelas normativas, nunca um cache.

⚠️ **Encadeamento dentro do ANO-CALENDÁRIO, nunca entre anos.** O excesso de
deduções do livro-caixa (art. 69, RIR/2018, §1º) e o saldo de crédito do
imposto pago no exterior (Perguntas e Respostas IRPF 2026, pergunta 267,
"Atenção") são, os dois, POR LEI, limitados a dezembro do mesmo
ano-calendário — a apuração de qualquer mês recomeça de janeiro do MESMO
ano, nunca lê dezembro do ano anterior. O saldo "abaixo de R$ 10,00" (RIR/
2018, art. 938, §§ 4º e 5º; Lei 9.430/1996, art. 68) não tem, nas fontes
consultadas, uma regra que o reinicie por ano-calendário (HI-37) — mas esta implementação, ao só
olhar o ano pedido, também o reinicia em janeiro; é uma LIMITAÇÃO DECLARADA
desta fatia (ver o plano DL-046, "Não testado"), não uma regra confirmada.

⚠️ **Nenhum número normativo aparece como literal Python neste arquivo**
(critério 5 do plano): tabela progressiva, redução da Lei 15.270/2025,
percentual do desconto simplificado e valor por dependente vêm SEMPRE de
`apps.livro_caixa.models.VigenciaTabelaProgressivaCarneLeao`/
`VigenciaReducaoCarneLeao`/`VigenciaDependenteCarneLeao`, gravadas por
migração de dados. A ausência de uma vigência aplicável levanta
`TabelaCarneLeaoNaoConfigurada` — nunca um valor-padrão do código. A ÚNICA
exceção CONSCIENTE é o limite de R$ 10,00 do DARF (`_LIMITE_DARF`, abaixo):
constante LEGAL (Lei 9.430/1996, art. 68; RIR/2018, art. 938, §§ 4º e 5º),
não normativa-com-vigência — a lei não fixa esse valor "a partir de uma
data", como as tabelas de cima; é um piso fixo (DE-091 item 9, B-1).

HI-36 (requisitos.md) — arredondamento: nenhuma das fontes lidas (RIR/2018,
Lei 9.250/1995, Lei 15.270/2025, Perguntas e Respostas IRPF 2026) fixa a
política de arredondamento de cada etapa intermediária do carnê-leão (só do
resultado final, implicitamente, por ser sempre expresso em reais e
centavos). Escolha CONSERVADORA declarada: `PoliticaArredondamento.
MEIO_PARA_CIMA` (ROUND_HALF_UP), aplicada a CADA valor monetário que se
torna uma LINHA da memória de cálculo, para nunca deixar um cálculo
intermediário sem escala definida entre etapas. (Correção de 2026-09-27,
rodada 1 da auditoria da fatia 2, B-2: a versão anterior deste parágrafo
afirmava que truncar "reduziria o imposto devido em relação ao valor exato"
— a auditoria mediu contraexemplos; a frase foi retirada, a escolha por
MEIO_PARA_CIMA permanece só pela razão declarada acima.)
"""

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, models, transaction

from apps.auditoria.services import registrar
from apps.core.dinheiro import PoliticaArredondamento, quantizar
from apps.core.restricoes import mensagens_de, restricao_como_400
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.livro_caixa.models import (
    DependentesCarneLeaoCliente,
    FaixaTabelaProgressivaCarneLeao,
    LancamentoCaixa,
    NaturezaCaixa,
    VigenciaDependenteCarneLeao,
    VigenciaReducaoCarneLeao,
    VigenciaTabelaProgressivaCarneLeao,
)
from apps.livro_caixa.validators import (
    CODIGO_RENDIMENTO_NOTARIAL,
    CODIGO_RENDIMENTO_PENSAO_ALIMENTICIA,
    CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO,
    rendimento_carne_leao_e_sujeito_ao_recolhimento_mensal,
)

# HI-36 — ver o docstring do módulo.
_POLITICA = PoliticaArredondamento.MEIO_PARA_CIMA
_ZERO = Decimal("0.00")

# DE-091 item 9 (B-1): constante LEGAL, não normativa-com-vigência — ver o
# docstring do módulo, parágrafo "Nenhum número normativo".
_LIMITE_DARF = Decimal("10.00")

# Códigos que integram o LIMITE do livro-caixa (DE-091 item 1, A-1/A-2):
# receita da atividade de trabalho não assalariado e notarial, recebida de
# QUALQUER origem (PF, PJ ou exterior) — ver `_agregados_do_mes`.
_CODIGOS_ATIVIDADE_LIVRO_CAIXA = (
    CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO,
    CODIGO_RENDIMENTO_NOTARIAL,
)


def _q(valor):
    return quantizar(valor, casas=2, politica=_POLITICA)


def _fmt_reais(valor):
    """`Decimal` → texto no formato brasileiro ("R$ 1.234,56") — usado só
    para compor `criterio_escolha_forma` (DE-091 item 7, acréscimo do
    arquiteto-senior), nunca para cálculo."""
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


class TabelaCarneLeaoNaoConfigurada(Exception):
    """Levantada quando não há, no BANCO, uma vigência de tabela
    progressiva, redução (Lei 15.270/2025) ou valor por dependente
    aplicável ao mês pedido — ou quando o ano pedido está fora do escopo
    desta fatia (antes de 2025). NUNCA cai para um valor padrão do código —
    ver o critério 5 do plano DL-046, fatia 2, e o docstring do módulo."""


class DependentesCarneLeaoInvalido(Exception):
    """Erro de domínio ao registrar/retificar a quantidade de dependentes
    de um cliente — mesmo papel de `LancamentoCaixaInvalido` (services.py)."""


class ImpostoExteriorSemRendimentoExterior(Exception):
    """⚠️ **Não é mais levantada pela apuração.** A rodada 1 desta correção
    recusava o mês inteiro quando havia imposto pago no exterior
    (`P20.01.00003`) sem nenhum rendimento sujeito de fonte no exterior no
    mesmo mês (HI-38). A reconferência mediu o efeito colateral (R-M4): a
    recusa bloqueava TODO o resto do ano-calendário (a apuração de qualquer
    mês encadeia desde janeiro), quando a Perguntas e Respostas IRPF 2026
    prevê justamente esse caso (imposto pago em mês posterior ao
    rendimento) como compensável no mês do próprio pagamento.

    A decisão revista (DE-092, item 1) é: o mês é apurado normalmente, a
    compensação desse pagamento específico é zero, e a memória do mês traz
    um alerta em linguagem simples avisando que o valor pode ser aproveitado
    na declaração anual — sem interromper o encadeamento dos meses
    seguintes. Ver `_apurar_um_mes`.

    Esta classe continua **definida**, mas nunca mais levantada por este
    módulo, porque a tela do carnê-leão (`views_web.py`, outro worktree)
    ainda a importa e a captura como um estado de erro — removê-la
    quebraria esse import. Reportado ao `arquiteto-senior` para decidir se
    a tela deve parar de importá-la numa etapa futura."""


# ---------------------------------------------------------------------------
# Motor de cálculo PURO — sem ORM, só `Decimal`. Testável isoladamente com
# casos calculados à mão (critério 1 do plano).


def _faixa_da_base(base, faixas):
    """`faixas` já ordenadas por `ordem` (alíquota crescente). Devolve a
    primeira cuja `limite_superior` (ou ausência dele, na última faixa)
    cobre `base` — as faixas da tabela oficial são CONTÍGUAS, sem lacuna
    entre uma e a próxima (RC-131), então a primeira que cobre é a única
    que cobre."""
    for faixa in faixas:
        if faixa.limite_superior is None or base <= faixa.limite_superior:
            return faixa
    raise TabelaCarneLeaoNaoConfigurada(
        f"A tabela progressiva não tem faixa que cubra a base de cálculo {base} "
        "— faltam faixas com limite superior aberto (última faixa)."
    )


def _imposto_pela_tabela(base, faixas):
    _, imposto = _faixa_e_imposto_pela_tabela(base, faixas)
    return imposto


def _faixa_e_imposto_pela_tabela(base, faixas):
    """Mesmo cálculo de `_imposto_pela_tabela`, mas devolve também a FAIXA
    usada — item 7 do contrato da API (acréscimo do arquiteto-senior,
    2026-09-27): a tela mostra `faixa_aplicada` dentro de cada memória de
    cálculo, para o contador conferir contra a tabela oficial sem abrir o
    banco."""
    faixa = _faixa_da_base(base, faixas)
    bruto = base * faixa.aliquota - faixa.parcela_a_deduzir
    return faixa, _q(max(_ZERO, bruto))


def _faixa_aplicada_para_api(faixa):
    return {
        "limite_inferior": faixa.limite_inferior,
        "limite_superior": faixa.limite_superior,
        "aliquota": faixa.aliquota,
        "parcela_a_deduzir": faixa.parcela_a_deduzir,
    }


def _reducao_bruta(rendimento_bruto, reducao_cfg):
    """Lei nº 9.250/1995, art. 3º-A (incluído pela Lei 15.270/2025) — Anexo
    X da IN RFB nº 1.500/2014 (na redação da IN RFB nº 2.299/2025): a
    redução usa o RENDIMENTO TRIBUTÁVEL BRUTO sujeito ao ajuste mensal
    (ANTES de qualquer dedução, inclusive livro-caixa), NUNCA a base de
    cálculo — RC-133 (requisitos.md).

    `reducao_cfg=None` (DE-091 item 5, M-5): ausência LEGÍTIMA de vigência
    de redução para o mês — a Lei 15.270/2025 só produz efeitos "a partir
    do mês de janeiro do ano-calendário de 2026" (art. 8º); qualquer mês de
    2025 não tem, e não DEVE ter, uma vigência de redução — devolve
    `_ZERO`, nunca levanta `TabelaCarneLeaoNaoConfigurada`.

    ⚠️ **Correção de 2026-09-27**, a partir de exemplo oficial da Receita
    Federal ("Exemplos de Aplicação da Lei 15.270/2025",
    gov.br/receitafederal — Exemplo 5): "Neste exemplo, o salário
    (rendimento tributável sujeito à incidência mensal) é superior ao
    valor de R$ 7.350,00, logo, não é permitida a redução (...). Importante
    observar que se utiliza nessa tabela de redução o valor do SALÁRIO (R$
    7.607,20), e NÃO o da BASE DE CÁLCULO (R$ 7.000,00)." A versão anterior
    desta função usava a base (após deduções) — ERRADO, contrariado pelo
    próprio exemplo oficial da Receita; a IN RFB nº 2.299/2025 confirma a
    mesma distinção (Anexo X — "Rendimentos Tributáveis Sujeitos ao
    Ajuste Mensal" — é conceito DIFERENTE do Anexo II — base de cálculo).
    Para o carnê-leão (fora do contexto de folha), "rendimento tributável"
    é o total de rendimentos SUJEITOS ao carnê-leão do mês (RC-132), antes
    de qualquer dedução — decisão do arquiteto-senior, 2026-09-27.

    Redução fixa até `limite_faixa_plena` (imposto zero); decrescente
    linearmente até `limite_superior`; nenhuma redução depois (§2º) —
    todos os TRÊS limites comparados contra o BRUTO, nunca a base.
    """
    if reducao_cfg is None:
        return _ZERO
    if rendimento_bruto <= 0:
        return _ZERO
    if rendimento_bruto <= reducao_cfg.limite_faixa_plena:
        valor = reducao_cfg.reducao_maxima
    elif rendimento_bruto <= reducao_cfg.limite_superior:
        valor = reducao_cfg.constante_formula - (reducao_cfg.coeficiente * rendimento_bruto)
    else:
        valor = _ZERO
    return _q(max(_ZERO, valor))


def _pipeline(base_bruta, rendimento_bruto, faixas, reducao_cfg, *, vigencia_tabela_inicio=None):
    """Base → imposto pela tabela → redução (limitada ao imposto, §1º) →
    imposto após redução. `base_bruta` pode ser negativa (rendimento menor
    que as deduções); a base de cálculo real nunca é negativa.

    `rendimento_bruto` (RC-133) é o rendimento ANTES de qualquer dedução —
    o MESMO valor para as duas formas de dedução (reais ou desconto
    simplificado) no mesmo mês, porque a redução nunca olha a dedução
    escolhida. Só `base_bruta` muda entre as duas chamadas que comparam
    as formas (`_apurar_um_mes`). `reducao_cfg=None`: ver `_reducao_bruta`.

    `vigencia_tabela_inicio` (item 7 do contrato da API, acréscimo do
    arquiteto-senior): opcional — só quem já sabe a vigência da tabela
    (`_apurar_um_mes`) a informa; os testes que chamam `_pipeline`
    diretamente (motor puro) não precisam dela, e o campo fica `None`."""
    base = max(_ZERO, _q(base_bruta))
    faixa, imposto_tabela = _faixa_e_imposto_pela_tabela(base, faixas)
    reducao_disponivel = _reducao_bruta(rendimento_bruto, reducao_cfg)
    # §1º do art. 3º-A: a redução fica LIMITADA ao imposto apurado pela
    # tabela — nunca produz imposto negativo nem "crédito" de redução.
    reducao_aplicada = min(reducao_disponivel, imposto_tabela)
    imposto_apos_reducao = _q(imposto_tabela - reducao_aplicada)
    return {
        "base": base,
        "imposto_tabela": imposto_tabela,
        "reducao_disponivel": reducao_disponivel,
        "reducao_aplicada": reducao_aplicada,
        "imposto_apos_reducao": imposto_apos_reducao,
        "faixa_aplicada": _faixa_aplicada_para_api(faixa),
        "vigencia_tabela_inicio": vigencia_tabela_inicio,
    }


def _imposto_sem_rendimento_exterior(
    rendimento_total, rendimento_exterior, deducao_escolhida, faixas, reducao_cfg
):
    """Perguntas e Respostas IRPF 2026, pergunta 267 ("Atenção"): o limite
    de compensação do imposto pago no exterior é "a diferença entre o
    imposto calculado COM a inclusão dos rendimentos de fontes no exterior
    e o imposto calculado SEM a inclusão desses rendimentos" — a MESMA
    forma de dedução (real ou desconto simplificado) já escolhida para o
    mês, variando só o rendimento (RC-134). O rendimento BRUTO da redução
    (RC-133) também varia entre as duas chamadas — excluir o rendimento do
    exterior muda tanto a base quanto o bruto que a redução compara contra
    os limiares de R$ 5.000,00/R$ 7.350,00.

    Devolve só o `imposto_apos_reducao` "sem exterior" — quem chama já tem
    o "com exterior" (é o `pipeline_escolhido` do mês, calculado uma vez
    só; ver `_apurar_um_mes`)."""
    rendimento_sem_exterior = rendimento_total - rendimento_exterior
    return _pipeline(
        rendimento_sem_exterior - deducao_escolhida,
        rendimento_sem_exterior,
        faixas,
        reducao_cfg,
    )["imposto_apos_reducao"]


def _motivo_exclusao_do_rendimento(codigo):
    """Texto para o campo `motivo_exclusao` do item `rendimentos` da API
    (DE-091 item 7/M-2) quando o rendimento NÃO integra a base do
    carnê-leão — `None` quando integra. Só é chamada para um `(codigo,
    origem)` que já falhou `rendimento_carne_leao_e_sujeito_ao_
    recolhimento_mensal` — os dois motivos possíveis, hoje (`apps.
    livro_caixa.validators`): pensão alimentícia recebida (imune) ou
    rendimento de pessoa jurídica fora do modelo notarial (retenção na
    fonte, RIR/2018 art. 118)."""
    if codigo == CODIGO_RENDIMENTO_PENSAO_ALIMENTICIA:
        return (
            "Pensão alimentícia recebida é imune ao Imposto de Renda (STF, ADI "
            "5.422, transitada em julgado em 05/11/2022; Perguntas e Respostas "
            "IRPF 2026, pergunta 266)."
        )
    return (
        "Rendimento recebido de pessoa jurídica: sujeito a retenção na fonte "
        "pelo pagador, fora do carnê-leão (RIR/2018, art. 118)."
    )


def _agregados_do_mes(lancamentos):
    """Soma os lançamentos de UM mês por categoria relevante ao carnê-leão.
    Estorno contribui com sinal INVERTIDO do original, do MESMO lado (mesma
    convenção de `apps.livro_caixa.services.apurar_livro_caixa`, D3) — nunca
    como um lançamento novo do lado oposto.

    ⚠️ **DE-091 item 1 (A-1/A-2)**: `receita_atividade_limite` é a receita
    de trabalho não assalariado e notarial recebida de QUALQUER origem (PF,
    PJ ou exterior) — o LIMITE do livro-caixa (art. 68/69, RIR/2018), que é
    DIFERENTE da BASE do carnê-leão (RC-132: só PF/exterior, exceto o
    notarial, que entra sempre). Por isso este acúmulo fica FORA do filtro
    de sujeição usado para `rendimento_total_sujeito`."""
    rendimento_total_sujeito = _ZERO
    rendimento_trabalho_base = _ZERO
    rendimento_notarial_base = _ZERO
    rendimento_exterior_sujeito = _ZERO
    receita_atividade_limite = _ZERO
    despesa_p10 = _ZERO
    previdencia_oficial = _ZERO
    pensao_paga = _ZERO
    imposto_pago_exterior = _ZERO
    por_codigo_origem = defaultdict(lambda: _ZERO)

    for lancamento in lancamentos:
        sinal = Decimal(-1) if lancamento.estorno_de_id is not None else Decimal(1)
        contribuicao = sinal * lancamento.valor
        codigo = lancamento.conta.codigo_carne_leao

        if lancamento.conta.natureza == NaturezaCaixa.RECEITA:
            origem = lancamento.recebido_de
            por_codigo_origem[(codigo, origem)] += contribuicao

            if codigo in _CODIGOS_ATIVIDADE_LIVRO_CAIXA:
                receita_atividade_limite += contribuicao

            # RC-132: só rendimento SUJEITO ao carnê-leão integra a BASE —
            # rendimento de PJ (fora do modelo notarial) é tributado por
            # retenção na fonte, fora do escopo desta fatia; pensão
            # alimentícia recebida é imune (STF). O limite do livro-caixa,
            # acima, já foi somado independentemente desta checagem.
            if not rendimento_carne_leao_e_sujeito_ao_recolhimento_mensal(
                codigo, recebido_de=origem
            ):
                continue
            rendimento_total_sujeito += contribuicao
            if codigo == CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO:
                rendimento_trabalho_base += contribuicao
            elif codigo == CODIGO_RENDIMENTO_NOTARIAL:
                rendimento_notarial_base += contribuicao
            if origem == "EX":
                rendimento_exterior_sujeito += contribuicao
        else:  # DESPESA
            if codigo.startswith("P10"):
                despesa_p10 += contribuicao
            elif codigo == "P20.01.00001":  # RC-131(e): previdência oficial
                previdencia_oficial += contribuicao
            elif codigo == "P20.01.00002":  # RC-131(e): pensão alimentícia paga
                pensao_paga += contribuicao
            elif codigo == "P20.01.00003":  # RC-131(e): imposto pago no exterior
                imposto_pago_exterior += contribuicao

    return {
        "rendimento_total_sujeito": rendimento_total_sujeito,
        "rendimento_trabalho_base": rendimento_trabalho_base,
        "rendimento_notarial_base": rendimento_notarial_base,
        "rendimento_exterior_sujeito": rendimento_exterior_sujeito,
        "receita_atividade_limite": receita_atividade_limite,
        "despesa_p10": despesa_p10,
        "previdencia_oficial": previdencia_oficial,
        "pensao_paga": pensao_paga,
        "imposto_pago_exterior": imposto_pago_exterior,
        "por_codigo_origem": dict(por_codigo_origem),
    }


def _rendimentos_detalhados(por_codigo_origem):
    """Lista ORDENADA (determinística) de `{codigo, origem, valor,
    entra_na_base, motivo_exclusao}` — item 7/M-2 do contrato da API,
    exatamente com estes nomes de campo."""
    detalhes = []
    for (codigo, origem), valor in sorted(por_codigo_origem.items()):
        entra_na_base = rendimento_carne_leao_e_sujeito_ao_recolhimento_mensal(
            codigo, recebido_de=origem
        )
        detalhes.append(
            {
                "codigo": codigo,
                "origem": origem,
                "valor": _q(valor),
                "entra_na_base": entra_na_base,
                "motivo_exclusao": (
                    None if entra_na_base else _motivo_exclusao_do_rendimento(codigo)
                ),
            }
        )
    return detalhes


def _vencimento_do_mes(ano, mes):
    """RC-131(d): "DARF código 0190, vencimento no último dia útil do mês
    SEGUINTE ao do recebimento" — texto descritivo (a apuração não calcula
    o dia útil exato nesta fatia, só o mês/ano de vencimento; DE-091 item
    7, acréscimo do arquiteto-senior)."""
    if mes == 12:
        mes_seguinte, ano_seguinte = 1, ano + 1
    else:
        mes_seguinte, ano_seguinte = mes + 1, ano
    return f"último dia útil de {mes_seguinte:02d}/{ano_seguinte:04d}"


def _apurar_um_mes(
    *,
    ano,
    mes,
    agregados,
    quantidade_dependentes,
    valor_por_dependente,
    faixas,
    reducao_cfg,
    percentual_desconto_simplificado,
    vigencia_tabela_inicio,
    excesso_livro_caixa_anterior,
    saldo_credito_exterior_anterior,
    saldo_pendente_abaixo_de_dez_anterior,
):
    rendimento_total = agregados["rendimento_total_sujeito"]

    # Livro-caixa (art. 68/69, RIR/2018) — DE-091 item 1 (A-1/A-2): o LIMITE
    # é a receita da ATIVIDADE (trabalho não assalariado + notarial),
    # recebida de QUALQUER origem (PF, PJ ou exterior); a DEDUÇÃO em si
    # continua restrita ao rendimento que integra a BASE (trabalho
    # PF/exterior + notarial de qualquer origem). O excesso levado ao mês
    # seguinte (até dezembro) é só a parte que passa do LIMITE — a parte
    # dentro do limite mas sem contrapartida na base (receita de PJ, por
    # exemplo) fica "usada" sem gerar excesso nem dedução: ela pertence à
    # declaração anual, fora do escopo desta fatia (DE-091 item 1).
    disponivel_livro_caixa = max(_ZERO, agregados["despesa_p10"] + excesso_livro_caixa_anterior)
    limite_atividade = max(_ZERO, agregados["receita_atividade_limite"])
    deducao_contra_limite = min(disponivel_livro_caixa, limite_atividade)
    excesso_livro_caixa_novo = _q(disponivel_livro_caixa - deducao_contra_limite)
    if mes == 12:
        excesso_livro_caixa_novo = _ZERO

    rendimento_base_relevante = max(
        _ZERO, agregados["rendimento_trabalho_base"] + agregados["rendimento_notarial_base"]
    )
    deducao_livro_caixa = min(deducao_contra_limite, rendimento_base_relevante)

    dependentes_valor = _q(Decimal(quantidade_dependentes) * valor_por_dependente)

    deducoes_reais_total = _q(
        agregados["previdencia_oficial"]
        + agregados["pensao_paga"]
        + dependentes_valor
        + deducao_livro_caixa
    )

    # Q267 (P&R IRPF 2026): desconto simplificado = percentual (vigência da
    # tabela, DE-091 item 8/B-1) do limite da FAIXA DE ALÍQUOTA ZERO da
    # tabela vigente — nunca um número solto (a primeira faixa, ordenada
    # por `ordem`, é sempre a de alíquota 0%).
    faixa_zero = faixas[0]
    if faixa_zero.aliquota != 0:
        raise TabelaCarneLeaoNaoConfigurada(
            "A primeira faixa da tabela progressiva vigente não tem alíquota "
            "zero — dado normativo incoerente (verifique a migração de dados)."
        )
    desconto_simplificado = _q(faixa_zero.limite_superior * percentual_desconto_simplificado)

    # RC-133: a redução usa o rendimento BRUTO (antes de qualquer dedução)
    # — o MESMO valor (`rendimento_total`) nas duas chamadas abaixo, seja
    # qual for a forma de dedução. Só a BASE (primeiro argumento) muda.
    pipeline_real = _pipeline(
        rendimento_total - deducoes_reais_total,
        rendimento_total,
        faixas,
        reducao_cfg,
        vigencia_tabela_inicio=vigencia_tabela_inicio,
    )
    pipeline_simplificado = _pipeline(
        rendimento_total - desconto_simplificado,
        rendimento_total,
        faixas,
        reducao_cfg,
        vigencia_tabela_inicio=vigencia_tabela_inicio,
    )

    # DE-091 item 2 (M-1): escolhe pela MAIOR DEDUÇÃO, ANTES da redução —
    # mesmo critério que a própria Receita usa para orientar o contribuinte
    # ("Exemplos de Aplicação da Lei 15.270/2025", gov.br/receitafederal,
    # publicado 22/12/2025, atualizado 04/03/2026, Exemplos 1 e 2: "Como o
    # desconto simplificado mensal é mais vantajoso do que as deduções
    # legais, a fonte pagadora deve considerá-lo" — CORREÇÃO da rodada da
    # reconferência, R-B5: a citação anterior apontava a P&R IRPF 2026,
    # pergunta 267, que não traz essa frase);
    # decidir pelo IMPOSTO FINAL (como a versão anterior fazia) podia
    # escolher a forma de MENOR dedução em alguns casos de fronteira da
    # redução — a auditoria da rodada 1 mediu isso (achado M-1). Empate:
    # fica com o SIMPLIFICADO, por dispensar comprovação — texto de
    # `criterio_escolha_forma` gerado NO MESMO PONTO da escolha (item 7,
    # acréscimo do arquiteto-senior).
    if desconto_simplificado == deducoes_reais_total:
        forma_escolhida = "simplificado"
        pipeline_escolhido = pipeline_simplificado
        deducao_escolhida_valor = desconto_simplificado
        criterio_escolha_forma = (
            "Deduções iguais: aplicado o desconto simplificado, que dispensa comprovação."
        )
    elif desconto_simplificado > deducoes_reais_total:
        forma_escolhida = "simplificado"
        pipeline_escolhido = pipeline_simplificado
        deducao_escolhida_valor = desconto_simplificado
        criterio_escolha_forma = (
            "Aplicada a forma com maior dedução: desconto simplificado "
            f"({_fmt_reais(desconto_simplificado)}) contra deduções reais "
            f"({_fmt_reais(deducoes_reais_total)})."
        )
    else:
        forma_escolhida = "real"
        pipeline_escolhido = pipeline_real
        deducao_escolhida_valor = deducoes_reais_total
        criterio_escolha_forma = (
            "Aplicada a forma com maior dedução: deduções reais "
            f"({_fmt_reais(deducoes_reais_total)}) contra desconto simplificado "
            f"({_fmt_reais(desconto_simplificado)})."
        )

    imposto_com_exterior = pipeline_escolhido["imposto_apos_reducao"]
    imposto_sem_exterior = _imposto_sem_rendimento_exterior(
        rendimento_total,
        agregados["rendimento_exterior_sujeito"],
        deducao_escolhida_valor,
        faixas,
        reducao_cfg,
    )
    limite_exterior = _q(max(_ZERO, imposto_com_exterior - imposto_sem_exterior))

    # DE-091 item 3 (M-3) — leitura LITERAL da P&R IRPF 2026, pergunta 267:
    # só a parte do pagamento do MÊS que cabe dentro do limite do mês entra
    # no crédito disponível; o que passa do limite NUNCA compensa nem
    # carrega (perdido para o carnê-leão — só aproveitável na declaração
    # anual, fora do escopo). O saldo de meses ANTERIORES (já filtrado pelo
    # limite deles, no passado) soma-se inteiro.
    parte_compensavel_do_mes = min(agregados["imposto_pago_exterior"], limite_exterior)
    # R-B4 (reconferência): a parte do pagamento do mês que NUNCA compensa
    # (passa do limite) ficava sem rótulo próprio na memória — rotulada
    # aqui como "não compensável" (perdida para o carnê-leão; só
    # aproveitável na declaração anual, observado o limite do rendimento
    # de origem).
    imposto_exterior_nao_compensavel = _q(
        agregados["imposto_pago_exterior"] - parte_compensavel_do_mes
    )
    credito_exterior_disponivel = _q(parte_compensavel_do_mes + saldo_credito_exterior_anterior)
    compensacao_exterior = max(_ZERO, min(credito_exterior_disponivel, imposto_com_exterior))
    saldo_credito_exterior_novo = _q(credito_exterior_disponivel - compensacao_exterior)
    if mes == 12:
        saldo_credito_exterior_novo = _ZERO

    imposto_devido_no_mes = _q(imposto_com_exterior - compensacao_exterior)

    # RIR/2018, art. 938, §§ 4º e 5º (Lei 9.430/1996, art. 68): DARF de
    # imposto sobre a renda abaixo de R$ 10,00 é vedado e o valor soma aos
    # períodos seguintes do mesmo código; repetido para o carnê-leão na
    # página "Carnê-leão — pagar" da Receita (RC-131(d)). Virada do ano: HI-37.
    total_a_considerar = _q(imposto_devido_no_mes + saldo_pendente_abaixo_de_dez_anterior)
    if total_a_considerar < _LIMITE_DARF:
        valor_a_pagar = _ZERO
        saldo_pendente_novo = total_a_considerar
    else:
        valor_a_pagar = total_a_considerar
        saldo_pendente_novo = _ZERO

    # DE-092 item 2 (R-M1, correção da reconferência): o alerta de defesa
    # dispara SÓ quando o RENDIMENTO SUJEITO do mês (antes de qualquer
    # dedução) é negativo — a versão anterior comparava rendimento menos a
    # dedução ESCOLHIDA, que é negativo em quase todo mês comum (a dedução
    # normalmente supera o rendimento), disparando em 11 de 12 meses de um
    # cenário real (achado da reconferência) — alerta falso crônico que o
    # contador aprende a ignorar. Na prática, com a agregação por ORM,
    # `rendimento_total_sujeito` nunca fica negativo (nenhuma combinação de
    # lançamento e estorno, no MESMO mês, produz soma negativa); o alerta é
    # uma defesa, testada forçando o valor diretamente em `agregados` (sem
    # passar pelo ORM). Valor negativo no padrão do produto: entre
    # parênteses, sem sinal de menos (RC-90).
    alertas = []
    if rendimento_total < 0:
        alertas.append(
            f"O rendimento sujeito do mês foi negativo: ({_fmt_reais(_q(-rendimento_total))})."
        )

    # DE-092 item 1 (R-M4, correção da reconferência): imposto pago no
    # exterior num mês SEM rendimento sujeito de fonte no exterior não
    # bloqueia mais a apuração (HI-38 antiga recusava o mês inteiro, e a
    # apuração de qualquer mês encadeia desde janeiro — a recusa acabava
    # bloqueando o resto do ano-calendário inteiro, quando a Perguntas e
    # Respostas IRPF 2026 prevê justamente esse caso: pagamento em mês
    # posterior ao rendimento, compensável no mês do próprio pagamento). A
    # compensação deste pagamento específico já sai zero (a diferença entre
    # o imposto "com" e "sem" um rendimento do exterior de R$ 0,00 é
    # sempre R$ 0,00) — só falta avisar em linguagem simples.
    if agregados["imposto_pago_exterior"] > 0 and agregados["rendimento_exterior_sujeito"] <= 0:
        alertas.append(
            "Imposto pago no exterior de "
            f"{_fmt_reais(_q(agregados['imposto_pago_exterior']))} não foi "
            "compensado neste mês porque não há rendimento do exterior no mês; "
            "pode ser aproveitado na declaração anual, observado o limite do "
            "rendimento de origem (Perguntas e Respostas IRPF 2026, pergunta "
            "267)."
        )

    return {
        "ano": ano,
        "mes": mes,
        "vencimento": _vencimento_do_mes(ano, mes),
        "rendimento_total_sujeito": _q(rendimento_total),
        "rendimento_trabalho_base": _q(agregados["rendimento_trabalho_base"]),
        "rendimento_notarial_base": _q(agregados["rendimento_notarial_base"]),
        "rendimentos": _rendimentos_detalhados(agregados["por_codigo_origem"]),
        "previdencia_oficial": _q(agregados["previdencia_oficial"]),
        "pensao_alimenticia_paga": _q(agregados["pensao_paga"]),
        "dependentes_quantidade": quantidade_dependentes,
        "dependentes_valor": dependentes_valor,
        "valor_por_dependente": valor_por_dependente,
        "receita_atividade_limite_livro_caixa": _q(agregados["receita_atividade_limite"]),
        "despesa_livro_caixa_do_mes": _q(agregados["despesa_p10"]),
        "excesso_livro_caixa_anterior": _q(excesso_livro_caixa_anterior),
        "deducao_livro_caixa_aplicada": _q(deducao_livro_caixa),
        "excesso_livro_caixa_novo": excesso_livro_caixa_novo,
        "deducoes_reais_total": deducoes_reais_total,
        "desconto_simplificado": desconto_simplificado,
        "forma_escolhida": forma_escolhida,
        "deducao_aplicada": deducao_escolhida_valor,
        "criterio_escolha_forma": criterio_escolha_forma,
        "memoria_deducoes_reais": pipeline_real,
        "memoria_desconto_simplificado": pipeline_simplificado,
        "base_de_calculo": pipeline_escolhido["base"],
        "imposto_pela_tabela": pipeline_escolhido["imposto_tabela"],
        "reducao_lei_15270_2025": pipeline_escolhido["reducao_aplicada"],
        "reducao_vigente": reducao_cfg is not None,
        "imposto_apos_reducao": pipeline_escolhido["imposto_apos_reducao"],
        "imposto_com_exterior": _q(imposto_com_exterior),
        "imposto_sem_exterior": _q(imposto_sem_exterior),
        "imposto_pago_exterior_do_mes": _q(agregados["imposto_pago_exterior"]),
        "limite_compensacao_exterior": limite_exterior,
        "compensacao_exterior_aplicada": compensacao_exterior,
        "imposto_exterior_nao_compensavel": imposto_exterior_nao_compensavel,
        "saldo_credito_exterior_novo": saldo_credito_exterior_novo,
        "imposto_devido_no_mes": imposto_devido_no_mes,
        "saldo_pendente_abaixo_de_dez_anterior": _q(saldo_pendente_abaixo_de_dez_anterior),
        "valor_a_pagar": valor_a_pagar,
        "saldo_pendente_abaixo_de_dez_novo": saldo_pendente_novo,
        "alertas": alertas,
        "codigo_darf": "0190",
    }


# ---------------------------------------------------------------------------
# Camada ORM — agregação dos lançamentos e das vigências normativas,
# número de consultas CONSTANTE em relação ao número de meses/lançamentos:
# UMA consulta de lançamentos, UMA de dependentes, TRÊS de vigências
# normativas (uma por tabela) — nunca uma consulta por mês.


def _maior_vigencia_nao_posterior(vigencias_desc, referencia):
    """`vigencias_desc`: lista já ordenada por `vigencia_inicio` DESCENDENTE
    (em memória — DE-089). Devolve a primeira cujo início não é posterior a
    `referencia`, ou `None`."""
    for vigencia in vigencias_desc:
        if vigencia.vigencia_inicio <= referencia:
            return vigencia
    return None


def _lancamentos_por_mes(empresa, ano, mes_final):
    ultimo_dia = calendar.monthrange(ano, mes_final)[1]
    lancamentos = (
        LancamentoCaixa.objects.filter(
            empresa=empresa, data__gte=date(ano, 1, 1), data__lte=date(ano, mes_final, ultimo_dia)
        )
        .select_related("conta")
        .order_by("data", "id")
    )
    por_mes = defaultdict(list)
    for lancamento in lancamentos:
        por_mes[lancamento.data.month].append(lancamento)
    return por_mes


def _dependentes_por_mes(empresa, ano, mes_final):
    registros = list(
        DependentesCarneLeaoCliente.objects.filter(empresa=empresa).order_by("-competencia_inicio")
    )
    resultado = {}
    for mes in range(1, mes_final + 1):
        referencia = date(ano, mes, 1)
        aplicavel = next((r for r in registros if r.competencia_inicio <= referencia), None)
        resultado[mes] = aplicavel.quantidade if aplicavel is not None else 0
    return resultado


_PRIMEIRO_ANO_COM_TABELA = 2025

# R-B3 (reconferência): a Lei 15.270/2025, art. 8º, produz efeitos "a
# partir do mês de janeiro do ano-calendário de 2026" — a partir desta
# data, a redução é OBRIGATÓRIA (sua ausência vira erro de configuração,
# nunca leitura de "sem redução"). Ver `_apurar_ano_calendario`.
_INICIO_REDUCAO_OBRIGATORIA = date(2026, 1, 1)


def _apurar_ano_calendario(*, empresa, ano, mes_final):
    """Recalcula, do zero, janeiro a `mes_final` do `ano` pedido —
    NUNCA lê nem grava resultado (RC-130). Assume que quem CHAMA já
    verificou autorização/isolamento (mesmo limite declarado de
    `apps.contabilidade.services.apurar_balancete`/`apurar_livro_caixa`) —
    as views deste app aplicam essa verificação via
    `EmpresaEscopadaLivroCaixaMixin`/`PodeLerLivroCaixa`.
    """
    if ano < _PRIMEIRO_ANO_COM_TABELA:
        raise TabelaCarneLeaoNaoConfigurada(
            f"A apuração do carnê-leão está implementada a partir do "
            f"ano-calendário de {_PRIMEIRO_ANO_COM_TABELA} — {ano} está fora do "
            "escopo desta funcionalidade (nenhuma tabela progressiva foi "
            f"semeada para anos anteriores a {_PRIMEIRO_ANO_COM_TABELA})."
        )

    ultimo_dia_do_mes_final = calendar.monthrange(ano, mes_final)[1]
    referencia_final = date(ano, mes_final, ultimo_dia_do_mes_final)

    vigencias_tabela = list(
        VigenciaTabelaProgressivaCarneLeao.objects.filter(vigencia_inicio__lte=referencia_final)
        .order_by("-vigencia_inicio")
        .prefetch_related(
            models.Prefetch(
                "faixas", queryset=FaixaTabelaProgressivaCarneLeao.objects.order_by("ordem")
            )
        )
    )
    vigencias_reducao = list(
        VigenciaReducaoCarneLeao.objects.filter(vigencia_inicio__lte=referencia_final).order_by(
            "-vigencia_inicio"
        )
    )
    vigencias_dependente = list(
        VigenciaDependenteCarneLeao.objects.filter(vigencia_inicio__lte=referencia_final).order_by(
            "-vigencia_inicio"
        )
    )

    lancamentos_por_mes = _lancamentos_por_mes(empresa, ano, mes_final)
    dependentes_por_mes = _dependentes_por_mes(empresa, ano, mes_final)

    excesso_livro_caixa = _ZERO
    saldo_credito_exterior = _ZERO
    saldo_pendente = _ZERO
    meses = []
    for mes in range(1, mes_final + 1):
        referencia = date(ano, mes, 1)
        vig_tabela = _maior_vigencia_nao_posterior(vigencias_tabela, referencia)
        # DE-091 item 5 (M-5)/R-B3 (reconferência): vig_reducao só PODE ser
        # `None` para um mês ANTERIOR a 2026-01-01 — ausência LEGÍTIMA (Lei
        # 15.270/2025, art. 8º: "a partir do mês de janeiro do ano-
        # calendário de 2026"). A partir de 2026-01-01 a ausência é ERRO de
        # configuração normativa (falta semear a migração de dados), nunca
        # uma leitura válida de "sem redução" — a reconferência mediu que a
        # versão anterior aceitava `None` para QUALQUER mês, inclusive
        # 2026 em diante, o que geraria imposto maior em silêncio (a
        # redução, que reduziria o imposto, simplesmente não seria
        # aplicada). Ver `_reducao_bruta`.
        vig_reducao = _maior_vigencia_nao_posterior(vigencias_reducao, referencia)
        vig_dependente = _maior_vigencia_nao_posterior(vigencias_dependente, referencia)
        if vig_tabela is None or not list(vig_tabela.faixas.all()):
            raise TabelaCarneLeaoNaoConfigurada(
                f"Não há tabela progressiva do carnê-leão vigente para {mes:02d}/{ano}."
            )
        if vig_reducao is None and referencia >= _INICIO_REDUCAO_OBRIGATORIA:
            raise TabelaCarneLeaoNaoConfigurada(
                "Não há redução (Lei 15.270/2025) vigente para "
                f"{mes:02d}/{ano} — a partir de "
                f"{_INICIO_REDUCAO_OBRIGATORIA.strftime('%m/%Y')} a redução é "
                "obrigatória, e sua ausência é falha de configuração, não "
                "ausência legítima (só antes disso)."
            )
        if vig_dependente is None:
            raise TabelaCarneLeaoNaoConfigurada(
                f"Não há valor por dependente do carnê-leão vigente para {mes:02d}/{ano}."
            )

        resultado_mes = _apurar_um_mes(
            ano=ano,
            mes=mes,
            agregados=_agregados_do_mes(lancamentos_por_mes.get(mes, [])),
            quantidade_dependentes=dependentes_por_mes.get(mes, 0),
            valor_por_dependente=vig_dependente.valor_por_dependente,
            faixas=list(vig_tabela.faixas.all()),
            reducao_cfg=vig_reducao,
            percentual_desconto_simplificado=vig_tabela.percentual_desconto_simplificado,
            vigencia_tabela_inicio=vig_tabela.vigencia_inicio,
            excesso_livro_caixa_anterior=excesso_livro_caixa,
            saldo_credito_exterior_anterior=saldo_credito_exterior,
            saldo_pendente_abaixo_de_dez_anterior=saldo_pendente,
        )
        resultado_mes["tabela_vigencia_inicio"] = vig_tabela.vigencia_inicio
        resultado_mes["reducao_vigencia_inicio"] = (
            vig_reducao.vigencia_inicio if vig_reducao is not None else None
        )
        resultado_mes["dependente_vigencia_inicio"] = vig_dependente.vigencia_inicio
        meses.append(resultado_mes)

        excesso_livro_caixa = resultado_mes["excesso_livro_caixa_novo"]
        saldo_credito_exterior = resultado_mes["saldo_credito_exterior_novo"]
        saldo_pendente = resultado_mes["saldo_pendente_abaixo_de_dez_novo"]

    return {"empresa_id": empresa.id, "ano": ano, "meses": meses}


def _sob_snapshot(func, **kwargs):
    """DE-067/A5 (auditoria DL-045): leitura sob `REPEATABLE READ`, mesmo
    desenho de `apurar_balanco_patrimonial`/`_apurar_coluna_dre`
    (apps.contabilidade.services) — degrada (sem a garantia extra) quando já
    dentro de uma transação aberta, em vez de quebrar a página."""
    ja_estava_em_transacao = connection.in_atomic_block
    with transaction.atomic():
        if not ja_estava_em_transacao:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return func(**kwargs)


def apurar_carne_leao_mensal(*, empresa, ano, mes):
    """Demonstrativo do carnê-leão de UM mês, com a memória de cálculo
    completa e o encadeamento (excesso de livro-caixa, crédito do exterior,
    saldo abaixo de R$ 10,00) recalculado desde janeiro do MESMO
    ano-calendário (RC-130)."""
    resultado = _sob_snapshot(_apurar_ano_calendario, empresa=empresa, ano=ano, mes_final=mes)
    return resultado["meses"][-1]


_CAMPOS_TOTAIS_ANUAIS = (
    "rendimento_bruto",
    "deducoes_aplicadas",
    "base",
    "imposto_tabela",
    "reducao_aplicada",
    "compensacao_exterior",
    "imposto_devido",
    "valor_a_pagar",
)

# Cada nome de `_CAMPOS_TOTAIS_ANUAIS` (contrato da API, item 7/M-2 da
# DE-091) mapeado para a chave correspondente no dict de UM mês
# (`_apurar_um_mes`) — nomes DIFERENTES de propósito: o nome anual é da
# DECLARAÇÃO (rendimento bruto, base, imposto devido); o nome mensal é do
# MOTOR (rendimento_total_sujeito, base_de_calculo, imposto_devido_no_mes).
_CAMPO_ANUAL_PARA_CAMPO_MENSAL = {
    "rendimento_bruto": "rendimento_total_sujeito",
    "deducoes_aplicadas": None,  # ver abaixo — depende da forma escolhida
    "base": "base_de_calculo",
    "imposto_tabela": "imposto_pela_tabela",
    "reducao_aplicada": "reducao_lei_15270_2025",
    "compensacao_exterior": "compensacao_exterior_aplicada",
    "imposto_devido": "imposto_devido_no_mes",
    "valor_a_pagar": "valor_a_pagar",
}


def _totais_anuais(meses):
    """Soma EXATA dos 12 meses para cada um dos 8 campos do contrato da API
    (DE-091 item 7/M-2) — `Decimal` somado direto (sem novo arredondamento:
    cada parcela mensal já passou por `_q`, e soma de valores já
    arredondados a 2 casas não introduz erro de escala).

    ⚠️ **R-B5 (reconferência):** `deducoes_aplicadas` lê `deducao_aplicada`
    direto do dict de CADA mês (campo que `_apurar_um_mes` já devolve,
    desde a correção da reconferência) — antes, esta função e a TELA
    (`views_web.py`) repetiam a MESMA regra ("simplificado? desconto :
    deduções reais") cada uma na sua camada, e foi essa duplicação que
    deixou a tela sem cobertura (achado N21)."""
    totais = dict.fromkeys(_CAMPOS_TOTAIS_ANUAIS, _ZERO)
    for mes_resultado in meses:
        for campo_anual in _CAMPOS_TOTAIS_ANUAIS:
            if campo_anual == "deducoes_aplicadas":
                totais[campo_anual] += mes_resultado["deducao_aplicada"]
            else:
                totais[campo_anual] += mes_resultado[_CAMPO_ANUAL_PARA_CAMPO_MENSAL[campo_anual]]
    return {campo: _q(valor) for campo, valor in totais.items()}


def apurar_carne_leao_anual(*, empresa, ano):
    """Demonstrativo anual: os 12 meses do ano-calendário, cada um com a
    mesma estrutura de `apurar_carne_leao_mensal`, mais `totais` — a soma
    EXATA dos 12 meses dos 8 campos do contrato da API (DE-091 item 7/M-2)."""
    resultado = _sob_snapshot(_apurar_ano_calendario, empresa=empresa, ano=ano, mes_final=12)
    resultado["totais"] = _totais_anuais(resultado["meses"])
    return resultado


def registrar_dependentes_carne_leao(
    *, empresa, quantidade, competencia_inicio, criado_por=None, request=None
):
    """Registra a quantidade de dependentes vigente a partir de
    `competencia_inicio` (HI-35). Mesmo padrão de `criar_conta_livro_caixa`:
    trava a linha da EMPRESA antes de validar o modo de escrituração (N6,
    DL-046 rodada 1) para fechar a mesma corrida já corrigida naquela
    fatia."""
    with (
        transaction.atomic(),
        restricao_como_400(mensagens_de("dependentes_carne_leao_competencia_unica_por_empresa")),
    ):
        empresa_travada = Empresa.objects.select_for_update().get(pk=empresa.pk)
        try:
            recusar_se_nao_livro_caixa(empresa_travada)
        except EmpresaNaoEmModoLivroCaixa as exc:
            raise DependentesCarneLeaoInvalido(exc.mensagem) from exc

        registro = DependentesCarneLeaoCliente(
            empresa=empresa_travada,
            quantidade=quantidade,
            competencia_inicio=competencia_inicio,
            criado_por=criado_por,
        )
        try:
            registro.full_clean()
        except DjangoValidationError as exc:
            raise DependentesCarneLeaoInvalido("; ".join(exc.messages)) from exc
        # A `UniqueConstraint` residual (corrida entre duas requisições que
        # ainda não veem a linha uma da outra) é traduzida pelo
        # `restricao_como_400` do `with`, acima — mesmo padrão de
        # `registrar_regime_tributario` (apps.empresas.services).
        registro.save()
        registrar(
            acao="dependentes_carne_leao.registrado",
            usuario=criado_por,
            escritorio=empresa.escritorio,
            objeto=registro,
            request=request,
            detalhes={
                "empresa_id": empresa.id,
                "quantidade": quantidade,
                "competencia_inicio": competencia_inicio.isoformat(),
            },
        )
    return registro


def retificar_dependentes_carne_leao(registro, *, quantidade, retificado_por=None, request=None):
    """DE-091 item 6 (M-6): corrige a QUANTIDADE de um registro já
    existente de dependentes — nunca um novo registro concorrente com a
    MESMA `competencia_inicio` (a `UniqueConstraint` já recusaria isso; a
    correção é sempre sobre o registro existente). Trilha de auditoria com
    o valor ANTES e DEPOIS — mesmo espírito de RC-130 (nunca edição
    silenciosa), aplicado por analogia: `DependentesCarneLeaoCliente` não é
    um lançamento efetivado, mas alimenta diretamente o cálculo do
    carnê-leão, então a correção precisa do MESMO tipo de rastro.

    `registro` já isolado por empresa por QUEM CHAMA (mesmo padrão de
    `EstornarLancamentoCaixaView`: a view busca o objeto com
    `get_object_or_404(..., empresa=empresa)` ANTES de chamar o serviço — um
    `registro` de OUTRA empresa/escritório já vira 404 na view, antes de
    chegar aqui).

    ⚠️ **R-B6 (reconferência)**: trava também a linha da EMPRESA
    (`select_for_update`), a mesma corrida N6 que `registrar_dependentes_
    carne_leao` já fecha — sem a trava, uma troca concorrente de modo de
    escrituração (contabilidade ↔ livro-caixa) podia ler o modo ANTIGO
    entre o `Model.clean()` (que já recusa modo contabilidade) e o
    `save()` desta função."""
    with transaction.atomic():
        registro = DependentesCarneLeaoCliente.objects.select_for_update().get(pk=registro.pk)
        Empresa.objects.select_for_update().get(pk=registro.empresa_id)

        quantidade_anterior = registro.quantidade
        registro.quantidade = quantidade
        try:
            registro.full_clean()
        except DjangoValidationError as exc:
            raise DependentesCarneLeaoInvalido("; ".join(exc.messages)) from exc
        registro.save(update_fields=["quantidade"])
        registrar(
            acao="dependentes_carne_leao.retificado",
            usuario=retificado_por,
            escritorio=registro.empresa.escritorio,
            objeto=registro,
            request=request,
            detalhes={
                "empresa_id": registro.empresa_id,
                "competencia_inicio": registro.competencia_inicio.isoformat(),
                "quantidade_anterior": quantidade_anterior,
                "quantidade_nova": quantidade,
            },
        )
    return registro
