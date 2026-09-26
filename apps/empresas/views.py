from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

# BL-217/A1 (auditoria DL-020 rodada 1): as views de FUNÇÃO deste módulo
# declaram os métodos HTTP que aceitam. É esta declaração — fato do objeto,
# não substring do fonte — que a varredura de contratos
# (`apps/core/tests/test_dl019_varredura_de_contratos.py`) lê para saber se a
# view é superfície de escrita. A classificação textual anterior
# (`"request.method" in fonte`) foi contornada pelo auditor com uma view que
# grava lendo `json.loads(request.body)`, com a suíte inteira verde.
from django.views.decorators.http import require_http_methods, require_safe
from rest_framework import generics
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.core.datas import DataInvalida, para_data
from apps.core.escolhas import EscolhaInvalida, para_escolha
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.core.restricoes import (
    RestricaoViolada,
    mensagens_de,
    mensagens_de_gatilho,
    restricao_como_400,
)
from apps.empresas.forms import EmpresaForm
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.empresas.models import (
    Empresa,
    Estabelecimento,
    HistoricoRegimeTributario,
    ModoEscrituracao,
    RegimeTributario,
    TipoInscricao,
)
from apps.empresas.serializers import (
    EmpresaSerializer,
    EstabelecimentoSerializer,
    HistoricoRegimeTributarioSerializer,
)
from apps.empresas.services import (
    CNPJDuplicado,
    EstabelecimentoParaEmpresaCPF,
    ExclusaoDeRegimeInvalida,
    InscricaoCruzadaEntreEmpresaEEstabelecimento,
    erro_de_cnpj_duplicado_como_400,
    excluir_ultimo_regime_tributario,
    recusar_cnpj_de_estabelecimento_igual_a_outra_empresa,
    recusar_estabelecimento_para_empresa_cpf,
    registrar_regime_tributario,
)
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo, papel_permitido

# Criação/alteração de cadastro é restrita a quem administra o escritório;
# consulta continua liberada a qualquer papel vinculado (ver get_permissions
# e as views de leitura, que só exigem TemEscritorioAtivo).
PodeGerenciarEmpresa = papel_permitido(Papel.ADMINISTRADOR, Papel.GESTOR)


# BL-196 / achado R6-2: a política dos cinco dicionários, aplicada às rotas
# de escrita deste app. Medido pelo auditor, todas devolvendo **201/200** com
# o dado ignorado em silêncio: querystring em POST; `empresa: 999` e `xpto`
# no corpo de estabelecimento e de regime tributário.
#
# `empresa` no corpo é o caso que mais engana: o vínculo real vem SEMPRE do
# escopo da URL, revalidado contra o escritório ativo
# (`EmpresaEscopadaMixin.get_empresa()`), então `empresa: 999` nunca vazou
# nada — mas quem o envia acredita ter escolhido a empresa, e ninguém dizia o
# contrário.
#
# Os campos vêm do serializer, só os GRAVÁVEIS (`read_only` fora): assim a
# lista não pode divergir do contrato real da rota, e `id`/`criado_em`/
# `regime_atual` — que o auditor mediu sendo aceitos e ignorados — ficam
# recusados por construção, sem lista literal para manter em dois lugares.
def _campos_gravaveis(serializer):
    return frozenset(nome for nome, campo in serializer.fields.items() if not campo.read_only)


def _diff_dos_campos_gravaveis(serializer, instance):
    """Devolve o diff entre o estado atual da `instance` e os valores
    submetidos pelo cliente, restrito aos campos graváveis do serializer.

    Retorna dois dicts alinhados por chave de campo:
    - `valores_anteriores`: valor que o campo tinha ANTES do save.
    - `valores_novos`: valor submetido pelo cliente.
    Só campos que MUDARAM aparecem nos dois dicts. Campos que o cliente
    não enviou (PATCH parcial) são ignorados — não há "mudança" a
    registrar.

    Os dicts são flat (mesma forma de `valores_antigos` em
    `excluir_ultimo_regime_tributario`, `apps/empresas/services.py:305`),
    não aninhados. O `registrar()` da BL-14 recebe o par direto.
    """
    valores_anteriores = {}
    valores_novos = {}
    gravaveis = _campos_gravaveis(serializer)
    for campo in gravaveis:
        if campo not in serializer.validated_data:
            # PATCH parcial não mencionou este campo — não há mudança
            # a registrar.
            continue
        novo = serializer.validated_data[campo]
        antigo = getattr(instance, campo)
        if novo != antigo:
            valores_anteriores[campo] = antigo
            valores_novos[campo] = novo
    return valores_anteriores, valores_novos


def _recusar_dado_nao_contratado(request, contrato):
    """Ponte única entre `apps.core.requisicao` (que julga) e o DRF (que
    responde) neste app — ver o módulo para o contrato completo."""
    try:
        recusar_dado_nao_contratado(request, contrato)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


