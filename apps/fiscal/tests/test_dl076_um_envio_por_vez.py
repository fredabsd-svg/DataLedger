"""DE-076 item 1 (achado A3 da auditoria rodada 1) — os dois experimentos
que o auditor mediu como 500 antes da correção: espera de lock e impasse
(deadlock) entre dois envios REAIS do MESMO escritório.

`django_db(transaction=True)` e threads reais — mesmo padrão de
`test_concorrencia.py`, aqui com envios GRANDES o bastante para a janela
de corrida ficar real (a auditoria mediu com 1.500+ notas; usamos uma
contagem menor, mas ainda maior que a janela de processamento de UMA nota,
o suficiente para a segunda thread quase sempre encontrar a primeira já
dentro da transação — o teste não depende de vencer a corrida sempre no
mesmo sentido, só de nunca haver exceção não tratada, e de a PERDEDORA
sempre receber a mensagem de "envio em processamento").
"""

from __future__ import annotations

import threading
import time

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.models import DocumentoFiscal, LoteDeRecepcao
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse, zip_de
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

# Menor que os 5.850/10.000 arquivos que os testes de vazão exercitam —
# aqui só precisa ser grande o bastante para o processamento levar tempo
# mensurável (dezenas de milissegundos), para a segunda thread quase
# sempre chegar enquanto a primeira ainda está dentro da transação.
_QUANTIDADE_NOTAS_ENVIO_GRANDE = 300


@pytest.mark.django_db(transaction=True)
def test_espera_de_lock_nao_produz_excecao_e_a_perdedora_recebe_a_mensagem():
    escritorio = Escritorio.objects.create(nome="Escritório Lock A3", cnpj="66666666000177")
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Lock A3 Ltda", cnpj="11222333000181"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-lock-a3", email="gestor-lock-a3@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    nota_comum = identificador_nfse(sufixo=1)
    itens_thread_1 = {"comum.xml": xml_nfse(identificador=nota_comum, incluir_tomador=False)}
    for i in range(2, 2 + _QUANTIDADE_NOTAS_ENVIO_GRANDE):
        itens_thread_1[f"n{i}.xml"] = xml_nfse(
            identificador=identificador_nfse(sufixo=i), incluir_tomador=False
        )
    zip_grande = zip_de(itens_thread_1)
    zip_solta = zip_de({"comum.xml": xml_nfse(identificador=nota_comum, incluir_tomador=False)})

    resultados = {}
    erros = {}

    def _thread_1():
        try:
            lote = services.receber_envio(
                escritorio=escritorio,
                usuario=usuario,
                arquivo=zip_grande,
                nome_arquivo="grande.zip",
            )
            resultados["1"] = lote
        except Exception as exc:  # nunca deveria propagar sem ser EnvioInvalido tratado abaixo
            erros["1"] = exc
        finally:
            connection.close()

    def _thread_2():
        time.sleep(0.05)  # dá tempo da thread 1 entrar na transação primeiro
        try:
            lote = services.receber_envio(
                escritorio=escritorio, usuario=usuario, arquivo=zip_solta, nome_arquivo="solta.xml"
            )
            resultados["2"] = lote
        except services.EnvioInvalido as exc:
            resultados["2"] = exc
        except Exception as exc:
            erros["2"] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=_thread_1)
    t2 = threading.Thread(target=_thread_2)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # O ponto central do achado A3: NENHUMA exceção não tratada, dos dois
    # lados — nem `OperationalError` de espera de lock, nem qualquer outra.
    assert erros == {}, erros

    # A thread 1 (mais rápida a começar, envio maior) deveria vencer o
    # lock quase sempre, mas o teste não EXIGE essa ordem — só que
    # exatamente uma das duas processe de verdade e a outra seja recusada
    # pelo bloqueio, com a mensagem certa.
    lotes = [v for v in resultados.values() if isinstance(v, LoteDeRecepcao)]
    recusas = [v for v in resultados.values() if isinstance(v, services.EnvioInvalido)]
    assert len(lotes) == 1, resultados
    assert len(recusas) == 1, resultados
    assert services.MENSAGEM_ENVIO_EM_ANDAMENTO in recusas[0].messages
    assert (
        DocumentoFiscal.objects.filter(escritorio=escritorio, identificador=nota_comum).count() == 1
    )


@pytest.mark.django_db(transaction=True)
def test_deadlock_nao_ocorre_mais_porque_envios_do_mesmo_escritorio_sao_serializados():
    # Cenário original do achado A3: ZIP [A, B] e ZIP [B, A] simultâneos —
    # antes da DE-076, cada envio inseria A e B dentro da MESMA transação
    # de envio, e a ORDEM OPOSTA entre as duas threads produzia impasse
    # real (deadlock detected) no índice único de documento. Com a
    # serialização por escritório, as duas nunca chegam a disputar o
    # índice ao mesmo tempo: uma delas é recusada pelo lock ANTES de
    # tocar em qualquer documento.
    escritorio = Escritorio.objects.create(nome="Escritório Deadlock A3", cnpj="77777777000188")
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Deadlock A3 Ltda", cnpj="11222333000181"
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-deadlock-a3",
        email="gestor-deadlock-a3@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    identificador_a = identificador_nfse(sufixo=101)
    identificador_b = identificador_nfse(sufixo=102)
    zip_ab = zip_de(
        {
            "a.xml": xml_nfse(identificador=identificador_a, incluir_tomador=False),
            "b.xml": xml_nfse(identificador=identificador_b, incluir_tomador=False),
        }
    )
    zip_ba = zip_de(
        {
            "b.xml": xml_nfse(identificador=identificador_b, incluir_tomador=False),
            "a.xml": xml_nfse(identificador=identificador_a, incluir_tomador=False),
        }
    )

    barreira = threading.Barrier(2)
    resultados = {}
    erros = {}

    def _enviar(chave, conteudo, nome):
        barreira.wait()
        try:
            lote = services.receber_envio(
                escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo=nome
            )
            resultados[chave] = lote
        except services.EnvioInvalido as exc:
            resultados[chave] = exc
        except Exception as exc:
            erros[chave] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=_enviar, args=("AB", zip_ab, "ab.zip"))
    t2 = threading.Thread(target=_enviar, args=("BA", zip_ba, "ba.zip"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert erros == {}, erros

    lotes = [v for v in resultados.values() if isinstance(v, LoteDeRecepcao)]
    recusas = [v for v in resultados.values() if isinstance(v, services.EnvioInvalido)]
    assert len(lotes) == 1, resultados
    assert len(recusas) == 1, resultados
    assert services.MENSAGEM_ENVIO_EM_ANDAMENTO in recusas[0].messages
    assert DocumentoFiscal.objects.filter(escritorio=escritorio).count() == 2
