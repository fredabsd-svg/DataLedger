"""DL-053 (RC-145/RC-146) — fechamento de mês do livro-caixa, servidor + API.

Cobre os critérios 1 a 6 e 8 do plano (o 7 é a tela, do `especialista-frontend`):

1. mês encerrado recusa lançamento (serviço, API e tela) e deixa o banco
   inalterado; mês aberto e mês sem registro aceitam;
2. estorno de lançamento de mês encerrado recusado; reabrir e estornar passa;
3. ADMINISTRADOR e GESTOR encerram/reabrem, com trilha; os outros quatro
   papéis recebem 403 COM O BANCO INALTERADO, testado pela requisição;
4. reabrir sem motivo, encerrar mês encerrado e reabrir mês aberto: recusados
   sem efeito;
5. isolamento entre escritórios (404) e entre empresas;
6. concorrência com duas conexões, inclusive partindo de mês SEM registro.

Dados 100% sintéticos. As datas ficam em 2025 e 2026, sempre no passado.
Os testes de concorrência seguem a DL-050: todo `join` tem `timeout` e há
asserção de que as threads terminaram — resultado incompleto reprova, em vez
de travar em silêncio.
"""

import contextlib
import itertools
import json
import threading
import time
from datetime import date
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.views import PodeFecharCompetencia
from apps.core.papeis_de_fechamento import PAPEIS_QUE_FECHAM_PERIODO
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa import services
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    EstadoMesCaixa,
    FechamentoMesCaixa,
    LancamentoCaixa,
    NaturezaCaixa,
)
from apps.livro_caixa.permissoes import PAPEIS_QUE_FECHAM_MES_CAIXA, papel_pode_fechar_mes_caixa
from apps.livro_caixa.services import (
    FechamentoMesCaixaInvalido,
    FechamentoMesCaixaRecusado,
    FechamentoMesCaixaTravado,
    MesCaixaEncerrado,
    MesCaixaOcupado,
    criar_lancamento_caixa,
    encerrar_mes_caixa,
    estado_dos_meses_caixa,
    estornar_lancamento_caixa,
    reabrir_mes_caixa,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

_SENHA = "senha-forte-123"
_SEQ = itertools.count(1)


def _usuario(papel, escritorio, prefixo=None):
    nome = f"{prefixo or papel}-dl053-{next(_SEQ)}"
    usuario = get_user_model().objects.create_user(
        username=nome, email=f"{nome}@escritorio.com.br", password=_SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _cliente_logado(usuario):
    cliente = Client(raise_request_exception=False)
    assert cliente.login(username=usuario.username, password=_SENHA)
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
    escritorio_a = Escritorio.objects.create(nome="Escritório DL-053 A", cnpj="31000000000153")
    escritorio_b = Escritorio.objects.create(nome="Escritório DL-053 B", cnpj="32000000000153")
    empresa, conta = _montar_empresa(escritorio_a, "Fulano DL-053", "12345678909")
    # Segunda empresa do MESMO escritório: prova que o fechamento de uma não
    # vaza para a outra.
    empresa_irma, conta_irma = _montar_empresa(escritorio_a, "Beltrano DL-053", "11144477735")
    empresa_b, conta_b = _montar_empresa(escritorio_b, "Ciclano DL-053", "22255588846")
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Empresa Contabilidade DL-053 Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa": empresa,
        "conta": conta,
        "empresa_irma": empresa_irma,
        "conta_irma": conta_irma,
        "empresa_b": empresa_b,
        "empresa_contabilidade": empresa_contabilidade,
        "gestor": _usuario(Papel.GESTOR, escritorio_a),
    }


def _lancar(cenario, data, *, empresa=None, conta=None, chave=None, valor="100.00"):
    return criar_lancamento_caixa(
        empresa=empresa or cenario["empresa"],
        conta=conta or cenario["conta"],
        data=data,
        valor=valor,
        historico="Honorários DL-053",
        recebido_de="PJ",
        criado_por=cenario["gestor"],
        chave_idempotencia=chave,
    )


def _encerrar(cenario, ano=2026, mes=1, empresa=None):
    return encerrar_mes_caixa(
        empresa=empresa or cenario["empresa"], ano=ano, mes=mes, usuario=cenario["gestor"]
    )


def _reabrir(cenario, ano=2026, mes=1, motivo="Corrigir lançamento de janeiro", empresa=None):
    return reabrir_mes_caixa(
        empresa=empresa or cenario["empresa"],
        ano=ano,
        mes=mes,
        usuario=cenario["gestor"],
        motivo=motivo,
    )


def _fotografia(empresa):
    """O que precisa ficar IGUAL quando uma operação é recusada."""
    return {
        "lancamentos": list(
            LancamentoCaixa.objects.filter(empresa=empresa).values_list("id", flat=True)
        ),
        "fechamentos": list(
            FechamentoMesCaixa.objects.filter(empresa=empresa).values_list(
                "id", "estado", "fechado_em", "fechado_por_id", "reaberto_em", "motivo_reabertura"
            )
        ),
        # Só a trilha do livro-caixa: o login do usuário do teste também grava
        # um registro, e não é o que está sob prova.
        "trilha": list(
            RegistroAuditoria.objects.filter(
                Q(acao__startswith="lancamento_caixa.")
                | Q(acao__startswith="fechamento_mes_caixa.")
            ).values_list("id", flat=True)
        ),
    }


def _url(nome, empresa_id, *args):
    return reverse(f"livro_caixa:{nome}", args=[empresa_id, *args])


def _corpo_lancamento(cenario, data):
    return json.dumps(
        {
            "conta": cenario["conta"].id,
            "data": data,
            "valor": "50.00",
            "historico": "Lançamento pela API",
            "recebido_de": "PJ",
        }
    )


# ---------------------------------------------------------------------------
# Critério 1 — lançamento em mês encerrado / aberto / sem registro (serviço)
# ---------------------------------------------------------------------------


def test_mes_sem_registro_aceita_lancamento(cenario):
    assert not FechamentoMesCaixa.objects.exists()
    lancamento = _lancar(cenario, date(2026, 1, 15))
    assert LancamentoCaixa.objects.filter(pk=lancamento.pk).exists()


def test_mes_encerrado_recusa_lancamento_e_deixa_o_banco_inalterado(cenario):
    _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(MesCaixaEncerrado) as erro:
        _lancar(cenario, date(2026, 1, 20))

    # A mensagem nomeia o mês e orienta a reabrir.
    assert "01/2026" in str(erro.value)
    assert "Reabra" in str(erro.value)
    assert _fotografia(cenario["empresa"]) == antes


def test_recusa_de_mes_encerrado_nao_e_erro_de_validacao_de_lancamento(cenario):
    """Um `except LancamentoCaixaInvalido` esquecido numa porta de escrita não
    pode engolir a recusa como se fosse erro de digitação."""
    assert not issubclass(MesCaixaEncerrado, services.LancamentoCaixaInvalido)
    assert issubclass(MesCaixaOcupado, MesCaixaEncerrado)


def test_limites_do_mes_ultimo_e_primeiro_dia_e_virada_de_ano(cenario):
    _encerrar(cenario, ano=2025, mes=12)
    _encerrar(cenario, ano=2026, mes=1)

    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2025, 12, 31))
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 1))
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 31))

    # Os vizinhos continuam abertos: 30/11/2025 e 01/02/2026.
    assert _lancar(cenario, date(2025, 11, 30)).pk
    assert _lancar(cenario, date(2026, 2, 1)).pk


