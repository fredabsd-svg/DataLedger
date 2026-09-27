"""DL-046, fatia 1 — livro-caixa do cliente pessoa física (RC-113/RC-114/
RC-128), servidor + API. A tela vem depois pelo `especialista-frontend`.

Cobre: modelo (sucesso/erro/limite), recusa por modo de escrituração nos
dois sentidos, isolamento entre empresas/escritórios, papéis (escritura x
leitura), idempotência, estorno (imutabilidade, unicidade, ordem de data,
visibilidade no relatório), conciliação do relatório "Livro Caixa", CPF
inválido/incoerente, código do Carnê-Leão Web incoerente com a natureza, e
migração aplicada em banco vazio (conferida separadamente por
`manage.py migrate` em Postgres/SQLite — ver o relatório da etapa).
"""

import json
import threading
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.test import Client
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.empresas.services import (
    EmpresaNaoEmModoLivroCaixa,
    TransicaoParaContabilidadeInvalida,
    recusar_se_nao_livro_caixa,
    recusar_transicao_para_contabilidade_com_movimento_de_caixa,
)
from apps.livro_caixa.admin import ContaLivroCaixaAdmin
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    LancamentoCaixa,
    LancamentoCaixaImutavelError,
    NaturezaCaixa,
    OrigemRecebimento,
)
from apps.livro_caixa.services import (
    ChaveIdempotenciaConflitanteCaixa,
    LancamentoCaixaInvalido,
    apurar_livro_caixa,
    criar_conta_livro_caixa,
    criar_lancamento_caixa,
    estornar_lancamento_caixa,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CPF_TITULAR = "11144477735"
CPF_BENEFICIARIO = "22255588846"
CNPJ_PAGADOR = "11122233000183"


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario():
    escritorio_a = Escritorio.objects.create(nome="Escritório Caixa A", cnpj="33333333000144")
    escritorio_b = Escritorio.objects.create(nome="Escritório Caixa B", cnpj="55555555000166")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Fulano de Tal",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="12345678909",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b,
        razao_social="Ciclano de Tal",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_TITULAR,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Empresa Contabilidade Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    conta_receita = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="R1",
        nome="Honorários recebidos",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta_despesa = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="D1",
        nome="Despesas dedutíveis",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P10.001",
    )
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "empresa_contabilidade": empresa_contabilidade,
        "conta_receita": conta_receita,
        "conta_despesa": conta_despesa,
    }


# ---------------------------------------------------------------------------
# 1. Modelo — ContaLivroCaixa
# ---------------------------------------------------------------------------


def test_conta_livro_caixa_criada_com_sucesso(cenario):
    conta = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="R2",
        nome="Aluguel recebido",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    assert conta.ativa is True


def test_conta_recusa_empresa_em_modo_contabilidade(cenario):
    conta = ContaLivroCaixa(
        empresa=cenario["empresa_contabilidade"],
        codigo="R1",
        nome="Honorários",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    with pytest.raises(ValidationError):
        conta.full_clean()


def test_conta_recusa_codigo_de_pagamento_em_conta_de_receita(cenario):
    conta = ContaLivroCaixa(
        empresa=cenario["empresa_a"],
        codigo="R3",
        nome="Receita mal classificada",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="P10.001",
    )
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()
    assert "codigo_carne_leao" in excinfo.value.message_dict


def test_conta_recusa_codigo_de_rendimento_em_conta_de_despesa(cenario):
    conta = ContaLivroCaixa(
        empresa=cenario["empresa_a"],
        codigo="D3",
        nome="Despesa mal classificada",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="R01.001.001",
    )
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()
    assert "codigo_carne_leao" in excinfo.value.message_dict


def test_conta_codigo_unico_por_empresa(cenario):
    ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="DUP",
        nome="Primeira",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    with pytest.raises(IntegrityError):
        ContaLivroCaixa.objects.create(
            empresa=cenario["empresa_a"],
            codigo="DUP",
            nome="Segunda",
            natureza=NaturezaCaixa.RECEITA,
            codigo_carne_leao="R01.004.001",
        )


def test_mesmo_codigo_em_empresas_diferentes_nao_colide(cenario):
    ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="X1",
        nome="Conta empresa A",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta_b = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_b"],
        codigo="X1",
        nome="Conta empresa B",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    assert conta_b.pk is not None


def test_conta_recusa_mudar_natureza_com_lancamento_gravado(cenario):
    conta = cenario["conta_receita"]
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta,
        data=date(2026, 1, 10),
        valor="100.00",
        historico="Recebimento",
        recebido_de=OrigemRecebimento.PJ,
    )
    conta.natureza = NaturezaCaixa.DESPESA
    with pytest.raises(ValidationError):
        conta.full_clean()


def test_conta_pode_mudar_natureza_sem_lancamento_gravado(cenario):
    conta = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="LIVRE",
        nome="Sem movimento ainda",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta.natureza = NaturezaCaixa.DESPESA
    conta.codigo_carne_leao = "P10.002"
    conta.full_clean()
    conta.save()
    conta.refresh_from_db()
    assert conta.natureza == NaturezaCaixa.DESPESA


# ---------------------------------------------------------------------------
# 2. Modelo — LancamentoCaixa
# ---------------------------------------------------------------------------


def test_lancamento_criado_com_sucesso(cenario):
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="1500.00",
        historico="Honorários de janeiro",
        recebido_de=OrigemRecebimento.PJ,
    )
    assert lancamento.pk is not None
    assert lancamento.valor == Decimal("1500.00")
    assert lancamento.criado_agora is True


def test_lancamento_recusa_empresa_em_modo_contabilidade(cenario):
    conta_de_outra_empresa = ContaLivroCaixa(
        empresa=cenario["empresa_contabilidade"],
        codigo="X",
        nome="X",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_contabilidade"],
            conta=conta_de_outra_empresa,
            data=date(2026, 1, 15),
            valor="100.00",
            historico="Tentativa",
            recebido_de=OrigemRecebimento.PJ,
        )


def test_lancamento_recusa_conta_de_outra_empresa(cenario):
    conta_de_b = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_b"],
        codigo="B1",
        nome="Conta de B",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=conta_de_b,
            data=date(2026, 1, 15),
            valor="100.00",
            historico="Conta errada",
            recebido_de=OrigemRecebimento.PJ,
        )


def test_lancamento_recusa_valor_zero_ou_negativo(cenario):
    for valor in ("0.00", "-10.00"):
        with pytest.raises(LancamentoCaixaInvalido):
            criar_lancamento_caixa(
                empresa=cenario["empresa_a"],
                conta=cenario["conta_receita"],
                data=date(2026, 1, 15),
                valor=valor,
                historico="Valor inválido",
                recebido_de=OrigemRecebimento.PJ,
            )


def test_lancamento_recusa_escala_maior_que_duas_casas(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.001",
            historico="Escala inválida",
            recebido_de=OrigemRecebimento.PJ,
        )


