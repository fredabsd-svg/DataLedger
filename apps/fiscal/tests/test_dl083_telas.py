"""DL-083, frente B: telas da receita de NF-e (escrituração e conferência) e do Presumido.

Critérios de aceite da frente B (instrução de implementação, sobre o item 8 do plano):
1. item indTot 0 com frete mostra a receita do item (o frete) e o aviso; item com indDeduzDeson 1
   mostra o aviso do ICMS desonerado com o valor em pt-BR; com indDeduzDeson 0, nada se deduz;
2. a soma de receita exibida na tela da nota é a da conferência do domínio para a mesma nota;
3. o seletor de natureza oferece `combustivel` e `combustivel_revenda`, com os rótulos do enum;
4. a apuração do Presumido com NF-e mostra as linhas (origem "NF-e"), a devolução deduzida e
   o saldo; trimestre com NF-e em rascunho mostra "NF-e do trimestre ainda não escriturada";
5. isolamento: outro escritório recebe 404; CLIENTE recebe 403; PARALEGAL lê e não escreve.

Os valores esperados estão escritos à mão, em pt-BR, com a conta em comentário. Dados sintéticos
(`xml_nfe_dl081`, CNPJs de `xml_nfe_dl080`). As NF-e de cenário entram pela recepção real, e a
efetivação de cenário passa pelo serviço; o que se confere aqui é o que chega à TELA.
"""

import html as html_lib
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import presumido as servico_presumido
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.escrituracao_nfe import DivergenciaComVnf
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    LeituraItensNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 3
DH_FEV = "2026-02-10T10:00:00-03:00"
DH_MAI = "2026-05-10T10:00:00-03:00"
DH_JUL = "2026-07-10T10:00:00-03:00"
DH_2027 = "2027-03-10T10:00:00-03:00"

# Rótulos escritos à mão, como o contador lê na tela.
ROTULO_REVENDA = "Venda de mercadoria adquirida de terceiros (revenda)"
ROTULO_COMBUSTIVEL = "Revenda de combustíveis para consumo (1,6% no IRPJ)"
ROTULO_COMBUSTIVEL_REVENDA = "Revenda de combustíveis para revenda (8% no IRPJ)"
ROTULO_DEVOLUCAO = "Devolução de venda recebida"
ROTULO_ATIVIDADE_COMERCIO = "Comércio, indústria e transporte de cargas"
ROTULO_ATIVIDADE_COMBUSTIVEIS = "Revenda de combustíveis"
ROTULO_PAPEL_RECEITA = "Receita"
ROTULO_PAPEL_DEDUCAO = "Dedução (devolução)"


# ---------------------------------------------------------------------------
# Fixtures: usuários por papel, e as empresas dos dois cenários
# ---------------------------------------------------------------------------


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-dl083-telas")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-dl083-telas")


@pytest.fixture
def cliente(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-dl083-telas")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-dl083-telas")


