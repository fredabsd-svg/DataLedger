"""DL-080 (frente A), serviço de recepção da NF-e: vínculos, deduplicação, eventos e limites.

Passa pelo pipeline real (`services.receber_envio`) com XML sintético (`xml_nfe_dl080`).
Os critérios 5, 6, 7 e 9 do plano e o limite de 4 MB (HI-112) estão aqui.
A não contaminação da NFS-e fica em `test_dl080_nao_contaminacao.py`.
"""

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    DocumentoNFe,
    EventoFiscal,
    EventoNFe,
    LoteDeRecepcao,
    PapelNFe,
    TipoResultadoArquivo,
    VinculoNFeEmpresa,
)
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DE_FORA,
    CNPJ_DESTINATARIO_A,
    CNPJ_EMITENTE_A,
    CNPJ_SEM_CADASTRO,
    CPF_CLIENTE,
    CPF_SEM_CADASTRO,
    chave_nfe,
    cnpj_com_dv,
    proc_evento_xml,
    xml_nfe,
)
from apps.fiscal.tests.xml_sinteticos import xml_nfse, zip_de
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CNPJ_FILIAL = cnpj_com_dv("300400500600")  # filial da empresa emitente (mesma empresa, outro CNPJ)
MI = 1024 * 1024
TETO_NFE = services.LIMITE_TAMANHO_XML_NFE_BYTES  # 4 MB (HI-112)
TETO_NFSE = services.LIMITE_TAMANHO_XML_BYTES  # 1 MB (HI-22)
CHAVE_PADRAO = chave_nfe(emitente=CNPJ_EMITENTE_A)


# --- helpers ------------------------------------------------------------------------


def _enviar(escritorio, usuario, conteudo, nome="nota.xml"):
    return services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo=nome
    )


def _unico(lote):
    return lote.resultados.get()


def _nfe_com_tamanho(alvo: int) -> bytes:
    """NF-e de exatamente `alvo` bytes; o excedente vai num comentário XML (sem efeito)."""
    base = xml_nfe()
    conteudo = xml_nfe(padding_comentario=alvo - len(base) - 9)
    assert len(conteudo) == alvo
    return conteudo


def _nfse_com_tamanho(alvo: int) -> bytes:
    base = xml_nfse(incluir_tomador=False)
    marcador_abre, marcador_fecha = b"<!--", b"-->\n"
    n = alvo - len(base) - len(marcador_abre) - len(marcador_fecha)
    conteudo = base.replace(b"?>\n", b"?>\n" + marcador_abre + b"p" * n + marcador_fecha, 1)
    assert len(conteudo) == alvo
    return conteudo


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Sintetica Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def destinatario(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Destinataria Sintetica Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )


# --- vínculos e papéis (critério 5) ---------------------------------------------------


def test_empresa_como_emitente_recebe_vinculo_de_emitente(escritorio_a, usuario_gestor_a, emitente):
    lote = _enviar(escritorio_a, usuario_gestor_a, xml_nfe(destinatario=None, modelo="65"))
    resultado = _unico(lote)
    assert resultado.resultado == TipoResultadoArquivo.RECEBIDO
    vinculo = VinculoNFeEmpresa.objects.get()
    assert (vinculo.empresa, vinculo.papel) == (emitente, PapelNFe.EMITENTE)
    assert resultado.documento_nfe == vinculo.documento
    assert resultado.documento is None


def test_empresa_como_destinatario_recebe_vinculo_de_destinatario(
    escritorio_a, usuario_gestor_a, destinatario
):
    lote = _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO
    vinculo = VinculoNFeEmpresa.objects.get()
    assert (vinculo.empresa, vinculo.papel) == (destinatario, PapelNFe.DESTINATARIO)


