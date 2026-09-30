"""DL-053, critério 7 — a TELA do fechamento de mês do livro-caixa.

O servidor (modelo, serviços, trava, API) é coberto por
`test_dl053_fechamento_do_mes.py`. Aqui se prova que a tela:

* mostra os 12 meses, o estado e a autoria, e explica a falta de permissão;
* chama os serviços e traduz cada recusa em mensagem (nunca 500);
* recusa no SERVIDOR quem não pode fechar/reabrir (403 e banco inalterado),
  testado pela requisição e não pela presença do botão;
* isola escritórios (404) e modos de escrituração;
* não oferece lançar/estornar em mês encerrado, e o POST continua recusado;
* não deixa identificador interno (RC-, DE-, BL-...) aparecer para o contador.

Dados 100% sintéticos; datas em 2025 e 2026, sempre no passado.
"""

import itertools
import re
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    EstadoMesCaixa,
    FechamentoMesCaixa,
    LancamentoCaixa,
    NaturezaCaixa,
)
from apps.livro_caixa.services import (
    criar_lancamento_caixa,
    encerrar_mes_caixa,
    reabrir_mes_caixa,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

_SENHA = "senha-forte-123"
_SEQ = itertools.count(1)

PAPEIS_QUE_FECHAM = [Papel.ADMINISTRADOR, Papel.GESTOR]
PAPEIS_QUE_SO_LEEM = [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL]
PAPEIS_SEM_ACESSO = [Papel.CLIENTE]

# Códigos internos de regra/decisão/backlog que o contador nunca deve ler.
_IDENTIFICADOR_INTERNO = re.compile(r"\b(?:RC|DE|BL|HI|PE|DL)-\d+")


def _usuario(papel, escritorio):
    nome = f"{papel}-tela053-{next(_SEQ)}"
    usuario = get_user_model().objects.create_user(
        username=nome, email=f"{nome}@escritorio.com.br", password=_SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _cliente(papel, escritorio, **opcoes):
    usuario = _usuario(papel, escritorio)
    cliente = Client(raise_request_exception=False, **opcoes)
    assert cliente.login(username=usuario.username, password=_SENHA)
    cliente.usuario = usuario
    return cliente


def _montar_empresa(escritorio, razao_social, cpf):
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social=razao_social,
        tipo_inscricao=TipoInscricao.CPF,
        cpf=cpf,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    conta = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="R1",
        nome="Honorários recebidos",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    return empresa, conta


@pytest.fixture
def cenario():
    escritorio_a = Escritorio.objects.create(nome="Escritório Tela053 A", cnpj="51000000000153")
    escritorio_b = Escritorio.objects.create(nome="Escritório Tela053 B", cnpj="52000000000153")
    empresa, conta = _montar_empresa(escritorio_a, "Fulano Tela053", "12345678909")
    empresa_b, _ = _montar_empresa(escritorio_b, "Ciclano Tela053", "22255588846")
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Empresa Contabilidade Tela053 Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa": empresa,
        "conta": conta,
        "empresa_b": empresa_b,
        "empresa_contabilidade": empresa_contabilidade,
        "autor": _usuario(Papel.GESTOR, escritorio_a),
    }


def _lancar(cenario, data, valor="100.00", historico="Honorários Tela053"):
    return criar_lancamento_caixa(
        empresa=cenario["empresa"],
        conta=cenario["conta"],
        data=data,
        valor=valor,
        historico=historico,
        recebido_de="PJ",
        criado_por=cenario["autor"],
    )


def _encerrar(cenario, ano=2026, mes=1):
    return encerrar_mes_caixa(
        empresa=cenario["empresa"], ano=ano, mes=mes, usuario=cenario["autor"]
    )


def _reabrir(cenario, ano=2026, mes=1, motivo="Corrigir lançamento"):
    return reabrir_mes_caixa(
        empresa=cenario["empresa"], ano=ano, mes=mes, usuario=cenario["autor"], motivo=motivo
    )


def _fotografia(*empresas):
    """O que precisa ficar IGUAL quando uma operação é recusada."""
    return {
        "lancamentos": sorted(
            LancamentoCaixa.objects.filter(empresa__in=empresas).values_list("id", flat=True)
        ),
        "fechamentos": sorted(
            FechamentoMesCaixa.objects.filter(empresa__in=empresas).values_list(
                "id",
                "ano",
                "mes",
                "estado",
                "fechado_em",
                "fechado_por_id",
                "reaberto_em",
                "reaberto_por_id",
                "motivo_reabertura",
            )
        ),
        "trilha": sorted(
            RegistroAuditoria.objects.filter(
                Q(acao__startswith="lancamento_caixa.")
                | Q(acao__startswith="fechamento_mes_caixa.")
            ).values_list("id", flat=True)
        ),
    }


def _url(nome, empresa, **consulta):
    url = reverse(f"livro_caixa_web:{nome}", args=[empresa.id])
    if consulta:
        url += "?" + "&".join(f"{k}={v}" for k, v in consulta.items())
    return url


def _texto(resposta):
    """HTML da resposta com os espaços em branco colapsados — o que o
    navegador mostraria em uma linha, sem depender da indentação do template."""
    return re.sub(r"\s+", " ", resposta.content.decode())


def _mensagens(resposta):
    return " ".join(str(m) for m in resposta.context["messages"]) if resposta.context else ""


# ---------------------------------------------------------------------------
# Painel: quem vê, quem vê as ações, e os estados
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", PAPEIS_QUE_FECHAM)
def test_painel_mostra_as_acoes_para_quem_pode_fechar(cenario, papel):
    _encerrar(cenario, mes=3)
    cliente = _cliente(papel, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "livro_caixa/fechamento_mes.html" in [t.name for t in resposta.templates]
    # Onze meses abertos oferecem "Encerrar"; o mês 03 encerrado oferece "Reabrir".
    assert html.count(_url("mes_encerrar", cenario["empresa"]) + "?ano=2026&amp;mes=") == 11
    assert html.count(_url("mes_reabrir", cenario["empresa"]) + "?ano=2026&amp;mes=3") == 1
    assert "não encerrar nem reabrir" not in html


@pytest.mark.parametrize("papel", PAPEIS_QUE_SO_LEEM)
def test_painel_para_quem_so_le_mostra_tudo_mas_nenhuma_acao_e_explica(cenario, papel):
    _encerrar(cenario, mes=3)
    cliente = _cliente(papel, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    # O painel inteiro continua legível: estado e autoria.
    assert "Encerrado" in html
    assert cenario["autor"].username in html
    # Nenhuma ação de fechar/reabrir, e a explicação está em TEXTO.
    assert "/fechamento-de-mes/encerrar/" not in html
    assert "/fechamento-de-mes/reabrir/" not in html
    assert "exige administrador ou gestor" in html


@pytest.mark.parametrize("papel", PAPEIS_SEM_ACESSO)
def test_painel_nega_quem_nao_le_o_livro_caixa(cenario, papel):
    cliente = _cliente(papel, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"]))

    assert resposta.status_code == 403
    assert cenario["empresa"].razao_social not in resposta.content.decode()


def test_painel_lista_os_12_meses_com_estado_autoria_reabertura_e_motivo(cenario):
    _encerrar(cenario, mes=1)
    _encerrar(cenario, mes=2)
    _reabrir(cenario, mes=2, motivo="Conferir recibo de fevereiro")
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026))

    html = _texto(resposta)
    assert resposta.status_code == 200
    for mes in range(1, 13):
        assert f"{mes:02d}/2026" in html
    meses = {m["mes"]: m for m in resposta.context["meses"]}
    assert len(meses) == 12
    assert meses[1]["encerrado"] is True
    assert meses[2]["encerrado"] is False
    assert meses[5]["encerrado"] is False
    # Janeiro: quem e quando (nome e data em pt-BR); fevereiro: reabertura e motivo.
    assert "Encerrado por" in html
    assert cenario["autor"].username in html
    assert "Última reabertura por" in html
    assert "Conferir recibo de fevereiro" in html
    assert "Último encerramento por" in html
    assert re.search(r"\d{2}/\d{2}/2026 \d{2}:\d{2}", html)
    # Resumo do ano em texto (1 mês encerrado de 12).
    assert "1 mês de 2026 está encerrado" in html


def test_painel_estado_vazio_nenhum_mes_encerrado(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Nenhum mês de 2026 está encerrado" in html
    assert html.count("Nunca encerrado.") == 12
    assert "Encerrado</strong>" not in html


def test_painel_sem_ano_usa_o_ano_corrente(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"]))

    assert resposta.status_code == 200
    assert len(resposta.context["meses"]) == 12


@pytest.mark.parametrize("ano", ["abc", "3000", "1969", "-1", "2026.5", "٢٠٢٦"])
def test_painel_estado_de_erro_ano_invalido_da_400_com_mensagem_e_saida(cenario, ano):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=ano))

    assert resposta.status_code == 400
    html = resposta.content.decode()
    assert "O ano informado não é válido" in html
    assert "Não foi possível abrir este ano" in html
    assert "Ver o ano" in html  # caminho de volta


def test_painel_recusa_empresa_em_modo_contabilidade(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa_contabilidade"]))

    assert resposta.status_code == 403


def test_painel_so_aceita_leitura(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.post(_url("fechamento_mes", cenario["empresa"]))

    assert resposta.status_code == 405


# ---------------------------------------------------------------------------
# Encerrar: POST por quem pode, efeito e mensagem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", PAPEIS_QUE_FECHAM)
def test_encerrar_pela_tela_grava_estado_autoria_trilha_e_mostra_sucesso(cenario, papel):
    cliente = _cliente(papel, cenario["escritorio_a"])

    resposta = cliente.post(
        _url("mes_encerrar", cenario["empresa"]), {"ano": "2026", "mes": "4"}, follow=True
    )

    assert resposta.status_code == 200
    fechamento = FechamentoMesCaixa.objects.get(empresa=cenario["empresa"], ano=2026, mes=4)
    assert fechamento.estado == EstadoMesCaixa.ENCERRADO
    assert fechamento.fechado_por == cliente.usuario
    assert RegistroAuditoria.objects.filter(
        acao="fechamento_mes_caixa.encerrado", usuario=cliente.usuario
    ).exists()
    assert "Mês 04/2026 do livro-caixa de Fulano Tela053 encerrado com sucesso" in (
        resposta.content.decode()
    )
    # A tela seguinte é o painel do MESMO ano, já mostrando o mês encerrado.
    assert resposta.context["ano"] == 2026
    assert {m["mes"]: m["encerrado"] for m in resposta.context["meses"]}[4] is True


@pytest.mark.parametrize("papel", PAPEIS_QUE_SO_LEEM + PAPEIS_SEM_ACESSO)
def test_encerrar_por_papel_sem_permissao_da_403_e_nao_altera_o_banco(cenario, papel):
    cliente = _cliente(papel, cenario["escritorio_a"])
    antes = _fotografia(cenario["empresa"])

    # A requisição FORÇADA, sem passar pelo botão (que nem aparece para eles).
    resposta_post = cliente.post(
        _url("mes_encerrar", cenario["empresa"]), {"ano": "2026", "mes": "4"}
    )
    resposta_get = cliente.get(_url("mes_encerrar", cenario["empresa"], ano=2026, mes=4))

    assert resposta_post.status_code == 403
    assert resposta_get.status_code == 403
    assert _fotografia(cenario["empresa"]) == antes
    assert not FechamentoMesCaixa.objects.filter(empresa=cenario["empresa"]).exists()


def test_encerrar_sem_token_csrf_e_recusado_e_nao_altera_o_banco(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"], enforce_csrf_checks=True)
    antes = _fotografia(cenario["empresa"])

    resposta = cliente.post(_url("mes_encerrar", cenario["empresa"]), {"ano": "2026", "mes": "4"})

    assert resposta.status_code == 403
    assert _fotografia(cenario["empresa"]) == antes


def test_formularios_de_acao_levam_token_csrf_e_os_campos_ocultos(cenario):
    _encerrar(cenario, mes=1)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    encerrar = cliente.get(_url("mes_encerrar", cenario["empresa"], ano=2026, mes=2))
    reabrir = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1))

    for resposta in (encerrar, reabrir):
        html = resposta.content.decode()
        assert resposta.status_code == 200
        assert 'name="csrfmiddlewaretoken"' in html
        assert 'name="ano" value="2026"' in html
        assert 'method="post"' in html


def test_encerrar_mes_ja_encerrado_pelo_post_e_recusado_sem_efeito(cenario):
    primeiro = _encerrar(cenario, mes=4)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    antes = _fotografia(cenario["empresa"])

    resposta = cliente.post(
        _url("mes_encerrar", cenario["empresa"]), {"ano": "2026", "mes": "4"}, follow=True
    )

    assert resposta.status_code == 200
    assert "já está encerrado" in _mensagens(resposta)
    assert _fotografia(cenario["empresa"]) == antes
    primeiro.refresh_from_db()
    assert primeiro.fechado_por == cenario["autor"]  # o primeiro fechamento não é sobrescrito


@pytest.mark.parametrize(
    "dados",
    [
        {"ano": "2026", "mes": "13"},
        {"ano": "2026", "mes": "0"},
        {"ano": "2026", "mes": "abc"},
        {"ano": "abc", "mes": "4"},
        {"ano": "3000", "mes": "4"},
        {"mes": "4"},
        {},
    ],
)
def test_encerrar_com_ano_ou_mes_invalido_da_mensagem_e_nao_altera(cenario, dados):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.post(_url("mes_encerrar", cenario["empresa"]), dados, follow=True)

    assert resposta.status_code == 200
    assert "Erro:" in resposta.content.decode()
    assert not FechamentoMesCaixa.objects.filter(empresa=cenario["empresa"]).exists()


def test_encerrar_com_campo_nao_contratado_e_recusado_sem_efeito(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.post(
        _url("mes_encerrar", cenario["empresa"]),
        {"ano": "2026", "mes": "4", "estado": "encerrado"},
        follow=True,
    )

    assert resposta.status_code == 200
    assert not FechamentoMesCaixa.objects.filter(empresa=cenario["empresa"]).exists()


def test_tela_de_encerrar_mostra_o_que_o_mes_contem_antes_do_botao(cenario):
    _lancar(cenario, date(2026, 5, 10), valor="100.00")
    _lancar(cenario, date(2026, 5, 20), valor="50.50")
    _lancar(cenario, date(2026, 6, 1), valor="999.00")  # outro mês: não entra
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_encerrar", cenario["empresa"], ano=2026, mes=5))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "<h1>Encerrar mês 05/2026</h1>" in html
    assert "150,50" in html  # entradas e saldo do mês, somente de maio
    assert "999,00" not in html
    assert "2 lançamentos" in html
    assert "Encerrar mês 05/2026</button>" in html
    # Mesmo cálculo do relatório Livro Caixa: os totais batem com ele.
    relatorio = cliente.get(
        _url("relatorio", cenario["empresa"], inicio="2026-05-01", fim="2026-05-31")
    )
    assert "150,50" in relatorio.content.decode()


def test_tela_de_encerrar_mes_vazio_diz_que_nao_tem_lancamento(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_encerrar", cenario["empresa"], ano=2026, mes=2))

    html = resposta.content.decode()
    assert "não tem nenhum lançamento" in html
    assert "0,00" in html


def test_tela_de_encerrar_mes_em_curso_avisa(cenario):
    from django.utils import timezone

    hoje = timezone.localdate()
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_encerrar", cenario["empresa"], ano=hoje.year, mes=hoje.month))

    assert "ainda não terminou" in resposta.content.decode()


def test_get_de_encerrar_mes_ja_encerrado_volta_ao_painel_com_aviso(cenario):
    _encerrar(cenario, mes=4)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_encerrar", cenario["empresa"], ano=2026, mes=4), follow=True)

    assert resposta.redirect_chain
    assert "já está encerrado" in _mensagens(resposta)


# ---------------------------------------------------------------------------
# Reabrir: motivo obrigatório, efeito, recusas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", PAPEIS_QUE_FECHAM)
def test_reabrir_pela_tela_grava_motivo_autoria_trilha_e_mostra_sucesso(cenario, papel):
    _encerrar(cenario, mes=4)
    cliente = _cliente(papel, cenario["escritorio_a"])

    resposta = cliente.post(
        _url("mes_reabrir", cenario["empresa"]),
        {"ano": "2026", "mes": "4", "motivo": "  Corrigir recibo de abril  "},
        follow=True,
    )

    assert resposta.status_code == 200
    fechamento = FechamentoMesCaixa.objects.get(empresa=cenario["empresa"], ano=2026, mes=4)
    assert fechamento.estado == EstadoMesCaixa.ABERTO
    assert fechamento.motivo_reabertura == "Corrigir recibo de abril"
    assert fechamento.reaberto_por == cliente.usuario
    registro = RegistroAuditoria.objects.get(acao="fechamento_mes_caixa.reaberto")
    assert registro.usuario == cliente.usuario
    assert "Mês 04/2026 do livro-caixa de Fulano Tela053 reaberto com sucesso" in (
        resposta.content.decode()
    )
    # E o painel mostra o motivo, em texto.
    assert "Corrigir recibo de abril" in resposta.content.decode()


@pytest.mark.parametrize("papel", PAPEIS_QUE_SO_LEEM + PAPEIS_SEM_ACESSO)
def test_reabrir_por_papel_sem_permissao_da_403_e_nao_altera_o_banco(cenario, papel):
    _encerrar(cenario, mes=4)
    cliente = _cliente(papel, cenario["escritorio_a"])
    antes = _fotografia(cenario["empresa"])

    resposta_post = cliente.post(
        _url("mes_reabrir", cenario["empresa"]),
        {"ano": "2026", "mes": "4", "motivo": "Tentativa sem permissão"},
    )
    resposta_get = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=4))

    assert resposta_post.status_code == 403
    assert resposta_get.status_code == 403
    assert _fotografia(cenario["empresa"]) == antes
    assert mes_ainda_encerrado(cenario, 4)


def mes_ainda_encerrado(cenario, mes):
    return FechamentoMesCaixa.objects.filter(
        empresa=cenario["empresa"], ano=2026, mes=mes, estado=EstadoMesCaixa.ENCERRADO
    ).exists()


@pytest.mark.parametrize("motivo", ["", "   ", "\n\t"])
def test_reabrir_sem_motivo_volta_ao_formulario_com_erro_e_nada_muda(cenario, motivo):
    _encerrar(cenario, mes=4)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    antes = _fotografia(cenario["empresa"])

    resposta = cliente.post(
        _url("mes_reabrir", cenario["empresa"]), {"ano": "2026", "mes": "4", "motivo": motivo}
    )

    assert resposta.status_code == 400
    html = resposta.content.decode()
    assert "livro_caixa/fechamento_mes_reabrir.html" in [t.name for t in resposta.templates]
    assert "Informe o motivo da reabertura" in html  # erro em TEXTO, com o que fazer
    assert '<label for="id_motivo">Motivo da reabertura</label>' in html
    assert _fotografia(cenario["empresa"]) == antes
    assert mes_ainda_encerrado(cenario, 4)


def test_reabrir_com_motivo_longo_demais_preserva_o_que_foi_digitado(cenario):
    _encerrar(cenario, mes=4)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    antes = _fotografia(cenario["empresa"])
    motivo = "x" * 1001

    resposta = cliente.post(
        _url("mes_reabrir", cenario["empresa"]), {"ano": "2026", "mes": "4", "motivo": motivo}
    )

    assert resposta.status_code == 400
    assert motivo in resposta.content.decode()  # o formulário NÃO some nem perde o texto
    assert _fotografia(cenario["empresa"]) == antes


def test_reabrir_mes_aberto_pelo_post_e_recusado_sem_efeito(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    antes = _fotografia(cenario["empresa"])

    resposta = cliente.post(
        _url("mes_reabrir", cenario["empresa"]),
        {"ano": "2026", "mes": "4", "motivo": "Não havia o que reabrir"},
        follow=True,
    )

    assert resposta.status_code == 200
    assert "está aberto" in _mensagens(resposta)
    assert _fotografia(cenario["empresa"]) == antes


def test_get_de_reabrir_mes_aberto_volta_ao_painel_com_aviso(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=4), follow=True)

    assert resposta.redirect_chain
    assert "não está encerrado" in _mensagens(resposta)


def test_tela_de_reabrir_diz_quem_encerrou_e_o_que_acontece(cenario):
    _encerrar(cenario, mes=4)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=4))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert cenario["autor"].username in html
    assert "trilha de auditoria" in html
    assert "<textarea" in html and "required" in html
    assert "Reabrir mês 04/2026</button>" in html


def test_depois_de_reabrir_e_possivel_encerrar_de_novo_e_o_historico_aparece(cenario):
    _encerrar(cenario, mes=4)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    cliente.post(
        _url("mes_reabrir", cenario["empresa"]),
        {"ano": "2026", "mes": "4", "motivo": "Primeira correção"},
    )
    cliente.post(_url("mes_encerrar", cenario["empresa"]), {"ano": "2026", "mes": "4"})

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026))

    mes4 = {m["mes"]: m for m in resposta.context["meses"]}[4]
    assert mes4["encerrado"] is True
    assert mes4["motivo_reabertura"] == "Primeira correção"  # a última reabertura continua visível
    assert RegistroAuditoria.objects.filter(acao__startswith="fechamento_mes_caixa.").count() == 3


