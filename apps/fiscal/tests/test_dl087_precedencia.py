"""DL-087 (frente A), precedência e resolução da sugestão — funções puras, sem banco.

Regras e itens são objetos simples (`SimpleNamespace`), com os mesmos atributos do modelo. Os
valores esperados são escritos à mão. Cobre os critérios 1 (equivalência sem regra), 2 (precedência
degrau a degrau, com as duas regras nomeadas no conflito), 3 (vigência nas duas pontas) e o ajuste
do arquiteto: pesos em potência de dois, desempate por prefixo mais longo, conflito só com natureza
diferente.
"""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.fiscal import cfop as tabela_cfop
from apps.fiscal import classificacao as cl
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.ncm_combustivel import NCM_LUBRIFICANTE

FUSO = ZoneInfo("America/Sao_Paulo")
EMPRESA = 7
OUTRA_EMPRESA = 8
NCM_DE_COMBUSTIVEL = "27101259"  # gasolina, na lista positiva
NCM_DE_CERVEJA = "22030000"  # comum: fora de combustível e de lubrificante


def nota(emissao="2026-03-15T10:00:00-03:00", **campos):
    base = {
        "modelo": "55",
        "tp_nf": "1",
        "fin_nfe": "1",
        "id_dest": "1",
        "transferencia_entre_estabelecimentos": False,
        "dh_emissao": datetime.fromisoformat(emissao),
    }
    base.update(campos)
    return SimpleNamespace(**base)


def item(cfop="5102", ncm=NCM_DE_CERVEJA, csosn="102", cst=None):
    return SimpleNamespace(cfop=cfop, ncm=ncm, csosn=csosn, cst=cst)


def regra(
    pk,
    *,
    natureza=N.REVENDA,
    cfop="5102",
    ncm="",
    ncm_modo="",
    cst_csosn="",
    id_dest="",
    empresa=None,
    tipo="saida_propria",
    inicio=date(2026, 1, 1),
    fim=None,
):
    return SimpleNamespace(
        pk=pk,
        empresa_id=empresa,
        tipo=tipo,
        cfop=cfop,
        ncm=ncm,
        ncm_modo=ncm_modo,
        cst_csosn=cst_csosn,
        id_dest=id_dest,
        crt_emitente="",
        uf_emitente="",
        cfop_entrada="",
        # Regra fake não revogada: o modelo tem este campo, e a resolução o lê (A1).
        desativada_em=None,
        natureza=natureza,
        vigencia_inicio=inicio,
        vigencia_fim=fim,
    )


def contexto(*regras, padrao=""):
    return cl.ContextoDeClassificacao(
        escritorio_id=1, empresa_id=EMPRESA, padrao_combustivel=padrao, regras=tuple(regras)
    )


# ---------------------------------------------------------------------------
# Pesos publicados (ajuste do arquiteto, item 1): potências de dois
# ---------------------------------------------------------------------------


def test_pesos_sao_potencias_de_dois_com_o_cfop_acima_de_todos():
    # DL-091 (A2): os pesos antigos foram multiplicados por quatro, e CRT e UF do emitente entraram
    # nos menores valores. A ordem entre os critérios antigos é a mesma
    # (ver `test_dl091_regras_entrada`).
    assert cl.PESOS_DE_ESPECIFICIDADE == {
        "cfop": 64,
        "ncm_exato": 32,
        "ncm_prefixo": 16,
        "cst_csosn": 8,
        "id_dest": 4,
        "uf_emitente": 2,
        "crt_emitente": 1,
    }


def test_conjuntos_distintos_de_criterios_nunca_empatam():
    """Com os pesos antigos (8, 4, 2, 2, 1) CFOP+prefixo+CST empatava com CFOP+exato+idDest (12 e 13
    empatavam em outras combinações). Com potências de dois, cada combinação tem soma própria."""
    conjuntos = []
    for ncm, modo in (("", ""), ("2710", "prefixo"), ("27101259", "exato")):
        for cst in ("", "00"):
            for id_dest in ("", "1"):
                conjuntos.append(
                    cl.especificidade(
                        regra(
                            1,
                            ncm=ncm,
                            ncm_modo=modo,
                            cst_csosn=cst,
                            id_dest=id_dest,
                        )
                    )
                )
    assert len(conjuntos) == len(set(conjuntos)) == 12


