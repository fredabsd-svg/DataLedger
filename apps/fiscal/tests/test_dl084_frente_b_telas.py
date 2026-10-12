"""DL-084, frente B2: telas do Lucro Presumido (parâmetros, feriados locais, CSLL a classificar,
encerramento de medida, pendências do mês, antecipação do vencimento e sugestão de natureza).

- Caminho feliz, erro e permissão para cada tela nova; mutação do critério 9: remover a checagem de
  permissão de qualquer tela nova derruba os testes de permissão.
- O aviso de antecipação aparece quando cabe e não aparece quando não cabe.
- A pendência do mês lista a empresa certa e só a do escritório ativo.
- A CSLL "a classificar" mostra o aviso ("o tomador reteve só a CSLL?") e a tela não confirma
  sozinha.
- Encerrar medida não apaga o histórico e a revogação continua funcionando.
- O aviso "calendário a conferir" não aparece em nenhuma resposta.

Datas de vencimento e faixas esperadas escritas à mão, do serviço já testado na frente A
(`test_dl084_calendario.py`). Dados 100% sintéticos; os feriados de Palmas são os da carga real.
"""

import re
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import (
    Estabelecimento,
    HistoricoRegimeTributario,
    RegimeTributario,
    TipoEstabelecimento,
)
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal import views_web
from apps.fiscal.models import (
    ConfirmacaoRetencaoPresumido,
    EncerramentoMedidaJudicialLC224,
    ExcecaoFeriadoLocal,
    FeriadoLocal,
    NaturezaOperacaoNFe,
    ParametrosPresumidoEmpresa,
)
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
AVISO_BANCARIO_PALMAS = "feriado bancário em Palmas (Febraban)"
AVISO_ANTECIPAR = "antecipar: sem expediente bancário na praça"
AVISO_CONFIRMAR = "feriado local: confirmar expediente bancário na praça"


# ---------------------------------------------------------------------------
# Auxiliares: usuários, URLs, HTML e a checagem de referências de id
# ---------------------------------------------------------------------------


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio-fiscal-teste.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _url(nome, *args, **consulta):
    url = reverse(f"fiscal_web:{nome}", args=list(args))
    return url + ("?" + urlencode(consulta) if consulta else "")


def _html(resposta):
    return resposta.content.decode("utf-8")


def _ids_referenciados_existem(html):
    """Todo `aria-describedby` e todo `for` aponta para um `id` que existe na própria página."""
    existentes = set(re.findall(r'\bid="([^"]+)"', html))
    referencias = set()
    for bloco in re.findall(r'aria-describedby="([^"]+)"', html):
        referencias.update(bloco.split())
    referencias.update(re.findall(r'\bfor="([^"]+)"', html))
    return referencias - existentes


def _linha_que_contem(html, trecho):
    """A `<tr>` inteira que contém o trecho — para conferir o aviso DA LINHA, não o da página."""
    for linha in re.findall(r"<tr>.*?</tr>", html, re.S):
        if trecho in linha:
            return linha
    raise AssertionError(f"não há linha com {trecho!r} no HTML")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-dl084b2")


@pytest.fixture
def paralegal(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl084b2")


def _matriz(empresa, municipio, uf):
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz sintética",
        cnpj="11222333000181",
        municipio=municipio,
        uf=uf,
    )


@pytest.fixture
def empresa_presumida(empresa_a, usuario_gestor_a):
    """Empresa de Lucro Presumido desde 2026, critério de competência, comércio como padrão."""
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    servico.criar_atividade(
        empresa_a,
        {"atividade": COMERCIO, "inicio": date(2026, 1, 1), "padrao": True},
        usuario_gestor_a,
    )
    return empresa_a


@pytest.fixture
def empresa_palmas(empresa_presumida):
    """A empresa presumida, com matriz em Palmas/TO: a praça dos feriados locais."""
    _matriz(empresa_presumida, "Palmas", "TO")
    return empresa_presumida


# ---------------------------------------------------------------------------
# 1. Parâmetros da empresa (item 6): leitura, gravação, erro campo a campo e permissão
# ---------------------------------------------------------------------------


