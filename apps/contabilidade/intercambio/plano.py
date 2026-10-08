"""Conferência, aplicação e exportação do plano de contas (DL-077, fatia 1).

TRÊS OPERAÇÕES, E A SEPARAÇÃO É PROPOSITAL.

1. `conferir_plano` LÊ e decide. Não grava nada. Devolve a prévia: para cada
   conta, a ação (criar, atualizar, sem mudança, recusada), o tipo e a natureza
   FINAIS e de onde vieram, e as ocorrências com linha e campo.
2. `aplicar_plano` GRAVA, e só se a prévia não tiver erro. Antes de gravar,
   recalcula a conferência DENTRO de uma trava por empresa e compara com a
   prévia que o contador viu (SHA-256 do arquivo e assinatura do plano). Se o
   arquivo mudou, ou o cadastro mudou de forma que a conferência é outra, recusa.
   Tudo é um único `transaction.atomic()`: falha no meio desfaz o resto.
3. `exportar_plano` escreve o plano da empresa no formato pedido.

REGRAS DA FATIA 1 (plano DL-077, consulta do contador-senior de 08/10/2026).
- Políticas: `so_acrescentar` (padrão) e `acrescentar_e_atualizar_nome`.
  Nenhuma política apaga conta, e nenhuma muda tipo, natureza, conta superior
  ou caráter analítico de conta EXISTENTE. Só a segunda troca o NOME.
- Conta superior deve existir no arquivo ou no cadastro, e ser SINTÉTICA.
- Código repetido no arquivo: erro (a segunda ocorrência).
- Tipo, nesta ordem: o do arquivo; senão o da conta superior; senão o prefixo
  informado na prévia, o mais longo que casa com o código. Sem nenhum dos três:
  erro (HI-87). O produto não adivinha tipo.
  Quando o arquivo traz tipo e a conta superior tem outro: erro.
- Natureza, nesta ordem: a do arquivo; senão presumida pelo tipo (HI-88),
  com AVISO por conta, para o contador conferir as redutoras.
- Conta existente com tipo, natureza ou caráter analítico diferente do arquivo:
  erro. A conta superior diferente da cadastrada: erro.
- Plano referencial (I051) lido e não gravado: aviso. O DataLedger ainda não
  guarda o plano referencial nesta fatia.
- Arquivo sem nenhuma conta: erro.
- Documento (DL-077, B3): se o arquivo declara CNPJ/CPF (registro 0000), ele tem de ser
  o da empresa escolhida. Diferente: erro no nível do arquivo (linha 0), e nada é gravado.
  A conferência fica AQUI, no núcleo, para valer em qualquer porta que use o plano.
- Situação (DL-077, B4): conta nova inativa no arquivo nasce inativa. Conta existente
  mantém a situação do cadastro, nas duas políticas; divergência é aviso.
- Superior (A3): o leitor entrega o imediato e as superiores possíveis. Vale o MAIOR prefixo
  que exista no arquivo OU no cadastro, respeitando a fronteira de nível. Aviso quando não é
  o imediato.
- Profundidade (A8): cadeia de superiores do arquivo acima de 50 níveis é recusada.
- Teto (A6): mais de 5.000 contas numa importação é recusado (413, nomeado).
- Controle (A1): caractere de 00 a 31, ou 127, no código ou no nome é erro com linha e campo.
- Conta de resultado (A2): quando o formato marca COD_NAT 04, o tipo FINAL tem de ser receita
  ou despesa, seja de onde vier.
"""

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from django.db import transaction

from apps.auditoria.services import registrar
from apps.contabilidade.intercambio.canonico import (
    NIVEL_AVISO,
    NIVEL_ERRO,
    ContaLida,
    IntercambioRecusado,
    Ocorrencia,
    ResultadoLeitura,
)
from apps.contabilidade.intercambio.formatos import (
    AVISOS_DE_EXPORTACAO,
    ESCRITORES,
    FORMATOS_QUE_PRECISAM_DO_DOCUMENTO,
)
from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais, FormatoNaoSuportado
from apps.contabilidade.models import (
    NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO,
    Conta,
    ItemLancamento,
    TipoConta,
)
from apps.contabilidade.services import (
    ContaRecusadaNoCadastro,
    _travar_empresa_para_operacao_de_zeramento,
    criar_conta_pelo_plano,
    renomear_conta_pelo_plano,
)

POLITICA_SO_ACRESCENTAR = "so_acrescentar"
POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME = "acrescentar_e_atualizar_nome"
POLITICAS = (POLITICA_SO_ACRESCENTAR, POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME)

ACAO_CRIAR = "criar"
ACAO_ATUALIZAR = "atualizar"
ACAO_SEM_MUDANCA = "sem_mudanca"
ACAO_RECUSADA = "recusada"

ORIGEM_ARQUIVO = "arquivo"
ORIGEM_CONTA_SUPERIOR = "conta_superior"
ORIGEM_PREFIXO = "prefixo"
ORIGEM_CADASTRO = "cadastro"
ORIGEM_PRESUMIDA = "presumida_pelo_tipo"

FILTROS_DE_EXPORTACAO = ("todas", "analiticas", "com_movimento")

