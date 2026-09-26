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
import logging
import re
import zipfile
import zlib

from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, OperationalError, connection, transaction
from django.db.models import Exists, OuterRef
from django.db.models.functions import Substr

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa, Estabelecimento
from apps.empresas.validators import normalizar_cnpj, normalizar_cpf
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HI-22 (docs/projeto/requisitos.md), REVISTA por DE-076 (auditoria rodada
# 1, achado A4): a auditoria mediu 37 s para 5.850 arquivos e 61 s para
# 10.000, acima dos 30 s do servidor de aplicação (`Dockerfile`, `gunicorn`
# sem `--timeout`). LIMITE_ARQUIVOS_NO_ENVIO caiu de 10.000 para 2.000 —
# ver a medição de vazão registrada no relatório desta rodada de correção
# (test_dl076_vazao_do_envio.py) — e a identificação de empresa por arquivo
# passou a reaproveitar um DICIONÁRIO montado uma vez por envio
# (`_mapa_de_inscricoes_do_escritorio`), em vez de consultar o banco a cada
# arquivo. Os demais limites não são regra confirmada pelo Fred — são
# hipótese registrada. Existem para que um ZIP hostil não consuma memória/
# tempo proporcional a um conteúdo forjado pelo remetente, não porque
# medimos o teto real do escritório.
LIMITE_TAMANHO_ENVIO_BYTES = 50 * 1024 * 1024  # 50 MB
LIMITE_ARQUIVOS_NO_ENVIO = 2_000
LIMITE_TAMANHO_XML_BYTES = 1 * 1024 * 1024  # 1 MB por XML
LIMITE_DESCOMPACTADO_BYTES = 200 * 1024 * 1024  # 200 MB

# DE-076 item 1 (achado A3): um envio por vez, por escritório. Namespace
# FIXO e arbitrário (as duas metades de um lock consultivo do PostgreSQL
# são sempre DOIS `int4`) — combinado com o `id` do escritório, forma uma
# chave estável e específica deste mecanismo, que não colide com nenhum
# outro uso de `pg_advisory_xact_lock` no sistema (não há outro, hoje; o
# namespace existe para o dia em que houver).
_NAMESPACE_LOCK_ENVIO_FISCAL = 0x444C3130  # arbitrário, só precisa ser fixo

MENSAGEM_ENVIO_EM_ANDAMENTO = (
    "Já há um envio em processamento neste escritório; aguarde terminar e envie de novo."
)

# Qualquer OperationalError que ESCAPE do bloqueio consultivo acima (ele
# não espera, então não deveria produzir espera nem impasse — mas a DE-076
# pede defesa em profundidade para qualquer um que ainda ocorra, por
# concorrência com outra operação do banco fora deste mecanismo) — SÓ os
# dois SQLSTATE abaixo (e o texto equivalente, quando o driver não expõe
# `pgcode`) viram `EnvioInvalido` legível. Qualquer outro `OperationalError`
# sobe intacto — nunca mascarar um erro de sistema genuíno como se fosse
# concorrência de envio.
_SQLSTATE_LOCK_OU_DEADLOCK = frozenset({"40P01", "55P03", "57014"})
_PADRAO_LOCK_OU_DEADLOCK = re.compile(
    r"deadlock detected|lock timeout|could not obtain lock|canceling statement due to lock timeout",
    re.IGNORECASE,
)


def _e_erro_de_lock_ou_deadlock(exc: OperationalError) -> bool:
    pgcode = getattr(getattr(exc, "__cause__", None), "pgcode", None)
    if pgcode in _SQLSTATE_LOCK_OU_DEADLOCK:
        return True
    return bool(_PADRAO_LOCK_OU_DEADLOCK.search(str(exc)))


def _adquirir_lock_de_envio_do_escritorio(escritorio) -> bool:
    """`pg_try_advisory_xact_lock` — NÃO espera: devolve na hora `True`
    (conseguiu) ou `False` (outro envio do MESMO escritório já segura o
    lock). O lock é escopado à TRANSAÇÃO (`_xact_`) — libera sozinho no
    COMMIT ou ROLLBACK, mesmo se o processo morrer no meio; nunca precisa
    de unlock explícito. `receber_envio` é `@transaction.atomic`, então a
    transação já está aberta quando esta função roda.

    Achado da revisão da DL-039 (Fred, revisão de commit): `pg_try_
    advisory_xact_lock` é função do PostgreSQL — não existe em SQLite, e
    `config/settings.py` permite SQLite em desenvolvimento (`DEBUG=True`
    sem `DATABASE_URL`, BL-50/DE-014). Sem esta guarda, um envio pela tela
    em SQLite local quebrava com erro de banco na hora de adquirir o
    lock. Em SQLite (`connection.vendor != "postgresql"`) devolve sempre
    `True` (nunca recusa por "envio em processamento") — SQLite já
    SERIALIZA toda escrita no nível do arquivo do banco inteiro (só uma
    conexão escreve por vez), então a invariante "um envio por vez, por
    escritório" fica, ali, subsumida pela invariante mais grosseira "um
    escritor por vez, no banco inteiro"; nunca é o mecanismo real de
    produção (SQLite não é ambiente de produção deste sistema, DE-014).
    """
    if connection.vendor != "postgresql":
        return True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_xact_lock(%s, %s)",
            [_NAMESPACE_LOCK_ENVIO_FISCAL, escritorio.pk],
        )
        (obteve,) = cursor.fetchone()
    return obteve


