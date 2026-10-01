"""DL-054, critério 6 (e os critérios 1 a 4 PELA TELA) — a reabertura em
cascata e o aviso do encadeamento do carnê-leão.

O servidor (trava do lançamento, cascata, concorrência, API) é coberto por
`test_dl054_encadeamento.py`. Aqui se prova que a tela:

* na reabertura de um mês com meses encerrados depois dele no ano, mostra a
  LISTA deles antes do formulário, explica o encadeamento e oferece UMA ação
  ("Reabrir este mês e os seguintes encerrados") atrás de confirmação explícita;
* sem a confirmação, nada muda (a corrida volta ao formulário, 409, sem 500);
* com a confirmação, reabre todos numa vez, com um motivo, e a mensagem de
  sucesso lista os meses;
* exige o papel no SERVIDOR (ADMINISTRADOR e GESTOR; os demais 403, banco
  inalterado), o motivo, e isola escritórios (404);
* recusa lançar/estornar em mês aberto anterior a um encerrado, explica a
  regra no formulário e na lista, e não oferece o estorno;
* não deixa identificador interno (RC-, DE-, BL-...) aparecer.

Dados 100% sintéticos; datas em 2026, no passado.
"""

import itertools
import re
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import Client
from django.urls import reverse
from django.utils import timezone

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
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

_SENHA = "senha-forte-123"
_SEQ = itertools.count(1)
_MOTIVO = "Corrigir despesa de janeiro"

PAPEIS_QUE_FECHAM = [Papel.ADMINISTRADOR, Papel.GESTOR]
PAPEIS_QUE_NAO_FECHAM = [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE]

# Códigos internos de regra/decisão/backlog que o contador nunca deve ler.
_IDENTIFICADOR_INTERNO = re.compile(r"\b(?:RC|DE|BL|HI|PE|DL)-\d+")


def test_a_matriz_de_papeis_cobre_os_seis_papeis():
    # Se um papel novo surgir, este teste obriga a decidir se ele fecha mês.
    assert set(PAPEIS_QUE_FECHAM + PAPEIS_QUE_NAO_FECHAM) == set(Papel)


def _usuario(papel, escritorio):
    nome = f"{papel}-tela054-{next(_SEQ)}"
    usuario = get_user_model().objects.create_user(
        username=nome, email=f"{nome}@escritorio.com.br", password=_SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _cliente(papel, escritorio):
    usuario = _usuario(papel, escritorio)
    cliente = Client(raise_request_exception=False)
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
    escritorio_a = Escritorio.objects.create(nome="Escritório Tela054 A", cnpj="61000000000154")
    escritorio_b = Escritorio.objects.create(nome="Escritório Tela054 B", cnpj="62000000000154")
    empresa, conta = _montar_empresa(escritorio_a, "Fulano Tela054", "12345678909")
    outra, _ = _montar_empresa(escritorio_a, "Beltrano Tela054", "22255588846")
    de_outro_escritorio, _ = _montar_empresa(escritorio_b, "Ciclano Tela054", "39053344705")
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa": empresa,
        "conta": conta,
        "outra_empresa": outra,
        "empresa_b": de_outro_escritorio,
        "autor": _usuario(Papel.GESTOR, escritorio_a),
    }


def _lancar(cenario, data, valor="100.00", historico="Honorários Tela054"):
    return criar_lancamento_caixa(
        empresa=cenario["empresa"],
        conta=cenario["conta"],
        data=data,
        valor=valor,
        historico=historico,
        recebido_de="PJ",
        criado_por=cenario["autor"],
    )


