"""DL-038, etapa 2, critério 7 — o documento emitido (Balanço) imprime o
rótulo e a inscrição corretos para empresa pessoa física (CPF).

Antes desta etapa, o único documento que imprime a inscrição da empresa
(o Balanço — o único que hoje passa `identificacao-do-documento`, RC-95)
assumia sempre CNPJ (`_cnpj_mascarado(empresa.cnpj)`, em
`apps/contabilidade/views_web.py`). Uma empresa CPF em modo contabilidade é
PERMITIDA pelo modelo (R4 não proíbe isso — CPF só SUGERE livro-caixa,
HI-23) e sairia com a inscrição EM BRANCO no papel, porque `empresa.cnpj` é
vazio por invariante de banco para empresa CPF
("empresa_inscricao_consistente_com_tipo", apps/empresas/models.py).

Dois níveis de teste:
  1. `rotulo_e_inscricao_da_empresa` (apps.contabilidade.services) — função
     PURA, testada isolada, sem banco.
  2. A tela do Balanço de ponta a ponta, com uma empresa CPF classificada e
     balanceada (pode_emitir=True) — prova que o HTML servido realmente
     mostra "CPF 111.444.777-35" em vez de "CNPJ " em branco.

O segundo teste da tela para CNPJ (regressão) confirma que a saída CNPJ não
mudou — mesmo texto que `test_dl034_tela_do_balanco.py::
test_bloco_de_identificacao_do_item_51_no_html` já prova para o cenário
clássico daquela suíte (não duplicado aqui; ver o cenário mínimo próprio
abaixo, para não depender de fixture de outro arquivo).

Dados 100% sintéticos.
"""

import itertools
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import (
    ClassificacaoPatrimonial,
    Conta,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento, rotulo_e_inscricao_da_empresa
from apps.empresas.models import Empresa, TipoInscricao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

# Mesmo motivo do arquivo irmão (test_dl034_tela_do_balanco.py): a view
# `balanco` chama `apurar_balanco_patrimonial` (DE-067), que abre a PRÓPRIA
# transação de nível superior — precisa rodar fora do atomic() padrão do
# pytest-django.
pytestmark = pytest.mark.django_db(transaction=True)

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA

_CONTADOR_DE_CNPJ_DE_ESCRITORIO = itertools.count(1)


def _cnpj_sintetico_de_escritorio():
    # CNPJ sintético de 14 dígitos, único por chamada — mesma técnica de
    # test_dl034_tela_do_balanco.py::_cnpj_sintetico (não é dígito
    # verificador válido; o escritório não passa pela validação de CNPJ de
    # apps.empresas, que não está em causa aqui).
    return f"{next(_CONTADOR_DE_CNPJ_DE_ESCRITORIO):014d}"


# ---------------------------------------------------------------------------
# 1. Função pura — sem banco.
# ---------------------------------------------------------------------------


class _EmpresaFalsaCPF:
    tipo_inscricao = TipoInscricao.CPF
    cpf = "11144477735"
    cnpj = ""


class _EmpresaFalsaCNPJ:
    tipo_inscricao = TipoInscricao.CNPJ
    cnpj = "11122233000183"
    cpf = ""


def test_rotulo_e_inscricao_da_empresa_cpf():
    rotulo, inscricao = rotulo_e_inscricao_da_empresa(_EmpresaFalsaCPF())
    assert rotulo == "CPF"
    assert inscricao == "111.444.777-35"


def test_rotulo_e_inscricao_da_empresa_cnpj_nao_muda():
    # Regressão: mesma máscara XX.XXX.XXX/XXXX-XX que `_cnpj_mascarado`
    # (removida nesta etapa) e `apps.empresas.views._mascara_cnpj` sempre
    # produziram.
    rotulo, inscricao = rotulo_e_inscricao_da_empresa(_EmpresaFalsaCNPJ())
    assert rotulo == "CNPJ"
    assert inscricao == "11.122.233/0001-83"


def test_rotulo_e_inscricao_da_empresa_cpf_com_tamanho_errado_devolve_original():
    # Mesma política de "nunca mascarar errado" de _mascara_cnpj/_mascara_cpf.
    class _EmpresaCpfCurto:
        tipo_inscricao = TipoInscricao.CPF
        cpf = "123"
        cnpj = ""

    rotulo, inscricao = rotulo_e_inscricao_da_empresa(_EmpresaCpfCurto())
    assert rotulo == "CPF"
    assert inscricao == "123"


# ---------------------------------------------------------------------------
# 2. Tela do Balanço de ponta a ponta — cenário mínimo, classificado e
#    balanceado (pode_emitir=True), sem conta retificadora dentro de grupo
#    (mesma restrição do arquivo irmão) — adaptado de
#    test_dl034_tela_do_balanco.py::cenario_com_inversao, só para não
#    depender de fixture definida em outro arquivo de teste.
# ---------------------------------------------------------------------------


def _conta(empresa, *, codigo, nome, tipo, natureza, pai=None, classificacao=None):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_patrimonial=classificacao,
        # Duas contas FOLHA, sem hierarquia (nenhuma "ATIVO"/"PASSIVO"
        # agrupadora) — as duas recebem lançamento direto, então as duas
        # aceitam lançamento. Cenário mínimo o bastante para
        # `avaliar_emissao_do_balanco` liberar a emissão (resíduo zero,
        # nenhuma conta sem classificação com movimento).
        aceita_lancamento=True,
    )


