"""A suíte não pode depender de artefato NÃO VERSIONADO — BL-178 (achado B5 da
auditoria DL-019 rodada 2).

## O defeito, e por que ele é de classe

`config/settings.py` usa `whitenoise.storage.CompressedManifestStaticFilesStorage`,
que exige o `staticfiles.json` gerado por `collectstatic`. A integração
contínua roda `collectstatic` **depois** do `pytest`, de propósito (DE-012): se
rodasse antes, o manifesto existiria durante os testes e a CI passaria com um
`{% static %}` que falharia na máquina de quem desenvolve.

A defesa cobria **uma** direção. O que aconteceu foi a outra: a árvore de
trabalho tinha um `staticfiles/` de uma execução antiga — ignorado pelo Git,
logo invisível em `git status` —, e
`test_admin_recusa_vigencia_futura_no_inline_e_nao_grava` passava localmente
e falhava na CI com `ValueError: Missing staticfiles manifest entry for
'admin/css/base.css'`. **"1058 passed" foi declarado quatro vezes enquanto a
CI dizia `1 failed, 1055 passed, 2 skipped`.**

Duas consequências, medidas pelo auditor e piores que a falha em si:

1. `pytest_sessionfinish` sai cedo em sessão vermelha, então a conferência do
   elo de execução (BL-171) **nunca rodou na CI** — o mecanismo entregue na
   rodada anterior estava desligado lá.
2. O par de controle do admin escondia metade: o teste **negativo** espera 200
   e por isso **renderiza** o template → estourava; o **positivo** termina em
   302 e **não renderiza** → passava. Na CI, a metade que defende o RC-81 no
   admin nunca rodou, e o positivo ficava verde provando menos do que parece.

## A correção, e o que ela NÃO faz

O manifesto é artefato de **implantação**, não insumo de teste. A fixture
`estaticos_independentes_do_manifesto` (raiz, `conftest.py`) troca o backend de
estáticos da SESSÃO inteira pelo `StaticFilesStorage` simples e aponta
`STATIC_ROOT` para um diretório temporário vazio — de modo que o resultado seja
o mesmo em árvore limpa e em árvore com sobras.

Ela **não** inverte a ordem da CI, que continua rodando `collectstatic` depois
do `pytest`: trocar "local permissivo" por "CI permissiva" seria o mesmo
defeito com o sinal virado, e o workflow explica por escrito por que. O
pipeline de estáticos continua exercido pelo passo `collectstatic` da CI e pelo
`Dockerfile`; nada foi afrouxado ali, e o teste abaixo prende isso.

## Por que o controle positivo aponta `STATIC_ROOT` para um diretório vazio

Porque medir na árvore suja não mede nada. Com `STATIC_ROOT` vazio, este
arquivo reproduz a árvore limpa **de dentro** da árvore suja: remover a fixture
reprova a suíte aqui também, em qualquer máquina. Sem isso, a defesa dependeria
de alguém lembrar de clonar o repositório antes de declarar verde — que é
exatamente o que não aconteceu por quatro relatórios seguidos.
"""

import pytest
from django.test import override_settings

import conftest

# O backend declarado em `config/settings.py` para PRODUÇÃO. Fixado aqui para
# que ninguém "conserte" o B5 pelo lado errado — enfraquecendo a implantação
# em vez de tirar o manifesto do caminho dos testes.
BACKEND_DE_ESTATICOS_DE_PRODUCAO = "whitenoise.storage.CompressedManifestStaticFilesStorage"


@pytest.mark.django_db
def test_a_suite_renderiza_pagina_do_admin_sem_manifesto_de_estaticos(client, tmp_path):
    """O controle positivo da fixture, e a reprodução da árvore limpa.

    `tmp_path` é um diretório recém-criado e vazio: não há `staticfiles.json`
    nenhum ali. Sob o backend de produção, renderizar qualquer template do
    admin levanta `ValueError: Missing staticfiles manifest entry`. Se a
    fixture da sessão for removida, este teste falha — **inclusive numa árvore
    que tenha `staticfiles/` de sobra**, que era onde a medição era permissiva.
    """
    with override_settings(STATIC_ROOT=str(tmp_path)):
        resposta = client.get("/admin/login/")

    assert resposta.status_code == 200
    # O template do admin usa `{% static %}`: se a URL saiu, o storage
    # resolveu sem consultar manifesto nenhum.
    assert b"admin/css/base.css" in resposta.content


def test_a_suite_usa_o_storage_simples_e_a_producao_continua_com_o_manifesto():
    """A correção não pode ter sido feita afrouxando a implantação.

    `config.settings.STORAGES` é o dicionário do MÓDULO — `override_settings`
    patcheia o wrapper de configuração, não o módulo —, então ele continua
    mostrando o que a produção declara.
    """
    from django.conf import settings as settings_efetivas

    import config.settings as settings_de_producao

    assert (
        settings_de_producao.STORAGES["staticfiles"]["BACKEND"] == BACKEND_DE_ESTATICOS_DE_PRODUCAO
    )
    assert (
        settings_efetivas.STORAGES["staticfiles"]["BACKEND"]
        == conftest.BACKEND_DE_ESTATICOS_DA_SUITE
    )
    assert conftest.BACKEND_DE_ESTATICOS_DA_SUITE != BACKEND_DE_ESTATICOS_DE_PRODUCAO


def test_a_integracao_continua_continua_coletando_estaticos_depois_do_pytest():
    """A outra metade de "não afrouxar": a CI ainda exerce o pipeline de
    estáticos, e ainda o faz DEPOIS do pytest.

    Inverter essa ordem seria trocar "local permissivo" por "CI permissiva" —
    o mesmo defeito com o sinal virado. O workflow explica isso por escrito; se
    alguém mexer na ordem, este teste reprova antes de a CI voltar a mascarar.
    """
    from apps.core.tests.test_dl019_varredura_de_contratos import RAIZ

    workflow = (RAIZ / ".github" / "workflows" / "backend.yml").read_text(encoding="utf-8")
    posicao_do_pytest = workflow.index("run: pytest -rs")
    posicao_do_collectstatic = workflow.index("run: python manage.py collectstatic --noinput")

    assert posicao_do_pytest < posicao_do_collectstatic, (
        "O passo `collectstatic` voltou a rodar ANTES do `pytest`. Isso faria a "
        "CI passar com um `{% static %}` que falharia fora dela — CI mais "
        "permissiva que o ambiente local, que é a direção que a DE-012 recusou."
    )
