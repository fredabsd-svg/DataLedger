"""DL-091 (frente A2): regras da DL-087 para ENTRADAS (compra).

Cobre: o tipo `entrada` aceito e `devolucao_compra` recusado; CRT e UF do emitente e CFOP de entrada
só na regra de entrada; a conferência do CFOP fixado; combustível de entrada com NCM; os pesos
publicados sem empate e com a mesma ORDEM dos antigos; a sugestão de entrada por regra, que nunca
muda a de saída; o CFOP de entrada sugerido; o CHECK e o gatilho do banco; a trilha; a fila e a API.

Dados sintéticos (CNPJs de `xml_nfe_dl080`). Plano: docs/planos/DL-091-nfe-de-entrada.md, A2.
"""

import itertools
import json
from datetime import date
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import classificacao as cl
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import (
    NaturezaOperacaoNFe as N,
)
from apps.fiscal.models import (
    RegraClassificacaoNFe,
    TipoEscrituracaoNFe,
)
from apps.fiscal.tests.test_dl091_entradas import _nota, _saida_finnfe_4
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

ENTRADA = TipoEscrituracaoNFe.ENTRADA
SAIDA = TipoEscrituracaoNFe.SAIDA_PROPRIA


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Compradora A2 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _dados(**campos) -> cl.DadosDaRegra:
    base = {
        "tipo": ENTRADA,
        "cfop": "5102",
        "natureza": N.ENTRADA_COMERCIALIZACAO,
        "vigencia_inicio": date(2026, 1, 1),
    }
    base.update(campos)
    return cl.DadosDaRegra(**base)


def _regra(escritorio, usuario, empresa=None, **campos) -> RegraClassificacaoNFe:
    return cl.criar_regra(
        escritorio=escritorio, empresa=empresa, dados=_dados(**campos), usuario=usuario
    )


def _contexto(empresa, *regras):
    return cl.ContextoDeClassificacao(
        escritorio_id=empresa.escritorio_id,
        empresa_id=empresa.pk,
        padrao_combustivel="",
        regras=tuple(regras),
    )


def _compra(escritorio, usuario, empresa, numero, **campos):
    """Compra: a empresa é a destinatária (tpNF 1 do fornecedor, finNFe 1)."""
    return _nota(escritorio, usuario, empresa, numero=numero, **campos)


def _saida(escritorio, usuario, empresa, numero, cfop="5102", ncm="22030000"):
    """Saída própria: a empresa emite, tpNF 1 e finNFe 1."""
    return _nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        cfop=cfop,
        ncm=ncm,
        tp_nf="1",
        fin_nfe="1",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )


def _sugestao_de_entrada(contexto, documento):
    item = documento.itens.get(n_item=1)
    return cl.sugerir_natureza_com_regras(contexto, documento, item, ENTRADA)


# ---------------------------------------------------------------------------
# Tipo e critérios (validação, antes do banco)
# ---------------------------------------------------------------------------


def test_tipo_entrada_e_aceito_e_devolucao_de_compra_e_recusada_com_o_motivo_do_contrato():
    assert cl.validar_dados_da_regra(_dados()).tipo == ENTRADA
    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        cl.validar_dados_da_regra(_dados(tipo=TipoEscrituracaoNFe.DEVOLUCAO_COMPRA))
    assert "A1" in erro.value.mensagem


def test_crt_uf_e_cfop_de_entrada_so_valem_na_regra_de_entrada():
    for campos in (
        {"crt_emitente": "1"},
        {"uf_emitente": "TO"},
        {"cfop_entrada": "1102"},
    ):
        with pytest.raises(servico.EntradaInvalidaNFe):
            cl.validar_dados_da_regra(_dados(tipo=SAIDA, natureza=N.REVENDA, **campos))


