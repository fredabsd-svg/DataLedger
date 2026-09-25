"""Camada de serviço da recepção de documentos fiscais — DL-010, fatia 1.

Contrato obrigatório do plano (docs/planos/DL-010-F1-recepcao-nfse.md):

- `receber_envio(*, escritorio, usuario, arquivo, nome_arquivo) -> LoteDeRecepcao`
- `documentos_do_escritorio(escritorio, *, empresa=None, competencia=None, situacao=None)
  -> QuerySet[DocumentoFiscal]`, SEMPRE queryset, cada linha anotada com o
  booleano `cancelada` (calculado no banco — contrato repassado à tela).
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
from django.db.models import Exists, OuterRef
from django.db.models.functions import Substr

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

# RC-112 (docs/projeto/requisitos.md, resposta do Fred de 2026-09-25 à
# PE-66): o escritório ATENDE cliente pessoa física que emite NFS-e com
# CPF. O cadastro de cliente pessoa física ainda NÃO existe nesta etapa
# (modelagem própria, em estudo) — enquanto não existir, a nota é recusada,
# mas com um motivo ESPECÍFICO, para não confundir "não é cliente" com "é
# cliente, mas o sistema ainda não tem onde cadastrá-lo". O texto NÃO
# depende de nada que exista ou não em outro escritório (critério 27
# continua valendo: a mensagem é sobre o TIPO do documento do XML, que o
# próprio remetente já sabe — não sobre o que este ou outro escritório tem
# cadastrado).
MENSAGEM_PARTICIPANTE_PESSOA_FISICA_SEM_CADASTRO = (
    "Participante pessoa física (CPF): cadastro de cliente pessoa física ainda não disponível."
)


def localizar_empresa_do_escritorio(escritorio, participante):
    """Ponto ÚNICO de identificação de empresa a partir de uma inscrição,
    dentro de um escritório (critério 13 do plano; DE-074 item 7).

    `participante` é um `apps.fiscal.leitor.ParticipanteLido` (ou `None`) —
    carrega a inscrição JUNTO do seu tipo (CNPJ/CPF/NIF/nao_informado), e é
    o tipo que decide o ramo de busca abaixo. Nenhum outro ponto do código
    presume que participante é sempre CNPJ.
    """
    if participante is None:
        return None
    if participante.tipo_documento == "CNPJ":
        return _localizar_empresa_por_cnpj(escritorio, participante.documento)
    if participante.tipo_documento == "CPF":
        # PONTO DE EXTENSÃO (RC-112): quando existir cadastro de cliente
        # pessoa física, a busca por CPF entra AQUI, no mesmo molde de
        # `_localizar_empresa_por_cnpj` — sempre filtrada pelo escritório.
        # Até lá, CPF nunca casa.
        return None
    # NIF (identificação fiscal estrangeira) e "nao_informado" (cNaoNIF)
    # nunca casam: não são inscrição de empresa brasileira cadastrável
    # neste sistema.
    return None


def _localizar_empresa_por_cnpj(escritorio, cnpj_bruto):
    """Busca em `Empresa.cnpj` E em `Estabelecimento.cnpj`, SEMPRE filtrando
    pelo escritório recebido — o CNPJ é único no sistema inteiro (PE-21),
    então uma busca SEM esse filtro encontraria empresa de OUTRO escritório,
    que é exatamente o vazamento que o critério 27 (isolamento) proíbe.
    """
    try:
        cnpj = normalizar_cnpj(cnpj_bruto)
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


def _tem_participante_pessoa_fisica(documento_lido: leitor.DocumentoLido) -> bool:
    if documento_lido.prestador is not None and documento_lido.prestador.tipo_documento == "CPF":
        return True
    return documento_lido.tomador is not None and documento_lido.tomador.tipo_documento == "CPF"


def _vincular_participantes(escritorio, documento_lido: leitor.DocumentoLido):
    """Localiza prestador e tomador entre as empresas do escritório e
    devolve a lista de `(empresa, papel)` a vincular. Levanta
    `leitor.ArquivoRecusado` se NENHUM dos dois casar — critério 5. A
    mensagem distingue "nenhum é cliente" de "o único candidato é pessoa
    física, sem cadastro ainda" (RC-112) — sem revelar, em nenhum dos dois
    casos, se o CNPJ pertence a alguém em outro escritório (critério 27).

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
        if _tem_participante_pessoa_fisica(documento_lido):
            raise leitor.ArquivoRecusado(MENSAGEM_PARTICIPANTE_PESSOA_FISICA_SEM_CADASTRO)
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


