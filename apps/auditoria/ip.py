"""DL-057 (BL-553): IP real do cliente para a trilha de auditoria.

Atrás de proxy reverso (DE-014) `REMOTE_ADDR` é o IP do PROXY, então a trilha
inteira gravaria o mesmo endereço. O IP do cliente chega em `X-Forwarded-For`,
mas esse cabeçalho é escrito também por quem faz a requisição: qualquer cliente
pode mandar `X-Forwarded-For: 1.2.3.4` e, se o sistema confiar nele, forjar a
origem que fica registrada na trilha.

Regra (única, usada por `registrar` e disponível para outros pontos):

1. `X-Forwarded-For` só é considerado quando `REMOTE_ADDR` (o par TCP, que o
   cliente não escolhe) pertence a `settings.PROXIES_CONFIAVEIS`. Lista vazia
   (padrão) = cabeçalho ignorado.
2. O cabeçalho é percorrido da DIREITA para a ESQUERDA: cada proxy confiável
   acrescenta à direita o endereço de quem lhe entregou a requisição, então só
   a parte à direita foi escrita por infraestrutura nossa. O primeiro endereço
   que não é proxy confiável é o cliente; o que está à esquerda dele pode ter
   sido forjado e é descartado.
3. Se todos os endereços do cabeçalho forem proxies confiáveis, o cliente está
   dentro da rede confiável e vale o mais à esquerda.
4. Qualquer valor malformado encontrado no caminho invalida o cabeçalho e cai
   para `REMOTE_ADDR`. Nunca levanta exceção: a trilha não pode deixar de gravar
   por causa de um cabeçalho ruim.

Esta função NÃO altera `SECURE_PROXY_SSL_HEADER` nem nenhuma outra configuração
de proxy do Django.
"""

import ipaddress
from functools import lru_cache

from django.conf import settings


def _normalizar(endereco):
    """Devolve o `ipaddress` sem a forma IPv4-mapeada (`::ffff:a.b.c.d`).

    Sockets dual-stack entregam IPv4 nessa forma; sem normalizar, um proxy
    `10.0.0.1` configurado não casaria com `::ffff:10.0.0.1`.
    """
    if endereco.version == 6 and endereco.ipv4_mapped is not None:
        return endereco.ipv4_mapped
    return endereco


def _ler_ip(texto):
    """IP válido normalizado, ou `None` para qualquer texto que não seja IP."""
    if not isinstance(texto, str):
        return None
    texto = texto.strip()
    # Python 3.9+ aceita escopo IPv6 ("fe80::1%eth0"); a coluna `inet` do
    # PostgreSQL e o GenericIPAddressField não, e o texto é controlado por quem
    # faz a requisição. Endereço com escopo é tratado como malformado.
    if "%" in texto:
        return None
    try:
        return _normalizar(ipaddress.ip_address(texto))
    except ValueError:
        return None


@lru_cache(maxsize=32)
def _redes_confiaveis(entradas):
    """Converte `PROXIES_CONFIAVEIS` (IP ou CIDR) em redes.

    Entrada inválida é ignorada aqui (lado seguro: menos confiança, nunca
    mais). O erro de configuração é barrado na subida, em `config/settings.py`.
    """
    redes = []
    for entrada in entradas:
        try:
            redes.append(ipaddress.ip_network(str(entrada).strip(), strict=False))
        except ValueError:
            continue
    return tuple(redes)


def _e_confiavel(endereco, redes):
    return any(endereco.version == rede.version and endereco in rede for rede in redes)


def ip_do_cliente(request):
    """IP do cliente da requisição, como texto, ou `None` se não houver IP válido.

    Ver o docstring do módulo para a regra. Nunca levanta exceção.
    """
    remoto = _ler_ip(request.META.get("REMOTE_ADDR"))
    if remoto is None:
        return None

    redes = _redes_confiaveis(tuple(getattr(settings, "PROXIES_CONFIAVEIS", ())))
    if not _e_confiavel(remoto, redes):
        # Par TCP não é proxy nosso: o cabeçalho veio de quem pede e é ignorado.
        return str(remoto)

    cabecalho = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not isinstance(cabecalho, str) or not cabecalho.strip():
        return str(remoto)

    cliente = remoto
    for texto in reversed(cabecalho.split(",")):
        candidato = _ler_ip(texto)
        if candidato is None:
            return str(remoto)
        cliente = candidato
        if not _e_confiavel(candidato, redes):
            break
    return str(cliente)
