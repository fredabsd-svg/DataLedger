"""DL-077, fatia 1 (critério 7): API do plano — permissão no servidor, isolamento,
contrato de campos, limites de tamanho, token da aplicação e trilha.

Chamadas reais pelo cliente HTTP, com sessão autenticada (o mesmo caminho da tela).
Dados sintéticos. A permissão é a da contabilidade: escrever = ADMINISTRADOR, GESTOR,
ANALISTA, FINANCEIRO (`PodeEscriturar`); ler = também PARALEGAL (`PodeLerContabilidade`);
CLIENTE não passa em nenhuma das três rotas.
"""

import re
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio.leitura import MAXIMO_DE_LINHAS, TAMANHO_MAXIMO_ARQUIVO_BYTES
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa, ModoEscrituracao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"
PLANO_VALIDO = (
    CABECALHO + "\r\n1;Ativo;;N;ativo;devedora\r\n1.1;Caixa;1;S;ativo;devedora\r\n"
).encode("utf-8")
PLANO_COM_ERRO = (CABECALHO + "\r\n1;Ativo;;N;ativo;devedora\r\n2;Sem tipo;;S;;\r\n").encode(
    "utf-8"
)


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario(client):
    escritorio_a = Escritorio.objects.create(nome="Escritório API A", cnpj="55555555000155")
    escritorio_b = Escritorio.objects.create(nome="Escritório API B", cnpj="66666666000166")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa API Ltda", cnpj="77777777000177"
    )
    outra = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Outra API Ltda", cnpj="88888888000188"
    )
    _usuario("analista-api", escritorio_a, Papel.ANALISTA)
    _usuario("paralegal-api", escritorio_a, Papel.PARALEGAL)
    _usuario("cliente-api", escritorio_a, Papel.CLIENTE)
    _usuario("gestor-b-api", escritorio_b, Papel.GESTOR)
    return {"empresa": empresa, "outra": outra}


def _entrar(client, username):
    assert client.login(username=username, password=SENHA)


def _previa_url(empresa_id):
    return reverse("contabilidade:plano-importacao-previa", args=[empresa_id])


def _aplicar_url(empresa_id):
    return reverse("contabilidade:plano-importacao-aplicar", args=[empresa_id])


def _exportar_url(empresa_id):
    return reverse("contabilidade:plano-exportacao", args=[empresa_id])


def _arquivo(conteudo=PLANO_VALIDO, nome="plano.txt"):
    return SimpleUploadedFile(nome, conteudo, content_type="text/plain")


def _previa(client, empresa, conteudo=PLANO_VALIDO, formato="proprio", **extra):
    return client.post(
        _previa_url(empresa.id),
        {"arquivo": _arquivo(conteudo), "formato": formato, **extra},
    )


def _aplicar(client, empresa, previa_json, conteudo=PLANO_VALIDO, formato="proprio", **extra):
    return client.post(
        _aplicar_url(empresa.id),
        {
            "arquivo": _arquivo(conteudo),
            "formato": formato,
            "sha256": previa_json["sha256"],
            "assinatura": previa_json["assinatura"],
            **extra,
        },
    )


# -----------------------------------------------------------------------------
# Prévia
# -----------------------------------------------------------------------------


def test_previa_devolve_o_que_o_contador_revisa_e_nao_grava(client, cenario):
    _entrar(client, "analista-api")

    resposta = _previa(client, cenario["empresa"])

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["pode_aplicar"] is True
    assert corpo["contagens"]["criar"] == 2
    assert len(corpo["sha256"]) == 64
    assert len(corpo["assinatura"]) == 64
    assert {i["codigo"] for i in corpo["itens"]} == {"1", "1.1"}
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 0


@pytest.mark.parametrize("usuario", ["paralegal-api", "cliente-api"])
def test_previa_recusa_quem_nao_escreve_o_plano(client, cenario, usuario):
    """Ler é liberado a PARALEGAL; importar não. CLIENTE não passa em nada."""
    _entrar(client, usuario)

    assert _previa(client, cenario["empresa"]).status_code == 403


def test_previa_de_empresa_de_outro_escritorio_responde_404(client, cenario):
    _entrar(client, "analista-api")

    assert _previa(client, cenario["outra"]).status_code == 404


def test_previa_recusa_campo_que_a_rota_nao_le(client, cenario):
    _entrar(client, "analista-api")

    resposta = _previa(client, cenario["empresa"], xpto="ignorado em silêncio?")

    assert resposta.status_code == 400
    assert "xpto" in resposta.content.decode()


