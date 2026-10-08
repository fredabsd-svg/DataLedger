"""Telas da importação de lançamentos com área de conferência (DL-077, fatia 3, frente B).

Chamadas reais pelo cliente HTTP, com sessão autenticada: o mesmo caminho do contador. Dados
SINTÉTICOS: escritórios, empresas e CNPJs fictícios, contas do plano de `cenario_dl077_exportacao`
e valores redondos. Nenhum arquivo real entra aqui.

As contagens, os totais e os históricos esperados foram DERIVADOS À MÃO de cada arquivo de amostra,
antes de rodar (ver os comentários junto de cada amostra). Quando a saída diverge do esperado, a
divergência é investigada, não copiada para o teste.

Permissões (as da API): receber, de-para, avisos, reconferir, efetivar e descartar exigem
`PodeEscriturar` (ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO). Ler a importação exige a leitura da
contabilidade, e PARALEGAL lê e não age. CLIENTE não passa em nenhuma rota.
"""

import io
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from openpyxl import Workbook

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.intercambio.canonico import NIVEL_AVISO
from apps.contabilidade.intercambio.formatos import excel_lancamentos
from apps.contabilidade.intercambio.formatos.excel_lancamentos import NOME_DA_ABA
from apps.contabilidade.intercambio.formatos.proprio_lancamentos_leitura import (
    CABECALHO_LANCAMENTOS,
)
from apps.contabilidade.models import (
    Conta,
    DeParaConta,
    EstadoImportacaoLancamentos,
    ImportacaoLancamentos,
    LancamentoContabil,
    LancamentoImportado,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import encerrar_competencia
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_pagina_acessivel
from apps.contabilidade.views_web import (
    FORMATOS_DE_IMPORTACAO_DE_LANCAMENTOS_NA_TELA,
    MENSAGEM_CONFIRMACAO_DA_EFETIVACAO,
    POLITICAS_DE_EFETIVACAO_NA_TELA,
)
from apps.core.context_processors import ROTULOS_DE_TELA
from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.services import MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CNPJ_DE_OUTRO_ESCRITORIO = "88888888000188"  # sintético

# ---------------------------------------------------------------------------
# Arquivos de amostra. Um lançamento por número, com as mesmas três situações em todos os formatos:
#   1 — pronto: débito e crédito com o mesmo histórico, contas que existem no plano.
#   2 — aviso: o débito e o crédito trazem históricos diferentes ("Compra à vista" e "Pagamento").
#   3 — erro: a conta 9.9 não existe no plano (e, no sistema de referência, nenhum código existe).
# Total: 100,00 + 50,00 + 30,00 = 180,00 de débito, e o mesmo de crédito.
# ---------------------------------------------------------------------------

ECD = (
    f"|0000|LECD|01012026|31012026|Empresa Sintetica Ltda|{CNPJ_DA_EMPRESA}|SP|||\r\n"
    "|I200|1|10012026|100,00|N||\r\n"
    "|I250|1.1.1||100,00|D|||Compra de material||\r\n"
    "|I250|2.1||100,00|C|||Compra de material||\r\n"
    "|I200|2|11012026|50,00|N||\r\n"
    "|I250|1.1.1||50,00|D|||Compra à vista||\r\n"
    "|I250|2.1||50,00|C|||Pagamento||\r\n"
    "|I200|3|12012026|30,00|N||\r\n"
    "|I250|9.9||30,00|D|||Aluguel de janeiro||\r\n"
    "|I250|1.1.2||30,00|C|||Aluguel de janeiro||\r\n"
).encode("iso-8859-1")

# Só o lançamento 1 (pronto): para os testes que precisam de uma efetivação possível (tudo ou nada).
PROPRIO_LIMPO = (
    "numero;data;historico;conta;lado;valor\r\n"
    "1;2026-01-10;Compra de material;1.1.1;D;100.00\r\n"
    "1;2026-01-10;Compra de material;2.1;C;100.00\r\n"
).encode("utf-8")

PROPRIO = (
    "numero;data;historico;conta;lado;valor\r\n"
    "1;2026-01-10;Compra de material;1.1.1;D;100.00\r\n"
    "1;2026-01-10;Compra de material;2.1;C;100.00\r\n"
    "2;2026-01-11;Compra à vista;1.1.1;D;50.00\r\n"
    "2;2026-01-11;Pagamento;2.1;C;50.00\r\n"
    "3;2026-01-12;Aluguel de janeiro;9.9;D;30.00\r\n"
    "3;2026-01-12;Aluguel de janeiro;1.1.2;C;30.00\r\n"
).encode("utf-8")

# Sistema de referência: cada 6100 é um lançamento, e o número dele é a LINHA no arquivo (3, 4 e 5).
# Os códigos são REDUZIDOS: nenhum existe no plano, então todos pedem de-para. O 0220 no 6100 da
# linha 4 gera o aviso 6100.6 (o código do histórico não é lido).
REFERENCIA = (
    f"|0000|{CNPJ_DA_EMPRESA}|\r\n"
    "|6000|X||||\r\n"
    "|6100|10/01/2026|11|21|100,00||Compra de material||||\r\n"
    "|6100|11/01/2026|11|21|50,00|0220|Compra à vista||||\r\n"
    "|6100|12/01/2026|7|11|30,00||Aluguel de janeiro||||\r\n"
).encode("iso-8859-1")


def _planilha(linhas):
    """Planilha no modelo: aba `lancamentos`, cabeçalho do formato, conta como texto."""
    pasta = Workbook()
    aba = pasta.active
    aba.title = NOME_DA_ABA
    aba.append(list(CABECALHO_LANCAMENTOS))
    for linha in linhas:
        aba.append(linha)
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


PLANILHA = _planilha(
    [
        [1, date(2026, 1, 10), "Compra de material", "1.1.1", "D", 100.0],
        [1, date(2026, 1, 10), "Compra de material", "2.1", "C", 100.0],
        [2, date(2026, 1, 11), "Compra à vista", "1.1.1", "D", 50.0],
        [2, date(2026, 1, 11), "Pagamento", "2.1", "C", 50.0],
        [3, date(2026, 1, 12), "Aluguel de janeiro", "9.9", "D", 30.0],
        [3, date(2026, 1, 12), "Aluguel de janeiro", "1.1.2", "C", 30.0],
    ]
)

# (formato, arquivo, nome, de-para a fazer, erros antes do de-para, prontos antes do de-para,
#  número do lançamento com aviso, histórico do lançamento com aviso depois de montado).
CASOS_DE_FLUXO = [
    pytest.param(
        "ecd",
        ECD,
        "lancamentos.txt",
        {"9.9": "4.1"},
        1,
        1,
        "2",
        "Compra à vista | Pagamento",
        id="ecd",
    ),
    pytest.param(
        "proprio",
        PROPRIO,
        "lancamentos.txt",
        {"9.9": "4.1"},
        1,
        1,
        "2",
        "Compra à vista | Pagamento",
        id="proprio",
    ),
    pytest.param(
        "excel",
        PLANILHA,
        "lancamentos.xlsx",
        {"9.9": "4.1"},
        1,
        1,
        "2",
        "Compra à vista | Pagamento",
        id="excel",
    ),
    pytest.param(
        "referencia",
        REFERENCIA,
        "lancamentos.txt",
        {"11": "1.1.1", "21": "2.1", "7": "4.1"},
        3,
        0,
        "4",
        "Compra à vista",
        id="referencia",
    ),
]

# O corpo válido de cada ação, para as varreduras de permissão e de estado.
DADOS_DE_ACAO = {
    "lancamentos_importacao_depara": {"codigo_origem": "9.9", "conta": "4.1"},
    "lancamentos_importacao_avisos": {"numeros": ["2"]},
    "lancamentos_importacao_reconferir": {},
    "lancamentos_importacao_efetivar": {"politica": "tudo_ou_nada", "confirmar": "sim"},
    "lancamentos_importacao_descartar": {"motivo": "Arquivo de teste"},
}
ACOES = list(DADOS_DE_ACAO)
ROTAS_SEM_IMPORTACAO = {
    "lancamentos_importacoes",
    "lancamentos_importar",
    "lancamentos_importar_modelo_excel",
}


# ---------------------------------------------------------------------------
# Cenário e helpers
# ---------------------------------------------------------------------------


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario():
    escritorio_a = criar_escritorio("Escritório Telas A", "11111111000111")
    escritorio_b = criar_escritorio("Escritório Telas B", "22222222000122")
    empresa = criar_empresa(
        escritorio=escritorio_a, razao_social="Empresa Telas Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    outra_da_mesma = criar_empresa(
        escritorio=escritorio_a, razao_social="Outra Telas Ltda", cnpj="66666666000166"
    )
    criar_plano(outra_da_mesma)
    # Conta exclusiva da outra empresa: se aparecer na conferência desta, o isolamento falhou.
    Conta.objects.create(
        empresa=outra_da_mesma,
        codigo="8.8",
        nome="Conta Sigilosa da Outra Empresa",
        aceita_lancamento=True,
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    de_outro_escritorio = criar_empresa(
        escritorio=escritorio_b,
        razao_social="Empresa de Outro Escritório Ltda",
        cnpj=CNPJ_DE_OUTRO_ESCRITORIO,
    )
    criar_plano(de_outro_escritorio)
    _usuario("gestor-telas", escritorio_a, Papel.GESTOR)
    _usuario("analista-telas", escritorio_a, Papel.ANALISTA)
    _usuario("financeiro-telas", escritorio_a, Papel.FINANCEIRO)
    _usuario("paralegal-telas", escritorio_a, Papel.PARALEGAL)
    _usuario("cliente-telas", escritorio_a, Papel.CLIENTE)
    _usuario("gestor-outro-escritorio-telas", escritorio_b, Papel.GESTOR)
    return {
        "empresa": empresa,
        "contas": contas,
        "outra_da_mesma": outra_da_mesma,
        "de_outro_escritorio": de_outro_escritorio,
    }


@pytest.fixture
def empresa_livro_caixa(cenario):
    """Mesmo escritório do gestor-telas, empresa em modo livro-caixa (DL-038)."""
    return Empresa.objects.create(
        escritorio=cenario["empresa"].escritorio,
        razao_social="Empresa Livro-Caixa Telas Ltda",
        cnpj="99999999000199",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )


def _entrar(client, username):
    assert client.login(username=username, password=SENHA)


def _url(nome, empresa, *args):
    return reverse(f"contabilidade_web:{nome}", args=[empresa.id, *args])


def _arquivo(conteudo, nome):
    return SimpleUploadedFile(nome, conteudo, content_type="application/octet-stream")


def _enviar(client, empresa, formato, conteudo, nome):
    return client.post(
        _url("lancamentos_importar", empresa),
        {"arquivo": _arquivo(conteudo, nome), "formato": formato},
    )


def _receber_direto(empresa, formato, conteudo, nome="lancamentos.txt"):
    """Recebe pelo serviço, sem a tela: para os testes que não medem o envio."""
    return servico.receber(
        empresa=empresa, formato=formato, conteudo=conteudo, nome_arquivo=nome, usuario=None
    )


def _importacao_de_proprio(empresa):
    return _receber_direto(empresa, "proprio", PROPRIO)


def _importacao_limpa(empresa):
    return _receber_direto(empresa, "proprio", PROPRIO_LIMPO)


def _ultima_importacao(empresa):
    return ImportacaoLancamentos.objects.filter(empresa=empresa).order_by("-id").first()


def _conferencia(client, empresa, importacao, **params):
    return client.get(_url("lancamentos_importacao", empresa, importacao.id), params or None)


def _agir(client, empresa, importacao, nome, dados=None):
    corpo = DADOS_DE_ACAO[nome] if dados is None else dados
    return client.post(_url(nome, empresa, importacao.id), corpo)


def _chamar(client, empresa, nome, metodo, importacao):
    """Uma rota qualquer das telas, com um corpo válido quando ela recebe um."""
    args = [] if nome in ROTAS_SEM_IMPORTACAO else [importacao.id]
    url = _url(nome, empresa, *args)
    if metodo == "GET":
        return client.get(url)
    if nome == "lancamentos_importar":
        return client.post(url, {"formato": "proprio", "arquivo": _arquivo(PROPRIO, "x.txt")})
    return client.post(url, DADOS_DE_ACAO[nome])


def _lancamentos_no_diario(empresa):
    return LancamentoContabil.objects.filter(empresa=empresa)


def _total_debito(empresa):
    return sum(
        (
            item.valor
            for lancamento in _lancamentos_no_diario(empresa)
            for item in lancamento.itens.all()
            if item.tipo == TipoPartida.DEBITO
        ),
        Decimal("0.00"),
    )


def _estado(importacao):
    importacao.refresh_from_db()
    return importacao.estado


def _foto_do_que_grava(empresa):
    """Contagens do que pode mudar com uma ação recusada. Ação recusada não pode mudar nenhuma."""
    return (
        _lancamentos_no_diario(empresa).count(),
        DeParaConta.objects.filter(empresa=empresa).count(),
        ImportacaoLancamentos.objects.filter(empresa=empresa).count(),
        LancamentoImportado.objects.filter(
            importacao__empresa=empresa, lancamento__isnull=False
        ).count(),
    )


def _aceitar_o_arquivo_se_preciso(client, empresa, importacao):
    """A11: arquivo sem empresa declarada pede o aceite do aviso do arquivo antes de efetivar.

    Dá o passo que o contador dá na tela (o formulário de aceite da conferência).
    """
    importacao.refresh_from_db()
    if importacao.exige_aceite_do_arquivo and not importacao.aceite_do_arquivo:
        resposta = _agir(
            client,
            empresa,
            importacao,
            "lancamentos_importacao_avisos",
            {"aceitar_arquivo": "1"},
        )
        assert resposta.status_code == 302, resposta.content.decode()


def _efetivar_com_so_validos(client, empresa, importacao):
    """Pede a política parcial. Ela está suspensa (BL-676): o servidor responde 400."""
    return _agir(
        client,
        empresa,
        importacao,
        "lancamentos_importacao_efetivar",
        {"politica": "so_validos", "confirmar": "sim"},
    )


def _efetivar_tudo_ou_nada(client, empresa, importacao):
    return _agir(
        client,
        empresa,
        importacao,
        "lancamentos_importacao_efetivar",
        {"politica": "tudo_ou_nada", "confirmar": "sim"},
    )


# ---------------------------------------------------------------------------
# Fluxo completo, por formato: do envio ao Diário
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "formato,conteudo,nome,de_para,erros_antes,prontos_antes,numero_do_aviso,historico_do_aviso",
    CASOS_DE_FLUXO,
)
def test_fluxo_completo_por_formato_do_envio_ao_diario(
    client,
    cenario,
    formato,
    conteudo,
    nome,
    de_para,
    erros_antes,
    prontos_antes,
    numero_do_aviso,
    historico_do_aviso,
):
    empresa = cenario["empresa"]
    _entrar(client, "gestor-telas")

    envio = _enviar(client, empresa, formato, conteudo, nome)

    assert envio.status_code == 302, envio.content.decode()
    importacao = _ultima_importacao(empresa)
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert _lancamentos_no_diario(empresa).count() == 0, "o envio não pode gravar no Diário"

    # Contagens escritas à mão: 3 lançamentos; 1 com aviso (o 2, ou o 4 no sistema de referência).
    # Erro: 1 (o 3, pela conta 9.9), e no sistema de referência os 3, porque nenhum código existe.
    antes = _conferencia(client, empresa, importacao)
    assert antes.status_code == 200
    assert antes.context["contagens"]["total"] == 3
    assert antes.context["contagens"]["com_erro"] == erros_antes
    assert antes.context["contagens"]["com_aviso_a_aceitar"] == 1
    assert antes.context["contagens"]["prontos"] == prontos_antes
    assert [item["codigo"] for item in antes.context["codigos_sem_conta"]] == sorted(de_para)

    # De-para de cada código, escolhido na lista de contas analíticas ativas da própria tela.
    for codigo, conta in de_para.items():
        resposta = client.post(
            _url("lancamentos_importacao_depara", empresa, importacao.id),
            {"codigo_origem": codigo, "conta": conta},
        )
        assert resposta.status_code == 302, resposta.content.decode()
    assert DeParaConta.objects.filter(empresa=empresa, formato=formato).count() == len(de_para)

    # Depois do de-para, a conferência refeita já não tem erro: o aviso e o pronto são o que sobra.
    depois = _conferencia(client, empresa, importacao)
    assert depois.context["contagens"]["com_erro"] == 0
    assert depois.context["contagens"]["com_aviso_a_aceitar"] == 1
    assert depois.context["contagens"]["prontos"] == 2
    assert depois.context["codigos_sem_conta"] == []

    assert (
        _agir(client, empresa, importacao, "lancamentos_importacao_reconferir").status_code == 302
    )

    aviso = _agir(
        client, empresa, importacao, "lancamentos_importacao_avisos", {"numeros": [numero_do_aviso]}
    )
    assert aviso.status_code == 302
    apos_aviso = _conferencia(client, empresa, importacao)
    assert apos_aviso.context["contagens"]["com_aviso_a_aceitar"] == 0
    assert apos_aviso.context["contagens"]["prontos"] == 3

    _aceitar_o_arquivo_se_preciso(client, empresa, importacao)
    efetivacao = _agir(client, empresa, importacao, "lancamentos_importacao_efetivar")
    assert efetivacao.status_code == 302, efetivacao.content.decode()

    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EFETIVADA
    assert importacao.quantidade_efetivados == 3
    assert importacao.quantidade_nao_efetivados == 0
    assert _lancamentos_no_diario(empresa).count() == 3
    assert _total_debito(empresa) == Decimal("180.00")
    lancamento_do_aviso = LancamentoImportado.objects.get(
        importacao=importacao, numero_origem=numero_do_aviso
    ).lancamento
    assert lancamento_do_aviso.historico == historico_do_aviso

    tela = _conferencia(client, empresa, importacao)
    assert tela.status_code == 200
    html = tela.content.decode()
    assert "Esta importação está efetivada" in html
    assert (
        reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, lancamento_do_aviso.id])
        in html
    )
    assert RegistroAuditoria.objects.filter(
        acao="lancamentos.importacao.efetivada", objeto_id=str(importacao.id)
    ).exists()