def test_crt_fora_de_1_a_4_e_uf_inexistente_sao_recusados_e_uf_minuscula_e_normalizada():
    with pytest.raises(servico.EntradaInvalidaNFe):
        cl.validar_dados_da_regra(_dados(crt_emitente="5"))
    with pytest.raises(servico.EntradaInvalidaNFe):
        cl.validar_dados_da_regra(_dados(uf_emitente="XX"))
    assert cl.validar_dados_da_regra(_dados(uf_emitente="to")).uf_emitente == "TO"


def test_cfop_de_entrada_fixado_e_conferido_contra_o_criterio_e_a_natureza():
    # 5102 pede primeiro dígito 1 (5→1): 2102 é recusado.
    with pytest.raises(servico.EntradaInvalidaNFe):
        cl.validar_dados_da_regra(_dados(cfop_entrada="2102"))
    # 1556 é grupo de uso e consumo: não cabe na natureza de comercialização.
    with pytest.raises(servico.EntradaInvalidaNFe):
        cl.validar_dados_da_regra(_dados(cfop_entrada="1556"))
    # Fora da tabela oficial: recusado.
    with pytest.raises(servico.EntradaInvalidaNFe):
        cl.validar_dados_da_regra(_dados(cfop_entrada="1999"))
    assert cl.validar_dados_da_regra(_dados(cfop_entrada="1.102")).cfop_entrada == "1102"


def test_combustivel_de_entrada_exige_ncm_como_a_venda():
    for natureza in (N.ENTRADA_COMBUSTIVEL_REVENDA, N.ENTRADA_COMBUSTIVEL_CONSUMO):
        with pytest.raises(servico.EntradaInvalidaNFe) as erro:
            cl.validar_dados_da_regra(_dados(cfop="5656", natureza=natureza, ncm=""))
        assert "exige NCM" in erro.value.mensagem
    aceita = cl.validar_dados_da_regra(
        _dados(
            cfop="5656",
            natureza=N.ENTRADA_COMBUSTIVEL_CONSUMO,
            ncm="27101259",
            ncm_modo="exato",
        )
    )
    assert aceita.ncm == "27101259"


def test_regra_de_entrada_so_leva_natureza_de_entrada_e_saida_nao_leva():
    with pytest.raises(servico.EntradaInvalidaNFe):
        cl.validar_dados_da_regra(_dados(natureza=N.REVENDA))
    with pytest.raises(servico.EntradaInvalidaNFe):
        cl.validar_dados_da_regra(_dados(tipo=SAIDA, natureza=N.ENTRADA_COMERCIALIZACAO))


# ---------------------------------------------------------------------------
# Pesos: publicados, sem empate entre conjuntos distintos, e a mesma ORDEM dos antigos
# ---------------------------------------------------------------------------

_PESOS_ANTIGOS = {
    "cfop": 16,
    "ncm_exato": 8,
    "ncm_prefixo": 4,
    "cst_csosn": 2,
    "id_dest": 1,
}
_CRITERIOS_OPCIONAIS = (
    "ncm_exato",
    "ncm_prefixo",
    "cst_csosn",
    "id_dest",
    "uf_emitente",
    "crt_emitente",
)


def _conjuntos_validos():
    """Todos os conjuntos de critérios opcionais. NCM exato e por prefixo não coexistem (uma regra
    tem um modo de NCM)."""
    for k in range(len(_CRITERIOS_OPCIONAIS) + 1):
        for combo in itertools.combinations(_CRITERIOS_OPCIONAIS, k):
            if "ncm_exato" in combo and "ncm_prefixo" in combo:
                continue
            yield frozenset(combo)


def _soma(pesos, conjunto):
    return cl.PESO_CFOP + sum(pesos[c] for c in conjunto)


