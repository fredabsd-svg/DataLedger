"""API da escrituração das NF-e de saída e da devolução — DL-081, frente A (item 8).

Rotas em `apps/fiscal/urls_api.py`, sob `fiscal/api/empresas/<empresa_id>/nfe/`. O padrão é o de
`apps.fiscal.api` (DL-072) e de `apps.fiscal.api_nfe` (DL-080).

Autorização (AGENTS.md §11, no servidor): leitura com `PodeConsultarFiscal` (todos menos CLIENTE:
PARALEGAL lê); escrita, estorno e reclassificação com `PodeEscriturarFiscal` (ADMINISTRADOR,
GESTOR, ANALISTA e FINANCEIRO, a mesma regra da NFS-e). CLIENTE recebe 403.

Isolamento em duas camadas: a empresa vem do escritório ATIVO (404 para outro escritório ou
empresa de outro escritório), e cada nota e escrituração é buscada PELA EMPRESA da URL (404 para
nota ou escrituração de outra empresa, mesmo do mesmo escritório: IDOR).

Entrada estranha responde 400, nunca 500 (lições da DL-079): byte nulo e caractere substituto
recusados antes do banco; número fora da faixa do banco (bigint) recusado; datas fora de
1970 a 2999 recusadas; campo fora do contrato recusado.
"""

import re
from datetime import date
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote_servico
from apps.fiscal.api import PodeConsultarFiscal, PodeEscriturarFiscal, _ano_e_mes_da_consulta
from apps.fiscal.cfop import cfop as consultar_cfop
from apps.fiscal.itens_nfe import receita_do_item
from apps.fiscal.models import (
    CATALOGO_NATUREZA_NFE,
    EscrituracaoNFe,
    ItemNFe,
    LeituraItensNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    TipoEscrituracaoNFe,
    VinculoNFeEmpresa,
)
from apps.tenancy.permissions import TemEscritorioAtivo

# Maior identificador que o banco aceita (BigAutoField). Acima disso, o PostgreSQL responde erro
# de faixa, e a API responderia 500. Recusa-se antes.
MAIOR_ID = 2**63 - 1
_ANO_MINIMO_DATA, _ANO_MAXIMO_DATA = 1970, 2999
# Reconferência da DL-083, R1: o limite vem do campo do modelo, nunca de um literal.
_TAMANHO_NATUREZA = NaturezaItemNFe._meta.get_field("natureza").max_length
_TAMANHO_MOTIVO = servico.MOTIVO_MAXIMO
_MAXIMO_ITENS_POR_PEDIDO = 5000

