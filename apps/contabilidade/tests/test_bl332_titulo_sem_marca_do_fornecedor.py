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
from apps.contabilidade.tests.test_bl329_marca_fora_do_papel import (
    _parsear_html,
    _tem_timbre_impressao,
)
from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
    NOMES_DE_TELA_DE_CONTABILIDADE,
    _urls_de_contabilidade,
)
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
    # com CONTEÚDO de verdade — o nome do relatório E a razão social do
    # cliente, nos TRÊS documentos (RC-98/F10 da auditoria DL-026, rodada
    # 6: o Razão passou a seguir o MESMO formato de Balancete/Diário — ver
    # o comentário completo em templates/contabilidade/razao.html sobre a
    # divergência anterior, declarada e revertida pelo Fred).
    assert titulo.strip() != "", (tela, titulo)
    assert cen["empresa"].razao_social in titulo, (tela, titulo)


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


# ---------------------------------------------------------------------------
# BL-344 (F2 da auditoria DL-026, rodada 6,
# docs/auditorias/2026-09-19-dl-026-rodada-6.md): a guarda ACIMA
# (`test_titulo_do_documento_nao_contem_a_marca_do_fornecedor`) é
# parametrizada por uma LISTA de três nomes escritos à mão
# (`["balancete", "diario", "razao"]`) — e o auditor mediu que uma QUARTA
# tela transformada em documento (`.timbre-impressao` no HTML, exatamente
# o que qualquer módulo novo vai fazer), ESQUECENDO de sobrescrever
# `titulo_sufixo_do_fornecedor`, imprime "— DataLedger" em toda folha com
# `1775 passed` — a suíte inteira verde.
#
# O arquivo IRMÃO escrito no MESMO DIA (test_bl338_operador_fora_do_
# papel.py) já tinha a derivação CERTA para a MESMA pergunta ("esta tela é
# documento?"): presença ESTRUTURAL de `.timbre-impressao` no HTML
# RENDERIZADO, parametrizada sobre `NOMES_DE_TELA_DE_CONTABILIDADE`. A
# guarda abaixo COMPARTILHA essa derivação — `_tem_timbre_impressao`,
# movida para test_bl329_marca_fora_do_papel.py (o módulo-base que os
# dois arquivos já importam) — em vez de duplicá-la: a propriedade é
# *"toda tela cujo HTML contém `.timbre-impressao` tem `<title>` SEM o
# nome do fornecedor; toda tela SEM `.timbre-impressao` tem `<title>` COM
# ele"*, testada sobre as OITO telas de `NOMES_DE_TELA_DE_CONTABILIDADE`
# (não só as três documentos — o controle negativo das outras cinco entra
# de graça, pela MESMA parametrização).
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_bl344():
    """Mesmo formato de `cenario_bl338`
    (test_bl338_operador_fora_do_papel.py) — escritório, empresa, duas
    contas e um lançamento — porque `_urls_de_contabilidade` (BL-334,
    test_dl024_atalhos_e_acessibilidade.py) exige `empresa`, `caixa` e
    `lancamento` para montar a URL das OITO telas de contabilidade, não
    só as três documentos que a fixture `cen` (acima) cobria."""
    escritorio = Escritorio.objects.create(nome="Escritório BL-344", cnpj="88899900000122")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-344 Ltda", cnpj="88899900000213"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl344",
        email="gestora-bl344@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    lancamento = criar_lancamento(
        empresa=empresa,
        data=timezone.localdate(),
        historico="BL-344 — movimento para as telas terem o que mostrar",
        itens=[
            {"conta": caixa, "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
        ],
        criado_por=usuario,
        chave_idempotencia="k-bl344",
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "lancamento": lancamento}