def test_pesos_publicados_sao_os_antigos_vezes_quatro_e_os_de_fornecedor_os_menores():
    assert cl.PESOS_DE_ESPECIFICIDADE == {
        "cfop": 64,
        "ncm_exato": 32,
        "ncm_prefixo": 16,
        "cst_csosn": 8,
        "id_dest": 4,
        "uf_emitente": 2,
        "crt_emitente": 1,
    }
    assert all(
        v == 4 * _PESOS_ANTIGOS[k]
        for k, v in cl.PESOS_DE_ESPECIFICIDADE.items()
        if k in _PESOS_ANTIGOS
    )


def test_nenhum_conjunto_distinto_de_criterios_empata():
    pesos = cl.PESOS_DE_ESPECIFICIDADE
    somas = {}
    for conjunto in _conjuntos_validos():
        soma = _soma(pesos, conjunto)
        assert soma not in somas, f"empate: {sorted(conjunto)} e {sorted(somas[soma])}"
        somas[soma] = conjunto


def test_a_ordem_entre_os_criterios_antigos_nao_mudou_com_a_escala_e_os_novos_nao_a_alteram():
    """Para dois conjuntos só com critérios ANTIGOS, a comparação dá o mesmo resultado com os pesos
    antigos e com os novos. Os critérios de fornecedor, que não existiam, entram como os menores."""
    antigos = [
        frozenset(c) for c in _conjuntos_validos() if not ({"uf_emitente", "crt_emitente"} & set(c))
    ]
    for a, b in itertools.permutations(antigos, 2):
        velho_a = 16 + sum(_PESOS_ANTIGOS[x] for x in a)
        velho_b = 16 + sum(_PESOS_ANTIGOS[x] for x in b)
        assert (velho_a < velho_b) == (
            _soma(cl.PESOS_DE_ESPECIFICIDADE, a) < _soma(cl.PESOS_DE_ESPECIFICIDADE, b)
        )


def test_especificidade_da_regra_usa_os_pesos_publicados_inclusive_crt_e_uf():
    regra = SimpleNamespace(
        cfop="5102",
        ncm="",
        ncm_modo="",
        cst_csosn="",
        id_dest="",
        crt_emitente="1",
        uf_emitente="TO",
    )
    assert cl.especificidade(regra) == 64 + 2 + 1


# ---------------------------------------------------------------------------
# Sugestão de entrada por regra
# ---------------------------------------------------------------------------


def test_crt_da_regra_de_entrada_muda_a_sugestao_da_compra_e_so_dela(
    escritorio_a, usuario_gestor_a, empresa
):
    _regra(escritorio_a, usuario_gestor_a, crt_emitente="1", natureza=N.ENTRADA_INDUSTRIALIZACAO)
    contexto = cl.contexto_da_empresa(empresa)
    compra_simples = _compra(escritorio_a, usuario_gestor_a, empresa, "101", crt="1")
    compra_normal = _compra(escritorio_a, usuario_gestor_a, empresa, "102", crt="3")

    assert _sugestao_de_entrada(contexto, compra_simples).natureza == N.ENTRADA_INDUSTRIALIZACAO
    assert _sugestao_de_entrada(contexto, compra_normal).natureza == N.ENTRADA_COMERCIALIZACAO


def test_regra_de_entrada_nunca_muda_a_sugestao_de_saida(escritorio_a, usuario_gestor_a, empresa):
    """A saída com CFOP 5102 tem a sugestão da casa (revenda). Regras de entrada com os critérios
    do fornecedor, que casariam com QUALQUER nota de mesmo CFOP, não a mudam."""
    saida = _saida(escritorio_a, usuario_gestor_a, empresa, "201")
    item = saida.itens.get(n_item=1)
    base = cl.sugerir_natureza_com_regras(_contexto(empresa), saida, item, SAIDA)
    _regra(escritorio_a, usuario_gestor_a, crt_emitente="1", natureza=N.ENTRADA_INDUSTRIALIZACAO)
    _regra(escritorio_a, usuario_gestor_a, uf_emitente="SP", natureza=N.ENTRADA_ST)
    depois = cl.sugerir_natureza_com_regras(cl.contexto_da_empresa(empresa), saida, item, SAIDA)
    # A sugestão INTEIRA (natureza, motivo, origem), e não só a natureza: se a regra de entrada
    # entrasse no caminho de saída, o motivo mudaria ("não vale: não cabe em saída própria").
    assert depois == base
    assert depois.natureza == N.REVENDA


