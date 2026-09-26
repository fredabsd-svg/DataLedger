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
from decimal import Decimal

import pytest
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
    assert "Lucro líquido do período" not in conteudo
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
        "Lucro bruto",
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
        "Lucro líquido do período",
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


def test_conta_classificacao_dre_guarda_de_transicao_recusa_com_movimento(
    client, cenario_dre_completo
):
    """A guarda de TRANSIÇÃO de `Conta.clean()` — recusar reclassificar
    uma conta que já tem lançamento gravado — aparece na TELA como
    `form.non_field_errors()`, nunca 500 nem gravação silenciosa. A
    conta "Receita bruta" do cenário completo TEM movimento (a fixture
    lança 10.000,00 nela)."""
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    receita_bruta = Conta.objects.get(empresa=empresa, codigo="3.1")
    assert receita_bruta.classificacao_dre == ClassificacaoDre.RECEITA_BRUTA

    url = reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, receita_bruta.id])
    resposta = client.post(url, data={"classificacao_dre": ClassificacaoDre.OUTRAS_RECEITAS})
    assert resposta.status_code == 200  # re-renderiza o formulário, não redireciona
    conteudo = resposta.content.decode()
    assert "já tem lançamento gravado" in conteudo
    # A SELEÇÃO que a pessoa tentou continua preenchida (formulário
    # preservado) — não some com o erro.
    assert 'value="outras_receitas" selected' in conteudo
    receita_bruta.refresh_from_db()
    assert receita_bruta.classificacao_dre == ClassificacaoDre.RECEITA_BRUTA  # nada mudou


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
    # Link direto para classificar/corrigir esta conta específica.
    assert (
        reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, conta_torta.id])
        in conteudo
    )


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
