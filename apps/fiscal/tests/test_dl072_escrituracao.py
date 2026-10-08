"""DL-072 (frente A) — escrituração das NFS-e prestadas, camada de domínio.

Critérios do plano cobertos aqui: 1 (competência = dCompet), 2 (efetivar grava
natureza, datas e valores; trilha na mesma transação), 3 (sugestão de natureza
e troca pelo contador antes de efetivar), 4 (estorno exige motivo, devolve a
nota a "a escriturar", fica na trilha), 5 (cancelada não se efetiva; cancelamento
depois gera pendência, que some com o estorno), 7 (tomada não entra),
8 (conferência: recebidas = escrituradas + pendentes; avisos e bloqueios).

Dados 100% sintéticos, gerados por `xml_sinteticos.xml_nfse`/`xml_evento`
e recebidos pelo pipeline real (`services.receber_envio`).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao as servico
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    EstadoEscrituracao,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import (
    chave_nfse_de,
    identificador_nfse,
    xml_evento,
    xml_nfse,
)

pytestmark = pytest.mark.django_db

NATUREZA_DEVIDO = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
NATUREZA_RETIDO = NaturezaOperacao.PRESTADO_ISS_RETIDO
NATUREZA_OUTRO_MUNICIPIO = NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO


def _receber(escritorio, usuario, conteudo, nome="nota.xml"):
    return services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo=nome
    )


def _nota(escritorio, usuario, sufixo=1, **kwargs):
    """NFS-e sintética recebida. Prestador = empresa_a; tomador = empresa_a2."""
    identificador = identificador_nfse(sufixo)
    _receber(
        escritorio,
        usuario,
        xml_nfse(identificador=identificador, numero=str(sufixo), **kwargs),
    )
    return DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)


def _vinculo(documento, empresa, papel=PapelDocumento.PRESTADOR):
    return VinculoDocumentoEmpresa.objects.get(documento=documento, empresa=empresa, papel=papel)


def _cancelar(escritorio, usuario, documento, sufixo_evento=1):
    """Recebe o evento e100101-equivalente (cancelamento) da nota."""
    _receber(
        escritorio,
        usuario,
        xml_evento(chave_nfse=chave_nfse_de(documento.identificador), codigo="e101101"),
        nome=f"evento{sufixo_evento}.xml",
    )


def _trilha(acao):
    return list(RegistroAuditoria.objects.filter(acao=acao).order_by("id"))


# ---------------------------------------------------------------------------
# Critério 1 — a competência é dCompet, nunca dhEmi (HI-57)
# ---------------------------------------------------------------------------


def test_nota_entra_no_mes_de_dcompet_e_nao_no_de_dhemi(escritorio_a, empresa_a, usuario_gestor_a):
    _nota(
        escritorio_a,
        usuario_gestor_a,
        dh_emi="2024-01-15T10:00:00-03:00",
        d_compet="2024-02-01",
    )

    janeiro = servico.notas_a_escriturar(empresa_a, 2024, 1)
    fevereiro = servico.notas_a_escriturar(empresa_a, 2024, 2)

    assert janeiro == []
    assert len(fevereiro) == 1
    assert fevereiro[0].situacao == servico.SITUACAO_A_ESCRITURAR
    assert fevereiro[0].competencia_difere_da_emissao is True


def test_data_de_emissao_usa_o_dia_de_brasilia_e_nao_o_utc(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # 22h de 31/01 em Brasília é 01/02 em UTC. Se a data de emissão saísse do
    # instante UTC, o aviso e a data guardada estariam errados em um dia.
    _nota(
        escritorio_a,
        usuario_gestor_a,
        dh_emi="2024-01-31T22:00:00-03:00",
        d_compet="2024-01-31",
    )

    (nota,) = servico.notas_a_escriturar(empresa_a, 2024, 1)

    assert nota.data_emissao == date(2024, 1, 31)
    assert nota.competencia_difere_da_emissao is False


# ---------------------------------------------------------------------------
# Critério 2 — efetivar grava natureza, datas e valores; trilha na transação
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("v_serv", "v_liq"),
    [
        ("1234.56", "1111.11"),
        ("0.10", "0.10"),  # centavos: nunca float
        ("999999999999999.99", "999999999999999.99"),  # limite de TSDec15V2
    ],
)
def test_efetivar_grava_natureza_datas_e_valores_exatos(
    escritorio_a, empresa_a, usuario_gestor_a, v_serv, v_liq
):
    nota = _nota(
        escritorio_a,
        usuario_gestor_a,
        dh_emi="2024-01-15T10:00:00-03:00",
        d_compet="2024-02-01",
        v_serv=v_serv,
        v_liq=v_liq,
        tp_ret_issqn="1",
    )

    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a
    )

    gravada = EscrituracaoFiscal.objects.get(pk=escrituracao.pk)
    assert gravada.estado == EstadoEscrituracao.EFETIVADA
    assert gravada.natureza == NATUREZA_DEVIDO
    assert gravada.data_emissao == date(2024, 1, 15)
    assert gravada.data_competencia == date(2024, 2, 1)
    assert gravada.valor_servico == Decimal(v_serv)
    assert gravada.valor_liquido == Decimal(v_liq)
    assert isinstance(gravada.valor_servico, Decimal)
    assert gravada.iss_retido is False
    assert gravada.efetivada_em is not None
    assert gravada.efetivada_por_id == usuario_gestor_a.pk
    assert gravada.empresa_id == empresa_a.pk


def test_efetivar_registra_trilha_com_antes_e_depois(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, v_serv="500.00", v_liq="450.00")

    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a
    )

    (registro,) = _trilha("escrituracao_fiscal.efetivada")
    assert registro.objeto_tipo == "EscrituracaoFiscal"
    assert registro.objeto_id == str(escrituracao.pk)
    assert registro.detalhes["antes"] is None
    assert registro.detalhes["depois"]["estado"] == EstadoEscrituracao.EFETIVADA
    assert registro.detalhes["depois"]["valor_servico"] == "500.00"
    assert registro.detalhes["natureza_sugerida"] == NATUREZA_DEVIDO


def test_falha_na_trilha_desfaz_a_efetivacao(
    escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    # Atomicidade (AGENTS.md §8): efetivação e trilha são uma transação só. Se
    # a trilha falha, a escrituração não pode ter sido gravada.
    nota = _nota(escritorio_a, usuario_gestor_a)

    def trilha_quebrada(**_kwargs):
        raise RuntimeError("falha simulada da trilha")

    monkeypatch.setattr(servico, "registrar", trilha_quebrada)

    with pytest.raises(RuntimeError, match="falha simulada"):
        servico.efetivar_escrituracao(_vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a)

    assert EscrituracaoFiscal.objects.count() == 0


# ---------------------------------------------------------------------------
# Critério 3 — natureza sugerida; o contador confirma; a sugestão não é gravada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tp_ret_issqn", "esperada"),
    [
        ("1", NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR),
        ("2", NaturezaOperacao.PRESTADO_ISS_RETIDO),
        ("3", NaturezaOperacao.PRESTADO_ISS_RETIDO),
    ],
)
def test_sugestao_retido_so_para_tpretissqn_2_ou_3(
    escritorio_a, empresa_a, usuario_gestor_a, tp_ret_issqn, esperada
):
    nota = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn=tp_ret_issqn)

    assert servico.sugerir_natureza(nota) == esperada
    # A sugestão também chega pela lista (é o que a tela e a API mostram).
    (linha,) = servico.notas_a_escriturar(empresa_a, 2024, 1)
    assert linha.natureza_sugerida == esperada


def test_sugestao_nunca_presume_outro_municipio_nem_sem_incidencia(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # `empresa_a` precisa existir: sem um participante do escritório, o
    # pipeline recusa a nota (não há o que vincular).
    # O XML não diz o município de incidência nem se há exceção de ISS. Quem
    # decide é o contador; a sugestão só distingue retido de devido.
    for tp in ("1", "2", "3"):
        nota = _nota(escritorio_a, usuario_gestor_a, sufixo=int(tp) + 10, tp_ret_issqn=tp)
        assert servico.sugerir_natureza(nota) not in {
            NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO,
            NaturezaOperacao.PRESTADO_SEM_INCIDENCIA_ISS,
        }


def test_sugestao_nao_grava_escrituracao(escritorio_a, empresa_a, usuario_gestor_a):
    _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="2")

    servico.notas_a_escriturar(empresa_a, 2024, 1)
    servico.conferencia(empresa_a, 2024, 1)

    assert EscrituracaoFiscal.objects.count() == 0


def test_contador_troca_a_sugestao_no_rascunho_e_efetiva_a_escolhida(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="2")
    vinculo = _vinculo(nota, empresa_a)

    rascunho = servico.salvar_rascunho(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    (linha,) = servico.notas_a_escriturar(empresa_a, 2024, 1)
    assert linha.situacao == servico.SITUACAO_RASCUNHO

    # Troca no rascunho: continua a MESMA linha, não cria outra.
    rascunho = servico.salvar_rascunho(vinculo, NATUREZA_OUTRO_MUNICIPIO, usuario_gestor_a)
    efetivada = servico.efetivar_escrituracao(vinculo, NATUREZA_OUTRO_MUNICIPIO, usuario_gestor_a)

    assert efetivada.pk == rascunho.pk
    assert EscrituracaoFiscal.objects.count() == 1
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert efetivada.natureza == NATUREZA_OUTRO_MUNICIPIO
    assert efetivada.iss_retido is True  # copiado do documento, não da escolha
    (registro,) = _trilha("escrituracao_fiscal.efetivada")
    assert registro.detalhes["natureza_sugerida"] == NATUREZA_RETIDO


def test_natureza_fora_do_catalogo_e_recusada_sem_gravar(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)

    with pytest.raises(servico.EntradaInvalidaEscrituracao, match="desconhecida"):
        servico.efetivar_escrituracao(
            _vinculo(nota, empresa_a), "aliquota-5-por-cento", usuario_gestor_a
        )

    assert EscrituracaoFiscal.objects.count() == 0


# ---------------------------------------------------------------------------
# Critério 4 (domínio) — estorno com motivo, devolve a nota, fica na trilha
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_estorno_sem_motivo_e_recusado(escritorio_a, empresa_a, usuario_gestor_a, motivo):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a
    )

    with pytest.raises(servico.EntradaInvalidaEscrituracao, match="motivo"):
        servico.estornar_escrituracao(escrituracao, motivo, usuario_gestor_a)

    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).estado == (
        EstadoEscrituracao.EFETIVADA
    )


def test_estorno_com_motivo_longo_demais_e_recusado(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a
    )

    with pytest.raises(servico.EntradaInvalidaEscrituracao, match="500"):
        servico.estornar_escrituracao(escrituracao, "x" * 501, usuario_gestor_a)


def test_estorno_devolve_a_nota_para_a_escriturar_e_fica_na_trilha(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    escrituracao = servico.efetivar_escrituracao(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)

    estornada = servico.estornar_escrituracao(
        escrituracao, "  valor do serviço digitado errado  ", usuario_gestor_a
    )

    assert estornada.estado == EstadoEscrituracao.ESTORNADA
    assert estornada.motivo_estorno == "valor do serviço digitado errado"  # sem espaço
    assert estornada.estornada_em is not None
    # A linha NÃO some: o histórico é o próprio estorno.
    assert EscrituracaoFiscal.objects.filter(pk=escrituracao.pk).count() == 1
    (linha,) = servico.notas_a_escriturar(empresa_a, 2024, 1)
    assert linha.situacao == servico.SITUACAO_A_ESCRITURAR

    (registro,) = _trilha("escrituracao_fiscal.estornada")
    assert registro.detalhes["antes"]["estado"] == EstadoEscrituracao.EFETIVADA
    assert registro.detalhes["depois"]["estado"] == EstadoEscrituracao.ESTORNADA
    assert registro.detalhes["depois"]["motivo_estorno"] == "valor do serviço digitado errado"


def test_reefetivar_depois_do_estorno_cria_outra_linha(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    primeira = servico.efetivar_escrituracao(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)
    servico.estornar_escrituracao(primeira, "erro de natureza", usuario_gestor_a)

    segunda = servico.efetivar_escrituracao(vinculo, NATUREZA_RETIDO, usuario_gestor_a)

    assert segunda.pk != primeira.pk
    assert segunda.criada_agora is True
    assert EscrituracaoFiscal.objects.count() == 2
    assert len(_trilha("escrituracao_fiscal.efetivada")) == 2


@pytest.mark.parametrize("acao", ["estornar", "estornar_duas_vezes"])
def test_so_efetivada_pode_ser_estornada(escritorio_a, empresa_a, usuario_gestor_a, acao):
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    if acao == "estornar":
        rascunho = servico.salvar_rascunho(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)
        with pytest.raises(servico.EscrituracaoErro, match="Só escrituração efetivada"):
            servico.estornar_escrituracao(rascunho, "motivo", usuario_gestor_a)
    else:
        efetivada = servico.efetivar_escrituracao(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)
        servico.estornar_escrituracao(efetivada, "primeiro", usuario_gestor_a)
        with pytest.raises(servico.EscrituracaoErro, match="Só escrituração efetivada"):
            servico.estornar_escrituracao(efetivada, "segundo", usuario_gestor_a)


# ---------------------------------------------------------------------------
# Critério 5 — cancelada não se efetiva; cancelamento depois gera pendência
# ---------------------------------------------------------------------------


def test_nota_cancelada_nao_e_efetivada(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _cancelar(escritorio_a, usuario_gestor_a, nota)

    with pytest.raises(servico.EscrituracaoErro, match="cancelada"):
        servico.efetivar_escrituracao(_vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a)

    assert EscrituracaoFiscal.objects.count() == 0
    (linha,) = servico.notas_a_escriturar(empresa_a, 2024, 1)
    assert linha.situacao == servico.SITUACAO_CANCELADA


def test_cancelamento_depois_da_efetivacao_vira_pendencia_sem_estorno_automatico(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a
    )

    _cancelar(escritorio_a, usuario_gestor_a, nota)

    (linha,) = servico.notas_a_escriturar(empresa_a, 2024, 1)
    assert linha.situacao == servico.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA
    # Sem estorno automático: a escrituração continua efetivada.
    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).estado == (
        EstadoEscrituracao.EFETIVADA
    )
    conferencia = servico.conferencia(empresa_a, 2024, 1)
    assert [n.situacao for n in conferencia.bloqueios] == [
        servico.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA
    ]


def test_estorno_faz_a_pendencia_sumir(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a
    )
    _cancelar(escritorio_a, usuario_gestor_a, nota)

    servico.estornar_escrituracao(escrituracao, "nota cancelada pela prefeitura", usuario_gestor_a)

    (linha,) = servico.notas_a_escriturar(empresa_a, 2024, 1)
    assert linha.situacao == servico.SITUACAO_CANCELADA
    assert servico.conferencia(empresa_a, 2024, 1).bloqueios == []


# ---------------------------------------------------------------------------
# Critério 6 (domínio, sequencial) — idempotência da efetivação
# ---------------------------------------------------------------------------


def test_efetivar_de_novo_com_a_mesma_natureza_e_idempotente(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    primeira = servico.efetivar_escrituracao(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)

    segunda = servico.efetivar_escrituracao(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)

    assert segunda.pk == primeira.pk
    assert segunda.criada_agora is False
    assert EscrituracaoFiscal.objects.count() == 1
    # Repetir o clique não é fato novo: nenhuma trilha a mais.
    assert len(_trilha("escrituracao_fiscal.efetivada")) == 1


def test_efetivar_com_outra_natureza_com_nota_ja_efetivada_e_recusado(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    servico.efetivar_escrituracao(vinculo, NATUREZA_DEVIDO, usuario_gestor_a)

    with pytest.raises(servico.EscrituracaoErro, match="Estorne"):
        servico.efetivar_escrituracao(vinculo, NATUREZA_RETIDO, usuario_gestor_a)

    assert EscrituracaoFiscal.objects.count() == 1
    assert EscrituracaoFiscal.objects.get().natureza == NATUREZA_DEVIDO


# ---------------------------------------------------------------------------
# Critério 7 — nota tomada não entra nesta escrituração
# ---------------------------------------------------------------------------


def test_nota_tomada_nao_aparece_e_nao_e_escriturada(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)  # tomador = empresa_a2
    vinculo_tomador = _vinculo(nota, empresa_a2, papel=PapelDocumento.TOMADOR)

    assert servico.notas_a_escriturar(empresa_a2, 2024, 1) == []
    with pytest.raises(servico.EntradaInvalidaEscrituracao, match="prestadora"):
        servico.efetivar_escrituracao(vinculo_tomador, NATUREZA_DEVIDO, usuario_gestor_a)
    with pytest.raises(servico.EntradaInvalidaEscrituracao, match="prestadora"):
        servico.salvar_rascunho(vinculo_tomador, NATUREZA_DEVIDO, usuario_gestor_a)
    assert EscrituracaoFiscal.objects.count() == 0


# ---------------------------------------------------------------------------
# Critério 8 — conferência: recebidas = escrituradas + pendentes (HI-59)
# ---------------------------------------------------------------------------


def test_conferencia_fecha_recebidas_com_escrituradas_mais_pendentes(
    escritorio_a, empresa_a, usuario_gestor_a
):
    efetivada = _nota(escritorio_a, usuario_gestor_a, sufixo=1)
    rascunho = _nota(escritorio_a, usuario_gestor_a, sufixo=2)
    a_escriturar = _nota(escritorio_a, usuario_gestor_a, sufixo=3)
    cancelada = _nota(escritorio_a, usuario_gestor_a, sufixo=4)
    _cancelar(escritorio_a, usuario_gestor_a, cancelada)

    servico.efetivar_escrituracao(_vinculo(efetivada, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a)
    servico.salvar_rascunho(_vinculo(rascunho, empresa_a), NATUREZA_DEVIDO, usuario_gestor_a)

    resultado = servico.conferencia(empresa_a, 2024, 1)

    assert resultado.recebidas == 4
    assert resultado.escrituradas == 1
    assert resultado.pendentes == 3
    assert resultado.recebidas == resultado.escrituradas + resultado.pendentes
    # Bloqueio: nota sem escrituração efetivada que ainda pode ser escriturada.
    # A cancelada que nunca foi escriturada não bloqueia.
    ids_bloqueio = {n.vinculo.documento_id for n in resultado.bloqueios}
    assert ids_bloqueio == {rascunho.pk, a_escriturar.pk}
    assert cancelada.pk not in ids_bloqueio


def test_conferencia_avisa_competencia_diferente_da_emissao(
    escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(
        escritorio_a,
        usuario_gestor_a,
        sufixo=1,
        dh_emi="2024-01-15T10:00:00-03:00",
        d_compet="2024-02-01",
    )
    _nota(
        escritorio_a,
        usuario_gestor_a,
        sufixo=2,
        d_compet="2024-02-10",
        dh_emi="2024-02-10T09:00:00-03:00",
    )

    resultado = servico.conferencia(empresa_a, 2024, 2)

    assert [n.documento.identificador for n in resultado.avisos] == [identificador_nfse(1)]
    assert resultado.bloqueios and len(resultado.bloqueios) == 2  # ambas a escriturar


def test_conferencia_so_relata_e_nao_grava(escritorio_a, empresa_a, usuario_gestor_a):
    _nota(escritorio_a, usuario_gestor_a)

    servico.conferencia(empresa_a, 2024, 1)

    assert EscrituracaoFiscal.objects.count() == 0
    assert RegistroAuditoria.objects.filter(acao__startswith="escrituracao_fiscal.").count() == 0


# ---------------------------------------------------------------------------
# Isolamento no domínio (o da API está em test_dl072_api.py)
# ---------------------------------------------------------------------------


def test_lista_nao_mistura_empresas_nem_escritorios(
    escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a)

    assert len(servico.notas_a_escriturar(empresa_a, 2024, 1)) == 1
    assert servico.notas_a_escriturar(empresa_b, 2024, 1) == []