# ---------------------------------------------------------------------------
# Isolamento: escritório e modo de escrituração
# ---------------------------------------------------------------------------


def test_empresa_de_outro_escritorio_da_404_nas_tres_telas_e_nada_muda(cenario):
    encerrar_mes_caixa(
        empresa=cenario["empresa_b"],
        ano=2026,
        mes=4,
        usuario=_usuario(Papel.GESTOR, cenario["escritorio_b"]),
    )
    cliente = _cliente(Papel.ADMINISTRADOR, cenario["escritorio_a"])
    antes = _fotografia(cenario["empresa"], cenario["empresa_b"])
    empresa_b = cenario["empresa_b"]

    respostas = [
        cliente.get(_url("fechamento_mes", empresa_b, ano=2026)),
        cliente.get(_url("mes_encerrar", empresa_b, ano=2026, mes=5)),
        cliente.post(_url("mes_encerrar", empresa_b), {"ano": "2026", "mes": "5"}),
        cliente.get(_url("mes_reabrir", empresa_b, ano=2026, mes=4)),
        cliente.post(
            _url("mes_reabrir", empresa_b), {"ano": "2026", "mes": "4", "motivo": "Invasão"}
        ),
    ]

    assert [r.status_code for r in respostas] == [404] * 5
    assert _fotografia(cenario["empresa"], cenario["empresa_b"]) == antes
    # E o 404 não revela nada do cliente alheio.
    assert all("Ciclano" not in r.content.decode() for r in respostas)