def test_encerrar_um_mes_nao_afeta_outro_mes_nem_outra_empresa(cenario):
    _encerrar(cenario, ano=2026, mes=1)

    assert _lancar(cenario, date(2026, 2, 10)).pk
    assert _lancar(
        cenario, date(2026, 1, 10), empresa=cenario["empresa_irma"], conta=cenario["conta_irma"]
    ).pk
    # mesmo mês, mesmo ano anterior
    assert _lancar(cenario, date(2025, 1, 10)).pk


def test_reabrir_e_lancar_aceita(cenario):
    _encerrar(cenario)
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 20))

    _reabrir(cenario)

    assert _lancar(cenario, date(2026, 1, 20)).pk


def test_repeticao_idempotente_de_lancamento_ja_gravado_nao_grava_nada_em_mes_encerrado(cenario):
    original = _lancar(cenario, date(2026, 1, 10), chave="chave-dl053-repeticao")
    _encerrar(cenario)
    antes = LancamentoCaixa.objects.count()

    repetido = _lancar(cenario, date(2026, 1, 10), chave="chave-dl053-repeticao")

    assert repetido.pk == original.pk
    assert repetido.criado_agora is False
    assert LancamentoCaixa.objects.count() == antes


def test_chave_nova_em_mes_encerrado_e_recusada_mesmo_com_idempotency_key(cenario):
    _encerrar(cenario)
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 10), chave="chave-dl053-nova")
    assert not LancamentoCaixa.objects.exists()


# ---------------------------------------------------------------------------
# Critério 2 — estorno
# ---------------------------------------------------------------------------


def test_estorno_de_lancamento_de_mes_encerrado_e_recusado_e_passa_depois_de_reabrir(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(MesCaixaEncerrado) as erro:
        estornar_lancamento_caixa(original, criado_por=cenario["gestor"])

    assert "01/2026" in str(erro.value)
    assert "RC-130" in str(erro.value)
    assert _fotografia(cenario["empresa"]) == antes

    _reabrir(cenario)
    estorno = estornar_lancamento_caixa(original, criado_por=cenario["gestor"])
    assert estorno.estorno_de_id == original.pk
    assert estorno.data == original.data


# ---------------------------------------------------------------------------
# Critério 1 e 2 — pela API
# ---------------------------------------------------------------------------


def test_api_lancamento_em_mes_encerrado_da_409_e_nao_grava(client, cenario):
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))

    resposta = cliente.post(
        _url("lancamentos", cenario["empresa"].id),
        data=_corpo_lancamento(cenario, "2026-01-20"),
        content_type="application/json",
    )

    assert resposta.status_code == 409
    assert "encerrado" in resposta.json()["detail"]
    assert _fotografia(cenario["empresa"]) == antes


def test_api_lancamento_em_mes_aberto_e_sem_registro_da_201(client, cenario):
    _encerrar(cenario, mes=1)
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))

    resposta = cliente.post(
        _url("lancamentos", cenario["empresa"].id),
        data=_corpo_lancamento(cenario, "2026-02-20"),
        content_type="application/json",
    )

    assert resposta.status_code == 201


def test_api_estorno_em_mes_encerrado_da_409_e_depois_de_reabrir_da_201(client, cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(_usuario(Papel.FINANCEIRO, cenario["escritorio_a"]))
    url = _url("estornar", cenario["empresa"].id, original.id)

    recusado = cliente.post(url)
    assert recusado.status_code == 409
    assert _fotografia(cenario["empresa"]) == antes

    _reabrir(cenario)
    aceito = cliente.post(url)
    assert aceito.status_code == 201
    assert LancamentoCaixa.objects.filter(estorno_de=original).count() == 1


# ---------------------------------------------------------------------------
# Critério 1 e 2 — pela tela (POST)
# ---------------------------------------------------------------------------


def _dados_do_formulario(cenario, data):
    return {
        "data": data,
        "conta": str(cenario["conta"].id),
        "valor": "75,00",
        "historico": "Lançamento pela tela",
        "documento_origem": "",
        "recebido_de": "PJ",
        "cpf_titular_pagamento": "",
        "cpf_beneficiario_servico": "",
        "cnpj_pagador": "",
        "chave_idempotencia": "chave-tela-dl053",
    }


def test_tela_lancamento_em_mes_encerrado_da_409_com_mensagem_e_nao_grava(cenario):
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))

    resposta = cliente.post(
        reverse("livro_caixa_web:lancamento_novo", args=[cenario["empresa"].id]),
        _dados_do_formulario(cenario, "2026-01-20"),
    )

    assert resposta.status_code == 409
    conteudo = resposta.content.decode()
    assert "encerrado" in conteudo
    assert "01/2026" in conteudo
    assert _fotografia(cenario["empresa"]) == antes


def test_tela_lancamento_em_mes_aberto_grava(cenario):
    _encerrar(cenario, mes=1)
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))

    resposta = cliente.post(
        reverse("livro_caixa_web:lancamento_novo", args=[cenario["empresa"].id]),
        _dados_do_formulario(cenario, "2026-02-20"),
    )

    assert resposta.status_code == 302
    assert LancamentoCaixa.objects.filter(empresa=cenario["empresa"]).count() == 1


