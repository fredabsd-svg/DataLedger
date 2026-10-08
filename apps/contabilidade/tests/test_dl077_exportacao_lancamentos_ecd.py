"""DL-077, fatia 2: exportação de lançamentos e saldos no leiaute da ECD (I150, I155, I200, I250).

Dois grupos. O primeiro usa o banco e o cenário sintético de `cenario_dl077_exportacao`, e o
ESPERADO é escrito à mão, linha por linha e campo por campo, a partir dos números do cenário.
O segundo testa o escritor sozinho, sem banco, com lançamentos e saldos montados à mão.

Índices de campo: `linha.split("|")` começa com um campo vazio (antes do primeiro `|`). Por isso
REG é o índice 1, e o primeiro campo de dados é o 2. As páginas citadas são as IMPRESSAS no
rodapé do Leiaute 9 (ADE Cofis 01/2026). O texto do manual não é copiado (RC-167).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.intercambio.canonico import LADO_CREDITO, LADO_DEBITO, IntercambioRecusado
from apps.contabilidade.intercambio.formatos import ecd_lancamentos
from apps.contabilidade.intercambio.lancamentos import ExportacaoRecusada, exportar_lancamentos
from apps.contabilidade.intercambio.lancamentos_canonico import (
    LancamentoParaExportar,
    PartidaParaExportar,
    PeriodoDeSaldo,
    SaldoDaConta,
)
from apps.contabilidade.models import Conta, ItemLancamento, TipoPartida
from apps.contabilidade.services import apurar_balancete
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    criar_empresa,
    criar_escritorio,
    criar_plano,
    montar_cenario_de_referencia,
)

D = Decimal
INICIO = date(2026, 1, 1)
FIM = date(2026, 3, 31)

pytestmark = pytest.mark.django_db


def _linhas(conteudo):
    """Linhas do arquivo, sem a última quebra. Decodificadas em ISO-8859-1, como o leiaute pede."""
    return [linha for linha in conteudo.decode("iso-8859-1").split("\r\n") if linha != ""]


def _campos(linha):
    return linha.split("|")


def _i155_por_mes(linhas):
    """{mmaaaa: [campos de cada I155 do mês]}. O mês vem do DT_INI do I150 (campo 2, ddmmaaaa)."""
    por_mes = {}
    mes = None
    for linha in linhas:
        if linha.startswith("|I150|"):
            mes = _campos(linha)[2][2:]
            por_mes[mes] = []
        elif linha.startswith("|I155|"):
            por_mes[mes].append(_campos(linha))
    return por_mes


def _com_sinal(valor_texto, indicador):
    numero = D(valor_texto.replace(",", "."))
    return numero if indicador == "D" else -numero


def _texto(valor):
    return f"{valor:.2f}".replace(".", ",")


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório ECD", "11111111000111")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa ECD Ltda", cnpj="77777777000177"
    )
    contas = criar_plano(empresa)
    lancamentos = montar_cenario_de_referencia(empresa, contas)
    return {"empresa": empresa, "contas": contas, **lancamentos}


def _esperado(c):
    """As linhas da ECD para o cenário com saldos de janeiro a março de 2026, escritas à mão.

    I155: COD_CTA, COD_CCUS (vazio), VL_SLD_INI, IND_DC_INI, VL_DEB, VL_CRED, VL_SLD_FIN,
          IND_DC_FIN.
    I200: NUM_LCTO, DT_LCTO, VL_LCTO, IND_LCTO, DT_LCTO_EXT (vazio).
    I250: COD_CTA, COD_CCUS (vazio), VL_DC, IND_DC, NUM_ARQ (vazio), COD_HIST_PAD (vazio),
          HIST, COD_PART (vazio).
    """
    l1, l2, l3, l4, e = c["l1"].pk, c["l2"].pk, c["l3"].pk, c["l4"].pk, c["estorno"].pk
    l5, z = c["l5"].pk, c["zeramento"].pk
    return [
        "|I150|01012026|31012026|",
        "|I155|1.1.1||0,00|D|1000,00|0,00|1000,00|D|",
        "|I155|5.1||0,00|D|0,00|1000,00|1000,00|C|",
        "|I150|01022026|28022026|",
        "|I155|1.1.1||1000,00|D|500,00|200,00|1300,00|D|",
        "|I155|2.1||0,00|D|0,00|100,00|100,00|C|",
        "|I155|3.1||0,00|D|0,00|500,00|500,00|C|",
        "|I155|4.1||0,00|D|300,00|0,00|300,00|D|",
        "|I155|5.1||1000,00|C|0,00|0,00|1000,00|C|",
        "|I150|01032026|31032026|",
        "|I155|1.1.1||1300,00|D|10,00|500,00|810,00|D|",
        "|I155|1.1.2||0,00|D|170,00|0,00|170,00|D|",
        "|I155|2.1||100,00|C|0,00|215,00|315,00|C|",
        "|I155|3.1||500,00|C|515,00|15,00|0,00|D|",
        "|I155|4.1||300,00|D|50,00|350,00|0,00|D|",
        "|I155|5.1||1000,00|C|335,00|0,00|665,00|C|",
        f"|I200|{l1}|10012026|1000,00|N||",
        "|I250|1.1.1||1000,00|D|||Aporte de capital||",
        "|I250|5.1||1000,00|C|||Aporte de capital||",
        f"|I200|{l2}|05022026|500,00|N||",
        "|I250|1.1.1||500,00|D|||Venda à vista||",
        "|I250|3.1||500,00|C|||Venda à vista||",
        f"|I200|{l3}|20022026|300,00|N||",
        "|I250|4.1||300,00|D|||Pagamento de aluguel e luz||",
        "|I250|1.1.1||200,00|C|||Pagamento de aluguel e luz||",
        "|I250|2.1||100,00|C|||Pagamento de aluguel e luz||",
        f"|I200|{l4}|03032026|200,00|N||",
        '|I250|1.1.2||150,00|D|||Compra a prazo; fornecedor "Alfa"||',
        '|I250|4.1||50,00|D|||Compra a prazo; fornecedor "Alfa"||',
        '|I250|2.1||200,00|C|||Compra a prazo; fornecedor "Alfa"||',
        f"|I200|{e}|04032026|500,00|N||",
        # A ordem das partidas do estorno é a do lançamento gravado (o reverso do original).
        "|I250|1.1.1||500,00|C|||Estorno: Venda à vista||",
        "|I250|3.1||500,00|D|||Estorno: Venda à vista||",
        f"|I200|{l5}|15032026|30,00|N||",
        "|I250|1.1.1||10,00|D|||Operação com dois e dois||",
        "|I250|1.1.2||20,00|D|||Operação com dois e dois||",
        "|I250|3.1||15,00|C|||Operação com dois e dois||",
        "|I250|2.1||15,00|C|||Operação com dois e dois||",
        f"|I200|{z}|31032026|350,00|E||",
        "|I250|3.1||15,00|D|||Encerramento do resultado||",
        "|I250|5.1||335,00|D|||Encerramento do resultado||",
        "|I250|4.1||350,00|C|||Encerramento do resultado||",
    ]


def _exportar_ecd(empresa, **extra):
    return exportar_lancamentos(
        empresa=empresa,
        formato="ecd",
        data_inicial=INICIO,
        data_final=FIM,
        incluir_saldos=True,
        **extra,
    )


# -----------------------------------------------------------------------------
# Arquivo gerado a partir do banco
# -----------------------------------------------------------------------------


def test_arquivo_com_saldos_sai_linha_a_linha_como_o_esperado_escrito_a_mao(cenario):
    arquivo = _exportar_ecd(cenario["empresa"])

    assert _linhas(arquivo.conteudo) == _esperado(cenario)
    assert arquivo.conteudo.endswith(b"\r\n")


def test_zeramento_sai_com_ind_lcto_e_os_demais_com_n(cenario):
    """IND_LCTO (I200, campo 05, p. 143): E para o encerramento do resultado, N para os demais."""
    linhas = _linhas(_exportar_ecd(cenario["empresa"]).conteudo)
    indicadores = {
        _campos(linha)[2]: _campos(linha)[5] for linha in linhas if linha.startswith("|I200|")
    }

    assert indicadores[str(cenario["zeramento"].pk)] == "E"
    assert sorted(indicadores.values()) == ["E"] + ["N"] * 6


def test_estorno_sai_como_lancamento_normal_com_o_proprio_historico(cenario):
    linhas = _linhas(_exportar_ecd(cenario["empresa"]).conteudo)
    estorno = str(cenario["estorno"].pk)

    assert f"|I200|{estorno}|04032026|500,00|N||" in linhas
    assert "|I250|3.1||500,00|D|||Estorno: Venda à vista||" in linhas


def test_lancamentos_saem_por_data_e_depois_por_numero(cenario):
    linhas = _linhas(_exportar_ecd(cenario["empresa"]).conteudo)
    cabecalhos = [linha for linha in linhas if linha.startswith("|I200|")]
    numeros = [_campos(linha)[2] for linha in cabecalhos]
    datas = [
        date(int(_campos(linha)[3][4:8]), int(_campos(linha)[3][2:4]), int(_campos(linha)[3][:2]))
        for linha in cabecalhos
    ]

    assert numeros == [
        str(cenario[chave].pk) for chave in ("l1", "l2", "l3", "l4", "estorno", "l5", "zeramento")
    ]
    assert datas == sorted(datas)


def _soma_dos_itens(empresa, conta, mes_ini, mes_fim, *, ate_o_fim_do_mes):
    """(débitos, créditos) de uma conta, lidos direto dos itens, sem o escritor nem o balancete."""
    filtro = {"conta": conta, "lancamento__empresa": empresa}
    if ate_o_fim_do_mes:
        periodo = ItemLancamento.objects.filter(lancamento__data__lt=mes_ini, **filtro)
    else:
        periodo = ItemLancamento.objects.filter(
            lancamento__data__gte=mes_ini, lancamento__data__lte=mes_fim, **filtro
        )
    debitos = sum((i.valor for i in periodo if i.tipo == TipoPartida.DEBITO), D("0"))
    creditos = sum((i.valor for i in periodo if i.tipo == TipoPartida.CREDITO), D("0"))
    return debitos, creditos


def test_saldos_conferem_com_os_itens_lidos_direto_do_banco(cenario):
    """Conciliação independente: cada I155 é recalculado a partir dos ITENS, por conta e mês.

    O saldo inicial de um mês é a soma dos itens ANTERIORES ao mês. Conta sem saldo nem
    movimento não sai no arquivo, e o teste confere isso nos dois sentidos.
    """
    empresa = cenario["empresa"]
    por_mes = _i155_por_mes(_linhas(_exportar_ecd(empresa).conteudo))
    meses = {
        "012026": (date(2026, 1, 1), date(2026, 1, 31)),
        "022026": (date(2026, 2, 1), date(2026, 2, 28)),
        "032026": (date(2026, 3, 1), date(2026, 3, 31)),
    }

    for mes, (mes_ini, mes_fim) in meses.items():
        lidos = {campos[2]: campos for campos in por_mes[mes]}
        for conta in Conta.objects.filter(empresa=empresa, aceita_lancamento=True):
            deb_antes, cred_antes = _soma_dos_itens(
                empresa, conta, mes_ini, mes_fim, ate_o_fim_do_mes=True
            )
            deb, cred = _soma_dos_itens(empresa, conta, mes_ini, mes_fim, ate_o_fim_do_mes=False)
            ini = deb_antes - cred_antes
            fim_saldo = ini + deb - cred
            if ini == 0 and deb == 0 and cred == 0:
                assert conta.codigo not in lidos, (mes, conta.codigo)
                continue
            campos = lidos[conta.codigo]
            assert campos[4] == _texto(abs(ini)), (mes, conta.codigo)
            assert campos[5] == ("C" if ini < 0 else "D"), (mes, conta.codigo)
            assert campos[6] == _texto(deb), (mes, conta.codigo)
            assert campos[7] == _texto(cred), (mes, conta.codigo)
            assert campos[8] == _texto(abs(fim_saldo)), (mes, conta.codigo)
            assert campos[9] == ("C" if fim_saldo < 0 else "D"), (mes, conta.codigo)


def test_i155_cumpre_as_regras_de_validacao_do_manual_no_arquivo_gerado(cenario):
    """Regras do I155 (p. 136-137), conferidas no ARQUIVO gerado, não no escritor."""
    por_mes = _i155_por_mes(_linhas(_exportar_ecd(cenario["empresa"]).conteudo))

    anterior = {}
    for mes, registros in por_mes.items():
        soma_ini = soma_fin = soma_deb = soma_cred = D("0")
        atual = {}
        inicial_do_mes = {}
        for campos in registros:
            conta = campos[2]
            ini = _com_sinal(campos[4], campos[5])
            deb = D(campos[6].replace(",", "."))
            cred = D(campos[7].replace(",", "."))
            fin = _com_sinal(campos[8], campos[9])
            assert fin == ini + deb - cred, (mes, conta)  # REGRA_VALIDACAO_SALDO_FINAL
            soma_ini += ini
            soma_fin += fin
            soma_deb += deb
            soma_cred += cred
            atual[conta] = fin
            inicial_do_mes[conta] = ini
        assert soma_ini == 0, mes  # REGRA_VALIDACAO_SOMA_SALDO_INICIAL
        assert soma_fin == 0, mes  # REGRA_VALIDACAO_SOMA_SALDO_FINAL
        assert soma_deb == soma_cred, mes  # REGRA_VALIDACAO_DEB_DIF_CRED
        for conta in set(anterior) | set(inicial_do_mes):
            # REGRA_VALIDACAO_SALDO_INI_DIF_FIN (p. 137): conta fora do mês vale zero.
            assert inicial_do_mes.get(conta, D("0")) == anterior.get(conta, D("0")), (mes, conta)
        anterior = atual


def test_soma_dos_debitos_e_creditos_dos_itens_do_arquivo_e_igual(cenario):
    """Partidas: D de um lado e C do outro (I250, campo 05). VL_LCTO = a soma de um lado (I200)."""
    linhas = _linhas(_exportar_ecd(cenario["empresa"]).conteudo)
    debitos = creditos = valor_do_cabecalho = D("0")
    for linha in linhas:
        campos = _campos(linha)
        if linha.startswith("|I250|"):
            if campos[5] == "D":
                debitos += D(campos[4].replace(",", "."))
            else:
                creditos += D(campos[4].replace(",", "."))
        elif linha.startswith("|I200|"):
            valor_do_cabecalho += D(campos[4].replace(",", "."))

    assert debitos == creditos == valor_do_cabecalho == D("2880.00")


def test_zero_sai_como_0_00_com_indicador_d_ou_c(cenario):
    """Saldo zero: VL com `0,00` e IND_DC obrigatório (p. 135). Vendas fecha março zerada."""
    linhas = _linhas(_exportar_ecd(cenario["empresa"]).conteudo)

    assert "|I155|3.1||500,00|C|515,00|15,00|0,00|D|" in linhas


def test_relatorio_de_conferencia_bate_com_o_cenario(cenario):
    arquivo = _exportar_ecd(cenario["empresa"])
    relatorio = arquivo.relatorio

    assert relatorio.quantidade_lancamentos == 7
    assert relatorio.quantidade_partidas == 19
    assert relatorio.quantidade_zeramentos == 1
    assert relatorio.quantidade_estornos == 1
    assert relatorio.soma_debitos == relatorio.soma_creditos == D("2880.00")
    assert relatorio.quantidade_meses == 3
    assert [c.codigo for c in relatorio.contas_usadas] == [
        "1.1.1",
        "1.1.2",
        "2.1",
        "3.1",
        "4.1",
        "5.1",
    ]
    assert relatorio.sha256 == arquivo.sha256
    assert len(arquivo.sha256) == 64
    assert relatorio.nome_do_arquivo == (
        "lancamentos-77777777000177-20260101-20260331-registros-I200-I150-I155.txt"
    )


def test_nome_do_arquivo_sem_saldos_e_o_arquivo_sem_os_registros_de_saldo(cenario):
    arquivo = exportar_lancamentos(
        empresa=cenario["empresa"],
        formato="ecd",
        data_inicial=INICIO,
        data_final=FIM,
        incluir_saldos=False,
    )

    nome = arquivo.relatorio.nome_do_arquivo
    assert nome == "lancamentos-77777777000177-20260101-20260331-registros-I200.txt"
    assert "ECD" not in nome and "SPED" not in nome
    assert _linhas(arquivo.conteudo) == [
        linha for linha in _esperado(cenario) if not linha.startswith(("|I150|", "|I155|"))
    ]


def test_conta_sintetica_com_lancamento_legado_e_recusada_nomeando_a_conta(cenario):
    """Estado legado: a conta tem lançamento mas perdeu a permissão. Não sai no I250 (p. 151)."""
    Conta.objects.filter(pk=cenario["contas"]["3.1"].pk).update(aceita_lancamento=False)

    with pytest.raises(ExportacaoRecusada) as excinfo:
        _exportar_ecd(cenario["empresa"])

    assert "conta 3.1" in excinfo.value.mensagem
    assert "REGRA_CONTA_PARA_LANCAMENTO" in excinfo.value.mensagem


def test_conta_com_lancamento_e_subordinadas_e_recusada_nomeando_a_conta(cenario):
    Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="1.1.1.1",
        nome="Caixa filha",
        conta_pai=cenario["contas"]["1.1.1"],
        aceita_lancamento=True,
        tipo="ativo",
        natureza="devedora",
    )

    with pytest.raises(ExportacaoRecusada) as excinfo:
        _exportar_ecd(cenario["empresa"])

    assert "conta 1.1.1" in excinfo.value.mensagem
    assert "subordinadas" in excinfo.value.mensagem


def test_saldo_do_i155_e_o_do_balancete_do_produto_com_sinal_debito_menos_credito(cenario):
    """Conciliação com o balancete: o saldo final é o de `apurar_balancete`, com sinal D − C."""
    empresa = cenario["empresa"]
    por_mes = _i155_por_mes(_linhas(_exportar_ecd(empresa).conteudo))
    balancete = apurar_balancete(empresa=empresa, inicio=date(2026, 3, 1), fim=date(2026, 3, 31))
    linha_do_balancete = next(linha for linha in balancete["contas"] if linha["conta"] == "1.1.1")
    campos = next(c for c in por_mes["032026"] if c[2] == "1.1.1")

    assert linha_do_balancete["saldo_final"] == D("810.00")  # Ativo, devedora
    assert _com_sinal(campos[8], campos[9]) == linha_do_balancete["saldo_final"]
    assert campos[6] == "10,00" and campos[7] == "500,00"


# -----------------------------------------------------------------------------
# O escritor sozinho (sem banco)
# -----------------------------------------------------------------------------


def _lancamento(numero, data, historico, partidas, *, zeramento=False):
    return LancamentoParaExportar(
        numero=numero,
        data=data,
        historico=historico,
        zeramento=zeramento,
        estorno=False,
        partidas=tuple(PartidaParaExportar(c, lado, D(v)) for c, lado, v in partidas),
    )


def _periodo(inicio, fim, *contas):
    return PeriodoDeSaldo(
        inicio=inicio,
        fim=fim,
        contas=tuple(
            SaldoDaConta(
                codigo_conta=codigo,
                saldo_inicial=D(ini),
                debitos=D(deb),
                creditos=D(cred),
                saldo_final=D(fin),
            )
            for codigo, ini, deb, cred, fin in contas
        ),
    )


def test_escritor_escreve_i200_e_i250_com_ind_lcto_normal_e_encerramento():
    normal = _lancamento(
        1,
        date(2026, 2, 3),
        "Compra",
        [("1.1", LADO_DEBITO, "10.50"), ("2.1", LADO_CREDITO, "10.50")],
    )
    encerramento = _lancamento(
        2,
        date(2026, 2, 28),
        "Encerramento",
        [("3.1", LADO_DEBITO, "1.00"), ("4.1", LADO_CREDITO, "1.00")],
        zeramento=True,
    )

    conteudo = ecd_lancamentos.escrever([normal, encerramento])

    assert _linhas(conteudo) == [
        "|I200|1|03022026|10,50|N||",
        "|I250|1.1||10,50|D|||Compra||",
        "|I250|2.1||10,50|C|||Compra||",
        "|I200|2|28022026|1,00|E||",
        "|I250|3.1||1,00|D|||Encerramento||",
        "|I250|4.1||1,00|C|||Encerramento||",
    ]


def test_escritor_usa_iso_8859_1_com_acentos_e_recusa_o_que_nao_existe_em_latin_1():
    com_acento = _lancamento(
        1,
        date(2026, 1, 5),
        "Descrição: ação",
        [("1", LADO_DEBITO, "1.00"), ("2", LADO_CREDITO, "1.00")],
    )

    conteudo = ecd_lancamentos.escrever([com_acento])
    assert "ação".encode("iso-8859-1") in conteudo  # ç e ã em Latin-1 (um byte cada), não UTF-8

    fora = _lancamento(
        2,
        date(2026, 1, 5),
        "Pago em € hoje",
        [("1", LADO_DEBITO, "1.00"), ("2", LADO_CREDITO, "1.00")],
    )
    with pytest.raises(IntercambioRecusado) as excinfo:
        ecd_lancamentos.escrever([fora])

    assert "ISO-8859-1" in excinfo.value.mensagem
    assert excinfo.value.ocorrencias[0].campo == "HIST"


def test_historico_com_pipe_e_recusado_nomeando_o_lancamento_e_o_campo():
    com_pipe = _lancamento(
        7,
        date(2026, 1, 5),
        "Parte A|Parte B",
        [("1", LADO_DEBITO, "1.00"), ("2", LADO_CREDITO, "1.00")],
    )

    with pytest.raises(IntercambioRecusado) as excinfo:
        ecd_lancamentos.escrever([com_pipe])

    ocorrencia = excinfo.value.ocorrencias[0]
    assert (ocorrencia.linha, ocorrencia.campo) == (7, "HIST")
    assert "'|'" in ocorrencia.mensagem


def test_lancamento_desbalanceado_no_escritor_e_recusado():
    """O banco já impede isto (partidas dobradas). O escritor confere de novo, como cinto."""
    torto = _lancamento(
        3,
        date(2026, 1, 5),
        "Torto",
        [("1", LADO_DEBITO, "1.00"), ("2", LADO_CREDITO, "0.90")],
    )

    with pytest.raises(IntercambioRecusado) as excinfo:
        ecd_lancamentos.escrever([torto])

    assert "REGRA_VALIDACAO_VL_LCTO_DEB" in excinfo.value.mensagem


def test_sem_lancamento_e_sem_saldo_o_arquivo_sai_vazio():
    assert ecd_lancamentos.escrever([]) == b""


def test_escritor_recusa_periodo_cuja_soma_do_saldo_inicial_nao_e_zero():
    periodo = _periodo(
        date(2026, 1, 1), date(2026, 1, 31), ("1.1", "10.00", "0.00", "0.00", "10.00")
    )

    with pytest.raises(IntercambioRecusado) as excinfo:
        ecd_lancamentos.escrever([], [periodo], incluir_saldos=True)

    assert "REGRA_VALIDACAO_SOMA_SALDO_INICIAL" in excinfo.value.mensagem


def test_escritor_recusa_saldo_final_que_nao_e_inicial_mais_movimento():
    periodo = _periodo(
        date(2026, 1, 1),
        date(2026, 1, 31),
        ("1.1", "0.00", "10.00", "0.00", "9.00"),
        ("2.1", "0.00", "0.00", "10.00", "-10.00"),
    )

    with pytest.raises(IntercambioRecusado) as excinfo:
        ecd_lancamentos.escrever([], [periodo], incluir_saldos=True)

    assert "REGRA_VALIDACAO_SALDO_FINAL" in excinfo.value.mensagem


def test_escritor_recusa_saldo_inicial_de_mes_que_nao_e_o_final_do_anterior():
    janeiro = _periodo(
        date(2026, 1, 1),
        date(2026, 1, 31),
        ("1.1", "0.00", "10.00", "0.00", "10.00"),
        ("2.1", "0.00", "0.00", "10.00", "-10.00"),
    )
    fevereiro = _periodo(
        date(2026, 2, 1),
        date(2026, 2, 28),
        ("1.1", "0.00", "0.00", "0.00", "0.00"),
        ("2.1", "0.00", "0.00", "0.00", "0.00"),
    )

    with pytest.raises(IntercambioRecusado) as excinfo:
        ecd_lancamentos.escrever([], [janeiro, fevereiro], incluir_saldos=True)

    assert "REGRA_VALIDACAO_SALDO_INI_DIF_FIN" in excinfo.value.mensagem


def test_zero_no_i155_sai_como_0_00_e_indicador_d_pela_convencao():
    """O manual exige D ou C para o zero e não escolhe. O escritor usa D (convenção)."""
    periodo = _periodo(date(2026, 1, 1), date(2026, 1, 31), ("1.1", "0.00", "5.00", "5.00", "0.00"))

    linhas = _linhas(ecd_lancamentos.escrever([], [periodo], incluir_saldos=True))

    assert linhas == [
        "|I150|01012026|31012026|",
        "|I155|1.1||0,00|D|5,00|5,00|0,00|D|",
    ]
