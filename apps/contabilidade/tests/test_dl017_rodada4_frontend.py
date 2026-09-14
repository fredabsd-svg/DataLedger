"""Correções da rodada 4 da auditoria da DL-017 (docs/auditorias/
2026-09-14-dl-017-rodada-4.md) atribuídas ao `especialista-frontend`:
A1 (BL-126) e A3 (BL-128). Dados 100% sintéticos, criados nos próprios
testes.

A2, A9, A10 são do `desenvolvedor-pleno`; A4, A5, A6, A8 têm teste em
`test_dl017_rodada2_frontend.py`/`test_dl017_rodada3_frontend.py` (onde o
código correspondente já vivia); A7 é do `arquiteto-senior`.
"""

import inspect

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório rodada 4", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Rodada 4 Ltda", cnpj="11122233000183"
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
        username="gestora-r4", email="gestora-r4@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-r4", password="senha-forte-123")


def _url_lancamento(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _dados_base(cen, *, acao="gravar", chave, conta_1=None):
    return {
        "acao": acao,
        "num_linhas": "2",
        "data": timezone.localdate().isoformat(),
        "historico": "rodada 4",
        "chave_idempotencia": chave,
        "conta_1": conta_1 if conta_1 is not None else str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "10,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "10,00",
    }


# ---------------------------------------------------------------------------
# A1 — BL-126: conta_id não pode produzir 500 nem reinterpretar dígito
# Unicode em silêncio.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "conta_id_hostil",
    [
        # `id=` explícito: um valor de milhares de dígitos usado como ID
        # de teste (o padrão do pytest) já quebrou o cache interno de
        # fixtures do pytest neste ambiente em rodadas anteriores.
        pytest.param("9" * 4301, id="9-vezes-4301"),  # antes: 500 (limite do Python)
        pytest.param("9" * 6000, id="9-vezes-6000"),
        pytest.param("７", id="fullwidth-7"),  # antes: 302, reinterpretado como a conta 7
        pytest.param("٢", id="indico-arabico-2"),
    ],
)
def test_conta_id_hostil_nunca_e_500_nem_reinterpretado(client, cen, conta_id_hostil):
    """A1/BL-126 — a MESMA classe que o campo `nivel` já tinha fechado na
    rodada 2 (`isdigit()` sozinho aceita QUALQUER dígito Unicode, e o
    `int()` sem `try/except` estoura em texto longo demais). Agora
    `conta_id` passa por `_identificador_de_cliente` (delega a `para_id`,
    `apps.core.identificadores` — ver o teste de delegação logo abaixo):
    nunca 500, nunca gravado numa conta diferente da que o texto realmente
    escreve.
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    dados = _dados_base(cen, chave=f"a1-{conta_id_hostil}", conta_1=conta_id_hostil)
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400, (conta_id_hostil, resposta.status_code)
    assert LancamentoContabil.objects.count() == antes
    assert "conta inválida" in resposta.content.decode().lower()


def test_conta_id_valido_continua_gravando(client, cen):
    """Controle: um `conta_id` normal (o caso de todo dia) continua
    funcionando depois da correção.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="a1-controle-valido")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 302
    lancamento = LancamentoContabil.objects.get(chave_idempotencia="a1-controle-valido")
    assert {item.conta_id for item in lancamento.itens.all()} == {
        cen["caixa"].id,
        cen["receita"].id,
    }


def test_conta_id_delega_ao_julgador_partilhado_de_identificador(client, cen, monkeypatch):
    """A1/BL-126, integração posterior à rodada 4: `conta_id` é um
    IDENTIFICADOR de banco, a mesma invariante que `apps.core.
    identificadores.para_id` já julga para a API e para `apps.tenancy`
    (BL-127/A2). Esta view não reimplementa o padrão — delega. Prova
    ESTRUTURAL (o texto-fonte chama `_identificador_de_cliente`, que por
    sua vez chama `para_id`) e COMPORTAMENTAL (susta `para_id` e confere
    que um `conta_id` normal, que gravaria em qualquer outra condição,
    passa a ser recusado — só alcançável se a chamada é REAL, não só
    textual).
    """
    fonte_itens_e_totais = inspect.getsource(views_web._itens_e_totais)
    assert '_identificador_de_cliente(linha["conta_id"])' in fonte_itens_e_totais
    fonte_identificador = inspect.getsource(views_web._identificador_de_cliente)
    assert "para_id(" in fonte_identificador

    def _para_id_que_recusa_tudo(valor):
        raise views_web.IdentificadorInvalido("simulação de teste: para_id indisponível")

    monkeypatch.setattr(views_web, "para_id", _para_id_que_recusa_tudo)

    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    dados = _dados_base(cen, chave="a1-delegacao-para-id")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes
    assert "conta inválida" in resposta.content.decode().lower()


