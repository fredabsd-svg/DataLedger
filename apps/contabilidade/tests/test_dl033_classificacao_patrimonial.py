"""DL-033, fatia 1 — o CAMPO de classificação circulante × não circulante
(`Conta.classificacao_patrimonial`) e as duas guardas do modelo.

Cobre os critérios 1, 2 e 3 do plano
(`docs/planos/DL-033-circulante-e-nao-circulante.md`):

1. Os grupos vêm de uma fonte única (`ClassificacaoPatrimonial`, derivado do
   modelo) — nunca uma tupla escrita à mão (DE-056).
2. Mudar a classificação de conta COM movimento é recusado, no MODELO —
   tanto movimento PRÓPRIO quanto movimento SÓ DE DESCENDENTE (a segunda
   forma que escapou na BL-83/DL-023).
3. Conta SEM movimento reclassifica livremente (controle positivo).

A guarda de CONSISTÊNCIA (classificação compatível com o `tipo` da conta —
RC-106: só Ativo e Passivo se dividem em circulante/não circulante) também é
testada aqui, por ser parte do mesmo `clean()`.

Prova via `full_clean()` DIRETO (não via admin/requisição): é o que o plano
pede — "guarda no modelo" — e é o mesmo nível de prova que
`test_dl023_conta_nao_muda_de_empresa_ou_natureza.py` usa para a metade que
não depende do `ModelForm` do admin.

Dados 100% sintéticos, criados nos próprios testes.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.contabilidade.models import (
    GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL,
    NATUREZA_NATURAL_DO_TIPO,
    TIPO_DA_CLASSIFICACAO_PATRIMONIAL,
    ClassificacaoPatrimonial,
    Conta,
    GrupoDaLei,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório DL-033", cnpj="10101010000199")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-033 Ltda", cnpj="10111213000155"
    )


def _conta(empresa, *, codigo, nome="Conta", tipo=TipoConta.ATIVO, natureza=D, pai=None):
    return Conta.objects.create(
        empresa=empresa, conta_pai=pai, codigo=codigo, nome=nome, tipo=tipo, natureza=natureza
    )


def _com_movimento_proprio(empresa, conta):
    """Dá movimento PRÓPRIO a `conta`: um lançamento balanceado contra uma
    contrapartida descartável da mesma empresa."""
    contrapartida = _conta(
        empresa, codigo=f"contra-{conta.codigo}", tipo=TipoConta.RECEITA, natureza=C
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 1, 15),
        historico="DL-033 movimento",
        itens=[
            {"conta": conta, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": contrapartida, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    return conta


# ---------------------------------------------------------------------------
# Critério 1 — os grupos vêm de uma fonte única (DE-056)
# ---------------------------------------------------------------------------


def test_mapa_tipo_da_classificacao_cobre_exatamente_os_valores_do_enum():
    """Teste DERIVADO: se um `ClassificacaoPatrimonial` novo nascer sem
    entrada em `TIPO_DA_CLASSIFICACAO_PATRIMONIAL`, este teste reprova
    NOMEANDO o valor esquecido — nunca um `KeyError`/`None` silencioso na
    guarda de consistência nem na camada de saldos. Mesmo padrão que a
    DL-032 já usa para `TipoConta.values`."""
    assert set(TIPO_DA_CLASSIFICACAO_PATRIMONIAL.keys()) == set(ClassificacaoPatrimonial.values), (
        f"valor(es) de ClassificacaoPatrimonial sem entrada no mapa: "
        f"{set(ClassificacaoPatrimonial.values) - set(TIPO_DA_CLASSIFICACAO_PATRIMONIAL.keys())}"
    )
    # Controle positivo do sentido da lei (RC-106): só ATIVO e PASSIVO
    # aparecem como valor do mapa — Patrimônio Líquido, Receita e Despesa
    # nunca são o tipo esperado de nenhuma classificação.
    assert set(TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values()) == {TipoConta.ATIVO, TipoConta.PASSIVO}


def test_todo_valor_de_grupo_da_lei_mapeia_para_o_mesmo_lado_do_tipo():
    """Controle cruzado (BL-490, achado A5: "nenhum `startswith` sobre
    valor de classificação sobra em código nem em teste") — substitui o
    antigo cross-check por prefixo de string por um que compara os DOIS
    mapas derivados entre si: para cada `ClassificacaoPatrimonial`, o
    `GrupoDaLei` correspondente (`GRUPO_DA_LEI_DA_CLASSIFICACAO_
    PATRIMONIAL`) começa com "ativo_" se e somente se o `TipoConta`
    correspondente (`TIPO_DA_CLASSIFICACAO_PATRIMONIAL`) é `ATIVO` — os
    dois mapas, escritos independentemente, precisam concordar."""
    for classificacao, tipo_esperado in TIPO_DA_CLASSIFICACAO_PATRIMONIAL.items():
        grupo = GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL[classificacao]
        grupo_e_do_lado_do_ativo = grupo in (
            GrupoDaLei.ATIVO_CIRCULANTE,
            GrupoDaLei.ATIVO_NAO_CIRCULANTE,
        )
        assert grupo_e_do_lado_do_ativo == (tipo_esperado == TipoConta.ATIVO), (
            classificacao,
            grupo,
            tipo_esperado,
        )


def test_mapa_natureza_natural_cobre_exatamente_os_tipos_classificaveis():
    """BL-496 (DL-034, critério 1, opção (b)) — teste DERIVADO no mesmo
    molde de `test_mapa_tipo_da_classificacao_cobre_exatamente_os_valores_
    do_enum`: `NATUREZA_NATURAL_DO_TIPO` tem entrada para EXATAMENTE os
    `TipoConta` que participam da separação circulante/não circulante — os
    mesmos de `TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values()`, nem mais nem
    menos — e a convenção contábil certa: devedora no Ativo, credora no
    Passivo (Lei 6.404/76)."""
    assert set(NATUREZA_NATURAL_DO_TIPO.keys()) == set(TIPO_DA_CLASSIFICACAO_PATRIMONIAL.values())
    assert NATUREZA_NATURAL_DO_TIPO[TipoConta.ATIVO] == NaturezaConta.DEVEDORA
    assert NATUREZA_NATURAL_DO_TIPO[TipoConta.PASSIVO] == NaturezaConta.CREDORA


def test_classificacao_nao_circulante_mapeia_somente_para_grupo_nao_circulante():
    """BL-497 (RESSALVA R2 da rodada 2 de auditoria da DL-033, mutação M5):
    o cruzamento acima só confere o LADO (Ativo × Passivo) — apontar o
    Imobilizado para `GrupoDaLei.ATIVO_CIRCULANTE` (lado CERTO, GRUPO
    errado — imprime o imobilizado dentro do subtotal do circulante,
    erro de norma) passava em 1.622 testes, porque nenhum cruzamento
    conferia CIRCULANTE × NÃO CIRCULANTE, só ATIVO × PASSIVO.

    Este cruzamento novo fecha essa porta: pelos NOMES dos membros do
    enum (`.name`, nunca `.value`), sem `startswith` — toda
    `ClassificacaoPatrimonial` cujo NOME contém "NAO_CIRCULANTE" mapeia
    para um `GrupoDaLei` cujo NOME também contém "NAO_CIRCULANTE", e
    vice-versa. Mutar UMA linha do mapa (ex.: apontar o imobilizado para
    `GrupoDaLei.ATIVO_CIRCULANTE`) reprova este teste."""
    for classificacao in ClassificacaoPatrimonial:
        grupo = GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL[classificacao]
        classificacao_e_nao_circulante = "NAO_CIRCULANTE" in classificacao.name
        grupo_e_nao_circulante = "NAO_CIRCULANTE" in grupo.name
        assert classificacao_e_nao_circulante == grupo_e_nao_circulante, (classificacao, grupo)


# ---------------------------------------------------------------------------
# Guarda de CONSISTÊNCIA: classificação compatível com o tipo (RC-106)
# ---------------------------------------------------------------------------


def test_classificacao_ativa_em_conta_de_tipo_ativo_e_aceita(empresa):
    """Sucesso: os cinco valores de Ativo (circulante + quatro subgrupos)
    em conta de `tipo=ATIVO` — nenhum levanta."""
    for indice, (classificacao, tipo_esperado) in enumerate(
        TIPO_DA_CLASSIFICACAO_PATRIMONIAL.items()
    ):
        if tipo_esperado != TipoConta.ATIVO:
            continue
        conta = Conta(
            empresa=empresa,
            codigo=f"1.{indice}",
            nome="Conta",
            tipo=TipoConta.ATIVO,
            natureza=D,
            classificacao_patrimonial=classificacao,
        )
        conta.full_clean()  # não levanta


def test_classificacao_passiva_em_conta_de_tipo_passivo_e_aceita(empresa):
    for indice, (classificacao, tipo_esperado) in enumerate(
        TIPO_DA_CLASSIFICACAO_PATRIMONIAL.items()
    ):
        if tipo_esperado != TipoConta.PASSIVO:
            continue
        conta = Conta(
            empresa=empresa,
            codigo=f"2.{indice}",
            nome="Conta",
            tipo=TipoConta.PASSIVO,
            natureza=C,
            classificacao_patrimonial=classificacao,
        )
        conta.full_clean()  # não levanta


def test_classificacao_ativa_em_conta_de_tipo_passivo_e_recusada(empresa):
    """Erro: RC-106 não permite "Ativo Circulante" numa conta de Passivo —
    a guarda de consistência recusa mesmo em conta NOVA, sem movimento."""
    conta = Conta(
        empresa=empresa,
        codigo="1",
        nome="Conta",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        classificacao_patrimonial=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()
    assert "Ativo" in str(excinfo.value)


def test_classificacao_em_conta_de_patrimonio_liquido_e_recusada(empresa):
    """RC-106: Patrimônio Líquido é o TERCEIRO grupo do passivo, fora da
    separação circulante/não circulante — não pode receber nenhum valor de
    `ClassificacaoPatrimonial`."""
    conta = Conta(
        empresa=empresa,
        codigo="3",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_patrimonial=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
    )
    with pytest.raises(ValidationError):
        conta.full_clean()


def test_classificacao_em_conta_de_despesa_e_recusada(empresa):
    """RC-106: Receita e Despesa não fazem parte do Balanço Patrimonial."""
    conta = Conta(
        empresa=empresa,
        codigo="5",
        nome="Despesas Gerais",
        tipo=TipoConta.DESPESA,
        natureza=D,
        classificacao_patrimonial=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
    )
    with pytest.raises(ValidationError):
        conta.full_clean()


def test_conta_sem_classificacao_nenhuma_e_sempre_aceita(empresa):
    """Controle positivo: `classificacao_patrimonial=None` (o padrão de
    TODA conta nova, qualquer que seja o tipo) nunca é recusado pela
    guarda de consistência — é exatamente o estado em que toda conta
    existente nasce nesta etapa (nenhuma migração classifica nada)."""
    for indice, (tipo, natureza) in enumerate(
        (
            (TipoConta.ATIVO, D),
            (TipoConta.PASSIVO, C),
            (TipoConta.PATRIMONIO_LIQUIDO, C),
            (TipoConta.RECEITA, C),
            (TipoConta.DESPESA, D),
        )
    ):
        conta = Conta(
            empresa=empresa,
            codigo=f"9.{indice}",
            nome="Conta",
            tipo=tipo,
            natureza=natureza,
        )
        conta.full_clean()  # não levanta


# ---------------------------------------------------------------------------
# Critério 2 — mudar a classificação de conta COM MOVIMENTO é recusado
# ---------------------------------------------------------------------------


def test_full_clean_recusa_mudar_classificacao_de_conta_com_movimento_proprio(empresa):
    """Movimento PRÓPRIO: a forma mais simples do critério 2."""
    conta = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D)
    conta.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    conta.full_clean()
    conta.save()
    _com_movimento_proprio(empresa, conta)

    conta.classificacao_patrimonial = (
        ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO
    )
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    mensagem = str(excinfo.value)
    assert "classificação" in mensagem
    # A mensagem nomeia o caminho CERTO — reclassificação por lançamento —
    # não "estorne", que é o caminho de natureza/tipo (guarda diferente,
    # HI-18): confirma que a mensagem é PRÓPRIA desta guarda, não a
    # reaproveitada do BL-83.
    assert "RECLASSIFICAÇÃO" in mensagem
    conta.refresh_from_db()
    assert conta.classificacao_patrimonial == ClassificacaoPatrimonial.ATIVO_CIRCULANTE


def test_full_clean_recusa_apagar_classificacao_de_conta_com_movimento(empresa):
    """A guarda também recusa a TERCEIRA forma de mexer no campo: apagar
    (valor -> `None`) uma classificação já declarada de conta com
    movimento. Diferente de "primeira classificação" (`None` -> valor,
    sempre livre — ver o teste de controle logo abaixo), apagar uma
    classificação já usada num Balanço reescreveria aquele Balanço em
    silêncio."""
    conta = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D)
    conta.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    conta.full_clean()
    conta.save()
    _com_movimento_proprio(empresa, conta)

    conta.classificacao_patrimonial = None
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    assert "classificação" in str(excinfo.value)
    conta.refresh_from_db()
    assert conta.classificacao_patrimonial == ClassificacaoPatrimonial.ATIVO_CIRCULANTE


def test_full_clean_recusa_mudar_classificacao_de_conta_com_movimento_so_de_descendente(empresa):
    """Movimento SÓ DE DESCENDENTE (não próprio) — a forma que ESCAPOU na
    primeira versão da guarda de natureza/tipo (BL-83) e só foi corrigida
    numa rodada seguinte. A conta `pai` aqui nunca recebe lançamento
    nenhum: só a filha tem movimento, e mesmo assim a reclassificação do
    PAI precisa ser recusada — senão o saldo CONSOLIDADO da filha (regra
    única de saldo, DE-020) muda de grupo no Balanço sem nenhum lançamento
    novo."""
    pai = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D)
    pai.aceita_lancamento = False
    pai.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    pai.full_clean()
    pai.save()
    filha = _conta(empresa, codigo="1.1", pai=pai, tipo=TipoConta.ATIVO, natureza=D)
    _com_movimento_proprio(empresa, filha)
    assert not pai.itens_lancamento.exists()  # sem movimento PRÓPRIO — é o ponto do teste

    pai.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO
    with pytest.raises(ValidationError) as excinfo:
        pai.full_clean()

    assert "classificação" in str(excinfo.value)
    pai.refresh_from_db()
    assert pai.classificacao_patrimonial == ClassificacaoPatrimonial.ATIVO_CIRCULANTE


def test_full_clean_recusa_mudar_classificacao_de_neta_com_bisneta_movimentada(empresa):
    """Profundidade > 1, no mesmo espírito de
    `test_admin_recusa_trocar_natureza_de_neta_com_bisneta_movimentada`
    (DL-023): a guarda precisa alcançar QUALQUER descendente, não só
    filhos diretos."""
    avo = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D)
    avo.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    avo.full_clean()
    avo.save()
    pai = _conta(empresa, codigo="1.1", pai=avo, tipo=TipoConta.ATIVO, natureza=D)
    neta = _conta(empresa, codigo="1.1.1", pai=pai, tipo=TipoConta.ATIVO, natureza=D)
    _com_movimento_proprio(empresa, neta)

    avo.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS
    with pytest.raises(ValidationError):
        avo.full_clean()


# ---------------------------------------------------------------------------
# Critério 3 — conta SEM movimento reclassifica livremente (controle positivo)
# ---------------------------------------------------------------------------


def test_full_clean_aceita_mudar_classificacao_de_conta_sem_movimento(empresa):
    """Controle positivo: sem ele, a guarda acima poderia estar recusando
    TUDO (bug que recusa sempre) e nenhum teste perceberia."""
    conta = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D)
    conta.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    conta.full_clean()
    conta.save()
    assert not conta._tem_movimento_proprio_ou_de_descendente()

    conta.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL
    conta.full_clean()  # não levanta
    conta.save()
    conta.refresh_from_db()
    assert (
        conta.classificacao_patrimonial == ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL
    )


def test_full_clean_aceita_classificar_conta_pela_primeira_vez_mesmo_com_movimento(empresa):
    """Controle positivo importante: a guarda é de TRANSIÇÃO (só dispara
    quando o valor GRAVADO muda — mesmo padrão do BL-245 para
    natureza/tipo). Uma conta com movimento que ainda NÃO tem
    classificação (o estado em que toda conta migrada nesta etapa nasce)
    pode RECEBER a primeira classificação livremente — senão o produto
    nunca conseguiria classificar o plano de contas já em uso."""
    conta = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D)
    conta.save()
    _com_movimento_proprio(empresa, conta)
    assert conta.classificacao_patrimonial is None

    conta.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    conta.full_clean()  # não levanta: None -> valor é a PRIMEIRA classificação, não uma TROCA
    conta.save()
    conta.refresh_from_db()
    assert conta.classificacao_patrimonial == ClassificacaoPatrimonial.ATIVO_CIRCULANTE


def test_full_clean_aceita_gravar_sem_mudar_a_classificacao_mesmo_com_movimento(empresa):
    """Controle positivo: salvar a conta SEM tocar
    `classificacao_patrimonial` (ex.: só renomeando) nunca dispara esta
    guarda, mesmo com movimento — mesmo padrão do achado novo 14 da DL-023
    (rodada 2) para `aceita_lancamento`."""
    conta = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D)
    conta.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    conta.full_clean()
    conta.save()
    _com_movimento_proprio(empresa, conta)

    conta.nome = "Caixa e Equivalentes"  # não toca a classificação
    conta.full_clean()  # não levanta


# ---------------------------------------------------------------------------
# BL-494 (achado A9 da auditoria) — o campo entra em list_display e em
# list_filter do admin: é a única porta, antes da tela do Balanço, por onde
# o contador consegue VER quais contas ainda faltam classificar.
# ---------------------------------------------------------------------------


SENHA_ADMIN = "senha-forte-dl033"


def _login_admin(client, usuario):
    assert client.login(username=usuario.username, password=SENHA_ADMIN)


def test_admin_changelist_mostra_a_classificacao_na_lista(client, empresa):
    admin_user = get_user_model().objects.create_superuser(
        username="admin-dl033-bl494",
        email="admin-dl033-bl494@escritorio.com.br",
        password=SENHA_ADMIN,
    )
    conta = _conta(empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D, nome="Caixa")
    conta.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    conta.full_clean()
    conta.save()
    _login_admin(client, admin_user)

    resposta = client.get("/admin/contabilidade/conta/")

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    corpo = resposta.content.decode()
    # A coluna da lista mostra o RÓTULO da classificação, não o valor cru.
    assert "Ativo circulante" in corpo, corpo


def test_admin_changelist_filtra_contas_sem_classificacao(client, empresa):
    """O filtro `EmptyFieldListFilter` sobre `classificacao_patrimonial`
    (BL-494) é o que permite achar as NÃO classificadas pelo admin — a
    única porta existente até a tela do Balanço nascer."""
    admin_user = get_user_model().objects.create_superuser(
        username="admin-dl033-bl494-filtro",
        email="admin-dl033-bl494-filtro@escritorio.com.br",
        password=SENHA_ADMIN,
    )
    classificada = _conta(
        empresa, codigo="1", tipo=TipoConta.ATIVO, natureza=D, nome="Caixa Classificado"
    )
    classificada.classificacao_patrimonial = ClassificacaoPatrimonial.ATIVO_CIRCULANTE
    classificada.full_clean()
    classificada.save()
    _conta(empresa, codigo="2", tipo=TipoConta.ATIVO, natureza=D, nome="Estoque Sem Classificar")
    _login_admin(client, admin_user)

    resposta = client.get(
        "/admin/contabilidade/conta/", {"classificacao_patrimonial__isempty": "1"}
    )

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    corpo = resposta.content.decode()
    assert "Estoque Sem Classificar" in corpo, corpo
    assert "Caixa Classificado" not in corpo, corpo
