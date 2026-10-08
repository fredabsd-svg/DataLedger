"""DL-075 — correção única da auditoria (docs/auditorias/2026-10-08-dl-075-rodada-1.md).

Cobre o SERVIÇO de cada achado: isolamento do cálculo com valores (A2), fator r com exportação
(A3), atividade por nota (A5), mudança de atividade com mês confirmado (A6), limites não
cadastrados (A7), receita interna sem situação (A8), FS12 em lote (A9), textos da recusa e da
memória (A10) e valores e datas de entrada (A11). As portas de tela e de API estão em
`test_dl075_correcao_telas_api.py`.

Dados 100% sintéticos (CNPJs fictícios de `xml_sinteticos`). Os números esperados estão escritos
à mão. Os exemplos do Manual do PGDAS-D são casos de referência (exemplo 2: 8.080,00).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import folha_fator_r as servico_folha
from apps.fiscal import pre_das as servico
from apps.fiscal import receita as servico_receita
from apps.fiscal import services as servicos_recepcao
from apps.fiscal.escrituracao import efetivar_escrituracao
from apps.fiscal.models import (
    DocumentoFiscal,
    EnquadramentoAtividade,
    EstadoReceitaInformada,
    FolhaFatorR,
    MercadoReceita,
    NaturezaOperacao,
    PapelDocumento,
    ReceitaInformada,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.test_dl074_suporte import ORIGEM_OUTRAS, escriturar, informar_e_confirmar
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    folha_confirmada,
    folhas_dos_12_meses,
    janela_de_receitas,
    receber_e_confirmar_mes,
    sequencia_anterior,
)
from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_COM_ZERO_A_ESQUERDA,
    identificador_nfse,
    xml_nfse,
)

pytestmark = pytest.mark.django_db

INTERNO = MercadoReceita.INTERNO
EXTERNO = MercadoReceita.EXTERNO
ANEXO_III = EnquadramentoAtividade.ANEXO_III
ANEXO_IV = EnquadramentoAtividade.ANEXO_IV
ANEXO_III_OU_V = EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R


def _escriturar_como_prestador(escritorio, prestadora, usuario, *, sufixo, competencia, valor):
    """NFS-e sintética em que `prestadora` é a PRESTADORA, efetivada com natureza interna.

    O helper `escriturar` da DL-074 fixa o prestador no CNPJ da empresa A. Para a vizinha
    (outra empresa do mesmo escritório) o prestador tem de ser o dela. O tomador é um CNPJ
    sem empresa cadastrada.
    """
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
            v_serv=f"{Decimal(valor):.2f}",
            v_liq=f"{Decimal(valor):.2f}",
            prestador_documento=prestadora.cnpj,
            tomador_documento=CNPJ_COM_ZERO_A_ESQUERDA,
        ),
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)
    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=prestadora, papel=PapelDocumento.PRESTADOR
    )
    return efetivar_escrituracao(vinculo, NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR, usuario)


def _cenario_com_vizinha(empresa_a, empresa_a2, usuario):
    """Auditada (Anexo III, 25.000 por mês, PA 100.000) e vizinha do MESMO escritório.

    A vizinha tem tudo que, se vazasse para a auditada, mudaria o cálculo: receita informada
    maior (mensal 90.000, PA 77.777), atividade Anexo IV, folha confirmada e nota escriturada.
    """
    auditada = cenario_simples(empresa_a)
    vizinha = cenario_simples(empresa_a2)
    atividade_padrao(auditada, usuario, ANEXO_III)
    atividade_padrao(vizinha, usuario, ANEXO_IV)
    janela_de_receitas(vizinha, usuario, 2026, 6, [90000] * 12)
    receber_e_confirmar_mes(vizinha, usuario, 2026, 6, "77777.00")
    folha_confirmada(vizinha, usuario, 2026, 6, remuneracao="50000.00")
    _escriturar_como_prestador(
        empresa_a2.escritorio,
        vizinha,
        usuario,
        sufixo=9301,
        competencia=(2026, 6),
        valor="40000.00",
    )
    janela_de_receitas(auditada, usuario, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(auditada, usuario, 2026, 6, "100000.00")
    return auditada, vizinha


# ---------------------------------------------------------------------------
# A2 — isolamento do cálculo entre empresas com valores (mata M10 a M13)
# ---------------------------------------------------------------------------


def test_pre_das_da_auditada_nao_enxerga_receita_folha_nem_atividade_da_vizinha(
    empresa_a, empresa_a2, usuario_gestor_a
):
    auditada, _vizinha = _cenario_com_vizinha(empresa_a, empresa_a2, usuario_gestor_a)

    resultado = servico.pre_das(auditada, 2026, 6)

    # Exemplo 2 do Manual do PGDAS-D: RBT12 300.000 (12 × 25.000), 2ª faixa do Anexo III,
    # alíquota efetiva 0,0808, sobre 100.000 do PA. Esperado à mão: 8.080,00.
    assert resultado.rbt12[INTERNO] == Decimal("300000")
    assert [anexo.anexo for anexo in resultado.anexos] == ["III"]
    assert resultado.total == Decimal("8080.00")


def test_fator_r_da_auditada_usa_so_a_propria_folha(empresa_a, empresa_a2, usuario_gestor_a):
    """FS12 = 120.000 da auditada; RBT12 conjunto 540.000; r = 0,22 → Anexo V.

    A vizinha tem folha de 500.000 por mês nos mesmos meses. Se a folha dela entrasse, o FS12
    seria outro e o anexo também.
    """
    auditada = cenario_simples(empresa_a)
    vizinha = cenario_simples(empresa_a2)
    atividade_padrao(auditada, usuario_gestor_a, ANEXO_III_OU_V)
    atividade_padrao(vizinha, usuario_gestor_a, ANEXO_III_OU_V)
    janela_de_receitas(auditada, usuario_gestor_a, 2026, 6, [45000] * 12)
    receber_e_confirmar_mes(auditada, usuario_gestor_a, 2026, 6, "45000.00")
    folhas_dos_12_meses(auditada, usuario_gestor_a, 2026, 6, [Decimal("10000")] * 12)
    folhas_dos_12_meses(vizinha, usuario_gestor_a, 2026, 6, [Decimal("500000")] * 12)

    resultado = servico.pre_das(auditada, 2026, 6)

    assert resultado.fator_r.fs12 == Decimal("120000")
    assert resultado.fator_r.rbt12_conjunto == Decimal("540000")
    assert resultado.fator_r.valor == Decimal("0.22")
    assert [anexo.anexo for anexo in resultado.anexos] == ["V"]


def test_folha_da_vizinha_no_mesmo_mes_nao_conflita_com_a_da_auditada(
    empresa_a, empresa_a2, usuario_gestor_a
):
    """Mata M12 (filtro de empresa tirado de `folha_ativa`): sem o filtro, a folha da vizinha
    no mesmo mês recusaria o lançamento da auditada como "já existe folha deste mês"."""
    auditada = cenario_simples(empresa_a)
    vizinha = cenario_simples(empresa_a2)
    folha_confirmada(vizinha, usuario_gestor_a, 2026, 6, remuneracao="5000")

    folha = folha_confirmada(auditada, usuario_gestor_a, 2026, 6, remuneracao="1000")

    assert folha.empresa_id == auditada.pk
    assert FolhaFatorR.objects.filter(ano=2026, mes=6).count() == 2


# ---------------------------------------------------------------------------
# A3 — fator r com exportação no RBT12 conjunto (mata M38)
# ---------------------------------------------------------------------------


def test_fator_r_soma_o_mercado_externo_no_rbt12_conjunto(empresa_a, usuario_gestor_a):
    """12 meses de 25.000 interno e 25.000 externo: RBT12 conjunto 600.000. FS12 150.000 →
    r = 0,25 → Anexo V. Sem a exportação, o r daria 0,50 e o anexo seria III (mutante M38)."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III_OU_V)
    for ano, mes in [*sequencia_anterior(2026, 6), (2026, 6)]:
        informar_e_confirmar(empresa, usuario_gestor_a, ano, mes, "25000.00", mercado=INTERNO)
        informar_e_confirmar(empresa, usuario_gestor_a, ano, mes, "25000.00", mercado=EXTERNO)
        servico_receita.confirmar_mes(empresa, ano, mes, usuario_gestor_a)
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [Decimal("12500")] * 12)

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.fator_r.fs12 == Decimal("150000")
    assert resultado.fator_r.rbt12_conjunto == Decimal("600000")
    assert resultado.fator_r.valor == Decimal("0.25")
    assert {anexo.anexo for anexo in resultado.anexos} == {"V"}