def test_estado_do_mes_de_uma_empresa_nao_aparece_na_outra_do_mesmo_escritorio(cenario):
    irma, _ = _montar_empresa(cenario["escritorio_a"], "Beltrano Tela053", "11144477735")
    encerrar_mes_caixa(empresa=irma, ano=2026, mes=7, usuario=cenario["autor"])
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026))

    assert {m["mes"]: m["encerrado"] for m in resposta.context["meses"]}[7] is False
    assert "Beltrano" not in resposta.content.decode()


def test_acoes_de_fechamento_recusam_empresa_em_modo_contabilidade(cenario):
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    empresa = cenario["empresa_contabilidade"]

    respostas = [
        cliente.get(_url("mes_encerrar", empresa, ano=2026, mes=4)),
        cliente.post(_url("mes_encerrar", empresa), {"ano": "2026", "mes": "4"}),
        cliente.post(_url("mes_reabrir", empresa), {"ano": "2026", "mes": "4", "motivo": "x"}),
    ]

    assert [r.status_code for r in respostas] == [403] * 3
    assert not FechamentoMesCaixa.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Estado do mês nas telas de lançamento: aviso, ação ausente, servidor recusa
# ---------------------------------------------------------------------------


def test_lista_de_lancamentos_nao_oferece_estornar_em_mes_encerrado_e_diz_por_que(cenario):
    em_janeiro = _lancar(cenario, date(2026, 1, 10), historico="Lançamento de janeiro")
    em_fevereiro = _lancar(cenario, date(2026, 2, 10), historico="Lançamento de fevereiro")
    _encerrar(cenario, mes=1)
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    resposta = cliente.get(
        _url("lancamentos", cenario["empresa"], inicio="2026-01-01", fim="2026-02-28")
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Mês encerrado neste período:" in html
    assert "01/2026" in html
    assert "Mês encerrado</span>" in html
    assert f"/lancamentos/{em_janeiro.id}/estornar/" not in html
    assert f"/lancamentos/{em_fevereiro.id}/estornar/" in html  # mês aberto continua oferecendo
    # O servidor continua recusando o estorno forçado.
    forcado = cliente.post(
        reverse("livro_caixa_web:lancamento_estornar", args=[cenario["empresa"].id, em_janeiro.id])
    )
    assert forcado.status_code == 409


def test_lista_de_lancamentos_volta_a_oferecer_estornar_depois_de_reabrir(cenario):
    lancamento = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, mes=1)
    _reabrir(cenario, mes=1)
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    resposta = cliente.get(
        _url("lancamentos", cenario["empresa"], inicio="2026-01-01", fim="2026-01-31")
    )

    html = resposta.content.decode()
    assert "Mês encerrado neste período" not in html
    assert f"/lancamentos/{lancamento.id}/estornar/" in html


