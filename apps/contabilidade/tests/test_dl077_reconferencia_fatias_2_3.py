"""Ressalvas da reconferência das fatias 2 e 3 (DL-077): R1 a R4.

A reconferência (`docs/auditorias/2026-10-08-dl-077-fatias-2-3-reconferencia.md`) reprovou por:

- R1 (alta): partida com número ilegível some na leitura e a política só os válidos efetiva o
  lançamento incompleto (formato próprio e Excel). Decisão do arquiteto: a efetivação parcial
  fica SUSPENSA (BL-676). Só existe tudo ou nada.
- R2 (média): registro com identificador ilegível dentro de um lote do leiaute de referência some
  em silêncio, e até a tudo ou nada efetiva o lançamento incompleto.
- R3 (baixa): byte nulo no motivo do descarte e nos números do aceite de avisos dava 500.
- R4 (baixa): lacunas de teste (N04, N31, N12, N13 e N17).

Dados SINTÉTICOS: CNPJ de exemplo, plano do cenário de exportação, valores redondos. Nenhum
arquivo real entra aqui (RC-167).
"""

import io
import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from openpyxl import Workbook

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.intercambio.canonico import NIVEL_AVISO, NIVEL_ERRO
from apps.contabilidade.intercambio.formatos import (
    proprio_lancamentos_leitura,
    referencia_lancamentos_leitura,
)
from apps.contabilidade.models import EstadoImportacaoLancamentos, LancamentoContabil, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

SENHA = "senha-forte-123"
CNPJ_DE_OUTRA = "88888888000188"
MENSAGEM_SO_VALIDOS_SUSPENSA = (
    "a efetivação parcial ('só os válidos') está suspensa: corrija ou descarte os lançamentos "
    "com erro e efetive tudo — BL-676"
)
D = date(2026, 3, 10)
CABECALHO_H = ["numero", "data", "historico", "conta", "lado", "valor"]
pytestmark = pytest.mark.django_db


# --- Construtores de arquivo (sintéticos) -----------------------------------------------------


def _proprio(*linhas):
    cabecalho = "numero;data;historico;conta;lado;valor\r\n"
    return (cabecalho + "".join(linha + "\r\n" for linha in linhas)).encode("utf-8")


def _par(
    numero, data="2026-03-10", historico="Compra", conta_d="1.1.1", conta_c="2.1", valor="100.00"
):
    return [
        f"{numero};{data};{historico};{conta_d};D;{valor}",
        f"{numero};{data};{historico};{conta_c};C;{valor}",
    ]


def _ecd(*linhas, cnpj=CNPJ_DA_EMPRESA):
    corpo = [f"|0000|LECD|01032026|31032026|Empresa Sintetica Ltda|{cnpj}|SP|||", *linhas]
    return ("".join(linha + "\r\n" for linha in corpo)).encode("iso-8859-1")


def _i200(numero, data="10032026", valor="100,00"):
    return f"|I200|{numero}|{data}|{valor}|N||"


def _i250(conta, lado, valor, historico="Compra"):
    return f"|I250|{conta}||{valor}|{lado}|||{historico}||"


def _referencia(*linhas, cnpj=CNPJ_DA_EMPRESA):
    corpo = [f"|0000|{cnpj}|", *linhas]
    return ("".join(linha + "\r\n" for linha in corpo)).encode("iso-8859-1")


def _ref_6100(data="10/03/2026", debito="3", credito="12", valor="100,00", historico="Compra"):
    return f"|6100|{data}|{debito}|{credito}|{valor}||{historico}||||"


def _xlsx(linhas):
    pasta = Workbook()
    planilha = pasta.active
    planilha.title = "lancamentos"
    for linha in linhas:
        planilha.append(linha)
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


def _excel_com_numero_vazio_no_fim():
    return _xlsx(
        [
            CABECALHO_H,
            [1, D, "C", "1.1.1", "D", 100],
            [1, D, "C", "2.1", "C", 100],
            [None, D, "C", "1.1.2", "D", 50],
            [None, D, "C", "3.1", "C", 50],
        ]
    )


