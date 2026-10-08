"""DL-077, reconferência da fatia 1 (2026-10-08): teto de contas por importação (R4, N27).

- T-R4: aplicar exatamente 2.500 contas (o teto) leva menos de 25 s. O gunicorn padrão mata o
  worker síncrono em 30 s, e a aplicação segura o lock da empresa. O tempo medido é impresso
  (rodar com `-s` para ver) e vira asserção frouxa.
- N27: a fronteira exata. 2.500 passa a conferência e a aplicação; 2.501 é recusado com o nome
  do limite, antes de qualquer consulta ao cadastro.

Dados sintéticos. Nenhum arquivo de cliente real.
"""

import time

import pytest

from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais, ler_arquivo
from apps.contabilidade.intercambio.plano import (
    MAXIMO_DE_CONTAS_POR_IMPORTACAO,
    aplicar_plano,
    conferir_plano,
)
from apps.contabilidade.models import Conta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"
LIMITE_DO_TESTE_DE_APLICACAO_S = 25.0  # frouxo: o worker morre em 30 s

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório DL077 Teto", cnpj="33333333000133")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL077 Teto Ltda", cnpj="22233344000138"
    )


def _proprio(*linhas):
    conteudo = ("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("utf-8")
    return ler_arquivo("proprio", conteudo, nome_arquivo="plano-teto.txt")


def _plano_de(total):
    """Um arquivo com `total` contas: uma sintética `1` e `total - 1` analíticas sob ela."""
    linhas = ["1;Ativo;;N;ativo;devedora"]
    linhas += [f"1.{i};Conta {i};1;S;;" for i in range(1, total)]
    return _proprio(*linhas)


def _aplicar(empresa, previa):
    return aplicar_plano(
        empresa,
        previa,
        None,
        None,
        sha256_esperado=previa.sha256,
        assinatura_esperada=previa.assinatura,
    )


@pytest.mark.django_db
def test_aplicacao_de_2500_contas_e_aceita_e_cabe_no_tempo_de_um_worker(empresa):
    """T-R4 e N27 (fronteira de cima): exatamente o teto passa a conferência e a aplicação."""
    assert MAXIMO_DE_CONTAS_POR_IMPORTACAO == 2_500
    previa = conferir_plano(
        empresa, _plano_de(MAXIMO_DE_CONTAS_POR_IMPORTACAO), "so_acrescentar", {}
    )
    assert not previa.tem_erro, [o.mensagem for o in previa.ocorrencias][:3]

    inicio = time.perf_counter()
    _aplicar(empresa, previa)
    decorrido = time.perf_counter() - inicio

    print(f"\nT-R4: aplicação de {MAXIMO_DE_CONTAS_POR_IMPORTACAO} contas em {decorrido:.2f} s")
    assert decorrido < LIMITE_DO_TESTE_DE_APLICACAO_S, f"aplicação levou {decorrido:.2f} s"
    assert Conta.objects.filter(empresa=empresa).count() == MAXIMO_DE_CONTAS_POR_IMPORTACAO


def test_arquivo_com_uma_conta_acima_do_teto_e_recusado_com_o_nome_do_limite(empresa):
    """N27 (fronteira de cima): 2.501 contas são recusadas na conferência, antes do cadastro."""
    # Literal de propósito: um teste que calcula `MAXIMO + 1` acompanharia uma constante
    # trocada e deixaria de provar a fronteira.
    resultado = _plano_de(2501)

    with pytest.raises(ArquivoGrandeDemais, match="2500"):
        conferir_plano(empresa, resultado, "so_acrescentar", {})
