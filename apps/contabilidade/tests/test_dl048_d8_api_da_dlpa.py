"""DL-048, **fatia D8** — a porta de API da DLPA: `DlpaView` (GET),
`ContaClassificacaoDlpaView` (PATCH) e `ContaSerializer.classificacao_dlpa`.

A tela e o serviço já foram entregues na fatia CTB-12/CTB-13 (PR #59). Esta
fatia **revela**: não duplica regra de apuração, nem autorização, nem
isolamento — cada uma delas já é decidida no serviço e na camada de
permissões, e o teste abaixo aponta para lá quando o assunto é outro.

Cobre os doze critérios do plano
(docs/planos/DL-048-fatia-d8-api-da-dlpa.md):

- R1  GET exige `PodeLerContabilidade`; 403 e NENHUM valor na resposta
- R2  GET 404 para empresa de outro escritório (isolamento)
- R3  409 quando `pode_emitir` é falso — e o corpo traz o número assim mesmo
- R4  dinheiro como string de duas casas, nunca float
- R5  `paragrafo_2` SEMPRE presente, com a pendência do dividendo por ação
- R6  PATCH exige `PodeEscriturar`; 403 sem ele
- R7  PATCH 404 para conta de outra empresa
- R8  corpo malformado → 400, nunca 500 (o R3 da auditoria DL-045)
- R9  PATCH grava e devolve a conta com a classificação
- R10 PATCH registra trilha com o valor antes e o de depois
- R11 incompatibilidade de tipo é 400 nomeando linha e tipo aceito
- R12 `""` e `null` removem a classificação, sem erro

**O desenho que o Fred pediu** — a DLPA pode estar EMBUTIDA na DMPL (Lei
6.404/76, art. 186, §2º) e não só como peça autônoma — aparece em R5 e em
`test_a_chave_da_linha_e_o_contrato_com_a_dmpl`: a chave estruturada da linha
é o que a CTB-14 vai consumir, e o §2º é **declarado** na resposta em vez de
silenciado (achado 11 da auditoria de 29/09).

Dados 100% sintéticos, herdados do cenário da fatia anterior — os MESMOS
números, para que a API seja conferível contra a tela já entregue.
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    ClassificacaoDlpa,
    Conta,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.tests import test_dl048_dlpa as _fatia
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel

pytestmark = pytest.mark.django_db

# Reuso do cenário da fatia CTB-12/CTB-13 pelo import DIRETO do módulo, com
# alias. Importar a fixture pelo nome (`from ... import cenario_dlpa`) faz o
# `ruff` acusar F811 em cada teste que usa o parâmetro: ele não sabe que o
# nome importado é uma fixture, porque o consumo é do pytest. O alias resolve
# e deixa explícito que os MESMOS números servem à API e à tela já entregue.
cenario_dlpa = _fatia.cenario_dlpa

ANO = _fatia.ANO
MES = _fatia.MES
_autenticar = _fatia._autenticar
_cnpj_sintetico = _fatia._cnpj_sintetico
_conta = _fatia._conta

C = NaturezaConta.CREDORA
D = NaturezaConta.DEVEDORA


def _url_da_dlpa(empresa):
    return reverse("contabilidade:dlpa", args=[empresa.id, ANO, MES])


def _url_da_classificacao(empresa, conta):
    return reverse("contabilidade:conta-classificacao-dlpa", args=[empresa.id, conta.id])


def _linhas_por_chave(corpo):
    return {linha["chave"]: linha["valor"] for linha in corpo["linhas"]}


# ---------------------------------------------------------------------------
# GET — leitura, valores e o § 2º declarado
# ---------------------------------------------------------------------------


def test_get_devolve_o_mesmo_numero_da_tela(client, cenario_dlpa):
    """R4: o número da API é o da tela — 14.500,00 de saldo final, string com
    duas casas. A tela já foi conferida no PR #59; aqui o mesmo número vem
    por JSON, o que prova que a view NÃO recalcula nada."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-le")
    resposta = client.get(_url_da_dlpa(cenario_dlpa["empresa"]))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["saldo_inicial"] == "800.00"
    assert corpo["saldo_final"] == "14500.00"
    assert corpo["conciliacao"]["diferenca"] == "0.00"
    assert corpo["pode_emitir"] is True

    # Dinheiro NUNCA volta como float: 14500.0 em JSON é ponto flutuante, e o
    # projeto proíbe ponto flutuante para valor monetário (AGENTS.md §10).
    bruto = resposta.content.decode()
    assert '"14500.00"' in bruto
    assert "14500.0," not in bruto and "14500.0}" not in bruto

    linhas = _linhas_por_chave(corpo)
    assert linhas[ClassificacaoDlpa.RESULTADO_DO_EXERCICIO] == "25000.00"
    assert linhas[f"transferencia:{ClassificacaoDlpa.RESERVA_LEGAL}"] == "-1250.00"
    assert linhas[f"reversao:{ClassificacaoDlpa.RESERVA_LEGAL}"] == "300.00"
    assert linhas[ClassificacaoDlpa.DIVIDENDO] == "-10000.00"


