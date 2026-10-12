"""DL-087 (frente B): as telas da classificação fiscal versionada, e o comportamento de cada uma.

Cobre os cinco estados de cada tela (vazio, erro com a mensagem do serviço, sucesso, carregando
não se aplica por ser HTML do servidor, sem permissão) e os fluxos: cadastro com prévia antes de
gravar, desativação com motivo obrigatório, fila agrupada com "criar regra" pré-preenchido, e a
página das regras do produto (só leitura).

Dados sintéticos: NFC-e geradas pela recepção real (`suporte_dl085.nfce`), CNPJ de teste.
Permissões, isolamento e CSRF estão em `test_dl087_telas_permissoes.py`; a origem da sugestão na
escrituração e no lote, em `test_dl087_telas_origem.py`; HTML de acessibilidade, em
`test_dl087_telas_acessibilidade.py`.
"""

from datetime import date, timedelta
from html import unescape

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.fiscal import classificacao
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.escrituracao_nfe import FUSO_SP
from apps.fiscal.models import RegraClassificacaoNFe
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.suporte_dl085 import nfce
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

NCM_COMBUSTIVEL = "27101259"
NCM_LUBRIFICANTE_PREFIXO = "2710"
MES = {"ano": 2026, "mes": 3}


# ---------------------------------------------------------------------------
# Suporte deste arquivo (os outros arquivos DL-087 de telas importam daqui)
# ---------------------------------------------------------------------------


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Telas DL087 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-telas-dl087")


@pytest.fixture
def analista(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.ANALISTA, "analista-telas-dl087")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-telas-dl087")


@pytest.fixture
def cliente(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-telas-dl087")


def dados(**campos):
    """Critérios de uma regra de saída, com a vigência de março/2026 (dados sintéticos)."""
    base = {
        "tipo": "saida_propria",
        "cfop": "5949",
        "natureza": "revenda",
        "vigencia_inicio": date(2026, 3, 1),
    }
    base.update(campos)
    return classificacao.DadosDaRegra(**base)


def regra_do_escritorio(escritorio, usuario, **campos):
    return classificacao.criar_regra(
        escritorio=escritorio, empresa=None, dados=dados(**campos), usuario=usuario
    )


def regra_da_empresa(escritorio, empresa, usuario, **campos):
    return classificacao.criar_regra(
        escritorio=escritorio, empresa=empresa, dados=dados(**campos), usuario=usuario
    )


def notas_sem_sugestao(escritorio, usuario, empresa, quantidade=3):
    """NFC-e de CFOP 5949 sem sinal: caem na fila, e a regra do CFOP 5949 as tira dela."""
    for numero in range(1, quantidade + 1):
        nfce(escritorio, usuario, numero=numero, cfop="5949", csosn="102", ncm="22030000")
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)


def url_regras(empresa):
    return reverse("fiscal_web:classificacao_regras", args=[empresa.pk])


def url_nova(empresa):
    return reverse("fiscal_web:classificacao_regra_nova", args=[empresa.pk])


def url_fila(empresa, ano=2026, mes=3):
    return reverse("fiscal_web:classificacao_fila", args=[empresa.pk]) + f"?ano={ano}&mes={mes}"


def url_desativar(empresa, regra):
    return reverse("fiscal_web:classificacao_regra_desativar", args=[empresa.pk, regra.pk])


def formulario(**campos):
    """Os campos que a tela manda, com os padrões de uma regra de empresa para CFOP 5102."""
    base = {
        "escopo": "empresa",
        "tipo": "saida_propria",
        "cfop": "5102",
        "ncm": "",
        "ncm_modo": "",
        "cst_csosn": "",
        "id_dest": "",
        "natureza": "revenda",
        "vigencia_inicio": "01/03/2026",
        "vigencia_fim": "",
        "competencia": "03/2026",
        "acao": "criar",
    }
    base.update(campos)
    return base


def ontem_sp():
    return timezone.now().astimezone(FUSO_SP).date() - timedelta(days=1)


# ---------------------------------------------------------------------------
# Regras da empresa: lista, estados e a régua de decisão
# ---------------------------------------------------------------------------


