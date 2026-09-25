from contextlib import contextmanager
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.auditoria.services import registrar
from apps.empresas.models import (
    Empresa,
    Estabelecimento,
    HistoricoRegimeTributario,
    ModoEscrituracao,
    TipoInscricao,
)
from apps.empresas.validators import mensagem_de_vigencia_de_regime_fora_da_faixa

# Nome real da constraint de unicidade no Postgres, mapeado a
# (modelo, nome do campo, rótulo humano). Usado para traduzir a corrida na
# unicidade de CNPJ/CPF (R4 da reauditoria da etapa DL-011: duas requisições
# simultâneas com o mesmo identificador, a segunda comita entre o SELECT do
# UniqueValidator/validate_unique e o INSERT) em mensagem de campo, em vez
# de deixar o IntegrityError subir como 500.
#
# DL-038: `empresas_empresa_cnpj_key` (índice implícito de `unique=True` de
# campo) foi SUBSTITUÍDO por `empresa_cnpj_unico` (UniqueConstraint
# condicional — ver apps/empresas/models.py) porque a unicidade do CNPJ de
# `Empresa` deixou de poder ser incondicional: duas empresas CPF têm
# `cnpj == ""` e isso NUNCA pode contar como duplicata. `empresa_cpf_unico`
# é a entrada nova, simétrica, para CPF (R3/PE-21: mesma política GLOBAL do
# CNPJ). `empresas_estabelecimento_cnpj_key` não muda — `Estabelecimento`
# continua exclusivamente CNPJ (R7).
_CONSTRAINTS_INSCRICAO_UNICA = {
    "empresa_cnpj_unico": (Empresa, "cnpj", "CNPJ"),
    "empresas_estabelecimento_cnpj_key": (Estabelecimento, "cnpj", "CNPJ"),
    "empresa_cpf_unico": (Empresa, "cpf", "CPF"),
}


def modo_escrituracao_sugerido(tipo_inscricao):
    """HI-23 (hipótese registrada em `docs/projeto/requisitos.md`, NÃO
    confirmada pelo Fred): nova empresa CPF SUGERE o modo livro-caixa; o
    usuário pode trocar. FONTE ÚNICA da sugestão — achado B5 da auditoria
    rodada 1: antes desta função, a sugestão só existia em `EmpresaForm.
    clean()` (apps/empresas/forms.py); a API sempre assumia `contabilidade`
    para QUALQUER tipo quando `modo_escrituracao` vinha omitido — o MESMO
    pedido ("CPF sem modo") dava `livro_caixa` pela tela e `contabilidade`
    pela API, o oposto do objetivo 3 do plano DL-038 ("a contabilidade por
    partidas dobradas não seja aplicada por engano a quem escritura
    livro-caixa"). Chamada por `EmpresaForm.clean()` (tela) e por
    `EmpresaSerializer` (API, apps/empresas/serializers.py) — nenhum dos
    dois reimplementa a condição.

    É só a SUGESTÃO do valor-padrão quando `modo_escrituracao` vem OMITIDO
    — uma escolha EXPLÍCITA do cliente (mesmo que igual à sugestão) nunca
    passa por aqui; quem chama só usa o resultado quando o campo estiver
    ausente/vazio no envio.
    """
    return (
        ModoEscrituracao.LIVRO_CAIXA
        if tipo_inscricao == TipoInscricao.CPF
        else ModoEscrituracao.CONTABILIDADE
    )


def erros_de_consistencia_de_inscricao(tipo_inscricao, cnpj, cpf):
    """Consistência CRUZADA entre `tipo_inscricao`, `cnpj` e `cpf` — a MESMA
    invariante que a `CheckConstraint` "empresa_inscricao_consistente_com_
    tipo" (apps/empresas/models.py) garante no banco (camada 1 da DE-008).
    FONTE ÚNICA desta regra em Python: chamada por `EmpresaSerializer.
    validate` (API, apps/empresas/serializers.py) e por `EmpresaAdminForm.
    clean` (admin, apps/empresas/admin.py) — nenhum dos dois reimplementa a
    comparação (achado B1 da auditoria rodada 1: antes desta função, só a
    API tinha a checagem em Python; o admin dependia de `Model.
    validate_constraints()`, que virou no-op nesta mesma etapa por outro
    motivo — ver o comentário em `Empresa.validate_constraints` — e por
    isso um `tipo_inscricao=CPF` com os dois campos preenchidos batia
    direto na `CheckConstraint` do banco, sem mensagem por campo: 500).

    Devolve um `dict {campo: mensagem}` — vazio quando está tudo
    consistente. Nunca levanta: quem chama decide o tipo de exceção (DRF
    ou `forms.ValidationError`).
    """
    if tipo_inscricao == TipoInscricao.CNPJ:
        erros = {}
        if not cnpj:
            erros["cnpj"] = "CNPJ é obrigatório quando o tipo de inscrição é CNPJ."
        if cpf:
            erros["cpf"] = "CPF não pode ser informado quando o tipo de inscrição é CNPJ."
        return erros
    if tipo_inscricao == TipoInscricao.CPF:
        erros = {}
        if not cpf:
            erros["cpf"] = "CPF é obrigatório quando o tipo de inscrição é CPF."
        if cnpj:
            erros["cnpj"] = "CNPJ não pode ser informado quando o tipo de inscrição é CPF."
        return erros
    return {}


