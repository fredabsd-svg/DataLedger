"""DL-077, fatia 1: correção única da auditoria (rodada 1), parte da ECD e do documento.

Cobre, com expectativas escritas à mão:
- T5 (A5, RC-46): CNPJ alfanumérico. A ECD aceita `[A-Z0-9]{12}[0-9]{2}` no registro 0000 e
  compara na forma canônica (maiúsculas, sem máscara). O leiaute do sistema de referência, edição
  de 2018, recusa com mensagem NOMEADA, na importação e na exportação.
- T9 (A9): 0000 repetido é erro; 0000 sem CNPJ é aviso; arquivo sem 0000 é aviso na prévia.
- T2 (A2, lado do leitor ECD): COD_NAT 04 chega ao núcleo com tipos aceitos receita e despesa.

Dados sintéticos. CNPJ alfanumérico fictício.
"""

from datetime import date

import pytest

from apps.contabilidade.intercambio.canonico import NIVEL_AVISO, NIVEL_ERRO, IntercambioRecusado
from apps.contabilidade.intercambio.leitura import ler_arquivo
from apps.contabilidade.intercambio.plano import conferir_plano, exportar_plano
from apps.contabilidade.services import criar_conta_pelo_plano
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

CNPJ_ALFA = "12ABC34501DE35"  # sintético (RC-46)
CNPJ_ALFA_DE_OUTRA = "98XYZ76543WX21"  # sintético
CNPJ_NUMERICO = "22233344000138"  # sintético
MENSAGEM_ALFA = (
    "o leiaute do sistema de referência, edição de 2018, só define inscrição numérica; "
    "CNPJ alfanumérico ainda não é suportado nesse formato."
)


@pytest.fixture
def empresa_alfa():
    escritorio = Escritorio.objects.create(nome="Escritório DL077 RC-46", cnpj="44444444000144")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Alfanumérica Ltda", cnpj=CNPJ_ALFA
    )


@pytest.fixture
def empresa_numerica():
    escritorio = Escritorio.objects.create(nome="Escritório DL077 Doc", cnpj="45454545000145")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Numérica Ltda", cnpj=CNPJ_NUMERICO
    )


def _ecd(*linhas):
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")


def _0000(cnpj):
    """Registro 0000 da ECD: o CNPJ é o campo 06, que fica no índice 5 da lista de campos."""
    return f"|0000|LECD|01012026|31122026|Empresa Sintética Ltda|{cnpj}|SP||"


def _previa_ecd(empresa, *linhas):
    return conferir_plano(
        empresa, ler_arquivo("ecd", _ecd(*linhas), nome_arquivo="e.txt"), "so_acrescentar", {}
    )


def _erros(previa):
    return [o for o in previa.ocorrencias if o.nivel == NIVEL_ERRO]


def _avisos(previa):
    return [o for o in previa.ocorrencias if o.nivel == NIVEL_AVISO]


# -----------------------------------------------------------------------------
# T5 (A5): CNPJ alfanumérico na ECD
# -----------------------------------------------------------------------------


def test_ecd_com_cnpj_alfanumerico_da_mesma_empresa_passa_na_conferencia(empresa_alfa):
    previa = _previa_ecd(empresa_alfa, _0000(CNPJ_ALFA), "|I050|01012026|01|S|1|1||Ativo|")

    assert not any(o.campo == "documento" for o in _erros(previa))
    assert not previa.tem_erro, previa.ocorrencias


def test_ecd_cnpj_alfanumerico_de_outra_empresa_e_recusado(empresa_alfa):
    previa = _previa_ecd(empresa_alfa, _0000(CNPJ_ALFA_DE_OUTRA), "|I050|01012026|01|S|1|1||Ativo|")

    assert any(o.campo == "documento" for o in _erros(previa))
    assert previa.tem_erro


def test_ecd_cnpj_alfanumerico_em_minusculas_e_comparado_na_forma_canonica(empresa_alfa):
    """O campo do leiaute é C 014. Em minúsculas, o valor canônico é o mesmo."""
    previa = _previa_ecd(empresa_alfa, _0000(CNPJ_ALFA.lower()), "|I050|01012026|01|S|1|1||Ativo|")

    assert not previa.tem_erro, previa.ocorrencias


def test_ecd_cnpj_com_mascara_nao_e_aceito_no_0000(empresa_numerica):
    """O manual não prevê máscara no 0000 (campo C 014). Não se aceita palpite."""
    previa = _previa_ecd(
        empresa_numerica,
        _0000("22.233.344/0001-38"),
        "|I050|01012026|01|S|1|1||Ativo|",
    )

    erro = next(o for o in _erros(previa) if o.campo == "0000.06")
    assert "14 caracteres" in erro.mensagem and "sem máscara" in erro.mensagem


