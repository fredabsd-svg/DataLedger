"""API de leitura das NF-e e NFC-e recebidas — DL-080, frente A.

Rotas em `apps/fiscal/urls_api.py`, sob `fiscal/api/`. Só `GET`: a recepção continua pelas
telas de envio (`apps.fiscal.views_web`), e nenhuma escrita entra por esta API.

Autorização (AGENTS.md §11, no servidor): `PodeConsultarFiscal`, que vale para todos os
papéis menos CLIENTE (mesmo critério da NFS-e). O papel vem de `request.papel`, resolvido
pelo middleware a partir do vínculo com o escritório ATIVO.

Isolamento em duas camadas: a empresa vem de `EmpresaEscopadaMixin` (404 para empresa de
outro escritório), e a nota é buscada pelo VÍNCULO com essa empresa (404 para nota de outra
empresa do mesmo escritório, ou de outro escritório: IDOR).

Direção para o cliente: calculada pelo PAPEL da empresa combinado com `tpNF`. `tpNF` é do
ponto de vista do emitente, então sozinho ele inverte a direção quando a empresa é a
destinatária (pesquisa, seção 5). Ver `direcao_para_o_cliente`.
"""

from datetime import date
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.fiscal import services
from apps.fiscal.api import PodeConsultarFiscal
from apps.fiscal.models import EventoNFe, ModeloNFe, PapelNFe, VinculoNFeEmpresa
from apps.tenancy.permissions import TemEscritorioAtivo

# Eventos de NF-e com nome, só para os códigos que a pesquisa do leiaute (seção 2) cita.
# Código fora desta lista é mostrado com o número e a frase "não catalogado", nunca com um
# nome inventado.
DESCRICAO_EVENTO_NFE = {
    "110110": "Carta de Correção",
    "110111": "Cancelamento",
    "110112": "Cancelamento por substituição",
    "110140": "EPEC (emissão em contingência)",
    "110150": "Ator interessado (transportador)",
    "110001": "Cancelamento de evento",
    "111500": "Prorrogação de ICMS e seus cancelamentos",
    "111501": "Prorrogação de ICMS e seus cancelamentos",
    "111502": "Prorrogação de ICMS e seus cancelamentos",
    "111503": "Prorrogação de ICMS e seus cancelamentos",
    "210200": "Confirmação da operação",
    "210210": "Ciência da operação",
    "210220": "Desconhecimento da operação",
    "210240": "Operação não realizada",
    "211110": "Solicitação de apropriação de crédito presumido",
    "211124": "Perecimento, perda, roubo ou furto no transporte contratado pelo adquirente",
    "211128": "Aceite de débito na apuração por nota de crédito",
    "211130": "Imobilização de item",
    "211140": "Solicitação de apropriação de crédito de combustível",
    "211150": "Solicitação de apropriação de crédito de bens e serviços",
    "112110": "Informação de efetivo pagamento integral (crédito presumido)",
    "112120": "Importação em ALC/ZFM não convertida em isenção",
    "112130": "Perecimento, perda, roubo ou furto no transporte contratado pelo fornecedor",
    "112140": "Fornecimento não realizado com pagamento antecipado",
    "112150": "Atualização da data de previsão de entrega",
    "212110": "Manifestação sobre transferência de crédito de IBS (sucessão)",
    "212120": "Manifestação sobre transferência de crédito de CBS (sucessão)",
    "412120": "Manifestação do Fisco sobre transferência de crédito de IBS",
    "412130": "Manifestação do Fisco sobre transferência de crédito de CBS",
}

_SITUACOES = ("valida", "cancelada")


def direcao_para_o_cliente(papel: str, tp_nf: str) -> str:
    """Sentido da nota para a EMPRESA, pelo papel combinado com `tpNF`.

    - emitente e `tpNF` 1: `saida` (a empresa vendeu);
    - emitente e `tpNF` 0: `entrada_propria` (a empresa emitiu uma nota de entrada);
    - destinatário e `tpNF` 1: `entrada` (a empresa comprou);
    - destinatário e `tpNF` 0: `a_conferir`. A pesquisa não encontrou, em fonte oficial,
      a regra desse caso. Não se adivinha: a tela mostra "a conferir".
    """
    if papel == PapelNFe.EMITENTE:
        return "saida" if tp_nf == "1" else "entrada_propria"
    if papel == PapelNFe.DESTINATARIO:
        return "entrada" if tp_nf == "1" else "a_conferir"
    raise ValueError(f"papel desconhecido: {papel!r}.")


