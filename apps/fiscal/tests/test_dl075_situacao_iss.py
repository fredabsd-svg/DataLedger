"""DL-075 (frente C, HI-80) — situação do ISS na receita informada.

A receita informada do mercado INTERNO exige a situação do ISS (próprio município, outro
município ou retido). A da EXPORTAÇÃO não tem situação. Não há valor padrão: o serviço, a
API e a tela recusam a falta ou o excesso ANTES de gravar; o banco recusa o que escapa do
Python; a receita confirmada não muda a situação por UPDATE SQL direto; e o pré-DAS
recusa, nomeando cada receita, a receita antiga confirmada sem situação.

Dispositivos: LC 123, art. 18, § 4º-A; Res. CGSN 140, art. 25, § 9º (HI-80, hipótese de
produto; decisão do Fred pendente). Dados sintéticos; os esperados são escritos à mão.
"""

import json
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    EnquadramentoAtividade,
    EstadoReceitaInformada,
    MercadoReceita,
    ReceitaInformada,
    SituacaoIssReceitaInformada,
)
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    janela_de_receitas,
)

pytestmark = pytest.mark.django_db

PROPRIO = SituacaoIssReceitaInformada.PROPRIO_MUNICIPIO
OUTRO = SituacaoIssReceitaInformada.OUTRO_MUNICIPIO
RETIDO = SituacaoIssReceitaInformada.RETIDO
CODIGO_SEM_SITUACAO = "receita_informada_sem_situacao_iss"
DISPOSITIVO_SITUACAO = "LC 123, art. 18, § 4º-A; Res. CGSN 140, art. 25, § 9º; HI-80"
RESTRICAO_IMUTAVEL = "receita_informada_imutavel_depois_de_confirmada"
_AUSENTE = object()


def _lancar(
    empresa,
    usuario,
    *,
    mercado="interno",
    situacao=PROPRIO,
    valor="100.00",
    ano=2026,
    mes=5,
    suporte=SUPORTE_SINTETICO,
):
    return servico_receita.lancar_receita_informada(
        empresa,
        ano,
        mes,
        mercado,
        valor,
        "outras_receitas_atividade",
        "Motivo sintético.",
        suporte,
        usuario,
        situacao_iss=situacao,
    )


def _confirmar(empresa, usuario, receita):
    servico_receita.confirmar_receita_informada(receita, usuario)
    return receita


def _recusa_do_banco(restricao, operacao):
    """A operação é recusada PELO BANCO, e a restrição violada é a esperada (pelo nome)."""
    with pytest.raises(IntegrityError) as info:
        with transaction.atomic():
            operacao()
    diag = getattr(info.value.__cause__, "diag", None)
    assert diag is not None and diag.constraint_name == restricao, info.value


def _receita_antiga_confirmada(empresa, usuario, *, ano, mes, valor, suporte):
    """Receita INTERNA confirmada sem situação do ISS, como as de antes da regra (HI-80).

    Não passa pelo serviço, que agora a recusa: é o dado legado que o pré-DAS precisa
    recusar. O banco aceita o INSERT (o gatilho só age em UPDATE e DELETE).
    """
    agora = timezone.now()
    return ReceitaInformada.objects.create(
        empresa=empresa,
        ano=ano,
        mes=mes,
        mercado=MercadoReceita.INTERNO,
        valor=Decimal(valor),
        origem="outras_receitas_atividade",
        motivo="Motivo sintético.",
        documento_suporte=suporte,
        estado=EstadoReceitaInformada.CONFIRMADA,
        criado_por=usuario,
        confirmada_em=agora,
        confirmada_por=usuario,
    )


# ---------------------------------------------------------------------------
# Serviço: recusa antes de gravar (interno exige; exportação proíbe)
# ---------------------------------------------------------------------------


def test_interno_sem_situacao_e_recusado_nomeando_a_regra_e_nada_grava(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)

    with pytest.raises(servico_receita.EntradaInvalidaReceita) as excecao:
        _lancar(empresa, usuario_gestor_a, situacao=None)

    assert "situação do ISS" in excecao.value.mensagem
    assert "HI-80" in excecao.value.mensagem
    assert "Não há valor padrão" in excecao.value.mensagem
    assert not ReceitaInformada.objects.exists()


