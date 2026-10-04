"""DL-062 — o sinal da conta-RAIZ retificadora no Balanço Patrimonial
(BL-604). Cada teste aqui REPROVA sem a correção e passa com ela.

**O defeito:** o sinal do saldo vem da natureza da conta que o consolida
(regra única de saldo, DE-020). A retificadora aninhada ("(-) Prejuízos
Acumulados", "(-) Ações em Tesouraria") herda o sinal do GRUPO e sai
correta; cadastrada como RAIZ — `conta_pai is None`, sem ancestral do
grupo — não há grupo que aplique a natureza credora do PL, e a natureza
DEVEDORA dela assinava o próprio saldo: o Balanço SOMAVA o que devia
SUBTRAIR. Medido em 04/10/2026: PL = 117.000,00 quando o correto é
113.000,00, a equação `ativo = passivo + PL` fechava em −4.000,00 e
`avaliar_emissao_do_balanco` devolvia `pode_emitir = True` — o Balanço
sai para o cliente errado sem veto nenhum.

**A correção** é a MESMA normalização de sinal que a função já aplicava,
dois blocos abaixo, à soma por classificação (BL-496) e que a DRE aplica
ao resíduo por tipo: a contribuição de uma RAIZ entra com o sinal da
natureza NATURAL do seu `TipoConta`, nunca com o da natureza cadastrada
da própria conta.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.models import (
    NATUREZA_NATURAL_DO_TIPO,
    NATUREZA_NATURAL_DO_TIPO_DRE,
    NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO,
    ClassificacaoPatrimonial,
    Conta,
    NaturezaConta,
    TipoConta,
)
from apps.contabilidade.services import (
    TIPO_DA_CLASSIFICACAO_PATRIMONIAL,
    apurar_dmpl,
    apurar_saldos,
    avaliar_emissao_da_dmpl,
    avaliar_emissao_do_balanco,
    criar_lancamento,
)
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    COL,
    MES,
    PL,
    C,
    D,
    _caso_a,
    _conta,
    _empresa,
    _lancar,
    _plano_basico,
)

pytestmark = pytest.mark.django_db

# PL do caso A, conferido na tabela do plano da DL-061: capital 100.000,00 +
# reserva legal 1.250,00 + lucros acumulados 13.750,00 (25.000,00 − 1.250,00
# de reserva − 10.000,00 de dividendos).
PL_DO_CASO_A = Decimal("115000.00")
# Menos a ação em tesouraria de 2.000,00 — o valor que o Balanço tem de
# publicar depois da correção. Antes dela, o Balanço publicava 117.000,00.
PL_COM_TESOURARIA = Decimal("113000.00")


def _caso_com_retificadora_solta_na_raiz():
    """O caso A **mais** a conta que reproduce o BL-604: "9 Ações em
    tesouraria", tipo PL, natureza DEVEDORA, `conta_pai is None` (raiz),
    classificada na coluna redutora da DMPL, com 2.000,00 de débito contra
    Caixa. `_conta` passa a conta por `full_clean()` — o cadastro aceita,
    porque a topologia é válida no modelo; o defeito é do Balanço."""
    empresa, contas, _ = _caso_a()
    tesouraria = _conta(
        empresa,
        "9",
        "Ações em tesouraria",
        PL,
        D,
        dmpl=COL.ACOES_OU_QUOTAS_EM_TESOURARIA,
    )
    assert tesouraria.conta_pai_id is None, "a conta tem de ser RAIZ — é o defeito"
    _lancar(
        empresa,
        date(ANO, MES, 20),
        "Compra de ações em tesouraria",
        tesouraria,
        contas["caixa"],
        "2000.00",
    )
    return empresa, contas, tesouraria


# ---------------------------------------------------------------------------
# Critérios 1 e 2 — o número e a equação
# ---------------------------------------------------------------------------


def test_retificadora_de_pl_na_raiz_subtrai_do_total_do_balanco():
    """Critério 1. Reprova antes da correção: PL = 117.000,00."""
    empresa, _, _ = _caso_com_retificadora_solta_na_raiz()

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    pl = saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO]
    assert pl == PL_COM_TESOURARIA, "a raiz devedora tem de REDUZIR o PL"
    # A soma ingênua, que ignora a natureza natural do tipo: existe para o
    # teste distinguir "corrigiu" de "inverteu o sinal inteiro" (espelha o
    # `!= Decimal("1080.00")` de `test_retificadora_dentro_do_patrimonio_...`).
    assert pl != PL_DO_CASO_A + Decimal("2000.00")


def test_equacao_deixa_de_desbalancar_com_retificadora_de_pl_na_raiz():
    """Critério 2. Reprova antes da correção: `diferenca` = −4.000,00.

    A equação `ativo = passivo + PL + resultado` é o "momento da verdade"
    do módulo (`services.py`); o Balanço que não fecha é documento que não
    pode sair."""
    empresa, _, _ = _caso_com_retificadora_solta_na_raiz()

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    equacao = saldos["equacao"]
    assert equacao["diferenca"] == Decimal("0.00")
    assert (
        equacao["ativo"]
        == equacao["passivo"] + equacao["patrimonio_liquido"] + equacao["resultado_nao_transferido"]
    )


# ---------------------------------------------------------------------------
# Critério 4 — a correção é do NÚMERO, não um veto novo
# ---------------------------------------------------------------------------


def test_o_balanco_continua_emitivel_e_o_pl_entra_correto():
    """Critério 4. Antes da correção o Balanço também emitia — com o PL
    errado. Ele tem de continuar emitindo, agora com o número certo: a
    etapa não trocou "documento errado" por "recusa sem motivo"."""
    empresa, contas, _ = _caso_com_retificadora_solta_na_raiz()
    # Classifica o circulante/não circulante, senão o Balanço veta por lista
    # de cobertura e o teste não mediria o que diz medir.
    for conta, classificacao in (
        (contas["caixa"], ClassificacaoPatrimonial.ATIVO_CIRCULANTE),
        (contas["imobilizado"], ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO),
        (contas["dividendos"], ClassificacaoPatrimonial.PASSIVO_CIRCULANTE),
    ):
        Conta.objects.filter(pk=conta.pk).update(classificacao_patrimonial=classificacao)

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))
    emissao = avaliar_emissao_do_balanco(saldos)

    assert emissao["pode_emitir"] is True
    assert emissao["residuo_pendente"] == {}
    assert emissao["listas_pendentes"] == {}
    assert saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO] == PL_COM_TESOURARIA


# ---------------------------------------------------------------------------
# Critério 5 — o defeito FECHADO, não só o número mudado
# ---------------------------------------------------------------------------


def test_a_dmpl_passa_a_ser_aprovada_com_a_retificadora_solta_na_raiz():
    """Critério 5. Reprova antes da correção: `pode_emitir` False por
    "Diferença entre a DMPL e o Balanço".

    Este é o teste que prova que o defeito está FECHADO — a DMPL é a
    segunda leitura das mesmas contas, e ela passa a concordar com o
    Balanço justamente no caso em que discordava."""
    empresa, _, _ = _caso_com_retificadora_solta_na_raiz()

    dmpl = apurar_dmpl(empresa=empresa, ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dmpl(dmpl)

    assert dmpl["pendencias"]["diferenca_de_fechamento"] == []
    assert emissao["pode_emitir"] is True


# ---------------------------------------------------------------------------
# Critério 3 — é a CLASSE, não o caso do PL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "nome", "tipo", "natureza"),
    [
        ("9", "Ações em tesouraria", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.DEVEDORA),
        ("4.9", "(-) Devoluções de Vendas", TipoConta.RECEITA, NaturezaConta.DEVEDORA),
        ("5.9", "(-) Descontos Obtidos", TipoConta.DESPESA, NaturezaConta.CREDORA),
    ],
    ids=["pl", "receita", "despesa"],
)
def test_raiz_com_natureza_oposta_a_do_tipo_subtrai(codigo, nome, tipo, natureza):
    """Critério 3. Uma RAIZ cuja natureza é a OPOSTA da natural do seu tipo
    é uma retificadora por definição — e subtrai. Os três tipos falhavam do
    mesmo jeito (medido: equação em −200,00 com os três juntos)."""
    empresa = _empresa(f"Empresa {tipo}")
    caixa = _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)
    retificadora = _conta(empresa, codigo, nome, tipo, natureza)

    criar_lancamento(
        empresa=empresa,
        data=date(ANO, MES, 10),
        historico="Movimento da retificadora",
        itens=[
            {
                "conta": retificadora,
                "tipo": "debito" if natureza == NaturezaConta.DEVEDORA else "credito",
                "valor": "100.00",
            },
            {
                "conta": caixa,
                "tipo": "credito" if natureza == NaturezaConta.DEVEDORA else "debito",
                "valor": "100.00",
            },
        ],
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    assert saldos["totais_por_tipo"][tipo] == Decimal("-100.00"), (
        f"a raiz {tipo} de natureza {natureza} tem de entrar com sinal invertido"
    )
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# Critério 6 — CONTROLE POSITIVO: a árvore bem montada não se move
# ---------------------------------------------------------------------------


def test_a_retificadora_aninhada_continua_subtraindo_do_grupo():
    """Critério 6, e o teste que mais importa: sem ele a suíte não
    distingue "corrigiu a raiz retificadora" de "inverteu o sinal de tudo".

    `test_retificadora_dentro_do_patrimonio_liquido_subtrai_nunca_soma`
    (`test_dl032_camada_de_saldos.py`) é o caso aninhado, com o valor 920,00
    conferido. Aqui a prova equivalente roda no cenário da DMPL, onde a
    retificadora "3.4 (-) Prejuízos Acumulados" tem pai de tipo PL: a
    normalização tem de ser no-op e o PL sai inteiro."""
    empresa = _empresa("Empresa aninhada")
    plano = _plano_basico(empresa)
    grupo_pl = plano["pl"]
    assert grupo_pl.natureza == C, "o grupo do PL é credor — é ele que dá o sinal"

    retificadora = _conta(
        empresa,
        "3.9",
        "(-) Prejuízos Acumulados",
        PL,
        NaturezaConta.DEVEDORA,
        pai=grupo_pl,
    )
    criar_lancamento(
        empresa=empresa,
        data=date(ANO, MES, 10),
        historico="Reconhecimento de prejuízo",
        itens=[
            {"conta": retificadora, "tipo": "debito", "valor": "500.00"},
            {"conta": plano["caixa"], "tipo": "credito", "valor": "500.00"},
        ],
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    # A retificadora aninhada REDUZ o grupo: −500,00, nunca +500,00.
    assert saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO] == Decimal("-500.00")
    assert saldos["contas_retificadoras_rais"] == [], (
        "conta aninhada não é raiz: a lista de retificadoras de raiz fica vazia"
    )


# ---------------------------------------------------------------------------
# Critério 7 — a anomalia é DECLARADA, e avisa sem impedir
# ---------------------------------------------------------------------------


def test_a_raiz_retificadora_e_nomeada_e_so_avisa():
    """Critério 7. A soma deixou de ser ingênua, então o produto tem de
    dizer que mexeu: nomeia a conta, com o saldo e a contribuição, em lista
    INFORMATIVA — depois da correção o número está certo e a topologia é
    apenas incomum."""
    empresa, _, tesouraria = _caso_com_retificadora_solta_na_raiz()

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    nomeadas = saldos["contas_retificadoras_rais"]
    assert len(nomeadas) == 1
    achada = nomeadas[0]
    assert achada["conta"] == tesouraria.codigo
    assert achada["tipo"] == TipoConta.PATRIMONIO_LIQUIDO
    assert achada["natureza"] == NaturezaConta.DEVEDORA
    assert achada["natureza_natural_do_tipo"] == NaturezaConta.CREDORA
    # O VALOR não vai na lista (achado A2 da auditoria): ele já está
    # impresso na linha da conta, e a tela mostraria um Decimal cru.
    assert set(achada) == {
        "conta",
        "nome",
        "tipo",
        "natureza",
        "natureza_natural_do_tipo",
    }


def test_a_lista_de_retificadoras_avisa_sem_impedir_a_emissao():
    """Critério 7, segunda metade: a lista é INFORMATIVA. Um plano de
    contas com a retificadora na raiz é incomum, não errado — vetar o
    Balanço agora bloquearia um documento CORRETO."""
    empresa, contas, _ = _caso_com_retificadora_solta_na_raiz()
    for conta, classificacao in (
        (contas["caixa"], ClassificacaoPatrimonial.ATIVO_CIRCULANTE),
        (contas["imobilizado"], ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO),
        (contas["dividendos"], ClassificacaoPatrimonial.PASSIVO_CIRCULANTE),
    ):
        Conta.objects.filter(pk=conta.pk).update(classificacao_patrimonial=classificacao)

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))
    emissao = avaliar_emissao_do_balanco(saldos)

    assert emissao["pode_emitir"] is True
    assert "contas_retificadoras_rais" in emissao["listas_informativas"]
    assert "contas_retificadoras_rais" not in emissao["listas_pendentes"]


# ---------------------------------------------------------------------------
# Critério 4 / D6 e achado A7 da auditoria — o BALANÇO IMPRESSO fecha
# ---------------------------------------------------------------------------


def test_a_seccao_impressa_do_pl_fecha_com_a_retificadora_na_raiz():
    """**O número que o contador lê no papel.**

    A correção mexe no TOTAL, e o risco real do plano ("corrige o total e
    não a linha") só aparece na MONTAGEM IMPRESSA: se a linha da conta
    continuasse exibindo o valor com o sinal da natureza cadastrada e o
    subtotal com o da natural, o documento mostraria duas verdades. Aqui as
    duas peças são montadas de verdade e comparadas.

    A CONVENÇÃO impressa é valor absoluto + letra D/C (RC-61/BL-77), e ela
    é o que torna a conta de dedução legível sem número negativo: o grupo
    aparece como "115.000,00 C", a retificadora como "2.000,00 D", e o
    subtotal como "113.000,00 C" — que é a subtração contábil, escrita do
    jeito que o contador confere no papel.

    A auditoria mediu este mesmo cenário na tela real (achado A7: não havia
    guarda); este teste é a guarda, e roda sem navegador."""
    from apps.contabilidade.views_web import _montar_grupos_do_balanco

    empresa, _, _ = _caso_com_retificadora_solta_na_raiz()
    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    grupos = _montar_grupos_do_balanco(saldos)
    pl = grupos["patrimonio_liquido"]

    linha_do_grupo = next(linha for linha in pl["linhas"] if linha["codigo"] == "3")
    linha_da_tesouraria = next(linha for linha in pl["linhas"] if linha["codigo"] == "9")

    assert linha_do_grupo["saldo_ptbr"] == "115.000,00"
    assert linha_do_grupo["saldo_natureza"]["letra"] == "C"
    # A dedução: valor POSITIVO, com a letra que diz que é devedora. Nunca
    # um "-2.000,00" — a convenção do módulo é letra, não sinal.
    assert linha_da_tesouraria["saldo_ptbr"] == "2.000,00"
    assert linha_da_tesouraria["saldo_natureza"]["letra"] == "D"
    assert not linha_da_tesouraria["saldo_ptbr"].startswith("-"), "nunca negativo"

    # E o subtotal é a subtração, não a soma ingênua.
    assert pl["subtotal"]["valor_ptbr"] == "113.000,00"
    assert pl["subtotal"]["natureza"]["letra"] == "C"
    assert pl["subtotal"]["valor_ptbr"] != "117.000,00", "a soma ingênua saía antes"


def test_o_grande_total_impresso_do_ativo_bate_com_o_passivo_e_pl():
    """A mesma montagem, conferindo a EQUAÇÃO no documento impresso — que é
    como o contador a verifica no papel, sem somar na mão."""
    from apps.contabilidade.views_web import _montar_grupos_do_balanco

    empresa, _, _ = _caso_com_retificadora_solta_na_raiz()
    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    grupos = _montar_grupos_do_balanco(saldos)

    assert grupos["total_ativo"]["valor_ptbr"] == "123.000,00"
    assert grupos["total_passivo_e_pl"]["valor_ptbr"] == "123.000,00"


def test_o_subtotal_impresso_usa_o_mapa_e_nao_um_ternario_proprio():
    """Achado A5 da auditoria: o subtotal usava `DEVEDORA se ATIVO senão
    CREDORA`, uma SEGUNDA fonte de verdade para o mesmo sinal — hoje em
    acordo com o mapa, e por isso invisível, mas um `TipoConta` novo cairia
    no ternário como CREDORA sem ninguém perceber. Este teste fixa que a
    apresentação e a apuração leem o MESMO mapa, e cobre TODOS os tipos —
    inclusive os que o Balanço ainda não imprime (Receita, Despesa), que é
    justamente onde os dois caminhos divergiriam."""
    from apps.contabilidade.views_web import _subtotal_do_balanco

    for tipo in TipoConta.values:
        natural = NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO[tipo]
        esperado = "devedora" if natural == NaturezaConta.DEVEDORA else "credora"
        assert _subtotal_do_balanco(Decimal("100.00"), tipo)["natureza_esperada"] == esperado


# ---------------------------------------------------------------------------
# Achado A2 da auditoria — a lista nomeia o que ACONTECEU, não o que poderia
# ---------------------------------------------------------------------------


def test_raiz_retificadora_com_saldo_zero_nao_gera_aviso():
    """A2: a lista declarava a raiz retificadora mesmo com saldo ZERO,
    gerando aviso permanente e afirmando um "sinal invertido" que não
    ocorreu (inverter zero é zero). Aqui a conta existe, é raiz e tem
    natureza oposta à do tipo — mas não foi movimentada, e não há o que
    declarar."""
    empresa = _empresa("Empresa sem movimento")
    _plano_basico(empresa)
    _conta(
        empresa,
        "9",
        "Ações em tesouraria (sem movimento)",
        PL,
        D,
        dmpl=COL.ACOES_OU_QUOTAS_EM_TESOURARIA,
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(ANO, MES, 31))

    assert saldos["contas_retificadoras_rais"] == []


# ---------------------------------------------------------------------------
# Achado A1 da auditoria — a lista nova tem NOME HUMANO e AÇÃO na tela
# ---------------------------------------------------------------------------


def test_a_lista_nova_tem_nome_humano_e_acao_na_tela():
    """A1: sem registro, a tela mostrava o nome cru da lista e a ação
    "Ação não cadastrada para a pendência … avise o suporte". O contrato
    BL-508, escrito no mesmo arquivo, exige nome humano E ação que resolve
    para toda lista declarada — inclusive as informativas."""
    from apps.contabilidade.views_web import (
        ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA,
        NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO,
    )

    assert "contas_retificadoras_rais" in NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO
    assert "contas_retificadoras_rais" in ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA
    # A ação da lista informativa não pode mandar "corrigir": o número do
    # Balanço já está certo, e uma ação imperativa seria instrução falsa.
    acao = ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA["contas_retificadoras_rais"]
    assert "Nada precisa ser corrigido para emitir" in acao


# ---------------------------------------------------------------------------
# Critérios 8 e 9 — testes DERIVADOS dos mapas
# ---------------------------------------------------------------------------


def test_o_mapa_do_total_cobre_exatamente_os_tipos_do_modelo():
    """Critério 8. Um `TipoConta` novo tem de aparecer no mapa com o lado
    natural que a contabilidade manda, em vez de ficar de fora em silêncio
    (o defeito que o projeto já pagou caro com `TipoConta` — DE-056)."""
    assert set(NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO.keys()) == set(TipoConta.values)


def test_o_lado_natural_de_cada_tipo_e_o_da_equacao_contabil():
    """Critério 8, com os valores — pelo motivo de cada um deles."""
    assert NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO == {
        TipoConta.ATIVO: NaturezaConta.DEVEDORA,
        TipoConta.PASSIVO: NaturezaConta.CREDORA,
        TipoConta.PATRIMONIO_LIQUIDO: NaturezaConta.CREDORA,
        TipoConta.RECEITA: NaturezaConta.CREDORA,
        TipoConta.DESPESA: NaturezaConta.DEVEDORA,
    }


def test_o_mapa_novo_nao_altera_os_outros_dois_mapas():
    """Critério 9. Os três mapas respondem a perguntas diferentes e cada um
    tem seu teste derivado; o novo não pode absorver nenhum dos dois
    antigos — `NATUREZA_NATURAL_DO_TIPO` é escopado à classificação
    circulante/não circulante, e `NATUREZA_NATURAL_DO_TIPO_DRE`, ao resíduo
    da DRE."""
    assert set(NATUREZA_NATURAL_DO_TIPO.keys()) == set(TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values())
    assert set(NATUREZA_NATURAL_DO_TIPO_DRE.keys()) == {
        TipoConta.RECEITA,
        TipoConta.DESPESA,
    }
    assert NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO is not NATUREZA_NATURAL_DO_TIPO
