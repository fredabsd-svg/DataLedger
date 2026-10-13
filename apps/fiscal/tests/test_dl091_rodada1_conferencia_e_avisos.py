"""DL-091, correção da rodada 1: conferência de saída sem compras, defesas da receita e da
conferência de entradas, regime pela data de entrada e avisos de outro estado.

- T7 (A6, N13/N14): compras não entram nos números da conferência de SAÍDA do mês.
- T11 (A6, M04/M13): defesa em profundidade. Compra com natureza de receita gravada no banco não
  entra na receita; totais da conferência de entradas não aceitam escrituração de outra empresa.
- T8 (A7, N19): o regime que vale para o aviso é o da DATA DE ENTRADA, não o de hoje.
- T9 (A7, M17/N10): `idDest` 2 sozinho faz o aviso de Simples quando a UF da matriz não está
  cadastrada; CFOP 6 com emitente da UF da empresa gera aviso de UF incoerente.

Dados sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, seção "Decisões para a correção".
"""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import conferencia_entradas as conferencia_entradas
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import receita as receita_servico
from apps.fiscal.itens_nfe import ler_itens
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    NaturezaItemNFe,
    TipoEscrituracaoNFe,
)
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.test_dl091_entradas import (
    _confirmar,
    _matriz,
    _nota,
    _rascunho,
)
from apps.fiscal.tests.test_dl091_rodada1_api import _venda
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A, chave_nfe

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Conferência rodada 1 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _regime(empresa, regime, inicio, fim=None):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=regime, vigencia_inicio=inicio, vigencia_fim=fim
    )


def _numeros(conferencia):
    return (
        conferencia.recebidas,
        conferencia.escrituradas,
        conferencia.pendentes,
        conferencia.canceladas,
        conferencia.itens_sem_sugestao,
        conferencia.nao_elegiveis,
    )


# ---------------------------------------------------------------------------
# T7: a conferência de SAÍDA do mês não conta compra
# ---------------------------------------------------------------------------


def test_compras_do_mes_nao_mudam_os_numeros_da_conferencia_de_saida(
    escritorio_a, usuario_gestor_a, empresa
):
    _venda(escritorio_a, usuario_gestor_a, empresa, numero="5001")
    _venda(escritorio_a, usuario_gestor_a, empresa, numero="5002", cfop="5949")
    base = servico.conferencia_do_mes(empresa, 2026, 3)
    assert _numeros(base)[0] == 2 and base.itens_sem_sugestao == 1, "a saída precisa existir"

    _nota(escritorio_a, usuario_gestor_a, empresa, numero="5101", cfop="5102")
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="5102", cfop="5949")
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa, numero="5103")
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)

    depois = servico.conferencia_do_mes(empresa, 2026, 3)

    assert _numeros(depois) == _numeros(base)


# ---------------------------------------------------------------------------
# T11: defesas da receita e da conferência de entradas
# ---------------------------------------------------------------------------


def test_compra_com_natureza_de_receita_gravada_no_banco_nao_entra_na_receita(
    escritorio_a, usuario_gestor_a, empresa
):
    """Defesa em profundidade. O serviço nunca grava natureza de receita numa compra, mas o banco
    não cruza tipo e natureza. Por isso a receita precisa excluir a ENTRADA por si só.

    O cenário é montado como o serviço o faria: a natureza muda no rascunho (o banco só deixa
    mudar em rascunho) e a escrituração vai a efetivada com o mesmo UPDATE do `efetivar`.
    """
    _regime(empresa, RegimeTributario.LUCRO_PRESUMIDO, date(2026, 1, 1))
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa, numero="5301")
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=N.REVENDA, cfop_entrada="")
    EscrituracaoNFe.objects.filter(pk=esc.pk).update(
        estado=EstadoEscrituracao.EFETIVADA,
        efetivada_em=timezone.now(),
        efetivada_por=usuario_gestor_a,
        competencia=date(2026, 3, 1),
        data_emissao=date(2026, 3, 15),
        valor_nf=Decimal("100.00"),
        soma_itens=Decimal("100.00"),
        receita_bruta=Decimal("0.00"),
        devolucao=Decimal("0.00"),
    )

    linhas = receita_servico.linhas_nfe_do_periodo(empresa, (2026, 3), (2026, 3))

    assert linhas == []


def test_totais_da_conferencia_de_entradas_ignoram_escrituracao_de_outra_empresa(
    escritorio_a, usuario_gestor_a, empresa
):
    """Defesa em profundidade: a conferência recebe escriturações de OUTRA empresa e não as soma.
    Os itens que ela lê são filtrados pela empresa, não só pelas ids que recebe."""
    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra rodada 1 Ltda", cnpj="12345678000195"
    )
    esc_outra = _rascunho(escritorio_a, usuario_gestor_a, outra, numero="5401")
    _confirmar(esc_outra, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc_outra, usuario=usuario_gestor_a)
    efetivadas_de_outra = [
        nota
        for nota in servico.notas_do_mes(outra, 2026, 3)
        if nota.tipo == TipoEscrituracaoNFe.ENTRADA and nota.situacao == servico.SITUACAO_EFETIVADA
    ]
    assert len(efetivadas_de_outra) == 1

    resultado = conferencia_entradas.ConferenciaDeEntradas(ano=2026, mes=3)
    conferencia_entradas._preencher_totais(empresa, resultado, efetivadas_de_outra)

    assert resultado.por_natureza == ()
    assert resultado.por_cfop_de_entrada == ()
    assert resultado.por_marca == ()
    assert resultado.credito_destacado_elegivel == Decimal("0.00")


