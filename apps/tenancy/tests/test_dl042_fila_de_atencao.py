"""DL-042 (2ª passada): "Início" como fila do que precisa de atenção
(apps.tenancy.views._fila_de_atencao, renderizada em tenancy/painel.html).

Três garantias, cada uma com dado sintético próprio:

1. Isolamento entre escritórios — nenhuma categoria da fila de um
   escritório aparece na tela de outro (RC-18/AGENTS.md §11).
2. Permissão por papel — CLIENTE (fora de PAPEIS_QUE_LEEM_CONTABILIDADE e
   de PAPEIS_QUE_CONSULTAM_DOCUMENTOS) não vê a seção inteira, mesmo
   quando há pendência real no escritório dele.
3. Número de consultas limitado — `django_assert_max_num_queries` contra
   o painel com pendência em TODAS as categorias ao mesmo tempo, prova de
   que a fila não introduz N+1 por categoria nem por item.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.fiscal.services import receber_envio
from apps.fiscal.tests.xml_sinteticos import (
    chave_nfse_de,
    identificador_nfse,
    xml_evento,
    xml_nfe_minimo,
    xml_nfse,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CPF_SINTETICO_VALIDO = "11144477735"


def _usuario_com_papel(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _empresa_sem_plano_de_contas(escritorio, cnpj, razao_social):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social=razao_social,
        cnpj=cnpj,
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )


# ---------------------------------------------------------------------------
# 1. Isolamento entre escritórios
# ---------------------------------------------------------------------------


def test_fila_isola_por_escritorio(client):
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11222333000181")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="99888777000162")
    _empresa_sem_plano_de_contas(escritorio_a, "22444666000177", "Empresa Exclusiva de A Ltda")
    _empresa_sem_plano_de_contas(escritorio_b, "33555777000188", "Empresa Exclusiva de B Ltda")
    usuario_a = _usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-a-fila")

    assert client.login(username="gestor-a-fila", password="senha-forte-123")
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    html = resposta.content.decode()

    assert "Empresa Exclusiva de A Ltda" in html
    assert "Empresa Exclusiva de B Ltda" not in html
    # Controle: o usuário realmente ficou no escritório A (seleção
    # automática de vínculo único, EscritorioAtivoMiddleware).
    assert client.session["escritorio_id"] == escritorio_a.id
    assert usuario_a.vinculos.get().escritorio_id == escritorio_a.id


def test_fila_de_competencias_abertas_isola_por_escritorio(client):
    escritorio_a = Escritorio.objects.create(nome="Escritório Comp A", cnpj="11222333000181")
    escritorio_b = Escritorio.objects.create(nome="Escritório Comp B", cnpj="99888777000162")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Competência Aberta A Ltda", cnpj="22444666000177"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Competência Aberta B Ltda", cnpj="33555777000188"
    )
    usuario_a = _usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-comp-a")
    _usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-comp-b")

    mes_passado = date(2026, 1, 15)
    for empresa, usuario in [(empresa_a, usuario_a), (empresa_b, None)]:
        ativo = Conta.objects.create(
            empresa=empresa,
            codigo="1",
            nome="Caixa",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
        )
        receita = Conta.objects.create(
            empresa=empresa,
            codigo="2",
            nome="Receita",
            tipo=TipoConta.RECEITA,
            natureza=NaturezaConta.CREDORA,
        )
        criar_lancamento(
            empresa=empresa,
            data=mes_passado,
            historico="Lançamento em competência antiga — fila DL-042",
            itens=[
                {"conta": ativo, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
                {"conta": receita, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
            ],
            criado_por=usuario_a if usuario is None else usuario,
            chave_idempotencia=f"dl042-fila-{empresa.id}",
        )

    assert client.login(username="gestor-comp-a", password="senha-forte-123")
    html = client.get(reverse("tenancy:painel")).content.decode()
    assert "Competência Aberta A Ltda" in html
    assert "Competência Aberta B Ltda" not in html


# ---------------------------------------------------------------------------
# 2. Permissão por papel — CLIENTE não vê itens contábeis/fiscais
# ---------------------------------------------------------------------------


def test_papel_cliente_nao_ve_a_fila_de_atencao(client):
    escritorio = Escritorio.objects.create(nome="Escritório Cliente", cnpj="11222333000181")
    _empresa_sem_plano_de_contas(escritorio, "22444666000177", "Empresa Pendente Para Cliente Ltda")
    _usuario_com_papel(escritorio, Papel.CLIENTE, "cliente-fila")

    assert client.login(username="cliente-fila", password="senha-forte-123")
    resposta = client.get(reverse("tenancy:painel"))
    html = resposta.content.decode()

    assert "O que precisa de atenção" not in html
    assert "Empresa Pendente Para Cliente Ltda" not in html


@pytest.mark.parametrize(
    "papel", [Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO]
)
def test_papeis_que_leem_contabilidade_veem_a_fila(client, papel):
    escritorio = Escritorio.objects.create(nome=f"Escritório {papel}", cnpj="11222333000181")
    _empresa_sem_plano_de_contas(escritorio, "22444666000177", "Empresa Visível Para O Papel Ltda")
    _usuario_com_papel(escritorio, papel, f"usuario-{papel}")

    assert client.login(username=f"usuario-{papel}", password="senha-forte-123")
    html = client.get(reverse("tenancy:painel")).content.decode()
    assert "O que precisa de atenção" in html
    assert "Empresa Visível Para O Papel Ltda" in html


def test_papel_que_le_contabilidade_sem_pendencia_mostra_tudo_em_dia(client):
    """Estado vazio "tudo em dia": o papel TEM permissão (a seção
    aparece), mas não há nenhuma pendência — nunca confundir com o
    CLIENTE, que nem a seção vê."""
    escritorio = Escritorio.objects.create(nome="Escritório Em Dia", cnpj="11222333000181")
    _usuario_com_papel(escritorio, Papel.GESTOR, "gestor-em-dia")

    assert client.login(username="gestor-em-dia", password="senha-forte-123")
    html = client.get(reverse("tenancy:painel")).content.decode()
    assert "O que precisa de atenção" in html
    assert "Tudo em dia." in html


# ---------------------------------------------------------------------------
# 3. Número de consultas limitado
# ---------------------------------------------------------------------------


def test_fila_com_pendencia_em_todas_as_categorias_tem_consultas_limitadas(
    client, django_assert_max_num_queries
):
    escritorio = Escritorio.objects.create(nome="Escritório Cheio", cnpj="11222333000181")
    usuario = _usuario_com_papel(escritorio, Papel.GESTOR, "gestor-cheio")

    # Categoria 1: empresa sem plano de contas.
    _empresa_sem_plano_de_contas(escritorio, "22444666000177", "Empresa Sem Plano Ltda")

    # Categoria 2: competência de mês anterior ainda aberta.
    empresa_competencia = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Competência Ltda", cnpj="33555777000188"
    )
    ativo = Conta.objects.create(
        empresa=empresa_competencia,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa_competencia,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    criar_lancamento(
        empresa=empresa_competencia,
        data=date(2026, 1, 15),
        historico="Lançamento — teste de consultas da fila DL-042",
        itens=[
            {"conta": ativo, "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": receita, "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
        criado_por=usuario,
        chave_idempotencia="dl042-fila-consultas-competencia",
    )

    # Categoria 3 e 4: fiscal — precisa de uma empresa cujo CNPJ bate com o
    # prestador do XML sintético, senão o envio vira "recusado: nenhum
    # participante do escritório" (mesmo cuidado do cenario_fiscal em
    # test_dl024_atalhos_e_acessibilidade.py).
    empresa_fiscal = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Fiscal Ltda", cnpj="44666888000199"
    )
    receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfe_minimo(),
        nome_arquivo="nota-fiscal-eletronica-recusada.xml",
    )
    identificador = identificador_nfse(sufixo=901)
    receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(
            identificador=identificador,
            numero="901",
            prestador_documento=empresa_fiscal.cnpj,
            tomador_nome="Tomador da Fila DL-042",
        ),
        nome_arquivo="nota-901.xml",
    )
    receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_evento(
            chave_nfse=chave_nfse_de(identificador),
            codigo="e101101",
            autor_documento=empresa_fiscal.cnpj,
        ),
        nome_arquivo="evento-cancelamento-901.xml",
    )

    # Categoria 5: empresa CPF em livro-caixa (informativo).
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa CPF Livro-Caixa Ltda",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_SINTETICO_VALIDO,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )

    assert client.login(username="gestor-cheio", password="senha-forte-123")

    # Controle positivo: as cinco categorias realmente aparecem — sem
    # isso, um teste de "consultas limitadas" que sempre passa (porque a
    # fila está vazia) não prova nada (a mesma lição de BL-271 registrada
    # em test_dl024_atalhos_e_acessibilidade.py).
    html_controle = client.get(reverse("tenancy:painel")).content.decode()
    for titulo in [
        "Empresas sem plano de contas",
        "Competências de meses anteriores ainda abertas",
        "Envios fiscais com recusas recentes",
        "Notas canceladas recebidas",
        "Empresas CPF em livro-caixa",
    ]:
        assert titulo in html_controle, f"controle: categoria {titulo!r} deveria aparecer"

    # 26 é o TETO, não o número medido. DL-044 (3ª iteração): a faixa de
    # indicadores do topo (`_indicadores_do_painel` — até 4 `.count()`,
    # tamanho FIXO, nunca por item) e "Empresas da carteira"
    # (`_empresas_da_carteira` — 1 consulta de empresas + 2 agregações
    # `values().annotate()`, tamanho FIXO, nunca uma sub-consulta por
    # empresa) somaram ao teto anterior de 20 (que media 14 consultas de
    # verdade) — o NOVO número medido é 21. A margem entre 21 e 26 continua
    # de propósito — o teto existe para pegar uma REGRESSÃO de N+1 futura
    # (uma consulta por item/empresa), não para cravar o número exato de
    # hoje, que quebraria a cada ajuste sem relação com N+1.
    with django_assert_max_num_queries(26):
        resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