def test_lancamento_aceita_zeros_a_direita_sem_falso_positivo_de_escala(cenario):
    # `casas_decimais()` normaliza antes de medir — "100.000" tem a MESMA
    # precisão real de "100" (achado 4 reaproveitado, contabilidade).
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.000",
        historico="Zeros à direita",
        recebido_de=OrigemRecebimento.PJ,
    )
    assert lancamento.valor == Decimal("100.00")


def test_lancamento_recusa_data_fora_da_faixa(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(1999, 12, 31),
            valor="100.00",
            historico="Data antiga demais",
            recebido_de=OrigemRecebimento.PJ,
        )
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date.today() + timedelta(days=31),
            valor="100.00",
            historico="Data futura demais",
            recebido_de=OrigemRecebimento.PJ,
        )


def test_lancamento_despesa_recusa_campos_de_receita(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_despesa"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="Despesa com recebido_de",
            recebido_de=OrigemRecebimento.PJ,
        )


def test_lancamento_receita_exige_recebido_de(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="Receita sem recebido_de",
        )


def test_trabalho_nao_assalariado_de_pf_exige_os_dois_cpfs(cenario):
    conta_trabalho = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="TNA",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=conta_trabalho,
            data=date(2026, 1, 15),
            valor="100.00",
            historico="Sem CPFs",
            recebido_de=OrigemRecebimento.PF,
        )

    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta_trabalho,
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Com os dois CPFs",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento=CPF_TITULAR,
        cpf_beneficiario_servico=CPF_BENEFICIARIO,
    )
    assert lancamento.pk is not None


def test_lancamento_recusa_cpf_com_formato_invalido(cenario):
    conta_trabalho = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="TNA2",
        nome="Trabalho não assalariado 2",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=conta_trabalho,
            data=date(2026, 1, 15),
            valor="100.00",
            historico="CPF malformado",
            recebido_de=OrigemRecebimento.PF,
            cpf_titular_pagamento="00000000000",
            cpf_beneficiario_servico=CPF_BENEFICIARIO,
        )


def test_lancamento_aceita_cnpj_pagador_opcional_em_receita_de_pj(cenario):
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="500.00",
        historico="Recebido de PJ com CNPJ",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador=CNPJ_PAGADOR,
    )
    assert lancamento.cnpj_pagador == CNPJ_PAGADOR


def test_lancamento_e_imutavel(cenario):
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Original",
        recebido_de=OrigemRecebimento.PJ,
    )
    lancamento.historico = "Editado"
    with pytest.raises(LancamentoCaixaImutavelError):
        lancamento.save()
    with pytest.raises(LancamentoCaixaImutavelError):
        lancamento.delete()


# ---------------------------------------------------------------------------
# 3. Idempotência
# ---------------------------------------------------------------------------


def test_idempotencia_mesma_chave_mesmo_conteudo_nao_duplica(cenario):
    primeiro = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="200.00",
        historico="Idempotente",
        recebido_de=OrigemRecebimento.PJ,
        chave_idempotencia="chave-1",
    )
    segundo = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="200.00",
        historico="Idempotente",
        recebido_de=OrigemRecebimento.PJ,
        chave_idempotencia="chave-1",
    )
    assert primeiro.pk == segundo.pk
    assert segundo.criado_agora is False
    assert LancamentoCaixa.objects.filter(empresa=cenario["empresa_a"]).count() == 1


def test_idempotencia_mesma_chave_conteudo_diferente_e_conflito(cenario):
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="200.00",
        historico="Original",
        recebido_de=OrigemRecebimento.PJ,
        chave_idempotencia="chave-2",
    )
    with pytest.raises(ChaveIdempotenciaConflitanteCaixa):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="999.00",
            historico="Original",
            recebido_de=OrigemRecebimento.PJ,
            chave_idempotencia="chave-2",
        )
    assert LancamentoCaixa.objects.filter(empresa=cenario["empresa_a"]).count() == 1


def test_idempotencia_e_por_empresa_nao_global(cenario):
    # A mesma chave em EMPRESAS diferentes não conflita nem reaproveita —
    # a unicidade da constraint é (empresa, chave_idempotencia).
    conta_b = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_b"],
        codigo="RB",
        nome="Receita B",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    a = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="10.00",
        historico="A",
        recebido_de=OrigemRecebimento.PJ,
        chave_idempotencia="mesma-chave",
    )
    b = criar_lancamento_caixa(
        empresa=cenario["empresa_b"],
        conta=conta_b,
        data=date(2026, 1, 15),
        valor="20.00",
        historico="B",
        recebido_de=OrigemRecebimento.PJ,
        chave_idempotencia="mesma-chave",
    )
    assert a.pk != b.pk
    assert a.criado_agora and b.criado_agora


# ---------------------------------------------------------------------------
# 4. Estorno
# ---------------------------------------------------------------------------


def test_estorno_cria_lancamento_reverso_rastreavel(cenario):
    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="300.00",
        historico="A estornar",
        recebido_de=OrigemRecebimento.PJ,
    )
    estorno = estornar_lancamento_caixa(original)
    assert estorno.estorno_de_id == original.pk
    assert estorno.valor == original.valor
    assert estorno.conta_id == original.conta_id
    assert estorno.data >= original.data


def test_estorno_nao_pode_ser_estornado_de_novo(cenario):
    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="300.00",
        historico="A estornar",
        recebido_de=OrigemRecebimento.PJ,
    )
    estorno = estornar_lancamento_caixa(original)
    with pytest.raises(LancamentoCaixaInvalido):
        estornar_lancamento_caixa(estorno)


def test_lancamento_ja_estornado_nao_pode_ser_estornado_de_novo(cenario):
    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="300.00",
        historico="A estornar",
        recebido_de=OrigemRecebimento.PJ,
    )
    estornar_lancamento_caixa(original)
    with pytest.raises(LancamentoCaixaInvalido):
        estornar_lancamento_caixa(original)


def test_estorno_e_unico_no_banco_sob_contorno_do_servico(cenario):
    """Defesa RESIDUAL de corrida: a constraint de banco
    `lancamento_caixa_estorno_de_unico` segura mesmo que alguém contorne o
    serviço e grave um segundo estorno diretamente pelo ORM."""
    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="300.00",
        historico="A estornar",
        recebido_de=OrigemRecebimento.PJ,
    )
    estornar_lancamento_caixa(original)
    segundo_estorno = LancamentoCaixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 16),
        valor=Decimal("300.00"),
        historico="Segundo estorno direto no ORM",
        recebido_de=OrigemRecebimento.PJ,
        estorno_de=original,
    )
    with pytest.raises(IntegrityError):
        segundo_estorno.save()


def test_estorno_recusa_data_anterior_ao_original(cenario):
    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="300.00",
        historico="A estornar",
        recebido_de=OrigemRecebimento.PJ,
    )
    with pytest.raises(LancamentoCaixaInvalido):
        estornar_lancamento_caixa(original, data=date(2026, 1, 10))


# ---------------------------------------------------------------------------
# 5. Conciliação do relatório "Livro Caixa"
# ---------------------------------------------------------------------------