def test_nota_entre_duas_empresas_do_escritorio_tem_dois_papeis(
    escritorio_a, usuario_gestor_a, emitente, destinatario
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    papeis = dict(VinculoNFeEmpresa.objects.values_list("empresa_id", "papel"))
    assert papeis == {emitente.pk: PapelNFe.EMITENTE, destinatario.pk: PapelNFe.DESTINATARIO}
    documento = DocumentoNFe.objects.get()
    assert documento.transferencia_entre_estabelecimentos is False


def test_transferencia_entre_matriz_e_filial_vira_um_vinculo_como_emitente(
    escritorio_a, usuario_gestor_a, emitente
):
    # HI-111: emitente é a matriz e destinatário é a filial da MESMA empresa.
    Estabelecimento.objects.create(
        empresa=emitente,
        escritorio=escritorio_a,
        tipo=TipoEstabelecimento.FILIAL,
        nome="Filial sintetica",
        cnpj=CNPJ_FILIAL,
    )
    lote = _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(destinatario=("CNPJ", CNPJ_FILIAL)),
    )
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO
    vinculo = VinculoNFeEmpresa.objects.get()
    assert (vinculo.empresa, vinculo.papel) == (emitente, PapelNFe.EMITENTE)
    assert vinculo.documento.transferencia_entre_estabelecimentos is True


def test_transferencia_com_filial_como_emitente_tambem_vira_um_vinculo(
    escritorio_a, usuario_gestor_a, emitente
):
    Estabelecimento.objects.create(
        empresa=emitente,
        escritorio=escritorio_a,
        tipo=TipoEstabelecimento.FILIAL,
        nome="Filial sintetica",
        cnpj=CNPJ_FILIAL,
    )
    chave = chave_nfe(emitente=CNPJ_FILIAL)
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(
            chave=chave, emitente=("CNPJ", CNPJ_FILIAL), destinatario=("CNPJ", CNPJ_EMITENTE_A)
        ),
    )
    vinculo = VinculoNFeEmpresa.objects.get()
    assert (vinculo.empresa, vinculo.papel) == (emitente, PapelNFe.EMITENTE)
    assert vinculo.documento.transferencia_entre_estabelecimentos is True


def test_nfce_sem_destinatario_com_empresa_emitente_recebe_vinculo(
    escritorio_a, usuario_gestor_a, emitente
):
    lote = _enviar(escritorio_a, usuario_gestor_a, xml_nfe(modelo="65", destinatario=None))
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO
    documento = DocumentoNFe.objects.get()
    assert documento.modelo == "65"
    assert documento.destinatario_tipo_documento == ""
    assert VinculoNFeEmpresa.objects.get().papel == PapelNFe.EMITENTE


@pytest.mark.parametrize(
    "xml_com_participante_que_nao_e_parte",
    [
        pytest.param({"autxml_cnpj": CNPJ_EMITENTE_A}, id="autXML-com-CNPJ-do-cliente"),
        pytest.param({"transporta_cnpj": CNPJ_EMITENTE_A}, id="transportador-com-CNPJ-do-cliente"),
        pytest.param(
            {"inf_adicional": f"Ref. {CNPJ_EMITENTE_A}"}, id="informacao-adicional-com-CNPJ"
        ),
    ],
)
def test_autxml_transportador_e_informacao_adicional_nao_ligam_empresa(
    escritorio_a, usuario_gestor_a, emitente, xml_com_participante_que_nao_e_parte
):
    # Emitente e destinatário são de fora; o cliente aparece só em um campo que não é parte.
    conteudo = xml_nfe(
        emitente=("CNPJ", CNPJ_DE_FORA),
        destinatario=("CNPJ", CNPJ_SEM_CADASTRO),
        **xml_com_participante_que_nao_e_parte,
    )
    lote = _enviar(escritorio_a, usuario_gestor_a, conteudo)
    resultado = _unico(lote)
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert resultado.motivo == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO
    assert not VinculoNFeEmpresa.objects.exists()
    assert not DocumentoNFe.objects.exists()


def test_nota_sem_parte_do_escritorio_e_recusada_com_a_mensagem_da_nfse(
    escritorio_a, usuario_gestor_a
):
    lote = _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(emitente=("CNPJ", CNPJ_DE_FORA), destinatario=("CNPJ", CNPJ_SEM_CADASTRO)),
    )
    resultado = _unico(lote)
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert resultado.motivo == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO


