"""DL-077, fatia 1 (decisões B3 e B4 do arquiteto): conferência do CNPJ/CPF declarado pelo
arquivo, e situação ativa/inativa da conta, no NÚCLEO (`conferir_plano`, `aplicar_plano`,
`exportar_plano`).

Dois formatos têm documento declarado: o leiaute com separador do sistema de referência
(registro 0000, campo 2) e a ECD (registro 0000, campo 06, p. 64 do manual). O próprio
DataLedger não declara documento. A situação vem só do leiaute com separador (campo 7 do
0200). Dados sintéticos: CNPJ fictício, nomes fictícios. Os arquivos são montados aqui,
do que o leiaute define.
"""

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio.canonico import NIVEL_AVISO, NIVEL_ERRO
from apps.contabilidade.intercambio.leitura import ler_arquivo
from apps.contabilidade.intercambio.plano import (
    PlanoRecusado,
    aplicar_plano,
    conferir_plano,
    exportar_plano,
)
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

CNPJ = "44444444000144"  # sintético: é o da empresa escolhida
CNPJ_DE_OUTRA = "55555555000155"  # sintético: é o declarado pelo arquivo de outra empresa
PREFIXOS = {"1": "ativo"}


def _iso(*linhas):
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")


def _ref(cabecalho_0000, *contas):
    """Leiaute com separador: 0000 e 0200 (11 campos, identificador incluído)."""
    return _iso(cabecalho_0000, *contas)


def _conta_ref(reduzido, classificacao, tipo, descricao, situacao="A"):
    return "|".join(
        ["0200", reduzido, classificacao, tipo, descricao, "", situacao, "", "", "", ""]
    )


def _ecd(cnpj_no_0000):
    """ECD mínima: 0000 (CNPJ no campo 06) e uma I050 analítica."""
    return _iso(
        f"|0000|LECD|01012026|31122026|Empresa Sintética Ltda|{cnpj_no_0000}|SP||",
        "|I050|31012026|01|S|1|1||Ativo|",
    )


def _proprio():
    return (
        "codigo;nome;codigo_pai;analitica;tipo;natureza\r\n1;Ativo;;N;ativo;devedora\r\n"
    ).encode("utf-8")


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório Declarado", cnpj="33333333000133")
    return Empresa.objects.create(escritorio=escritorio, razao_social="Empresa", cnpj=CNPJ)


def _previa(empresa, conteudo, formato, politica="so_acrescentar", prefixos=None):
    resultado = ler_arquivo(formato, conteudo, nome_arquivo="plano.txt")
    return conferir_plano(empresa, resultado, politica, prefixos or {})


def _aplicar(empresa, previa):
    return aplicar_plano(
        empresa,
        previa,
        None,
        None,
        sha256_esperado=previa.sha256,
        assinatura_esperada=previa.assinatura,
    )


def _erro_de_documento(previa):
    return [o for o in previa.ocorrencias if o.campo == "documento" and o.nivel == NIVEL_ERRO]


# -----------------------------------------------------------------------------
# B3: conferência do documento declarado, no núcleo, nos dois formatos
# -----------------------------------------------------------------------------


def test_referencia_declarando_o_cnpj_da_empresa_com_mascara_nao_gera_erro(empresa):
    conteudo = _ref("0000|44.444.444/0001-44", _conta_ref("1", "1", "S", "Ativo"))

    previa = _previa(empresa, conteudo, "referencia", prefixos=PREFIXOS)

    assert not _erro_de_documento(previa)
    assert not previa.tem_erro, previa.ocorrencias


def test_referencia_declarando_outro_cnpj_gera_erro_no_arquivo_sem_repetir_os_numeros(empresa):
    conteudo = _ref("0000|" + CNPJ_DE_OUTRA, _conta_ref("1", "1", "S", "Ativo"))

    previa = _previa(empresa, conteudo, "referencia", prefixos=PREFIXOS)

    erros = _erro_de_documento(previa)
    assert [(o.linha, o.nivel) for o in erros] == [(0, NIVEL_ERRO)]
    assert previa.tem_erro
    assert CNPJ_DE_OUTRA not in erros[0].mensagem and CNPJ not in erros[0].mensagem


def test_referencia_com_outro_cnpj_nao_grava_nada_mesmo_com_token_da_previa(empresa):
    conteudo = _ref("0000|" + CNPJ_DE_OUTRA, _conta_ref("1", "1", "S", "Ativo"))
    previa = _previa(empresa, conteudo, "referencia", prefixos=PREFIXOS)

    with pytest.raises(PlanoRecusado):
        _aplicar(empresa, previa)

    assert Conta.objects.filter(empresa=empresa).count() == 0


def test_ecd_declarando_o_cnpj_da_empresa_nao_gera_erro(empresa):
    previa = _previa(empresa, _ecd(CNPJ), "ecd")

    assert not _erro_de_documento(previa)
    assert not previa.tem_erro, previa.ocorrencias


