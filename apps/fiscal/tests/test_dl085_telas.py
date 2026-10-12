"""DL-085, frente B: tela "Escriturar o mês em lote" (rota `fiscal_web:nfe_lote`).

Cenário sintético (`suporte_dl085`): 3 NFC-e de combustível (CFOP 5656, 390,00), 2 de revenda
(CFOP 5102, 160,00) e 1 sem sugestão de natureza (CFOP 5949, 100,00), que fica FORA do lote. Os
valores esperados estão escritos à mão aqui, não copiados do código.

O que a tela faz é conferido pelo HTML e pelo banco. A regra (prévia, assinatura, efetivação) já
tem testes na frente A (`test_dl085_api.py`, `test_dl085_partes.py`, ...): aqui se confere só o que
o contador vê e o que a tela manda ao serviço.

A confirmação é por grupo (DL-085, frente A, grupos): a caixa "incluir este grupo" manda só os
grupos marcados ao serviço. O grupo desmarcado fica intacto (ver o teste de grupo desmarcado).
"""

import re
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import escrituracao_nfe_lote as servico_lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    LeituraItensNFe,
    LoteEscrituracaoNFe,
    NaturezaItemNFe,
)
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_dl085 import nfce, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 3
CHAVE_COMBUSTIVEL = "5656|500|combustivel"
NATUREZA_DO_POSTO = "combustivel_revenda"


# ---------------------------------------------------------------------------
# Cenário e auxiliares
# ---------------------------------------------------------------------------


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-telas-dl085")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-telas-dl085")


@pytest.fixture
def cliente(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-telas-dl085")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-telas-dl085")


@pytest.fixture
def posto(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Telas DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def vizinha(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Vizinha Telas DL085 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _cenario(escritorio, usuario, empresa):
    """3 de combustível, 2 de revenda e 1 sem sugestão (fora). Devolve o vínculo da nota de fora."""
    for numero, valor in ((1, "100.00"), (2, "250.00"), (3, "40.00")):
        nfce(escritorio, usuario, numero=numero, valor=valor)
    for numero in (4, 5):
        nfce(escritorio, usuario, numero=numero, valor="80.00", cfop="5102", csosn="102")
    fora = nfce(escritorio, usuario, numero=9, cfop="5949", csosn="102")
    return vinculo(fora, empresa)


def _url(empresa, ano=ANO, mes=MES):
    return reverse("fiscal_web:nfe_lote", args=[empresa.pk]) + f"?ano={ano}&mes={mes}"


def _post(client, empresa, dados, **kwargs):
    return client.post(reverse("fiscal_web:nfe_lote", args=[empresa.pk]), dados, **kwargs)


def _html(resposta):
    return resposta.content.decode("utf-8")


def _assinatura(html):
    return re.search(r'name="assinatura" value="([0-9a-f]{64})"', html).group(1)


def _ler_tudo(client, empresa):
    """Um POST de leitura (o limite padrão cobre o mês de teste)."""
    resposta = _post(client, empresa, {"acao": "ler", "ano": ANO, "mes": MES})
    assert resposta.status_code == 302
    return resposta


def _dados_de_confirmacao(html, *, escolhas=None, excluir=()):
    """Monta o POST de confirmação como o formulário montaria, a partir do HTML da prévia."""
    chaves = re.findall(r'<input type="hidden" name="grupo" value="([^"]+)"', html)
    dados = {
        "acao": "confirmar",
        "ano": ANO,
        "mes": MES,
        "assinatura": _assinatura(html),
        "grupo": chaves,
        "incluir": [chave for chave in chaves if chave not in excluir],
    }
    for chave in chaves:
        dados[f"assinatura_{chave}"] = re.findall(
            rf'name="assinatura_{re.escape(chave)}" value="([^"]+)"', html
        )
        dados[f"escolha_{chave}"] = (escolhas or {}).get(chave, "")
    return dados


def _chave_do_grupo_com(html, combinacao):
    """Chave do grupo cujas combinações incluem a `combinacao` (id "CFOP|CST|natureza")."""
    for chave in re.findall(r'<input type="hidden" name="grupo" value="([^"]+)"', html):
        if re.search(
            rf'name="assinatura_{re.escape(chave)}" value="{re.escape(combinacao)}"', html
        ):
            return chave
    raise AssertionError(f"grupo com {combinacao} não está na prévia")


def _lote_id(html):
    return re.search(r'name="lote_id" value="(\d+)"', html).group(1)


def _efetivadas(empresa):
    return EscrituracaoNFe.objects.filter(
        empresa=empresa, estado=EstadoEscrituracao.EFETIVADA
    ).count()


def _rotulos_das_caixas_e_seletores_estao_ligados(html):
    """Cada caixa e cada seletor tem um <label for=> que aponta para o próprio campo."""
    ids = re.findall(r'<(?:input type="checkbox"|select) id="([^"]+)"', html)
    assert ids, "a prévia deveria ter caixas ou seletores"
    for campo in ids:
        assert f'for="{campo}"' in html, f"campo {campo} sem <label> ligado"


# ---------------------------------------------------------------------------
# Critério 1 — a tela mostra "a ler", os grupos, o fora do lote com motivo e link
# ---------------------------------------------------------------------------


def test_a_ler_aparece_antes_de_qualquer_leitura(escritorio_a, gestor, posto, client):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)

    html = _html(client.get(_url(posto)))

    assert "6 nota(s) ainda não lida(s)" in html
    assert "Ler as próximas 6" in html
    assert "Prévia por grupo" not in html


def test_depois_de_ler_mostra_grupos_fora_do_lote_com_motivo_e_link(
    escritorio_a, gestor, posto, client
):
    fora = _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)

    html = _html(client.get(_url(posto)))

    assert "Prévia por grupo" in html
    assert "Todas as notas do mês já foram lidas" in html
    # Grupos: a combinação de cada um, o número de notas e o valor de receita em pt-BR.
    assert "5656" in html and "5102" in html
    assert "390,00" in html and "160,00" in html
    # Fora do lote: uma nota, com o motivo nomeado e o link para a escrituração individual.
    assert "Fora do lote: 1 nota(s)" in html
    assert "Sem sugestão de natureza" in html
    assert "sem sinal suficiente" in html
    assert reverse("fiscal_web:nfe_escriturar", args=[posto.pk, fora.pk]) in html
    assert "100,00" in html
    # Acessibilidade: legenda e cabeçalho com escopo em cada tabela; rótulos ligados aos campos.
    assert "<caption>" in html
    assert '<th scope="col">' in html
    _rotulos_das_caixas_e_seletores_estao_ligados(html)
    assert_moldura_acessivel(html)


