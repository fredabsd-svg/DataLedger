"""DL-045, fatia 3 — a tela e o documento da DRE
(apps.contabilidade.views_web.dre), o campo "Linha da DRE" no formulário
de CRIAÇÃO de conta (`conta_nova`) e a tela de classificação da Linha da
DRE de conta EXISTENTE (`conta_classificacao_dre`, correção da rodada 1
de auditoria, achado A7).

Cobre os critérios do plano
(docs/planos/DL-045-demonstracao-do-resultado.md) que são da FRENTE DA
TELA: permissão verificada no servidor com o CORPO conferido, isolamento
entre escritórios, veto de emissão NOMEANDO o que falta — inclusive as
listas novas da correção A1/A2 (tipo divergente da linha; aninhada com
linha diferente/mesma linha) — (critério 6), identificação NBC TG 26 item
51 em toda página (critério 7), e o campo "Linha da DRE" nos dois
formulários de conta (criação e classificação de conta existente).

A decisão de SE PODE emitir e os NÚMEROS da apuração são do SERVIDOR
(`apps.contabilidade.services.apurar_dre`/`avaliar_emissao_da_dre`) e têm
suíte própria (test_dl045_dre.py, fatias 1 e 2). Este arquivo testa que a
TELA OBEDECE a essa decisão e APRESENTA os mesmos números corretamente —
não reconfere a aritmética em si.

Dados 100% sintéticos, criados nos próprios testes. Datas em 2026, sempre
no passado (hoje é 2026-09-26).
"""

import itertools
import re
from decimal import Decimal
from html.parser import HTMLParser

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import (
    ClassificacaoDre,
    Conta,
    NaturezaConta,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    criar_lancamento,
    estornar_lancamento,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA

_CONTADOR_DE_CNPJ = itertools.count(1)


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _conta(empresa, *, codigo, nome, tipo, natureza, pai=None, classificacao_dre=None):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_dre=classificacao_dre,
    )


def _lancar(empresa, data, historico, debito, credito, valor):
    criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel=Papel.GESTOR, username="gestor-dl045t"):
    _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_dre_completo():
    """Plano mínimo com as TREZE linhas do art. 187 ocupadas (HI-29), toda
    movimentação num único dia de MARÇO/2026 — exercício começa em
    01/01/2026 (HI-28) e nada mais acontece antes, então a coluna do MÊS e
    a do ACUMULADO batem exatamente com os mesmos números, o que simplifica
    a asserção sem perder cobertura das duas colunas (as duas aparecem no
    HTML, uma vez cada).

    Números escolhidos para cada linha e subtotal terem um valor PRÓPRIO,
    nenhum repetido — controle contra um subtotal que, por acidente,
    somasse a linha errada e ainda batesse por coincidência numérica:

    Receita bruta ............................ 10.000,00
    (-) Deduções da receita ..................... 1.000,00
        = Receita líquida ........................ 9.000,00
    (-) Custo .................................... 3.000,00
        = Lucro bruto ............................. 6.000,00
    (-) Despesas com vendas ........................ 500,00
    (-) Despesas gerais e administrativas .......... 800,00
    (+) Outras receitas ............................ 200,00
    (-) Outras despesas ............................ 100,00
    (-) Outras despesas operacionais ................ 50,00
        = Resultado antes do resultado financeiro  4.750,00
    (+) Receitas financeiras ....................... 300,00
    (-) Despesas financeiras ....................... 150,00
        = Resultado financeiro ..................... 150,00
        = Resultado antes dos tributos ........... 4.900,00
    (-) Provisão para IRPJ e CSLL ................... 400,00
    (-) Participações ............................... 100,00
        = Lucro líquido do período ............... 4.400,00
    """
    escritorio = Escritorio.objects.create(nome="Escritório DL-045t", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DRE Completa DL-045t Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa = _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    receita_bruta = _conta(
        empresa,
        codigo="3.1",
        nome="Receita Bruta",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.RECEITA_BRUTA,
    )
    deducoes = _conta(
        empresa,
        codigo="3.2",
        nome="Deduções da Receita",
        tipo=TipoConta.RECEITA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DEDUCOES_DA_RECEITA,
    )
    custo = _conta(
        empresa,
        codigo="4.1",
        nome="Custo dos Serviços",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.CUSTO,
    )
    despesas_vendas = _conta(
        empresa,
        codigo="4.2",
        nome="Despesas com Vendas",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DESPESAS_COM_VENDAS,
    )
    despesas_adm = _conta(
        empresa,
        codigo="4.3",
        nome="Despesas Gerais e Administrativas",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS,
    )
    outras_receitas = _conta(
        empresa,
        codigo="3.3",
        nome="Outras Receitas",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.OUTRAS_RECEITAS,
    )
    outras_despesas = _conta(
        empresa,
        codigo="4.4",
        nome="Outras Despesas",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.OUTRAS_DESPESAS,
    )
    outras_despesas_operacionais = _conta(
        empresa,
        codigo="4.5",
        nome="Outras Despesas Operacionais",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS,
    )
    receitas_financeiras = _conta(
        empresa,
        codigo="3.4",
        nome="Receitas Financeiras",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.RECEITAS_FINANCEIRAS,
    )
    despesas_financeiras = _conta(
        empresa,
        codigo="4.6",
        nome="Despesas Financeiras",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DESPESAS_FINANCEIRAS,
    )
    provisao = _conta(
        empresa,
        codigo="4.7",
        nome="Provisão para IRPJ e CSLL",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.PROVISAO_IRPJ_CSLL,
    )
    participacoes = _conta(
        empresa,
        codigo="4.8",
        nome="Participações",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.PARTICIPACOES,
    )

    data = timezone.datetime(2026, 3, 16).date()
    _lancar(empresa, data, "Receita bruta de serviços", caixa, receita_bruta, "10000.00")
    _lancar(empresa, data, "ISS sobre serviços (dedução)", deducoes, caixa, "1000.00")
    _lancar(empresa, data, "Custo dos serviços prestados", custo, caixa, "3000.00")
    _lancar(empresa, data, "Comissão de vendas", despesas_vendas, caixa, "500.00")
    _lancar(empresa, data, "Despesas administrativas", despesas_adm, caixa, "800.00")
    _lancar(empresa, data, "Receita de aluguel eventual", caixa, outras_receitas, "200.00")
    _lancar(empresa, data, "Baixa de bem obsoleto", outras_despesas, caixa, "100.00")
    _lancar(empresa, data, "Multa administrativa", outras_despesas_operacionais, caixa, "50.00")
    _lancar(
        empresa, data, "Rendimento de aplicação financeira", caixa, receitas_financeiras, "300.00"
    )
    _lancar(empresa, data, "Juros de empréstimo", despesas_financeiras, caixa, "150.00")
    _lancar(empresa, data, "Provisão de IRPJ/CSLL do período", provisao, caixa, "400.00")
    _lancar(empresa, data, "Participação de administradores", participacoes, caixa, "100.00")

    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "ano": 2026,
        "mes": 3,
    }


