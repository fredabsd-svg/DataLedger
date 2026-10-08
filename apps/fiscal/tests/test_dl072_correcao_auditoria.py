"""DL-072 — correção única da auditoria (rodada 1, 08/10/2026), camada de domínio.

Cobre os achados do domínio (docs/auditorias/2026-10-08-dl-072-dl-073-rodada-1.md):
- A2: a data de emissão é o dia escrito no documento (HI-72), e uma nota cujo XML
  não informa a data não é escriturada com data inventada;
- A5: mensagens de natureza vazia e fora do catálogo;
- A7: a natureza GRAVADA que contradiz o XML aparece na conferência, sem bloquear;
- A8: totais em R$ e conciliação entre a gravada e o documento, com valores
  escritos à mão;
- A10: a tela de uma nota usa o mesmo cálculo da lista, sem o mês inteiro.

Reconferência (docs/auditorias/2026-10-08-dl-072-dl-073-reconferencia.md):
- R1: aceitar a sugestão nunca gera divergência;
- R4: o estorno continua possível depois de o documento mudar;
- R5: os totais da conferência somam centavos sem float.

Dados 100% sintéticos (xml_sinteticos.py), recebidos pelo pipeline real.
"""

from decimal import Decimal

import pytest

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
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse

pytestmark = pytest.mark.django_db

DEVIDO = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
RETIDO = NaturezaOperacao.PRESTADO_ISS_RETIDO
EXPORTACAO = NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO
IMUNE = NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO
FORA_DA_LISTA = NaturezaOperacao.PRESTADO_FORA_LISTA_LC116
OUTRO_MUNICIPIO = NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO


def _nota(escritorio, usuario, sufixo=1, **kwargs):
    identificador = identificador_nfse(sufixo)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(identificador=identificador, numero=str(sufixo), **kwargs),
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    return DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)


def _vinculo(documento, empresa, papel=PapelDocumento.PRESTADOR):
    return VinculoDocumentoEmpresa.objects.get(documento=documento, empresa=empresa, papel=papel)


# ---------------------------------------------------------------------------
# A2 — sem o dia escrito no XML, a efetivação recusa; nada é gravado inventado
# ---------------------------------------------------------------------------


def test_efetivar_recusa_quando_o_xml_guardado_nao_informa_a_data(
    escritorio_a, empresa_a, usuario_gestor_a
):
    documento = _nota(escritorio_a, usuario_gestor_a)
    # XML sem o caminho infNFSe/DPS/infDPS/dhEmi: a leitura não tem data.
    DocumentoFiscal.objects.filter(pk=documento.pk).update(xml_original=b"<NFSe>sem dhEmi</NFSe>")

    with pytest.raises(servico.EscrituracaoErro, match="não informa a data de emissão"):
        servico.efetivar_escrituracao(_vinculo(documento, empresa_a), DEVIDO, usuario_gestor_a)

    assert EscrituracaoFiscal.objects.count() == 0


# ---------------------------------------------------------------------------
# A5 — mensagens de natureza: vazia e fora do catálogo
# ---------------------------------------------------------------------------


def test_natureza_vazia_tem_mensagem_propria(escritorio_a, empresa_a, usuario_gestor_a):
    documento = _nota(escritorio_a, usuario_gestor_a)

    with pytest.raises(servico.EntradaInvalidaEscrituracao) as info:
        servico.efetivar_escrituracao(_vinculo(documento, empresa_a), "", usuario_gestor_a)

    assert info.value.mensagem == "Escolha a natureza da operação."
    assert EscrituracaoFiscal.objects.count() == 0


