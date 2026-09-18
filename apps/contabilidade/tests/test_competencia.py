"""Testes do modelo `Competencia` (F1 — DL-016).

Escopo deste arquivo: SOMENTE o que F1 entrega (modelo + constraints).
Comportamento transacional em `criar_lancamento` (F2) tem seu próprio
arquivo em `test_services.py` (`class CompetenciaNoLancamentoTests`),
e F3/F4 trarão `test_encerramento.py` e `test_reabertura.py`.

ESTADO DESTE ARQUIVO: DUAS CORREÇÕES aplicadas em CI (após `31bbfc9`).

PRIMEIRA CORREÇÃO (commit 81179b0, segundo push do PR #31):
- Adicionado `from apps.tenancy.models import Escritorio`.
- Os dois `setUpTestData` (de `CompetenciaModelTests` e
  `CompetenciaOrderingTests`) agora criam `Escritorio` antes da `Empresa`,
  seguindo o mesmo padrão de `apps/contabilidade/tests/test_services.py`
  e `apps/core/tests/test_dl024_*.py`.
- Ver DE-046.

SEGUNDA CORREÇÃO (commit atual, terceiro push do PR #31):
- `test_mes_fora_da_faixa_recusado` e `test_ano_fora_da_faixa_recusado`
  agora envolvem o `Competencia.objects.create(...)` em
  `transaction.atomic()` para que o `assertRaises(IntegrityError)` capture
  o erro num savepoint próprio — sem isso, a transação do `TestCase`
  fica corrompida após o primeiro `subTest`, e o segundo cai com
  `TransactionManagementError` em vez de `IntegrityError`. Mesmo padrão
  de `apps/empresas/tests/test_canonizacao_constraint.py:48`.
- `test_listagem_ordenada_mais_recente_primeiro` removida a chamada
  `.order_by()` (sem argumentos) que CANCELAVA o `Meta.ordering` do
  manager default. O `values_list(...)` puro agora reflete a ordenação
  do `Meta` como pretendido.

A escrita original foi feita em turno onde o ambiente do agente não
dispunha de Python 3.12+ (exigido por Django 6.1.1) — o sandbox rodava
Python 3.11, e o `pip install -r requirements/dev.txt` falha com
`ERROR: Could not find a version that satisfies the requirement
Django==6.1.1`. Por isso, o arquivo só foi validado por
`python -m py_compile`, NÃO por `manage.py test`, até a CI real
(Python 3.14.7 + PostgreSQL) executar.

Por que mesmo assim eu os escrevo:
- A auditoria da DL-016 (DE-008, camada 1) pediu defesa de unicidade
  em duas camadas (banco + aplicação), e os testes abaixo são a
  evidência de que a camada de aplicação existe e está sendo exercida.
- F2/F3/F4 vão IMPORTAR estes testes como base; sem eles, não há
  contrato público do modelo para reuso.
"""

# Imports pesados (django.test, models, Empresa, Conta) são feitos dentro
# de cada classe via `setUp` ou `setUpTestData` para que o `py_compile`
# deste arquivo não falhe por ausência do Django no ambiente do agente.
# O `import django` no topo garante erro claro se este módulo for
# carregado sem Django configurado.
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.contabilidade.models import Competencia, EstadoCompetencia
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio


