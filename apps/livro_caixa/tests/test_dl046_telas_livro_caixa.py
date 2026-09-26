"""DL-046, fatia 1 — telas do livro-caixa do cliente pessoa física
(`apps.livro_caixa.views_web`). Servidor + API já prontos e testados em
`test_dl046_livro_caixa.py` (46 testes); este arquivo testa que a TELA
OBEDECE às regras do servidor e as APRESENTA corretamente — permissão
(escrita x leitura), isolamento entre escritórios, recusa por modo de
escrituração (o inverso de `test_dl038_recusa_livro_caixa.py`), formulário
que preserva o que foi digitado ao recusar, estorno com confirmação
explícita (arquétipo E), relatório conciliável com o serviço, e o item do
menu "Livro-caixa" no lugar de "Contabilidade".

Dados 100% sintéticos, criados nos próprios testes. Datas em 2026, sempre
no passado (hoje é 2026-09-26).
"""

import itertools
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa.models import ContaLivroCaixa, LancamentoCaixa, NaturezaCaixa
from apps.livro_caixa.services import criar_lancamento_caixa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

_CONTADOR_DE_DOCUMENTO = itertools.count(1)


def _cpf_sintetico():
    # CPFs sintéticos com dígito verificador válido (reaproveitados dos
    # exemplos já usados em test_dl046_livro_caixa.py, para não inventar
    # um algoritmo de checagem aqui).
    base = ["11144477735", "22255588846", "52998224725", "12345678909", "98765432100"]
    return base[next(_CONTADOR_DE_DOCUMENTO) % len(base)]


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_DOCUMENTO):014d}"


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel=Papel.GESTOR, username="gestor-dl046t"):
    _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL-046t", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano de Tal DL-046t",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=_cpf_sintetico(),
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Contabilidade DL-046t Ltda",
        cnpj=_cnpj_sintetico(),
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    conta_receita = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="R1",
        nome="Honorários recebidos",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta_despesa = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="D1",
        nome="Despesas dedutíveis",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P10.001",
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "empresa_contabilidade": empresa_contabilidade,
        "conta_receita": conta_receita,
        "conta_despesa": conta_despesa,
    }


@pytest.fixture
def cenario_com_lancamento(cenario):
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa"],
        conta=cenario["conta_receita"],
        data=timezone.datetime(2026, 3, 10).date(),
        valor=Decimal("1500.00"),
        historico="Honorários de março",
        recebido_de="PJ",
    )
    cenario["lancamento"] = lancamento
    return cenario


# ---------------------------------------------------------------------------
# Permissão e isolamento (item 1 e 2 do FAZER)
# ---------------------------------------------------------------------------


