"""Testes da management command `backfill_lancamento_competencia` (DL-016 F5).

Escopo deste arquivo: SOMENTE o comportamento da command. O modelo
`Competencia` tem seu proprio arquivo (`test_competencia.py`), e a
vinculacao automatica em `criar_lancamento` (F2) tem
`test_services.py:class CompetenciaNoLancamentoTests`.

Os 5 cenarios cobertos aqui:

1. **Competencia ja existe:** `Competencia(2026, 9)` criada; lancamento
   de set/2026 sem FK -> Competencia count nao muda; FK atribuida.
2. **Competencia a criar:** Lancamento de ago/2026 sem FK ->
   `Competencia(2026, 8)` criada, FK atribuida.
3. **Dry-run nao altera o banco:** Lancamento sem FK, rodar com
   dry-run -> Competencia count nao muda, FK permanece None, exit 0.
4. **Idempotencia:** rodar --apply duas vezes seguidas, a 2a nao
   altera nada (coberto pela clausula `competencia__isnull=True`).
5. **Concorrencia:** lancamento criado ENTRE duas passadas eh pego
   pela 2a passada.

NOTA SOBRE ORFAOS: Este arquivo NAO cobre o caso "lancamento sem
empresa". O `LancamentoContabil.empresa` e `ForeignKey(Empresa,
on_delete=PROTECT)` sem `null=True` desde DL-006 - ou seja, NOT NULL
por schema, e portanto e fisicamente impossivel criar um lancamento
orfao via ORM. A command deliberadamente NAO tem branch de orfao
(branch morto por design). A cobertura contra orfaos reais passa a
ser uma CHECK constraint em `empresa_id IS NOT NULL` em DL-016 F6,
e um `SELECT COUNT(*) ... WHERE empresa_id IS NULL` no runbook de
deploy do F5 (ver docstring da command).

O padrao de fixtures segue o que o PR #31 da DL-016 (F1) ja
estabeleceu em `test_competencia.py`:
- `setUpTestData` cria `Escritorio` antes da `Empresa`.
- Empresa tem `cnpj` valido pelo algoritmo, mas o foco do teste
  e o fluxo da command, nao a validacao do CNPJ.
"""

import datetime

from django.core.management import call_command
from django.test import TestCase

