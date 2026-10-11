"""DL-086, achado A-02 (NÍVEL 1) — estorno do livro-caixa exige MOTIVO.

O estorno de lançamento do livro-caixa passou a exigir motivo obrigatório —
mesmo contrato dos cinco estornos fiscais — gravado nos `detalhes` da trilha
de auditoria do registro `lancamento_caixa.estornado` (e não numa coluna do
lançamento: a tabela recusa TODO UPDATE no banco, gatilho da DL-069, e o
estorno cria uma linha NOVA sem tocar na original).

Critério 8 do plano (docs/planos/DL-086-revisao-de-layout-e-acessos.md):
estorno sem motivo é recusado; com motivo, o lançamento é estornado UMA vez
e o motivo sai na trilha; mês encerrado continua recusando (regressão
DL-053/054).

Mutantes que este arquivo derruba:
- `_normalizar_motivo_do_estorno` removida de `estornar_lancamento_caixa`:
  os testes de recusa (vazio, espaços, NUL, teto) falham — o reverso seria
  criado sem motivo;
- validação movida para DEPOIS da transação: `test_estorno_sem_motivo_nao_
  grava_nada` falha na fotografia (lock/INSERT teriam acontecido);
- caminho web/API contornando o serviço (validando na borda só): os testes
  de web e API com motivo inválido falham;
- guarda `estorno_de ⇒ motivo_estorno` removida de `criar_lancamento_caixa`
  (B2 da auditoria independente): `test_criar_reverso_direto_sem_motivo_e_
  recusado` falha — o reverso direto seria criado sem motivo na trilha.

Padrão do arquivo: fixtures compartilhados de test_dl053 (mesmo molde de
test_dl054), dados 100% sintéticos.
"""

# ruff: noqa: F811
# (as fixtures importadas são usadas como parâmetro, o padrão do repositório)
import json
from datetime import date

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.livro_caixa.models import LancamentoCaixa
from apps.livro_caixa.services import (
    MENSAGEM_MOTIVO_ESTORNO_OBRIGATORIO,
    TAMANHO_MAXIMO_MOTIVO_ESTORNO,
    LancamentoCaixaInvalido,
    MesCaixaEncerrado,
    criar_lancamento_caixa,
    estornar_lancamento_caixa,
)
from apps.livro_caixa.tests.test_dl053_fechamento_do_mes import (  # noqa: F401
    _cliente_logado,
    _encerrar,
    _fotografia,
    _lancar,
    _url,
    _usuario,
    cenario,
)

pytestmark = pytest.mark.django_db

MOTIVO = "Lançamento duplicado no importador de 02/2026."


# ---------------------------------------------------------------------------
# Serviço — sucesso e recusa (a regra mora no serviço; tela e API chamam)
# ---------------------------------------------------------------------------


def test_estorno_com_motivo_cria_reverso_unico_e_grava_o_motivo_na_trilha(cenario):
    original = _lancar(cenario, date(2026, 1, 10))

    estorno = estornar_lancamento_caixa(original, motivo=MOTIVO, criado_por=cenario["gestor"])

    # Reverso único, mesma conta e mesmo valor, amarrado ao original.
    assert estorno.estorno_de == original
    assert estorno.conta_id == original.conta_id
    assert estorno.valor == original.valor
    assert LancamentoCaixa.objects.filter(estorno_de=original).count() == 1

    # O motivo está na TRILHA do ato de estornar.
    (registro,) = RegistroAuditoria.objects.filter(acao="lancamento_caixa.estornado")
    assert registro.detalhes["motivo_estorno"] == MOTIVO
    assert registro.usuario_id == cenario["gestor"].id

    # E NUNCA no lançamento: a linha gravada não carrega o motivo (o texto é
    # fato do ato, não conteúdo contábil — ver docstring do serviço).
    campos = [estorno.historico, estorno.recebido_de or "", str(estorno.valor)]
    assert all(MOTIVO not in campo for campo in campos)