def test_tela_estorno_em_mes_encerrado_da_409_e_nao_grava(cenario):
    original = _lancar(cenario, date(2026, 1, 10))
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))

    resposta = cliente.post(
        reverse("livro_caixa_web:lancamento_estornar", args=[cenario["empresa"].id, original.id])
    )

    assert resposta.status_code == 409
    assert "encerrado" in resposta.content.decode()
    assert _fotografia(cenario["empresa"]) == antes


# ---------------------------------------------------------------------------
# Critério 3 e 4 — transições no serviço, com trilha
# ---------------------------------------------------------------------------


def test_encerrar_grava_estado_autoria_e_trilha(cenario):
    fechamento = _encerrar(cenario, ano=2026, mes=3)

    fechamento.refresh_from_db()
    assert fechamento.estado == EstadoMesCaixa.ENCERRADO
    assert fechamento.fechado_por == cenario["gestor"]
    assert fechamento.fechado_em is not None
    assert fechamento.reaberto_em is None

    registro = RegistroAuditoria.objects.get(acao="fechamento_mes_caixa.encerrado")
    assert registro.usuario == cenario["gestor"]
    assert registro.escritorio == cenario["escritorio_a"]
    assert registro.objeto_tipo == "FechamentoMesCaixa"
    assert registro.objeto_id == str(fechamento.pk)
    assert registro.detalhes == {
        "ano": 2026,
        "mes": 3,
        "empresa_id": cenario["empresa"].id,
    }


def test_reabrir_grava_motivo_autoria_e_trilha_com_o_fechamento_desfeito(cenario):
    fechamento = _encerrar(cenario, mes=3)
    fechado_em = FechamentoMesCaixa.objects.get(pk=fechamento.pk).fechado_em
    outro = _usuario(Papel.ADMINISTRADOR, cenario["escritorio_a"])

    reabrir_mes_caixa(
        empresa=cenario["empresa"],
        ano=2026,
        mes=3,
        usuario=outro,
        motivo="  Receita lançada no mês errado  ",
    )

    fechamento.refresh_from_db()
    assert fechamento.estado == EstadoMesCaixa.ABERTO
    assert fechamento.motivo_reabertura == "Receita lançada no mês errado"
    assert fechamento.reaberto_por == outro
    assert fechamento.reaberto_em is not None

    registro = RegistroAuditoria.objects.get(acao="fechamento_mes_caixa.reaberto")
    assert registro.usuario == outro
    assert registro.detalhes["motivo"] == "Receita lançada no mês errado"
    assert registro.detalhes["fechado_por_anterior"] == cenario["gestor"].id
    assert registro.detalhes["fechado_em_anterior"] == fechado_em.isoformat()
    assert (registro.detalhes["ano"], registro.detalhes["mes"]) == (2026, 3)


def test_reencerrar_depois_de_reabrir_reaproveita_a_linha_e_guarda_a_reabertura(cenario):
    _encerrar(cenario)
    _reabrir(cenario, motivo="Primeira correção")
    novo_autor = _usuario(Papel.ADMINISTRADOR, cenario["escritorio_a"])

    encerrar_mes_caixa(empresa=cenario["empresa"], ano=2026, mes=1, usuario=novo_autor)

    assert FechamentoMesCaixa.objects.filter(empresa=cenario["empresa"]).count() == 1
    linha = FechamentoMesCaixa.objects.get(empresa=cenario["empresa"])
    assert linha.estado == EstadoMesCaixa.ENCERRADO
    assert linha.fechado_por == novo_autor
    assert linha.motivo_reabertura == "Primeira correção"
    assert RegistroAuditoria.objects.filter(acao="fechamento_mes_caixa.encerrado").count() == 2


def test_encerrar_mes_ja_encerrado_e_recusado_sem_efeito(cenario):
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    outro = _usuario(Papel.ADMINISTRADOR, cenario["escritorio_a"])

    with pytest.raises(FechamentoMesCaixaRecusado):
        encerrar_mes_caixa(empresa=cenario["empresa"], ano=2026, mes=1, usuario=outro)

    # O autor e o horário do PRIMEIRO fechamento permanecem; nada na trilha.
    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize("cenario_do_mes", ["nunca_fechado", "reaberto"])
def test_reabrir_mes_aberto_e_recusado_sem_efeito(cenario, cenario_do_mes):
    if cenario_do_mes == "reaberto":
        _encerrar(cenario)
        _reabrir(cenario)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(FechamentoMesCaixaRecusado):
        _reabrir(cenario, motivo="Tentativa em mês aberto")

    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize("motivo", [None, "", "   ", "\t\n"])
def test_reabrir_sem_motivo_e_recusado_e_o_mes_continua_encerrado(cenario, motivo):
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])

    with pytest.raises(FechamentoMesCaixaInvalido):
        reabrir_mes_caixa(
            empresa=cenario["empresa"], ano=2026, mes=1, usuario=cenario["gestor"], motivo=motivo
        )

    assert _fotografia(cenario["empresa"]) == antes
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 20))


def test_motivo_de_reabertura_com_caractere_nulo_ou_grande_demais_e_recusado(cenario):
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    for motivo in ("motivo\x00nulo", "x" * (services.TAMANHO_MAXIMO_MOTIVO_REABERTURA + 1)):
        with pytest.raises(FechamentoMesCaixaInvalido):
            _reabrir(cenario, motivo=motivo)
    assert _fotografia(cenario["empresa"]) == antes
    # No limite exato é aceito.
    _reabrir(cenario, motivo="x" * services.TAMANHO_MAXIMO_MOTIVO_REABERTURA)


@pytest.mark.parametrize(
    "ano,mes", [(2026, 0), (2026, 13), (1969, 1), (3000, 1), (True, 1), ("2026", 1), (2026, None)]
)
def test_ano_e_mes_fora_da_faixa_sao_recusados_sem_criar_linha(cenario, ano, mes):
    with pytest.raises(FechamentoMesCaixaInvalido):
        encerrar_mes_caixa(empresa=cenario["empresa"], ano=ano, mes=mes, usuario=cenario["gestor"])
    assert not FechamentoMesCaixa.objects.exists()


def test_empresa_em_modo_contabilidade_nao_tem_fechamento_de_caixa(cenario):
    with pytest.raises(FechamentoMesCaixaInvalido):
        encerrar_mes_caixa(
            empresa=cenario["empresa_contabilidade"],
            ano=2026,
            mes=1,
            usuario=cenario["gestor"],
        )
    assert not FechamentoMesCaixa.objects.exists()


