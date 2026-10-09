"""DL-081 (frente A), escrituração: rascunho, natureza, conferência com vNF, efetivação, estorno,
imutabilidade por SQL direto, unicidade e corrida (critérios 3 e 4 do plano).

Os exemplos são os da consulta de 09/10/2026, item 3 (Simples: vNF 2.970,00 -> receita 2.880,00,
segregada em 1.480,00 normal, 800,00 ST e 600,00 monofásico) e item 4 (Presumido: vNF 10.700,00 ->
receita 9.900,00). Os valores esperados estão escritos aqui à mão, não copiados do código.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    LeituraItensNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    TipoEscrituracaoNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-escrit-dl081")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Escrit Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def destinatario(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Destinataria Escrit Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def simples_exemplo() -> bytes:
    """Consulta, item 3: revenda 1.000 - 50 + 30 = 980; ST substituído 800; monofásico 600;
    substituto 500.
    vST 90 vai só no total. vNF = 2.900 - 50 + 30 + 90 = 2.970."""
    dets = [
        xml.det(
            1,
            cfop="5102",
            vprod="1000.00",
            vdesc="50.00",
            vfrete="30.00",
            icms_xml=xml.icms(csosn="102"),
        ),
        xml.det(2, cfop="5405", vprod="800.00", icms_xml=xml.icms(csosn="500")),
        xml.det(
            3,
            cfop="5102",
            vprod="600.00",
            icms_xml=xml.icms(csosn="102"),
            pis_xml="<PIS><PISNT><CST>04</CST></PISNT></PIS>",
        ),
        xml.det(
            4,
            cfop="5401",
            vprod="500.00",
            icms_xml=xml.icms(
                csosn="201",
                filhos="<modBCST>4</modBCST><vBCST>500.00</vBCST>"
                "<pICMSST>18.00</pICMSST><vICMSST>90.00</vICMSST>",
            ),
        ),
    ]
    return xml.nfe(
        dets=dets,
        vnf="2970.00",
        totais={"vProd": "2900.00", "vDesc": "50.00", "vFrete": "30.00", "vST": "90.00"},
        tp_nf="1",
        fin_nfe="1",
        id_dest="1",
        crt="1",
    )


def presumido_exemplo() -> bytes:
    """Consulta, item 4: vProd 10.000, vDesc 200, vFrete 100, vIPI 500, vST 300 -> vNF 10.700."""
    dets = [
        xml.det(
            1,
            cfop="5101",
            vprod="10000.00",
            vdesc="200.00",
            vfrete="100.00",
            icms_xml=xml.icms(
                cst="00",
                filhos="<modBC>3</modBC><vBC>9900.00</vBC>"
                "<pICMS>18.00</pICMS><vICMS>1782.00</vICMS>",
            ),
            ipi_xml=("<IPI><IPITrib><CST>50</CST><vIPI>500.00</vIPI></IPITrib></IPI>"),
        ),
    ]
    return xml.nfe(
        dets=dets,
        vnf="10700.00",
        totais={
            "vProd": "10000.00",
            "vDesc": "200.00",
            "vFrete": "100.00",
            "vST": "300.00",
            "vIPI": "500.00",
        },
        tp_nf="1",
        fin_nfe="1",
        id_dest="1",
        crt="3",
    )


def naturezas(escrituracao, mapa):
    """Confirma a natureza de cada item pela ordem n_item, como o contador faria."""
    for registro in NaturezaItemNFe.objects.select_related("item").filter(
        escrituracao=escrituracao
    ):
        registro.natureza = mapa[registro.item.n_item]
        NaturezaItemNFe.objects.filter(pk=registro.pk).update(natureza=registro.natureza)


def rascunho_da_nota(escritorio, gestor, emitente, xml_bytes):
    documento = receber(escritorio, gestor, xml_bytes)
    esc = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    return documento, esc


# --- rascunho e natureza -----------------------------------------------------------------------


def test_rascunho_nasce_com_uma_linha_de_natureza_por_item_vazia(escritorio_a, gestor, emitente):
    documento, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    assert esc.estado == EstadoEscrituracao.RASCUNHO
    assert esc.tipo == TipoEscrituracaoNFe.SAIDA_PROPRIA
    linhas = list(NaturezaItemNFe.objects.filter(escrituracao=esc).order_by("item__n_item"))
    assert [linha.natureza for linha in linhas] == ["", "", "", ""]
    assert len(linhas) == ItemNFe.objects.filter(documento=documento).count() == 4


def test_criar_rascunho_de_novo_devolve_o_mesmo(escritorio_a, gestor, emitente):
    documento = receber(escritorio_a, gestor, simples_exemplo())
    primeiro = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    segundo = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    assert primeiro.pk == segundo.pk
    assert segundo.criada_agora is False
    assert EscrituracaoNFe.objects.filter(vinculo__documento=documento).count() == 1


def test_natureza_de_devolucao_nao_cabe_em_saida_propria(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.definir_natureza(esc, N.DEVOLUCAO_VENDA, ids, usuario=gestor)


def test_natureza_fora_do_catalogo_e_recusada_sem_eco(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        servico.definir_natureza(esc, "contrabando_xyz", [1], usuario=gestor)
    assert "contrabando_xyz" not in erro.value.mensagem


def test_definir_natureza_em_bloco_grava_e_registra_trilha(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, N.REVENDA, ids[:1], usuario=gestor)
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=ids[0]).natureza == N.REVENDA
    assert RegistroAuditoria.objects.filter(acao="escrituracao_nfe.natureza_definida").exists()


def test_item_de_outra_nota_nao_e_gravado(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    _, outra = rascunho_da_nota(
        escritorio_a,
        gestor,
        emitente,
        xml.nfe(dets=[xml.det(1, cfop="5102", vprod="10.00")], vnf="10.00", numero="2"),
    )
    estranho = NaturezaItemNFe.objects.filter(escrituracao=outra).first().item_id
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.definir_natureza(esc, N.REVENDA, [estranho], usuario=gestor)
    assert not NaturezaItemNFe.objects.filter(escrituracao=esc, natureza=N.REVENDA).exists()


# --- conferência com vNF e efetivação ----------------------------------------------------------


def test_exemplo_do_simples_efetiva_com_receita_2880_e_segregacao(escritorio_a, gestor, emitente):
    """Consulta, item 3: receita 2.880,00 = 2.970,00 − 90,00 (vST). Segregação: 1.480 normal,
    800 ST, 600 monofásico. O vST de 90,00 fica fora."""
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    naturezas(esc, {1: N.REVENDA, 2: N.REVENDA_ST_SUBSTITUIDO, 3: N.MONOFASICO, 4: N.SUBSTITUTO_ST})
    efetivada = servico.efetivar(esc, usuario=gestor)
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert efetivada.receita_bruta == Decimal("2880.00")
    assert efetivada.soma_itens == Decimal("2880.00")
    assert efetivada.devolucao == Decimal("0.00")
    assert efetivada.valor_nf == Decimal("2970.00")
    assert servico.segregacao_da_escrituracao(efetivada) == {
        "normal": Decimal("1480.00"),
        "sujeita_st": Decimal("800.00"),
        "monofasico": Decimal("600.00"),
        "exportacao": Decimal("0.00"),
    }


def test_exemplo_do_presumido_efetiva_com_receita_9900(escritorio_a, gestor, emitente):
    """Consulta, item 4: vProd − vDesc + vFrete = 9.900; vIPI e vST ficam fora (vNF 10.700)."""
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, presumido_exemplo())
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    efetivada = servico.efetivar(esc, usuario=gestor)
    assert efetivada.receita_bruta == Decimal("9900.00")


def test_divergencia_com_vnf_bloqueia_e_nomeia_os_valores(escritorio_a, gestor, emitente):
    """vNF 10.701 em vez de 10.700: a conferência não bate, e a efetivação é recusada com os
    valores."""
    divergente = presumido_exemplo().replace(b"<vNF>10700.00</vNF>", b"<vNF>10701.00</vNF>")
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, divergente)
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=gestor)
    mensagem = erro.value.mensagem
    assert "diverge" in mensagem
    assert "10701" in mensagem and "9900" in mensagem
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.RASCUNHO


def test_nota_sem_vnf_nao_e_conferida_e_e_recusada(escritorio_a, gestor, emitente):
    """vNF é obrigatório no XSD. Sem ele, a nota não tem como ser conferida: recusa, não zero."""
    semvnf = presumido_exemplo().replace(b"<vNF>10700.00</vNF>", b"")
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, semvnf)
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=gestor)
    assert "vNF" in erro.value.mensagem


def test_efetivar_sem_natureza_em_todos_os_itens_e_recusado(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    naturezas(esc, {1: N.REVENDA, 2: N.REVENDA_ST_SUBSTITUIDO, 3: N.MONOFASICO, 4: N.SUBSTITUTO_ST})
    NaturezaItemNFe.objects.filter(escrituracao=esc, item__n_item=4).update(natureza="")
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=gestor)
    assert "Falta a natureza de 1" in erro.value.mensagem


def test_efetivar_e_idempotente_sem_trilha_nova(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, presumido_exemplo())
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    primeira = servico.efetivar(esc, usuario=gestor)
    trilhas = RegistroAuditoria.objects.filter(acao="escrituracao_nfe.efetivada").count()
    segunda = servico.efetivar(esc, usuario=gestor)
    assert primeira.pk == segunda.pk
    assert segunda.criada_agora is False
    assert RegistroAuditoria.objects.filter(acao="escrituracao_nfe.efetivada").count() == trilhas


def test_leitura_ilegivel_bloqueia_o_rascunho(escritorio_a, gestor, emitente):
    ilegivel = xml.nfe(dets=[xml.det(1, cfop="5102", vprod="10.00", ncm="2203")], vnf="10.00")
    documento = receber(escritorio_a, gestor, ilegivel)
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    assert "ilegíveis" in erro.value.mensagem and "NCM" in erro.value.mensagem
    assert not EscrituracaoNFe.objects.filter(vinculo__documento=documento).exists()
    assert (
        LeituraItensNFe.objects.get(documento=documento).estado == LeituraItensNFe.ESTADO_ILEGIVEL
    )


# --- estorno, imutabilidade e unicidade --------------------------------------------------------


def test_estorno_exige_motivo_e_grava_trilha(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, presumido_exemplo())
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    servico.efetivar(esc, usuario=gestor)
    with pytest.raises(servico.EntradaInvalidaNFe):
        servico.estornar(esc, "   ", usuario=gestor)
    estornada = servico.estornar(esc, "Nota emitida com CFOP errado", usuario=gestor)
    assert estornada.estado == EstadoEscrituracao.ESTORNADA
    assert estornada.motivo_estorno == "Nota emitida com CFOP errado"
    assert RegistroAuditoria.objects.filter(acao="escrituracao_nfe.estornada").exists()


def test_estornada_nao_volta_a_ser_efetivada_nem_muda_natureza(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, presumido_exemplo())
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    servico.efetivar(esc, usuario=gestor)
    servico.estornar(esc, "Erro de digitação", usuario=gestor)
    with pytest.raises(servico.EscrituracaoNFeErro):
        servico.efetivar(esc, usuario=gestor)
    item = NaturezaItemNFe.objects.filter(escrituracao=esc).first().item_id
    with pytest.raises(servico.EscrituracaoNFeErro):
        servico.definir_natureza(esc, N.REVENDA, [item], usuario=gestor)


def test_imutabilidade_efetivada_por_sql_direto(escritorio_a, gestor, emitente):
    """O banco recusa alteração de valor, de natureza e de exclusão, mesmo sem o Python."""
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, presumido_exemplo())
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    servico.efetivar(esc, usuario=gestor)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EscrituracaoNFe.objects.filter(pk=esc.pk).update(receita_bruta=Decimal("1.00"))
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=N.REVENDA)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("DELETE FROM fiscal_escrituracaonfe WHERE id = %s", [esc.pk])
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            NaturezaItemNFe.objects.filter(escrituracao=esc).delete()


def test_rascunho_nao_efetiva_por_sql_sem_natureza(escritorio_a, gestor, emitente):
    """O gatilho recusa rascunho -> efetivada com item sem natureza, mesmo por UPDATE direto."""
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EscrituracaoNFe.objects.filter(pk=esc.pk).update(
                estado=EstadoEscrituracao.EFETIVADA,
                competencia=esc.competencia,
                data_emissao=esc.data_emissao,
            )


def test_natureza_com_valor_fora_do_catalogo_e_recusada_pelo_banco(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza="valor_inventado")


def test_no_maximo_uma_escrituracao_ativa_por_vinculo_no_banco(escritorio_a, gestor, emitente):
    documento = receber(escritorio_a, gestor, simples_exemplo())
    v = vinculo(documento, emitente)
    servico.criar_rascunho(v, usuario=gestor)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            EscrituracaoNFe.objects.create(
                vinculo=v,
                empresa=emitente,
                tipo=TipoEscrituracaoNFe.SAIDA_PROPRIA,
                estado=EstadoEscrituracao.RASCUNHO,
                criado_por=gestor,
            )


def test_nota_cancelada_nao_e_escriturada(escritorio_a, gestor, emitente):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apps.fiscal.models import EventoNFe

    documento = receber(escritorio_a, gestor, presumido_exemplo())
    EventoNFe.objects.create(
        escritorio=escritorio_a,
        identificador=f"ID110111{documento.chave}01",
        tp_evento="110111",
        n_seq_evento=1,
        chave=documento.chave,
        dh_evento=datetime(2026, 3, 16, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        autor_tipo_documento="CNPJ",
        autor_documento=CNPJ_EMITENTE_A,
        c_stat="135",
        xml_original=b"<evento-sintetico/>",
        sha256_arquivo="0" * 64,
    )
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    assert "cancelada" in erro.value.mensagem


# --- pendência, competência no fuso de São Paulo e conferência do mês ------------------------


def _cancelar_nota(escritorio, documento):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apps.fiscal.models import EventoNFe

    EventoNFe.objects.create(
        escritorio=escritorio,
        identificador=f"ID110111{documento.chave}01",
        tp_evento="110111",
        n_seq_evento=1,
        chave=documento.chave,
        dh_evento=datetime(2026, 3, 20, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        autor_tipo_documento="CNPJ",
        autor_documento=CNPJ_EMITENTE_A,
        c_stat="135",
        xml_original=b"<evento-sintetico/>",
        sha256_arquivo="2" * 64,
    )


def test_escriturada_e_cancelada_depois_vira_pendencia_e_sai_da_conta(
    escritorio_a, gestor, emitente
):
    """Critério 4: escriturada e cancelada depois é pendência e sai da receita."""
    documento, esc = rascunho_da_nota(escritorio_a, gestor, emitente, presumido_exemplo())
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    servico.efetivar(esc, usuario=gestor)
    _cancelar_nota(escritorio_a, documento)
    notas = [n for n in servico.notas_do_mes(emitente, 2026, 3) if n.documento.pk == documento.pk]
    assert notas[0].situacao == servico.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA
    conferencia = servico.conferencia_do_mes(emitente, 2026, 3)
    assert conferencia.escrituradas == 0
    assert conferencia.escrituradas_canceladas == 1
    assert conferencia.canceladas == 1
    assert conferencia.pendentes == 0


def test_competencia_e_o_mes_de_dhEmi_no_fuso_de_sao_paulo(escritorio_a, gestor, emitente):
    """31/03/2026 às 23:30 em Brasília é 01/04/2026 em UTC. A competência segue Brasília: março."""
    nota = xml.nfe(
        dets=[xml.det(1, cfop="5101", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="100.00",
        totais={"vProd": "100.00"},
        numero="90",
        dh_emi="2026-03-31T23:30:00-03:00",
    )
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, nota)
    naturezas(esc, {1: N.PRODUCAO_PROPRIA})
    efetivada = servico.efetivar(esc, usuario=gestor)
    assert efetivada.competencia == date(2026, 3, 1)
    assert efetivada.data_emissao == date(2026, 3, 31)


def test_conferencia_do_mes_mostra_receita_por_natureza_e_cfop(escritorio_a, gestor, emitente):
    _, esc = rascunho_da_nota(escritorio_a, gestor, emitente, simples_exemplo())
    naturezas(esc, {1: N.REVENDA, 2: N.REVENDA_ST_SUBSTITUIDO, 3: N.MONOFASICO, 4: N.SUBSTITUTO_ST})
    servico.efetivar(esc, usuario=gestor)
    conferencia = servico.conferencia_do_mes(emitente, 2026, 3)
    assert conferencia.receita_por_natureza["revenda"]["soma_na_receita"] == Decimal("980.00")
    assert conferencia.receita_por_natureza["monofasico"]["soma_na_receita"] == Decimal("600.00")
    soma = sum(linha["soma_na_receita"] for linha in conferencia.receita_por_natureza.values())
    assert soma == Decimal("2880.00")
    # CFOP 5102 soma os itens 1 (980,00) e 3 (600,00); CFOP 5405 é o item 2 (800,00).
    assert conferencia.receita_por_cfop["5102"] == Decimal("1580.00")
    assert conferencia.receita_por_cfop["5405"] == Decimal("800.00")
    assert conferencia.itens_sem_sugestao == 0


def test_itens_sem_sugestao_contam_na_conferencia(escritorio_a, gestor, emitente):
    """CFOP 5000 não está na tabela oficial: o item fica sem sugestão e a conferência conta."""
    nota = xml.nfe(
        dets=[xml.det(1, cfop="5000", vprod="10.00", icms_xml=xml.icms(csosn="102"))],
        vnf="10.00",
        totais={"vProd": "10.00"},
        numero="91",
    )
    rascunho_da_nota(escritorio_a, gestor, emitente, nota)
    assert servico.conferencia_do_mes(emitente, 2026, 3).itens_sem_sugestao == 1
