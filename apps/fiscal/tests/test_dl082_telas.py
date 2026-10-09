"""DL-082 (frente B): telas do pré-DAS de comércio e indústria e da escrituração de NF-e.

- Pré-DAS (`fiscal/pre_das.html`): mercadoria por anexo I/II e segmento; tributo desconsiderado
  escrito como tal, nunca como zero digitado; venda bruta, devolução deduzida e receita líquida;
  avisos (CSOSN 900) e recusas nomeadas, com o texto do domínio.
- Escrituração da NF-e (`fiscal/nfe_escriturar.html`): marca de monofásico e segmento da devolução,
  gravados pelas funções de domínio só em rascunho. Efetivada: só leitura.

A regra é a da frente A (`apps.fiscal.pre_das`, `apps.fiscal.escrituracao_nfe`). Aqui se prova o
que a TELA mostra e grava, e que a autorização vale no servidor (GESTOR grava; PARALEGAL vê com
controles desabilitados e POST 403; CLIENTE 403; outro escritório 404).

Valores esperados ESCRITOS À MÃO nestes testes, copiados dos casos de referência da frente A
(caso D, caso F, devolução de 20.000 e aviso CSOSN 900), e não calculados pela função de produção.
Dados 100% sintéticos (XML de `xml_nfe_dl080` e `xml_nfe_dl081`).
"""

import html as html_lib
import re

