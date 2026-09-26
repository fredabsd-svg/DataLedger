"""DL-038 (R6) — não é possível passar uma empresa para modo livro-caixa se
ela já tem plano de contas OU lançamento contábil gravado; sem movimento, a
transição é permitida.

Cobre `apps.empresas.services.recusar_transicao_para_livro_caixa_com_
movimento` diretamente (a FONTE ÚNICA da regra) e `Empresa.clean()` (o
consumidor de ModelForm/admin, DE-008) — o caminho da API já está coberto,
de ponta a ponta, em `test_dl038_api.py`.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.contabilidade.models import TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.services import (
    TransicaoParaLivroCaixaInvalida,
    recusar_transicao_para_livro_caixa_com_movimento,
)
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório R6 DL-038", cnpj="90909090000190")


@pytest.fixture
def empresa(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa R6 Ltda", cnpj="11122233000183"
    )


# --- A função de serviço, isolada ------------------------------------------


def test_transicao_sem_movimento_nao_levanta_nada(empresa):
    recusar_transicao_para_livro_caixa_com_movimento(
        empresa,
        modo_anterior=ModoEscrituracao.CONTABILIDADE,
        modo_novo=ModoEscrituracao.LIVRO_CAIXA,
    )


def test_transicao_com_plano_de_contas_e_recusada(empresa):
    empresa.contas.create(codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza="devedora")

    with pytest.raises(TransicaoParaLivroCaixaInvalida):
        recusar_transicao_para_livro_caixa_com_movimento(
            empresa,
            modo_anterior=ModoEscrituracao.CONTABILIDADE,
            modo_novo=ModoEscrituracao.LIVRO_CAIXA,
        )


def test_transicao_com_lancamento_e_recusada(empresa):
    caixa = empresa.contas.create(
        codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza="devedora"
    )
    capital = empresa.contas.create(
        codigo="3", nome="Capital", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza="credora"
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 1, 15),
        historico="Movimento de teste R6",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )

    with pytest.raises(TransicaoParaLivroCaixaInvalida, match="lançamento contábil"):
        recusar_transicao_para_livro_caixa_com_movimento(
            empresa,
            modo_anterior=ModoEscrituracao.CONTABILIDADE,
            modo_novo=ModoEscrituracao.LIVRO_CAIXA,
        )


def test_transicao_que_nao_e_para_livro_caixa_nunca_e_examinada(empresa):
    # A regra é sobre a transição PARA livro-caixa — voltar para
    # contabilidade nunca aciona esta checagem, mesmo com movimento.
    empresa.contas.create(codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza="devedora")

    recusar_transicao_para_livro_caixa_com_movimento(
        empresa,
        modo_anterior=ModoEscrituracao.LIVRO_CAIXA,
        modo_novo=ModoEscrituracao.CONTABILIDADE,
    )


def test_empresa_ja_em_livro_caixa_sem_mudanca_nunca_e_examinada(empresa):
    empresa.contas.create(codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza="devedora")

    recusar_transicao_para_livro_caixa_com_movimento(
        empresa,
        modo_anterior=ModoEscrituracao.LIVRO_CAIXA,
        modo_novo=ModoEscrituracao.LIVRO_CAIXA,
    )


# --- Empresa.clean() (ModelForm/admin, DE-008) ------------------------------


def test_clean_recusa_transicao_para_livro_caixa_com_movimento(empresa):
    empresa.contas.create(codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza="devedora")
    empresa.modo_escrituracao = ModoEscrituracao.LIVRO_CAIXA

    with pytest.raises(ValidationError, match="plano de contas"):
        empresa.clean()


def test_clean_permite_transicao_para_livro_caixa_sem_movimento(empresa):
    empresa.modo_escrituracao = ModoEscrituracao.LIVRO_CAIXA
    empresa.clean()  # não levanta


def test_clean_de_empresa_nova_nunca_examina_transicao(escritorio):
    # `self.pk` ainda `None` — não há "modo gravado" para comparar. Mesmo
    # padrão do guard de troca de escritório, logo acima no mesmo método.
    empresa_nova = Empresa(
        escritorio=escritorio,
        razao_social="Empresa Nova R6 Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_nova.clean()  # não levanta: não há transição, é criação
