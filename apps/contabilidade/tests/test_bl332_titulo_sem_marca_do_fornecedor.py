"""BL-332 (achado A2 da auditoria DL-026, rodada 5,
docs/auditorias/2026-09-19-dl-026-rodada-5.md): com as opções PADRÃO de
impressão do navegador (a caixa "Cabeçalhos e rodapés" vem MARCADA por
padrão no Chrome e no Edge), o conteúdo da tag title da página é impresso
no cabeçalho de TODA folha — e até esta correção esse conteúdo sempre
incluía " — DataLedger", a marca de quem VENDE o software, no papel que o
escritório entrega ao CLIENTE dele. Medido pelo auditor em PDF real:
"9/19/26, 1:23 PM Balancete — Comércio Sintético de Materiais Ltda —
DataLedger" no cabeçalho de todas as folhas, com a URL interna do sistema
no rodapé.

DECISÃO (Fred, 2026-09-19, RC-97), registrada em docs/projeto/backlog.md
(BL-332): o sufixo do fornecedor sai da tag title de um DOCUMENTO —
Balancete, Diário, Razão, as três telas com timbre de impressão (BL-282) —
e o título passa a ser só "nome do relatório — razão social do cliente",
sem sufixo nenhum. Para toda OUTRA tela (sem cliente no contexto — login,
painel, lista de empresas...) o sufixo continua: "DataLedger" ali é
legítimo, é a interface do PRODUTO, não um documento que sai do escritório
para o cliente. O mecanismo (`titulo_sufixo_do_fornecedor`, um segundo
bloco de `templates/base.html`, com o sufixo como PADRÃO) está comentado
por inteiro lá.

O QUE ESTE ARQUIVO VERIFICA, em HTML RENDERIZADO da página real (cliente
de teste do Django, URL de verdade, view de verdade) — a PROPRIEDADE, não
a string-fonte "— DataLedger" em nenhum template (grep de string não prova
o que o NAVEGADOR recebe; renderização prova):

1. A tag title renderizada de Balancete/Diário/Razão NÃO contém
   "DataLedger" — e continua não-vazia (contém o nome do relatório e a
   razão social da empresa), controle contra um "passa" vazio por acidente
   (título apagado por inteiro esconderia o defeito atrás de outro).
2. CONTROLE NEGATIVO: uma tela SEM cliente no contexto (aqui, o painel de
   tenancy — `tenancy:painel`, que este arquivo não edita e cuja rota
   continua herdando o comportamento PADRÃO de `templates/base.html`)
   CONTINUA com "DataLedger" na tag title — prova de que a correção não
   é uma remoção cega do sufixo em toda a aplicação, só nos DOCUMENTOS.
3. Prova por mutação (BL-311: sabotagem só em CÓPIA dentro de `tmp_path`,
   nunca no arquivo real — mesmo padrão de test_bl282_timbre_de_impressao.
   py): remover a sobrescrita do bloco `titulo_sufixo_do_fornecedor` em
   `balancete.html` faz a tela voltar a herdar o sufixo padrão do
   fornecedor — o defeito original do achado A2 — e a guarda PRECISA
   morrer nesse caso.

O QUE ESTE ARQUIVO NÃO VERIFICA — mesmo limite de
test_bl282_timbre_de_impressao.py: se o NAVEGADOR de verdade imprime o
conteúdo da tag title no cabeçalho da folha com as opções padrão do
diálogo de impressão. Isso é medido por fora, com Chromium real, por
scripts/medir_impressao.py (modo "com-cabecalho" — o único que reproduz o
achado A2; ver a docstring do módulo daquele script).

Dados sintéticos, criados nos próprios testes.
"""

import copy
import re
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

