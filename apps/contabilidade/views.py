import hashlib
import json
import re
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.contabilidade.intercambio import importacao_lancamentos
from apps.contabilidade.intercambio.canonico import IntercambioRecusado
from apps.contabilidade.intercambio.formatos import LEITORES, excel, referencia
from apps.contabilidade.intercambio.lancamentos import exportar_lancamentos
from apps.contabilidade.intercambio.leitura import (
    TAMANHO_MAXIMO_ARQUIVO_BYTES,
    ArquivoGrandeDemais,
    ler_arquivo,
)
from apps.contabilidade.intercambio.plano import (
    POLITICA_SO_ACRESCENTAR,
    ArquivoAlteradoDesdeAPrevia,
    ParametroInvalido,
    PlanoAlteradoDesdeAPrevia,
    PlanoRecusado,
    aplicar_plano,
    conferir_plano,
    exportar_plano,
    validar_politica,
    validar_prefixos,
)
from apps.contabilidade.models import (
    Conta,
    DeParaConta,
    ImportacaoLancamentos,
    LancamentoContabil,
    MarcacaoDmpl,
    NaturezaConta,
    OrigemLancamento,
    ParametroContabilEmpresa,
    TipoPartida,
)
from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.contabilidade.serializers import (
    ClassificacaoDfcPatchSerializer,
    ClassificacaoDlpaPatchSerializer,
    ClassificacaoDmplPatchSerializer,
    ClassificacaoDrePatchSerializer,
    ContaSerializer,
    LancamentoContabilSerializer,
    MarcacaoDmplGravacaoSerializer,
)
from apps.contabilidade.services import (
    ChaveIdempotenciaConflitante,
    ClassificacaoAlteraPeriodoFechado,
    CompetenciaEncerrada,
    CompetenciaJaEntregue,
    CompetenciaOperacaoInvalida,
    CompetenciaOperacaoRecusada,
    EstornoDeOrigemAutomaticaNaoPermitido,
    HierarquiaInconsistente,
    LancamentoInvalido,
    MarcacaoDmplInvalida,
    ParametroContabilInvalido,
    VigenciaParametroContabilConflitante,
    apurar_balancete,
    apurar_dfc,
    apurar_dlpa,
    apurar_dmpl,
    apurar_dre,
    apurar_razao,
    avaliar_emissao_da_dfc,
    avaliar_emissao_da_dlpa,
    avaliar_emissao_da_dmpl,
    avaliar_emissao_da_dre,
    classificar_conta_na_dfc,
    classificar_conta_na_dlpa,
    classificar_conta_na_dmpl,
    classificar_conta_na_dre,
    criar_lancamento,
    encerrar_competencia,
    encerrar_vigencia_de_parametro_contabil,
    estornar_lancamento,
    listar_diario,
    localizar_contas_que_aceitam_lancamento_e_tem_subordinadas,
    localizar_contas_sinteticas_com_movimento,
    localizar_inconsistencias_de_hierarquia,
    localizar_lancamentos_com_data_fora_da_faixa,
    localizar_lotes_desbalanceados,
    marcar_competencia_como_entregue,
    mensagens_da_validacao_django,
    movimento_fora_do_periodo,
    pre_visualizar_zeramento,
    reabrir_competencia,
    registrar_parametro_contabil,
    remover_marcacoes_da_dmpl,
    salvar_marcacoes_da_dmpl,
    zerar_resultado,
)
from apps.core.datas import DataInvalida, para_data
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal
from apps.core.escolhas import EscolhaInvalida, para_escolha
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.papeis_de_fechamento import PAPEIS_QUE_FECHAM_PERIODO
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_campos_nao_contratados,
    recusar_dado_nao_contratado,
)
from apps.core.restricoes import RestricaoViolada, mensagens_de, restricao_como_400
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.empresas.services import EmpresaEmModoLivroCaixa, recusar_se_livro_caixa
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo, papel_permitido


class EmpresaEscopadaContabilMixin(EmpresaEscopadaMixin):
    """`EmpresaEscopadaMixin` + a recusa da contabilidade para empresa em
    modo livro-caixa (R5/DL-038, DE-075) — PONTO ÚNICO desta recusa para
    TODA rota de API da contabilidade, porque é aqui que toda uma delas já
    resolve a empresa escopada (`self.get_empresa()`), sem exceção: as dez
    classes abaixo (`ContaListCreateView` a
    `ConferenciaLotesDesbalanceadosView`) usam esta mixin no lugar da
    `EmpresaEscopadaMixin` genérica, e é a única mudança entre elas.

    A REGRA (condição + mensagem) mora só em `apps.empresas.services.
    recusar_se_livro_caixa` — este método só CHAMA e traduz para o formato
    do DRF (`ValidationError` vira 400, nunca 403: não é falta de
    permissão, é o TIPO de escrituração da empresa que não comporta a
    operação). `apps/core/tests/test_dl038_recusa_contabilidade_livro_
    caixa.py` prova, por VARREDURA das rotas registradas em `apps.
    contabilidade.urls`/`urls_web` (não por lista escrita à mão), que
    NENHUMA rota escapa desta recusa.
    """

    def get_empresa(self):
        empresa = super().get_empresa()
        try:
            recusar_se_livro_caixa(empresa)
        except EmpresaEmModoLivroCaixa as exc:
            raise DRFValidationError({"empresa": [exc.mensagem]}) from exc
        return empresa


# Mesmo limite do CharField `chave_idempotencia` (models.py). Validado aqui,
# na fronteira da API, para que um cabeçalho longo demais vire 400 (entrada
# do cliente) em vez de vazar como 500 do banco (`DataError: value too long
# for type character varying(255)` — achado A3 da auditoria).
TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA = 255

# Mesmo limite do CharField `historico` (LancamentoContabil.historico,
# max_length=300). Validado aqui pelo mesmo motivo do limite acima (BL-44 /
# achado N3): sem esta checagem, um histórico longo demais só falharia no
# INSERT do Postgres (`DataError: value too long for type character
# varying(300)`), vazando como 500 em vez de 400.
TAMANHO_MAXIMO_HISTORICO = 300

# Maior valor absoluto que cabe em `ItemLancamento.valor` (DecimalField
# max_digits=18, decimal_places=2): com 2 casas decimais fixas, a parte
# inteira suporta no máximo 18 - 2 = 16 dígitos, então qualquer valor cujo
# módulo alcance 10**16 já não cabe na coluna. Verificado aqui, na fronteira
# da API (BL-44 / achado N3), para que o excesso vire 400 (entrada do
# cliente) em vez de `DataError` do Postgres vazando como 500. Não cobre
# ESCALA (casas decimais) — essa é uma regra do domínio contábil, aplicada
# por `criar_lancamento` com sua própria mensagem, que informa o valor
# recebido e a escala aceita (DE-010) — duplicar a checagem aqui com uma
# mensagem genérica escondia a mensagem de domínio, mais útil ao contador.
LIMITE_MAGNITUDE_VALOR = Decimal(10) ** (18 - 2)

# Formato ESTRITO aceito para `nivel` (achado 12): um ou mais dígitos ASCII
# (`[0-9]`, não `\d` — mesmo motivo do padrão de data acima, achado novo 11),
# sem sinal, sem espaço e sem "_" como separador. Verificado ANTES de
# `int()`, que aceita "1_0" (convertido para 10), " 2 " e "+2" sem avisar —
# mesma classe de reinterpretação silenciosa que a checagem acima evita para
# data. Também aceitaria QUALQUER dígito Unicode ("٢") se usássemos `\d`.
_PADRAO_NIVEL_SIMPLES = re.compile(r"^[0-9]+$")

# Teto superior para `nivel` (achado novo 11): nenhum plano de contas real
# chega a esta profundidade — é só para recusar um valor absurdo como
# "999999999999999999999999999999" (que o Python aceitaria como inteiro de
# precisão arbitrária sem erro nenhum) em vez de deixá-lo percorrer o
# cálculo de nível sem produzir efeito útil. Generoso o bastante para não
# incomodar nenhum plano de contas real (a hierarquia mais profunda do
# domínio contábil, no material de referência do projeto, tem poucos
# níveis — ver docs/projeto/mapa-funcional-contabil.md).
NIVEL_MAXIMO = 50

# Achado R5-6 da auditoria DL-017 rodada 5 (BL-145, minha parte — a
# política combinada com o especialista-frontend, que já aplica a mesma
# recusa na tela): campo desconhecido no corpo do POST de lançamento era
# aceito e IGNORADO em silêncio (`empresa`, `id`, `criado_por`,
# `estornado` no topo; `xpto` dentro de um item) — enquanto a tela já
# recusa (medido pelo auditor: `valor_total`/`estorno` → 400). É a MESMA
# classe do achado 5 (BL-116, "nenhum dado enviado numa requisição deixa
# de ser lido ou recusado"), só que pela superfície da API. O agravante
# concreto: quem manda `chave_idempotencia` NO CORPO (em vez do cabeçalho
# `Idempotency-Key`, o único contrato válido) não era avisado e recebia a
# DUPLICIDADE que a chave existe para impedir — `chave_idempotencia` no
# corpo é, por construção, um "campo desconhecido" e cai nesta mesma
# recusa, fechando o buraco sem precisar de um caso especial.
CAMPOS_PERMITIDOS_LANCAMENTO = frozenset({"data", "historico", "itens"})
CAMPOS_PERMITIDOS_ITEM = frozenset({"conta", "tipo", "valor"})

# BL-196 / achado R6-2 (rodada 6): a política dos cinco dicionários passou a
# morar em `apps.core.requisicao` e vale para as SETE superfícies de escrita,
# não só para o POST de lançamento. O que sobrava, medido pelo auditor, era
# tudo o que NÃO é o corpo: querystring num POST (201 com um par de partidas
# completo pendurado na URL, nem lido nem recusado), `request.FILES` e
# cabeçalho não contratado. Cada view abaixo declara o seu contrato; nenhuma
# reimplementa a subtração de conjuntos.
#
# `aceita_querystring=False` em todas: nenhuma rota de ESCRITA desta API tem
# contrato de querystring — o recorte de período é das rotas de LEITURA
# (`_periodo_obrigatorio`), que não passam por aqui.
#
# Cabeçalhos: a API de lançamento USA `Idempotency-Key` (BL-41), então ela
# não o declara como ignorado. As outras rotas de escrita NÃO têm contrato de
# idempotência nenhum, e quem manda a chave nelas precisa saber que ela não
# tem efeito — é o mesmo defeito da tela (R5-6), na direção oposta: lá o
# cabeçalho era ignorado, aqui ele seria ignorado em rotas que não o
# implementam.
CONTRATO_POST_CONTA = ContratoDeRequisicao(
    # DL-045/RC-118: `classificacao_dre` somada aqui — sem isto, a
    # "política dos cinco dicionários" (BL-196) recusaria com "dado não
    # contratado" ANTES de o campo novo do serializer sequer ser
    # examinado, mesmo já declarado em `ContaSerializer.Meta.fields`.
    campos={
        "codigo",
        "nome",
        "tipo",
        "natureza",
        "conta_pai",
        "aceita_lancamento",
        "ativo",
        "classificacao_dre",
        # DL-048 (fatia D8): mesma razão do `classificacao_dre` acima. Sem
        # esta linha, o campo novo do serializer é recusado com "dado não
        # contratado" ANTES de qualquer validação — e a recusa acontece por
        # contrato, não por tipo, então a mensagem nem nomeia o campo.
        "classificacao_dlpa",
        # DL-063 (BL-606): mesma razão das duas de cima, e pela MESMA
        # decisão do Fred de 04/10/2026 — a coluna da DMPL deixa de ser
        # exclusivo da porta própria de classificação e passa a ser aceita no
        # cadastro de conta, como a linha da DRE e a linha da DLPA. Sem esta
        # linha, o campo novo do serializer é recusado com "dado não
        # contratado" ANTES de qualquer validação, e a recusa acontece por
        # contrato, sem nem nomear o campo.
        "classificacao_dmpl",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de conta",
)
CONTRATO_POST_LANCAMENTO = ContratoDeRequisicao(
    campos=CAMPOS_PERMITIDOS_LANCAMENTO,
    contexto="no lançamento",
)
# Estorno é rota de AÇÃO: o que estornar vem da URL, e o corpo não tem
# contrato nenhum. `campos=frozenset()` é "nenhum campo aceito" — diferente
# de não declarar, que seria "não julgo o corpo".
CONTRATO_POST_ESTORNO = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno",
)
# Fechar e entregar competência: rotas de AÇÃO, a competência vem da URL
# (empresa/ano/mês), sem corpo nenhum — mesmo desenho do estorno.
CONTRATO_POST_ENCERRAR_COMPETENCIA = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no fechamento de competência",
)
CONTRATO_POST_ENTREGAR_COMPETENCIA = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na entrega de competência",
)
# Reabrir é a ÚNICA das três com corpo: `motivo` é obrigatório (critério 5).
CONTRATO_POST_REABRIR_COMPETENCIA = ContratoDeRequisicao(
    campos={"motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reabertura de competência",
)

# DL-043 fatia 1: criação de vigência de parâmetro contábil — os cinco
# campos que `registrar_parametro_contabil` exige, nenhum outro (política
# dos cinco dicionários, BL-196).
CONTRATO_POST_PARAMETRO_CONTABIL = ContratoDeRequisicao(
    campos={
        "periodicidade_zeramento",
        "conta_resultado_do_exercicio",
        "conta_lucros_acumulados",
        "conta_prejuizos_acumulados",
        "vigencia_inicio",
    },
    contexto="no parâmetro contábil",
)
# Encerrar vigência é rota de AÇÃO, sem corpo — mesmo desenho do estorno e
# do fechamento de competência.
CONTRATO_POST_ENCERRAR_VIGENCIA_PARAMETRO_CONTABIL = ContratoDeRequisicao(
    campos=frozenset(),
    contexto="no encerramento de vigência do parâmetro contábil",
)
# DL-043 fatia 2: `zerar_resultado` (POST) não recebe corpo — ano/mês vêm
# da URL, como o fechamento de competência.
CONTRATO_POST_ZERAR_RESULTADO = ContratoDeRequisicao(
    campos=frozenset(),
    contexto="no zeramento do resultado",
)
# A7 (auditoria DL-045, rodada 1): PATCH da linha da DRE de uma conta já
# existente — um campo só, a própria conta vem da URL.
CONTRATO_PATCH_CLASSIFICACAO_DRE = ContratoDeRequisicao(
    campos={"classificacao_dre"},
    contexto="na classificação da linha da DRE",
)
# DL-048 (fatia D8): mesmo contrato da DRE para a linha da DLPA — um campo só,
# e a própria conta vem da URL. Um contrato NOVO (e não o mesmo) porque a
# política recusa chave desconhecida por NOME: aceitar `classificacao_dre` num
# PATCH de DLPA gravaria a linha errada em silêncio.
CONTRATO_PATCH_CLASSIFICACAO_DLPA = ContratoDeRequisicao(
    campos={"classificacao_dlpa"},
    contexto="na classificação da linha da DLPA",
)
# DL-061 (fatia 2, E18): PATCH da COLUNA da DMPL — um campo só, e a própria
# conta vem da URL. Contrato NOVO (e não o mesmo da DLPA) pelo motivo de
# sempre: a política recusa chave desconhecida por NOME, e um corpo com
# `classificacao_dlpa` neste PATCH tem de ser recusado, não aplicado à
# classificação errada em silêncio.
CONTRATO_PATCH_CLASSIFICACAO_DMPL = ContratoDeRequisicao(
    campos={"classificacao_dmpl"},
    contexto="na classificação da coluna da DMPL",
)
# DL-066 (etapa 2): PATCH dos TRÊS campos da DFC de uma conta — contrato
# NOVO (e não o mesmo da DMPL) pelo motivo de sempre: a política recusa
# chave desconhecida por NOME, e um corpo com `classificacao_dmpl` neste
# PATCH tem de ser recusado, não aplicado à classificação errada em silêncio.
# Os três campos juntos porque `classificar_conta_na_dfc` recebe o ESTADO
# DESEJADO completo e grava com UMA trilha — a fusão do PATCH parcial é na
# view, que é quem conhece a conta.
CONTRATO_PATCH_CLASSIFICACAO_DFC = ContratoDeRequisicao(
    campos={"caixa_e_equivalentes", "classificacao_dfc", "item_de_resultado_sem_caixa"},
    contexto="na classificação da DFC",
)
# DL-061 (fatia 2, BL-605): PUT da marcação manual da DMPL — o corpo é o
# CONJUNTO completo de marcações do lançamento (substituição atômica); o
# lançamento vem da URL. A lista de cada marcação é validada pelo serializer
# (que recusa também a chave desconhecida DENTRO de cada item).
CONTRATO_PUT_MARCACAO_DMPL = ContratoDeRequisicao(
    campos={"marcacoes"},
    contexto="na marcação da DMPL",
)
# DELETE da marcação: rota de AÇÃO — o que limpar vem da URL, e o corpo não
# tem contrato nenhum (`campos=frozenset()` é "nenhum campo aceito"), mesmo
# desenho do estorno. Quem mandar Idempotency-Key aqui precisa saber que ela
# não tem efeito: esta rota não tem contrato de idempotência.
CONTRATO_DELETE_MARCACAO_DMPL = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na limpeza da marcação da DMPL",
)


def _recusar_dado_nao_contratado(request, contrato):
    """Aplica a política de `apps.core.requisicao` e traduz o veredito para o
    protocolo desta superfície (400 em JSON do DRF).

    A tradução é de UMA linha de propósito: o módulo julga e não sabe
    responder HTTP; esta função é a única ponte entre ele e o DRF nesta API.
    """
    try:
        recusar_dado_nao_contratado(request, contrato)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _sem_campos_desconhecidos(dados, campos_permitidos, *, contexto):
    """Recusa (`DRFValidationError`, nomeando a chave) se `dados` for um
    `dict` com alguma chave fora de `campos_permitidos`.

    Delega o julgamento a `apps.core.requisicao.recusar_campos_nao_
    contratados` (BL-196) — a subtração de conjuntos e o texto da mensagem
    moram lá, num lugar só. Esta função continua existindo porque o corpo da
    API é ANINHADO: cada item da lista de partidas é um dicionário próprio,
    que o contrato do topo não alcança."""
    try:
        recusar_campos_nao_contratados(dados, campos_permitidos, contexto=contexto)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _como_moeda(valor):
    """Formata um Decimal monetário como string com duas casas.

    SQLite (usado em desenvolvimento local) não preserva a escala de um
    DecimalField em agregações (`Sum`) como o PostgreSQL faz; sem esta
    normalização, um saldo exato como 1000.00 poderia virar "1000" só por
    causa do banco usado no ambiente, mascarando o valor real.
    """
    return str(Decimal(valor).quantize(Decimal("0.01")))


