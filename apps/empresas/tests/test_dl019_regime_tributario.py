"""BL-153 (faixa do RC-81 + hipótese HI-07) e BL-162 (exclusão do último
período, RC-82/DE-035) — achado R6-6 da auditoria DL-017 rodada 6.

**O defeito medido:** `POST regime-tributario {"vigencia_inicio":
"9999-12-31"}` respondia **201**. `9999-12-31` é `date.max`, não existe data
posterior, a regra de vigência crescente exige que a próxima comece depois — e
não havia `PUT`, `DELETE` nem tela de edição. **A empresa nunca mais podia ter
regime registrado**, e só acesso direto ao banco desfazia. Um dígito errado
congelava para sempre o histórico do dado que governa a apuração fiscal.

**Duas metades, com origens diferentes, e isto está escrito porque a diferença
importa:**

- O **teto em hoje** é regra confirmada (RC-81, Fred em 2026-09-15, resposta
  literal "Não" a "o escritório registra regime com vigência futura?"). Fecha a
  armadilha por construção: `date.max` não entra, e amanhã sempre existe data
  posterior à última registrada.
- O **piso em 01/01/2000** é **hipótese** (HI-07): o RC-77 confirma esse piso
  para DATA DE LANÇAMENTO, e ninguém o confirmou para regime tributário. Os
  testes do piso existem para fixar o comportamento ATUAL, não para afirmar
  regra — se o Fred baixar o piso, eles mudam junto com a hipótese.

A **exclusão** segue RC-82 ("apagar", decisão do Fred contra a recomendação do
`arquiteto-senior`) com o alcance da DE-035: só o último período, o anterior
volta a vigente, e o evento vai para `RegistroAuditoria` — o registro sai do
produto, a trilha técnica fica.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.empresas.services import (
    ExclusaoDeRegimeInvalida,
    excluir_ultimo_regime_tributario,
    registrar_regime_tributario,
)
from apps.empresas.validators import VIGENCIA_REGIME_MINIMA, validar_vigencia_de_regime
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório RC-81", cnpj="88888888000188")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa RC-81 Ltda", cnpj="11222333000181"
    )
    outra = Empresa.objects.create(
        escritorio=escritorio, razao_social="Outra RC-81 Ltda", cnpj="ab123cde000155"
    )
    gestora = get_user_model().objects.create_user(
        username="gestora-rc81", email="gestora-rc81@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=gestora, escritorio=escritorio, papel=Papel.GESTOR
    )
    analista = get_user_model().objects.create_user(
        username="analista-rc81", email="analista-rc81@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=analista, escritorio=escritorio, papel=Papel.ANALISTA
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "outra_empresa": outra,
        "gestora": gestora,
        "analista": analista,
    }


def _url_lista(cenario, empresa=None):
    return reverse("empresas:api-regime-tributario", args=[(empresa or cenario["empresa"]).id])


def _url_detalhe(cenario, registro, empresa=None):
    return reverse(
        "empresas:api-regime-tributario-detalhe",
        args=[(empresa or cenario["empresa"]).id, registro.pk],
    )


# ---------------------------------------------------------------------------
# RC-81 — teto em hoje (regra confirmada)
# ---------------------------------------------------------------------------


def test_vigencia_futura_e_recusada_pelo_dominio(cenario):
    with pytest.raises(ValueError) as erro:
        registrar_regime_tributario(
            cenario["empresa"], RegimeTributario.SIMPLES_NACIONAL, date(9999, 12, 31)
        )

    assert "não pode ser futura" in str(erro.value)
    assert not HistoricoRegimeTributario.objects.exists()


def test_vigencia_de_amanha_e_recusada(cenario):
    """O teto é HOJE, não "este ano": um dia à frente já é futuro, e o teste
    calcula a data em vez de escrevê-la — literal passaria a testar outra coisa
    amanhã."""
    with pytest.raises(ValueError):
        registrar_regime_tributario(
            cenario["empresa"],
            RegimeTributario.LUCRO_REAL,
            timezone.localdate() + timedelta(days=1),
        )

    assert not HistoricoRegimeTributario.objects.exists()


def test_vigencia_de_hoje_e_aceita(cenario):
    registro = registrar_regime_tributario(
        cenario["empresa"], RegimeTributario.LUCRO_REAL, timezone.localdate()
    )

    assert registro.vigencia_inicio == timezone.localdate()


@pytest.mark.parametrize("vigencia", ["9999-12-31", "2099-01-01"])
def test_api_recusa_vigencia_futura_com_400(client, cenario, vigencia):
    assert client.login(username="gestora-rc81", password=SENHA)

    resposta = client.post(
        _url_lista(cenario),
        {"regime": "simples_nacional", "vigencia_inicio": vigencia},
        content_type="application/json",
    )

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert not HistoricoRegimeTributario.objects.exists()


def test_api_continua_aceitando_vigencia_passada(client, cenario):
    assert client.login(username="gestora-rc81", password=SENHA)

    resposta = client.post(
        _url_lista(cenario),
        {"regime": "simples_nacional", "vigencia_inicio": "2024-01-01"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)


def test_amanha_sempre_existe_data_posterior_a_ultima_registrada(cenario):
    """É o que a armadilha do R6-6 exigia, e o motivo pelo qual o teto de
    "hoje" a fecha por construção: registrado o regime mais recente possível
    (hoje), a própria regra de vigência crescente continua satisfazível — basta
    o dia seguinte. Antes, com `9999-12-31` aceito, não havia dia seguinte."""
    registrar_regime_tributario(
        cenario["empresa"], RegimeTributario.SIMPLES_NACIONAL, timezone.localdate()
    )
    ultima = HistoricoRegimeTributario.objects.filter(empresa=cenario["empresa"]).first()

    assert ultima.vigencia_inicio < ultima.vigencia_inicio + timedelta(days=1)
    assert ultima.vigencia_inicio <= timezone.localdate()


# ---------------------------------------------------------------------------
# HI-07 — piso em 2000 (HIPÓTESE declarada, não regra confirmada)
# ---------------------------------------------------------------------------


def test_vigencia_anterior_ao_piso_e_recusada_enquanto_a_hipotese_valer(cenario):
    """HI-07: se o Fred confirmar outro piso, este teste muda junto — ele fixa
    o comportamento atual e o nomeia como hipótese, em vez de deixar o campo
    sem piso nenhum (o que manteria metade do defeito: `0001-01-01` entrando)."""
    with pytest.raises(ValueError) as erro:
        registrar_regime_tributario(
            cenario["empresa"], RegimeTributario.LUCRO_REAL, date(1999, 12, 31)
        )

    assert "anterior a" in str(erro.value)
    assert VIGENCIA_REGIME_MINIMA == date(2000, 1, 1)


def test_vigencia_no_piso_exato_e_aceita(cenario):
    registro = registrar_regime_tributario(
        cenario["empresa"], RegimeTributario.LUCRO_REAL, VIGENCIA_REGIME_MINIMA
    )

    assert registro.vigencia_inicio == VIGENCIA_REGIME_MINIMA


# ---------------------------------------------------------------------------
# A outra superfície de escrita deste campo: o admin (item 2 da DE-034)
# ---------------------------------------------------------------------------


def test_validador_de_campo_recusa_vigencia_futura(cenario):
    with pytest.raises(ValidationError):
        validar_vigencia_de_regime(timezone.localdate() + timedelta(days=1))

    validar_vigencia_de_regime(timezone.localdate())  # não levanta


def test_admin_recusa_vigencia_futura_no_inline_e_nao_grava(client, cenario):
    """Exercita o ADMIN de verdade, com POST autenticado — `full_clean()` verde
    não prova que o admin chama `full_clean()`.

    O `HistoricoRegimeTributarioInline` grava por `ModelForm` e NUNCA passa por
    `registrar_regime_tributario`: sem o validador de campo, o admin era a
    porta por onde `9999-12-31` continuava entrando."""
    get_user_model().objects.create_superuser(
        username="admin-rc81", email="admin-rc81@escritorio.com.br", password=SENHA
    )
    assert client.login(username="admin-rc81", password=SENHA)
    empresa = cenario["empresa"]

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        {
            "escritorio": cenario["escritorio"].pk,
            "razao_social": empresa.razao_social,
            "nome_fantasia": "",
            "cnpj": empresa.cnpj,
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
            "historico_regime_tributario-TOTAL_FORMS": "1",
            "historico_regime_tributario-INITIAL_FORMS": "0",
            "historico_regime_tributario-MIN_NUM_FORMS": "0",
            "historico_regime_tributario-MAX_NUM_FORMS": "1000",
            "historico_regime_tributario-0-regime": "simples_nacional",
            "historico_regime_tributario-0-vigencia_inicio": "9999-12-31",
            "historico_regime_tributario-0-vigencia_fim": "",
            "_continue": "Salvar e continuar editando",
        },
    )

    # 200 = formulário reapresentado com erro (302 seria "salvou e redirecionou").
    assert resposta.status_code == 200, resposta.status_code
    assert not HistoricoRegimeTributario.objects.exists()


def test_admin_grava_vigencia_passada_no_inline(client, cenario):
    """Controle positivo do MESMO caminho: sem ele, o teste acima passaria
    igual se o admin estivesse quebrado por qualquer outro motivo (campo
    faltando, permissão, formset mal montado) — e eu concluiria "o validador
    funciona" a partir de um 200 que não tem nada a ver com ele."""
    get_user_model().objects.create_superuser(
        username="admin2-rc81", email="admin2-rc81@escritorio.com.br", password=SENHA
    )
    assert client.login(username="admin2-rc81", password=SENHA)
    empresa = cenario["empresa"]

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        {
            "escritorio": cenario["escritorio"].pk,
            "razao_social": empresa.razao_social,
            "nome_fantasia": "",
            "cnpj": empresa.cnpj,
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
            "historico_regime_tributario-TOTAL_FORMS": "1",
            "historico_regime_tributario-INITIAL_FORMS": "0",
            "historico_regime_tributario-MIN_NUM_FORMS": "0",
            "historico_regime_tributario-MAX_NUM_FORMS": "1000",
            "historico_regime_tributario-0-regime": "simples_nacional",
            "historico_regime_tributario-0-vigencia_inicio": "2024-03-01",
            "historico_regime_tributario-0-vigencia_fim": "",
            "_continue": "Salvar e continuar editando",
        },
    )

    assert resposta.status_code == 302, resposta.status_code
    assert HistoricoRegimeTributario.objects.count() == 1


