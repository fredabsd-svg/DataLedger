"""Serviços do livro-caixa (DL-046, fatia 1) — RC-113/RC-114/RC-128.

Mesmo desenho geral de `apps.contabilidade.services` (criação com
validação centralizada, idempotência por impressão digital, estorno
rastreável, trilha de auditoria na MESMA transação), simplificado para o
regime de CAIXA: um lançamento tem uma conta e um valor só (nunca partidas
dobradas — isso é a contabilidade).
"""

import hashlib
import json
import warnings
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.core.dinheiro import ValorMonetarioInvalido, casas_decimais, para_decimal
from apps.core.restricoes import mensagens_de, restricao_como_400
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.empresas.validators import normalizar_cnpj, normalizar_cpf
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    EstadoMesCaixa,
    FechamentoMesCaixa,
    LancamentoCaixa,
    NaturezaCaixa,
)
from apps.livro_caixa.validators import (
    codigo_carne_leao_e_deducao_do_carne_leao,
    mensagem_de_data_de_lancamento_caixa_fora_da_faixa,
)

# Mesma escala da escrituração manual contábil (DE-010) — recusa, nunca
# arredonda.
ESCALA_MAXIMA_LANCAMENTO_CAIXA = 2


class LancamentoCaixaInvalido(Exception):
    """Erro de domínio na criação/estorno de um lançamento de caixa —
    mesmo papel de `LancamentoInvalido` (contabilidade): todo erro de
    negócio deste módulo usa este tipo, para a view traduzir para 400 sem
    precisar conhecer cada causa em separado."""


class ChaveIdempotenciaConflitanteCaixa(Exception):
    """A MESMA `chave_idempotencia`, na MESMA empresa, foi reaproveitada
    para um lançamento de caixa com conteúdo DIFERENTE (mesmo espírito de
    `ChaveIdempotenciaConflitante`, contabilidade) — nunca devolve o
    lançamento errado como se fosse sucesso."""


class MesCaixaEncerrado(Exception):
    """Lançamento ou estorno recusado: o mês de destino do livro-caixa está
    encerrado (DL-053, RC-145). A correção é reabrir o mês (com motivo) —
    exatamente o procedimento da RC-130.

    Deliberadamente distinta de `LancamentoCaixaInvalido`: o corpo do
    lançamento é válido; o que recusa é o ESTADO do mês em que ele cairia.
    A API traduz para 409 (conflito de estado), a tela também — mesma
    distinção que `CompetenciaEncerrada` faz na contabilidade. NÃO é
    subclasse de `LancamentoCaixaInvalido` de propósito: um `except
    LancamentoCaixaInvalido` esquecido numa porta de escrita nova não pode
    engolir a recusa como se fosse erro de digitação (400).
    """


class MesCaixaOcupado(MesCaixaEncerrado):
    """Gravação recusada porque a ESPERA pelo lock do mês estourou o
    `lock_timeout` do banco (ou houve deadlock) — NUNCA porque o mês está de
    fato encerrado. Subclasse de `MesCaixaEncerrado` para herdar a tradução
    HTTP (409) em todas as portas de escrita; a mensagem diz a causa real
    (um fechamento ou reabertura em andamento) e orienta tentar de novo."""


class FechamentoMesCaixaInvalido(Exception):
    """Entrada malformada para encerrar/reabrir um mês do livro-caixa —
    ano/mês fora da faixa, motivo de reabertura em branco, empresa fora do
    modo livro-caixa. A API traduz para 400: o cliente corrige o que enviou.
    Contraste com `FechamentoMesCaixaRecusado`, que é sobre o ESTADO."""


class FechamentoMesCaixaRecusado(Exception):
    """O ESTADO atual do mês impede a transição pedida: encerrar mês já
    encerrado, reabrir mês que está aberto (ou que nunca foi fechado). O
    pedido é bem formado; o que impede é o que já está gravado — 409."""


class FechamentoMesCaixaTravado(FechamentoMesCaixaRecusado):
    """Encerrar/reabrir recusado porque a espera pelo lock do mês estourou
    o `lock_timeout` (um lançamento ou outra transição do MESMO mês ainda em
    andamento). Nada foi gravado; tentar de novo é seguro — 409."""


