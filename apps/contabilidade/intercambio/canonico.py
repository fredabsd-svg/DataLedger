"""Registros neutros do núcleo de intercâmbio contábil (DL-077, fatia 1).

ESTE MÓDULO É O CONTRATO entre os formatos (leitores e escritores) e o núcleo
(`plano.py`). A frente B (leitores do sistema de referência e do Excel) é
implementada CONTRA estes mesmos dataclasses: um leitor novo recebe os bytes
do arquivo e devolve um `ResultadoLeitura`, sem gravar nada e sem saber da
conferência nem da aplicação. Mudar um campo obrigatório aqui quebra a frente
B; acrescentar um campo com valor padrão não quebra.

Convenções que valem para todos os formatos:

- `linha` é o número da linha de origem, começando em 1. Ocorrência sobre o
  ARQUIVO INTEIRO (ex.: codificação) usa `linha=0`.
- Valor monetário é `Decimal`, nunca `float`.
- Um campo que o formato NÃO diz vem como `None`, nunca como palpite. Ex.: a
  ECD não traz natureza (HI-88), então `natureza=None`; o COD_NAT 04 não separa
  receita de despesa (HI-87), então `tipo=None`. Quem decide o que fazer com
  o `None` é o núcleo (`plano.py`), que o registra como ocorrência.
- Um leitor NÃO levanta exceção por conteúdo ruim: registra `Ocorrencia` com
  nível `erro` e segue. Um registro com erro não entra em `contas`/`lancamentos`.
  Exceção só para o que impede a leitura inteira (ver `leitura.py`).
- Um escritor RECUSA (levanta `IntercambioRecusado`) o que não consegue
  representar no leiaute. Nunca substitui caractere em silêncio.

Frente B: o que o leitor precisa devolver para o núcleo funcionar —
- `ContaLida.codigo` é a chave do plano no formato de origem. Quando o formato
  traz outro código para a mesma conta (p.ex. o código reduzido do sistema de
  referência), ele vai em `codigo_origem`; o `codigo` continua sendo o código
  da conta no DataLedger (o mesmo que o de-para resolverá).
- `codigo_pai` referencia um `codigo` do MESMO arquivo ou do cadastro. Um leitor
  não precisa conhecer o cadastro; o núcleo confere.
- `analitica` é `True` quando a conta recebe lançamento (o que a ECD chama de
  IND_CTA = A, e o formato próprio chama de analitica = S).
- `tipo` e `natureza` usam os valores de `TipoConta` e `NaturezaConta`
  ("ativo", "passivo", "patrimonio_liquido", "receita", "despesa";
  "devedora", "credora"). Vazio quando o formato não diz.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

NIVEL_ERRO = "erro"
NIVEL_AVISO = "aviso"
NIVEIS_DE_OCORRENCIA = (NIVEL_ERRO, NIVEL_AVISO)

LADO_DEBITO = "debito"
LADO_CREDITO = "credito"


@dataclass(frozen=True)
class Ocorrencia:
    """Algo que o leitor ou o núcleo achou no arquivo, com linha e campo.

    `nivel` é `erro` (impede a gravação de tudo) ou `aviso` (grava, mas o
    contador precisa ver). Não existe um terceiro nível: o que não impede nem
    merece atenção não vira ocorrência.
    """

    linha: int
    campo: str
    nivel: str
    mensagem: str

    def __post_init__(self):
        if self.nivel not in NIVEIS_DE_OCORRENCIA:
            raise ValueError(f"nível de ocorrência desconhecido: {self.nivel!r}")


@dataclass(frozen=True)
class ContaLida:
    """Uma conta do plano, como veio do arquivo (antes de qualquer conferência)."""

    linha: int
    codigo: str
    nome: str
    codigo_pai: str | None
    analitica: bool
    tipo: str | None
    natureza: str | None
    codigo_origem: str | None
    referencial: str | None
    # Situação no arquivo: True = ativa, False = inativa, None = o formato não diz.
    # Só o leiaute do sistema de referência traz (campo 7 do 0200). A conta inativa
    # é criada inativa no DataLedger, com aviso. Na política de atualizar, a situação
    # de conta existente NÃO muda.
    ativa: bool | None = None


@dataclass(frozen=True)
class PartidaLida:
    """Uma partida (um lado de um lançamento). SEM USO nesta fatia: a frente de
    lançamentos (fatia 3) a consome. Está aqui para o contrato ficar completo e
    para a frente B já saber em que forma o lançamento chega.
    """

    linha: int
    codigo_conta: str
    lado: str
    valor: Decimal
    historico: str | None = None
    centro_de_custo: str | None = None
    participante: str | None = None


@dataclass(frozen=True)
class LancamentoLido:
    """Um lançamento com suas partidas. SEM USO nesta fatia (ver `PartidaLida`)."""

    linha: int
    numero: str
    data: date
    historico: str
    partidas: tuple[PartidaLida, ...] = ()


@dataclass
class ResultadoLeitura:
    """O que um leitor devolve para o núcleo.

    `sha256` e `nome_arquivo` são preenchidos por `leitura.ler_arquivo`, e não
    pelo leitor: o leitor não precisa saber de onde veio o arquivo.
    `registros_ignorados` conta, por código de registro, o que o formato tem e
    o leitor não usa (ex.: os registros 0000 e I010 na ECD). Contar em vez de
    descartar em silêncio é o que deixa o contador ver que algo foi ignorado.
    """

    formato: str = ""
    nome_arquivo: str = ""
    sha256: str = ""
    codificacao: str = ""
    contas: list[ContaLida] = field(default_factory=list)
    lancamentos: list[LancamentoLido] = field(default_factory=list)
    ocorrencias: list[Ocorrencia] = field(default_factory=list)
    registros_ignorados: dict[str, int] = field(default_factory=dict)
    # CNPJ/CPF que o PRÓPRIO arquivo declara (só dígitos), quando o formato traz: o
    # registro 0000 no leiaute do sistema de referência e na ECD. None = o arquivo não
    # declara. Quem confere contra a empresa é `conferir_plano`, no núcleo.
    documento_declarado: str | None = None

    @property
    def tem_erro(self) -> bool:
        return any(o.nivel == NIVEL_ERRO for o in self.ocorrencias)


class IntercambioRecusado(Exception):
    """Recusa nomeada do núcleo: o arquivo ou a escrita não podem seguir.

    `mensagem` é para o contador. `ocorrencias`, quando houver, dizem linha e
    campo. Quem chama (API) traduz para 400 ou 413; o núcleo não responde HTTP.
    """

    def __init__(self, mensagem, ocorrencias=()):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.ocorrencias = tuple(ocorrencias)