def test_lista_vazia_diz_que_a_empresa_nao_tem_regra(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.get(url_regras(empresa))

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    assert "Nenhuma regra de classificação para esta empresa" in html
    assert "a sugestão é a do produto" in html


def test_lista_mostra_criterios_natureza_vigencia_autor_e_itens(
    client, gestor, empresa, escritorio_a
):
    regra_do_escritorio(escritorio_a, gestor, ncm="22030000", ncm_modo="exato", cst_csosn="102")
    client.force_login(gestor)

    html = client.get(url_regras(empresa)).content.decode("utf-8")

    assert "CFOP 5949; NCM exato 22030000; CST/CSOSN 102" in html
    assert "Revenda" in html or "revenda" in html.lower()
    assert "a partir de 01/03/2026, sem fim" in html
    assert gestor.get_username() in html
    assert "Do escritório" in html
    # Itens confirmados a partir da regra: contagem de quem a usa, zero antes de qualquer uso.
    assert "Itens confirmados a partir desta regra" in html


def test_lista_publica_a_ordem_de_decisao_e_os_pesos_do_servico(client, gestor, empresa):
    client.force_login(gestor)

    html = client.get(url_regras(empresa)).content.decode("utf-8")

    assert "Como a regra decide" in html
    for trecho in (
        "CFOP 16",
        "NCM exato 8",
        "NCM por prefixo 4",
        "CST/CSOSN 2",
        "idDest 1",
        "Vence a de maior especificidade",
        "mais longo",
        "vence a regra da empresa sobre a do escritório",
        "Empate com a mesma natureza não é conflito",
        "Empate com natureza diferente é conflito",
    ):
        assert trecho in html, trecho


def test_filtro_por_escopo_e_situacao_so_mostra_o_que_foi_pedido(
    client, gestor, empresa, escritorio_a
):
    regra_do_escritorio(escritorio_a, gestor)
    regra_da_empresa(escritorio_a, empresa, gestor, cfop="5102")
    client.force_login(gestor)

    so_empresa = client.get(url_regras(empresa) + "?escopo=empresa").content.decode("utf-8")
    so_escritorio = client.get(url_regras(empresa) + "?escopo=escritorio").content.decode("utf-8")

    assert "CFOP 5102" in so_empresa and "CFOP 5949" not in so_empresa
    assert "CFOP 5949" in so_escritorio and "CFOP 5102" not in so_escritorio


def test_filtro_invalido_responde_400_com_mensagem(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.get(url_regras(empresa) + "?escopo=qualquer")

    assert resposta.status_code == 400
    # O Django escapa a aspa simples (&#x27;): a comparação é com o texto que o contador lê.
    assert "Filtro 'Alcance' inválido." in unescape(resposta.content.decode("utf-8"))


def test_lista_nao_altera_nada(client, gestor, empresa, escritorio_a):
    regra = regra_do_escritorio(escritorio_a, gestor)
    antes = RegraClassificacaoNFe.objects.count()
    client.force_login(gestor)

    client.get(url_regras(empresa))
    client.get(url_regras(empresa) + "?situacao=desativada")

    assert RegraClassificacaoNFe.objects.count() == antes
    regra.refresh_from_db()
    assert regra.ativa


# ---------------------------------------------------------------------------
# Formulário: GET, prévia de impacto (sem gravar), criação e os erros do serviço
# ---------------------------------------------------------------------------


def test_formulario_vazio_mostra_todos_os_campos_com_rotulo(client, gestor, empresa):
    client.force_login(gestor)

    html = client.get(url_nova(empresa)).content.decode("utf-8")

    for rotulo in (
        "CFOP (4 dígitos, obrigatório)",
        "NCM (opcional)",
        "Modo do NCM",
        "CST ou CSOSN (opcional)",
        "idDest (opcional)",
        "Natureza resultante",
        "Início da vigência (obrigatório)",
        "Fim da vigência (opcional)",
    ):
        assert rotulo in html, rotulo
    # Escritório aparece como opção para gestor; a natureza só traz as do tipo escolhido.
    assert "Do escritório" in html
    assert "Revenda" in html or "revenda" in html.lower()


def test_gestor_recebe_a_opcao_de_escritorio_e_analista_nao(client, gestor, analista, empresa):
    client.force_login(gestor)
    assert 'value="escritorio"' in client.get(url_nova(empresa)).content.decode("utf-8")

    client.force_login(analista)
    html_analista = client.get(url_nova(empresa)).content.decode("utf-8")
    assert 'value="escritorio"' not in html_analista
    assert "só administrador e gestor a criam" in html_analista


def test_previa_mostra_o_alcance_e_nao_grava_nada(client, gestor, empresa, escritorio_a):
    notas_sem_sugestao(escritorio_a, gestor, empresa)
    client.force_login(gestor)
    antes = RegraClassificacaoNFe.objects.count()

    resposta = client.post(
        url_nova(empresa),
        formulario(cfop="5949", acao="previa"),
    )

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    assert "Alcance antes de gravar: 03/2026" in html
    assert "Nada foi gravado" in html
    assert RegraClassificacaoNFe.objects.count() == antes


def test_previa_com_ncm_mostra_o_alcance_com_e_sem_o_ncm(client, gestor, empresa, escritorio_a):
    notas_sem_sugestao(escritorio_a, gestor, empresa)
    client.force_login(gestor)

    html = client.post(
        url_nova(empresa),
        formulario(cfop="5949", ncm="22030000", ncm_modo="exato", acao="previa"),
    ).content.decode("utf-8")

    assert "Com todos os critérios preenchidos" in html
    assert "Sem o NCM" in html
    assert "Alcance da regra com todos os critérios e sem cada critério opcional" in html


def test_previa_de_combustivel_sem_ncm_mostra_a_recusa_do_servico(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa),
        formulario(cfop="5656", natureza="combustivel", acao="previa"),
    )

    assert resposta.status_code == 400
    html = resposta.content.decode("utf-8")
    assert "exige NCM" in html
    assert 'id="erro_natureza"' in html


def test_previa_com_combustivel_e_prefixo_mostra_aviso_de_lubrificante(
    client, gestor, empresa, escritorio_a
):
    notas_sem_sugestao(escritorio_a, gestor, empresa)
    client.force_login(gestor)

    html = client.post(
        url_nova(empresa),
        formulario(
            cfop="5949",
            natureza="combustivel",
            ncm=NCM_LUBRIFICANTE_PREFIXO,
            ncm_modo="prefixo",
            acao="previa",
        ),
    ).content.decode("utf-8")

    assert "Aviso:" in html
    assert "alcança NCM de lubrificante" in html


def test_criar_regra_grava_pelo_servico_e_volta_para_a_lista(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(url_nova(empresa), formulario(escopo="empresa", acao="criar"))

    assert resposta.status_code == 302
    assert resposta["Location"].startswith(url_regras(empresa))
    regra = RegraClassificacaoNFe.objects.get()
    assert regra.empresa_id == empresa.pk and regra.cfop == "5102"
    assert regra.natureza == "revenda" and regra.vigencia_inicio == date(2026, 3, 1)
    assert resposta["Location"].endswith(f"#regra-{regra.pk}")


def test_criar_com_cst_regime_normal_no_escritorio_mostra_o_aviso_do_simples(
    client, gestor, empresa
):
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa),
        formulario(escopo="escritorio", cst_csosn="00", acao="criar"),
        follow=True,
    )

    texto = resposta.content.decode("utf-8")
    assert "clientes do Simples emitem CSOSN" in texto


