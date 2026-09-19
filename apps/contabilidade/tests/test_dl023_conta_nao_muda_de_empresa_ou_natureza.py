"""DL-023, critérios 1 a 4 e 11 (BL-83, achado novo 1 da auditoria DL-015
rodada 4).

O defeito medido: `ContaAdmin` deixava mover conta COM movimento para OUTRA
empresa e trocar a NATUREZA/TIPO de conta já movimentada. Efeito: o
balancete da empresa de origem passava a mostrar zero de débito contra mil
de crédito, o Diário continuava fechando, e nenhuma das quatro categorias da
conferência acusava nada — trocar a natureza inverte o sinal de todo o
histórico da conta.

A defesa mora em `Conta.clean()` (apps/contabilidade/models.py), chamado
por `full_clean()` — o que qualquer `ModelForm`, inclusive o do admin,
executa. Todo teste aqui é por REQUISIÇÃO autenticada ao admin, com o
objeto reconferido no banco depois da resposta: `full_clean()` verde não
prova que o admin o chama.
"""

from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import (
    apurar_balancete,
    apurar_razao,
    criar_lancamento,
    listar_diario,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL-023", cnpj="10101010000122")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-023 Ltda", cnpj="10111213000144"
    )
    outra_empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Outra Empresa DL-023 Ltda", cnpj="20212223000155"
    )
    # BL-248 (achado P4, auditoria DL-023 rodada 1): um SEGUNDO escritório,
    # com uma empresa "sigilosa" dele, para provar a fronteira que a
    # rodada 1 não checava.
    outro_escritorio = Escritorio.objects.create(
        nome="Escritório DL-023 sigiloso", cnpj="30303030000188"
    )
    empresa_outro_escritorio = Empresa.objects.create(
        escritorio=outro_escritorio,
        razao_social="CLIENTE SIGILOSO Ltda",
        cnpj="11122233000183",
    )
    admin = get_user_model().objects.create_superuser(
        username="admin-dl023-conta",
        email="admin-dl023-conta@escritorio.com.br",
        password=SENHA,
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "outra_empresa": outra_empresa,
        "outro_escritorio": outro_escritorio,
        "empresa_outro_escritorio": empresa_outro_escritorio,
        "admin": admin,
    }


def _conta(
    empresa,
    *,
    codigo,
    nome="Conta",
    tipo=TipoConta.ATIVO,
    natureza=NaturezaConta.DEVEDORA,
    pai=None,
):
    return Conta.objects.create(
        empresa=empresa, conta_pai=pai, codigo=codigo, nome=nome, tipo=tipo, natureza=natureza
    )


def _com_movimento(cenario, conta):
    """Dá movimento PRÓPRIO a `conta`: um lançamento balanceado contra uma
    segunda conta descartável da mesma empresa."""
    contrapartida = _conta(
        cenario["empresa"],
        codigo=f"contra-{conta.codigo}",
        nome="Contrapartida",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 1, 15),
        historico="DL-023 movimento",
        itens=[
            {"conta": conta, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": contrapartida, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    return conta


def _retrato_diario(empresa, periodo):
    """Retrato comparável do Diário (BL-259, achado A6): lista de
    `(id, data, histórico, [(conta_id, tipo, valor), ...])`, para comparar
    ANTES/DEPOIS de uma tentativa recusada sem depender de instâncias
    vivas de `LancamentoContabil` (que mudam de identidade entre
    consultas)."""
    return [
        (
            lancamento.id,
            lancamento.data,
            lancamento.historico,
            sorted((item.conta_id, item.tipo, item.valor) for item in lancamento.itens.all()),
        )
        for lancamento in listar_diario(empresa=empresa, **periodo)
    ]


def _login_admin(client, cenario):
    assert client.login(username="admin-dl023-conta", password=SENHA)


def _post_change(client, conta, dados):
    payload = {
        "empresa": conta.empresa_id,
        "conta_pai": conta.conta_pai_id or "",
        "codigo": conta.codigo,
        "nome": conta.nome,
        "tipo": conta.tipo,
        "natureza": conta.natureza,
        "aceita_lancamento": "on" if conta.aceita_lancamento else "",
        "ativo": "on" if conta.ativo else "",
        "_continue": "Salvar e continuar editando",
    }
    payload.update(dados)
    return client.post(f"/admin/contabilidade/conta/{conta.pk}/change/", payload)


# ---------------------------------------------------------------------------
# Critério 1: conta COM PARTIDAS não muda de empresa
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_empresa_de_conta_com_partidas(client, cenario):
    """BL-266 (achado A1 da auditoria DL-023 rodada 3): não basta `200` +
    objeto inalterado — um FORMULÁRIO QUEBRADO por outro motivo (ex.: CNPJ
    inválido em outro campo) também produz esse par, sem a defesa ter
    disparado. A mensagem do MODELO no corpo é o que distingue "recusei de
    propósito" de "quebrei": aqui, `outra_empresa` está no MESMO escritório
    (dentro do `queryset` do dropdown), então quem recusa é `Conta.clean()`
    — a mensagem do modelo precisa aparecer."""
    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1"))
    estado_antes = (conta.empresa_id, conta.natureza, conta.tipo, conta.codigo, conta.nome)
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"empresa": cenario["outra_empresa"].id})

    # 200 = formulário reapresentado com erro (302 seria "salvou e
    # redirecionou") — mesmo critério já usado no resto do projeto para
    # distinguir recusa de sucesso no admin.
    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    corpo = resposta.content.decode()
    assert "lançamento próprio" in corpo, corpo
    conta.refresh_from_db()
    # "byte a byte": empresa, natureza e tipo — os três campos que o
    # critério 1 nomeia — continuam exatamente como estavam.
    assert (conta.empresa_id, conta.natureza, conta.tipo, conta.codigo, conta.nome) == estado_antes


