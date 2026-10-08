"""DL-077, fatia 1: correção única da auditoria (rodada 1), parte do NÚCLEO.

Cobre, com expectativas escritas à mão a partir da especificação da correção:
- T1 (A1): caractere de controle no código ou no nome é erro com linha e campo, e a
  aplicação nunca chega ao banco com NUL.
- T2 (A2, lado do núcleo): conta de resultado (COD_NAT 04) não herda "ativo" nem recebe
  "ativo" por prefixo; erro nomeado.
- T3 (A3): a superior é o maior prefixo existente no arquivo OU no cadastro, com aviso quando
  não é o imediato.
- T6 (A6): teto de contas por importação e número de consultas da aplicação.
- T8 (A8): cadeia de superiores acima de 50 níveis é recusada com erro nomeado, sem recursão.
- Lacunas da seção 10 da auditoria: N10, N11, N13, M19, M25, N24, e os avisos do A12.

Dados sintéticos. Nenhum arquivo de cliente real.
"""

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio.canonico import ContaLida, ResultadoLeitura
from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais, ler_arquivo
from apps.contabilidade.intercambio.plano import (
    MAXIMO_DE_CONTAS_POR_IMPORTACAO,
    MAXIMO_DE_NIVEIS_DE_SUPERIOR,
    ParametroInvalido,
    PlanoRecusado,
    aplicar_plano,
    conferir_plano,
    exportar_plano,
    validar_prefixos,
)
from apps.contabilidade.models import Conta
from apps.contabilidade.services import (
    ContaRecusadaNoCadastro,
    criar_conta_pelo_plano,
    renomear_conta_pelo_plano,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"
CNPJ_DA_EMPRESA = "22233344000138"  # sintético


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório DL077 Correção", cnpj="33333333000133")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL077 Correção Ltda", cnpj=CNPJ_DA_EMPRESA
    )


def _proprio(*linhas):
    conteudo = ("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("utf-8")
    return ler_arquivo("proprio", conteudo, nome_arquivo="plano-teste.txt")


def _cadastrar(empresa, codigo, nome, tipo, *, pai=None, analitica=False):
    return criar_conta_pelo_plano(
        empresa=empresa,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza="devedora" if tipo in ("ativo", "despesa") else "credora",
        codigo_pai=pai,
        analitica=analitica,
    )


def _aplicar(empresa, previa, usuario=None):
    return aplicar_plano(
        empresa,
        previa,
        usuario,
        None,
        sha256_esperado=previa.sha256,
        assinatura_esperada=previa.assinatura,
    )


def _erros(previa):
    return {(o.linha, o.campo) for o in previa.ocorrencias if o.nivel == "erro"}


def _avisos(previa):
    return {(o.linha, o.campo) for o in previa.ocorrencias if o.nivel == "aviso"}


# -----------------------------------------------------------------------------
# T1 (A1): caractere de controle
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "linha_do_arquivo"),
    [
        ("nome", "1;Ativo\x00X;;N;ativo;devedora"),  # NUL: o caso que virava 500 na aplicação
        ("nome", "1;Ativo\tX;;N;ativo;devedora"),  # TAB
        ("nome", "1;Ativo\x1bX;;N;ativo;devedora"),  # ESC
        ("nome", "1;Ativo\x07X;;N;ativo;devedora"),  # BEL
        ("nome", "1;Ativo\x7fX;;N;ativo;devedora"),  # DEL (127)
        ("codigo", "1\x00;Ativo;;N;ativo;devedora"),
        ("codigo", "1\tA;Ativo;;N;ativo;devedora"),
    ],
)
def test_controle_no_codigo_ou_no_nome_e_erro_com_linha_e_campo(empresa, campo, linha_do_arquivo):
    previa = conferir_plano(empresa, _proprio(linha_do_arquivo), "so_acrescentar", {})

    assert previa.tem_erro
    assert (2, campo) in _erros(previa)
    assert previa.itens[0].acao != "criar"  # a conta não é criada


def test_controle_no_nome_e_recusado_na_aplicacao_sem_500_e_sem_gravar(empresa):
    previa = conferir_plano(
        empresa, _proprio("1;Caixa\x00X;;N;ativo;devedora"), "so_acrescentar", {}
    )

    with pytest.raises(PlanoRecusado):
        _aplicar(empresa, previa)
    assert not Conta.objects.filter(empresa=empresa).exists()