def _aviso_de_movimento_fora_do_periodo(*, empresa, inicio, fim, ids_contas=None):
    """Serializa `movimento_fora_do_periodo` para a resposta JSON (BL-198).

    Devolve `None` quando não há nada fora do período — a chave existe SEMPRE
    na resposta, com `null`, porque um cliente que só a veja quando há
    movimento não tem como distinguir "não há" de "esta versão do servidor
    não responde isso".

    Por que a API também recebe o aviso, e não só a tela (item 2 da DE-034):
    o fato invisível é invisível pela porta da API do mesmo jeito. Um cliente
    que pede o Diário de janeiro recebe um total que CONCILIA e nenhuma pista
    de que existe um lançamento de 5.000,00 em `9999-12-31` — foi exatamente
    isso que o auditor mediu, e fechar só na tela repetiria o vício que o
    R6-2 nomeou.

    As datas saem em `isoformat()` (AAAA-MM-DD), como todas as outras datas
    desta API — nunca `date` cru, que o encoder JSON do DRF converteria por
    conta própria.

    O recorte por conta entra aqui como `ids_contas` — o conjunto já apurado
    por `apurar_razao` (chave `ids_contas`, BL-212) —, nunca como a `Conta`:
    esta serialização não mostra nada da conta, então receber a conta só
    serviria para `movimento_fora_do_periodo` percorrer a subárvore uma
    SEGUNDA vez (uma consulta por nível de profundidade), que é a regressão
    de desempenho da BL-212. Sem `ids_contas`, o recorte é a empresa inteira
    (Diário e Balancete).
    """
    fora = movimento_fora_do_periodo(empresa=empresa, inicio=inicio, fim=fim, ids_contas=ids_contas)
    if fora is None:
        return None

    def _lado(dados):
        if dados is None:
            return None
        return {
            "quantidade": dados["quantidade"],
            "data_extrema": dados["data_extrema"].isoformat(),
        }

    return {"anteriores": _lado(fora["anteriores"]), "posteriores": _lado(fora["posteriores"])}


def _saldo_absoluto_com_natureza(saldo_assinado, natureza_cadastrada):
    """Converte um saldo ASSINADO (a convenção interna de `services.py`:
    positivo quando o saldo está do mesmo lado da natureza CADASTRADA da
    conta — ver `_saldo_por_natureza`/`_sinal_do_item`) para o par que a
    apresentação contábil exige (RC-61 / BL-77, critério 5 do plano
    DL-017): `(valor_absoluto: Decimal, letra: "D" | "C" | None)`. O valor
    NUNCA é negativo — quem consome (a resposta HTTP hoje, a tela na fase B)
    mostra a letra ao lado do número, nunca o sinal.

    A natureza APURADA (a letra devolvida aqui) não é a mesma coisa que a
    natureza CADASTRADA da conta (`Conta.natureza`, o parâmetro
    `natureza_cadastrada`): uma conta DEVEDORA cujo movimento do período
    pesa mais para o crédito apura saldo CREDOR — mesmo continuando
    cadastrada como devedora. É o coração do caso de referência do Fred
    (docs/projeto/mapa-funcional-contabil.md, "Conta retificadora,
    apresentação de saldo e implantação"): a conta retificadora de
    depreciação é cadastrada com natureza CONTRÁRIA à do grupo de
    propósito, e o GRUPO (que tem natureza própria, devedora) apura saldo
    devedor mesmo absorvendo o crédito da retificadora — a natureza apurada
    do grupo vem do SINAL do resultado, nunca copiada de um filho.
    A mesma lógica vale para uma conta isolada, sem filhos: se o crédito do
    período supera o débito de uma conta cadastrada devedora, ela apura
    saldo credor, ponto.

    Saldo exatamente ZERO não tem lado — não existe "meio D, meio C" nem um
    lado mais correto que o outro para apresentar. Decisão explícita deste
    módulo (não há regra contábil que escolha um lado para zero): devolve
    `letra=None`. Quem for renderizar (a fase B) não deve mostrar indicador
    nenhum quando `letra` vier `None` — mostrar "D" ou "C" para saldo zero
    seria inventar uma informação que os dados não sustentam.
    """
    if saldo_assinado == 0:
        return saldo_assinado, None

    letra_cadastrada = "D" if natureza_cadastrada == NaturezaConta.DEVEDORA else "C"
    if saldo_assinado > 0:
        return saldo_assinado, letra_cadastrada

    # Negativo, na convenção assinada dos serviços: o saldo apurado está do
    # lado CONTRÁRIO ao cadastrado. Inverte o sinal (nunca devolve negativo)
    # e a letra.
    letra_apurada = "C" if letra_cadastrada == "D" else "D"
    return -saldo_assinado, letra_apurada


def _periodo_obrigatorio(request):
    """Extrai e valida `inicio`/`fim` da querystring das saídas com período.

    DE-016: o período passa a ser OBRIGATÓRIO no Diário, Razão e Balancete —
    quebra deliberada do contrato anterior. Ausente, malformado (formato
    diferente de AAAA-MM-DD) ou invertido (`inicio > fim`) sempre vira 400
    com mensagem útil, nunca 500 nem um período implícito (critério 2 do
    plano DL-015).

    A conversão em si é delegada a `apps.core.datas.para_data` (BL-133,
    achado A9 da auditoria DL-017 rodada 4 / DE-030 estendida a dado
    tipado): antes, este módulo tinha seu PRÓPRIO `_PADRAO_DATA_SIMPLES` e
    sua própria chamada a `date.fromisoformat`, e `apps.empresas.views`
    não tinha proteção nenhuma — duas cópias da mesma regra (uma delas
    frouxa) é exatamente o que a DE-026 existe para impedir.
    """
    bruto_inicio = request.query_params.get("inicio")
    bruto_fim = request.query_params.get("fim")
    if not bruto_inicio or not bruto_fim:
        raise DRFValidationError("Informe 'inicio' e 'fim' (formato AAAA-MM-DD) na querystring.")

    try:
        inicio = para_data(bruto_inicio)
    except DataInvalida as exc:
        raise DRFValidationError(f"'inicio' inválido: {exc}") from exc
    try:
        fim = para_data(bruto_fim)
    except DataInvalida as exc:
        raise DRFValidationError(f"'fim' inválido: {exc}") from exc

    if inicio > fim:
        raise DRFValidationError(
            f"'inicio' ({inicio.isoformat()}) não pode ser posterior a 'fim' ({fim.isoformat()})."
        )
    return inicio, fim


def _nivel_opcional(request):
    """Extrai e valida o parâmetro opcional `nivel` do Balancete.

    Ausente (ou vazio), devolve `None` — sem recorte de hierarquia. Presente
    e malformado (não inteiro, ou menor que 1) vira 400: a raiz do plano de
    contas é o nível 1, não existe nível zero ou negativo.
    """
    bruto = request.query_params.get("nivel")
    if not bruto:
        return None
    if not _PADRAO_NIVEL_SIMPLES.fullmatch(bruto):
        # Recusa ANTES de `int()` (achado 12): "1_0" seria interpretado como
        # 10 (separador de dígitos do Python, PEP 515), e " 2 "/"+2" seriam
        # aceitos em silêncio — reinterpretação que o contrato não promete.
        raise DRFValidationError(f"'nivel' inválido: '{bruto}' não é um número inteiro.")
    try:
        nivel = int(bruto)
    except ValueError as exc:
        raise DRFValidationError(f"'nivel' inválido: '{bruto}' não é um número inteiro.") from exc
    if nivel < 1 or nivel > NIVEL_MAXIMO:
        # achado novo 11: limite SUPERIOR explícito, além do mínimo já
        # existente — sem ele, um valor absurdo como
        # "999999999999999999999999999999" (inteiro Python válido, sem
        # limite de tamanho) seria aceito sem recusa nenhuma.
        raise DRFValidationError(
            f"'nivel' deve ser um número inteiro entre 1 e {NIVEL_MAXIMO} "
            "(a raiz do plano de contas é o nível 1)."
        )
    return nivel


# Faixa de `ano`/`mes` na URL de fechar/reabrir/entregar competência — as
# MESMAS faixas das duas `CheckConstraint` de `Competencia.Meta`
# (`competencia_mes_entre_1_e_12`, `competencia_ano_entre_1970_e_2999`).
# Validada AQUI, na fronteira, para que um mês/ano fora da faixa vire 400
# com mensagem específica ("mês inválido") em vez do 400 genérico de
# "corrida entre requisições" que `obter_ou_criar_competencia` devolve para
# a violação de `CheckConstraint` (ver o docstring dela) — mesmo raciocínio
# de `_nivel_opcional`/`_periodo_obrigatorio`: julgar o formato na fronteira
# da API, não deixar o banco reportar por baixo.
_MES_MINIMO, _MES_MAXIMO = 1, 12
_ANO_MINIMO, _ANO_MAXIMO = 1970, 2999


def _validar_ano_mes(ano, mes):
    """Recusa (400) `ano`/`mes` fora da faixa que `Competencia` aceita.

    `ano`/`mes` já chegam como `int` aqui — o `<int:...>` do urlconf
    (`apps/contabilidade/urls.py`) já recusou texto não numérico antes de
    a view rodar (404, comportamento padrão do conversor `int` do Django).
    """
    if not (_MES_MINIMO <= mes <= _MES_MAXIMO):
        raise DRFValidationError(
            f"'mes' inválido: {mes} — deve estar entre {_MES_MINIMO} e {_MES_MAXIMO}."
        )
    if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
        raise DRFValidationError(
            f"'ano' inválido: {ano} — deve estar entre {_ANO_MINIMO} e {_ANO_MAXIMO}."
        )


# Consulta é liberada a qualquer papel vinculado ao escritório ativo;
# lançar/editar o plano de contas ou a escrituração é restrito a quem
# efetivamente cuida da contabilidade do escritório.
PodeEscriturar = papel_permitido(
    Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO
)


# DL-016 fatia 1, critério 8: fechar, reabrir e entregar competência exigem
# papel autorizado, verificado NO SERVIDOR (nunca só escondendo botão na
# tela — a tela nem existe ainda, esta fatia é só servidor).
#
# RC-102, CONFIRMADO pelo Fred em 2026-09-20 — resposta literal
# "Administrador e gestor pode, analista não" — depois de ter sido hipótese
# (HI-17) até este ponto da etapa: os papéis autorizados são ADMINISTRADOR e
# GESTOR. ANALISTA lança (está em `PodeEscriturar`, acima) e não fecha/
# reabre/entrega; FINANCEIRO, PARALEGAL e CLIENTE nunca estiveram em
# questão para esta operação e ficam de fora pela mesma resposta.
#
# DL-053 / RC-146: a lista de papéis vive em `apps.core.papeis_de_fechamento`
# (fonte única, compartilhada com o fechamento de mês do livro-caixa); o
# comportamento aqui é o MESMO de antes — só a lista saiu deste arquivo.
PodeFecharCompetencia = papel_permitido(*PAPEIS_QUE_FECHAM_PERIODO)


# Leitura das quatro saídas contábeis com período (Diário, Razão, Balancete,
# conferência) — e, desde o achado novo 2 da rodada 2, TAMBÉM o `GET` de
# `ContaListCreateView` (plano de contas) e de `LancamentoListCreateView`
# (Diário "crú", sem período): DE-020 §4, corrigida. Decisão imediata e
# conservadora do arquiteto-senior: o papel CLIENTE deixa de ler a
# contabilidade — antes, qualquer usuário com vínculo de papel CLIENTE no
# escritório lia o Diário (com histórico), o Razão e o Balancete completos
# de TODOS os outros clientes do mesmo escritório, o que é sigilo de
# cliente contra cliente, não apenas permissão fina.
#
# A DE-020 §4 original listava só as QUATRO rotas criadas por esta etapa
# (Diário, Razão, Balancete, conferência) — e ficou pela metade: o CLIENTE
# continuava lendo a MESMA escrituração completa por `GET .../lancamentos/`
# (sem período, com histórico e partidas) e o plano de contas por
# `GET .../contas/`. O critério correto, daqui em diante: NENHUMA rota
# devolve escrituração, plano de contas ou saldo a quem não pode ler
# contabilidade — independentemente de quando a rota foi criada. As rotas de
# ESCRITURAÇÃO (POST das duas views abaixo) continuam usando `PodeEscriturar`,
# sem mudança — só a LEITURA passou a exigir este papel.
#
# Os demais papéis vinculados ao escritório seguem lendo, até uma matriz fina
# por módulo (PE-36).
#
# DE-026 / DL-017 fase A, critério 1: esta classe NÃO decide mais nada
# sozinha — ela só traduz `apps.contabilidade.permissoes.
# papel_pode_ler_contabilidade` (a fonte única da regra, sem depender de
# DRF) para o protocolo de permissão do DRF. A tela (fase B) vai chamar a
# MESMA função diretamente, sem passar pelo DRF. Ver o docstring de
# `permissoes.py` para o contrato completo, e
# `tests/test_permissoes_contabilidade.py` para o teste que prova que os
# dois lados decidem igual.
class PodeLerContabilidade(BasePermission):
    message = "Papel sem permissão para ler a contabilidade."

    def has_permission(self, request, view):
        return papel_pode_ler_contabilidade(getattr(request, "papel", None))


class ContaListCreateView(EmpresaEscopadaContabilMixin, generics.ListCreateAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = ContaSerializer

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturar())
        else:
            # achado novo 2: leitura do plano de contas segue a MESMA regra
            # das outras saídas contábeis — o papel CLIENTE não lê.
            permissions.append(PodeLerContabilidade())
        return permissions

    def get_queryset(self):
        return Conta.objects.filter(empresa=self.get_empresa())

    def post(self, request, *args, **kwargs):
        # BL-196: a política dos cinco dicionários ANTES de qualquer
        # gravação. Medido pelo auditor nesta rota: querystring em POST,
        # `empresa: 999`, `xpto` e `id: 4242` no corpo → **201 em todos**,
        # ignorados em silêncio. `id` é especialmente ruim: quem o envia
        # acredita ter escolhido o identificador do registro.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_CONTA)
        return super().post(request, *args, **kwargs)

    def get_serializer_context(self):
        # A empresa do contexto vem do escopo da URL, já revalidada contra o
        # escritório ativo (EmpresaEscopadaMixin.get_empresa()) — nunca de um
        # campo enviado pelo cliente. É o que permite ao serializer recusar
        # `conta_pai` de outra empresa (BL-40) sem confiar no payload.
        context = super().get_serializer_context()
        context["empresa"] = self.get_empresa()
        return context

    def perform_create(self, serializer):
        # `restricao_como_400` (achado R5-5 da auditoria DL-017 rodada 5,
        # BL-144 / DE-034): antes, esta view não tinha `try` nenhum —
        # `codigo` repetido na mesma empresa (`Conta.Meta.constraints`,
        # `codigo_unico_por_empresa`) derrubava com `IntegrityError` cru,
        # 500. Medido sob concorrência (4 POSTs simultâneos com o mesmo
        # código): `500, 201, 500, 500` — a integridade do dado nunca foi
        # violada (a constraint segurou), só a RESPOSTA quebrava. O
        # `transaction.atomic()` isola o `IntegrityError` num savepoint.
        #
        # BL-14 (DL-024): o `registrar()` foi MOVIDO para dentro do mesmo
        # `transaction.atomic()` que grava a Conta. Antes, qualquer falha
        # no INSERT do `RegistroAuditoria` deixava a Conta gravada e a
        # trilha silenciosamente vazia — o plano de contas dizia uma
        # coisa, a trilha dizia outra. Agora ambos são uma só operação
        # atômica. O `RestricaoViolada` continua sendo traduzido para 400
        # como antes; qualquer outra exceção (incluindo a do `registrar()`)
        # propaga como 500.
        try:
            # A mensagem vem do registro único `apps.core.restricoes.
            # MENSAGENS_DE_RESTRICAO` (BL-204): antes era um literal aqui, e
            # literal espalhado por view é exatamente como as duas
            # `CheckConstraint` de CNPJ ficaram sem tradução — não havia lugar
            # nenhum onde alguém pudesse ver a lista inteira e notar a falta.
            with (
                transaction.atomic(),
                restricao_como_400(mensagens_de("codigo_unico_por_empresa")),
            ):
                conta = serializer.save(empresa=self.get_empresa())
                registrar(acao="conta.criada", objeto=conta, request=self.request)
        except RestricaoViolada as exc:
            raise DRFValidationError({"codigo": [str(exc)]}) from exc


