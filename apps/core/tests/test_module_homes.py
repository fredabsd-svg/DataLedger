"""Comportamento readonly, filtros e isolamento das homes (DL-049)."""

from datetime import date, datetime
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import Competencia, Conta, EstadoCompetencia, LancamentoContabil
from apps.contabilidade.services import localizar_lotes_desbalanceados
from apps.core.module_homes import (
    LIMITE_PREFERENCIAS_ESCRITORIOS,
    SESSION_KEY,
    menu_modulos,
    montar_home,
    resolver_escopo,
)
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.fiscal.models import DocumentoFiscal, EventoFiscal, LoteDeRecepcao, ResultadoDoArquivo
from apps.fiscal.services import receber_envio
from apps.fiscal.tests.xml_sinteticos import xml_evento, xml_nfse
from apps.livro_caixa.models import ContaLivroCaixa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario(client):
    escritorio = Escritorio.objects.create(nome="Escritório das homes", cnpj="11111111000111")
    outro = Escritorio.objects.create(nome="Escritório isolado", cnpj="22222222000122")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Alfa Serviços Ltda", cnpj="11444777000161"
    )
    segunda = Empresa.objects.create(
        escritorio=escritorio, razao_social="Beta Comércio Ltda", cnpj="11222333000181"
    )
    alheia = Empresa.objects.create(
        escritorio=outro, razao_social="Sigilo de outro escritório", cnpj="11444777000161"
    )
    usuario = get_user_model().objects.create_user(username="gestor-home", password="senha-teste")
    vinculo = VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    client.force_login(usuario)
    return {
        "escritorio": escritorio,
        "outro": outro,
        "empresa": empresa,
        "segunda": segunda,
        "alheia": alheia,
        "usuario": usuario,
        "vinculo": vinculo,
    }


def _url(modulo="contabilidade", *, lista=False):
    return reverse("module_home:pendencias" if lista else "module_home:home", args=[modulo])


def _request(cenario, parametros, modulo="contabilidade"):
    request = RequestFactory().get(_url(modulo), parametros)
    request.user = cenario["usuario"]
    request.escritorio = cenario["escritorio"]
    request.papel = Papel.GESTOR
    request.session = {}
    request.resolver_match = resolve(_url(modulo))
    return request


def _plano(empresa, *, ativa=False):
    return Conta.objects.create(
        empresa=empresa, codigo="1", nome="Ativo", tipo="ativo", natureza="devedora", ativo=ativa
    )


def _receber(cenario, xml, nome="nota.xml"):
    return receber_envio(
        escritorio=cenario["escritorio"],
        usuario=cenario["usuario"],
        arquivo=BytesIO(xml),
        nome_arquivo=nome,
    )


def _trocar_escritorio(client, escritorio):
    sessao = client.session
    sessao["escritorio_id"] = escritorio.pk
    sessao.save()


def _escritorio_sem_empresas(client, cenario, *, papel=Papel.GESTOR):
    escritorio = Escritorio.objects.create(nome="Escritório sem clientes", cnpj="33333333000133")
    vinculo = VinculoUsuarioEscritorio.objects.create(
        usuario=cenario["usuario"], escritorio=escritorio, papel=papel
    )
    _trocar_escritorio(client, escritorio)
    return {**cenario, "escritorio": escritorio, "vinculo": vinculo}


def test_entrada_autenticada_e_modulo_desconhecido(client):
    assert client.get(_url()).status_code == 302
    assert client.get(_url("modulo-inexistente")).status_code == 302


@pytest.mark.parametrize("modulo", ["vendas", "estoque", "inventario"])
@pytest.mark.parametrize("lista", [False, True])
def test_modulo_fora_do_escopo_retornando404_autenticado(client, cenario, modulo, lista):
    resposta = client.get(_url(modulo, lista=lista))
    assert resposta.status_code == 404


