"""BL-149 (b) e BL-161 — a tela de cadastro de conta: os cinco dicionários
da requisição medidos NA VIEW, e o RC-80 (conta sem as contas-mãe).

## BL-149 (b): por que um teste de ponta a ponta, e não mais um unitário

O defeito original foi medido pelo auditor **nesta tela**: enviar `conta_pai`
como **arquivo** gravava a conta **na raiz do plano**, com 302 de sucesso e
sem uma palavra — mudando a indentação do Plano de Contas, o nível da conta
e a linha em que ela é somada no Balancete por nível.

A política dos cinco dicionários está aplicada nas nove superfícies, com 44
testes. O que o inventário de 2026-09-15 mediu faltando é justamente o teste
**de ponta a ponta em `conta_nova`**: o único teste com arquivo em
`conta_pai` é unitário, com `RequestFactory`, e **não exercita a view**. Um
teste que não passa pela view não pode provar que a view recusa — e era a
view que gravava.

Então tudo aqui é `client.post`, com sessão, permissão e banco, e cada caso
afirma as **duas** metades: a resposta (400, nomeando o campo) e o **efeito**
(nada gravado). O controle positivo — um POST legítimo que GRAVA — está no
mesmo bloco, porque sem ele um `conta_nova` que recusasse tudo passaria em
todos os casos negativos.

## BL-161: o RC-80 tem DUAS metades, e a segunda é a escolha do Fred

> **RC-80 — conta sem as contas-mãe: avisar e deixar criar.**

O Fred escolheu isso explicitamente **contra** a alternativa de recusar.
Então as duas metades precisam de teste: **avisa** (a primeira tentativa não
grava, volta com o aviso, os dados preenchidos e um botão que diz o que vai
acontecer) e **deixa criar quando confirmado** (grava, como raiz do plano).
Testar só a primeira transformaria o RC-80 numa recusa com texto amigável,
que é exatamente o que ele não é.

Dados 100% sintéticos, criados nos próprios testes.
"""

from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import strip_tags

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-149", cnpj="55555555000155")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-149 Ltda", cnpj="55566677000133"
    )
    ativo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl149", email="gestora-bl149@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "ativo": ativo}


def _autenticar(client):
    assert client.login(username="gestora-bl149", password=SENHA)


def _url(cenario):
    return reverse("contabilidade_web:conta_nova", args=[cenario["empresa"].id])


def _campos_de_conta_filha(cenario, codigo="1.1"):
    """Um cadastro LEGÍTIMO e completo: conta filha de "1 Ativo", com a
    conta-pai escolhida explicitamente (então o RC-80 não entra em cena)."""
    return {
        "codigo": codigo,
        "nome": "Caixa",
        "tipo": TipoConta.ATIVO,
        "natureza": NaturezaConta.DEVEDORA,
        "conta_pai": str(cenario["ativo"].id),
        "aceita_lancamento": "on",
    }


def _texto_visivel(resposta):
    """O texto que o contador LÊ: sem marcação e com os espaços colapsados —
    as frases do aviso trazem `<strong>` no meio."""
    return " ".join(strip_tags(resposta.content.decode()).split())


# ---------------------------------------------------------------------------
# BL-149 (b) — os cinco dicionários da requisição, medidos NA VIEW
# ---------------------------------------------------------------------------


def test_conta_pai_enviado_como_ARQUIVO_e_recusado_e_nada_e_gravado(client, cenario):
    """O defeito original do auditor, reproduzido pelo mesmo caminho que ele
    usou: a requisição.

    Antes da correção, esta requisição respondia **302 de sucesso** e gravava
    a conta **na raiz do plano** — `conta_pai` chegava em `request.FILES`,
    `ContaCriarForm` só lê `request.POST`, e o campo simplesmente não existia
    para ele. O efeito é estrutural e silencioso: nível, indentação e a linha
    do Balancete por nível mudam sem ninguém pedir.
    """
    _autenticar(client)
    contas_antes = Conta.objects.count()
    dados = _campos_de_conta_filha(cenario)
    dados["conta_pai"] = BytesIO(str(cenario["ativo"].id).encode())

    resposta = client.post(_url(cenario), dados)

    assert resposta.status_code == 400
    assert Conta.objects.count() == contas_antes
    assert not Conta.objects.filter(codigo="1.1").exists()
    texto = _texto_visivel(resposta)
    # A recusa NOMEIA o campo — nada é ignorado em silêncio.
    assert "Este formulário não aceita arquivo nenhum" in texto
    assert "conta_pai" in texto
    # E devolve o que o usuário digitou: recusar sem devolver troca um
    # defeito por outro.
    assert 'value="1.1"' in resposta.content.decode()