def _impressao_digital_caixa(
    *,
    empresa_id,
    conta_id,
    data,
    valor,
    historico,
    documento_origem,
    recebido_de,
    cpf_titular_pagamento,
    cpf_beneficiario_servico,
    cpf_beneficiario_nao_informado,
    cnpj_pagador,
    valor_irrf,
    competencia_previdencia,
    multa_previdencia,
    juros_previdencia,
    estorno_de_id,
):
    """Hash estável do conteúdo de um lançamento de caixa, para a
    idempotência — mesmo desenho de `_impressao_digital` (contabilidade):
    `json.dumps(..., sort_keys=True)` para a fronteira entre campos nunca
    ser forjável pelo conteúdo de um campo de texto livre.

    N7 (reconferência): `cpf_beneficiario_nao_informado` entra na
    impressão — antes, dois corpos com o MESMO titular mas indicador
    diferente (`true`/`false`) produziam a MESMA impressão, e a repetição
    da chave devolvia o segundo corpo (inválido, porque teria beneficiário
    e indicador incoerentes se fosse gravado de verdade) como se fosse
    repetição do primeiro — sucesso (200) para um corpo que nunca foi
    validado.

    DL-046, fatia 3: os quatro campos novos (IRRF e previdência oficial)
    entram na impressão pelo MESMO motivo do N7 — sem isso, dois corpos
    diferindo só em `valor_irrf` (ou só em `multa_previdencia`, etc.), com a
    mesma chave, colidiriam na MESMA impressão, e a repetição devolveria o
    segundo corpo (nunca validado) como se fosse repetição do primeiro.
    """
    estrutura = {
        "empresa_id": empresa_id,
        "conta_id": conta_id,
        "data": data.isoformat(),
        "valor": str(Decimal(valor).quantize(Decimal("0.01"))),
        "historico": (historico or "").strip(),
        "documento_origem": (documento_origem or "").strip(),
        "recebido_de": recebido_de or "",
        "cpf_titular_pagamento": cpf_titular_pagamento or "",
        "cpf_beneficiario_servico": cpf_beneficiario_servico or "",
        "cpf_beneficiario_nao_informado": bool(cpf_beneficiario_nao_informado),
        "cnpj_pagador": cnpj_pagador or "",
        "valor_irrf": str(valor_irrf) if valor_irrf is not None else None,
        "competencia_previdencia": (
            competencia_previdencia.isoformat() if competencia_previdencia is not None else None
        ),
        "multa_previdencia": str(multa_previdencia) if multa_previdencia is not None else None,
        "juros_previdencia": str(juros_previdencia) if juros_previdencia is not None else None,
        "estorno_de_id": estorno_de_id,
    }
    bruto = json.dumps(estrutura, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def criar_conta_livro_caixa(
    *,
    empresa,
    codigo,
    nome,
    natureza,
    codigo_carne_leao,
    codigo_ocupacao="",
    ativa=True,
    criado_por=None,
    request=None,
):
    """Cria uma conta do livro-caixa, validando tudo por `full_clean()`
    ANTES de gravar — um lugar só para a recusa por modo de escrituração e
    a coerência natureza <-> código do Carnê-Leão Web
    (`ContaLivroCaixa.clean()`), em vez de duplicar essas regras aqui.

    `DjangoValidationError` (de `full_clean()`) propaga para quem chamou
    sem tradução — a view é quem sabe traduzir para o protocolo HTTP,
    preservando o campo de cada erro (`message_dict`).
    """
    with (
        transaction.atomic(),
        restricao_como_400(mensagens_de("conta_livro_caixa_codigo_unico_por_empresa")),
    ):
        # N6 (reconferência da DL-046): trava a linha da EMPRESA ANTES de
        # validar o modo de escrituração (`full_clean()` chama `ContaLivro
        # Caixa.clean()`, que chama `recusar_se_nao_livro_caixa`). Sem
        # isto, uma troca de modo concorrente (`PATCH .../empresas/<id>/`)
        # podia comitar entre esta checagem e o `INSERT` da conta,
        # deixando uma conta de caixa órfã numa empresa já em
        # contabilidade — o auditor mediu 10 de 10 pares terminando assim.
        # `EmpresaDetailView.update()` trava a MESMA linha do lado da
        # troca de modo (espelho desta trava).
        #
        # Achado do próprio desenvolvedor ao testar N6: travar a LINHA no
        # banco não basta — o objeto `empresa` recebido pela função (lido
        # pela VIEW antes do lock) continua com o `modo_escrituracao`
        # ANTIGO em memória. `ContaLivroCaixa.clean()` valida `self.
        # empresa`, que o Django mantém em CACHE a partir do valor que
        # atribuímos abaixo — por isso a instância travada e FRESCA
        # (`empresa_travada`, lida DEPOIS do `select_for_update()`,
        # dentro da transação) é a que vai para `conta.empresa`, nunca a
        # `empresa` recebida como parâmetro.
        empresa_travada = Empresa.objects.select_for_update().get(pk=empresa.pk)
        conta = ContaLivroCaixa(
            empresa=empresa_travada,
            codigo=codigo,
            nome=nome,
            natureza=natureza,
            codigo_carne_leao=codigo_carne_leao,
            codigo_ocupacao=codigo_ocupacao or "",
            ativa=ativa,
        )
        conta.full_clean()
        conta.save()
        registrar(
            acao="conta_livro_caixa.criada",
            usuario=criado_por,
            escritorio=empresa.escritorio,
            objeto=conta,
            request=request,
            detalhes={"empresa_id": empresa.id, "codigo": codigo, "natureza": natureza},
        )
    return conta


def _normalizado_ou_vazio(valor, normalizador):
    """Aplica `normalizador` (`normalizar_cpf`/`normalizar_cnpj`) só quando
    `valor` não é vazio — B2 da rodada 1 de auditoria: sem isto, CPF/CNPJ
    com máscara era recusado por `full_clean()` com a mensagem de TAMANHO
    do `CharField` ("no máximo 11 caracteres, ele possui 14"), contradizendo
    a mensagem do próprio `validar_cpf`/`validar_cnpj` ("com ou sem
    máscara"). Normaliza ANTES de `full_clean()`, no mesmo ponto em que
    `Empresa`/`Estabelecimento` já normalizam (`CPFFormField.to_python`,
    `CPFSerializerField.to_internal_value`) — aqui não há um `Form`/
    `Serializer` de escrita para o lançamento (a view extrai o corpo à mão,
    mesmo desenho de `LancamentoListCreateView.post`, contabilidade), então
    a normalização precisa morar no SERVIÇO."""
    if not valor:
        return valor or ""
    return normalizador(valor)


def _valor_monetario_opcional(bruto, *, nome_campo):
    """DL-046, fatia 3: converte um valor monetário OPCIONAL (IRRF, multa
    ou juros) — `None`/`""` devolve `None`; texto devolve `Decimal` de 2
    casas, nunca negativo. Mesma política de `valor` (recusa, nunca
    arredonda; escala máxima de `ESCALA_MAXIMA_LANCAMENTO_CAIXA`) — mas sem
    a exigência de ser MAIOR que zero (`valor` do lançamento é sempre
    positivo; multa/juros/IRRF podem legitimamente ser zero ou ausentes)."""
    if bruto is None or bruto == "":
        return None
    try:
        valor = para_decimal(bruto)
    except ValorMonetarioInvalido as exc:
        raise LancamentoCaixaInvalido(f"'{nome_campo}' inválido: {exc}") from exc
    if valor < 0:
        raise LancamentoCaixaInvalido(f"'{nome_campo}' não pode ser negativo; recebido {valor}.")
    escala = casas_decimais(valor)
    if escala > ESCALA_MAXIMA_LANCAMENTO_CAIXA:
        raise LancamentoCaixaInvalido(
            f"'{nome_campo}' tem {escala} casas decimais; o livro-caixa aceita no "
            f"máximo {ESCALA_MAXIMA_LANCAMENTO_CAIXA}."
        )
    return valor.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Fechamento de mês do livro-caixa (DL-053, RC-145/RC-146) — NÍVEL 1.
#
# ## A trava e a corrida
#
# Toda gravação de `LancamentoCaixa` passa por `criar_lancamento_caixa` (o
# estorno chama a mesma função; não há importação, recepção fiscal nem outra
# porta que grave lançamento de caixa — varredura registrada no plano da
# entrega). Por isso a trava mora ali, num ponto só.
#
# O problema difícil é o mês SEM LINHA. Um lock de linha (`FOR SHARE`, como a
# contabilidade faz na `Competencia`) só funciona quando a linha existe; aqui
# o mês nasce aberto SEM registro, e o fechamento CRIA a linha. Um lançamento
# que lê "não há linha" e um fechamento que insere a linha e commita logo em
# seguida não se enxergam: o lançamento é gravado depois do commit do
# fechamento, em mês encerrado — uma corrida que lock de linha nenhum evita,
# porque não há linha para travar.
#
# A solução é um lock consultivo (advisory) do PostgreSQL por (empresa, ano,
# mês), escopado à TRANSAÇÃO (`pg_advisory_xact_lock*`: libera sozinho no
# COMMIT/ROLLBACK, mesmo se o processo morrer):
#
# - lançamento/estorno pedem o lock em modo COMPARTILHADO
#   (`pg_advisory_xact_lock_shared`): vários lançamentos do mesmo mês não se
#   bloqueiam entre si — a escrituração normal continua concorrente;
# - encerrar/reabrir pedem o lock em modo EXCLUSIVO (`pg_advisory_xact_lock`):
#   esperam os lançamentos em andamento terminarem e fazem os seguintes
#   esperarem até o commit da transição.
#
# Só DEPOIS de ter o lock o estado do mês é lido. Em READ COMMITTED (o padrão
# do Django/PostgreSQL, que este projeto não altera), cada comando enxerga o
# que já foi comitado, então quem esperou o fechamento vê a linha nova e
# recusa; quem chegou antes commita o lançamento e o fechamento só então
# prossegue — o lançamento aconteceu ANTES do fechamento, que é ordem legítima.
# Em qualquer das duas ordens o lançamento nunca termina em mês encerrado.
# Com a linha já existente o mesmo lock vale (a trava não depende de a linha
# existir), e as transições ainda travam a linha com `select_for_update()`
# para nenhuma escrita direta concorrente (admin, shell) ler estado velho.
#
# Escolha entre lock por (empresa, mês) e por empresa: por (empresa, mês) um
# fechamento de janeiro nunca espera lançamento de fevereiro. O custo é só a
# composição da chave (bigint): namespace (8 bits) | empresa (40 bits) |
# índice do mês desde 1970 (16 bits). Usa a forma de UM bigint do PostgreSQL,
# que é um espaço de chaves diferente da forma de dois int4 usada pelo lock do
# envio fiscal — os dois nunca colidem.
#
# `lock_timeout` (config/settings.py): a espera também é limitada. Estourou —
# ou o PostgreSQL escolheu esta transação como vítima de deadlock — o
# `OperationalError` cru é traduzido para exceção de domínio (409); nunca 500.
# Comparação por SQLSTATE, nunca pelo texto da mensagem (muda com o idioma do
# servidor). Qualquer outro `OperationalError` (conexão caída) propaga.
# ---------------------------------------------------------------------------

_NAMESPACE_LOCK_MES_CAIXA = 0x4C  # 8 bits; arbitrário, só precisa ser fixo
_MAXIMO_EMPRESA_ID_NO_LOCK = 2**40 - 1
_ANO_MINIMO_FECHAMENTO, _ANO_MAXIMO_FECHAMENTO = 1970, 2999
TAMANHO_MAXIMO_MOTIVO_REABERTURA = 1000

_SQLSTATE_ESPERA_DE_LOCK_FALHOU = frozenset({"55P03", "40P01"})


def _e_falha_de_espera_de_lock(excecao_de_banco):
    """`True` quando o `OperationalError` foi causado pelo estouro do
    `lock_timeout` (SQLSTATE 55P03) ou por deadlock (40P01). `psycopg`
    preserva o código na exceção original, em `__cause__`."""
    causa = excecao_de_banco.__cause__
    return getattr(causa, "sqlstate", None) in _SQLSTATE_ESPERA_DE_LOCK_FALHOU


def _chave_do_lock_do_mes(*, empresa_id, ano, mes):
    """Compõe o bigint do lock consultivo de (empresa, ano, mês). `ano` e
    `mes` já estão na faixa das `CheckConstraint` do modelo (1970..2999,
    1..12), então o índice cabe em 16 bits (máx. 12 371)."""
    if not (0 < empresa_id <= _MAXIMO_EMPRESA_ID_NO_LOCK):
        raise ValueError(f"empresa_id fora da faixa do lock do mês: {empresa_id}")
    indice_do_mes = (ano - _ANO_MINIMO_FECHAMENTO) * 12 + (mes - 1)
    return (_NAMESPACE_LOCK_MES_CAIXA << 56) | (empresa_id << 16) | indice_do_mes


def _adquirir_lock_do_mes(*, empresa_id, ano, mes, exclusivo):
    """Pede o lock consultivo do mês (ver o bloco de comentários acima) e
    ESPERA por ele. Propaga `OperationalError` — quem chama traduz, porque a
    mensagem e a exceção de domínio dependem do contexto (lançar x fechar).

    Precisa rodar DENTRO de uma transação: fora dela o lock `_xact_` seria
    liberado ao fim do próprio comando e não protegeria nada — por isso a
    recusa explícita em vez de uma trava que só parece existir.

    Fora do PostgreSQL (SQLite, só desenvolvimento local — `config/settings.py`
    recusa SQLite com `DEBUG=False`) não há lock consultivo: o SQLite já
    serializa toda escrita no arquivo do banco. O aviso é declarado, não
    silencioso, como o de `apps.contabilidade.services`.
    """
    if not connection.in_atomic_block:
        raise RuntimeError(
            "O lock do mês do livro-caixa só protege dentro de uma transação; "
            "chame a partir de uma função decorada com transaction.atomic."
        )
    if connection.vendor != "postgresql":
        warnings.warn(
            f"_adquirir_lock_do_mes sem lock: a conexão é '{connection.vendor}', não "
            "PostgreSQL. A garantia de CONCORRÊNCIA do fechamento de mês (DL-053) não "
            "vale aqui, só a checagem serial. Válido apenas em desenvolvimento local.",
            RuntimeWarning,
            stacklevel=3,
        )
        return
    funcao = "pg_advisory_xact_lock" if exclusivo else "pg_advisory_xact_lock_shared"
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {funcao}(%s)",
            [_chave_do_lock_do_mes(empresa_id=empresa_id, ano=ano, mes=mes)],
        )


