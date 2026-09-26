"""Achado N2 da reconferência (BL-527, DL-039): a trava por escritório
(DE-076 item 1, achado A3) estava correta, mas três comportamentos
sobreviviam a mutações sem NENHUM teste capaz de reprová-las:

- **N04:** a chave da trava usar `escritorio.pk` de verdade — sem isso, o
  envio de um escritório B ficaria recusado enquanto o A segura a trava
  (falso positivo ENTRE escritórios, quebra o critério 27 de isolamento
  de forma nova: um escritório atrapalharia o outro).
- **N05:** `_e_erro_de_lock_ou_deadlock` discriminar de verdade — sem
  isso, qualquer `OperationalError` (inclusive erro de sistema genuíno)
  viraria "conflito de envio, tente de novo", mascarando a falha.
- **N06:** o `raise` de `OperationalError` dentro do `except` por arquivo
  não pode ser retirado silenciosamente — um deadlock ou timeout de lock
  durante a gravação de UM arquivo tem que subir até `receber_envio`
  tratar (ou propagar), nunca virar "recusado" só daquele arquivo.
"""

from __future__ import annotations

import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError, connection, transaction

from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.models import LoteDeRecepcao
from apps.fiscal.tests.xml_sinteticos import xml_nfse
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


# --- N04: a chave da trava tem que incluir o escritório -----------------


@pytest.mark.django_db(transaction=True)
def test_trava_do_escritorio_a_nao_bloqueia_envio_do_escritorio_b(escritorio_a, escritorio_b):
    Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B BL-527 Ltda", cnpj="11222333000181"
    )
    usuario_b = get_user_model().objects.create_user(
        username="gestor-b-bl527", email="gestor-b-bl527@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_b, escritorio=escritorio_b, papel=Papel.GESTOR
    )

    trava_obtida = threading.Event()
    pode_liberar = threading.Event()

    def _segurar_a_trava_do_escritorio_a():
        with transaction.atomic():
            obteve = services._adquirir_lock_de_envio_do_escritorio(escritorio_a)
            assert obteve is True
            trava_obtida.set()
            # Segura a transação aberta (e a trava com ela) até o teste
            # terminar de exercitar o escritório B.
            pode_liberar.wait(timeout=5)
        connection.close()

    thread_a = threading.Thread(target=_segurar_a_trava_do_escritorio_a)
    thread_a.start()
    assert trava_obtida.wait(timeout=5), "thread A não conseguiu a trava a tempo"

    try:
        # Achado N04: SE a chave da trava não incluísse `escritorio.pk`
        # (por exemplo, uma constante fixa), este envio do escritório B
        # seria recusado com `MENSAGEM_ENVIO_EM_ANDAMENTO` — falso
        # positivo entre escritórios DIFERENTES, nunca o comportamento
        # pretendido (a trava é só POR escritório).
        lote_b = services.receber_envio(
            escritorio=escritorio_b,
            usuario=usuario_b,
            arquivo=xml_nfse(prestador_documento="11222333000181", incluir_tomador=False),
            nome_arquivo="nota-b.xml",
        )
        assert lote_b.total_recebidos == 1
    finally:
        pode_liberar.set()
        thread_a.join(timeout=5)


# --- N05: `_e_erro_de_lock_ou_deadlock` discrimina de verdade ------------


class _CausaComPgcode(Exception):
    """`__cause__` precisa derivar de `BaseException` — psycopg expõe
    `pgcode` num atributo do driver, que É uma exceção encadeada de
    verdade; este dublê só precisa se comportar como uma para o teste."""

    def __init__(self, pgcode):
        super().__init__(pgcode)
        self.pgcode = pgcode


@pytest.mark.parametrize("pgcode", ["40P01", "55P03", "57014"])
def test_erro_com_sqlstate_de_lock_ou_deadlock_e_reconhecido(pgcode):
    exc = OperationalError("erro de banco qualquer")
    exc.__cause__ = _CausaComPgcode(pgcode)
    assert services._e_erro_de_lock_ou_deadlock(exc) is True


def test_erro_com_texto_de_deadlock_sem_pgcode_e_reconhecido():
    exc = OperationalError("deadlock detected while processing")
    assert services._e_erro_de_lock_ou_deadlock(exc) is True


def test_erro_de_conexao_generico_nao_e_reconhecido_como_lock_ou_deadlock():
    # Achado N05: este é o experimento que mata a mutação "sempre True" —
    # um `OperationalError` que NÃO é de lock/deadlock (por exemplo, perda
    # de conexão com o servidor) tem que continuar `False`, para subir
    # intacto em vez de virar "conflito, tente de novo".
    exc = OperationalError("server closed the connection unexpectedly")
    assert services._e_erro_de_lock_ou_deadlock(exc) is False


