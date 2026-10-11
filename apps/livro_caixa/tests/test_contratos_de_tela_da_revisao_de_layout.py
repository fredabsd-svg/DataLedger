"""DL-086 — contratos de TELA da revisão de layout do livro-caixa (A-05, A-08,
A-10, A-11, A-12, A-15, A-19, A-21, A-24).

Este arquivo guarda o NOVO contrato das telas corrigidas na revisão — o
arquivo `test_dl086_*` desta etapa pertence ao item A-02 (estorno com motivo)
e é de outro implementador, por isso os testes da revisão moram aqui.

Os testes que assertavam o contrato ANTIGO (ação que sumia para quem só lê,
"Salvar" genérico, vazio em prosa solta) estão nos arquivos de teste da
DL-046/053 e não podem ser editados por este implementador — o que precisa
mudar neles está registrado no relatório da etapa.

Dados 100% sintéticos. O "mês atual" da tela nunca é o dos dados: os testes de
estado vazio do período PADRÃO não criam lançamento nenhum, então são
independentes da data de execução.
"""

import itertools
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa.models import ContaLivroCaixa, DependentesCarneLeaoCliente, NaturezaCaixa
from apps.livro_caixa.services import criar_lancamento_caixa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

_CONTADOR_DE_DOCUMENTO = itertools.count(1)


def _cpf_sintetico():
    base = ["11144477735", "22255588846", "52998224725", "12345678909", "98765432100"]
    return base[next(_CONTADOR_DE_DOCUMENTO) % len(base)]


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_DOCUMENTO):014d}"


def _autenticar(client, escritorio, papel=Papel.GESTOR):
    usuario = get_user_model().objects.create_user(
        username=f"{papel}-revisao-{next(_CONTADOR_DE_DOCUMENTO)}",
        email=f"revisao-{next(_CONTADOR_DE_DOCUMENTO)}@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    client.force_login(usuario)
    return usuario


@pytest.fixture
def cenario():
    # Nomes SEM identificador interno do projeto: as guardas "sem identificador
    # interno" olham o texto visível, e dado de teste com "DL-xxx" no nome
    # esconderia um vazamento real do produto.
    escritorio = Escritorio.objects.create(
        nome="Escritório Revisão de telas", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano de Tal Revisão de telas",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=_cpf_sintetico(),
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    conta_receita = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="R1",
        nome="Aluguel recebido",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta_p20 = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="D20",
        nome="IRPF pago",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00007",
    )
    # Empresa SEM conta nenhuma — é o que tira o plano de contas e o
    # formulário de lançamento do vazio (A-12).
    empresa_sem_conta = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Beltrano Revisão de telas",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=_cpf_sintetico(),
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "empresa_sem_conta": empresa_sem_conta,
        "conta_receita": conta_receita,
        "conta_p20": conta_p20,
    }


def _lancar(empresa, conta, dia, valor, historico, **kwargs):
    """`recebido_de` só quando o teste pedir: em despesa o serviço RECUSA o
    campo, e em receita ele é obrigatório — cada chamada diz o que precisa."""
    return criar_lancamento_caixa(
        empresa=empresa,
        conta=conta,
        data=dia,
        valor=Decimal(valor),
        historico=historico,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# A-05 (DL-086): a ação primária que sumia para quem só lê fica visível e
# desabilitada, COM o motivo — direção de arte §2B.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rota", "rotulo", "motivo"),
    [
        ("livro_caixa_web:plano_de_contas", "Nova conta", "não cadastrar conta"),
        ("livro_caixa_web:lancamentos", "Novo lançamento", "não lançar nem estornar"),
    ],
)
def test_a05_acao_primaria_para_quem_so_le_e_desabilitada_com_o_motivo(
    client, cenario, rota, rotulo, motivo
):
    _autenticar(client, cenario["escritorio"], papel=Papel.PARALEGAL)
    url = reverse(rota, args=[cenario["empresa"].id])

    html = client.get(url).content.decode()

    assert f'disabled aria-describedby="ajuda_sem_permissao">{rotulo}</button>' in html
    assert 'id="ajuda_sem_permissao"' in html
    assert motivo in html
    # O sumiço antigo (contrato que este achado corrigia) continua proibido:
    # o rótulo TEM de estar na tela, mesmo desabilitado.
    assert rotulo in html