def _recusar_se_mes_caixa_encerrado(*, empresa, data, e_estorno):
    """A TRAVA de `criar_lancamento_caixa` (critérios 1 e 2 da DL-053).

    Pede o lock do mês em modo compartilhado e só então lê o estado; se
    `encerrado`, levanta `MesCaixaEncerrado` (409) nomeando mês e empresa. A
    condição é `estado != ABERTO` (não `== ENCERRADO`): estado desconhecido
    bloqueia, nunca libera. Mês sem linha é aberto.

    Para o estorno, `data` é a do lançamento ORIGINAL (DE-091 item 4), então
    estornar lançamento de mês encerrado exige reabri-lo — a RC-130.
    """
    try:
        _adquirir_lock_do_mes(empresa_id=empresa.id, ano=data.year, mes=data.month, exclusivo=False)
    except OperationalError as exc:
        if not _e_falha_de_espera_de_lock(exc):
            raise
        # Só parâmetros já em memória na mensagem: a transação está abortada
        # pelo estouro do lock, e qualquer consulta aqui falharia.
        raise MesCaixaOcupado(
            f"O mês {data.month:02d}/{data.year} do livro-caixa de {empresa} está sendo "
            "encerrado ou reaberto por outra operação agora; não foi possível confirmar o "
            "estado dele a tempo. Tente novamente em instantes."
        ) from exc

    estado = (
        FechamentoMesCaixa.objects.filter(empresa=empresa, ano=data.year, mes=data.month)
        .values_list("estado", flat=True)
        .first()
    )
    if estado is not None and estado != EstadoMesCaixa.ABERTO:
        mes_ano = f"{data.month:02d}/{data.year}"
        if e_estorno:
            raise MesCaixaEncerrado(
                f"O mês {mes_ano} do livro-caixa de {empresa} está encerrado; não é possível "
                "estornar lançamento dele. Reabra o mês (informando o motivo) para corrigir "
                "o lançamento no mês original (RC-130)."
            )
        raise MesCaixaEncerrado(
            f"O mês {mes_ano} do livro-caixa de {empresa} está encerrado; não é possível "
            "gravar lançamento nele. Reabra o mês (informando o motivo) ou lance em um "
            "mês aberto."
        )


