"""DL-058 (B1 e B2): duas pequenas fugas de informação entre empresas.

Dados 100% sintéticos, criados nos próprios testes.

- B1: `conta_pai` de outra empresa e `conta_pai` inexistente recebiam respostas
  DIFERENTES na API; a diferença dizia a quem testava ids que o id existia em
  algum lugar. Agora a resposta é a mesma.
- B2: a consulta de lançamentos da DLPA (`id__in`) filtra também pela empresa.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.views_web import _lancamentos_da_dlpa_por_id, _montar_linhas_da_dlpa
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _conta(empresa, codigo, tipo, natureza):
    return Conta.objects.create(
        empresa=empresa, codigo=codigo, nome=f"Conta {codigo}", tipo=tipo, natureza=natureza
    )


@pytest.fixture
def cenario():
    """Duas empresas no MESMO escritório e uma terceira em OUTRO escritório,
    cada uma com um lançamento (o histórico de cada um é reconhecível)."""
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_c = Escritorio.objects.create(nome="Escritório C", cnpj="33333333000133")
    empresas = {
        "a": Empresa.objects.create(
            escritorio=escritorio_a, razao_social="Empresa A Ltda", cnpj="11122233000183"
        ),
        "b": Empresa.objects.create(
            escritorio=escritorio_a, razao_social="Empresa B Ltda", cnpj="44455566000183"
        ),
        "c": Empresa.objects.create(
            escritorio=escritorio_c, razao_social="Empresa C Ltda", cnpj="77788899000122"
        ),
    }
    contas = {}
    lancamentos = {}
    for chave, empresa in empresas.items():
        caixa = _conta(empresa, "1.1", TipoConta.ATIVO, NaturezaConta.DEVEDORA)
        capital = _conta(empresa, "2.1", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA)
        contas[chave] = caixa
        lancamentos[chave] = criar_lancamento(
            empresa=empresa,
            data=date(2024, 1, 10),
            historico=f"Historico sintetico da empresa {chave}",
            itens=[
                {"conta": caixa, "tipo": "debito", "valor": Decimal("100.00")},
                {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
            ],
        )
    usuario = get_user_model().objects.create_user(
        username="gestor", email="gestor@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_a, papel=Papel.GESTOR
    )
    return {"empresas": empresas, "contas": contas, "lancamentos": lancamentos}


def _post_conta_com_pai(client, empresa, conta_pai_id):
    return client.post(
        reverse("contabilidade:contas", args=[empresa.id]),
        data={
            "codigo": "1.1.1",
            "nome": "Sub caixa",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": conta_pai_id,
        },
        content_type="application/json",
    )


# --- B1: mesma resposta para id alheio e inexistente --------------------------


def test_b1_conta_pai_alheia_e_inexistente_recebem_a_mesma_resposta(client, cenario):
    client.login(username="gestor", password="senha-forte-123")
    empresa = cenario["empresas"]["a"]
    inexistente = Conta.objects.order_by("-id").first().id + 1000

    mesmo_escritorio = _post_conta_com_pai(client, empresa, cenario["contas"]["b"].id)
    outro_escritorio = _post_conta_com_pai(client, empresa, cenario["contas"]["c"].id)
    id_inexistente = _post_conta_com_pai(client, empresa, inexistente)

    assert id_inexistente.status_code == 400
    assert "conta_pai" in id_inexistente.json()
    # Status E corpo idênticos: nada que diferencie "existe em outra empresa"
    # de "não existe".
    assert mesmo_escritorio.status_code == id_inexistente.status_code
    assert outro_escritorio.status_code == id_inexistente.status_code
    assert mesmo_escritorio.json() == id_inexistente.json()
    assert outro_escritorio.json() == id_inexistente.json()
    # E nem o id enviado volta no corpo.
    assert str(inexistente) not in id_inexistente.content.decode()
    assert not Conta.objects.filter(empresa=empresa, codigo="1.1.1").exists()


def test_b1_conta_pai_da_propria_empresa_continua_aceita(client, cenario):
    """Sem este par, 'recusar tudo' passaria o teste acima."""
    client.login(username="gestor", password="senha-forte-123")
    empresa = cenario["empresas"]["a"]

    resposta = _post_conta_com_pai(client, empresa, cenario["contas"]["a"].id)

    assert resposta.status_code == 201, resposta.content
    assert Conta.objects.get(empresa=empresa, codigo="1.1.1").conta_pai == cenario["contas"]["a"]


# --- B2: a consulta de lançamentos da DLPA também filtra pela empresa ---------


def test_b2_id_de_lancamento_de_outra_empresa_forjado_na_lista_nao_e_devolvido(cenario):
    propria = cenario["empresas"]["a"]
    forjado_mesmo_escritorio = cenario["lancamentos"]["b"].id
    forjado_outro_escritorio = cenario["lancamentos"]["c"].id
    proprio = cenario["lancamentos"]["a"].id

    encontrados = _lancamentos_da_dlpa_por_id(
        {proprio, forjado_mesmo_escritorio, forjado_outro_escritorio}, propria
    )

    assert set(encontrados) == {proprio}
    texto = str(encontrados)
    assert "empresa b" not in texto
    assert "empresa c" not in texto


def test_b2_documento_nao_imprime_a_descricao_do_lancamento_alheio(cenario):
    """O mesmo, pela ponta que o contador vê: a linha da DLPA que carrega um
    id forjado sai sem a descrição do lançamento alheio."""
    propria = cenario["empresas"]["a"]
    dlpa_apurada = {
        "linhas": [
            {
                "chave": "saldo_inicial",
                "titulo": "Saldo inicial",
                "valor": Decimal("0.00"),
                "lancamentos": [cenario["lancamentos"]["a"].id, cenario["lancamentos"]["c"].id],
            }
        ]
    }

    linhas = _montar_linhas_da_dlpa(dlpa_apurada, propria)

    origens = linhas[0]["origens"]
    assert "Historico sintetico da empresa a" in origens[0]
    assert origens[1] == ""
    assert "empresa c" not in " ".join(origens)
