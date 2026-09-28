import re
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.utils import timezone

# Fonte: Nota Técnica Conjunta CNPJ Alfanumérico — NT 2025.001, versão 1.00,
# de 25/04/2025 (ENCAT, Anexo I). Base legal: Instrução Normativa RFB
# nº 2.229, de 15/10/2024. O CNPJ alfanumérico está em vigor desde 31/07/2026
# e substitui, sem quebrar, o CNPJ puramente numérico (ver verificação de
# compatibilidade retroativa em docs/planos/DL-011-cnpj-alfanumerico.md).
#
# Formato oficial do campo (14 posições): 8 de raiz + 4 de ordem do
# estabelecimento, alfanuméricas em maiúsculas, seguidas de 2 dígitos
# verificadores sempre numéricos. Regex do Anexo I: [A-Z0-9]{12}[0-9]{2}.
_FORMATO_CNPJ = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")

# Máscara oficial aceita: exatamente "XX.XXX.XXX/XXXX-XX", nas posições
# fixas abaixo. Não removemos "." "/" "-" onde quer que apareçam: isso
# aceitaria entradas absurdas como "../-11222333000181" (achado 6 da
# auditoria da etapa DL-011), que só por coincidência sobra com 14
# caracteres depois de tirar os separadores de qualquer posição. A máscara
# só é reconhecida no formato exato; qualquer outra combinação de separador
# é tratada como caractere inválido (e cai no ramo de erro abaixo).
#
# O último grupo é [A-Za-z0-9]{2}, não [0-9]{2}: se restringíssemos aqui a
# só dígitos, um CNPJ mascarado com letra na posição do DV (ex.:
# "11.222.333/0001-8A") deixaria de casar com esta regex e cairia direto no
# erro genérico de "máscara mal formada" — sem dizer que o problema
# específico é letra onde só pode haver número. Quem impõe "DV é numérico"
# é só _FORMATO_CNPJ, depois da máscara já ter sido removida (reauditoria da
# etapa DL-011, ajuste 2): uma regra, um lugar, uma mensagem específica.
_REGEX_MASCARA = re.compile(
    r"^([A-Za-z0-9]{2})\.([A-Za-z0-9]{3})\.([A-Za-z0-9]{3})/([A-Za-z0-9]{4})-([A-Za-z0-9]{2})$"
)

# Sem máscara: exatamente 14 caracteres alfanuméricos ASCII. Restringir a
# ASCII aqui — e checar o conjunto de caracteres ANTES de aplicar .upper() —
# evita que uma letra de largura variável mude de tamanho na conversão de
# caixa (ex.: "ß".upper() == "SS", 1 caractere virando 2; achado 3 da
# auditoria da etapa DL-011). str.upper() do Python segue Unicode, não é
# seguro aplicar antes de restringir o alfabeto a A-Z/a-z/0-9.
_REGEX_SEM_MASCARA = re.compile(r"^[A-Za-z0-9]{14}$")

# Pesos do dígito verificador (módulo 11), Anexo I da NT 2025.001. O cálculo
# é o mesmo algoritmo histórico do CNPJ numérico; a única mudança da nota é
# que cada caractere entra na soma pelo valor ASCII menos 48, em vez de
# int(caractere). Para dígitos '0'-'9' os dois valores coincidem, por isso o
# algoritmo novo reproduz exatamente o DV dos CNPJs numéricos já cadastrados
# (compatibilidade retroativa conferida contra CNPJs numéricos válidos
# conhecidos e, na auditoria da etapa, contra 200 mil gerados — ver
# test_validators.py e o plano da etapa). Para letras, ord(c) - 48 dá A=17,
# B=18, C=19 e assim por diante.
_PESOS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

# A nota técnica registra que as letras I, O, U, Q e F "talvez" devam ser
# excluídas da raiz/ordem, mas afirma textualmente que essa exclusão "precisa
# ser confirmada" pela Receita Federal. Não implementamos essa exclusão:
# recusar um CNPJ legítimo por uma regra ainda não confirmada é pior do que
# aceitar um que a Receita venha a não emitir. Revisitar quando houver
# confirmação oficial (pendência registrada no plano da etapa DL-011).