def _decimal_texto(valor: Decimal | None) -> str | None:
    """Valor monetário como texto (sem `float`), ou `None` quando o campo é ausente."""
    if valor is None:
        return None
    return format(valor, "f")


def _data_iso(valor) -> str:
    return valor.isoformat()


def _filtros_da_consulta(parametros) -> dict:
    """Lê e valida os filtros. Valor inválido vira `ValueError` com mensagem em português."""
    filtros = {}
    for nome in ("inicio", "fim"):
        bruto = parametros.get(nome, "").strip()
        if bruto:
            try:
                filtros[nome] = date.fromisoformat(bruto)
            except ValueError as exc:
                raise ValueError(f"'{nome}' deve ser uma data AAAA-MM-DD.") from exc
    if "inicio" in filtros and "fim" in filtros and filtros["inicio"] > filtros["fim"]:
        raise ValueError("'inicio' não pode ser posterior a 'fim'.")

    papel = parametros.get("papel", "").strip()
    if papel:
        if papel not in PapelNFe.values:
            raise ValueError("'papel' deve ser 'emitente' ou 'destinatario'.")
        filtros["papel"] = papel

    modelo = parametros.get("modelo", "").strip()
    if modelo:
        if modelo not in ModeloNFe.values:
            raise ValueError("'modelo' deve ser '55' (NF-e) ou '65' (NFC-e).")
        filtros["modelo"] = modelo

    situacao = parametros.get("situacao", "").strip()
    if situacao:
        if situacao not in _SITUACOES:
            raise ValueError("'situacao' deve ser 'valida' ou 'cancelada'.")
        filtros["situacao"] = situacao
    return filtros


def _item_da_lista(vinculo: VinculoNFeEmpresa) -> dict:
    documento = vinculo.documento
    return {
        "documento_id": documento.pk,
        "papel": vinculo.papel,
        "direcao": direcao_para_o_cliente(vinculo.papel, documento.tp_nf),
        "situacao": "cancelada" if vinculo.cancelada else "valida",
        "modelo": documento.modelo,
        "modelo_nome": documento.get_modelo_display(),
        "serie": documento.serie,
        "numero": documento.numero,
        "chave": documento.chave,
        "dh_emissao": _data_iso(documento.dh_emissao),
        "v_nf": _decimal_texto(documento.v_nf),
        "tem_ibscbs": documento.tem_ibscbs_total or documento.tem_ibscbs_item,
        "transferencia_entre_estabelecimentos": documento.transferencia_entre_estabelecimentos,
    }


def _evento_da_nota(evento: EventoNFe) -> dict:
    return {
        "identificador": evento.identificador,
        "tp_evento": evento.tp_evento,
        "descricao": DESCRICAO_EVENTO_NFE.get(
            evento.tp_evento, "evento não catalogado nesta recepção"
        ),
        "n_seq_evento": evento.n_seq_evento,
        "dh_evento": _data_iso(evento.dh_evento),
        "autor": {
            "tipo_documento": evento.autor_tipo_documento,
            "documento": evento.autor_documento,
        },
        "autor_identificado": evento.empresa_id is not None,
        # `c_stat` do retorno: ausente quando o retorno não veio. Sem retorno, sem efeito.
        "c_stat": evento.c_stat,
        "registrado": evento.c_stat in services.CODIGOS_EFETIVOS_NFE,
        "efeito": services.efeito_do_evento_nfe(evento),
        # Aviso para conferir (cStat 136: registrado, mas não vinculado a NF-e). `None` sem aviso.
        "aviso": services.aviso_do_evento_nfe(evento),
    }


