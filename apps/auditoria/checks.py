"""DL-068 (BL-577): verificações de configuração da trilha de auditoria.

`config/settings.py` já RECUSA subir com uma rede `/0` em
`DJANGO_PROXIES_CONFIAVEIS`, ou com redes cuja soma cobre exatamente uma família
inteira. Este módulo cobre o que fica abaixo disso: uma rede
larga que contém endereços públicos. Ela não impede a subida, porque há
implantação legítima atrás de CDN com faixas públicas largas, mas quem confia
em uma faixa pública larga está confiando em milhares de máquinas que não são
nossas para escrever o `X-Forwarded-For` que vira o IP da trilha. Por isso o
`manage.py check` (e o `check --deploy`) avisa.
"""

import ipaddress

from django.conf import settings
from django.core.checks import Tags, Warning, register

# HIPÓTESE (HI-51), ainda a validar com o Fred: nenhuma norma fixa estes
# limites. /24 (IPv4) e /64 (IPv6) são as menores redes que costumam
# representar UM segmento de um proxy ou de um balanceador; abaixo disso, a
# rede é larga o bastante para merecer um segundo olhar. Mudar o valor aqui
# não exige migração.
PREFIXO_MINIMO_IPV4 = 24
PREFIXO_MINIMO_IPV6 = 64

# Blocos que NÃO são a internet pública: endereços privados, loopback e
# link-local. Uma rede só é "não pública" se estiver INTEIRAMENTE dentro de um
# deles. Não se usa `rede.is_private` do `ipaddress` porque ele é mais largo que
# "privado, loopback ou link-local": também devolve verdadeiro para faixas de
# documentação (`2001:db8::/32`, `198.51.100.0/24`), de teste de desempenho
# (`198.18.0.0/15`) e outras reservadas, e uma rede assim não é a rede interna
# de um proxy. A lista explícita diz exatamente o que a regra do plano quer.
_BLOCOS_NAO_PUBLICOS = tuple(
    ipaddress.ip_network(bloco)
    for bloco in (
        "10.0.0.0/8",  # RFC 1918
        "172.16.0.0/12",  # RFC 1918
        "192.168.0.0/16",  # RFC 1918
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local
        "fc00::/7",  # IPv6 ULA (equivalente do privado)
        "::1/128",  # loopback
        "fe80::/10",  # link-local
    )
)


def _contem_endereco_publico(rede):
    """Verdadeiro se a rede NÃO está inteiramente em bloco privado/loopback/link-local."""
    return not any(
        bloco.version == rede.version and rede.subnet_of(bloco) for bloco in _BLOCOS_NAO_PUBLICOS
    )


def _e_larga(rede):
    limite = PREFIXO_MINIMO_IPV4 if rede.version == 4 else PREFIXO_MINIMO_IPV6
    return rede.prefixlen < limite


@register(Tags.security)
def verificar_proxies_confiaveis_largos(app_configs=None, **kwargs):
    """Avisa (`auditoria.W001`) por rede larga com endereço público em
    `settings.PROXIES_CONFIAVEIS`.

    IP único e rede privada larga (por exemplo `10.0.0.0/8`) não avisam. Entrada
    que não é IP nem rede é ignorada aqui: o erro de configuração já foi barrado
    na subida, em `config/settings.py`.
    """
    avisos = []
    for entrada in getattr(settings, "PROXIES_CONFIAVEIS", ()):
        try:
            rede = ipaddress.ip_network(str(entrada).strip(), strict=False)
        except ValueError:
            continue
        if _e_larga(rede) and _contem_endereco_publico(rede):
            avisos.append(
                Warning(
                    f"DJANGO_PROXIES_CONFIAVEIS contém a rede pública larga {rede}.",
                    hint=(
                        "Qualquer máquina dessa rede pode forjar o IP gravado na trilha de "
                        "auditoria pelo cabeçalho X-Forwarded-For. Prefira o endereço do "
                        f"proxy, ou uma rede de no mínimo /{PREFIXO_MINIMO_IPV4} (IPv4) ou "
                        f"/{PREFIXO_MINIMO_IPV6} (IPv6). Se a faixa pública larga é "
                        "intencional (por exemplo, uma CDN), este aviso pode ser mantido."
                    ),
                    id="auditoria.W001",
                )
            )
    return avisos
