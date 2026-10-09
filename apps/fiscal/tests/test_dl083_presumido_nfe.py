"""DL-083 (frente A), Presumido: a receita de NF-e entra pela atividade de presunção da natureza.

Critérios 5 e 6 do plano (docs/planos/DL-083-receita-de-nfe-no-presumido.md):
- trimestre com NFS-e e NF-e (revenda a 8% e combustível para consumo a 1,6%) bate ao centavo com a
  conta feita À MÃO, no IRPJ, no adicional, na CSLL e na parcela da LC 224;
- devolução deduz no trimestre dela, o excedente passa ao seguinte, e o saldo do ano vira aviso;
- cancelamento deduz na origem;
- devolução de combustível, serviço conjugado e NF-e não escriturada recusam, cada um com o motivo.

Os valores esperados são escritos à mão nos testes, em centavos, com a conta em comentário.
Nenhum teste calcula o esperado chamando a função de produção. Dados sintéticos: o CNPJ da empresa
é o do prestador de teste (`xml_sinteticos`), e as notas são geradas por `xml_nfe_dl081`.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as nfe_servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import (
    CATALOGO_NATUREZA_NFE,
    EventoNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
COMBUSTIVEIS = tab.REVENDA_COMBUSTIVEIS
SERVICOS = tab.SERVICOS_GERAIS
D = Decimal


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-dl083-presumido")


@pytest.fixture
def empresa(escritorio_a, gestor):
    """Lucro Presumido em 2026, critério de competência. A atividade padrão é SERVIÇOS GERAIS (32%),
    que é a das NFS-e. A receita de NF-e não usa o padrão: vem da natureza de cada item."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Presumida DL083 Ltda", cnpj=CNPJ_PRESTADOR_PADRAO
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    presumido_servico.definir_criterio(empresa, 2026, "competencia", gestor)
    presumido_servico.criar_atividade(
        empresa, {"atividade": SERVICOS, "inicio": date(2026, 1, 1), "padrao": True}, gestor
    )
    return empresa


def _nfe(escritorio, gestor, empresa, *, numero, valor, dh_emi, cfop="5102", tp_nf="1", fin="1"):
    """NF-e recebida pela recepção real, com a empresa como emitente (saída própria ou entrada)."""
    return receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop=cfop, vprod=valor, icms_xml=xml.icms(csosn="102"))],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
            emitente=("CNPJ", empresa.cnpj),
            tp_nf=tp_nf,
            fin_nfe=fin,
        ),
    )


def efetivar_nfe(escritorio, gestor, empresa, *, natureza, **dados):
    """NF-e com a natureza confirmada em todos os itens, e efetivada pelo serviço real."""
    documento = _nfe(escritorio, gestor, empresa, **dados)
    esc = nfe_servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    return nfe_servico.efetivar(esc, usuario=gestor)


def cancelar(escritorio, documento, empresa):
    """Evento de cancelamento da NF-e (110111, c_stat 135), como o de `test_dl081_receita`."""
    EventoNFe.objects.create(
        escritorio=escritorio,
        identificador=f"ID110111{documento.chave}01",
        tp_evento="110111",
        n_seq_evento=1,
        chave=documento.chave,
        dh_evento=documento.dh_emissao,
        autor_tipo_documento="CNPJ",
        autor_documento=empresa.cnpj,
        c_stat="135",
        xml_original=b"<evento-sintetico/>",
        sha256_arquivo="1" * 64,
    )


def _apurar(empresa, trimestre):
    return presumido_servico.apurar_trimestre(empresa, 2026, trimestre)


# ---------------------------------------------------------------------------------------------
# Mapeamento natureza -> atividade, num lugar só (HI-134)
# ---------------------------------------------------------------------------------------------