def test_a05_acao_primaria_para_quem_escritura_continua_o_link_habilitado(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:lancamentos", args=[cenario["empresa"].id])
    ).content.decode()

    assert 'class="botao botao--primario"' in html
    assert "Novo lançamento</a>" in html
    assert "ajuda_sem_permissao" not in html


# ---------------------------------------------------------------------------
# A-08 (DL-086, DE-101): encerrar período é ação sensível — tom --perigoso.
# ---------------------------------------------------------------------------


def test_a08_botao_de_encerrar_mes_e_perigoso_e_nomeia_o_mes(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    resposta = client.get(
        reverse("livro_caixa_web:mes_encerrar", args=[cenario["empresa"].id]),
        {"ano": "2026", "mes": "5"},
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'class="botao botao--perigoso">Encerrar mês 05/2026</button>' in html
    assert 'botao--primario">Encerrar mês' not in html


# ---------------------------------------------------------------------------
# A-10 (DL-086): linha de SEÇÃO do tbody rotula linhas — scope="rowgroup".
# ---------------------------------------------------------------------------


def test_a10_carne_leao_mensal_secoes_do_tbody_sao_rowgroup(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)
    _lancar(
        cenario["empresa"],
        cenario["conta_receita"],
        date(2026, 3, 10),
        "1000.00",
        "Aluguel de março",
        recebido_de="PF",
    )

    html = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa"].id]),
        {"ano": "2026", "mes": "3"},
    ).content.decode()

    # Seis seções no tbody; a linha de identificação do thead continua colgroup.
    assert html.count('scope="rowgroup"') == 6
    assert html.count('scope="colgroup"') == 1
    assert '<th scope="rowgroup" colspan="2">Rendimentos sujeitos ao carnê-leão</th>' in html


def test_a10_arquivos_do_carne_leao_secoes_do_tbody_sao_rowgroup(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)
    _lancar(
        cenario["empresa"],
        cenario["conta_receita"],
        date(2026, 3, 10),
        "1000.00",
        "Aluguel de março",
        recebido_de="PF",
    )

    html = client.get(
        reverse("livro_caixa_web:arquivos_carne_leao", args=[cenario["empresa"].id]),
        {"inicio": "2026-03-01", "fim": "2026-03-31"},
    ).content.decode()

    assert html.count('scope="rowgroup"') == 3
    assert html.count('scope="colgroup"') == 1
    assert '<th scope="rowgroup" colspan="2">Arquivo de rendimentos</th>' in html


def test_a10_relatorio_secao_p20_do_tbody_e_rowgroup(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)
    _lancar(
        cenario["empresa"],
        cenario["conta_receita"],
        date(2026, 3, 10),
        "1000.00",
        "Aluguel de março",
        recebido_de="PF",
    )
    _lancar(cenario["empresa"], cenario["conta_p20"], date(2026, 3, 12), "80.00", "IRPF de março")

    html = client.get(
        reverse("livro_caixa_web:relatorio", args=[cenario["empresa"].id]),
        {"inicio": "2026-03-01", "fim": "2026-03-31"},
    ).content.decode()

    assert html.count('scope="rowgroup"') == 1
    assert 'scope="rowgroup" colspan="6"' in html
    assert "Pagamentos que deduzem a base do carnê-leão" in html


# ---------------------------------------------------------------------------
# A-11 (DL-086): o grupo de radios "Recebido de" tem nome acessível de grupo.
# ---------------------------------------------------------------------------


def test_a11_recebido_de_e_fieldset_com_legend(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:lancamento_novo", args=[cenario["empresa"].id])
    ).content.decode()

    assert '<fieldset class="campo campo-radio">' in html
    assert "<legend>Recebido de (só para receita)</legend>" in html
    # name, valores e quantidade de opções preservados.
    assert html.count('name="recebido_de"') == 3
    # O markup antigo (span no lugar do legend) não volta.
    assert "campo-criterio-de-apuracao" not in html


# ---------------------------------------------------------------------------
# A-12 (DL-086): estado vazio no componente .estado-vazio, com botão de saída.
# ---------------------------------------------------------------------------


def test_a12_plano_de_contas_vazio_tem_estado_vazio_com_botao_primario(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:plano_de_contas", args=[cenario["empresa_sem_conta"].id])
    ).content.decode()

    assert 'class="estado-vazio"' in html
    assert 'class="estado-vazio__titulo"' in html
    assert 'class="estado-vazio__descricao"' in html
    # O vazio é de DADO (falta cadastro): a saída cria dado — botão primário.
    assert (
        '<a class="botao botao--primario" href="'
        f'{reverse("livro_caixa_web:conta_nova", args=[cenario["empresa_sem_conta"].id])}"'
        ">Cadastrar a primeira conta</a>"
    ) in html


def test_a12_plano_de_contas_vazio_para_quem_so_le_o_botao_fica_com_o_motivo(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.PARALEGAL)

    html = client.get(
        reverse("livro_caixa_web:plano_de_contas", args=[cenario["empresa_sem_conta"].id])
    ).content.decode()

    assert (
        'disabled aria-describedby="ajuda_sem_permissao">Cadastrar a primeira conta</button>'
        in html
    )
    assert 'id="ajuda_sem_permissao"' in html


def test_a12_lancamento_form_sem_conta_tem_estado_vazio_com_botao_primario(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:lancamento_novo", args=[cenario["empresa_sem_conta"].id])
    ).content.decode()

    assert 'class="estado-vazio"' in html
    assert "ainda não tem nenhuma conta do livro-caixa ativa" in html
    assert ">Cadastrar conta</a>" in html


def test_a12_lista_vazia_por_filtro_tem_botao_secundario_de_sair_do_filtro(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:lancamentos", args=[cenario["empresa"].id]),
        {"inicio": "2026-04-01", "fim": "2026-04-30"},
    ).content.decode()

    assert "Nenhum lançamento encontrado com este período." in html
    # Vazio por FILTRO: a saída é sair do filtro — botão secundário (§8.4c),
    # e o primário do estado vazio não existe neste ramo.
    assert ">Ver o mês atual</a>" in html
    url_novo = reverse("livro_caixa_web:lancamento_novo", args=[cenario["empresa"].id])
    assert html.count(f'href="{url_novo}"') == 1  # só o do cabeçalho


def test_a12_lista_vazia_sem_filtro_tem_botao_primario_de_lancar(client, cenario):
    # Sem lançamento nenhum na empresa, o mês atual (período PADRÃO) está
    # vazio em qualquer data de execução.
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:lancamentos", args=[cenario["empresa"].id])
    ).content.decode()

    assert "Nenhum lançamento de caixa em" in html
    assert ">Ver o mês atual</a>" not in html
    assert "Lance o primeiro" not in html
    # Vazio de DADO: a saída cria dado — botão primário, repetindo o link do
    # cabeçalho (dois lugares, o mesmo primário).
    url_novo = reverse("livro_caixa_web:lancamento_novo", args=[cenario["empresa"].id])
    assert html.count(f'href="{url_novo}"') == 2  # cabeçalho + estado vazio