def test_encerrar_sem_usuario_e_recusado(cenario):
    with pytest.raises(FechamentoMesCaixaInvalido):
        encerrar_mes_caixa(empresa=cenario["empresa"], ano=2026, mes=1, usuario=None)
    assert not FechamentoMesCaixa.objects.exists()


def test_encerrar_um_mes_sem_nenhum_lancamento_e_permitido(cenario):
    """Mesmo caso RC-53 da contabilidade: fechar mês ainda sem movimento."""
    assert _encerrar(cenario, ano=2025, mes=6).estado == EstadoMesCaixa.ENCERRADO


# ---------------------------------------------------------------------------
# Atomicidade: a trilha falha, nada fica gravado
# ---------------------------------------------------------------------------


def test_atomicidade_encerrar_com_trilha_falhando_nao_deixa_fechamento(cenario):
    with mock.patch.object(services, "registrar", side_effect=RuntimeError("trilha fora do ar")):
        with pytest.raises(RuntimeError):
            _encerrar(cenario)

    assert not FechamentoMesCaixa.objects.exists()
    # E o mês continua aceitando lançamento.
    assert _lancar(cenario, date(2026, 1, 20)).pk


def test_atomicidade_reabrir_com_trilha_falhando_mantem_o_mes_encerrado(cenario):
    _encerrar(cenario)
    with mock.patch.object(services, "registrar", side_effect=RuntimeError("trilha fora do ar")):
        with pytest.raises(RuntimeError):
            _reabrir(cenario)

    linha = FechamentoMesCaixa.objects.get(empresa=cenario["empresa"])
    assert linha.estado == EstadoMesCaixa.ENCERRADO
    assert linha.reaberto_em is None
    assert linha.motivo_reabertura == ""
    with pytest.raises(MesCaixaEncerrado):
        _lancar(cenario, date(2026, 1, 20))


# ---------------------------------------------------------------------------
# Restrições de banco do modelo
# ---------------------------------------------------------------------------


def _linha_crua(cenario, **extra):
    base = {
        "empresa": cenario["empresa"],
        "ano": 2026,
        "mes": 5,
        "estado": EstadoMesCaixa.ENCERRADO,
        "fechado_em": "2026-05-31T12:00:00+00:00",
        "fechado_por": cenario["gestor"],
    }
    base.update(extra)
    return FechamentoMesCaixa.objects.create(**base)


@pytest.mark.parametrize(
    "extra",
    [
        {"mes": 13},
        {"mes": 0},
        {"ano": 1969},
        {"ano": 3000},
        {"estado": "qualquer"},
        # aberto sem nenhuma reabertura registrada
        {"estado": EstadoMesCaixa.ABERTO},
        # reabertura sem motivo
        {"reaberto_em": "2026-06-01T12:00:00+00:00", "reaberto_por_id": 1},
    ],
)
def test_banco_recusa_linha_invalida(cenario, extra):
    if "reaberto_por_id" in extra:
        extra = {**extra, "reaberto_por_id": cenario["gestor"].id}
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _linha_crua(cenario, **extra)


def test_banco_recusa_segundo_fechamento_do_mesmo_mes(cenario):
    _linha_crua(cenario)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _linha_crua(cenario)


def test_modelo_recusa_empresa_em_contabilidade_no_full_clean(cenario):
    from django.core.exceptions import ValidationError

    linha = FechamentoMesCaixa(
        empresa=cenario["empresa_contabilidade"],
        ano=2026,
        mes=1,
        estado=EstadoMesCaixa.ENCERRADO,
        fechado_em="2026-01-31T12:00:00+00:00",
        fechado_por=cenario["gestor"],
    )
    with pytest.raises(ValidationError):
        linha.full_clean()


def test_usuario_que_fechou_nao_pode_ser_apagado(cenario):
    from django.db.models import ProtectedError

    autor = _usuario(Papel.GESTOR, cenario["escritorio_a"], "autor-fecha")
    encerrar_mes_caixa(empresa=cenario["empresa"], ano=2026, mes=1, usuario=autor)
    with pytest.raises(ProtectedError):
        autor.delete()


# ---------------------------------------------------------------------------
# Critério 3 — matriz de papéis, pela REQUISIÇÃO, com banco inalterado
# ---------------------------------------------------------------------------

_PODEM_FECHAR = {Papel.ADMINISTRADOR, Papel.GESTOR}
_PODEM_LER = {Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL}


def test_a_matriz_cobre_todos_os_papeis_existentes():
    assert set(Papel.values) == {
        "administrador",
        "gestor",
        "analista",
        "financeiro",
        "paralegal",
        "cliente",
    }


def test_a_lista_de_quem_fecha_e_a_mesma_da_contabilidade_e_nao_uma_copia():
    """RC-146 = RC-102: uma lista só. Mudar `PAPEIS_QUE_FECHAM_PERIODO` muda as
    duas permissões; nenhuma delas tem lista literal própria."""
    assert PAPEIS_QUE_FECHAM_MES_CAIXA is PAPEIS_QUE_FECHAM_PERIODO
    assert set(PAPEIS_QUE_FECHAM_PERIODO) == _PODEM_FECHAR
    for papel in Papel.values:
        esperado = papel in _PODEM_FECHAR
        assert papel_pode_fechar_mes_caixa(papel) is esperado
        requisicao = mock.Mock(papel=papel)
        assert PodeFecharCompetencia().has_permission(requisicao, None) is esperado
    assert papel_pode_fechar_mes_caixa(None) is False


@pytest.mark.parametrize("papel", Papel.values)
def test_api_encerrar_por_papel_e_banco_inalterado_quando_negado(cenario, papel):
    usuario = _usuario(papel, cenario["escritorio_a"])
    cliente = _cliente_logado(usuario)
    antes = _fotografia(cenario["empresa"])

    resposta = cliente.post(_url("encerrar-mes", cenario["empresa"].id, 2026, 1))

    if papel in _PODEM_FECHAR:
        assert resposta.status_code == 200, resposta.content
        assert resposta.json()["estado"] == "encerrado"
        assert resposta.json()["fechado_por"] == usuario.id
        assert FechamentoMesCaixa.objects.filter(empresa=cenario["empresa"]).count() == 1
        assert RegistroAuditoria.objects.filter(
            acao="fechamento_mes_caixa.encerrado", usuario=usuario
        ).exists()
    else:
        assert resposta.status_code == 403
        assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize("papel", Papel.values)