def test_criar_conta_pelo_plano_recusa_controle_como_defesa(empresa):
    """Defesa: mesmo que um caminho chegue até `criar_conta_pelo_plano`, o NUL não grava."""
    with pytest.raises(ContaRecusadaNoCadastro, match="caractere de controle"):
        criar_conta_pelo_plano(
            empresa=empresa,
            codigo="1",
            nome="Caixa\x00X",
            tipo="ativo",
            natureza="devedora",
            codigo_pai=None,
            analitica=True,
        )
    assert not Conta.objects.filter(empresa=empresa).exists()


# -----------------------------------------------------------------------------
# T2 (A2, lado do núcleo): conta de resultado não herda nem recebe "ativo"
# -----------------------------------------------------------------------------


def test_conta_de_resultado_nao_herda_ativo_da_superior_do_cadastro(empresa):
    _cadastrar(empresa, "1", "Ativo", "ativo")  # sintética (analitica=False)
    resultado = ResultadoLeitura(
        contas=[
            ContaLida(
                linha=2,
                codigo="1.9",
                nome="Receita sob ativo",
                codigo_pai="1",
                analitica=True,
                tipo=None,
                natureza=None,
                codigo_origem=None,
                referencial=None,
                tipos_aceitos=frozenset({"receita", "despesa"}),
            )
        ]
    )

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {})

    assert (2, "tipo") in _erros(previa)
    erro = next(o for o in previa.ocorrencias if o.campo == "tipo")
    assert erro.mensagem == (
        "conta de resultado (COD_NAT 04) não pode herdar 'ativo' da conta superior; "
        "informe receita ou despesa por prefixo"
    )


def test_conta_de_resultado_com_prefixo_de_ativo_e_erro_nomeado(empresa):
    resultado = ResultadoLeitura(
        contas=[
            ContaLida(
                linha=2,
                codigo="9.1",
                nome="Resultado raiz",
                codigo_pai=None,
                analitica=True,
                tipo=None,
                natureza=None,
                codigo_origem=None,
                referencial=None,
                tipos_aceitos=frozenset({"receita", "despesa"}),
            )
        ]
    )

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {"9": "ativo"})

    erro = next(o for o in previa.ocorrencias if o.campo == "tipo")
    assert erro.linha == 2 and erro.nivel == "erro"
    assert "pelo prefixo '9'" in erro.mensagem and "receita ou despesa" in erro.mensagem


def test_conta_de_resultado_com_prefixo_de_receita_passa(empresa):
    resultado = ResultadoLeitura(
        contas=[
            ContaLida(
                linha=2,
                codigo="3.1",
                nome="Receita",
                codigo_pai=None,
                analitica=True,
                tipo=None,
                natureza=None,
                codigo_origem=None,
                referencial=None,
                tipos_aceitos=frozenset({"receita", "despesa"}),
            )
        ]
    )

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {"3": "receita"})

    assert not previa.tem_erro
    assert previa.itens[0].tipo == "receita"


# -----------------------------------------------------------------------------
# T3 (A3): superior pelo maior prefixo existente no arquivo OU no cadastro
# -----------------------------------------------------------------------------


def _ref(*registros):
    return ("\r\n".join(registros) + "\r\n").encode("iso-8859-1")


def _reg(*campos):
    return "|" + "|".join(campos) + "|"


def _linha_0200(reduzido, classificacao, analitica, nome, situacao="A"):
    tipo = "A" if analitica else "S"
    return _reg("0200", reduzido, classificacao, tipo, nome, "", situacao, "", "", "", "")


def _ler_referencia(*registros):
    return ler_arquivo(
        "referencia",
        _ref(_reg("0000", CNPJ_DA_EMPRESA), *registros),
        nome_arquivo="ref.txt",
    )


