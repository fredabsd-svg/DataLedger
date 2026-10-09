"""DL-085 (frente A), critério 3: a efetivação em lote é a efetivação individual, nota a nota.

Duas empresas IDÊNTICAS do mesmo escritório recebem as mesmas notas sintéticas (só o CNPJ emitente
muda). A empresa A é escriturada pelo LOTE, em partes de 2 notas. A empresa B é escriturada NOTA A
NOTA, pelas funções da escrituração individual (criar_rascunho, definir_natureza, efetivar), com as
naturezas que a prévia sugere. O teste compara, nota a nota: estado, valores, receita, naturezas e a
trilha de auditoria (ator, ação e detalhes; ids de item trocados por nItem, que é igual nas duas).
"""

from collections import defaultdict
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import DocumentoNFe, EscrituracaoNFe, ItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import (
    CNPJ_SEGUNDA_EMPRESA,
    confirmar_tudo,
    nfce,
    previa_lida,
    usuario_gestor,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a)


def _roteiro(escritorio, usuario, emitente):
    """Sete notas que cobrem os caminhos: combustível, lubrificante (sugestão de revenda, com
    aviso),
    revenda, item fora do total com frete (rateado para a venda) e combustível de valor redondo."""
    nfce(escritorio, usuario, numero=1, emitente=emitente, valor="100.00")
    nfce(escritorio, usuario, numero=2, emitente=emitente, valor="250.50")
    nfce(escritorio, usuario, numero=3, emitente=emitente, valor="80.00", cfop="5102", csosn="102")
    nfce(
        escritorio,
        usuario,
        numero=4,
        emitente=emitente,
        dets=[
            xml.det(1, cfop="5102", vprod="40.00", icms_xml=xml.icms(csosn="102")),
            xml.det(2, cfop="5102", vprod="50.00", ind_tot="0", vfrete="10.00"),
        ],
        vnf="50.00",
    )
    nfce(
        escritorio,
        usuario,
        numero=5,
        emitente=emitente,
        dets=[
            xml.det(
                1,
                cfop="5656",
                vprod="30.00",
                ncm="27101931",  # óleo lubrificante: fora do 1,6% (HI-139), sugere revenda
                icms_xml=xml.icms(csosn="500"),
            )
        ],
        vnf="30.00",
    )
    nfce(escritorio, usuario, numero=6, emitente=emitente, valor="12.34")
    nfce(escritorio, usuario, numero=7, emitente=emitente, valor="7.00", cfop="5102", csosn="102")


def _empresas(escritorio):
    a = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A", cnpj=CNPJ_EMITENTE_A
    )
    b = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa B", cnpj=CNPJ_SEGUNDA_EMPRESA
    )
    return a, b


def _individual(empresa, usuario, previa):
    """Escrituração nota a nota, pelas funções individuais, com as naturezas que a prévia sugere."""
    for grupo in previa.grupos:
        for nota in grupo.notas:
            documento = DocumentoNFe.objects.get(pk=nota.documento_id)
            escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
            por_natureza = defaultdict(list)
            for item in nota.itens:
                por_natureza[item.natureza_sugerida].append(item.item_id)
            for natureza in sorted(por_natureza):
                servico.definir_natureza(
                    escrituracao, natureza, por_natureza[natureza], usuario=usuario
                )
            servico.efetivar(escrituracao, usuario=usuario)


def _resultado(empresa):
    """Por número da nota: estado, valores, receita e a natureza de cada item (pelo nItem)."""
    saida = {}
    escrituracoes = EscrituracaoNFe.objects.filter(empresa=empresa).select_related(
        "vinculo__documento"
    )
    for escrituracao in escrituracoes:
        documento = escrituracao.vinculo.documento
        naturezas = {
            item.n_item: escrituracao.naturezas_dos_itens.get(item=item).natureza
            for item in ItemNFe.objects.filter(documento=documento)
        }
        saida[documento.numero] = {
            "estado": escrituracao.estado,
            "tipo": escrituracao.tipo,
            "competencia": escrituracao.competencia,
            "valor_nf": escrituracao.valor_nf,
            "soma_itens": escrituracao.soma_itens,
            "receita_bruta": escrituracao.receita_bruta,
            "devolucao": escrituracao.devolucao,
            "naturezas": naturezas,
        }
    return saida