@pytest.fixture
def presumida(escritorio_a, gestor):
    """Empresa do Lucro Presumido em 2026, com critério de competência e a atividade padrão de
    serviços. A receita de NF-e não usa o padrão: vem da natureza de cada item."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Presumida DL083 Telas Ltda", cnpj=CNPJ_EMITENTE_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    servico_presumido.definir_criterio(empresa, 2026, "competencia", gestor)
    servico_presumido.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": True},
        gestor,
    )
    return empresa


# ---------------------------------------------------------------------------
# Auxiliares: XML sintético, URLs, a leitura do HTML e os passos pela tela
# ---------------------------------------------------------------------------


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _texto(resposta):
    """HTML sem entidades, como o contador lê."""
    return html_lib.unescape(resposta.content.decode("utf-8"))


def _xml_dos_avisos(*, indeduz="1", vnf="290.00", numero="951", dh_emi=None, cnpj=CNPJ_EMITENTE_A):
    """Três itens, o mesmo cenário do teste de API da frente A:
    1 normal, vProd 100,00 (receita 100,00);
    2 com indTot 0, vProd 50,00 não cobrado e frete 10,00 (receita 10,00);
    3 com vICMSDeson de 20,00: receita 180,00 com indDeduzDeson 1, ou 200,00 com 0.
    Total da nota: 290,00 com indDeduzDeson 1 (conferência fecha); 310,00 com 0."""
    deson = xml.icms(
        cst="40",
        filhos=f"<vICMSDeson>20.00</vICMSDeson><indDeduzDeson>{indeduz}</indDeduzDeson>",
    )
    dets = [
        xml.det(1, vprod="100.00"),
        xml.det(2, vprod="50.00", ind_tot="0", vfrete="10.00"),
        xml.det(3, vprod="200.00", icms_xml=deson),
    ]
    extras = {"dh_emi": dh_emi} if dh_emi else {}
    return xml.nfe(dets=dets, vnf=vnf, numero=numero, emitente=("CNPJ", cnpj), **extras)


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Telas DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _nota_de_avisos(escritorio, usuario, empresa, **dados):
    return vinculo(receber(escritorio, usuario, _xml_dos_avisos(**dados)), empresa)


def _xml_de_uma_linha(*, numero, valor, dh_emi, cnpj, cfop="5102", tp_nf="1", fin="1"):
    return xml.nfe(
        dets=[xml.det(1, cfop=cfop, vprod=valor, icms_xml=xml.icms(csosn="102"))],
        vnf=valor,
        totais={"vProd": valor},
        numero=str(numero),
        dh_emi=dh_emi,
        emitente=("CNPJ", cnpj),
        tp_nf=tp_nf,
        fin_nfe=fin,
    )


def _efetivar_nfe(escritorio, usuario, empresa, *, natureza, numero, valor, dh_emi, **xml_extra):
    """NF-e de uma linha, com a natureza em todos os itens, efetivada pelo serviço real."""
    documento = receber(
        escritorio,
        usuario,
        _xml_de_uma_linha(
            numero=numero, valor=valor, dh_emi=dh_emi, cnpj=empresa.cnpj, **xml_extra
        ),
    )
    escrituracao = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=escrituracao).update(natureza=natureza)
    servico_nfe.efetivar(escrituracao, usuario=usuario)


def _url_escriturar(empresa, vinculo_):
    return reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo_.pk])


def _url_conferencia(empresa):
    return (
        reverse("fiscal_web:nfe_conferencia")
        + "?"
        + urlencode({"empresa": empresa.pk, "ano": ANO, "mes": MES})
    )


def _url_apuracao(empresa, trimestre):
    return (
        reverse("fiscal_web:presumido_apuracao")
        + "?"
        + urlencode({"empresa": empresa.pk, "ano": ANO, "trimestre": trimestre})
    )


def _criar_rascunho(client, empresa, vinculo_):
    resposta = client.post(_url_escriturar(empresa, vinculo_), {"acao": "criar"})
    assert resposta.status_code == 302


def _confirmar_natureza(client, empresa, vinculo_, n_item, natureza):
    item = ItemNFe.objects.get(documento=vinculo_.documento, n_item=n_item)
    resposta = client.post(
        _url_escriturar(empresa, vinculo_),
        {"acao": "item", "item_id": item.pk, "natureza": natureza},
    )
    assert resposta.status_code == 302


def _linhas(html):
    """Cada `<tr>` como lista de textos das células (th e td), sem tags e com espaços normalizados.
    Só lê a tabela com `<tr>` simples, que é como as telas desta frente escrevem."""
    linhas = []
    for linha in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        celulas = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", linha, re.S)
        linhas.append([" ".join(re.sub(r"<[^>]+>", " ", c).split()) for c in celulas])
    return linhas


def _linha_do_item(html, n_item):
    """Linha da tabela de itens da escrituração: nove células (item, produto, CFOP, CST, NCM, vProd,
    receita, natureza, e marca e segmento da devolução, DL-082). Índices: vProd é 5, receita é 6.
    Ajuste mínimo: a coluna nova acrescentou uma célula; os índices lidos não mudaram."""
    for linha in _linhas(html):
        if len(linha) == 9 and linha[0] == str(n_item):
            return linha
    raise AssertionError(f"item {n_item} não aparece na tela")


def _valor_na_linha(html, inicio):
    """Último valor da primeira linha cujo rótulo começa por `inicio` (conferência e totais)."""
    for linha in _linhas(html):
        if linha and linha[0].startswith(inicio):
            return linha[-1]
    raise AssertionError(f"linha '{inicio}' ausente")


def _linha_com(html, *primeiras):
    """Linha cujas primeiras células são exatamente `primeiras` (a linha tem de existir)."""
    for linha in _linhas(html):
        if linha[: len(primeiras)] == list(primeiras):
            return linha
    raise AssertionError(f"linha {primeiras!r} ausente")


def _valor_da_definicao(html, rotulo):
    achado = re.search(
        rf"<dt>{re.escape(rotulo)}</dt>\s*<dd[^>]*>(.*?)</dd>",
        html,
        re.S,
    )
    assert achado, f"definição '{rotulo}' ausente"
    return " ".join(re.sub(r"<[^>]+>", " ", achado.group(1)).split())


def _botao_efetivar(html):
    achado = re.search(r"<button[^>]*>Efetivar escrituração</button>", html)
    assert achado, "botão de efetivar ausente"
    return achado.group(0)


# ---------------------------------------------------------------------------
# Critério 1: receita do item, avisos de indTot 0 e de ICMS desonerado (escrituração)
# ---------------------------------------------------------------------------


def test_item_indtot_zero_mostra_o_frete_como_receita_e_o_aviso_do_vprod(
    client, gestor, emitente, escritorio_a
):
    """Item 2: indTot 0, vProd 50,00 não cobrado, frete 10,00. A receita é 10,00 (o frete), e o
    aviso diz que o vProd não compõe a receita. Nada de "fora do total" solto na célula."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente)
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)

    html = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    item2 = _linha_do_item(html, 2)
    assert item2[5] == "50,00"
    assert item2[6] == "10,00 item 2 fora do total: vProd R$ 50,00 não compõe a receita"


