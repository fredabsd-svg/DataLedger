"""BL-199 e BL-213 — o que um caminho de RECUSA da tela de lançamento
devolve, e o `action` que os dois formulários declaram.

## Por que este arquivo existe

O inventário de 2026-09-15 mediu que `_linhas_a_reexibir_do_post`
(`views_web.py:1096`) e `_recusa_lancamento_com_erro` (`:1125`) **não eram
referenciados por nenhum teste do repositório**, e que nenhum teste enviava
8 linhas para conferir que voltavam 8. O comportamento existia e nada o
protegia — que é a definição de "código sem teste" desta etapa.

E o BL-213 é o subtipo mais perigoso da família de comentários falsos: o
docstring de `_mensagem_de_tela_para_dado_nao_contratado` (`:1248`) afirma
que os dois formulários declaram `action` explícito "(ver os templates, **e
o teste que lê o atributo**)". Os templates têm o atributo; **o teste não
existia**. Um comentário que cita a própria prova de que é verdadeiro
*impede* que alguém vá conferir — foi exatamente assim que a BL-212 nasceu.

## As duas formas de teste usadas aqui, e por quê

1. **Pelo efeito, não pela forma.** O teste do `action` não se contenta em
   procurar `action=` no HTML: ele **lê o atributo** com um parser de HTML
   e depois **usa a regra do HTML** (formulário sem `action` envia para a
   URL do próprio documento, querystring incluída) para descobrir para onde
   o navegador enviaria, e POSTa lá. Com o `action` removido do template, o
   destino passa a levar a querystring de volta, a tela recusa (com razão —
   R5-6/BL-145) e o teste falha. Medir só a presença do texto `action=`
   deixaria passar um `action` que carregasse querystring.
2. **Pela requisição, nunca por `RequestFactory`.** Toda recusa aqui é
   medida por `client.post` na view de verdade, com sessão e permissão —
   porque o defeito do BL-199 foi medido na tela, não na função.

Dados 100% sintéticos, criados nos próprios testes.
"""

