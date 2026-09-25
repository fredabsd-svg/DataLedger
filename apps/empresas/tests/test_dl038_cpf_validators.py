"""Testes de `validar_cpf`/`normalizar_cpf` — DL-038 (R2).

Fonte do algoritmo: NÃO É publicação da própria Receita Federal (pesquisa
registrada em `apps/empresas/validators.py`, acima de `_PESOS_CPF_PRIMEIRO_
DIGITO`, conduzida pelo `auxiliar-pesquisa` em 2026-09-25) — é convenção
técnica de mercado (`validate-docbr`, Secretaria da Fazenda do Paraná,
macoratti.net), convergente e sem divergência entre as fontes consultadas,
citada como NÃO OFICIAL no próprio código-fonte, como a tarefa exigiu.

Cobre o critério de aceite 2 do plano (docs/planos/DL-038-cliente-pessoa-
fisica.md): CPF válido aceito; DV errado, sequência repetida, tamanho errado
e letras recusados com mensagem; zero à esquerda preservado.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.empresas.validators import normalizar_cpf, validar_cpf

# CPFs sintéticos válidos (calculados pelo próprio algoritmo, não são CPFs
# reais de ninguém) — usados amplamente na literatura técnica de exemplo
# ("11144477735" é o exemplo clássico usado por praticamente toda fonte
# consultada) e um segundo, independente, para não repetir sempre o mesmo.
CPF_VALIDO = "11144477735"
CPF_VALIDO_2 = "52998224725"

# CPFs sintéticos válidos que começam com dígito "0" — para o caso de "zero
# à esquerda preservado" (R2): calculados localmente pelo mesmo algoritmo,
# não são CPFs reais.
CPF_VALIDO_COM_ZERO_A_ESQUERDA = "01803406380"


def test_cpf_valido_nao_levanta_erro():
    validar_cpf(CPF_VALIDO)


def test_segundo_cpf_valido_nao_levanta_erro():
    validar_cpf(CPF_VALIDO_2)


def test_cpf_valido_com_mascara_nao_levanta_erro():
    validar_cpf("111.444.777-35")


def test_cpf_com_digito_verificador_errado_e_invalido():
    with pytest.raises(ValidationError, match="dígitos verificadores"):
        validar_cpf("11144477736")


@pytest.mark.parametrize(
    "cpf",
    [
        "00000000000",
        "11111111111",
        "22222222222",
        "33333333333",
        "44444444444",
        "55555555555",
        "66666666666",
        "77777777777",
        "88888888888",
        "99999999999",
    ],
)
def test_cpf_com_sequencia_repetida_e_invalido(cpf):
    # As dez sequências "passam" no cálculo do módulo 11 por coincidência
    # estrutural do algoritmo (ver o comentário em validators.py) — por isso
    # a checagem é SEPARADA do cálculo do DV, e cobre as dez, não só "111...".
    with pytest.raises(ValidationError, match="sequência de dígito repetido"):
        validar_cpf(cpf)


@pytest.mark.parametrize(
    "cpf",
    [
        "123",  # curto demais
        "1234567890",  # 10 dígitos
        "123456789012",  # 12 dígitos
    ],
)
def test_cpf_com_tamanho_errado_e_invalido(cpf):
    with pytest.raises(ValidationError):
        validar_cpf(cpf)


def test_cpf_com_letras_e_invalido():
    with pytest.raises(ValidationError, match="11 dígitos numéricos"):
        validar_cpf("1114447773A")


def test_cpf_com_mascara_mal_formada_e_invalido():
    # Mesma política de rigor da máscara do CNPJ: só o formato EXATO
    # XXX.XXX.XXX-XX é reconhecido; qualquer outra distribuição de
    # separador é caractere inválido, não máscara "quase certa".
    with pytest.raises(ValidationError):
        validar_cpf("111.444.777/35")


def test_cpf_com_tipo_invalido_levanta_validation_error():
    # Mesmo achado 5 da auditoria DL-011, agora para CPF: tipo errado tem
    # que virar ValidationError, nunca AttributeError.
    with pytest.raises(ValidationError):
        validar_cpf(None)
    with pytest.raises(ValidationError):
        validar_cpf(11144477735)


# --- Zero à esquerda (R2) ---------------------------------------------


def test_cpf_com_zero_a_esquerda_nao_levanta_erro():
    validar_cpf(CPF_VALIDO_COM_ZERO_A_ESQUERDA)


def test_normalizar_cpf_preserva_zero_a_esquerda():
    # O ponto que mais importa do R2: normalizar_cpf devolve TEXTO, não
    # int — um int descartaria o zero à esquerda silenciosamente (o mesmo
    # risco que levou o CNPJ a ser sempre texto). Confirma aqui, direto.
    resultado = normalizar_cpf(CPF_VALIDO_COM_ZERO_A_ESQUERDA)
    assert resultado == CPF_VALIDO_COM_ZERO_A_ESQUERDA
    assert isinstance(resultado, str)
    assert len(resultado) == 11
    assert resultado.startswith("0")


def test_normalizar_cpf_remove_mascara():
    assert normalizar_cpf("111.444.777-35") == CPF_VALIDO


# Mesmo tratamento de espaço na borda do normalizar_cnpj — ver o comentário
# em validators.py e em test_validators.py.
@pytest.mark.parametrize(
    "cpf",
    [
        " 11144477735",
        "11144477735 ",
        " 11144477735 ",
        " 111.444.777-35 ",
    ],
)
def test_cpf_com_espaco_na_borda_nao_levanta_erro(cpf):
    validar_cpf(cpf)