# ---------------------------------------------------------------------------
# Degraus 3 a 5: especificidade, prefixo mais longo, escopo, conflito
# ---------------------------------------------------------------------------


def test_regra_mais_especifica_vence_a_mais_generica_mesmo_de_outro_escopo():
    """Degrau 3: a do escritório com NCM exato (CFOP + NCM) vence a da empresa só com CFOP."""
    especifica = regra(1, ncm=NCM_DE_CERVEJA, ncm_modo="exato", natureza=N.REVENDA)
    generica = regra(2, empresa=EMPRESA, natureza=N.PRODUCAO_PROPRIA)
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(generica, especifica), nota(), item(), "saida_propria"
    )
    assert sugestao.natureza == N.REVENDA
    assert sugestao.regra_ids == (1,)
    assert sugestao.escopo_regra == cl.ESCOPO_ESCRITORIO


def test_prefixo_mais_longo_vence_o_mais_curto_antes_do_escopo():
    """Ajuste do arquiteto, item 2: entre prefixos que casam o mesmo item, vence o mais longo. Mesmo
    que o de prefixo curto seja da EMPRESA (que, sem o desempate, venceria pelo escopo)."""
    curto_da_empresa = regra(
        1, ncm="27", ncm_modo="prefixo", natureza=N.COMBUSTIVEL, cfop="5656", empresa=EMPRESA
    )
    longo_do_escritorio = regra(
        2, ncm="2710", ncm_modo="prefixo", natureza=N.COMBUSTIVEL_REVENDA, cfop="5656"
    )
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(curto_da_empresa, longo_do_escritorio),
        nota(),
        item(cfop="5656", ncm=NCM_DE_COMBUSTIVEL, csosn="500"),
        "saida_propria",
    )
    assert sugestao.natureza == N.COMBUSTIVEL_REVENDA
    assert sugestao.regra_ids == (2,)


def test_empate_de_especificidade_vence_o_escopo_empresa():
    do_escritorio = regra(1, natureza=N.REVENDA)
    da_empresa = regra(2, natureza=N.PRODUCAO_PROPRIA, empresa=EMPRESA)
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(do_escritorio, da_empresa), nota(), item(), "saida_propria"
    )
    assert sugestao.natureza == N.PRODUCAO_PROPRIA
    assert sugestao.escopo_regra == cl.ESCOPO_EMPRESA
    assert sugestao.regra_ids == (2,)


def test_inverter_a_precedencia_de_escopo_derruba_este_teste():
    """Mutante da lista do critério 8: se o escopo empatado perdesse para o escritório, a empresa
    (regra 2) não venceria aqui. Este teste fixa o sentido da ordem."""
    do_escritorio = regra(1, natureza=N.REVENDA)
    da_empresa = regra(2, natureza=N.PRODUCAO_PROPRIA, empresa=EMPRESA)
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(da_empresa, do_escritorio), nota(), item(), "saida_propria"
        ).natureza
        == N.PRODUCAO_PROPRIA
    )


def test_conflito_com_naturezas_diferentes_nomeia_as_duas_regras_e_nao_sugere():
    do_escritorio = regra(1, natureza=N.REVENDA)
    outra_do_escritorio = regra(2, natureza=N.PRODUCAO_PROPRIA)
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(do_escritorio, outra_do_escritorio), nota(), item(), "saida_propria"
    )
    assert sugestao.natureza is None
    assert sugestao.motivo.startswith("conflito")
    assert "regra n.º 1" in sugestao.motivo and "regra n.º 2" in sugestao.motivo
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_CONFLITO_DE_REGRAS
    assert sugestao.regra_ids == (1, 2)


def test_conflito_nao_cai_no_padrao_de_combustivel_silenciosamente():
    """Critério 8: padrão silencioso no conflito é defeito. Com padrão 'posto' e NCM de combustível,
    a
    embutida daria 'combustivel'; o conflito de regras precisa continuar sem sugestão."""
    a = regra(1, natureza=N.REVENDA, cfop="5656")
    b = regra(2, natureza=N.PRODUCAO_PROPRIA, cfop="5656")
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(a, b, padrao="posto"),
        nota(),
        item(cfop="5656", ncm=NCM_DE_COMBUSTIVEL, csosn="500"),
        "saida_propria",
    )
    assert sugestao.natureza is None
    assert sugestao.motivo.startswith("conflito")