@pytest.mark.parametrize("pagina", ["home", "painel"])
def test_navegacao_renderizada_respeita_escopo_e_preserva_contexto(client, cenario, pagina):
    class NavegacaoDosModulos(HTMLParser):
        def __init__(self):
            super().__init__()
            self.no_menu = False
            self.encontrou_menu = False
            self.destinos = []
            self.rotulos = []

        def handle_starttag(self, tag, attrs):
            atributos = dict(attrs)
            if tag == "nav" and atributos.get("aria-label") == "Trocar módulo":
                self.no_menu = True
                self.encontrou_menu = True
            if tag == "a" and self.no_menu:
                self.destinos.append(atributos["href"])

        def handle_endtag(self, tag):
            if tag == "nav":
                self.no_menu = False

        def handle_data(self, data):
            if self.no_menu:
                self.rotulos.append(data.strip())

    resposta = client.get(_url(), {"empresa": cenario["segunda"].pk, "competencia": "2024-02"})
    if pagina == "painel":
        resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    parser = NavegacaoDosModulos()
    parser.feed(resposta.content.decode())
    assert parser.encontrou_menu
    assert {"Vendas", "Estoque", "Inventário", "Inventario"}.isdisjoint(parser.rotulos)
    destinos = {urlsplit(url).path: url for url in parser.destinos}
    for slug in ("vendas", "estoque", "inventario"):
        assert _url(slug) not in destinos
        assert _url(slug, lista=True) not in destinos
    for slug in ("financeiro", "folha"):
        assert _url(slug) in destinos
    # Seguir os links HTML prova o destino e o contexto das rotinas reais,
    # inclusive a seleção incompatível com Livro-caixa, sem ampliar a carteira.
    for slug in ("contabilidade", "fiscal", "livro-caixa"):
        destino = destinos[_url(slug)]
        filtros = parse_qs(urlsplit(destino).query)
        assert filtros["empresa"] == [str(cenario["segunda"].pk)]
        assert filtros["competencia"] == ["2024-02"]
        home = client.get(destino)
        assert home.status_code == 200
        assert home.context["home"]["modulo"]["slug"] == slug
        assert home.context["home"]["filtros"]["empresa"] == str(cenario["segunda"].pk)
        assert home.context["home"]["filtros"]["competencia"] == "2024-02"


def test_sem_permissao_nao_consulta_empresa_nem_expoe_nomes(client, cenario):
    cenario["vinculo"].papel = Papel.CLIENTE
    cenario["vinculo"].save(update_fields=["papel"])
    with CaptureQueriesContext(connection) as consultas:
        resposta = client.get(_url(), {"empresa": "todas", "competencia": "2026-09"})
    assert resposta.status_code == 403
    assert not any('FROM "empresas_empresa"' in consulta["sql"] for consulta in consultas)
    assert cenario["empresa"].razao_social not in resposta.content.decode()
    assert cenario["alheia"].razao_social not in resposta.content.decode()
    assert "R$" not in resposta.content.decode()


@pytest.mark.parametrize("empresa", ["0", "-1", "abc", "9" * 5000, "9223372036854775808"])
def test_identificador_invalido_retornando400(client, cenario, empresa):
    assert client.get(_url(), {"empresa": empresa}).status_code == 400


@pytest.mark.parametrize("competencia", ["2026-00", "2026-13", "0000-01", "3000-01", "9" * 5000])
def test_competencia_invalida_retornando400(client, cenario, competencia):
    assert client.get(_url(), {"competencia": competencia}).status_code == 400


def test_empresa_alheia_e_grupo_alheio_retornam404(client, cenario):
    assert client.get(_url(), {"empresa": cenario["alheia"].pk}).status_code == 404
    assert (
        client.get(
            _url(), {"empresa": "grupo", "empresas": [cenario["empresa"].pk, cenario["alheia"].pk]}
        ).status_code
        == 404
    )


def test_competencia_historica_e_escopo_persistem_entre_modulos(client, cenario):
    client.get(_url(), {"empresa": cenario["segunda"].pk, "competencia": "2024-02"})
    resposta = client.get(_url("fiscal"))
    filtros = resposta.context["home"]["filtros"]
    assert filtros["empresa"] == str(cenario["segunda"].pk)
    assert filtros["competencia"] == "2024-02"
    assert filtros["competencia_rotulo"] == "fev/2024"
    assert any(
        opcao["valor"] == "2024-02" and opcao["selecionada"]
        for opcao in filtros["competencias_opcoes"]
    )


def test_grupo_aceita_multiplos_parametros_e_deduplica(client, cenario):
    primeira, segunda = cenario["empresa"], cenario["segunda"]
    resposta = client.get(
        _url(),
        {
            "empresa": "grupo",
            "empresas": [primeira.pk, segunda.pk, primeira.pk],
            "competencia": "2026-09",
        },
    )
    assert resposta.status_code == 200
    assert resposta.context["home"]["filtros"]["empresas_ids"] == sorted([primeira.pk, segunda.pk])
    assert resposta.context["home"]["carteira"]["cadastradas"] == "2"
    csv = client.get(_url(), {"empresa": "grupo", "empresas": f"{primeira.pk},{segunda.pk}"})
    assert csv.context["home"]["carteira"]["cadastradas"] == "2"