TAMANHO_MAXIMO_CODIGO = 20  # Conta.codigo
TAMANHO_MAXIMO_NOME = 200  # Conta.nome

# Teto de contas por importação (A6 da auditoria da DL-077). Acima disso a conferência e
# a aplicação levariam minutos e segurariam o lock da empresa; a recusa é nomeada. Um
# plano real cabe folgado: o limite é de operação, não de regra contábil.
MAXIMO_DE_CONTAS_POR_IMPORTACAO = 5_000

# Profundidade máxima da cadeia de superiores DENTRO do arquivo (A8). Acima disso o
# núcleo recusa a conta com erro nomeado, em vez de estourar a recursão do Python. A
# exportação em árvore também recursa, e este limite a mantém segura para o que se importa.
MAXIMO_DE_NIVEIS_DE_SUPERIOR = 50

# Tipo de conta de resultado (COD_NAT 04 da ECD): a mensagem nomeia o código do leiaute.
_ROTULO_DE_RESULTADO = "conta de resultado (COD_NAT 04)"


class ParametroInvalido(IntercambioRecusado):
    """Política, prefixo ou filtro fora do que a fatia aceita. A API responde 400."""


class PlanoRecusado(IntercambioRecusado):
    """O plano tem erro, ou o cadastro recusou alguma conta. Nada foi gravado."""


class ArquivoAlteradoDesdeAPrevia(IntercambioRecusado):
    """O SHA-256 do arquivo aplicado não é o da prévia. A API responde 409."""


class PlanoAlteradoDesdeAPrevia(IntercambioRecusado):
    """O arquivo é o mesmo, mas a conferência agora dá outro resultado (o cadastro
    mudou). A API responde 409. Quem vê isso confere a prévia de novo."""


@dataclass(frozen=True)
class ItemDoPlano:
    """O que a aplicação faria com UMA conta do arquivo, e por quê."""

    linha: int
    codigo: str
    nome: str
    codigo_pai: str | None
    analitica: bool
    acao: str
    tipo: str | None
    origem_tipo: str | None
    natureza: str | None
    origem_natureza: str | None
    ocorrencias: tuple[Ocorrencia, ...] = ()
    # Situação FINAL da conta depois da aplicação: True ativa, False inativa. Para conta
    # existente, é a do cadastro (a importação não muda a situação dela).
    ativa: bool | None = None


@dataclass(frozen=True)
class PreviaDoPlano:
    """Resultado de `conferir_plano`. Não grava nada; é o que o contador revisa."""

    resultado: ResultadoLeitura
    politica: str
    tipos_por_prefixo: tuple[tuple[str, str], ...]
    itens: tuple[ItemDoPlano, ...]
    ordem: tuple[str, ...]
    ocorrencias: tuple[Ocorrencia, ...]
    assinatura: str
    contagens: dict = field(default_factory=dict)

    @property
    def sha256(self):
        return self.resultado.sha256

    @property
    def tem_erro(self):
        return any(o.nivel == NIVEL_ERRO for o in self.ocorrencias)


@dataclass(frozen=True)
class ResultadoDaAplicacao:
    criadas: int
    atualizadas: int
    sem_mudanca: int
    sha256: str
    assinatura: str


@dataclass(frozen=True)
class ArquivoDoPlano:
    """Saída de `exportar_plano`. `sha256` é o do arquivo gerado (vai para a trilha)."""

    formato: str
    filtro: str
    conteudo: bytes
    sha256: str
    quantidade_contas: int
    sinteticas_incluidas: int
    # Avisos do formato sobre o arquivo gerado (ex.: código reduzido não estável). A
    # API os devolve no cabeçalho, e a trilha os registra.
    avisos: tuple[str, ...] = ()


# -----------------------------------------------------------------------------
# Parâmetros
# -----------------------------------------------------------------------------


def validar_politica(politica):
    if politica not in POLITICAS:
        raise ParametroInvalido(f"política '{politica}' não existe. Use: {', '.join(POLITICAS)}.")
    return politica


def validar_prefixos(tipos_por_prefixo):
    """Confere o mapa prefixo -> tipo da prévia. Devolve um dict limpo.

    O prefixo casa com o INÍCIO do código (`"3"` casa `"3.1.01"`). O tipo tem
    que ser um valor de `TipoConta`. Nenhum prefixo é aplicado por ordem de
    chegada: quem casa é sempre o mais longo.
    """
    if tipos_por_prefixo is None:
        return {}
    if not isinstance(tipos_por_prefixo, Mapping):
        raise ParametroInvalido("os prefixos devem ser um mapa prefixo -> tipo.")
    limpos = {}
    validos = set(TipoConta.values)
    for prefixo, tipo in tipos_por_prefixo.items():
        if not isinstance(prefixo, str) or not prefixo.strip():
            raise ParametroInvalido("prefixo vazio: informe o começo do código da conta.")
        if tipo not in validos:
            raise ParametroInvalido(
                f"o tipo '{tipo}' do prefixo '{prefixo}' não existe. "
                f"Use: {', '.join(sorted(validos))}."
            )
        limpos[prefixo.strip()] = tipo
    return limpos


def _prefixo_que_casa(codigo, tipos):
    candidatos = [prefixo for prefixo in tipos if codigo.startswith(prefixo)]
    return max(candidatos, key=len) if candidatos else None