_TAMANHO_MAXIMO_MOTIVO = 500  # ResultadoDoArquivo.motivo (models.py)
_TAMANHO_MAXIMO_CAMINHO_NO_ZIP = 500  # ResultadoDoArquivo.caminho_no_zip (models.py)

# Achado N1 (reconferência DL-010/DL-038, BL-526): mensagem NEUTRA para o
# `DataError` capturado por arquivo — nunca `str(exc)` do driver do banco,
# que ecoa nome de tabela/coluna (informação interna de esquema, não algo
# que o contador deveria ver). O detalhe completo vai só para o log
# (`logger.warning`, abaixo), nunca para `ResultadoDoArquivo.motivo`.
MENSAGEM_ERRO_DE_DADOS_NO_ARQUIVO = (
    "Arquivo recusado: os dados deste arquivo não puderam ser gravados. "
    "Detalhe técnico registrado no log do servidor."
)


def _truncar(texto: str, tamanho: int) -> str:
    """Corta `texto` no limite de COLUNA do banco, sem levantar nada —
    achado A1: um namespace de XML ou um nome de entrada de ZIP de 600
    caracteres ecoava sem corte na mensagem de recusa e estourava
    `django.db.DataError` (`value too long for type character
    varying(500)`) ao gravar `ResultadoDoArquivo`, derrubando o ENVIO
    INTEIRO com 500 em vez de recusar só o arquivo. Corte é SEMPRE seguro
    aqui: `motivo`/`caminho_no_zip` são só para EXIBIÇÃO (RC-71, critério
    18) — nunca usados para classificar nem para deduplicar.
    """
    if len(texto) <= tamanho:
        return texto
    marcador = "… (truncado)"
    return texto[: tamanho - len(marcador)] + marcador


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
# CPF. Desde a DL-038, `Empresa` admite `tipo_inscricao=CPF` — o cadastro
# existe. Esta mensagem passou a valer só quando o CPF do participante
# GENUINAMENTE não está cadastrado como Empresa (tipo CPF) NESTE
# escritório: com cadastro, `_localizar_empresa_por_cpf` encontra a
# empresa e este código nem chega a ser alcançado (`_vincular_participantes`
# só levanta esta recusa quando `vinculos` está vazio). O texto continua
# sem depender de nada que exista ou não em OUTRO escritório (critério 27:
# a mensagem não pode revelar se o CPF pertence a alguém alhures) — é
# sempre "não está cadastrado NESTE escritório", com ou sem cadastro em
# outro.
MENSAGEM_PARTICIPANTE_PESSOA_FISICA_SEM_CADASTRO = (
    "Participante pessoa física (CPF): nenhuma empresa deste escritório está "
    "cadastrada com este CPF."
)


