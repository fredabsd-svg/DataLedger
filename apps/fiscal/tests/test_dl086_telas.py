"""DL-086, frente fiscal: estados vazios no componente, ação de célula em botão e "Limpar filtros".

Achados da auditoria de layout (relatório consolidado no PR da DL-086), todos verificados no
contrato visual (docs/projeto/direcao-de-arte.md §8.4, §8.4b, §8.4c):

- A-12: estado vazio em prosa solta (recepção, relatório do envio) → `.estado-vazio` completo
  (ícone decorativo + título + descrição, e a saída quando há ação óbvia);
- A-13: anatomia de `.estado-vazio` incompleta na família DL-079 — ícone e descrição que
  faltavam;
- A-14: "Limpar filtros" (`.botao--fantasma`) nas parciais de filtro, SÓ com filtro ativo além
  do padrão — a decisão é da VIEW (`algum_filtro_ativo` compara o filtro efetivo ao padrão da
  tela), nunca derivada da querystring no template;
- A-18: link solto em célula de ação → `.botao--secundario.botao--pequeno` (padrão
  notas_a_escriturar.html);
- A-20: `role="alert"` na mensagem de erro do detalhe de NF-e, como nas demais `mensagem-error`.

Relógio controlado por cálculo (AGENTS.md §7): os casos "padrão" e "além do padrão" derivam de
`timezone.localdate()` na hora do teste, para o resultado não depender do dia da execução.
"""

import re

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.models import DocumentoFiscal, EventoFiscal, LoteDeRecepcao
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_EMITENTE_A,
    proc_evento_xml,
    xml_nfe,
)
from apps.fiscal.tests.xml_sinteticos import chave_nfse_de, xml_evento, xml_nfse

pytestmark = pytest.mark.django_db


def _html(resposta):
    return resposta.content.decode("utf-8")


def _hoje():
    return timezone.localdate()


def _mes_que_nao_e_o_corrente():
    """(ano, mês) que SEMPRE difere do mês corrente — o mês avança um, com virada de ano."""
    hoje = _hoje()
    return hoje.year, (hoje.month % 12) + 1


# ---------------------------------------------------------------------------
# A-14 — "Limpar filtros" só com filtro ativo além do padrão
# ---------------------------------------------------------------------------


def test_limpar_filtros_nao_aparece_sem_filtro_alem_do_padrao(client, usuario_gestor_a, empresa_a):
    """A-14: o padrão das telas de competência é o mês corrente. Sem filtro (e até com o mês
    corrente digitado — a MESMA consulta) não há o que limpar: o botão não aparece."""
    client.force_login(usuario_gestor_a)
    hoje = _hoje()
    url = reverse("fiscal_web:notas_a_escriturar")
    sem_parametro = client.get(url, {"empresa": empresa_a.pk})
    com_mes_corrente = client.get(
        url, {"empresa": empresa_a.pk, "ano": hoje.year, "mes": hoje.month}
    )
    assert "Limpar filtros" not in _html(sem_parametro)
    assert "Limpar filtros" not in _html(com_mes_corrente)


def test_limpar_filtros_aparece_com_competencia_alem_do_padrao(client, usuario_gestor_a, empresa_a):
    """A-14: com a competência fora do mês corrente, o `.botao--fantasma` aparece e o destino
    preserva a empresa de contexto (padrão nfe_lista.html) — limpar é voltar ao padrão da tela."""
    client.force_login(usuario_gestor_a)
    ano, mes = _mes_que_nao_e_o_corrente()
    resposta = client.get(
        reverse("fiscal_web:notas_a_escriturar"),
        {"empresa": empresa_a.pk, "ano": ano, "mes": mes},
    )
    html = _html(resposta)
    assert 'class="botao botao--fantasma"' in html
    assert f'href="{reverse("fiscal_web:notas_a_escriturar")}?empresa={empresa_a.pk}"' in html
    assert "Limpar filtros" in html


def test_limpar_filtros_aparece_quando_o_filtro_e_recusado(client, usuario_gestor_a, empresa_a):
    """A-14: filtro recusado é a saída da tela de erro — o botão aparece (como em
    documentos_lista.html). Com a empresa válida, o destino preserva a empresa de contexto e
    limpa o período digitado."""
    client.force_login(usuario_gestor_a)
    resposta = client.get(
        reverse("fiscal_web:notas_a_escriturar"),
        {"empresa": empresa_a.pk, "ano": "abc", "mes": "10"},
    )
    assert resposta.status_code == 400
    html = _html(resposta)
    assert "Limpar filtros" in html
    assert f'href="{reverse("fiscal_web:notas_a_escriturar")}?empresa={empresa_a.pk}"' in html


