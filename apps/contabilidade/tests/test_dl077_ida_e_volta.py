"""DL-077, fatia 1 (critério 2): ida e volta do plano nos dois formatos TXT.

Exporta o plano de uma empresa, reimporta em outra (vazia) e na própria (só
acrescentar). Dados sintéticos. Duas limitações do leiaute da ECD são provadas
aqui, não escondidas: a ECD não leva natureza (HI-88) e não separa receita de
despesa (HI-87). Sem prefixo, o produto recusa; com prefixo, recria o plano.
"""

import hashlib
from datetime import date

import pytest

from apps.contabilidade.intercambio.canonico import NIVEL_AVISO, NIVEL_ERRO
from apps.contabilidade.intercambio.leitura import ler_arquivo
from apps.contabilidade.intercambio.plano import (
    aplicar_plano,
    conferir_plano,
    exportar_plano,
)
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

DATA_ALTERACAO = date(2026, 1, 31)


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL077 Ida e volta", cnpj="33333333000133")


def _empresa(escritorio, nome, cnpj):
    return Empresa.objects.create(escritorio=escritorio, razao_social=nome, cnpj=cnpj)


def _cadastrar_plano(empresa, incluir_redutora=True):
    """Plano de exemplo com todos os tipos. Tudo sintético e fictício."""

    def conta(codigo, nome, tipo, natureza, pai=None, analitica=True):
        return Conta.objects.create(
            empresa=empresa,
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            natureza=natureza,
            conta_pai=pai,
            aceita_lancamento=analitica,
        )

    ativo = conta("1", "Ativo", TipoConta.ATIVO, NaturezaConta.DEVEDORA, analitica=False)
    circulante = conta(
        "1.1", "Circulante", TipoConta.ATIVO, NaturezaConta.DEVEDORA, ativo, analitica=False
    )
    conta("1.1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA, circulante)
    if incluir_redutora:
        conta(
            "1.2",
            "Depreciação acumulada",
            TipoConta.ATIVO,
            NaturezaConta.CREDORA,
            ativo,
        )
    passivo = conta("2", "Passivo", TipoConta.PASSIVO, NaturezaConta.CREDORA, analitica=False)
    conta("2.1", "Fornecedores", TipoConta.PASSIVO, NaturezaConta.CREDORA, passivo)
    receitas = conta("3", "Receitas", TipoConta.RECEITA, NaturezaConta.CREDORA, analitica=False)
    conta("3.1", "Vendas", TipoConta.RECEITA, NaturezaConta.CREDORA, receitas)
    despesas = conta("4", "Despesas", TipoConta.DESPESA, NaturezaConta.DEVEDORA, analitica=False)
    conta("4.1", "Aluguel", TipoConta.DESPESA, NaturezaConta.DEVEDORA, despesas)
    pl = conta(
        "5",
        "Patrimônio líquido",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.CREDORA,
        analitica=False,
    )
    conta("5.1", "Capital social", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA, pl)


def _fotografia(empresa):
    """Estado do plano que a ida e volta precisa preservar."""
    return {
        c.codigo: (
            c.nome,
            c.conta_pai.codigo if c.conta_pai_id else None,
            c.aceita_lancamento,
            c.tipo,
            c.natureza,
        )
        for c in Conta.objects.filter(empresa=empresa).select_related("conta_pai")
    }


def _importar(empresa, arquivo, prefixos=None):
    resultado = ler_arquivo(arquivo.formato, arquivo.conteudo, nome_arquivo="ida-e-volta.txt")
    previa = conferir_plano(empresa, resultado, "so_acrescentar", prefixos or {})
    return previa


def _aplicar(empresa, previa):
    return aplicar_plano(
        empresa,
        previa,
        None,
        None,
        sha256_esperado=previa.sha256,
        assinatura_esperada=previa.assinatura,
    )


def test_proprio_em_empresa_vazia_recria_o_mesmo_plano_inclusive_redutora(escritorio):
    origem = _empresa(escritorio, "Origem Ltda", "11122233000183")
    _cadastrar_plano(origem)
    destino = _empresa(escritorio, "Destino Ltda", "44455566000183")

    arquivo = exportar_plano(empresa=origem, formato="proprio")
    previa = _importar(destino, arquivo)

    assert not previa.tem_erro, previa.ocorrencias
    _aplicar(destino, previa)
    assert _fotografia(destino) == _fotografia(origem)


def test_ecd_em_empresa_vazia_recria_o_plano_com_os_prefixos_de_receita_e_despesa(escritorio):
    """Sem natureza na ECD, as contas são recriadas com natureza PRESUMIDA. O plano
    de exemplo não tem redutora, então a presunção coincide com o original."""
    origem = _empresa(escritorio, "Origem ECD Ltda", "11122233000183")
    _cadastrar_plano(origem, incluir_redutora=False)
    destino = _empresa(escritorio, "Destino ECD Ltda", "44455566000183")

    arquivo = exportar_plano(empresa=origem, formato="ecd", data_alteracao=DATA_ALTERACAO)
    previa = _importar(destino, arquivo, prefixos={"3": "receita", "4": "despesa"})

    assert not previa.tem_erro, previa.ocorrencias
    _aplicar(destino, previa)
    assert _fotografia(destino) == _fotografia(origem)


def test_ecd_sem_prefixo_recusa_receita_e_despesa_HI87(escritorio):
    """A ECD (COD_NAT 04) não diz receita nem despesa. Sem prefixo, o produto recusa
    essas contas e não grava nada: é o HI-87 funcionando na ida e volta."""
    origem = _empresa(escritorio, "Origem sem prefixo Ltda", "11122233000183")
    _cadastrar_plano(origem, incluir_redutora=False)
    destino = _empresa(escritorio, "Destino sem prefixo Ltda", "44455566000183")

    arquivo = exportar_plano(empresa=origem, formato="ecd", data_alteracao=DATA_ALTERACAO)
    previa = _importar(destino, arquivo)

    assert previa.tem_erro
    campos_com_erro = {(o.campo, o.nivel) for o in previa.ocorrencias}
    assert ("tipo", NIVEL_ERRO) in campos_com_erro
    assert Conta.objects.filter(empresa=destino).count() == 0


def test_ecd_perde_a_natureza_redutora_e_o_produto_avisa_HI88(escritorio):
    """Limitação declarada: a ECD não leva natureza. A redutora volta como presumida
    (devedora, no ativo), e o produto AVISA a conta. Não é silêncio."""
    origem = _empresa(escritorio, "Origem redutora Ltda", "11122233000183")
    _cadastrar_plano(origem, incluir_redutora=True)
    destino = _empresa(escritorio, "Destino redutora Ltda", "44455566000183")

    arquivo = exportar_plano(empresa=origem, formato="ecd", data_alteracao=DATA_ALTERACAO)
    previa = _importar(destino, arquivo, prefixos={"3": "receita", "4": "despesa"})

    assert not previa.tem_erro, previa.ocorrencias
    redutora = next(i for i in previa.itens if i.codigo == "1.2")
    assert redutora.natureza == "devedora"
    assert any(
        o.nivel == NIVEL_AVISO and o.campo == "natureza" and o.linha == redutora.linha
        for o in previa.ocorrencias
    )


def test_mesma_empresa_so_acrescentar_nao_cria_nada_no_proprio_formato(escritorio):
    empresa = _empresa(escritorio, "Mesma Ltda", "11122233000183")
    _cadastrar_plano(empresa)
    antes = _fotografia(empresa)

    arquivo = exportar_plano(empresa=empresa, formato="proprio")
    previa = _importar(empresa, arquivo)

    assert not previa.tem_erro, previa.ocorrencias
    assert previa.contagens["criar"] == 0
    assert previa.contagens["recusada"] == 0
    resultado = _aplicar(empresa, previa)
    assert resultado.criadas == 0
    assert _fotografia(empresa) == antes


def test_mesma_empresa_so_acrescentar_nao_cria_nada_no_formato_ecd(escritorio):
    empresa = _empresa(escritorio, "Mesma ECD Ltda", "11122233000183")
    _cadastrar_plano(empresa)
    antes = _fotografia(empresa)

    arquivo = exportar_plano(empresa=empresa, formato="ecd", data_alteracao=DATA_ALTERACAO)
    previa = _importar(empresa, arquivo)

    assert not previa.tem_erro, previa.ocorrencias
    assert previa.contagens["criar"] == 0
    resultado = _aplicar(empresa, previa)
    assert resultado.criadas == 0
    assert _fotografia(empresa) == antes


def test_a_exportacao_devolve_o_sha256_do_conteudo_gerado(escritorio):
    """O SHA-256 devolvido é o do conteúdo entregue: é o que a trilha da view registra."""
    empresa = _empresa(escritorio, "SHA Ltda", "11122233000183")
    _cadastrar_plano(empresa)

    arquivo = exportar_plano(empresa=empresa, formato="proprio")

    assert arquivo.sha256 == hashlib.sha256(arquivo.conteudo).hexdigest()
    assert arquivo.quantidade_contas == Conta.objects.filter(empresa=empresa).count()
