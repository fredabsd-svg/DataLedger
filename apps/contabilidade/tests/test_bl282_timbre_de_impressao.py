"""BL-282 (M6 da auditoria DL-026, rodada 1, docs/projeto/backlog.md):
até esta correção, a impressão do Balancete, do Diário e do Razão saía
limpa e legível E com "DataLedger." no topo — a marca de quem VENDE o
software, não a do escritório que EMITE o relatório para o cliente dele.
É o vício nacional que a pesquisa do plano nomeou.

O SERVIDOR já entregava o contrato antes desta rodada (`Escritorio.
linhas_do_timbre`, com a decisão de "se o escritório não cadastrou
timbre, usar o NOME do escritório" já resolvida lá, e `timbre_linhas` no
contexto de `diario`/`razao`/`balancete` em `views_web.py`). Esta rodada
fecha o lado da TELA: as três templates passam a incluir `timbre_linhas`
num bloco (`.timbre-impressao`) visível SÓ na impressão
(`@media print`, em `static/css/base.css`) — a marca "DataLedger."
(`.marca`, dentro de `.cabecalho__topo`) sai do papel na mesma regra.

O que este arquivo verifica, em HTML RENDERIZADO da página real (cliente
de teste do Django, URL de verdade, view de verdade) — não `context`:

1. As três telas trazem `timbre_linhas` no HTML, em ordem, dentro de
   `.timbre-impressao`.
2. Quando o escritório NÃO cadastrou timbre, a linha que aparece é o NOME
   do escritório (o contrato do servidor, `linhas_do_timbre`, chegando
   até a tela — não redecidido aqui).
3. Quando o escritório CADASTROU as três linhas de timbre, são ELAS que
   aparecem — não o nome.
4. Prova por mutação (BL-311: sabotagem só numa CÓPIA em `tmp_path`,
   nunca no arquivo real) de que o teste realmente depende do bloco.

O que este arquivo NÃO verifica (ver o relatório da etapa para a evidência
correspondente, medida por fora da suíte, com Playwright/Chromium contra o
servidor real — §4.8/§7 da direção de arte: navegador não roda na
integração contínua deste projeto):

- Que `.marca`/`.cabecalho__topo` FICAM INVISÍVEIS na impressão — é CSS
  (`@media print`), e o cliente de teste do Django não tem motor de
  layout/CSS. Medido por fora, com `page.emulate_media("print")`.
- `@page { size: A4 }`, repetição de `<thead>` entre folhas e
  `break-inside: avoid` em `<tr>` — as três são comportamento de
  PAGINAÇÃO, que só um motor de impressão real decide. Medido por fora,
  com `page.pdf(format="A4")` contra o servidor real e a base sintética de
  73 contas.

Dados 100% sintéticos, criados nos próprios testes.
"""

import copy
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

_RAIZ_TEMPLATES = Path(__file__).resolve().parents[3] / "templates"


@pytest.fixture
def cen_sem_timbre():
    """Escritório SEM nenhum campo de timbre preenchido — `linhas_do_timbre`
    cai no NOME do escritório (contrato do servidor, não redecidido aqui)."""
    escritorio = Escritorio.objects.create(
        nome="Escritório BL-282 Sem Timbre", cnpj="55555555000155"
    )
    return _cenario_comum(escritorio, sufixo="a")


@pytest.fixture
def cen_com_timbre():
    """Escritório com os três campos de timbre preenchidos."""
    escritorio = Escritorio.objects.create(
        nome="Nome interno, não deve aparecer no timbre",
        cnpj="55566677000133",
        razao_social_no_timbre="Contabilidade Exemplo Ltda ME",
        endereco_no_timbre="Rua das Flores, 123 — Centro — Exemplópolis/TO",
        registro_no_timbre="CRC-TO 001234/O-5",
    )
    return _cenario_comum(escritorio, sufixo="b")


_CNPJS_POR_SUFIXO = {"a": "55566677000188", "b": "55566677000269"}


def _cenario_comum(escritorio, *, sufixo):
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social=f"Empresa BL-282-{sufixo} Ltda",
        cnpj=_CNPJS_POR_SUFIXO[sufixo],
    )
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
    usuario = get_user_model().objects.create_user(
        username=f"gestora-bl282-{sufixo}",
        email=f"gestora-bl282-{sufixo}@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="BL-282 — movimento para o período aparecer",
        itens=[
            {"conta": ativo, "tipo": "debito", "valor": Decimal("300.00")},
            {"conta": receita, "tipo": "credito", "valor": Decimal("300.00")},
        ],
        criado_por=None,
        chave_idempotencia=f"k-bl282-{sufixo}",
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "ativo": ativo,
        "receita": receita,
        "usuario": usuario.username,
    }


def _login(client, cen):
    assert client.login(username=cen["usuario"], password="senha-forte-123")


def _urls(cen):
    hoje = timezone.localdate()
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()
    empresa_id = cen["empresa"].id
    return {
        "balancete": (
            reverse("contabilidade_web:balancete", args=[empresa_id])
            + f"?inicio={inicio}&fim={fim}"
        ),
        "diario": (
            reverse("contabilidade_web:diario", args=[empresa_id]) + f"?inicio={inicio}&fim={fim}"
        ),
        "razao": (
            reverse("contabilidade_web:razao", args=[empresa_id, cen["ativo"].id])
            + f"?inicio={inicio}&fim={fim}"
        ),
    }