@transaction.atomic
def criar_lancamento_caixa(
    *,
    empresa,
    conta,
    data,
    valor,
    historico,
    documento_origem="",
    recebido_de=None,
    cpf_titular_pagamento="",
    cpf_beneficiario_servico="",
    cpf_beneficiario_nao_informado=False,
    cnpj_pagador="",
    valor_irrf=None,
    competencia_previdencia=None,
    multa_previdencia=None,
    juros_previdencia=None,
    criado_por=None,
    chave_idempotencia=None,
    estorno_de=None,
    request=None,
    _pular_validacao_dependente_da_conta=False,
):
    """Cria um lançamento de caixa, validando tudo ANTES de gravar.

    Mesma ordem de `criar_lancamento` (contabilidade): recusa por modo de
    escrituração primeiro (defesa em profundidade — a view já recusa
    antes de chegar aqui), depois validação de dado, e só então a
    checagem de idempotência (nunca "atalha" para sucesso com um corpo
    inválido só porque a chave já existe).

    `chave_idempotencia` opcional: repetir a chamada com a MESMA chave,
    na MESMA empresa, e o MESMO conteúdo (comparado por impressão
    digital) devolve o lançamento já existente em vez de duplicar
    (`criado_agora=False`, atributo não persistido). Chave repetida com
    conteúdo DIFERENTE levanta `ChaveIdempotenciaConflitanteCaixa`.

    A2 (rodada 1 de auditoria): a checagem de idempotência acima cobre a
    repetição SEQUENCIAL (uma requisição de cada vez). Sob CORRIDA (duas
    requisições concorrentes com a mesma chave, nenhuma vendo a linha da
    outra na pré-checagem), a defesa é a `UniqueConstraint` de banco — o
    `save()`, mais abaixo, roda num SAVEPOINT próprio, e um `IntegrityError`
    daquela constraint é tratado exatamente como a pré-checagem: mesmo
    conteúdo devolve o existente (200), conteúdo diferente levanta o
    conflito (409). Nunca um 500.

    `_pular_validacao_dependente_da_conta` (uso INTERNO, nunca exposto por
    view nenhuma): M4 (DE-087 item 4) — setada só por
    `estornar_lancamento_caixa`, para o ESTORNO copiar o original sem
    revalidar as regras de CPF/CNPJ contra o código ATUAL da conta.
    """
    try:
        recusar_se_nao_livro_caixa(empresa)
    except EmpresaNaoEmModoLivroCaixa as exc:
        raise LancamentoCaixaInvalido(exc.mensagem) from exc

    if conta.empresa_id != empresa.id:
        raise LancamentoCaixaInvalido(
            "A conta do livro-caixa informada não pertence a esta empresa."
        )

    # B1 (rodada 1 de auditoria): conta INATIVA não recebe lançamento NOVO —
    # mas o ESTORNO (`estorno_de is not None`) de um lançamento antigo
    # continua possível, mesmo que a conta tenha sido inativada depois.
    # Corrigir um lançamento antigo não pode ficar bloqueado por uma
    # decisão de cadastro tomada depois dele.
    if estorno_de is None and not conta.ativa:
        raise LancamentoCaixaInvalido(
            f"A conta '{conta.codigo}' está inativa; não é possível lançar um "
            "novo movimento nela. Reative a conta ou use outra."
        )

    try:
        valor = para_decimal(valor)
    except ValorMonetarioInvalido as exc:
        raise LancamentoCaixaInvalido(str(exc)) from exc
    if valor <= 0:
        raise LancamentoCaixaInvalido(
            f"O valor do lançamento deve ser maior que zero; recebido {valor}."
        )
    escala = casas_decimais(valor)
    if escala > ESCALA_MAXIMA_LANCAMENTO_CAIXA:
        raise LancamentoCaixaInvalido(
            f"O valor {valor} tem {escala} casas decimais; o livro-caixa aceita no "
            f"máximo {ESCALA_MAXIMA_LANCAMENTO_CAIXA}."
        )
    # `casas_decimais()` normaliza (zero à direita não é precisão real) —
    # mas o `DecimalField.decimal_places=2` do modelo NÃO normaliza: o
    # `DecimalValidator` do próprio Django olha o expoente CRU de
    # `Decimal`, e "100.000" tem exponent=-3 mesmo valendo exatamente
    # "100.00". Sem este `quantize()`, um valor como "100.000" passaria
    # aqui e ainda assim seria recusado por `full_clean()` mais abaixo, com
    # uma mensagem que contradiz esta checagem ("não pode ter mais de 2
    # casas decimais" depois de este código já ter aceitado 0 casas
    # SIGNIFICATIVAS). `quantize()` é seguro exatamente porque `escala` já
    # provou que a redução para 2 casas não perde informação nenhuma.
    valor = valor.quantize(Decimal("0.01"))

    mensagem_data = mensagem_de_data_de_lancamento_caixa_fora_da_faixa(data)
    if mensagem_data is not None:
        raise LancamentoCaixaInvalido(mensagem_data)

    if "\x00" in (historico or ""):
        raise LancamentoCaixaInvalido("O histórico não pode conter o caractere nulo (código 0).")
    if chave_idempotencia and "\x00" in chave_idempotencia:
        raise LancamentoCaixaInvalido(
            "A chave de idempotência não pode conter o caractere nulo (código 0)."
        )

    # B2 (rodada 1 de auditoria): normaliza CPF/CNPJ (com ou sem máscara)
    # ANTES da impressão digital e de `full_clean()` — nunca depois, para a
    # impressão digital ser estável entre "111.444.777-35" e "11144477735"
    # (o MESMO lançamento, só digitado de duas formas).
    try:
        cpf_titular_pagamento = _normalizado_ou_vazio(cpf_titular_pagamento, normalizar_cpf)
        cpf_beneficiario_servico = _normalizado_ou_vazio(cpf_beneficiario_servico, normalizar_cpf)
        cnpj_pagador = _normalizado_ou_vazio(cnpj_pagador, normalizar_cnpj)
    except DjangoValidationError as exc:
        raise LancamentoCaixaInvalido("; ".join(exc.messages)) from exc

    # DL-046, fatia 3: os três valores monetários opcionais seguem a MESMA
    # política de `valor` (texto, nunca número JSON — a checagem de tipo é
    # da VIEW; aqui só a conversão). `competencia_previdencia` já chega como
    # `date`/`None` (a VIEW converte "AAAA-MM-DD", mesmo padrão de `data`) —
    # a coerência com o código da conta (só previdência oficial) é
    # verificada por `full_clean()`, mais abaixo.
    valor_irrf = _valor_monetario_opcional(valor_irrf, nome_campo="valor_irrf")
    multa_previdencia = _valor_monetario_opcional(multa_previdencia, nome_campo="multa_previdencia")
    juros_previdencia = _valor_monetario_opcional(juros_previdencia, nome_campo="juros_previdencia")

    if chave_idempotencia:
        impressao = _impressao_digital_caixa(
            empresa_id=empresa.id,
            conta_id=conta.id,
            data=data,
            valor=valor,
            historico=historico,
            documento_origem=documento_origem,
            recebido_de=recebido_de,
            cpf_titular_pagamento=cpf_titular_pagamento,
            cpf_beneficiario_servico=cpf_beneficiario_servico,
            cpf_beneficiario_nao_informado=cpf_beneficiario_nao_informado,
            cnpj_pagador=cnpj_pagador,
            valor_irrf=valor_irrf,
            competencia_previdencia=competencia_previdencia,
            multa_previdencia=multa_previdencia,
            juros_previdencia=juros_previdencia,
            estorno_de_id=estorno_de.id if estorno_de is not None else None,
        )
        existente = LancamentoCaixa.objects.filter(
            empresa=empresa, chave_idempotencia=chave_idempotencia
        ).first()
        if existente is not None:
            if existente.chave_idempotencia_fingerprint == impressao:
                # B5 (rodada 1 de auditoria): a repetição idempotente
                # também é um FATO que a trilha precisa registrar — antes,
                # ela devolvia o existente em silêncio, sem rastro nenhum
                # de que uma segunda requisição chegou.
                registrar(
                    acao="lancamento_caixa.criacao_repetida",
                    usuario=criado_por,
                    escritorio=empresa.escritorio,
                    objeto=existente,
                    request=request,
                    detalhes={
                        "chave_idempotencia_hash": hashlib.sha256(
                            chave_idempotencia.encode("utf-8")
                        ).hexdigest()[:12]
                    },
                )
                existente.criado_agora = False
                return existente
            raise ChaveIdempotenciaConflitanteCaixa(
                "Esta chave de idempotência já foi usada nesta empresa para um "
                "lançamento de caixa com conteúdo diferente."
            )
    else:
        impressao = None

    # DL-053: a TRAVA do mês encerrado. Depois de toda a validação e da
    # checagem de idempotência (uma repetição idempotente devolve o lançamento
    # que JÁ existe e não grava nada, então não precisa da trava), e ANTES de
    # qualquer INSERT. O lock compartilhado do mês é mantido até o fim desta
    # transação (inclui a trilha), que é o que impede um fechamento concorrente
    # de commitar entre esta leitura do estado e a gravação do lançamento.
    _recusar_se_mes_caixa_encerrado(empresa=empresa, data=data, e_estorno=estorno_de is not None)

    lancamento = LancamentoCaixa(
        empresa=empresa,
        conta=conta,
        data=data,
        valor=valor,
        historico=historico,
        documento_origem=documento_origem or "",
        recebido_de=recebido_de or None,
        cpf_titular_pagamento=cpf_titular_pagamento or "",
        cpf_beneficiario_servico=cpf_beneficiario_servico or "",
        cpf_beneficiario_nao_informado=bool(cpf_beneficiario_nao_informado),
        cnpj_pagador=cnpj_pagador or "",
        valor_irrf=valor_irrf,
        competencia_previdencia=competencia_previdencia,
        multa_previdencia=multa_previdencia,
        juros_previdencia=juros_previdencia,
        chave_idempotencia=chave_idempotencia or None,
        chave_idempotencia_fingerprint=impressao,
        estorno_de=estorno_de,
        criado_por=criado_por,
    )
    if _pular_validacao_dependente_da_conta:
        lancamento._estorno_nao_revalida_regras_da_conta = True

    # A2 (rodada 1 de auditoria): a janela em que `full_clean()` — que
    # também valida a `UniqueConstraint` da chave de idempotência
    # (`validate_constraints()`, Django ≥ 4.1) — já vê a linha da OUTRA
    # requisição concorrente, comprometida entre a pré-checagem acima e
    # este ponto. Sem dispensar essa checagem, essa corrida virava 400 "já
    # existe" em vez do 200 que a idempotência promete.
    #
    # N2 (reconferência): a correção original passava `chave_idempotencia`
    # em `full_clean(exclude=...)`, e `exclude` também dispensa
    # `clean_fields()` — não só `validate_constraints()` — para aquele
    # campo. Isso desligava o `MaxLengthValidator` (255) e o
    # `ProhibitNullCharactersValidator` (M2) do PRÓPRIO campo, e uma chave
    # de 300 caracteres batia direto no `DataError` do PostgreSQL (500) em
    # vez de ser recusada aqui. Corrigido separando as duas fases: `full_
    # clean(validate_constraints=False)` continua validando TODOS os
    # campos, inclusive `chave_idempotencia` (comprimento e NUL) — só a
    # checagem de CONSTRAINT (a `UniqueConstraint` da idempotência) fica de
    # fora, e só quando há chave, tratada separadamente por
    # `validate_constraints(exclude=...)`.
    try:
        lancamento.full_clean(validate_constraints=False)
    except DjangoValidationError as exc:
        raise LancamentoCaixaInvalido("; ".join(exc.messages)) from exc

    excluir_da_validacao = {"chave_idempotencia"} if chave_idempotencia else set()
    try:
        lancamento.validate_constraints(exclude=excluir_da_validacao or None)
    except DjangoValidationError as exc:
        raise LancamentoCaixaInvalido("; ".join(exc.messages)) from exc

    try:
        with transaction.atomic():
            lancamento.save()
    except IntegrityError:
        if chave_idempotencia:
            # A MESMA corrida, agora pega pela constraint de banco (a
            # pré-checagem e a exclusão de `full_clean()` acima, juntas,
            # cobrem a maior parte da janela; esta é a defesa final,
            # residual, para o instante entre `full_clean()` e o `INSERT`
            # em si). `filter().first()`, nunca `.get()` (mesmo raciocínio
            # de `criar_lancamento`, contabilidade): se a violação foi de
            # OUTRA constraint (`valor_positivo`, `estorno_de_unico`), pode
            # não existir nenhuma linha com esta chave ainda, e `.get()`
            # levantaria `DoesNotExist` — um 500 disfarçado de 400.
            existente = LancamentoCaixa.objects.filter(
                empresa=empresa, chave_idempotencia=chave_idempotencia
            ).first()
            if existente is not None:
                if existente.chave_idempotencia_fingerprint == impressao:
                    registrar(
                        acao="lancamento_caixa.criacao_repetida",
                        usuario=criado_por,
                        escritorio=empresa.escritorio,
                        objeto=existente,
                        request=request,
                        detalhes={
                            "chave_idempotencia_hash": hashlib.sha256(
                                chave_idempotencia.encode("utf-8")
                            ).hexdigest()[:12],
                            "corrida": True,
                        },
                    )
                    existente.criado_agora = False
                    return existente
                raise ChaveIdempotenciaConflitanteCaixa(
                    "A mesma Idempotency-Key já foi usada para um lançamento de "
                    "caixa com conteúdo diferente. Gere uma nova chave para este "
                    "lançamento."
                ) from None
        # Qualquer OUTRA violação de integridade propaga sem conversão, de
        # propósito — mesma decisão de `criar_lancamento` (contabilidade):
        # uma `IntegrityError` de origem desconhecida pode ser defeito
        # nosso, não erro do cliente, e converter tudo em 400 esconderia o
        # defeito de quem monitora 500.
        raise

    registrar(
        acao="lancamento_caixa.estornado" if estorno_de is not None else "lancamento_caixa.criado",
        usuario=criado_por,
        escritorio=empresa.escritorio,
        objeto=lancamento,
        request=request,
        detalhes={
            "empresa_id": empresa.id,
            "conta": conta.codigo,
            "valor": str(valor),
            "data": data.isoformat(),
            "estorno_de_id": estorno_de.id if estorno_de is not None else None,
        },
    )
    lancamento.criado_agora = True
    return lancamento