@pytest.mark.parametrize("vazio", ["", "   "])
def test_interno_com_situacao_em_branco_e_recusado(empresa_a, usuario_gestor_a, vazio):
    empresa = cenario_simples(empresa_a)

    with pytest.raises(servico_receita.EntradaInvalidaReceita, match="situação do ISS"):
        _lancar(empresa, usuario_gestor_a, situacao=vazio)

    assert not ReceitaInformada.objects.exists()


def test_situacao_fora_do_catalogo_e_recusada(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)

    with pytest.raises(servico_receita.EntradaInvalidaReceita, match="fora do catálogo"):
        _lancar(empresa, usuario_gestor_a, situacao="palpite")

    assert not ReceitaInformada.objects.exists()


@pytest.mark.parametrize("situacao", [PROPRIO, OUTRO, RETIDO])
def test_interno_com_situacao_do_catalogo_grava_o_rascunho_com_ela(
    empresa_a, usuario_gestor_a, situacao
):
    empresa = cenario_simples(empresa_a)

    receita = _lancar(empresa, usuario_gestor_a, situacao=situacao)

    receita.refresh_from_db()
    assert receita.situacao_iss == situacao
    assert receita.estado == EstadoReceitaInformada.RASCUNHO


def test_trilha_do_lancamento_registra_a_situacao_do_iss(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)

    receita = _lancar(empresa, usuario_gestor_a, situacao=RETIDO)

    evento = RegistroAuditoria.objects.get(acao="receita_informada.lancada")
    assert evento.objeto_id == str(receita.pk)
    assert evento.detalhes["depois"]["situacao_iss"] == RETIDO


def test_exportacao_com_situacao_do_iss_e_recusada_sem_gravar(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)

    with pytest.raises(servico_receita.EntradaInvalidaReceita) as excecao:
        _lancar(empresa, usuario_gestor_a, mercado="externo", situacao=RETIDO)

    assert "não tem situação do ISS" in excecao.value.mensagem
    assert not ReceitaInformada.objects.exists()


def test_exportacao_sem_situacao_e_aceita_e_fica_sem_situacao(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)

    receita = _lancar(empresa, usuario_gestor_a, mercado="externo", situacao=None)

    receita.refresh_from_db()
    assert receita.mercado == MercadoReceita.EXTERNO
    assert receita.situacao_iss is None


# ---------------------------------------------------------------------------
# API: 400 com a mensagem da regra, 201 com o campo devolvido
# ---------------------------------------------------------------------------


def _base(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}/receitas-informadas/"


def _corpo(**mudancas):
    corpo = {
        "ano": 2026,
        "mes": 5,
        "mercado": "interno",
        "situacao_iss": "retido",
        "valor": "1000.00",
        "origem": "outras_receitas_atividade",
        "motivo": "Motivo sintético.",
        "documento_suporte": SUPORTE_SINTETICO,
    }
    for chave, valor in mudancas.items():
        if valor is _AUSENTE:
            corpo.pop(chave)
        else:
            corpo[chave] = valor
    return corpo