# --- Helpers ----------------------------------------------------------------------------------


@pytest.fixture
def cenario(client):
    escritorio = criar_escritorio("Escritório Reconferência", "99999999000199")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Reconferência", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    outra = criar_empresa(
        escritorio=escritorio, razao_social="Outra Reconferência", cnpj=CNPJ_DE_OUTRA
    )
    contas_outra = criar_plano(outra)
    _usuario("gestor-rec", escritorio, Papel.GESTOR)
    return {
        "empresa": empresa,
        "contas": contas,
        "outra": outra,
        "contas_outra": contas_outra,
    }


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _entrar(client, username="gestor-rec"):
    assert client.login(username=username, password=SENHA)


def _depara_da_referencia(empresa, contas):
    """Códigos reduzidos do sistema de referência usados nos arquivos de teste."""
    for codigo, conta in (("3", "1.1.1"), ("4", "1.1.2"), ("12", "2.1")):
        servico.definir_de_para(
            empresa=empresa, formato="referencia", codigo_origem=codigo, conta=contas[conta]
        )


def _receber(empresa, formato, conteudo, nome="lancamentos.txt"):
    return servico.receber(
        empresa=empresa, formato=formato, conteudo=conteudo, nome_arquivo=nome, usuario=None
    )


def _aceitar_arquivo_se_preciso(importacao):
    if importacao.exige_aceite_do_arquivo and not importacao.aceite_do_arquivo:
        servico.aceitar_avisos(importacao, [], aceitar_arquivo=True, usuario=None)


def _diario(empresa):
    return LancamentoContabil.objects.filter(empresa=empresa)


def _url(nome, empresa, *args):
    return reverse(f"contabilidade:{nome}", args=[empresa.id, *args])


def _url_tela(nome, empresa, *args):
    return reverse(f"contabilidade_web:{nome}", args=[empresa.id, *args])


def _enviar_pela_api(client, empresa, conteudo, formato, nome="a.txt"):
    return client.post(
        _url("lancamentos-importacao", empresa),
        {
            "arquivo": SimpleUploadedFile(nome, conteudo, content_type="text/plain"),
            "formato": formato,
        },
    )


# --- R1 (alta): nenhuma política grava lançamento incompleto -----------------------------------

R1_CASOS = [
    pytest.param(
        "proprio",
        _proprio(
            *_par(1), "1x;2026-03-10;Compra;1.1.2;D;50.00", "1x;2026-03-10;Compra;3.1;C;50.00"
        ),
        "a.txt",
        id="proprio-numero-1x-no-fim",
    ),
    pytest.param(
        "proprio",
        _proprio(*_par(1), ";2026-03-10;Compra;1.1.2;D;50.00", ";2026-03-10;Compra;3.1;C;50.00"),
        "a.txt",
        id="proprio-numero-vazio-no-fim",
    ),
    pytest.param(
        "proprio",
        _proprio("x;2026-03-10;Compra;1.1.2;D;50.00", "x;2026-03-10;Compra;3.1;C;50.00", *_par(1)),
        "a.txt",
        id="proprio-numero-ilegivel-no-inicio",
    ),
    pytest.param(
        "excel", _excel_com_numero_vazio_no_fim(), "a.xlsx", id="excel-numero-vazio-no-fim"
    ),
    pytest.param(
        "referencia",
        _referencia(
            "|6000|C||||",
            _ref_6100(debito="3", credito="12", valor="60,00"),
            _ref_6100(debito="4", credito="12", valor="40,00"),
            "|6l00|10/03/2026|3|12|25,00||Compra||||",
        ),
        "a.txt",
        id="referencia-6100-com-identificador-ilegivel-no-fim-do-lote",
    ),
]


@pytest.mark.parametrize("formato,conteudo,nome", R1_CASOS)
@pytest.mark.parametrize("politica", [servico.SO_VALIDOS, servico.TUDO_OU_NADA])
def test_r1_nenhuma_politica_grava_lancamento_incompleto(
    cenario, formato, conteudo, nome, politica
):
    empresa = cenario["empresa"]
    _depara_da_referencia(empresa, cenario["contas"])
    importacao = _receber(empresa, formato, conteudo, nome)
    _aceitar_arquivo_se_preciso(importacao)

    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=politica, usuario=None)

    assert not _diario(empresa).exists()