def test_parametros_da_empresa_mostram_o_padrao_do_escritorio(
    client, empresa_presumida, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    resposta = client.get(_url("presumido_parametros", empresa=empresa_presumida.pk))
    assert resposta.status_code == 200
    html = _html(resposta)
    # Sem linha gravada, a empresa nasce com o padrão do escritório: três quotas, sem padrão.
    assert "padrão do escritório" in html
    assert "Três quotas" in html
    assert "Sem padrão" in html
    assert "Forma de recolhimento padrão" in html
    assert "Padrão de combustível" in html


def test_tela_de_parametros_e_acessivel(client, empresa_presumida, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = _html(client.get(_url("presumido_parametros", empresa=empresa_presumida.pk)))
    assert_moldura_acessivel(html)
    assert not _ids_referenciados_existem(html), _ids_referenciados_existem(html)


def test_gravar_parametros_pela_tela_grava_e_trilha_o_antes_e_o_depois(
    client, empresa_presumida, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("presumido_parametros_gravar", empresa_presumida.pk),
        {"forma_recolhimento": "quota_unica", "padrao_combustivel": "posto"},
    )
    assert resposta.status_code == 302
    assert servico.parametros_da_empresa(empresa_presumida) == servico.ParametrosDaEmpresa(
        "quota_unica", "posto", True
    )
    registro = RegistroAuditoria.objects.get(acao="presumido.parametros_definidos")
    assert registro.detalhes["antes"] == {
        "forma_recolhimento": "tres_quotas",
        "padrao_combustivel": "",
    }
    assert registro.detalhes["depois"] == {
        "forma_recolhimento": "quota_unica",
        "padrao_combustivel": "posto",
    }
    html = _html(client.get(_url("presumido_parametros", empresa=empresa_presumida.pk)))
    assert "parâmetros gravados desta empresa" in html
    assert "Quota única" in html
    assert "Posto de combustível" in html


def test_parametro_fora_do_catalogo_e_recusado_campo_a_campo(
    client, empresa_presumida, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("presumido_parametros_gravar", empresa_presumida.pk),
        {"forma_recolhimento": "mensal", "padrao_combustivel": "posto"},
    )
    assert resposta.status_code == 400
    html = _html(resposta)
    # Erro em linguagem de escritório, no campo que causou — nunca o código do banco.
    assert "Forma de recolhimento: escolha quota única, duas quotas ou três quotas." in html
    assert 'id="erro_forma_recolhimento"' in html
    assert servico.parametros_da_empresa(empresa_presumida).definido is False
    assert not ParametrosPresumidoEmpresa.objects.filter(empresa=empresa_presumida).exists()


def test_parametro_de_combustivel_fora_do_catalogo_e_recusado_no_campo(
    client, empresa_presumida, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("presumido_parametros_gravar", empresa_presumida.pk),
        {"forma_recolhimento": "tres_quotas", "padrao_combustivel": "loja"},
    )
    assert resposta.status_code == 400
    html = _html(resposta)
    assert (
        "Padrão de combustível: escolha posto, TRR ou distribuidora, ou deixe sem padrão." in html
    )
    assert 'id="erro_padrao_combustivel"' in html
    assert servico.parametros_da_empresa(empresa_presumida).definido is False


# ---------------------------------------------------------------------------
# 2. Feriados locais (item 2): avisos do serviço, cadastro com fonte, edição e exclusão
# ---------------------------------------------------------------------------


def test_feriados_da_praca_mostram_os_avisos_do_servico(client, empresa_palmas, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(_url("presumido_feriados", empresa=empresa_palmas.pk))
    assert resposta.status_code == 200
    html = _html(resposta)
    assert "Praça de Palmas (TO)" in html
    # Os dois níveis de aviso, com os TEXTOS do serviço — e a data normativa, não mudada.
    assert AVISO_BANCARIO_PALMAS in html
    assert AVISO_ANTECIPAR in html
    assert AVISO_CONFIRMAR in html
    assert "19/03" in html and "São José" in html
    assert calc.AVISO_LOCAL_SEM_FONTE_BANCARIA in html
    # A data normativa nunca muda na tela: o feriado local só avisa.
    assert "nunca muda a data de vencimento" in html


def test_tela_de_feriados_e_acessivel(client, empresa_palmas, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas.pk)))
    assert_moldura_acessivel(html)
    assert not _ids_referenciados_existem(html), _ids_referenciados_existem(html)


def test_cadastrar_feriado_pela_tela_exige_a_fonte(client, empresa_palmas, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("presumido_feriado_novo", empresa_palmas.pk),
        {
            "abrangencia": "municipio",
            "dia": "2",
            "mes": "1",
            "descricao": "Feriado sintético sem lei",
            "fundamento": "",
            "data_leitura": "09/10/2026",
            "fonte_bancaria": "",
            "vigencia_inicio": "01/01/2026",
            "vigencia_fim": "",
        },
    )
    assert resposta.status_code == 400
    html = _html(resposta)
    assert "a fonte é obrigatória" in html
    assert 'id="erro_fundamento"' in html
    assert not FeriadoLocal.objects.filter(descricao="Feriado sintético sem lei").exists()


def test_cadastrar_feriado_pela_tela_grava_com_fonte_e_leitura(
    client, empresa_palmas, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("presumido_feriado_novo", empresa_palmas.pk),
        {
            "abrangencia": "municipio",
            "dia": "2",
            "mes": "1",
            "descricao": "Feriado sintético de Palmas",
            "fundamento": "Lei municipal sintética nº 1/2026",
            "data_leitura": "09/10/2026",
            "fonte_bancaria": "Febraban (teste sintético)",
            "vigencia_inicio": "01/01/2026",
            "vigencia_fim": "",
        },
    )
    assert resposta.status_code == 302
    feriado = FeriadoLocal.objects.get(descricao="Feriado sintético de Palmas")
    assert (feriado.uf, feriado.municipio, feriado.esfera) == ("TO", "PALMAS", "municipal")
    assert (feriado.mes, feriado.dia) == (1, 2)
    assert feriado.fundamento == "Lei municipal sintética nº 1/2026"
    assert feriado.data_leitura == date(2026, 10, 9)
    # A trilha registra o ato com antes e depois (AGENTS.md §11).
    registro = RegistroAuditoria.objects.get(acao="presumido.feriado_local_cadastrado")
    assert registro.detalhes["depois"]["data"] == "02/01"
    html = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas.pk)))
    assert "Feriado sintético de Palmas" in html
    assert AVISO_BANCARIO_PALMAS in html  # com fonte bancária: o fechamento da praça é confirmado


def test_alterar_feriado_pela_tela_edita_sem_mudar_a_data_normativa(
    client, empresa_palmas, usuario_gestor_a, escritorio_a
):
    client.force_login(usuario_gestor_a)
    # DE-106: a edição é da linha DO ESCRITÓRIO (a da base recusa). Cadastra a linha e a altera.
    assert (
        client.post(
            _url("presumido_feriado_novo", empresa_palmas.pk),
            {
                "abrangencia": "municipio",
                "dia": "7",
                "mes": "9",
                "descricao": "Feriado sintético de setembro",
                "fundamento": "Lei municipal sintética nº 3/2026",
                "data_leitura": "09/10/2026",
                "fonte_bancaria": "Febraban (teste sintético)",
                "vigencia_inicio": "01/01/2026",
                "vigencia_fim": "",
            },
        ).status_code
        == 302
    )
    feriado = FeriadoLocal.objects.get(descricao="Feriado sintético de setembro")
    assert feriado.escritorio == escritorio_a  # nasce escopada ao escritório que agiu
    resposta = client.post(
        _url("presumido_feriado_editar", empresa_palmas.pk, feriado.pk),
        {
            "abrangencia": "municipio",
            "dia": "7",
            "mes": "9",
            "descricao": "Feriado sintético de setembro",
            "fundamento": "Lei municipal sintética nº 3/2026 (conferida)",
            "data_leitura": "10/10/2026",
            "fonte_bancaria": "",
            "vigencia_inicio": "01/01/2026",
            "vigencia_fim": "",
        },
    )
    assert resposta.status_code == 302
    feriado.refresh_from_db()
    # A data normativa NÃO muda; o que mudou foi a fonte, e com ela o aviso (mais fraco agora).
    assert (feriado.mes, feriado.dia) == (9, 7)
    assert feriado.fundamento == "Lei municipal sintética nº 3/2026 (conferida)"
    assert feriado.fonte_bancaria == ""
    html = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas.pk)))
    assert "07/09" in html
    linha = _linha_que_contem(html, "Feriado sintético de setembro")
    assert AVISO_CONFIRMAR in linha
    assert AVISO_BANCARIO_PALMAS not in linha