def test_superior_e_o_maior_prefixo_que_existe_no_cadastro(empresa):
    """Cadastro: `1` (sintética) e `1.1` (sintética, filha de `1`). Arquivo: `1` e `1.1.01`.
    O imediato de `1.1.01` é `1.1`, que existe no cadastro: a superior é `1.1`, sem aviso."""
    _cadastrar(empresa, "1", "Ativo", "ativo")
    _cadastrar(empresa, "1.1", "Circulante", "ativo", pai="1")
    resultado = _ler_referencia(
        _linha_0200("1", "1", False, "Ativo"),
        _linha_0200("2", "1.1.01", True, "Caixa"),
    )

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {})

    assert not previa.tem_erro, previa.ocorrencias
    caixa = next(item for item in previa.itens if item.codigo == "1.1.01")
    assert caixa.codigo_pai == "1.1"
    assert not any(o.campo == "codigo_pai" for o in previa.ocorrencias)


def test_superior_cai_no_maior_prefixo_existente_com_aviso_quando_nao_e_imediato(empresa):
    """Cadastro só com `1`. Arquivo: `1` e `1.1.01`. O imediato `1.1` não existe em lugar
    nenhum, então a superior é `1`, e o aviso diz que o imediato não existe. Nunca `1`
    calado."""
    _cadastrar(empresa, "1", "Ativo", "ativo")
    resultado = _ler_referencia(
        _linha_0200("1", "1", False, "Ativo"),
        _linha_0200("2", "1.1.01", True, "Caixa"),
    )

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {})

    caixa = next(item for item in previa.itens if item.codigo == "1.1.01")
    assert caixa.codigo_pai == "1"
    aviso = next(o for o in previa.ocorrencias if o.campo == "codigo_pai" and o.linha == 3)
    assert aviso.nivel == "aviso"
    assert "'1.1'" in aviso.mensagem and "imediato" in aviso.mensagem


def test_superior_no_arquivo_tem_preferencia_sobre_o_cadastro_so_pelo_maior_prefixo(empresa):
    """`1.1` está só no ARQUIVO (não no cadastro), `1` no cadastro. A superior de `1.1.01` é
    `1.1`, porque o arquivo também conta. Sem aviso: é o imediato."""
    _cadastrar(empresa, "1", "Ativo", "ativo")
    resultado = _ler_referencia(
        _linha_0200("2", "1.1", False, "Circulante"),
        _linha_0200("3", "1.1.01", True, "Caixa"),
    )

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {})

    assert not previa.tem_erro, previa.ocorrencias
    caixa = next(item for item in previa.itens if item.codigo == "1.1.01")
    assert caixa.codigo_pai == "1.1"


# -----------------------------------------------------------------------------
# T6 (A6): teto de contas e número de consultas
# -----------------------------------------------------------------------------


def test_arquivo_acima_do_teto_de_contas_e_recusado_com_nome_do_limite(empresa):
    linhas = [
        f"c{i};Conta {i};;S;ativo;devedora" for i in range(MAXIMO_DE_CONTAS_POR_IMPORTACAO + 1)
    ]
    resultado = _proprio(*linhas)

    with pytest.raises(ArquivoGrandeDemais, match=str(MAXIMO_DE_CONTAS_POR_IMPORTACAO)):
        conferir_plano(empresa, resultado, "so_acrescentar", {})
    assert not Conta.objects.filter(empresa=empresa).exists()


def test_aplicar_200_contas_fica_abaixo_de_10_consultas_por_conta(
    empresa, django_assert_max_num_queries
):
    """Meta da correção: no máximo 10 consultas por conta (2.000 para 200 contas). O teto deste
    teste é mais apertado, 1.700 para 201 contas (8,5 por conta), porque a medição do desenho
    atual deu 1.613. Uma consulta por conta a mais (a superior buscada no banco de novo, ou as
    quatro CHECK de classificação de volta) passa de 1.700 e reprova."""
    linhas = ["1;Ativo;;N;ativo;devedora"] + [f"1.{i};Conta {i};1;S;;" for i in range(200)]
    previa = conferir_plano(empresa, _proprio(*linhas), "so_acrescentar", {})

    with django_assert_max_num_queries(1700):
        resultado = _aplicar(empresa, previa)

    assert resultado.criadas == 201
    assert Conta.objects.filter(empresa=empresa).count() == 201


