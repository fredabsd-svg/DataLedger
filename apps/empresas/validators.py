import re

from django.core.exceptions import ValidationError

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

    # Espaço em branco na borda (comum em CNPJ colado de planilha) é
    # descartado aqui, antes das regexes de máscara. Sem isso, o campo de
    # formulário aceitava (CharField do Django tem strip=True por padrão) e
    # a API recusava o mesmo valor — porque este código roda antes do
    # trim_whitespace do DRF (reauditoria da etapa DL-011, ajuste 1). Só
    # espaço comum (str.strip() sem argumento); não é tratamento de
    # caractere invisível exótico.
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
