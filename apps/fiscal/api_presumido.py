"""API do Lucro Presumido, IRPJ e CSLL — DL-079, frente A.

Rotas em `apps/fiscal/urls_api.py`, sob `fiscal/api/empresas/<empresa_id>/presumido/`. Toda a regra
fica em `apps.fiscal.presumido`; aqui há só autorização, isolamento, validação da entrada e tradução
de erro.

Autorização (AGENTS.md §11, verificada NO SERVIDOR, nunca só na tela):
- ler (GET): `papel_pode_consultar_documentos`. PARALEGAL lê; CLIENTE recebe 403.
- escrever (POST): `papel_pode_escriturar_fiscal`. PARALEGAL e CLIENTE recebem 403.
O papel vem de `request.papel`, resolvido pelo middleware no escritório ATIVO.

Isolamento: `EmpresaEscopadaMixin` responde 404 para empresa de outro escritório; cada registro é
buscado DENTRO da empresa, então um id de outra empresa do mesmo escritório também responde 404.

Entrada: ano e trimestre são validados aqui (400, nunca 500); campo fora do contrato do POST é 400
com o nome da chave (apps.core.requisicao). Valor monetário chega como TEXTO; float é recusado.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.permissoes import papel_pode_consultar_documentos, papel_pode_escriturar_fiscal
from apps.tenancy.permissions import TemEscritorioAtivo

_ANO_MINIMO, _ANO_MAXIMO = 1970, 2999
_CONTEXTO = "no presumido"


def _contrato(campos, contexto):
    return ContratoDeRequisicao(
        campos=set(campos),
        cabecalhos_ignorados=("Idempotency-Key",),
        contexto=contexto,
    )


CONTRATO_ATIVIDADE = _contrato(
    {"atividade", "inicio", "fim", "padrao", "requisitos_hospitalares_confirmados"},
    "no cadastro da atividade de presunção",
)
CONTRATO_ENCERRAR_ATIVIDADE = _contrato({"fim"}, "no encerramento da atividade")
CONTRATO_CRITERIO = _contrato({"ano", "criterio"}, "na definição do critério")
CONTRATO_RECEITA = _contrato(
    {"ano", "trimestre", "tipo", "atividade_id", "descricao", "valor", "suporte", "competencia"},
    "no lançamento da receita do trimestre",
)
CONTRATO_PARAMETROS = _contrato(
    {"forma_recolhimento", "padrao_combustivel"},
    "nos parâmetros da empresa no presumido",
)
CONTRATO_ENCERRAR_MEDIDA = _contrato(
    {"ano", "trimestre", "motivo"},
    "no encerramento da medida judicial",
)
CONTRATO_ESTORNO = _contrato({"motivo"}, "no estorno da receita")
CONTRATO_INTEGRAIS = _contrato({"ano", "trimestre", "observacao"}, "na declaração de integrais")
CONTRATO_RETENCAO = _contrato(
    {"escrituracao_id", "irrf_confirmado", "csll_confirmada", "motivo"},
    "na confirmação da retenção",
)
CONTRATO_MEDIDA = _contrato(
    {
        "tributo",
        "ano_inicial",
        "trimestre_inicial",
        "ano_final",
        "trimestre_final",
        "numero_processo",
        "orgao",
        "data_decisao",
        "deposito_judicial",
        "suporte",
    },
    "no cadastro da medida judicial",
)
CONTRATO_REVOGAR = _contrato({"motivo"}, "na revogação da medida")


class PermissaoPresumido(BasePermission):
    """Ler exige o mesmo papel da consulta fiscal; escrever exige o papel que escritura."""

    message = "Papel sem permissão para o presumido."

    def has_permission(self, request, view):
        papel = getattr(request, "papel", None)
        if request.method in SAFE_METHODS:
            return papel_pode_consultar_documentos(papel)
        return papel_pode_escriturar_fiscal(papel)


def _recusar_dado_nao_contratado(request, contrato):
    try:
        recusar_dado_nao_contratado(request, contrato)
    except DadoNaoContratado as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _corpo(request) -> dict:
    dados = request.data
    if not hasattr(dados, "get"):
        raise DRFValidationError("O corpo da requisição deve ser um objeto JSON.")
    return dados


def _inteiro(valor, nome: str) -> int:
    """Inteiro do contrato, com a regra do serviço (`inteiro_de_entrada`).

    `int(2026.0)` e `int(1.5)` não passam mais como inteiro (auditoria DL-079, A14).
    """
    try:
        return servico.inteiro_de_entrada(valor, f"'{nome}'")
    except servico.EntradaInvalidaPresumido as exc:
        raise DRFValidationError(exc.mensagem) from exc


def _ano_e_trimestre(request) -> tuple[int, int]:
    ano = _inteiro(request.query_params.get("ano"), "ano")
    trimestre = _inteiro(request.query_params.get("trimestre"), "trimestre")
    # A apuração só existe a partir da vigência da LC 224 (2026): ano anterior é entrada inválida.
    if not (tab.ANO_INICIAL_LC224 <= ano <= _ANO_MAXIMO):
        raise DRFValidationError(f"'ano' inválido: {ano}.")
    if trimestre not in (1, 2, 3, 4):
        raise DRFValidationError(f"'trimestre' inválido: {trimestre}. Use 1 a 4.")
    return ano, trimestre


def _traduzir(exc: servico.PresumidoErro):
    if isinstance(exc, servico.EntradaInvalidaPresumido):
        raise DRFValidationError(exc.mensagem) from exc
    if isinstance(exc, servico.NaoEncontradoPresumido):
        return Response({"detail": exc.mensagem}, status=status.HTTP_404_NOT_FOUND)
    return Response({"detail": exc.mensagem}, status=status.HTTP_409_CONFLICT)


def _dec(valor):
    return None if valor is None else str(valor)


def _iso(valor):
    return None if valor is None else valor.isoformat()


def _atividade_payload(atividade) -> dict:
    return {
        "id": atividade.pk,
        "atividade": atividade.atividade,
        "rotulo": atividade.get_atividade_display(),
        "inicio": _iso(atividade.inicio),
        "fim": _iso(atividade.fim),
        "padrao": atividade.padrao,
        "requisitos_hospitalares_confirmados": atividade.requisitos_hospitalares_confirmados,
        "aliquotas": {
            "irpj": str(tab.ATIVIDADES_POR_CODIGO[atividade.atividade].irpj),
            "csll": str(tab.ATIVIDADES_POR_CODIGO[atividade.atividade].csll),
        },
    }


def _receita_payload(receita) -> dict:
    return {
        "id": receita.pk,
        "ano": receita.ano,
        "trimestre": receita.trimestre,
        "tipo": receita.tipo,
        "atividade_id": receita.atividade_id,
        "descricao": receita.descricao,
        "valor": _dec(receita.valor),
        "suporte": receita.suporte,
        "competencia": receita.competencia,
        "estado": receita.estado,
        "motivo_estorno": receita.motivo_estorno,
        "estornada_em": receita.estornada_em.isoformat() if receita.estornada_em else None,
    }


def _encerramento_payload(medida) -> dict | None:
    """O encerramento da medida, se houver (DL-084, item 7). A trilha guarda o antes e o depois."""
    encerramento = next(iter(medida.encerramentos.all()), None)
    if encerramento is None:
        return None
    return {
        "ano": encerramento.ano,
        "trimestre": encerramento.trimestre,
        "motivo": encerramento.motivo,
        "encerrada_em": encerramento.encerrada_em.isoformat(),
    }


def _medida_payload(medida) -> dict:
    fim_efetivo = servico.fim_efetivo_da_medida(medida)
    return {
        "id": medida.pk,
        "tributo": medida.tributo,
        "ano_inicial": medida.ano_inicial,
        "trimestre_inicial": medida.trimestre_inicial,
        "ano_final": medida.ano_final,
        "trimestre_final": medida.trimestre_final,
        "numero_processo": medida.numero_processo,
        "orgao": medida.orgao,
        "data_decisao": _iso(medida.data_decisao),
        "deposito_judicial": medida.deposito_judicial,
        "suporte": medida.suporte,
        "ativa": medida.ativa,
        "revogada_em": medida.revogada_em.isoformat() if medida.revogada_em else None,
        "motivo_revogacao": medida.motivo_revogacao,
        # DL-084, item 7: o último trimestre que a medida cobre hoje, depois do encerramento.
        "fim_efetivo": (
            None if fim_efetivo is None else {"ano": fim_efetivo[0], "trimestre": fim_efetivo[1]}
        ),
        "encerramento": _encerramento_payload(medida),
    }


def _parcela_payload(parcela: calc.Parcela) -> dict:
    return {
        "numero": parcela.numero,
        "valor": _dec(parcela.valor),
        "vencimento": _iso(parcela.vencimento),
        # Sempre falso desde a DL-084 (item 1); o campo fica só para a tela atual não quebrar.
        "aviso_calendario": parcela.aviso_calendario,
        # DL-084, item 1: data civil de onde o vencimento antecipou por dia sem expediente bancário.
        "antecipada_de": _iso(parcela.antecipada_de),
        # DL-084, item 2: avisos do feriado local da praça nesta data. Não mudam a data.
        "avisos_locais": list(parcela.avisos_locais),
        "juros": parcela.juros,
    }


def _quotas_payload(opcoes: calc.OpcoesDeQuota) -> dict:
    return {
        "devido": _dec(opcoes.devido),
        "quota_unica": [_parcela_payload(p) for p in opcoes.quota_unica],
        "duas_quotas": (
            [_parcela_payload(p) for p in opcoes.duas_quotas]
            if opcoes.duas_quotas is not None
            else None
        ),
        "motivo_sem_duas_quotas": opcoes.motivo_sem_duas_quotas,
        "tres_quotas": (
            [_parcela_payload(p) for p in opcoes.tres_quotas]
            if opcoes.tres_quotas is not None
            else None
        ),
        "motivo_sem_tres_quotas": opcoes.motivo_sem_tres_quotas,
    }


def _linha_payload(linha: calc.LinhaAtividade) -> dict:
    return {
        "atividade": linha.atividade,
        "receita": _dec(linha.receita),
        "excedente": _dec(linha.excedente),
        "aliquota": str(linha.aliquota),
        "aliquota_acrescida": str(linha.aliquota_acrescida),
        "base_normal": _dec(linha.base_normal),
        "base_acrescida": _dec(linha.base_acrescida),
    }


def _tributo_payload(colunas: servico.ColunasTributo) -> dict:
    return {
        "tributo": colunas.tributo,
        "codigo_darf": tab.CODIGO_DARF[colunas.tributo],
        "acrescimo_aplicavel": colunas.acrescimo_aplicavel,
        "receita_presumida": _dec(colunas.receita_presumida),
        "receitas_integrais": _dec(colunas.receitas_integrais),
        "base_sem_lc224": _dec(colunas.base_sem_lc224),
        "base_com_lc224": _dec(colunas.base_com_lc224),
        "imposto_sem_lc224": _dec(colunas.imposto_sem_lc224),
        "imposto_com_lc224": _dec(colunas.imposto_com_lc224),
        "parcela_lc224": _dec(colunas.parcela_lc224),
        "adicional_com_lc224": _dec(colunas.adicional_com_lc224),
        "memoria_com_lc224": [_linha_payload(linha) for linha in colunas.memoria_com_lc224],
        "memoria_sem_lc224": [_linha_payload(linha) for linha in colunas.memoria_sem_lc224],
        "caso_quarto_trimestre": colunas.caso_quarto,
        "deducao_quarto_trimestre": _dec(colunas.deducao_quarto_trimestre),
        "saldo_per_dcomp": _dec(colunas.saldo_per_dcomp),
        "retencao_confirmada": _dec(colunas.retencao_confirmada),
        "coluna_escolhida": colunas.coluna_escolhida,
        "medida": colunas.medida,
        "valor_suspenso": _dec(colunas.valor_suspenso),
        "tributo_escolhido": _dec(colunas.tributo_escolhido),
        "a_recolher": _dec(colunas.a_recolher),
        "saldo_negativo": _dec(colunas.saldo_negativo),
        "quotas": _quotas_payload(colunas.quotas),
    }


def _composicao_do_fechamento(linhas) -> list[dict]:
    """O que cada trimestre com acréscimo contribui para a dedução do 4º (A6). Trimestre com medida
    aparece com `suspensa_por_medida` true: a parcela dele fica fora da dedução (DL-079, item 0)."""
    return [
        {
            "trimestre": linha.trimestre,
            "diferenca_recalculo": _dec(linha.diferenca_recalculo),
            "suspensa_por_medida": linha.suspensa_por_medida,
        }
        for linha in linhas
        if linha.em_acrescimo
    ]


def _fechamento_payload(fechamento: calc.Fechamento | None, linhas=()):
    if fechamento is None:
        return None
    return {
        "n": fechamento.n,
        "receita_no_acrescimo": _dec(fechamento.receita_no_acrescimo),
        "limite_anual": _dec(fechamento.limite_anual),
        "excedente_anual_bruto": _dec(fechamento.excedente_anual_bruto),
        "excedente_anual": _dec(fechamento.excedente_anual),
        "s": _dec(fechamento.s),
        "caso": fechamento.caso,
        "trimestres": _composicao_do_fechamento(linhas),
    }


def _linha_nfe_payload(linha: servico.LinhaNFeApurada) -> dict:
    """Uma linha de NF-e da memória (DL-083). `papel` diz se é receita ou devolução (dedução)."""
    return {
        "origem": linha.origem,
        "escrituracao_id": linha.escrituracao_id,
        "numero": linha.numero,
        "data_competencia": _iso(linha.data_competencia),
        "natureza": linha.natureza,
        "cfop": linha.cfop,
        "atividade": linha.atividade,
        "papel": linha.papel,
        "valor": _dec(linha.valor),
    }


def _apuracao_payload(resultado: servico.Apuracao) -> dict:
    return {
        "ano": resultado.ano,
        "trimestre": resultado.trimestre,
        "situacao": resultado.situacao,
        "criterio": resultado.criterio,
        "recusas": [
            {"codigo": r.codigo, "mensagem": r.mensagem, "itens": list(r.itens)}
            for r in resultado.recusas
        ],
        "declaracao_integrais": {
            "valida": resultado.declaracao_valida,
            "total_declarado": _dec(resultado.declaracao_total),
            "integrais_atuais": _dec(resultado.integrais_atuais),
        },
        "notas": [
            {
                "escrituracao_id": n.escrituracao_id,
                "numero": n.numero,
                "data_competencia": _iso(n.data_competencia),
                "valor_servico": _dec(n.valor_servico),
                "desconto_incondicionado": _dec(n.desconto_incondicionado),
                "base": _dec(n.base),
                "atividade": n.atividade,
            }
            for n in resultado.notas
        ],
        "receitas": [
            {"receita_id": r.receita_id, "atividade": r.atividade, "valor": _dec(r.valor)}
            for r in resultado.receitas
        ],
        "irpj": _tributo_payload(resultado.irpj) if resultado.irpj else None,
        "csll": _tributo_payload(resultado.csll) if resultado.csll else None,
        "fechamento_irpj": _fechamento_payload(
            resultado.fechamento_irpj, resultado.irpj.linhas_do_ano if resultado.irpj else ()
        ),
        "fechamento_csll": _fechamento_payload(
            resultado.fechamento_csll, resultado.csll.linhas_do_ano if resultado.csll else ()
        ),
        "avisos": list(resultado.avisos),
        "nfe": [_linha_nfe_payload(linha) for linha in resultado.nfe],
        "devolucao_deduzida": _dec(resultado.devolucao_deduzida),
        "saldo_devolucao_transportado": _dec(resultado.saldo_devolucao_transportado),
        # HI-140: devolução e saldo por atividade. Os totais acima são a soma destes.
        # Reconferência da DL-083, R5: é o valor DEDUZIDO por atividade, e o nome diz isso.
        "devolucao_deduzida_por_atividade": _por_atividade_payload(
            resultado.devolucao_por_atividade
        ),
        "saldo_por_atividade": _por_atividade_payload(resultado.saldo_por_atividade),
    }


def _por_atividade_payload(pares) -> list[dict]:
    """Uma linha por atividade com valor, na ordem do catálogo: código, rótulo e valor."""
    return [
        {
            "atividade": codigo,
            "rotulo": tab.ATIVIDADES_POR_CODIGO[codigo].rotulo,
            "valor": _dec(valor),
        }
        for codigo, valor in pares
    ]


def _retencao_payload(linha: servico.LinhaRetencao) -> dict:
    return {
        "escrituracao_id": linha.escrituracao_id,
        "numero": linha.numero,
        "data_competencia": _iso(linha.data_competencia),
        "valor_servico": _dec(linha.valor_servico),
        "irrf_proposto": _dec(linha.irrf_proposto),
        "csll_proposta": _dec(linha.csll_proposta),
        "csll_situacao": linha.csll_situacao,
        "csll_motivo": linha.csll_motivo,
        "irrf_confirmado": _dec(linha.irrf_confirmado),
        "csll_confirmada": _dec(linha.csll_confirmada),
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class _Base(EmpresaEscopadaMixin, APIView):
    permission_classes = [TemEscritorioAtivo, PermissaoPresumido]


class AtividadesPresumidoView(_Base):
    """GET lista as atividades de presunção; POST cadastra uma (padrão não sobrepõe outra)."""

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        atividades = servico.listar_atividades(empresa)
        return Response({"atividades": [_atividade_payload(a) for a in atividades]})

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ATIVIDADE)
        empresa = self.get_empresa()
        try:
            atividade = servico.criar_atividade(empresa, _corpo(request), request.user, request)
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(_atividade_payload(atividade), status=status.HTTP_201_CREATED)


class EncerrarAtividadePresumidoView(_Base):
    def post(self, request, empresa_id, atividade_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ENCERRAR_ATIVIDADE)
        empresa = self.get_empresa()
        try:
            atividade = servico.encerrar_atividade(
                empresa, atividade_id, _corpo(request).get("fim"), request.user, request
            )
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(_atividade_payload(atividade), status=status.HTTP_200_OK)


class CriterioPresumidoView(_Base):
    """GET o critério de um ano (?ano=); POST define o critério uma vez (trocar é 409)."""

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano = _inteiro(request.query_params.get("ano"), "ano")
        if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
            raise DRFValidationError(f"'ano' inválido: {ano}.")
        return Response({"ano": ano, "criterio": servico.criterio_do_ano(empresa, ano)})

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_CRITERIO)
        empresa = self.get_empresa()
        dados = _corpo(request)
        try:
            ano = _inteiro(dados.get("ano"), "ano")
            registro, criado = servico.definir_criterio(
                empresa, ano, dados.get("criterio"), request.user, request
            )
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(
            {"ano": registro.ano, "criterio": registro.criterio},
            status=status.HTTP_201_CREATED if criado else status.HTTP_200_OK,
        )


class ReceitasPresumidoView(_Base):
    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, trimestre = _ano_e_trimestre(request)
        receitas = servico.listar_receitas(empresa, ano, trimestre)
        return Response(
            {
                "ano": ano,
                "trimestre": trimestre,
                "receitas": [_receita_payload(r) for r in receitas],
            }
        )

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_RECEITA)
        empresa = self.get_empresa()
        dados = _corpo(request)
        try:
            ano = _inteiro(dados.get("ano"), "ano")
            trimestre = _inteiro(dados.get("trimestre"), "trimestre")
            receita = servico.criar_receita(empresa, ano, trimestre, dados, request.user, request)
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(_receita_payload(receita), status=status.HTTP_201_CREATED)


class EstornarReceitaPresumidoView(_Base):
    def post(self, request, empresa_id, receita_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ESTORNO)
        empresa = self.get_empresa()
        try:
            receita = servico.estornar_receita(
                empresa, receita_id, _corpo(request).get("motivo"), request.user, request
            )
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(_receita_payload(receita), status=status.HTTP_200_OK)


class DeclaracaoIntegraisPresumidoView(_Base):
    """POST declara as receitas integrais do trimestre com o total atual como snapshot."""

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_INTEGRAIS)
        empresa = self.get_empresa()
        dados = _corpo(request)
        try:
            ano = _inteiro(dados.get("ano"), "ano")
            trimestre = _inteiro(dados.get("trimestre"), "trimestre")
            declaracao = servico.declarar_receitas_integrais(
                empresa, ano, trimestre, dados.get("observacao"), request.user, request
            )
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(
            {
                "id": declaracao.pk,
                "ano": declaracao.ano,
                "trimestre": declaracao.trimestre,
                "total": _dec(declaracao.total),
                "observacao": declaracao.observacao,
            },
            status=status.HTTP_201_CREATED,
        )


class RetencoesPresumidoView(_Base):
    """GET as retenções propostas do trimestre e o que já foi confirmado; POST confirma uma nota."""

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, trimestre = _ano_e_trimestre(request)
        linhas = servico.retencoes_do_trimestre(empresa, ano, trimestre)
        return Response(
            {
                "ano": ano,
                "trimestre": trimestre,
                "retencoes": [_retencao_payload(linha) for linha in linhas],
            }
        )

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_RETENCAO)
        empresa = self.get_empresa()
        dados = _corpo(request)
        try:
            escrituracao_id = _inteiro(dados.get("escrituracao_id"), "escrituracao_id")
            confirmacao = servico.confirmar_retencao(
                empresa,
                escrituracao_id,
                dados.get("irrf_confirmado"),
                dados.get("csll_confirmada"),
                dados.get("motivo"),
                request.user,
                request,
            )
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(
            {
                "id": confirmacao.pk,
                "escrituracao_id": confirmacao.escrituracao_id,
                "irrf_confirmado": _dec(confirmacao.irrf_confirmado),
                "csll_confirmada": _dec(confirmacao.csll_confirmada),
                "motivo": confirmacao.motivo,
                "estado": confirmacao.estado,
            },
            status=status.HTTP_201_CREATED,
        )


class MedidasPresumidoView(_Base):
    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        medidas = servico.listar_medidas(empresa)
        return Response({"medidas": [_medida_payload(m) for m in medidas]})

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_MEDIDA)
        empresa = self.get_empresa()
        try:
            medida = servico.cadastrar_medida(empresa, _corpo(request), request.user, request)
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(_medida_payload(medida), status=status.HTTP_201_CREATED)


class RevogarMedidaPresumidoView(_Base):
    def post(self, request, empresa_id, medida_id):
        _recusar_dado_nao_contratado(request, CONTRATO_REVOGAR)
        empresa = self.get_empresa()
        try:
            medida = servico.revogar_medida(
                empresa, medida_id, _corpo(request).get("motivo"), request.user, request
            )
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(_medida_payload(medida), status=status.HTTP_200_OK)


class EncerrarMedidaPresumidoView(_Base):
    """POST encerra a medida a partir de (ano, trimestre), inclusive (DL-084, item 7)."""

    def post(self, request, empresa_id, medida_id):
        _recusar_dado_nao_contratado(request, CONTRATO_ENCERRAR_MEDIDA)
        empresa = self.get_empresa()
        dados = _corpo(request)
        try:
            ano = _inteiro(dados.get("ano"), "ano")
            trimestre = _inteiro(dados.get("trimestre"), "trimestre")
            servico.encerrar_medida(
                empresa, medida_id, ano, trimestre, dados.get("motivo"), request.user, request
            )
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        medida = servico.listar_medidas(empresa).get(pk=medida_id)
        return Response(_medida_payload(medida), status=status.HTTP_200_OK)


class ParametrosPresumidoView(_Base):
    """GET os parâmetros da empresa (padrão do escritório se nunca gravados); POST grava.

    Padrão do escritório: três quotas e sem padrão de combustível (DL-084, item 6; HI-136).
    """

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        return Response(_parametros_payload(servico.parametros_da_empresa(empresa)))

    def post(self, request, empresa_id):
        _recusar_dado_nao_contratado(request, CONTRATO_PARAMETROS)
        empresa = self.get_empresa()
        try:
            parametros = servico.definir_parametros(empresa, _corpo(request), request.user, request)
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(_parametros_payload(parametros))


class PendenciasPresumidoView(_Base):
    """GET as pendências de cadastro do Presumido no mês (?ano=&mes=). DL-084, item 8."""

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano = _inteiro(request.query_params.get("ano"), "ano")
        mes = _inteiro(request.query_params.get("mes"), "mes")
        if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
            raise DRFValidationError(f"'ano' inválido: {ano}.")
        try:
            pendencias = servico.pendencias_de_cadastro(empresa, ano, mes)
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(
            {
                "ano": ano,
                "mes": mes,
                "pendencias": [{"codigo": p.codigo, "mensagem": p.mensagem} for p in pendencias],
            }
        )


def _parametros_payload(parametros: servico.ParametrosDaEmpresa) -> dict:
    return {
        "forma_recolhimento": parametros.forma_recolhimento,
        "padrao_combustivel": parametros.padrao_combustivel,
        "definido": parametros.definido,
    }


class ApuracaoPresumidoView(_Base):
    """GET a apuração do trimestre (?ano=&trimestre=), com memória e recusas nomeadas."""

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano, trimestre = _ano_e_trimestre(request)
        try:
            resultado = servico.apurar_trimestre(empresa, ano, trimestre)
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        payload = _apuracao_payload(resultado)
        # DL-084, item 6: a forma padrão só diz qual plano a tela abre. Não muda o cálculo.
        payload["forma_recolhimento_padrao"] = servico.parametros_da_empresa(
            empresa
        ).forma_recolhimento
        return Response(payload)


class LimitePresumidoView(_Base):
    """GET o controle do limite da LC 224 do ano (?ano=&tributo=irpj|csll)."""

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        ano = _inteiro(request.query_params.get("ano"), "ano")
        if not (_ANO_MINIMO <= ano <= _ANO_MAXIMO):
            raise DRFValidationError(f"'ano' inválido: {ano}.")
        tributo = request.query_params.get("tributo")
        try:
            controle = servico.controle_limite_ano(empresa, ano, tributo)
        except servico.PresumidoErro as exc:
            return _traduzir(exc)
        return Response(
            {
                "ano": controle.ano,
                "tributo": controle.tributo,
                "primeiro_trimestre": controle.primeiro_trimestre,
                "linhas": [
                    {
                        "trimestre": linha.trimestre,
                        "em_acrescimo": linha.em_acrescimo,
                        "receita_presumida": _dec(linha.receita_presumida),
                        "limite": _dec(linha.limite),
                        "excedente": _dec(linha.excedente),
                        "sobra": _dec(linha.sobra),
                        # A6: o que a tela mostra como "diferença" e "parcela suspensa".
                        "diferenca_recalculo": _dec(linha.diferenca_recalculo),
                        "suspensa_por_medida": linha.suspensa_por_medida,
                    }
                    for linha in controle.linhas
                ],
                "fechamento": _fechamento_payload(controle.fechamento, controle.linhas),
                "recusas": [
                    {"codigo": r.codigo, "mensagem": r.mensagem, "itens": list(r.itens)}
                    for r in controle.recusas
                ],
            }
        )
