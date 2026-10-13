"""DL-091 (frente B): acessibilidade das telas novas e alteradas de compra.

Confere marcação, não leitor de tela (que não foi usado, e está dito na direção de arte §7): rótulo
ligado ao campo pelo `for`, erro ligado ao campo por `aria-describedby`, trilha com `aria-current`,
e tabelas com legenda e cabeçalho de coluna.
"""

import html
import re

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import ItemNFe
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.test_dl091_entradas import _com_regime, _matriz, _nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Compradora acessibilidade DL091 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    return empresa


def _html(resposta):
    return html.unescape(resposta.content.decode("utf-8"))


def _tag(texto, padrao):
    achado = re.search(padrao, texto, flags=re.DOTALL)
    assert achado is not None, padrao
    return achado.group(0)


def test_campos_da_compra_tem_rotulo_ligado_e_o_erro_do_item_fica_associado(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, numero="6101", dh_emi="2026-03-10T10:00:00-03:00"
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    item = ItemNFe.objects.get(documento=documento, n_item=1)
    client.force_login(usuario_gestor_a)
    url = reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, esc.vinculo_id])

    resposta = client.post(
        url,
        {
            "acao": "item",
            "item_id": item.pk,
            "natureza": "entrada_comercializacao",
            "cfop_entrada": "1403",
        },
    )
    texto = _html(resposta)

    assert resposta.status_code == 400
    # Cada campo tem o seu rótulo, ligado pelo `for`.
    assert f'<label for="id_natureza_{item.pk}">Natureza do item 1</label>' in texto
    assert f'<label for="id_cfop_entrada_{item.pk}">CFOP de entrada do item 1</label>' in texto
    # O erro é texto, com role de alerta, e os campos o apontam por aria-describedby.
    assert f'id="erro_item_{item.pk}" role="alert"' in texto or (
        f'role="alert" id="erro_item_{item.pk}"' in texto
    )
    campo = _tag(texto, rf'<input type="text" id="id_cfop_entrada_{item.pk}"[^>]*>')
    assert f"erro_item_{item.pk}" in campo
    seletor = _tag(texto, rf'<select id="id_natureza_{item.pk}"[^>]*>')
    assert f"erro_item_{item.pk}" in seletor


def test_data_de_entrada_tem_rotulo_e_erro_associado_no_campo(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, numero="6102", dh_emi="2026-03-10T10:00:00-03:00"
    )
    client.force_login(usuario_gestor_a)
    url = reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk])

    resposta = client.post(url, {"acao": "criar", "data_entrada": "01/03/2026"})
    texto = _html(resposta)

    assert resposta.status_code == 400
    assert '<label for="id_data_entrada_criar">Data de entrada (dd/mm/aaaa)</label>' in texto
    campo = _tag(texto, r'<input type="text" id="id_data_entrada_criar"[^>]*>')
    assert "erro_data_entrada_criar" in campo
    assert 'id="erro_data_entrada_criar"' in texto


def test_trilha_da_compra_marca_a_tela_atual_com_aria_current_e_sem_link_para_ela(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, numero="6103", dh_emi="2026-03-10T10:00:00-03:00"
    )
    client.force_login(usuario_gestor_a)
    url = reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk])

    texto = _html(client.get(url))

    trilha = _tag(texto, r'<nav class="trilha" aria-label="Trilha de navegação">.*?</nav>')
    assert '<li aria-current="page">Escriturar compra nº 6103</li>' in trilha
    assert "Escriturar compra nº 6103</a>" not in trilha


def test_conferencia_de_entradas_tem_legenda_e_cabecalho_em_cada_tabela(
    client, usuario_gestor_a, empresa, escritorio_a
):
    _nota(
        escritorio_a, usuario_gestor_a, empresa, numero="6104", dh_emi="2026-03-10T10:00:00-03:00"
    )
    client.force_login(usuario_gestor_a)

    texto = _html(
        client.get(
            reverse("fiscal_web:nfe_conferencia_entradas", args=[empresa.pk]) + "?ano=2026&mes=3"
        )
    )

    tabelas = re.findall(r"<table class=\"tabela-dados\">.*?</table>", texto, flags=re.DOTALL)
    assert tabelas, "a conferência deveria ter tabelas com notas recebidas"
    for tabela in tabelas:
        assert "<caption>" in tabela
        assert '<th scope="col">' in tabela
    assert re.search(r'<li aria-current="page">Conferência de entradas</li>', texto)


def test_regra_de_compra_com_erro_no_crt_tem_o_campo_associado_ao_erro(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        reverse("fiscal_web:classificacao_regra_nova", args=[empresa.pk]),
        {
            "acao": "criar",
            "escopo": "empresa",
            "tipo": "entrada",
            "cfop": "5102",
            "natureza": "entrada_comercializacao",
            "vigencia_inicio": "01/01/2026",
            "crt_emitente": "9",
        },
    )
    texto = _html(resposta)

    assert resposta.status_code == 400
    seletor = _tag(texto, r'<select id="id_crt_emitente"[^>]*>')
    assert "erro_crt_emitente" in seletor
    assert '<label for="id_crt_emitente">CRT do emitente (opcional)</label>' in texto
    assert 'id="erro_crt_emitente" ' in texto or 'id="erro_crt_emitente">' in texto