# ---------------------------------------------------------------------------
# Critério 2: conta COM FILHAS não muda de empresa
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_empresa_de_conta_com_filhas(client, cenario):
    """BL-266: mensagem do modelo no corpo, não só status — `outra_empresa`
    está no mesmo escritório (dentro do `queryset` do dropdown), então quem
    recusa é `Conta.clean()`."""
    pai = _conta(cenario["empresa"], codigo="1", tipo=TipoConta.ATIVO)
    _conta(cenario["empresa"], codigo="1.1", pai=pai, nome="Filha")
    _login_admin(client, cenario)

    resposta = _post_change(client, pai, {"empresa": cenario["outra_empresa"].id})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    corpo = resposta.content.decode()
    assert "conta filha" in corpo, corpo
    pai.refresh_from_db()
    assert pai.empresa_id == cenario["empresa"].id


# ---------------------------------------------------------------------------
# Critério 3: natureza/tipo de conta COM MOVIMENTO não mudam
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_natureza_de_conta_com_movimento(client, cenario):
    """Critério 3 nomeia TRÊS saídas — Diário, Razão e Balancete (BL-259,
    achado A6): as três são conferidas antes e depois da tentativa
    recusada, não só o Balancete."""
    conta = _com_movimento(
        cenario, _conta(cenario["empresa"], codigo="1", natureza=NaturezaConta.DEVEDORA)
    )
    periodo = {"inicio": date(2026, 1, 1), "fim": date(2026, 1, 31)}
    balancete_antes = apurar_balancete(empresa=cenario["empresa"], **periodo)
    razao_antes = apurar_razao(conta=conta, empresa=cenario["empresa"], **periodo)
    diario_antes = _retrato_diario(cenario["empresa"], periodo)
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"natureza": NaturezaConta.CREDORA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    # BL-266: mensagem do modelo no corpo — o campo `natureza` não é
    # restringido por nenhum `formfield_for_foreignkey` (não é FK), então
    # só `Conta.clean()` pode ter recusado este POST.
    assert "a natureza" in resposta.content.decode()
    conta.refresh_from_db()
    assert conta.natureza == NaturezaConta.DEVEDORA
    balancete_depois = apurar_balancete(empresa=cenario["empresa"], **periodo)
    razao_depois = apurar_razao(conta=conta, empresa=cenario["empresa"], **periodo)
    diario_depois = _retrato_diario(cenario["empresa"], periodo)
    # As TRÊS saídas continuam conciliáveis — débito igual a crédito — e
    # IDÊNTICAS às de antes da tentativa: nada mudou de sinal nem de valor.
    assert balancete_depois["total_debitos"] == balancete_depois["total_creditos"]
    assert balancete_antes == balancete_depois
    assert razao_antes == razao_depois
    assert diario_antes == diario_depois


def test_admin_recusa_trocar_tipo_de_conta_com_movimento(client, cenario):
    """BL-266: mensagem do modelo no corpo — `tipo` não é FK, ninguém além
    de `Conta.clean()` pode ter recusado este POST."""
    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1", tipo=TipoConta.ATIVO))
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"tipo": TipoConta.DESPESA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    assert "o tipo" in resposta.content.decode()
    conta.refresh_from_db()
    assert conta.tipo == TipoConta.ATIVO


