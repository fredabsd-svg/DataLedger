"""Apoio dos testes da DL-074 (frente A): fábricas de dados SINTÉTICOS.

Não contém casos de teste. Os números dos casos de referência ficam escritos à mão
nos próprios testes (`test_dl074_rbt12_referencia.py`), nunca calculados aqui.

Todo CNPJ, nome e número vem de `xml_sinteticos.py` (dados fictícios).
"""

from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import receita as servico_receita
from apps.fiscal import services as servicos_recepcao
from apps.fiscal.escrituracao import efetivar_escrituracao
from apps.fiscal.models import (
    DocumentoFiscal,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse

NATUREZA_INTERNA = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
NATUREZA_EXPORTACAO = NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO
ORIGEM_OUTRAS = "outras_receitas_atividade"


def fixar_inicio_de_uso(empresa: Empresa, ano: int, mes: int) -> None:
    """Fixa `criado_em` (início de uso do sistema) no dia 1 do mês, ao meio-dia de Brasília."""
    quando = timezone.make_aware(datetime(ano, mes, 1, 12, 0), timezone.get_current_timezone())
    Empresa.objects.filter(pk=empresa.pk).update(criado_em=quando)
    empresa.refresh_from_db()


def preparar_simples(empresa: Empresa, *, abertura: date | None, inicio_simples: date) -> Empresa:
    """Data de abertura no CNPJ e Simples Nacional (aberto) a partir de `inicio_simples`."""
    Empresa.objects.filter(pk=empresa.pk).update(data_abertura_cnpj=abertura)
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio=inicio_simples,
    )
    empresa.refresh_from_db()
    return empresa


def escriturar(
    escritorio, empresa, usuario, *, sufixo: int, competencia, valor, natureza=NATUREZA_INTERNA
):
    """NFS-e sintética em que `empresa` é PRESTADORA, recebida e EFETIVADA com `natureza`.

    `competencia` é (ano, mês): vira `dCompet` (o mês da escrituração, HI-57).
    `valor` é o `vServ`, em reais. Devolve a escrituração efetivada.
    """
    ano, mes = competencia
    identificador = identificador_nfse(sufixo)
    servicos_recepcao.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(
            identificador=identificador,
            numero=str(sufixo),
            dh_emi=f"{ano}-{mes:02d}-10T10:00:00-03:00",
            d_compet=f"{ano}-{mes:02d}-10",
            v_serv=f"{Decimal(valor):.2f}",
            v_liq=f"{Decimal(valor):.2f}",
        ),
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)
    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )
    return efetivar_escrituracao(vinculo, natureza, usuario)


def informar_e_confirmar(empresa, usuario, ano: int, mes: int, valor, mercado="interno"):
    """Receita informada de origem "outras receitas", já CONFIRMADA. Devolve a receita."""
    receita = servico_receita.lancar_receita_informada(
        empresa,
        ano,
        mes,
        mercado,
        valor,
        ORIGEM_OUTRAS,
        "Lançamento sintético de teste.",
        "Extrato sintético de teste.",
        usuario,
    )
    return servico_receita.confirmar_receita_informada(receita, usuario)


def confirmar_meses(empresa, usuario, competencias):
    """Confirma os meses (lista de (ano, mês)) como "receita completa"."""
    return [servico_receita.confirmar_mes(empresa, ano, mes, usuario) for ano, mes in competencias]


def sequencia(ano: int, mes: int, quantidade: int):
    """(ano, mês) de `quantidade` meses a partir de `ano/mes`, em ordem."""
    indice = ano * 12 + (mes - 1)
    return [((indice + k) // 12, (indice + k) % 12 + 1) for k in range(quantidade)]
