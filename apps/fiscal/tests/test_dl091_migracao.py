"""DL-091 (frente A1), migração aditiva e reversível (0021). A reversão recusa, sem alterar nada,
enquanto houver escrituração de entrada ou natureza de entrada / devolução de compra gravada.

As guardas são chamadas com o registro real de apps. A ida, a volta e a ida foram executadas com
`manage.py migrate` (saída no relatório da entrega); aqui ficam as guardas e a ordem das operações.
"""

import importlib
from types import SimpleNamespace

import pytest
from django.apps import apps as registro_de_apps
from django.db import connection

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.itens_nfe import ler_itens
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe, TipoEscrituracaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A, chave_nfe

pytestmark = pytest.mark.django_db

# As guardas de baixo leem `schema_editor.connection.vendor` e executam o passo de checagens da
# 0014 (`SET CONSTRAINTS`, sem alterar esquema). O editor mínimo basta para isso.
_EDITOR = SimpleNamespace(
    connection=connection,
    execute=lambda sql, params=None: connection.cursor().execute(sql),
)

M21 = importlib.import_module("apps.fiscal.migrations.0021_dl091_entrada_nfe")


def test_guarda_da_0021_passa_sem_entrada(escritorio_a):
    """Sem escrituração de entrada nem natureza nova, a reversão segue (a guarda não recusa)."""
    M21._recusar_reversao_com_entrada(registro_de_apps, _EDITOR)


def test_guarda_da_0021_recusa_com_escrituracao_de_entrada(escritorio_a, usuario_gestor_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Migração DL091 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )
    icms = xml.icms(
        cst="00", filhos="<modBC>3</modBC><vBC>100.00</vBC><pICMS>12.00</pICMS><vICMS>12.00</vICMS>"
    )
    documento = receber(
        escritorio_a,
        usuario_gestor_a,
        xml.nfe(
            dets=[xml.det(1, cfop="6102", vprod="100.00", icms_xml=icms)],
            vnf="100.00",
            totais={"vProd": "100.00"},
            chave=chave_nfe(cuf="35", emitente=CNPJ_EMITENTE_A, modelo="55", numero="901"),
            numero="901",
            emitente=("CNPJ", CNPJ_EMITENTE_A),
            destinatario=("CNPJ", CNPJ_DESTINATARIO_A),
            crt="3",
        ),
    )
    ler_itens(documento)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    with pytest.raises(RuntimeError, match="escrituração\\(ões\\) de entrada"):
        M21._recusar_reversao_com_entrada(registro_de_apps, _EDITOR)


def test_guarda_da_0021_recusa_com_natureza_de_entrada_gravada(escritorio_a, usuario_gestor_a):
    """Natureza de entrada gravada em qualquer escrituração também recusa a reversão."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Migração natureza DL091 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
    icms = xml.icms(csosn="102")
    documento = receber(
        escritorio_a,
        usuario_gestor_a,
        xml.nfe(
            dets=[xml.det(1, cfop="5102", vprod="50.00", icms_xml=icms)],
            vnf="50.00",
            totais={"vProd": "50.00"},
            chave=chave_nfe(cuf="35", emitente=CNPJ_DESTINATARIO_A, modelo="55", numero="902"),
            numero="902",
            emitente=("CNPJ", CNPJ_DESTINATARIO_A),
            destinatario=("CNPJ", CNPJ_EMITENTE_A),
            crt="3",
        ),
    )
    ler_itens(documento)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_COMPRA
    )
    with pytest.raises(RuntimeError, match="natureza\\(s\\) de entrada"):
        M21._recusar_reversao_com_entrada(registro_de_apps, _EDITOR)


def test_a_guarda_da_0021_e_a_ultima_operacao_e_roda_primeiro_na_reversao():
    operacoes = M21.Migration.operations
    assert operacoes[-1].reverse_code is M21._recusar_reversao_com_entrada
    assert operacoes[-2].reverse_code is M21._desfazer_checks_e_gatilho


def test_a_guarda_da_0021_encadeia_todas_as_guardas_de_baixo_antes_de_mexer_no_esquema():
    """O Django reverte cada migração em transação própria: a 0021 precisa recusar ANTES de
    mexer no esquema, então chama as guardas de TODAS as migrações de baixo que recusam.
    Cada entrada da lista tem de existir: uma guarda ausente quebraria a reversão só na hora
    dela."""
    for modulo, nome in M21._GUARDAS_DE_BAIXO:
        guarda = getattr(importlib.import_module(f"apps.fiscal.migrations.{modulo}"), nome)
        assert callable(guarda), (modulo, nome)
    nomes = [modulo.split("_")[0] for modulo, _ in M21._GUARDAS_DE_BAIXO]
    assert nomes == ["0020", "0019", "0018", "0017", "0016", "0015", "0014", "0012"]


def test_tipo_entrada_e_natureza_de_entrada_estao_no_catalogo():
    assert TipoEscrituracaoNFe.ENTRADA == "entrada"
    assert NaturezaOperacaoNFe.DEVOLUCAO_COMPRA == "devolucao_compra"