def _detalhe_da_nota(vinculo: VinculoNFeEmpresa, eventos, situacao: str) -> dict:
    documento = vinculo.documento
    destinatario_definido = bool(documento.destinatario_tipo_documento)
    return {
        "documento_id": documento.pk,
        "papel": vinculo.papel,
        "direcao": direcao_para_o_cliente(vinculo.papel, documento.tp_nf),
        "situacao": situacao,
        "modelo": documento.modelo,
        "modelo_nome": documento.get_modelo_display(),
        "versao": documento.versao,
        "chave": documento.chave,
        "serie": documento.serie,
        "numero": documento.numero,
        "dh_emissao": _data_iso(documento.dh_emissao),
        "tp_nf": documento.tp_nf,
        "fin_nfe": documento.fin_nfe,
        "tp_nf_debito": documento.tp_nf_debito or None,
        "tp_nf_credito": documento.tp_nf_credito or None,
        "id_dest": documento.id_dest,
        "c_uf": documento.c_uf,
        "emitente": {
            "tipo_documento": documento.emitente_tipo_documento,
            "documento": documento.emitente_documento,
            "nome": documento.emitente_nome,
            "crt": documento.emitente_crt or None,
        },
        "destinatario": (
            {
                "tipo_documento": documento.destinatario_tipo_documento,
                "documento": documento.destinatario_documento,
                "nome": documento.destinatario_nome,
            }
            if destinatario_definido
            else None
        ),
        "totais": {
            "v_nf": _decimal_texto(documento.v_nf),
            "v_prod": _decimal_texto(documento.v_prod),
            "v_icms": _decimal_texto(documento.v_icms),
            "v_st": _decimal_texto(documento.v_st),
            "v_ipi": _decimal_texto(documento.v_ipi),
            "v_pis": _decimal_texto(documento.v_pis),
            "v_cofins": _decimal_texto(documento.v_cofins),
            "v_desc": _decimal_texto(documento.v_desc),
            "v_frete": _decimal_texto(documento.v_frete),
        },
        "protocolo": {
            "c_stat": documento.c_stat,
            "n_prot": documento.n_prot or None,
            "dh_recbto": _data_iso(documento.dh_recbto),
        },
        "quantidade_itens": documento.quantidade_itens,
        "tem_ibscbs_total": documento.tem_ibscbs_total,
        "tem_ibscbs_item": documento.tem_ibscbs_item,
        "transferencia_entre_estabelecimentos": documento.transferencia_entre_estabelecimentos,
        "eventos": [_evento_da_nota(evento) for evento in eventos],
    }


class NotasNFeView(EmpresaEscopadaMixin, APIView):
    """GET — NF-e e NFC-e em que a empresa é emitente ou destinatária.

    Filtros opcionais na querystring: `inicio` e `fim` (AAAA-MM-DD, por `dh_emissao`), `papel`
    (`emitente` ou `destinatario`), `modelo` (`55` ou `65`), `situacao` (`valida` ou `cancelada`).
    Uma nota aparece uma vez por papel da empresa, com o papel de cada linha.
    """

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id):
        empresa = self.get_empresa()
        try:
            filtros = _filtros_da_consulta(request.query_params)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        vinculos = services.vinculos_nfe_da_empresa(empresa.escritorio, empresa, **filtros)
        return Response({"empresa_id": empresa.pk, "notas": [_item_da_lista(v) for v in vinculos]})


class DetalheNFeView(EmpresaEscopadaMixin, APIView):
    """GET — uma NF-e ou NFC-e da empresa, com todos os eventos registrados para a chave.

    Nota de OUTRA empresa, mesmo do mesmo escritório, responde 404: a busca passa pelo vínculo
    com a empresa da URL. O evento aparece mesmo quando não tem empresa identificada (órfão).
    """

    permission_classes = [TemEscritorioAtivo, PodeConsultarFiscal]

    def get(self, request, empresa_id, documento_id):
        empresa = self.get_empresa()
        vinculo = get_object_or_404(
            VinculoNFeEmpresa.objects.select_related("documento"),
            empresa=empresa,
            documento_id=documento_id,
            documento__escritorio=empresa.escritorio,
        )
        documento = vinculo.documento
        eventos = EventoNFe.objects.filter(
            escritorio=empresa.escritorio, chave=documento.chave
        ).order_by("dh_evento", "n_seq_evento")
        situacao = services.situacao_da_nfe(documento)
        return Response(_detalhe_da_nota(vinculo, eventos, situacao))
