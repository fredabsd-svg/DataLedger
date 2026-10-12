"""DL-084, item 6 (HI-136): parâmetros por empresa, e o padrão de combustível na sugestão de
natureza.

Critério 6: parâmetros com trilha, isolamento e permissão no servidor; empresa nova abre em três
quotas. Os CFOP e NCM usados são exemplos sintéticos da tabela oficial já versionada no projeto.
"""

import json
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao_nfe as nfe
from apps.fiscal import presumido as servico
from apps.fiscal.models import NaturezaOperacaoNFe
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _url(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}/presumido/parametros/"


# ---------------------------------------------------------------------------
# Serviço: padrão, trilha e isolamento
# ---------------------------------------------------------------------------


def test_empresa_nova_abre_em_tres_quotas_e_sem_padrao_de_combustivel(empresa_a):
    padrao = servico.parametros_da_empresa(empresa_a)
    assert padrao == servico.ParametrosDaEmpresa("tres_quotas", "", False)


def test_gravar_parametros_deixa_trilha_com_antes_e_depois(empresa_a, usuario_gestor_a):
    gravado = servico.definir_parametros(
        empresa_a,
        {"forma_recolhimento": "quota_unica", "padrao_combustivel": "posto"},
        usuario_gestor_a,
    )
    assert gravado == servico.ParametrosDaEmpresa("quota_unica", "posto", True)
    registro = RegistroAuditoria.objects.get(acao="presumido.parametros_definidos")
    assert registro.detalhes["antes"] == {
        "forma_recolhimento": "tres_quotas",
        "padrao_combustivel": "",
    }
    assert registro.detalhes["depois"] == {
        "forma_recolhimento": "quota_unica",
        "padrao_combustivel": "posto",
    }


def test_campo_ausente_mantem_o_valor_atual(empresa_a, usuario_gestor_a):
    servico.definir_parametros(empresa_a, {"padrao_combustivel": "trr"}, usuario_gestor_a)
    atual = servico.definir_parametros(
        empresa_a, {"forma_recolhimento": "duas_quotas"}, usuario_gestor_a
    )
    assert atual == servico.ParametrosDaEmpresa("duas_quotas", "trr", True)


def test_mesmo_valor_nao_grava_nova_trilha(empresa_a, usuario_gestor_a):
    servico.definir_parametros(empresa_a, {"padrao_combustivel": "posto"}, usuario_gestor_a)
    servico.definir_parametros(empresa_a, {"padrao_combustivel": "posto"}, usuario_gestor_a)
    assert RegistroAuditoria.objects.filter(acao="presumido.parametros_definidos").count() == 1


@pytest.mark.parametrize(
    "dados",
    [
        {"forma_recolhimento": "mensal"},
        {"padrao_combustivel": "loja"},
        {"padrao_combustivel": "POSTO"},
    ],
)
def test_valor_fora_do_catalogo_e_recusado(empresa_a, usuario_gestor_a, dados):
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.definir_parametros(empresa_a, dados, usuario_gestor_a)
    assert servico.parametros_da_empresa(empresa_a).definido is False


def test_parametros_de_uma_empresa_nao_aparecem_em_outra_do_mesmo_escritorio(
    empresa_a, empresa_a2, usuario_gestor_a
):
    servico.definir_parametros(empresa_a, {"forma_recolhimento": "quota_unica"}, usuario_gestor_a)
    assert servico.parametros_da_empresa(empresa_a2) == servico.ParametrosDaEmpresa(
        "tres_quotas", "", False
    )


# ---------------------------------------------------------------------------
# API: permissão no servidor, isolamento de escritório e entrada
# ---------------------------------------------------------------------------