def test_mesma_natureza_em_regras_de_mesma_precedencia_nao_e_conflito():
    """Ajuste do arquiteto, item 3: duas regras de mesma precedência com a MESMA natureza dão a
    sugestão, e o motivo nomeia as duas. Não é conflito."""
    a = regra(1, natureza=N.REVENDA)
    b = regra(2, natureza=N.REVENDA)
    sugestao = cl.sugerir_natureza_com_regras(contexto(a, b), nota(), item(), "saida_propria")
    assert sugestao.natureza == N.REVENDA
    assert not sugestao.motivo.startswith("conflito")
    assert "regra n.º 1" in sugestao.motivo and "regra n.º 2" in sugestao.motivo
    assert "não é conflito" in sugestao.motivo


# ---------------------------------------------------------------------------
# Passo 1 e 2: ajuste, CFOP fora da tabela, natureza que não cabe no tipo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fin", ["2", "3", "5", "6"])
def test_nota_de_ajuste_nunca_recebe_regra(fin):
    qualquer = regra(1, natureza=N.REVENDA, cfop="5102")
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(qualquer), nota(fin_nfe=fin), item(), "ajuste"
    )
    assert sugestao.natureza == N.AJUSTE
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PRODUTO


def test_cfop_fora_da_tabela_segue_a_embutida_sem_regra():
    qualquer = regra(1, natureza=N.REVENDA, cfop="5102")
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(qualquer), nota(), item(cfop="5000"), "saida_propria"
    )
    assert sugestao.natureza is None
    assert "a classificar" in sugestao.motivo
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PRODUTO


def test_regra_com_natureza_que_nao_cabe_no_tipo_nao_vale_e_o_motivo_diz_isso():
    """Passo 2: natureza de devolução numa regra de saída não casa. Se é o único candidato, o motivo
    diz por que a regra não valeu, e a sugestão é a embutida."""
    incompativel = regra(9, natureza=N.DEVOLUCAO_VENDA, cfop="5102")
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(incompativel), nota(), item(), "saida_propria"
    )
    assert sugestao.natureza == N.REVENDA  # a embutida de 5102 com CSOSN 102
    assert "regra n.º 9" in sugestao.motivo
    assert "não vale" in sugestao.motivo
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PRODUTO


def test_regra_incompativel_ao_lado_de_uma_valida_so_perde_sem_aviso():
    incompativel = regra(9, natureza=N.DEVOLUCAO_VENDA, cfop="5102", ncm="", ncm_modo="")
    valida = regra(2, natureza=N.PRODUCAO_PROPRIA, cfop="5102")
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(incompativel, valida), nota(), item(), "saida_propria"
    )
    assert sugestao.natureza == N.PRODUCAO_PROPRIA
    assert sugestao.regra_ids == (2,)


# ---------------------------------------------------------------------------
# Critério 3: vigência nas duas pontas, contra a DATA DE EMISSÃO
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("emissao", "casa"),
    [
        ("2026-03-09T23:59:59-03:00", False),  # um dia antes do início
        ("2026-03-10T00:00:00-03:00", True),  # início (inclusive)
        ("2026-03-20T23:59:59-03:00", True),  # fim (inclusive)
        ("2026-03-21T00:00:00-03:00", False),  # um dia depois do fim
    ],
)
def test_vigencia_vale_pela_data_de_emissao_nas_duas_pontas(emissao, casa):
    vigente = regra(1, natureza=N.PRODUCAO_PROPRIA, inicio=date(2026, 3, 10), fim=date(2026, 3, 20))
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(vigente), nota(emissao=emissao), item(), "saida_propria"
    )
    assert (sugestao.origem == servico.ORIGEM_DA_SUGESTAO_REGRA) is casa


def test_data_de_emissao_no_fuso_de_sao_paulo_decide_o_dia():
    """23:30 em São Paulo é 02:30 do dia seguinte em UTC. A vigência vale o dia de SP."""
    vigente = regra(1, natureza=N.PRODUCAO_PROPRIA, inicio=date(2026, 3, 10), fim=date(2026, 3, 10))
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(vigente),
        nota(emissao="2026-03-10T23:30:00-03:00"),
        item(),
        "saida_propria",
    )
    assert sugestao.natureza == N.PRODUCAO_PROPRIA
    assert datetime(2026, 3, 10, 23, 30, tzinfo=FUSO).date() == date(2026, 3, 10)


