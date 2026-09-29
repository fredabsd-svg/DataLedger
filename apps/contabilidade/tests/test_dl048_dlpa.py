"""DL-048, etapas CTB-12 e CTB-13 — a Demonstração dos Lucros ou Prejuízos
Acumulados (DLPA): o campo `Conta.classificacao_dlpa` (molde de
`classificacao_patrimonial`/`classificacao_dre`), a apuração
(`apps.contabilidade.services.apurar_dlpa`), a decisão de emissão
(`avaliar_emissao_da_dlpa`), a porta de gravação (`classificar_conta_na_
dlpa`) e as DUAS telas (`dlpa` e `conta_classificacao_dlpa`).

Cobre os critérios do plano
(docs/planos/DL-048-contabilidade-anual-demonstracoes.md) desta fatia:

- caso de referência do plano (CTB-13): saldo inicial 0, lucro 25.000,00,
  reserva legal 1.250,00, dividendos 10.000,00 → saldo final 13.750,00;
- identidade `saldo inicial + Σ linhas = saldo final` (cada linha vem de
  lançamento identificável; sem pendência, vale por matemática);
- conciliação DLPA ↔ Balanço da mesma data (critério de aceite);
- nenhuma conta classificada por inferência: o que falta é DECLARADO e
  veta a emissão; linha desconhecida (ORM direto) também veta;
- direção do movimento decide reversão (art. 186, II) × transferência
  (art. 186, III) para a MESMA conta de reserva;
- compensação entre lucros e prejuízos (PE-38, ainda aberta) não é
  presumida: lançamento entre as duas contas sujeito tem efeito líquido
  zero e some da demonstração;
- isolamento entre empresas/escritórios, permissão de leitura e de
  escrita, e identificação NBC TG 26 item 51 na página emitida.

Os mapas derivados (títulos × enum, tipos aceitos × enum, listas de
pendência × chaves reais) existem no molde dos testes derivados da
DL-033/DL-045: enum novo sem entrada correspondente reprova o teste em
vez de sumir do documento.

Dados 100% sintéticos, criados nos próprios testes. Datas em 2026, sempre
no passado (hoje é 2026-09-28); exercício = ano civil (HI-28).
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    RESERVAS_DE_LUCROS_DA_DLPA,
    TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA,
    ClassificacaoDlpa,
    Conta,
    NaturezaConta,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    _LISTAS_DA_DLPA_QUE_IMPEDEM_A_EMISSAO,
    _LISTAS_DE_AVISO_DA_DLPA,
    _TITULOS_DAS_LINHAS_DA_DLPA,
    apurar_dlpa,
    avaliar_emissao_da_dlpa,
    classificar_conta_na_dlpa,
    criar_lancamento,
    estornar_lancamento,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA

ANO = 2026
MES = 3

_CONTADOR_DE_CNPJ = iter(range(51000000000000, 51000000009999))


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _conta(
    empresa,
    *,
    codigo,
    nome,
    tipo,
    natureza,
    pai=None,
    classificacao_dlpa=None,
):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_dlpa=classificacao_dlpa,
    )


def _lancar(empresa, data, historico, debito, credito, valor):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, username, papel=Papel.GESTOR):
    _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")


def _linhas_por_chave(dlpa):
    return {linha["chave"]: linha["valor"] for linha in dlpa["linhas"]}


def _chaves_em_ordem(dlpa):
    return [linha["chave"] for linha in dlpa["linhas"]]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_dlpa():
    """Plano mínimo com TODOS os eventos do art. 186 ocupados, números
    escolhidos para baterem com a identidade linha a linha:

    Saldo inicial (31/12/2025, contra o Caixa) ............ 800,00
    Ajuste de exercício anterior (20/03, contrapartida de
      tipo ATIVO — prova que "qualquer tipo" aceita) ....... 150,00
    Reversão de reserva legal (20/03) ...................... 300,00
    Lucro do exercício (16/03, transferência do "resultado") 25.000,00
    Transferência para reserva legal (16/03) ............. (1.250,00)
    Dividendos distribuídos (16/03) ..................... (10.000,00)
    Lucro incorporado ao capital (20/03) ................... (500,00)
    = Movimento do exercício ............................ 13.700,00
    = Saldo final (31/03/2026) .......................... 14.500,00

    Um lançamento de receita que NÃO toca a conta sujeito (Caixa ×
    Receita) fica de fora da leitura e gera o aviso de "resultado ainda
    não zerado" — nenhum lançamento desta base transfere resultado por
    parâmetro contábil; a transferência acima é manual, no mesmo formato
    que `zerar_resultado` grava.
    """
    escritorio = Escritorio.objects.create(nome="Escritório DL-048", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DLPA Completa Ltda",
        cnpj=_cnpj_sintetico(),
    )
    caixa = _conta(empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    resultado = _conta(
        empresa,
        codigo="3.0",
        nome="Resultado do Exercício",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.RESULTADO_DO_EXERCICIO,
    )
    lucros = _conta(
        empresa,
        codigo="3.1",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    )
    prejuizos = _conta(
        empresa,
        codigo="3.2",
        nome="(-) Prejuízos Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=D,
        classificacao_dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    )
    reserva = _conta(
        empresa,
        codigo="3.3",
        nome="Reserva Legal",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.RESERVA_LEGAL,
    )
    dividendos = _conta(
        empresa,
        codigo="2.1",
        nome="Dividendos a Pagar",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.DIVIDENDO,
    )
    capital = _conta(
        empresa,
        codigo="3.4",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL,
    )
    ajuste = _conta(
        empresa,
        codigo="1.2",
        nome="Ajuste de Exercícios Anteriores",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao_dlpa=ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR,
    )
    receita = _conta(empresa, codigo="4.1", nome="Receita", tipo=TipoConta.RECEITA, natureza=C)

    _lancar(
        empresa,
        timezone.datetime(2025, 12, 31).date(),
        "Saldo de abertura vindo do ano anterior",
        caixa,
        lucros,
        "800.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 16).date(),
        "Transferência do resultado do exercício",
        resultado,
        lucros,
        "25000.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 16).date(),
        "Constituição de reserva legal",
        lucros,
        reserva,
        "1250.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 16).date(),
        "Distribuição de dividendos do exercício",
        lucros,
        dividendos,
        "10000.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 20).date(),
        "Reversão parcial de reserva legal",
        reserva,
        lucros,
        "300.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 20).date(),
        "Ajuste de exercício anterior (retificação de erro)",
        ajuste,
        lucros,
        "150.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 20).date(),
        "Lucro incorporado ao capital social",
        lucros,
        capital,
        "500.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 25).date(),
        "Receita de serviços do período",
        caixa,
        receita,
        "777.00",
    )

    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "caixa": caixa,
        "resultado": resultado,
        "lucros": lucros,
        "prejuizos": prejuizos,
        "reserva": reserva,
        "dividendos": dividendos,
        "capital": capital,
        "ajuste": ajuste,
        "receita": receita,
    }


# ---------------------------------------------------------------------------
# Modelo e mapas derivados (CTB-12)
# ---------------------------------------------------------------------------


def test_conta_existente_nasce_sem_classificacao_dlpa(cenario_dlpa):
    nova = _conta(
        cenario_dlpa["empresa"],
        codigo="9.9",
        nome="Conta Nova",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )
    nova.full_clean()
    assert nova.classificacao_dlpa is None


def test_classificacao_dlpa_incompativel_com_tipo_e_recusada(cenario_dlpa):
    receita = cenario_dlpa["receita"]
    receita.classificacao_dlpa = ClassificacaoDlpa.RESERVA_LEGAL
    with pytest.raises(ValidationError, match="não é compatível com o"):
        receita.full_clean()


def test_linha_de_ajuste_aceita_qualquer_tipo_de_conta(cenario_dlpa):
    # Decisão registrada em TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA: a
    # contrapartida de retificação de erro (LSA art. 186, §1º; CPC 23)
    # pode ser qualquer conta — o cenário prova na prática (conta de
    # ATIVO classificada) e o mapa cobre os cinco tipos.
    conta_receita = cenario_dlpa["receita"]
    conta_receita.classificacao_dlpa = ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR
    conta_receita.full_clean()
    assert TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA[ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR] == (
        tuple(TipoConta.values)
    )


def test_string_vazia_e_normalizada_para_none_no_clean(cenario_dlpa):
    lucros = cenario_dlpa["lucros"]
    lucros.classificacao_dlpa = ""
    lucros.full_clean()
    assert lucros.classificacao_dlpa is None


def test_titulos_das_linhas_cobrem_exatamente_o_enum(cenario_dlpa):
    """Mapa derivado: TODO valor do enum que não é conta sujeito nem
    reserva precisa de título de linha fixa — um valor novo sem título
    reprova aqui em vez de sumir do documento (molde dos mapas
    `TIPOS_ACEITOS_*`)."""
    esperado = set(ClassificacaoDlpa.values) - {
        ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
        *RESERVAS_DE_LUCROS_DA_DLPA,
    }
    assert set(_TITULOS_DAS_LINHAS_DA_DLPA) == esperado
    assert set(RESERVAS_DE_LUCROS_DA_DLPA) <= set(ClassificacaoDlpa.values)


def test_mapa_de_tipos_aceitos_cobre_exatamente_o_enum():
    assert set(TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA) == set(ClassificacaoDlpa.values)


def test_as_seis_reservas_de_rc137_sao_pl_e_estao_no_enum():
    assert len(RESERVAS_DE_LUCROS_DA_DLPA) == 6
    for reserva in RESERVAS_DE_LUCROS_DA_DLPA:
        assert reserva in ClassificacaoDlpa.values
        assert TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA[reserva] == (TipoConta.PATRIMONIO_LIQUIDO,)


def test_listas_de_pendencia_cobrem_exatamente_as_chaves_reais(cenario_dlpa):
    """Partição (molde `test_bl502`/DL-045): a união das listas que VETAM
    é exatamente o inventário de `apurar_dlpa["pendencias"]`, sem
    duplicata — e `avisos` é o contrato separado de `_LISTAS_DE_AVISO_...`."""
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    chaves = list(dlpa["pendencias"])
    assert len(chaves) == len(set(chaves))
    assert set(chaves) == set(_LISTAS_DA_DLPA_QUE_IMPEDEM_A_EMISSAO)
    assert set(dlpa["avisos"]) == set(_LISTAS_DE_AVISO_DA_DLPA)


# ---------------------------------------------------------------------------
# Apuração: caso de referência, identidade e conciliação
# ---------------------------------------------------------------------------


def test_caso_de_referencia_do_plano_bate_saldo_final_13_750():
    """O exemplo do plano (CTB-13): transferência de 25.000,00, reserva
    legal de 1.250,00 e dividendos de 10.000,00 → saldo final 13.750,00,
    conciliado com o Balanço da mesma data."""
    escritorio = Escritorio.objects.create(nome="Escritório Referência", cnpj=_cnpj_sintetico())
    referencial = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Referência CTB-13 Ltda", cnpj=_cnpj_sintetico()
    )
    resultado = _conta(
        referencial,
        codigo="3.0",
        nome="Resultado do Exercício",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.RESULTADO_DO_EXERCICIO,
    )
    lucros = _conta(
        referencial,
        codigo="3.1",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    )
    reserva = _conta(
        referencial,
        codigo="3.3",
        nome="Reserva Legal",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.RESERVA_LEGAL,
    )
    dividendos = _conta(
        referencial,
        codigo="2.1",
        nome="Dividendos a Pagar",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.DIVIDENDO,
    )
    data = timezone.datetime(2026, 3, 16).date()
    _lancar(referencial, data, "Lucro do exercício", resultado, lucros, "25000.00")
    _lancar(referencial, data, "Reserva legal (5%)", lucros, reserva, "1250.00")
    _lancar(referencial, data, "Dividendos", lucros, dividendos, "10000.00")

    dlpa = apurar_dlpa(empresa=referencial, ano=ANO, mes=MES)
    assert dlpa["saldo_inicial"] == Decimal("0.00")
    assert dlpa["saldo_final"] == Decimal("13750.00")
    assert dlpa["conciliacao"]["diferenca"] == Decimal("0.00")
    assert avaliar_emissao_da_dlpa(dlpa)["pode_emitir"] is True


def test_identidade_saldo_inicial_somado_as_linhas_igual_saldo_final(cenario_dlpa):
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    linhas_do_meio = dlpa["linhas"][1:-1]
    assert (
        dlpa["saldo_inicial"] + sum(linha["valor"] for linha in linhas_do_meio)
        == (dlpa["saldo_final"])
    )
    assert dlpa["saldo_inicial"] == Decimal("800.00")
    assert dlpa["saldo_final"] == Decimal("14500.00")


def test_conciliacao_com_o_balanco_da_mesma_data(cenario_dlpa):
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    assert dlpa["conciliacao"]["saldo_no_balanco"] == Decimal("14500.00")
    assert dlpa["conciliacao"]["diferenca"] == Decimal("0.00")


def test_linhas_na_ordem_dos_incisos_do_artigo_186(cenario_dlpa):
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    assert _chaves_em_ordem(dlpa) == [
        "saldo_inicial",
        ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR,
        f"reversao:{ClassificacaoDlpa.RESERVA_LEGAL}",
        ClassificacaoDlpa.RESULTADO_DO_EXERCICIO,
        f"transferencia:{ClassificacaoDlpa.RESERVA_LEGAL}",
        ClassificacaoDlpa.DIVIDENDO,
        ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL,
        "saldo_final",
    ]
    valores = _linhas_por_chave(dlpa)
    assert valores[ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR] == Decimal("150.00")
    assert valores[f"reversao:{ClassificacaoDlpa.RESERVA_LEGAL}"] == Decimal("300.00")
    assert valores[ClassificacaoDlpa.RESULTADO_DO_EXERCICIO] == Decimal("25000.00")
    assert valores[f"transferencia:{ClassificacaoDlpa.RESERVA_LEGAL}"] == Decimal("-1250.00")
    assert valores[ClassificacaoDlpa.DIVIDENDO] == Decimal("-10000.00")
    assert valores[ClassificacaoDlpa.LUCRO_INCORPORADO_AO_CAPITAL] == Decimal("-500.00")


def test_a_dlpa_nao_tem_a_rubrica_de_correcao_monetaria(cenario_dlpa):
    """Contrato do Fred (29/09/2026): a rubrica "Correção monetária do
    saldo inicial" (art. 186, I) **não sai** no documento — a Lei 9.249/95,
    art. 4º, p.ú., vedou a correção monetária da moeda, então a linha é
    letra morta em qualquer exercício posterior e só ocuparia espaço no
    documento entregue ao cliente.

    Três faces do mesmo contrato, e as três precisam valer: a rubrica
    some do ENUM (ninguém pode classificar conta nela), some das LINHAS
    da apuração e some do TEXTO emitido (nada de rótulo sobrando na tela
    nem no impresso).
    """
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)

    # 1. O enum não tem o membro — o caminho de classificação fecha.
    assert "correcao_monetaria_do_saldo_inicial" not in ClassificacaoDlpa.values
    assert not any("correção monetária" in rotulo.lower() for rotulo in ClassificacaoDlpa.labels)

    # 2. Nenhuma linha da apuração carrega a chave, nem por título.
    chaves = _chaves_em_ordem(dlpa)
    assert "correcao_monetaria_do_saldo_inicial" not in chaves
    assert not any("correção monetária" in linha["titulo"].lower() for linha in dlpa["linhas"])

    # 3. A IDENTIDADE continua fechando SEM essa chave: é o que prova que
    #    tirar a linha não mexeu em número nenhum. Saldo inicial 800,00
    #    + ajuste 150,00 + reversão 300,00 + lucro 25.000,00
    #    + transferência −1.250,00 + dividendos −10.000,00
    #    + incorporação ao capital −500,00 = 13.700,00 de movimento.
    movimento_esperado = (
        Decimal("150.00")
        + Decimal("300.00")
        + Decimal("25000.00")
        - Decimal("1250.00")
        - Decimal("10000.00")
        - Decimal("500.00")
    )
    assert movimento_esperado == Decimal("13700.00")
    assert dlpa["saldo_inicial"] + movimento_esperado == dlpa["saldo_final"]
    assert dlpa["movimento"] == Decimal("13700.00")
    soma_das_linhas = sum(
        (
            linha["valor"]
            for linha in dlpa["linhas"]
            if linha["chave"] not in ("saldo_inicial", "saldo_final")
        ),
        Decimal("0.00"),
    )
    assert soma_das_linhas == Decimal("13700.00")
    assert dlpa["saldo_inicial"] + soma_das_linhas == dlpa["saldo_final"]


def test_nenhuma_conta_pode_ser_classificada_na_rubrica_removida(cenario_dlpa):
    """O caminho de escrita também fecha: uma conta que ainda tivesse o
    valor antigo — vinda de base gravada antes da decisão — cai na
    pendência que VETA a emissão, nomeando o valor cru, em vez de virar
    linha invisível no total. É o que faz a remoção ser segura mesmo sem
    migração de dado: o pior caso possível é bloqueio visível, nunca soma
    silenciosa."""
    empresa = cenario_dlpa["empresa"]
    reserva = cenario_dlpa["reserva"]
    Conta.objects.filter(pk=reserva.pk).update(
        classificacao_dlpa="correcao_monetaria_do_saldo_inicial"
    )

    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is False
    assert emissao["listas_pendentes"]["contas_com_classificacao_dlpa_desconhecida"] == [
        {
            "conta": "3.3",
            "nome": "Reserva Legal",
            "classificacao_dlpa": "correcao_monetaria_do_saldo_inicial",
        }
    ]


def test_cada_linha_carrega_os_lancamentos_que_a_geraram(cenario_dlpa):
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    por_chave = {linha["chave"]: linha for linha in dlpa["linhas"]}
    # Linha com UMA origem: a transferência do resultado, identificável.
    transferencia = por_chave[f"transferencia:{ClassificacaoDlpa.RESERVA_LEGAL}"]
    assert len(transferencia["lancamentos"]) == 1
    # As DUAS linhas da reserva vêm de lançamentos DIFERENTES.
    reversao = por_chave[f"reversao:{ClassificacaoDlpa.RESERVA_LEGAL}"]
    assert len(reversao["lancamentos"]) == 1
    assert set(transferencia["lancamentos"]).isdisjoint(reversao["lancamentos"])
    # Linhas de saldo nunca têm origem em lançamento próprio.
    assert por_chave["saldo_inicial"]["lancamentos"] == []
    assert por_chave["saldo_final"]["lancamentos"] == []


def test_linha_com_dois_lancamentos_guarda_os_dois_sem_duplicar(cenario_dlpa):
    """Achado 6 da auditoria de 29/09/2026: o caminho de AGREGAÇÃO — uma
    mesma linha alimentada por DOIS lançamentos — não era exercitado por
    teste nenhum. O `setdefault(...).append(...)` seguido de
    `dict.fromkeys(...)` é exatamente onde um erro passaria despercebido:
    duplicar um id, ou perder um dos dois, e a rastreabilidade do art. 186
    ("cada linha precisa vir de lançamento identificável") deixaria de
    valer sem nada reprovar.

    Aqui a MESMA reserva recebe uma SEGUNDA transferência no mesmo
    exercício, e a linha tem de carregar os dois lançamentos distintos,
    sem repetição, com o valor somado."""
    empresa = cenario_dlpa["empresa"]
    reserva = cenario_dlpa["reserva"]
    # A linha da 1ª transferência já existe no cenário com 1.250,00.
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 18).date(),
        "Segunda transferência para reserva legal",
        cenario_dlpa["lucros"],
        reserva,
        "400.00",
    )

    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    linha = {item["chave"]: item for item in dlpa["linhas"]}[
        f"transferencia:{ClassificacaoDlpa.RESERVA_LEGAL}"
    ]
    # DOIS lançamentos, distintos, e a lista sem repetição — os dois
    # objetos de lançamento alimentam a MESMA linha.
    assert len(linha["lancamentos"]) == 2
    assert len(set(linha["lancamentos"])) == 2
    # E o valor é a soma dos DOIS: −1.250,00 − 400,00 = −1.650,00.
    assert linha["valor"] == Decimal("-1650.00")


def test_saldo_inicial_cobre_somente_o_que_e_de_ano_anterior(cenario_dlpa):
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    assert dlpa["data_inicio_exercicio"].isoformat() == "2026-01-01"
    assert dlpa["data_fim"].isoformat() == "2026-03-31"
    # Os 800,00 de 31/12/2025 entram só como saldo inicial — nenhum
    # lançamento do ano anterior vira linha do exercício.
    assert dlpa["saldo_inicial"] == Decimal("800.00")
    assert dlpa["movimento"] == Decimal("13700.00")
    for linha in dlpa["linhas"][1:-1]:
        if linha["valor"] != Decimal("0.00"):
            assert len(linha["lancamentos"]) == 1, linha["chave"]


def test_compensacao_entre_lucros_e_prejuizos_soma_zero_e_some(cenario_dlpa):
    """PE-38/HI-26 (com o Fred) — a leitura não pressupõe resposta: um
    lançamento entre as DUAS contas sujeito tem efeito líquido zero
    (`crédito − débito` se cancela) e não aparece em nenhuma linha.

    Achado 7 da auditoria de 29/09/2026: a versão anterior só afirmava que
    NENHUMA linha valia exatamente 1.000,00. Isso passaria se a
    compensação tivesse sido reatribuída a outra linha (o lucro iria a
    26.000,00 e os dividendos a −11.000,00). Aqui a afirmação é o que o
    nome do teste promete: o dicionário INTEIRO de linhas é idêntico
    antes e depois do lançamento de compensação."""
    empresa = cenario_dlpa["empresa"]
    antes = _linhas_por_chave(apurar_dlpa(empresa=empresa, ano=ANO, mes=MES))

    _lancar(
        empresa,
        timezone.datetime(2026, 3, 22).date(),
        "Compensação de prejuízo acumulado contra lucros",
        cenario_dlpa["lucros"],
        cenario_dlpa["prejuizos"],
        "1000.00",
    )
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    depois = _linhas_por_chave(dlpa)

    assert dlpa["saldo_final"] == Decimal("14500.00"), "compensação não pode mover o saldo"
    assert dlpa["movimento"] == Decimal("13700.00")
    # A igualdade INTEIRA é a guarda de verdade: nenhuma linha pode ter
    # recebido os 1.000,00, para nenhuma das linhas.
    assert depois == antes
    # E, explicitamente, as linhas que uma reatribuição alteraria.
    assert depois[ClassificacaoDlpa.RESULTADO_DO_EXERCICIO] == Decimal("25000.00")
    assert depois[ClassificacaoDlpa.DIVIDENDO] == Decimal("-10000.00")


def test_saldo_final_bate_com_o_balanco_e_a_conciliacao_nao_acende(cenario_dlpa):
    """O critério de aceite da CTB-13 é este número: saldo final da DLPA ==
    saldo da conta de lucros acumulados no Balanço da mesma data. No caso
    íntegro os DOIS caminhos (a agregação própria da DLPA e o motor do
    Balancete) concordam e a pendência fica apagada."""
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    assert dlpa["conciliacao"]["diferenca"] == Decimal("0.00")
    assert dlpa["conciliacao"]["saldo_no_balanco"] == dlpa["saldo_final"]
    assert dlpa["pendencias"]["diferenca_de_fechamento"] == []


def test_conta_sujeito_com_filha_movimentada_acende_a_diferenca_e_veta(cenario_dlpa):
    """Achado 2 da auditoria de 29/09/2026 (gravidade ALTA): a pendência
    que IMPLEMENTA o critério de aceite da CTB-13 — a conciliação com o
    Balanço — não era disparada por teste nenhum. O único teste que a
    tocava comparava só o NOME da chave, e passaria mesmo com o cálculo
    devolvendo uma diferença constante. Aqui ela é disparada de verdade.

    O cenário é o que a decisão D9 nomeia: conta sujeito que **não é
    folha**, cuja FILHA tem movimento. Os dois caminhos divergem por
    construção — a DLPA lê a conta EXATA (D5, sem herança) e o motor do
    Balancete consolida a subárvore — então a diferença acende e a
    emissão é recusada, nomeando o valor."""
    empresa = cenario_dlpa["empresa"]
    filha = _conta(
        empresa,
        codigo="3.1.1",
        nome="Lucros Acumulados - Subconta",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=cenario_dlpa["lucros"],
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 10).date(),
        "Movimento na subconta da conta sujeito",
        filha,
        cenario_dlpa["caixa"],
        "777.00",
    )

    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    # A diferença NÃO é zero — é exatamente o 777,00 que a DLPA (conta
    # exata) não viu e o Balanço (consolidado) viu. A subconta foi
    # DEBITADA, então a subárvore consolidada fica 777,00 ABAIXO da conta
    # exata: `diferenca = saldo_final − saldo_no_balanco` sai positiva.
    assert dlpa["conciliacao"]["diferenca"] == Decimal("777.00")
    assert (
        dlpa["conciliacao"]["diferenca"]
        == dlpa["saldo_final"] - dlpa["conciliacao"]["saldo_no_balanco"]
    )

    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is False
    pendencia = emissao["listas_pendentes"]["diferenca_de_fechamento"][0]
    assert pendencia["diferenca"] == Decimal("777.00")
    # Achado 4: o veto NOMEIA as contas sujeito com o próprio saldo, para o
    # contador olhar no Balanço e ver qual diverge.
    assert {conta["conta"] for conta in pendencia["contas"]} == {"3.1", "3.2"}


def test_o_veto_da_conciliacao_nomeia_a_conta_e_usa_parenteses(cenario_dlpa, client):
    """Achado 4, ponta a ponta pela tela: o texto do veto mostra código e
    nome da conta sujeito, e o saldo NEGATIVO sai entre parênteses — como
    em toda célula assinada do produto (RC-90) e como sai na linha do
    Balanço que o contador vai conferir para validar."""
    empresa = cenario_dlpa["empresa"]
    _autenticar(client, cenario_dlpa["escritorio"], "veto-conciliacao")
    filha = _conta(
        empresa,
        codigo="3.1.1",
        nome="Lucros Acumulados - Subconta",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=cenario_dlpa["lucros"],
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 10).date(),
        "Movimento na subconta da conta sujeito",
        filha,
        cenario_dlpa["caixa"],
        "777.00",
    )
    # A conta 3.2 é DEVEDORA ("(-) Prejuízos Acumulados"): um DÉBITO nela
    # produz efeito de PL NEGATIVO, que é o caso em que a regra dos
    # parênteses precisa aparecer. Sem este lançamento as duas contas
    # sujeito saem positivas e o teste não exercitaria nada.
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 12).date(),
        "Débito em prejuízos acumulados",
        cenario_dlpa["prejuizos"],
        cenario_dlpa["caixa"],
        "300.00",
    )

    resposta = client.get(reverse("contabilidade_web:dlpa", args=[empresa.id]))
    assert resposta.context["pode_emitir"] is False
    lista = next(
        item
        for item in resposta.context["listas_pendentes"]
        if "Diferença entre a DLPA e o Balanço" in item["titulo"]
    )
    linhas = lista["linhas"]
    # As DUAS contas sujeito nomeadas, com código e nome.
    assert {linha["conta"] for linha in linhas} == {"3.1", "3.2"}
    assert any(linha["nome"] == "Lucros Acumulados" for linha in linhas)
    # A conta com saldo negativo sai entre parênteses — e acredora, sem
    # parênteses. Nenhum sinal de menos solto no texto.
    detalhes = [linha["detalhe"] for linha in linhas]
    negativo = next(d for d in detalhes if "(" in d)
    positivo = next(d for d in detalhes if "(" not in d)
    assert negativo == "Saldo no Balanço: (300,00)"
    assert "-" not in negativo
    assert positivo.startswith("Saldo no Balanço: ")


def test_conta_sujeito_com_filha_parada_ainda_emite(cenario_dlpa):
    """O caso ESPELHO do anterior, e é ele que impede o conserto de
    "resolver" a divergência vetando sempre: subconta que não se move não
    produz diferença, a emissão acontece e o número sai certo. A
    conciliação é sobre MOVIMENTO, não sobre o simples existir da
    subconta."""
    empresa = cenario_dlpa["empresa"]
    _conta(
        empresa,
        codigo="3.1.1",
        nome="Lucros Acumulados - Subconta parada",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=cenario_dlpa["lucros"],
    )

    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    assert dlpa["conciliacao"]["diferenca"] == Decimal("0.00")
    assert avaliar_emissao_da_dlpa(dlpa)["pode_emitir"] is True
    assert dlpa["saldo_final"] == Decimal("14500.00")


def test_conta_sujeito_com_classificacao_corrompida_e_nomeada(cenario_dlpa):
    """Achado 3 da auditoria de 29/09/2026: com `classificacao_dlpa`
    gravada fora do enum NA conta que o contador queria usar como sujeito,
    a apuração respondia só "nenhuma conta classificada" — mandando o
    contador ao plano de contas sem dizer que o valor gravado é lixo, e
    a conta aparecia com "—" (fora do enum não há rótulo). Agora o valor
    órfão é DECLARADO com código, nome e valor cru, e a emissão é
    recusada: falha fechada, com o diagnóstico certo."""
    empresa = cenario_dlpa["empresa"]
    # O cenário tem DUAS contas sujeito (3.1 e 3.2); as DUAS são
    # corrompidas para reproduzir o caso original, em que nenhuma sobra
    # como sujeito e a apuração só dizia "nenhuma classificada".
    Conta.objects.filter(pk__in=[cenario_dlpa["lucros"].pk, cenario_dlpa["prejuizos"].pk]).update(
        classificacao_dlpa="linha_que_nao_existe"
    )

    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is False
    # A pendência que NOMEIA o valor corrompido está presente...
    desconhecidas = emissao["listas_pendentes"]["contas_com_classificacao_dlpa_desconhecida"]
    assert {
        "conta": "3.1",
        "nome": "Lucros Acumulados",
        "classificacao_dlpa": "linha_que_nao_existe",
    } in desconhecidas
    # ...e a conta NÃO foi rebaixada a "não classificada" sem explicação:
    # as DUAS pendências aparecem, porque as duas coisas são verdade.
    assert (
        "nenhuma_conta_de_lucros_ou_prejuizos_acumulados_classificada"
        in emissao["listas_pendentes"]
    )


def test_a_demonstracao_imprime_a_origem_de_cada_linha(cenario_dlpa, client):
    """Achado 5 da auditoria de 29/09/2026: `apurar_dlpa` devolvia os
    lançamentos de cada linha e a view **jogava fora** — a rastreabilidade
    do art. 186 ("cada linha precisa vir de lançamento identificável")
    existia na apuração e morria antes do documento. Agora o lançamento
    que formou a linha é discriminado na tela, o que é o que o §1º do
    artigo pede dos ajustes de exercício anterior."""
    empresa = cenario_dlpa["empresa"]
    _autenticar(client, cenario_dlpa["escritorio"], "conta-origem")

    resposta = client.get(reverse("contabilidade_web:dlpa", args=[empresa.id]))
    assert resposta.status_code == 200
    assert resposta.context["pode_emitir"] is True

    # A linha do ajuste de exercício anterior discrimina o lançamento que
    # a formou — data e histórico, como no Diário.
    linhas = resposta.context["linhas"]
    por_chave = {linha["chave"]: linha for linha in linhas}
    origens = por_chave[ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR]["origens"]
    assert origens == ["20/03/2026 — Ajuste de exercício anterior (retificação de erro)"]
    # A linha de saldo não tem origem: saldo não vem de lançamento próprio.
    assert por_chave["saldo_inicial"]["origens"] == []
    assert por_chave["saldo_final"]["origens"] == []
    # E a discriminação aparece no HTML entregue, não só no contexto.
    conteudo = resposta.content.decode()
    assert "Ajuste de exercício anterior (retificação de erro)" in conteudo
    assert "20/03/2026" in conteudo


def test_a_conta_nova_aceita_a_classificacao_da_dlpa(client, cenario_dlpa):
    """Achado 16: o campo `classificacao_dlpa` no formulário de conta nova
    é caminho de escrita do campo NOVO e não tinha cobertura. O auditor
    verificara o comportamento por sonda própria; aqui vira teste."""
    _autenticar(client, cenario_dlpa["escritorio"], "criador-conta")
    resposta = client.post(
        reverse("contabilidade_web:conta_nova", args=[cenario_dlpa["empresa"].id]),
        data={
            "codigo": "9",
            "nome": "Reserva Estatutária",
            "tipo": TipoConta.PATRIMONIO_LIQUIDO,
            "natureza": NaturezaConta.CREDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
            "classificacao_dlpa": ClassificacaoDlpa.RESERVA_ESTATUTARIA,
        },
    )
    assert resposta.status_code == 302
    conta = Conta.objects.get(codigo="9", empresa=cenario_dlpa["empresa"])
    assert conta.classificacao_dlpa == ClassificacaoDlpa.RESERVA_ESTATUTARIA


def test_a_conta_nova_recusa_classificacao_incompativel_sem_gravar(client, cenario_dlpa):
    """O caminho de recusa: linha que o tipo da conta não aceita volta
    com o erro e **não grava nada** — a guarda é do servidor
    (`Conta.clean()`), não da tela."""
    _autenticar(client, cenario_dlpa["escritorio"], "criador-conta-invalido")
    url = reverse("contabilidade_web:conta_nova", args=[cenario_dlpa["empresa"].id])
    resposta = client.post(
        url,
        data={
            "codigo": "4.9",
            "nome": "Conta de resultado com linha de reserva",
            "tipo": TipoConta.RECEITA,
            "natureza": NaturezaConta.CREDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
            "classificacao_dlpa": ClassificacaoDlpa.RESERVA_ESTATUTARIA,
        },
    )
    assert resposta.status_code == 200
    assert not Conta.objects.filter(codigo="4.9", empresa=cenario_dlpa["empresa"]).exists()


def test_a_tela_nao_monta_a_demonstracao_quando_a_conciliacao_acende(cenario_dlpa, client):
    """A mesma pendência, ponta a ponta pela TELA: com a conciliação
    quebrada, a DLPA não é montada — o contador recebe só o que falta."""
    empresa = cenario_dlpa["empresa"]
    _autenticar(client, cenario_dlpa["escritorio"], "conta-conciliacao")
    filha = _conta(
        empresa,
        codigo="3.1.1",
        nome="Lucros Acumulados - Subconta",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=cenario_dlpa["lucros"],
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 10).date(),
        "Movimento na subconta da conta sujeito",
        filha,
        cenario_dlpa["caixa"],
        "777.00",
    )

    resposta = client.get(reverse("contabilidade_web:dlpa", args=[empresa.id]))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "pode_emitir" in resposta.context
    assert resposta.context["pode_emitir"] is False
    # O veto nomeia a pendência de conciliação...
    titulos = [lista["titulo"] for lista in resposta.context["listas_pendentes"]]
    assert any("Diferença entre a DLPA e o Balanço" in titulo for titulo in titulos)
    # ...e a demonstração NÃO é montada.
    assert "13.700,00" not in conteudo


def test_estorno_de_uma_destinacao_compensa_na_identidade(cenario_dlpa):
    """Estorno é lançamento inverso (ITG 2000) — a DLPA lê os livros
    como estão: o estorno da transferência some do SALDO final e as
    linhas da reserva recompõem o líquido real (300,00 de reversão
    menos a transferência de 1.250,00 + o estorno de 1.250,00)."""
    empresa = cenario_dlpa["empresa"]
    transferencia = _lancar(
        empresa,
        timezone.datetime(2026, 3, 16).date(),
        "Constituição de reserva legal (será estornada)",
        cenario_dlpa["lucros"],
        cenario_dlpa["reserva"],
        "700.00",
    )
    gestor = _usuario_com_papel(Papel.GESTOR, cenario_dlpa["escritorio"], "gestor-estorno-dl048")
    estornar_lancamento(
        transferencia,
        criado_por=gestor,
        data=timezone.datetime(2026, 3, 23).date(),
    )
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    # O estorno devolveu os 700,00 que o lançamento tinha tirado — o
    # saldo final é o do cenário SEM esse lançamento.
    assert dlpa["saldo_final"] == Decimal("14500.00")
    assert dlpa["conciliacao"]["diferenca"] == Decimal("0.00")
    linhas_do_meio = dlpa["linhas"][1:-1]
    assert (
        dlpa["saldo_inicial"] + sum(linha["valor"] for linha in linhas_do_meio)
        == (dlpa["saldo_final"])
    )


def test_isolamento_entre_empresas_da_mesmo_escritorio(cenario_dlpa):
    """Trio canônico (8a/8b/8c da DL-045): a apuração de uma empresa não
    enxerga lançamentos nem pendências da outra."""
    outra = Empresa.objects.create(
        escritorio=cenario_dlpa["escritorio"],
        razao_social="Outra Empresa do Escritório Ltda",
        cnpj=_cnpj_sintetico(),
    )
    _conta(
        outra,
        codigo="3.1",
        nome="Lucros Acumulados da Outra",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    )
    _conta(
        outra,
        codigo="3.0",
        nome="Resultado da Outra",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.RESULTADO_DO_EXERCICIO,
    )
    _lancar(
        outra,
        timezone.datetime(2026, 3, 10).date(),
        "Resultado da outra empresa",
        Conta.objects.get(empresa=outra, codigo="3.0"),
        Conta.objects.get(empresa=outra, codigo="3.1"),
        "99999.00",
    )

    dlpa_da_primeira = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    dlpa_da_segunda = apurar_dlpa(empresa=outra, ano=ANO, mes=MES)

    assert dlpa_da_primeira["saldo_final"] == Decimal("14500.00")
    assert dlpa_da_segunda["saldo_final"] == Decimal("99999.00")
    assert dlpa_da_segunda["pendencias"]["movimentos_sem_classificacao_dlpa"] == []


# ---------------------------------------------------------------------------
# Pendências: o que falta é declarado e veta
# ---------------------------------------------------------------------------


def test_movimento_contra_conta_sem_classificacao_veta_e_nomeia(cenario_dlpa):
    empresa = cenario_dlpa["empresa"]
    reserva_sem_linha = _conta(
        empresa,
        codigo="3.5",
        nome="Reserva Sem Linha Cadastrada",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 24).date(),
        "Destinação para conta que ninguém classificou",
        cenario_dlpa["lucros"],
        reserva_sem_linha,
        "44.00",
    )
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is False
    pendentes = emissao["listas_pendentes"]["movimentos_sem_classificacao_dlpa"]
    assert [p["conta"] for p in pendentes] == ["3.5"]
    assert pendentes[0]["nome"] == "Reserva Sem Linha Cadastrada"


def test_classificacao_gravada_fora_do_enum_veta(cenario_dlpa):
    """Valor corrompido por ORM/SQL direto (a constraint de banco só
    recusa `""`; um valor nunca existente passa) — a apuração não
    adivinha: declara e veta, com o valor cru na lista."""
    empresa = cenario_dlpa["empresa"]
    reserva = cenario_dlpa["reserva"]
    Conta.objects.filter(pk=reserva.pk).update(classificacao_dlpa="valor_que_nunca_existiu")
    _lancar(
        empresa,
        timezone.datetime(2026, 3, 24).date(),
        "Destinação para conta corrompida",
        cenario_dlpa["lucros"],
        reserva,
        "10.00",
    )
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is False
    desconhecidas = emissao["listas_pendentes"]["contas_com_classificacao_dlpa_desconhecida"]
    assert desconhecidas == [
        {
            "conta": "3.3",
            "nome": "Reserva Legal",
            "classificacao_dlpa": "valor_que_nunca_existiu",
        }
    ]


def test_sem_conta_sujeito_veta_com_mensagem_acionavel():
    escritorio = Escritorio.objects.create(nome="Escritório Sem Sujeito", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Sem Sujeito Ltda", cnpj=_cnpj_sintetico()
    )
    _conta(empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is False
    lista = emissao["listas_pendentes"][
        "nenhuma_conta_de_lucros_ou_prejuizos_acumulados_classificada"
    ]
    assert len(lista) == 1
    assert "classifique" in lista[0]["mensagem"].lower()


def test_aviso_de_resultado_nao_zerado_nunca_veta(cenario_dlpa):
    """O cenário tem receita sem zeramento: o aviso existe e a emissão
    CONTINUA liberada — aviso não é pendência (contrato separado)."""
    dlpa = apurar_dlpa(empresa=cenario_dlpa["empresa"], ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is True
    assert emissao["avisos"]["resultado_nao_transferido"][0]["valor"] == Decimal("777.00")
    assert "resultado_nao_transferido" not in emissao["listas_pendentes"]


def test_zeramento_real_alimenta_a_linha_do_lucro_do_exercicio():
    """Cadeia CTB-11 → CTB-13: o zeramento (parâmetro contábil de
    verdade) gera a transferência que a DLPA lê como "Lucro (prejuízo)
    líquido do exercício", e o aviso de resultado não zerado some."""
    escritorio = Escritorio.objects.create(nome="Escritório Zeramento", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Zeramento Ltda", cnpj=_cnpj_sintetico()
    )
    caixa = _conta(empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    receita = _conta(empresa, codigo="4.1", nome="Receita", tipo=TipoConta.RECEITA, natureza=C)
    despesa = _conta(empresa, codigo="5.1", nome="Despesa", tipo=TipoConta.DESPESA, natureza=D)
    resultado = _conta(
        empresa,
        codigo="3.0",
        nome="Resultado do Exercício",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.RESULTADO_DO_EXERCICIO,
    )
    lucros = _conta(
        empresa,
        codigo="3.1",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    )
    prejuizos = _conta(
        empresa,
        codigo="3.2",
        nome="(-) Prejuízos Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=D,
        classificacao_dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    )
    gestor = _usuario_com_papel(Papel.GESTOR, escritorio, "gestor-zera-dl048")

    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=resultado,
        conta_lucros_acumulados=lucros,
        conta_prejuizos_acumulados=prejuizos,
        vigencia_inicio=timezone.datetime(2026, 1, 1).date(),
        usuario=gestor,
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 8, 10).date(),
        "Receita de agosto",
        caixa,
        receita,
        "5000.00",
    )
    _lancar(
        empresa,
        timezone.datetime(2026, 8, 15).date(),
        "Despesa de agosto",
        despesa,
        caixa,
        "2000.00",
    )
    resultado_zeramento = zerar_resultado(empresa=empresa, ano=2026, mes=8, usuario=gestor)
    assert resultado_zeramento["lancamento_etapa2"] is not None

    dlpa = apurar_dlpa(empresa=empresa, ano=2026, mes=8)
    emissao = avaliar_emissao_da_dlpa(dlpa)
    assert emissao["pode_emitir"] is True, emissao
    valores = _linhas_por_chave(dlpa)
    assert valores[ClassificacaoDlpa.RESULTADO_DO_EXERCICIO] == Decimal("3000.00")
    assert dlpa["saldo_final"] == Decimal("3000.00")
    assert emissao["avisos"] == {}, "com o zeramento feito, não sobra resultado sem transferir"