def test_item_normal_mostra_o_vprod_como_receita_e_nao_ganha_aviso(
    client, gestor, emitente, escritorio_a
):
    # 100,00 de vProd, sem desconto nem deson: receita 100,00 e célula sem texto de aviso.
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente)
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)

    item1 = _linha_do_item(_texto(client.get(_url_escriturar(emitente, vinculo_))), 1)

    assert item1[6] == "100,00"


def test_icms_desonerado_deduzido_mostra_o_aviso_com_o_valor_em_ptbr(
    client, gestor, emitente, escritorio_a
):
    """Item 3: vProd 200,00, vICMSDeson 20,00 com indDeduzDeson 1. Receita 180,00, e o aviso
    "ICMS desonerado deduzido do total: R$ 20,00"."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente)
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)

    item3 = _linha_do_item(_texto(client.get(_url_escriturar(emitente, vinculo_))), 3)

    assert item3[5] == "200,00"
    assert item3[6] == "180,00 ICMS desonerado deduzido do total: R$ 20,00"


def test_indeduzdeson_zero_nao_deduz_e_nao_mostra_o_aviso_do_icms(
    client, gestor, emitente, escritorio_a
):
    """Com indDeduzDeson 0 o vICMSDeson não sai do total: a receita do item 3 é o vProd cheio, e a
    tela não diz que houve dedução. Total da nota: 100 + 10 + 200 = 310,00."""
    vinculo_ = _nota_de_avisos(
        escritorio_a, gestor, emitente, indeduz="0", vnf="310.00", numero="952"
    )
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)

    html = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    assert _linha_do_item(html, 3)[6] == "200,00"
    assert "ICMS desonerado" not in html


# ---------------------------------------------------------------------------
# Critério 2: a soma da receita na tela é a da conferência do domínio, para a mesma nota
# ---------------------------------------------------------------------------


def test_soma_da_receita_no_rascunho_conferido_e_a_do_dominio(
    client, gestor, emitente, escritorio_a
):
    """Rascunho com as três naturezas de receita, que fecha com o vNF. A tela mostra a soma que o
    serviço confere: 100,00 + 10,00 + 180,00 = 290,00, igual ao vNF."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente)
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)
    for n_item in (1, 2, 3):
        _confirmar_natureza(client, emitente, vinculo_, n_item, NaturezaOperacaoNFe.REVENDA)

    html = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    documento = vinculo_.documento
    registros = NaturezaItemNFe.objects.select_related("item").filter(
        escrituracao__vinculo=vinculo_
    )
    pares = [(r.item, r.natureza) for r in registros.order_by("item__n_item")]
    conferencia = servico_nfe.conferir_valores(
        documento, LeituraItensNFe.objects.get(documento=documento), pares
    )
    assert conferencia.soma_itens == Decimal("290.00")
    assert _valor_na_linha(html, "Receita dos itens") == "290,00"


