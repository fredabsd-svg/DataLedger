"""Regras de domínio PURAS da escrituração — faixa de data e teto de
partidas (RC-77 e RC-79, confirmados pelo Fred em 2026-09-15; BL-158, BL-160).

**Por que este módulo existe, e por que ele não pode importar ORM.** A faixa
precisa valer em três lugares que não podem compartilhar um módulo com
modelo:

1. `apps.contabilidade.services.criar_lancamento` — o caminho de negócio, por
   onde passam a tela e a API;
2. `LancamentoContabil.data`, como **validador de campo do modelo** — o que
   faz o **admin do Django** respeitar a faixa (`apps/contabilidade/admin.py`
   registra `LancamentoContabilAdmin`, e o admin grava por `ModelForm`, que
   chama `full_clean()`; ele **nunca** chama `criar_lancamento`);
3. `apps/contabilidade/views_web.py`, que importa a mínima e a máxima para
   preencher `min`/`max` do campo de data como conveniência (DE-031 —
   conveniência, nunca defesa).

`models.py` não pode importar de `services.py` (`services.py` importa
`models.py`: erro circular na carga do app), então a fonte única da faixa
passou a ser este módulo, sem ORM e sem Django além de `ValidationError`
(exigência do contrato de validador de campo) e `timezone` (o "hoje" do fuso
configurado). `services.py` **importa** daqui e reexporta os nomes que a tela
já usa — uma definição, um número.

O achado que trouxe o item 2 para cá é do `arquiteto-senior`, em 2026-09-15,
ao conferir o que eu havia encontrado no admin de regime tributário: se a
recusa do RC-77 morasse só em `criar_lancamento`, **o admin criaria um
lançamento datado `9999-12-31`, invisível em todas as telas de operação
normal** — o BL-151 inteiro, que é a razão declarada de a DL-019 existir,
entrando por uma porta que ninguém havia olhado. É o item 2 da DE-034 (o
mesmo campo nas outras superfícies) aplicado à superfície administrativa.
"""

from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

# RC-77, confirmado pelo Fred em 2026-09-15 (docs/projeto/requisitos.md): a
# data de um lançamento fica entre 01/01/2000 e hoje + 30 dias.
#
# Por que existe um teto superior, e por que ele é o item que faz a DL-019
# existir (achado R6-4 da auditoria da rodada 6): um `9` digitado no lugar de
# um `2` grava o lançamento em `9999-12-31`, e ele **não aparece em nenhuma
# tela de operação normal** — nem Diário, nem Razão, nem Balancete, nem
# Conferência. O balancete do período CONCILIA, então nenhuma conferência
# acusa: para achar o valor o contador precisa suspeitar e alargar o período
# até o ano 9999. Os 30 dias à frente cobrem lançamento programado (razão
# dada pelo Fred).
#
# O piso de 2000 foi proposta do `arquiteto-senior` aceita pelo Fred; se
# aparecer escrituração anterior para importar (DL-010), **revalidar com ele**
# em vez de alargar por conta própria.
#
# A mínima é constante porque não se move; a máxima é FUNÇÃO porque se move
# todo dia, e uma constante calculada no import congelaria a faixa no momento
# em que o processo subiu (um servidor de longa duração passaria a recusar o
# dia seguinte).
DATA_MINIMA_LANCAMENTO = date(2000, 1, 1)
DIAS_FUTUROS_MAXIMOS_LANCAMENTO = 30

# RC-79, confirmado pelo Fred em 2026-09-15: teto de 200 partidas por
# lançamento, com recusa explícita — NUNCA truncamento (BL-91).
#
# O teto é regra de NEGÓCIO e mora aqui, não na tela (item 2 da DE-034, e o
# defeito concreto que a BL-160 fecha): até a DL-019 ele existia só como
# `LINHAS_MAXIMAS_LANCAMENTO` em `views_web.py`, e por isso a API **não tinha
# teto nenhum** — o mesmo campo, sem a mesma regra, na superfície ao lado.
# `criar_lancamento` é o único ponto por onde tela e API passam para gravar,
# então a recusa lá fecha as duas de uma vez. A tela importa esta constante e
# mantém, do lado dela, o teto de segurança de LEITURA (BL-120), que é outro
# número e serve para outra coisa: impedir que o servidor leia mais linhas do
# que o negócio aceita.
LIMITE_PARTIDAS_POR_LANCAMENTO = 200


