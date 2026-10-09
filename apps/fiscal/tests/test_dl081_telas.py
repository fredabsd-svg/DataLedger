"""DL-081, frente B: telas da escrituração das NF-e de saída e da devolução de venda.

Fluxo pela tela, com o exemplo do Simples da consulta de 09/10/2026 (item 3): nota de vNF 2.970,00,
receita de 2.880,00, segregada em 1.480,00 (normal), 800,00 (ST) e 600,00 (monofásico). Todos os
valores esperados estão escritos à mão aqui, não copiados do código. Os XML são sintéticos
(`xml_nfe_dl081`). A tela não recalcula: a sugestão, a conferência e a efetivação são do serviço da
frente A, e aqui se confere só o que chega à tela, em pt-BR.

As permissões, o isolamento e a entrada estranha estão em `test_dl081_telas_permissoes.py` e
`test_dl081_telas_entrada.py`.
"""

import html as html_lib
import re
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    NaturezaItemNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A, proc_evento_xml
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 3  # a data de emissão padrão dos XML sintéticos é 15/03/2026


# ---------------------------------------------------------------------------
# XML do exemplo do Simples (consulta, item 3), com os valores escritos à mão
# ---------------------------------------------------------------------------


def simples(*, vnf="2970.00", numero="1"):
    """Revenda 1.000 - 50 + 30 = 980 (CSOSN 102); ST substituído 800 (CSOSN 500); monofásico 600
    (PIS 04); substituto 500 (CSOSN 201, ST 90). vProd 2.900, vDesc 50, vFrete 30, vST 90."""
    dets = [
        xml.det(
            1,
            cfop="5102",
            vprod="1000.00",
            vdesc="50.00",
            vfrete="30.00",
            icms_xml=xml.icms(csosn="102"),
        ),
        xml.det(2, cfop="5405", vprod="800.00", icms_xml=xml.icms(csosn="500")),
        xml.det(
            3,
            cfop="5102",
            vprod="600.00",
            icms_xml=xml.icms(csosn="102"),
            pis_xml="<PIS><PISNT><CST>04</CST></PISNT></PIS>",
        ),
        xml.det(
            4,
            cfop="5401",
            vprod="500.00",
            icms_xml=xml.icms(
                csosn="201",
                filhos="<modBCST>4</modBCST><vBCST>500.00</vBCST>"
                "<pICMSST>18.00</pICMSST><vICMSST>90.00</vICMSST>",
            ),
        ),
    ]
    return xml.nfe(
        dets=dets,
        vnf=vnf,
        totais={"vProd": "2900.00", "vDesc": "50.00", "vFrete": "30.00", "vST": "90.00"},
        tp_nf="1",
        fin_nfe="1",
        id_dest="1",
        crt="1",
        numero=numero,
    )


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-telas-dl081")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Telas DL081 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra Telas DL081 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


# ---------------------------------------------------------------------------
# Auxiliares: URL, HTML e os passos da escrituração
# ---------------------------------------------------------------------------


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _texto(resposta):
    """HTML já sem entidades, para comparar com o texto que o contador lê."""
    return html_lib.unescape(resposta.content.decode("utf-8"))


def _url_lista(empresa, ano=ANO, mes=MES):
    return (
        reverse("fiscal_web:nfe_a_escriturar")
        + "?"
        + urlencode({"empresa": empresa.pk, "ano": ano, "mes": mes})
    )


def _url_escriturar(empresa, vinculo_):
    return reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo_.pk])


def _url_estornar(empresa, escrituracao):
    return reverse("fiscal_web:nfe_estornar", args=[empresa.pk, escrituracao.pk])


def _url_reclassificar():
    return reverse("fiscal_web:nfe_reclassificar")


def _url_conferencia(empresa, ano=ANO, mes=MES):
    return (
        reverse("fiscal_web:nfe_conferencia")
        + "?"
        + urlencode({"empresa": empresa.pk, "ano": ano, "mes": mes})
    )


def _nota(escritorio, usuario, empresa, *, vnf="2970.00", numero="1"):
    documento = receber(escritorio, usuario, simples(vnf=vnf, numero=numero))
    return vinculo(documento, empresa)


