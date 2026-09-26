"""DL-043 fatia 3 — as telas de parâmetro contábil (fatia 1) e zeramento do
resultado (fatia 2). Mede a PORTA (permissão, isolamento, tradução de
exceção para mensagem em português, nunca 500, prévia sem gravar, execução
grava exatamente o que a prévia mostrou, idempotência), nunca a regra de
negócio em si — `registrar_parametro_contabil`/`encerrar_vigencia_de_
parametro_contabil`/`pre_visualizar_zeramento`/`zerar_resultado`
(services.py) já são cobertos por test_dl043_parametro_contabil.py e
test_dl043_zeramento_referencia.py/test_dl043_zeramento_concorrencia_e_
permissoes.py, cada um auditado em rodada própria.

Dados 100% sintéticos, criados nos próprios testes. `ROOT_URLCONF` REAL do
produto (`config/urls.py`, sem `pytest.mark.urls`) — mesma escolha de
test_dl031_fechamento_de_competencia.py/test_dl038_recusa_livro_caixa.py.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import (
    Competencia,
    Conta,
    EstadoCompetencia,
    LancamentoContabil,
    NaturezaConta,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento, registrar_parametro_contabil
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA


# ---------------------------------------------------------------------------
# Fixtures e helpers — no molde de test_dl031_fechamento_de_competencia.py.
# ---------------------------------------------------------------------------


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    if papel is not None:
        VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel, username):
    usuario = _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")
    return usuario


def _conta(empresa, *, codigo, nome, tipo, natureza, aceita_lancamento=True):
    return Conta.objects.create(
        empresa=empresa,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        aceita_lancamento=aceita_lancamento,
    )


@pytest.fixture
def cenario():
    """Empresa com plano mínimo para lançar E para zerar: caixa (ativo),
    uma receita, uma despesa, e as três contas de destino do zeramento
    (resultado do exercício e lucros acumulados CREDORAS; (-) prejuízos
    acumulados DEVEDORA — RC-61)."""
    escritorio = Escritorio.objects.create(nome="Escritório DL-043 Telas", cnpj="12345678000195")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Telas DL-043 Ltda", cnpj="11444777000242"
    )
    contas = {
        "caixa": _conta(empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D),
        "receita": _conta(
            empresa, codigo="4.1", nome="Receita de vendas", tipo=TipoConta.RECEITA, natureza=C
        ),
        "despesa": _conta(
            empresa, codigo="5.1", nome="Despesa administrativa", tipo=TipoConta.DESPESA, natureza=D
        ),
        "resultado": _conta(
            empresa,
            codigo="3.4",
            nome="Resultado do Exercício",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=C,
        ),
        "lucros": _conta(
            empresa,
            codigo="3.2",
            nome="Lucros Acumulados",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=C,
        ),
        "prejuizos": _conta(
            empresa,
            codigo="3.3",
            nome="(-) Prejuízos Acumulados",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=D,
        ),
    }
    return {"escritorio": escritorio, "empresa": empresa, **contas}


def _registrar_parametro(
    empresa, contas, *, periodicidade=PeriodicidadeZeramento.MENSAL, inicio=None
):
    """Atalho de PREPARAÇÃO de cenário — chama o SERVIÇO diretamente (não a
    tela), no mesmo espírito de `test_dl031...encerrar_competencia` usado
    para montar estado antes de medir uma tela DIFERENTE."""
    return registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=periodicidade,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=inicio or date(2026, 1, 1),
    )


def _lancar_lucro(empresa, contas, data, usuario, valor="500.00"):
    """Um lançamento com receita > despesa, gerando LUCRO no período."""
    criar_lancamento(
        empresa=empresa,
        data=data,
        historico="Venda de teste",
        itens=[
            {"conta": contas["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": contas["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
        criado_por=usuario,
    )


def _url_parametros(empresa_id):
    return reverse("contabilidade_web:parametros_contabeis", args=[empresa_id])


def _url_encerrar_vigencia(empresa_id):
    return reverse("contabilidade_web:parametro_contabil_encerrar", args=[empresa_id])


def _url_zerar(empresa_id, ano=None, mes=None):
    base = reverse("contabilidade_web:zerar_resultado", args=[empresa_id])
    return base if ano is None else f"{base}?ano={ano}&mes={mes}"


# ---------------------------------------------------------------------------
# Parâmetros contábeis — leitura, permissão, cadastro, erro preservado,
# encerramento de vigência, isolamento.
# ---------------------------------------------------------------------------


def test_lista_vazia_e_visivel_para_quem_le(client, cenario):
    _autenticar(client, cenario["escritorio"], Papel.ANALISTA, "p1-analista")
    resposta = client.get(_url_parametros(cenario["empresa"].id))
    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "ainda não tem parâmetro contábil registrado" in corpo
    # Critério: ANALISTA lê, mas o formulário de registrar não aparece —
    # nem o botão "Encerrar vigência" (não há vigência nenhuma ainda, mas
    # o teste abaixo, com vigência, cobre esse segundo ponto).
    assert "Registrar vigência" not in corpo
    assert "exige administrador ou gestor" in corpo


def test_cliente_nao_le_a_lista(client, cenario):
    _autenticar(client, cenario["escritorio"], Papel.CLIENTE, "p1-cliente")
    resposta = client.get(_url_parametros(cenario["empresa"].id))
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]


def test_gestor_registra_vigencia_com_sucesso(client, cenario):
    empresa, contas = cenario["empresa"], cenario
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "p1-gestor")

    resposta = client.post(
        _url_parametros(empresa.id),
        data={
            "periodicidade_zeramento": PeriodicidadeZeramento.MENSAL,
            "conta_resultado_do_exercicio": contas["resultado"].id,
            "conta_lucros_acumulados": contas["lucros"].id,
            "conta_prejuizos_acumulados": contas["prejuizos"].id,
            "vigencia_inicio": "2026-01-01",
        },
        follow=True,
    )

    assert resposta.status_code == 200
    assert ParametroContabilEmpresa.objects.filter(empresa=empresa).count() == 1
    vigencia = ParametroContabilEmpresa.objects.get(empresa=empresa)
    assert vigencia.periodicidade_zeramento == PeriodicidadeZeramento.MENSAL
    assert vigencia.vigencia_fim is None
    corpo = resposta.content.decode()
    assert "registrada com sucesso" in corpo
    assert "Vigente" in corpo


def test_analista_forcando_post_recebe_403_e_nada_e_gravado(client, cenario):
    empresa, contas = cenario["empresa"], cenario
    _autenticar(client, cenario["escritorio"], Papel.ANALISTA, "p1-analista-forca")

    resposta = client.post(
        _url_parametros(empresa.id),
        data={
            "periodicidade_zeramento": PeriodicidadeZeramento.MENSAL,
            "conta_resultado_do_exercicio": contas["resultado"].id,
            "conta_lucros_acumulados": contas["lucros"].id,
            "conta_prejuizos_acumulados": contas["prejuizos"].id,
            "vigencia_inicio": "2026-01-01",
        },
    )

    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    assert ParametroContabilEmpresa.objects.filter(empresa=empresa).count() == 0


def test_select_de_prejuizos_recusa_conta_credora_antes_do_servico(client, cenario):
    """RC-61: o recorte de CONVENIÊNCIA do `<select>` (`ParametroContabilForm.
    __init__`) só lista contas DEVEDORAS para "conta de prejuízos" — enviar
    uma conta CREDORA (aqui, a própria "Lucros Acumulados") nunca chega a
    alcançar o serviço: o PRÓPRIO Django recusa como "não é uma escolha
    válida" (`ModelChoiceField`), porque a conta está fora do `queryset`
    filtrado. O formulário volta com o erro, e o que a pessoa digitou nos
    OUTROS campos continua nos widgets (arquétipo B: "o formulário não
    some quando dá erro")."""
    empresa, contas = cenario["empresa"], cenario
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "p1-erro-preservado")

    resposta = client.post(
        _url_parametros(empresa.id),
        data={
            "periodicidade_zeramento": PeriodicidadeZeramento.MENSAL,
            "conta_resultado_do_exercicio": contas["resultado"].id,
            "conta_lucros_acumulados": contas["lucros"].id,
            # Errada de propósito: CREDORA, deveria ser DEVEDORA (RC-61) —
            # fora do queryset filtrado do campo.
            "conta_prejuizos_acumulados": contas["lucros"].id,
            "vigencia_inicio": "2026-05-17",
        },
    )

    assert resposta.status_code == 400
    assert ParametroContabilEmpresa.objects.filter(empresa=empresa).count() == 0
    corpo = resposta.content.decode()
    assert "Faça uma escolha válida" in corpo
    # O que a pessoa digitou continua no formulário — valor exato do campo
    # de data, e a conta CERTA (resultado) continua selecionada.
    assert 'value="2026-05-17"' in corpo