def estornar_lancamento_caixa(
    lancamento, *, criado_por=None, data=None, historico=None, request=None
):
    """Cria o lançamento reverso de `lancamento` — mesma conta, mesmo
    valor, `estorno_de=lancamento`. Nunca edita nem apaga o original.

    Estorno único (mesmo padrão de `estornar_lancamento`, contabilidade):
    `select_for_update()` bloqueia a linha do original durante toda a
    operação (evita duas chamadas concorrentes passarem pela checagem
    "ainda não foi estornado" antes de qualquer gravação); a constraint de
    banco `lancamento_caixa_estorno_de_unico` é a defesa residual de
    corrida.

    A data do estorno nunca pode ser anterior à do original (mesmo RC-78
    da contabilidade, aplicado por analogia — reportado, não uma segunda
    confirmação do Fred para o livro-caixa).

    ⚠️ **DE-091 item 4 (M-4, correção da rodada 1 da auditoria da fatia 2):
    o padrão passou a ser a data do ORIGINAL** (era "hoje", `timezone.
    localdate()`) — o encadeamento do carnê-leão (excesso de livro-caixa,
    crédito do exterior, saldo abaixo de R$ 10,00) é recalculado dentro do
    MESMO mês (RC-130); um estorno datado de "hoje" moveria o efeito para
    um mês diferente do lançamento corrigido, sem nenhuma necessidade —
    corrigir um lançamento de um mês passado deve refletir NAQUELE mês, não
    no mês em que o escritório percebeu o erro. Data EXPLÍCITA (`data`) de
    um mês DIFERENTE do original é recusada — a correção de um lançamento
    de outro mês segue por estorno NO MÊS ORIGINAL seguido de um novo
    lançamento no mês correto, nunca por uma data de estorno fora do mês do
    lançamento estornado (RC-130).
    """
    with transaction.atomic():
        lancamento = LancamentoCaixa.objects.select_for_update().get(pk=lancamento.pk)

        if lancamento.estorno_de_id is not None:
            raise LancamentoCaixaInvalido(
                "Não é possível estornar um lançamento que já é um estorno."
            )
        if lancamento.estornos.exists():
            raise LancamentoCaixaInvalido("Este lançamento já foi estornado.")

        data_do_estorno = data if data is not None else lancamento.data
        if data_do_estorno < lancamento.data:
            raise LancamentoCaixaInvalido(
                "A data do estorno não pode ser anterior à data do lançamento original "
                f"({lancamento.data.strftime('%d/%m/%Y')})."
            )
        if (data_do_estorno.year, data_do_estorno.month) != (
            lancamento.data.year,
            lancamento.data.month,
        ):
            raise LancamentoCaixaInvalido(
                "A data do estorno deve ficar no MESMO mês do lançamento original "
                f"({lancamento.data.strftime('%m/%Y')}) — a correção de um "
                "lançamento de outro mês segue por estorno no mês original seguido "
                "de um novo lançamento no mês correto, nunca por uma data de "
                "estorno fora do mês."
            )

        return criar_lancamento_caixa(
            empresa=lancamento.empresa,
            conta=lancamento.conta,
            data=data_do_estorno,
            valor=lancamento.valor,
            historico=historico or f"Estorno do lançamento de caixa {lancamento.pk}",
            documento_origem=lancamento.documento_origem,
            recebido_de=lancamento.recebido_de,
            cpf_titular_pagamento=lancamento.cpf_titular_pagamento,
            cpf_beneficiario_servico=lancamento.cpf_beneficiario_servico,
            cpf_beneficiario_nao_informado=lancamento.cpf_beneficiario_nao_informado,
            cnpj_pagador=lancamento.cnpj_pagador,
            # DL-046, fatia 3: os quatro campos novos são copiados do
            # original pelo MESMO motivo do `cpf_beneficiario_nao_informado`
            # acima (N13) — o estorno é um espelho exato do lançamento que
            # reverte, nunca um lançamento novo com dados próprios.
            valor_irrf=lancamento.valor_irrf,
            competencia_previdencia=lancamento.competencia_previdencia,
            multa_previdencia=lancamento.multa_previdencia,
            juros_previdencia=lancamento.juros_previdencia,
            criado_por=criado_por,
            estorno_de=lancamento,
            request=request,
            # M4 (DE-087 item 4): o estorno COPIA o original — nunca
            # revalida as regras de CPF/CNPJ contra o código ATUAL da
            # conta (que pode ter mudado desde então, embora a guarda de
            # `ContaLivroCaixa.clean()` já impeça isso quando há
            # lançamento gravado — esta é a segunda camada).
            _pular_validacao_dependente_da_conta=True,
        )