def test_api_reabrir_por_papel_e_banco_inalterado_quando_negado(cenario, papel):
    _encerrar(cenario)
    usuario = _usuario(papel, cenario["escritorio_a"])
    cliente = _cliente_logado(usuario)
    antes = _fotografia(cenario["empresa"])

    resposta = cliente.post(
        _url("reabrir-mes", cenario["empresa"].id, 2026, 1),
        data=json.dumps({"motivo": "Correção autorizada"}),
        content_type="application/json",
    )

    if papel in _PODEM_FECHAR:
        assert resposta.status_code == 200, resposta.content
        corpo = resposta.json()
        assert corpo["estado"] == "aberto"
        assert corpo["reaberto_por"] == usuario.id
        assert corpo["motivo_reabertura"] == "Correção autorizada"
        assert RegistroAuditoria.objects.filter(
            acao="fechamento_mes_caixa.reaberto", usuario=usuario
        ).exists()
    else:
        assert resposta.status_code == 403
        assert _fotografia(cenario["empresa"]) == antes
        with pytest.raises(MesCaixaEncerrado):
            _lancar(cenario, date(2026, 1, 20))


@pytest.mark.parametrize("papel", Papel.values)
def test_api_consultar_meses_por_papel(cenario, papel):
    cliente = _cliente_logado(_usuario(papel, cenario["escritorio_a"]))
    resposta = cliente.get(_url("meses", cenario["empresa"].id) + "?ano=2026")
    assert resposta.status_code == (200 if papel in _PODEM_LER else 403)


def test_api_sem_login_nao_encerra_nem_reabre_nem_consulta(cenario):
    anonimo = Client(raise_request_exception=False)
    for nome, args in (("encerrar-mes", (2026, 1)), ("reabrir-mes", (2026, 1))):
        resposta = anonimo.post(_url(nome, cenario["empresa"].id, *args))
        assert resposta.status_code in (401, 403)
    assert anonimo.get(_url("meses", cenario["empresa"].id)).status_code in (401, 403)
    assert not FechamentoMesCaixa.objects.exists()


# ---------------------------------------------------------------------------
# Critério 4 e contrato da API
# ---------------------------------------------------------------------------


def test_api_reabrir_sem_motivo_da_400_e_o_mes_continua_encerrado(cenario):
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    cliente = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    url = _url("reabrir-mes", cenario["empresa"].id, 2026, 1)

    for corpo in ({}, {"motivo": ""}, {"motivo": "   "}, {"motivo": None}):
        resposta = cliente.post(url, data=json.dumps(corpo), content_type="application/json")
        assert resposta.status_code == 400, corpo
    nao_texto = cliente.post(
        url, data=json.dumps({"motivo": ["a"]}), content_type="application/json"
    )
    assert nao_texto.status_code == 400
    assert _fotografia(cenario["empresa"]) == antes


def test_api_recusa_campo_nao_contratado(cenario):
    _encerrar(cenario)
    cliente = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    antes = _fotografia(cenario["empresa"])

    reabrir = cliente.post(
        _url("reabrir-mes", cenario["empresa"].id, 2026, 1),
        data=json.dumps({"motivo": "ok", "estado": "aberto"}),
        content_type="application/json",
    )
    encerrar = cliente.post(
        _url("encerrar-mes", cenario["empresa"].id, 2026, 2),
        data=json.dumps({"estado": "encerrado"}),
        content_type="application/json",
    )

    assert reabrir.status_code == 400
    assert encerrar.status_code == 400
    assert _fotografia(cenario["empresa"]) == antes


def test_api_encerrar_duas_vezes_da_409_e_reabrir_mes_aberto_da_409(cenario):
    cliente = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    encerrar = _url("encerrar-mes", cenario["empresa"].id, 2026, 4)
    reabrir = _url("reabrir-mes", cenario["empresa"].id, 2026, 4)
    corpo = json.dumps({"motivo": "Correção"})

    assert cliente.post(reabrir, data=corpo, content_type="application/json").status_code == 409
    assert cliente.post(encerrar).status_code == 200
    antes = _fotografia(cenario["empresa"])
    assert cliente.post(encerrar).status_code == 409
    assert _fotografia(cenario["empresa"]) == antes


@pytest.mark.parametrize("ano,mes", [(2026, 13), (2026, 0), (1969, 1), (3000, 1)])
def test_api_ano_ou_mes_fora_da_faixa_da_400(cenario, ano, mes):
    cliente = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    resposta = cliente.post(_url("encerrar-mes", cenario["empresa"].id, ano, mes))
    assert resposta.status_code == 400
    assert not FechamentoMesCaixa.objects.exists()


def test_api_consulta_devolve_os_12_meses_com_o_estado_de_cada_um(cenario):
    _encerrar(cenario, mes=1)
    _encerrar(cenario, mes=2)
    _reabrir(cenario, mes=2, motivo="Conferir fevereiro")
    cliente = _cliente_logado(_usuario(Papel.PARALEGAL, cenario["escritorio_a"]))

    resposta = cliente.get(_url("meses", cenario["empresa"].id) + "?ano=2026")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["empresa"] == cenario["empresa"].id
    assert corpo["ano"] == 2026
    assert [m["mes"] for m in corpo["meses"]] == list(range(1, 13))
    estados = {m["mes"]: m["estado"] for m in corpo["meses"]}
    assert estados[1] == "encerrado"
    assert estados[2] == "aberto"
    assert all(estados[m] == "aberto" for m in range(3, 13))
    janeiro, fevereiro, marco = corpo["meses"][:3]
    assert janeiro["fechado_por"] == cenario["gestor"].id
    assert janeiro["fechado_em"] is not None
    assert fevereiro["motivo_reabertura"] == "Conferir fevereiro"
    assert fevereiro["reaberto_por"] == cenario["gestor"].id
    assert marco["fechado_em"] is None and marco["fechado_por"] is None
    assert marco["motivo_reabertura"] == ""


def test_api_consulta_com_ano_invalido_da_400_e_sem_ano_usa_o_corrente(cenario):
    cliente = _cliente_logado(_usuario(Papel.ANALISTA, cenario["escritorio_a"]))
    assert cliente.get(_url("meses", cenario["empresa"].id) + "?ano=abc").status_code == 400
    assert cliente.get(_url("meses", cenario["empresa"].id) + "?ano=1800").status_code == 400
    sem_ano = cliente.get(_url("meses", cenario["empresa"].id))
    assert sem_ano.status_code == 200
    assert len(sem_ano.json()["meses"]) == 12


