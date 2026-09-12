"""Testes de ponta a ponta da API de empresas/estabelecimentos para CNPJ.

Cobre o achado 2 (alta) da auditoria da etapa DL-011: o CharField gerado
automaticamente pelo ModelSerializer herda max_length=14 do model (o CNPJ já
canonizado), então um CNPJ mascarado — até 18 caracteres — era recusado pelo
MaxLengthValidator antes de normalizar_cnpj tirar a máscara. EmpresaSerializer
e EstabelecimentoSerializer agora normalizam em to_internal_value, antes da
validação de campo do DRF. Testado aqui via requisição HTTP real (não só
chamando a função de validação isolada), porque foi assim que a auditoria
reproduziu o defeito.
"""

import json
import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.urls import reverse
from rest_framework.validators import UniqueValidator

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor", email="gestor@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


def test_criar_empresa_via_api_com_cnpj_mascarado_e_aceito_e_gravado_canonico(client, gestor):
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Mascarada Ltda", "cnpj": "11.122.233/0001-83"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.filter(cnpj="11122233000183").exists()
    # A resposta também deve devolver o valor canônico, não o que foi
    # enviado, para o cliente da API não ficar com uma ideia errada do que
    # foi persistido.
    assert resposta.json()["cnpj"] == "11122233000183"


def test_criar_empresa_via_api_com_cnpj_alfanumerico_mascarado_e_minusculo_e_aceito(client, gestor):
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Alfanumérica Ltda", "cnpj": "ab.123.cde/0001-55"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.filter(cnpj="AB123CDE000155").exists()
    assert resposta.json()["cnpj"] == "AB123CDE000155"


def test_criar_empresa_via_api_com_cnpj_com_dv_invalido_e_recusado(client, gestor):
    # A normalização não pode enfraquecer a validação: continua recusando
    # DV incorreto, agora sobre o valor já canonizado.
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Invalida Ltda", "cnpj": "11.122.233/0001-84"},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not Empresa.objects.filter(razao_social="Empresa Invalida Ltda").exists()


def test_criar_empresa_via_api_com_cnpj_mascarado_e_espacos_na_borda_e_aceito(client, gestor):
    # Ajuste 1 (reauditoria da etapa DL-011): CNPJ colado de planilha vem
    # com espaço, com frequência. O caminho da tela já aceitava (CharField
    # de formulário tem strip=True por padrão); o caminho da API recusava,
    # porque _normalizar_cnpj_do_payload rodava antes do trim_whitespace do
    # DRF. Este teste é de ponta a ponta (POST real), não só unitário.
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Com Espaco Ltda", "cnpj": " 11.222.333/0001-81 "},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.filter(cnpj="11222333000181").exists()
    assert resposta.json()["cnpj"] == "11222333000181"


def test_criar_estabelecimento_via_api_com_cnpj_mascarado_e_aceito(client, gestor, escritorio):
    # R3.3 (reauditoria, rodada 2): trocado de CNPJ puramente numérico para
    # alfanumérico minúsculo e mascarado, para o teste de ponta a ponta
    # exercitar caixa (que é canonizada em Estabelecimento.save()) além de
    # máscara (que é canonizada no serializer) — o teste anterior só
    # exercitava a máscara.
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa.pk}),
        data={"tipo": "matriz", "nome": "Matriz", "cnpj": "ab.123.cde/0001-55"},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert empresa.estabelecimentos.filter(cnpj="AB123CDE000155").exists()


# --- R9/M18: contrato fixado por teste — CNPJ numérico como número JSON ---


def test_criar_empresa_via_api_com_cnpj_numerico_enviado_como_numero_json(client, gestor):
    # Decisão do arquiteto-senior na reauditoria (R9, mutante M18): CNPJ
    # numérico enviado sem aspas no JSON (ex.: {"cnpj": 11222333000181}) é
    # ACEITO. Cliente de API em linguagem sem tipagem forte (JS solto,
    # planilha exportando JSON, etc.) manda número sem perceber, e recusar
    # isso é atrito sem ganho. CharField.to_internal_value do DRF já
    # converte int/float para string antes de CNPJSerializerField normalizar.
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Numero Ltda", "cnpj": 11222333000181},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.filter(cnpj="11222333000181").exists()


# --- R10: mensagens de erro na API -----------------------------------------


