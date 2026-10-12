"""API da classificação fiscal versionada — DL-087, corte 1 (frente A, API).

Rotas em `apps/fiscal/urls_api.py`, sob `fiscal/api/empresas/<empresa_id>/nfe/classificacao/`.

Autorização (AGENTS.md §11, no servidor, nunca só na tela):
- leitura (listar regras, fila, regras do produto): `PodeConsultarFiscal`, o mesmo de ler o fiscal;
- criar regra, prévia de impacto e desativar: quem tem a permissão do ESCOPO. Regra de EMPRESA:
  `papel_pode_escriturar_fiscal`. Regra de ESCRITÓRIO (vale para todos os clientes): só
  ADMINISTRADOR
  e GESTOR (`PAPEIS_QUE_GEREM_REGRA_DO_ESCRITORIO`, DL-087, HI-153). Recusa com 403.
- Desativar usa a permissão do escopo DA REGRA, não a do escopo pedido.

Isolamento: a empresa vem do escritório ativo (404 para outro escritório). Cada regra é buscada no
escritório ativo E na empresa da URL, ou regra do escritório: 404 para regra de outra empresa.

Entrada estranha responde 400 (contrato, texto, faixa de data), nunca 500. Conflito de duplicidade e
regra já desativada respondem 409.
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.requisicao import ContratoDeRequisicao
from apps.fiscal import classificacao
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.api import PodeConsultarFiscal, _ano_e_mes_da_consulta
from apps.fiscal.api_escrituracao_nfe import (
    _data_no_intervalo,
    _EmpresaComIdValido,
    _id_valido,
    _recusar_dado_nao_contratado,
    _resposta_de_conflito,
    _sem_caractere_invalido,
)
from apps.fiscal.models import (
    ModoNcmRegraNFe,
    NaturezaOperacaoNFe,
    RegraClassificacaoNFe,
    TipoRegraClassificacaoNFe,
)
from apps.fiscal.permissoes import papel_pode_escriturar_fiscal
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo

# DL-087 (HI-153, item 3): regra que vale para TODOS os clientes do escritório é parametrização
# global: só ADMINISTRADOR e GESTOR (a mesma composição que RC-102 dá ao fechamento). Hipótese até o
# Fred validar o HI-153.
PAPEIS_QUE_GEREM_REGRA_DO_ESCRITORIO = (Papel.ADMINISTRADOR, Papel.GESTOR)

MENSAGEM_SEM_PERMISSAO_ESCRITORIO = (
    "Só administrador e gestor criam ou desativam regra do escritório, que vale para todos os "
    "clientes."
)
MENSAGEM_SEM_PERMISSAO_EMPRESA = (
    "Papel sem permissão para criar ou desativar regra de classificação da empresa."
)

CONTRATO_CRIAR_REGRA = ContratoDeRequisicao(
    campos={
        "escopo",
        "tipo",
        "cfop",
        "ncm",
        "ncm_modo",
        "cst_csosn",
        "id_dest",
        "natureza",
        "vigencia_inicio",
        "vigencia_fim",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na criação de regra de classificação de NF-e",
)
CONTRATO_PREVIA_DE_IMPACTO = ContratoDeRequisicao(
    campos={
        "escopo",
        "tipo",
        "cfop",
        "ncm",
        "ncm_modo",
        "cst_csosn",
        "id_dest",
        "natureza",
        "vigencia_inicio",
        "vigencia_fim",
        "ano",
        "mes",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na prévia de impacto de regra de classificação de NF-e",
)
CONTRATO_DESATIVAR_REGRA = ContratoDeRequisicao(
    campos={"motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na desativação de regra de classificação de NF-e",
)

_ANO_MINIMO, _ANO_MAXIMO = 1970, 2999
_ESCOPOS = (classificacao.ESCOPO_EMPRESA, classificacao.ESCOPO_ESCRITORIO)
_SITUACOES = ("ativa", "desativada")
_TAMANHO_NCM = 10
_TAMANHO_CFOP = 5
_TAMANHO_CST = 3


def _papel_do_request(request):
    return getattr(request, "papel", None)


def _exigir_permissao_para_o_escopo(request, escopo: str) -> None:
    """403 quando o papel não pode mexer em regra deste escopo. Decisão no servidor."""
    papel = _papel_do_request(request)
    if escopo == classificacao.ESCOPO_ESCRITORIO:
        if papel not in PAPEIS_QUE_GEREM_REGRA_DO_ESCRITORIO:
            raise PermissionDenied(MENSAGEM_SEM_PERMISSAO_ESCRITORIO)
        return
    if not papel_pode_escriturar_fiscal(papel):
        raise PermissionDenied(MENSAGEM_SEM_PERMISSAO_EMPRESA)


def _pode(request, escopo: str) -> bool:
    try:
        _exigir_permissao_para_o_escopo(request, escopo)
    except PermissionDenied:
        return False
    return True


class _CriterioEntradaSerializer(serializers.Serializer):
    """Critérios e resultado de uma regra. Texto e data passam pelas mesmas barreiras da
    escrituração."""

    tipo = serializers.CharField(max_length=16, validators=[_sem_caractere_invalido])
    cfop = serializers.CharField(
        max_length=_TAMANHO_CFOP, allow_blank=True, validators=[_sem_caractere_invalido]
    )
    ncm = serializers.CharField(
        max_length=_TAMANHO_NCM,
        required=False,
        allow_blank=True,
        allow_null=True,
        validators=[_sem_caractere_invalido],
    )
    ncm_modo = serializers.CharField(
        max_length=8, required=False, allow_blank=True, allow_null=True
    )
    cst_csosn = serializers.CharField(
        max_length=_TAMANHO_CST,
        required=False,
        allow_blank=True,
        allow_null=True,
        validators=[_sem_caractere_invalido],
    )
    id_dest = serializers.CharField(max_length=1, required=False, allow_blank=True, allow_null=True)
    natureza = serializers.CharField(max_length=29, validators=[_sem_caractere_invalido])
    vigencia_inicio = serializers.DateField()
    vigencia_fim = serializers.DateField(required=False, allow_null=True)

    def validate_vigencia_inicio(self, valor):
        return _data_no_intervalo(valor)

    def validate_vigencia_fim(self, valor):
        return _data_no_intervalo(valor)


class CriarRegraEntradaSerializer(_CriterioEntradaSerializer):
    escopo = serializers.ChoiceField(choices=_ESCOPOS)


class PrevisaoEntradaSerializer(_CriterioEntradaSerializer):
    escopo = serializers.ChoiceField(choices=_ESCOPOS)
    ano = serializers.IntegerField(min_value=_ANO_MINIMO, max_value=_ANO_MAXIMO)
    mes = serializers.IntegerField(min_value=1, max_value=12)


class DesativarEntradaSerializer(serializers.Serializer):
    motivo = serializers.CharField(
        max_length=servico.MOTIVO_MAXIMO, allow_blank=True, validators=[_sem_caractere_invalido]
    )


def _dados_da_entrada(entrada: dict) -> classificacao.DadosDaRegra:
    """Converte o JSON validado em `DadosDaRegra`. A validação de conteúdo é do serviço (400)."""
    return classificacao.DadosDaRegra(
        tipo=entrada.get("tipo") or "",
        cfop=entrada.get("cfop") or "",
        natureza=entrada.get("natureza") or "",
        vigencia_inicio=entrada["vigencia_inicio"],
        vigencia_fim=entrada.get("vigencia_fim"),
        ncm=entrada.get("ncm") or "",
        ncm_modo=entrada.get("ncm_modo") or "",
        cst_csosn=entrada.get("cst_csosn") or "",
        id_dest=entrada.get("id_dest") or "",
    )


def _iso(valor):
    return None if valor is None else valor.isoformat()


def _regra_payload(regra: RegraClassificacaoNFe) -> dict:
    total = getattr(regra, "total_confirmados", None)
    return {
        "id": regra.pk,
        "escopo": classificacao.ESCOPO_EMPRESA
        if regra.empresa_id
        else classificacao.ESCOPO_ESCRITORIO,
        "empresa_id": regra.empresa_id,
        "tipo": regra.tipo,
        "cfop": regra.cfop,
        "ncm": regra.ncm or None,
        "ncm_modo": regra.ncm_modo or None,
        "cst_csosn": regra.cst_csosn or None,
        "id_dest": regra.id_dest or None,
        "natureza": regra.natureza,
        "natureza_rotulo": NaturezaOperacaoNFe(regra.natureza).label,
        "vigencia_inicio": _iso(regra.vigencia_inicio),
        "vigencia_fim": _iso(regra.vigencia_fim),
        "ativa": regra.ativa,
        "criada_em": regra.criada_em.isoformat() if regra.criada_em else None,
        "criada_por_id": regra.criada_por_id,
        "desativada_em": regra.desativada_em.isoformat() if regra.desativada_em else None,
        "desativada_por_id": regra.desativada_por_id,
        "motivo_desativacao": regra.motivo_desativacao or None,
        # DL-087, item 6: quantos itens confirmados vieram desta regra (inclusive já efetivados).
        "itens_confirmados": total,
    }


def _regra_da_empresa_ou_404(request, empresa, regra_id: int) -> RegraClassificacaoNFe:
    """Regra do escritório ativo que vale para a empresa da URL. Outra empresa: 404."""
    _id_valido(regra_id)
    consulta = RegraClassificacaoNFe.objects.filter(escritorio=request.escritorio).filter(
        Q(empresa__isnull=True) | Q(empresa=empresa)
    )
    return get_object_or_404(consulta, pk=regra_id)


class RegrasDaEmpresaView(_EmpresaComIdValido, APIView):
    """GET — regras que valem para a empresa (do escritório e as dela). POST — cria uma regra."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        escopo = request.query_params.get("escopo") or None
        situacao = request.query_params.get("situacao") or None
        if escopo is not None and escopo not in _ESCOPOS:
            raise DRFValidationError("'escopo' deve ser empresa ou escritorio.")
        if situacao is not None and situacao not in _SITUACOES:
            raise DRFValidationError("'situacao' deve ser ativa ou desativada.")
        regras = classificacao.regras_da_empresa(
            empresa, escopo=escopo, situacao=situacao
        ).annotate(total_confirmados=Count("itens_confirmados"))
        return Response(
            {
                "regras": [_regra_payload(regra) for regra in regras],
                "pesos": classificacao.PESOS_DE_ESPECIFICIDADE,
                "ordem_de_precedencia": [
                    "maior especificidade (somam-se os pesos publicados: CFOP, NCM exato ou "
                    "prefixo, CST/CSOSN e idDest; pesos em potência de dois)",
                    "prefixo de NCM mais longo",
                    "escopo empresa sobre escritório",
                    "mesma natureza não é conflito; natureza diferente é conflito (sem sugestão)",
                ],
                "pode_criar_regra_de_empresa": _pode(request, classificacao.ESCOPO_EMPRESA),
                "pode_criar_regra_de_escritorio": _pode(request, classificacao.ESCOPO_ESCRITORIO),
            }
        )

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_CRIAR_REGRA)
        empresa = self.get_empresa()
        entrada = CriarRegraEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        escopo = entrada.validated_data["escopo"]
        # 403 antes de qualquer validação de conteúdo: quem não pode criar não aprende nada das
        # regras.
        _exigir_permissao_para_o_escopo(request, escopo)
        try:
            dados = classificacao.validar_dados_da_regra(_dados_da_entrada(entrada.validated_data))
            avisos = classificacao.avisos_da_regra(dados, escopo)
            regra = classificacao.criar_regra(
                escritorio=request.escritorio,
                empresa=empresa if escopo == classificacao.ESCOPO_EMPRESA else None,
                dados=dados,
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoNFeErro as exc:
            return _resposta_de_conflito(exc)
        return Response(
            {"regra": _regra_payload(regra), "avisos": list(avisos)},
            status=status.HTTP_201_CREATED,
        )


class RegraDesativarView(_EmpresaComIdValido, APIView):
    """POST — desativa a regra: fixa o fim da vigência (ontem) e grava quem, quando e o motivo."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def post(self, request, empresa_id, regra_id):
        _recusar_dado_nao_contratado(request, CONTRATO_DESATIVAR_REGRA)
        empresa = self.get_empresa()
        regra = _regra_da_empresa_ou_404(request, empresa, regra_id)
        _exigir_permissao_para_o_escopo(
            request,
            classificacao.ESCOPO_EMPRESA if regra.empresa_id else classificacao.ESCOPO_ESCRITORIO,
        )
        entrada = DesativarEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            desativada = classificacao.desativar_regra(
                regra,
                motivo=entrada.validated_data["motivo"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoNFeErro as exc:
            return _resposta_de_conflito(exc)
        return Response({"regra": _regra_payload(desativada)})


class PrevisaoDeImpactoView(_EmpresaComIdValido, APIView):
    """POST — prévia de impacto de uma regra AINDA NÃO salva. Não grava nada (DL-087, item 7)."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_PREVIA_DE_IMPACTO)
        empresa = self.get_empresa()
        entrada = PrevisaoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        escopo = entrada.validated_data["escopo"]
        _exigir_permissao_para_o_escopo(request, escopo)
        dados = _dados_da_entrada(entrada.validated_data)
        try:
            previa = classificacao.previa_de_impacto(
                empresa,
                entrada.validated_data["ano"],
                entrada.validated_data["mes"],
                dados,
                escopo,
            )
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        return Response(
            {
                "ano": previa.ano,
                "mes": previa.mes,
                "escopo": previa.escopo,
                "itens_a_escriturar": previa.itens_a_escriturar,
                "itens_que_mudam": previa.itens_que_mudam,
                "itens_que_saem_da_fila": previa.itens_que_saem_da_fila,
                "itens_que_entram_na_fila": previa.itens_que_entram_na_fila,
                "grupos_afetados": previa.grupos_afetados,
                "notas_afetadas": previa.notas_afetadas,
                "avisos": list(previa.avisos),
            }
        )


class FilaAClassificarView(_EmpresaComIdValido, APIView):
    """GET — itens sem sugestão ou em conflito, agrupados, com os critérios para criar a regra."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        fila = classificacao.fila_a_classificar(empresa, ano, mes)
        pode_empresa = _pode(request, classificacao.ESCOPO_EMPRESA)
        pode_escritorio = _pode(request, classificacao.ESCOPO_ESCRITORIO)
        return Response(
            {
                "ano": fila.ano,
                "mes": fila.mes,
                "quantidade_notas": fila.quantidade_notas,
                "quantidade_itens": fila.quantidade_itens,
                "valor": format(fila.valor, "f"),
                "notas_sem_leitura": fila.notas_sem_leitura,
                "mes_confirmado": fila.mes_confirmado,
                "aviso_do_mes": fila.aviso_do_mes or None,
                "grupos": [
                    {
                        "chave": grupo.chave,
                        "tipo": grupo.tipo,
                        "cfop": grupo.cfop,
                        "ncm": grupo.ncm or None,
                        "cst_csosn": grupo.cst_csosn or None,
                        "id_dest": grupo.id_dest or None,
                        "motivo": grupo.motivo,
                        "situacao": grupo.situacao,
                        "notas": grupo.notas,
                        "itens": grupo.itens,
                        "valor": format(grupo.valor, "f"),
                        "criavel": grupo.criavel,
                        "motivo_nao_criavel": grupo.motivo_nao_criavel or None,
                        "criterios_da_regra": grupo.criterios_da_regra,
                        # Acionável para quem está logado: o escopo da regra que o grupo sugere.
                        "pode_criar_regra_de_empresa": grupo.criavel and pode_empresa,
                        "pode_criar_regra_de_escritorio": grupo.criavel and pode_escritorio,
                    }
                    for grupo in fila.grupos
                ],
            }
        )


class RegrasDoProdutoView(_EmpresaComIdValido, APIView):
    """GET — a sugestão embutida, em palavras, com a fonte de cada linha. Só leitura (DL-087)."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        self.get_empresa()
        return Response(
            {
                "regras": [dict(linha) for linha in classificacao.REGRAS_DO_PRODUTO],
                "tipos_com_regra": sorted(TipoRegraClassificacaoNFe.values),
                "modos_de_ncm": sorted(ModoNcmRegraNFe.values),
            }
        )