def _natureza_presumida(tipo):
    """Natureza que o tipo carrega (HI-88). Mesma fonte do balanço (models)."""
    return NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO[TipoConta(tipo)].value


def _tem_controle(texto):
    """Caractere de controle (00-31 e 127) no código ou no nome (A1).

    NUL e os demais controles não cabem no PostgreSQL (NUL falha com 500 na gravação) e
    quebram os leiautes de texto. Vale para TODOS os formatos porque a conferência é do
    núcleo; o leitor da ECD e o da referência também recusam, mas por defesa em profundidade
    o núcleo confere de novo.
    """
    return any(ord(caractere) < 32 or ord(caractere) == 127 for caractere in texto)


def _documento_canonico(texto):
    """CNPJ (inclusive alfanumérico, RC-46) ou CPF, na forma canônica: maiúsculas, sem máscara.

    Não pode usar `\\D`: o CNPJ alfanumérico tem letras (RC-46, em vigor desde 31/07/2026),
    e apagá-las faria duas empresas diferentes parecerem a mesma. Vazio se não há documento.
    """
    return re.sub(r"[^0-9A-Z]", "", (texto or "").upper())


# -----------------------------------------------------------------------------
# Conferência
# -----------------------------------------------------------------------------


@dataclass
class _Resolucao:
    item: ItemDoPlano
    tipo: str | None
    natureza: str | None
    analitica: bool
    erro: bool