def test_r1_o_erro_de_numero_ilegivel_fica_no_arquivo_e_bloqueia_a_tudo_ou_nada(cenario):
    importacao = _receber(
        cenario["empresa"],
        "proprio",
        _proprio(*_par(1), ";2026-03-10;Compra;1.1.2;D;50.00", ";2026-03-10;Compra;3.1;C;50.00"),
    )

    assert importacao.quantidade_erros_do_arquivo == 2
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)


# --- R1 e R2: a efetivação parcial está suspensa (BL-676) --------------------------------------


def test_so_validos_e_recusado_mesmo_com_arquivo_limpo_e_nada_e_gravado(cenario):
    empresa = cenario["empresa"]
    importacao = _receber(empresa, "proprio", _proprio(*_par(1)))

    with pytest.raises(servico.ImportacaoNaoEfetivada) as exc:
        servico.efetivar(importacao, politica=servico.SO_VALIDOS, usuario=None)

    assert exc.value.mensagem == MENSAGEM_SO_VALIDOS_SUSPENSA
    assert not _diario(empresa).exists()
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA


def test_so_validos_suspenso_nao_grava_o_lancamento_que_presta(cenario):
    empresa = cenario["empresa"]
    importacao = _receber(
        empresa,
        "proprio",
        _proprio(*_par(1), "2;2026-03-11;Ruim;1.1.1;D;100.00", "2;2026-03-11;Ruim;2.1;C;90.00"),
    )

    with pytest.raises(servico.ImportacaoNaoEfetivada, match="suspensa"):
        servico.efetivar(importacao, politica=servico.SO_VALIDOS, usuario=None)

    assert not _diario(empresa).exists()


def test_politica_desconhecida_continua_recusada_e_nao_lista_so_validos(cenario):
    importacao = _receber(cenario["empresa"], "proprio", _proprio(*_par(1)))

    with pytest.raises(servico.ImportacaoRecusada) as exc:
        servico.efetivar(importacao, politica="tanto_faz", usuario=None)

    assert "so_validos" not in exc.value.mensagem
    assert "tudo_ou_nada" in exc.value.mensagem


# --- R2 (média): registro ilegível dentro de lote do leiaute de referência ----------------------


def test_r2_registro_ilegivel_no_fim_do_lote_vira_erro_e_o_lote_nao_vira_lancamento():
    arquivo = _referencia(
        "|6000|C||||",
        _ref_6100(debito="3", credito="12", valor="60,00"),
        _ref_6100(debito="4", credito="12", valor="40,00"),
        "|6l00|10/03/2026|3|12|25,00||Compra||||",
    )

    resultado = referencia_lancamentos_leitura.ler(arquivo)

    # Linhas: 1 = 0000, 2 = 6000, 3 e 4 = 6100, 5 = o registro ilegível.
    erros = [(o.linha, o.campo) for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]
    assert erros == [(5, "REG")]
    assert resultado.lancamentos == []
    assert resultado.registros_ignorados == {"6l00": 1}


def test_r2_registro_ilegivel_no_meio_do_lote_e_erro_e_o_lote_continua_fechado_como_erro():
    arquivo = _referencia(
        "|6000|C||||",
        _ref_6100(debito="3", credito="12", valor="60,00"),
        "|6x00|10/03/2026|3|12|25,00||Compra||||",
        _ref_6100(debito="4", credito="12", valor="40,00"),
    )

    resultado = referencia_lancamentos_leitura.ler(arquivo)

    # O 6100 depois do registro ilegível continua no lote: não vira "6100 sem lote".
    erros = [(o.linha, o.campo) for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]
    assert erros == [(4, "REG")]
    assert resultado.lancamentos == []