def test_soma_da_receita_com_nota_recusada_e_a_mesma_do_dominio(
    client, gestor, emitente, escritorio_a
):
    """vNF de 300,00 contra uma receita de 290,00: o serviço recusa a conferência. A tela, que
    não tem a conferência, refaz a soma com a MESMA função (`receita_do_item`). A mensagem de
    divergência do domínio traz a soma, e a tela tem de mostrar o mesmo número."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente, vnf="300.00", numero="953")
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)
    for n_item in (1, 2, 3):
        _confirmar_natureza(client, emitente, vinculo_, n_item, NaturezaOperacaoNFe.REVENDA)

    html = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    documento = vinculo_.documento
    registros = NaturezaItemNFe.objects.select_related("item").filter(
        escrituracao__vinculo=vinculo_
    )
    pares = [(r.item, r.natureza) for r in registros.order_by("item__n_item")]
    with pytest.raises(DivergenciaComVnf) as erro:
        servico_nfe.conferir_valores(
            documento, LeituraItensNFe.objects.get(documento=documento), pares
        )
    soma_do_dominio = re.search(r"Receita dos itens \(R\$ ([\d.]+,\d{2})\)", str(erro.value))
    assert soma_do_dominio is not None
    assert soma_do_dominio.group(1) == "290,00"
    assert _valor_na_linha(html, "Receita dos itens") == "290,00"
    assert "Não confere" in html


def test_soma_da_receita_efetivada_bate_com_o_total_da_conferencia_do_mes(
    client, gestor, emitente, escritorio_a
):
    """Nota efetivada pela tela: a receita mostrada é a gravada (290,00). A tela de conferência do
    mês mostra a mesma nota no total de NF-e, e o domínio soma 290,00 nas naturezas de receita."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente)
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)
    for n_item in (1, 2, 3):
        _confirmar_natureza(client, emitente, vinculo_, n_item, NaturezaOperacaoNFe.REVENDA)
    efetivou = client.post(_url_escriturar(emitente, vinculo_), {"acao": "efetivar"})
    assert efetivou.status_code == 302

    receita_da_nota = _valor_na_linha(
        _texto(client.get(_url_escriturar(emitente, vinculo_))), "Receita dos itens"
    )
    html_mes = _texto(client.get(_url_conferencia(emitente)))

    conferencia_do_mes = servico_nfe.conferencia_do_mes(emitente, ANO, MES)
    soma_do_dominio = sum(
        (linha["soma_na_receita"] for linha in conferencia_do_mes.receita_por_natureza.values()),
        Decimal("0.00"),
    )
    assert soma_do_dominio == Decimal("290.00")
    assert receita_da_nota == "290,00"
    assert _valor_na_linha(html_mes, "Receita de NF-e do mês") == "290,00"


# ---------------------------------------------------------------------------
# Critério 3: seletor de natureza com as duas naturezas de combustível
# ---------------------------------------------------------------------------


def _opcoes(html):
    return dict(re.findall(r'<option value="([^"]+)"[^>]*>([^<]*)</option>', html))


def test_seletor_de_natureza_oferece_as_duas_naturezas_de_combustivel(
    client, gestor, emitente, escritorio_a
):
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente)
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)

    opcoes = _opcoes(_texto(client.get(_url_escriturar(emitente, vinculo_))))

    assert opcoes["combustivel"] == ROTULO_COMBUSTIVEL
    assert opcoes["combustivel_revenda"] == ROTULO_COMBUSTIVEL_REVENDA


def test_reclassificacao_em_massa_oferece_as_duas_naturezas_de_combustivel(
    client, gestor, emitente
):
    _logar(client, gestor)
    url = reverse("fiscal_web:nfe_reclassificar") + f"?empresa={emitente.pk}"

    opcoes = _opcoes(_texto(client.get(url)))

    assert opcoes["combustivel"] == ROTULO_COMBUSTIVEL
    assert opcoes["combustivel_revenda"] == ROTULO_COMBUSTIVEL_REVENDA


