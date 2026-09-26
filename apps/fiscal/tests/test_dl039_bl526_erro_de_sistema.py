"""Achado N1 da reconferência (BL-526, DL-039): o `except` de erro de banco
por arquivo, dentro de `_processar_um_arquivo`, capturava QUALQUER
`django.db.Error` que não fosse `OperationalError` — inclusive
`ProgrammingError`, `InternalError`, `InterfaceError` e `NotSupportedError`,
que indicam defeito de SISTEMA (esquema desatualizado, migração não
aplicada, conexão quebrada), não arquivo ruim. Isso fazia uma falha de
implantação aparecer ao contador como "arquivos recusados", com
`LoteDeRecepcao` e trilha de auditoria de envio CONCLUÍDO — um sistema
quebrado parecendo funcionar. A mensagem também ecoava `str(exc)` do banco
(nome de tabela/coluna).

Correção: só `DataError` (defeito do CONTEÚDO do arquivo) vira "recusado",
com mensagem NEUTRA; qualquer outro erro de banco sobe intacto e desfaz o
envio INTEIRO (nem `LoteDeRecepcao`, nem `ResultadoDoArquivo`, nem a
trilha).
"""

from __future__ import annotations

import pytest
from django.db import DataError, InterfaceError, InternalError, NotSupportedError, ProgrammingError

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import services
from apps.fiscal.models import LoteDeRecepcao, ResultadoDoArquivo, TipoResultadoArquivo
from apps.fiscal.tests.xml_sinteticos import xml_nfse

pytestmark = pytest.mark.django_db


def test_data_error_vira_recusado_com_mensagem_neutra_sem_texto_do_banco(
    monkeypatch, escritorio_a, empresa_a, usuario_gestor_a
):
    detalhe_interno = 'value too long for type character varying(20): coluna "numero" da tabela X'

    def _levanta_data_error(*args, **kwargs):
        raise DataError(detalhe_interno)

    monkeypatch.setattr(services, "_criar_documento_e_vinculos", _levanta_data_error)

    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(incluir_tomador=False),
        nome_arquivo="nota.xml",
    )

    assert lote.total_recusados == 1
    resultado = lote.resultados.get()
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert resultado.motivo == services.MENSAGEM_ERRO_DE_DADOS_NO_ARQUIVO
    # A mensagem NUNCA ecoa o texto interno do banco (nome de coluna/tabela).
    assert detalhe_interno not in resultado.motivo
    assert "varying" not in resultado.motivo
    assert "coluna" not in resultado.motivo.lower()


@pytest.mark.parametrize(
    "excecao", [ProgrammingError, InternalError, InterfaceError, NotSupportedError]
)
def test_erro_de_sistema_propaga_e_desfaz_o_envio_inteiro_sem_lote_nem_trilha(
    monkeypatch, excecao, escritorio_a, empresa_a, usuario_gestor_a
):
    # O ponto central do achado: a exceção NUNCA pode ser engolida — se um
    # dia um `except` mais largo voltar a capturá-la (regressão), este
    # teste reprova, porque `pytest.raises` não vai ver nada subir.
    def _levanta(*args, **kwargs):
        raise excecao("erro de sistema simulado")

    monkeypatch.setattr(services, "_criar_documento_e_vinculos", _levanta)

    with pytest.raises(excecao):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=xml_nfse(incluir_tomador=False),
            nome_arquivo="nota.xml",
        )

    # Nada foi gravado: nem o lote, nem o resultado do arquivo, nem a
    # trilha de auditoria — a transação inteira de `receber_envio` desfez.
    assert not LoteDeRecepcao.objects.filter(escritorio=escritorio_a).exists()
    assert not ResultadoDoArquivo.objects.exists()
    assert not RegistroAuditoria.objects.filter(
        escritorio=escritorio_a, acao="fiscal.envio_recebido"
    ).exists()


def test_integrity_error_de_restricao_conhecida_continua_tratado_como_duplicado(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Controle negativo: a mudança do achado N1 não pode afetar o caminho
    # de `IntegrityError` já existente (duplicidade por unicidade) — ele
    # tem seu PRÓPRIO `except`, anterior ao de `DataError`, e continua
    # intacto.
    conteudo = xml_nfse(incluir_tomador=False)
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="n1.xml"
    )
    lote2 = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="n2.xml"
    )
    assert lote2.total_duplicados == 1