def _encerrar(cenario, *meses, ano=2026, empresa=None):
    for mes in meses:
        encerrar_mes_caixa(
            empresa=empresa or cenario["empresa"], ano=ano, mes=mes, usuario=cenario["autor"]
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


def _url_estornar(empresa, lancamento):
    return reverse("livro_caixa_web:lancamento_estornar", args=[empresa.id, lancamento.id])


def _texto(resposta):
    """HTML com os espaços em branco colapsados — o que o navegador mostraria
    em uma linha, sem depender da indentação do template."""
    return re.sub(r"\s+", " ", resposta.content.decode())


def _mensagens(resposta):
    return " ".join(str(m) for m in resposta.context["messages"]) if resposta.context else ""


def _estados(cenario, empresa=None):
    linhas = FechamentoMesCaixa.objects.filter(empresa=empresa or cenario["empresa"], ano=2026)
    return {linha.mes: linha.estado for linha in linhas}


def _post_reabrir(cliente, cenario, *, mes=1, motivo=_MOTIVO, cascata=True, **extra):
    dados = {"ano": "2026", "mes": str(mes), "motivo": motivo}
    if cascata:
        dados["confirmar_cascata"] = "1"
    dados.update(extra)
    return cliente.post(_url("mes_reabrir", cenario["empresa"]), dados)


# ---------------------------------------------------------------------------
# Critério 6/1 — GET: a lista dos posteriores antes do formulário
# ---------------------------------------------------------------------------


def test_get_reabrir_janeiro_com_fevereiro_e_marco_encerrados_mostra_a_lista_antes_do_formulario(
    cenario,
):
    _encerrar(cenario, 1, 2, 3)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1))

    assert resposta.status_code == 200
    texto = _texto(resposta)
    # A lista dos meses que serão reabertos junto, com quem encerrou.
    assert "Reabrir 01/2026 exige reabrir também 2 meses encerrados de 2026" in texto
    for posterior in ("02/2026", "03/2026"):
        assert f"<strong>{posterior}</strong> — encerrado" in texto
    # A explicação do encadeamento, em linguagem de escritório.
    assert "O carnê-leão se encadeia de janeiro a dezembro" in texto
    assert "no mesmo ato e com o mesmo motivo" in texto
    # UMA ação: confirmação explícita + botão que diz o que vai acontecer.
    assert 'name="confirmar_cascata" value="1" required' in texto
    assert "Reabrir este mês e os seguintes encerrados (01/2026, 02/2026 e 03/2026)" in texto
    # A lista vem ANTES do formulário de reabertura.
    form = texto.index(f'action="{_url("mes_reabrir", cenario["empresa"])}"')
    assert texto.index("Reabrir 01/2026 exige reabrir também") < form
    assert texto.index("<strong>02/2026</strong> — encerrado") < form
    assert texto.index("<strong>03/2026</strong> — encerrado") < form
    # Ver a tela não muda nada.
    assert _estados(cenario) == {1: "encerrado", 2: "encerrado", 3: "encerrado"}


def test_get_reabrir_com_um_so_posterior_fala_no_singular(cenario):
    _encerrar(cenario, 1, 2)
    cliente = _cliente(Papel.ADMINISTRADOR, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1)))

    assert "exige reabrir também 1 mês encerrado de 2026" in texto
    assert "do mês seguinte já encerrado" in texto
    assert "Reabrir este mês e os seguintes encerrados (01/2026 e 02/2026)" in texto


def test_get_reabrir_o_ultimo_mes_encerrado_funciona_como_antes(cenario):
    _encerrar(cenario, 1, 2, 3)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=3))

    texto = _texto(resposta)
    assert resposta.status_code == 200
    assert "confirmar_cascata" not in texto
    assert "exige reabrir também" not in texto
    assert "Reabrir mês 03/2026" in texto
    assert "O mês volta a aceitar lançamento e estorno." in texto


def test_get_reabrir_so_lista_os_encerrados_do_mesmo_ano_e_posteriores(cenario):
    # 12/2025 e 01/2026 encerrados, 02/2026 aberto, 03/2026 encerrado.
    _encerrar(cenario, 12, ano=2025)
    _encerrar(cenario, 1, 3)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1)))

    assert "<strong>03/2026</strong> — encerrado" in texto
    assert "<strong>02/2026</strong>" not in texto  # aberto: não entra
    assert "12/2025" not in texto  # outro ano: não entra
    assert "(01/2026 e 03/2026)" in texto


# ---------------------------------------------------------------------------
# Critério 3 pela tela — sem confirmar nada muda; confirmando reabre os três
# ---------------------------------------------------------------------------


