"""DL-091 (frente A1), escrituração de ENTRADA: elegibilidade, data de entrada, CFOP de entrada,
memória de crédito, avisos, efetivação, estorno, devolução de compra e imutabilidade.

Tudo sintético, com os valores escritos à mão (não copiados do código). Plano:
docs/planos/DL-091-nfe-de-entrada.md (critérios 3 a 7, 9 e 10). A regra de receita (critério 1)
está em `test_dl091_receita.py`; a API, em `test_dl091_api.py`.
"""

import inspect
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import (
    Empresa,
    Estabelecimento,
    HistoricoRegimeTributario,
    RegimeTributario,
    TipoEstabelecimento,
)
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import receita as receita_servico
from apps.fiscal.itens_nfe import ler_itens
from apps.fiscal.models import (
    CATALOGO_NATUREZA_NFE,
    NATUREZAS_DE_ENTRADA,
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    MarcaCreditoEntrada,
    MemoriaEntradaItemNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    PapelNFe,
    TipoEscrituracaoNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A, chave_nfe

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe
DH_EMI = "2026-03-15T10:00:00-03:00"  # 15/03/2026, em São Paulo
ICMS_00 = "<modBC>3</modBC><vBC>100.00</vBC><pICMS>18.00</pICMS><vICMS>18.00</vICMS>"


@pytest.fixture
def empresa(escritorio_a):
    """Compradora: a empresa destinatária das notas de compra (CNPJ de destinatário sintético)."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Compradora DL091 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _matriz(empresa, escritorio, uf: str):
    """A matriz é a fonte da UF da empresa (aviso de outro estado)."""
    return Estabelecimento.objects.create(
        empresa=empresa,
        escritorio=escritorio,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz sintetica",
        cnpj=CNPJ_DESTINATARIO_A,
        uf=uf,
    )


def _chave(cuf: str, numero: str, modelo: str, emitente_cnpj: str) -> str:
    """A chave traz o CNPJ do EMITENTE da nota (a recepção confere). cUF é a UF do emitente."""
    return chave_nfe(cuf=cuf, emitente=emitente_cnpj, modelo=modelo, numero=numero)


def _nota(
    escritorio,
    usuario,
    empresa,
    *,
    numero="1",
    cfop="5102",
    ncm="22030000",
    icms=None,
    cuf="35",
    crt="3",
    tp_nf="1",
    fin_nfe="1",
    modelo="55",
    vprod="100.00",
    dh_emi=DH_EMI,
    emitente=None,
    destinatario=None,
    pis=None,
    cofins=None,
    ipi="",
):
    """Nota sintética recebida pela recepção real. Padrão: compra de SP (interestadual) para a
    empresa, CRT 3, CST 00 com ICMS destacado de 18,00."""
    det = xml.det(
        1,
        cfop=cfop,
        vprod=vprod,
        ncm=ncm,
        icms_xml=icms or xml.icms(cst="00", filhos=ICMS_00),
        pis_xml=pis,
        cofins_xml=cofins,
        ipi_xml=ipi,
    )
    emit = emitente or ("CNPJ", CNPJ_EMITENTE_A)
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[det],
            vnf=vprod,
            totais={"vProd": vprod},
            chave=_chave(cuf, numero, modelo, emit[1]),
            numero=numero,
            modelo=modelo,
            tp_nf=tp_nf,
            fin_nfe=fin_nfe,
            dh_emi=dh_emi,
            emitente=emit,
            destinatario=destinatario or ("CNPJ", empresa.cnpj),
            crt=crt,
        ),
    )
    # A recepção não lê os itens; o rascunho lê. Os testes precisam deles para olhar cada item.
    ler_itens(documento)
    return documento


def _rascunho(escritorio, usuario, empresa, **dados):
    documento = _nota(escritorio, usuario, empresa, **dados)
    return servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)


def _item(escritorio, usuario, empresa, **dados) -> ItemNFe:
    documento = _nota(escritorio, usuario, empresa, **dados)
    return documento.itens.get(n_item=1)


def _confirmar(escrituracao, natureza, cfop, usuario):
    """Confirma natureza e CFOP de entrada de TODOS os itens (o caminho da API e da tela)."""
    ids = list(
        NaturezaItemNFe.objects.filter(escrituracao=escrituracao).values_list("item_id", flat=True)
    )
    return entradas.definir_natureza_de_entrada(escrituracao, natureza, cfop, ids, usuario=usuario)


# ---------------------------------------------------------------------------
# Elegibilidade e recusas (critério 3)
# ---------------------------------------------------------------------------


def test_compra_de_nfe_55_com_finnfe_1_e_escrituravel(escritorio_a, usuario_gestor_a, empresa):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa)
    assert servico.tipo_da_nota(documento, PapelNFe.DESTINATARIO) == TipoEscrituracaoNFe.ENTRADA


def test_nfce_destinataria_tpnf0_e_finnfe_2_recusadas_com_motivo_nomeado(
    escritorio_a, usuario_gestor_a, empresa
):
    nfce = _nota(escritorio_a, usuario_gestor_a, empresa, modelo="65", numero="2")
    assert servico.tipo_da_nota(nfce, PapelNFe.DESTINATARIO) is None
    assert "NFC-e em que a empresa é destinatária" in servico.motivo_fora_da_escrituracao(
        nfce, PapelNFe.DESTINATARIO
    )

    tp0 = _nota(escritorio_a, usuario_gestor_a, empresa, tp_nf="0", numero="3")
    assert servico.tipo_da_nota(tp0, PapelNFe.DESTINATARIO) is None
    assert "tpNF 0" in servico.motivo_fora_da_escrituracao(tp0, PapelNFe.DESTINATARIO)

    ajuste = _nota(escritorio_a, usuario_gestor_a, empresa, fin_nfe="2", numero="4")
    assert servico.tipo_da_nota(ajuste, PapelNFe.DESTINATARIO) is None
    assert "finNFe 2" in servico.motivo_fora_da_escrituracao(ajuste, PapelNFe.DESTINATARIO)


def test_devolucao_de_venda_recebida_continua_devolucao_e_nao_vira_entrada(
    escritorio_a, usuario_gestor_a, empresa
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, fin_nfe="4", cfop="1202")
    assert servico.tipo_da_nota(documento, PapelNFe.DESTINATARIO) == TipoEscrituracaoNFe.DEVOLUCAO


def _saida_finnfe_4(escritorio, usuario, empresa, *, cfop, numero, ncm="22030000"):
    """Saída própria (a empresa emite, tpNF 1) com finNFe 4: devolução ou retorno genérico."""
    return _nota(
        escritorio,
        usuario,
        empresa,
        cfop=cfop,
        ncm=ncm,
        tp_nf="1",
        fin_nfe="4",
        numero=numero,
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )


def test_finnfe_4_em_saida_com_cfop_de_devolucao_de_compra_e_escrituravel_so_com_devolucao(
    escritorio_a, usuario_gestor_a, empresa
):
    """DL-091, contrato do arquiteto: a devolução de compra do cliente sai com tpNF 1 e finNFe 4.
    É DEVOLUCAO_COMPRA, e só a natureza `devolucao_compra` cabe. Revenda não cabe: é o que protege a
    receita."""
    documento = _saida_finnfe_4(escritorio_a, usuario_gestor_a, empresa, cfop="5202", numero="5")
    assert (
        servico.tipo_da_nota(documento, PapelNFe.EMITENTE) == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    assert esc.tipo == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA
    item = documento.itens.get(n_item=1)
    assert servico.sugerir_natureza_item(documento, item).natureza == N.DEVOLUCAO_COMPRA

    ids = [item.pk]
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.definir_natureza(esc, N.REVENDA, ids, usuario=usuario_gestor_a)
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.definir_natureza(esc, N.COMBUSTIVEL, ids, usuario=usuario_gestor_a)
    servico.definir_natureza(esc, N.DEVOLUCAO_COMPRA, ids, usuario=usuario_gestor_a)
    efetivada = servico.efetivar(esc, usuario=usuario_gestor_a)
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert efetivada.receita_bruta == Decimal("0.00") and efetivada.devolucao == Decimal("0.00")


def test_finnfe_4_com_cfop_de_retorno_nao_devolucao_fica_sem_sugestao_e_nao_efetiva(
    escritorio_a, usuario_gestor_a, empresa
):
    """DL-091, contrato (item 3): retorno em finNFe 4 que não é devolução de compra (5.915, remessa
    para conserto) não tem sugestão, com o motivo nomeado. Sem natureza, a nota não efetiva."""
    documento = _saida_finnfe_4(escritorio_a, usuario_gestor_a, empresa, cfop="5915", numero="6")
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    sugestao = servico.sugerir_natureza_item(documento, documento.itens.get(n_item=1))
    assert sugestao.natureza is None
    assert "retorno em finNFe 4: fora do catálogo do corte 1" in sugestao.motivo
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=usuario_gestor_a)
    assert "Falta a natureza" in erro.value.mensagem


def test_naturezas_permitidas_de_devolucao_de_compra_sao_so_devolucao_de_compra():
    """A regra que protege a receita: finNFe 4 em saída só leva devolucao_compra."""
    assert servico.naturezas_permitidas(TipoEscrituracaoNFe.DEVOLUCAO_COMPRA) == {
        N.DEVOLUCAO_COMPRA
    }
    saida = servico.naturezas_permitidas(TipoEscrituracaoNFe.SAIDA_PROPRIA)
    assert N.REVENDA in saida and N.DEVOLUCAO_COMPRA in saida  # finNFe 1 continua como antes


def test_uma_escrituracao_ativa_por_nota(escritorio_a, usuario_gestor_a, empresa):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa)
    primeira = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    segunda = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    assert primeira.pk == segunda.pk
    assert segunda.criada_agora is False
    assert EscrituracaoNFe.objects.filter(vinculo=vinculo(documento, empresa)).count() == 1


def test_banco_recusa_entrada_sem_data_de_entrada(escritorio_a, usuario_gestor_a, empresa):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    with pytest.raises(IntegrityError), transaction.atomic():
        EscrituracaoNFe.objects.filter(pk=esc.pk).update(data_entrada=None)


# ---------------------------------------------------------------------------
# Data de entrada e competência (critério 6; HI-158)
# ---------------------------------------------------------------------------


def test_data_de_entrada_padrao_e_a_emissao(escritorio_a, usuario_gestor_a, empresa):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    assert esc.tipo == TipoEscrituracaoNFe.ENTRADA
    assert esc.data_entrada == date(2026, 3, 15)


def test_competencia_e_o_mes_da_data_de_entrada_e_nao_o_da_emissao(
    escritorio_a, usuario_gestor_a, empresa
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(
        vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 4, 2)
    )
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    efetivada = servico.efetivar(esc, usuario=usuario_gestor_a)
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert efetivada.competencia == date(2026, 4, 1)
    assert efetivada.data_emissao == date(2026, 3, 15)


def test_data_de_entrada_anterior_a_emissao_e_recusada(escritorio_a, usuario_gestor_a, empresa):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa)
    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        servico.criar_rascunho(
            vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 3, 14)
        )
    assert erro.value.mensagem == entradas.MOTIVO_DATA_ANTERIOR_A_EMISSAO


def test_data_de_entrada_so_existe_na_escrituracao_de_entrada(
    escritorio_a, usuario_gestor_a, empresa
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, fin_nfe="4", cfop="1202")
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.criar_rascunho(
            vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 3, 20)
        )


def test_efetivacao_recusa_data_de_entrada_anterior_a_emissao(
    escritorio_a, usuario_gestor_a, empresa
):
    """A API e o serviço recusam; aqui a data é forçada no banco para provar a defesa da
    efetivação."""
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    EscrituracaoNFe.objects.filter(pk=esc.pk).update(data_entrada=date(2026, 3, 1))
    esc.refresh_from_db()
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=usuario_gestor_a)
    assert erro.value.mensagem == entradas.MOTIVO_DATA_ANTERIOR_A_EMISSAO


# ---------------------------------------------------------------------------
# CFOP de entrada (critério 4)
# ---------------------------------------------------------------------------


def _item_sintetico(cfop: str, **dados) -> ItemNFe:
    """Item de nota (não gravado) para as funções puras de CFOP e de sugestão."""
    return ItemNFe(cfop=cfop, n_item=1, **dados)


@pytest.mark.parametrize(
    ("cfop_emitente", "cfop_entrada"),
    [("5102", "1102"), ("6102", "2102"), ("7102", "3102")],
)
def test_primeiro_digito_do_cfop_de_entrada_converte_5_6_7_em_1_2_3(cfop_emitente, cfop_entrada):
    item = _item_sintetico(cfop_emitente)
    assert (
        entradas.validar_cfop_de_entrada(item, N.ENTRADA_COMERCIALIZACAO, cfop_entrada)
        == cfop_entrada
    )


@pytest.mark.parametrize(
    ("cfop_emitente", "cfop_errado"),
    [("5102", "2102"), ("6102", "1102"), ("7102", "1102")],
)
def test_primeiro_digito_errado_e_recusado(cfop_emitente, cfop_errado):
    item = _item_sintetico(cfop_emitente)
    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        entradas.validar_cfop_de_entrada(item, N.ENTRADA_COMERCIALIZACAO, cfop_errado)
    assert "primeiro dígito" in erro.value.mensagem


def test_o_grupo_do_cfop_de_entrada_vem_da_natureza():
    item = _item_sintetico("5102")
    # O mesmo 5.102 vira 1.102 (revenda), 1.556 (consumo) ou 1.551 (ativo), conforme a natureza.
    assert entradas.validar_cfop_de_entrada(item, N.ENTRADA_USO_CONSUMO, "1556") == "1556"
    assert entradas.validar_cfop_de_entrada(item, N.ENTRADA_ATIVO, "1551") == "1551"
    with pytest.raises(servico.EntradaInvalidaNFe):
        entradas.validar_cfop_de_entrada(item, N.ENTRADA_USO_CONSUMO, "1102")
    with pytest.raises(servico.EntradaInvalidaNFe):
        entradas.validar_cfop_de_entrada(item, N.ENTRADA_COMERCIALIZACAO, "1551")


def test_cfop_de_entrada_fora_da_tabela_oficial_e_recusado():
    item = _item_sintetico("5102")
    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        entradas.validar_cfop_de_entrada(item, N.ENTRADA_COMERCIALIZACAO, "1999")
    assert erro.value.mensagem == entradas.MENSAGEM_CFOP_FORA_DA_TABELA


def test_1949_so_e_aceito_na_natureza_de_remessa_e_nunca_e_sugerido():
    item_remessa = _item_sintetico("5949")
    assert (
        entradas.validar_cfop_de_entrada(item_remessa, N.ENTRADA_REMESSA_RETORNO, "1949") == "1949"
    )
    with pytest.raises(servico.EntradaInvalidaNFe):
        entradas.validar_cfop_de_entrada(_item_sintetico("5102"), N.ENTRADA_COMERCIALIZACAO, "1949")
    par = entradas.sugerir_par_de_entrada(None, item_remessa)
    assert par.cfop is None  # 5.949 do emitente não gera sugestão; 1.949 só por escolha


def test_cfop_do_emitente_nunca_muda_e_a_confirmacao_so_grava_o_do_destinatario(
    escritorio_a, usuario_gestor_a, empresa
):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa, cfop="5102")
    antes = ItemNFe.objects.get(documento=esc.vinculo.documento, n_item=1).cfop
    _confirmar(esc, N.ENTRADA_USO_CONSUMO, "1556", usuario_gestor_a)
    depois = ItemNFe.objects.get(documento=esc.vinculo.documento, n_item=1)
    assert depois.cfop == antes == "5102"
    assert NaturezaItemNFe.objects.get(escrituracao=esc).cfop_entrada == "1556"


@pytest.mark.parametrize(
    ("cfop", "cst", "csosn", "ncm", "natureza", "cfop_sugerido"),
    [
        ("5102", "00", None, "22030000", N.ENTRADA_COMERCIALIZACAO, "1102"),
        ("6102", "00", None, "22030000", N.ENTRADA_COMERCIALIZACAO, "2102"),
        ("5101", "00", None, "22030000", N.ENTRADA_INDUSTRIALIZACAO, "1101"),
        ("5102", "60", None, "22030000", N.ENTRADA_ST, "1403"),
        ("5405", "00", None, "22030000", N.ENTRADA_ST, "1403"),
        ("5910", "00", None, "22030000", N.ENTRADA_BONIFICACAO, "1910"),
        ("5152", "00", None, "22030000", N.ENTRADA_TRANSFERENCIA, "1152"),
        ("5655", "00", None, "27101921", N.ENTRADA_COMBUSTIVEL_REVENDA, "1652"),
        ("5656", "00", None, "27101921", N.ENTRADA_COMBUSTIVEL_CONSUMO, "1653"),
    ],
)
def test_sugestao_do_par_natureza_e_cfop_pelo_cfop_do_emitente(
    cfop, cst, csosn, ncm, natureza, cfop_sugerido
):
    item = _item_sintetico(cfop, cst=cst, csosn=csosn, ncm=ncm)
    par = entradas.sugerir_par_de_entrada(None, item)
    assert (par.natureza, par.cfop) == (natureza, cfop_sugerido)


def test_combustivel_sem_ncm_de_combustivel_nao_tem_sugestao():
    item = _item_sintetico("5655", cst="00", ncm="22030000")
    par = entradas.sugerir_par_de_entrada(None, item)
    assert par.natureza is None and par.cfop is None


def test_sugestao_nao_grava_nada(escritorio_a, usuario_gestor_a, empresa):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    registro = NaturezaItemNFe.objects.get(escrituracao=esc)
    assert registro.natureza == "" and registro.cfop_entrada == ""


# ---------------------------------------------------------------------------
# Memória de crédito (critério 5), escrita à mão
# ---------------------------------------------------------------------------


def _marca(documento, item, natureza):
    marca, credito = entradas.marca_do_credito(documento, item, natureza)
    return marca, credito


def test_e4_com_icms_destacado_nunca_vira_credito_elegivel(escritorio_a, usuario_gestor_a, empresa):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa)
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_USO_CONSUMO) == (
        MarcaCreditoEntrada.VEDADO_ATE_2032,
        None,
    )


def test_fornecedor_do_simples_sem_pcredsn_nunca_vira_credito_elegivel(
    escritorio_a, usuario_gestor_a, empresa
):
    icms = xml.icms(csosn="101", filhos="<vCredICMSSN>5.00</vCredICMSSN>")
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, crt="1", icms=icms)
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO) == (
        MarcaCreditoEntrada.SEM_CREDITO_SEM_PCREDSN,
        None,
    )


def test_fornecedor_do_simples_com_vcredicmssn_limita_ao_valor_informado(
    escritorio_a, usuario_gestor_a, empresa
):
    icms = xml.icms(csosn="101", filhos="<pCredSN>2.8000</pCredSN><vCredICMSSN>28.00</vCredICMSSN>")
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, crt="1", icms=icms, vprod="1000.00")
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO) == (
        MarcaCreditoEntrada.CREDITO_LIMITADO,
        Decimal("28.00"),
    )


def test_cst_60_marca_st_retido_sem_credito(escritorio_a, usuario_gestor_a, empresa):
    icms = xml.icms(cst="60", filhos="<vBCSTRet>100.00</vBCSTRet><vICMSSTRet>18.00</vICMSSTRet>")
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, icms=icms)
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO) == (
        MarcaCreditoEntrada.ST_RETIDO,
        None,
    )


def test_ncm_de_combustivel_da_lista_marca_monofasico(escritorio_a, usuario_gestor_a, empresa):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, ncm="27101921", cfop="5655")
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMBUSTIVEL_REVENDA) == (
        MarcaCreditoEntrada.MONOFASICO,
        None,
    )


def test_regime_normal_com_cst_que_da_credito_pleno_marca_credito_destacado(
    escritorio_a, usuario_gestor_a, empresa
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa)
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO) == (
        MarcaCreditoEntrada.CREDITO_DESTACADO,
        Decimal("18.00"),
    )


def test_consumo_proprio_de_combustivel_nao_gera_credito(escritorio_a, usuario_gestor_a, empresa):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, ncm="22030000")
    item = documento.itens.get(n_item=1)
    assert (
        _marca(documento, item, N.ENTRADA_COMBUSTIVEL_CONSUMO)[0]
        == MarcaCreditoEntrada.NAO_SE_CREDITA
    )


def test_regime_fora_do_crt_conhecido_fica_a_conferir(escritorio_a, usuario_gestor_a, empresa):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, crt=None)
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO)[0] == MarcaCreditoEntrada.A_CONFERIR


def test_memoria_gravada_na_efetivacao_copia_fcp_ipi_pis_cofins_e_e_imutavel(
    escritorio_a, usuario_gestor_a, empresa
):
    icms = xml.icms(
        cst="00",
        filhos="<modBC>3</modBC><vBC>100.00</vBC><pICMS>18.00</pICMS>"
        "<vICMS>18.00</vICMS><vFCP>2.00</vFCP>",
    )
    esc = _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        icms=icms,
        pis="<PIS><PISAliq><CST>01</CST><vPIS>1.65</vPIS></PISAliq></PIS>",
        cofins="<COFINS><COFINSAliq><CST>01</CST><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS>",
    )
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    memoria = MemoriaEntradaItemNFe.objects.get(natureza_item__escrituracao=esc)
    assert memoria.marca_credito == MarcaCreditoEntrada.CREDITO_DESTACADO
    assert memoria.credito_elegivel == Decimal("18.00")
    assert memoria.v_icms == Decimal("18.00") and memoria.v_bc == Decimal("100.00")
    assert memoria.v_fcp == Decimal("2.00")
    assert memoria.cst_pis == "01" and memoria.v_pis == Decimal("1.65")
    assert memoria.cst_cofins == "01" and memoria.v_cofins == Decimal("7.60")
    # Gravada uma vez, e imutável depois: UPDATE e DELETE com a escrituração efetivada são
    # recusados.
    with pytest.raises(IntegrityError), transaction.atomic():
        MemoriaEntradaItemNFe.objects.filter(pk=memoria.pk).update(v_icms=Decimal("0.01"))
    with pytest.raises(IntegrityError), transaction.atomic():
        MemoriaEntradaItemNFe.objects.filter(pk=memoria.pk).delete()


def test_modulo_de_entrada_nao_tem_aliquota_do_tocantins():
    """Nenhum percentual no código da entrada: a memória repete o que a nota destaca."""
    assert "%" not in inspect.getsource(entradas)


# ---------------------------------------------------------------------------
# Avisos nomeados (critério 7; item 6)
# ---------------------------------------------------------------------------


def _com_regime(empresa, regime, dia=date(2026, 1, 1)):
    HistoricoRegimeTributario.objects.create(empresa=empresa, regime=regime, vigencia_inicio=dia)


def test_aviso_de_outro_estado_so_para_optante_do_simples_na_data(
    escritorio_a, usuario_gestor_a, empresa
):
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.SIMPLES_NACIONAL)
    compra_sp = _nota(escritorio_a, usuario_gestor_a, empresa, crt="1", icms=xml.icms(csosn="102"))
    esc = servico.criar_rascunho(vinculo(compra_sp, empresa), usuario=usuario_gestor_a)
    item = compra_sp.itens.get(n_item=1)
    contexto = entradas.contexto_da_entrada(empresa, esc.data_entrada)
    avisos = entradas.avisos_da_entrada(compra_sp, item, N.ENTRADA_COMERCIALIZACAO, contexto)
    assert entradas.AVISO_SIMPLES_OUTRO_ESTADO in avisos

    compra_to = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        crt="1",
        cuf="17",
        numero="20",
        icms=xml.icms(csosn="102"),
    )
    item_to = compra_to.itens.get(n_item=1)
    avisos_to = entradas.avisos_da_entrada(compra_to, item_to, N.ENTRADA_COMERCIALIZACAO, contexto)
    assert entradas.AVISO_SIMPLES_OUTRO_ESTADO not in avisos_to


def test_aviso_de_difal_de_uso_so_no_regime_normal_e_so_com_outro_estado(
    escritorio_a, usuario_gestor_a, empresa
):
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    documento = _nota(escritorio_a, usuario_gestor_a, empresa)
    item = documento.itens.get(n_item=1)
    contexto = entradas.contexto_da_entrada(empresa, date(2026, 3, 15))
    assert entradas.AVISO_NORMAL_OUTRO_ESTADO_USO in entradas.avisos_da_entrada(
        documento, item, N.ENTRADA_USO_CONSUMO, contexto
    )
    assert entradas.AVISO_NORMAL_OUTRO_ESTADO_USO not in entradas.avisos_da_entrada(
        documento, item, N.ENTRADA_COMERCIALIZACAO, contexto
    )


def test_avisos_de_cst_sem_credito_pleno_de_fornecedor_sem_pcredsn_e_de_lubrificante(
    escritorio_a, usuario_gestor_a, empresa
):
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    contexto = entradas.contexto_da_entrada(empresa, date(2026, 3, 15))
    cst40 = _nota(escritorio_a, usuario_gestor_a, empresa, cuf="17", icms=xml.icms(cst="40"))
    assert entradas.AVISO_CST_SEM_CREDITO_PLENO in entradas.avisos_da_entrada(
        cst40, cst40.itens.get(n_item=1), N.ENTRADA_COMERCIALIZACAO, contexto
    )
    simples_sem_pcredsn = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        cuf="17",
        crt="1",
        numero="30",
        icms=xml.icms(csosn="101", filhos="<vCredICMSSN>5.00</vCredICMSSN>"),
    )
    assert entradas.AVISO_SIMPLES_SEM_PCREDSN in entradas.avisos_da_entrada(
        simples_sem_pcredsn,
        simples_sem_pcredsn.itens.get(n_item=1),
        N.ENTRADA_COMERCIALIZACAO,
        contexto,
    )
    lubrificante = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        cuf="17",
        ncm="27101931",
        cfop="5655",
        numero="40",
    )
    assert entradas.AVISO_LUBRIFICANTE_EM_COMBUSTIVEL in entradas.avisos_da_entrada(
        lubrificante, lubrificante.itens.get(n_item=1), N.ENTRADA_COMBUSTIVEL_REVENDA, contexto
    )


def test_uf_do_emitente_incoerente_com_o_cfop_gera_aviso(escritorio_a, usuario_gestor_a, empresa):
    _matriz(empresa, escritorio_a, "TO")
    contexto = entradas.contexto_da_entrada(empresa, date(2026, 3, 15))
    # CFOP 5 (interno) com emitente de SP: incoerente. CFOP 6 com emitente de SP: coerente.
    incoerente = _nota(escritorio_a, usuario_gestor_a, empresa, cfop="5102", numero="50")
    assert entradas.AVISO_UF_INCOERENTE in entradas.avisos_da_entrada(
        incoerente, incoerente.itens.get(n_item=1), N.ENTRADA_COMERCIALIZACAO, contexto
    )
    coerente = _nota(escritorio_a, usuario_gestor_a, empresa, cfop="6102", numero="51")
    assert entradas.AVISO_UF_INCOERENTE not in entradas.avisos_da_entrada(
        coerente, coerente.itens.get(n_item=1), N.ENTRADA_COMERCIALIZACAO, contexto
    )


def test_sem_matriz_com_uf_o_aviso_de_outro_estado_nao_e_inventado(
    escritorio_a, usuario_gestor_a, empresa
):
    _com_regime(empresa, RegimeTributario.SIMPLES_NACIONAL)
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, crt="1", icms=xml.icms(csosn="102"))
    contexto = entradas.contexto_da_entrada(empresa, date(2026, 3, 15))
    avisos = entradas.avisos_da_entrada(
        documento, documento.itens.get(n_item=1), N.ENTRADA_COMERCIALIZACAO, contexto
    )
    assert entradas.AVISO_UF_DA_EMPRESA_NAO_CADASTRADA in avisos
    assert entradas.AVISO_SIMPLES_OUTRO_ESTADO not in avisos


# ---------------------------------------------------------------------------
# Efetivação, estorno e receita (critérios 1, 9)
# ---------------------------------------------------------------------------


def test_efetivar_sem_cfop_de_entrada_e_recusado(escritorio_a, usuario_gestor_a, empresa):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=N.ENTRADA_COMERCIALIZACAO)
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=usuario_gestor_a)
    assert "CFOP de entrada" in erro.value.mensagem


def test_natureza_de_entrada_pelo_servico_generico_e_recusada(
    escritorio_a, usuario_gestor_a, empresa
):
    """Sem o CFOP, a natureza de entrada não pode entrar pelo caminho comum (o lote usa este)."""
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.definir_natureza(esc, N.ENTRADA_COMERCIALIZACAO, ids, usuario=usuario_gestor_a)


def test_efetivar_entrada_nao_chama_o_gatilho_de_mes_confirmado_e_saida_chama(
    escritorio_a, usuario_gestor_a, empresa, monkeypatch
):
    chamadas = []
    monkeypatch.setattr(
        receita_servico,
        "marcar_a_retificar",
        lambda *a, **k: chamadas.append(("retificar", a)),
    )
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    assert chamadas == []  # a compra não muda receita: nenhum mês é marcado a retificar

    # Controle positivo: uma saída efetivada CHAMA o gatilho, então o espião funciona.
    saida = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="60",
        tp_nf="1",
        fin_nfe="1",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
        cfop="5102",
    )
    esc_saida = servico.criar_rascunho(vinculo(saida, empresa), usuario=usuario_gestor_a)
    NaturezaItemNFe.objects.filter(escrituracao=esc_saida).update(natureza=N.REVENDA)
    servico.efetivar(esc_saida, usuario=usuario_gestor_a)
    assert len(chamadas) == 1


def test_estorno_de_entrada_nao_mexe_em_receita_e_mantem_a_memoria(
    escritorio_a, usuario_gestor_a, empresa, monkeypatch
):
    chamadas = []
    monkeypatch.setattr(
        receita_servico,
        "marcar_a_retificar_por_estorno",
        lambda *a, **k: chamadas.append(a),
    )
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    estornada = servico.estornar(esc, "compra lançada em duplicidade", usuario_gestor_a)
    assert estornada.estado == EstadoEscrituracao.ESTORNADA
    assert chamadas == []
    assert MemoriaEntradaItemNFe.objects.filter(natureza_item__escrituracao=esc).count() == 1


def test_efetivacao_de_entrada_grava_trilha_com_receita_nao_afetada(
    escritorio_a, usuario_gestor_a, empresa
):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    registro = RegistroAuditoria.objects.filter(
        acao="escrituracao_nfe.efetivada", objeto_id=str(esc.pk)
    ).latest("pk")
    assert registro.detalhes["receita_nao_afetada"] is True
    assert registro.detalhes["marcas"]


def test_todas_as_naturezas_de_entrada_sao_nao_receita_e_fora_da_saida():
    for natureza in NATUREZAS_DE_ENTRADA:
        assert CATALOGO_NATUREZA_NFE[natureza].papel == "nao_receita"
    saida = servico.naturezas_permitidas(TipoEscrituracaoNFe.SAIDA_PROPRIA)
    assert not (NATUREZAS_DE_ENTRADA & saida)
    assert N.DEVOLUCAO_COMPRA in saida
    assert N.DEVOLUCAO_COMPRA not in servico.naturezas_permitidas(TipoEscrituracaoNFe.ENTRADA)
    assert N.DEVOLUCAO_COMPRA not in servico.naturezas_permitidas(TipoEscrituracaoNFe.DEVOLUCAO)


# ---------------------------------------------------------------------------
# Devolução de compra (item 7; HI-157)
# ---------------------------------------------------------------------------


def test_devolucao_de_compra_e_sugerida_pela_descricao_oficial_do_cfop(
    escritorio_a, usuario_gestor_a, empresa
):
    devolucao = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="70",
        tp_nf="1",
        fin_nfe="1",
        cfop="5202",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    sugestao = servico.sugerir_natureza_item(devolucao, devolucao.itens.get(n_item=1))
    assert sugestao.natureza == N.DEVOLUCAO_COMPRA

    consignacao = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="71",
        tp_nf="1",
        fin_nfe="1",
        cfop="5918",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    assert (
        servico.sugerir_natureza_item(consignacao, consignacao.itens.get(n_item=1)).natureza is None
    )


def test_devolucao_de_compra_so_com_cfop_de_indevol_1(escritorio_a, usuario_gestor_a, empresa):
    venda = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="72",
        tp_nf="1",
        fin_nfe="1",
        cfop="5102",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    esc = servico.criar_rascunho(vinculo(venda, empresa), usuario=usuario_gestor_a)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.definir_natureza(esc, N.DEVOLUCAO_COMPRA, ids, usuario=usuario_gestor_a)


def test_devolucao_de_compra_fica_fora_da_receita_e_do_saldo_do_art_17(
    escritorio_a, usuario_gestor_a, empresa
):
    devolucao = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="73",
        tp_nf="1",
        fin_nfe="1",
        cfop="5202",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    esc = servico.criar_rascunho(vinculo(devolucao, empresa), usuario=usuario_gestor_a)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, N.DEVOLUCAO_COMPRA, ids, usuario=usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    assert receita_servico._primeiro_mes_com_devolucao(empresa) is None
    assert receita_servico.linhas_nfe_do_periodo(empresa, (2026, 1), (2026, 12)) == []


def test_aviso_de_estorno_do_credito_aparece_na_devolucao_de_compra(
    escritorio_a, usuario_gestor_a, empresa
):
    devolucao = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="74",
        tp_nf="1",
        fin_nfe="1",
        cfop="5202",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    item = devolucao.itens.get(n_item=1)
    # A tela e a API de saída leem os avisos por `avisos_da_nota`: o estorno aparece lá (item 7).
    assert (
        entradas.AVISO_DEVOLUCAO_DE_COMPRA
        in servico.avisos_da_nota([(item, N.DEVOLUCAO_COMPRA)])[item.pk]
    )


def test_finnfe_4_com_cfop_de_devolucao_nao_gera_aviso_de_entrada_em_saida_propria():
    """Guarda: a natureza de devolução de compra não é de entrada e não aparece como compra."""
    assert N.DEVOLUCAO_COMPRA not in NATUREZAS_DE_ENTRADA


# ---------------------------------------------------------------------------
# Leitor de itens no posto (item 8): só verificação, o leitor NÃO foi alterado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("grupo", ["ICMS02", "ICMS15", "ICMS53", "ICMS61"])
def test_posto_compra_com_icms_monofasico_e_lida_sem_valor_e_marca_monofasico_pelo_ncm(
    escritorio_a, usuario_gestor_a, empresa, grupo
):
    """Estado REAL do leitor (critério do item 8). Medido em 13/10/2026 com o leitor da `main`:
    os grupos ICMS02, 15, 53 e 61 NÃO ficam ilegíveis. São lidos com CST e sem `vICMS`, porque o
    leitor não conhece os campos monofásicos (`qBCMono`, `vICMSMono`). Por isso a memória marca
    "monofásico" pelo NCM da lista (não pelo valor), e o valor monofásico NÃO é registrado. Ler esse
    valor é a nova versão do leitor, fora do corte 1 (P7). O leitor NÃO foi alterado aqui.
    """
    from apps.fiscal.itens_nfe import ler_itens
    from apps.fiscal.models import LeituraItensNFe

    cst = grupo.removeprefix("ICMS")
    icms = f"<ICMS><{grupo}><orig>0</orig><CST>{cst}</CST></{grupo}></ICMS>"
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        ncm="27101921",
        cfop="5655",
        icms=icms,
        numero=f"8{cst}",
    )
    ler_itens(documento)
    leitura = LeituraItensNFe.objects.get(documento=documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_LIDA
    item = documento.itens.get(n_item=1)
    assert item.cst == cst
    assert item.v_icms is None  # o valor monofásico não é lido pelo leitor de hoje
    marca, credito = entradas.marca_do_credito(documento, item, N.ENTRADA_COMBUSTIVEL_REVENDA)
    assert (marca, credito) == (MarcaCreditoEntrada.MONOFASICO, None)


@pytest.mark.parametrize(
    ("ncm", "marca", "descricao"),
    [
        # Art. 2º da LC 192, pela enumeração da consulta de 13/10/2026, seção 5: diesel e GLP.
        ("27101921", MarcaCreditoEntrada.MONOFASICO, "óleo diesel (art. 2º)"),
        ("27111910", MarcaCreditoEntrada.MONOFASICO, "GLP (art. 2º)"),
        # Combustível da lista fora do art. 2º: a regra não se afirma (a conferir).
        ("27101911", MarcaCreditoEntrada.A_CONFERIR, "querosene de aviação (fora do art. 2º)"),
        ("27101251", MarcaCreditoEntrada.A_CONFERIR, "óleo leve de aviação (fora do art. 2º)"),
        ("27101922", MarcaCreditoEntrada.A_CONFERIR, "fuel-oil (fora do art. 2º)"),
        ("27111100", MarcaCreditoEntrada.A_CONFERIR, "gás natural liquefeito (fora do art. 2º)"),
        # Na lista, mas a descrição não separa com segurança: conferir o NCM.
        ("27101259", MarcaCreditoEntrada.MONOFASICO_CONFERIR_NCM, "óleo leve, outras"),
    ],
)
def test_monofasico_so_para_o_art_2_da_lc_192_o_resto_da_lista_e_conferido(
    escritorio_a, usuario_gestor_a, empresa, ncm, marca, descricao
):
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        ncm=ncm,
        cfop="5655",
        numero=f"7{ncm[-3:]}",
    )
    item = documento.itens.get(n_item=1)
    assert marca_e_credito(documento, item, N.ENTRADA_COMBUSTIVEL_REVENDA)[0] == marca, descricao


def marca_e_credito(documento, item, natureza):
    return entradas.marca_do_credito(documento, item, natureza)


def test_querosene_fora_do_art_2_gera_aviso_e_nao_e_monofasico(
    escritorio_a, usuario_gestor_a, empresa
):
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, ncm="27101911", cfop="5655", numero="790"
    )
    contexto = entradas.contexto_da_entrada(empresa, date(2026, 3, 15))
    avisos = entradas.avisos_da_entrada(
        documento, documento.itens.get(n_item=1), N.ENTRADA_COMBUSTIVEL_REVENDA, contexto
    )
    assert entradas.AVISO_COMBUSTIVEL_FORA_DO_ART_2 in avisos