def test_natureza_fora_do_catalogo_nomeia_o_catalogo_e_nao_ecoa_o_valor(
    escritorio_a, empresa_a, usuario_gestor_a
):
    documento = _nota(escritorio_a, usuario_gestor_a)

    with pytest.raises(servico.EntradaInvalidaEscrituracao) as info:
        servico.efetivar_escrituracao(
            _vinculo(documento, empresa_a), "aliquota-5-por-cento", usuario_gestor_a
        )

    assert "não é uma das naturezas do catálogo fiscal" in info.value.mensagem
    # O valor vem do cliente: não volta na mensagem.
    assert "aliquota-5-por-cento" not in info.value.mensagem
    assert EscrituracaoFiscal.objects.count() == 0


# ---------------------------------------------------------------------------
# A7 — natureza GRAVADA contra o XML: avisa na conferência, sem bloquear
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("xml_kwargs", "natureza", "trecho_do_aviso"),
    [
        # Retenção no XML (tpRetISSQN 2 ou 3) contra as naturezas que afirmam "sem retenção".
        ({"tp_ret_issqn": "2"}, DEVIDO, "retenção do ISS"),
        ({"tp_ret_issqn": "2"}, OUTRO_MUNICIPIO, "retenção do ISS"),
        ({"tp_ret_issqn": "3"}, IMUNE, "retenção do ISS"),
        ({"tp_ret_issqn": "3"}, FORA_DA_LISTA, "retenção do ISS"),
        # tribISSQN 3 (exportação no leiaute 1.01) contra uma natureza que não é exportação.
        ({"trib_issqn": "3"}, DEVIDO, "tribISSQN de exportação"),
        # Exportação gravada sem tribISSQN de exportação no XML.
        ({}, EXPORTACAO, "não traz tribISSQN de exportação"),
        ({"trib_issqn": "1"}, EXPORTACAO, "não traz tribISSQN de exportação"),
    ],
)
def test_conferencia_avisa_natureza_gravada_que_contradiz_o_xml(
    escritorio_a, empresa_a, usuario_gestor_a, xml_kwargs, natureza, trecho_do_aviso
):
    documento = _nota(escritorio_a, usuario_gestor_a, **xml_kwargs)
    servico.efetivar_escrituracao(_vinculo(documento, empresa_a), natureza, usuario_gestor_a)

    (divergente,) = servico.conferencia(empresa_a, 2024, 1).divergencias

    assert any(trecho_do_aviso in motivo for motivo in divergente.divergencias_de_natureza)
    # Só relata: a escrituração continua efetivada com a natureza que o contador escolheu.
    assert EscrituracaoFiscal.objects.get().natureza == natureza


@pytest.mark.parametrize(
    ("xml_kwargs", "natureza"),
    [
        ({"tp_ret_issqn": "2"}, RETIDO),
        ({"trib_issqn": "3"}, EXPORTACAO),
    ],
)
def test_natureza_coerente_com_o_xml_nao_gera_aviso(
    escritorio_a, empresa_a, usuario_gestor_a, xml_kwargs, natureza
):
    documento = _nota(escritorio_a, usuario_gestor_a, **xml_kwargs)
    servico.efetivar_escrituracao(_vinculo(documento, empresa_a), natureza, usuario_gestor_a)

    assert servico.conferencia(empresa_a, 2024, 1).divergencias == []


def test_rascunho_com_natureza_que_contradiz_o_xml_tambem_avisa(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # "Gravada" vale para rascunho e efetivada: o aviso aparece antes de efetivar.
    documento = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="2")
    servico.salvar_rascunho(_vinculo(documento, empresa_a), DEVIDO, usuario_gestor_a)

    (divergente,) = servico.conferencia(empresa_a, 2024, 1).divergencias

    assert divergente.situacao == servico.SITUACAO_RASCUNHO
    assert divergente.divergencias_de_natureza


# ---------------------------------------------------------------------------
# Reconferência R1 — aceitar a sugestão nunca gera divergência
# ---------------------------------------------------------------------------

# Código de não incidência por versão (XSD, ver escrituracao.py). Só serve para
# escrever a expectativa do teste, de forma independente da implementação.
_NAO_INCIDENCIA_POR_VERSAO = {"1.00": "3", "1.01": "4"}


