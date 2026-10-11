"""DL-086 (achado D-01) — a trilha padrão termina no nome da tela atual.

Seis telas da contabilidade (DRE, DLPA, DMPL, DFC, Relatórios e Parâmetros
contábeis) não tinham entrada em `ROTULOS_DE_TELA`, e a trilha padrão
terminava a empresa LINKANDO para o Plano de contas — sem o passo da tela
atual e sem `aria-current` em lugar nenhum (viola o §8.2 do contrato: "o
último item da trilha é a própria tela, em texto, com aria-current — nunca
um link").

Mutante que este arquivo derruba: remover uma das seis entradas de
`ROTULOS_DE_TELA` devolve a trilha com 2 degraus e o último é link — os
dois testes falham.

Teste unitário: `_trilha_padrao` recebe `resolver_match`/`empresa_atual`;
um `SimpleNamespace` com id sintético basta para o `reverse` (não consulta
banco).
"""

from types import SimpleNamespace

import pytest

from apps.core.context_processors import ROTULOS_DE_TELA, _trilha_padrao

# As seis telas que a DL-086 deu entrada na tabela, com o rótulo esperado.
TELAS_SEM_DEGRAU_ANTES = [
    ("dre", "DRE"),
    ("dlpa", "DLPA"),
    ("dmpl", "DMPL"),
    ("dfc", "DFC"),
    ("relatorios", "Relatórios"),
    ("parametros_contabeis", "Parâmetros contábeis"),
]

_EMPRESA = SimpleNamespace(id=987_654_321, razao_social="Empresa Sintética DL-086")


def _resolver(url_name, namespace="contabilidade_web"):
    return SimpleNamespace(
        namespace=namespace,
        url_name=url_name,
        view_name=f"{namespace}:{url_name}",
    )


@pytest.mark.parametrize("url_name,rotulo", TELAS_SEM_DEGRAU_ANTES)
def test_trilha_termina_na_tela_atual_em_texto(url_name, rotulo):
    trilha = _trilha_padrao(_resolver(url_name), _EMPRESA)

    # Último degrau: a própria tela, em TEXTO (url None marca o atual).
    assert trilha[-1] == (rotulo, None), trilha
    # Estrutura completa: Contabilidade › Empresa › Tela (§8.2).
    assert len(trilha) == 3, trilha
    # Os degraus anteriores são links de verdade.
    assert all(url is not None for _, url in trilha[:-1]), trilha


def test_a_tabela_tem_exatamente_as_seis_entradas_das_seis_telas():
    """Controle nominal: se o rótulo mudar de nome no dicionário, o teste
    acima passaria a não encontrar a tela e falharia por causa errada — este
    aqui nomeia a causa certa."""
    for url_name, rotulo in TELAS_SEM_DEGRAU_ANTES:
        assert ROTULOS_DE_TELA.get(("contabilidade_web", url_name)) == rotulo


def test_tela_ja_conhecida_continua_com_o_mesmo_desenho():
    """Par positivo: o Balancete (tela antiga, já registrada) continua com 3
    degraus e o último em texto — a correção não mudou o desenho existente."""
    trilha = _trilha_padrao(_resolver("balancete"), _EMPRESA)
    assert trilha[-1] == ("Balancete", None), trilha
    assert len(trilha) == 3, trilha