def test_trocar_escritorio_descarta_ids_da_sessao(client, cenario):
    client.get(_url(), {"empresa": "todas", "competencia": "2024-02"})
    VinculoUsuarioEscritorio.objects.create(
        usuario=cenario["usuario"], escritorio=cenario["outro"], papel=Papel.GESTOR
    )
    sessao = client.session
    sessao["escritorio_id"] = cenario["outro"].pk
    sessao.save()
    resposta = client.get(_url())
    assert resposta.context["home"]["filtros"]["empresa"] == str(cenario["alheia"].pk)
    assert resposta.context["home"]["carteira"]["cadastradas"] == "1"
    assert cenario["empresa"].razao_social not in resposta.content.decode()


def test_ida_e_volta_restauram_grupo_e_competencia_de_cada_escritorio(client, cenario):
    VinculoUsuarioEscritorio.objects.create(
        usuario=cenario["usuario"], escritorio=cenario["outro"], papel=Papel.GESTOR
    )
    _trocar_escritorio(client, cenario["escritorio"])
    ids = sorted([cenario["empresa"].pk, cenario["segunda"].pk])
    client.get(_url(), {"empresa": "grupo", "empresas": ids, "competencia": "2024-02"})
    _trocar_escritorio(client, cenario["outro"])
    client.get(_url(), {"empresa": cenario["alheia"].pk, "competencia": "2022-11"})

    for escritorio, empresa, competencia, esperados in (
        (cenario["escritorio"], "grupo", "2024-02", ids),
        (cenario["outro"], str(cenario["alheia"].pk), "2022-11", [cenario["alheia"].pk]),
    ):
        _trocar_escritorio(client, escritorio)
        resposta = client.get(_url("fiscal"))
        filtros = resposta.context["home"]["filtros"]
        assert filtros["empresa"] == empresa
        assert filtros["competencia"] == competencia
        assert filtros["empresas_ids"] == esperados
        inicio = client.get(reverse("tenancy:painel"))
        destinos = {item["chave"]: item["url"] for item in inicio.context["modulos"]}
        assert parse_qs(urlsplit(destinos["fiscal"]).query)["competencia"] == [competencia]
        assert parse_qs(urlsplit(destinos["fiscal"]).query)["empresa"] == [empresa]
        request = _request({**cenario, "escritorio": escritorio}, {}, "fiscal")
        # Em HTTP o middleware já resolveu o escritório usando a sessão.
        # Carregar essa sessão antes mede consultas do menu, não sua leitura
        # inicial pelo SessionStore retornado pelo client de teste.
        request.session = dict(client.session)
        with CaptureQueriesContext(connection) as consultas:
            menu = menu_modulos(request)
        assert len(consultas) == 0
        assert all(
            parse_qs(urlsplit(item["url"]).query)["competencia"] == [competencia] for item in menu
        )
        assert cenario["alheia"].razao_social not in str(menu)


@pytest.mark.parametrize("identificador,status", [("alheia", 404), ("malformado", 400)])
def test_grupo_restaurado_revalida_empresa_no_escritorio(client, cenario, identificador, status):
    sessao = client.session
    sessao[SESSION_KEY] = {
        "escritorios": {
            str(cenario["escritorio"].pk): {
                "empresa": "grupo",
                "empresas": [
                    str(cenario["empresa"].pk),
                    str(cenario["alheia"].pk) if identificador == "alheia" else "0",
                ],
                "competencia": "2024-02",
            }
        }
    }
    sessao.save()
    resposta = client.get(_url())
    assert resposta.status_code == status
    assert cenario["alheia"].razao_social not in resposta.content.decode()