def test_vigencia_vazia_depois_de_desativar_nunca_casa():
    """Regra desativada hoje tem fim em ontem; se tinha início hoje, a vigência é vazia."""
    vazia = regra(1, natureza=N.PRODUCAO_PROPRIA, inicio=date(2026, 3, 15), fim=date(2026, 3, 14))
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(vazia), nota(emissao="2026-03-15T10:00:00-03:00"), item(), "saida_propria"
    )
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PRODUTO


# ---------------------------------------------------------------------------
# Critérios: CFOP, NCM (exato e prefixo), CST/CSOSN como está na nota, idDest, empresa
# ---------------------------------------------------------------------------


def test_ncm_exato_so_casa_o_ncm_inteiro_e_prefixo_casa_o_comeco():
    exato = regra(1, natureza=N.PRODUCAO_PROPRIA, ncm="27101259", ncm_modo="exato")
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(exato), nota(), item(ncm="2710.12.59"), "saida_propria"
        ).natureza
        == N.PRODUCAO_PROPRIA
    )
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(exato), nota(), item(ncm="27101260"), "saida_propria"
        ).origem
        == servico.ORIGEM_DA_SUGESTAO_PRODUTO
    )
    prefixo = regra(2, natureza=N.PRODUCAO_PROPRIA, ncm="2710", ncm_modo="prefixo")
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(prefixo), nota(), item(ncm="27101260"), "saida_propria"
        ).natureza
        == N.PRODUCAO_PROPRIA
    )


def test_cst_csosn_compara_o_codigo_como_esta_na_nota():
    regra_csosn = regra(1, natureza=N.PRODUCAO_PROPRIA, cst_csosn="102")
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(regra_csosn), nota(), item(csosn="102"), "saida_propria"
        ).natureza
        == N.PRODUCAO_PROPRIA
    )
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(regra_csosn), nota(), item(csosn="500"), "saida_propria"
        ).origem
        == servico.ORIGEM_DA_SUGESTAO_PRODUTO
    )


def test_id_dest_limita_a_regra_ao_destino_da_nota():
    so_interna = regra(1, natureza=N.PRODUCAO_PROPRIA, id_dest="1")
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(so_interna), nota(id_dest="1"), item(), "saida_propria"
        ).natureza
        == N.PRODUCAO_PROPRIA
    )
    assert (
        cl.sugerir_natureza_com_regras(
            contexto(so_interna), nota(id_dest="2"), item(), "saida_propria"
        ).origem
        == servico.ORIGEM_DA_SUGESTAO_PRODUTO
    )


def test_regra_de_outra_empresa_nao_casa_mesmo_sendo_do_mesmo_escritorio():
    """Isolamento: a regra de OUTRA empresa não entra no contexto desta (o filtro é na carga); e,
    mesmo que entrasse, a checagem de escopo a recusa."""
    da_outra = regra(1, natureza=N.PRODUCAO_PROPRIA, empresa=OUTRA_EMPRESA)
    sugestao = cl.sugerir_natureza_com_regras(contexto(da_outra), nota(), item(), "saida_propria")
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PRODUTO


def test_tipo_da_regra_precisa_ser_o_tipo_da_nota():
    devolucao = regra(1, natureza=N.DEVOLUCAO_VENDA, tipo="devolucao", cfop="5102")
    sugestao = cl.sugerir_natureza_com_regras(contexto(devolucao), nota(), item(), "saida_propria")
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PRODUTO


# ---------------------------------------------------------------------------
# Critério 1: sem regra cadastrada, nada muda (equivalência com sugerir_natureza_com_padrao)
# ---------------------------------------------------------------------------

_NCMS = (NCM_DE_COMBUSTIVEL, sorted(NCM_LUBRIFICANTE)[0], NCM_DE_CERVEJA)
_CSTS = (
    ("500", None),  # ICMS já recolhido (CSOSN 500)
    ("201", None),  # substituto (CSOSN 201)
    ("102", None),  # comum (CSOSN 102)
    (None, "60"),  # ICMS já recolhido (CST 60)
)
_TABELA_CFOP = tuple(sorted(tabela_cfop._tabela()))