# ---------------------------------------------------------------------------
# Encerrar e reabrir o mês (DL-053, critérios 3, 4 e 5)
#
# PERMISSÃO (RC-146 = RC-102): quem pode encerrar/reabrir é decidido pela
# VIEW (`PodeFecharMesCaixa`, `papel_pode_fechar_mes_caixa`) — mesmo
# desenho de `encerrar_competencia`, que também não conhece papel. Estas
# funções recebem o `usuario` explícito (autoria e trilha), nunca o inferem.
# ---------------------------------------------------------------------------


def _validar_empresa_ano_mes_do_fechamento(*, empresa, ano, mes, usuario):
    """Entrada das duas transições: recusa (400) o que o cliente pode
    corrigir. Na API o mesmo limite já é checado na fronteira, com mensagem
    específica; aqui é a defesa de quem chama o serviço direto (shell,
    comando, tarefa)."""
    if usuario is None:
        raise FechamentoMesCaixaInvalido("Informe o usuário que encerra ou reabre o mês.")
    try:
        recusar_se_nao_livro_caixa(empresa)
    except EmpresaNaoEmModoLivroCaixa as exc:
        raise FechamentoMesCaixaInvalido(exc.mensagem) from exc
    if isinstance(mes, bool) or not isinstance(mes, int) or not (1 <= mes <= 12):
        raise FechamentoMesCaixaInvalido(f"'mes' inválido: {mes!r} — deve estar entre 1 e 12.")
    if (
        isinstance(ano, bool)
        or not isinstance(ano, int)
        or not (_ANO_MINIMO_FECHAMENTO <= ano <= _ANO_MAXIMO_FECHAMENTO)
    ):
        raise FechamentoMesCaixaInvalido(
            f"'ano' inválido: {ano!r} — deve estar entre "
            f"{_ANO_MINIMO_FECHAMENTO} e {_ANO_MAXIMO_FECHAMENTO}."
        )