def test_a_chave_da_linha_e_o_contrato_com_a_dmpl(client, cenario_dlpa):
    """A chave estruturada é o contrato com a CTB-14: a linha da DLPA é a
    DESTINAÇÃO e a coluna da DMPL é a CONTRAPARTIDA — *"o mesmo fato visto por
    dois lados"* (RC-137). A direção do movimento (decisão D4) já vem embutida
    na chave, então a DMPL não precisa recalcular reserva × reversão.

    Por isso a chave é `transferencia:<reserva>` / `reversao:<reserva>` e não
    um rótulo: a DMPL vai ler estas chaves como movimento de coluna."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-chave")
    corpo = client.get(_url_da_dlpa(cenario_dlpa["empresa"])).json()

    chaves = [linha["chave"] for linha in corpo["linhas"]]
    assert f"transferencia:{ClassificacaoDlpa.RESERVA_LEGAL}" in chaves
    assert f"reversao:{ClassificacaoDlpa.RESERVA_LEGAL}" in chaves
    # A MESMA conta de reserva aparece nas duas direções, com chaves distintas:
    # é a diferença entre art. 186, II (reversão) e III (transferência).
    assert len(set(chaves)) == len(chaves)

    # Toda linha carrega os lançamentos que a geraram — rastreabilidade
    # (critério 1 do plano da fatia anterior) preservada na API.
    for linha in corpo["linhas"]:
        assert "lancamentos" in linha
        if linha["chave"] not in ("saldo_inicial", "saldo_final"):
            assert linha["lancamentos"], linha["chave"]


def test_paragrafo_2_e_declarado_e_sempre_presente(client, cenario_dlpa):
    """R5 — o desenho que o Fred pediu: a DLPA pode ser embutida na DMPL.

    O § 2º do art. 186 é **declarado**, nunca omitido. O achado 11 da
    auditoria registrou que o "dividendo por ação" não existe no enum e que a
    base de cálculo é dado da DMPL (CTB-14); uma API que devolvesse só as
    linhas ESCONDERIA essa pendência de quem consome."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-p2")
    corpo = client.get(_url_da_dlpa(cenario_dlpa["empresa"])).json()

    p2 = corpo["paragrafo_2"]
    assert p2["fonte"] == "Lei 6.404/76, art. 186, § 2º"
    assert p2["dividendo_por_acao"] is None
    assert "CTB-14" in p2["situacao_do_dividendo_por_acao"]
    assert p2["pode_ser_incluida_na_dmpl"] is True
    # Faculdade da lei, não obrigação: a API não escolhe o modo de emissão.
    assert "faculdade" in p2["natureza"]