def _mapa_de_inscricoes_do_escritorio(escritorio):
    """Achado A4 da auditoria (DE-076 item 2): resolve, em DUAS consultas
    (uma vez por ENVIO, não por arquivo), todas as inscrições do
    escritório — CNPJ e CPF de `Empresa`, mais CNPJ de cada
    `Estabelecimento` — para um dicionário `{(tipo, inscrição
    canonizada): Empresa}`.

    Isto é só o DADO; a REGRA de identificação continua num ponto só,
    em `_localizar_empresa_por_cnpj`/`_localizar_empresa_por_cpf`
    (critério 13 do plano) — elas apenas passam a consultar este
    dicionário em vez do banco quando ele é fornecido. `receber_envio`
    monta o mapa UMA VEZ e passa adiante para cada arquivo do mesmo
    envio; nada aqui é reaproveitado ENTRE envios (o mapa vive só na
    pilha de uma chamada de `receber_envio`, nunca em cache global —
    uma empresa cadastrada no meio de um envio gigante não é vista pelos
    arquivos já processados, mas isso é aceitável: o próprio envio, e
    qualquer reenvio futuro, resolvem pela consulta fresca de novo).
    """
    mapa = {}
    for empresa in Empresa.objects.filter(escritorio=escritorio):
        if empresa.cnpj:
            mapa[("CNPJ", empresa.cnpj)] = empresa
        if empresa.cpf:
            mapa[("CPF", empresa.cpf)] = empresa
    estabelecimentos = Estabelecimento.objects.filter(
        empresa__escritorio=escritorio
    ).select_related("empresa")
    for estabelecimento in estabelecimentos:
        # `setdefault`: se um CNPJ de Estabelecimento coincidisse com o de
        # uma Empresa (não deveria, mas não é este ponto que garante isso),
        # a Empresa continua vencendo — mesma prioridade da consulta direta
        # em `_localizar_empresa_por_cnpj` (Empresa primeiro, Estabelecimento
        # como resultado supletivo).
        mapa.setdefault(("CNPJ", estabelecimento.cnpj), estabelecimento.empresa)
    return mapa


def localizar_empresa_do_escritorio(escritorio, participante, *, mapa=None):
    """Ponto ÚNICO de identificação de empresa a partir de uma inscrição,
    dentro de um escritório (critério 13 do plano; DE-074 item 7).

    `participante` é um `apps.fiscal.leitor.ParticipanteLido` (ou `None`) —
    carrega a inscrição JUNTO do seu tipo (CNPJ/CPF/NIF/nao_informado), e é
    o tipo que decide o ramo de busca abaixo. Nenhum outro ponto do código
    presume que participante é sempre CNPJ.

    `mapa` (opcional): dicionário de `_mapa_de_inscricoes_do_escritorio`
    (achado A4) — quando fornecido (caminho de `receber_envio`, montado
    UMA VEZ por envio), a busca é O(1) em memória. Achado N3 (reconferência
    DL-010/DL-038, BL-528): ANTES desta correção havia um SEGUNDO caminho,
    de consulta direta ao banco, para quando `mapa` não era fornecido — dois
    lugares repetindo o mesmo filtro de isolamento por escritório, um deles
    nunca exercitado por código de produção nenhum (nem testado contra
    vazamento entre escritórios). Agora existe um ÚNICO caminho: SEM `mapa`,
    esta função MONTA um (mesmo custo de consultas de sempre para um
    participante avulso — usado por quem processa fora do laço de um envio,
    ex.: teste unitário) e reaproveita o MESMO dicionário filtrado por
    escritório que `receber_envio` usa — nunca uma consulta paralela que
    pudesse divergir do filtro.
    """
    if participante is None:
        return None
    if mapa is None:
        mapa = _mapa_de_inscricoes_do_escritorio(escritorio)
    if participante.tipo_documento == "CNPJ":
        return _localizar_empresa_por_cnpj(participante.documento, mapa=mapa)
    if participante.tipo_documento == "CPF":
        # DL-038 (R8): CPF casa com `Empresa` de `tipo_inscricao=CPF` do
        # MESMO escritório — mesmo molde de `_localizar_empresa_por_cnpj`.
        return _localizar_empresa_por_cpf(participante.documento, mapa=mapa)
    # NIF (identificação fiscal estrangeira) e "nao_informado" (cNaoNIF)
    # nunca casam: não são inscrição de empresa brasileira cadastrável
    # neste sistema.
    return None


