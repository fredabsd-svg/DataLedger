"""DL-091 (frente B): tela de escrituração da COMPRA e da devolução de compra.

Dados 100% sintéticos (CNPJ de `xml_nfe_dl080`, notas de `test_dl091_entradas`). Valores escritos à
mão nos testes: a memória e a prévia que a tela mostra são conferidas contra eles, não contra o que
o próprio código calcula.

Cenário-base: compra de SP (cUF 35) para uma empresa com matriz no Tocantins, regime normal
(lucro presumido), ICMS 18,00 CST 00. Pela regra da A1, a natureza E1 com CFOP 1102 dá "crédito
destacado elegível" de 18,00; E4 (uso e consumo) com ICMS destacado é "vedado até 2032", com aviso
de DIFAL (SP para TO).
"""

import html
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.test import Client
from django.urls import reverse

from apps.empresas.models import Empresa, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import (
    NATUREZAS_DE_ENTRADA,
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    MemoriaEntradaItemNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    TipoEscrituracaoNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl091_entradas import (
    _com_regime,
    _matriz,
    _nota,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe
EMISSAO_FEVEREIRO = "2026-02-27T10:00:00-03:00"  # 27/02/2026, em São Paulo
ANTES_DA_EMISSAO = "26/02/2026"
DEPOIS_DA_EMISSAO = "03/03/2026"


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Compradora telas DL091 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    return empresa


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-telas-dl091")


@pytest.fixture
def cliente_do_escritorio(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-telas-dl091")


def _texto(resposta):
    """HTML sem entidades: o template escapa a aspa simples, e o contador lê a aspa."""
    return html.unescape(resposta.content.decode("utf-8"))


def _url_da_nota(empresa, documento):
    return reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk])


def _compra(escritorio, usuario, empresa, **dados):
    """Nota de compra recebida pela recepção real (sintética), sem escrituração ainda."""
    dados.setdefault("numero", "3001")
    dados.setdefault("dh_emi", EMISSAO_FEVEREIRO)
    return _nota(escritorio, usuario, empresa, **dados)


def _valores_do_seletor(texto, item_id):
    """Valores (sem o vazio) das opções do seletor de natureza de UM item."""
    trecho = re.search(rf'<select id="id_natureza_{item_id}".*?</select>', texto, flags=re.DOTALL)
    assert trecho is not None, "o seletor de natureza do item não está na tela"
    return {valor for valor in re.findall(r'<option value="([a-z_]*)"', trecho.group(0)) if valor}


def _item(documento):
    return ItemNFe.objects.get(documento=documento, n_item=1)


def _confirmar_pela_tela(client, empresa, esc, item, natureza, cfop):
    return client.post(
        reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, esc.vinculo_id]),
        {"acao": "item", "item_id": item.pk, "natureza": natureza, "cfop_entrada": cfop},
    )


# ---------------------------------------------------------------------------
# Estados e tipo na tela (critérios 1 e 3)
# ---------------------------------------------------------------------------


def test_compra_sem_rascunho_mostra_o_tipo_e_o_botao_de_criar_com_data_sugerida(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_da_nota(empresa, documento)))

    assert "Entrada de compra (NF-e de terceiro, finNFe 1)" in texto
    assert 'name="data_entrada" value="27/02/2026"' in texto
    assert "Criar rascunho da compra" in texto
    assert 'name="acao" value="criar"' in texto


