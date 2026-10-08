"""DL-074 — correção da auditoria rodada 1: A3, A4, A6 (Propostas 3 a 6) e A7 (b).

Achados e propostas em docs/auditorias/2026-10-08-dl-074-rodada-1.md. Dados 100%
sintéticos (xml_sinteticos.py e test_dl074_suporte.py). Números esperados escritos à mão.

- A3: lançar receita IDÊNTICA a outra não estornada é recusado, nomeando a existente.
- A4: valor com ponto de milhar e sem vírgula ("10.000") é recusado pedindo a vírgula.
- A6, Proposta 3: isolamento entre empresas no domínio (composição e confirmação).
- A6, Proposta 4: INSERT SQL de receita confirmada em mês confirmado → a retificar.
- A6, Proposta 5: fronteiras exatas de 20% (limite e sublimite).
- A6, Proposta 6: gatilhos — estorno que troca o valor e DELETE de confirmação.
- A7 (b): confirmar mês posterior ao mês corrente ou anterior à abertura é recusado.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico
from apps.fiscal import services as servicos_recepcao
from apps.fiscal.escrituracao import efetivar_escrituracao
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    DocumentoFiscal,
    EstadoReceitaInformada,
    MercadoReceita,
    NaturezaOperacao,
    PapelDocumento,
    ReceitaInformada,
    SituacaoIssReceitaInformada,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.test_dl074_suporte import (
    ORIGEM_OUTRAS,
    confirmar_meses,
    escriturar,
    fixar_hoje,
    fixar_inicio_de_uso,
    informar_e_confirmar,
    preparar_simples,
)
from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_TOMADOR_PADRAO,
    identificador_nfse,
    xml_nfse,
)

pytestmark = pytest.mark.django_db

INTERNO = MercadoReceita.INTERNO
EXTERNO = MercadoReceita.EXTERNO
RESTRICAO_RECEITA = "receita_informada_imutavel_depois_de_confirmada"
RESTRICAO_CONFIRMACAO = "confirmacao_mes_imutavel_depois_de_confirmada"
CNPJ_TERCEIRA = "11444777000161"  # CNPJ sintético com dígitos verificadores válidos.


def _recusa_do_banco(restricao, operacao):
    with pytest.raises(IntegrityError) as info:
        with transaction.atomic():
            operacao()
    diag = getattr(info.value.__cause__, "diag", None)
    assert diag is not None and diag.constraint_name == restricao, info.value


def _lancamento_valido(**sobrescritas):
    dados = {
        "ano": "2024",
        "mes": "03",
        "mercado": "interno",
        "situacao_iss": "proprio_municipio",
        "valor": "100,00",
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "Extrato sintético de teste.",
        "acao": "rascunho",
    }
    dados.update(sobrescritas)
    return dados


def _url_lancar(empresa):
    return reverse("fiscal_web:receita_informada_nova", args=[empresa.pk])


def _url_confirmar_mes(empresa, ano, mes):
    return reverse("fiscal_web:receita_mes_confirmar", args=[empresa.pk, ano, mes])


def _base_api(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}"


@pytest.fixture
def empresa(empresa_a):
    fixar_inicio_de_uso(empresa_a, 2024, 1)
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


@pytest.fixture
def receita_confirmada(empresa_a, usuario_gestor_a):
    return informar_e_confirmar(empresa_a, usuario_gestor_a, 2026, 5, "100.00")


@pytest.fixture
def confirmacao(empresa_a, usuario_gestor_a):
    return servico.confirmar_mes(empresa_a, 2026, 5, usuario_gestor_a)


# ---------------------------------------------------------------------------
# A3 — receita informada idêntica a outra não estornada é recusada (serviço, tela, API)
# ---------------------------------------------------------------------------


def _lancar(empresa, usuario, **variacao):
    """Lançamento de referência (mar/2024, interno, 1.500,00, NF 123); `variacao` troca campos."""
    campos = {
        "ano": 2024,
        "mes": 3,
        "mercado": INTERNO,
        "valor": "1500",
        "origem": ORIGEM_OUTRAS,
        "documento_suporte": "NF 123 sintética",
    }
    campos.update(variacao)
    # HI-80: o interno leva situação do ISS (exigida); a exportação não leva.
    situacao = (
        SituacaoIssReceitaInformada.PROPRIO_MUNICIPIO if campos["mercado"] == INTERNO else None
    )
    return servico.lancar_receita_informada(
        empresa,
        campos["ano"],
        campos["mes"],
        campos["mercado"],
        campos["valor"],
        campos["origem"],
        "Lançamento sintético de teste.",
        campos["documento_suporte"],
        usuario,
        situacao_iss=situacao,
    )


def test_a3_receita_identica_a_outra_nao_estornada_e_recusada_nomeando_a_existente(
    empresa, usuario_gestor_a
):
    primeira = _lancar(empresa, usuario_gestor_a)

    with pytest.raises(servico.ReceitaErro) as info:
        _lancar(empresa, usuario_gestor_a, valor="1500.00")

    mensagem = info.value.mensagem
    assert "existe receita igual lançada em" in mensagem
    assert "outro documento de suporte" in mensagem
    assert ReceitaInformada.objects.filter(empresa=empresa).count() == 1
    assert ReceitaInformada.objects.get(empresa=empresa).pk == primeira.pk


@pytest.mark.parametrize(
    "variacao",
    [
        {"documento_suporte": "NF 456 sintética"},
        {"valor": "1500.01"},
        {"mercado": EXTERNO},
        {"mes": 4},
        {"origem": "servico_documento_nao_integrado"},
    ],
    ids=["documento", "valor", "mercado", "mes", "origem"],
)
def test_a3_receita_que_difere_em_um_campo_e_aceita(empresa, usuario_gestor_a, variacao):
    _lancar(empresa, usuario_gestor_a)

    _lancar(empresa, usuario_gestor_a, **variacao)

    assert ReceitaInformada.objects.filter(empresa=empresa).count() == 2


def test_a3_receita_igual_mas_estornada_nao_bloqueia_novo_lancamento(empresa, usuario_gestor_a):
    primeira = _lancar(empresa, usuario_gestor_a)
    servico.confirmar_receita_informada(primeira, usuario_gestor_a)
    servico.estornar_receita_informada(primeira, "Lançamento errado.", usuario_gestor_a)

    _lancar(empresa, usuario_gestor_a)

    assert ReceitaInformada.objects.filter(empresa=empresa).count() == 2


def test_a3_tela_dois_posts_iguais_gravam_uma_receita_so(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    primeiro = client.post(_url_lancar(empresa), _lancamento_valido(valor="1.500,00"))
    segundo = client.post(_url_lancar(empresa), _lancamento_valido(valor="1.500,00"))

    assert primeiro.status_code == 302
    assert segundo.status_code == 200
    assert "existe receita igual lançada em" in segundo.content.decode()
    assert ReceitaInformada.objects.filter(empresa=empresa).count() == 1


def test_a3_api_segundo_post_identico_e_409_e_nada_grava(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    corpo = {
        "ano": 2024,
        "mes": 3,
        "mercado": "interno",
        "situacao_iss": "proprio_municipio",
        "valor": "1500.00",
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "NF 123 sintética",
    }
    url = f"{_base_api(empresa)}/receitas-informadas/"

    primeira = client.post(url, data=corpo, content_type="application/json")
    segunda = client.post(url, data=corpo, content_type="application/json")

    assert primeira.status_code == 201, primeira.content
    assert segunda.status_code == 409, segunda.content
    assert "existe receita igual" in segunda.json()["detail"]
    assert ReceitaInformada.objects.filter(empresa=empresa).count() == 1


# ---------------------------------------------------------------------------
# A4 — valor com ponto de milhar e sem vírgula é recusado pedindo a vírgula (tela)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("digitado", "sugestao"),
    [("10.000", "10.000,00"), ("1.500", "1.500,00"), ("1.234.567", "1.234.567,00")],
)
def test_a4_ponto_de_milhar_sem_virgula_e_recusado_pedindo_a_virgula(
    client, empresa, usuario_gestor_a, digitado, sugestao
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url_lancar(empresa), _lancamento_valido(valor=digitado, acao="confirmar")
    )

    assert resposta.status_code == 200
    assert f"use vírgula para os centavos: {sugestao}" in resposta.content.decode()
    assert ReceitaInformada.objects.count() == 0


@pytest.mark.parametrize(
    ("digitado", "gravado"),
    [("1.000,50", "1000.50"), ("1500", "1500.00"), ("1500,5", "1500.50")],
)
def test_a4_formas_sem_ambiguidade_gravam_o_valor_certo(
    client, empresa, usuario_gestor_a, digitado, gravado
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_lancar(empresa), _lancamento_valido(valor=digitado))

    assert resposta.status_code == 302
    assert ReceitaInformada.objects.get().valor == Decimal(gravado)


# ---------------------------------------------------------------------------
# A7 (b) — confirmar mês posterior ao mês corrente ou anterior à abertura é recusado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("ano", "mes"), [(2026, 11), (2026, 12), (2030, 1)])
def test_a7_confirmar_mes_posterior_ao_mes_corrente_e_recusado(
    empresa_a, usuario_gestor_a, monkeypatch, ano, mes
):
    fixar_hoje(monkeypatch, date(2026, 10, 8))

    with pytest.raises(servico.EntradaInvalidaReceita, match="posterior ao mês corrente"):
        servico.confirmar_mes(empresa_a, ano, mes, usuario_gestor_a)

    assert not ConfirmacaoReceitaMensal.objects.filter(empresa=empresa_a).exists()


def test_a7_confirmar_o_mes_corrente_e_permitido(empresa_a, usuario_gestor_a, monkeypatch):
    fixar_hoje(monkeypatch, date(2026, 10, 8))

    confirmacao = servico.confirmar_mes(empresa_a, 2026, 10, usuario_gestor_a)

    assert confirmacao.estado == "confirmada"


def test_a7_confirmar_mes_anterior_a_abertura_e_recusado_e_o_da_abertura_e_aceito(
    empresa_a, usuario_gestor_a, monkeypatch
):
    fixar_hoje(monkeypatch, date(2026, 10, 8))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )

    with pytest.raises(servico.EntradaInvalidaReceita, match="anterior à abertura no CNPJ"):
        servico.confirmar_mes(empresa, 2026, 2, usuario_gestor_a)

    assert servico.confirmar_mes(empresa, 2026, 3, usuario_gestor_a).mes == 3


def test_a7_tela_recusa_mes_futuro_sem_gravar(client, empresa, usuario_gestor_a, monkeypatch):
    fixar_hoje(monkeypatch, date(2026, 10, 8))
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_confirmar_mes(empresa, 2026, 11), follow=True)

    assert "posterior ao mês corrente" in resposta.content.decode()
    assert not ConfirmacaoReceitaMensal.objects.filter(empresa=empresa).exists()


def test_a7_api_recusa_mes_futuro_com_400(client, empresa, usuario_gestor_a, monkeypatch):
    fixar_hoje(monkeypatch, date(2026, 10, 8))
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        f"{_base_api(empresa)}/receita/confirmar/",
        data={"ano": 2026, "mes": 11},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert not ConfirmacaoReceitaMensal.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Proposta 3 (A6) — isolamento entre empresas no domínio (mata M10a, M10b e M10c)
# ---------------------------------------------------------------------------


def _escriturar_como_prestadora(escritorio, empresa, usuario, *, sufixo, competencia, valor):
    """NFS-e sintética em que `empresa` é a PRESTADORA (o helper padrão só serve à empresa A)."""
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
            prestador_documento=empresa.cnpj,
            tomador_documento=CNPJ_TOMADOR_PADRAO,
            v_serv=f"{Decimal(valor):.2f}",
            v_liq=f"{Decimal(valor):.2f}",
        ),
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)
    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )
    return efetivar_escrituracao(vinculo, NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR, usuario)


def test_composicao_e_confirmacao_isolam_empresas(
    empresa_a, empresa_a2, escritorio_a, usuario_gestor_a
):
    # Duas outras empresas do MESMO mês e escritório movimentam receita: a empresa A não
    # pode enxergar nem a receita informada nem a escrituração nem a confirmação delas.
    empresa_c = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Terceira Ltda", cnpj=CNPJ_TERCEIRA
    )
    for empresa_do_teste in (empresa_a, empresa_a2, empresa_c):
        fixar_inicio_de_uso(empresa_do_teste, 2024, 1)

    escriturar(
        escritorio_a, empresa_a, usuario_gestor_a, sufixo=801, competencia=(2025, 5), valor="100"
    )
    _escriturar_como_prestadora(
        escritorio_a, empresa_c, usuario_gestor_a, sufixo=803, competencia=(2025, 5), valor="300"
    )
    informar_e_confirmar(empresa_a2, usuario_gestor_a, 2025, 5, "7000")
    confirmar_meses(empresa_a2, usuario_gestor_a, [(2025, 5)])

    composicao_a = servico.composicao_do_mes(empresa_a, 2025, 5)
    composicao_c = servico.composicao_do_mes(empresa_c, 2025, 5)

    assert composicao_a.interno.documento == Decimal("100.00")
    assert composicao_a.interno.informado == Decimal("0.00")
    assert composicao_c.interno.documento == Decimal("300.00")
    assert servico.situacao_do_mes(empresa_a, 2025, 5) == "nao_confirmado"
    assert servico.situacao_do_mes(empresa_a2, 2025, 5) == "confirmado"


# ---------------------------------------------------------------------------
# Proposta 4 (A6) — segunda camada: INSERT SQL de receita confirmada em mês confirmado
# ---------------------------------------------------------------------------


def test_insert_sql_de_receita_confirmada_em_mes_confirmado_vira_a_retificar(
    empresa_a, usuario_gestor_a, monkeypatch
):
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    servico.confirmar_mes(empresa_a, 2026, 5, usuario_gestor_a)
    assert servico.situacao_do_mes(empresa_a, 2026, 5) == "confirmado"

    # Caminho que escapa dos serviços: INSERT direto, já em estado confirmado.
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO fiscal_receitainformada ("
            " empresa_id, ano, mes, mercado, valor, origem, motivo, documento_suporte,"
            " estado, criado_em, criado_por_id, confirmada_em, confirmada_por_id,"
            " estornada_em, estornada_por_id, motivo_estorno)"
            " VALUES (%s, 2026, 5, 'interno', 50.00, 'ajuste', 'M.', 'S.',"
            " 'confirmada', now(), %s, now(), %s, NULL, NULL, '')",
            [empresa_a.pk, usuario_gestor_a.pk, usuario_gestor_a.pk],
        )

    assert servico.situacao_do_mes(empresa_a, 2026, 5) == "a_retificar"
    assert servico.composicao_do_mes(empresa_a, 2026, 5).total(INTERNO) == Decimal("50.00")


# ---------------------------------------------------------------------------
# Proposta 5 (A6) — fronteiras de 20% do limite e do sublimite (mata M09, M09b e M09c)
# ---------------------------------------------------------------------------

_SUBLIMITE = ("sublimite_excedido_ate_20", "sublimite_excedido_acima_20")
_LIMITE = ("limite_excedido_ate_20", "limite_excedido_acima_20")


@pytest.mark.parametrize(
    ("receita_do_ano", "esperados"),
    [
        ("3600000.00", set()),
        ("3600000.01", {"sublimite_excedido_ate_20"}),
        ("4320000.00", {"sublimite_excedido_ate_20"}),
        ("4320000.01", {"sublimite_excedido_acima_20"}),
        ("4800000.00", {"sublimite_excedido_acima_20"}),
        ("4800000.01", {"sublimite_excedido_acima_20", "limite_excedido_ate_20"}),
        ("5760000.00", {"sublimite_excedido_acima_20", "limite_excedido_ate_20"}),
        ("5760000.01", {"sublimite_excedido_acima_20", "limite_excedido_acima_20"}),
    ],
)
def test_fronteiras_de_20_por_cento_do_sublimite_e_do_limite(
    empresa_a, usuario_gestor_a, monkeypatch, receita_do_ano, esperados
):
    # Abertura 05/01/2026: teto do limite = 12 × 400.000 = 4.800.000; do sublimite = 3.600.000.
    # Uma receita única em janeiro/2026 = receita acumulada no ano.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 1, 5), inicio_simples=date(2026, 1, 5)
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 1, receita_do_ano)
    confirmar_meses(empresa, usuario_gestor_a, [(2026, 1)])

    resultado = apuracao.rbt12(empresa, 2026, 1)

    excessos = {
        a.codigo for a in resultado.avisos if a.codigo.startswith(("sublimite_", "limite_"))
    }
    assert excessos == esperados


# ---------------------------------------------------------------------------
# Proposta 6 (A6) — gatilhos: o estorno não troca o valor (T03); a confirmação não se apaga (T04)
# ---------------------------------------------------------------------------


def test_estorno_sql_que_tambem_troca_o_valor_e_recusado_pelo_banco(
    receita_confirmada, usuario_gestor_a
):
    _recusa_do_banco(
        RESTRICAO_RECEITA,
        lambda: ReceitaInformada.objects.filter(pk=receita_confirmada.pk).update(
            estado=EstadoReceitaInformada.ESTORNADA,
            estornada_em=timezone.now(),
            estornada_por=usuario_gestor_a,
            motivo_estorno="Estorno sintético.",
            valor="9.00",
        ),
    )

    receita_confirmada.refresh_from_db()
    assert receita_confirmada.estado == EstadoReceitaInformada.CONFIRMADA
    assert receita_confirmada.valor == Decimal("100.00")


def test_delete_de_confirmacao_pelo_queryset_e_recusado_pelo_banco(confirmacao):
    _recusa_do_banco(
        RESTRICAO_CONFIRMACAO,
        lambda: ConfirmacaoReceitaMensal.objects.filter(pk=confirmacao.pk).delete(),
    )

    assert ConfirmacaoReceitaMensal.objects.filter(pk=confirmacao.pk).exists()


def test_delete_sql_de_confirmacao_e_recusado_pelo_banco(confirmacao):
    def apagar_por_sql():
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM fiscal_confirmacaoreceitamensal WHERE id = %s", [confirmacao.pk]
            )

    _recusa_do_banco(RESTRICAO_CONFIRMACAO, apagar_por_sql)

    assert ConfirmacaoReceitaMensal.objects.filter(pk=confirmacao.pk).exists()


# ---------------------------------------------------------------------------
# A7 (a) no painel — a tela mostra o aviso de receita anterior à abertura
# ---------------------------------------------------------------------------


def test_a7_painel_mostra_o_aviso_de_receita_antes_da_abertura(
    client, empresa_a, usuario_gestor_a, monkeypatch
):
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    # Simples a partir da abertura (R4: o início do período não pode ser anterior a ela).
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 1, "50000")
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 3, "1000")
    confirmar_meses(empresa, usuario_gestor_a, [(2026, 3), (2026, 4)])
    client.force_login(usuario_gestor_a)

    resposta = client.get(
        reverse("fiscal_web:receita_do_mes"), {"empresa": empresa.pk, "ano": 2026, "mes": 4}
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "receita de 01/2026 anterior à abertura no CNPJ (10/03/2026)" in conteudo
    assert "Avisos de limite, de regime e de dados" in conteudo