def normalizar_cnpj(valor):
    """Remove a máscara oficial e converte para maiúsculas.

    Função única de normalização (canonização), usada tanto por
    ``validar_cnpj`` quanto por todo caminho de gravação — ``Empresa.save()``,
    ``Estabelecimento.save()``, o formulário e o serializer. É essencial que
    seja a mesma função em todo lugar: se a validação normalizasse só para
    checar o formato e descartasse o resultado (como a primeira versão desta
    etapa fazia), "AB123CDE000155" e "ab123cde000155" passariam os dois pela
    validação e seriam gravados como dois registros diferentes, apesar de
    ``unique=True`` — porque o Postgres compara texto com diferença de caixa
    (achado 1 da auditoria da etapa DL-011).

    Levanta ``ValidationError`` para tipo, caractere ou máscara inválidos —
    sempre antes de qualquer conversão de caixa, nunca depois (ver o
    comentário de ``_REGEX_SEM_MASCARA`` sobre por que a ordem importa).
    """
    if not isinstance(valor, str):
        # CNPJ chega como texto em todos os caminhos legítimos (formulário,
        # serializer, banco). Um `None` ou `int` aqui indica uso incorreto da
        # função, não um CNPJ malformado digitado por alguém — mas ainda
        # assim deve virar ValidationError, não AttributeError, para quem
        # chama esta função como parte da validação de um campo (achado 5 da
        # auditoria da etapa DL-011).
        raise ValidationError("CNPJ deve ser um texto.")

    # Espaço em branco na borda (comum em CNPJ colado de planilha ou de
    # página web) é descartado aqui, antes das regexes de máscara. Sem
    # isso, o campo de formulário aceitava (CharField do Django tem
    # strip=True por padrão) e a API recusava o mesmo valor — porque este
    # código roda antes do trim_whitespace do DRF (reauditoria da etapa
    # DL-011, ajuste 1).
    #
    # Correção de comentário (achado R8 da reauditoria, rodada 2): a frase
    # anterior aqui dizia que só espaço comum era removido. Isso é falso.
    # `str.strip()` sem argumento remove qualquer caractere da classe
    # Unicode `str.isspace()` — inclusive NBSP (U+00A0), tabulação ("\t"),
    # quebra de linha ("\n", "\r") e outros espaços Unicode (ex.:
    # U+2000-U+200A, U+3000). O comportamento real é mais permissivo do que
    # o texto antigo afirmava, e é o desejável: CNPJ colado de página HTML
    # costuma vir com NBSP. Caractere de largura zero (U+200B, zero-width
    # space) NÃO é removido, porque não pertence à classe `str.isspace()` —
    # e por isso continua sendo recusado como caractere inválido,
    # corretamente.
    valor = valor.strip()

    mascarado = _REGEX_MASCARA.fullmatch(valor)
    if mascarado:
        sem_mascara = "".join(mascarado.groups())
    elif _REGEX_SEM_MASCARA.fullmatch(valor):
        sem_mascara = valor
    else:
        raise ValidationError(
            "CNPJ deve ter 14 caracteres alfanuméricos (A-Z, 0-9), com ou sem "
            "a máscara XX.XXX.XXX/XXXX-XX."
        )

    return sem_mascara.upper()


def _calcular_digito_verificador(caracteres, pesos):
    """Soma módulo 11 conforme o Anexo I da NT 2025.001.

    ``caracteres`` e ``pesos`` devem ter o mesmo tamanho, na mesma ordem
    posicional; cada caractere entra na soma como ``ord(c) - 48``.
    """
    soma = sum((ord(c) - 48) * peso for c, peso in zip(caracteres, pesos, strict=True))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def validar_cnpj(valor):
    """Valida um CNPJ (numérico ou alfanumérico) pelos dígitos verificadores.

    Aceita o valor com ou sem máscara e em qualquer caixa; levanta
    ValidationError para tamanho, formato ou dígitos verificadores
    inválidos. Não confirma que o CNPJ existe de fato ou está ativo — isso
    exigiria consulta externa, fora do escopo desta etapa.

    Não persiste o valor normalizado: quem grava o dado (Model.save()) é
    responsável por canonizar com ``normalizar_cnpj`` antes de salvar. Esta
    função só valida.
    """
    cnpj = normalizar_cnpj(valor)

    if not _FORMATO_CNPJ.fullmatch(cnpj):
        raise ValidationError(
            "CNPJ deve ter 14 caracteres: 12 alfanuméricos (A-Z, 0-9) seguidos "
            "de 2 dígitos verificadores numéricos."
        )

    # CNPJ zerado: o próprio algoritmo do módulo 11 calcularia DV "00" para
    # "000000000000", que coincide com os dígitos informados e passaria a
    # verificação por acidente. A NT 2025.001 manda rejeitar esse caso
    # explicitamente. Verificação exaustiva (auditoria da etapa DL-011): das
    # 36 sequências possíveis de 14 caracteres iguais (0-9, A-Z), só esta
    # tem o DV calculado coincidindo com os dígitos informados — todas as
    # demais já falham no cálculo abaixo, sem precisar de exceção especial.
    if cnpj == "0" * 14:
        raise ValidationError("CNPJ inválido.")

    base = cnpj[:12]
    primeiro_digito = _calcular_digito_verificador(base, _PESOS[1:])
    segundo_digito = _calcular_digito_verificador(base + primeiro_digito, _PESOS)

    if cnpj[12:] != primeiro_digito + segundo_digito:
        raise ValidationError("CNPJ inválido: dígitos verificadores não conferem.")