class _Conferencia:
    """Resolve cada conta do arquivo, com a conta superior antes da filha.

    `em_curso` detecta ciclo na própria recursão. `memo` evita refazer conta já
    resolvida. `ordem` guarda a ordem em que as contas ficaram prontas, que é a
    ordem segura de criação: a superior sempre antes da filha.
    """

    def __init__(self, resultado, banco, politica, tipos):
        self.arquivo = {}
        for conta in resultado.contas:
            if conta.codigo and conta.codigo not in self.arquivo:
                self.arquivo[conta.codigo] = conta
        self.banco = banco
        self.politica = politica
        self.tipos = tipos
        self.memo = {}
        self.ordem = []
        # Aviso de superior escolhida por prefixo (A3), por código da conta.
        self.avisos_de_pai = {}
        codigos = set(self.arquivo)
        self.arquivo = {
            codigo: self._escolher_superior(conta, codigos)
            for codigo, conta in self.arquivo.items()
        }

    def _escolher_superior(self, conta, codigos_do_arquivo):
        """Escolhe a conta superior entre os prefixos candidatos (A3).

        O leitor entrega a classificação e as superiores POSSÍVEIS, da mais próxima para a
        mais distante. Vale a primeira que exista no arquivo OU no cadastro: é o maior prefixo
        existente, e o corte respeita a fronteira de nível (feita pelo leitor). Se nenhuma
        existe, fica o imediato, e a resolução recusa com "não está no arquivo nem no cadastro".
        Escolher o imediato sem olhar o cadastro foi o defeito: a conta caía na superior errada
        em silêncio, com efeito em nível, balancete por nível e DRE.
        """
        candidatas = conta.superiores_candidatas
        if not candidatas:
            return conta
        escolhida = next(
            (c for c in candidatas if c in codigos_do_arquivo or c in self.banco), None
        )
        if escolhida is None:
            return conta
        if escolhida != candidatas[0]:
            self.avisos_de_pai[conta.codigo] = Ocorrencia(
                conta.linha,
                "codigo_pai",
                NIVEL_AVISO,
                f"superior '{escolhida}' escolhida pelo maior prefixo existente: o prefixo "
                f"imediato '{candidatas[0]}' não existe no arquivo nem no cadastro. Confira a "
                "hierarquia.",
            )
        return replace(conta, codigo_pai=escolhida)

    def _altura_da_cadeia(self, codigo):
        """Quantas superiores DO ARQUIVO a conta tem, até o topo ou até o limite (A8).

        Sem recursão e sem memo: a altura não depende da ordem em que as contas são
        resolvidas. Para no limite, então custa no máximo MAXIMO_DE_NIVEIS_DE_SUPERIOR + 1 passos.
        """
        altura = 0
        visitados = {codigo}
        atual = self.arquivo[codigo].codigo_pai
        while (
            atual in self.arquivo
            and atual not in visitados
            and altura <= MAXIMO_DE_NIVEIS_DE_SUPERIOR
        ):
            visitados.add(atual)
            altura += 1
            atual = self.arquivo[atual].codigo_pai
        return altura

    def resolver(self, codigo, em_curso=frozenset()):
        if codigo in self.memo:
            return self.memo[codigo]
        conta = self.arquivo[codigo]
        ocorrencias = []

        def erro(campo, mensagem):
            ocorrencias.append(Ocorrencia(conta.linha, campo, NIVEL_ERRO, mensagem))

        def aviso(campo, mensagem):
            ocorrencias.append(Ocorrencia(conta.linha, campo, NIVEL_AVISO, mensagem))

        if codigo in self.avisos_de_pai:
            ocorrencias.append(self.avisos_de_pai[codigo])

        if not conta.nome.strip():
            erro("nome", "nome obrigatório.")
        elif len(conta.nome) > TAMANHO_MAXIMO_NOME:
            erro(
                "nome", f"nome com {len(conta.nome)} caracteres; o máximo é {TAMANHO_MAXIMO_NOME}."
            )
        if len(codigo) > TAMANHO_MAXIMO_CODIGO:
            erro(
                "codigo",
                f"código com {len(codigo)} caracteres; o máximo é {TAMANHO_MAXIMO_CODIGO}.",
            )
        # A1: NUL e controles entram no banco e quebram a exportação dos leiautes de texto.
        for campo, valor in (("codigo", codigo), ("nome", conta.nome)):
            if _tem_controle(valor):
                erro(campo, f"{campo} com caractere de controle (00 a 31, ou 127), não permitido.")

        # Conta superior (p. ex. ECD COD_CTA_SUP): precisa existir e ser sintética.
        pai_tipo = None
        pai_analitica = None
        if conta.codigo_pai is not None and self._altura_da_cadeia(codigo) > (
            MAXIMO_DE_NIVEIS_DE_SUPERIOR
        ):
            # A8: cadeia acima do limite. Não recursa: a conta é recusada aqui, e as
            # filhas dela herdam o erro pela regra "superior tem erro" abaixo.
            erro(
                "codigo_pai",
                f"a cadeia de superiores de {codigo} passa de {MAXIMO_DE_NIVEIS_DE_SUPERIOR} "
                "níveis dentro do arquivo. Hierarquia tão funda não é aceita; reorganize o plano.",
            )
        elif conta.codigo_pai is not None:
            if conta.codigo_pai == codigo or conta.codigo_pai in em_curso:
                erro(
                    "codigo_pai", f"a conta superior {conta.codigo_pai} forma ciclo na hierarquia."
                )
            elif conta.codigo_pai in self.arquivo:
                pai = self.resolver(conta.codigo_pai, em_curso | {codigo})
                if pai.erro:
                    erro(
                        "codigo_pai",
                        f"a conta superior {conta.codigo_pai} tem erro "
                        f"(linha {self.arquivo[conta.codigo_pai].linha}). Corrija-a antes.",
                    )
                pai_tipo = pai.tipo
                pai_analitica = pai.analitica
            elif conta.codigo_pai in self.banco:
                cadastrada = self.banco[conta.codigo_pai]
                pai_tipo = cadastrada.tipo
                pai_analitica = cadastrada.aceita_lancamento
            else:
                erro(
                    "codigo_pai",
                    f"a conta superior {conta.codigo_pai} não está no arquivo nem no cadastro "
                    "da empresa.",
                )
            if pai_analitica:
                erro(
                    "codigo_pai",
                    f"a conta superior {conta.codigo_pai} é analítica, e só conta sintética "
                    "recebe filha (REGRA_CONTA_NIVEL_SUPERIOR_NAO_SINTETICA, ECD p. 120).",
                )

        tipo = natureza = origem_tipo = origem_natureza = None
        prefixo_usado = None
        acao = ACAO_CRIAR
        ativa = None

        if codigo in self.banco:
            cadastrada = self.banco[codigo]
            acao = ACAO_SEM_MUDANCA
            tipo, origem_tipo = cadastrada.tipo, ORIGEM_CADASTRO
            natureza, origem_natureza = cadastrada.natureza, ORIGEM_CADASTRO
            # Situação: a da conta existente é a que vale, nas duas políticas. Se o
            # arquivo diz outra, é aviso (o contador vê e decide no cadastro).
            ativa = cadastrada.ativo
            if conta.ativa is not None and conta.ativa != cadastrada.ativo:
                aviso(
                    "ativa",
                    "a situação no arquivo difere da cadastrada; a conta mantém a situação "
                    "atual. A importação não altera situação de conta existente.",
                )
            if conta.tipo is not None and conta.tipo != cadastrada.tipo:
                erro(
                    "tipo",
                    f"o arquivo diz '{conta.tipo}', e a conta está cadastrada como "
                    f"'{cadastrada.tipo}'. O produto não altera tipo de conta existente.",
                )
            if conta.natureza is not None and conta.natureza != cadastrada.natureza:
                erro(
                    "natureza",
                    f"o arquivo diz '{conta.natureza}', e a conta está cadastrada como "
                    f"'{cadastrada.natureza}'. O produto não altera natureza de conta existente.",
                )
            if conta.analitica != cadastrada.aceita_lancamento:
                erro(
                    "analitica",
                    "a conta está cadastrada como "
                    f"{'analítica' if cadastrada.aceita_lancamento else 'sintética'}, e o "
                    "arquivo diz o contrário. O produto não altera isso em conta existente.",
                )
            superior_cadastrada = (
                cadastrada.conta_pai.codigo if cadastrada.conta_pai_id is not None else None
            )
            if conta.codigo_pai != superior_cadastrada:
                erro(
                    "codigo_pai",
                    f"a conta superior no arquivo ({conta.codigo_pai or 'raiz'}) difere da "
                    f"cadastrada ({superior_cadastrada or 'raiz'}). O produto não reestrutura "
                    "conta existente.",
                )
            if conta.nome != cadastrada.nome:
                if self.politica == POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME:
                    acao = ACAO_ATUALIZAR
                else:
                    aviso(
                        "nome",
                        f"o arquivo traz '{conta.nome}'; mantido o cadastrado "
                        f"'{cadastrada.nome}' (política só acrescentar).",
                    )
        else:
            # Conta nova nasce conforme o arquivo: inativa só se ele disser inativa. Sem
            # situação no formato (ECD, próprio), nasce ativa, como toda conta nova.
            ativa = conta.ativa is not False
            if conta.tipo is not None:
                tipo, origem_tipo = conta.tipo, ORIGEM_ARQUIVO
                if pai_tipo is not None and pai_tipo != conta.tipo:
                    erro(
                        "tipo",
                        f"tipo '{conta.tipo}' é incompatível com o da conta superior "
                        f"('{pai_tipo}').",
                    )
            elif pai_tipo is not None:
                tipo, origem_tipo = pai_tipo, ORIGEM_CONTA_SUPERIOR
            else:
                prefixo = _prefixo_que_casa(codigo, self.tipos)
                prefixo_usado = prefixo
                if prefixo is not None:
                    tipo, origem_tipo = self.tipos[prefixo], ORIGEM_PREFIXO
                else:
                    erro(
                        "tipo",
                        "sem tipo: o arquivo não diz, a conta superior não tem tipo, e nenhum "
                        "prefixo informado casa com este código. Informe o prefixo na prévia "
                        "(ex.: 3 para receita). O produto não adivinha tipo (HI-87).",
                    )

            if conta.natureza is not None:
                natureza, origem_natureza = conta.natureza, ORIGEM_ARQUIVO
            elif tipo is not None:
                natureza, origem_natureza = _natureza_presumida(tipo), ORIGEM_PRESUMIDA
                aviso(
                    "natureza",
                    f"natureza '{natureza}' presumida pelo tipo '{tipo}' (o arquivo não diz). "
                    "Confira: contas redutoras, como depreciação acumulada no ativo, são "
                    "credoras (HI-88).",
                )

        # A2: conta de resultado (COD_NAT 04) só aceita receita ou despesa. Vale para o tipo
        # FINAL, qualquer que seja a origem: arquivo, superior, prefixo ou cadastro. Sem isto,
        # uma conta de resultado herdava "ativo" da superior e caía no Balanço, sem erro.
        if tipo is not None and conta.tipos_aceitos is not None and tipo not in conta.tipos_aceitos:
            if origem_tipo == ORIGEM_CONTA_SUPERIOR:
                motivo = (
                    f"não pode herdar '{tipo}' da conta superior; informe receita ou despesa "
                    "por prefixo"
                )
            elif origem_tipo == ORIGEM_PREFIXO:
                motivo = (
                    f"não pode ter tipo '{tipo}' pelo prefixo '{prefixo_usado}'; informe receita "
                    "ou despesa por prefixo"
                )
            elif origem_tipo == ORIGEM_CADASTRO:
                motivo = (
                    f"está cadastrada como '{tipo}', e o arquivo diz resultado. O produto não "
                    "altera tipo de conta existente"
                )
            else:
                motivo = f"não pode ter o tipo '{tipo}' do arquivo; informe receita ou despesa"
            erro("tipo", f"{_ROTULO_DE_RESULTADO} {motivo}")

        if conta.referencial is not None:
            aviso(
                "referencial",
                "plano referencial lido, mas o DataLedger ainda não guarda o plano referencial "
                "nesta fatia: não foi gravado.",
            )

        tem_erro = any(o.nivel == NIVEL_ERRO for o in ocorrencias)
        if tem_erro:
            acao = ACAO_RECUSADA
        item = ItemDoPlano(
            linha=conta.linha,
            codigo=codigo,
            nome=conta.nome,
            codigo_pai=conta.codigo_pai,
            analitica=conta.analitica,
            acao=acao,
            tipo=tipo,
            origem_tipo=origem_tipo,
            natureza=natureza,
            origem_natureza=origem_natureza,
            ocorrencias=tuple(ocorrencias),
            ativa=ativa,
        )
        resolucao = _Resolucao(
            item=item,
            tipo=tipo,
            natureza=natureza,
            analitica=conta.analitica,
            erro=tem_erro,
        )
        self.memo[codigo] = resolucao
        self.ordem.append(codigo)
        return resolucao