# DL-038: qual campo do serializer cada `RestricaoViolada` de `Empresa`
# reporta — `RestricaoViolada.nome` é o nome da CONSTRAINT (nunca o texto
# da mensagem, que é conteúdo de produto e muda), então o mapeamento é
# estável mesmo que a mensagem seja reescrita. `empresa_inscricao_
# consistente_com_tipo` reporta em "tipo_inscricao": é a invariante entre
# os TRÊS campos, e não faz sentido apontar só para "cnpj" ou só para
# "cpf" quando o problema pode ser qualquer lado da combinação.
_CAMPO_DA_RESTRICAO_DE_EMPRESA = {
    "empresa_cnpj_canonico": "cnpj",
    "empresa_cpf_formato_valido": "cpf",
    "empresa_inscricao_consistente_com_tipo": "tipo_inscricao",
    # Achado D1 da auditoria DL-039 rodada 1 (BL-533): gatilho de banco
    # (não é `Meta.constraint` — ver `apps.core.restricoes.MENSAGENS_DE_
    # RESTRICAO_DE_GATILHO`), disparado quando a checagem em Python
    # (`recusar_transicao_para_cpf_com_estabelecimento`, chamada em
    # `EmpresaSerializer.validate`) perde a corrida contra um
    # `Estabelecimento` inserido depois da checagem e antes do UPDATE.
    "empresa_transicao_cpf_com_estabelecimento": "tipo_inscricao",
}


def _campo_da_restricao_de_empresa(nome_constraint):
    # `.get(..., "cnpj")` preserva o comportamento ANTERIOR à DL-038 (só
    # existia "empresa_cnpj_canonico", sempre reportado em "cnpj") para
    # qualquer nome não mapeado — nunca estoura KeyError por uma constraint
    # nova que um dia apareça aqui sem entrada.
    return _CAMPO_DA_RESTRICAO_DE_EMPRESA.get(nome_constraint, "cnpj")


def _contrato_da_tela_de_empresa():
    """Contrato da TELA de cadastro de empresa (`criar_empresa`).

    Encontrado pela varredura da BL-196 (`apps/core/tests/test_dl019_
    varredura_de_contratos.py`, segunda rodada da DL-020): esta era a única
    superfície de escrita do repositório que ainda não aplicava a política dos
    cinco dicionários. A rodada 6 mediu `conta_nova` e `ativar_escritorio`, o
    fechamento cobriu as rotas de API deste app, e esta tela ficou de fora —
    exatamente o "vizinho aberto" que a DE-034 existe para pegar. É a mesma
    classe do defeito de `conta_nova`: `cnpj` enviado como ARQUIVO não aparece
    em `request.POST`, e um campo desconhecido (`escritorio`, por exemplo) era
    aceito e descartado em silêncio.

    Os campos saem do PRÓPRIO formulário (`EmpresaForm.fields`), como
    `_campos_gravaveis` faz para os serializers da API: uma lista literal aqui
    divergiria do `<form>` na primeira mudança de cadastro.
    `csrfmiddlewaretoken` entra porque o `<form>` o emite de verdade — não é
    dado de negócio, mas é chave presente no corpo, e o contrato julga o
    corpo inteiro.
    """
    return ContratoDeRequisicao(
        campos=frozenset(EmpresaForm().fields) | {"csrfmiddlewaretoken"},
        # Cadastro de empresa pela tela não tem contrato de idempotência
        # nenhum: quem manda `Idempotency-Key` aqui está usando o contrato da
        # API e precisa ouvir isso, em vez de acreditar num controle de
        # repetição que esta superfície não implementa (R5-6/BL-145).
        cabecalhos_ignorados=("Idempotency-Key",),
        contexto="no cadastro de empresa pela tela",
    )


CONTRATO_POST_REGIME = ContratoDeRequisicao(
    campos={"regime", "vigencia_inicio"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no regime tributário",
)
CONTRATO_EXCLUSAO_DE_REGIME = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na exclusão de regime tributário",
)


class EmpresaQuerySetMixin:
    permission_classes = [TemEscritorioAtivo]

    def get_queryset(self):
        # Isolamento: sempre filtrado pelo escritório ativo da requisição,
        # nunca por um identificador recebido do cliente.
        return Empresa.objects.filter(escritorio=self.request.escritorio)