def test_excluir_feriado_pela_tela_com_confirmacao(client, empresa_palmas, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        _url("presumido_feriado_novo", empresa_palmas.pk),
        {
            "abrangencia": "municipio",
            "dia": "3",
            "mes": "1",
            "descricao": "Feriado sintético a excluir",
            "fundamento": "Lei sintética nº 2/2026",
            "data_leitura": "09/10/2026",
            "fonte_bancaria": "",
            "vigencia_inicio": "01/01/2026",
            "vigencia_fim": "",
        },
    )
    assert resposta.status_code == 302
    feriado = FeriadoLocal.objects.get(descricao="Feriado sintético a excluir")
    confirmacao = client.get(_url("presumido_feriado_excluir", empresa_palmas.pk, feriado.pk))
    assert confirmacao.status_code == 200
    html = _html(confirmacao)
    # Ação sensível: `.botao--perigoso` com rótulo que nomeia o alvo (direção de arte §8.4).
    assert 'class="botao botao--perigoso"' in html
    assert "Excluir feriado de 03/01 — Feriado sintético a excluir" in html
    assert (
        client.post(
            _url("presumido_feriado_excluir", empresa_palmas.pk, feriado.pk), {}
        ).status_code
        == 302
    )
    assert not FeriadoLocal.objects.filter(pk=feriado.pk).exists()
    assert RegistroAuditoria.objects.filter(acao="presumido.feriado_local_excluido").exists()


def test_feriado_com_excecao_nao_se_exclui_e_manda_excluir_a_excecao(
    client, empresa_palmas, usuario_gestor_a, escritorio_a
):
    client.force_login(usuario_gestor_a)
    # DE-106: a exclusão é da linha DO ESCRITÓRIO (a da base recusa — ver o teste do escopo). A
    # linha dela com exceção do escritório segue sem se excluir antes de a exceção sair.
    client.post(
        _url("presumido_feriado_novo", empresa_palmas.pk),
        {
            "abrangencia": "municipio",
            "dia": "7",
            "mes": "9",
            "descricao": "Feriado sintético com exceção",
            "fundamento": "Lei municipal sintética nº 4/2026",
            "data_leitura": "09/10/2026",
            "fonte_bancaria": "",
            "vigencia_inicio": "01/01/2026",
            "vigencia_fim": "",
        },
    )
    feriado = FeriadoLocal.objects.get(descricao="Feriado sintético com exceção")
    assert (
        client.post(
            _url("presumido_feriado_excecao_nova", empresa_palmas.pk, feriado.pk),
            {
                "ano": "2027",
                "data_observada": "08/09/2027",
                "fundamento": "Decreto sintético nº 2/2027",
                "data_leitura": "09/10/2026",
                "fonte_bancaria": "",
            },
        ).status_code
        == 302
    )
    resposta = client.post(_url("presumido_feriado_excluir", empresa_palmas.pk, feriado.pk), {})
    assert resposta.status_code == 409
    html = _html(resposta)
    assert "exclua cada exceção antes de excluir" in html
    assert FeriadoLocal.objects.filter(pk=feriado.pk).exists()
    assert ExcecaoFeriadoLocal.objects.filter(feriado=feriado).exists()


def test_cadastrar_excecao_por_ano_pela_tela_move_o_aviso_e_nao_a_data_normativa(
    client, empresa_palmas, usuario_gestor_a, escritorio_a
):
    client.force_login(usuario_gestor_a)
    feriado = FeriadoLocal.objects.get(uf="TO", municipio="PALMAS", mes=3, dia=19)
    resposta = client.post(
        _url("presumido_feriado_excecao_nova", empresa_palmas.pk, feriado.pk),
        {
            "ano": "2027",
            "data_observada": "22/03/2027",
            "fundamento": "Decreto sintético nº 1/2027",
            "data_leitura": "09/10/2026",
            "fonte_bancaria": "",
        },
    )
    assert resposta.status_code == 302
    excecao = ExcecaoFeriadoLocal.objects.get(feriado=feriado, ano=2027)
    assert excecao.data_observada == date(2027, 3, 22)
    # DE-106: a exceção nasce escopada ao escritório que agiu (a base continua como a carga).
    assert excecao.escritorio == escritorio_a
    feriado.refresh_from_db()
    # A data normativa do feriado não muda: a exceção registra a data OBSERVADA daquele ano.
    assert (feriado.mes, feriado.dia) == (3, 19)
    html = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas.pk)))
    assert "2027: observado em 22/03/2027" in html