def test_preferencia_antiga_migra_sem_perder_contexto_e_limita_retencao(cenario):
    request = _request(cenario, {})
    request.session[SESSION_KEY] = {
        "escritorio_id": cenario["escritorio"].pk,
        "empresa": str(cenario["segunda"].pk),
        "empresas": [],
        "competencia": "2024-02",
    }
    escopo = resolver_escopo(request, "contabilidade")
    assert escopo.empresa == str(cenario["segunda"].pk)
    assert escopo.competencia == "2024-02"
    contexto = request.session[SESSION_KEY]["escritorios"]
    assert list(contexto) == [str(cenario["escritorio"].pk)]
    assert contexto[str(cenario["escritorio"].pk)]["competencia"] == "2024-02"

    # Preferências sintéticas bastam: reter uma entrada não autoriza o acesso
    # ao escritório, e o consumidor global não consulta empresas/vínculos.
    preferencias = {
        str(100000 + indice): {"empresa": "todas", "empresas": [], "competencia": "2022-11"}
        for indice in range(LIMITE_PREFERENCIAS_ESCRITORIOS + 3)
    }
    preferencias.update(contexto)
    request.session[SESSION_KEY] = {"escritorios": preferencias}
    resolver_escopo(request, "contabilidade")
    retidas = request.session[SESSION_KEY]["escritorios"]
    assert len(retidas) == LIMITE_PREFERENCIAS_ESCRITORIOS
    assert str(cenario["escritorio"].pk) in retidas
    assert "100000" not in retidas


def test_sem_registro_nao_significa_aberta_e_get_nao_cria_competencia(client, cenario):
    antes = (
        Competencia.objects.count(),
        RegistroAuditoria.objects.count(),
        LancamentoContabil.objects.count(),
    )
    resposta = client.get(_url(), {"empresa": cenario["empresa"].pk, "competencia": "2026-09"})
    home = resposta.context["home"]
    card = next(card for card in home["kpis"] if card["estado"] == "competencias-abertas")
    assert card["quantidade"] == 0
    assert "sem registro" in card["descricao"]
    assert any(linha["estado"] == "sem-registro" for linha in home["fila"])
    assert (
        Competencia.objects.count(),
        RegistroAuditoria.objects.count(),
        LancamentoContabil.objects.count(),
    ) == antes


def test_plano_inativo_continua_existente_e_conjuntos_se_sobrepoem(client, cenario):
    _plano(cenario["empresa"], ativa=False)
    for empresa in (cenario["empresa"], cenario["segunda"]):
        Competencia.objects.create(empresa=empresa, ano=2026, mes=9)
    resposta = client.get(_url(), {"empresa": "todas", "competencia": "2026-09"})
    carteira = resposta.context["home"]["carteira"]
    assert carteira["cadastradas"] == "2"
    assert carteira["com_pendencia"] == "2"
    assert carteira["setup_incompleto"] == "1"
    assert len(carteira["criticas"]) == 2


def test_bloqueio_base_inteira_e_mesma_regra_single_multi(client, cenario):
    _plano(cenario["empresa"])
    lote = LancamentoContabil.objects.create(
        empresa=cenario["empresa"], data=date(2025, 1, 1), historico="Lote legado sem partidas"
    )
    assert list(
        localizar_lotes_desbalanceados(empresa=cenario["empresa"]).values_list("pk", flat=True)
    ) == [lote.pk]
    assert list(
        localizar_lotes_desbalanceados(
            empresas=[cenario["empresa"], cenario["segunda"]]
        ).values_list("pk", flat=True)
    ) == [lote.pk]
    with pytest.raises(ValueError):
        localizar_lotes_desbalanceados(empresa=cenario["empresa"], empresas=[cenario["segunda"]])
    resposta = client.get(_url(), {"empresa": "todas", "competencia": "2026-09"})
    home = resposta.context["home"]
    assert home["kpis"][0]["quantidade"] == 1
    assert home["fila"][0]["estado"] == "lotes-desbalanceados"
    assert home["fila"][0]["referencia"] == "Origem: 01/01/2025"
    for card in home["kpis"]:
        lista = client.get(card["url"])
        assert lista.status_code == 200
        assert lista.context["home"]["fila_total"] == card["quantidade"]
        assert all(linha["estado"] == card["estado"] for linha in lista.context["home"]["fila"])


def test_fechada_mostra_historico_reabertura_so_permitida_e_nao_entregue(client, cenario):
    competencia = Competencia.objects.create(
        empresa=cenario["empresa"], ano=2026, mes=9, estado=EstadoCompetencia.ENCERRADA
    )
    parametros = {"empresa": cenario["empresa"].pk, "competencia": "2026-09"}
    home = client.get(_url(), parametros).context["home"]
    assert home["estado"] == "competencia_fechada"
    assert home["fila"][0]["cta"] == "Reabrir"
    assert "ano=2026" in home["fila"][0]["url"]
    competencia.entregue_em = timezone.now()
    competencia.save(update_fields=["entregue_em"])
    home = client.get(_url(), parametros).context["home"]
    assert home["fila"][0]["cta"] == "Ver histórico"
    competencia.entregue_em = None
    competencia.save(update_fields=["entregue_em"])
    cenario["vinculo"].papel = Papel.ANALISTA
    cenario["vinculo"].save(update_fields=["papel"])
    assert client.get(_url(), parametros).context["home"]["fila"][0]["cta"] == "Ver histórico"