@pytest.mark.parametrize(
    "caso",
    ["querystring", "cabecalho", "campo_desconhecido"],
)
def test_conta_nova_recusa_os_outros_dicionarios_pela_requisicao(client, cenario, caso):
    """As outras três portas da mesma política, todas pela view: parâmetro na
    URL de um POST, `Idempotency-Key` por cabeçalho (o contrato da API, não
    desta tela) e campo desconhecido no corpo.

    Antes da BL-149 as três eram aceitas e descartadas em silêncio nesta
    tela — a defesa existia na tela vizinha (`lancamento_novo`) e não aqui.
    """
    _autenticar(client)
    contas_antes = Conta.objects.count()
    endereco = _url(cenario)
    dados = _campos_de_conta_filha(cenario)
    cabecalhos = {}
    if caso == "querystring":
        endereco = f"{endereco}?utm_source=email"
        esperado = "não aceita parâmetros na URL"
    elif caso == "cabecalho":
        cabecalhos = {"HTTP_IDEMPOTENCY_KEY": "chave-da-api"}
        esperado = "não usa o cabeçalho"
    else:
        dados["campo_que_ninguem_le"] = "x"
        esperado = "Não reconheço o(s) campo(s) enviado(s)"

    resposta = client.post(endereco, dados, **cabecalhos)

    assert resposta.status_code == 400, caso
    assert Conta.objects.count() == contas_antes, caso
    assert esperado in _texto_visivel(resposta), caso


def test_controle_positivo_um_cadastro_legitimo_continua_gravando(client, cenario):
    """O controle que impede a leitura errada de todos os casos acima: uma
    `conta_nova` que recusasse qualquer POST passaria nos quatro. Este POST
    é legítimo, grava, e grava **sob a conta-pai escolhida** — que é
    justamente o que o defeito do arquivo destruía."""
    _autenticar(client)

    resposta = client.post(_url(cenario), _campos_de_conta_filha(cenario))

    assert resposta.status_code == 302, _texto_visivel(resposta)[:600]
    criada = Conta.objects.get(empresa=cenario["empresa"], codigo="1.1")
    assert criada.conta_pai_id == cenario["ativo"].id


# ---------------------------------------------------------------------------
# BL-161 / RC-80 — avisar E deixar criar
# ---------------------------------------------------------------------------


def test_conta_sem_as_contas_mae_AVISA_e_nao_grava_na_primeira_tentativa(client, cenario):
    """Metade 1 do RC-80: nenhuma consequência estrutural de um cadastro
    acontece sem o usuário ser avisado.

    Cadastrar `4.1.1` num plano sem `4` e sem `4.1` é legítimo (o contador
    pode estar montando o plano de baixo para cima), mas a conta entra como
    RAIZ do plano — muda a indentação e a linha do Balancete por nível.
    Então a primeira tentativa **não grava**: volta a tela com o aviso, os
    dados preenchidos e um botão que diz o que vai acontecer.

    200 e não 400 de propósito: não é erro do usuário, é confirmação.
    """
    _autenticar(client)

    resposta = client.post(
        _url(cenario),
        {
            "codigo": "4.1.1",
            "nome": "Energia elétrica",
            "tipo": TipoConta.DESPESA,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
        },
    )

    assert resposta.status_code == 200
    assert not Conta.objects.filter(empresa=cenario["empresa"], codigo="4.1.1").exists()
    assert resposta.context["contas_mae_faltantes"] == ("4", "4.1")
    assert resposta.context["codigo_pedido"] == "4.1.1"
    texto = _texto_visivel(resposta)
    # O aviso nomeia as contas-mãe que faltam e a consequência, em texto.
    assert "4.1.1" in texto and "4, 4.1" in texto
    assert "entra como conta RAIZ do plano" in texto
    assert "Nada foi gravado ainda" in texto
    # O caminho de correção fica visível ao lado da confirmação.
    assert "cadastre 4, 4.1 primeiro" in texto
    html = resposta.content.decode()
    # Risco proporcional: o botão DIZ o que vai acontecer, em vez de
    # "Confirmar", e é ele que carrega o valor de confirmação.
    assert 'name="confirmar_conta_sem_conta_mae" value="1"' in html
    assert "Criar 4.1.1 assim mesmo, como raiz do plano" in texto
    assert 'role="alert"' in html
    # E os dados digitados voltam preenchidos — reenviar não exige redigitar.
    assert 'value="4.1.1"' in html
    assert 'value="Energia elétrica"' in html