def _normaliza(valor, n_item_por_id):
    """Tira o que é de cada empresa (vínculo e ids) e troca o id de item pelo nItem."""
    if isinstance(valor, dict):
        saida = {}
        for chave, conteudo in valor.items():
            if chave in ("vinculo_id", "id"):
                continue
            if chave.isdigit() and int(chave) in n_item_por_id:
                chave = str(n_item_por_id[int(chave)])
            saida[chave] = _normaliza(conteudo, n_item_por_id)
        return saida
    if isinstance(valor, list):
        return [_normaliza(v, n_item_por_id) for v in valor]
    return valor


def _trilha(empresa, n_item_por_id):
    """Por número da nota: a sequência (ação, ator, detalhes normalizados) da escrituração."""
    saida = {}
    for escrituracao in EscrituracaoNFe.objects.filter(empresa=empresa).select_related(
        "vinculo__documento"
    ):
        registros = RegistroAuditoria.objects.filter(
            objeto_tipo="EscrituracaoNFe", objeto_id=str(escrituracao.pk)
        ).order_by("pk")
        saida[escrituracao.vinculo.documento.numero] = [
            (r.acao, r.usuario_id, _normaliza(r.detalhes, n_item_por_id)) for r in registros
        ]
    return saida


def test_lote_e_individual_produzem_o_mesmo_resultado_e_a_mesma_trilha_nota_a_nota(
    escritorio_a, gestor
):
    """Critério 3. Mesma receita, mesmas naturezas e mesma trilha por nota, nas 7 notas."""
    empresa_a, empresa_b = _empresas(escritorio_a)
    _roteiro(escritorio_a, gestor, CNPJ_EMITENTE_A)
    _roteiro(escritorio_a, gestor, CNPJ_SEGUNDA_EMPRESA)

    previa_a = previa_lida(empresa_a, 2026, 3)
    previa_b = previa_lida(empresa_b, 2026, 3)
    assert previa_a.fora == () and previa_b.fora == ()

    confirmar_tudo(empresa_a, gestor, 2026, 3, previa_a, limite=2)
    _individual(empresa_b, gestor, previa_b)

    resultado_a = _resultado(empresa_a)
    assert len(resultado_a) == 7
    assert resultado_a == _resultado(empresa_b)
    n_item_por_id = dict(ItemNFe.objects.values_list("pk", "n_item"))
    assert _trilha(empresa_a, n_item_por_id) == _trilha(empresa_b, n_item_por_id)


def test_nota_com_frete_tem_receita_escrita_a_mao_nas_duas_empresas(escritorio_a, gestor):
    """A nota 4 tem um item de 40,00 (receita) e um item fora do total de 50,00 com frete de
    10,00. O
    frete vai para a venda da mesma nota (HI-138): a receita é 40,00 + 10,00 = 50,00, igual ao vNF.
    Nas duas empresas, sem centavo a mais nem a menos."""
    empresa_a, empresa_b = _empresas(escritorio_a)
    _roteiro(escritorio_a, gestor, CNPJ_EMITENTE_A)
    _roteiro(escritorio_a, gestor, CNPJ_SEGUNDA_EMPRESA)
    confirmar_tudo(empresa_a, gestor, 2026, 3, previa_lida(empresa_a, 2026, 3), limite=3)
    _individual(empresa_b, gestor, previa_lida(empresa_b, 2026, 3))

    for empresa in (empresa_a, empresa_b):
        nota4 = EscrituracaoNFe.objects.get(empresa=empresa, vinculo__documento__numero="4")
        assert nota4.receita_bruta == Decimal("50.00")
        assert nota4.valor_nf == Decimal("50.00")
        assert nota4.soma_itens == Decimal("50.00")