# ---------------------------------------------------------------------------
# A5 — atividade por nota: mais de uma atividade vigente e nota no mês (decisão do arquiteto)
# ---------------------------------------------------------------------------


def test_duas_atividades_vigentes_e_uma_nota_no_mes_bloqueia_nomeando_a_lista(
    empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    servico.cadastrar_atividade(
        empresa,
        {
            "descricao": "Consultoria sintética",
            "codigo_subitem": "",
            "enquadramento": ANEXO_IV,
            "inicio": date(2018, 1, 1),
            "fim": None,
            "padrao": False,
        },
        usuario_gestor_a,
    )
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9401,
        competencia=(2026, 6),
        valor="100000.00",
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2026, 6)

    bloqueio = next(
        b for b in excecao.value.bloqueios if b.codigo == "notas_sem_atividade_definida"
    )
    assert "mais de uma atividade vigente em 06/2026" in bloqueio.mensagem
    assert "Consultoria sintética (Anexo IV)" in bloqueio.mensagem
    assert "BL-670" in bloqueio.mensagem
    assert "o pré-DAS não escolhe o anexo por você" in bloqueio.mensagem


def test_uma_atividade_so_com_nota_no_mes_calcula(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9402,
        competencia=(2026, 6),
        valor="100000.00",
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("8080.00")


def test_duas_atividades_vigentes_sem_nota_e_receita_com_atividade_explicita_calcula(
    empresa_a, usuario_gestor_a
):
    """Sem nota no mês, a regra de A5 não se aplica. A receita informada que aponta a
    atividade explícita continua usando o enquadramento dela."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    atividade_iv = servico.cadastrar_atividade(
        empresa,
        {
            "descricao": "Consultoria sintética",
            "codigo_subitem": "",
            "enquadramento": ANEXO_IV,
            "inicio": date(2018, 1, 1),
            "fim": None,
            "padrao": False,
        },
        usuario_gestor_a,
    )
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receita = servico_receita.lancar_receita_informada(
        empresa,
        2026,
        6,
        INTERNO,
        "100000.00",
        ORIGEM_OUTRAS,
        "Motivo sintético.",
        "Suporte sintético.",
        usuario_gestor_a,
        atividade=atividade_iv,
        situacao_iss="proprio_municipio",
    )
    servico_receita.confirmar_receita_informada(receita, usuario_gestor_a)
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    resultado = servico.pre_das(empresa, 2026, 6)

    assert [anexo.anexo for anexo in resultado.anexos] == ["IV"]


# ---------------------------------------------------------------------------
# A6 — mudança ou exclusão de atividade que cobre mês confirmado
# ---------------------------------------------------------------------------


def _empresa_com_meses_confirmados(empresa_a, usuario):
    """Padrão Anexo III desde 2018 e receita confirmada de 06/2025 a 06/2026."""
    empresa = cenario_simples(empresa_a)
    atividade = atividade_padrao(empresa, usuario, ANEXO_III)
    janela_de_receitas(empresa, usuario, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario, 2026, 6, "100000.00")
    return empresa, atividade


def test_mudar_enquadramento_de_atividade_que_cobre_mes_confirmado_e_recusado(
    empresa_a, usuario_gestor_a
):
    empresa, atividade = _empresa_com_meses_confirmados(empresa_a, usuario_gestor_a)

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.alterar_atividade(atividade, {"enquadramento": ANEXO_IV}, usuario_gestor_a)

    mensagem = excecao.value.mensagem
    assert "A mudança de enquadramento" in mensagem
    assert "06/2025" in mensagem  # primeiro mês confirmado coberto
    assert "encerre a vigência" in mensagem
    assert "a partir do mês aberto" in mensagem
    atividade.refresh_from_db()
    assert atividade.enquadramento == ANEXO_III


def test_encerrar_vigencia_antes_de_mes_confirmado_e_recusado(empresa_a, usuario_gestor_a):
    empresa, atividade = _empresa_com_meses_confirmados(empresa_a, usuario_gestor_a)

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.alterar_atividade(atividade, {"fim": date(2026, 3, 10)}, usuario_gestor_a)

    # Encerrar em 10/03/2026 tira a atividade de abril em diante: abril é o primeiro mês
    # confirmado que mudaria (março ainda é coberto, por inteiro ou em parte).
    assert "04/2026" in excecao.value.mensagem
    atividade.refresh_from_db()
    assert atividade.fim is None


def test_encerrar_vigencia_para_o_futuro_continua_permitido(empresa_a, usuario_gestor_a):
    empresa, atividade = _empresa_com_meses_confirmados(empresa_a, usuario_gestor_a)

    alterada = servico.alterar_atividade(atividade, {"fim": date(2026, 12, 31)}, usuario_gestor_a)

    assert alterada.fim == date(2026, 12, 31)


def test_mudar_atividade_que_nao_cobre_mes_confirmado_continua_permitido(
    empresa_a, usuario_gestor_a
):
    empresa, _padrao = _empresa_com_meses_confirmados(empresa_a, usuario_gestor_a)
    futura = servico.cadastrar_atividade(
        empresa,
        {
            "descricao": "Consultoria futura",
            "codigo_subitem": "",
            "enquadramento": ANEXO_III,
            "inicio": date(2026, 7, 1),
            "fim": None,
            "padrao": False,
        },
        usuario_gestor_a,
    )

    alterada = servico.alterar_atividade(futura, {"enquadramento": ANEXO_IV}, usuario_gestor_a)

    assert alterada.enquadramento == ANEXO_IV


def test_excluir_atividade_que_cobre_mes_confirmado_e_recusado(empresa_a, usuario_gestor_a):
    empresa, atividade = _empresa_com_meses_confirmados(empresa_a, usuario_gestor_a)

    with pytest.raises(servico.AtividadeConflito) as excecao:
        servico.excluir_atividade(atividade, usuario_gestor_a)

    assert "A exclusão" in excecao.value.mensagem
    assert "encerre a vigência" in excecao.value.mensagem
    assert servico.AtividadeEmpresa.objects.filter(pk=atividade.pk).exists()


# ---------------------------------------------------------------------------
# A7 — limites e sublimite não cadastrados: recusa nomeada (HI-70)
# ---------------------------------------------------------------------------


def test_pa_2025_com_limites_nao_cadastrados_recusa_nomeando_o_ano(empresa_a, usuario_gestor_a):
    """Sublimite só tem vigência a partir de 2026: no PA 07/2025 o pré-DAS não confere o
    excesso e não calcula, em vez de calcular o ISS com receita acima do sublimite."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2025, 7, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2025, 7, "25000.00")

    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2025, 7)

    bloqueio = next(b for b in excecao.value.bloqueios if b.codigo == "limites_nao_cadastrados")
    assert bloqueio.mensagem == (
        "Os limites e o sublimite de 2025 não estão cadastrados: o pré-DAS não confere o "
        "sublimite e não calcula (HI-70)."
    )