def test_cfop_fora_da_tabela_responde_400_com_erro_no_campo(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(url_nova(empresa), formulario(cfop="5000", acao="criar"))

    assert resposta.status_code == 400
    html = resposta.content.decode("utf-8")
    assert "fora da tabela oficial" in html
    assert 'id="erro_cfop"' in html
    assert not RegraClassificacaoNFe.objects.exists()


def test_data_fora_do_formato_e_erro_do_campo_e_nao_500(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa), formulario(vigencia_inicio="2026-03-01", acao="criar")
    )

    assert resposta.status_code == 400
    assert "dd/mm/aaaa" in resposta.content.decode("utf-8")
    assert not RegraClassificacaoNFe.objects.exists()


def test_inicio_da_vigencia_vazio_e_erro_obrigatorio(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(url_nova(empresa), formulario(vigencia_inicio="", acao="criar"))

    assert resposta.status_code == 400
    assert 'id="erro_vigencia_inicio"' in resposta.content.decode("utf-8")


def test_fim_anterior_ao_inicio_e_recusado_com_mensagem(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa),
        formulario(vigencia_fim="01/02/2026", acao="criar"),
    )

    assert resposta.status_code == 400
    assert "anterior ao início" in resposta.content.decode("utf-8")


def test_duplicada_responde_409_com_a_regra_existente(client, gestor, empresa):
    regra_da_empresa(empresa.escritorio, empresa, gestor, cfop="5102", natureza="revenda")
    client.force_login(gestor)

    resposta = client.post(url_nova(empresa), formulario(cfop="5102", acao="criar"))

    assert resposta.status_code == 409
    assert "Já existe a regra n.º" in resposta.content.decode("utf-8")
    assert RegraClassificacaoNFe.objects.count() == 1