def test_criar_rascunho_pela_tela_grava_a_data_de_entrada_informada(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    client.force_login(usuario_gestor_a)
    url = _url_da_nota(empresa, documento)

    resposta = client.post(url, {"acao": "criar", "data_entrada": DEPOIS_DA_EMISSAO})

    assert resposta.status_code == 302
    esc = EscrituracaoNFe.objects.get(vinculo__documento=documento)
    assert esc.tipo == TipoEscrituracaoNFe.ENTRADA
    assert esc.data_entrada == date(2026, 3, 3)


def test_criar_rascunho_com_data_anterior_a_emissao_mostra_a_mensagem_do_servico_no_campo(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url_da_nota(empresa, documento), {"acao": "criar", "data_entrada": ANTES_DA_EMISSAO}
    )

    texto = _texto(resposta)
    assert resposta.status_code == 400
    assert "data de entrada anterior à data de emissão da nota" in texto
    assert 'id="erro_data_entrada_criar"' in texto
    assert 'value="26/02/2026"' in texto  # o que foi digitado continua no campo
    assert not EscrituracaoNFe.objects.filter(vinculo__documento=documento).exists()


def test_data_de_formato_errado_e_erro_do_campo_e_nada_e_gravado(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url_da_nota(empresa, documento), {"acao": "criar", "data_entrada": "31/02/2026"}
    )

    assert resposta.status_code == 400
    assert 'id="erro_data_entrada_criar"' in _texto(resposta)
    assert not EscrituracaoNFe.objects.filter(vinculo__documento=documento).exists()


def test_rascunho_muda_a_data_pela_tela_e_a_competencia_acompanha(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    url = _url_da_nota(empresa, documento)

    recusado = client.post(url, {"acao": "data_entrada", "data_entrada": ANTES_DA_EMISSAO})
    aceito = client.get(url)
    client.post(url, {"acao": "data_entrada", "data_entrada": DEPOIS_DA_EMISSAO})
    depois = _texto(client.get(url))

    assert recusado.status_code == 400
    assert "data de entrada anterior à data de emissão da nota" in _texto(recusado)
    assert "27/02/2026" in _texto(aceito)
    esc.refresh_from_db()
    assert esc.data_entrada == date(2026, 3, 3)
    assert "Competência" in depois and "03/2026" in depois


def test_compra_mostra_cfop_do_emitente_so_como_texto_e_seletor_so_de_entrada(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_da_nota(empresa, documento)))

    assert "CFOP do emitente" in texto
    assert "5102" in texto
    # O CFOP do emitente nunca é campo: a única caixa de CFOP é a do CFOP de entrada do item.
    assert 'name="cfop"' not in texto
    assert 'name="cfop_entrada" value="1102"' in texto
    assert _valores_do_seletor(texto, _item(documento).pk) == {
        valor.value for valor in NATUREZAS_DE_ENTRADA
    }
    assert esc.tipo == TipoEscrituracaoNFe.ENTRADA


# ---------------------------------------------------------------------------
# Seletor de natureza por tipo (critério: saída não oferece E1–E11; compra não oferece revenda;
# devolução de compra só `devolucao_compra`)
# ---------------------------------------------------------------------------


def test_seletor_da_saida_nao_oferece_nenhuma_natureza_de_entrada(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="7001",
        cfop="5102",
        tp_nf="1",
        fin_nfe="1",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    valores = _valores_do_seletor(
        _texto(client.get(_url_da_nota(empresa, documento))), _item(documento).pk
    )

    assert "revenda" in valores
    assert not valores & {valor.value for valor in NATUREZAS_DE_ENTRADA}


def test_seletor_da_compra_nao_oferece_revenda_de_saida(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    valores = _valores_do_seletor(
        _texto(client.get(_url_da_nota(empresa, documento))), _item(documento).pk
    )

    assert "revenda" not in valores
    assert "devolucao_compra" not in valores
    assert N.ENTRADA_COMERCIALIZACAO in valores


def test_devolucao_de_compra_mostra_o_tipo_e_oferece_so_devolucao_de_compra(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="5001",
        cfop="5202",
        tp_nf="1",
        fin_nfe="4",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_da_nota(empresa, documento)))

    assert "Devolução de compra ou retorno (saída própria, finNFe 4)" in texto
    assert _valores_do_seletor(texto, _item(documento).pk) == {"devolucao_compra"}


def test_devolucao_de_compra_explica_o_retorno_sem_sugestao_e_a_efetivacao_fica_travada(
    client, usuario_gestor_a, empresa, escritorio_a
):
    """Item de retorno (5.915, remessa para conserto) numa finNFe 4: sem sugestão, com o motivo do
    serviço, e a efetivação não fecha enquanto o item não tiver natureza."""
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="5002",
        cfop="5915",
        tp_nf="1",
        fin_nfe="4",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_da_nota(empresa, documento)))

    assert "sem sugestão" in texto
    assert "retorno em finNFe 4: fora do catálogo do corte 1" in texto
    assert "Falta a natureza de 1 item(ns)" in texto
    assert 'disabled aria-describedby="id_motivo_efetivar"' in texto
    resposta = client.post(_url_da_nota(empresa, documento), {"acao": "efetivar"})
    assert resposta.status_code == 409
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.RASCUNHO


# ---------------------------------------------------------------------------
# CFOP de entrada: sugestão, edição, recusa do serviço no campo (critérios 4)
# ---------------------------------------------------------------------------