@pytest.mark.parametrize("tp_ret_issqn", ["1", "2", "3"])
@pytest.mark.parametrize("trib_issqn", ["1", "2", "3", "4", None])
@pytest.mark.parametrize("versao", ["1.00", "1.01"])
def test_aceitar_a_sugestao_nunca_gera_divergencia(
    escritorio_a, empresa_a, usuario_gestor_a, versao, trib_issqn, tp_ret_issqn
):
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        versao=versao,
        trib_issqn=trib_issqn,
        tp_ret_issqn=tp_ret_issqn,
    )
    vinculo = _vinculo(documento, empresa_a)
    sugerida = servico.nota_do_vinculo(empresa_a, vinculo).natureza_sugerida

    # A única combinação sem sugestão é a não incidência sem retenção (HI-67). A
    # expectativa é conferida, e o caso não é pulado.
    sem_sugestao = tp_ret_issqn == "1" and trib_issqn == _NAO_INCIDENCIA_POR_VERSAO[versao]
    assert (sugerida is None) == sem_sugestao
    if sugerida is None:
        return

    servico.efetivar_escrituracao(vinculo, sugerida, usuario_gestor_a)

    assert servico.nota_do_vinculo(empresa_a, vinculo).divergencias_de_natureza == ()
    assert servico.conferencia(empresa_a, 2024, 1).divergencias == []


# ---------------------------------------------------------------------------
# A8 — totais em R$ e conciliação com valores escritos à mão
# ---------------------------------------------------------------------------