def test_toda_natureza_do_catalogo_tem_destino_definido_no_presumido():
    """Cada natureza cai em exatamente um destino: mapeada para uma atividade, dedução, não receita
    ou recusa. O mapa esperado é escrito à mão, e nenhuma natureza fica sem destino."""
    mapeadas = {
        NaturezaOperacaoNFe.REVENDA: COMERCIO,
        NaturezaOperacaoNFe.PRODUCAO_PROPRIA: COMERCIO,
        NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO: COMERCIO,
        NaturezaOperacaoNFe.SUBSTITUTO_ST: COMERCIO,
        NaturezaOperacaoNFe.MONOFASICO: COMERCIO,
        NaturezaOperacaoNFe.EXPORTACAO_DIRETA: COMERCIO,
        NaturezaOperacaoNFe.COMERCIAL_EXPORTADORA: COMERCIO,
        NaturezaOperacaoNFe.COMBUSTIVEL: COMBUSTIVEIS,
        NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA: COMERCIO,
    }
    deducao = {
        NaturezaOperacaoNFe.DEVOLUCAO_VENDA: COMERCIO,
        # HI-140: a devolução de combustível para consumo deduz da atividade de combustível (1,6%).
        NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO: COMBUSTIVEIS,
    }
    recusa = {NaturezaOperacaoNFe.SERVICO_CONJUGADA}
    nao_receita = {
        NaturezaOperacaoNFe.REMESSA_RETORNO,
        NaturezaOperacaoNFe.TRANSFERENCIA,
        NaturezaOperacaoNFe.BONIFICACAO,
        NaturezaOperacaoNFe.CUPOM_NFCE,
        NaturezaOperacaoNFe.AJUSTE,
    }
    assert set(CATALOGO_NATUREZA_NFE) == set(mapeadas) | set(deducao) | recusa | nao_receita
    for natureza, atividade in mapeadas.items():
        assert CATALOGO_NATUREZA_NFE[natureza].papel == "receita", natureza
        assert CATALOGO_NATUREZA_NFE[natureza].atividade_presumido == atividade, natureza
    for natureza, atividade in deducao.items():
        assert CATALOGO_NATUREZA_NFE[natureza].papel == "deducao", natureza
        assert CATALOGO_NATUREZA_NFE[natureza].atividade_presumido == atividade, natureza
    for natureza in recusa:
        # Receita sem atividade informada: a apuração recusa (`servico_conjugada`).
        assert CATALOGO_NATUREZA_NFE[natureza].papel == "receita", natureza
        assert CATALOGO_NATUREZA_NFE[natureza].atividade_presumido is None, natureza
    for natureza in nao_receita:
        assert CATALOGO_NATUREZA_NFE[natureza].papel == "nao_receita", natureza
        assert CATALOGO_NATUREZA_NFE[natureza].atividade_presumido is None, natureza


def test_aliquotas_das_atividades_de_combustivel_e_comercio_com_fonte_na_tabela():
    """1,6% para a revenda de combustível (consumo) e 8% para comércio e indústria no IRPJ; 12% de
    CSLL nas duas. Os números vêm da tabela, com fonte (Lei 9.249, art. 15, § 1º, I)."""
    assert tab.ATIVIDADES_POR_CODIGO[COMBUSTIVEIS].irpj == D("0.016")
    assert tab.ATIVIDADES_POR_CODIGO[COMBUSTIVEIS].csll == D("0.12")
    assert tab.ATIVIDADES_POR_CODIGO[COMERCIO].irpj == D("0.08")
    assert tab.ATIVIDADES_POR_CODIGO[COMERCIO].csll == D("0.12")


# ---------------------------------------------------------------------------------------------
# Critério 5: trimestre com NFS-e e NF-e, conta à mão (IRPJ, adicional, CSLL, parcela LC 224)
# ---------------------------------------------------------------------------------------------


