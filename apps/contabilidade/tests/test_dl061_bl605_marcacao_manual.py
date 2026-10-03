"""DL-061, fatia 2 (BL-605) — a marcação manual por lançamento e a API da
DMPL (decisões E15–E18 do plano, docs/planos/DL-061-dmpl.md).

A marcação é a EXCEÇÃO prevista pela RC-151: quando a regra automática de
linha não decide (lançamento ambíguo, par sem regra, contrapartida sem
linha), o contador reparte o efeito do lançamento à mão entre as células
(linha × coluna) e a emissão deixa de ser vetada. O contrato (E16) é o que
mantém os números corretos: Σ `valor` por coluna = o `movimento` daquele
lançamento — a marcação muda AONDE o valor aparece, nunca QUANTO existe.

Cobre os cenários obrigatórios do plano:

- M3 (dividendo pago com reserva, estornado): o par marcado libera a
  emissão e a linha mostra o líquido do par;
- eventos opostos em tesouraria marcados em DUAS linhas, com os brutos;
- recusas (Σ errado, linha/coluna fora do enum, valor zero, lançamento de
  outra empresa, lançamento decidido pela regra, CLIENTE 403, empresa alheia
  404);
- desmarcar devolve o veto exatamente como antes;
- trilha (ator + antes/depois) em cada salvar/limpar;
- imutabilidade do lançamento marcado;
- identidade DLPA × DMPL com marcação na coluna de lucros acumulados;
- API: GET da DMPL igual à apuração, PUT substitui o conjunto de uma vez.

Dados 100% sintéticos, herdados dos helpers de `test_dl061_dmpl.py` — os
MESMOS números, para a marcação ser conferível contra a apuração já testada.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import LancamentoContabil, MarcacaoDmpl
from apps.contabilidade.services import (
    MarcacaoDmplInvalida,
    avaliar_emissao_da_dmpl,
    classificar_conta_na_dmpl,
    estornar_lancamento,
    remover_marcacoes_da_dmpl,
    salvar_marcacoes_da_dmpl,
)
from apps.contabilidade.tests.test_dl048_dlpa import _autenticar
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    COL,
    LUCROS,
    MES,
    _apurar,
    _caso_a,
    _celula,
    _chaves_das_linhas,
    _conferir_identidade_com_a_dlpa,
    _contas_do_caso_b,
    _dec,
    _empresa,
    _lancar,
    _lancar_itens,
    _pendencias_nao_vazias,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

CAPITAL = COL.CAPITAL_SOCIAL
RESERVA_LEGAL = COL.RESERVA_LEGAL
TESOURARIA = COL.ACOES_OU_QUOTAS_EM_TESOURARIA

LINHA_DIVIDENDOS = "dividendos"
LINHA_AQUISICAO = "aquisicao_de_acoes_ou_quotas_em_tesouraria"
LINHA_ALIENACAO = "alienacao_ou_cancelamento_de_acoes_ou_quotas_em_tesouraria"
LINHA_REVERSAO = "reversao_de_reservas"
LINHA_CAPITAL_COM_RESERVAS = "aumento_de_capital_com_reservas_e_lucros"

ACAO_DA_TRILHA = "lancamento.marcacoes_dmpl_alteradas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _marc(linha, coluna, valor):
    """Uma marcação no formato do corpo do PUT (o `valor` chega como texto —
    na API ele viaja como TEXTO, DE-030; aqui o serviço normaliza)."""
    return {"linha": linha, "coluna": coluna, "valor": _dec(valor)}


def _salvar(lancamento, marcacoes, usuario):
    return salvar_marcacoes_da_dmpl(lancamento=lancamento, marcacoes=marcacoes, usuario=usuario)


def _com_tesouraria():
    """`_caso_a` mais as contas de tesouraria e de ajustes do caso B (sem os
    lançamentos do caso B): é o cenário da M2, com a coluna de tesouraria
    pronta para receber o par marcado."""
    empresa, contas, gestor = _caso_a()
    contas.update(_contas_do_caso_b(empresa, contas["pl"]))
    return empresa, contas, gestor


def _cenario_m3():
    """O caso M3 da reconferência: dividendo pago com a reserva legal e o
    estorno exato — o par que a regra automática não decide (o original é
    "dividendo positivo em reserva", pendência; o estorno é decidido como
    "dividendos")."""
    empresa, contas, gestor = _caso_a()
    pagamento = _lancar(
        empresa,
        date(2026, 3, 10),
        "Dividendo pago com a reserva legal",
        contas["dividendos"],
        contas["reserva_legal"],
        "1000.00",
    )
    estorno = estornar_lancamento(pagamento, data=date(2026, 3, 20), criado_por=gestor)
    return empresa, contas, gestor, pagamento, estorno


def _permuta_de_tesouraria():
    """A M2 da reconferência: compra de 1.500 e venda de 1.000 de ações em
    tesouraria no MESMO lançamento — eventos opostos, vetados pela regra."""
    empresa, contas, gestor = _com_tesouraria()
    permuta = _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Permuta de ações em tesouraria",
        [
            (contas["tesouraria"], "D", "1500.00"),
            (contas["caixa"], "D", "1000.00"),
            (contas["caixa"], "C", "1500.00"),
            (contas["tesouraria"], "C", "1000.00"),
        ],
    )
    return empresa, contas, gestor, permuta


def _campos_do_lancamento(lancamento):
    return {
        campo: getattr(lancamento, campo)
        for campo in (
            "data",
            "historico",
            "estorno_de_id",
            "criado_por_id",
            "criado_em",
            "competencia_id",
            "chave_idempotencia",
            "chave_idempotencia_fingerprint",
        )
    }


def _itens_do_lancamento(lancamento):
    return [(item.conta_id, item.tipo, item.valor) for item in lancamento.itens.order_by("id")]


def _marcacoes_gravadas(lancamento):
    return [
        {"linha": m.linha, "coluna": m.coluna, "valor": str(m.valor)}
        for m in MarcacaoDmpl.objects.filter(lancamento=lancamento).order_by("id")
    ]


# ---------------------------------------------------------------------------
# 1. Caso M3 — dividendo pago com reserva, estornado
# ---------------------------------------------------------------------------


def test_m3_o_par_marcado_libera_a_emissao_e_a_linha_mostra_o_liquido():
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    # Hoje, vetado: o original é "dividendo positivo em reserva" (a regra não
    # decide) e o estorno dele não libera nada sozinho.
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    (pendente,) = dmpl["pendencias"]["contrapartidas_sem_classificacao"]
    assert pagamento.id in pendente["lancamentos"]

    # O ESTORNO é decidido pela regra (linha "dividendos", −1.000): marcar o
    # que a regra decide é recusado (E17) — a marcação é a exceção.
    with pytest.raises(MarcacaoDmplInvalida):
        _salvar(estorno, [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "-1000.00")], gestor)

    # Só o ORIGINAL é marcado (Σ por coluna = efeito: +1.000 na reserva) — é
    # o que o contrato permite.
    _salvar(pagamento, [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "1000.00")], gestor)

    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True, emissao
    # O par (marcado + estorno automático) some na linha: 0,00 na reserva.
    assert _celula(dmpl, LINHA_DIVIDENDOS, RESERVA_LEGAL) == _dec("0.00")
    # …e o bruto de cada lado continua rastreável pelos lançamentos da célula.
    linha = next(item for item in dmpl["linhas"] if item["chave"] == LINHA_DIVIDENDOS)
    assert sorted(linha["lancamentos"][RESERVA_LEGAL]) == sorted([pagamento.id, estorno.id])
    # Saldo e conciliação inalterados: a marcação muda ONDE, não QUANTO.
    assert dmpl["saldo_final"]["valores"][RESERVA_LEGAL] == _dec("1250.00")
    assert dmpl["conciliacao"]["por_coluna"][RESERVA_LEGAL]["diferenca"] == _dec("0.00")


def test_m3_com_os_dois_lados_marcados_mostra_o_mesmo_liquido():
    """O contrato (Σ por coluna = efeito) permite marcar o par inteiro quando
    os DOIS lados são problema — aqui não são, então o ponto é o contrário:
    marcar o estorno junto é recusado, e o resultado do par segue igual."""
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    _salvar(pagamento, [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "1000.00")], gestor)
    with pytest.raises(MarcacaoDmplInvalida):
        _salvar(estorno, [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "-1000.00")], gestor)
    dmpl = _apurar(empresa)
    assert _celula(dmpl, LINHA_DIVIDENDOS, RESERVA_LEGAL) == _dec("0.00")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True


# ---------------------------------------------------------------------------
# 2. Eventos opostos em tesouraria — DUAS linhas, com os brutos
# ---------------------------------------------------------------------------


def test_eventos_opostos_em_tesouraria_marcados_em_duas_linhas_mostram_os_brutos():
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)

    _salvar(
        permuta,
        [
            _marc(LINHA_AQUISICAO, TESOURARIA, "-1500.00"),
            _marc(LINHA_ALIENACAO, TESOURARIA, "1000.00"),
        ],
        gestor,
    )

    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is True, emissao
    # Os BRUTOS saem nas duas linhas — o líquido não é evento nenhum (RC-155).
    assert _celula(dmpl, LINHA_AQUISICAO, TESOURARIA) == _dec("-1500.00")
    assert _celula(dmpl, LINHA_ALIENACAO, TESOURARIA) == _dec("1000.00")
    # E o saldo final continua o efeito líquido real do lançamento.
    assert dmpl["saldo_final"]["valores"][TESOURARIA] == _dec("-500.00")
    assert dmpl["conciliacao"]["por_coluna"][TESOURARIA]["diferenca"] == _dec("0.00")


def test_mesma_coluna_em_duas_linhas_diferentes_e_aceita_e_a_mesma_linha_nao():
    """O contrato do conjunto (E15): linha × coluna única por lançamento — o
    par compra/venda usa DUAS linhas da mesma coluna (aceito); duas
    marcações para a MESMA célula são ambíguas de somar (recusado)."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(
            permuta,
            [
                _marc(LINHA_AQUISICAO, TESOURARIA, "-1500.00"),
                _marc(LINHA_AQUISICAO, TESOURARIA, "1000.00"),
            ],
            gestor,
        )
    assert "DUAS marcações" in str(exc.value)
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