def _documento_da_empresa(empresa):
    """CNPJ, ou CPF para empresa de pessoa física, na forma canônica. Vazio se não há."""
    return _documento_canonico(empresa.cnpj or empresa.cpf or "")


def _assinatura(itens):
    """SHA-256 do plano conferido: o que o contador revisou, em forma canônica.

    JSON com a lista ordenada, para que nome com `|` ou quebra de linha não
    produza a mesma assinatura por acidente.
    """
    linhas = sorted(
        [
            item.codigo,
            item.acao,
            item.tipo or "",
            item.natureza or "",
            item.codigo_pai or "",
            "A" if item.analitica else "S",
            "" if item.ativa is None else ("A" if item.ativa else "I"),
            item.nome,
        ]
        for item in itens
    )
    return hashlib.sha256(json.dumps(linhas, ensure_ascii=False).encode("utf-8")).hexdigest()


def conferir_plano(empresa, resultado, politica, tipos_por_prefixo=None):
    """Confere o plano lido contra o cadastro da empresa. Não grava nada.

    `resultado` é o `ResultadoLeitura` de um leitor (ver `leitura.ler_arquivo`).
    `tipos_por_prefixo` é o mapa prefixo -> tipo que o contador informou na
    prévia (p. ex. `{"3": "receita", "4": "despesa"}`).
    """
    politica = validar_politica(politica)
    tipos = validar_prefixos(tipos_por_prefixo)
    # A6: o teto vem antes de qualquer conferência cara. Recusa nomeada (413 na API).
    if len(resultado.contas) > MAXIMO_DE_CONTAS_POR_IMPORTACAO:
        raise ArquivoGrandeDemais(
            f"o arquivo traz {len(resultado.contas)} contas; o limite por importação é "
            f"{MAXIMO_DE_CONTAS_POR_IMPORTACAO}. Divida o plano em partes."
        )
    banco = {
        conta.codigo: conta
        for conta in Conta.objects.filter(empresa=empresa).select_related("conta_pai")
    }

    conferencia = _Conferencia(resultado, banco, politica, tipos)
    itens = []
    primeira_linha = {}
    for conta in resultado.contas:
        if not conta.codigo:
            itens.append(
                ItemDoPlano(
                    linha=conta.linha,
                    codigo=conta.codigo,
                    nome=conta.nome,
                    codigo_pai=conta.codigo_pai,
                    analitica=conta.analitica,
                    acao=ACAO_RECUSADA,
                    tipo=None,
                    origem_tipo=None,
                    natureza=None,
                    origem_natureza=None,
                    ocorrencias=(
                        Ocorrencia(conta.linha, "codigo", NIVEL_ERRO, "código obrigatório."),
                    ),
                )
            )
            continue
        if conta.codigo in primeira_linha:
            itens.append(
                ItemDoPlano(
                    linha=conta.linha,
                    codigo=conta.codigo,
                    nome=conta.nome,
                    codigo_pai=conta.codigo_pai,
                    analitica=conta.analitica,
                    acao=ACAO_RECUSADA,
                    tipo=None,
                    origem_tipo=None,
                    natureza=None,
                    origem_natureza=None,
                    ocorrencias=(
                        Ocorrencia(
                            conta.linha,
                            "codigo",
                            NIVEL_ERRO,
                            f"código '{conta.codigo}' repetido no arquivo (primeira ocorrência "
                            f"na linha {primeira_linha[conta.codigo]}).",
                        ),
                    ),
                )
            )
            continue
        primeira_linha[conta.codigo] = conta.linha
        itens.append(conferencia.resolver(conta.codigo).item)

    # A12: "nenhuma conta" só quando não há erro de linha. Com erro de linha, o contador já
    # vê o motivo na linha; a frase extra era duplicata.
    ocorrencias_do_arquivo = []
    if not resultado.contas and not resultado.tem_erro:
        ocorrencias_do_arquivo.append(
            Ocorrencia(0, "arquivo", NIVEL_ERRO, "o arquivo não traz nenhuma conta do plano.")
        )

    contagens = {
        "criar": sum(1 for i in itens if i.acao == ACAO_CRIAR),
        "atualizar": sum(1 for i in itens if i.acao == ACAO_ATUALIZAR),
        "sem_mudanca": sum(1 for i in itens if i.acao == ACAO_SEM_MUDANCA),
        "recusada": sum(1 for i in itens if i.acao == ACAO_RECUSADA),
    }
    # A12: a importação não grava classificação de balanço, DRE, DLPA, DMPL nem DFC. Quem
    # confere a prévia precisa saber que essas contas nascem sem classificação.
    if contagens["criar"]:
        ocorrencias_do_arquivo.append(
            Ocorrencia(
                0,
                "classificacao",
                NIVEL_AVISO,
                f"{contagens['criar']} conta(s) nova(s) serão criadas sem classificação de "
                "balanço, DRE, DLPA, DMPL nem DFC: classifique depois no plano de contas.",
            )
        )

    # Conferência da empresa (isolamento entre empresas): o documento que o PRÓPRIO arquivo
    # declara tem de ser o da empresa escolhida. Quando o arquivo não declara (None), não há
    # o que comparar aqui; o aviso de "empresa não conferida" vem do leitor. A comparação é
    # na forma canônica (RC-46: CNPJ alfanumérico). A mensagem não repete os números.
    ocorrencias_do_documento = []
    if resultado.documento_declarado is not None and (
        resultado.documento_declarado != _documento_da_empresa(empresa)
    ):
        ocorrencias_do_documento.append(
            Ocorrencia(
                0,
                "documento",
                NIVEL_ERRO,
                "o arquivo não é da empresa escolhida: o CNPJ/CPF que ele declara é outro. "
                "Nada foi gravado.",
            )
        )

    ocorrencias = sorted(
        [
            *resultado.ocorrencias,
            *ocorrencias_do_arquivo,
            *ocorrencias_do_documento,
            *(o for item in itens for o in item.ocorrencias),
        ],
        key=lambda o: (o.linha, o.campo),
    )
    return PreviaDoPlano(
        resultado=resultado,
        politica=politica,
        tipos_por_prefixo=tuple(sorted(tipos.items())),
        itens=tuple(itens),
        ordem=tuple(conferencia.ordem),
        ocorrencias=tuple(ocorrencias),
        assinatura=_assinatura(itens),
        contagens=contagens,
    )


