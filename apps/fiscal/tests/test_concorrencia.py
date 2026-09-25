"""Concorrência REAL (duas conexões de PostgreSQL) para o critério 28 do
plano DL-010-F1 — REVISTO por DE-076 (achado A3 da auditoria rodada 1):
duas recepções simultâneas do MESMO escritório nunca resultam em espera de
bloqueio nem impasse (*deadlock*), porque `receber_envio` serializa envios
por escritório com `pg_try_advisory_xact_lock` (que NÃO espera). Uma das
duas threads adquire o lock e processa normalmente; a OUTRA é recusada de
imediato com `EnvioInvalido` — mensagem legível, nunca 500, nada gravado
por ela.

Antes desta correção, as duas threads disputavam o MESMO índice único de
documento (`documento_fiscal_unico_por_escritorio`) dentro de transações
inteiras de envio — a auditoria mediu que isso produzia espera de lock
(`OperationalError` por `lock_timeout`) ou impasse (`deadlock detected`) em
envios grandes o bastante para a janela de corrida ficar real, e os dois
testes deste arquivo, escritos para transações de milissegundos, nunca
exercitavam essa janela.

`django_db(transaction=True)` é necessário para que as duas threads, cada
uma com sua própria conexão, enxerguem de fato o commit uma da outra — o
modo padrão de teste do Django envolve tudo numa transação que não seria
visível entre conexões (mesmo padrão de
apps/contabilidade/tests/test_bl40_bl41.py, testes de corrida real).

Os experimentos de ESPERA DE LOCK e DEADLOCK propostos pela auditoria (dois
ZIPs grandes disputando o mesmo índice) estão em
`test_dl076_um_envio_por_vez.py` — este arquivo cobre o caso mais simples
(a mesma nota/evento soltos, duas vezes), que já era o critério 28
original.
"""

from __future__ import annotations

import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.models import DocumentoFiscal, EventoFiscal
from apps.fiscal.tests.xml_sinteticos import xml_evento, xml_nfse
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio


@pytest.mark.django_db(transaction=True)
def test_corrida_real_de_documento_produz_um_unico_documento():
    escritorio = Escritorio.objects.create(nome="Escritório Corrida Fiscal", cnpj="33333333000144")
    # A empresa precisa existir (prestador da NFS-e sintética) para o
    # documento ser aceito, mas não é referenciada diretamente no teste.
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Corrida Fiscal Ltda", cnpj="11222333000181"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-corrida-fiscal",
        email="gestor-corrida-fiscal@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    conteudo = xml_nfse(incluir_tomador=False)

    resultados = []
    recusados_por_lock = []
    erros = []
    barreira = threading.Barrier(2)

    def tentar_receber():
        barreira.wait()
        try:
            lote = services.receber_envio(
                escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo="nota.xml"
            )
            resultados.append(lote.total_recebidos)
        except services.EnvioInvalido as exc:
            # DE-076 item 1: a thread que NÃO consegue o lock é recusada
            # de imediato — nunca espera, nunca disputa o índice.
            recusados_por_lock.append(exc)
        except Exception as exc:  # qualquer OUTRA exceção é o defeito que este teste prova
            erros.append(exc)
        finally:
            connection.close()  # cada thread precisa fechar a própria conexão

    threads = [threading.Thread(target=tentar_receber) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert erros == []
    # Exatamente uma thread processa (e recebe a nota); a outra é recusada
    # pelo lock — nunca as duas processando, nunca as duas recusadas.
    assert len(resultados) == 1, (resultados, recusados_por_lock)
    assert resultados[0] == 1
    assert len(recusados_por_lock) == 1
    assert services.MENSAGEM_ENVIO_EM_ANDAMENTO in recusados_por_lock[0].messages
    assert DocumentoFiscal.objects.filter(escritorio=escritorio).count() == 1


@pytest.mark.django_db(transaction=True)
def test_corrida_real_de_evento_produz_um_unico_evento():
    escritorio = Escritorio.objects.create(nome="Escritório Corrida Evento", cnpj="44444444000155")
    usuario = get_user_model().objects.create_user(
        username="gestor-corrida-evento",
        email="gestor-corrida-evento@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    conteudo = xml_evento()

    resultados = []
    recusados_por_lock = []
    erros = []
    barreira = threading.Barrier(2)

    def tentar_receber():
        barreira.wait()
        try:
            lote = services.receber_envio(
                escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo="evento.xml"
            )
            resultados.append(lote.total_recebidos)
        except services.EnvioInvalido as exc:
            recusados_por_lock.append(exc)
        except Exception as exc:
            erros.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=tentar_receber) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert erros == []
    assert len(resultados) == 1, (resultados, recusados_por_lock)
    assert resultados[0] == 1
    assert len(recusados_por_lock) == 1
    assert services.MENSAGEM_ENVIO_EM_ANDAMENTO in recusados_por_lock[0].messages
    assert EventoFiscal.objects.filter(escritorio=escritorio).count() == 1
