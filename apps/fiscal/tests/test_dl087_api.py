"""DL-087 (frente A), API da classificação: permissão no servidor (403), isolamento (404), contrato
(400), conflito (409), avisos, prévia de impacto que não grava, fila e regras do produto.

Critérios 4 (permissão e isolamento), 5 (recusas com mensagem) e 6 (fila, por API).
Dados sintéticos: NFC-e geradas pela recepção real (`suporte_dl085.nfce`).
"""

import json
from datetime import date

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal.models import RegraClassificacaoNFe
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.suporte_dl085 import CNPJ_SEGUNDA_EMPRESA, nfce
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

NCM_COMBUSTIVEL = "27101259"


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _ler(empresa):
    """Lê o mês em partes (como a tela faz) para que a fila e a prévia enxerguem as notas."""
    from apps.fiscal import escrituracao_nfe_lote as lote

    leitura = lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    assert leitura.terminou and not leitura.falhas_nesta_chamada, leitura


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _corpo(**campos):
    base = {
        "escopo": "escritorio",
        "tipo": "saida_propria",
        "cfop": "5102",
        "natureza": "revenda",
        "vigencia_inicio": "2026-03-01",
        "vigencia_fim": None,
        "ncm": "",
        "ncm_modo": "",
        "cst_csosn": "",
        "id_dest": "",
    }
    base.update(campos)
    return base


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-api-dl087")


@pytest.fixture
def analista(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.ANALISTA, "analista-api-dl087")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-api-dl087")


@pytest.fixture
def cliente(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-api-dl087")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-api-dl087")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto API DL087 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def vizinha(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Vizinha API DL087 Ltda", cnpj=CNPJ_SEGUNDA_EMPRESA
    )


@pytest.fixture
def empresa_b(escritorio_b):
    return Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B DL087 Ltda", cnpj="77888999000155"
    )


# ---------------------------------------------------------------------------
# Permissão (403) por papel e por escopo, no servidor
# ---------------------------------------------------------------------------


def test_cliente_recebe_403_em_tudo(client, cliente, empresa):
    client.force_login(cliente)
    assert client.get(_url("nfe_classificacao_regras", empresa.pk)).status_code == 403
    assert (
        client.get(_url("nfe_classificacao_fila", empresa.pk) + "?ano=2026&mes=3").status_code
        == 403
    )
    assert client.get(_url("nfe_classificacao_produto", empresa.pk)).status_code == 403
    assert _post(client, _url("nfe_classificacao_regras", empresa.pk), _corpo()).status_code == 403


def test_analista_cria_regra_de_empresa_e_nao_cria_regra_de_escritorio(client, analista, empresa):
    client.force_login(analista)
    recusada = _post(
        client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="escritorio")
    )
    assert recusada.status_code == 403
    assert "administrador e gestor" in recusada.json()["detail"]
    assert RegraClassificacaoNFe.objects.count() == 0
    aceita = _post(client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="empresa"))
    assert aceita.status_code == 201


def test_paralegal_le_a_fila_e_nao_cria_regra(client, paralegal, empresa):
    client.force_login(paralegal)
    assert (
        client.get(_url("nfe_classificacao_fila", empresa.pk) + "?ano=2026&mes=3").status_code
        == 200
    )
    resposta = _post(client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="empresa"))
    assert resposta.status_code == 403
    assert RegraClassificacaoNFe.objects.count() == 0


def test_gestor_cria_regra_de_escritorio_com_trilha(client, gestor, empresa):
    client.force_login(gestor)
    resposta = _post(
        client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="escritorio")
    )
    assert resposta.status_code == 201
    regra = resposta.json()["regra"]
    assert regra["escopo"] == "escritorio" and regra["empresa_id"] is None
    assert RegistroAuditoria.objects.filter(acao="classificacao_nfe.regra_criada").count() == 1


def test_analista_nao_desativa_regra_de_escritorio_e_gestor_desativa(
    client, analista, gestor, empresa
):
    client.force_login(gestor)
    criada = _post(
        client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="escritorio")
    )
    regra_id = criada.json()["regra"]["id"]
    client.force_login(analista)
    recusa = _post(
        client, _url("nfe_classificacao_regra_desativar", empresa.pk, regra_id), {"motivo": "não"}
    )
    assert recusa.status_code == 403
    client.force_login(gestor)
    feita = _post(
        client, _url("nfe_classificacao_regra_desativar", empresa.pk, regra_id), {"motivo": "fim"}
    )
    assert feita.status_code == 200
    assert feita.json()["regra"]["ativa"] is False


# ---------------------------------------------------------------------------
# Isolamento (404): outro escritório e outra empresa do mesmo escritório
# ---------------------------------------------------------------------------


def test_empresa_de_outro_escritorio_responde_404(client, gestor, empresa_b):
    client.force_login(gestor)
    assert client.get(_url("nfe_classificacao_regras", empresa_b.pk)).status_code == 404
    assert (
        _post(client, _url("nfe_classificacao_regras", empresa_b.pk), _corpo()).status_code == 404
    )