# -----------------------------------------------------------------------------
# Aplicação
# -----------------------------------------------------------------------------


def aplicar_plano(empresa, previa, usuario, request=None, *, sha256_esperado, assinatura_esperada):
    """Grava o plano conferido, de forma atômica, só se não houver erro.

    `previa` é a prévia de `conferir_plano` calculada sobre o arquivo que chegou
    AGORA. `sha256_esperado` e `assinatura_esperada` são o que o contador viu
    na prévia: se qualquer um for diferente, recusa (arquivo mudou, ou a
    conferência de agora não é a que foi revisada).

    Dentro da trava da empresa, a conferência é refeita e comparada com
    `assinatura_esperada`. Só então grava. Erro em qualquer conta desfaz tudo.
    """
    if previa.sha256 != sha256_esperado:
        raise ArquivoAlteradoDesdeAPrevia(
            "o arquivo enviado não é o que foi conferido na prévia. Refaça a conferência."
        )
    if previa.tem_erro:
        raise PlanoRecusado(
            "o plano tem erro. Nada foi gravado: corrija o arquivo e confira de novo.",
            [o for o in previa.ocorrencias if o.nivel == NIVEL_ERRO],
        )

    with transaction.atomic():
        # ATENÇÃO: o nome da função diz "zeramento", mas a trava é POR EMPRESA e
        # compartilhada por todas as operações que mudam o cadastro da empresa
        # (zeramento, parâmetro contábil e esta aplicação do plano). Reusada aqui
        # por decisão do arquiteto-senior (DL-077). Ela impede que duas operações
        # da mesma empresa conferiam contra um cadastro que a outra está mudando.
        _travar_empresa_para_operacao_de_zeramento(empresa)
        fresca = conferir_plano(
            empresa, previa.resultado, previa.politica, dict(previa.tipos_por_prefixo)
        )
        if fresca.assinatura != assinatura_esperada:
            raise PlanoAlteradoDesdeAPrevia(
                "o cadastro mudou desde a prévia e o resultado agora é outro. "
                "Nada foi gravado: confira o plano de novo."
            )
        if fresca.tem_erro:
            raise PlanoRecusado(
                "o plano tem erro frente ao cadastro atual. Nada foi gravado.",
                [o for o in fresca.ocorrencias if o.nivel == NIVEL_ERRO],
            )

        por_codigo = {item.codigo: item for item in fresca.itens}
        # A6: as contas da empresa são lidas UMA vez. Cada conta criada entra no mapa, e a
        # superior de cada conta nova sai daqui, em vez de uma consulta por conta.
        existentes = {conta.codigo: conta for conta in Conta.objects.filter(empresa=empresa)}
        criadas = atualizadas = inativas_criadas = 0
        for codigo in fresca.ordem:
            item = por_codigo[codigo]
            try:
                if item.acao == ACAO_CRIAR:
                    conta_criada = criar_conta_pelo_plano(
                        empresa=empresa,
                        codigo=item.codigo,
                        nome=item.nome,
                        tipo=item.tipo,
                        natureza=item.natureza,
                        codigo_pai=item.codigo_pai,
                        analitica=item.analitica,
                        usuario=usuario,
                        request=request,
                        pai=existentes.get(item.codigo_pai) if item.codigo_pai else None,
                    )
                    existentes[conta_criada.codigo] = conta_criada
                    criadas += 1
                    if item.ativa is False:
                        # A situação não é argumento de `criar_conta_pelo_plano`; grava-se
                        # logo depois, na mesma transação. A trilha do plano registra a
                        # quantidade de inativas criadas.
                        conta_criada.ativo = False
                        conta_criada.save(update_fields=["ativo"])
                        inativas_criadas += 1
                elif item.acao == ACAO_ATUALIZAR:
                    conta = Conta.objects.get(empresa=empresa, codigo=item.codigo)
                    renomear_conta_pelo_plano(
                        conta=conta, nome=item.nome, usuario=usuario, request=request
                    )
                    atualizadas += 1
            except ContaRecusadaNoCadastro as exc:
                raise PlanoRecusado(
                    f"o cadastro recusou a conta {item.codigo} (linha {item.linha}). "
                    "Nada foi gravado.",
                    [Ocorrencia(item.linha, "codigo", NIVEL_ERRO, m) for m in exc.mensagens],
                ) from exc

        sem_mudanca = fresca.contagens["sem_mudanca"]
        registrar(
            acao="plano_de_contas.importado",
            objeto=empresa,
            escritorio=empresa.escritorio,
            usuario=usuario,
            request=request,
            detalhes={
                "formato": fresca.resultado.formato,
                "politica": fresca.politica,
                # A12: o mapa de prefixos que decidiu os tipos vai para a trilha, para a
                # aplicação poder ser reconstituída sem a prévia.
                "prefixos": dict(fresca.tipos_por_prefixo),
                "nome_arquivo": fresca.resultado.nome_arquivo,
                "sha256": fresca.sha256,
                "assinatura": fresca.assinatura,
                "criadas": criadas,
                "inativas_criadas": inativas_criadas,
                "atualizadas": atualizadas,
                "sem_mudanca": sem_mudanca,
                "registros_ignorados": dict(fresca.resultado.registros_ignorados),
            },
        )

    return ResultadoDaAplicacao(
        criadas=criadas,
        atualizadas=atualizadas,
        sem_mudanca=sem_mudanca,
        sha256=fresca.sha256,
        assinatura=fresca.assinatura,
    )