def test_post_sem_confirmar_a_cascata_volta_ao_formulario_com_a_lista_e_nao_muda_nada(cenario):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario, cascata=False, motivo="Motivo que não pode sumir")

    assert resposta.status_code == 409  # conflito de ESTADO, nunca 500
    texto = _texto(resposta)
    assert "Nada foi alterado" in _mensagens(resposta)
    assert "não pode ser reaberto sozinho" in _mensagens(resposta)
    assert "02/2026" in _mensagens(resposta) and "03/2026" in _mensagens(resposta)
    # A tela volta com a lista, a caixa de confirmação e o motivo digitado.
    assert "Reabrir 01/2026 exige reabrir também 2 meses encerrados de 2026" in texto
    assert 'name="confirmar_cascata"' in texto
    assert "Motivo que não pode sumir" in texto
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == {1: "encerrado", 2: "encerrado", 3: "encerrado"}


@pytest.mark.parametrize("valor", ["", "0", "on", "true", "sim", "2"])
def test_so_o_valor_1_confirma_a_cascata(cenario, valor):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario, cascata=False, confirmar_cascata=valor)

    assert resposta.status_code == 409
    assert _fotografia(cenario["empresa"]) == antes


def test_corrida_o_formulario_simples_foi_aberto_antes_de_outro_mes_ser_encerrado(cenario):
    # A pessoa abre a tela de janeiro quando só janeiro está encerrado (sem
    # caixa de confirmação); antes de enviar, alguém encerra fevereiro.
    _encerrar(cenario, 1)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    aberta = _texto(cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1)))
    assert "confirmar_cascata" not in aberta
    _encerrar(cenario, 2)
    antes = _fotografia(cenario["empresa"])

    resposta = _post_reabrir(cliente, cenario, cascata=False)

    assert resposta.status_code == 409
    texto = _texto(resposta)
    assert "<strong>02/2026</strong> — encerrado" in texto
    assert 'name="confirmar_cascata"' in texto
    assert _fotografia(cenario["empresa"]) == antes


def test_post_com_a_cascata_confirmada_reabre_os_tres_com_trilha_e_mensagem(cenario):
    _encerrar(cenario, 1, 2, 3)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario, motivo=f"  {_MOTIVO}  ")

    assert resposta.status_code == 302
    assert resposta["Location"] == _url("fechamento_mes", cenario["empresa"], ano=2026)
    assert _estados(cenario) == {1: "aberto", 2: "aberto", 3: "aberto"}
    for linha in FechamentoMesCaixa.objects.filter(empresa=cenario["empresa"]):
        assert linha.motivo_reabertura == _MOTIVO
        assert linha.reaberto_por == cliente.usuario
    trilha = list(
        RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").order_by("id")
    )
    assert [r.detalhes["mes"] for r in trilha] == [1, 2, 3]
    for registro in trilha:
        assert registro.usuario == cliente.usuario
        assert registro.detalhes["motivo"] == _MOTIVO
        assert registro.detalhes["cascata"] is True
        assert registro.detalhes["mes_de_origem"] == 1
    # A mensagem de sucesso lista os três meses.
    painel = cliente.get(resposta["Location"])
    mensagem = _mensagens(painel)
    assert "Meses 01/2026, 02/2026 e 03/2026 do livro-caixa de Fulano Tela054 reabertos" in mensagem
    assert "trilha de auditoria de cada um" in mensagem
    assert "03/2026" in _texto(painel)
    # E o painel mostra os três abertos.
    assert "Nenhum mês de 2026 está encerrado" in _texto(painel)


def test_depois_da_cascata_lancar_em_janeiro_e_aceito_pela_tela(cenario):
    _encerrar(cenario, 1, 2)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    _post_reabrir(cliente, cenario)

    resposta = cliente.post(
        _url("lancamento_novo", cenario["empresa"]),
        _dados_de_lancamento(cenario, "2026-01-20", historico="Depois da cascata"),
    )

    assert resposta.status_code == 302
    assert LancamentoCaixa.objects.filter(empresa=cenario["empresa"]).count() == 1


