"""DL-061, fatia 1 (servidor) — a Demonstração das Mutações do Patrimônio
Líquido (DMPL, CTB-14 da DL-048): o campo `Conta.classificacao_dmpl`, a
apuração (`apurar_dmpl`), a decisão de emissão (`avaliar_emissao_da_dmpl`), a
porta de gravação (`classificar_conta_na_dmpl`), a norma por vigência
(`norma_das_demonstracoes`) e a marca de adoção antecipada da NBC TG 51.

Cobre os critérios de aceite 1, 2, 3, 4, 5, 8 e 9 do plano
(docs/planos/DL-061-dmpl.md); a tela, as permissões HTTP (critério 7) e a
medição no navegador (critério 6) são da fatia do `especialista-frontend`.

- 1: casos A e B do plano, calculados à mão, por lançamentos reais e
  `zerar_resultado`;
- 2: a coluna de lucros acumulados é IDÊNTICA à DLPA (saldo inicial, cada
  evento, saldo final) no cenário da DLPA e nos casos A e B;
- 3: conciliação por coluna e do total com o Balanço; a divergência veta e
  NOMEIA a coluna;
- 4: cada pendência que veta, uma a uma;
- 5: norma citada nas três situações;
- 8: isolamento entre empresas nos dois sentidos;
- 9: `Decimal` em todo o cálculo.

Toda regra tem um teste que derrubaria uma mutação plausível dela (direção
da tesouraria, orientação do par de colunas, âncora de lucros acumulados,
limite de 01/01/2027…). Dados 100% sintéticos, criados nos próprios testes.
Datas em 2026, no passado (hoje é 2026-10-01); exercício = ano civil (HI-28).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA,
    GRUPO_DA_CLASSIFICACAO_DMPL,
    RESERVAS_DE_LUCROS_DA_DLPA,
    RESERVAS_DE_LUCROS_DA_DMPL,
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL,
    ClassificacaoDlpa,
    ClassificacaoDmpl,
    Conta,
    GrupoDaDmpl,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    _LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO,
    _TITULOS_DAS_LINHAS_DA_DMPL,
    ParametroContabilInvalido,
    apurar_dlpa,
    apurar_dmpl,
    avaliar_emissao_da_dmpl,
    classificar_conta_na_dmpl,
    criar_lancamento,
    definir_adocao_antecipada_da_nbc_tg_51,
    estornar_lancamento,
    linha_da_dmpl_equivalente_a_linha_da_dlpa,
    norma_das_demonstracoes,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.contabilidade.tests.test_dl048_dlpa import cenario_dlpa  # noqa: F401  (fixture)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA
PL = TipoConta.PATRIMONIO_LIQUIDO

ANO = 2026
MES = 3

COL = ClassificacaoDmpl
LUCROS = COL.LUCROS_OU_PREJUIZOS_ACUMULADOS

_CONTADOR_DE_CNPJ = iter(range(52000000000000, 52000000009999))


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _dec(valor):
    return Decimal(valor)


def _empresa(nome="Empresa DMPL Ltda"):
    escritorio = Escritorio.objects.create(nome=f"Escritório {nome}", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social=nome, cnpj=_cnpj_sintetico()
    )
    return empresa


def _conta(empresa, codigo, nome, tipo, natureza, *, dmpl=None, dlpa=None, pai=None):
    """Cria a conta e a passa por `full_clean()`: o plano de teste só contém
    contas que o próprio cadastro aceitaria."""
    conta = Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_dmpl=dmpl,
        classificacao_dlpa=dlpa,
    )
    conta.full_clean()
    return conta


def _plano_basico(empresa):
    """Plano mínimo dos casos A e B: capital, reserva legal e lucros
    acumulados (com prejuízos), mais o resultado do exercício (passagem), o
    passivo de dividendos e as contas de caixa/receita/despesa."""
    # O grupo "3 Patrimônio Líquido" é conta-pai de todas as contas de PL: é
    # assim que o Balanço trata a retificadora devedora (prejuízos, ações em
    # tesouraria) como SUBTRAÇÃO dentro do grupo (RC-61/RC-104,
    # `apurar_saldos`). Retificadora solta na raiz seria SOMADA ao PL pelo
    # Balanço, e a conciliação da DMPL acusaria a divergência.
    pl = Conta.objects.create(
        empresa=empresa,
        codigo="3",
        nome="Patrimônio Líquido",
        tipo=PL,
        natureza=C,
        aceita_lancamento=False,
    )
    return {
        "pl": pl,
        "caixa": _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, D),
        "imobilizado": _conta(empresa, "1.2", "Imobilizado", TipoConta.ATIVO, D),
        "dividendos": _conta(
            empresa,
            "2.1",
            "Dividendos a Pagar",
            TipoConta.PASSIVO,
            C,
            dlpa=ClassificacaoDlpa.DIVIDENDO,
        ),
        "resultado": _conta(
            empresa,
            "3.0",
            "Resultado do Exercício",
            PL,
            C,
            dlpa=ClassificacaoDlpa.RESULTADO_DO_EXERCICIO,
            pai=pl,
        ),
        "capital": _conta(
            empresa,
            "3.1",
            "Capital Social",
            PL,
            C,
            dmpl=COL.CAPITAL_SOCIAL,
            dlpa=ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL,
            pai=pl,
        ),
        "reserva_legal": _conta(
            empresa,
            "3.2",
            "Reserva Legal",
            PL,
            C,
            dmpl=COL.RESERVA_LEGAL,
            dlpa=ClassificacaoDlpa.RESERVA_LEGAL,
            pai=pl,
        ),
        "lucros": _conta(
            empresa,
            "3.3",
            "Lucros Acumulados",
            PL,
            C,
            dmpl=LUCROS,
            dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
            pai=pl,
        ),
        "prejuizos": _conta(
            empresa,
            "3.4",
            "(-) Prejuízos Acumulados",
            PL,
            D,
            dmpl=LUCROS,
            dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
            pai=pl,
        ),
        "receita": _conta(empresa, "4.1", "Receita", TipoConta.RECEITA, C),
        "despesa": _conta(empresa, "5.1", "Despesa", TipoConta.DESPESA, D),
    }


def _contas_do_caso_b(empresa, pl):
    return {
        "ajustes": _conta(
            empresa,
            "3.5",
            "Ajustes de Avaliação Patrimonial",
            PL,
            C,
            dmpl=COL.AJUSTES_DE_AVALIACAO_PATRIMONIAL,
            pai=pl,
        ),
        "tesouraria": _conta(
            empresa,
            "3.6",
            "(-) Ações em Tesouraria",
            PL,
            D,
            dmpl=COL.ACOES_OU_QUOTAS_EM_TESOURARIA,
            pai=pl,
        ),
    }


def _lancar(empresa, data, historico, debito, credito, valor):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": _dec(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": _dec(valor)},
        ],
    )


def _lancar_itens(empresa, data, historico, itens):
    """`itens`: lista de `(conta, "D"|"C", valor)`."""
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {
                "conta": conta,
                "tipo": TipoPartida.DEBITO if lado == "D" else TipoPartida.CREDITO,
                "valor": _dec(valor),
            }
            for conta, lado, valor in itens
        ],
    )


def _gestor(empresa, username="gestor-dl061"):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=empresa.escritorio, papel=Papel.GESTOR
    )
    return usuario


def _parametro_do_zeramento(empresa, contas, usuario, **extra):
    return registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2026, 1, 1),
        usuario=usuario,
        **extra,
    )


def _caso_a(empresa=None, valores=None):
    """Caso A do plano: capital 100.000,00; lucro 25.000,00; reserva legal
    1.250,00; dividendos 10.000,00 — com lançamentos reais e o zeramento de
    verdade (não uma transferência manual)."""
    empresa = empresa or _empresa()
    contas = _plano_basico(empresa)
    gestor = _gestor(empresa, f"gestor-a-{empresa.pk}")
    _parametro_do_zeramento(empresa, contas, gestor)
    capital, lucro, reserva, dividendos = valores or (
        "100000.00",
        "25000.00",
        "1250.00",
        "10000.00",
    )
    _lancar(
        empresa,
        date(2025, 12, 31),
        "Capital integralizado",
        contas["caixa"],
        contas["capital"],
        capital,
    )
    _lancar(
        empresa, date(2026, 3, 5), "Receita do período", contas["caixa"], contas["receita"], lucro
    )
    zerar_resultado(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    _lancar(
        empresa,
        date(2026, 3, 31),
        "Reserva legal",
        contas["lucros"],
        contas["reserva_legal"],
        reserva,
    )
    _lancar(
        empresa, date(2026, 3, 31), "Dividendos", contas["lucros"], contas["dividendos"], dividendos
    )
    return empresa, contas, gestor


def _caso_b():
    """Caso B: o A acrescido de aumento de capital em dinheiro de 20.000,00,
    ajuste de avaliação patrimonial de +3.000,00 e aquisição de ações em
    tesouraria de 2.000,00."""
    empresa, contas, gestor = _caso_a()
    contas.update(_contas_do_caso_b(empresa, contas["pl"]))
    _lancar(
        empresa,
        date(2026, 2, 10),
        "Aumento de capital",
        contas["caixa"],
        contas["capital"],
        "20000.00",
    )
    _lancar(
        empresa,
        date(2026, 3, 10),
        "Reavaliação",
        contas["imobilizado"],
        contas["ajustes"],
        "3000.00",
    )
    _lancar(
        empresa,
        date(2026, 3, 12),
        "Ações em tesouraria",
        contas["tesouraria"],
        contas["caixa"],
        "2000.00",
    )
    return empresa, contas, gestor


def _linha(dmpl, chave):
    for linha in dmpl["linhas"]:
        if linha["chave"] == chave:
            return linha
    return None


def _celula(dmpl, chave, coluna):
    linha = _linha(dmpl, chave)
    assert linha is not None, f"linha {chave} ausente: {[x['chave'] for x in dmpl['linhas']]}"
    return linha["valores"][coluna]


def _chaves_das_linhas(dmpl):
    return [linha["chave"] for linha in dmpl["linhas"]]


def _apurar(empresa, mes=MES, ano=ANO):
    return apurar_dmpl(empresa=empresa, ano=ano, mes=mes)


def _pendencias_nao_vazias(dmpl):
    return {nome for nome, itens in dmpl["pendencias"].items() if itens}


# ---------------------------------------------------------------------------
# Modelo e mapas derivados (E1)
# ---------------------------------------------------------------------------


def test_os_mapas_cobrem_exatamente_o_enum():
    """Coluna nova sem grupo, sem tipo aceito ou sem entrada na tabela
    DLPA × DMPL reprova aqui — não some em silêncio do documento."""
    assert {c.value for c in GRUPO_DA_CLASSIFICACAO_DMPL} == set(ClassificacaoDmpl.values)
    assert {c.value for c in TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL} == set(ClassificacaoDmpl.values)
    assert {c.value for c in COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA} == set(
        ClassificacaoDlpa.values
    )
    for tipos in TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL.values():
        assert tipos == (TipoConta.PATRIMONIO_LIQUIDO,)


def test_as_colunas_estao_na_ordem_dos_grupos_do_item_111a():
    """E1: capital; reservas de capital; ajustes; reservas de lucros;
    tesouraria; lucros/prejuízos. A ordem dos membros do enum é a ordem das
    colunas no documento — grupo nenhum reaparece depois de outro começar."""
    ordem_dos_grupos = list(GrupoDaDmpl.values)
    indices = [ordem_dos_grupos.index(GRUPO_DA_CLASSIFICACAO_DMPL[c].value) for c in COL]
    assert indices == sorted(indices)
    assert list(COL.values)[0] == "capital_social"
    assert list(COL.values)[-1] == "lucros_ou_prejuizos_acumulados"
    assert len(COL.values) == 12


def test_as_seis_reservas_de_lucros_da_dmpl_espelham_as_da_dlpa():
    assert [r.value for r in RESERVAS_DE_LUCROS_DA_DMPL] == [
        r.value for r in RESERVAS_DE_LUCROS_DA_DLPA
    ]
    assert set(RESERVAS_DE_LUCROS_DA_DMPL) <= set(COL)
    for reserva in RESERVAS_DE_LUCROS_DA_DLPA:
        assert COLUNAS_DA_DMPL_ADMITIDAS_PARA_A_CLASSIFICACAO_DLPA[reserva] == {COL(reserva.value)}


def test_nao_existe_coluna_para_as_reservas_c_e_d_do_art_182_nem_correcao_monetaria():
    """HI-50 e a Lei 9.249/95, art. 4º, p.ú.: nenhuma dessas vira coluna."""
    nomes = " ".join(COL.values)
    for proibido in ("debenture", "doacoes", "subvencoes", "correcao_monetaria"):
        assert proibido not in nomes


def test_conta_nasce_sem_coluna_e_a_vazia_vira_none():
    empresa = _empresa()
    nova = _conta(empresa, "3.9", "Nova", PL, C)
    assert nova.classificacao_dmpl is None
    nova.classificacao_dmpl = ""
    nova.full_clean()
    assert nova.classificacao_dmpl is None


def test_coluna_so_para_conta_de_patrimonio_liquido():
    empresa = _empresa()
    for tipo in (TipoConta.ATIVO, TipoConta.PASSIVO, TipoConta.RECEITA, TipoConta.DESPESA):
        conta = Conta.objects.create(
            empresa=empresa, codigo=f"9.{tipo}", nome="X", tipo=tipo, natureza=C
        )
        conta.classificacao_dmpl = COL.CAPITAL_SOCIAL
        with pytest.raises(ValidationError, match="não é compatível com o tipo"):
            conta.full_clean()


def test_coluna_valor_fora_do_enum_e_recusado_pelo_full_clean():
    empresa = _empresa()
    conta = _conta(empresa, "3.9", "Nova", PL, C)
    conta.classificacao_dmpl = "coluna_inventada"
    with pytest.raises(ValidationError):
        conta.full_clean()


@pytest.mark.parametrize(
    ("dlpa", "dmpl"),
    [
        (ClassificacaoDlpa.RESERVA_LEGAL, COL.RESERVA_ESTATUTARIA),
        (ClassificacaoDlpa.RESERVA_LEGAL, COL.CAPITAL_SOCIAL),
        (ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS, COL.RESERVA_LEGAL),
        (ClassificacaoDlpa.RESULTADO_DO_EXERCICIO, COL.LUCROS_OU_PREJUIZOS_ACUMULADOS),
        (ClassificacaoDlpa.RESULTADO_DO_EXERCICIO, COL.CAPITAL_SOCIAL),
        (ClassificacaoDlpa.DIVIDENDO, COL.LUCROS_OU_PREJUIZOS_ACUMULADOS),
        (ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR, COL.LUCROS_OU_PREJUIZOS_ACUMULADOS),
        (ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL, COL.RESERVA_LEGAL),
    ],
)
def test_divergencia_entre_dlpa_e_dmpl_na_mesma_conta_e_recusada(dlpa, dmpl):
    empresa = _empresa()
    conta = _conta(empresa, "3.9", "Conta", PL, C)
    conta.classificacao_dlpa = dlpa
    conta.classificacao_dmpl = dmpl
    with pytest.raises(ValidationError, match="DLPA"):
        conta.full_clean()


@pytest.mark.parametrize(
    ("dlpa", "dmpl"),
    [
        (ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS, COL.LUCROS_OU_PREJUIZOS_ACUMULADOS),
        (ClassificacaoDlpa.RESERVA_LEGAL, COL.RESERVA_LEGAL),
        (ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR, COL.RESERVA_DE_LUCROS_A_REALIZAR),
        (ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL, COL.CAPITAL_SOCIAL),
        (None, COL.AJUSTES_DE_AVALIACAO_PATRIMONIAL),
        (ClassificacaoDlpa.RESERVA_LEGAL, None),
    ],
)
def test_combinacoes_consistentes_de_dlpa_e_dmpl_sao_aceitas(dlpa, dmpl):
    empresa = _empresa()
    conta = _conta(empresa, "3.9", "Conta", PL, C)
    conta.classificacao_dlpa = dlpa
    conta.classificacao_dmpl = dmpl
    conta.full_clean()


def test_o_banco_recusa_coluna_em_branco():
    """A defesa de banco `ck_conta_classificacao_dmpl_nao_vazia`: `""` por
    fora do `full_clean()` (ORM direto) nunca chega a existir."""
    empresa = _empresa()
    conta = _conta(empresa, "3.9", "Nova", PL, C)
    with pytest.raises(IntegrityError), transaction.atomic():
        Conta.objects.filter(pk=conta.pk).update(classificacao_dmpl="")


# ---------------------------------------------------------------------------
# Critério 1 — casos A e B do plano, calculados à mão
# ---------------------------------------------------------------------------


def test_caso_a_reproduz_o_exemplo_do_plano_ao_centavo():
    empresa, _, _ = _caso_a()
    dmpl = _apurar(empresa)

    assert [c["chave"] for c in dmpl["colunas"]] == ["capital_social", "reserva_legal", LUCROS]
    assert _chaves_das_linhas(dmpl) == [
        "saldo_inicial",
        "resultado_do_exercicio",
        "constituicao_de_reservas",
        "dividendos",
        "saldo_final",
    ]

    # Saldo inicial: só o capital.
    assert dmpl["saldo_inicial"]["valores"] == {
        "capital_social": _dec("100000.00"),
        "reserva_legal": _dec("0"),
        LUCROS: _dec("0"),
    }
    assert dmpl["saldo_inicial"]["total"] == _dec("100000.00")
    # Resultado do exercício: 25.000,00 só nos lucros.
    assert _celula(dmpl, "resultado_do_exercicio", LUCROS) == _dec("25000.00")
    assert _celula(dmpl, "resultado_do_exercicio", "capital_social") == _dec("0")
    assert _linha(dmpl, "resultado_do_exercicio")["total"] == _dec("25000.00")
    # Constituição de reservas: +1.250,00 na reserva, (1.250,00) nos lucros, total zero.
    assert _celula(dmpl, "constituicao_de_reservas", "reserva_legal") == _dec("1250.00")
    assert _celula(dmpl, "constituicao_de_reservas", LUCROS) == _dec("-1250.00")
    assert _linha(dmpl, "constituicao_de_reservas")["total"] == _dec("0.00")
    # Dividendos: (10.000,00) nos lucros.
    assert _celula(dmpl, "dividendos", LUCROS) == _dec("-10000.00")
    assert _linha(dmpl, "dividendos")["total"] == _dec("-10000.00")
    # Saldo final: 100.000,00 / 1.250,00 / 13.750,00 = 115.000,00.
    assert dmpl["saldo_final"]["valores"] == {
        "capital_social": _dec("100000.00"),
        "reserva_legal": _dec("1250.00"),
        LUCROS: _dec("13750.00"),
    }
    assert dmpl["saldo_final"]["total"] == _dec("115000.00")
    assert _linha(dmpl, "saldo_final")["total"] == _dec("115000.00")

    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True, emissao
    assert emissao["avisos"] == {}, "com o zeramento feito não sobra resultado a transferir"
    assert emissao["motivos"] == []


def test_caso_b_reproduz_o_exemplo_do_plano_ao_centavo():
    empresa, _, _ = _caso_b()
    dmpl = _apurar(empresa)

    # Colunas na ordem do item 111A: capital, ajustes, reserva legal, tesouraria, lucros.
    assert [c["chave"] for c in dmpl["colunas"]] == [
        "capital_social",
        "ajustes_de_avaliacao_patrimonial",
        "reserva_legal",
        "acoes_ou_quotas_em_tesouraria",
        LUCROS,
    ]
    # Ordem das linhas (E4): só as com movimento, na ordem do plano.
    assert _chaves_das_linhas(dmpl) == [
        "saldo_inicial",
        "aumento_de_capital",
        "aquisicao_de_acoes_ou_quotas_em_tesouraria",
        "resultado_do_exercicio",
        "outros_resultados_abrangentes",
        "constituicao_de_reservas",
        "dividendos",
        "saldo_final",
    ]
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("20000.00")
    assert _celula(
        dmpl, "aquisicao_de_acoes_ou_quotas_em_tesouraria", "acoes_ou_quotas_em_tesouraria"
    ) == _dec("-2000.00")
    assert _celula(
        dmpl, "outros_resultados_abrangentes", "ajustes_de_avaliacao_patrimonial"
    ) == _dec("3000.00")

    assert dmpl["saldo_final"]["valores"] == {
        "capital_social": _dec("120000.00"),
        "ajustes_de_avaliacao_patrimonial": _dec("3000.00"),
        "reserva_legal": _dec("1250.00"),
        "acoes_ou_quotas_em_tesouraria": _dec("-2000.00"),
        LUCROS: _dec("13750.00"),
    }
    # 100.000 + 20.000 + 25.000 − 10.000 + 3.000 − 2.000 = 136.000.
    assert dmpl["saldo_final"]["total"] == _dec("136000.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


def test_identidade_de_cada_linha_saldo_inicial_mais_movimento_igual_saldo_final():
    empresa, _, _ = _caso_b()
    dmpl = _apurar(empresa)
    eventos = [x for x in dmpl["linhas"] if x["chave"] not in ("saldo_inicial", "saldo_final")]
    for coluna in (c["chave"] for c in dmpl["colunas"]):
        movimento = sum((x["valores"][coluna] for x in eventos), _dec("0"))
        assert (
            dmpl["saldo_inicial"]["valores"][coluna] + movimento
            == dmpl["saldo_final"]["valores"][coluna]
        )
    for linha in dmpl["linhas"]:
        assert linha["total"] == sum(linha["valores"].values(), _dec("0"))


def test_rastreabilidade_cada_celula_com_valor_aponta_lancamentos_da_empresa():
    empresa, _, _ = _caso_b()
    dmpl = _apurar(empresa)
    ids_da_empresa = set(
        LancamentoContabil.objects.filter(empresa=empresa).values_list("id", flat=True)
    )
    assert ids_da_empresa
    for linha in dmpl["linhas"]:
        if linha["chave"] in ("saldo_inicial", "saldo_final"):
            assert linha["lancamentos"] == {}
            continue
        for coluna, valor in linha["valores"].items():
            if valor != 0:
                assert linha["lancamentos"][coluna], (linha["chave"], coluna)
        for ids in linha["lancamentos"].values():
            assert set(ids) <= ids_da_empresa


def test_contrato_do_retorno_tem_as_chaves_documentadas():
    empresa, _, _ = _caso_a()
    dmpl = _apurar(empresa)
    assert set(dmpl) == {
        "empresa_id",
        "ano",
        "mes",
        "data_inicio_exercicio",
        "data_fim",
        "colunas",
        "linhas",
        "saldo_inicial",
        "saldo_final",
        "conciliacao",
        "pendencias",
        "avisos",
        "norma",
    }
    assert dmpl["empresa_id"] == empresa.id
    assert (dmpl["ano"], dmpl["mes"]) == (2026, 3)
    assert dmpl["data_inicio_exercicio"] == date(2026, 1, 1)
    assert dmpl["data_fim"] == date(2026, 3, 31)
    assert set(dmpl["colunas"][0]) == {"chave", "titulo", "grupo", "grupo_titulo"}
    assert dmpl["colunas"][0]["grupo"] == "capital_social"
    assert dmpl["colunas"][1]["grupo"] == "reservas_de_lucros"
    assert dmpl["colunas"][1]["grupo_titulo"] == "Reservas de lucros"
    assert set(dmpl["linhas"][0]) == {"chave", "titulo", "valores", "total", "lancamentos"}
    assert set(dmpl["saldo_final"]) == {"valores", "total"}
    assert set(dmpl["conciliacao"]) == {"por_coluna", "total"}
    assert set(dmpl["pendencias"]) == set(_LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO)
    for linha in dmpl["linhas"]:
        assert linha["titulo"] == _TITULOS_DAS_LINHAS_DA_DMPL[linha["chave"]]


def test_a_ordem_e_os_titulos_das_linhas_sao_os_da_decisao_e4():
    assert list(_TITULOS_DAS_LINHAS_DA_DMPL) == [
        "saldo_inicial",
        "ajustes_de_exercicios_anteriores",
        "aumento_de_capital",
        "reducao_de_capital",
        "aquisicao_de_acoes_ou_quotas_em_tesouraria",
        "alienacao_ou_cancelamento_de_acoes_ou_quotas_em_tesouraria",
        "constituicao_de_reservas_de_capital",
        "resultado_do_exercicio",
        "outros_resultados_abrangentes",
        "constituicao_de_reservas",
        "reversao_de_reservas",
        "aumento_de_capital_com_reservas_e_lucros",
        "dividendos",
        "saldo_final",
    ]


# ---------------------------------------------------------------------------
# Critério 2 — a coluna de lucros acumulados é a DLPA
# ---------------------------------------------------------------------------


def _conferir_identidade_com_a_dlpa(empresa, mes=MES):
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=mes)
    dmpl = _apurar(empresa, mes=mes)
    assert dmpl["saldo_inicial"]["valores"][LUCROS] == dlpa["saldo_inicial"]
    assert dmpl["saldo_final"]["valores"][LUCROS] == dlpa["saldo_final"]

    esperado = {}
    for linha in dlpa["linhas"]:
        if linha["chave"] in ("saldo_inicial", "saldo_final"):
            continue
        equivalente = linha_da_dmpl_equivalente_a_linha_da_dlpa(linha["chave"])
        assert equivalente is not None, linha["chave"]
        esperado[equivalente] = esperado.get(equivalente, _dec("0")) + linha["valor"]
    encontrado = {
        linha["chave"]: linha["valores"][LUCROS]
        for linha in dmpl["linhas"]
        if linha["chave"] not in ("saldo_inicial", "saldo_final") and linha["valores"][LUCROS] != 0
    }
    assert encontrado == {chave: valor for chave, valor in esperado.items() if valor != 0}
    return dlpa, dmpl


def test_identidade_com_a_dlpa_nos_casos_a_e_b():
    for caso in (_caso_a, _caso_b):
        empresa, _, _ = caso()
        _conferir_identidade_com_a_dlpa(empresa)


def test_identidade_com_a_dlpa_no_cenario_da_propria_dlpa(cenario_dlpa):  # noqa: F811
    """O cenário que exercita TODOS os eventos do art. 186: ajuste de
    exercício anterior, reversão, resultado, transferência, dividendos e
    lucro incorporado ao capital — cada um no evento correspondente da DMPL."""
    cenario = cenario_dlpa
    for chave, coluna in (
        ("lucros", LUCROS),
        ("prejuizos", LUCROS),
        ("reserva", COL.RESERVA_LEGAL),
        ("capital", COL.CAPITAL_SOCIAL),
    ):
        Conta.objects.filter(pk=cenario[chave].pk).update(classificacao_dmpl=coluna)
    dlpa, dmpl = _conferir_identidade_com_a_dlpa(cenario["empresa"])

    assert dmpl["saldo_final"]["valores"][LUCROS] == _dec("14500.00")
    assert _celula(dmpl, "ajustes_de_exercicios_anteriores", LUCROS) == _dec("150.00")
    assert _celula(dmpl, "reversao_de_reservas", LUCROS) == _dec("300.00")
    assert _celula(dmpl, "reversao_de_reservas", "reserva_legal") == _dec("-300.00")
    assert _celula(dmpl, "resultado_do_exercicio", LUCROS) == _dec("25000.00")
    assert _celula(dmpl, "constituicao_de_reservas", LUCROS) == _dec("-1250.00")
    assert _celula(dmpl, "dividendos", LUCROS) == _dec("-10000.00")
    assert _celula(dmpl, "aumento_de_capital_com_reservas_e_lucros", LUCROS) == _dec("-500.00")
    assert _celula(dmpl, "aumento_de_capital_com_reservas_e_lucros", "capital_social") == _dec(
        "500.00"
    )
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True, emissao
    # Resultado de 777,00 ainda sem zerar: aviso, nunca veto.
    assert emissao["avisos"]["resultado_nao_transferido"][0]["valor"] == _dec("777.00")


def test_a_identidade_com_a_dlpa_vale_em_cada_mes_do_exercicio():
    empresa, _, _ = _caso_b()
    for mes in (3, 4, 12):
        _conferir_identidade_com_a_dlpa(empresa, mes=mes)


def test_lucros_nunca_ancora_ambigua_quando_nao_esta_sozinho_no_seu_lado():
    """D lucros 300 + D reserva legal 100 / C capital 400: a DLPA empareceria
    os lucros com cada outra partida (inclusive a reserva, no sentido
    errado) e a DMPL, pelo fluxo, de outro jeito — as duas discordariam por
    linha. A regra recusa (AMBÍGUO) em vez de deixar os documentos
    discordarem em silêncio."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Capitalização de lucros e reserva",
        [
            (contas["lucros"], "D", "300.00"),
            (contas["reserva_legal"], "D", "100.00"),
            (contas["capital"], "C", "400.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


# ---------------------------------------------------------------------------
# Regras de linha (E2), uma a uma
# ---------------------------------------------------------------------------


def test_reversao_de_reserva_vai_da_reserva_para_os_lucros():
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa, date(2026, 3, 20), "Reversão", contas["reserva_legal"], contas["lucros"], "200.00"
    )
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "reversao_de_reservas", "reserva_legal") == _dec("-200.00")
    assert _celula(dmpl, "reversao_de_reservas", LUCROS) == _dec("200.00")
    assert _linha(dmpl, "reversao_de_reservas")["total"] == _dec("0.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


def test_estorno_da_constituicao_aparece_como_reversao_e_a_soma_fecha():
    empresa, contas, _ = _caso_a()
    constituicao = _lancar(
        empresa,
        date(2026, 3, 31),
        "Outra reserva",
        contas["lucros"],
        contas["reserva_legal"],
        "400.00",
    )
    estornar_lancamento(constituicao, data=date(2026, 3, 31))
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "constituicao_de_reservas", "reserva_legal") == _dec("1650.00")
    assert _celula(dmpl, "reversao_de_reservas", "reserva_legal") == _dec("-400.00")
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("1250.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


def test_lucros_para_capital_e_aumento_de_capital_com_reservas_e_lucros():
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa, date(2026, 3, 20), "Capitalização", contas["lucros"], contas["capital"], "500.00"
    )
    _lancar(
        empresa,
        date(2026, 3, 21),
        "Capitalização de reserva",
        contas["reserva_legal"],
        contas["capital"],
        "200.00",
    )
    dmpl = _apurar(empresa)
    linha = "aumento_de_capital_com_reservas_e_lucros"
    assert _celula(dmpl, linha, "capital_social") == _dec("700.00")
    assert _celula(dmpl, linha, LUCROS) == _dec("-500.00")
    assert _celula(dmpl, linha, "reserva_legal") == _dec("-200.00")
    assert _linha(dmpl, linha)["total"] == _dec("0.00")
    assert "aumento_de_capital" not in _chaves_das_linhas(dmpl)