def mensagem_cnpj_duplicado(model, rotulo="CNPJ"):
    """Mensagem de duplicidade de CNPJ/CPF, no mesmo formato que o DRF
    geraria para um UniqueValidator automático (usa o verbose_name do
    modelo, para não hardcodear "empresa"/"estabelecimento" em dois
    lugares). `rotulo` é "CNPJ" por padrão (compatibilidade com os dois
    chamadores existentes, que só tratam CNPJ) — DL-038 passa "CPF" para
    o caso novo."""
    return f"{model._meta.verbose_name} com este {rotulo} já existe."


class CNPJDuplicado(ValidationError):
    """CNPJ **ou CPF** já cadastrado, detectado pela corrida na constraint
    de unicidade. Nome da classe preservado por compatibilidade — é
    consumida por várias views que só a reconhecem por este nome — mas
    DL-038 estendeu a causa: a chave do dict pode ser ``"cnpj"`` OU
    ``"cpf"``, dependendo de qual constraint colidiu (ver
    ``mensagem_se_cnpj_duplicado``). Quem captura esta exceção já reencaminha
    ``exc.message_dict`` inteiro (nunca lê a chave "cnpj" por presunção), e
    por isso nenhuma view precisou mudar para o caso do CPF.

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
    """Traduz um IntegrityError de corrida na unicidade do CNPJ **ou CPF**.

    Devolve `(campo, mensagem)` — `campo` é `"cnpj"` ou `"cpf"`, o nome que
    vai virar chave do dict de erro — se `exc` for exatamente a violação de
    uma das constraints de `_CONSTRAINTS_INSCRICAO_UNICA`; devolve
    `(None, None)` para qualquer outro IntegrityError. Quem chamar DEVE
    deixar qualquer outro IntegrityError subir sem tratamento — não
    converter todo IntegrityError em erro de cliente (instrução explícita
    do `arquiteto-senior` na reauditoria, depois de um erro parecido na
    DL-007: aquilo mascarou defeito de sistema como erro 400 do cliente).
    """
    diagnostico = getattr(exc.__cause__, "diag", None)
    nome_constraint = getattr(diagnostico, "constraint_name", None)
    info = _CONSTRAINTS_INSCRICAO_UNICA.get(nome_constraint)
    if info is None:
        return None, None
    modelo, campo, rotulo = info
    return campo, mensagem_cnpj_duplicado(modelo, rotulo)


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

    Só a violação das constraints de ``_CONSTRAINTS_INSCRICAO_UNICA``
    (``empresa_cnpj_unico``, ``empresa_cpf_unico``,
    ``empresas_estabelecimento_cnpj_key``) é traduzida
    (``mensagem_se_cnpj_duplicado`` devolve ``(None, None)`` para qualquer
    outra causa, e este gerenciador deixa o ``IntegrityError`` original
    subir sem tradução nesse caso) — não repetir o erro da DL-007, que
    converteu todo ``IntegrityError`` em erro de cliente e mascarou defeito
    de sistema.
    """
    try:
        yield
    except IntegrityError as exc:
        campo, mensagem = mensagem_se_cnpj_duplicado(exc)
        if mensagem is None:
            raise
        raise CNPJDuplicado({campo: [mensagem]}) from exc


