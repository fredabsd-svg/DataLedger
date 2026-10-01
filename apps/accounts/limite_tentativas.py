"""Limite de tentativas de login e de cadastro de escritório (DL-056).

Contrato, em uma frase: **a tentativa é RESERVADA no banco, sob trava, ANTES de
a senha ser verificada** — e só o sucesso devolve a reserva.

Por que reservar antes, e não contar a falha depois? Com "verifica, autentica,
registra a falha", duas requisições simultâneas leem 4 falhas, as duas passam
no limite de 5 e as duas autenticam: o limite vira sugestão sob concorrência,
justamente o cenário de quem faz força bruta em paralelo. Reservando dentro de
uma transação curta, serializada por trava consultiva do PostgreSQL por chave,
o limite vale exatamente, sem depender de a senha ser verificada antes.

Decisões que valem ser lidas antes de mexer:

- **Tentativa bloqueada NÃO é gravada.** Se fosse, cada tentativa do atacante
  renovaria o bloqueio e a vítima nunca mais entraria. O bloqueio expira
  `janela` segundos depois da falha que o causou, aconteça o que acontecer.
- **Sucesso zera o contador do usuário** (e devolve a reserva do IP daquela
  tentativa). Por isso o limite por IP conta FALHAS, e um escritório inteiro
  atrás do mesmo NAT, entrando com sucesso, não se bloqueia.
- **A mensagem de recusa é a do login inválido** (ver `LoginForm`). O bloqueio
  depende só do texto digitado e do IP — nunca de o usuário existir — então a
  resposta não distingue usuário existente de inexistente, nem "senha errada"
  de "bloqueado". O custo é real e está declarado: quem está bloqueado não é
  informado (senha certa também é recusada até a janela passar).
- **Sem IP conhecido, NÃO há limite por IP** (só o por usuário). O IP vem de
  `apps.auditoria.ip.ip_do_cliente` — a MESMA função da trilha — que devolve
  `None` quando `REMOTE_ADDR` falta ou é inválido. Agrupar todos os `None` numa
  chave única ("desconhecido") faria 20 falhas de qualquer pessoa bloquearem o
  login de TODOS (achado O2 da auditoria da DL-057). O limite por usuário
  continua valendo, então a força bruta contra uma conta segue contida.
  Atrás de proxy, sem `PROXIES_CONFIAVEIS` configurada, o IP é o do proxy e o
  limite por IP vira global: a implantação deve exigir a variável.
- **Bloqueio de conta por terceiros é possível**: quem digitar 5 vezes o
  usuário de alguém o bloqueia por até a janela. É o preço de qualquer limite
  por conta; o limite por IP e a janela curta o contêm, e a escolha de N e J
  é hipótese a validar com o Fred (ver `config/settings.py`).
"""

from __future__ import annotations

import hashlib
import hmac
import unicodedata
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import TentativaDeAcesso
from apps.auditoria.ip import ip_do_cliente

Escopo = TentativaDeAcesso.Escopo

# Teto de linhas apagadas por chamada: a limpeza é oportunista e acompanha uma
# requisição de usuário, então nunca pode virar uma varredura longa.
LOTE_DE_LIMPEZA = 500


def _agora():
    """Relógio do módulo. Os testes o substituem para avançar o tempo."""
    return timezone.now()


def normalizar_usuario(texto: str) -> str:
    """Forma canônica do usuário digitado, para que variações caiam no mesmo balde.

    NFKC (a mesma normalização que o Django aplica ao campo de usuário), sem
    espaços nas pontas e sem distinção de caixa: "ANA@x" e "ana@x" não podem
    ser dois baldes, ou trocar a caixa reiniciaria a contagem.
    """
    return unicodedata.normalize("NFKC", texto).strip().casefold()


def chave_do_usuario(texto: str) -> str:
    """HMAC do usuário normalizado; nunca o texto digitado (ver `TentativaDeAcesso`).

    Com chave secreta, para que quem lê a tabela não teste candidatos a usuário
    por força bruta offline. Trocar `SECRET_KEY` só zera os contadores.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
        b"dl056:usuario:" + normalizar_usuario(texto).encode(),
        hashlib.sha256,
    ).hexdigest()


def resumo_do_usuario(texto: str) -> str:
    """Prefixo (16 hex) de `chave_do_usuario`, o que a trilha de auditoria grava.

    Função ÚNICA do "resumo do usuário digitado" (DL-058/B3 + DL-056): o limitador
    e a trilha de falha de login (`apps.accounts.signals`) usam o mesmo valor,
    com a mesma normalização e a mesma chave (`SECRET_KEY`), então o evento
    `login.falha`, o `login.bloqueado` e a linha de `TentativaDeAcesso` se
    correlacionam. O texto nunca vai para a trilha porque pode ser uma senha
    digitada no campo errado; 16 hex bastam para reconhecer a mesma tentativa
    repetida sem permitir confirmar candidatos offline (HMAC com segredo).
    """
    return chave_do_usuario(texto)[:16]


@dataclass(frozen=True)
class Reserva:
    """Tentativas reservadas por uma requisição; `devolver` desfaz o IP dela."""

    ids_ip: tuple[int, ...]
    chave_usuario: str | None


def _travar(rotulos: list[str]) -> None:
    """Serializa reservas concorrentes sobre as mesmas chaves (até o fim da transação).

    Sem isso o "contar e inserir" corre: duas transações contam 4 e inserem a
    5ª e a 6ª. A trava é por chave, não global, e tomada em ordem alfabética
    para que duas requisições com as mesmas duas chaves nunca se travem em
    cruz (deadlock). Só PostgreSQL: SQLite serializa a escrita inteira e só é
    aceito em desenvolvimento (config/settings.py, DE-014).
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        for rotulo in sorted(set(rotulos)):
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [rotulo])