def _localizar_empresa_por_cnpj(cnpj_bruto, *, mapa):
    """Busca em `Empresa.cnpj` E em `Estabelecimento.cnpj` dentro de `mapa`
    — SEMPRE um dicionário já filtrado pelo escritório
    (`_mapa_de_inscricoes_do_escritorio`), nunca uma consulta paralela ao
    banco (achado N3: caminho único, ver `localizar_empresa_do_escritorio`).
    O CNPJ é único no sistema inteiro (PE-21): é exatamente por isso que o
    filtro por escritório, aplicado UMA vez na montagem do dicionário, é
    quem impede o vazamento que o critério 27 (isolamento) proíbe — nunca
    algo repetido (e potencialmente esquecido) em cada busca individual.
    """
    try:
        cnpj = normalizar_cnpj(cnpj_bruto)
    except ValidationError:
        return None
    return mapa.get(("CNPJ", cnpj))


def _localizar_empresa_por_cpf(cpf_bruto, *, mapa):
    """DL-038 (R8): busca em `Empresa.cpf` (tipo_inscricao=CPF) dentro de
    `mapa` — mesmo molde de `_localizar_empresa_por_cnpj` (achado N3):
    único caminho, dicionário sempre filtrado pelo escritório na origem.
    Diferente do CNPJ, não existe "Estabelecimento" para pessoa física —
    só a própria `Empresa`.
    """
    try:
        cpf = normalizar_cpf(cpf_bruto)
    except ValidationError:
        return None
    return mapa.get(("CPF", cpf))


def _tem_participante_pessoa_fisica(documento_lido: leitor.DocumentoLido) -> bool:
    if documento_lido.prestador is not None and documento_lido.prestador.tipo_documento == "CPF":
        return True
    return documento_lido.tomador is not None and documento_lido.tomador.tipo_documento == "CPF"