# ---------------------------------------------------------------------------
# T8: o regime do aviso é o da data de entrada
# ---------------------------------------------------------------------------


def test_aviso_de_outro_estado_segue_a_data_de_entrada_e_nao_o_regime_de_hoje(
    escritorio_a, usuario_gestor_a, empresa
):
    """Simples até 30/06/2026 e Presumido desde 01/07/2026. Compra de março recebe o aviso do
    Simples; a mesma compra com data de entrada em agosto não recebe. Hoje é outubro (Presumido), e
    por isso a regra que lê "hoje" erraria o caso de março."""
    _matriz(empresa, escritorio_a, "TO")
    _regime(empresa, RegimeTributario.SIMPLES_NACIONAL, date(2026, 1, 1), date(2026, 6, 30))
    _regime(empresa, RegimeTributario.LUCRO_PRESUMIDO, date(2026, 7, 1))
    compra = _nota(escritorio_a, usuario_gestor_a, empresa, crt="1", icms=xml.icms(csosn="102"))
    esc = servico.criar_rascunho(
        vinculo(compra, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 3, 15)
    )
    item = compra.itens.get(n_item=1)

    marco = entradas.previa_do_item(esc, item, N.ENTRADA_COMERCIALIZACAO, "1102")
    assert entradas.AVISO_SIMPLES_OUTRO_ESTADO in marco["avisos"]

    esc = entradas.definir_data_de_entrada(esc, date(2026, 8, 15), usuario=usuario_gestor_a)
    agosto = entradas.previa_do_item(esc, item, N.ENTRADA_COMERCIALIZACAO, "1102")
    assert entradas.AVISO_SIMPLES_OUTRO_ESTADO not in agosto["avisos"]


# ---------------------------------------------------------------------------
# T9: idDest 2 sozinho e UF incoerente
# ---------------------------------------------------------------------------


def _nota_com_id_dest(escritorio, usuario, empresa, *, numero, id_dest, cuf="35", cfop="5102"):
    """Compra de CRT 1 (Simples) do emitente, com o `idDest` escolhido. Dados sintéticos."""
    det = xml.det(1, cfop=cfop, vprod="100.00", ncm="22030000", icms_xml=xml.icms(csosn="102"))
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[det],
            vnf="100.00",
            totais={"vProd": "100.00"},
            chave=chave_nfe(cuf=cuf, emitente=CNPJ_EMITENTE_A, modelo="55", numero=numero),
            numero=numero,
            id_dest=id_dest,
            emitente=("CNPJ", CNPJ_EMITENTE_A),
            destinatario=("CNPJ", empresa.cnpj),
            crt="1",
        ),
    )
    ler_itens(documento)
    return documento


def test_id_dest_2_sozinho_gera_aviso_de_simples_quando_nao_ha_uf_da_matriz(
    escritorio_a, usuario_gestor_a, empresa
):
    """Sem matriz com UF, só o `idDest` 2 diz que a compra é de outro estado. O aviso sai, e o aviso
    de UF não cadastrada também. Controle: `idDest` 1 não gera o aviso de outro estado."""
    _regime(empresa, RegimeTributario.SIMPLES_NACIONAL, date(2026, 1, 1))
    interestadual = _nota_com_id_dest(
        escritorio_a, usuario_gestor_a, empresa, numero="9101", id_dest="2"
    )
    interna = _nota_com_id_dest(escritorio_a, usuario_gestor_a, empresa, numero="9102", id_dest="1")
    contexto = entradas.contexto_da_entrada(empresa, date(2026, 3, 15))

    avisos_interestadual = entradas.avisos_da_entrada(
        interestadual,
        interestadual.itens.get(n_item=1),
        N.ENTRADA_COMERCIALIZACAO,
        contexto,
    )
    avisos_interna = entradas.avisos_da_entrada(
        interna, interna.itens.get(n_item=1), N.ENTRADA_COMERCIALIZACAO, contexto
    )

    assert entradas.AVISO_SIMPLES_OUTRO_ESTADO in avisos_interestadual
    assert entradas.AVISO_UF_DA_EMPRESA_NAO_CADASTRADA in avisos_interestadual
    assert entradas.AVISO_SIMPLES_OUTRO_ESTADO not in avisos_interna


def test_cfop_6_com_emitente_da_uf_da_empresa_gera_aviso_de_uf_incoerente(
    escritorio_a, usuario_gestor_a, empresa
):
    """CFOP 6 (interestadual) com emitente da mesma UF da empresa é incoerente. Controle: CFOP 6 com
    emitente de outra UF (SP, sendo a empresa do TO) é coerente."""
    _matriz(empresa, escritorio_a, "TO")
    contexto = entradas.contexto_da_entrada(empresa, date(2026, 3, 15))
    mesma_uf = _nota(escritorio_a, usuario_gestor_a, empresa, cuf="17", cfop="6102", numero="9201")
    outra_uf = _nota(escritorio_a, usuario_gestor_a, empresa, cuf="35", cfop="6102", numero="9202")

    avisos_mesma = entradas.avisos_da_entrada(
        mesma_uf, mesma_uf.itens.get(n_item=1), N.ENTRADA_COMERCIALIZACAO, contexto
    )
    avisos_outra = entradas.avisos_da_entrada(
        outra_uf, outra_uf.itens.get(n_item=1), N.ENTRADA_COMERCIALIZACAO, contexto
    )

    assert entradas.AVISO_UF_INCOERENTE in avisos_mesma
    assert entradas.AVISO_UF_INCOERENTE not in avisos_outra
