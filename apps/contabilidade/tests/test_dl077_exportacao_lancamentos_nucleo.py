"""DL-077, fatia 2: núcleo da exportação de lançamentos (intervalo, parâmetros, isolamento,
formato próprio, sistema de referência, relatório de conferência).

Usa o cenário sintético de `cenario_dl077_exportacao`. O esperado de cada formato é escrito à mão
neste arquivo, campo por campo. Dados fictícios.

Sobre o sistema de referência: o produto NÃO tem o número de casas decimais do valor do 6100
declarado no manual (ver `referencia_lancamentos`). Por isso, a exportação pelo produto é recusada.
Os testes que querem o ARQUIVO do sistema de referência injetam 2 casas com `monkeypatch`, e isso é
teste do mecanismo, não afirmação sobre o manual.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.contabilidade.intercambio import lancamentos as nucleo
from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    ContaLida,
    IntercambioRecusado,
)
from apps.contabilidade.intercambio.formatos import referencia, referencia_lancamentos
from apps.contabilidade.intercambio.lancamentos import (
    ExportacaoRecusada,
    _carregar_lancamentos,
    exportar_lancamentos,
)
from apps.contabilidade.intercambio.lancamentos_canonico import (
    LancamentoParaExportar,
    PartidaParaExportar,
)
from apps.contabilidade.intercambio.plano import ParametroInvalido
from apps.contabilidade.models import Conta
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    CNPJ_DA_OUTRA_EMPRESA,
    PLANO,
    criar_empresa,
    criar_escritorio,
    criar_plano,
    lancar,
    montar_cenario_de_referencia,
)

D = Decimal
INICIO = date(2026, 1, 1)
FIM = date(2026, 3, 31)

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório Núcleo", "22222222000122")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Núcleo Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    lancamentos = montar_cenario_de_referencia(empresa, contas)
    return {"escritorio": escritorio, "empresa": empresa, "contas": contas, **lancamentos}


@pytest.fixture
def casas_declaradas(monkeypatch):
    """Injeta 2 casas no valor do 6100, só para testar o MECANISMO do sistema de referência."""
    monkeypatch.setattr(nucleo, "CASAS_DECIMAIS_DO_VALOR_6100", 2)


def _exportar(empresa, formato, inicio=INICIO, fim=FIM, **extra):
    return exportar_lancamentos(
        empresa=empresa, formato=formato, data_inicial=inicio, data_final=fim, **extra
    )


def _linhas(conteudo, codificacao="utf-8"):
    return [linha for linha in conteudo.decode(codificacao).split("\r\n") if linha != ""]


# -----------------------------------------------------------------------------
# Intervalo e parâmetros
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "inicio, fim, mensagem",
    [
        (None, FIM, "informe a data inicial e a final"),
        (INICIO, None, "informe a data inicial e a final"),
        (FIM, INICIO, "posterior à data final"),
        (date(2026, 1, 1), date(2027, 1, 2), "367 dias; o máximo por arquivo é 366"),
    ],
)
def test_intervalo_obrigatorio_ordenado_e_de_no_maximo_um_ano(cenario, inicio, fim, mensagem):
    with pytest.raises(ParametroInvalido) as excinfo:
        _exportar(cenario["empresa"], "proprio", inicio=inicio, fim=fim)

    assert mensagem in excinfo.value.mensagem


def test_intervalo_de_366_dias_e_aceito_e_o_de_367_e_recusado(cenario):
    # 2027-01-01 a 2028-01-01 são 366 dias corridos, contando os dois extremos.
    aceito = _exportar(cenario["empresa"], "proprio", inicio=date(2027, 1, 1), fim=date(2028, 1, 1))
    assert aceito.relatorio.quantidade_lancamentos == 0

    with pytest.raises(ParametroInvalido):
        _exportar(cenario["empresa"], "proprio", inicio=date(2027, 1, 1), fim=date(2028, 1, 2))


def test_formato_desconhecido_ou_de_so_importacao_e_recusado(cenario):
    with pytest.raises(ParametroInvalido) as excinfo:
        _exportar(cenario["empresa"], "excel")
    assert "não existe para a exportação de lançamentos" in excinfo.value.mensagem

    with pytest.raises(ParametroInvalido):
        _exportar(cenario["empresa"], "")

    assert nucleo.FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS == ("ecd", "proprio", "referencia")


def test_saldos_so_existem_na_ecd(cenario):
    with pytest.raises(ParametroInvalido) as excinfo:
        _exportar(cenario["empresa"], "proprio", incluir_saldos=True)
    assert "existem só no leiaute da ECD" in excinfo.value.mensagem


def test_saldos_exigem_meses_inteiros(cenario):
    with pytest.raises(ParametroInvalido) as excinfo:
        _exportar(
            cenario["empresa"],
            "ecd",
            inicio=date(2026, 1, 15),
            fim=date(2026, 3, 31),
            incluir_saldos=True,
        )
    assert "por mês inteiro" in excinfo.value.mensagem

    with pytest.raises(ParametroInvalido):
        _exportar(
            cenario["empresa"],
            "ecd",
            inicio=date(2026, 1, 1),
            fim=date(2026, 3, 30),
            incluir_saldos=True,
        )


def test_omitir_nao_representaveis_so_existe_no_sistema_de_referencia(cenario):
    with pytest.raises(ParametroInvalido) as excinfo:
        _exportar(cenario["empresa"], "proprio", omitir_nao_representaveis=True)
    assert "só existe no leiaute do sistema de referência" in excinfo.value.mensagem


def test_lancamentos_fora_do_intervalo_nao_entram(cenario):
    empresa = cenario["empresa"]
    lancar(
        empresa,
        cenario["contas"],
        date(2025, 12, 31),
        "Antes do período",
        [("1.1.1", "77.00")],
        [("5.1", "77.00")],
    )
    lancar(
        empresa,
        cenario["contas"],
        date(2026, 4, 1),
        "Depois do período",
        [("1.1.1", "88.00")],
        [("5.1", "88.00")],
    )

    arquivo = _exportar(empresa, "proprio")
    conteudo = arquivo.conteudo.decode("utf-8")

    assert "Antes do período" not in conteudo
    assert "Depois do período" not in conteudo
    assert arquivo.relatorio.quantidade_lancamentos == 7


# -----------------------------------------------------------------------------
# Isolamento entre empresas
# -----------------------------------------------------------------------------


def test_lancamento_de_outra_empresa_nao_sai_nem_no_arquivo_nem_no_relatorio(cenario):
    outra = criar_empresa(
        escritorio=cenario["escritorio"],
        razao_social="Outra Núcleo Ltda",
        cnpj=CNPJ_DA_OUTRA_EMPRESA,
    )
    lancar(
        outra,
        criar_plano(outra),
        date(2026, 2, 10),
        "Lançamento SÓ da outra empresa",
        [("1.1.1", "9999.00")],
        [("5.1", "9999.00")],
    )

    arquivo = _exportar(cenario["empresa"], "proprio")

    assert "Lançamento SÓ da outra empresa" not in arquivo.conteudo.decode("utf-8")
    assert arquivo.relatorio.quantidade_lancamentos == 7
    assert arquivo.relatorio.soma_debitos == D("2880.00")


def test_codigo_reduzido_nao_mistura_contas_de_outra_empresa(cenario, casas_declaradas):
    """Conta de outra empresa, com código que viria antes, não pode deslocar o reduzido daqui."""
    outra = criar_empresa(
        escritorio=cenario["escritorio"],
        razao_social="Outra Núcleo Ltda",
        cnpj=CNPJ_DA_OUTRA_EMPRESA,
    )
    Conta.objects.create(
        empresa=outra,
        codigo="0.0.0",
        nome="Conta só da outra",
        aceita_lancamento=True,
        tipo="ativo",
        natureza="devedora",
    )

    arquivo = _exportar(cenario["empresa"], "referencia", omitir_nao_representaveis=True)

    reduzidos = {c.codigo: c.codigo_reduzido for c in arquivo.relatorio.contas_usadas}
    assert "0.0.0" not in reduzidos
    assert reduzidos["1.1.1"] == 3  # 1, 1.1, 1.1.1: o reduzido de Caixa no plano desta empresa


# -----------------------------------------------------------------------------
# Formato próprio
# -----------------------------------------------------------------------------


def test_formato_proprio_sai_linha_a_linha_como_o_esperado_escrito_a_mao(cenario):
    c = cenario
    esperado = [
        "numero;data;historico;conta;lado;valor",
        f"{c['l1'].pk};2026-01-10;Aporte de capital;1.1.1;D;1000.00",
        f"{c['l1'].pk};2026-01-10;Aporte de capital;5.1;C;1000.00",
        f"{c['l2'].pk};2026-02-05;Venda à vista;1.1.1;D;500.00",
        f"{c['l2'].pk};2026-02-05;Venda à vista;3.1;C;500.00",
        f"{c['l3'].pk};2026-02-20;Pagamento de aluguel e luz;4.1;D;300.00",
        f"{c['l3'].pk};2026-02-20;Pagamento de aluguel e luz;1.1.1;C;200.00",
        f"{c['l3'].pk};2026-02-20;Pagamento de aluguel e luz;2.1;C;100.00",
        f'{c["l4"].pk};2026-03-03;"Compra a prazo; fornecedor ""Alfa""";1.1.2;D;150.00',
        f'{c["l4"].pk};2026-03-03;"Compra a prazo; fornecedor ""Alfa""";4.1;D;50.00',
        f'{c["l4"].pk};2026-03-03;"Compra a prazo; fornecedor ""Alfa""";2.1;C;200.00',
        # Ordem das partidas do estorno: a do lançamento gravado, que é o reverso do original.
        f"{c['estorno'].pk};2026-03-04;Estorno: Venda à vista;1.1.1;C;500.00",
        f"{c['estorno'].pk};2026-03-04;Estorno: Venda à vista;3.1;D;500.00",
        f"{c['l5'].pk};2026-03-15;Operação com dois e dois;1.1.1;D;10.00",
        f"{c['l5'].pk};2026-03-15;Operação com dois e dois;1.1.2;D;20.00",
        f"{c['l5'].pk};2026-03-15;Operação com dois e dois;3.1;C;15.00",
        f"{c['l5'].pk};2026-03-15;Operação com dois e dois;2.1;C;15.00",
        f"{c['zeramento'].pk};2026-03-31;Encerramento do resultado;3.1;D;15.00",
        f"{c['zeramento'].pk};2026-03-31;Encerramento do resultado;5.1;D;335.00",
        f"{c['zeramento'].pk};2026-03-31;Encerramento do resultado;4.1;C;350.00",
    ]

    arquivo = _exportar(c["empresa"], "proprio")

    assert _linhas(arquivo.conteudo) == esperado
    assert arquivo.conteudo.endswith(b"\r\n")
    assert not arquivo.conteudo.startswith(b"\xef\xbb\xbf")  # sem BOM, na escrita