def test_erro_do_servico_preserva_o_formulario_e_nada_e_gravado(client, cenario):
    """Um erro que o `<select>` NÃO consegue prevenir por si só (depende do
    ESTADO já gravado, não de qual conta foi escolhida): registrar uma
    vigência nova com início ANTERIOR ao início da vigência aberta atual —
    `registrar_parametro_contabil` recusa (ParametroContabilInvalido),
    porque a nova teria de começar DEPOIS. Chega de verdade ao serviço."""
    empresa, contas = cenario["empresa"], cenario
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "p1-erro-servico")
    _registrar_parametro(empresa, cenario, inicio=date(2026, 6, 1))

    resposta = client.post(
        _url_parametros(empresa.id),
        data={
            "periodicidade_zeramento": PeriodicidadeZeramento.MENSAL,
            "conta_resultado_do_exercicio": contas["resultado"].id,
            "conta_lucros_acumulados": contas["lucros"].id,
            "conta_prejuizos_acumulados": contas["prejuizos"].id,
            # Antes do início da vigência aberta (2026-06-01) — recusado.
            "vigencia_inicio": "2026-01-15",
        },
    )

    assert resposta.status_code == 400
    assert ParametroContabilEmpresa.objects.filter(empresa=empresa).count() == 1
    corpo = resposta.content.decode()
    assert "deve começar depois do início da vigência atual" in corpo
    assert 'value="2026-01-15"' in corpo