def test_api_interno_sem_situacao_responde_400_e_nada_grava(client, empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _base(empresa),
        data=json.dumps(_corpo(situacao_iss=_AUSENTE)),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "situação do ISS" in resposta.content.decode()
    assert not ReceitaInformada.objects.exists()


def test_api_situacao_fora_do_catalogo_responde_400(client, empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _base(empresa),
        data=json.dumps(_corpo(situacao_iss="palpite")),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not ReceitaInformada.objects.exists()


def test_api_exportacao_com_situacao_responde_400(client, empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _base(empresa),
        data=json.dumps(_corpo(mercado="externo", situacao_iss="retido")),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "não tem situação do ISS" in resposta.content.decode()
    assert not ReceitaInformada.objects.exists()


def test_api_interno_com_situacao_responde_201_e_devolve_o_campo(
    client, empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _base(empresa), data=json.dumps(_corpo(situacao_iss=OUTRO)), content_type="application/json"
    )

    assert resposta.status_code == 201
    assert resposta.json()["situacao_iss"] == OUTRO
    assert resposta.json()["estado"] == EstadoReceitaInformada.RASCUNHO


def test_api_exportacao_sem_situacao_responde_201_com_situacao_nula(
    client, empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _base(empresa),
        data=json.dumps(_corpo(mercado="externo", situacao_iss=_AUSENTE)),
        content_type="application/json",
    )

    assert resposta.status_code == 201
    assert resposta.json()["situacao_iss"] is None


# ---------------------------------------------------------------------------
# Tela: select sem valor pré-selecionado; recusa sem gravar
# ---------------------------------------------------------------------------


def _url_lancar(empresa):
    return reverse("fiscal_web:receita_informada_nova", args=[empresa.pk])


def _formulario(**mudancas):
    dados = {
        "ano": "2026",
        "mes": "05",
        "mercado": "interno",
        "situacao_iss": "retido",
        "valor": "100,00",
        "origem": "outras_receitas_atividade",
        "motivo": "Motivo sintético.",
        "documento_suporte": SUPORTE_SINTETICO,
        "acao": "rascunho",
    }
    dados.update(mudancas)
    return dados


def test_tela_nao_pre_seleciona_a_situacao_do_iss(client, empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    html = client.get(_url_lancar(empresa), {"ano": "2026", "mes": "5"}).content.decode()

    assert 'name="situacao_iss"' in html
    assert '<option value="" selected>Escolha a situação do ISS</option>' in html
    for valor in (PROPRIO, OUTRO, RETIDO):
        assert f'value="{valor}" selected' not in html


def test_tela_recusa_interno_sem_situacao_e_nao_grava(client, empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_lancar(empresa), _formulario(situacao_iss=""))

    assert resposta.status_code == 200
    assert "Informe a situação do ISS" in resposta.content.decode()
    assert not ReceitaInformada.objects.exists()


def test_tela_recusa_exportacao_com_situacao_e_nao_grava(client, empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url_lancar(empresa), _formulario(mercado="externo", situacao_iss=RETIDO)
    )

    assert resposta.status_code == 200
    assert "não tem situação do ISS" in resposta.content.decode()
    assert not ReceitaInformada.objects.exists()


def test_tela_grava_rascunho_com_a_situacao_escolhida(client, empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_lancar(empresa), _formulario(situacao_iss=OUTRO))

    assert resposta.status_code == 302
    receita = ReceitaInformada.objects.get()
    assert receita.situacao_iss == OUTRO
    assert receita.estado == EstadoReceitaInformada.RASCUNHO


# ---------------------------------------------------------------------------
# Banco: catálogo, "fora do interno" e imutabilidade da situação na confirmada
# ---------------------------------------------------------------------------


def test_banco_recusa_situacao_fora_do_catalogo(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    receita = _lancar(empresa, usuario_gestor_a, situacao=PROPRIO)

    _recusa_do_banco(
        "receita_informada_situacao_iss_valida",
        lambda: ReceitaInformada.objects.filter(pk=receita.pk).update(situacao_iss="palpite"),
    )


def test_banco_recusa_situacao_em_exportacao(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    receita = _lancar(empresa, usuario_gestor_a, mercado="externo", situacao=None)

    _recusa_do_banco(
        "receita_informada_iss_so_no_interno",
        lambda: ReceitaInformada.objects.filter(pk=receita.pk).update(situacao_iss=RETIDO),
    )


def test_update_sql_direto_da_situacao_de_receita_confirmada_e_recusado(
    empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    receita = _confirmar(
        empresa, usuario_gestor_a, _lancar(empresa, usuario_gestor_a, situacao=RETIDO)
    )

    def _sql_direto():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE fiscal_receitainformada SET situacao_iss = %s WHERE id = %s",
                [OUTRO, receita.pk],
            )

    _recusa_do_banco(RESTRICAO_IMUTAVEL, _sql_direto)
    receita.refresh_from_db()
    assert receita.situacao_iss == RETIDO


def test_estorno_pelo_banco_nao_pode_trocar_a_situacao(empresa_a, usuario_gestor_a):
    """O estorno só muda as colunas do estorno; a situação do ISS continua a da confirmação."""
    empresa = cenario_simples(empresa_a)
    receita = _confirmar(
        empresa, usuario_gestor_a, _lancar(empresa, usuario_gestor_a, situacao=RETIDO)
    )

    _recusa_do_banco(
        RESTRICAO_IMUTAVEL,
        lambda: ReceitaInformada.objects.filter(pk=receita.pk).update(
            estado=EstadoReceitaInformada.ESTORNADA,
            estornada_em=timezone.now(),
            estornada_por=usuario_gestor_a,
            motivo_estorno="Motivo sintético.",
            situacao_iss=OUTRO,
        ),
    )


# ---------------------------------------------------------------------------
# Pré-DAS: recusa nomeada da receita antiga; segmento pela situação
# ---------------------------------------------------------------------------


def test_receita_interna_confirmada_sem_situacao_bloqueia_e_nomeia_cada_receita(
    empresa_a, usuario_gestor_a
):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    antiga_1 = _receita_antiga_confirmada(
        empresa, usuario_gestor_a, ano=2026, mes=6, valor="60000.00", suporte="NF 101 sintética"
    )
    antiga_2 = _receita_antiga_confirmada(
        empresa, usuario_gestor_a, ano=2026, mes=6, valor="40000.00", suporte="NF 102 sintética"
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as excecao:
        servico_pre_das.pre_das(empresa, 2026, 6)

    (bloqueio,) = [b for b in excecao.value.bloqueios if b.codigo == CODIGO_SEM_SITUACAO]
    assert bloqueio.dispositivo == DISPOSITIVO_SITUACAO
    texto = bloqueio.mensagem
    assert texto.count("receita nº") == 2
    for receita in (antiga_1, antiga_2):
        assert f"receita nº {receita.pk}, competência 06/2026, valor {receita.valor}" in texto
        assert f"documento de suporte '{receita.documento_suporte}'" in texto
    assert "Informe a situação do ISS (estorne e relance)." in texto


def _pre_das_com_receita_informada_retida_ou_outra(empresa_a, usuario, situacao):
    """Janela de 300.000 (Anexo III, 2ª faixa) e 100.000 informados no PA, com a situação."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario, 2026, 6, [25000] * 12)
    receita = _lancar(empresa, usuario, valor="100000.00", situacao=situacao, mes=6)
    _confirmar(empresa, usuario, receita)
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario)
    return servico_pre_das.pre_das(empresa, 2026, 6)


@pytest.mark.parametrize(
    "situacao, segmento, iss, total",
    [
        # Próprio município: segmento normal, o ISS entra no DAS (Anexo III, 2ª faixa: 8,08%).
        (PROPRIO, servico_pre_das.SEG_NORMAL, "2585.60", "8080.00"),
        # Outro município: o ISS entra no DAS com o mesmo percentual; só muda o destino.
        (OUTRO, servico_pre_das.SEG_OUTRO_MUNICIPIO, "2585.60", "8080.00"),
        # Retido: o percentual do ISS é desconsiderado; os federais não mudam (HI-78).
        (RETIDO, servico_pre_das.SEG_RETIDO, "0.00", "5494.40"),
    ],
)
def test_receita_informada_com_situacao_escolhe_o_segmento_do_iss(
    empresa_a, usuario_gestor_a, situacao, segmento, iss, total
):
    resultado = _pre_das_com_receita_informada_retida_ou_outra(
        empresa_a, usuario_gestor_a, situacao
    )

    (anexo,) = resultado.anexos
    (apurado,) = anexo.segmentos
    assert apurado.segmento == segmento
    valores = {linha.tributo: str(linha.valor) for linha in apurado.linhas}
    assert valores["ISS"] == iss
    assert str(resultado.total) == total