def test_trimestre_com_nfse_e_nfe_bate_ao_centavo_com_a_conta_a_mao(empresa, escritorio_a, gestor):
    """Caso com excedente da LC 224. O 1º trimestre tem exatamente 1.250.000,00 (sobra zero), e o
    2º recebe: revenda 1.200.000,00 (8%), combustível para consumo 100.000,00 (1,6%) e NFS-e
    100.000,00 (32%). Receita do 2º trimestre: 1.400.000,00. Excedente: 150.000,00.

    Conta à mão, em centavos:
      rateio do excedente (ordem do catálogo: comércio, combustível, serviços):
        comércio     150.000,00 x 1.200.000 / 1.400.000 = 128.571,43
        combustível  150.000,00 x   100.000 / 1.400.000 =  10.714,29
        serviços     150.000,00 − 128.571,43 − 10.714,29 = 10.714,28

      IRPJ, sem acréscimo (receita x alíquota):
        comércio 1.200.000,00 x 8%    =  96.000,00
        combustível 100.000,00 x 1,6% =   1.600,00
        serviços 100.000,00 x 32%     =  32.000,00
        base = 129.600,00; principal 15% = 19.440,00
        adicional = (129.600,00 − 20.000 x 3) x 10% = 6.960,00
        IRPJ sem LC 224 = 26.400,00

      IRPJ, com acréscimo de 10% na alíquota (x 1,10) sobre o excedente:
        comércio    (1.200.000,00 − 128.571,43) x 8%  = 85.714,29
                    excedente 128.571,43 x 8,8%            = 11.314,29
        combustível (100.000,00 − 10.714,29) x 1,6%   =  1.428,57
                    excedente  10.714,29 x 1,76%           =    188,57
        serviços    (100.000,00 − 10.714,28) x 32%    = 28.571,43
                    excedente  10.714,28 x 35,2%           =  3.771,43
        base = 130.988,58; principal 15% = 19.648,29
        adicional = (130.988,58 − 60.000,00) x 10% = 7.098,86
        IRPJ com LC 224 = 26.747,15; parcela da LC 224 = 26.747,15 − 26.400,00 = 347,15

      CSLL, no 2º trimestre (acréscimo a partir de 01/04/2026), 9% sobre a base:
        sem: 1.200.000 x 12% + 100.000 x 12% + 100.000 x 32% = 188.000,00 → 16.920,00
        com: comércio 1.071.428,57 x 12% = 128.571,43, excedente 128.571,43 x 13,2% = 16.971,43;
             combustível 89.285,71 x 12% = 10.714,29, excedente 10.714,29 x 13,2% = 1.414,29;
             serviços 28.571,43 + 3.771,43. Base = 190.014,30; CSLL 9% = 17.101,29
        parcela da LC 224 = 17.101,29 − 16.920,00 = 181,29
    """
    nota_efetivada(escritorio_a, empresa, gestor, 1, v_serv="1250000.00", d_compet="2026-01-15")
    nota_efetivada(escritorio_a, empresa, gestor, 2, v_serv="100000.00", d_compet="2026-06-15")
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=21,
        valor="1200000.00",
        dh_emi="2026-04-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=22,
        valor="100000.00",
        dh_emi="2026-05-10T10:00:00-03:00",
        cfop="5656",
    )

    apuracao = _apurar(empresa, 2)
    assert apuracao.recusas == ()
    irpj, csll = apuracao.irpj, apuracao.csll

    assert irpj.receita_presumida == D("1400000.00")
    assert [(linha.atividade, linha.receita) for linha in irpj.memoria_sem_lc224] == [
        (COMERCIO, D("1200000.00")),
        (COMBUSTIVEIS, D("100000.00")),
        (SERVICOS, D("100000.00")),
    ]
    assert irpj.base_sem_lc224 == D("129600.00")
    assert irpj.imposto_sem_lc224 == D("26400.00")
    assert irpj.base_com_lc224 == D("130988.58")
    assert irpj.adicional_com_lc224 == D("7098.86")
    assert irpj.imposto_com_lc224 == D("26747.15")
    assert irpj.parcela_lc224 == D("347.15")

    assert csll.imposto_sem_lc224 == D("16920.00")
    assert csll.imposto_com_lc224 == D("17101.29")
    assert csll.parcela_lc224 == D("181.29")


