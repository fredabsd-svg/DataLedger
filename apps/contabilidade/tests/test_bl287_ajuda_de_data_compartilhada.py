"""BL-287 (etapa própria, depois da rodada 3 da DL-026): o mesmo arranjo de
ajuda de formato de data do Balancete (BL-277/BL-284) agora vale em Diário,
Razão e Lançamento.

**Isto NÃO é o mesmo requisito que
`test_dl017_rodada2_frontend.descricoes_de_data_sem_defesa` já cobre.**
Aquela guarda verifica um INVARIANTE de acessibilidade (todo campo de data
tem `aria-describedby` apontando para um elemento visível, com a classe
`texto-apoio`, que existe de verdade) e por DESENHO aceita as duas formas —
descrição própria por campo OU compartilhada entre campos — porque as duas
cumprem o requisito de acessibilidade igualmente bem. Ela continua sem
mudar (confirmado por leitura antes de tocar em qualquer template: BL-287
não pede uma guarda nova aqui, pede a MUDANÇA DE PADRÃO no produto).

O que faltava um teste para provar é mais estreito: que Diário e Razão
PASSARAM a usar o arranjo COMPARTILHADO (antes usavam um parágrafo por
campo, com o MESMO texto duas vezes — a causa física, nomeada no BL-277,
de o filtro comer altura demais) — e que Lançamento, que tem um único
campo de data (não dois, então não há o que compartilhar), passou a usar a
MESMA convenção visual (`ajuda-formato-data`) que as outras telas do
módulo, em vez de ficar com a única grafia diferente. A guarda genérica do
BL-284 não pode provar isto: um `aria-describedby` que aponta para um
elemento PRÓPRIO (não compartilhado) também passa nela — é exatamente o
comportamento antigo que este arquivo prova ter mudado.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.core.marcacao import tem_classe
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório BL-287", cnpj="11222333000144")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-287 Ltda", cnpj="22333444000155"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl287",
        email="gestora-bl287@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa}


def _login(client, cen):
    assert client.login(username="gestora-bl287", password="senha-forte-123")


# ---------------------------------------------------------------------------
# Detector — reutilizável pelo teste real e pelo de mutação
# ---------------------------------------------------------------------------


def _aria_describedby_de(html, id_campo):
    m = re.search(r'\bid="' + re.escape(id_campo) + r'"[^>]*\baria-describedby="([^"]*)"', html)
    assert m, f"#{id_campo}: sem aria-describedby no HTML renderizado"
    return m.group(1)


def campos_de_data_nao_compartilham_ajuda(html, id_a, id_b):
    """Devolve uma lista de problemas (vazia = os dois campos apontam para
    o MESMO parágrafo de ajuda, que existe e é visível). Distinto, de
    propósito, de `descricoes_de_data_sem_defesa` (BL-284): aquele aceita
    descrição própria OU compartilhada; este exige COMPARTILHADA — o
    requisito específico do BL-287 para Diário e Razão."""
    alvo_a = _aria_describedby_de(html, id_a)
    alvo_b = _aria_describedby_de(html, id_b)
    problemas = []
    if alvo_a != alvo_b:
        problemas.append(
            f"#{id_a} aponta para '#{alvo_a}' e #{id_b} aponta para '#{alvo_b}' — "
            "deveriam apontar para o MESMO parágrafo (arranjo compartilhado)"
        )
        return problemas
    # Um único elemento com esse id — não dois parágrafos de mesmo id (HTML
    # inválido) nem o alvo ausente.
    ocorrencias = len(re.findall(r'\bid="' + re.escape(alvo_a) + r'"', html))
    if ocorrencias != 1:
        problemas.append(f"'#{alvo_a}' aparece {ocorrencias} vezes no documento (esperado: 1)")
    m = re.search(r'<p\b([^>]*\bid="' + re.escape(alvo_a) + r'"[^>]*)>', html)
    if not m:
        problemas.append(f"'#{alvo_a}' não é um <p> (ou não foi encontrado)")
    elif not tem_classe(m.group(1), "ajuda-formato-data"):
        problemas.append(f"'#{alvo_a}' não tem a classe ajuda-formato-data")
    return problemas


def _elemento_por_id(html, alvo):
    m = re.search(r'<([a-zA-Z][\w-]*)\b([^>]*\bid="' + re.escape(alvo) + r'"[^>]*)>', html)
    return m.group(2) if m else None


# ---------------------------------------------------------------------------
# Diário e Razão: arranjo COMPARTILHADO (mesmo id_periodo_ajuda do Balancete)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_view,args_extra",
    [("diario", []), ("razao", ["caixa"])],
)
def test_campos_de_data_compartilham_um_unico_paragrafo_de_ajuda(
    client, cen, nome_view, args_extra
):
    _login(client, cen)
    args = [cen["empresa"].id] + [cen[nome].id for nome in args_extra]
    url = reverse(f"contabilidade_web:{nome_view}", args=args)
    html = client.get(url).content.decode()

    problemas = campos_de_data_nao_compartilham_ajuda(html, "id_inicio", "id_fim")
    assert not problemas, (nome_view, problemas)


def test_mutacao_revertendo_para_ajuda_propria_por_campo_e_detectada(client, cen):
    """Reproduz literalmente o desenho ANTERIOR ao BL-287 (o que o Diário e
    a Razão tinham antes desta etapa): cada campo com o PRÓPRIO parágrafo
    de ajuda, cada um com seu `id` e seu `aria-describedby`. Os dois
    parágrafos continuam válidos e visíveis — a guarda genérica do BL-284
    (`descricoes_de_data_sem_defesa`) continuaria satisfeita —, mas os
    campos deixam de compartilhar UM parágrafo só, que é o requisito
    específico que este arquivo prova.
    """
    _login(client, cen)
    url = reverse("contabilidade_web:diario", args=[cen["empresa"].id])
    html = client.get(url).content.decode()

    assert not campos_de_data_nao_compartilham_ajuda(html, "id_inicio", "id_fim"), (
        "controle: a página real não deveria ter problema nenhum"
    )

    # A mutação: troca o `aria-describedby` do campo "Fim" para um id NOVO,
    # e acrescenta um parágrafo PRÓPRIO com esse id (mesma classe e mesmo
    # texto do original) — exatamente a forma antiga, válida em
    # acessibilidade, mas não mais compartilhada.
    paragrafo_proprio = (
        '<p class="texto-apoio ajuda-formato-data" id="id_fim_ajuda_soltinha">'
        "O formato deste campo é o do seu navegador. Toda data exibida pelo sistema é dd/mm/aaaa."
        "</p>"
    )
    # Troca só a SEGUNDA ocorrência de aria-describedby="id_periodo_ajuda"
    # (a do campo "Fim") — a primeira (campo "Início") permanece intacta,
    # como continuaria acontecendo numa correção parcial de verdade.
    partes = html.split('aria-describedby="id_periodo_ajuda"')
    assert len(partes) == 3, "controle: esperava exatamente duas ocorrências no Diário"
    mutado = (
        partes[0]
        + 'aria-describedby="id_periodo_ajuda"'
        + partes[1]
        + 'aria-describedby="id_fim_ajuda_soltinha"'
        + partes[2].replace("</form>", paragrafo_proprio + "</form>", 1)
    )
    assert mutado != html, "controle: a mutação precisa mudar alguma coisa no HTML real"

    achados = campos_de_data_nao_compartilham_ajuda(mutado, "id_inicio", "id_fim")
    assert achados, (
        "a mutação (voltar a um parágrafo por campo) não foi detectada — a guarda não guarda"
    )
    assert any("deveriam apontar para o MESMO parágrafo" in a for a in achados), achados


# ---------------------------------------------------------------------------
# Lançamento: um único campo de data — não há o que compartilhar, mas a
# CONVENÇÃO visual (classe ajuda-formato-data) precisa ser a mesma.
# ---------------------------------------------------------------------------


def test_lancamento_tem_um_unico_campo_de_data_com_a_mesma_convencao_visual(client, cen):
    """Lançamento não tem dois campos de data para compartilhar ajuda — só
    "Data". O requisito aqui é outro: o parágrafo de ajuda usa a MESMA
    classe (`ajuda-formato-data`) que Diário, Razão e Balancete usam,
    fechando a diferença de CONVENÇÃO que existia antes desta etapa (só
    `texto-apoio`, sem a classe dedicada — ver o comentário em
    templates/contabilidade/lancamento_form.html sobre por que o ganho
    aqui é de 4px, não de linha)."""
    _login(client, cen)
    url = reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])
    html = client.get(url).content.decode()

    # Só existe UM campo de data nesta tela — controle de que a premissa
    # do teste (não há dois campos para comparar) continua verdadeira.
    assert html.count('type="date"') == 1, "controle: Lançamento deveria ter um único campo de data"

    alvo = _aria_describedby_de(html, "id_data")
    atributos = _elemento_por_id(html, alvo)
    assert atributos is not None, f"'#{alvo}' não existe no documento"
    assert tem_classe(atributos, "texto-apoio"), f"'#{alvo}' sem a classe texto-apoio"
    assert tem_classe(atributos, "ajuda-formato-data"), f"'#{alvo}' sem a classe ajuda-formato-data"


def test_mutacao_removendo_a_classe_ajuda_formato_data_do_lancamento_e_detectada(client, cen):
    """M6/BL-297 já ensinou, no arquivo irmão, que checagem por SUBSTRING
    de classe é a forma errada — repete aqui o mesmo cuidado: a mutação
    troca a classe por uma parecida (`ajuda-formato-data-legenda`), que um
    detector ingênuo por substring aceitaria, e `tem_classe` (casamento
    por TOKEN) precisa continuar reprovando.
    """
    _login(client, cen)
    url = reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])
    html = client.get(url).content.decode()

    assert 'class="texto-apoio ajuda-formato-data" id="id_data_ajuda"' in html, (
        "controle: a marcação esperada precisa estar presente no HTML real"
    )

    mutado = html.replace(
        'class="texto-apoio ajuda-formato-data" id="id_data_ajuda"',
        'class="texto-apoio ajuda-formato-data-legenda" id="id_data_ajuda"',
        1,
    )
    assert mutado != html, "controle: a mutação precisa mudar alguma coisa no HTML real"

    alvo = _aria_describedby_de(mutado, "id_data")
    atributos = _elemento_por_id(mutado, alvo)
    assert not tem_classe(atributos, "ajuda-formato-data"), (
        "a mutação (classe parecida por substring) não foi detectada — a guarda não guarda"
    )


# ---------------------------------------------------------------------------
# Controle positivo do detector — sintético, sem banco
# ---------------------------------------------------------------------------


def test_controle_positivo_campos_de_data_nao_compartilham_ajuda():
    compartilhado = (
        '<input id="id_inicio" aria-describedby="id_periodo_ajuda">'
        '<input id="id_fim" aria-describedby="id_periodo_ajuda">'
        '<p class="texto-apoio ajuda-formato-data" id="id_periodo_ajuda">ajuda</p>'
    )
    proprio = (
        '<input id="id_inicio" aria-describedby="id_inicio_ajuda">'
        '<input id="id_fim" aria-describedby="id_fim_ajuda">'
        '<p class="texto-apoio" id="id_inicio_ajuda">ajuda</p>'
        '<p class="texto-apoio" id="id_fim_ajuda">ajuda</p>'
    )
    assert not campos_de_data_nao_compartilham_ajuda(compartilhado, "id_inicio", "id_fim")
    assert campos_de_data_nao_compartilham_ajuda(proprio, "id_inicio", "id_fim")
