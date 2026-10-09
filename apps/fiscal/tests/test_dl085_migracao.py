"""DL-085 (frente A), migração 0013: aditiva e reversível, pelo `migrate` do Django.

Ida, volta e ida. A reversão apaga só o REGISTRO dos lotes (duas tabelas novas). As escriturações
individuais e a trilha de auditoria ficam como estão. Também confere a trava do banco: um lote em
andamento por empresa e mês, no máximo.
"""

from datetime import date

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EscrituracaoNFe, LoteEscrituracaoNFe, NaturezaItemNFe
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import nfce, previa_lida, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

ULTIMA_ANTES = "0012_dl083_combustivel_revenda"
TABELAS = ("fiscal_loteescrituracaonfe", "fiscal_loteescrituracaonfenota")


def _tabela_existe(nome: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [nome])
        return cursor.fetchone()[0]


def _escrituracao_individual(escritorio, usuario, empresa):
    """Uma escrituração efetivada pelo caminho individual, para provar que a reversão não a toca."""
    documento = nfce(escritorio, usuario, numero=900, valor="55.00")
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza="combustivel")
    return servico.efetivar(esc, usuario=usuario)


def test_migracao_0013_vai_volta_e_vai_sem_tocar_nas_escrituracoes(escritorio_a):
    usuario = usuario_gestor(escritorio_a, "gestor-migracao-dl085")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Migracao DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    efetivada = _escrituracao_individual(escritorio_a, usuario, empresa)
    assert all(_tabela_existe(t) for t in TABELAS)

    try:
        call_command("migrate", "fiscal", ULTIMA_ANTES, verbosity=0)
        assert not any(_tabela_existe(t) for t in TABELAS)
        efetivada.refresh_from_db()
        assert efetivada.estado == "efetivada"
        assert EscrituracaoNFe.objects.filter(pk=efetivada.pk).exists()
    finally:
        # Ida até o head de TODAS as apps, também se uma asserção acima falhar (DL-082): a volta
        # só da fiscal deixava o banco parado em 0012 para os testes seguintes.
        call_command("migrate", verbosity=0)
    assert all(_tabela_existe(t) for t in TABELAS)
    assert not LoteEscrituracaoNFe.objects.exists()
    previa = previa_lida(empresa, 2026, 3)
    assert previa.grupos == () and previa.ja_efetivadas == 1


def test_banco_recusa_dois_lotes_em_andamento_no_mesmo_mes(escritorio_a):
    """Trava do banco, a segunda defesa depois do `select_for_update` do serviço: um lote em
    andamento por empresa e mês, no máximo. Concluído com data não conta.
    Sem data, a CHECK recusa."""
    usuario = usuario_gestor(escritorio_a, "gestor-trava-dl085")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Trava DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )

    def criar(estado="em_andamento", concluido_em=None):
        return LoteEscrituracaoNFe.objects.create(
            escritorio=escritorio_a,
            empresa=empresa,
            competencia=date(2026, 3, 1),
            assinatura="a" * 64,
            estado=estado,
            concluido_em=concluido_em,
            criado_por=usuario,
        )

    criar()
    with pytest.raises(IntegrityError), transaction.atomic():
        criar()
    criar(estado="concluido", concluido_em=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        criar(estado="concluido")