# ---------------------------------------------------------------------------
# A-15 (DL-086): a lista de lançamentos é paginada no servidor (25 por página,
# mesmo per_page e mesmo contrato de querystring do fiscal) e a paginação
# preserva os filtros.
# ---------------------------------------------------------------------------


def _lotes(empresa, conta, quantidade):
    for indice in range(quantidade):
        _lancar(
            empresa,
            conta,
            date(2026, 3, min(indice + 1, 28)),
            "10.00",
            f"Lançamento em lote {indice}",
            recebido_de="PF",
            chave_idempotencia=f"dl086-a15-lote-{indice}",
        )


def test_a15_pagina_2_existe_com_mais_de_25_lancamentos(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)
    _lotes(cenario["empresa"], cenario["conta_receita"], 26)

    url = reverse("livro_caixa_web:lancamentos", args=[cenario["empresa"].id])
    primeira = client.get(url, {"inicio": "2026-03-01", "fim": "2026-03-31"}).content.decode()
    segunda = client.get(
        url, {"inicio": "2026-03-01", "fim": "2026-03-31", "pagina": "2"}
    ).content.decode()

    assert primeira.count("Lançamento em lote") == 25
    assert segunda.count("Lançamento em lote") == 1
    assert "Página 1 de 2" in primeira
    assert "Página 2 de 2" in segunda