def test_estorno_sem_motivo_nao_grava_nada(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(LancamentoCaixaInvalido) as exc:
        estornar_lancamento_caixa(original, motivo="", criado_por=cenario["gestor"])

    assert "motivo" in str(exc.value).lower()
    assert _fotografia(cenario["empresa"]) == antes


def test_estorno_com_motivo_de_espacos_e_recusado(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(LancamentoCaixaInvalido):
        estornar_lancamento_caixa(original, motivo="   \t  ", criado_por=cenario["gestor"])

    assert _fotografia(cenario["empresa"]) == antes


def test_estorno_com_caractere_nulo_e_recusado(cenario):
    """O PostgreSQL não grava o caractere nulo em texto (jsonb dos `detalhes`
    da trilha incluído) — sem a recusa explícita, o motivo daria 500 no
    INSERT da trilha e derrubaria o estorno inteiro depois de gravado."""
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(LancamentoCaixaInvalido):
        estornar_lancamento_caixa(
            original, motivo="motivo com nul\x00 aqui", criado_por=cenario["gestor"]
        )

    assert _fotografia(cenario["empresa"]) == antes


def test_estorno_com_motivo_acima_do_teto_e_recusado(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])
    motivo_longo = "x" * (TAMANHO_MAXIMO_MOTIVO_ESTORNO + 1)

    with pytest.raises(LancamentoCaixaInvalido) as exc:
        estornar_lancamento_caixa(original, motivo=motivo_longo, criado_por=cenario["gestor"])

    assert str(TAMANHO_MAXIMO_MOTIVO_ESTORNO) in str(exc.value)
    assert _fotografia(cenario["empresa"]) == antes


def test_estorno_com_motivo_do_teto_exato_e_aceito(cenario):
    """Limite do teto: o maior motivo aceito estorna normalmente (o corte é
    acima de `TAMANHO_MAXIMO_MOTIVO_ESTORNO`, não nele)."""
    original = _lancar(cenario, date(2026, 1, 10))
    motivo_do_teto = "m" * TAMANHO_MAXIMO_MOTIVO_ESTORNO

    estorno = estornar_lancamento_caixa(
        original, motivo=motivo_do_teto, criado_por=cenario["gestor"]
    )

    assert estorno.estorno_de == original
    (registro,) = RegistroAuditoria.objects.filter(acao="lancamento_caixa.estornado")
    assert registro.detalhes["motivo_estorno"] == motivo_do_teto


def test_estorno_com_motivo_que_nao_e_texto_e_recusado(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(LancamentoCaixaInvalido):
        estornar_lancamento_caixa(original, motivo=123, criado_por=cenario["gestor"])

    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize("motivo_direto", [None, ""], ids=["sem-motivo", "motivo-vazio"])
def test_criar_reverso_direto_sem_motivo_e_recusado(cenario, motivo_direto):
    """B2 (rodada 1 da auditoria independente) + N1 (reconferência): guarda
    de consistência — `criar_lancamento_caixa(..., estorno_de=X)` sem
    `motivo_estorno` (ou com ele vazio) é recusado, para o chamador FUTURO
    (shell, importador, MCP) não criar um estorno cuja trilha sai sem motivo.
    Mutante derrubado: remover a guarda do início de `criar_lancamento_caixa`
    — ou enfraquecê-la para `is None` (a variante vazia passaria)."""
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(LancamentoCaixaInvalido):
        criar_lancamento_caixa(
            empresa=cenario["empresa"],
            conta=cenario["conta"],
            data=date(2026, 1, 11),
            valor="100.00",
            historico="Reverso direto sem motivo",
            recebido_de="PJ",
            criado_por=cenario["gestor"],
            estorno_de=original,
            motivo_estorno=motivo_direto,
        )

    assert _fotografia(cenario["empresa"]) == antes


def test_mes_encerrado_continua_recusando_mesmo_com_motivo(cenario):
    """Regressão DL-053/054: o motivo novo não pode enfraquecer a trava de
    mês encerrado — o caminho continua sendo reabrir o mês, com motivo."""
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, ano=2026, mes=1)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(MesCaixaEncerrado):
        estornar_lancamento_caixa(original, motivo=MOTIVO, criado_por=cenario["gestor"])

    assert _fotografia(cenario["empresa"]) == antes


# ---------------------------------------------------------------------------
# Tela — o formulário exige o motivo e o que foi digitado volta no erro
# ---------------------------------------------------------------------------


def _url_estornar_web(cenario, lancamento):
    return reverse(
        "livro_caixa_web:lancamento_estornar",
        args=[cenario["empresa"].id, lancamento.id],
    )


def test_tela_de_estorno_mostra_o_campo_de_motivo_obrigatorio(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    cliente = _cliente_logado(cenario["gestor"])

    resposta = cliente.get(_url_estornar_web(cenario, original))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert 'name="motivo"' in corpo
    assert "required" in corpo
    assert 'aria-describedby="id_motivo_ajuda"' in corpo
    assert f'maxlength="{TAMANHO_MAXIMO_MOTIVO_ESTORNO}"' in corpo


def test_tela_de_estorno_sem_motivo_nao_estorna(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(cenario["gestor"])

    resposta = cliente.post(_url_estornar_web(cenario, original), {"motivo": ""})

    assert resposta.status_code == 400
    assert MENSAGEM_MOTIVO_ESTORNO_OBRIGATORIO in resposta.content.decode()
    assert _fotografia(cenario["empresa"]) == antes


def test_tela_de_estorno_preserva_o_digitado_quando_o_motivo_e_recusado(cenario):
    """Arquétipo B (§2 da direção de arte): o formulário não some no erro —
    o que a pessoa digitou continua lá. Motivo acima do teto é o erro que dá
    para distinguir no corpo sem depender de espaço em branco invisível."""
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(cenario["gestor"])
    digitado = "Justificativa longa que estoura o teto: " + "y" * (
        TAMANHO_MAXIMO_MOTIVO_ESTORNO + 1
    )

    resposta = cliente.post(_url_estornar_web(cenario, original), {"motivo": digitado})

    assert resposta.status_code == 400
    assert _fotografia(cenario["empresa"]) == antes
    assert "Justificativa longa que estoura o teto:" in resposta.content.decode()


def test_tela_de_estorno_com_motivo_estorna_e_grava_na_trilha(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    cliente = _cliente_logado(cenario["gestor"])

    resposta = cliente.post(_url_estornar_web(cenario, original), {"motivo": MOTIVO})

    assert resposta.status_code == 302
    assert LancamentoCaixa.objects.filter(estorno_de=original).count() == 1
    (registro,) = RegistroAuditoria.objects.filter(acao="lancamento_caixa.estornado")
    assert registro.detalhes["motivo_estorno"] == MOTIVO


# ---------------------------------------------------------------------------
# API — mesma regra, mesma voz (o serviço; a borda só traduz o erro de campo)
# ---------------------------------------------------------------------------


def test_api_de_estorno_sem_motivo_e_400_sem_gravar(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(cenario["gestor"])

    resposta = cliente.post(
        _url("estornar", cenario["empresa"].id, original.id),
        data=json.dumps({}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "motivo" in resposta.content.decode().lower()
    assert _fotografia(cenario["empresa"]) == antes


def test_api_de_estorno_com_motivo_de_outro_tipo_e_400(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(cenario["gestor"])

    resposta = cliente.post(
        _url("estornar", cenario["empresa"].id, original.id),
        data=json.dumps({"motivo": 123}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "texto" in resposta.content.decode()
    assert _fotografia(cenario["empresa"]) == antes


def test_api_de_estorno_com_motivo_estorna_e_grava_na_trilha(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    cliente = _cliente_logado(cenario["gestor"])

    resposta = cliente.post(
        _url("estornar", cenario["empresa"].id, original.id),
        data=json.dumps({"motivo": MOTIVO}),
        content_type="application/json",
    )

    assert resposta.status_code == 201
    assert LancamentoCaixa.objects.filter(estorno_de=original).count() == 1
    (registro,) = RegistroAuditoria.objects.filter(acao="lancamento_caixa.estornado")
    assert registro.detalhes["motivo_estorno"] == MOTIVO