def test_apuracao_concilia_com_os_lancamentos_incluindo_estorno(cenario):
    receita_1 = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 5),
        valor="1000.00",
        historico="Recebimento 1",
        recebido_de=OrigemRecebimento.PJ,
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 10),
        valor="500.00",
        historico="Recebimento 2",
        recebido_de=OrigemRecebimento.PJ,
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_despesa"],
        data=date(2026, 1, 12),
        valor="200.00",
        historico="Despesa 1",
    )
    estornar_lancamento_caixa(receita_1, data=date(2026, 1, 20))

    apuracao = apurar_livro_caixa(
        empresa=cenario["empresa_a"], inicio=date(2026, 1, 1), fim=date(2026, 1, 31)
    )

    # Entradas: 1000 (recebimento 1) + 500 (recebimento 2) - 1000 (estorno) = 500.
    assert apuracao["total_entradas"] == Decimal("500.00")
    assert apuracao["total_saidas"] == Decimal("200.00")
    assert apuracao["saldo"] == Decimal("300.00")
    # O estorno aparece como linha PRÓPRIA — nunca oculto.
    assert len(apuracao["itens"]) == 4
    estornos_visiveis = [item for item in apuracao["itens"] if item["e_estorno"]]
    assert len(estornos_visiveis) == 1
    assert estornos_visiveis[0]["estorno_de_id"] == receita_1.pk

    soma_manual = sum(
        (-1 if item["e_estorno"] else 1) * item["valor"]
        for item in apuracao["itens"]
        if item["natureza"] == NaturezaCaixa.RECEITA
    ) - sum(
        (-1 if item["e_estorno"] else 1) * item["valor"]
        for item in apuracao["itens"]
        if item["natureza"] == NaturezaCaixa.DESPESA
    )
    assert soma_manual == apuracao["saldo"]


def test_apuracao_recorta_pelo_periodo(cenario):
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2025, 12, 31),
        valor="1000.00",
        historico="Fora do período",
        recebido_de=OrigemRecebimento.PJ,
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 1),
        valor="50.00",
        historico="Dentro do período",
        recebido_de=OrigemRecebimento.PJ,
    )
    apuracao = apurar_livro_caixa(
        empresa=cenario["empresa_a"], inicio=date(2026, 1, 1), fim=date(2026, 1, 31)
    )
    assert apuracao["total_entradas"] == Decimal("50.00")
    assert len(apuracao["itens"]) == 1


# ---------------------------------------------------------------------------
# 6. Isolamento entre empresas/escritórios
# ---------------------------------------------------------------------------


def test_criar_conta_de_uma_empresa_nao_aparece_para_outra(cenario):
    ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="ISO",
        nome="Só de A",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    assert not ContaLivroCaixa.objects.filter(empresa=cenario["empresa_b"], codigo="ISO").exists()