def test_cascata_nao_toca_nem_o_mes_aberto_nem_outro_ano_nem_outra_empresa(cenario):
    _encerrar(cenario, 12, ano=2025)
    _encerrar(cenario, 1, 3)
    _encerrar(cenario, 1, 2, 3, empresa=cenario["outra_empresa"])
    _encerrar(cenario, 1, 2, 3, empresa=cenario["empresa_b"])
    outras = _fotografia(cenario["outra_empresa"], cenario["empresa_b"])["fechamentos"]
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario)

    assert resposta.status_code == 302
    assert _estados(cenario) == {1: "aberto", 3: "aberto"}  # 02/2026 nunca teve linha
    assert FechamentoMesCaixa.objects.get(empresa=cenario["empresa"], ano=2025, mes=12).estado == (
        EstadoMesCaixa.ENCERRADO
    )
    assert _fotografia(cenario["outra_empresa"], cenario["empresa_b"])["fechamentos"] == outras


def test_cascata_confirmada_sem_posteriores_reabre_so_o_mes_e_a_mensagem_e_a_de_sempre(cenario):
    # A pessoa viu a caixa; antes de enviar, o posterior foi reaberto por outra.
    _encerrar(cenario, 1)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario)

    assert resposta.status_code == 302
    mensagem = _mensagens(cliente.get(resposta["Location"]))
    assert "Mês 01/2026 do livro-caixa de Fulano Tela054 reaberto com sucesso" in mensagem
    assert _estados(cenario) == {1: "aberto"}


def test_reabrir_sem_posteriores_pela_tela_continua_igual(cenario):
    _encerrar(cenario, 4)
    cliente = _cliente(Papel.ADMINISTRADOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario, mes=4, cascata=False)

    assert resposta.status_code == 302
    assert _estados(cenario) == {4: "aberto"}
    assert RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.reaberto").count() == 1
    registro = RegistroAuditoria.objects.get(acao="fechamento_mes_caixa.reaberto")
    assert "cascata" not in registro.detalhes


# ---------------------------------------------------------------------------
# Critério 4 pela tela — papéis (os seis), motivo, isolamento, contrato
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", PAPEIS_QUE_FECHAM)
def test_administrador_e_gestor_reabrem_em_cascata_pela_tela(cenario, papel):
    _encerrar(cenario, 1, 2, 3)
    cliente = _cliente(papel, cenario["escritorio_a"])

    assert cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1)).status_code == 200
    resposta = _post_reabrir(cliente, cenario)

    assert resposta.status_code == 302
    assert _estados(cenario) == {1: "aberto", 2: "aberto", 3: "aberto"}


@pytest.mark.parametrize("papel", PAPEIS_QUE_NAO_FECHAM)
def test_os_demais_papeis_recebem_403_e_o_banco_fica_inalterado(cenario, papel):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(papel, cenario["escritorio_a"])

    resposta_get = cliente.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1))
    resposta_post = _post_reabrir(cliente, cenario)
    resposta_post_simples = _post_reabrir(cliente, cenario, cascata=False)

    assert resposta_get.status_code == 403
    assert resposta_post.status_code == 403
    assert resposta_post_simples.status_code == 403
    assert _fotografia(cenario["empresa"]) == antes
    assert _estados(cenario) == {1: "encerrado", 2: "encerrado", 3: "encerrado"}


@pytest.mark.parametrize("motivo", ["", "    ", "\n\t"])
def test_motivo_e_obrigatorio_na_cascata_e_a_tela_volta_com_a_lista(cenario, motivo):
    _encerrar(cenario, 1, 2, 3)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario, motivo=motivo)

    assert resposta.status_code == 400
    texto = _texto(resposta)
    assert "motivo" in _mensagens(resposta).lower()
    assert "Reabrir 01/2026 exige reabrir também 2 meses encerrados de 2026" in texto
    assert 'name="confirmar_cascata"' in texto
    assert _fotografia(cenario["empresa"]) == antes


def test_motivo_longo_demais_na_cascata_preserva_o_que_foi_digitado(cenario):
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = _post_reabrir(cliente, cenario, motivo="x" * 5000)

    assert resposta.status_code == 400
    assert "x" * 100 in resposta.content.decode()
    assert _fotografia(cenario["empresa"]) == antes


