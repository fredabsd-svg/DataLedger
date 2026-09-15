"""Testes de `apps.core.restricoes` (BL-144, achado R5-5 da auditoria
DL-017 rodada 5).

Unitários, sem banco: constrói um `IntegrityError` sintético com o mesmo
formato de diagnóstico que o psycopg anexa (`exc.__cause__.diag.
constraint_name`), no mesmo molde do teste equivalente em
`apps.empresas.tests.test_api` para `mensagem_se_cnpj_duplicado`. Os
testes COM banco real (a constraint de verdade sendo violada) vivem em
`apps.contabilidade.tests.test_bl144_codigo_conta_duplicado` e
`apps.empresas.tests.test_bl144_matriz_duplicada` — este arquivo prova só
a lógica de tradução, isolada.
"""

import pytest
from django.db import IntegrityError

from apps.core.restricoes import RestricaoViolada, restricao_como_400


class _DiagnosticoFalso:
    def __init__(self, constraint_name):
        self.constraint_name = constraint_name


def _integrity_error_de(nome_constraint):
    causa = Exception("violação simulada")
    causa.diag = _DiagnosticoFalso(nome_constraint)
    erro = IntegrityError("duplicate key value violates unique constraint")
    erro.__cause__ = causa
    return erro


def test_restricao_como_400_traduz_a_constraint_mapeada():
    with pytest.raises(RestricaoViolada, match="Já existe uma conta"):
        with restricao_como_400(
            {"codigo_unico_por_empresa": "Já existe uma conta com este código."}
        ):
            raise _integrity_error_de("codigo_unico_por_empresa")


def test_restricao_como_400_deixa_subir_constraint_nao_mapeada():
    """A mesma cautela de `mensagem_se_cnpj_duplicado`: só a(s) constraint(s)
    nomeadas no mapa são traduzidas. Qualquer outra `IntegrityError` sobe
    SEM tradução — nunca mascarar defeito de sistema como erro de cliente
    (decisão revista depois da DL-007)."""
    with pytest.raises(IntegrityError):
        with restricao_como_400({"codigo_unico_por_empresa": "mensagem"}):
            raise _integrity_error_de("uma_constraint_qualquer_nao_mapeada")


def test_restricao_como_400_deixa_subir_integrity_error_sem_diagnostico():
    """`exc.__cause__` pode não existir (driver diferente do psycopg, ou
    erro sem causa encadeada) — `getattr(..., None)` em cascata não pode
    levantar `AttributeError` por conta própria."""
    with pytest.raises(IntegrityError):
        with restricao_como_400({"codigo_unico_por_empresa": "mensagem"}):
            raise IntegrityError("sem causa nenhuma")


def test_restricao_como_400_nao_interfere_quando_nao_ha_erro():
    with restricao_como_400({"codigo_unico_por_empresa": "mensagem"}):
        resultado = 1 + 1
    assert resultado == 2
