"""DL-079, correção da auditoria rodada 1 (achados A1 a A8, A10, A12 e A14), com os testes
T-A1 a T-A5 do relatório (seção 15) e os testes que matam os mutantes sobreviventes (A4).

Dados sintéticos: NFS-e prestadas pelo pipeline real (`suporte_presumido_dl079`), CNPJs de
`conftest` e um CNPJ fictício de outra cliente. Os valores esperados estão escritos à mão nos
comentários; não são lidos do próprio produto. Cada bloco nomeia o achado (A…) e o mutante
que deve derrubar (M…).
"""

import json
from datetime import date
from decimal import Decimal as D
from urllib.parse import urlencode

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import (
    AtividadePresuncaoEmpresa,
    ConfirmacaoRetencaoPresumido,
    CriterioReceitaPresumido,
    DeclaracaoReceitasIntegrais,
    MedidaJudicialLC224,
    ReceitaTrimestralPresumido,
)
from apps.fiscal.tests.suporte_presumido_dl079 import (
    efetivar_prestada,
    nota_efetivada,
    receber_prestada,
)
from apps.fiscal.tests.suporte_tomada_dl078 import cancelar

pytestmark = pytest.mark.django_db

COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
SERVICOS = tab.SERVICOS_GERAIS
INTERMEDIACAO = tab.INTERMEDIACAO_NEGOCIOS
CNPJ_CLIENTE_B = "77888999000155"
NUL = "\x00"
TEXTO_SUSPENSO = "parcela suspensa por medida judicial — fora da dedução"


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _presumida(empresa, usuario, codigo_padrao=COMERCIO, inicio=date(2026, 1, 1)):
    """Lucro Presumido em 2026, critério de competência e atividade PADRÃO (das NFS-e)."""
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    servico.definir_criterio(empresa, 2026, "competencia", usuario)
    return servico.criar_atividade(
        empresa, {"atividade": codigo_padrao, "inicio": inicio, "padrao": True}, usuario
    )


def _atividade(empresa, usuario, codigo, inicio=date(2026, 1, 1)):
    return servico.criar_atividade(
        empresa, {"atividade": codigo, "inicio": inicio, "padrao": False}, usuario
    )


def _receita(empresa, usuario, trimestre, valor, atividade, suporte):
    return servico.criar_receita(
        empresa,
        2026,
        trimestre,
        {
            "tipo": "presuncao",
            "valor": valor,
            "descricao": f"receita {suporte}",
            "suporte": suporte,
            "atividade_id": atividade.pk,
        },
        usuario,
    )


def _integral(empresa, usuario, trimestre, valor, suporte):
    return servico.criar_receita(
        empresa,
        2026,
        trimestre,
        {"tipo": "integral", "valor": valor, "descricao": suporte, "suporte": suporte},
        usuario,
    )


def _nota(escritorio, empresa, usuario, sufixo, valor, competencia, **xml):
    return nota_efetivada(
        escritorio, empresa, usuario, sufixo, v_serv=valor, d_compet=competencia, **xml
    )


def _url(nome, *args, **consulta):
    url = reverse(f"fiscal_web:{nome}", args=list(args))
    return url + ("?" + urlencode(consulta) if consulta else "")


def _api(empresa, sufixo):
    return f"/fiscal/api/empresas/{empresa.pk}/presumido/{sufixo}"


