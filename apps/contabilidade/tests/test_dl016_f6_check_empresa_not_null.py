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
   mencionando o ck_lancamentocontabil_empresa_not_null** — e o cenario
   que a CHECK constraint da F6 defende, apos o NOT NULL da coluna ter
   sido afrouxado (exatamente o cenario de bypass documentado no DE-051
   e na migration 0005). Sem o CHECK, esse INSERT passa silenciosamente.
   Com o CHECK, o banco rejeita com mensagem explicita mencionando o
   nome da constraint.

3. **Constraint nomeada existe na introspeccao do banco** — sanity check
   de que a migration 0005 foi aplicada e a constraint esta presente.

4. **Sanity: caminho feliz nao e bloqueado** — INSERT direto com
   empresa_id valido passa, provando que a constraint nao esta
   bloqueando escritas legitimas.

Importante: o teste #2 faz `ALTER TABLE ... DROP NOT NULL` em setup para
simular o cenario de bypass que o CHECK defende. Em try/finally garante
que a coluna volta a NOT NULL mesmo se o assertion falhar no meio. Sem
isso, o teste polui o schema pra testes subsequentes na mesma sessao.

O padrao de fixtures segue o que o PR #31 da DL-016 (F1) ja estabeleceu
em `test_competencia.py`:
- `setUpTestData` cria `Escritorio` antes da `Empresa`.
- CNPJ em 14 digitos sem mascara, em formato canonico aceito pela
  CheckConstraint `empresa_cnpj_canonico` da Empresa.
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

    def test_insert_direto_sem_empresa_falha_com_mensagem_sobre_not_null_ou_check(self):
        """INSERT direto via SQL bypassando o ORM deve falhar.

        Em PG, NOT NULL da coluna e avaliado antes de CHECK constraint, entao
        a mensagem de erro vira do NOT NULL (mensagem "violates not-null
        constraint"). O que importa e que o INSERT e rejeitado pelo banco
        — sem o CHECK, um futuro DROP NOT NULL deixaria esse INSERT passar;
        com o CHECK, mesmo apos DROP NOT NULL o INSERT continua sendo
        rejeitado (e a mensagem vira "violates check constraint
        ck_lancamentocontabil_empresa_not_null").

        Aceita AMBAS as mensagens como sinal de defesa em profundidade:
        - 'violates not-null constraint' (situacao normal de hoje)
        - 'ck_lancamentocontabil_empresa_not_null' (situacao apos bypass do NOT NULL)
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
        msg = str(ctx.exception)
        self.assertTrue(
            "violates not-null constraint" in msg
            or "ck_lancamentocontabil_empresa_not_null" in msg,
            f"Mensagem deveria mencionar not-null OU check. Recebido: {msg}",
        )

    def test_insert_direto_sem_empresa_falha_apos_drop_not_null(self):
        """Cenario real de bypass: apos ALTER TABLE DROP NOT NULL, o CHECK
        constraint da F6 passa a ser a unica defesa. INSERT com empresa_id=NULL
        deve falhar mencionando explicitamente `ck_lancamentocontabil_empresa_not_null`.

        try/finally garante que mesmo se o assertion falhar, o NOT NULL
        volta ao estado original (cleanup obrigatorio para nao quebrar
        testes subsequentes na mesma sessao).
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE contabilidade_lancamentocontabil ALTER COLUMN empresa_id DROP NOT NULL"
            )
        try:
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
                                    (NULL, '2026-09-01', 'bypass check', NOW())
                                """
                            )
                        transaction.savepoint_commit(sid)
                    except IntegrityError:
                        transaction.savepoint_rollback(sid)
                        raise
            self.assertIn(
                "ck_lancamentocontabil_empresa_not_null",
                str(ctx.exception),
                f"Apos DROP NOT NULL, o CHECK deveria ser a defesa. Recebido: {ctx.exception}",
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "ALTER TABLE contabilidade_lancamentocontabil "
                    "ALTER COLUMN empresa_id SET NOT NULL"
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
        self.assertTrue(LancamentoContabil.objects.filter(historico="bypass test happy").exists())
