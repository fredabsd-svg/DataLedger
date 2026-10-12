"""DL-084, item 7 (BL-680, item 1) e item 8 (HI-136): encerramento de medida judicial e pendências.

Critério 7: a medida encerrada num trimestre continua valendo nos trimestres anteriores e deixa de
valer nos seguintes; a trilha mostra o encerramento. Dados sintéticos (processo fictício).
"""

import json
from datetime import date

import pytest
from django.db import IntegrityError, connection, transaction

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import EncerramentoMedidaJudicialLC224, MedidaJudicialLC224
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def relogio_fim_de_2026(monkeypatch):
    monkeypatch.setattr(servico, "_hoje", lambda: date(2026, 12, 31))


@pytest.fixture
def presumido(empresa_a, usuario_gestor_a, escritorio_a):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    servico.criar_atividade(
        empresa_a,
        {
            "atividade": tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA,
            "inicio": date(2026, 1, 1),
            "padrao": True,
        },
        usuario_gestor_a,
    )
    return {"empresa": empresa_a, "usuario": usuario_gestor_a}


def _medida(presumido, ano=2026, trimestre=1, ano_final=None, trimestre_final=None):
    dados = {
        "tributo": "irpj",
        "ano_inicial": ano,
        "trimestre_inicial": trimestre,
        "ano_final": ano_final,
        "trimestre_final": trimestre_final,
        "numero_processo": "PROCESSO-SINTETICO-0001",
        "orgao": "Juízo sintético",
        "data_decisao": "2026-01-15",
        "deposito_judicial": False,
        "suporte": "Decisão sintética",
    }
    return servico.cadastrar_medida(presumido["empresa"], dados, presumido["usuario"])


def _situacao_irpj(presumido, trimestre):
    return servico.apurar_trimestre(presumido["empresa"], 2026, trimestre).irpj.medida


# ---------------------------------------------------------------------------
# Critério 7: vale antes, deixa de valer depois, e a trilha mostra o encerramento
# ---------------------------------------------------------------------------


def test_medida_encerrada_no_segundo_trimestre_vale_ate_ele_e_nao_depois(presumido):
    medida = _medida(presumido)
    assert [_situacao_irpj(presumido, t) for t in (1, 2, 3, 4)] == ["suspensa"] * 4

    servico.encerrar_medida(
        presumido["empresa"], medida.pk, 2026, 2, "decisão cassada sintética", presumido["usuario"]
    )

    # 1º e 2º trimestres continuam com a medida; 3º e 4º deixam de valer.
    assert [_situacao_irpj(presumido, t) for t in (1, 2, 3, 4)] == [
        "suspensa",
        "suspensa",
        "nenhuma",
        "nenhuma",
    ]


def test_encerramento_nao_apaga_a_medida_nem_muda_os_dados_dela(presumido):
    medida = _medida(presumido)
    antes = (medida.ativa, medida.ano_final, medida.trimestre_final, medida.numero_processo)
    servico.encerrar_medida(presumido["empresa"], medida.pk, 2026, 2, "x", presumido["usuario"])
    medida.refresh_from_db()
    assert (medida.ativa, medida.ano_final, medida.trimestre_final, medida.numero_processo) == antes
    assert MedidaJudicialLC224.objects.filter(pk=medida.pk).exists()


def test_trilha_mostra_o_encerramento_com_antes_e_depois(presumido):
    medida = _medida(presumido)
    servico.encerrar_medida(
        presumido["empresa"], medida.pk, 2026, 2, "decisão cassada", presumido["usuario"]
    )
    registro = RegistroAuditoria.objects.get(acao="presumido.medida_encerrada")
    assert registro.detalhes["antes"] == {"fim_efetivo": None}
    assert registro.detalhes["depois"] == {"fim_efetivo": "2026/T2"}
    assert registro.detalhes["medida_id"] == medida.pk


def test_encerrar_so_antecipa_nao_estende_a_medida_que_ja_tem_fim(presumido):
    medida = _medida(presumido, ano_final=2026, trimestre_final=3)
    # 4º trimestre seria estender: recusado.
    with pytest.raises(servico.PresumidoConflito):
        servico.encerrar_medida(presumido["empresa"], medida.pk, 2026, 4, "x", presumido["usuario"])
    # 2º trimestre antecipa o fim que era o 3º: aceito.
    servico.encerrar_medida(presumido["empresa"], medida.pk, 2026, 2, "x", presumido["usuario"])
    assert servico.fim_efetivo_da_medida(medida) == (2026, 2)


def test_segundo_encerramento_da_mesma_medida_e_recusado(presumido):
    medida = _medida(presumido)
    servico.encerrar_medida(presumido["empresa"], medida.pk, 2026, 2, "x", presumido["usuario"])
    with pytest.raises(servico.PresumidoConflito):
        servico.encerrar_medida(presumido["empresa"], medida.pk, 2026, 1, "x", presumido["usuario"])


def test_encerramento_antes_do_inicio_da_medida_e_recusado(presumido):
    medida = _medida(presumido, trimestre=3)
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.encerrar_medida(presumido["empresa"], medida.pk, 2026, 2, "x", presumido["usuario"])


def test_medida_revogada_nao_se_encerra(presumido):
    medida = _medida(presumido)
    servico.revogar_medida(presumido["empresa"], medida.pk, "cassada", presumido["usuario"])
    with pytest.raises(servico.PresumidoConflito):
        servico.encerrar_medida(presumido["empresa"], medida.pk, 2026, 2, "x", presumido["usuario"])


