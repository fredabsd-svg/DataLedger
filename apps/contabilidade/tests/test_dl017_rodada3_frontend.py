"""Correções da rodada 3 da auditoria da DL-017 (docs/auditorias/
2026-09-14-dl-017-rodada-3.md) atribuídas ao `especialista-frontend`:
R3-1 (BL-115, BLOQUEADOR), R3-2 (BL-116) e R3-9 (BL-120).

R3-3, R3-4 (código), R3-10 são do `desenvolvedor-pleno`; R3-5 a R3-8 são
do `arquiteto-senior` — sem teste aqui. Dados 100% sintéticos, criados
nos próprios testes.
"""

import signal
import time

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório rodada 3", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Rodada 3 Ltda", cnpj="11122233000183"
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
        username="gestora-r3", email="gestora-r3@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-r3", password="senha-forte-123")


def _url_lancamento(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _dados_base(cen, *, acao="gravar", chave):
    return {
        "acao": acao,
        "data": timezone.localdate().isoformat(),
        "historico": "rodada 3",
        "chave_idempotencia": chave,
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "10,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "10,00",
    }


# ---------------------------------------------------------------------------
# R3-1 (BLOQUEADOR) — BL-115: nenhum número vindo do cliente dimensiona um
# laço, alocação ou repetição, em nenhum ramo.
# ---------------------------------------------------------------------------

# Generoso: a rodada 3 mediu 2,6 s para 1 milhão pela requisição HTTP
# completa e NENHUM retorno em 45 s para 10**12 — a recusa correta deve
# acontecer bem antes de qualquer leitura, em bem menos de 1 segundo.
_TETO_DE_TEMPO_S = 3


@pytest.mark.parametrize("acao", ["gravar", "adicionar_linha"])
@pytest.mark.parametrize(
    "num_linhas_hostil",
    [
        pytest.param(str(10**12), id="10-elevado-a-12"),  # não retornava (nada em 45s)
        # "9" * 4000: maior que qualquer uso real, mas dentro do limite de
        # conversão do Python (4300 dígitos) — precisa ser recusado pela
        # REGRA DE NEGÓCIO desta view, não pelo `int()`. `id=` curto de
        # propósito: usar a string de 4000 dígitos como id de teste (o
        # padrão do pytest) já bastou para quebrar o cache interno de
        # fixtures do pytest neste ambiente.
        pytest.param("9" * 4000, id="9-vezes-4000-digitos"),
        pytest.param("1000000", id="um-milhao"),  # 2,6 s medidos pela auditoria
        pytest.param("10000000", id="dez-milhoes"),  # 26 s medidos pela auditoria
    ],
)
def test_num_linhas_absurdo_e_recusado_rapido_nos_dois_ramos(client, cen, acao, num_linhas_hostil):
    """R3-1/BL-115 — a classe é: nenhum número vindo do cliente dimensiona
    laço, alocação ou repetição, em NENHUM ramo desta view. A correção do
    R2-10 (repetir ao contador os valores que não couberam) passou a
    chamar a leitura de linhas ANTES de recusar, com um `num_linhas` que
    vinha do cliente sem teto — este teste CRONOMETRA a resposta, porque
    "não travou nesta chamada" não é evidência sem tempo medido.
    """
    _login(client, cen)
    dados = _dados_base(cen, acao=acao, chave=f"r3-1-{acao}-{len(num_linhas_hostil)}")
    dados["num_linhas"] = num_linhas_hostil

    antes = LancamentoContabil.objects.count()
    inicio = time.monotonic()
    resposta = client.post(_url_lancamento(cen), dados)
    duracao = time.monotonic() - inicio

    assert resposta.status_code == 400, (num_linhas_hostil, acao, resposta.status_code)
    assert duracao < _TETO_DE_TEMPO_S, (num_linhas_hostil, acao, duracao)
    assert LancamentoContabil.objects.count() == antes


def test_num_linhas_no_limite_de_conversao_do_python_nao_e_500(client, cen):
    """Controle: um `num_linhas` com mais dígitos do que o limite de
    conversão do Python (`int()` levantaria `ValueError` sozinho) cai no
    `except (TypeError, ValueError)` já existente e degrada para o
    padrão de linhas iniciais — nunca um 500, e sem passar perto de um
    `range()` proporcional ao texto enviado.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="r3-1-limite-conversao")
    dados["num_linhas"] = "9" * 4400  # acima do limite de conversão do Python
    inicio = time.monotonic()
    resposta = client.post(_url_lancamento(cen), dados)
    duracao = time.monotonic() - inicio
    assert resposta.status_code in (302, 400), resposta.status_code
    assert duracao < _TETO_DE_TEMPO_S, duracao


# ---------------------------------------------------------------------------
# A6/BL-130 — os dois testes de defesa em profundidade acima (na forma
# antiga) mediam a DURAÇÃO de uma chamada com `num_linhas=10**12` e
# afirmavam `duracao < 1`. Sob o mutante que remove a capa interna
# (`num_linhas = min(num_linhas, LINHAS_LEITURA_TETO_DE_SEGURANCA)`), a
# chamada NÃO RETORNA — o teste não FALHA, ele PENDURA. Medido pelo
# auditor: 10 minutos antes de ser morto manualmente, com o banco de
# teste travado e a execução seguinte envenenada por um motivo alheio. Um
# teste cujo modo de falha é pendurar não reprova um build: ele estoura o
# `timeout-minutes` do workflow inteiro, com uma causa que não se parece
# com a causa (a mesma armadilha do `aa10f20`, por outra via).
#
# A correção usa as DUAS saídas que o achado sugere, sem escolher uma só:
# 1. Medir a PROPRIEDADE (não a duração) com um valor pequeno e seguro
#    (`LINHAS_LEITURA_TETO_DE_SEGURANCA + 1`, nunca `10**12`): confirma
#    que a capa realmente exclui o que está acima do teto.
# 2. Um teto de tempo que de fato INTERROMPE a chamada com `10**12` (via
#    `signal.alarm`, sem depender de `pytest-timeout`, que não está
#    instalado) — continua exercitando o valor hostil de verdade, mas sem
#    o risco de pendurar a sessão inteira: sob o mutante, este teste
#    FALHA com uma mensagem clara em poucos segundos, nunca trava.
# ---------------------------------------------------------------------------


class _TempoEsgotado(Exception):
    pass


def _com_teto_de_tempo_que_interrompe(segundos, funcao, *args, **kwargs):
    """Chama `funcao(*args, **kwargs)` com um teto de tempo que
    INTERROMPE a chamada de verdade (via `signal.alarm`), em vez de só
    medir quanto tempo ela levou depois que já retornou. Levanta
    `_TempoEsgotado` se `funcao` não retornar dentro de `segundos` —
    transforma "pendurar" numa `AssertionError`/exceção normal, dentro do
    próprio processo de teste, bem antes de qualquer timeout externo
    (do `pytest`, do workflow) precisar agir.
    """

    def _alarme(signum, frame):
        raise _TempoEsgotado(f"não retornou em {segundos}s")

    anterior = signal.signal(signal.SIGALRM, _alarme)
    signal.alarm(segundos)
    try:
        return funcao(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, anterior)


def test_linhas_lancamento_do_post_exclui_o_que_esta_acima_do_teto_de_seguranca():
    """A6/BL-130, saída 1 (propriedade): chama com
    `LINHAS_LEITURA_TETO_DE_SEGURANCA + 1` — um número pequeno, rápido em
    QUALQUER implementação, capada ou não — e mede o EFEITO da capa: uma
    linha completa no índice imediatamente acima do teto não é lida. Sob
    o mutante que remove a capa, esta chamada continua rápida, mas a
    linha 201 passaria a ser lida — é essa mudança de comportamento que
    prova a capa, não quanto tempo a chamada levou.
    """
    indice_acima_do_teto = views_web.LINHAS_LEITURA_TETO_DE_SEGURANCA + 1
    post = {
        f"conta_{indice_acima_do_teto}": "999",
        f"tipo_{indice_acima_do_teto}": "debito",
        f"valor_{indice_acima_do_teto}": "10,00",
    }
    linhas, erros = views_web._linhas_lancamento_do_post(post, indice_acima_do_teto)
    indices_lidos = {linha["indice"] for linha in linhas}
    assert indice_acima_do_teto not in indices_lidos
    assert max(indices_lidos, default=0) <= views_web.LINHAS_LEITURA_TETO_DE_SEGURANCA


def test_linhas_lancamento_do_post_nunca_pendura_com_num_linhas_absurdo():
    """A6/BL-130, saída 2 (teto de tempo que interrompe): exercita o MESMO
    `10**12` que a rodada 3 usava, mas sob um teto de 5s que INTERROMPE a
    chamada de verdade — nunca deixa a sessão pendurar. Sob o mutante que
    remove a capa interna, este teste levanta `_TempoEsgotado` em ~5s (uma
    falha limpa e rápida) em vez de travar por minutos.
    """
    linhas, erros = _com_teto_de_tempo_que_interrompe(
        5, views_web._linhas_lancamento_do_post, {}, 10**12
    )
    assert linhas == []
    assert erros == []


def test_contexto_form_lancamento_exclui_o_que_esta_acima_do_teto_de_seguranca(cen):
    """Mesma defesa (saída 1, propriedade), para `_contexto_form_lancamento`."""
    indice_acima_do_teto = views_web.LINHAS_LEITURA_TETO_DE_SEGURANCA + 1
    contexto = views_web._contexto_form_lancamento(
        cen["empresa"],
        [],
        indice_acima_do_teto,
        data_texto="",
        historico="",
        chave_idempotencia="x",
    )
    indices = {linha["indice"] for linha in contexto["linhas"]}
    assert indice_acima_do_teto not in indices
    assert len(contexto["linhas"]) == views_web.LINHAS_LEITURA_TETO_DE_SEGURANCA


def test_contexto_form_lancamento_nunca_pendura_com_num_linhas_absurdo(cen):
    """Mesma defesa (saída 2, teto de tempo que interrompe), para
    `_contexto_form_lancamento`.
    """
    contexto = _com_teto_de_tempo_que_interrompe(
        5,
        views_web._contexto_form_lancamento,
        cen["empresa"],
        [],
        10**12,
        data_texto="",
        historico="",
        chave_idempotencia="x",
    )
    assert len(contexto["linhas"]) == views_web.LINHAS_LEITURA_TETO_DE_SEGURANCA


# ---------------------------------------------------------------------------
# R3-2 — BL-116: índice de linha fora do canônico é RECUSADO, nunca ignorado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chave_extra",
    [
        "conta_10000",  # 5+ dígitos — não casava o padrão antigo, ficava invisível
        "conta_0",  # fora do range(1, N+1)
        "conta_01",  # zero à esquerda — int() normaliza para outra chave
        "conta_0001",
        "conta_+3",  # sinal
        "tipo_99999",
    ],
)
def test_indice_de_linha_fora_do_canonico_e_recusado_nao_ignorado(client, cen, chave_extra):
    """R3-2/BL-116 — a classe é: nenhuma linha enviada no POST deixa de
    ser lida, e o que não for entendido é RECUSADO, nunca ignorado. Antes
    desta correção, cada uma destas chaves fazia a linha correspondente
    desaparecer em silêncio, com HTTP 302 "gravado com sucesso" — a
    MESMA classe do achado 5, por outra porta.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave=f"r3-2-{chave_extra}")
    dados["num_linhas"] = "2"
    dados[chave_extra] = "valor-fantasma"

    antes = LancamentoContabil.objects.count()
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400, (chave_extra, resposta.status_code)
    assert LancamentoContabil.objects.count() == antes
    assert chave_extra in resposta.content.decode()


