"""DL-072 — catálogo de seis naturezas, mercado e sugestão por `tribISSQN` (HI-67).

O que cobre aqui:
- o catálogo tem as seis naturezas, e "sem incidência" saiu;
- `mercado_da_natureza`: só a exportação é externa; valor fora do catálogo recusa;
- a sugestão: retenção vence; `tribISSQN` 1, 2, 3 e 4 mapeados pela TABELA DA
  VERSÃO do leiaute (1.01 e 1.00 têm códigos diferentes, conferidos nos XSD);
- XML sem `tribISSQN`, em caminho errado, ilegível ou de versão sem tabela cai na
  regra seguinte, sem exceção;
- não-incidência não gera sugestão (None) e nada é gravado sem o contador;
- efetivar sem natureza é recusado, e a exportação efetivada grava o mercado externo.

Dados 100% sintéticos (xml_sinteticos.xml_nfse), pelo pipeline real de recepção.
"""

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao as servico
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
    mercado_da_natureza,
)
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse

pytestmark = pytest.mark.django_db

DEVIDO = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
RETIDO = NaturezaOperacao.PRESTADO_ISS_RETIDO
OUTRO_MUNICIPIO = NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO
EXPORTACAO = NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO
IMUNE = NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO
FORA_DA_LISTA = NaturezaOperacao.PRESTADO_FORA_LISTA_LC116


def _nota(escritorio, usuario, sufixo=1, **kwargs):
    identificador = identificador_nfse(sufixo)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(identificador=identificador, numero=str(sufixo), **kwargs),
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    return DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)


def _vinculo(documento, empresa):
    return VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )


# ---------------------------------------------------------------------------
# Catálogo: seis naturezas, e "sem incidência" não existe mais
# ---------------------------------------------------------------------------


def test_catalogo_tem_exatamente_as_seis_naturezas_da_hi_67():
    assert set(NaturezaOperacao.values) == {
        "prestado_iss_devido_prestador",
        "prestado_iss_retido",
        "prestado_iss_outro_municipio",
        "prestado_exportacao_servico",
        "prestado_iss_imune_isento_reduzido",
        "prestado_fora_lista_lc116",
    }
    assert len(NaturezaOperacao.choices) == 6
    assert all(rotulo.strip() for _valor, rotulo in NaturezaOperacao.choices)


def test_nao_existe_mais_o_valor_unico_sem_incidencia():
    assert not hasattr(NaturezaOperacao, "PRESTADO_SEM_INCIDENCIA_ISS")
    assert "prestado_sem_incidencia_iss" not in NaturezaOperacao.values


# ---------------------------------------------------------------------------
# mercado_da_natureza: só a exportação é externa
# ---------------------------------------------------------------------------


def test_exportacao_de_servico_e_mercado_externo():
    assert mercado_da_natureza(NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO) == "externo"


@pytest.mark.parametrize(
    "natureza",
    [
        NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR,
        NaturezaOperacao.PRESTADO_ISS_RETIDO,
        NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO,
        NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO,
        NaturezaOperacao.PRESTADO_FORA_LISTA_LC116,
    ],
)
def test_as_outras_cinco_sao_mercado_interno(natureza):
    assert mercado_da_natureza(natureza) == "interno"


def test_mercado_aceita_o_valor_textual_do_catalogo():
    # O banco guarda o valor textual; a função tem de dar a mesma resposta para ele.
    assert mercado_da_natureza("prestado_exportacao_servico") == "externo"
    assert mercado_da_natureza("prestado_fora_lista_lc116") == "interno"


def test_natureza_fora_do_catalogo_nao_vira_interno_em_silencio():
    # Um valor desconhecido mudaria a base do Simples: recusa, não presume.
    with pytest.raises(ValueError, match="fora do catálogo"):
        mercado_da_natureza("sem_incidencia_antiga")