# ---------------------------------------------------------------------------
# Envio: recusas do formulário, sem gravar nada
# ---------------------------------------------------------------------------


def test_formato_desconhecido_e_recusado_na_tela_sem_importacao(client, cenario):
    _entrar(client, "gestor-telas")

    resposta = _enviar(client, cenario["empresa"], "xpto", PROPRIO, "a.txt")

    assert resposta.status_code == 400
    assert "Escolha o formato do arquivo." in resposta.content.decode()
    assert _ultima_importacao(cenario["empresa"]) is None


def test_planilha_com_extensao_xlsm_e_recusada_com_mensagem(client, cenario):
    _entrar(client, "gestor-telas")

    resposta = _enviar(client, cenario["empresa"], "excel", PLANILHA, "lanc.xlsm")

    assert resposta.status_code == 400
    assert "não é aceito" in resposta.content.decode()
    assert _ultima_importacao(cenario["empresa"]) is None


def test_arquivo_com_cnpj_de_outra_empresa_e_recusado_sem_mostrar_os_numeros(client, cenario):
    _entrar(client, "gestor-telas")
    de_outra = REFERENCIA.replace(
        CNPJ_DA_EMPRESA.encode("ascii"), CNPJ_DE_OUTRO_ESCRITORIO.encode("ascii")
    )

    resposta = _enviar(client, cenario["empresa"], "referencia", de_outra, "outra.txt")

    html = resposta.content.decode()
    assert resposta.status_code == 400
    assert "declara CNPJ/CPF diferente" in html
    assert CNPJ_DE_OUTRO_ESCRITORIO not in html
    assert _ultima_importacao(cenario["empresa"]) is None