# -----------------------------------------------------------------------------
# Exportação
# -----------------------------------------------------------------------------


def _ordenar_em_arvore(contas):
    """Ordem de saída: cada conta logo depois da sua superior, irmãs por código.

    Conta cuja superior não está na lista sai como raiz, e conta em ciclo sai
    no fim, sem ordem: o escritor é quem recusa o ciclo.
    """
    por_codigo = {conta.codigo: conta for conta in contas}
    filhas = defaultdict(list)
    raizes = []
    for conta in contas:
        if conta.codigo_pai is None or conta.codigo_pai not in por_codigo:
            raizes.append(conta)
        else:
            filhas[conta.codigo_pai].append(conta)

    saida = []
    visitadas = set()

    def visitar(conta):
        if conta.codigo in visitadas:
            return
        visitadas.add(conta.codigo)
        saida.append(conta)
        for filha in sorted(filhas[conta.codigo], key=lambda c: c.codigo):
            visitar(filha)

    for raiz in sorted(raizes, key=lambda c: c.codigo):
        visitar(raiz)
    saida.extend(conta for conta in contas if conta.codigo not in visitadas)
    return saida


def exportar_plano(*, empresa, formato, filtro="todas", inicio=None, fim=None, data_alteracao=None):
    """Gera o arquivo do plano da `empresa` no `formato`, com o `filtro` pedido.

    Filtros:
    - `todas`: todo o plano.
    - `analiticas`: só as analíticas, MAIS as sintéticas que elas precisam como
      conta superior. Sem elas, o arquivo não se reimporta (a conta superior
      precisa existir, ECD p. 118-120).
    - `com_movimento`: contas com partida entre `inicio` e `fim` (datas
      inclusive), MAIS suas superiores, pelo mesmo motivo.

    Isolamento: toda consulta é filtrada por `empresa`. Nunca se lê conta de
    outra empresa, nem para achar superior.
    """
    if formato not in ESCRITORES:
        raise FormatoNaoSuportado(
            f"formato '{formato}' não suportado para exportação. "
            f"Use: {', '.join(sorted(ESCRITORES))}."
        )
    if filtro not in FILTROS_DE_EXPORTACAO:
        raise ParametroInvalido(
            f"filtro '{filtro}' não existe. Use: {', '.join(FILTROS_DE_EXPORTACAO)}."
        )
    if filtro == "com_movimento":
        if inicio is None or fim is None:
            raise ParametroInvalido("o filtro com movimento exige o período (início e fim).")
        if inicio > fim:
            raise ParametroInvalido("o início do período é posterior ao fim.")

    contas = list(Conta.objects.filter(empresa=empresa).select_related("conta_pai"))
    por_id = {conta.id: conta for conta in contas}

    if filtro == "todas":
        escolhidas = set(por_id)
    elif filtro == "analiticas":
        escolhidas = {conta.id for conta in contas if conta.aceita_lancamento}
    else:
        com_movimento = set(
            ItemLancamento.objects.filter(
                lancamento__empresa=empresa,
                lancamento__data__gte=inicio,
                lancamento__data__lte=fim,
            ).values_list("conta_id", flat=True)
        )
        escolhidas = com_movimento & set(por_id)

    incluidas = set(escolhidas)
    for conta_id in escolhidas:
        atual = por_id[conta_id].conta_pai_id
        while atual is not None and atual in por_id and atual not in incluidas:
            incluidas.add(atual)
            atual = por_id[atual].conta_pai_id
    sinteticas_incluidas = len(incluidas - escolhidas)

    registros = [
        ContaLida(
            linha=0,
            codigo=conta.codigo,
            nome=conta.nome,
            codigo_pai=conta.conta_pai.codigo if conta.conta_pai_id is not None else None,
            analitica=conta.aceita_lancamento,
            tipo=conta.tipo,
            natureza=conta.natureza,
            codigo_origem=None,
            referencial=None,
            ativa=conta.ativo,
        )
        for conta in (por_id[i] for i in incluidas)
    ]
    registros = _ordenar_em_arvore(registros)

    # O documento (registro 0000) só vai aos escritores que o pedem: os demais não
    # aceitam o argumento. Vem do próprio cadastro da empresa, nunca de parâmetro da API.
    argumentos = {"data_alteracao": data_alteracao}
    if formato in FORMATOS_QUE_PRECISAM_DO_DOCUMENTO:
        argumentos["documento"] = _documento_da_empresa(empresa) or None
    conteudo = ESCRITORES[formato](registros, **argumentos)
    return ArquivoDoPlano(
        formato=formato,
        filtro=filtro,
        conteudo=conteudo,
        sha256=hashlib.sha256(conteudo).hexdigest(),
        quantidade_contas=len(registros),
        sinteticas_incluidas=sinteticas_incluidas,
        avisos=tuple(AVISOS_DE_EXPORTACAO.get(formato, ())),
    )