def test_formato_proprio_valor_com_ponto_e_duas_casas_nunca_com_virgula(cenario):
    """Lê com o leitor CSV, porque o histórico do cenário tem `;` entre aspas (RFC 4180)."""
    import csv
    import io

    arquivo = _exportar(cenario["empresa"], "proprio")
    linhas = list(csv.reader(io.StringIO(arquivo.conteudo.decode("utf-8")), delimiter=";"))
    valores = [linha[5] for linha in linhas[1:]]

    assert len(valores) == 19  # uma linha por partida
    assert all(len(linha) == 6 for linha in linhas)
    assert all("," not in valor for valor in valores)
    assert all(len(valor.split(".")[1]) == 2 for valor in valores)
    assert '"Compra a prazo; fornecedor ""Alfa"""' in arquivo.conteudo.decode("utf-8")


def test_nome_do_arquivo_do_formato_proprio_nao_diz_ecd(cenario):
    nome = _exportar(cenario["empresa"], "proprio").relatorio.nome_do_arquivo

    assert nome == "lancamentos-77777777000177-20260101-20260331-formato-dataledger.txt"


def test_relatorio_do_formato_proprio_confere_debitos_com_creditos(cenario):
    relatorio = _exportar(cenario["empresa"], "proprio").relatorio

    assert relatorio.quantidade_lancamentos == 7
    assert relatorio.quantidade_partidas == 19
    assert relatorio.soma_debitos == relatorio.soma_creditos == D("2880.00")
    assert relatorio.omitidos == ()
    assert relatorio.avisos == ()