def test_ecd_cnpj_numerico_continua_valido_e_sem_regressao(empresa_numerica):
    previa = _previa_ecd(empresa_numerica, _0000(CNPJ_NUMERICO), "|I050|01012026|01|S|1|1||Ativo|")

    assert not previa.tem_erro, previa.ocorrencias


def test_importacao_de_referencia_com_0000_alfanumerico_recusa_com_mensagem_nomeada():
    conteudo = (f"|0000|{CNPJ_ALFA}|\r\n|0200|1|1|S|Ativo|||A|||||\r\n").encode("iso-8859-1")

    resultado = ler_arquivo("referencia", conteudo, nome_arquivo="ref.txt")

    erro = next(o for o in _erros_do_leitor(resultado) if o.campo == "0000.2")
    assert erro.mensagem == MENSAGEM_ALFA
    assert resultado.documento_declarado is None


def test_exportacao_de_referencia_de_empresa_alfanumerica_recusa_com_mensagem_nomeada(
    empresa_alfa,
):
    """Exportação: a mensagem é a nomeada, e não o 'inválido' genérico da auditoria."""
    criar_conta_pelo_plano(
        empresa=empresa_alfa,
        codigo="1",
        nome="Ativo",
        tipo="ativo",
        natureza="devedora",
        codigo_pai=None,
        analitica=False,
    )

    with pytest.raises(IntercambioRecusado) as excinfo:
        exportar_plano(empresa=empresa_alfa, formato="referencia")

    assert excinfo.value.mensagem == MENSAGEM_ALFA


def test_exportacao_ecd_de_empresa_alfanumerica_nao_e_recusada_por_documento(empresa_alfa):
    """A ECD exportada não leva o 0000: o CNPJ alfanumérico não impede esta exportação."""
    criar_conta_pelo_plano(
        empresa=empresa_alfa,
        codigo="1",
        nome="Ativo",
        tipo="ativo",
        natureza="devedora",
        codigo_pai=None,
        analitica=False,
    )

    arquivo = exportar_plano(empresa=empresa_alfa, formato="ecd", data_alteracao=date(2026, 1, 1))

    assert arquivo.quantidade_contas == 1


def _erros_do_leitor(resultado):
    return [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]


# -----------------------------------------------------------------------------
# T9 (A9): registro 0000
# -----------------------------------------------------------------------------


def test_dois_0000_no_mesmo_arquivo_sao_erro_mesmo_se_o_primeiro_confere(empresa_numerica):
    """Concatenação: a empresa certa primeiro, e uma abertura de OUTRA empresa depois. Antes,
    a segunda passava em silêncio e a conferência era contornável."""
    previa = _previa_ecd(
        empresa_numerica,
        _0000(CNPJ_NUMERICO),
        "|I050|01012026|01|S|1|1||Ativo|",
        _0000(CNPJ_ALFA_DE_OUTRA),
    )

    erro = next(o for o in _erros(previa) if o.campo == "0000")
    assert erro.linha == 3
    assert "repetido" in erro.mensagem and "linha 1" in erro.mensagem
    assert previa.tem_erro


def test_0000_sem_cnpj_e_aviso_de_empresa_nao_conferida(empresa_numerica):
    previa = _previa_ecd(
        empresa_numerica,
        "|0000|LECD|01012026|31122026|Empresa Sintética Ltda|||",
        "|I050|01012026|01|S|1|1||Ativo|",
    )

    aviso = next(o for o in _avisos(previa) if o.campo == "0000.06")
    assert aviso.linha == 1
    assert "não foi conferida" in aviso.mensagem
    assert not previa.tem_erro


def test_arquivo_sem_0000_e_aviso_visivel_na_previa(empresa_numerica):
    previa = _previa_ecd(empresa_numerica, "|I050|01012026|01|S|1|1||Ativo|")

    aviso = next(o for o in _avisos(previa) if o.campo == "0000")
    assert aviso.linha == 0
    assert "a empresa do arquivo não conferida" in aviso.mensagem
    assert not previa.tem_erro


# -----------------------------------------------------------------------------
# T2 (A2, lado do leitor ECD): COD_NAT 04 vira "resultado" para o núcleo
# -----------------------------------------------------------------------------


def test_ecd_cod_nat_04_chega_ao_nucleo_com_tipos_aceitos_receita_e_despesa():
    resultado = ler_arquivo(
        "ecd",
        _ecd(
            _0000(CNPJ_NUMERICO),
            "|I050|01012026|01|S|1|1||Ativo|",
            "|I050|01012026|04|A|2|1.9|1|Receita sob ativo|",
        ),
        nome_arquivo="e.txt",
    )

    resultado_04 = next(c for c in resultado.contas if c.codigo == "1.9")
    assert resultado_04.tipo is None
    assert resultado_04.tipos_aceitos == frozenset({"receita", "despesa"})
    ativo = next(c for c in resultado.contas if c.codigo == "1")
    assert ativo.tipos_aceitos is None  # COD_NAT 01 já diz o tipo: sem restrição extra