def _extrair_itens(payload_itens, empresa):
    """Valida e converte os itens recebidos da API em dados prontos para o serviço."""
    if not isinstance(payload_itens, list) or len(payload_itens) < 2:
        raise DRFValidationError("Informe ao menos duas partidas (itens).")

    itens = []
    for item in payload_itens:
        _sem_campos_desconhecidos(item, CAMPOS_PERMITIDOS_ITEM, contexto="em um item")

        try:
            conta_bruta = item["conta"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Conta inválida para esta empresa.") from exc

        try:
            # `para_id` (achado R5-3 da auditoria DL-017 rodada 5, BL-142 /
            # DE-034): antes, `item["conta"]` ia direto para `.get(pk=...)`,
            # protegido só pelo `except (..., TypeError, ValueError)`
            # abaixo — o que barra texto não numérico, mas NÃO barra
            # reinterpretação silenciosa: `1.9` (número JSON) gravava na
            # conta 1 (Postgres/psycopg truncam o float ao comparar com a
            # coluna inteira), `true` gravava na conta 1 (`bool` é `int` em
            # Python), `" 1 "`/`"+1"` gravavam na conta 1, e `"٢"`/`"２"`
            # (dígito Unicode) gravavam na conta 2 — sempre HTTP 201, sem
            # aviso. É a MESMA classe que a tela e `apps.tenancy` já
            # fecham com `para_id` — só a API de contabilidade não usava
            # (dois comentários de `views_web.py` afirmavam que usava; não
            # usava — ver a correção desses comentários, pedida ao
            # `especialista-frontend`).
            conta_id = para_id(conta_bruta)
        except IdentificadorInvalido as exc:
            raise DRFValidationError(f"Conta inválida para esta empresa: {exc}") from exc

        try:
            conta = Conta.objects.get(pk=conta_id, empresa=empresa)
        except Conta.DoesNotExist as exc:
            raise DRFValidationError("Conta inválida para esta empresa.") from exc

        try:
            valor_bruto = item["valor"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Valor inválido em um dos itens.") from exc

        # DE-030 (achado R3-3, auditoria DL-017 rodada 3): esta view NÃO
        # constrói `Decimal` por conta própria — entrega TEXTO a
        # `apps.core.dinheiro.para_decimal`, o único julgador de formato
        # monetário do sistema (mesmo módulo que a tela usa, DE-027/DE-029).
        # Antes desta correção, o código fazia `str(valor_bruto)` e depois
        # `Decimal(texto)`: um `valor` enviado como NÚMERO JSON (não texto)
        # virava `float` de precisão binária ao ser decodificado pelo
        # parser de JSON, ANTES de qualquer checagem — e para magnitudes
        # grandes (medido: acima de ~7×10¹³) o `float` já tinha perdido a
        # última casa decimal. `str()` desse float reproduzia o valor JÁ
        # CORROMPIDO, não o texto que o cliente pretendia enviar, e a
        # recusa de notação científica que este arquivo anuncia era
        # contornada simplesmente trocando aspas por número (`1e3` como
        # texto: 400; `1e3` como número JSON: aceito, virava 1000,00). Por
        # isso `valor` que não chegue como `str` é recusado AQUI, antes de
        # qualquer conversão — nunca convertido para texto e reinterpretado.
        if not isinstance(valor_bruto, str):
            raise DRFValidationError(
                f"Valor inválido em um dos itens: {valor_bruto!r} precisa ser "
                'enviado como TEXTO (ex.: "100.00"), nunca como número JSON — '
                "um número perde precisão ao ser decodificado pelo parser JSON, "
                "antes mesmo de chegar a este servidor."
            )
        try:
            valor = para_decimal(valor_bruto)
        except ValorMonetarioInvalido as exc:
            # `para_decimal` já recusa: formato fora do decimal simples
            # (sinal opcional, dígitos, ponto decimal opcional — sem
            # espaços, "_" como separador de dígitos ou notação científica,
            # achado 7 da auditoria de 2026-09-12) e valor não finito
            # (`NaN`/`Infinity`/`-Infinity`, achado BL-44/N3). A mensagem do
            # próprio módulo monetário já é específica; só acrescenta o
            # contexto de que é um item do lote.
            raise DRFValidationError(f"Valor inválido em um dos itens: {exc}") from exc

        if abs(valor) >= LIMITE_MAGNITUDE_VALOR:
            raise DRFValidationError(
                f"Valor {valor} é grande demais para um item de lançamento; o "
                f"módulo deve ser menor que {LIMITE_MAGNITUDE_VALOR}."
            )

        try:
            # `para_escolha` (achado R5-2, BL-141 / DE-034): esta checagem
            # já era segura por acidente de forma (pertencimento a uma
            # lista fechada nunca levanta exceção, seja qual for o tipo do
            # valor testado) — mas era uma segunda cópia manual do mesmo
            # padrão que `regime`, em `apps.empresas.views`, não tinha.
            # Migrada para o módulo compartilhado para não deixar um
            # terceiro campo de `choices` reinventar a checagem por conta
            # própria no futuro.
            tipo = para_escolha(item.get("tipo"), TipoPartida.values, nome_campo="tipo")
        except EscolhaInvalida as exc:
            raise DRFValidationError(str(exc)) from exc

        itens.append({"conta": conta, "tipo": tipo, "valor": valor})
    return itens


class LancamentoListCreateView(EmpresaEscopadaContabilMixin, generics.ListAPIView):
    """Diário: lista cronológica dos lançamentos da empresa; POST cria um novo."""

    permission_classes = [TemEscritorioAtivo]
    serializer_class = LancamentoContabilSerializer

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturar())
        else:
            # achado novo 2: esta rota devolvia a escrituração completa
            # (histórico, valores, partidas) a qualquer papel vinculado ao
            # escritório, inclusive CLIENTE — era o "caminho fácil" que
            # continuava aberto depois da DE-020 §4 original, porque a
            # decisão citava só as quatro rotas novas (Diário, Razão,
            # Balancete, conferência) e não esta, que já existia antes.
            permissions.append(PodeLerContabilidade())
        return permissions

    def get_queryset(self):
        return LancamentoContabil.objects.filter(empresa=self.get_empresa()).prefetch_related(
            "itens__conta"
        )

    def post(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        dados = request.data
        # BL-196: o corpo já era julgado aqui (R5-6/BL-145); o que faltava
        # eram os OUTROS dicionários da mesma requisição — o auditor mediu
        # `POST .../lancamentos/?conta_3=…&xpto=1` devolvendo **201**, com o
        # par de partidas da querystring nem lido nem recusado. A política
        # inteira agora vem de um lugar só (`apps.core.requisicao`), com o
        # MESMO contrato de campos de antes.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_LANCAMENTO)
        itens = _extrair_itens(dados.get("itens"), empresa)

        historico = dados.get("historico", "")
        if not isinstance(historico, str):
            # `len()` funciona para list/dict/etc. (devolveria uma contagem
            # sem sentido, nunca um erro) e explode com `TypeError` para
            # número ou `None` — em qualquer um dos dois casos o valor
            # seguiria para `criar_lancamento` e para o INSERT do Postgres
            # com um tipo que a coluna não aceita, virando 500 em vez de 400
            # (mesma classe de defeito do BL-44 / achado N3: tipo de entrada
            # inesperado não capturado na fronteira da API).
            raise DRFValidationError("O campo 'historico' deve ser texto.")
        if len(historico) > TAMANHO_MAXIMO_HISTORICO:
            # Sem esta checagem, o texto seguiria até o INSERT e o Postgres
            # rejeitaria com `DataError: value too long for type character
            # varying(300)` — 500 em vez de 400 (BL-44 / achado N3).
            raise DRFValidationError(
                f"O histórico não pode ter mais de {TAMANHO_MAXIMO_HISTORICO} caracteres."
            )

        try:
            data_bruta = dados["data"]
        except (KeyError, TypeError) as exc:
            raise DRFValidationError("Informe 'data' no formato AAAA-MM-DD.") from exc
        try:
            # `para_data` (achado A9 da auditoria DL-017 rodada 4, BL-133):
            # antes, este trecho chamava `date.fromisoformat` direto, sem a
            # gramática estrita que `_periodo_obrigatorio` já aplicava a
            # `inicio`/`fim` — o mesmo módulo tinha a defesa certa num lugar
            # e não noutro. Sem ela, uma data de semana ISO
            # ("2026-W01-1") era aceita e REINTERPRETADA em silêncio para
            # outro ano/mês/dia (medido: grava "2025-12-29" para quem
            # digitou "2026-W01-1") — corrupção silenciosa da DATA de um
            # lançamento contábil, pior que o 500 que o `except` antigo já
            # evitava para tipo errado (`TypeError`, número JSON etc., que
            # `para_data` também recusa, com `DataInvalida`, não mais
            # deixando vazar cru).
            data_lancamento = para_data(data_bruta)
        except DataInvalida as exc:
            raise DRFValidationError(f"'data' inválida: {exc}") from exc

        # Idempotência opcional (BL-41): o cliente decide quando quer garantia
        # de não duplicar em caso de repetição de rede ou duplo clique,
        # enviando um cabeçalho próprio. Sem o cabeçalho, o comportamento é
        # exatamente o de antes (cada POST cria um lançamento) — contrato
        # compatível, nada muda para quem não envia a chave.
        #
        # `strip()` + tratar string vazia como ausente (achado A4): " " e "  "
        # não podem contar como duas chaves DISTINTAS — um cliente que só
        # envia espaço em branco não pretendia usar idempotência nenhuma.
        chave_idempotencia = (request.headers.get("Idempotency-Key") or "").strip() or None
        if chave_idempotencia and len(chave_idempotencia) > TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA:
            raise DRFValidationError(
                f"O cabeçalho Idempotency-Key não pode ter mais de "
                f"{TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA} caracteres."
            )

        # O serviço informa se de fato criou ou reaproveitou um lançamento
        # existente (mesma Idempotency-Key). A trilha de auditoria e o
        # status HTTP precisam refletir o resultado real, nunca "criado" por
        # padrão: um registro de auditoria que afirma criação que não
        # aconteceu deixa de sustentar prova (AGENTS.md §11), e 201 numa
        # repetição afirmaria um fato falso. Repetição não é erro — é
        # informação útil (duplo clique, tempestade de retentativa) e por
        # isso vira uma ação própria, rastreável, em vez de ficar oculta
        # atrás de "lancamento.criado". `lancamento.criado_agora` é acessado
        # direto (sem `getattr(..., True)`): `criar_lancamento` sempre define
        # este atributo antes de devolver o objeto, e um padrão "True" por
        # omissão falharia ABERTO exatamente no mesmo sentido do defeito que
        # esta correção existe para fechar (achado A7).
        #
        # BL-14 (DL-024) e DL-052 (M1): `criar_lancamento` e `registrar()`
        # rodam dentro do MESMO `transaction.atomic()` (o `with` abaixo
        # envolve as duas chamadas). Antes, qualquer falha no INSERT do
        # `RegistroAuditoria` deixava o lançamento gravado e a trilha
        # silenciosamente vazia — a contabilidade dizia uma coisa, a trilha
        # dizia outra. O comentário original do BL-14 afirmava que o `with`
        # já cobria o `criar_lancamento`, mas ele só cobria o `registrar()`:
        # `criar_lancamento` (`@transaction.atomic`) comitava sozinho, por
        # ser a transação mais externa (`ATOMIC_REQUESTS` desligado), antes
        # de a trilha ser tentada. Agora a falha do `registrar()` reverte
        # também o lançamento. Os `except` de negócio ficam FORA do `with`:
        # são recusas pré-INSERT (nada a reverter) e a transação já saiu
        # limpa quando elas viram resposta HTTP; qualquer outra exceção
        # (incluindo a do `registrar()`) propaga e desfaz tudo.
        status_code = None
        try:
            with transaction.atomic():
                lancamento = criar_lancamento(
                    empresa=empresa,
                    data=data_lancamento,
                    historico=historico,
                    itens=itens,
                    criado_por=request.user,
                    chave_idempotencia=chave_idempotencia,
                )
                if lancamento.criado_agora:
                    registrar(acao="lancamento.criado", objeto=lancamento, request=request)
                    status_code = status.HTTP_201_CREATED
                else:
                    registrar(
                        acao="lancamento.criacao_repetida",
                        objeto=lancamento,
                        request=request,
                        # Só um hash curto da chave, nunca a chave crua (achado A8):
                        # é uma string arbitrária vinda do cliente, e `registrar()`
                        # só deve receber dados não sensíveis. O hash ainda permite
                        # correlacionar repetições da MESMA chave entre registros.
                        detalhes={
                            "chave_idempotencia_hash": hashlib.sha256(
                                chave_idempotencia.encode("utf-8")
                            ).hexdigest()[:12]
                        },
                    )
                    status_code = status.HTTP_200_OK
        except ChaveIdempotenciaConflitante as exc:
            # Conflito de estado (a chave já existe com outro conteúdo), não
            # entrada inválida: 409, não 400 — e nada foi gravado (achado A2).
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CompetenciaEncerrada as exc:
            # DL-016 fatia 1, critério 1: mesma classe de conflito de estado
            # que `ChaveIdempotenciaConflitante` — 409, e nada foi gravado (a
            # recusa acontece DENTRO da transação de `criar_lancamento`,
            # antes de qualquer INSERT).
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except LancamentoInvalido as exc:
            raise DRFValidationError(str(exc)) from exc

        serializer = self.get_serializer(lancamento)
        return Response(serializer.data, status=status_code)


class EstornarLancamentoView(EmpresaEscopadaContabilMixin, APIView):
    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def post(self, request, empresa_id, lancamento_id):
        # BL-196: rota de ação, e mesmo assim entra na política — um corpo
        # com `data` ou `historico` aqui sugere ao cliente que ele está
        # escolhendo a data do estorno, e ela é decidida pelo servidor
        # (RC-78). Aceitar e ignorar seria a mesma classe de defeito de
        # sempre, com consequência contábil: o cliente acreditaria ter
        # datado o estorno.
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ESTORNO)
        empresa = self.get_empresa()
        lancamento = get_object_or_404(LancamentoContabil, pk=lancamento_id, empresa=empresa)

        # DL-052 (M1): estorno e trilha na MESMA transação. `estornar_lancamento`
        # é `@transaction.atomic`, mas como esta view é a transação mais
        # externa (`ATOMIC_REQUESTS` está desligado) o estorno era COMITADO ao
        # retornar dele; se `registrar` falhasse em seguida, a resposta era
        # 500 com o estorno já gravado e nenhum registro na trilha — e, como
        # o lançamento "já foi estornado", o contador não conseguia refazer.
        # Com o `atomic` externo, a falha da trilha desfaz o estorno. Os
        # `except` ficam FORA do `with`: a recusa de negócio sai da transação
        # (que reverte sem gravar nada) antes de virar resposta HTTP.
        # DL-089 / BL-73: o papel do escritório ativo (resolvido pelo middleware, nunca do
        # corpo) decide se pode estornar lançamento de origem automática. A recusa sai do
        # `atomic` sem nada gravado e vira 403.
        try:
            with transaction.atomic():
                estorno = estornar_lancamento(
                    lancamento,
                    criado_por=request.user,
                    papel=getattr(request, "papel", None),
                )
                registrar(
                    acao="lancamento.estornado",
                    objeto=estorno,
                    request=request,
                    detalhes={
                        "lancamento_original_id": lancamento.pk,
                        "origem": estorno.origem,
                    },
                )
        except CompetenciaEncerrada as exc:
            # DL-016 fatia 1, critério 2: o estorno É um lançamento novo, e a
            # competência que decide é a DELE (a data do estorno), não a do
            # original — ver o comentário em `estornar_lancamento`. 409,
            # nada gravado.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except EstornoDeOrigemAutomaticaNaoPermitido as exc:
            # DL-089 (A8, BL-73): a TENTATIVA negada também fica na trilha, porque é ela que
            # mostra quem tentou desfazer o que o sistema gerou. Fica FORA do `atomic` acima,
            # que já reverteu sem gravar nada; senão a negativa seria desfeita junto com ele.
            # Só papel e identificadores: nada sensível em `detalhes`.
            registrar(
                acao="lancamento.estorno_negado",
                objeto=lancamento,
                request=request,
                detalhes={
                    "papel": str(getattr(request, "papel", None) or ""),
                    "origem": lancamento.origem,
                    "motivo": "origem_automatica_sem_permissao",
                    # Reconferência, R3: qual regra fez o lançamento contar como automático.
                    "criterio": exc.criterio,
                },
            )
            raise PermissionDenied(str(exc)) from exc
        except LancamentoInvalido as exc:
            raise DRFValidationError(str(exc)) from exc

        serializer = LancamentoContabilSerializer(estorno)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def _competencia_como_dict(competencia):
    """Serialização mínima de `Competencia` para as três rotas de ação
    abaixo (DL-016 fatia 1). Sem `serializers.ModelSerializer` de propósito:
    não há entrada a validar (o corpo já foi julgado pelo contrato de cada
    view), só saída — um dict simples evita um serializer que ninguém usa
    para escrever.

    `fechada_por`/`entregue_por` saem como ID (nunca o objeto `User`
    inteiro nem o e-mail): as demais respostas desta API também não
    expõem dados de usuário além do necessário, e "quem" já está na trilha
    de auditoria com o contexto completo.
    """
    return {
        "empresa": competencia.empresa_id,
        "ano": competencia.ano,
        "mes": competencia.mes,
        "estado": competencia.estado,
        "fechada_em": competencia.fechada_em.isoformat() if competencia.fechada_em else None,
        "fechada_por": competencia.fechada_por_id,
        "entregue_em": competencia.entregue_em.isoformat() if competencia.entregue_em else None,
        "entregue_por": competencia.entregue_por_id,
    }


class EncerrarCompetenciaView(EmpresaEscopadaContabilMixin, APIView):
    """Fecha a competência (ano, mês) da empresa (DL-016 fatia 1).

    Critérios do plano cobertos aqui: 1 (indiretamente — é o que TORNA a
    trava do critério 1 possível de acionar), 3, 4, 8, 9, 10, 11.
    """

    permission_classes = [TemEscritorioAtivo, PodeFecharCompetencia]

    def post(self, request, empresa_id, ano, mes):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ENCERRAR_COMPETENCIA)
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        # BL-458/A3 (rodada 2 de auditoria): `registrar()` foi MOVIDO para
        # dentro de `encerrar_competencia` — o serviço já é
        # `@transaction.atomic`, então a trilha commita junto com a
        # transição sem a view precisar abrir savepoint nenhum. `request` só
        # serve para o `registrar()` capturar o endereço IP; usuário e
        # escritório são explícitos dentro do serviço.
        try:
            competencia = encerrar_competencia(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except CompetenciaOperacaoRecusada as exc:
            # RC-58 / critério 3: lote desbalanceado na base — conflito de
            # ESTADO da base, não entrada malformada. Nada foi gravado (a
            # recusa acontece antes de qualquer `save()`, dentro da
            # transação atômica do serviço).
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(_competencia_como_dict(competencia), status=status.HTTP_200_OK)


class ReabrirCompetenciaView(EmpresaEscopadaContabilMixin, APIView):
    """Reabre a competência (ano, mês) da empresa (DL-016 fatia 1).

    Critérios do plano cobertos aqui: 5, 6, 8, 9.
    """

    permission_classes = [TemEscritorioAtivo, PodeFecharCompetencia]

    def post(self, request, empresa_id, ano, mes):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_REABRIR_COMPETENCIA)
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        # `motivo` é o ÚNICO campo aceito por `CONTRATO_POST_REABRIR_
        # COMPETENCIA` — a política dos cinco dicionários já recusou
        # qualquer outra chave. Ausência (`None`) e tipo errado (não-texto)
        # viram 400 aqui, na fronteira; string vazia/só espaço é recusada
        # pelo SERVIÇO (`reabrir_competencia`, critério 5), porque "vazio"
        # é regra de NEGÓCIO (o motivo é obrigatório), não de formato — a
        # mesma distinção que `apps.core.requisicao` já traça entre "dado
        # não contratado" e "dado contratado mas inválido".
        motivo = request.data.get("motivo") if isinstance(request.data, dict) else None
        if motivo is not None and not isinstance(motivo, str):
            raise DRFValidationError("O campo 'motivo' deve ser texto.")

        # BL-458/A3 (rodada 2 de auditoria): `registrar()` foi MOVIDO para
        # dentro de `reabrir_competencia` — era a operação MAIS afiada de
        # perder rastro (ela apaga `fechada_em`/`fechada_por` da linha), e
        # chamar o serviço direto, sem view, gravava zero trilha. O serviço
        # devolve só `competencia` agora (antes devolvia também
        # `motivo_normalizado`, que a view usava para montar `detalhes` —
        # isso passou para dentro do serviço, junto com `fechada_por_
        # anterior`/`fechada_em_anterior`, BL-459/A4).
        try:
            competencia = reabrir_competencia(
                empresa=empresa,
                ano=ano,
                mes=mes,
                usuario=request.user,
                motivo=motivo,
                request=request,
            )
        except CompetenciaOperacaoInvalida as exc:
            # Critério 5: motivo vazio — entrada malformada, 400.
            raise DRFValidationError(str(exc)) from exc
        except CompetenciaJaEntregue as exc:
            # Critério 6 / RC-101: já entregue — conflito de ESTADO, 409, com
            # a data da entrega e a orientação de ajustar no mês aberto.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CompetenciaOperacaoRecusada as exc:
            # Reabrir competência que não está encerrada — mesmo tratamento
            # de conflito de estado, 409.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(_competencia_como_dict(competencia), status=status.HTTP_200_OK)