def test_carteira_mista_prioriza_trabalho_e_mantem_historico_por_empresa(client, cenario):
    Competencia.objects.create(empresa=cenario["empresa"], ano=2026, mes=9)
    Competencia.objects.create(
        empresa=cenario["segunda"], ano=2026, mes=9, estado=EstadoCompetencia.ENCERRADA
    )
    home = client.get(_url(), {"empresa": "todas", "competencia": "2026-09"}).context["home"]
    assert home["estado"] != "competencia_fechada"
    assert home["fila"][0]["estado"] == "competencias-abertas"
    assert home["fila"][-1]["historico"]


def test_troca_para_livro_caixa_nao_amplia_empresa_incompativel(client, cenario):
    client.get(_url(), {"empresa": cenario["empresa"].pk, "competencia": "2026-09"})
    resposta = client.get(_url("livro-caixa"))
    assert resposta.context["home"]["estado"] == "inaplicavel"
    assert resposta.context["home"]["filtros"]["empresa"] == str(cenario["empresa"].pk)
    assert not resposta.context["home"]["kpis"]


def test_livro_caixa_nao_inventa_fechamento_ou_valores(client, cenario):
    empresa = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Ana Livro Caixa",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="52998224725",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    ContaLivroCaixa.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Honorários",
        natureza="receita",
        codigo_carne_leao="R01.001.001",
        ativa=False,
    )
    home = client.get(
        _url("livro-caixa"), {"empresa": empresa.pk, "competencia": "2026-09"}
    ).context["home"]
    assert len(home["kpis"]) == 2
    assert home["kpis"][0]["quantidade"] == 0
    assert home["kpis"][1]["quantidade"] == 1
    assert "ausência de movimento não prova pendência" in home["fila"][0]["motivo"]
    assert "R$" not in str(home)
    assert all("fechamento" not in atalho["url"] for atalho in home["atalhos"])


@pytest.mark.parametrize("modulo", ["financeiro", "folha"])
def test_modulo_planejado_sem_dados_ou_acoes_ficticias(client, cenario, modulo):
    home = client.get(_url(modulo), {"empresa": "todas", "competencia": "2026-09"}).context["home"]
    assert home["estado"] == "indisponivel"
    assert home["kpis"] == [] and home["carteira"] is None and home["fila"] == []
    assert home["novos"] == [] and home["acoes"] == []


def test_fiscal_recusa_sem_empresa_nunca_vira_pendencia_da_empresa(client, cenario):
    lote = LoteDeRecepcao.objects.create(
        escritorio=cenario["escritorio"],
        usuario=cenario["usuario"],
        nome_arquivo="envio.zip",
        sha256_arquivo="a" * 64,
        tamanho_bytes=10,
        total_recusados=1,
    )
    LoteDeRecepcao.objects.filter(pk=lote.pk).update(
        criado_em=timezone.make_aware(datetime(2026, 9, 12))
    )
    ResultadoDoArquivo.objects.create(
        lote=lote, caminho_no_zip="recusada.xml", resultado="recusado", motivo="XML inválido"
    )
    home_empresa = client.get(
        _url("fiscal"), {"empresa": cenario["empresa"].pk, "competencia": "2026-09"}
    ).context["home"]
    assert all(card["estado"] != "arquivos-recusados" for card in home_empresa["kpis"])
    home_todas = client.get(_url("fiscal"), {"empresa": "todas"}).context["home"]
    assert home_todas["kpis"][0]["quantidade"] == 1
    assert home_todas["fila"][0]["empresa_id"] is None
    assert home_todas["carteira"]["com_pendencia"] == "—"
    assert home_todas["carteira"]["setup_incompleto"] == "—"
    assert "Envios em set/2026" in home_todas["kpis"][0]["descricao"]
    for card in home_todas["kpis"]:
        assert client.get(card["url"]).context["home"]["fila_total"] == card["quantidade"]