def test_frete_de_item_fora_do_total_em_nota_com_venda_e_atribuido_e_avisado(
    client, gestor, emitente, escritorio_a
):
    """HI-138 (substitui o bloqueio antigo): item 2 (indTot 0, frete 10,00) em remessa, numa nota
    com vendas. O frete é atribuído à receita das vendas, e a tela AVISA. O botão continua
    habilitado, porque a nota fecha com o vNF (conferência ao centavo)."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente, numero="955")
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)
    _confirmar_natureza(client, emitente, vinculo_, 1, NaturezaOperacaoNFe.REVENDA)
    _confirmar_natureza(client, emitente, vinculo_, 2, NaturezaOperacaoNFe.REMESSA_RETORNO)
    _confirmar_natureza(client, emitente, vinculo_, 3, NaturezaOperacaoNFe.REVENDA)

    html = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    assert (
        "item 2 (Remessa, retorno, demonstração, conserto ou mostruário): R$ 10,00 de "
        "frete/seguro/outros/desconto atribuído à receita da venda desta nota"
    ) in html
    assert "item fora do total com valor cobrado" not in html
    assert "disabled" not in _botao_efetivar(html)


def test_efetivar_nota_de_2027_mostra_a_recusa_nomeada_e_nao_grava(
    client, gestor, emitente, escritorio_a
):
    """Receita de 2027 não se efetiva (HI-133). Se o botão estiver habilitado, o servidor recusa no
    POST com a mesma mensagem, e a escrituração continua em rascunho."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente, dh_emi=DH_2027, numero="956")
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)
    for n_item in (1, 2, 3):
        _confirmar_natureza(client, emitente, vinculo_, n_item, NaturezaOperacaoNFe.REVENDA)

    resposta = client.post(_url_escriturar(emitente, vinculo_), {"acao": "efetivar"})

    assert resposta.status_code == 409
    assert "regra de receita de 2027 pendente: NT 2026.008 e vNF" in _texto(resposta)
    assert EscrituracaoNFe.objects.get(vinculo=vinculo_).estado == EstadoEscrituracao.RASCUNHO


# ---------------------------------------------------------------------------
# Critério 4: memória do Presumido com as linhas de NF-e, devolução e saldo
# ---------------------------------------------------------------------------


def test_apuracao_mostra_as_linhas_de_nfe_com_origem_natureza_cfop_atividade_e_valor(
    client, gestor, presumida, escritorio_a
):
    """Revenda de 5.000,00 (CFOP 5102, comércio e indústria) e combustível para consumo de 3.000,00
    (CFOP 5656, revenda de combustíveis). Cada linha traz origem, nota, competência, natureza,
    CFOP, atividade, papel e valor. Na memória, cada atividade tem a sua receita."""
    _efetivar_nfe(
        escritorio_a,
        gestor,
        presumida,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=23,
        valor="5000.00",
        dh_emi=DH_FEV,
    )
    _efetivar_nfe(
        escritorio_a,
        gestor,
        presumida,
        natureza=NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=24,
        valor="3000.00",
        dh_emi="2026-02-11T10:00:00-03:00",
        cfop="5656",
    )
    _logar(client, gestor)

    html = _texto(client.get(_url_apuracao(presumida, 1)))

    assert _linha_com(html, "NF-e", "nº 23") == [
        "NF-e",
        "nº 23",
        "02/2026",
        ROTULO_REVENDA,
        "5102",
        ROTULO_ATIVIDADE_COMERCIO,
        ROTULO_PAPEL_RECEITA,
        "5.000,00",
    ]
    assert _linha_com(html, "NF-e", "nº 24") == [
        "NF-e",
        "nº 24",
        "02/2026",
        ROTULO_COMBUSTIVEL,
        "5656",
        ROTULO_ATIVIDADE_COMBUSTIVEIS,
        ROTULO_PAPEL_RECEITA,
        "3.000,00",
    ]
    # Memória por atividade (as três colunas seguem a atividade): a receita de combustível sai na
    # linha da revenda de combustíveis, e a de comércio na linha de comércio. `_linha_com` falha se
    # a linha não existir com esse valor na coluna Receita.
    _linha_com(html, ROTULO_ATIVIDADE_COMBUSTIVEIS, "3.000,00")
    _linha_com(html, ROTULO_ATIVIDADE_COMERCIO, "5.000,00")
    # Sem devolução, a devolução deduzida e o saldo aparecem zerados.
    assert (
        _valor_da_definicao(
            html, "Devolução de NF-e deduzida neste trimestre (comércio e indústria)"
        )
        == "0,00"
    )
    assert (
        _valor_da_definicao(html, "Saldo de devolução de NF-e que passa ao trimestre seguinte")
        == "0,00"
    )


