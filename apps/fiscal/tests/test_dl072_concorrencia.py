"""DL-072 (frente A) — critério 6: efetivar duas vezes não cria duas ativas.

Cada thread usa a SUA conexão de PostgreSQL, por isso o teste é marcado com
`transaction=True`: sem commit real, uma thread não enxergaria a outra (mesmo
padrão de `test_concorrencia.py`, do recebimento de NFS-e).

Três provas, em camadas:
1. Dois cliques pelo serviço, mesma natureza: os dois voltam sem erro, há UMA
   escrituração e UMA entrada na trilha.
2. Dois cliques pelo serviço, naturezas diferentes: um vence, o outro recebe
   409 de negócio (`EscrituracaoErro`), e há UMA ativa.
3. Corrida no nível do banco, sem a trava do serviço: dois INSERTs ao mesmo
   tempo. O resultado é determinístico — exatamente um passa e o outro cai na
   restrição `escrituracao_ativa_unica_por_vinculo`. Sem a restrição, os dois
   passariam; é esta prova que o mutante de unicidade derruba.

Todo `join()` tem timeout e uma asserção depois. Thread travada vira falha
visível, não suíte que pendura.
"""

import threading

import pytest
from django.db import IntegrityError, connection

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao as servico
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    EstadoEscrituracao,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse

pytestmark = pytest.mark.django_db(transaction=True)

NATUREZA = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
OUTRA = NaturezaOperacao.PRESTADO_ISS_RETIDO
TIMEOUT_SEGUNDOS = 30


def _preparar(escritorio, empresa, usuario):
    identificador = identificador_nfse(1)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(identificador=identificador, numero="1"),
        nome_arquivo="nota.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)
    return VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )


def _em_paralelo(alvos):
    """Roda `alvos` (lista de callables) em threads, cada uma com a própria
    conexão, e devolve [(resultado, erro)] na ordem dos alvos."""
    barreira = threading.Barrier(len(alvos))
    resultados = [None] * len(alvos)

    def correr(indice, alvo):
        try:
            barreira.wait(timeout=TIMEOUT_SEGUNDOS)
            resultados[indice] = (alvo(), None)
        except BaseException as exc:  # noqa: BLE001 — o erro é o dado do teste
            resultados[indice] = (None, exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=correr, args=(i, a)) for i, a in enumerate(alvos)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT_SEGUNDOS)
    assert not any(t.is_alive() for t in threads), "thread travada: falha, não espera infinita"
    assert all(r is not None for r in resultados), "alguma thread não devolveu resultado"
    return resultados


def test_dois_cliques_com_a_mesma_natureza_geram_uma_escrituracao(
    escritorio_a, empresa_a, usuario_gestor_a
):
    vinculo = _preparar(escritorio_a, empresa_a, usuario_gestor_a)

    resultados = _em_paralelo(
        [
            lambda: servico.efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a),
            lambda: servico.efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a),
        ]
    )

    assert [erro for _, erro in resultados] == [None, None], resultados
    assert EscrituracaoFiscal.objects.count() == 1
    assert EscrituracaoFiscal.objects.get().estado == EstadoEscrituracao.EFETIVADA
    # Uma das duas criou; a outra só reconheceu a existente (idempotência).
    criadas = [escrituracao.criada_agora for escrituracao, _ in resultados]
    assert sorted(criadas) == [False, True]
    assert RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.efetivada").count() == 1, (
        "a repetição não pode gerar segunda entrada na trilha"
    )


def test_dois_cliques_com_naturezas_diferentes_um_vence_e_o_outro_e_409(
    escritorio_a, empresa_a, usuario_gestor_a
):
    vinculo = _preparar(escritorio_a, empresa_a, usuario_gestor_a)

    resultados = _em_paralelo(
        [
            lambda: servico.efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a),
            lambda: servico.efetivar_escrituracao(vinculo, OUTRA, usuario_gestor_a),
        ]
    )

    erros = [erro for _, erro in resultados if erro is not None]
    vencedores = [escrituracao for escrituracao, erro in resultados if erro is None]
    assert len(vencedores) == 1, resultados
    assert len(erros) == 1
    assert isinstance(erros[0], servico.EscrituracaoErro), erros[0]
    assert EscrituracaoFiscal.objects.count() == 1
    assert EscrituracaoFiscal.objects.get().natureza == vencedores[0].natureza


def test_corrida_direto_no_banco_deixa_passar_so_uma_linha_ativa(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Sem a trava do serviço: dois INSERTs de rascunho ao mesmo tempo para o
    # mesmo vínculo. O resultado não depende do tempo: exatamente um passa.
    vinculo = _preparar(escritorio_a, empresa_a, usuario_gestor_a)

    def inserir():
        return EscrituracaoFiscal.objects.create(
            vinculo=vinculo,
            empresa=empresa_a,
            natureza=NATUREZA,
            estado=EstadoEscrituracao.RASCUNHO,
            criado_por=usuario_gestor_a,
        )

    resultados = _em_paralelo([inserir, inserir])

    sucessos = [r for r, erro in resultados if erro is None]
    falhas = [erro for _, erro in resultados if erro is not None]
    assert len(sucessos) == 1, resultados
    assert len(falhas) == 1
    assert isinstance(falhas[0], IntegrityError), falhas[0]
    diag = getattr(falhas[0].__cause__, "diag", None)
    assert diag is not None and diag.constraint_name == "escrituracao_ativa_unica_por_vinculo"
    assert EscrituracaoFiscal.objects.count() == 1


def test_efetivacoes_de_notas_diferentes_nao_se_bloqueiam(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Trava por VÍNCULO, não global: duas notas em paralelo, as duas efetivam.
    vinculo_a = _preparar(escritorio_a, empresa_a, usuario_gestor_a)
    identificador_b = identificador_nfse(2)
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(identificador=identificador_b, numero="2"),
        nome_arquivo="nota2.xml",
    )
    documento_b = DocumentoFiscal.objects.get(
        escritorio=escritorio_a, identificador=identificador_b
    )
    vinculo_b = VinculoDocumentoEmpresa.objects.get(
        documento=documento_b, empresa=empresa_a, papel=PapelDocumento.PRESTADOR
    )

    resultados = _em_paralelo(
        [
            lambda: servico.efetivar_escrituracao(vinculo_a, NATUREZA, usuario_gestor_a),
            lambda: servico.efetivar_escrituracao(vinculo_b, NATUREZA, usuario_gestor_a),
        ]
    )

    assert [erro for _, erro in resultados] == [None, None]
    assert EscrituracaoFiscal.objects.filter(estado=EstadoEscrituracao.EFETIVADA).count() == 2