# ---------------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------------


def test_dlpa_papel_sem_permissao_recebe_403_e_nenhum_valor(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], papel=Papel.CLIENTE, username="cliente-dl048")
    url = reverse("contabilidade_web:dlpa", args=[cenario_dlpa["empresa"].id])
    resposta = client.get(f"{url}?ano={ANO}&mes={MES}")
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()
    assert "Seu papel não permite" in conteudo
    for valor in ("14.500,00", "25.000,00", "800,00"):
        assert valor not in conteudo, valor
    assert cenario_dlpa["empresa"].razao_social not in conteudo


def test_dlpa_empresa_de_outro_escritorio_da_404(client, cenario_dlpa):
    outro_escritorio = Escritorio.objects.create(
        nome="Outro Escritório DL-048", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, outro_escritorio, username="gestor-outro-dl048")
    url = reverse("contabilidade_web:dlpa", args=[cenario_dlpa["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 404
    assert cenario_dlpa["empresa"].razao_social not in resposta.content.decode()


def test_dlpa_emitida_mostra_identificacao_linhas_e_saldos(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-emite-dl048")
    url = reverse("contabilidade_web:dlpa", args=[cenario_dlpa["empresa"].id])
    resposta = client.get(f"{url}?ano={ANO}&mes={MES}")
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    # Controle positivo + identificação do item 51 na página (classe D).
    assert "DLPA pronta para emissão" in conteudo
    assert "identificacao-do-documento" in conteudo
    assert cenario_dlpa["empresa"].razao_social in conteudo
    assert "Demonstração dos Lucros ou Prejuízos Acumulados" in conteudo
    assert "01/01/2026" in conteudo and "31/03/2026" in conteudo
    assert "Critério de apuração" in conteudo
    # Números do caso, na ordem dos incisos.
    for trecho in (
        "800,00",  # saldo inicial
        "150,00",  # ajuste
        "300,00",  # reversão
        "25.000,00",  # lucro
        "1.250,00",  # transferência (parênteses, pela classe)
        "10.000,00",  # dividendos
        "14.500,00",  # saldo final
    ):
        assert trecho in conteudo, trecho
    assert "valor-invertido" in conteudo, "valor negativo deve sair entre parênteses"


def test_dlpa_com_pendencia_veta_sem_montar_a_demonstracao(client, cenario_dlpa):
    _lancar(
        cenario_dlpa["empresa"],
        timezone.datetime(2026, 3, 24).date(),
        "Destinação para conta sem classificação",
        cenario_dlpa["lucros"],
        _conta(
            cenario_dlpa["empresa"],
            codigo="3.6",
            nome="Reserva Não Classificada",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=C,
        ),
        "44.00",
    )
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-veto-dl048")
    url = reverse("contabilidade_web:dlpa", args=[cenario_dlpa["empresa"].id])
    resposta = client.get(f"{url}?ano={ANO}&mes={MES}")
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "A DLPA NÃO pode ser emitida" in conteudo
    # O que falta, nomeado, com a AÇÃO que resolve.
    assert "Reserva Não Classificada" in conteudo
    assert "classificar esta conta" in conteudo
    # E a demonstração NÃO é montada.
    assert "DLPA pronta para emissão" not in conteudo
    assert "14.500,00" not in conteudo


def test_dlpa_veto_esconde_link_para_quem_nao_escritura(client, cenario_dlpa):
    _lancar(
        cenario_dlpa["empresa"],
        timezone.datetime(2026, 3, 24).date(),
        "Destinação para conta sem classificação",
        cenario_dlpa["lucros"],
        _conta(
            cenario_dlpa["empresa"],
            codigo="3.7",
            nome="Outra Reserva Não Classificada",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=C,
        ),
        "11.00",
    )
    # PARALEGAL lê, não escritura: a pendência aparece, o link não.
    _autenticar(
        client,
        cenario_dlpa["escritorio"],
        papel=Papel.PARALEGAL,
        username="paralegal-dl048",
    )
    url = reverse("contabilidade_web:dlpa", args=[cenario_dlpa["empresa"].id])
    conteudo = client.get(f"{url}?ano={ANO}&mes={MES}").content.decode()
    assert "A DLPA NÃO pode ser emitida" in conteudo
    assert "Outra Reserva Não Classificada" in conteudo
    assert "classificar esta conta" not in conteudo


def test_dlpa_competencia_malformada_recebe_400(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-400-dl048")
    url = reverse("contabilidade_web:dlpa", args=[cenario_dlpa["empresa"].id])
    resposta = client.get(f"{url}?ano=abc&mes=3")
    assert resposta.status_code == 400


def test_dlpa_empresa_sem_contas_renderiza_estado_vazio(client):
    escritorio = Escritorio.objects.create(nome="Escritório Vazio DL-048", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Vazio DL-048 Ltda", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, escritorio, username="gestor-vazio-dl048")
    url = reverse("contabilidade_web:dlpa", args=[empresa.id])
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "ainda não tem nenhuma conta cadastrada" in conteudo
    assert "identificacao-do-documento" not in conteudo


def test_dlpa_aparece_no_hub_de_relatorios_e_no_menu_lateral(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-hub-dl048")
    url = reverse("contabilidade_web:relatorios", args=[cenario_dlpa["empresa"].id])
    conteudo = client.get(url).content.decode()
    dlpa_url = reverse("contabilidade_web:dlpa", args=[cenario_dlpa["empresa"].id])
    assert dlpa_url in conteudo, "cartão da DLPA ausente do hub"
    assert "#icone-dlpa" in conteudo, "ícone do cartão ausente do sprite"
    # O menu lateral (base.html) é o mesmo em toda página autenticada.
    assert ">DLPA</a>" in conteudo, "item de menu da DLPA ausente"


def test_plano_de_contas_mostra_coluna_e_botao_da_dlpa(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-plano-dl048")
    url = reverse("contabilidade_web:plano_de_contas", args=[cenario_dlpa["empresa"].id])
    conteudo = client.get(url).content.decode()
    assert "Linha da DLPA" in conteudo
    assert "Lucros ou prejuízos acumulados (conta da DLPA)" in conteudo
    conta = cenario_dlpa["reserva"]
    caminho = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, conta.id],
    )
    assert caminho in conteudo


# ---------------------------------------------------------------------------
# Tela de classificar a linha da DLPA (porta do CTB-12)
# ---------------------------------------------------------------------------


def test_classificacao_dlpa_get_mostra_linha_atual_e_opcoes(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-get-dl048")
    conta = cenario_dlpa["reserva"]
    url = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, conta.id],
    )
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Linha da DLPA" in conteudo
    assert "Reserva legal" in conteudo
    assert "Lucros ou prejuízos acumulados" in conteudo


def test_classificacao_dlpa_post_grava_com_trilha(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-post-dl048")
    conta = _conta(
        cenario_dlpa["empresa"],
        codigo="3.8",
        nome="Reserva Estatutária",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )
    url = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, conta.id],
    )
    resposta = client.post(url, {"classificacao_dlpa": ClassificacaoDlpa.RESERVA_ESTATUTARIA})
    assert resposta.status_code == 302
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == ClassificacaoDlpa.RESERVA_ESTATUTARIA

    registro = RegistroAuditoria.objects.filter(
        acao="conta.classificacao_dlpa_alterada", objeto_id=str(conta.pk)
    ).latest("id")
    assert registro.detalhes["classificacao_dlpa_antes"] is None
    assert registro.detalhes["classificacao_dlpa_depois"] == ClassificacaoDlpa.RESERVA_ESTATUTARIA


def test_classificacao_dlpa_post_invalido_reexibe_com_erro_e_nao_grava(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-invalido-dl048")
    receita = cenario_dlpa["receita"]
    url = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, receita.id],
    )
    resposta = client.post(url, {"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL})
    assert resposta.status_code == 200, "recusa de regra é a tela respondendo, nunca um 500"
    conteudo = resposta.content.decode()
    assert "não é compatível com o" in conteudo
    receita.refresh_from_db()
    assert receita.classificacao_dlpa is None


def test_classificacao_dlpa_post_remover_volta_para_none(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-remove-dl048")
    conta = cenario_dlpa["reserva"]
    url = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, conta.id],
    )
    resposta = client.post(url, {"classificacao_dlpa": ""})
    assert resposta.status_code == 302
    conta.refresh_from_db()
    assert conta.classificacao_dlpa is None
    registro = RegistroAuditoria.objects.filter(
        acao="conta.classificacao_dlpa_alterada", objeto_id=str(conta.pk)
    ).latest("id")
    assert registro.detalhes["classificacao_dlpa_antes"] == ClassificacaoDlpa.RESERVA_LEGAL
    assert registro.detalhes["classificacao_dlpa_depois"] is None


def test_classificacao_dlpa_campo_extra_no_corpo_recebe_400(client, cenario_dlpa):
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-contrato-dl048")
    conta = cenario_dlpa["reserva"]
    url = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, conta.id],
    )
    resposta = client.post(
        url, {"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL, "xpto": "1"}
    )
    assert resposta.status_code == 400
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == ClassificacaoDlpa.RESERVA_LEGAL, "nada foi gravado"


def test_classificacao_dlpa_sem_permissao_recebe_403(client, cenario_dlpa):
    _autenticar(
        client,
        cenario_dlpa["escritorio"],
        papel=Papel.PARALEGAL,
        username="paralegal-classifica-dl048",
    )
    conta = cenario_dlpa["reserva"]
    url = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, conta.id],
    )
    resposta = client.post(url, {"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL})
    assert resposta.status_code == 403
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == ClassificacaoDlpa.RESERVA_LEGAL, "nada foi gravado"


def test_classificacao_dlpa_conta_de_outro_escritorio_da_404(client, cenario_dlpa):
    outro_escritorio = Escritorio.objects.create(
        nome="Outro Escritório Classifica", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, outro_escritorio, username="gestor-outro-classifica-dl048")
    conta = cenario_dlpa["reserva"]
    url = reverse(
        "contabilidade_web:conta_classificacao_dlpa",
        args=[cenario_dlpa["empresa"].id, conta.id],
    )
    resposta = client.get(url)
    assert resposta.status_code == 404


def test_classificar_servico_reclassifica_livremente_com_movimento(cenario_dlpa):
    """DE-086 aplicado à DLPA: classificação é propriedade de
    apresentação — trocar com movimento gravado é livre, com trilha."""
    gestor = _usuario_com_papel(Papel.GESTOR, cenario_dlpa["escritorio"], "gestor-servico-dl048")
    conta = cenario_dlpa["reserva"]
    classificar_conta_na_dlpa(
        conta=conta,
        classificacao=ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR,
        usuario=gestor,
    )
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR
    registro = RegistroAuditoria.objects.filter(
        acao="conta.classificacao_dlpa_alterada", objeto_id=str(conta.pk)
    ).latest("id")
    assert registro.detalhes["classificacao_dlpa_antes"] == ClassificacaoDlpa.RESERVA_LEGAL
    assert (
        registro.detalhes["classificacao_dlpa_depois"]
        == ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR
    )