def test_previa_recusa_parametro_na_url(client, cenario):
    _entrar(client, "analista-api")

    resposta = client.post(
        _previa_url(cenario["empresa"].id) + "?formato=proprio",
        {"arquivo": _arquivo(), "formato": "proprio"},
    )

    assert resposta.status_code == 400


def test_previa_recusa_formato_fora_da_lista(client, cenario):
    _entrar(client, "analista-api")

    resposta = _previa(client, cenario["empresa"], formato="excel")

    assert resposta.status_code == 400
    assert "formato" in resposta.json()


def test_previa_sem_arquivo_responde_400_no_campo_arquivo(client, cenario):
    _entrar(client, "analista-api")

    resposta = client.post(_previa_url(cenario["empresa"].id), {"formato": "proprio"})

    assert resposta.status_code == 400
    assert "arquivo" in resposta.json()


def test_previa_prefixos_que_nao_sao_json_responde_400(client, cenario):
    _entrar(client, "analista-api")

    resposta = _previa(client, cenario["empresa"], prefixos="3=receita")

    assert resposta.status_code == 400
    assert "prefixos" in resposta.json()


def test_previa_com_politica_desconhecida_responde_400(client, cenario):
    _entrar(client, "analista-api")

    resposta = _previa(client, cenario["empresa"], politica="apagar_tudo")

    assert resposta.status_code == 400
    assert "politica" in resposta.json()


def test_arquivo_acima_de_10_mb_responde_413(client, cenario):
    _entrar(client, "analista-api")
    grande = b"x" * (TAMANHO_MAXIMO_ARQUIVO_BYTES + 1)

    resposta = _previa(client, cenario["empresa"], conteudo=grande)

    assert resposta.status_code == 413
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 0


def test_arquivo_acima_do_limite_de_linhas_responde_413(client, cenario):
    _entrar(client, "analista-api")
    muitas_linhas = b"\n" * (MAXIMO_DE_LINHAS + 1)

    resposta = _previa(client, cenario["empresa"], conteudo=muitas_linhas)

    assert resposta.status_code == 413


def test_empresa_em_livro_caixa_recusa_previa_e_exportacao(client, cenario):
    """Mesma recusa de toda a contabilidade (DL-038): o modo livro-caixa não escreve plano."""
    empresa = cenario["empresa"]
    empresa.modo_escrituracao = ModoEscrituracao.LIVRO_CAIXA
    empresa.save(update_fields=["modo_escrituracao"])
    _entrar(client, "analista-api")

    assert _previa(client, empresa).status_code == 400
    assert client.get(_exportar_url(empresa.id), {"formato": "proprio"}).status_code == 400


# -----------------------------------------------------------------------------
# Aplicação
# -----------------------------------------------------------------------------


def test_aplicar_com_o_token_da_previa_grava_e_registra_trilha(client, cenario):
    _entrar(client, "analista-api")
    previa = _previa(client, cenario["empresa"]).json()

    resposta = _aplicar(client, cenario["empresa"], previa)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["criadas"] == 2
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 2
    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.importado")
    assert trilha.detalhes["sha256"] == previa["sha256"]
    assert trilha.usuario is not None and trilha.usuario.username == "analista-api"


def test_aplicar_com_sha_de_outro_arquivo_responde_409_e_nao_grava(client, cenario):
    _entrar(client, "analista-api")
    previa = _previa(client, cenario["empresa"]).json()
    previa["sha256"] = "0" * 64

    resposta = _aplicar(client, cenario["empresa"], previa)

    assert resposta.status_code == 409
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 0


def test_aplicar_depois_de_o_cadastro_mudar_sem_erro_responde_409(client, cenario):
    """Outro usuário cadastra a conta '1' IGUAL ao arquivo, depois da prévia. Não há
    erro, mas a conferência mudou ('criar' virou 'sem mudança'): a assinatura da prévia
    não bate e a aplicação recusa, para o contador rever o que vai gravar."""
    _entrar(client, "analista-api")
    previa = _previa(client, cenario["empresa"]).json()
    Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )

    resposta = _aplicar(client, cenario["empresa"], previa)

    assert resposta.status_code == 409, resposta.content
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 1


def test_aplicar_depois_de_o_cadastro_conflitar_responde_400_e_nada_grava(client, cenario):
    """Cadastro com tipo diferente, depois da prévia: a conferência de agora tem erro,
    e a aplicação recusa antes de gravar qualquer coisa."""
    _entrar(client, "analista-api")
    previa = _previa(client, cenario["empresa"]).json()
    Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.PASSIVO,
        natureza=NaturezaConta.CREDORA,
        aceita_lancamento=False,
    )

    resposta = _aplicar(client, cenario["empresa"], previa)

    assert resposta.status_code == 400, resposta.content
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 1


