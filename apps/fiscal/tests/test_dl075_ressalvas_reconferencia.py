"""DL-075 — ressalvas R1, R2, R3 e R5 da reconferência de 2026-10-08 (docs/auditorias/).

R1: a guarda do A6 também recusa encerrar a vigência no meio de mês confirmado e o cadastro
retroativo que cobre mês confirmado. Encerrar no último dia de mês aberto, ou para o futuro, e
cadastrar a partir do mês aberto continuam permitidos.
R2: isolamento da guarda entre empresas do mesmo escritório; a tabela da memória do pré-DAS na
tela com valores exatos; o formato de `memoria[].valor` na API.
R3: lacunas de teste (N27, N07, N08, N13, N28, N29, N23).
R5: valor só com dígitos ASCII, nas três portas (serviço, API e tela).

Dados 100% sintéticos (`test_dl075_suporte` e `test_dl074_suporte`). Os números esperados
estão escritos à mão.
"""

import calendar
import json
import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import folha_fator_r as servico_folha
from apps.fiscal import pre_das as servico
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    EnquadramentoAtividade,
    FolhaFatorR,
    MercadoReceita,
    ReceitaInformada,
)
from apps.fiscal.tests.test_dl074_suporte import ORIGEM_OUTRAS, fixar_inicio_de_uso
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    folha_confirmada,
    janela_de_receitas,
    receber_e_confirmar_mes,
)

pytestmark = pytest.mark.django_db

ANEXO_III = EnquadramentoAtividade.ANEXO_III
ANEXO_IV = EnquadramentoAtividade.ANEXO_IV
INTERNO = MercadoReceita.INTERNO


@pytest.fixture
def empresa(empresa_a):
    """Simples desde 2018, abertura em 2015, início de uso em 2025/01 (sem restrição)."""
    return cenario_simples(empresa_a)


def _base(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}"


def _cenario_exemplo_2(empresa, usuario):
    """Manual do PGDAS-D, exemplo 2: RBT12 300.000; receita de 06/2026 de 100.000 (sintética)."""
    atividade_padrao(empresa, usuario, ANEXO_III)
    janela_de_receitas(empresa, usuario, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario, 2026, 6, "100000.00")


# ---------------------------------------------------------------------------
# R1 — mudança parcial de vigência e cadastro retroativo sobre mês confirmado
# ---------------------------------------------------------------------------


def test_r1_encerrar_no_meio_de_mes_confirmado_e_recusado_nomeando_o_mes(empresa, usuario_gestor_a):
    # Padrão desde 2018 cobre 06/2026 por inteiro; encerrar em 15/06 deixa só metade do mês.
    atividade = atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.alterar_atividade(atividade, {"fim": date(2026, 6, 15)}, usuario_gestor_a)

    assert "06/2026" in excecao.value.mensagem
    atividade.refresh_from_db()
    assert atividade.fim is None