def test_paragrafo_2_existe_mesmo_sem_nenhum_movimento(client, cenario_dlpa):
    """A chave SEMPRE existe. Cliente que só a enxergasse quando houvesse
    dividendo não distinguiria "não há" de "o servidor não responde isso" — o
    mesmo raciocínio de `_aviso_de_movimento_fora_do_periodo` (BL-198)."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-vazio")
    limpo = Empresa.objects.create(
        escritorio=cenario_dlpa["escritorio"],
        razao_social="Empresa Sem Movimento Ltda",
        cnpj=_cnpj_sintetico(),
    )
    _conta(
        limpo,
        codigo="1.1",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        classificacao_dlpa=ClassificacaoDlpa.LUCROS_OU_PREJUIZOS_ACUMULADOS,
    )
    corpo = client.get(_url_da_dlpa(limpo)).json()

    assert "paragrafo_2" in corpo
    assert corpo["paragrafo_2"]["dividendo_por_acao"] is None
    assert corpo["saldo_final"] == "0.00"
    assert all(linha["valor"] == "0.00" for linha in corpo["linhas"])


# ---------------------------------------------------------------------------
# GET — permissão, isolamento, pendência e formato
# ---------------------------------------------------------------------------


def test_get_sem_permissao_recebe_403_e_nenhum_valor(client, cenario_dlpa):
    """R1: 403 sem `PodeLerContabilidade`, e a resposta não carrega NENHUM
    valor — nem o saldo, nem a razão social. Same shape do teste da tela."""
    _autenticar(client, cenario_dlpa["escritorio"], papel=Papel.CLIENTE, username="cliente-d8")
    resposta = client.get(_url_da_dlpa(cenario_dlpa["empresa"]))

    assert resposta.status_code == 403
    bruto = resposta.content.decode()
    for vazamento in ("14500", "25000", cenario_dlpa["empresa"].razao_social):
        assert vazamento not in bruto, vazamento


def test_get_anonimo_nao_recebe_a_demonstracao(client, cenario_dlpa):
    """R1 também cobre o anônimo. O código exato (401 vs 403) é da pilha de
    autenticação do DRF e não é o que esta rota promete; o que ela promete é
    que ANÔNIMO não recebe a demonstração nem um valor sequer."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-para-deslogar")
    client.logout()
    resposta = client.get(_url_da_dlpa(cenario_dlpa["empresa"]))

    assert resposta.status_code in (401, 403)
    bruto = resposta.content.decode()
    for vazamento in ("14500", "25000", cenario_dlpa["empresa"].razao_social):
        assert vazamento not in bruto, vazamento


def test_get_empresa_de_outro_escritorio_da_404(client, cenario_dlpa):
    """R2 — isolamento no servidor: o `get_empresa()` do mixin resolve a
    empresa pelo ESCRITÓRIO ativo; empresa alheia não existe neste escopo."""
    outro = Escritorio.objects.create(nome="Outro Escritório D8", cnpj=_cnpj_sintetico())
    _autenticar(client, outro, username="gestor-d8-outro")
    resposta = client.get(_url_da_dlpa(cenario_dlpa["empresa"]))

    assert resposta.status_code == 404
    assert cenario_dlpa["empresa"].razao_social not in resposta.content.decode()