import pytest
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import views_web
from apps.fiscal.models import (
    ANEXO_I,
    ANEXO_II,
    SEGMENTO_EXPORTACAO,
    SEGMENTO_MONOFASICO,
    SEGMENTO_NORMAL,
    SEGMENTO_ST_MONOFASICO,
    SEGMENTO_SUJEITA_ST,
    EnquadramentoAtividade,
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    MercadoReceita,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    SegmentoDevolucao,
)
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import (
    atividade_padrao,
    cenario_simples,
    janela_de_receitas,
    receber_e_confirmar_mes,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

NF = NaturezaOperacaoNFe
ANO, MES = 2026, 6
SEGMENTOS_DE_MERCADORIA = (
    SEGMENTO_NORMAL,
    SEGMENTO_SUJEITA_ST,
    SEGMENTO_MONOFASICO,
    SEGMENTO_ST_MONOFASICO,
    SEGMENTO_EXPORTACAO,
)


@pytest.fixture
def loja_a(escritorio_a):
    """Emitente das NF-e de mercadoria (CNPJ_EMITENTE_A), no escritório A, já no Simples com a
    data de abertura que o RBT12 exige (`cenario_simples`, o mesmo cenário da frente A)."""
    return cenario_simples(
        Empresa.objects.create(
            escritorio=escritorio_a,
            razao_social="Comércio Telas DL082 Ltda",
            cnpj=CNPJ_EMITENTE_A,
        )
    )


@pytest.fixture
def paralegal_a(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-dl082-telas")


@pytest.fixture
def cliente_a(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-dl082-telas")


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _texto(resposta):
    """HTML sem entidades, para comparar com o texto que o contador lê."""
    return html_lib.unescape(resposta.content.decode("utf-8"))


def _pre_das(client, empresa, ano=ANO, mes=MES):
    return client.get(
        reverse("fiscal_web:pre_das"), {"empresa": empresa.pk, "ano": ano, "mes": mes}
    )


def _url_escriturar(empresa, documento):
    return reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk])


def _id_do_item(documento, n_item):
    return ItemNFe.objects.get(documento=documento, n_item=n_item).pk


def _rascunho(empresa, usuario, documento, naturezas):
    """Rascunho com as naturezas dadas (por `n_item`), pelo serviço de produção. Não efetiva."""
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    for n_item, natureza in naturezas.items():
        servico_nfe.definir_natureza(
            esc, natureza, [_id_do_item(documento, n_item)], usuario=usuario
        )
    return esc


def _tabela_que_contem(html, texto):
    """O bloco `<table>` que contém o texto (para checar caption e cabeçalhos da mesma tabela)."""
    for tabela in re.findall(r"<table.*?</table>", html, flags=re.S):
        if texto in tabela:
            return tabela
    raise AssertionError(f"nenhuma tabela contém {texto!r}")


# ---------------------------------------------------------------------------
# Cenários de referência (valores escritos à mão, copiados da frente A)
# ---------------------------------------------------------------------------


def _cenario_caso_d(loja, escritorio, usuario):
    """Caso D (frente A): Anexo I, RBT12 600.000 (3ª faixa, efetiva 7,19%). Normal 30.000, ST 12.000
    (CSOSN 500), monofásico 8.000 (natureza monofásica). Total 3.216,81 (normal 2.157,01; ST 573,76;
    monofásico 486,04)."""
    janela(loja, usuario, ANO, MES, [50000] * 12)
    documento = nota(
        escritorio,
        usuario,
        loja,
        numero=201,
        itens=[
            {"cfop": "5102", "vprod": "30000.00", "csosn": "102"},
            {"cfop": "5405", "vprod": "12000.00", "csosn": "500"},
            {"cfop": "5102", "vprod": "8000.00", "csosn": "102"},
        ],
    )
    escriturar(
        loja,
        usuario,
        documento,
        {
            1: NF.REVENDA,
            2: NF.REVENDA_ST_SUBSTITUIDO,
            3: NF.MONOFASICO,
        },
    )
    confirmar_pa(loja, usuario, ANO, MES)
    return loja


def _cenario_caso_f(loja, escritorio, usuario):
    """Caso F (frente A): Anexo II interno, RBT12 900.000 (efetiva 8,70%): produção 40.000 e ST de
    produção 10.000. Externo, RBT12 150.000 (1ª faixa): exportação de produção 20.000.
    Esperado (à mão): normal 3.480,00; ST 591,60; exportação 418,50; total 4.490,10."""
    janela(loja, usuario, ANO, MES, interno=[75000] * 12, externo=[12500] * 12)
    producao = nota(
        escritorio,
        usuario,
        loja,
        numero=811,
        itens=[{"cfop": "5101", "vprod": "40000.00"}],
    )
    escriturar(loja, usuario, producao, {1: NF.PRODUCAO_PROPRIA})
    st_producao = nota(
        escritorio,
        usuario,
        loja,
        numero=812,
        itens=[{"cfop": "5401", "vprod": "10000.00", "csosn": "500"}],
    )
    escriturar(loja, usuario, st_producao, {1: NF.REVENDA_ST_SUBSTITUIDO})
    exportacao = nota(
        escritorio,
        usuario,
        loja,
        numero=813,
        itens=[{"cfop": "7101", "vprod": "20000.00"}],
        id_dest="3",
    )
    escriturar(loja, usuario, exportacao, {1: NF.EXPORTACAO_DIRETA})
    confirmar_pa(loja, usuario, ANO, MES)
    return loja


def _cenario_devolucao(loja, escritorio, usuario):
    """Venda de revenda 100.000 (Anexo I, normal) e devolução de 20.000 confirmada como revenda.
    Esperado (à mão): bruto 100.000,00; deduzido 20.000,00; líquido 80.000,00; alíquota 5,32%;
    total 4.256,00 (RBT12 300.000)."""
    janela(loja, usuario, ANO, MES, [25000] * 12)
    venda = nota(
        escritorio, usuario, loja, numero=301, itens=[{"cfop": "5102", "vprod": "100000.00"}]
    )
    escriturar(loja, usuario, venda, {1: NF.REVENDA})
    devolucao = nota(
        escritorio,
        usuario,
        loja,
        numero=302,
        itens=[{"cfop": "1202", "vprod": "20000.00"}],
        devolucao=True,
    )
    escriturar(
        loja,
        usuario,
        devolucao,
        {1: NF.DEVOLUCAO_VENDA},
        segmentos={1: SegmentoDevolucao.REVENDA},
    )
    confirmar_pa(loja, usuario, ANO, MES)
    return loja


# ---------------------------------------------------------------------------
# Pré-DAS: critério 1 (anexo, segmento, desconsiderado como texto, bruto, deduzido, líquido)
# ---------------------------------------------------------------------------


def test_caso_d_mostra_anexo_I_os_tres_segmentos_e_o_total_de_referencia(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    _cenario_caso_d(loja_a, escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = _pre_das(client, loja_a)

    html = _texto(resposta)
    assert resposta.status_code == 200
    assert "Mercado interno: Anexo I" in html
    assert "7,1900%" in html
    for rotulo in (
        "Normal (sem ST, monofásico nem exportação)",
        "Sujeita a ST (ICMS substituído)",
        "Monofásico de PIS e Cofins",
    ):
        assert rotulo in html, rotulo
    # Totais de cada segmento (caso D), escritos à mão.
    assert re.search(
        r"Total da receita líquida de 30\.000,00 \(R\$\)</th>\s*<td></td>\s*"
        r'<td class="valor-monetario">2\.157,01</td>',
        html,
    )
    assert re.search(
        r"Total da receita líquida de 12\.000,00 \(R\$\)</th>\s*<td></td>\s*"
        r'<td class="valor-monetario">573,76</td>',
        html,
    )
    assert re.search(
        r"Total da receita líquida de 8\.000,00 \(R\$\)</th>\s*<td></td>\s*"
        r'<td class="valor-monetario">486,04</td>',
        html,
    )
    assert re.search(r'Total do pré-DAS</th>\s*<td class="valor-monetario">3\.216,81</td>', html)
    assert_moldura_acessivel(html)


def test_tributo_desconsiderado_aparece_como_texto_com_motivo_e_dispositivo_nunca_como_zero(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    """ICMS sai no segmento de ST; PIS e Cofins saem no monofásico. Na tabela, a célula de valor diz
    "desconsiderado" e a situação diz o motivo. Não há 0,00 digitado para esses tributos."""
    _cenario_caso_d(loja_a, escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, loja_a))

    # O título do segmento fica FORA da tabela: a tabela se acha pelo texto da situação.
    st = _tabela_que_contem(html, "ICMS: desconsiderado — ST")
    assert re.search(
        r'<th scope="row">ICMS</th>\s*<td class="valor-monetario">—</td>\s*'
        r'<td class="valor-monetario">desconsiderado</td>\s*'
        r"<td>ICMS: desconsiderado — ST \(Res\. CGSN 140, art\. 25, § 8º, I\)</td>",
        st,
    )
    assert '<td class="valor-monetario">0,00</td>' not in st
    monofasico = _tabela_que_contem(html, "Cofins: desconsiderado — monofásico")
    for rotulo, texto in (
        ("Cofins", "Cofins: desconsiderado — monofásico (Res. CGSN 140, art. 25, §§ 6º e 7º, II)"),
        (
            "PIS/Pasep",
            "PIS/Pasep: desconsiderado — monofásico (Res. CGSN 140, art. 25, §§ 6º e 7º, II)",
        ),
    ):
        assert re.search(
            rf'<th scope="row">{re.escape(rotulo)}</th>\s*<td class="valor-monetario">—</td>\s*'
            rf'<td class="valor-monetario">desconsiderado</td>\s*<td>{re.escape(texto)}</td>',
            monofasico,
        ), rotulo
    assert '<td class="valor-monetario">0,00</td>' not in monofasico


def test_mercadoria_mostra_venda_bruta_devolucao_deduzida_e_receita_liquida_por_segmento(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    """Venda 100.000 e devolução 20.000 no mesmo segmento. Esperado (à mão): 100.000,00 bruto;
    20.000,00 deduzido; 80.000,00 líquido; total 4.256,00."""
    _cenario_devolucao(loja_a, escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, loja_a))

    assert "Venda, devolução e receita líquida de mercadoria" in html
    assert re.search(
        r'<td class="valor-monetario">100\.000,00</td>\s*'
        r'<td class="valor-monetario">20\.000,00</td>\s*'
        r'<td class="valor-monetario">80\.000,00</td>',
        html,
    )
    assert re.search(r'Total do pré-DAS</th>\s*<td class="valor-monetario">4\.256,00</td>', html)
    tabela = _tabela_que_contem(html, "Venda bruta, devolução deduzida e receita líquida")
    assert '<th scope="col">Devolução deduzida (R$)</th>' in tabela
    assert "<caption>" in tabela


def test_caso_f_mostra_exportacao_de_mercadoria_com_os_tributos_desconsiderados(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    _cenario_caso_f(loja_a, escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, loja_a))

    assert "Mercado interno: Anexo II" in html
    assert "Mercado externo (exportação de serviço e de mercadoria): Anexo II" in html
    assert "Exportação de mercadoria (mercado externo)" in html
    # Caso F, escrito à mão: normal 3.480,00; ST 591,60; exportação 418,50; total 4.490,10.
    assert re.search(
        r"Total da receita líquida de 40\.000,00 \(R\$\)</th>\s*<td></td>\s*"
        r'<td class="valor-monetario">3\.480,00</td>',
        html,
    )
    assert re.search(
        r"Total da receita líquida de 20\.000,00 \(R\$\)</th>\s*<td></td>\s*"
        r'<td class="valor-monetario">418,50</td>',
        html,
    )
    assert re.search(r'Total do pré-DAS</th>\s*<td class="valor-monetario">4\.490,10</td>', html)
    exportacao = _tabela_que_contem(html, "PIS/Pasep: desconsiderado — exportação")
    for rotulo in ("PIS/Pasep", "Cofins", "IPI", "ICMS"):
        assert re.search(
            rf'<th scope="row">{re.escape(rotulo)}</th>\s*<td class="valor-monetario">—</td>\s*'
            rf'<td class="valor-monetario">desconsiderado</td>\s*<td>{re.escape(rotulo)}: '
            r"desconsiderado — exportação \(Res\. CGSN 140, art\. 25, § 3º\)</td>",
            exportacao,
        ), rotulo
    assert '<td class="valor-monetario">0,00</td>' not in exportacao


def test_avisos_csosn_900_aparecem_sem_recusar_o_calculo(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    """Revenda de 100.000 com CSOSN 900: aviso, não recusa. Esperado (à mão): total 5.320,00."""
    janela(loja_a, usuario_gestor_a, ANO, MES, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=705,
        itens=[{"cfop": "5102", "vprod": "100000.00", "csosn": "900"}],
    )
    escriturar(loja_a, usuario_gestor_a, documento, {1: NF.REVENDA})
    confirmar_pa(loja_a, usuario_gestor_a, ANO, MES)
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, loja_a))

    assert "Avisos: não recusam o cálculo, mas conferir no PGDAS-D" in html
    assert "CSOSN 900 em nota 705 (CFOP 5102)" in html
    assert "Pré-DAS não calculado" not in html
    assert re.search(r'Total do pré-DAS</th>\s*<td class="valor-monetario">5\.320,00</td>', html)


# ---------------------------------------------------------------------------
# Pré-DAS: recusas nomeadas, com o texto do domínio (critério 1 e 5)
# ---------------------------------------------------------------------------


def test_anexo_da_mercadoria_a_confirmar_mostra_o_texto_do_dominio_e_leva_as_nfe(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    """Revenda com ST (natureza) e CFOP 5.949, que não decide o anexo: recusa nomeada, com a
    natureza e o CFOP, e link para a escrituração das NF-e."""
    janela(loja_a, usuario_gestor_a, ANO, MES, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=802,
        itens=[{"cfop": "5949", "vprod": "10000.00", "csosn": "500"}],
    )
    escriturar(loja_a, usuario_gestor_a, documento, {1: NF.REVENDA_ST_SUBSTITUIDO})
    confirmar_pa(loja_a, usuario_gestor_a, ANO, MES)
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, loja_a))

    assert "Pré-DAS não calculado em 06/2026" in html
    assert "anexo da mercadoria a confirmar (natureza revenda_st_substituido, CFOP 5949)" in html
    assert "Abrir as NF-e a escriturar" in html
    assert reverse("fiscal_web:nfe_a_escriturar") in html
    assert "Total do pré-DAS" not in html


def test_devolucao_sem_segmento_confirmado_recusa_o_mes_com_o_motivo_nomeado(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    janela(loja_a, usuario_gestor_a, ANO, MES, [25000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=321,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(loja_a, usuario_gestor_a, venda, {1: NF.REVENDA})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=322,
        itens=[{"cfop": "1202", "vprod": "20000.00"}],
        devolucao=True,
    )
    escriturar(loja_a, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_VENDA})
    confirmar_pa(loja_a, usuario_gestor_a, ANO, MES)
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, loja_a))

    assert "Devolução de venda sem segmento confirmado em 06/2026, nota(s) 322" in html
    assert "O pré-DAS não rateia a devolução (HI-129)." in html
    assert "Total do pré-DAS" not in html