def _lancar(empresa, data, historico, debito, credito, valor):
    criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _cenario_balanco_minimo(*, razao_social, tipo_inscricao, cnpj="", cpf=""):
    escritorio = Escritorio.objects.create(
        nome=f"Escritório {razao_social}", cnpj=_cnpj_sintetico_de_escritorio()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social=razao_social,
        tipo_inscricao=tipo_inscricao,
        cnpj=cnpj,
        cpf=cpf,
    )
    caixa = _conta(
        empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    capital_social = _conta(
        empresa, codigo="3", nome="Capital Social", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C
    )
    hoje = timezone.localdate()
    _lancar(empresa, hoje, "Integralização de capital", caixa, capital_social, "1000.00")
    _usuario_com_papel(Papel.GESTOR, escritorio, f"gestor-{empresa.id}")
    return escritorio, empresa


def test_balanco_de_empresa_cpf_mostra_rotulo_cpf_e_inscricao_formatada(client):
    escritorio, empresa = _cenario_balanco_minimo(
        razao_social="Fulano de Tal", tipo_inscricao=TipoInscricao.CPF, cpf="11144477735"
    )
    client.login(username=f"gestor-{empresa.id}", password="senha-forte-123")

    resposta = client.get(reverse("contabilidade_web:balanco", args=[empresa.id]))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Balanço pronto para emissão" in conteudo
    assert 'class="identificacao-do-documento"' in conteudo
    # A pergunta que este teste responde: a inscrição sai CPF formatado —
    # nunca "CNPJ" e nunca em branco.
    assert "CPF 111.444.777-35" in conteudo
    assert "CNPJ" not in conteudo


def test_balanco_de_empresa_cnpj_continua_mostrando_cnpj_mascarado(client):
    # Regressão: a mesma tela, para empresa CNPJ (o caminho que já existia
    # antes desta etapa), continua idêntica.
    escritorio, empresa = _cenario_balanco_minimo(
        razao_social="Empresa CNPJ Ltda",
        tipo_inscricao=TipoInscricao.CNPJ,
        cnpj="11122233000183",
    )
    client.login(username=f"gestor-{empresa.id}", password="senha-forte-123")

    resposta = client.get(reverse("contabilidade_web:balanco", args=[empresa.id]))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Balanço pronto para emissão" in conteudo
    assert "CNPJ 11.122.233/0001-83" in conteudo
