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
    demais, porque ``Empresa.save()``/``Estabelecimento.save()`` também
    levantam ``ValidationError`` (de ``normalizar_cnpj``, quando o valor é
    inválido), só que fora do formato que o ``except`` esperava. Dois
    sintomas distintos, cada um numa forma diferente de ``ValidationError``
    que o ``except`` largo capturava sem distinguir:

    - **Mensagem simples** (``ValidationError("texto")``, sem ``error_dict``):
      o ``except`` chamava ``exc.message_dict`` incondicionalmente — que só
      existe na forma construída com dict —, e isso estourava
      ``AttributeError`` sem tratamento (500 escondendo a causa raiz no
      log, em vez do ``ValidationError`` original).
    - **Dict sem a chave ``"cnpj"``** (ex.: ``ValidationError({"razao_social":
      [...]})``, de uma regra de negócio futura): na tela,
      ``exc.message_dict.get("cnpj", [])`` devolvia lista vazia, o laço não
      adicionava erro nenhum, e a view devolvia **200 sem nenhum erro no
      formulário e nada gravado** — falha convertida em sucesso aparente,
      o que o AGENTS.md §8 proíbe.

    A correção é estreitar o contrato, não alargar o ``except``: só esta
    subclasse — que o gerenciador constrói sempre com dict, garantindo
    ``message_dict`` e a chave ``"cnpj"`` — é capturada pelas views.
    Qualquer outra ``ValidationError`` (de ``save()``, de *signal*, de
    regra nova, em qualquer uma das duas formas acima) sobe intacta, com a
    causa legível. Ver ``erro_de_cnpj_duplicado_como_400`` para onde e como
    esta exceção é levantada.
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

    Levanta ``CNPJDuplicado({"cnpj": [mensagem]})`` — sempre com dict, nunca
    o ``ValidationError`` genérico. Ver a docstring de ``CNPJDuplicado``
    para o porquê: capturar o tipo genérico nas views era largo demais e
    causava dois sintomas distintos (500 opaco e 200 silencioso) quando
    ``Model.save()`` levantava sua própria ``ValidationError`` por outro
    motivo. Os dois caminhos que usam isto (API e formulário da tela) sabem
    traduzir só o tipo estreito para o formato de erro certo.

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