def test_dividendo_pago_a_conta_de_reserva_de_lucros_e_dividendos():
    """A classificação da DLPA da contrapartida vale para QUALQUER coluna."""
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 22),
        "Dividendo da reserva",
        contas["reserva_legal"],
        contas["dividendos"],
        "300.00",
    )
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "dividendos", "reserva_legal") == _dec("-300.00")
    assert _celula(dmpl, "dividendos", LUCROS) == _dec("-10000.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


def test_ajuste_de_exercicio_anterior_pela_classificacao_da_contrapartida():
    empresa, contas, _ = _caso_a()
    ajuste = _conta(
        empresa,
        "1.3",
        "Correção de erro de exercício anterior",
        TipoConta.ATIVO,
        D,
        dlpa=ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR,
    )
    _lancar(empresa, date(2026, 3, 22), "Retificação", ajuste, contas["lucros"], "150.00")
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "ajustes_de_exercicios_anteriores", LUCROS) == _dec("150.00")
    _conferir_identidade_com_a_dlpa(empresa)


def test_capital_credito_e_aumento_e_debito_e_reducao():
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa, date(2026, 2, 1), "Integralização", contas["caixa"], contas["capital"], "7000.00"
    )
    _lancar(empresa, date(2026, 2, 2), "Devolução", contas["capital"], contas["caixa"], "1500.00")
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("7000.00")
    assert _celula(dmpl, "reducao_de_capital", "capital_social") == _dec("-1500.00")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("105500.00")


