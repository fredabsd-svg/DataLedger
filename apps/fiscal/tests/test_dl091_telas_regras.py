"""DL-091 (frente B): regras de classificação aceitam o tipo ENTRADA, CRT e UF do emitente e CFOP de
entrada, e a tela "Como a regra decide" publica os pesos atuais.

Dados sintéticos. Os pesos esperados são os números que o próprio texto da regra diz (64, 32, 16,
8, 4, UF 2, CRT 1), escritos à mão aqui; a constante do serviço é conferida por igualdade, não
copiada para a tela.
"""

import html
import re

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, RegimeTributario
from apps.fiscal import classificacao
from apps.fiscal.models import RegraClassificacaoNFe, TipoRegraClassificacaoNFe
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.test_dl091_entradas import _com_regime, _matriz
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Compradora regras DL091 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    return empresa


def _texto(resposta):
    return " ".join(html.unescape(resposta.content.decode("utf-8")).split())


def _url_nova(empresa):
    return reverse("fiscal_web:classificacao_regra_nova", args=[empresa.pk])


def _url_lista(empresa):
    return reverse("fiscal_web:classificacao_regras", args=[empresa.pk])


def _dados_de_compra(**trocas):
    """Formulário de regra de COMPRA: CFOP do emitente 5102, natureza E1, vigente desde 2026."""
    dados = {
        "acao": "criar",
        "escopo": "empresa",
        "tipo": TipoRegraClassificacaoNFe.ENTRADA,
        "cfop": "5102",
        "ncm": "",
        "ncm_modo": "",
        "cst_csosn": "",
        "id_dest": "",
        "natureza": "entrada_comercializacao",
        "vigencia_inicio": "01/01/2026",
        "vigencia_fim": "",
        "crt_emitente": "1",
        "uf_emitente": "TO",
        "cfop_entrada": "1102",
    }
    dados.update(trocas)
    return dados


def test_formulario_tem_os_tres_criterios_de_compra_com_rotulo_e_texto_de_ajuda(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_nova(empresa)))

    assert '<label for="id_crt_emitente">CRT do emitente (opcional)</label>' in texto
    assert '<label for="id_uf_emitente">UF do emitente (opcional)</label>' in texto
    assert '<label for="id_cfop_entrada">CFOP de entrada fixado (opcional)</label>' in texto
    assert "Só para compra (tipo Entrada)" in texto
    assert '<option value="4">4: MEI</option>' in texto
    assert '<option value="TO">TO</option>' in texto


def test_criar_regra_de_compra_grava_crt_uf_e_cfop_de_entrada_pelo_servico(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_nova(empresa), _dados_de_compra())

    assert resposta.status_code == 302
    regra = RegraClassificacaoNFe.objects.get(empresa=empresa)
    assert regra.tipo == TipoRegraClassificacaoNFe.ENTRADA
    assert (regra.crt_emitente, regra.uf_emitente, regra.cfop_entrada) == ("1", "TO", "1102")
    assert regra.cfop == "5102" and regra.natureza == "entrada_comercializacao"


def test_lista_mostra_os_criterios_de_compra_com_o_cfop_do_emitente_nomeado(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)
    client.post(_url_nova(empresa), _dados_de_compra())

    texto = _texto(client.get(_url_lista(empresa)))

    assert "Entrada de compra (NF-e de terceiro, finNFe 1)" in texto
    assert (
        "CFOP do emitente 5102; CRT do emitente 1; UF do emitente TO; CFOP de entrada fixado 1102"
        in (texto)
    )


def test_criterio_de_compra_em_regra_de_saida_e_recusado_no_campo_do_tipo(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url_nova(empresa),
        _dados_de_compra(tipo=TipoRegraClassificacaoNFe.SAIDA_PROPRIA, natureza="revenda"),
    )

    texto = _texto(resposta)
    assert resposta.status_code == 400
    assert 'id="erro_tipo"' in texto
    assert (
        "CRT do emitente, UF do emitente e CFOP de entrada só valem para a regra de entrada"
        in texto
    )
    assert not RegraClassificacaoNFe.objects.filter(empresa=empresa).exists()


def test_cfop_de_entrada_com_primeiro_digito_errado_e_erro_no_proprio_campo(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_nova(empresa), _dados_de_compra(cfop_entrada="2102"))

    texto = _texto(resposta)
    assert resposta.status_code == 400
    assert 'id="erro_cfop_entrada"' in texto
    assert "O primeiro dígito do CFOP de entrada é 1 para o CFOP 5102" in texto
    assert 'id="id_cfop_entrada"' in texto and 'value="2102"' in texto
    assert not RegraClassificacaoNFe.objects.filter(empresa=empresa).exists()


def test_crt_fora_da_lista_e_erro_no_campo_do_crt(client, usuario_gestor_a, empresa):
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_nova(empresa), _dados_de_compra(crt_emitente="9"))

    texto = _texto(resposta)
    assert resposta.status_code == 400
    assert 'id="erro_crt_emitente"' in texto
    assert "CRT do emitente deve ser 1 (Simples Nacional)" in texto


def test_uf_fora_das_27_siglas_e_erro_no_campo_da_uf(client, usuario_gestor_a, empresa):
    client.force_login(usuario_gestor_a)

    resposta = client.post(_url_nova(empresa), _dados_de_compra(uf_emitente="XX"))

    texto = _texto(resposta)
    assert resposta.status_code == 400
    assert 'id="erro_uf_emitente"' in texto
    assert "UF do emitente deve ser uma das 27 siglas" in texto


def test_como_a_regra_decide_publica_os_pesos_atuais_e_que_crt_e_uf_so_valem_para_compra(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_lista(empresa)))

    # Pesos escritos à mão (64/32/16/8/4, UF 2 e CRT 1) e conferidos com a constante do serviço.
    assert classificacao.PESO_CFOP == 64
    assert classificacao.PESO_UF_EMITENTE == 2 and classificacao.PESO_CRT_EMITENTE == 1
    assert (
        "Os pesos são: CFOP 64, NCM exato 32, NCM por prefixo 16, CST/CSOSN 8, idDest 4, "
        "UF do emitente 2 e CRT do emitente 1."
    ) in texto
    assert (
        "CRT do emitente e UF do emitente só valem para a regra de compra (tipo Entrada)"
    ) in texto


def test_regras_do_produto_descrevem_a_entrada_e_nao_dizem_mais_sem_sugestao_para_devolucao(
    client, usuario_gestor_a, empresa
):
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(reverse("fiscal_web:classificacao_produto")))

    for natureza in ("E1", "E2", "E3", "E6", "E7", "E8", "E9"):
        assert f"{natureza} ·" in texto, natureza
    assert "o produto não sugere E4, E5, E10 nem E11" in texto
    assert "5→1, 6→2, 7→3" in texto
    assert "NCM exigido como na venda (HI-139)" in texto
    assert "devolução de compra: natureza só dela, fora da receita" in texto
    assert "fora do catálogo de venda" not in texto


def test_formulario_de_compra_so_leitura_para_quem_so_consulta(client, paralegal_dl091, empresa):
    client.force_login(paralegal_dl091)

    html_bruto = client.get(_url_nova(empresa)).content.decode("utf-8")

    for campo in ("crt_emitente", "uf_emitente", "cfop_entrada"):
        tag = re.search(rf'<(select|input) [^>]*name="{campo}"[^>]*>', html_bruto)
        assert tag is not None, campo
        assert "disabled" in tag.group(0), campo


@pytest.fixture
def paralegal_dl091(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-regras-dl091")