# DL-023, BL-246 (achado P2 da auditoria rodada 1): nome da constraint que
# governa "no máximo um período de regime aberto por empresa" (Meta de
# HistoricoRegimeTributario, apps/empresas/models.py). Ponto ÚNICO de onde
# esse nome é comparado — antes da rodada 2, `registrar_regime_tributario`
# tinha essa comparação embutida no próprio corpo, e
# `excluir_ultimo_regime_tributario` não tinha NENHUMA: o `DELETE` de um
# regime, concorrente com um `POST` que abre outro período, reabre o
# período anterior bem no instante em que o `POST` concorrente já comitou
# a linha nova — as duas ficam com `vigencia_fim IS NULL` ao mesmo tempo, a
# constraint recusa, e o `IntegrityError` subia CRU (500), porque a
# exclusão só capturava `ExclusaoDeRegimeInvalida`. Medido pelo auditor: 6
# de 8 execuções de 3 `POST` + 3 `DELETE` simultâneos devolviam 500.
_NOME_CONSTRAINT_PERIODO_UNICO = "um_periodo_de_regime_aberto_por_empresa"


def _e_violacao_de_periodo_unico(exc):
    """`True` quando `exc` (um `IntegrityError`) é a violação da
    `UniqueConstraint` acima — usada pelos DOIS caminhos de escrita que
    podem colidir com ela (`registrar_regime_tributario` e
    `excluir_ultimo_regime_tributario`), para que a tradução seja um
    PONTO ÚNICO, não uma cópia colada em cada caminho (é essa cópia que
    faltou na exclusão e produziu o P2)."""
    nome_constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
    return nome_constraint == _NOME_CONSTRAINT_PERIODO_UNICO


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
        if not _e_violacao_de_periodo_unico(exc):
            raise
        raise ValueError(
            "Esta empresa já tem um período de regime tributário aberto, criado por "
            "outra requisição ao mesmo tempo. Recarregue e confira o regime atual "
            "antes de tentar de novo."
        ) from exc