def test_capital_a_integralizar_contra_o_capital_tem_efeito_liquido_zero():
    """Mesma coluna: a subscrição (D capital a integralizar / C capital
    subscrito) não é evento; só a integralização é."""
    empresa, contas, _ = _caso_a()
    a_integralizar = _conta(
        empresa,
        "3.8",
        "(-) Capital a Integralizar",
        PL,
        D,
        dmpl=COL.CAPITAL_SOCIAL,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2026, 2, 1), "Subscrição", a_integralizar, contas["capital"], "50000.00")
    dmpl = _apurar(empresa)
    assert "aumento_de_capital" not in _chaves_das_linhas(dmpl)
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("100000.00")

    _lancar(
        empresa,
        date(2026, 2, 15),
        "Integralização em dinheiro",
        contas["caixa"],
        a_integralizar,
        "20000.00",
    )
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("20000.00")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("120000.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


def test_tesouraria_debito_e_aquisicao_credito_e_alienacao():
    """Mutação típica: inverter a direção da tesouraria."""
    empresa, contas, _ = _caso_b()
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Alienação de parte das ações",
        contas["caixa"],
        contas["tesouraria"],
        "500.00",
    )
    dmpl = _apurar(empresa)
    coluna = "acoes_ou_quotas_em_tesouraria"
    assert _celula(dmpl, "aquisicao_de_acoes_ou_quotas_em_tesouraria", coluna) == _dec("-2000.00")
    assert _celula(
        dmpl, "alienacao_ou_cancelamento_de_acoes_ou_quotas_em_tesouraria", coluna
    ) == _dec("500.00")
    assert dmpl["saldo_final"]["valores"][coluna] == _dec("-1500.00")