def test_pendencia_veta_com_409_e_o_corpo_traz_o_numero(client, cenario_dlpa):
    """R3 — 409 quando `pode_emitir` é falso, e o corpo INTEIRO mesmo assim.

    Um cliente que montasse documento com 200 receberia número imprimível sem
    saber da pendência; um cliente que só recebesse o veto não distinguiria
    "não pode emitir" de "o servidor não sabe ler". O status informa, não
    substitui."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-pend")

    # Contrapartida SEM classificação: é o que produz
    # `movimentos_sem_classificacao_dlpa` e veta a emissão.
    sem_classificacao = _conta(
        cenario_dlpa["empresa"],
        codigo="9.1",
        nome="Conta sem classificação da DLPA",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    criar_lancamento(
        empresa=cenario_dlpa["empresa"],
        data=date(2026, 3, 10),
        historico="Movimento da conta sujeito com contrapartida não classificada",
        itens=[
            {
                "conta": cenario_dlpa["lucros"],
                "tipo": TipoPartida.DEBITO,
                "valor": Decimal("999.00"),
            },
            {
                "conta": sem_classificacao,
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("999.00"),
            },
        ],
    )

    resposta = client.get(_url_da_dlpa(cenario_dlpa["empresa"]))
    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["pode_emitir"] is False
    assert "movimentos_sem_classificacao_dlpa" in corpo["listas_pendentes"]
    # O número continua no corpo — é o que permite ao cliente mostrar o que
    # falta em vez de esconder o documento inteiro.
    assert corpo["saldo_final"] is not None
    assert "linhas" in corpo and "conciliacao" in corpo


@pytest.mark.parametrize("mes", [0, 13])
def test_mes_fora_da_faixa_recebe_400_e_nao_excecao_crua(client, cenario_dlpa, mes):
    """Achado 14 da auditoria de 29/09: `mes` fora de 1–12 levantava
    `IllegalMonthError` crua. A correção pertence à fronteira, que é onde a
    validação de FORMATO vive — e a API é a fronteira desta porta.

    ⚠️ Só 0 e 13 são testados: `-1` não chega à view, porque o padrão da rota
    é `[0-9]+` e o servidor responde 404 antes de qualquer código rodar. Isso
    é comportamento correto, e é por isso que o achado era 500-e-não-400."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-mes")
    resposta = client.get(
        reverse("contabilidade:dlpa", args=[cenario_dlpa["empresa"].id, ANO, mes])
    )
    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# PATCH — classificação pela API
# ---------------------------------------------------------------------------


def test_patch_classifica_e_devolve_a_conta(client, cenario_dlpa):
    """R9 — grava e devolve a conta com `classificacao_dlpa`.

    Usa uma conta NOVA e sem classificação, não uma do cenário: as contas do
    cenário já estão classificadas de propósito (é o que faz a DLPA fechar), e
    reclassificar uma delas tornaria o teste dependente de que valor cada uma
    tem."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-patch")
    conta = _conta(
        cenario_dlpa["empresa"],
        codigo="9.2",
        nome="Reserva a classificar",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )
    assert conta.classificacao_dlpa is None

    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], conta),
        data=json.dumps({"classificacao_dlpa": ClassificacaoDlpa.RESERVA_ESTATUTARIA}),
        content_type="application/json",
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["classificacao_dlpa"] == ClassificacaoDlpa.RESERVA_ESTATUTARIA
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == ClassificacaoDlpa.RESERVA_ESTATUTARIA


def test_patch_registra_a_trilha_com_o_valor_antes_e_o_depois(client, cenario_dlpa):
    """R10 — a trilha registra os DOIS valores. É o que permite responder
    "quem mudou, quando e de quê para quê" depois da CLASSIFICAÇÃO, e é
    obligatoire em qualquer operação que muda dado de apresentação."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-trilha")
    conta = cenario_dlpa["receita"]
    antes = RegistroAuditoria.objects.count()

    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], conta),
        data=json.dumps({"classificacao_dlpa": ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR}),
        content_type="application/json",
    )
    assert resposta.status_code == 200
    assert RegistroAuditoria.objects.count() == antes + 1

    registro = RegistroAuditoria.objects.order_by("-id").first()
    assert registro.acao == "conta.classificacao_dlpa_alterada"
    assert registro.detalhes["classificacao_dlpa_antes"] is None
    assert (
        registro.detalhes["classificacao_dlpa_depois"]
        == ClassificacaoDlpa.AJUSTE_DE_EXERCICIO_ANTERIOR
    )