def test_natureza_que_nao_cabe_no_tipo_responde_400_no_campo_natureza(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa),
        formulario(tipo="devolucao", cfop="1202", natureza="revenda", acao="criar"),
    )

    assert resposta.status_code == 400
    assert 'id="erro_natureza"' in resposta.content.decode("utf-8")


def test_atualizar_naturezas_troca_a_lista_sem_gravar(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa), formulario(tipo="devolucao", cfop="1202", acao="atualizar")
    )

    assert resposta.status_code == 200
    assert not RegraClassificacaoNFe.objects.exists()


def test_formulario_de_paralegal_fica_desabilitado_com_o_motivo(client, paralegal, empresa):
    client.force_login(paralegal)

    resposta = client.get(url_nova(empresa))

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    assert "não cria: criar regra de classificação é de quem escritura no fiscal" in html
    assert 'name="acao" value="criar" class="botao botao--primario" disabled' in html


def test_formulario_pre_preenchido_pela_fila_traz_os_criterios_e_o_aviso(client, gestor, empresa):
    client.force_login(gestor)
    query = (
        "?origem=fila&escopo=empresa&tipo=saida_propria&cfop=5949&ncm=22030000"
        "&ncm_modo=exato&cst_csosn=102&vigencia_inicio=01/03/2026&ano=2026&mes=3"
    )

    html = client.get(url_nova(empresa) + query).content.decode("utf-8")

    assert 'value="5949"' in html
    assert 'value="22030000"' in html
    assert "Veio da fila." in html
    assert "NCM, CST ou CSOSN e idDest são opcionais" in html
    assert 'name="origem" value="fila"' in html


