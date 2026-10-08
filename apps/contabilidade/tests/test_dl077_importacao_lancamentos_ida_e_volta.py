"""Ida e volta: exportar com a fatia 2 e reimportar com a fatia 3 (DL-077, fatia 3, frente A).

Uma empresa de origem exporta seus lançamentos em cada formato; a mesma empresa (o mesmo CNPJ,
em outro escritório: é a migração real) reimporta com o mesmo plano e efetiva. O conjunto de
lançamentos resultante tem de ser o da origem: data, histórico e, por conta, lado e valor.

O sistema de referência usa código REDUZIDO. O de-para é montado com o mapa de códigos reduzidos
do plano (`codigos_reduzidos`), como faria o contador ao importar o arquivo de outro escritório.
"""

from datetime import date

import pytest

from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.intercambio.formatos import referencia_lancamentos
from apps.contabilidade.intercambio.lancamentos import exportar_lancamentos
from apps.contabilidade.models import LancamentoContabil
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
    lancar,
)

pytestmark = pytest.mark.django_db
INICIO = date(2026, 1, 1)
FIM = date(2026, 3, 31)


def _fotografia(empresa):
    """Conjunto de lançamentos da empresa, sem ids: é o que a ida e a volta devem preservar."""
    return sorted(
        (
            lancamento.data.isoformat(),
            lancamento.historico,
            tuple(sorted((i.conta.codigo, i.tipo, str(i.valor)) for i in lancamento.itens.all())),
        )
        for lancamento in LancamentoContabil.objects.filter(empresa=empresa)
    )


@pytest.fixture
def origem():
    escritorio = criar_escritorio("Escritório de origem", "10101010000110")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Migrada Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    lancar(
        empresa,
        contas,
        date(2026, 1, 10),
        "Aporte de capital",
        [("1.1.1", "1000.00")],
        [("5.1", "1000.00")],
    )
    lancar(
        empresa,
        contas,
        date(2026, 2, 5),
        "Compra a prazo; fornecedor Alfa",
        [("1.1.1", "300.00")],
        [("2.1", "300.00")],
    )
    lancar(
        empresa,
        contas,
        date(2026, 3, 3),
        "Venda com recebimento parcial",
        [("1.1.1", "300.00")],
        [("3.1", "200.00"), ("2.1", "100.00")],
    )
    return {"empresa": empresa, "contas": contas, "escritorio": escritorio}


def _destino_com_o_mesmo_cnpj(origem):
    """Mesmo CNPJ, outro escritório: a empresa que mudou de escritório."""
    destino_escritorio = criar_escritorio("Escritório de destino", "20202020000220")
    destino = criar_empresa(
        escritorio=destino_escritorio, razao_social="Migrada Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(destino)
    return destino, contas


def _exportar(empresa, formato):
    return exportar_lancamentos(
        empresa=empresa,
        formato=formato,
        data_inicial=INICIO,
        data_final=FIM,
        incluir_saldos=False,
        omitir_nao_representaveis=False,
        usuario=None,
    )


def _reimportar_e_efetivar(destino, formato, conteudo, nome):
    importacao = servico.receber(
        empresa=destino, formato=formato, conteudo=conteudo, nome_arquivo=nome, usuario=None
    )
    assert importacao.quantidade_com_erro == 0, [
        o for linha in importacao.lancamentos.all() for o in linha.ocorrencias
    ]
    return servico.efetivar(importacao, politica=servico.TUDO_OU_NADA)


@pytest.mark.parametrize("formato", ["proprio", "ecd"])
def test_ida_e_volta_preserva_datas_contas_valores_e_historicos(origem, formato):
    destino, _contas = _destino_com_o_mesmo_cnpj(origem)
    arquivo = _exportar(origem["empresa"], formato)

    resultado = _reimportar_e_efetivar(destino, formato, arquivo.conteudo, f"ida.{formato}")

    assert resultado.criados == 3
    assert _fotografia(destino) == _fotografia(origem["empresa"])


def test_ida_e_volta_pelo_sistema_de_referencia_com_o_de_para_dos_reduzidos(origem):
    destino, contas_destino = _destino_com_o_mesmo_cnpj(origem)
    arquivo = _exportar(origem["empresa"], "referencia")
    mapa = referencia_lancamentos.codigos_reduzidos(
        conta.codigo for conta in origem["contas"].values()
    )
    for codigo, reduzido in mapa.items():
        # Expectativa ajustada (DL-077, alinhamento das fatias 2 e 3): o de-para só aponta para
        # conta analítica, e o serviço recusa a sintética. Lançamento nunca usa conta sintética,
        # então pular a sintética não tira nada da ida e volta.
        if not origem["contas"][codigo].aceita_lancamento:
            continue
        servico.definir_de_para(
            empresa=destino,
            formato="referencia",
            codigo_origem=str(reduzido),
            conta=contas_destino[codigo],
            usuario=None,
        )

    resultado = _reimportar_e_efetivar(destino, "referencia", arquivo.conteudo, "ida.txt")

    assert resultado.criados == 3
    assert _fotografia(destino) == _fotografia(origem["empresa"])


def test_o_arquivo_de_referencia_tem_linhas_com_barra_no_inicio_e_no_fim_e_valor_com_virgula(
    origem,
):
    arquivo = _exportar(origem["empresa"], "referencia").conteudo.decode("iso-8859-1")
    linhas = [linha for linha in arquivo.split("\r\n") if linha]

    assert all(linha.startswith("|") and linha.endswith("|") for linha in linhas)
    assert any(linha.startswith("|6100|10/01/2026|") and "|1000,00|" in linha for linha in linhas)


def test_reimportar_o_mesmo_arquivo_no_mesmo_destino_nao_duplica(origem):
    destino, _contas = _destino_com_o_mesmo_cnpj(origem)
    arquivo = _exportar(origem["empresa"], "proprio")
    _reimportar_e_efetivar(destino, "proprio", arquivo.conteudo, "ida.txt")

    with pytest.raises(servico.ImportacaoJaExiste):
        servico.receber(
            empresa=destino,
            formato="proprio",
            conteudo=arquivo.conteudo,
            nome_arquivo="ida.txt",
            usuario=None,
        )
    assert LancamentoContabil.objects.filter(empresa=destino).count() == 3
