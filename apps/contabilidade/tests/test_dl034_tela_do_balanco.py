"""DL-034 — a tela do Balanço Patrimonial (apps.contabilidade.views_web.balanco).

Cobre os critérios do plano (docs/planos/DL-034-a-tela-do-balanco.md) que
são da FRENTE DA TELA — views_web.py, urls_web.py, templates/contabilidade/
balanco.html e os dois parciais que ela usa: permissão verificada no
servidor com o CORPO conferido (não só o código — lição do BL-211),
isolamento entre escritórios, os cinco grupos da lei somando o Ativo e o
Passivo, recusa de emissão NOMEANDO o que falta (com controle positivo),
apresentação (D/C, parênteses, o bloco do item 51) e os cinco estados
(vazio, erro, sucesso, sem permissão — "carregando" não se aplica: a tela
é renderizada no servidor, sem JavaScript, mesmo padrão de Balancete/
Diário/Razão, que também não têm estado de carregamento no cliente).

A decisão de SE PODE emitir (as quatro condições do critério 1) é do
SERVIDOR — `apps.contabilidade.services.avaliar_emissao_do_balanco` — e
tem suíte própria do `desenvolvedor-pleno`
(test_dl034_balanco_patrimonial.py). Este arquivo testa que a TELA
OBEDECE a essa decisão (nunca monta a tabela quando `pode_emitir` é falso,
sempre monta quando é verdadeiro) e a APRESENTA corretamente — não
reimplementa nem reconfere a aritmética da decisão em si.

⚠️ Nenhuma fixture deste arquivo usa conta RETIFICADORA dentro de um
grupo — instrução explícita do plano DL-034 ("O CONTRATO entre as duas
frentes"): a frente do servidor estava corrigindo o SINAL dessas contas
(a opção (b) do critério 1) enquanto esta tela foi escrita, e um teste que
fixasse esse número aqui reprovaria amanhã, ou pior, atrapalharia a
correção. Cenários com retificadora já são cobertos pelos testes de
`apurar_saldos`/`avaliar_emissao_do_balanco`, que são do
`desenvolvedor-pleno`.

⚠️ **Exceção, aberta na rodada de correção do BL-501/BL-503/BL-508/BL-509
(2026-09-21):** a restrição acima nasceu enquanto a opção (b) ainda
estava em aberto. A auditoria da DL-034 (rodada 1) MEDIU (b) provada para
retificadora de grupo E para a topologia pura do BL-486 (Clientes D /
"(-) PDD" C, irmãs topo classificadas) — o número sai CERTO nas duas. A
restrição não se aplica mais a essa topologia específica:
`cenario_com_aviso_de_natureza_divergente`, abaixo, usa exatamente ela,
de propósito, para testar o critério 6 da correção (DE-070: a lista deixa
de vetar e vira aviso).

Dados 100% sintéticos, criados nos próprios testes.
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
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

# `transaction=True`: a view `balanco` chama `apurar_balanco_patrimonial`
# (DE-067), que abre sua PRÓPRIA transação de nível superior (`SET
# TRANSACTION ISOLATION LEVEL REPEATABLE READ` só é válido como primeira
# instrução depois do `BEGIN`). O `django_db` PADRÃO do pytest-django já
# embrulha o corpo de cada teste num `transaction.atomic()` para poder
# desfazer no fim — dentro dele, `connection.in_atomic_block` SEMPRE seria
# `True`, e a guarda de precondição daquela função recusaria QUALQUER
# requisição a esta tela, mesmo sem nenhum atomic() explícito escrito
# aqui. `transaction=True` desliga esse embrulho, para o teste exercitar a
# view como uma requisição real exercitaria (fora de qualquer atomic —
# `ATOMIC_REQUESTS` está desligado, `config/settings.py`). Mesma solução
# que `apps.contabilidade.tests.test_dl034_balanco_patrimonial` já usa
# para o mesmo motivo.
pytestmark = pytest.mark.django_db(transaction=True)

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA

_CONTADOR_DE_CNPJ = itertools.count(1)


def _cnpj_sintetico():
    # CNPJ sintético de 14 dígitos, único por chamada — mesma técnica de
    # test_dl033_camada_de_saldos_circulante.py (não redigito verificador
    # válido: os testes deste módulo não passam pela validação de CNPJ de
    # apps.empresas, que não está em causa aqui).
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _conta(
    empresa,
    *,
    codigo,
    nome,
    tipo,
    natureza,
    pai=None,
    classificacao=None,
    aceita_lancamento=True,
):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_patrimonial=classificacao,
        aceita_lancamento=aceita_lancamento,
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


def _autenticar(client, escritorio, papel=Papel.GESTOR, username="gestor-dl034"):
    _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")


# ---------------------------------------------------------------------------
# Fixtures — cenários LIMPOS, sem retificadora dentro de grupo (ver docstring
# do módulo).
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario_classificado():
    """Plano de contas com as CINCO seções do Balanço ocupadas — Ativo
    Circulante, os QUATRO subgrupos do Ativo Não Circulante, Passivo
    Circulante, Passivo Não Circulante e Patrimônio Líquido — e a equação
    fechando: Ativo = Passivo + Patrimônio Líquido = 12.600,50.

    Nenhum lançamento toca Receita nem Despesa: `resultado_nao_
    transferido` fica ZERO por construção (não há nada a transferir),
    então o Balanço não carrega a ressalva informativa desse campo.

    Números escolhidos para exercitar centavos NÃO redondos (300,50) e
    para os quatro subgrupos do Ativo Não Circulante terem valores TODOS
    diferentes entre si — controle contra um subtotal que, por acidente,
    somasse o grupo errado e ainda batesse por coincidência numérica.
    """
    escritorio = Escritorio.objects.create(nome="Escritório DL-034", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Classificada DL-034 Ltda",
        cnpj=_cnpj_sintetico(),
    )

    ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    circulante = _conta(
        empresa,
        codigo="1.1",
        nome="Ativo Circulante",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
        aceita_lancamento=False,
    )
    caixa = _conta(
        empresa, codigo="1.1.01", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D, pai=circulante
    )
    realizavel = _conta(
        empresa,
        codigo="1.2",
        nome="Realizável a Longo Prazo",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO,
    )
    investimentos = _conta(
        empresa,
        codigo="1.3",
        nome="Investimentos",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS,
    )
    imobilizado = _conta(
        empresa,
        codigo="1.4",
        nome="Imobilizado",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
    )
    intangivel = _conta(
        empresa,
        codigo="1.5",
        nome="Intangível",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL,
    )

    passivo = _conta(
        empresa,
        codigo="2",
        nome="PASSIVO",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        aceita_lancamento=False,
    )
    passivo_circulante = _conta(
        empresa,
        codigo="2.1",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=passivo,
        classificacao=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
    )
    passivo_nao_circulante = _conta(
        empresa,
        codigo="2.2",
        nome="Financiamentos",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=passivo,
        classificacao=ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE,
    )

    capital_social = _conta(
        empresa, codigo="3.1", nome="Capital Social", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C
    )

    hoje = timezone.localdate()
    _lancar(empresa, hoje, "Integralização de capital", caixa, capital_social, "10000.00")
    _lancar(empresa, hoje, "Aplicação em investimento", investimentos, caixa, "2000.00")
    _lancar(
        empresa, hoje, "Compra de imobilizado a prazo", imobilizado, passivo_circulante, "1500.00"
    )
    _lancar(
        empresa,
        hoje,
        "Empréstimo de longo prazo aplicado no realizável",
        realizavel,
        passivo_nao_circulante,
        "800.00",
    )
    _lancar(empresa, hoje, "Ativo intangível a prazo", intangivel, passivo_circulante, "300.50")

    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "caixa": caixa,
        "data_base": hoje,
    }


@pytest.fixture
def cenario_pendente():
    """Uma conta ATIVO com saldo, sem classificação própria nem
    ancestral — dispara `contas_sem_classificacao_patrimonial` (critério 1,
    condição 2). Cenário mínimo e LIMPO, sem retificadora."""
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-034 Pendente", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Pendente DL-034 Ltda", cnpj=_cnpj_sintetico()
    )
    caixa = _conta(
        empresa, codigo="1", nome="Caixa Sem Classificação", tipo=TipoConta.ATIVO, natureza=D
    )
    receita = _conta(
        empresa, codigo="2", nome="Receita de Serviços", tipo=TipoConta.RECEITA, natureza=C
    )
    hoje = timezone.localdate()
    _lancar(empresa, hoje, "Venda à vista", caixa, receita, "500.00")
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "data_base": hoje}


@pytest.fixture
def cenario_com_inversao():
    """Passivo Circulante que termina com saldo DEVEDOR (a empresa pagou
    mais do que devia ao fornecedor, sem nenhum lançamento anterior de
    compra) — exercita o ramo "invertido, entre parênteses" tanto na linha
    da conta (`_saldo.html`) quanto no subtotal do grupo (`_saldo_grupo.
    html`), sem depender de conta retificadora nenhuma: é simplesmente uma
    conta cuja natureza CADASTRADA (credora) diverge do lado que o
    movimento produziu.
    """
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-034 Inversão", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Inversão DL-034 Ltda", cnpj=_cnpj_sintetico()
    )
    # Caixa e Fornecedores entram cada um sob o PRÓPRIO pai não classificado
    # (Ativo/Passivo) — nunca como raízes soltas: a guarda nova do critério
    # 1 (condição 3, BL-496) considera IRMÃS quaisquer dois nós topo
    # classificados sob o MESMO ancestral (inclusive a ausência de pai, que
    # conta como um só "grupo" de raízes) — duas raízes soltas de tipo e
    # natureza DIFERENTES (Ativo devedora, Passivo credora) disparariam a
    # pendência por "natureza divergente entre irmãs" mesmo sem terem
    # nenhuma relação real entre si. Com um pai próprio para cada lado, a
    # única "irmã" de Caixa é ela mesma (Ativo só tem um filho), e o mesmo
    # vale para Fornecedores — o cenário fica limpo para testar SÓ a
    # inversão de sinal, sem tropeçar nessa guarda.
    ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    caixa = _conta(
        empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    passivo = _conta(
        empresa,
        codigo="2",
        nome="PASSIVO",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        aceita_lancamento=False,
    )
    fornecedores = _conta(
        empresa,
        codigo="2.1",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=passivo,
        classificacao=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
    )
    capital_social = _conta(
        empresa, codigo="3", nome="Capital Social", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C
    )
    hoje = timezone.localdate()
    _lancar(empresa, hoje, "Integralização de capital", caixa, capital_social, "1000.00")
    # Fornecedores nunca teve saldo credor — este débito produz saldo
    # DEVEDOR numa conta cadastrada CREDORA: o caso que a apresentação
    # precisa marcar entre parênteses, com "D" ao lado.
    _lancar(
        empresa, hoje, "Pagamento sem compra anterior registrada", fornecedores, caixa, "300.00"
    )
    return {"escritorio": escritorio, "empresa": empresa, "data_base": hoje}


@pytest.fixture
def cenario_com_resultado_nao_transferido():
    """Receita e Despesa movimentadas SEM lançamento de encerramento
    (RC-104) — `resultado_nao_transferido` fica 250,00 (300,00 de receita
    menos 50,00 de despesa), e a soma de Ativo (1.250,00) diverge da soma
    de Passivo + Patrimônio Líquido (1.000,00) só por causa disso. Receita
    e Despesa NUNCA entram na separação circulante/não circulante
    (RC-106) — não precisam de `classificacao_patrimonial` nenhuma — então
    este cenário continua com resíduo zero e `pode_emitir=True`.
    """
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-034 Resultado", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Resultado DL-034 Ltda", cnpj=_cnpj_sintetico()
    )
    caixa = _conta(
        empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    capital_social = _conta(
        empresa, codigo="2", nome="Capital Social", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C
    )
    receita = _conta(
        empresa, codigo="3", nome="Receita de Serviços", tipo=TipoConta.RECEITA, natureza=C
    )
    despesa = _conta(
        empresa, codigo="4", nome="Despesas Administrativas", tipo=TipoConta.DESPESA, natureza=D
    )
    hoje = timezone.localdate()
    _lancar(empresa, hoje, "Integralização de capital", caixa, capital_social, "1000.00")
    _lancar(empresa, hoje, "Prestação de serviço à vista", caixa, receita, "300.00")
    _lancar(empresa, hoje, "Pagamento de despesa", despesa, caixa, "50.00")
    return {"escritorio": escritorio, "empresa": empresa, "data_base": hoje}


# ---------------------------------------------------------------------------
# Permissão e isolamento (nível 1 — critérios 2 e 3 do plano)
# ---------------------------------------------------------------------------


def test_papel_sem_permissao_recebe_403_e_nenhum_valor_no_corpo(client, cenario_classificado):
    """Critério 2: papel CLIENTE (fora de PAPEIS_QUE_LEEM_CONTABILIDADE)
    recebe 403 — e o CORPO da resposta não carrega nenhum valor da
    apuração (lição do BL-211: código sozinho não prova nada)."""
    _autenticar(
        client, cenario_classificado["escritorio"], papel=Papel.CLIENTE, username="cliente-dl034"
    )
    url = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()
    assert "Seu papel não permite" in conteudo
    # Nenhum dos valores em reais da apuração vaza no corpo da recusa.
    for valor in ("8.000,00", "12.600,50", "1.800,50", "10.000,00"):
        assert valor not in conteudo, valor
    assert cenario_classificado["empresa"].razao_social not in conteudo


def test_empresa_de_outro_escritorio_da_404_sem_confirmar_existencia(client, cenario_classificado):
    """Critério 3: empresa de outro escritório nunca aparece — 404, sem
    confirmar nem a existência do registro."""
    outro_escritorio = Escritorio.objects.create(
        nome="Outro Escritório DL-034", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, outro_escritorio, username="gestor-outro-dl034")
    url = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 404
    assert cenario_classificado["empresa"].razao_social not in resposta.content.decode()


# ---------------------------------------------------------------------------
# Estados: vazio, erro
# ---------------------------------------------------------------------------


def test_estado_vazio_empresa_sem_plano_de_contas(client):
    escritorio = Escritorio.objects.create(nome="Escritório DL-034 Vazio", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Vazia DL-034 Ltda", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, escritorio, username="gestor-vazio-dl034")
    resposta = client.get(reverse("contabilidade_web:balanco", args=[empresa.id]))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "ainda não tem nenhuma conta cadastrada" in conteudo
    assert reverse("contabilidade_web:plano_de_contas", args=[empresa.id]) in conteudo
    # Nada de tabela nem de recusa: é o estado "nada para avaliar ainda".
    assert "NÃO pode ser emitido" not in conteudo


def test_data_base_invalida_retorna_400_com_saida_navegavel(client, cenario_classificado):
    _autenticar(client, cenario_classificado["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    resposta = client.get(url + "?data_base=abacaxi")
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "não pôde ser usada" in conteudo
    assert (
        reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id]) in conteudo
    )


# ---------------------------------------------------------------------------
# Recusa de emissão — critério 1: nomeando o que falta, sem montar tabela
# ---------------------------------------------------------------------------


def test_recusa_de_emissao_nomeia_a_conta_pendente_e_nao_monta_a_tabela(client, cenario_pendente):
    _autenticar(client, cenario_pendente["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_pendente["empresa"].id])
    resposta = client.get(url)
    # 200: a tela respondeu corretamente "não pode emitir, e eis o
    # porquê" — não é falha de protocolo.
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "NÃO pode ser emitido" in conteudo
    # A conta pendente é NOMEADA — código e nome, não um "há um erro" mudo.
    assert "Caixa Sem Classificação" in conteudo
    assert cenario_pendente["caixa"].codigo in conteudo
    # Caminho de correção visível.
    assert (
        reverse("contabilidade_web:plano_de_contas", args=[cenario_pendente["empresa"].id])
        in conteudo
    )
    # A tabela do Balanço NÃO existe nesta resposta — nenhum "Total do
    # Ativo" nem estrutura de grupo aparece enquanto houver pendência.
    assert "Total do Ativo" not in conteudo
    assert "<table" not in conteudo


def test_controle_positivo_base_completa_exige_emissao(client, cenario_classificado):
    """Controle positivo do critério 1: uma base COMPLETA (sem pendência
    nenhuma) EXIGE a emissão — não basta a ausência de recusa aparecer por
    acidente."""
    _autenticar(client, cenario_classificado["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "NÃO pode ser emitido" not in conteudo
    assert "Balanço pronto para emissão" in conteudo
    assert "<table" in conteudo


# ---------------------------------------------------------------------------
# Os cinco grupos da lei somam o Ativo e o Passivo (critério 5 do plano)
# ---------------------------------------------------------------------------


def test_os_cinco_grupos_da_lei_com_os_valores_certos(client, cenario_classificado):
    _autenticar(client, cenario_classificado["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    conteudo = client.get(url).content.decode()

    # Ativo Circulante: só Caixa, 10.000,00 - 2.000,00 = 8.000,00.
    assert "Ativo circulante" in conteudo
    assert "8.000,00" in conteudo

    # Os QUATRO subgrupos do Ativo Não Circulante, cada um com o SEU
    # próprio valor (nenhum dos quatro se repete, controle contra soma no
    # grupo errado).
    assert "Ativo não circulante — realizável a longo prazo" in conteudo
    assert "800,00" in conteudo
    assert "Ativo não circulante — investimentos" in conteudo
    assert "2.000,00" in conteudo
    assert "Ativo não circulante — imobilizado" in conteudo
    assert "1.500,00" in conteudo
    assert "Ativo não circulante — intangível" in conteudo
    assert "300,50" in conteudo

    # Subtotal do Ativo Não Circulante: 800 + 2.000 + 1.500 + 300,50 = 4.600,50.
    assert "4.600,50" in conteudo

    # Total do Ativo: 8.000 + 4.600,50 = 12.600,50.
    assert "Total do Ativo" in conteudo
    assert "12.600,50" in conteudo

    # Passivo Circulante (Fornecedores): 1.500 + 300,50 = 1.800,50.
    assert "Passivo circulante" in conteudo
    assert "1.800,50" in conteudo

    # Passivo Não Circulante (Financiamentos): 800,00.
    assert "Passivo não circulante" in conteudo

    # Patrimônio Líquido: Capital Social, 10.000,00 — o TERCEIRO grupo do
    # passivo, ao lado de Circulante/Não Circulante, nunca dentro deles.
    assert "Patrimônio Líquido" in conteudo
    assert "10.000,00" in conteudo

    # Total do Passivo + PL: 1.800,50 + 800,00 + 10.000,00 = 12.600,50 —
    # mesmo valor do Total do Ativo (a equação fecha).
    assert "Total do Passivo + Patrimônio Líquido" in conteudo
    assert conteudo.count("12.600,50") >= 2


def test_cada_subgrupo_tem_o_seu_proprio_valor_na_posicao_certa(client, cenario_classificado):
    """Guarda contra "somar o subgrupo errado": os QUATRO valores são
    DISTINTOS entre si de propósito (fixture), e este teste confere que
    cada valor aparece DEPOIS do título do subgrupo a que pertence e
    ANTES do título do subgrupo seguinte — não só "os quatro números
    aparecem em algum lugar da página", que passaria mesmo com a soma
    atribuída ao subgrupo errado.
    """
    _autenticar(client, cenario_classificado["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    conteudo = client.get(url).content.decode()

    ordem = [
        ("Ativo não circulante — realizável a longo prazo", "800,00"),
        ("Ativo não circulante — investimentos", "2.000,00"),
        ("Ativo não circulante — imobilizado", "1.500,00"),
        ("Ativo não circulante — intangível", "300,50"),
    ]
    posicao_anterior = conteudo.index("Ativo não circulante — realizável a longo prazo")
    for titulo, valor in ordem:
        posicao_titulo = conteudo.index(titulo, posicao_anterior)
        posicao_valor = conteudo.index(valor, posicao_titulo)
        proximo_titulo = conteudo.find("Ativo não circulante", posicao_titulo + len(titulo))
        if proximo_titulo != -1:
            assert posicao_valor < proximo_titulo, (
                f"{valor!r} apareceu DEPOIS do próximo título de subgrupo — "
                "sinal de que foi somado no grupo errado"
            )
        posicao_anterior = posicao_titulo


# ---------------------------------------------------------------------------
# Apresentação: D/C, parênteses, sem cor sozinha
# ---------------------------------------------------------------------------


def test_saldo_invertido_aparece_entre_parenteses_com_letra_d(client, cenario_com_inversao):
    _autenticar(client, cenario_com_inversao["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_com_inversao["empresa"].id])
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Balanço pronto para emissão" in conteudo
    # A CONTA Fornecedores (credora, saldo devedor de 300,00): parênteses
    # em volta do valor, nunca só cor — RC-90/direção de arte. O HTML de
    # origem tem uma tag ABRINDO entre "(" e o número
    # (`_saldo.html`/`_saldo_grupo.html`: `<span class="valor-invertido">(
    # <span class="valor-monetario">valor</span>)</span>`), então a
    # asserção confere o MARCADOR da abertura, não a string "(300,00)"
    # inteira, que nunca existe contígua no HTML servido (só no texto
    # renderizado que o navegador mostra).
    assert 'class="valor-invertido">(' in conteudo
    assert "300,00" in conteudo
    # A letra "D" acompanha o valor, em texto — nunca só a cor.
    assert ">D<" in conteudo


def test_resultado_nao_transferido_aparece_como_ressalva_honesta(
    client, cenario_com_resultado_nao_transferido
):
    """ "Eu sei o que ele NÃO diz": quando Total do Ativo e Total do
    Passivo + PL divergem por causa de resultado ainda não transferido
    (RC-104), a tela EXPLICA a diferença em vez de deixar duas somas
    incompatíveis no papel sem nenhuma palavra."""
    _autenticar(client, cenario_com_resultado_nao_transferido["escritorio"])
    url = reverse(
        "contabilidade_web:balanco",
        args=[cenario_com_resultado_nao_transferido["empresa"].id],
    )
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Balanço pronto para emissão" in conteudo
    assert "Lucro" in conteudo
    assert "250,00" in conteudo
    assert "ainda não transferido ao Patrimônio Líquido" in conteudo
    # As duas somas realmente aparecem DIFERENTES — 1.250,00 (Ativo) e
    # 1.000,00 (Passivo + PL) — é a divergência que o texto acima explica.
    assert "1.250,00" in conteudo
    assert "1.000,00" in conteudo


# ---------------------------------------------------------------------------
# O bloco de identificação do item 51 (RC-95) — critério 4 do plano
# ---------------------------------------------------------------------------


def test_bloco_de_identificacao_do_item_51_no_html(client, cenario_classificado):
    """Os CINCO campos do item 51 aparecem no corpo do documento: nome da
    entidade (a), individual/grupo (b), data-base (c), moeda (d) e nível
    de arredondamento (e). A repetição em TODA página impressa (item 52) é
    medida no navegador real — ver o relatório da etapa; este teste cobre
    só a PRESENÇA do conteúdo no HTML servido."""
    _autenticar(client, cenario_classificado["escritorio"])
    empresa = cenario_classificado["empresa"]
    url = reverse("contabilidade_web:balanco", args=[empresa.id])
    conteudo = client.get(url).content.decode()

    assert 'class="identificacao-do-documento"' in conteudo
    # (a) nome da entidade e CNPJ (RC-93).
    assert empresa.razao_social in conteudo
    assert empresa.cnpj[0:2] in conteudo  # o CNPJ mascarado contém o original
    # (b) individual ou de grupo.
    assert "Individual" in conteudo
    # (c) data-base.
    assert cenario_classificado["data_base"].strftime("%d/%m/%Y") in conteudo
    # (d) moeda de apresentação.
    assert "Real (R$)" in conteudo
    # (e) nível de arredondamento.
    assert "unidade de real, com centavos" in conteudo.lower()


# ---------------------------------------------------------------------------
# Acessibilidade estrutural própria desta tela (a varredura de
# apps/core/tests/test_dl024_varredura_de_interface.py já cobre <caption>,
# <th scope>, classe "valor-monetario" e ausência de cor/medida solta em
# QUALQUER template novo, incluindo os três desta etapa — não repetido
# aqui).
# ---------------------------------------------------------------------------


def test_nenhuma_tela_do_balanco_usa_javascript(client, cenario_classificado, cenario_pendente):
    _autenticar(client, cenario_classificado["escritorio"], username="gestor-js-1")
    url_completa = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    assert "<script" not in client.get(url_completa).content.decode().lower()

    _autenticar(client, cenario_pendente["escritorio"], username="gestor-js-2")
    url_pendente = reverse("contabilidade_web:balanco", args=[cenario_pendente["empresa"].id])
    assert "<script" not in client.get(url_pendente).content.decode().lower()


# ---------------------------------------------------------------------------
# BL-504 (auditoria DL-034, achado A6) — "Balanço pronto para emissão" é
# estado de fluxo interno, não conteúdo da demonstração: permanece na
# TELA, sai do documento IMPRESSO. Este arquivo confere só a metade da
# tela (o HTML servido tem de carregar o gancho de CSS que esconde o
# bloco na impressão); a metade da IMPRESSÃO em si é medida no navegador
# real — ver o relatório da etapa e `scripts/medir_identificacao_do_
# emitente.py` (BL-501), que exporta o PDF de verdade.
# ---------------------------------------------------------------------------


def test_balanco_pronto_para_emissao_aparece_na_tela_com_o_gancho_de_somente_tela(
    client, cenario_classificado
):
    _autenticar(client, cenario_classificado["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_classificado["empresa"].id])
    conteudo = client.get(url).content.decode()
    assert "Balanço pronto para emissão" in conteudo
    # `faixa-fechamento--somente-tela` é o seletor que static/css/base.css
    # esconde dentro de `@media print` — SEM esta classe, o texto sairia
    # no papel (é exatamente o que a versão anterior fazia). Este teste
    # NÃO mede a impressão em si (o HTML servido nunca aplica CSS) — só
    # que o gancho existe no corpo.
    assert 'class="faixa-fechamento faixa-fechamento--somente-tela"' in conteudo


# ---------------------------------------------------------------------------
# BL-508 (auditoria DL-034, achado A10) — a lista de pendência não mostra
# nome cru de campo (`classificacao_patrimonial`, `natureza`, `conta_pai`,
# `tipo`), e toda pendência declarada nomeia uma ação que RESOLVE
# (correção 4 do auditor: "explica" tem de ser verificável).
# ---------------------------------------------------------------------------

# Substrings que NUNCA podem aparecer no corpo — o NOME CRU do campo do
# banco (nunca a palavra em português comum: "tipo" sozinho apareceria em
# "Tipo cadastrado", que É esperado) e os valores em snake_case dos três
# enums envolvidos (a versão HUMANIZADA usa maiúscula e espaço — "Ativo
# circulante", "Devedora" — nunca colide com o valor cru).
_FRAGMENTOS_CRUS_PROIBIDOS_NO_CORPO = (
    "classificacao_patrimonial:",
    "classificacao_patrimonial_ancestral:",
    "natureza:",
    "conta_pai:",
    "tipo:",
    "tipo_da_raiz:",
    "ativo_circulante",
    "ativo_nao_circulante",
    "passivo_circulante",
    "passivo_nao_circulante",
    "patrimonio_liquido",
)


def _assert_sem_nome_cru_de_campo_no_corpo(conteudo):
    minusculo = conteudo.lower()
    encontrados = [frag for frag in _FRAGMENTOS_CRUS_PROIBIDOS_NO_CORPO if frag in minusculo]
    assert not encontrados, f"nome(s) cru(s) de campo/valor no corpo HTTP: {encontrados}"


def test_pendencia_por_tipo_sem_classificacao_nao_mostra_nome_cru_de_campo(
    client, cenario_pendente
):
    """`cenario_pendente` dispara `contas_sem_classificacao_patrimonial`,
    cujo item extra é `"tipo": TipoConta.ATIVO` (valor cru `"ativo"`) —
    confere que a tela mostra "Tipo cadastrado: Ativo", nunca "tipo:
    ativo"."""
    _autenticar(client, cenario_pendente["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[cenario_pendente["empresa"].id])
    conteudo = client.get(url).content.decode()
    assert resposta_status_ok_e_pendente(conteudo)
    _assert_sem_nome_cru_de_campo_no_corpo(conteudo)
    assert "Tipo cadastrado: Ativo" in conteudo
    # A ação que resolve ESTA lista específica (BL-508, critério "explica
    # é verificável") tem de estar no corpo — não só um link genérico.
    assert (
        "Classificar a conta (ou um ancestral dela) como circulante ou não circulante" in conteudo
    )


def resposta_status_ok_e_pendente(conteudo):
    return "O Balanço NÃO pode ser emitido nesta data-base" in conteudo


@pytest.fixture
def cenario_com_aviso_de_natureza_divergente():
    """Duas contas IRMÃS (mesmo `conta_pai`, um contêiner "Ativo
    Circulante" NUNCA classificado), cada uma topo-classificada
    independentemente como `ativo_circulante`, com natureza CADASTRADA
    divergente — a topologia exata do BL-486 (Clientes D / "(-) PDD" C).
    Desde a DE-070, isto é só AVISO (`contas_topo_classificadas_com_
    natureza_divergente_entre_irmas`) — não veta a emissão. Nenhuma outra
    lista de pendência dispara (nenhum lançamento toca Receita/Despesa,
    nenhuma conta fica sem classificação, nenhum nó não-folha recebe
    movimento próprio), e a equação fecha:

        Ativo    = Clientes (1.220,00 D) − PDD (50,00 C, contra) +
                   Investimentos (500,00 D)                       = 1.670,00
        Passivo  = Fornecedores (500,00 C)                        =   500,00
        PL       = Capital Social (1.220,00 C − 50,00 D)          = 1.170,00
        Passivo + PL                                              = 1.670,00  ✅
    """
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-034 Aviso Natureza", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Aviso Natureza Divergente DL-034 Ltda",
        cnpj=_cnpj_sintetico(),
    )
    ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    # O CONTÊINER nunca é classificado — só as duas FOLHAS, abaixo (senão
    # dispararia `contas_com_classificacao_aninhada`, um veto de verdade).
    circulante = _conta(
        empresa,
        codigo="1.1",
        nome="Ativo Circulante",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        aceita_lancamento=False,
    )
    clientes = _conta(
        empresa,
        codigo="1.1.01",
        nome="Clientes",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=circulante,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    pdd = _conta(
        empresa,
        codigo="1.1.02",
        nome="(-) Provisão para Devedores Duvidosos",
        tipo=TipoConta.ATIVO,
        natureza=C,
        pai=circulante,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    investimentos = _conta(
        empresa,
        codigo="1.2",
        nome="Investimentos",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS,
    )
    passivo = _conta(
        empresa,
        codigo="2",
        nome="PASSIVO",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        aceita_lancamento=False,
    )
    fornecedores = _conta(
        empresa,
        codigo="2.1",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=passivo,
        classificacao=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
    )
    capital_social = _conta(
        empresa, codigo="3", nome="Capital Social", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C
    )
    hoje = timezone.localdate()
    # Só contas de BALANÇO (Ativo/Passivo/PL) — nenhum lançamento toca
    # Receita/Despesa, para `resultado_nao_transferido` ficar ZERO e não
    # acrescentar uma ressalva (BL-503) que não é o que este teste mede.
    _lancar(empresa, hoje, "Integralização de capital", clientes, capital_social, "1220.00")
    _lancar(empresa, hoje, "Provisão para devedores duvidosos", capital_social, pdd, "50.00")
    _lancar(
        empresa, hoje, "Aplicação em investimento a prazo", investimentos, fornecedores, "500.00"
    )
    return {"escritorio": escritorio, "empresa": empresa, "data_base": hoje}


def test_lista_que_so_avisa_nao_bloqueia_e_a_tela_emite_mostrando_o_aviso(
    client, cenario_com_aviso_de_natureza_divergente
):
    """DE-070/critério de aceite 6 da correção: a condição 3 deixou de
    vetar — a tela mostra os GRUPOS (emite de verdade, "Total do Ativo"
    presente) e exibe o aviso, nunca como "Erro" bloqueante."""
    _autenticar(client, cenario_com_aviso_de_natureza_divergente["escritorio"])
    url = reverse(
        "contabilidade_web:balanco",
        args=[cenario_com_aviso_de_natureza_divergente["empresa"].id],
    )
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()

    # Emitiu de verdade — a tabela foi montada, não só "não foi recusada".
    assert "Total do Ativo" in conteudo
    assert "Total do Passivo + Patrimônio Líquido" in conteudo
    assert "O Balanço NÃO pode ser emitido nesta data-base" not in conteudo

    # O aviso aparece — mas como AVISO, nunca como "Erro" bloqueante.
    assert "<strong>Aviso:</strong> não impede a emissão do Balanço." in conteudo
    assert "mensagem mensagem-warning" in conteudo
    assert "Clientes" in conteudo
    assert "(-) Provisão para Devedores Duvidosos" in conteudo
    # A ação (confirmar, não necessariamente corrigir — é aviso) está no
    # corpo, e nomeia o caminho de correção SE for de fato um erro.
    assert "Confira se a natureza cadastrada de cada conta abaixo está correta" in conteudo

    _assert_sem_nome_cru_de_campo_no_corpo(conteudo)


def test_lista_que_so_avisa_continua_visivel_mesmo_quando_outra_pendencia_bloqueia(
    client, cenario_com_aviso_de_natureza_divergente
):
    """O aviso não fica escondido só porque, NA MESMA apuração, alguma
    OUTRA lista também está pendente e bloqueia — cria uma conta extra,
    sem classificação, com saldo (dispara `contas_sem_classificacao_
    patrimonial`, que VETA) ao lado da topologia do BL-486 (que só
    avisa). O aviso tem de continuar aparecendo, fora do bloco "Erro"."""
    empresa = cenario_com_aviso_de_natureza_divergente["empresa"]
    hoje = cenario_com_aviso_de_natureza_divergente["data_base"]
    conta_pendente = _conta(
        empresa,
        codigo="4",
        nome="Máquinas Sem Classificação",
        tipo=TipoConta.ATIVO,
        natureza=D,
    )
    capital_social = Conta.objects.get(empresa=empresa, codigo="3")
    _lancar(
        empresa, hoje, "Compra de máquina sem classificar", conta_pendente, capital_social, "10.00"
    )

    _autenticar(client, cenario_com_aviso_de_natureza_divergente["escritorio"])
    url = reverse("contabilidade_web:balanco", args=[empresa.id])
    conteudo = client.get(url).content.decode()

    assert "O Balanço NÃO pode ser emitido nesta data-base" in conteudo
    assert "Total do Ativo" not in conteudo  # não emitiu — outra lista vetou
    # O AVISO continua presente, FORA do bloco de erro.
    assert "<strong>Aviso:</strong> não impede a emissão do Balanço." in conteudo
    assert "Clientes" in conteudo and "(-) Provisão para Devedores Duvidosos" in conteudo
    _assert_sem_nome_cru_de_campo_no_corpo(conteudo)