def test_api_lista_de_contas_nao_alcanca_empresa_de_outro_escritorio(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-iso")
    client.login(username="gestor-iso", password="senha-forte-123")

    resposta = client.get(
        reverse("livro_caixa:contas", kwargs={"empresa_id": cenario["empresa_b"].id})
    )
    # Empresa de outro escritório: 404 (nunca confirma existência).
    assert resposta.status_code == 404


def test_api_lista_de_contas_do_mesmo_escritorio_nao_mistura_empresas(client, cenario):
    # Duas empresas no MESMO escritório (diferente do teste acima, que só
    # prova o filtro de ESCRITÓRIO de `get_empresa()`): esta é a checagem
    # que de fato exercita o filtro `empresa=` de `get_queryset()` — uma
    # conta de OUTRA empresa do mesmo escritório nunca pode aparecer na
    # listagem.
    empresa_a2 = Empresa.objects.create(
        escritorio=cenario["escritorio_a"],
        razao_social="Segunda Empresa do Escritório A",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_BENEFICIARIO,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    ContaLivroCaixa.objects.create(
        empresa=empresa_a2,
        codigo="SO-DE-A2",
        nome="Conta só de A2",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-iso-mesmo-escritorio")
    client.login(username="gestor-iso-mesmo-escritorio", password="senha-forte-123")

    resposta = client.get(_url_contas(cenario["empresa_a"].id))
    assert resposta.status_code == 200
    codigos = {item["codigo"] for item in resposta.json()}
    assert "SO-DE-A2" not in codigos
    assert cenario["conta_receita"].codigo in codigos


# ---------------------------------------------------------------------------
# 7. Recusa por modo de escrituração (espelho, nos dois sentidos)
# ---------------------------------------------------------------------------


def test_recusar_se_nao_livro_caixa_aceita_empresa_em_livro_caixa(cenario):
    recusar_se_nao_livro_caixa(cenario["empresa_a"])  # não levanta


def test_recusar_se_nao_livro_caixa_recusa_empresa_em_contabilidade(cenario):
    with pytest.raises(EmpresaNaoEmModoLivroCaixa):
        recusar_se_nao_livro_caixa(cenario["empresa_contabilidade"])


def test_criar_conta_livro_caixa_service_recusa_empresa_de_contabilidade(cenario):
    with pytest.raises(ValidationError):
        criar_conta_livro_caixa(
            empresa=cenario["empresa_contabilidade"],
            codigo="X",
            nome="X",
            natureza=NaturezaCaixa.RECEITA,
            codigo_carne_leao="R01.003.001",
        )


# ---------------------------------------------------------------------------
# 8. API — contratos, papéis e fluxo completo
# ---------------------------------------------------------------------------


def _url_contas(empresa_id):
    return reverse("livro_caixa:contas", kwargs={"empresa_id": empresa_id})


def _url_lancamentos(empresa_id):
    return reverse("livro_caixa:lancamentos", kwargs={"empresa_id": empresa_id})


def _url_estornar(empresa_id, lancamento_id):
    return reverse(
        "livro_caixa:estornar", kwargs={"empresa_id": empresa_id, "lancamento_id": lancamento_id}
    )


def _url_relatorio(empresa_id):
    return reverse("livro_caixa:livro-caixa", kwargs={"empresa_id": empresa_id})


def test_api_cria_conta_com_sucesso(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-conta")
    client.login(username="gestor-conta", password="senha-forte-123")

    resposta = client.post(
        _url_contas(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "codigo": "API1",
                "nome": "Receita via API",
                "natureza": "receita",
                "codigo_carne_leao": "R01.003.001",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    assert ContaLivroCaixa.objects.filter(empresa=cenario["empresa_a"], codigo="API1").exists()


def test_api_recusa_campo_desconhecido_no_corpo_de_conta(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-campo")
    client.login(username="gestor-campo", password="senha-forte-123")

    resposta = client.post(
        _url_contas(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "codigo": "API2",
                "nome": "X",
                "natureza": "receita",
                "codigo_carne_leao": "R01.003.001",
                "empresa": 999,
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert not ContaLivroCaixa.objects.filter(empresa=cenario["empresa_a"], codigo="API2").exists()


def test_api_cria_lancamento_com_sucesso_e_idempotencia(client, cenario):
    _usuario_com_papel(Papel.ANALISTA, cenario["escritorio_a"], "analista-lanc")
    client.login(username="analista-lanc", password="senha-forte-123")

    corpo = json.dumps(
        {
            "conta": cenario["conta_receita"].id,
            "data": "2026-01-15",
            "valor": "250.00",
            "historico": "Via API",
            "recebido_de": "PJ",
        }
    )
    resposta_1 = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=corpo,
        content_type="application/json",
        headers={"Idempotency-Key": "chave-api-1"},
    )
    assert resposta_1.status_code == 201, resposta_1.content

    resposta_2 = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=corpo,
        content_type="application/json",
        headers={"Idempotency-Key": "chave-api-1"},
    )
    assert resposta_2.status_code == 200
    assert resposta_1.json()["id"] == resposta_2.json()["id"]
    assert LancamentoCaixa.objects.filter(empresa=cenario["empresa_a"]).count() == 1


def test_api_valor_como_numero_json_e_recusado(client, cenario):
    _usuario_com_papel(Papel.ANALISTA, cenario["escritorio_a"], "analista-num")
    client.login(username="analista-num", password="senha-forte-123")

    resposta = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "conta": cenario["conta_receita"].id,
                "data": "2026-01-15",
                "valor": 250.00,
                "historico": "Número JSON",
                "recebido_de": "PJ",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert not LancamentoCaixa.objects.filter(empresa=cenario["empresa_a"]).exists()


def test_api_papel_cliente_nao_pode_escriturar(client, cenario):
    _usuario_com_papel(Papel.CLIENTE, cenario["escritorio_a"], "cliente-caixa")
    client.login(username="cliente-caixa", password="senha-forte-123")

    resposta = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "conta": cenario["conta_receita"].id,
                "data": "2026-01-15",
                "valor": "10.00",
                "historico": "Tentativa",
                "recebido_de": "PJ",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 403


def test_api_papel_paralegal_le_mas_nao_escritura(client, cenario):
    _usuario_com_papel(Papel.PARALEGAL, cenario["escritorio_a"], "paralegal-caixa")
    client.login(username="paralegal-caixa", password="senha-forte-123")

    leitura = client.get(_url_lancamentos(cenario["empresa_a"].id))
    assert leitura.status_code == 200

    escrita = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "conta": cenario["conta_receita"].id,
                "data": "2026-01-15",
                "valor": "10.00",
                "historico": "Tentativa",
                "recebido_de": "PJ",
            }
        ),
        content_type="application/json",
    )
    assert escrita.status_code == 403


def test_api_estorno_e_relatorio(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-estorno")
    client.login(username="gestor-estorno", password="senha-forte-123")

    criacao = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "conta": cenario["conta_receita"].id,
                "data": "2026-02-01",
                "valor": "400.00",
                "historico": "A estornar via API",
                "recebido_de": "PJ",
            }
        ),
        content_type="application/json",
    )
    lancamento_id = criacao.json()["id"]

    estorno = client.post(_url_estornar(cenario["empresa_a"].id, lancamento_id))
    assert estorno.status_code == 201, estorno.content
    assert estorno.json()["estorno_de"] == lancamento_id

    # O ESTORNO é datado pelo SERVIDOR como HOJE (RC-78 por analogia — a
    # view não aceita 'data' no corpo do estorno), não na data do
    # lançamento original — por isso o período do relatório precisa
    # alcançar as duas datas para conciliar de fato.
    relatorio = client.get(
        _url_relatorio(cenario["empresa_a"].id)
        + f"?inicio=2026-02-01&fim={(date.today() + timedelta(days=1)).isoformat()}"
    )
    assert relatorio.status_code == 200
    corpo = relatorio.json()
    assert corpo["total_entradas"] == "0.00"
    assert len(corpo["itens"]) == 2


def test_api_recusa_toda_rota_para_empresa_em_contabilidade(client, cenario):
    """DL-046, item 2 do FAZER: espelho da varredura DL-038 — nenhuma rota
    do livro-caixa aceita empresa em modo contabilidade."""
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-espelho")
    client.login(username="gestor-espelho", password="senha-forte-123")
    empresa_id = cenario["empresa_contabilidade"].id

    resposta_contas = client.get(_url_contas(empresa_id))
    assert resposta_contas.status_code == 400
    assert "empresa" in resposta_contas.json()

    resposta_lancamentos = client.get(_url_lancamentos(empresa_id))
    assert resposta_lancamentos.status_code == 400

    resposta_relatorio = client.get(
        _url_relatorio(empresa_id) + "?inicio=2026-01-01&fim=2026-01-31"
    )
    assert resposta_relatorio.status_code == 400


def test_empresa_em_livro_caixa_continua_recusada_na_contabilidade(client, cenario):
    """A outra metade do item 2: nenhuma mudança desta etapa em
    `apps.contabilidade` deveria afetar a recusa já existente (DL-038)."""
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-contab")
    client.login(username="gestor-contab", password="senha-forte-123")

    resposta = client.get(
        reverse("contabilidade:diario", kwargs={"empresa_id": cenario["empresa_a"].id})
    )
    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# 9. A1 — sair do livro-caixa com movimento é recusado (espelho do R6/DL-038)
# ---------------------------------------------------------------------------


def test_recusar_transicao_para_contabilidade_com_conta_gravada(cenario):
    empresa = cenario["empresa_a"]
    with pytest.raises(TransicaoParaContabilidadeInvalida):
        recusar_transicao_para_contabilidade_com_movimento_de_caixa(
            empresa,
            modo_anterior=ModoEscrituracao.LIVRO_CAIXA,
            modo_novo=ModoEscrituracao.CONTABILIDADE,
        )


def test_recusar_transicao_para_contabilidade_com_lancamento_gravado(cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Movimento existente",
        recebido_de=OrigemRecebimento.PJ,
    )
    with pytest.raises(TransicaoParaContabilidadeInvalida):
        recusar_transicao_para_contabilidade_com_movimento_de_caixa(
            empresa,
            modo_anterior=ModoEscrituracao.LIVRO_CAIXA,
            modo_novo=ModoEscrituracao.CONTABILIDADE,
        )


def test_recusar_transicao_para_contabilidade_sem_movimento_e_aceita(cenario):
    empresa = cenario["empresa_b"]  # não tem conta nem lançamento
    recusar_transicao_para_contabilidade_com_movimento_de_caixa(
        empresa,
        modo_anterior=ModoEscrituracao.LIVRO_CAIXA,
        modo_novo=ModoEscrituracao.CONTABILIDADE,
    )  # não levanta


def test_empresa_full_clean_recusa_troca_para_contabilidade_com_lancamento(cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Movimento existente",
        recebido_de=OrigemRecebimento.PJ,
    )
    empresa.modo_escrituracao = ModoEscrituracao.CONTABILIDADE
    with pytest.raises(ValidationError):
        empresa.full_clean(exclude=["cnpj"])
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA


def test_api_patch_recusa_troca_de_modo_com_lancamento_gravado(client, cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Movimento existente",
        recebido_de=OrigemRecebimento.PJ,
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-a1")
    client.login(username="gestor-a1", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.id}),
        data=json.dumps({"modo_escrituracao": "contabilidade"}),
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert "modo_escrituracao" in resposta.json()
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA
    # O livro-caixa continua acessível — não "some" da API.
    relatorio = client.get(_url_relatorio(empresa.id) + "?inicio=2026-01-01&fim=2026-12-31")
    assert relatorio.status_code == 200


def test_api_patch_aceita_troca_de_modo_sem_movimento_de_caixa(client, cenario):
    # Contraprova exigida pelo achado A1: a MESMA troca, numa empresa SEM
    # conta nem lançamento de caixa, continua aceita (200) — a guarda é da
    # TRANSIÇÃO com movimento, não do modo por si só.
    empresa = cenario["empresa_b"]
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_b"], "gestor-a1-contraprova")
    client.login(username="gestor-a1-contraprova", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.id}),
        data=json.dumps({"modo_escrituracao": "contabilidade"}),
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE


# ---------------------------------------------------------------------------
# 10. A2 — corrida de idempotência: nunca 500, {201,200} ou {201,409}
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_a2_corrida_de_idempotencia_mesmo_conteudo_dois_201_ou_200_nunca_500():
    """Reprodução do achado A2: duas requisições concorrentes com a MESMA
    `Idempotency-Key` e o MESMO corpo. Uma barreira dentro de `full_clean()`
    (o ponto exato que a rodada 1 mediu como o buraco: a pré-checagem de
    idempotência não vê a linha da outra requisição, que só existe depois
    do `save()`) garante que as DUAS threads passem a validação antes de
    qualquer uma tentar gravar — forçando a corrida real no `INSERT`."""
    escritorio = Escritorio.objects.create(nome="Escritório A2", cnpj="80000000000180")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa A2 Corrida",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="12345678909",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    conta = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="A2",
        nome="Receita A2",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-a2-corrida",
        email="gestor-a2-corrida@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    barreira = threading.Barrier(2)
    original_full_clean = LancamentoCaixa.full_clean

    def full_clean_com_barreira(self, *args, **kwargs):
        resultado = original_full_clean(self, *args, **kwargs)
        barreira.wait(timeout=5)
        return resultado

    corpo = json.dumps(
        {
            "conta": conta.id,
            "data": "2026-03-01",
            "valor": "500.00",
            "historico": "Corrida A2",
            "recebido_de": "PJ",
        }
    )
    resultados = {}

    def _postar(chave):
        try:
            cliente = Client(raise_request_exception=False)
            cliente.login(username="gestor-a2-corrida", password="senha-forte-123")
            resposta = cliente.post(
                reverse("livro_caixa:lancamentos", kwargs={"empresa_id": empresa.id}),
                data=corpo,
                content_type="application/json",
                headers={"Idempotency-Key": "chave-a2-corrida"},
            )
            resultados[chave] = resposta.status_code
        finally:
            connection.close()

    with mock.patch.object(LancamentoCaixa, "full_clean", full_clean_com_barreira):
        threads = [threading.Thread(target=_postar, args=(chave,)) for chave in "AB"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert set(resultados.values()) <= {201, 200}, resultados
    assert 500 not in resultados.values(), resultados
    assert sorted(resultados.values()) == [200, 201], resultados
    assert LancamentoCaixa.objects.filter(empresa=empresa).count() == 1


@pytest.mark.django_db(transaction=True)
def test_a2_corrida_de_idempotencia_conteudo_diferente_e_conflito_nunca_500():
    """Contraprova exigida pelo caso de teste 2: a MESMA corrida, agora com
    CONTEÚDO diferente sob a mesma chave — nunca 500, e o perdedor recebe
    409 (conflito), nunca 200 (o lançamento errado como se fosse sucesso)."""
    escritorio = Escritorio.objects.create(nome="Escritório A2b", cnpj="80000000000280")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa A2b Corrida",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="22255588846",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    conta = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="A2B",
        nome="Receita A2b",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-a2b-corrida",
        email="gestor-a2b-corrida@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    barreira = threading.Barrier(2)
    original_full_clean = LancamentoCaixa.full_clean

    def full_clean_com_barreira(self, *args, **kwargs):
        resultado = original_full_clean(self, *args, **kwargs)
        barreira.wait(timeout=5)
        return resultado

    resultados = {}

    def _postar(chave, valor):
        try:
            cliente = Client(raise_request_exception=False)
            cliente.login(username="gestor-a2b-corrida", password="senha-forte-123")
            resposta = cliente.post(
                reverse("livro_caixa:lancamentos", kwargs={"empresa_id": empresa.id}),
                data=json.dumps(
                    {
                        "conta": conta.id,
                        "data": "2026-03-01",
                        "valor": valor,
                        "historico": "Corrida A2b",
                        "recebido_de": "PJ",
                    }
                ),
                content_type="application/json",
                headers={"Idempotency-Key": "chave-a2b-corrida"},
            )
            resultados[chave] = resposta.status_code
        finally:
            connection.close()

    with mock.patch.object(LancamentoCaixa, "full_clean", full_clean_com_barreira):
        threads = [
            threading.Thread(target=_postar, args=("A", "500.00")),
            threading.Thread(target=_postar, args=("B", "999.00")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert 500 not in resultados.values(), resultados
    assert sorted(resultados.values()) == [201, 409], resultados
    assert LancamentoCaixa.objects.filter(empresa=empresa).count() == 1


# ---------------------------------------------------------------------------
# 11. M2 — caractere NUL em campo de texto livre (API) nunca 500
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["codigo", "nome"])
def test_api_conta_recusa_nul_em_texto_livre(client, cenario, campo):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], f"gestor-nul-conta-{campo}")
    client.login(username=f"gestor-nul-conta-{campo}", password="senha-forte-123")

    dados = {
        "codigo": "NUL1",
        "nome": "Conta NUL",
        "natureza": "receita",
        "codigo_carne_leao": "R01.003.001",
    }
    dados[campo] = "valor\x00com\x00nul"

    resposta = client.post(
        _url_contas(cenario["empresa_a"].id),
        data=json.dumps(dados),
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert not ContaLivroCaixa.objects.filter(empresa=cenario["empresa_a"], codigo="NUL1").exists()


def test_api_lancamento_recusa_nul_em_documento_origem(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-nul-lancamento")
    client.login(username="gestor-nul-lancamento", password="senha-forte-123")

    resposta = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "conta": cenario["conta_receita"].id,
                "data": "2026-01-15",
                "valor": "10.00",
                "historico": "Documento com NUL",
                "documento_origem": "nota\x00fiscal",
                "recebido_de": "PJ",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert not LancamentoCaixa.objects.filter(empresa=cenario["empresa_a"]).exists()


# ---------------------------------------------------------------------------
# 12. M3/M4 — conta com lançamento não muda de empresa nem de código; o
# estorno de um lançamento antigo continua possível depois de qualquer
# alteração PERMITIDA da conta
# ---------------------------------------------------------------------------


def test_conta_com_lancamento_nao_muda_de_empresa(cenario):
    conta = cenario["conta_receita"]
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta,
        data=date(2026, 1, 10),
        valor="100.00",
        historico="Movimento",
        recebido_de=OrigemRecebimento.PJ,
    )
    conta.empresa = cenario["empresa_b"]
    with pytest.raises(ValidationError):
        conta.full_clean()
    conta.refresh_from_db()
    assert conta.empresa_id == cenario["empresa_a"].id


def test_conta_com_lancamento_nao_muda_o_codigo_carne_leao(cenario):
    conta = cenario["conta_receita"]
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta,
        data=date(2026, 1, 10),
        valor="100.00",
        historico="Movimento",
        recebido_de=OrigemRecebimento.PJ,
    )
    conta.codigo_carne_leao = "R01.004.001"
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()
    assert "codigo_carne_leao" in excinfo.value.message_dict
    conta.refresh_from_db()
    assert conta.codigo_carne_leao == "R01.003.001"


def test_admin_nao_oferece_empresa_editavel_para_conta_existente():
    admin_instance = ContaLivroCaixaAdmin(ContaLivroCaixa, None)
    assert admin_instance.get_readonly_fields(None, obj=None) == []
    conta_qualquer = ContaLivroCaixa(pk=1)
    assert admin_instance.get_readonly_fields(None, obj=conta_qualquer) == ["empresa"]


def test_estorno_de_lancamento_antigo_continua_possivel_apos_alteracao_permitida_da_conta(
    cenario,
):
    """M4: o ESTORNO copia o original e não revalida contra a conta ATUAL —
    mesmo que a conta ainda não tivesse lançamento na hora da alteração
    (guarda de imutabilidade só passa a valer DEPOIS do primeiro
    lançamento), o estorno de um lançamento gravado ANTES da alteração
    nunca deve depender do estado atual da conta."""
    conta_livre = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="M4LIVRE",
        nome="Conta livre para reclassificar",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta_livre,
        data=date(2026, 1, 10),
        valor="100.00",
        historico="Antes da reclassificação",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento=CPF_TITULAR,
        cpf_beneficiario_servico=CPF_BENEFICIARIO,
    )

    # A guarda de imutabilidade (M4) já bloqueia esta troca, agora que a
    # conta tem lançamento — confirma que o caminho de origem está
    # fechado, ANTES de provar a segunda camada (o estorno).
    conta_livre.natureza = NaturezaCaixa.DESPESA
    conta_livre.codigo_carne_leao = "P10.001"
    with pytest.raises(ValidationError):
        conta_livre.full_clean()

    # O estorno do lançamento ANTIGO continua possível, mesmo que a
    # tentativa de reclassificar acima tenha sido corretamente recusada —
    # e mesmo que, num cenário anterior a esta correção, a conta pudesse
    # ter mudado de código livremente.
    estorno = estornar_lancamento_caixa(original)
    assert estorno.pk is not None
    assert estorno.cpf_titular_pagamento == CPF_TITULAR
    assert estorno.cpf_beneficiario_servico == CPF_BENEFICIARIO