# -----------------------------------------------------------------------------
# T8 (A8): cadeia profunda
# -----------------------------------------------------------------------------


def _cadeia(profundidade):
    """Cadeia c0 <- c1 <- ... <- c{profundidade}, com a folha PRIMEIRO no arquivo."""
    linhas = [f"c{i};Nível {i};c{i - 1};N;;" for i in range(profundidade, 0, -1)]
    linhas.append("c0;Raiz;;N;ativo;devedora")
    return linhas


def test_cadeia_de_1200_niveis_na_ordem_inversa_e_erro_nomeado_e_nao_500(empresa):
    previa = conferir_plano(empresa, _proprio(*_cadeia(1200)), "so_acrescentar", {})

    assert previa.tem_erro
    mensagens = [o.mensagem for o in previa.ocorrencias if o.nivel == "erro"]
    assert any(
        f"passa de {MAXIMO_DE_NIVEIS_DE_SUPERIOR} níveis" in mensagem for mensagem in mensagens
    )


def test_cadeia_no_limite_de_50_niveis_e_aceita(empresa):
    previa = conferir_plano(
        empresa, _proprio(*_cadeia(MAXIMO_DE_NIVEIS_DE_SUPERIOR)), "so_acrescentar", {}
    )

    assert not previa.tem_erro, previa.ocorrencias


# -----------------------------------------------------------------------------
# Lacunas da seção 10 da auditoria
# -----------------------------------------------------------------------------


def test_exportacao_analiticas_inclui_as_sinteticas_necessarias_n11(empresa):
    """N11: `filtro=analiticas` leva a analítica E as sintéticas que ela precisa como superior.
    Sem as sintéticas, o arquivo não se reimporta (a superior precisa existir)."""
    _cadastrar(empresa, "1", "Ativo", "ativo")
    _cadastrar(empresa, "1.1", "Circulante", "ativo", pai="1")
    _cadastrar(empresa, "1.1.1", "Caixa", "ativo", pai="1.1", analitica=True)
    _cadastrar(empresa, "2", "Passivo", "passivo")
    _cadastrar(empresa, "2.1", "Fornecedores", "passivo", pai="2", analitica=True)
    _cadastrar(empresa, "3", "Receitas", "receita")

    arquivo = exportar_plano(empresa=empresa, formato="proprio", filtro="analiticas")

    codigos = {
        linha.split(";")[0] for linha in arquivo.conteudo.decode("utf-8").split("\r\n")[1:] if linha
    }
    assert codigos == {"1", "1.1", "1.1.1", "2", "2.1"}  # `3` não é analítica nem superior
    assert arquivo.quantidade_contas == 5
    assert arquivo.sinteticas_incluidas == 3  # `1`, `1.1` e `2` entraram só como superiores


def test_prefixo_vazio_ou_so_com_espacos_e_recusado_n13():
    with pytest.raises(ParametroInvalido, match="prefixo vazio"):
        validar_prefixos({"": "receita"})
    with pytest.raises(ParametroInvalido, match="prefixo vazio"):
        validar_prefixos({"   ": "receita"})


def test_prefixo_vazio_nao_chega_a_conferir_n13(empresa):
    with pytest.raises(ParametroInvalido):
        conferir_plano(empresa, _proprio("1;Ativo;;N;;"), "so_acrescentar", {"": "receita"})


def test_codigo_repetido_no_resultado_do_nucleo_e_erro_n_m19(empresa):
    """M19: o núcleo confere duplicidade mesmo que um leitor não tenha feito isso."""
    resultado = ResultadoLeitura(
        contas=[
            ContaLida(
                linha=2,
                codigo="1",
                nome="Ativo",
                codigo_pai=None,
                analitica=False,
                tipo="ativo",
                natureza="devedora",
                codigo_origem=None,
                referencial=None,
            ),
            ContaLida(
                linha=3,
                codigo="1",
                nome="Outro",
                codigo_pai=None,
                analitica=False,
                tipo="ativo",
                natureza="devedora",
                codigo_origem=None,
                referencial=None,
            ),
        ]
    )

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {})

    assert (3, "codigo") in _erros(previa)
    erro = next(o for o in previa.ocorrencias if o.linha == 3 and o.campo == "codigo")
    assert "repetido" in erro.mensagem and "linha 2" in erro.mensagem
    assert [item.acao for item in previa.itens] == ["criar", "recusada"]