def _reservar(itens: list[tuple[str, str, int, int]]) -> tuple[list[int], str]:
    """Reserva uma tentativa em cada item ou em nenhum.

    `itens`: (escopo, chave, limite, janela_em_segundos). Devolve
    `(ids_criados, "")`, ou `([], escopo_no_limite)` se QUALQUER item já
    estiver no limite — nesse caso nada é gravado (ver "Tentativa bloqueada NÃO
    é gravada" no docstring do módulo).
    """
    agora = _agora()
    with transaction.atomic():
        _travar([f"dl056:{escopo}:{chave}" for escopo, chave, _, _ in itens])
        for escopo, chave, limite, janela in itens:
            usadas = TentativaDeAcesso.objects.filter(
                escopo=escopo,
                chave=chave,
                registrado_em__gt=agora - timedelta(seconds=janela),
            ).count()
            if usadas >= limite:
                return [], escopo
        criadas = TentativaDeAcesso.objects.bulk_create(
            [TentativaDeAcesso(escopo=e, chave=c, registrado_em=agora) for e, c, _, _ in itens]
        )
    return [t.pk for t in criadas], ""


def limpar_vencidas() -> int:
    """Apaga até `LOTE_DE_LIMPEZA` tentativas que nenhuma janela mais enxerga.

    Oportunista: roda a cada reserva, sem tarefa em segundo plano. Usa o índice
    de `registrado_em`; o teto por chamada impede uma varredura longa dentro de
    uma requisição. Uma cauda maior que o lote é drenada nas chamadas seguintes.
    """
    retencao = timedelta(
        seconds=max(
            settings.LIMITE_TENTATIVAS_LOGIN_JANELA_SEGUNDOS,
            settings.LIMITE_TENTATIVAS_CADASTRO_JANELA_SEGUNDOS,
        )
    )
    ids = list(
        TentativaDeAcesso.objects.filter(registrado_em__lt=_agora() - retencao).values_list(
            "pk", flat=True
        )[:LOTE_DE_LIMPEZA]
    )
    if not ids:
        return 0
    apagadas, _ = TentativaDeAcesso.objects.filter(pk__in=ids).delete()
    return apagadas


def reservar_tentativa_de_login(request, usuario_digitado: str) -> tuple[Reserva | None, str]:
    """Reserva uma tentativa de login por usuário e por IP.

    Devolve `(reserva, motivo)`. Bloqueada: `(None, "usuario" | "ip")`, sem
    gravar nada. `motivo` serve só à trilha — nunca é mostrado a quem tentou.
    """
    janela = settings.LIMITE_TENTATIVAS_LOGIN_JANELA_SEGUNDOS
    chave_usuario = chave_do_usuario(usuario_digitado)
    ip = ip_do_cliente(request)
    por_usuario = (
        Escopo.LOGIN_USUARIO,
        chave_usuario,
        settings.LIMITE_TENTATIVAS_LOGIN_POR_USUARIO,
        janela,
    )
    itens = [por_usuario]
    # `ip is None` (O2): sem IP conhecido não se aplica o limite por IP — ver o
    # docstring do módulo. Nunca usar um texto fixo como chave para o `None`.
    if ip is not None:
        itens.append((Escopo.LOGIN_IP, ip, settings.LIMITE_TENTATIVAS_LOGIN_POR_IP, janela))
    ids, bloqueado_em = _reservar(itens)
    limpar_vencidas()
    if not ids:
        return None, "usuario" if bloqueado_em == Escopo.LOGIN_USUARIO else "ip"
    # ids[0] é a linha do usuário; ids[1:] é a do IP, que não existe sem IP.
    return Reserva(ids_ip=tuple(ids[1:]), chave_usuario=chave_usuario), ""


def confirmar_sucesso_de_login(reserva: Reserva) -> None:
    """Login bem-sucedido: zera o usuário e devolve a reserva do IP desta tentativa."""
    with transaction.atomic():
        if reserva.chave_usuario is not None:
            TentativaDeAcesso.objects.filter(
                escopo=Escopo.LOGIN_USUARIO, chave=reserva.chave_usuario
            ).delete()
        TentativaDeAcesso.objects.filter(pk__in=reserva.ids_ip).delete()


def reservar_cadastro(request) -> bool:
    """Reserva um cadastro de escritório para o IP; `False` se já no limite.

    Chamada SÓ depois de o formulário ser válido, imediatamente antes de criar:
    conta o que cria usuário e escritório (cadastro em massa), não a digitação
    errada de CNPJ. Não cobre a enumeração de e-mail/CNPJ pelas mensagens de
    validação do formulário — fora do escopo da DL-056.
    """
    ip = ip_do_cliente(request)
    if ip is None:
        # O2: o cadastro só tem limite por IP; sem IP conhecido não há o que
        # limitar, e agrupar os `None` numa chave única bloquearia o cadastro de
        # todos. Recusar por falta de IP seria pior (derruba o cadastro legítimo
        # por defeito de infraestrutura) — a falta de IP fica visível na trilha
        # (`endereco_ip` nulo), que usa a mesma função.
        return True
    ids, _ = _reservar(
        [
            (
                Escopo.CADASTRO_IP,
                ip,
                settings.LIMITE_TENTATIVAS_CADASTRO_POR_IP,
                settings.LIMITE_TENTATIVAS_CADASTRO_JANELA_SEGUNDOS,
            )
        ]
    )
    limpar_vencidas()
    return bool(ids)