def test_empresa_de_outro_escritorio_da_404_e_a_cascata_nao_acontece(cenario):
    _encerrar(cenario, 1, 2, 3, empresa=cenario["empresa_b"])
    antes = _fotografia(cenario["empresa_b"])
    cliente = _cliente(Papel.ADMINISTRADOR, cenario["escritorio_a"])

    resposta_get = cliente.get(_url("mes_reabrir", cenario["empresa_b"], ano=2026, mes=1))
    resposta_post = cliente.post(
        _url("mes_reabrir", cenario["empresa_b"]),
        {"ano": "2026", "mes": "1", "motivo": _MOTIVO, "confirmar_cascata": "1"},
    )

    assert resposta_get.status_code == 404
    assert resposta_post.status_code == 404
    assert _fotografia(cenario["empresa_b"]) == antes
    assert _estados(cenario, cenario["empresa_b"]) == {
        1: "encerrado",
        2: "encerrado",
        3: "encerrado",
    }


def test_campo_nao_contratado_e_recusado_sem_efeito(cenario):
    # `cascata` é o nome do campo da API JSON; na tela o único campo é
    # `confirmar_cascata`. Qualquer outro nome é recusado, nada muda.
    _encerrar(cenario, 1, 2)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.post(
        _url("mes_reabrir", cenario["empresa"]),
        {"ano": "2026", "mes": "1", "motivo": _MOTIVO, "cascata": "1"},
    )

    assert resposta.status_code == 302
    assert _fotografia(cenario["empresa"]) == antes


# ---------------------------------------------------------------------------
# Critério 6 — painel dos 12 meses: a ação diz que é em cascata
# ---------------------------------------------------------------------------


def test_painel_indica_que_reabrir_e_em_cascata_so_onde_ha_posteriores(cenario):
    _encerrar(cenario, 1, 2, 3)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    resposta = cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026))

    texto = _texto(resposta)
    assert resposta.status_code == 200
    # Janeiro e fevereiro têm encerrados depois: cascata, com os meses em texto.
    assert texto.count("Reabrir em cascata") == 2
    assert "Reabre também 02/2026, 03/2026." in texto
    assert "Reabre também 03/2026." in texto
    assert 'Reabrir em cascata<span class="visualmente-oculto"> o mês 01/2026 e os encerrados' in (
        texto
    )
    # Março é o último encerrado: "Reabrir" simples, sem aviso de cascata.
    assert re.search(r">Reabrir<span class=\"visualmente-oculto\"> o mês 03/2026", texto)
    # O texto geral do painel explica a regra.
    assert "reabrir um mês que tem meses encerrados depois dele reabre também esses meses" in texto


def test_painel_sem_encadeamento_nao_fala_em_cascata_na_acao(cenario):
    _encerrar(cenario, 5)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026)))

    assert "Reabrir em cascata" not in texto
    assert "Reabre também" not in texto


def test_painel_de_quem_so_le_nao_oferece_nem_anuncia_a_cascata(cenario):
    _encerrar(cenario, 1, 2)
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2026)))

    assert "Reabrir em cascata" not in texto
    assert "Reabre também" not in texto
    assert _url("mes_reabrir", cenario["empresa"]) + "?ano" not in texto


def test_painel_mostra_apenas_o_ano_consultado_para_a_cascata(cenario):
    _encerrar(cenario, 12, ano=2025)
    _encerrar(cenario, 1)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("fechamento_mes", cenario["empresa"], ano=2025)))

    assert "Reabrir em cascata" not in texto  # 12/2025 é o último do ano de 2025


# ---------------------------------------------------------------------------
# Critérios 1 e 6 pela tela — lançar/estornar antes de um mês encerrado
# ---------------------------------------------------------------------------


def _dados_de_lancamento(cenario, data, historico="Texto que não pode sumir"):
    return {
        "data": data,
        "conta": cenario["conta"].id,
        "valor": "77,00",
        "historico": historico,
        "documento_origem": "",
        "recebido_de": "PJ",
        "cpf_titular_pagamento": "",
        "cpf_beneficiario_servico": "",
        "cnpj_pagador": "",
        "chave_idempotencia": f"chave-tela054-{next(_SEQ)}",
    }