def test_paralegal_le_mas_nao_ve_botao_de_escrever(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.PARALEGAL, username="paralegal-dl046t")
    url = reverse("livro_caixa_web:plano_de_contas", args=[cenario["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Nova conta" not in conteudo


def test_paralegal_recebe_403_ao_tentar_criar_conta(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.PARALEGAL, username="paralegal-dl046t2")
    url = reverse("livro_caixa_web:conta_nova", args=[cenario["empresa"].id])
    resposta_get = client.get(url)
    assert resposta_get.status_code == 403
    resposta_post = client.post(
        url,
        {
            "codigo": "R9",
            "nome": "Não deveria gravar",
            "natureza": "receita",
            "codigo_carne_leao": "R01.003.001",
        },
    )
    assert resposta_post.status_code == 403
    assert not ContaLivroCaixa.objects.filter(empresa=cenario["empresa"], codigo="R9").exists()


def test_cliente_recebe_403_em_toda_tela_do_livro_caixa(client, cenario):
    _autenticar(client, cenario["escritorio"], papel=Papel.CLIENTE, username="cliente-dl046t")
    empresa = cenario["empresa"]
    urls = [
        reverse("livro_caixa_web:plano_de_contas", args=[empresa.id]),
        reverse("livro_caixa_web:conta_nova", args=[empresa.id]),
        reverse("livro_caixa_web:lancamento_novo", args=[empresa.id]),
        reverse("livro_caixa_web:lancamentos", args=[empresa.id]),
        reverse("livro_caixa_web:relatorio", args=[empresa.id]),
    ]
    for url in urls:
        resposta = client.get(url)
        assert resposta.status_code == 403, url
        assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
        assert empresa.razao_social not in resposta.content.decode()


def test_empresa_de_outro_escritorio_da_404_sem_confirmar_existencia(client, cenario):
    outro_escritorio = Escritorio.objects.create(
        nome="Outro Escritório DL-046t", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, outro_escritorio, username="gestor-outro-dl046t")
    url = reverse("livro_caixa_web:plano_de_contas", args=[cenario["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 404
    assert cenario["empresa"].razao_social not in resposta.content.decode()


# ---------------------------------------------------------------------------
# Recusa por modo de escrituração — o INVERSO de test_dl038_recusa_livro_
# caixa.py: aqui é a empresa em CONTABILIDADE que é recusada pelo
# livro-caixa (item 1 do FAZER: "recusa de verdade continua no servidor").
# ---------------------------------------------------------------------------


def test_empresa_em_modo_contabilidade_e_recusada_em_toda_tela_do_livro_caixa(client, cenario):
    _autenticar(client, cenario["escritorio"])
    empresa = cenario["empresa_contabilidade"]
    urls = [
        reverse("livro_caixa_web:plano_de_contas", args=[empresa.id]),
        reverse("livro_caixa_web:conta_nova", args=[empresa.id]),
        reverse("livro_caixa_web:lancamento_novo", args=[empresa.id]),
        reverse("livro_caixa_web:lancamentos", args=[empresa.id]),
        reverse("livro_caixa_web:relatorio", args=[empresa.id]),
    ]
    for url in urls:
        resposta = client.get(url)
        assert resposta.status_code == 403, url
        assert "contabilidade" in resposta.content.decode().lower()


# ---------------------------------------------------------------------------
# Plano de contas do livro-caixa (item 2 do FAZER)
# ---------------------------------------------------------------------------


def test_plano_de_contas_lista_as_contas_com_codigo_do_carne_leao(client, cenario):
    _autenticar(client, cenario["escritorio"])
    url = reverse("livro_caixa_web:plano_de_contas", args=[cenario["empresa"].id])
    conteudo = client.get(url).content.decode()
    assert "R1" in conteudo
    assert "Honorários recebidos" in conteudo
    assert "R01.003.001" in conteudo
    assert "D1" in conteudo
    assert "P10.001" in conteudo


def test_conta_nova_cria_com_sucesso_e_redireciona(client, cenario):
    _autenticar(client, cenario["escritorio"])
    empresa = cenario["empresa"]
    url = reverse("livro_caixa_web:conta_nova", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "codigo": "R2",
            "nome": "Aluguel recebido",
            "natureza": "receita",
            "codigo_carne_leao": "R01.003.001",
            "ativa": "on",
        },
    )
    assert resposta.status_code == 302
    conta = ContaLivroCaixa.objects.get(empresa=empresa, codigo="R2")
    assert conta.codigo_carne_leao == "R01.003.001"


def test_conta_nova_com_codigo_incompativel_preserva_o_formulario(client, cenario):
    """Formulário de documento (arquétipo B, direção de arte §2): "o
    formulário não some quando dá erro" — o que a pessoa digitou continua
    lá, e o erro é texto."""
    _autenticar(client, cenario["escritorio"])
    empresa = cenario["empresa"]
    url = reverse("livro_caixa_web:conta_nova", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "codigo": "R3",
            "nome": "Receita mal classificada",
            "natureza": "receita",
            "codigo_carne_leao": "P10.001",  # formato de PAGAMENTO numa RECEITA
        },
    )
    assert resposta.status_code == 200  # re-renderiza, não redireciona
    conteudo = resposta.content.decode()
    assert "não tem o formato" in conteudo
    assert 'value="R3"' in conteudo
    assert 'value="Receita mal classificada"' in conteudo
    assert 'value="P10.001"' in conteudo
    assert not ContaLivroCaixa.objects.filter(empresa=empresa, codigo="R3").exists()


def test_conta_nova_com_codigo_duplicado_mostra_erro_no_campo(client, cenario):
    _autenticar(client, cenario["escritorio"])
    empresa = cenario["empresa"]
    url = reverse("livro_caixa_web:conta_nova", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "codigo": "R1",  # já existe (fixture `cenario`)
            "nome": "Repetida",
            "natureza": "receita",
            "codigo_carne_leao": "R01.003.001",
        },
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "já existe" in conteudo.lower() or "código" in conteudo.lower()
    assert ContaLivroCaixa.objects.filter(empresa=empresa, codigo="R1").count() == 1


# ---------------------------------------------------------------------------
# Lançamento de caixa (item 3 do FAZER)
# ---------------------------------------------------------------------------


def test_lancamento_novo_grava_com_sucesso(client, cenario):
    _autenticar(client, cenario["escritorio"])
    empresa = cenario["empresa"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-10",
            "conta": str(cenario["conta_receita"].id),
            "valor": "1.500,00",
            "historico": "Honorários de março",
            "documento_origem": "",
            "recebido_de": "PJ",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "chave_idempotencia": "teste-dl046-1",
        },
    )
    assert resposta.status_code == 302
    lancamento = LancamentoCaixa.objects.get(empresa=empresa)
    assert lancamento.valor == Decimal("1500.00")
    assert lancamento.historico == "Honorários de março"


def test_lancamento_novo_com_valor_invalido_preserva_o_formulario(client, cenario):
    _autenticar(client, cenario["escritorio"])
    empresa = cenario["empresa"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-10",
            "conta": str(cenario["conta_receita"].id),
            "valor": "abacaxi",
            "historico": "Tentativa inválida",
            "documento_origem": "",
            "recebido_de": "",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "chave_idempotencia": "teste-dl046-2",
        },
    )
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "não está no formato aceito" in conteudo
    assert 'value="abacaxi"' in conteudo
    assert 'value="Tentativa inválida"' in conteudo
    assert not LancamentoCaixa.objects.filter(empresa=empresa).exists()


def test_lancamento_novo_rendimento_trabalho_nao_assalariado_exige_os_dois_cpfs(client, cenario):
    """R01.001.001 recebido de PF exige CPF titular e beneficiário
    (services.py) — a tela propaga a recusa do servidor, sem reimplementar
    a regra."""
    _autenticar(client, cenario["escritorio"])
    empresa = cenario["empresa"]
    conta = ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="R9",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-10",
            "conta": str(conta.id),
            "valor": "500,00",
            "historico": "Recibo avulso",
            "documento_origem": "",
            "recebido_de": "PF",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "chave_idempotencia": "teste-dl046-3",
        },
    )
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "CPF do titular" in conteudo or "CPF do beneficiário" in conteudo
    assert not LancamentoCaixa.objects.filter(empresa=empresa, conta=conta).exists()