def test_empresa_sem_notas_mostra_estado_vazio(escritorio_a, gestor, posto, client):
    client.force_login(gestor)

    html = _html(client.get(_url(posto)))

    assert "Nada a escriturar em 03/2026" in html
    assert "Prévia por grupo" not in html


def test_links_de_entrada_na_lista_e_na_conferencia(escritorio_a, gestor, posto, client):
    client.force_login(gestor)
    link = reverse("fiscal_web:nfe_lote", args=[posto.pk]) + "?ano=2026&amp;mes=3"

    lista = _html(
        client.get(reverse("fiscal_web:nfe_a_escriturar") + f"?empresa={posto.pk}&ano=2026&mes=3")
    )
    conferencia = _html(
        client.get(reverse("fiscal_web:nfe_conferencia") + f"?empresa={posto.pk}&ano=2026&mes=3")
    )

    assert link in lista
    assert link in conferencia


# ---------------------------------------------------------------------------
# Critério 2 — ler em partes pela tela até zerar
# ---------------------------------------------------------------------------


def test_ler_em_partes_pela_tela_ate_zerar(escritorio_a, gestor, posto, client, monkeypatch):
    # Limite de 2 notas por clique: 6 notas levam 3 cliques. O valor é o do domínio, lido na hora.
    monkeypatch.setattr(servico_lote, "LIMITE_PADRAO_DA_LEITURA", 2)
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)

    html = _html(client.get(_url(posto)))
    assert "Ler as próximas 2" in html

    resposta = _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES}, follow=True)
    html = _html(resposta)
    assert "lidas 2 nota(s); restam 4 a ler" in html
    assert "4 nota(s) ainda não lida(s)" in html

    _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES}, follow=True)
    resposta = _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES}, follow=True)
    html = _html(resposta)
    assert "restam 0 a ler" in html
    assert "Todas as notas do mês já foram lidas" in html
    assert "Prévia por grupo" in html