def test_regra_de_saida_nunca_casa_com_compra(escritorio_a, usuario_gestor_a, empresa):
    cl.criar_regra(
        escritorio=escritorio_a,
        empresa=None,
        dados=cl.DadosDaRegra(
            tipo=SAIDA, cfop="5102", natureza=N.REVENDA, vigencia_inicio=date(2026, 1, 1)
        ),
        usuario=usuario_gestor_a,
    )
    compra = _compra(escritorio_a, usuario_gestor_a, empresa, "301")
    item = compra.itens.get(n_item=1)
    base = cl.sugerir_natureza_com_regras(_contexto(empresa), compra, item, ENTRADA)
    sugestao = _sugestao_de_entrada(cl.contexto_da_empresa(empresa), compra)
    assert sugestao == base
    assert sugestao.natureza == N.ENTRADA_COMERCIALIZACAO


def test_uf_do_emitente_decide_se_a_regra_de_entrada_casa(escritorio_a, usuario_gestor_a, empresa):
    _regra(escritorio_a, usuario_gestor_a, uf_emitente="TO", natureza=N.ENTRADA_INDUSTRIALIZACAO)
    contexto = cl.contexto_da_empresa(empresa)
    do_tocantins = _compra(escritorio_a, usuario_gestor_a, empresa, "401", cuf="17")
    de_sao_paulo = _compra(escritorio_a, usuario_gestor_a, empresa, "402", cuf="35")
    assert _sugestao_de_entrada(contexto, do_tocantins).natureza == N.ENTRADA_INDUSTRIALIZACAO
    assert _sugestao_de_entrada(contexto, de_sao_paulo).natureza == N.ENTRADA_COMERCIALIZACAO


def test_cfop_de_entrada_fixado_pela_regra_aparece_na_sugestao_e_o_da_a1_vale_sem_ele(
    escritorio_a, usuario_gestor_a, empresa
):
    _regra(escritorio_a, usuario_gestor_a, crt_emitente="1", cfop_entrada="1113")
    contexto = cl.contexto_da_empresa(empresa)
    compra = _compra(escritorio_a, usuario_gestor_a, empresa, "501", crt="1")
    item = compra.itens.get(n_item=1)
    sugestao = _sugestao_de_entrada(contexto, compra)
    assert sugestao.natureza == N.ENTRADA_COMERCIALIZACAO
    assert entradas.cfop_de_entrada_para(compra, item, sugestao.natureza, sugestao) == "1113"
    # Sem regra: a conversão da A1 (5.102 de comercialização → 1.102).
    sem_regra = _compra(escritorio_a, usuario_gestor_a, empresa, "502", crt="3")
    item_sem = sem_regra.itens.get(n_item=1)
    sugestao_sem = _sugestao_de_entrada(contexto, sem_regra)
    assert (
        entradas.cfop_de_entrada_para(sem_regra, item_sem, sugestao_sem.natureza, sugestao_sem)
        == "1102"
    )


def test_padrao_de_combustivel_do_posto_nao_vira_natureza_de_saida_na_compra(
    escritorio_a, usuario_gestor_a, empresa
):
    """Posto ou TRR tem padrão de combustível "para consumo" (DL-084), que é de SAÍDA. Na compra
    de combustível sem sinal de CFOP, ele não pode devolver a natureza `combustivel`: a compra fica
    sem sugestão, e o contador escolhe (DL-091, A2)."""
    compra = _compra(escritorio_a, usuario_gestor_a, empresa, "351", cfop="5949", ncm="27101259")
    item = compra.itens.get(n_item=1)
    contexto_do_posto = cl.ContextoDeClassificacao(
        escritorio_id=empresa.escritorio_id,
        empresa_id=empresa.pk,
        padrao_combustivel="posto",
        regras=(),
    )
    sugestao = cl.sugerir_natureza_com_regras(contexto_do_posto, compra, item, ENTRADA)
    assert sugestao.natureza is None