def test_lista_de_lancamentos_liga_ao_fechamento_de_mes(cenario):
    cliente = _cliente(Papel.PARALEGAL, cenario["escritorio_a"])

    resposta = cliente.get(_url("lancamentos", cenario["empresa"]))

    assert _url("fechamento_mes", cenario["empresa"]) in resposta.content.decode()


def test_formulario_de_lancamento_avisa_os_meses_encerrados(cenario):
    from django.utils import timezone

    ano = timezone.localdate().year
    encerrar_mes_caixa(empresa=cenario["empresa"], ano=ano, mes=1, usuario=cenario["autor"])
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    resposta = cliente.get(_url("lancamento_novo", cenario["empresa"]))

    html = resposta.content.decode()
    assert "Meses encerrados não recebem lançamento" in html
    assert f"01/{ano}" in html
    assert _url("fechamento_mes", cenario["empresa"]) in html


def test_formulario_de_lancamento_sem_mes_encerrado_nao_mostra_o_aviso(cenario):
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    resposta = cliente.get(_url("lancamento_novo", cenario["empresa"]))

    assert "Meses encerrados não recebem lançamento" not in resposta.content.decode()


def test_post_de_lancamento_em_mes_encerrado_continua_recusado_com_formulario_preenchido(cenario):
    _encerrar(cenario, mes=1)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    resposta = cliente.post(
        _url("lancamento_novo", cenario["empresa"]),
        {
            "data": "2026-01-20",
            "conta": cenario["conta"].id,
            "valor": "77,00",
            "historico": "Texto que não pode sumir",
            "recebido_de": "PJ",
            "cnpj_pagador": "11222333000181",
            "chave_idempotencia": "chave-tela053",
        },
    )

    assert resposta.status_code == 409
    html = resposta.content.decode()
    assert "está encerrado" in html
    assert "Texto que não pode sumir" in html
    assert _fotografia(cenario["empresa"]) == antes