# ---------------------------------------------------------------------------
# CPF — DL-038 (R2). PESQUISA REALIZADA em 2026-09-25 pelo `auxiliar-pesquisa`
# antes de escrever este algoritmo: a Receita Federal publica o algoritmo do
# DV do CNPJ alfanumérico (NT Conjunta 2025.001 — ver _PESOS acima), mas
# **não foi localizada** nenhuma publicação oficial da RFB com o algoritmo
# matemático do DV do CPF — a prática dela é validar por consulta
# (webservice), não publicar a fórmula. Isto está declarado aqui como
# LIMITE, não escondido.
#
# ⚠️ FONTE, portanto, NÃO OFICIAL: o algoritmo abaixo é a convenção técnica
# de mercado, replicada de forma idêntica e sem divergência em toda fonte
# consultada — biblioteca `validate-docbr` (`validate_docbr/CPF.py`,
# https://github.com/alvarofpp/validate-docbr, amplamente usada em produção
# no Brasil) e artigos técnicos independentes convergentes (Secretaria da
# Fazenda do Paraná, https://www.fazenda.pr.gov.br/Pagina/calculo-digito-
# verificador; macoratti.net, https://www.macoratti.net/alg_cpf.htm).
# Cruzamento de múltiplas fontes independentes é o que sustenta usar isto
# como regra técnica de ENTRADA (formato de dado, não norma fiscal) — mas
# não é fundamento normativo, e não deve ser citado como tal. Se algum dia
# for necessário fundamento oficial, a pergunta é do Fred, não presunção
# nossa (mesma régua da DE-010).
_PESOS_CPF_PRIMEIRO_DIGITO = [10, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_CPF_SEGUNDO_DIGITO = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]

# Máscara oficial de apresentação do CPF: "XXX.XXX.XXX-XX". Mesma política
# de rigor da máscara do CNPJ (_REGEX_MASCARA acima): só o formato EXATO é
# reconhecido como máscara — qualquer outra combinação de "." ou "-" é
# caractere inválido, nunca separador a descartar de qualquer posição
# (mesmo raciocínio do achado 6 da auditoria DL-011).
_REGEX_MASCARA_CPF = re.compile(r"^([0-9]{3})\.([0-9]{3})\.([0-9]{3})-([0-9]{2})$")

# Sem máscara: exatamente 11 dígitos. Diferente do CNPJ, o CPF não tem
# variante alfanumérica confirmada em nenhuma fonte — só dígitos.
_REGEX_SEM_MASCARA_CPF = re.compile(r"^[0-9]{11}$")

# As 10 sequências de dígito único repetido (RC-2 do plano DL-038: "sequência
# repetida" recusada). Motivo MATEMÁTICO, não convenção arbitrária: se os 9
# dígitos-base são todos iguais a k, a primeira soma pondera para 54k e a
# segunda para 65k — as duas somas produzem o MESMO dígito verificador k
# pelo cálculo abaixo, então as dez sequências "passam" no módulo 11 por
# coincidência estrutural do algoritmo. Toda fonte consultada (nota acima)
# trata isso como checagem SEPARADA do cálculo do DV, nunca decorrente dele
# — por isso a rejeição explícita aqui, no mesmo espírito do "CNPJ zerado"
# em validar_cnpj.
_SEQUENCIAS_REPETIDAS_CPF = frozenset(str(digito) * 11 for digito in range(10))


def normalizar_cpf(valor):
    """Remove a máscara oficial do CPF — texto de 11 dígitos, sem máscara.

    Função única de normalização (canonização), no mesmo molde de
    ``normalizar_cnpj``: usada por ``validar_cpf`` e por todo caminho de
    gravação, para que o mesmo CPF com ou sem máscara nunca vire dois
    registros diferentes.

    Levanta ``ValidationError`` para tipo, caractere ou máscara inválidos —
    sempre antes de qualquer outra checagem.
    """
    if not isinstance(valor, str):
        raise ValidationError("CPF deve ser um texto.")

    # Mesmo tratamento de espaço em branco na borda do normalizar_cnpj —
    # ver o comentário lá sobre a classe Unicode que str.strip() cobre.
    valor = valor.strip()

    mascarado = _REGEX_MASCARA_CPF.fullmatch(valor)
    if mascarado:
        sem_mascara = "".join(mascarado.groups())
    elif _REGEX_SEM_MASCARA_CPF.fullmatch(valor):
        sem_mascara = valor
    else:
        raise ValidationError(
            "CPF deve ter 11 dígitos numéricos, com ou sem a máscara XXX.XXX.XXX-XX."
        )

    return sem_mascara