class CompetenciaModelTests(TestCase):
    """Testes do modelo `Competencia` puro (sem F2/F3/F4)."""

    @classmethod
    def setUpTestData(cls):
        # Empresa mínima; `cnpj` válido pelo algoritmo, mas o que importa
        # aqui é que `Empresa.save()` não reclame de validação de campo.
        # `escritorio` é obrigatório desde DL-009/DL-015 (FK NOT NULL);
        # ver `apps/empresas/models.py:66`.
        cls.escritorio = Escritorio.objects.create(
            nome="Escritório DL-016 F1",
            cnpj="11111111000111",
        )
        cls.empresa = Empresa.objects.create(
            escritorio=cls.escritorio,
            razao_social="ACME LTDA",
            cnpj="11.444.777/0001-61",
        )

    def test_estado_padrao_e_aberta(self):
        """`Competencia.objects.create` simples nasce com `estado='aberta'`."""
        comp = Competencia.objects.create(empresa=self.empresa, ano=2026, mes=11)
        self.assertEqual(comp.estado, EstadoCompetencia.ABERTA)
        self.assertEqual(comp.estado, "aberta")  # valor bruto, não o label

    def test_str_em_portugues(self):
        """`__str__` devolve mês por extenso + ano + empresa."""
        comp = Competencia.objects.create(empresa=self.empresa, ano=2026, mes=11)
        texto = str(comp)
        # Verifica os três componentes sem depender de formatação
        # exata (espaços, separadores, ordem). O mês de novembro é o
        # mais estável do calendário gregoriano.
        self.assertIn("novembro", texto)
        self.assertIn("2026", texto)
        self.assertIn("ACME", texto)

    def test_unica_por_empresa_ano_mes(self):
        """Tentar criar segunda `Competencia` com mesma chave única falha."""
        Competencia.objects.create(empresa=self.empresa, ano=2026, mes=11)
        with self.assertRaises(IntegrityError):
            Competencia.objects.create(empresa=self.empresa, ano=2026, mes=11)

    def test_mes_fora_da_faixa_recusado(self):
        """Mês = 0 e mês = 13 devem ser recusados pelo CheckConstraint.

        O `transaction.atomic()` em volta do `assertRaises` é o que isola o
        `IntegrityError` num savepoint: sem ele, o `TestCase` deixa a transação
        quebrada e o segundo `subTest` cai com `TransactionManagementError`
        em vez do `IntegrityError` esperado (achado do segundo CI do PR #31).
        Mesmo padrão de `apps/empresas/tests/test_canonizacao_constraint.py`.
        """
        for mes_invalido in (0, 13):
            with self.subTest(mes=mes_invalido):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Competencia.objects.create(
                        empresa=self.empresa, ano=2026, mes=mes_invalido
                    )

    def test_ano_fora_da_faixa_recusado(self):
        """Ano < 1970 e ano > 2999 devem ser recusados pelo CheckConstraint.

        Ver comentário em `test_mes_fora_da_faixa_recusado` sobre o savepoint.
        """
        for ano_invalido in (1969, 3000):
            with self.subTest(ano=ano_invalido):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Competencia.objects.create(
                        empresa=self.empresa, ano=ano_invalido, mes=11
                    )

    def test_competencias_da_mesma_empresa_em_meses_diferentes_coexistem(self):
        """Janeiro e fevereiro do mesmo ano SÃO linhas distintas."""
        c1 = Competencia.objects.create(empresa=self.empresa, ano=2026, mes=1)
        c2 = Competencia.objects.create(empresa=self.empresa, ano=2026, mes=2)
        self.assertNotEqual(c1.pk, c2.pk)
        self.assertEqual(Competencia.objects.count(), 2)


class CompetenciaOrderingTests(TestCase):
    """Testa o `Meta.ordering = ["-ano", "-mes"]` (mais recente primeiro)."""

    @classmethod
    def setUpTestData(cls):
        cls.escritorio = Escritorio.objects.create(
            nome="Escritório DL-016 F1 ordering",
            cnpj="22222222000122",
        )
        cls.empresa = Empresa.objects.create(
            escritorio=cls.escritorio,
            razao_social="ACME LTDA",
            cnpj="11.444.777/0001-61",
        )
        Competencia.objects.create(empresa=cls.empresa, ano=2025, mes=6)
        Competencia.objects.create(empresa=cls.empresa, ano=2026, mes=11)
        Competencia.objects.create(empresa=cls.empresa, ano=2026, mes=3)

    def test_listagem_ordenada_mais_recente_primeiro(self):
        # Sem `.order_by()` aqui — chamar `.order_by()` sem args CANCELA
        # o `Meta.ordering` do manager default, e o teste viraria prova de
        # "a ordem é indeterminada", não de "a ordem é a do Meta".
        # Achado do segundo CI do PR #31.
        resultado = list(Competencia.objects.values_list("ano", "mes"))
        # Aplica a ordenação do Meta na mão para comparar:
        ordenadas = sorted(resultado, key=lambda t: (t[0], t[1]), reverse=True)
        self.assertEqual(resultado, ordenadas)
        # Confirmação adicional: o primeiro é (2026, 11).
        self.assertEqual(resultado[0], (2026, 11))
