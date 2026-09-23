"""DL-027 Fatia B.3 — carimbo de data e hora da emissão.

Plano DL-027 (item 1 da "O que entra, com o motivo"):
"Carimbo de data e hora da emissão." Catálogo do plano DL-027, item 1.

O carimbo:
- É capturado por request (`timezone.localtime()`) e passado para o
  template como `carimbo_de_emissao` e `carimbo_de_emissao_texto` (string
  pt-BR pronta).
- Aparece no bloco `contexto_extra` do `templates/base.html` — mesmo
  lugar onde Empresa e Período já aparecem, em todas as telas que
  sobrescrevem o bloco. Aqui só testamos o Balancete; a propagação para
  Diário/Razão/Balanço é mecânica (mesma view pattern, mesmo template
  block) e será testada quando essas telas entrarem na mesma etapa.
- Usa o fuso `settings.TIME_ZONE` ("America/Sao_Paulo"), não UTC — o
  usuário lê o carimbo no relógio dele.
"""

import re
from datetime import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório DL-027 B.3", cnpj="77777777000177")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DL-027 B.3 Ltda",
        cnpj="77788899000100",
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-dl027b3",
        email="gestor-dl027b3@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "usuario": usuario}


def _login(client, cen):
    client.force_login(cen["usuario"])


# Regex do formato do carimbo: "dd/mm/aaaa às HH:MM:SS" — exatamente
# como a view produz via `strftime("%d/%m/%Y às %H:%M:%S")`.
_FORMATO_DO_CARIMBO = re.compile(r"\b\d{2}/\d{2}/\d{4}\s+às\s+\d{2}:\d{2}:\d{2}\b")


def test_view_balancete_carimbo_esta_no_contexto(client, cen):
    """O carimbo é injetado no contexto da view — a view não produz o
    timestamp no template (seria fragil: timezone, formato, etc. — tudo
    da camada Python)."""
    _login(client, cen)
    resposta = client.get(reverse("contabilidade_web:balancete", args=[cen["empresa"].id]))
    assert resposta.status_code == 200
    assert "carimbo_de_emissao" in resposta.context
    assert isinstance(resposta.context["carimbo_de_emissao"], datetime)
    assert "carimbo_de_emissao_texto" in resposta.context


def test_view_balancete_carimbo_texto_no_formato_pt_br(client, cen):
    """A string pt-BR do carimbo segue o formato `dd/mm/aaaa às
    HH:MM:SS` — exigido pelo plano e pela convenção brasileira."""
    _login(client, cen)
    resposta = client.get(reverse("contabilidade_web:balancete", args=[cen["empresa"].id]))
    texto = resposta.context["carimbo_de_emissao_texto"]
    assert _FORMATO_DO_CARIMBO.search(texto), (
        f"Formato do carimbo fora do esperado (dd/mm/aaaa às HH:MM:SS): {texto!r}"
    )


def test_view_balancete_carimbo_no_fuso_america_sao_paulo(client, cen):
    """O carimbo é timezone-aware e está em America/Sao_Paulo — não em
    UTC. O usuário lê o carimbo no relógio dele, não em UTC."""
    from datetime import timedelta

    _login(client, cen)
    resposta = client.get(reverse("contabilidade_web:balancete", args=[cen["empresa"].id]))
    carimbo = resposta.context["carimbo_de_emissao"]
    assert carimbo.tzinfo is not None, "Carimbo sem timezone"
    # Brasil aboliu o DST em 2019 — São Paulo é sempre -03:00.
    offset = carimbo.utcoffset()
    assert offset == timedelta(hours=-3), f"Esperava offset -03:00, recebi {offset}"


def test_view_balancete_carimbo_aparece_no_html_renderizado(client, cen):
    """O carimbo SAI NO PAPEL — não só no contexto (este é o ponto da
    B.3: o carimbo é IMPRESSO no documento, critério do plano DL-027)."""
    _login(client, cen)
    resposta = client.get(reverse("contabilidade_web:balancete", args=[cen["empresa"].id]))
    html = resposta.content.decode()
    assert "Emitido em" in html
    assert resposta.context["carimbo_de_emissao_texto"] in html


def test_view_balancete_carimbo_distinto_entre_requests_consecutivas(client, cen):
    """Duas requests seguidas recebem carimbos DISTINTOS (com segundos
    diferentes pelo menos) — confirma que cada emissão carrega o seu
    próprio timestamp, requisito do critério "carimbo de data e hora da
    emissão" do plano."""
    from datetime import timedelta

    _login(client, cen)
    resposta1 = client.get(reverse("contabilidade_web:balancete", args=[cen["empresa"].id]))
    # Espera 1,1 segundo para garantir que o segundo do timestamp mude
    # mesmo em sistemas rápidos.
    import time as _time

    _time.sleep(1.1)
    resposta2 = client.get(reverse("contabilidade_web:balancete", args=[cen["empresa"].id]))

    c1 = resposta1.context["carimbo_de_emissao"]
    c2 = resposta2.context["carimbo_de_emissao"]
    assert c2 - c1 >= timedelta(seconds=1), (
        f"Carimbo não mudou entre requests consecutivas: c1={c1}, c2={c2}"
    )