def test_chave_com_cnpj_de_cliente_nao_liga_a_empresa(escritorio_a, usuario_gestor_a, emitente):
    # A chave não liga empresa (pesquisa, seção 5). Aqui ela traz o CNPJ de um cliente, e o emitente
    # do XML é de fora. Desde a correção da rodada 1 (A8), a própria chave é conferida contra o
    # emitente fora das séries de NFA-e (890 a 899): a recusa vem dessa conferência, antes de
    # qualquer participante. O invariante continua o mesmo: a nota não entra e nada é vinculado.
    chave_com_cnpj_do_cliente = chave_nfe(emitente=CNPJ_EMITENTE_A)
    lote = _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(
            chave=chave_com_cnpj_do_cliente,
            emitente=("CNPJ", CNPJ_DE_FORA),
            destinatario=("CNPJ", CNPJ_SEM_CADASTRO),
        ),
    )
    assert _unico(lote).resultado == TipoResultadoArquivo.RECUSADO
    assert "diferente do emitente" in _unico(lote).motivo
    assert not VinculoNFeEmpresa.objects.exists()
    assert not DocumentoNFe.objects.exists()


def test_mensagem_de_recusa_e_identica_para_cnpj_de_outro_escritorio_e_para_cnpj_inexistente(
    escritorio_a, escritorio_b, usuario_gestor_a
):
    # Critério 27: a mensagem não revela se o CNPJ pertence a alguém em outro escritório.
    Empresa.objects.create(
        escritorio=escritorio_b, razao_social="De Outro Escritorio", cnpj=CNPJ_DE_FORA
    )
    motivos = []
    for cnpj in (CNPJ_DE_FORA, CNPJ_SEM_CADASTRO):
        lote = _enviar(
            escritorio_a,
            usuario_gestor_a,
            xml_nfe(emitente=("CNPJ", cnpj), destinatario=("CNPJ", CNPJ_SEM_CADASTRO)),
        )
        motivos.append(_unico(lote).motivo)
    assert motivos[0] == motivos[1] == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO


def test_participante_pessoa_fisica_sem_cadastro_recebe_mensagem_propria(
    escritorio_a, usuario_gestor_a
):
    lote = _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(emitente=("CNPJ", CNPJ_DE_FORA), destinatario=("CPF", CPF_SEM_CADASTRO)),
    )
    assert _unico(lote).motivo == services.MENSAGEM_PARTICIPANTE_PESSOA_FISICA_SEM_CADASTRO


def test_destinatario_pessoa_fisica_cadastrada_liga_a_empresa(escritorio_a, usuario_gestor_a):
    cliente = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Cliente Pessoa Fisica",
        tipo_inscricao="CPF",
        cpf=CPF_CLIENTE,
    )
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(emitente=("CNPJ", CNPJ_DE_FORA), destinatario=("CPF", CPF_CLIENTE)),
    )
    vinculo = VinculoNFeEmpresa.objects.get()
    assert (vinculo.empresa, vinculo.papel) == (cliente, PapelNFe.DESTINATARIO)


