"""Concorrência REAL (duas conexões de PostgreSQL) para o critério 28 do
plano DL-010-F1: duas recepções simultâneas da MESMA nota resultam em UM
documento e um resultado "duplicado" — nunca uma falha 500 (IntegrityError
não tratado).

`django_db(transaction=True)` é necessário para que as duas threads, cada
uma com sua própria conexão, enxerguem de fato o commit uma da outra — o
modo padrão de teste do Django envolve tudo numa transação que não seria
visível entre conexões (mesmo padrão de
apps/contabilidade/tests/test_bl40_bl41.py, testes de corrida real).
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
    erros = []
    barreira = threading.Barrier(2)

    def tentar_receber():
        barreira.wait()
        try:
            lote = services.receber_envio(
                escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo="nota.xml"
            )
            resultados.append(lote.total_recebidos)
        except (
            Exception
        ) as exc:  # nunca deveria propagar — se propagar, é o defeito que o teste prova
            erros.append(exc)
        finally:
            connection.close()  # cada thread precisa fechar a própria conexão

    threads = [threading.Thread(target=tentar_receber) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert erros == []
    # Uma thread recebe (total_recebidos=1), a outra vê duplicado
    # (total_recebidos=0) — nunca as duas com 1.
    assert sorted(resultados) == [0, 1]
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
    erros = []
    barreira = threading.Barrier(2)

    def tentar_receber():
        barreira.wait()
        try:
            lote = services.receber_envio(
                escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo="evento.xml"
            )
            resultados.append(lote.total_recebidos)
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
    assert sorted(resultados) == [0, 1]
    assert EventoFiscal.objects.filter(escritorio=escritorio).count() == 1