# ---------------------------------------------------------------------------
# 13. Isolamento — M04 (lista de lançamentos, API), M06 (relatório, serviço)
# e M07 (estorno, API): duas empresas do MESMO escritório
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_isolamento(cenario):
    empresa_a2 = Empresa.objects.create(
        escritorio=cenario["escritorio_a"],
        razao_social="Segunda Empresa do Escritório A (isolamento)",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_BENEFICIARIO,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    conta_a2 = ContaLivroCaixa.objects.create(
        empresa=empresa_a2,
        codigo="ISO-A2",
        nome="Receita de A2",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    lancamento_a = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 5),
        valor="111.00",
        historico="Lançamento de A",
        recebido_de=OrigemRecebimento.PJ,
    )
    lancamento_a2 = criar_lancamento_caixa(
        empresa=empresa_a2,
        conta=conta_a2,
        data=date(2026, 1, 6),
        valor="222.00",
        historico="Lançamento de A2",
        recebido_de=OrigemRecebimento.PJ,
    )
    return {
        **cenario,
        "empresa_a2": empresa_a2,
        "conta_a2": conta_a2,
        "lancamento_a": lancamento_a,
        "lancamento_a2": lancamento_a2,
    }


def test_m04_api_lista_lancamentos_de_a_nao_contem_nada_de_a2(client, cenario_isolamento):
    _usuario_com_papel(Papel.GESTOR, cenario_isolamento["escritorio_a"], "gestor-m04")
    client.login(username="gestor-m04", password="senha-forte-123")

    resposta = client.get(_url_lancamentos(cenario_isolamento["empresa_a"].id))
    assert resposta.status_code == 200
    corpo = resposta.json()
    ids = {item["id"] for item in corpo["results"]}
    assert cenario_isolamento["lancamento_a"].id in ids
    assert cenario_isolamento["lancamento_a2"].id not in ids