def test_excluir_excecao_pela_tela_com_confirmacao(client, empresa_palmas, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    feriado = FeriadoLocal.objects.get(uf="TO", municipio="PALMAS", mes=10, dia=5)
    # DE-106: se exclui a exceção DO ESCRITÓRIO (a da base é somente leitura — ver o teste do
    # escopo). Cadastra a exceção dele neste feriado carregado e a exclui.
    assert (
        client.post(
            _url("presumido_feriado_excecao_nova", empresa_palmas.pk, feriado.pk),
            {
                "ano": "2027",
                "data_observada": "07/10/2027",
                "fundamento": "Decreto sintético nº 3/2027",
                "data_leitura": "09/10/2026",
                "fonte_bancaria": "",
            },
        ).status_code
        == 302
    )
    excecao = feriado.excecoes.get(ano=2027)
    confirmacao = client.get(
        _url("presumido_feriado_excecao_excluir", empresa_palmas.pk, feriado.pk, excecao.pk)
    )
    assert confirmacao.status_code == 200
    html = _html(confirmacao)
    assert 'class="botao botao--perigoso"' in html
    assert "Excluir exceção de 2027 do feriado de 05/10" in html
    assert (
        client.post(
            _url("presumido_feriado_excecao_excluir", empresa_palmas.pk, feriado.pk, excecao.pk), {}
        ).status_code
        == 302
    )
    assert not ExcecaoFeriadoLocal.objects.filter(pk=excecao.pk).exists()
    # O feriado não muda.
    feriado.refresh_from_db()
    assert (feriado.mes, feriado.dia) == (10, 5)


# ---------------------------------------------------------------------------
# 3. Encerrar medida judicial (item 7): rótulo que nomeia o alvo, histórico e revogação
# ---------------------------------------------------------------------------


def _medida(empresa, usuario, **extra):
    dados = {
        "tributo": "irpj",
        "ano_inicial": 2026,
        "trimestre_inicial": 1,
        "ano_final": None,
        "trimestre_final": None,
        "numero_processo": "PROCESSO-SINTETICO-B2",
        "orgao": "Juízo sintético",
        "data_decisao": "2026-01-15",
        "deposito_judicial": False,
        "suporte": "Decisão sintética",
    }
    dados.update(extra)
    return servico.cadastrar_medida(empresa, dados, usuario)


def test_encerrar_medida_pela_tela_nao_apaga_o_historico(
    client, monkeypatch, empresa_presumida, usuario_gestor_a
):
    # O alvo nomeado na ação de linha é o trimestre corrente: relógio fixo em 2026/T3.
    monkeypatch.setattr(views_web, "_competencia_padrao", lambda: (2026, 9))
    client.force_login(usuario_gestor_a)
    medida = _medida(empresa_presumida, usuario_gestor_a)
    antes = (
        medida.ativa,
        medida.ano_final,
        medida.trimestre_final,
        medida.numero_processo,
        medida.data_decisao,
    )

    lista = _html(client.get(_url("presumido_medidas", empresa=empresa_presumida.pk)))
    # Ação de linha nomeia o alvo: "Encerrar medida no 3º trimestre de 2026", nunca "Encerrar".
    assert "Encerrar medida no 3º trimestre de 2026" in lista

    tela = client.get(
        _url("presumido_medida_encerrar", empresa_presumida.pk, medida.pk, ano=2026, trimestre=3)
    )
    assert tela.status_code == 200
    html = _html(tela)
    assert "anteriores continuam com a medida" in html
    assert 'class="botao botao--perigoso"' in html
    assert "Encerrar medida judicial" in html

    resposta = client.post(
        _url("presumido_medida_encerrar", empresa_presumida.pk, medida.pk),
        {"ano": "2026", "trimestre": "3", "motivo": "decisão sintética que encerrou a suspensão"},
    )
    assert resposta.status_code == 302

    # O histórico não é apagado: a medida continua lá, com os mesmos dados.
    medida.refresh_from_db()
    assert (
        medida.ativa,
        medida.ano_final,
        medida.trimestre_final,
        medida.numero_processo,
        medida.data_decisao,
    ) == antes
    encerramento = EncerramentoMedidaJudicialLC224.objects.get(medida=medida)
    assert (encerramento.ano, encerramento.trimestre) == (2026, 3)
    assert encerramento.motivo == "decisão sintética que encerrou a suspensão"

    # A trilha mostra o encerramento, e a lista mostra até onde a medida vale.
    registro = RegistroAuditoria.objects.get(acao="presumido.medida_encerrada")
    assert registro.detalhes["depois"] == {"fim_efetivo": "2026/T3"}
    html_depois = _html(client.get(_url("presumido_medidas", empresa=empresa_presumida.pk)))
    assert "encerrada a partir do 3º trimestre de 2026" in html_depois

    # A revogação continua funcionando (outro ato, com outro efeito).
    assert (
        client.post(
            _url("presumido_medida_revogar", empresa_presumida.pk, medida.pk),
            {"motivo": "cassada depois do encerramento"},
        ).status_code
        == 302
    )
    medida.refresh_from_db()
    assert medida.ativa is False


def test_encerrar_medida_com_erro_mostra_a_recusa_e_nada_grava(
    client, empresa_presumida, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    medida = _medida(empresa_presumida, usuario_gestor_a, ano_inicial=2026, trimestre_inicial=2)
    resposta = client.post(
        _url("presumido_medida_encerrar", empresa_presumida.pk, medida.pk),
        {"ano": "2026", "trimestre": "1", "motivo": "antes do início"},
    )
    # O serviço recusa encerramento anterior ao início da medida: a tela mostra a recusa dele.
    assert resposta.status_code == 400
    assert "anterior ao início" in _html(resposta)
    invalido = client.post(
        _url("presumido_medida_encerrar", empresa_presumida.pk, medida.pk),
        {"ano": "2026", "trimestre": "9", "motivo": "x"},
    )
    assert invalido.status_code == 400
    assert "Trimestre inválido: use 1, 2, 3 ou 4." in _html(invalido)
    assert not EncerramentoMedidaJudicialLC224.objects.filter(medida=medida).exists()


# ---------------------------------------------------------------------------
# 4. Pendências de cadastro do mês (item 8): a empresa certa, e só a do escritório
# ---------------------------------------------------------------------------


def test_pendencias_do_mes_listam_a_empresa_certa_e_so_a_do_escritorio(
    client, escritorio_a, escritorio_b, empresa_a, empresa_a2, empresa_b, usuario_gestor_a, gestor_b
):
    # empresa_a: Lucro Presumido SEM atividade padrão → pendência. empresa_a2: com atividade →
    # sem pendência. empresa_b: de OUTRO escritório, também com pendência → nunca aparece aqui.
    for empresa in (empresa_a, empresa_a2, empresa_b):
        HistoricoRegimeTributario.objects.create(
            empresa=empresa,
            regime=RegimeTributario.LUCRO_PRESUMIDO,
            vigencia_inicio=date(2026, 1, 1),
        )
    servico.criar_atividade(
        empresa_a2,
        {"atividade": COMERCIO, "inicio": date(2026, 1, 1), "padrao": True},
        usuario_gestor_a,
    )

    client.force_login(usuario_gestor_a)
    resposta = client.get(_url("presumido_pendencias", ano=2026, mes=3))
    assert resposta.status_code == 200
    html = _html(resposta)
    assert "Prestadora A Ltda" in html  # a empresa certa
    assert "Sem atividade de presunção padrão vigente em 03/2026" in html
    # Com link para cadastrar (a ação que resolve a pendência).
    assert reverse("fiscal_web:presumido_atividade_nova", args=[empresa_a.pk]) in html
    assert "Tomadora A2 Ltda" not in html  # sem pendência, não lista
    assert "Empresa B Ltda" not in html  # de outro escritório, nunca

    # E a lista do OUTRO escritório é a dele, sem vazar a nossa.
    client.force_login(gestor_b)
    html_b = _html(client.get(_url("presumido_pendencias", ano=2026, mes=3)))
    assert "Empresa B Ltda" in html_b
    assert "Prestadora A Ltda" not in html_b


def test_pendencias_com_mes_invalido_e_400(client, empresa_presumida, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(_url("presumido_pendencias", ano=2026, mes=13))
    assert resposta.status_code == 400
    assert "Mês inválido: use 1 a 12." in _html(resposta)


def test_apuracao_mostra_a_pendencia_do_mes_com_link_para_cadastrar(
    client, empresa_presumida, usuario_gestor_a
):
    # Sem atividade padrão vigente em fevereiro: a pendência do mês aparece na apuração, com o link.
    atividade = servico.listar_atividades(empresa_presumida)[0]
    servico.encerrar_atividade(empresa_presumida, atividade.pk, "2026-01-31", usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    html = _html(
        client.get(_url("presumido_apuracao", empresa=empresa_presumida.pk, ano=2026, trimestre=1))
    )
    assert "Pendências de cadastro do mês" in html
    assert "Sem atividade de presunção padrão vigente em 02/2026" in html
    assert reverse("fiscal_web:presumido_atividade_nova", args=[empresa_presumida.pk]) in html


def test_apuracao_sem_pendencia_nao_mostra_o_bloco(client, empresa_presumida, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = _html(
        client.get(_url("presumido_apuracao", empresa=empresa_presumida.pk, ano=2026, trimestre=1))
    )
    assert "Pendências de cadastro do mês" not in html


# ---------------------------------------------------------------------------
# 5. CSLL a classificar (item 3): o aviso aparece onde a retenção é exibida e confirmada
# ---------------------------------------------------------------------------


def test_csll_a_classificar_mostra_o_aviso_na_lista_e_na_confirmacao(
    client, empresa_presumida, escritorio_a, usuario_gestor_a
):
    # vRetCSLL de 10,00 sobre base de 1.000,00 = 1%: o tomador reteve só a CSLL → "a classificar".
    nota = nota_efetivada(
        escritorio_a,
        empresa_presumida,
        usuario_gestor_a,
        sufixo=891,
        v_serv="1000.00",
        d_compet="2026-01-10",
        ret_csll="10.00",
        tp_ret="3",
    )
    client.force_login(usuario_gestor_a)
    lista = _html(
        client.get(_url("presumido_retencoes", empresa=empresa_presumida.pk, ano=2026, trimestre=1))
    )
    assert "a classificar" in lista
    assert "o tomador reteve só a CSLL?" in lista
    assert "Nenhuma dedução acontece sem a sua confirmação" in lista

    confirmacao = _html(
        client.get(
            _url(
                "presumido_retencao_confirmar",
                empresa_presumida.pk,
                nota.pk,
                ano=2026,
                trimestre=1,
            )
        )
    )
    assert "CSLL a classificar:" in confirmacao
    assert "o tomador reteve só a CSLL?" in confirmacao
    assert "Nenhuma dedução acontece sem a sua confirmação" in confirmacao
    # A tela não confirma sozinha: nada de dedução sem o ato do contador.
    assert not ConfirmacaoRetencaoPresumido.objects.exists()


# ---------------------------------------------------------------------------
# 6. Vencimento com antecipação (itens 1 e 2) e a chave morta "calendário a conferir"
# ---------------------------------------------------------------------------


def _apuracao_de_2029_com_quotas(empresa, usuario):
    """1.000.000,00 de comércio no 1º trimestre de 2029: IRPJ = 8% × 15% = 12.000,00, acima de
    3.000,00 — o plano de três quotas existe, com vencimentos escritos à mão: 30/04, 30/05 (último
    dia de maio é quinta, Corpus Christi, então antecipa de 31/05) e 29/06/2029."""
    servico.definir_criterio(empresa, 2029, "competencia", usuario)
    servico.criar_receita(
        empresa,
        2029,
        1,
        {
            "tipo": "presuncao",
            "valor": "1000000.00",
            "descricao": "Receita sintética de 2029",
            "suporte": "Documento sintético",
            "atividade_id": servico.listar_atividades(empresa)[0].pk,
        },
        usuario,
    )
    servico.declarar_sem_receitas_integrais(empresa, 2029, 1, usuario)


def test_aviso_de_antecipacao_aparece_quando_cabe_e_nao_aparece_quando_nao_cabe(
    client, empresa_palmas, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    _apuracao_de_2029_com_quotas(empresa_palmas, usuario_gestor_a)

    # Feriado SINTÉTICO da praça, com a lista bancária confirmada, no dia da 1ª quota (30/04/2029).
    feriado = FeriadoLocal.objects.create(
        uf="TO",
        municipio="PALMAS",
        esfera="municipal",
        mes=4,
        dia=30,
        descricao="Feriado sintético da praça",
        fundamento="Lei sintética nº 9/2029",
        data_leitura=date(2026, 10, 9),
        fonte_bancaria="Febraban (teste sintético)",
        vigencia_inicio=date(2029, 1, 1),
    )
    url = _url("presumido_apuracao", empresa=empresa_palmas.pk, ano=2029, trimestre=1)
    html = _html(client.get(url))
    # O vencimento que cai em dia sem expediente bancário na praça avisa que deve antecipar…
    assert AVISO_ANTECIPAR in html
    assert AVISO_BANCARIO_PALMAS in html
    # …e a antecipação nacional explica o recuo, com a data civil que ficou para trás.
    assert "antecipado: sem expediente bancário (era 31/05/2029)" in html

    # Sem o feriado, o aviso de antecipação não cabe e não aparece.
    feriado.delete()
    html_sem = _html(client.get(url))
    assert AVISO_ANTECIPAR not in html_sem
    assert AVISO_BANCARIO_PALMAS not in html_sem
    assert "antecipado: sem expediente bancário (era 31/05/2029)" in html_sem


def test_o_aviso_de_calendario_a_conferir_nao_aparece_em_nenhuma_resposta(
    client, monkeypatch, empresa_palmas, escritorio_a, usuario_gestor_a
):
    monkeypatch.setattr(views_web, "_competencia_padrao", lambda: (2026, 12))
    client.force_login(usuario_gestor_a)
    _apuracao_de_2029_com_quotas(empresa_palmas, usuario_gestor_a)
    medida = _medida(empresa_palmas, usuario_gestor_a)
    urls = [
        _url("presumido_apuracao", empresa=empresa_palmas.pk, ano=2029, trimestre=1),
        _url("presumido_retencoes", empresa=empresa_palmas.pk, ano=2029, trimestre=1),
        _url("presumido_receitas", empresa=empresa_palmas.pk, ano=2029, trimestre=1),
        _url("presumido_medidas", empresa=empresa_palmas.pk),
        _url("presumido_limite", empresa=empresa_palmas.pk, ano=2029, tributo="irpj"),
        _url("presumido_parametros", empresa=empresa_palmas.pk),
        _url("presumido_feriados", empresa=empresa_palmas.pk),
        _url("presumido_pendencias", ano=2029, mes=1),
        _url("presumido_medida_encerrar", empresa_palmas.pk, medida.pk),
    ]
    for url in urls:
        resposta = client.get(url)
        assert resposta.status_code == 200, url
        assert "calendário a conferir" not in _html(resposta), url


# ---------------------------------------------------------------------------
# 7. Permissão e isolamento das telas novas (critério 9: mutação derruba estes testes)
# ---------------------------------------------------------------------------


def _rotas_de_escrita_novas(empresa, medida, feriado, excecao):
    """(nome, args, query) das telas novas com GET do formulário e POST do ato."""
    return [
        ("presumido_feriado_novo", [empresa.pk], {}),
        ("presumido_feriado_editar", [empresa.pk, feriado.pk], {}),
        ("presumido_feriado_excluir", [empresa.pk, feriado.pk], {}),
        ("presumido_feriado_excecao_excluir", [empresa.pk, feriado.pk, excecao.pk], {}),
        ("presumido_medida_encerrar", [empresa.pk, medida.pk], {"ano": 2026, "trimestre": 2}),
    ]


def _rotas_de_post_novas(empresa, feriado):
    """(nome, args) das telas novas que SÓ aceitam POST (o GET delas é 405 para todo mundo)."""
    return [
        ("presumido_parametros_gravar", [empresa.pk]),
        ("presumido_feriado_excecao_nova", [empresa.pk, feriado.pk]),
    ]


@pytest.fixture
def dados_novos(empresa_palmas, usuario_gestor_a):
    medida = _medida(empresa_palmas, usuario_gestor_a)
    feriado = FeriadoLocal.objects.get(uf="TO", municipio="PALMAS", mes=10, dia=5)
    return {"medida": medida, "feriado": feriado, "excecao": feriado.excecoes.get(ano=2026)}


def _contagem_de_dados(empresa):
    return (
        ParametrosPresumidoEmpresa.objects.filter(empresa=empresa).count(),
        FeriadoLocal.objects.filter(uf="TO").count(),
        ExcecaoFeriadoLocal.objects.count(),
        EncerramentoMedidaJudicialLC224.objects.count(),
    )


def test_cliente_recebe_403_em_todas_as_telas_novas_e_nada_grava(
    client, empresa_palmas, usuario_cliente_a, dados_novos
):
    client.force_login(usuario_cliente_a)
    antes = _contagem_de_dados(empresa_palmas)
    for nome in ("presumido_parametros", "presumido_feriados", "presumido_pendencias"):
        assert client.get(_url(nome, empresa=empresa_palmas.pk)).status_code == 403, nome
    for nome, args, query in _rotas_de_escrita_novas(
        empresa_palmas, dados_novos["medida"], dados_novos["feriado"], dados_novos["excecao"]
    ):
        assert client.get(_url(nome, *args, **query)).status_code == 403, nome
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 403, nome
    for nome, args in _rotas_de_post_novas(empresa_palmas, dados_novos["feriado"]):
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 403, nome
    assert _contagem_de_dados(empresa_palmas) == antes


def test_paralegal_le_e_nao_escreve_nas_telas_novas(client, empresa_palmas, paralegal, dados_novos):
    client.force_login(paralegal)
    antes = _contagem_de_dados(empresa_palmas)
    for nome in ("presumido_parametros", "presumido_feriados", "presumido_pendencias"):
        assert client.get(_url(nome, empresa=empresa_palmas.pk)).status_code == 200, nome
    for nome, args, query in _rotas_de_escrita_novas(
        empresa_palmas, dados_novos["medida"], dados_novos["feriado"], dados_novos["excecao"]
    ):
        assert client.get(_url(nome, *args, **query)).status_code == 403, nome
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 403, nome
    for nome, args in _rotas_de_post_novas(empresa_palmas, dados_novos["feriado"]):
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 403, nome
    assert _contagem_de_dados(empresa_palmas) == antes
    # Quem só consulta vê a ação desabilitada com o motivo, nunca sumindo (§2B).
    html = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas.pk)))
    assert "Seu papel consulta os feriados locais, mas não cadastra, altera nem exclui." in html
    assert 'class="botao botao--perigoso botao--pequeno" disabled' in html


def test_outro_escritorio_recebe_404_nas_telas_novas(client, empresa_palmas, gestor_b, dados_novos):
    client.force_login(gestor_b)
    antes = _contagem_de_dados(empresa_palmas)
    for nome in ("presumido_parametros", "presumido_feriados"):
        assert client.get(_url(nome, empresa=empresa_palmas.pk)).status_code == 404, nome
    for nome, args, query in _rotas_de_escrita_novas(
        empresa_palmas, dados_novos["medida"], dados_novos["feriado"], dados_novos["excecao"]
    ):
        assert client.get(_url(nome, *args, **query)).status_code == 404, nome
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 404, nome
    for nome, args in _rotas_de_post_novas(empresa_palmas, dados_novos["feriado"]):
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 404, nome
    assert _contagem_de_dados(empresa_palmas) == antes


# ---------------------------------------------------------------------------
# 8. Sugestão de natureza com o padrão de combustível da empresa (item 8)
# ---------------------------------------------------------------------------


def test_sugestao_de_natureza_da_tela_usa_o_padrao_de_combustivel_da_empresa(monkeypatch):
    """A linha do item chama `sugerir_natureza_com_padrao` com o padrão da empresa (posto): o NCM é
    de combustível e o CFOP (5949) não decide consumo ou revenda — o padrão decide."""
    chamadas = []
    original = servico_nfe.sugerir_natureza_com_padrao

    def espião(documento, item, padrao_combustivel, tipo=None):
        chamadas.append(padrao_combustivel)
        return original(documento, item, padrao_combustivel, tipo)

    monkeypatch.setattr(views_web.servico_nfe, "sugerir_natureza_com_padrao", espião)
    ncm = next(iter(sorted(servico_nfe.NCM_COMBUSTIVEL)))
    item = SimpleNamespace(
        pk=1,
        n_item=1,
        x_prod="Combustível sintético",
        ncm=ncm,
        cfop="5949",
        csosn="102",
        cst="",
        v_prod=D("10.00"),
        ind_tot="1",
        v_frete=None,
        v_seg=None,
        v_outro=None,
        v_desc=None,
        v_icms_deson=None,
        ind_deduz_deson=None,
    )
    documento = SimpleNamespace(
        fin_nfe="1", id_dest="1", transferencia_entre_estabelecimentos=False
    )
    linha = views_web._linha_do_item_nfe(item, "", documento, "saida", padrao_combustivel="posto")
    assert chamadas == ["posto"]
    assert linha["sugestao"] == NaturezaOperacaoNFe.COMBUSTIVEL
    assert "padrão de combustível" in linha["sugestao_motivo"]


# ---------------------------------------------------------------------------
# 9. Escopo do escritório nos feriados (DE-106, achado A1 da auditoria da DL-084)
# ---------------------------------------------------------------------------


@pytest.fixture
def empresa_palmas_b(empresa_b, gestor_b):
    """Empresa de OUTRO escritório, também com matriz em Palmas: mesma praça, outro escritório."""
    _matriz(empresa_b, "Palmas", "TO")
    return empresa_b


def _avisos_locais(empresa, dia):
    praca, feriados = servico._feriados_locais_da_praca(empresa)
    return calc.avisos_de_feriado_local(dia, feriados, praca) if praca else ()


def test_gestor_de_outro_escritorio_nao_edita_nem_exclui_a_linha_da_base_de_palmas(
    client, empresa_palmas_b, gestor_b
):
    """O coração do achado A1: a linha carregada (lei e fonte bancária) que as empresas do
    escritório A usam não se toca do escritório B — recusa nomeada, com a linguagem de escritório,
    e o dado intocado. A UI mostra a ação desabilitada com o motivo (§2B da direção de arte)."""
    base = FeriadoLocal.objects.get(uf="TO", municipio="PALMAS", mes=3, dia=19)
    antes = (base.fundamento, base.data_leitura, base.fonte_bancaria, base.vigencia_inicio)
    client.force_login(gestor_b)
    for nome, args in (
        ("presumido_feriado_editar", [empresa_palmas_b.pk, base.pk]),
        ("presumido_feriado_excluir", [empresa_palmas_b.pk, base.pk]),
    ):
        for resposta in (client.get(_url(nome, *args)), client.post(_url(nome, *args), {})):
            assert resposta.status_code == 409, nome
            html = _html(resposta)
            assert "linha da base (lei e fonte da carga)" in html
            assert "cadastre a sua para a sua praça" in html
    base.refresh_from_db()
    assert (base.fundamento, base.data_leitura, base.fonte_bancaria, base.vigencia_inicio) == antes

    # A exceção da base também não se exclui (é o decreto carregado).
    base_outubro = FeriadoLocal.objects.get(uf="TO", municipio="PALMAS", mes=10, dia=5)
    excecao_base = base_outubro.excecoes.get(ano=2026)
    endereco = _url(
        "presumido_feriado_excecao_excluir", empresa_palmas_b.pk, base_outubro.pk, excecao_base.pk
    )
    for resposta in (client.get(endereco), client.post(endereco, {})):
        assert resposta.status_code == 409
        assert "linha da base (lei e fonte da carga)" in _html(resposta)
    assert ExcecaoFeriadoLocal.objects.filter(pk=excecao_base.pk).exists()

    # E a UI mostra o motivo com a ação desabilitada, nunca sumindo (§2B).
    html = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas_b.pk)))
    assert "Linha da base (carga/lei)" in html
    assert "cadastre a sua para a sua praça" in html
    assert 'class="botao botao--perigoso botao--pequeno" disabled' in html


