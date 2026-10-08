"""DL-072 (frente B) — telas da escrituração das NFS-e prestadas.

Critérios de TELA do plano (docs/planos/DL-072-escrituracao-das-nfse-prestadas.md):
- 1: nota recebida aparece na competência do `dCompet`, não na do `dhEmi`;
- 2: efetivar pela tela grava natureza, datas e valores, e redireciona;
- 3: natureza SUGERIDA pré-selecionada, trocável antes de efetivar;
- 4: estorno com motivo obrigatório; efetivada não se edita pela tela;
- 5: nota cancelada não é efetivada (mensagem), e a pendência aparece;
- 6: repetir a efetivação pela tela não duplica;
- 7: nota tomada não aparece na lista;
- 8: conferência com recebidas = escrituradas + pendentes, e avisos/bloqueios;
- 9: 404 entre escritórios e entre empresas do mesmo escritório;
- 10: CLIENTE não acessa; PARALEGAL vê as listas sem botões e recebe 403 no POST.

Dados 100% sintéticos (xml_sinteticos.py). Autorização e isolamento são
verificados pelo cliente HTTP real, com sessão e escritório ativo resolvidos
pelo middleware. A moldura de acessibilidade é a MESMA guarda das outras telas
do produto (`assert_moldura_acessivel`, test_dl024_atalhos_e_acessibilidade).
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
    assert_moldura_acessivel,
)
from apps.fiscal import escrituracao as servico
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    EstadoEscrituracao,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import (
    chave_nfse_de,
    identificador_nfse,
    xml_evento,
    xml_nfse,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

NATUREZA_DEVIDA = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
NATUREZA_RETIDA = NaturezaOperacao.PRESTADO_ISS_RETIDO


# ---------------------------------------------------------------------------
# Fábrica de dados sintéticos e de URLs
# ---------------------------------------------------------------------------


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _logar(client, usuario):
    client.force_login(usuario)
    return client


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-telas-escrituracao")


@pytest.fixture
def paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-a-telas-escrituracao")


def _nota(escritorio, usuario, sufixo=1, **kwargs):
    """NFS-e prestada pela `empresa_a` e tomada pela `empresa_a2` (padrão do
    xml_sinteticos), com o sufixo no identificador e no número."""
    identificador = identificador_nfse(sufixo)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(identificador=identificador, numero=str(sufixo), **kwargs),
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    return DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)


def _cancelar(escritorio, usuario, documento):
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador), codigo="e101101"),
        nome_arquivo="evento.xml",
    )


def _vinculo(documento, empresa, papel=PapelDocumento.PRESTADOR):
    return VinculoDocumentoEmpresa.objects.get(documento=documento, empresa=empresa, papel=papel)


def _url_lista():
    return reverse("fiscal_web:notas_a_escriturar")


def _url_escriturar(empresa, vinculo):
    return reverse("fiscal_web:escriturar_nota", args=[empresa.pk, vinculo.pk])


def _url_detalhe(empresa, escrituracao):
    return reverse("fiscal_web:escrituracao_detalhe", args=[empresa.pk, escrituracao.pk])


def _url_estornar(empresa, escrituracao):
    return reverse("fiscal_web:escrituracao_estornar", args=[empresa.pk, escrituracao.pk])


def _url_conferencia():
    return reverse("fiscal_web:conferencia_escrituracao")


def _competencia(empresa, ano=2024, mes=1):
    return {"empresa": empresa.pk, "ano": ano, "mes": mes}


ALVO_DO_FORMULARIO = 'name="acao"'


# ---------------------------------------------------------------------------
# Renderização (200) e moldura de acessibilidade — as cinco telas novas
# ---------------------------------------------------------------------------


def test_tela_notas_a_escriturar_e_acessivel(client, escritorio_a, empresa_a, usuario_gestor_a):
    _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), _competencia(empresa_a))

    assert resposta.status_code == 200
    assert "fiscal/notas_a_escriturar.html" in [t.name for t in resposta.templates]
    assert "<caption" in resposta.content.decode()
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_notas_a_escriturar_estado_vazio_e_acessivel(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    sem_empresa = client.get(_url_lista())
    sem_notas = client.get(_url_lista(), _competencia(empresa_a))

    assert sem_empresa.status_code == 200
    assert "Escolha uma empresa para ver as notas a escriturar." in sem_empresa.content.decode()
    assert sem_notas.status_code == 200
    assert "Nenhuma nota prestada por" in sem_notas.content.decode()
    assert_moldura_acessivel(sem_empresa.content.decode())
    assert_moldura_acessivel(sem_notas.content.decode())


def test_tela_escriturar_nota_e_acessivel(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a)))

    assert resposta.status_code == 200
    assert "fiscal/escriturar_nota.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_escrituracao_detalhe_e_acessivel(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_detalhe(empresa_a, escrituracao))

    assert resposta.status_code == 200
    assert "fiscal/escrituracao_detalhe.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_escrituracao_estornar_e_acessivel(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_estornar(empresa_a, escrituracao))

    assert resposta.status_code == 200
    assert "fiscal/escrituracao_estornar.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_conferencia_escrituracao_e_acessivel(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_a))

    assert resposta.status_code == 200
    assert "fiscal/conferencia_escrituracao.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


# ---------------------------------------------------------------------------
# Critério 1 — competência pelo dCompet, aviso de mês divergente
# ---------------------------------------------------------------------------


def test_competencia_pela_dcompet_na_lista(client, escritorio_a, empresa_a, usuario_gestor_a):
    # Emitida em janeiro, competência (dCompet) em fevereiro: só aparece em fevereiro.
    _nota(escritorio_a, usuario_gestor_a, d_compet="2024-02-01")
    _logar(client, usuario_gestor_a)

    de_janeiro = client.get(_url_lista(), _competencia(empresa_a, 2024, 1))
    de_fevereiro = client.get(_url_lista(), _competencia(empresa_a, 2024, 2))

    assert de_janeiro.context["total_notas"] == 0
    assert de_fevereiro.context["total_notas"] == 1


def test_aviso_quando_competencia_difere_da_emissao(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a, d_compet="2024-02-01")
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), _competencia(empresa_a, 2024, 2))
    conteudo = resposta.content.decode()

    assert resposta.context["notas_com_aviso"] == 1
    assert "têm mês de competência diferente do mês de emissão" in conteudo
    assert "Emitida em 01/2024" in conteudo


def test_sem_aviso_quando_competencia_e_a_emissao(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), _competencia(empresa_a, 2024, 1))

    assert resposta.context["notas_com_aviso"] == 0
    assert "diferente do mês de emissão" not in resposta.content.decode()


# ---------------------------------------------------------------------------
# Critério 3 — natureza sugerida pré-selecionada, trocável antes de efetivar
# ---------------------------------------------------------------------------


def test_natureza_sugerida_retida_vem_pre_selecionada(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="2")
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a))).content.decode()

    assert f'value="{NATUREZA_RETIDA.value}" selected' in conteudo
    assert "Sugerida a partir do XML" in conteudo
    # Só a sugestão aparece pré-selecionada: nada foi gravado.
    assert EscrituracaoFiscal.objects.count() == 0


def test_natureza_sugerida_devida_quando_nao_retida(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="1")
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a))).content.decode()

    assert f'value="{NATUREZA_DEVIDA.value}" selected' in conteudo


# ---------------------------------------------------------------------------
# HI-67 — seis naturezas na tela, e sem sugestão nada vem marcado
# ---------------------------------------------------------------------------


def test_tela_mostra_as_seis_naturezas_com_rotulos(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a))).content.decode()

    assert len(NaturezaOperacao.choices) == 6
    for valor, rotulo in NaturezaOperacao.choices:
        assert f'value="{valor}"' in conteudo
        assert rotulo in conteudo


def test_exportacao_sugerida_vem_pre_selecionada(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="3")
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a))).content.decode()

    assert f'value="{NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO.value}" selected' in conteudo
    assert "Sugerida a partir do XML" in conteudo
    assert EscrituracaoFiscal.objects.count() == 0


def test_sem_sugestao_nenhuma_natureza_vem_marcada(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    # XML com não incidência (tribISSQN 4): sem sugestão, nenhuma opção marcada.
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="4")
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a))).content.decode()

    for valor, _rotulo in NaturezaOperacao.choices:
        assert f'value="{valor}" selected' not in conteudo
    # A primeira opção é um aviso vazio e marcado, não uma natureza.
    assert '<option value="" selected>' in conteudo
    assert "não incidência de ISS" in conteudo
    assert EscrituracaoFiscal.objects.count() == 0


def test_sem_sugestao_efetivar_sem_escolher_e_recusado_pela_tela(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="4")
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": "", "acao": "efetivar"},
    )

    # Auditoria A5: o vazio tem mensagem própria, e não a de natureza desconhecida.
    assert resposta.status_code == 200
    assert "Escolha a natureza da operação." in resposta.content.decode()
    assert EscrituracaoFiscal.objects.count() == 0


def test_sem_sugestao_contador_escolhe_e_efetiva_pela_tela(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, trib_issqn="4")
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NaturezaOperacao.PRESTADO_FORA_LISTA_LC116.value, "acao": "efetivar"},
    )

    escrituracao = EscrituracaoFiscal.objects.get()
    assert resposta.status_code == 302
    assert escrituracao.natureza == NaturezaOperacao.PRESTADO_FORA_LISTA_LC116


def test_lista_mostra_sem_sugestao_com_rotulo_proprio(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a, trib_issqn="4")
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), _competencia(empresa_a, 2024, 1))

    assert resposta.status_code == 200
    assert "Sem sugestão — escolha a natureza" in resposta.content.decode()


# ---------------------------------------------------------------------------
# Critério 2 — efetivar e salvar rascunho pela tela; repetir não duplica (6)
# ---------------------------------------------------------------------------


def test_efetivar_pela_tela_grava_e_redireciona(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a, v_serv="250.50", v_liq="240.00")
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NATUREZA_DEVIDA.value, "acao": "efetivar"},
    )

    escrituracao = EscrituracaoFiscal.objects.get()
    assert resposta.status_code == 302
    assert resposta["Location"] == _url_detalhe(empresa_a, escrituracao)
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA
    assert escrituracao.natureza == NATUREZA_DEVIDA
    assert escrituracao.valor_servico == Decimal("250.50")
    assert escrituracao.valor_liquido == Decimal("240.00")
    assert escrituracao.data_competencia == nota.d_competencia
    assert escrituracao.efetivada_por == usuario_gestor_a
    assert RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.efetivada").exists()


def test_salvar_rascunho_pela_tela_nao_efetiva(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NATUREZA_RETIDA.value, "acao": "rascunho"},
    )

    rascunho = EscrituracaoFiscal.objects.get()
    assert resposta.status_code == 302
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    assert rascunho.natureza == NATUREZA_RETIDA
    assert rascunho.efetivada_em is None
    assert not RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.efetivada").exists()


def test_repetir_efetivacao_pela_tela_nao_duplica(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)
    url = _url_escriturar(empresa_a, _vinculo(nota, empresa_a))
    dados = {"natureza": NATUREZA_DEVIDA.value, "acao": "efetivar"}

    primeira = client.post(url, dados)
    segunda = client.post(url, dados)

    assert primeira.status_code == 302
    assert segunda.status_code == 302
    assert EscrituracaoFiscal.objects.count() == 1
    assert RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.efetivada").count() == 1


# ---------------------------------------------------------------------------
# Critério 5 e recusas do serviço: mensagem, status 200, nada gravado
# ---------------------------------------------------------------------------


def test_nota_cancelada_nao_e_efetivada_pela_tela(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _cancelar(escritorio_a, usuario_gestor_a, nota)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NATUREZA_DEVIDA.value, "acao": "efetivar"},
    )

    assert resposta.status_code == 200
    assert "Nota cancelada não pode ser escriturada." in resposta.content.decode()
    assert EscrituracaoFiscal.objects.count() == 0


def test_efetivada_com_outra_natureza_vira_mensagem_sem_gravar(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    servico.efetivar_escrituracao(_vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NATUREZA_RETIDA.value, "acao": "efetivar"},
    )

    escrituracao = EscrituracaoFiscal.objects.get()
    assert resposta.status_code == 200
    assert "já está escriturada como" in resposta.content.decode()
    assert escrituracao.natureza == NATUREZA_DEVIDA
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA


def test_nota_tomada_nao_e_escriturada_pela_tela(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)
    vinculo_tomador = _vinculo(nota, empresa_a2, papel=PapelDocumento.TOMADOR)

    resposta = client.post(
        _url_escriturar(empresa_a2, vinculo_tomador),
        {"natureza": NATUREZA_DEVIDA.value, "acao": "efetivar"},
    )

    assert resposta.status_code == 200
    assert "Só é escriturada a nota em que a empresa é prestadora" in resposta.content.decode()
    assert EscrituracaoFiscal.objects.count() == 0


def test_natureza_fora_do_catalogo_vira_mensagem(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": "natureza_inventada", "acao": "efetivar"},
    )

    assert resposta.status_code == 200
    assert "Natureza de operação desconhecida" in resposta.content.decode()
    assert EscrituracaoFiscal.objects.count() == 0


def test_campo_nao_contratado_no_formulario_vira_400_sem_gravar(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NATUREZA_DEVIDA.value, "acao": "efetivar", "valor_servico": "1,00"},
    )

    assert resposta.status_code == 400
    assert EscrituracaoFiscal.objects.count() == 0


# ---------------------------------------------------------------------------
# Critério 4 — estorno com motivo; sem motivo, mensagem; efetivada não se edita
# ---------------------------------------------------------------------------


def test_estorno_com_motivo_pela_tela(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_estornar(empresa_a, escrituracao),
        {"motivo": "Nota emitida em duplicidade pelo prestador"},
    )

    escrituracao.refresh_from_db()
    assert resposta.status_code == 302
    assert resposta["Location"] == _url_detalhe(empresa_a, escrituracao)
    assert escrituracao.estado == EstadoEscrituracao.ESTORNADA
    assert escrituracao.motivo_estorno == "Nota emitida em duplicidade pelo prestador"
    assert escrituracao.estornada_por == usuario_gestor_a
    assert RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.estornada").exists()


def test_estorno_sem_motivo_mostra_mensagem_e_nao_grava(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    resposta = client.post(_url_estornar(empresa_a, escrituracao), {"motivo": "   "})

    escrituracao.refresh_from_db()
    assert resposta.status_code == 200
    assert "Informe o motivo do estorno." in resposta.content.decode()
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA


def test_formulario_de_estorno_exige_motivo_no_navegador(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_estornar(empresa_a, escrituracao)).content.decode()

    assert '<textarea id="id_motivo" name="motivo" required' in conteudo
    assert "Obrigatório." in conteudo


def test_detalhe_mostra_quem_efetivou_e_o_motivo_do_estorno(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    servico.estornar_escrituracao(escrituracao, "Valor errado no XML", usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_detalhe(empresa_a, escrituracao)).content.decode()

    assert "Efetivada por" in conteudo
    assert usuario_gestor_a.get_username() in conteudo
    assert "Estornada em" in conteudo
    assert "Motivo do estorno" in conteudo
    assert "Valor errado no XML" in conteudo


def test_cancelamento_depois_da_escrituracao_aparece_como_pendencia_ate_o_estorno(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    # Critério 5 do plano: cancelamento depois da efetivação vira pendência,
    # sem estorno automático; a pendência some quando a escrituração é estornada.
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _cancelar(escritorio_a, usuario_gestor_a, nota)
    _logar(client, usuario_gestor_a)

    detalhe = client.get(_url_detalhe(empresa_a, escrituracao)).content.decode()
    lista = client.get(_url_lista(), _competencia(empresa_a, 2024, 1)).content.decode()

    assert "foi cancelada depois desta escrituração" in detalhe
    assert "Cancelada depois de escriturada" in lista
    assert EstadoEscrituracao.EFETIVADA == EscrituracaoFiscal.objects.get().estado

    servico.estornar_escrituracao(escrituracao, "Cancelada pela prefeitura", usuario_gestor_a)
    lista_depois = client.get(_url_lista(), _competencia(empresa_a, 2024, 1)).content.decode()

    assert "Cancelada depois de escriturada" not in lista_depois
    assert "Cancelada" in lista_depois


def test_efetivada_nao_tem_formulario_de_escriturar(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    servico.efetivar_escrituracao(_vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a))).content.decode()

    assert ALVO_DO_FORMULARIO not in conteudo
    assert "Ver a escrituração" in conteudo


# ---------------------------------------------------------------------------
# Critério 8 — conferência com a soma fechando, bloqueios e avisos listados
# ---------------------------------------------------------------------------


def test_conferencia_fecha_a_soma_e_lista_bloqueios(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    # Três notas da MESMA competência (janeiro): uma efetivada, uma rascunho
    # (bloqueia) e uma cancelada que nunca foi escriturada (não bloqueia).
    efetivada = _nota(escritorio_a, usuario_gestor_a, sufixo=1)
    rascunho = _nota(escritorio_a, usuario_gestor_a, sufixo=2)
    cancelada = _nota(escritorio_a, usuario_gestor_a, sufixo=3)
    servico.efetivar_escrituracao(_vinculo(efetivada, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    servico.salvar_rascunho(_vinculo(rascunho, empresa_a), NATUREZA_RETIDA, usuario_gestor_a)
    _cancelar(escritorio_a, usuario_gestor_a, cancelada)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1))

    contexto = resposta.context
    assert resposta.status_code == 200
    assert contexto["recebidas"] == 3
    assert contexto["escrituradas"] == 1
    assert contexto["pendentes"] == 2
    assert contexto["recebidas"] == contexto["escrituradas"] + contexto["pendentes"]
    assert contexto["fecha"] is True
    assert contexto["pendentes_com_bloqueio"] == 1
    assert contexto["pendentes_sem_bloqueio"] == 1
    assert [linha["nota"].documento.pk for linha in contexto["bloqueios"]] == [rascunho.pk]
    conteudo = resposta.content.decode()
    assert "a conferência fecha" in conteudo
    assert "Relatório de conferência" in conteudo


def test_conferencia_lista_bloqueio_com_a_nota(client, escritorio_a, empresa_a, usuario_gestor_a):
    rascunho = _nota(escritorio_a, usuario_gestor_a, sufixo=4)
    servico.salvar_rascunho(_vinculo(rascunho, empresa_a), NATUREZA_RETIDA, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1))

    contexto = resposta.context
    assert [linha["nota"].documento.pk for linha in contexto["bloqueios"]] == [rascunho.pk]
    assert contexto["avisos"] == []
    assert "Nenhuma nota exige ação nesta competência." not in resposta.content.decode()


def test_conferencia_mostra_aviso_de_competencia_diferente(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a, sufixo=5, d_compet="2024-03-01")
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 3))

    assert len(resposta.context["avisos"]) == 1
    assert "Emitida em 01/2024" in resposta.content.decode()


def test_conferencia_de_empresa_de_outro_escritorio_nao_vaza(
    client, escritorio_a, empresa_b, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_b, 2024, 1))

    # Auditoria A9: empresa de OUTRO escritório é 404 (critério 9 do plano), e não
    # mais 400. A mudança é a decisão do arquiteto: 400 ficou só para entrada
    # malformada. O nome da empresa não pode aparecer na resposta.
    assert resposta.status_code == 404
    assert "Empresa B Ltda" not in resposta.content.decode()


def test_competencia_invalida_mantem_o_que_foi_digitado(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), {"empresa": empresa_a.pk, "ano": "abc", "mes": "1"})

    conteudo = resposta.content.decode()
    assert resposta.status_code == 400
    assert "Competência inválida" in conteudo
    assert f'value="{empresa_a.pk}" selected' in conteudo
    assert 'name="ano" value="abc"' in conteudo


# ---------------------------------------------------------------------------
# Critério 7 — nota tomada não aparece na lista; link da lista de documentos
# ---------------------------------------------------------------------------


def test_nota_tomada_nao_aparece_na_lista(client, escritorio_a, empresa_a2, usuario_gestor_a):
    _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), _competencia(empresa_a2, 2024, 1))

    assert resposta.status_code == 200
    assert resposta.context["total_notas"] == 0
    assert "Nenhuma nota prestada por" in resposta.content.decode()


def test_lista_de_documentos_tem_escriturar_so_para_prestador(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    conteudo = client.get(reverse("fiscal_web:documentos_lista")).content.decode()

    assert _url_escriturar(empresa_a, _vinculo(nota, empresa_a)) in conteudo
    assert (
        _url_escriturar(empresa_a2, _vinculo(nota, empresa_a2, PapelDocumento.TOMADOR))
        not in conteudo
    )
    assert "Escriturar — Prestadora A Ltda" in conteudo


def test_lista_de_documentos_nao_linka_nota_cancelada(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _cancelar(escritorio_a, usuario_gestor_a, nota)
    _logar(client, usuario_gestor_a)

    conteudo = client.get(reverse("fiscal_web:documentos_lista")).content.decode()

    assert _url_escriturar(empresa_a, _vinculo(nota, empresa_a)) not in conteudo


# ---------------------------------------------------------------------------
# Critério 10 — PARALEGAL vê sem botões e recebe 403; CLIENTE não acessa
# ---------------------------------------------------------------------------


def test_paralegal_ve_as_listas_sem_botoes(
    client, escritorio_a, empresa_a, usuario_gestor_a, paralegal_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, paralegal_a)

    lista = client.get(_url_lista(), _competencia(empresa_a, 2024, 1)).content.decode()
    documentos = client.get(reverse("fiscal_web:documentos_lista")).content.decode()
    conferencia = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1)).content.decode()

    assert "Seu papel consulta estas notas" in lista
    assert _url_escriturar(empresa_a, _vinculo(nota, empresa_a)) not in lista
    assert _url_escriturar(empresa_a, _vinculo(nota, empresa_a)) not in documentos
    assert '<th scope="col">Escrituração</th>' not in documentos
    assert "Efetivar escrituração" not in conferencia


def test_paralegal_nao_abre_nem_grava_escrituracao(
    client, escritorio_a, empresa_a, usuario_gestor_a, paralegal_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, paralegal_a)
    url_escriturar = _url_escriturar(empresa_a, _vinculo(nota, empresa_a))

    assert client.get(url_escriturar).status_code == 403
    assert (
        client.post(
            url_escriturar, {"natureza": NATUREZA_RETIDA.value, "acao": "efetivar"}
        ).status_code
        == 403
    )
    assert client.get(_url_estornar(empresa_a, escrituracao)).status_code == 403
    assert client.post(_url_estornar(empresa_a, escrituracao), {"motivo": "x"}).status_code == 403

    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA
    assert EscrituracaoFiscal.objects.count() == 1


def test_paralegal_consulta_detalhe_da_escrituracao(
    client, escritorio_a, empresa_a, usuario_gestor_a, paralegal_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, paralegal_a)

    resposta = client.get(_url_detalhe(empresa_a, escrituracao))

    assert resposta.status_code == 200
    assert "Estornar escrituração" not in resposta.content.decode()


def test_cliente_nao_acessa_nenhuma_tela_de_escrituracao(
    client, escritorio_a, empresa_a, usuario_gestor_a, usuario_cliente_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_cliente_a)

    urls = [
        _url_lista(),
        _url_conferencia(),
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        _url_detalhe(empresa_a, escrituracao),
        _url_estornar(empresa_a, escrituracao),
    ]
    assert [client.get(url).status_code for url in urls] == [403] * len(urls)
    assert (
        client.post(urls[2], {"natureza": NATUREZA_DEVIDA.value, "acao": "efetivar"}).status_code
        == 403
    )


@pytest.mark.parametrize(
    "nome_rota,argumentos",
    [
        ("fiscal_web:notas_a_escriturar", []),
        ("fiscal_web:conferencia_escrituracao", []),
    ],
)
def test_anonimo_e_redirecionado_ao_login(client, nome_rota, argumentos):
    resposta = client.get(reverse(nome_rota, args=argumentos))

    assert resposta.status_code == 302
    assert "login" in resposta["Location"]


def test_anonimo_e_redirecionado_nas_telas_com_id(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    urls = [
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        _url_detalhe(empresa_a, escrituracao),
        _url_estornar(empresa_a, escrituracao),
    ]
    for url in urls:
        resposta = client.get(url)
        assert resposta.status_code == 302
        assert "login" in resposta["Location"]


# ---------------------------------------------------------------------------
# Critério 9 — isolamento: 404 entre escritórios e entre empresas
# ---------------------------------------------------------------------------


def test_outro_escritorio_recebe_404_nas_telas_de_uma_nota(
    client, escritorio_a, empresa_a, usuario_gestor_a, gestor_b
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, gestor_b)

    assert client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a))).status_code == 404
    assert client.get(_url_detalhe(empresa_a, escrituracao)).status_code == 404
    assert client.get(_url_estornar(empresa_a, escrituracao)).status_code == 404
    assert (
        client.post(
            _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
            {"natureza": NATUREZA_RETIDA.value, "acao": "efetivar"},
        ).status_code
        == 404
    )
    assert client.post(_url_estornar(empresa_a, escrituracao), {"motivo": "x"}).status_code == 404
    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA


def test_outro_escritorio_nao_lista_notas_pelo_filtro_de_empresa(
    client, escritorio_a, empresa_a, usuario_gestor_a, gestor_b
):
    _nota(escritorio_a, usuario_gestor_a)
    _logar(client, gestor_b)

    resposta = client.get(_url_lista(), _competencia(empresa_a, 2024, 1))

    # Auditoria A9: empresa de OUTRO escritório é 404 (critério 9), e não mais 400.
    # A mudança é decisão do arquiteto. O nome da empresa não pode aparecer.
    assert resposta.status_code == 404
    assert "Prestadora A Ltda" not in resposta.content.decode()


def test_vinculo_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    # Vínculo da nota (que pertence a empresa_a) pedido pelo caminho de empresa_a2.
    assert client.get(_url_escriturar(empresa_a2, _vinculo(nota, empresa_a))).status_code == 404


def test_escrituracao_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    assert client.get(_url_detalhe(empresa_a2, escrituracao)).status_code == 404
    assert client.get(_url_estornar(empresa_a2, escrituracao)).status_code == 404


# ---------------------------------------------------------------------------
# Menu e home do módulo (padrão existente: aparece a quem consulta)
# ---------------------------------------------------------------------------


def test_menu_fiscal_mostra_escrituracao_a_quem_consulta(client, paralegal_a, usuario_cliente_a):
    _logar(client, paralegal_a)
    assert (
        reverse("fiscal_web:notas_a_escriturar")
        in client.get(reverse("tenancy:painel")).content.decode()
    )

    _logar(client, usuario_cliente_a)
    assert (
        reverse("fiscal_web:notas_a_escriturar")
        not in client.get(reverse("tenancy:painel")).content.decode()
    )


def test_home_do_fiscal_tem_atalho_para_notas_a_escriturar(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(reverse("module_home:home", args=["fiscal"]))

    # Confere o ATALHO da home (não o texto do menu, que também traz o link).
    atalhos = resposta.context["home"]["atalhos"]
    assert resposta.status_code == 200
    assert any(
        atalho["url"].startswith(_url_lista()) and atalho["rotulo"] == "Notas a escriturar"
        for atalho in atalhos
    )


def test_atalho_da_home_nao_aparece_para_quem_nao_consulta(client, escritorio_a, usuario_cliente_a):
    _logar(client, usuario_cliente_a)

    # CLIENTE não abre a home do Fiscal (403): nenhum atalho pode chegar a ela.
    resposta = client.get(reverse("module_home:home", args=["fiscal"]))

    assert resposta.status_code == 403
    assert "Notas a escriturar" not in resposta.content.decode()


# ---------------------------------------------------------------------------
# Conteúdo verificado: datas e valores do detalhe, sucesso, tomador, estornada
# ---------------------------------------------------------------------------


def test_detalhe_mostra_as_tres_datas_e_os_valores(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, v_serv="250.50", v_liq="240.00")
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_detalhe(empresa_a, escrituracao)).content.decode()

    # HI-72 (auditoria A2): o rótulo diz o que é gravado, o dia do dhEmi.
    assert "Data de emissão (dia do dhEmi)" in conteudo
    assert "Data de competência (dCompet)" in conteudo
    assert "Data da escrituração" in conteudo
    assert "15/01/2024" in conteudo
    assert "01/2024" in conteudo
    assert "250,50" in conteudo
    assert "240,00" in conteudo


def test_efetivar_mostra_confirmacao_de_sucesso(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NATUREZA_DEVIDA.value, "acao": "efetivar"},
        follow=True,
    )

    assert resposta.status_code == 200
    assert "Nota escriturada com a natureza confirmada." in resposta.content.decode()


def test_tomador_na_tela_de_escriturar_nao_mostra_formulario(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(
        _url_escriturar(empresa_a2, _vinculo(nota, empresa_a2, PapelDocumento.TOMADOR))
    )

    assert resposta.status_code == 200
    assert "Esta nota não entra na escrituração desta empresa" in resposta.content.decode()
    assert ALVO_DO_FORMULARIO not in resposta.content.decode()


def test_nota_estornada_nao_pode_ser_estornada_de_novo_pela_tela(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    servico.estornar_escrituracao(escrituracao, "Lançamento de teste", usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_estornar(empresa_a, escrituracao))

    assert resposta.status_code == 200
    assert "pode ser estornada" in resposta.content.decode()
    assert ALVO_DO_FORMULARIO not in resposta.content.decode()


# ---------------------------------------------------------------------------
# Correção única da auditoria (rodada 1): A2, A5, A6, A7, A8, A9, A10, A11 nas telas
# ---------------------------------------------------------------------------

EXPORTACAO = NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO


@pytest.mark.parametrize("dh_emi", ["2024-01-31T23:30:00-04:00", "2024-01-31T22:30:00-05:00"])
def test_relatorio_nao_avisa_nota_de_31_01_em_fuso_a_oeste(
    client, escritorio_a, empresa_a, usuario_gestor_a, dh_emi
):
    # A2 (HI-72): o aviso usa o dia escrito no documento. Brasília daria 01/02 e um
    # aviso falso de "Emitida em 02/2024".
    _nota(escritorio_a, usuario_gestor_a, dh_emi=dh_emi, d_compet="2024-01-31")
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1)).content.decode()

    assert "Nenhuma nota com competência diferente do mês de emissão." in conteudo
    assert "Emitida em" not in conteudo


# A5 — natureza vazia e natureza fora do catálogo, pela tela.


@pytest.mark.parametrize("acao", ["efetivar", "rascunho"])
def test_natureza_vazia_pela_tela_tem_mensagem_de_escolha(
    client, escritorio_a, empresa_a, usuario_gestor_a, acao
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)), {"natureza": "", "acao": acao}
    )

    assert resposta.status_code == 200
    assert "Escolha a natureza da operação." in resposta.content.decode()
    assert EscrituracaoFiscal.objects.count() == 0


@pytest.mark.parametrize("acao", ["efetivar", "rascunho"])
def test_natureza_fora_do_catalogo_pela_tela_nomeia_o_catalogo(
    client, escritorio_a, empresa_a, usuario_gestor_a, acao
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_escriturar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": "natureza_inventada", "acao": acao},
    )

    assert resposta.status_code == 200
    assert "não é uma das naturezas do catálogo fiscal" in resposta.content.decode()
    assert EscrituracaoFiscal.objects.count() == 0


# A6 — a lista mostra a natureza GRAVADA quando há escrituração, e a sugerida só sem ela.


def test_lista_mostra_a_natureza_gravada_e_diz_a_origem(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    efetivada = _nota(escritorio_a, usuario_gestor_a, sufixo=1)  # XML sugere devido
    servico.efetivar_escrituracao(_vinculo(efetivada, empresa_a), EXPORTACAO, usuario_gestor_a)
    rascunho = _nota(escritorio_a, usuario_gestor_a, sufixo=2)
    servico.salvar_rascunho(_vinculo(rascunho, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    sem_escrituracao = _nota(escritorio_a, usuario_gestor_a, sufixo=3, tp_ret_issqn="2")
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), _competencia(empresa_a))

    linhas = {linha["nota"].documento.pk: linha for linha in resposta.context["linhas"]}
    assert linhas[efetivada.pk]["natureza"] == EXPORTACAO.label
    assert linhas[efetivada.pk]["origem_natureza"] == "Escriturada"
    assert linhas[rascunho.pk]["natureza"] == NATUREZA_DEVIDA.label
    assert linhas[rascunho.pk]["origem_natureza"] == "Rascunho, não efetivada"
    assert linhas[sem_escrituracao.pk]["natureza"] == NATUREZA_RETIDA.label
    assert linhas[sem_escrituracao.pk]["origem_natureza"] == "Sugerida pelo XML, não escriturada"
    conteudo = resposta.content.decode()
    assert '<th scope="col">Natureza</th>' in conteudo
    assert '<th scope="col">Natureza sugerida</th>' not in conteudo


# A7 — natureza gravada contra o XML aparece na conferência.


def test_conferencia_mostra_o_aviso_de_natureza_que_contradiz_o_xml(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="2")
    servico.efetivar_escrituracao(_vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1))

    conteudo = resposta.content.decode()
    assert len(resposta.context["divergencias"]) == 1
    assert "Natureza gravada diferente do XML" in conteudo
    assert "retenção do ISS (tpRetISSQN 2)" in conteudo


def test_conferencia_sem_contradicao_diz_que_nao_ha(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    conteudo = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1)).content.decode()

    assert "Nenhuma natureza gravada contradiz o XML nesta competência." in conteudo


# A8 — totais em reais e conciliação, com valores escritos à mão.


def test_conferencia_mostra_valores_em_reais_e_a_conciliacao(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    efetivada = _nota(escritorio_a, usuario_gestor_a, sufixo=1, v_serv="1000.00", v_liq="950.00")
    servico.efetivar_escrituracao(_vinculo(efetivada, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    _nota(escritorio_a, usuario_gestor_a, sufixo=2, v_serv="250.50", v_liq="240.00")
    rascunho = _nota(escritorio_a, usuario_gestor_a, sufixo=3, v_serv="0.01", v_liq="0.01")
    servico.salvar_rascunho(_vinculo(rascunho, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1))

    conteudo = resposta.content.decode()
    assert resposta.context["diferenca_nula"] is True
    for valor in ("1.250,51", "1.000,00", "250,51", "(sem diferença)"):
        assert valor in conteudo
    assert "Diferente de zero: verificar" not in conteudo


def test_conferencia_destaca_diferenca_quando_o_documento_mudou_depois(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    documento = _nota(escritorio_a, usuario_gestor_a, v_serv="1000.00", v_liq="950.00")
    servico.efetivar_escrituracao(_vinculo(documento, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a)
    DocumentoFiscal.objects.filter(pk=documento.pk).update(v_serv=Decimal("1000.01"))
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), _competencia(empresa_a, 2024, 1))

    conteudo = resposta.content.decode()
    assert resposta.context["diferenca_nula"] is False
    assert "-0,01" in conteudo
    assert "Diferente de zero: verificar" in conteudo


# A9 — empresa de outro escritório ou inexistente: 404; entrada malformada: 400.


def test_empresa_malformada_na_lista_continua_400(client, escritorio_a, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_lista(), {"empresa": "abc", "ano": 2024, "mes": 1})

    assert resposta.status_code == 400
    assert "inválida." in resposta.content.decode()


def test_empresa_inexistente_na_conferencia_e_404(client, escritorio_a, usuario_gestor_a):
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(), {"empresa": 999999, "ano": 2024, "mes": 1})

    assert resposta.status_code == 404


# A10 — a tela de uma nota não reprocessa o mês inteiro.


def test_tela_de_uma_nota_nao_reprocessa_o_mes(
    client, escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    def lista_do_mes_proibida(*_args, **_kwargs):
        raise AssertionError("a tela de uma nota não deve listar o mês inteiro")

    monkeypatch.setattr(servico, "notas_a_escriturar", lista_do_mes_proibida)

    resposta = client.get(_url_escriturar(empresa_a, _vinculo(nota, empresa_a)))

    assert resposta.status_code == 200
    assert resposta.context["nota"] is not None


# A11 — o detalhe mostra o histórico do vínculo e a trilha, sem outro escritório.


def test_detalhe_mostra_as_outras_escrituracoes_e_a_trilha(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    vinculo = _vinculo(nota, empresa_a)
    primeira = servico.efetivar_escrituracao(vinculo, NATUREZA_DEVIDA, usuario_gestor_a)
    servico.estornar_escrituracao(primeira, "natureza errada", usuario_gestor_a)
    segunda = servico.efetivar_escrituracao(vinculo, NATUREZA_RETIDA, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    detalhe_da_segunda = client.get(_url_detalhe(empresa_a, segunda))
    detalhe_da_primeira = client.get(_url_detalhe(empresa_a, primeira))

    # A anterior (estornada) aparece no detalhe da atual, com link para ela.
    assert _url_detalhe(empresa_a, primeira) in detalhe_da_segunda.content.decode()
    assert _url_detalhe(empresa_a, segunda) in detalhe_da_primeira.content.decode()
    assert [linha["acao"] for linha in detalhe_da_segunda.context["trilha"]] == ["Efetivada"]
    assert [linha["acao"] for linha in detalhe_da_primeira.context["trilha"]] == [
        "Efetivada",
        "Estornada",
    ]


def test_trilha_do_detalhe_nao_mostra_registro_de_outro_escritorio(
    client, escritorio_a, escritorio_b, empresa_a, usuario_gestor_a, gestor_b
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA_DEVIDA, usuario_gestor_a
    )
    # Registro de OUTRO escritório com o mesmo `objeto_id`: não pode aparecer aqui.
    RegistroAuditoria.objects.create(
        usuario=gestor_b,
        escritorio=escritorio_b,
        acao="escrituracao_fiscal.efetivada",
        objeto_tipo="EscrituracaoFiscal",
        objeto_id=str(escrituracao.pk),
        detalhes={},
    )
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_detalhe(empresa_a, escrituracao))

    assert [linha["acao"] for linha in resposta.context["trilha"]] == ["Efetivada"]
    assert "gestor-b-telas-escrituracao" not in resposta.content.decode()
