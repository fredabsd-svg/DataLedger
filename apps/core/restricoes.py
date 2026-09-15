"""Módulo compartilhado para traduzir violação de restrição de banco
declarada em `Meta.constraints` (`UniqueConstraint`/`CheckConstraint`) em
mensagem de negócio — 400, nunca 500 (BL-144, achado R5-5 da auditoria
DL-017 rodada 5).

O padrão já existia, uma vez, em `apps.empresas.services.
erro_de_cnpj_duplicado_como_400` — só para a unicidade de CNPJ. A DE-034
manda varrer TODA `Meta.constraints` do repositório com a mesma pergunta:
"existe caminho de API que converte esta violação em 400?" — e a resposta
era não para `Conta.codigo_unico_por_empresa` (contabilidade) e
`Estabelecimento.uma_matriz_por_empresa` (empresas), mesmo esta última
vivendo na MESMA função que já trata a unicidade do CNPJ:
`EstabelecimentoListCreateView.perform_create` já abre `with
transaction.atomic(), erro_de_cnpj_duplicado_como_400():` — a defesa
existe, e não cobre a constraint declarada quatro linhas abaixo no mesmo
`Meta`.

**Por que um módulo novo, e não generalizar `erro_de_cnpj_duplicado_
como_400`:** aquela função tem histórico próprio (achados A1/B1/R4 de
três rodadas anteriores), testes que dependem do formato exato de
`CNPJDuplicado` (`ValidationError` com `message_dict["cnpj"]`), e é
consumida por `criar_empresa` (view HTML, fora do escopo desta correção).
Reescrevê-la para generalizar arriscava esses três consumidores por um
ganho marginal. Este módulo cobre as constraints NOVAS com o mesmo
princípio (traduzir pelo nome da constraint, nunca por heurística de
mensagem), sem tocar no que já funciona.

Uso:

    try:
        with transaction.atomic(), restricao_como_400(
            {"codigo_unico_por_empresa": "Já existe uma conta com este código nesta empresa."}
        ):
            conta = serializer.save(empresa=empresa)
    except RestricaoViolada as exc:
        raise DRFValidationError(str(exc)) from exc

`transaction.atomic()` fica por fora, a cargo de quem chama — é o
savepoint que isola o `IntegrityError` para a conexão continuar utilizável
depois (mesmo desenho de `erro_de_cnpj_duplicado_como_400`).
"""

from contextlib import contextmanager

from django.db import IntegrityError


class RestricaoViolada(Exception):
    """Levantada quando uma `IntegrityError` corresponde a uma das
    constraints mapeadas em `restricao_como_400`. A mensagem já é a
    mensagem de negócio pronta para o cliente (não o texto cru do banco)."""


def _nome_da_constraint_violada(exc):
    """Extrai o nome da constraint de banco que causou `exc`, via o
    diagnóstico do driver (psycopg) — mesmo mecanismo de
    `apps.empresas.services.mensagem_se_cnpj_duplicado`. Devolve `None`
    quando não há diagnóstico (driver diferente, ou erro sem constraint
    nomeada) — quem chama trata isso como "não é uma das constraints
    mapeadas" e deixa o erro original subir.
    """
    diagnostico = getattr(exc.__cause__, "diag", None)
    return getattr(diagnostico, "constraint_name", None)


@contextmanager
def restricao_como_400(mapa_constraint_para_mensagem):
    """Traduz `IntegrityError` de uma constraint MAPEADA em `RestricaoViolada`.

    `mapa_constraint_para_mensagem` é um `dict` `{nome_da_constraint:
    mensagem_de_negocio}`. Só a(s) constraint(s) nomeadas no mapa são
    traduzidas; qualquer outra `IntegrityError` sobe SEM tradução — nunca
    converter toda `IntegrityError` em erro de cliente (a mesma instrução
    que rege `erro_de_cnpj_duplicado_como_400` e
    `criar_lancamento`/`estornar_lancamento`: um `IntegrityError` de
    origem desconhecida pode ser defeito de sistema, não erro do cliente,
    e mascará-lo como 400 esconde o defeito de quem monitora 500 — decisão
    revista depois de um erro parecido na DL-007).
    """
    try:
        yield
    except IntegrityError as exc:
        nome_constraint = _nome_da_constraint_violada(exc)
        mensagem = mapa_constraint_para_mensagem.get(nome_constraint)
        if mensagem is None:
            raise
        raise RestricaoViolada(mensagem) from exc