def _vincular_participantes(escritorio, documento_lido: leitor.DocumentoLido, *, mapa=None):
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

    `mapa`: ver `localizar_empresa_do_escritorio` (achado A4).
    """
    vinculos = []
    empresa_prestador = localizar_empresa_do_escritorio(
        escritorio, documento_lido.prestador, mapa=mapa
    )
    if empresa_prestador is not None:
        vinculos.append((empresa_prestador, PapelDocumento.PRESTADOR))
    empresa_tomador = localizar_empresa_do_escritorio(escritorio, documento_lido.tomador, mapa=mapa)
    if empresa_tomador is not None and empresa_tomador != empresa_prestador:
        vinculos.append((empresa_tomador, PapelDocumento.TOMADOR))
    if not vinculos:
        if _tem_participante_pessoa_fisica(documento_lido):
            raise leitor.ArquivoRecusado(MENSAGEM_PARTICIPANTE_PESSOA_FISICA_SEM_CADASTRO)
        raise leitor.ArquivoRecusado(MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO)
    return vinculos


def _adicionar_vinculos_que_faltam(documento, escritorio, lido: leitor.DocumentoLido, *, mapa=None):
    """Achado A5 da auditoria: um documento RECEBIDO antes, quando só um
    dos participantes era cliente cadastrado, ganha o vínculo que faltava
    quando o OUTRO participante é cadastrado depois e a mesma nota é
    reenviada (RC-69, "um documento com dois vínculos"; R8 da DL-038 —
    vale também para o cliente pessoa física recém-cadastrado).

    Chamado só no caminho de "duplicado" (o documento já existe). Reusa
    `_vincular_participantes` — a MESMA regra de identificação, nunca uma
    segunda cópia — e cria só os vínculos que ainda NÃO existem,
    respeitando a unicidade `(documento, empresa)` mesmo sob corrida
    (savepoint próprio por vínculo, IntegrityError vira "já existe,
    ignora" — idempotente).

    Devolve a primeira `Empresa` recém-vinculada (para a mensagem), ou
    `None` se nada mudou.
    """
    try:
        vinculos_alvo = _vincular_participantes(escritorio, lido, mapa=mapa)
    except leitor.ArquivoRecusado:
        # Documento já existia (teve pelo menos um vínculo antes), mas
        # NENHUM participante casa agora — caso degenerado (ex.: a
        # empresa vinculada foi excluída entre os dois envios). Nada a
        # acrescentar; o vínculo antigo, se ainda existir, permanece.
        return None
    ja_vinculadas = set(documento.vinculos.values_list("empresa_id", flat=True))
    vinculada_agora = None
    for empresa, papel in vinculos_alvo:
        if empresa.pk in ja_vinculadas:
            continue
        try:
            with transaction.atomic():
                VinculoDocumentoEmpresa.objects.create(
                    documento=documento, empresa=empresa, papel=papel
                )
        except IntegrityError:
            # Corrida: outro processo já criou este vínculo entre a
            # consulta de `ja_vinculadas` e este INSERT — idempotente.
            continue
        vinculada_agora = empresa
    return vinculada_agora


def _criar_documento_e_vinculos(
    escritorio, lido: leitor.DocumentoLido, *, mapa=None
) -> DocumentoFiscal:
    # A checagem de isolamento acontece ANTES de qualquer escrita: uma nota
    # sem participante do escritório nunca chega a tocar o banco.
    vinculos_alvo = _vincular_participantes(escritorio, lido, mapa=mapa)

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


def _criar_evento(escritorio, lido: leitor.EventoLido, *, mapa=None) -> EventoFiscal:
    # Evento ÓRFÃO (sem empresa identificável) é aceito e guardado — RC-70,
    # critério 17. Diferente do documento, o evento NUNCA é recusado por
    # falta de participante do escritório.
    empresa = None
    if lido.autor is not None:
        empresa = localizar_empresa_do_escritorio(escritorio, lido.autor, mapa=mapa)
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


def _motivo_de_duplicado(existente, sha256_novo: str, rotulo: str, *, vinculo_novo=None) -> str:
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

    `vinculo_novo` (achado A5): quando o reenvio acrescentou um vínculo
    que faltava (empresa cadastrada depois do primeiro recebimento), a
    mensagem registra QUAL empresa entrou — sem isso, o resultado
    "duplicado" pareceria idêntico ao reenvio comum, escondendo que algo
    de fato mudou no documento.
    """
    if existente is not None and existente.sha256_arquivo != sha256_novo:
        return (
            f"{rotulo} já recebido, mas o conteúdo deste arquivo é DIFERENTE "
            "do recebido antes — conferir."
        )
    base = f"{rotulo} já recebido anteriormente por este escritório."
    if vinculo_novo is not None:
        base += f" Vínculo novo criado com {vinculo_novo.razao_social}."
    return base


def _processar_um_arquivo(escritorio, conteudo: bytes, *, mapa=None) -> dict:
    """Processa UM arquivo já extraído (XML solto, ou uma entrada do ZIP).

    Nunca levanta exceção — devolve um dicionário pronto para
    `ResultadoDoArquivo.objects.create(**dicionario)` (menos `lote` e
    `caminho_no_zip`, que quem chama acrescenta). Cada arquivo grava em seu
    próprio `transaction.atomic()` (savepoint, DE-074 item 5/critério 28):
    um `IntegrityError` de unicidade dentro dele vira "duplicado"; qualquer
    outro problema vira "recusado" — nenhum dos dois propaga e derruba o
    envio inteiro (critério 7/8).

    `mapa`: ver `localizar_empresa_do_escritorio` (achado A4).
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
        # é o que isola o `IntegrityError`/`DataError` de um arquivo sem
        # poluir a transação do lote inteiro.
        with transaction.atomic():
            if eh_documento:
                documento = _criar_documento_e_vinculos(escritorio, lido, mapa=mapa)
            else:
                evento = _criar_evento(escritorio, lido, mapa=mapa)
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
            # Achado A5: o reenvio de uma nota já recebida acrescenta
            # qualquer vínculo que faltava (empresa cadastrada depois do
            # primeiro recebimento) — idempotente, dentro do seu próprio
            # savepoint (ver `_adicionar_vinculos_que_faltam`).
            vinculo_novo = None
            if existente is not None:
                vinculo_novo = _adicionar_vinculos_que_faltam(
                    existente, escritorio, lido, mapa=mapa
                )
            return {
                "resultado": TipoResultadoArquivo.DUPLICADO,
                "motivo": _motivo_de_duplicado(
                    existente, sha256, "Documento", vinculo_novo=vinculo_novo
                ),
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
    except DataError as exc:
        # Achado A1 (rodada 1) restrito pelo achado N1 (reconferência,
        # BL-526): ÚLTIMA linha de defesa DENTRO do savepoint deste
        # arquivo, mas SÓ para `DataError` — campo grande demais, tipo
        # incompatível, precisão numérica excedida etc., que são defeito
        # do CONTEÚDO do arquivo, não do sistema. Vira "recusado" deste
        # ARQUIVO, nunca um 500 que derruba o envio inteiro, e a mensagem
        # é NEUTRA (nunca `str(exc)`, que ecoaria nome de tabela/coluna do
        # banco) — o detalhe completo vai só para o log.
        #
        # `IntegrityError` de restrição conhecida já tem seu próprio
        # `except` acima (unicidade de documento/evento). Qualquer OUTRO
        # erro de banco — `ProgrammingError`, `InternalError`,
        # `InterfaceError`, `NotSupportedError`, `OperationalError` que não
        # seja de lock/deadlock — indica defeito de SISTEMA (esquema
        # desatualizado, migração não aplicada, conexão quebrada), não
        # arquivo ruim. Nenhum desses tipos é `DataError`, então nenhum
        # deles é pego por este `except` — todos sobem intactos, saem de
        # `_processar_um_arquivo`, saem de `_receber_envio_com_lock_
        # adquirido` e desfazem a transação INTEIRA de `receber_envio`
        # (`@transaction.atomic`): nem o `LoteDeRecepcao`, nem nenhum
        # `ResultadoDoArquivo`, nem a trilha de auditoria chegam a ser
        # gravados — um erro de sistema nunca deve parecer um envio
        # concluído com arquivos recusados.
        logger.warning(
            "Erro de dados ao gravar arquivo fiscal (escritório %s): %s",
            escritorio.pk,
            exc,
            exc_info=True,
        )
        return {
            "resultado": TipoResultadoArquivo.RECUSADO,
            "motivo": MENSAGEM_ERRO_DE_DADOS_NO_ARQUIVO,
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


# Achado A8 da auditoria (rodada 1): `zipfile.ZipFile()` materializa o
# diretório central INTEIRO em memória (`infolist()`) antes de qualquer
# checagem de limite — um ZIP de 49 MB com 601.184 entradas VAZIAS chegava
# a consumir ~340 MB de RSS por requisição só para ser recusado depois.
# As constantes e a função abaixo leem o TOTAL DE ENTRADAS diretamente do
# registro de fim de diretório central (EOCD) — e do EOCD64, quando o
# total não cabe em 16 bits —, sem construir `ZipFile` nem alocar nada
# proporcional ao número de entradas.
_TAMANHO_EOCD = 22
_TAMANHO_MAXIMO_COMENTARIO_ZIP = 65535
_ASSINATURA_EOCD = b"PK\x05\x06"
_ASSINATURA_EOCD64_LOCATOR = b"PK\x06\x07"
_ASSINATURA_EOCD64 = b"PK\x06\x06"
_TAMANHO_EOCD64_LOCATOR = 20
_TAMANHO_MINIMO_EOCD64 = 56


def _contagem_de_entradas_do_zip(conteudo: bytes) -> int | None:
    """Lê o total de entradas do ZIP a partir do EOCD (e do EOCD64, se
    necessário), SEM construir `zipfile.ZipFile`. Devolve `None` quando
    não consegue localizar o registro com confiança — quem chama trata
    isso como "não sei", NUNCA como "zero": o caminho normal (mais caro,
    mas correto) continua protegido pela checagem de `len(infolist())`
    depois. Nunca um FALSO NEGATIVO aqui vira um ZIP hostil aceito.
    """
    tamanho_busca = min(len(conteudo), _TAMANHO_EOCD + _TAMANHO_MAXIMO_COMENTARIO_ZIP)
    janela = conteudo[-tamanho_busca:]
    posicao = janela.rfind(_ASSINATURA_EOCD)
    if posicao == -1 or len(janela) - posicao < _TAMANHO_EOCD:
        return None
    eocd = janela[posicao : posicao + _TAMANHO_EOCD]
    comprimento_comentario = int.from_bytes(eocd[20:22], "little")
    # Confirma que este é o EOCD de VERDADE, não uma coincidência de bytes
    # dentro de um comentário anterior: o comprimento do comentário
    # declarado tem que fechar EXATAMENTE com o fim do buffer.
    if posicao + _TAMANHO_EOCD + comprimento_comentario != len(janela):
        return None

    total = int.from_bytes(eocd[10:12], "little")
    if total != 0xFFFF:
        return total

    # ZIP64: o total de 16 bits declarado é o valor-sentinela 0xFFFF — o
    # número real está no EOCD64, localizado pelo "locator" que antecede
    # o EOCD em exatamente 20 bytes (posição ABSOLUTA no conteúdo, não na
    # janela recortada acima).
    offset_absoluto_eocd = len(conteudo) - len(janela) + posicao
    offset_locator = offset_absoluto_eocd - _TAMANHO_EOCD64_LOCATOR
    if offset_locator < 0:
        return None
    locator = conteudo[offset_locator : offset_locator + _TAMANHO_EOCD64_LOCATOR]
    if len(locator) != _TAMANHO_EOCD64_LOCATOR or locator[:4] != _ASSINATURA_EOCD64_LOCATOR:
        return None
    offset_eocd64 = int.from_bytes(locator[8:16], "little")
    if offset_eocd64 < 0 or offset_eocd64 + _TAMANHO_MINIMO_EOCD64 > len(conteudo):
        return None
    eocd64 = conteudo[offset_eocd64 : offset_eocd64 + _TAMANHO_MINIMO_EOCD64]
    if eocd64[:4] != _ASSINATURA_EOCD64:
        return None
    # Total de entradas no EOCD64: offset 32, 8 bytes (little-endian) —
    # ver o layout do registro na especificação APPNOTE.TXT §4.3.14.
    return int.from_bytes(eocd64[32:40], "little")


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
    # Achado A8: recusa CEDO, pelo EOCD, sem pagar o custo de
    # `infolist()` quando já dá para saber que o envio é hostil.
    contagem_estimada = _contagem_de_entradas_do_zip(conteudo)
    if contagem_estimada is not None and contagem_estimada > LIMITE_ARQUIVOS_NO_ENVIO:
        raise EnvioInvalido(
            f"O envio tem {contagem_estimada} arquivos, acima do limite de "
            f"{LIMITE_ARQUIVOS_NO_ENVIO} (HI-22)."
        )

    try:
        arquivo_zip = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as exc:
        raise EnvioInvalido(f"ZIP corrompido: {exc}") from exc

    infos = arquivo_zip.infolist()
    if len(infos) > LIMITE_ARQUIVOS_NO_ENVIO:
        # Checagem AUTORITATIVA (não confia só na estimativa do EOCD acima
        # — ela é uma otimização, esta é a garantia): um EOCD ambíguo ou
        # deliberadamente incoerente com o diretório central real ainda
        # cai aqui.
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
        try:
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
        except (zipfile.BadZipFile, zlib.error, NotImplementedError, EOFError, OSError) as exc:
            # Achado A2 da auditoria: só o CONSTRUTOR de `ZipFile` estava
            # protegido — abrir/ler uma entrada com deflate corrompido
            # (`zlib.error`), CRC-32 incompatível (`zipfile.BadZipFile`) ou
            # método de compressão não suportado (`NotImplementedError`,
            # ex.: deflate64) derrubava o ENVIO INTEIRO com 500. Um ZIP com
            # UMA entrada corrompida é ZIP INTEIRO hostil (não dá para
            # confiar no restante do diretório central) — vira
            # `EnvioInvalido`, nada é gravado, com mensagem legível.
            raise EnvioInvalido(
                f"ZIP corrompido (entrada {info.filename!r} não pôde ser lida): {exc}"
            ) from exc
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
    `LIMITE_ARQUIVOS_NO_ENVIO` entradas, com mais de
    `LIMITE_DESCOMPACTADO_BYTES` de conteúdo descompactado (HI-22), ou
    quando já há outro envio do MESMO escritório em processamento (DE-076
    item 1, achado A3) — nesses casos nada é gravado, nem o
    `LoteDeRecepcao`.

    Todo o processamento — o lote, cada arquivo (em seu próprio savepoint)
    e o registro de auditoria — roda em UMA transação (`@transaction.
    atomic`, DE-074 item 5, critério 31): ou o envio inteiro é gravado, ou
    nada é.

    DE-076 item 1: o PRIMEIRO passo, ainda antes de ler o corpo do envio, é
    tentar o bloqueio consultivo do escritório — sem esperar (`pg_try_
    advisory_xact_lock`). Se outro envio do mesmo escritório já o segura,
    recusa IMEDIATAMENTE, sem gastar tempo lendo ou processando nada. Isso
    elimina, na origem, a espera de lock e o impasse (deadlock) que a
    auditoria mediu entre dois envios concorrentes do MESMO escritório
    disputando o mesmo índice único de documento — a unicidade é POR
    ESCRITÓRIO (DE-074), então só envios do mesmo escritório disputam o
    mesmo índice.
    """
    if not _adquirir_lock_de_envio_do_escritorio(escritorio):
        raise EnvioInvalido(MENSAGEM_ENVIO_EM_ANDAMENTO)

    try:
        return _receber_envio_com_lock_adquirido(
            escritorio=escritorio, usuario=usuario, arquivo=arquivo, nome_arquivo=nome_arquivo
        )
    except OperationalError as exc:
        # Defesa em profundidade (DE-076 item 1): o bloqueio acima já
        # deveria eliminar espera e impasse ENTRE envios do mesmo
        # escritório — mas qualquer `OperationalError` de lock/deadlock
        # que ainda assim escape (concorrência com alguma outra operação
        # do banco, fora deste mecanismo) vira mensagem legível, nunca
        # 500. Qualquer OUTRO `OperationalError` — que não seja de
        # lock/deadlock — sobe intacto: não é este código que decide que
        # todo erro de banco é "conflito de envio".
        if _e_erro_de_lock_ou_deadlock(exc):
            raise EnvioInvalido(
                "Não foi possível concluir o envio agora (conflito de banco de dados); "
                "tente novamente em instantes."
            ) from exc
        raise


def _receber_envio_com_lock_adquirido(
    *, escritorio, usuario, arquivo, nome_arquivo
) -> LoteDeRecepcao:
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

    # Achado A4: resolvido UMA VEZ por envio, não uma vez por arquivo — ver
    # `_mapa_de_inscricoes_do_escritorio`.
    mapa = _mapa_de_inscricoes_do_escritorio(escritorio)

    contagens = {
        TipoResultadoArquivo.RECEBIDO: 0,
        TipoResultadoArquivo.DUPLICADO: 0,
        TipoResultadoArquivo.RECUSADO: 0,
    }
    for caminho_no_zip, conteudo_arquivo in itens:
        info = _processar_um_arquivo(escritorio, conteudo_arquivo, mapa=mapa)
        resultado = info.pop("resultado")
        ResultadoDoArquivo.objects.create(
            lote=lote,
            caminho_no_zip=_truncar(caminho_no_zip, _TAMANHO_MAXIMO_CAMINHO_NO_ZIP),
            resultado=resultado,
            motivo=_truncar(info.pop("motivo", ""), _TAMANHO_MAXIMO_MOTIVO),
            **info,
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
