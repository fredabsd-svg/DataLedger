"""DL-070 (BL-619) — a alteração de `Conta` pelo admin entra na trilha de auditoria.

Critério 9 do plano `docs/planos/DL-070-melhorias-com-equipe-multiagente.md`:
um superusuário altera a coluna da DMPL de uma conta pelo admin do Django e a
trilha precisa registrar `contabilidade.conta.admin_atualizado` com
`classificacao_dmpl` no antes e no depois. A cobertura genérica do admin
(DL-030, `apps/auditoria/signals.py`) é a que deve produzir esse registro.

Dados sintéticos: CNPJs de exemplo com dígito verificador válido, nomes
fictícios. A conta não tem movimento, então a troca não cai na guarda de
período encerrado de `Conta.clean()`.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import ClassificacaoDmpl, Conta, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

SENHA = "senha-forte-dl070"
CNPJ_ESCRITORIO = "11222333000181"
CNPJ_EMPRESA = "11444777000161"


def _criar_conta_de_patrimonio_liquido():
    escritorio = Escritorio.objects.create(nome="Escritório DL-070 BL-619", cnpj=CNPJ_ESCRITORIO)
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa sintética DL-070", cnpj=CNPJ_EMPRESA
    )
    return Conta.objects.create(
        empresa=empresa,
        codigo="2.03.01",
        nome="Capital social sintético",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
        classificacao_dmpl=ClassificacaoDmpl.CAPITAL_SOCIAL,
    )


def _superusuario_logado():
    get_user_model().objects.create_superuser(
        username="admin-dl070", password=SENHA, email="admin-dl070@example.com"
    )
    client = Client()
    assert client.login(username="admin-dl070", password=SENHA)
    return client


def _dados_do_formulario_do_admin(client, url):
    """Monta o POST com TODOS os campos que o formulário do admin mostra, a
    partir do próprio `initial` do formulário renderizado. Assim o teste não
    depende de conhecer a lista de campos do `ModelForm` nem de adivinhar
    como o admin serializa cada tipo (FK pelo pk, booleano como "on")."""
    form = client.get(url).context["adminform"].form
    dados = {}
    for nome in form.fields:
        valor = form.initial.get(nome)
        if isinstance(valor, bool):
            if valor:
                dados[nome] = "on"
        elif valor is not None:
            dados[nome] = str(valor)
    return dados


@pytest.mark.django_db(transaction=True)
def test_admin_altera_coluna_da_dmpl_e_a_trilha_registra_antes_e_depois():
    conta = _criar_conta_de_patrimonio_liquido()
    client = _superusuario_logado()
    url = reverse("admin:contabilidade_conta_change", args=[conta.pk])

    dados = _dados_do_formulario_do_admin(client, url)
    dados["classificacao_dmpl"] = ClassificacaoDmpl.RESERVA_LEGAL

    resposta = client.post(url, data=dados)

    assert resposta.status_code == 302, resposta.content
    conta.refresh_from_db()
    assert conta.classificacao_dmpl == ClassificacaoDmpl.RESERVA_LEGAL

    registro = RegistroAuditoria.objects.get(acao="contabilidade.conta.admin_atualizado")
    assert registro.detalhes["valores_anteriores"]["classificacao_dmpl"] == (
        ClassificacaoDmpl.CAPITAL_SOCIAL
    )
    assert registro.detalhes["valores_novos"]["classificacao_dmpl"] == (
        ClassificacaoDmpl.RESERVA_LEGAL
    )