def _calcular_digito_verificador_cpf(digitos, pesos):
    """Soma módulo 11 do CPF — ver a nota de fonte acima de `_PESOS_CPF_
    PRIMEIRO_DIGITO`. `digitos` é uma sequência de caracteres numéricos;
    diferente do CNPJ alfanumérico, aqui é sempre `int(c)` direto (CPF não
    tem letra)."""
    soma = sum(int(c) * peso for c, peso in zip(digitos, pesos, strict=True))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def validar_cpf(valor):
    """Valida um CPF pelos dígitos verificadores (fonte não oficial — ver o
    comentário de `_PESOS_CPF_PRIMEIRO_DIGITO`).

    Aceita o valor com ou sem máscara; levanta ValidationError para tamanho,
    formato, sequência repetida ou dígitos verificadores inválidos. Não
    confirma que o CPF existe de fato — isso exigiria consulta externa,
    fora do escopo desta etapa.

    Não persiste o valor normalizado: quem grava o dado é responsável por
    canonizar com ``normalizar_cpf`` antes de salvar. Esta função só valida.
    """
    cpf = normalizar_cpf(valor)

    if not _REGEX_SEM_MASCARA_CPF.fullmatch(cpf):
        raise ValidationError("CPF deve ter 11 dígitos numéricos.")

    if cpf in _SEQUENCIAS_REPETIDAS_CPF:
        raise ValidationError("CPF inválido: sequência de dígito repetido não é um CPF válido.")

    primeiro_digito = _calcular_digito_verificador_cpf(cpf[:9], _PESOS_CPF_PRIMEIRO_DIGITO)
    segundo_digito = _calcular_digito_verificador_cpf(
        cpf[:9] + primeiro_digito, _PESOS_CPF_SEGUNDO_DIGITO
    )

    if cpf[9:] != primeiro_digito + segundo_digito:
        raise ValidationError("CPF inválido: dígitos verificadores não conferem.")


# ---------------------------------------------------------------------------
# Faixa de `vigencia_inicio` de regime tributário (RC-85 confirmado, HI-07
# hipótese) — achado R6-6 da auditoria DL-017 rodada 6, BL-200.
#
# O defeito medido: `POST regime-tributario {"vigencia_inicio":"9999-12-31"}`
# devolvia 201. `9999-12-31` é `date.max`, não existe data posterior, a regra
# de vigência crescente (`registrar_regime_tributario`) exige que a próxima
# comece DEPOIS — e não havia `PUT`, `DELETE` nem tela de edição. Um dígito
# errado congelava para sempre o histórico do dado que governa toda a
# apuração fiscal da empresa, e só acesso direto ao banco desfazia.
#
# LIMITE SUPERIOR — REGRA CONFIRMADA (RC-85, Fred em 2026-09-15, resposta
# literal "Não" a "o escritório registra regime com vigência futura?"):
# `vigencia_inicio` nunca é posterior a HOJE. Isto fecha a armadilha por
# construção, não por vigilância: `date.max` não entra mais, e amanhã sempre
# existe uma data posterior à última registrada.
#
# LIMITE INFERIOR — HIPÓTESE, NÃO REGRA CONFIRMADA (HI-07): o piso de
# 01/01/2000 é o mesmo do RC-77, que o Fred confirmou para DATA DE
# LANÇAMENTO. Ninguém o confirmou para regime tributário — estender é
# presunção, e está registrado como hipótese em docs/projeto/requisitos.md
# (HI-07) para ser perguntado. Sem piso nenhum, `0001-01-01` entraria, o que
# mantém metade do defeito; com este piso declarado como hipótese, o
# comportamento é seguro e a dívida fica visível. Se houver empresa com
# regime documentado antes de 2000, o piso BAIXA — decisão do Fred, não
# nossa.
VIGENCIA_REGIME_MINIMA = date(2000, 1, 1)


def vigencia_regime_maxima():
    """Hoje — a última `vigencia_inicio` aceita para um regime (RC-85).

    Função, não constante: "hoje" se move, e uma constante calculada no
    import congelaria o teto no momento em que o processo subiu (um servidor
    de longa duração passaria a recusar o dia seguinte). `timezone.
    localdate()` respeita o fuso configurado; `date.today()` não.
    """
    return timezone.localdate()