def _travar_mes_para_transicao(*, empresa, ano, mes):
    """Lock consultivo EXCLUSIVO do mês (espera os lançamentos em andamento e
    barra os novos até o commit) e, se a linha existir, `FOR UPDATE` nela.
    Devolve a linha travada ou `None` (mês sem registro = aberto). Estouro de
    `lock_timeout`/deadlock vira `FechamentoMesCaixaTravado` (409)."""
    try:
        _adquirir_lock_do_mes(empresa_id=empresa.id, ano=ano, mes=mes, exclusivo=True)
        return (
            FechamentoMesCaixa.objects.select_for_update()
            .filter(empresa=empresa, ano=ano, mes=mes)
            .first()
        )
    except OperationalError as exc:
        if not _e_falha_de_espera_de_lock(exc):
            raise
        raise FechamentoMesCaixaTravado(
            f"O mês {mes:02d}/{ano} do livro-caixa de {empresa} está sendo alterado por "
            "outra operação agora (um lançamento, fechamento ou reabertura em andamento); "
            "não foi possível travá-lo a tempo. Nada foi gravado. Tente novamente em "
            "instantes."
        ) from exc


@transaction.atomic
def encerrar_mes_caixa(*, empresa, ano, mes, usuario, request=None):
    """Encerra o mês (ano, mes) do livro-caixa da empresa: `aberto -> encerrado`.

    Cria a linha se o mês nunca teve registro (mês sem registro é aberto) e
    a reutiliza se o mês foi reaberto antes. Mês JÁ encerrado é RECUSADO
    (`FechamentoMesCaixaRecusado`, 409), sem efeito — diferente da
    competência contábil, que trata o repetido como no-op: aqui o critério 4
    da DL-053 manda recusar, e o autor/horário do primeiro fechamento nunca
    são sobrescritos.

    Atomicidade: estado, autoria e trilha (`registrar`) gravam na MESMA
    transação — se a trilha falhar, o fechamento não fica gravado. A trilha
    carrega `ano`/`mes`/`empresa_id`, sem dado pessoal.

    Concorrência: lock consultivo exclusivo do mês (ver o bloco de
    comentários da trava). Dois encerramentos simultâneos do MESMO mês
    produzem UM fechamento; o segundo, ao obter o lock, encontra `encerrado`
    e é recusado. Fechar também espera o lançamento em andamento terminar,
    então o fechamento nunca "passa por cima" de uma gravação em voo.

    Levanta `FechamentoMesCaixaInvalido` (400) para entrada malformada ou
    empresa fora do modo livro-caixa, `FechamentoMesCaixaRecusado` (409) para
    o estado, e `FechamentoMesCaixaTravado` (409) se a espera pelo lock
    estourar.
    """
    _validar_empresa_ano_mes_do_fechamento(empresa=empresa, ano=ano, mes=mes, usuario=usuario)
    fechamento = _travar_mes_para_transicao(empresa=empresa, ano=ano, mes=mes)

    if fechamento is not None and fechamento.estado == EstadoMesCaixa.ENCERRADO:
        raise FechamentoMesCaixaRecusado(
            f"O mês {mes:02d}/{ano} do livro-caixa de {empresa} já está encerrado "
            f"(em {timezone.localtime(fechamento.fechado_em):%d/%m/%Y %H:%M}). Nada foi alterado."
        )

    agora = timezone.now()
    if fechamento is None:
        fechamento = FechamentoMesCaixa(
            empresa=empresa,
            ano=ano,
            mes=mes,
            estado=EstadoMesCaixa.ENCERRADO,
            fechado_em=agora,
            fechado_por=usuario,
        )
        fechamento.full_clean()
        fechamento.save()
    else:
        # Mês reaberto que volta a ser encerrado: a linha é reaproveitada; a
        # reabertura anterior fica registrada na linha e na trilha.
        fechamento.estado = EstadoMesCaixa.ENCERRADO
        fechamento.fechado_em = agora
        fechamento.fechado_por = usuario
        fechamento.save(update_fields=["estado", "fechado_em", "fechado_por"])

    registrar(
        acao="fechamento_mes_caixa.encerrado",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=fechamento,
        request=request,
        detalhes={"ano": ano, "mes": mes, "empresa_id": empresa.id},
    )
    return fechamento


@transaction.atomic
def reabrir_mes_caixa(*, empresa, ano, mes, usuario, motivo, request=None):
    """Reabre o mês (ano, mes) do livro-caixa da empresa: `encerrado -> aberto`.

    `motivo` é OBRIGATÓRIO (critério 4): vazio, só espaço, com caractere
    nulo ou acima de `TAMANHO_MAXIMO_MOTIVO_REABERTURA` é recusado
    (`FechamentoMesCaixaInvalido`, 400) ANTES de qualquer lock — erro de
    entrada, não de estado. Reabrir mês que está aberto (ou que nunca foi
    fechado) é recusado (`FechamentoMesCaixaRecusado`, 409), sem efeito.

    A linha NÃO é apagada: `estado` volta a `aberto` e `reaberto_em`/
    `reaberto_por`/`motivo_reabertura` são gravados. A trilha
    (`fechamento_mes_caixa.reaberto`) leva o motivo e o fechamento que está
    sendo desfeito (`fechado_por_anterior`/`fechado_em_anterior`), na mesma
    transação — reabertura é o ato mais afiado do período e nunca pode
    acontecer sem rastro.
    """
    if motivo is not None and not isinstance(motivo, str):
        raise FechamentoMesCaixaInvalido("O motivo da reabertura deve ser texto.")
    motivo_normalizado = (motivo or "").strip()
    if not motivo_normalizado:
        raise FechamentoMesCaixaInvalido(
            "Informe o motivo da reabertura: não pode ficar em branco."
        )
    if "\x00" in motivo_normalizado:
        raise FechamentoMesCaixaInvalido(
            "O motivo da reabertura não pode conter o caractere nulo (código 0)."
        )
    if len(motivo_normalizado) > TAMANHO_MAXIMO_MOTIVO_REABERTURA:
        raise FechamentoMesCaixaInvalido(
            f"O motivo da reabertura tem {len(motivo_normalizado)} caracteres; o máximo "
            f"é {TAMANHO_MAXIMO_MOTIVO_REABERTURA}."
        )
    _validar_empresa_ano_mes_do_fechamento(empresa=empresa, ano=ano, mes=mes, usuario=usuario)
    fechamento = _travar_mes_para_transicao(empresa=empresa, ano=ano, mes=mes)

    if fechamento is None or fechamento.estado != EstadoMesCaixa.ENCERRADO:
        raise FechamentoMesCaixaRecusado(
            f"Só é possível reabrir um mês encerrado; o mês {mes:02d}/{ano} do livro-caixa "
            f"de {empresa} está aberto. Nada foi alterado."
        )

    # Capturados ANTES do `save()`: o fechamento que está sendo desfeito
    # deixa de ser o estado atual da linha, e a trilha precisa dele.
    fechado_por_anterior = fechamento.fechado_por_id
    fechado_em_anterior = fechamento.fechado_em

    fechamento.estado = EstadoMesCaixa.ABERTO
    fechamento.reaberto_em = timezone.now()
    fechamento.reaberto_por = usuario
    fechamento.motivo_reabertura = motivo_normalizado
    fechamento.save(update_fields=["estado", "reaberto_em", "reaberto_por", "motivo_reabertura"])
    registrar(
        acao="fechamento_mes_caixa.reaberto",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=fechamento,
        request=request,
        detalhes={
            "ano": ano,
            "mes": mes,
            "empresa_id": empresa.id,
            "motivo": motivo_normalizado,
            "fechado_por_anterior": fechado_por_anterior,
            "fechado_em_anterior": fechado_em_anterior.isoformat(),
        },
    )
    return fechamento