def test_encerramento_e_ato_gravado_o_banco_nao_muda_nem_apaga(presumido):
    medida = _medida(presumido)
    encerramento = servico.encerrar_medida(
        presumido["empresa"], medida.pk, 2026, 2, "x", presumido["usuario"]
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE fiscal_encerramentomedidajudiciallc224 SET motivo = 'outro' WHERE id = %s",
                [encerramento.pk],
            )
    with pytest.raises(IntegrityError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM fiscal_encerramentomedidajudiciallc224 WHERE id = %s",
                [encerramento.pk],
            )
    assert EncerramentoMedidaJudicialLC224.objects.filter(pk=encerramento.pk).exists()


def test_encerrar_pela_api_e_a_medida_volta_com_o_fim_efetivo(client, presumido):
    medida = _medida(presumido)
    client.force_login(presumido["usuario"])
    url = f"/fiscal/api/empresas/{presumido['empresa'].pk}/presumido/medidas/{medida.pk}/encerrar/"
    resposta = client.post(
        url,
        data=json.dumps({"ano": 2026, "trimestre": 2, "motivo": "decisão sintética"}),
        content_type="application/json",
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["fim_efetivo"] == {"ano": 2026, "trimestre": 2}
    assert corpo["encerramento"]["trimestre"] == 2


def test_encerrar_por_api_com_campo_fora_do_contrato_e_400(client, presumido):
    medida = _medida(presumido)
    client.force_login(presumido["usuario"])
    url = f"/fiscal/api/empresas/{presumido['empresa'].pk}/presumido/medidas/{medida.pk}/encerrar/"
    resposta = client.post(
        url,
        data=json.dumps({"ano": 2026, "trimestre": 2, "motivo": "x", "extra": 1}),
        content_type="application/json",
    )
    assert resposta.status_code == 400


def test_paralegal_nao_encerra_medida_pela_api(client, presumido, escritorio_a):
    medida = _medida(presumido)
    paralegal = _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-medida-dl084")
    client.force_login(paralegal)
    url = f"/fiscal/api/empresas/{presumido['empresa'].pk}/presumido/medidas/{medida.pk}/encerrar/"
    resposta = client.post(
        url,
        data=json.dumps({"ano": 2026, "trimestre": 2, "motivo": "x"}),
        content_type="application/json",
    )
    assert resposta.status_code == 403


def _usuario(escritorio, papel, username):
    from django.contrib.auth import get_user_model

    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


# ---------------------------------------------------------------------------
# Item 8: pendência de cadastro do mês (empresa do Presumido sem atividade padrão vigente)
# ---------------------------------------------------------------------------


def _empresa_lp(escritorio, cnpj, regime=RegimeTributario.LUCRO_PRESUMIDO, abertura=None):
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social=f"Cliente pendência {cnpj}",
        cnpj=cnpj,
        data_abertura_cnpj=abertura,
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=regime, vigencia_inicio=date(2026, 1, 1)
    )
    return empresa


def test_empresa_lp_sem_atividade_padrao_aparece_na_pendencia_do_mes(escritorio_a):
    empresa = _empresa_lp(escritorio_a, "77888999000155")
    pendencias = servico.pendencias_de_cadastro(empresa, 2026, 3)
    assert [p.codigo for p in pendencias] == [servico.CODIGO_SEM_ATIVIDADE_PADRAO]
    assert "03/2026" in pendencias[0].mensagem


def test_com_atividade_padrao_vigente_no_mes_nao_ha_pendencia(escritorio_a, usuario_gestor_a):
    empresa = _empresa_lp(escritorio_a, "77888999000156")
    servico.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": True},
        usuario_gestor_a,
    )
    assert servico.pendencias_de_cadastro(empresa, 2026, 3) == ()


def test_padrao_encerrado_antes_do_mes_gera_pendencia_so_nos_meses_seguintes(
    escritorio_a, usuario_gestor_a
):
    empresa = _empresa_lp(escritorio_a, "77888999000157")
    atividade = servico.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": True},
        usuario_gestor_a,
    )
    servico.encerrar_atividade(empresa, atividade.pk, "2026-02-28", usuario_gestor_a)
    assert servico.pendencias_de_cadastro(empresa, 2026, 2) == ()
    assert len(servico.pendencias_de_cadastro(empresa, 2026, 3)) == 1


def test_empresa_de_simples_nao_recebe_pendencia_de_presumido(escritorio_a):
    empresa = _empresa_lp(escritorio_a, "77888999000158", regime=RegimeTributario.SIMPLES_NACIONAL)
    assert servico.pendencias_de_cadastro(empresa, 2026, 3) == ()


def test_empresa_aberta_depois_do_mes_nao_tem_pendencia_no_mes(escritorio_a):
    empresa = _empresa_lp(escritorio_a, "77888999000159", abertura=date(2026, 6, 1))
    assert servico.pendencias_de_cadastro(empresa, 2026, 3) == ()
    assert len(servico.pendencias_de_cadastro(empresa, 2026, 6)) == 1


def test_mes_invalido_e_recusado(escritorio_a):
    empresa = _empresa_lp(escritorio_a, "77888999000160")
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.pendencias_de_cadastro(empresa, 2026, 13)


def test_pendencia_pela_api_do_mes(client, escritorio_a, usuario_gestor_a):
    empresa = _empresa_lp(escritorio_a, "77888999000161")
    client.force_login(usuario_gestor_a)
    resposta = client.get(f"/fiscal/api/empresas/{empresa.pk}/presumido/pendencias/?ano=2026&mes=3")
    assert resposta.status_code == 200
    assert [p["codigo"] for p in resposta.json()["pendencias"]] == ["sem_atividade_padrao"]
