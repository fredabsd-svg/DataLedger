"""DL-082, migração 0014: a reversão pelo `migrate` real não apaga dado do contador em silêncio.

- Marca de monofásico ou segmento de devolução em escrituração RASCUNHO ou EFETIVADA: a reversão
  recusa com a mensagem nomeada, e o banco fica como estava (as colunas continuam, com o valor).
- Só escriturações ESTORNADAS: a reversão passa (política da 0012, DL-083). A marca estornada
  continua na trilha de auditoria. Depois, a ida devolve as colunas ao head.

Os testes usam `transaction=True`, porque a reversão faz DDL. Cada um termina com o banco no head.
"""

import pytest
from django.core.management import call_command
from django.db import connection

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal.models import ItemNFe, NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl082 import nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

ULTIMA_ANTES = "0013_dl085_lote_escrituracao_nfe"
MENSAGEM = "Reversão da migração 0014 recusada (DL-082)"


def _colunas_do_item():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'fiscal_naturezaitemnfe'"
        )
        return {linha[0] for linha in cursor.fetchall()}


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Migracao DL082 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _revenda(escritorio, usuario, empresa, numero, *, efetivar: bool, marca: bool):
    """Uma revenda com natureza e, se pedido, a marca. Devolve a escrituração."""
    documento = nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    item_id = ItemNFe.objects.get(documento=documento).pk
    servico_nfe.definir_natureza(esc, NaturezaOperacaoNFe.REVENDA, [item_id], usuario=usuario)
    if marca:
        servico_nfe.definir_marca_monofasico(esc, [item_id], True, usuario=usuario)
    if efetivar:
        esc = servico_nfe.efetivar(esc, usuario=usuario)
    return esc


@pytest.mark.django_db(transaction=True)
def test_reversao_recusa_com_marca_em_rascunho_e_nao_muda_nada(
    escritorio_a, usuario_gestor_a, empresa
):
    _revenda(escritorio_a, usuario_gestor_a, empresa, 901, efetivar=False, marca=True)
    try:
        with pytest.raises(RuntimeError) as erro:
            call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
        assert MENSAGEM in str(erro.value)
        assert "1 item(ns) com marca de monofásico" in str(erro.value)
        assert "monofasico" in _colunas_do_item()
        assert NaturezaItemNFe.objects.get().monofasico is True
    finally:
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_reversao_recusa_com_marca_em_efetivada_e_nao_muda_nada(
    escritorio_a, usuario_gestor_a, empresa
):
    _revenda(escritorio_a, usuario_gestor_a, empresa, 902, efetivar=True, marca=True)
    try:
        with pytest.raises(RuntimeError) as erro:
            call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
        assert MENSAGEM in str(erro.value)
        assert "1 item(ns) com marca de monofásico" in str(erro.value)
        assert NaturezaItemNFe.objects.get().monofasico is True
    finally:
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_reversao_recusa_com_segmento_de_devolucao_em_rascunho(
    escritorio_a, usuario_gestor_a, empresa
):
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=903,
        itens=[{"cfop": "1202", "vprod": "500.00"}],
        devolucao=True,
    )
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    item_id = ItemNFe.objects.get(documento=documento).pk
    servico_nfe.definir_natureza(
        esc, NaturezaOperacaoNFe.DEVOLUCAO_VENDA, [item_id], usuario=usuario_gestor_a
    )
    servico_nfe.definir_segmento_devolucao(esc, [item_id], "revenda", usuario=usuario_gestor_a)
    try:
        with pytest.raises(RuntimeError) as erro:
            call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
        assert MENSAGEM in str(erro.value)
        assert "1 com segmento de devolução confirmado" in str(erro.value)
        assert "segmento_devolucao" in _colunas_do_item()
    finally:
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_reversao_passa_com_so_estornadas_e_a_marca_fica_na_trilha(
    escritorio_a, usuario_gestor_a, empresa
):
    esc = _revenda(escritorio_a, usuario_gestor_a, empresa, 904, efetivar=True, marca=True)
    servico_nfe.estornar(esc, "migração DL082: teste de reversão", usuario=usuario_gestor_a)
    try:
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)

        assert "monofasico" not in _colunas_do_item()
        assert "segmento_devolucao" not in _colunas_do_item()
        # A estornada é imutável, e a marca dela fica na trilha de auditoria (gravada a cada
        # definição).
        assert RegistroAuditoria.objects.filter(
            acao="escrituracao_nfe.monofasico_definido"
        ).exists()
    finally:
        call_command("migrate", verbosity=0)

    assert "monofasico" in _colunas_do_item()
    assert "segmento_devolucao" in _colunas_do_item()