def test_csosn_103_e_combustivel_recusam_com_o_texto_do_dominio(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    """Benefício de ICMS sem parâmetro (CSOSN 103, HI-131) e combustível para consumo (HI-132)."""
    janela(loja_a, usuario_gestor_a, ANO, MES, [25000] * 12)
    beneficio = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=601,
        itens=[{"cfop": "5102", "vprod": "1000.00", "csosn": "103"}],
    )
    escriturar(loja_a, usuario_gestor_a, beneficio, {1: NF.REVENDA})
    combustivel = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=602,
        itens=[{"cfop": "5656", "vprod": "2000.00"}],
    )
    escriturar(loja_a, usuario_gestor_a, combustivel, {1: NF.COMBUSTIVEL})
    confirmar_pa(loja_a, usuario_gestor_a, ANO, MES)
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, loja_a))

    assert "Item com benefício ou imunidade de ICMS sem parâmetro estadual em 06/2026" in html
    assert "nota 601 (CFOP 5102, CSOSN 103)" in html
    assert "combustível para consumo: ICMS fora do DAS e PIS/Cofins concentrados" in html
    assert "Total do pré-DAS" not in html


# ---------------------------------------------------------------------------
# Pré-DAS: critério 2 (mês só de serviço igual ao de antes) e estados
# ---------------------------------------------------------------------------


