"""DL-018 — primeiro acesso via produto.

Três operações que o caminho de bootstrap de uma instalação precisa:

- `criar_primeiro_escritorio_e_vinculo_admin`: usuário autenticado, sem
  vínculo ativo com nenhum escritório, cria o **primeiro** escritório
  e torna-se seu administrador (HI-1 e HI-2 da DL-018). Tudo numa
  transação atômica — se o vínculo não for criado, o escritório também
  não fica órfão.
- `emitir_convite_para_escritorio`: administrador (papel=ADMINISTRADOR
  do escritório) cadastra um e-mail e cria um `ConviteEscritorio` com
  token aceito por rota dedicada.
- `aceitar_convite_e_criar_vinculo`: portador de token válido (com
  sessão autenticada) aceita o convite e ganha o papel que o convite
  carrega (`ANALISTA` por padrão — papel de entrada para o segundo
  funcionário; o administrador promove se for caso). Só aceita convite
  **dentro do prazo de 7 dias** e **apresentado por usuário cujo e-mail
  é o do convidado** (DL-052, A2): sem essas duas condições o token
  vazado por qualquer canal valeria, para sempre, como chave de entrada
  no escritório.

Por que estas três operações estão aqui, e não em `views.py`: a regra
de negócio (limite de um escritório por usuário sem vínculo, vínculo
sempre ADMINISTRADOR no primeiro escritório, convite só por
ADMINISTRADOR) não cabe em view — cabe em serviço. As views são
superfícies; este arquivo é a regra.
"""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.tenancy.models import (
    ConviteEscritorio,
    Escritorio,
    Papel,
    VinculoUsuarioEscritorio,
)


class PrimeiroEscritorioJaExiste(Exception):
    """O usuário autenticado já tem vínculo ativo com pelo menos um
    escritório. O bootstrap é exclusivo de instalação nova — uma
    instalação com escritório não entra por aqui."""


class ConvidanteNaoEhAdministrador(Exception):
    """Quem tenta convidar não é ADMINISTRADOR ativo do escritório
    alvo. Defesa contra escalada: o convite é o ponto de entrada de
    sigilo, e o ADMINISTRADOR é o único papel com poder de definir
    quem entra."""


class ConviteInvalido(Exception):
    """Token inexistente, já consumido, expirado (mais de 7 dias) ou
    apresentado por usuário cujo e-mail não é o do convidado. A
    mensagem nunca revela a qual e-mail o convite pertence. A view traduz
    para mensagem ao usuário e redirecionamento ao painel.

    DL-059 (BL-566): quando a recusa vem de um convite que EXISTE, a exceção
    carrega `motivo` (um dos `MOTIVO_*`) e `convite`, para o serviço gravar o
    evento de recusa na trilha sem interpretar o texto da mensagem. Token
    inexistente ou já consumido não tem convite a apontar: `motivo` e
    `convite` ficam `None` e nada é gravado (o token nunca vai para a
    trilha)."""

    def __init__(self, mensagem, *, motivo=None, convite=None):
        super().__init__(mensagem)
        self.motivo = motivo
        self.convite = convite


class ConviteTokenColidiu(Exception):
    """`get_random_string` retornou um token que já existe. Probabilidade
    ~1 em 2^190, mas o `save()` do modelo tem um loop defensivo que
    gera um novo candidato e re-tenta; este erro só seria levantado se
    o loop esgotasse, o que é praticamente impossível. View traduz para
    503 (retry com novo token é o caminho correto)."""


@dataclass
class ResultadoBootstrap:
    escritorio: Escritorio
    vinculo: VinculoUsuarioEscritorio