# ---------------------------------------------------------------------------
# BL-162 / RC-82 / DE-035 — exclusão do último período
# ---------------------------------------------------------------------------


def _dois_periodos(cenario):
    primeiro = registrar_regime_tributario(
        cenario["empresa"], RegimeTributario.SIMPLES_NACIONAL, date(2024, 1, 1)
    )
    segundo = registrar_regime_tributario(
        cenario["empresa"], RegimeTributario.LUCRO_PRESUMIDO, date(2025, 1, 1)
    )
    primeiro.refresh_from_db()
    assert primeiro.vigencia_fim == date(2024, 12, 31)
    return primeiro, segundo


def test_apagar_o_ultimo_devolve_o_anterior_a_condicao_de_vigente(cenario):
    """Item 2 da DE-035, e o ponto onde o defeito silencioso mora: sem a
    reabertura, apagar "funciona" e deixa a empresa **sem regime vigente** —
    exatamente o estado que a exclusão existe para consertar."""
    primeiro, segundo = _dois_periodos(cenario)

    excluir_ultimo_regime_tributario(
        empresa=cenario["empresa"], registro=segundo, usuario=cenario["gestora"]
    )

    primeiro.refresh_from_db()
    assert primeiro.vigencia_fim is None
    assert not HistoricoRegimeTributario.objects.filter(pk=segundo.pk).exists()