# ---------------------------------------------------------------------------
# A8 — confirmação de receita interna sem situação do ISS (serviço)
# ---------------------------------------------------------------------------


def test_confirmar_receita_interna_sem_situacao_iss_e_recusado_e_fica_rascunho(
    empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    receita = servico_receita.lancar_receita_informada(
        empresa,
        2026,
        6,
        INTERNO,
        "1000.00",
        ORIGEM_OUTRAS,
        "Motivo sintético.",
        "Suporte sintético.",
        usuario_gestor_a,
        situacao_iss="proprio_municipio",
    )
    # Rascunho legado, sem situação (o banco permite no interno: a regra é do serviço).
    ReceitaInformada.objects.filter(pk=receita.pk).update(situacao_iss=None)
    receita.refresh_from_db()

    with pytest.raises(servico_receita.EntradaInvalidaReceita, match="situação do ISS"):
        servico_receita.confirmar_receita_informada(receita, usuario_gestor_a)

    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.RASCUNHO


# ---------------------------------------------------------------------------
# A9 — FS12 dos 12 meses em duas consultas, igual ao mês a mês
# ---------------------------------------------------------------------------


def test_fs12_do_ano_igual_ao_de_cada_mes_com_duas_consultas(
    empresa_a, usuario_gestor_a, django_assert_num_queries
):
    empresa = cenario_simples(empresa_a)
    # 2025 com um mês sem folha; 2026 com um rascunho (não entra no FS12).
    for mes in range(1, 13):
        if mes == 9:
            continue
        folha_confirmada(empresa, usuario_gestor_a, 2025, mes, remuneracao=str(1000 + mes))
    servico_folha.lancar_folha(
        empresa,
        2026,
        3,
        {
            "remuneracao_empregados_avulsos": Decimal("777"),
            "pro_labore_autonomos": Decimal("0"),
            "decimo_terceiro": Decimal("0"),
            "cpp_recolhida": Decimal("0"),
            "fgts_recolhido": Decimal("0"),
        },
        SUPORTE_SINTETICO,
        usuario_gestor_a,
    )

    with django_assert_num_queries(2):
        em_lote = servico_folha.fs12_do_ano(empresa, 2026)

    for mes in range(1, 13):
        esperado = servico_folha.fs12(empresa, 2026, mes)
        assert em_lote[mes] == esperado, f"mês {mes}"


# ---------------------------------------------------------------------------
# A10 — textos da recusa e da memória
# ---------------------------------------------------------------------------


def test_limite_nao_apurado_nao_leva_o_sufixo_de_primeiro_corte(empresa_a, usuario_gestor_a):
    """Mês 03/2026 da janela recebido mas não confirmado: a recusa diz o motivo e não diz
    "Fora do primeiro corte"."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    for ano, mes in sequencia_anterior(2026, 6):
        if (ano, mes) == (2026, 3):
            informar_e_confirmar(empresa, usuario_gestor_a, ano, mes, "25000.00")
        else:
            receber_e_confirmar_mes(empresa, usuario_gestor_a, ano, mes, "25000.00")
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2026, 6)

    textos = [b.mensagem for b in excecao.value.bloqueios if b.codigo.startswith("excesso")]
    assert textos, "o aviso de limite não apurado precisa aparecer na recusa"
    assert all("Fora do primeiro corte" not in texto for texto in textos)
    assert "rbt12_nao_apuravel" in {b.codigo for b in excecao.value.bloqueios}


def test_troca_de_atividade_padrao_no_meio_do_mes_tem_mensagem_propria(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III, fim=date(2026, 6, 15))
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_IV, inicio=date(2026, 6, 16))
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2026, 6)

    (bloqueio,) = [
        b for b in excecao.value.bloqueios if b.codigo == "atividades_padrao_sobrepostas"
    ]
    assert bloqueio.mensagem == (
        "Mudança de atividade padrão no meio de 06/2026: o pré-DAS não divide o mês — "
        "ajuste a vigência para o 1º dia."
    )
    assert "Mantenha só uma" not in bloqueio.mensagem


def test_mes_nao_confirmado_mostra_situacao_em_texto_e_nao_o_codigo(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2026, 6)

    (bloqueio,) = [b for b in excecao.value.bloqueios if b.codigo == "mes_nao_confirmado"]
    assert "(situação: não confirmado)" in bloqueio.mensagem
    assert "nao_confirmado" not in bloqueio.mensagem


def test_memoria_mostra_dinheiro_com_duas_casas_e_percentual_com_a_precisao_de_antes(
    empresa_a, empresa_a2, usuario_gestor_a
):
    auditada, _vizinha = _cenario_com_vizinha(empresa_a, empresa_a2, usuario_gestor_a)

    resultado = servico.pre_das(auditada, 2026, 6)

    por_descricao = {passo.descricao: passo for passo in resultado.memoria}
    rbt = por_descricao["RBT12 do mercado interno (regra § 1º)"]
    assert rbt.valor == "300.000,00"
    total = por_descricao["Total do pré-DAS"]
    assert total.valor == "8.080,00"
    efetiva = por_descricao["interno, Anexo III: alíquota efetiva"]
    assert efetiva.valor == "0.080800000000"  # percentual: a precisão que o cálculo usa


# ---------------------------------------------------------------------------
# A11 — valores e datas de entrada no serviço
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["1E+3", "1e3", "NaN", "Infinity", "-Infinity"])
def test_servico_de_receita_recusa_notacao_cientifica_e_nao_finitos(
    empresa_a, usuario_gestor_a, valor
):
    empresa = cenario_simples(empresa_a)

    with pytest.raises(servico_receita.EntradaInvalidaReceita):
        servico_receita.lancar_receita_informada(
            empresa,
            2026,
            6,
            INTERNO,
            valor,
            ORIGEM_OUTRAS,
            "Motivo sintético.",
            "Suporte sintético.",
            usuario_gestor_a,
            situacao_iss="proprio_municipio",
        )

    assert ReceitaInformada.objects.count() == 0


@pytest.mark.parametrize("valor", ["1E+3", "NaN", "Infinity"])
def test_servico_de_folha_recusa_notacao_cientifica_e_nao_finitos(
    empresa_a, usuario_gestor_a, valor
):
    empresa = cenario_simples(empresa_a)
    componentes = {
        "remuneracao_empregados_avulsos": valor,
        "pro_labore_autonomos": "0",
        "decimo_terceiro": "0",
        "cpp_recolhida": "0",
        "fgts_recolhido": "0",
    }

    with pytest.raises(servico_folha.EntradaInvalidaFolha):
        servico_folha.lancar_folha(
            empresa, 2026, 6, componentes, SUPORTE_SINTETICO, usuario_gestor_a
        )

    assert FolhaFatorR.objects.count() == 0


def test_servico_de_folha_recusa_milhar_com_zero_a_direita_em_vez_de_virar_dez(
    empresa_a, usuario_gestor_a
):
    """Antes, `normalize()` deixava "10.000" passar como 10,00 (mesmo erro da receita, DL-074)."""
    empresa = cenario_simples(empresa_a)
    componentes = {
        "remuneracao_empregados_avulsos": "10.000",
        "pro_labore_autonomos": "0",
        "decimo_terceiro": "0",
        "cpp_recolhida": "0",
        "fgts_recolhido": "0",
    }

    with pytest.raises(servico_folha.EntradaInvalidaFolha, match="duas casas decimais"):
        servico_folha.lancar_folha(
            empresa, 2026, 6, componentes, SUPORTE_SINTETICO, usuario_gestor_a
        )


def test_inicio_de_atividade_anterior_a_2018_e_recusado_com_nome(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)

    with pytest.raises(servico.EntradaInvalidaAtividade, match="01/01/2018"):
        servico.cadastrar_atividade(
            empresa,
            {
                "descricao": "Serviço sintético de teste",
                "codigo_subitem": "",
                "enquadramento": ANEXO_III,
                "inicio": date(1, 1, 1),
                "fim": None,
                "padrao": True,
            },
            usuario_gestor_a,
        )

    assert servico.AtividadeEmpresa.objects.filter(empresa=empresa).count() == 0