def test_trilha_guarda_contagens_intervalo_e_sha_e_nao_guarda_o_nome_do_arquivo(cenario):
    relatorio = _exportar(cenario["empresa"], "proprio").relatorio

    trilha = relatorio.para_trilha()

    assert trilha["sha256"] == relatorio.sha256
    assert trilha["inicio"] == "2026-01-01"
    assert trilha["fim"] == "2026-03-31"
    assert trilha["quantidade_lancamentos"] == 7
    assert trilha["soma_debitos"] == "2880.00"
    assert "nome_do_arquivo" not in trilha
    assert "77777777000177" not in repr(trilha)


def test_autor_do_relatorio_e_o_nome_do_usuario_ou_sistema(cenario):
    usuario = get_user_model().objects.create_user(
        username="contador-nucleo",
        email="contador-nucleo@escritorio.com.br",
        password="senha-forte-123",
        first_name="Contador",
        last_name="Teste",
    )

    assert _exportar(cenario["empresa"], "proprio", usuario=usuario).relatorio.autor == (
        "Contador Teste"
    )
    assert _exportar(cenario["empresa"], "proprio").relatorio.autor == "sistema"


# -----------------------------------------------------------------------------
# Sistema de referência (0000, 6000, 6100)
# -----------------------------------------------------------------------------