# ---------------------------------------------------------------------------
# 3. Recusas — sucesso, erro e limites
# ---------------------------------------------------------------------------


def test_recusa_quando_a_soma_por_coluna_nao_reproduz_o_efeito():
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(permuta, [_marc(LINHA_AQUISICAO, TESOURARIA, "-1000.00")], gestor)
    mensagem = str(exc.value)
    # A recusa NOMEIA a coluna e os DOIS valores (o que foi marcado e o que o
    # lançamento efetivamente moveu na coluna).
    assert "Ações ou quotas em tesouraria" in mensagem
    assert "-1000.00" in mensagem
    assert "-500.00" in mensagem
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_recusa_linha_fora_do_enum():
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(permuta, [_marc("banana", TESOURARIA, "-500.00")], gestor)
    mensagem = str(exc.value)
    assert '"banana"' in mensagem
    assert "linha" in mensagem.lower()
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_recusa_coluna_fora_do_enum():
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(permuta, [_marc(LINHA_AQUISICAO, "tesouraria_xpto", "-500.00")], gestor)
    assert '"tesouraria_xpto"' in str(exc.value)
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_recusa_valor_zero():
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(permuta, [_marc(LINHA_AQUISICAO, TESOURARIA, "0")], gestor)
    assert "zero" in str(exc.value)
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_recusa_linha_de_saldo():
    """Decisão de implementação registrada: as linhas de saldo são
    CALCULADAS pela apuração, nunca distribuídas — marcar nelas faria a
    célula sumir do documento (ver `MarcacaoDmpl.clean()`)."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    for linha_de_saldo in ("saldo_inicial", "saldo_final"):
        with pytest.raises(MarcacaoDmplInvalida) as exc:
            _salvar(permuta, [_marc(linha_de_saldo, TESOURARIA, "-500.00")], gestor)
        assert "saldo" in str(exc.value).lower()


def test_recusa_lancamento_que_a_regra_decide_so_zinho():
    """E17 (RC-151 como propriedade): se a regra decide, o servidor recusa —
    "repartir à mão" não vira caminho normal."""
    empresa, contas, gestor = _caso_a()
    decidido = _lancar(
        empresa,
        date(2026, 2, 10),
        "Aumento de capital",
        contas["caixa"],
        contas["capital"],
        "200.00",
    )
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(decidido, [_marc("aumento_de_capital", CAPITAL, "200.00")], gestor)
    assert "regra automática" in str(exc.value)
    assert not MarcacaoDmpl.objects.filter(lancamento=decidido).exists()


def test_recusa_coluna_sem_conta_classificada():
    """A célula de uma coluna que não aparece no documento SUMIRIA: recusada
    antes de gravar, com a ação que resolve (classificar a conta)."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    proposto = COL.DIVIDENDO_ADICIONAL_PROPOSTO
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(
            permuta,
            [
                _marc(LINHA_DIVIDENDOS, proposto, "500.00"),
                _marc(LINHA_REVERSAO, proposto, "-500.00"),
            ],
            gestor,
        )
    assert "não aparece na DMPL" in str(exc.value)