@pytest.fixture
def cenario_dre_pendente():
    """Conta de RECEITA analítica (folha, sem descendentes) com movimento
    no período e SEM linha da DRE — nem própria, nem herdada de um
    ancestral — dispara `contas_sem_classificacao_dre_com_movimento`
    (critério 6 do plano). Cenário mínimo."""
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-045t Pendente", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DRE Pendente DL-045t Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa = _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    receita = _conta(
        empresa, codigo="2", nome="Receita Não Classificada", tipo=TipoConta.RECEITA, natureza=C
    )
    data = timezone.datetime(2026, 3, 16).date()
    _lancar(empresa, data, "Venda à vista", caixa, receita, "777.00")
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "receita": receita,
        "ano": 2026,
        "mes": 3,
    }


# ---------------------------------------------------------------------------
# Permissão e isolamento (critérios 6 e 8 do plano)
# ---------------------------------------------------------------------------


def test_papel_sem_permissao_recebe_403_e_nenhum_valor_no_corpo(client, cenario_dre_completo):
    _autenticar(
        client, cenario_dre_completo["escritorio"], papel=Papel.CLIENTE, username="cliente-dl045t"
    )
    url = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()
    assert "Seu papel não permite" in conteudo
    for valor in ("10.000,00", "4.400,00", "9.000,00"):
        assert valor not in conteudo, valor
    assert cenario_dre_completo["empresa"].razao_social not in conteudo


def test_empresa_de_outro_escritorio_da_404_sem_confirmar_existencia(client, cenario_dre_completo):
    outro_escritorio = Escritorio.objects.create(
        nome="Outro Escritório DL-045t", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, outro_escritorio, username="gestor-outro-dl045t")
    url = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 404
    assert cenario_dre_completo["empresa"].razao_social not in resposta.content.decode()


# ---------------------------------------------------------------------------
# Estados: vazio, competência inválida
# ---------------------------------------------------------------------------


def test_estado_vazio_empresa_sem_plano_de_contas(client):
    escritorio = Escritorio.objects.create(nome="Escritório DL-045t Vazio", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Vazia DL-045t Ltda", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, escritorio, username="gestor-vazio-dl045t")
    resposta = client.get(reverse("contabilidade_web:dre", args=[empresa.id]))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "ainda não tem nenhuma conta cadastrada" in conteudo
    assert reverse("contabilidade_web:plano_de_contas", args=[empresa.id]) in conteudo
    assert "NÃO pode ser emitida" not in conteudo


def test_competencia_invalida_retorna_400_com_saida_navegavel(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    url = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    resposta = client.get(url + "?ano=abacaxi&mes=3")
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "não pôde ser usada" in conteudo
    assert reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id]) in conteudo


# ---------------------------------------------------------------------------
# Veto de emissão — critério 6: nomeando o que falta, sem montar a DRE
# ---------------------------------------------------------------------------


def test_veto_nomeia_a_conta_pendente_e_nao_monta_a_demonstracao(client, cenario_dre_pendente):
    _autenticar(client, cenario_dre_pendente["escritorio"])
    url = reverse("contabilidade_web:dre", args=[cenario_dre_pendente["empresa"].id])
    url_com_competencia = (
        f"{url}?ano={cenario_dre_pendente['ano']}&mes={cenario_dre_pendente['mes']}"
    )
    resposta = client.get(url_com_competencia)
    # 200: a tela respondeu corretamente "não pode emitir, e eis o
    # porquê" — não é falha de protocolo.
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "NÃO pode ser emitida" in conteudo
    # A conta pendente é NOMEADA — código e nome.
    assert "Receita Não Classificada" in conteudo
    assert cenario_dre_pendente["receita"].codigo in conteudo
    # Caminho de correção: link para o Plano de contas — mesmo desenho do
    # veto do Balanço (a tela de edição de conta ainda não existe; ver a
    # nota do módulo).
    assert (
        reverse("contabilidade_web:plano_de_contas", args=[cenario_dre_pendente["empresa"].id])
        in conteudo
    )
    # A demonstração NÃO existe nesta resposta enquanto houver pendência.
    assert "Lucro (prejuízo) líquido do período" not in conteudo
    assert "<table" not in conteudo


def test_controle_positivo_base_completa_exige_emissao(client, cenario_dre_completo):
    """Controle positivo do critério 6: uma base COMPLETA (sem pendência
    nenhuma) EXIGE a emissão — não basta a ausência de recusa."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    url = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    url_com_competencia = (
        f"{url}?ano={cenario_dre_completo['ano']}&mes={cenario_dre_completo['mes']}"
    )
    resposta = client.get(url_com_competencia)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "NÃO pode ser emitida" not in conteudo
    assert "DRE pronta para emissão" in conteudo
    assert "<table" in conteudo


# ---------------------------------------------------------------------------
# Emissão — os números batem com o serviço (mesmo cenário, as DUAS colunas)
# ---------------------------------------------------------------------------


def test_todas_as_linhas_e_subtotais_do_art_187_com_os_valores_certos(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    url = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    url_com_competencia = (
        f"{url}?ano={cenario_dre_completo['ano']}&mes={cenario_dre_completo['mes']}"
    )
    conteudo = client.get(url_com_competencia).content.decode()

    # Treze linhas do art. 187, cada uma com um valor PRÓPRIO (nenhum
    # repetido — controle contra soma na linha errada). O mês e o
    # acumulado do exercício batem exatamente (fixture: tudo aconteceu no
    # mesmo mês, primeiro do exercício), então CADA valor aparece DUAS
    # vezes no HTML (coluna Mês e coluna Acumulado).
    valores_esperados_duas_vezes = (
        "10.000,00",  # Receita bruta
        "1.000,00",  # Deduções da receita
        "9.000,00",  # Receita líquida
        "3.000,00",  # Custo
        "6.000,00",  # Lucro bruto
        "500,00",  # Despesas com vendas
        "800,00",  # Despesas gerais e administrativas
        "200,00",  # Outras receitas
        "100,00",  # Outras despesas (e Participações, mesmo valor — ok)
        "50,00",  # Outras despesas operacionais
        "4.750,00",  # Resultado antes do resultado financeiro
        "300,00",  # Receitas financeiras
        "150,00",  # Despesas financeiras
        "4.900,00",  # Resultado antes dos tributos
        "400,00",  # Provisão IRPJ/CSLL
        "4.400,00",  # Lucro líquido do período
    )
    for valor in valores_esperados_duas_vezes:
        assert conteudo.count(valor) >= 2, (valor, conteudo.count(valor))

    # Títulos das treze linhas e dos seis subtotais.
    for titulo in (
        "Receita bruta de vendas e serviços",
        "Deduções da receita",
        "Receita líquida",
        "Custo",
        "Resultado bruto",  # F1 (reconferência DL-045): rótulo do art. 187, VII
        "Despesas com vendas",
        "Despesas gerais e administrativas",
        "Outras receitas",
        "Outras despesas",
        "Outras despesas operacionais",
        "Resultado antes do resultado financeiro",
        "Receitas financeiras",
        "Despesas financeiras",
        "Resultado financeiro",
        "Resultado antes dos tributos sobre o lucro",
        "Provisão para IRPJ e CSLL",
        "Participações",
        "Lucro (prejuízo) líquido do período",  # F1: ITG 1000 anexo 3 / art. 187, VII
    ):
        assert titulo in conteudo, titulo


def test_bloco_de_identificacao_do_item_51_no_html(client, cenario_dre_completo):
    """Os campos do item 51 aparecem no corpo do documento: nome da
    entidade e inscrição (a), individual/grupo (b), período coberto (c),
    moeda (d) e nível de arredondamento (e). A repetição em TODA página
    impressa (item 52) é medida no navegador real
    (scripts/medir_identificacao_do_emitente.py); este teste cobre só a
    PRESENÇA do conteúdo no HTML servido."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    url_com_competencia = (
        f"{url}?ano={cenario_dre_completo['ano']}&mes={cenario_dre_completo['mes']}"
    )
    conteudo = client.get(url_com_competencia).content.decode()

    assert 'class="identificacao-do-documento"' in conteudo
    assert empresa.razao_social in conteudo
    assert empresa.cnpj[0:2] in conteudo  # o CNPJ mascarado contém o original
    assert "Individual" in conteudo
    assert "Março" in conteudo
    assert "2026" in conteudo
    assert "Real (R$)" in conteudo
    assert "unidade de real, com centavos" in conteudo.lower()