def _motivo_de_duplicado(existente, sha256_novo: str, rotulo: str) -> str:
    """Mensagem de um resultado "duplicado" — distingue o caso NORMAL
    (reenviar o mesmo arquivo, RC-69) do caso que merece CONFERÊNCIA:
    mesmo identificador (`escritorio` + `identificador`), conteúdo
    DIFERENTE do já guardado.

    O original NUNCA é sobrescrito de nenhum dos dois jeitos — a
    correção de lançamento fiscal já efetivado segue procedimento
    rastreável (AGENTS.md §10), nunca edição silenciosa; aqui não há
    edição alguma, só a mensagem muda para sinalizar a divergência.

    `rotulo` é "Documento" ou "Evento", para reusar a mesma função nos
    dois `except IntegrityError` de `_processar_um_arquivo`.
    """
    if existente is not None and existente.sha256_arquivo != sha256_novo:
        return (
            f"{rotulo} já recebido, mas o conteúdo deste arquivo é DIFERENTE "
            "do recebido antes — conferir."
        )
    return f"{rotulo} já recebido anteriormente por este escritório."


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
                f"Arquivo acima do limite de {LIMITE_TAMANHO_XML_BYTES} bytes por XML (HI-22)."
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
                "motivo": _motivo_de_duplicado(existente, sha256, "Documento"),
                "documento": existente,
            }
        existente = EventoFiscal.objects.filter(
            escritorio=escritorio, identificador=lido.identificador
        ).first()
        return {
            "resultado": TipoResultadoArquivo.DUPLICADO,
            "motivo": _motivo_de_duplicado(existente, sha256, "Evento"),
            "evento": existente,
        }

    if eh_documento:
        return {"resultado": TipoResultadoArquivo.RECEBIDO, "motivo": "", "documento": documento}
    return {"resultado": TipoResultadoArquivo.RECEBIDO, "motivo": "", "evento": evento}


_TAMANHO_DO_BLOCO_DE_LEITURA = 65536  # 64 KiB — só para o caminho genérico de `.read()`