def test_depois_de_apagar_nao_sobra_intervalo_sem_regime(cenario):
    """A garantia escrita no critério da BL-162, verificada pelo efeito: para
    cada dia entre o início do primeiro período e hoje existe EXATAMENTE um
    período cobrindo aquele dia."""
    primeiro, segundo = _dois_periodos(cenario)
    excluir_ultimo_regime_tributario(
        empresa=cenario["empresa"], registro=segundo, usuario=cenario["gestora"]
    )

    periodos = list(HistoricoRegimeTributario.objects.filter(empresa=cenario["empresa"]))
    dias = [date(2024, 1, 1), date(2024, 12, 31), date(2025, 1, 1), timezone.localdate()]
    for dia in dias:
        cobrindo = [
            periodo
            for periodo in periodos
            if periodo.vigencia_inicio <= dia
            and (periodo.vigencia_fim is None or dia <= periodo.vigencia_fim)
        ]
        assert len(cobrindo) == 1, (dia, cobrindo)


def test_apagar_periodo_do_meio_e_recusado_e_nada_muda(cenario):
    """Item 1 da DE-035: apagar o período do meio abriria buraco na linha do
    tempo — o antecessor já teve a `vigencia_fim` recortada, e sem o sucessor
    aquele intervalo fica sem regime nenhum. Empresa sem regime numa
    competência é pior que empresa com regime errado, porque a apuração não tem
    nem o que conferir."""
    primeiro, segundo = _dois_periodos(cenario)

    with pytest.raises(ExclusaoDeRegimeInvalida) as erro:
        excluir_ultimo_regime_tributario(
            empresa=cenario["empresa"], registro=primeiro, usuario=cenario["gestora"]
        )

    assert "último" in str(erro.value)
    primeiro.refresh_from_db()
    segundo.refresh_from_db()
    assert HistoricoRegimeTributario.objects.count() == 2
    assert primeiro.vigencia_fim == date(2024, 12, 31)


