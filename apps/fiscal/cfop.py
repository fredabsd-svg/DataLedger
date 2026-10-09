"""Tabela de CFOP como DADO com fonte — DL-081, frente A.

Fonte: Portal Nacional da NF-e, tabela de apoio do Informe Técnico 2023.002 v2.10, publicada
em 04/09/2026 (aviso do Portal, `https://www.nfe.fazenda.gov.br/portal/informe.aspx?ehCTG=false&Informe=nCdXYyjCKQg=`).
Planilha baixada em 09/10/2026 de
`https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=74KmX8poGpM=`, sha256
`577e05eec452294945d0e9df1f9bb9b21a4af115938e75ec74cf6a541ae4dacf` (registrado no plano DL-081 e
na consulta de 09/10/2026, seção 2). O arquivo `dados/cfop_it2023002_v210.csv` é a planilha
convertida para CSV, sem alteração de conteúdo: 619 códigos, separados por `;`, colunas
`codigo;descricao;indNFe;indComunica;indTransp;indDevol;vigencia_inicio;vigencia_fim`. O sha256
DO CSV é conferido por teste (`test_dl081_cfop.py`), e não o da planilha.

RESSALVA DO PRÓPRIO INFORME: o Convênio s/nº de 1970 prevalece em caso de divergência. A
conferência com o Convênio não foi feita (CONFAZ inacessível em 09/10/2026, consulta, seção 2).
Esta tabela é tabela de apoio, não norma: a descrição de um CFOP não é fundamento normativo.

Regra de uso (consulta de 09/10/2026, seção 2): a DEVOLUÇÃO é identificada pela coluna
`indDevol`, nunca pela faixa do CFOP. Cada faixa mistura usos (x.201 e x.202 podem ser devolução
de venda na entrada e devolução de compra na saída, e x.410, x.503, x.918 também têm `indDevol` 1).
CFOP fora da tabela não recebe suposição: quem chama recebe `None` e leva a sugestão
"a classificar".
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

ARQUIVO_TABELA = Path(__file__).resolve().parent / "dados" / "cfop_it2023002_v210.csv"

# Formato do CFOP no arquivo: "X.YYY" (4 dígitos, o primeiro de 1 a 7).
# A entrada aceita com ou sem ponto.
_FORMATO_CFOP = re.compile(r"[1-7]\.?[0-9]{3}")
_COLUNAS = ("codigo", "descricao", "indNFe", "indComunica", "indTransp", "indDevol")


@dataclass(frozen=True)
class Cfop:
    """Um CFOP da tabela oficial. Os indicadores são `bool`, lidos de 0/1 do arquivo."""

    codigo: str
    descricao: str
    ind_nfe: bool
    ind_comunica: bool
    ind_transp: bool
    ind_devol: bool
    vigencia_inicio: date
    vigencia_fim: date | None


def _data(texto: str, campo: str, linha: int) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError as exc:
        raise ValueError(f"CFOP: {campo} inválida na linha {linha} da tabela: {texto!r}") from exc


def _indicador(texto: str, campo: str, linha: int) -> bool:
    if texto not in ("0", "1"):
        raise ValueError(f"CFOP: {campo} fora de 0/1 na linha {linha} da tabela: {texto!r}")
    return texto == "1"


@lru_cache(maxsize=1)
def _tabela() -> dict[str, Cfop]:
    """Carrega o CSV uma vez por processo.

    Linha malformada ou código repetido derruba o carregamento:
    uma tabela com erro não pode classificar nota em silêncio."""
    tabela: dict[str, Cfop] = {}
    with ARQUIVO_TABELA.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        if tuple(leitor.fieldnames or ()) != (*_COLUNAS, "vigencia_inicio", "vigencia_fim"):
            raise ValueError("CFOP: cabeçalho da tabela diferente do esperado.")
        for numero, linha in enumerate(leitor, start=2):
            codigo = linha["codigo"]
            if codigo in tabela:
                raise ValueError(f"CFOP: código {codigo} repetido na tabela (linha {numero}).")
            tabela[codigo] = Cfop(
                codigo=codigo,
                descricao=linha["descricao"],
                ind_nfe=_indicador(linha["indNFe"], "indNFe", numero),
                ind_comunica=_indicador(linha["indComunica"], "indComunica", numero),
                ind_transp=_indicador(linha["indTransp"], "indTransp", numero),
                ind_devol=_indicador(linha["indDevol"], "indDevol", numero),
                vigencia_inicio=_data(linha["vigencia_inicio"], "vigencia_inicio", numero),
                vigencia_fim=_data(linha["vigencia_fim"], "vigencia_fim", numero),
            )
    return tabela


def cfop(codigo: str) -> Cfop | None:
    """CFOP da tabela oficial, ou `None` quando o código não existe nela.

    Aceita "5102" e "5.102". Formato inválido também devolve `None`: quem chama trata como
    "a classificar", e nunca presume o significado do código.
    """
    if not isinstance(codigo, str) or not _FORMATO_CFOP.fullmatch(codigo):
        return None
    limpo = codigo.replace(".", "")
    return _tabela().get(f"{limpo[0]}.{limpo[1:]}")


# Devolução de combustível, pela DESCRIÇÃO da tabela oficial (DL-083, PE-85.2, HI-134 e HI-140).
#
# Dois sentidos, com o mesmo fato econômico (devolução de combustível ou lubrificante):
# - devolução de VENDA, na entrada própria da empresa: 1.660 a 1.662 e 2.660 a 2.662. O emitente
#   da nota de entrada é a empresa, e o CFOP diz a destinação original da venda;
# - devolução de COMPRA, recebida pela empresa como destinatária: 5.660 a 5.662 e 6.660 a 6.662.
#   O CFOP é o do cliente, que devolveu a venda à empresa.
# Os dois são `indDevol` 1. A tabela diz a destinação pelo texto ("destinados a consumidor ou
# usuário
# final", "destinados à comercialização", "destinados à industrialização subsequente"), e o texto é
# o que decide, não o terceiro dígito do código.
_PREFIXO_DEVOLUCAO_VENDA_COMBUSTIVEL = "Devolução de venda de combustíveis ou lubrificantes"
_PREFIXO_DEVOLUCAO_COMPRA_COMBUSTIVEL = "Devolução de compra de combustíveis ou lubrificantes"
_DESTINACAO_CONSUMIDOR_FINAL = "consumidor ou usuário final"


def e_devolucao_de_combustivel(codigo: str) -> bool:
    """O CFOP é devolução de combustível ou lubrificante, de venda ou de compra (`indDevol` 1).

    CFOP fora da tabela, ou formato inválido, não é: quem chama trata como "a classificar". Não
    separa combustível de lubrificante: quem separa é o NCM (`ncm_combustivel`).
    """
    info = cfop(codigo)
    return (
        info is not None
        and info.ind_devol
        and info.descricao.startswith(
            (_PREFIXO_DEVOLUCAO_VENDA_COMBUSTIVEL, _PREFIXO_DEVOLUCAO_COMPRA_COMBUSTIVEL)
        )
    )


def e_devolucao_de_combustivel_para_consumo(codigo: str) -> bool:
    """Devolução de combustível cuja destinação original é o consumidor ou usuário final.

    É a que sai do 1,6% (Lei 9.249, art. 15, § 1º, I) quando o NCM é de combustível. Pela descrição
    da tabela: "destinados a consumidor ou usuário final" (x.662) ou "adquiridos por consumidor ou
    usuário final" (5.662, 6.662).
    """
    return (
        e_devolucao_de_combustivel(codigo)
        and _DESTINACAO_CONSUMIDOR_FINAL in cfop(codigo).descricao
    )
