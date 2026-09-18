"""Testes da management command `backfill_lancamento_competencia` (DL-016 F5).

Escopo deste arquivo: SOMENTE o comportamento da command. O modelo
`Competencia` tem seu proprio arquivo (`test_competencia.py`), e a
vinculacao automatica em `criar_lancamento` (F2) tem
`test_services.py:class CompetenciaNoLancamentoTests`.

Os 4 cenarios cobertos aqui:

1. **Orfao pulado:** Lancamento com `empresa=None` (forcado em teste)
   -> contador orfaos += 1, FK permanece None, exit 0.
2. **Competencia ja existe:** `Competencia(2026, 9)` criada; lancamento
   de set/2026 sem FK -> Competencia count nao muda; FK atribuida.
3. **Competencia a criar:** Lancamento de ago/2026 sem FK ->
   `Competencia(2026, 8)` criada, FK atribuida.
4. **Dry-run nao altera o banco:** Lancamento sem FK, rodar com
   dry-run -> Competencia count nao muda, FK permanece None, exit 0.

Para o cenario "orfao pulado": o `LancamentoContabil.empresa` e
`on_delete=PROTECT`, e na pratica nunca deveria ter `empresa=None`
em producao (a FK e parte do modelo desde DL-006 e a coluna nunca
foi alterada para null=True). Porem, o teste cria o orfao por uma
via que burla o caminho de negocio (`objects.update` direto na FK)
para confirmar que a command trata o caso sem quebrar.

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
        # Uma conta para associar aos lancamentos (a FK nao e NOT NULL
        # em LancamentoContabil, mas ItemLancamento exige conta).
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
        empresa=None,
        historico: str = "lancamento de teste",
    ) -> LancamentoContabil:
        """Cria LancamentoContabil sem FK competencia e com 1 ItemLancamento.

        `empresa=None` permite simular o cenario de orfao.
        """
        lancamento = LancamentoContabil.objects.create(
            empresa=empresa,  # pode ser None para teste de orfao
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
    # Cenario 1: orfao pulado
    # ------------------------------------------------------------------
    def test_orfao_sem_empresa_e_pulado_sem_quebrar(self):
        """Lancamento com empresa=None nao vira Competencia; FK continua None."""
        # Forca a criacao de um lancamento orfao. Na pratica nunca
        # acontece (FK obrigatoria desde DL-006), mas o teste confirma
        # que a command trata o caso sem crashar.
        orfao = self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 1, 15),
            empresa=None,
            historico="orfao forcado para teste",
        )

        # Sanidade: o lancamento existe sem FK.
        self.assertIsNone(orfao.competencia_id)
        self.assertIsNone(orfao.empresa_id)
        competencias_antes = Competencia.objects.count()

        # Roda a command em dry-run (default).
        call_command("backfill_lancamento_competencia")

        # O orfao continua sem FK. Nenhuma Competencia foi criada.
        orfao.refresh_from_db()
        self.assertIsNone(
            orfao.competencia_id,
            "Orfao (empresa=None) NAO deve receber FK de Competencia.",
        )
        self.assertEqual(Competencia.objects.count(), competencias_antes)

    def test_orfao_nao_falha_em_apply(self):
        """Em apply, orfao tambem nao quebra a command. FK continua None."""
        orfao = self._criar_lancamento_sem_competencia(
            data=datetime.date(2026, 1, 15),
            empresa=None,
            historico="orfao forcado para teste em apply",
        )
        competencias_antes = Competencia.objects.count()

        # Roda em --apply.
        call_command("backfill_lancamento_competencia", "--apply")

        orfao.refresh_from_db()
        self.assertIsNone(orfao.competencia_id)
        self.assertEqual(Competencia.objects.count(), competencias_antes)

    # ------------------------------------------------------------------
    # Cenario 2: competencia ja existe
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
    # Cenario 3: competencia a criar
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
    # Cenario 4: dry-run nao altera o banco
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
    # Idempotencia: rodar duas vezes seguidas nao muda nada na 2a
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
    # Concorrentes: lancamento criado durante a 1a passada eh pego na 2a
    # (simulado criando-se apos a 1a passada manual)
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
