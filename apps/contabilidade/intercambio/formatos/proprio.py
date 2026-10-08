"""Formato próprio do DataLedger para o plano de contas (DL-077, fatia 1).

Este docstring é a ESPECIFICAÇÃO do formato. O arquiteto copia o texto para a
documentação do projeto (`docs/`); o código não grava documento fora de si.

ESPECIFICAÇÃO — versão 1
------------------------

Codificação
    UTF-8. Na leitura, com ou sem BOM (o BOM é descartado). Na escrita, sem BOM.

Fim de linha
    Na leitura, CRLF ou LF. Na escrita, CRLF (RFC 4180).

Separador
    Ponto e vírgula (`;`).

Cabeçalho
    A primeira linha é OBRIGATÓRIA e tem exatamente estes nomes, nesta ordem:

        codigo;nome;codigo_pai;analitica;tipo;natureza

Linhas de dados
    Cada linha seguinte é uma conta. Linha em branco é ignorada. Toda linha
    de dados tem EXATAMENTE seis campos, na ordem do cabeçalho.

Campos
    codigo      obrigatório. Texto de até 20 caracteres, único no arquivo e no
                cadastro da empresa. (O limite vem do cadastro: `Conta.codigo`.)
    nome        obrigatório. Texto de até 200 caracteres.
    codigo_pai  vazio = conta raiz do plano. Senão, o `codigo` de outra conta
                do arquivo ou já cadastrada na empresa.
    analitica   obrigatório. `S` = analítica (recebe lançamento);
                `N` = sintética (agrupa outras contas). Qualquer outro valor é erro.
    tipo        vazio, ou um dos valores de `TipoConta`:
                ativo | passivo | patrimonio_liquido | receita | despesa.
                Vazio = o tipo vem do pai, ou do prefixo informado na conferência
                (HI-87). Sem nenhum dos três, a linha é erro.
    natureza    vazio, ou `devedora` | `credora` (valores de `NaturezaConta`).
                Vazio = a natureza é presumida pelo tipo, com AVISO por conta,
                para o contador conferir as redutoras (HI-88).

Escape (RFC 4180, com `;` como separador)
    Campo que contenha `;`, aspas duplas, CR ou LF vai entre aspas duplas.
    Aspas duplas DENTRO de um campo entre aspas são escritas duas vezes (`""`).
    Campo sem nenhum desses caracteres pode vir com ou sem aspas. Aspas em
    campo que não começa com aspas, ou aspas sem fechamento, são erro de
    estrutura: a leitura para na linha e o erro diz qual.

Espaços
    Espaços nas extremidades de cada campo são descartados na leitura.

Exemplo
    codigo;nome;codigo_pai;analitica;tipo;natureza
    1;Ativo;;N;ativo;devedora
    1.1;"Caixa; bancos";1;N;;
    1.1.1;Caixa geral;1.1;A;;
    3;Receitas;;N;receita;credora

Erros de estrutura (nomeados, com linha)
    - Arquivo que não é UTF-8 válido: a leitura não avança.
    - Cabeçalho diferente do especificado: a leitura não avança.
    - Linha com número de campos diferente de seis.
    - Aspas malformadas: a leitura para na linha.

ESCRITA
-------
`escrever(contas, *, data_alteracao=None)` aceita `data_alteracao` por
uniformidade com a ECD; este formato não tem campo de data e ignora o
parâmetro. Nada é recusado por causa dele.
"""

import csv
import io

from apps.contabilidade.intercambio.canonico import (
    NIVEL_ERRO,
    ContaLida,
    IntercambioRecusado,
    Ocorrencia,
    ResultadoLeitura,
)
from apps.contabilidade.models import NaturezaConta, TipoConta

FORMATO = "proprio"

CABECALHO = ("codigo", "nome", "codigo_pai", "analitica", "tipo", "natureza")
TAMANHO_MAXIMO_CODIGO = 20  # Conta.codigo (max_length)
TAMANHO_MAXIMO_NOME = 200  # Conta.nome (max_length)

_TIPOS = frozenset(valor for valor, _rotulo in TipoConta.choices)
_NATUREZAS = frozenset(valor for valor, _rotulo in NaturezaConta.choices)
_SEPARADOR = ";"


