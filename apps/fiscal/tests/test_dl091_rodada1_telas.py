"""DL-091, correção da rodada 1, telas da compra e do estorno.

- T13 (A10): em cada estado da tela da compra (sem rascunho, rascunho sem natureza, com erro num
  item,
  efetivada), todo IDREF (`aria-describedby` e `for`) aponta para um `id` que existe na página.
  Antes,
  o seletor de natureza apontava para `ajuda_natureza_<item>`, que nenhum elemento definia.
- A12: o estorno da DEVOLUÇÃO DE COMPRA usa o texto da compra ("não compõe a receita"). Antes, só a
  compra usava esse texto, e a devolução mostrava "sai da receita do mês" com receita 0,00.

Dados sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, seção "Decisões para a correção".
"""

import html
import re

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import ItemNFe, NaturezaItemNFe, TipoEscrituracaoNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.test_dl091_entradas import _confirmar, _matriz, _nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Telas rodada 1 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
    _matriz(empresa, escritorio_a, "TO")
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio="2026-01-01",
    )
    return empresa


def _idrefs_sem_destino(texto):
    """Os valores de `aria-describedby` e de `for` que não existem como `id` na página."""
    ids = set(re.findall(r'\sid="([^"]+)"', texto))
    referencias = re.findall(r'aria-describedby="([^"]+)"', texto) + re.findall(
        r'\sfor="([^"]+)"', texto
    )
    return sorted({token for bloco in referencias for token in bloco.split() if token not in ids})


def test_todo_idref_da_tela_da_compra_resolve_para_um_elemento_em_cada_estado(
    client, escritorio_a, usuario_gestor_a, empresa
):
    """T13: sem rascunho, rascunho sem natureza, com erro num item e efetivada."""
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="1301")
    url = reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk])
    client.force_login(usuario_gestor_a)
    paginas = {"sem rascunho": client.get(url).content}

    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    paginas["rascunho sem natureza"] = client.get(url).content
    item = ItemNFe.objects.get(documento=documento, n_item=1)
    erro = client.post(
        url,
        {
            "acao": "item",
            "item_id": item.pk,
            "natureza": N.ENTRADA_COMERCIALIZACAO,
            "cfop_entrada": "2102",
        },
    )
    assert erro.status_code == 400
    paginas["com erro no item"] = erro.content

    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    paginas["efetivada"] = client.get(url).content

    for estado, conteudo in paginas.items():
        texto = html.unescape(conteudo.decode("utf-8"))
        assert _idrefs_sem_destino(texto) == [], estado


def test_estorno_da_devolucao_de_compra_usa_o_texto_da_compra_e_nao_o_da_receita(
    client, escritorio_a, usuario_gestor_a, empresa
):
    """A12: a devolução de compra (finNFe 4, saída própria) está fora da receita, como a compra."""
    devolucao = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="1302",
        cfop="5202",
        tp_nf="1",
        fin_nfe="4",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    esc = servico.criar_rascunho(vinculo(devolucao, empresa), usuario=usuario_gestor_a)
    assert esc.tipo == TipoEscrituracaoNFe.DEVOLUCAO_COMPRA
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, N.DEVOLUCAO_COMPRA, ids, usuario=usuario_gestor_a)
    efetivada = servico.efetivar(esc, usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = " ".join(
        html.unescape(
            client.get(
                reverse("fiscal_web:nfe_estornar", args=[empresa.pk, efetivada.pk])
            ).content.decode("utf-8")
        ).split()
    )

    assert "A compra não compõe a receita: o estorno não muda a receita do mês" in texto
    assert "Receita bruta da escrituração" not in texto
    assert "Ela sai da receita do mês" not in texto
