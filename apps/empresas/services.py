from datetime import timedelta

from django.db import transaction

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
