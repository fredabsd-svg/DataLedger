"""DL-091 (frente B): compras na lista "NF-e a escriturar", no lote do mês e os links para a
conferência de entradas.

Dados 100% sintéticos. A competência da compra escriturada é a da DATA DE ENTRADA (HI-158); a
compra ainda não escriturada fica no mês da emissão. Os textos e as datas esperados foram escritos
à mão a partir do cenário, e não copiados do que o código devolve.
"""

import html
from datetime import date
from urllib.parse import urlencode

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, RegimeTributario
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as servico_lote
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl091_entradas import _com_regime, _confirmar, _matriz, _nota, _rascunho
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

FEVEREIRO = "2026-02-27T10:00:00-03:00"  # emissão em 27/02/2026
MARCO = "2026-03-10T10:00:00-03:00"


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Compradora lista DL091 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    return empresa


def _texto(resposta):
    return " ".join(html.unescape(resposta.content.decode("utf-8")).split())


def _lista(empresa, ano, mes):
    return (
        reverse("fiscal_web:nfe_a_escriturar")
        + "?"
        + urlencode({"empresa": empresa.pk, "ano": ano, "mes": mes})
    )


def test_compra_com_data_de_entrada_em_marco_conta_em_marco_com_tipo(
    client, usuario_gestor_a, empresa, escritorio_a
):
    """Emitida em fevereiro, escriturada com data de entrada em março: conta em março (HI-158)."""
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="4101", dh_emi=FEVEREIRO)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    entradas.definir_data_de_entrada(esc, date(2026, 3, 2), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    em_marco = _texto(client.get(_lista(empresa, 2026, 3)))
    em_fevereiro = _texto(client.get(_lista(empresa, 2026, 2)))

    assert "Entrada de compra (NF-e de terceiro, finNFe 1)" in em_marco
    assert "03/2026 (data de entrada)" in em_marco
    assert "Entrada de compra" not in em_fevereiro


def test_compra_ainda_nao_escriturada_fica_no_mes_da_emissao_com_a_competencia_de_emissao(
    client, usuario_gestor_a, empresa, escritorio_a
):
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="4102", dh_emi=FEVEREIRO)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_lista(empresa, 2026, 2)))

    assert "Entrada de compra (NF-e de terceiro, finNFe 1)" in texto
    assert "02/2026 (emissão)" in texto
    assert "Criar rascunho" in texto


def test_lista_leva_a_conferencia_de_entradas_do_mes_so_quando_ha_empresa(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    com_empresa = client.get(_lista(empresa, 2026, 3)).content.decode("utf-8")
    sem_empresa = _texto(client.get(reverse("fiscal_web:nfe_a_escriturar")))

    link = reverse("fiscal_web:nfe_conferencia_entradas", args=[empresa.pk])
    # A querystring sai escapada no HTML (`&amp;`): o link é conferido como ele aparece na página.
    assert f'href="{link}?ano=2026&amp;mes=3"' in com_empresa
    assert "Conferência de entradas" not in sem_empresa


def test_lista_mostra_as_colunas_de_tipo_e_competencia(
    client, usuario_gestor_a, empresa, escritorio_a
):
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="4103", dh_emi=FEVEREIRO)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_lista(empresa, 2026, 2)))

    assert '<th scope="col">Tipo</th>' in texto
    assert '<th scope="col">Competência</th>' in texto
    assert "<caption>NF-e da empresa no mês, com o tipo, a competência e a situação" in texto


def test_lote_do_mes_mostra_o_cfop_de_entrada_e_que_a_compra_fica_fora_da_receita(
    client, usuario_gestor_a, empresa, escritorio_a
):
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="4104", cfop="5102", dh_emi=MARCO)
    client.force_login(usuario_gestor_a)

    resposta = client.get(reverse("fiscal_web:nfe_lote", args=[empresa.pk]) + "?ano=2026&mes=3")
    texto = _texto(resposta)

    assert resposta.status_code == 200
    assert "CFOP de entrada 1102" in texto
    assert "fora da receita (compra)" in texto
    assert "Tipo" in texto and "Entrada de compra" in texto
    # O seletor do grupo é de compra: E1 a E11, e a revenda de saída não aparece.
    assert "E1 · Compra para comercialização" in texto
    assert "Venda de mercadoria adquirida de terceiros (revenda)" not in texto
    link = reverse("fiscal_web:nfe_conferencia_entradas", args=[empresa.pk])
    assert f"{link}?ano=2026&amp;mes=3" in resposta.content.decode("utf-8")


def test_motivo_de_cfop_de_entrada_a_escolher_tem_rotulo_na_tela():
    """Grupo de compra sem CFOP de entrada padrão sai do lote com o motivo nomeado: o rótulo existe
    e não cai no código cru."""
    from apps.fiscal import views_web

    assert (
        views_web._ROTULO_MOTIVO_FORA_DO_LOTE[servico_lote.CODIGO_CFOP_DE_ENTRADA_A_ESCOLHER]
        == "Compra: CFOP de entrada a escolher"
    )


def test_lote_de_outro_escritorio_responde_404(client, usuario_gestor_a, escritorio_b, empresa):
    usuario_de_b = usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-lote-dl091")
    client.force_login(usuario_de_b)

    assert (
        client.get(
            reverse("fiscal_web:nfe_lote", args=[empresa.pk]) + "?ano=2026&mes=3"
        ).status_code
        == 404
    )


def test_compra_efetivada_na_lista_mostra_a_competencia_da_data_de_entrada(
    client, usuario_gestor_a, empresa, escritorio_a
):
    """Emitida e efetivada em fevereiro com a data de entrada padrão (a emissão): a competência é
    fevereiro, e o rótulo diz que veio da data de entrada, não da emissão."""
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa, numero="4105", dh_emi=FEVEREIRO)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_lista(empresa, 2026, 2)))

    assert "Efetivada" in texto
    assert "02/2026 (data de entrada)" in texto


def test_lote_com_grupo_sem_cfop_de_entrada_sai_do_lote_com_o_motivo(
    client, usuario_gestor_a, empresa, escritorio_a
):
    """Uma regra de ENTRADA que sugere E4 (uso e consumo) sem fixar o CFOP de entrada: a E4 tem
    mais de um grupo de CFOP, e a compra não tem padrão. O grupo sai do lote, com o motivo nomeado,
    com o motivo do serviço na tela."""
    from apps.fiscal import classificacao
    from apps.fiscal.models import TipoRegraClassificacaoNFe

    dados = classificacao.validar_dados_da_regra(
        classificacao.DadosDaRegra(
            tipo=TipoRegraClassificacaoNFe.ENTRADA,
            cfop="5556",
            natureza=N.ENTRADA_USO_CONSUMO,
            vigencia_inicio=date(2026, 1, 1),
        )
    )
    classificacao.criar_regra(
        escritorio=escritorio_a, empresa=empresa, dados=dados, usuario=usuario_gestor_a
    )
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="4106", cfop="5556", dh_emi=MARCO)
    client.force_login(usuario_gestor_a)

    texto = _texto(
        client.get(reverse("fiscal_web:nfe_lote", args=[empresa.pk]) + "?ano=2026&mes=3")
    )

    # O rótulo da lista "fora do lote" e o motivo que o serviço escreveu para a nota.
    assert "Compra: CFOP de entrada a escolher" in texto
    assert "sem CFOP de entrada padrão para a natureza" in texto
    assert "escriture esta nota individualmente e confirme o CFOP de entrada" in texto
