"""Testes dos campos `nire` e `nivel_de_arredondamento` da Empresa
(DL-027, Fatia A — RC-93, BL-340).

O cadastro de Empresa **não tinha** estes dois campos antes desta
etapa. A obrigação do RC-93 — *"razão social, CNPJ, período,
NIRE e as demais informações de identificação obrigatória saem
sempre"* — não é atendível sem os dados. Este arquivo existe para
fixar o comportamento esperado **antes** da migração que adiciona
os campos.

Os testes são **positivos** sobre os campos novos:

  - **NIRE**: aceito em texto (apenas dígitos), persistido como
    canônico (sem máscara, sem pontos), e devolvido em forma
    canônica quando a empresa é lida de volta.
  - **Nível de arredondamento**: texto curto (até 100 caracteres),
    default sensato quando a empresa não informa (o motor
    determinístico vai sobrescrever depois).

Por que NÃO testar:
  - **Recusa de NIRE com máscara:** a aplicação canônica é
    responsabilidade do `save()` (`normalizar_cnpj` faz o mesmo
    para CNPJ), e a regra do vazio para NIRE fica no `forms.py`
    e no `serializers.py`, não no modelo.
  - **Unicidade do NIRE:** o NIRE é por **estado** (Junta
    Comercial), não por empresa — duas empresas do mesmo grupo
    podem ter o mesmo NIRE se uma for subsidiária; um CNPJ
    sempre corresponde a um NIRE. Esta regra fica para a próxima
    etapa, depois do `HI-12` ser confirmado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL-027", cnpj="11444777000161")


@pytest.fixture
def usuario(escritorio):
    User = get_user_model()
    return User.objects.create_user(
        username="gestor-dl027",
        email="gestor-dl027@escritorio.com.br",
        password="senha-forte-123",
    )


@pytest.mark.django_db
class TestEmpresaNire:
    """O campo `nire` da Empresa."""

    def test_campo_nire_aceita_texto_e_persiste(self, escritorio):
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Padaria NIRE",
            cnpj="11444777000161",
            nire="35200000000",
        )
        empresa.refresh_from_db()
        assert empresa.nire == "35200000000"

    def test_campo_nire_e_vazio_por_default(self, escritorio):
        """NIRE é opcional no cadastro: o sistema emite o relatório
        com o marcador `(não informado)` até o contador preencher.
        A regra do vazio está em
        `apps.documentos.identificacao._marcador_de_vazio`, e ela
        trata tanto `None` quanto string vazia como vazio — a
        função pura é tolerante ao modelo.

        Por que `default=""` em vez de `default=None`? Mesmo padrão
        do `nome_fantasia` do mesmo modelo: `CharField` com
        `blank=True` no Django usa string vazia como "ausência"
        canônica, e isso evita o custo de `NULL` no banco para um
        campo que raramente vai estar preenchido."""
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Padaria Sem NIRE",
            cnpj="12131415000166",
        )
        assert empresa.nire == ""
        assert empresa.nire is None or empresa.nire == ""  # tolerância da função pura

    def test_campo_nire_pode_ser_atualizado_para_valor_valido(self, escritorio):
        """Atualização é a forma comum de preencher depois da
        criação — o contador pode cadastrar a empresa só com CNPJ
        e voltar depois para completar."""
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Padaria Atualiza",
            cnpj="11122233000181",
        )
        empresa.nire = "35211111111"
        empresa.save()
        empresa.refresh_from_db()
        assert empresa.nire == "35211111111"


@pytest.mark.django_db
class TestEmpresaNivelArredondamento:
    """O campo `nivel_de_arredondamento` da Empresa."""

    def test_campo_nivel_arredondamento_persiste_texto(self, escritorio):
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Padaria Arredondamento",
            cnpj="22233344000195",
            nivel_de_arredondamento="2 casas decimais (ABNT NBR 5891)",
        )
        empresa.refresh_from_db()
        assert empresa.nivel_de_arredondamento == "2 casas decimais (ABNT NBR 5891)"

    def test_campo_nivel_arredondamento_default_e_texto_sensato(self, escritorio):
        """Default escolhido pelo plano: `2 casas decimais (ABNT NBR
        5891)` — é o que o sistema usa quando o motor determinístico
        não devolve texto explícito. Texto, não enum, porque a regra
        do DE-010 é **aberta** (cada cálculo passa política
        explícita) e o default do cadastro é só fallback para a
        impressão."""
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Padaria Default",
            cnpj="33344455000106",
        )
        assert empresa.nivel_de_arredondamento == "2 casas decimais (ABNT NBR 5891)"

    def test_campo_nivel_arredondamento_pode_ser_personalizado(self, escritorio):
        """Texto curto (até 100 caracteres). Limite declarado:
        política monetária é por regra, e cada empresa pode ter a
        sua — ICMS com TRUNCAR para algum caso específico, por
        exemplo, é legítimo."""
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Padaria Custom",
            cnpj="55566677000155",
            nivel_de_arredondamento="4 casas para volume",
        )
        empresa.refresh_from_db()
        assert empresa.nivel_de_arredondamento == "4 casas para volume"