def test_natureza_trocada_pelo_contador_sem_padrao_de_cfop_nao_tem_cfop_sugerido(
    escritorio_a, usuario_gestor_a, empresa
):
    compra = _compra(escritorio_a, usuario_gestor_a, empresa, "601")
    item = compra.itens.get(n_item=1)
    # 5.102 tem grupo de 4 sufixos na natureza de uso e consumo (E4), e a A1 não sugere E4 para ele.
    assert entradas.cfop_de_entrada_para(compra, item, N.ENTRADA_USO_CONSUMO) == ""


def test_regra_do_escritorio_e_a_da_empresa_separadas_por_criterio_nao_empatam(
    escritorio_a, usuario_gestor_a, empresa
):
    """Duas regras com os MESMOS critérios no mesmo escopo e vigências que se cruzam: 409. Com CRT
    diferente, não são duplicata: os critérios são outros."""
    _regra(escritorio_a, usuario_gestor_a, crt_emitente="1")
    _regra(escritorio_a, usuario_gestor_a, crt_emitente="3", natureza=N.ENTRADA_INDUSTRIALIZACAO)
    with pytest.raises(cl.RegraDuplicada):
        _regra(escritorio_a, usuario_gestor_a, crt_emitente="1", natureza=N.ENTRADA_ST)


# ---------------------------------------------------------------------------
# Banco: CHECKs e gatilho (segunda defesa, sem passar pelo serviço)
# ---------------------------------------------------------------------------


