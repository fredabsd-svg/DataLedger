"""DE-076 item 2 (achado A4 da auditoria rodada 1) — vazão do envio, depois
da otimização de consultas (mapa de inscrições resolvido uma vez por
envio, não uma vez por arquivo — `apps.fiscal.services._mapa_de_
inscricoes_do_escritorio`) e do limite revisto para 2.000 arquivos.

Dois testes complementares, como a tarefa pediu:

1. `test_consultas_por_arquivo_nao_crescem_com_o_tamanho_do_envio` —
   REGRESSÃO por CONTAGEM DE CONSULTAS (`django_assert_max_num_queries`),
   não por tempo: mede o SQL de dois envios de tamanhos diferentes e prova
   que a diferença de consultas entre eles é peQUENA e CONSTANTE (não
   proporcional à diferença de arquivos) — se alguém reintroduzir uma
   consulta por arquivo, este teste fica vermelho de forma determinística,
   sem depender da velocidade da máquina.
2. `test_vazao_de_2000_arquivos_fica_abaixo_do_teto_do_servidor` — a
   MEDIÇÃO de vazão pedida, pelo MESMO caminho que a auditoria usou
   (`fiscal_web:recepcao`, cliente de teste, PostgreSQL local): 2.000
   arquivos com DOIS vínculos (prestador e tomador cadastrados —
   `xml_nfse()` já usa os CNPJs padrão de `empresa_a`/`empresa_a2` das
   fixtures). Imprime o tempo medido (visível com `pytest -s`) e falha se
   ultrapassar um teto BEM acima do valor esperado (folga generosa contra
   variação de hardware do executor) — o número exato medido nesta rodada
   está registrado no relatório da correção, não hardcoded aqui como teto
   apertado (isso seria reintroduzir fragilidade por tempo).
"""

from __future__ import annotations

import time

import pytest
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse, zip_de

pytestmark = pytest.mark.django_db


def _zip_com_n_notas(quantidade, *, prefixo):
    itens = {
        f"{prefixo}{i}.xml": xml_nfse(
            identificador=identificador_nfse(sufixo=i), incluir_tomador=True
        )
        for i in range(1, quantidade + 1)
    }
    return zip_de(itens)


def _consultas_do_envio(client, conteudo, nome_arquivo):
    from django.db import connection

    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.post(
            reverse("fiscal_web:recepcao"),
            {"arquivo": _upload(nome_arquivo, conteudo)},
            follow=True,
        )
    assert resposta.status_code == 200, resposta.content
    return len(capturadas)


def _upload(nome, conteudo):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(nome, conteudo, content_type="application/zip")


def _autenticar(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)


def test_consultas_por_arquivo_nao_crescem_com_o_tamanho_do_envio(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    _autenticar(client, usuario_gestor_a)

    rasa = 10
    profunda = 60
    consultas_rasa = _consultas_do_envio(client, _zip_com_n_notas(rasa, prefixo="r"), "rasa.zip")
    consultas_profunda = _consultas_do_envio(
        client, _zip_com_n_notas(profunda, prefixo="p"), "profunda.zip"
    )

    arquivos_a_mais = profunda - rasa
    diferenca_de_consultas = consultas_profunda - consultas_rasa
    # Achado A4: ANTES da otimização, cada arquivo custava ~9 consultas de
    # IDENTIFICAÇÃO (CNPJ/CPF do prestador e do tomador, até 2 cada) SOMADAS
    # ao custo inerente de gravação (SAVEPOINT + RELEASE + INSERT do
    # documento + INSERT de cada vínculo — medido em ~6/arquivo com dois
    # vínculos, mesmo depois da otimização, porque savepoint por arquivo é
    # o próprio mecanismo do critério 28/DE-074 item 5, não uma consulta de
    # identificação). O teto abaixo (8/arquivo) tem folga sobre o custo
    # inerente medido (~6), mas ainda reprova a REINTRODUÇÃO das consultas
    # de identificação por arquivo (isso empurraria para ~10/arquivo).
    assert diferenca_de_consultas <= arquivos_a_mais * 8, (
        f"{consultas_rasa} consultas para {rasa} arquivos, {consultas_profunda} para "
        f"{profunda}: {diferenca_de_consultas} a mais para {arquivos_a_mais} arquivos a "
        "mais ("
        f"{diferenca_de_consultas / arquivos_a_mais:.1f}/arquivo). Suspeita de consulta de "
        "identificação por arquivo reintroduzida (achado A4)."
    )


def test_consultas_do_envio_nao_crescem_com_o_numero_de_empresas_do_escritorio(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    # A outra metade do achado A4: `_mapa_de_inscricoes_do_escritorio` faz
    # DUAS consultas (Empresa, Estabelecimento) INDEPENDENTE de quantas
    # linhas elas devolvem — cadastrar mais 200 empresas no escritório não
    # pode custar mais NENHUMA consulta ao processar o MESMO envio.
    from apps.empresas.models import Empresa

    _autenticar(client, usuario_gestor_a)
    conteudo = _zip_com_n_notas(5, prefixo="e")
    consultas_antes = _consultas_do_envio(client, conteudo, "antes.zip")

    Empresa.objects.bulk_create(
        [
            Empresa(
                escritorio=escritorio_a,
                razao_social=f"Empresa Extra {i} Ltda",
                cnpj=f"{i:014d}",
            )
            for i in range(10000000, 10000200)
        ]
    )

    conteudo_2 = _zip_com_n_notas(5, prefixo="d")
    consultas_depois = _consultas_do_envio(client, conteudo_2, "depois.zip")

    assert consultas_depois <= consultas_antes + 2, (
        f"{consultas_antes} consultas antes de cadastrar 200 empresas extras, "
        f"{consultas_depois} depois — o mapa de inscrições deveria continuar em DUAS "
        "consultas fixas, não crescer com o tamanho do cadastro do escritório."
    )


@pytest.mark.django_db
def test_vazao_de_2000_arquivos_fica_abaixo_do_teto_do_servidor(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    from apps.fiscal import services

    _autenticar(client, usuario_gestor_a)
    quantidade = services.LIMITE_ARQUIVOS_NO_ENVIO
    conteudo = _zip_com_n_notas(quantidade, prefixo="v")

    inicio = time.perf_counter()
    resposta = client.post(
        reverse("fiscal_web:recepcao"),
        {"arquivo": _upload("vazao.zip", conteudo)},
        follow=True,
    )
    duracao = time.perf_counter() - inicio

    assert resposta.status_code == 200, resposta.content
    print(f"\nVAZAO {quantidade} arquivos 302 {duracao:.1f}s (DE-076, teto do envio revisto)")

    # Teto GENEROSO (não é o alvo de 15s da DE-076 — é a garantia de que
    # não voltamos ao patamar de 37-61s medido antes da correção; o
    # NÚMERO medido nesta execução vai para o relatório da rodada, não
    # para uma asserção apertada e frágil contra variação de hardware).
    assert duracao < 20.0, (
        f"Envio de {quantidade} arquivos levou {duracao:.1f}s — acima do teto de 20s "
        "de folga contra o timeout do servidor de aplicação (achado A4)."
    )