def test_criar_empresa_via_api_com_cnpj_vazio_da_mensagem_de_obrigatorio(client, gestor):
    # Antes (R10, reauditoria rodada 2): "" pela API caía na mensagem de
    # formato do CNPJ, porque o normalizar_cnpj de _normalizar_cnpj_do_payload
    # (mecanismo antigo) rodava antes do allow_blank/required do DRF. Com
    # CNPJSerializerField (um CharField comum na parte de blank/required),
    # o CharField.run_validation do DRF intercepta "" ANTES de chegar em
    # to_internal_value, e dá a mensagem de campo obrigatório — igual à tela.
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Vazia Ltda", "cnpj": ""},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    (mensagem,) = resposta.json()["cnpj"]
    assert "branco" in mensagem or "obrigat" in mensagem.lower()
    assert not Empresa.objects.filter(razao_social="Empresa Vazia Ltda").exists()


def test_criar_empresa_via_api_com_cnpj_so_espaco_da_mensagem_de_obrigatorio(client, gestor):
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Espaco Ltda", "cnpj": "   "},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    (mensagem,) = resposta.json()["cnpj"]
    assert "branco" in mensagem or "obrigat" in mensagem.lower()


def test_criar_empresa_via_api_com_cnpj_invalido_e_sem_razao_social_agrega_os_dois_erros(
    client, gestor
):
    # R7 (reauditoria, rodada 2): antes, o raise de
    # _normalizar_cnpj_do_payload acontecia ANTES de super().to_internal_value(),
    # fora do laço por-campo do DRF que agrega erros — um payload com dois
    # defeitos devolvia só o erro do cnpj. CNPJSerializerField.to_internal_value
    # roda DENTRO desse laço, então os dois erros voltam juntos.
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"cnpj": "xx"},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    corpo = resposta.json()
    assert "cnpj" in corpo
    assert "razao_social" in corpo


# --- R4: corrida na unicidade do CNPJ não pode devolver 500 ---------------


def test_criar_empresa_via_api_com_corrida_neutralizando_o_unique_validator_da_400(
    client, gestor, monkeypatch
):
    # R4 (reauditoria, rodada 2), reprodução determinística: o
    # UniqueValidator normalmente pega duplicidade ANTES do INSERT, com um
    # SELECT. A corrida real (duas requisições comitando entre esse SELECT
    # e o INSERT) é rara de reproduzir de forma confiável; neutralizar o
    # UniqueValidator força exatamente o caminho que só aconteceria sob
    # corrida — o INSERT tenta ir para a frente e é o IntegrityError da
    # constraint do banco quem pega a duplicidade. Sem o try/except em
    # EmpresaListCreateView.perform_create, isso devolveria 500.
    monkeypatch.setattr(UniqueValidator, "__call__", lambda self, value, serializer_field: None)

    Empresa.objects.create(
        escritorio=Escritorio.objects.get(cnpj="11111111000111"),
        razao_social="Empresa Original Ltda",
        cnpj="AB123CDE000155",
    )
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Concorrente Ltda", "cnpj": "ab123cde000155"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cnpj"]
    assert "já existe" in mensagem
    assert Empresa.objects.filter(cnpj="AB123CDE000155").count() == 1