def test_nm_no_sistema_de_referencia_recusa_a_exportacao_listando_o_lancamento(cenario):
    """N×M não tem decomposição única: o pareamento seria invenção. A recusa lista o lançamento."""
    with pytest.raises(IntercambioRecusado) as excinfo:
        _exportar(cenario["empresa"], "referencia")

    mensagem = excinfo.value.mensagem
    assert f"lançamento {cenario['l5'].pk} (15/03/2026, 2 débitos × 2 créditos)" in mensagem
    assert "Nenhum arquivo foi gerado" in mensagem
    assert [o.linha for o in excinfo.value.ocorrencias] == [cenario["l5"].pk]


def test_com_as_casas_do_produto_1x1_sai_no_sistema_de_referencia_com_virgula(cenario):
    """DL-077 fatia 3: 6100 com 2 casas declaradas (decisão do arquiteto). Valor em vírgula."""
    assert nucleo.CASAS_DECIMAIS_DO_VALOR_6100 == 2
    empresa = criar_empresa(
        escritorio=cenario["escritorio"],
        razao_social="Empresa Só 1x1 Ltda",
        cnpj=CNPJ_DA_OUTRA_EMPRESA,
    )
    contas = criar_plano(empresa)
    lancar(
        empresa,
        contas,
        date(2026, 1, 10),
        "Só um para um",
        [("1.1.1", "1234.56")],
        [("5.1", "1234.56")],
    )

    arquivo = _exportar(empresa, "referencia")

    linhas = arquivo.conteudo.decode("iso-8859-1").split("\r\n")
    assert "|6100|10/01/2026|3|12|1234,56||Só um para um||||" in linhas