class _ErroDeEstrutura(Exception):
    """Linha que não segue o escape da especificação. A leitura para nela."""

    def __init__(self, linha, mensagem):
        super().__init__(mensagem)
        self.linha = linha
        self.mensagem = mensagem


def _registros(texto):
    """Gera (número da linha, [campos]) para cada linha de `texto`.

    Leitor de estados próprio, e não o módulo `csv`, de propósito: o `csv` aceita
    aspas soltas no meio de campo sem reclamar, e a especificação do formato diz
    que isso é erro. Campo entre aspas pode ter `;`, quebra de linha e `""`
    (aspas escritas). Levanta `_ErroDeEstrutura` no primeiro problema; as linhas
    anteriores já foram geradas e são válidas.
    """
    n = len(texto)
    i = 0
    linha = 1
    while i < n:
        inicio = linha
        campos = []
        while True:
            if i < n and texto[i] == '"':
                i += 1
                buf = []
                while True:
                    if i >= n:
                        raise _ErroDeEstrutura(inicio, "aspas sem fechamento neste campo")
                    caractere = texto[i]
                    if caractere == '"':
                        if i + 1 < n and texto[i + 1] == '"':
                            buf.append('"')
                            i += 2
                            continue
                        i += 1
                        break
                    if caractere == "\n":
                        linha += 1
                    buf.append(caractere)
                    i += 1
                campos.append("".join(buf))
                if i < n and texto[i] not in ";\r\n":
                    raise _ErroDeEstrutura(
                        linha, "depois de campo entre aspas só pode vir ';' ou fim de linha"
                    )
            else:
                j = i
                while j < n and texto[j] not in ";\r\n":
                    j += 1
                bruto = texto[i:j]
                if '"' in bruto:
                    raise _ErroDeEstrutura(linha, "aspas em campo que não começa com aspas")
                campos.append(bruto)
                i = j

            if i >= n:
                break
            if texto[i] == _SEPARADOR:
                i += 1
                continue
            if texto.startswith("\r\n", i):
                i += 2
            elif texto[i] == "\n":
                i += 1
            else:
                raise _ErroDeEstrutura(linha, "retorno de carro sem avanço de linha")
            linha += 1
            break
        yield inicio, campos


def _dialeto():
    """Parâmetros do `csv` da ESCRITA: aspas em campo que tenha `;`, aspas, CR ou LF."""
    return {"delimiter": _SEPARADOR, "quotechar": '"', "doublequote": True}


def ler(conteudo: bytes) -> ResultadoLeitura:
    """Lê o formato próprio. Não levanta exceção por conteúdo ruim."""
    resultado = ResultadoLeitura(formato=FORMATO, codificacao="utf-8")
    ocorrencias = resultado.ocorrencias

    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        ocorrencias.append(
            Ocorrencia(
                0,
                "codificacao",
                NIVEL_ERRO,
                "o arquivo não está em UTF-8 válido. O formato próprio exige UTF-8.",
            )
        )
        resultado.codificacao = ""
        return resultado

    cabecalho_visto = False
    vistos = {}
    try:
        for numero, campos in _registros(texto):
            if not cabecalho_visto:
                cabecalho_visto = True
                cabecalho = tuple(valor.strip() for valor in campos)
                if cabecalho != CABECALHO:
                    ocorrencias.append(
                        Ocorrencia(
                            numero,
                            "cabecalho",
                            NIVEL_ERRO,
                            "o cabeçalho deve ser exatamente "
                            f"{_SEPARADOR.join(CABECALHO)}; veio "
                            f"{_SEPARADOR.join(cabecalho)}.",
                        )
                    )
                    return resultado
                continue
            if campos == [""]:
                continue  # linha em branco
            ocorrencias.extend(_ler_linha(numero, campos, vistos, resultado))
    except _ErroDeEstrutura as exc:
        ocorrencias.append(
            Ocorrencia(exc.linha, "estrutura", NIVEL_ERRO, f"{exc.mensagem}. A leitura parou aqui.")
        )

    if not cabecalho_visto:
        ocorrencias.append(
            Ocorrencia(1, "cabecalho", NIVEL_ERRO, "arquivo vazio: falta o cabeçalho.")
        )
    ocorrencias.sort(key=lambda o: (o.linha, o.campo))
    return resultado


