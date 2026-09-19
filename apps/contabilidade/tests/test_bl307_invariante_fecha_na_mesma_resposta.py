"""BL-307 (A1 da auditoria DL-024 rodada 3,
docs/auditorias/2026-09-18-dl-024-rodada-3.md): a correção do BL-289 cobriu
`veredito_fechamento` no caminho `acao=adicionar_linha` e deixou o caminho
`acao=gravar` (e qualquer outro valor de `acao`, tratado como tentativa de
gravação — ver o comentário em `views_web.lancamento_novo`) inteiro de fora:
`_contexto_form_lancamento` não recebia `linhas_excluidas_do_total` ali, então
o padrão (`0`) fazia o veredito achar que nenhuma linha tinha sido descartada
— mesmo quando havia. O auditor mediu quatro POSTs `acao=gravar`
independentes em que a página respondia HTTP 400 dizendo "Fecha" em verde.

**Requisito geral, não a lista de quatro casos do relatório** (instrução do
`arquiteto-senior` na rodada 5): a frase que a tela mostra sobre o
fechamento é verdadeira em TODA resposta que o servidor devolve, qualquer
que seja o caminho de recusa. Formalizado como duas metades da mesma
invariante, sobre a MESMA resposta HTTP (nunca duas requisições
diferentes — essa foi a falha do teste que não pegou o achado, registrada
pelo auditor: "`test_invariante_fecha_implica_gravar_302_nunca_400` lê o
veredito de uma resposta de `adicionar_linha` e, em seguida, num POST
separado, verifica o status de `gravar`"):

1. **Recíproca, universal para qualquer `acao`:** se a resposta tem
   `status_code == 400`, o HTML dela NUNCA contém o marcador
   `<strong class="veredito-fechamento">Fecha</strong>`. Vale para
   `adicionar_linha` e para qualquer tentativa de gravação, porque nenhum
   caminho de recusa deste formulário tem o direito de dizer "Fecha" —
   400 é, por definição, "não gravou".
2. **Direta, escopada às tentativas de GRAVAÇÃO** (`acao != "adicionar_
   linha"` — inclusive um valor desconhecido, que a view trata como
   tentativa de gravar, conforme o comentário "Qualquer outro valor de
   'acao' ... é tratado como tentativa de gravação"): se o HTML da
   resposta contém o marcador "Fecha", o status é `302`. Não vale para
   `adicionar_linha` porque esse botão nunca tenta gravar — seu "Fecha" é
   só a conferência das partidas digitadas até agora (contrato inalterado
   desde o BL-289, com teste próprio em `test_bl289_veredito_fechamento.py`).

A bateria de casos abaixo cobre os quatro POSTs do relatório do auditor
(valor inválido, linha incompleta, histórico grande demais, data inválida)
e ACRESCENTA casos que o relatório não citou: chave de idempotência grande
demais, conta inexistente, tipo de partida inválido e uma ação desconhecida
(`acao=confirmar`) — para provar que a guarda está presa ao REQUISITO, não
à lista literal do achado. A mesma asserção genérica é aplicada aos nove
casos e a qualquer caminho de recusa futuro que caia neles, sem
customização por caso.

Dados 100% sintéticos, criados nos próprios testes.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.contabilidade.views import TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA, TAMANHO_MAXIMO_HISTORICO
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

# Marcador literal que o template usa para o estado "fecha" — o mesmo que a
# auditoria mediu na reprodução do achado A1 (docs/auditorias/2026-09-18-
# dl-024-rodada-3.md, linha 95). Verificar o HTML renderizado, não o
# `context`, é deliberado: o achado foi medido na PÁGINA que o navegador
# recebe, e uma guarda que só lesse `context` correria o mesmo risco já
# registrado pelo BL-306 (o veredito "em três camadas").
MARCADOR_FECHA = '<strong class="veredito-fechamento">Fecha</strong>'


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório BL-307", cnpj="33322211000177")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-307 Ltda", cnpj="33344455000122"
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
        username="gestora-bl307",
        email="gestora-bl307@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _url_tela(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _corpo_base(cen, chave):
    """Duas partidas VÁLIDAS e balanceadas (300,00/300,00) — o corpo que,
    sozinho, fecharia — mais a chave de idempotência ÚNICA desta tentativa.
    `num_linhas=2`: cada caso acrescenta a linha 3 quando precisa de uma
    linha extra quebrada; os casos que não mexem em linha mantêm só as
    duas. `chave` entra aqui, e não é sobrescrita depois, porque o caso
    `chave_idempotencia_grande_demais` PRECISA poder alterá-la sem que o
    chamador desfaça a alteração em seguida.
    """
    return {
        "acao": "gravar",
        "num_linhas": "2",
        "data": timezone.localdate().isoformat(),
        "historico": "BL-307",
        "chave_idempotencia": chave,
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "300,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "300,00",
    }


# ---------------------------------------------------------------------------
# Cada função abaixo recebe o corpo BASE (duas partidas batendo) e devolve
# uma cópia MODIFICADA que introduz exatamente um motivo de recusa — sem
# nunca deixar as duas linhas originais de bater sozinhas, que é a condição
# que expôs o achado A1 (débito == crédito nas partidas VÁLIDAS, mas a
# resposta ainda assim tem de ser recusada).
# ---------------------------------------------------------------------------


def _valor_invalido_em_terceira_linha(corpo):
    """Caso 1 do relatório: duas linhas válidas batendo + uma linha com
    valor "abc" — descarta uma linha (`linhas_excluidas_do_total`)."""
    corpo = dict(corpo)
    corpo["num_linhas"] = "3"
    corpo["conta_3"] = corpo["conta_1"]
    corpo["tipo_3"] = "debito"
    corpo["valor_3"] = "abc"
    return corpo


def _linha_incompleta(corpo):
    """Caso 2 do relatório: duas linhas válidas batendo + uma linha com só
    a conta preenchida — descarta uma linha."""
    corpo = dict(corpo)
    corpo["num_linhas"] = "3"
    corpo["conta_3"] = corpo["conta_1"]
    # tipo_3 e valor_3 ficam de fora de propósito — linha PARCIAL.
    return corpo


def _historico_grande_demais(corpo):
    """Caso 3 do relatório: as duas linhas continuam válidas e SEM exclusão
    — o histórico é o único motivo de recusa. Prova que
    `linhas_excluidas_do_total` sozinho não bastava (achado da rodada 5): é
    o caso que exercita `bloqueado_por_outro_erro`."""
    corpo = dict(corpo)
    corpo["historico"] = "x" * (TAMANHO_MAXIMO_HISTORICO + 1)
    return corpo


def _data_invalida(corpo):
    """Caso 4 do relatório: idem, mas o motivo é a data. Mesma classe do
    caso anterior — nenhuma linha excluída."""
    corpo = dict(corpo)
    corpo["data"] = "abacaxi"
    return corpo


def _chave_idempotencia_grande_demais(corpo):
    """CASO NÃO CITADO PELO RELATÓRIO: chave de idempotência maior que o
    teto do modelo. Mesma classe dos dois casos acima — nenhuma linha
    excluída, débito e crédito das partidas VÁLIDAS batem — e é
    exatamente o outro campo que `bloqueado_por_outro_erro` cobre."""
    corpo = dict(corpo)
    corpo["chave_idempotencia"] = "k" * (TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA + 1)
    return corpo


def _conta_inexistente_em_terceira_linha(corpo):
    """CASO NÃO CITADO PELO RELATÓRIO: terceira linha com uma conta que não
    existe (id fora da faixa) — descarta a linha por motivo diferente do
    caso 1 (lá era valor inválido; aqui é `conta inválida`)."""
    corpo = dict(corpo)
    corpo["num_linhas"] = "3"
    corpo["conta_3"] = "999999"
    corpo["tipo_3"] = "debito"
    corpo["valor_3"] = "10,00"
    return corpo


def _tipo_invalido_em_terceira_linha(corpo):
    """CASO NÃO CITADO PELO RELATÓRIO: terceira linha com `tipo` fora de
    {debito, credito} — outra origem de linha excluída."""
    corpo = dict(corpo)
    corpo["num_linhas"] = "3"
    corpo["conta_3"] = corpo["conta_1"]
    corpo["tipo_3"] = "transferencia"
    corpo["valor_3"] = "10,00"
    return corpo


def _acao_desconhecida_com_linha_quebrada(corpo):
    """CASO NÃO CITADO PELO RELATÓRIO: `acao` que a view NUNCA viu antes —
    o comentário da view promete que "qualquer outro valor de 'acao' ...
    é tratado como tentativa de gravação". Um caminho de recusa NOVO,
    criado no futuro sob um nome de ação diferente, tem de cair na mesma
    guarda — este caso é o substituto mais próximo que dá para escrever
    hoje."""
    corpo = dict(corpo)
    corpo["acao"] = "confirmar"
    corpo["num_linhas"] = "3"
    corpo["conta_3"] = corpo["conta_1"]
    corpo["tipo_3"] = "debito"
    corpo["valor_3"] = "abc"
    return corpo


CASOS_DE_RECUSA = {
    "valor_invalido_terceira_linha": _valor_invalido_em_terceira_linha,
    "linha_incompleta": _linha_incompleta,
    "historico_grande_demais": _historico_grande_demais,
    "data_invalida": _data_invalida,
    "chave_idempotencia_grande_demais": _chave_idempotencia_grande_demais,
    "conta_inexistente_terceira_linha": _conta_inexistente_em_terceira_linha,
    "tipo_invalido_terceira_linha": _tipo_invalido_em_terceira_linha,
    "acao_desconhecida_com_linha_quebrada": _acao_desconhecida_com_linha_quebrada,
}


@pytest.mark.parametrize("nome_caso", sorted(CASOS_DE_RECUSA))
def test_recusa_com_partidas_validas_batendo_nunca_diz_fecha(client, cen, nome_caso):
    """A ÚNICA asserção da invariante, aplicada a cada um dos oito casos —
    quatro do relatório do auditor, quatro além dele. Nenhum caso é
    verificado por um texto de mensagem específico: a guarda é genérica de
    propósito (AGENTS.md exige que a correção não seja "do tamanho exato
    do achado")."""
    assert client.login(username="gestora-bl307", password="senha-forte-123")
    chave = f"k-bl307-{nome_caso}"
    corpo = CASOS_DE_RECUSA[nome_caso](_corpo_base(cen, chave))

    resposta = client.post(_url_tela(cen), corpo)

    assert resposta.status_code == 400, (
        f"pré-condição do caso {nome_caso!r}: deveria ser recusado (400), "
        f"veio {resposta.status_code}"
    )
    html = resposta.content.decode("utf-8")
    assert MARCADOR_FECHA not in html, (
        f"invariante violada no caso {nome_caso!r}: resposta 400 contém "
        '"Fecha" — a mesma mentira do achado A1 da auditoria DL-024 rodada 3'
    )
    # Nenhum lançamento gravado nesta tentativa, seja qual for a chave que
    # de fato foi enviada (o caso `chave_idempotencia_grande_demais`
    # SUBSTITUI `chave` por uma string diferente, de propósito).
    assert LancamentoContabil.objects.count() == 0


def test_controle_positivo_gravar_com_sucesso_e_302_e_nao_renderiza_a_pagina(client, cen):
    """Controle: o MESMO corpo base (sem nenhuma quebra) tem de continuar
    gravando — 302, redireciona para o detalhe, nunca renderiza o
    formulário de novo. Sem este controle, a asserção acima poderia estar
    vácua por recusar TUDO indiscriminadamente."""
    assert client.login(username="gestora-bl307", password="senha-forte-123")
    corpo = _corpo_base(cen, "k-bl307-controle-positivo")

    resposta = client.post(_url_tela(cen), corpo)

    assert resposta.status_code == 302
    assert LancamentoContabil.objects.filter(chave_idempotencia="k-bl307-controle-positivo").exists()


def test_controle_positivo_adicionar_linha_com_partidas_batendo_diz_fecha_em_200(client, cen):
    """Controle da METADE que a invariante direta NÃO cobre: `adicionar_
    linha` com as duas partidas batendo mostra "Fecha" em 200 — não é
    recusa, é conferência, e não precisa (nem deve) virar 302. Prova que
    a guarda acima está escopada corretamente: ela nunca testa este caso
    como violação."""
    assert client.login(username="gestora-bl307", password="senha-forte-123")
    corpo = _corpo_base(cen, "k-bl307-adicionar-linha-fecha")
    corpo["acao"] = "adicionar_linha"

    resposta = client.post(_url_tela(cen), corpo)

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    assert MARCADOR_FECHA in html
    assert LancamentoContabil.objects.count() == 0


@pytest.mark.parametrize("nome_caso", sorted(CASOS_DE_RECUSA))
def test_recusa_tambem_nao_fecha_via_context_explicito(client, cen, nome_caso):
    """Complemento não-vácuo: além de o HTML não dizer "Fecha", o
    `veredito_fechamento` explícito no `context` também não pode ser
    `"fecha"` — cobre o caso em que um `especialista-frontend` mudasse o
    texto do template sem mudar a decisão do servidor, o que faria a
    asserção baseada só em HTML passar por acidente."""
    assert client.login(username="gestora-bl307", password="senha-forte-123")
    corpo = CASOS_DE_RECUSA[nome_caso](_corpo_base(cen, f"k-bl307-ctx-{nome_caso}"))

    resposta = client.post(_url_tela(cen), corpo)

    assert resposta.status_code == 400
    assert resposta.context["veredito_fechamento"] != "fecha", (
        f"caso {nome_caso!r}: context['veredito_fechamento'] == "
        f"{resposta.context['veredito_fechamento']!r} numa resposta 400"
    )