def test_conta_sem_as_contas_mae_E_CRIADA_quando_confirmada(client, cenario):
    """Metade 2 do RC-80, e a que o Fred escolheu explicitamente contra a
    alternativa de recusar: **confirmada, cria.**

    Confere o efeito estrutural inteiro, não só o 302: a conta existe, está
    **sem conta-pai** (é o que o aviso prometeu) e aparece no Plano de Contas
    como raiz — nível 1, a classe de indentação `nivel-1`.
    """
    _autenticar(client)

    resposta = client.post(
        _url(cenario),
        {
            "codigo": "4.1.1",
            "nome": "Energia elétrica",
            "tipo": TipoConta.DESPESA,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
            "confirmar_conta_sem_conta_mae": "1",
        },
    )

    assert resposta.status_code == 302, _texto_visivel(resposta)[:600]
    criada = Conta.objects.get(empresa=cenario["empresa"], codigo="4.1.1")
    assert criada.conta_pai_id is None

    plano = client.get(reverse("contabilidade_web:plano_de_contas", args=[cenario["empresa"].id]))
    linha = next(item for item in plano.context["linhas"] if item["conta"].codigo == "4.1.1")
    assert linha["nivel"] == 1
    assert linha["nivel_classe"] == 1
    assert "Conta “4.1.1 — Energia elétrica” criada com sucesso." in _texto_visivel(plano)


def test_reenviar_pelo_botao_Salvar_comum_traz_o_aviso_de_novo_em_vez_de_gravar(client, cenario):
    """O cuidado de risco proporcional que o template documenta: o botão
    "Salvar" comum continua existindo, mas **sem** o valor de confirmação —
    reenviar por ele traz o aviso de novo, nunca grava por acidente. Um
    valor diferente de "1" também não confirma.
    """
    _autenticar(client)
    dados = {
        "codigo": "4.1.1",
        "nome": "Energia elétrica",
        "tipo": TipoConta.DESPESA,
        "natureza": NaturezaConta.DEVEDORA,
        "conta_pai": "",
        "confirmar_conta_sem_conta_mae": "0",
    }

    resposta = client.post(_url(cenario), dados)

    assert resposta.status_code == 200
    assert not Conta.objects.filter(empresa=cenario["empresa"], codigo="4.1.1").exists()
    assert resposta.context["contas_mae_faltantes"] == ("4", "4.1")