class EntregarCompetenciaView(EmpresaEscopadaContabilMixin, APIView):
    """Marca a competência (ano, mês) da empresa como entregue ao cliente
    (DL-016 fatia 1).

    Critérios do plano cobertos aqui: 7, 8, 9.
    """

    permission_classes = [TemEscritorioAtivo, PodeFecharCompetencia]

    def post(self, request, empresa_id, ano, mes):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ENTREGAR_COMPETENCIA)
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        # BL-458/A3 (rodada 2 de auditoria): `registrar()` mora no serviço.
        try:
            competencia = marcar_competencia_como_entregue(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except CompetenciaOperacaoRecusada as exc:
            # Critério 7: entregar mês aberto — conflito de estado, 409.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(_competencia_como_dict(competencia), status=status.HTTP_200_OK)


def _parametro_contabil_como_dict(parametro):
    """Serialização mínima de `ParametroContabilEmpresa` — mesmo molde de
    `_competencia_como_dict`, acima: FKs saem como ID, nunca o objeto
    inteiro.
    """
    return {
        "id": parametro.pk,
        "empresa": parametro.empresa_id,
        "periodicidade_zeramento": parametro.periodicidade_zeramento,
        "conta_resultado_do_exercicio": parametro.conta_resultado_do_exercicio_id,
        "conta_lucros_acumulados": parametro.conta_lucros_acumulados_id,
        "conta_prejuizos_acumulados": parametro.conta_prejuizos_acumulados_id,
        "vigencia_inicio": parametro.vigencia_inicio.isoformat(),
        "vigencia_fim": parametro.vigencia_fim.isoformat() if parametro.vigencia_fim else None,
    }


def _conta_da_empresa_ou_400(*, empresa, valor, rotulo):
    """Resolve um id de conta (do corpo JSON) para uma `Conta` da MESMA
    empresa escopada — nunca de outra empresa nem de outro escritório
    (AGENTS.md §11).

    Julga o identificador com `para_id` ANTES de consultar o banco, mesmo
    motivo de `_ContaPaiField` em `apps.contabilidade.serializers`
    (BL-142/DE-034: um `PrimaryKeyRelatedField` comum resolveria `1.9` ou
    um dígito Unicode sem avisar). Um id que não resolva (ausente, tipo
    errado, OU conta de outra empresa) sempre vira o MESMO texto de erro —
    de propósito: distinguir "não existe" de "existe, mas é de outra
    empresa" confirmaria a um cliente sem acesso que aquele id existe em
    outra empresa (vazamento de enumeração), o mesmo cuidado que
    `EmpresaEscopadaMixin.get_empresa()` já aplica devolvendo 404 (não
    403) para empresa de outro escritório.
    """
    if valor is None:
        raise DRFValidationError(f"'{rotulo}' é obrigatório.")
    try:
        conta_id = para_id(valor)
    except IdentificadorInvalido as exc:
        raise DRFValidationError(f"'{rotulo}': {exc}") from exc
    conta = Conta.objects.filter(pk=conta_id, empresa=empresa).first()
    if conta is None:
        raise DRFValidationError(
            f"'{rotulo}': nenhuma conta com este identificador foi encontrada nesta empresa."
        )
    return conta


class ParametrosContabeisListCreateView(EmpresaEscopadaContabilMixin, APIView):
    """Lista e cria vigências de parâmetro contábil da empresa (DL-043
    fatia 1, BL-474).

    Permissão RC-102 aplicada por analogia (o parâmetro decide o
    zeramento, mesma sensibilidade do fechamento de competência): só
    ADMINISTRADOR/GESTOR, verificado NO SERVIDOR — a tela é a fatia 3,
    fora do escopo aqui.
    """

    permission_classes = [TemEscritorioAtivo, PodeFecharCompetencia]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        vigencias = ParametroContabilEmpresa.objects.filter(empresa=empresa)
        return Response([_parametro_contabil_como_dict(v) for v in vigencias])

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_PARAMETRO_CONTABIL)
        empresa = self.get_empresa()
        dados = request.data if isinstance(request.data, dict) else {}

        periodicidade = dados.get("periodicidade_zeramento")
        if not isinstance(periodicidade, str):
            raise DRFValidationError("'periodicidade_zeramento' é obrigatório e deve ser texto.")

        conta_resultado = _conta_da_empresa_ou_400(
            empresa=empresa,
            valor=dados.get("conta_resultado_do_exercicio"),
            rotulo="conta_resultado_do_exercicio",
        )
        conta_lucros = _conta_da_empresa_ou_400(
            empresa=empresa,
            valor=dados.get("conta_lucros_acumulados"),
            rotulo="conta_lucros_acumulados",
        )
        conta_prejuizos = _conta_da_empresa_ou_400(
            empresa=empresa,
            valor=dados.get("conta_prejuizos_acumulados"),
            rotulo="conta_prejuizos_acumulados",
        )

        bruto_vigencia = dados.get("vigencia_inicio")
        if not isinstance(bruto_vigencia, str):
            raise DRFValidationError("'vigencia_inicio' é obrigatório (formato AAAA-MM-DD).")
        try:
            vigencia_inicio = para_data(bruto_vigencia)
        except DataInvalida as exc:
            raise DRFValidationError(f"'vigencia_inicio' inválida: {exc}") from exc

        try:
            parametro = registrar_parametro_contabil(
                empresa=empresa,
                periodicidade_zeramento=periodicidade,
                conta_resultado_do_exercicio=conta_resultado,
                conta_lucros_acumulados=conta_lucros,
                conta_prejuizos_acumulados=conta_prejuizos,
                vigencia_inicio=vigencia_inicio,
                usuario=request.user,
                request=request,
            )
        except ParametroContabilInvalido as exc:
            raise DRFValidationError(str(exc)) from exc
        except VigenciaParametroContabilConflitante as exc:
            # Conflito de ESTADO (vigência aberta concorrente, sobreposição
            # de banco, ou retroatividade sobre zeramento já gravado) — 409,
            # nunca 400: nada foi enviado de errado, o que impede é o que já
            # está gravado.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CompetenciaOperacaoRecusada as exc:
            # DE-078 item 3: estouro do `lock_timeout` na trava de EMPRESA
            # (`EmpresaTravadaPorOutraOperacao`, subclasse desta) — outra
            # operação de parâmetro/zeramento da mesma empresa está em
            # andamento. 409, nada gravado — nunca o 500 cru que um
            # `OperationalError` sem tradução produziria (achado B3).
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(_parametro_contabil_como_dict(parametro), status=status.HTTP_201_CREATED)


class EncerrarVigenciaParametroContabilView(EmpresaEscopadaContabilMixin, APIView):
    """Encerra HOJE a vigência de parâmetro contábil aberta da empresa, sem
    abrir uma nova (DL-043 fatia 1)."""

    permission_classes = [TemEscritorioAtivo, PodeFecharCompetencia]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ENCERRAR_VIGENCIA_PARAMETRO_CONTABIL)
        empresa = self.get_empresa()
        try:
            parametro = encerrar_vigencia_de_parametro_contabil(
                empresa=empresa, usuario=request.user, request=request
            )
        except VigenciaParametroContabilConflitante as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CompetenciaOperacaoRecusada as exc:
            # DE-078 item 3: estouro do `lock_timeout` na trava de empresa
            # — ver o mesmo `except` em `ParametrosContabeisListCreateView.
            # post`.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(_parametro_contabil_como_dict(parametro), status=status.HTTP_200_OK)


def _item_de_zeramento_como_dict(item):
    """Serialização de um item calculado (`conta`, `tipo`, `valor` —
    `apps.contabilidade.services._calcular_zeramento`) para a resposta
    JSON: código+nome da conta bastam para o contador conferir a prévia,
    nunca o objeto `Conta` inteiro.
    """
    return {
        "conta": item["conta"].codigo,
        "conta_nome": item["conta"].nome,
        "tipo": item["tipo"],
        "valor": _como_moeda(item["valor"]),
    }


def _zeramento_calculado_como_dict(calculo):
    """Serialização comum da prévia (GET) e do resultado da execução
    (POST) do zeramento: as duas respostas descrevem a MESMA forma de
    dado (itens da etapa 1, incluindo a contrapartida em "resultado do
    exercício"; e a etapa 2, se houver) — para o contador comparar
    visualmente a prévia com o que foi de fato gravado.
    """
    itens_etapa1 = list(calculo["itens_etapa1"])
    if calculo["item_resultado_etapa1"] is not None:
        itens_etapa1.append(calculo["item_resultado_etapa1"])

    etapa2 = None
    if calculo["etapa2"] is not None:
        etapa2 = {
            "destino": calculo["etapa2"]["destino"],
            "itens": [
                _item_de_zeramento_como_dict(calculo["etapa2"]["item_resultado"]),
                _item_de_zeramento_como_dict(calculo["etapa2"]["item_destino"]),
            ],
        }

    return {
        "etapa1": (
            {"itens": [_item_de_zeramento_como_dict(item) for item in itens_etapa1]}
            if itens_etapa1
            else None
        ),
        "etapa2": etapa2,
    }


class ZerarResultadoView(EmpresaEscopadaContabilMixin, APIView):
    """Prévia (GET) e execução (POST) do zeramento do resultado do período
    cuja competência final é (ano, mês) — DL-043 fatia 2, RC-104/RC-105.

    GET devolve os valores que SERIAM lançados, sem gravar nada (leitura
    best-effort, sem trava de competência — ver `pre_visualizar_
    zeramento`; pode divergir do POST se, entre os dois, outra requisição
    gravar lançamento no período). POST executa de fato, dentro da trava
    de competência (`zerar_resultado`) — idempotente: repetir sem
    movimento novo não gera nada; com movimento novo (competência ainda
    aberta), gera só o complemento.
    """

    permission_classes = [TemEscritorioAtivo, PodeFecharCompetencia]

    def get(self, request, empresa_id, ano, mes):
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)
        try:
            calculo = pre_visualizar_zeramento(empresa=empresa, ano=ano, mes=mes)
        except ParametroContabilInvalido as exc:
            raise DRFValidationError(str(exc)) from exc
        except CompetenciaEncerrada as exc:
            # DE-078 item 2: `ZeramentoForaDeOrdem` é subclasse desta — já
            # existe zeramento posterior gravado para a empresa. 409
            # também na PRÉVIA: o contador vê o motivo da recusa antes de
            # tentar gravar, não só depois do POST.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        resposta = _zeramento_calculado_como_dict(calculo)
        resposta["data_final"] = calculo["data_final"].isoformat()
        resposta["periodicidade_zeramento"] = calculo["parametro"].periodicidade_zeramento
        return Response(resposta)

    def post(self, request, empresa_id, ano, mes):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_ZERAR_RESULTADO)
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        try:
            resultado = zerar_resultado(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except ParametroContabilInvalido as exc:
            raise DRFValidationError(str(exc)) from exc
        except LancamentoInvalido as exc:
            # DE-078 item 5 (B3): qualquer recusa de `criar_lancamento` que
            # não seja o teto de partidas (já dividido, ver `_dividir_em_
            # lancamentos_balanceados`) — por exemplo, data fora da faixa
            # do RC-77 num caminho não coberto pela checagem de HI-25.
            # 400, nunca o 500 cru que a auditoria mediu (achado B3).
            raise DRFValidationError(str(exc)) from exc
        except ChaveIdempotenciaConflitante as exc:
            # DE-078 item 6 (B4): a chave reservada já está ocupada — só
            # alcançável hoje por uma corrida entre dois pedidos de
            # zeramento (a recusa de prefixo em `criar_lancamento` já
            # fecha a porta de um cliente forjar a chave). 409, nunca 500.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CompetenciaEncerrada as exc:
            # RC-57 (competência encerrada) OU DE-078 item 2/B2
            # (`ZeramentoForaDeOrdem`, subclasse desta) — conflito de
            # estado, 409, nada gravado (as duas checagens em
            # `zerar_resultado` acontecem ANTES de calcular qualquer
            # saldo).
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except CompetenciaOperacaoRecusada as exc:
            # DE-078 item 3 (B2(b)/B10/B3): estouro do `lock_timeout` na
            # trava de empresa OU de competência
            # (`EmpresaTravadaPorOutraOperacao`/`CompetenciaTravadaPorOutra
            # Operacao`, as duas subclasses desta). 409, nunca o 500 cru
            # que a auditoria mediu em 1,23s (achado B3).
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        lancamento_etapa1 = resultado["lancamento_etapa1"]
        lancamento_etapa2 = resultado["lancamento_etapa2"]
        return Response(
            {
                "data_final": resultado["data_final"].isoformat(),
                "periodicidade_zeramento": resultado["periodicidade_zeramento"],
                "lancamento_etapa1": lancamento_etapa1.pk if lancamento_etapa1 else None,
                "criado_etapa1": resultado["criado_etapa1"],
                # DE-078 item 5 (B3): lista COMPLETA dos lançamentos da
                # etapa 1 — no caso comum (dentro do teto de partidas) tem
                # exatamente UM id, igual a `lancamento_etapa1` acima;
                # `lancamento_etapa1` continua existindo para quem já lia
                # só essa chave (compatibilidade com a fatia 3).
                "lancamentos_etapa1": [lanc.pk for lanc in resultado["lancamentos_etapa1"]],
                "lancamento_etapa2": lancamento_etapa2.pk if lancamento_etapa2 else None,
                "criado_etapa2": resultado["criado_etapa2"],
                "destino_etapa2": resultado["destino_etapa2"],
            },
            status=status.HTTP_200_OK,
        )


class DiarioView(EmpresaEscopadaContabilMixin, APIView):
    """Diário: lançamentos da empresa no período, em ordem cronológica (BL-59, DL-015)."""

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        inicio, fim = _periodo_obrigatorio(request)
        # DL-089: `?origem=` filtra o Diário por origem (manual, importacao, escrita_fiscal).
        # Vazio ou ausente = sem filtro. O Razão não tem este filtro: ver `listar_diario`.
        origem = (request.query_params.get("origem") or "").strip() or None
        if origem is not None and origem not in OrigemLancamento.values:
            raise DRFValidationError(
                f"'origem' inválida: {origem!r}. Use um de: {', '.join(OrigemLancamento.values)}."
            )

        lancamentos = []
        total_debito = Decimal("0")
        total_credito = Decimal("0")
        # `listar_diario` já faz prefetch de itens+conta em consultas de
        # tamanho constante; iterar `lancamento.itens.all()` aqui usa o
        # cache do prefetch, sem gerar uma consulta por lançamento (N+1).
        for lancamento in listar_diario(empresa=empresa, inicio=inicio, fim=fim, origem=origem):
            debito_lancamento = Decimal("0")
            credito_lancamento = Decimal("0")
            itens = []
            for item in lancamento.itens.all():
                if item.tipo == TipoPartida.DEBITO:
                    debito_lancamento += item.valor
                else:
                    credito_lancamento += item.valor
                itens.append(
                    {
                        "conta": item.conta.codigo,
                        "nome": item.conta.nome,
                        "tipo": item.tipo,
                        "valor": _como_moeda(item.valor),
                    }
                )
            total_debito += debito_lancamento
            total_credito += credito_lancamento
            lancamentos.append(
                {
                    "id": lancamento.id,
                    "data": lancamento.data.isoformat(),
                    "historico": lancamento.historico,
                    "origem": lancamento.origem,
                    "total_debito": _como_moeda(debito_lancamento),
                    "total_credito": _como_moeda(credito_lancamento),
                    "itens": itens,
                }
            )

        return Response(
            {
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                # DL-089: o filtro aplicado (None quando não há filtro). Os totais são os
                # do que foi listado, e não os do período inteiro.
                "origem_filtrada": origem,
                "lancamentos": lancamentos,
                "total_debito": _como_moeda(total_debito),
                "total_credito": _como_moeda(total_credito),
                # BL-198: o Diário do período pode conciliar perfeitamente e
                # ainda assim haver escrituração fora dele. Ver
                # `_aviso_de_movimento_fora_do_periodo`.
                "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                    empresa=empresa, inicio=inicio, fim=fim
                ),
            }
        )


class RazaoView(EmpresaEscopadaContabilMixin, APIView):
    """Razão de uma conta no período: saldo anterior, itens e saldo final (BL-60, DL-015).

    Consolidação (achado 8 / DE-020, corrigida pela DE-022): o extrato
    CONSOLIDA sempre que a conta TIVER DESCENDENTES — a resposta declara
    `"analitica": false` e `"consolidado": true` para que quem lê saiba que
    está vendo o grupo, não uma conta com movimento próprio. `"analitica"`
    é sempre o NEGATIVO de `"consolidado"` (as duas descrevem a mesma
    pergunta — "esta conta tem descendentes?" — só que em polaridades
    opostas): antes da correção do achado novo 1, este campo vinha de
    `conta.aceita_lancamento`, um critério DIFERENTE do que decidia a
    consolidação, e uma conta que aceita lançamento e tem filhas aparecia
    marcada `"analitica": true` com o Razão zerado, enquanto o Balancete da
    MESMA conta trazia o total consolidado.

    Saldo com natureza (RC-61 / BL-77, critério 5 do plano DL-017):
    `saldo_anterior`, `saldo_final` e a coluna `saldo` de cada item de
    `itens` NUNCA vêm negativos — são o valor ABSOLUTO, acompanhados do
    campo irmão `<campo>_natureza` ("D", "C" ou `None` para saldo zero — ver
    `_saldo_absoluto_com_natureza`). A natureza aplicada é sempre a da
    CONTA CONSULTADA (`conta`, inclusive quando consolidado — o grupo), a
    mesma que já decide o sinal interno em `apurar_razao`/`_sinal_do_item`;
    nunca a de uma conta descendente.
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        inicio, fim = _periodo_obrigatorio(request)

        try:
            apuracao = apurar_razao(conta=conta, empresa=empresa, inicio=inicio, fim=fim)
        except HierarquiaInconsistente as exc:
            # Ciclo ou conta_pai de outra empresa na hierarquia (achado 6):
            # resposta controlada, nomeando a conta, nunca um 500 mudo.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        itens = []
        for linha in apuracao["itens"]:
            # RC-61 / BL-77: a coluna "saldo" de cada linha do Razão também
            # vira valor absoluto + natureza apurada — sempre pela natureza
            # da conta CONSULTADA (`conta`), nunca a do item individual (ver
            # docstring da classe e de `apurar_razao`).
            saldo_abs, saldo_natureza = _saldo_absoluto_com_natureza(linha["saldo"], conta.natureza)
            itens.append(
                {
                    "lancamento_id": linha["lancamento_id"],
                    "data": linha["data"].isoformat(),
                    "historico": linha["historico"],
                    "conta": linha["conta"],
                    "nome": linha["conta_nome"],
                    "tipo": linha["tipo"],
                    # Decimal como string: o encoder JSON padrão do DRF
                    # converte Decimal para float fora de um DecimalField de
                    # serializer, o que quebraria a precisão decimal exigida
                    # para valores monetários (AGENTS.md, seção 10).
                    "valor": _como_moeda(linha["valor"]),
                    "saldo": _como_moeda(saldo_abs),
                    "saldo_natureza": saldo_natureza,
                }
            )

        saldo_anterior_abs, saldo_anterior_natureza = _saldo_absoluto_com_natureza(
            apuracao["saldo_anterior"], conta.natureza
        )
        saldo_final_abs, saldo_final_natureza = _saldo_absoluto_com_natureza(
            apuracao["saldo_final"], conta.natureza
        )

        return Response(
            {
                "conta": conta.codigo,
                "nome": conta.nome,
                # DE-022 (achado novo 1): "analitica" é o NEGATIVO de
                # "consolidado" — o mesmo critério ("tem descendentes?"),
                # nunca mais `conta.aceita_lancamento`. Ver docstring da
                # classe.
                "analitica": not apuracao["consolidado"],
                "consolidado": apuracao["consolidado"],
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "saldo_anterior": _como_moeda(saldo_anterior_abs),
                "saldo_anterior_natureza": saldo_anterior_natureza,
                "total_debito": _como_moeda(apuracao["total_debito"]),
                "total_credito": _como_moeda(apuracao["total_credito"]),
                "saldo_final": _como_moeda(saldo_final_abs),
                "saldo_final_natureza": saldo_final_natureza,
                "itens": itens,
                # BL-198, recortado pela CONTA consultada (e pelas
                # descendentes): o aviso do Razão fala da conta que está na
                # tela, não da empresa inteira. O recorte é LITERALMENTE o
                # conjunto que esta apuração somou — `apuracao["ids_contas"]`,
                # o mesmo objeto, não uma segunda travessia da subárvore
                # (BL-212: recomputá-lo dobra a consulta por nível de
                # profundidade e estourou o teto de consultas do Razão).
                "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                    empresa=empresa, inicio=inicio, fim=fim, ids_contas=apuracao["ids_contas"]
                ),
            }
        )


class BalanceteView(EmpresaEscopadaContabilMixin, APIView):
    """Balancete de verificação da empresa no período, com 4 colunas por conta
    (saldo anterior, débitos, créditos, saldo final) — BL-61, DL-015.

    Saldo com natureza (RC-61 / BL-77, critério 5 do plano DL-017):
    `saldo_anterior` e `saldo_final`, em cada linha, NUNCA vêm negativos —
    são o valor ABSOLUTO, acompanhados do campo irmão `<campo>_natureza`
    ("D", "C" ou `None` para saldo zero — ver `_saldo_absoluto_com_natureza`
    em `views.py`). A natureza é a APURADA daquela linha, não a CADASTRADA
    da conta (`linha["natureza"]`, que `apurar_balancete` devolve só para
    esta conversão): o caso de referência é o grupo Imobilizado do Fred
    (docs/projeto/mapa-funcional-contabil.md) — devedor, cadastrado como
    tal — que segue apurando saldo DEVEDOR mesmo absorvendo o crédito da
    retificadora (natureza cadastrada oposta) entre suas descendentes.
    `debitos`/`creditos`/`debitos_proprios`/`creditos_proprios` continuam
    como somas BRUTAS (sempre ≥ 0 por construção): não precisam de
    indicador de natureza, só o saldo tem lado.
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        inicio, fim = _periodo_obrigatorio(request)
        nivel = _nivel_opcional(request)

        try:
            apuracao = apurar_balancete(empresa=empresa, inicio=inicio, fim=fim, nivel=nivel)
        except HierarquiaInconsistente as exc:
            # Ciclo ou conta_pai de outra empresa na hierarquia (achado 6):
            # resposta controlada, nomeando a conta, nunca um 500 mudo.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        contas = []
        for linha in apuracao["contas"]:
            # RC-61 / BL-77: `linha["natureza"]` é a natureza CADASTRADA da
            # conta (adicionada por `apurar_balancete` só para esta
            # conversão) — a natureza APURADA de cada saldo é derivada do
            # SINAL do valor assinado, não copiada dela. Ver docstring da
            # classe e de `_saldo_absoluto_com_natureza`.
            saldo_anterior_abs, saldo_anterior_natureza = _saldo_absoluto_com_natureza(
                linha["saldo_anterior"], linha["natureza"]
            )
            saldo_final_abs, saldo_final_natureza = _saldo_absoluto_com_natureza(
                linha["saldo_final"], linha["natureza"]
            )
            contas.append(
                {
                    "conta": linha["conta"],
                    "nome": linha["nome"],
                    "nivel": linha["nivel"],
                    "analitica": linha["analitica"],
                    "saldo_anterior": _como_moeda(saldo_anterior_abs),
                    "saldo_anterior_natureza": saldo_anterior_natureza,
                    "debitos": _como_moeda(linha["debitos"]),
                    "creditos": _como_moeda(linha["creditos"]),
                    # Achado novo 3 / DE-024 §2: movimento PRÓPRIO da conta (o
                    # que foi lançado DIRETO nela, sem o das descendentes) — é
                    # sobre estes dois campos, não sobre "debitos"/"creditos"
                    # (consolidados), que a soma das linhas reconcilia com
                    # total_debitos/total_creditos abaixo. Sempre ≥ 0: não
                    # levam indicador de natureza (ver docstring da classe).
                    "debitos_proprios": _como_moeda(linha["debitos_proprios"]),
                    "creditos_proprios": _como_moeda(linha["creditos_proprios"]),
                    "saldo_final": _como_moeda(saldo_final_abs),
                    "saldo_final_natureza": saldo_final_natureza,
                }
            )

        return Response(
            {
                "inicio": inicio.isoformat(),
                "fim": fim.isoformat(),
                "contas": contas,
                "total_debitos": _como_moeda(apuracao["total_debitos"]),
                "total_creditos": _como_moeda(apuracao["total_creditos"]),
                # BL-198: é no Balancete que a invisibilidade dói mais, porque
                # ele é a saída que o contador usa para CONCILIAR — e ele
                # concilia, com o valor de fora do período ausente dos dois
                # lados. Ver `_aviso_de_movimento_fora_do_periodo`.
                "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                    empresa=empresa, inicio=inicio, fim=fim
                ),
            }
        )