@pytest.mark.parametrize("padrao", ["", "posto"])
def test_sem_regra_a_resolucao_e_igual_a_sugerir_natureza_com_padrao(padrao):
    """Critério 1: para todo CFOP da tabela oficial × NCM (combustível, lubrificante, comum) × CST
    ou
    CSOSN (ST e comum) × idDest (1 e 3) × tipo (saída e devolução), sem regra, a resolução nova dá
    exatamente a mesma sugestão (natureza, motivo) que `sugerir_natureza_com_padrao`."""
    vazio = contexto(padrao=padrao)
    comparados = 0
    for cfop_codigo in _TABELA_CFOP:
        for ncm in _NCMS:
            for csosn, cst in _CSTS:
                for id_dest in ("1", "3"):
                    for fin, tipo in (("1", "saida_propria"), ("4", "devolucao")):
                        documento = nota(
                            fin_nfe=fin, tp_nf="1" if fin == "1" else "0", id_dest=id_dest
                        )
                        it = item(cfop=cfop_codigo, ncm=ncm, csosn=csosn, cst=cst)
                        esperado = servico.sugerir_natureza_com_padrao(documento, it, padrao, tipo)
                        obtido = cl.sugerir_natureza_com_regras(vazio, documento, it, tipo)
                        assert obtido.natureza == esperado.natureza, (cfop_codigo, ncm, csosn, cst)
                        assert obtido.motivo == esperado.motivo, (cfop_codigo, ncm, csosn, cst)
                        assert obtido.origem in (
                            servico.ORIGEM_DA_SUGESTAO_PRODUTO,
                            servico.ORIGEM_DA_SUGESTAO_PADRAO,
                        )
                        comparados += 1
    assert comparados == len(_TABELA_CFOP) * 3 * 4 * 2 * 2


def test_origem_da_sugestao_do_padrao_e_gravada_como_padrao():
    sugestao = cl.sugerir_natureza_com_regras(
        contexto(padrao="posto"),
        nota(),
        item(cfop="5949", ncm=NCM_DE_COMBUSTIVEL, csosn="102"),
        "saida_propria",
    )
    assert sugestao.natureza == N.COMBUSTIVEL
    assert sugestao.origem == servico.ORIGEM_DA_SUGESTAO_PADRAO


def test_fonte_da_sugestao_so_existe_com_regra():
    """A assinatura do lote só muda para quem tem regra: sem regra, a fonte é vazia."""
    com_regra = cl.sugerir_natureza_com_regras(
        contexto(regra(4, natureza=N.REVENDA)), nota(), item(), "saida_propria"
    )
    sem_regra = cl.sugerir_natureza_com_regras(contexto(), nota(), item(), "saida_propria")
    assert cl.fonte_da_sugestao(com_regra) == "regra:4"
    assert cl.fonte_da_sugestao(sem_regra) == ""


def test_origem_confirmada_diz_de_onde_veio_a_natureza():
    com_regra = cl.sugerir_natureza_com_regras(
        contexto(regra(4, natureza=N.REVENDA)), nota(), item(), "saida_propria"
    )
    assert cl.origem_da_confirmacao(com_regra, N.REVENDA) == ("regra", 4)
    assert cl.origem_da_confirmacao(com_regra, N.PRODUCAO_PROPRIA) == ("manual", None)
    produto = cl.sugerir_natureza_com_regras(contexto(), nota(), item(), "saida_propria")
    assert cl.origem_da_confirmacao(produto, N.REVENDA) == ("produto", None)
    sem_sugestao = cl.sugerir_natureza_com_regras(
        contexto(), nota(), item(cfop="5000"), "saida_propria"
    )
    assert cl.origem_da_confirmacao(sem_sugestao, N.REVENDA) == ("manual", None)


# ---------------------------------------------------------------------------
# Regras do produto (só leitura) e pesos publicados
# ---------------------------------------------------------------------------


def test_regras_do_produto_tem_sinal_resultado_e_fonte_em_cada_linha():
    assert len(cl.REGRAS_DO_PRODUTO) >= 25
    for linha in cl.REGRAS_DO_PRODUTO:
        assert linha["sinal"].strip(), linha
        assert linha["resultado"].strip(), linha
        assert linha["fonte"].strip(), linha