def test_a_linha_que_o_escritorio_b_cria_so_aparece_e_afeta_as_empresas_dele(
    client, empresa_palmas_b, gestor_b, empresa_palmas, usuario_gestor_a, escritorio_b
):
    client.force_login(gestor_b)
    assert (
        client.post(
            _url("presumido_feriado_novo", empresa_palmas_b.pk),
            {
                "abrangencia": "municipio",
                "dia": "2",
                "mes": "1",
                "descricao": "Feriado sintético do escritório B",
                "fundamento": "Lei municipal sintética nº B/2026",
                "data_leitura": "09/10/2026",
                "fonte_bancaria": "Febraban (teste sintético)",
                "vigencia_inicio": "01/01/2026",
                "vigencia_fim": "",
            },
        ).status_code
        == 302
    )
    linha = FeriadoLocal.objects.get(descricao="Feriado sintético do escritório B")
    assert linha.escritorio == escritorio_b  # nasce escopada ao escritório que agiu

    # Só aparece para as empresas do escritório B.
    html_b = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas_b.pk)))
    assert "Feriado sintético do escritório B" in html_b
    client.force_login(usuario_gestor_a)
    html_a = _html(client.get(_url("presumido_feriados", empresa=empresa_palmas.pk)))
    assert "Feriado sintético do escritório B" not in html_a

    # E só afeta as empresas dele: o aviso de 02/01 sai para B e não para A.
    assert _avisos_locais(empresa_palmas_b, date(2027, 1, 2)) == (
        AVISO_BANCARIO_PALMAS,
        AVISO_ANTECIPAR,
    )
    assert _avisos_locais(empresa_palmas, date(2027, 1, 2)) == ()