@pytest.mark.parametrize("nome_tela", sorted(NOMES_DE_TELA_DE_CONTABILIDADE))
def test_titulo_reflete_se_a_tela_e_documento_ou_produto(client, cenario_bl344, nome_tela):
    """BL-344/F2: a propriedade central, DERIVADA do HTML renderizado —
    nunca de uma lista de nomes escrita à mão. Roda sobre as OITO telas
    de `NOMES_DE_TELA_DE_CONTABILIDADE`: as três que têm timbre hoje
    (Balancete/Diário/Razão) precisam continuar sem a marca; as cinco que
    não têm (Plano de contas, Nova conta, Conferência, Novo lançamento,
    Detalhe do lançamento) precisam continuar COM ela — e uma sexta tela
    nova, futura, que ganhe timbre sem que ninguém lembre de atualizar
    esta lista, é pega pela MESMA pergunta, porque a pergunta é sobre o
    HTML, não sobre o nome da rota."""
    assert client.login(username="gestora-bl344", password="senha-forte-123")
    url = _urls_de_contabilidade(cenario_bl344)[nome_tela]
    resposta = client.get(url)
    assert resposta.status_code == 200, f"{nome_tela}: {resposta.status_code}"
    html = resposta.content.decode()

    tem_timbre = _tem_timbre_impressao(_parsear_html(html))
    titulo = _titulo_renderizado(html)
    assert titulo.strip() != "", (nome_tela, titulo)

    if tem_timbre:
        assert "DataLedger" not in titulo, (
            f"{nome_tela} TEM timbre de impressão (é DOCUMENTO), mas o <title> "
            f"continua trazendo a marca do fornecedor: {titulo!r}"
        )
    else:
        assert "DataLedger" in titulo, (
            f"{nome_tela} NÃO TEM timbre de impressão (é tela de PRODUTO), mas "
            f"o <title> perdeu a marca do fornecedor: {titulo!r}"
        )


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: sabotagem só em CÓPIA em tmp_path). Reprodução
# EXATA da sabotagem que o auditor mediu contra `lancamento_detalhe`
# (F2) — repetida também contra `conferencia`, como o critério de
# aceite pede.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_tela,caminho_relativo",
    [
        ("lancamento_detalhe", "contabilidade/lancamento_detalhe.html"),
        ("conferencia", "contabilidade/conferencia.html"),
    ],
)
def test_sabotagem_transformar_tela_em_documento_esquecendo_o_titulo_mata_a_guarda(
    client, cenario_bl344, tmp_path, nome_tela, caminho_relativo
):
    """BL-344/F2: transforma `nome_tela` numa tela de DOCUMENTO —
    ganha `.timbre-impressao` no HTML, exatamente como qualquer módulo
    novo (Fiscal, Folha, Honorários...) vai fazer — e ESQUECE de
    sobrescrever `titulo_sufixo_do_fornecedor`: a MESMA omissão que o
    auditor mediu contra `lancamento_detalhe` (e, aqui, repetida também
    contra `conferencia`, como o critério de aceite pede). Antes do
    BL-344, a guarda de título só conhecia três nomes fixos — nenhuma das
    duas telas estava nela — e a suíte ficava inteira verde com "—
    DataLedger" saindo em toda folha. Agora a propriedade acima
    (`test_titulo_reflete_se_a_tela_e_documento_ou_produto`) é DERIVADA
    do HTML: este teste prova que a MESMA condição que a sabotagem produz
    — timbre presente E marca do fornecedor no título — é exatamente a
    que faz aquela guarda REPROVAR, nomeando a tela."""
    caminho_real = _RAIZ_TEMPLATES / caminho_relativo
    conteudo_antes = caminho_real.read_text(encoding="utf-8")

    marcador = "{% block content %}"
    assert marcador in conteudo_antes, (
        f"controle: marcador de content não encontrado em {caminho_relativo}"
    )
    sobrescrita = (
        marcador + '\n    <div class="timbre-impressao"><p>Escritório sabotado (BL-344)</p></div>\n'
    )
    conteudo_mutado = conteudo_antes.replace(marcador, sobrescrita, 1)
    assert conteudo_mutado != conteudo_antes, "controle: a mutação precisa mudar o conteúdo"

    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)
    (raiz_copia / caminho_relativo).write_text(conteudo_mutado, encoding="utf-8")

    motor = copy.deepcopy(settings.TEMPLATES)
    assert len(motor) == 1
    motor[0]["DIRS"] = [raiz_copia]

    assert client.login(username="gestora-bl344", password="senha-forte-123")
    url = _urls_de_contabilidade(cenario_bl344)[nome_tela]
    with override_settings(TEMPLATES=motor):
        resposta = client.get(url)
        assert resposta.status_code == 200
        html = resposta.content.decode()
        tem_timbre = _tem_timbre_impressao(_parsear_html(html))
        assert tem_timbre, "controle: a sabotagem precisa ter introduzido .timbre-impressao"
        titulo = _titulo_renderizado(html)
        assert "DataLedger" in titulo, (
            "a sabotagem deveria ter reproduzido a omissão do achado F2 — tela "
            "transformada em documento (tem timbre) mas com o título ainda trazendo "
            f"a marca do fornecedor: {titulo!r}. Isto é EXATAMENTE o estado (tem_timbre="
            "True e 'DataLedger' in titulo) que faz "
            "test_titulo_reflete_se_a_tela_e_documento_ou_produto REPROVAR para "
            f"{nome_tela!r} — a prova de que a guarda morre, nomeando a tela."
        )

    # Fora do override: a tela volta ao normal, e o arquivo real nunca foi escrito.
    resposta_normal = client.get(url)
    titulo_normal = _titulo_renderizado(resposta_normal.content.decode())
    assert "DataLedger" in titulo_normal
    assert caminho_real.read_text(encoding="utf-8") == conteudo_antes