def test_encerrar_vigencia_com_sucesso(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.ADMINISTRADOR, "p1-encerra")
    _registrar_parametro(empresa, cenario, inicio=date(2020, 1, 1))

    resposta = client.post(_url_encerrar_vigencia(empresa.id), data={}, follow=True)

    assert resposta.status_code == 200
    vigencia = ParametroContabilEmpresa.objects.get(empresa=empresa)
    assert vigencia.vigencia_fim is not None
    assert "encerrada hoje" in resposta.content.decode()


def test_encerrar_vigencia_sem_vigencia_aberta_mostra_mensagem_do_servico(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.ADMINISTRADOR, "p1-sem-vigencia")

    resposta = client.post(_url_encerrar_vigencia(empresa.id), data={}, follow=True)

    assert resposta.status_code == 200
    assert "não tem vigência de parâmetro contábil aberta" in resposta.content.decode()


def test_encerrar_vigencia_sem_permissao_403_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.ANALISTA, "p1-encerra-sem-permissao")
    _registrar_parametro(empresa, cenario, inicio=date(2020, 1, 1))

    resposta = client.post(_url_encerrar_vigencia(empresa.id), data={})

    assert resposta.status_code == 403
    vigencia = ParametroContabilEmpresa.objects.get(empresa=empresa)
    assert vigencia.vigencia_fim is None


def test_encerrar_vigencia_via_get_e_405(client, cenario):
    _autenticar(client, cenario["escritorio"], Papel.ADMINISTRADOR, "p1-get-405")
    resposta = client.get(_url_encerrar_vigencia(cenario["empresa"].id))
    assert resposta.status_code == 405