# ---------------------------------------------------------------------------
# Critério 3 — confirmar efetiva as notas dos grupos marcados, e só eles
# ---------------------------------------------------------------------------


def test_confirmar_com_todos_os_grupos_efetiva_as_notas_do_lote_e_so_elas(
    escritorio_a, gestor, posto, client
):
    fora = _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    html = _html(client.get(_url(posto)))

    resposta = _post(client, posto, _dados_de_confirmacao(html), follow=True)

    assert resposta.status_code == 200
    assert "Lote concluído" in _html(resposta)
    assert _efetivadas(posto) == 5
    assert not EscrituracaoNFe.objects.filter(vinculo=fora).exists()
    assert LoteEscrituracaoNFe.objects.filter(empresa=posto).count() == 1


def _chave_do_grupo_com(html, combinacao):
    """Chave do grupo cuja lista de combinações do formulário traz `combinacao` (5656|500|...)."""
    for chave, valor in re.findall(r'name="assinatura_([^"]+)" value="([^"]+)"', html):
        if valor == combinacao:
            return chave
    raise AssertionError(f"grupo com {combinacao} não está na prévia")


def test_grupo_desmarcado_fica_intacto_e_os_marcados_sao_efetivados(
    escritorio_a, gestor, posto, client
):
    """Confirmação por grupo: o de combustível fica desmarcado, e suas 3 notas não ganham rascunho
    nem escrituração. O de revenda (2 notas) é efetivado, e o lote só registra esse grupo."""
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    html = _html(client.get(_url(posto)))
    combustivel = _chave_do_grupo_com(html, CHAVE_COMBUSTIVEL)

    resposta = _post(client, posto, _dados_de_confirmacao(html, excluir=[combustivel]), follow=True)

    assert resposta.status_code == 200
    assert "Lote concluído" in _html(resposta)
    assert _efetivadas(posto) == 2
    numeros_do_grupo_desmarcado = [1, 2, 3]
    assert not EscrituracaoNFe.objects.filter(
        empresa=posto, vinculo__documento__numero__in=[str(n) for n in numeros_do_grupo_desmarcado]
    ).exists()
    lote = LoteEscrituracaoNFe.objects.get(empresa=posto)
    assert servico_lote.resumo_do_lote(lote)["grupos"] == [
        chave
        for chave in re.findall(r'<input type="hidden" name="grupo" value="([^"]+)"', html)
        if chave != combustivel
    ]


# ---------------------------------------------------------------------------
# Critério 4 — assinatura desatualizada: mensagem, prévia recarregada, nada efetivado
# ---------------------------------------------------------------------------


def test_assinatura_desatualizada_mostra_a_mensagem_recarrega_a_previa_e_nada_efetiva(
    escritorio_a, gestor, posto, client
):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    antiga = _html(client.get(_url(posto)))
    dados = _dados_de_confirmacao(antiga)
    nfce(escritorio_a, gestor, numero=6, valor="10.00")  # a prévia muda depois de exibida

    resposta = _post(client, posto, dados)

    html = _html(resposta)
    assert resposta.status_code == 409
    assert "A prévia mudou" in html
    assert "Nada foi efetivado" in html
    # A tela recarregou a prévia de agora: a nota nova aparece como "a ler", e a assinatura é outra.
    assert "1 nota(s) ainda não lida(s)" in html
    nova = servico_lote.previa_do_lote(posto, ANO, MES).assinatura
    assert nova != dados["assinatura"]
    assert _efetivadas(posto) == 0
    assert not LoteEscrituracaoNFe.objects.filter(empresa=posto).exists()


# ---------------------------------------------------------------------------
# Critério 5 — continuar processa as partes até concluir, sem duplicar
# ---------------------------------------------------------------------------


