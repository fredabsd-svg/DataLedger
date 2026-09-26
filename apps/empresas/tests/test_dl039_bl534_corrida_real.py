"""Achado D2 da auditoria DL-039 rodada 1 (BL-534): os dois gatilhos da
migração 0010 não se travavam um contra o outro. O `SELECT tipo_inscricao
... FROM empresas_empresa` do gatilho de Estabelecimento não travava a
linha da empresa — a trava automática de FK do INSERT (`FOR KEY SHARE`)
não conflita com a trava automática do UPDATE de coluna comum (`FOR NO
KEY UPDATE`) — então as duas transações corriam em paralelo sem nunca se
travarem, e as duas confirmavam: empresa CPF **com** estabelecimento
gravada, exatamente o estado que os gatilhos existem para impedir.

Correção (migração 0011): o gatilho de Estabelecimento passou a ler a
empresa com `SELECT ... FOR SHARE`, que CONFLITA com `FOR NO KEY UPDATE`
— agora as duas ordens serializam de verdade.

Caso de teste proposto pelo relatório, reproduzido aqui com DUAS conexões
reais (`transaction=True`, sem mock de banco nenhum), nas DUAS ordens:
nunca `Empresa(tipo_inscricao="CPF")` com estabelecimento sobra, e a
transação perdedora recebe uma recusa LEGÍVEL (a mesma mensagem de
negócio do gatilho — nunca um erro genérico de lock/deadlock/timeout, e
nunca as duas confirmarem juntas).
"""

from __future__ import annotations

import threading
import time

import pytest
from django.db import IntegrityError, connection, transaction

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento, TipoInscricao
from apps.tenancy.models import Escritorio


def _mensagem_e_legivel(exc: IntegrityError) -> bool:
    texto = str(exc)
    return "pessoa jurídica" in texto or "estabelecimento" in texto


@pytest.mark.django_db(transaction=True)
def test_corrida_insert_estabelecimento_primeiro_nunca_deixa_cpf_com_estabelecimento():
    # Ordem 1: o INSERT do estabelecimento acontece PRIMEIRO e fica aberto
    # (segurando o `FOR SHARE` da linha da empresa) — o UPDATE de
    # `tipo_inscricao` na outra transação tem que ESPERAR o commit, e só
    # então enxergar o estabelecimento (já committed) e ser recusado.
    escritorio = Escritorio.objects.create(nome="Escritório BL-534 A", cnpj="91100000000091")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-534 A Ltda", cnpj="11122233000183"
    )

    resultados = {}
    erros = {}
    estabelecimento_inserido = threading.Event()

    def _thread_insere_estabelecimento():
        try:
            with transaction.atomic():
                Estabelecimento.objects.create(
                    empresa_id=empresa.pk,
                    tipo=TipoEstabelecimento.MATRIZ,
                    nome="Matriz BL-534 A",
                    cnpj="AB123CDE000155",
                )
                estabelecimento_inserido.set()
                # Mantém a transação aberta por tempo suficiente para a
                # outra thread tentar o UPDATE e ficar bloqueada na trava
                # FOR SHARE, esperando este commit.
                time.sleep(0.3)
            resultados["insert"] = "sucesso"
        except IntegrityError as exc:
            erros["insert"] = exc
        finally:
            connection.close()

    def _thread_atualiza_para_cpf():
        assert estabelecimento_inserido.wait(timeout=5), "estabelecimento não inseriu a tempo"
        try:
            with transaction.atomic():
                Empresa.objects.filter(pk=empresa.pk).update(
                    tipo_inscricao=TipoInscricao.CPF, cnpj="", cpf="11144477735"
                )
            resultados["update"] = "sucesso"
        except IntegrityError as exc:
            erros["update"] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=_thread_insere_estabelecimento)
    t2 = threading.Thread(target=_thread_atualiza_para_cpf)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(resultados) == 1, (resultados, erros)
    assert len(erros) == 1, (resultados, erros)
    (excecao,) = erros.values()
    assert _mensagem_e_legivel(excecao), str(excecao)

    empresa.refresh_from_db()
    tem_estabelecimento = empresa.estabelecimentos.exists()
    assert not (empresa.tipo_inscricao == TipoInscricao.CPF and tem_estabelecimento), (
        "CORRIDA CPF com estabelecimento: estado inconsistente sobrou"
    )


@pytest.mark.django_db(transaction=True)
def test_corrida_update_para_cpf_primeiro_nunca_deixa_cpf_com_estabelecimento():
    # Ordem 2 (inversa): o UPDATE de `tipo_inscricao` acontece PRIMEIRO e
    # fica aberto (segurando o `FOR NO KEY UPDATE` da linha da empresa) —
    # o INSERT do estabelecimento, na outra transação, tem que ESPERAR o
    # commit (bloqueado no `FOR SHARE`), e só então enxergar
    # `tipo_inscricao='CPF'` (já committed) e ser recusado.
    escritorio = Escritorio.objects.create(nome="Escritório BL-534 B", cnpj="91100000000092")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-534 B Ltda", cnpj="11122233000183"
    )

    resultados = {}
    erros = {}
    empresa_atualizada = threading.Event()

    def _thread_atualiza_para_cpf():
        try:
            with transaction.atomic():
                Empresa.objects.filter(pk=empresa.pk).update(
                    tipo_inscricao=TipoInscricao.CPF, cnpj="", cpf="11144477735"
                )
                empresa_atualizada.set()
                time.sleep(0.3)
            resultados["update"] = "sucesso"
        except IntegrityError as exc:
            erros["update"] = exc
        finally:
            connection.close()

    def _thread_insere_estabelecimento():
        assert empresa_atualizada.wait(timeout=5), "empresa não atualizou a tempo"
        try:
            with transaction.atomic():
                Estabelecimento.objects.create(
                    empresa_id=empresa.pk,
                    tipo=TipoEstabelecimento.MATRIZ,
                    nome="Matriz BL-534 B",
                    cnpj="AB123CDE000155",
                )
            resultados["insert"] = "sucesso"
        except IntegrityError as exc:
            erros["insert"] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=_thread_atualiza_para_cpf)
    t2 = threading.Thread(target=_thread_insere_estabelecimento)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(resultados) == 1, (resultados, erros)
    assert len(erros) == 1, (resultados, erros)
    (excecao,) = erros.values()
    assert _mensagem_e_legivel(excecao), str(excecao)

    empresa.refresh_from_db()
    tem_estabelecimento = empresa.estabelecimentos.exists()
    assert not (empresa.tipo_inscricao == TipoInscricao.CPF and tem_estabelecimento), (
        "CORRIDA CPF com estabelecimento: estado inconsistente sobrou"
    )
