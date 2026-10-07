"""DL-068 (critério 1, auditoria N7): o Django instalado é o fixado, e o pin
tem as correções de segurança.

`Django==6.1.2` traz as correções dos 4 CVEs publicados em 06/10/2026:
CVE-2026-77050, CVE-2026-84429, CVE-2026-87890 e CVE-2026-87975. Sem teste, o
pin voltaria para 6.1.1 sem que nada reprovasse. E o pin só protege se o
ambiente que roda a suíte for o fixado: por isso a versão instalada também é
comparada com ele.
"""

import re
from pathlib import Path

import django
import pytest

BASE_TXT = Path(__file__).resolve().parents[3] / "requirements" / "base.txt"
VERSAO_MINIMA = (6, 1, 2)


def _ler_pin(texto):
    """Versão `(X, Y, Z)` da linha `Django==X.Y.Z`, ou `None` se não houver.

    Só aceita o pin exato (`==`): `>=` deixaria a versão instalada à sorte do
    resolvedor, e é justamente o que o critério 1 quer evitar.
    """
    for linha in texto.splitlines():
        achado = re.fullmatch(r"\s*Django==(\d+)\.(\d+)\.(\d+)\s*(#.*)?", linha)
        if achado:
            return tuple(int(parte) for parte in achado.groups()[:3])
    return None


def _pin():
    return _ler_pin(BASE_TXT.read_text(encoding="utf-8"))


def _problema_do_pin(pin):
    """Mensagem de reprovação do pin, ou `None` se ele é aceitável."""
    if pin is None:
        return "requirements/base.txt não traz `Django==X.Y.Z`"
    if pin < VERSAO_MINIMA:
        return (
            f"Django=={'.'.join(map(str, pin))} é anterior a 6.1.2, que corrige "
            "CVE-2026-77050, CVE-2026-84429, CVE-2026-87890 e CVE-2026-87975"
        )
    return None


def test_o_leitor_do_pin_entende_o_formato_e_rejeita_o_resto():
    """Controle do próprio leitor: ele não pode devolver um pin inventado."""
    assert _ler_pin("Django==6.1.2\n") == (6, 1, 2)
    assert _ler_pin("# c\ndjango-environ==0.13.0\nDjango==6.1.1  # nota\n") == (6, 1, 1)
    assert _ler_pin("Django>=6.1.2\n") is None
    assert _ler_pin("django-environ==0.13.0\n") is None


@pytest.mark.parametrize("texto", ["Django==6.1.1\n", "Django==5.2.9\n", "Django>=6.1.2\n", ""])
def test_o_criterio_reprova_pin_anterior_a_correcao_ou_ausente(texto):
    """Controle positivo (a mutação em memória): o critério NÃO aprova tudo."""
    assert _problema_do_pin(_ler_pin(texto)) is not None


@pytest.mark.parametrize("texto", ["Django==6.1.2\n", "Django==6.1.3\n", "Django==6.2.0\n"])
def test_o_criterio_aceita_a_versao_corrigida_e_as_posteriores(texto):
    assert _problema_do_pin(_ler_pin(texto)) is None


def test_requirements_fixa_o_django_exato_com_as_correcoes_de_seguranca():
    assert _problema_do_pin(_pin()) is None, _problema_do_pin(_pin())


def test_o_django_instalado_e_o_fixado_no_requirements():
    pin = _pin()

    assert pin is not None
    assert django.VERSION[:3] == pin, (
        f"o ambiente roda Django {django.get_version()}, mas requirements/base.txt "
        f"fixa {'.'.join(map(str, pin))}: a suíte não está testando o que vai a produção"
    )