def test_limpar_filtros_nao_aparece_na_tela_sem_filtro_alem_da_empresa(
    client, usuario_gestor_a, empresa_a
):
    """A-14: atividades do Simples não tem período no filtro — com a empresa escolhida (o
    contexto, não um filtro) não há o que limpar. O botão nunca pode virar ruído fixo."""
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:atividades"), {"empresa": empresa_a.pk})
    assert "Limpar filtros" not in _html(resposta)


def test_limpar_filtros_com_ano_alem_do_padrao(client, usuario_gestor_a, empresa_a):
    """A-14: a folha do fator r filtra por ANO; o padrão é o ano corrente."""
    client.force_login(usuario_gestor_a)
    hoje = _hoje()
    url = reverse("fiscal_web:folhas_fator_r")
    assert "Limpar filtros" not in _html(
        client.get(url, {"empresa": empresa_a.pk, "ano": hoje.year})
    )
    com_ano_de_fora = client.get(url, {"empresa": empresa_a.pk, "ano": hoje.year - 1})
    assert "Limpar filtros" in _html(com_ano_de_fora)


def test_limpar_filtros_no_presumido_com_trimestre_alem_do_padrao(client, usuario_gestor_a):
    """A-14: as telas de período do Presumido têm o trimestre corrente como padrão."""
    client.force_login(usuario_gestor_a)
    hoje = _hoje()
    trimestre_corrente = (hoje.month - 1) // 3 + 1
    outro_trimestre = (trimestre_corrente % 4) + 1
    url = reverse("fiscal_web:presumido_apuracao")
    assert "Limpar filtros" not in _html(
        client.get(url, {"ano": hoje.year, "trimestre": trimestre_corrente})
    )
    assert "Limpar filtros" in _html(
        client.get(url, {"ano": hoje.year, "trimestre": outro_trimestre})
    )


def test_limpar_filtros_no_limite_com_tributo_alem_do_padrao(client, usuario_gestor_a):
    """A-14: no controle do limite, o padrão é o ano corrente no IRPJ — trocar o tributo já é
    filtro além do padrão."""
    client.force_login(usuario_gestor_a)
    hoje = _hoje()
    url = reverse("fiscal_web:presumido_limite")
    assert "Limpar filtros" not in _html(client.get(url, {"tributo": "irpj"}))
    assert "Limpar filtros" in _html(client.get(url, {"ano": hoje.year, "tributo": "csll"}))


def test_limpar_filtros_na_receita_do_mes_usa_a_parcial_propria(
    client, usuario_gestor_a, empresa_a
):
    """A-14: a parcial `_filtro_receita.html` recebe o mesmo par da view (cobre a tela do mês)."""
    client.force_login(usuario_gestor_a)
    hoje = _hoje()
    url = reverse("fiscal_web:receita_do_mes")
    assert "Limpar filtros" not in _html(
        client.get(url, {"empresa": empresa_a.pk, "ano": hoje.year, "mes": hoje.month})
    )
    ano, mes = _mes_que_nao_e_o_corrente()
    assert "Limpar filtros" in _html(
        client.get(url, {"empresa": empresa_a.pk, "ano": ano, "mes": mes})
    )


# ---------------------------------------------------------------------------
# A-12 — estados vazios no componente `.estado-vazio`
# ---------------------------------------------------------------------------


def test_recepcao_estado_vazio_no_componente(client, usuario_gestor_a):
    """A-12: "Nenhum envio..." era prosa solta — agora é `.estado-vazio` com a anatomia
    completa. Sem botão: a saída é o formulário de envio da própria tela (referência
    atividades.html). O texto literal continua (test_telas_dl010_f1.py o verifica)."""
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:recepcao")))
    assert '<div class="estado-vazio">' in html
    assert '<svg class="estado-vazio__icone" aria-hidden="true">' in html
    assert "estado-vazio__titulo" in html
    assert "estado-vazio__descricao" in html
    assert "Nenhum envio de documentos fiscais foi feito ainda" in html


def test_relatorio_do_envio_vazio_no_componente_com_saida(client, escritorio_a, usuario_gestor_a):
    """A-12: o lote sem resultado linha a linha vira `.estado-vazio` com a saída óbvia —
    um novo envio, em botão primário que nomeia a consequência."""
    lote = LoteDeRecepcao.objects.create(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        nome_arquivo="vazio.zip",
        tamanho_bytes=0,
    )
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:relatorio_envio", args=[lote.pk])))
    assert '<div class="estado-vazio">' in html
    assert '<svg class="estado-vazio__icone" aria-hidden="true">' in html
    assert "estado-vazio__titulo" in html
    assert "estado-vazio__descricao" in html
    assert f'<a class="botao botao--primario" href="{reverse("fiscal_web:recepcao")}">' in html
    assert "Enviar outro arquivo" in html


