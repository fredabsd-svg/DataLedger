"""DL-038, etapa 2 — as TELAS de cadastro de empresa: formulário (tipo de
inscrição, modo de escrituração) e lista.

Cobre:

- Critério 1/2 do plano, lado da TELA: escolher CNPJ ou CPF e o número
  correspondente; escolher modo de escrituração; sem campo de pessoa
  jurídica oferecido para CPF (R7 — não há o que esconder, o formulário
  nunca ofereceu NIRE/estabelecimento).
- HI-23: nova empresa CPF sem escolha explícita de modo de escrituração
  grava livro-caixa; CNPJ sem escolha explícita continua contabilidade
  (compatibilidade com o comportamento anterior a esta etapa); escolha
  explícita do contador sempre vence a sugestão.
- Erros do servidor (CPF inválido, CPF duplicado, exclusividade cnpj/cpf)
  aparecem no formulário, preservando o que foi digitado, nunca 500 —
  inclusive o bug corrigido nesta etapa: `criar_empresa` só lia a chave
  "cnpj" de `CNPJDuplicado.message_dict`, e um CPF duplicado era engolido
  em silêncio (200, sem erro, nada gravado).
- Lista de empresas: rótulo/inscrição corretos por tipo (a view já
  calculava isso — DL-038 etapa 1 — este arquivo prova que a TELA usa) e o
  modo de escrituração aparece; empresa em livro-caixa não oferece os
  links da contabilidade (R5 — a recusa de verdade é do servidor; aqui só
  se confere que a lista não convida para um link que seria recusado).

Dados 100% sintéticos.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.forms import EmpresaForm
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL-038 Telas", cnpj="11111111000111")


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _gestor_logado(client, escritorio, username="gestor"):
    _usuario_com_papel(Papel.GESTOR, escritorio, username)
    client.login(username=username, password="senha-forte-123")


# ---------------------------------------------------------------------------
# Formulário: as duas opções sempre visíveis, sem campo de PJ para CPF (R7)
# ---------------------------------------------------------------------------


def test_form_de_empresa_nova_mostra_as_duas_opcoes_de_tipo_e_de_modo(client, escritorio):
    _gestor_logado(client, escritorio)

    conteudo = client.get(reverse("empresas:criar")).content.decode()

    # As DUAS opções de cada grupo aparecem sempre — nenhuma escondida por
    # JavaScript (direcao-de-arte.md §4.6).
    assert 'value="CNPJ"' in conteudo
    assert 'value="CPF"' in conteudo
    assert 'value="contabilidade"' in conteudo
    assert 'value="livro_caixa"' in conteudo
    # Os dois campos de número aparecem os dois (obrigatoriedade é
    # CRUZADA, decidida no servidor — nunca um escondido por script).
    assert 'name="cnpj"' in conteudo
    assert 'name="cpf"' in conteudo


def test_form_de_empresa_nao_oferece_nire_nem_estabelecimento(client, escritorio):
    # R7: nenhum campo de pessoa JURÍDICA é oferecido — nem para CNPJ, nem
    # para CPF. Não é uma restrição condicional: o formulário nunca teve
    # esses campos.
    _gestor_logado(client, escritorio)

    conteudo = client.get(reverse("empresas:criar")).content.decode()

    assert 'name="nire"' not in conteudo
    assert "estabelecimento" not in conteudo.lower()


def test_form_de_empresa_tem_fieldset_com_legenda_para_cada_grupo_de_radio(client, escritorio):
    # Acessibilidade: cada grupo de radio button é um <fieldset> com
    # <legend> — marcação nativa de "isto é um grupo com um nome", mais
    # forte para leitor de tela do que um <label> solto apontando para um
    # único radio.
    _gestor_logado(client, escritorio)

    conteudo = client.get(reverse("empresas:criar")).content.decode()

    assert conteudo.count("<fieldset") == 2
    assert conteudo.count("<legend>") == 2


def test_form_de_empresa_nova_nao_vem_com_nenhum_radio_pre_marcado(client, escritorio):
    # Achado de verificação visual (Playwright, nesta etapa): a primeira
    # versão deste formulário vinha com "CNPJ" e "Contabilidade" JÁ
    # marcados na tela em branco — não por `initial`/`required` explícito,
    # mas porque `BaseModelForm.__init__` sempre semeia `self.initial` a
    # partir do valor DEFAULT do campo do MODELO (`Empresa()` em branco já
    # tem `tipo_inscricao="CNPJ"`/`modo_escrituracao="contabilidade"`). Um
    # radio pré-marcado é ENVIADO pelo navegador mesmo sem o contador
    # tocar nele — a sugestão de HI-23 (livro-caixa para CPF) nunca seria
    # acionada de verdade, porque `modo_escrituracao` nunca chegaria
    # "ausente" a `clean()`. `EmpresaForm.__init__` zera `self.initial`
    # das duas chaves para isto nunca voltar a acontecer — este teste
    # confere o HTML servido, não só o comportamento de `clean()` (que já
    # está coberto acima, mas não pegaria esta classe de regressão).
    _gestor_logado(client, escritorio)

    conteudo = client.get(reverse("empresas:criar")).content.decode()

    assert "checked" not in conteudo


# ---------------------------------------------------------------------------
# HI-23 — sugestão de modo de escrituração sem JavaScript
# ---------------------------------------------------------------------------


def test_empresa_cnpj_sem_escolher_modo_grava_contabilidade(client, escritorio):
    # Compatibilidade: nenhum cadastro de CNPJ existente passa a exigir um
    # clique a mais só porque "modo de escrituração" passou a existir.
    _gestor_logado(client, escritorio)

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Empresa CNPJ Sem Escolha Ltda",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CNPJ,
            "cnpj": "11122233000183",
            "cpf": "",
        },
        follow=True,
    )

    assert resposta.status_code == 200
    empresa = Empresa.objects.get(cnpj="11122233000183")
    assert empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE


def test_empresa_cpf_sem_escolher_modo_grava_livro_caixa(client, escritorio):
    # HI-23: a sugestão de verdade, sem nenhum campo pré-marcado no HTML —
    # a AUSÊNCIA de escolha é o que aciona o padrão, no servidor.
    _gestor_logado(client, escritorio)

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano de Tal",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CPF,
            "cnpj": "",
            "cpf": "11144477735",
        },
        follow=True,
    )

    assert resposta.status_code == 200
    empresa = Empresa.objects.get(cpf="11144477735")
    assert empresa.modo_escrituracao == ModoEscrituracao.LIVRO_CAIXA


def test_empresa_cpf_escolhendo_contabilidade_explicitamente_e_respeitado(client, escritorio):
    # "O usuário pode trocar" — a escolha explícita sempre vence a
    # sugestão.
    _gestor_logado(client, escritorio)

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano Com Contabilidade",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CPF,
            "cnpj": "",
            "cpf": "12345678909",
            "modo_escrituracao": ModoEscrituracao.CONTABILIDADE,
        },
        follow=True,
    )

    assert resposta.status_code == 200
    empresa = Empresa.objects.get(cpf="12345678909")
    assert empresa.modo_escrituracao == ModoEscrituracao.CONTABILIDADE


# ---------------------------------------------------------------------------
# Erros do servidor no formulário — nunca 500, sempre com o que foi digitado
# ---------------------------------------------------------------------------


def test_empresa_cpf_invalido_recusa_no_formulario_preservando_o_digitado(client, escritorio):
    _gestor_logado(client, escritorio)

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "CPF Inválido Ltda",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CPF,
            "cnpj": "",
            # Sequência repetida: recusada por regra própria (RC-2/DL-038),
            # nunca 500.
            "cpf": "11111111111",
        },
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "CPF inválido" in conteudo
    # O que foi digitado continua lá — arquétipo B, direcao-de-arte.md §2.B.
    assert 'value="CPF Inválido Ltda"' in conteudo
    assert not Empresa.objects.filter(razao_social="CPF Inválido Ltda").exists()


def test_empresa_cpf_e_cnpj_juntos_sao_recusados_com_mensagem_de_exclusividade(client, escritorio):
    _gestor_logado(client, escritorio)

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Os Dois Preenchidos Ltda",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CPF,
            "cnpj": "11122233000183",
            "cpf": "11144477735",
        },
    )

    assert resposta.status_code == 200
    assert (
        "CNPJ não pode ser informado quando o tipo de inscrição é CPF." in resposta.content.decode()
    )
    assert not Empresa.objects.filter(razao_social="Os Dois Preenchidos Ltda").exists()


def test_empresa_cpf_duplicado_e_recusado_no_formulario_nunca_200_silencioso(client, escritorio):
    # Bug corrigido nesta etapa: o `except CNPJDuplicado` de `criar_empresa`
    # só lia a chave "cnpj" do `message_dict` — um CPF duplicado (chave
    # "cpf") não adicionava erro NENHUM ao formulário: 200, sem aviso, e a
    # segunda empresa não era gravada (falha convertida em sucesso
    # aparente, AGENTS.md §8).
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Primeiro Fulano",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
    )
    _gestor_logado(client, escritorio)

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Segundo Fulano",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CPF,
            "cnpj": "",
            "cpf": "11144477735",
        },
    )

    assert resposta.status_code == 200
    assert "já existe" in resposta.content.decode()
    assert Empresa.objects.filter(cpf="11144477735").count() == 1


def test_empresa_cpf_vazio_com_tipo_cpf_da_mensagem_de_obrigatorio(client, escritorio):
    _gestor_logado(client, escritorio)

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Sem CPF Ltda",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CPF,
            "cnpj": "",
            "cpf": "",
        },
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Este campo é obrigatório." in conteudo
    assert not Empresa.objects.filter(razao_social="Sem CPF Ltda").exists()


# ---------------------------------------------------------------------------
# Formulário — teste unitário (sem client) das duas mensagens da regra
# cruzada, e da sugestão de HI-23 no nível do form
# ---------------------------------------------------------------------------


def test_empresa_form_cnpj_preenchido_com_tipo_cpf_da_erro_de_exclusividade():
    form = EmpresaForm(
        data={
            "razao_social": "Empresa Ltda",
            "nome_fantasia": "",
            "tipo_inscricao": TipoInscricao.CPF,
            "cnpj": "11122233000183",
            "cpf": "11144477735",
        }
    )

    assert not form.is_valid()
    assert form.errors["cnpj"] == ["CNPJ não pode ser informado quando o tipo de inscrição é CPF."]


def test_empresa_form_sem_tipo_inscricao_se_comporta_como_cnpj_compatibilidade():
    # Compatibilidade com o formulário de antes da DL-038: um POST que não
    # sabe que "tipo de inscrição" existe (não envia o campo) continua
    # tratado como CNPJ.
    form = EmpresaForm(
        data={"razao_social": "Empresa Ltda", "nome_fantasia": "", "cnpj": "11122233000183"}
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["tipo_inscricao"] == TipoInscricao.CNPJ
    assert form.cleaned_data["modo_escrituracao"] == ModoEscrituracao.CONTABILIDADE


# ---------------------------------------------------------------------------
# Lista de empresas: rótulo/inscrição corretos e modo de escrituração
# ---------------------------------------------------------------------------


def test_lista_mostra_rotulo_inscricao_e_modo_de_cada_empresa(client, escritorio):
    Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa CNPJ Ltda", cnpj="11122233000183"
    )
    Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano de Tal",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    _gestor_logado(client, escritorio)

    conteudo = client.get(reverse("empresas:lista")).content.decode()

    assert "CNPJ 11.122.233/0001-83" in conteudo
    assert "CPF 111.444.777-35" in conteudo
    assert "Contabilidade (partidas dobradas)" in conteudo
    assert "Livro-caixa" in conteudo


def test_lista_empresa_livro_caixa_nao_oferece_link_de_contabilidade(client, escritorio):
    empresa_livro_caixa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano Livro-Caixa",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        cnpj="",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    _gestor_logado(client, escritorio)

    conteudo = client.get(reverse("empresas:lista")).content.decode()

    assert "a contabilidade por partidas dobradas não se aplica" in conteudo
    assert reverse("contabilidade_web:balancete", args=[empresa_livro_caixa.id]) not in conteudo


def test_lista_empresa_contabilidade_continua_com_links_de_contabilidade(client, escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa CNPJ Ltda", cnpj="11122233000183"
    )
    _gestor_logado(client, escritorio)

    conteudo = client.get(reverse("empresas:lista")).content.decode()

    assert reverse("contabilidade_web:balancete", args=[empresa.id]) in conteudo
    assert reverse("contabilidade_web:plano_de_contas", args=[empresa.id]) in conteudo
    assert reverse("contabilidade_web:lancamento_novo", args=[empresa.id]) in conteudo