@pytest.mark.parametrize("entrada", ["default", "todas"])
@pytest.mark.parametrize("papel", [Papel.GESTOR, Papel.PARALEGAL])
def test_fiscal_sem_clientes_mostra_ocorrencias_da_recepcao_real(
    client, cenario, entrada, papel, monkeypatch
):
    instante = timezone.make_aware(datetime(2026, 9, 15, 12))
    monkeypatch.setattr(timezone, "now", lambda: instante)
    vazio = _escritorio_sem_empresas(client, cenario, papel=papel)
    recusa = _receber(vazio, b"<xml quebrado", "recusa-do-escritorio.xml")
    evento = _receber(vazio, xml_evento(chave_nfse="9" * 50), "evento-sem-cliente.xml")
    _receber({**cenario, "escritorio": cenario["outro"]}, b"<outro quebrado", "recusa-alheia.xml")
    _receber(
        {**cenario, "escritorio": cenario["outro"]},
        xml_evento(chave_nfse="8" * 50),
        "evento-alheio.xml",
    )
    assert recusa.total_recusados == 1
    assert evento.total_recusados == 0
    assert not Empresa.objects.filter(escritorio=vazio["escritorio"]).exists()
    assert EventoFiscal.objects.get(escritorio=vazio["escritorio"]).empresa_id is None
    antes = (
        LoteDeRecepcao.objects.count(),
        ResultadoDoArquivo.objects.count(),
        EventoFiscal.objects.count(),
        RegistroAuditoria.objects.count(),
    )
    parametros = {"competencia": f"{timezone.localdate():%Y-%m}"}
    if entrada == "todas":
        parametros["empresa"] = "todas"
    resposta = client.get(_url("fiscal"), parametros)
    assert resposta.status_code == 200
    home = resposta.context["home"]
    assert home["filtros"]["empresa"] == "todas"
    assert home["filtros"]["empresas_ids"] == []
    assert home["carteira"]["cadastradas"] == "0"
    assert home["carteira"]["ativas"] == "0"
    assert home["carteira"]["com_pendencia"] == "—"
    assert home["carteira"]["criticas"] == []
    cards = {card["estado"]: card for card in home["kpis"]}
    assert cards["eventos-sem-nota"]["quantidade"] == 1
    assert cards["notas-canceladas"]["quantidade"] == 0
    if papel == Papel.GESTOR:
        assert cards["arquivos-recusados"]["quantidade"] == 1
        assert (
            client.get(reverse("fiscal_web:relatorio_envio", args=[recusa.pk])).status_code == 200
        )
    else:
        assert "arquivos-recusados" not in cards
        assert all("recepcao" not in atalho["url"] for atalho in home["atalhos"])
        assert (
            client.get(reverse("fiscal_web:relatorio_envio", args=[recusa.pk])).status_code == 403
        )
        assert (
            client.get(
                _url("fiscal", lista=True), {**parametros, "estado": "arquivos-recusados"}
            ).status_code
            == 400
        )
    for card in home["kpis"]:
        lista = client.get(card["url"])
        assert lista.status_code == 200
        assert lista.context["home"]["fila_total"] == card["quantidade"]
        assert all(linha["estado"] == card["estado"] for linha in lista.context["home"]["fila"])
    assert home["fila_total"] == (2 if papel == Papel.GESTOR else 1)
    assert all(linha["empresa_id"] is None for linha in home["fila"])
    assert all(linha["empresa_nome"] == "Empresa não identificada" for linha in home["fila"])
    assert all(client.get(linha["url"]).status_code == 200 for linha in home["fila"])
    html = resposta.content.decode()
    assert "recusa-alheia.xml" not in html
    assert cenario["alheia"].razao_social not in html
    assert "8" * 50 not in html
    assert "R$" not in html
    assert (
        LoteDeRecepcao.objects.count(),
        ResultadoDoArquivo.objects.count(),
        EventoFiscal.objects.count(),
        RegistroAuditoria.objects.count(),
    ) == antes


@pytest.mark.parametrize(
    "situacao", ["disponivel", "sem_empresas", "fiscal_sem_empresas", "inaplicavel", "indisponivel"]
)
def test_estado_desconhecido_retornando400_em_todos_os_caminhos(client, cenario, situacao):
    modulo = "contabilidade"
    parametros = {"empresa": str(cenario["empresa"].pk), "estado": "nao-existe"}
    if situacao in {"sem_empresas", "fiscal_sem_empresas"}:
        _escritorio_sem_empresas(client, cenario)
        parametros["empresa"] = "todas"
        if situacao == "fiscal_sem_empresas":
            modulo = "fiscal"
    elif situacao == "inaplicavel":
        modulo = "livro-caixa"
    elif situacao == "indisponivel":
        modulo = "financeiro"
    resposta = client.get(_url(modulo, lista=True), parametros)
    assert resposta.status_code == 400
    assert resposta.context["home"]["estado"] == "filtro_invalido"
    assert cenario["empresa"].razao_social not in resposta.content.decode()
    assert "nao-existe" not in resposta.content.decode()