def mensagem_de_vigencia_de_regime_fora_da_faixa(vigencia_inicio):
    """Mensagem de recusa se `vigencia_inicio` estiver fora da faixa; `None`
    se estiver dentro.

    Devolve mensagem em vez de levantar porque os dois consumidores precisam
    de tipos de exceção diferentes e a REGRA precisa ser uma só:
    `apps.empresas.services.registrar_regime_tributario` levanta `ValueError`
    (que a API já traduz para 400) e `validar_vigencia_de_regime` levanta
    `ValidationError` (contrato obrigatório de validador de campo de modelo,
    usado pelo admin). Duplicar a comparação nos dois lados é exatamente o
    que a DE-026 existe para impedir.

    Recusa também o que não é `datetime.date` puro (inclusive `datetime`,
    que é subclasse de `date`): o campo é `DateField`, um `datetime` seria
    truncado na gravação, e a comparação de faixa estouraria `TypeError`
    cru em vez de erro de domínio.
    """
    if isinstance(vigencia_inicio, datetime) or not isinstance(vigencia_inicio, date):
        return (
            "A vigência do regime tributário deve ser uma data (datetime.date); "
            f"recebido {type(vigencia_inicio).__name__} ({vigencia_inicio!r})."
        )
    maxima = vigencia_regime_maxima()
    if vigencia_inicio > maxima:
        return (
            f"A vigência do regime tributário não pode ser futura: "
            f"{vigencia_inicio.strftime('%d/%m/%Y')} é posterior a hoje "
            f"({maxima.strftime('%d/%m/%Y')}). Confira o ano digitado."
        )
    if vigencia_inicio < VIGENCIA_REGIME_MINIMA:
        return (
            f"A vigência do regime tributário não pode ser anterior a "
            f"{VIGENCIA_REGIME_MINIMA.strftime('%d/%m/%Y')}; recebido "
            f"{vigencia_inicio.strftime('%d/%m/%Y')}."
        )
    return None


def validar_vigencia_de_regime(valor):
    """Validador de CAMPO DE MODELO para `HistoricoRegimeTributario.
    vigencia_inicio` (DE-034 item 2 — o mesmo campo nas outras superfícies).

    A regra já está em `registrar_regime_tributario`, por onde a API passa.
    Ela NÃO alcança o **admin do Django** (`HistoricoRegimeTributarioInline`,
    em `apps/empresas/admin.py`), que grava por `ModelForm` e nunca chama o
    serviço — a segunda, e única outra, superfície de escrita deste campo
    hoje (não existe tela do produto para regime tributário). Um validador de
    campo é chamado por `full_clean()`, que é o que o `ModelForm` do admin
    executa, então a faixa vale nas duas portas sem reimplementar a
    comparação.

    Não cobre `objects.create()`/`bulk_create()` — nenhum validador de campo
    cobre, porque o ORM não chama `full_clean()`. O caminho de negócio
    (`registrar_regime_tributario`) é quem garante isso ali.
    """
    mensagem = mensagem_de_vigencia_de_regime_fora_da_faixa(valor)
    if mensagem is not None:
        raise ValidationError(mensagem)


# ---------------------------------------------------------------------------
# DL-046 (RC-129) — CAEPF (Cadastro de Atividade Econômica da Pessoa
# Física), campo opcional no cadastro de cliente pessoa física.
#
# FONTE (consultada em 2026-09-26): documentação oficial do Cadastro
# Compartilhado da Receita Federal (SERPRO),
# https://bcadastros.serpro.gov.br/documentacao/cadastro_caepf/ — o número
# completo (`nroAepfCompleto`) tem **14 posições**: os **9 primeiros dígitos
# do CPF** do titular, seguidos de um **número resumido de 5 posições**
# (`nroAepfResumido`) que identifica a inscrição dentro daquele CPF. Exemplo
# do próprio documento: CPF começando em "000000025" produz CAEPF
# "00000002500171" (prefixo "000000025" + resumido "00171").
#
# ⚠️ **A fonte NÃO documenta o algoritmo de cálculo de um dígito
# verificador** para o CAEPF (só a composição estrutural do número) — outras
# fontes não oficiais mencionam "3 dígitos sequenciais + 2 DV" dentro do
# resumido de 5 posições, mas nenhuma delas publica a fórmula do DV, e a
# fonte oficial (SERPRO) não confirma essa divisão interna. Por isso este
# validador confere SÓ o que a fonte oficial garante — 14 dígitos numéricos
# e os 9 primeiros iguais aos 9 primeiros dígitos do CPF informado — e NUNCA
# tenta recalcular um dígito verificador que nenhuma fonte confirmada
# documenta (instrução da tarefa: "se não achar fonte, só valide dígitos e
# registre HI" — ver HI-31 em docs/projeto/requisitos.md).
_REGEX_CAEPF = re.compile(r"^[0-9]{14}$")