def test_conferencia_soma_em_reais_e_concilia_com_os_documentos(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Valores escritos à mão: 1000,00 escriturada; 250,50 a escriturar; 0,01 rascunho.
    efetivada = _nota(escritorio_a, usuario_gestor_a, sufixo=1, v_serv="1000.00", v_liq="950.00")
    servico.efetivar_escrituracao(_vinculo(efetivada, empresa_a), DEVIDO, usuario_gestor_a)
    _nota(escritorio_a, usuario_gestor_a, sufixo=2, v_serv="250.50", v_liq="240.00")
    rascunho = _nota(escritorio_a, usuario_gestor_a, sufixo=3, v_serv="0.01", v_liq="0.01")
    servico.salvar_rascunho(_vinculo(rascunho, empresa_a), DEVIDO, usuario_gestor_a)

    conferencia = servico.conferencia(empresa_a, 2024, 1)

    assert conferencia.total_recebidas == Decimal("1250.51")
    assert conferencia.total_escrituradas == Decimal("1000.00")
    assert conferencia.total_pendentes == Decimal("250.51")
    fecha = conferencia.total_escrituradas + conferencia.total_pendentes
    assert conferencia.total_recebidas == fecha
    assert conferencia.soma_gravada_escrituradas == Decimal("1000.00")
    assert conferencia.soma_documentos_escrituradas == Decimal("1000.00")
    assert conferencia.diferenca_escrituradas == Decimal("0.00")


def test_conciliacao_aponta_documento_alterado_depois_da_escrituracao(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # O documento é o que a escrituração copiou. Se ele mudar depois, a conciliação
    # mostra a diferença, em vez de a escrituração parecer conferida.
    documento = _nota(escritorio_a, usuario_gestor_a, v_serv="1000.00", v_liq="950.00")
    servico.efetivar_escrituracao(_vinculo(documento, empresa_a), DEVIDO, usuario_gestor_a)
    DocumentoFiscal.objects.filter(pk=documento.pk).update(v_serv=Decimal("1000.01"))

    conferencia = servico.conferencia(empresa_a, 2024, 1)

    assert conferencia.soma_gravada_escrituradas == Decimal("1000.00")
    assert conferencia.soma_documentos_escrituradas == Decimal("1000.01")
    assert conferencia.diferenca_escrituradas == Decimal("-0.01")


def test_totais_da_conferencia_somam_centavos_sem_float(escritorio_a, empresa_a, usuario_gestor_a):
    # Reconferência R5: em float, 0,10 + 0,20 dá 0,30000000000000004, e um valor de 15
    # dígitos inteiros (o máximo de vServ) perde os centavos. O total tem que sair exato.
    _nota(escritorio_a, usuario_gestor_a, sufixo=1, v_serv="0.10", v_liq="0.10")
    _nota(escritorio_a, usuario_gestor_a, sufixo=2, v_serv="0.20", v_liq="0.20")
    _nota(escritorio_a, usuario_gestor_a, sufixo=3, v_serv="999999999999999.99", v_liq="1.00")

    conferencia = servico.conferencia(empresa_a, 2024, 1)

    assert conferencia.total_recebidas == Decimal("1000000000000000.29")
    assert str(conferencia.total_pendentes) == "1000000000000000.29"


# ---------------------------------------------------------------------------
# A10 — a tela de uma nota usa a mesma regra da lista, sem o mês inteiro
# ---------------------------------------------------------------------------


def test_nota_do_vinculo_e_a_mesma_linha_que_a_lista_daria(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    escriturada = _nota(escritorio_a, usuario_gestor_a, sufixo=1)
    servico.efetivar_escrituracao(_vinculo(escriturada, empresa_a), DEVIDO, usuario_gestor_a)
    rascunho = _nota(escritorio_a, usuario_gestor_a, sufixo=2, tp_ret_issqn="2")
    servico.salvar_rascunho(_vinculo(rascunho, empresa_a), RETIDO, usuario_gestor_a)
    a_escriturar = _nota(escritorio_a, usuario_gestor_a, sufixo=3, trib_issqn="4")

    for documento in (escriturada, rascunho, a_escriturar):
        vinculo = _vinculo(documento, empresa_a)
        da_lista = next(
            n for n in servico.notas_a_escriturar(empresa_a, 2024, 1) if n.vinculo.pk == vinculo.pk
        )
        direta = servico.nota_do_vinculo(empresa_a, vinculo)

        assert direta.situacao == da_lista.situacao
        assert direta.natureza_sugerida == da_lista.natureza_sugerida
        assert direta.data_emissao == da_lista.data_emissao
        assert direta.escrituracao == da_lista.escrituracao
        assert direta.divergencias_de_natureza == da_lista.divergencias_de_natureza


def test_nota_do_vinculo_de_tomada_e_none_e_de_outra_empresa_levanta(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    documento = _nota(escritorio_a, usuario_gestor_a)
    tomador = _vinculo(documento, empresa_a2, papel=PapelDocumento.TOMADOR)

    assert servico.nota_do_vinculo(empresa_a2, tomador) is None
    with pytest.raises(ValueError):
        servico.nota_do_vinculo(empresa_a2, _vinculo(documento, empresa_a))


# ---------------------------------------------------------------------------
# Reconferência R4 — o estorno não depende do documento estar igual à efetivação
# ---------------------------------------------------------------------------


def test_estorno_funciona_mesmo_depois_de_o_documento_mudar(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # A checagem de valores vale para a EFETIVAÇÃO (e para o INSERT de estornada), nunca
    # para o UPDATE de estorno. Se o documento muda depois, o estorno continua possível:
    # é quando ele é mais necessário.
    documento = _nota(escritorio_a, usuario_gestor_a, v_serv="10.00", v_liq="10.00")
    efetivada = servico.efetivar_escrituracao(
        _vinculo(documento, empresa_a), DEVIDO, usuario_gestor_a
    )
    DocumentoFiscal.objects.filter(pk=documento.pk).update(v_serv=Decimal("11.00"))

    estornada = servico.estornar_escrituracao(efetivada, "documento mudou", usuario_gestor_a)

    assert estornada.estado == EstadoEscrituracao.ESTORNADA