def test_lancamentos_lista_mostra_o_periodo_e_o_lancamento(client, cenario_com_lancamento):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    url = reverse("livro_caixa_web:lancamentos", args=[empresa.id])
    conteudo = client.get(f"{url}?inicio=2026-03-01&fim=2026-03-31").content.decode()
    assert "Honorários de março" in conteudo
    assert "1.500,00" in conteudo
    assert "Estornar" in conteudo


# ---------------------------------------------------------------------------
# Estorno — arquétipo E, confirmação explícita (item 3 do FAZER: "estorno
# é a ÚNICA correção")
# ---------------------------------------------------------------------------


def test_estornar_get_mostra_confirmacao_com_o_que_vai_acontecer(client, cenario_com_lancamento):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    lancamento = cenario_com_lancamento["lancamento"]
    url = reverse("livro_caixa_web:lancamento_estornar", args=[empresa.id, lancamento.id])
    conteudo = client.get(url).content.decode()
    assert "O que vai acontecer" in conteudo
    assert "1.500,00" in conteudo
    assert "NUNCA é" in conteudo or "nunca é alterado" in conteudo.lower()
    # Botão nomeia a consequência, nunca só "Confirmar" (direção de arte §2E).
    assert f"Estornar lançamento nº {lancamento.id}" in conteudo