def test_formulario_de_criacao_grava_o_contexto_da_fila_no_post(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(url_nova(empresa), formulario(origem="fila", cfop="5949", acao="previa"))

    assert resposta.status_code == 200
    assert "Veio da fila." in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# Desativação: confirmação, motivo obrigatório e efeito na vigência
# ---------------------------------------------------------------------------


def test_desativar_mostra_o_efeito_e_pede_o_motivo(client, gestor, empresa, escritorio_a):
    regra = regra_do_escritorio(escritorio_a, gestor)
    client.force_login(gestor)

    html = client.get(url_desativar(empresa, regra)).content.decode("utf-8")

    assert "O que vai acontecer" in html
    # A1: desativar é revogar. O texto diz que a regra vale para TODAS as notas, e que as efetivadas
    # guardam a origem.
    assert "deixa de valer para TODAS as notas" in html
    assert "guardam a origem que tiveram" in html
    assert "Motivo da desativação (obrigatório)" in html


def test_desativar_sem_motivo_responde_400_e_nada_muda(client, gestor, empresa, escritorio_a):
    regra = regra_do_escritorio(escritorio_a, gestor)
    client.force_login(gestor)

    resposta = client.post(url_desativar(empresa, regra), {"motivo": "   "})

    assert resposta.status_code == 400
    assert "Informe o motivo da desativação." in resposta.content.decode("utf-8")
    regra.refresh_from_db()
    assert regra.ativa


def test_desativar_com_motivo_revoga_e_grava_quem_e_o_motivo(client, gestor, empresa, escritorio_a):
    regra = regra_do_escritorio(escritorio_a, gestor)
    client.force_login(gestor)

    resposta = client.post(url_desativar(empresa, regra), {"motivo": "Regra errada"})

    assert resposta.status_code == 302
    regra.refresh_from_db()
    assert not regra.ativa
    # A1: a revogação grava o fim na véspera do início, e nenhuma nota cai nessa vigência.
    assert regra.vigencia_fim == regra.vigencia_inicio - timedelta(days=1)
    assert regra.motivo_desativacao == "Regra errada"
    assert regra.desativada_por_id == gestor.pk


def test_desativar_de_novo_responde_409_e_a_tela_diz_que_nada_a_fazer(
    client, gestor, empresa, escritorio_a
):
    regra = regra_do_escritorio(escritorio_a, gestor)
    classificacao.desativar_regra(regra, motivo="primeira vez", usuario=gestor)
    client.force_login(gestor)

    tela = client.get(url_desativar(empresa, regra)).content.decode("utf-8")
    resposta = client.post(url_desativar(empresa, regra), {"motivo": "de novo"})

    assert "Esta regra já está desativada" in tela
    assert resposta.status_code == 409


def test_lista_filtra_desativadas_depois_de_desativar(client, gestor, empresa, escritorio_a):
    regra = regra_do_escritorio(escritorio_a, gestor)
    classificacao.desativar_regra(regra, motivo="fim", usuario=gestor)
    client.force_login(gestor)

    ativas = client.get(url_regras(empresa) + "?situacao=ativa").content.decode("utf-8")
    desativadas = client.get(url_regras(empresa) + "?situacao=desativada").content.decode("utf-8")

    assert "CFOP 5949" not in ativas
    assert "CFOP 5949" in desativadas
    assert "revogada em" in desativadas


# ---------------------------------------------------------------------------
# Fila "a classificar"
# ---------------------------------------------------------------------------


def test_fila_vazia_diz_que_nao_ha_nada_a_classificar_no_mes(client, gestor, empresa):
    client.force_login(gestor)

    html = client.get(url_fila(empresa)).content.decode("utf-8")

    assert "Nada a classificar em 03/2026." in html


def test_fila_agrupa_e_oferece_criar_regra_pre_preenchida(client, gestor, empresa, escritorio_a):
    notas_sem_sugestao(escritorio_a, gestor, empresa, quantidade=3)
    client.force_login(gestor)

    html = client.get(url_fila(empresa)).content.decode("utf-8")

    assert "3 nota(s)" in html or "3</strong> nota(s)" in html
    assert "Criar regra" in html
    assert "cfop=5949" in html
    assert "origem=fila" in html
    assert "vigencia_inicio=01%2F03%2F2026" in html or "vigencia_inicio=01/03/2026" in html


def test_fila_criar_regra_pelo_grupo_esvazia_o_grupo(client, gestor, empresa, escritorio_a):
    notas_sem_sugestao(escritorio_a, gestor, empresa, quantidade=2)
    client.force_login(gestor)
    client.post(
        url_nova(empresa),
        formulario(cfop="5949", natureza="revenda", vigencia_inicio="01/03/2026", acao="criar"),
    )

    html = client.get(url_fila(empresa)).content.decode("utf-8")

    assert "Nada a classificar em 03/2026." in html


def test_fila_mostra_o_aviso_quando_o_mes_esta_confirmado(
    client, gestor, empresa, escritorio_a, monkeypatch
):
    """A confirmação do mês vem do serviço. Aqui se prova só que a tela mostra o aviso dela
    (o serviço é trocado por um valor fixo, em teste isolado de apresentação)."""
    notas_sem_sugestao(escritorio_a, gestor, empresa)
    monkeypatch.setattr(classificacao, "mes_confirmado_da_empresa", lambda *_: True)
    client.force_login(gestor)

    html = client.get(url_fila(empresa)).content.decode("utf-8")

    assert "Mês já confirmado" in html


def test_fila_conta_notas_sem_leitura_e_nao_as_lista(client, gestor, empresa, escritorio_a):
    nfce(escritorio_a, gestor, numero=9, cfop="5949", csosn="102", ncm="22030000")
    client.force_login(gestor)

    html = client.get(url_fila(empresa)).content.decode("utf-8")

    assert "ainda não lida" in html


def test_fila_mes_invalido_responde_400(client, gestor, empresa):
    client.force_login(gestor)

    assert client.get(url_fila(empresa, mes=13)).status_code == 400


def test_fila_nao_altera_nada(client, gestor, empresa, escritorio_a):
    notas_sem_sugestao(escritorio_a, gestor, empresa)
    antes = RegraClassificacaoNFe.objects.count()
    client.force_login(gestor)

    client.get(url_fila(empresa))

    assert RegraClassificacaoNFe.objects.count() == antes


# ---------------------------------------------------------------------------
# Regras do produto (só leitura)
# ---------------------------------------------------------------------------


def test_regras_do_produto_mostra_as_linhas_com_fonte(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.get(reverse("fiscal_web:classificacao_produto"))

    assert resposta.status_code == 200
    html = resposta.content.decode("utf-8")
    primeira = classificacao.REGRAS_DO_PRODUTO[0]
    assert primeira["sinal"] in html
    assert primeira["fonte"] in html
    assert "não é norma relida aqui" in html


def test_regras_do_produto_nao_aceita_escrita(client, gestor):
    client.force_login(gestor)

    assert client.post(reverse("fiscal_web:classificacao_produto"), {}).status_code == 405
