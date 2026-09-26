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
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
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