def test_par_completo_em_indice_nao_canonico_nao_desaparece(client, cen):
    """Reprodução da tabela do R3-2: duas partidas canônicas (10,00/10,00)
    MAIS um PAR COMPLETO (77,00/77,00) num índice fora do canônico. Antes
    desta correção: 302, 2 partidas gravadas, 10,00 — o par de 77,00
    simplesmente sumia. Agora: 400, nada gravado.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="r3-2-par-completo")
    dados["num_linhas"] = "2"
    dados["conta_10000"] = str(cen["caixa"].id)
    dados["tipo_10000"] = "debito"
    dados["valor_10000"] = "77,00"
    dados["conta_10001"] = str(cen["receita"].id)
    dados["tipo_10001"] = "credito"
    dados["valor_10001"] = "77,00"

    antes = LancamentoContabil.objects.count()
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == antes


def test_adicionar_linha_tambem_recusa_indice_nao_canonico(client, cen):
    """A conferência (botão "Adicionar linha") não pode ser a porta de
    trás desta mesma classe: antes, o rodapé mostrava os dois lados
    BATENDO (a linha extra virava invisível, não incompleta — o aviso do
    R2-5 nunca disparava) e os 500,00 enviados somiam da tela. Agora:
    400, a chave nomeada, nada de conferência enganosa.
    """
    _login(client, cen)
    dados = _dados_base(cen, acao="adicionar_linha", chave="r3-2-conferencia")
    dados["num_linhas"] = "4"
    dados["valor_1"] = "1.000,00"
    dados["valor_2"] = "1.000,00"
    dados["conta_0001"] = str(cen["caixa"].id)
    dados["tipo_0001"] = "debito"
    dados["valor_0001"] = "500,00"

    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "conta_0001" in conteudo


# ---------------------------------------------------------------------------
# R3-9 — BL-120: o teto de segurança não pode ser seguro só por acidente
# aritmético com o teto de negócio.
# ---------------------------------------------------------------------------


def test_indice_canonico_no_limite_do_teto_de_seguranca_e_aceito_como_indice(client, cen):
    """Controle positivo: um índice EXATAMENTE no teto de segurança (200)
    é CANÔNICO — a leitura o aceita como índice de verdade. Só o teto de
    NEGÓCIO (20) o recusa depois, e é essa recusa (não "chave não
    entendida") que deve aparecer.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="r3-9-limite-200")
    dados["num_linhas"] = "2"
    dados["conta_200"] = str(cen["caixa"].id)
    dados["tipo_200"] = "debito"
    dados["valor_200"] = "5,00"

    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "máximo" in conteudo
    assert "Não entendi" not in conteudo


def test_indice_acima_do_teto_de_seguranca_nunca_e_capado_em_silencio(client, cen):
    """R3-9/BL-120: um índice ACIMA do teto de segurança (201) é tratado
    como NÃO CANÔNICO — a mesma recusa do R3-2 —, nunca capado em
    silêncio para 200. É exatamente o capeamento silencioso
    (`min(maior, 200)`) que reabriria a perda do achado 5 no dia em que
    o Fred responder PE-42 com um teto de negócio de 200 partidas ou
    mais: nenhuma linha de código mudaria, e a perda voltaria.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="r3-9-acima-201")
    dados["num_linhas"] = "2"
    dados["conta_201"] = str(cen["caixa"].id)
    dados["tipo_201"] = "debito"
    dados["valor_201"] = "5,00"

    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "conta_201" in conteudo
    assert "Não entendi" in conteudo


def test_teto_de_seguranca_e_estritamente_maior_que_o_teto_de_negocio():
    """R3-9/BL-120: a verificação DEDICADA que falha se
    `LINHAS_MAXIMAS_LANCAMENTO >= LINHAS_LEITURA_TETO_DE_SEGURANCA` — a
    desigualdade entre os dois tetos é, hoje, o único motivo pelo qual um
    índice "não canônico" nunca colide com um índice de negócio válido.
    Reforça o `assert` de nível de módulo em `views_web.py` (que `python
    -O` descartaria) com uma verificação que a suíte sempre executa.
    """
    assert views_web.LINHAS_MAXIMAS_LANCAMENTO < views_web.LINHAS_LEITURA_TETO_DE_SEGURANCA


# ---------------------------------------------------------------------------
# Regressão: o caminho canônico normal continua intacto depois desta rodada.
# ---------------------------------------------------------------------------


def test_lancamento_canonico_normal_continua_gravando(client, cen):
    _login(client, cen)
    dados = _dados_base(cen, chave="r3-regressao-normal")
    dados["num_linhas"] = "2"
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 302
    assert LancamentoContabil.objects.count() == 1