def test_ajustes_de_avaliacao_nos_dois_sentidos_sao_outros_resultados_abrangentes():
    empresa, contas, _ = _caso_b()
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Perda na reavaliação",
        contas["ajustes"],
        contas["imobilizado"],
        "800.00",
    )
    dmpl = _apurar(empresa)
    assert _celula(
        dmpl, "outros_resultados_abrangentes", "ajustes_de_avaliacao_patrimonial"
    ) == _dec("2200.00")
    assert dmpl["saldo_final"]["valores"]["ajustes_de_avaliacao_patrimonial"] == _dec("2200.00")


def test_reserva_de_capital_credito_e_constituicao_e_e_resolvida_com_o_capital():
    """D Caixa 100 / C capital 70 / C ágio 30: âncora externa (a única
    partida a débito), cada coluna emparelhada por inteiro com ela."""
    empresa, contas, _ = _caso_a()
    agio = _conta(
        empresa, "3.7", "Ágio na Emissão de Ações", PL, C, dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES
    )
    _lancar_itens(
        empresa,
        date(2026, 3, 18),
        "Emissão de ações com ágio",
        [(contas["caixa"], "D", "100.00"), (contas["capital"], "C", "70.00"), (agio, "C", "30.00")],
    )
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("70.00")
    assert _celula(dmpl, "constituicao_de_reservas_de_capital", "agio_na_emissao_de_acoes") == _dec(
        "30.00"
    )
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