def test_estornar_post_cria_o_lancamento_reverso_e_nao_apaga_o_original(
    client, cenario_com_lancamento
):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    lancamento = cenario_com_lancamento["lancamento"]
    url = reverse("livro_caixa_web:lancamento_estornar", args=[empresa.id, lancamento.id])
    resposta = client.post(url)
    assert resposta.status_code == 302
    lancamento.refresh_from_db()
    assert lancamento.estorno_de_id is None  # original intacto
    estorno = LancamentoCaixa.objects.get(estorno_de=lancamento)
    assert estorno.valor == lancamento.valor
    assert estorno.conta_id == lancamento.conta_id


def test_estornar_um_lancamento_ja_estornado_recusa_com_mensagem(client, cenario_com_lancamento):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    lancamento = cenario_com_lancamento["lancamento"]
    url = reverse("livro_caixa_web:lancamento_estornar", args=[empresa.id, lancamento.id])
    primeira = client.post(url)
    assert primeira.status_code == 302
    segunda = client.post(url)
    assert segunda.status_code == 400
    assert "já foi estornado" in segunda.content.decode()
    assert LancamentoCaixa.objects.filter(estorno_de=lancamento).count() == 1


def test_lista_nao_oferece_estornar_para_lancamento_ja_estornado_ou_para_um_estorno(
    client, cenario_com_lancamento
):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    lancamento = cenario_com_lancamento["lancamento"]
    url_estornar = reverse("livro_caixa_web:lancamento_estornar", args=[empresa.id, lancamento.id])
    client.post(url_estornar)

    url_lista = reverse("livro_caixa_web:lancamentos", args=[empresa.id])
    conteudo = client.get(f"{url_lista}?inicio=2026-03-01&fim=2026-03-31").content.decode()
    # Duas linhas na lista (original + estorno), mas NENHUMA com link
    # "Estornar" — o original já foi estornado, e um estorno nunca é
    # estornável (mesma regra do serviço).
    assert conteudo.count("botao--secundario botao--pequeno") == 0


# ---------------------------------------------------------------------------
# Relatório "Livro Caixa" (item 4 do FAZER) — concilia com o serviço
# ---------------------------------------------------------------------------


def test_relatorio_bate_com_a_apuracao_do_servico(client, cenario_com_lancamento):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    url = reverse("livro_caixa_web:relatorio", args=[empresa.id])
    conteudo = client.get(f"{url}?inicio=2026-03-01&fim=2026-03-31").content.decode()
    assert "1.500,00" in conteudo  # entrada
    assert "0,00" in conteudo  # saída
    assert "Honorários de março" in conteudo
    # Identificação do CONTRIBUINTE (nome, CPF) — critério do FAZER 4.
    assert empresa.razao_social in conteudo
    assert "CPF" in conteudo
    assert empresa.cpf[0:3] in conteudo  # CPF mascarado contém o original