def test_lancar_em_janeiro_com_fevereiro_encerrado_pela_tela_da_409_com_mensagem(cenario):
    _encerrar(cenario, 2)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    resposta = cliente.post(
        _url("lancamento_novo", cenario["empresa"]), _dados_de_lancamento(cenario, "2026-01-20")
    )

    assert resposta.status_code == 409
    texto = _texto(resposta)
    assert "O mês 02/2026 do livro-caixa de Fulano Tela054 está encerrado" in texto
    assert "carnê-leão" in texto
    assert "Reabra 02/2026" in texto
    assert "Texto que não pode sumir" in texto  # formulário volta preenchido
    assert _fotografia(cenario["empresa"]) == antes


def test_lancar_depois_do_mes_encerrado_ou_em_outro_ano_continua_aceito(cenario):
    _encerrar(cenario, 2)
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    em_marco = cliente.post(
        _url("lancamento_novo", cenario["empresa"]), _dados_de_lancamento(cenario, "2026-03-05")
    )
    em_2025 = cliente.post(
        _url("lancamento_novo", cenario["empresa"]), _dados_de_lancamento(cenario, "2025-12-05")
    )

    assert em_marco.status_code == 302
    assert em_2025.status_code == 302


def test_estornar_em_janeiro_com_fevereiro_encerrado_explica_e_nao_oferece_o_botao(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, 2)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])
    url = _url_estornar(cenario["empresa"], original)

    pagina = cliente.get(url)
    forcado = cliente.post(url)

    texto = _texto(pagina)
    assert pagina.status_code == 200
    assert "Há um mês encerrado depois deste" in texto
    assert "<strong>02/2026</strong>" in texto
    assert f'action="{url}"' not in texto  # nenhum formulário de estorno
    assert "disabled" in texto
    assert _url("fechamento_mes", cenario["empresa"], ano=2026) in texto
    assert forcado.status_code == 409
    mensagem = _mensagens(forcado)
    assert "02/2026" in mensagem and "carnê-leão" in mensagem
    assert "Há um mês encerrado depois deste" in _texto(forcado)
    assert _fotografia(cenario["empresa"]) == antes


def test_estornar_em_mes_sem_encerrado_depois_continua_oferecendo_o_botao(cenario):
    original = _lancar(cenario, date(2026, 3, 10))
    _encerrar(cenario, 2)
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url_estornar(cenario["empresa"], original)))

    assert "Há um mês encerrado depois deste" not in texto
    assert "Estornar lançamento nº" in texto
    assert 'method="post"' in texto


def test_formulario_de_lancamento_explica_a_regra_do_encadeamento(cenario):
    ano = timezone.localdate().year
    encerrar_mes_caixa(empresa=cenario["empresa"], ano=ano, mes=2, usuario=cenario["autor"])
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("lancamento_novo", cenario["empresa"])))

    assert "Meses encerrados não recebem lançamento" in texto
    assert f"02/{ano}" in texto
    assert "Também não recebe lançamento um mês anterior a um mês encerrado do mesmo ano" in texto
    assert "o carnê-leão se encadeia de janeiro a dezembro" in texto
    assert f"Meses abertos que recusam por isso: 01/{ano}." in texto
    assert _url("fechamento_mes", cenario["empresa"], ano=ano) in texto


def test_formulario_sem_mes_encerrado_nao_mostra_nenhum_dos_dois_avisos(cenario):
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("lancamento_novo", cenario["empresa"])))

    assert "Meses encerrados não recebem lançamento" not in texto
    assert "Também não recebe lançamento um mês anterior" not in texto


def test_formulario_com_so_janeiro_encerrado_nao_lista_mes_aberto_bloqueado(cenario):
    ano = timezone.localdate().year
    encerrar_mes_caixa(empresa=cenario["empresa"], ano=ano, mes=1, usuario=cenario["autor"])
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    texto = _texto(cliente.get(_url("lancamento_novo", cenario["empresa"])))

    assert "Hoje nenhum mês aberto está nessa situação." in texto
    assert "Meses abertos que recusam por isso" not in texto