@pytest.mark.parametrize("payload", [None, ""])
def test_patch_com_valor_vazio_remove_a_classificacao(client, cenario_dlpa, payload):
    """R12 — `null` e `""` significam a MESMA coisa: remover. Remover é
    operação normal desta API, não erro (achado A4 da DL-045)."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-remover")
    conta = cenario_dlpa["reserva"]
    assert conta.classificacao_dlpa == ClassificacaoDlpa.RESERVA_LEGAL

    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], conta),
        data=json.dumps({"classificacao_dlpa": payload}),
        content_type="application/json",
    )

    assert resposta.status_code == 200
    assert resposta.json()["classificacao_dlpa"] is None
    conta.refresh_from_db()
    assert conta.classificacao_dlpa is None


def test_patch_sem_permissao_recebe_403_e_nao_grava(client, cenario_dlpa):
    """R6 — classificar é ESCREVER, então pede quem escreve.

    O papel usado é o **CLIENTE**, e não o ANALISTA: o ANALISTA tem
    `PodeEscriturar` (é a mesma matriz de `ContaListCreateView.post`), então
    usá-lo aqui daria 200 e o teste passaria medindo a coisa errada. A
    matriz real de quem escreve está em `apps.contabilidade.permissoes`."""
    _autenticar(client, cenario_dlpa["escritorio"], papel=Papel.CLIENTE, username="cliente-d8-w")
    conta = cenario_dlpa["reserva"]
    antes = conta.classificacao_dlpa

    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], conta),
        data=json.dumps({"classificacao_dlpa": ClassificacaoDlpa.RESERVA_ESTATUTARIA}),
        content_type="application/json",
    )

    assert resposta.status_code == 403
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == antes


def test_patch_conta_de_outra_empresa_da_404(client, cenario_dlpa):
    """R7 — o filtro é `Conta.objects.filter(empresa=empresa)`, nunca uma
    consulta sem esse filtro: conta de outra empresa é 404, não 403 (o 403
    vazaria a existência do recurso)."""
    outro = Escritorio.objects.create(nome="Escritório Alheio D8", cnpj=_cnpj_sintetico())
    _autenticar(client, outro, username="gestor-d8-alheio")
    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], cenario_dlpa["reserva"]),
        data=json.dumps({"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL}),
        content_type="application/json",
    )
    assert resposta.status_code == 404


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param(json.dumps(["classificacao_dlpa"]), id="corpo-lista"),
        pytest.param(json.dumps({"classificacao_dlpa": {"a": 1}}), id="valor-dict"),
        pytest.param(json.dumps({"classificacao_dlpa": ["reserva_legal"]}), id="valor-lista"),
        pytest.param(json.dumps({"classificacao_dlpa": 123}), id="valor-numero"),
    ],
)
def test_patch_corpo_malformado_recebe_400_e_nao_500(client, cenario_dlpa, corpo):
    """R8 — o R3 da auditoria DL-045 aplicado à DLPA. Sem a validação de tipo
    antes do serviço, `request.data.get(...)` estourava `AttributeError` para
    corpo-lista e `Conta.clean()` estourava `TypeError: unhashable type` para
    valor dict/list: os dois vaziavam como 500 mudo, sem nada gravado."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-malformado")
    conta = cenario_dlpa["reserva"]
    antes = conta.classificacao_dlpa

    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], conta),
        data=corpo,
        content_type="application/json",
    )

    assert resposta.status_code == 400
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == antes