class ExclusaoDeRegimeInvalida(Exception):
    """Levantada quando a exclusão pedida não pode ser concluída como
    negócio — duas causas, as duas convertidas para 400 por
    `HistoricoRegimeTributarioDetailView.delete` (apps/empresas/views.py),
    que já captura este tipo:

    1. A exclusão pedida não é a do ÚLTIMO período (regra original,
       RC-86/DE-039).
    2. **BL-246 (achado P2, auditoria DL-023 rodada 1):** a reabertura do
       período ANTERIOR colidiu, sob concorrência, com um `POST` que abriu
       outro período para a mesma empresa ao mesmo tempo — violação da
       `UniqueConstraint` "um_periodo_de_regime_aberto_por_empresa"
       traduzida por `_e_violacao_de_periodo_unico`. Reaproveitar este
       tipo (em vez de um novo) é o que permite corrigir o 500 sem tocar
       em `apps/empresas/views.py`: a view já sabe traduzir este tipo para
       400, e nenhuma view nova precisa aprender a fazer isso.

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
        # BL-246 (achado P2, auditoria DL-023 rodada 1): mesmo com a ORDEM
        # corrigida acima, esta linha ainda pode colidir com a constraint
        # sob CONCORRÊNCIA — não com `ultimo` (já apagado nesta mesma
        # transação), mas com um `POST` concorrente que abriu um período
        # NOVO para a mesma empresa. O `select_for_update()` do início
        # desta função trava as linhas que EXISTIAM no momento da consulta;
        # a linha nova do `POST` concorrente não existia ainda (ou não é
        # alcançada pelo lock), então esta transação segue sem saber dela
        # até tentar o UPDATE abaixo. Medido pelo auditor: 6 de 8 execuções
        # de 3 POST + 3 DELETE simultâneos devolviam 500 aqui, porque este
        # `IntegrityError` subia cru — a exclusão só capturava
        # `ExclusaoDeRegimeInvalida`.
        #
        # `transaction.atomic()` aqui dentro cria um SAVEPOINT (a função
        # inteira já está em `@transaction.atomic`, e há um `delete()` e um
        # `registrar()` já executados nesta transação que não podem virar
        # savepoint quebrado): o `IntegrityError` propagado FORA deste
        # bloco interno desfaz só o savepoint. Mas como o que se propaga
        # DAQUI é `ExclusaoDeRegimeInvalida` — não mais o `IntegrityError`
        # —, a exceção sobe para FORA do `@transaction.atomic` da função
        # inteira, e o Django reverte a transação por completo: o
        # `ultimo.delete()` e o `registrar()` de auditoria voltam atrás
        # junto. É o comportamento correto — a exclusão inteira falhou, não
        # só a reabertura —, e é o mesmo padrão já medido pelo auditor
        # ("trilha sob falha induzida no meio": atômico, sem trilha parcial).
        try:
            with transaction.atomic():
                anterior.vigencia_fim = None
                anterior.save(update_fields=["vigencia_fim"])
        except IntegrityError as exc:
            if not _e_violacao_de_periodo_unico(exc):
                raise
            raise ExclusaoDeRegimeInvalida(
                "Não foi possível concluir a exclusão: outra requisição abriu um "
                "novo período de regime tributário para esta empresa ao mesmo "
                "tempo. Nada foi alterado — recarregue e confira o regime atual "
                "antes de tentar de novo."
            ) from exc
    return valores_antigos


# ---------------------------------------------------------------------------
# DL-038 (R5, DE-075): a contabilidade por partidas dobradas recusa empresa
# em modo livro-caixa — FONTE ÚNICA da condição e da mensagem, para que
# toda rota de contabilidade (tela e API) chame a MESMA função no ponto em
# que resolve a empresa escopada, em vez de cada rota reimplementar a
# comparação `modo_escrituracao == LIVRO_CAIXA` com seu próprio texto (o
# defeito que o critério 4 do plano existe para impedir: duas mensagens
# diferentes para o mesmo motivo de recusa).
# ---------------------------------------------------------------------------

MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA = (
    "Esta empresa está em modo de escrituração livro-caixa, não contabilidade "
    "por partidas dobradas. A contabilidade não está disponível para ela."
)


class EmpresaEmModoLivroCaixa(Exception):
    """Levantada por `recusar_se_livro_caixa` quando a empresa está em modo
    `livro_caixa` — ver o comentário da seção acima para o porquê de ser um
    tipo próprio (não `ValueError` nem `ValidationError`): os DOIS
    consumidores (mixin de API em `apps.contabilidade.views`, decorador de
    tela em `apps.contabilidade.views_web`) precisam de tratamentos de HTTP
    diferentes (400 JSON vs. HTML renderizado), e um tipo estreito e
    próprio deixa cada lado traduzir sem arriscar capturar por engano outra
    exceção de negócio que também herdasse de `ValueError`/`ValidationError`.
    """

    def __init__(self, mensagem=MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA):
        self.mensagem = mensagem
        super().__init__(mensagem)


def recusar_se_livro_caixa(empresa):
    """Levanta `EmpresaEmModoLivroCaixa` se `empresa.modo_escrituracao` for
    `LIVRO_CAIXA` (R5). Não faz nada (devolve `None`) caso contrário —
    quem chama só precisa saber que "não levantou nada" é o caminho livre.
    """
    if empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA:
        raise EmpresaEmModoLivroCaixa()


# ---------------------------------------------------------------------------
# DL-038 (R6): não é possível mudar uma empresa PARA modo livro-caixa se ela
# já tem plano de contas ou lançamento contábil gravado — mudaria o
# significado da escrituração já feita sob a premissa de partidas dobradas,
# sem nenhum registro do porquê. FONTE ÚNICA da condição e da mensagem,
# consumida por `Empresa.clean()` (defesa para ModelForm/admin, DE-008) E
# por `EmpresaSerializer.validate` (o caminho que a API realmente usa) —
# nenhum dos dois reimplementa a comparação.
# ---------------------------------------------------------------------------


class TransicaoParaLivroCaixaInvalida(ValidationError):
    """R6/DL-038: empresa com plano de contas ou lançamento não pode passar
    para modo livro-caixa. Subclasse de `django.core.exceptions.
    ValidationError` (não um tipo próprio) de propósito: `Empresa.clean()`
    precisa poder deixá-la propagar sem tradução nenhuma — é exatamente o
    contrato que `full_clean()` exige de uma exceção de validação de
    modelo. `EmpresaSerializer.validate` já sabe traduzir qualquer
    `ValidationError` do Django para o formato do DRF (ver o padrão já
    usado por `mensagem_de_vigencia_de_regime_fora_da_faixa`)."""


def recusar_transicao_para_livro_caixa_com_movimento(empresa, *, modo_anterior, modo_novo):
    """Levanta `TransicaoParaLivroCaixaInvalida` se esta TRANSIÇÃO
    (`modo_anterior` -> `modo_novo`) for para `LIVRO_CAIXA` e a empresa já
    tiver plano de contas ou lançamento gravado.

    Só examina a TRANSIÇÃO, nunca o estado por si só: uma empresa que JÁ
    está em `LIVRO_CAIXA` (nenhuma mudança) ou que está migrando PARA
    `CONTABILIDADE` não aciona esta regra — o requisito R6 é especificamente
    sobre o momento em que a contabilidade por partidas dobradas deixaria
    de valer para um histórico que já existe sob essa premissa.
    """
    if modo_novo != ModoEscrituracao.LIVRO_CAIXA or modo_anterior == ModoEscrituracao.LIVRO_CAIXA:
        return
    if empresa.contas.exists() or empresa.lancamentos.exists():
        raise TransicaoParaLivroCaixaInvalida(
            "Não é possível mudar esta empresa para livro-caixa: ela já tem plano de "
            "contas ou lançamento contábil gravado. Empresas com escrituração "
            "existente permanecem em modo contabilidade."
        )


# ---------------------------------------------------------------------------
# DL-038 (R7), achado B2 da auditoria rodada 1: NIRE e ESTABELECIMENTO são
# conceitos de pessoa JURÍDICA — não fazem sentido para um cliente pessoa
# física (matriz/filial pressupõe CNPJ). Antes desta correção, a API criava
# `Estabelecimento` para qualquer `Empresa`, inclusive CPF, e o `PATCH` que
# trocava CNPJ->CPF não olhava se havia estabelecimento gravado; a medição
# do auditor: NFS-e com prestador igual ao CNPJ dessa filial entrava
# vinculada a uma "pessoa física" — o cadastro central ficava inconsistente
# e uma nota de CNPJ caía numa pessoa física. FONTE ÚNICA das duas regras
# abaixo, consumida pela API (`EstabelecimentoSerializer`/`EmpresaSerializer.
# validate`, apps/empresas/serializers.py) e pelo admin (`Estabelecimento.
# clean()`/`Empresa.clean()`, apps/empresas/models.py).
#
# Sem `CheckConstraint` de banco: Postgres não permite uma CHECK que
# consulte outra TABELA (o tipo mora em `Empresa`, o registro que a regra
# protege é `Estabelecimento`) — a defesa de banco possível aqui seria um
# TRIGGER, fora do padrão de constraint declarativa que o resto do projeto
# usa; fica como camada 2/3 da DE-008 (serviço + serializer/clean), não
# camada 1. Registrado, não escondido.
# ---------------------------------------------------------------------------


class EstabelecimentoParaEmpresaCPF(ValidationError):
    """R7/DL-038 (achado B2): `Estabelecimento` não pode existir para uma
    `Empresa` de `tipo_inscricao=CPF`. Subclasse de `ValidationError` (não
    um tipo próprio) — mesmo contrato de `TransicaoParaLivroCaixaInvalida`,
    para `Estabelecimento.clean()`/`Empresa.clean()` poderem propagar sem
    tradução, e `EstabelecimentoSerializer`/`EmpresaSerializer` traduzirem
    para o formato do DRF do mesmo jeito que já fazem para R6."""


def recusar_estabelecimento_para_empresa_cpf(empresa):
    """Levanta `EstabelecimentoParaEmpresaCPF` se `empresa.tipo_inscricao`
    for `CPF`. Chamada tanto na CRIAÇÃO de um `Estabelecimento` novo
    (API/admin) quanto — indiretamente, via `recusar_transicao_para_cpf_
    com_estabelecimento` — na TROCA de tipo de uma empresa que já tem
    estabelecimento gravado.
    """
    if empresa.tipo_inscricao == TipoInscricao.CPF:
        raise EstabelecimentoParaEmpresaCPF(
            "Não é possível cadastrar estabelecimento (matriz/filial) para uma "
            "empresa do tipo CPF: NIRE e estabelecimento são exclusivos de pessoa "
            "jurídica (CNPJ)."
        )


def recusar_transicao_para_cpf_com_estabelecimento(empresa, *, tipo_anterior, tipo_novo):
    """Levanta `EstabelecimentoParaEmpresaCPF` se esta TRANSIÇÃO
    (`tipo_anterior` -> `tipo_novo`) for para `CPF` e a empresa já tiver
    `Estabelecimento` gravado (mesmo padrão de `recusar_transicao_para_
    livro_caixa_com_movimento`, R6: só examina a TRANSIÇÃO, nunca o estado
    por si só).
    """
    if tipo_novo != TipoInscricao.CPF or tipo_anterior == TipoInscricao.CPF:
        return
    if empresa.estabelecimentos.exists():
        raise EstabelecimentoParaEmpresaCPF(
            "Não é possível mudar esta empresa para CPF: ela já tem estabelecimento "
            "(matriz/filial) gravado. Exclua os estabelecimentos antes de trocar o "
            "tipo de inscrição."
        )