from apps.contabilidade.models import (
    Competencia,
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio


class BackfillCompetenciaTests(TestCase):
    """Suite da management command `backfill_lancamento_competencia`."""

    @classmethod
    def setUpTestData(cls):
        cls.escritorio = Escritorio.objects.create(
            nome="Escritorio DL-016 F5",
            cnpj="11111111000111",
        )
        cls.empresa = Empresa.objects.create(
            escritorio=cls.escritorio,
            razao_social="ACME Backfill LTDA",
            cnpj="11.444.777/0001-61",
        )
        # Uma conta para associar aos lancamentos (ItemLancamento exige conta).
        cls.conta_caixa = Conta.objects.create(
            empresa=cls.empresa,
            codigo="1.1.1.01",
            nome="Caixa",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
        )

    def _criar_lancamento_sem_competencia(
        self,
        *,
        data: datetime.date,
        empresa: Empresa | None = None,
        historico: str = "lancamento de teste",
    ) -> LancamentoContabil:
        """Cria LancamentoContabil sem FK competencia e com 1 ItemLancamento.

        `empresa` NAO tem default None explicito no call site: como
        `LancamentoContabil.empresa` e NOT NULL por schema desde
        DL-006, o default interno `self.empresa` garante que o teste
        sempre cria lancamentos validos. Para passar uma empresa
        diferente (cenarios multi-empresa, se viermos a ter), basta
        passar o argumento `empresa=...`.
        """
        if empresa is None:
            empresa = self.empresa
        lancamento = LancamentoContabil.objects.create(
            empresa=empresa,
            data=data,
            historico=historico,
        )
        ItemLancamento.objects.create(
            lancamento=lancamento,
            conta=self.conta_caixa,
            tipo=TipoPartida.DEBITO,
            valor="100.00",
        )
        return lancamento

    # ------------------------------------------------------------------
    # Cenario 1: competencia ja existe
    # ------------------------------------------------------------------
    def test_competencia_existente_e_reaproveitada(self):
        """Se a Competencia(2026, 9) ja existe, a FK e atribuida sem criar nova."""
        comp_existente = Competencia.objects.create(empresa=self.empresa, ano=2026, mes=9)
        lanc = self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 9, 10),
            historico="setembro sem FK; competencia ja existe",
        )
        self.assertIsNone(lanc.competencia_id)
        competencias_antes = Competencia.objects.count()

        call_command("backfill_lancamento_competencia", "--apply")

        # A Competencia(2026, 9) NAO foi duplicada; apenas reaproveitada.
        self.assertEqual(Competencia.objects.count(), competencias_antes)
        # A FK do lancamento agora aponta para a Competencia existente.
        lanc.refresh_from_db()
        self.assertEqual(lanc.competencia_id, comp_existente.id)

    # ------------------------------------------------------------------
    # Cenario 2: competencia a criar
    # ------------------------------------------------------------------
    def test_competencia_a_criar_e_criada_e_atribuida(self):
        """Lancamento de ago/2026 sem FK cria Competencia(2026, 8)."""
        lanc = self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 8, 10),
            historico="agosto sem FK; competencia precisa ser criada",
        )
        self.assertIsNone(lanc.competencia_id)
        # Sanidade: nenhuma competencia de agosto antes do backfill.
        self.assertFalse(Competencia.objects.filter(empresa=self.empresa, ano=2026, mes=8).exists())

        call_command("backfill_lancamento_competencia", "--apply")

        # Agora existe uma Competencia(2026, 8) e a FK foi preenchida.
        comp_criada = Competencia.objects.get(empresa=self.empresa, ano=2026, mes=8)
        lanc.refresh_from_db()
        self.assertEqual(lanc.competencia_id, comp_criada.id)

    # ------------------------------------------------------------------
    # Cenario 3: dry-run nao altera o banco
    # ------------------------------------------------------------------
    def test_dry_run_nao_cria_competencia_nem_atribui_fk(self):
        """Dry-run (default) nao cria Competencia nem preenche FK."""
        lanc = self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 7, 10),
            historico="julho sem FK; dry-run nao deve alterar",
        )
        competencias_antes = Competencia.objects.count()

        # Sem flag --apply: modo dry-run (default explicito no add_arguments).
        call_command("backfill_lancamento_competencia")

        # Nem Competencia nova nem FK atribuida.
        self.assertEqual(Competencia.objects.count(), competencias_antes)
        lanc.refresh_from_db()
        self.assertIsNone(
            lanc.competencia_id,
            "Dry-run NAO deve atribuir FK de Competencia.",
        )

    # ------------------------------------------------------------------
    # Cenario 4: Idempotencia - rodar duas vezes seguidas nao muda nada
    # ------------------------------------------------------------------
    def test_idempotencia_em_apply(self):
        """Rodar --apply duas vezes: a 2a passada nao altera nada."""
        self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 6, 10),
            historico="junho sem FK; idempotencia",
        )
        self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 5, 10),
            historico="maio sem FK; idempotencia",
        )

        call_command("backfill_lancamento_competencia", "--apply")
        competencias_pos_p1 = Competencia.objects.count()

        # Segunda passada: nada deve mudar.
        call_command("backfill_lancamento_competencia", "--apply")
        self.assertEqual(Competencia.objects.count(), competencias_pos_p1)

    # ------------------------------------------------------------------
    # Cenario 5: Concorrencia - lancamento criado durante a 1a passada
    # eh pego na 2a (simulado criando-se apos a 1a passada manual)
    # ------------------------------------------------------------------
    def test_segunda_passada_pega_lancamento_criado_no_meio(self):
        """Lancamento criado ENTRE as passadas eh pego na 2a passada.

        Nao testamos concorrencia de fato (impossivel sem threads); em vez
        disso, simulamos criando o lancamento apos a primeira passada
        rodar ate o fim e verificando que a segunda passada o atribui.
        """
        # 1a passada em base vazia: nao faz nada.
        call_command("backfill_lancamento_competencia", "--apply")

        # Agora surge um lancamento sem FK (simula o que
        # criar_lancamento nao pegou porque ja tinha fechado a passada).
        concorrente = self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 4, 10),
            historico="concorrente criado entre passadas",
        )

        # 2a passada pega ele.
        call_command("backfill_lancamento_competencia", "--apply", "--max-passes", "1")

        concorrente.refresh_from_db()
        self.assertIsNotNone(
            concorrente.competencia_id,
            "Lancamento criado entre passadas deveria ser pego na 2a passada.",
        )
