from contextlib import contextmanager
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario
from apps.empresas.validators import mensagem_de_vigencia_de_regime_fora_da_faixa

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

    Faixa de `vigencia_inicio` (BL-200, achado R6-6): teto em HOJE, regra
    confirmada (RC-85); piso em 01/01/2000, **hipótese declarada** (HI-07).
    Ver o comentário em `apps.empresas.validators`, que é a fonte única da
    faixa e da mensagem — este serviço só traduz para `ValueError`, que é o
    que a API já converte em 400.
    """
    mensagem = mensagem_de_vigencia_de_regime_fora_da_faixa(vigencia_inicio)
    if mensagem is not None:
        raise ValueError(mensagem)

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

    # DL-023, critério 8 (concorrência, BL-211/A2): quando `periodo_vigente`
    # é `None` para DUAS requisições concorrentes (nenhuma linha existe
    # ainda para o `select_for_update()` travar), as duas passam pela
    # checagem acima e as duas tentam criar. A `UniqueConstraint`
    # "um_periodo_de_regime_aberto_por_empresa" (Meta de
    # HistoricoRegimeTributario) garante que só UMA das duas grava; a outra
    # recebe `IntegrityError` aqui. Sem tradução, isso subiria cru: a view
    # só captura `ValueError` (apps/empresas/views.py), e o cliente
    # concorrente perdedor receberia 500 — exatamente a classe de defeito
    # que a BL-144 existe para impedir ("nenhuma violação de invariante
    # chega ao cliente como 5xx"). `transaction.atomic()` aqui dentro cria
    # um SAVEPOINT (a função inteira já está em `@transaction.atomic`): o
    # `IntegrityError` propagado FORA deste bloco interno só desfaz o
    # savepoint, não a transação inteira, e a conexão continua utilizável
    # depois — mesmo desenho de `erro_de_cnpj_duplicado_como_400`.
    try:
        with transaction.atomic():
            return HistoricoRegimeTributario.objects.create(
                empresa=empresa, regime=regime, vigencia_inicio=vigencia_inicio
            )
    except IntegrityError as exc:
        nome_constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if nome_constraint != "um_periodo_de_regime_aberto_por_empresa":
            raise
        raise ValueError(
            "Esta empresa já tem um período de regime tributário aberto, criado por "
            "outra requisição ao mesmo tempo. Recarregue e confira o regime atual "
            "antes de tentar de novo."
        ) from exc


class ExclusaoDeRegimeInvalida(Exception):
    """Levantada quando a exclusão pedida não é a do ÚLTIMO período.

    Tipo próprio, e não `ValueError`, por um motivo de contrato: quem chama
    precisa distinguir "esta exclusão é proibida por regra" (400, com
    mensagem útil ao contador) de qualquer outro `ValueError` que possa vir
    de outro lugar da pilha. `registrar_regime_tributario` usa `ValueError`
    por história — não repetir a escolha em código novo.
    """


@transaction.atomic
def excluir_ultimo_regime_tributario(*, empresa, registro, usuario=None, request=None):
    """Apaga o ÚLTIMO período de regime tributário da empresa (RC-86/DE-039).

    Contexto, porque a escolha aqui não é técnica e não é minha: o achado
    R6-6 mostrou que um dígito errado em `vigencia_inicio` deixava a empresa
    **sem nenhum caminho de correção pelo produto**. O Fred decidiu, em
    2026-09-15, que a correção **apaga** o registro errado (RC-86) — contra a
    recomendação do `arquiteto-senior` de registrar uma correção no molde do
    estorno. Regime tributário é dado **cadastral**, não escrituração.

    A fronteira, que é o que impede esta decisão de contaminar o resto
    (DE-039): isto vale para CADASTRO. **Não** se estende a lançamento
    contábil efetivado — ali a correção segue por estorno rastreável e
    apagar continua proibido (`LancamentoImutavelError`, em
    `apps.contabilidade.models`). O teste da fronteira é a pergunta "isto é
    escrituração?"; se for, não se apaga.

    Três garantias, todas do alcance técnico fixado na DE-039:

    1. **Só o último período** — o que não tem sucessor. Apagar um período do
       meio abriria buraco na linha do tempo: o antecessor já teve a
       `vigencia_fim` recortada para o dia anterior ao sucessor, e sem o
       sucessor aquele intervalo fica **sem regime nenhum**. Empresa sem
       regime numa competência é pior que empresa com regime errado, porque a
       apuração não tem nem o que conferir. Pedido assim é RECUSADO
       (`ExclusaoDeRegimeInvalida`), nunca executado.
    2. **O período anterior volta a ser vigente** — a `vigencia_fim` recortada
       volta a `None`. Sem isso, apagar deixaria a empresa sem regime
       corrente, que é exatamente o estado que a exclusão existe para
       consertar. É o ponto onde o defeito silencioso mora: sem esta linha,
       tudo "funciona" e a empresa fica sem regime vigente sem nada acusar.
    3. **O evento é gravado em `RegistroAuditoria`**, com os valores antigos e
       o autor. Isto **não** contraria o "apagar" do Fred, e a distinção foi
       apresentada a ele e confirmada ("Concordo com você", 2026-09-15): o
       **registro** sai do histórico do produto — nenhuma tela, relatório ou
       apuração volta a ver aquele período —, e o que fica é a **trilha
       técnica**, que o `AGENTS.md` torna obrigatória ("trilha de auditoria
       protegida, suficiente") e que não é dispensável por pedido. Ele
       escolheu o que o produto mostra, não o que o log guarda.

    `select_for_update()` sobre TODOS os períodos da empresa: duas exclusões
    simultâneas do mesmo último período não podem as duas passar pela
    checagem "este é o último" antes de qualquer gravação, e a reabertura da
    `vigencia_fim` do anterior precisa da linha travada.

    Devolve o `dict` com os valores do período apagado (já em texto, como
    foram para a trilha), porque depois do `delete()` o objeto não é mais
    fonte confiável — quem chama monta a resposta a partir dele.
    """
    periodos = list(
        HistoricoRegimeTributario.objects.select_for_update()
        .filter(empresa=empresa)
        .order_by("-vigencia_inicio", "-id")
    )
    if not periodos:
        raise ExclusaoDeRegimeInvalida("Esta empresa não tem regime tributário registrado.")

    ultimo = periodos[0]
    if registro.pk != ultimo.pk:
        raise ExclusaoDeRegimeInvalida(
            "Só o último período de regime tributário pode ser apagado. O período "
            f"de {registro.vigencia_inicio.strftime('%d/%m/%Y')} tem um período "
            f"posterior ({ultimo.vigencia_inicio.strftime('%d/%m/%Y')}), e apagá-lo "
            "deixaria a empresa sem regime nenhum no intervalo entre os dois. "
            "Apague primeiro o período mais recente."
        )

    valores_antigos = {
        "id": ultimo.pk,
        "empresa_id": empresa.pk,
        "regime": ultimo.regime,
        "vigencia_inicio": ultimo.vigencia_inicio.isoformat(),
        "vigencia_fim": ultimo.vigencia_fim.isoformat() if ultimo.vigencia_fim else None,
    }

    anterior = periodos[1] if len(periodos) > 1 else None
    if anterior is not None:
        # Garantia 2 da DE-039. `vigencia_fim` do anterior foi recortada por
        # `registrar_regime_tributario` quando o período agora apagado
        # entrou; desfazer o recorte é o que devolve a empresa a um estado
        # consistente. Guardamos o valor anterior na trilha para que o
        # evento seja reconstituível.
        valores_antigos["vigencia_fim_reaberta_do_periodo_anterior"] = (
            anterior.vigencia_fim.isoformat() if anterior.vigencia_fim else None
        )

    # `registrar()` ANTES do `delete()`: depois da exclusão o `pk` da
    # instância é `None`, e a trilha registraria um objeto sem identificação.
    registrar(
        acao="regime_tributario.excluido",
        objeto=ultimo,
        usuario=usuario,
        request=request,
        detalhes=valores_antigos,
    )

    # DL-023, critério 1 (efeito colateral da UniqueConstraint "um_periodo_
    # de_regime_aberto_por_empresa"): `ultimo` (o período apagado) e
    # `anterior` (o período que volta a vigente) têm os DOIS
    # `vigencia_fim IS NULL` no instante entre "reabrir o anterior" e
    # "apagar o último" — se a reabertura acontecesse ANTES da exclusão,
    # as duas linhas violariam a constraint ao mesmo tempo (medido: a
    # suíte reprovava aqui, `IntegrityError` na própria exclusão, depois
    # de a constraint entrar). A ORDEM que evita a violação é apagar
    # PRIMEIRO — assim nunca existem duas linhas abertas na mesma
    # transação — e só depois reabrir o anterior. A trilha já foi gravada
    # acima com os valores corretos, então a ordem de escrita no banco não
    # muda o que fica registrado.
    ultimo.delete()
    if anterior is not None:
        anterior.vigencia_fim = None
        anterior.save(update_fields=["vigencia_fim"])
    return valores_antigos