@transaction.atomic
def criar_primeiro_escritorio_e_vinculo_admin(
    *,
    usuario,
    nome: str,
    cnpj: str,
    request=None,
) -> ResultadoBootstrap:
    """Operação atômica: cria o primeiro escritório e vincula o usuário
    como ADMINISTRADOR. Falha se o usuário já tem escritório.

    Quem valida a ENTRADA EXTERNA (CNPJ e nome) é o formulário da view,
    `PrimeiroEscritorioForm` em apps/tenancy/forms.py (DL-070, BL-645 e
    BL-646): tamanho, normalização e dígitos verificadores. Este serviço
    confia no chamador e não revalida CNPJ nem tamanho do nome. Quem o
    chamar de outro caminho (shell, fixture, importador da DL-010) precisa
    passar pela mesma validação antes.

    A regra "um escritório por usuário sem vínculo ativo" é deste serviço,
    e aqui ela tem defesa própria, porque se morresse na view qualquer outro
    caminho a reproduziria. O modelo `VinculoUsuarioEscritorio` tem
    `UniqueConstraint(fields=["usuario", "escritorio"], ...)`, mas isso cobre
    duplicar (mesmo escritório, mesmo usuário), não o estado "usuário com
    QUALQUER escritório ativo".

    Mensagens de erro são `Exception` específica (não `ValidationError`)
    porque o serviço não toca em `full_clean()` — a view é que decide
    se traduz para 400 ou 409. Manter as duas camadas (serviço +
    modelo) é o que a DE-008 pede: a regra fica no serviço, a
    integridade estrutural fica no banco."""
    if VinculoUsuarioEscritorio.objects.filter(usuario=usuario, ativo=True).exists():
        raise PrimeiroEscritorioJaExiste(
            f"O usuário {usuario} já tem pelo menos um escritório ativo."
        )

    escritorio = Escritorio.objects.create(nome=nome, cnpj=cnpj)
    vinculo = VinculoUsuarioEscritorio.objects.create(
        usuario=usuario,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )

    registrar(
        acao="escritorio.criado_por_bootstrap",
        usuario=usuario,
        escritorio=escritorio,
        detalhes={
            "via": "primeiro_acesso",
            "papel_atribuido": Papel.ADMINISTRADOR,
        },
        # DL-059 (BL-579): `request` opcional só para a trilha gravar a origem (IP);
        # chamadas sem request (shell, importador) seguem funcionando, sem IP.
        request=request,
    )
    return ResultadoBootstrap(escritorio=escritorio, vinculo=vinculo)


@transaction.atomic
def emitir_convite_para_escritorio(
    *,
    escritorio: Escritorio,
    email_convidado: str,
    convidador,
    papel_inicial: str = Papel.ANALISTA,
    request=None,
) -> ConviteEscritorio:
    """Convite escrito pelo ADMINISTRADOR do escritório para o e-mail do
    segundo funcionário. Token opaco (32 chars base64-url), com prazo de 7
    dias.

    O convite NÃO vincula o usuário — apenas o torna elegível. O
    vínculo é criado em `aceitar_convite_e_criar_vinculo`, com o
    usuário autenticado apresentando o token. Esta separação é a
    defesa contra o cenário "convidado mal intencionado cria conta
    com e-mail de terceiro"."""
    if not VinculoUsuarioEscritorio.objects.filter(
        usuario=convidador, escritorio=escritorio, papel=Papel.ADMINISTRADOR, ativo=True
    ).exists():
        raise ConvidanteNaoEhAdministrador(
            "Convite só pode ser emitido por ADMINISTRADOR ativo do escritório."
        )

    from django.db import IntegrityError

    try:
        convite = ConviteEscritorio.objects.create(
            escritorio=escritorio,
            email=email_convidado,
            papel_inicial=papel_inicial,
            emitido_por=convidador,
        )
    except IntegrityError as exc:
        # Defesa em camada 2 (modelo.save já tentou colidir internamente
        # e o loop defensivo esgotou): converte para exceção de domínio
        # em vez de propagar 500. View traduz para 503 — retry com novo
        # token é o caminho correto.
        raise ConviteTokenColidiu("Colisão de token de convite — raro, tente novamente.") from exc

    registrar(
        acao="convite.escritorio.emitido",
        usuario=convidador,
        escritorio=escritorio,
        detalhes={"convite_id": convite.id, "email_convidado": email_convidado},
        request=request,  # DL-059 (BL-579): origem (IP) na trilha
    )
    return convite


@dataclass
class ResultadoAceitacao:
    vinculo: VinculoUsuarioEscritorio
    convite: ConviteEscritorio


def normalizar_email(email: str | None) -> str:
    """Forma de comparação de e-mail do convite: sem espaços nas pontas e
    sem diferença de maiúsculas (`casefold`). Só para COMPARAR — o valor
    gravado no convite e no usuário não é alterado."""
    return (email or "").strip().casefold()


def convite_e_do_usuario(convite: ConviteEscritorio, usuario) -> bool:
    """O e-mail do usuário autenticado é o e-mail para o qual o convite
    foi emitido? Usuário sem e-mail nunca confere (nem com convite de
    e-mail vazio): convite sem destinatário identificável não é
    aceitável por ninguém."""
    email_do_usuario = normalizar_email(getattr(usuario, "email", ""))
    return bool(email_do_usuario) and email_do_usuario == normalizar_email(convite.email)


# DL-059 (BL-566): valores de `detalhes["motivo"]` do evento
# `convite.escritorio.recusado`.
MOTIVO_VENCIDO = "vencido"
MOTIVO_EMAIL_DIVERGENTE = "email_divergente"
MOTIVO_JA_VINCULADO = "ja_vinculado"