def test_mesmo_cnpj_em_dois_escritorios_fica_isolado(
    escritorio_a, escritorio_b, usuario_gestor_a, usuario_gestor_b, emitente
):
    # DL-041: o mesmo CNPJ pode existir em dois escritórios. Cada nota fica no seu.
    emitente_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Mesmo CNPJ em B", cnpj=CNPJ_EMITENTE_A
    )
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(destinatario=None))
    _enviar(escritorio_b, usuario_gestor_b, xml_nfe(destinatario=None))

    assert DocumentoNFe.objects.filter(escritorio=escritorio_a).count() == 1
    assert DocumentoNFe.objects.filter(escritorio=escritorio_b).count() == 1
    vinculos_b = VinculoNFeEmpresa.objects.filter(empresa=emitente_b)
    assert vinculos_b.count() == 1
    assert vinculos_b.get().documento.escritorio == escritorio_b
    assert (
        VinculoNFeEmpresa.objects.filter(
            empresa=emitente, documento__escritorio=escritorio_b
        ).count()
        == 0
    )


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    from django.contrib.auth import get_user_model

    usuario = get_user_model().objects.create_user(
        username="gestor-fiscal-b-dl080",
        email="gestor-fiscal-b-dl080@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    return usuario


def test_nota_nao_gera_documento_nem_vinculo_de_nfse(escritorio_a, usuario_gestor_a, emitente):
    # Só o emitente é cliente aqui; o destinatário não está cadastrado. Um vínculo só.
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    assert DocumentoFiscal.objects.count() == 0
    assert VinculoNFeEmpresa.objects.count() == 1
    assert DocumentoNFe.objects.count() == 1


# --- deduplicação (critério 7) -------------------------------------------------------


def test_reimportar_o_mesmo_arquivo_nao_duplica(escritorio_a, usuario_gestor_a, emitente):
    conteudo = xml_nfe()
    _enviar(escritorio_a, usuario_gestor_a, conteudo)
    lote = _enviar(escritorio_a, usuario_gestor_a, conteudo)
    resultado = _unico(lote)
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    # A9 (rodada 1): a NF-e é feminina, então "já recebida".
    assert "NF-e já recebida" in resultado.motivo
    assert DocumentoNFe.objects.count() == 1
    assert VinculoNFeEmpresa.objects.count() == 1


def test_mesmo_xml_dentro_de_outro_zip_nao_duplica(escritorio_a, usuario_gestor_a, emitente):
    conteudo = xml_nfe()
    _enviar(escritorio_a, usuario_gestor_a, conteudo)
    zipado = zip_de({"pasta/outra/nota-renomeada.xml": conteudo})
    lote = _enviar(escritorio_a, usuario_gestor_a, zipado, nome="lote.zip")
    assert _unico(lote).resultado == TipoResultadoArquivo.DUPLICADO
    assert DocumentoNFe.objects.count() == 1


def test_conteudo_diferente_com_a_mesma_chave_e_sinalizado_sem_sobrescrever(
    escritorio_a, usuario_gestor_a, emitente
):
    original = xml_nfe()
    _enviar(escritorio_a, usuario_gestor_a, original)
    documento = DocumentoNFe.objects.get()
    sha_original = documento.sha256_arquivo

    diferente = xml_nfe(padding_comentario=40)
    lote = _enviar(escritorio_a, usuario_gestor_a, diferente)
    resultado = _unico(lote)
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert "DIFERENTE" in resultado.motivo
    documento.refresh_from_db()
    assert documento.sha256_arquivo == sha_original
    assert bytes(documento.xml_original) == original
    assert DocumentoNFe.objects.count() == 1


def test_reimportacao_acrescenta_o_vinculo_que_faltava(escritorio_a, usuario_gestor_a, emitente):
    # Primeiro recebimento: só o emitente é cliente. Depois o destinatário é cadastrado.
    conteudo = xml_nfe()
    lote_1 = _enviar(escritorio_a, usuario_gestor_a, conteudo)
    assert VinculoNFeEmpresa.objects.count() == 1
    assert _unico(lote_1).resultado == TipoResultadoArquivo.RECEBIDO

    destinatario = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Destinataria Tardia", cnpj=CNPJ_DESTINATARIO_A
    )
    lote_2 = _enviar(escritorio_a, usuario_gestor_a, conteudo)
    resultado = _unico(lote_2)
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert "Vínculo novo criado" in resultado.motivo
    assert (
        VinculoNFeEmpresa.objects.filter(empresa=destinatario).get().papel == PapelNFe.DESTINATARIO
    )


# --- eventos e cancelamento (critério 6) --------------------------------------------


def _cancelamento(chave=CHAVE_PADRAO, c_stat="135", autor=("CNPJ", CNPJ_EMITENTE_A)):
    return proc_evento_xml(tp_evento="110111", chave=chave, c_stat=c_stat, autor=autor)


def test_cancelamento_depois_da_nota_torna_a_nota_cancelada(
    escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    documento = DocumentoNFe.objects.get()
    assert services.situacao_da_nfe(documento) == "valida"
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento())
    assert services.situacao_da_nfe(documento) == "cancelada"