def test_servico_estado_dos_meses_nao_vaza_entre_empresas(cenario):
    _encerrar(cenario)
    irma = estado_dos_meses_caixa(empresa=cenario["empresa_irma"], ano=2026)
    assert {m["estado"] for m in irma} == {"aberto"}
    propria = estado_dos_meses_caixa(empresa=cenario["empresa"], ano=2026)
    assert propria[0]["estado"] == "encerrado"


# ---------------------------------------------------------------------------
# Critério 5 — isolamento
# ---------------------------------------------------------------------------


def test_usuario_de_outro_escritorio_nao_encerra_nao_reabre_e_nao_ve_o_estado(cenario):
    _encerrar(cenario)
    antes = _fotografia(cenario["empresa"])
    intruso = _cliente_logado(_usuario(Papel.ADMINISTRADOR, cenario["escritorio_b"]))
    empresa_id = cenario["empresa"].id

    assert intruso.post(_url("encerrar-mes", empresa_id, 2026, 2)).status_code == 404
    reabrir = intruso.post(
        _url("reabrir-mes", empresa_id, 2026, 1),
        data=json.dumps({"motivo": "Tentativa de outro escritório"}),
        content_type="application/json",
    )
    assert reabrir.status_code == 404
    consulta = intruso.get(_url("meses", empresa_id) + "?ano=2026")
    assert consulta.status_code == 404
    assert "encerrado" not in consulta.content.decode()
    assert _fotografia(cenario["empresa"]) == antes


def test_fechar_uma_empresa_nao_altera_a_irma_do_mesmo_escritorio(cenario):
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    assert gestor.post(_url("encerrar-mes", cenario["empresa"].id, 2026, 1)).status_code == 200

    consulta = gestor.get(_url("meses", cenario["empresa_irma"].id) + "?ano=2026").json()
    assert {m["estado"] for m in consulta["meses"]} == {"aberto"}
    assert not FechamentoMesCaixa.objects.filter(empresa=cenario["empresa_irma"]).exists()


def test_api_de_empresa_em_modo_contabilidade_e_recusada_nas_tres_rotas(cenario):
    gestor = _cliente_logado(_usuario(Papel.GESTOR, cenario["escritorio_a"]))
    empresa_id = cenario["empresa_contabilidade"].id

    assert gestor.get(_url("meses", empresa_id)).status_code == 400
    assert gestor.post(_url("encerrar-mes", empresa_id, 2026, 1)).status_code == 400
    assert (
        gestor.post(
            _url("reabrir-mes", empresa_id, 2026, 1),
            data=json.dumps({"motivo": "x"}),
            content_type="application/json",
        ).status_code
        == 400
    )
    assert not FechamentoMesCaixa.objects.exists()


# ---------------------------------------------------------------------------
# A chave do lock (unidade, sem banco)
# ---------------------------------------------------------------------------


def test_chave_do_lock_e_unica_por_empresa_e_mes_e_cabe_em_bigint():
    chaves = set()
    empresas = [1, 2, 65_535, 65_536, 10**9, services._MAXIMO_EMPRESA_ID_NO_LOCK]
    anos_meses = [(1970, 1), (1970, 12), (2025, 12), (2026, 1), (2999, 11), (2999, 12)]
    for empresa_id in empresas:
        for ano, mes in anos_meses:
            chave = services._chave_do_lock_do_mes(empresa_id=empresa_id, ano=ano, mes=mes)
            assert 0 < chave < 2**63
            chaves.add(chave)
    assert len(chaves) == len(empresas) * len(anos_meses)


@pytest.mark.parametrize("empresa_id", [0, -1, 2**40])
def test_chave_do_lock_recusa_empresa_fora_da_faixa(empresa_id):
    with pytest.raises(ValueError):
        services._chave_do_lock_do_mes(empresa_id=empresa_id, ano=2026, mes=1)


def test_o_lock_do_mes_nao_protege_fora_de_transacao():
    """Sem transação o lock `_xact_` soltaria ao fim do comando: recusa em
    vez de fingir que trava."""
    # Estes testes rodam dentro de uma transação; a recusa é exercitada
    # simulando a ausência dela.
    with mock.patch.object(connection, "in_atomic_block", False):
        with pytest.raises(RuntimeError):
            services._adquirir_lock_do_mes(empresa_id=1, ano=2026, mes=1, exclusivo=False)


# ---------------------------------------------------------------------------
# Critério 6 — concorrência com duas conexões (transaction=True)
# ---------------------------------------------------------------------------
#
# DL-050: todo `join` tem timeout e há asserção de que as threads terminaram.
# `transaction=True` porque as threads usam conexões PRÓPRIAS — com o
# `atomic()` do pytest-django a linha da fixture não estaria comitada e elas
# não a enxergariam.

_TIMEOUT_DE_JOIN = 60
# O `lock_timeout` da conexão é de 1210 ms (`config/settings.py`). Toda pausa
# proposital dos testes abaixo fica bem abaixo disso, para a espera do lock
# ser a coisa medida e não o estouro dele.
_PAUSA_CURTA = 0.4


def _cenario_commitado():
    sufixo = next(_SEQ)
    escritorio = Escritorio.objects.create(
        nome=f"Escritório Corrida {sufixo}", cnpj=f"{40_000_000_000_000 + sufixo:014d}"
    )
    empresa, conta = _montar_empresa(escritorio, f"Corrida {sufixo}", "12345678909")
    return {
        "empresa": empresa,
        "conta": conta,
        "gestor": _usuario(Papel.GESTOR, escritorio, "corrida"),
    }


def _rodar_em_thread(alvo):
    """Roda `alvo()` numa thread com conexão própria; devolve `(thread,
    resultado)`, onde `resultado` ganha `valor` ou `erro`."""
    resultado = {}

    def _corpo():
        try:
            resultado["valor"] = alvo()
        except BaseException as exc:  # noqa: BLE001 - o teste inspeciona o tipo
            resultado["erro"] = exc
        finally:
            connection.close()

    thread = threading.Thread(target=_corpo)
    thread.start()
    return thread, resultado


def _esperar(*threads):
    for thread in threads:
        thread.join(timeout=_TIMEOUT_DE_JOIN)
    assert not [t for t in threads if t.is_alive()], "thread nao concluiu"