def _ler_linha(numero, campos, vistos, resultado):
    """Interpreta uma linha de dados. Acrescenta a `resultado.contas` se for válida."""
    erros = []

    def recusar(campo, mensagem):
        erros.append(Ocorrencia(numero, campo, NIVEL_ERRO, mensagem))

    if len(campos) != len(CABECALHO):
        recusar(
            "estrutura",
            f"a linha tem {len(campos)} campos; o formato exige {len(CABECALHO)} "
            f"({_SEPARADOR.join(CABECALHO)}).",
        )
        return erros

    codigo, nome, codigo_pai, analitica, tipo, natureza = (valor.strip() for valor in campos)

    if not codigo:
        recusar("codigo", "código obrigatório.")
    elif len(codigo) > TAMANHO_MAXIMO_CODIGO:
        recusar(
            "codigo", f"código com {len(codigo)} caracteres; o máximo é {TAMANHO_MAXIMO_CODIGO}."
        )
    if not nome:
        recusar("nome", "nome obrigatório.")
    elif len(nome) > TAMANHO_MAXIMO_NOME:
        recusar("nome", f"nome com {len(nome)} caracteres; o máximo é {TAMANHO_MAXIMO_NOME}.")
    if analitica not in ("S", "N"):
        recusar("analitica", f"valor '{analitica}': use S (analítica) ou N (sintética).")
    if tipo and tipo not in _TIPOS:
        recusar("tipo", f"tipo '{tipo}' não existe. Valores: {', '.join(sorted(_TIPOS))}.")
    if natureza and natureza not in _NATUREZAS:
        recusar(
            "natureza",
            f"natureza '{natureza}' não existe. Valores: {', '.join(sorted(_NATUREZAS))}.",
        )

    if codigo and codigo in vistos:
        recusar(
            "codigo",
            f"código '{codigo}' repetido (primeira ocorrência na linha {vistos[codigo]}).",
        )
    if erros:
        return erros

    vistos[codigo] = numero
    resultado.contas.append(
        ContaLida(
            linha=numero,
            codigo=codigo,
            nome=nome,
            codigo_pai=codigo_pai or None,
            analitica=analitica == "S",
            tipo=tipo or None,
            natureza=natureza or None,
            codigo_origem=None,
            referencial=None,
        )
    )
    return erros


def escrever(contas, *, data_alteracao=None):
    """Escreve o formato próprio: UTF-8, sem BOM, CRLF, cabeçalho na primeira linha.

    `data_alteracao` é ignorado (ver docstring do módulo). Levanta
    `IntercambioRecusado` se algum campo não cabe no formato.
    """
    ocorrencias = []
    saida = io.StringIO(newline="")
    escritor = csv.writer(saida, lineterminator="\r\n", **_dialeto())
    escritor.writerow(CABECALHO)
    for conta in contas:
        if not conta.codigo or len(conta.codigo) > TAMANHO_MAXIMO_CODIGO:
            ocorrencias.append(
                Ocorrencia(conta.linha, "codigo", NIVEL_ERRO, "código vazio ou acima do limite.")
            )
            continue
        if not conta.nome or len(conta.nome) > TAMANHO_MAXIMO_NOME:
            ocorrencias.append(
                Ocorrencia(conta.linha, "nome", NIVEL_ERRO, f"nome de {conta.codigo} inválido.")
            )
            continue
        if conta.tipo is not None and conta.tipo not in _TIPOS:
            ocorrencias.append(
                Ocorrencia(conta.linha, "tipo", NIVEL_ERRO, f"tipo '{conta.tipo}' desconhecido.")
            )
            continue
        if conta.natureza is not None and conta.natureza not in _NATUREZAS:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "natureza",
                    NIVEL_ERRO,
                    f"natureza '{conta.natureza}' desconhecida.",
                )
            )
            continue
        escritor.writerow(
            [
                conta.codigo,
                conta.nome,
                conta.codigo_pai or "",
                "S" if conta.analitica else "N",
                conta.tipo or "",
                conta.natureza or "",
            ]
        )
    if ocorrencias:
        raise IntercambioRecusado(
            "O plano não cabe no formato próprio: "
            + "; ".join(f"linha {o.linha}, {o.campo}: {o.mensagem}" for o in ocorrencias),
            ocorrencias,
        )
    return saida.getvalue().encode("utf-8")