def test_cancelamento_antes_da_nota_torna_a_nota_cancelada(
    escritorio_a, usuario_gestor_a, emitente
):
    # Ordem inversa: o evento chega primeiro, como órfão. A consulta por chave resolve.
    lote_evento = _enviar(escritorio_a, usuario_gestor_a, _cancelamento())
    assert _unico(lote_evento).resultado == TipoResultadoArquivo.RECEBIDO
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    documento = DocumentoNFe.objects.get()
    assert services.situacao_da_nfe(documento) == "cancelada"


def test_cancelamento_por_substituicao_110112_tambem_cancela(
    escritorio_a, usuario_gestor_a, emitente
):
    # NFC-e (65): a chave é a dela, não a da NF-e de 55.
    chave_nfce = chave_nfe(emitente=CNPJ_EMITENTE_A, modelo="65")
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(modelo="65", destinatario=None))
    evento = proc_evento_xml(tp_evento="110112", chave=chave_nfce, c_stat="135")
    _enviar(escritorio_a, usuario_gestor_a, evento)
    assert services.situacao_da_nfe(DocumentoNFe.objects.get()) == "cancelada"


@pytest.mark.parametrize("c_stat", [None, "128"], ids=["sem-retorno", "retorno-fora-dos-efetivos"])
def test_evento_sem_retorno_ou_com_retorno_nao_efetivo_nao_cancela(
    escritorio_a, usuario_gestor_a, emitente, c_stat
):
    # Sem retorno, ou com retorno fora de {135, 155} (HI-116: o 136 não cancela), o evento não
    # prova registro.
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat=c_stat))
    assert EventoNFe.objects.count() == 1, "o evento é guardado mesmo sem efeito"
    assert services.situacao_da_nfe(DocumentoNFe.objects.get()) == "valida"


# A7 (rodada 1, HI-116): 136 não cancela. Ver test_dl080_correcao_rodada1.py.
@pytest.mark.parametrize("c_stat", ["135", "155"])
def test_retorno_efetivo_cancela(escritorio_a, usuario_gestor_a, emitente, c_stat):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat=c_stat))
    assert services.situacao_da_nfe(DocumentoNFe.objects.get()) == "cancelada"