def test_escritor_de_referencia_com_casas_declaradas_escreve_o_layout_escrito_a_mao(cenario):
    """Mecanismo: com as casas injetadas, o escritor segue o layout descrito no módulo.

    0000 com o documento; um 6000 por lançamento (tipo X, D ou C); um 6100 por par de contas
    (valor com vírgula decimal, 2 casas, e `|` nas pontas); o N×M omitido e listado.
    O código reduzido é o do
    plano inteiro (1, 1.1, 1.1.1, ... 5.1 -> 12).
    """
    empresa = cenario["empresa"]
    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    lancamentos = _carregar_lancamentos(empresa, INICIO, FIM, {conta.pk: conta for conta in contas})

    conteudo, omitidos = referencia_lancamentos.escrever(
        lancamentos,
        documento=CNPJ_DA_EMPRESA,
        codigos_reduzidos=referencia_lancamentos.codigos_reduzidos(c.codigo for c in contas),
        casas_decimais_do_valor=2,
        omitir_nao_representaveis=True,
    )

    assert [o.numero for o in omitidos] == [cenario["l5"].pk]
    assert _linhas(conteudo, "iso-8859-1") == [
        "|0000|77777777000177|",
        "|6000|X||||",
        "|6100|10/01/2026|3|12|1000,00||Aporte de capital||||",
        "|6000|X||||",
        "|6100|05/02/2026|3|8|500,00||Venda à vista||||",
        "|6000|D||||",
        "|6100|20/02/2026|10|3|200,00||Pagamento de aluguel e luz||||",
        "|6100|20/02/2026|10|6|100,00||Pagamento de aluguel e luz||||",
        "|6000|C||||",
        '|6100|03/03/2026|4|6|150,00||Compra a prazo; fornecedor "Alfa"||||',
        '|6100|03/03/2026|10|6|50,00||Compra a prazo; fornecedor "Alfa"||||',
        "|6000|X||||",
        "|6100|04/03/2026|8|3|500,00||Estorno: Venda à vista||||",
        "|6000|C||||",
        "|6100|31/03/2026|8|10|15,00||Encerramento do resultado||||",
        "|6100|31/03/2026|12|10|335,00||Encerramento do resultado||||",
    ]


def test_escritor_de_referencia_sem_omitir_recusa_o_nm_mesmo_com_as_casas(cenario):
    empresa = cenario["empresa"]
    contas = list(Conta.objects.filter(empresa=empresa))
    lancamentos = _carregar_lancamentos(empresa, INICIO, FIM, {c.pk: c for c in contas})

    with pytest.raises(IntercambioRecusado) as excinfo:
        referencia_lancamentos.escrever(
            lancamentos,
            documento=CNPJ_DA_EMPRESA,
            codigos_reduzidos=referencia_lancamentos.codigos_reduzidos(c.codigo for c in contas),
            casas_decimais_do_valor=2,
        )

    assert f"lançamento {cenario['l5'].pk}" in excinfo.value.mensagem


def test_exportacao_de_referencia_com_as_casas_injetadas_sai_com_o_relatorio(
    cenario, casas_declaradas
):
    arquivo = _exportar(cenario["empresa"], "referencia", omitir_nao_representaveis=True)

    relatorio = arquivo.relatorio
    assert [o.numero for o in relatorio.omitidos] == [cenario["l5"].pk]
    assert relatorio.omitidos[0].quantidade_debitos == 2
    assert relatorio.omitidos[0].quantidade_creditos == 2
    assert relatorio.quantidade_lancamentos == 6
    assert relatorio.soma_debitos == relatorio.soma_creditos == D("2850.00")
    assert relatorio.nome_do_arquivo == (
        "lancamentos-77777777000177-20260101-20260331-leiaute-com-separador.txt"
    )
    assert relatorio.avisos and "Nao e a ECD" in relatorio.avisos[0]


def test_codigo_reduzido_do_produto_e_o_mesmo_do_0200_da_fatia_1():
    """O reduzido sai igual ao que o escritor do 0200 da fatia 1 grava para o mesmo plano."""
    contas_lidas = [
        ContaLida(
            linha=0,
            codigo=codigo,
            nome=nome,
            codigo_pai=pai,
            analitica=analitica,
            tipo=None,
            natureza=None,
            codigo_origem=None,
            referencial=None,
            ativa=True,
        )
        for codigo, nome, pai, analitica, _tipo, _natureza in PLANO
    ]
    conteudo_0200 = referencia.escrever(contas_lidas, documento=CNPJ_DA_EMPRESA)
    # Leiaute da fatia 1 corrigida: `|` nas pontas (`|0200|reduzido|codigo|...|`). Índice 0 é
    # o vazio antes da primeira barra; 1 é o REG; 2 o código reduzido; 3 o código da conta.
    reduzidos_do_0200 = {
        linha.split("|")[3]: int(linha.split("|")[2])
        for linha in _linhas(conteudo_0200, "iso-8859-1")
        if linha.startswith("|0200|")
    }

    proprio = referencia_lancamentos.codigos_reduzidos(codigo for codigo, *_ in PLANO)

    assert proprio == reduzidos_do_0200
    assert proprio["1.1.1"] == 3
    assert proprio["5.1"] == 12