def test_ecd_declarando_outro_cnpj_gera_erro_e_nao_grava(empresa):
    previa = _previa(empresa, _ecd(CNPJ_DE_OUTRA), "ecd")

    assert _erro_de_documento(previa)
    with pytest.raises(PlanoRecusado):
        _aplicar(empresa, previa)
    assert Conta.objects.filter(empresa=empresa).count() == 0


def test_ecd_com_cnpj_que_nao_tem_14_digitos_e_erro_nomeado_no_leitor(empresa):
    resultado = ler_arquivo("ecd", _ecd("4444444400014A"), nome_arquivo="plano.txt")

    assert resultado.documento_declarado is None
    assert any(o.campo == "0000.06" and o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)


def test_ecd_sem_0000_nao_tem_documento_para_conferir_e_nao_gera_erro_de_documento(empresa):
    conteudo = _iso("|I050|31012026|01|S|1|1||Ativo|")

    previa = _previa(empresa, conteudo, "ecd")

    assert previa.resultado.documento_declarado is None
    assert not _erro_de_documento(previa)


def test_proprio_nao_declara_documento_e_nao_e_conferido(empresa):
    previa = _previa(empresa, _proprio(), "proprio")

    assert previa.resultado.documento_declarado is None
    assert not _erro_de_documento(previa)
    assert not previa.tem_erro


# -----------------------------------------------------------------------------
# B4: situação ativa/inativa da conta
# -----------------------------------------------------------------------------


def test_conta_inativa_no_arquivo_e_criada_inativa_com_aviso_e_fica_na_trilha(empresa):
    conteudo = _ref(
        "0000|" + CNPJ,
        _conta_ref("1", "1", "S", "Ativo"),
        _conta_ref("2", "1.1", "A", "Caixa antiga", situacao="I"),
    )
    previa = _previa(empresa, conteudo, "referencia", prefixos=PREFIXOS)

    assert not previa.tem_erro, previa.ocorrencias
    assert any(o.campo == "0200.7" and o.nivel == NIVEL_AVISO for o in previa.ocorrencias)
    _aplicar(empresa, previa)

    assert Conta.objects.get(empresa=empresa, codigo="1.1").ativo is False
    assert Conta.objects.get(empresa=empresa, codigo="1").ativo is True
    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.importado")
    assert trilha.detalhes["inativas_criadas"] == 1


def test_conta_ativa_no_arquivo_e_criada_ativa(empresa):
    conteudo = _ref("0000|" + CNPJ, _conta_ref("1", "1", "S", "Ativo"))
    previa = _previa(empresa, conteudo, "referencia", prefixos=PREFIXOS)

    _aplicar(empresa, previa)

    assert Conta.objects.get(empresa=empresa, codigo="1").ativo is True


def test_atualizar_nome_nao_muda_a_situacao_de_conta_existente(empresa):
    """Política de atualizar o nome: o nome muda, a situação do cadastro fica (inativa),
    mesmo com o arquivo dizendo ativa. A divergência vira aviso."""
    conta = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Nome antigo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
        ativo=False,
    )
    conteudo = _ref("0000|" + CNPJ, _conta_ref("1", "1", "S", "Nome novo", situacao="A"))
    previa = _previa(
        empresa,
        conteudo,
        "referencia",
        politica="acrescentar_e_atualizar_nome",
        prefixos=PREFIXOS,
    )

    assert any(o.campo == "ativa" and o.nivel == NIVEL_AVISO for o in previa.ocorrencias)
    _aplicar(empresa, previa)

    conta.refresh_from_db()
    assert conta.nome == "Nome novo"
    assert conta.ativo is False


def test_arquivo_inativo_nao_desativa_conta_existente_ativa(empresa):
    conta = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
        ativo=True,
    )
    conteudo = _ref("0000|" + CNPJ, _conta_ref("1", "1", "S", "Ativo", situacao="I"))

    previa = _previa(empresa, conteudo, "referencia", prefixos=PREFIXOS)
    assert not previa.tem_erro
    _aplicar(empresa, previa)

    conta.refresh_from_db()
    assert conta.ativo is True


def test_exportacao_do_leiaute_de_referencia_grava_a_situacao_real(empresa):
    Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa antiga",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=True,
        conta_pai=Conta.objects.get(empresa=empresa, codigo="1"),
        ativo=False,
    )

    arquivo = exportar_plano(empresa=empresa, formato="referencia", filtro="todas")

    linhas = arquivo.conteudo.decode("iso-8859-1").split("\r\n")
    situacoes = {
        linha.split("|")[2]: linha.split("|")[6] for linha in linhas if linha[:5] == "0200|"
    }
    assert situacoes == {"1": "A", "1.1": "I"}
    assert arquivo.avisos and "nao e estavel" in arquivo.avisos[0]


def test_formatos_sem_situacao_criam_contas_ativas_e_a_exportacao_proprio_nao_tem_aviso(empresa):
    previa = _previa(empresa, _proprio(), "proprio")
    _aplicar(empresa, previa)

    assert Conta.objects.get(empresa=empresa, codigo="1").ativo is True
    arquivo = exportar_plano(empresa=empresa, formato="proprio", filtro="todas")
    assert arquivo.avisos == ()