def test_a15_paginacao_preserva_os_filtros_do_periodo(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)
    _lotes(cenario["empresa"], cenario["conta_receita"], 26)

    url = reverse("livro_caixa_web:lancamentos", args=[cenario["empresa"].id])
    primeira = client.get(url, {"inicio": "2026-03-01", "fim": "2026-03-31"}).content.decode()
    segunda = client.get(
        url, {"inicio": "2026-03-01", "fim": "2026-03-31", "pagina": "2"}
    ).content.decode()

    # A querystring sem 'pagina' sai escapada (&amp;) e a 'pagina' vem depois,
    # literal — mesmo contrato das listas do fiscal (test_dl080_telas.py).
    assert 'href="?inicio=2026-03-01&amp;fim=2026-03-31&pagina=2"' in primeira
    assert 'href="?inicio=2026-03-01&amp;fim=2026-03-31&pagina=1"' in segunda


def test_a15_pagina_fora_da_faixa_nao_quebra(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)
    _lotes(cenario["empresa"], cenario["conta_receita"], 2)

    url = reverse("livro_caixa_web:lancamentos", args=[cenario["empresa"].id])
    resposta = client.get(url, {"inicio": "2026-03-01", "fim": "2026-03-31", "pagina": "999"})

    assert resposta.status_code == 200
    assert resposta.content.decode().count("Lançamento em lote") == 2


# ---------------------------------------------------------------------------
# A-19 (DL-086): o submit nomeia a consequência, nunca só "Salvar".
# ---------------------------------------------------------------------------


def test_a19_conta_form_nomeia_a_consequencia(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:conta_nova", args=[cenario["empresa"].id])
    ).content.decode()

    assert ">Cadastrar conta</button>" in html
    assert ">Salvar</button>" not in html


def test_a19_dependentes_nomeia_a_consequencia(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:dependentes_carne_leao", args=[cenario["empresa"].id])
    ).content.decode()

    assert ">Registrar vigência dos dependentes</button>" in html
    assert ">Salvar</button>" not in html


# ---------------------------------------------------------------------------
# A-21 (DL-086): o formato monetário é dito em TEXTO, não só no placeholder.
# ---------------------------------------------------------------------------


def test_a21_campos_monetarios_tem_texto_apoio_de_formato(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)

    html = client.get(
        reverse("livro_caixa_web:lancamento_novo", args=[cenario["empresa"].id])
    ).content.decode()

    # Valor, IRRF, multa e juros da previdência — os quatro campos monetários.
    assert html.count("Em pt-BR, como 1.234,56") == 4
    assert html.count('placeholder="0,00"') == 4
    assert 'aria-describedby="id_valor_ajuda"' in html
    assert 'id="id_valor_ajuda"' in html


# ---------------------------------------------------------------------------
# A-24 (DL-086): o .estado-vazio de dependentes tem a anatomia do componente.
# ---------------------------------------------------------------------------


def test_a24_estado_vazio_dos_dependentes_tem_anatomia_completa(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.GESTOR)
    assert not DependentesCarneLeaoCliente.objects.filter(empresa=cenario["empresa"]).exists()

    html = client.get(
        reverse("livro_caixa_web:dependentes_carne_leao", args=[cenario["empresa"].id])
    ).content.decode()

    assert 'class="estado-vazio"' in html
    assert 'class="estado-vazio__titulo"' in html
    assert 'class="estado-vazio__descricao"' in html
    assert "ainda não tem nenhuma quantidade de dependentes registrada" in html
    assert "considera zero dependentes em todo mês até o primeiro" in html