# ---------------------------------------------------------------------------
# BL-245 (achado P1 da auditoria DL-023 rodada 1): conta SINTÉTICA sem
# movimento PRÓPRIO, mas com filha MOVIMENTADA, também não muda de natureza
# nem de tipo — a natureza da conta apresentada (a sintética) governa a
# apresentação do GRUPO no Balancete, consolidando o movimento de toda a
# subárvore.
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_natureza_de_sintetica_com_filha_movimentada(client, cenario):
    """Reprodução exata do achado do auditor: conta `1` com
    `aceita_lancamento=False`, SEM movimento próprio, com filha `1.1`
    movimentada em 1.000,00 D — a linha do grupo no Balancete não pode
    inverter de sinal."""
    pai = _conta(cenario["empresa"], codigo="1", natureza=NaturezaConta.DEVEDORA)
    pai.aceita_lancamento = False
    pai.save(update_fields=["aceita_lancamento"])
    filha = _conta(
        cenario["empresa"], codigo="1.1", pai=pai, natureza=NaturezaConta.DEVEDORA, nome="Filha"
    )
    _com_movimento(cenario, filha)
    assert not pai.itens_lancamento.exists()  # sem movimento PRÓPRIO — é o ponto do achado
    periodo = {"inicio": date(2026, 1, 1), "fim": date(2026, 1, 31)}
    balancete_antes = apurar_balancete(empresa=cenario["empresa"], **periodo)
    linha_pai_antes = next(linha for linha in balancete_antes["contas"] if linha["conta"] == "1")
    assert linha_pai_antes["saldo_final"] == Decimal("100.00")
    _login_admin(client, cenario)

    resposta = _post_change(client, pai, {"natureza": NaturezaConta.CREDORA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    # BL-266: mensagem do modelo no corpo.
    assert "a natureza" in resposta.content.decode()
    pai.refresh_from_db()
    assert pai.natureza == NaturezaConta.DEVEDORA
    balancete_depois = apurar_balancete(empresa=cenario["empresa"], **periodo)
    linha_pai_depois = next(linha for linha in balancete_depois["contas"] if linha["conta"] == "1")
    # A linha do GRUPO continua fechando no mesmo lado — não inverteu para
    # -100.00, que era o dano medido pelo auditor.
    assert linha_pai_depois["saldo_final"] == Decimal("100.00")
    assert balancete_antes == balancete_depois


def test_admin_recusa_trocar_tipo_de_sintetica_com_filha_movimentada(client, cenario):
    pai = _conta(cenario["empresa"], codigo="1", tipo=TipoConta.ATIVO)
    pai.aceita_lancamento = False
    pai.save(update_fields=["aceita_lancamento"])
    filha = _conta(cenario["empresa"], codigo="1.1", pai=pai, tipo=TipoConta.ATIVO, nome="Filha")
    _com_movimento(cenario, filha)
    _login_admin(client, cenario)

    resposta = _post_change(client, pai, {"tipo": TipoConta.DESPESA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    assert "o tipo" in resposta.content.decode()  # BL-266: mensagem do modelo no corpo
    pai.refresh_from_db()
    assert pai.tipo == TipoConta.ATIVO


def test_admin_recusa_trocar_natureza_de_neta_com_bisneta_movimentada(client, cenario):
    """Profundidade > 1: a consulta recursiva (`WITH RECURSIVE`) precisa
    alcançar QUALQUER descendente, não só filhos diretos."""
    avo = _conta(cenario["empresa"], codigo="1", natureza=NaturezaConta.DEVEDORA)
    pai = _conta(cenario["empresa"], codigo="1.1", pai=avo, natureza=NaturezaConta.DEVEDORA)
    neta = _conta(
        cenario["empresa"], codigo="1.1.1", pai=pai, natureza=NaturezaConta.DEVEDORA, nome="Neta"
    )
    _com_movimento(cenario, neta)
    _login_admin(client, cenario)

    resposta = _post_change(client, avo, {"natureza": NaturezaConta.CREDORA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    assert "a natureza" in resposta.content.decode()  # BL-266: mensagem do modelo no corpo
    avo.refresh_from_db()
    assert avo.natureza == NaturezaConta.DEVEDORA


def test_admin_continua_editando_sintetica_com_filha_sem_movimento_nenhum(client, cenario):
    """Controle positivo: a correção da BL-245 não pode engessar uma
    sintética cuja subárvore INTEIRA está livre de movimento — critério 4
    continua valendo para esse caso."""
    pai = _conta(cenario["empresa"], codigo="1", natureza=NaturezaConta.DEVEDORA)
    pai.aceita_lancamento = False
    pai.save(update_fields=["aceita_lancamento"])
    _conta(cenario["empresa"], codigo="1.1", pai=pai, natureza=NaturezaConta.DEVEDORA, nome="Filha")
    _login_admin(client, cenario)

    resposta = _post_change(client, pai, {"natureza": NaturezaConta.CREDORA})

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    pai.refresh_from_db()
    assert pai.natureza == NaturezaConta.CREDORA


# ---------------------------------------------------------------------------
# BL-265 (achado P5 da auditoria DL-023 rodada 3): o `WITH RECURSIVE` de
# `_tem_movimento_proprio_ou_de_descendente` lê o NOME DE COLUNA das duas FKs
# pelo `_meta`, não mais por literal escrito à mão — fecha a assimetria com
# os nomes de TABELA, que já vinham do `_meta.db_table`. Os dois testes
# abaixo foram REESCRITOS na rodada 6 (achado A1): a versão anterior não
# tocava o código de produção (ver docstring do primeiro teste).
# ---------------------------------------------------------------------------


def test_query_recursiva_usa_coluna_de_conta_pai_do_meta_de_verdade(cenario):
    """BL-265 (achado A1 da auditoria DL-023 rodada 6): a versão anterior
    deste teste comparava dois literais Python entre si
    (`Conta._meta.get_field("conta_pai").column == "conta_pai_id"`) — prova
    comportamento do PRÓPRIO Django (como `_meta` resolve o nome de coluna
    de uma FK sem `db_column=`), não do código do DataLedger. Medido pelo
    auditor: revertendo a BL-265 para os literais escritos à mão, ZERO
    testes deste arquivo morriam — inclusive este, que levava o NOME da
    correção.

    Este teste substitui aquele. Ele força `_meta.get_field("conta_pai").
    column` a devolver um nome de coluna que NÃO EXISTE na tabela
    (`mock.patch.object` no objeto de campo, que é o mesmo objeto cacheado
    que `_meta.get_field` sempre devolve) e prova que
    `_tem_movimento_proprio_ou_de_descendente` de fato CONSULTA o `_meta`
    em tempo de execução: com o literal antigo escrito à mão
    (`"conta_pai_id"`), o patch não teria efeito nenhum sobre a consulta, e
    este teste NÃO morreria. Critério objetivo do achado: reverter a
    BL-265 para literal tem que matar o teste — antes, matava zero; agora,
    mata (ver mutação registrada no relatório da rodada 6).

    A chamada arriscada roda dentro de `transaction.atomic()` (savepoint):
    o Postgres aborta a transação corrente quando a consulta referencia
    uma coluna inexistente, e sem o savepoint o `pytest-django` (que já
    envolve o teste inteiro numa transação) impediria o controle positivo
    de usar o banco de novo depois — mesmo padrão já usado noutros testes
    de mutação desta etapa (`services.py`, BL-246).
    """
    from django.db import transaction
    from django.db.utils import ProgrammingError

    conta = _conta(cenario["empresa"], codigo="1")
    campo_conta_pai = Conta._meta.get_field("conta_pai")

    with pytest.raises(ProgrammingError):
        with (
            transaction.atomic(),
            mock.patch.object(campo_conta_pai, "column", "coluna_que_nao_existe"),
        ):
            conta._tem_movimento_proprio_ou_de_descendente()

    # Controle positivo: fora do patch, a mesma chamada funciona
    # normalmente — prova que o `pytest.raises` acima não é um erro de
    # setup do cenário, e que o savepoint devolveu a conexão a um estado
    # utilizável.
    assert conta._tem_movimento_proprio_ou_de_descendente() is False


def test_query_recursiva_usa_coluna_de_conta_do_item_do_meta_de_verdade(cenario):
    """Mesma prova que o teste acima, para a SEGUNDA coluna que a BL-265
    corrigiu (`ItemLancamento.conta`, não `Conta.conta_pai`) — as duas FKs
    tinham o mesmo defeito, e cada uma precisa do próprio mutante para não
    haver uma lacuna simétrica à que a rodada 6 encontrou."""
    from django.db import transaction
    from django.db.utils import ProgrammingError

    from apps.contabilidade.models import ItemLancamento

    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1"))
    campo_conta_do_item = ItemLancamento._meta.get_field("conta")

    with pytest.raises(ProgrammingError):
        with (
            transaction.atomic(),
            mock.patch.object(campo_conta_do_item, "column", "coluna_que_nao_existe"),
        ):
            conta._tem_movimento_proprio_ou_de_descendente()

    # Controle positivo: sem o patch, a conta TEM movimento próprio — este
    # teste usa `_com_movimento` (diferente do teste acima) justamente para
    # exercitar a metade da consulta que junta com `ItemLancamento`.
    assert conta._tem_movimento_proprio_ou_de_descendente() is True


# ---------------------------------------------------------------------------
# Critério 4: conta SEM movimento e SEM filhas continua editável
# ---------------------------------------------------------------------------


def test_admin_continua_editando_conta_sem_movimento_e_sem_filhas(client, cenario):
    """A defesa não pode engessar o cadastro legítimo: sem movimento e sem
    filhas, trocar empresa, natureza e tipo continua permitido."""
    conta = _conta(
        cenario["empresa"], codigo="9", natureza=NaturezaConta.DEVEDORA, tipo=TipoConta.ATIVO
    )
    _login_admin(client, cenario)

    resposta = _post_change(
        client,
        conta,
        {
            "empresa": cenario["outra_empresa"].id,
            "natureza": NaturezaConta.CREDORA,
            "tipo": TipoConta.PASSIVO,
        },
    )

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    conta.refresh_from_db()
    assert conta.empresa_id == cenario["outra_empresa"].id
    assert conta.natureza == NaturezaConta.CREDORA
    assert conta.tipo == TipoConta.PASSIVO


# ---------------------------------------------------------------------------
# BL-248 (achado P4 da auditoria DL-023 rodada 1): fronteira de ESCRITÓRIO.
# Conta LIVRE (sem movimento e sem filhas) não atravessa escritório, mesmo
# sendo editável dentro do MESMO escritório (critério 4 preservado); e o
# dropdown de `empresa` no admin não lista empresa de outro escritório.
# ---------------------------------------------------------------------------


def test_admin_recusa_via_formulario_mover_conta_livre_para_empresa_de_outro_escritorio(
    client, cenario
):
    """BL-266 (achado A1 da auditoria DL-023 rodada 3): este teste tinha o
    NOME do guard de `Conta.clean()`, mas media outra coisa. Medido pelo
    auditor, por requisição: a única mensagem no corpo é a de "escolha
    válida" do `ModelChoiceField` — "fronteira de isolamento" (a mensagem
    do MODELO) não aparece. Motivo estrutural, não descuido: o dropdown de
    `empresa` (`ContaAdmin.formfield_for_foreignkey`, BL-248) restringe o
    `queryset` ao escritório ATUAL da conta, então qualquer POST com
    empresa de outro escritório já é rejeitado pelo `ModelChoiceField`
    ANTES de `Conta.clean()` receber o valor novo — `construct_instance()`
    só atribui campos presentes em `cleaned_data`, e um campo com erro de
    validação não entra lá. Isso vale para QUALQUER POST, não só para o
    que o HTML renderiza: a restrição é no `queryset`, não na marcação.

    Consequência, e por que ela é aceitável — QUALIFICADA na rodada 6
    (achado A3 da auditoria focada, BAIXA): o auditor sondou 19 formas de
    requisição (`_to_field`, `_popup`, `_saveasnew` — que o Django honra
    mesmo com `save_as = False` —, empresa enviada duas vezes, empresa
    migrando de escritório entre o `GET` que renderiza o formulário e o
    `POST`, `object_id` com zero à esquerda, staff comum) e em NENHUMA o
    guard do MODELO foi quem recusou — sempre o formulário. Isso é limite
    MEDIDO, não suposição, mas a frase anterior ("mais forte, cobrindo o
    que a porta única de escrita de hoje não alcançaria") generalizava além
    do que foi medido: no ADMIN especificamente, os dois guards não SE
    COBREM, COINCIDEM — a única superfície que o formulário não alcança é
    o `add` (não há `object_id`/conta ainda para ancorar o `queryset` de
    `formfield_for_foreignkey`), e é EXATAMENTE a mesma superfície que o
    guard do modelo também não cobre, porque todo o bloco de `Conta.
    clean()` que trata troca de empresa está sob `if self.pk:` — uma conta
    nova não tem "empresa original" para comparar. Essa lacuna do `add` é
    a BL-267 (fora desta etapa). Fora do admin (`full_clean()` chamado
    direto, ex.: importação em lote da DL-010), o guard do modelo continua
    sendo a ÚNICA defesa — é ali que a frase "mais forte" continua valendo
    sem qualificação."""
    conta = _conta(cenario["empresa"], codigo="9")
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"empresa": cenario["empresa_outro_escritorio"].id})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    # A camada que recusou É o formulário: achado A4 da auditoria da rodada
    # 6 (BAIXA) — a versão anterior deste teste afirmava
    # `"fronteira de isolamento" not in corpo`, verdadeira hoje, mas uma
    # asserção NEGATIVA proíbe por teste uma camada que a BL-262 (fora
    # desta etapa) vai mudar: ancorar o dropdown no escritório do USUÁRIO
    # (não mais no escritório ATUAL da conta) faria o modelo passar a
    # recusar em parte dos casos que hoje só o formulário recusa, e quem
    # fizer aquela etapa encontraria este teste vermelho com uma docstring
    # dizendo "não existe cenário". A asserção agora é POSITIVA e nomeia a
    # CHAVE do erro no formulário (`"empresa"` — a do modelo, se algum dia
    # aparecer aqui, seria `"__all__"`, porque `Conta.clean()` não associa
    # o erro a um campo específico), o que prova a mesma coisa sem proibir
    # a evolução futura da defesa.
    erros_do_formulario = resposta.context["adminform"].form.errors
    assert "empresa" in erros_do_formulario, erros_do_formulario
    # Ausência da mensagem do MODELO — comentário, não asserção, pelo
    # mesmo motivo do parágrafo acima: hoje ela de fato não aparece (ver
    # docstring), mas fixar isso como proibição travaria a BL-262.
    corpo = resposta.content.decode()
    assert "Faça uma escolha válida" in corpo, corpo
    conta.refresh_from_db()
    assert conta.empresa_id == cenario["empresa"].id


def test_admin_change_nao_lista_empresa_de_outro_escritorio_no_dropdown(client, cenario):
    """Reprodução do `[SONDA P]` do auditor: a razão social da empresa de
    OUTRO escritório não pode aparecer no corpo do formulário de troca."""
    conta = _conta(cenario["empresa"], codigo="9")
    _login_admin(client, cenario)

    resposta = client.get(f"/admin/contabilidade/conta/{conta.pk}/change/")

    assert resposta.status_code == 200, resposta.status_code
    corpo = resposta.content.decode()
    assert cenario["empresa_outro_escritorio"].razao_social not in corpo
    assert cenario["empresa"].razao_social in corpo


def test_full_clean_recusa_mover_conta_para_empresa_de_outro_escritorio(cenario):
    """BL-266: este é o teste que prova o guard de escritório do MODELO —
    chamando `full_clean()` direto, sem passar pelo `ModelForm`/dropdown do
    admin, que restringiria o valor antes de `clean()` rodar (ver o
    docstring de `test_admin_recusa_via_formulario_mover_conta_livre_para_
    empresa_de_outro_escritorio`, acima). É este teste que o mutante que
    neutraliza o guard do MODELO mata."""
    from django.core.exceptions import ValidationError

    conta = _conta(cenario["empresa"], codigo="9")
    conta.empresa = cenario["empresa_outro_escritorio"]

    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    # A mensagem nomeia a causa certa: empresa REAL, de OUTRO escritório —
    # não confundir com BL-264 (empresa que não existe), logo abaixo.
    assert "outro" in str(excinfo.value) and "escritório" in str(excinfo.value)
    assert "não existe" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# BL-264 (achado P4 da auditoria DL-023 rodada 3, INTRODUZIDO pela rodada 2):
# `self.empresa.escritorio_id` carregava a linha inteira e estourava
# `Empresa.DoesNotExist` (não `ValidationError`) quando `empresa_id` apontava
# para registro inexistente — 500 em qualquer `full_clean()` direto (não
# alcançável pelo admin, mas alcançável por importação em lote, DL-010).
#
# Correção da RODADA 4 do arquiteto: a primeira versão desta correção reusava
# a mensagem de "outro escritório" também para FK inexistente — mensagem que
# nomeia a causa ERRADA. Os dois testes abaixo distinguem os dois casos.
# ---------------------------------------------------------------------------


def test_full_clean_recusa_conta_com_empresa_inexistente_com_mensagem_propria(cenario):
    """O cenário exato que o auditor mediu: `empresa_id` aponta para um
    registro que não existe. Antes da correção: `Empresa.DoesNotExist`
    (não é `ValidationError`, 500 em quem chamar). Depois: `ValidationError`
    com mensagem de EMPRESA INEXISTENTE — não de "outro escritório", que
    seria a causa errada (a empresa não existe; não há como saber a que
    escritório ela pertenceria)."""
    from django.core.exceptions import ValidationError

    conta = _conta(cenario["empresa"], codigo="9")
    conta.empresa_id = 999999  # não existe nenhuma Empresa com este id

    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    mensagem = str(excinfo.value)
    assert "não existe" in mensagem
    # E NÃO a mensagem do caso vizinho (empresa real, outro escritório) —
    # é exatamente a confusão que a rodada 4 corrigiu.
    assert "fronteira de isolamento" not in mensagem


def test_full_clean_distingue_empresa_inexistente_de_empresa_de_outro_escritorio(cenario):
    """As DUAS causas, lado a lado, para deixar a distinção impossível de
    reintroduzir por acidente: mensagens DIFERENTES para causas DIFERENTES."""
    from django.core.exceptions import ValidationError

    conta_com_empresa_inexistente = _conta(cenario["empresa"], codigo="9")
    conta_com_empresa_inexistente.empresa_id = 999999

    conta_com_outro_escritorio = _conta(cenario["empresa"], codigo="10")
    conta_com_outro_escritorio.empresa = cenario["empresa_outro_escritorio"]

    with pytest.raises(ValidationError) as erro_inexistente:
        conta_com_empresa_inexistente.full_clean()
    with pytest.raises(ValidationError) as erro_outro_escritorio:
        conta_com_outro_escritorio.full_clean()

    assert str(erro_inexistente.value) != str(erro_outro_escritorio.value)
    assert "não existe" in str(erro_inexistente.value)
    assert "escritório" in str(erro_outro_escritorio.value)


# ---------------------------------------------------------------------------
# Rodada 6 (achado P1 da auditoria focada, MÉDIA): a BL-264 corrigiu a forma
# MENOS provável de `empresa_id` inválido (id inteiro grande demais para
# existir, `2**70`) e deixou aberta a MAIS provável — um valor de TIPO que a
# coluna inteira de `Empresa.pk` não aceita. Medido pelo auditor: `"abc"`,
# `"1e3"`, `"  "` e `[]` levantavam `ValueError`/`TypeError` (500 em quem
# chamar `full_clean()` direto), não `ValidationError` — regressão em
# relação à revisão anterior a esta etapa, que devolvia `ValidationError`
# limpa para esses casos. O comentário da própria BL-264 já nomeia o
# candidato mais provável a produzir isso: a importação em lote da DL-010,
# que pode chamar `full_clean()` linha a linha de uma planilha — texto numa
# coluna numérica é mais comum ali do que um id inteiro que só não existe.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("empresa_id_invalido", ["abc", "1e3", "  ", []])
def test_full_clean_recusa_empresa_id_de_tipo_invalido_com_mensagem_propria(
    cenario, empresa_id_invalido
):
    """Os quatro valores que o auditor mediu: todos levantam
    `ValidationError` — nunca `ValueError`/`TypeError` — com uma TERCEIRA
    mensagem, distinta das duas outras causas (empresa inexistente, empresa
    de outro escritório): aqui o identificador nem chega a ser um id
    válido para consultar."""
    from django.core.exceptions import ValidationError

    conta = _conta(cenario["empresa"], codigo="9")
    conta.empresa_id = empresa_id_invalido

    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    assert "não é válido" in str(excinfo.value)


def test_full_clean_tres_causas_de_empresa_invalida_tem_tres_mensagens_distintas(cenario):
    """Controle das TRÊS causas lado a lado (mesmo espírito do teste que já
    compara "inexistente" com "outro escritório"): "não existe", "outro
    escritório" e "não é válido" são duas a duas diferentes — nenhuma
    mensagem cobre acidentalmente a causa de outra."""
    from django.core.exceptions import ValidationError

    conta_inexistente = _conta(cenario["empresa"], codigo="9")
    conta_inexistente.empresa_id = 999999

    conta_outro_escritorio = _conta(cenario["empresa"], codigo="10")
    conta_outro_escritorio.empresa = cenario["empresa_outro_escritorio"]

    conta_tipo_invalido = _conta(cenario["empresa"], codigo="11")
    conta_tipo_invalido.empresa_id = "abc"

    with pytest.raises(ValidationError) as erro_inexistente:
        conta_inexistente.full_clean()
    with pytest.raises(ValidationError) as erro_outro_escritorio:
        conta_outro_escritorio.full_clean()
    with pytest.raises(ValidationError) as erro_tipo_invalido:
        conta_tipo_invalido.full_clean()

    mensagens = {
        str(erro_inexistente.value),
        str(erro_outro_escritorio.value),
        str(erro_tipo_invalido.value),
    }
    assert len(mensagens) == 3, mensagens


def test_full_clean_com_empresa_id_none_nao_reclama_de_empresa_inexistente(cenario):
    """O caso que a rodada 6 pediu para resolver na mesma linha: antes,
    `empresa_id = None` caía no mesmo caminho de "id que não bate com
    nenhuma empresa" e a mensagem dizia "a empresa informada não existe" —
    quando, na verdade, NADA foi informado. `empresa` não é `null=True`
    (não é papel deste guard reportar a ausência: `clean_fields()`, chamado
    por `full_clean()` antes de `clean()`, já acusa campo obrigatório
    vazio, e os dois erros se acumulam no mesmo `ValidationError` — daí o
    `full_clean()` continuar levantando erro aqui). O que este teste prova
    é que a mensagem ERRADA ("não existe") não aparece mais junto."""
    from django.core.exceptions import ValidationError

    conta = _conta(cenario["empresa"], codigo="9")
    conta.empresa = None
    conta.empresa_id = None

    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    mensagem_completa = str(excinfo.value)
    assert "não existe" not in mensagem_completa
    assert "não é válido" not in mensagem_completa


# ---------------------------------------------------------------------------
# A mesma defesa fora do admin: `full_clean()` chamado diretamente — prova
# que a regra mora no MODELO, e não é dependente de o admin a chamar (a
# distinção que o próprio critério de teste da etapa exige: a prova de
# ADMIN é por requisição, acima; esta é a prova de MODELO, isolada).
# ---------------------------------------------------------------------------


def test_full_clean_recusa_troca_de_empresa_de_conta_com_movimento(cenario):
    from django.core.exceptions import ValidationError

    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1"))
    conta.empresa = cenario["outra_empresa"]

    with pytest.raises(ValidationError):
        conta.full_clean()


# ---------------------------------------------------------------------------
# BL-261 (terceiro caminho da BL-83, achado novo 1 da auditoria DL-023
# rodada 3): mudar SOMENTE `conta_pai` de uma conta com movimento para
# grupo de natureza oposta — sem tocar natureza, tipo ou empresa. Efeito
# medido: o Balancete fechava (débito = crédito), mas a linha do grupo
# de destino mostrava -R$ 1.000,00 enquanto a do grupo de origem mostrava
# R$ 0,00, e nenhuma das cinco categorias da conferência acusava.
# ---------------------------------------------------------------------------


def test_admin_recusa_reparentar_conta_movimentada_para_grupo_de_natureza_oposta(client, cenario):
    """O cenário exato do defeito medido: grupo 1 (devedor, filha com
    R$ 1.000 D) reparentada para grupo 2 (credor). O Balancete fechava
    mas cada linha ia para lado oposto — sem que nenhuma defesa acusasse."""
    grupo_origem = _conta(
        cenario["empresa"],
        codigo="1",
        nome="Grupo Devedor",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    grupo_destino = _conta(
        cenario["empresa"],
        codigo="2",
        nome="Grupo Credor",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    conta_movimentada = _conta(
        cenario["empresa"],
        codigo="1.1",
        pai=grupo_origem,
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    _com_movimento(cenario, conta_movimentada)
    estado_antes = (
        conta_movimentada.conta_pai_id,
        conta_movimentada.natureza,
        conta_movimentada.tipo,
    )
    _login_admin(client, cenario)

    resposta = _post_change(client, conta_movimentada, {"conta_pai": grupo_destino.pk})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    corpo = resposta.content.decode()
    assert "natureza oposta" in corpo, corpo
    conta_movimentada.refresh_from_db()
    assert conta_movimentada.conta_pai_id == grupo_origem.pk  # inalterada
    estado_final = (
        conta_movimentada.conta_pai_id,
        conta_movimentada.natureza,
        conta_movimentada.tipo,
    )
    assert estado_final == estado_antes


def test_admin_reparentando_sem_movimento_para_natureza_oposta(client, cenario):
    """Controle positivo: sem movimento, reparentar para qualquer grupo é
    operação legítima — a defesa não pode engessar o cadastro."""
    grupo_origem = _conta(
        cenario["empresa"],
        codigo="1",
        natureza=NaturezaConta.DEVEDORA,
    )
    grupo_destino = _conta(
        cenario["empresa"],
        codigo="2",
        natureza=NaturezaConta.CREDORA,
    )
    conta_livre = _conta(
        cenario["empresa"],
        codigo="3",
        pai=grupo_origem,
        natureza=NaturezaConta.DEVEDORA,
    )
    _login_admin(client, cenario)

    resposta = _post_change(client, conta_livre, {"conta_pai": grupo_destino.pk})

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    conta_livre.refresh_from_db()
    assert conta_livre.conta_pai_id == grupo_destino.pk


def test_admin_reparentando_com_movimento_para_mesma_natureza(client, cenario):
    """Com movimento, reparentar para grupo da MESMA natureza é operação
    legítima — a defesa não pode proibir o que é seguro."""
    grupo_origem = _conta(
        cenario["empresa"],
        codigo="1",
        natureza=NaturezaConta.DEVEDORA,
    )
    grupo_destino = _conta(
        cenario["empresa"],
        codigo="1.5",
        natureza=NaturezaConta.DEVEDORA,
    )
    conta_movimentada = _conta(
        cenario["empresa"],
        codigo="1.1",
        pai=grupo_origem,
        natureza=NaturezaConta.DEVEDORA,
    )
    _com_movimento(cenario, conta_movimentada)
    _login_admin(client, cenario)

    resposta = _post_change(client, conta_movimentada, {"conta_pai": grupo_destino.pk})

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    conta_movimentada.refresh_from_db()
    assert conta_movimentada.conta_pai_id == grupo_destino.pk


def test_admin_continua_reparentando_conta_livre_para_grupo_de_natureza_oposta(client, cenario):
    """Conta livre (sem movimento) reparentada para grupo de natureza oposta:
    BL-261 não dispara porque a conta não tem movimento — não há saldo
    a inverter. Critério 4 da DL-023 preservado: conta livre pode
    reclassificar para qualquer grupo."""
    grupo_origem = _conta(
        cenario["empresa"],
        codigo="1",
        natureza=NaturezaConta.DEVEDORA,
    )
    grupo_destino = _conta(
        cenario["empresa"],
        codigo="2",
        natureza=NaturezaConta.CREDORA,
    )
    conta_livre = _conta(
        cenario["empresa"],
        codigo="9",
        pai=grupo_origem,
        natureza=NaturezaConta.DEVEDORA,
    )
    assert not conta_livre.itens_lancamento.exists()
    _login_admin(client, cenario)

    resposta = _post_change(client, conta_livre, {"conta_pai": grupo_destino.pk})

    # Conta livre reparentada para grupo oposto: BL-261 não bloqueia porque
    # não há movimento. Comportamento intencional — não é lacuna.
    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    conta_livre.refresh_from_db()
    assert conta_livre.conta_pai_id == grupo_destino.pk