def test_devolucao_deduzida_e_saldo_aparecem_no_trimestre_em_que_acontecem(
    client, gestor, presumida, escritorio_a
):
    """Venda de 100.000,00 em fevereiro; devolução de 150.000,00 em maio, sem venda no 2º trimestre;
    venda de 120.000,00 em julho.
      2º: a devolução não tem o que deduzir; deduzido 0,00; saldo 150.000,00.
      3º: absorve 120.000,00 da venda; deduzido 120.000,00; saldo 30.000,00.
      4º: o saldo de 30.000,00 não coube no ano: aviso."""
    _efetivar_nfe(
        escritorio_a,
        gestor,
        presumida,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=41,
        valor="100000.00",
        dh_emi=DH_FEV,
    )
    _efetivar_nfe(
        escritorio_a,
        gestor,
        presumida,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=42,
        valor="150000.00",
        dh_emi=DH_MAI,
        cfop="1202",
        tp_nf="0",
        fin="4",
    )
    _efetivar_nfe(
        escritorio_a,
        gestor,
        presumida,
        natureza=NaturezaOperacaoNFe.REVENDA,
        numero=43,
        valor="120000.00",
        dh_emi=DH_JUL,
    )
    _logar(client, gestor)

    segundo = _texto(client.get(_url_apuracao(presumida, 2)))
    assert _linha_com(segundo, "NF-e", "nº 42") == [
        "NF-e",
        "nº 42",
        "05/2026",
        ROTULO_DEVOLUCAO,
        "1202",
        ROTULO_ATIVIDADE_COMERCIO,
        ROTULO_PAPEL_DEDUCAO,
        "150.000,00",
    ]
    assert (
        _valor_da_definicao(
            segundo, "Devolução de NF-e deduzida neste trimestre (comércio e indústria)"
        )
        == "0,00"
    )
    assert (
        _valor_da_definicao(segundo, "Saldo de devolução de NF-e que passa ao trimestre seguinte")
        == "150.000,00"
    )

    terceiro = _texto(client.get(_url_apuracao(presumida, 3)))
    assert (
        _valor_da_definicao(
            terceiro, "Devolução de NF-e deduzida neste trimestre (comércio e indústria)"
        )
        == "120.000,00"
    )
    assert (
        _valor_da_definicao(terceiro, "Saldo de devolução de NF-e que passa ao trimestre seguinte")
        == "30.000,00"
    )

    quarto = _texto(client.get(_url_apuracao(presumida, 4)))
    assert "não coube na receita do ano: R$ 30.000,00" in quarto


def test_nfe_do_trimestre_em_rascunho_aparece_como_recusa_nomeada(
    client, gestor, presumida, escritorio_a
):
    """NF-e de fevereiro ainda em rascunho: a apuração do 1º trimestre fica parcial, com a recusa
    em português e a nota que a causa. O código interno não aparece."""
    documento = receber(
        escritorio_a,
        gestor,
        _xml_de_uma_linha(numero=63, valor="800.00", dh_emi=DH_FEV, cnpj=presumida.cnpj),
    )
    vinculo_ = vinculo(documento, presumida)
    _logar(client, gestor)
    client.post(
        reverse("fiscal_web:nfe_escriturar", args=[presumida.pk, vinculo_.pk]), {"acao": "criar"}
    )

    html = _texto(client.get(_url_apuracao(presumida, 1)))

    assert _linha_com(html, "NF-e do trimestre ainda não escriturada") == [
        "NF-e do trimestre ainda não escriturada",
        "NF-e nº 63",
    ]
    assert "Parcial" in html
    assert "nfe_nao_escriturada" not in html


def test_devolucao_de_combustivel_avisa_e_servico_conjugado_recusa_como_recusa_nomeada(
    client, gestor, presumida, escritorio_a
):
    _efetivar_nfe(
        escritorio_a,
        gestor,
        presumida,
        natureza=NaturezaOperacaoNFe.DEVOLUCAO_VENDA,
        numero=61,
        valor="10000.00",
        dh_emi=DH_FEV,
        cfop="1662",
        tp_nf="0",
        fin="4",
    )
    _efetivar_nfe(
        escritorio_a,
        gestor,
        presumida,
        natureza=NaturezaOperacaoNFe.SERVICO_CONJUGADA,
        numero=62,
        valor="5000.00",
        dh_emi=DH_FEV,
    )
    _logar(client, gestor)

    html = _texto(client.get(_url_apuracao(presumida, 1)))

    # HI-140: a devolução de combustível não recusa mais; a memória avisa a natureza.
    assert "devolução com destinação a consumo deduzida a 8%: confira a natureza" in html
    assert "devolução de combustível: atividade a confirmar" not in html
    assert _linha_com(html, "serviço em NF-e conjugada: atividade de presunção a informar") == [
        "serviço em NF-e conjugada: atividade de presunção a informar",
        "NF-e nº 62",
    ]