def test_lista_avisa_e_nao_oferece_estornar_em_mes_aberto_anterior_a_um_encerrado(cenario):
    em_janeiro = _lancar(cenario, date(2026, 1, 10), historico="Lançamento de janeiro")
    em_marco = _lancar(cenario, date(2026, 3, 10), historico="Lançamento de março")
    _encerrar(cenario, 2)
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    resposta = cliente.get(
        _url("lancamentos", cenario["empresa"], inicio="2026-01-01", fim="2026-03-31")
    )

    texto = _texto(resposta)
    assert resposta.status_code == 200
    assert "Meses abertos que também não recebem lançamento nem estorno:</strong> 01/2026." in texto
    assert "o carnê-leão se encadeia de janeiro a dezembro" in texto
    assert "Mês posterior encerrado</span>" in texto
    assert f"/lancamentos/{em_janeiro.id}/estornar/" not in texto
    assert f"/lancamentos/{em_marco.id}/estornar/" in texto  # depois do encerrado: oferece


def test_lista_do_periodo_dentro_do_mes_bloqueado_avisa_mesmo_com_o_encerrado_fora_dele(cenario):
    em_janeiro = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, 3)
    cliente = _cliente(Papel.ANALISTA, cenario["escritorio_a"])

    texto = _texto(
        cliente.get(_url("lancamentos", cenario["empresa"], inicio="2026-01-01", fim="2026-01-31"))
    )

    assert "Meses abertos que também não recebem lançamento nem estorno:</strong> 01/2026." in texto
    assert f"/lancamentos/{em_janeiro.id}/estornar/" not in texto


def test_lista_volta_ao_normal_depois_da_cascata(cenario):
    em_janeiro = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, 1, 2)
    cliente = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    _post_reabrir(cliente, cenario)

    texto = _texto(
        cliente.get(_url("lancamentos", cenario["empresa"], inicio="2026-01-01", fim="2026-02-28"))
    )

    assert "Meses abertos que também não recebem" not in texto
    assert f"/lancamentos/{em_janeiro.id}/estornar/" in texto


# ---------------------------------------------------------------------------
# Nenhum identificador interno visível, em nenhum dos estados novos
# ---------------------------------------------------------------------------


def test_nenhum_estado_novo_mostra_identificador_interno(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario, 1, 2, 3)
    gestor = _cliente(Papel.GESTOR, cenario["escritorio_a"])
    analista = _cliente(Papel.ANALISTA, cenario["escritorio_a"])
    paginas = [
        gestor.get(_url("fechamento_mes", cenario["empresa"], ano=2026)),
        gestor.get(_url("mes_reabrir", cenario["empresa"], ano=2026, mes=1)),
        _post_reabrir(gestor, cenario, cascata=False),  # 409: a tela volta com a explicação
        _post_reabrir(gestor, cenario, motivo=""),  # 400: motivo vazio, com a lista
        analista.get(_url("lancamento_novo", cenario["empresa"])),
        analista.post(
            _url("lancamento_novo", cenario["empresa"]),
            _dados_de_lancamento(cenario, "2026-01-20"),
        ),
        analista.get(
            _url("lancamentos", cenario["empresa"], inicio="2026-01-01", fim="2026-03-31")
        ),
        analista.get(_url_estornar(cenario["empresa"], original)),
        analista.post(_url_estornar(cenario["empresa"], original)),
        analista.post(_url("mes_reabrir", cenario["empresa"]), {"ano": "2026", "mes": "1"}),
    ]

    for pagina in paginas:
        texto = re.sub(r"<!--.*?-->", "", pagina.content.decode(), flags=re.S)
        achados = _IDENTIFICADOR_INTERNO.findall(texto)
        assert not achados, f"identificador interno visível: {achados}"
    # Mensagens (já renderizadas no HTML acima, mas conferidas na fonte também).
    for pagina in paginas:
        assert not _IDENTIFICADOR_INTERNO.findall(_mensagens(pagina))