def normalizar_caepf(valor):
    """Remove espaço/máscara do CAEPF — texto de 14 dígitos, sem máscara.

    Mesmo molde de `normalizar_cpf`/`normalizar_cnpj`: aceita dígitos com ou
    sem separador (o cadastro compartilhado costuma exibir o número
    resumido como `NNN.NNNNN`, mas a fonte oficial não fixa uma máscara
    única) — remove qualquer caractere que não seja dígito antes de validar
    o tamanho, então "000.000.025.001.71" e "00000002500171" normalizam
    para o mesmo valor.
    """
    if not isinstance(valor, str):
        raise ValidationError("CAEPF deve ser um texto.")
    valor = valor.strip()
    if valor == "":
        return valor
    apenas_digitos = re.sub(r"[^0-9]", "", valor)
    return apenas_digitos


def validar_caepf(valor, *, cpf=None):
    """Valida o FORMATO do CAEPF (14 dígitos) e, quando `cpf` for informado,
    a COERÊNCIA estrutural com ele (os 9 primeiros dígitos do CAEPF são os
    9 primeiros dígitos do CPF do titular — fonte SERPRO, ver o comentário
    acima). NÃO valida dígito verificador: nenhuma fonte confirmada
    documenta o algoritmo (HI-31).

    `cpf` é opcional aqui (a validação cruzada com o CPF da própria empresa
    é responsabilidade de quem chama — `Empresa.clean()`/`EmpresaSerializer`
    — que tem os dois valores disponíveis); passado ele, a coerência é
    conferida nesta mesma função para não duplicar a comparação.
    """
    caepf = normalizar_caepf(valor)
    if not _REGEX_CAEPF.fullmatch(caepf):
        raise ValidationError("CAEPF deve ter 14 dígitos numéricos.")
    if cpf:
        cpf_normalizado = normalizar_cpf(cpf)
        if caepf[:9] != cpf_normalizado[:9]:
            raise ValidationError(
                "CAEPF não corresponde ao CPF desta empresa: os 9 primeiros "
                "dígitos do CAEPF devem ser os 9 primeiros dígitos do CPF do "
                "titular (Cadastro Compartilhado da Receita Federal)."
            )