def test_referencia_recusa_historico_com_pipe_e_o_que_nao_existe_em_latin_1():
    reduzidos = referencia_lancamentos.codigos_reduzidos(codigo for codigo, *_ in PLANO)

    def lancamento(historico):
        return LancamentoParaExportar(
            numero=9,
            data=date(2026, 1, 5),
            historico=historico,
            zeramento=False,
            estorno=False,
            partidas=(
                PartidaParaExportar("1.1.1", LADO_DEBITO, D("1.00")),
                PartidaParaExportar("5.1", LADO_CREDITO, D("1.00")),
            ),
        )

    with pytest.raises(IntercambioRecusado) as excinfo:
        referencia_lancamentos.escrever(
            [lancamento("Parte A|B")],
            documento=CNPJ_DA_EMPRESA,
            codigos_reduzidos=reduzidos,
            casas_decimais_do_valor=2,
        )
    assert excinfo.value.ocorrencias[0].campo == "histórico"

    with pytest.raises(IntercambioRecusado) as excinfo:
        referencia_lancamentos.escrever(
            [lancamento("Pago em € hoje")],
            documento=CNPJ_DA_EMPRESA,
            codigos_reduzidos=reduzidos,
            casas_decimais_do_valor=2,
        )
    assert "fora de ISO-8859-1" in excinfo.value.ocorrencias[0].mensagem


def test_referencia_recusa_sem_cnpj_no_0000():
    with pytest.raises(IntercambioRecusado) as excinfo:
        referencia_lancamentos.escrever(
            [], documento=None, codigos_reduzidos={}, casas_decimais_do_valor=2
        )
    assert "CNPJ ou CPF" in excinfo.value.mensagem


def test_valor_com_mais_casas_que_as_declaradas_e_recusado_e_nao_arredondado():
    reduzidos = referencia_lancamentos.codigos_reduzidos(codigo for codigo, *_ in PLANO)
    fino = LancamentoParaExportar(
        numero=3,
        data=date(2026, 1, 5),
        historico="Centavos",
        zeramento=False,
        estorno=False,
        partidas=(
            PartidaParaExportar("1.1.1", LADO_DEBITO, D("1.25")),
            PartidaParaExportar("5.1", LADO_CREDITO, D("1.25")),
        ),
    )

    with pytest.raises(IntercambioRecusado) as excinfo:
        referencia_lancamentos.escrever(
            [fino],
            documento=CNPJ_DA_EMPRESA,
            codigos_reduzidos=reduzidos,
            casas_decimais_do_valor=1,
        )

    assert "mais casas decimais" in excinfo.value.mensagem


def test_tipo_do_lote_pela_contagem_de_partidas():
    def lancamento(debitos, creditos):
        partidas = tuple(PartidaParaExportar("1", LADO_DEBITO, D("1.00")) for _ in range(debitos))
        partidas += tuple(
            PartidaParaExportar("2", LADO_CREDITO, D("1.00")) for _ in range(creditos)
        )
        return LancamentoParaExportar(
            numero=1,
            data=date(2026, 1, 1),
            historico="x",
            zeramento=False,
            estorno=False,
            partidas=partidas,
        )

    assert referencia_lancamentos.tipo_do_lote(lancamento(1, 1)) == "X"
    assert referencia_lancamentos.tipo_do_lote(lancamento(1, 3)) == "D"
    assert referencia_lancamentos.tipo_do_lote(lancamento(3, 1)) == "C"
    assert referencia_lancamentos.tipo_do_lote(lancamento(2, 2)) is None


def test_erro_do_nucleo_e_recusa_nomeada_e_nao_erro_nao_tratado(cenario):
    """Toda recusa do núcleo é `IntercambioRecusado`, para a API e a tela traduzirem em 400."""
    assert issubclass(ExportacaoRecusada, IntercambioRecusado)
    assert issubclass(ParametroInvalido, IntercambioRecusado)