def _linhas_dre_como_moeda(linhas):
    """`{ClassificacaoDre: Decimal}` -> `{str: str}`, com `_como_moeda` em
    cada valor — a chave já é `str` (o `TextChoices` é uma `str`), mas
    `str()` explícito documenta a conversão e não depende do valor já ser
    o literal certo por acidente."""
    return {str(classificacao): _como_moeda(valor) for classificacao, valor in linhas.items()}


def _subtotais_dre_como_moeda(subtotais):
    return {nome: _como_moeda(valor) for nome, valor in subtotais.items()}


def _residuo_dre_como_moeda(residuo_por_tipo):
    return {str(tipo): _como_moeda(valor) for tipo, valor in residuo_por_tipo.items()}


def _residuo_pendente_dre_para_json(residuo_pendente_por_coluna):
    """`{"coluna_mes": {TipoConta: Decimal}, "coluna_acumulado": {...}}`
    -> mesma forma, com chave e valor como `str` (DL-045, decisão do
    arquiteto de 26/09/2026: as duas colunas vetam, cada pendência
    marcada com a coluna de onde vem)."""
    return {
        nome_coluna: {str(tipo): _como_moeda(valor) for tipo, valor in residuo.items()}
        for nome_coluna, residuo in residuo_pendente_por_coluna.items()
    }


def _estornos_de_zeramento_para_json(estornos):
    """`data` (objeto `date`) -> `isoformat()`, mesma regra de toda data
    desta API (A3, auditoria DL-045 rodada 1)."""
    return [
        {
            "lancamento": item["lancamento"],
            "data": item["data"].isoformat(),
            "historico": item["historico"],
            "estorno_de_chave": item["estorno_de_chave"],
        }
        for item in estornos
    ]


def _coluna_dre_para_json(coluna):
    return {
        "linhas": _linhas_dre_como_moeda(coluna["linhas"]),
        "subtotais": _subtotais_dre_como_moeda(coluna["subtotais"]),
        "residuo_por_tipo": _residuo_dre_como_moeda(coluna["residuo_por_tipo"]),
        "total_debitos": _como_moeda(coluna["total_debitos"]),
        "total_creditos": _como_moeda(coluna["total_creditos"]),
        "contas_sem_classificacao_dre_com_movimento": (
            coluna["contas_sem_classificacao_dre_com_movimento"]
        ),
        "contas_nao_folha_sem_classificacao_dre_com_movimento_proprio": (
            coluna["contas_nao_folha_sem_classificacao_dre_com_movimento_proprio"]
        ),
        "contas_com_classificacao_dre_aninhada_mesma_linha": (
            coluna["contas_com_classificacao_dre_aninhada_mesma_linha"]
        ),
        "contas_com_classificacao_dre_aninhada_linha_diferente": (
            coluna["contas_com_classificacao_dre_aninhada_linha_diferente"]
        ),
        "contas_com_tipo_divergente_da_linha": coluna["contas_com_tipo_divergente_da_linha"],
        "contas_com_classificacao_dre_desconhecida": (
            coluna["contas_com_classificacao_dre_desconhecida"]
        ),
        "estornos_de_zeramento_na_coluna": _estornos_de_zeramento_para_json(
            coluna["estornos_de_zeramento_na_coluna"]
        ),
    }