def test_r1_encerrar_no_ultimo_dia_do_mes_confirmado_continua_permitido(empresa, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    alterada = servico.alterar_atividade(atividade, {"fim": date(2026, 6, 30)}, usuario_gestor_a)

    assert alterada.fim == date(2026, 6, 30)


def test_r1_nova_vigencia_a_partir_do_mes_aberto_continua_permitida(empresa, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")
    servico.alterar_atividade(atividade, {"fim": date(2026, 6, 30)}, usuario_gestor_a)

    nova = atividade_padrao(empresa, usuario_gestor_a, ANEXO_IV, inicio=date(2026, 7, 1))

    assert nova.inicio == date(2026, 7, 1)
    assert nova.enquadramento == ANEXO_IV


@pytest.mark.parametrize("padrao", [True, False])
def test_r1_cadastro_retroativo_que_cobre_mes_confirmado_e_recusado(
    empresa, usuario_gestor_a, padrao
):
    # Sem atividade cadastrada: o cadastro retroativo de 2018 cobre 06/2026 confirmado.
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.cadastrar_atividade(
            empresa,
            {
                "descricao": "Serviço sintético retroativo",
                "codigo_subitem": "",
                "enquadramento": ANEXO_III,
                "inicio": date(2018, 1, 1),
                "fim": None,
                "padrao": padrao,
            },
            usuario_gestor_a,
        )

    assert "06/2026" in excecao.value.mensagem
    assert "a partir do mês aberto" in excecao.value.mensagem
    assert servico.AtividadeEmpresa.objects.filter(empresa=empresa).count() == 0


# ---------------------------------------------------------------------------
# R2a — isolamento da guarda do A6 entre empresas do mesmo escritório (mata X02)
# ---------------------------------------------------------------------------


def test_r2a_meses_confirmados_da_vizinha_nao_bloqueiam_a_auditada(
    empresa_a, empresa_a2, usuario_gestor_a
):
    vizinha = cenario_simples(empresa_a)
    atividade_padrao(vizinha, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(vizinha, usuario_gestor_a, 2026, 6, "100000.00")
    auditada = cenario_simples(empresa_a2)
    atividade = atividade_padrao(auditada, usuario_gestor_a, ANEXO_III)

    alterada = servico.alterar_atividade(atividade, {"enquadramento": ANEXO_IV}, usuario_gestor_a)

    assert alterada.enquadramento == ANEXO_IV


def test_r2a_recusa_da_auditada_cita_so_o_proprio_mes(empresa_a, empresa_a2, usuario_gestor_a):
    # A vizinha tem 01/2026 confirmado, ANTES do mês da auditada. Sem o filtro por empresa, a
    # mensagem citaria 01/2026 (o mês mais antigo da lista). Ela deve citar só 06/2026.
    vizinha = cenario_simples(empresa_a)
    atividade_padrao(vizinha, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(vizinha, usuario_gestor_a, 2026, 1, "100000.00")
    auditada = cenario_simples(empresa_a2)
    atividade = atividade_padrao(auditada, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(auditada, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.alterar_atividade(atividade, {"enquadramento": ANEXO_IV}, usuario_gestor_a)

    assert "06/2026" in excecao.value.mensagem
    assert "01/2026" not in excecao.value.mensagem


# ---------------------------------------------------------------------------
# R2b — tabela da memória de cálculo na tela, com valores exatos (mata N30)
# ---------------------------------------------------------------------------


def _url_pre_das():
    return reverse("fiscal_web:pre_das")


def _rotulo_que_comeca_com(pares, inicio):
    """Valor da única linha cujo rótulo começa por `inicio` (o rótulo traz o regime da regra)."""
    (valor,) = [valor for rotulo, valor in pares if rotulo.startswith(inicio)]
    return valor


def _linhas_da_memoria(html):
    """(descrição, valor) de cada linha da tabela da memória, como a tela as mostra."""
    inicio = html.index("<caption>Memória de cálculo")
    tabela = html[inicio : html.index("</table>", inicio)]
    return re.findall(r'<td>([^<]*)</td>\s*<td class="valor-monetario">([^<]*)</td>', tabela)


def test_r2b_tela_memoria_mostra_valores_exatos_em_pt_br(client, empresa, usuario_gestor_a):
    _cenario_exemplo_2(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = client.get(_url_pre_das(), {"empresa": empresa.pk, "ano": 2026, "mes": 6})

    assert resposta.status_code == 200
    linhas = _linhas_da_memoria(resposta.content.decode())
    valores = dict(linhas)
    assert len(linhas) >= 10
    assert _rotulo_que_comeca_com(linhas, "RBT12 do mercado interno") == "300.000,00"
    assert valores["Total do pré-DAS"] == "8.080,00"
    # Células numéricas (só dígitos, ponto e vírgula) saem bem formadas: dinheiro em pt-BR
    # ("1.135,24") ou percentual com ponto ("0.112000"). Nenhuma vira só a vírgula (mata N30).
    numericas = [
        (descricao, valor) for descricao, valor in linhas if re.fullmatch(r"[\d.,]+", valor)
    ]
    assert len(numericas) >= 10
    for descricao, valor in numericas:
        assert re.fullmatch(r"\d[\d.]*,\d+|\d+\.\d+", valor), (descricao, valor)


# ---------------------------------------------------------------------------
# R2c — formato de memoria[].valor na API (dinheiro pt-BR; percentual com ponto)
# ---------------------------------------------------------------------------


def test_r2c_api_memoria_valor_em_dinheiro_pt_br_e_percentual_em_ponto(
    client, empresa, usuario_gestor_a
):
    _cenario_exemplo_2(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = client.get(f"{_base(empresa)}/pre-das/?ano=2026&mes=6")

    assert resposta.status_code == 200
    pares = [(passo["descricao"], passo["valor"]) for passo in resposta.json()["memoria"]]
    # Dinheiro sai em pt-BR, como o documento que o contador confere.
    assert _rotulo_que_comeca_com(pares, "RBT12 do mercado interno") == "300.000,00"
    assert _rotulo_que_comeca_com(pares, "Total do pré-DAS") == "8.080,00"
    # Alíquota efetiva é fração com ponto decimal, com a precisão total (0,0808 = 8,08%).
    assert _rotulo_que_comeca_com(pares, "interno, Anexo III: alíquota efetiva") == (
        "0.080800000000"
    )


# ---------------------------------------------------------------------------
# R3 — lacunas de teste (N27, N07, N08)
# ---------------------------------------------------------------------------


def test_r3_n27_trocar_padrao_para_nao_padrao_com_mesmo_enquadramento_e_recusado(
    empresa, usuario_gestor_a
):
    atividade = atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.alterar_atividade(atividade, {"padrao": False}, usuario_gestor_a)

    assert "A troca de atividade padrão" in excecao.value.mensagem
    assert "06/2026" in excecao.value.mensagem
    atividade.refresh_from_db()
    assert atividade.padrao is True


def test_r3_n07_mes_a_retificar_ou_reaberto_ou_nao_confirmado_nao_bloqueia(
    empresa, usuario_gestor_a
):
    atividade = atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 5, "100000.00")
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")
    # 05/2026 volta a "a retificar" (estorno); 06/2026 é reaberto. Nenhum dos dois está confirmado.
    servico_receita.marcar_a_retificar_por_estorno(
        empresa, 2026, 5, usuario_gestor_a, origem="estorno sintético de teste"
    )
    servico_receita.reabrir_mes(
        empresa, 2026, 6, "Reabertura sintética de teste.", usuario_gestor_a
    )
    # 04/2026 tem só receita lançada em rascunho, sem confirmação.
    servico_receita.lancar_receita_informada(
        empresa,
        2026,
        4,
        INTERNO,
        "1000.00",
        ORIGEM_OUTRAS,
        "Motivo sintético.",
        SUPORTE_SINTETICO,
        usuario_gestor_a,
        situacao_iss="proprio_municipio",
    )

    alterada = servico.alterar_atividade(atividade, {"enquadramento": ANEXO_IV}, usuario_gestor_a)

    assert alterada.enquadramento == ANEXO_IV


def test_r3_n08_fim_no_primeiro_dia_do_mes_confirmado_conta_como_cobertura(
    empresa, usuario_gestor_a
):
    # Vigência termina em 31/05: não cobre 06/2026. Estender até 01/06 cobre um dia de 06/2026.
    atividade = atividade_padrao(empresa, usuario_gestor_a, ANEXO_III, fim=date(2026, 5, 31))
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.alterar_atividade(atividade, {"fim": date(2026, 6, 1)}, usuario_gestor_a)

    assert "06/2026" in excecao.value.mensagem
    atividade.refresh_from_db()
    assert atividade.fim == date(2026, 5, 31)


# ---------------------------------------------------------------------------
# R3 — FS12 em lote: estorno seguido de nova folha, e limites de período (N13, N28, N29)
# ---------------------------------------------------------------------------


def test_r3_n13_fs12_do_ano_igual_a_fs12_com_estorno_e_nova_folha(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    fixar_inicio_de_uso(empresa, 2024, 1)
    for mes in range(1, 13):
        folha_confirmada(empresa, usuario_gestor_a, 2024, mes, remuneracao="1000")
    for mes in range(1, 13):
        folha_confirmada(empresa, usuario_gestor_a, 2025, mes, remuneracao=str(1000 + mes))
    # 03/2025: estornada e recriada com 777 (estorno seguido de nova folha).
    estornada = FolhaFatorR.objects.get(empresa=empresa, ano=2025, mes=3)
    servico_folha.estornar_folha(estornada, "Estorno sintético de teste.", usuario_gestor_a)
    folha_confirmada(empresa, usuario_gestor_a, 2025, 3, remuneracao="777")
    # 09/2025: só estornada, sem nova folha (o mês fica sem lançamento).
    servico_folha.estornar_folha(
        FolhaFatorR.objects.get(empresa=empresa, ano=2025, mes=9),
        "Estorno sintético de teste.",
        usuario_gestor_a,
    )

    em_lote = servico_folha.fs12_do_ano(empresa, 2025)

    for mes in range(1, 13):
        assert em_lote[mes] == servico_folha.fs12(empresa, 2025, mes), f"mês {mes}"
    # PA 10/2025 (janela 10/2024 a 09/2025): 09/2025 aparece como sem lançamento, não como
    # estornada. A estorno não pode entrar no lote.
    assert em_lote[10].pendentes == ((2025, 9, "sem_lancamento"),)
    assert em_lote[10].valor is None
    # PA 04/2025 (janela 04/2024 a 03/2025): a folha recriada de 777 entra; nada pendente.
    # 04/2024 a 12/2024 = 9 x 1000; 01/2025 a 03/2025 = 1001 + 1002 + 777 = 2780. Total 11780.
    assert em_lote[4].pendentes == ()
    assert em_lote[4].valor == Decimal("11780.00")


@pytest.mark.parametrize(
    ("historico", "mes_de_fronteira", "inicio_esperado"),
    [
        # Período fechado termina no dia 1º de março; o aberto começa só em abril (N29).
        ([(date(2018, 1, 1), date(2026, 3, 1)), (date(2026, 4, 1), None)], 3, date(2018, 1, 1)),
        # Período aberto começa no último dia de março; o fechado termina em fevereiro (N28).
        ([(date(2018, 1, 1), date(2026, 2, 28)), (date(2026, 3, 31), None)], 3, date(2026, 3, 31)),
    ],
)
def test_r3_n28_n29_escolha_de_periodo_em_lote_igual_a_mes_a_mes(
    empresa_a2, historico, mes_de_fronteira, inicio_esperado
):
    Empresa.objects.filter(pk=empresa_a2.pk).update(data_abertura_cnpj=date(2015, 3, 10))
    for inicio, fim in historico:
        HistoricoRegimeTributario.objects.create(
            empresa=empresa_a2,
            regime=RegimeTributario.SIMPLES_NACIONAL,
            vigencia_inicio=inicio,
            vigencia_fim=fim,
        )
    periodos = apuracao.periodos_do_simples(empresa_a2)

    for mes in range(1, 13):
        primeiro = date(2026, mes, 1)
        ultimo = date(2026, mes, calendar.monthrange(2026, mes)[1])
        em_lote = apuracao._escolher_periodo(periodos, primeiro, ultimo)
        assert em_lote == apuracao._periodo_do_simples(empresa_a2, 2026, mes), f"mês {mes}"

    escolhido = apuracao._escolher_periodo(
        periodos, date(2026, mes_de_fronteira, 1), date(2026, mes_de_fronteira, 31)
    )
    assert escolhido.vigencia_inicio == inicio_esperado


# ---------------------------------------------------------------------------
# R3 — RBT12 proporcional exibido com duas casas (N23)
# ---------------------------------------------------------------------------


def test_r3_n23_rbt12_proporcional_aparece_arredondado_na_memoria(empresa_a, usuario_gestor_a):
    # Início em 02/2026: 7 meses de atividade na janela do PA 09/2026. Receita de 70,01 no total.
    # RBT12 = 70,01 x 12 / 7 = 120,0171428571... Exibição: "120,02" (cálculo segue exato).
    empresa = cenario_simples(empresa_a, abertura=date(2026, 2, 1), inicio_simples=date(2026, 2, 1))
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III, inicio=date(2026, 2, 1))
    valores = ["10.00"] * 6 + ["10.01"]
    for mes, valor in zip(range(2, 9), valores, strict=True):
        receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, mes, valor)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 9, "5000.00")

    rbt = apuracao.rbt12(empresa, 2026, 9).de(INTERNO).apurado
    memoria = servico.pre_das(empresa, 2026, 9).memoria
    pares = [(passo.descricao, passo.valor) for passo in memoria]

    # O cálculo guarda a precisão total (dezenas de dígitos); só a exibição arredonda.
    assert abs(rbt - Decimal("70.01") * 12 / Decimal(7)) < Decimal("1E-18")
    assert _rotulo_que_comeca_com(pares, "RBT12 do mercado interno") == "120,02"


# ---------------------------------------------------------------------------
# R5 — valor só com dígitos ASCII, antes do Decimal, nas três portas
# ---------------------------------------------------------------------------

# "1_000": o Decimal aceita o underscore. "٣" e "١٠.00": o Decimal aceita dígitos Unicode.
VALORES_FORA_DO_FORMATO = ["1_000", "1_000.00", "٣", "٣.50", "١٠.00", "1 000.00"]


def _componentes_da_folha(remuneracao):
    return {
        "remuneracao_empregados_avulsos": remuneracao,
        "pro_labore_autonomos": "0",
        "decimo_terceiro": "0",
        "cpp_recolhida": "0",
        "fgts_recolhido": "0",
    }


@pytest.mark.parametrize("valor", VALORES_FORA_DO_FORMATO)
def test_r5_servico_de_receita_recusa_valor_fora_do_formato_ascii(empresa, usuario_gestor_a, valor):
    with pytest.raises(servico_receita.EntradaInvalidaReceita, match="Valor inválido"):
        servico_receita.lancar_receita_informada(
            empresa,
            2026,
            5,
            INTERNO,
            valor,
            ORIGEM_OUTRAS,
            "Motivo sintético.",
            SUPORTE_SINTETICO,
            usuario_gestor_a,
            situacao_iss="proprio_municipio",
        )

    assert ReceitaInformada.objects.count() == 0


@pytest.mark.parametrize("valor", VALORES_FORA_DO_FORMATO)
def test_r5_servico_de_folha_recusa_valor_fora_do_formato_ascii(empresa, usuario_gestor_a, valor):
    with pytest.raises(servico_folha.EntradaInvalidaFolha, match="valor inválido"):
        servico_folha.lancar_folha(
            empresa,
            2026,
            5,
            _componentes_da_folha(valor),
            SUPORTE_SINTETICO,
            usuario_gestor_a,
        )

    assert FolhaFatorR.objects.count() == 0


@pytest.mark.parametrize("valor", VALORES_FORA_DO_FORMATO)
def test_r5_api_recusa_valor_fora_do_formato_ascii_na_receita_e_na_folha(
    client, empresa, usuario_gestor_a, valor
):
    client.force_login(usuario_gestor_a)
    receita = {
        "ano": 2026,
        "mes": 6,
        "mercado": "interno",
        "valor": valor,
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "Extrato sintético de teste.",
        "situacao_iss": "proprio_municipio",
    }
    folha = {
        "ano": 2026,
        "mes": 5,
        "remuneracao_empregados_avulsos": valor,
        "pro_labore_autonomos": "0.00",
        "decimo_terceiro": "0.00",
        "cpp_recolhida": "0.00",
        "fgts_recolhido": "0.00",
        "documento_suporte": SUPORTE_SINTETICO,
    }

    resposta_receita = client.post(
        f"{_base(empresa)}/receitas-informadas/",
        data=json.dumps(receita),
        content_type="application/json",
    )
    resposta_folha = client.post(
        f"{_base(empresa)}/folhas-fator-r/nova/",
        data=json.dumps(folha),
        content_type="application/json",
    )

    assert resposta_receita.status_code == 400
    assert "Valor inválido" in str(resposta_receita.json())
    assert resposta_folha.status_code == 400
    assert ReceitaInformada.objects.count() == 0
    assert FolhaFatorR.objects.count() == 0


@pytest.mark.parametrize("valor", VALORES_FORA_DO_FORMATO)
def test_r5_tela_recusa_valor_fora_do_formato_ascii_sem_gravar(
    client, empresa, usuario_gestor_a, valor
):
    client.force_login(usuario_gestor_a)
    receita = {
        "ano": "2026",
        "mes": "05",
        "mercado": "interno",
        "situacao_iss": "proprio_municipio",
        "valor": valor,
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "Extrato sintético de teste.",
        "acao": "rascunho",
    }
    folha = {
        "ano": "2026",
        "mes": "05",
        "remuneracao_empregados_avulsos": valor,
        "pro_labore_autonomos": "0,00",
        "decimo_terceiro": "0,00",
        "cpp_recolhida": "0,00",
        "fgts_recolhido": "0,00",
        "documento_suporte": SUPORTE_SINTETICO,
    }

    resposta_receita = client.post(
        reverse("fiscal_web:receita_informada_nova", args=[empresa.pk]), receita
    )
    resposta_folha = client.post(reverse("fiscal_web:folha_nova", args=[empresa.pk]), folha)

    assert resposta_receita.status_code == 200
    assert "inválido" in resposta_receita.content.decode().lower()
    assert resposta_folha.status_code == 200
    assert "inválido" in resposta_folha.content.decode().lower()
    assert ReceitaInformada.objects.count() == 0
    assert FolhaFatorR.objects.count() == 0