def data_maxima_lancamento():
    """Última data aceita para um lançamento: hoje + `DIAS_FUTUROS_MAXIMOS_
    LANCAMENTO` (RC-77).

    Usa `timezone.localdate()`, o mesmo "hoje" que `estornar_lancamento` usa
    — nunca `date.today()`, que ignora o fuso configurado.
    """
    return timezone.localdate() + timedelta(days=DIAS_FUTUROS_MAXIMOS_LANCAMENTO)


def mensagem_de_data_de_lancamento_fora_da_faixa(data):
    """Mensagem de recusa se `data` estiver fora da faixa do RC-77; `None` se
    estiver dentro.

    Devolve mensagem em vez de levantar porque os consumidores precisam de
    tipos de exceção DIFERENTES para a MESMA regra:
    `apps.contabilidade.services.validar_data_de_lancamento` levanta
    `LancamentoInvalido` (exceção de domínio, que as duas views já traduzem
    para 400) e `validar_data_de_lancamento_do_modelo` levanta
    `ValidationError` (contrato obrigatório de validador de campo de modelo,
    usado pelo admin). Repetir a comparação nos dois lados é o que a DE-026
    existe para impedir.

    Recusa também o que não é `datetime.date` puro — inclusive
    `datetime.datetime`, que é subclasse de `date`: o campo do modelo é
    `DateField`, então um `datetime` seria TRUNCADO na gravação (perda
    silenciosa da hora que o chamador achava estar registrando) e, pior,
    quebraria a comparação de faixa com `TypeError` cru em vez de erro de
    domínio.
    """
    if isinstance(data, datetime) or not isinstance(data, date):
        return (
            f"A data do lançamento deve ser uma data (datetime.date); recebido "
            f"{type(data).__name__} ({data!r})."
        )
    maxima = data_maxima_lancamento()
    if data < DATA_MINIMA_LANCAMENTO or data > maxima:
        return (
            f"A data do lançamento ({data.strftime('%d/%m/%Y')}) está fora da faixa "
            f"aceita: de {DATA_MINIMA_LANCAMENTO.strftime('%d/%m/%Y')} até "
            f"{maxima.strftime('%d/%m/%Y')} (hoje + {DIAS_FUTUROS_MAXIMOS_LANCAMENTO} "
            "dias). Confira o ano digitado."
        )
    return None


def validar_data_de_lancamento_do_modelo(valor):
    """Validador de CAMPO DE MODELO para `LancamentoContabil.data`.

    O nome diz "do modelo" de propósito, para não ser confundido com
    `apps.contabilidade.services.validar_data_de_lancamento`: a regra é a
    MESMA (as duas chamam a função de mensagem acima), o que difere é a
    exceção — aqui `ValidationError`, porque é o único tipo que
    `full_clean()` sabe agregar num erro de formulário.

    É este validador que faz o **admin** respeitar a faixa. Ele NÃO cobre
    `objects.create()`/`bulk_create()`/`QuerySet.update()` — nenhum validador
    de campo cobre, porque o ORM não chama `full_clean()`; nesses caminhos
    quem garante a faixa é `criar_lancamento` (caminho de negócio) e, para o
    dado já gravado por fora, a categoria nova da Conferência
    (`localizar_lancamentos_com_data_fora_da_faixa`), que ACENDE A LUZ sobre
    o que a validação de entrada não conserta.
    """
    mensagem = mensagem_de_data_de_lancamento_fora_da_faixa(valor)
    if mensagem is not None:
        raise ValidationError(mensagem)
