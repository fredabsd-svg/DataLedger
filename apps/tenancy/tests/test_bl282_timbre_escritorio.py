"""BL-282 (M6 da auditoria DL-026, rodada 1, docs/projeto/backlog.md): o
relatório impresso saía limpo e legível, mas com "DataLedger." no topo — a
marca do FORNECEDOR do software, não a do escritório de contabilidade que
o usa. Faltava campo de timbre no cadastro do escritório.

Decisão de arquitetura do arquiteto-senior, registrada no pedido desta
etapa: timbre é TEXTO nesta rodada, não imagem (upload de logotipo é
etapa própria — armazenamento de mídia, validação de tipo e isolamento
de mídia entre escritórios).

Este arquivo testa o MODELO (`Escritorio.linhas_do_timbre`, o contrato
único entre servidor e template) e o isolamento do dado exposto no
contexto HTTP das telas imprimíveis. Dados 100% sintéticos.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# `Escritorio.linhas_do_timbre` — contrato de dados, sem HTTP.
# ---------------------------------------------------------------------------


def test_timbre_completo_traz_as_tres_linhas_na_ordem():
    escritorio = Escritorio.objects.create(
        nome="Nome de Interface Ltda",
        cnpj="10101010000110",
        razao_social_no_timbre="Razão Social Completa de Contabilidade Ltda",
        endereco_no_timbre="Rua das Acácias, 123 — Centro — Palmas/TO",
        registro_no_timbre="CRC-TO 000123/O-4",
    )
    assert escritorio.linhas_do_timbre == [
        "Razão Social Completa de Contabilidade Ltda",
        "Rua das Acácias, 123 — Centro — Palmas/TO",
        "CRC-TO 000123/O-4",
    ]


def test_timbre_parcial_omite_linha_vazia_sem_deixar_buraco():
    """Só o endereço cadastrado, sem razão social de timbre nem registro:
    a lista tem que cair para `nome` na primeira posição e pular direto
    para o endereço — nunca uma string vazia no meio."""
    escritorio = Escritorio.objects.create(
        nome="Contabilidade Parcial Ltda",
        cnpj="20202020000120",
        endereco_no_timbre="Av. Central, 456 — Araguaína/TO",
    )
    assert escritorio.linhas_do_timbre == [
        "Contabilidade Parcial Ltda",
        "Av. Central, 456 — Araguaína/TO",
    ]


def test_timbre_ausente_cai_para_o_nome_sem_lista_vazia():
    """Nenhum campo de timbre cadastrado: a lista nunca fica vazia — cai
    para `nome`, porque `nome` é obrigatório em todo `Escritorio`."""
    escritorio = Escritorio.objects.create(nome="Sem Timbre Cadastrado Ltda", cnpj="30303030000130")
    assert escritorio.linhas_do_timbre == ["Sem Timbre Cadastrado Ltda"]


def test_timbre_com_espacos_em_branco_e_tratado_como_vazio():
    """Campo preenchido só com espaço não deve contar como "cadastrado" —
    senão o cabeçalho ganharia uma linha em branco."""
    escritorio = Escritorio.objects.create(
        nome="Espaços Ltda",
        cnpj="40404040000140",
        razao_social_no_timbre="   ",
        endereco_no_timbre="   ",
        registro_no_timbre="   ",
    )
    assert escritorio.linhas_do_timbre == ["Espaços Ltda"]


# ---------------------------------------------------------------------------
# Isolamento no contexto HTTP — o timbre que aparece é do escritório da
# empresa CONSULTADA, nunca de outro (regra permanente do projeto).
# ---------------------------------------------------------------------------


@pytest.fixture
def dois_escritorios():
    escritorio_a = Escritorio.objects.create(
        nome="Escritório A",
        cnpj="50505050000150",
        razao_social_no_timbre="Escritório A — Contabilidade e Assessoria Ltda",
        endereco_no_timbre="Rua A, 1 — Palmas/TO",
        registro_no_timbre="CRC-TO 000001/O-1",
    )
    escritorio_b = Escritorio.objects.create(
        nome="Escritório B",
        cnpj="60606060000160",
        razao_social_no_timbre="Escritório B — Serviços Contábeis Ltda",
        endereco_no_timbre="Rua B, 2 — Gurupi/TO",
        registro_no_timbre="CRC-TO 000002/O-2",
    )
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente do A Ltda", cnpj="50566677000199"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Cliente do B Ltda", cnpj="60677788000200"
    )
    conta_a = Conta.objects.create(
        empresa=empresa_a,
        codigo="1",
        nome="Caixa A",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    contrapartida_a = Conta.objects.create(
        empresa=empresa_a,
        codigo="2",
        nome="Diversos A",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    usuario_a = get_user_model().objects.create_user(
        username="gestora-bl282-a",
        email="gestora-bl282-a@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_a, escritorio=escritorio_a, papel=Papel.GESTOR
    )
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "conta_a": conta_a,
        "contrapartida_a": contrapartida_a,
    }


def _login_a(client):
    assert client.login(username="gestora-bl282-a", password="senha-forte-123")


def test_balancete_expoe_o_timbre_do_escritorio_da_empresa_consultada(client, dois_escritorios):
    _login_a(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=dois_escritorios["empresa_a"],
        data=hoje,
        historico="BL-282 movimento para o balancete não ficar vazio",
        itens=[
            {
                "conta": dois_escritorios["conta_a"],
                "tipo": "debito",
                "valor": Decimal("10.00"),
            },
            {
                "conta": dois_escritorios["contrapartida_a"],
                "tipo": "credito",
                "valor": Decimal("10.00"),
            },
        ],
        criado_por=None,
        chave_idempotencia="k-bl282-balancete",
    )
    url = reverse("contabilidade_web:balancete", args=[dois_escritorios["empresa_a"].id])
    resposta = client.get(f"{url}?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}")
    assert resposta.status_code == 200
    assert resposta.context["timbre_linhas"] == [
        "Escritório A — Contabilidade e Assessoria Ltda",
        "Rua A, 1 — Palmas/TO",
        "CRC-TO 000001/O-1",
    ]
    # Nunca o timbre do outro escritório (isolamento — regra permanente,
    # AGENTS.md: "Dados de empresas diferentes permanecem isolados").
    assert "Escritório B" not in "".join(resposta.context["timbre_linhas"])


def test_usuario_do_escritorio_a_nao_alcanca_o_balancete_da_empresa_b(client, dois_escritorios):
    """Isolamento na outra direção: mesmo tentando pela URL, a empresa de
    OUTRO escritório dá 404 — o timbre de B nunca chega ao usuário de A
    porque a tela inteira é inacessível (mesma regra de
    `_empresa_do_escritorio_ativo`, já coberta para outras telas em
    `apps/tenancy/tests/test_isolamento.py`; este teste é o par específico
    do timbre, guardando contra uma regressão futura que abrisse acesso à
    empresa sem reintroduzir o vazamento do timbre)."""
    _login_a(client)
    url = reverse("contabilidade_web:balancete", args=[dois_escritorios["empresa_b"].id])
    resposta = client.get(url)
    assert resposta.status_code == 404


def test_diario_e_razao_tambem_expoe_o_timbre_pelo_mesmo_contrato(client, dois_escritorios):
    """BL-282 pede para expor "ao menos no Balancete" e declarar se Diário/
    Razão saíram de graça — saíram, pelo mesmo `empresa.escritorio.
    linhas_do_timbre`; este teste prova que o contrato (`timbre_linhas`)
    também está nessas duas telas."""
    _login_a(client)
    hoje = timezone.localdate()

    url_diario = reverse("contabilidade_web:diario", args=[dois_escritorios["empresa_a"].id])
    resposta_diario = client.get(
        f"{url_diario}?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"
    )
    assert resposta_diario.status_code == 200
    assert resposta_diario.context["timbre_linhas"][0] == (
        "Escritório A — Contabilidade e Assessoria Ltda"
    )

    url_razao = reverse(
        "contabilidade_web:razao",
        args=[dois_escritorios["empresa_a"].id, dois_escritorios["conta_a"].id],
    )
    resposta_razao = client.get(
        f"{url_razao}?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"
    )
    assert resposta_razao.status_code == 200
    assert resposta_razao.context["timbre_linhas"][0] == (
        "Escritório A — Contabilidade e Assessoria Ltda"
    )


def test_balancete_sem_timbre_cadastrado_usa_o_nome_do_escritorio(client):
    """Escritório sem nenhum campo de timbre: o contrato nunca fica vazio
    — cai para `nome`, e a tela continua funcionando (não bloqueia por
    falta de cadastro)."""
    escritorio = Escritorio.objects.create(nome="Sem Timbre Ltda", cnpj="70707070000170")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Cliente Sem Timbre Ltda", cnpj="70788899000211"
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl282-sem-timbre",
        email="gestora-bl282-sem-timbre@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestora-bl282-sem-timbre", password="senha-forte-123")

    url = reverse("contabilidade_web:balancete", args=[empresa.id])
    resposta = client.get(url)
    assert resposta.status_code == 200
    assert resposta.context["timbre_linhas"] == ["Sem Timbre Ltda"]