# ---------------------------------------------------------------------------
# DL-046, fatia 3 (RC-127, HI-34) — código de ocupação do Carnê-Leão Web.
#
# Tabela oficial ("Códigos de ocupações", Manual do Carnê-Leão, Receita
# Federal — publicada em 10/07/2023, atualizada em 30/01/2024, consultada
# em 2026-09-27): 3 dígitos numéricos ("Código da ocupação: 03 caracteres",
# página "Formato do arquivo de Escrituração"). Os seis códigos militares e
# "sem ocupação" aparecem na página como 1 ou 2 dígitos ("10", "20", "30",
# "40", "50", "0") — preenchidos aqui com zero à esquerda até 3 posições,
# para bater com a largura fixa do campo; nenhum outro valor foi alterado
# em relação ao texto publicado, inclusive o parêntese não fechado do
# código 101 (assim mesmo na página oficial — conferido no HTML de
# origem). O código 229 segue na tabela porque a própria página o mantém,
# marcado "até o ano-calendário 2023"; este validador não é sensível a
# ano-calendário (só confere formato e pertencimento à tabela), então
# aceitar 229 evita recusar um lançamento histórico legítimo — quem
# escritura decide qual código cabe ao ano do lançamento.
TABELA_OCUPACOES_CARNE_LEAO_WEB = {
    "101": (
        "Membro do Poder Executivo (Presidente da República, Vice-Presidente da República, "
        "Ministro de Estado, Governador, Vice-Governador, Prefeito, Vice-Prefeito"
    ),
    "102": (
        "Membro do Poder Judiciário (Ministro, Juiz e Desembargador) e de Tribunal de Contas "
        "(Ministro e Conselheiro)"
    ),
    "103": "Membro do Poder Legislativo (Senador, Deputado Federal, Deputado Estadual e Vereador)",
    "104": "Membro do Ministério Público (Procurador e Promotor)",
    "105": (
        "Dirigente superior da administração pública (ocupante de cargo de direção, chefia, "
        "assessoria e de natureza especial), inclusive os das fundações públicas e autarquias"
    ),
    "106": "Diplomata e afins",
    "107": "Servidor das carreiras do Poder Legislativo",
    "108": "Servidor das carreiras do Ministério Público",
    "109": (
        "Servidor das carreiras do Poder Judiciário, Oficial de Justiça, Auxiliar, Assistente e "
        "Analista Judiciário"
    ),
    "110": (
        "Advogado do setor público, Procurador da Fazenda, Consultor Jurídico, Procurador de "
        "autarquias e fundações públicas, Defensor Público"
    ),
    "111": "Servidor das carreiras de auditoria fiscal e de fiscalização",
    "112": "Servidor das carreiras do Banco Central, CVM e Susep",
    "113": "Delegado de Polícia e outros servidores das carreiras de polícia, exceto militar",
    "114": (
        "Servidor das carreiras de gestão governamental, analista, gestor e técnico de planejamento"
    ),
    "115": "Servidor das carreiras de ciência e tecnologia",
    "116": (
        "Servidor das demais carreiras da administração pública direta, autárquica e fundacional"
    ),
    "117": "Titular de Cartório",
    "118": (
        "Dirigente ou administrador de partido político, organização patronal, sindical, "
        "filantrópica e religiosa"
    ),
    "120": (
        "Dirigente, presidente e diretor de empresa industrial, comercial ou prestadora de serviços"
    ),
    "121": "Presidente e diretor de empresa pública e sociedade de economia mista",
    "130": "Gerente ou supervisor de empresa industrial, comercial ou prestadora de serviços",
    "131": "Gerente ou supervisor de empresa pública e sociedade de economia mista",
    "140": (
        "Presidente, diretor, gerente e supervisor de organismo internacional e de organização "
        "não-governamental"
    ),
    "211": "Matemático, estatístico, atuário e afins",
    "212": (
        "Analista de sistemas, desenvolvedor de software, administrador de redes e bancos de dados "
        "e outros especialistas em informática (exceto técnico)"
    ),
    "213": "Físico, químico, meteorologista, geólogo, oceanógrafo e afins",
    "214": "Engenheiro, arquiteto e afins",
    "215": "Piloto de aeronaves, comandante de embarcações e oficiais de máquinas",
    "221": "Biólogo, biomédico e afins",
    "222": "Agrônomo e afins",
    "224": "Profissional da educação física (exceto professor)",
    "225": "Médico",
    "226": "Odontólogo",
    "227": "Enfermeiro de nível superior, nutricionista, farmacêutico e afins",
    "228": "Veterinário, patologista (veterinário) e zootecnista",
    "229": (
        "Fonoaudiólogo, fisioterapeuta, terapeuta ocupacional e afins (até o ano-calendário 2023)"
    ),
    "230": "Fonoaudiólogo (a partir do ano-calendário 2024)",
    "231": "Fisioterapeuta (a partir do ano-calendário 2024)",
    "232": "Terapeuta ocupacional (a partir do ano-calendário 2024)",
    "241": "Advogado",
    "250": "Sociólogo e cientista político",
    "251": "Antropólogo e arqueólogo",
    "252": "Economista, administrador, contador, auditor e afins",
    "253": "Profissional de marketing, de publicidade e de comercialização",
    "254": "Psicanalista",
    "255": "Psicólogo",
    "256": "Geógrafo",
    "257": "Historiador",
    "258": "Assistente social e economista doméstico",
    "259": "Filósofo",
    "261": "Jornalista e repórter",
    "263": "Sacerdote ou membro de ordens ou seitas religiosas",
    "264": "Tradutor, intérprete, filólogo",
    "265": "Bibliotecário, documentalista, arquivólogo, museólogo",
    "266": "Escritor, crítico, redator",
    "271": "Locutor, comentarista",
    "272": "Ator, diretor de espetáculos",
    "273": "Cantor e compositor",
    "274": "Músico, arranjador, regente de orquestra ou coral",
    "275": "Desenhista industrial (designer), escultor, pintor artístico e afins",
    "276": "Cenógrafo, decorador de interiores",
    "277": "Empresário e produtor de espetáculos",
    "279": "Outros profissionais do espetáculo e das artes",
    "290": "Professor na educação infantil",
    "291": "Professor do ensino fundamental",
    "292": "Professor do ensino médio",
    "293": "Professor do ensino profissional",
    "294": "Professor do ensino superior",
    "295": "Instrutor e professor de escolas livres",
    "296": "Pedagogo, orientador educacional",
    "311": "Técnico em ciências físicas e químicas",
    "312": "Técnico em construção civil, de edificações e obras de infra-estrutura",
    "313": "Técnico em eletro-eletrônica e fotônica",
    "314": "Técnico em metalmecânica",
    "316": "Técnico em mineralogia e geologia",
    "317": "Técnico em informática",
    "318": "Desenhista técnico e modelista",
    "319": "Outros técnicos de nível médio das ciências físicas, químicas, engenharia e afins",
    "320": "Técnico em biologia",
    "321": "Técnico da produção agropecuária",
    "322": "Técnico da ciência da saúde humana",
    "323": "Técnico da ciência da saúde animal",
    "324": "Técnico de laboratório, Raios-X e outros equipamentos e instrumentos de diagnóstico",
    "325": "Técnico de bioquímica e da biotecnologia",
    "328": "Técnico de conservação, dissecação e empalhamento de corpos",
    "351": "Técnico das ciências administrativas e contábeis",
    "352": "Técnico de inspeção, fiscalização e coordenação administrativa",
    "353": "Agente de Bolsa de Valores, câmbio e outros serviços financeiros",
    "354": "Agente e representante comercial, corretor, leiloeiro e afins",
    "355": "Corretor e Administrador de Imóveis",
    "371": "Técnico de serviços culturais",
    "372": (
        "Cinegrafista, fotógrafo e outros técnicos em operação de máquinas de tratamento de dados"
    ),
    "373": "Técnico em operação de estações de rádio e televisão",
    "374": "Técnico em operação de aparelhos de sonorização, cenografia e projeção",
    "375": "Decorador e vitrinista",
    "376": "Apresentador, artistas de artes populares e modelos",
    "377": "Atleta, desportista e afins",
    "391": "Outros técnicos de nível médio",
    "410": "Bancário, economiário, escriturário, secretário, assistente e auxiliar administrativo",
    "420": "Trabalhador de atendimento ao público, caixa, despachante, recenseador e afins",
    "511": "Comissário de bordo, guia de turismo, agente de viagem e afins",
    "512": "Trabalhador dos serviços domésticos em geral",
    "513": "Trabalhador dos serviços de hotelaria e alimentação",
    "514": "Trabalhador dos serviços de administração, conservação e manutenção de edifícios",
    "515": "Trabalhador dos serviços de saúde",
    "516": "Trabalhador dos serviços de embelezamento e cuidados pessoais",
    "517": "Trabalhador dos serviços de proteção e segurança (exceto militar)",
    "518": (
        "Motorista e condutor do transporte de passageiros (motorista de taxi, ônibus, pequena "
        "embarcação etc)"
    ),
    "519": "Outros trabalhadores de serviços diversos",
    "529": "Vendedor e prestador de serviços do comércio, ambulante, caixeiro-viajante e camelô",
    "610": "Produtor na exploração agropecuária",
    "620": "Trabalhador na exploração agropecuária",
    "630": "Pescador, caçador e extrativista florestal",
    "640": "Operador de máquina agropecuária e florestal",
    "710": "Trabalhador da indústria extrativa e da construção civil",
    "720": "Trabalhador da transformação de metais e compósitos",
    "730": "Trabalhador da fabricação e instalação eletro-eletrônica",
    "740": "Montador de aparelhos e instrumentos de precisão e musicais",
    "750": "Joalheiro, vidreiro, ceramista e afins",
    "760": "Trabalhador das indústrias têxteis, do curtimento, do vestuário e das artes gráficas",
    "770": "Trabalhador das indústrias de madeira e do mobiliário",
    "780": (
        "Condutor e operador de robôs, veículos de equipamentos de movimentação de carga e afins"
    ),
    "810": "Trabalhador das indústrias química, petroquímica, borracha e plástico e afins",
    "820": "Trabalhador de instalações siderúrgicas e de materiais de construção",
    "830": "Trabalhador de instalações e máquinas de fabricação de celulose e papel",
    "840": "Trabalhador da fabricação de alimentos, bebidas, fumo e de agroindústrias",
    "860": "Operador de instalações de produção e distribuição de energia",
    "870": "Trabalhador de outras instalações agroindustriais",
    "900": "Trabalhador de reparação e manutenção",
    "010": "Militar da Aeronáutica",
    "020": "Militar do Exército",
    "030": "Militar da Marinha",
    "040": "Policial Militar",
    "050": "Bombeiro Militar",
    "000": "Sem ocupações",
}


def validar_codigo_ocupacao(valor):
    """Valida o FORMATO (3 dígitos numéricos) e o PERTENCIMENTO de `valor` à
    tabela oficial de ocupações do Carnê-Leão Web
    (`TABELA_OCUPACOES_CARNE_LEAO_WEB`, acima). Usado no cadastro da pessoa
    física (`Empresa.codigo_ocupacao`) e, por sobreposição opcional, na
    conta de rendimento do livro-caixa
    (`apps.livro_caixa.models.ContaLivroCaixa.codigo_ocupacao`) — a mesma
    regra nos dois lugares, sem duplicar a tabela.
    """
    if not isinstance(valor, str):
        raise ValidationError("Código de ocupação deve ser um texto.")
    codigo = valor.strip()
    if not re.fullmatch(r"[0-9]{3}", codigo):
        raise ValidationError(
            "Código de ocupação deve ter 3 dígitos numéricos (tabela oficial "
            "de ocupações do Carnê-Leão Web)."
        )
    if codigo not in TABELA_OCUPACOES_CARNE_LEAO_WEB:
        raise ValidationError(
            f"Código de ocupação '{codigo}' não consta na tabela oficial do Carnê-Leão Web."
        )
