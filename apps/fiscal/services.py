"""Camada de serviço da recepção de documentos fiscais — DL-010, fatia 1.

Contrato obrigatório do plano (docs/planos/DL-010-F1-recepcao-nfse.md):

- `receber_envio(*, escritorio, usuario, arquivo, nome_arquivo) -> LoteDeRecepcao`
- `documentos_do_escritorio(escritorio, *, empresa=None, competencia=None, situacao=None)`
- `situacao_do_documento(documento) -> "valida" | "cancelada"`

Nenhuma regra deste módulo é duplicada em `apps.fiscal.permissoes` nem em
`apps.fiscal.leitor` — cada um cuida de UMA coisa (autorização, leitura de
XML, orquestração de gravação), e este arquivo é quem os liga.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa, Estabelecimento
from apps.empresas.validators import normalizar_cnpj
from apps.fiscal import leitor
from apps.fiscal.models import (
    DocumentoFiscal,
    EventoFiscal,
    LoteDeRecepcao,
    PapelDocumento,
    ResultadoDoArquivo,
    TipoDocumentoFiscal,
    TipoResultadoArquivo,
    VinculoDocumentoEmpresa,
)

# ---------------------------------------------------------------------------
# HI-22 (docs/projeto/requisitos.md): limites de um envio. NÃO são regra
# confirmada pelo Fred — são hipótese registrada, dimensionada pelo acervo
# real que ele enviou (5.850 arquivos cabem com folga). Existem para que um
# ZIP hostil não consuma memória/tempo proporcional a um conteúdo forjado
# pelo remetente, não porque medimos o teto real do escritório.
LIMITE_TAMANHO_ENVIO_BYTES = 50 * 1024 * 1024  # 50 MB
LIMITE_ARQUIVOS_NO_ENVIO = 10_000
LIMITE_TAMANHO_XML_BYTES = 1 * 1024 * 1024  # 1 MB por XML
LIMITE_DESCOMPACTADO_BYTES = 200 * 1024 * 1024  # 200 MB


class EnvioInvalido(ValidationError):
    """O ENVIO INTEIRO é inválido: vazio, grande demais, ZIP corrompido,
    aninhado, cifrado, ou acima de algum limite da HI-22.

    Diferente de um arquivo ruim DENTRO de um envio válido — isso vira um
    `ResultadoDoArquivo` "recusado" e não impede os demais (critério 7/8).
    `EnvioInvalido` interrompe o envio inteiro ANTES de gravar qualquer
    coisa (nem o `LoteDeRecepcao` chega a ser criado).
    """


# Mensagem de recusa por "nenhum participante é empresa deste escritório" —
# UMA só, usada para prestador e tomador, com ou sem tomador presente no
# XML. Critério 27 do plano: a mensagem tem que ser IDÊNTICA exista ou não
# a empresa em OUTRO escritório — nunca dar pista de que o CNPJ pertence a
# alguém, para que a importação não vire ferramenta de descobrir CNPJ de
# cliente alheio.
MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO = (
    "Nenhum participante deste documento (prestador ou tomador) pertence a "
    "uma empresa deste escritório."
)


def localizar_empresa_do_escritorio(escritorio, participante):
    """Ponto ÚNICO de identificação de empresa por CNPJ, dentro de um
    escritório (critério 13 do plano; DE-074 item 7).

    Procura em `Empresa.cnpj` E em `Estabelecimento.cnpj`, SEMPRE filtrando
    pelo escritório recebido — o CNPJ é único no sistema inteiro (PE-21),
    então uma busca SEM esse filtro encontraria empresa de OUTRO escritório,
    que é exatamente o vazamento que o critério 27 (isolamento) proíbe.

    `participante` é um `apps.fiscal.leitor.ParticipanteLido` (ou `None`).
    CPF NUNCA casa: `Empresa` não tem campo de CPF hoje (PE-66 — cliente
    pessoa física prestador de serviço não tem onde ser cadastrado; a nota
    é recusada com motivo, não adivinhada). `NIF` e `nao_informado` também
    nunca casam, pelo mesmo motivo — não são CNPJ.
    """
    if participante is None or participante.tipo_documento != "CNPJ":
        return None
    try:
        cnpj = normalizar_cnpj(participante.documento)
    except ValidationError:
        return None
    empresa = Empresa.objects.filter(escritorio=escritorio, cnpj=cnpj).first()
    if empresa is not None:
        return empresa
    estabelecimento = (
        Estabelecimento.objects.filter(empresa__escritorio=escritorio, cnpj=cnpj)
        .select_related("empresa")
        .first()
    )
    if estabelecimento is not None:
        return estabelecimento.empresa
    return None


def _vincular_participantes(escritorio, documento_lido: leitor.DocumentoLido):
    """Localiza prestador e tomador entre as empresas do escritório e
    devolve a lista de `(empresa, papel)` a vincular. Levanta
    `leitor.ArquivoRecusado` se NENHUM dos dois casar — critério 5.

    Quando prestador e tomador são a MESMA empresa do escritório (nota de
    uma empresa para ela mesma), só um vínculo é criado, como prestador —
    a igualdade evita a violação da unicidade `(documento, empresa)` de
    `VinculoDocumentoEmpresa`.
    """
    vinculos = []
    empresa_prestador = localizar_empresa_do_escritorio(escritorio, documento_lido.prestador)
    if empresa_prestador is not None:
        vinculos.append((empresa_prestador, PapelDocumento.PRESTADOR))
    empresa_tomador = localizar_empresa_do_escritorio(escritorio, documento_lido.tomador)
    if empresa_tomador is not None and empresa_tomador != empresa_prestador:
        vinculos.append((empresa_tomador, PapelDocumento.TOMADOR))
    if not vinculos:
        raise leitor.ArquivoRecusado(MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO)
    return vinculos


def _criar_documento_e_vinculos(escritorio, lido: leitor.DocumentoLido) -> DocumentoFiscal:
    # A checagem de isolamento acontece ANTES de qualquer escrita: uma nota
    # sem participante do escritório nunca chega a tocar o banco.
    vinculos_alvo = _vincular_participantes(escritorio, lido)

    documento = DocumentoFiscal.objects.create(
        escritorio=escritorio,
        tipo=TipoDocumentoFiscal.NFSE_NACIONAL,
        versao=lido.versao,
        identificador=lido.identificador,
        xml_original=lido.xml_bytes,
        sha256_arquivo=lido.sha256,
        numero=lido.numero,
        dh_emissao=lido.dh_emissao,
        d_competencia=lido.d_competencia,
        prestador_tipo_documento=lido.prestador.tipo_documento,
        prestador_documento=lido.prestador.documento,
        prestador_nome=lido.prestador.nome,
        tomador_tipo_documento=lido.tomador.tipo_documento if lido.tomador else "",
        tomador_documento=lido.tomador.documento if lido.tomador else "",
        tomador_nome=lido.tomador.nome if lido.tomador else "",
        v_serv=lido.v_serv,
        v_liq=lido.v_liq,
        tp_ret_issqn=lido.tp_ret_issqn,
    )  # pode levantar IntegrityError (escritorio+identificador já existe) —
    # tratado por quem chama (_processar_um_arquivo), fora deste savepoint.

    for empresa, papel in vinculos_alvo:
        VinculoDocumentoEmpresa.objects.create(documento=documento, empresa=empresa, papel=papel)

    return documento


def _criar_evento(escritorio, lido: leitor.EventoLido) -> EventoFiscal:
    # Evento ÓRFÃO (sem empresa identificável) é aceito e guardado — RC-70,
    # critério 17. Diferente do documento, o evento NUNCA é recusado por
    # falta de participante do escritório.
    empresa = None
    if lido.autor is not None:
        empresa = localizar_empresa_do_escritorio(escritorio, lido.autor)
    return EventoFiscal.objects.create(
        escritorio=escritorio,
        identificador=lido.identificador,
        codigo=lido.codigo,
        chave_nfse=lido.chave_nfse,
        data_evento=lido.data_evento,
        xml_original=lido.xml_bytes,
        sha256_arquivo=lido.sha256,
        empresa=empresa,
    )  # pode levantar IntegrityError (escritorio+identificador já existe) —
    # tratado por quem chama, fora deste savepoint.


def _processar_um_arquivo(escritorio, conteudo: bytes) -> dict:
    """Processa UM arquivo já extraído (XML solto, ou uma entrada do ZIP).

    Nunca levanta exceção — devolve um dicionário pronto para
    `ResultadoDoArquivo.objects.create(**dicionario)` (menos `lote` e
    `caminho_no_zip`, que quem chama acrescenta). Cada arquivo grava em seu
    próprio `transaction.atomic()` (savepoint, DE-074 item 5/critério 28):
    um `IntegrityError` de unicidade dentro dele vira "duplicado"; qualquer
    outro problema vira "recusado" — nenhum dos dois propaga e derruba o
    envio inteiro (critério 7/8).
    """
    if len(conteudo) > LIMITE_TAMANHO_XML_BYTES:
        return {
            "resultado": TipoResultadoArquivo.RECUSADO,
            "motivo": (
                f"Arquivo acima do limite de {LIMITE_TAMANHO_XML_BYTES} bytes "
                "por XML (HI-22)."
            ),
        }

    sha256 = hashlib.sha256(conteudo).hexdigest()

    try:
        lido = leitor.ler_arquivo(conteudo, sha256)
    except leitor.ArquivoRecusado as exc:
        return {"resultado": TipoResultadoArquivo.RECUSADO, "motivo": str(exc)}

    eh_documento = isinstance(lido, leitor.DocumentoLido)

    try:
        # `transaction.atomic()` aninhado dentro do `atomic()` de
        # `receber_envio` vira SAVEPOINT (comportamento padrão do Django) —
        # é o que isola o `IntegrityError` de um arquivo sem poluir a
        # transação do lote inteiro.
        with transaction.atomic():
            if eh_documento:
                documento = _criar_documento_e_vinculos(escritorio, lido)
            else:
                evento = _criar_evento(escritorio, lido)
    except leitor.ArquivoRecusado as exc:
        return {"resultado": TipoResultadoArquivo.RECUSADO, "motivo": str(exc)}
    except IntegrityError:
        # A conexão já está de volta a um estado utilizável (o `atomic()`
        # fez ROLLBACK TO SAVEPOINT ao sair por exceção) — a consulta
        # abaixo roda na transação EXTERNA, ainda válida.
        if eh_documento:
            existente = DocumentoFiscal.objects.filter(
                escritorio=escritorio, identificador=lido.identificador
            ).first()
            return {
                "resultado": TipoResultadoArquivo.DUPLICADO,
                "motivo": "Documento já recebido anteriormente por este escritório.",
                "documento": existente,
            }
        existente = EventoFiscal.objects.filter(
            escritorio=escritorio, identificador=lido.identificador
        ).first()
        return {
            "resultado": TipoResultadoArquivo.DUPLICADO,
            "motivo": "Evento já recebido anteriormente por este escritório.",
            "evento": existente,
        }

    if eh_documento:
        return {"resultado": TipoResultadoArquivo.RECEBIDO, "motivo": "", "documento": documento}
    return {"resultado": TipoResultadoArquivo.RECEBIDO, "motivo": "", "evento": evento}


def _ler_bytes_do_arquivo_enviado(arquivo) -> bytes:
    """`arquivo` é `bytes`/`bytearray` puro OU um arquivo de upload do
    Django (`UploadedFile`, que tem `.chunks()`). Devolve sempre `bytes`."""
    if isinstance(arquivo, (bytes, bytearray)):
        return bytes(arquivo)
    if hasattr(arquivo, "chunks"):
        return b"".join(arquivo.chunks())
    if hasattr(arquivo, "read"):
        conteudo = arquivo.read()
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        return conteudo
    raise TypeError("arquivo deve ser bytes ou um objeto de upload do Django.")


def _e_zip(conteudo: bytes) -> bool:
    # Assinatura de ZIP: PK\x03\x04 (entrada normal) ou PK\x05\x06 (arquivo
    # vazio). Classificação pelo CONTEÚDO, nunca pela extensão do nome do
    # arquivo (RC-71) — vale também para o envio como um todo.
    return conteudo[:4] in (b"PK\x03\x04", b"PK\x05\x06")


def _itens_do_zip(conteudo: bytes) -> list[tuple[str, bytes]]:
    """Extrai (caminho, bytes) de cada entrada do ZIP, sem escrever nada em
    disco (critério 25). Levanta `EnvioInvalido` para as condições que
    tornam o ZIP INTEIRO hostil: corrompido, mais entradas que o limite,
    conteúdo descompactado acima do limite (conferido pelo TAMANHO
    DECLARADO no cabeçalho E por um limite REAL na leitura — um ZIP
    malicioso pode declarar um `file_size` pequeno e entregar muito mais
    bytes ao descompactar), ZIP dentro de ZIP, ou entrada cifrada.
    Diretórios são ignorados.
    """
    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as exc:
        raise EnvioInvalido(f"ZIP corrompido: {exc}") from exc

    infos = arquivo_zip.infolist()
    if len(infos) > LIMITE_ARQUIVOS_NO_ENVIO:
        raise EnvioInvalido(
            f"O envio tem {len(infos)} arquivos, acima do limite de "
            f"{LIMITE_ARQUIVOS_NO_ENVIO} (HI-22)."
        )

    total_declarado = 0
    for info in infos:
        if info.is_dir():
            continue
        # Bit 0 de flag_bits é o de senha (criptografia clássica do
        # formato ZIP) — a biblioteca padrão não sabe descriptografar sem
        # senha, então tratamos como hostil, nunca tentamos adivinhar.
        if info.flag_bits & 0x1:
            raise EnvioInvalido(f"Entrada cifrada no ZIP: {info.filename!r}.")
        total_declarado += info.file_size
    if total_declarado > LIMITE_DESCOMPACTADO_BYTES:
        raise EnvioInvalido(
            f"O conteúdo descompactado declarado ({total_declarado} bytes) "
            f"excede o limite de {LIMITE_DESCOMPACTADO_BYTES} bytes (HI-22)."
        )

    total_lido = 0
    itens = []
    for info in infos:
        if info.is_dir():
            continue
        with arquivo_zip.open(info) as membro:
            # Lê com um limite REAL (nunca confia só no header declarado):
            # pedimos 1 byte A MAIS do que o restante da cota — se vier
            # esse byte extra, o conteúdo descompactado real excede o
            # limite, e abortamos sem ter lido o arquivo inteiro na
            # memória.
            cota_restante = LIMITE_DESCOMPACTADO_BYTES - total_lido
            dados = membro.read(cota_restante + 1)
        total_lido += len(dados)
        if total_lido > LIMITE_DESCOMPACTADO_BYTES:
            raise EnvioInvalido(
                f"O conteúdo descompactado excede o limite de "
                f"{LIMITE_DESCOMPACTADO_BYTES} bytes (HI-22) na leitura real."
            )
        if _e_zip(dados):
            raise EnvioInvalido(f"ZIP dentro de ZIP não é suportado: {info.filename!r}.")
        itens.append((info.filename, dados))
    return itens


def _itens_do_envio(conteudo: bytes, nome_arquivo: str) -> list[tuple[str, bytes]]:
    if _e_zip(conteudo):
        return _itens_do_zip(conteudo)
    # Não é ZIP: o próprio envio é o único arquivo (XML solto).
    return [(nome_arquivo, conteudo)]


@transaction.atomic
def receber_envio(*, escritorio, usuario, arquivo, nome_arquivo) -> LoteDeRecepcao:
    """Recebe um envio (um XML solto ou um ZIP de XMLs) e devolve o
    `LoteDeRecepcao` com o resultado de cada arquivo.

    Nunca levanta exceção por causa de um arquivo RUIM dentro do envio — o
    arquivo vira um `ResultadoDoArquivo` "recusado" e o processamento
    continua para os demais (critério 7/8). Levanta `EnvioInvalido` só
    quando o ENVIO INTEIRO é inválido: vazio, acima de
    `LIMITE_TAMANHO_ENVIO_BYTES`, ZIP corrompido, com mais de
    `LIMITE_ARQUIVOS_NO_ENVIO` entradas, ou com mais de
    `LIMITE_DESCOMPACTADO_BYTES` de conteúdo descompactado (HI-22) — nesses
    casos nada é gravado, nem o `LoteDeRecepcao`.

    Todo o processamento — o lote, cada arquivo (em seu próprio savepoint)
    e o registro de auditoria — roda em UMA transação (`@transaction.
    atomic`, DE-074 item 5, critério 31): ou o envio inteiro é gravado, ou
    nada é.
    """
    conteudo = _ler_bytes_do_arquivo_enviado(arquivo)

    if not conteudo:
        raise EnvioInvalido("O envio está vazio.")
    if len(conteudo) > LIMITE_TAMANHO_ENVIO_BYTES:
        raise EnvioInvalido(
            f"O envio excede o limite de {LIMITE_TAMANHO_ENVIO_BYTES} bytes (HI-22)."
        )

    sha256_envio = hashlib.sha256(conteudo).hexdigest()
    itens = _itens_do_envio(conteudo, nome_arquivo)

    lote = LoteDeRecepcao.objects.create(
        escritorio=escritorio,
        usuario=usuario,
        nome_arquivo=nome_arquivo,
        sha256_arquivo=sha256_envio,
        tamanho_bytes=len(conteudo),
    )

    contagens = {
        TipoResultadoArquivo.RECEBIDO: 0,
        TipoResultadoArquivo.DUPLICADO: 0,
        TipoResultadoArquivo.RECUSADO: 0,
    }
    for caminho_no_zip, conteudo_arquivo in itens:
        info = _processar_um_arquivo(escritorio, conteudo_arquivo)
        resultado = info.pop("resultado")
        ResultadoDoArquivo.objects.create(lote=lote, caminho_no_zip=caminho_no_zip, resultado=resultado, **info)
        contagens[resultado] += 1

    lote.total_arquivos = len(itens)
    lote.total_recebidos = contagens[TipoResultadoArquivo.RECEBIDO]
    lote.total_duplicados = contagens[TipoResultadoArquivo.DUPLICADO]
    lote.total_recusados = contagens[TipoResultadoArquivo.RECUSADO]
    lote.save(
        update_fields=["total_arquivos", "total_recebidos", "total_duplicados", "total_recusados"]
    )

    # Critério 31: contagens e SHA-256 do ENVIO, nunca conteúdo de XML nem
    # dado de terceiro (nome/CNPJ de participante fica de fora de
    # propósito — AGENTS.md §11, trilha protegida sem expor segredo).
    registrar(
        acao="fiscal.envio_recebido",
        usuario=usuario,
        escritorio=escritorio,
        objeto=lote,
        detalhes={
            "sha256_arquivo": sha256_envio,
            "total_arquivos": lote.total_arquivos,
            "total_recebidos": lote.total_recebidos,
            "total_duplicados": lote.total_duplicados,
            "total_recusados": lote.total_recusados,
        },
    )

    return lote


def documentos_do_escritorio(escritorio, *, empresa=None, competencia=None, situacao=None):
    """Consulta de `DocumentoFiscal`, SEMPRE filtrada pelo escritório
    (RC-18/AGENTS.md §11) — nunca lista documento de outro escritório,
    mesmo que `empresa` pertença a outro por engano do chamador (o filtro
    de `empresa` é ADICIONAL ao de `escritorio`, nunca um substituto).

    `empresa`: filtra pelos documentos em que essa `Empresa` tem vínculo
    (prestador ou tomador).
    `competencia`: tupla/sequência `(ano, mes)` — filtra por `d_competencia`.
    `situacao`: `"valida"` ou `"cancelada"` — como a situação é DERIVADA dos
    eventos (nunca uma coluna), filtrar por ela materializa a consulta em
    uma lista (não uma queryset preguiçosa); sem esse filtro, o retorno
    continua sendo uma queryset, para quem chama poder paginar/encadear.
    """
    qs = DocumentoFiscal.objects.filter(escritorio=escritorio)
    if empresa is not None:
        qs = qs.filter(vinculos__empresa=empresa).distinct()
    if competencia is not None:
        ano, mes = competencia
        qs = qs.filter(d_competencia__year=ano, d_competencia__month=mes)
    qs = qs.order_by("-dh_emissao")
    if situacao is None:
        return qs
    return [documento for documento in qs if situacao_do_documento(documento) == situacao]


# HI-20 (docs/projeto/requisitos.md): os quatro códigos de evento que
# CANCELAM a NFS-e. Fonte: leitura das DESCRIÇÕES de cada elemento em
# tiposEventos_v1.01.xsd (xs:documentation de e101101/e105102/e105104/
# e305101) — a CONSEQUÊNCIA JURÍDICA de cada evento não está escrita no
# esquema, só a descrição textual; por isso é hipótese, não regra
# confirmada. e101103 (só a SOLICITAÇÃO de análise fiscal) e e105105
# (INDEFERIDO) NÃO cancelam — são o meio do caminho, não o fim.
CODIGOS_QUE_CANCELAM = frozenset({"e101101", "e105102", "e105104", "e305101"})


def situacao_do_documento(documento: DocumentoFiscal) -> str:
    """`"valida"` ou `"cancelada"` — DERIVADA dos eventos do MESMO
    escritório cuja chave referencia esta nota (DE-074 item 4), NUNCA
    gravada no documento: assim a ORDEM de chegada (nota antes ou depois do
    evento, RC-70) não importa, e não existe um campo de estado para
    envelhecer.

    `DocumentoFiscal.identificador` é "NFS" + 50 dígitos (TSIdNFSe);
    `EventoFiscal.chave_nfse` é só os 50 dígitos, sem o prefixo (TSChaveNFSe)
    — a conversão entre os dois formatos vive só aqui.
    """
    chave_sem_prefixo = documento.identificador[3:]
    tem_cancelamento = EventoFiscal.objects.filter(
        escritorio_id=documento.escritorio_id,
        chave_nfse=chave_sem_prefixo,
        codigo__in=CODIGOS_QUE_CANCELAM,
    ).exists()
    return "cancelada" if tem_cancelamento else "valida"
