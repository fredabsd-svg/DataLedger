"""DL-045, fatia 3 — a tela e o documento da DRE
(apps.contabilidade.views_web.dre) e o campo "Linha da DRE" no formulário
de CRIAÇÃO de conta (`conta_nova`).

Cobre os critérios do plano
(docs/planos/DL-045-demonstracao-do-resultado.md) que são da FRENTE DA
TELA: permissão verificada no servidor com o CORPO conferido, isolamento
entre escritórios, veto de emissão NOMEANDO o que falta (critério 6),
identificação NBC TG 26 item 51 em toda página (critério 7), e o campo
"Linha da DRE" no formulário de conta (critério 4).

⚠️ NOTA (instrução do arquiteto-senior, 26/09/2026): a edição de conta
EXISTENTE (reclassificar a Linha da DRE de uma conta já cadastrada) fica
de fora desta etapa — espera um serviço próprio, com guardas e trilha de
auditoria, que o desenvolvedor-pleno ainda vai construir. Por isso este
arquivo não testa nenhuma tela de edição de conta (ela não existe ainda)
— só a CRIAÇÃO.

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

from apps.contabilidade.models import ClassificacaoDre, Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
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


# NOTA (instrução do arquiteto-senior, 26/09/2026): não existe teste de
# "editar conta" aqui — a tela não existe ainda. A guarda de TRANSIÇÃO de
# `Conta.clean()` (recusar reclassificar uma conta que já tem lançamento
# gravado) já tem suíte própria no MODELO (test_dl045_dre.py, fatia 1);
# quando a tela de edição existir (serviço próprio do desenvolvedor-
# pleno), o teste de que a recusa aparece como `form.non_field_errors()`
# entra junto com ela.


def test_plano_de_contas_mostra_a_linha_da_dre_cadastrada(client, cenario_dre_completo):
    _autenticar(client, cenario_dre_completo["escritorio"])
    empresa = cenario_dre_completo["empresa"]
    conteudo = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    ).content.decode()
    assert "Linha da DRE" in conteudo
    assert "Receita bruta de vendas e serviços" in conteudo