def _bloco_timbre(html):
    """Extrai o conteúdo de `.timbre-impressao` do HTML renderizado — sem
    parser de HTML completo, no mesmo estilo do resto da suíte
    (`apps.core.marcacao`, `_extrair_valores_ptbr`): procura a `<div
    class="timbre-impressao">` e devolve tudo até o `</div>` que a fecha.
    Como o bloco não tem `<div>` aninhada dentro (só `<p>`), o PRIMEIRO
    `</div>` depois da abertura já é o fechamento certo.
    """
    marcador = '<div class="timbre-impressao">'
    inicio = html.index(marcador)
    fim = html.index("</div>", inicio)
    return html[inicio:fim]


def _paragrafos(bloco_timbre):
    import re

    return [m.strip() for m in re.findall(r"<p>(.*?)</p>", bloco_timbre, re.DOTALL)]


@pytest.mark.parametrize("tela", ["balancete", "diario", "razao"])
def test_timbre_cai_no_nome_do_escritorio_quando_nao_ha_timbre_cadastrado(
    client, cen_sem_timbre, tela
):
    _login(client, cen_sem_timbre)
    resposta = client.get(_urls(cen_sem_timbre)[tela])
    assert resposta.status_code == 200
    paragrafos = _paragrafos(_bloco_timbre(resposta.content.decode()))
    assert paragrafos == [cen_sem_timbre["escritorio"].nome], (tela, paragrafos)


@pytest.mark.parametrize("tela", ["balancete", "diario", "razao"])
def test_timbre_mostra_as_tres_linhas_cadastradas_na_ordem(client, cen_com_timbre, tela):
    _login(client, cen_com_timbre)
    resposta = client.get(_urls(cen_com_timbre)[tela])
    assert resposta.status_code == 200
    paragrafos = _paragrafos(_bloco_timbre(resposta.content.decode()))
    assert paragrafos == [
        "Contabilidade Exemplo Ltda ME",
        "Rua das Flores, 123 — Centro — Exemplópolis/TO",
        "CRC-TO 001234/O-5",
    ], (tela, paragrafos)
    # Controle: o NOME interno do escritório (usado em outras faixas da
    # tela, como "Escritório ativo") não pode vazar para dentro do
    # timbre — são dois textos DIFERENTES de propósito, no fixture.
    assert "Nome interno" not in "".join(paragrafos)


def test_timbre_nunca_e_o_texto_dataledger(client, cen_com_timbre):
    """Controle direto contra a causa do BL-282: nenhuma linha do timbre
    é a marca do fornecedor — o bloco existe para SUBSTITUÍ-LA, não para
    repeti-la."""
    _login(client, cen_com_timbre)
    resposta = client.get(_urls(cen_com_timbre)["balancete"])
    paragrafos = _paragrafos(_bloco_timbre(resposta.content.decode()))
    assert all("DataLedger" not in p for p in paragrafos), paragrafos


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: cópia isolada em tmp_path, nunca o arquivo
# real — mesmo padrão de test_bl281_natureza_cadastrada_no_balancete.py e
# de test_dl024_veredito_no_html_renderizado.py).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tela,caminho_relativo",
    [
        ("balancete", "contabilidade/balancete.html"),
        ("diario", "contabilidade/diario.html"),
        ("razao", "contabilidade/razao.html"),
    ],
)
def test_mutacao_remover_o_bloco_de_timbre_faz_o_teste_morrer(
    client, cen_sem_timbre, tmp_path, tela, caminho_relativo
):
    """Remove, só numa CÓPIA de `templates/`, o bloco `.timbre-impressao`
    inteiro (as três linhas: abertura da `<div>`, o `{% for %}` e o
    fechamento) — reproduzindo o estado ANTES desta correção, em que a
    tela nunca expunha `timbre_linhas` nenhuma. Prova que os testes acima
    dependem de fato do bloco, não de uma coincidência de texto."""
    caminho_real = _RAIZ_TEMPLATES / caminho_relativo
    conteudo_antes = caminho_real.read_text(encoding="utf-8")

    marcador_abertura = '<div class="timbre-impressao">'
    assert marcador_abertura in conteudo_antes, (
        f"controle: marcador de abertura do timbre não encontrado em {caminho_relativo}"
    )
    inicio = conteudo_antes.index(marcador_abertura)
    fim = conteudo_antes.index("</div>", inicio) + len("</div>")
    conteudo_mutado = conteudo_antes[:inicio] + conteudo_antes[fim:]
    assert conteudo_mutado != conteudo_antes, "controle: a mutação precisa mudar o conteúdo"

    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)
    (raiz_copia / caminho_relativo).write_text(conteudo_mutado, encoding="utf-8")

    motor = copy.deepcopy(settings.TEMPLATES)
    assert len(motor) == 1
    motor[0]["DIRS"] = [raiz_copia]

    _login(client, cen_sem_timbre)
    with override_settings(TEMPLATES=motor):
        resposta = client.get(_urls(cen_sem_timbre)[tela])
        assert resposta.status_code == 200
        html = resposta.content.decode()
        assert '<div class="timbre-impressao">' not in html, (
            "a mutação deveria ter removido o bloco de timbre, e ele continua no HTML"
        )
        with pytest.raises(ValueError):
            _bloco_timbre(html)

    # Fora do override: a página volta a trazer o bloco, e o arquivo do
    # repositório nunca foi escrito.
    resposta_normal = client.get(_urls(cen_sem_timbre)[tela])
    assert '<div class="timbre-impressao">' in resposta_normal.content.decode()
    assert caminho_real.read_text(encoding="utf-8") == conteudo_antes