def test_os_avisos_do_escritorio_a_nao_mudam_quando_b_cadastra_feriado_e_excecao_na_mesma_praca(
    client, empresa_palmas_b, gestor_b, empresa_palmas
):
    """O coração do achado A1: B cadastra feriado e exceção na MESMA praça e nenhum aviso das
    empresas de A muda. Para as empresas de B, a linha do escritório substitui a da base no mesmo
    dia e a exceção do escritório substitui a da base no mesmo ano — só para as dele."""
    # Como as empresas de A veem hoje: 19/03 com a lista bancária, 09/10/2026 observado, 05/10 mudo.
    assert _avisos_locais(empresa_palmas, date(2027, 3, 19)) == (
        AVISO_BANCARIO_PALMAS,
        AVISO_ANTECIPAR,
    )
    assert _avisos_locais(empresa_palmas, date(2026, 10, 9)) == (
        AVISO_BANCARIO_PALMAS,
        AVISO_ANTECIPAR,
    )
    assert _avisos_locais(empresa_palmas, date(2026, 10, 5)) == ()

    client.force_login(gestor_b)
    # B cadastra o PRÓPRIO feriado de 19/03 (sem fonte bancária) e o PRÓPRIO 05/10 com exceção de
    # 2026 observada em 08/10 — ambos escopados ao escritório dele.
    assert (
        client.post(
            _url("presumido_feriado_novo", empresa_palmas_b.pk),
            {
                "abrangencia": "municipio",
                "dia": "19",
                "mes": "3",
                "descricao": "São José, feriado do escritório B",
                "fundamento": "Lei municipal sintética nº C/2026",
                "data_leitura": "09/10/2026",
                "fonte_bancaria": "",
                "vigencia_inicio": "01/01/2026",
                "vigencia_fim": "",
            },
        ).status_code
        == 302
    )
    assert (
        client.post(
            _url("presumido_feriado_novo", empresa_palmas_b.pk),
            {
                "abrangencia": "municipio",
                "dia": "5",
                "mes": "10",
                "descricao": "Criação do Estado, do escritório B",
                "fundamento": "Lei estadual sintética nº D/2026",
                "data_leitura": "09/10/2026",
                "fonte_bancaria": "Febraban (teste sintético)",
                "vigencia_inicio": "01/01/2026",
                "vigencia_fim": "",
            },
        ).status_code
        == 302
    )
    linha_b = FeriadoLocal.objects.get(descricao="Criação do Estado, do escritório B")
    assert (
        client.post(
            _url("presumido_feriado_excecao_nova", empresa_palmas_b.pk, linha_b.pk),
            {
                "ano": "2026",
                "data_observada": "08/10/2026",
                "fundamento": "Decreto sintético nº B/2026",
                "data_leitura": "09/10/2026",
                "fonte_bancaria": "Febraban (teste sintético)",
            },
        ).status_code
        == 302
    )

    # Para as empresas de B: a linha dele substitui a da base no mesmo dia (19/03 sem fonte) e a
    # exceção dele substitui a da base no mesmo ano (08/10 avisa; 09/10 e 05/10 não).
    assert _avisos_locais(empresa_palmas_b, date(2027, 3, 19)) == (AVISO_CONFIRMAR,)
    assert _avisos_locais(empresa_palmas_b, date(2026, 10, 8)) == (
        AVISO_BANCARIO_PALMAS,
        AVISO_ANTECIPAR,
    )
    assert _avisos_locais(empresa_palmas_b, date(2026, 10, 9)) == ()
    assert _avisos_locais(empresa_palmas_b, date(2026, 10, 5)) == ()

    # E para as empresas de A, NADA mudou.
    assert _avisos_locais(empresa_palmas, date(2027, 3, 19)) == (
        AVISO_BANCARIO_PALMAS,
        AVISO_ANTECIPAR,
    )
    assert _avisos_locais(empresa_palmas, date(2026, 10, 9)) == (
        AVISO_BANCARIO_PALMAS,
        AVISO_ANTECIPAR,
    )
    assert _avisos_locais(empresa_palmas, date(2026, 10, 5)) == ()
    assert _avisos_locais(empresa_palmas, date(2026, 10, 8)) == ()
