"""DL-086 — contrato dos componentes nas telas revisadas da contabilidade.

F-03, F-05, F-06 e F-07 são achados de LAYOUT: o defeito era classe CSS
inexistente ou componente pronto ignorado, e estes testes fixam o contrato
novo de cada tela para a regressão ser vista, não apenas conferida à mão:

- F-05: o grupo "Critério de apuração" do Balancete é `fieldset`/`legend` no
  componente `.campo-radio` (o leitor de tela precisa saber que os radios são
  UM grupo com este nome), com nome e valores GET preservados.
- F-06: as caixas de confirmação usam `.campo--caixa` — não `.campo-checkbox`,
  que não existe em CSS nenhum.
- F-03: a conferência da exportação usa `.lista-de-definicao`, `.tabela-dados`
  e `.cartao-tabela` — não `.relatorio-conferencia`, que também não existe.
- F-07: as ações de classificação do Plano de contas seguem a regra POR
  CONTAGEM do §8.4b: três ou mais ações viram o menu `.menu-acoes`; duas
  ações ficam em dois botões pequenos.

Dados 100% sintéticos, criados aqui. Os rótulos e URLs assertados são os
mesmos de antes da revisão (a mudança é de estrutura, não de destino).
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.template.loader import get_template
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

_CONTADOR_DE_CNPJ = iter(range(56000000000000, 56000000009999))
USUARIO = "gestor-dl086-componentes"


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _cenario(nome="Empresa DL-086 componentes"):
    escritorio = Escritorio.objects.create(nome="Escritório DL-086", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social=nome, cnpj=_cnpj_sintetico()
    )
    usuario = get_user_model().objects.create_user(
        username=USUARIO,
        email=f"{USUARIO}@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return escritorio, empresa


def _entrar(client):
    assert client.login(username=USUARIO, password="senha-forte-123")


def _conta(empresa, codigo, nome, tipo, natureza):
    return Conta.objects.create(
        empresa=empresa, codigo=codigo, nome=nome, tipo=tipo, natureza=natureza
    )


# ---------------------------------------------------------------------------
# F-05 — Balancete: grupo de rádio com fieldset/legend
# ---------------------------------------------------------------------------


def test_balancete_agrupa_o_criterio_de_apuracao_em_fieldset_legend(client):
    escritorio, empresa = _cenario("Empresa DL-086 balancete")
    _entrar(client)
    html = client.get(reverse("contabilidade_web:balancete", args=[empresa.id])).content.decode()

    assert "<legend>Critério de apuração</legend>" in html
    assert '<fieldset class="campo campo-radio campo-criterio-de-apuracao">' in html
    # Nome e valores GET preservados — o filtro continua o mesmo formulário.
    assert 'name="criterio_de_apuracao"' in html
    assert 'value="todas"' in html
    assert 'value="com_movimento"' in html
    # O achado F-05 era justamente o rótulo num span de classe inexistente.
    assert "campo-rotulo" not in html


# ---------------------------------------------------------------------------
# F-06 — caixas de confirmação com o componente pronto
# ---------------------------------------------------------------------------


def test_exportar_usa_campo_de_caixa_nas_tres_confirmacoes(client):
    escritorio, empresa = _cenario("Empresa DL-086 caixas")
    _entrar(client)
    html = client.get(
        reverse("contabilidade_web:lancamentos_exportar", args=[empresa.id])
    ).content.decode()

    assert html.count('class="campo campo--caixa"') == 3
    assert "campo-checkbox" not in html  # classe inexistente, achado F-06
    for nome in ("incluir_saldos", "omitir_nao_representaveis", "normalizar_texto"):
        assert f'name="{nome}"' in html


def test_efetivacao_da_importacao_usa_campo_de_caixa():
    """A outra caixa de confirmação da mesma família (F-06) — a parcial da
    efetivação renderizada com o contexto mínimo do ramo "tudo ou nada"."""
    importacao = SimpleNamespace(id=1)
    html = get_template("contabilidade/_lancamentos_importacao_efetivacao.html").render(
        {
            "empresa": SimpleNamespace(id=1),
            "importacao": importacao,
            "tudo_ou_nada": {
                "pode": True,
                "quantidade": 1,
                "pendencias": [],
                "erros_do_arquivo": [],
            },
            "pode_agir": True,
            "politica_tudo_ou_nada": "tudo_ou_nada",
            "contagens": {"total": 1},
        }
    )
    assert 'class="campo campo--caixa"' in html
    assert "campo-checkbox" not in html


# ---------------------------------------------------------------------------
# F-03 — conferência da exportação nos componentes do sistema
# ---------------------------------------------------------------------------


def test_conferencia_da_exportacao_usa_lista_de_definicao_e_tabelas_do_sistema(client):
    escritorio, empresa = _cenario("Empresa DL-086 conferencia")
    caixa = _conta(empresa, "1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)
    receita = _conta(empresa, "3", "Receita de serviços", TipoConta.RECEITA, NaturezaConta.CREDORA)
    # Um lançamento representável (1 débito, 1 crédito) e um N×M que o
    # sistema de referência não representa: a conferência mostra os dois
    # recortes (contas usadas e omitidos) que a migração F-03 reorganizou.
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 2),
        historico="Receita comum DL-086",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": receita, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 3),
        historico="Lançamento N x M DL-086",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("6.00")},
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("4.00")},
            {"conta": receita, "tipo": TipoPartida.CREDITO, "valor": Decimal("7.00")},
            {"conta": receita, "tipo": TipoPartida.CREDITO, "valor": Decimal("3.00")},
        ],
    )
    _entrar(client)
    html = client.get(
        reverse("contabilidade_web:lancamentos_exportar", args=[empresa.id]),
        {
            "formato": "referencia",
            "inicio": "2026-03-01",
            "fim": "2026-03-31",
            "omitir_nao_representaveis": "true",
        },
    ).content.decode()

    assert "Conferência do arquivo" in html
    assert "relatorio-conferencia" not in html  # classe inexistente, achado F-03
    assert "lista-de-definicao" in html
    assert "tabela-dados" in html
    assert "cartao-tabela" in html
    # `.valor-monetario` só onde o dado é dinheiro (as somas da lista de
    # definição); as contagens da tabela de omitidos ficam sem a classe.
    assert '<dd class="valor-monetario">' in html
    assert "Débitos e créditos conferem" in html


# ---------------------------------------------------------------------------
# F-07 — Plano de contas: a regra de contagem das ações de linha
# ---------------------------------------------------------------------------


def test_tres_acoes_de_classificacao_viram_o_menu_classificar(client):
    escritorio, empresa = _cenario("Empresa DL-086 menu")
    receita = _conta(empresa, "3", "Receita de serviços", TipoConta.RECEITA, NaturezaConta.CREDORA)
    _entrar(client)
    html = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    ).content.decode()

    assert 'class="menu-acoes"' in html
    assert '<summary class="botao botao--secundario botao--pequeno">Classificar</summary>' in html
    assert 'class="menu-acoes__lista"' in html
    # Os itens mantêm URL e rótulo de antes da revisão.
    for rota, rotulo in (
        ("conta_classificacao_dre", "Linha da DRE"),
        ("conta_classificacao_dlpa", "Linha da DLPA"),
        ("conta_classificacao_dfc", "Classificação da DFC"),
    ):
        assert reverse(f"contabilidade_web:{rota}", args=[empresa.id, receita.id]) in html
        assert rotulo in html


def test_duas_acoes_de_classificacao_ficam_em_dois_botoes_pequenos(client):
    """§8.4b (F-07): a regra é por CONTAGEM — conta sem DRE nem DMPL tem
    exatamente duas ações, e duas ações não viram menu."""
    escritorio, empresa = _cenario("Empresa DL-086 dois botoes")
    passivo = _conta(empresa, "2", "Fornecedores", TipoConta.PASSIVO, NaturezaConta.CREDORA)
    _entrar(client)
    html = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    ).content.decode()

    assert "menu-acoes" not in html
    assert (
        reverse("contabilidade_web:conta_classificacao_dlpa", args=[empresa.id, passivo.id]) in html
    )
    assert (
        reverse("contabilidade_web:conta_classificacao_dfc", args=[empresa.id, passivo.id]) in html
    )
    # DRE é só de resultado e DMPL só de patrimônio líquido: nem aparecem.
    assert (
        reverse("contabilidade_web:conta_classificacao_dre", args=[empresa.id, passivo.id])
        not in html
    )
    assert (
        reverse("contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, passivo.id])
        not in html
    )
