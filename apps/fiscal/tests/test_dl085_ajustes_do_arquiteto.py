"""DL-085: ajustes do arquiteto depois da reconferência (sem terceira rodada, §3.1).

- R1: a prévia pesada da confirmação é calculada FORA da trava da empresa.
- R2: a efetivação em lote não carrega o XML original das notas.
- R4: rascunho vazio entra no lote (N8) e a nova tentativa por deadlock (N13, N14, N42).
- R8: os textos da página pública, do cartão e do seletor não voltam a dizer que o fiscal só
  recebe NFS-e.
"""

from pathlib import Path

import psycopg
import pytest
from django.conf import settings
from django.db import OperationalError, connection
from django.test.utils import CaptureQueriesContext

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    LoteEscrituracaoNFe,
    LoteEscrituracaoNFeNota,
    VinculoNFeEmpresa,
)
from apps.fiscal.tests.suporte_dl085 import nfce, previa_lida, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

ANO, MES = 2026, 3


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-ajustes-dl085")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Ajustes DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _notas(escritorio, usuario, quantidade):
    for numero in range(1, quantidade + 1):
        nfce(escritorio, usuario, numero=numero)


@pytest.mark.django_db
def test_a_previa_da_confirmacao_e_calculada_fora_da_trava(
    escritorio_a, gestor, empresa, monkeypatch
):
    """R1: na primeira confirmação, `_calcular` roda antes de `travar_empresa`."""
    _notas(escritorio_a, gestor, 2)
    previa = previa_lida(empresa, ANO, MES)
    eventos = []
    calcular_original = lote._calcular
    travar_original = lote.receita_servico.travar_empresa

    def calcular(*args, **kwargs):
        eventos.append("calcular")
        return calcular_original(*args, **kwargs)

    def travar(*args, **kwargs):
        eventos.append("travar")
        return travar_original(*args, **kwargs)

    monkeypatch.setattr(lote, "_calcular", calcular)
    monkeypatch.setattr(lote.receita_servico, "travar_empresa", travar)
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)

    assert progresso.efetivadas_nesta_chamada == 1
    assert eventos.index("calcular") < eventos.index("travar")
    assert eventos.count("calcular") == 1


@pytest.mark.django_db
def test_a_efetivacao_em_lote_nao_carrega_o_xml_original(escritorio_a, gestor, empresa):
    """R2: nenhuma consulta da confirmação e da parte traz o `xml_original`."""
    _notas(escritorio_a, gestor, 6)
    previa = previa_lida(empresa, ANO, MES)
    with CaptureQueriesContext(connection) as contexto:
        progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=6)
    assert progresso.efetivadas_nesta_chamada == 6
    assert [q["sql"] for q in contexto.captured_queries if "xml_original" in q["sql"]] == []


@pytest.mark.django_db
def test_rascunho_vazio_entra_no_lote(escritorio_a, gestor, empresa):
    """R4 (N8): rascunho criado e ainda sem natureza não é escolha do contador: entra no lote."""
    _notas(escritorio_a, gestor, 2)
    vinculo = VinculoNFeEmpresa.objects.filter(empresa=empresa).order_by("pk").first()
    servico_nfe.ler_itens(vinculo.documento)
    servico_nfe.criar_rascunho(vinculo, usuario=gestor)
    previa = previa_lida(empresa, ANO, MES)
    assert not any(nota.vinculo_id == vinculo.pk for nota in previa.fora)
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=10)
    assert progresso.efetivadas_total == 2


@pytest.mark.django_db
def test_nova_tentativa_so_no_deadlock(escritorio_a, gestor, empresa, monkeypatch):
    """R4 (N13, N14, N42): deadlock repete até três vezes; outro erro de banco não repete."""
    _notas(escritorio_a, gestor, 2)
    previa = previa_lida(empresa, ANO, MES)
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    lote_obj = LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id)
    linha = LoteEscrituracaoNFeNota.objects.get(lote=lote_obj, estado="pendente")
    original = lote._processar_nota_uma_vez
    chamadas = []

    def deadlock_duas_vezes(*args, **kwargs):
        chamadas.append(1)
        if len(chamadas) <= 2:
            raise OperationalError("deadlock") from psycopg.errors.DeadlockDetected("x")
        return original(*args, **kwargs)

    monkeypatch.setattr(lote, "_processar_nota_uma_vez", deadlock_duas_vezes)
    assert lote._processar_nota(lote_obj, linha.pk, gestor, None, set())[0] == "efetivada"
    assert len(chamadas) == 3

    chamadas.clear()

    def deadlock_sempre(*args, **kwargs):
        chamadas.append(1)
        raise OperationalError("deadlock") from psycopg.errors.DeadlockDetected("x")

    monkeypatch.setattr(lote, "_processar_nota_uma_vez", deadlock_sempre)
    with pytest.raises(OperationalError):
        lote._processar_nota(lote_obj, linha.pk, gestor, None, set())
    assert len(chamadas) == 3

    chamadas.clear()

    def outro_erro(*args, **kwargs):
        chamadas.append(1)
        raise OperationalError("conexão caiu") from psycopg.errors.AdminShutdown("x")

    monkeypatch.setattr(lote, "_processar_nota_uma_vez", outro_erro)
    with pytest.raises(OperationalError):
        lote._processar_nota(lote_obj, linha.pk, gestor, None, set())
    assert len(chamadas) == 1


_SUPERFICIES = [
    "templates/registration/landing.html",
    "templates/registration/public_base.html",
    "templates/core/module_home.html",
    "apps/core/module_homes.py",
    "apps/tenancy/views.py",
]
_FRASES_DESMENTIDAS = [
    "Recepção e consulta de NFS-e nacional",
    "recepção e consulta de NFS-e",
    "Recepção e conferência de NFS-e nacional",
    "Escrituração e apuração fiscal completas estão planejadas",
    "Receber NFS-e",
    "só recepção/consulta de NFS-e",
]


@pytest.mark.parametrize("superficie", _SUPERFICIES)
def test_textos_da_interface_nao_voltam_a_dizer_que_o_fiscal_so_recebe_nfse(superficie):
    """R8: as superfícies que o Fred e os visitantes leem não repetem a afirmação desmentida."""
    texto = (Path(settings.BASE_DIR) / superficie).read_text(encoding="utf-8")
    for frase in _FRASES_DESMENTIDAS:
        assert frase not in texto, f"{superficie}: {frase!r}"
