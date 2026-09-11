from django.core.exceptions import ValidationError

# Pesos do algoritmo público de dígitos verificadores de CNPJ (Receita
# Federal). Não inventado: é o mesmo algoritmo usado por qualquer validador
# de CNPJ. Não confirma que o CNPJ existe de fato ou está ativo — isso
# exigiria consulta externa, fora do escopo desta etapa.
_PESOS_PRIMEIRO_DIGITO = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_SEGUNDO_DIGITO = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]


def _calcular_digito_verificador(numeros, pesos):
    soma = sum(int(numero) * peso for numero, peso in zip(numeros, pesos, strict=True))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def validar_cnpj(valor):
    """Valida um CNPJ pelos dígitos verificadores oficiais.

    Aceita o valor com ou sem máscara; levanta ValidationError para
    tamanho, formato ou dígitos verificadores inválidos.
    """
    digitos = "".join(filter(str.isdigit, valor))

    if len(digitos) != 14:
        raise ValidationError("CNPJ deve ter 14 dígitos.")

    if digitos == digitos[0] * 14:
        raise ValidationError("CNPJ inválido.")

    primeiro_digito = _calcular_digito_verificador(digitos[:12], _PESOS_PRIMEIRO_DIGITO)
    segundo_digito = _calcular_digito_verificador(
        digitos[:12] + primeiro_digito, _PESOS_SEGUNDO_DIGITO
    )

    if digitos[12:] != primeiro_digito + segundo_digito:
        raise ValidationError("CNPJ inválido: dígitos verificadores não conferem.")