MENSAGEM_CONVITE_EXPIRADO = (
    "Este convite venceu (vale 7 dias a partir da emissão). "
    "Peça ao administrador do escritório para emitir outro."
)
MENSAGEM_JA_VINCULADO = (
    "Sua conta já tem vínculo com este escritório; este convite não é necessário. "
    "Use o painel para acessá-lo."
)
MENSAGEM_CONVITE_DE_OUTRO_EMAIL = (
    "Este convite não foi emitido para o e-mail da sua conta. "
    "Entre com a conta do e-mail convidado ou peça ao administrador um novo convite."
)


def aceitar_convite_e_criar_vinculo(*, token: str, usuario, request=None) -> ResultadoAceitacao:
    """Usuário autenticado apresenta token de convite e ganha o vínculo
    com o papel que o convite carrega.

    Recusa com `ConviteInvalido` — sem criar vínculo e sem consumir o
    convite — quando: o token não existe ou já foi consumido; o convite
    tem mais de 7 dias (`ConviteEscritorio.expirado`: vence só quando
    `agora > criado_em + 7 dias`, então exatamente 7 dias ainda vale); ou
    o e-mail do usuário difere do e-mail do convidado (sem diferença de
    maiúsculas nem de espaços nas pontas); ou o usuário já tem vínculo com o
    escritório do convite. As recusas por prazo e por
    e-mail usam mensagens próprias, e a de e-mail não diz a qual e-mail
    o convite pertence (DL-052, A2).

    DL-059 (BL-566): cada recusa de um convite existente deixa o evento
    `convite.escritorio.recusado` (`convite_id` e `motivo`, nunca o e-mail)
    — token apresentado por quem não deveria ou fora do prazo é sinal útil
    de incidente. `request` é opcional e só informa a origem (IP) à trilha.

    Por que a gravação fica AQUI, fora da transação: a recusa é uma exceção
    levantada de dentro de `_aceitar_em_transacao` (`@transaction.atomic`),
    e uma exceção desfaz a transação inteira, levando junto qualquer
    `registrar` feito antes do `raise`. Então a transação interna só
    decide e levanta; este envoltório captura `ConviteInvalido` já DEPOIS
    do rollback e grava o evento numa operação própria. Nenhum vínculo
    nem consumo existe nesse ponto (a recusa vem antes de qualquer escrita),
    de modo que o evento de recusa nunca coexiste com o de aceite."""
    try:
        return _aceitar_em_transacao(token=token, usuario=usuario, request=request)
    except ConviteInvalido as recusa:
        if recusa.motivo is not None:
            registrar(
                acao="convite.escritorio.recusado",
                usuario=usuario,
                escritorio=recusa.convite.escritorio,
                detalhes={"convite_id": recusa.convite.id, "motivo": recusa.motivo},
                request=request,
            )
        raise


@transaction.atomic
def _aceitar_em_transacao(*, token: str, usuario, request=None) -> ResultadoAceitacao:
    """Decide e executa o aceite numa transação; ver
    `aceitar_convite_e_criar_vinculo` para o contrato e para o motivo de a
    trilha de recusa ficar fora daqui."""
    convite = (
        ConviteEscritorio.objects.select_for_update()
        .filter(token=token, consumido_em__isnull=True)
        .first()
    )
    if convite is None:
        raise ConviteInvalido("Convite inexistente, expirado ou já consumido.")
    if convite.expirado:
        raise ConviteInvalido(MENSAGEM_CONVITE_EXPIRADO, motivo=MOTIVO_VENCIDO, convite=convite)
    if not convite_e_do_usuario(convite, usuario):
        raise ConviteInvalido(
            MENSAGEM_CONVITE_DE_OUTRO_EMAIL, motivo=MOTIVO_EMAIL_DIVERGENTE, convite=convite
        )
    # DL-052 rodada 1 (D5): quem já tem vínculo (ativo ou não) com o escritório
    # violaria `unico_vinculo_usuario_escritorio` — antes isso virava
    # `IntegrityError` (500). Recusa de negócio, convite NÃO consumido.
    if VinculoUsuarioEscritorio.objects.filter(
        usuario=usuario, escritorio=convite.escritorio
    ).exists():
        raise ConviteInvalido(MENSAGEM_JA_VINCULADO, motivo=MOTIVO_JA_VINCULADO, convite=convite)

    vinculo = VinculoUsuarioEscritorio.objects.create(
        usuario=usuario,
        escritorio=convite.escritorio,
        papel=convite.papel_inicial,
        ativo=True,
    )
    convite.consumido_por = usuario
    convite.consumido_em = timezone.now()
    convite.save(update_fields=["consumido_por", "consumido_em"])

    registrar(
        acao="convite.escritorio.aceito",
        usuario=usuario,
        escritorio=convite.escritorio,
        detalhes={"convite_id": convite.id, "papel_atribuido": convite.papel_inicial},
        request=request,  # DL-059 (BL-579): origem (IP) na trilha
    )
    return ResultadoAceitacao(vinculo=vinculo, convite=convite)
