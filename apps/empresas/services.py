from contextlib import contextmanager
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario

# Nome real da constraint de unicidade de cnpj no Postgres (confirmado via
# pg_constraint), mapeado ao modelo correspondente. Usado para traduzir a
# corrida na unicidade do CNPJ (R4 da reauditoria da etapa DL-011: duas
# requisições simultâneas com o mesmo CNPJ, a segunda comita entre o SELECT
# do UniqueValidator/validate_unique e o INSERT) em mensagem de campo, em
# vez de deixar o IntegrityError subir como 500.
_CONSTRAINTS_CNPJ_UNICO = {
    "empresas_empresa_cnpj_key": Empresa,
    "empresas_estabelecimento_cnpj_key": Estabelecimento,
}


def mensagem_cnpj_duplicado(model):
    """Mensagem de duplicidade de CNPJ, no mesmo formato que o DRF geraria
    para um UniqueValidator automático (usa o verbose_name do modelo, para
    não hardcodear "empresa"/"estabelecimento" em dois lugares)."""
    return f"{model._meta.verbose_name} com este CNPJ já existe."


class CNPJDuplicado(ValidationError):
    """CNPJ já cadastrado, detectado pela corrida na constraint de unicidade.

    Achado B1 da auditoria da etapa DL-011 (rodada 4): o gerenciador
    ``erro_de_cnpj_duplicado_como_400`` levantava ``ValidationError`` do
    Django puro, e as quatro views capturavam esse tipo genérico — largo
    demais. ``Empresa.save()``/``Estabelecimento.save()`` também levantam
    ``ValidationError`` (de ``normalizar_cnpj``, quando o valor é inválido),
    só que com **mensagem simples**, sem ``error_dict``. Como o
    ``except ValidationError`` das views sempre chamava
    ``exc.message_dict`` — que só existe quando o ``ValidationError`` foi
    construído com um dict —, uma ``ValidationError`` de mensagem vinda de
    ``save()`` (ou de um *signal*, ou de uma regra futura) virava
    ``AttributeError`` sem tratamento (500 escondendo a causa raiz no log),
    e na tela virava **200 sem nenhum erro no formulário e nada gravado** —
    falha convertida em sucesso aparente, o que o AGENTS.md §8 proíbe.

    A correção é estreitar o contrato, não alargar o ``except``: só esta
    subclasse — que o gerenciador constrói sempre com dict, garantindo
    ``message_dict`` — é capturada pelas views. Qualquer outra
    ``ValidationError`` (de ``save()``, de *signal*, de regra nova) sobe
    intacta, com a causa legível.
    """


def mensagem_se_cnpj_duplicado(exc):
    """Traduz um IntegrityError de corrida na unicidade do CNPJ.

    Devolve a mensagem amigável se `exc` for exatamente a violação da
    constraint de unicidade de cnpj de Empresa ou Estabelecimento; devolve
    None para qualquer outro IntegrityError. Quem chamar DEVE deixar
    qualquer outro IntegrityError subir sem tratamento — não converter todo
    IntegrityError em erro de cliente (instrução explícita do
    `arquiteto-senior` na reauditoria, depois de um erro parecido na
    DL-007: aquilo mascarou defeito de sistema como erro 400 do cliente).
    """
    diagnostico = getattr(exc.__cause__, "diag", None)
    nome_constraint = getattr(diagnostico, "constraint_name", None)
    modelo = _CONSTRAINTS_CNPJ_UNICO.get(nome_constraint)
    if modelo is None:
        return None
    return mensagem_cnpj_duplicado(modelo)


@contextmanager
def erro_de_cnpj_duplicado_como_400():
    """Traduz a corrida na unicidade do CNPJ num erro de campo, não um 500.

    Achado A1 da reauditoria da etapa DL-011 (rodada 3): o tratamento de
    ``IntegrityError`` do R4 tinha sido escrito três vezes (criação de
    Empresa e de Estabelecimento pela API, criação pela tela) e faltou a
    quarta — atualização de Empresa (``PUT``/``PATCH``), reproduzida pelo
    auditor em 6 de 6 execuções com duas *threads*. Bloco repetido é bloco
    esquecido na próxima vez; por isso a lógica de detecção mora só aqui.

    Uso: ``with transaction.atomic(), erro_de_cnpj_duplicado_como_400():
    <gravação>``. O ``transaction.atomic()`` fica por fora, a cargo de quem
    chama — é o savepoint que isola o ``IntegrityError`` para a conexão
    continuar utilizável depois (para o ``registrar()`` de auditoria, por
    exemplo), e não é papel deste gerenciador abrir transação.

    Levanta ``CNPJDuplicado({"cnpj": [mensagem]})`` — subclasse de
    ``django.core.exceptions.ValidationError``, sempre construída com dict
    (achado B1 da auditoria, rodada 4: capturar o ``ValidationError``
    genérico nas views era largo demais, porque ``Model.save()`` também
    levanta ``ValidationError``, só que de mensagem simples — ver a
    docstring de ``CNPJDuplicado``). Os dois caminhos que usam isto (API e
    formulário da tela) sabem traduzir esse tipo para o formato de erro
    certo, e só ele — nunca o ``ValidationError`` genérico, que deve subir
    intacto para quem chamou perceber a causa real.

    Só a violação das constraints ``empresas_empresa_cnpj_key`` /
    ``empresas_estabelecimento_cnpj_key`` é traduzida
    (``mensagem_se_cnpj_duplicado`` devolve ``None`` para qualquer outra
    causa, e este gerenciador deixa o ``IntegrityError`` original subir sem
    tradução nesse caso) — não repetir o erro da DL-007, que converteu todo
    ``IntegrityError`` em erro de cliente e mascarou defeito de sistema.
    """
    try:
        yield
    except IntegrityError as exc:
        mensagem = mensagem_se_cnpj_duplicado(exc)
        if mensagem is None:
            raise
        raise CNPJDuplicado({"cnpj": [mensagem]}) from exc


@transaction.atomic
def registrar_regime_tributario(empresa, regime, vigencia_inicio):
    """Registra um novo período de regime tributário para a empresa.

    Fecha automaticamente o período vigente anterior (vigencia_fim nulo),
    definindo seu fim como o dia anterior ao novo início. Nunca edita o
    valor do regime de um período já existente — preserva o histórico
    necessário para reproduzir apurações antigas.
    """
    periodo_vigente = (
        HistoricoRegimeTributario.objects.select_for_update()
        .filter(empresa=empresa, vigencia_fim__isnull=True)
        .first()
    )
    if periodo_vigente is not None:
        if vigencia_inicio <= periodo_vigente.vigencia_inicio:
            raise ValueError(
                "A nova vigência deve começar depois do início do período vigente atual."
            )
        periodo_vigente.vigencia_fim = vigencia_inicio - timedelta(days=1)
        periodo_vigente.save(update_fields=["vigencia_fim"])

    return HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=regime, vigencia_inicio=vigencia_inicio
    )