@pytest.mark.parametrize("modulo", ["contabilidade", "fiscal", "livro-caixa", "financeiro"])
def test_pagina_inexistente_retornando404_tambem_sem_empresas(client, cenario, modulo):
    _escritorio_sem_empresas(client, cenario)
    resposta = client.get(_url(modulo, lista=True), {"empresa": "todas", "pagina": "2"})
    assert resposta.status_code == 404


@pytest.mark.parametrize("pagina", ["0", "-1", "abc", "9" * 5000])
def test_pagina_malformada_retornando400_sem_apuracao(client, cenario, pagina):
    resposta = client.get(_url("financeiro", lista=True), {"pagina": pagina})
    assert resposta.status_code == 400


def test_paralegal_fiscal_nao_recebe_dados_de_envio_restrito(client, cenario):
    cenario["vinculo"].papel = Papel.PARALEGAL
    cenario["vinculo"].save(update_fields=["papel"])
    home = client.get(_url("fiscal"), {"empresa": "todas", "competencia": "2026-09"}).context[
        "home"
    ]
    assert all(card["estado"] != "arquivos-recusados" for card in home["kpis"])
    assert all("recepcao" not in atalho["url"] for atalho in home["atalhos"])
    assert (
        client.get(_url("fiscal", lista=True), {"estado": "arquivos-recusados"}).status_code == 400
    )


def test_fiscal_evento_orfao_usa_recepcao_e_nota_cancelada_usa_competencia(client, cenario):
    _receber(
        cenario,
        xml_nfse(
            prestador_documento=cenario["empresa"].cnpj,
            tomador_documento=cenario["segunda"].cnpj,
        ),
    )
    documento = DocumentoFiscal.objects.get()
    DocumentoFiscal.objects.filter(pk=documento.pk).update(d_competencia=date(2026, 9, 1))
    _receber(cenario, xml_evento(chave_nfse=documento.identificador[3:]), "cancelamento.xml")
    _receber(cenario, xml_evento(chave_nfse="9" * 50), "orfao.xml")
    EventoFiscal.objects.update(criado_em=timezone.make_aware(datetime(2026, 9, 15)))
    home = client.get(_url("fiscal"), {"empresa": "todas", "competencia": "2026-09"}).context[
        "home"
    ]
    cards = {card["estado"]: card for card in home["kpis"]}
    assert cards["eventos-sem-nota"]["quantidade"] == 1
    assert cards["notas-canceladas"]["quantidade"] == 1
    assert "não competência da nota" in cards["eventos-sem-nota"]["descricao"]
    assert "cancelamento não é uma pendência aberta" in cards["notas-canceladas"]["descricao"]
    assert home["fila"][-1]["historico"]
    # A mesma nota vinculada aos dois clientes conta UMA vez na carteira.
    assert sum(linha["estado"] == "notas-canceladas" for linha in home["fila"]) == 1


def test_consultas_nao_crescem_com_carteira_e_fila_pagina_no_servidor(client, cenario):
    for indice in range(30):
        empresa = Empresa.objects.create(
            escritorio=cenario["escritorio"],
            razao_social=f"Cliente {indice:02d}",
            cnpj=f"{indice + 100000000000:012d}99",
        )
        Competencia.objects.create(empresa=empresa, ano=2026, mes=9)
    request = _request(cenario, {"empresa": "todas", "competencia": "2026-09"})
    with CaptureQueriesContext(connection) as consultas:
        escopo = resolver_escopo(request, "contabilidade")
        home = montar_home(request, escopo)
    assert len(consultas) <= 9
    assert len(home["fila"]) == 8
    resposta = client.get(
        _url(lista=True),
        {"empresa": "todas", "competencia": "2026-09", "estado": "competencias-abertas"},
    )
    lista = resposta.context["home"]
    assert lista["fila_total"] == 30
    assert len(lista["fila"]) == 25
    proxima = client.get(lista["paginacao"]["proxima_url"])
    assert len(proxima.context["home"]["fila"]) == 5
    assert {linha["empresa_id"] for linha in lista["fila"]}.isdisjoint(
        {linha["empresa_id"] for linha in proxima.context["home"]["fila"]}
    )