# ---------------------------------------------------------------------------
# Sugestão por tribISSQN, versão 1.01 (tribISSQN: 1 tributável, 2 imunidade,
# 3 exportação, 4 não incidência — tiposSimples_v1.01.xsd:1080-1083)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tp_ret_issqn", "trib_issqn", "esperada"),
    [
        # Sem retenção: cada tribISSQN leva à sua natureza.
        ("1", "1", DEVIDO),
        ("1", "2", IMUNE),
        ("1", "3", EXPORTACAO),
        ("1", "4", None),
        # Retenção VENCE qualquer tribISSQN (HI-67: retido não cai em exportação).
        ("2", "1", RETIDO),
        ("2", "2", RETIDO),
        ("2", "3", RETIDO),
        ("2", "4", RETIDO),
        ("3", "1", RETIDO),
        ("3", "2", RETIDO),
        ("3", "3", RETIDO),
        ("3", "4", RETIDO),
    ],
)
def test_sugestao_por_tribissqn_no_leiaute_1_01_com_retencao_vencendo(
    escritorio_a, empresa_a, usuario_gestor_a, tp_ret_issqn, trib_issqn, esperada
):
    nota = _nota(
        escritorio_a,
        usuario_gestor_a,
        versao="1.01",
        tp_ret_issqn=tp_ret_issqn,
        trib_issqn=trib_issqn,
    )

    assert servico.sugerir_natureza(nota) == esperada


# ---------------------------------------------------------------------------
# Sugestão por tribISSQN, versão 1.00 — códigos DIFERENTES do 1.01
# (tiposSimples_v1.00.xsd:1086-1089: 2 exportação, 3 não incidência, 4 imunidade)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trib_issqn", "esperada"),
    [
        ("1", DEVIDO),
        ("2", EXPORTACAO),
        ("3", None),
        ("4", IMUNE),
    ],
)
def test_sugestao_por_tribissqn_no_leiaute_1_00_usa_a_tabela_da_propria_versao(
    escritorio_a, empresa_a, usuario_gestor_a, trib_issqn, esperada
):
    # Mesmo código "2" significa imunidade no 1.01 e exportação no 1.00: a
    # sugestão lê a tabela da versão, nunca uma só.
    nota = _nota(escritorio_a, usuario_gestor_a, versao="1.00", trib_issqn=trib_issqn)

    assert servico.sugerir_natureza(nota) == esperada