# LIMITAÇÃO DECLARADA (DL-080, decisão do arquiteto): o 110001 NÃO cancela a nota, e esta
# recepção também não reverte um cancelamento que um 110001 anule. Fica no backlog.
@pytest.mark.parametrize(
    "tp_evento",
    ["110110", "210200", "210210", "210220", "210240", "112110", "110001", "412120"],
    ids=[
        "carta-de-correcao",
        "confirmacao",
        "ciencia",
        "desconhecimento",
        "nao-realizada",
        "reforma-112110",
        "cancelamento-de-evento-110001",
        "reforma-412120-fisco",
    ],
)
def test_evento_que_nao_cancela_fica_guardado_sem_mudar_a_situacao(
    escritorio_a, usuario_gestor_a, emitente, tp_evento
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    evento = proc_evento_xml(tp_evento=tp_evento, chave=CHAVE_PADRAO, c_stat="135")
    lote = _enviar(escritorio_a, usuario_gestor_a, evento)
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO
    assert EventoNFe.objects.get().tp_evento == tp_evento
    assert services.situacao_da_nfe(DocumentoNFe.objects.get()) == "valida"


def test_evento_orfao_e_guardado_sem_empresa(escritorio_a, usuario_gestor_a):
    evento = proc_evento_xml(chave=CHAVE_PADRAO, autor=("CNPJ", CNPJ_SEM_CADASTRO), c_stat="135")
    lote = _enviar(escritorio_a, usuario_gestor_a, evento)
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO
    evento_guardado = EventoNFe.objects.get()
    assert evento_guardado.empresa is None
    assert evento_guardado.autor_documento == CNPJ_SEM_CADASTRO


def test_evento_de_empresa_do_escritorio_guarda_a_empresa_autora(
    escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento())
    assert EventoNFe.objects.get().empresa == emitente


def test_evento_reimportado_nao_duplica(escritorio_a, usuario_gestor_a, emitente):
    evento = _cancelamento()
    _enviar(escritorio_a, usuario_gestor_a, evento)
    lote = _enviar(escritorio_a, usuario_gestor_a, evento)
    assert _unico(lote).resultado == TipoResultadoArquivo.DUPLICADO
    assert EventoNFe.objects.count() == 1


def test_cancelamento_de_outro_escritorio_nao_cancela_a_nota_deste(
    escritorio_a, escritorio_b, usuario_gestor_a, usuario_gestor_b, emitente
):
    # Mesma chave, escritório diferente: o evento de B não altera a nota de A (isolamento).
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    _enviar(escritorio_b, usuario_gestor_b, _cancelamento())
    assert services.situacao_da_nfe(DocumentoNFe.objects.get(escritorio=escritorio_a)) == "valida"


# --- limites (HI-112, HI-22) ----------------------------------------------------------


def test_nfe_acima_de_4mb_e_recusada_com_limite_nomeado(escritorio_a, usuario_gestor_a, emitente):
    lote = _enviar(escritorio_a, usuario_gestor_a, _nfe_com_tamanho(TETO_NFE + 1))
    resultado = _unico(lote)
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert "NF-e acima do limite de" in resultado.motivo
    assert "HI-112" in resultado.motivo
    assert not DocumentoNFe.objects.exists()


def test_nfe_de_3mb_e_aceita_acima_do_teto_antigo_da_nfse(escritorio_a, usuario_gestor_a, emitente):
    lote = _enviar(escritorio_a, usuario_gestor_a, _nfe_com_tamanho(3 * MI))
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO


def test_nota_grande_com_muitos_itens_e_aceita(escritorio_a, usuario_gestor_a, emitente):
    # 990 itens é o máximo do XSD (leiauteNFe_v4.00.xsd:867). Cada item leva 500 caracteres de
    # informação adicional e um comentário XML de 300 bytes (sem efeito no leitor). A nota passa do
    # teto de 1 MB da NFS-e e fica abaixo do teto de 4 MB da NF-e.
    conteudo = xml_nfe(itens=990, info_adicional_item="x" * 500, comentario_por_item=300)
    assert TETO_NFSE < len(conteudo) < TETO_NFE
    lote = _enviar(escritorio_a, usuario_gestor_a, conteudo)
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO
    assert DocumentoNFe.objects.get().quantidade_itens == 990


def test_nfe_grande_dentro_de_zip_nao_e_cortada_antes_do_seu_teto(
    escritorio_a, usuario_gestor_a, emitente
):
    # A leitura de cada entrada do ZIP acompanha o teto da NF-e, não o da NFS-e.
    grande = _nfe_com_tamanho(2 * MI)
    lote = _enviar(escritorio_a, usuario_gestor_a, zip_de({"grande.xml": grande}), nome="l.zip")
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO


def test_nfse_acima_de_1mb_continua_recusada_com_a_mensagem_antiga(escritorio_a, usuario_gestor_a):
    lote = _enviar(escritorio_a, usuario_gestor_a, _nfse_com_tamanho(TETO_NFSE + 1))
    resultado = _unico(lote)
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert resultado.motivo == (f"Arquivo acima do limite de {TETO_NFSE} bytes por XML (HI-22).")


def test_nfse_entre_1mb_e_4mb_continua_recusada_pelo_teto_da_nfse(escritorio_a, usuario_gestor_a):
    lote = _enviar(escritorio_a, usuario_gestor_a, _nfse_com_tamanho(2 * MI))
    assert _unico(lote).resultado == TipoResultadoArquivo.RECUSADO
    assert "acima do limite" in _unico(lote).motivo


# --- relatório do lote (critério 9, tela) ----------------------------------------------


def test_relatorio_do_lote_mostra_nfe_nfce_e_evento_de_nfe(
    client, escritorio_a, usuario_gestor_a, emitente
):
    lote = _enviar(
        escritorio_a,
        usuario_gestor_a,
        zip_de(
            {
                "nfe.xml": xml_nfe(),
                "nfce.xml": xml_nfe(
                    modelo="65",
                    destinatario=None,
                    chave=chave_nfe(emitente=CNPJ_EMITENTE_A, modelo="65", numero="7"),
                    numero="7",
                ),
                "evento.xml": _cancelamento(),
            }
        ),
        nome="envio.zip",
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:relatorio_envio", args=[lote.id]))
    assert resposta.status_code == 200
    # O template quebra linha dentro da frase: compara com os espaços normalizados.
    conteudo = " ".join(resposta.content.decode("utf-8").split())
    assert "NF-e nº 1, série 1" in conteudo
    assert "NFC-e nº 7, série 1" in conteudo
    assert "Evento de NF-e 110111" in conteudo
    assert CHAVE_PADRAO in conteudo
    assert resposta.context["lote"].total_recebidos == 3


def test_auditoria_do_envio_nao_leva_conteudo_de_nota(escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    registro = RegistroAuditoria.objects.filter(acao="fiscal.envio_recebido").latest("id")
    texto = str(registro.detalhes)
    assert "Destinataria" not in texto and "Emitente Sintetica" not in texto
    assert CNPJ_EMITENTE_A not in texto
    assert LoteDeRecepcao.objects.count() == 1


def test_recepcao_de_nfe_nao_cria_evento_de_nfse(escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento())
    assert EventoFiscal.objects.count() == 0


def test_retorno_com_cstat_de_quatro_digitos_e_guardado_sem_erro(
    escritorio_a, usuario_gestor_a, emitente
):
    # Antes, o campo tinha 3 posições: retorno de 4 dígitos virava erro de dados e perdia o evento.
    lote = _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(c_stat="1000"))
    assert _unico(lote).resultado == TipoResultadoArquivo.RECEBIDO
    assert EventoNFe.objects.get().c_stat == "1000"


def test_retorno_nao_efetivo_seguido_de_cancelamento_aceito_com_o_mesmo_id_cancela(
    escritorio_a, usuario_gestor_a, emitente
):
    # Decisão do arquiteto (DL-080): o evento é único por (escritório, identificador, sha256). Um
    # retorno rejeitado e um cancelamento aceito, com o MESMO Id e conteúdos diferentes, são dois
    # registros: o segundo entra e o lote o sinaliza. A nota fica cancelada.
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    lote_rejeitado = _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat="128"))
    assert _unico(lote_rejeitado).resultado == TipoResultadoArquivo.RECEBIDO
    lote_aceito = _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat="135"))
    resultado = _unico(lote_aceito)
    assert resultado.resultado == TipoResultadoArquivo.RECEBIDO
    assert "conteúdo diferente" in resultado.motivo
    assert EventoNFe.objects.count() == 2
    assert services.situacao_da_nfe(DocumentoNFe.objects.get()) == "cancelada"


