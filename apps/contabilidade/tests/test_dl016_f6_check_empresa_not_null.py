"""Testes da CHECK constraint `ck_lancamentocontabil_empresa_not_null` (DL-016 F6).

Escopo deste arquivo: SOMENTE a defesa em profundidade contra INSERT direto
que burle o ORM (shell-admin, psql, scripts de migração antigos). A garantia
principal continua sendo a coluna NOT NULL no schema — gerada automaticamente
pelo Django porque `LancamentoContabil.empresa = ForeignKey(...)` sem
`null=True`.

O cenario coberto aqui:

1. **Insert via ORM sem empresa falha em `full_clean()`** — coberto pelo
   `IntegrityError` que vem do NOT NULL do schema. Esse NAO e o alvo do
   teste: ele ja existe em outros arquivos via path normal. O foco F6
   e diferente.

2. **Insert direto via SQL bypassando o ORM falha com `IntegrityError`
   "violates check constraint"** — e o cenario que a CHECK constraint da
   F6 defende. Sem o CHECK, esse INSERT passa (a coluna e NOT NULL por
   schema, mas em PG ha historico de bypass via `SET CONSTRAINTS ALL
   DEFERRED` + raw SQL, alem de races em migracoes). Com o CHECK,
   qualquer tentativa falha no banco, mesmo que o NOT NULL da coluna
   tenha sido afrouxado por algum ALTER TABLE malicioso ou por uma
   migration futura descuidada.

3. **Constraint nomeada existe na introspeccao do banco** — sanity check
   de que a migration 0005 foi aplicada e a constraint esta presente.

O padrao de fixtures segue o que o PR #31 da DL-016 (F1) ja estabeleceu
em `test_competencia.py`:
- `setUpTestData` cria `Escritorio` antes da `Empresa`.
- Empresa tem `cnpj` valido pelo algoritmo, mas o foco do teste
  e a defesa do banco, nao a validacao do CNPJ.
"""

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.contabilidade.models import LancamentoContabil
from apps.empresas.models import Empresa, Escritorio


class CheckEmpresaNotNullTests(TestCase):
    """Testes da CHECK constraint `ck_lancamentocontabil_empresa_not_null`."""

    @classmethod
    def setUpTestData(cls):
        cls.escritorio = Escritorio.objects.create(
            nome="Escritório F6",
            cnpj="11111111000111",
        )
        cls.empresa = Empresa.objects.create(
            escritorio=cls.escritorio,
            cnpj="22222222000122",
            razao_social="Empresa F6 LTDA",
        )

    def test_constraint_existe_no_banco(self):
        """A constraint `ck_lancamentocontabil_empresa_not_null` deve estar
        presente na introspeccao do schema (psql: \\d contabilidade_lancamentocontabil)."""
        with connection.cursor() as cursor:
            # PG-specific: information_schema.check_constraints
            cursor.execute(
                """
                SELECT constraint_name
                FROM information_schema.check_constraints
                WHERE constraint_name = 'ck_lancamentocontabil_empresa_not_null'
                """
            )
            row = cursor.fetchone()
        self.assertIsNotNone(
            row,
            "CHECK constraint ck_lancamentocontabil_empresa_not_null "
            "nao encontrada no schema. A migration 0005 foi aplicada?",
        )

    def test_insert_direto_com_empresa_null_falha(self):
        """INSERT direto via SQL bypassando o ORM deve falhar com IntegrityError.

        Sem a CHECK constraint, este INSERT passaria em cenarios onde o NOT NULL
        da coluna tivesse sido afrouxado (ALTER TABLE malicioso, migration
        descuidada) ou onde houvesse race com SET CONSTRAINTS DEFERRED.
        Com a CHECK, o banco rejeita na hora.

        NOTA: usamos transacao savepoint para isolar o INSERT que vai falhar —
        sem isso, o Django marcaria a transacao como broken e qualquer
        assertAfter falharia por conexao suja.
        """
        with self.assertRaises(IntegrityError) as ctx:
            with transaction.atomic():
                sid = transaction.savepoint()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO contabilidade_lancamentocontabil
                                (empresa_id, data, historico, criado_em)
                            VALUES
                                (NULL, '2026-09-01', 'bypass test', NOW())
                            """
                        )
                    transaction.savepoint_commit(sid)
                except IntegrityError:
                    transaction.savepoint_rollback(sid)
                    raise
        # Sanidade: a mensagem menciona a constraint
        self.assertIn(
            "ck_lancamentocontabil_empresa_not_null",
            str(ctx.exception),
            f"Mensagem de erro deveria mencionar a constraint. Recebido: {ctx.exception}",
        )

    def test_insert_direto_com_empresa_valida_passa(self):
        """INSERT direto via SQL com empresa_id valido deve passar (sanity check
        do cenario feliz — garante que a constraint nao esta bloqueando
        escritas legitimas)."""
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO contabilidade_lancamentocontabil
                        (empresa_id, data, historico, criado_em)
                    VALUES
                        (%s, '2026-09-01', 'bypass test happy', NOW())
                    """,
                    [self.empresa.pk],
                )
        # Conferindo que entrou
        self.assertTrue(LancamentoContabil.objects.filter(historico="bypass test happy").exists())