class DreView(EmpresaEscopadaContabilMixin, APIView):
    """Demonstração do Resultado do Exercício (DL-045, fatia 2 — RC-118/
    RC-119/RC-120): duas colunas (mês e acumulado do exercício, HI-28),
    pelo MOVIMENTO do período, excluindo lançamentos de zeramento
    (DL-043).

    Autorização: a MESMA das outras saídas contábeis com período (Diário,
    Razão, Balancete) — `PodeLerContabilidade`, nunca `PodeFecharCompeten
    cia` (a DRE é leitura, não uma ação de fechamento).

    409 (`pode_emitir=False`) quando há conta de resultado analítica com
    movimento SEM classificação (critério 6 do plano) — em QUALQUER das
    duas colunas (mês ou acumulado; decisão do arquiteto, 26/09/2026: a
    DRE formal imprime o acumulado, então uma pendência só nele também
    deixa um número impresso errado). Mesmo padrão de veto do Balanço
    (`avaliar_emissao_do_balanco`/`apurar_balanco_patrimonial`, DL-034),
    adaptado: aqui não há template/emissão formal ainda (fatia 3), então
    o 409 é da PRÓPRIA leitura — o corpo da resposta sempre traz os dois
    números (mês e acumulado), mesmo quando `pode_emitir` é falso, para o
    cliente decidir o que mostrar (nunca esconder o dado por trás só do
    código de status). `residuo_pendente`/`listas_pendentes`/`listas_
    informativas` vêm agrupados por coluna (`"coluna_mes"`/`"coluna_
    acumulado"`) — só a coluna que TEM algo a reportar aparece.

    A2/A1 (auditoria DL-045, rodada 1): `contas_com_tipo_divergente_da_
    linha` e `contas_com_classificacao_dre_aninhada_linha_diferente`
    também vetam agora (ver `_LISTAS_DA_DRE_QUE_IMPEDEM_A_EMISSAO` em
    `services.py`) — nada mudou NESTA view por causa disso; ela só lê o
    que `avaliar_emissao_da_dre` decide.
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id, ano, mes):
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        try:
            dre = apurar_dre(empresa=empresa, ano=ano, mes=mes)
        except HierarquiaInconsistente as exc:
            # Mesmo padrão do Balancete/Razão: ciclo ou conta_pai de outra
            # empresa na hierarquia — resposta controlada, nunca 500 mudo.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        emissao = avaliar_emissao_da_dre(dre)
        corpo = {
            "empresa_id": dre["empresa_id"],
            "ano": dre["ano"],
            "mes": dre["mes"],
            "data_inicio_mes": dre["data_inicio_mes"].isoformat(),
            "data_fim_mes": dre["data_fim_mes"].isoformat(),
            "data_inicio_exercicio": dre["data_inicio_exercicio"].isoformat(),
            "data_fim_exercicio": dre["data_fim_exercicio"].isoformat(),
            "coluna_mes": _coluna_dre_para_json(dre["coluna_mes"]),
            "coluna_acumulado": _coluna_dre_para_json(dre["coluna_acumulado"]),
            "pode_emitir": emissao["pode_emitir"],
            "residuo_pendente": _residuo_pendente_dre_para_json(emissao["residuo_pendente"]),
            "listas_pendentes": emissao["listas_pendentes"],
            "listas_informativas": emissao["listas_informativas"],
        }
        status_code = status.HTTP_200_OK if emissao["pode_emitir"] else status.HTTP_409_CONFLICT
        return Response(corpo, status=status_code)


class ContaClassificacaoDreView(EmpresaEscopadaContabilMixin, APIView):
    """A7 (auditoria DL-045, rodada 1): PATCH da linha da DRE
    (`classificacao_dre`) de uma conta já existente — a porta operacional
    que faltava. Antes desta view, só o `admin` do Django conseguia
    classificar ou corrigir conta (e corrigir um erro de classificação
    exigia conta nova + transferência do movimento, deixando marca
    permanente na DRE do mês da correção — ver o achado A7 completo).

    Autorização: `PodeEscriturar` — o MESMO papel que grava lançamento e
    cria conta (`ContaListCreateView.post`), nunca uma permissão nova
    para a classificação da DRE (RC-118 não criou papel próprio).

    Corpo: `{"classificacao_dre": "<valor de ClassificacaoDre, ou null/""
    para remover>"}` — um campo só (`CONTRATO_PATCH_CLASSIFICACAO_DRE`).
    A ÚNICA guarda que resta em `Conta.clean()` é a de compatibilidade
    de TIPO (Lei 6.404/76, art. 187) — DE-086 (reconferência) removeu a
    guarda de transição e as duas do A6 (rodada 1): a linha da DRE pode
    mudar livremente com movimento, sempre com trilha (ver
    `classificar_conta_na_dre`, services.py). Esta view não duplica
    nenhuma regra de negócio — só traduz `django.core.exceptions.
    ValidationError` para 400 do DRF.

    R3 (auditoria DL-045, reconferência): o CORPO é validado por
    `ClassificacaoDrePatchSerializer` (serializers.py) ANTES do serviço
    — um corpo que não é dicionário, ou um valor de `classificacao_dre`
    que não é `str`/`None`/`""` (dict, lista), devolve 400 aqui, nunca
    500. Antes desta validação, `request.data.get(...)` estourava
    `AttributeError` para corpo-lista, e `Conta.clean()` estourava
    `TypeError: unhashable type` para valor dict/lista — os dois casos
    vazavam como 500 mudo, sem nada gravado.

    200 com a conta serializada (`ContaSerializer`) quando aceito. 404
    quando a conta não existe NESTA empresa (isolamento — `Conta.objects
    .filter(empresa=empresa)`, nunca uma consulta sem esse filtro).
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def patch(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        _recusar_dado_nao_contratado(request, CONTRATO_PATCH_CLASSIFICACAO_DRE)

        # R3: valida o TIPO do corpo e do valor ANTES de qualquer coisa
        # que possa gravar ou estourar 500 — ver o docstring da classe e
        # de `ClassificacaoDrePatchSerializer`.
        entrada = ClassificacaoDrePatchSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        classificacao = entrada.validated_data.get("classificacao_dre") or None

        try:
            classificar_conta_na_dre(
                conta=conta,
                classificacao=classificacao,
                usuario=request.user,
                request=request,
            )
        except DjangoValidationError as exc:
            raise DRFValidationError(
                {"classificacao_dre": mensagens_da_validacao_django(exc)}
            ) from exc

        return Response(ContaSerializer(conta).data, status=status.HTTP_200_OK)


# DL-048 (fatia D8) — o § 2º do art. 186 da Lei 6.404/76, como BLOCO de
# resposta, e não como frase no docstring.
#
# "A demonstração de lucros ou prejuízos acumulados deverá indicar o montante
#  do dividendo por ação do capital social e poderá ser incluída na demonstração
#  das mutações do patrimônio líquido, se elaborada e publicada pela companhia."
# (texto lido no Planalto em 29/09/2026)
#
# São TRÊS fatos que a API precisa declarar, e todos os três são
# consecuencias que um cliente não pode deduzir sozinho:
#
# 1. O "montante do dividendo por ação" NÃO é apurável aqui, e a razão é
#    estrutural, não uma pendência esquecida: a base de cálculo (número de
#    ações do capital social) é dado da DMPL, que é a CTB-14. A DLPA lê
#    movimento de lançamentos e não tem esse dado. O achado 11 da auditoria de
#    29/09 registrou exatamente isso, e a decisão foi DECLARAR em vez de
#    inventar o número (AGENTS.md §10: não inventar fórmula ou leiaute).
# 2. "Poderá ser incluída na DMPL" é FACULDADE da lei, não dever. A API não
#    escolhe entre emitir a DLPA autônoma ou embutida — essa escolha é da
#    emissão, e a apuração é a MESMA nos dois casos. Por isso a resposta não
#    tem campo "modo": teria duas respostas idênticas com nomes diferentes, e
#    quem integrasse escolheria pelo nome em vez de pela lei.
# 3. A chave SEMPRE existe, mesmo sem dividendo nenhum. Cliente que só a
#    enxergasse quando houvesse valor não tem como distinguir "não há" de
#    "esta versão do servidor não responde isso" — o mesmo raciocínio de
#    `_aviso_de_movimento_fora_do_periodo` (BL-198).
#
# ⚠️ O que a API NÃO faz, por decisão: não calcula dividendo por ação, não
# emite coluna de DMPL, e não escolhe o modo de emissão. A CTB-14 consome as
# `chave` das linhas (que já carregam a destinação × reversão da D4) como
# movimento de coluna — a MESMA leitura estruturada, sem segunda lógica.
_PARAGRAFO_2_DA_DLPA = {
    "fonte": "Lei 6.404/76, art. 186, § 2º",
    "dividendo_por_acao": None,
    "situacao_do_dividendo_por_acao": (
        "pendente: a base de cálculo (ações do capital social) é dado da DMPL (CTB-14)"
    ),
    "pode_ser_incluida_na_dmpl": True,
    "natureza": (
        "faculdade da lei, não obrigação — a escolha de emitir a DLPA autônoma ou "
        "embutida é da emissão, não da leitura"
    ),
}


def _linhas_da_dlpa_para_json(linhas):
    return [
        {
            "chave": linha["chave"],
            "titulo": linha["titulo"],
            "valor": _como_moeda(linha["valor"]),
            "lancamentos": list(linha["lancamentos"]),
        }
        for linha in linhas
    ]


class DlpaView(EmpresaEscopadaContabilMixin, APIView):
    """Demonstração dos Lucros ou Prejuízos Acumulados (DL-048, **fatia D8** —
    a porta de API que a decisão D8 deixou para depois da tela).

    **O que ela NÃO é:** uma segunda apuração. Revela, sem recalcular, o que
    `apurar_dlpa` e `avaliar_emissao_da_dlpa` já decidem no servidor. Nenhuma
    regra de negócio é duplicada aqui — a autorização, o isolamento, a
    conciliação com o Balanço e os vetos de emissão vivem no serviço e na
    camada de permissões, como em `DreView`.

    **Autorização:** a MESMA das outras saídas contábeis com período (Diário,
    Razão, Balancete, DRE) — `PodeLerContabilidade`, nunca
    `PodeFecharCompetencia`: a DLPA é leitura, não ação de fechamento.

    **Período:** `ano`/`mes` identificam o RECURSO (o exercício até a competência
    pedida), mesmo padrão de `dre/<int:ano>/<int:mes>/`. `_validar_ano_mes`
    recusa mês fora de 1–12 e ano implausível com 400 — é o achado 14 da
    auditoria de 29/09 ("`mes` fora da faixa levanta exceção crua") corrigido
    AQUI, na fronteira, que é onde a validação de FORMATO pertence.

    **409 (`pode_emitir=False`) com o corpo INTEIRO mesmo assim:** mesmo padrão
    de `DreView`. Um cliente que só recebesse o veto não distinguiria "não pode
    emitir" de "o servidor não sabe ler"; e um cliente que montasse documento
    com 200 receberia número imprimível sem saber da pendência. Por isso o
    corpo sempre traz saldos, linhas, conciliação e pendências — o status
    informa, não substitui.

    **A chave `chave` de cada linha é o contrato com a DMPL (CTB-14).** A
    RC-137 fixa que a linha da DLPA é a DESTINAÇÃO e a coluna da DMPL é a
    CONTRAPARTIDA — *"o mesmo fato visto por dois lados"*. Por isso a apuração
    emite a leitura estruturada do evento, e a `chave` (`transferencia:<reserva>`
    × `reversao:<reserva>`, decisão D4) é a identidade desse evento. Ver
    `_PARAGRAFO_2_DA_DLPA` para o que a lei faculta e o que esta API declara
    em vez de calcular.
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id, ano, mes):
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        try:
            dlpa = apurar_dlpa(empresa=empresa, ano=ano, mes=mes)
        except HierarquiaInconsistente as exc:
            # Mesmo padrão do Balancete/Razão/DRE: ciclo ou `conta_pai` de outra
            # empresa na hierarquia — resposta controlada, nunca 500 mudo.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        emissao = avaliar_emissao_da_dlpa(dlpa)
        corpo = {
            "empresa_id": dlpa["empresa_id"],
            "ano": dlpa["ano"],
            "mes": dlpa["mes"],
            "data_inicio_exercicio": dlpa["data_inicio_exercicio"].isoformat(),
            "data_fim": dlpa["data_fim"].isoformat(),
            "saldo_inicial": _como_moeda(dlpa["saldo_inicial"]),
            "movimento": _como_moeda(dlpa["movimento"]),
            "saldo_final": _como_moeda(dlpa["saldo_final"]),
            "linhas": _linhas_da_dlpa_para_json(dlpa["linhas"]),
            "conciliacao": {
                "saldo_no_balanco": _como_moeda(dlpa["conciliacao"]["saldo_no_balanco"]),
                "diferenca": _como_moeda(dlpa["conciliacao"]["diferenca"]),
            },
            "pode_emitir": emissao["pode_emitir"],
            "listas_pendentes": emissao["listas_pendentes"],
            "avisos": emissao["avisos"],
            "paragrafo_2": dict(_PARAGRAFO_2_DA_DLPA),
        }
        status_code = status.HTTP_200_OK if emissao["pode_emitir"] else status.HTTP_409_CONFLICT
        return Response(corpo, status=status_code)


class ContaClassificacaoDlpaView(EmpresaEscopadaContabilMixin, APIView):
    """DL-048 (fatia D8): `PATCH` da linha da DLPA (`classificacao_dlpa`) de
    uma conta já existente — a porta de API da tela `conta_classificacao_dlpa`.

    Autenticação e autorização são as MESMAS da tela: `TemEscritorioAtivo` +
    `PodeEscriturar`, o MESMO papel que grava lançamento e cria conta
    (`ContaListCreateView.post`). **Nenhuma permissão nova** — a RC-137 não
    criou papel próprio para classificação, e criar um agora daria a
    classificação mais poder de que o lançamento tem.

    Corpo: `{"classificacao_dlpa": "<valor de ClassificacaoDlpa, ou null/""
    para remover>"}` — um campo só (`CONTRATO_PATCH_CLASSIFICACAO_DLPA`).
    O contrato é **separado** do da DRE de propósito: a política recusa chave
    desconhecida por nome, e um corpo com `classificacao_dre` neste PATCH tem
    de ser recusado, não aplicado à linha errada em silêncio.

    Validação em DUAS camadas, nenhuma delas duplicando regra:
    `ClassificacaoDlpaPatchSerializer` valida o TIPO do corpo e do valor
    (400, nunca 500 — R3 da auditoria DL-045); a compatibilidade com
    `Conta.tipo` é decidida por `Conta.full_clean()` dentro de
    `classificar_conta_na_dlpa`, e o `ValidationError` do Django é traduzido
    para 400 do DRF.

    200 com a conta serializada (incluindo o `classificacao_dlpa` novo) quando
    aceito; **404** quando a conta não existe NESTA empresa (isolamento —
    `Conta.objects.filter(empresa=empresa)`, nunca uma consulta sem esse
    filtro); 403 sem `PodeEscriturar`.
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def patch(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        _recusar_dado_nao_contratado(request, CONTRATO_PATCH_CLASSIFICACAO_DLPA)

        entrada = ClassificacaoDlpaPatchSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        classificacao = entrada.validated_data.get("classificacao_dlpa") or None

        try:
            classificar_conta_na_dlpa(
                conta=conta,
                classificacao=classificacao,
                usuario=request.user,
                request=request,
            )
        except ClassificacaoAlteraPeriodoFechado as exc:
            # DL-065 (BL-550): 409, não 400 — o que recusa é o ESTADO da
            # competência que a demonstração leria, não o corpo enviado. Mesma
            # tradução de `CompetenciaEncerrada` acima, e nada foi gravado: a
            # recusa vem de dentro de `full_clean()`, antes do `save()`.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            raise DRFValidationError(
                {"classificacao_dlpa": mensagens_da_validacao_django(exc)}
            ) from exc

        return Response(ContaSerializer(conta).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# DL-061, fatia 2 (BL-605, E18): a porta de API da DMPL — a apuração
# (`DmplView`), a coluna da conta (`ContaClassificacaoDmplView`) e a marcação
# manual por lançamento (`MarcacaoDmplView`), no padrão exato das rotas D8 da
# DLPA acima.
# ---------------------------------------------------------------------------


def _para_json_da_apuracao(valor):
    """Converte uma estrutura de `apurar_dmpl` para o corpo JSON SEM mudar o
    formato: `Decimal` vira texto de duas casas (`_como_moeda` — DL-030:
    dinheiro nunca é número JSON), data vira ISO 8601, e o resto segue igual.

    Recursivo de propósito: `pendencias`/`avisos`/`linhas` crescem por dict e
    por lista, e uma tabela escrita à mão chave a chave envelheceria a cada
    pendência nova — a divergência apareceria como campo sumindo do JSON, não
    como erro. O contrato é o MESMO dicionário que a tela consome.
    """
    if isinstance(valor, Decimal):
        return _como_moeda(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {chave: _para_json_da_apuracao(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_para_json_da_apuracao(item) for item in valor]
    return valor


def _marcacoes_da_dmpl_para_json(lancamento):
    """O conjunto de marcações manuais de UM lançamento, no formato do
    GET/PUT/DELETE de `MarcacaoDmplView`: `{"lancamento_id", "marcacoes":
    [{linha, coluna, valor}]}`. `valor` como texto de duas casas (DL-030), e
    a mesma forma de leitura e de gravação — quem lê sabe o que manda.
    """
    return {
        "lancamento_id": lancamento.id,
        "marcacoes": [
            {
                "linha": marcacao.linha,
                "coluna": marcacao.coluna,
                "valor": _como_moeda(marcacao.valor),
            }
            for marcacao in MarcacaoDmpl.objects.filter(lancamento=lancamento).order_by("id")
        ],
    }


class DmplView(EmpresaEscopadaContabilMixin, APIView):
    """DL-061 (fatia 2, E18): `GET` da DMPL — a apuração inteira, o MESMO
    contrato da tela (e o mesmo padrão de `DlpaView`: a view REVELA, não
    recalcula — regra de negócio, autorização, isolamento e veto moram no
    serviço e na camada de permissões).

    **Autorização:** a das outras saídas contábeis com período —
    `PodeLerContabilidade`; CLIENTE nunca lê (403).

    **Período:** `ano`/`mes` identificam o RECURSO (o exercício até a
    competência pedida), mesmo padrão de `dlpa/<int:ano>/<int:mes>/`;
    `_validar_ano_mes` recusa fora da faixa com 400.

    **409 quando `pode_emitir` é falso, com o corpo INTEIRO mesmo assim:**
    mesmo desenho de `DlpaView` — o status informa o veto, não substitui a
    apuração (o cliente distingue "não pode emitir" de "o servidor não sabe
    ler" e vê o que falta, nomeado).
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id, ano, mes):
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        try:
            dmpl = apurar_dmpl(empresa=empresa, ano=ano, mes=mes)
        except HierarquiaInconsistente as exc:
            # Mesmo padrão do Balancete/Razão/DRE/DLPA: ciclo ou `conta_pai`
            # de outra empresa na hierarquia — resposta controlada, nunca 500.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        emissao = avaliar_emissao_da_dmpl(dmpl)
        corpo = _para_json_da_apuracao(dmpl)
        corpo.update(
            {
                "pode_emitir": emissao["pode_emitir"],
                "motivos": list(emissao["motivos"]),
                "listas_pendentes": _para_json_da_apuracao(emissao["listas_pendentes"]),
            }
        )
        status_code = status.HTTP_200_OK if emissao["pode_emitir"] else status.HTTP_409_CONFLICT
        return Response(corpo, status=status_code)


class ContaClassificacaoDmplView(EmpresaEscopadaContabilMixin, APIView):
    """DL-061 (fatia 2, E18): `PATCH` da COLUNA da DMPL (`classificacao_dmpl`)
    de uma conta já existente — o espelho de `ContaClassificacaoDlpaView`.

    Autenticação e autorização são as MESMAS da tela e da DLPA:
    `TemEscritorioAtivo` + `PodeEscriturar` (quem escritura classifica);
    CLIENTE 403. Corpo: `{"classificacao_dmpl": "<valor de ClassificacaoDmpl,
    ou null/"" para remover>"}` — um campo só
    (`CONTRATO_PATCH_CLASSIFICACAO_DMPL`).

    Validação em DUAS camadas, sem duplicar regra: o serializer valida o TIPO
    do corpo e do valor (400, nunca 500); a compatibilidade com `Conta.tipo`
    e com a DLPA é decidida por `Conta.full_clean()` dentro de
    `classificar_conta_na_dmpl`, com trilha (antes/depois) na MESMA
    transação. 200 com a conta serializada quando aceito; **404** quando a
    conta não existe NESTA empresa (isolamento — `filter(empresa=empresa)`,
    nunca consulta sem esse filtro).
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def patch(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        _recusar_dado_nao_contratado(request, CONTRATO_PATCH_CLASSIFICACAO_DMPL)

        entrada = ClassificacaoDmplPatchSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        classificacao = entrada.validated_data.get("classificacao_dmpl") or None

        try:
            classificar_conta_na_dmpl(
                conta=conta,
                classificacao=classificacao,
                usuario=request.user,
                request=request,
            )
        except ClassificacaoAlteraPeriodoFechado as exc:
            # DL-065 (BL-550): 409 pelo mesmo motivo da porta da DLPA acima —
            # recusa de ESTADO (competência encerrada ou entregue), não de
            # entrada. Nada gravado.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            raise DRFValidationError(
                {"classificacao_dmpl": mensagens_da_validacao_django(exc)}
            ) from exc

        return Response(ContaSerializer(conta).data, status=status.HTTP_200_OK)


class DfcView(EmpresaEscopadaContabilMixin, APIView):
    """DL-066 (etapa 2): `GET` da DFC — a apuração inteira, o MESMO contrato
    da tela (e o mesmo padrão de `DmplView`: a view REVELA, não recalcula —
    regra de negócio, autorização, isolamento e veto moram no serviço e na
    camada de permissões).

    **Autorização:** a das outras saídas contábeis com período —
    `PodeLerContabilidade`; CLIENTE nunca lê (403).

    **Período:** `ano`/`mes` identificam o RECURSO (o exercício até a
    competência pedida), mesmo padrão de `dmpl/<int:ano>/<int:mes>/`;
    `_validar_ano_mes` recusa fora da faixa com 400.

    **409 quando `pode_emitir` é falso, com o corpo INTEIRO mesmo assim:**
    mesmo desenho de `DmplView` — o status informa o veto, não substitui a
    apuração (o cliente vê o que falta, nomeado, inclusive a conciliação do
    método indireto quando ela não fecha).
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id, ano, mes):
        empresa = self.get_empresa()
        _validar_ano_mes(ano, mes)

        try:
            dfc = apurar_dfc(empresa=empresa, ano=ano, mes=mes)
        except HierarquiaInconsistente as exc:
            # Mesmo padrão do Balancete/Razão/DRE/DLPA/DMPL: ciclo ou
            # `conta_pai` de outra empresa na hierarquia — resposta
            # controlada, nunca 500.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        emissao = avaliar_emissao_da_dfc(dfc)
        corpo = _para_json_da_apuracao(dfc)
        corpo.update(
            {
                "pode_emitir": emissao["pode_emitir"],
                "motivos": list(emissao["motivos"]),
                "listas_pendentes": _para_json_da_apuracao(emissao["listas_pendentes"]),
            }
        )
        status_code = status.HTTP_200_OK if emissao["pode_emitir"] else status.HTTP_409_CONFLICT
        return Response(corpo, status=status_code)


class ContaClassificacaoDfcView(EmpresaEscopadaContabilMixin, APIView):
    """DL-066 (etapa 2): `PATCH` dos TRÊS campos da DFC
    (`caixa_e_equivalentes`, `classificacao_dfc`,
    `item_de_resultado_sem_caixa`) de uma conta já existente — o espelho de
    `ContaClassificacaoDmplView`, com a diferença de que o serviço recebe o
    ESTADO DESEJADO completo e grava com UMA trilha.

    Autenticação e autorização são as MESMAS da tela e das irmãs:
    `TemEscritorioAtivo` + `PodeEscriturar` (quem escritura classifica);
    CLIENTE 403. Corpo (`CONTRATO_PATCH_CLASSIFICACAO_DFC`): qualquer
    subconjunto dos três campos — o PATCH é parcial, e a fusão com o valor
    gravado acontece AQUI, nunca no serviço (que não tem sentinela de "não
    mexer").

    Validação em DUAS camadas, sem duplicar regra: o serializer valida a
    FORMA do corpo e do valor (400, nunca 500); as coerências (caixa ×
    atividade, item sem caixa só em resultado, guarda de período fechado da
    DL-065) são decididas por `Conta.full_clean()` dentro de
    `classificar_conta_na_dfc`, com trilha (antes/depois) na MESMA transação.
    200 com a conta serializada quando aceito; **409** para período fechado
    (recusa de ESTADO, nada gravado); **404** quando a conta não existe NESTA
    empresa (isolamento — `filter(empresa=empresa)`, nunca consulta sem esse
    filtro).
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def patch(self, request, empresa_id, conta_id):
        empresa = self.get_empresa()
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        _recusar_dado_nao_contratado(request, CONTRATO_PATCH_CLASSIFICACAO_DFC)

        entrada = ClassificacaoDfcPatchSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        try:
            classificar_conta_na_dfc(
                conta=conta,
                caixa_e_equivalentes=entrada.validated_data.get(
                    "caixa_e_equivalentes", conta.caixa_e_equivalentes
                ),
                classificacao_dfc=entrada.validated_data.get(
                    "classificacao_dfc", conta.classificacao_dfc
                ),
                item_de_resultado_sem_caixa=entrada.validated_data.get(
                    "item_de_resultado_sem_caixa", conta.item_de_resultado_sem_caixa
                ),
                usuario=request.user,
                request=request,
            )
        except ClassificacaoAlteraPeriodoFechado as exc:
            # DL-065 (BL-550), estendida aos três campos: 409 pelo mesmo
            # motivo da porta da DMPL — recusa de ESTADO (competência
            # encerrada ou entregue), não de entrada. Nada gravado.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            raise DRFValidationError(
                {"classificacao_dfc": mensagens_da_validacao_django(exc)}
            ) from exc

        return Response(ContaSerializer(conta).data, status=status.HTTP_200_OK)


class MarcacaoDmplView(EmpresaEscopadaContabilMixin, APIView):
    """DL-061 (fatia 2, BL-605, E18): a marcação manual da DMPL de UM
    lançamento — `GET` (ler o conjunto), `PUT` (substituir o conjunto
    inteiro, de uma vez) e `DELETE` (limpar, voltando para a regra
    automática). Mesmo padrão das rotas irmãs: o lançamento vem da URL,
    escopado à empresa (`get_object_or_404(..., empresa=empresa)` — lançamento
    de outra empresa é 404, nunca 403).

    **Permissões no servidor:** quem LÊ a contabilidade lê (`GET`);
    quem ESCRITURA marca e limpa (`PUT`/`DELETE`), o mesmo papel que grava
    lançamento — nenhuma permissão nova. CLIENTE recebe 403.

    **Contrato do corpo (PUT):** `{"marcacoes": [{"linha", "coluna",
    "valor"}]}` — o CONJUNTO completo (substituição atômica); lista vazia
    limpa. `valor` viaja como TEXTO (DE-030). As regras do conjunto (E16:
    Σ por coluna = movimento do lançamento; E17: só quando a regra não
    decide) são do SERVIÇO (`salvar_marcacoes_da_dmpl`), que traduz a
    recusa para 400 com a mensagem do que falta.

    **Nada confia em id recebido sem conferir a empresa:** a empresa vem da
    URL (revalidada contra o escritório ativo pelo mixin) e o lançamento é
    buscado DENTRO dela — igual a `EstornarLancamentoView`.

    **Período fechado (DL-071, BL-655):** `PUT` e `DELETE` respondem **409**
    quando alguma DMPL que lê o lançamento é de competência encerrada ou
    entregue (o serviço decide e diz qual); a consulta de período só acontece
    DEPOIS de o lançamento ser achado na empresa, então id alheio continua 404.
    """

    permission_classes = [TemEscritorioAtivo]

    def get_permissions(self):
        # Mesmo molde de `ContaListCreateView`: leitura para quem lê a
        # contabilidade; escrita (marcar/limpar) para quem escritura.
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "GET":
            permissions.append(PodeLerContabilidade())
        else:
            permissions.append(PodeEscriturar())
        return permissions

    def _lancamento_da_empresa(self, empresa, lancamento_id):
        return get_object_or_404(LancamentoContabil, pk=lancamento_id, empresa=empresa)

    def get(self, request, empresa_id, lancamento_id):
        empresa = self.get_empresa()
        lancamento = self._lancamento_da_empresa(empresa, lancamento_id)
        return Response(_marcacoes_da_dmpl_para_json(lancamento), status=status.HTTP_200_OK)

    def put(self, request, empresa_id, lancamento_id):
        # `get_empresa()` ANTES de qualquer leitura do corpo: a recusa de
        # livro-caixa é a primeira resposta desta API (a varredura da DL-038
        # exige a MESMA mensagem `{"empresa": [...]}` em todo método aceito).
        empresa = self.get_empresa()
        _recusar_dado_nao_contratado(request, CONTRATO_PUT_MARCACAO_DMPL)
        lancamento = self._lancamento_da_empresa(empresa, lancamento_id)

        entrada = MarcacaoDmplGravacaoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        try:
            # Substituição atômica com trilha, na transação do serviço.
            salvar_marcacoes_da_dmpl(
                lancamento=lancamento,
                marcacoes=entrada.validated_data["marcacoes"],
                usuario=request.user,
                request=request,
            )
        except ClassificacaoAlteraPeriodoFechado as exc:
            # DL-071 (BL-655): 409, pelo mesmo motivo e com a mesma tradução
            # das classificações de conta (DL-065) — o que recusa é o ESTADO
            # do período que a DMPL leria, não o corpo enviado. Nada foi
            # gravado: a recusa vem antes de qualquer escrita do serviço.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except MarcacaoDmplInvalida as exc:
            raise DRFValidationError(str(exc)) from exc

        return Response(_marcacoes_da_dmpl_para_json(lancamento), status=status.HTTP_200_OK)

    def delete(self, request, empresa_id, lancamento_id):
        empresa = self.get_empresa()
        _recusar_dado_nao_contratado(request, CONTRATO_DELETE_MARCACAO_DMPL)
        lancamento = self._lancamento_da_empresa(empresa, lancamento_id)

        try:
            remover_marcacoes_da_dmpl(lancamento=lancamento, usuario=request.user, request=request)
        except ClassificacaoAlteraPeriodoFechado as exc:
            # DL-071 (BL-655): remover também é reclassificar a leitura (o
            # veto da DMPL volta a valer), então a trava é a mesma do PUT.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(_marcacoes_da_dmpl_para_json(lancamento), status=status.HTTP_200_OK)


class ConferenciaLotesDesbalanceadosView(EmpresaEscopadaContabilMixin, APIView):
    """Conferência de inconsistências da base contábil da empresa (BL-64, DL-015).

    Sem período: uma base torta é torta em qualquer recorte. Em operação
    normal nada disto deveria existir — `criar_lancamento` impede a
    gravação de um lançamento desbalanceado, e `Conta.clean()` impede a
    reclassificação de uma conta com movimento e o ciclo na hierarquia
    (achados 2 e 6); esta rota existe para achar o que foi gravado ou
    alterado por outro caminho (ex.: acesso direto ao ORM).

    Quatro categorias, cada uma reportada mesmo que as outras estejam vazias:

    - `lotes`: lançamentos com menos de duas partidas — `motivo`
      "sem_partidas" (zero itens) ou "partida_unica" (exatamente um item) —
      ou com débito diferente de crédito (`motivo` "desbalanceado") —
      achado 9, rótulo de três vias corrigido pelo achado novo 12 (antes,
      um lote com UMA partida de 5,00 aparecia como "sem_partidas" na MESMA
      linha em que o total mostrava 5,00 — a própria ferramenta de
      diagnóstico se contradizia).
    - `contas_sinteticas_com_movimento`: contas marcadas como sintéticas que
      já têm itens de lançamento próprios — achado 2.
    - `contas_que_aceitam_lancamento_e_tem_subordinadas`: quarta categoria
      (DE-022, achado novo 1) — conta que aceita lançamento direto E tem
      contas subordinadas. NÃO é erro nem é bloqueado (a DE-022 explica por
      quê); é só para o contador enxergar o caso.
    - `hierarquia_inconsistente`: mensagens descrevendo ciclo ou
      `conta_pai` de outra empresa no plano de contas — achado 6, agora
      acumulando TODAS as inconsistências encontradas, não só a primeira
      (achado novo 13).
    """

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()

        def _motivo(lancamento):
            # Achado novo 12: três motivos, não dois — "sem_partidas" (zero
            # itens) e "partida_unica" (um item) são casos DIFERENTES de
            # "desbalanceado" (duas ou mais partidas cuja soma não fecha), e
            # confundi-los fazia a própria conferência se contradizer (uma
            # linha dizendo "sem_partidas" ao lado de um total de 5,00).
            if lancamento.quantidade_itens == 0:
                return "sem_partidas"
            if lancamento.quantidade_itens == 1:
                return "partida_unica"
            return "desbalanceado"

        lotes = [
            {
                "id": lancamento.id,
                "data": lancamento.data.isoformat(),
                "historico": lancamento.historico,
                "total_debito": _como_moeda(lancamento.total_debito),
                "total_credito": _como_moeda(lancamento.total_credito),
                "diferenca": _como_moeda(lancamento.total_debito - lancamento.total_credito),
                "motivo": _motivo(lancamento),
            }
            for lancamento in localizar_lotes_desbalanceados(empresa=empresa)
        ]

        contas_sinteticas_com_movimento = [
            {
                "conta": conta.codigo,
                "nome": conta.nome,
                "debitos": _como_moeda(conta.debitos),
                "creditos": _como_moeda(conta.creditos),
            }
            for conta in localizar_contas_sinteticas_com_movimento(empresa=empresa)
        ]

        contas_que_aceitam_lancamento_e_tem_subordinadas = [
            {"conta": conta.codigo, "nome": conta.nome}
            for conta in localizar_contas_que_aceitam_lancamento_e_tem_subordinadas(empresa=empresa)
        ]

        # BL-198, quinta categoria: a Conferência não tem período — uma base
        # torta é torta em qualquer recorte —, então aqui o equivalente ao
        # aviso das outras três saídas é listar o que está FORA DA FAIXA
        # PLAUSÍVEL (RC-77). É a única saída em que o `9999-12-31` já gravado
        # aparece sem o contador precisar suspeitar primeiro: validar a
        # entrada fecha a porta, e isto acende a luz sobre o que já entrou
        # (a DL-020 declara o reparo de dado já gravado fora de escopo).
        lancamentos_com_data_fora_da_faixa = [
            {
                "id": lancamento.id,
                "data": lancamento.data.isoformat(),
                "historico": lancamento.historico,
            }
            for lancamento in localizar_lancamentos_com_data_fora_da_faixa(empresa=empresa)
        ]

        return Response(
            {
                "lotes": lotes,
                "lancamentos_com_data_fora_da_faixa": lancamentos_com_data_fora_da_faixa,
                "contas_sinteticas_com_movimento": contas_sinteticas_com_movimento,
                "contas_que_aceitam_lancamento_e_tem_subordinadas": (
                    contas_que_aceitam_lancamento_e_tem_subordinadas
                ),
                "hierarquia_inconsistente": localizar_inconsistencias_de_hierarquia(
                    empresa=empresa
                ),
            }
        )


# ---------------------------------------------------------------------------
# DL-077 (fatia 1): importação e exportação do plano de contas em arquivo.
#
# Três rotas, e a separação é de propósito: a PRÉVIA lê e confere sem gravar; a
# APLICAÇÃO recebe o arquivo de novo e recusa se ele não for o que foi revisado
# (SHA-256 e assinatura da prévia); a EXPORTAÇÃO devolve o arquivo. Importar e
# aplicar exigem o mesmo papel que escreve o plano (`PodeEscriturar`); exportar
# exige o papel que lê a contabilidade. CLIENTE não passa em nenhuma das três.
# ---------------------------------------------------------------------------

# Contratos declarados por campo (política dos cinco dicionários, BL-196): o
# arquivo é aceito por ser multipart, e nenhum outro campo de corpo ou URL passa.
CONTRATO_POST_IMPORTACAO_PLANO = ContratoDeRequisicao(
    campos={"arquivo", "formato", "politica", "prefixos"},
    aceita_arquivo=True,
    contexto="na conferência do plano de contas",
)
CONTRATO_POST_APLICACAO_PLANO = ContratoDeRequisicao(
    campos={"arquivo", "formato", "politica", "prefixos", "sha256", "assinatura"},
    aceita_arquivo=True,
    contexto="na aplicação do plano de contas",
)
CAMPOS_QUERYSTRING_EXPORTACAO_PLANO = frozenset(
    {"formato", "filtro", "inicio", "fim", "data_alteracao"}
)


class ArquivoAcimaDoLimite(APIException):
    """Arquivo acima do limite de tamanho ou de linhas (HTTP 413)."""

    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "Arquivo acima do limite."
    default_code = "arquivo_acima_do_limite"


# Campos de TEXTO do multipart da importação (A7/A10). Enviados como arquivo, o `.strip()`
# da view estourava em 500 (BL-196/R6-2). A recusa sai antes de qualquer leitura, no campo.
_CAMPOS_DE_TEXTO_DA_IMPORTACAO = ("formato", "politica", "prefixos", "sha256", "assinatura")


def _entrada_da_importacao(request, *, com_token):
    """Lê e valida os campos do multipart. Devolve (formato, política, prefixos, arquivo).

    `com_token=True` (aplicação) exige também `sha256` e `assinatura`, os dois
    valores que a prévia devolveu. Erro de campo vira 400 com o nome do campo.
    """
    erros_de_texto = {
        campo: [f"o campo '{campo}' é texto: não envie arquivo nele."]
        for campo in _CAMPOS_DE_TEXTO_DA_IMPORTACAO
        if campo in request.FILES
    }
    if erros_de_texto:
        raise DRFValidationError(erros_de_texto)

    arquivo = request.FILES.get("arquivo")
    erros = {}
    if arquivo is None:
        erros["arquivo"] = ["Envie o plano no campo 'arquivo' (multipart)."]

    formato = (request.data.get("formato") or "").strip()
    if formato not in LEITORES:
        erros["formato"] = [
            f"formato '{formato}' não suportado nesta versão. Use: {', '.join(sorted(LEITORES))}."
        ]

    politica = (request.data.get("politica") or POLITICA_SO_ACRESCENTAR).strip()
    try:
        validar_politica(politica)
    except ParametroInvalido as exc:
        erros["politica"] = [exc.mensagem]

    prefixos = {}
    try:
        prefixos = validar_prefixos(json.loads(request.data.get("prefixos") or "{}"))
    except (ValueError, TypeError):
        erros["prefixos"] = ['prefixos deve ser um objeto JSON, por exemplo {"3": "receita"}.']
    except ParametroInvalido as exc:
        erros["prefixos"] = [exc.mensagem]

    if com_token:
        for campo in ("sha256", "assinatura"):
            if not (request.data.get(campo) or "").strip():
                erros[campo] = ["Informe o valor devolvido pela prévia."]

    # Excel: só `.xlsx`. O conteúdo é conferido de novo no leitor (macro, .xls,
    # CSV renomeado), mas o nome é a primeira barreira e a mensagem mais clara.
    if formato == excel.FORMATO and arquivo is not None:
        if not arquivo.name.lower().endswith(".xlsx"):
            erros["arquivo"] = [
                "a planilha precisa ser .xlsx, sem macros (.xlsm não é aceito). "
                "Use o modelo para baixar."
            ]

    if erros:
        raise DRFValidationError(erros)
    # A11 (limite de corpo): esta checagem vem DEPOIS de o Django receber o corpo inteiro, e
    # é por isso que não basta. O limite de corpo da requisição (ex.: `client_max_body_size`
    # no proxy à frente) é de implantação e não está no repositório: o proxy DEVE limitar o
    # corpo antes do aplicativo, senão o servidor grava um arquivo grande em disco antes do 413.
    if arquivo.size > TAMANHO_MAXIMO_ARQUIVO_BYTES:
        raise ArquivoAcimaDoLimite(
            f"arquivo com {arquivo.size} bytes; o limite é "
            f"{TAMANHO_MAXIMO_ARQUIVO_BYTES // (1024 * 1024)} MB."
        )
    return formato, politica, prefixos, arquivo


def _ler_e_conferir(empresa, arquivo, formato, politica, prefixos):
    """Lê o arquivo com o leitor do formato e confere contra o cadastro. Não grava.

    A conferência do CNPJ/CPF declarado no arquivo é do NÚCLEO (`conferir_plano`), não
    desta view: assim vale para qualquer porta que use o plano, e não só esta API.
    """
    try:
        resultado = ler_arquivo(formato, arquivo.read(), nome_arquivo=arquivo.name)
    except ArquivoGrandeDemais as exc:
        raise ArquivoAcimaDoLimite(exc.mensagem) from exc
    except IntercambioRecusado as exc:
        raise DRFValidationError({"arquivo": [exc.mensagem]}) from exc
    try:
        return conferir_plano(empresa, resultado, politica, prefixos)
    except ArquivoGrandeDemais as exc:
        # Teto de contas por importação (A6): é o núcleo que recusa, e a API responde 413.
        raise ArquivoAcimaDoLimite(exc.mensagem) from exc


def _ocorrencia_como_dict(ocorrencia):
    return {
        "linha": ocorrencia.linha,
        "campo": ocorrencia.campo,
        "nivel": ocorrencia.nivel,
        "mensagem": ocorrencia.mensagem,
    }


def _previa_como_dict(previa):
    """Forma da prévia na API: o que o contador revisa, conta a conta."""
    return {
        "formato": previa.resultado.formato,
        "politica": previa.politica,
        "nome_arquivo": previa.resultado.nome_arquivo,
        "codificacao": previa.resultado.codificacao,
        "sha256": previa.sha256,
        "assinatura": previa.assinatura,
        "pode_aplicar": not previa.tem_erro,
        "contagens": previa.contagens,
        "registros_ignorados": previa.resultado.registros_ignorados,
        "itens": [
            {
                "linha": item.linha,
                "codigo": item.codigo,
                "nome": item.nome,
                "codigo_pai": item.codigo_pai,
                "analitica": item.analitica,
                "acao": item.acao,
                "tipo": item.tipo,
                "origem_tipo": item.origem_tipo,
                "natureza": item.natureza,
                "origem_natureza": item.origem_natureza,
                "ocorrencias": [_ocorrencia_como_dict(o) for o in item.ocorrencias],
            }
            for item in previa.itens
        ],
        "ocorrencias": [_ocorrencia_como_dict(o) for o in previa.ocorrencias],
    }


class PlanoDeContasImportacaoPreviaView(EmpresaEscopadaContabilMixin, APIView):
    """Prévia da importação: lê o arquivo e confere. Não grava nada."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def post(self, request, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_IMPORTACAO_PLANO)
        empresa = self.get_empresa()
        formato, politica, prefixos, arquivo = _entrada_da_importacao(request, com_token=False)
        previa = _ler_e_conferir(empresa, arquivo, formato, politica, prefixos)
        return Response(_previa_como_dict(previa))


class PlanoDeContasImportacaoAplicarView(EmpresaEscopadaContabilMixin, APIView):
    """Aplica o plano. Recebe o arquivo de novo e exige o SHA-256 e a assinatura da prévia.

    409 se o arquivo ou o cadastro mudaram desde a prévia; 400 com as ocorrências
    se o plano tem erro. Nada é gravado em nenhum desses casos.
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def post(self, request, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_APLICACAO_PLANO)
        empresa = self.get_empresa()
        formato, politica, prefixos, arquivo = _entrada_da_importacao(request, com_token=True)
        previa = _ler_e_conferir(empresa, arquivo, formato, politica, prefixos)
        try:
            aplicado = aplicar_plano(
                empresa,
                previa,
                request.user,
                request,
                sha256_esperado=request.data["sha256"].strip(),
                assinatura_esperada=request.data["assinatura"].strip(),
            )
        except (ArquivoAlteradoDesdeAPrevia, PlanoAlteradoDesdeAPrevia) as exc:
            return Response({"plano": [exc.mensagem]}, status=status.HTTP_409_CONFLICT)
        except PlanoRecusado as exc:
            return Response(
                {
                    "plano": [exc.mensagem],
                    "ocorrencias": [_ocorrencia_como_dict(o) for o in exc.ocorrencias],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CompetenciaOperacaoRecusada as exc:
            # Outra operação de zeramento ou parâmetro está em curso na empresa:
            # conflito de estado, não entrada malformada.
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                "aplicado": True,
                "criadas": aplicado.criadas,
                "atualizadas": aplicado.atualizadas,
                "sem_mudanca": aplicado.sem_mudanca,
                "sha256": aplicado.sha256,
                "assinatura": aplicado.assinatura,
            }
        )


class PlanoDeContasModeloExcelView(EmpresaEscopadaContabilMixin, APIView):
    """Baixa o modelo `.xlsx` da importação do plano (aba `plano` e aba `instrucoes`).

    O modelo não depende da empresa, mas a rota passa por `get_empresa()` mesmo assim:
    é o que aplica o isolamento por escritório e a recusa do modo livro-caixa (DL-038)
    a esta rota, como a todas as outras da contabilidade.
    """

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def get(self, request, *args, **kwargs):
        try:
            recusar_campos_nao_contratados(
                request.query_params,
                frozenset(),
                contexto="no modelo do plano de contas",
            )
        except DadoNaoContratado as exc:
            raise DRFValidationError(exc.mensagem) from exc
        self.get_empresa()
        resposta = HttpResponse(excel.gerar_modelo(), content_type=TIPO_DE_CONTEUDO_XLSX)
        resposta["Content-Disposition"] = 'attachment; filename="modelo-plano-de-contas.xlsx"'
        return resposta


# Sufixo do nome do arquivo por leiaute. Nenhum deles usa "ECD" nem "SPED": o arquivo
# não é a ECD, e o nome não pode dizer que é (ver `formatos/ecd.py`).
_SUFIXO_DO_ARQUIVO_EXPORTADO = {
    "ecd": "registros-I050",
    referencia.FORMATO: "leiaute-com-separador",
}
# Leiaute em ISO-8859-1 (ECD e leiaute com separador). O formato próprio é UTF-8.
_FORMATOS_EM_ISO_8859_1 = frozenset({"ecd", referencia.FORMATO})
TIPO_DE_CONTEUDO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _nome_do_arquivo_exportado(empresa, formato, hoje):
    """`plano-<documento>-<aaaammdd>-<sufixo>.txt`, sem as palavras ECD nem SPED.

    Decisão do arquiteto-senior (DL-077): o arquivo no leiaute da ECD se chama
    `registros-I050`, que diz o que ele contém (registros I050/I051), e não que
    ele é a ECD: não tem bloco J, termos nem assinatura (ver `formatos/ecd.py`).
    """
    documento = re.sub(r"[^0-9A-Za-z]", "", empresa.cnpj or empresa.cpf or "") or "sem-documento"
    sufixo = _SUFIXO_DO_ARQUIVO_EXPORTADO.get(formato, "formato-dataledger")
    return f"plano-{documento}-{hoje:%Y%m%d}-{sufixo}.txt"


class PlanoDeContasExportacaoView(EmpresaEscopadaContabilMixin, APIView):
    """Exporta o plano da empresa. Filtros: todas | analiticas | com_movimento."""

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, *args, **kwargs):
        try:
            recusar_campos_nao_contratados(
                request.query_params,
                CAMPOS_QUERYSTRING_EXPORTACAO_PLANO,
                contexto="na exportação do plano de contas",
            )
        except DadoNaoContratado as exc:
            raise DRFValidationError(exc.mensagem) from exc

        empresa = self.get_empresa()
        parametros = request.query_params
        formato = (parametros.get("formato") or "").strip()
        filtro = (parametros.get("filtro") or "todas").strip()
        try:
            inicio = para_data(parametros["inicio"]) if "inicio" in parametros else None
            fim = para_data(parametros["fim"]) if "fim" in parametros else None
            data_alteracao = (
                para_data(parametros["data_alteracao"]) if "data_alteracao" in parametros else None
            )
        except DataInvalida as exc:
            raise DRFValidationError({"data": [str(exc)]}) from exc

        try:
            arquivo = exportar_plano(
                empresa=empresa,
                formato=formato,
                filtro=filtro,
                inicio=inicio,
                fim=fim,
                data_alteracao=data_alteracao,
            )
        except IntercambioRecusado as exc:
            raise DRFValidationError({"plano": [exc.mensagem]}) from exc

        registrar(
            acao="plano_de_contas.exportado",
            objeto=empresa,
            escritorio=empresa.escritorio,
            usuario=request.user,
            request=request,
            detalhes={
                "formato": arquivo.formato,
                "filtro": arquivo.filtro,
                "inicio": inicio.isoformat() if inicio else None,
                "fim": fim.isoformat() if fim else None,
                "quantidade_contas": arquivo.quantidade_contas,
                "sinteticas_incluidas": arquivo.sinteticas_incluidas,
                "sha256": arquivo.sha256,
                "avisos": list(arquivo.avisos),
            },
        )

        if formato in _FORMATOS_EM_ISO_8859_1:
            tipo_do_conteudo = "text/plain; charset=iso-8859-1"
        else:
            tipo_do_conteudo = "text/plain; charset=utf-8"
        resposta = HttpResponse(arquivo.conteudo, content_type=tipo_do_conteudo)
        nome = _nome_do_arquivo_exportado(empresa, arquivo.formato, timezone.localdate())
        resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
        # Avisos do formato (ASCII, por isso cabem em cabeçalho HTTP). Juntos, separados por
        # "; ". Ausente quando o formato não tem aviso.
        if arquivo.avisos:
            resposta["X-DataLedger-Avisos"] = "; ".join(arquivo.avisos)
        return resposta


# ---------------------------------------------------------------------------
# DL-077 (fatia 2): exportação de lançamentos e saldos.
#
# Uma rota de API (GET), com o arquivo no corpo e o relatório de conferência nos
# cabeçalhos `X-DataLedger-*`. O parâmetro `sha256`, opcional, é o SHA-256 que a tela
# mostrou na conferência: se os lançamentos mudaram desde então, o arquivo gerado é outro,
# e a API responde 409 em vez de entregar um arquivo que o contador não conferiu.
# Exportar exige o papel que lê a contabilidade (`PodeLerContabilidade`). Empresa em modo
# livro-caixa é recusada pela mixin, como nas demais rotas da contabilidade (DL-038).
# ---------------------------------------------------------------------------

CAMPOS_QUERYSTRING_EXPORTACAO_LANCAMENTOS = frozenset(
    {
        "formato",
        "inicio",
        "fim",
        "incluir_saldos",
        "omitir_nao_representaveis",
        "normalizar_texto",
        "sha256",
    }
)


class ConferenciaDesatualizada(APIException):
    """Os lançamentos mudaram desde a conferência que o contador viu (HTTP 409)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Os lançamentos mudaram desde a conferência. Confira o arquivo de novo."
    default_code = "conferencia_desatualizada"


def _booleano_da_querystring(parametros, nome):
    """`true`/`1` ou `false`/`0` (ou ausente, que é false). Qualquer outro valor é erro."""
    valor = (parametros.get(nome) or "").strip().lower()
    if valor in ("", "false", "0"):
        return False
    if valor in ("true", "1"):
        return True
    raise DRFValidationError({nome: [f"valor '{valor}' inválido: use true ou false."]})


class LancamentosExportacaoView(EmpresaEscopadaContabilMixin, APIView):
    """Exporta os lançamentos (e saldos, na ECD) da empresa no intervalo pedido."""

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, *args, **kwargs):
        try:
            recusar_campos_nao_contratados(
                request.query_params,
                CAMPOS_QUERYSTRING_EXPORTACAO_LANCAMENTOS,
                contexto="na exportação de lançamentos",
            )
        except DadoNaoContratado as exc:
            raise DRFValidationError(exc.mensagem) from exc

        empresa = self.get_empresa()
        parametros = request.query_params
        formato = (parametros.get("formato") or "").strip()
        try:
            inicio = para_data(parametros["inicio"]) if parametros.get("inicio") else None
            fim = para_data(parametros["fim"]) if parametros.get("fim") else None
        except DataInvalida as exc:
            raise DRFValidationError({"data": [str(exc)]}) from exc
        incluir_saldos = _booleano_da_querystring(parametros, "incluir_saldos")
        omitir = _booleano_da_querystring(parametros, "omitir_nao_representaveis")
        normalizar = _booleano_da_querystring(parametros, "normalizar_texto")
        sha_conferido = (parametros.get("sha256") or "").strip().lower() or None

        try:
            arquivo = exportar_lancamentos(
                empresa=empresa,
                formato=formato,
                data_inicial=inicio,
                data_final=fim,
                incluir_saldos=incluir_saldos,
                omitir_nao_representaveis=omitir,
                normalizar_texto=normalizar,
                usuario=request.user,
            )
        except IntercambioRecusado as exc:
            raise DRFValidationError({"lancamentos": [exc.mensagem]}) from exc

        if sha_conferido is not None and sha_conferido != arquivo.sha256:
            raise ConferenciaDesatualizada()

        relatorio = arquivo.relatorio
        registrar(
            acao="lancamentos.exportados",
            objeto=empresa,
            escritorio=empresa.escritorio,
            usuario=request.user,
            request=request,
            detalhes=relatorio.para_trilha(),
        )

        if formato == "proprio":
            tipo_do_conteudo = "text/plain; charset=utf-8"
        else:
            tipo_do_conteudo = "text/plain; charset=iso-8859-1"
        resposta = HttpResponse(arquivo.conteudo, content_type=tipo_do_conteudo)
        resposta["Content-Disposition"] = f'attachment; filename="{relatorio.nome_do_arquivo}"'
        resposta["X-DataLedger-Sha256"] = relatorio.sha256
        resposta["X-DataLedger-Lancamentos"] = str(relatorio.quantidade_lancamentos)
        resposta["X-DataLedger-Partidas"] = str(relatorio.quantidade_partidas)
        resposta["X-DataLedger-Soma-Debitos"] = str(relatorio.soma_debitos)
        resposta["X-DataLedger-Soma-Creditos"] = str(relatorio.soma_creditos)
        resposta["X-DataLedger-Omitidos"] = str(relatorio.quantidade_omitidos)
        resposta["X-DataLedger-Textos-Normalizados"] = str(len(relatorio.textos_normalizados))
        if relatorio.avisos:
            resposta["X-DataLedger-Avisos"] = "; ".join(relatorio.avisos)
        return resposta


# ---------------------------------------------------------------------------
# DL-077 (fatia 3, frente A): importação de lançamentos com área de conferência.
#
# Quem RECEBE, CONFERE, define o de-para, aceita avisos, EFETIVA e DESCARTA é quem escritura
# (`PodeEscriturar`; efetivar é o mesmo papel que lança à mão). Quem LÊ a importação e o de-para é
# quem lê a contabilidade (`PodeLerContabilidade`, que inclui PARALEGAL). CLIENTE não passa. Empresa
# em livro-caixa é recusada pela mixin, como nas demais rotas (DL-038). Nada aqui grava no Diário
# além da efetivação, e ela passa pelo serviço (`efetivar`), não pela view.
# ---------------------------------------------------------------------------

CONTRATO_POST_RECEBER_LANCAMENTOS = ContratoDeRequisicao(
    campos={"arquivo", "formato"},
    aceita_arquivo=True,
    contexto="no envio de lançamentos",
)
CONTRATO_POST_EFETIVAR_LANCAMENTOS = ContratoDeRequisicao(
    campos={"politica"}, contexto="na efetivação de lançamentos"
)
CONTRATO_POST_AVISOS_LANCAMENTOS = ContratoDeRequisicao(
    campos={"numeros", "aceitar_arquivo"}, contexto="no aceite de avisos"
)
CONTRATO_POST_DESCARTE_LANCAMENTOS = ContratoDeRequisicao(
    campos={"motivo"}, contexto="no descarte da importação"
)
CONTRATO_POST_DEPARA_LANCAMENTOS = ContratoDeRequisicao(
    campos={"formato", "codigo_origem", "conta"}, contexto="no de-para de contas"
)
CAMPOS_QUERYSTRING_DETALHE_IMPORTACAO = frozenset({"pagina", "tamanho", "filtro"})
CAMPOS_QUERYSTRING_DEPARA = frozenset({"formato"})
TAMANHO_PADRAO_PAGINA_IMPORTACAO = 50
TAMANHO_MAXIMO_PAGINA_IMPORTACAO = 200
FILTROS_DA_IMPORTACAO = ("todos", "erros", "avisos")


def _resposta_da_recusa(exc):
    """Traduz a recusa do serviço em HTTP. Conflito de estado é 409; entrada ruim é 400."""
    if isinstance(exc, importacao_lancamentos.ImportacaoJaExiste):
        return Response(
            {"detail": str(exc), "importacao_id": exc.importacao_id},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, importacao_lancamentos.ImportacaoEmEstadoInvalido):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, (CompetenciaEncerrada, CompetenciaOperacaoRecusada)):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, importacao_lancamentos.ImportacaoNaoEfetivada):
        return Response(
            {"detail": str(exc), "ocorrencias": list(exc.ocorrencias)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, ArquivoGrandeDemais):
        return Response({"detail": str(exc)}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _importacao_como_dict(importacao, *, com_ocorrencias=True):
    """A importação como a API a devolve. As ocorrências do arquivo ficam FORA da lista (A8).

    `ocorrencias_do_arquivo` traz no máximo 500 itens; `quantidade_ocorrencias_do_arquivo`, o total.
    A lista de importações (`com_ocorrencias=False`) não as traz: uma importação com 190.000 linhas
    inválidas faria a resposta da lista ter dezenas de MB.
    """
    dados = {
        "id": importacao.pk,
        "formato": importacao.formato,
        "nome_arquivo": importacao.nome_arquivo,
        "sha256": importacao.sha256,
        "estado": importacao.estado,
        "politica_de_efetivacao": importacao.politica_de_efetivacao,
        "quantidade_lancamentos": importacao.quantidade_lancamentos,
        "quantidade_com_erro": importacao.quantidade_com_erro,
        "quantidade_com_aviso": importacao.quantidade_com_aviso,
        "quantidade_efetivados": importacao.quantidade_efetivados,
        "quantidade_nao_efetivados": importacao.quantidade_nao_efetivados,
        "soma_debitos": str(importacao.soma_debitos),
        "soma_creditos": str(importacao.soma_creditos),
        "soma_debitos_efetivados": str(importacao.soma_debitos_efetivados),
        "soma_creditos_efetivados": str(importacao.soma_creditos_efetivados),
        "quantidade_ocorrencias_do_arquivo": importacao.quantidade_ocorrencias_do_arquivo,
        "quantidade_erros_do_arquivo": importacao.quantidade_erros_do_arquivo,
        "quantidade_erros_do_arquivo_inteiro": importacao.quantidade_erros_do_arquivo_inteiro,
        "exige_aceite_do_arquivo": importacao.exige_aceite_do_arquivo,
        "aceite_do_arquivo": importacao.aceite_do_arquivo,
        "criado_em": importacao.criado_em.isoformat(),
        "efetivada_em": importacao.efetivada_em.isoformat() if importacao.efetivada_em else None,
        "descartada_em": importacao.descartada_em.isoformat() if importacao.descartada_em else None,
        "motivo_do_descarte": importacao.motivo_do_descarte,
    }
    if com_ocorrencias:
        dados["ocorrencias_do_arquivo"] = importacao.ocorrencias_do_arquivo
    return dados


def _lancamento_importado_como_dict(lancamento):
    return {
        "id": lancamento.pk,
        "numero_origem": lancamento.numero_origem,
        "linha": lancamento.linha,
        "data": lancamento.data.isoformat(),
        "historico": lancamento.historico,
        "partidas": lancamento.partidas,
        "ocorrencias": lancamento.ocorrencias,
        "tem_erro": lancamento.tem_erro,
        "tem_aviso": lancamento.tem_aviso,
        "aceito_com_aviso": lancamento.aceito_com_aviso,
        "lancamento_id": lancamento.lancamento_id,
    }


def _importacao_da_empresa(empresa, importacao_id):
    """Busca a importação DENTRO da empresa da URL. Outra empresa responde 404, nunca o registro."""
    return get_object_or_404(ImportacaoLancamentos, pk=importacao_id, empresa=empresa)


class ImportacaoLancamentosListarEnviarView(EmpresaEscopadaContabilMixin, APIView):
    """Lista as importações da empresa (GET) e recebe um arquivo em conferência (POST)."""

    permission_classes = [TemEscritorioAtivo]

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturar())
        else:
            permissions.append(PodeLerContabilidade())
        return permissions

    def get(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        importacoes = importacao_lancamentos.listar_importacoes(empresa)[:200]
        return Response(
            {"importacoes": [_importacao_como_dict(i, com_ocorrencias=False) for i in importacoes]}
        )

    def post(self, request, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_RECEBER_LANCAMENTOS)
        empresa = self.get_empresa()
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            raise DRFValidationError(
                {"arquivo": ["Envie o arquivo no campo 'arquivo' (multipart)."]}
            )
        if arquivo.size > TAMANHO_MAXIMO_ARQUIVO_BYTES:
            raise ArquivoAcimaDoLimite(
                f"arquivo com {arquivo.size} bytes; o limite é "
                f"{TAMANHO_MAXIMO_ARQUIVO_BYTES // (1024 * 1024)} MB."
            )
        formato = (request.data.get("formato") or "").strip()
        try:
            importacao = importacao_lancamentos.receber(
                empresa=empresa,
                formato=formato,
                conteudo=arquivo.read(),
                nome_arquivo=arquivo.name,
                usuario=request.user,
                request=request,
            )
        except IntercambioRecusado as exc:
            return _resposta_da_recusa(exc)
        # R2: a resposta do envio mostra os registros que a leitura ignorou (contados, como a prévia
        # do plano). Não são gravados em campo; a trilha guarda a mesma contagem.
        dados = _importacao_como_dict(importacao)
        dados["registros_ignorados"] = importacao.registros_ignorados_da_leitura
        return Response(dados, status=status.HTTP_201_CREATED)


class ImportacaoLancamentosDetalheView(EmpresaEscopadaContabilMixin, APIView):
    """A importação com os lançamentos da conferência, paginados, e as ocorrências do arquivo."""

    permission_classes = [TemEscritorioAtivo, PodeLerContabilidade]

    def get(self, request, importacao_id, *args, **kwargs):
        try:
            recusar_campos_nao_contratados(
                request.query_params,
                CAMPOS_QUERYSTRING_DETALHE_IMPORTACAO,
                contexto="na conferência de lançamentos",
            )
        except DadoNaoContratado as exc:
            raise DRFValidationError(exc.mensagem) from exc

        empresa = self.get_empresa()
        importacao = _importacao_da_empresa(empresa, importacao_id)
        parametros = request.query_params
        try:
            pagina = max(1, int(parametros.get("pagina") or 1))
            tamanho = min(
                TAMANHO_MAXIMO_PAGINA_IMPORTACAO,
                max(1, int(parametros.get("tamanho") or TAMANHO_PADRAO_PAGINA_IMPORTACAO)),
            )
        except ValueError as exc:
            raise DRFValidationError({"pagina": ["pagina e tamanho são inteiros."]}) from exc
        filtro = (parametros.get("filtro") or "todos").strip()
        if filtro not in FILTROS_DA_IMPORTACAO:
            raise DRFValidationError(
                {"filtro": [f"use um de: {', '.join(FILTROS_DA_IMPORTACAO)}."]}
            )

        lancamentos = importacao.lancamentos.all()
        if filtro == "erros":
            lancamentos = lancamentos.filter(tem_erro=True)
        elif filtro == "avisos":
            lancamentos = lancamentos.filter(tem_aviso=True)
        total = lancamentos.count()
        inicio = (pagina - 1) * tamanho
        return Response(
            {
                "importacao": _importacao_como_dict(importacao),
                "lancamentos": [
                    _lancamento_importado_como_dict(lancamento)
                    for lancamento in lancamentos[inicio : inicio + tamanho]
                ],
                "paginacao": {"pagina": pagina, "tamanho": tamanho, "total": total},
            }
        )


class _AcaoSobreImportacaoView(EmpresaEscopadaContabilMixin, APIView):
    """Base das rotas de ação (POST) sobre uma importação: papel de escrituração e empresa certa."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturar]

    def _importacao(self, importacao_id):
        return _importacao_da_empresa(self.get_empresa(), importacao_id)


class ImportacaoLancamentosReconferirView(_AcaoSobreImportacaoView):
    def post(self, request, importacao_id, *args, **kwargs):
        _recusar_dado_nao_contratado(
            request, ContratoDeRequisicao(campos=frozenset(), contexto="na reconferência")
        )
        importacao = self._importacao(importacao_id)
        try:
            atual = importacao_lancamentos.reconferir(
                importacao, usuario=request.user, request=request
            )
        except (IntercambioRecusado, CompetenciaOperacaoRecusada) as exc:
            return _resposta_da_recusa(exc)
        return Response(_importacao_como_dict(atual))


class ImportacaoLancamentosAvisosView(_AcaoSobreImportacaoView):
    def post(self, request, importacao_id, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_AVISOS_LANCAMENTOS)
        importacao = self._importacao(importacao_id)
        numeros = request.data.get("numeros", [])
        if not isinstance(numeros, list):
            raise DRFValidationError({"numeros": ["envie a lista de números de lançamento."]})
        aceitar_arquivo = request.data.get("aceitar_arquivo", False)
        if not isinstance(aceitar_arquivo, bool):
            raise DRFValidationError({"aceitar_arquivo": ["use true ou false."]})
        try:
            quantidade = importacao_lancamentos.aceitar_avisos(
                importacao,
                numeros,
                aceitar_arquivo=aceitar_arquivo,
                usuario=request.user,
                request=request,
            )
        except IntercambioRecusado as exc:
            return _resposta_da_recusa(exc)
        return Response({"aceitos": quantidade})


class ImportacaoLancamentosEfetivarView(_AcaoSobreImportacaoView):
    def post(self, request, importacao_id, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_EFETIVAR_LANCAMENTOS)
        importacao = self._importacao(importacao_id)
        politica = (request.data.get("politica") or importacao_lancamentos.TUDO_OU_NADA).strip()
        try:
            resultado = importacao_lancamentos.efetivar(
                importacao, politica=politica, usuario=request.user, request=request
            )
        except (
            IntercambioRecusado,
            LancamentoInvalido,
            CompetenciaEncerrada,
            CompetenciaOperacaoRecusada,
        ) as exc:
            return _resposta_da_recusa(exc)
        return Response(
            {
                "efetivada": True,
                "criados": resultado.criados,
                "reaproveitados": resultado.reaproveitados,
                "nao_efetivados": resultado.nao_efetivados,
                "importacao": _importacao_como_dict(resultado.importacao),
            }
        )


class ImportacaoLancamentosDescartarView(_AcaoSobreImportacaoView):
    def post(self, request, importacao_id, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_DESCARTE_LANCAMENTOS)
        importacao = self._importacao(importacao_id)
        try:
            atual = importacao_lancamentos.descartar(
                importacao, motivo=request.data.get("motivo"), usuario=request.user, request=request
            )
        except IntercambioRecusado as exc:
            return _resposta_da_recusa(exc)
        return Response(_importacao_como_dict(atual))


class DeParaContaLancamentosView(EmpresaEscopadaContabilMixin, APIView):
    """De-para de código de origem para conta, por empresa e formato (GET lê, POST grava)."""

    permission_classes = [TemEscritorioAtivo]

    def get_permissions(self):
        permissions = [permission() for permission in self.permission_classes]
        if self.request.method == "POST":
            permissions.append(PodeEscriturar())
        else:
            permissions.append(PodeLerContabilidade())
        return permissions

    def get(self, request, *args, **kwargs):
        try:
            recusar_campos_nao_contratados(
                request.query_params, CAMPOS_QUERYSTRING_DEPARA, contexto="no de-para de contas"
            )
        except DadoNaoContratado as exc:
            raise DRFValidationError(exc.mensagem) from exc
        empresa = self.get_empresa()
        formato = (request.query_params.get("formato") or "").strip()
        depara = DeParaConta.objects.filter(empresa=empresa).select_related("conta")
        if formato:
            depara = depara.filter(formato=formato)
        return Response(
            {
                "de_para": [
                    {
                        "id": item.pk,
                        "formato": item.formato,
                        "codigo_origem": item.codigo_origem,
                        "conta_id": item.conta_id,
                        "conta_codigo": item.conta.codigo,
                        "conta_nome": item.conta.nome,
                    }
                    for item in depara
                ]
            }
        )

    def post(self, request, *args, **kwargs):
        _recusar_dado_nao_contratado(request, CONTRATO_POST_DEPARA_LANCAMENTOS)
        empresa = self.get_empresa()
        try:
            conta_id = int(request.data.get("conta"))
        except (TypeError, ValueError) as exc:
            raise DRFValidationError(
                {"conta": ["informe o identificador numérico da conta."]}
            ) from exc
        conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)
        try:
            depara = importacao_lancamentos.definir_de_para(
                empresa=empresa,
                formato=(request.data.get("formato") or "").strip(),
                codigo_origem=request.data.get("codigo_origem"),
                conta=conta,
                usuario=request.user,
                request=request,
            )
        except IntercambioRecusado as exc:
            return _resposta_da_recusa(exc)
        return Response(
            {
                "id": depara.pk,
                "formato": depara.formato,
                "codigo_origem": depara.codigo_origem,
                "conta_id": depara.conta_id,
                "conta_codigo": conta.codigo,
            }
        )
