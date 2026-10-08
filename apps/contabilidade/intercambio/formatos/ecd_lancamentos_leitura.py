"""Leitor de LANÇAMENTOS no leiaute da ECD: I200, I250 e I075 (DL-077, fatia 3, frente A).

FONTE. Manual de Orientação do Leiaute 9 da ECD, Anexo ao ADE Cofis nº 01/2026, atualização
de maio de 2026, lido em http://sped.rfb.gov.br/arquivo/download/7990 em 08/10/2026. O texto
NÃO é copiado para cá (RC-167): cita-se registro, campo e página IMPRESSA do rodapé.
- 0000: campo 3 DT_INI, campo 4 DT_FIN, campo 6 CNPJ (pp. 63-64).
- I075 (histórico padronizado): campo 2 COD_HIST, campo 3 DESCR_HIST (p. 130).
- I200 (lançamento): campos 1 a 6 (pp. 143-144); regras (pp. 145-147).
- I250 (partidas): campos 1 a 9 (pp. 148-149); regras (pp. 149-151).

O QUE ENTRA. Lançamento N (normal) e X (extemporâneo). O lançamento E (encerramento das
contas de resultado) NÃO entra: o zeramento do resultado é do DataLedger (DL-043), então o
E vira aviso no arquivo e nada é gravado para ele. Os demais registros são contados em
`registros_ignorados`.

O QUE É RECUSADO (o lançamento inteiro, com a linha e o campo):
- 0000 repetido (A9, mesma regra do leitor do plano): é erro, e o segundo não é lido; o
  primeiro 0000 é o que vale;
- número do lançamento repetido no arquivo (REGRA_REGISTRO_DUPLICADO, p. 146): recusam-se os
  dois;
- data fora do intervalo do 0000 (REGRA_DATA_INTERVALO_DO_ARQUIVO, p. 146);
- valor do lançamento diferente da soma dos débitos ou da soma dos créditos
  (REGRA_VALIDACAO_VL_LCTO_DEB e _CRED, p. 146);
- partida sem histórico (HIST e COD_HIST_PAD vazios, REGRA_HISTORICO_OBRIGATORIO, p. 150);
- campo fora do formato (N 19,2 com vírgula, datas ddmmaaaa, IND_DC D ou C etc.).

O QUE VIRA AVISO (o contador confere e aceita antes de gravar):
- lançamento X: o histórico precisa trazer motivo, data e número de origem (p. 149, campo 8,
  observação; ITG 2000 (R1), item 32);
- COD_HIST_PAD sem registro I075 no arquivo: só o HIST é usado;
- COD_CCUS, NUM_ARQ e COD_PART preenchidos: o DataLedger não tem centro de custo, documento
  arquivado nem participante, então o campo é ignorado e o aviso diz isso;
- data anterior a 01/01/1980 (REGRA_DATA_ANTIGA, p. 146);
- 0000 sem CNPJ, ou arquivo sem 0000 (A9): a empresa do arquivo não é conferida, e o aviso diz
  isso. Mesma regra de `ecd.py`.

HISTÓRICO. O histórico é POR PARTIDA no leiaute (p. 149). Quando há COD_HIST_PAD com I075, o
texto da partida é a fórmula do próprio manual: DESCR_HIST + " " + HIST (p. 149). Sem HIST,
vale só a descrição. A montagem do histórico do lançamento é do núcleo.

NUMERAÇÃO. O número do lançamento é NUM_LCTO (campo 2 do I200, chave do registro, p. 146).
CODIFICAÇÃO. A ECD exige ISO-8859-1 (p. 52); UTF-8 é aceito com aviso (ver `ecd._decodificar`).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    NIVEL_AVISO,
    NIVEL_ERRO,
    LancamentoLido,
    Ocorrencia,
    PartidaLida,
    ResultadoLeitura,
)
from apps.contabilidade.intercambio.formatos.ecd import (
    REGISTROS_DO_LEIAUTE_9,
    _data_ddmmaaaa_valida,
    _decodificar,
    _tem_controle,
)

FORMATO = "ecd"

TAMANHO_MAXIMO_NUM_LCTO = 255  # campo C sem tamanho próprio no manual: padrão de 255 (p. 53)
TAMANHO_MAXIMO_COD_CTA = 255  # idem (p. 53)
TAMANHO_MAXIMO_HIST = 65535  # I250, campo 08 (p. 149)
IND_LCTO_NORMAL = "N"
IND_LCTO_ENCERRAMENTO = "E"  # p. 143, campo 05
IND_LCTO_EXTEMPORANEO = "X"  # p. 143, campo 05
DATA_ANTIGA = date(1980, 1, 1)  # REGRA_DATA_ANTIGA: aviso se não for superior a 01/01/1980 (p. 146)

_PADRAO_VALOR = re.compile(r"[0-9]+,[0-9]{2}")  # N 19,2 com vírgula, sem milhar (p. 53)
# CNPJ numérico ou alfanumérico de 14 posições (RC-46): 12 caracteres + 2 dígitos verificadores.
_PADRAO_CNPJ = re.compile(r"[A-Z0-9]{12}[0-9]{2}")


@dataclass
class _Partida:
    linha: int
    codigo: str
    lado: str
    valor: Decimal
    cod_hist_pad: str
    hist: str


@dataclass
class _Lancamento:
    """I200 lido e suas partidas. `rejeitado` = algum campo ou partida foi recusado."""

    linha: int
    numero: str | None = None
    data: date | None = None
    vl_lcto: Decimal | None = None
    ind_lcto: str = ""
    data_origem: date | None = None
    partidas: list = field(default_factory=list)
    rejeitado: bool = False


def _valor_com_virgula(texto):
    """Decimal de N 19,2 com vírgula, ou None se o texto não obedece ao formato."""
    if not _PADRAO_VALOR.fullmatch(texto):
        return None
    return Decimal(texto.replace(",", "."))


def _ler_0000(numero, campos, ocorrencias):
    """(período, CNPJ) do 0000. Período é (DT_INI, DT_FIN) se ambos forem datas válidas.

    A9: 0000 sem CNPJ é AVISO, porque a empresa do arquivo não pode ser conferida. O CNPJ é
    guardado na forma canônica (maiúsculas, sem máscara; RC-46), a mesma do leitor do plano,
    para que a comparação com a empresa não dependa de como o arquivo foi digitado.
    """
    periodo = None
    documento = None
    cnpj = campos[5].strip().upper() if len(campos) > 5 else ""
    if not cnpj:
        ocorrencias.append(
            Ocorrencia(
                numero,
                "0000.6",
                NIVEL_AVISO,
                "registro 0000 sem CNPJ (campo 6, p. 64): a empresa do arquivo não foi conferida.",
            )
        )
    elif not _PADRAO_CNPJ.fullmatch(cnpj):
        ocorrencias.append(
            Ocorrencia(
                numero,
                "0000.6",
                NIVEL_ERRO,
                "CNPJ do registro 0000 (campo 6, p. 64) deve ter 14 posições: números ou o "
                "CNPJ alfanumérico (RC-46). Não é possível conferir a empresa.",
            )
        )
    else:
        documento = cnpj
    if len(campos) > 3:
        ini, fim = campos[2].strip(), campos[3].strip()
        if _data_ddmmaaaa_valida(ini) and _data_ddmmaaaa_valida(fim):
            periodo = (
                date(int(ini[4:]), int(ini[2:4]), int(ini[:2])),
                date(int(fim[4:]), int(fim[2:4]), int(fim[:2])),
            )
    return periodo, documento


def _ler_i200(numero, campos, ocorrencias):
    """Cabeçalho do lançamento (I200, campos 1 a 6, pp. 143-144)."""
    lancamento = _Lancamento(linha=numero)

    def recusar(campo, mensagem):
        ocorrencias.append(Ocorrencia(numero, campo, NIVEL_ERRO, mensagem))
        lancamento.rejeitado = True

    if len(campos) != 6:
        recusar("REG", f"I200 tem 6 campos (pp. 143-144); o registro traz {len(campos)}.")
        return lancamento

    _reg, num, dt, vl, ind, dt_ext = (valor.strip() for valor in campos)

    if not num:
        recusar("NUM_LCTO", "número do lançamento obrigatório (campo 02, p. 143).")
    elif len(num) > TAMANHO_MAXIMO_NUM_LCTO or _tem_controle(num):
        recusar("NUM_LCTO", "número com caractere de controle ou acima de 255 caracteres (p. 53).")
    else:
        lancamento.numero = num

    if not _data_ddmmaaaa_valida(dt):
        recusar("DT_LCTO", f"data '{dt}' não é ddmmaaaa válida (campo 03, p. 53 e p. 143).")
    else:
        lancamento.data = date(int(dt[4:]), int(dt[2:4]), int(dt[:2]))

    valor = _valor_com_virgula(vl)
    if valor is None:
        recusar("VL_LCTO", f"valor '{vl}' fora do formato N 19,2 (vírgula, duas casas, p. 53).")
    elif valor <= 0:
        recusar(
            "VL_LCTO", "valor do lançamento diferente de zero (REGRA_OBRIG_NAO_MF_I200, p. 145)."
        )
    else:
        lancamento.vl_lcto = valor

    if ind not in (IND_LCTO_NORMAL, IND_LCTO_ENCERRAMENTO, IND_LCTO_EXTEMPORANEO):
        recusar("IND_LCTO", f"indicador '{ind}' deve ser N, E ou X (campo 05, p. 143).")
    else:
        lancamento.ind_lcto = ind

    if ind == IND_LCTO_EXTEMPORANEO:
        if not dt_ext:
            recusar(
                "DT_LCTO_EXT",
                "lançamento extemporâneo (X) exige a data de origem (REGRA_DT_LCTO_EXT_"
                "OBRIGATORIA, p. 146).",
            )
        elif not _data_ddmmaaaa_valida(dt_ext):
            recusar("DT_LCTO_EXT", f"data de origem '{dt_ext}' não é ddmmaaaa válida (p. 53).")
        else:
            lancamento.data_origem = date(int(dt_ext[4:]), int(dt_ext[2:4]), int(dt_ext[:2]))
    elif dt_ext:
        recusar(
            "DT_LCTO_EXT",
            "data de origem só existe no lançamento extemporâneo "
            "(REGRA_DT_LCTO_EXT_INDEVIDA, p. 146).",
        )
    return lancamento


def _ler_i250(numero, campos, lancamento, ocorrencias):
    """Partida (I250, campos 1 a 9, pp. 148-149). Acrescenta a `lancamento` se for válida."""

    def recusar(campo, mensagem):
        ocorrencias.append(Ocorrencia(numero, campo, NIVEL_ERRO, mensagem))
        lancamento.rejeitado = True

    def avisar(campo, mensagem):
        ocorrencias.append(Ocorrencia(numero, campo, NIVEL_AVISO, mensagem))

    if len(campos) != 9:
        recusar("REG", f"I250 tem 9 campos (pp. 148-149); o registro traz {len(campos)}.")
        return

    _reg, cod_cta, cod_ccus, vl_dc, ind_dc, num_arq, cod_hist_pad, hist, cod_part = campos
    cod_cta = cod_cta.strip()
    vl_dc = vl_dc.strip()
    ind_dc = ind_dc.strip()
    cod_hist_pad = cod_hist_pad.strip()

    erro_na_partida = False
    if not cod_cta or len(cod_cta) > TAMANHO_MAXIMO_COD_CTA or _tem_controle(cod_cta):
        recusar("COD_CTA", "código da conta obrigatório, até 255 caracteres (p. 148).")
        erro_na_partida = True

    valor = _valor_com_virgula(vl_dc)
    if valor is None or valor <= 0:
        recusar("VL_DC", f"valor da partida '{vl_dc}' fora do N 19,2 positivo (p. 148).")
        erro_na_partida = True

    if ind_dc not in ("D", "C"):
        recusar("IND_DC", f"indicador '{ind_dc}' deve ser D ou C (campo 05, p. 148).")
        erro_na_partida = True

    if hist.strip() == "" and cod_hist_pad == "":
        recusar(
            "HIST",
            "partida sem histórico: HIST ou COD_HIST_PAD tem de estar preenchido "
            "(REGRA_HISTORICO_OBRIGATORIO, p. 150).",
        )
        erro_na_partida = True
    if len(hist) > TAMANHO_MAXIMO_HIST or _tem_controle(hist):
        recusar(
            "HIST", "histórico com caractere de controle ou acima de 65.535 caracteres (p. 149)."
        )
        erro_na_partida = True

    if cod_ccus.strip():
        avisar(
            "COD_CCUS",
            "centro de custos ignorado: o DataLedger não tem centro de custo (campo 03, p. 148).",
        )
    if num_arq.strip():
        avisar(
            "NUM_ARQ",
            "NUM_ARQ ignorado: o DataLedger não guarda o caminho do documento arquivado "
            "(campo 06, p. 149).",
        )
    if cod_part.strip():
        avisar(
            "COD_PART",
            "participante ignorado: o DataLedger não tem participante (campo 09, p. 149).",
        )

    if erro_na_partida:
        lancamento.rejeitado = True
        return
    lado = LADO_DEBITO if ind_dc == "D" else LADO_CREDITO
    lancamento.partidas.append(
        _Partida(
            linha=numero,
            codigo=cod_cta,
            lado=lado,
            valor=valor,
            cod_hist_pad=cod_hist_pad,
            hist=hist,
        )
    )


def _resolver_historico(partida, historicos_padronizados, linha_do_lancamento, ocorrencias):
    """Texto da partida: fórmula do manual (p. 149) com I075, ou só o HIST. None = recusada."""
    if not partida.cod_hist_pad:
        return partida.hist
    descricao = historicos_padronizados.get(partida.cod_hist_pad)
    if descricao is None:
        ocorrencias.append(
            Ocorrencia(
                partida.linha,
                "COD_HIST_PAD",
                NIVEL_AVISO,
                f"histórico padronizado '{partida.cod_hist_pad}' não está no I075 deste arquivo: "
                "só o HIST da partida é usado (p. 149).",
            )
        )
        if not partida.hist.strip():
            ocorrencias.append(
                Ocorrencia(
                    partida.linha,
                    "HIST",
                    NIVEL_ERRO,
                    "partida sem texto de histórico: o código padronizado não tem I075 no "
                    "arquivo e o HIST está vazio (REGRA_HISTORICO_OBRIGATORIO, p. 150).",
                )
            )
            return None
        return partida.hist
    # Fórmula do próprio manual: [DESCR_HIST] + " " + [HIST] (p. 149).
    return descricao if not partida.hist.strip() else f"{descricao} {partida.hist}"


def ler(conteudo: bytes) -> ResultadoLeitura:
    """Lê I200 e I250 (e I075, para o histórico padronizado) de um trecho de ECD."""
    texto, codificacao, ocorrencias = _decodificar(conteudo)
    resultado = ResultadoLeitura(formato=FORMATO, codificacao=codificacao)
    ignorados = Counter()
    lancamentos = []
    historicos_padronizados = {}
    periodo = None
    documento = None
    documento_visto = False
    atual = None

    for numero, bruta in enumerate(texto.split("\n"), start=1):
        linha = bruta.rstrip("\r")
        if not linha.strip():
            continue
        if not (len(linha) >= 2 and linha.startswith("|") and linha.endswith("|")):
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "linha",
                    NIVEL_ERRO,
                    "linha fora do leiaute: cada registro começa e termina com '|' (p. 52).",
                )
            )
            atual = None
            continue

        campos = linha[1:-1].split("|")
        reg = campos[0].strip()
        if reg not in REGISTROS_DO_LEIAUTE_9:
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "REG",
                    NIVEL_ERRO,
                    f"registro desconhecido '{reg}': não consta da tabela de registros do "
                    "leiaute 9 (pp. 57-58 e 230-233).",
                )
            )
            atual = None
            continue

        if reg != "I250":
            atual = None  # a partida só se liga ao I200 imediatamente acima (p. 148)

        if reg == "0000":
            # A9: o segundo 0000 é erro e NÃO sobrescreve o primeiro. Antes, sobrescrevia o
            # período e o CNPJ, e a conferência podia ser feita contra a abertura de outra empresa.
            if documento_visto:
                ocorrencias.append(
                    Ocorrencia(
                        numero,
                        "0000",
                        NIVEL_ERRO,
                        "segundo 0000 no arquivo: um arquivo traz a abertura de uma empresa só.",
                    )
                )
            else:
                documento_visto = True
                periodo, documento = _ler_0000(numero, campos, ocorrencias)
            ignorados[reg] += 1  # o 0000 entra só pelo CNPJ e pelo período
            continue
        if reg == "I075":
            if len(campos) != 3:
                ocorrencias.append(
                    Ocorrencia(numero, "I075", NIVEL_ERRO, "I075 tem 3 campos (p. 130).")
                )
                continue
            cod_hist = campos[1].strip()
            if not cod_hist or _tem_controle(cod_hist):
                ocorrencias.append(
                    Ocorrencia(
                        numero,
                        "COD_HIST",
                        NIVEL_ERRO,
                        "código do histórico padronizado vazio (p. 130).",
                    )
                )
            elif cod_hist in historicos_padronizados:
                ocorrencias.append(
                    Ocorrencia(
                        numero,
                        "COD_HIST",
                        NIVEL_ERRO,
                        f"código de histórico '{cod_hist}' repetido "
                        "(REGRA_REGISTRO_DUPLICADO, p. 130).",
                    )
                )
            else:
                historicos_padronizados[cod_hist] = campos[2].strip()
            continue
        if reg == "I200":
            atual = _ler_i200(numero, campos, ocorrencias)
            lancamentos.append(atual)
            continue
        if reg == "I250":
            if atual is None:
                ocorrencias.append(
                    Ocorrencia(
                        numero, "REG", NIVEL_ERRO, "I250 sem I200 imediatamente acima (p. 148)."
                    )
                )
                continue
            _ler_i250(numero, campos, atual, ocorrencias)
            continue
        ignorados[reg] += 1

    # Nº do lançamento repetido: o arquivo é ambíguo, então os dois são recusados (p. 146).
    vistos = {}
    for lancamento in lancamentos:
        if lancamento.numero is None:
            continue
        if lancamento.numero in vistos:
            ocorrencias.append(
                Ocorrencia(
                    lancamento.linha,
                    "NUM_LCTO",
                    NIVEL_ERRO,
                    f"NUM_LCTO '{lancamento.numero}' repetido (REGRA_REGISTRO_DUPLICADO, p. 146); "
                    f"a primeira ocorrência é a da linha {vistos[lancamento.numero].linha}.",
                )
            )
            lancamento.rejeitado = True
            vistos[lancamento.numero].rejeitado = True
        else:
            vistos[lancamento.numero] = lancamento

    aceitos = []
    for lancamento in lancamentos:
        if lancamento.rejeitado or lancamento.numero is None:
            continue
        if periodo is not None and lancamento.data is not None:
            inicio, fim = periodo
            if not (inicio <= lancamento.data <= fim):
                ocorrencias.append(
                    Ocorrencia(
                        lancamento.linha,
                        "DT_LCTO",
                        NIVEL_ERRO,
                        "data do lançamento fora do período do arquivo (0000, DT_INI a DT_FIN; "
                        "REGRA_DATA_INTERVALO_DO_ARQUIVO, p. 146).",
                    )
                )
                continue
        if lancamento.data is not None and lancamento.data <= DATA_ANTIGA:
            ocorrencias.append(
                Ocorrencia(
                    lancamento.linha,
                    "DT_LCTO",
                    NIVEL_AVISO,
                    "data anterior a 01/01/1980 (REGRA_DATA_ANTIGA, p. 146).",
                )
            )
        if lancamento.ind_lcto == IND_LCTO_ENCERRAMENTO:
            ocorrencias.append(
                Ocorrencia(
                    lancamento.linha,
                    "IND_LCTO",
                    NIVEL_AVISO,
                    "lançamento de encerramento (E) não é importado: o zeramento do resultado é "
                    "gerado pelo DataLedger (DL-043). Nada foi gravado para ele.",
                )
            )
            continue
        if lancamento.ind_lcto == IND_LCTO_EXTEMPORANEO:
            if (
                periodo is not None
                and lancamento.data_origem is not None
                and lancamento.data_origem < periodo[0]
            ):
                ocorrencias.append(
                    Ocorrencia(
                        lancamento.linha,
                        "DT_LCTO_EXT",
                        NIVEL_ERRO,
                        "data de origem anterior ao início da escrituração "
                        "(REGRA_DT_LCTO_EXT_INV, p. 146).",
                    )
                )
                continue
            ocorrencias.append(
                Ocorrencia(
                    lancamento.linha,
                    "IND_LCTO",
                    NIVEL_AVISO,
                    "lançamento extemporâneo (X): confira que o histórico traz o motivo, "
                    "a data e o "
                    "número do lançamento de origem (p. 149; ITG 2000 (R1), item 32).",
                )
            )
        if not lancamento.partidas:
            ocorrencias.append(
                Ocorrencia(
                    lancamento.linha, "I250", NIVEL_ERRO, "lançamento sem partidas (pp. 148-151)."
                )
            )
            continue

        textos = []
        for partida in lancamento.partidas:
            texto_da_partida = _resolver_historico(
                partida, historicos_padronizados, lancamento.linha, ocorrencias
            )
            textos.append(texto_da_partida)
        if any(texto is None for texto in textos):
            continue

        soma_debito = sum(
            (p.valor for p in lancamento.partidas if p.lado == LADO_DEBITO), Decimal("0.00")
        )
        soma_credito = sum(
            (p.valor for p in lancamento.partidas if p.lado == LADO_CREDITO), Decimal("0.00")
        )
        if soma_debito != lancamento.vl_lcto or soma_credito != lancamento.vl_lcto:
            ocorrencias.append(
                Ocorrencia(
                    lancamento.linha,
                    "VL_LCTO",
                    NIVEL_ERRO,
                    f"VL_LCTO {lancamento.vl_lcto} difere da soma dos débitos ({soma_debito}) "
                    f"ou dos créditos ({soma_credito}) (REGRA_VALIDACAO_VL_LCTO_DEB/CRED, p. 146).",
                )
            )
            continue

        aceitos.append(
            LancamentoLido(
                linha=lancamento.linha,
                numero=lancamento.numero,
                data=lancamento.data,
                historico="",  # o histórico do lançamento é montado pelo núcleo, por partida
                partidas=tuple(
                    PartidaLida(
                        linha=partida.linha,
                        codigo_conta=partida.codigo,
                        lado=partida.lado,
                        valor=partida.valor,
                        historico=texto,
                    )
                    for partida, texto in zip(lancamento.partidas, textos, strict=True)
                ),
            )
        )

    if not documento_visto:
        # A9: sem 0000 não há como conferir a empresa. Aviso, e não erro: o trecho pode ser
        # legítimo, mas o contador precisa confirmar antes de aplicar.
        ocorrencias.append(
            Ocorrencia(
                0,
                "0000",
                NIVEL_AVISO,
                "o arquivo não traz o registro 0000: a empresa do arquivo não foi conferida. "
                "Confira que o trecho é mesmo desta empresa antes de aplicar.",
            )
        )
    resultado.lancamentos = aceitos
    resultado.documento_declarado = documento
    resultado.ocorrencias = sorted(ocorrencias, key=lambda o: (o.linha, o.campo))
    resultado.registros_ignorados = dict(sorted(ignorados.items()))
    return resultado