def test_regra_de_outro_escritorio_responde_404_ao_desativar(
    client, gestor, gestor_b, empresa, empresa_b
):
    client.force_login(gestor_b)
    criada = _post(
        client, _url("nfe_classificacao_regras", empresa_b.pk), _corpo(escopo="escritorio")
    )
    regra_b = criada.json()["regra"]["id"]
    client.force_login(gestor)
    resposta = _post(
        client, _url("nfe_classificacao_regra_desativar", empresa.pk, regra_b), {"motivo": "x"}
    )
    assert resposta.status_code == 404
    assert RegraClassificacaoNFe.objects.get(pk=regra_b).ativa


def test_regra_de_empresa_vizinha_responde_404_pela_outra_empresa(client, gestor, empresa, vizinha):
    """Mesmo escritório, empresa diferente: a regra da vizinha não aparece nem se desativa pela
    URL de `empresa` (IDOR)."""
    client.force_login(gestor)
    criada = _post(client, _url("nfe_classificacao_regras", vizinha.pk), _corpo(escopo="empresa"))
    regra_vizinha = criada.json()["regra"]["id"]
    assert (
        _post(
            client,
            _url("nfe_classificacao_regra_desativar", empresa.pk, regra_vizinha),
            {"motivo": "x"},
        ).status_code
        == 404
    )
    listagem = client.get(_url("nfe_classificacao_regras", empresa.pk)).json()["regras"]
    assert all(r["id"] != regra_vizinha for r in listagem)


def test_lista_da_empresa_traz_regras_do_escritorio_e_as_dela(client, gestor, empresa, vizinha):
    client.force_login(gestor)
    _post(client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="escritorio"))
    _post(
        client,
        _url("nfe_classificacao_regras", empresa.pk),
        _corpo(
            escopo="empresa",
            cfop="5656",
            natureza="combustivel",
            ncm=NCM_COMBUSTIVEL,
            ncm_modo="exato",
        ),
    )
    _post(
        client,
        _url("nfe_classificacao_regras", vizinha.pk),
        _corpo(escopo="empresa", cfop="5103", natureza="producao_propria"),
    )
    regras = client.get(_url("nfe_classificacao_regras", empresa.pk)).json()["regras"]
    assert {r["escopo"] for r in regras} == {"escritorio", "empresa"}
    assert len(regras) == 2


# ---------------------------------------------------------------------------
# Contrato (400), recusas com mensagem (critério 5) e duplicidade (409)
# ---------------------------------------------------------------------------


def test_campo_fora_do_contrato_e_400(client, gestor, empresa):
    client.force_login(gestor)
    resposta = _post(
        client, _url("nfe_classificacao_regras", empresa.pk), _corpo(valor_inventado=1)
    )
    assert resposta.status_code == 400


def test_combustivel_sem_ncm_e_400_com_mensagem(client, gestor, empresa):
    client.force_login(gestor)
    resposta = _post(
        client,
        _url("nfe_classificacao_regras", empresa.pk),
        _corpo(escopo="empresa", cfop="5656", natureza="combustivel"),
    )
    assert resposta.status_code == 400
    assert "exige NCM" in str(resposta.json())


def test_ajuste_e_cfop_fora_da_tabela_sao_400(client, gestor, empresa):
    client.force_login(gestor)
    url = _url("nfe_classificacao_regras", empresa.pk)
    assert (
        _post(client, url, _corpo(escopo="empresa", tipo="ajuste", natureza="ajuste")).status_code
        == 400
    )
    fora = _post(client, url, _corpo(escopo="empresa", cfop="5000"))
    assert fora.status_code == 400
    assert "fora da tabela oficial" in str(fora.json())


def test_duplicada_responde_409_com_a_regra_existente(client, gestor, empresa):
    client.force_login(gestor)
    url = _url("nfe_classificacao_regras", empresa.pk)
    _post(client, url, _corpo(escopo="empresa"))
    duplicada = _post(client, url, _corpo(escopo="empresa", vigencia_inicio="2026-06-01"))
    assert duplicada.status_code == 409
    assert "regra n.º" in duplicada.json()["detail"]


def test_regra_de_escritorio_com_cst_regime_normal_responde_com_aviso(client, gestor, empresa):
    client.force_login(gestor)
    resposta = _post(
        client,
        _url("nfe_classificacao_regras", empresa.pk),
        _corpo(escopo="escritorio", cst_csosn="00"),
    )
    assert resposta.status_code == 201
    assert any("Simples" in aviso for aviso in resposta.json()["avisos"])


def test_combustivel_com_prefixo_de_lubrificante_cria_e_avisa(client, gestor, empresa):
    client.force_login(gestor)
    resposta = _post(
        client,
        _url("nfe_classificacao_regras", empresa.pk),
        _corpo(
            escopo="empresa", cfop="5656", natureza="combustivel", ncm="2710", ncm_modo="prefixo"
        ),
    )
    assert resposta.status_code == 201
    assert any("lubrificante" in aviso for aviso in resposta.json()["avisos"])