def test_gestor_grava_e_le_pela_api(client, empresa_a, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    gravou = client.post(
        _url(empresa_a),
        data=json.dumps({"forma_recolhimento": "quota_unica", "padrao_combustivel": "trr"}),
        content_type="application/json",
    )
    assert gravou.status_code == 200
    assert gravou.json() == {
        "forma_recolhimento": "quota_unica",
        "padrao_combustivel": "trr",
        "definido": True,
    }
    lido = client.get(_url(empresa_a)).json()
    assert lido["padrao_combustivel"] == "trr"


def test_api_de_empresa_nova_devolve_o_padrao_do_escritorio(client, empresa_a, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    lido = client.get(_url(empresa_a)).json()
    assert lido == {
        "forma_recolhimento": "tres_quotas",
        "padrao_combustivel": "",
        "definido": False,
    }


def test_paralegal_le_mas_nao_grava(client, empresa_a, escritorio_a):
    paralegal = _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-parametros-dl084")
    client.force_login(paralegal)
    assert client.get(_url(empresa_a)).status_code == 200
    negado = client.post(
        _url(empresa_a),
        data=json.dumps({"padrao_combustivel": "posto"}),
        content_type="application/json",
    )
    assert negado.status_code == 403
    assert servico.parametros_da_empresa(empresa_a).definido is False


def test_empresa_de_outro_escritorio_responde_404(client, escritorio_b, empresa_a):
    intruso = _usuario(escritorio_b, Papel.GESTOR, "gestor-intruso-dl084")
    client.force_login(intruso)
    assert client.get(_url(empresa_a)).status_code == 404
    resposta = client.post(
        _url(empresa_a),
        data=json.dumps({"padrao_combustivel": "posto"}),
        content_type="application/json",
    )
    assert resposta.status_code == 404


def test_campo_fora_do_contrato_e_400(client, empresa_a, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url(empresa_a),
        data=json.dumps({"campo_inventado": "x"}),
        content_type="application/json",
    )
    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# Padrão de combustível na sugestão de natureza (PE-85.1): só quando o CFOP não decide
# ---------------------------------------------------------------------------


def _documento():
    return SimpleNamespace(fin_nfe="1", id_dest="1", transferencia_entre_estabelecimentos=False)


def _item(cfop, ncm="", csosn="102", cst=""):
    return SimpleNamespace(cfop=cfop, ncm=ncm, csosn=csosn, cst=cst)


def _ncm_de_combustivel():
    return next(iter(sorted(nfe.NCM_COMBUSTIVEL)))


@pytest.mark.parametrize("padrao", ["posto", "trr"])
def test_posto_e_trr_sugerem_consumo_quando_o_cfop_nao_decide_e_o_ncm_e_de_combustivel(padrao):
    # CFOP 5949 não diz se é consumo ou revenda. O NCM é de combustível, então o padrão decide.
    sugestao = nfe.sugerir_natureza_com_padrao(
        _documento(), _item("5949", ncm=_ncm_de_combustivel()), padrao, "saida"
    )
    assert sugestao.natureza == NaturezaOperacaoNFe.COMBUSTIVEL
    assert "padrão de combustível" in sugestao.motivo


def test_cfop_de_combustivel_sem_ncm_nao_e_decidido_pelo_padrao():
    # CFOP 5656 já diz consumo. O que falta é o NCM, e o padrão não passa por cima disso.
    sugestao = nfe.sugerir_natureza_com_padrao(_documento(), _item("5656"), "posto", "saida")
    assert sugestao.natureza is None


def test_distribuidora_nao_tem_padrao_e_o_item_decide():
    sugestao = nfe.sugerir_natureza_com_padrao(
        _documento(), _item("5949", ncm=_ncm_de_combustivel()), "distribuidora", "saida"
    )
    assert sugestao.natureza is None


def test_sem_padrao_a_sugestao_e_a_de_antes():
    item = _item("5949", ncm=_ncm_de_combustivel())
    antes = nfe.sugerir_natureza_item(_documento(), item, "saida")
    depois = nfe.sugerir_natureza_com_padrao(_documento(), item, None, "saida")
    assert depois == antes


def test_item_comum_de_posto_nao_recebe_o_padrao_de_combustivel():
    # Loja de conveniência: NCM comum, CFOP sem sinal de combustível. O padrão não entra.
    sugestao = nfe.sugerir_natureza_com_padrao(_documento(), _item("5949"), "posto", "saida")
    assert sugestao.natureza is None


def test_cfop_de_revenda_de_combustivel_nao_e_mudado_pelo_padrao():
    # CFOP 5655 é comercialização de combustível: o CFOP já diz revenda. O padrão "posto" não entra.
    sem_padrao = nfe.sugerir_natureza_com_padrao(_documento(), _item("5655"), None, "saida")
    com_padrao = nfe.sugerir_natureza_com_padrao(_documento(), _item("5655"), "posto", "saida")
    assert com_padrao == sem_padrao
    assert com_padrao.natureza is None


def test_ncm_de_lubrificante_decide_e_o_padrao_nao_entra():
    ncm_lubrificante = next(iter(sorted(nfe.NCM_LUBRIFICANTE)))
    sugestao = nfe.sugerir_natureza_com_padrao(
        _documento(), _item("5656", ncm=ncm_lubrificante), "posto", "saida"
    )
    assert sugestao.natureza == NaturezaOperacaoNFe.REVENDA