def test_recusa_em_lancamento_de_outra_empresa_e_404_na_api(client):
    """Isolamento nos dois níveis: a API responde 404 (o lançamento não
    existe NESTA empresa) e nada é gravado em lugar nenhum."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    outra = _caso_a()[0]  # outra empresa, outro escritório
    _autenticar(client, empresa.escritorio, username="gestor-bl605-iso")

    resposta = client.put(
        reverse("contabilidade:marcacao-dmpl", args=[empresa.id, outra.lancamentos.first().id]),
        data={"marcacoes": [{"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": "-500.00"}]},
        content_type="application/json",
    )
    assert resposta.status_code == 404, resposta.content
    assert not MarcacaoDmpl.objects.filter(lancamento__empresa=outra).exists()
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_o_modelo_recusa_marcacao_de_empresa_diferente_da_do_lancamento():
    """A defesa do MODELO (mesma guarda de `ItemLancamento.clean()`): a
    marcação é da MESMA empresa do lançamento. O isolamento por requisição é
    o 404 da API (teste acima) — aqui é a camada de conveniência do
    admin/`ModelForm`, que não passa pela view."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    outra_empresa = _caso_a()[0]
    lancamento_alheio = outra_empresa.lancamentos.first()
    marcacao = MarcacaoDmpl(
        lancamento=lancamento_alheio,
        empresa=empresa,  # empresa ERRADA (a do lançamento é outra)
        linha=LINHA_AQUISICAO,
        coluna=TESOURARIA,
        valor=_dec("-500.00"),
    )
    with pytest.raises(ValidationError):
        marcacao.full_clean()


# ---------------------------------------------------------------------------
# 3b. Correção da reconferência (A1/A2) — evento inventado e chave extra
# ---------------------------------------------------------------------------