def test_nfe_entra_com_a_natureza_e_nao_com_o_padrao_da_empresa(empresa, escritorio_a, gestor):
    """A NF-e de revenda cai em comércio (8%), e não em serviços, que é a atividade padrão da
    empresa. A memória mostra a origem "NF-e", a natureza, a atividade e o valor de cada linha."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=23,
        valor="5000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=24,
        valor="3000.00",
        dh_emi="2026-02-11T10:00:00-03:00",
        cfop="5656",
    )
    apuracao = _apurar(empresa, 1)
    assert apuracao.recusas == ()
    assert [(n.origem, n.natureza, n.atividade, n.valor) for n in apuracao.nfe] == [
        ("NF-e", NaturezaOperacaoNFe.REVENDA, COMERCIO, D("5000.00")),
        ("NF-e", NaturezaOperacaoNFe.COMBUSTIVEL, COMBUSTIVEIS, D("3000.00")),
    ]
    # IRPJ: comércio 5.000,00 x 8% = 400,00; combustível 3.000,00 x 1,6% = 48,00.
    assert apuracao.irpj.base_sem_lc224 == D("448.00")


# ---------------------------------------------------------------------------------------------
# Critério 5: devolução deduz no trimestre dela; excedente passa; saldo do ano vira aviso
# ---------------------------------------------------------------------------------------------


def test_devolucao_deduz_no_trimestre_dela_e_nao_no_da_venda(empresa, escritorio_a, gestor):
    """Venda de 100.000,00 em fevereiro (1º tri). Em abril (2º tri), revenda de 50.000,00 e
    devolução de 30.000,00. O 1º trimestre fica com 100.000,00 (não é deduzido da venda), e o 2º
    fica com 50.000,00 − 30.000,00 = 20.000,00."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=31,
        valor="100000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=32,
        valor="50000.00",
        dh_emi="2026-04-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=33,
        valor="30000.00",
        dh_emi="2026-04-20T10:00:00-03:00",
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    primeiro = _apurar(empresa, 1)
    segundo = _apurar(empresa, 2)
    assert primeiro.irpj.receita_presumida == D("100000.00")
    assert segundo.irpj.receita_presumida == D("20000.00")
    assert segundo.devolucao_deduzida == D("30000.00")
    assert segundo.saldo_devolucao_transportado == D("0.00")
    assert primeiro.devolucao_deduzida == D("0.00")
    assert [(n.papel, n.atividade, n.valor) for n in segundo.nfe if n.papel == "deducao"] == [
        ("deducao", COMERCIO, D("30000.00"))
    ]


def test_excedente_da_devolucao_passa_ao_trimestre_seguinte_e_o_saldo_do_ano_vira_aviso(
    empresa, escritorio_a, gestor
):
    """Venda de 100.000,00 no 1º trimestre. Devolução de 150.000,00 no 2º (sem venda), e venda de
    120.000,00 no 3º.
      2º: pool 0; a devolução não tem o que deduzir, e passa 150.000,00.
      3º: pool 120.000,00; absorve 120.000,00; passa 30.000,00.
      4º: pool 0; o saldo de 30.000,00 não coube no ano, e vira aviso no 4º trimestre."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=41,
        valor="100000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=42,
        valor="150000.00",
        dh_emi="2026-05-10T10:00:00-03:00",
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=43,
        valor="120000.00",
        dh_emi="2026-07-10T10:00:00-03:00",
    )

    segundo = _apurar(empresa, 2)
    assert segundo.devolucao_deduzida == D("0.00")
    assert segundo.saldo_devolucao_transportado == D("150000.00")
    assert segundo.irpj.receita_presumida == D("0.00")

    terceiro = _apurar(empresa, 3)
    assert terceiro.devolucao_deduzida == D("120000.00")
    assert terceiro.saldo_devolucao_transportado == D("30000.00")
    assert terceiro.irpj.receita_presumida == D("0.00")

    quarto = _apurar(empresa, 4)
    assert quarto.saldo_devolucao_transportado == D("30000.00")
    avisos = " ".join(quarto.avisos)
    assert "Saldo de devolução de NF-e que não coube na receita do ano" in avisos
    assert "R$ 30.000,00" in avisos
    # Antes do 4º trimestre, o saldo ainda pode ser absorvido: não há aviso de fim de ano.
    assert "não coube na receita do ano" not in " ".join(terceiro.avisos)


# ---------------------------------------------------------------------------------------------
# Critério 5: cancelamento deduz na origem
# ---------------------------------------------------------------------------------------------


def test_venda_cancelada_depois_de_escriturada_sai_da_origem(empresa, escritorio_a, gestor):
    esc = efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=51,
        valor="100000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    cancelar(escritorio_a, esc.vinculo.documento, empresa)
    apuracao = _apurar(empresa, 1)
    assert apuracao.nfe == ()
    assert apuracao.irpj.receita_presumida == D("0.00")


def test_devolucao_cancelada_nao_deduz_no_trimestre_dela(empresa, escritorio_a, gestor):
    """Venda de 50.000,00 e devolução de 30.000,00 no mesmo trimestre. Cancelada a devolução, a
    dedução some: o trimestre fica com 50.000,00."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=52,
        valor="50000.00",
        dh_emi="2026-04-10T10:00:00-03:00",
    )
    devolucao = efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=53,
        valor="30000.00",
        dh_emi="2026-04-20T10:00:00-03:00",
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    assert _apurar(empresa, 2).irpj.receita_presumida == D("20000.00")
    cancelar(escritorio_a, devolucao.vinculo.documento, empresa)
    apuracao = _apurar(empresa, 2)
    assert apuracao.irpj.receita_presumida == D("50000.00")
    assert apuracao.devolucao_deduzida == D("0.00")