def _item(vinculo_, n_item):
    return ItemNFe.objects.get(documento=vinculo_.documento, n_item=n_item)


def _escriturar_com_o_exemplo(client, empresa, vinculo_):
    """Os passos que o contador faz na tela: rascunho, confirmação em bloco por sugestão, e a
    monofásica escolhida à mão (o XML não traz o sinal de monofásico)."""
    url = _url_escriturar(empresa, vinculo_)
    client.post(url, {"acao": "criar"})
    client.post(url, {"acao": "bloco", "sinal": "revenda"})
    client.post(url, {"acao": "item", "item_id": _item(vinculo_, 3).pk, "natureza": "monofasico"})
    client.post(url, {"acao": "bloco", "sinal": "revenda_st_substituido"})
    client.post(url, {"acao": "bloco", "sinal": "substituto_st"})
    return EscrituracaoNFe.objects.get(vinculo=vinculo_, estado=EstadoEscrituracao.RASCUNHO)


def _botao_efetivar(html):
    """A tag do botão de efetivar, para ler se está habilitado."""
    achado = re.search(r"<button[^>]*>Efetivar escrituração</button>", html)
    assert achado, "botão de efetivar ausente"
    return achado.group(0)


@pytest.fixture
def cenario(client, gestor, emitente, escritorio_a):
    """Gestor logado, empresa emitente e a nota do exemplo do Simples, ainda sem escrituração."""
    _logar(client, gestor)
    return {"empresa": emitente, "vinculo": _nota(escritorio_a, gestor, emitente)}


# ---------------------------------------------------------------------------
# Tela 1: NF-e a escriturar no mês
# ---------------------------------------------------------------------------


def test_lista_mostra_a_nota_sem_escrituracao_com_valor_ptbr_e_botao_de_criar(client, cenario):
    resposta = client.get(_url_lista(cenario["empresa"]))

    texto = _texto(resposta)
    assert resposta.status_code == 200
    assert "2.970,00" in texto
    assert "Sem escrituração" in texto
    assert "Criar rascunho" in texto
    assert "2970.00" not in texto


def test_lista_sem_empresa_pede_a_escolha_e_nao_lista_nada(client, cenario):
    resposta = client.get(reverse("fiscal_web:nfe_a_escriturar"))

    assert resposta.status_code == 200
    assert "Escolha uma empresa para ver as NF-e a escriturar." in _texto(resposta)
    assert "Criar rascunho" not in _texto(resposta)


def test_nota_ilegivel_mostra_o_campo_que_impediu_a_leitura_depois_da_primeira_tentativa(
    client, gestor, emitente, escritorio_a
):
    # vDesc igual a zero: campo opcional com zero é ilegível (decisão da frente A). A consulta não
    # grava a leitura: ela acontece na tentativa de criar o rascunho. Antes disso, a lista diz
    # "Ainda não lida", e depois mostra o campo que impediu a leitura.
    ilegivel = xml.nfe(
        dets=[
            xml.det(1, cfop="5102", vprod="100.00", vdesc="0.00", icms_xml=xml.icms(csosn="102"))
        ],
        vnf="100.00",
        totais={"vProd": "100.00"},
        numero="9",
    )
    vinculo_ = vinculo(receber(escritorio_a, gestor, ilegivel), emitente)
    _logar(client, gestor)
    assert "Ainda não lida" in _texto(client.get(_url_lista(emitente)))

    tentativa = client.post(_url_escriturar(emitente, vinculo_), {"acao": "criar"})

    assert tentativa.status_code == 409
    assert "Itens ilegíveis, nota bloqueada" in _texto(tentativa)
    assert "vDesc" in _texto(tentativa)
    lista = _texto(client.get(_url_lista(emitente)))
    assert "Ilegível" in lista
    assert "vDesc" in lista
    assert "Criar rascunho" not in lista


def test_lista_de_outro_mes_nao_mostra_a_nota(client, cenario):
    texto = _texto(client.get(_url_lista(cenario["empresa"], ano=2025, mes=1)))

    assert "2.970,00" not in texto
    assert "Nenhuma NF-e de saída ou devolução desta empresa em 01/2025." in texto