def _ler_bytes_do_arquivo_enviado(arquivo) -> bytes:
    """`arquivo` é `bytes`/`bytearray` puro OU um arquivo de upload do
    Django (`UploadedFile`, que tem `.chunks()`). Devolve sempre `bytes`.

    Confere o limite de tamanho ANTES de terminar de ler, não depois
    (correção do arquiteto sobre a versão anterior desta função): um
    upload de 2 GB era lido por INTEIRO na memória — `b"".join(arquivo.
    chunks())` — antes de `receber_envio` sequer olhar o tamanho. Aqui:

    1. Se o objeto expõe `.size` (todo `UploadedFile` do Django expõe —
       `InMemoryUploadedFile` e `TemporaryUploadedFile`), o tamanho
       DECLARADO é conferido ANTES de chamar `.chunks()` — um upload que já
       se anuncia grande demais nunca chega a ser lido.
    2. Ao iterar `.chunks()` (ou, na ausência delas, ao ler em blocos
       fixos), a soma acumulada é conferida a CADA pedaço — a leitura para
       assim que ultrapassa o limite, sem terminar de consumir o restante
       do fluxo. Só o caso de `bytes`/`bytearray` já em memória (usado
       pelos testes e por chamadores que já têm o conteúdo pronto) escapa
       dessa checagem incremental; para ele, `receber_envio` confere o
       tamanho logo em seguida, e o custo de memória já existia antes de
       chegar aqui.

    Levanta `EnvioInvalido` diretamente quando o limite é ultrapassado —
    mais cedo do que `receber_envio`, de propósito.
    """
    if isinstance(arquivo, (bytes, bytearray)):
        return bytes(arquivo)

    tamanho_declarado = getattr(arquivo, "size", None)
    if tamanho_declarado is not None and tamanho_declarado > LIMITE_TAMANHO_ENVIO_BYTES:
        raise EnvioInvalido(
            f"O envio excede o limite de {LIMITE_TAMANHO_ENVIO_BYTES} bytes (HI-22)."
        )

    if hasattr(arquivo, "chunks"):
        pedacos = []
        total = 0
        for pedaco in arquivo.chunks():
            pedacos.append(pedaco)
            total += len(pedaco)
            if total > LIMITE_TAMANHO_ENVIO_BYTES:
                raise EnvioInvalido(
                    f"O envio excede o limite de {LIMITE_TAMANHO_ENVIO_BYTES} bytes (HI-22)."
                )
        return b"".join(pedacos)

    if hasattr(arquivo, "read"):
        # Objeto genérico de arquivo (não é UploadedFile do Django, sem
        # `.chunks()`): lê em blocos fixos, nunca `arquivo.read()` sem
        # argumento, pela mesma razão do ramo acima.
        pedacos = []
        total = 0
        while True:
            bloco = arquivo.read(_TAMANHO_DO_BLOCO_DE_LEITURA)
            if not bloco:
                break
            pedacos.append(bloco)
            total += len(bloco)
            if total > LIMITE_TAMANHO_ENVIO_BYTES:
                raise EnvioInvalido(
                    f"O envio excede o limite de {LIMITE_TAMANHO_ENVIO_BYTES} bytes (HI-22)."
                )
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        return b"".join(pedacos)

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
            # Lê no máximo LIMITE_TAMANHO_XML_BYTES + 1 bytes desta
            # ENTRADA — nunca o resto da cota total (correção do
            # arquiteto): o limite por arquivo já é 1 MB (HI-22); ler até
            # ~200 MB de uma única entrada só para descartá-la depois como
            # "recusado" (arquivo grande demais) desperdiça memória à toa
            # e é o mesmo ataque do ZIP que mente no `file_size` do
            # cabeçalho, só que por dentro de uma entrada só. Este limite
            # NÃO precisa ser lido por inteiro para sabermos que excede: o
            # byte a mais já prova isso, e o conteúdo truncado nunca chega
            # a ser interpretado como XML — `_processar_um_arquivo` recusa
            # pelo tamanho ANTES de chamar o leitor.
            dados = membro.read(LIMITE_TAMANHO_XML_BYTES + 1)
        # A soma acumulada ENTRE entradas continua protegendo o limite
        # total descompactado (HI-22): mesmo com cada leitura individual
        # capada, um ZIP com milhares de entradas grandes ainda esbarra
        # aqui antes de qualquer uma delas ser processada.
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
        ResultadoDoArquivo.objects.create(
            lote=lote, caminho_no_zip=caminho_no_zip, resultado=resultado, **info
        )
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


# HI-20 (docs/projeto/requisitos.md): os quatro códigos de evento que
# CANCELAM a NFS-e. Fonte: leitura das DESCRIÇÕES de cada elemento em
# tiposEventos_v1.01.xsd (xs:documentation de e101101/e105102/e105104/
# e305101) — a CONSEQUÊNCIA JURÍDICA de cada evento não está escrita no
# esquema, só a descrição textual; por isso é hipótese, não regra
# confirmada. e101103 (só a SOLICITAÇÃO de análise fiscal) e e105105
# (INDEFERIDO) NÃO cancelam — são o meio do caminho, não o fim.
CODIGOS_QUE_CANCELAM = frozenset({"e101101", "e105102", "e105104", "e305101"})