def _registrar_com_pausa(acao_alvo, dentro, liberar):
    """`registrar` que, para `acao_alvo`, sinaliza `dentro` e espera `liberar`
    — a pausa acontece DENTRO da transação do serviço, com o lock já tomado e
    a linha já escrita, mas ainda não comitada."""
    original = services.registrar

    def _registrar(*args, **kwargs):
        if kwargs.get("acao") == acao_alvo:
            dentro.set()
            assert liberar.wait(timeout=_TIMEOUT_DE_JOIN), "pausa nunca liberada"
        return original(*args, **kwargs)

    return _registrar


@contextlib.contextmanager
def _pausando(acao_alvo):
    """Instala `_registrar_com_pausa` e GARANTE, no `finally`, que a pausa é
    liberada — uma asserção que falhe no meio do teste não pode deixar a
    thread presa na espera (e o processo do pytest preso com ela)."""
    dentro, liberar = threading.Event(), threading.Event()
    try:
        with mock.patch.object(
            services, "registrar", _registrar_com_pausa(acao_alvo, dentro, liberar)
        ):
            yield dentro, liberar
    finally:
        liberar.set()


@pytest.mark.django_db(transaction=True)
def test_fechamento_em_andamento_num_mes_sem_registro_faz_o_lancamento_esperar_e_ser_recusado():
    """O caso que lock de LINHA não cobre: o mês não tem registro, o
    fechamento CRIA a linha. Sem o lock consultivo, o lançamento leria "não há
    linha", o fechamento comitaria, e o lançamento seria gravado em mês
    encerrado."""
    c = _cenario_commitado()
    assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).exists()

    with _pausando("fechamento_mes_caixa.encerrado") as (dentro, liberar):
        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"])
        )
        assert dentro.wait(timeout=30), "fechamento nunca chegou à pausa"

        lancar, res_lancar = _rodar_em_thread(
            lambda: criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 1, 20),
                valor="10.00",
                historico="Corrida com o fechamento",
                recebido_de="PJ",
            )
        )
        time.sleep(_PAUSA_CURTA)
        # O lançamento está ESPERANDO o fechamento — não terminou, e ainda não
        # gravou nada visível.
        assert lancar.is_alive(), "o lançamento não esperou o fechamento em andamento"
        assert not LancamentoCaixa.objects.filter(empresa=c["empresa"]).exists()

        liberar.set()
        _esperar(fechar, lancar)

    assert "erro" not in res_fechar, res_fechar
    assert isinstance(res_lancar.get("erro"), MesCaixaEncerrado), res_lancar
    assert not LancamentoCaixa.objects.filter(empresa=c["empresa"]).exists()
    assert FechamentoMesCaixa.objects.get(empresa=c["empresa"]).estado == EstadoMesCaixa.ENCERRADO


@pytest.mark.django_db(transaction=True)
def test_lancamento_em_andamento_faz_o_fechamento_esperar_e_os_dois_terminam_na_ordem_certa():
    """O inverso: o lançamento chegou primeiro e está no meio da transação. O
    fechamento espera; quando o lançamento comita, o fechamento encerra o mês
    JÁ com o lançamento dentro — ordem legítima (o lançamento aconteceu antes)."""
    c = _cenario_commitado()

    with _pausando("lancamento_caixa.criado") as (dentro, liberar):
        lancar, res_lancar = _rodar_em_thread(
            lambda: criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 1, 20),
                valor="10.00",
                historico="Lançamento em voo",
                recebido_de="PJ",
            )
        )
        assert dentro.wait(timeout=30), "lançamento nunca chegou à pausa"

        fechar, res_fechar = _rodar_em_thread(
            lambda: encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"])
        )
        time.sleep(_PAUSA_CURTA)
        assert fechar.is_alive(), "o fechamento não esperou o lançamento em andamento"
        assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).exists()

        liberar.set()
        _esperar(lancar, fechar)

    assert "erro" not in res_lancar, res_lancar
    assert "erro" not in res_fechar, res_fechar
    assert LancamentoCaixa.objects.filter(empresa=c["empresa"]).count() == 1
    assert FechamentoMesCaixa.objects.get(empresa=c["empresa"]).estado == EstadoMesCaixa.ENCERRADO


