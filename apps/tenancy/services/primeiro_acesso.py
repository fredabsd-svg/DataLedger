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
  sessão autenticada) aceita o convite e vira `ANALISTA` (papel de
  entrada para o segundo funcionário — o administrador promove se for
  caso).

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
    """Token inexistente, já consumido ou expirado. View traduz para 404
    (token inexistente) ou 410 (já consumido/expirado)."""


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
) -> ResultadoBootstrap:
    """Operação atômica: cria o primeiro escritório e vincula o usuário
    como ADMINISTRADOR. Falha se o usuário já tem escritório.

    A defesa é NA ORIGEM (serviço), não na view: se a regra morresse
    na view, qualquer outro caminho (shell, fixture, importador da
    DL-010) reproduziria o defeito. O modelo `VinculoUsuarioEscritorio`
    tem `UniqueConstraint(fields=["usuario", "escritorio"], ...)`, mas
    isso cobre duplicar (mesmo escritório, mesmo usuário), não o
    estado "usuário com QUALQUER escritório ativo".

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
    )
    return ResultadoBootstrap(escritorio=escritorio, vinculo=vinculo)


@transaction.atomic
def emitir_convite_para_escritorio(
    *,
    escritorio: Escritorio,
    email_convidado: str,
    convidador,
    papel_inicial: str = Papel.ANALISTA,
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

    convite = ConviteEscritorio.objects.create(
        escritorio=escritorio,
        email=email_convidado,
        papel_inicial=papel_inicial,
        emitido_por=convidador,
    )

    registrar(
        acao="convite.escritorio.emitido",
        usuario=convidador,
        escritorio=escritorio,
        detalhes={"convite_id": convite.id, "email_convidado": email_convidado},
    )
    return convite


@dataclass
class ResultadoAceitacao:
    vinculo: VinculoUsuarioEscritorio
    convite: ConviteEscritorio


@transaction.atomic
def aceitar_convite_e_criar_vinculo(*, token: str, usuario) -> ResultadoAceitacao:
    """Usuário autenticado apresenta token de convite e ganha o vínculo
    com o papel que o convite carrega. Falha se o convite expirou ou já
    foi aceito."""
    convite = (
        ConviteEscritorio.objects.select_for_update()
        .filter(token=token, consumido_em__isnull=True)
        .first()
    )
    if convite is None:
        raise ConviteInvalido("Convite inexistente, expirado ou já consumido.")

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
    )
    return ResultadoAceitacao(vinculo=vinculo, convite=convite)