def test_dividendo_lancado_contra_varios_destinos_do_mesmo_lancamento():
    """D lucros 100 / C reserva 40 / C dividendos 60: os lucros são a única
    partida a débito; cada destino leva o que recebeu — sem rateio."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 3, 25),
        "Destinação do lucro",
        [
            (contas["lucros"], "D", "100.00"),
            (contas["reserva_legal"], "C", "40.00"),
            (contas["dividendos"], "C", "60.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "constituicao_de_reservas", "reserva_legal") == _dec("1290.00")
    assert _celula(dmpl, "constituicao_de_reservas", LUCROS) == _dec("-1290.00")
    assert _celula(dmpl, "dividendos", LUCROS) == _dec("-10060.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    _conferir_identidade_com_a_dlpa(empresa)


def test_prejuizo_do_zeramento_vira_resultado_negativo_nos_lucros():
    empresa = _empresa()
    contas = _plano_basico(empresa)
    gestor = _gestor(empresa, "gestor-prejuizo")
    _parametro_do_zeramento(empresa, contas, gestor)
    _lancar(empresa, date(2026, 3, 5), "Despesa", contas["despesa"], contas["caixa"], "4000.00")
    zerar_resultado(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "resultado_do_exercicio", LUCROS) == _dec("-4000.00")
    assert dmpl["saldo_final"]["valores"][LUCROS] == _dec("-4000.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    _conferir_identidade_com_a_dlpa(empresa)


# ---------------------------------------------------------------------------
# Período (E6)
# ---------------------------------------------------------------------------


def test_o_exercicio_vai_de_primeiro_de_janeiro_ao_fim_do_mes_pedido():
    empresa, contas, _ = _caso_a()
    # 31/12/2025 é saldo inicial; 01/01/2026 é movimento; abril fica fora de março.
    _lancar(empresa, date(2026, 1, 1), "Primeiro dia", contas["caixa"], contas["capital"], "10.00")
    _lancar(empresa, date(2026, 4, 1), "Abril", contas["caixa"], contas["capital"], "999.00")
    dmpl = _apurar(empresa, mes=3)
    assert dmpl["saldo_inicial"]["valores"]["capital_social"] == _dec("100000.00")
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("10.00")
    assert dmpl["saldo_final"]["valores"]["capital_social"] == _dec("100010.00")
    em_abril = _apurar(empresa, mes=4)
    assert em_abril["saldo_final"]["valores"]["capital_social"] == _dec("101009.00")
    assert em_abril["data_fim"] == date(2026, 4, 30)
    # Fevereiro: ainda antes do zeramento de março.
    fevereiro = _apurar(empresa, mes=2)
    assert fevereiro["data_fim"] == date(2026, 2, 28)
    assert fevereiro["saldo_final"]["valores"][LUCROS] == _dec("0")


def test_o_saldo_inicial_do_ano_seguinte_e_o_saldo_final_do_anterior():
    empresa, _, _ = _caso_a()
    fim_2026 = _apurar(empresa, mes=12)
    inicio_2027 = apurar_dmpl(empresa=empresa, ano=2027, mes=1)
    assert inicio_2027["saldo_inicial"]["valores"] == fim_2026["saldo_final"]["valores"]
    assert inicio_2027["data_inicio_exercicio"] == date(2027, 1, 1)


# ---------------------------------------------------------------------------
# Critério 3 — conciliação com o Balanço
# ---------------------------------------------------------------------------


def test_a_conciliacao_fecha_por_coluna_e_no_total():
    empresa, _, _ = _caso_b()
    dmpl = _apurar(empresa)
    por_coluna = dmpl["conciliacao"]["por_coluna"]
    assert set(por_coluna) == {c["chave"] for c in dmpl["colunas"]}
    for coluna, conferencia in por_coluna.items():
        assert conferencia["diferenca"] == 0, coluna
        assert conferencia["saldo_na_dmpl"] == dmpl["saldo_final"]["valores"][coluna]
    total = dmpl["conciliacao"]["total"]
    assert total["saldo_na_dmpl"] == _dec("136000.00")
    assert total["saldo_no_balanco"] == _dec("136000.00")
    assert total["saldo_contas_de_passagem"] == _dec("0")
    assert total["diferenca"] == 0
    assert dmpl["pendencias"]["diferenca_de_fechamento"] == []


def test_o_saldo_da_conta_de_passagem_entra_no_total_mas_nao_vira_coluna():
    """Resultado do exercício ainda com saldo (sem zerar o período): o total
    da DMPL + a conta de passagem é o PL do Balanço, e o aviso diz o resto."""
    empresa = _empresa()
    contas = _plano_basico(empresa)
    _lancar(empresa, date(2025, 12, 31), "Capital", contas["caixa"], contas["capital"], "1000.00")
    # Resultado do exercício creditado e NÃO transferido aos lucros.
    _lancar(
        empresa, date(2026, 3, 5), "Lucro apurado", contas["caixa"], contas["resultado"], "300.00"
    )
    dmpl = _apurar(empresa)
    assert "resultado_do_exercicio" not in {c["chave"] for c in dmpl["colunas"]}
    total = dmpl["conciliacao"]["total"]
    assert total["saldo_contas_de_passagem"] == _dec("300.00")
    assert total["saldo_na_dmpl"] == _dec("1000.00")
    assert total["saldo_na_dmpl"] + total["saldo_contas_de_passagem"] == total["saldo_no_balanco"]
    assert total["saldo_no_balanco"] == _dec("1300.00")
    assert total["diferenca"] == 0
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


def test_resultado_ainda_nao_transferido_e_aviso_e_nunca_veto():
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 29),
        "Receita nova, ainda sem zerar",
        contas["caixa"],
        contas["receita"],
        "777.00",
    )
    dmpl = _apurar(empresa)
    assert dmpl["avisos"]["resultado_nao_transferido"] == [{"valor": _dec("777.00")}]
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True
    assert emissao["avisos"]["resultado_nao_transferido"][0]["valor"] == _dec("777.00")


def test_divergencia_com_o_balanco_veta_e_nomeia_a_coluna():
    """Subconta de uma conta de coluna que se move: a DMPL lê a conta EXATA
    (sem herança, como a DLPA) e o Balanço consolida a subárvore — a
    diferença acende, veta, e NOMEIA a coluna (e o total)."""
    empresa, contas, _ = _caso_a()
    filha = _conta(empresa, "3.2.1", "Reserva Legal - Subconta", PL, C, pai=contas["reserva_legal"])
    _lancar(empresa, date(2026, 3, 30), "Movimento na subconta", contas["caixa"], filha, "500.00")

    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is False
    entradas = {e["coluna"]: e for e in emissao["listas_pendentes"]["diferenca_de_fechamento"]}
    assert set(entradas) == {"reserva_legal", "total"}
    reserva = entradas["reserva_legal"]
    assert reserva["titulo"] == "Reserva legal"
    assert reserva["saldo_na_dmpl"] == _dec("1250.00")
    assert reserva["saldo_no_balanco"] == _dec("1750.00")
    assert reserva["diferenca"] == _dec("-500.00")
    assert [c["conta"] for c in reserva["contas"]] == ["3.2"]
    assert entradas["total"]["diferenca"] == _dec("-500.00")
    # A subconta tem saldo e não tem coluna: a segunda pendência, também nomeada.
    sem_coluna = emissao["listas_pendentes"]["contas_do_patrimonio_liquido_sem_coluna"]
    assert [c["conta"] for c in sem_coluna] == ["3.2.1"]
    # As colunas que fecham não aparecem.
    assert dmpl["conciliacao"]["por_coluna"][LUCROS]["diferenca"] == 0
    assert any("Reserva legal" in motivo or "Diferença" in motivo for motivo in emissao["motivos"])


def test_a_divergencia_do_total_aparece_mesmo_sem_divergencia_de_coluna():
    """Conta de PL sem coluna com saldo: nenhuma coluna diverge, mas o total
    da DMPL não fecha com o PL do Balanço."""
    empresa, contas, _ = _caso_a()
    outra = _conta(empresa, "3.9", "Outras Reservas", PL, C)
    _lancar(empresa, date(2026, 3, 30), "Reserva sem coluna", contas["caixa"], outra, "40.00")
    dmpl = _apurar(empresa)
    entradas = dmpl["pendencias"]["diferenca_de_fechamento"]
    assert [e["coluna"] for e in entradas] == ["total"]
    assert entradas[0]["diferenca"] == _dec("-40.00")
    assert all(c["diferenca"] == 0 for c in dmpl["conciliacao"]["por_coluna"].values())


# ---------------------------------------------------------------------------
# Critério 4 — pendências que vetam, uma a uma
# ---------------------------------------------------------------------------


def test_todas_as_pendencias_vetam_e_a_tupla_e_o_inventario_das_chaves():
    empresa, _, _ = _caso_a()
    dmpl = _apurar(empresa)
    assert set(dmpl["pendencias"]) == set(_LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO)
    assert len(_LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO) == len(
        set(_LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO)
    )
    for nome in _LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO:
        isolada = dict(dmpl)
        isolada["pendencias"] = {n: ([{"x": 1}] if n == nome else []) for n in dmpl["pendencias"]}
        emissao = avaliar_emissao_da_dmpl(isolada)
        assert emissao["pode_emitir"] is False, nome
        assert list(emissao["listas_pendentes"]) == [nome]
        assert len(emissao["motivos"]) == 1


def test_sem_nenhuma_coluna_classificada_veta():
    empresa = _empresa()
    _conta(empresa, "3.1", "Capital Social", PL, C)
    _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, D)
    dmpl = _apurar(empresa)
    assert dmpl["colunas"] == []
    assert _pendencias_nao_vazias(dmpl) == {"nenhuma_coluna_classificada"}
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


def test_conta_de_pl_com_movimento_ou_saldo_e_sem_coluna_veta():
    empresa, contas, _ = _caso_a()
    com_movimento = _conta(empresa, "3.8", "PL com movimento", PL, C)
    so_saldo = _conta(empresa, "3.9", "PL só com saldo", PL, C)
    _conta(empresa, "3.10", "PL parada", PL, C)
    _lancar(empresa, date(2026, 3, 10), "Movimento", contas["caixa"], com_movimento, "10.00")
    _lancar(empresa, date(2025, 12, 31), "Saldo antigo", contas["caixa"], so_saldo, "20.00")
    dmpl = _apurar(empresa)
    entradas = {
        e["conta"]: e for e in dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]
    }
    assert set(entradas) == {"3.8", "3.9"}, "a parada e a conta de passagem não entram"
    assert entradas["3.8"]["movimento_no_exercicio"] is True
    assert entradas["3.9"]["movimento_no_exercicio"] is False
    assert entradas["3.9"]["saldo_inicial"] == _dec("20.00")
    assert entradas["3.8"]["conta_id"] == com_movimento.id
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


def test_conta_de_pl_sem_coluna_com_movimento_so_depois_do_periodo_nao_veta():
    empresa, contas, _ = _caso_a()
    futura = _conta(empresa, "3.8", "PL com movimento só em abril", PL, C)
    _lancar(empresa, date(2026, 4, 10), "Abril", contas["caixa"], futura, "10.00")
    assert "contas_do_patrimonio_liquido_sem_coluna" not in _pendencias_nao_vazias(
        _apurar(empresa, mes=3)
    )
    assert "contas_do_patrimonio_liquido_sem_coluna" in _pendencias_nao_vazias(
        _apurar(empresa, mes=4)
    )


def test_contrapartida_sem_classificacao_em_lucros_ou_reserva_veta():
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Lucros contra o caixa",
        contas["lucros"],
        contas["caixa"],
        "50.00",
    )
    _lancar(
        empresa,
        date(2026, 3, 21),
        "Reserva contra o caixa",
        contas["caixa"],
        contas["reserva_legal"],
        "60.00",
    )
    dmpl = _apurar(empresa)
    entradas = dmpl["pendencias"]["contrapartidas_sem_classificacao"]
    por_coluna = {e["coluna"]: e for e in entradas}
    assert set(por_coluna) == {LUCROS, "reserva_legal"}
    assert {e["conta"] for e in entradas} == {"1.1"}
    assert por_coluna[LUCROS]["conta_id"] == contas["caixa"].id
    assert por_coluna[LUCROS]["coluna_titulo"] == "Lucros ou prejuízos acumulados"
    assert len(por_coluna[LUCROS]["lancamentos"]) == 1
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


def test_a_mesma_contrapartida_sem_classificacao_nao_veta_na_coluna_de_capital():
    """Mutação típica: aplicar a pendência de lucros/reserva a todas as
    colunas. Capital, tesouraria e ajustes decidem pela direção."""
    empresa, _, _ = _caso_b()
    assert _pendencias_nao_vazias(_apurar(empresa)) == set()


def test_debito_em_reserva_de_capital_nao_tem_regra_e_veta():
    empresa, contas, _ = _caso_a()
    agio = _conta(empresa, "3.7", "Ágio", PL, C, dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES)
    _lancar(empresa, date(2026, 3, 18), "Devolução de ágio", agio, contas["caixa"], "10.00")
    dmpl = _apurar(empresa)
    entradas = dmpl["pendencias"]["contrapartidas_sem_classificacao"]
    assert [e["coluna"] for e in entradas] == ["agio_na_emissao_de_acoes"]
    assert "reserva de capital" in entradas[0]["mensagem"]


def test_conta_externa_classificada_na_dlpa_como_reserva_mas_sem_coluna_veta_com_motivo():
    empresa, contas, _ = _caso_a()
    sem_coluna = _conta(
        empresa,
        "3.8",
        "Reserva Estatutária (sem coluna)",
        PL,
        C,
        dlpa=ClassificacaoDlpa.RESERVA_ESTATUTARIA,
    )
    _lancar(
        empresa, date(2026, 3, 25), "Reserva estatutária", contas["lucros"], sem_coluna, "100.00"
    )
    dmpl = _apurar(empresa)
    pendentes = _pendencias_nao_vazias(dmpl)
    assert {
        "contrapartidas_sem_classificacao",
        "contas_do_patrimonio_liquido_sem_coluna",
    } <= pendentes
    mensagem = dmpl["pendencias"]["contrapartidas_sem_classificacao"][0]["mensagem"]
    assert "Reserva estatutária" in mensagem and "coluna" in mensagem


def test_par_de_colunas_sem_regra_veta_nomeando_origem_e_destino():
    empresa, contas, _ = _caso_a()
    estatutaria = _conta(
        empresa,
        "3.8",
        "Reserva Estatutária",
        PL,
        C,
        dmpl=COL.RESERVA_ESTATUTARIA,
        dlpa=ClassificacaoDlpa.RESERVA_ESTATUTARIA,
    )
    _lancar(
        empresa, date(2026, 3, 26), "Entre reservas", contas["reserva_legal"], estatutaria, "100.00"
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["pares_de_colunas_sem_regra"]
    assert (entrada["origem"], entrada["destino"]) == ("reserva_legal", "reserva_estatutaria")
    assert entrada["origem_titulo"] == "Reserva legal"
    assert entrada["destino_titulo"] == "Reserva estatutária"
    assert len(entrada["lancamentos"]) == 1
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    # O saldo final NÃO depende de a linha ter sido decidida.
    assert dmpl["saldo_final"]["valores"]["reserva_estatutaria"] == _dec("100.00")
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("1150.00")


def test_capital_para_reserva_nao_tem_regra():
    """A orientação do par importa: lucros → capital é aumento; capital →
    reserva não existe."""
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 26),
        "Capital para reserva",
        contas["capital"],
        contas["reserva_legal"],
        "10.00",
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["pares_de_colunas_sem_regra"]
    assert (entrada["origem"], entrada["destino"]) == ("capital_social", "reserva_legal")


def test_lancamento_ambiguo_veta_e_nomeia_o_lancamento_e_as_colunas():
    empresa, contas, _ = _caso_a()
    agio = _conta(empresa, "3.7", "Ágio", PL, C, dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES)
    ambiguo = _lancar_itens(
        empresa,
        date(2026, 3, 27),
        "Dois débitos e dois créditos em colunas",
        [
            (contas["lucros"], "D", "100.00"),
            (contas["reserva_legal"], "D", "50.00"),
            (contas["capital"], "C", "70.00"),
            (agio, "C", "80.00"),
        ],
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["lancamentos_ambiguos"]
    assert entrada["lancamento_id"] == ambiguo.id
    assert entrada["data"] == date(2026, 3, 27)
    assert set(entrada["colunas"]) == {
        "Lucros ou prejuízos acumulados",
        "Reserva legal",
        "Capital social",
        "Ágio na emissão de ações",
    }
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    # Nunca rateio presumido: nenhuma célula foi gravada para esse lançamento.
    assert _celula(dmpl, "constituicao_de_reservas", LUCROS) == _dec("-1250.00")
    assert _celula(dmpl, "dividendos", LUCROS) == _dec("-10000.00")
    # E o saldo final continua certo (o lançamento move as colunas, não some).
    assert dmpl["saldo_final"]["valores"][LUCROS] == _dec("13650.00")


def test_dois_debitos_e_dois_creditos_sem_lucros_tambem_e_ambiguo_mas_um_lado_unico_nao():
    empresa, contas, _ = _caso_b()
    _lancar_itens(
        empresa,
        date(2026, 3, 27),
        "Ajustes e tesouraria contra capital e reserva",
        [
            (contas["ajustes"], "D", "30.00"),
            (contas["tesouraria"], "C", "10.00"),
            (contas["capital"], "C", "20.00"),
            (contas["reserva_legal"], "D", "0.01"),
            (contas["caixa"], "C", "0.01"),
        ],
    )
    dmpl = _apurar(empresa)
    # débitos: ajustes (−30), reserva (−0,01); créditos: tesouraria, capital, caixa
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)


def test_divergencia_entre_dlpa_e_dmpl_na_mesma_conta_veta_nomeando_a_conta():
    """Só alcançável por ORM direto (o `clean()` recusa): conta de reserva
    legal na DLPA, mas na coluna estatutária da DMPL."""
    empresa, contas, _ = _caso_a()
    Conta.objects.filter(pk=contas["reserva_legal"].pk).update(
        classificacao_dmpl=COL.RESERVA_ESTATUTARIA
    )
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["contas_com_classificacao_dlpa_e_dmpl_divergentes"]
    assert entrada["conta"] == "3.2"
    assert entrada["classificacao_dlpa"] == "reserva_legal"
    assert entrada["classificacao_dmpl"] == "reserva_estatutaria"
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


def test_conta_na_coluna_de_lucros_sem_ser_conta_sujeito_da_dlpa_veta():
    """O `clean()` aceita (a falta de linha na DLPA não é erro de cadastro),
    mas a coluna de lucros deixaria de ser a DLPA."""
    empresa, contas, _ = _caso_a()
    extra = _conta(empresa, "3.9", "Lucros fora da DLPA", PL, C, dmpl=LUCROS)
    dmpl = _apurar(empresa)
    entradas = dmpl["pendencias"]["contas_com_classificacao_dlpa_e_dmpl_divergentes"]
    assert [e["conta"] for e in entradas] == ["3.9"]
    assert entradas[0]["conta_id"] == extra.id
    assert (
        "contas_com_classificacao_dlpa_e_dmpl_divergentes"
        in avaliar_emissao_da_dmpl(dmpl)["listas_pendentes"]
    )


def test_coluna_gravada_fora_do_enum_veta_e_a_conta_fica_sem_coluna():
    empresa, contas, _ = _caso_a()
    sem_sentido = _conta(empresa, "3.9", "Coluna corrompida", PL, C)
    Conta.objects.filter(pk=sem_sentido.pk).update(classificacao_dmpl="coluna_inventada")
    _lancar(empresa, date(2026, 3, 28), "Movimento", contas["caixa"], sem_sentido, "15.00")
    dmpl = _apurar(empresa)
    (entrada,) = dmpl["pendencias"]["contas_com_classificacao_dmpl_desconhecida"]
    assert entrada["conta"] == "3.9"
    assert entrada["classificacao_dmpl"] == "coluna_inventada"
    assert "coluna_inventada" not in {c["chave"] for c in dmpl["colunas"]}
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False


# ---------------------------------------------------------------------------
# Critério 5 — norma por vigência, com adoção antecipada
# ---------------------------------------------------------------------------


def test_norma_de_2026_cita_a_nbc_tg_26_r5():
    empresa = _empresa()
    norma = norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2026, 1, 1))
    assert norma["norma"] == "NBC TG 26 (R5)"
    assert norma["chave"] == "nbc_tg_26_r5"
    assert norma["itens_da_dmpl"] == "106 a 110"
    assert norma["item_das_colunas"] == "106B"
    assert norma["item_da_identificacao"] == "51"
    assert norma["item_da_conciliacao"] == "106(d)"
    assert norma["item_do_dividendo_por_acao"] == "107"
    assert norma["por_adocao_antecipada"] is False


def test_norma_de_2027_cita_a_nbc_tg_51():
    empresa = _empresa()
    norma = norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2027, 1, 1))
    assert norma["norma"] == "NBC TG 51"
    assert norma["chave"] == "nbc_tg_51"
    assert norma["itens_da_dmpl"] == "107 a 112"
    assert norma["item_das_colunas"] == "111A"
    assert norma["item_da_identificacao"] == "27"
    assert norma["item_da_conciliacao"] == "107(c)"
    assert norma["item_do_dividendo_por_acao"] == "110"
    assert norma["por_adocao_antecipada"] is False


def test_o_limite_e_o_primeiro_de_janeiro_de_2027_inclusive():
    empresa = _empresa()
    assert (
        norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2026, 12, 31))["chave"]
        == "nbc_tg_26_r5"
    )
    assert (
        norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2027, 1, 1))["chave"]
        == "nbc_tg_51"
    )
    assert (
        norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2028, 1, 1))["chave"]
        == "nbc_tg_51"
    )


def test_2026_com_adocao_antecipada_cita_a_nbc_tg_51():
    empresa, contas, gestor = _caso_a()
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    norma = norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2026, 1, 1))
    assert norma["chave"] == "nbc_tg_51"
    assert norma["item_da_identificacao"] == "27"
    assert norma["por_adocao_antecipada"] is True
    # E a apuração carrega a mesma resposta.
    assert _apurar(empresa)["norma"] == norma


def test_adocao_antecipada_em_exercicio_de_2027_nao_e_antecipada():
    empresa, contas, gestor = _caso_a()
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    norma = norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2027, 1, 1))
    assert norma["chave"] == "nbc_tg_51"
    assert norma["por_adocao_antecipada"] is False


def test_a_marca_vale_na_vigencia_do_inicio_do_exercicio_e_nao_na_atual():
    """Mutação típica: ler a vigência ABERTA em vez da que cobre a data. A
    marca está na vigência que começa em 01/06/2026; o exercício de 2026
    começou em 01/01/2026, quando ela ainda não valia."""
    empresa = _empresa()
    contas = _plano_basico(empresa)
    gestor = _gestor(empresa, "gestor-vigencia")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2025, 1, 1),
        usuario=gestor,
    )
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2026, 6, 1),
        adota_nbc_tg_51_antecipadamente=True,
        usuario=gestor,
    )
    assert (
        norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2026, 1, 1))["chave"]
        == "nbc_tg_26_r5"
    )
    assert (
        norma_das_demonstracoes(empresa=empresa, data_inicio_exercicio=date(2026, 6, 1))["chave"]
        == "nbc_tg_51"
    )


def test_a_marca_de_uma_empresa_nao_vaza_para_outra():
    a, _, gestor_a = _caso_a()
    b = _empresa("Outra Empresa Ltda")
    contas_b = _plano_basico(b)
    gestor_b = _gestor(b, "gestor-b-norma")
    _parametro_do_zeramento(b, contas_b, gestor_b)
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=a, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor_a
    )
    assert (
        norma_das_demonstracoes(empresa=b, data_inicio_exercicio=date(2026, 1, 1))["chave"]
        == "nbc_tg_26_r5"
    )


def test_marcar_a_adocao_antecipada_grava_trilha_com_antes_e_depois():
    empresa, _, gestor = _caso_a()
    parametro = definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    parametro.refresh_from_db()
    assert parametro.adota_nbc_tg_51_antecipadamente is True
    registro = RegistroAuditoria.objects.get(
        acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
    )
    assert registro.usuario_id == gestor.pk
    assert registro.escritorio_id == empresa.escritorio_id
    assert registro.objeto_id == str(parametro.pk)
    assert registro.detalhes["adota_nbc_tg_51_antecipadamente_antes"] is False
    assert registro.detalhes["adota_nbc_tg_51_antecipadamente_depois"] is True
    assert registro.detalhes["data_inicio_exercicio"] == "2026-01-01"

    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=False, usuario=gestor
    )
    ultimo = RegistroAuditoria.objects.filter(
        acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
    ).latest("id")
    assert ultimo.detalhes["adota_nbc_tg_51_antecipadamente_antes"] is True
    assert ultimo.detalhes["adota_nbc_tg_51_antecipadamente_depois"] is False


def test_repetir_a_marca_nao_grava_trilha_nova():
    empresa, _, gestor = _caso_a()
    for _ in range(3):
        definir_adocao_antecipada_da_nbc_tg_51(
            empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
        )
    assert (
        RegistroAuditoria.objects.filter(
            acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
        ).count()
        == 1
    )


def test_marcar_a_adocao_sem_parametro_vigente_e_recusado_sem_efeito():
    empresa = _empresa()
    gestor = _gestor(empresa, "gestor-sem-parametro")
    with pytest.raises(ParametroContabilInvalido, match="parâmetro contábil vigente"):
        definir_adocao_antecipada_da_nbc_tg_51(
            empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
        )
    assert not RegistroAuditoria.objects.filter(
        acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
    ).exists()


def test_nova_vigencia_herda_a_marca_a_menos_que_se_diga_o_contrario():
    empresa, contas, gestor = _caso_a()
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    herdada = registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2026, 6, 1),
        usuario=gestor,
    )
    assert herdada.adota_nbc_tg_51_antecipadamente is True
    explicita = registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2026, 9, 1),
        adota_nbc_tg_51_antecipadamente=False,
        usuario=gestor,
    )
    assert explicita.adota_nbc_tg_51_antecipadamente is False


def test_vigencia_sem_marca_nasce_false():
    empresa, contas, gestor = _caso_a()
    assert (
        ParametroContabilEmpresa.objects.get(empresa=empresa).adota_nbc_tg_51_antecipadamente
        is False
    )


# ---------------------------------------------------------------------------
# Porta de gravação da coluna
# ---------------------------------------------------------------------------


def test_classificar_a_coluna_grava_com_trilha_antes_e_depois():
    empresa = _empresa()
    gestor = _gestor(empresa, "gestor-classifica")
    conta = _conta(empresa, "3.9", "Reserva", PL, C)
    classificar_conta_na_dmpl(conta=conta, classificacao=COL.RESERVA_LEGAL, usuario=gestor)
    conta.refresh_from_db()
    assert conta.classificacao_dmpl == "reserva_legal"
    classificar_conta_na_dmpl(conta=conta, classificacao=COL.RESERVA_ESTATUTARIA, usuario=gestor)
    classificar_conta_na_dmpl(conta=conta, classificacao="", usuario=gestor)
    conta.refresh_from_db()
    assert conta.classificacao_dmpl is None

    registros = list(
        RegistroAuditoria.objects.filter(acao="conta.classificacao_dmpl_alterada").order_by("id")
    )
    assert [
        (r.detalhes["classificacao_dmpl_antes"], r.detalhes["classificacao_dmpl_depois"])
        for r in registros
    ] == [
        (None, "reserva_legal"),
        ("reserva_legal", "reserva_estatutaria"),
        ("reserva_estatutaria", None),
    ]
    assert all(r.usuario_id == gestor.pk and r.objeto_id == str(conta.pk) for r in registros)
    assert all(r.escritorio_id == empresa.escritorio_id for r in registros)


def test_classificar_conta_que_nao_e_de_pl_e_recusado_e_nada_muda_nem_grava_trilha():
    empresa = _empresa()
    gestor = _gestor(empresa, "gestor-recusa")
    caixa = _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, D)
    with pytest.raises(ValidationError):
        classificar_conta_na_dmpl(conta=caixa, classificacao=COL.CAPITAL_SOCIAL, usuario=gestor)
    caixa.refresh_from_db()
    assert caixa.classificacao_dmpl is None
    assert not RegistroAuditoria.objects.filter(acao="conta.classificacao_dmpl_alterada").exists()


def test_classificar_coluna_divergente_da_dlpa_e_recusado_pelo_servico():
    empresa, contas, gestor = _caso_a()
    with pytest.raises(ValidationError, match="DLPA"):
        classificar_conta_na_dmpl(
            conta=contas["reserva_legal"], classificacao=COL.CAPITAL_SOCIAL, usuario=gestor
        )
    contas["reserva_legal"].refresh_from_db()
    assert contas["reserva_legal"].classificacao_dmpl == "reserva_legal"


def test_classificar_valor_fora_do_enum_e_recusado():
    empresa = _empresa()
    gestor = _gestor(empresa, "gestor-enum")
    conta = _conta(empresa, "3.9", "Reserva", PL, C)
    with pytest.raises(ValidationError):
        classificar_conta_na_dmpl(conta=conta, classificacao="inventada", usuario=gestor)


def test_a_coluna_vale_para_a_conta_exata_sem_heranca():
    """D5 da DLPA, repetida: classificar a conta pai não classifica a filha;
    a filha com movimento vira conta de PL sem coluna."""
    empresa, contas, _ = _caso_a()
    filha = _conta(empresa, "3.2.1", "Reserva Legal - Subconta", PL, C, pai=contas["reserva_legal"])
    _lancar(empresa, date(2026, 3, 30), "Movimento da filha", contas["caixa"], filha, "5.00")
    dmpl = _apurar(empresa)
    assert [c["conta"] for c in dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]] == [
        "3.2.1"
    ]
    assert dmpl["saldo_final"]["valores"]["reserva_legal"] == _dec("1250.00")


# ---------------------------------------------------------------------------
# Critério 8 — isolamento entre empresas, nos dois sentidos
# ---------------------------------------------------------------------------


def test_dados_de_outra_empresa_nunca_entram_nos_dois_sentidos():
    a, _, _ = _caso_a(valores=("100000.00", "25000.00", "1250.00", "10000.00"))
    b, contas_b, _ = _caso_a(valores=("7000.00", "700.00", "35.00", "70.00"))
    # A empresa B tem uma coluna que a A não tem, com o MESMO código de conta.
    ajustes_b = _conta(b, "3.5", "Ajustes B", PL, C, dmpl=COL.AJUSTES_DE_AVALIACAO_PATRIMONIAL)
    _lancar(b, date(2026, 3, 10), "Reavaliação B", contas_b["imobilizado"], ajustes_b, "999.00")

    dmpl_a = _apurar(a)
    dmpl_b = _apurar(b)

    assert dmpl_a["empresa_id"] == a.id and dmpl_b["empresa_id"] == b.id
    assert dmpl_a["saldo_final"]["total"] == _dec("115000.00")
    assert dmpl_b["saldo_final"]["total"] == _dec("7000.00") + _dec("700.00") - _dec(
        "70.00"
    ) + _dec("999.00")
    assert "ajustes_de_avaliacao_patrimonial" not in {c["chave"] for c in dmpl_a["colunas"]}
    assert "ajustes_de_avaliacao_patrimonial" in {c["chave"] for c in dmpl_b["colunas"]}
    for dmpl, dono in ((dmpl_a, a), (dmpl_b, b)):
        meus = set(LancamentoContabil.objects.filter(empresa=dono).values_list("id", flat=True))
        for linha in dmpl["linhas"]:
            for ids in linha["lancamentos"].values():
                assert set(ids) <= meus
        assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    # Apurar uma não depende de a outra existir: refazer A dá o mesmo resultado.
    assert _apurar(a)["saldo_final"] == dmpl_a["saldo_final"]


def test_item_cruzado_entre_empresas_nunca_entra_em_nenhum_dos_lados():
    """Dado corrompido (só alcançável por ORM direto): partida de uma conta
    da empresa A dentro de um lançamento da B, e o inverso. Os DOIS filtros
    de empresa (lançamento E conta) existem por isso: nenhum desses itens
    pode mexer em saldo inicial, movimento, conciliação ou pendência de
    ninguém."""
    a, contas_a, _ = _caso_a()
    b, contas_b, _ = _caso_a(valores=("5000.00", "500.00", "25.00", "50.00"))
    antes_a = _apurar(a)
    antes_b = _apurar(b)

    abertura_b = LancamentoContabil.objects.get(empresa=b, historico="Capital integralizado")
    reserva_b = LancamentoContabil.objects.get(empresa=b, historico="Reserva legal")
    abertura_a = LancamentoContabil.objects.get(empresa=a, historico="Capital integralizado")
    reserva_a = LancamentoContabil.objects.get(empresa=a, historico="Reserva legal")
    # Cada partida cruzada vem com uma contrapartida a débito no caixa da
    # MESMA empresa dona da conta cruzada (nunca no da dona do lançamento,
    # que mudaria a leitura legítima dela): o gatilho de partidas dobradas
    # (diferido) exige o lançamento balanceado, e o caixa não é coluna.
    for lancamento, conta, valor, caixa_da_conta in (
        (abertura_b, contas_a["capital"], "777.00", contas_a["caixa"]),  # saldo inicial de A
        (reserva_b, contas_a["capital"], "555.00", contas_a["caixa"]),  # movimento de A
        (reserva_b, contas_a["lucros"], "444.00", contas_a["caixa"]),  # coluna de lucros de A
        (abertura_a, contas_b["capital"], "333.00", contas_b["caixa"]),  # saldo inicial de B
        (reserva_a, contas_b["capital"], "222.00", contas_b["caixa"]),  # movimento de B
    ):
        ItemLancamento.objects.create(
            lancamento=lancamento, conta=conta, tipo=TipoPartida.CREDITO, valor=_dec(valor)
        )
        ItemLancamento.objects.create(
            lancamento=lancamento,
            conta=caixa_da_conta,
            tipo=TipoPartida.DEBITO,
            valor=_dec(valor),
        )

    assert _apurar(a) == antes_a
    assert _apurar(b) == antes_b


def test_conta_com_coluna_de_outra_empresa_nao_cria_pendencia_na_empresa_consultada():
    a, _, _ = _caso_a()
    b = _empresa("Empresa B Sem Plano Nenhum")
    # B tem conta de PL sem coluna, com movimento: pendência de B, nunca de A.
    caixa_b = _conta(b, "1.1", "Caixa B", TipoConta.ATIVO, D)
    pl_b = _conta(b, "3.9", "PL sem coluna B", PL, C)
    _lancar(b, date(2026, 3, 1), "Movimento B", caixa_b, pl_b, "10.00")
    assert _pendencias_nao_vazias(_apurar(a)) == set()
    assert "contas_do_patrimonio_liquido_sem_coluna" in _pendencias_nao_vazias(_apurar(b))


# ---------------------------------------------------------------------------
# Critério 9 — Decimal em todo o cálculo
# ---------------------------------------------------------------------------


def _todos_os_valores_numericos(estrutura):
    if isinstance(estrutura, dict):
        for chave, valor in estrutura.items():
            if chave == "lancamentos":  # ids de lançamento, não dinheiro
                continue
            yield from _todos_os_valores_numericos(valor)
    elif isinstance(estrutura, (list, tuple)):
        for valor in estrutura:
            yield from _todos_os_valores_numericos(valor)
    elif isinstance(estrutura, (int, float, Decimal)) and not isinstance(estrutura, bool):
        yield estrutura


def test_todo_valor_monetario_e_decimal_nunca_float():
    empresa, _, _ = _caso_b()
    dmpl = _apurar(empresa)
    numeros = [
        n
        for n in _todos_os_valores_numericos(
            [
                dmpl["linhas"],
                dmpl["saldo_inicial"],
                dmpl["saldo_final"],
                dmpl["conciliacao"],
                dmpl["avisos"],
            ]
        )
    ]
    assert numeros
    assert all(isinstance(n, Decimal) for n in numeros), [
        n for n in numeros if not isinstance(n, Decimal)
    ]


def test_centavos_somam_exatamente_sem_erro_de_ponto_flutuante():
    """0,10 + 0,20 = 0,30 exato (em float binário daria 0,30000000000000004)."""
    empresa = _empresa()
    contas = _plano_basico(empresa)
    _lancar(empresa, date(2026, 2, 1), "Um", contas["caixa"], contas["capital"], "0.10")
    _lancar(empresa, date(2026, 2, 2), "Dois", contas["caixa"], contas["capital"], "0.20")
    _lancar(empresa, date(2026, 2, 3), "Três", contas["caixa"], contas["capital"], "0.07")
    dmpl = _apurar(empresa)
    assert _celula(dmpl, "aumento_de_capital", "capital_social") == _dec("0.37")
    assert str(_celula(dmpl, "aumento_de_capital", "capital_social")) == "0.37"
    assert dmpl["saldo_final"]["total"] == _dec("0.37")
    assert dmpl["conciliacao"]["total"]["diferenca"] == 0


# ---------------------------------------------------------------------------
# Custo constante
# ---------------------------------------------------------------------------


def test_o_numero_de_consultas_nao_cresce_com_o_numero_de_lancamentos():
    empresa, contas, _ = _caso_a()
    with CaptureQueriesContext(connection) as poucos:
        _apurar(empresa)
    for dia in range(1, 25):
        _lancar(
            empresa,
            date(2026, 2, dia),
            f"Aumento {dia}",
            contas["caixa"],
            contas["capital"],
            "1.00",
        )
        _lancar(
            empresa,
            date(2026, 2, dia),
            f"Reserva {dia}",
            contas["lucros"],
            contas["reserva_legal"],
            "1.00",
        )
    with CaptureQueriesContext(connection) as muitos:
        _apurar(empresa)
    assert len(muitos) == len(poucos), (len(poucos), len(muitos))