def test_apagar_o_unico_periodo_deixa_a_empresa_sem_historico(cenario):
    """Caso de borda legítimo: um único período errado, apagado, devolve a
    empresa ao estado "sem regime registrado" — que é recuperável (basta
    registrar de novo) e é o que o contador quer quando errou o primeiro."""
    unico = registrar_regime_tributario(
        cenario["empresa"], RegimeTributario.SIMPLES_NACIONAL, date(2024, 1, 1)
    )

    excluir_ultimo_regime_tributario(
        empresa=cenario["empresa"], registro=unico, usuario=cenario["gestora"]
    )

    assert not HistoricoRegimeTributario.objects.exists()


def test_exclusao_grava_trilha_com_os_valores_antigos_e_o_autor(cenario):
    """Item 3 da DE-035. O REGISTRO sai do histórico do produto; o FATO de
    alguém ter apagado fica na trilha técnica — distinção apresentada ao Fred e
    confirmada por ele ("Concordo com você", 2026-09-15). Sem segredo nenhum
    nos detalhes: regime, datas e ids."""
    primeiro, segundo = _dois_periodos(cenario)

    excluir_ultimo_regime_tributario(
        empresa=cenario["empresa"], registro=segundo, usuario=cenario["gestora"]
    )

    registro = RegistroAuditoria.objects.filter(acao="regime_tributario.excluido").first()
    assert registro is not None
    assert registro.usuario_id == cenario["gestora"].pk
    assert registro.objeto_tipo == "HistoricoRegimeTributario"
    assert registro.objeto_id == str(segundo.pk)
    assert registro.detalhes["regime"] == RegimeTributario.LUCRO_PRESUMIDO
    assert registro.detalhes["vigencia_inicio"] == "2025-01-01"
    assert registro.detalhes["vigencia_fim_reaberta_do_periodo_anterior"] == "2024-12-31"


def test_api_apaga_o_ultimo_periodo(client, cenario):
    assert client.login(username="gestora-rc81", password=SENHA)
    primeiro, segundo = _dois_periodos(cenario)

    resposta = client.delete(_url_detalhe(cenario, segundo))

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    corpo = resposta.json()
    assert corpo["apagado"]["vigencia_inicio"] == "2025-01-01"
    primeiro.refresh_from_db()
    assert primeiro.vigencia_fim is None


def test_api_recusa_exclusao_de_periodo_do_meio(client, cenario):
    assert client.login(username="gestora-rc81", password=SENHA)
    primeiro, _ = _dois_periodos(cenario)

    resposta = client.delete(_url_detalhe(cenario, primeiro))

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert HistoricoRegimeTributario.objects.count() == 2


def test_papel_sem_gestao_recebe_recusa_no_servidor(client, cenario):
    """Autorização no SERVIDOR, não ausência de botão: o ANALISTA não tem
    `PodeGerenciarEmpresa` e recebe 403 mesmo chamando a rota direto."""
    assert client.login(username="analista-rc81", password=SENHA)
    _, segundo = _dois_periodos(cenario)

    resposta = client.delete(_url_detalhe(cenario, segundo))

    assert resposta.status_code == 403, (resposta.status_code, resposta.content)
    assert HistoricoRegimeTributario.objects.count() == 2


def test_registro_de_outra_empresa_nao_e_apagado(client, cenario):
    """Isolamento: `registro_id` de outra empresa responde 404 e não apaga
    nada, mesmo com o escritório ativo correto."""
    assert client.login(username="gestora-rc81", password=SENHA)
    da_outra = registrar_regime_tributario(
        cenario["outra_empresa"], RegimeTributario.LUCRO_REAL, date(2024, 5, 1)
    )

    resposta = client.delete(
        reverse(
            "empresas:api-regime-tributario-detalhe",
            args=[cenario["empresa"].id, da_outra.pk],
        )
    )

    assert resposta.status_code == 404, resposta.status_code
    assert HistoricoRegimeTributario.objects.filter(pk=da_outra.pk).exists()