def test_relatorio_mostra_estorno_visivel(client, cenario_com_lancamento):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    lancamento = cenario_com_lancamento["lancamento"]
    url_estornar = reverse("livro_caixa_web:lancamento_estornar", args=[empresa.id, lancamento.id])
    client.post(url_estornar)

    # RC-78 (por analogia): a data do estorno é decidida pelo SERVIDOR —
    # `estornar_lancamento_caixa` usa `timezone.localdate()` (hoje), não a
    # data do original. O período consultado precisa cobrir as DUAS datas.
    url = reverse("livro_caixa_web:relatorio", args=[empresa.id])
    hoje_iso = timezone.localdate().isoformat()
    conteudo = client.get(f"{url}?inicio=2026-03-01&fim={hoje_iso}").content.decode()
    assert "Estorno" in conteudo
    # O efeito líquido do estorno é zero (mesma conta, mesmo valor,
    # contribuição invertida no total) — saldo do período volta a 0,00.
    assert "0,00" in conteudo
    # Direção de arte §2A: valor invertido (a linha do estorno SUBTRAI do
    # total, ao contrário do resto da coluna) vai entre parênteses — nunca
    # só cor. Sem isto, somar a coluna Valor a olho não bateria com
    # Entradas/Saídas/Saldo do cartão acima.
    assert "(1.500,00)" in conteudo


def test_relatorio_periodo_invalido_retorna_400_com_saida_navegavel(client, cenario):
    _autenticar(client, cenario["escritorio"])
    url = reverse("livro_caixa_web:relatorio", args=[cenario["empresa"].id])
    resposta = client.get(f"{url}?inicio=abacaxi&fim=2026-03-31")
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "não pôde ser usado" in conteudo
    assert reverse("livro_caixa_web:relatorio", args=[cenario["empresa"].id]) in conteudo


# ---------------------------------------------------------------------------
# Nenhuma tela usa JavaScript (direção de arte §4.6)
# ---------------------------------------------------------------------------


def test_nenhuma_tela_do_livro_caixa_usa_javascript(client, cenario_com_lancamento):
    _autenticar(client, cenario_com_lancamento["escritorio"])
    empresa = cenario_com_lancamento["empresa"]
    lancamento = cenario_com_lancamento["lancamento"]
    urls = [
        reverse("livro_caixa_web:plano_de_contas", args=[empresa.id]),
        reverse("livro_caixa_web:conta_nova", args=[empresa.id]),
        reverse("livro_caixa_web:lancamento_novo", args=[empresa.id]),
        reverse("livro_caixa_web:lancamentos", args=[empresa.id]),
        reverse("livro_caixa_web:lancamento_estornar", args=[empresa.id, lancamento.id]),
        reverse("livro_caixa_web:relatorio", args=[empresa.id]),
    ]
    for url in urls:
        assert "<script" not in client.get(url).content.decode().lower(), url


# ---------------------------------------------------------------------------
# Menu lateral (item 1 do FAZER): "Livro-caixa" no lugar de "Contabilidade"
# ---------------------------------------------------------------------------


def test_menu_mostra_livro_caixa_para_empresa_em_livro_caixa(client, cenario):
    _autenticar(client, cenario["escritorio"])
    url = reverse("livro_caixa_web:plano_de_contas", args=[cenario["empresa"].id])
    conteudo = client.get(url).content.decode()
    assert '<span class="rotulo-menu">Livro-caixa</span>' in conteudo
    assert '<span class="rotulo-menu">Contabilidade</span>' not in conteudo
    assert reverse("livro_caixa_web:plano_de_contas", args=[cenario["empresa"].id]) in conteudo
    assert reverse("livro_caixa_web:lancamentos", args=[cenario["empresa"].id]) in conteudo
    assert reverse("livro_caixa_web:relatorio", args=[cenario["empresa"].id]) in conteudo


def test_menu_mostra_contabilidade_para_empresa_em_contabilidade(client, cenario):
    _autenticar(client, cenario["escritorio"])
    Conta.objects.create(
        empresa=cenario["empresa_contabilidade"],
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    conteudo = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[cenario["empresa_contabilidade"].id])
    ).content.decode()
    assert '<span class="rotulo-menu">Contabilidade</span>' in conteudo
    assert '<span class="rotulo-menu">Livro-caixa</span>' not in conteudo
