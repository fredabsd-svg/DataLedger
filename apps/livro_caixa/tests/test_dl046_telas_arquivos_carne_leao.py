"""DL-046, fatia 3 — telas dos arquivos do Carnê-Leão Web
(`especialista-frontend`).

Cobre a TELA de pendências/conferência (`arquivos_carne_leao`), os DOIS
downloads (`arquivo_rendimentos`/`arquivo_pagamentos`) e os quatro campos
novos do formulário de lançamento de caixa (`valor_irrf`,
`competencia_previdencia`, `multa_previdencia`, `juros_previdencia`).

O serviço (`apps.livro_caixa.carne_leao_arquivos`) já tem suíte própria
(`test_dl046_fatia3_arquivos_carne_leao.py`) com a reprodução linha a linha
dos arquivos-modelo oficiais — este arquivo testa só a TELA: que ela
apresenta o que o serviço devolveu sem recalcular nada, que o download sai
byte a byte igual ao do serviço (com o cabeçalho certo e nome de arquivo
NEUTRO), e que os cinco estados (vazio, carregando — não aplicável a view
síncrona —, erro, sucesso, sem permissão) existem.

⚠️ O teste de VALOR monetário aqui é de APRESENTAÇÃO (pt-BR) e de
conciliação com o serviço, feito com `Decimal` em Python — nunca com
agregação do banco (SQLite não preserva escala decimal em `Sum`, DE-020).
`apurar_livro_caixa` e o gerador somam em Python, por isso os totais
exibidos são exatos mesmo neste ambiente.

Dados 100% sintéticos. Datas em 2026, sempre no passado.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.tests.gatilhos_do_livro import gatilho_desligado
from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa.carne_leao_arquivos import gerar_arquivos_carne_leao
from apps.livro_caixa.models import ContaLivroCaixa, LancamentoCaixa, NaturezaCaixa
from apps.livro_caixa.services import criar_lancamento_caixa
from apps.livro_caixa.tests.test_dl069_livro_caixa_imutavel_no_banco import (
    IMUTAVEL_LANCAMENTO_CAIXA,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CPF_CLIENTE_A = "11144477735"
CPF_CLIENTE_B = "22255588846"


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel=Papel.GESTOR, username="gestor-arq"):
    usuario = _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")
    return usuario


@pytest.fixture
def cenario():
    """Duas empresas no MESMO escritório (isolamento de dado entre
    clientes de um escritório), uma empresa em modo contabilidade (recusa)
    e uma empresa de OUTRO escritório (404)."""
    escritorio_a = Escritorio.objects.create(nome="Escritório Arquivos A", cnpj="77788899000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório Arquivos B", cnpj="77788899000222")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Fulano de Tal — Arquivos",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_CLIENTE_A,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_a2 = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Beltrano de Tal — Arquivos",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_CLIENTE_B,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Empresa Contabilidade Arquivos Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b,
        razao_social="Ciclano de Tal — Arquivos",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="52998224725",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    contas = {
        "conta_aluguel": ContaLivroCaixa.objects.create(
            empresa=empresa_a,
            codigo="RA",
            nome="Aluguel recebido",
            natureza=NaturezaCaixa.RECEITA,
            codigo_carne_leao="R01.003.001",
        ),
        "conta_trabalho": ContaLivroCaixa.objects.create(
            empresa=empresa_a,
            codigo="RT",
            nome="Trabalho não assalariado",
            natureza=NaturezaCaixa.RECEITA,
            codigo_carne_leao="R01.001.001",
        ),
        "conta_previdencia": ContaLivroCaixa.objects.create(
            empresa=empresa_a,
            codigo="DPREV",
            nome="Previdência oficial paga",
            natureza=NaturezaCaixa.DESPESA,
            codigo_carne_leao="P20.01.00001",
        ),
        "conta_plano": ContaLivroCaixa.objects.create(
            empresa=empresa_a,
            codigo="D10",
            nome="Água do escritório",
            natureza=NaturezaCaixa.DESPESA,
            codigo_carne_leao="P10.01.00001",
        ),
        "conta_fora_da_tabela": ContaLivroCaixa.objects.create(
            empresa=empresa_a,
            codigo="RF",
            nome="Rendimento com código fora das tabelas",
            natureza=NaturezaCaixa.RECEITA,
            codigo_carne_leao="R01.999.999",
        ),
        # Conta SEM código do Carnê-Leão Web — só alcançável por ORM direto
        # (`full_clean()` sempre exige o código); mesmo padrão da suíte do
        # serviço. É o ÚNICO caso em que a conferência mostra diferença
        # diferente de zero.
        "conta_sem_codigo": ContaLivroCaixa.objects.create(
            empresa=empresa_a,
            codigo="RSC",
            nome="Receita legada sem código",
            natureza=NaturezaCaixa.RECEITA,
        ),
        "conta_aluguel_a2": ContaLivroCaixa.objects.create(
            empresa=empresa_a2,
            codigo="RA",
            nome="Aluguel recebido",
            natureza=NaturezaCaixa.RECEITA,
            codigo_carne_leao="R01.003.001",
        ),
    }
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_a2": empresa_a2,
        "empresa_contabilidade": empresa_contabilidade,
        "empresa_b": empresa_b,
        **contas,
    }


# ⚠️ Os HISTÓRICOS de teste usam só caractere representável em ISO-8859-1
# (sem travessão/em-dash, sem emoji): o leiaute oficial recusa — como
# PENDÊNCIA de histórico — qualquer caractere fora dessa codificação, e um
# "—" no histórico desviaria o lançamento para essa pendência em vez da que
# o teste quer exercitar (mesmo cuidado da suíte do serviço,
# test_dl046_fatia3_arquivos_carne_leao.py). O caso fora do latin-1 é
# exercitado de PROPÓSITO num teste próprio.
def _lancar(empresa, conta, dia, valor, *, historico="Movimento - teste de arquivos", **kwargs):
    return criar_lancamento_caixa(
        empresa=empresa,
        conta=conta,
        data=dia,
        # `valor` chega em pt-BR ("1.000,00"), como o formulário da tela
        # envia — a tradução aqui é só do TESTE; quem converte na aplicação
        # é `_decimal_do_formulario`/`para_decimal`.
        valor=Decimal(valor.replace(".", "").replace(",", ".")),
        historico=historico,
        **kwargs,
    )


def _lancar_receita_aluguel(empresa, conta, dia, valor, *, historico):
    return _lancar(empresa, conta, dia, valor, historico=historico, recebido_de="PF")


def _lancar_pagamento(empresa, conta, dia, valor, *, historico, **kwargs):
    return _lancar(empresa, conta, dia, valor, historico=historico, **kwargs)


def _url_tela(empresa):
    return reverse("livro_caixa_web:arquivos_carne_leao", args=[empresa.id])


def _url_download(nome_da_rota, empresa):
    return reverse(f"livro_caixa_web:{nome_da_rota}", args=[empresa.id])


_PERIODO_MARCO = {"inicio": "2026-03-01", "fim": "2026-03-31"}


# ---------------------------------------------------------------------------
# Tela de arquivos — sucesso com conferência.
# ---------------------------------------------------------------------------


def test_tela_de_arquivos_mostra_conferencia_e_os_dois_downloads(client, cenario):
    usuario = _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="Aluguel de março",
    )
    _lancar_pagamento(
        empresa, cenario["conta_plano"], date(2026, 3, 12), "200,00", historico="Água de março"
    )

    resposta = client.get(_url_tela(empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    assert "livro_caixa/arquivos_carne_leao.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()

    # Um único h1 (direção de arte §8.3) e estado de SUCESSO.
    assert conteudo.count("<h1") == 1
    assert _url_download("arquivo_rendimentos", empresa) in conteudo
    assert _url_download("arquivo_pagamentos", empresa) in conteudo

    # A conferência mostra o que o SERVIÇO devolveu — nada é calculado aqui.
    assert "1.000,00" in conteudo
    assert "200,00" in conteudo
    assert "R01.003.001" in conteudo
    assert "P10.01.00001" in conteudo
    assert conteudo.count("Diferença (Livro Caixa menos arquivo)") == 2
    assert "Diferença zero: o arquivo de rendimentos bate com as entradas" in conteudo
    assert "Diferença zero: o arquivo de pagamentos bate com as saídas" in conteudo

    conferencia = resposta.context["conferencia"]
    assert conferencia["linhas_rendimentos"] == 1
    assert conferencia["linhas_pagamentos"] == 1
    assert conferencia["total_rendimentos_ptbr"] == "1.000,00"
    assert conferencia["total_pagamentos_ptbr"] == "200,00"
    assert conferencia["diferenca_rendimentos_ptbr"] == "0,00"
    assert conferencia["diferenca_pagamentos_ptbr"] == "0,00"
    assert usuario.is_authenticated  # só para deixar explícito quem gerou


def test_conferencia_expoe_as_diferencas_sempre_com_texto_nao_so_cor(client, cenario):
    """Lançamento de conta SEM código do Carnê-Leão Web fica fora do arquivo
    e continua no Livro Caixa — a diferença fica exposta (valor + texto),
    nunca escondida (critério 5 do plano; direção de arte §4.3)."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="Aluguel de março",
    )
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_sem_codigo"],
        date(2026, 3, 11),
        "300,00",
        historico="Receita legada sem código",
    )

    resposta = client.get(_url_tela(empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Diferença diferente de zero" in conteudo
    assert "fora do arquivo e continua no Livro" in conteudo
    conferencia = resposta.context["conferencia"]
    assert conferencia["diferenca_rendimentos_ptbr"] == "300,00"
    assert not conferencia["diferenca_rendimentos_zerada"]
    assert conferencia["lancamentos_excluidos_sem_codigo"] == 1


def test_tela_de_arquivos_em_periodo_vazio_mostra_estado_vazio_sem_downloads(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    resposta = client.get(_url_tela(empresa), {"inicio": "2026-04-01", "fim": "2026-04-30"})
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "estado-vazio" in conteudo
    assert "Nenhum lançamento neste período." in conteudo
    # Nada a exportar: os downloads somem junto com o movimento.
    assert resposta.context["pode_baixar"] is False
    assert _url_download("arquivo_rendimentos", empresa) not in conteudo
    assert _url_download("arquivo_pagamentos", empresa) not in conteudo


# ---------------------------------------------------------------------------
# Tela de arquivos — estado de pendência: lista TODA e nenhum download.
# ---------------------------------------------------------------------------


def test_pendencias_listam_todas_e_os_downloads_somem(client, cenario):
    """Quatro pendências de quatro naturezas DIFERENTES, cada uma em um
    lançamento (o serviço aponta uma pendência por lançamento): ocupação
    ausente, histórico acima de 255, competência da previdência ausente e
    código de rendimento fora das tabelas. A lista sai COMPLETA — nada é
    truncado — e nenhum botão de download aparece (nunca arquivo parcial)."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]

    sem_ocupacao = _lancar(
        empresa,
        cenario["conta_trabalho"],
        date(2026, 3, 5),
        "900,00",
        historico="Recibo de serviço - sem ocupação",
        recebido_de="PJ",
        cnpj_pagador="11222333000181",
    )
    historico_longo = _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="A" * 260,
    )
    previdencia = _lancar_pagamento(
        empresa,
        cenario["conta_previdencia"],
        date(2026, 3, 12),
        "350,00",
        historico="Contribuição previdenciária",
        competencia_previdencia=date(2026, 3, 1),
    )
    # A competência obrigatória é validada no SERVIÇO; para a tela de
    # pendência precisar deste caso, a linha é corrompida por ORM direto
    # (mesmo padrão da suíte do serviço). Desde a DL-069 o banco recusa UPDATE em
    # lançamento de caixa; o propósito do teste é a tela de PENDÊNCIAS, não a
    # imutabilidade — só a MONTAGEM do dado desliga o gatilho (a asserção não muda).
    with gatilho_desligado(IMUTAVEL_LANCAMENTO_CAIXA):
        LancamentoCaixa.objects.filter(pk=previdencia.pk).update(competencia_previdencia=None)
    fora_da_tabela = _lancar_receita_aluguel(
        empresa,
        cenario["conta_fora_da_tabela"],
        date(2026, 3, 15),
        "500,00",
        historico="Rendimento com código desconhecido",
    )

    resposta = client.get(_url_tela(empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    pendencias = resposta.context["pendencias"]
    assert len(pendencias) == 4

    # TODAS listadas, cada uma com o lançamento que a originou.
    for esperado in (
        (sem_ocupacao.id, "Código de ocupação", "código de ocupação ausente"),
        (historico_longo.id, "Histórico", "255"),
        (previdencia.id, "Competência da previdência oficial", "competência ausente"),
        (fora_da_tabela.id, "Código do Carnê-Leão Web da conta", "fora das tabelas"),
    ):
        lancamento_id, campo, motivo = esperado
        assert f"nº {lancamento_id}" in conteudo, esperado
        assert campo in conteudo, esperado
        assert motivo in conteudo, esperado

    # Nenhum download, nem o link da faixa de ação nem outro qualquer.
    assert resposta.context["pode_baixar"] is False
    assert _url_download("arquivo_rendimentos", empresa) not in conteudo
    assert _url_download("arquivo_pagamentos", empresa) not in conteudo
    assert "nenhum arquivo foi gerado" in conteudo.lower()


def test_pendencia_lista_o_link_para_os_lancamentos_do_periodo(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    lancamento = _lancar(
        empresa,
        cenario["conta_trabalho"],
        date(2026, 3, 5),
        "900,00",
        historico="Recibo de serviço - sem ocupação",
        recebido_de="PJ",
        cnpj_pagador="11222333000181",
    )
    resposta = client.get(_url_tela(empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    url_lista = reverse("livro_caixa_web:lancamentos", args=[empresa.id])
    assert f"{url_lista}?inicio=2026-03-01&amp;fim=2026-03-31" in conteudo
    assert f"nº {lancamento.id}" in conteudo


# ---------------------------------------------------------------------------
# Erro: período inválido (querystring malformada e fora do ano-calendário).
# ---------------------------------------------------------------------------


def test_periodo_malformado_retorna_400_com_saida_navegavel(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    resposta = client.get(_url_tela(empresa), {"inicio": "abacaxi", "fim": "2026-03-31"})
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "não pôde ser usado" in conteudo
    assert _url_tela(empresa) in conteudo


def test_periodo_fora_do_unico_ano_calendario_retorna_400(client, cenario):
    """A recusa vem do SERVIÇO (início e fim em anos diferentes) — a tela
    só repassa a mensagem, nunca um segundo critério."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    resposta = client.get(_url_tela(empresa), {"inicio": "2025-12-01", "fim": "2026-01-31"})
    assert resposta.status_code == 400
    assert "ano-calendário" in resposta.content.decode()


# ---------------------------------------------------------------------------
# Downloads — bytes iguais aos do serviço, cabeçalho certo, nome neutro.
# ---------------------------------------------------------------------------


def test_download_de_rendimentos_devolve_os_bytes_do_servico_com_o_header_certo(client, cenario):
    usuario = _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="Aluguel de março",
    )
    _lancar_pagamento(
        empresa, cenario["conta_plano"], date(2026, 3, 12), "200,00", historico="Água de março"
    )

    rendimentos_esperados, _pagamentos, _conferencia = gerar_arquivos_carne_leao(
        empresa=empresa,
        inicio=date(2026, 3, 1),
        fim=date(2026, 3, 31),
        usuario=usuario,
        request=None,
    )
    resposta = client.get(_url_download("arquivo_rendimentos", empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "text/csv; charset=ISO-8859-1"
    assert resposta["Content-Disposition"] == (
        'attachment; filename="carne-leao-rendimentos-2026-03-a-2026-03.csv"'
    )
    assert resposta.content == rendimentos_esperados
    assert b"Aluguel de mar" in resposta.content  # a linha do período, com acento latin-1


def test_download_de_pagamentos_devolve_os_bytes_do_servico_com_o_header_certo(client, cenario):
    usuario = _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="Aluguel de março",
    )
    _lancar_pagamento(
        empresa, cenario["conta_plano"], date(2026, 3, 12), "200,00", historico="Água de março"
    )

    _rendimentos, pagamentos_esperados, _conferencia = gerar_arquivos_carne_leao(
        empresa=empresa,
        inicio=date(2026, 3, 1),
        fim=date(2026, 3, 31),
        usuario=usuario,
        request=None,
    )
    resposta = client.get(_url_download("arquivo_pagamentos", empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "text/csv; charset=ISO-8859-1"
    assert resposta["Content-Disposition"] == (
        'attachment; filename="carne-leao-pagamentos-2026-03-a-2026-03.csv"'
    )
    assert resposta.content == pagamentos_esperados


def test_nome_do_arquivo_nunca_carrega_cpf_nem_cnpj(client, cenario):
    """O anexo pode parar em pasta de download compartilhada — o nome é
    NEUTRO (tipo de arquivo + período), como nos downloads do Fiscal."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="Aluguel de março",
    )
    for nome_da_rota in ("arquivo_rendimentos", "arquivo_pagamentos"):
        resposta = client.get(_url_download(nome_da_rota, empresa), _PERIODO_MARCO)
        assert resposta.status_code == 200, nome_da_rota
        disposicao = resposta["Content-Disposition"]
        assert CPF_CLIENTE_A not in disposicao, nome_da_rota
        assert re.fullmatch(
            r'attachment; filename="carne-leao-(rendimentos|pagamentos)-'
            r'\d{4}-\d{2}-a-\d{4}-\d{2}\.csv"',
            disposicao,
        ), nome_da_rota


def test_download_com_pendencia_redireciona_sem_entregar_arquivo(client, cenario):
    """Nunca arquivo parcial: com pendência, a resposta é mensagem + redirect
    de volta para a tela de arquivos, que lista o que falta."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar(
        empresa,
        cenario["conta_trabalho"],
        date(2026, 3, 5),
        "900,00",
        historico="Recibo de serviço - sem ocupação",
        recebido_de="PJ",
        cnpj_pagador="11222333000181",
    )
    for nome_da_rota in ("arquivo_rendimentos", "arquivo_pagamentos"):
        resposta = client.get(_url_download(nome_da_rota, empresa), _PERIODO_MARCO)
        assert resposta.status_code == 302, nome_da_rota
        assert "Content-Disposition" not in resposta, nome_da_rota
        assert resposta.url.startswith(_url_tela(empresa)), nome_da_rota
        assert "inicio=2026-03-01" in resposta.url, nome_da_rota

        seguida = client.get(resposta.url)
        assert seguida.status_code == 200
        assert "código de ocupação ausente" in seguida.content.decode()


def test_download_com_periodo_malformado_redireciona_sem_500(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    for nome_da_rota in ("arquivo_rendimentos", "arquivo_pagamentos"):
        resposta = client.get(
            f"{_url_download(nome_da_rota, empresa)}?inicio=abacaxi&fim=2026-03-31"
        )
        assert resposta.status_code == 302, nome_da_rota
        assert "Content-Disposition" not in resposta, nome_da_rota


# ---------------------------------------------------------------------------
# Isolamento e permissão — mesma ordem de checagem das outras telas.
# ---------------------------------------------------------------------------


def test_isolamento_entre_empresas_do_mesmo_escritorio(client, cenario):
    """A tela e os downloads de uma empresa nunca trazem movimento de OUTRA
    empresa do MESMO escritório (isolamento por empresa, não só por
    escritório — o serviço filtra por `empresa`, e a tela não soma nada)."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    empresa_a2 = cenario["empresa_a2"]
    _lancar_receita_aluguel(
        empresa, cenario["conta_aluguel"], date(2026, 3, 10), "1.000,00", historico="Aluguel da A"
    )
    _lancar_receita_aluguel(
        empresa_a2,
        cenario["conta_aluguel_a2"],
        date(2026, 3, 10),
        "7.777,00",
        historico="HISTORICO-QUE-NAO-PODE-VAZAR",
    )

    resposta = client.get(_url_tela(empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "HISTORICO-QUE-NAO-PODE-VAZAR" not in conteudo
    assert "7.777,00" not in conteudo
    conferencia = resposta.context["conferencia"]
    assert conferencia["total_rendimentos_ptbr"] == "1.000,00"

    for nome_da_rota in ("arquivo_rendimentos", "arquivo_pagamentos"):
        baixado = client.get(_url_download(nome_da_rota, empresa), _PERIODO_MARCO)
        assert baixado.status_code == 200, nome_da_rota
        assert b"HISTORICO-QUE-NAO-PODE-VAZAR" not in baixado.content, nome_da_rota


def test_empresa_de_outro_escritorio_da_404_nos_tres_enderecos(client, cenario):
    _autenticar(client, cenario["escritorio_b"], username="gestor-outro-arq")
    empresa = cenario["empresa_a"]
    urls = [
        _url_tela(empresa),
        _url_download("arquivo_rendimentos", empresa),
        _url_download("arquivo_pagamentos", empresa),
    ]
    for url in urls:
        resposta = client.get(url, _PERIODO_MARCO)
        assert resposta.status_code == 404, url
        assert empresa.razao_social not in resposta.content.decode(), url


def test_papel_cliente_recebe_403_nos_tres_enderecos(client, cenario):
    _autenticar(client, cenario["escritorio_a"], papel=Papel.CLIENTE, username="cliente-arq")
    empresa = cenario["empresa_a"]
    urls = [
        _url_tela(empresa),
        _url_download("arquivo_rendimentos", empresa),
        _url_download("arquivo_pagamentos", empresa),
    ]
    for url in urls:
        resposta = client.get(url, _PERIODO_MARCO)
        assert resposta.status_code == 403, url
        assert "erros/sem_permissao.html" in [t.name for t in resposta.templates], url
        assert empresa.razao_social not in resposta.content.decode(), url


def test_empresa_em_modo_contabilidade_e_recusada_nos_tres_enderecos(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_contabilidade"]
    urls = [
        _url_tela(empresa),
        _url_download("arquivo_rendimentos", empresa),
        _url_download("arquivo_pagamentos", empresa),
    ]
    for url in urls:
        resposta = client.get(url, _PERIODO_MARCO)
        assert resposta.status_code == 403, url
        assert "contabilidade" in resposta.content.decode().lower(), url


# ---------------------------------------------------------------------------
# Nunca 500 — querystring malformada nos três endereços.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "querystring",
    [
        "inicio=abacaxi&fim=2026-03-31",
        "inicio=2026-03-01&fim=",
        "inicio=&fim=2026-03-31",
        "inicio=2026-02-30&fim=2026-03-31",
        "inicio=2026-03-31&fim=2026-03-01",
        "inicio=2025-12-01&fim=2026-01-31",
        "inicio=1&fim=2",
        "inicio[]=2026-03-01&fim=2026-03-31",
        "inicio=2026-03-01",
    ],
)
def test_nunca_500_com_querystring_malformada(client, cenario, querystring):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    for nome_da_rota in ("arquivos_carne_leao", "arquivo_rendimentos", "arquivo_pagamentos"):
        resposta = client.get(f"{_url_download(nome_da_rota, empresa)}?{querystring}")
        assert resposta.status_code in (200, 302, 400), (
            nome_da_rota,
            querystring,
            resposta.status_code,
        )


# ---------------------------------------------------------------------------
# Nenhum identificador interno nem jargão técnico no texto visível (DE-092).
# As mensagens de pendência nascem no SERVIÇO e duas delas trazem a
# referência interna entre parênteses — a view normaliza só esse parêntese
# (ver `_motivo_de_pendencia_para_tela`), e estes testes são a prova de que
# nada chega à tela.
# ---------------------------------------------------------------------------

_REGEX_IDENTIFICADOR_INTERNO = re.compile(r"\b(RC|HI|DE|PE|BL|DL)-\d+")


def _sem_identificador_interno_nem_patch(html):
    achado = _REGEX_IDENTIFICADOR_INTERNO.search(html)
    assert achado is None, f"identificador interno no texto visível: {achado.group()!r}"
    assert "PATCH" not in html


def test_sem_identificador_interno_no_estado_de_sucesso(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="Aluguel de março",
    )
    resposta = client.get(_url_tela(empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    _sem_identificador_interno_nem_patch(resposta.content.decode())


def test_sem_identificador_interno_nas_pendencias_inclusive_as_do_servico(client, cenario):
    """As duas pendências cujo motivo do SERVIÇO cita a referência interna
    (histórico fora de ISO-8859-1 e código de rendimento fora das tabelas)
    são exatamente as que provam a normalização."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_aluguel"],
        date(2026, 3, 10),
        "1.000,00",
        historico="Caractere fora de latin-1: \u2603",
    )
    _lancar_receita_aluguel(
        empresa,
        cenario["conta_fora_da_tabela"],
        date(2026, 3, 15),
        "500,00",
        historico="Rendimento com código desconhecido",
    )
    resposta = client.get(_url_tela(empresa), _PERIODO_MARCO)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "ISO-8859-1" in conteudo  # o motivo continua integral
    assert "fora das tabelas confirmadas" in conteudo
    _sem_identificador_interno_nem_patch(conteudo)


# ---------------------------------------------------------------------------
# Formulário de lançamento de caixa — os quatro campos novos (RC-127/RC-135).
# O bloqueio que isto resolve: `P20.01.00001` exige `competencia_previdencia`
# no servidor e a tela não enviava o campo — o pagamento de previdência
# oficial não podia ser lançado pela tela.
# ---------------------------------------------------------------------------


def test_formulario_de_lancamento_oferece_os_quatro_campos_novos(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    resposta = client.get(reverse("livro_caixa_web:lancamento_novo", args=[empresa.id]))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    for nome in ("valor_irrf", "competencia_previdencia", "multa_previdencia", "juros_previdencia"):
        assert f'name="{nome}"' in conteudo, nome
        assert f'<label for="id_{nome}">' in conteudo, nome
        assert f'aria-describedby="id_{nome}_ajuda"' in conteudo, nome
    assert 'type="date" id="id_competencia_previdencia"' in conteudo
    # DE-092: os textos de apoio novos também não podem carregar
    # identificador interno do projeto no texto visível.
    _sem_identificador_interno_nem_patch(conteudo)


def test_pagamento_de_previdencia_oficial_pela_tela_grava_com_competencia(client, cenario):
    """REGRESSÃO do bloqueio funcional: lançar previdência oficial pela tela,
    com competência, multa e juros — antes desta fatia o POST era recusado
    porque o campo de competência não existia no formulário."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-12",
            "conta": str(cenario["conta_previdencia"].id),
            "valor": "350,00",
            "historico": "Contribuição previdenciária de março",
            "documento_origem": "",
            "recebido_de": "",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "competencia_previdencia": "2026-03-01",
            "multa_previdencia": "12,34",
            "juros_previdencia": "5,67",
            "chave_idempotencia": "teste-arquivos-prev-1",
        },
    )
    assert resposta.status_code == 302
    lancamento = LancamentoCaixa.objects.get(empresa=empresa)
    assert lancamento.competencia_previdencia == date(2026, 3, 1)
    assert lancamento.multa_previdencia == Decimal("12.34")
    assert lancamento.juros_previdencia == Decimal("5.67")


def test_previdencia_oficial_sem_competencia_e_recusada_e_preserva_o_digitado(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-12",
            "conta": str(cenario["conta_previdencia"].id),
            "valor": "350,00",
            "historico": "Contribuição previdenciária de março",
            "documento_origem": "",
            "recebido_de": "",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "competencia_previdencia": "",
            "multa_previdencia": "12,34",
            "juros_previdencia": "5,67",
            "chave_idempotencia": "teste-arquivos-prev-2",
        },
    )
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "exige a competência" in conteudo
    # O formulário não some com o erro: o que foi digitado continua lá.
    assert 'value="350,00"' in conteudo
    assert 'value="12,34"' in conteudo
    assert 'value="5,67"' in conteudo
    assert not LancamentoCaixa.objects.filter(empresa=empresa).exists()


def test_competencia_de_previdencia_fora_do_dia_um_e_recusada(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-12",
            "conta": str(cenario["conta_previdencia"].id),
            "valor": "350,00",
            "historico": "Contribuição previdenciária de março",
            "documento_origem": "",
            "recebido_de": "",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "competencia_previdencia": "2026-03-15",
            "chave_idempotencia": "teste-arquivos-prev-3",
        },
    )
    assert resposta.status_code == 400
    assert not LancamentoCaixa.objects.filter(empresa=empresa).exists()


def test_valor_irrf_e_aceito_na_receita_de_pj_de_trabalho_nao_assalariado(client, cenario):
    """O leiaute oficial só tem coluna de indicador/valor de IRRF nas linhas
    de trabalho não assalariado e de serviços notariais — por isso o caso
    ACEITO usa a conta de trabalho. O caso recusado (aluguel, cuja linha tem
    7 campos e não tem a coluna) está logo abaixo; antes da correção da
    rodada 1 da auditoria este teste usava a conta de ALUGUEL e cementava o
    defeito: o valor era gravado e depois sumia do arquivo em silêncio."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-10",
            "conta": str(cenario["conta_trabalho"].id),
            "valor": "1.000,00",
            "historico": "Honorário recebido de PJ com retenção",
            "documento_origem": "",
            "recebido_de": "PJ",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "11222333000181",
            "valor_irrf": "150,75",
            "chave_idempotencia": "teste-arquivos-irrf-1",
        },
    )
    assert resposta.status_code == 302
    lancamento = LancamentoCaixa.objects.get(empresa=empresa)
    assert lancamento.valor_irrf == Decimal("150.75")


def test_valor_irrf_e_recusado_no_modelo_de_aluguel_que_nao_tem_a_coluna(client, cenario):
    """Achado 1 da rodada 1 da auditoria (nível 1): a linha de aluguel e
    outros rendimentos tem 7 campos e NÃO tem coluna de IRRF nos
    arquivos-modelo oficiais. Antes desta correção o valor era aceito,
    gravado e depois **omitido do CSV** sem pendência nem aviso — dado que o
    contador informou sumindo do arquivo que vai à Receita. O campo agora é
    recusado no lançamento (mesmo padrão do `cnpj_pagador` do mesmo modelo),
    com o digitado preservado na tela."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-10",
            "conta": str(cenario["conta_aluguel"].id),
            "valor": "1.000,00",
            "historico": "Aluguel recebido de PJ com retenção",
            "documento_origem": "",
            "recebido_de": "PJ",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "valor_irrf": "150,75",
            "chave_idempotencia": "teste-arquivos-irrf-aluguel",
        },
    )
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "não tem coluna de IRRF" in conteudo
    assert 'value="150,75"' in conteudo
    assert not LancamentoCaixa.objects.filter(empresa=empresa).exists()


def test_valor_irrf_e_recusado_na_receita_de_pf_com_o_valor_preservado(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    url = reverse("livro_caixa_web:lancamento_novo", args=[empresa.id])
    resposta = client.post(
        url,
        {
            "data": "2026-03-10",
            "conta": str(cenario["conta_aluguel"].id),
            "valor": "1.000,00",
            "historico": "Aluguel recebido de PF",
            "documento_origem": "",
            "recebido_de": "PF",
            "cpf_titular_pagamento": "",
            "cpf_beneficiario_servico": "",
            "cnpj_pagador": "",
            "valor_irrf": "150,75",
            "chave_idempotencia": "teste-arquivos-irrf-2",
        },
    )
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "IRRF retido" in conteudo
    assert 'value="150,75"' in conteudo
    assert not LancamentoCaixa.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Achado 4 da rodada 1 da auditoria — período sem movimento não é download
# ---------------------------------------------------------------------------


def test_download_de_periodo_sem_movimento_nao_devolve_csv_vazio_com_200(client, cenario):
    """A TELA esconde os botões quando não há o que exportar, mas o endereço
    de download devolvia um CSV vazio com 200 — sucesso aparente
    contradizendo a tela. A MESMA regra de estado vazio vale agora nos dois
    downloads (e na API), decidida pela mesma função
    (`conferencia_sem_movimento`) nos três lugares."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    abril = {"inicio": "2026-04-01", "fim": "2026-04-30"}

    resposta = client.get(_url_download("arquivo_rendimentos", empresa), abril)

    # Nenhum CSV: a resposta é o redirect de volta para a tela, sem
    # `Content-Disposition` nem corpo de anexo.
    assert resposta.status_code == 302, resposta.content
    assert "Content-Disposition" not in resposta
    assert _url_tela(empresa) in resposta["Location"]
    assert not LancamentoCaixa.objects.filter(empresa=empresa).exists()


def test_download_de_periodo_com_movimento_continua_servindo_o_csv(client, cenario):
    """Controle: a regra nova não pode ter derrubado o caso normal."""
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _lancar_receita_aluguel(
        empresa, cenario["conta_aluguel"], date(2026, 3, 10), "1.000,00", historico="Aluguel"
    )

    resposta = client.get(_url_download("arquivo_rendimentos", empresa), _PERIODO_MARCO)

    assert resposta.status_code == 200, resposta.content
    assert "attachment" in resposta["Content-Disposition"]