class EmpresaListCreateView(EmpresaQuerySetMixin, generics.ListCreateAPIView):
    serializer_class = EmpresaSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(PodeGerenciarEmpresa())
        return permissions

    def post(self, request, *args, **kwargs):
        # BL-196. `escritorio` no corpo é ignorado por construção (o
        # serializer o define a partir do escritório ativo), e agora é
        # recusado: é um campo de ISOLAMENTO, e um cliente que o envie
        # precisa ouvir "não" em vez de receber 201 e acreditar que
        # cadastrou empresa em outro escritório.
        _recusar_dado_nao_contratado(
            request,
            ContratoDeRequisicao(
                campos=_campos_gravaveis(self.get_serializer()),
                cabecalhos_ignorados=("Idempotency-Key",),
                contexto="no cadastro de empresa",
            ),
        )
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        # R4 (reauditoria, rodada 2): duas requisições simultâneas com o
        # mesmo CNPJ podem passar as duas pelo UniqueValidator do
        # serializer (ele faz SELECT; entre o SELECT e este INSERT o
        # concorrente comita) e uma delas estoura IntegrityError na
        # constraint do banco. O savepoint de transaction.atomic() isola
        # esse erro: se ele ocorrer, só o INSERT é desfeito, e a conexão
        # continua utilizável.
        # erro_de_cnpj_duplicado_como_400 (apps/empresas/services.py)
        # concentra a detecção de qual IntegrityError é a violação da
        # constraint de cnpj — ver o comentário lá sobre por que isso mora
        # num lugar só (A1, reauditoria, rodada 3).
        #
        # `restricao_como_400("empresa_cnpj_canonico")` ACRESCENTADO (BL-204,
        # achado R6-10 / DE-034 item 3): é a outra metade do MESMO `Meta` que
        # a BL-144 fechou. Inalcançável por esta rota hoje — `Empresa.save()`
        # canoniza o CNPJ antes do INSERT —, e mapeada de propósito: o
        # comentário do próprio modelo aponta a DL-010 (importação em lote)
        # como candidata natural a `bulk_create`, que NÃO passa por `save()`,
        # e já existe teste provando que esses caminhos vazam
        # `IntegrityError` cru. A armadilha estava armada para a etapa
        # seguinte; o mapeamento a desarma antes de a importação existir.
        #
        # BL-14 (DL-024): o `registrar()` foi MOVIDO para dentro do mesmo
        # `transaction.atomic()` que grava a Empresa. Antes, um
        # `IntegrityError` no INSERT do `RegistroAuditoria` deixava a
        # Empresa gravada e a trilha silenciosamente vazia — a
        # contabilidade dizia uma coisa, a trilha dizia outra. Agora
        # ambos são uma só operação atômica: se a trilha falha, a
        # Empresa não foi gravada, e o cliente vê o erro em vez de
        # acreditar num 201 falso. O `CNPJDuplicado` e o `RestricaoViolada`
        # continuam sendo traduzidos para 400 como antes; qualquer outra
        # exceção (incluindo a do `registrar()`) propaga como 500.
        # DL-038: as duas constraints novas (BL-CPF, mesma lógica da
        # "empresa_cnpj_canonico" citada acima) entram no MESMO `with` —
        # ver `_CAMPO_DA_RESTRICAO_DE_EMPRESA` para qual campo cada uma
        # reporta.
        try:
            with (
                transaction.atomic(),
                erro_de_cnpj_duplicado_como_400(),
                restricao_como_400(
                    mensagens_de(
                        "empresa_cnpj_canonico",
                        "empresa_cpf_formato_valido",
                        "empresa_inscricao_consistente_com_tipo",
                    )
                ),
            ):
                empresa = serializer.save()
                registrar(acao="empresa.criada", objeto=empresa, request=self.request)
        except CNPJDuplicado as exc:
            raise DRFValidationError(exc.message_dict) from exc
        except RestricaoViolada as exc:
            raise DRFValidationError(
                {_campo_da_restricao_de_empresa(exc.nome): [str(exc)]}
            ) from exc