@pytest.mark.django_db(transaction=True)
def test_reabertura_em_andamento_faz_o_lancamento_esperar_e_depois_ser_aceito():
    c = _cenario_commitado()
    encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"])

    with _pausando("fechamento_mes_caixa.reaberto") as (dentro, liberar):
        reabrir, res_reabrir = _rodar_em_thread(
            lambda: reabrir_mes_caixa(
                empresa=c["empresa"], ano=2026, mes=1, usuario=c["gestor"], motivo="Correção"
            )
        )
        assert dentro.wait(timeout=30)
        lancar, res_lancar = _rodar_em_thread(
            lambda: criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 1, 20),
                valor="10.00",
                historico="Depois da reabertura",
                recebido_de="PJ",
            )
        )
        time.sleep(_PAUSA_CURTA)
        assert lancar.is_alive(), "o lançamento não esperou a reabertura em andamento"
        liberar.set()
        _esperar(reabrir, lancar)

    assert "erro" not in res_reabrir, res_reabrir
    assert "erro" not in res_lancar, res_lancar
    assert LancamentoCaixa.objects.filter(empresa=c["empresa"]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_dois_fechamentos_simultaneos_do_mesmo_mes_produzem_um_unico_fechamento():
    c = _cenario_commitado()
    barreira = threading.Barrier(2)

    def _fechar():
        barreira.wait(timeout=30)
        return encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=7, usuario=c["gestor"])

    t1, r1 = _rodar_em_thread(_fechar)
    t2, r2 = _rodar_em_thread(_fechar)
    _esperar(t1, t2)

    resultados = [r1, r2]
    sucessos = [r for r in resultados if "erro" not in r]
    falhas = [r for r in resultados if "erro" in r]
    assert len(sucessos) == 1, resultados
    assert len(falhas) == 1, resultados
    assert isinstance(falhas[0]["erro"], FechamentoMesCaixaRecusado), falhas
    assert FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).count() == 1
    assert (
        RegistroAuditoria.objects.filter(
            acao="fechamento_mes_caixa.encerrado", objeto_tipo="FechamentoMesCaixa"
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_corrida_repetida_de_fechamento_e_lancamento_num_mes_sem_registro_nunca_fura_a_trava():
    """Doze corridas sem pausa artificial, cada uma num mês sem registro.

    O que identifica a violação: o fechamento, já com o lock exclusivo, conta
    os lançamentos do mês; o total final tem de ser IGUAL a essa contagem.
    Se fosse maior, um lançamento teria comitado DEPOIS de o fechamento assumir
    o mês — ou seja, em mês encerrado."""
    c = _cenario_commitado()
    original_registrar = services.registrar
    visto_pelo_fechamento = {}

    def _registrar(*args, **kwargs):
        if kwargs.get("acao") == "fechamento_mes_caixa.encerrado":
            mes = kwargs["detalhes"]["mes"]
            visto_pelo_fechamento[mes] = LancamentoCaixa.objects.filter(
                empresa=c["empresa"], data__year=2025, data__month=mes
            ).count()
        return original_registrar(*args, **kwargs)

    desfechos = []
    with mock.patch.object(services, "registrar", _registrar):
        for mes in range(1, 13):
            barreira = threading.Barrier(2)

            def _lancar(mes=mes, barreira=barreira):
                barreira.wait(timeout=30)
                return criar_lancamento_caixa(
                    empresa=c["empresa"],
                    conta=c["conta"],
                    data=date(2025, mes, 15),
                    valor="10.00",
                    historico=f"Corrida do mês {mes}",
                    recebido_de="PJ",
                )

            def _fechar(mes=mes, barreira=barreira):
                barreira.wait(timeout=30)
                return encerrar_mes_caixa(
                    empresa=c["empresa"], ano=2025, mes=mes, usuario=c["gestor"]
                )

            tl, rl = _rodar_em_thread(_lancar)
            tf, rf = _rodar_em_thread(_fechar)
            _esperar(tl, tf)

            assert "erro" not in rf, (mes, rf)
            assert "erro" not in rl or isinstance(rl["erro"], MesCaixaEncerrado), (mes, rl)
            final = LancamentoCaixa.objects.filter(
                empresa=c["empresa"], data__year=2025, data__month=mes
            ).count()
            assert final == visto_pelo_fechamento[mes], (mes, final, visto_pelo_fechamento)
            assert final == (0 if "erro" in rl else 1), (mes, rl)
            assert (
                FechamentoMesCaixa.objects.get(empresa=c["empresa"], ano=2025, mes=mes).estado
                == EstadoMesCaixa.ENCERRADO
            )
            desfechos.append("recusado" if "erro" in rl else "gravado")

    # As duas ordens são legítimas; só a violação é proibida. O registro dos
    # desfechos ajuda a diagnosticar se a corrida deixou de ser exercitada.
    assert len(desfechos) == 12


def _segurar_lock_do_mes(empresa_id, ano, mes, preso, liberar):
    def _corpo():
        with transaction.atomic():
            services._adquirir_lock_do_mes(empresa_id=empresa_id, ano=ano, mes=mes, exclusivo=True)
            preso.set()
            assert liberar.wait(timeout=_TIMEOUT_DE_JOIN)

    return _rodar_em_thread(_corpo)


@pytest.mark.django_db(transaction=True)
def test_espera_que_estoura_o_lock_timeout_vira_409_de_dominio_e_nao_grava_nada():
    c = _cenario_commitado()
    preso, liberar = threading.Event(), threading.Event()
    segurando, res_segurando = _segurar_lock_do_mes(c["empresa"].id, 2026, 3, preso, liberar)
    try:
        assert preso.wait(timeout=30)

        with pytest.raises(MesCaixaOcupado) as ocupado:
            criar_lancamento_caixa(
                empresa=c["empresa"],
                conta=c["conta"],
                data=date(2026, 3, 10),
                valor="10.00",
                historico="Espera que estoura",
                recebido_de="PJ",
            )
        assert "Tente novamente" in str(ocupado.value)
        assert isinstance(ocupado.value, MesCaixaEncerrado)

        with pytest.raises(FechamentoMesCaixaTravado):
            encerrar_mes_caixa(empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"])
        with pytest.raises(FechamentoMesCaixaTravado):
            reabrir_mes_caixa(
                empresa=c["empresa"], ano=2026, mes=3, usuario=c["gestor"], motivo="Não chega"
            )
    finally:
        liberar.set()
        _esperar(segurando)

    assert "erro" not in res_segurando, res_segurando
    assert not LancamentoCaixa.objects.filter(empresa=c["empresa"]).exists()
    assert not FechamentoMesCaixa.objects.filter(empresa=c["empresa"]).exists()
    # Liberado o lock, tudo volta a funcionar.
    assert criar_lancamento_caixa(
        empresa=c["empresa"],
        conta=c["conta"],
        data=date(2026, 3, 10),
        valor="10.00",
        historico="Depois de liberar",
        recebido_de="PJ",
    ).pk


@pytest.mark.django_db(transaction=True)
def test_o_lock_e_por_empresa_e_por_mes_outro_mes_e_outra_empresa_nao_esperam():
    c = _cenario_commitado()
    outra = _cenario_commitado()
    preso, liberar = threading.Event(), threading.Event()
    segurando, res_segurando = _segurar_lock_do_mes(c["empresa"].id, 2026, 3, preso, liberar)
    try:
        assert preso.wait(timeout=30)
        inicio = time.monotonic()

        outro_mes = criar_lancamento_caixa(
            empresa=c["empresa"],
            conta=c["conta"],
            data=date(2026, 4, 10),
            valor="10.00",
            historico="Outro mês",
            recebido_de="PJ",
        )
        outra_empresa = criar_lancamento_caixa(
            empresa=outra["empresa"],
            conta=outra["conta"],
            data=date(2026, 3, 10),
            valor="10.00",
            historico="Outra empresa, mesmo mês",
            recebido_de="PJ",
        )
        outro_ano = criar_lancamento_caixa(
            empresa=c["empresa"],
            conta=c["conta"],
            data=date(2025, 3, 10),
            valor="10.00",
            historico="Mesmo mês, outro ano",
            recebido_de="PJ",
        )
        # Nenhum dos três esperou o lock segurado (que só estouraria em ~1,2 s).
        assert time.monotonic() - inicio < 1.0
        assert outro_mes.pk and outra_empresa.pk and outro_ano.pk
    finally:
        liberar.set()
        _esperar(segurando)
    assert "erro" not in res_segurando, res_segurando