def test_r2_registro_desconhecido_fora_de_lote_e_aviso_por_registro_e_nao_bloqueia():
    arquivo = _referencia(
        "|0220|x|",
        "|6000|C||||",
        _ref_6100(debito="3", credito="12", valor="100,00"),
    )

    resultado = referencia_lancamentos_leitura.ler(arquivo)

    assert [(o.linha, o.campo, o.nivel) for o in resultado.ocorrencias] == [
        (2, "registro", NIVEL_AVISO)
    ]
    assert len(resultado.lancamentos) == 1
    assert resultado.registros_ignorados == {"0220": 1}


def test_r2_no_servico_o_registro_ilegivel_no_fim_do_lote_recusa_as_duas_politicas(cenario):
    empresa = cenario["empresa"]
    _depara_da_referencia(empresa, cenario["contas"])
    importacao = _receber(
        empresa,
        "referencia",
        _referencia(
            "|6000|C||||",
            _ref_6100(debito="3", credito="12", valor="60,00"),
            _ref_6100(debito="4", credito="12", valor="40,00"),
            "|6l00|10/03/2026|3|12|25,00||Compra||||",
        ),
    )

    assert importacao.quantidade_erros_do_arquivo_inteiro == 1
    for politica in (servico.TUDO_OU_NADA, servico.SO_VALIDOS):
        with pytest.raises(servico.ImportacaoNaoEfetivada):
            servico.efetivar(importacao, politica=politica, usuario=None)
    assert not _diario(empresa).exists()


def test_registros_ignorados_ficam_na_trilha_e_no_resultado_do_envio(cenario):
    empresa = cenario["empresa"]
    importacao = _receber(
        empresa,
        "referencia",
        _referencia("|0220|x|", "|6000|C||||", _ref_6100(debito="3", credito="12", valor="100,00")),
    )

    assert importacao.registros_ignorados_da_leitura == {"0220": 1}
    registro = RegistroAuditoria.objects.get(acao="lancamentos.importacao.recebida")
    assert registro.detalhes["registros_ignorados"] == {"0220": 1}


def test_api_envio_devolve_os_registros_ignorados(client, cenario):
    _entrar(client)
    resposta = _enviar_pela_api(
        client,
        cenario["empresa"],
        _referencia("|0220|x|", "|6000|C||||", _ref_6100(debito="3", credito="12", valor="100,00")),
        "referencia",
    )

    assert resposta.status_code == 201
    assert resposta.json()["registros_ignorados"] == {"0220": 1}


def test_tela_mostra_os_registros_ignorados_depois_do_envio(client, cenario):
    _entrar(client)
    resposta = client.post(
        _url_tela("lancamentos_importar", cenario["empresa"]),
        {
            "formato": "referencia",
            "arquivo": SimpleUploadedFile(
                "a.txt",
                _referencia(
                    "|0220|x|", "|6000|C||||", _ref_6100(debito="3", credito="12", valor="100,00")
                ),
                content_type="text/plain",
            ),
        },
        follow=True,
    )

    assert resposta.status_code == 200
    assert "0220 (1)" in resposta.content.decode()