def test_criar_conta_repetida_e_recusada_pela_validacao_do_modelo_m25(empresa):
    """M25: `full_clean` é a última linha de defesa. Código repetido não vira IntegrityError
    crua (500), e sim `ContaRecusadaNoCadastro`."""
    _cadastrar(empresa, "1", "Ativo", "ativo")

    with pytest.raises(ContaRecusadaNoCadastro):
        _cadastrar(empresa, "1", "De novo", "ativo")

    assert Conta.objects.filter(empresa=empresa, codigo="1").count() == 1


def test_criar_conta_com_nome_vazio_e_recusada_pelo_modelo_m25(empresa):
    """M25, a outra metade: o que só o `full_clean` valida (nome obrigatório) não chega ao banco
    quando a criação é chamada direto, sem passar pela conferência."""
    with pytest.raises(ContaRecusadaNoCadastro):
        _cadastrar(empresa, "1", "", "ativo")

    assert not Conta.objects.filter(empresa=empresa).exists()


def test_renomear_para_nome_vazio_ou_longo_e_recusado_n24(empresa):
    """N24: `full_clean` também na renomeação. Nome vazio ou acima de 200 não chega ao banco."""
    conta = _cadastrar(empresa, "1", "Ativo", "ativo")

    with pytest.raises(ContaRecusadaNoCadastro):
        renomear_conta_pelo_plano(conta=conta, nome="")
    with pytest.raises(ContaRecusadaNoCadastro):
        renomear_conta_pelo_plano(conta=conta, nome="x" * 201)

    conta.refresh_from_db()
    assert conta.nome == "Ativo"


def test_nome_de_arquivo_com_caminho_vai_so_com_o_nome_para_a_trilha_n10(empresa):
    """N10: o caminho do arquivo nunca entra na trilha, só o nome."""
    resultado = ler_arquivo(
        "proprio",
        f"{CABECALHO}\r\n1;Ativo;;N;ativo;devedora\r\n".encode(),
        nome_arquivo="/etc/pasta-de-trabalho/plano-teste.txt",
    )
    assert resultado.nome_arquivo == "plano-teste.txt"

    previa = conferir_plano(empresa, resultado, "so_acrescentar", {})
    _aplicar(empresa, previa)

    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.importado")
    assert trilha.detalhes["nome_arquivo"] == "plano-teste.txt"


# -----------------------------------------------------------------------------
# A12: avisos da prévia e trilha com o mapa de prefixos
# -----------------------------------------------------------------------------


def test_previa_avisa_que_conta_nova_nasce_sem_classificacao(empresa):
    previa = conferir_plano(empresa, _proprio("1;Ativo;;N;ativo;devedora"), "so_acrescentar", {})

    avisos = [o for o in previa.ocorrencias if o.campo == "classificacao"]
    assert len(avisos) == 1 and avisos[0].nivel == "aviso" and avisos[0].linha == 0
    assert "classifique depois no plano de contas" in avisos[0].mensagem


def test_sem_conta_nova_nao_ha_aviso_de_classificacao(empresa):
    _cadastrar(empresa, "1", "Ativo", "ativo")

    previa = conferir_plano(empresa, _proprio("1;Ativo;;N;ativo;devedora"), "so_acrescentar", {})

    assert not any(o.campo == "classificacao" for o in previa.ocorrencias)


def test_erro_de_linha_nao_repete_a_frase_arquivo_sem_conta_a12(empresa):
    previa = conferir_plano(empresa, _proprio("1;Ativo;;X;ativo;devedora"), "so_acrescentar", {})

    assert previa.tem_erro
    assert not any("nenhuma conta" in o.mensagem for o in previa.ocorrencias)


def test_trilha_da_importacao_guarda_o_mapa_de_prefixos_usado_a12(empresa):
    previa = conferir_plano(empresa, _proprio("1;Ativo;;N;;"), "so_acrescentar", {"1": "ativo"})

    _aplicar(empresa, previa)

    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.importado")
    assert trilha.detalhes["prefixos"] == {"1": "ativo"}
