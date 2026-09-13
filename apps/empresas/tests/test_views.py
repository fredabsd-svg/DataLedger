"""Testes das views HTML de empresas (DL-009: estados de tela).

Cobre o que a etapa DL-009 mudou: mensagem de sucesso ao cadastrar, template
próprio de "sem permissão" em vez de texto cru, CNPJ mascarado na listagem e
a ocultação do link "Nova empresa" para quem não pode usá-lo. Isolamento e
regra de permissão em si já são cobertos por test_isolamento.py e
test_permissoes.py — este arquivo não repete aquilo, só o comportamento de
apresentação.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def test_criar_empresa_com_sucesso_exibe_mensagem_de_confirmacao(client, escritorio):
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {"razao_social": "Empresa Nova Ltda", "nome_fantasia": "", "cnpj": "11122233000183"},
        follow=True,
    )

    assert resposta.status_code == 200
    assert Empresa.objects.filter(cnpj="11122233000183").exists()
    conteudo = resposta.content.decode()
    assert "cadastrada com sucesso" in conteudo
    # A mensagem tem que ser anunciada, não só decorativa.
    assert 'role="status"' in conteudo


def test_criar_empresa_com_cnpj_mascarado_e_aceito_e_gravado_canonico(client, escritorio):
    # Achado 2 (auditoria da etapa DL-011, alta): CNPJ digitado com máscara —
    # o uso normal — era recusado pelo MaxLengthValidator do campo do model
    # (14) antes de normalizar_cnpj tirar a máscara (o form gerava um campo
    # automático com esse limite). EmpresaForm agora declara o campo cnpj
    # explicitamente e normaliza em clean_cnpj antes do full_clean() do
    # model. Este teste é de ponta a ponta (POST real na view), não só
    # unitário na função de validação isolada.
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Empresa Mascarada Ltda",
            "nome_fantasia": "",
            "cnpj": "11.122.233/0001-83",
        },
        follow=True,
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "cadastrada com sucesso" in conteudo
    # Gravado sem máscara: é o valor canônico que fica no banco.
    assert Empresa.objects.filter(cnpj="11122233000183").exists()


def test_criar_empresa_com_cnpj_alfanumerico_mascarado_e_minusculo_e_aceito(client, escritorio):
    # Mesmo achado 2, agora combinando os três problemas que a auditoria
    # reproduziu juntos: letras, máscara e minúsculas.
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Empresa Alfanumérica Ltda",
            "nome_fantasia": "",
            "cnpj": "ab.123.cde/0001-55",
        },
        follow=True,
    )

    assert resposta.status_code == 200
    assert "cadastrada com sucesso" in resposta.content.decode()
    assert Empresa.objects.filter(cnpj="AB123CDE000155").exists()


def test_criar_empresa_sem_permissao_usa_template_proprio_com_link_de_volta(client, escritorio):
    _usuario_com_papel(Papel.CLIENTE, escritorio, "cliente")
    client.login(username="cliente", password="senha-forte-123")

    resposta = client.get(reverse("empresas:criar"))

    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()
    # Nada de texto cru sem contexto: precisa de explicação e caminho de volta.
    assert "Sem permissão" in conteudo
    assert reverse("empresas:lista") in conteudo
    assert not Empresa.objects.exists()


def test_lista_empresas_exibe_cnpj_mascarado(client, escritorio):
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    conteudo = resposta.content.decode()
    assert "11.122.233/0001-83" in conteudo
    # CNPJ cru (14 dígitos seguidos) não deve aparecer mais na página.
    assert "11122233000183" not in conteudo


def test_lista_empresas_exibe_cnpj_alfanumerico_mascarado(client, escritorio):
    # CNPJ alfanumérico sintético (DL-011): base "AB123CDE0001" com DV "55"
    # calculado pelo algoritmo oficial da NT 2025.001 (ver
    # apps/empresas/tests/test_validators.py). O agrupamento com pontuação é
    # convenção de exibição nossa, não da NT (ver comentário em
    # apps/empresas/views.py::_mascara_cnpj), mas continua valendo para as 14
    # posições alfanuméricas ou numéricas.
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Alfanumérica Ltda", cnpj="AB123CDE000155"
    )
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    conteudo = resposta.content.decode()
    assert "AB.123.CDE/0001-55" in conteudo
    # CNPJ cru (14 caracteres seguidos) não deve aparecer mais na página.
    assert "AB123CDE000155" not in conteudo


def test_lista_empresas_vazia_mostra_mensagem_de_estado_vazio(client, escritorio):
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    assert "Nenhuma empresa cadastrada neste escritório." in resposta.content.decode()


def test_lista_empresas_sem_escritorio_ativo_explica_e_da_caminho_de_volta(client):
    get_user_model().objects.create_user(
        username="sem_vinculo", email="sem_vinculo@escritorio.com.br", password="senha-forte-123"
    )
    client.login(username="sem_vinculo", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Nenhum escritório ativo" in conteudo
    assert reverse("tenancy:painel") in conteudo


def test_link_nova_empresa_oculto_para_papel_sem_permissao_de_gerenciar(client, escritorio):
    _usuario_com_papel(Papel.CLIENTE, escritorio, "cliente")
    client.login(username="cliente", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    assert resposta.status_code == 200
    assert "Nova empresa" not in resposta.content.decode()


def test_link_nova_empresa_visivel_para_gestor(client, escritorio):
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    assert "Nova empresa" in resposta.content.decode()


def test_lista_empresas_exibe_data_em_pt_br(client, escritorio):
    """Critério 13, sem teste antes do achado A4: data teria que estar em
    pt-BR (dd/mm/aaaa), não em outro formato."""
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.get(reverse("empresas:lista"))

    conteudo = resposta.content.decode()
    # localtime() é obrigatório aqui, e não detalhe de estilo. USE_TZ=True
    # guarda `criado_em` em UTC, e TIME_ZONE="America/Sao_Paulo" faz o
    # template renderizar no fuso de Brasília. Comparar direto com o valor em
    # UTC fazia este teste falhar todo dia entre 00:00 e 03:00 UTC — das 21:00
    # à meia-noite em São Paulo —, porque nessa janela a data em UTC já virou
    # e a local ainda não. Descoberto em 2026-09-13, com o teste acusando
    # "13/09/2026" contra "12/09/2026" na tela; a tela estava certa.
    #
    # Falha que só aparece em três horas do dia parece intermitência e
    # costuma ser tratada como tal. Não era: era o teste comparando fusos
    # diferentes.
    data_esperada = timezone.localtime(empresa.criado_em).strftime("%d/%m/%Y")
    assert data_esperada in conteudo
    # Formato ISO (americano/técnico) não pode ser o que aparece na tela.
    assert timezone.localtime(empresa.criado_em).strftime("%Y-%m-%d") not in conteudo


def test_form_com_erro_todo_aria_describedby_aponta_para_id_existente(client, escritorio):
    """A1: o Django (desde a 5.0) anota o widget com
    aria-describedby="{auto_id}_error" quando o campo tem erro. Se a caixa
    de erro do template usar outro id, o atributo fica pendurado no vazio —
    pior que não ter o atributo, porque parece acessível e não é. Este
    teste é genérico (não é sobre o campo cnpj especificamente) para pegar
    qualquer campo futuro que caia no mesmo problema.
    """
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        # CNPJ com dígito verificador errado: gera erro só no campo cnpj.
        {"razao_social": "Empresa Invalida Ltda", "nome_fantasia": "", "cnpj": "11122233000199"},
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    referencias = re.findall(r'aria-describedby="([^"]*)"', conteudo)
    assert referencias, "esperava ao menos um campo com erro anotado por aria-describedby"
    for valor in referencias:
        for id_referenciado in valor.split():
            assert f'id="{id_referenciado}"' in conteudo, (
                f"aria-describedby aponta para '{id_referenciado}', que não existe na página"
            )


def test_criar_empresa_pela_tela_com_corrida_neutralizando_o_validate_unique_da_erro_de_campo(
    client, escritorio, monkeypatch
):
    # A3 (reauditoria da etapa DL-011, rodada 3), mutante N10: o try/except
    # em torno de empresa.save() em criar_empresa não tinha teste próprio —
    # o form.is_valid() já pega duplicidade comum via validate_unique() (um
    # SELECT), então só a CORRIDA (SELECT->INSERT concorrente) exercita o
    # try/except. Neutralizar validate_unique() força esse caminho sem
    # precisar de duas threads reais.
    from django.forms.models import BaseModelForm

    monkeypatch.setattr(BaseModelForm, "validate_unique", lambda self: None)

    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Original Ltda", cnpj="AB123CDE000155"
    )
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Empresa Concorrente Ltda",
            "nome_fantasia": "",
            "cnpj": "ab123cde000155",
        },
    )

    assert resposta.status_code == 200
    assert "já existe" in resposta.content.decode()
    assert Empresa.objects.filter(cnpj="AB123CDE000155").count() == 1


def test_criar_empresa_pela_tela_com_validationerror_de_dict_sem_cnpj_nao_e_engolida(
    client, escritorio, monkeypatch
):
    # B1 (auditoria da etapa DL-011, rodada 4): antes desta correção, o
    # except da tela era ValidationError genérico e lia
    # exc.message_dict.get("cnpj", []) — se a ValidationError vinda de
    # Empresa.save() tivesse dict, mas SEM a chave "cnpj" (ex.: uma regra
    # de negócio futura sobre razao_social), o loop não adicionava erro
    # nenhum: a view devolvia 200, sem nenhum erro no formulário, e nada
    # era gravado — falha virando sucesso aparente (AGENTS.md §8). Com o
    # tipo próprio (CNPJDuplicado), essa ValidationError não é capturada e
    # sobe intacta — nunca mais 200 silencioso.
    #
    # C6 (auditoria de fechamento, rodada 5): `pytest.raises(DjangoValidationError)`
    # é satisfeito por qualquer subclasse, inclusive `CNPJDuplicado` — uma
    # regressão que envelopasse a ValidationError genérica nesse tipo
    # passaria despercebida. `assert type(...) is DjangoValidationError`
    # discrimina o tipo exato. A asserção antiga
    # `not Empresa.objects.filter(...).exists()` foi removida por ser
    # vazia: com save() monkeypatchado para sempre levantar, nada seria
    # gravado de qualquer forma — não provava cobertura de persistência.
    def _save_com_validationerror_de_outro_campo(self, *args, **kwargs):
        raise DjangoValidationError({"razao_social": ["problema de regra de negócio"]})

    monkeypatch.setattr(Empresa, "save", _save_com_validationerror_de_outro_campo)
    _usuario_com_papel(Papel.GESTOR, escritorio, "gestor")
    client.login(username="gestor", password="senha-forte-123")

    with pytest.raises(DjangoValidationError) as excinfo:
        client.post(
            reverse("empresas:criar"),
            {
                "razao_social": "Empresa Nova Ltda",
                "nome_fantasia": "",
                "cnpj": "11122233000183",
            },
        )

    assert type(excinfo.value) is DjangoValidationError