def test_cfop_de_entrada_sugerido_aparece_no_campo_e_o_nao_confirmado_nao_grava(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_da_nota(empresa, documento)))

    assert 'name="cfop_entrada" value="1102"' in texto
    assert "Sugerido: 1102" in texto
    assert not NaturezaItemNFe.objects.filter(escrituracao=esc).exclude(natureza="").exists()


def test_cfop_de_entrada_recusado_pelo_servico_volta_ao_campo_com_a_mensagem(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    # E1 (grupo 102/104) com 1403 (grupo de ST): o serviço recusa pelo grupo.
    resposta = _confirmar_pela_tela(
        client, empresa, esc, _item(documento), N.ENTRADA_COMERCIALIZACAO, "1403"
    )

    texto = _texto(resposta)
    assert resposta.status_code == 400
    assert "não pertence ao grupo da natureza escolhida" in texto
    assert f'id="erro_item_{_item(documento).pk}"' in texto
    assert 'name="cfop_entrada" value="1403"' in texto
    assert not NaturezaItemNFe.objects.filter(escrituracao=esc).exclude(natureza="").exists()


def test_cfop_com_primeiro_digito_errado_e_recusado_com_o_nome_da_regra(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    # 2102 tem formato e grupo válidos para E1, mas o CFOP 5102 do emitente pede o dígito 1.
    resposta = _confirmar_pela_tela(
        client, empresa, esc, _item(documento), N.ENTRADA_COMERCIALIZACAO, "2102"
    )

    assert resposta.status_code == 400
    assert "O primeiro dígito do CFOP de entrada é 1 para o CFOP 5102" in _texto(resposta)
    assert 'name="cfop_entrada" value="2102"' in _texto(resposta)


def test_cfop_de_saida_digitado_como_entrada_e_recusado_pelo_formato(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = _confirmar_pela_tela(
        client, empresa, esc, _item(documento), N.ENTRADA_COMERCIALIZACAO, "5102"
    )

    assert resposta.status_code == 400
    assert "CFOP de entrada inválido: são quatro dígitos, com 1, 2 ou 3 na frente." in _texto(
        resposta
    )


def test_cfop_nunca_muda_e_post_com_campo_do_emitente_e_recusado(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    cfop_antes = _item(documento).cfop

    resposta = client.post(
        _url_da_nota(empresa, documento),
        {
            "acao": "item",
            "item_id": _item(documento).pk,
            "natureza": N.ENTRADA_COMERCIALIZACAO,
            "cfop_entrada": "1102",
            "cfop": "9999",  # campo que a tela não tem: o contrato recusa, e nada grava
        },
    )

    assert resposta.status_code == 400
    assert _item(documento).cfop == cfop_antes == "5102"
    assert not NaturezaItemNFe.objects.filter(natureza=N.ENTRADA_COMERCIALIZACAO).exists()


def test_confirmacao_de_natureza_e_cfop_grava_e_mostra_a_previa_antes_de_efetivar(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = _confirmar_pela_tela(
        client, empresa, esc, _item(documento), N.ENTRADA_COMERCIALIZACAO, "1102"
    )
    texto = _texto(client.get(_url_da_nota(empresa, documento)))

    assert resposta.status_code == 302
    assert "Natureza e CFOP de entrada do item confirmados." in texto
    # Valores escritos à mão: ICMS destacado 18,00 com CST 00 e regime normal = crédito destacado.
    achatado = " ".join(texto.split())
    assert (
        "Prévia da memória, antes de efetivar: Crédito destacado: elegível (LC 87, art. 20)."
        in (achatado)
    )
    assert 'Crédito admitido: <span class="valor-monetario">18,00</span>' in achatado


def test_aviso_de_difal_de_uso_aparece_na_previa_com_o_texto_nomeado(
    client, usuario_gestor_a, empresa, escritorio_a
):
    """E4 (uso e consumo) com ICMS destacado: vedado até 2032 (nunca crédito elegível) e, por ser de
    outro estado no regime normal, o aviso nomeado de DIFAL, sem valor."""
    documento = _compra(escritorio_a, usuario_gestor_a, empresa, numero="3002", cfop="5556")
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    _confirmar_pela_tela(client, empresa, esc, _item(documento), N.ENTRADA_USO_CONSUMO, "1556")
    texto = " ".join(_texto(client.get(_url_da_nota(empresa, documento))).split())

    assert "Crédito vedado até 31/12/2032 (LC 87, art. 33, I)" in texto
    assert "possível DIFAL (CF art. 155, § 2º, VII e VIII, não conferido)" in texto
    assert 'Crédito admitido: <span class="valor-monetario">nenhum</span>' in texto


# ---------------------------------------------------------------------------
# Efetivação, memória e estorno (critérios 1 e 5)
# ---------------------------------------------------------------------------


def test_efetivar_com_natureza_faltando_fica_desabilitado_com_o_motivo(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = " ".join(_texto(client.get(_url_da_nota(empresa, documento))).split())

    assert (
        "Falta a natureza de 1 item(ns). Confirme a natureza de cada item antes de efetivar."
        in (texto)
    )
    assert 'id="id_motivo_efetivar"' in texto


def test_efetivar_pela_tela_grava_a_memoria_e_a_receita_do_mes_nao_muda(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    _confirmar_pela_tela(client, empresa, esc, _item(documento), N.ENTRADA_COMERCIALIZACAO, "1102")

    resposta = client.post(_url_da_nota(empresa, documento), {"acao": "efetivar"})

    assert resposta.status_code == 302
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.EFETIVADA
    assert esc.receita_bruta == Decimal("0.00")
    assert MemoriaEntradaItemNFe.objects.filter(natureza_item__escrituracao=esc).count() == 1


def test_memoria_depois_da_efetivacao_mostra_os_valores_escritos_a_mao(
    client, usuario_gestor_a, empresa, escritorio_a
):
    """A nota traz ST retido (CST 60, vICMSSTRet 7,00), FCP 2,00, IPI 3,00, PIS 1,65 e Cofins 7,60,
    todos escritos à mão no XML. A tela mostra o que a memória gravou, com a marca em palavras."""
    icms = xml.icms(
        cst="60",
        filhos="<vBCSTRet>50.00</vBCSTRet><vICMSSTRet>7.00</vICMSSTRet><vFCP>2.00</vFCP>",
    )
    documento = _compra(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="3003",
        cfop="5405",
        icms=icms,
        ipi="<IPI><IPITrib><CST>50</CST><vIPI>3.00</vIPI></IPITrib></IPI>",
        pis="<PIS><PISAliq><CST>01</CST><vPIS>1.65</vPIS></PISAliq></PIS>",
        cofins="<COFINS><COFINSAliq><CST>01</CST><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS>",
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    _confirmar_pela_tela(client, empresa, esc, _item(documento), N.ENTRADA_ST, "1403")
    client.post(_url_da_nota(empresa, documento), {"acao": "efetivar"})

    texto = _texto(client.get(_url_da_nota(empresa, documento)))
    memoria = texto.split("Memória de crédito e de impostos, por item", 1)[1]
    linha = re.search(r'<th scope="row">1</th>(.*?)</tr>', memoria, flags=re.DOTALL)
    assert linha is not None
    celulas = re.findall(r"<td[^>]*>(.*?)</td>", linha.group(1), flags=re.DOTALL)
    textos = [" ".join(re.sub(r"<[^>]+>", " ", celula).split()) for celula in celulas]
    # Colunas: vICMS, marca de crédito, crédito elegível, ST retido, FCP, IPI, PIS e Cofins.
    # A CST 60 não traz vICMS (ausente é traço, não zero); a marca é de ST retido, sem crédito.
    assert textos[0] == "—"
    assert textos[1].startswith("ICMS-ST retido: sem crédito, compõe o custo")
    assert textos[2] == "nenhum"
    assert textos[3] == "7,00"
    assert textos[4] == "2,00"
    assert textos[5] == "3,00"
    assert textos[6] == "1,65"
    assert textos[7] == "7,60"


def test_estorno_da_compra_nao_diz_que_sai_da_receita(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    _confirmar_pela_tela(client, empresa, esc, _item(documento), N.ENTRADA_COMERCIALIZACAO, "1102")
    client.post(_url_da_nota(empresa, documento), {"acao": "efetivar"})

    texto = " ".join(
        _texto(client.get(reverse("fiscal_web:nfe_estornar", args=[empresa.pk, esc.pk]))).split()
    )

    assert "A compra não compõe a receita: o estorno não muda a receita do mês" in texto
    assert "Receita bruta da escrituração" not in texto
    assert "Ela sai da receita do mês" not in texto


def test_bloco_monofasico_e_segmento_sao_recusados_na_compra(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    url = _url_da_nota(empresa, documento)

    respostas = [
        client.post(url, {"acao": "bloco", "sinal": N.ENTRADA_COMERCIALIZACAO}),
        client.post(url, {"acao": "monofasico", "item_id": _item(documento).pk, "monofasico": "1"}),
        client.post(
            url,
            {"acao": "segmento_devolucao", "item_id": _item(documento).pk, "segmento": "x"},
        ),
    ]

    assert [r.status_code for r in respostas] == [400, 400, 400]
    assert not NaturezaItemNFe.objects.filter(natureza__in=NATUREZAS_DE_ENTRADA).exists()


# ---------------------------------------------------------------------------
# Permissões, isolamento, CSRF e GET que não altera estado (critérios 9 e do POST)
# ---------------------------------------------------------------------------


def test_paralegal_ve_a_compra_sem_controles_de_escrita_e_o_post_responde_403(
    client, paralegal, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(paralegal)
    url = _url_da_nota(empresa, documento)

    resposta = client.get(url)
    texto = _texto(resposta)

    assert resposta.status_code == 200
    assert "Seu papel consulta as NF-e" in texto
    assert 'name="cfop_entrada"' not in texto
    assert 'name="data_entrada"' not in texto
    assert client.post(url, {"acao": "efetivar"}).status_code == 403
    assert (
        client.post(
            url,
            {"acao": "item", "item_id": _item(documento).pk, "natureza": "entrada_comercializacao"},
        ).status_code
        == 403
    )
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.RASCUNHO


def test_cliente_do_escritorio_recebe_403_na_compra(
    client, cliente_do_escritorio, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    client.force_login(cliente_do_escritorio)

    assert client.get(_url_da_nota(empresa, documento)).status_code == 403


def test_compra_de_outro_escritorio_responde_404_mesmo_com_a_empresa_certa(
    client, usuario_gestor_a, escritorio_b, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    vinculo_a = vinculo(documento, empresa)
    empresa_de_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa de B telas DL091", cnpj="77888999000155"
    )
    usuario_de_b = usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-telas-dl091")
    client.force_login(usuario_de_b)

    # A empresa e a nota são do escritório A: quem pede como B recebe 404, e não a tela.
    assert client.get(_url_da_nota(empresa, documento)).status_code == 404
    url_com_empresa_de_b = reverse(
        "fiscal_web:nfe_escriturar", args=[empresa_de_b.pk, vinculo_a.pk]
    )
    assert client.get(url_com_empresa_de_b).status_code == 404


def test_post_sem_csrf_e_recusado_e_nada_muda(usuario_gestor_a, empresa, escritorio_a):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(usuario_gestor_a)

    resposta = cliente.post(
        _url_da_nota(empresa, documento),
        {
            "acao": "item",
            "item_id": _item(documento).pk,
            "natureza": "entrada_comercializacao",
            "cfop_entrada": "1102",
        },
    )

    assert resposta.status_code == 403
    assert not NaturezaItemNFe.objects.filter(natureza__in=NATUREZAS_DE_ENTRADA).exists()


def test_get_da_compra_nao_altera_estado(client, usuario_gestor_a, empresa, escritorio_a):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    antes = list(
        NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("natureza", "cfop_entrada")
    )

    client.get(_url_da_nota(empresa, documento))
    client.get(_url_da_nota(empresa, documento))

    depois = list(
        NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("natureza", "cfop_entrada")
    )
    assert antes == depois
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.RASCUNHO


def test_sucesso_da_efetivacao_aparece_como_mensagem_da_tela(
    client, usuario_gestor_a, empresa, escritorio_a
):
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    _confirmar_pela_tela(client, empresa, esc, _item(documento), N.ENTRADA_COMERCIALIZACAO, "1102")

    resposta = client.post(_url_da_nota(empresa, documento), {"acao": "efetivar"}, follow=True)

    assert "Escrituração de compra efetivada. A memória de cada item está gravada." in _texto(
        resposta
    )


def test_lista_de_consulta_da_compra_usa_a_mesma_querystring_de_empresa(
    client, usuario_gestor_a, empresa, escritorio_a
):
    """A tela de compra leva de volta à lista do mês, com a empresa na querystring."""
    documento = _compra(escritorio_a, usuario_gestor_a, empresa)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url_da_nota(empresa, documento)))

    query = urlencode({"empresa": empresa.pk, "ano": 2026, "mes": 2})
    assert f"{reverse('fiscal_web:nfe_a_escriturar')}?{query}" in texto