def test_m06_apurar_livro_caixa_de_a_nao_contem_nada_de_a2(cenario_isolamento):
    apuracao = apurar_livro_caixa(
        empresa=cenario_isolamento["empresa_a"], inicio=date(2026, 1, 1), fim=date(2026, 1, 31)
    )
    ids = {item["lancamento_id"] for item in apuracao["itens"]}
    assert cenario_isolamento["lancamento_a"].id in ids
    assert cenario_isolamento["lancamento_a2"].id not in ids
    assert apuracao["total_entradas"] == Decimal("111.00")


def test_m07_api_estorno_de_a_com_id_de_lancamento_de_a2_da_404(client, cenario_isolamento):
    _usuario_com_papel(Papel.GESTOR, cenario_isolamento["escritorio_a"], "gestor-m07")
    client.login(username="gestor-m07", password="senha-forte-123")

    resposta = client.post(
        _url_estornar(cenario_isolamento["empresa_a"].id, cenario_isolamento["lancamento_a2"].id)
    )
    assert resposta.status_code == 404
    assert not LancamentoCaixa.objects.filter(
        estorno_de=cenario_isolamento["lancamento_a2"]
    ).exists()


# ---------------------------------------------------------------------------
# 14. M16 — formato de rendimento não pode ser enfraquecido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("codigo_invalido", ["R01.1.1", "R01.001.0011", "R01.001"])
def test_m16_codigo_de_rendimento_mal_formado_e_recusado(cenario, codigo_invalido):
    conta = ContaLivroCaixa(
        empresa=cenario["empresa_a"],
        codigo=f"M16-{codigo_invalido}",
        nome="Receita mal formada",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao=codigo_invalido,
    )
    with pytest.raises(ValidationError):
        conta.full_clean()


# ---------------------------------------------------------------------------
# 15. M17/M18 — CPF pelo leiaute oficial (M5/DE-087 item 6)
# ---------------------------------------------------------------------------


def test_m17_pf_sem_titular_e_sem_beneficiario_e_recusado(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="PF sem nada",
            recebido_de=OrigemRecebimento.PF,
        )