def _post_json(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _estado(empresa):
    """Contagens que uma recusa NÃO pode alterar (receitas ativas, medidas, atividades etc.)."""
    return (
        ReceitaTrimestralPresumido.objects.filter(empresa=empresa, estado="ativa").count(),
        ReceitaTrimestralPresumido.objects.filter(empresa=empresa).count(),
        MedidaJudicialLC224.objects.filter(empresa=empresa, ativa=True).count(),
        AtividadePresuncaoEmpresa.objects.filter(empresa=empresa, fim__isnull=True).count(),
        DeclaracaoReceitasIntegrais.objects.filter(empresa=empresa).count(),
        ConfirmacaoRetencaoPresumido.objects.filter(
            escrituracao__empresa=empresa, estado="ativa"
        ).count(),
    )


def _ano_com_caso_iii(empresa, usuario, escritorio):
    """Comércio por NFS-e de 1.500.000,00 em cada trimestre de 2026.

    IRPJ (N = 4): excedente de 250.000,00 por trimestre; ExcAnual = 6.000.000 − 5.000.000 =
    1.000.000; S = 750.000 (E1 + E2 + E3); 1.000.000 ≥ 750.000, então caso III.
    CSLL (N = 3, desde o 2º trimestre): ExcAnual = 4.500.000 − 3.750.000 = 750.000;
    S = 500.000; caso III.
    """
    for trimestre in (1, 2, 3, 4):
        _nota(
            escritorio,
            empresa,
            usuario,
            1100 + trimestre,
            "1500000.00",
            f"2026-{3 * trimestre - 2:02d}-15",
        )


@pytest.fixture
def cliente_b(escritorio_a):
    """Outra cliente do MESMO escritório: o isolamento dentro do escritório é o que se testa."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente B Ltda", cnpj=CNPJ_CLIENTE_B
    )


@pytest.fixture
def presumido(empresa_a, usuario_gestor_a):
    """Empresa A presumida em 2026, com comércio como atividade padrão."""
    padrao = _presumida(empresa_a, usuario_gestor_a)
    return {"empresa": empresa_a, "padrao": padrao}


@pytest.fixture
def duas_clientes(empresa_a, cliente_b, escritorio_a, usuario_gestor_a):
    """A e B no mesmo escritório, no mesmo trimestre, com um dado de cada tipo (T-A4a e seguintes).

    A: padrão SERVICOS; receita informada 100.000,00; integral 1.000,00; declaração de integrais
       (feita ANTES da de B); nota do 2º trimestre com retenção de 500,00 confirmada; medida
       judicial só a partir do 3º trimestre (não cobre o 1º); atividade de serviços extra (para o
       encerramento).
    B: padrão COMERCIO, criada DEPOIS da de A; atividade de serviços; receita informada 500.000,00;
       integral 7.000,00; declaração; NFS-e de 3.000.000,00 com retenção de 900,00 confirmada;
       medida "ambos" sem prazo final a partir do 1º trimestre.
    """
    usuario = usuario_gestor_a
    padrao_a = _presumida(empresa_a, usuario, SERVICOS)
    atividade_a_extra = _atividade(empresa_a, usuario, SERVICOS)
    receita_a = _receita(empresa_a, usuario, 1, "100000.00", padrao_a, "A serviços")
    integral_a = _integral(empresa_a, usuario, 1, "1000.00", "A integral")
    servico.declarar_receitas_integrais(empresa_a, 2026, 1, "", usuario)
    nota_a = _nota(
        escritorio_a,
        empresa_a,
        usuario,
        1401,
        "50000.00",
        "2026-04-10",
        ret_irrf="500.00",
    )
    servico.confirmar_retencao(empresa_a, nota_a.pk, "500.00", None, "", usuario)
    medida_a = servico.cadastrar_medida(
        empresa_a,
        {
            "tributo": "irpj",
            "ano_inicial": 2026,
            "trimestre_inicial": 3,
            "numero_processo": "proc-ficticio-A",
            "orgao": "Vara fictícia",
            "data_decisao": "2026-07-01",
            "suporte": "decisão sintética A",
        },
        usuario,
    )

    padrao_b = _presumida(cliente_b, usuario, COMERCIO)
    atividade_b = _atividade(cliente_b, usuario, SERVICOS)
    receita_b = _receita(cliente_b, usuario, 1, "500000.00", atividade_b, "B serviços")
    integral_b = _integral(cliente_b, usuario, 1, "7000.00", "B integral")
    servico.declarar_receitas_integrais(cliente_b, 2026, 1, "", usuario)
    nota_b = _nota(
        escritorio_a,
        cliente_b,
        usuario,
        1501,
        "3000000.00",
        "2026-01-20",
        prestador=CNPJ_CLIENTE_B,
        ret_irrf="900.00",
    )
    servico.confirmar_retencao(cliente_b, nota_b.pk, "900.00", None, "", usuario)
    medida_b = servico.cadastrar_medida(
        cliente_b,
        {
            "tributo": "ambos",
            "ano_inicial": 2026,
            "trimestre_inicial": 1,
            "numero_processo": "proc-ficticio-B",
            "orgao": "Vara fictícia",
            "data_decisao": "2026-02-01",
            "suporte": "decisão sintética B",
        },
        usuario,
    )
    return {
        "a": empresa_a,
        "b": cliente_b,
        "padrao_a": padrao_a,
        "padrao_b": padrao_b,
        "atividade_a_extra": atividade_a_extra,
        "atividade_b": atividade_b,
        "receita_a": receita_a,
        "receita_b": receita_b,
        "integral_a": integral_a,
        "integral_b": integral_b,
        "nota_a": nota_a,
        "nota_b": nota_b,
        "medida_a": medida_a,
        "medida_b": medida_b,
    }


# ---------------------------------------------------------------------------
# A1 (T-A1): fechamento do ano só no 4º trimestre; controle só com o 4º trimestre iniciado
# ---------------------------------------------------------------------------


def test_t_a1_fechamento_so_existe_no_quarto_trimestre(presumido, escritorio_a, usuario_gestor_a):
    empresa = presumido["empresa"]
    _ano_com_caso_iii(empresa, usuario_gestor_a, escritorio_a)
    for trimestre in (1, 2, 3):
        apuracao = servico.apurar_trimestre(empresa, 2026, trimestre)
        assert apuracao.irpj is not None
        assert apuracao.fechamento_irpj is None
        assert apuracao.fechamento_csll is None
    quarto = servico.apurar_trimestre(empresa, 2026, 4)
    assert quarto.fechamento_irpj.caso == "III"
    assert quarto.fechamento_irpj.excedente_anual == D("1000000.00")
    assert quarto.fechamento_irpj.s == D("750000.00")
    assert quarto.fechamento_csll.caso == "III"
    assert quarto.fechamento_csll.excedente_anual == D("750000.00")
    assert quarto.fechamento_csll.s == D("500000.00")


def test_t_a1_controle_so_mostra_fechamento_com_o_quarto_trimestre_iniciado(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    _ano_com_caso_iii(empresa, usuario_gestor_a, escritorio_a)
    # Ano em curso sem o 4º trimestre: sem fechamento, sem dedução e sem diferença de recálculo.
    em_curso = servico.controle_limite_ano(empresa, 2026, "irpj", hoje=date(2026, 9, 30))
    assert em_curso.fechamento is None
    assert em_curso.deducao_quarto_trimestre == D("0.00")
    assert all(linha.diferenca_recalculo is None for linha in em_curso.linhas)
    # Com o 4º trimestre iniciado (1º de outubro), o caso sai.
    iniciado = servico.controle_limite_ano(empresa, 2026, "irpj", hoje=date(2026, 10, 1))
    assert iniciado.fechamento.caso == "III"


def test_t_a1_tela_nao_mostra_fechamento_antes_do_quarto_trimestre(
    client, presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    _ano_com_caso_iii(empresa, usuario_gestor_a, escritorio_a)
    client.force_login(usuario_gestor_a)
    for trimestre in (1, 2, 3):
        html = client.get(
            _url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=trimestre)
        ).content.decode("utf-8")
        assert "Fechamento do ano" not in html
    html = client.get(
        _url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=4)
    ).content.decode("utf-8")
    assert "Fechamento do ano" in html


def test_t_a1_api_fechamento_nulo_de_t1_a_t3(client, presumido, escritorio_a, usuario_gestor_a):
    empresa = presumido["empresa"]
    _ano_com_caso_iii(empresa, usuario_gestor_a, escritorio_a)
    client.force_login(usuario_gestor_a)
    for trimestre in (1, 2, 3):
        corpo = client.get(_api(empresa, f"apuracao/?ano=2026&trimestre={trimestre}")).json()
        assert corpo["fechamento_irpj"] is None and corpo["fechamento_csll"] is None
    corpo = client.get(_api(empresa, "apuracao/?ano=2026&trimestre=4")).json()
    assert corpo["fechamento_irpj"]["caso"] == "III"


# ---------------------------------------------------------------------------
# A2 e A14 (T-A2): entrada estranha responde 400 e nunca 500, na API e na tela, pela mesma porta
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario(presumido, escritorio_a, usuario_gestor_a):
    empresa = presumido["empresa"]
    servicos = _atividade(empresa, usuario_gestor_a, SERVICOS)
    receita = _receita(empresa, usuario_gestor_a, 1, "1000.00", servicos, "suporte-base")
    medida = servico.cadastrar_medida(
        empresa,
        {
            "tributo": "irpj",
            "ano_inicial": 2026,
            "trimestre_inicial": 1,
            "numero_processo": "proc-ficticio-c",
            "orgao": "Vara fictícia",
            "data_decisao": "2026-03-01",
            "suporte": "decisão sintética",
        },
        usuario_gestor_a,
    )
    escrituracao = _nota(
        escritorio_a, empresa, usuario_gestor_a, 1201, "5000.00", "2026-01-20", ret_irrf="100.00"
    )
    return {
        "empresa": empresa,
        "usuario": usuario_gestor_a,
        "atividade": servicos,
        "receita": receita,
        "medida": medida,
        "escrituracao": escrituracao,
    }


def _corpo_receita(c, **alterados):
    corpo = {
        "ano": 2026,
        "trimestre": 1,
        "tipo": "presuncao",
        "atividade_id": c["atividade"].pk,
        "valor": "100.00",
        "descricao": "descrição sintética",
        "suporte": "suporte sintético",
    }
    corpo.update(alterados)
    return corpo


def _corpo_medida(**alterados):
    corpo = {
        "tributo": "irpj",
        "ano_inicial": 2026,
        "trimestre_inicial": 1,
        "ano_final": None,
        "trimestre_final": None,
        "numero_processo": "proc-ficticio-d",
        "orgao": "Vara fictícia",
        "data_decisao": "2026-03-01",
        "deposito_judicial": False,
        "suporte": "decisão sintética",
    }
    corpo.update(alterados)
    return corpo


# Os 12 primeiros são os vetores da API do relatório (A2); os demais são do A14.
VETORES_API = [
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, valor="99999999999999.99")),
        id="a2-valor-14-digitos-receitas",
    ),
    pytest.param(
        lambda c: (
            "retencoes/",
            {
                "escrituracao_id": c["escrituracao"].pk,
                "irrf_confirmado": "99999999999999.99",
                "csll_confirmada": None,
                "motivo": "",
            },
        ),
        id="a2-valor-14-digitos-retencoes",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, descricao=f"a{NUL}b")),
        id="a2-nul-descricao",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, suporte=f"a{NUL}b")),
        id="a2-nul-suporte",
    ),
    pytest.param(
        lambda c: (f"receitas/{c['receita'].pk}/estornar/", {"motivo": f"x{NUL}"}),
        id="a2-nul-motivo-estorno",
    ),
    pytest.param(
        lambda c: (
            "retencoes/",
            {
                "escrituracao_id": c["escrituracao"].pk,
                "irrf_confirmado": "50.00",
                "csll_confirmada": None,
                "motivo": f"x{NUL}",
            },
        ),
        id="a2-nul-motivo-retencao",
    ),
    pytest.param(
        lambda c: (f"medidas/{c['medida'].pk}/revogar/", {"motivo": f"x{NUL}"}),
        id="a2-nul-motivo-revogacao",
    ),
    pytest.param(
        lambda c: ("integrais/", {"ano": 2026, "trimestre": 1, "observacao": f"x{NUL}"}),
        id="a2-nul-observacao-integrais",
    ),
    pytest.param(
        lambda c: ("medidas/", _corpo_medida(numero_processo=f"x{NUL}")),
        id="a2-nul-numero-processo",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, atividade_id="abc")),
        id="a2-atividade-texto",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, atividade_id=[1])),
        id="a2-atividade-lista",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, atividade_id={"a": 1})),
        id="a2-atividade-dict",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, atividade_id=1.5)),
        id="a14-atividade-decimal",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, atividade_id=True)),
        id="a14-atividade-booleano",
    ),
    pytest.param(
        lambda c: ("receitas/", _corpo_receita(c, ano=2026.0)),
        id="a14-ano-decimal",
    ),
    pytest.param(
        lambda c: ("medidas/", _corpo_medida(data_decisao="0001-01-01")),
        id="a14-data-decisao-0001",
    ),
    pytest.param(
        lambda c: (
            "atividades/",
            {"atividade": SERVICOS, "inicio": "2026-01-01", "fim": "9999-12-31", "padrao": False},
        ),
        id="a14-fim-atividade-9999",
    ),
    pytest.param(
        lambda c: (
            "atividades/",
            {"atividade": SERVICOS, "inicio": "0001-01-01", "padrao": False},
        ),
        id="a14-inicio-atividade-0001",
    ),
]


@pytest.mark.parametrize("vetor", VETORES_API)
def test_t_a2_api_entrada_estranha_responde_400_e_nao_grava(vetor, client, cenario):
    empresa = cenario["empresa"]
    sufixo, corpo = vetor(cenario)
    client.force_login(cenario["usuario"])
    antes = _estado(empresa)
    resposta = _post_json(client, _api(empresa, sufixo), corpo)
    assert resposta.status_code == 400, resposta.content[:300]
    assert _estado(empresa) == antes


VETORES_TELA = [
    pytest.param("receita", {"valor": "99999999999999,99"}, id="a2-tela-valor-14-digitos"),
    pytest.param("receita", {"descricao": f"a{NUL}b"}, id="a2-tela-nul-descricao"),
    pytest.param("integrais", {"observacao": f"a{NUL}b"}, id="a2-tela-nul-observacao"),
]


@pytest.mark.parametrize("tela, alterados", VETORES_TELA)
def test_t_a2_tela_entrada_estranha_responde_400_e_nao_grava(tela, alterados, client, cenario):
    empresa = cenario["empresa"]
    client.force_login(cenario["usuario"])
    if tela == "receita":
        url = reverse("fiscal_web:presumido_receita_nova", args=[empresa.pk])
        dados = {
            "ano": "2026",
            "trimestre": "1",
            "tipo": "presuncao",
            "atividade_id": str(cenario["atividade"].pk),
            "valor": "100,00",
            "descricao": "d",
            "suporte": "s",
        }
    else:
        url = reverse("fiscal_web:presumido_integrais_declarar", args=[empresa.pk])
        dados = {"ano": "2026", "trimestre": "1", "observacao": "", "modo": ""}
    dados.update(alterados)
    antes = _estado(empresa)
    resposta = client.post(url, dados)
    assert resposta.status_code == 400
    assert _estado(empresa) == antes


def test_t_a2_servico_recusa_os_mesmos_vetores_antes_de_gravar(presumido, usuario_gestor_a):
    empresa = presumido["empresa"]
    antes = _estado(empresa)
    casos = [
        lambda: servico.criar_receita(
            empresa,
            2026,
            1,
            {"tipo": "integral", "valor": "99999999999999.99", "suporte": "s", "descricao": "d"},
            usuario_gestor_a,
        ),
        lambda: servico.criar_receita(
            empresa,
            2026,
            1,
            {"tipo": "integral", "valor": "1" * 40, "suporte": "s", "descricao": "d"},
            usuario_gestor_a,
        ),
        lambda: servico.criar_receita(
            empresa,
            2026,
            1,
            {"tipo": "integral", "valor": "10.00", "suporte": "s", "descricao": f"d{NUL}"},
            usuario_gestor_a,
        ),
        lambda: servico.declarar_receitas_integrais(
            empresa, 2026, 1, f"obs{NUL}", usuario_gestor_a
        ),
        lambda: servico.estornar_receita(empresa, True, "x", usuario_gestor_a),
        lambda: servico.encerrar_atividade(empresa, "7x", date(2026, 6, 30), usuario_gestor_a),
        lambda: servico.confirmar_retencao(empresa, "abc", "1.00", None, "", usuario_gestor_a),
        lambda: servico.revogar_medida(empresa, 1.5, "x", usuario_gestor_a),
        lambda: servico.definir_criterio(empresa, 2026.0, "competencia", usuario_gestor_a),
        lambda: servico.cadastrar_medida(
            empresa, _corpo_medida(data_decisao="9999-12-31"), usuario_gestor_a
        ),
    ]
    for caso in casos:
        with pytest.raises(servico.EntradaInvalidaPresumido):
            caso()
    assert _estado(empresa) == antes


def test_t_a2_valor_no_teto_do_campo_e_aceito(presumido, usuario_gestor_a):
    # O teto é 9.999.999.999.999,99 (13 dígitos inteiros): o limite exato passa; um centavo a
    # mais, não.
    receita = servico.criar_receita(
        presumido["empresa"],
        2026,
        1,
        {"tipo": "integral", "valor": "9999999999999.99", "suporte": "s", "descricao": "d"},
        usuario_gestor_a,
    )
    assert receita.valor == D("9999999999999.99")
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_receita(
            presumido["empresa"],
            2026,
            1,
            {"tipo": "integral", "valor": "10000000000000.00", "suporte": "s2", "descricao": "d"},
            usuario_gestor_a,
        )


def test_a14_datas_fora_de_1900_a_2100_sao_recusadas(presumido, usuario_gestor_a):
    empresa = presumido["empresa"]
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_atividade(
            empresa,
            {"atividade": SERVICOS, "inicio": "1899-12-31", "padrao": False},
            usuario_gestor_a,
        )
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.cadastrar_medida(
            empresa, _corpo_medida(data_decisao="2101-01-01"), usuario_gestor_a
        )
    # Limites inclusivos: 1º de janeiro de 1900 e 31 de dezembro de 2100 são datas válidas.
    atividade = servico.criar_atividade(
        empresa,
        {"atividade": SERVICOS, "inicio": "1900-01-01", "fim": "2100-12-31", "padrao": False},
        usuario_gestor_a,
    )
    assert atividade.fim == date(2100, 12, 31)


# ---------------------------------------------------------------------------
# A3 (T-A3): receita igual à ativa é recusada com a existente nomeada; estornada, a segunda passa
# ---------------------------------------------------------------------------


def test_t_a3_receita_igual_e_recusada_e_nomeia_a_existente(presumido, usuario_gestor_a):
    empresa = presumido["empresa"]
    servicos = _atividade(empresa, usuario_gestor_a, SERVICOS)
    primeira = _receita(empresa, usuario_gestor_a, 1, "100000.00", servicos, "NF suporte 1")
    with pytest.raises(servico.PresumidoConflito) as excinfo:
        _receita(empresa, usuario_gestor_a, 1, "100000.00", servicos, "NF suporte 1")
    assert f"receita nº {primeira.pk}" in excinfo.value.mensagem
    assert servico.apurar_trimestre(empresa, 2026, 1).irpj.receita_presumida == D("100000.00")
    # Outro documento de suporte é outra receita, não duplicata.
    _receita(empresa, usuario_gestor_a, 1, "100000.00", servicos, "NF suporte 2")
    assert servico.apurar_trimestre(empresa, 2026, 1).irpj.receita_presumida == D("200000.00")


def test_t_a3_depois_de_estornar_a_primeira_a_segunda_passa(presumido, usuario_gestor_a):
    empresa = presumido["empresa"]
    servicos = _atividade(empresa, usuario_gestor_a, SERVICOS)
    primeira = _receita(empresa, usuario_gestor_a, 1, "100000.00", servicos, "NF suporte 1")
    servico.estornar_receita(empresa, primeira.pk, "lançada duas vezes", usuario_gestor_a)
    segunda = _receita(empresa, usuario_gestor_a, 1, "100000.00", servicos, "NF suporte 1")
    assert segunda.estado == "ativa"
    assert servico.apurar_trimestre(empresa, 2026, 1).irpj.receita_presumida == D("100000.00")


def test_t_a3_api_e_tela_recusam_o_reenvio_com_409(client, presumido, usuario_gestor_a):
    empresa = presumido["empresa"]
    servicos = _atividade(empresa, usuario_gestor_a, SERVICOS)
    client.force_login(usuario_gestor_a)
    corpo = _corpo_receita({"atividade": servicos}, valor="100000.00", suporte="NF API")
    assert _post_json(client, _api(empresa, "receitas/"), corpo).status_code == 201
    segundo = _post_json(client, _api(empresa, "receitas/"), corpo)
    assert segundo.status_code == 409
    assert "receita nº" in segundo.json()["detail"]
    url = reverse("fiscal_web:presumido_receita_nova", args=[empresa.pk])
    dados = {
        "ano": "2026",
        "trimestre": "1",
        "tipo": "presuncao",
        "atividade_id": str(servicos.pk),
        "valor": "100000,00",
        "descricao": "d",
        "suporte": "NF TELA",
    }
    assert client.post(url, dados).status_code == 302
    resposta = client.post(url, dados)
    assert resposta.status_code == 409
    assert "receita nº" in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# A4 (T-A4a a T-A4i): isolamento, resíduos, meses do adicional, medida só da CSLL e 3º mês
# ---------------------------------------------------------------------------


def test_t_a4a_a_apuracao_de_a_so_ve_o_que_e_de_a(duas_clientes, escritorio_a, usuario_gestor_a):
    d = duas_clientes
    ap = servico.apurar_trimestre(d["a"], 2026, 1)
    assert ap.irpj.receita_presumida == D("100000.00")
    assert ap.irpj.receitas_integrais == D("1000.00")
    assert ap.irpj.base_sem_lc224 == D("33000.00")
    assert ap.irpj.imposto_sem_lc224 == D("4950.00")
    assert ap.irpj.retencao_confirmada == D("0.00")
    assert ap.irpj.medida == "nenhuma"
    assert ap.declaracao_total == D("1000.00") and ap.declaracao_valida
    # B existe de verdade e tem tudo o que A não pode herdar.
    bp = servico.apurar_trimestre(d["b"], 2026, 1)
    assert bp.irpj.receita_presumida == D("3500000.00")
    assert bp.irpj.receitas_integrais == D("7000.00")
    assert bp.irpj.retencao_confirmada == D("900.00")
    assert bp.irpj.medida == "suspensa"


def test_t_a4b_atividade_padrao_e_por_empresa(presumido, cliente_b, escritorio_a, usuario_gestor_a):
    # A tem padrão de COMÉRCIO (8%, fixture). B recebe padrão de SERVIÇOS (32%) DEPOIS, com id
    # maior.
    # A nota de A tem de usar a padrão de A: 100.000 x 8% = 8.000,00 de base. Com o filtro de
    # empresa tirado, a padrão de B (mais nova) é a escolhida e a base vira 32.000,00.
    empresa = presumido["empresa"]
    _presumida(cliente_b, usuario_gestor_a, SERVICOS)
    _nota(escritorio_a, empresa, usuario_gestor_a, 1601, "100000.00", "2026-01-15")
    ap = servico.apurar_trimestre(empresa, 2026, 1)
    assert ap.irpj.base_sem_lc224 == D("8000.00")
    assert [linha.atividade for linha in ap.irpj.memoria_sem_lc224] == [COMERCIO]


def test_t_a4c_ato_de_outra_empresa_do_mesmo_escritorio_responde_404_e_nao_muda(
    client, duas_clientes, usuario_gestor_a
):
    d = duas_clientes
    client.force_login(usuario_gestor_a)
    antes_a = _estado(d["a"])
    antes_b = _estado(d["b"])
    confirmacoes_a = ConfirmacaoRetencaoPresumido.objects.filter(escrituracao=d["nota_a"]).count()
    casos = [
        (
            "api",
            _api(d["b"], f"atividades/{d['atividade_a_extra'].pk}/encerrar/"),
            {"fim": "2026-06-30"},
        ),
        ("api", _api(d["b"], f"receitas/{d['receita_a'].pk}/estornar/"), {"motivo": "x"}),
        ("api", _api(d["b"], f"medidas/{d['medida_a'].pk}/revogar/"), {"motivo": "x"}),
        (
            "api",
            _api(d["b"], "retencoes/"),
            {
                "escrituracao_id": d["nota_a"].pk,
                "irrf_confirmado": "123.00",
                "csll_confirmada": None,
                "motivo": "",
            },
        ),
    ]
    for _tipo, url, corpo in casos:
        assert _post_json(client, url, corpo).status_code == 404, url
    telas = [
        (
            reverse(
                "fiscal_web:presumido_atividade_encerrar",
                args=[d["b"].pk, d["atividade_a_extra"].pk],
            ),
            {"fim": "30/06/2026"},
        ),
        (
            reverse("fiscal_web:presumido_receita_estornar", args=[d["b"].pk, d["receita_a"].pk]),
            {"motivo": "x"},
        ),
        (
            reverse("fiscal_web:presumido_medida_revogar", args=[d["b"].pk, d["medida_a"].pk]),
            {"motivo": "x"},
        ),
        (
            reverse("fiscal_web:presumido_retencao_confirmar", args=[d["b"].pk, d["nota_a"].pk]),
            {"ano": "2026", "trimestre": "1", "irrf_confirmado": "123,00", "motivo": ""},
        ),
    ]
    for url, dados in telas:
        assert client.post(url, dados).status_code == 404, url
    assert _estado(d["a"]) == antes_a
    assert _estado(d["b"]) == antes_b
    assert (
        ConfirmacaoRetencaoPresumido.objects.filter(escrituracao=d["nota_a"]).count()
        == confirmacoes_a
    )


def test_t_a4c_servico_nao_age_sobre_registro_de_outra_empresa(duas_clientes, usuario_gestor_a):
    d = duas_clientes
    with pytest.raises(servico.NaoEncontradoPresumido):
        servico.estornar_receita(d["b"], d["receita_a"].pk, "x", usuario_gestor_a)
    with pytest.raises(servico.NaoEncontradoPresumido):
        servico.revogar_medida(d["b"], d["medida_a"].pk, "x", usuario_gestor_a)
    with pytest.raises(servico.NaoEncontradoPresumido):
        servico.encerrar_atividade(
            d["b"], d["atividade_a_extra"].pk, date(2026, 6, 30), usuario_gestor_a
        )
    with pytest.raises(servico.NaoEncontradoPresumido):
        servico.confirmar_retencao(d["b"], d["nota_a"].pk, "1.00", None, "", usuario_gestor_a)
    d["receita_a"].refresh_from_db()
    d["medida_a"].refresh_from_db()
    d["atividade_a_extra"].refresh_from_db()
    assert d["receita_a"].estado == "ativa"
    assert d["medida_a"].ativa is True
    assert d["atividade_a_extra"].fim is None


def test_t_a4d_listagens_nao_trazem_linhas_de_outra_empresa(duas_clientes):
    d = duas_clientes
    receitas_a = {r.pk for r in servico.listar_receitas(d["a"], 2026, 1)}
    assert d["receita_a"].pk in receitas_a
    assert d["receita_b"].pk not in receitas_a
    atividades_a = {x.pk for x in servico.listar_atividades(d["a"])}
    assert d["atividade_b"].pk not in atividades_a and d["padrao_b"].pk not in atividades_a
    medidas_a = {m.pk for m in servico.listar_medidas(d["a"])}
    assert d["medida_a"].pk in medidas_a and d["medida_b"].pk not in medidas_a


def test_t_a4e_meses_do_adicional_pelo_servico(presumido, escritorio_a, usuario_gestor_a):
    # Empresa aberta em 15/05/2026: o mês da abertura conta inteiro (HIPÓTESE do módulo). T2 tem
    # maio e junho (2 meses), T3 e T4 têm 3. Receita de serviços de 2.800.000,00 em T2 a T4:
    # base sem LC 224 = 2.800.000 x 32% = 896.000,00; adicional de IRPJ =
    # (896.000 − 20.000 x meses) x 10%.
    empresa = presumido["empresa"]
    empresa.data_abertura_cnpj = date(2026, 5, 15)
    empresa.save(update_fields=["data_abertura_cnpj"])
    servicos = _atividade(empresa, usuario_gestor_a, SERVICOS)
    for trimestre in (2, 3, 4):
        _receita(empresa, usuario_gestor_a, trimestre, "2800000.00", servicos, f"serv T{trimestre}")
    t2 = servico.apurar_trimestre(empresa, 2026, 2)
    assert t2.irpj.linhas_do_ano[1].sem_lc224.meses == 2
    assert t2.irpj.linhas_do_ano[1].sem_lc224.adicional == D("85600.00")
    t3 = servico.apurar_trimestre(empresa, 2026, 3)
    assert t3.irpj.linhas_do_ano[2].sem_lc224.meses == 3
    assert t3.irpj.linhas_do_ano[2].sem_lc224.adicional == D("83600.00")
    t4 = servico.apurar_trimestre(empresa, 2026, 4)
    assert t4.fechamento_irpj.n == 3


def test_t_a4f_residuo_do_rateio_no_trimestre(presumido, escritorio_a, usuario_gestor_a):
    # Comércio 1.264.058,77; serviços 1.222.522,33; intermediação 287.516,72. Total 2.774.097,82;
    # excedente 1.524.097,82. Rateio: 694.477,75 + 671.657,50 + 157.962,57 (o resíduo fica na
    # última).
    empresa = presumido["empresa"]
    _nota(escritorio_a, empresa, usuario_gestor_a, 1701, "1264058.77", "2026-01-15")
    servicos = _atividade(empresa, usuario_gestor_a, SERVICOS)
    intermediacao = _atividade(empresa, usuario_gestor_a, INTERMEDIACAO)
    _receita(empresa, usuario_gestor_a, 1, "1222522.33", servicos, "serv rateio")
    _receita(empresa, usuario_gestor_a, 1, "287516.72", intermediacao, "int rateio")
    ap = servico.apurar_trimestre(empresa, 2026, 1)
    assert [linha.excedente for linha in ap.irpj.memoria_com_lc224] == [
        D("694477.75"),
        D("671657.50"),
        D("157962.57"),
    ]


def test_t_a4g_residuo_do_caso_ii_no_quarto_trimestre(presumido, escritorio_a, usuario_gestor_a):
    # IRPJ, comércio: T1 2.336.044,50; T2 1.842.852,49; T3 2.495.609,64; T4 531.218,21.
    # E1 = 1.086.044,50; E2 = 592.852,49; E3 = 1.245.609,64. ExcAnual = 7.205.724,84 − 5.000.000 =
    # 2.205.724,84. S = 2.924.506,63. 2.205.724,84 < 2.924.506,63: caso II.
    empresa = presumido["empresa"]
    for trimestre, valor in [
        (1, "2336044.50"),
        (2, "1842852.49"),
        (3, "2495609.64"),
        (4, "531218.21"),
    ]:
        _nota(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            1800 + trimestre,
            valor,
            f"2026-{3 * trimestre - 2:02d}-15",
        )
    quarto = servico.apurar_trimestre(empresa, 2026, 4)
    assert quarto.fechamento_irpj.caso == "II"
    assert quarto.fechamento_irpj.excedente_anual == D("2205724.84")
    assert quarto.fechamento_irpj.s == D("2924506.63")
    # E' dos três primeiros trimestres somam exatamente o excedente anual (o resíduo vai no último).
    assert sum((linha.excedente_ajustado for linha in quarto.irpj.linhas_do_ano[:3]), D("0")) == (
        D("2205724.84")
    )
    assert quarto.irpj.deducao_quarto_trimestre == D("1437.56")


def test_t_a4h_medida_so_da_csll_nao_suspende_o_irpj(presumido, escritorio_a, usuario_gestor_a):
    # T1 de 1.300.000,00 (IRPJ com E1 = 50.000,00); T2 de 2.000.000,00 (E2 = 750.000,00 nos dois
    # tributos; a CSLL não tem o T1). Parcela da CSLL no T2 (LC 224): (1.250.000 x 12% + 750.000 x
    # 13,2%) x 9% − 2.000.000 x 12% x 9% = 22.410,00 − 21.600,00 = 810,00.
    empresa = presumido["empresa"]
    _nota(escritorio_a, empresa, usuario_gestor_a, 1901, "1300000.00", "2026-01-15")
    _nota(escritorio_a, empresa, usuario_gestor_a, 1902, "2000000.00", "2026-04-15")
    servico.cadastrar_medida(
        empresa,
        {
            "tributo": "csll",
            "ano_inicial": 2026,
            "trimestre_inicial": 2,
            "numero_processo": "proc-ficticio-h",
            "orgao": "Vara fictícia",
            "data_decisao": "2026-04-01",
            "suporte": "decisão sintética",
        },
        usuario_gestor_a,
    )
    ap = servico.apurar_trimestre(empresa, 2026, 2)
    assert ap.irpj.medida == "nenhuma"
    assert ap.irpj.valor_suspenso is None
    assert ap.csll.medida == "suspensa"
    assert ap.csll.valor_suspenso == D("810.00")


def test_t_a4i_terceiro_mes_do_trimestre_entra_no_trimestre(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    _nota(escritorio_a, empresa, usuario_gestor_a, 2001, "1000.00", "2026-03-31")
    _nota(escritorio_a, empresa, usuario_gestor_a, 2002, "2000.00", "2026-04-02")
    assert servico.apurar_trimestre(empresa, 2026, 1).irpj.receita_presumida == D("1000.00")
    assert servico.apurar_trimestre(empresa, 2026, 2).irpj.receita_presumida == D("2000.00")


def test_t_a5_consultas_da_apuracao_nao_crescem_com_o_numero_de_notas(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]

    def contar_consultas():
        with CaptureQueriesContext(connection) as contexto:
            servico.apurar_trimestre(empresa, 2026, 1)
        return len(contexto.captured_queries)

    for sufixo in range(5):
        _nota(escritorio_a, empresa, usuario_gestor_a, 2100 + sufixo, "1000.00", "2026-01-10")
    com_5 = contar_consultas()
    for sufixo in range(5, 55):
        _nota(escritorio_a, empresa, usuario_gestor_a, 2100 + sufixo, "1000.00", "2026-01-10")
    com_55 = contar_consultas()
    assert com_5 == com_55


def test_m05_retencao_proposta_nao_confirmada_nao_deduz_no_irpj_nem_na_csll(
    presumido, escritorio_a, usuario_gestor_a
):
    # Comércio de 100.000,00: IRPJ 8% x 15% = 1.200,00; CSLL 12% x 9% = 1.080,00. A nota propõe
    # IRRF de 1.500,00 e CSLL exata de 1.000,00, mas nada é confirmado: nada pode deduzir.
    empresa = presumido["empresa"]
    nota = _nota(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        2201,
        "100000.00",
        "2026-01-20",
        tp_ret="8",
        ret_irrf="1500.00",
        ret_csll="1000.00",
    )
    proposta = servico.retencoes_do_trimestre(empresa, 2026, 1)
    assert proposta[0].irrf_proposto == D("1500.00") and proposta[0].csll_proposta == D("1000.00")
    ap = servico.apurar_trimestre(empresa, 2026, 1)
    assert ap.irpj.retencao_confirmada == D("0.00")
    assert ap.csll.retencao_confirmada == D("0.00")
    assert ap.irpj.a_recolher == D("1200.00")
    assert ap.csll.a_recolher == D("1080.00")
    assert nota.pk in {n.escrituracao_id for n in ap.notas}


# ---------------------------------------------------------------------------
# A5: a anotação `cancelada` alimenta a leitura; o cancelamento segue valendo
# ---------------------------------------------------------------------------


def test_a5_nota_cancelada_continua_fora_da_base_com_a_anotacao(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    _nota(escritorio_a, empresa, usuario_gestor_a, 2301, "1000.00", "2026-01-10")
    cancelada = receber_prestada(
        escritorio_a, usuario_gestor_a, 2302, v_serv="9000.00", d_compet="2026-01-11"
    )
    efetivar_prestada(cancelada, empresa, usuario_gestor_a)
    cancelar(escritorio_a, usuario_gestor_a, cancelada, sufixo_evento=9)
    assert servico.apurar_trimestre(empresa, 2026, 1).irpj.receita_presumida == D("1000.00")


# ---------------------------------------------------------------------------
# A6: a API expõe a composição do limite e do fechamento, como a tela
# ---------------------------------------------------------------------------


def test_a6_api_e_tela_mostram_a_mesma_suspensao_do_limite(
    client, presumido, escritorio_a, usuario_gestor_a, monkeypatch
):
    monkeypatch.setattr(servico, "_hoje", lambda: date(2026, 12, 31))
    empresa = presumido["empresa"]
    _ano_com_caso_iii(empresa, usuario_gestor_a, escritorio_a)
    servico.cadastrar_medida(
        empresa,
        {
            "tributo": "irpj",
            "ano_inicial": 2026,
            "trimestre_inicial": 2,
            "numero_processo": "proc-ficticio-a6",
            "orgao": "Vara fictícia",
            "data_decisao": "2026-04-01",
            "suporte": "decisão sintética",
        },
        usuario_gestor_a,
    )
    client.force_login(usuario_gestor_a)
    corpo = client.get(_api(empresa, "limite/?ano=2026&tributo=irpj")).json()
    linhas = corpo["linhas"]
    suspensas = [linha["suspensa_por_medida"] for linha in linhas]
    assert suspensas == [False, True, True, True]
    assert linhas[0]["diferenca_recalculo"] == "0.00"
    assert [t["suspensa_por_medida"] for t in corpo["fechamento"]["trimestres"]] == suspensas
    html = client.get(_url("presumido_limite", empresa=empresa.pk, ano=2026, tributo="irpj"))
    texto = html.content.decode("utf-8")
    assert texto.count(TEXTO_SUSPENSO) == sum(suspensas)
    # A apuração do 4º trimestre expõe a mesma composição (lista por trimestre no fechamento).
    apuracao = client.get(_api(empresa, "apuracao/?ano=2026&trimestre=4")).json()
    assert [t["trimestre"] for t in apuracao["fechamento_irpj"]["trimestres"]] == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# A7 (T-A7): gatilhos de imutabilidade por SQL direto
# ---------------------------------------------------------------------------


def _sql(sql, params):
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_a7_atividade_so_aceita_o_encerramento_por_sql(presumido):
    atividade = presumido["padrao"]
    recusados = [
        (
            "UPDATE fiscal_atividadepresuncaoempresa SET padrao = false WHERE id = %s",
            [atividade.pk],
        ),
        (
            "UPDATE fiscal_atividadepresuncaoempresa SET atividade = 'servicos_gerais' "
            "WHERE id = %s",
            [atividade.pk],
        ),
        (
            "UPDATE fiscal_atividadepresuncaoempresa SET inicio = '2025-01-01' WHERE id = %s",
            [atividade.pk],
        ),
        ("DELETE FROM fiscal_atividadepresuncaoempresa WHERE id = %s", [atividade.pk]),
    ]
    for sql, params in recusados:
        with pytest.raises(IntegrityError):
            _sql(sql, params)
    # Encerrar (preencher `fim` quando ele é nulo) é a única mudança permitida.
    _sql(
        "UPDATE fiscal_atividadepresuncaoempresa SET fim = '2026-06-30' WHERE id = %s",
        [atividade.pk],
    )
    atividade.refresh_from_db()
    assert atividade.fim == date(2026, 6, 30)
    # Depois de encerrada, nem o fim muda.
    with pytest.raises(IntegrityError):
        _sql(
            "UPDATE fiscal_atividadepresuncaoempresa SET fim = '2026-07-31' WHERE id = %s",
            [atividade.pk],
        )


def test_a7_criterio_nao_muda_nem_se_apaga_por_sql(presumido):
    criterio = CriterioReceitaPresumido.objects.get(empresa=presumido["empresa"], ano=2026)
    with pytest.raises(IntegrityError):
        _sql(
            "UPDATE fiscal_criterioreceitapresumido SET criterio = 'caixa' WHERE id = %s",
            [criterio.pk],
        )
    with pytest.raises(IntegrityError):
        _sql("DELETE FROM fiscal_criterioreceitapresumido WHERE id = %s", [criterio.pk])
    criterio.refresh_from_db()
    assert criterio.criterio == "competencia"


# ---------------------------------------------------------------------------
# A8: dois planos de quota, nos limites 1.999,99; 2.000,00; 2.999,99 e 3.000,00
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "devido, duas, tres",
    [
        ("1999.99", None, None),
        ("2000.00", ["1000.00", "1000.00"], None),
        ("2999.99", ["1500.00", "1499.99"], None),
        ("3000.00", ["1500.00", "1500.00"], ["1000.00", "1000.00", "1000.00"]),
    ],
)
def test_a8_planos_de_quota_nos_limites(devido, duas, tres):
    opcoes = calc.opcoes_de_quota(D(devido), 2026, 1)
    assert len(opcoes.quota_unica) == 1
    if duas is None:
        assert opcoes.duas_quotas is None and opcoes.motivo_sem_duas_quotas
    else:
        assert [p.valor for p in opcoes.duas_quotas] == [D(v) for v in duas]
        assert opcoes.motivo_sem_duas_quotas is None
    if tres is None:
        assert opcoes.tres_quotas is None and opcoes.motivo_sem_tres_quotas
    else:
        assert [p.valor for p in opcoes.tres_quotas] == [D(v) for v in tres]
        assert opcoes.motivo_sem_tres_quotas is None


def test_a8_motivos_nomeados_dos_planos():
    dois_mil = calc.opcoes_de_quota(D("2000.00"), 2026, 1)
    assert "abaixo de R$ 1.000,00" in dois_mil.motivo_sem_tres_quotas
    assert "R$ 3.000,00" in dois_mil.motivo_sem_tres_quotas
    abaixo = calc.opcoes_de_quota(D("1999.99"), 2026, 1)
    assert abaixo.motivo_sem_duas_quotas == "Imposto abaixo de R$ 2.000,00: só quota única."


def test_a8_juros_das_duas_quotas_e_residuo_na_segunda():
    # 2.000,01: a primeira leva o arredondamento para cima (1.000,01) e a segunda, 1.000,00.
    opcoes = calc.opcoes_de_quota(D("2000.01"), 2026, 1)
    assert [p.valor for p in opcoes.duas_quotas] == [D("1000.01"), D("1000.00")]
    assert [p.juros for p in opcoes.duas_quotas] == ["sem juros", "1%"]
    assert sum(p.valor for p in opcoes.duas_quotas) == D("2000.01")


def test_a8_apuracao_oferece_duas_quotas_e_a_tela_mostra(
    client, presumido, escritorio_a, usuario_gestor_a
):
    # Serviços de 50.000,00 no 1º trimestre: IRPJ 50.000 x 32% x 15% = 2.400,00, sem adicional.
    # Duas quotas de 1.200,00; três quotas indisponíveis (a menor ficaria em 800,00).
    empresa = presumido["empresa"]
    servicos = _atividade(empresa, usuario_gestor_a, SERVICOS)
    _receita(empresa, usuario_gestor_a, 1, "50000.00", servicos, "serv quota")
    ap = servico.apurar_trimestre(empresa, 2026, 1)
    assert ap.irpj.a_recolher == D("2400.00")
    assert [p.valor for p in ap.irpj.quotas.duas_quotas] == [D("1200.00"), D("1200.00")]
    assert ap.irpj.quotas.tres_quotas is None
    client.force_login(usuario_gestor_a)
    corpo = client.get(_api(empresa, "apuracao/?ano=2026&trimestre=1")).json()
    assert [p["valor"] for p in corpo["irpj"]["quotas"]["duas_quotas"]] == ["1200.00", "1200.00"]
    assert "abaixo de R$ 1.000,00" in corpo["irpj"]["quotas"]["motivo_sem_tres_quotas"]
    html = client.get(
        _url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=1)
    ).content.decode("utf-8")
    assert "Duas quotas" in html
    assert "Plano de três quotas indisponível" in html


# ---------------------------------------------------------------------------
# A10: rótulo completo do serviço hospitalar; a ESC nomeada, fora do primeiro corte
# ---------------------------------------------------------------------------


def test_a10_rotulo_do_hospitalar_e_o_texto_do_inciso():
    assert tab.ATIVIDADES_POR_CODIGO[tab.SERVICOS_HOSPITALARES].rotulo == (
        "Serviços hospitalares e de auxílio diagnóstico e terapia, patologia clínica, "
        "imagenologia, anatomia patológica e citopatologia, medicina nuclear e análises e "
        "patologias clínicas"
    )


def test_a10_esc_e_nomeada_pelo_servico_na_recusa_de_atividade_fora_do_catalogo(
    presumido, usuario_gestor_a
):
    with pytest.raises(servico.EntradaInvalidaPresumido) as excinfo:
        servico.criar_atividade(
            presumido["empresa"],
            {"atividade": "empresa_simples_de_credito", "inicio": date(2026, 1, 1)},
            usuario_gestor_a,
        )
    assert "Empresa Simples de Crédito (38,4%, Lei 9.249, art. 15, § 1º, IV)" in (
        excinfo.value.mensagem
    )
    assert "não classifique como serviços em geral" in excinfo.value.mensagem


def test_a10_tela_de_atividades_nomeia_a_esc(client, presumido, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = client.get(_url("presumido_atividades", empresa=presumido["empresa"].pk)).content.decode(
        "utf-8"
    )
    assert tab.ESC_FORA_DO_PRIMEIRO_CORTE in html
    assert "Empresa Simples de Crédito (38,4%, Lei 9.249, art. 15, § 1º, IV)" in html


# ---------------------------------------------------------------------------
# A12: confirmar retenção só de nota que entra na apuração; API e tela recusam igual
# ---------------------------------------------------------------------------


@pytest.fixture
def notas_para_retencao(presumido, escritorio_a, usuario_gestor_a):
    """Nota de janeiro (dentro da atividade padrão) e nota de março (depois do fim da padrão,
    então sem atividade vigente), e uma nota de janeiro com XML inválido no desconto."""
    empresa = presumido["empresa"]
    servico.encerrar_atividade(empresa, presumido["padrao"].pk, date(2026, 2, 28), usuario_gestor_a)
    return {
        "boa": _nota(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            2401,
            "5000.00",
            "2026-01-20",
            ret_irrf="100.00",
        ),
        "sem_atividade": _nota(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            2402,
            "5000.00",
            "2026-03-20",
            ret_irrf="300.00",
        ),
        "xml_invalido": _nota(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            2403,
            "5000.00",
            "2026-01-21",
            ret_irrf="200.00",
            desc_incond="10.5",
        ),
    }


def test_a12_servico_recusa_nota_que_nao_entra_na_apuracao(
    presumido, notas_para_retencao, usuario_gestor_a
):
    empresa = presumido["empresa"]
    for chave in ("sem_atividade", "xml_invalido"):
        with pytest.raises(servico.EntradaInvalidaPresumido):
            servico.confirmar_retencao(
                empresa, notas_para_retencao[chave].pk, "100.00", None, "", usuario_gestor_a
            )
        assert not ConfirmacaoRetencaoPresumido.objects.filter(
            escrituracao=notas_para_retencao[chave]
        ).exists()
    # Controle: a nota que entra na apuração é confirmada normalmente.
    confirmacao = servico.confirmar_retencao(
        empresa, notas_para_retencao["boa"].pk, "100.00", None, "", usuario_gestor_a
    )
    assert confirmacao.irrf_confirmado == D("100.00")


def test_a12_api_recusa_com_400_e_nao_grava(
    client, presumido, notas_para_retencao, usuario_gestor_a
):
    empresa = presumido["empresa"]
    client.force_login(usuario_gestor_a)
    corpo = {
        "escrituracao_id": notas_para_retencao["sem_atividade"].pk,
        "irrf_confirmado": "300.00",
        "csll_confirmada": None,
        "motivo": "",
    }
    resposta = _post_json(client, _api(empresa, "retencoes/"), corpo)
    assert resposta.status_code == 400
    assert "não entra na apuração" in resposta.content.decode("utf-8")
    assert not ConfirmacaoRetencaoPresumido.objects.filter(
        escrituracao=notas_para_retencao["sem_atividade"]
    ).exists()


def test_a12_tela_recusa_com_400_com_a_mesma_mensagem_e_nao_404(
    client, presumido, notas_para_retencao, usuario_gestor_a
):
    empresa = presumido["empresa"]
    client.force_login(usuario_gestor_a)
    url = reverse(
        "fiscal_web:presumido_retencao_confirmar",
        args=[empresa.pk, notas_para_retencao["sem_atividade"].pk],
    )
    resposta = client.post(
        url, {"ano": "2026", "trimestre": "1", "irrf_confirmado": "300,00", "motivo": ""}
    )
    assert resposta.status_code == 400
    assert "não entra na apuração" in resposta.content.decode("utf-8")
    assert not ConfirmacaoRetencaoPresumido.objects.filter(
        escrituracao=notas_para_retencao["sem_atividade"]
    ).exists()


# ---------------------------------------------------------------------------
# Número de consultas e demais A2 (vetores de texto no serviço) já cobertos acima
# ---------------------------------------------------------------------------


def test_nota_de_outra_empresa_nao_confirma_por_id_mesmo_sendo_do_escritorio(
    duas_clientes, usuario_gestor_a
):
    d = duas_clientes
    with pytest.raises(servico.NaoEncontradoPresumido):
        servico.confirmar_retencao(d["b"], d["nota_a"].pk, "1.00", None, "", usuario_gestor_a)


def test_declaracao_sem_receitas_continua_recusada_com_integrais(presumido, usuario_gestor_a):
    # Regressão: a declaração "não houve" segue recusada quando há receitas integrais.
    empresa = presumido["empresa"]
    servico.criar_receita(
        empresa,
        2026,
        1,
        {"tipo": "integral", "valor": "10.00", "suporte": "s", "descricao": "d"},
        usuario_gestor_a,
    )
    with pytest.raises(servico.PresumidoConflito):
        servico.declarar_sem_receitas_integrais(empresa, 2026, 1, usuario_gestor_a)


def test_percentuais_do_catalogo_sao_fracoes_decimais():
    # Sem float: os percentuais e o resíduo da quota continuam Decimal.
    assert all(isinstance(a.irpj, D) and isinstance(a.csll, D) for a in tab.CATALOGO_ATIVIDADES)
    assert tab.ATIVIDADES_POR_CODIGO[COMERCIO].irpj == D("0.08")
    assert isinstance(calc.opcoes_de_quota(D("2000.01"), 2026, 1).duas_quotas[0].valor, D)