def test_aplicar_plano_com_erro_responde_400_com_ocorrencias_e_nada_grava(client, cenario):
    _entrar(client, "analista-api")
    previa = _previa(client, cenario["empresa"], conteudo=PLANO_COM_ERRO).json()
    assert previa["pode_aplicar"] is False

    resposta = _aplicar(client, cenario["empresa"], previa, conteudo=PLANO_COM_ERRO)

    assert resposta.status_code == 400
    corpo = resposta.json()
    assert any(o["campo"] == "tipo" and o["nivel"] == "erro" for o in corpo["ocorrencias"])
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 0


def test_aplicar_sem_token_responde_400(client, cenario):
    _entrar(client, "analista-api")

    resposta = client.post(
        _aplicar_url(cenario["empresa"].id),
        {"arquivo": _arquivo(), "formato": "proprio"},
    )

    assert resposta.status_code == 400
    assert "sha256" in resposta.json() and "assinatura" in resposta.json()


@pytest.mark.parametrize("usuario", ["paralegal-api", "cliente-api"])
def test_aplicar_recusa_quem_nao_escreve(client, cenario, usuario):
    _entrar(client, "analista-api")
    previa = _previa(client, cenario["empresa"]).json()
    client.logout()
    _entrar(client, usuario)

    assert _aplicar(client, cenario["empresa"], previa).status_code == 403
    assert Conta.objects.filter(empresa=cenario["empresa"]).count() == 0


# -----------------------------------------------------------------------------
# Exportação
# -----------------------------------------------------------------------------


def _cadastrar_plano_exportavel(empresa):
    Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa ção",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=True,
        conta_pai=Conta.objects.get(empresa=empresa, codigo="1"),
    )


def test_exportar_proprio_devolve_arquivo_com_nome_sem_sped_e_registra_trilha(client, cenario):
    empresa = cenario["empresa"]
    _cadastrar_plano_exportavel(empresa)
    _entrar(client, "paralegal-api")

    resposta = client.get(_exportacao_url_com(empresa, formato="proprio"))

    assert resposta.status_code == 200, resposta.content
    disposicao = resposta.headers["Content-Disposition"]
    assert re.fullmatch(
        r'attachment; filename="plano-77777777000177-\d{8}-formato-dataledger\.txt"', disposicao
    ), disposicao
    assert "sped" not in disposicao.lower()
    assert resposta.content.startswith(CABECALHO.encode() + b"\r\n")
    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.exportado")
    assert trilha.detalhes["formato"] == "proprio"
    assert trilha.detalhes["quantidade_contas"] == 2


def test_exportar_ecd_exige_data_de_alteracao(client, cenario):
    _entrar(client, "paralegal-api")

    resposta = client.get(_exportacao_url_com(cenario["empresa"], formato="ecd"))

    assert resposta.status_code == 400
    assert "p. 118" in resposta.json()["plano"][0]


def test_exportar_ecd_em_iso_8859_1_com_nome_do_leiaute(client, cenario):
    empresa = cenario["empresa"]
    _cadastrar_plano_exportavel(empresa)
    _entrar(client, "paralegal-api")

    resposta = client.get(_exportacao_url_com(empresa, formato="ecd", data_alteracao="2026-01-31"))

    assert resposta.status_code == 200, resposta.content
    assert resposta.headers["Content-Type"] == "text/plain; charset=iso-8859-1"
    disposicao = resposta.headers["Content-Disposition"]
    assert re.search(r'filename="plano-77777777000177-\d{8}-registros-I050\.txt"', disposicao)
    # Decisão do arquiteto (DL-077): sem "ECD" nem "SPED" no nome do arquivo exportado.
    assert "ecd" not in disposicao.lower()
    assert "sped" not in disposicao.lower()
    texto = resposta.content.decode("iso-8859-1")
    assert "|I050|31012026|01|S|1|1||Ativo|" in texto
    assert "|I050|31012026|01|A|2|1.1|1|Caixa ção|" in texto


def test_exportar_ecd_recusa_caractere_fora_do_latin1_com_400(client, cenario):
    empresa = cenario["empresa"]
    Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa € reservado",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=True,
    )
    _entrar(client, "paralegal-api")

    resposta = client.get(_exportacao_url_com(empresa, formato="ecd", data_alteracao="2026-01-31"))

    assert resposta.status_code == 400
    assert "p. 52" in resposta.json()["plano"][0]