def test_m17_pf_com_titular_mas_sem_beneficiario_e_sem_indicador_e_recusado(cenario):
    """Isola a exigência do BENEFICIÁRIO (M17): titular presente, mas nem
    o CPF do beneficiário nem o indicador de "não informado" — a omissão
    tem que ser recusada, nunca aceita em silêncio."""
    with pytest.raises(LancamentoCaixaInvalido) as excinfo:
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="PF com titular, sem beneficiário e sem indicador",
            recebido_de=OrigemRecebimento.PF,
            cpf_titular_pagamento=CPF_TITULAR,
        )
    assert "beneficiário" in str(excinfo.value)


def test_m17_pf_com_titular_e_indicador_de_beneficiario_nao_informado_e_aceito(cenario):
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="PF, beneficiário não informado",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento=CPF_TITULAR,
        cpf_beneficiario_nao_informado=True,
    )
    assert lancamento.cpf_beneficiario_servico == ""
    assert lancamento.cpf_beneficiario_nao_informado is True


def test_m17_pf_com_beneficiario_e_indicador_marcado_e_incoerente(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="PF com os dois: contraditório",
            recebido_de=OrigemRecebimento.PF,
            cpf_titular_pagamento=CPF_TITULAR,
            cpf_beneficiario_servico=CPF_BENEFICIARIO,
            cpf_beneficiario_nao_informado=True,
        )


def test_m18_pj_sem_cpf_e_aceito(cenario):
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="PJ sem CPF nenhum",
        recebido_de=OrigemRecebimento.PJ,
    )
    assert lancamento.cpf_titular_pagamento == ""


def test_m18_pj_com_cpf_titular_e_recusado(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="PJ com CPF: incoerente",
            recebido_de=OrigemRecebimento.PJ,
            cpf_titular_pagamento=CPF_TITULAR,
        )


def test_m18_ex_com_cnpj_e_recusado(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="EX com CNPJ: incoerente",
            recebido_de=OrigemRecebimento.EX,
            cnpj_pagador=CNPJ_PAGADOR,
        )


def test_pf_com_cnpj_pagador_e_recusado(cenario):
    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 15),
            valor="100.00",
            historico="PF com CNPJ: incoerente",
            recebido_de=OrigemRecebimento.PF,
            cpf_titular_pagamento=CPF_TITULAR,
            cpf_beneficiario_nao_informado=True,
            cnpj_pagador=CNPJ_PAGADOR,
        )


# ---------------------------------------------------------------------------
# 16. M27 — valor como número JSON INTEIRO (sem parte decimal) também é
# recusado — o mutante sobreviveu porque o teste original só usava "250.00"
# como texto; o número JSON `250` (int, sem fração) é o caso que passava.
# ---------------------------------------------------------------------------


def test_m27_api_recusa_valor_como_numero_json_inteiro(client, cenario):
    _usuario_com_papel(Papel.ANALISTA, cenario["escritorio_a"], "analista-m27")
    client.login(username="analista-m27", password="senha-forte-123")

    resposta = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "conta": cenario["conta_receita"].id,
                "data": "2026-01-15",
                "valor": 250,
                "historico": "Inteiro JSON",
                "recebido_de": "PJ",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert not LancamentoCaixa.objects.filter(empresa=cenario["empresa_a"]).exists()


# ---------------------------------------------------------------------------
# 17. M28 — guarda de NATUREZA de conta com lançamento, isolada da
# coerência de código (troca natureza E código, os dois coerentes entre si,
# para a guarda de TRANSIÇÃO ser o que recusa, não a coerência)
# ---------------------------------------------------------------------------


def test_m28_conta_de_receita_com_lancamento_nao_muda_para_despesa_mesmo_com_codigo_coerente(
    cenario,
):
    conta = cenario["conta_receita"]
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta,
        data=date(2026, 1, 10),
        valor="100.00",
        historico="Movimento",
        recebido_de=OrigemRecebimento.PJ,
    )
    conta.natureza = NaturezaCaixa.DESPESA
    conta.codigo_carne_leao = "P10.001"  # coerente com despesa — a coerência NÃO recusa
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()
    mensagem = str(excinfo.value)
    assert "natureza" in mensagem and "lançamento gravado" in mensagem


# ---------------------------------------------------------------------------
# 18. M32 — estorno de DESPESA reduz as saídas e não altera as entradas
# ---------------------------------------------------------------------------


def test_m32_estorno_de_despesa_reduz_saidas_sem_alterar_entradas(cenario):
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 4, 1),
        valor="1000.00",
        historico="Receita do mês",
        recebido_de=OrigemRecebimento.PJ,
    )
    despesa = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_despesa"],
        data=date(2026, 4, 5),
        valor="300.00",
        historico="Despesa do mês",
    )
    estornar_lancamento_caixa(despesa, data=date(2026, 4, 10))

    apuracao = apurar_livro_caixa(
        empresa=cenario["empresa_a"], inicio=date(2026, 4, 1), fim=date(2026, 4, 30)
    )
    assert apuracao["total_entradas"] == Decimal("1000.00")
    assert apuracao["total_saidas"] == Decimal("0.00")
    assert apuracao["saldo"] == Decimal("1000.00")


# ---------------------------------------------------------------------------
# 19. B1 — conta inativa recusa lançamento novo; estorno de antigo continua
# ---------------------------------------------------------------------------


def test_b1_conta_inativa_recusa_lancamento_novo(cenario):
    conta = cenario["conta_receita"]
    conta.ativa = False
    conta.save(update_fields=["ativa"])

    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=conta,
            data=date(2026, 1, 15),
            valor="100.00",
            historico="Tentativa em conta inativa",
            recebido_de=OrigemRecebimento.PJ,
        )


def test_b1_conta_inativa_permite_estorno_de_lancamento_antigo(cenario):
    conta = cenario["conta_receita"]
    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta,
        data=date(2026, 1, 10),
        valor="100.00",
        historico="Antes de inativar",
        recebido_de=OrigemRecebimento.PJ,
    )
    conta.ativa = False
    conta.save(update_fields=["ativa"])

    estorno = estornar_lancamento_caixa(original)
    assert estorno.pk is not None


# ---------------------------------------------------------------------------
# 20. B2 — CPF/CNPJ com máscara são normalizados, não recusados por tamanho
# ---------------------------------------------------------------------------


def test_b2_cpf_com_mascara_e_normalizado(cenario):
    conta_trabalho = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="B2CPF",
        nome="Trabalho não assalariado B2",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    cpf_mascarado = f"{CPF_TITULAR[:3]}.{CPF_TITULAR[3:6]}.{CPF_TITULAR[6:9]}-{CPF_TITULAR[9:]}"
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta_trabalho,
        data=date(2026, 1, 15),
        valor="100.00",
        historico="CPF com máscara",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento=cpf_mascarado,
        cpf_beneficiario_nao_informado=True,
    )
    assert lancamento.cpf_titular_pagamento == CPF_TITULAR


def test_b2_cnpj_com_mascara_e_normalizado(cenario):
    cnpj_mascarado = "11.122.233/0001-83"
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="CNPJ com máscara",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador=cnpj_mascarado,
    )
    assert lancamento.cnpj_pagador == CNPJ_PAGADOR