def test_navegacao_de_competencia_desloca_um_mes(client, cenario_dre_completo):
    """ "‹ Março de 2026 ›": os links de navegação levam para fevereiro e
    abril do MESMO ano, sem trocar de rota."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    url = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    conteudo = client.get(f"{url}?ano=2026&mes=3").content.decode()
    assert "ano=2026&amp;mes=2" in conteudo or "ano=2026&mes=2" in conteudo
    assert "ano=2026&amp;mes=4" in conteudo or "ano=2026&mes=4" in conteudo


def test_navegacao_de_competencia_rola_o_ano_em_janeiro_e_dezembro(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    url = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    conteudo_janeiro = client.get(f"{url}?ano=2026&mes=1").content.decode()
    assert "ano=2025&amp;mes=12" in conteudo_janeiro or "ano=2025&mes=12" in conteudo_janeiro
    conteudo_dezembro = client.get(f"{url}?ano=2026&mes=12").content.decode()
    assert "ano=2027&amp;mes=1" in conteudo_dezembro or "ano=2027&mes=1" in conteudo_dezembro


def test_nenhuma_tela_da_dre_usa_javascript(client, cenario_dre_completo, cenario_dre_pendente):
    _autenticar(client, cenario_dre_completo["escritorio"], username="gestor-js-1-dl045t")
    url_completa = reverse("contabilidade_web:dre", args=[cenario_dre_completo["empresa"].id])
    assert "<script" not in client.get(url_completa).content.decode().lower()

    _autenticar(client, cenario_dre_pendente["escritorio"], username="gestor-js-2-dl045t")
    url_pendente = reverse("contabilidade_web:dre", args=[cenario_dre_pendente["empresa"].id])
    assert "<script" not in client.get(url_pendente).content.decode().lower()


# ---------------------------------------------------------------------------
# Recepção pelo hub de Relatórios e pelo submenu lateral
# ---------------------------------------------------------------------------


def test_dre_aparece_no_hub_de_relatorios(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    conteudo = client.get(
        reverse("contabilidade_web:relatorios", args=[empresa.id])
    ).content.decode()
    assert reverse("contabilidade_web:dre", args=[empresa.id]) in conteudo
    assert "DRE" in conteudo


def test_dre_aparece_no_submenu_lateral_de_relatorios(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    # Qualquer tela autenticada carrega a barra lateral — usa o próprio
    # painel de fechamento, sem relação com a DRE, só para inspecionar o
    # menu renderizado.
    conteudo = client.get(
        reverse("contabilidade_web:fechamento", args=[empresa.id])
    ).content.decode()
    assert reverse("contabilidade_web:dre", args=[empresa.id]) in conteudo


# ---------------------------------------------------------------------------
# Formulário de conta — campo "Linha da DRE" (critério 4 do plano)
# ---------------------------------------------------------------------------


def test_formulario_de_nova_conta_mostra_o_campo_linha_da_dre(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    conteudo = client.get(
        reverse("contabilidade_web:conta_nova", args=[empresa.id])
    ).content.decode()
    assert "Linha da DRE" in conteudo
    # As treze opções do enum aparecem como <option> do <select>.
    assert "Receita bruta de vendas e serviços" in conteudo
    assert "Lucro líquido" not in conteudo  # não é uma linha da DRE, é um subtotal


def test_criar_conta_com_linha_da_dre_pelo_formulario(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    resposta = client.post(
        reverse("contabilidade_web:conta_nova", args=[empresa.id]),
        data={
            "codigo": "9",
            "nome": "Nova Receita",
            "tipo": TipoConta.RECEITA,
            "natureza": C,
            "conta_pai": "",
            "aceita_lancamento": "on",
            "classificacao_dre": ClassificacaoDre.RECEITA_BRUTA,
        },
    )
    assert resposta.status_code == 302
    conta = Conta.objects.get(empresa=empresa, codigo="9")
    assert conta.classificacao_dre == ClassificacaoDre.RECEITA_BRUTA


def test_plano_de_contas_mostra_a_linha_da_dre_cadastrada(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    conteudo = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    ).content.decode()
    assert "Linha da DRE" in conteudo
    assert "Receita bruta de vendas e serviços" in conteudo


def test_plano_de_contas_mostra_o_botao_linha_da_dre_so_para_conta_de_resultado(
    client, cenario_dre_completo
):
    """DL-045/A7: o botão "Linha da DRE" só aparece para conta de RECEITA
    ou DESPESA (a única classificação que a Lei 6.404/76, art. 187,
    aceita) — nunca para uma conta patrimonial, que o servidor sempre
    recusaria."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    resposta = client.get(reverse("contabilidade_web:plano_de_contas", args=[empresa.id]))
    conteudo = resposta.content.decode()
    receita_bruta = Conta.objects.get(empresa=empresa, codigo="3.1")
    caixa = Conta.objects.get(empresa=empresa, codigo="1")
    assert (
        reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita_bruta.id])
        in conteudo
    )
    assert (
        reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, caixa.id])
        not in conteudo
    )


# ---------------------------------------------------------------------------
# Tela "conta_classificacao_dre" — DL-045, correção da rodada 1 de
# auditoria (A7): classificar (ou reclassificar, ou remover) a Linha da
# DRE de uma conta EXISTENTE.
# ---------------------------------------------------------------------------


def test_conta_classificacao_dre_papel_sem_permissao_recebe_403(client, cenario_dre_completo):
    _autenticar(
        client, cenario_dre_completo["escritorio"], papel=Papel.CLIENTE, username="cliente-a7"
    )
    empresa = cenario_dre_completo["empresa"]
    receita_bruta = Conta.objects.get(empresa=empresa, codigo="3.1")
    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita_bruta.id])
    resposta = client.get(url)
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()
    assert "Seu papel não permite" in conteudo
    assert receita_bruta.nome not in conteudo


def test_conta_classificacao_dre_empresa_de_outro_escritorio_da_404(client, cenario_dre_completo):
    outro_escritorio = Escritorio.objects.create(
        nome="Outro Escritório DL-045t A7", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, outro_escritorio, username="gestor-outro-a7")
    empresa = cenario_dre_completo["empresa"]
    receita_bruta = Conta.objects.get(empresa=empresa, codigo="3.1")
    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita_bruta.id])
    resposta = client.get(url)
    assert resposta.status_code == 404
    assert receita_bruta.nome not in resposta.content.decode()