def test_recusa_par_em_coluna_que_o_lancamento_nao_move():
    """A1 (MÉDIA): o par líquido zero em coluna que o lançamento NÃO
    movimentava passava no Σ (0 = 0) e virava evento INVENTADO no documento.
    Agora a recusa exige item do lançamento na coluna e NOMEIA a coluna — e o
    gêmeo legítimo (teste abaixo) continua aceito: a propriedade vem dos
    ITENS, nunca do efeito líquido."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(
            permuta,
            [
                _marc("aumento_de_capital", CAPITAL, "500.00"),
                _marc("reducao_de_capital", CAPITAL, "-500.00"),
            ],
            gestor,
        )
    mensagem = str(exc.value)
    assert "Capital social" in mensagem
    assert "não movimenta" in mensagem
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_marcacao_forcada_em_coluna_nao_movimentada_nao_vira_celula():
    """A1 (ii): a MESMA marcação gravada à força (ORM/SQL direto) não vira
    célula em `apurar_dmpl` — a defesa de leitura volta para a regra
    automática (o veto do lançamento ambíguo acende de novo)."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    for linha, coluna, valor in (
        (LINHA_AQUISICAO, TESOURARIA, "-1500.00"),
        (LINHA_ALIENACAO, TESOURARIA, "1000.00"),
        # O par INVENTADO: capital não tem item nenhum neste lançamento.
        ("aumento_de_capital", CAPITAL, "500.00"),
        ("reducao_de_capital", CAPITAL, "-500.00"),
    ):
        MarcacaoDmpl.objects.create(
            lancamento=permuta,
            empresa=empresa,
            linha=linha,
            coluna=coluna,
            valor=_dec(valor),
            criado_por=gestor,
        )

    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)
    # Nenhuma célula publicada — nem a do par inventado, nem as demais: o
    # lançamento inteiro volta para a leitura automática.
    assert "aumento_de_capital" not in _chaves_das_linhas(dmpl)
    assert "reducao_de_capital" not in _chaves_das_linhas(dmpl)
    assert LINHA_AQUISICAO not in _chaves_das_linhas(dmpl)