def test_mesmo_codigo_2_muda_de_significado_conforme_a_versao(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota_101 = _nota(escritorio_a, usuario_gestor_a, sufixo=101, versao="1.01", trib_issqn="2")
    nota_100 = _nota(escritorio_a, usuario_gestor_a, sufixo=100, versao="1.00", trib_issqn="2")

    assert servico.sugerir_natureza(nota_101) == IMUNE
    assert servico.sugerir_natureza(nota_100) == EXPORTACAO


# ---------------------------------------------------------------------------
# Quando o XML não permite a leitura, a sugestão cai na regra seguinte
# ---------------------------------------------------------------------------


def test_xml_sem_tribissqn_sugere_devido_e_nao_presume(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="1")

    assert servico.sugerir_natureza(nota) == DEVIDO


def test_xml_sem_tribissqn_com_retencao_sugere_retido(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="2")

    assert servico.sugerir_natureza(nota) == RETIDO


def test_tribissqn_fora_do_caminho_nao_conta(escritorio_a, empresa_a, usuario_gestor_a):
    # `tribISSQN` solto em `trib` (fora de `tribMun`) não é o campo do leiaute:
    # não pode decidir a natureza. O caminho é valores/trib/tribMun/tribISSQN.
    xml = xml_nfse(minificado=True, tp_ret_issqn="1").replace(
        b"<trib><tribMun>", b"<trib><tribISSQN>3</tribISSQN><tribMun>"
    )
    assert b"<trib><tribISSQN>3</tribISSQN>" in xml
    nota = _nota(escritorio_a, usuario_gestor_a, sufixo=7)
    DocumentoFiscal.objects.filter(pk=nota.pk).update(xml_original=xml)
    nota.refresh_from_db()

    assert servico.sugerir_natureza(nota) == DEVIDO


def test_xml_ilegivel_cai_em_devido_sem_excecao(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="3")
    assert servico.sugerir_natureza(nota) == EXPORTACAO

    DocumentoFiscal.objects.filter(pk=nota.pk).update(xml_original=b"<nao-e-xml")
    nota.refresh_from_db()

    assert servico.sugerir_natureza(nota) == DEVIDO


def test_versao_sem_tabela_de_tribissqn_cai_em_devido(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="3")
    DocumentoFiscal.objects.filter(pk=nota.pk).update(versao="9.99")
    nota.refresh_from_db()

    assert servico.sugerir_natureza(nota) == DEVIDO


def test_dtd_com_entidade_nao_forja_a_sugestao_de_natureza(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Auditoria B1 (parte DL-072): `tribISSQN` é lido por `_raiz_segura`, sem DTD.
    # Com um parser comum, a entidade `&t;` expandiria para "3" (exportação no 1.01)
    # e a sugestão seria exportação. Com o parser seguro, o XML é recusado e a
    # sugestão cai em "devido", a regra padrão.
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="@@")
    forjado = xml_nfse(identificador=identificador_nfse(1), trib_issqn="@@").replace(b"@@", b"&t;")
    forjado = forjado.replace(
        b'<?xml version="1.0" encoding="UTF-8"?>\n',
        b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE NFSe [<!ENTITY t "3">]>',
    )
    # Guarda: se a declaração do XML sintético mudar, a substituição não casa e o
    # teste viraria vazio. Isso o reprova.
    assert b"<!DOCTYPE" in forjado and b"&t;" in forjado
    DocumentoFiscal.objects.filter(pk=nota.pk).update(xml_original=forjado)
    nota.refresh_from_db()

    assert servico.sugerir_natureza(nota) == DEVIDO


def test_sugestao_nunca_presume_outro_municipio_nem_fora_da_lista_em_nenhum_codigo(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Nenhum código das duas versões pode virar "outro município" nem "fora da
    # lista": o XML não diz isso. Não-incidência resulta em None (ver acima).
    sufixo = 200
    for versao in ("1.01", "1.00"):
        for codigo in ("1", "2", "3", "4"):
            sufixo += 1
            nota = _nota(
                escritorio_a,
                usuario_gestor_a,
                sufixo=sufixo,
                versao=versao,
                trib_issqn=codigo,
            )
            assert servico.sugerir_natureza(nota) not in {OUTRO_MUNICIPIO, FORA_DA_LISTA}


# ---------------------------------------------------------------------------
# Não-incidência: sem sugestão, nada gravado, efetivar exige escolha
# ---------------------------------------------------------------------------


def test_nao_incidencia_lista_com_sugestao_nula_e_nada_gravado(
    escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a, trib_issqn="4")

    (linha,) = servico.notas_a_escriturar(empresa_a, 2024, 1)

    assert linha.natureza_sugerida is None
    assert EscrituracaoFiscal.objects.count() == 0


def test_efetivar_sem_natureza_e_recusado_e_nada_e_gravado(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="4")

    # Auditoria A5: o vazio tem mensagem própria ("Escolha a natureza"), e não a de
    # natureza desconhecida. A recusa e o "nada gravado" continuam os mesmos.
    with pytest.raises(servico.EntradaInvalidaEscrituracao, match="Escolha a natureza da operação"):
        servico.efetivar_escrituracao(_vinculo(nota, empresa_a), "", usuario_gestor_a)

    assert EscrituracaoFiscal.objects.count() == 0


def test_contador_escolhe_fora_da_lista_e_a_escolha_e_gravada_com_sugestao_nula_na_trilha(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="4", v_serv="80.00", v_liq="80.00")

    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), FORA_DA_LISTA, usuario_gestor_a
    )

    gravada = EscrituracaoFiscal.objects.get(pk=escrituracao.pk)
    assert gravada.natureza == FORA_DA_LISTA
    assert mercado_da_natureza(gravada.natureza) == "interno"
    # A trilha registra que não havia sugestão (None) e qual natureza foi escolhida.
    (registro,) = RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.efetivada")
    assert registro.detalhes["natureza_sugerida"] is None
    assert registro.detalhes["depois"]["natureza"] == FORA_DA_LISTA


def test_efetivar_exportacao_grava_mercado_externo(escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="3", v_serv="1000.00", v_liq="1000.00")

    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), EXPORTACAO, usuario_gestor_a
    )

    gravada = EscrituracaoFiscal.objects.get(pk=escrituracao.pk)
    assert gravada.natureza == EXPORTACAO
    assert mercado_da_natureza(gravada.natureza) == "externo"