def test_mes_so_de_servico_nao_ganha_nenhum_elemento_de_mercadoria(
    client, usuario_gestor_a, empresa_a
):
    """A tela de serviço da DL-075 não ganha aviso, tabela de venda/devolução nem rótulo de
    mercadoria. Este teste prova a AUSÊNCIA desses elementos. A igualdade byte a byte do HTML com o
    de antes (sem o token CSRF e com espaços normalizados) foi conferida à parte, por comparação
    manual, e não é teste permanente."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, ANO, MES, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, ANO, MES, "100000.00")
    _logar(client, usuario_gestor_a)

    html = _texto(_pre_das(client, empresa))

    assert html.count("Mercado interno: Anexo III") == 1
    for elemento in (
        "Avisos: não recusam",
        "Venda, devolução e receita líquida de mercadoria",
        "Venda bruta, devolução deduzida",
        "desconsiderado — ",
        "Total da receita líquida de",
        "Normal (sem ST, monofásico nem exportação)",
    ):
        assert elemento not in html, elemento
    assert "Total da receita de 100.000,00 (R$)" in html


def test_sem_empresa_pede_a_escolha_e_erro_de_competencia_responde_400(
    client, usuario_gestor_a, empresa_a
):
    _logar(client, usuario_gestor_a)

    vazia = _texto(client.get(reverse("fiscal_web:pre_das")))
    assert "Escolha uma empresa para ver o pré-DAS do mês." in vazia

    # Empresa real, competência inválida: a recusa da entrada é 400, nunca 500.
    erro = client.get(
        reverse("fiscal_web:pre_das"), {"empresa": empresa_a.pk, "ano": ANO, "mes": 13}
    )
    assert erro.status_code == 400
    assert "Competência inválida: informe um ano (AAAA) e um mês (1 a 12) válidos." in _texto(erro)


def test_pre_das_permissoes_paralegal_consulta_cliente_nao_e_outro_escritorio_404(
    client, loja_a, escritorio_a, usuario_gestor_a, paralegal_a, cliente_a, empresa_b
):
    _cenario_devolucao(loja_a, escritorio_a, usuario_gestor_a)

    _logar(client, paralegal_a)
    assert _pre_das(client, loja_a).status_code == 200

    _logar(client, cliente_a)
    assert _pre_das(client, loja_a).status_code == 403

    _logar(client, usuario_gestor_a)
    assert _pre_das(client, empresa_b).status_code == 404


# ---------------------------------------------------------------------------
# Escrituração da NF-e: critério 3 (marca e segmento em rascunho) e 4 (permissões)
# ---------------------------------------------------------------------------


def test_gestor_grava_a_marca_de_monofasico_em_rascunho_e_desmarca(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=911,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = _rascunho(loja_a, usuario_gestor_a, venda, {1: NF.REVENDA})
    _logar(client, usuario_gestor_a)
    url = _url_escriturar(loja_a, venda)
    item = _id_do_item(venda, 1)

    marcou = client.post(url, {"acao": "monofasico", "item_id": item, "monofasico": "1"})

    assert marcou.status_code == 302
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).monofasico is True
    tela = _texto(client.get(url))
    assert 'name="monofasico" value="1" checked' in tela
    assert "Gravar marca" in tela

    desmarcou = client.post(
        url, {"acao": "monofasico", "item_id": item}
    )  # caixa desmarcada: sem campo
    assert desmarcou.status_code == 302
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).monofasico is False


def test_gestor_confirma_o_segmento_da_devolucao_com_a_sugestao_do_dominio(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    """Devolução de revenda (CFOP 1.202). O domínio sugere "revenda"; a tela mostra a sugestão, não
    pré-seleciona, e grava só a escolha do contador. Desfazer é o campo vazio."""
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=921,
        itens=[{"cfop": "1202", "vprod": "200.00"}],
        devolucao=True,
    )
    esc = _rascunho(loja_a, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_VENDA})
    _logar(client, usuario_gestor_a)
    url = _url_escriturar(loja_a, devolucao)
    item = _id_do_item(devolucao, 1)

    tela = _texto(client.get(url))
    assert "Sugestão: Devolução de revenda, Anexo I, sem ST nem monofásico." in tela
    assert "sugerida pelo CFOP 1202" in tela
    assert '<option value="" selected>Escolha o segmento</option>' in tela
    assert f'<option value="revenda">{SegmentoDevolucao.REVENDA.label}</option>' in tela

    client.post(url, {"acao": "segmento_devolucao", "item_id": item, "segmento": "revenda"})
    assert (
        NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).segmento_devolucao == "revenda"
    )
    tela = _texto(client.get(url))
    assert '<option value="revenda" selected>' in tela
    assert "Desfazer a confirmação" in tela

    client.post(url, {"acao": "segmento_devolucao", "item_id": item, "segmento": ""})
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).segmento_devolucao == ""


def test_segmento_fora_do_par_do_cfop_e_recusado_pelo_dominio_com_400(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    """Devolução de exportação exige CFOP 3.xxx. Com CFOP 1.202 o domínio recusa, sem gravar."""
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=931,
        itens=[{"cfop": "1202", "vprod": "200.00"}],
        devolucao=True,
    )
    esc = _rascunho(loja_a, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_VENDA})
    _logar(client, usuario_gestor_a)
    item = _id_do_item(devolucao, 1)

    resposta = client.post(
        _url_escriturar(loja_a, devolucao),
        {"acao": "segmento_devolucao", "item_id": item, "segmento": "revenda_exportacao"},
    )

    assert resposta.status_code == 400
    assert "Devolução de exportação tem CFOP 3.xxx" in _texto(resposta)
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).segmento_devolucao == ""


def test_entrada_estranha_responde_400_e_nao_grava_nada(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=941,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = _rascunho(loja_a, usuario_gestor_a, venda, {1: NF.REVENDA})
    _logar(client, usuario_gestor_a)
    url = _url_escriturar(loja_a, venda)
    item = _id_do_item(venda, 1)

    marca = client.post(url, {"acao": "monofasico", "item_id": item, "monofasico": "sim"})
    assert marca.status_code == 400
    assert "'Monofásico' aceita só marcada ou desmarcada." in _texto(marca)
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).monofasico is False


def test_marca_de_monofasico_so_vale_para_mercadoria(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=951,
        itens=[{"cfop": "1202", "vprod": "200.00"}],
        devolucao=True,
    )
    esc = _rascunho(loja_a, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_VENDA})
    _logar(client, usuario_gestor_a)
    item = _id_do_item(devolucao, 1)

    resposta = client.post(
        _url_escriturar(loja_a, devolucao),
        {"acao": "monofasico", "item_id": item, "monofasico": "1"},
    )

    assert resposta.status_code == 400
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).monofasico is False


def test_efetivada_fica_so_leitura_e_o_post_de_marca_e_recusado(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=961,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    escriturar(loja_a, usuario_gestor_a, venda, {1: NF.REVENDA}, marcas=[1])
    _logar(client, usuario_gestor_a)
    url = _url_escriturar(loja_a, venda)

    tela = _texto(client.get(url))

    assert "Marca de monofásico: sim." in tela
    assert 'name="acao" value="monofasico"' not in tela
    assert 'name="acao" value="segmento_devolucao"' not in tela
    resposta = client.post(url, {"acao": "monofasico", "item_id": _id_do_item(venda, 1)})
    assert resposta.status_code == 409
    assert "não é mais rascunho" in _texto(resposta)
    efetivada = EscrituracaoNFe.objects.get(vinculo=vinculo(venda, loja_a))
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert (
        NaturezaItemNFe.objects.get(
            escrituracao=efetivada, item_id=_id_do_item(venda, 1)
        ).monofasico
        is True
    )


def test_paralegal_ve_os_controles_desabilitados_com_motivo_e_o_post_responde_403(
    client, loja_a, escritorio_a, usuario_gestor_a, paralegal_a
):
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=971,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = _rascunho(loja_a, usuario_gestor_a, venda, {1: NF.REVENDA})
    _logar(client, paralegal_a)
    url = _url_escriturar(loja_a, venda)
    item = _id_do_item(venda, 1)

    resposta_de_consulta = client.get(url)
    tela = _texto(resposta_de_consulta)

    assert resposta_de_consulta.status_code == 200
    assert '<input type="checkbox" disabled' in tela
    assert "Seu papel consulta esta nota, mas não grava a marca de monofásico" in tela
    # Direção de arte §2.B: o botão aparece desabilitado com o motivo, e nunca some.
    assert f'disabled aria-describedby="id_motivo_marca_{item}">Gravar marca</button>' in tela
    assert 'name="acao" value="monofasico"' not in tela
    resposta = client.post(url, {"acao": "monofasico", "item_id": item, "monofasico": "1"})
    assert resposta.status_code == 403
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).monofasico is False


def test_paralegal_com_devolucao_ve_o_segmento_desabilitado_e_o_post_responde_403(
    client, loja_a, escritorio_a, usuario_gestor_a, paralegal_a
):
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=981,
        itens=[{"cfop": "1202", "vprod": "200.00"}],
        devolucao=True,
    )
    esc = _rascunho(loja_a, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_VENDA})
    _logar(client, paralegal_a)
    url = _url_escriturar(loja_a, devolucao)
    item = _id_do_item(devolucao, 1)

    tela = _texto(client.get(url))

    assert '<select id="id_segmento_' in tela
    assert f'id="id_segmento_{item}" disabled' in tela
    assert (
        f'disabled aria-describedby="id_motivo_segmento_{item}">Confirmar segmento</button>' in tela
    )
    assert 'name="acao" value="segmento_devolucao"' not in tela
    resposta = client.post(
        url, {"acao": "segmento_devolucao", "item_id": item, "segmento": "revenda"}
    )
    assert resposta.status_code == 403
    assert NaturezaItemNFe.objects.get(escrituracao=esc, item_id=item).segmento_devolucao == ""


def test_cliente_nao_acessa_a_escrituracao_nem_grava(
    client, loja_a, escritorio_a, usuario_gestor_a, cliente_a
):
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=991,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = _rascunho(loja_a, usuario_gestor_a, venda, {1: NF.REVENDA})
    _logar(client, cliente_a)
    url = _url_escriturar(loja_a, venda)

    assert client.get(url).status_code == 403
    assert (
        client.post(
            url, {"acao": "monofasico", "item_id": _id_do_item(venda, 1), "monofasico": "1"}
        ).status_code
        == 403
    )
    assert (
        NaturezaItemNFe.objects.get(escrituracao=esc, item_id=_id_do_item(venda, 1)).monofasico
        is False
    )


def test_nota_de_outro_escritorio_responde_404_na_tela_e_no_post(
    client, loja_a, escritorio_a, usuario_gestor_a, empresa_b
):
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=1001,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    _rascunho(loja_a, usuario_gestor_a, venda, {1: NF.REVENDA})
    _logar(client, usuario_gestor_a)
    url_de_outra_empresa = reverse(
        "fiscal_web:nfe_escriturar", args=[empresa_b.pk, vinculo(venda, loja_a).pk]
    )

    assert client.get(url_de_outra_empresa).status_code == 404
    assert (
        client.post(
            url_de_outra_empresa,
            {"acao": "monofasico", "item_id": _id_do_item(venda, 1), "monofasico": "1"},
        ).status_code
        == 404
    )


def test_tabela_de_itens_tem_legenda_cabecalhos_com_escopo_e_rotulos_dos_controles(
    client, loja_a, escritorio_a, usuario_gestor_a
):
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja_a,
        numero=1011,
        itens=[{"cfop": "1202", "vprod": "200.00"}],
        devolucao=True,
    )
    _rascunho(loja_a, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_VENDA})
    _logar(client, usuario_gestor_a)
    item = _id_do_item(devolucao, 1)

    html = _texto(client.get(_url_escriturar(loja_a, devolucao)))

    tabela = _tabela_que_contem(html, f'id="id_segmento_{item}"')
    assert "<caption>" in tabela
    assert '<th scope="col">Marca de monofásico e segmento da devolução</th>' in tabela
    assert f'<label for="id_segmento_{item}">Segmento da devolução do item 1</label>' in tabela
    assert f'aria-describedby="id_sugestao_segmento_{item}"' in tabela
    assert f'<p class="texto-apoio" id="id_sugestao_segmento_{item}">' in tabela
    assert_moldura_acessivel(html)


# ---------------------------------------------------------------------------
# Guardas de consistência: a tela não pode mentir sobre o domínio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("anexo", [ANEXO_I, ANEXO_II])
def test_mapa_de_desconsiderados_da_tela_confere_com_o_dominio_segmento_por_segmento(anexo):
    """Se o domínio mudar o que sai do DAS, este teste falha antes de a tela escrever um motivo
    errado. Cada tributo que o domínio desconsidera precisa de motivo e dispositivo."""
    for segmento in SEGMENTOS_DE_MERCADORIA:
        do_dominio = servico_pre_das._desconsiderados(anexo, segmento)
        na_tela = frozenset().union(
            *(tributos for tributos, _motivo, _disp in views_web._DESCONSIDERADOS_NA_TELA[segmento])
        )
        assert na_tela == do_dominio, (anexo, segmento)
        for tributo in do_dominio:
            situacao = views_web._situacao_do_desconsiderado(tributo, segmento)
            assert situacao.endswith(")"), (anexo, segmento, tributo, situacao)


def test_rotulos_cobrem_os_cinco_segmentos_de_mercadoria_do_dominio():
    assert set(views_web._ROTULO_DO_SEGMENTO_DE_MERCADORIA) == set(
        servico_pre_das._DISP_DO_SEGMENTO_DE_MERCADORIA
    )


def test_dispositivos_citados_na_tela_estao_no_texto_do_dominio():
    """O texto da tela cita o artigo; o do domínio precisa conter a mesma citação."""
    assert "art. 25, § 8º, I" in servico_pre_das.DISP_SEGREGACAO_ST
    assert "art. 25, §§ 6º e 7º, II" in servico_pre_das.DISP_SEGREGACAO_MONOFASICO
    assert "art. 25, § 3º" in servico_pre_das.DISP_EXPORTACAO
    assert views_web._DISP_DA_ST == "Res. CGSN 140, art. 25, § 8º, I"
    assert views_web._DISP_DO_MONOFASICO == "Res. CGSN 140, art. 25, §§ 6º e 7º, II"
    assert views_web._DISP_DA_EXPORTACAO == "Res. CGSN 140, art. 25, § 3º"


def test_externo_so_ganha_o_rotulo_de_mercadoria_quando_o_mes_tem_mercadoria():
    assert views_web._rotulo_do_mercado(MercadoReceita.EXTERNO, set()) == (
        "Mercado externo (exportação de serviço)"
    )
    assert views_web._rotulo_do_mercado(MercadoReceita.EXTERNO, {MercadoReceita.EXTERNO}) == (
        "Mercado externo (exportação de serviço e de mercadoria)"
    )
    assert views_web._rotulo_do_mercado(MercadoReceita.INTERNO, {MercadoReceita.EXTERNO}) == (
        "Mercado interno"
    )