def test_conta_com_conta_pai_escolhida_nao_pede_confirmacao_nenhuma(client, cenario):
    """Controle negativo do RC-80: com a conta-pai escolhida, a conta **não**
    vai ficar como raiz, e o aviso ("ela ficará como raiz do plano") seria
    falso. Um aviso que aparecesse sempre seria pior que nenhum: ensina a
    clicar em "confirmar" sem ler.

    O cenário é escolhido para DISCRIMINAR, e esta frase é o registro de um
    achado da própria campanha de mutantes desta rodada: a primeira versão
    deste teste cadastrava `1.1` sob `1`, e o mutante que faz o aviso
    ignorar a conta-pai escolhida **sobreviveu** — porque a mãe implícita de
    `1.1` é `1`, que existe, então não havia aviso a suprimir. Aqui `4.1.1`
    tem a mãe `4.1` FALTANDO no plano: sem o desvio por conta-pai
    explicitamente escolhida, esta requisição pediria confirmação.
    """
    _autenticar(client)
    despesas = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="4",
        nome="Despesas",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )

    resposta = client.post(
        _url(cenario),
        {
            "codigo": "4.1.1",
            "nome": "Energia elétrica",
            "tipo": TipoConta.DESPESA,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": str(despesas.id),
            "aceita_lancamento": "on",
        },
    )

    assert resposta.status_code == 302, _texto_visivel(resposta)[:600]
    criada = Conta.objects.get(empresa=cenario["empresa"], codigo="4.1.1")
    assert criada.conta_pai_id == despesas.id
    # E a mãe intermediária de fato não existe: é o que torna este teste
    # capaz de falhar se o desvio por conta-pai desaparecer.
    assert not Conta.objects.filter(empresa=cenario["empresa"], codigo="4.1").exists()


def test_conta_cujas_maes_JA_EXISTEM_nao_pede_confirmacao(client, cenario):
    """O outro controle negativo, e o que distingue "não tem conta-pai
    escolhida" de "as contas-mãe não existem": `1.1.1` num plano que já tem
    `1` e `1.1` não pede confirmação nenhuma, mesmo sem `conta_pai`
    preenchido — o que falta ali é a ligação, não a hierarquia."""
    _autenticar(client)
    Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="1.1",
        nome="Disponibilidades",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=cenario["ativo"],
        aceita_lancamento=False,
    )

    resposta = client.post(
        _url(cenario),
        {
            "codigo": "1.1.1",
            "nome": "Caixa geral",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
        },
    )

    assert resposta.status_code == 302, _texto_visivel(resposta)[:600]
    assert Conta.objects.filter(empresa=cenario["empresa"], codigo="1.1.1").exists()


def test_contas_mae_faltantes_nao_atravessa_empresas(client, cenario):
    """Isolamento: `4` e `4.1` existirem na empresa VIZINHA não satisfaz o
    plano desta. Sem este recorte, o aviso deixaria de aparecer por causa do
    plano de outro cliente do escritório — e a conta entraria como raiz sem
    ninguém ser avisado."""
    _autenticar(client)
    vizinha = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Empresa vizinha Ltda",
        cnpj="55566677000214",
    )
    for codigo, nome in (("4", "Despesas"), ("4.1", "Despesas operacionais")):
        Conta.objects.create(
            empresa=vizinha,
            codigo=codigo,
            nome=nome,
            tipo=TipoConta.DESPESA,
            natureza=NaturezaConta.DEVEDORA,
            aceita_lancamento=False,
        )

    resposta = client.post(
        _url(cenario),
        {
            "codigo": "4.1.1",
            "nome": "Energia elétrica",
            "tipo": TipoConta.DESPESA,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": "",
        },
    )

    assert resposta.status_code == 200
    assert resposta.context["contas_mae_faltantes"] == ("4", "4.1")


@pytest.mark.parametrize(
    "codigo,esperado",
    [
        ("4.1.1", ("4", "4.1")),
        ("4.1", ("4",)),
        ("1.1.1.1", ("1", "1.1", "1.1.1")),
        # Sem separador: um plano que usa "41111" não implica mãe nenhuma, e
        # inventar hierarquia por fatia de dígitos seria presumir regra
        # contábil — o que o AGENTS.md proíbe.
        ("41111", ()),
        ("4", ()),
        # Código malformado não é hierarquia; quem julga formato é o modelo.
        ("4..1", ()),
        (".1", ()),
        ("4.1.", ()),
        ("", ()),
    ],
)
def test_codigos_das_contas_mae_implicitos_no_codigo(codigo, esperado):
    """A derivação em si, sem banco: do mais alto para o mais próximo, e
    vazio quando não há hierarquia a inferir. É a metade da regra que decide
    o texto do aviso — `4.1.1` avisa sobre `4` e `4.1`, nessa ordem."""
    assert views_web._codigos_das_contas_mae(codigo) == esperado