def documentos_do_escritorio(escritorio, *, empresa=None, competencia=None, situacao=None):
    """Consulta de `DocumentoFiscal`, SEMPRE filtrada pelo escritório
    (RC-18/AGENTS.md §11) — nunca lista documento de outro escritório,
    mesmo que `empresa` pertença a outro por engano do chamador (o filtro
    de `empresa` é ADICIONAL ao de `escritorio`, nunca um substituto).

    Devolve SEMPRE uma `QuerySet` (nunca materializa em lista), anotada com
    um booleano `cancelada` em cada linha — correção do arquiteto sobre a
    versão anterior, que calculava a situação em PYTHON, um `SELECT` de
    eventos por documento (5.000 notas viravam 5.000 consultas). A
    anotação usa `Exists`/`OuterRef` — a situação é calculada no PRÓPRIO
    banco, então listar N documentos com `situacao` continua custando UMA
    consulta, não N. **Este é o contrato que a tela (etapa 2) consome:**
    cada `DocumentoFiscal` do resultado tem `.cancelada` (`bool`) pronto,
    sem consulta adicional.

    `empresa`: filtra pelos documentos em que essa `Empresa` tem vínculo
    (prestador ou tomador).
    `competencia`: tupla/sequência `(ano, mes)` — filtra por `d_competencia`.
    `situacao`: `"valida"` ou `"cancelada"` — vira `.filter(cancelada=...)`
    sobre a anotação, dentro da mesma consulta. Qualquer outro valor não
    nulo levanta `ValueError` — silenciosamente devolver uma lista vazia
    para um valor digitado errado esconderia o erro de quem chama.
    """
    qs = DocumentoFiscal.objects.filter(escritorio=escritorio)
    if empresa is not None:
        qs = qs.filter(vinculos__empresa=empresa).distinct()
    if competencia is not None:
        ano, mes = competencia
        qs = qs.filter(d_competencia__year=ano, d_competencia__month=mes)

    # `Substr(..., 4)` descarta os 3 primeiros caracteres ("NFS") do
    # identificador do documento (posição 1-indexada do SQL: começa no
    # 4º caractere) para comparar com `EventoFiscal.chave_nfse`, que é só
    # os 50 dígitos sem o prefixo — mesma conversão que a versão anterior
    # fazia em Python (`documento.identificador[3:]`), agora dentro da
    # subconsulta correlacionada.
    eventos_de_cancelamento = EventoFiscal.objects.filter(
        escritorio_id=OuterRef("escritorio_id"),
        chave_nfse=Substr(OuterRef("identificador"), 4),
        codigo__in=CODIGOS_QUE_CANCELAM,
    )
    qs = qs.annotate(cancelada=Exists(eventos_de_cancelamento))
    qs = qs.order_by("-dh_emissao")

    if situacao is None:
        return qs
    if situacao == "cancelada":
        return qs.filter(cancelada=True)
    if situacao == "valida":
        return qs.filter(cancelada=False)
    raise ValueError(f"situacao deve ser 'valida' ou 'cancelada' (recebido {situacao!r}).")


def situacao_do_documento(documento: DocumentoFiscal) -> str:
    """`"valida"` ou `"cancelada"` — DERIVADA dos eventos do MESMO
    escritório cuja chave referencia esta nota (DE-074 item 4), NUNCA
    gravada no documento: assim a ORDEM de chegada (nota antes ou depois do
    evento, RC-70) não importa, e não existe um campo de estado para
    envelhecer.

    Se `documento` veio de `documentos_do_escritorio` (já anotado com
    `.cancelada`), usa a anotação — CUSTO ZERO, nenhuma consulta nova, o
    que evita o N+1 ao percorrer uma lista de documentos. Se veio de outro
    caminho (ex.: `DocumentoFiscal.objects.get(...)`, sem a anotação),
    consulta os eventos diretamente. `Exists` nunca devolve `NULL`, então
    distinguir "sem anotação" de "anotação com valor `False`" por
    `getattr(..., None)` é seguro.

    `DocumentoFiscal.identificador` é "NFS" + 50 dígitos (TSIdNFSe);
    `EventoFiscal.chave_nfse` é só os 50 dígitos, sem o prefixo (TSChaveNFSe)
    — a conversão entre os dois formatos vive só aqui (e, em SQL, dentro de
    `documentos_do_escritorio` acima).
    """
    cancelada = getattr(documento, "cancelada", None)
    if cancelada is None:
        chave_sem_prefixo = documento.identificador[3:]
        cancelada = EventoFiscal.objects.filter(
            escritorio_id=documento.escritorio_id,
            chave_nfse=chave_sem_prefixo,
            codigo__in=CODIGOS_QUE_CANCELAM,
        ).exists()
    return "cancelada" if cancelada else "valida"