def test_conta_classificacao_dre_conta_de_outra_empresa_da_404(client, cenario_dre_completo):
    """Isolamento POR CONTA, não só por empresa: uma conta de outra
    empresa do MESMO escritório também dá 404 — `empresa=empresa` no
    filtro, nunca `Conta.objects.get(pk=...)` cru."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    outra_empresa = Empresa.objects.create(
        escritorio=cenario_dre_completo["escritorio"],
        razao_social="Outra Empresa DL-045t A7 Ltda",
        cnpj=_cnpj_sintetico(),
    )
    conta_de_outra_empresa = _conta(
        outra_empresa, codigo="1", nome="Caixa de Outra Empresa", tipo=TipoConta.ATIVO, natureza=D
    )
    url = reverse(
        "contabilidade_web:conta_classificacao_dre",
        args=[cenario_dre_completo["empresa"].id, conta_de_outra_empresa.id],
    )
    resposta = client.get(url)
    assert resposta.status_code == 404


def test_conta_classificacao_dre_get_mostra_a_linha_atual_e_o_select(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    receita_bruta = Conta.objects.get(empresa=empresa, codigo="3.1")
    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita_bruta.id])
    conteudo = client.get(url).content.decode()
    assert receita_bruta.codigo in conteudo
    assert receita_bruta.nome in conteudo
    assert "Linha da DRE" in conteudo
    assert "Receita bruta de vendas e serviços" in conteudo
    assert "Sem classificação" in conteudo


def test_conta_classificacao_dre_post_classifica_conta_sem_classificacao(
    client, cenario_dre_pendente
):
    """A conta SEM linha da DRE do cenário de veto — a mesma que o link do
    veto aponta — pode ser classificada por esta tela, exatamente o
    caminho de correção que o veto promete."""
    _autenticar(client, cenario_dre_pendente["escritorio"])
    empresa = cenario_dre_pendente["empresa"]
    receita = cenario_dre_pendente["receita"]

    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita.id])
    resposta = client.post(url, data={"classificacao_dre": ClassificacaoDre.RECEITA_BRUTA})
    assert resposta.status_code == 302
    receita.refresh_from_db()
    assert receita.classificacao_dre == ClassificacaoDre.RECEITA_BRUTA

    # E a DRE, consultada de novo na MESMA competência, deixa de vetar.
    url_dre = reverse("contabilidade_web:dre", args=[empresa.id])
    conteudo_dre = client.get(
        f"{url_dre}?ano={cenario_dre_pendente['ano']}&mes={cenario_dre_pendente['mes']}"
    ).content.decode()
    assert "NÃO pode ser emitida" not in conteudo_dre
    assert "DRE pronta para emissão" in conteudo_dre


def test_conta_classificacao_dre_post_sem_classificacao_grava_none(client, cenario_dre_completo):
    """Achado A4: escolher "Sem classificação" (opção vazia do select)
    grava `None`, nunca `""` — verificado no BANCO, não só no formulário.
    Conta NOVA, sem nenhum lançamento — a guarda de TRANSIÇÃO só recusa
    quando HÁ movimento (ver o teste da guarda, logo abaixo); aqui o
    interesse é só a normalização "" -> None."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    conta_sem_movimento = _conta(
        empresa,
        codigo="3.9",
        nome="Receita Sem Movimento",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.OUTRAS_RECEITAS,
    )

    url = reverse(
        "contabilidade_web:conta_classificacao_dre", args=[empresa.id, conta_sem_movimento.id]
    )
    resposta = client.post(url, data={"classificacao_dre": ""})
    assert resposta.status_code == 302
    conta_sem_movimento.refresh_from_db()
    assert conta_sem_movimento.classificacao_dre is None