def test_isolamento_parametros_empresa_de_outro_escritorio_e_404(client, cenario):
    outro_escritorio = Escritorio.objects.create(nome="Outro Escritório", cnpj="99888777000111")
    _autenticar(client, outro_escritorio, Papel.ADMINISTRADOR, "p1-outro-escritorio")

    resposta = client.get(_url_parametros(cenario["empresa"].id))

    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Zeramento — estados (sem parâmetro, fora da periodicidade, encerrada,
# nada a zerar), prévia sem gravar, confirmação bate com a prévia,
# idempotência pela tela, permissão, isolamento.
# ---------------------------------------------------------------------------


def test_previa_sem_parametro_vigente_explica_e_linka_para_cadastro(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-sem-parametro")

    resposta = client.get(_url_zerar(empresa.id, 2026, 3))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "não tem parâmetro contábil vigente" in corpo
    assert _url_parametros(empresa.id) in corpo
    # Nenhum botão de confirmação nesta tela — nada para gravar.
    assert "Gerar lançamentos de zeramento" not in corpo


def test_previa_fora_da_periodicidade_mostra_mensagem_do_servico(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-fora-periodicidade")
    _registrar_parametro(empresa, cenario, periodicidade=PeriodicidadeZeramento.TRIMESTRAL)
    _lancar_lucro(empresa, cenario, date(2026, 2, 15), usuario)

    # Fevereiro não é mês de encerramento trimestral (só mar/jun/set/dez).
    resposta = client.get(_url_zerar(empresa.id, 2026, 2))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "periodicidade vigente desta empresa é" in corpo
    assert "Gerar lançamentos de zeramento" not in corpo


def test_previa_competencia_encerrada_recusa_sem_oferecer_o_botao(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-encerrada")
    _registrar_parametro(empresa, cenario)
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario)
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=3)
    competencia.estado = EstadoCompetencia.ENCERRADA
    competencia.save(update_fields=["estado"])

    resposta = client.get(_url_zerar(empresa.id, 2026, 3))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "está encerrada" in corpo
    assert "RC-103" in corpo
    assert "Gerar lançamentos de zeramento" not in corpo


def test_previa_nada_a_zerar_quando_nao_ha_movimento(client, cenario):
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-nada-a-zerar")
    _registrar_parametro(empresa, cenario)

    resposta = client.get(_url_zerar(empresa.id, 2026, 3))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "Nada a zerar neste período" in corpo
    assert "Gerar lançamentos de zeramento" not in corpo


def test_previa_nao_grava_nenhum_lancamento(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-previa-nao-grava")
    _registrar_parametro(empresa, cenario)
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario)
    antes = LancamentoContabil.objects.filter(empresa=empresa).count()

    resposta = client.get(_url_zerar(empresa.id, 2026, 3))

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "Gerar lançamentos de zeramento" in corpo
    # A prévia mostra a conta de receita e a contrapartida em resultado —
    # confirmando que ela CALCULOU algo, sem ter gravado nada (linha
    # abaixo é a prova).
    assert "Receita de vendas" in corpo
    depois = LancamentoContabil.objects.filter(empresa=empresa).count()
    assert depois == antes


def test_confirmacao_grava_exatamente_o_que_a_previa_mostrou(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-confirma-bate")
    _registrar_parametro(empresa, cenario)
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario, valor="500.00")

    previa = client.get(_url_zerar(empresa.id, 2026, 3)).content.decode()
    assert "500,00" in previa
    assert "lucros acumulados (lucro)" in previa

    resposta = client.post(
        _url_zerar(empresa.id),
        data={"ano": 2026, "mes": 3, "confirmar_zeramento": "1"},
    )

    assert resposta.status_code == 200
    resultado_html = resposta.content.decode()
    assert "gerado agora" in resultado_html

    # Os DOIS lançamentos gravados batem com o que a prévia mostrou: a
    # etapa 1 zera a receita de 500,00 contra "resultado do exercício", e
    # a etapa 2 transfere 500,00 de "resultado do exercício" para "lucros
    # acumulados" — mesmo valor, mesma direção que a prévia anunciou.
    lancamentos = list(
        LancamentoContabil.objects.filter(empresa=empresa, data=date(2026, 3, 31)).order_by("id")
    )
    assert len(lancamentos) == 2
    for lancamento in lancamentos:
        totais = {TipoPartida.DEBITO: Decimal("0"), TipoPartida.CREDITO: Decimal("0")}
        for item in lancamento.itens.all():
            totais[item.tipo] += item.valor
        assert totais[TipoPartida.DEBITO] == totais[TipoPartida.CREDITO] == Decimal("500.00")

    lucros = Conta.objects.get(pk=cenario["lucros"].id)
    item_lucros = lucros.itens_lancamento.filter(lancamento__empresa=empresa).get()
    assert item_lucros.valor == Decimal("500.00")
    assert item_lucros.tipo == TipoPartida.CREDITO


def test_confirmacao_sem_marcar_a_caixa_nao_grava_e_volta_a_previa(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-sem-confirmar")
    _registrar_parametro(empresa, cenario)
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario)

    resposta = client.post(_url_zerar(empresa.id), data={"ano": 2026, "mes": 3}, follow=True)

    assert resposta.status_code == 200
    assert "nada foi gravado" in resposta.content.decode()
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == 1  # só o lucro lançado


def test_repeticao_pela_tela_e_idempotente(client, cenario):
    """Critério "repetição idempotente pela tela": repetir a confirmação
    sem movimento novo no período não grava nada a mais — `_saldo_
    assinado_ate` (services.py) já encontra toda conta zerada pela
    primeira chamada, então `_calcular_zeramento` devolve `itens_etapa1`
    vazia e `etapa2=None` na segunda vez (não é "reaproveitar um
    lançamento existente por chave", é literalmente "nada mais a
    calcular") — o mesmo comportamento que `test_dl043_zeramento_
    referencia.py` mede no nível do serviço; aqui a prova é que a TELA
    traduz isso para o mesmo texto explicativo da prévia ("nada a
    zerar"), nunca um lançamento duplicado nem um erro."""
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-idempotente")
    _registrar_parametro(empresa, cenario)
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario)

    dados = {"ano": 2026, "mes": 3, "confirmar_zeramento": "1"}
    primeira = client.post(_url_zerar(empresa.id), data=dados)
    assert "gerado agora" in primeira.content.decode()
    quantidade_apos_primeira = LancamentoContabil.objects.filter(empresa=empresa).count()

    segunda = client.post(_url_zerar(empresa.id), data=dados)
    assert segunda.status_code == 200
    corpo_segunda = segunda.content.decode()
    assert "Nenhuma conta de receita ou despesa tinha saldo a zerar" in corpo_segunda
    assert "já estava zerado depois da etapa acima" in corpo_segunda
    assert "gerado agora" not in corpo_segunda
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == quantidade_apos_primeira


def test_analista_le_previa_mas_nao_confirma(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.ADMINISTRADOR, "z1-setup-analista")
    _registrar_parametro(empresa, cenario)
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario)
    client.logout()
    _autenticar(client, cenario["escritorio"], Papel.ANALISTA, "z1-analista-le")

    resposta_get = client.get(_url_zerar(empresa.id, 2026, 3))
    assert resposta_get.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta_get.templates]

    resposta_post = client.post(
        _url_zerar(empresa.id), data={"ano": 2026, "mes": 3, "confirmar_zeramento": "1"}
    )
    assert resposta_post.status_code == 403
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == 1  # só o lucro lançado