def test_erro_com_pgcode_de_outra_categoria_nao_e_reconhecido():
    exc = OperationalError("connection timed out")
    exc.__cause__ = _CausaComPgcode("08006")  # connection_failure, não é lock/deadlock
    assert services._e_erro_de_lock_ou_deadlock(exc) is False


# --- N06: `OperationalError` por arquivo tem que propagar até quem chama -


def test_operational_error_nao_lock_dentro_de_um_arquivo_propaga_ate_receber_envio(
    monkeypatch, escritorio_a, empresa_a, usuario_gestor_a
):
    # Achado N06: SE o `raise` dentro do `except` por arquivo fosse
    # retirado (ou se o erro fosse engolido antes de chegar lá), este
    # `OperationalError` viraria "recusado" só do arquivo, e o lote
    # terminaria como se nada de anormal tivesse acontecido. Este
    # `OperationalError` não é de lock/deadlock (mensagem não bate no
    # padrão), então nem a camada de `receber_envio` deveria traduzi-lo em
    # `EnvioInvalido` — tem que subir intacto.
    def _levanta_operational_error(*args, **kwargs):
        raise OperationalError("connection reset by peer")

    monkeypatch.setattr(services, "_criar_documento_e_vinculos", _levanta_operational_error)

    with pytest.raises(OperationalError):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=xml_nfse(incluir_tomador=False),
            nome_arquivo="nota.xml",
        )

    assert not LoteDeRecepcao.objects.filter(escritorio=escritorio_a).exists()


def test_operational_error_de_lock_dentro_de_um_arquivo_vira_envio_invalido_legivel(
    monkeypatch, escritorio_a, empresa_a, usuario_gestor_a
):
    # Simetria do teste acima: quando o `OperationalError` por arquivo É de
    # lock/deadlock, `receber_envio` traduz para `EnvioInvalido` legível —
    # nunca 500, e também nunca "recusado" silencioso por arquivo.
    def _levanta_deadlock(*args, **kwargs):
        exc = OperationalError("deadlock detected")
        exc.__cause__ = _CausaComPgcode("40P01")
        raise exc

    monkeypatch.setattr(services, "_criar_documento_e_vinculos", _levanta_deadlock)

    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=xml_nfse(incluir_tomador=False),
            nome_arquivo="nota.xml",
        )

    assert not LoteDeRecepcao.objects.filter(escritorio=escritorio_a).exists()


# --- Revisão da DL-039 (Fred): a trava não pode quebrar fora do PostgreSQL


def test_trava_e_ignorada_fora_do_postgresql_sem_chamar_funcao_pg(
    monkeypatch, escritorio_a, empresa_a, usuario_gestor_a
):
    # `pg_try_advisory_xact_lock` é função do PostgreSQL — não existe em
    # SQLite, que `config/settings.py` permite em desenvolvimento
    # (`DEBUG=True` sem `DATABASE_URL`, BL-50/DE-014). Sem esta guarda, um
    # envio pela tela em SQLite local quebrava ao tentar adquirir o lock.
    # Este teste roda contra o PostgreSQL real da suíte (não troca de
    # banco), mas SIMULA `connection.vendor` como se fosse outro banco —
    # o suficiente para provar que `_adquirir_lock_de_envio_do_escritorio`
    # nem TENTA chamar a função pg_* quando o vendor não é "postgresql":
    # se tentasse, o SQL abaixo (que não muda) continuaria funcionando
    # (o banco real é PostgreSQL) e este teste não provaria nada — por
    # isso o teste de ponta a ponta em SQLite de verdade
    # (test_dl039_bl529_gatilho_sqlite.py) é quem fecha a prova completa.
    chamou_o_cursor = []
    cursor_original = connection.cursor

    def _cursor_espiao(*args, **kwargs):
        chamou_o_cursor.append(True)
        return cursor_original(*args, **kwargs)

    monkeypatch.setattr(services.connection, "vendor", "sqlite")
    monkeypatch.setattr(services.connection, "cursor", _cursor_espiao)

    obteve = services._adquirir_lock_de_envio_do_escritorio(escritorio_a)

    assert obteve is True
    assert chamou_o_cursor == []


def test_receber_envio_funciona_com_vendor_simulado_de_nao_postgresql(
    monkeypatch, escritorio_a, empresa_a, usuario_gestor_a
):
    # Fim a fim: com o vendor simulado como não-PostgreSQL, `receber_envio`
    # continua funcionando (a trava vira sempre `True`, nunca recusa por
    # "conflito de envio").
    monkeypatch.setattr(services.connection, "vendor", "sqlite")

    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(incluir_tomador=False),
        nome_arquivo="nota.xml",
    )

    assert lote.total_recebidos == 1