@pytest.mark.django_db(transaction=True)
def test_criar_empresa_via_api_corrida_real_com_duas_threads_nunca_devolve_500():
    # R4 (reauditoria, rodada 2), reprodução com concorrência real (o
    # método do auditor): duas threads batem no mesmo endpoint com o mesmo
    # CNPJ (em caixas diferentes, para também exercitar a canonização),
    # sincronizadas por uma barreira para maximizar a chance de as duas
    # caírem na janela entre o SELECT do UniqueValidator e o INSERT.
    # `django_db(transaction=True)` é necessário: sem ele, o teste roda
    # dentro de uma transação que nunca comita de fato, e as duas threads
    # não veem a gravação uma da outra. Resultado admissível: {201, 400} —
    # nunca 500 — e exatamente um registro no banco ao final.
    escritorio = Escritorio.objects.create(nome="Escritório Corrida", cnpj="11111111000111")
    usuario = get_user_model().objects.create_user(
        username="gestor-corrida",
        email="gestor-corrida@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )

    barreira = threading.Barrier(2)
    resultados = {}

    def _postar(chave, cnpj):
        try:
            cliente = Client(raise_request_exception=False)
            cliente.login(username="gestor-corrida", password="senha-forte-123")
            barreira.wait()
            resposta = cliente.post(
                reverse("empresas:api-lista"),
                data=json.dumps({"razao_social": f"Empresa Corrida {chave} Ltda", "cnpj": cnpj}),
                content_type="application/json",
            )
            resultados[chave] = resposta.status_code
        finally:
            # Cada thread abre sua própria conexão de banco (Django usa
            # conexão thread-local). Sem fechar explicitamente, a conexão
            # fica pendente depois que a thread termina e o pytest-django
            # não consegue DROP DATABASE do banco de teste ao final da
            # suíte ("is being accessed by other users").
            connection.close()

    thread_a = threading.Thread(target=_postar, args=("A", "AB123CDE000155"))
    thread_b = threading.Thread(target=_postar, args=("B", "ab123cde000155"))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert set(resultados.values()) <= {201, 400}, resultados
    assert Empresa.objects.filter(cnpj="AB123CDE000155").count() == 1


# --- A1: a mesma corrida do R4, reaberta em PUT/PATCH ----------------------


def test_atualizar_empresa_via_api_com_corrida_neutralizando_o_unique_validator_da_400(
    client, gestor, monkeypatch
):
    # A1 (reauditoria da etapa DL-011, rodada 3): o R4 tinha sido corrigido
    # só na criação. Alterar o CNPJ de uma empresa para o valor já usado
    # por outra tem a mesma corrida (SELECT do UniqueValidator, depois
    # UPDATE) — reproduzida pelo auditor em 6 de 6 execuções reais.
    # Reprodução determinística: neutraliza o UniqueValidator para forçar
    # o caminho que só ocorreria sob corrida.
    escritorio = Escritorio.objects.get(cnpj="11111111000111")
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Alvo Ltda", cnpj="AB123CDE000155"
    )
    empresa_para_alterar = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa a Alterar Ltda", cnpj="11122233000183"
    )
    monkeypatch.setattr(UniqueValidator, "__call__", lambda self, value, serializer_field: None)
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa_para_alterar.pk}),
        data=json.dumps({"cnpj": "ab123cde000155"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cnpj"]
    assert "já existe" in mensagem
    empresa_para_alterar.refresh_from_db()
    assert empresa_para_alterar.cnpj == "11122233000183"


@pytest.mark.django_db(transaction=True)
def test_atualizar_empresa_via_api_corrida_real_com_duas_threads_nunca_devolve_500():
    # Mesma reprodução com concorrência real de
    # test_criar_empresa_via_api_corrida_real_com_duas_threads_nunca_devolve_500,
    # agora em PATCH: duas empresas já existentes, cada thread tenta
    # colocar o mesmo CNPJ (em caixas diferentes) na outra.
    escritorio = Escritorio.objects.create(nome="Escritório Corrida Patch", cnpj="22222222000122")
    usuario = get_user_model().objects.create_user(
        username="gestor-corrida-patch",
        email="gestor-corrida-patch@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa_a = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Corrida Patch A Ltda", cnpj="11122233000183"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Corrida Patch B Ltda", cnpj="11444777000161"
    )

    barreira = threading.Barrier(2)
    resultados = {}

    def _patch(chave, pk, cnpj):
        try:
            cliente = Client(raise_request_exception=False)
            cliente.login(username="gestor-corrida-patch", password="senha-forte-123")
            barreira.wait()
            resposta = cliente.patch(
                reverse("empresas:api-detalhe", kwargs={"pk": pk}),
                data=json.dumps({"cnpj": cnpj}),
                content_type="application/json",
            )
            resultados[chave] = resposta.status_code
        finally:
            connection.close()

    thread_a = threading.Thread(target=_patch, args=("A", empresa_a.pk, "AB123CDE000155"))
    thread_b = threading.Thread(target=_patch, args=("B", empresa_b.pk, "ab123cde000155"))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert set(resultados.values()) <= {200, 400}, resultados
    assert Empresa.objects.filter(cnpj="AB123CDE000155").count() == 1


# --- A3/N11: a mesma corrida do R4, sem teste no POST de Estabelecimento --


def test_criar_estabelecimento_via_api_com_corrida_neutralizando_o_unique_validator_da_400(
    client, gestor, escritorio, monkeypatch
):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz",
        cnpj="AB123CDE000155",
    )
    monkeypatch.setattr(UniqueValidator, "__call__", lambda self, value, serializer_field: None)
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa.pk}),
        data={"tipo": "filial", "nome": "Filial Concorrente", "cnpj": "ab123cde000155"},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cnpj"]
    assert "já existe" in mensagem
    assert Estabelecimento.objects.filter(cnpj="AB123CDE000155").count() == 1