def _nome_do_usuario_do_fechamento(usuario):
    """Nome para exibição ao lado do id — o escritório precisa ver QUEM
    fechou sem consultar a trilha."""
    if usuario is None:
        return None
    return usuario.get_full_name() or usuario.get_username()


def estado_dos_meses_caixa(*, empresa, ano):
    """Estado dos 12 meses de `ano` para a empresa — SEMPRE 12 itens, em
    ordem: o mês sem registro aparece como `aberto` (decisão 3 do plano),
    sem autoria. Uma consulta só (com `select_related` nos dois usuários).

    Só LEITURA, sem lock: serve à consulta e à tela. NÃO substitui a trava —
    quem grava sempre passa por `criar_lancamento_caixa`.
    """
    registros = {
        r.mes: r
        for r in FechamentoMesCaixa.objects.filter(empresa=empresa, ano=ano).select_related(
            "fechado_por", "reaberto_por"
        )
    }
    meses = []
    for mes in range(1, 13):
        r = registros.get(mes)
        meses.append(
            {
                "ano": ano,
                "mes": mes,
                "estado": r.estado if r is not None else EstadoMesCaixa.ABERTO.value,
                "fechado_em": r.fechado_em if r is not None else None,
                "fechado_por": r.fechado_por_id if r is not None else None,
                "fechado_por_nome": (
                    _nome_do_usuario_do_fechamento(r.fechado_por) if r is not None else None
                ),
                "reaberto_em": r.reaberto_em if r is not None else None,
                "reaberto_por": r.reaberto_por_id if r is not None else None,
                "reaberto_por_nome": (
                    _nome_do_usuario_do_fechamento(r.reaberto_por) if r is not None else None
                ),
                "motivo_reabertura": r.motivo_reabertura if r is not None else "",
            }
        )
    return meses


def mes_caixa_esta_encerrado(*, empresa, ano, mes):
    """Leitura SEM lock: o mês está encerrado? Para a tela decidir se oferece
    a ação de lançar. Informativa — a recusa de verdade é a trava de
    `criar_lancamento_caixa`, que lê o estado sob lock."""
    return FechamentoMesCaixa.objects.filter(
        empresa=empresa, ano=ano, mes=mes, estado=EstadoMesCaixa.ENCERRADO
    ).exists()


GRUPO_ENTRADA = "entrada"
GRUPO_SAIDA_CUSTEIO = "saida_custeio"
GRUPO_SAIDA_DEDUCAO_CARNE_LEAO = "saida_deducao_carne_leao"


def apurar_livro_caixa(*, empresa, inicio, fim):
    """Relatório "Livro Caixa" do período `[inicio, fim]` — lançamentos em
    ordem cronológica, totais de entradas (receita) e saídas (despesa), e
    saldo, CONCILIÁVEL com os lançamentos (critério 3 do plano).

    Um ESTORNO aparece como uma linha PRÓPRIA (nunca oculta nem cancela o
    original na listagem — "os estornos visíveis" do critério da tarefa),
    mas contribui aos TOTAIS com o sinal INVERTIDO do original: um estorno
    de receita SUBTRAI da receita total, um estorno de despesa SUBTRAI da
    despesa total — nunca aparece como uma despesa/receita nova. Sem essa
    conversão de sinal, o total do período dobraria a magnitude do
    lançamento estornado, em vez de zerar o seu efeito.

    D3 (rodada 1 de auditoria, DE-087 item 13): pagamentos `P20` (imposto
    pago, previdência oficial, pensão alimentícia) saem num grupo PRÓPRIO
    (`GRUPO_SAIDA_DEDUCAO_CARNE_LEAO`), separado das despesas de custeio
    (`GRUPO_SAIDA_CUSTEIO`, `P10`/`P11`) — no art. 68 do RIR/2018 são
    DEDUÇÕES do carnê-leão, não despesas do livro-caixa. O SALDO de caixa
    continua conciliado: as duas saídas ainda reduzem o dinheiro em caixa
    igualmente (regime de caixa), então `total_saidas` (mantido para
    compatibilidade com quem já consome esta chave) soma os dois grupos, e
    `saldo` não muda — só a APRESENTAÇÃO ganha o detalhe do grupo, por
    item (`grupo`) e por total (`total_saidas_custeio`/
    `total_saidas_deducao_carne_leao`).

    UMA consulta (`select_related` na conta), número de consultas
    CONSTANTE em relação ao número de lançamentos.
    """
    lancamentos = list(
        LancamentoCaixa.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        .select_related("conta")
        .order_by("data", "id")
    )

    zero = Decimal("0.00")
    total_entradas = zero
    total_saidas_custeio = zero
    total_saidas_deducao_carne_leao = zero
    itens = []
    for lancamento in lancamentos:
        e_estorno = lancamento.estorno_de_id is not None
        sinal = -1 if e_estorno else 1
        contribuicao = sinal * lancamento.valor
        if lancamento.conta.natureza == NaturezaCaixa.RECEITA:
            total_entradas += contribuicao
            grupo = GRUPO_ENTRADA
        elif codigo_carne_leao_e_deducao_do_carne_leao(lancamento.conta.codigo_carne_leao):
            total_saidas_deducao_carne_leao += contribuicao
            grupo = GRUPO_SAIDA_DEDUCAO_CARNE_LEAO
        else:
            total_saidas_custeio += contribuicao
            grupo = GRUPO_SAIDA_CUSTEIO
        itens.append(
            {
                "lancamento_id": lancamento.id,
                "data": lancamento.data,
                "conta": lancamento.conta.codigo,
                "conta_nome": lancamento.conta.nome,
                "natureza": lancamento.conta.natureza,
                "grupo": grupo,
                "valor": lancamento.valor,
                "historico": lancamento.historico,
                "documento_origem": lancamento.documento_origem,
                "estorno_de_id": lancamento.estorno_de_id,
                "e_estorno": e_estorno,
            }
        )

    total_saidas = total_saidas_custeio + total_saidas_deducao_carne_leao
    return {
        "empresa_id": empresa.id,
        "data_inicio": inicio,
        "data_fim": fim,
        "itens": itens,
        "total_entradas": total_entradas,
        "total_saidas_custeio": total_saidas_custeio,
        "total_saidas_deducao_carne_leao": total_saidas_deducao_carne_leao,
        "total_saidas": total_saidas,
        "saldo": total_entradas - total_saidas,
    }