# Regex por CONTEÚDO da tag title — não string-fonte de nenhum template: o
# que este arquivo mede é o HTML que o cliente de teste RECEBE, a mesma
# distância entre "medição" e "código-fonte" que o achado A2 nomeou (o
# artefato MEDIDO precisa ser o artefato ENTREGUE).
_PADRAO_TITLE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _titulo_renderizado(html):
    m = _PADRAO_TITLE.search(html)
    assert m, "controle: nenhuma tag title encontrada no HTML renderizado"
    return m.group(1)


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório BL-332", cnpj="66677788000199")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-332 Ltda", cnpj="66677788000280"
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
        username="gestora-bl332",
        email="gestora-bl332@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="BL-332 — movimento para o período aparecer",
        itens=[
            {"conta": ativo, "tipo": "debito", "valor": Decimal("500.00")},
            {"conta": receita, "tipo": "credito", "valor": Decimal("500.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl332",
    )
    return {"escritorio": escritorio, "empresa": empresa, "ativo": ativo, "usuario": usuario}


def _login(client, cen):
    assert client.login(username=cen["usuario"].username, password="senha-forte-123")


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


# ---------------------------------------------------------------------------
# Guarda central.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tela", ["balancete", "diario", "razao"])
def test_titulo_do_documento_nao_contem_a_marca_do_fornecedor(client, cen, tela):
    _login(client, cen)
    resposta = client.get(_urls(cen)[tela])
    assert resposta.status_code == 200
    titulo = _titulo_renderizado(resposta.content.decode())
    assert "DataLedger" not in titulo, (tela, titulo)
    # Controle contra um "passa" vazio por acidente: a tag title continua
    # com CONTEÚDO de verdade — o nome do relatório e, exceto no Razão
    # (ver a decisão registrada em razao.html), a razão social do cliente.
    assert titulo.strip() != "", (tela, titulo)


def test_titulo_de_tela_sem_cliente_continua_com_a_marca_do_produto(client, cen):
    """Controle NEGATIVO: o painel (tenancy:painel, fora dos arquivos que
    esta etapa edita) não tem empresa nenhuma no contexto — é tela do
    PRODUTO, não documento do escritório — e continua herdando o sufixo
    padrão de templates/base.html. Prova que a correção do BL-332 é
    seletiva (documentos), não uma remoção cega do nome do produto em toda
    a aplicação."""
    _login(client, cen)
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    titulo = _titulo_renderizado(resposta.content.decode())
    assert "DataLedger" in titulo, titulo


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: sabotagem só em CÓPIA em tmp_path, nunca no
# arquivo real — mesmo padrão de test_bl282_timbre_de_impressao.py).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tela,caminho_relativo",
    [
        ("balancete", "contabilidade/balancete.html"),
        ("diario", "contabilidade/diario.html"),
        ("razao", "contabilidade/razao.html"),
    ],
)
def test_sabotagem_remover_a_sobrescrita_do_bloco_faz_a_marca_voltar(
    client, cen, tmp_path, tela, caminho_relativo
):
    """Remove, só numa CÓPIA de `templates/`, a sobrescrita de
    `titulo_sufixo_do_fornecedor` (o bloco inteiro, vazio, que a tela
    declara) — reproduzindo o estado ANTES desta correção, em que a tela
    herdava o sufixo " — DataLedger" do padrão de `templates/base.html`
    sem exceção nenhuma. Prova que a guarda acima depende de fato da
    sobrescrita, não de uma coincidência de texto."""
    caminho_real = _RAIZ_TEMPLATES / caminho_relativo
    conteudo_antes = caminho_real.read_text(encoding="utf-8")

    marcador = "{% block titulo_sufixo_do_fornecedor %}{% endblock %}"
    assert marcador in conteudo_antes, (
        f"controle: marcador da sobrescrita não encontrado em {caminho_relativo}"
    )
    conteudo_mutado = conteudo_antes.replace(marcador, "", 1)
    assert conteudo_mutado != conteudo_antes, "controle: a mutação precisa mudar o conteúdo"

    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)
    (raiz_copia / caminho_relativo).write_text(conteudo_mutado, encoding="utf-8")

    motor = copy.deepcopy(settings.TEMPLATES)
    assert len(motor) == 1
    motor[0]["DIRS"] = [raiz_copia]

    _login(client, cen)
    with override_settings(TEMPLATES=motor):
        resposta = client.get(_urls(cen)[tela])
        assert resposta.status_code == 200
        titulo = _titulo_renderizado(resposta.content.decode())
        assert "DataLedger" in titulo, (
            "a sabotagem deveria ter feito a marca do fornecedor VOLTAR à tag title, "
            f"e ela continuou ausente: {titulo!r}"
        )

    # Fora do override: a tela volta a não trazer a marca, e o arquivo do
    # repositório nunca foi escrito.
    resposta_normal = client.get(_urls(cen)[tela])
    titulo_normal = _titulo_renderizado(resposta_normal.content.decode())
    assert "DataLedger" not in titulo_normal
    assert caminho_real.read_text(encoding="utf-8") == conteudo_antes