def test_continuar_processa_as_partes_ate_concluir_sem_duplicar(
    escritorio_a, gestor, posto, client, monkeypatch
):
    monkeypatch.setattr(servico_lote, "LIMITE_PADRAO_DA_PARTE", 2)
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    html = _html(client.get(_url(posto)))

    html = _html(_post(client, posto, _dados_de_confirmacao(html), follow=True))
    assert "Lote em andamento" in html
    assert "Efetivadas <strong>2</strong>, restam <strong>3</strong>" in html
    lote = _lote_id(html)

    continuar = {"acao": "continuar", "ano": ANO, "mes": MES, "lote_id": lote}
    html = _html(_post(client, posto, continuar, follow=True))
    assert "Efetivadas <strong>4</strong>, restam <strong>1</strong>" in html

    html = _html(_post(client, posto, continuar, follow=True))
    assert "Lote concluído" in html
    assert "<strong>5</strong> efetivada(s)" in html

    # Repetir depois de concluído não processa nada: nenhuma escrituração a mais.
    html = _html(_post(client, posto, continuar, follow=True))
    assert "Lote concluído" in html
    assert _efetivadas(posto) == 5
    assert EscrituracaoNFe.objects.filter(empresa=posto).count() == 5
    assert LoteEscrituracaoNFe.objects.filter(empresa=posto).count() == 1


def test_lote_em_andamento_aparece_na_previa_e_nao_oferece_confirmar_outro(
    escritorio_a, gestor, posto, client, monkeypatch
):
    monkeypatch.setattr(servico_lote, "LIMITE_PADRAO_DA_PARTE", 2)
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    _post(client, posto, _dados_de_confirmacao(_html(client.get(_url(posto)))), follow=True)

    html = _html(client.get(_url(posto)))

    assert "Lote em andamento neste mês" in html
    assert "Continuar o lote: próxima parte" in html
    assert "Confirmar o lote:" not in html


# ---------------------------------------------------------------------------
# Critério 6 — escolha de outra natureza é aplicada
# ---------------------------------------------------------------------------


def test_escolha_de_outra_natureza_para_um_grupo_e_aplicada(escritorio_a, gestor, posto, client):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    html = _html(client.get(_url(posto)))
    grupo = _chave_do_grupo_com(html, CHAVE_COMBUSTIVEL)

    resposta = _post(
        client,
        posto,
        _dados_de_confirmacao(html, escolhas={grupo: NATUREZA_DO_POSTO}),
        follow=True,
    )

    assert resposta.status_code == 200
    assert _efetivadas(posto) == 5
    trocadas = NaturezaItemNFe.objects.filter(
        escrituracao__empresa=posto, natureza=NATUREZA_DO_POSTO
    )
    assert trocadas.count() == 3  # só as três de combustível
    assert (
        NaturezaItemNFe.objects.filter(escrituracao__empresa=posto, natureza="revenda").count() == 2
    )


def test_natureza_que_nao_cabe_no_grupo_e_recusada_sem_efetivar(
    escritorio_a, gestor, posto, client
):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    html = _html(client.get(_url(posto)))
    grupo = _chave_do_grupo_com(html, CHAVE_COMBUSTIVEL)

    resposta = _post(
        client,
        posto,
        _dados_de_confirmacao(html, escolhas={grupo: "natureza_que_nao_existe"}),
    )

    assert resposta.status_code == 400
    assert "não cabe neste grupo" in _html(resposta)
    assert _efetivadas(posto) == 0


# ---------------------------------------------------------------------------
# Progresso com falha: a tela mostra a nota e o motivo (falha simulada no serviço de efetivação)
# ---------------------------------------------------------------------------


def test_progresso_mostra_a_falha_com_o_motivo_e_a_nota(escritorio_a, gestor, posto, client):
    """Falha de sistema SIMULADA numa nota (teste): o serviço de efetivação recusa uma nota, e a
    tela precisa dizer qual e por quê. As demais são efetivadas."""
    fora = _cenario(escritorio_a, gestor, posto)
    alvo = vinculo(
        nfce(escritorio_a, gestor, numero=7, valor="60.00"),
        posto,
    )
    client.force_login(gestor)
    _ler_tudo(client, posto)
    html = _html(client.get(_url(posto)))
    original = servico_nfe.efetivar

    def efetivar_com_falha(escrituracao, **kwargs):
        if escrituracao.vinculo_id == alvo.pk:
            raise servico_nfe.EscrituracaoNFeErro("Falha simulada nesta nota (teste).")
        return original(escrituracao, **kwargs)

    with mock.patch.object(servico_nfe, "efetivar", side_effect=efetivar_com_falha):
        resposta = _post(client, posto, _dados_de_confirmacao(html), follow=True)

    html = _html(resposta)
    assert "Lote concluído" in html
    assert "<strong>1</strong> falha(s)" in html
    assert "nº 7, série 1" in html
    assert "Falha simulada nesta nota (teste)." in html
    assert reverse("fiscal_web:nfe_escriturar", args=[posto.pk, alvo.pk]) in html
    assert not EscrituracaoNFe.objects.filter(vinculo=alvo).exists()
    assert not EscrituracaoNFe.objects.filter(vinculo=fora).exists()