# ---------------------------------------------------------------------------------------------
# Critério 6: recusas nomeadas
# ---------------------------------------------------------------------------------------------


def test_devolucao_de_combustivel_nao_recusa_mais_e_avisa_quando_consumo_ficou_como_revenda(
    empresa, escritorio_a, gestor
):
    """HI-140 (substitui a recusa `devolucao_combustivel`, que não tinha caminho): CFOP 1.662 como
    `devolucao_venda` (8%) não recusa, e a memória avisa para o contador conferir a natureza.

    Sem receita no trimestre, a devolução fica como saldo, na atividade de comércio (8%).
    """
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=61,
        valor="10000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
        cfop="1662",
        tp_nf="0",
        fin="4",
    )
    apuracao = _apurar(empresa, 1)
    assert "devolucao_combustivel" not in {r.codigo for r in apuracao.recusas}
    assert apuracao.irpj is not None
    assert "devolução com destinação a consumo deduzida a 8%: confira a natureza (NF-e nº 61)" in (
        apuracao.avisos
    )
    assert apuracao.saldo_por_atividade == ((COMERCIO, D("10000.00")),)


def test_devolucao_de_combustivel_para_consumo_deduz_da_atividade_de_combustivel(
    empresa, escritorio_a, gestor
):
    """HI-140: a devolução de 10.000,00 (CFOP 1.662), com a natureza de consumo, deduz do 1,6%, a
    atividade da venda de combustível. A receita de comércio de 100.000,00 não é tocada."""
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=60,
        valor="100000.00",
        dh_emi="2026-02-05T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=62,
        valor="50000.00",
        dh_emi="2026-02-12T10:00:00-03:00",
    )
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
        numero=61,
        valor="10000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
        cfop="1662",
        tp_nf="0",
        fin="4",
    )
    apuracao = _apurar(empresa, 1)
    assert apuracao.irpj is not None
    # A devolução de 1,6% deduz da receita de combustível (50.000,00), não da de comércio.
    assert apuracao.devolucao_por_atividade == ((COMBUSTIVEIS, D("10000.00")),)
    assert apuracao.saldo_por_atividade == ((COMBUSTIVEIS, D("0.00")),)
    assert apuracao.devolucao_deduzida == D("10000.00")
    assert not any("confira a natureza" in aviso for aviso in apuracao.avisos)


def test_servico_conjugado_recusa_com_o_motivo(empresa, escritorio_a, gestor):
    efetivar_nfe(
        escritorio_a,
        gestor,
        empresa,
        natureza=NaturezaOperacaoNFe.SERVICO_CONJUGADA,
        numero=62,
        valor="5000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    apuracao = _apurar(empresa, 1)
    assert apuracao.situacao == "parcial"
    assert apuracao.irpj is None
    recusas = {r.codigo: r.mensagem for r in apuracao.recusas}
    assert (
        recusas["servico_conjugada"]
        == "serviço em NF-e conjugada: atividade de presunção a informar"
    )


def test_nfe_do_trimestre_ainda_em_rascunho_recusa_com_o_motivo(empresa, escritorio_a, gestor):
    documento = _nfe(
        escritorio_a,
        gestor,
        empresa,
        numero=63,
        valor="800.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    nfe_servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    apuracao = _apurar(empresa, 1)
    assert apuracao.situacao == "parcial"
    recusas = {r.codigo: r.mensagem for r in apuracao.recusas}
    assert recusas["nfe_nao_escriturada"] == "NF-e do trimestre ainda não escriturada"
    assert apuracao.irpj is None


def test_trimestre_sem_nfe_nao_ganha_nenhuma_recusa_nova(empresa):
    """Sem NF-e nenhuma, o trimestre não tem recusa de NF-e, e a apuração não muda de forma."""
    for trimestre in (1, 2, 3, 4):
        apuracao = _apurar(empresa, trimestre)
        codigos = {r.codigo for r in apuracao.recusas}
        assert not codigos & {"nfe_nao_escriturada", "devolucao_combustivel", "servico_conjugada"}
        assert apuracao.nfe == ()
        assert apuracao.devolucao_deduzida == D("0.00")
        assert apuracao.saldo_devolucao_transportado == D("0.00")