def test_b2_api_aceita_cpf_com_mascara(client, cenario):
    conta_trabalho = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="B2CPFAPI",
        nome="Trabalho não assalariado B2 API",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-b2")
    client.login(username="gestor-b2", password="senha-forte-123")

    cpf_mascarado = f"{CPF_TITULAR[:3]}.{CPF_TITULAR[3:6]}.{CPF_TITULAR[6:9]}-{CPF_TITULAR[9:]}"
    resposta = client.post(
        _url_lancamentos(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "conta": conta_trabalho.id,
                "data": "2026-01-15",
                "valor": "100.00",
                "historico": "CPF com máscara via API",
                "recebido_de": "PF",
                "cpf_titular_pagamento": cpf_mascarado,
                "cpf_beneficiario_nao_informado": True,
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["cpf_titular_pagamento"] == CPF_TITULAR


# ---------------------------------------------------------------------------
# 21. B3 — tipos de `codigo`/`nome` na API (texto, com `strip`)
# ---------------------------------------------------------------------------


def test_b3_api_recusa_codigo_nao_textual(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-b3-tipo")
    client.login(username="gestor-b3-tipo", password="senha-forte-123")

    resposta = client.post(
        _url_contas(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "codigo": ["X1"],
                "nome": "Nome válido",
                "natureza": "receita",
                "codigo_carne_leao": "R01.003.001",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert (
        not ContaLivroCaixa.objects.filter(empresa=cenario["empresa_a"])
        .filter(codigo__contains="X1")
        .exists()
    )


def test_b3_api_recusa_codigo_so_de_espacos(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-b3-espaco")
    client.login(username="gestor-b3-espaco", password="senha-forte-123")

    resposta = client.post(
        _url_contas(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "codigo": "   ",
                "nome": "Nome válido",
                "natureza": "receita",
                "codigo_carne_leao": "R01.003.001",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content


def test_b3_api_grava_codigo_e_nome_sem_espaco_nas_bordas(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-b3-strip")
    client.login(username="gestor-b3-strip", password="senha-forte-123")

    resposta = client.post(
        _url_contas(cenario["empresa_a"].id),
        data=json.dumps(
            {
                "codigo": "  B3STRIP  ",
                "nome": "  Nome com espaço  ",
                "natureza": "receita",
                "codigo_carne_leao": "R01.003.001",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    conta = ContaLivroCaixa.objects.get(empresa=cenario["empresa_a"], codigo="B3STRIP")
    assert conta.nome == "Nome com espaço"


# ---------------------------------------------------------------------------
# 22. B5 — trilha: ações próprias para estorno e repetição idempotente
# ---------------------------------------------------------------------------


def test_b5_trilha_do_estorno_usa_acao_propria(cenario):
    from apps.auditoria.models import RegistroAuditoria

    original = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Original B5",
        recebido_de=OrigemRecebimento.PJ,
    )
    estorno = estornar_lancamento_caixa(original)

    registro_original = RegistroAuditoria.objects.get(
        acao="lancamento_caixa.criado", detalhes__conta=cenario["conta_receita"].codigo
    )
    assert registro_original is not None
    registro_estorno = RegistroAuditoria.objects.filter(
        acao="lancamento_caixa.estornado", detalhes__estorno_de_id=original.pk
    ).first()
    assert registro_estorno is not None
    assert registro_estorno.detalhes["estorno_de_id"] == original.pk
    assert estorno.pk is not None


def test_b5_trilha_da_repeticao_idempotente_e_registrada(cenario):
    from apps.auditoria.models import RegistroAuditoria

    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Idempotente B5",
        recebido_de=OrigemRecebimento.PJ,
        chave_idempotencia="chave-b5",
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="100.00",
        historico="Idempotente B5",
        recebido_de=OrigemRecebimento.PJ,
        chave_idempotencia="chave-b5",
    )
    assert RegistroAuditoria.objects.filter(acao="lancamento_caixa.criacao_repetida").exists()


# ---------------------------------------------------------------------------
# 23. B6 — paginação da API de lançamentos
# ---------------------------------------------------------------------------


def test_b6_api_lancamentos_e_paginada(client, cenario):
    for i in range(3):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_receita"],
            data=date(2026, 1, 1 + i),
            valor="10.00",
            historico=f"Lançamento {i}",
            recebido_de=OrigemRecebimento.PJ,
        )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-b6")
    client.login(username="gestor-b6", password="senha-forte-123")

    resposta = client.get(_url_lancamentos(cenario["empresa_a"].id))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo.keys()) >= {"count", "next", "previous", "results"}
    assert corpo["count"] == 3
    assert len(corpo["results"]) == 3


# ---------------------------------------------------------------------------
# 24. D3 — relatório separa saídas P20 (dedução do carnê-leão) das despesas
# de custeio, mantendo o saldo de caixa conciliado
# ---------------------------------------------------------------------------


def test_d3_relatorio_separa_p20_das_despesas_de_custeio(cenario):
    conta_p20 = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="P20-INSS",
        nome="Previdência oficial (dedução do carnê-leão)",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00001",
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 5, 1),
        valor="1000.00",
        historico="Receita",
        recebido_de=OrigemRecebimento.PJ,
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_despesa"],
        data=date(2026, 5, 2),
        valor="200.00",
        historico="Despesa de custeio",
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta_p20,
        data=date(2026, 5, 3),
        valor="150.00",
        historico="INSS do mês",
    )

    apuracao = apurar_livro_caixa(
        empresa=cenario["empresa_a"], inicio=date(2026, 5, 1), fim=date(2026, 5, 31)
    )
    assert apuracao["total_entradas"] == Decimal("1000.00")
    assert apuracao["total_saidas_custeio"] == Decimal("200.00")
    assert apuracao["total_saidas_deducao_carne_leao"] == Decimal("150.00")
    # O SALDO de caixa continua conciliado — as duas saídas juntas.
    assert apuracao["total_saidas"] == Decimal("350.00")
    assert apuracao["saldo"] == Decimal("650.00")

    grupos = {item["conta"]: item["grupo"] for item in apuracao["itens"]}
    assert grupos[cenario["conta_despesa"].codigo] == "saida_custeio"
    assert grupos["P20-INSS"] == "saida_deducao_carne_leao"
    assert grupos[cenario["conta_receita"].codigo] == "entrada"


def test_d3_api_relatorio_expoe_os_dois_grupos_de_saida(client, cenario):
    conta_p20 = ContaLivroCaixa.objects.create(
        empresa=cenario["empresa_a"],
        codigo="P20-API",
        nome="Pensão alimentícia (dedução do carnê-leão)",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.02.00001",
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=conta_p20,
        data=date(2026, 6, 1),
        valor="80.00",
        historico="Pensão do mês",
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-d3")
    client.login(username="gestor-d3", password="senha-forte-123")

    resposta = client.get(
        _url_relatorio(cenario["empresa_a"].id) + "?inicio=2026-06-01&fim=2026-06-30"
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total_saidas_deducao_carne_leao"] == "80.00"
    assert corpo["total_saidas_custeio"] == "0.00"
    assert any(item["grupo"] == "saida_deducao_carne_leao" for item in corpo["itens"])
