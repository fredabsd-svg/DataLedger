"""DL-075 (frente B) — telas do pré-DAS, das atividades e da folha para o fator r.

Telas: pré-DAS do mês (apurado e recusado), atividades da empresa (listar, cadastrar, alterar,
encerrar) e folha para o fator r (listar com o FS12 do mês, lançar, confirmar, estornar). A regra
é a da frente A (`apps.fiscal.pre_das`, `apps.fiscal.folha_fator_r`): aqui se prova que a TELA
mostra o que o serviço calcula, recusa e não grava o que o serviço recusa, e que a autorização
e o isolamento são verificados no servidor.

- Dados 100% sintéticos (test_dl075_suporte e test_dl074_suporte). Nenhum dado real.
- O caso de referência é o EXEMPLO 2 do Manual do PGDAS-D (8.080,00), o mesmo de
  test_dl075_referencia: os números estão escritos à mão aqui.
- Conferência (classe 1): o pré-DAS diz que não gera nem transmite nada.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
    NOMES_DE_TELA_FISCAL_FORA_DA_CONTABILIDADE,
    assert_moldura_acessivel,
)
from apps.fiscal import folha_fator_r as servico_folha
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import receita as servico_receita
from apps.fiscal import views_web
from apps.fiscal.models import (
    AtividadeEmpresa,
    EnquadramentoAtividade,
    EstadoFolhaFatorR,
    FolhaFatorR,
)
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    folha_confirmada,
    janela_de_receitas,
    receber_e_confirmar_mes,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fábrica e URLs
# ---------------------------------------------------------------------------


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _logar(client, usuario):
    client.force_login(usuario)
    return client


@pytest.fixture
def paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl075-telas")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-dl075-telas")


@pytest.fixture
def empresa(empresa_a):
    """Simples desde 2018, abertura em 2015, início de uso em 2025/01 (sem restrição)."""
    return cenario_simples(empresa_a)


def _url_pre_das():
    return reverse("fiscal_web:pre_das")


def _url_atividades():
    return reverse("fiscal_web:atividades")


def _url_folhas():
    return reverse("fiscal_web:folhas_fator_r")


def _pre_das_de(empresa, ano, mes):
    return {"empresa": empresa.pk, "ano": ano, "mes": mes}


def _url_nova_atividade(empresa):
    return reverse("fiscal_web:atividade_nova", args=[empresa.pk])


def _url_editar_atividade(empresa, atividade):
    return reverse("fiscal_web:atividade_editar", args=[empresa.pk, atividade.pk])


def _url_encerrar_atividade(empresa, atividade):
    return reverse("fiscal_web:atividade_encerrar", args=[empresa.pk, atividade.pk])


def _url_nova_folha(empresa):
    return reverse("fiscal_web:folha_nova", args=[empresa.pk])


def _url_confirmar_folha(empresa, folha):
    return reverse("fiscal_web:folha_confirmar", args=[empresa.pk, folha.pk])


def _url_estornar_folha(empresa, folha):
    return reverse("fiscal_web:folha_estornar", args=[empresa.pk, folha.pk])


def _atividade_valida(**sobrescritas):
    """Dados de um POST válido do cadastro de atividade. Sobrescreva o que o teste muda."""
    dados = {
        "descricao": "Serviço sintético de teste",
        "codigo_subitem": "",
        "enquadramento": EnquadramentoAtividade.ANEXO_III,
        "inicio": "01/01/2018",
        "fim": "",
        "padrao": "1",
    }
    dados.update(sobrescritas)
    return dados


def _folha_valida(**sobrescritas):
    """Dados de um POST válido do lançamento de folha. Sobrescreva o que o teste muda."""
    dados = {
        "ano": "2026",
        "mes": "05",
        "remuneracao_empregados_avulsos": "1.000,00",
        "pro_labore_autonomos": "0,00",
        "decimo_terceiro": "0,00",
        "cpp_recolhida": "0,00",
        "fgts_recolhido": "0,00",
        "documento_suporte": SUPORTE_SINTETICO,
    }
    dados.update(sobrescritas)
    return dados


def _folha_de_lancada(empresa, usuario, ano, mes, remuneracao="1000"):
    """Folha do mês em rascunho, pelo serviço (com trilha)."""
    componentes = {
        "remuneracao_empregados_avulsos": Decimal(remuneracao),
        "pro_labore_autonomos": Decimal("0"),
        "decimo_terceiro": Decimal("0"),
        "cpp_recolhida": Decimal("0"),
        "fgts_recolhido": Decimal("0"),
    }
    return servico_folha.lancar_folha(empresa, ano, mes, componentes, SUPORTE_SINTETICO, usuario)


# ---------------------------------------------------------------------------
# Formatação pt-BR (apresentação; o cálculo não passa por aqui)
# ---------------------------------------------------------------------------


def test_formatacao_pt_br_de_dinheiro_percentual_e_memoria():
    assert views_web._dinheiro_ptbr(Decimal("8080")) == "8.080,00"
    assert views_web._dinheiro_ptbr(Decimal("-1234.5")) == "-1.234,50"
    assert views_web._dinheiro_ptbr(None) == "—"
    # Alíquota efetiva: fração → percentual com 4 casas, como a tela mostra.
    assert views_web._percentual_ptbr(Decimal("0.0808")) == "8,0800%"
    assert views_web._percentual_ptbr(Decimal("0.09972")) == "9,9720%"
    # A memória troca ponto por vírgula só nos NÚMEROS (valor e descrição), nunca no dispositivo.
    assert views_web._texto_da_memoria_em_ptbr("RBT12 até 180000.00") == "RBT12 até 180000,00"
    assert views_web._texto_da_memoria_em_ptbr("LC 123, art. 18, § 1º-A") == (
        "LC 123, art. 18, § 1º-A"
    )


# ---------------------------------------------------------------------------
# Pré-DAS: apurado (EXEMPLO 2) e recusado (cada bloqueio, com o que falta)
# ---------------------------------------------------------------------------


def test_tela_pre_das_apurado_mostra_o_exemplo_2_do_manual(client, empresa, usuario_gestor_a):
    """Manual do PGDAS-D, exemplo 2: RBT12 300.000; receita do mês 100.000; Anexo III, 2ª faixa.

    Esperado (à mão): alíquota efetiva 8,08%; total 8.080,00; IRPJ 323,20; CSLL 282,80;
    Cofins 1.135,24; PIS 246,44; CPP 3.506,72; ISS 2.585,60.
    """
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_pre_das(), _pre_das_de(empresa, 2026, 6))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fiscal/pre_das.html" in [t.name for t in resposta.templates]
    assert "Pré-apuração para conferência contra o PGDAS-D." in html
    assert "não gera nem transmite DAS" in html
    assert "Mercado interno: Anexo III" in html
    assert "8,0800%" in html
    tributos = {
        "IRPJ": "323,20",
        "CSLL": "282,80",
        "Cofins": "1.135,24",
        "PIS/Pasep": "246,44",
        "CPP": "3.506,72",
        "ISS": "2.585,60",
    }
    for rotulo, valor in tributos.items():
        assert re.search(
            rf'<th scope="row">{re.escape(rotulo)}</th>\s*<td class="valor-monetario">'
            rf"{re.escape(valor)}</td>",
            html,
        ), rotulo
    assert re.search(r'Total do pré-DAS</th>\s*<td class="valor-monetario">8\.080,00</td>', html)
    assert "§ 1º-A" in html and "§ 1º-B" in html
    assert_moldura_acessivel(html)


def test_tela_pre_das_recusado_lista_cada_bloqueio_com_o_que_falta(
    client, empresa, usuario_gestor_a
):
    """Sem atividade, sem receita confirmada: a tela lista os dois bloqueios e não calcula."""
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_pre_das(), _pre_das_de(empresa, 2026, 6))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Pré-DAS não calculado em 06/2026" in html
    assert "Não há atividade padrão vigente em 06/2026" in html
    assert "A receita de 06/2026 não está confirmada completa" in html
    assert "RBT12 não apurável" in html
    # Cada bloqueio tem o link de quem resolve, e o que não tem caminho diz o porquê.
    assert reverse("fiscal_web:atividades") in html
    assert reverse("fiscal_web:receita_do_mes") in html
    assert "Total do pré-DAS" not in html
    assert "Valor calculado de 06/2026" not in html
    assert_moldura_acessivel(html)


def test_tela_pre_das_recusado_por_fator_r_e_regime_de_caixa_lista_os_dois(
    client, empresa, usuario_gestor_a
):
    """Fator r exigido sem folha confirmada e opção pelo regime de caixa em 2026: a tela lista
    os dois bloqueios, cada um com o caminho para resolver (ou com o motivo de não haver)."""
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")
    servico_receita.registrar_opcao_regime_caixa(empresa, 2026, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_pre_das(), _pre_das_de(empresa, 2026, 6))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Empresa optante pelo regime de caixa em 2026" in html
    assert "Fator r exigido sem folha confirmada" in html
    assert "Lançar e confirmar a folha" in html
    assert reverse("fiscal_web:folhas_fator_r") in html
    assert "Total do pré-DAS" not in html


def test_pre_das_de_2027_recusa_citando_a_res_190(client, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_pre_das(), _pre_das_de(empresa, 2027, 1))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Res. CGSN 190/2026" in html
    assert "Total do pré-DAS" not in html


def test_tela_pre_das_sem_empresa_pede_a_escolha_e_lista_as_empresas(
    client, empresa, empresa_a2, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_pre_das())

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Escolha uma empresa para ver o pré-DAS do mês." in html
    assert "Prestadora A Ltda" in html and "Tomadora A2 Ltda" in html
    assert_moldura_acessivel(html)


def test_tela_com_empresa_escolhida_nao_lista_as_outras_empresas(
    client, empresa, empresa_a2, usuario_gestor_a
):
    """Direção de arte §8.1: a tela de UMA empresa não repete o nome de outra do escritório."""
    _logar(client, usuario_gestor_a)

    html = client.get(_url_pre_das(), _pre_das_de(empresa, 2026, 6)).content.decode()

    assert empresa.razao_social in html
    assert empresa_a2.razao_social not in html


def test_pre_das_com_competencia_invalida_responde_400(client, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_pre_das(), {"empresa": empresa.pk, "ano": "2026", "mes": "13"})

    assert resposta.status_code == 400
    assert "Competência inválida" in resposta.content.decode()


def test_bloqueio_de_data_de_abertura_nao_inventa_caminho(empresa):
    """Sem data de abertura no CNPJ, a tela diz onde a data fica, sem link para uma tela que
    não existe (não há tela web de edição do cadastro da empresa)."""
    bloqueio = servico_pre_das.Bloqueio(
        "rbt12_recusado",
        "Informe a data de abertura no CNPJ da empresa: sem ela o RBT12 não é apurado.",
        "Res. CGSN 140/2018, art. 22",
    )

    rotulo, url, texto = views_web._acao_do_bloqueio(bloqueio, empresa, 2026, 6)

    assert (rotulo, url) == (None, None)
    assert "data de abertura" in texto


# ---------------------------------------------------------------------------
# Atividades: listar, cadastrar, alterar e encerrar
# ---------------------------------------------------------------------------


def test_tela_atividades_mostra_o_catalogo_com_o_dispositivo(client, empresa, usuario_gestor_a):
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_atividades(), {"empresa": empresa.pk})

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Serviço sintético de teste" in html
    assert "LC 123/2006, art. 18, §§ 5º-B e 5º-F" in html
    assert "em aberto" in html
    assert_moldura_acessivel(html)


def test_tela_atividade_nova_e_acessivel(client, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_nova_atividade(empresa))

    assert resposta.status_code == 200
    assert "fiscal/atividade_form.html" in [t.name for t in resposta.templates]
    assert "Início da vigência" in resposta.content.decode()
    assert_moldura_acessivel(resposta.content.decode())


def test_cadastrar_atividade_pela_tela(client, empresa, usuario_gestor_a):
    """O caminho feliz grava com trilha; cada recusa responde 200 ou 400 e NÃO grava."""
    _logar(client, usuario_gestor_a)

    # Caminho feliz: grava, e a tela volta para a lista.
    feliz = client.post(_url_nova_atividade(empresa), _atividade_valida())
    assert feliz.status_code == 302
    atividade = AtividadeEmpresa.objects.get(empresa=empresa)
    assert atividade.enquadramento == EnquadramentoAtividade.ANEXO_III
    assert atividade.padrao is True
    assert atividade.inicio == date(2018, 1, 1)
    assert atividade.fim is None

    # Enquadramento fora do catálogo: recusa com mensagem, nada gravado.
    fora_do_catalogo = client.post(
        _url_nova_atividade(empresa),
        _atividade_valida(enquadramento="anexo_x", padrao=""),
    )
    assert fora_do_catalogo.status_code == 200
    assert "Escolha o enquadramento da atividade no catálogo." in (
        fora_do_catalogo.content.decode()
    )

    # Data inválida: recusa, nada gravado.
    data_invalida = client.post(
        _url_nova_atividade(empresa), _atividade_valida(inicio="31/02/2026", padrao="")
    )
    assert data_invalida.status_code == 200
    assert "início da vigência é uma data inválida" in data_invalida.content.decode()

    # Segunda padrão com vigência em aberto sobreposta: recusa com o motivo, nada gravado.
    segunda_padrao = client.post(
        _url_nova_atividade(empresa), _atividade_valida(inicio="01/01/2019")
    )
    assert segunda_padrao.status_code == 200
    assert "A padrão é uma por vez" in segunda_padrao.content.decode()

    # Campo fora do contrato: 400 e nada gravado.
    fora_do_contrato = client.post(
        _url_nova_atividade(empresa), _atividade_valida(inicio="01/01/2020", extra="x")
    )
    assert fora_do_contrato.status_code == 400

    assert AtividadeEmpresa.objects.filter(empresa=empresa).count() == 1


def test_tela_atividade_editar_mostra_o_que_esta_gravado(client, empresa, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_editar_atividade(empresa, atividade))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'value="Serviço sintético de teste"' in html
    assert 'value="01/01/2018"' in html
    assert_moldura_acessivel(html)


def test_alterar_atividade_pela_tela(client, empresa, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_editar_atividade(empresa, atividade),
        _atividade_valida(
            descricao="Consultoria sintética", enquadramento=EnquadramentoAtividade.ANEXO_IV
        ),
    )

    assert resposta.status_code == 302
    atividade.refresh_from_db()
    assert atividade.descricao == "Consultoria sintética"
    assert atividade.enquadramento == EnquadramentoAtividade.ANEXO_IV


def test_tela_encerrar_atividade_e_acessivel(client, empresa, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_encerrar_atividade(empresa, atividade))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fiscal/atividade_encerrar.html" in [t.name for t in resposta.templates]
    assert "A linha não é apagada" in html
    assert_moldura_acessivel(html)


def test_encerrar_atividade_pela_tela(client, empresa, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    _logar(client, usuario_gestor_a)

    # Data de fim inválida: recusa, a vigência continua em aberto.
    invalida = client.post(_url_encerrar_atividade(empresa, atividade), {"fim": "32/12/2026"})
    assert invalida.status_code == 200
    atividade.refresh_from_db()
    assert atividade.fim is None

    # Fim anterior ao início: a regra do serviço recusa e a tela mostra o motivo.
    anterior = client.post(_url_encerrar_atividade(empresa, atividade), {"fim": "31/12/2017"})
    assert anterior.status_code == 200
    atividade.refresh_from_db()
    assert atividade.fim is None

    # Encerramento válido: grava o fim e volta para a lista.
    feliz = client.post(_url_encerrar_atividade(empresa, atividade), {"fim": "31/12/2026"})
    assert feliz.status_code == 302
    atividade.refresh_from_db()
    assert atividade.fim == date(2026, 12, 31)

    # Já encerrada: a tela recusa outra data de fim e não grava.
    de_novo = client.post(_url_encerrar_atividade(empresa, atividade), {"fim": "30/06/2026"})
    assert de_novo.status_code == 200
    assert "já tem fim de vigência em 31/12/2026" in de_novo.content.decode()
    atividade.refresh_from_db()
    assert atividade.fim == date(2026, 12, 31)


# ---------------------------------------------------------------------------
# Folha para o fator r: listar (com o FS12 do mês), lançar, confirmar e estornar
# ---------------------------------------------------------------------------


def test_tela_folhas_fator_r_mostra_a_folha_e_o_fs12_de_cada_mes(client, empresa, usuario_gestor_a):
    folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao=Decimal("1000"))
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_folhas(), {"empresa": empresa.pk, "ano": 2026})

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Folhas lançadas em 2026" in html
    assert "1.000,00" in html
    # Janela de 06/2026 não tem os 12 meses confirmados: o FS12 diz o que falta, sem valor.
    assert "FS12 de cada mês de 2026" in html
    assert "Faltam confirmar" in html
    assert_moldura_acessivel(html)


def test_tela_folhas_fator_r_sem_empresa_pede_a_escolha(client, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_folhas())

    assert resposta.status_code == 200
    assert "Escolha uma empresa para ver a folha do fator r." in resposta.content.decode()


def test_tela_lancar_folha_e_acessivel(client, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_nova_folha(empresa), {"ano": "2026", "mes": "5"})

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fiscal/folha_form.html" in [t.name for t in resposta.templates]
    for rotulo in (
        "Remuneração base INSS: empregados e avulsos",
        "Pró-labore e autônomos",
        "13º salário",
        "CPP recolhida",
        "FGTS recolhido",
    ):
        assert rotulo in html, rotulo
    assert_moldura_acessivel(html)


def test_lancar_folha_pela_tela_recusa_sem_gravar(client, empresa, usuario_gestor_a):
    """Caminho feliz: lança em rascunho. Cada recusa responde 200 ou 400 e não grava."""
    _logar(client, usuario_gestor_a)

    feliz = client.post(_url_nova_folha(empresa), _folha_valida())
    assert feliz.status_code == 302
    folha = FolhaFatorR.objects.get(empresa=empresa)
    assert folha.estado == EstadoFolhaFatorR.RASCUNHO
    assert folha.remuneracao_empregados_avulsos == Decimal("1000.00")

    # Componente em branco: a tela pede o zero explícito, sem folha zero por omissão.
    em_branco = client.post(
        _url_nova_folha(empresa), _folha_valida(mes="06", pro_labore_autonomos="")
    )
    assert em_branco.status_code == 200
    assert "Use 0,00 se não houve" in em_branco.content.decode()

    # Notação científica não é valor digitado: recusa antes do serviço.
    cientifica = client.post(
        _url_nova_folha(empresa), _folha_valida(mes="06", decimo_terceiro="1e3")
    )
    assert cientifica.status_code == 200
    assert "valor inválido" in cientifica.content.decode()

    # Mais de duas casas: o serviço recusa com a regra.
    tres_casas = client.post(
        _url_nova_folha(empresa), _folha_valida(mes="06", cpp_recolhida="1,234")
    )
    assert tres_casas.status_code == 200
    assert "aceita no máximo duas casas decimais" in tres_casas.content.decode()

    # Segundo lançamento do mesmo mês: o rascunho anterior já ocupa a vaga.
    repetida = client.post(_url_nova_folha(empresa), _folha_valida(mes="05"))
    assert repetida.status_code == 200
    assert "Já existe folha de 05/2026" in repetida.content.decode()

    # Campo fora do contrato: 400.
    fora_do_contrato = client.post(_url_nova_folha(empresa), _folha_valida(mes="07", extra="x"))
    assert fora_do_contrato.status_code == 400

    assert FolhaFatorR.objects.filter(empresa=empresa).count() == 1


def test_confirmar_folha_pela_tela(client, empresa, usuario_gestor_a):
    folha = _folha_de_lancada(empresa, usuario_gestor_a, 2026, 5)
    _logar(client, usuario_gestor_a)

    resposta = client.post(_url_confirmar_folha(empresa, folha))

    assert resposta.status_code == 302
    folha.refresh_from_db()
    assert folha.estado == EstadoFolhaFatorR.CONFIRMADA
    assert folha.confirmada_por == usuario_gestor_a

    # Confirmar de novo: o serviço recusa (já não é rascunho) e nada muda.
    de_novo = client.post(_url_confirmar_folha(empresa, folha))
    assert de_novo.status_code == 302
    folha.refresh_from_db()
    assert folha.estado == EstadoFolhaFatorR.CONFIRMADA


def test_tela_estornar_folha_e_acessivel(client, empresa, usuario_gestor_a):
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao=Decimal("500"))
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_estornar_folha(empresa, folha))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "fiscal/folha_estornar.html" in [t.name for t in resposta.templates]
    assert "Motivo do estorno" in html
    assert_moldura_acessivel(html)


def test_estornar_folha_pela_tela_exige_motivo(client, empresa, usuario_gestor_a):
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao=Decimal("500"))
    _logar(client, usuario_gestor_a)

    # Sem motivo: o serviço recusa; a folha continua confirmada.
    sem_motivo = client.post(_url_estornar_folha(empresa, folha), {"motivo": "   "})
    assert sem_motivo.status_code == 200
    assert "Informe o motivo do estorno." in sem_motivo.content.decode()
    folha.refresh_from_db()
    assert folha.estado == EstadoFolhaFatorR.CONFIRMADA

    # Com motivo: estorna e guarda o motivo na própria folha.
    com_motivo = client.post(
        _url_estornar_folha(empresa, folha), {"motivo": "Lançado com a competência errada."}
    )
    assert com_motivo.status_code == 302
    folha.refresh_from_db()
    assert folha.estado == EstadoFolhaFatorR.ESTORNADA
    assert folha.motivo_estorno == "Lançado com a competência errada."


# ---------------------------------------------------------------------------
# Permissões: PARALEGAL vê e não escreve; CLIENTE nada; anônimo vai ao login
# ---------------------------------------------------------------------------


def test_paralegal_ve_as_telas_e_nao_escreve(client, empresa, paralegal_a, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao=Decimal("500"))
    _logar(client, paralegal_a)

    assert client.get(_url_pre_das(), _pre_das_de(empresa, 2026, 6)).status_code == 200
    assert client.get(_url_atividades(), {"empresa": empresa.pk}).status_code == 200
    assert client.get(_url_folhas(), {"empresa": empresa.pk, "ano": 2026}).status_code == 200

    # Quem só consulta vê o botão desabilitado com o motivo, e o POST é recusado no servidor.
    html = client.get(_url_atividades(), {"empresa": empresa.pk}).content.decode()
    assert "disabled" in html
    assert "não cadastra, altera, lança nem estorna" in html

    assert client.get(_url_nova_atividade(empresa)).status_code == 403
    assert client.post(_url_nova_atividade(empresa), _atividade_valida()).status_code == 403
    assert (
        client.post(_url_editar_atividade(empresa, atividade), _atividade_valida()).status_code
        == 403
    )
    assert (
        client.post(_url_encerrar_atividade(empresa, atividade), {"fim": "31/12/2026"}).status_code
        == 403
    )
    assert client.get(_url_nova_folha(empresa)).status_code == 403
    assert client.post(_url_nova_folha(empresa), _folha_valida()).status_code == 403
    assert client.post(_url_confirmar_folha(empresa, folha)).status_code == 403
    assert client.post(_url_estornar_folha(empresa, folha), {"motivo": "x"}).status_code == 403

    # Nada foi gravado pelas tentativas.
    atividade.refresh_from_db()
    assert atividade.fim is None
    assert AtividadeEmpresa.objects.filter(empresa=empresa).count() == 1
    folha.refresh_from_db()
    assert folha.estado == EstadoFolhaFatorR.CONFIRMADA
    assert FolhaFatorR.objects.filter(empresa=empresa).count() == 1


def test_cliente_e_recusado_em_todas_as_telas(client, empresa, usuario_cliente_a, usuario_gestor_a):
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    _logar(client, usuario_cliente_a)

    assert client.get(_url_pre_das(), _pre_das_de(empresa, 2026, 6)).status_code == 403
    assert client.get(_url_atividades(), {"empresa": empresa.pk}).status_code == 403
    assert client.get(_url_folhas(), {"empresa": empresa.pk}).status_code == 403
    assert client.get(_url_nova_atividade(empresa)).status_code == 403
    assert (
        client.post(_url_encerrar_atividade(empresa, atividade), {"fim": "31/12/2026"}).status_code
        == 403
    )
    assert client.post(_url_nova_folha(empresa), _folha_valida()).status_code == 403


@pytest.mark.parametrize(
    "nome_rota,argumentos",
    [
        ("fiscal_web:pre_das", []),
        ("fiscal_web:atividades", []),
        ("fiscal_web:folhas_fator_r", []),
        ("fiscal_web:atividade_nova", [1]),
        ("fiscal_web:folha_nova", [1]),
    ],
)
def test_anonimo_e_redirecionado_ao_login(client, nome_rota, argumentos):
    resposta = client.get(reverse(nome_rota, args=argumentos))

    assert resposta.status_code == 302
    assert "login" in resposta["Location"]


# ---------------------------------------------------------------------------
# Isolamento: outro escritório e outra empresa do mesmo escritório recebem 404
# ---------------------------------------------------------------------------


def test_outro_escritorio_recebe_404_nas_telas_do_simples(
    client, gestor_b, empresa, usuario_gestor_a
):
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao=Decimal("500"))
    _logar(client, gestor_b)

    assert client.get(_url_pre_das(), _pre_das_de(empresa, 2026, 6)).status_code == 404
    assert client.get(_url_atividades(), {"empresa": empresa.pk}).status_code == 404
    assert client.get(_url_folhas(), {"empresa": empresa.pk, "ano": 2026}).status_code == 404
    assert client.get(_url_nova_atividade(empresa)).status_code == 404
    assert client.post(_url_nova_atividade(empresa), _atividade_valida()).status_code == 404
    assert client.get(_url_editar_atividade(empresa, atividade)).status_code == 404
    assert (
        client.post(_url_encerrar_atividade(empresa, atividade), {"fim": "31/12/2026"}).status_code
        == 404
    )
    assert client.post(_url_nova_folha(empresa), _folha_valida()).status_code == 404
    assert client.post(_url_confirmar_folha(empresa, folha)).status_code == 404
    assert client.post(_url_estornar_folha(empresa, folha), {"motivo": "x"}).status_code == 404

    atividade.refresh_from_db()
    assert atividade.fim is None
    folha.refresh_from_db()
    assert folha.estado == EstadoFolhaFatorR.CONFIRMADA


def test_registro_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, empresa, empresa_a2, usuario_gestor_a
):
    """Atividade e folha são de `empresa`; pedidas pela URL de `empresa_a2` (mesmo escritório)."""
    atividade = atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao=Decimal("500"))
    _logar(client, usuario_gestor_a)

    assert client.get(_url_editar_atividade(empresa_a2, atividade)).status_code == 404
    assert (
        client.post(
            _url_encerrar_atividade(empresa_a2, atividade), {"fim": "31/12/2026"}
        ).status_code
        == 404
    )
    assert client.post(_url_confirmar_folha(empresa_a2, folha)).status_code == 404
    assert client.post(_url_estornar_folha(empresa_a2, folha), {"motivo": "x"}).status_code == 404

    atividade.refresh_from_db()
    assert atividade.fim is None
    folha.refresh_from_db()
    assert folha.estado == EstadoFolhaFatorR.CONFIRMADA


# ---------------------------------------------------------------------------
# Menu, atalho da home, link do painel da receita e inventário
# ---------------------------------------------------------------------------


def test_menu_simples_mostra_pre_das_atividades_e_folha_a_quem_consulta(
    client, paralegal_a, usuario_cliente_a
):
    _logar(client, paralegal_a)
    html = client.get(reverse("tenancy:painel")).content.decode()
    assert _url_pre_das() in html
    assert _url_atividades() in html
    assert _url_folhas() in html
    assert "Pré-DAS" in html and "Atividades" in html and "Folha (fator r)" in html

    _logar(client, usuario_cliente_a)
    html_cliente = client.get(reverse("tenancy:painel")).content.decode()
    assert _url_pre_das() not in html_cliente


def test_home_do_fiscal_tem_atalho_para_o_pre_das(client, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(reverse("module_home:home", args=["fiscal"]))

    atalhos = resposta.context["home"]["atalhos"]
    assert resposta.status_code == 200
    assert any(
        atalho["rotulo"] == "Pré-DAS do Simples (conferência)"
        and atalho["url"].startswith(_url_pre_das())
        for atalho in atalhos
    )


def test_painel_da_receita_tem_link_para_o_pre_das_do_mes(client, empresa, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    html = client.get(
        reverse("fiscal_web:receita_do_mes"),
        {"empresa": empresa.pk, "ano": 2026, "mes": 6},
    ).content.decode()

    assert f"{_url_pre_das()}?empresa={empresa.pk}&amp;ano=2026&amp;mes=6" in html
    assert "Ver o pré-DAS de 06/2026" in html


def test_rotas_do_pre_das_atividades_e_folha_estao_no_inventario():
    """Cada rota nova tem uma linha no inventário do DL-024: a guarda de cobertura reprova
    rota que nasce sem classificação, e este teste nomeia a que faltar."""
    rotas = {
        "fiscal_web:pre_das",
        "fiscal_web:atividades",
        "fiscal_web:atividade_nova",
        "fiscal_web:atividade_editar",
        "fiscal_web:atividade_encerrar",
        "fiscal_web:folhas_fator_r",
        "fiscal_web:folha_nova",
        "fiscal_web:folha_confirmar",
        "fiscal_web:folha_estornar",
    }
    assert rotas <= set(NOMES_DE_TELA_FISCAL_FORA_DA_CONTABILIDADE)