def test_conta_classificacao_dre_recusa_tipo_incompativel_mostra_valor_realmente_gravado(
    client, cenario_dre_completo
):
    """R6 (reconferência DL-045): a guarda usada aqui é a de TIPO
    incompatível (`TIPOS_ACEITOS_DA_CLASSIFICACAO_DRE`, models.py) — a
    ÚNICA guarda de `Conta.clean()` que sobrevive à DE-086 (a guarda de
    TRANSIÇÃO por movimento foi revista pelo arquiteto na mesma
    reconferência: reclassificar conta com movimento deixou de ser
    recusado, então este teste não usa mais aquele cenário). "Caixa" é
    ATIVO — nenhuma linha de resultado aceita conta patrimonial (Lei
    6.404/76, art. 187).

    A recusa aparece na TELA como `form.non_field_errors()`, nunca 500
    nem gravação silenciosa — e o achado R6 propriamente: `classificar_
    conta_na_dre` (services.py) muta `conta.classificacao_dre` no objeto
    Python ANTES de `full_clean()` recusar; sem `conta.refresh_from_db()`
    na view, "Linha atual" mostraria o valor RECUSADO ("Receita bruta de
    vendas e serviços") como se tivesse sido gravado. Este teste prova
    que a tela mostra o valor REALMENTE gravado ("Sem classificação")."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    caixa = Conta.objects.get(empresa=empresa, codigo="1")
    assert caixa.classificacao_dre is None

    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, caixa.id])
    resposta = client.post(url, data={"classificacao_dre": ClassificacaoDre.RECEITA_BRUTA})
    assert resposta.status_code == 200  # re-renderiza o formulário, não redireciona
    conteudo = resposta.content.decode()
    assert "não é compatível com o tipo desta conta" in conteudo

    # R6: "Linha atual" mostra o valor REALMENTE gravado (None -> "Sem
    # classificação"), nunca o valor recusado como se fosse o atual.
    assert "Linha atual: <strong>Sem classificação</strong>" in conteudo
    assert "Linha atual: <strong>Receita bruta de vendas e serviços</strong>" not in conteudo
    caixa.refresh_from_db()
    assert caixa.classificacao_dre is None  # nada mudou no banco


def test_conta_classificacao_dre_dado_nao_contratado_recusa_400(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    receita_bruta = Conta.objects.get(empresa=empresa, codigo="3.1")
    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita_bruta.id])
    resposta = client.post(
        url, data={"classificacao_dre": ClassificacaoDre.RECEITA_BRUTA, "campo_extra": "1"}
    )
    assert resposta.status_code == 400
    receita_bruta.refresh_from_db()
    assert receita_bruta.classificacao_dre == ClassificacaoDre.RECEITA_BRUTA  # nada mudou


# ---------------------------------------------------------------------------
# Listas novas do veto — DL-045, correção da rodada 1 de auditoria
# (A1/A2, DE-085): tipo divergente da linha, aninhada com linha
# diferente/mesma linha.
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_dre_tipo_divergente():
    """Conta PATRIMONIAL (Ativo) classificada, DIRETO no banco (bypassa
    `Conta.clean()`, o mesmo caminho que o auditor mediu — a guarda só
    roda em `full_clean()`), sob uma linha de RESULTADO — dispara
    `contas_com_tipo_divergente_da_linha` (A2, veta)."""
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-045t Tipo Divergente", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DRE Tipo Divergente DL-045t Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa = _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    # Gravada DIRETO com `.objects.create()` — `ContaCriarForm`/`Conta.
    # clean()` nunca deixariam isto passar; é exatamente o estado que a
    # guarda existe para acusar (dado torto gravado por fora, admin ou
    # migração antiga).
    ativo_sob_linha_de_resultado = Conta.objects.create(
        empresa=empresa,
        codigo="1.9",
        nome="Ativo Classificado Torto",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao_dre=ClassificacaoDre.RECEITA_BRUTA,
    )
    data = timezone.datetime(2026, 3, 16).date()
    _lancar(
        empresa, data, "Movimento no ativo torto", ativo_sob_linha_de_resultado, caixa, "900.00"
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "conta_torta": ativo_sob_linha_de_resultado,
        "ano": 2026,
        "mes": 3,
    }


def test_veto_lista_conta_com_tipo_divergente_da_linha(client, cenario_dre_tipo_divergente):
    """R8 (reconferência DL-045): a conta pendente é PATRIMONIAL (Ativo)
    sob uma linha de RESULTADO — nenhuma linha da DRE aceita conta
    patrimonial (Lei 6.404/76, art. 187), então o link "classificar esta
    conta" (que levaria a uma recusa garantida) NÃO aparece; a orientação
    é mover a conta para o grupo patrimonial correto no plano de contas."""
    _autenticar(client, cenario_dre_tipo_divergente["escritorio"])
    empresa = cenario_dre_tipo_divergente["empresa"]
    conta_torta = cenario_dre_tipo_divergente["conta_torta"]
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    conteudo = client.get(
        f"{url}?ano={cenario_dre_tipo_divergente['ano']}&mes={cenario_dre_tipo_divergente['mes']}"
    ).content.decode()
    assert "NÃO pode ser emitida" in conteudo
    assert conta_torta.nome in conteudo
    assert conta_torta.codigo in conteudo
    # SEM link: a conta é patrimonial, nenhuma linha da DRE a aceitaria.
    assert (
        reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, conta_torta.id])
        not in conteudo
    )
    assert "mover a conta para o grupo patrimonial correto no plano de contas" in conteudo


def test_veto_lista_conta_com_tipo_divergente_mostra_link_para_paralegal_como_texto_sem_link(
    client, cenario_dre_tipo_divergente
):
    """Controle negativo do teste acima: mesmo papel com permissão de
    escrita (GESTOR), a MESMA pendência nunca aparece com link, porque o
    critério que a esconde é o TIPO da conta (patrimonial), não a
    permissão — R8 tem DOIS filtros independentes (`pode_escriturar` E
    `linha.tipo`), este teste isola o segundo."""
    _autenticar(client, cenario_dre_tipo_divergente["escritorio"], username="gestor-r8-tipo")
    empresa = cenario_dre_tipo_divergente["empresa"]
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    conteudo = client.get(
        f"{url}?ano={cenario_dre_tipo_divergente['ano']}&mes={cenario_dre_tipo_divergente['mes']}"
    ).content.decode()
    assert "classificar esta conta" not in conteudo
    assert "mover a conta para o grupo patrimonial correto no plano de contas" in conteudo


@pytest.fixture
def cenario_dre_aninhada():
    """Ancestral e conta-folha, os DOIS com linha da DRE própria — a
    LINHA DIFERENTE dispara `..._linha_diferente` (veta); a MESMA linha
    dispara `..._mesma_linha` (só avisa). Duas empresas separadas, uma
    para cada caso, para não misturar veredito na mesma DRE."""
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-045t Aninhada", cnpj=_cnpj_sintetico()
    )

    empresa_diferente = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DRE Aninhada Diferente DL-045t Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa_1 = _conta(empresa_diferente, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    ancestral_1 = _conta(
        empresa_diferente,
        codigo="3",
        nome="Receitas (ancestral)",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.RECEITA_BRUTA,
    )
    filha_linha_diferente = _conta(
        empresa_diferente,
        codigo="3.1",
        nome="Receita Financeira Classificada Na Filha",
        tipo=TipoConta.RECEITA,
        natureza=C,
        pai=ancestral_1,
        classificacao_dre=ClassificacaoDre.RECEITAS_FINANCEIRAS,
    )
    data = timezone.datetime(2026, 3, 16).date()
    _lancar(
        empresa_diferente,
        data,
        "Movimento na filha aninhada",
        caixa_1,
        filha_linha_diferente,
        "300.00",
    )

    empresa_mesma = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DRE Aninhada Mesma Linha DL-045t Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa_2 = _conta(empresa_mesma, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    ancestral_2 = _conta(
        empresa_mesma,
        codigo="3",
        nome="Receitas (ancestral)",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.RECEITA_BRUTA,
    )
    filha_mesma_linha = _conta(
        empresa_mesma,
        codigo="3.1",
        nome="Receita Bruta Redundante Na Filha",
        tipo=TipoConta.RECEITA,
        natureza=C,
        pai=ancestral_2,
        classificacao_dre=ClassificacaoDre.RECEITA_BRUTA,
    )
    _lancar(
        empresa_mesma, data, "Movimento na filha aninhada", caixa_2, filha_mesma_linha, "300.00"
    )

    return {
        "escritorio": escritorio,
        "empresa_diferente": empresa_diferente,
        "filha_linha_diferente": filha_linha_diferente,
        "empresa_mesma": empresa_mesma,
        "filha_mesma_linha": filha_mesma_linha,
        "ano": 2026,
        "mes": 3,
    }


def test_veto_lista_aninhada_com_linha_diferente(client, cenario_dre_aninhada):
    _autenticar(client, cenario_dre_aninhada["escritorio"])
    empresa = cenario_dre_aninhada["empresa_diferente"]
    filha = cenario_dre_aninhada["filha_linha_diferente"]
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    conteudo = client.get(
        f"{url}?ano={cenario_dre_aninhada['ano']}&mes={cenario_dre_aninhada['mes']}"
    ).content.decode()
    assert "NÃO pode ser emitida" in conteudo
    assert filha.nome in conteudo
    assert (
        reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, filha.id])
        in conteudo
    )


def test_aviso_lista_aninhada_com_mesma_linha_nao_bloqueia(client, cenario_dre_aninhada):
    """Controle: a MESMA topologia, mas com a MESMA linha nas duas contas,
    nunca bloqueia — a demonstração emite normalmente, com o aviso
    presente."""
    _autenticar(client, cenario_dre_aninhada["escritorio"])
    empresa = cenario_dre_aninhada["empresa_mesma"]
    filha = cenario_dre_aninhada["filha_mesma_linha"]
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    conteudo = client.get(
        f"{url}?ano={cenario_dre_aninhada['ano']}&mes={cenario_dre_aninhada['mes']}"
    ).content.decode()
    assert "NÃO pode ser emitida" not in conteudo
    assert "DRE pronta para emissão" in conteudo
    assert "Aviso:" in conteudo
    assert filha.nome in conteudo


# ---------------------------------------------------------------------------
# Lista informativa "estornos_de_zeramento_na_coluna" — DL-045, correção
# da rodada 1 de auditoria (A3/A4, DE-085 item 4). Forma de item DIFERENTE
# das demais (lançamento, não conta) — cobre o ramo `tipo_linha ==
# "lancamento"` do template, sem cair no humanizador genérico de conta.
# ---------------------------------------------------------------------------


def test_aviso_lista_de_estornos_de_zeramento_na_coluna(client):
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-045t Estorno", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DRE Estorno DL-045t Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa = _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    receita_bruta = _conta(
        empresa,
        codigo="3.1",
        nome="Receita Bruta",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.RECEITA_BRUTA,
    )
    resultado = _conta(
        empresa,
        codigo="9",
        nome="Resultado do Exercício",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )
    lucros = _conta(
        empresa,
        codigo="9.1",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )
    prejuizos = _conta(
        empresa,
        codigo="9.2",
        nome="(-) Prejuízos Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=D,
    )
    usuario = _usuario_com_papel(Papel.GESTOR, escritorio, "gestor-estorno-dl045t")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=resultado,
        conta_lucros_acumulados=lucros,
        conta_prejuizos_acumulados=prejuizos,
        vigencia_inicio=timezone.datetime(2020, 1, 1).date(),
        usuario=usuario,
    )

    _lancar(
        empresa,
        timezone.datetime(2026, 1, 15).date(),
        "Receita de janeiro",
        caixa,
        receita_bruta,
        "1000.00",
    )
    zeramento_janeiro = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=usuario)
    for lancamento_zeramento in filter(
        None,
        [zeramento_janeiro.get("lancamento_etapa2")]
        + list(zeramento_janeiro.get("lancamentos_etapa1") or []),
    ):
        estornar_lancamento(lancamento_zeramento, data=timezone.datetime(2026, 2, 10).date())
    _lancar(
        empresa,
        timezone.datetime(2026, 2, 20).date(),
        "Receita legítima de fevereiro",
        caixa,
        receita_bruta,
        "200.00",
    )

    _autenticar(client, escritorio)
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    conteudo = client.get(f"{url}?ano=2026&mes=2").content.decode()

    assert "DRE pronta para emissão" in conteudo
    assert "Aviso:" in conteudo
    assert "estorno" in conteudo.lower()
    assert "10/02/2026" in conteudo
    # A conta "Resultado do Exercício" acumulada bate com a variação real
    # do PL (1.200,00), não com o dobro por causa do estorno reprocessado
    # — mesma conferência do teste do serviço (test_dl045_dre.py).
    assert "1.200,00" in conteudo


# ---------------------------------------------------------------------------
# R5 (reconferência DL-045): a navegação de competência ("‹ Mês anterior /
# Março de 2026 / Mês seguinte ›") é controle de TELA, nunca conteúdo do
# documento — precisa ficar FORA do papel. A ocultação em si é CSS
# (`@media print`, static/css/base.css) — nenhum HTML servido carrega CSS
# aplicado (o teste de tela nunca prova o que o navegador faz com a
# folha de estilo, ver o docstring de test_bl282_timbre_de_impressao.py).
# Este teste cobre o que É verificável SEM navegador: a REGRA existe, no
# ARQUIVO certo, para o seletor certo, com o efeito certo — uma varredura
# estrutural do CSS-fonte, no molde do detector de
# test_dl024_varredura_de_interface.py. A ocultação de FATO (medida no
# navegador real) foi verificada à parte, na bancada, com Playwright
# contra o servidor de desenvolvimento — ver o retorno desta rodada.
# ---------------------------------------------------------------------------


def _bloco_de_nivel_superior(texto, abertura):
    """Extrai o CORPO de um bloco `abertura { ... }` de nível superior
    (ex.: `"@media print {"`), por CONTAGEM DE CHAVES — não um `re`
    não-guloso (`.*?\\}`), que pararia na PRIMEIRA `}` interna (a regra
    de dentro do `@media`), nunca na que fecha o bloco inteiro."""
    inicio = texto.index(abertura)
    posicao_da_chave = texto.index("{", inicio)
    profundidade = 0
    for indice in range(posicao_da_chave, len(texto)):
        if texto[indice] == "{":
            profundidade += 1
        elif texto[indice] == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[posicao_da_chave + 1 : indice]
    raise AssertionError(f"bloco {abertura!r} nunca fechou — chaves desbalanceadas")


def test_r5_navegacao_de_competencia_esta_oculta_no_media_print():
    css = (settings.BASE_DIR / "static" / "css" / "base.css").read_text(encoding="utf-8")
    bloco_impressao = _bloco_de_nivel_superior(css, "@media print {")

    # A regra é extraída DENTRO do bloco de impressão (nunca em outro
    # `@media`, nem em comentário) — mesma extração regra-por-regra que
    # test_dl024 já usa para o detector de medida/cor.
    padrao_regra = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
    regra_da_navegacao = None
    for seletores, corpo in padrao_regra.findall(bloco_impressao):
        if ".navegacao-competencia" in seletores:
            regra_da_navegacao = (seletores, corpo)
            break

    assert regra_da_navegacao is not None, (
        "`.navegacao-competencia` não apareceu em nenhuma regra do @media print "
        "de static/css/base.css"
    )
    _, corpo = regra_da_navegacao
    assert "display: none" in corpo, (
        f"`.navegacao-competencia` está no @media print, mas a regra não esconde "
        f"o elemento: {corpo!r}"
    )


# ---------------------------------------------------------------------------
# R10 (reconferência DL-045): o link de navegação ("‹ Mês anterior"/"Mês
# seguinte ›") só aparece quando a competência ADJACENTE está dentro da
# faixa válida (`_ANO_MINIMO_COMPETENCIA`=1970, `_ANO_MAXIMO_COMPETENCIA`=
# 2999) — antes, o link era sempre montado e podia levar a um 400 (a
# versão anterior nunca testava a borda antes de gerar o `href`).
# ---------------------------------------------------------------------------


def test_r10_sem_link_de_mes_anterior_na_borda_inferior_da_faixa_de_competencia(client):
    escritorio = Escritorio.objects.create(nome="Escritório DL-045t R10a", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa R10a DL-045t Ltda", cnpj=_cnpj_sintetico()
    )
    _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    _autenticar(client, escritorio, username="gestor-r10a")
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    # Janeiro/1970: o mês ANTERIOR (dezembro/1969) está fora da faixa —
    # sem link. O mês seguinte (fevereiro/1970) está dentro — com link.
    conteudo = client.get(f"{url}?ano=1970&mes=1").content.decode()
    assert "ano=1969" not in conteudo
    assert "Mês anterior" not in conteudo
    assert "ano=1970&amp;mes=2" in conteudo or "ano=1970&mes=2" in conteudo


def test_r10_sem_link_de_mes_seguinte_na_borda_superior_da_faixa_de_competencia(client):
    escritorio = Escritorio.objects.create(nome="Escritório DL-045t R10b", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa R10b DL-045t Ltda", cnpj=_cnpj_sintetico()
    )
    _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    _autenticar(client, escritorio, username="gestor-r10b")
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    # Dezembro/2999: o mês SEGUINTE (janeiro/3000) está fora da faixa —
    # sem link. O mês anterior (novembro/2999) está dentro — com link.
    conteudo = client.get(f"{url}?ano=2999&mes=12").content.decode()
    assert "ano=3000" not in conteudo
    assert "Mês seguinte" not in conteudo
    assert "ano=2999&amp;mes=11" in conteudo or "ano=2999&mes=11" in conteudo


# ---------------------------------------------------------------------------
# T06 (reconferência DL-045): PARALEGAL lê a contabilidade
# (`PAPEIS_QUE_LEEM_CONTABILIDADE`, apps/contabilidade/permissoes.py), mas
# NUNCA escreve — `conta_classificacao_dre` usa `_pode_escriturar`
# (`PodeEscriturar`, a MESMA restrição da API), não `_pode_ler`. Mutante
# que trocasse a checagem por `_pode_ler` deixaria PARALEGAL gravar.
# ---------------------------------------------------------------------------


def test_t06_paralegal_recebe_403_no_get_e_no_post_da_classificacao_sem_gravar_nada(
    client, cenario_dre_completo
):
    _autenticar(
        client, cenario_dre_completo["escritorio"], papel=Papel.PARALEGAL, username="paralegal-t06"
    )
    empresa = cenario_dre_completo["empresa"]
    receita_bruta = Conta.objects.get(empresa=empresa, codigo="3.1")
    valor_original = receita_bruta.classificacao_dre
    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita_bruta.id])

    resposta_get = client.get(url)
    assert resposta_get.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta_get.templates]
    assert receita_bruta.nome not in resposta_get.content.decode()

    resposta_post = client.post(url, data={"classificacao_dre": ClassificacaoDre.OUTRAS_RECEITAS})
    assert resposta_post.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta_post.templates]

    receita_bruta.refresh_from_db()
    assert receita_bruta.classificacao_dre == valor_original  # nada gravado


# ---------------------------------------------------------------------------
# R7 (tela), reconferência DL-045 — "caso 13": fixture com MÊS DIFERENTE do
# ACUMULADO em TODA linha (`cenario_dre_completo`, acima, lança tudo num
# único mês, então mês e acumulado batem por construção — um mutante que
# trocasse a coluna "mês" pela "acumulado" (T02) nunca seria pego lá). Este
# cenário lança em JANEIRO e MARÇO/2026 e consulta a competência de MARÇO,
# para as duas colunas terem valor PRÓPRIO em toda linha e subtotal — e o
# resultado financeiro sai NEGATIVO nas duas colunas (T03: parênteses).
#
# A tabela é lida LINHA A LINHA por `_LeitorDeLinhasDaDre` (título, mês,
# acumulado) — nunca por contagem de substring solta no corpo, que não
# distingue "o valor certo está na CÉLULA certa" de "o valor aparece em
# algum lugar do documento" (T01: linha trocada; T04: resultado financeiro
# mostrando o lucro bruto). O bloco de identificação do item 51 (mês de
# março, acumulado de 01/01 a 31/03) mata N22 (fim do acumulado impresso
# como início do mês, em vez de fim do mês).
# ---------------------------------------------------------------------------


class _LeitorDeLinhasDaDre(HTMLParser):
    """Lê, de `<table class="tabela-dre">` (templates/contabilidade/
    dre.html), cada `<tr>` do `<tbody>` como uma tupla (título, mês,
    acumulado) — texto de CADA célula, espaço/quebra de linha colapsados.
    Um parser de HTML, não uma expressão regular sobre o texto bruto ou
    uma contagem de substring: o R7-tela da reconferência pede
    explicitamente a tabela lida LINHA A LINHA, porque só assim um
    mutante que troca o CONTEÚDO de uma célula por outra linha (T01), ou
    a coluna mês pela acumulado (T02), ou omite o parêntese do negativo
    (T03), ou usa a fórmula errada num subtotal (T04) tem como ser pego —
    uma busca de substring no corpo inteiro não nota célula errada
    quando o valor (por coincidência ou não) aparece em ALGUM lugar do
    documento.

    Molde de `_LeitorDeFormularios`
    (test_dl019_frontend_recusa_do_formulario_de_lancamento.py): mesma
    biblioteca padrão (`html.parser.HTMLParser`), nenhuma dependência
    nova.
    """

    def __init__(self):
        super().__init__()
        self.linhas = []
        self._dentro_da_tabela = 0
        self._dentro_do_tbody = False
        self._linha_atual = None
        self._celula_atual = None

    def handle_starttag(self, tag, atributos):
        atributos = dict(atributos)
        if tag == "table":
            if "tabela-dre" in (atributos.get("class") or "").split():
                self._dentro_da_tabela += 1
            return
        if not self._dentro_da_tabela:
            return
        if tag == "tbody":
            self._dentro_do_tbody = True
        elif tag == "tr" and self._dentro_do_tbody:
            self._linha_atual = []
        elif tag == "td" and self._linha_atual is not None:
            self._celula_atual = []

    def handle_data(self, data):
        if self._celula_atual is not None:
            self._celula_atual.append(data)

    def handle_endtag(self, tag):
        if tag == "table" and self._dentro_da_tabela:
            self._dentro_da_tabela -= 1
            if not self._dentro_da_tabela:
                self._dentro_do_tbody = False
            return
        if not self._dentro_da_tabela:
            return
        if tag == "tbody":
            self._dentro_do_tbody = False
        elif tag == "td" and self._celula_atual is not None:
            texto = " ".join("".join(self._celula_atual).split())
            self._linha_atual.append(texto)
            self._celula_atual = None
        elif tag == "tr" and self._linha_atual is not None:
            if len(self._linha_atual) == 3:
                self.linhas.append(tuple(self._linha_atual))
            self._linha_atual = None


def _linhas_da_dre_por_titulo(html):
    leitor = _LeitorDeLinhasDaDre()
    leitor.feed(html)
    assert leitor.linhas, 'nenhuma linha lida de <table class="tabela-dre"> — a tabela existe?'
    por_titulo = {}
    for titulo, mes, acumulado in leitor.linhas:
        assert titulo not in por_titulo, f"título repetido na tabela: {titulo!r}"
        por_titulo[titulo] = (mes, acumulado)
    return por_titulo


@pytest.fixture
def cenario_dre_mes_diferente_do_acumulado():
    """Lançamentos em JANEIRO e MARÇO/2026, na MESMA conta em cada linha —
    a coluna "mês" (consulta em mes=3) vê só o lançamento de março; a
    coluna "acumulado" vê janeiro + março. Todo valor de linha e subtotal
    tem mês != acumulado, e o resultado financeiro sai NEGATIVO nas duas
    colunas (mês: -350,00; acumulado: -270,00) — números conferidos à mão
    e por script (nenhum arredondamento binário: tudo `Decimal`).
    """
    escritorio = Escritorio.objects.create(nome="Escritório DL-045t Caso13", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DRE Caso 13 DL-045t Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa = _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    receita_bruta = _conta(
        empresa,
        codigo="3.1",
        nome="Receita Bruta",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.RECEITA_BRUTA,
    )
    deducoes = _conta(
        empresa,
        codigo="3.2",
        nome="Deduções da Receita",
        tipo=TipoConta.RECEITA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DEDUCOES_DA_RECEITA,
    )
    custo = _conta(
        empresa,
        codigo="4.1",
        nome="Custo dos Serviços",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.CUSTO,
    )
    despesas_vendas = _conta(
        empresa,
        codigo="4.2",
        nome="Despesas com Vendas",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DESPESAS_COM_VENDAS,
    )
    despesas_adm = _conta(
        empresa,
        codigo="4.3",
        nome="Despesas Gerais e Administrativas",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS,
    )
    outras_receitas = _conta(
        empresa,
        codigo="3.3",
        nome="Outras Receitas",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.OUTRAS_RECEITAS,
    )
    outras_despesas = _conta(
        empresa,
        codigo="4.4",
        nome="Outras Despesas",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.OUTRAS_DESPESAS,
    )
    outras_despesas_operacionais = _conta(
        empresa,
        codigo="4.5",
        nome="Outras Despesas Operacionais",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS,
    )
    receitas_financeiras = _conta(
        empresa,
        codigo="3.4",
        nome="Receitas Financeiras",
        tipo=TipoConta.RECEITA,
        natureza=C,
        classificacao_dre=ClassificacaoDre.RECEITAS_FINANCEIRAS,
    )
    despesas_financeiras = _conta(
        empresa,
        codigo="4.6",
        nome="Despesas Financeiras",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.DESPESAS_FINANCEIRAS,
    )
    provisao = _conta(
        empresa,
        codigo="4.7",
        nome="Provisão para IRPJ e CSLL",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.PROVISAO_IRPJ_CSLL,
    )
    participacoes = _conta(
        empresa,
        codigo="4.8",
        nome="Participações",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_dre=ClassificacaoDre.PARTICIPACOES,
    )

    janeiro = timezone.datetime(2026, 1, 16).date()
    marco = timezone.datetime(2026, 3, 16).date()
    # (histórico, débito, crédito, valor de janeiro, valor de março) — MESMA
    # direção débito/crédito de `cenario_dre_completo`, só o valor muda por
    # mês (nenhuma conta nova, nenhum lançamento redundante).
    lancamentos = (
        ("Receita bruta de serviços", caixa, receita_bruta, "4000.00", "6000.00"),
        ("ISS sobre serviços (dedução)", deducoes, caixa, "300.00", "700.00"),
        ("Custo dos serviços prestados", custo, caixa, "1000.00", "2000.00"),
        ("Comissão de vendas", despesas_vendas, caixa, "200.00", "300.00"),
        ("Despesas administrativas", despesas_adm, caixa, "300.00", "500.00"),
        ("Receita de aluguel eventual", caixa, outras_receitas, "80.00", "120.00"),
        ("Baixa de bem obsoleto", outras_despesas, caixa, "40.00", "60.00"),
        ("Multa administrativa", outras_despesas_operacionais, caixa, "20.00", "30.00"),
        (
            "Rendimento de aplicação financeira",
            caixa,
            receitas_financeiras,
            "130.00",
            "50.00",
        ),
        ("Juros de empréstimo", despesas_financeiras, caixa, "50.00", "400.00"),
        ("Provisão de IRPJ/CSLL do período", provisao, caixa, "110.00", "310.00"),
        ("Participação de administradores", participacoes, caixa, "30.00", "90.00"),
    )
    for historico, debito, credito, valor_janeiro, valor_marco in lancamentos:
        _lancar(empresa, janeiro, historico, debito, credito, valor_janeiro)
        _lancar(empresa, marco, historico, debito, credito, valor_marco)

    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "ano": 2026,
        "mes": 3,
    }


# `{titulo: (mes_esperado, acumulado_esperado)}` — os NÚMEROS batem com a
# fixture acima (débito/crédito de janeiro + março), conferidos por script
# em Decimal antes de entrarem aqui (nenhum arredondamento binário). Cada
# valor tem o parêntese de negativo já incluído no texto esperado — mesma
# apresentação de `_valor_dre.html` (RC-90).
_VALORES_ESPERADOS_CASO_13 = {
    "Receita bruta de vendas e serviços": ("6.000,00", "10.000,00"),
    "Deduções da receita (impostos, devoluções e abatimentos)": ("700,00", "1.000,00"),
    "Receita líquida": ("5.300,00", "9.000,00"),
    "Custo (CMV/CPV/CSP)": ("2.000,00", "3.000,00"),
    "Resultado bruto": ("3.300,00", "6.000,00"),
    "Despesas com vendas": ("300,00", "500,00"),
    "Despesas gerais e administrativas": ("500,00", "800,00"),
    "Outras receitas": ("120,00", "200,00"),
    "Outras despesas": ("60,00", "100,00"),
    "Outras despesas operacionais": ("30,00", "50,00"),
    # Nenhuma conta desta fixture está classificada nesta linha — sempre
    # 0,00 nas duas colunas (a linha existe e é IMPRESSA mesmo vazia,
    # HI-29 — as treze linhas do art. 187 são estrutura fixa).
    "Resultado de equivalência patrimonial": ("0,00", "0,00"),
    "Resultado antes do resultado financeiro": ("2.530,00", "4.750,00"),
    "Receitas financeiras": ("50,00", "180,00"),
    "Despesas financeiras": ("400,00", "450,00"),
    "Resultado financeiro": ("(350,00)", "(270,00)"),
    "Resultado antes dos tributos sobre o lucro": ("2.180,00", "4.480,00"),
    "Provisão para IRPJ e CSLL": ("310,00", "420,00"),
    "Participações": ("90,00", "120,00"),
    "Lucro (prejuízo) líquido do período": ("1.780,00", "3.940,00"),
}


def test_r7_tela_caso_13_mes_diferente_do_acumulado_linha_a_linha(
    client, cenario_dre_mes_diferente_do_acumulado
):
    _autenticar(client, cenario_dre_mes_diferente_do_acumulado["escritorio"])
    empresa = cenario_dre_mes_diferente_do_acumulado["empresa"]
    url = reverse("contabilidade_web:dre", args=[empresa.id])
    resposta = client.get(f"{url}?ano=2026&mes=3")
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "NÃO pode ser emitida" not in conteudo

    linhas = _linhas_da_dre_por_titulo(conteudo)
    assert set(linhas) == set(_VALORES_ESPERADOS_CASO_13), set(_VALORES_ESPERADOS_CASO_13) ^ set(
        linhas
    )
    for titulo, (mes_esperado, acumulado_esperado) in _VALORES_ESPERADOS_CASO_13.items():
        mes_lido, acumulado_lido = linhas[titulo]
        # T02 (mês mostra o acumulado): comparar as DUAS colunas separadas
        # já mata — mês e acumulado nunca coincidem nesta fixture.
        assert mes_lido == mes_esperado, (titulo, "mês", mes_lido, mes_esperado)
        assert acumulado_lido == acumulado_esperado, (
            titulo,
            "acumulado",
            acumulado_lido,
            acumulado_esperado,
        )
    # T01 (linha trocada)/T04 (resultado financeiro mostra o lucro bruto):
    # cobertos pela comparação título-a-título acima — uma troca de linha
    # faria ALGUM título ler o par (mês, acumulado) de outro título.
    # T03 (negativo sem parêntese): conferido pelo formato literal
    # "(350,00)"/"(270,00)" em `_VALORES_ESPERADOS_CASO_13`, acima.

    # N22: o bloco de identificação (item 51) imprime o FIM do acumulado
    # como 31/03/2026 (fim do MÊS pedido), nunca o início do mês (01/03).
    assert "01/01/2026 a 31/03/2026" in conteudo
    assert "01/01/2026 a 01/03/2026" not in conteudo