def test_tela_de_estornar_em_mes_encerrado_nao_oferece_o_botao_e_o_post_segue_recusado(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, mes=1)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])
    url = reverse("livro_caixa_web:lancamento_estornar", args=[cenario["empresa"].id, original.id])

    pagina = cliente.get(url)
    forcado = cliente.post(url)

    html = pagina.content.decode()
    assert pagina.status_code == 200
    assert "Este mês está encerrado" in html
    # Nenhum formulário de estorno (o único POST da moldura é o "Sair").
    assert f'action="{url}"' not in html
    assert "disabled" in html  # o botão aparece desabilitado, com o motivo em texto
    assert _url("fechamento_mes", cenario["empresa"]) in html
    assert forcado.status_code == 409
    assert _fotografia(cenario["empresa"]) == antes
    # O 409 também já vem com a tela explicando, sem botão.
    assert "Este mês está encerrado" in forcado.content.decode()


def test_tela_de_estornar_em_mes_aberto_continua_oferecendo_o_botao(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    pagina = cliente.get(
        reverse("livro_caixa_web:lancamento_estornar", args=[cenario["empresa"].id, original.id])
    )

    html = pagina.content.decode()
    assert "Este mês está encerrado" not in html
    assert "Estornar lançamento nº" in html
    assert 'method="post"' in html


# ---------------------------------------------------------------------------
# Texto visível: nenhum identificador interno
# ---------------------------------------------------------------------------


def test_nenhuma_tela_do_fechamento_mostra_identificador_interno(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, mes=1)
    _encerrar(cenario, mes=2)
    _reabrir(cenario, mes=2, motivo="Motivo de teste")
    gestor = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    analista = _cliente(Papel.ANALISTA, cenario["escritorio_a"])
    paginas = [
        gestor.get(_url("fechamento_mes", cenario["empresa"], ano=2026)),
        gestor.get(_url("fechamento_mes", cenario["empresa"], ano="abc")),
        gestor.get(_url("mes_encerrar", cenario["empresa"], ano=2026, mes=3)),
        gestor.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1)),
        gestor.post(
            _url("mes_reabrir", cenario["empresa"]), {"ano": "2026", "mes": "1", "motivo": ""}
        ),
        gestor.post(
            _url("mes_encerrar", cenario["empresa"]), {"ano": "2026", "mes": "1"}, follow=True
        ),
        gestor.post(
            _url("mes_reabrir", cenario["empresa"]),
            {"ano": "2026", "mes": "3", "motivo": "x"},
            follow=True,
        ),
        analista.get(_url("fechamento_mes", cenario["empresa"], ano=2026)),
        analista.get(
            _url("lancamentos", cenario["empresa"], inicio="2026-01-01", fim="2026-02-28")
        ),
        analista.get(_url("lancamento_novo", cenario["empresa"])),
        analista.get(
            reverse(
                "livro_caixa_web:lancamento_estornar", args=[cenario["empresa"].id, original.id]
            )
        ),
        # A mensagem de estorno recusado (o texto do serviço cita um código).
        analista.post(
            reverse(
                "livro_caixa_web:lancamento_estornar", args=[cenario["empresa"].id, original.id]
            )
        ),
        analista.post(
            _url("mes_encerrar", cenario["empresa"]), {"ano": "2026", "mes": "1"}
        ),  # 403: a página de erro também
    ]

    for pagina in paginas:
        texto = re.sub(r"<!--.*?-->", "", pagina.content.decode(), flags=re.S)
        achados = _IDENTIFICADOR_INTERNO.findall(texto)
        assert not achados, f"identificador interno visível: {achados}"