class EmpresaDetailView(EmpresaQuerySetMixin, generics.RetrieveUpdateAPIView):
    serializer_class = EmpresaSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method in ("PUT", "PATCH"):
            permissions.append(PodeGerenciarEmpresa())
        return permissions

    def _recusar_dado_nao_contratado_na_atualizacao(self, request):
        # BL-196 / DE-034 item 2: a atualização é a MESMA superfície de
        # escrita que a criação, com o mesmo corpo — e a rodada 6 mediu a
        # criação, não esta. Fechar só a criação repetiria, em duas rotas
        # vizinhas do mesmo arquivo, o padrão que o R6-2 nomeou.
        _recusar_dado_nao_contratado(
            request,
            ContratoDeRequisicao(
                campos=_campos_gravaveis(self.get_serializer()),
                cabecalhos_ignorados=("Idempotency-Key",),
                contexto="na alteração de empresa",
            ),
        )

    def put(self, request, *args, **kwargs):
        self._recusar_dado_nao_contratado_na_atualizacao(request)
        return super().put(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        self._recusar_dado_nao_contratado_na_atualizacao(request)
        return super().patch(request, *args, **kwargs)

    def perform_update(self, serializer):
        # A1 (reauditoria da etapa DL-011, rodada 3): o R4 tinha sido
        # corrigido só na criação. PUT/PATCH para o CNPJ de outra empresa
        # tem exatamente a mesma corrida (SELECT do UniqueValidator, depois
        # UPDATE) — reproduzida pelo auditor em 6 de 6 execuções com duas
        # threads. Mesmo tratamento de perform_create, mesmo gerenciador de
        # contexto compartilhado.
        # `empresa_cnpj_canonico` também aqui (BL-204): mesma constraint, mesmo
        # `Meta`, e a atualização é o outro caminho de gravação do mesmo campo
        # — ver o comentário em `perform_create`.
        #
        # BL-57 (DL-024): o `registrar()` foi ADICIONADO dentro do mesmo
        # `transaction.atomic()` da gravação, com `detalhes` no formato
        # `valores_anteriores` / `valores_novos` (mesmo padrão de
        # `valores_antigos` em `apps/empresas/services.py:305`, na
        # `excluir_ultimo_regime_tributario`). A lista de campos
        # auditados é derivada do CONTRATO, não escrita à mão:
        # `_campos_gravaveis(serializer)` (`apps/empresas/views.py:72`) já
        # é a fonte única dos campos graváveis do serializer (BL-196/DE-034).
        # Aqui isso é exatamente `{razao_social, nome_fantasia, cnpj, ativo}`
        # — `id` não é gravável, `regime_atual` é read-only,
        # `escritorio` não está no serializer (forçado pela requisição,
        # travado pelo modelo desde a DL-023/BL-211/A3), e
        # `regime_tributario` tem rota própria com trilha (RC-86/DE-039).
        # Campo novo no serializer amanhã entra na trilha sozinho, e o
        # teste de derivação (com `monkeypatch` no serializer) cobre isso.
        # Só os campos que MUDARAM aparecem nos dois dicts (diff, não
        # retrato). PUT/PATCH que não altera nada (mesmo payload reenviado)
        # NÃO gera registro — anti-P8 da DL-011 rodada 3.
        # `ativo: true → false` é material: o diff trata a desativação
        # como qualquer outra mudança.
        original = serializer.instance
        diff_anterior, diff_novo = _diff_dos_campos_gravaveis(serializer, original)

        try:
            with (
                transaction.atomic(),
                erro_de_cnpj_duplicado_como_400(),
                restricao_como_400(
                    {
                        **mensagens_de(
                            "empresa_cnpj_canonico",
                            "empresa_cpf_formato_valido",
                            "empresa_inscricao_consistente_com_tipo",
                        ),
                        # D1/BL-533: janela de corrida entre a checagem em
                        # Python e o UPDATE — ver o comentário em
                        # `_CAMPO_DA_RESTRICAO_DE_EMPRESA`.
                        **mensagens_de_gatilho("empresa_transicao_cpf_com_estabelecimento"),
                    }
                ),
            ):
                serializer.save()
                if diff_anterior:  # houve mudança em algum campo
                    registrar(
                        acao="empresa.atualizada",
                        objeto=original,  # após save(), é a instância atualizada
                        request=self.request,
                        detalhes={
                            "valores_anteriores": diff_anterior,
                            "valores_novos": diff_novo,
                        },
                    )
        except CNPJDuplicado as exc:
            raise DRFValidationError(exc.message_dict) from exc
        except RestricaoViolada as exc:
            raise DRFValidationError(
                {_campo_da_restricao_de_empresa(exc.nome): [str(exc)]}
            ) from exc


class EstabelecimentoListCreateView(EmpresaEscopadaMixin, generics.ListCreateAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = EstabelecimentoSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(PodeGerenciarEmpresa())
        return permissions

    def get_queryset(self):
        return Estabelecimento.objects.filter(empresa=self.get_empresa())

    def post(self, request, *args, **kwargs):
        # BL-196: medido pelo auditor nesta rota — `empresa: 999` e `xpto` no
        # corpo devolviam **201**, ignorados em silêncio.
        _recusar_dado_nao_contratado(
            request,
            ContratoDeRequisicao(
                campos=_campos_gravaveis(self.get_serializer()),
                cabecalhos_ignorados=("Idempotency-Key",),
                contexto="no cadastro de estabelecimento",
            ),
        )
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer):
        # Achado B2 da auditoria rodada 1 (DL-038, R7): estabelecimento é
        # conceito de pessoa jurídica — recusado ANTES de qualquer escrita
        # para empresa CPF. A REGRA mora só em `apps.empresas.services.
        # recusar_estabelecimento_para_empresa_cpf`.
        empresa = self.get_empresa()
        try:
            recusar_estabelecimento_para_empresa_cpf(empresa)
        except EstabelecimentoParaEmpresaCPF as exc:
            raise DRFValidationError({"empresa": exc.messages}) from exc

        # Achado U-B4 da auditoria DL-041 rodada 1 (decisão do
        # arquiteto-senior): o CNPJ deste estabelecimento não pode ser o
        # MESMO de OUTRA empresa do mesmo escritório — a matriz com o CNPJ
        # da PRÓPRIA `empresa` (a que esta rota está escopada por
        # `get_empresa()`) continua permitida, de propósito.
        cnpj = serializer.validated_data.get("cnpj")
        if cnpj:
            try:
                recusar_cnpj_de_estabelecimento_igual_a_outra_empresa(
                    empresa.escritorio_id, cnpj, empresa_do_estabelecimento=empresa
                )
            except InscricaoCruzadaEntreEmpresaEEstabelecimento as exc:
                raise DRFValidationError({"cnpj": exc.messages}) from exc

        # Mesmo tratamento de corrida do achado R4 em EmpresaListCreateView
        # (ver comentário lá): cnpj de Estabelecimento também é unique=True.
        #
        # `restricao_como_400` ACRESCENTADO (achado R5-5 da auditoria
        # DL-017 rodada 5, BL-144 / DE-034 — "agravante de método"
        # nomeado pelo auditor): esta função JÁ envolvia a gravação em
        # `erro_de_cnpj_duplicado_como_400()` — a defesa existia, nesta
        # MESMA função, só para a unicidade de CNPJ, e não para
        # `uma_matriz_por_empresa` (`Estabelecimento.Meta.constraints`,
        # quatro linhas abaixo da de CNPJ no modelo). Uma segunda matriz
        # para a mesma empresa derrubava com `IntegrityError` cru, 500.
        # As duas constraints são checadas no MESMO `with`: qualquer uma
        # das duas, ao violar, sobe como a exceção de negócio certa; uma
        # `IntegrityError` de qualquer OUTRA origem continua subindo sem
        # tradução (nenhuma das duas camadas mascara defeito de sistema
        # como erro de cliente).
        #
        # `estabelecimento_cnpj_canonico` ACRESCENTADA (BL-204, achado R6-10):
        # a terceira constraint do MESMO `Meta`, pelo mesmo motivo da de
        # Empresa — ver o comentário em `EmpresaListCreateView.perform_create`.
        # As mensagens saem do registro único `apps.core.restricoes.
        # MENSAGENS_DE_RESTRICAO`, que a varredura de repositório confere
        # contra TODA `Meta.constraints` do projeto: era a conferência manual
        # que deixava constraint de fora.
        try:
            with (
                transaction.atomic(),
                erro_de_cnpj_duplicado_como_400(),
                restricao_como_400(
                    {
                        **mensagens_de("uma_matriz_por_empresa", "estabelecimento_cnpj_canonico"),
                        # D1/BL-533: janela de corrida entre a checagem de
                        # `recusar_estabelecimento_para_empresa_cpf` (linha
                        # acima) e o INSERT — se a empresa virar CPF nesse
                        # meio-tempo, o gatilho de banco (não é
                        # `Meta.constraint`; ver o comentário em
                        # `apps.core.restricoes.MENSAGENS_DE_RESTRICAO_DE_
                        # GATILHO`) recusa, e este `with` traduz para 400
                        # em vez de 500.
                        **mensagens_de_gatilho("estabelecimento_empresa_nao_e_cpf"),
                    }
                ),
            ):
                estabelecimento = serializer.save(empresa=empresa)
                registrar(
                    acao="estabelecimento.criado",
                    objeto=estabelecimento,
                    request=self.request,
                )
        except CNPJDuplicado as exc:
            raise DRFValidationError(exc.message_dict) from exc
        except RestricaoViolada as exc:
            # O campo em que o erro aparece depende de QUAL constraint caiu —
            # `exc.nome`, nunca o texto da mensagem (ver `RestricaoViolada`).
            if exc.nome == "estabelecimento_cnpj_canonico":
                campo = "cnpj"
            elif exc.nome == "estabelecimento_empresa_nao_e_cpf":
                campo = "empresa"
            else:
                campo = "tipo"
            raise DRFValidationError({campo: [str(exc)]}) from exc


class HistoricoRegimeTributarioListCreateView(EmpresaEscopadaMixin, generics.ListAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = HistoricoRegimeTributarioSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(PodeGerenciarEmpresa())
        return permissions

    def get_queryset(self):
        return HistoricoRegimeTributario.objects.filter(empresa=self.get_empresa())

    def post(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        # BL-196: medido pelo auditor nesta rota — querystring, `empresa` e
        # `xpto` no corpo devolviam **201**, ignorados em silêncio.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_REGIME)
        regime = request.data.get("regime")
        vigencia_inicio = request.data.get("vigencia_inicio")
        if not regime or not vigencia_inicio:
            raise DRFValidationError("regime e vigencia_inicio são obrigatórios.")

        try:
            # `para_escolha` (achado R5-2 da auditoria DL-017 rodada 5,
            # BL-141 / DE-034): `regime` é o VIZINHO de `vigencia_inicio`
            # no mesmo `request.data` — a correção anterior (BL-133, rodada
            # 4) tratou a linha de baixo e deixou esta como estava. Antes,
            # `regime` não tinha checagem nenhuma de tipo nem de `choices`:
            # uma lista, um dicionário, um número ou um booleano eram
            # GRAVADOS (`str(valor)` do Python vira o texto salvo —
            # "['simples_nacional']", "{'a': 1}", "True"), um texto fora
            # das `RegimeTributario.choices` também (`"SIMPLES_NACIONAL"`
            # em maiúsculas, ou com espaço em volta), e um texto de 500
            # caracteres derrubava a gravação com `DataError` — 500 cru,
            # `max_length=20` do campo. `para_escolha` recusa os sete casos
            # com 400, antes de qualquer gravação.
            regime = para_escolha(regime, RegimeTributario.values, nome_campo="regime")
        except EscolhaInvalida as exc:
            raise DRFValidationError(str(exc)) from exc

        try:
            # `para_data` (achado A9 da auditoria DL-017 rodada 4, BL-133 /
            # DE-030 estendida a dado tipado): antes, este trecho chamava
            # `date.fromisoformat` direto sobre `vigencia_inicio`, sem
            # gramática nem checagem de tipo — a mesma classe do R3-3
            # (número JSON reinterpretado / 500), só que num campo de data:
            #   "2026-W01-1" -> 201, gravado 2025-12-29 (reinterpretado em
            #                    silêncio — data de semana ISO aceita por
            #                    `fromisoformat` e convertida para OUTRO dia)
            #   20260101 (número JSON) -> 500 (`TypeError`, não capturado:
            #                    `fromisoformat` exige `str`)
            #   "20260101" (sem hífen) -> 201, gravado 2026-01-01 (aceito
            #                    fora do formato AAAA-MM-DD anunciado)
            # `para_data` usa a MESMA gramática que `apps.contabilidade.
            # views._periodo_obrigatorio` já aplicava a `inicio`/`fim`
            # (agora em `apps.core.datas`, para não duplicar a regra entre
            # os dois apps — DE-026).
            data_inicio = para_data(vigencia_inicio)
        except DataInvalida as exc:
            raise DRFValidationError(f"'vigencia_inicio' inválido: {exc}") from exc

        try:
            # BL-14 (DL-024): o serviço já tem uma transação própria, mas
            # ela termina antes de retornar. A transação externa mantém a
            # criação do período e o `registrar()` no mesmo commit; se a
            # trilha falhar, o período também volta atrás.
            with transaction.atomic():
                registro = registrar_regime_tributario(empresa, regime, data_inicio)
                registrar(
                    acao="regime_tributario.registrado",
                    objeto=registro,
                    request=request,
                    detalhes={"regime": regime, "vigencia_inicio": vigencia_inicio},
                )
        except ValueError as exc:
            raise DRFValidationError(str(exc)) from exc

        serializer = self.get_serializer(registro)
        return Response(serializer.data, status=201)


class HistoricoRegimeTributarioDetailView(EmpresaEscopadaMixin, APIView):
    """Exclusão do ÚLTIMO período de regime tributário (BL-209, RC-86/DE-039).

    Existe porque o achado R6-6 mostrou uma porta de mão única: um dígito
    errado em `vigencia_inicio` deixava a empresa sem NENHUM caminho de
    correção pelo produto — não havia `PUT`, `DELETE` nem edição na tela, e
    só acesso direto ao banco desfazia. O Fred decidiu, em 2026-09-15, que a
    correção **apaga** o registro (RC-86); o alcance está na DE-039 e a regra
    inteira mora em `apps.empresas.services.excluir_ultimo_regime_tributario`
    — esta view só traduz o veredito para HTTP.

    Só `DELETE`: não há `GET` de item (a listagem já responde isso) nem
    `PUT`/`PATCH`, porque editar um período em silêncio é justamente o que a
    DE-039 não quis — "apagar e registrar de novo" deixa rastro do que
    aconteceu, "editar" não.

    Autorização no SERVIDOR, com o mesmo papel que cria (`PodeGerenciarEmpresa`
    — ADMINISTRADOR e GESTOR): quem pode registrar o regime pode desfazer o
    último registro. Papel sem gestão recebe 403 mesmo sem nenhuma tela ter
    mostrado botão.
    """

    permission_classes = [TemEscritorioAtivo, PodeGerenciarEmpresa]

    def delete(self, request, empresa_id, registro_id):
        empresa = self.get_empresa()
        # `get_object_or_404` sempre escopado pela empresa da URL, que o mixin
        # já revalidou contra o escritório ativo: um `registro_id` de outra
        # empresa (ou de outro escritório) responde 404, nunca apaga.
        registro = get_object_or_404(HistoricoRegimeTributario, pk=registro_id, empresa=empresa)
        # BL-196: `DELETE` também entra na política. Um corpo com
        # `vigencia_inicio` aqui sugeriria que o cliente está escolhendo QUAL
        # período apagar por conteúdo, quando quem decide é a URL.
        _recusar_dado_nao_contratado(request, CONTRATO_EXCLUSAO_DE_REGIME)

        try:
            apagado = excluir_ultimo_regime_tributario(
                empresa=empresa, registro=registro, usuario=request.user, request=request
            )
        except ExclusaoDeRegimeInvalida as exc:
            raise DRFValidationError(str(exc)) from exc

        # 200 com o que foi apagado, não 204 vazio: o contador precisa ver
        # QUAL período saiu (regime e vigência), e a resposta é a única
        # confirmação que ele tem — o registro não existe mais para consultar.
        return Response({"apagado": apagado, "detail": "Período de regime tributário apagado."})


def _mascara_cnpj(cnpj):
    """Formata um CNPJ de 14 caracteres como XX.XXX.XXX/XXXX-XX.

    Puramente de apresentação: não repete a validação de
    apps.empresas.validators, que já garantiu o formato na gravação. Se o
    valor armazenado não tiver exatamente 14 caracteres (dado herdado ou
    corrompido), devolve o valor original em vez de mascarar errado.

    O CNPJ alfanumérico (NT 2025.001/IN RFB 2.229, ver
    apps/empresas/validators.py) continua com 14 posições, então o mesmo
    agrupamento de sempre é aplicado a letras e dígitos — não só a dígitos.
    Importante: esse agrupamento XX.XXX.XXX/XXXX-XX é convenção nossa de
    exibição, não uma regra normativa. A NT 2025.001 define validação, chave
    de acesso e código de barras; ela não define máscara de tela. Se a
    Receita publicar um formato de apresentação próprio, esta função deve
    ser revista.
    """
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[0:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


def _mascara_cpf(cpf):
    """Formata um CPF de 11 dígitos como XXX.XXX.XXX-XX — mesma política de
    `_mascara_cnpj` (puramente de apresentação; devolve o valor original se
    não tiver exatamente 11 caracteres, em vez de mascarar errado)."""
    if len(cpf) != 11:
        return cpf
    return f"{cpf[0:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}"


@login_required
@require_safe
def lista_empresas(request):
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")
    empresas = list(Empresa.objects.filter(escritorio=request.escritorio))
    # Formatação de apresentação (CNPJ/CPF mascarado) feita aqui, na view, e
    # não em template tag própria: esta etapa não tem permissão para criar
    # arquivos em apps/empresas/templatetags/ (ver docs/projeto/DL-009).
    #
    # DL-038 — critério 7 (etapa 2, `especialista-frontend`):
    # `templates/empresas/lista.html` agora lê `rotulo_inscricao`/
    # `inscricao_formatada` (não mais `cnpj_formatado` — a coluna mostra
    # CNPJ OU CPF conforme o tipo de cada linha, e um cabeçalho fixo
    # "CNPJ" mentiria para empresa CPF). `cnpj_formatado` continua
    # calculado abaixo por retrocompatibilidade (nenhum outro código deste
    # módulo lê o atributo, mas remover um atributo de apresentação sem
    # necessidade não é o escopo desta etapa).
    #
    # `em_livro_caixa`: booleano calculado com o enum e passado pronto ao
    # template (mesmo padrão de `pode_cadastrar`, abaixo) — decide se a
    # célula "Contabilidade" mostra os links de escrituração ou um aviso
    # (R5: a contabilidade por partidas dobradas não se aplica a empresa em
    # livro-caixa). Não é a recusa de verdade — essa continua só no
    # servidor, em `apps.empresas.services.recusar_se_livro_caixa`,
    # aplicada pelo decorador de cada view da contabilidade
    # (`apps.contabilidade.views_web._sem_contabilidade_para_livro_caixa`);
    # isto só evita oferecer, na lista, um link que o servidor sempre
    # recusaria — link ausente aqui não é a defesa, só evita o passeio.
    for empresa in empresas:
        empresa.cnpj_formatado = _mascara_cnpj(empresa.cnpj)
        empresa.em_livro_caixa = empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA
        if empresa.tipo_inscricao == TipoInscricao.CPF:
            empresa.rotulo_inscricao = "CPF"
            empresa.inscricao_formatada = _mascara_cpf(empresa.cpf)
        else:
            empresa.rotulo_inscricao = "CNPJ"
            empresa.inscricao_formatada = empresa.cnpj_formatado
    # DL-040: "Trocar de empresa" do menu global chega aqui com `?secao=` —
    # o nome da seção da contabilidade que a pessoa estava vendo antes de
    # trocar. Só um valor RECONHECIDO (chave de SECOES_DE_TROCA_DE_EMPRESA,
    # definida mais abaixo neste módulo) é aceito; qualquer outra coisa cai
    # em string vazia, e o template simplesmente não oferece o link extra —
    # nunca um erro por um parâmetro de conveniência mal formado. Esta
    # tela já lista razão social de TODAS as empresas do escritório
    # (propósito da tela; nenhum isolamento entre empresas a proteger
    # aqui), então oferecer o atalho de volta para a MESMA seção, por
    # empresa, não expõe nada que a tela já não expusesse.
    secao_de_troca = request.GET.get("secao", "")
    if secao_de_troca not in SECOES_DE_TROCA_DE_EMPRESA:
        secao_de_troca = ""

    contexto = {
        "empresas": empresas,
        # Booleano calculado com o enum e passado pronto ao template: a
        # regra de quem pode cadastrar mora só aqui, não repetida como
        # string literal na marcação (achado A8 da auditoria de DL-009).
        # A autorização real de qualquer forma é sempre re-checada no
        # servidor em criar_empresa; isto só decide o que a tela mostra.
        "pode_cadastrar": request.papel in (Papel.ADMINISTRADOR, Papel.GESTOR),
        "secao_de_troca": secao_de_troca,
    }
    return render(request, "empresas/lista.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def criar_empresa(request):
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")
    if request.papel not in (Papel.ADMINISTRADOR, Papel.GESTOR):
        # Falta de permissão ganha template próprio, com explicação e
        # caminho de volta — nunca mais texto cru sem contexto (BL-22).
        # A autorização real continua sendo aplicada aqui, no servidor;
        # o template só explica a negativa que já ocorreu.
        contexto = {"mensagem": "Seu papel não permite cadastrar empresas."}
        return render(request, "erros/sem_permissao.html", contexto, status=403)

    if request.method == "POST":
        # BL-196: a política vem de `apps.core.requisicao` (ponto único), e a
        # resposta segue o padrão já instituído nas telas da contabilidade
        # (`conta_nova`, BL-199): formulário RE-RENDERIZADO com 400 e com o
        # que o usuário digitou. Recusar sem devolver o que foi digitado troca
        # um defeito por outro; responder 200 faria a recusa passar por
        # "página normal" para qualquer cliente que olhe o código de status.
        try:
            recusar_dado_nao_contratado(request, _contrato_da_tela_de_empresa())
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return render(
                request, "empresas/form.html", {"form": EmpresaForm(request.POST)}, status=400
            )

        form = EmpresaForm(request.POST)
        if form.is_valid():
            empresa = form.save(commit=False)
            empresa.escritorio = request.escritorio
            # R4 (reauditoria da etapa DL-011): o form.is_valid() já checou
            # unicidade via validate_unique() (um SELECT), mas entre esse
            # SELECT e o INSERT abaixo um concorrente pode ter comitado o
            # mesmo CNPJ — a corrida que gera 500 se não tratada. O
            # savepoint isola o erro para a conexão continuar utilizável.
            try:
                with transaction.atomic(), erro_de_cnpj_duplicado_como_400():
                    empresa.save()
            except CNPJDuplicado as exc:
                # DL-038: `exc.message_dict` já vem com a CHAVE certa —
                # "cnpj" ou "cpf", conforme qual constraint colidiu (ver
                # `mensagem_se_cnpj_duplicado`, apps/empresas/services.py).
                # Antes desta etapa só existia "cnpj", e o `.get("cnpj",
                # [])` fixo bastava; fixo, ele passou a ENGOLIR em silêncio
                # a duplicidade de CPF — a exceção era capturada, a
                # transação desfeita (o savepoint), mas NENHUM erro ia para
                # o formulário: o contador via a MESMA tela sem aviso
                # nenhum e sem a empresa cadastrada, a classe de defeito
                # que o AGENTS.md §8 proíbe (falha convertida em sucesso
                # aparente). Iterar `.items()` cobre as duas chaves sem
                # supor qual delas colidiu.
                for campo, mensagens in exc.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(campo, mensagem)
            else:
                registrar(acao="empresa.criada", objeto=empresa, request=request)
                messages.success(request, f"Empresa “{empresa}” cadastrada com sucesso.")
                return redirect("empresas:lista")
    else:
        form = EmpresaForm()

    return render(request, "empresas/form.html", {"form": form})


# ---------------------------------------------------------------------------
# DL-040 — seletor de empresa do menu global: troca de empresa mantendo a
# MESMA seção da contabilidade (ex.: olhando o Balancete da empresa A, ir
# para o Balancete da empresa B sem passar pela lista de empresas).
# ---------------------------------------------------------------------------

# Nome de rota (`contabilidade_web:<nome>`) por CÓDIGO de seção — só as
# seções que dependem de UM ÚNICO argumento (`empresa_id`). "Razão" (exige
# também `conta_id`) e as telas de ação do fechamento (exigem `ano`/`mes`)
# não têm uma seção "equivalente" genérica na empresa de destino sem mais
# contexto do que este formulário simples carrega — ficam de fora do mapa,
# e a view cai no padrão (`plano_de_contas`) para elas, nunca em erro 400,
# porque o pedido nunca é "esta seção exata", é "continue vendo esta
# empresa, na contabilidade" (ver o comentário da view abaixo).
SECOES_DE_TROCA_DE_EMPRESA = {
    "plano_de_contas": "contabilidade_web:plano_de_contas",
    "diario": "contabilidade_web:diario",
    "balancete": "contabilidade_web:balancete",
    "balanco": "contabilidade_web:balanco",
    "conferencia": "contabilidade_web:conferencia",
    "fechamento": "contabilidade_web:fechamento",
    "lancamento_novo": "contabilidade_web:lancamento_novo",
}

_SECAO_PADRAO_DE_TROCA_DE_EMPRESA = "plano_de_contas"


@login_required
@require_safe
def trocar_empresa_na_secao(request):
    """DL-040: seletor de empresa do menu global (formulário GET, sem
    JavaScript) — troca a EMPRESA mantendo a MESMA seção da contabilidade.

    Isolamento (mesma regra de `_empresa_do_escritorio_ativo`, em
    `apps.contabilidade.views_web`): a empresa pedida nunca é aceita só pelo
    ID recebido — precisa pertencer ao ESCRITÓRIO ATIVO da requisição, ou a
    resposta é 404 (nunca 403: não confirma nem a existência da empresa
    para quem não tem acesso a ela).

    `secao` fora de `SECOES_DE_TROCA_DE_EMPRESA` (Razão, que exige
    `conta_id`, ou as telas de ação do fechamento, que exigem `ano`/`mes`)
    não é erro: cai no padrão (Plano de contas) — o pedido de quem usa o
    seletor é "continue vendo esta empresa", não "esta URL exata resolvida
    na outra empresa", e a alternativa (400/mensagem de erro) puniria a
    pessoa por usar o seletor numa tela que ele não cobre ainda.
    """
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")

    try:
        empresa_id = para_id(request.GET.get("empresa_id"))
    except IdentificadorInvalido as exc:
        raise Http404("Empresa inválida.") from exc

    # Nunca confiar apenas no ID recebido: exige que a empresa pertença ao
    # escritório ATIVO da requisição (mesmo isolamento de
    # `apps.contabilidade.views_web._empresa_do_escritorio_ativo`).
    empresa = get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)

    secao = request.GET.get("secao", "")
    rota_padrao = SECOES_DE_TROCA_DE_EMPRESA[_SECAO_PADRAO_DE_TROCA_DE_EMPRESA]
    nome_da_rota = SECOES_DE_TROCA_DE_EMPRESA.get(secao, rota_padrao)
    return redirect(nome_da_rota, empresa.id)
