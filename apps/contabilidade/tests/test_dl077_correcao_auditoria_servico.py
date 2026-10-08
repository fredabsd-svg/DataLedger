"""Correção única da auditoria das fatias 2 e 3 (DL-077, rodada 1): regras do SERVIÇO de importação.

Cada teste nomeia o achado (A1 a A12) e as lacunas de mutação (M26 a M58) da seção 12 da auditoria
`docs/auditorias/2026-10-08-dl-077-fatias-2-3-rodada-1.md`. Dados SINTÉTICOS: CNPJ de exemplo, plano
do cenário de exportação, valores redondos. Nenhum arquivo real entra aqui (RC-167).
"""

import io
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from openpyxl import Workbook

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.models import (
    EstadoImportacaoLancamentos,
    ImportacaoLancamentos,
    LancamentoContabil,
    LancamentoImportado,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento, encerrar_competencia
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.empresas.models import ModoEscrituracao

pytestmark = pytest.mark.django_db

CABECALHO = "numero;data;historico;conta;lado;valor\r\n"
CNPJ_DE_OUTRA = "88888888000188"


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório Correção", "66666666000166")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Correção", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    return {"empresa": empresa, "contas": contas}


# --- Construtores de arquivo (sintéticos) -----------------------------------------------------


def _proprio(*linhas):
    return (CABECALHO + "".join(linha + "\r\n" for linha in linhas)).encode("utf-8")


def _par(
    numero, data="2026-03-10", historico="Compra", conta_d="1.1.1", conta_c="2.1", valor="100.00"
):
    return [
        f"{numero};{data};{historico};{conta_d};D;{valor}",
        f"{numero};{data};{historico};{conta_c};C;{valor}",
    ]


def _ecd(*linhas, cnpj=CNPJ_DA_EMPRESA, com_0000=True):
    cabecalho = [f"|0000|LECD|01032026|31032026|Empresa Sintetica Ltda|{cnpj}|SP|||"]
    corpo = (cabecalho if com_0000 else []) + list(linhas)
    return ("".join(linha + "\r\n" for linha in corpo)).encode("iso-8859-1")


def _i200(numero, data="10032026", valor="100,00"):
    return f"|I200|{numero}|{data}|{valor}|N||"


def _i250(conta, lado, valor, historico="Compra"):
    return f"|I250|{conta}||{valor}|{lado}|||{historico}||"


def _referencia(*linhas):
    return ("".join(linha + "\r\n" for linha in linhas)).encode("iso-8859-1")


def _ref_0000(documento=CNPJ_DA_EMPRESA):
    return f"|0000|{documento}|"


def _ref_6100(data="10/03/2026", debito="3", credito="12", valor="100,00", historico="Compra"):
    return f"|6100|{data}|{debito}|{credito}|{valor}||{historico}||||"


def _xlsx(linhas):
    pasta = Workbook()
    planilha = pasta.active
    planilha.title = "lancamentos"
    for linha in linhas:
        planilha.append(linha)
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


def _receber(empresa, formato, conteudo, nome="lancamentos.txt"):
    return servico.receber(
        empresa=empresa, formato=formato, conteudo=conteudo, nome_arquivo=nome, usuario=None
    )


def _receber_proprio(empresa, *linhas, nome="lancamentos.txt"):
    return _receber(empresa, "proprio", _proprio(*linhas), nome)


def _aceitar_arquivo(importacao):
    servico.aceitar_avisos(importacao, [], aceitar_arquivo=True, usuario=None)


def _diario(empresa):
    return LancamentoContabil.objects.filter(empresa=empresa)


# --- A1: erro do arquivo inteiro bloqueia as duas políticas -----------------------------------


@pytest.mark.parametrize(
    "formato,conteudo",
    [
        pytest.param(
            "ecd",
            _ecd(
                _i200(1),
                _i250("1.1.1", "D", "100,00"),
                _i250("2.1", "C", "100,00"),
                f"|0000|LECD|01032026|31032026|Outra|{CNPJ_DE_OUTRA}|SP|||",
                _i200(2),
                _i250("1.1.1", "D", "100,00", "DA OUTRA EMPRESA"),
                _i250("2.1", "C", "100,00", "DA OUTRA EMPRESA"),
            ),
            id="ecd-segundo-0000",
        ),
        pytest.param(
            "ecd",
            _ecd(
                _i200(1),
                _i250("1.1.1", "D", "100,00"),
                _i250("2.1", "C", "100,00"),
                cnpj="1234567800019",
            ),
            id="ecd-cnpj-13-digitos",
        ),
        pytest.param(
            "referencia",
            _referencia(_ref_0000("12ABC345000190"), "|6000|X||||", _ref_6100()),
            id="referencia-cnpj-alfanumerico",
        ),
        pytest.param(
            "proprio",
            _proprio(*_par(1), '2;2026-03-10;"Venda;1.1.1;D;50.00'),
            id="proprio-aspas-sem-fechar",
        ),
    ],
)
def test_t_a1_erro_do_arquivo_inteiro_bloqueia_tudo_ou_nada_e_so_validos(
    cenario, formato, conteudo
):
    """A1: 'só os válidos' não contorna erro do arquivo inteiro. Nenhum lançamento
    entra no Diário."""
    empresa = cenario["empresa"]
    importacao = _receber(empresa, formato, conteudo)

    assert importacao.quantidade_erros_do_arquivo_inteiro >= 1

    for politica in (servico.TUDO_OU_NADA, servico.SO_VALIDOS):
        with pytest.raises(servico.ImportacaoNaoEfetivada):
            servico.efetivar(importacao, politica=politica, usuario=None)

    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert not _diario(empresa).exists()


def test_t_a1_so_validos_lista_os_erros_do_arquivo_inteiro_no_veredito(cenario):
    """A1 (na API de conferência): a lista do que bloqueia o só-válidos traz o erro do arquivo."""
    importacao = _receber(
        cenario["empresa"],
        "ecd",
        _ecd(
            _i200(1),
            _i250("1.1.1", "D", "100,00"),
            _i250("2.1", "C", "100,00"),
            cnpj="1234567800019",
        ),
    )
    erros = [o for o in importacao.ocorrencias_do_arquivo if servico.erro_do_arquivo_inteiro(o)]
    assert erros and erros[0]["campo"] == "0000.6"


# --- A2: byte nulo em arquivo de texto ----------------------------------------------------------


@pytest.mark.parametrize(
    "formato,conteudo",
    [
        pytest.param(
            "proprio", _proprio(*_par(1, historico="Com\x00nulo")), id="proprio-historico"
        ),
        pytest.param("proprio", _proprio(*_par(1)) + b"\x00" * 100, id="proprio-so-nulos"),
        pytest.param(
            "ecd",
            _ecd(
                _i200(1, valor="100,00\x00"),
                _i250("1.1.1", "D", "100,00"),
                _i250("2.1", "C", "100,00"),
            ),
            id="ecd-valor",
        ),
        pytest.param(
            "referencia",
            _referencia(_ref_0000(), "|6000|X||||", _ref_6100(data="10/03/2026\x00")),
            id="referencia-data",
        ),
    ],
)
def test_t_a2_byte_nulo_em_formato_de_texto_e_recusado_antes_de_ler(cenario, formato, conteudo):
    """A2: o byte nulo é recusa nomeada (ImportacaoRecusada, 400), sem chegar ao PostgreSQL."""
    with pytest.raises(servico.ImportacaoRecusada, match="byte nulo"):
        _receber(cenario["empresa"], formato, conteudo)

    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


def test_t_a2_mensagem_de_ocorrencia_escapa_controle_e_nao_leva_byte_cru(cenario):
    """A2: caractere de controle que chega numa mensagem vira \\uXXXX, e não vai cru ao JSON."""
    importacao = _receber_proprio(
        cenario["empresa"], "1;2026-03-10;x;1.1.1;D;1.00", "x\x01y;2026-03-10;a;1.1.1;D;1.00"
    )
    mensagens = [o["mensagem"] for o in importacao.ocorrencias_do_arquivo]

    assert any("\\u0001" in mensagem for mensagem in mensagens)
    assert not any("\x01" in mensagem for mensagem in mensagens)


# --- A3: teto de partidas por arquivo e reconferência sem reescrita --------------------------


def _quatro_partidas(numero):
    return [
        f"{numero};2026-03-10;Lote;1.1.1;D;50.00",
        f"{numero};2026-03-10;Lote;1.1.2;D;50.00",
        f"{numero};2026-03-10;Lote;2.1;C;50.00",
        f"{numero};2026-03-10;Lote;3.1;C;50.00",
    ]


def test_t_a3_arquivo_acima_de_4000_partidas_e_recusado_no_recebimento(cenario):
    """A3: 1.001 lançamentos de 4 partidas = 4.004 partidas: recusa nomeada, nada gravado."""
    linhas = [linha for numero in range(1, 1002) for linha in _quatro_partidas(numero)]

    with pytest.raises(servico.ImportacaoRecusada, match="4004 partidas"):
        _receber_proprio(cenario["empresa"], *linhas)

    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


def test_t_a3_arquivo_no_teto_de_4000_partidas_e_aceito(cenario):
    """A3, fronteira: 1.000 lançamentos de 4 partidas = 4.000 partidas entram na conferência."""
    linhas = [linha for numero in range(1, 1001) for linha in _quatro_partidas(numero)]

    importacao = _receber_proprio(cenario["empresa"], *linhas)

    assert importacao.quantidade_lancamentos == 1000
    assert importacao.quantidade_com_erro == 0


def test_t_a3_reconferencia_sem_mudanca_nao_regrava_nenhuma_linha(cenario):
    """A3: a reconferência só regrava a linha que mudou. Sem mudança, zero UPDATE de linha.

    É a reescrita redundante que se elimina dentro da efetivação; a reconferência continua (M27).
    """
    importacao = _receber_proprio(cenario["empresa"], *_par(1), *_par(2, historico="Venda"))
    with CaptureQueriesContext(connection) as capturadas:
        servico.reconferir(importacao, usuario=None)

    updates_de_linha = [
        q["sql"]
        for q in capturadas.captured_queries
        if q["sql"].lstrip().upper().startswith("UPDATE")
        and "contabilidade_lancamentoimportado" in q["sql"]
    ]
    assert updates_de_linha == []


# --- A4: a conferência replica o que criar_lancamento recusa ------------------------------------


def _lancamento_de_201_partidas(numero):
    """201 partidas que fecham: 101 débitos de 1,00 e 100 créditos de 1,01."""
    debitos = [f"{numero};2026-03-10;Grande;1.1.1;D;1.00"] * 101
    creditos = [f"{numero};2026-03-10;Grande;2.1;C;1.01"] * 100
    return debitos + creditos


def test_t_a4_mais_de_200_partidas_vira_erro_de_conferencia_e_so_validos_e_suspenso(cenario):
    """A4: 201 partidas é erro na conferência, com a mensagem do limite. Antes, só-válidos gravava
    o resto; agora a política está suspensa (BL-676) e nada entra no Diário."""
    empresa = cenario["empresa"]
    importacao = _receber_proprio(empresa, *_par(1), *_lancamento_de_201_partidas(2))

    grande = importacao.lancamentos.get(numero_origem="2")
    assert grande.tem_erro
    assert any("máximo 200 partidas" in o["mensagem"] for o in grande.ocorrencias)
    _aceitar_arquivo(importacao)

    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    with pytest.raises(servico.ImportacaoNaoEfetivada, match="suspensa"):
        servico.efetivar(importacao, politica=servico.SO_VALIDOS, usuario=None)
    assert _diario(empresa).count() == 0


def test_t_a4_valor_de_10_elevado_a_16_e_erro_de_conferencia_e_nao_500(cenario):
    """A4/A9: valor que o Diário não comporta é erro de conferência, nunca estouro na gravação."""
    empresa = cenario["empresa"]
    importacao = _receber_proprio(
        empresa,
        "1;2026-03-10;Grande;1.1.1;D;10000000000000000.00",
        "1;2026-03-10;Grande;2.1;C;10000000000000000.00",
    )

    assert importacao.quantidade_com_erro == 1
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert not _diario(empresa).exists()


def test_t_a4_o_maior_valor_que_cabe_e_aceito(cenario):
    """A9, fronteira: 9.999.999.999.999.999,99 cabe no campo e entra na conferência limpo."""
    importacao = _receber_proprio(
        cenario["empresa"],
        "1;2026-03-10;Limite;1.1.1;D;9999999999999999.99",
        "1;2026-03-10;Limite;2.1;C;9999999999999999.99",
    )

    assert importacao.quantidade_com_erro == 0


def test_t_a9_soma_que_o_resumo_nao_comporta_recusa_o_arquivo_sem_gravar(cenario):
    """A9: dois lançamentos que cabem, mas cuja soma passa de 10^16: recusa do
    arquivo, nada gravado."""
    linhas = [
        "1;2026-03-10;Grande;1.1.1;D;9999999999999999.00",
        "1;2026-03-10;Grande;2.1;C;9999999999999999.00",
        "2;2026-03-10;Grande;1.1.1;D;9999999999999999.00",
        "2;2026-03-10;Grande;2.1;C;9999999999999999.00",
    ]

    with pytest.raises(servico.ImportacaoRecusada, match="passa de 9.999.999.999.999.999,99"):
        _receber_proprio(cenario["empresa"], *linhas)

    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


def test_t_a4_empresa_em_livro_caixa_nao_recebe_importacao(cenario):
    """A4 (recusa de criar_lancamento, DL-038): a empresa em livro-caixa não recebe lançamento."""
    empresa = cenario["empresa"]
    empresa.modo_escrituracao = ModoEscrituracao.LIVRO_CAIXA
    empresa.save(update_fields=["modo_escrituracao"])

    with pytest.raises(servico.ImportacaoRecusada, match="livro-caixa|Livro-caixa|livro caixa"):
        _receber_proprio(empresa, *_par(1))


# --- A5: lançamento igual já no Diário ----------------------------------------------------------


def _efetivar_proprio(empresa, *linhas):
    importacao = _receber_proprio(empresa, *linhas)
    _aceitar_arquivo(importacao)
    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    return importacao


def test_t_a5_reimportar_o_diario_na_mesma_empresa_avisa_cada_duplicata(cenario):
    """A5: F1 efetivado; F2 = F1 + 1 lançamento. Os dois de F1 viram aviso de duplicidade."""
    empresa = cenario["empresa"]
    f1 = [*_par(1), *_par(2, historico="Venda", conta_d="1.1.2", conta_c="3.1", valor="200.00")]
    _efetivar_proprio(empresa, *f1)
    f2 = [*f1, *_par(3, historico="Aluguel", conta_d="4.1", conta_c="1.1.1", valor="50.00")]

    importacao = _receber_proprio(empresa, *f2, nome="f2.txt")

    duplicatas = {
        linha.numero_origem
        for linha in importacao.lancamentos.all()
        if any(o["campo"] == "duplicidade" for o in linha.ocorrencias)
    }
    assert duplicatas == {"1", "2"}
    assert importacao.lancamentos.get(numero_origem="3").tem_aviso is False
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    servico.aceitar_avisos(importacao, ["1", "2"], usuario=None)
    _aceitar_arquivo(importacao)
    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    # F2 = F1 + 1: dois de F1 já estavam no Diário, e o novo entra: 2 + 3 = 5 (duas duplicadas).
    assert _diario(empresa).count() == 5


def test_t_a5_dois_lancamentos_iguais_dentro_do_mesmo_arquivo_nao_geram_duplicidade(cenario):
    """A5: a comparação é só com o Diário. Dois iguais dentro do mesmo arquivo não avisam."""
    importacao = _receber_proprio(cenario["empresa"], *_par(1), *_par(2))

    assert not any(
        o["campo"] == "duplicidade"
        for linha in importacao.lancamentos.all()
        for o in linha.ocorrencias
    )


def test_t_a5_consultas_ao_diario_nao_crescem_com_o_numero_de_lancamentos(cenario):
    """A5: consulta eficiente. Conferir 5 ou 50 lançamentos faz o mesmo número de
    consultas ao Diário."""

    def consultas_ao_diario(n):
        empresa = criar_empresa(
            escritorio=cenario["empresa"].escritorio,
            razao_social=f"Empresa Consultas {n}",
            cnpj=f"9999999900{n:04d}"[:14],
        )
        criar_plano(empresa)
        linhas = [linha for numero in range(1, n + 1) for linha in _par(numero)]
        with CaptureQueriesContext(connection) as capturadas:
            _receber_proprio(empresa, *linhas)
        return sum(
            1
            for q in capturadas.captured_queries
            if "contabilidade_lancamentocontabil" in q["sql"]
            or "contabilidade_itemlancamento" in q["sql"]
        )

    assert consultas_ao_diario(5) == consultas_ao_diario(50)


# --- A7: soma efetivada separada da soma lida ---------------------------------------------------


def test_t_a7_efetivacao_grava_a_soma_efetivada_e_a_trilha_mostra_a_mesma(cenario):
    """A7: a soma efetivada e a trilha mostram o que entrou no Diário.

    Antes, o teste usava a política parcial (lido 300, gravado 100). Ela está suspensa (BL-676), e
    por tudo ou nada o gravado é o lido: 100,00 + 50,00.
    """
    empresa = cenario["empresa"]
    importacao = _receber_proprio(
        empresa,
        *_par(1, valor="100.00"),
        *_par(2, valor="50.00"),
    )
    _aceitar_arquivo(importacao)

    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    importacao.refresh_from_db()
    assert importacao.soma_debitos == Decimal("150.00")
    assert importacao.soma_debitos_efetivados == Decimal("150.00")
    assert importacao.soma_creditos_efetivados == Decimal("150.00")
    trilha = RegistroAuditoria.objects.get(acao="lancamentos.importacao.efetivada")
    assert trilha.detalhes["soma_debitos_efetivados"] == "150.00"
    assert trilha.detalhes["soma_creditos_efetivados"] == "150.00"
    assert trilha.detalhes["quantidade_efetivados"] == 2


# --- A8: ocorrências guardadas com teto e total -------------------------------------------------


def test_t_a8_guarda_no_maximo_500_ocorrencias_com_o_total(cenario):
    """A8: 600 linhas inválidas. Guardadas: 500. O total (601, com o aviso de empresa) é o real."""
    linhas = [f"x{n};2026-03-10;Lixo;1.1.1;D;1.00" for n in range(600)]

    importacao = _receber_proprio(cenario["empresa"], *linhas)

    assert importacao.quantidade_ocorrencias_do_arquivo == 601
    assert len(importacao.ocorrencias_do_arquivo) == 500


def test_t_a8_erro_do_arquivo_inteiro_nunca_some_do_corte(cenario):
    """A8: com 600 erros de linha antes, o erro do arquivo inteiro (lido por último) fica guardado.

    A guarda põe erro do arquivo na frente. Sem isso, o corte o tiraria, e o bloqueio sumiria.
    """
    empresa = cenario["empresa"]
    linhas = [f"x{n};2026-03-10;Lixo;1.1.1;D;1.00" for n in range(600)]
    linhas.append('9;2026-03-10;"Aberta;1.1.1;D;1.00')

    importacao = _receber_proprio(empresa, *linhas)

    assert importacao.ocorrencias_do_arquivo[0]["campo"] == "estrutura"
    _aceitar_arquivo(importacao)
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert not _diario(empresa).exists()


# --- A10: forma sem barras nas pontas (referência) ----------------------------------------------


def test_t_a10_referencia_sem_barras_nas_pontas_e_aceita_com_um_aviso_por_arquivo(cenario):
    """A10 (HI-91, item 2): linhas sem '|' nas pontas são lidas, com UM aviso
    'formato' por arquivo."""
    conteudo = _referencia(
        "0000|" + CNPJ_DA_EMPRESA,
        "6000|X|||",
        _ref_6100()[1:-1],
        "6000|X|||",
        _ref_6100(valor="50,00", historico="Outra")[1:-1],
    )
    # Os códigos da referência são reduzidos: o de-para os liga às contas do plano.
    for codigo, conta in (("3", "1.1.1"), ("12", "2.1")):
        servico.definir_de_para(
            empresa=cenario["empresa"],
            formato="referencia",
            codigo_origem=codigo,
            conta=cenario["contas"][conta],
            usuario=None,
        )

    importacao = _receber(cenario["empresa"], "referencia", conteudo)

    assert importacao.quantidade_lancamentos == 2
    assert importacao.quantidade_com_erro == 0
    avisos_de_formato = [o for o in importacao.ocorrencias_do_arquivo if o["campo"] == "formato"]
    assert len(avisos_de_formato) == 1


def test_t_a10_linha_sem_nenhum_pipe_continua_erro(cenario):
    """A10: sem '|' nenhum não há o que ler com segurança: continua erro de linha
    (arquivo inteiro)."""
    conteudo = _referencia(_ref_0000(), "isto nao e um registro")

    importacao = _receber(cenario["empresa"], "referencia", conteudo)

    assert importacao.quantidade_erros_do_arquivo_inteiro >= 1


# --- A11: arquivo que não declara a empresa exige aceite ----------------------------------------


def test_t_a11_arquivo_sem_empresa_exige_aceite_nas_duas_politicas(cenario):
    """A11: próprio (não declara empresa) exige o aceite do aviso antes de efetivar.

    A política só-válidos está suspensa (BL-676): ela é recusada antes, pela suspensão.
    """
    empresa = cenario["empresa"]
    importacao = _receber_proprio(empresa, *_par(1))
    assert importacao.exige_aceite_do_arquivo is True
    assert importacao.aceite_do_arquivo is False

    with pytest.raises(servico.ImportacaoNaoEfetivada) as excinfo:
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert any(o["campo"] == "empresa" for o in excinfo.value.ocorrencias)
    assert not _diario(empresa).exists()

    _aceitar_arquivo(importacao)
    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert _diario(empresa).count() == 1
    trilha = RegistroAuditoria.objects.get(acao="lancamentos.avisos_aceitos")
    assert trilha.detalhes["arquivo"] is True


def test_t_a11_ecd_com_0000_que_declara_a_empresa_nao_exige_aceite(cenario):
    """A11: o arquivo que declara a empresa (0000 com o CNPJ) não recebe o aviso."""
    importacao = _receber(
        cenario["empresa"],
        "ecd",
        _ecd(_i200(1), _i250("1.1.1", "D", "100,00"), _i250("2.1", "C", "100,00")),
    )

    assert importacao.exige_aceite_do_arquivo is False


def test_t_a11_ecd_sem_0000_exige_aceite(cenario):
    """A11: ECD sem o registro 0000 não declara a empresa: exige o aceite."""
    importacao = _receber(
        cenario["empresa"],
        "ecd",
        _ecd(_i200(1), _i250("1.1.1", "D", "100,00"), _i250("2.1", "C", "100,00"), com_0000=False),
    )

    assert importacao.exige_aceite_do_arquivo is True


def test_t_a11_excel_exige_aceite(cenario):
    """A11: o Excel não traz a empresa: exige o aceite."""
    conteudo = _xlsx(
        [
            ["numero", "data", "historico", "conta", "lado", "valor"],
            [1, "2026-03-10", "Compra", "1.1.1", "D", 100],
            [1, "2026-03-10", "Compra", "2.1", "C", 100],
        ]
    )

    importacao = _receber(cenario["empresa"], "excel", conteudo, nome="lancamentos.xlsx")

    assert importacao.exige_aceite_do_arquivo is True


# --- A12: trilha sem o nome do arquivo; lacunas M27 e M28 ----------------------------------------


def test_t_a12_trilha_do_recebimento_nao_guarda_o_nome_do_arquivo(cenario):
    """A12: o nome pode trazer CNPJ ou nome de cliente. A trilha guarda só a extensão."""
    nome = "12345678000199-cliente-segredo.txt"
    _receber_proprio(cenario["empresa"], *_par(1), nome=nome)

    trilha = RegistroAuditoria.objects.get(acao="lancamentos.importacao.recebida")
    assert trilha.detalhes["extensao"] == ".txt"
    assert "nome_arquivo" not in trilha.detalhes
    assert "12345678000199" not in str(trilha.detalhes)
    assert "segredo" not in str(trilha.detalhes)


def test_m27_efetivar_reconfere_e_recusa_competencia_fechada_depois_do_recebimento(cenario):
    """M27: entre o recebimento e a efetivação a competência é encerrada. A efetivação
    reconfere e recusa."""
    empresa = cenario["empresa"]
    importacao = _receber_proprio(empresa, *_par(1))
    _aceitar_arquivo(importacao)
    encerrar_competencia(empresa=empresa, ano=2026, mes=3, usuario=None)

    with pytest.raises(servico.ImportacaoNaoEfetivada) as excinfo:
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    assert any("competência 03/2026" in o["mensagem"] for o in excinfo.value.ocorrencias)
    assert not _diario(empresa).exists()


def test_m28_aceite_do_aviso_cai_quando_o_conjunto_de_avisos_muda(cenario):
    """M28: aceito o aviso de histórico, um lançamento igual entra no Diário. O aviso
    novo derruba o aceite."""
    empresa = cenario["empresa"]
    contas = cenario["contas"]
    importacao = _receber_proprio(
        empresa,
        "1;2026-03-10;Compra;1.1.1;D;100.00",
        "1;2026-03-10;Pagamento;2.1;C;100.00",
    )
    _aceitar_arquivo(importacao)
    assert importacao.lancamentos.get().tem_aviso is True
    servico.aceitar_avisos(importacao, ["1"], usuario=None)
    assert importacao.lancamentos.get().aceito_com_aviso is True

    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 10),
        historico="Compra | Pagamento",
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": contas["2.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    importacao = servico.reconferir(importacao, usuario=None)

    linha = importacao.lancamentos.get()
    assert any(o["campo"] == "duplicidade" for o in linha.ocorrencias)
    assert linha.aceito_com_aviso is False
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert (
        LancamentoImportado.objects.filter(importacao=importacao, lancamento__isnull=False).count()
        == 0
    )