# ---------------------------------------------------------------------------
# A-13 — anatomia completa de `.estado-vazio` na família do Presumido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rota",
    [
        "fiscal_web:presumido_apuracao",
        "fiscal_web:presumido_limite",
        "fiscal_web:presumido_criterio",
        "fiscal_web:presumido_medidas",
        "fiscal_web:presumido_atividades",
        "fiscal_web:presumido_retencoes",
        "fiscal_web:presumido_receitas",
    ],
)
def test_estado_vazio_do_presumido_com_a_anatomia_completa(client, usuario_gestor_a, rota):
    """A-13: o estado "escolha uma empresa/ano/período" traz ícone decorativo, título e
    descrição — como as referências iss_aliquotas.html e atividades.html."""
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse(rota)))
    assert '<div class="estado-vazio">' in html
    assert '<svg class="estado-vazio__icone" aria-hidden="true">' in html
    assert "estado-vazio__titulo" in html
    assert "estado-vazio__descricao" in html


# ---------------------------------------------------------------------------
# A-18 — link solto em célula de ação vira botão pequeno
# ---------------------------------------------------------------------------


def test_documento_detalhe_bota_o_download_de_xml_em_botao(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    """A-18: "Baixar XML" (evento e documento) nunca é link solto — §8.4b."""
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador)),
        nome_arquivo="evento.xml",
    )
    evento = EventoFiscal.objects.get(escritorio=escritorio_a)

    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:documento_detalhe", args=[documento.pk])))
    assert (
        f'<a class="botao botao--secundario botao--pequeno" '
        f'href="{reverse("fiscal_web:evento_xml", args=[evento.pk])}">Baixar XML</a>' in html
    )
    assert (
        f'<a class="botao botao--secundario" '
        f'href="{reverse("fiscal_web:documento_xml", args=[documento.pk])}">'
        f"Baixar XML original do documento</a>" in html
    )


def test_relatorio_do_envio_bota_a_acao_da_celula_em_botao(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    """A-18: "Ver documento" e "Baixar XML" na coluna "Documento/evento" viram
    `.botao--secundario.botao--pequeno`; o que identifica (código, nº, chave) continua texto."""
    lote_do_documento = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    lote_do_evento = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador)),
        nome_arquivo="evento.xml",
    )
    evento = EventoFiscal.objects.get(escritorio=escritorio_a)

    client.force_login(usuario_gestor_a)
    com_documento = _html(
        client.get(reverse("fiscal_web:relatorio_envio", args=[lote_do_documento.pk]))
    )
    assert (
        f'<a class="botao botao--secundario botao--pequeno" '
        f'href="{reverse("fiscal_web:documento_detalhe", args=[documento.pk])}">'
        f"Ver documento</a>" in com_documento
    )
    com_evento = _html(client.get(reverse("fiscal_web:relatorio_envio", args=[lote_do_evento.pk])))
    assert (
        f'<a class="botao botao--secundario botao--pequeno" '
        f'href="{reverse("fiscal_web:evento_xml", args=[evento.pk])}">Baixar XML</a>' in com_evento
    )


# ---------------------------------------------------------------------------
# A-20 — a mensagem de erro do detalhe de NF-e é alerta
# ---------------------------------------------------------------------------


def test_aviso_de_cancelada_no_detalhe_da_nfe_e_alerta(client, escritorio_a, usuario_gestor_a):
    """A-20: `role="alert"` na `.mensagem-error` de nota cancelada, como nas ~30 irmãs — sem
    ele, quem usa leitor de tela não é avisado do cancelamento."""

    def enviar(conteudo, nome):
        return services.receber_envio(
            escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo=nome
        ).resultados.get()

    emitente = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Sintetica Ltda", cnpj=CNPJ_EMITENTE_A
    )
    cancelada = enviar(xml_nfe(numero="1"), "nota.xml").documento_nfe
    enviar(proc_evento_xml(chave=cancelada.chave, c_stat="135"), "cancelamento.xml")

    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:nfe_detalhe", args=[emitente.pk, cancelada.pk]))
    html = _html(resposta)
    assert re.search(
        r'<p class="mensagem mensagem-error" role="alert">'
        r"<strong>.*cancelada.*</strong></p>",
        html,
        re.IGNORECASE,
    )
