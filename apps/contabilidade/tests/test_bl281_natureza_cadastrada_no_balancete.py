"""BL-281 (M5 da auditoria DL-026, rodada 1,
docs/projeto/backlog.md): os parênteses de saldo invertido (DE-053/RC-90)
só existiam no Razão, porque só o Razão tinha a conta CADASTRADA no
contexto de cada linha (`conta` vem da própria URL). O Balancete tinha
apenas o sinal COMPUTADO (`saldo_final_natureza`) — uma conta `1 ATIVO`
(devedora) com saldo `13.366,61 C` saía sem marcação nenhuma, exatamente
onde o contador procura anomalia.

Prova de onde vem a natureza cadastrada (pedida pelo arquiteto-senior):
`apps/contabilidade/services.py`, função `apurar_balancete`, linha ~1100
(`"natureza": conta.natureza`) — o comentário imediatamente acima (linhas
~1088-1099) já documentava que este campo é "Natureza CADASTRADA da conta
(`Conta.natureza`) — exposta aqui só para permitir à VIEW converter
saldo_anterior/saldo_final [...] em valor absoluto + natureza APURADA". A
view (`apps/contabilidade/views_web.py::balancete`) já CONSUMIA esse valor
para calcular a natureza apurada via `_saldo_absoluto_com_natureza`; só não
REPASSAVA para o contexto de cada linha — isso já estava corrigido no
servidor quando esta rodada começou (a onda anterior deixou escrito, no
comentário original deste arquivo, exatamente quais asserções de HTML
precisavam ser acrescentadas aqui quando o TEMPLATE passasse a incluir
`_saldo.html`).

Esta rodada fecha a lacuna do lado do TEMPLATE:
`templates/contabilidade/balancete.html` passa a incluir
`templates/contabilidade/_saldo.html` nas colunas de saldo anterior e de
saldo final — a MESMA parcial que o Razão já usava —, passando
`conta=linha.conta` (o dicionário `{"natureza": ...}` que a view expõe por
linha).

Os testes ORIGINAIS abaixo (a-e) continuam verificando o CONTEXTO
(`response.context["linhas"]`) — é a fronteira certa para provar que o
SERVIDOR decide certo. Os testes NOVOS (a partir de
`test_balancete_renderizado_...`) verificam o HTML RENDERIZADO da página
real (cliente de teste do Django, URL de verdade, view de verdade) — é a
fronteira que faltava: o achado repetido desta etapa (e desta mesma classe
de defeito em `test_dl024_veredito_no_html_renderizado.py`, do
arquiteto-senior) é que testar só o contexto prova que a DECISÃO está
certa, não que ela CHEGA à tela. Cobertura mínima pedida: conta devedora
com saldo credor TEM parênteses; conta devedora com saldo devedor NÃO TEM;
o mesmo par, espelhado, para conta credora; saldo zero não ganha marcação.

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

# Raiz de `templates/` do repositório — usada só pela prova por mutação lá
# embaixo, que copia a árvore para `tmp_path` (BL-311: nunca escreve no
# arquivo real; ver o docstring de `_mutacao_reverte_inclusao_da_parcial`
# e o mesmo padrão em
# apps/contabilidade/tests/test_dl024_veredito_no_html_renderizado.py,
# escrito para fechar exatamente este risco — corrupção acumulativa da
# árvore real sob execução concorrente).
_RAIZ_TEMPLATES = Path(__file__).resolve().parents[3] / "templates"
_CAMINHO_BALANCETE = _RAIZ_TEMPLATES / "contabilidade" / "balancete.html"


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório BL-281", cnpj="55555555000155")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-281 Ltda", cnpj="55566677000188"
    )
    ativo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    passivo = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=NaturezaConta.CREDORA,
    )
    # Contrapartida usada só para fechar as partidas dobradas dos
    # lançamentos abaixo — não é asserida em nenhum teste.
    contrapartida = Conta.objects.create(
        empresa=empresa,
        codigo="3",
        nome="Diversos",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    # Conta SEM nenhum lançamento no período: saldo zero, para o caso (d).
    conta_zero = Conta.objects.create(
        empresa=empresa,
        codigo="4",
        nome="Sem movimento",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl281",
        email="gestora-bl281@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "ativo": ativo,
        "passivo": passivo,
        "contrapartida": contrapartida,
        "conta_zero": conta_zero,
    }


def _login(client):
    assert client.login(username="gestora-bl281", password="senha-forte-123")


def _url(cen):
    hoje = timezone.localdate()
    base = reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
    return f"{base}?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"


def _linha(resposta, codigo):
    for linha in resposta.context["linhas"]:
        if linha["codigo"] == codigo:
            return linha
    raise AssertionError(f"conta {codigo!r} não apareceu em response.context['linhas']")


def test_conta_devedora_com_saldo_credor_sai_marcada_como_invertida(client, cen):
    """(a): crédito lançado numa conta ATIVO (devedora) sem débito
    correspondente inverte o saldo apurado para credor — a marcação de
    parênteses (RC-90) precisa ser possível: `conta.natureza` cadastrada
    ("devedora") diverge da letra apurada ("C")."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo invertido em conta devedora",
        itens=[
            {"conta": cen["contrapartida"], "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": cen["ativo"], "tipo": "credito", "valor": Decimal("100.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-a",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "1")
    assert linha["conta"]["natureza"] == "devedora"
    assert linha["saldo_final_natureza"]["letra"] == "C"


def test_conta_devedora_com_saldo_devedor_sai_sem_marcacao(client, cen):
    """(b): débito líquido numa conta devedora é o lado NORMAL — a letra
    apurada bate com a cadastrada, então `_saldo.html` não deve marcar
    parênteses quando a próxima onda incluir a parcial aqui."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo normal em conta devedora",
        itens=[
            {"conta": cen["ativo"], "tipo": "debito", "valor": Decimal("200.00")},
            {"conta": cen["contrapartida"], "tipo": "credito", "valor": Decimal("200.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-b",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "1")
    assert linha["conta"]["natureza"] == "devedora"
    assert linha["saldo_final_natureza"]["letra"] == "D"


def test_conta_credora_com_saldo_devedor_sai_marcada_como_invertida(client, cen):
    """(c): espelho de (a) — débito lançado numa conta PASSIVO (credora)
    sem crédito correspondente inverte o saldo apurado para devedor."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo invertido em conta credora",
        itens=[
            {"conta": cen["passivo"], "tipo": "debito", "valor": Decimal("150.00")},
            {"conta": cen["contrapartida"], "tipo": "credito", "valor": Decimal("150.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-c",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "2")
    assert linha["conta"]["natureza"] == "credora"
    assert linha["saldo_final_natureza"]["letra"] == "D"


def test_conta_credora_com_saldo_credor_sai_sem_marcacao(client, cen):
    """(c espelhado/normal): crédito líquido numa conta credora é o lado
    NORMAL — sem marcação."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo normal em conta credora",
        itens=[
            {"conta": cen["contrapartida"], "tipo": "debito", "valor": Decimal("250.00")},
            {"conta": cen["passivo"], "tipo": "credito", "valor": Decimal("250.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-d",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "2")
    assert linha["conta"]["natureza"] == "credora"
    assert linha["saldo_final_natureza"]["letra"] == "C"


def test_saldo_zero_nao_recebe_natureza_apurada(client, cen):
    """(d): sem nenhum lançamento no período, o saldo é zero — RC-61 diz
    que zero não tem lado. `saldo_final_natureza` precisa ser `None`
    (mesma regra que já protege o Razão), o que faz `_saldo.html` nunca
    alcançar a comparação com `conta.natureza` nesse caso — a marcação de
    invertido não depende de `conta` ter valor válido quando o saldo é
    zero. `conta.natureza` continua exposta (é a cadastrada da conta), só
    não é ela quem decide aqui."""
    _login(client)
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "4")
    assert linha["conta"]["natureza"] == "devedora"
    assert linha["saldo_final_natureza"] is None


def test_natureza_cadastrada_do_contexto_bate_com_a_conta_no_banco(client, cen):
    """Controle direto contra a causa do BL-281: o valor exposto em
    `linha["conta"]["natureza"]` é a mesma string gravada em
    `Conta.natureza` — não um valor recalculado ou copiado do saldo
    apurado (que poderia coincidir por acaso em alguns casos e mascarar
    uma regressão)."""
    _login(client)
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    for codigo, conta in (("1", cen["ativo"]), ("2", cen["passivo"])):
        linha = _linha(resposta, codigo)
        assert linha["conta"]["natureza"] == conta.natureza


# ---------------------------------------------------------------------------
# HTML renderizado da página real — a parte que faltava (ver o docstring do
# módulo). `_linha_do_html`/`_celula_saldo_final` isolam a célula certa
# dentro da linha certa, sem depender de `response.context`: o mesmo texto
# que o cliente de teste do Django recebeu é o mesmo que o navegador do
# contador recebe.
# ---------------------------------------------------------------------------


def _linha_do_html(html, codigo):
    """A `<tr>` cuja primeira célula de dado (`<td>{codigo}</td>`, a coluna
    "Código" — a coluna "Nível" vem antes, sem valor fixo por conta) é o
    código da conta pedida. `str.index`/`rfind` bastam: os códigos usados
    nestes testes ("1" a "4") são curtos e únicos na tabela, e a MESMA
    técnica de "andar a partir de um marcador de texto" já é usada por
    `test_dl024_veredito_no_html_renderizado.py` para extrair fragmento de
    template — aqui aplicada a HTML já renderizado, não ao arquivo fonte.
    """
    marcador = f"<td>{codigo}</td>"
    inicio_marcador = html.index(marcador)
    inicio_linha = html.rfind("<tr>", 0, inicio_marcador)
    assert inicio_linha != -1, f"nenhuma <tr> encontrada antes da conta {codigo!r}"
    fim_linha = html.index("</tr>", inicio_marcador) + len("</tr>")
    return html[inicio_linha:fim_linha]


def _celula_saldo_final(linha_html):
    """A célula de saldo FINAL é a ÚLTIMA `<td class="valor-monetario">`
    da linha — ordem das colunas em `balancete.html`: Nível, Código, Nome,
    Saldo anterior, Débitos, Créditos, Débitos próprios, Créditos
    próprios, Saldo final (cabeçalho de duas linhas,
    `.tabela-dois-niveis`). Usar a ÚLTIMA ocorrência (não a primeira, que
    seria o Saldo anterior) é o que ancora esta função na coluna certa
    mesmo que uma coluna nova apareça entre elas no futuro — desde que
    Saldo final continue sendo a última."""
    indice = linha_html.rfind('<td class="valor-monetario">')
    assert indice != -1, f"nenhuma célula de valor encontrada na linha: {linha_html!r}"
    return linha_html[indice:]


def test_balancete_renderizado_marca_parenteses_na_conta_devedora_com_saldo_credor(client, cen):
    """(a) no HTML de verdade: a célula de SALDO FINAL da conta devedora
    com saldo credor precisa trazer `class="valor-invertido"` e o valor
    entre parênteses — a MESMA convenção que o Razão já aplica."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 HTML — saldo invertido em conta devedora",
        itens=[
            {"conta": cen["contrapartida"], "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": cen["ativo"], "tipo": "credito", "valor": Decimal("100.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-html-a",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    celula = _celula_saldo_final(_linha_do_html(resposta.content.decode(), "1"))
    assert 'class="valor-invertido"' in celula, celula
    assert "(" in celula and ")" in celula, celula


def test_balancete_renderizado_nao_marca_a_conta_devedora_com_saldo_devedor(client, cen):
    """(b): débito líquido numa conta devedora é o lado NORMAL — sem
    parênteses no HTML renderizado."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 HTML — saldo normal em conta devedora",
        itens=[
            {"conta": cen["ativo"], "tipo": "debito", "valor": Decimal("200.00")},
            {"conta": cen["contrapartida"], "tipo": "credito", "valor": Decimal("200.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-html-b",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    celula = _celula_saldo_final(_linha_do_html(resposta.content.decode(), "1"))
    assert "valor-invertido" not in celula, celula
    # A letra "D" continua aparecendo — só a marcação de invertido some.
    assert "indicador-natureza" in celula, celula


def test_balancete_renderizado_marca_parenteses_na_conta_credora_com_saldo_devedor(client, cen):
    """(c): espelho de (a) — débito lançado numa conta PASSIVO (credora)
    sem crédito correspondente inverte o saldo apurado para devedor."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 HTML — saldo invertido em conta credora",
        itens=[
            {"conta": cen["passivo"], "tipo": "debito", "valor": Decimal("150.00")},
            {"conta": cen["contrapartida"], "tipo": "credito", "valor": Decimal("150.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-html-c",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    celula = _celula_saldo_final(_linha_do_html(resposta.content.decode(), "2"))
    assert 'class="valor-invertido"' in celula, celula
    assert "(" in celula and ")" in celula, celula


def test_balancete_renderizado_nao_marca_a_conta_credora_com_saldo_credor(client, cen):
    """(d): crédito líquido numa conta credora é o lado NORMAL — sem
    parênteses no HTML renderizado."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 HTML — saldo normal em conta credora",
        itens=[
            {"conta": cen["contrapartida"], "tipo": "debito", "valor": Decimal("250.00")},
            {"conta": cen["passivo"], "tipo": "credito", "valor": Decimal("250.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-html-d",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    celula = _celula_saldo_final(_linha_do_html(resposta.content.decode(), "2"))
    assert "valor-invertido" not in celula, celula
    assert "indicador-natureza" in celula, celula


def test_balancete_renderizado_saldo_zero_nao_recebe_marcacao(client, cen):
    """(e): RC-61 — zero não tem lado. Sem lançamento nenhum na conta, a
    célula de saldo final não pode ter nem `indicador-natureza` nem
    `valor-invertido`."""
    _login(client)
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    celula = _celula_saldo_final(_linha_do_html(resposta.content.decode(), "4"))
    assert "valor-invertido" not in celula, celula
    assert "indicador-natureza" not in celula, celula


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: sabotagem só numa CÓPIA em tmp_path, nunca no
# arquivo real — o mesmo padrão de
# test_dl024_veredito_no_html_renderizado.py::_arvore_de_templates_com_mutacao,
# reaproveitado aqui de forma independente porque aquele arquivo pertence a
# outra etapa e importar dele acoplaria as duas suítes por acidente).
# ---------------------------------------------------------------------------

_MARCADOR_INCLUSAO_SALDO_FINAL = (
    '{% include "contabilidade/_saldo.html" with valor=linha.saldo_final_ptbr '
    "natureza=linha.saldo_final_natureza conta=linha.conta %}"
)


def _mutacao_reverte_inclusao_da_parcial(conteudo_original):
    """Desfaz, só no TEXTO, exatamente a mudança desta etapa na célula de
    SALDO FINAL: troca o `{% include "_saldo.html" %}` pela renderização
    ANTIGA (valor cru + indicador D/C, sem parênteses) — o estado do
    balancete ANTES desta correção, byte a byte equivalente ao que estava
    em `balancete.html` no início desta etapa."""
    assert _MARCADOR_INCLUSAO_SALDO_FINAL in conteudo_original, (
        "controle: marcador de inclusão do saldo final não encontrado no arquivo real "
        "— a mutação não pode provar nada se o marcador mudou de forma"
    )
    substituto = (
        "{{ linha.saldo_final_ptbr }}\n"
        "                            {% if linha.saldo_final_natureza %}"
        '<span class="indicador-natureza">{{ linha.saldo_final_natureza.letra }}'
        '<span class="visualmente-oculto"> ({{ linha.saldo_final_natureza.extenso }})'
        "</span></span>{% endif %}"
    )
    return conteudo_original.replace(_MARCADOR_INCLUSAO_SALDO_FINAL, substituto, 1)


def test_mutacao_reverter_a_inclusao_da_parcial_faz_o_teste_de_html_morrer(client, cen, tmp_path):
    """Prova que os testes de HTML acima (não os de contexto, que já
    existiam) dependem de fato da correção desta etapa — não de uma
    coincidência de marcação. Reverte só a célula de SALDO FINAL do
    `balancete.html`, numa CÓPIA isolada em `tmp_path` (nunca no arquivo do
    repositório — BL-311), e mostra que a marcação de invertido SOME da
    página real, mesmo com o CONTEXTO (`response.context`) continuando
    certo — exatamente a lacuna que esta rodada existe para fechar."""
    conteudo_antes = _CAMINHO_BALANCETE.read_text(encoding="utf-8")

    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)
    caminho_na_copia = raiz_copia / "contabilidade" / "balancete.html"
    conteudo_mutado = _mutacao_reverte_inclusao_da_parcial(conteudo_antes)
    assert conteudo_mutado != conteudo_antes, "controle: a mutação precisa mudar o conteúdo"
    caminho_na_copia.write_text(conteudo_mutado, encoding="utf-8")

    motor = copy.deepcopy(settings.TEMPLATES)
    assert len(motor) == 1, (
        "settings.TEMPLATES tem mais de um motor configurado; este teste precisa "
        "decidir explicitamente qual DIRS substituir"
    )
    motor[0]["DIRS"] = [raiz_copia]

    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 mutação — saldo invertido em conta devedora",
        itens=[
            {"conta": cen["contrapartida"], "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": cen["ativo"], "tipo": "credito", "valor": Decimal("100.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-mutacao",
    )

    with override_settings(TEMPLATES=motor):
        resposta = client.get(_url(cen))
        assert resposta.status_code == 200
        celula = _celula_saldo_final(_linha_do_html(resposta.content.decode(), "1"))
        assert "valor-invertido" not in celula, (
            "a mutação deveria fazer a marcação de parênteses SUMIR da célula de "
            f"saldo final, e não sumiu: {celula!r}"
        )
        # O CONTEXTO continua certo — é exatamente isto que prova que os
        # testes ORIGINAIS (que afirmam sobre response.context) não
        # pegariam esta sabotagem: a decisão do servidor está certa, só a
        # ENTREGA que regrediu.
        linha_contexto = _linha(resposta, "1")
        assert linha_contexto["conta"]["natureza"] == "devedora"
        assert linha_contexto["saldo_final_natureza"]["letra"] == "C"

    # Fora do override: a página volta a marcar, e o arquivo do
    # repositório nunca foi escrito.
    resposta_normal = client.get(_url(cen))
    assert resposta_normal.status_code == 200
    celula_normal = _celula_saldo_final(_linha_do_html(resposta_normal.content.decode(), "1"))
    assert 'class="valor-invertido"' in celula_normal, celula_normal
    assert _CAMINHO_BALANCETE.read_text(encoding="utf-8") == conteudo_antes