def test_contexto_menu_sem_consultas_plural_e_preserva_parametros(cenario):
    request = _request(cenario, {})
    request.session[SESSION_KEY] = {
        "escritorio_id": cenario["escritorio"].pk,
        "empresa": "grupo",
        "empresas": [str(cenario["empresa"].pk)],
        "competencia": "2024-02",
    }
    with CaptureQueriesContext(connection) as consultas:
        menu = menu_modulos(request)
    assert len(consultas) == 0
    assert all("nome" not in item for item in menu)
    parametros = parse_qs(urlsplit(menu[1]["url"]).query)
    assert parametros["competencia"] == ["2024-02"]
    assert parametros["empresa"] == ["grupo"]
    with override_settings(ROOT_URLCONF="apps.empresas.urls"):
        assert menu_modulos(request) == []


def test_tiles_do_inicio_abrem_home_e_preservam_filtros(client, cenario):
    client.get(_url(), {"empresa": cenario["segunda"].pk, "competencia": "2024-02"})
    resposta = client.get(reverse("tenancy:painel"))
    modulos = {modulo["chave"]: modulo for modulo in resposta.context["modulos"]}
    for slug in ("contabilidade", "fiscal"):
        destino = modulos[slug]["url"]
        assert urlsplit(destino).path == _url(slug)
        filtros = parse_qs(urlsplit(destino).query)
        assert filtros["empresa"] == [str(cenario["segunda"].pk)]
        assert filtros["competencia"] == ["2024-02"]


@pytest.mark.parametrize("escopo", ["todas", "grupo", "uma"])
def test_seletor_nativo_tem_uma_opcao_selecionada_e_preserva_escopo(client, cenario, escopo):
    """Reenviar filtros não pode transformar carteira em sua última empresa."""

    class SelecaoDaEmpresa(HTMLParser):
        def __init__(self):
            super().__init__()
            self.no_select = False
            self.selecionadas = []

        def handle_starttag(self, tag, attrs):
            atributos = dict(attrs)
            if tag == "select":
                self.no_select = atributos.get("id") == "mh-company"
            if tag == "option" and self.no_select and "selected" in atributos:
                self.selecionadas.append(atributos.get("value"))

        def handle_endtag(self, tag):
            if tag == "select":
                self.no_select = False

    parametros = {"empresa": escopo, "competencia": "2026-09"}
    if escopo == "grupo":
        parametros["empresas"] = [cenario["empresa"].pk, cenario["segunda"].pk]
    elif escopo == "uma":
        parametros["empresa"] = str(cenario["empresa"].pk)
    resposta = client.get(_url(), parametros)
    parser = SelecaoDaEmpresa()
    parser.feed(resposta.content.decode())
    assert parser.selecionadas == [parametros["empresa"]]
    # Valores enviados pelo select HTML real mantêm a mesma carteira.
    parametros["empresa"] = parser.selecionadas[0]
    reaplicada = client.get(_url(), parametros)
    assert (
        reaplicada.context["home"]["filtros"]["empresa"]
        == resposta.context["home"]["filtros"]["empresa"]
    )
    assert (
        reaplicada.context["home"]["carteira"]["cadastradas"]
        == resposta.context["home"]["carteira"]["cadastradas"]
    )


@pytest.mark.parametrize(
    "modulo", ["contabilidade", "fiscal", "livro-caixa", "financeiro", "folha"]
)
@pytest.mark.parametrize("lista", [False, True])
def test_homes_compartilhadas_tem_moldura_acessivel(client, cenario, modulo, lista):
    """Cobertura REAL das duas rotas HTML no inventário compartilhado.

    A home e a lista são consultas da carteira, inclusive nos estados
    indisponíveis. Reaproveitam a mesma moldura e nunca se apresentam
    como demonstração contábil ou documento emitido ao cliente.
    """
    from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
        assert_moldura_acessivel,
    )

    Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Cliente Livro-caixa Acessível",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="52998224725",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    resposta = client.get(_url(modulo, lista=lista), {"empresa": "todas", "competencia": "2026-09"})
    assert resposta.status_code == 200
    template = "core/module_queue.html" if lista else "core/module_home.html"
    assert template in [item.name for item in resposta.templates]
    html = resposta.content.decode()
    assert_moldura_acessivel(html)
    assert 'class="timbre-impressao"' not in html
    assert 'class="identificacao-do-documento"' not in html
