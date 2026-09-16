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
    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1"))
    estado_antes = (conta.empresa_id, conta.natureza, conta.tipo, conta.codigo, conta.nome)
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"empresa": cenario["outra_empresa"].id})

    # 200 = formulário reapresentado com erro (302 seria "salvou e
    # redirecionou") — mesmo critério já usado no resto do projeto para
    # distinguir recusa de sucesso no admin.
    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    conta.refresh_from_db()
    # "byte a byte": empresa, natureza e tipo — os três campos que o
    # critério 1 nomeia — continuam exatamente como estavam.
    assert (conta.empresa_id, conta.natureza, conta.tipo, conta.codigo, conta.nome) == estado_antes


# ---------------------------------------------------------------------------
# Critério 2: conta COM FILHAS não muda de empresa
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_empresa_de_conta_com_filhas(client, cenario):
    pai = _conta(cenario["empresa"], codigo="1", tipo=TipoConta.ATIVO)
    _conta(cenario["empresa"], codigo="1.1", pai=pai, nome="Filha")
    _login_admin(client, cenario)

    resposta = _post_change(client, pai, {"empresa": cenario["outra_empresa"].id})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
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
    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1", tipo=TipoConta.ATIVO))
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"tipo": TipoConta.DESPESA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
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


def test_admin_recusa_mover_conta_livre_para_empresa_de_outro_escritorio(client, cenario):
    conta = _conta(cenario["empresa"], codigo="9")
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"empresa": cenario["empresa_outro_escritorio"].id})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
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
    from django.core.exceptions import ValidationError

    conta = _conta(cenario["empresa"], codigo="9")
    conta.empresa = cenario["empresa_outro_escritorio"]

    with pytest.raises(ValidationError):
        conta.full_clean()


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
