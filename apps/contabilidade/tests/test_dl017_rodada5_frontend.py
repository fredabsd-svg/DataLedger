"""Correções da rodada 5 da auditoria da DL-017 (docs/auditorias/
2026-09-14-dl-017-rodada-5.md) atribuídas ao `especialista-frontend`:
R5-1/BL-140 (bloqueador — testes ficam em
`test_dl017_rodada2_frontend.py`, onde `_chromium_funciona` e
`_renderizar_e_medir` já viviam), R5-4/BL-143 e BL-146 (este arquivo), e
R5-6/BL-145 (parte da tela, ver a seção própria abaixo).

R5-2, R5-3, R5-5 são do `desenvolvedor-pleno`. R5-7 é do
`arquiteto-senior`. Dados 100% sintéticos, criados nos próprios testes.
"""

import inspect

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
    escritorio = Escritorio.objects.create(nome="Escritório rodada 5", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Rodada 5 Ltda", cnpj="11122233000183"
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
        username="gestora-r5", email="gestora-r5@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-r5", password="senha-forte-123")


def _url_lancamento(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _url_diario(cen):
    return reverse("contabilidade_web:diario", args=[cen["empresa"].id])


def _dados_base(cen, *, acao="gravar", data=None, chave):
    return {
        "acao": acao,
        "num_linhas": "2",
        "data": data if data is not None else timezone.localdate().isoformat(),
        "historico": "rodada 5",
        "chave_idempotencia": chave,
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "10,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "10,00",
    }


# ---------------------------------------------------------------------------
# R5-4/BL-143 — a gramática de data da TELA não tinha teste nenhum: três
# mutantes (MX4, MX9, MX10) sobreviviam a 683 testes. A correção trocou a
# cópia privada `_PADRAO_DATA_SIMPLES` por `apps.core.datas.para_data` (o
# ÚNICO julgador de data do repositório, BL-133) nos três pontos —
# `data` do lançamento e `inicio`/`fim` do período. Os testes abaixo
# reproduzem a MEDIÇÃO do auditor: "2026-W01-1" (data de SEMANA ISO, que
# `date.fromisoformat` aceita e reinterpreta em silêncio para
# 2025-12-29) precisa ser RECUSADA, nunca gravada.
# ---------------------------------------------------------------------------


def test_data_do_lancamento_recusa_semana_iso_nunca_reinterpreta(client, cen):
    """MX9 — efeito medido pelo auditor na cópia mutada: `POST
    lancamento_novo, data="2026-W01-1"` gravava `2025-12-29` com 302
    "gravado com sucesso". Com `para_data`, a mesma entrada é recusada:
    400, nada gravado.
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    dados = _dados_base(cen, data="2026-W01-1", chave="r5-4-semana-iso")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes
    assert "data válida" in resposta.content.decode().lower()


@pytest.mark.parametrize(
    "data_hostil",
    [
        "20260105",  # sem separador — aceito por fromisoformat, fora do contrato AAAA-MM-DD
        "2026-01-05T00:00:00",  # data-hora ISO completa
        "+2026-01-05",  # sinal de era estendida
        "2026-001",  # dia-do-ano ISO
    ],
)
def test_data_do_lancamento_recusa_formatos_fora_do_contrato(client, cen, data_hostil):
    """Mesma classe, mais formatos que `date.fromisoformat` aceita e o
    contrato anunciado ("use o formato AAAA-MM-DD") não inclui — a mesma
    lista que o BL-139 fechou na API (MQ mata 4), agora também pela tela.
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    dados = _dados_base(cen, data=data_hostil, chave=f"r5-4-{data_hostil}")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400, (data_hostil, resposta.status_code)
    assert LancamentoContabil.objects.count() == antes


def test_data_do_lancamento_com_digito_unicode_e_recusada(client, cen):
    """R2-2/R2-7, a mesma classe, agora no campo `data`: dígito Unicode
    (fullwidth) não pode ser reinterpretado como dígito ASCII pela
    gramática de data — mata o mutante MX4/MQ3 (`PADRAO_DATA_SIMPLES` com
    `\\d`, que casaria qualquer dígito decimal Unicode).
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    dados = _dados_base(cen, data="２０２６-０１-０５", chave="r5-4-digito-unicode")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes


def test_data_do_lancamento_valida_continua_gravando(client, cen):
    """Controle: uma data comum, no formato certo, continua funcionando."""
    _login(client, cen)
    dados = _dados_base(cen, data="2026-01-05", chave="r5-4-controle-valida")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 302
    lancamento = LancamentoContabil.objects.get(chave_idempotencia="r5-4-controle-valida")
    assert lancamento.data.isoformat() == "2026-01-05"


def test_periodo_recusa_semana_iso_nunca_reinterpreta(client, cen):
    """MX10 — mesma classe no período (Diário/Razão/Balancete):
    `inicio`/`fim` com data de semana ISO precisa ser recusado com
    mensagem, nunca reinterpretado em silêncio para outra data.
    """
    _login(client, cen)
    resposta = client.get(_url_diario(cen), {"inicio": "2026-W01-1", "fim": "2026-01-31"})
    assert resposta.status_code == 400, resposta.status_code
    assert "data inválida" in resposta.content.decode().lower()


def test_periodo_com_digito_unicode_e_recusado(client, cen):
    """Mesma classe do teste de `data` acima, agora em `inicio`/`fim`."""
    _login(client, cen)
    resposta = client.get(_url_diario(cen), {"inicio": "２０２６-０１-０１", "fim": "2026-01-31"})
    assert resposta.status_code == 400, resposta.status_code


def test_periodo_valido_continua_funcionando(client, cen):
    """Controle: um período comum, no formato certo, continua funcionando."""
    _login(client, cen)
    resposta = client.get(_url_diario(cen), {"inicio": "2026-01-01", "fim": "2026-01-31"})
    assert resposta.status_code == 200


def test_tela_nao_tem_mais_copia_privada_de_gramatica_de_data(client, cen):
    """ESTRUTURAL: a cópia privada `_PADRAO_DATA_SIMPLES` não existe mais
    em `views_web.py` — a tela usa `apps.core.datas.para_data`, o único
    julgador de data do repositório (BL-133), nos três pontos. Pega
    diretamente o retrocesso "alguém recriou a cópia privada" sem
    precisar rodar um POST.
    """
    assert not hasattr(views_web, "_PADRAO_DATA_SIMPLES")
    fonte = inspect.getsource(views_web)
    assert "para_data(" in fonte
    # `date.fromisoformat(` com parênteses é a CHAMADA real — a menção em
    # prosa nos comentários (explicando o defeito antigo) não tem parênteses.
    assert "date.fromisoformat(" not in fonte


# ---------------------------------------------------------------------------
# BL-146 — comentário como afirmação verificável: um comentário deste
# arquivo afirmava que "a API já usa `para_id`" quando não usava (R5-3).
# O `desenvolvedor-pleno` corrigiu a API nesta mesma rodada (BL-142), e o
# comentário foi atualizado para voltar a afirmar isso — mas agora com um
# teste que CONFERE a afirmação contra o código-fonte real de
# `apps.contabilidade.views`, para que uma futura mudança que desfizesse
# a correção da API (ou reintroduzisse a afirmação prematuramente, antes
# dela existir) reprove a suíte em vez de ficar errada em silêncio outra
# vez.
# ---------------------------------------------------------------------------


def test_comentario_sobre_julgador_partilhado_so_afirma_o_que_e_verificavel():
    """O comentário de importação de `para_id`, em `views_web.py`, não
    pode voltar a afirmar "a API já usa `para_id`" enquanto isso não for
    verdade. Confere as DUAS metades: (1) o comentário não faz a
    afirmação falsa hoje; (2) se e quando o comentário vier a afirmar que
    a API usa, o código de `apps.contabilidade.views` REALMENTE precisa
    usar `para_id` — a checagem vale nos dois sentidos, não só no de hoje.

    R6-3/BL-150 (rodada 6) — este teste era o **décimo-primeiro** caso
    registrado de "teste que não consegue falhar", e o mais irônico: ele
    existe para impedir que um comentário minta sobre um julgador
    partilhado, e a linha que decidia era

        api_de_fato_usa = "para_id" in inspect.getsource(views_api)

    com `para_id` aparecendo em **dois comentários** de `views.py`. O
    valor era permanentemente `True`: o mutante M17 (remover import E
    chamada, comentários intactos) matava 7 testes do BL-142 e **passava**
    aqui. Duas correções, que juntas fecham os dois jeitos de errar:

    1. A agulha passou a ser `"para_id("`, **com parêntese** — só a
       chamada tem; a menção em prosa vem entre acentos graves.
    2. O escopo passou a ser a **função citada** (`_extrair_itens`), não o
       módulo inteiro — molde de `test_extrair_itens_usa_para_id`, que é
       quem de fato pegou o M17.

    As outras 8 frases da mesma família (o auditor catalogou 7 e todas
    eram verdadeiras, e nenhuma tinha teste) estão em
    `test_dl019_frontend_afirmacoes_de_comentario.py`, com a prosa
    removida por `tokenize` em vez de por convenção de acento grave — que
    é a defesa geral da classe. Este teste continua aqui porque é o caso
    nomeado pelo achado, no arquivo do achado.
    """
    from apps.contabilidade import views as views_api

    fonte_views_web = inspect.getsource(views_web)
    marcador = "# IdentificadorInvalido/para_id:"
    inicio = fonte_views_web.index(marcador)
    fim = fonte_views_web.index("from apps.core.identificadores import", inicio)
    bloco_comentario = fonte_views_web[inicio:fim]

    afirma_que_api_usa = "API já usa `para_id`" in bloco_comentario or (
        "API já usa" in bloco_comentario and "NÃO usa" not in bloco_comentario
    )
    api_de_fato_usa = "para_id(" in inspect.getsource(views_api._extrair_itens)

    assert afirma_que_api_usa == api_de_fato_usa, (
        "O comentário sobre o julgador partilhado precisa concordar com o código: "
        f"afirma que a API usa = {afirma_que_api_usa}, API de fato usa = {api_de_fato_usa}."
    )


# ---------------------------------------------------------------------------
# R5-6/BL-145 (parte da tela) — "nenhum dado enviado numa requisição deixa
# de ser lido ou recusado" (BL-128) vale para TODOS os dicionários da
# requisição: `request.GET` numa rota de POST, e o cabeçalho
# `Idempotency-Key` quando o campo oculto do corpo (o contrato real desta
# tela) está ausente.
# ---------------------------------------------------------------------------


def test_querystring_num_post_e_recusada_nomeando_a_chave(client, cen):
    """Reprodução da medição do auditor: um par de partidas COMPLETO e
    BALANCEADO (500,00 D + 500,00 C) na QUERYSTRING de um POST que também
    tem duas partidas normais no corpo. Antes desta correção: 302
    "gravado com sucesso", só as duas partidas do corpo — o par da
    querystring não aparecia em lugar nenhum. Agora: 400, nada gravado,
    as chaves nomeadas na mensagem.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="r5-6-querystring")
    antes = LancamentoContabil.objects.count()
    url = _url_lancamento(cen) + (
        "?conta_3=" + str(cen["caixa"].id) + "&tipo_3=debito&valor_3=500,00"
        "&conta_4=" + str(cen["receita"].id) + "&tipo_4=credito&valor_4=500,00"
    )
    resposta = client.post(url, dados)
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes
    conteudo = resposta.content.decode()
    assert "parâmetros na url" in conteudo.lower()
    assert "conta_3" in conteudo