# ---------------------------------------------------------------------------
# Critério 7 — permissões, isolamento e entrada
# ---------------------------------------------------------------------------


MOTIVO_SEM_ESCRITA = "Seu papel só consulta: ler e confirmar o lote é de quem escritura."


def _botao_desabilitado(html, texto):
    """(id do motivo, texto do motivo) do botão desabilitado cujo rótulo começa com `texto`.

    A direção de arte (§2.B) pede o botão visível e desabilitado, com o motivo LIGADO a ele."""
    padrao = (
        r'<button type="button" class="[^"]*" disabled aria-describedby="([^"]+)">\s*'
        + re.escape(texto)
    )
    achado = re.search(padrao, html)
    assert achado, f"botão desabilitado '{texto}' não está na tela"
    id_motivo = achado.group(1)
    motivo = re.search(r'<p id="' + re.escape(id_motivo) + r'" class="[^"]*">([^<]*)</p>', html)
    assert motivo, f"o motivo '{id_motivo}' do botão não existe na tela"
    return id_motivo, motivo.group(1)


def test_paralegal_ve_botoes_desabilitados_com_o_motivo_e_o_post_e_recusado(
    escritorio_a, gestor, paralegal, posto, client
):
    """PARALEGAL consulta: "Ler as próximas" e "Confirmar" aparecem DESABILITADOS, com o
    motivo ligado por aria-describedby. Nenhum formulário de escrita; o POST segue em 403."""
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    gestor_html = _html(client.get(_url(posto)))  # a prévia com o mês lido, para montar o POST
    nfce(escritorio_a, gestor, numero=6, valor="10.00")  # uma nota nova, ainda não lida
    client.force_login(paralegal)

    resposta = client.get(_url(posto))
    html = _html(resposta)

    assert resposta.status_code == 200
    assert "Prévia por grupo" in html
    assert "Fora do lote: 1 nota(s)" in html
    assert 'name="acao" value="confirmar"' not in html
    assert 'name="acao" value="ler"' not in html
    assert 'name="assinatura"' not in html
    assert html.count('id="id_motivo_sem_escrita"') == 1
    for texto in ("Ler as próximas 1", "Confirmar o lote: 5 nota(s) em 2 grupo(s)"):
        id_motivo, motivo = _botao_desabilitado(html, texto)
        assert id_motivo == "id_motivo_sem_escrita"
        assert motivo == MOTIVO_SEM_ESCRITA

    recusado = _post(client, posto, _dados_de_confirmacao(gestor_html))
    assert recusado.status_code == 403
    assert _efetivadas(posto) == 0
    assert not LoteEscrituracaoNFe.objects.filter(empresa=posto).exists()


def test_paralegal_ve_continuar_desabilitado_com_o_motivo_no_lote_em_andamento(
    escritorio_a, gestor, paralegal, posto, client
):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    previa = servico_lote.previa_do_lote(posto, ANO, MES)
    servico_lote.confirmar_lote(posto, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    client.force_login(paralegal)

    html = _html(client.get(_url(posto)))

    id_motivo, motivo = _botao_desabilitado(html, "Continuar o lote: próxima parte")
    assert (id_motivo, motivo) == ("id_motivo_sem_escrita", MOTIVO_SEM_ESCRITA)
    assert 'name="acao" value="continuar"' not in html


def test_paralegal_nao_le_as_notas_pelo_post(escritorio_a, gestor, paralegal, posto, client):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(paralegal)
    antes = LeituraItensNFe.objects.count()

    resposta = _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES})

    assert resposta.status_code == 403
    assert LeituraItensNFe.objects.count() == antes
    # A tela confirma o mesmo: as seis notas continuam "a ler".
    assert "6 nota(s) ainda não lida(s)" in _html(client.get(_url(posto)))