def test_banco_recusa_natureza_de_saida_em_regra_de_entrada(escritorio_a, usuario_gestor_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        RegraClassificacaoNFe.objects.create(
            escritorio=escritorio_a,
            tipo=ENTRADA,
            cfop="5102",
            natureza=N.REVENDA,
            vigencia_inicio=date(2026, 1, 1),
            criada_por=usuario_gestor_a,
        )


def test_banco_recusa_criterio_de_entrada_em_regra_de_saida(escritorio_a, usuario_gestor_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        RegraClassificacaoNFe.objects.create(
            escritorio=escritorio_a,
            tipo=SAIDA,
            cfop="5102",
            natureza=N.REVENDA,
            crt_emitente="1",
            vigencia_inicio=date(2026, 1, 1),
            criada_por=usuario_gestor_a,
        )


def test_banco_recusa_crt_fora_do_conjunto_e_uf_inexistente(escritorio_a, usuario_gestor_a):
    for campos in ({"crt_emitente": "9"}, {"uf_emitente": "XX"}):
        with pytest.raises(IntegrityError), transaction.atomic():
            RegraClassificacaoNFe.objects.create(
                escritorio=escritorio_a,
                tipo=ENTRADA,
                cfop="5102",
                natureza=N.ENTRADA_COMERCIALIZACAO,
                vigencia_inicio=date(2026, 1, 1),
                criada_por=usuario_gestor_a,
                **campos,
            )


def test_gatilho_impede_mudar_crt_de_regra_gravada(escritorio_a, usuario_gestor_a):
    regra = RegraClassificacaoNFe.objects.create(
        escritorio=escritorio_a,
        tipo=ENTRADA,
        cfop="5102",
        natureza=N.ENTRADA_COMERCIALIZACAO,
        crt_emitente="1",
        vigencia_inicio=date(2026, 1, 1),
        criada_por=usuario_gestor_a,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RegraClassificacaoNFe.objects.filter(pk=regra.pk).update(crt_emitente="3")


# ---------------------------------------------------------------------------
# Trilha, rótulo e fila
# ---------------------------------------------------------------------------


def test_criacao_de_regra_de_entrada_grava_os_criterios_novos_na_trilha(
    escritorio_a, usuario_gestor_a
):
    regra = _regra(
        escritorio_a,
        usuario_gestor_a,
        crt_emitente="2",
        uf_emitente="TO",
        cfop_entrada="1102",
        natureza=N.ENTRADA_COMERCIALIZACAO,
    )
    registro = RegistroAuditoria.objects.get(
        acao="classificacao_nfe.regra_criada", objeto_id=str(regra.pk)
    )
    assert registro.detalhes["crt_emitente"] == "2"
    assert registro.detalhes["uf_emitente"] == "TO"
    assert registro.detalhes["cfop_entrada"] == "1102"


def test_rotulo_do_tipo_cobre_os_tipos_novos():
    assert "entrada" in cl._rotulo_do_tipo(ENTRADA)
    assert "devolução de compra" in cl._rotulo_do_tipo(TipoEscrituracaoNFe.DEVOLUCAO_COMPRA)
    assert cl._rotulo_do_tipo(SAIDA) == "saída própria"


def test_fila_marca_retorno_em_finnfe_4_como_nao_criavel_e_compra_sem_sinal_como_criavel(
    escritorio_a, usuario_gestor_a, empresa
):
    _saida_finnfe_4(escritorio_a, usuario_gestor_a, empresa, cfop="5920", numero="701")
    _compra(escritorio_a, usuario_gestor_a, empresa, "702", cfop="5949")
    fila = cl.fila_a_classificar(empresa, 2026, 3)
    por_tipo = {g.tipo: g for g in fila.grupos}
    assert por_tipo[TipoEscrituracaoNFe.DEVOLUCAO_COMPRA].criavel is False
    assert (
        "contrato da DL-091, A1"
        in por_tipo[TipoEscrituracaoNFe.DEVOLUCAO_COMPRA].motivo_nao_criavel
    )
    assert por_tipo[ENTRADA].criavel is True
    assert por_tipo[ENTRADA].criterios_da_regra["tipo"] == ENTRADA


# ---------------------------------------------------------------------------
# API: cadastro da regra de entrada (400 nomeado, 403 e 201)
# ---------------------------------------------------------------------------


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _corpo(**campos):
    corpo = {
        "escopo": "escritorio",
        "tipo": ENTRADA,
        "cfop": "5102",
        "natureza": N.ENTRADA_COMERCIALIZACAO,
        "vigencia_inicio": "2026-01-01",
    }
    corpo.update(campos)
    return corpo


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def test_api_cria_regra_de_entrada_com_crt_e_recusa_crt_na_saida(client, usuario_gestor_a, empresa):
    client.force_login(usuario_gestor_a)
    url = _url("nfe_classificacao_regras", empresa.pk)
    criada = _post(client, url, _corpo(crt_emitente="1", uf_emitente="TO"))
    assert criada.status_code == 201, criada.content
    assert criada.json()["regra"]["crt_emitente"] == "1"
    assert criada.json()["regra"]["uf_emitente"] == "TO"
    recusada = _post(
        client, url, _corpo(tipo="saida_propria", natureza=N.REVENDA, crt_emitente="1")
    )
    assert recusada.status_code == 400


def test_api_recusa_devolucao_de_compra_como_tipo_de_regra(client, usuario_gestor_a, empresa):
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client,
        _url("nfe_classificacao_regras", empresa.pk),
        _corpo(tipo=TipoEscrituracaoNFe.DEVOLUCAO_COMPRA, natureza=N.DEVOLUCAO_COMPRA),
    )
    assert resposta.status_code == 400


def test_api_de_regra_de_entrada_nega_a_quem_nao_pode_criar_regra_do_escritorio(
    client, usuario_cliente_a, empresa
):
    client.force_login(usuario_cliente_a)
    assert _post(client, _url("nfe_classificacao_regras", empresa.pk), _corpo()).status_code == 403