from html.parser import HTMLParser
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import (
    Conta,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-199", cnpj="77777777000177")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-199 Ltda", cnpj="77788899000155"
    )
    caixa = Conta.objects.create(
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
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl152", email="gestora-bl152@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _autenticar(client):
    assert client.login(username="gestora-bl152", password=SENHA)


def _url_lancamento(cenario):
    return reverse("contabilidade_web:lancamento_novo", args=[cenario["empresa"].id])


# Oito linhas, balanceadas entre si (4 débitos e 4 créditos de 11,00 a
# 88,00). Os valores são DISTINTOS de propósito: um teste que procurasse
# "11,00" oito vezes não distinguiria "voltaram as 8 linhas" de "voltou a
# primeira linha oito vezes".
VALORES_DAS_OITO_LINHAS = ["11,00", "22,00", "33,00", "44,00", "44,00", "33,00", "22,00", "11,00"]


def _post_de_oito_linhas(cenario, **extras):
    dados = {
        "acao": "gravar",
        "num_linhas": "8",
        "data": timezone.localdate().isoformat(),
        "historico": "BL-199: oito linhas enviadas",
        "chave_idempotencia": "bl152-oito-linhas",
    }
    for indice, valor in enumerate(VALORES_DAS_OITO_LINHAS, start=1):
        e_debito = indice <= 4
        dados[f"conta_{indice}"] = str((cenario["caixa"] if e_debito else cenario["receita"]).id)
        dados[f"tipo_{indice}"] = "debito" if e_debito else "credito"
        dados[f"valor_{indice}"] = valor
    dados.update(extras)
    return dados


def _linhas_reexibidas(resposta):
    """As linhas que a resposta de fato devolveu, lidas do contexto de
    renderização — `(indice, conta_id, tipo, valor_texto)` por linha."""
    return [
        (linha["indice"], linha["conta_id"], linha["tipo"], linha["valor_texto"])
        for linha in resposta.context["linhas"]
    ]


# ---------------------------------------------------------------------------
# BL-199 — as 8 linhas enviadas voltam as 8, COM VALORES, em TODOS os
# quatro dicionários que `_recusa_lancamento_com_erro` recusa
# ---------------------------------------------------------------------------


def test_recusa_por_campo_desconhecido_devolve_as_oito_linhas_com_valores(client, cenario):
    """O critério do BL-199, literal: **8 linhas enviadas voltam as 8, com
    valores.**

    Medido pelo auditor na rodada 6: voltavam 4, porque
    `_recusa_lancamento_com_erro` passava `LINHAS_INICIAIS_LANCAMENTO` (4)
    fixo. As 4 últimas o contador digitava de novo — numa função cujo
    docstring promete devolver "tudo o que já estava preenchido".
    """
    _autenticar(client)

    resposta = client.post(
        _url_lancamento(cenario), _post_de_oito_linhas(cenario, campo_que_ninguem_le="x")
    )

    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    linhas = _linhas_reexibidas(resposta)
    assert len(linhas) == 8, linhas
    # Cada linha volta com os TRÊS campos que o contador digitou, na ordem.
    for indice, valor in enumerate(VALORES_DAS_OITO_LINHAS, start=1):
        e_debito = indice <= 4
        conta_esperada = str((cenario["caixa"] if e_debito else cenario["receita"]).id)
        assert linhas[indice - 1] == (
            indice,
            conta_esperada,
            "debito" if e_debito else "credito",
            valor,
        ), linhas
    # E o HTML entregue de fato carrega o valor da OITAVA linha — não só o
    # contexto. Sem isto, um template que ignorasse `linha.valor_texto`
    # passaria.
    html = resposta.content.decode()
    assert 'name="valor_8" value="11,00"' in html
    assert 'name="valor_5" value="44,00"' in html


@pytest.mark.parametrize(
    "dicionario,montar",
    [
        ("corpo", lambda dados: (dados, {})),
        (
            "arquivo",
            # `valor_3` enviado como ARQUIVO: o mesmo dicionário do A3/BL-128,
            # que fazia um par de partidas completo desaparecer da tela e do
            # total com 302 de "sucesso".
            lambda dados: ({**dados, "valor_3": BytesIO(b"33,00")}, {}),
        ),
        ("cabecalho", lambda dados: (dados, {"HTTP_IDEMPOTENCY_KEY": "chave-da-api"})),
    ],
)
def test_todos_os_caminhos_de_recusa_devolvem_as_oito_linhas(client, cenario, dicionario, montar):
    """DE-034, item 1 — a varredura não para no dicionário medido: os
    QUATRO dicionários que esta tela recusa por completo passam pelo MESMO
    `_recusa_lancamento_com_erro`, então os quatro precisam devolver as 8
    linhas. Um único ponto de derivação é o que torna isso verdade, e é o
    que este teste trava.

    A querystring tem teste próprio abaixo (`test_recusa_por_querystring
    _devolve_as_oito_linhas`), porque montá-la exige mexer na URL, não no
    corpo.
    """
    _autenticar(client)
    dados = _post_de_oito_linhas(cenario)
    if dicionario == "corpo":
        dados["campo_que_ninguem_le"] = "x"
    corpo, cabecalhos = montar(dados)

    resposta = client.post(_url_lancamento(cenario), corpo, **cabecalhos)

    assert resposta.status_code == 400, dicionario
    assert LancamentoContabil.objects.count() == 0
    linhas = _linhas_reexibidas(resposta)
    assert len(linhas) == 8, (dicionario, linhas)
    # O valor da última linha continua na resposta — a prova de que nenhuma
    # das quatro recusas trunca em 4.
    assert linhas[7][3] == "11,00", (dicionario, linhas)


def test_recusa_por_querystring_devolve_as_oito_linhas(client, cenario):
    """O quarto dicionário. A recusa de parâmetro de URL num POST está
    correta e é mantida (R5-6/BL-145) — o que este teste exige é que ela
    também não perca linha."""
    _autenticar(client)

    resposta = client.post(
        f"{_url_lancamento(cenario)}?utm_source=email", _post_de_oito_linhas(cenario)
    )

    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    linhas = _linhas_reexibidas(resposta)
    assert len(linhas) == 8, linhas
    assert linhas[7][3] == "11,00", linhas


def test_recusa_por_indice_nao_canonico_nao_perde_as_linhas_alem_do_campo_oculto(client, cenario):
    """DE-034, item 1, no vizinho de dentro da MESMA view: a recusa por
    índice não canônico (R3-2/BL-116) re-renderiza o formulário por outro
    caminho, e ela também não pode perder linha.

    O POST desta medição é o caso realista: o campo oculto `num_linhas`
    diz 4 (a tela tinha 4 linhas), o contador acrescentou linhas à mão ou
    por "+ linha" e o POST traz 8 — mais uma chave com índice malformado.
    Quem derivar o número de linhas a re-exibir do campo OCULTO devolve 4
    e perde as outras 4; quem derivar do CONTEÚDO devolve 8.
    """
    _autenticar(client)
    dados = _post_de_oito_linhas(cenario)
    dados["num_linhas"] = "4"
    dados["conta_0008"] = str(cenario["caixa"].id)

    resposta = client.post(_url_lancamento(cenario), dados)

    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    assert "índice de linha fora do formato esperado" in resposta.content.decode()
    linhas = _linhas_reexibidas(resposta)
    assert len(linhas) == 8, linhas
    assert linhas[7][3] == "11,00", linhas


def test_recusa_por_num_linhas_acima_do_teto_de_seguranca_nao_perde_linhas(client, cenario):
    """O terceiro caminho de recusa da mesma view (R3-1/BL-115): campo
    oculto `num_linhas` acima do teto de SEGURANÇA. Ele também passou a usar
    o ponto único de derivação, e por isso devolve as 8 linhas digitadas —
    antes devolvia 4.

    E a defesa da BL-115 continua valendo, porque a derivação **não olha o
    campo oculto**: o que dimensiona a página aqui é o conteúdo do POST (8
    linhas), nunca o `num_linhas` absurdo que acabou de ser recusado.
    """
    _autenticar(client)
    dados = _post_de_oito_linhas(cenario)
    dados["num_linhas"] = str(views_web.LINHAS_LEITURA_TETO_DE_SEGURANCA + 1)

    resposta = client.post(_url_lancamento(cenario), dados)

    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    # O apóstrofo em volta de `num_linhas` sai escapado no HTML; o que
    # importa é que a recusa foi ESTA, e não outra.
    assert "inválido: o formulário aceita no máximo" in resposta.content.decode()
    linhas = _linhas_reexibidas(resposta)
    assert len(linhas) == 8, linhas
    assert [linha[3] for linha in linhas] == VALORES_DAS_OITO_LINHAS, linhas


def test_piso_de_reexibicao_e_o_da_tela_INICIAL_e_nao_o_da_gravacao(client, cenario):
    """A decisão do resíduo do BL-199, travada por teste.

    O piso de `_linhas_a_reexibir_do_post` é `LINHAS_INICIAIS_LANCAMENTO`
    (4) e o do caminho de gravação é 2 (`views_web.py`,
    `num_linhas_exibicao`). O docstring dizia que "a derivação é a MESMA"
    — a FORMA é, o piso não era, e a frase foi corrigida em vez de o piso.
    A razão está no docstring da função, e a consequência observável é
    esta: um formulário RECUSADO nunca volta oferecendo MENOS linhas do
    que um formulário novo.

    Nada digitado se perde em nenhum dos dois pisos — o piso só acrescenta
    linha EM BRANCO —, e é isso que a segunda metade do teste afirma.
    """
    _autenticar(client)
    dados = {
        "acao": "gravar",
        "num_linhas": "2",
        "data": timezone.localdate().isoformat(),
        "historico": "BL-199: piso de reexibição",
        "chave_idempotencia": "bl152-piso",
        "conta_1": str(cenario["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "10,00",
        "conta_2": str(cenario["receita"].id),
        "tipo_2": "credito",
        "valor_2": "10,00",
        "campo_que_ninguem_le": "x",
    }

    resposta = client.post(_url_lancamento(cenario), dados)

    assert resposta.status_code == 400
    linhas = _linhas_reexibidas(resposta)
    assert len(linhas) == views_web.LINHAS_INICIAIS_LANCAMENTO == 4, linhas
    # As duas linhas digitadas voltam com valor; as duas do piso vêm em
    # branco — piso acrescenta, nunca substitui.
    assert [linha[3] for linha in linhas] == ["10,00", "10,00", "", ""], linhas


# ---------------------------------------------------------------------------
# BL-213 — o teste que o comentário de `views_web.py:1248` cita, e que não
# existia
# ---------------------------------------------------------------------------


class _LeitorDeFormularios(HTMLParser):
    """Lê, de cada `<form method="post">` do documento, o atributo `action`
    e os NOMES dos campos que ele emite.

    Um parser de HTML, e não uma expressão regular sobre o texto: o que o
    comentário afirma é sobre o ATRIBUTO (existe? tem querystring?), e
    procurar a string `action=` no fonte responderia "sim" até para um
    `action` dentro de um comentário `{% comment %}` do template — a mesma
    armadilha que fez o teste da BL-146 nunca conseguir falhar.
    `action=None` quando o atributo está AUSENTE, que é o caso que importa.

    Os nomes dos campos são lidos porque toda tela do sistema traz também o
    formulário de SAIR do `base.html` (um `<form method="post">` para
    `/logout/`, correto por não ser `GET`): o formulário DESTA tela é
    identificado pelos campos que ele emite, nunca pela ordem em que
    aparece no documento nem pelo `action` — identificar pelo `action`
    tornaria o teste circular, já que é o `action` que está sendo medido.
    """

    def __init__(self):
        super().__init__()
        self.formularios = []
        self._atual = None

    def handle_starttag(self, tag, atributos):
        atributos = dict(atributos)
        if tag == "form":
            if (atributos.get("method") or "").lower() == "post":
                self._atual = {"action": atributos.get("action"), "campos": set()}
                self.formularios.append(self._atual)
            else:
                self._atual = None
            return
        if self._atual is not None and tag in ("input", "select", "textarea", "button"):
            nome = atributos.get("name")
            if nome:
                self._atual["campos"].add(nome)

    def handle_endtag(self, tag):
        if tag == "form":
            self._atual = None


def _formulario_da_tela(html, campo_exclusivo):
    """O `<form method="post">` desta tela, identificado por um campo que só
    ela emite (`num_linhas` na tela de lançamento, `codigo` na de conta)."""
    leitor = _LeitorDeFormularios()
    leitor.feed(html)
    candidatos = [f for f in leitor.formularios if campo_exclusivo in f["campos"]]
    assert len(candidatos) == 1, (
        f"esperava exatamente um <form method=post> emitindo {campo_exclusivo!r}; "
        f"achei {[sorted(f['campos']) for f in leitor.formularios]}"
    )
    return candidatos[0]


@pytest.mark.parametrize(
    "rota,campo_exclusivo",
    [
        ("contabilidade_web:lancamento_novo", "num_linhas"),
        ("contabilidade_web:conta_nova", "codigo"),
    ],
    ids=["lancamento", "conta"],
)
def test_os_dois_formularios_declaram_action_explicito_e_sem_querystring(
    client, cenario, rota, campo_exclusivo
):
    """Metade 1 do BL-213: o atributo existe, aponta para a própria rota e
    **não** carrega querystring — mesmo quando a tela foi aberta por uma
    URL que tem uma.

    Sem `action`, um `<form>` envia para a URL do documento, querystring
    incluída, e esta tela recusa parâmetro de URL num POST: quem abrisse a
    tela por um link com `?utm_source=...` não conseguia gravar. É o achado
    R6-5 do auditor.
    """
    _autenticar(client)
    endereco = reverse(rota, args=[cenario["empresa"].id])

    resposta = client.get(f"{endereco}?utm_source=email&marcador=salvo")

    assert resposta.status_code == 200
    action = _formulario_da_tela(resposta.content.decode(), campo_exclusivo)["action"]
    assert action is not None, (
        "o <form> não declara `action`: sem ele o navegador reenvia a "
        "querystring da URL do documento no POST, e esta tela recusa "
        "parâmetro de URL (R6-5/BL-199, BL-213)"
    )
    assert action == endereco, action
    assert "?" not in action, action


def test_formulario_aberto_com_querystring_consegue_gravar(client, cenario):
    """Metade 2, e a que mede o EFEITO: o contador abre a tela por um link
    com `?utm_source=email`, envia o formulário **para onde o navegador
    enviaria**, e o lançamento GRAVA.

    `_destino_do_formulario` aplica a regra do HTML explicitamente
    (formulário sem `action` envia para a URL do documento, querystring
    incluída). Com o `action` removido do template, o destino volta a
    carregar `?utm_source=email`, a tela recusa com 400 e este teste falha
    — é o que torna a frase do comentário conferível pelo efeito, não pela
    presença de um atributo.
    """
    _autenticar(client)
    endereco = reverse("contabilidade_web:lancamento_novo", args=[cenario["empresa"].id])
    documento = f"{endereco}?utm_source=email"

    resposta_get = client.get(documento)
    action = _formulario_da_tela(resposta_get.content.decode(), "num_linhas")["action"]
    destino = action if action is not None else documento

    resposta = client.post(
        destino,
        {
            "acao": "gravar",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "BL-213: gravado a partir de tela aberta com querystring",
            "chave_idempotencia": "bl166-querystring",
            "conta_1": str(cenario["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "10,00",
            "conta_2": str(cenario["receita"].id),
            "tipo_2": "credito",
            "valor_2": "10,00",
        },
    )

    assert resposta.status_code == 302, resposta.content.decode()[:600]
    assert LancamentoContabil.objects.count() == 1