def test_cliente_recebe_403_na_tela_e_no_post(escritorio_a, gestor, cliente, posto, client):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(cliente)

    assert client.get(_url(posto)).status_code == 403
    assert _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES}).status_code == 403


def test_anonimo_vai_para_o_login(posto, client):
    resposta = client.get(_url(posto))

    assert resposta.status_code == 302
    assert "login" in resposta["Location"]


def test_empresa_de_outro_escritorio_responde_404_na_tela_e_no_post(
    escritorio_a, gestor, gestor_b, posto, client
):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor_b)

    assert client.get(_url(posto)).status_code == 404
    assert _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES}).status_code == 404


def test_continuar_lote_de_outra_empresa_responde_404_e_nao_mexe_no_lote(
    escritorio_a, gestor, posto, vizinha, client, monkeypatch
):
    monkeypatch.setattr(servico_lote, "LIMITE_PADRAO_DA_PARTE", 2)
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    _ler_tudo(client, posto)
    html = _html(
        _post(client, posto, _dados_de_confirmacao(_html(client.get(_url(posto)))), follow=True)
    )
    lote = _lote_id(html)
    andamento = LoteEscrituracaoNFe.objects.get(pk=lote)

    resposta = _post(
        client,
        vizinha,
        {"acao": "continuar", "ano": ANO, "mes": MES, "lote_id": lote},
    )

    assert resposta.status_code == 404
    andamento.refresh_from_db()
    assert andamento.estado == "em_andamento"


def test_post_sem_token_csrf_e_recusado(escritorio_a, gestor, posto):
    _cenario(escritorio_a, gestor, posto)
    cliente_com_csrf = Client(enforce_csrf_checks=True)
    cliente_com_csrf.force_login(gestor)

    resposta = _post(cliente_com_csrf, posto, {"acao": "ler", "ano": ANO, "mes": MES})

    assert resposta.status_code == 403


# ---------------------------------------------------------------------------
# Entrada estranha: 400, nunca 500
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dados,trecho",
    [
        pytest.param({"acao": "apagar", "ano": ANO, "mes": MES}, "Ação desconhecida", id="acao"),
        pytest.param({"acao": "ler", "ano": ANO, "mes": 13}, "Mês", id="mes"),
        pytest.param({"acao": "ler", "ano": "abc", "mes": MES}, "Ano", id="ano-nao-numero"),
        pytest.param({"acao": "ler", "ano": ANO, "mes": MES, "campo": "x"}, "campo", id="campo"),
        pytest.param(
            {"acao": "confirmar", "ano": ANO, "mes": MES, "grupo": ["invasao"]},
            "Grupo desconhecido",
            id="grupo-fora-do-formato",
        ),
        pytest.param(
            {
                "acao": "confirmar",
                "ano": ANO,
                "mes": MES,
                "assinatura": "a" * 64,
                "grupo": ["saida_propria-0123456789abcdef"],
                "escolha_saida_propria-0123456789abcdef": "x",
                "assinatura_saida_propria-0123456789abcdef": ["5656|500|x"],
                "incluir": ["grupo-que-nao-existe-0000"],
            },
            "Grupo desconhecido",
            id="incluir-grupo-que-nao-existe",
        ),
    ],
)
def test_entrada_estranha_responde_400_sem_gravar(
    escritorio_a, gestor, posto, client, dados, trecho
):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)

    resposta = _post(client, posto, dados)

    assert resposta.status_code == 400
    assert trecho in _html(resposta)
    assert _efetivadas(posto) == 0
    assert not LoteEscrituracaoNFe.objects.filter(empresa=posto).exists()


def test_ano_e_mes_fora_do_formato_na_consulta_respondem_400(escritorio_a, gestor, posto, client):
    client.force_login(gestor)

    assert (
        client.get(reverse("fiscal_web:nfe_lote", args=[posto.pk]) + "?ano=2026&mes=13").status_code
        == 400
    )
    assert (
        client.get(reverse("fiscal_web:nfe_lote", args=[posto.pk]) + "?ano=x&mes=3").status_code
        == 400
    )
