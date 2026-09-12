"""Testes de validar_cnpj/normalizar_cnpj (DL-011: CNPJ alfanumérico).

Fonte: NT 2025.001 (ENCAT) / IN RFB 2.229. Cobre os critérios de aceite 1-9
do plano docs/planos/DL-011-cnpj-alfanumerico.md (o critério 11, persistência
sem truncar, tem teste próprio abaixo que exige banco de dados) e os achados
1-7 da auditoria independente da etapa (docs/auditorias/, ver relatório da
etapa DL-011):

- Achado 1 (alta): canonização na gravação — testado em test_models.py e em
  test_empresa_persiste_cnpj_alfanumerico_sem_truncar abaixo (grava minúsculo,
  lê maiúsculo).
- Achado 2 (alta): máscara na fronteira do formulário/serializer — testado em
  test_views.py e test_api.py (ponta a ponta), não aqui.
- Achado 3 (média): .upper() não pode mudar o comprimento do texto.
- Achado 4 (média): fronteira resto % 11 < 2 (resto 0 e resto 1).
- Achado 5 (baixa): tipo inválido levanta ValidationError, não AttributeError.
- Achado 6 (baixa): máscara mal formada (separador fora de posição) é recusada.
- Achado 7 (baixa): teste que isola o mecanismo (regex de formato) da
  vacuidade anterior.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.empresas.models import Empresa
from apps.empresas.validators import _FORMATO_CNPJ, normalizar_cnpj, validar_cnpj
from apps.tenancy.models import Escritorio

# CNPJ alfanumérico de referência para os testes: base "AB123CDE0001" com
# DV "55" calculado pelo próprio algoritmo do Anexo I da NT 2025.001 (módulo
# 11, ASCII - 48). Não é um CNPJ real; é dado sintético só para teste.
CNPJ_ALFANUMERICO_VALIDO = "AB123CDE000155"

# Segundo CNPJ alfanumérico sintético, com base diferente do primeiro — usado
# onde é preciso um alfanumérico "qualquer outro" para não repetir sempre o
# mesmo fixture (ex.: no teste de minúsculas corrigido pelo achado 7).
CNPJ_ALFANUMERICO_VALIDO_2 = "XZ9K2M7F000275"


# Critério 1: os cinco CNPJs numéricos da NT 2025.001 (tabela de
# compatibilidade retroativa) continuam válidos pelo algoritmo novo.
@pytest.mark.parametrize(
    "cnpj",
    [
        "11222333000181",
        "11444777000161",
        "34028316000103",
        "00000000000191",
        "19131243000197",
    ],
)
def test_cnpj_numerico_conhecido_continua_valido(cnpj):
    validar_cnpj(cnpj)


def test_cnpj_valido_nao_levanta_erro():
    validar_cnpj("11122233000183")


def test_cnpj_valido_com_mascara_nao_levanta_erro():
    validar_cnpj("11.122.233/0001-83")


def test_cnpj_com_tamanho_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("123")


def test_cnpj_com_todos_digitos_iguais_e_invalido():
    # Não é uma regra explícita da NT; o DV calculado para "111...1" não
    # confere com os dígitos informados, então é recusado pelo próprio
    # cálculo do módulo 11 (sem exceção especial para dígitos repetidos).
    #
    # Verificação exaustiva (auditoria da etapa DL-011): das 36 sequências
    # possíveis de 14 caracteres iguais (dígitos 0-9 e letras A-Z), só
    # "00000000000000" tem o DV calculado coincidindo com os dois últimos
    # caracteres da própria sequência — por isso é a única que precisa de
    # rejeição explícita (ver test_cnpj_zerado_e_invalido); todas as demais,
    # incluindo repetições de letras, já falham naturalmente no cálculo do
    # módulo 11. Não reintroduzir uma exceção genérica para "dígitos
    # repetidos": ela seria redundante e menos fiel à norma.
    with pytest.raises(ValidationError):
        validar_cnpj("11111111111111")


def test_cnpj_com_digito_verificador_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("11122233000184")


# Critério 2: CNPJ alfanumérico com DV correto é aceito.
def test_cnpj_alfanumerico_valido_nao_levanta_erro():
    validar_cnpj(CNPJ_ALFANUMERICO_VALIDO)


# Critério 3: CNPJ alfanumérico com DV incorreto é recusado.
def test_cnpj_alfanumerico_com_digito_verificador_errado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("AB123CDE000156")


# Critério 4: letras nas posições 13-14 são recusadas (DV é sempre numérico).
def test_cnpj_com_letra_no_digito_verificador_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("AB123CDE00A1B5")


# Achado 7 (auditoria): o teste acima não isola o mecanismo — a string
# também tem DV numericamente errado, então uma mutação que trocasse
# `[A-Z0-9]{12}[0-9]{2}` por `[A-Z0-9]{14}` sobreviveria (o CNPJ seria
# recusado do mesmo jeito, mas pelo motivo errado). Este teste verifica a
# regex de formato diretamente, isolada do cálculo do DV.
def test_formato_cnpj_recusa_letra_nas_posicoes_de_digito_verificador():
    assert _FORMATO_CNPJ.fullmatch("AB123CDE0001A5") is None
    assert _FORMATO_CNPJ.fullmatch("AB123CDE00015A") is None


def test_formato_cnpj_aceita_apenas_numeros_nas_posicoes_de_digito_verificador():
    assert _FORMATO_CNPJ.fullmatch(CNPJ_ALFANUMERICO_VALIDO) is not None


# Critério 5: 13 ou 15 caracteres são recusados.
@pytest.mark.parametrize(
    "cnpj",
    [
        "AB123CDE00015",  # 13 caracteres
        "AB123CDE0001555",  # 15 caracteres
    ],
)
def test_cnpj_com_tamanho_diferente_de_14_e_invalido(cnpj):
    with pytest.raises(ValidationError):
        validar_cnpj(cnpj)


# Critério 6: CNPJ zerado é recusado (o cálculo do módulo 11 daria DV "00"
# por acidente, que coincidiria com os dígitos informados).
def test_cnpj_zerado_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("00000000000000")


# Critério 7: máscara aceita e removida, tanto em CNPJ numérico (já coberto
# acima) quanto em alfanumérico.
def test_cnpj_alfanumerico_com_mascara_nao_levanta_erro():
    validar_cnpj("AB.123.CDE/0001-55")


# Critério 8: entrada em minúsculas é normalizada e validada corretamente.
def test_cnpj_alfanumerico_em_minusculas_nao_levanta_erro():
    validar_cnpj(CNPJ_ALFANUMERICO_VALIDO.lower())


def test_segundo_cnpj_alfanumerico_em_minusculas_nao_levanta_erro():
    # Corrige achado 7 (auditoria): o teste anterior aqui usava
    # "11.122.233/0001-83".lower(), que não tem nenhuma letra — .lower() não
    # muda nada e o teste passava mesmo que a normalização de caixa
    # estivesse quebrada (vacuidade). Usa um segundo CNPJ alfanumérico, para
    # também não duplicar exatamente o mesmo valor do teste do critério 8.
    validar_cnpj(CNPJ_ALFANUMERICO_VALIDO_2.lower())


# Critério 9: caractere fora de [A-Z0-9./-] é recusado com mensagem útil.
def test_cnpj_com_caractere_invalido_e_invalido():
    with pytest.raises(ValidationError, match="alfanuméricos"):
        validar_cnpj("AB123CDE00#155")


# Achado 3 (auditoria, média): letras Unicode que mudam de comprimento ao
# converter para maiúsculas (ex.: "ß".upper() == "SS") não podem ser
# aceitas por sobrarem "14 caracteres" só depois do .upper(). O conjunto de
# caracteres válido é restrito a ASCII e checado ANTES da conversão de caixa.
def test_cnpj_com_caractere_unicode_que_expande_no_upper_e_invalido():
    with pytest.raises(ValidationError):
        validar_cnpj("ß123CDE000117")


# Achado 4 (auditoria, média): a fronteira `resto % 11 < 2` (rejeita resto 0
# e resto 1 com DV "0") não era exercida por nenhum caso dos 41 testes
# anteriores. Casos calculados pela auditoria da etapa DL-011.
@pytest.mark.parametrize(
    "cnpj",
    [
        "72981506162202",  # resto 1 no cálculo do DV1
        "11070434192580",  # resto 1 no cálculo do DV2
        "24365234257800",  # resto 0 nos dois
        "CR6G1EWE2BK600",  # alfanumérico, resto 1 nos dois
    ],
)
def test_cnpj_no_limite_do_resto_modulo_11_e_valido(cnpj):
    validar_cnpj(cnpj)


# Achado 5 (auditoria, baixa): tipo inválido deve levantar ValidationError,
# nunca AttributeError — quem chama validar_cnpj como validador de campo
# espera só ValidationError.
@pytest.mark.parametrize("valor", [None, 11222333000181])
def test_cnpj_com_tipo_invalido_levanta_validation_error(valor):
    with pytest.raises(ValidationError):
        validar_cnpj(valor)


# Achado 6 (auditoria, baixa): remover "." "/" "-" de qualquer posição
# aceitaria máscara mal formada, desde que o resultado tivesse 14
# caracteres por coincidência. A máscara só é reconhecida no formato exato
# XX.XXX.XXX/XXXX-XX; qualquer outra distribuição de separadores é recusada.
@pytest.mark.parametrize(
    "cnpj",
    [
        "../-11222333000181",
        ".1122.2330/00181-",
    ],
)
def test_cnpj_com_mascara_mal_formada_e_invalido(cnpj):
    with pytest.raises(ValidationError):
        validar_cnpj(cnpj)


# Ajuste 1 (reauditoria da etapa DL-011): espaço em branco na borda (comum
# em CNPJ colado de planilha) tem que ser aceito, tanto sem máscara quanto
# com máscara — a validação unitária isolada já cobre os dois casos; o
# caminho de ponta a ponta pela API está em test_api.py.
@pytest.mark.parametrize(
    "cnpj",
    [
        " 11222333000181",
        "11222333000181 ",
        " 11222333000181 ",
        " 11.222.333/0001-81 ",
    ],
)
def test_cnpj_com_espaco_na_borda_nao_levanta_erro(cnpj):
    validar_cnpj(cnpj)


# Ajuste 2 (reauditoria da etapa DL-011): letra na posição do dígito
# verificador tem que dar a mesma mensagem específica ("... seguidos de 2
# dígitos verificadores numéricos"), esteja o CNPJ mascarado ou não. Antes
# do ajuste, a versão mascarada caía no erro genérico de máscara mal
# formada, porque o último grupo de _REGEX_MASCARA exigia dígito e a letra
# fazia a própria máscara não casar — escondendo o motivo real da rejeição.
def test_cnpj_mascarado_com_letra_no_digito_verificador_da_mensagem_especifica():
    with pytest.raises(ValidationError, match="dígitos verificadores numéricos"):
        validar_cnpj("11.222.333/0001-8A")


# normalizar_cnpj é a função reutilizada por Empresa.save(),
# Estabelecimento.save(), EmpresaForm e EmpresaSerializer (achado 1 da
# auditoria): confirma o contrato de saída (sempre maiúsculo, sem máscara).
def test_normalizar_cnpj_remove_mascara_e_converte_maiusculas():
    assert normalizar_cnpj("ab.123.cde/0001-55") == CNPJ_ALFANUMERICO_VALIDO
    assert normalizar_cnpj(CNPJ_ALFANUMERICO_VALIDO.lower()) == CNPJ_ALFANUMERICO_VALIDO


# Critério 11: o campo do modelo persiste CNPJ alfanumérico sem truncar
# (max_length=14 já comporta letras; este teste evita regressão silenciosa
# se o campo for alterado no futuro). Também cobre o achado 1 (auditoria):
# o valor é gravado canonizado (maiúsculo) mesmo tendo sido passado em
# minúsculas — Empresa.save() canoniza antes de gravar.
@pytest.mark.django_db
def test_empresa_persiste_cnpj_alfanumerico_sem_truncar():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Alfanumérica Ltda",
        cnpj=CNPJ_ALFANUMERICO_VALIDO.lower(),
    )

    empresa.refresh_from_db()

    assert empresa.cnpj == CNPJ_ALFANUMERICO_VALIDO
    assert len(empresa.cnpj) == 14


@pytest.mark.django_db
def test_empresa_com_cnpj_em_caixas_diferentes_nao_duplica_registro():
    # Achado 1 (auditoria, alta): antes desta correção, "AB123CDE000155" e
    # "ab123cde000155" gravavam como dois registros distintos, porque
    # unique=True no Postgres é sensível a caixa e a validação normalizava
    # só para checar, descartando o resultado. Empresa.save() agora
    # canoniza antes de gravar, então o segundo INSERT com a mesma raiz em
    # caixa diferente deve colidir com a constraint de unicidade.
    from django.db import IntegrityError, transaction

    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Alfanumérica Ltda",
        cnpj=CNPJ_ALFANUMERICO_VALIDO,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Empresa.objects.create(
            escritorio=escritorio,
            razao_social="Empresa Alfanumérica Ltda (duplicada)",
            cnpj=CNPJ_ALFANUMERICO_VALIDO.lower(),
        )

    assert Empresa.objects.filter(cnpj=CNPJ_ALFANUMERICO_VALIDO).count() == 1