def test_patch_com_a_linha_da_dre_no_corpo_e_recusado(client, cenario_dlpa):
    """O contrato é SEPARADO do da DRE de propósito: a política recusa chave
    desconhecida por nome, e um corpo com `classificacao_dre` aqui gravaria a
    linha errada em silêncio — o pior defeito possível nesta porta."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-trocada")
    conta = cenario_dlpa["reserva"]
    antes_dlpa = conta.classificacao_dlpa
    antes_dre = conta.classificacao_dre

    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], conta),
        data=json.dumps({"classificacao_dre": "receita_bruta"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    conta.refresh_from_db()
    assert conta.classificacao_dlpa == antes_dlpa
    assert conta.classificacao_dre == antes_dre


def test_patch_tipo_incompativel_recebe_400_nomeando_a_linha(client, cenario_dlpa):
    """R11 — a compatibilidade com `Conta.tipo` é decidida por
    `Conta.full_clean()` dentro de `classificar_conta_na_dlpa` (fonte única:
    `TIPOS_ACEITOS_DA_CLASSIFICACAO_DLPA`), e o 400 tem de dizer QUAL linha e
    QUAL tipo — erro que não diz o que fazer obriga o contador a procurar."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-tipo")
    conta = cenario_dlpa["receita"]  # tipo RECEITA — nenhuma linha de DLPA aceita

    resposta = client.patch(
        _url_da_classificacao(cenario_dlpa["empresa"], conta),
        data=json.dumps({"classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    mensagem = resposta.content.decode()
    assert "Reserva legal" in mensagem
    # O rótulo vem de `TipoConta.PATRIMONIO_LIQUIDO.label` — "Patrimônio
    # Líquido", com L maiúscula. A mensagem é montada em `Conta.clean()`.
    assert "Patrimônio Líquido" in mensagem


# ---------------------------------------------------------------------------
# Paridade do serializer
# ---------------------------------------------------------------------------


def test_conta_serializer_expoe_as_duas_classificacoes(client, cenario_dlpa):
    """`ContaSerializer` expõe `classificacao_dre` E `classificacao_dlpa`: o
    campo novo não pode displazar o antigo — cliente que já consumia a DRE
    continua lendo as mesmas chaves."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-serializer")
    conta = cenario_dlpa["receita"]

    resposta = client.get(reverse("contabilidade:contas", args=[cenario_dlpa["empresa"].id]))
    assert resposta.status_code == 200
    contas = {c["id"]: c for c in resposta.json()}
    lidas = contas[conta.id]

    assert "classificacao_dlpa" in lidas
    assert "classificacao_dre" in lidas
    assert lidas["classificacao_dlpa"] is None


def test_post_de_conta_aceita_classificacao_dlpa(client, cenario_dlpa):
    """A porta de contas aceita a classificação nova com a MESMA autorização
    de hoje — nenhuma `permission_class` nova foi criada para isso."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-post")
    resposta = client.post(
        reverse("contabilidade:contas", args=[cenario_dlpa["empresa"].id]),
        data=json.dumps(
            {
                "codigo": "2.5",
                "nome": "Reserva Legal Nova",
                "tipo": TipoConta.PATRIMONIO_LIQUIDO,
                "natureza": C,
                "classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL,
            }
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 201
    assert resposta.json()["classificacao_dlpa"] == ClassificacaoDlpa.RESERVA_LEGAL
    assert Conta.objects.filter(codigo="2.5").count() == 1


def test_post_de_conta_com_tipo_incompativel_recebe_400(client, cenario_dlpa):
    """A mesma guarda do `PATCH`, agora no POST — e é a razão de ela existir
    no serializer: o DRF nunca chama `full_clean()` (BL-40/DE-008), então
    `Conta.clean()` não roda neste caminho."""
    _autenticar(client, cenario_dlpa["escritorio"], username="gestor-d8-post-tipo")
    resposta = client.post(
        reverse("contabilidade:contas", args=[cenario_dlpa["empresa"].id]),
        data=json.dumps(
            {
                "codigo": "3.7",
                "nome": "Reserva em conta de receita",
                "tipo": TipoConta.RECEITA,
                "natureza": C,
                "classificacao_dlpa": ClassificacaoDlpa.RESERVA_LEGAL,
            }
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "Reserva legal" in resposta.content.decode()
    assert Conta.objects.filter(codigo="3.7").count() == 0