def test_fim_anterior_ao_inicio_e_400(client, gestor, empresa):
    client.force_login(gestor)
    resposta = _post(
        client,
        _url("nfe_classificacao_regras", empresa.pk),
        _corpo(escopo="empresa", vigencia_inicio="2026-03-10", vigencia_fim="2026-03-09"),
    )
    assert resposta.status_code == 400


def test_desativar_sem_motivo_e_400_e_desativar_duas_vezes_e_409(client, gestor, empresa):
    client.force_login(gestor)
    regra_id = _post(
        client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="empresa")
    ).json()["regra"]["id"]
    url = _url("nfe_classificacao_regra_desativar", empresa.pk, regra_id)
    assert _post(client, url, {"motivo": ""}).status_code == 400
    assert _post(client, url, {"motivo": "troca"}).status_code == 200
    assert _post(client, url, {"motivo": "de novo"}).status_code == 409


# ---------------------------------------------------------------------------
# Prévia de impacto (critério 7 do plano; ajuste 7): conta, não grava
# ---------------------------------------------------------------------------


def test_previa_de_impacto_conta_sem_gravar_nada(client, gestor, empresa):
    """Três NFC-e de CFOP 5949 sem sinal (vão para a fila). Uma regra de empresa para 5949 tira as
    três da fila: a prévia conta isso, e nada é gravado."""
    for numero in (1, 2, 3):
        nfce(empresa.escritorio, gestor, numero=numero, cfop="5949", csosn="102", ncm="22030000")
    _ler(empresa)
    client.force_login(gestor)
    antes = RegraClassificacaoNFe.objects.count()
    resposta = _post(
        client,
        _url("nfe_classificacao_previa", empresa.pk),
        _corpo(escopo="empresa", cfop="5949", natureza="revenda", ano=2026, mes=3),
    )
    assert resposta.status_code == 200, resposta.content
    dados = resposta.json()
    assert dados["itens_a_escriturar"] == 3
    assert dados["itens_que_mudam"] == 3
    assert dados["itens_que_saem_da_fila"] == 3
    assert dados["itens_que_entram_na_fila"] == 0
    assert dados["grupos_afetados"] == 1
    assert dados["notas_afetadas"] == 3
    assert RegraClassificacaoNFe.objects.count() == antes
    assert RegistroAuditoria.objects.filter(acao="classificacao_nfe.regra_criada").count() == 0


def test_previa_de_impacto_com_criterios_invalidos_e_400(client, gestor, empresa):
    client.force_login(gestor)
    resposta = _post(
        client,
        _url("nfe_classificacao_previa", empresa.pk),
        _corpo(escopo="empresa", cfop="5656", natureza="combustivel", ano=2026, mes=3),
    )
    assert resposta.status_code == 400


def test_previa_exige_a_mesma_permissao_da_criacao(client, analista, empresa):
    client.force_login(analista)
    resposta = _post(
        client,
        _url("nfe_classificacao_previa", empresa.pk),
        _corpo(escopo="escritorio", ano=2026, mes=3),
    )
    assert resposta.status_code == 403


# ---------------------------------------------------------------------------
# Fila e regras do produto (leitura)
# ---------------------------------------------------------------------------


def test_fila_responde_os_campos_e_os_criterios_do_grupo(client, gestor, empresa):
    nfce(empresa.escritorio, gestor, numero=1, cfop="5949", csosn="102", ncm="22030000")
    _ler(empresa)
    client.force_login(gestor)
    corpo = client.get(_url("nfe_classificacao_fila", empresa.pk) + "?ano=2026&mes=3").json()
    assert corpo["quantidade_notas"] == 1
    (grupo,) = corpo["grupos"]
    assert grupo["cfop"] == "5949" and grupo["situacao"] == "sem_sugestao"
    assert grupo["criterios_da_regra"]["vigencia_inicio"] == "2026-03-01"
    assert grupo["criavel"] is True and grupo["pode_criar_regra_de_empresa"] is True


def test_fila_exige_ano_e_mes(client, gestor, empresa):
    client.force_login(gestor)
    assert client.get(_url("nfe_classificacao_fila", empresa.pk)).status_code == 400


def test_produto_devolve_as_regras_embutidas_so_leitura(client, gestor, empresa):
    client.force_login(gestor)
    corpo = client.get(_url("nfe_classificacao_produto", empresa.pk)).json()
    assert len(corpo["regras"]) >= 25
    assert all(linha["fonte"] for linha in corpo["regras"])
    assert _post(client, _url("nfe_classificacao_produto", empresa.pk), {}).status_code == 405


def test_lista_de_regras_informa_pesos_e_contagem_de_itens_confirmados(client, gestor, empresa):
    client.force_login(gestor)
    _post(client, _url("nfe_classificacao_regras", empresa.pk), _corpo(escopo="escritorio"))
    corpo = client.get(_url("nfe_classificacao_regras", empresa.pk)).json()
    assert corpo["pesos"]["cfop"] == 16
    assert corpo["regras"][0]["itens_confirmados"] == 0
    assert date(2026, 3, 1).isoformat() == corpo["regras"][0]["vigencia_inicio"]