def test_exportar_com_movimento_exige_periodo_valido(client, cenario):
    _entrar(client, "paralegal-api")
    empresa = cenario["empresa"]

    assert (
        client.get(
            _exportacao_url_com(empresa, formato="proprio", filtro="com_movimento")
        ).status_code
        == 400
    )
    assert (
        client.get(
            _exportacao_url_com(
                empresa,
                formato="proprio",
                filtro="com_movimento",
                inicio="2026-03-01",
                fim="2026-02-01",
            )
        ).status_code
        == 400
    )
    assert (
        client.get(
            _exportacao_url_com(
                empresa,
                formato="proprio",
                filtro="com_movimento",
                inicio="2026-02-30",
                fim="2026-03-01",
            )
        ).status_code
        == 400
    )


def test_exportar_filtro_e_formato_desconhecidos_respondem_400(client, cenario):
    _entrar(client, "paralegal-api")
    empresa = cenario["empresa"]

    assert (
        client.get(_exportacao_url_com(empresa, formato="proprio", filtro="algumas")).status_code
        == 400
    )
    assert client.get(_exportacao_url_com(empresa, formato="excel")).status_code == 400


def test_exportar_recusa_parametro_que_nao_existe(client, cenario):
    _entrar(client, "paralegal-api")

    resposta = client.get(_exportacao_url_com(cenario["empresa"], formato="proprio", xpto="1"))

    assert resposta.status_code == 400


def test_exportar_recusa_cliente_e_responde_404_para_outro_escritorio(client, cenario):
    _entrar(client, "cliente-api")
    assert client.get(_exportacao_url_com(cenario["empresa"], formato="proprio")).status_code == 403

    client.logout()
    _entrar(client, "paralegal-api")
    assert client.get(_exportacao_url_com(cenario["outra"], formato="proprio")).status_code == 404


def test_exportar_com_movimento_no_periodo_traz_a_superior_e_conta_na_trilha(client, cenario):
    """Conta com partida no período sai com a sua superior (sem ela, o arquivo não
    se reimporta), e a trilha diz quantas sintéticas vieram só pela hierarquia."""
    from decimal import Decimal

    from apps.contabilidade.models import TipoPartida
    from apps.contabilidade.services import criar_lancamento

    empresa = cenario["empresa"]
    _cadastrar_plano_exportavel(empresa)
    fornecedores = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=NaturezaConta.CREDORA,
        aceita_lancamento=True,
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 10),
        historico="Compra à vista",
        itens=[
            {
                "conta": Conta.objects.get(empresa=empresa, codigo="1.1"),
                "tipo": TipoPartida.DEBITO,
                "valor": Decimal("100.00"),
            },
            {"conta": fornecedores, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    _entrar(client, "paralegal-api")

    resposta = client.get(
        _exportacao_url_com(
            empresa,
            formato="proprio",
            filtro="com_movimento",
            inicio="2026-03-01",
            fim="2026-03-31",
        )
    )

    assert resposta.status_code == 200, resposta.content
    linhas = resposta.content.decode("utf-8").split("\r\n")
    assert linhas[1].startswith("1;Ativo;")  # a superior, sem movimento próprio
    assert linhas[2].startswith("1.1;Caixa")
    # Cabeçalho, '1' (superior, só pela hierarquia), '1.1' e '2.1' (ambas com partida),
    # e a linha vazia final do arquivo.
    assert linhas[3].startswith("2.1;Fornecedores")
    assert len(linhas) == 5
    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.exportado")
    assert trilha.detalhes["sinteticas_incluidas"] == 1
    assert trilha.detalhes["quantidade_contas"] == 3


def _exportacao_url_com(empresa, **parametros):
    from urllib.parse import urlencode

    return f"{_exportar_url(empresa.id)}?{urlencode(parametros)}"


def test_exportacao_nao_traz_contas_de_outra_empresa_do_mesmo_escritorio(client, cenario):
    """Isolamento na exportação: a empresa A não leva para o arquivo as contas da B,
    nem com o mesmo escritório, nem com o filtro de movimento."""
    empresa_a = cenario["empresa"]
    empresa_b = Empresa.objects.create(
        escritorio=empresa_a.escritorio, razao_social="Segunda Ltda", cnpj="99999999000199"
    )
    _cadastrar_plano_exportavel(empresa_a)
    Conta.objects.create(
        empresa=empresa_b,
        codigo="7",
        nome="Conta da outra empresa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=True,
    )
    _entrar(client, "paralegal-api")

    resposta = client.get(_exportacao_url_com(empresa_a, formato="proprio"))

    assert resposta.status_code == 200
    assert b"Conta da outra empresa" not in resposta.content
    assert b"\r\n7;" not in resposta.content
    assert resposta.content.count(b"\r\n") == 3  # cabeçalho + duas contas da A