def test_num_linhas_nao_delega_a_para_id_preserva_magnitude(monkeypatch):
    """Contraste com o teste acima: `num_linhas` (e `nivel`, e os índices
    de linha) são QUANTIDADE de negócio, não identificador — continuam em
    `_inteiro_de_cliente` (padrão `_PADRAO_NIVEL_SIMPLES` + `int()`
    local), não em `para_id`. Prova ESTRUTURAL: o `num_linhas` de
    `lancamento_novo` chama `_inteiro_de_cliente`, nunca
    `_identificador_de_cliente`. Prova COMPORTAMENTAL, isolada da view
    (que também usa `para_id` para `conta_id` no MESMO POST — sustar
    `para_id` ali quebraria a resolução de conta por um motivo alheio a
    este teste): com `para_id` substituído por uma função que sempre
    recusa, `_inteiro_de_cliente` ainda converte um texto de 4000 dígitos
    (maior que qualquer `num_linhas` real, mas dentro do limite de
    conversão do Python) para o `int` de magnitude real — só alcançável
    se a função NUNCA delega a `para_id`.
    """
    fonte_view = inspect.getsource(views_web.lancamento_novo)
    assert '_inteiro_de_cliente(request.POST.get("num_linhas"' in fonte_view
    assert '_identificador_de_cliente(request.POST.get("num_linhas"' not in fonte_view

    monkeypatch.setattr(
        views_web,
        "para_id",
        lambda valor: (_ for _ in ()).throw(
            views_web.IdentificadorInvalido("não deveria ser chamado por num_linhas")
        ),
    )
    texto_hostil = "9" * 4000
    assert views_web._inteiro_de_cliente(texto_hostil) == int(texto_hostil)


# ---------------------------------------------------------------------------
# A3 — BL-128: a política de "nenhum dado deixa de ser lido ou recusado"
# vale para a REQUISIÇÃO inteira — request.FILES incluso.
# ---------------------------------------------------------------------------


def test_par_completo_enviado_como_arquivo_e_recusado_nao_desaparece(client, cen):
    """A3/BL-128 — reprodução da medição do auditor: duas partidas normais
    (10,00/10,00) mais um PAR COMPLETO e balanceado (500,00 D + 500,00 C)
    enviado como CAMPOS DE ARQUIVO (`request.FILES`, não `request.POST`).
    Antes desta correção: 302 "gravado com sucesso", só os 2 itens de
    10,00 — os 500,00 somiam da tela, do total da conferência e do aviso
    do R2-5, porque `request.FILES` nunca era olhado. Agora: 400, nada
    gravado, a(s) chave(s) de arquivo nomeada(s) na mensagem.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="a3-par-completo")
    dados["conta_3"] = str(cen["caixa"].id)
    dados["tipo_3"] = "debito"
    dados["conta_4"] = str(cen["receita"].id)
    dados["tipo_4"] = "credito"
    # `valor_3`/`valor_4` viajam como ARQUIVO — não como texto de
    # `request.POST` — reproduzindo exatamente o transporte do achado.
    dados["valor_3"] = SimpleUploadedFile("valor_3.txt", b"500,00")
    dados["valor_4"] = SimpleUploadedFile("valor_4.txt", b"500,00")

    antes = LancamentoContabil.objects.count()
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes
    conteudo = resposta.content.decode()
    assert "arquivo" in conteudo.lower()
    assert "valor_3" in conteudo or "valor_4" in conteudo


def test_adicionar_linha_tambem_recusa_campo_de_arquivo(client, cen):
    """Mesma classe, pelo ramo de conferência (`adicionar_linha`): antes,
    o total mostrava "10,00" batendo consigo mesmo, os 500,00 enviados
    como arquivo não apareciam em lugar nenhum, e o aviso do R2-5 nunca
    disparava (a linha não era "incompleta" — para o código, ela não
    existia). Agora recusa igual ao ramo `gravar`.
    """
    _login(client, cen)
    dados = _dados_base(cen, acao="adicionar_linha", chave="a3-conferencia")
    dados["arquivo_qualquer"] = SimpleUploadedFile("x.txt", b"conteudo")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400
    assert "arquivo_qualquer" in resposta.content.decode()


def test_prefixo_de_chave_fora_de_minusculas_e_recusado_nao_ignorado(client, cen):
    """A3, achado colateral nomeado pelo auditor: "CONTA_3"/"Conta_3" (o
    template NUNCA emite prefixo fora de minúsculas) não podem ser
    silenciosamente ignorados — a política declarada é recusar o que não
    se entende, não só o que chega por `request.FILES`.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="a3-prefixo-maiusculo")
    dados["CONTA_3"] = str(cen["caixa"].id)
    dados["TIPO_3"] = "debito"
    dados["VALOR_3"] = "77,00"

    antes = LancamentoContabil.objects.count()
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == antes
    assert "CONTA_3" in resposta.content.decode()


def test_lancamento_sem_arquivo_nenhum_continua_gravando(client, cen):
    """Controle: um POST comum, sem `request.FILES`, não é afetado pela
    correção do A3.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="a3-controle-sem-arquivo")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 302
    assert LancamentoContabil.objects.count() == 1
