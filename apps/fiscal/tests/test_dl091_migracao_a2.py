"""DL-091 (frente A2), migração aditiva e reversível (0022): a reversão recusa, sem alterar nada,
enquanto houver regra de entrada, ou regra com CRT, UF ou CFOP de entrada gravado.

As guardas são chamadas com o registro real de apps, como em `test_dl091_migracao`. A ida, a volta e
a ida com `manage.py migrate` estão no relatório da entrega (saída real).
"""

from datetime import date
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps as registro_de_apps
from django.db import connection

from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.models import RegraClassificacaoNFe, TipoEscrituracaoNFe

M22 = import_module("apps.fiscal.migrations.0022_dl091_regra_de_entrada")
M19 = import_module("apps.fiscal.migrations.0019_dl087_regra_de_classificacao_nfe")

pytestmark = pytest.mark.django_db

# As guardas leem `schema_editor.connection.vendor`, e a da 0021 executa checagens SQL. Um editor
# mínimo basta, como em `test_dl091_migracao`.
_EDITOR = SimpleNamespace(
    connection=connection,
    execute=lambda sql, params=None: connection.cursor().execute(sql),
)


def _regra_de_entrada(escritorio, usuario, **campos):
    base = {
        "escritorio": escritorio,
        "tipo": TipoEscrituracaoNFe.ENTRADA,
        "cfop": "5102",
        "natureza": N.ENTRADA_COMERCIALIZACAO,
        "vigencia_inicio": date(2026, 1, 1),
        "criada_por": usuario,
    }
    base.update(campos)
    return RegraClassificacaoNFe.objects.create(**base)


def test_guarda_da_0022_passa_sem_regra_de_entrada(escritorio_a):
    M22._recusar_reversao_com_regra_de_entrada(registro_de_apps, _EDITOR)


def test_guarda_da_0022_recusa_com_regra_de_entrada(escritorio_a, usuario_gestor_a):
    _regra_de_entrada(escritorio_a, usuario_gestor_a)
    with pytest.raises(RuntimeError, match="regra\\(s\\) de classificação de entrada"):
        M22._recusar_reversao_com_regra_de_entrada(registro_de_apps, _EDITOR)


def test_guarda_da_0022_recusa_com_criterio_de_fornecedor_gravado(escritorio_a, usuario_gestor_a):
    _regra_de_entrada(escritorio_a, usuario_gestor_a, crt_emitente="1")
    with pytest.raises(RuntimeError, match="CRT, UF ou CFOP de entrada"):
        M22._recusar_reversao_com_regra_de_entrada(registro_de_apps, _EDITOR)


def test_guarda_da_0022_encadeia_a_guarda_da_0019_e_recusa_antes_de_qualquer_alteracao(
    escritorio_a, usuario_gestor_a
):
    """Regra de SAÍDA gravada: a 0022 não tem o que recusar, mas a guarda da 0019 (que a 0021
    encadeia) recusa. Sem o encadeamento, a 0022 desfaria o esquema e só depois a 0019 recusaria."""
    RegraClassificacaoNFe.objects.create(
        escritorio=escritorio_a,
        tipo="saida_propria",
        cfop="5102",
        natureza=N.REVENDA,
        vigencia_inicio=date(2026, 1, 1),
        criada_por=usuario_gestor_a,
    )
    with pytest.raises(RuntimeError, match="1 regra"):
        M22._recusar_reversao_com_regra_de_entrada(registro_de_apps, _EDITOR)
    # A guarda da 0019 é a mesma que roda sozinha.
    with pytest.raises(RuntimeError, match="1 regra"):
        M19._recusar_reversao_com_regras(registro_de_apps, _EDITOR)


def test_a_guarda_da_0022_e_a_ultima_operacao_e_roda_primeiro_na_reversao():
    from django.db.migrations import RunPython

    operacoes = M22.Migration.operations
    assert isinstance(operacoes[-1], RunPython)
    assert operacoes[-1].reverse_code is M22._recusar_reversao_com_regra_de_entrada
    assert operacoes[0].code is M22._trocar_gatilho
    assert operacoes[0].reverse_code is M22._restaurar_gatilho