def test_isolamento_zerar_empresa_de_outro_escritorio_e_404(client, cenario):
    outro_escritorio = Escritorio.objects.create(nome="Outro Escritório Z", cnpj="99888777000222")
    _autenticar(client, outro_escritorio, Papel.ADMINISTRADOR, "z1-outro-escritorio")

    resposta = client.get(_url_zerar(cenario["empresa"].id, 2026, 3))

    assert resposta.status_code == 404


def test_resultado_mostra_link_para_os_lancamentos_gerados(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "z1-links-resultado")
    _registrar_parametro(empresa, cenario)
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario)

    resposta = client.post(
        _url_zerar(empresa.id), data={"ano": 2026, "mes": 3, "confirmar_zeramento": "1"}
    )

    corpo = resposta.content.decode()
    lancamentos = list(LancamentoContabil.objects.filter(empresa=empresa).order_by("id"))
    # O lançamento de MOVIMENTO (o lucro sintético) não é de zeramento —
    # os DOIS últimos são os que o POST acabou de gravar.
    etapa1, etapa2 = lancamentos[-2], lancamentos[-1]
    assert reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, etapa1.id]) in corpo
    assert reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, etapa2.id]) in corpo


# ---------------------------------------------------------------------------
# Integração com o painel de fechamento — o link de entrada da ação.
# ---------------------------------------------------------------------------


def test_link_zerar_resultado_aparece_no_painel_de_fechamento(client, cenario):
    empresa = cenario["empresa"]
    usuario = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "f1-link-zerar")
    _lancar_lucro(empresa, cenario, date(2026, 3, 15), usuario)

    resposta = client.get(reverse("contabilidade_web:fechamento", args=[empresa.id]))

    corpo = resposta.content.decode()
    assert ">Zerar resultado<" in corpo
    assert _url_parametros(empresa.id) in corpo
