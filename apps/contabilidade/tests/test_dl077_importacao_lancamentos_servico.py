"""Serviço da importação de lançamentos com área de conferência (DL-077, fatia 3, frente A).

Dados SINTÉTICOS: escritório e empresas de teste, plano do `cenario_dl077_exportacao`, valores
redondos. Nenhum arquivo real entra aqui (RC-167). Os testes do banco usam PostgreSQL, porque a
imutabilidade é por gatilho e o gatilho só existe no PostgreSQL.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.models import (
    Competencia,
    DeParaConta,
    EstadoImportacaoLancamentos,
    ImportacaoLancamentos,
    ImportacaoLancamentosImutavel,
    LancamentoContabil,
    LancamentoImportado,
    TipoPartida,
)
from apps.contabilidade.services import (
    LancamentoInvalido,
    criar_lancamento,
    encerrar_competencia,
    reabrir_competencia,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)

pytestmark = pytest.mark.django_db

CABECALHO = "numero;data;historico;conta;lado;valor\r\n"


def _arquivo(*linhas):
    return (CABECALHO + "".join(linha + "\r\n" for linha in linhas)).encode("utf-8")


def _lancamento_simples(
    numero, data="2026-03-10", historico="Compra", conta_d="1.1.1", conta_c="2.1", valor="100.00"
):
    return [
        f"{numero};{data};{historico};{conta_d};D;{valor}",
        f"{numero};{data};{historico};{conta_c};C;{valor}",
    ]


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório Importação", "55555555000155")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Importação Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    return {"empresa": empresa, "contas": contas, "escritorio": escritorio}


def _receber(empresa, *linhas, formato="proprio", nome="lancamentos.txt"):
    return servico.receber(
        empresa=empresa,
        formato=formato,
        conteudo=_arquivo(*linhas),
        nome_arquivo=nome,
        usuario=None,
    )


def _aceitar_o_arquivo_se_preciso(importacao):
    """A11: arquivo sem empresa declarada (próprio, ECD sem 0000, Excel) pede o aceite do aviso.

    Este helper dá o passo que o contador dá na tela. Os testes de A11 não o usam: chamam o
    serviço direto, para ver a recusa sem aceite.
    """
    if importacao.exige_aceite_do_arquivo and not importacao.aceite_do_arquivo:
        servico.aceitar_avisos(importacao, [], aceitar_arquivo=True)


def _efetivar(importacao, politica=servico.TUDO_OU_NADA):
    _aceitar_o_arquivo_se_preciso(importacao)
    return servico.efetivar(importacao, politica=politica, usuario=None)


def _ocorrencias_com_erro(importacao):
    return [
        (linha.numero_origem, o["campo"], o["mensagem"])
        for linha in importacao.lancamentos.all()
        for o in linha.ocorrencias
        if o["nivel"] == "erro"
    ]


# ---------------------------------------------------------------------------
# Recebimento: nada entra no Diário
# ---------------------------------------------------------------------------


def test_receber_grava_em_conferencia_e_nao_mexe_no_diario(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))

    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert importacao.quantidade_lancamentos == 1
    assert importacao.quantidade_com_erro == 0
    assert importacao.soma_debitos == Decimal("100.00") == importacao.soma_creditos
    assert importacao.nome_arquivo == "lancamentos.txt"
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0
    assert LancamentoImportado.objects.get(importacao=importacao).lancamento is None


def test_receber_guarda_so_o_nome_do_arquivo_e_nao_o_caminho(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7), nome="/home/fred/x/lanc.txt")
    assert importacao.nome_arquivo == "lanc.txt"


def test_mesmo_arquivo_recebido_de_novo_e_recusado_citando_a_existente(cenario):
    primeira = _receber(cenario["empresa"], *_lancamento_simples(7))

    with pytest.raises(servico.ImportacaoJaExiste) as excinfo:
        _receber(cenario["empresa"], *_lancamento_simples(7))

    assert excinfo.value.importacao_id == primeira.pk
    assert f"importação {primeira.pk}" in str(excinfo.value)


def test_arquivo_descartado_pode_ser_recebido_de_novo(cenario):
    primeira = _receber(cenario["empresa"], *_lancamento_simples(7))
    servico.descartar(primeira, motivo="arquivo de teste")

    nova = _receber(cenario["empresa"], *_lancamento_simples(7))

    assert nova.pk != primeira.pk
    assert nova.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA


def test_mesmo_arquivo_em_outra_empresa_nao_e_duplicado(cenario):
    outra = criar_empresa(
        escritorio=cenario["escritorio"], razao_social="Outra Ltda", cnpj="88888888000188"
    )
    _receber(cenario["empresa"], *_lancamento_simples(7))
    criar_plano(outra)

    importacao = _receber(outra, *_lancamento_simples(7))

    assert importacao.empresa == outra


def test_cnpj_do_arquivo_de_outra_empresa_recusa_sem_expor_os_numeros(cenario):
    conteudo = (
        "|0000|LECD|01012026|31012026|Outra Ltda|88888888000188|SP|||\r\n"
        "|I200|1|05012026|100,00|N||\r\n|I250|1.1.1||100,00|D|||X||\r\n|I250|2.1||100,00|C|||X||\r\n"
    ).encode("iso-8859-1")

    with pytest.raises(servico.ImportacaoRecusada) as excinfo:
        servico.receber(
            empresa=cenario["empresa"],
            formato="ecd",
            conteudo=conteudo,
            nome_arquivo="x.txt",
            usuario=None,
        )

    assert "88888888000188" not in str(excinfo.value)
    assert "diferente" in str(excinfo.value)
    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


def test_formato_que_nao_le_lancamentos_e_recusado_com_nome(cenario):
    with pytest.raises(servico.ImportacaoRecusada, match="não suportado"):
        servico.receber(
            empresa=cenario["empresa"],
            formato="nenhum",
            conteudo=b"",
            nome_arquivo="x",
            usuario=None,
        )


def test_limite_de_lancamentos_por_arquivo_recusa_com_mensagem(cenario, monkeypatch):
    monkeypatch.setattr(servico, "LIMITE_DE_LANCAMENTOS_POR_ARQUIVO", 1)

    with pytest.raises(servico.ImportacaoRecusada, match="limite por arquivo é 1"):
        _receber(cenario["empresa"], *_lancamento_simples(1), *_lancamento_simples(2))


# ---------------------------------------------------------------------------
# Conferência: cada recusa (erro nunca efetiva)
# ---------------------------------------------------------------------------


def test_debito_diferente_de_credito_e_erro_e_nao_efetiva(cenario):
    importacao = _receber(
        cenario["empresa"],
        "7;2026-03-10;Compra;1.1.1;D;100.00",
        "7;2026-03-10;Compra;2.1;C;90.00",
    )

    assert importacao.quantidade_com_erro == 1
    with pytest.raises(servico.ImportacaoNaoEfetivada) as excinfo:
        _efetivar(importacao)
    assert any("débitos" in o["mensagem"] for o in excinfo.value.ocorrencias)
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0


def test_competencia_encerrada_e_erro_e_reabrir_e_reconferir_libera(cenario):
    empresa = cenario["empresa"]
    importacao = _receber(empresa, *_lancamento_simples(7, data="2026-03-10"))
    encerrar_competencia(empresa=empresa, ano=2026, mes=3, usuario=None)

    importacao = servico.reconferir(importacao)
    assert importacao.quantidade_com_erro == 1
    assert any("encerrada" in mensagem for _n, _c, mensagem in _ocorrencias_com_erro(importacao))
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        _efetivar(importacao)

    reabrir_competencia(empresa=empresa, ano=2026, mes=3, usuario=None, motivo="ajuste de teste")
    importacao = servico.reconferir(importacao)

    assert importacao.quantidade_com_erro == 0
    resultado = _efetivar(importacao)
    assert resultado.criados == 1
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == 1


def test_competencia_inexistente_e_aberta_e_a_efetivacao_a_cria(cenario):
    empresa = cenario["empresa"]
    assert not Competencia.objects.filter(empresa=empresa, ano=2026, mes=8).exists()
    importacao = _receber(empresa, *_lancamento_simples(7, data="2026-08-10"))

    assert importacao.quantidade_com_erro == 0
    _efetivar(importacao)
    assert Competencia.objects.filter(empresa=empresa, ano=2026, mes=8).exists()


def test_conta_sintetica_e_erro_e_nao_recebe_lancamento(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7, conta_d="1.1"))

    assert importacao.quantidade_com_erro == 1
    assert any("sintética" in mensagem for _n, _c, mensagem in _ocorrencias_com_erro(importacao))


def test_conta_inexistente_e_erro_que_lista_o_codigo_de_origem(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7, conta_c="9.9"))

    mensagens = [mensagem for _n, _c, mensagem in _ocorrencias_com_erro(importacao)]
    assert any("'9.9'" in mensagem and "de-para" in mensagem for mensagem in mensagens)


def test_conta_inativa_e_erro(cenario):
    conta = cenario["contas"]["2.1"]
    conta.ativo = False
    conta.save(update_fields=["ativo"])

    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))

    assert any("inativa" in mensagem for _n, _c, mensagem in _ocorrencias_com_erro(importacao))


def test_historico_acima_de_300_e_erro_e_nunca_truncado(cenario):
    longo = "x" * 301
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7, historico=longo))

    (linha,) = importacao.lancamentos.all()
    assert len(linha.historico) == 301
    assert any(
        "301 caracteres" in mensagem for _n, _c, mensagem in _ocorrencias_com_erro(importacao)
    )
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        _efetivar(importacao)


def test_historicos_diferentes_na_mesma_partida_viram_aviso_e_so_entram_com_aceite(cenario):
    importacao = _receber(
        cenario["empresa"],
        "7;2026-03-10;Compra A;1.1.1;D;100.00",
        "7;2026-03-10;Compra B;2.1;C;100.00",
    )

    (linha,) = importacao.lancamentos.all()
    assert linha.historico == "Compra A | Compra B"
    assert linha.tem_aviso and not linha.tem_erro
    with pytest.raises(servico.ImportacaoNaoEfetivada):
        _efetivar(importacao)

    assert servico.aceitar_avisos(importacao, ["7"]) == 1
    resultado = _efetivar(importacao)
    assert resultado.criados == 1
    assert (
        LancamentoContabil.objects.get(empresa=cenario["empresa"]).historico
        == "Compra A | Compra B"
    )


def test_aceitar_avisos_recusa_lancamento_sem_aviso_e_numero_que_nao_existe(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))

    with pytest.raises(servico.ImportacaoRecusada, match="não têm avisos"):
        servico.aceitar_avisos(importacao, ["7"])
    with pytest.raises(servico.ImportacaoRecusada, match="não estão nesta importação"):
        servico.aceitar_avisos(importacao, ["99"])


def test_lancamento_com_uma_partida_so_e_erro_de_conferencia(cenario):
    importacao = _receber(cenario["empresa"], "7;2026-03-10;Sozinho;1.1.1;D;100.00")

    assert importacao.quantidade_com_erro == 1
    assert any("duas partidas" in m for _n, _c, m in _ocorrencias_com_erro(importacao))


# ---------------------------------------------------------------------------
# De-para
# ---------------------------------------------------------------------------


def test_referencia_resolve_so_pelo_de_para_e_nunca_pelo_codigo_do_plano(cenario):
    # Código reduzido "1" existe no plano como conta "1" (sintética). No sistema de referência
    # o código do arquivo é REDUZIDO: ele não pode ser lido como a conta de mesmo número.
    arquivo = (
        "|0000|" + CNPJ_DA_EMPRESA + "|\r\n|6000|X||||\r\n"
        "|6100|10/03/2026|1|2|100,00||Compra||||\r\n"
    ).encode("iso-8859-1")
    importacao = servico.receber(
        empresa=cenario["empresa"],
        formato="referencia",
        conteudo=arquivo,
        nome_arquivo="r.txt",
        usuario=None,
    )

    mensagens = [m for _n, _c, m in _ocorrencias_com_erro(importacao)]
    assert any("'1'" in m for m in mensagens)
    assert any("'2'" in m for m in mensagens)


def test_referencia_com_de_para_efetiva_com_as_contas_mapeadas(cenario):
    contas = cenario["contas"]
    servico.definir_de_para(
        empresa=cenario["empresa"],
        formato="referencia",
        codigo_origem="3",
        conta=contas["1.1.1"],
        usuario=None,
    )
    servico.definir_de_para(
        empresa=cenario["empresa"],
        formato="referencia",
        codigo_origem="12",
        conta=contas["2.1"],
        usuario=None,
    )
    arquivo = (
        "|0000|" + CNPJ_DA_EMPRESA + "|\r\n|6000|X||||\r\n"
        "|6100|10/03/2026|3|12|100,00||Compra||||\r\n"
    ).encode("iso-8859-1")
    importacao = servico.receber(
        empresa=cenario["empresa"],
        formato="referencia",
        conteudo=arquivo,
        nome_arquivo="r.txt",
        usuario=None,
    )
    assert importacao.quantidade_com_erro == 0

    _efetivar(importacao)

    lancamento = LancamentoContabil.objects.get(empresa=cenario["empresa"])
    pares = sorted((i.conta.codigo, i.tipo, i.valor) for i in lancamento.itens.all())
    assert pares == [
        ("1.1.1", TipoPartida.DEBITO, Decimal("100.00")),
        ("2.1", TipoPartida.CREDITO, Decimal("100.00")),
    ]


def test_de_para_de_outra_empresa_nao_resolve_a_importacao(cenario):
    """Filtro de empresa no de-para: a tabela de outra empresa nunca vale aqui (h)."""
    outra = criar_empresa(
        escritorio=cenario["escritorio"], razao_social="Vizinha Ltda", cnpj="88888888000188"
    )
    outras_contas = criar_plano(outra)
    servico.definir_de_para(
        empresa=outra,
        formato="referencia",
        codigo_origem="3",
        conta=outras_contas["1.1.1"],
        usuario=None,
    )
    arquivo = (
        "|0000|" + CNPJ_DA_EMPRESA + "|\r\n|6000|X||||\r\n"
        "|6100|10/03/2026|3|12|100,00||Compra||||\r\n"
    ).encode("iso-8859-1")

    importacao = servico.receber(
        empresa=cenario["empresa"],
        formato="referencia",
        conteudo=arquivo,
        nome_arquivo="r.txt",
        usuario=None,
    )

    assert importacao.quantidade_com_erro == 1
    assert any("'3'" in m for _n, _c, m in _ocorrencias_com_erro(importacao))


def test_definir_de_para_com_conta_de_outra_empresa_e_recusado(cenario):
    outra = criar_empresa(
        escritorio=cenario["escritorio"], razao_social="Vizinha Ltda", cnpj="88888888000188"
    )
    conta_alheia = criar_plano(outra)["1.1.1"]

    with pytest.raises(servico.ImportacaoRecusada, match="não pertence a esta empresa"):
        servico.definir_de_para(
            empresa=cenario["empresa"],
            formato="referencia",
            codigo_origem="3",
            conta=conta_alheia,
            usuario=None,
        )
    assert not DeParaConta.objects.filter(empresa=cenario["empresa"]).exists()


# ---------------------------------------------------------------------------
# Políticas, atomicidade, idempotência, prefixo reservado
# ---------------------------------------------------------------------------


def test_tudo_ou_nada_recusa_com_um_erro_e_so_validos_efetiva_o_resto(cenario):
    importacao = _receber(
        cenario["empresa"],
        *_lancamento_simples(1, data="2026-03-10"),
        "2;2026-03-11;Ruim;1.1.1;D;100.00",
        "2;2026-03-11;Ruim;2.1;C;90.00",
    )

    with pytest.raises(servico.ImportacaoNaoEfetivada):
        _efetivar(importacao, politica=servico.TUDO_OU_NADA)
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0

    resultado = _efetivar(importacao, politica=servico.SO_VALIDOS)

    assert resultado.criados == 1
    assert resultado.nao_efetivados == ["2"]
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 1
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EFETIVADA
    assert importacao.quantidade_nao_efetivados == 1


def test_politica_desconhecida_e_recusada(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))
    with pytest.raises(servico.ImportacaoRecusada, match="desconhecida"):
        _efetivar(importacao, politica="tanto_faz")


def test_falha_no_meio_da_efetivacao_nao_deixa_lancamento_nem_estado(cenario, monkeypatch):
    importacao = _receber(
        cenario["empresa"],
        *_lancamento_simples(1, data="2026-03-10"),
        *_lancamento_simples(2, data="2026-03-11"),
    )
    chamadas = {"n": 0}
    original = servico.criar_lancamento

    def falha_na_segunda(**kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise LancamentoInvalido("falha simulada no meio da efetivação")
        return original(**kwargs)

    monkeypatch.setattr(servico, "criar_lancamento", falha_na_segunda)
    with pytest.raises(LancamentoInvalido):
        _efetivar(importacao)

    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert not LancamentoImportado.objects.filter(
        importacao=importacao, lancamento__isnull=False
    ).exists()


def test_efetivar_duas_vezes_nao_duplica_e_a_segunda_e_recusada(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))
    _efetivar(importacao)

    with pytest.raises(servico.ImportacaoEmEstadoInvalido):
        _efetivar(importacao)

    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 1


def test_mesmo_numero_em_arquivos_diferentes_nao_colide(cenario):
    primeiro = _receber(cenario["empresa"], *_lancamento_simples(7, valor="100.00"), nome="a.txt")
    segundo = _receber(cenario["empresa"], *_lancamento_simples(7, valor="250.00"), nome="b.txt")

    _efetivar(primeiro)
    _efetivar(segundo)

    lancamentos = LancamentoContabil.objects.filter(empresa=cenario["empresa"])
    assert lancamentos.count() == 2
    chaves = sorted(lancamentos.values_list("chave_idempotencia", flat=True))
    assert chaves == sorted([f"importacao:{primeiro.sha256}:7", f"importacao:{segundo.sha256}:7"])


def test_chave_de_importacao_so_pode_ser_usada_pela_efetivacao(cenario):
    with pytest.raises(LancamentoInvalido, match="reservado"):
        criar_lancamento(
            empresa=cenario["empresa"],
            data=date(2026, 3, 10),
            historico="Forjado",
            itens=[
                {
                    "conta": cenario["contas"]["1.1.1"],
                    "tipo": TipoPartida.DEBITO,
                    "valor": Decimal("1.00"),
                },
                {
                    "conta": cenario["contas"]["2.1"],
                    "tipo": TipoPartida.CREDITO,
                    "valor": Decimal("1.00"),
                },
            ],
            chave_idempotencia="importacao:abc:1",
        )

    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa"]).exists()

    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Pela importação",
        itens=[
            {
                "conta": cenario["contas"]["1.1.1"],
                "tipo": TipoPartida.DEBITO,
                "valor": Decimal("1.00"),
            },
            {
                "conta": cenario["contas"]["2.1"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("1.00"),
            },
        ],
        chave_idempotencia="importacao:abc:1",
        permitir_prefixo_da_importacao=True,
    )
    assert lancamento.criado_agora is True


def test_descartar_exige_motivo_e_impede_efetivar(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))
    with pytest.raises(servico.ImportacaoRecusada, match="motivo"):
        servico.descartar(importacao, motivo="   ")

    servico.descartar(importacao, motivo="arquivo enviado por engano")
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.DESCARTADA
    with pytest.raises(servico.ImportacaoEmEstadoInvalido):
        _efetivar(importacao)


# ---------------------------------------------------------------------------
# Imutabilidade: a importação fechada não muda (Python e gatilho do banco)
# ---------------------------------------------------------------------------


def test_importacao_efetivada_nao_muda_nem_se_exclui_pelo_modelo(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))
    _efetivar(importacao)
    importacao.refresh_from_db()

    importacao.motivo_do_descarte = "tentativa"
    with pytest.raises(ImportacaoLancamentosImutavel):
        importacao.save()
    with pytest.raises(ImportacaoLancamentosImutavel):
        importacao.delete()


def test_gatilho_do_banco_recusa_update_e_delete_de_importacao_fechada(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))
    _efetivar(importacao)

    with pytest.raises(IntegrityError, match="imutavel|imutável|não pode ser alterada"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE contabilidade_importacaolancamentos "
                    "SET nome_arquivo = 'x' WHERE id = %s",
                    [importacao.pk],
                )
    with pytest.raises(IntegrityError, match="excluída|excluido|não pode ser excluída"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM contabilidade_importacaolancamentos WHERE id = %s", [importacao.pk]
                )


def test_gatilho_recusa_alterar_linha_de_importacao_fechada(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))
    _efetivar(importacao)
    linha = LancamentoImportado.objects.get(importacao=importacao)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE contabilidade_lancamentoimportado SET historico = 'x' WHERE id = %s",
                    [linha.pk],
                )


def test_linha_de_importacao_nao_pode_ser_excluida_mesmo_em_conferencia(cenario):
    importacao = _receber(cenario["empresa"], *_lancamento_simples(7))
    linha = LancamentoImportado.objects.get(importacao=importacao)
    with pytest.raises(ImportacaoLancamentosImutavel):
        linha.delete()


# ---------------------------------------------------------------------------
# Isolamento e trilha
# ---------------------------------------------------------------------------


def test_listar_importacoes_so_traz_a_empresa_pedida(cenario):
    outra = criar_empresa(
        escritorio=cenario["escritorio"], razao_social="Vizinha Ltda", cnpj="88888888000188"
    )
    criar_plano(outra)
    _receber(cenario["empresa"], *_lancamento_simples(7))
    _receber(outra, *_lancamento_simples(7))

    listadas = list(servico.listar_importacoes(cenario["empresa"]))

    assert len(listadas) == 1
    assert listadas[0].empresa == cenario["empresa"]


def test_trilha_da_efetivacao_tem_sha_politica_e_contagens_sem_texto(cenario):
    from apps.auditoria.models import RegistroAuditoria

    importacao = _receber(cenario["empresa"], *_lancamento_simples(7, historico="Dado do cliente"))
    _efetivar(importacao, politica=servico.TUDO_OU_NADA)

    registro = RegistroAuditoria.objects.get(acao="lancamentos.importacao.efetivada")
    assert registro.detalhes["sha256"] == importacao.sha256
    assert registro.detalhes["politica"] == servico.TUDO_OU_NADA
    assert registro.detalhes["criados"] == 1
    assert "Dado do cliente" not in str(registro.detalhes)
