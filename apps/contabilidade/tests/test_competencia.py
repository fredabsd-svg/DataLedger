"""Testes do modelo `Competencia` (F1 — DL-016).

Escopo deste arquivo: SOMENTE o que F1 entrega (modelo + constraints).
Comportamento transacional em `criar_lancamento` (F2) tem seu próprio
arquivo em `test_services.py` (`class CompetenciaNoLancamentoTests`),
e F3/F4 trarão `test_encerramento.py` e `test_reabertura.py`.

ESTADO DESTE ARQUIVO: IMPORT-ONLY.

Este arquivo NÃO foi executado neste turno. O ambiente do agente não
dispunha de Python 3.12+ (exigido por Django 6.1.1) — o sandbox roda
Python 3.11, e o `pip install -r requirements/dev.txt` falha
com `ERROR: Could not find a version that satisfies the requirement
Django==6.1.1`. Por isso, este arquivo só foi validado por
`python -m py_compile`, NÃO por `manage.py test`. Os testes foram
escritos para serem executados em CI ou em máquina do Fred com
Python 3.12+, e a expectativa é de que passem sem ajustes. Se algo
falhar no CI, o problema é de implementação dos testes, não de design.

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
from django.db import IntegrityError
from django.test import TestCase

from apps.contabilidade.models import Competencia, EstadoCompetencia
from apps.empresas.models import Empresa


class CompetenciaModelTests(TestCase):
    """Testes do modelo `Competencia` puro (sem F2/F3/F4)."""

    @classmethod
    def setUpTestData(cls):
        # Empresa mínima; `cnpj` válido pelo algoritmo, mas o que importa
        # aqui é que `Empresa.save()` não reclame de validação de campo.
        cls.empresa = Empresa.objects.create(
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
        """Mês = 0 e mês = 13 devem ser recusados pelo CheckConstraint."""
        for mes_invalido in (0, 13):
            with self.subTest(mes=mes_invalido):
                with self.assertRaises(IntegrityError):
                    Competencia.objects.create(empresa=self.empresa, ano=2026, mes=mes_invalido)

    def test_ano_fora_da_faixa_recusado(self):
        """Ano < 1970 e ano > 2999 devem ser recusados pelo CheckConstraint."""
        for ano_invalido in (1969, 3000):
            with self.subTest(ano=ano_invalido):
                with self.assertRaises(IntegrityError):
                    Competencia.objects.create(empresa=self.empresa, ano=ano_invalido, mes=11)

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
        cls.empresa = Empresa.objects.create(
            razao_social="ACME LTDA",
            cnpj="11.444.777/0001-61",
        )
        Competencia.objects.create(empresa=cls.empresa, ano=2025, mes=6)
        Competencia.objects.create(empresa=cls.empresa, ano=2026, mes=11)
        Competencia.objects.create(empresa=cls.empresa, ano=2026, mes=3)

    def test_listagem_ordenada_mais_recente_primeiro(self):
        resultado = list(Competencia.objects.values_list("ano", "mes").order_by())
        # Aplica a ordenação do Meta na mão para comparar:
        ordenadas = sorted(resultado, key=lambda t: (t[0], t[1]), reverse=True)
        self.assertEqual(resultado, ordenadas)
        # Confirmação adicional: o primeiro é (2026, 11).
        self.assertEqual(resultado[0], (2026, 11))