def test_gemeo_legitimo_efeito_zero_com_itens_reais_na_coluna_continua_aceito():
    """A1 (iii), o gêmeo que a regra nova tem de preservar: compra e venda de
    tesouraria de valores IGUAIS no mesmo lançamento — efeito líquido zero na
    coluna, mas com itens REAIS nela. Continua marcável e publicado como os
    dois eventos brutos (o líquido zero não apaga o que aconteceu)."""
    empresa, contas, gestor = _com_tesouraria()
    permuta_igual = _lancar_itens(
        empresa,
        date(2026, 2, 6),
        "Compra e venda de ações em tesouraria no mesmo dia",
        [
            (contas["tesouraria"], "D", "1000.00"),
            (contas["caixa"], "D", "500.00"),
            (contas["caixa"], "C", "500.00"),
            (contas["tesouraria"], "C", "1000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)

    _salvar(
        permuta_igual,
        [
            _marc(LINHA_AQUISICAO, TESOURARIA, "-1000.00"),
            _marc(LINHA_ALIENACAO, TESOURARIA, "1000.00"),
        ],
        gestor,
    )

    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, LINHA_AQUISICAO, TESOURARIA) == _dec("-1000.00")
    assert _celula(dmpl, LINHA_ALIENACAO, TESOURARIA) == _dec("1000.00")
    # O saldo segue o efeito líquido real (zero) e a conciliação fecha.
    assert dmpl["saldo_final"]["valores"][TESOURARIA] == _dec("0.00")
    assert dmpl["conciliacao"]["por_coluna"][TESOURARIA]["diferenca"] == _dec("0.00")


def test_recusa_item_com_chave_extra_no_servico():
    """A2 (BAIXA): o serviço recusa a chave A MAIS em vez de descartá-la em
    silêncio (BL-196) — coerente com a recusa do PUT, e verificado também no
    caminho que não passa pela API."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    with pytest.raises(MarcacaoDmplInvalida) as exc:
        _salvar(
            permuta,
            [
                {
                    "linha": LINHA_AQUISICAO,
                    "coluna": TESOURARIA,
                    "valor": _dec("-500.00"),
                    "x": 1,
                }
            ],
            gestor,
        )
    assert "nada além disso" in str(exc.value)
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


# ---------------------------------------------------------------------------
# 4. Desmarcar devolve o veto exatamente como antes
# ---------------------------------------------------------------------------


def test_desmarcar_devolve_o_veto_exatamente_como_antes():
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    pendencias_antes = _apurar(empresa)["pendencias"]
    motivos_antes = avaliar_emissao_da_dmpl(_apurar(empresa))["motivos"]
    # Com o veto, o lançamento problemático NÃO publica célula nenhuma — só o
    # estorno (decidido pela regra) aparece, com o −1.000 automático.
    celula_antes = _celula(_apurar(empresa), LINHA_DIVIDENDOS, RESERVA_LEGAL)
    assert celula_antes == _dec("-1000.00")
    assert pendencias_antes["contrapartidas_sem_classificacao"]

    _salvar(pagamento, [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "1000.00")], gestor)
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is True
    assert _celula(_apurar(empresa), LINHA_DIVIDENDOS, RESERVA_LEGAL) == _dec("0.00")

    remover_marcacoes_da_dmpl(lancamento=pagamento, usuario=gestor)

    dmpl = _apurar(empresa)
    assert dmpl["pendencias"] == pendencias_antes
    assert avaliar_emissao_da_dmpl(dmpl)["motivos"] == motivos_antes
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    # A célula volta a ser exatamente a de antes — o veto não publica evento.
    assert _celula(dmpl, LINHA_DIVIDENDOS, RESERVA_LEGAL) == celula_antes


def test_limpar_com_lista_vazia_e_o_mesmo_que_remover():
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    _salvar(pagamento, [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "1000.00")], gestor)
    _salvar(pagamento, [], gestor)
    assert not MarcacaoDmpl.objects.filter(lancamento=pagamento).exists()
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is False


# ---------------------------------------------------------------------------
# 5. Trilha — cada salvar/limpar grava ator e antes/depois
# ---------------------------------------------------------------------------


def test_cada_salvar_e_limpar_grava_trilha_com_ator_e_antes_depois():
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    _salvar(
        pagamento,
        [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "1000.00")],
        gestor,
    )
    _salvar(
        pagamento,
        [
            _marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "400.00"),
            _marc(LINHA_REVERSAO, RESERVA_LEGAL, "600.00"),
        ],
        gestor,
    )
    remover_marcacoes_da_dmpl(lancamento=pagamento, usuario=gestor)

    registros = list(RegistroAuditoria.objects.filter(acao=ACAO_DA_TRILHA).order_by("id"))
    assert len(registros) == 3
    primeiro, segundo, terceiro = registros
    for registro in registros:
        assert registro.usuario_id == gestor.id
        assert registro.objeto_tipo == "LancamentoContabil"
        assert registro.objeto_id == str(pagamento.id)
    assert primeiro.detalhes == {
        "marcacoes_antes": [],
        "marcacoes_depois": [
            {"linha": LINHA_DIVIDENDOS, "coluna": RESERVA_LEGAL, "valor": "1000.00"}
        ],
    }
    assert segundo.detalhes["marcacoes_antes"] == [
        {"linha": LINHA_DIVIDENDOS, "coluna": RESERVA_LEGAL, "valor": "1000.00"}
    ]
    assert segundo.detalhes["marcacoes_depois"] == [
        {"linha": LINHA_DIVIDENDOS, "coluna": RESERVA_LEGAL, "valor": "400.00"},
        {"linha": LINHA_REVERSAO, "coluna": RESERVA_LEGAL, "valor": "600.00"},
    ]
    assert terceiro.detalhes["marcacoes_depois"] == []
    assert terceiro.detalhes["marcacoes_antes"] == [
        {"linha": LINHA_DIVIDENDOS, "coluna": RESERVA_LEGAL, "valor": "400.00"},
        {"linha": LINHA_REVERSAO, "coluna": RESERVA_LEGAL, "valor": "600.00"},
    ]


def test_recusa_nao_grava_trilha_nem_muda_nada():
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    registros_antes = RegistroAuditoria.objects.count()
    with pytest.raises(MarcacaoDmplInvalida):
        _salvar(permuta, [_marc(LINHA_AQUISICAO, TESOURARIA, "-1.00")], gestor)
    assert RegistroAuditoria.objects.count() == registros_antes
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


# ---------------------------------------------------------------------------
# 6. Imutabilidade — o lançamento marcado não muda nenhum campo
# ---------------------------------------------------------------------------


def test_marcar_nao_muda_nenhum_campo_do_lancamento_nem_dos_itens():
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    campos_antes = _campos_do_lancamento(permuta)
    itens_antes = _itens_do_lancamento(permuta)

    _salvar(
        permuta,
        [
            _marc(LINHA_AQUISICAO, TESOURARIA, "-1500.00"),
            _marc(LINHA_ALIENACAO, TESOURARIA, "1000.00"),
        ],
        gestor,
    )

    relido = LancamentoContabil.objects.get(pk=permuta.pk)
    assert _campos_do_lancamento(relido) == campos_antes
    assert _itens_do_lancamento(relido) == itens_antes
    # A marcação é guardada FORA do livro (E15): nada dela entra no lançamento.
    assert not hasattr(relido, "marcacoes_alteradas")


def test_o_lancamento_marcado_continua_imutavel_ao_save_e_ao_delete():
    from apps.contabilidade.models import LancamentoImutavelError

    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _salvar(permuta, [_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")], gestor)
    relido = LancamentoContabil.objects.get(pk=permuta.pk)
    with pytest.raises(LancamentoImutavelError):
        relido.save()
    with pytest.raises(LancamentoImutavelError):
        relido.delete()


# ---------------------------------------------------------------------------
# 7. Identidade DLPA × DMPL com marcação na coluna de lucros acumulados
# ---------------------------------------------------------------------------


def test_identidade_com_a_dlpa_vale_com_marcacao_na_coluna_de_lucros():
    """O lançamento ambíguo (`D reserva 300 / D lucros 200 / C capital 500`)
    é a M3(b): a regra não atribui cada valor a uma linha só. A marcação
    decide o par linha × coluna reproduzindo a leitura da DLPA (reversão de
    reserva de 300 e lucro incorporado ao capital de 500), e a identidade
    DLPA × DMPL continua valendo — inclusive na coluna de lucros."""
    empresa, contas, gestor = _caso_a()
    ambiguo = _lancar_itens(
        empresa,
        date(2026, 3, 25),
        "Reserva e lucros incorporados ao capital",
        [
            (contas["reserva_legal"], "D", "300.00"),
            (contas["lucros"], "D", "200.00"),
            (contas["capital"], "C", "500.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)

    _salvar(
        ambiguo,
        [
            _marc(LINHA_REVERSAO, LUCROS, "300.00"),
            _marc(LINHA_CAPITAL_COM_RESERVAS, LUCROS, "-500.00"),
            _marc(LINHA_REVERSAO, RESERVA_LEGAL, "-300.00"),
            _marc(LINHA_CAPITAL_COM_RESERVAS, CAPITAL, "500.00"),
        ],
        gestor,
    )

    _conferir_identidade_com_a_dlpa(empresa)
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, LINHA_REVERSAO, LUCROS) == _dec("300.00")
    assert _celula(dmpl, LINHA_CAPITAL_COM_RESERVAS, LUCROS) == _dec("-500.00")


# ---------------------------------------------------------------------------
# 8. API da DMPL (E18)
# ---------------------------------------------------------------------------


def _url_da_dmpl(empresa):
    return reverse("contabilidade:dmpl", args=[empresa.id, ANO, MES])


def _url_da_marcacao(empresa, lancamento):
    return reverse("contabilidade:marcacao-dmpl", args=[empresa.id, lancamento.id])


def _url_da_classificacao(empresa, conta):
    return reverse("contabilidade:conta-classificacao-dmpl", args=[empresa.id, conta.id])


def _moeda(valor):
    return str(_dec(valor).quantize(_dec("0.01")))


def test_api_get_da_dmpl_bate_com_a_apuracao(client):
    """A view REVELA, não recalcula: cada linha, cada célula, cada saldo e a
    conciliação vêm de `apurar_dmpl`, com dinheiro como texto de duas casas
    (DL-030)."""
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    _salvar(pagamento, [_marc(LINHA_DIVIDENDOS, RESERVA_LEGAL, "1000.00")], gestor)
    dmpl = _apurar(empresa)

    _autenticar(client, empresa.escritorio, username="gestor-bl605-get")
    resposta = client.get(_url_da_dmpl(empresa))
    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()

    assert corpo["pode_emitir"] is True
    assert corpo["empresa_id"] == dmpl["empresa_id"]
    assert [c["chave"] for c in corpo["colunas"]] == [c["chave"] for c in dmpl["colunas"]]

    for linha_api, linha_apurada in zip(corpo["linhas"], dmpl["linhas"], strict=True):
        assert linha_api["chave"] == linha_apurada["chave"]
        assert linha_api["titulo"] == linha_apurada["titulo"]
        assert linha_api["valores"] == {
            coluna: _moeda(valor) for coluna, valor in linha_apurada["valores"].items()
        }
        assert linha_api["total"] == _moeda(linha_apurada["total"])

    assert corpo["saldo_final"] == {
        "valores": {c: _moeda(v) for c, v in dmpl["saldo_final"]["valores"].items()},
        "total": _moeda(dmpl["saldo_final"]["total"]),
    }
    assert corpo["conciliacao"]["por_coluna"] == {
        coluna: {
            "saldo_na_dmpl": _moeda(v["saldo_na_dmpl"]),
            "saldo_no_balanco": _moeda(v["saldo_no_balanco"]),
            "diferenca": _moeda(v["diferenca"]),
        }
        for coluna, v in dmpl["conciliacao"]["por_coluna"].items()
    }
    # Dinheiro NUNCA volta como float (DL-030).
    bruto = resposta.content.decode()
    assert '"1250.00"' in bruto
    assert "1250.0," not in bruto and "1250.0}" not in bruto


def test_api_get_com_pendencia_responde_409_com_o_corpo_inteiro(client):
    """O status informa o veto; o corpo continua trazendo a apuração e o que
    falta, nomeado — mesmo contrato de `DlpaView`."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _autenticar(client, empresa.escritorio, username="gestor-bl605-409")
    resposta = client.get(_url_da_dmpl(empresa))
    assert resposta.status_code == 409, resposta.content
    corpo = resposta.json()
    assert corpo["pode_emitir"] is False
    assert corpo["linhas"] and corpo["saldo_final"]
    assert corpo["listas_pendentes"]["lancamentos_ambiguos"]
    assert corpo["motivos"]


def test_api_marcacao_get_put_delete_do_conjunto(client):
    """GET lê o conjunto; PUT substitui o conjunto INTEIRO de uma vez (as
    marcações antigas somem, não se acumulam); DELETE limpa — e o veto do
    lançamento volta. Tudo com dinheiro como texto."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _autenticar(client, empresa.escritorio, username="gestor-bl605-put")

    endereco = _url_da_marcacao(empresa, permuta)
    assert client.get(endereco).json() == {"lancamento_id": permuta.id, "marcacoes": []}

    corpo_primeiro = {
        "marcacoes": [
            {"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": "-1500.00"},
            {"linha": LINHA_ALIENACAO, "coluna": TESOURARIA, "valor": "1000.00"},
        ]
    }
    resposta = client.put(endereco, data=corpo_primeiro, content_type="application/json")
    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["marcacoes"] == corpo_primeiro["marcacoes"]
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is True

    # Substituição atômica: o segundo PUT é o conjunto NOVO, não um acréscimo
    # — e ele também reproduz o movimento da coluna (Σ = −500), então é
    # aceito. A marcação decide Onde o valor aparece: um único evento
    # "aquisição" de −500 no lugar do par bruto.
    corpo_segundo = {
        "marcacoes": [{"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": "-500.00"}]
    }
    resposta = client.put(endereco, data=corpo_segundo, content_type="application/json")
    assert resposta.status_code == 200, resposta.content
    assert client.get(endereco).json()["marcacoes"] == corpo_segundo["marcacoes"]
    assert _celula(_apurar(empresa), LINHA_AQUISICAO, TESOURARIA) == _dec("-500.00")
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is True

    # DELETE limpa o conjunto e o lançamento volta para a regra automática —
    # o veto (eventos opostos) acende exatamente como antes.
    resposta = client.delete(endereco)
    assert resposta.status_code == 200, resposta.content
    assert resposta.json() == {"lancamento_id": permuta.id, "marcacoes": []}
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is False


def test_api_put_com_conjunto_invalido_e_400_e_nada_muda(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _autenticar(client, empresa.escritorio, username="gestor-bl605-400")
    endereco = _url_da_marcacao(empresa, permuta)

    recusados = [
        # Σ por coluna errado (nomeia a coluna e os valores).
        {"marcacoes": [{"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": "-1000.00"}]},
        # linha fora do enum.
        {"marcacoes": [{"linha": "banana", "coluna": TESOURARIA, "valor": "-500.00"}]},
        # coluna fora do enum.
        {"marcacoes": [{"linha": LINHA_AQUISICAO, "coluna": "xpto", "valor": "-500.00"}]},
        # valor zero.
        {"marcacoes": [{"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": "0"}]},
        # DE-030: dinheiro viaja como TEXTO, nunca como número JSON.
        {"marcacoes": [{"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": -500.0}]},
        # chave desconhecida dentro do item — nunca ignorada em silêncio.
        {
            "marcacoes": [
                {"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": "-500.00", "x": 1}
            ]
        },
        # `marcacoes` que não é lista.
        {"marcacoes": {"linha": LINHA_AQUISICAO}},
    ]
    for corpo in recusados:
        resposta = client.put(endereco, data=corpo, content_type="application/json")
        assert resposta.status_code == 400, (corpo, resposta.status_code, resposta.content)
        assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()

    # Corpo malformado não vira 500 nem silêncio (R3/R8 da auditoria DL-045).
    resposta = client.put(endereco, data=[], content_type="application/json")
    assert resposta.status_code == 400, resposta.content


def test_api_cliente_recebe_403_em_todas_as_rotas_de_marcacao(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _salvar(permuta, [_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")], gestor)
    _autenticar(client, empresa.escritorio, papel=Papel.CLIENTE, username="cliente-bl605")

    for resposta in (
        client.get(_url_da_dmpl(empresa)),
        client.get(_url_da_marcacao(empresa, permuta)),
        client.put(
            _url_da_marcacao(empresa, permuta),
            data={"marcacoes": []},
            content_type="application/json",
        ),
        client.delete(_url_da_marcacao(empresa, permuta)),
        client.patch(
            _url_da_classificacao(empresa, contas["lucros"]),
            data={"classificacao_dmpl": LUCROS},
            content_type="application/json",
        ),
    ):
        assert resposta.status_code == 403, resposta.content
        bruto = resposta.content.decode()
        assert "500.00" not in bruto
    # 403 não escreve nada: a marcação gravada antes continua igual.
    assert _marcacoes_gravadas(permuta) == [
        {"linha": LINHA_AQUISICAO, "coluna": TESOURARIA, "valor": "-500.00"}
    ]


def test_api_empresa_de_outro_escritorio_recebe_404(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    outro = _empresa("Outro Escritório BL-605")
    _autenticar(client, outro.escritorio, username="gestor-bl605-alheio")

    assert client.get(_url_da_dmpl(empresa)).status_code == 404
    assert client.get(_url_da_marcacao(empresa, permuta)).status_code == 404
    resposta = client.put(
        _url_da_marcacao(empresa, permuta),
        data={"marcacoes": []},
        content_type="application/json",
    )
    assert resposta.status_code == 404
    assert empresa.razao_social not in resposta.content.decode()


def test_api_patch_classifica_a_coluna_e_grava_trilha(client):
    """O espelho do endpoint da DLPA (E18): PATCH da coluna da conta, com
    trilha antes/depois e 404 para conta de outra empresa."""
    from apps.contabilidade.models import Conta

    empresa, contas, gestor = _caso_a()
    _autenticar(client, empresa.escritorio, username="gestor-bl605-patch")
    conta = contas["capital"]
    assert conta.classificacao_dmpl == CAPITAL

    # Remover a coluna é operação normal (null)…
    resposta = client.patch(
        _url_da_classificacao(empresa, conta),
        data={"classificacao_dmpl": None},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["classificacao_dmpl"] is None
    assert Conta.objects.get(pk=conta.pk).classificacao_dmpl is None

    # …e recolocar, também — com trilha do antes e do depois em cada ato.
    resposta = client.patch(
        _url_da_classificacao(empresa, conta),
        data={"classificacao_dmpl": CAPITAL},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["classificacao_dmpl"] == CAPITAL

    ator = get_user_model().objects.get(username="gestor-bl605-patch")
    registros = list(
        RegistroAuditoria.objects.filter(acao="conta.classificacao_dmpl_alterada").order_by("id")
    )
    assert [r.detalhes for r in registros] == [
        {"classificacao_dmpl_antes": "capital_social", "classificacao_dmpl_depois": None},
        {"classificacao_dmpl_antes": None, "classificacao_dmpl_depois": "capital_social"},
    ]
    assert all(r.usuario_id == ator.id for r in registros)

    # Conta de outra empresa: 404 (isolamento), nunca 403.
    outra = _caso_a()[0]
    resposta = client.patch(
        _url_da_classificacao(empresa, outra.lancamentos.first().itens.first().conta),
        data={"classificacao_dmpl": CAPITAL},
        content_type="application/json",
    )
    assert resposta.status_code == 404, resposta.content


# ---------------------------------------------------------------------------
# Defesas do contrato — banco e deriva
# ---------------------------------------------------------------------------


def test_o_banco_recusa_duplicata_de_celula_e_valor_zero():
    """As duas `Meta.constraints` de `MarcacaoDmpl` são defesa de banco
    (DE-008, camada 1): o serviço já recusa antes, e estas provam que o
    ORM/SQL direto não passa em silêncio."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    dados = {
        "lancamento": permuta,
        "empresa": empresa,
        "linha": LINHA_AQUISICAO,
        "coluna": TESOURARIA,
        "valor": _dec("-500.00"),
        "criado_por": gestor,
    }
    MarcacaoDmpl.objects.create(**dados)
    with pytest.raises(IntegrityError), transaction.atomic():
        MarcacaoDmpl.objects.create(**dados)
    with pytest.raises(IntegrityError), transaction.atomic():
        MarcacaoDmpl.objects.create(**{**dados, "valor": _dec("0"), "linha": LINHA_ALIENACAO})


def test_marcacao_desatualizada_volta_para_a_regra_e_o_veto_acende():
    """Defesa da leitura (`_marcacoes_valem_como_celulas`): se a classificação
    de conta mudar DEPOIS da marcação, o conjunto deixa de reproduzir o
    movimento do lançamento — a apuração volta para a leitura automática e o
    veto acende, em vez de publicar eventos que não fecham com o saldo."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _salvar(
        permuta,
        [
            _marc(LINHA_AQUISICAO, TESOURARIA, "-1500.00"),
            _marc(LINHA_ALIENACAO, TESOURARIA, "1000.00"),
        ],
        gestor,
    )
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is True

    classificar_conta_na_dmpl(conta=contas["tesouraria"], classificacao=None, usuario=gestor)

    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert LINHA_AQUISICAO not in _chaves_das_linhas(dmpl)
    assert LINHA_ALIENACAO not in _chaves_das_linhas(dmpl)


def test_marcacao_em_coluna_que_saiu_do_documento_nao_vira_celula_fantasma():
    """A segunda condição da defesa da leitura: célula de coluna sem conta
    classificada NÃO renderiza — ela não pode entrar no documento em
    silêncio. O par abaixo soma ZERO na coluna (passaria pela igualdade de
    Σ, que trata coluna ausente como zero), e ainda assim não vira célula."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    proposto = COL.DIVIDENDO_ADICIONAL_PROPOSTO
    # O serviço recusa no ato de marcar…
    with pytest.raises(MarcacaoDmplInvalida):
        _salvar(
            permuta,
            [
                _marc(LINHA_DIVIDENDOS, proposto, "500.00"),
                _marc(LINHA_REVERSAO, proposto, "-500.00"),
            ],
            gestor,
        )
    # …e, mesmo que o par existisse gravado (ORM/SQL direto), a apuração não
    # publicaria as células: volta para a regra automática (o veto do
    # lançamento ambíguo acende de novo).
    for valor in ("500.00", "-500.00"):
        MarcacaoDmpl.objects.create(
            lancamento=permuta,
            empresa=empresa,
            linha=LINHA_DIVIDENDOS if valor == "500.00" else LINHA_REVERSAO,
            coluna=proposto,
            valor=_dec(valor),
            criado_por=gestor,
        )
    dmpl = _apurar(empresa)
    assert proposto not in {coluna["chave"] for coluna in dmpl["colunas"]}
    for linha in dmpl["linhas"]:
        assert linha["valores"].get(proposto, _dec("0")) == _dec("0")
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
