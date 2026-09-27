"""Serviços do livro-caixa (DL-046, fatia 1) — RC-113/RC-114/RC-128.

Mesmo desenho geral de `apps.contabilidade.services` (criação com
validação centralizada, idempotência por impressão digital, estorno
rastreável, trilha de auditoria na MESMA transação), simplificado para o
regime de CAIXA: um lançamento tem uma conta e um valor só (nunca partidas
dobradas — isso é a contabilidade).
"""

import hashlib
import json
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from apps.auditoria.services import registrar
from apps.core.dinheiro import ValorMonetarioInvalido, casas_decimais, para_decimal
from apps.core.restricoes import mensagens_de, restricao_como_400
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.empresas.validators import normalizar_cnpj, normalizar_cpf
from apps.livro_caixa.models import (
    ContaLivroCaixa,
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
        "estorno_de_id": estorno_de_id,
    }
    bruto = json.dumps(estrutura, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def criar_conta_livro_caixa(
    *, empresa, codigo, nome, natureza, codigo_carne_leao, ativa=True, criado_por=None, request=None
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