def test_mesmo_arquivo_recebido_de_novo_e_recusado_com_link_para_a_existente(client, cenario):
    empresa = cenario["empresa"]
    _entrar(client, "gestor-telas")
    primeira = _enviar(client, empresa, "proprio", PROPRIO, "lancamentos.txt")
    assert primeira.status_code == 302
    existente = _ultima_importacao(empresa)

    segunda = _enviar(client, empresa, "proprio", PROPRIO, "lancamentos.txt")

    html = segunda.content.decode()
    assert segunda.status_code == 409
    assert ImportacaoLancamentos.objects.filter(empresa=empresa).count() == 1
    assert (
        reverse("contabilidade_web:lancamentos_importacao", args=[empresa.id, existente.id]) in html
    )


# ---------------------------------------------------------------------------
# Efetivação: tudo ou nada (o só os válidos está suspenso, BL-676), confirmação e política
# ---------------------------------------------------------------------------


def test_efetivar_tudo_com_erro_e_recusado_e_nada_e_gravado(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")
    antes = _foto_do_que_grava(empresa)

    _aceitar_o_arquivo_se_preciso(client, empresa, importacao)
    resposta = _agir(client, empresa, importacao, "lancamentos_importacao_efetivar")

    html = resposta.content.decode()
    assert resposta.status_code == 400
    assert "nada foi gravado" in html
    assert {item["numero"] for item in resposta.context["bloqueios"]} == {"2", "3"}
    assert _foto_do_que_grava(empresa) == antes
    assert _estado(importacao) == EstadoImportacaoLancamentos.EM_CONFERENCIA


def test_so_validos_e_recusado_pela_suspensao_e_nada_entra_no_diario(client, cenario):
    """BL-676: a efetivação parcial está suspensa. Antes, gravava só o pronto (1) e listava os
    de fora (2 e 3). Agora a recusa vem nomeada, nada entra no Diário e a importação segue em
    conferência."""
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")
    _aceitar_o_arquivo_se_preciso(client, empresa, importacao)

    resposta = _efetivar_com_so_validos(client, empresa, importacao)

    assert resposta.status_code == 400, resposta.content.decode()
    assert "suspensa" in resposta.content.decode()
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert importacao.politica_de_efetivacao == ""
    assert _lancamentos_no_diario(empresa).count() == 0


def test_botao_de_efetivar_tudo_nao_aparece_habilitado_com_erro_pendente(client, cenario):
    """Mutante-alvo: se a tela oferecer a política tudo ou nada com erro pendente, esta falha."""
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")
    _aceitar_o_arquivo_se_preciso(client, empresa, importacao)

    html = _conferencia(client, empresa, importacao).content.decode()

    assert 'value="tudo_ou_nada"' not in html, "formulário de efetivar tudo com erro pendente"
    assert "Efetivar tudo ou nada (indisponível)" in html
    assert "Não é possível efetivar tudo" in html
    assert 'value="so_validos"' not in html, "a tela ofereceu a efetivação parcial suspensa"


def test_botao_de_efetivar_tudo_aparece_quando_a_politica_e_possivel(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")
    _agir(
        client,
        empresa,
        importacao,
        "lancamentos_importacao_depara",
        {"codigo_origem": "9.9", "conta": "4.1"},
    )
    _agir(client, empresa, importacao, "lancamentos_importacao_avisos", {"numeros": ["2"]})
    _aceitar_o_arquivo_se_preciso(client, empresa, importacao)

    html = _conferencia(client, empresa, importacao).content.decode()

    assert 'value="tudo_ou_nada"' in html
    assert "Efetivar 3 lançamentos (tudo ou nada)" in html


def test_efetivar_sem_a_confirmacao_explicita_e_recusado(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")
    antes = _foto_do_que_grava(empresa)

    resposta = client.post(
        _url("lancamentos_importacao_efetivar", empresa, importacao.id),
        {"politica": "so_validos"},
    )

    assert resposta.status_code == 400
    assert MENSAGEM_CONFIRMACAO_DA_EFETIVACAO in resposta.content.decode()
    assert _foto_do_que_grava(empresa) == antes


def test_politica_que_nao_existe_e_recusada_sem_gravar(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")
    antes = _foto_do_que_grava(empresa)

    resposta = _agir(
        client,
        empresa,
        importacao,
        "lancamentos_importacao_efetivar",
        {"politica": "metade", "confirmar": "sim"},
    )

    assert resposta.status_code == 400
    # O Django escapa o apóstrofo da mensagem (&#x27;): a asserção confere só o trecho sem aspas.
    assert "desconhecida" in resposta.content.decode()
    assert _foto_do_que_grava(empresa) == antes


def test_reconferir_depois_de_encerrar_a_competencia_acusa_o_erro(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")
    assert _conferencia(client, empresa, importacao).context["contagens"]["com_erro"] == 1

    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=None)
    resposta = _agir(client, empresa, importacao, "lancamentos_importacao_reconferir")

    assert resposta.status_code == 302
    # As três datas são de janeiro de 2026: com a competência encerrada, nenhuma entra.
    assert _conferencia(client, empresa, importacao).context["contagens"]["com_erro"] == 3


# ---------------------------------------------------------------------------
# De-para, avisos e descarte
# ---------------------------------------------------------------------------


def test_depara_com_conta_de_outra_empresa_ou_sintetica_e_recusado(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    outra_conta = Conta.objects.get(empresa=cenario["outra_da_mesma"], codigo="8.8")
    _entrar(client, "gestor-telas")
    antes = _foto_do_que_grava(empresa)

    de_outra = client.post(
        _url("lancamentos_importacao_depara", empresa, importacao.id),
        {"codigo_origem": "9.9", "conta": outra_conta.codigo},
    )
    sintetica = client.post(
        _url("lancamentos_importacao_depara", empresa, importacao.id),
        {"codigo_origem": "9.9", "conta": "1.1"},
    )

    assert de_outra.status_code == 400
    assert sintetica.status_code == 400
    assert "Nada foi gravado" in de_outra.content.decode()
    assert _foto_do_que_grava(empresa) == antes


def test_avisos_todos_aceitam_os_avisos_pendentes_de_uma_vez(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")

    resposta = client.post(
        _url("lancamentos_importacao_avisos", empresa, importacao.id), {"todos": "1"}
    )

    assert resposta.status_code == 302
    assert (
        _conferencia(client, empresa, importacao).context["contagens"]["com_aviso_a_aceitar"] == 0
    )
    assert LancamentoImportado.objects.get(
        importacao=importacao, numero_origem="2"
    ).aceito_com_aviso


def test_avisos_de_lancamento_sem_aviso_e_recusado(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")

    resposta = _agir(
        client, empresa, importacao, "lancamentos_importacao_avisos", {"numeros": ["1"]}
    )

    assert resposta.status_code == 400
    assert "não têm avisos a aceitar" in resposta.content.decode()
    assert not LancamentoImportado.objects.get(
        importacao=importacao, numero_origem="1"
    ).aceito_com_aviso


def test_descartar_exige_motivo_e_libera_o_arquivo_para_novo_envio(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")

    sem_motivo = _agir(
        client, empresa, importacao, "lancamentos_importacao_descartar", {"motivo": ""}
    )

    assert sem_motivo.status_code == 400
    assert "motivo do descarte é obrigatório" in sem_motivo.content.decode()
    assert _estado(importacao) == EstadoImportacaoLancamentos.EM_CONFERENCIA

    com_motivo = _agir(
        client,
        empresa,
        importacao,
        "lancamentos_importacao_descartar",
        {"motivo": "Arquivo de outro período"},
    )

    assert com_motivo.status_code == 302
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.DESCARTADA
    assert importacao.motivo_do_descarte == "Arquivo de outro período"
    assert _lancamentos_no_diario(empresa).count() == 0
    assert RegistroAuditoria.objects.filter(
        acao="lancamentos.importacao.descartada", objeto_id=str(importacao.id)
    ).exists()
    recebido_de_novo = _enviar(client, empresa, "proprio", PROPRIO, "lancamentos.txt")
    assert recebido_de_novo.status_code == 302
    assert _ultima_importacao(empresa).pk != importacao.pk


# ---------------------------------------------------------------------------
# Estado final: nenhuma ação altera uma importação efetivada ou descartada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "estado",
    [EstadoImportacaoLancamentos.EFETIVADA, EstadoImportacaoLancamentos.DESCARTADA],
    ids=["efetivada", "descartada"],
)
@pytest.mark.parametrize("nome", ACOES)
def test_importacao_fora_da_conferencia_nao_aceita_mais_acao_nenhuma(client, cenario, estado, nome):
    empresa = cenario["empresa"]
    contas = cenario["contas"]
    importacao = _importacao_de_proprio(empresa)
    if estado == EstadoImportacaoLancamentos.EFETIVADA:
        servico.definir_de_para(
            empresa=empresa,
            formato="proprio",
            codigo_origem="9.9",
            conta=contas["4.1"],
            usuario=None,
        )
        servico.reconferir(importacao, usuario=None)
        servico.aceitar_avisos(importacao, ["2"], usuario=None)
        servico.aceitar_avisos(importacao, [], aceitar_arquivo=True, usuario=None)
        servico.efetivar(importacao, politica="tudo_ou_nada", usuario=None)
    else:
        servico.descartar(importacao, motivo="Teste", usuario=None)
    _entrar(client, "gestor-telas")
    antes = _foto_do_que_grava(empresa)

    resposta = _agir(client, empresa, importacao, nome)

    assert resposta.status_code == 409, (nome, resposta.status_code, resposta.content.decode())
    assert _foto_do_que_grava(empresa) == antes
    assert _estado(importacao) == estado


# ---------------------------------------------------------------------------
# Conferência: filtros, paginação e isolamento dos dados que a tela mostra
# ---------------------------------------------------------------------------


def test_filtro_so_com_erro_e_so_com_aviso_mostram_os_lancamentos_certos(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")

    erros = _conferencia(client, empresa, importacao, filtro="erros")
    avisos = _conferencia(client, empresa, importacao, filtro="avisos")

    assert [linha["numero"] for linha in erros.context["lancamentos"]] == ["3"]
    assert [linha["numero"] for linha in avisos.context["lancamentos"]] == ["2"]


def test_filtro_que_nao_existe_e_pagina_que_nao_e_numero_sao_recusados(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")

    filtro_ruim = _conferencia(client, empresa, importacao, filtro="todas")
    pagina_ruim = _conferencia(client, empresa, importacao, pagina="abc")

    assert filtro_ruim.status_code == 400
    assert pagina_ruim.status_code == 400


def test_de_para_da_tela_nao_mostra_conta_de_outra_empresa_do_mesmo_escritorio(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")

    html = _conferencia(client, empresa, importacao).content.decode()

    assert "Conta para o código 9.9" in html
    assert "Conta Sigilosa da Outra Empresa" not in html
    assert "Outra Telas Ltda" not in html


# ---------------------------------------------------------------------------
# Permissões, isolamento, anônimo, livro-caixa e CSRF
# ---------------------------------------------------------------------------

ROTAS = [
    ("lancamentos_importacoes", "GET"),
    ("lancamentos_importar", "GET"),
    ("lancamentos_importar", "POST"),
    ("lancamentos_importar_modelo_excel", "GET"),
    ("lancamentos_importacao", "GET"),
] + [(acao, "POST") for acao in ACOES]


@pytest.mark.parametrize("nome,metodo", ROTAS)
def test_cliente_nao_passa_em_nenhuma_rota_das_importacoes(client, cenario, nome, metodo):
    importacao = _importacao_de_proprio(cenario["empresa"])
    _entrar(client, "cliente-telas")

    resposta = _chamar(client, cenario["empresa"], nome, metodo, importacao)

    assert resposta.status_code == 403
    assert _estado(importacao) == EstadoImportacaoLancamentos.EM_CONFERENCIA


def test_paralegal_le_a_importacao_mas_nao_age(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "paralegal-telas")
    antes = _foto_do_que_grava(empresa)

    lista = client.get(_url("lancamentos_importacoes", empresa))
    tela = _conferencia(client, empresa, importacao)

    assert lista.status_code == 200
    assert tela.status_code == 200
    html = tela.content.decode()
    assert 'name="politica"' not in html
    assert 'name="motivo"' not in html
    assert "Salvar de-para" not in html
    assert "Seu papel lê esta importação" in html
    assert client.get(_url("lancamentos_importar", empresa)).status_code == 403
    assert client.get(_url("lancamentos_importar_modelo_excel", empresa)).status_code == 403
    for acao in ACOES:
        assert _agir(client, empresa, importacao, acao).status_code == 403, acao
    assert _foto_do_que_grava(empresa) == antes
    assert _estado(importacao) == EstadoImportacaoLancamentos.EM_CONFERENCIA


@pytest.mark.parametrize("usuario", ["gestor-telas", "analista-telas", "financeiro-telas"])
def test_quem_escritura_efetiva_a_importacao(client, cenario, usuario):
    empresa = cenario["empresa"]
    importacao = _importacao_limpa(empresa)
    _entrar(client, usuario)
    _aceitar_o_arquivo_se_preciso(client, empresa, importacao)

    resposta = _efetivar_tudo_ou_nada(client, empresa, importacao)

    assert resposta.status_code == 302, resposta.content.decode()
    assert _estado(importacao) == EstadoImportacaoLancamentos.EFETIVADA


@pytest.mark.parametrize("nome,metodo", ROTAS)
def test_empresa_de_outro_escritorio_responde_404_nos_dois_sentidos(client, cenario, nome, metodo):
    importacao = _importacao_de_proprio(cenario["empresa"])
    _entrar(client, "gestor-telas")
    assert (
        _chamar(client, cenario["de_outro_escritorio"], nome, metodo, importacao).status_code == 404
    )
    client.logout()
    _entrar(client, "gestor-outro-escritorio-telas")
    assert _chamar(client, cenario["empresa"], nome, metodo, importacao).status_code == 404


def test_importacao_de_outra_empresa_do_mesmo_escritorio_responde_404_e_nao_muda(client, cenario):
    """Mesmo escritório, empresa errada na URL: a importação da outra não é lida nem agida."""
    importacao_da_outra = _importacao_de_proprio(cenario["outra_da_mesma"])
    _entrar(client, "gestor-telas")
    antes = _foto_do_que_grava(cenario["empresa"])

    leitura = _conferencia(client, cenario["empresa"], importacao_da_outra)
    acao = _agir(client, cenario["empresa"], importacao_da_outra, "lancamentos_importacao_efetivar")

    assert leitura.status_code == 404
    assert acao.status_code == 404
    assert _foto_do_que_grava(cenario["empresa"]) == antes
    assert _estado(importacao_da_outra) == EstadoImportacaoLancamentos.EM_CONFERENCIA


@pytest.mark.parametrize("nome,metodo", ROTAS)
def test_anonimo_vai_para_o_login(client, cenario, nome, metodo):
    importacao = _importacao_de_proprio(cenario["empresa"])

    resposta = _chamar(client, cenario["empresa"], nome, metodo, importacao)

    assert resposta.status_code == 302
    assert "login" in resposta["Location"]


@pytest.mark.parametrize("nome,metodo", ROTAS)
def test_empresa_em_livro_caixa_e_recusada_em_toda_rota(
    client, cenario, empresa_livro_caixa, nome, metodo
):
    importacao = _importacao_de_proprio(cenario["empresa"])
    _entrar(client, "gestor-telas")
    antes = _foto_do_que_grava(cenario["empresa"])

    resposta = _chamar(client, empresa_livro_caixa, nome, metodo, importacao)

    assert resposta.status_code == 403
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode()
    assert _foto_do_que_grava(cenario["empresa"]) == antes


def test_post_sem_token_csrf_e_recusado_no_envio_e_na_efetivacao(cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    cliente = Client(enforce_csrf_checks=True)
    _entrar(cliente, "gestor-telas")
    antes = _foto_do_que_grava(empresa)

    envio = cliente.post(
        _url("lancamentos_importar", empresa),
        {"arquivo": _arquivo(PROPRIO, "a.txt"), "formato": "proprio"},
    )
    efetivacao = cliente.post(
        _url("lancamentos_importacao_efetivar", empresa, importacao.id),
        {"politica": "so_validos", "confirmar": "sim"},
    )

    # 403 por CSRF, não por permissão: o gestor tem o papel, então a recusa é do token.
    assert envio.status_code == 403 and "CSRF" in envio.content.decode()
    assert efetivacao.status_code == 403 and "CSRF" in efetivacao.content.decode()
    assert _foto_do_que_grava(empresa) == antes


# ---------------------------------------------------------------------------
# Acessibilidade: as telas passam pelas mesmas guardas das telas do plano
# ---------------------------------------------------------------------------


def test_telas_da_importacao_passam_as_guardas_de_acessibilidade(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    _entrar(client, "gestor-telas")

    lista = client.get(_url("lancamentos_importacoes", empresa)).content.decode()
    formulario = client.get(_url("lancamentos_importar", empresa)).content.decode()
    conferencia = _conferencia(client, empresa, importacao).content.decode()
    erro = client.post(
        _url("lancamentos_importacao_efetivar", empresa, importacao.id),
        {"politica": "tudo_ou_nada", "confirmar": "sim"},
    ).content.decode()
    recusada = _efetivar_com_so_validos(client, empresa, importacao).content.decode()
    limpa = _importacao_limpa(empresa)
    _aceitar_o_arquivo_se_preciso(client, empresa, limpa)
    _efetivar_tudo_ou_nada(client, empresa, limpa)
    efetivada = _conferencia(client, empresa, limpa).content.decode()

    for html in (lista, formulario, conferencia, erro, recusada, efetivada):
        assert_pagina_acessivel(html)


# ---------------------------------------------------------------------------
# Lista, formulário, modelo e ponto de acesso no Diário
# ---------------------------------------------------------------------------


def test_lista_vazia_orienta_a_importar_e_a_quem_so_le(client, cenario):
    _entrar(client, "gestor-telas")
    assert (
        "Nenhum arquivo de lançamentos recebido"
        in client.get(_url("lancamentos_importacoes", cenario["empresa"])).content.decode()
    )
    client.logout()
    _entrar(client, "paralegal-telas")
    html = client.get(_url("lancamentos_importacoes", cenario["empresa"])).content.decode()
    assert "Importar arquivo" not in html


def test_lista_mostra_estado_formato_e_contagens_de_cada_importacao(client, cenario):
    empresa = cenario["empresa"]
    importacao = _importacao_de_proprio(empresa)
    servico.descartar(importacao, motivo="Teste da lista", usuario=None)
    _entrar(client, "gestor-telas")

    html = client.get(_url("lancamentos_importacoes", empresa)).content.decode()

    assert "Descartada" in html
    assert "DataLedger (TXT próprio)" in html
    assert "lancamentos.txt" in html


def test_modelo_excel_de_lancamentos_baixa_um_xlsx_que_o_leitor_aceita(client, cenario):
    _entrar(client, "gestor-telas")

    resposta = client.get(_url("lancamentos_importar_modelo_excel", cenario["empresa"]))

    assert resposta.status_code == 200
    assert resposta["Content-Type"] == TIPO_XLSX
    assert 'filename="modelo-lancamentos.xlsx"' in resposta["Content-Disposition"]
    resultado = excel_lancamentos.ler(resposta.content)
    # Só a aba `instrucoes` é ignorada (aviso); o modelo vazio não tem erro nem lançamento.
    assert [(o.linha, o.campo, o.nivel) for o in resultado.ocorrencias] == [(0, "aba", NIVEL_AVISO)]
    assert resultado.lancamentos == []


def test_modelo_excel_de_lancamentos_nao_aceita_parametro_na_url(client, cenario):
    _entrar(client, "gestor-telas")

    resposta = client.get(_url("lancamentos_importar_modelo_excel", cenario["empresa"]), {"x": "1"})

    assert resposta.status_code == 400


def test_envio_por_planilha_recebe_o_arquivo_do_modelo_preenchido(client, cenario):
    empresa = cenario["empresa"]
    _entrar(client, "gestor-telas")

    resposta = _enviar(client, empresa, "excel", PLANILHA, "lancamentos.xlsx")

    assert resposta.status_code == 302
    assert _ultima_importacao(empresa).formato == "excel"


def test_diario_mostra_importar_so_a_quem_escreve(client, cenario):
    empresa = cenario["empresa"]
    _entrar(client, "gestor-telas")
    escrita = client.get(_url("diario", empresa)).content.decode()
    client.logout()
    _entrar(client, "paralegal-telas")
    leitura = client.get(_url("diario", empresa)).content.decode()

    assert "Importar lançamentos" in escrita
    assert "Importar lançamentos" not in leitura
    assert "Importações de lançamentos" in escrita
    assert "Importações de lançamentos" in leitura


def test_rotulos_de_trilha_cobrem_as_rotas_da_importacao():
    nomes = [
        "lancamentos_importacoes",
        "lancamentos_importar",
        "lancamentos_importar_modelo_excel",
        "lancamentos_importacao",
        *[
            f"lancamentos_importacao_{acao.replace('lancamentos_importacao_', '')}"
            for acao in ACOES
        ],
    ]
    for nome in nomes:
        assert ("contabilidade_web", nome) in ROTULOS_DE_TELA, nome


def test_formatos_e_politicas_da_tela_sao_os_do_servico():
    assert set(FORMATOS_DE_IMPORTACAO_DE_LANCAMENTOS_NA_TELA) == set(
        servico.LEITORES_DE_LANCAMENTOS
    )
    assert set(POLITICAS_DE_EFETIVACAO_NA_TELA) == set(servico.POLITICAS_DE_EFETIVACAO)


def test_conferencia_pagina_de_50_em_50_e_a_pagina_que_nao_existe_cai_na_ultima(client, cenario):
    """60 lançamentos prontos: a 1ª página tem 50 e a 2ª, 10. Página além do fim cai na última."""
    empresa = cenario["empresa"]
    linhas = []
    for numero in range(1, 61):
        linhas.append(f"{numero};2026-01-10;Lote {numero};1.1.1;D;10.00")
        linhas.append(f"{numero};2026-01-10;Lote {numero};2.1;C;10.00")
    arquivo = ("numero;data;historico;conta;lado;valor\r\n" + "\r\n".join(linhas) + "\r\n").encode(
        "utf-8"
    )
    importacao = _receber_direto(empresa, "proprio", arquivo, "lote.txt")
    _entrar(client, "gestor-telas")

    primeira = _conferencia(client, empresa, importacao)
    segunda = _conferencia(client, empresa, importacao, pagina="2")
    alem = _conferencia(client, empresa, importacao, pagina="99")

    assert primeira.context["contagens"]["total"] == 60
    assert len(primeira.context["lancamentos"]) == 50
    assert len(segunda.context["lancamentos"]) == 10
    assert segunda.context["lancamentos"][0]["numero"] == "51"
    assert [linha["numero"] for linha in alem.context["lancamentos"]] == [
        linha["numero"] for linha in segunda.context["lancamentos"]
    ]
    assert "Página 1 de 2" in primeira.content.decode()