CONTRATO_CRIAR_RASCUNHO = ContratoDeRequisicao(
    campos={"vinculo_id"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na criação do rascunho de NF-e",
)
CONTRATO_NATUREZAS = ContratoDeRequisicao(
    campos={"natureza", "itens"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na definição da natureza dos itens",
)
CONTRATO_EFETIVAR = ContratoDeRequisicao(
    campos=frozenset(),
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na efetivação da escrituração de NF-e",
)
CONTRATO_ESTORNAR = ContratoDeRequisicao(
    campos={"motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da escrituração de NF-e",
)
CONTRATO_RECLASSIFICAR = ContratoDeRequisicao(
    campos={"natureza", "inicio", "fim", "cfop", "cst_csosn", "ncm"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reclassificação em massa",
)
# DL-085: a confirmação em bloco. A primeira chamada leva ano, mes, assinatura e escolhas; a
# continuação leva só lote_id (e, se quiser, a assinatura do lote, para conferir).
CONTRATO_CONFIRMAR_LOTE = ContratoDeRequisicao(
    campos={"ano", "mes", "assinatura", "escolhas", "lote_id", "limite"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na confirmação do lote de escrituração de NF-e",
)
# DL-085 (leitura em partes): lê o XML das notas do mês que ainda não têm leitura atual.
CONTRATO_LER_LOTE = ContratoDeRequisicao(
    campos={"ano", "mes", "limite"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na leitura em partes das notas do lote de escrituração de NF-e",
)


def _sem_caractere_invalido(valor: str) -> str:
    """Recusa byte nulo e substituto (surrogate) isolado. Ambos quebram o banco (500) se passam."""
    if "\x00" in valor:
        raise serializers.ValidationError("Texto com caractere inválido.")
    if any(0xD800 <= ord(caractere) <= 0xDFFF for caractere in valor):
        raise serializers.ValidationError("Texto com caractere inválido.")
    return valor


def _id_valido(valor) -> int:
    """Identificador dentro da faixa do banco. Fora dela, 400 (nunca erro de banco)."""
    if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= MAIOR_ID:
        raise DRFValidationError("Identificador fora da faixa aceita.")
    return valor


def _data_no_intervalo(valor: date | None) -> date | None:
    if valor is not None and not _ANO_MINIMO_DATA <= valor.year <= _ANO_MAXIMO_DATA:
        raise serializers.ValidationError(
            f"Data fora do intervalo aceito ({_ANO_MINIMO_DATA} a {_ANO_MAXIMO_DATA})."
        )
    return valor


class _EmpresaComIdValido(EmpresaEscopadaMixin):
    """A empresa da URL, com o identificador conferido antes do banco (400, não 500)."""

    def get_empresa(self):
        _id_valido(self.kwargs["empresa_id"])
        return super().get_empresa()


def _recusar_dado_nao_contratado(request, contrato):
    try:
        recusar_dado_nao_contratado(request, contrato)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _resposta_de_conflito(exc: servico.EscrituracaoNFeErro) -> Response:
    # 409: o estado atual não permite a operação. Nada foi gravado.
    return Response({"detail": exc.mensagem}, status=status.HTTP_409_CONFLICT)


# ---------------------------------------------------------------------------
# Serializers de entrada (tudo recusado antes do banco)
# ---------------------------------------------------------------------------


class CriarRascunhoEntradaSerializer(serializers.Serializer):
    vinculo_id = serializers.IntegerField(min_value=1, max_value=MAIOR_ID)


class NaturezasEntradaSerializer(serializers.Serializer):
    natureza = serializers.CharField(
        max_length=_TAMANHO_NATUREZA, validators=[_sem_caractere_invalido]
    )
    itens = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=MAIOR_ID),
        min_length=1,
        max_length=_MAXIMO_ITENS_POR_PEDIDO,
    )


class EstornarEntradaSerializer(serializers.Serializer):
    motivo = serializers.CharField(
        max_length=_TAMANHO_MOTIVO, allow_blank=True, validators=[_sem_caractere_invalido]
    )


class ReclassificarEntradaSerializer(serializers.Serializer):
    natureza = serializers.CharField(
        max_length=_TAMANHO_NATUREZA, validators=[_sem_caractere_invalido]
    )
    inicio = serializers.DateField(required=False, allow_null=True)
    fim = serializers.DateField(required=False, allow_null=True)
    cfop = serializers.CharField(
        max_length=5,
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[_sem_caractere_invalido],
    )
    cst_csosn = serializers.CharField(
        max_length=3,
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[_sem_caractere_invalido],
    )
    ncm = serializers.CharField(
        max_length=8,
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[_sem_caractere_invalido],
    )

    def validate_inicio(self, valor):
        return _data_no_intervalo(valor)

    def validate_fim(self, valor):
        return _data_no_intervalo(valor)

    def validate_cfop(self, valor):
        """CFOP com ou sem ponto ("5.102" ou "5102"). Vira os 4 dígitos, como a tela (A12).

        Antes, "5.102" não casava nada, em silêncio. Agora é normalizado, e o que não é CFOP
        de 4 dígitos é recusado com 400.
        """
        if valor is None:
            return None
        normalizado = valor.strip().replace(".", "")
        if not normalizado:
            return None
        if not re.fullmatch(r"[0-9]{4}", normalizado):
            raise serializers.ValidationError(
                "CFOP deve ter exatamente 4 dígitos (ex.: 5102 ou 5.102)."
            )
        return normalizado

    def validate(self, dados):
        inicio, fim = dados.get("inicio"), dados.get("fim")
        if inicio and fim and inicio > fim:
            raise serializers.ValidationError("'inicio' não pode ser posterior a 'fim'.")
        return dados


def _filtro_opcional(valor: str | None) -> str | None:
    """Filtro vazio é ausente. Texto presente segue como veio (sem espaço nas pontas)."""
    if valor is None:
        return None
    limpo = valor.strip()
    return limpo or None


# ---------------------------------------------------------------------------
# Payloads de saída
# ---------------------------------------------------------------------------


def _decimal(valor):
    return None if valor is None else format(valor, "f")


def _iso(valor):
    return None if valor is None else valor.isoformat()


def _avisos_payload(avisos) -> list[dict]:
    return [
        {"codigo": a.codigo, "mensagem": a.mensagem, "dispositivo": a.dispositivo} for a in avisos
    ]


def _nota_payload(nota: servico.NotaDoMes) -> dict:
    documento = nota.documento
    return {
        "vinculo_id": nota.vinculo.pk,
        "documento_id": documento.pk,
        "papel": nota.vinculo.papel,
        "tipo": nota.tipo,
        "situacao": nota.situacao,
        "pendente": nota.situacao in (servico.SITUACAO_A_ESCRITURAR, servico.SITUACAO_RASCUNHO),
        "escrituracao_id": nota.escrituracao.pk if nota.escrituracao else None,
        "modelo": documento.modelo,
        "chave": documento.chave,
        "serie": documento.serie,
        "numero": documento.numero,
        "dh_emissao": _iso(documento.dh_emissao),
        "valor_nf": _decimal(documento.v_nf),
        "leitura": nota.leitura_estado,
        "leitura_motivo": nota.leitura_motivo or None,
        "avisos": _avisos_payload(servico.avisos_ibscbs(documento, nota.leitura)),
    }


def _item_payload(
    natureza: NaturezaItemNFe,
    sugestao: servico.Sugestao,
    avisos: tuple[str, ...],
    receita_atribuida: Decimal | None,
) -> dict:
    item: ItemNFe = natureza.item
    return {
        "item_id": item.pk,
        "n_item": item.n_item,
        "c_prod": item.c_prod,
        "x_prod": item.x_prod,
        "ncm": item.ncm,
        "cest": item.cest or None,
        "cfop": item.cfop,
        "cfop_na_tabela_oficial": consultar_cfop(item.cfop) is not None,
        "cst": item.cst,
        "csosn": item.csosn,
        "ind_tot": item.ind_tot,
        "v_prod": _decimal(item.v_prod),
        # `receita_bruta_item` é o VALOR BRUTO do item, não a receita (DL-083). A receita é
        # `receita_do_item`: a regra única, com indTot e vICMSDeson. `avisos` diz o que a receita
        # deixou de fora, em pt-BR.
        "receita_bruta_item": _decimal(item.receita_bruta_item),
        "receita_do_item": _decimal(receita_do_item(item)),
        # HI-138: a receita que a conta usa, com a parcela do resíduo de item que não é receita. É
        # `None` quando a atribuição da nota recusa (a efetivação recusa com a mensagem nomeada).
        "receita_atribuida": _decimal(receita_atribuida),
        "avisos": list(avisos),
        "natureza": natureza.natureza or None,
        "sugestao": {"natureza": sugestao.natureza, "motivo": sugestao.motivo},
    }


def _escrituracao_payload(escrituracao: EscrituracaoNFe) -> dict:
    return {
        "id": escrituracao.pk,
        "vinculo_id": escrituracao.vinculo_id,
        "tipo": escrituracao.tipo,
        "estado": escrituracao.estado,
        "competencia": _iso(escrituracao.competencia),
        "data_emissao": _iso(escrituracao.data_emissao),
        "valor_nf": _decimal(escrituracao.valor_nf),
        "soma_itens": _decimal(escrituracao.soma_itens),
        "receita_bruta": _decimal(escrituracao.receita_bruta),
        "devolucao": _decimal(escrituracao.devolucao),
        "efetivada_em": _iso(escrituracao.efetivada_em),
        "estornada_em": _iso(escrituracao.estornada_em),
        "motivo_estorno": escrituracao.motivo_estorno or None,
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class EscrituracaoNFeListaView(_EmpresaComIdValido, APIView):
    """GET — notas do mês com a situação de escrituração. POST — cria o rascunho de uma nota."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [TemEscritorioAtivo(), PodeEscriturarFiscal()]
        return [TemEscritorioAtivo(), PodeConsultarFiscal()]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        notas = servico.notas_do_mes(empresa, ano, mes)
        elegiveis = [_nota_payload(n) for n in notas if n.tipo is not None]
        return Response(
            {
                "ano": ano,
                "mes": mes,
                "notas": elegiveis,
                "fora_da_escrituracao": sum(1 for n in notas if n.tipo is None),
            }
        )

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_CRIAR_RASCUNHO)
        empresa = self.get_empresa()
        entrada = CriarRascunhoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        vinculo = get_object_or_404(
            VinculoNFeEmpresa.objects.select_related("documento"),
            pk=entrada.validated_data["vinculo_id"],
            empresa=empresa,
            documento__escritorio=request.escritorio,
        )
        try:
            escrituracao = servico.criar_rascunho(vinculo, usuario=request.user, request=request)
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoNFeErro as exc:
            return _resposta_de_conflito(exc)
        codigo = status.HTTP_201_CREATED if escrituracao.criada_agora else status.HTTP_200_OK
        return Response(_escrituracao_payload(escrituracao), status=codigo)


class EscrituracaoNFeDetalheView(_EmpresaComIdValido, APIView):
    """GET — uma escrituração: totais, itens com natureza e sugestão, e avisos de IBS/CBS."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id, escrituracao_id):
        empresa = self.get_empresa()
        _id_valido(escrituracao_id)
        escrituracao = get_object_or_404(
            EscrituracaoNFe.objects.select_related("vinculo__documento"),
            pk=escrituracao_id,
            empresa=empresa,
        )
        documento = escrituracao.vinculo.documento
        leitura = LeituraItensNFe.objects.filter(documento=documento).first()
        itens = []
        if leitura is not None and leitura.estado == LeituraItensNFe.ESTADO_LIDA:
            naturezas = list(
                NaturezaItemNFe.objects.select_related("item")
                .filter(escrituracao=escrituracao)
                .order_by("item__n_item")
            )
            pares = [(n.item, n.natureza) for n in naturezas]
            avisos_por_item = servico.avisos_da_nota(pares)
            receitas = servico.receitas_atribuidas(pares)
            for natureza in naturezas:
                sugestao = servico.sugerir_natureza_item(
                    documento, natureza.item, escrituracao.tipo
                )
                itens.append(
                    _item_payload(
                        natureza,
                        sugestao,
                        avisos_por_item.get(natureza.item_id, ()),
                        None if receitas is None else receitas.get(natureza.item_id),
                    )
                )
        payload = _escrituracao_payload(escrituracao)
        payload.update(
            {
                "modelo": documento.modelo,
                "chave": documento.chave,
                "numero": documento.numero,
                "serie": documento.serie,
                "dh_emissao": _iso(documento.dh_emissao),
                "naturezas_permitidas": sorted(servico.naturezas_permitidas(escrituracao.tipo)),
                "segregacao": {
                    chave: _decimal(valor)
                    for chave, valor in servico.segregacao_da_escrituracao(escrituracao).items()
                },
                "leitura": leitura.estado if leitura else None,
                "leitura_motivo": (leitura.motivo or None) if leitura else None,
                "itens": itens,
                "avisos": _avisos_payload(servico.avisos_ibscbs(documento, leitura)),
                # A8: a tela desabilita "Efetivar" com este motivo (regra de data, hoje 2027).
                # O servidor recusa de novo no POST.
                "motivo_bloqueio_efetivacao": servico.motivo_bloqueio_efetivacao(documento),
                "catalogo": {
                    codigo: {
                        "rotulo": NaturezaOperacaoNFe(codigo).label,
                        "papel": CATALOGO_NATUREZA_NFE[codigo].papel,
                        "mercado": CATALOGO_NATUREZA_NFE[codigo].mercado,
                    }
                    for codigo in sorted(servico.naturezas_permitidas(escrituracao.tipo))
                },
            }
        )
        return Response(payload)


class DefinirNaturezasView(_EmpresaComIdValido, APIView):
    """POST — confirma a natureza de um ou de vários itens da escrituração (só rascunho)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, escrituracao_id):
        _recusar_dado_nao_contratado(request, CONTRATO_NATUREZAS)
        empresa = self.get_empresa()
        _id_valido(escrituracao_id)
        escrituracao = get_object_or_404(EscrituracaoNFe, pk=escrituracao_id, empresa=empresa)
        entrada = NaturezasEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            atualizada = servico.definir_natureza(
                escrituracao,
                entrada.validated_data["natureza"],
                entrada.validated_data["itens"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoNFeErro as exc:
            return _resposta_de_conflito(exc)
        return Response(_escrituracao_payload(atualizada), status=status.HTTP_200_OK)


class EfetivarEscrituracaoNFeView(_EmpresaComIdValido, APIView):
    """POST — efetiva a escrituração. 201 quando efetiva agora; 200 se já estava efetivada."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, escrituracao_id):
        _recusar_dado_nao_contratado(request, CONTRATO_EFETIVAR)
        empresa = self.get_empresa()
        _id_valido(escrituracao_id)
        escrituracao = get_object_or_404(EscrituracaoNFe, pk=escrituracao_id, empresa=empresa)
        try:
            efetivada = servico.efetivar(escrituracao, usuario=request.user, request=request)
        except servico.EscrituracaoNFeErro as exc:
            return _resposta_de_conflito(exc)
        codigo = status.HTTP_201_CREATED if efetivada.criada_agora else status.HTTP_200_OK
        return Response(_escrituracao_payload(efetivada), status=codigo)


class EstornarEscrituracaoNFeView(_EmpresaComIdValido, APIView):
    """POST — estorna escrituração efetivada, com motivo obrigatório."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id, escrituracao_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ESTORNAR)
        empresa = self.get_empresa()
        _id_valido(escrituracao_id)
        escrituracao = get_object_or_404(EscrituracaoNFe, pk=escrituracao_id, empresa=empresa)
        entrada = EstornarEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            estornada = servico.estornar(
                escrituracao,
                entrada.validated_data["motivo"],
                usuario=request.user,
                request=request,
            )
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoNFeErro as exc:
            return _resposta_de_conflito(exc)
        return Response(_escrituracao_payload(estornada), status=status.HTTP_200_OK)


class ReclassificarNFeView(_EmpresaComIdValido, APIView):
    """POST — troca a natureza dos itens que casam com os filtros (só em rascunho, item 7)."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_RECLASSIFICAR)
        empresa = self.get_empresa()
        entrada = ReclassificarEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        filtros = servico.FiltrosReclassificacao(
            inicio=dados.get("inicio"),
            fim=dados.get("fim"),
            cfop=_filtro_opcional(dados.get("cfop")),
            cst_csosn=_filtro_opcional(dados.get("cst_csosn")),
            ncm=_filtro_opcional(dados.get("ncm")),
        )
        try:
            resultado = servico.reclassificar_em_massa(
                empresa, dados["natureza"], filtros, usuario=request.user, request=request
            )
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        return Response(
            {
                "natureza": resultado.natureza,
                "escrituracoes_afetadas": resultado.escrituracoes_afetadas,
                "itens_alterados": resultado.itens_alterados,
            }
        )


class ConferenciaNFeView(_EmpresaComIdValido, APIView):
    """GET — conferência do mês: receita por natureza e CFOP, e a contagem de notas."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        conferencia = servico.conferencia_do_mes(empresa, ano, mes)
        return Response(
            {
                "ano": ano,
                "mes": mes,
                "recebidas": conferencia.recebidas,
                "escrituradas": conferencia.escrituradas,
                "pendentes": conferencia.pendentes,
                "canceladas": conferencia.canceladas,
                "escrituradas_canceladas": conferencia.escrituradas_canceladas,
                "nao_elegiveis": conferencia.nao_elegiveis,
                "itens_sem_sugestao": conferencia.itens_sem_sugestao,
                "receita_por_natureza": {
                    natureza: {
                        "papel": linha["papel"],
                        "mercado": linha["mercado"],
                        "bruto": _decimal(linha["bruto"]),
                        "soma_na_receita": _decimal(linha["soma_na_receita"]),
                    }
                    for natureza, linha in sorted(conferencia.receita_por_natureza.items())
                },
                # Valor BRUTO por CFOP: inclui o que não é receita, como a tela rotula (A12).
                "valor_bruto_por_cfop": {
                    cfop: _decimal(valor)
                    for cfop, valor in sorted(conferencia.valor_bruto_por_cfop.items())
                },
            }
        )


# ---------------------------------------------------------------------------
# DL-085 (frente A): prévia do mês em lote e confirmação em bloco, em partes
# ---------------------------------------------------------------------------


class TrocaDeGrupoEntradaSerializer(serializers.Serializer):
    """Uma escolha de natureza por grupo: {id da assinatura: natureza}. Validada no serviço."""

    grupo = serializers.CharField(max_length=40, validators=[_sem_caractere_invalido])
    naturezas = serializers.DictField(
        child=serializers.CharField(
            max_length=_TAMANHO_NATUREZA, validators=[_sem_caractere_invalido]
        ),
    )

    def validate_naturezas(self, valor):
        # Chaves são ids de assinatura (CFOP|CST|natureza): curtas. Acima disso, é entrada hostil.
        if len(valor) > _MAXIMO_ITENS_POR_PEDIDO:
            raise serializers.ValidationError("Escolhas demais em um grupo.")
        for chave in valor:
            if len(chave) > 100:
                raise serializers.ValidationError("Identificador de assinatura longo demais.")
            _sem_caractere_invalido(chave)
        return valor


class ConfirmarLoteEntradaSerializer(serializers.Serializer):
    ano = serializers.IntegerField(
        required=False, allow_null=True, min_value=_ANO_MINIMO_DATA, max_value=_ANO_MAXIMO_DATA
    )
    mes = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=12)
    assinatura = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=64,
        validators=[_sem_caractere_invalido],
    )
    escolhas = TrocaDeGrupoEntradaSerializer(many=True, required=False, allow_null=True)
    lote_id = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=MAIOR_ID
    )
    limite = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=lote_servico.LIMITE_MAXIMO_DA_PARTE
    )


def _escolhas_como_dicionario(trocas) -> dict[str, dict[str, str]]:
    """Lista de escolhas do corpo → {grupo: {id: natureza}}. Grupo repetido é 400."""
    resultado: dict[str, dict[str, str]] = {}
    for troca in trocas or []:
        grupo = troca["grupo"]
        if grupo in resultado:
            raise DRFValidationError("Grupo repetido nas escolhas: informe cada grupo uma vez.")
        resultado[grupo] = dict(troca["naturezas"])
    return resultado


def _previa_payload(previa: lote_servico.PreviaDoLote) -> dict:
    por_motivo: dict[str, int] = {}
    for recusa in previa.fora:
        por_motivo[recusa.codigo] = por_motivo.get(recusa.codigo, 0) + 1
    return {
        "ano": previa.ano,
        "mes": previa.mes,
        "assinatura": previa.assinatura,
        "grupos": [
            {
                "chave": grupo.chave,
                "tipo": grupo.tipo,
                "rotulo_tipo": TipoEscrituracaoNFe(grupo.tipo).label,
                "notas": grupo.quantidade_notas,
                "itens": grupo.quantidade_itens,
                "receita_bruta": _decimal(grupo.receita_bruta),
                "devolucao": _decimal(grupo.devolucao),
                "assinaturas": [
                    {
                        "id": a.id,
                        "cfop": a.cfop,
                        "cst_csosn": a.cst_csosn or None,
                        "natureza_sugerida": a.natureza,
                        "rotulo_natureza": NaturezaOperacaoNFe(a.natureza).label,
                    }
                    for a in grupo.assinaturas
                ],
                # As naturezas que a troca de grupo aceita: as do tipo, pelo catálogo.
                "naturezas_permitidas": [
                    {"natureza": n, "rotulo": NaturezaOperacaoNFe(n).label}
                    for n in sorted(servico.naturezas_permitidas(grupo.tipo))
                ],
            }
            for grupo in previa.grupos
        ],
        "fora_do_lote": {
            "total": len(previa.fora),
            "por_motivo": dict(sorted(por_motivo.items())),
            "notas": [
                {
                    "vinculo_id": recusa.vinculo_id,
                    "documento_id": recusa.documento_id,
                    "numero": recusa.numero,
                    "serie": recusa.serie,
                    "dh_emissao": _iso(recusa.dh_emissao),
                    "codigo": recusa.codigo,
                    "motivo": recusa.motivo,
                }
                for recusa in previa.fora
            ],
        },
        # "a ler": notas do mês sem leitura atual. A prévia não as lê, e elas não entram em grupo
        # nem em "fora do lote". Antes de confirmar, o contador lê estas notas (POST .../lote/ler/).
        "a_ler": {"notas": len(previa.a_ler)},
        "ja_efetivadas": previa.ja_efetivadas,
        "canceladas": previa.canceladas,
        "nao_elegiveis": previa.nao_elegiveis,
        "lote_em_andamento": (
            lote_servico.resumo_do_lote(previa.lote_em_andamento)
            if previa.lote_em_andamento is not None
            else None
        ),
    }


def _progresso_payload(progresso: lote_servico.ProgressoDoLote) -> dict:
    return {
        "lote_id": progresso.lote_id,
        "ano": progresso.ano,
        "mes": progresso.mes,
        "assinatura": progresso.assinatura,
        "estado": progresso.estado,
        "terminou": progresso.terminou,
        "total_notas": progresso.total_notas,
        "efetivadas_nesta_chamada": progresso.efetivadas_nesta_chamada,
        "ja_efetivadas_nesta_chamada": progresso.ja_efetivadas_nesta_chamada,
        "falhas_nesta_chamada": [
            {"vinculo_id": falha.vinculo_id, "motivo": falha.motivo}
            for falha in progresso.falhas_nesta_chamada
        ],
        "restantes": progresso.restantes,
        "efetivadas_total": progresso.efetivadas_total,
        "ja_efetivadas_total": progresso.ja_efetivadas_total,
        "falhas_total": progresso.falhas_total,
    }


class PreviaLoteNFeView(_EmpresaComIdValido, APIView):
    """GET — prévia do mês em lote: grupos (quantidades, receita, naturezas), notas fora do lote com
    o motivo, e a assinatura que a confirmação exige. Só lê (a primeira leitura de uma nota é a
    única escrita, documentada em `escrituracao_nfe_lote`)."""

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, mes = _ano_e_mes_da_consulta(request)
        try:
            previa = lote_servico.previa_do_lote(empresa, ano, mes)
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        return Response(_previa_payload(previa))


class ConfirmarLoteNFeView(_EmpresaComIdValido, APIView):
    """POST — confirma a prévia em bloco (1ª chamada: ano, mes, assinatura, escolhas) ou continua o
    lote (`lote_id`). Uma parte por chamada: 200 com o progresso; 409 se a assinatura não bate com a
    prévia de agora (nada é efetivado); 400 para entrada inválida; 404 lote de outra empresa."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_CONFIRMAR_LOTE)
        empresa = self.get_empresa()
        entrada = ConfirmarLoteEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        if dados.get("lote_id") is None and (dados.get("ano") is None or dados.get("mes") is None):
            raise DRFValidationError(
                "Informe 'ano' e 'mes' na primeira confirmação, ou 'lote_id' para continuar o lote."
            )
        try:
            progresso = lote_servico.confirmar_lote(
                empresa,
                dados.get("ano"),
                dados.get("mes"),
                dados.get("assinatura") or None,
                _escolhas_como_dicionario(dados.get("escolhas")),
                usuario=request.user,
                request=request,
                limite=dados.get("limite") or lote_servico.LIMITE_PADRAO_DA_PARTE,
                lote_id=dados.get("lote_id"),
            )
        except lote_servico.LoteNaoEncontrado as exc:
            raise NotFound("Lote de escrituração não encontrado nesta empresa.") from exc
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        except servico.EscrituracaoNFeErro as exc:
            return _resposta_de_conflito(exc)
        return Response(_progresso_payload(progresso), status=status.HTTP_200_OK)


class LerEntradaSerializer(serializers.Serializer):
    ano = serializers.IntegerField(min_value=_ANO_MINIMO_DATA, max_value=_ANO_MAXIMO_DATA)
    mes = serializers.IntegerField(min_value=1, max_value=12)
    limite = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=lote_servico.LIMITE_MAXIMO_DA_LEITURA,
    )


def _leitura_payload(leitura: lote_servico.LeituraDoMes) -> dict:
    return {
        "ano": leitura.ano,
        "mes": leitura.mes,
        "lidas_nesta_chamada": leitura.lidas_nesta_chamada,
        "ilegiveis_nesta_chamada": leitura.ilegiveis_nesta_chamada,
        "falhas_nesta_chamada": [
            {"vinculo_id": falha.vinculo_id, "motivo": falha.motivo}
            for falha in leitura.falhas_nesta_chamada
        ],
        "restam": leitura.restam,
        "terminou": leitura.terminou,
    }


class LerLoteNFeView(_EmpresaComIdValido, APIView):
    """POST — lê, em partes, o XML das notas do mês sem leitura atual (DL-085). 200 com "lidas X,
    restam Y". Só escrita de leitura: não cria escrituração, rascunho nem lote. Quem escritura pode;
    PARALEGAL e CLIENTE não."""

    permission_classes = [TemEscritorioAtivo, PodeEscriturarFiscal]

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_LER_LOTE)
        empresa = self.get_empresa()
        entrada = LerEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data
        try:
            leitura = lote_servico.ler_notas_do_mes(
                empresa,
                dados["ano"],
                dados["mes"],
                limite=dados.get("limite") or lote_servico.LIMITE_PADRAO_DA_LEITURA,
            )
        except servico.EntradaInvalidaNFe as exc:
            raise DRFValidationError(exc.mensagem) from exc
        return Response(_leitura_payload(leitura), status=status.HTTP_200_OK)