# ---------------------------------------------------------------------------
# Estados: vazio, erro e sem empresa (o padrão das telas vizinhas)
# ---------------------------------------------------------------------------


def test_apuracao_sem_nfe_nao_mostra_a_tabela_nem_o_bloco_de_devolucao(client, gestor, presumida):
    _logar(client, gestor)

    resposta = client.get(_url_apuracao(presumida, 1))

    html = _texto(resposta)
    assert resposta.status_code == 200
    assert "Linhas de NF-e que compõem" not in html
    assert "Devolução de NF-e deduzida" not in html


def test_apuracao_sem_empresa_pede_a_escolha(client, gestor):
    _logar(client, gestor)

    resposta = client.get(reverse("fiscal_web:presumido_apuracao"))

    assert resposta.status_code == 200
    assert "Escolha uma empresa, o ano e o trimestre para ver a apuração." in _texto(resposta)


def test_apuracao_com_trimestre_invalido_responde_400_com_o_erro_do_formulario(
    client, gestor, presumida
):
    _logar(client, gestor)

    resposta = client.get(
        reverse("fiscal_web:presumido_apuracao"),
        {"empresa": presumida.pk, "ano": ANO, "trimestre": 9},
    )

    assert resposta.status_code == 400
    assert 'id="erro_do_formulario"' in _texto(resposta)


# ---------------------------------------------------------------------------
# Critério 5: permissões e isolamento nas três telas
# ---------------------------------------------------------------------------


def _urls_da_frente_b(empresa, vinculo_):
    return {
        "escriturar": _url_escriturar(empresa, vinculo_),
        "conferencia": _url_conferencia(empresa),
        "apuracao": _url_apuracao(empresa, 1),
    }


def test_paralegal_le_as_tres_telas_e_nao_ve_botao_de_escrita(
    client, paralegal, presumida, escritorio_a, gestor
):
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, presumida, numero="970")
    _logar(client, paralegal)

    urls = _urls_da_frente_b(presumida, vinculo_)
    for nome, url in urls.items():
        assert client.get(url).status_code == 200, nome
    escriturar = _texto(client.get(urls["escriturar"]))
    assert 'name="acao"' not in escriturar
    assert "Criar rascunho" not in escriturar
    assert "Efetivar escrituração" not in escriturar


def test_cliente_recebe_403_nas_tres_telas(client, cliente, presumida, escritorio_a, gestor):
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, presumida, numero="971")
    _logar(client, cliente)

    for nome, url in _urls_da_frente_b(presumida, vinculo_).items():
        assert client.get(url).status_code == 403, nome


def test_outro_escritorio_recebe_404_nas_tres_telas(
    client, gestor_b, presumida, escritorio_a, gestor
):
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, presumida, numero="972")
    _logar(client, gestor_b)

    for nome, url in _urls_da_frente_b(presumida, vinculo_).items():
        assert client.get(url).status_code == 404, nome


def test_anonimo_vai_para_o_login_nas_tres_telas(client, presumida, escritorio_a, gestor):
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, presumida, numero="973")

    for nome, url in _urls_da_frente_b(presumida, vinculo_).items():
        resposta = client.get(url)
        assert resposta.status_code == 302, nome
        assert "login" in resposta["Location"], nome


# A8 (HI-133): a tela desabilita "Efetivar" com o motivo de 2027, antes do POST.
@pytest.mark.django_db
def test_nota_de_2027_em_rascunho_mostra_motivo_e_botao_desabilitado_na_tela(
    client, gestor, emitente, escritorio_a
):
    """A tela mostra "Efetivar" desabilitado com o motivo de 2027.
    O servidor recusa no POST (409)."""
    vinculo_ = _nota_de_avisos(escritorio_a, gestor, emitente, dh_emi=DH_2027, numero="2702")
    _logar(client, gestor)
    _criar_rascunho(client, emitente, vinculo_)

    html = _texto(client.get(_url_escriturar(emitente, vinculo_)))

    assert "disabled" in _botao_efetivar(html)
    assert "regra de receita de 2027 pendente: NT 2026.008 e vNF" in html