def test_cancelamento_aceito_seguido_de_retorno_nao_efetivo_com_o_mesmo_id_continua_cancelando(
    escritorio_a, usuario_gestor_a, emitente
):
    # A ordem inversa também cancela: a consulta vale para qualquer registro efetivo com a chave.
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat="135"))
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat="128"))
    assert EventoNFe.objects.count() == 2
    assert services.situacao_da_nfe(DocumentoNFe.objects.get()) == "cancelada"


def test_mesmo_id_e_mesmo_conteudo_continua_duplicado(escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat="135"))
    lote = _enviar(escritorio_a, usuario_gestor_a, _cancelamento(c_stat="135"))
    assert _unico(lote).resultado == TipoResultadoArquivo.DUPLICADO
    assert EventoNFe.objects.count() == 1


def test_entrada_de_nfse_grande_no_zip_continua_lida_so_ate_o_teto_da_nfse():
    # Igual ao que era antes desta frente: a NFS-e não é lida além de 1 MB + 1 byte.
    grande = _nfse_com_tamanho(2 * MI)
    itens = services._itens_do_zip(zip_de({"nfse.xml": grande}))
    assert len(itens[0][1]) == TETO_NFSE + 1


def test_entrada_de_nfe_grande_no_zip_e_lida_ate_o_seu_teto():
    grande = _nfe_com_tamanho(2 * MI)
    itens = services._itens_do_zip(zip_de({"nfe.xml": grande}))
    assert len(itens[0][1]) == 2 * MI