def test_api_so_validos_e_recusado_com_a_mensagem_e_nada_e_gravado(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao_id = _enviar_pela_api(client, empresa, _proprio(*_par(1)), "proprio").json()["id"]

    resposta = client.post(
        _url("lancamentos-importacao-efetivar", empresa, importacao_id),
        data=json.dumps({"politica": "so_validos"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == MENSAGEM_SO_VALIDOS_SUSPENSA
    assert not _diario(empresa).exists()


def test_tela_nao_oferece_so_validos_e_o_veredito_manda_corrigir_o_arquivo(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao = _receber(
        empresa,
        "proprio",
        _proprio(*_par(1), "2;2026-03-11;Ruim;1.1.1;D;100.00"),
    )

    resposta = client.get(_url_tela("lancamentos_importacao", empresa, importacao.pk))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert 'value="so_validos"' not in html
    assert "Só os válidos" not in html
    assert "precisa ser corrigido no arquivo" in html
    assert "descarte a importação" in html


def test_tela_so_validos_recusado_mostra_a_mensagem_e_nao_grava(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao = _receber(empresa, "proprio", _proprio(*_par(1)))

    resposta = client.post(
        _url_tela("lancamentos_importacao_efetivar", empresa, importacao.pk),
        {"politica": "so_validos", "confirmar": "sim"},
    )

    assert resposta.status_code == 400
    assert "suspensa" in resposta.content.decode()
    assert not _diario(empresa).exists()


# --- R3 (baixa): byte nulo nos campos de descarte e de aceite ----------------------------------


def test_r3_motivo_do_descarte_com_nul_e_recusado_e_nada_muda(cenario):
    importacao = _receber(cenario["empresa"], "proprio", _proprio(*_par(1)))

    with pytest.raises(servico.ImportacaoRecusada, match="caractere nulo"):
        servico.descartar(importacao, motivo="ok\x00", usuario=None)

    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert importacao.motivo_do_descarte == ""


def test_r3_numero_do_aceite_com_nul_e_recusado_e_nada_e_aceito(cenario):
    importacao = _receber(cenario["empresa"], "proprio", _proprio(*_par(1)))

    with pytest.raises(servico.ImportacaoRecusada, match="caractere nulo"):
        servico.aceitar_avisos(importacao, ["1\x00"], usuario=None)

    assert not importacao.lancamentos.filter(aceito_com_aviso=True).exists()


def test_r3_api_descartar_com_nul_responde_400_e_nao_descarta(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao = _receber(empresa, "proprio", _proprio(*_par(1)))

    resposta = client.post(
        _url("lancamentos-importacao-descartar", empresa, importacao.pk),
        data=json.dumps({"motivo": "ok\u0000"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA


def test_r3_api_aceite_com_nul_responde_400(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao = _receber(empresa, "proprio", _proprio(*_par(1)))

    resposta = client.post(
        _url("lancamentos-importacao-avisos", empresa, importacao.pk),
        data=json.dumps({"numeros": ["1\u0000"]}),
        content_type="application/json",
    )

    assert resposta.status_code == 400


def test_r3_tela_descartar_com_nul_responde_400_e_nao_descarta(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao = _receber(empresa, "proprio", _proprio(*_par(1)))

    resposta = client.post(
        _url_tela("lancamentos_importacao_descartar", empresa, importacao.pk),
        {"motivo": "ok\x00"},
    )

    assert resposta.status_code == 400
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA


def test_r3_tela_aceite_com_nul_responde_400(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao = _receber(empresa, "proprio", _proprio(*_par(1)))

    resposta = client.post(
        _url_tela("lancamentos_importacao_avisos", empresa, importacao.pk),
        {"numeros": ["1\x00"]},
    )

    assert resposta.status_code == 400


# --- R4 (baixa): lacunas de teste --------------------------------------------------------------


def test_n04_tudo_ou_nada_recusa_quando_o_leitor_descartou_um_lancamento(cenario):
    """N04: o I200 nº 2 tem VL_LCTO de 999,00 e as partidas somam 100,00. O leitor o descarta."""
    empresa = cenario["empresa"]
    arquivo = _ecd(
        _i200(1),
        _i250("1.1.1", "D", "100,00"),
        _i250("2.1", "C", "100,00"),
        _i200(2, valor="999,00"),
        _i250("1.1.1", "D", "100,00", "Outro"),
        _i250("2.1", "C", "100,00", "Outro"),
    )
    importacao = _receber(empresa, "ecd", arquivo)

    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    assert not _diario(empresa).exists()


def test_n04_so_validos_do_mesmo_arquivo_e_recusado_pela_suspensao(cenario):
    """N04, com a suspensão: antes, só-válidos gravava só o nº 1. Agora é recusado."""
    empresa = cenario["empresa"]
    arquivo = _ecd(
        _i200(1),
        _i250("1.1.1", "D", "100,00"),
        _i250("2.1", "C", "100,00"),
        _i200(2, valor="999,00"),
        _i250("1.1.1", "D", "100,00", "Outro"),
        _i250("2.1", "C", "100,00", "Outro"),
    )
    importacao = _receber(empresa, "ecd", arquivo)

    with pytest.raises(servico.ImportacaoNaoEfetivada, match="suspensa"):
        servico.efetivar(importacao, politica=servico.SO_VALIDOS, usuario=None)

    assert not _diario(empresa).exists()


def test_n31_conferir_e_baixar_pela_tela_com_normalizar_texto(client, cenario):
    """N31: o link da conferência leva `normalizar_texto` e o download devolve 200."""
    _entrar(client)
    empresa = cenario["empresa"]
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 2),
        historico="Pagamento – parcela 1",
        itens=[
            {
                "conta": cenario["contas"]["1.1.1"],
                "tipo": TipoPartida.DEBITO,
                "valor": Decimal("100.00"),
            },
            {
                "conta": cenario["contas"]["2.1"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("100.00"),
            },
        ],
    )

    conferencia = client.get(
        _url_tela("lancamentos_exportar", empresa),
        {"formato": "ecd", "inicio": "2026-03-01", "fim": "2026-03-31", "normalizar_texto": "on"},
    )

    assert conferencia.status_code == 200
    link = conferencia.context["link_do_arquivo"]
    assert "normalizar_texto=true" in link
    assert "sha256=" in link
    download = client.get(link)
    assert download.status_code == 200
    assert "attachment" in download["Content-Disposition"]


def test_n12_e_n13_consultas_de_duplicidade_filtram_a_empresa(cenario):
    """N12 e N13: as duas consultas do Diário na conferência filtram `empresa_id`.

    Equivalentes no resultado (a assinatura tem `conta_id`, que é da empresa), mas a consulta sem o
    filtro carregaria linhas de outro cliente na memória. Um lançamento igual de OUTRA empresa não
    pode aparecer como duplicidade.
    """
    empresa = cenario["empresa"]
    criar_lancamento(
        empresa=cenario["outra"],
        data=D,
        historico="Compra",
        itens=[
            {
                "conta": cenario["contas_outra"]["1.1.1"],
                "tipo": TipoPartida.DEBITO,
                "valor": Decimal("100.00"),
            },
            {
                "conta": cenario["contas_outra"]["2.1"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("100.00"),
            },
        ],
    )

    with CaptureQueriesContext(connection) as contexto:
        diario = servico._diario_da_empresa(empresa, {D})

    sql = [consulta["sql"] for consulta in contexto.captured_queries]
    assert len(sql) == 2
    # O Django registra a consulta já com o parâmetro: o filtro aparece como `"empresa_id" = <id>`.
    assert all(f'"empresa_id" = {empresa.pk}' in texto for texto in sql)
    assert diario == {}


def test_n17_aceitar_arquivo_sem_exigencia_e_recusado_no_servico(cenario):
    importacao = _receber(
        cenario["empresa"],
        "ecd",
        _ecd(_i200(1), _i250("1.1.1", "D", "100,00"), _i250("2.1", "C", "100,00")),
    )
    assert not importacao.exige_aceite_do_arquivo

    with pytest.raises(servico.ImportacaoRecusada, match="não tem aviso de empresa"):
        servico.aceitar_avisos(importacao, [], aceitar_arquivo=True, usuario=None)

    importacao.refresh_from_db()
    assert not importacao.aceite_do_arquivo


def test_n17_api_aceite_do_arquivo_sem_exigencia_responde_400(client, cenario):
    _entrar(client)
    empresa = cenario["empresa"]
    importacao_id = _enviar_pela_api(
        client,
        empresa,
        _ecd(_i200(1), _i250("1.1.1", "D", "100,00"), _i250("2.1", "C", "100,00")),
        "ecd",
    ).json()["id"]

    resposta = client.post(
        _url("lancamentos-importacao-avisos", empresa, importacao_id),
        data=json.dumps({"numeros": [], "aceitar_arquivo": True}),
        content_type="application/json",
    )

    assert resposta.status_code == 400


# --- R2 (continuação): linha em branco dentro de lote ou de lançamento -----------------------
# Uma linha em branco pode ser uma partida apagada. Os três leitores que não têm total declarado
# (próprio, referência e Excel) tratavam o vazio como formatação e perdiam a partida sem erro. O
# fuzzer da reconferência achou 448 (próprio), 49 (referência) e 126 (Excel) lançamentos incompletos
# e equilibrados. A ECD não é afetada: o VL_LCTO do I200 declara o total e a leitura recusa.


def test_r2_proprio_duas_linhas_em_branco_apagam_um_par_equilibrado_e_nada_e_gravado(cenario):
    """O caso que o fuzzer achou: as duas linhas da partida 50,00 viram linhas em branco. Sem a
    regra, sobrava D100/C100 equilibrado, e a tudo ou nada o gravava."""
    empresa = cenario["empresa"]
    importacao = _receber(
        empresa,
        "proprio",
        _proprio(
            *_par(1, valor="100.00"),
            "1;2026-03-10;Compra;1.1.2;D;50.00",
            "",
            "",
            "1;2026-03-10;Compra;3.1;C;50.00",
        ),
    )

    assert importacao.quantidade_erros_do_arquivo_inteiro == 1
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert not _diario(empresa).exists()


def test_r2_proprio_linha_em_branco_no_meio_e_erro_com_a_linha(cenario):
    leitura = proprio_lancamentos_leitura.ler(_proprio(*_par(1), "", *_par(2, valor="10.00")))

    erros = [(o.linha, o.campo) for o in leitura.ocorrencias if o.nivel == NIVEL_ERRO]
    assert erros == [(4, "linha")]


def test_r2_proprio_linha_em_branco_so_no_fim_e_formatacao_e_o_lancamento_entra(cenario):
    empresa = cenario["empresa"]
    importacao = _receber(empresa, "proprio", _proprio(*_par(1), ""))

    assert importacao.quantidade_erros_do_arquivo == 0
    _aceitar_arquivo_se_preciso(importacao)
    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert _diario(empresa).count() == 1


def test_r2_referencia_linha_em_branco_dentro_do_lote_e_erro_e_o_lote_nao_vira_lancamento():
    arquivo = _referencia(
        "|6000|C||||",
        _ref_6100(debito="3", credito="12", valor="60,00"),
        "",
        _ref_6100(debito="4", credito="12", valor="40,00"),
    )

    resultado = referencia_lancamentos_leitura.ler(arquivo)

    # Linhas: 1 = 0000, 2 = 6000, 3 = 6100, 4 = a linha em branco, 5 = o 6100 que segue.
    erros = [(o.linha, o.campo) for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]
    assert erros == [(4, "linha")]
    assert resultado.lancamentos == []


def test_r2_referencia_linha_em_branco_no_fim_do_arquivo_nao_conta():
    arquivo = _referencia(
        "|6000|C||||",
        _ref_6100(debito="3", credito="12", valor="100,00"),
        "",
    )

    resultado = referencia_lancamentos_leitura.ler(arquivo)

    assert [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO] == []
    assert len(resultado.lancamentos) == 1


def test_r2_excel_linha_vazia_no_meio_e_erro_e_nada_e_gravado(cenario):
    empresa = cenario["empresa"]
    _depara_da_referencia(empresa, cenario["contas"])
    conteudo = _xlsx(
        [
            CABECALHO_H,
            [1, D, "Compra", "1.1.1", "D", 50],
            [None] * 6,
            [1, D, "Compra", "2.1", "C", 50],
        ]
    )
    importacao = _receber(empresa, "excel", conteudo, "a.xlsx")
    _aceitar_arquivo_se_preciso(importacao)

    assert importacao.quantidade_erros_do_arquivo_inteiro == 1
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert not _diario(empresa).exists()


def test_r2_excel_linha_vazia_no_fim_nao_conta(cenario):
    empresa = cenario["empresa"]
    conteudo = _xlsx(
        [
            CABECALHO_H,
            [1, D, "Compra", "1.1.1", "D", 100],
            [1, D, "Compra", "2.1", "C", 100],
            [None] * 6,
        ]
    )
    importacao = _receber(empresa, "excel", conteudo, "a.xlsx")
    _aceitar_arquivo_se_preciso(importacao)

    assert importacao.quantidade_erros_do_arquivo == 0
    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    assert _diario(empresa).count() == 1
