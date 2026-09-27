"""DL-046, fatia 3 — arquivos de importação do Carnê-Leão Web (RC-127).
Servidor + API; a tela vem depois pelo `especialista-frontend`.

Cobre: os três campos novos (ocupação, IRRF, competência/multa/juros da
previdência oficial) com sucesso/erro/limite; o serviço
`gerar_arquivos_carne_leao` reproduzindo, LINHA A LINHA, os arquivos-modelo
oficiais da Receita (fixture em `fixtures/carne_leao_modelos/`, README com a
origem); codificação ISO-8859-1 e quebra de linha CRLF (HI-41); estorno e
estornado fora do arquivo (inclusive quando o par cai em lados diferentes
do período pedido); conta sem código excluída; pendências (ocupação
ausente, competência ausente, histórico longo/com caractere não-latin1/com
';', código fora das tabelas, P20.01.00004 fora do escopo); período fora de
um único ano-calendário recusado; conferência batendo com o Livro Caixa;
isolamento entre empresas/escritórios; papéis; modo contabilidade; API
nunca devolvendo 500.

`_linha_esperada`/`_linha_por_marcador`: as duas funções que comparam a
linha GERADA com a linha do ARQUIVO-MODELO oficial, trocando cada
placeholder pelo valor sintético do teste na ORDEM em que aparece no
modelo (preserva posição e contagem de campos — nunca adiciona nem remove
`;`).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.empresas.validators import validar_codigo_ocupacao
from apps.livro_caixa.carne_leao_arquivos import (
    GeracaoArquivoCarneLeaoBloqueada,
    PeriodoInvalidoParaArquivoCarneLeaoWeb,
    _competencia_csv,
    _data_csv,
    _valor_csv,
    gerar_arquivos_carne_leao,
)
from apps.livro_caixa.models import ContaLivroCaixa, NaturezaCaixa, OrigemRecebimento
from apps.livro_caixa.services import criar_lancamento_caixa, estornar_lancamento_caixa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CPF_TITULAR = "11144477735"
CPF_BENEFICIARIO = "22255588846"
CNPJ_PAGADOR = "11122233000183"
OCUPACAO_MEDICO = "225"
OCUPACAO_ADVOGADO = "241"

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "carne_leao_modelos"


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _linhas_do_modelo(nome_arquivo):
    """As linhas do arquivo-modelo oficial, decodificadas — o oráculo dos
    testes de reprodução (ver o README da fixture)."""
    bruto = (_FIXTURES / nome_arquivo).read_bytes()
    texto = bruto.decode("iso-8859-1")
    return [linha for linha in texto.split("\r\n") if linha]


def _linha_por_marcador(linhas, marcador):
    """A ÚNICA linha do modelo que contém `marcador` — nunca por índice
    (frágil à ordem do arquivo-modelo). O teste falha alto e claro se
    `marcador` não identificar exatamente uma linha."""
    encontradas = [linha for linha in linhas if marcador in linha]
    assert len(encontradas) == 1, (
        f"marcador {marcador!r} não identifica exatamente 1 linha do modelo "
        f"(encontrou {len(encontradas)}): {encontradas}"
    )
    return encontradas[0]


def _linha_esperada(linha_modelo, substituicoes):
    """Substitui cada placeholder do modelo pelo valor sintético do teste,
    NA ORDEM em que aparece na linha (`substituicoes` é uma lista de
    `(placeholder, valor)`, não um dict — o mesmo placeholder pode repetir,
    ex.: dois CPF `99999999999`, um do titular e outro do beneficiário)."""
    esperada = linha_modelo
    for placeholder, valor in substituicoes:
        assert placeholder in esperada, (
            f"placeholder {placeholder!r} não encontrado na linha do "
            f"modelo (já processada até aqui): {esperada!r}"
        )
        esperada = esperada.replace(placeholder, valor, 1)
    return esperada


def _linhas_geradas(conteudo_bytes):
    return [linha for linha in conteudo_bytes.decode("iso-8859-1").split("\r\n") if linha]


@pytest.fixture
def cenario():
    escritorio_a = Escritorio.objects.create(nome="Escritório Arquivos A", cnpj="22233344000155")
    escritorio_b = Escritorio.objects.create(nome="Escritório Arquivos B", cnpj="66677788000199")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Fulano Autônomo — Arquivos",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="12345678909",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
        # HI-34: ocupação do CADASTRO — usada nas linhas de trabalho não
        # assalariado que não sobrepõem por conta.
        codigo_ocupacao=OCUPACAO_MEDICO,
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b,
        razao_social="Ciclano Autônomo — Arquivos",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Empresa Contabilidade Ltda — Arquivos",
        cnpj="22233344000188",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )

    conta_trabalho = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RT",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    # Sobreposição de ocupação POR CONTA (HI-34) — código diferente do
    # cadastro, para provar que a conta sobrepõe.
    conta_trabalho_advogado = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RTADV",
        nome="Trabalho não assalariado — advocacia",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
        codigo_ocupacao=OCUPACAO_ADVOGADO,
    )
    conta_notarial = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RN",
        nome="Emolumentos",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.002",
    )
    conta_aluguel = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RA",
        nome="Aluguel recebido",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta_outros = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RO",
        nome="Outros rendimentos",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.004.001",
    )
    conta_pensao_recebida = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RP",
        nome="Pensão alimentícia recebida",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.002.001",
    )
    conta_despesa_dedutivel_padrao = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="D10",
        nome="Água do escritório (plano padrão)",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P10.01.00001",
    )
    conta_despesa_nao_dedutivel_padrao = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="D11",
        nome="Aplicação de capital (plano padrão)",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P11.01.00001",
    )
    conta_despesa_plano_proprio = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="D10P",
        nome="Despesa dedutível — plano próprio",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P10.99.00007",
    )
    conta_previdencia = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DPREV",
        nome="Previdência oficial",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00001",
    )
    conta_pensao_paga = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DPENSAO",
        nome="Pensão alimentícia paga",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00002",
    )
    conta_imposto_exterior = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DEXT",
        nome="Imposto pago no exterior",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00003",
    )
    conta_imposto_pago = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DIMP",
        nome="Imposto pago (carnê-leão)",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00004",
    )
    # Conta SEM código do Carnê-Leão Web — só alcançável por ORM direto
    # (`full_clean()`/o serviço sempre exigem o código); mesmo padrão de
    # "lançamento legado" já usado no resto da suíte deste módulo (N12).
    conta_sem_codigo = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RSC",
        nome="Receita legada sem código",
        natureza=NaturezaCaixa.RECEITA,
    )

    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "empresa_contabilidade": empresa_contabilidade,
        "conta_trabalho": conta_trabalho,
        "conta_trabalho_advogado": conta_trabalho_advogado,
        "conta_notarial": conta_notarial,
        "conta_aluguel": conta_aluguel,
        "conta_outros": conta_outros,
        "conta_pensao_recebida": conta_pensao_recebida,
        "conta_despesa_dedutivel_padrao": conta_despesa_dedutivel_padrao,
        "conta_despesa_nao_dedutivel_padrao": conta_despesa_nao_dedutivel_padrao,
        "conta_despesa_plano_proprio": conta_despesa_plano_proprio,
        "conta_previdencia": conta_previdencia,
        "conta_pensao_paga": conta_pensao_paga,
        "conta_imposto_exterior": conta_imposto_exterior,
        "conta_imposto_pago": conta_imposto_pago,
        "conta_sem_codigo": conta_sem_codigo,
    }


# ---------------------------------------------------------------------------
# 1. Reprodução linha a linha dos arquivos-modelo oficiais — critério 1 do
#    plano. Cada teste cria UM lançamento sintético, gera o arquivo e
#    compara com a linha do modelo, placeholders trocados.
# ---------------------------------------------------------------------------


def test_trabalho_nao_assalariado_pf_com_beneficiario_informado(cenario):
    linhas_modelo = _linhas_do_modelo("trabalho_nao_assalariado.csv")
    modelo = _linha_por_marcador(linhas_modelo, "CPF do beneficiario foi informado")

    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 15)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="1234.56",
        historico="Honorários de consulta - teste fatia 3",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento=CPF_TITULAR,
        cpf_beneficiario_servico=CPF_BENEFICIARIO,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999", OCUPACAO_MEDICO),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimento do trabalho não assalariado recebido de "
                "Pessoa Física quando o CPF do beneficiario foi informado",
                lancamento.historico,
            ),
            ("99999999999", CPF_TITULAR),
            ("99999999999", CPF_BENEFICIARIO),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    # Mesmo NÚMERO de campos do modelo (critério 1 do plano).
    assert esperada.count(";") == modelo.count(";")


def test_trabalho_nao_assalariado_pf_sem_beneficiario_informado(cenario):
    linhas_modelo = _linhas_do_modelo("trabalho_nao_assalariado.csv")
    modelo = _linha_por_marcador(linhas_modelo, "CPF do beneficiario não for informado")

    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 16)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="800.00",
        historico="Honorários sem CPF do beneficiário - teste",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento=CPF_TITULAR,
        cpf_beneficiario_nao_informado=True,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999", OCUPACAO_MEDICO),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimento do trabalho não assalariado recebido de "
                "Pessoa Física quando o CPF do beneficiario não for informado",
                lancamento.historico,
            ),
            ("99999999999", CPF_TITULAR),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")


def test_trabalho_nao_assalariado_pj_com_irrf(cenario):
    linhas_modelo = _linhas_do_modelo("trabalho_nao_assalariado.csv")
    modelo = _linha_por_marcador(linhas_modelo, "Pessoa Jurídica com IRRF")

    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 17)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="5000.00",
        historico="Honorários de pessoa jurídica com retenção - teste",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador=CNPJ_PAGADOR,
        valor_irrf="150.75",
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999", OCUPACAO_MEDICO),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimento do trabalho não assalariado recebido de "
                "Pessoa Jurídica com IRRF",
                lancamento.historico,
            ),
            ("99999999999999", CNPJ_PAGADOR),
            ("99999,99", _valor_csv(lancamento.valor_irrf)),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")


def test_trabalho_nao_assalariado_pj_sem_irrf(cenario):
    linhas_modelo = _linhas_do_modelo("trabalho_nao_assalariado.csv")
    modelo = _linha_por_marcador(linhas_modelo, "Pessoa Jurídica sem IRRF")

    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 18)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="3200.00",
        historico="Honorários de pessoa jurídica sem retenção - teste",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador=CNPJ_PAGADOR,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999", OCUPACAO_MEDICO),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimento do trabalho não assalariado recebido de "
                "Pessoa Jurídica sem IRRF",
                lancamento.historico,
            ),
            ("99999999999999", CNPJ_PAGADOR),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")


def test_trabalho_nao_assalariado_exterior(cenario):
    linhas_modelo = _linhas_do_modelo("trabalho_nao_assalariado.csv")
    modelo = _linha_por_marcador(linhas_modelo, "no exterior no Exterior")

    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 19)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="2000.00",
        historico="Honorários do exterior - teste",
        recebido_de=OrigemRecebimento.EX,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999", OCUPACAO_MEDICO),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimento do trabalho não assalariado no exterior no "
                "Exterior",
                lancamento.historico,
            ),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")


def test_trabalho_nao_assalariado_ocupacao_sobreposta_pela_conta(cenario):
    """HI-34: a conta SOBREPÕE a ocupação do cadastro."""
    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 20)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho_advogado"],
        data=dia,
        valor="900.00",
        historico="Honorários de advocacia - teste sobreposição",
        recebido_de=OrigemRecebimento.EX,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    linha = (
        f"{_data_csv(dia)};R01.001.001;{OCUPACAO_ADVOGADO};{_valor_csv(lancamento.valor)};;"
        f"{lancamento.historico};EX"
    )
    assert linha in _linhas_geradas(rendimentos)
    # A ocupação do CADASTRO (médico) não aparece nesta linha.
    assert OCUPACAO_MEDICO not in linha


def test_notarial_exterior(cenario):
    linhas_modelo = _linhas_do_modelo("servicos_notariais_e_registro.csv")
    modelo = _linha_por_marcador(linhas_modelo, "recebido do Exterior")

    empresa = cenario["empresa_a"]
    dia = date(2026, 4, 5)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_notarial"],
        data=dia,
        valor="700.00",
        historico="Emolumentos do exterior - teste",
        recebido_de=OrigemRecebimento.EX,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimentos de serviços notariais e de registro "
                "recebido do Exterior",
                lancamento.historico,
            ),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")
    # Ocupação SEMPRE 117 no modelo notarial, mesmo sem cadastro/conta.
    assert ";117;" in esperada


def test_notarial_pessoa_fisica(cenario):
    linhas_modelo = _linhas_do_modelo("servicos_notariais_e_registro.csv")
    modelo = _linha_por_marcador(linhas_modelo, "recebido de Pessoa Física")

    empresa = cenario["empresa_a"]
    dia = date(2026, 4, 6)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_notarial"],
        data=dia,
        valor="1500.00",
        historico="Emolumentos de pessoa física - teste",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento=CPF_TITULAR,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimentos de serviços notariais e de registro "
                "recebido de Pessoa Física",
                lancamento.historico,
            ),
            ("99999999999", CPF_TITULAR),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")


def test_notarial_pessoa_juridica_com_irrf(cenario):
    linhas_modelo = _linhas_do_modelo("servicos_notariais_e_registro.csv")
    modelo = _linha_por_marcador(linhas_modelo, "Pessoa Jurídica com IRRF")

    empresa = cenario["empresa_a"]
    dia = date(2026, 4, 7)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_notarial"],
        data=dia,
        valor="4000.00",
        historico="Emolumentos de pessoa jurídica com retenção - teste",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador=CNPJ_PAGADOR,
        valor_irrf="80.00",
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimentos de serviços notariais e de registro "
                "recebido de Pessoa Jurídica com IRRF",
                lancamento.historico,
            ),
            ("99999999999999", CNPJ_PAGADOR),
            ("99999,99", _valor_csv(lancamento.valor_irrf)),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")


def test_notarial_pessoa_juridica_sem_irrf(cenario):
    linhas_modelo = _linhas_do_modelo("servicos_notariais_e_registro.csv")
    modelo = _linha_por_marcador(linhas_modelo, "Pessoa Jurídica sem IRRF")

    empresa = cenario["empresa_a"]
    dia = date(2026, 4, 8)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_notarial"],
        data=dia,
        valor="2200.00",
        historico="Emolumentos de pessoa jurídica sem retenção - teste",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador=CNPJ_PAGADOR,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para rendimentos de serviços notariais e de registro "
                "recebido de Pessoa Jurídica sem IRRF",
                lancamento.historico,
            ),
            ("99999999999999", CNPJ_PAGADOR),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")


@pytest.mark.parametrize(
    ("historico_modelo", "conta_chave", "origem", "sufixo_marcador"),
    [
        (
            "Modelo de linha para rendimentos de Aluguel recebido de Pessoa Física",
            "conta_aluguel",
            OrigemRecebimento.PF,
            ";PF",
        ),
        (
            "Modelo de linha para rendimentos de Aluguel recebido do Exterior",
            "conta_aluguel",
            OrigemRecebimento.EX,
            ";EX",
        ),
        (
            "Modelo de linha para outros rendimentos recebido de Pessoa Física",
            "conta_outros",
            OrigemRecebimento.PF,
            ";PF",
        ),
        (
            "Modelo de linha para outros rendimentos recebido do Exterior",
            "conta_outros",
            OrigemRecebimento.EX,
            ";EX",
        ),
    ],
)
def test_aluguel_e_outros_sem_deducao(
    cenario, historico_modelo, conta_chave, origem, sufixo_marcador
):
    """As quatro linhas do modelo SEM dedução informada (HI-39: o valor da
    dedução fica sempre vazio nesta fatia — a linha correspondente do
    modelo é a mais curta, sem "com dedução informada"). O marcador é o
    próprio texto de histórico do modelo — único por linha, sem precisar
    do sufixo de "recebido de" além do necessário para distinguir a linha
    "sem dedução" da "com dedução informada" (que tem o MESMO prefixo)."""
    linhas_modelo = _linhas_do_modelo("aluguel_e_outros_rendimentos.csv")
    modelo = _linha_por_marcador(linhas_modelo, historico_modelo + sufixo_marcador)

    empresa = cenario["empresa_a"]
    dia = date(2026, 5, 10)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario[conta_chave],
        data=dia,
        valor="1100.00",
        historico="Rendimento sintético de teste - fatia 3",
        recebido_de=origem,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (historico_modelo, lancamento.historico),
        ],
    )
    assert esperada in _linhas_geradas(rendimentos)
    assert esperada.count(";") == modelo.count(";")
    # Código de ocupação e valor de dedução SEMPRE vazios neste modelo.
    assert esperada.split(";")[2] == ""
    assert esperada.split(";")[4] == ""


def test_pagamento_previdencia_oficial_completo(cenario):
    linhas_modelo = _linhas_do_modelo("pagamentos_gerais.csv")
    modelo = _linha_por_marcador(linhas_modelo, "Previdência Oficial")

    empresa = cenario["empresa_a"]
    dia = date(2026, 2, 20)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_previdencia"],
        data=dia,
        valor="600.00",
        historico="INSS competência 02/2026 - teste",
        competencia_previdencia=date(2026, 2, 1),
        multa_previdencia="30.00",
    )
    rendimentos_bytes, pagamentos_bytes, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    assert _linhas_geradas(rendimentos_bytes) == []

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            ("Modelo de linha para pagamento de Previdência Oficial", lancamento.historico),
            ("999999999,99", _valor_csv(lancamento.multa_previdencia)),
            ("99/9999", _competencia_csv(lancamento.competencia_previdencia)),
        ],
    )
    assert esperada in _linhas_geradas(pagamentos_bytes)
    assert esperada.count(";") == modelo.count(";")
    # Juros ficou VAZIO (não informado) — campo 6, entre multa e competência.
    assert esperada.split(";")[5] == ""


def test_pagamento_pensao_alimenticia_paga(cenario):
    linhas_modelo = _linhas_do_modelo("pagamentos_gerais.csv")
    modelo = _linha_por_marcador(linhas_modelo, "Pensão Alimentícia")

    empresa = cenario["empresa_a"]
    dia = date(2026, 2, 21)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_paga"],
        data=dia,
        valor="500.00",
        historico="Pensão paga - teste",
    )
    _rendimentos, pagamentos_bytes, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            ("Modelo de linha para pagamento de Pensão Alimentícia", lancamento.historico),
        ],
    )
    assert esperada in _linhas_geradas(pagamentos_bytes)
    assert esperada.count(";") == modelo.count(";")
    # Multa, juros e competência SEMPRE vazios neste código (mas
    # PRESENTES — este modelo não trunca campo vazio no fim da linha).
    campos = esperada.split(";")
    assert campos[4:7] == ["", "", ""]


def test_pagamento_imposto_pago_no_exterior(cenario):
    linhas_modelo = _linhas_do_modelo("pagamentos_gerais.csv")
    modelo = _linha_por_marcador(linhas_modelo, "Imposto Pago no Exterior")

    empresa = cenario["empresa_a"]
    dia = date(2026, 2, 22)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_imposto_exterior"],
        data=dia,
        valor="200.00",
        historico="Imposto pago no exterior - teste",
    )
    _rendimentos, pagamentos_bytes, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (
                "Modelo de linha para pagamento de Imposto Pago no Exterior",
                lancamento.historico,
            ),
        ],
    )
    assert esperada in _linhas_geradas(pagamentos_bytes)
    assert esperada.count(";") == modelo.count(";")


@pytest.mark.parametrize(
    ("marcador", "conta_chave", "codigo"),
    [
        ("Água do escritório/consultório", "conta_despesa_dedutivel_padrao", "P10.01.00001"),
        ("Aplicação de capital", "conta_despesa_nao_dedutivel_padrao", "P11.01.00001"),
    ],
)
def test_pagamento_plano_de_contas_padrao(cenario, marcador, conta_chave, codigo):
    linhas_modelo = _linhas_do_modelo("pagamentos_plano_de_contas_padrao.csv")
    modelo = _linha_por_marcador(linhas_modelo, marcador)
    assert f";{codigo};" in modelo  # confere que peguei a linha certa

    empresa = cenario["empresa_a"]
    dia = date(2026, 6, 1)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario[conta_chave],
        data=dia,
        valor="45.90",
        historico=f"Pagamento {marcador} - teste",
    )
    _rendimentos, pagamentos_bytes, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )

    esperada = _linha_esperada(
        modelo,
        [
            ("99/99/9999", _data_csv(dia)),
            ("999999999,99", _valor_csv(lancamento.valor)),
            (f"Modelo de linha para pagamento de {marcador}", lancamento.historico),
        ],
    )
    assert esperada in _linhas_geradas(pagamentos_bytes)
    assert esperada.count(";") == 3  # 4 campos, mesmo total do modelo


def test_pagamento_plano_proprio_regra_de_formacao(cenario):
    """Instrução oficial: "P10 + . + código da conta" para plano PRÓPRIO —
    qualquer sufixo (não só os códigos padrão do modelo) é reproduzido no
    formato de 4 campos, sem consulta ao arquivo-modelo (a instrução é a
    fonte, não um exemplo do arquivo-modelo, que só lista o plano padrão)."""
    empresa = cenario["empresa_a"]
    dia = date(2026, 6, 2)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_despesa_plano_proprio"],
        data=dia,
        valor="123.45",
        historico="Despesa do plano próprio - teste",
    )
    _rendimentos, pagamentos_bytes, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    linha = f"{_data_csv(dia)};P10.99.00007;{_valor_csv(lancamento.valor)};{lancamento.historico}"
    assert linha in _linhas_geradas(pagamentos_bytes)


# ---------------------------------------------------------------------------
# 2. Codificação e quebra de linha — HI-41.
# ---------------------------------------------------------------------------


def test_arquivos_saem_em_iso_8859_1_com_crlf(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 25)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="500.00",
        historico="Histórico com acentuação - ç, ã, é, ô",
        recebido_de=OrigemRecebimento.EX,
    )
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_despesa_dedutivel_padrao"],
        data=dia,
        valor="100.00",
        historico="Despesa com acentuação - ç, ã",
    )
    rendimentos, pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    for conteudo in (rendimentos, pagamentos):
        # Decodifica em latin-1 sem erro.
        texto = conteudo.decode("iso-8859-1")
        # Todo "\n" do arquivo é precedido de "\r" (CRLF, nunca LF solto —
        # HI-41), e o "ç" acentuado prova que a codificação é ISO-8859-1
        # (um único byte 0xE7), nunca UTF-8 (dois bytes para "ç").
        assert "\n" not in texto.replace("\r\n", "")
        assert b"\xe7" in conteudo  # "ç" em ISO-8859-1
        assert "ç".encode("utf-8") not in conteudo


# ---------------------------------------------------------------------------
# 3. Fora do arquivo: estorno/estornado; conta sem código.
# ---------------------------------------------------------------------------


def test_lancamento_estornado_e_o_proprio_estorno_ficam_fora(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 7, 10)
    original = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="1000.00",
        historico="Lançamento a ser estornado",
        recebido_de=OrigemRecebimento.EX,
    )
    estornar_lancamento_caixa(original)
    # Um lançamento NÃO estornado no mesmo período, para provar que o
    # arquivo não fica vazio por outro motivo.
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="1.00",
        historico="Lançamento normal - controle",
        recebido_de=OrigemRecebimento.EX,
    )

    rendimentos, _pagamentos, conferencia = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    linhas = _linhas_geradas(rendimentos)
    assert not any("1000,00" in linha for linha in linhas)
    assert any("1,00" in linha for linha in linhas)
    assert conferencia["lancamentos_excluidos_estorno"] == 2
    assert conferencia["total_rendimentos"] == Decimal("1.00")


def test_par_estorno_dividido_entre_dois_lados_do_periodo_ainda_fica_fora(cenario):
    """O estorno é sempre do MESMO mês do original (RC-130) — mas um
    período mais estreito que o mês pode conter só um dos dois. Mesmo
    assim, o ORIGINAL precisa ficar fora (a checagem de "foi estornado?"
    não se limita à janela do período — ver `_lancamentos_incluidos`)."""
    empresa = cenario["empresa_a"]
    original = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=date(2026, 7, 2),
        valor="777.00",
        historico="Original no início do mês",
        recebido_de=OrigemRecebimento.EX,
    )
    estornar_lancamento_caixa(original, data=date(2026, 7, 28))

    # Período cobre só o ORIGINAL (dia 2), não o estorno (dia 28).
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=date(2026, 7, 1), fim=date(2026, 7, 5), usuario=None
    )
    assert not any("777,00" in linha for linha in _linhas_geradas(rendimentos))


def test_conta_sem_codigo_fica_fora_do_arquivo(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 8, 1)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_sem_codigo"],
        data=dia,
        valor="999.00",
        historico="Receita de conta legada sem código",
        recebido_de=OrigemRecebimento.PF,
    )
    rendimentos, _pagamentos, conferencia = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    assert _linhas_geradas(rendimentos) == []
    assert conferencia["lancamentos_excluidos_sem_codigo"] == 1
    # A DIFERENÇA fica exposta na conferência, nunca escondida.
    assert conferencia["diferenca_rendimentos"] == Decimal("999.00")


# ---------------------------------------------------------------------------
# 4. Pendências — nada é truncado nem corrigido em silêncio.
# ---------------------------------------------------------------------------


def test_pendencia_ocupacao_ausente(cenario):
    empresa_sem_ocupacao = Empresa.objects.create(
        escritorio=cenario["escritorio_a"],
        razao_social="Sem Ocupação Cadastrada",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="98765432100",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    conta = ContaLivroCaixa.objects.create(
        empresa=empresa_sem_ocupacao,
        codigo="RT2",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    dia = date(2026, 9, 1)
    criar_lancamento_caixa(
        empresa=empresa_sem_ocupacao,
        conta=conta,
        data=dia,
        valor="100.00",
        historico="Sem ocupação",
        recebido_de=OrigemRecebimento.EX,
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa_sem_ocupacao, inicio=dia, fim=dia, usuario=None)
    pendencias = excinfo.value.pendencias
    assert len(pendencias) == 1
    assert pendencias[0].campo == "codigo_ocupacao"
    assert "ocupação" in pendencias[0].motivo


def test_pendencia_competencia_previdencia_ausente(cenario):
    """A competência é exigida no MODELO (clean()) — para provar a
    PENDÊNCIA (defesa em profundidade contra dado legado gravado por ORM
    direto, sem passar por `full_clean()`), o teste contorna o serviço."""
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 2)
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_previdencia"],
        data=dia,
        valor="300.00",
        historico="Previdência sem competência (legado)",
        competencia_previdencia=date(2026, 9, 1),
    )
    # Bypassa o modelo/serviço (dado legado) — igual ao padrão N12 do
    # resto da suíte deste módulo.
    from apps.livro_caixa.models import LancamentoCaixa as _LC

    _LC.objects.filter(pk=lancamento.pk).update(competencia_previdencia=None)

    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    pendencias = excinfo.value.pendencias
    assert len(pendencias) == 1
    assert pendencias[0].campo == "competencia_previdencia"


def test_pendencia_historico_maior_que_255(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 3)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="100.00",
        historico="X" * 256,
        recebido_de=OrigemRecebimento.EX,
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    pendencias = excinfo.value.pendencias
    assert len(pendencias) == 1
    assert pendencias[0].campo == "historico"
    assert "255" in pendencias[0].motivo


def test_historico_no_limite_de_255_nao_e_pendencia(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 4)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="100.00",
        historico="X" * 255,
        recebido_de=OrigemRecebimento.EX,
    )
    rendimentos, _pagamentos, _conf = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    assert any("X" * 255 in linha for linha in _linhas_geradas(rendimentos))


def test_pendencia_historico_com_caractere_nao_latin1(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 5)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="100.00",
        historico="Histórico com emoji 🙂 - sem representação em latin-1",
        recebido_de=OrigemRecebimento.EX,
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    pendencias = excinfo.value.pendencias
    assert len(pendencias) == 1
    assert pendencias[0].campo == "historico"
    assert "ISO-8859-1" in pendencias[0].motivo


def test_pendencia_historico_com_ponto_e_virgula(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 6)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="100.00",
        historico="Histórico; com ponto e vírgula",
        recebido_de=OrigemRecebimento.EX,
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    pendencias = excinfo.value.pendencias
    assert len(pendencias) == 1
    assert pendencias[0].campo == "historico"


def test_pendencia_codigo_de_rendimento_fora_das_tabelas(cenario):
    """`R01.002.001` (pensão alimentícia recebida) não tem leiaute
    confirmado nos seis arquivos-modelo (PE-71) — vira pendência, nunca
    uma linha adivinhada."""
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 7)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_recebida"],
        data=dia,
        valor="200.00",
        historico="Pensão recebida",
        recebido_de=OrigemRecebimento.PF,
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    pendencias = excinfo.value.pendencias
    assert len(pendencias) == 1
    assert pendencias[0].campo == "conta.codigo_carne_leao"
    assert "R01.002.001" in pendencias[0].motivo


def test_pendencia_imposto_pago_proprio_fora_do_escopo(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 8)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_imposto_pago"],
        data=dia,
        valor="150.00",
        historico="Imposto pago (carnê-leão) - fora do escopo",
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    pendencias = excinfo.value.pendencias
    assert len(pendencias) == 1
    assert pendencias[0].campo == "conta.codigo_carne_leao"
    assert "P20.01.00004" in pendencias[0].motivo


def test_pendencia_codigo_de_pagamento_fora_das_tabelas(cenario):
    empresa = cenario["empresa_a"]
    conta_desconhecida = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="D99",
        nome="Pagamento fora das tabelas",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.99.00099",
    )
    dia = date(2026, 9, 9)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=conta_desconhecida,
        data=dia,
        valor="50.00",
        historico="Pagamento de código não confirmado",
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    assert excinfo.value.pendencias[0].campo == "conta.codigo_carne_leao"


def test_pendencia_lista_mais_de_um_lancamento(cenario):
    """As pendências vêm TODAS de uma vez — o contador corrige tudo antes
    de tentar de novo, sem descobrir uma por vez."""
    empresa = cenario["empresa_a"]
    dia = date(2026, 9, 10)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_recebida"],
        data=dia,
        valor="10.00",
        historico="Pendência 1",
        recebido_de=OrigemRecebimento.PF,
    )
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_imposto_pago"],
        data=dia,
        valor="20.00",
        historico="Pendência 2",
    )
    with pytest.raises(GeracaoArquivoCarneLeaoBloqueada) as excinfo:
        gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=None)
    assert len(excinfo.value.pendencias) == 2


# ---------------------------------------------------------------------------
# 5. Período — dentro de um único ano-calendário.
# ---------------------------------------------------------------------------


def test_periodo_fora_de_um_ano_calendario_e_recusado(cenario):
    empresa = cenario["empresa_a"]
    with pytest.raises(PeriodoInvalidoParaArquivoCarneLeaoWeb):
        gerar_arquivos_carne_leao(
            empresa=empresa, inicio=date(2025, 12, 15), fim=date(2026, 1, 15), usuario=None
        )


def test_inicio_posterior_a_fim_e_recusado(cenario):
    empresa = cenario["empresa_a"]
    with pytest.raises(PeriodoInvalidoParaArquivoCarneLeaoWeb):
        gerar_arquivos_carne_leao(
            empresa=empresa, inicio=date(2026, 3, 10), fim=date(2026, 3, 1), usuario=None
        )


def test_periodo_do_ano_inteiro_e_aceito(cenario):
    """Segunda dúvida do plano — o Carnê-Leão Web não exige arquivo
    mensal (manual do sistema de referência, seção "Escrituração"/
    "Rendimentos"/"Pagamentos": listas "no ano selecionado", sem
    restrição de mês; "até 1000 linhas")."""
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=date(2026, 1, 5),
        valor="100.00",
        historico="Janeiro",
        recebido_de=OrigemRecebimento.EX,
    )
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        # RC-77: a data do LANÇAMENTO fica dentro de hoje + 30 dias — o
        # PERÍODO consultado, abaixo, pode ir até dezembro sem problema
        # (a restrição é só sobre a data do lançamento, não do relatório).
        data=date(2026, 9, 20),
        valor="200.00",
        historico="Setembro",
        recebido_de=OrigemRecebimento.EX,
    )
    rendimentos, _pagamentos, conferencia = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=date(2026, 1, 1), fim=date(2026, 12, 31), usuario=None
    )
    assert len(_linhas_geradas(rendimentos)) == 2
    assert conferencia["total_rendimentos"] == Decimal("300.00")


# ---------------------------------------------------------------------------
# 6. Conferência — totais por código batem com o Livro Caixa.
# ---------------------------------------------------------------------------


def test_conferencia_totais_por_codigo_e_comparacao_com_livro_caixa(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 10, 1)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="1000.00",
        historico="Receita 1",
        recebido_de=OrigemRecebimento.EX,
    )
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="500.00",
        historico="Receita 2",
        recebido_de=OrigemRecebimento.EX,
    )
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_despesa_dedutivel_padrao"],
        data=dia,
        valor="300.00",
        historico="Despesa 1",
    )
    _rendimentos, _pagamentos, conferencia = gerar_arquivos_carne_leao(
        empresa=empresa, inicio=dia, fim=dia, usuario=None
    )
    assert conferencia["totais_rendimentos_por_codigo"]["R01.001.001"] == Decimal("1500.00")
    assert conferencia["totais_pagamentos_por_codigo"]["P10.01.00001"] == Decimal("300.00")
    assert conferencia["total_entradas_livro_caixa"] == Decimal("1500.00")
    assert conferencia["total_saidas_livro_caixa"] == Decimal("300.00")
    assert conferencia["diferenca_rendimentos"] == Decimal("0.00")
    assert conferencia["diferenca_pagamentos"] == Decimal("0.00")


def test_isolamento_entre_empresas_do_mesmo_escritorio(cenario):
    """A2/M04 do resto da suíte deste módulo: isolamento entre empresas do
    MESMO escritório é o caso mais sutil (diferente de `empresa_id`
    incorreto na URL, aqui as duas empresas são igualmente "do escritório
    logado"). Uma segunda empresa CPF/livro-caixa, no MESMO escritório de
    `empresa_a`, com um lançamento de valor bem diferente — se o filtro por
    `empresa` vazar, o total apareceria na apuração da primeira."""
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["escritorio_a"],
        razao_social="Outra Pessoa Física — mesmo escritório",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="98765432100",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
        codigo_ocupacao=OCUPACAO_MEDICO,
    )
    outra_conta = ContaLivroCaixa.objects.create(
        empresa=outra_empresa,
        codigo="RT",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    dia = date(2026, 10, 3)
    criar_lancamento_caixa(
        empresa=outra_empresa,
        conta=outra_conta,
        data=dia,
        valor="999999.99",
        historico="Não pode vazar para a empresa A",
        recebido_de=OrigemRecebimento.EX,
    )
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="50.00",
        historico="Só da empresa A",
        recebido_de=OrigemRecebimento.EX,
    )

    rendimentos, _pagamentos, conferencia = gerar_arquivos_carne_leao(
        empresa=cenario["empresa_a"], inicio=dia, fim=dia, usuario=None
    )
    assert conferencia["total_rendimentos"] == Decimal("50.00")
    assert not any("999999,99" in linha for linha in _linhas_geradas(rendimentos))


# ---------------------------------------------------------------------------
# 7. Trilha de auditoria — período, linhas, totais; NUNCA o conteúdo.
# ---------------------------------------------------------------------------


def test_trilha_do_arquivo_gerado_nunca_expoe_conteudo(cenario):
    from apps.auditoria.models import RegistroAuditoria

    empresa = cenario["empresa_a"]
    dia = date(2026, 10, 5)
    usuario = _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-trilha-arquivo")
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="1000.00",
        historico="CPF SIGILOSO NÃO PODE APARECER NA TRILHA - 111.222.333-44",
        recebido_de=OrigemRecebimento.EX,
    )
    gerar_arquivos_carne_leao(empresa=empresa, inicio=dia, fim=dia, usuario=usuario)

    registro = RegistroAuditoria.objects.filter(acao="carne_leao_arquivo.gerado").latest("id")
    assert registro.detalhes["linhas_rendimentos"] == 1
    assert registro.detalhes["total_rendimentos"] == "1000.00"
    detalhes_texto = str(registro.detalhes)
    assert "111.222.333-44" not in detalhes_texto
    assert "SIGILOSO" not in detalhes_texto


# ---------------------------------------------------------------------------
# 8. Modelo — campos novos: sucesso, erro, limite.
# ---------------------------------------------------------------------------


def test_validar_codigo_ocupacao_formato_e_tabela():
    validar_codigo_ocupacao("225")  # não levanta
    with pytest.raises(ValidationError, match="3 dígitos"):
        validar_codigo_ocupacao("25")
    with pytest.raises(ValidationError, match="tabela oficial"):
        validar_codigo_ocupacao("999")


def test_empresa_codigo_ocupacao_so_para_cpf(cenario):
    # Instância NÃO salva (`Empresa(...)`, não `.objects.create()`) — testa
    # a camada 2 (`full_clean()`); a camada 1 (`CheckConstraint` de banco)
    # já tem cobertura própria no resto da suíte de CAEPF (mesmo padrão).
    empresa_cnpj = Empresa(
        escritorio=cenario["escritorio_a"],
        razao_social="Empresa CNPJ com ocupação inválida",
        cnpj="22233344000122",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
        codigo_ocupacao="225",
    )
    with pytest.raises(ValidationError):
        empresa_cnpj.full_clean()


def test_conta_codigo_ocupacao_so_em_trabalho_nao_assalariado_ou_notarial(cenario):
    conta_aluguel_com_ocupacao = cenario["conta_aluguel"]
    conta_aluguel_com_ocupacao.codigo_ocupacao = OCUPACAO_MEDICO
    with pytest.raises(ValidationError, match="trabalho não assalariado"):
        conta_aluguel_com_ocupacao.full_clean()


def test_conta_notarial_com_ocupacao_diferente_de_117_e_recusada(cenario):
    conta_notarial = cenario["conta_notarial"]
    conta_notarial.codigo_ocupacao = OCUPACAO_MEDICO
    with pytest.raises(ValidationError, match="117"):
        conta_notarial.full_clean()


def test_conta_notarial_com_ocupacao_117_e_aceita(cenario):
    conta_notarial = cenario["conta_notarial"]
    conta_notarial.codigo_ocupacao = "117"
    conta_notarial.full_clean()  # não levanta


def test_valor_irrf_recusado_fora_de_pj(cenario):
    from apps.livro_caixa.services import LancamentoCaixaInvalido

    with pytest.raises(LancamentoCaixaInvalido, match="pessoa jurídica"):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_trabalho"],
            data=date(2026, 3, 30),
            valor="100.00",
            historico="IRRF fora de PJ",
            recebido_de=OrigemRecebimento.PF,
            cpf_titular_pagamento=CPF_TITULAR,
            cpf_beneficiario_nao_informado=True,
            valor_irrf="10.00",
        )


def test_competencia_multa_juros_recusados_fora_da_previdencia_oficial(cenario):
    from apps.livro_caixa.services import LancamentoCaixaInvalido

    with pytest.raises(LancamentoCaixaInvalido, match="previdência oficial"):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_pensao_paga"],
            data=date(2026, 3, 31),
            valor="100.00",
            historico="Competência fora da previdência oficial",
            competencia_previdencia=date(2026, 3, 1),
        )


def test_competencia_multa_juros_recusados_em_receita(cenario):
    from apps.livro_caixa.services import LancamentoCaixaInvalido

    with pytest.raises(LancamentoCaixaInvalido, match="RECEITA"):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_trabalho"],
            data=date(2026, 3, 31),
            valor="100.00",
            historico="Competência em receita - inválido",
            recebido_de=OrigemRecebimento.EX,
            multa_previdencia="10.00",
        )


def test_estorno_copia_os_quatro_campos_novos(cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 10, 2)
    original = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_previdencia"],
        data=dia,
        valor="400.00",
        historico="Previdência a ser estornada",
        competencia_previdencia=date(2026, 10, 1),
        multa_previdencia="15.00",
        juros_previdencia="5.00",
    )
    estorno = estornar_lancamento_caixa(original)
    assert estorno.competencia_previdencia == date(2026, 10, 1)
    assert estorno.multa_previdencia == Decimal("15.00")
    assert estorno.juros_previdencia == Decimal("5.00")


def test_valor_irrf_negativo_e_recusado(cenario):
    from apps.livro_caixa.services import LancamentoCaixaInvalido

    with pytest.raises(LancamentoCaixaInvalido, match="negativo"):
        criar_lancamento_caixa(
            empresa=cenario["empresa_a"],
            conta=cenario["conta_trabalho"],
            data=date(2026, 3, 29),
            valor="100.00",
            historico="IRRF negativo",
            recebido_de=OrigemRecebimento.PJ,
            cnpj_pagador=CNPJ_PAGADOR,
            valor_irrf="-1.00",
        )


# ---------------------------------------------------------------------------
# 9. API — pendências/conferência (JSON) e download dos dois arquivos.
# ---------------------------------------------------------------------------


def _url_pendencias(empresa_id):
    return reverse("livro_caixa:carne-leao-arquivos-pendencias", kwargs={"empresa_id": empresa_id})


def _url_rendimentos(empresa_id):
    return reverse("livro_caixa:carne-leao-arquivo-rendimentos", kwargs={"empresa_id": empresa_id})


def _url_pagamentos(empresa_id):
    return reverse("livro_caixa:carne-leao-arquivo-pagamentos", kwargs={"empresa_id": empresa_id})


def test_api_pendencias_sem_pendencia_devolve_conferencia(client, cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 15)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="500.00",
        historico="Receita - teste API",
        recebido_de=OrigemRecebimento.EX,
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-conf")
    client.login(username="gestor-api-conf", password="senha-forte-123")

    resposta = client.get(
        _url_pendencias(empresa.id) + f"?inicio={dia.isoformat()}&fim={dia.isoformat()}"
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["pendencias"] == []
    assert corpo["gerar_disponivel"] is True
    assert corpo["conferencia"]["total_rendimentos"] == "500.00"


def test_api_pendencias_com_pendencia_nunca_gera_arquivo(client, cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 16)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_recebida"],
        data=dia,
        valor="10.00",
        historico="Sem tabela confirmada",
        recebido_de=OrigemRecebimento.PF,
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-pend")
    client.login(username="gestor-api-pend", password="senha-forte-123")

    resposta = client.get(
        _url_pendencias(empresa.id) + f"?inicio={dia.isoformat()}&fim={dia.isoformat()}"
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["gerar_disponivel"] is False
    assert len(corpo["pendencias"]) == 1
    assert "conferencia" not in corpo or corpo.get("conferencia") is None


def test_api_download_rendimentos_e_pagamentos(client, cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 17)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=dia,
        valor="700.00",
        historico="Receita - teste download",
        recebido_de=OrigemRecebimento.EX,
    )
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_despesa_dedutivel_padrao"],
        data=dia,
        valor="80.00",
        historico="Despesa - teste download",
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-download")
    client.login(username="gestor-api-download", password="senha-forte-123")
    qs = f"?inicio={dia.isoformat()}&fim={dia.isoformat()}"

    resposta_r = client.get(_url_rendimentos(empresa.id) + qs)
    assert resposta_r.status_code == 200
    assert resposta_r["Content-Disposition"].startswith("attachment;")
    assert "carne-leao-rendimentos-2026-03-a-2026-03.csv" in resposta_r["Content-Disposition"]
    assert b"700,00" in resposta_r.content
    assert resposta_r.content.decode("iso-8859-1")  # decodifica sem erro

    resposta_p = client.get(_url_pagamentos(empresa.id) + qs)
    assert resposta_p.status_code == 200
    assert "carne-leao-pagamentos-2026-03-a-2026-03.csv" in resposta_p["Content-Disposition"]
    assert b"80,00" in resposta_p.content


def test_api_download_com_pendencia_devolve_400_com_lista(client, cenario):
    empresa = cenario["empresa_a"]
    dia = date(2026, 3, 18)
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_recebida"],
        data=dia,
        valor="10.00",
        historico="Sem tabela",
        recebido_de=OrigemRecebimento.PF,
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-download-pend")
    client.login(username="gestor-api-download-pend", password="senha-forte-123")
    qs = f"?inicio={dia.isoformat()}&fim={dia.isoformat()}"

    resposta = client.get(_url_rendimentos(empresa.id) + qs)
    assert resposta.status_code == 400
    assert len(resposta.json()["pendencias"]) == 1


def test_api_periodo_fora_de_um_ano_e_400(client, cenario):
    empresa = cenario["empresa_a"]
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-periodo")
    client.login(username="gestor-api-periodo", password="senha-forte-123")
    resposta = client.get(_url_pendencias(empresa.id) + "?inicio=2025-12-01&fim=2026-01-31")
    assert resposta.status_code == 400


def test_api_isolamento_entre_escritorios(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-isolamento")
    client.login(username="gestor-api-isolamento", password="senha-forte-123")
    resposta = client.get(
        _url_pendencias(cenario["empresa_b"].id) + "?inicio=2026-01-01&fim=2026-01-31"
    )
    assert resposta.status_code == 404


def test_api_papel_paralegal_le_e_papel_cliente_nao(client, cenario):
    dia_qs = "?inicio=2026-01-01&fim=2026-01-31"
    empresa_id = cenario["empresa_a"].id

    _usuario_com_papel(Papel.PARALEGAL, cenario["escritorio_a"], "paralegal-api-carne")
    client.login(username="paralegal-api-carne", password="senha-forte-123")
    resposta_paralegal = client.get(_url_pendencias(empresa_id) + dia_qs)
    assert resposta_paralegal.status_code == 200
    client.logout()

    _usuario_com_papel(Papel.CLIENTE, cenario["escritorio_a"], "cliente-api-carne")
    client.login(username="cliente-api-carne", password="senha-forte-123")
    resposta_cliente = client.get(_url_pendencias(empresa_id) + dia_qs)
    assert resposta_cliente.status_code == 403


def test_api_recusa_empresa_em_modo_contabilidade(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-contab")
    client.login(username="gestor-api-contab", password="senha-forte-123")
    empresa_id = cenario["empresa_contabilidade"].id

    resposta = client.get(_url_pendencias(empresa_id) + "?inicio=2026-01-01&fim=2026-01-31")
    assert resposta.status_code == 400

    resposta_download = client.get(
        _url_rendimentos(empresa_id) + "?inicio=2026-01-01&fim=2026-01-31"
    )
    assert resposta_download.status_code == 400


def test_api_sem_login_e_401_ou_403_nunca_500(cenario):
    client = Client()
    resposta = client.get(
        _url_pendencias(cenario["empresa_a"].id) + "?inicio=2026-01-01&fim=2026-01-31"
    )
    assert resposta.status_code in (401, 403)


def test_api_querystring_malformada_nunca_500(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-api-malformada")
    client.login(username="gestor-api-malformada", password="senha-forte-123")
    empresa_id = cenario["empresa_a"].id

    for querystring in ("", "?inicio=abacate&fim=2026-01-31", "?inicio=2026-01-31"):
        resposta = client.get(_url_pendencias(empresa_id) + querystring)
        assert resposta.status_code == 400, querystring

    resposta_id_invalido = client.get(
        reverse("livro_caixa:carne-leao-arquivos-pendencias", kwargs={"empresa_id": 999999999})
        + "?inicio=2026-01-01&fim=2026-01-31"
    )
    assert resposta_id_invalido.status_code == 404