def test_post_sem_querystring_continua_gravando(client, cen):
    """Controle: um POST comum, sem querystring nenhuma, não é afetado."""
    _login(client, cen)
    dados = _dados_base(cen, chave="r5-6-controle-sem-querystring")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 302
    assert LancamentoContabil.objects.count() == 1


def test_idempotency_key_por_cabecalho_e_recusada_nao_duplica(client, cen):
    """Reprodução da medição do auditor: dois POSTs com o cabeçalho
    `Idempotency-Key` IGUAL, mas SEM `chave_idempotencia` no corpo. Antes
    desta correção: cada POST gerava uma chave aleatória nova
    (`uuid.uuid4().hex`) e GRAVAVA DUAS VEZES — a duplicidade que a chave
    de idempotência existe para impedir, na superfície errada. Agora:
    400 nos dois, nomeando o cabeçalho, nada gravado.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="")
    del dados["chave_idempotencia"]
    resposta1 = client.post(
        _url_lancamento(cen), dados, headers={"Idempotency-Key": "mesma-chave-por-cabecalho"}
    )
    resposta2 = client.post(
        _url_lancamento(cen), dados, headers={"Idempotency-Key": "mesma-chave-por-cabecalho"}
    )
    assert resposta1.status_code == 400, resposta1.status_code
    assert resposta2.status_code == 400, resposta2.status_code
    assert LancamentoContabil.objects.count() == 0
    assert "idempotency-key" in resposta1.content.decode().lower()


def test_post_com_chave_no_corpo_sem_cabecalho_continua_gravando(client, cen):
    """Controle: o contrato REAL desta tela (campo oculto no corpo, sem
    cabeçalho nenhum) continua funcionando sem qualquer recusa nova.
    """
    _login(client, cen)
    dados = _dados_base(cen, chave="r5-6-controle-sem-cabecalho")
    resposta = client.post(_url_lancamento(cen), dados)
    assert resposta.status_code == 302
    assert LancamentoContabil.objects.count() == 1