def test_criar_rascunho_pela_lista_leva_a_tela_de_escriturar_com_os_itens(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]

    resposta = client.post(_url_escriturar(empresa, vinculo_), {"acao": "criar"}, follow=True)

    texto = _texto(resposta)
    rascunho = EscrituracaoNFe.objects.get(vinculo=vinculo_)
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    assert "Rascunho criado" in texto
    assert "Confirmar natureza" in texto
    assert texto.count("Confirmar natureza") == 4
    assert "Sugestão: Venda de mercadoria adquirida de terceiros (revenda)" in texto


# ---------------------------------------------------------------------------
# Tela 2: escriturar uma nota (exemplo do Simples, valores à mão)
# ---------------------------------------------------------------------------


def test_efetivar_fica_desabilitado_com_o_motivo_enquanto_houver_item_sem_natureza(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "criar"})

    texto = _texto(client.get(_url_escriturar(empresa, vinculo_)))

    assert "disabled" in _botao_efetivar(texto)
    assert "Falta a natureza de 4 item(ns)." in texto


def test_confirmacao_em_bloco_so_atinge_os_itens_do_mesmo_sinal(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    url = _url_escriturar(empresa, vinculo_)
    client.post(url, {"acao": "criar"})

    client.post(url, {"acao": "bloco", "sinal": "revenda"})

    naturezas = {
        r.item.n_item: r.natureza
        for r in NaturezaItemNFe.objects.select_related("item").filter(
            escrituracao__vinculo=vinculo_
        )
    }
    assert naturezas == {1: "revenda", 2: "", 3: "revenda", 4: ""}


def test_troca_de_natureza_por_item_grava_so_aquele_item(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    url = _url_escriturar(empresa, vinculo_)
    client.post(url, {"acao": "criar"})

    resposta = client.post(
        url, {"acao": "item", "item_id": _item(vinculo_, 3).pk, "natureza": "monofasico"}
    )

    assert resposta.status_code == 302
    gravadas = dict(
        NaturezaItemNFe.objects.filter(escrituracao__vinculo=vinculo_).values_list(
            "item__n_item", "natureza"
        )
    )
    assert gravadas == {1: "", 2: "", 3: "monofasico", 4: ""}


def test_exemplo_do_simples_pela_tela_efetiva_com_receita_2880_e_segregacao(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    escrituracao = _escriturar_com_o_exemplo(client, empresa, vinculo_)

    resposta = client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"}, follow=True)

    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA
    assert escrituracao.receita_bruta == Decimal("2880.00")
    assert escrituracao.valor_nf == Decimal("2970.00")
    texto = _texto(resposta)
    assert "Escrituração efetivada" in texto
    assert "2.880,00" in texto
    assert "2.970,00" in texto
    # Segregação escrita à mão: normal 980 + 500 (substituto), ST 800, monofásico 600.
    assert "1.480,00" in texto
    assert "800,00" in texto
    assert "600,00" in texto


def test_efetivada_aparece_na_lista_como_efetivada_e_com_o_estorno_na_tela(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    _escriturar_com_o_exemplo(client, empresa, vinculo_)
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"})

    lista = _texto(client.get(_url_lista(empresa)))
    detalhe = _texto(client.get(_url_escriturar(empresa, vinculo_)))

    assert "Efetivada" in lista
    assert "Criar rascunho" not in lista
    assert "Estornar escrituração" in detalhe


def test_divergencia_com_vnf_desabilita_efetivar_e_mostra_valores_em_ptbr(
    client, gestor, emitente, escritorio_a
):
    _logar(client, gestor)
    vinculo_ = _nota(escritorio_a, gestor, emitente, vnf="2971.00", numero="2")
    _escriturar_com_o_exemplo(client, emitente, vinculo_)

    texto = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    assert "disabled" in _botao_efetivar(texto)
    assert "Não confere" in texto
    assert "2.880,00" in texto  # receita dos itens
    assert "2.971,00" in texto  # vNF
    # Nenhum valor sai com ponto decimal, como no texto do serviço.
    assert "2971.00" not in texto
    assert "2880.00" not in texto


def test_post_forcado_de_efetivar_com_divergencia_e_recusado_sem_gravar(
    client, gestor, emitente, escritorio_a
):
    _logar(client, gestor)
    vinculo_ = _nota(escritorio_a, gestor, emitente, vnf="2971.00", numero="2")
    escrituracao = _escriturar_com_o_exemplo(client, emitente, vinculo_)

    resposta = client.post(_url_escriturar(emitente, vinculo_), {"acao": "efetivar"})

    escrituracao.refresh_from_db()
    assert resposta.status_code == 409
    assert escrituracao.estado == EstadoEscrituracao.RASCUNHO
    assert "não confere com o valor da nota" in _texto(resposta)


def test_post_forcado_de_efetivar_sem_natureza_e_recusado_sem_gravar(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "criar"})

    resposta = client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"})

    assert resposta.status_code == 409
    assert "Falta a natureza de 4 item(ns)." in _texto(resposta)
    assert not EscrituracaoNFe.objects.filter(
        vinculo=vinculo_, estado=EstadoEscrituracao.EFETIVADA
    ).exists()


def test_escriturar_mostra_o_motivo_da_sugestao_e_cfop_com_descricao_oficial(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "criar"})

    texto = _texto(client.get(_url_escriturar(empresa, vinculo_)))

    assert "sugerida pelo sinal de CST/CSOSN" in texto or "sugerida pelo sinal de CFOP" in texto
    assert "CSOSN 500" in texto
    assert "CSOSN 201" in texto
    assert "CFOP fora da tabela oficial" not in texto


def test_nota_fora_da_escrituracao_explica_o_motivo_e_nao_cria_rascunho(client, gestor, emitente):
    # Nota de entrada (compra): a empresa é destinatária e não emitente.
    _logar(client, gestor)
    compra = xml.nfe(
        dets=[xml.det(1, cfop="1102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="100.00",
        totais={"vProd": "100.00"},
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        emitente_nome="Fornecedor Sintetico Ltda",
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
        destinatario_nome="Emitente Telas DL081 Ltda",
        numero="5",
    )
    documento = receber(emitente.escritorio, gestor, compra)
    compra_vinculo = vinculo(documento, emitente)

    resposta = client.get(_url_escriturar(emitente, compra_vinculo))

    assert resposta.status_code == 200
    assert "não entra na escrituração desta empresa" in _texto(resposta)
    assert not EscrituracaoNFe.objects.filter(vinculo=compra_vinculo).exists()


# ---------------------------------------------------------------------------
# Tela 3: estorno com motivo
# ---------------------------------------------------------------------------


def test_estorno_com_motivo_volta_a_nota_para_a_escriturar(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    escrituracao = _escriturar_com_o_exemplo(client, empresa, vinculo_)
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"})

    tela = _texto(client.get(_url_estornar(empresa, escrituracao)))
    resposta = client.post(
        _url_estornar(empresa, escrituracao), {"motivo": "Lançamento em duplicidade"}
    )

    escrituracao.refresh_from_db()
    assert "O que vai acontecer" in tela
    assert "2.880,00" in tela
    assert resposta.status_code == 302
    assert escrituracao.estado == EstadoEscrituracao.ESTORNADA
    assert escrituracao.motivo_estorno == "Lançamento em duplicidade"
    lista = _texto(client.get(_url_lista(empresa)))
    assert "Estornada, a escriturar de novo" in lista


def test_estorno_sem_motivo_e_recusado_e_nada_muda(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    escrituracao = _escriturar_com_o_exemplo(client, empresa, vinculo_)
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"})

    resposta = client.post(_url_estornar(empresa, escrituracao), {"motivo": "   "})

    escrituracao.refresh_from_db()
    assert resposta.status_code == 400
    assert "Informe o motivo do estorno." in _texto(resposta)
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA


def test_estorno_de_rascunho_e_recusado(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "criar"})
    rascunho = EscrituracaoNFe.objects.get(vinculo=vinculo_)

    resposta = client.post(_url_estornar(empresa, rascunho), {"motivo": "Teste"})

    rascunho.refresh_from_db()
    assert resposta.status_code == 409
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO


# ---------------------------------------------------------------------------
# Tela 4: reclassificação em massa (prévia só conta; confirmação grava só rascunho)
# ---------------------------------------------------------------------------


def _naturezas_da_nota(vinculo_):
    return dict(
        NaturezaItemNFe.objects.filter(escrituracao__vinculo=vinculo_).values_list(
            "item__n_item", "natureza"
        )
    )


def _formulario_de_reclassificacao(empresa, **extra):
    dados = {
        "empresa": empresa.pk,
        "natureza": "producao_propria",
        "inicio": "",
        "fim": "",
        "cfop": "5102",
        "cst_csosn": "",
        "ncm": "",
    }
    dados.update(extra)
    return dados


def _assinatura_da_previa(client, emitente):
    """Assinatura do conjunto que a PRÉVIA põe no formulário (A10, rodada 1). A confirmação sem ela,
    ou com outra, é recusada (409): o formulário real sempre a envia."""
    previa = client.post(
        _url_reclassificar(), _formulario_de_reclassificacao(emitente, acao="previa")
    )
    achado = re.search(
        r'name="previstas_assinatura" value="([0-9a-f]{64})"', previa.content.decode()
    )
    assert achado is not None, "a prévia precisa devolver a assinatura no formulário"
    return achado.group(1)


def test_previa_conta_sem_alterar_e_confirmacao_grava_so_o_rascunho(
    client, gestor, emitente, escritorio_a
):
    _logar(client, gestor)
    rascunho_vinculo = _nota(escritorio_a, gestor, emitente, numero="1")
    _escriturar_rascunho_revenda(client, emitente, rascunho_vinculo)
    efetivada_vinculo = _nota(escritorio_a, gestor, emitente, numero="2")
    _escriturar_com_o_exemplo(client, emitente, efetivada_vinculo)
    client.post(_url_escriturar(emitente, efetivada_vinculo), {"acao": "efetivar"})
    antes_efetivada = _naturezas_da_nota(efetivada_vinculo)

    previa = client.post(
        _url_reclassificar(), _formulario_de_reclassificacao(emitente, acao="previa")
    )

    # Prévia: a rascunho tem os itens 1 e 3 com CFOP 5102; a efetivada não entra.
    texto = _texto(previa)
    assert "Prévia: nada foi alterado ainda" in texto
    assert "<strong>2</strong> item(ns), em <strong>1</strong> nota(s)" in texto
    assert _naturezas_da_nota(rascunho_vinculo)[1] == "revenda"
    assert _naturezas_da_nota(efetivada_vinculo) == antes_efetivada

    confirmacao = client.post(
        _url_reclassificar(),
        _formulario_de_reclassificacao(
            emitente,
            acao="confirmar",
            previstas_notas="1",
            previstos_itens="2",
            previstas_assinatura=_assinatura_da_previa(client, emitente),
        ),
    )

    assert confirmacao.status_code == 302
    trocadas = _naturezas_da_nota(rascunho_vinculo)
    assert trocadas[1] == "producao_propria"
    assert trocadas[3] == "producao_propria"
    assert trocadas[2] == ""
    assert _naturezas_da_nota(efetivada_vinculo) == antes_efetivada


def test_confirmacao_com_previa_que_nao_bate_nao_grava_nada(client, gestor, emitente, escritorio_a):
    _logar(client, gestor)
    rascunho_vinculo = _nota(escritorio_a, gestor, emitente, numero="1")
    _escriturar_rascunho_revenda(client, emitente, rascunho_vinculo)
    antes = _naturezas_da_nota(rascunho_vinculo)

    resposta = client.post(
        _url_reclassificar(),
        _formulario_de_reclassificacao(
            emitente, acao="confirmar", previstas_notas="1", previstos_itens="5"
        ),
    )

    assert resposta.status_code == 409
    assert "nada foi alterado" in _texto(resposta)
    assert _naturezas_da_nota(rascunho_vinculo) == antes


def test_reclassificacao_nao_toca_a_nota_de_outra_empresa_do_escritorio(
    client, gestor, emitente, outra, escritorio_a
):
    _logar(client, gestor)
    minha = _nota(escritorio_a, gestor, emitente, numero="1")
    _escriturar_rascunho_revenda(client, emitente, minha)
    alheia = _nota_de_outra_empresa(escritorio_a, gestor, outra, numero="7")
    _escriturar_rascunho_revenda(client, outra, alheia)

    client.post(
        _url_reclassificar(),
        _formulario_de_reclassificacao(
            emitente,
            acao="confirmar",
            previstas_notas="1",
            previstos_itens="2",
            previstas_assinatura=_assinatura_da_previa(client, emitente),
        ),
    )

    assert _naturezas_da_nota(minha)[1] == "producao_propria"
    assert _naturezas_da_nota(alheia) == {1: "revenda"}


def test_reclassificacao_com_natureza_que_nao_cabe_recusa_e_nao_altera(
    client, gestor, emitente, escritorio_a
):
    _logar(client, gestor)
    vinculo_ = _nota(escritorio_a, gestor, emitente, numero="1")
    _escriturar_rascunho_revenda(client, emitente, vinculo_)
    antes = _naturezas_da_nota(vinculo_)

    resposta = client.post(
        _url_reclassificar(),
        _formulario_de_reclassificacao(emitente, acao="previa", natureza="devolucao_venda"),
    )

    assert resposta.status_code == 400
    assert "Nada foi alterado." in _texto(resposta)
    assert _naturezas_da_nota(vinculo_) == antes


def _escriturar_rascunho_revenda(client, empresa, vinculo_):
    """Rascunho com as naturezas confirmadas pela sugestão 'revenda' (itens 1 e 3)."""
    url = _url_escriturar(empresa, vinculo_)
    client.post(url, {"acao": "criar"})
    client.post(url, {"acao": "bloco", "sinal": "revenda"})


def _nota_de_outra_empresa(escritorio, usuario, empresa, *, numero):
    """Nota de 100,00 emitida pela OUTRA empresa do escritório (CSOSN 102, CFOP 5102)."""
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
            vnf="100.00",
            totais={"vProd": "100.00"},
            emitente=("CNPJ", CNPJ_DESTINATARIO_A),
            emitente_nome=empresa.razao_social,
            destinatario=None,
            numero=numero,
        ),
    )
    return vinculo(documento, empresa)


# ---------------------------------------------------------------------------
# Tela 5: conferência do mês
# ---------------------------------------------------------------------------


def test_conferencia_mostra_receita_por_natureza_composicao_e_totais(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    _escriturar_com_o_exemplo(client, empresa, vinculo_)
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"})

    texto = _texto(client.get(_url_conferencia(empresa)))

    assert "Receita de NF-e por natureza" in texto
    assert "Receita de NF-e do mês (soma das naturezas de receita, menos a devolução)" in texto
    assert "2.880,00" in texto  # total e composição do mercado interno
    assert "Mercado interno" in texto
    assert "Naturezas que não são receita: aparecem à parte, com soma zero" not in texto


def _quantidade(texto, rotulo):
    """Número da linha de conferência com este rótulo (a célula seguinte ao rótulo)."""
    achado = re.search(
        rf"<th scope=\"row\">{re.escape(rotulo)}</th>\s*<td>\s*(?:<span[^>]*>)?(\d+)", texto
    )
    assert achado, f"linha '{rotulo}' ausente"
    return achado.group(1)


def test_conferencia_nao_soma_nota_cancelada_depois_de_escriturada_e_a_destaca(
    client, gestor, cenario
):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    _escriturar_com_o_exemplo(client, empresa, vinculo_)
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"})
    antes = _texto(client.get(_url_conferencia(empresa)))
    # Cancelamento depois da efetivação: a nota sai da receita, e o estorno não é automático.
    services.receber_envio(
        escritorio=empresa.escritorio,
        usuario=gestor,
        arquivo=proc_evento_xml(chave=vinculo_.documento.chave),
        nome_arquivo="cancelamento.xml",
    )

    depois = _texto(client.get(_url_conferencia(empresa)))

    # A contagem de efetivadas é do número: antes 1, depois 0 (a cancelada não conta como válida).
    assert _quantidade(antes, "Escrituradas e efetivadas") == "1"
    assert _quantidade(depois, "Escrituradas e efetivadas") == "0"
    assert _quantidade(depois, "Canceladas depois de escriturada") == "1"
    assert "2.880,00" in antes
    assert "Canceladas depois de escriturada" in depois
    assert "sair da receita, estornar" in depois
    assert "Nenhuma natureza de receita escriturada no mês." in depois
    assert "2.880,00" not in depois


# ---------------------------------------------------------------------------
# Atalhos, menu, trilha e acessibilidade
# ---------------------------------------------------------------------------


def test_home_do_fiscal_tem_o_atalho_para_as_nfe_a_escriturar_da_empresa_unica(
    client, gestor, emitente
):
    _logar(client, gestor)

    html = client.get(reverse("module_home:home", args=["fiscal"])).content.decode("utf-8")

    assert f'href="{reverse("fiscal_web:nfe_a_escriturar")}?' in html
    assert f"empresa={emitente.pk}" in html
    assert "NF-e a escriturar" in html


def test_menu_do_fiscal_tem_o_grupo_de_escrituracao_de_nfe_e_marca_a_pagina_atual(client, cenario):
    html = _texto(client.get(_url_conferencia(cenario["empresa"])))

    assert 'aria-labelledby="grupo-escrituracao-nfe"' in html
    assert f'href="{reverse("fiscal_web:nfe_a_escriturar")}"' in html
    assert '<span class="item-atual" aria-current="page">Conferência de NF-e</span>' in html


def test_trilha_da_escriturar_leva_a_lista_e_marca_a_tela_atual(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]

    html = _texto(client.get(_url_escriturar(empresa, vinculo_)))

    assert 'aria-label="Trilha de navegação"' in html
    assert f'href="{_url_lista(empresa)}"' in html
    assert 'aria-current="page">Escriturar NF-e nº 1</li>' in html


@pytest.mark.parametrize(
    "rota",
    ["lista", "escriturar", "conferencia", "reclassificar"],
)
def test_telas_novas_sao_acessiveis_sem_estilo_embutido_e_com_rotulo(client, cenario, rota):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    url = {
        "lista": _url_lista(empresa),
        "escriturar": _url_escriturar(empresa, vinculo_),
        "conferencia": _url_conferencia(empresa),
        "reclassificar": _url_reclassificar() + "?" + urlencode({"empresa": empresa.pk}),
    }[rota]
    if rota == "escriturar":
        # Com rascunho, a tela tem a tabela de itens (a que precisa de escopo nos cabeçalhos).
        client.post(url, {"acao": "criar"})

    html = _texto(client.get(url))

    assert_moldura_acessivel(html)
    assert " style=" not in html
    # Todo campo tem rótulo `label for`, e todo `aria-describedby` aponta para um id que existe.
    for campo in re.findall(r'<(?:input|select|textarea)[^>]*\bid="([^"]+)"', html):
        assert f'for="{campo}"' in html, f"campo {campo} sem rótulo"
    for alvo in re.findall(r'aria-describedby="([^"]+)"', html):
        assert f'id="{alvo}"' in html, f"aria-describedby aponta para {alvo}, que não existe"
    # Toda tabela tem legenda, e todo cabeçalho de coluna declara escopo.
    assert html.count("<table") == html.count("<caption")
    if "<table" in html:
        assert 'scope="col"' in html


def test_estorno_com_botao_perigoso_e_motivo_com_rotulo(client, cenario):
    empresa, vinculo_ = cenario["empresa"], cenario["vinculo"]
    escrituracao = _escriturar_com_o_exemplo(client, empresa, vinculo_)
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "efetivar"})

    html = _texto(client.get(_url_estornar(empresa, escrituracao)))

    assert_moldura_acessivel(html)
    assert 'for="id_motivo"' in html
    assert 'aria-describedby="id_motivo_ajuda"' in html
    assert 'class="botao botao--perigoso"' in html


def test_pre_das_nao_mostra_mais_a_recusa_hi122_por_receita_de_nfe(
    client, gestor, emitente, escritorio_a
):
    _logar(client, gestor)
    vinculo_ = _nota(escritorio_a, gestor, emitente, numero="1")
    _escriturar_com_o_exemplo(client, emitente, vinculo_)
    client.post(_url_escriturar(emitente, vinculo_), {"acao": "efetivar"})

    html = _texto(
        client.get(reverse("fiscal_web:pre_das"), {"empresa": emitente.pk, "ano": ANO, "mes": MES})
    )

    # DL-082: a recusa geral por NF-e saiu (HI-122). A tela não repete o motivo antigo.
    assert "receita de mercadoria (NF-e) no mês" not in html
    assert "receita_de_mercadoria" not in html


def test_presumido_mostra_legivel_a_apuracao_parcial_por_nfe_nao_escriturada(
    client, gestor, emitente, escritorio_a
):
    """Item 7 da frente B. DL-083: a NF-e EFETIVADA já entra no Presumido, e a recusa que sobra é a
    NF-e do trimestre ainda NÃO escriturada (rascunho). O motivo chega à tela em português, sem o
    código interno. O cálculo não muda aqui."""
    _logar(client, gestor)
    vinculo_ = _nota(escritorio_a, gestor, emitente, numero="1")
    _escriturar_com_o_exemplo(client, emitente, vinculo_)

    html = _texto(
        client.get(
            reverse("fiscal_web:presumido_apuracao"),
            {"empresa": emitente.pk, "ano": ANO, "trimestre": 1},
        )
    )

    assert "NF-e do trimestre ainda não escriturada" in html
    assert "nfe_nao_escriturada" not in html


def test_avisos_de_ibscbs_aparecem_na_tela_so_no_caso_que_os_justifica(
    client, gestor, emitente, escritorio_a
):
    """Item 8 da frente B (HI-123): grupo IBS/CBS em nota de CRT 1 emitida em 2026 aparece como
    aviso, com o dispositivo, e fora da receita. Nota sem o grupo não ganha aviso nenhum."""
    _logar(client, gestor)
    com_grupo = xml.nfe(
        dets=[
            xml.det(
                1,
                cfop="5102",
                vprod="100.00",
                icms_xml=xml.icms(csosn="102"),
                ibscbs=True,
            )
        ],
        vnf="100.00",
        totais={"vProd": "100.00"},
        crt="1",
        numero="11",
    )
    vinculo_ = vinculo(receber(escritorio_a, gestor, com_grupo), emitente)
    client.post(_url_escriturar(emitente, vinculo_), {"acao": "criar"})

    texto = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    assert "Grupo IBS/CBS presente em nota de CRT 1 emitida em 2026: conferir." in texto
    assert "Não entra na receita." in texto
    assert "LC 214/2025, art. 348" in texto

    sem_grupo = _nota(escritorio_a, gestor, emitente, numero="12")
    assert "Grupo IBS/CBS" not in _texto(client.get(_url_escriturar(emitente, sem_grupo)))


def test_item_sem_sugestao_mostra_sem_sugestao_escolha_e_o_motivo_do_servico(
    client, gestor, emitente, escritorio_a
):
    """CFOP 5501 (comercial exportadora, bonificação): o serviço não sugere natureza. A tela diz
    "sem sugestão — escolha" e mostra o motivo que o serviço devolveu, sem escolher por ele."""
    _logar(client, gestor)
    sem_sinal = xml.nfe(
        dets=[xml.det(1, cfop="5501", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="100.00",
        totais={"vProd": "100.00"},
        numero="13",
    )
    vinculo_ = vinculo(receber(escritorio_a, gestor, sem_sinal), emitente)
    client.post(_url_escriturar(emitente, vinculo_), {"acao": "criar"})

    texto = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    assert "sem sugestão — escolha" in texto
    assert "sem sugestão: CFOP 5501 (comercial exportadora, bonificação)" in texto
    assert "Escolha a natureza" in texto  # opção vazia: nenhuma natureza fica pré-marcada
    assert "Falta a natureza de 1 item(ns)." in texto
