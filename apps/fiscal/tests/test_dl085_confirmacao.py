"""DL-085 (frente A), critério 2 e a confirmação em bloco: assinatura, escolhas, lote, trilha e
isolamento. Valores escritos à mão, em reais. Notas sintéticas (NFC-e, modelo 65), recebidas pela
recepção real (DL-080).
"""

from collections import Counter

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    EstadoLoteEscrituracaoNFe,
    EstadoNotaDoLoteNFe,
    LoteEscrituracaoNFe,
    LoteEscrituracaoNFeNota,
    NaturezaItemNFe,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import (
    CFOP_COMBUSTIVEL,
    CNPJ_SEGUNDA_EMPRESA,
    NCM_COMBUSTIVEL,
    confirmar_tudo,
    nfce,
    previa_lida,
    usuario_gestor,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

# Id da assinatura de combustível da prévia: CFOP | CSOSN | natureza sugerida.
ID_COMBUSTIVEL = f"{CFOP_COMBUSTIVEL}|500|combustivel"


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a)


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _notas_padrao(escritorio, usuario):
    """Três de combustível (100,00, 250,00 e 40,00) e duas de revenda (80,00 e 80,00)."""
    for numero, valor in ((1, "100.00"), (2, "250.00"), (3, "40.00")):
        nfce(escritorio, usuario, numero=numero, valor=valor)
    for numero in (4, 5):
        nfce(escritorio, usuario, numero=numero, valor="80.00", cfop="5102", csosn="102")


def _efetivadas(empresa):
    return EscrituracaoNFe.objects.filter(empresa=empresa, estado=EstadoEscrituracao.EFETIVADA)


def _naturezas_efetivadas(empresa) -> Counter:
    return Counter(
        NaturezaItemNFe.objects.filter(
            escrituracao__empresa=empresa,
            escrituracao__estado=EstadoEscrituracao.EFETIVADA,
        ).values_list("natureza", flat=True)
    )


def _chave_do_grupo(previa, natureza):
    return next(g.chave for g in previa.grupos if g.assinaturas[0].natureza == natureza)


def test_assinatura_desatualizada_recusa_com_409_e_nao_efetiva_nada(escritorio_a, gestor, empresa):
    """Critério 2. A prévia mostrada tinha 5 notas. Entra a 6ª. A confirmação com a assinatura
    antiga recusa, e nenhuma nota é efetivada nem nenhum lote é criado."""
    _notas_padrao(escritorio_a, gestor)
    previa_antiga = previa_lida(empresa, 2026, 3)
    nfce(escritorio_a, gestor, numero=6, valor="10.00")

    with pytest.raises(lote.PreviaDesatualizada) as exc:
        lote.confirmar_lote(empresa, 2026, 3, previa_antiga.assinatura, {}, gestor, limite=10)

    assert "Nada foi efetivado" in exc.value.mensagem
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_confirmacao_efetiva_o_mes_e_conclui_o_lote(escritorio_a, gestor, empresa):
    """As 5 notas viram escrituração efetivada, e o lote fica concluído, com quem confirmou."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)

    progresso = confirmar_tudo(empresa, gestor, 2026, 3, previa, limite=2)

    assert progresso.terminou
    assert progresso.efetivadas_total == 5
    assert progresso.falhas_total == 0
    assert _efetivadas(empresa).count() == 5
    gravado = LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id)
    assert gravado.estado == EstadoLoteEscrituracaoNFe.CONCLUIDO
    assert gravado.concluido_em is not None
    assert gravado.criado_por == gestor
    assert (gravado.quantidade_notas, gravado.quantidade_itens) == (5, 5)
    assert not gravado.notas.filter(estado=EstadoNotaDoLoteNFe.PENDENTE).exists()


def test_escolha_troca_a_natureza_de_todo_o_grupo_pela_assinatura(escritorio_a, gestor, empresa):
    """O grupo de combustível vai para `combustivel_revenda` (8%): 3 notas. O grupo de revenda não
    muda: 2 notas. Os dois grupos têm naturezas diferentes na escrituração, como a escolha manda."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    chave = _chave_do_grupo(previa, "combustivel")

    progresso = confirmar_tudo(
        empresa, gestor, 2026, 3, previa, escolhas={chave: {ID_COMBUSTIVEL: "combustivel_revenda"}}
    )

    assert progresso.efetivadas_total == 5
    assert _naturezas_efetivadas(empresa) == Counter({"combustivel_revenda": 3, "revenda": 2})


def test_escolha_igual_a_sugestao_nao_entra_na_trilha_como_troca(escritorio_a, gestor, empresa):
    """Escolha igual à sugestão não é gravada como troca: a trilha mostra só o que o contador
    mudou."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    chave = _chave_do_grupo(previa, "combustivel")

    progresso = confirmar_tudo(
        empresa, gestor, 2026, 3, previa, escolhas={chave: {ID_COMBUSTIVEL: "combustivel"}}
    )

    gravado = LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id)
    assert gravado.escolhas == {}
    assert _naturezas_efetivadas(empresa) == Counter({"combustivel": 3, "revenda": 2})


@pytest.mark.parametrize(
    "escolhas_fora,mensagem_parcial",
    [
        pytest.param("grupo", "Grupo de escolha desconhecido", id="grupo-que-nao-existe"),
        pytest.param("id", "fora do grupo", id="assinatura-que-nao-existe"),
        pytest.param("tipo", "não cabe neste grupo", id="natureza-de-outro-tipo"),
    ],
)
def test_escolha_invalida_e_recusada_com_entrada_invalida_sem_gravar(
    escritorio_a, gestor, empresa, escolhas_fora, mensagem_parcial
):
    """Escolha que não bate com a prévia ou com o tipo da nota: 400 (EntradaInvalidaNFe), e
    nada gravado. A natureza `ajuste` não cabe numa saída própria."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    chave = _chave_do_grupo(previa, "combustivel")
    escolhas = {
        "grupo": {"saida_propria-0000000000000000": {ID_COMBUSTIVEL: "combustivel_revenda"}},
        "id": {chave: {"5102|102|revenda": "revenda"}},
        "tipo": {chave: {ID_COMBUSTIVEL: "ajuste"}},
    }[escolhas_fora]

    with pytest.raises(servico.EntradaInvalidaNFe) as exc:
        lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, escolhas, gestor)

    assert mensagem_parcial in exc.value.mensagem
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_escolha_que_quebra_a_conferencia_recusa_o_lote_inteiro_antes_de_gravar(
    escritorio_a, gestor, empresa
):
    """Nota de posto: 1 item de 100,00 com frete de 10,00 (vNF 110,00). Trocada para remessa, o
    frete
    fica sem item de receita para ir (HI-138). A confirmação inteira recusa (400), e as outras notas
    também não são efetivadas: nada é gravado com natureza que o servidor já sabe que não fecha."""
    _notas_padrao(escritorio_a, gestor)
    nfce(
        escritorio_a,
        gestor,
        numero=6,
        dets=[
            xml.det(
                1,
                cfop=CFOP_COMBUSTIVEL,
                vprod="100.00",
                vfrete="10.00",
                ncm=NCM_COMBUSTIVEL,
                icms_xml=xml.icms(csosn="102"),
            )
        ],
        vnf="110.00",
        totais={"vProd": "100.00", "vFrete": "10.00"},
    )
    previa = previa_lida(empresa, 2026, 3)
    chave = next(g.chave for g in previa.grupos if g.quantidade_notas == 1)

    with pytest.raises(servico.EntradaInvalidaNFe) as exc:
        lote.confirmar_lote(
            empresa,
            2026,
            3,
            previa.assinatura,
            {chave: {f"{CFOP_COMBUSTIVEL}|102|combustivel": "remessa_retorno"}},
            gestor,
        )

    assert "nota 6" in exc.value.mensagem
    assert "Nada foi efetivado" in exc.value.mensagem
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_lote_em_andamento_continua_com_a_mesma_assinatura_e_recusa_outra(
    escritorio_a, gestor, empresa
):
    """Repetir a confirmação com a MESMA assinatura continua o lote, sem duplicar. Com outra prévia,
    recusa com 409: há lote em andamento deste mês."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=2)
    assert not primeira.terminou and primeira.restantes == 3

    repetida = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=2)

    assert repetida.lote_id == primeira.lote_id
    assert repetida.efetivadas_total == 4
    assert _efetivadas(empresa).count() == 4
    nfce(escritorio_a, gestor, numero=6, valor="10.00")
    nova = previa_lida(empresa, 2026, 3)
    with pytest.raises(lote.LoteEmAndamento):
        lote.confirmar_lote(empresa, 2026, 3, nova.assinatura, {}, gestor, limite=2)


def test_continuacao_por_lote_id_nao_recalcula_a_previa(escritorio_a, gestor, empresa):
    """Depois da primeira parte, a prévia muda. A continuação por `lote_id` não depende disso: segue
    o conjunto gravado, e não recusa por assinatura."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=3)
    assert previa_lida(empresa, 2026, 3).assinatura != previa.assinatura

    segunda = lote.confirmar_lote(empresa, None, None, None, None, gestor, lote_id=primeira.lote_id)

    assert segunda.terminou
    assert segunda.efetivadas_total == 5


def test_continuacao_com_escolhas_e_recusada_em_vez_de_ignorada(escritorio_a, gestor, empresa):
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=1)
    chave = _chave_do_grupo(previa, "combustivel")

    with pytest.raises(servico.EntradaInvalidaNFe):
        lote.confirmar_lote(
            empresa,
            None,
            None,
            None,
            {chave: {ID_COMBUSTIVEL: "combustivel_revenda"}},
            gestor,
            lote_id=primeira.lote_id,
        )


def test_lote_concluido_nao_efetiva_mais_nada_e_a_repeticao_da_previa_antiga_recusa(
    escritorio_a, gestor, empresa
):
    """Lote concluído: a continuação não processa nada. A primeira chamada repetida depois da
    conclusão
    recusa (409), porque a prévia já não tem as notas: nada se duplica."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    concluido = confirmar_tudo(empresa, gestor, 2026, 3, previa)

    mais = lote.confirmar_lote(empresa, None, None, None, None, gestor, lote_id=concluido.lote_id)
    assert mais.terminou and mais.efetivadas_nesta_chamada == 0
    assert _efetivadas(empresa).count() == 5

    with pytest.raises(lote.PreviaDesatualizada):
        lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor)
    assert _efetivadas(empresa).count() == 5


def test_nota_que_chega_depois_da_confirmacao_nao_e_efetivada_pelo_lote(
    escritorio_a, gestor, empresa
):
    """Ataque de escopo: a nota 7 entra no mês DEPOIS da confirmação. O lote termina sem ela: ela
    não estava na prévia confirmada, e continua pendente."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    primeira = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=1)
    tarde = nfce(escritorio_a, gestor, numero=7, valor="30.00")

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, lote_id=primeira.lote_id, limite=10
    )

    assert progresso.terminou and progresso.efetivadas_total == 5
    assert not EscrituracaoNFe.objects.filter(vinculo=vinculo(tarde, empresa)).exists()
    assert previa_lida(empresa, 2026, 3).fora == ()


def test_trilha_do_lote_registra_quem_assinatura_quantidades_e_naturezas(
    escritorio_a, gestor, empresa
):
    """Trilha do lote: o usuário, a assinatura, as quantidades e, por grupo, as naturezas
    fixadas."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    chave = _chave_do_grupo(previa, "combustivel")

    progresso = confirmar_tudo(
        empresa, gestor, 2026, 3, previa, escolhas={chave: {ID_COMBUSTIVEL: "combustivel_revenda"}}
    )

    registro = RegistroAuditoria.objects.get(
        acao="escrituracao_nfe.lote_confirmado",
        objeto_tipo="LoteEscrituracaoNFe",
        objeto_id=str(progresso.lote_id),
    )
    assert registro.usuario == gestor
    detalhes = registro.detalhes
    assert detalhes["assinatura"] == previa.assinatura
    assert (detalhes["quantidade_notas"], detalhes["quantidade_itens"]) == (5, 5)
    assert detalhes["escolhas"] == {chave: {ID_COMBUSTIVEL: "combustivel_revenda"}}
    grupos = {g["chave"]: g for g in detalhes["grupos"]}
    assert grupos[chave]["notas"] == 3
    assert grupos[chave]["receita_bruta"] == "390.00"
    assert grupos[chave]["naturezas"] == {ID_COMBUSTIVEL: "combustivel_revenda"}
    assert RegistroAuditoria.objects.filter(
        acao="escrituracao_nfe.lote_concluido", objeto_id=str(progresso.lote_id)
    ).exists()


def test_cada_nota_do_lote_tem_a_trilha_da_efetivacao_individual(escritorio_a, gestor, empresa):
    """A trilha de cada nota é a da escrituração individual: rascunho, natureza e efetivação."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    confirmar_tudo(empresa, gestor, 2026, 3, previa)

    for escrituracao in _efetivadas(empresa):
        acoes = list(
            RegistroAuditoria.objects.filter(
                objeto_tipo="EscrituracaoNFe", objeto_id=str(escrituracao.pk)
            )
            .order_by("pk")
            .values_list("acao", flat=True)
        )
        assert acoes == [
            "escrituracao_nfe.rascunho_criado",
            "escrituracao_nfe.natureza_definida",
            "escrituracao_nfe.efetivada",
        ]


def test_lote_de_uma_empresa_nao_toca_nota_de_outra_do_mesmo_escritorio(
    escritorio_a, gestor, empresa
):
    """Isolamento: o lote de uma empresa não efetiva nem cria escrituração para a outra."""
    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra DL085 Ltda", cnpj=CNPJ_SEGUNDA_EMPRESA
    )
    _notas_padrao(escritorio_a, gestor)
    for numero in (30, 31):
        nfce(escritorio_a, gestor, numero=numero, emitente=CNPJ_SEGUNDA_EMPRESA)

    confirmar_tudo(empresa, gestor, 2026, 3, previa_lida(empresa, 2026, 3))

    assert _efetivadas(empresa).count() == 5
    assert not EscrituracaoNFe.objects.filter(empresa=outra).exists()
    assert sum(g.quantidade_notas for g in previa_lida(outra, 2026, 3).grupos) == 2


def test_lote_nao_cria_lote_sem_nota_pendente(escritorio_a, gestor, empresa):
    """Mês sem nota pendente: a confirmação recusa (400), e não grava lote vazio."""
    previa = previa_lida(empresa, 2026, 3)

    with pytest.raises(servico.EntradaInvalidaNFe):
        lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor)
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_notas_fora_do_lote_nunca_sao_efetivadas_pela_confirmacao(escritorio_a, gestor, empresa):
    """Critério 8 (efetivar nota fora do lote). As notas que a prévia põe FORA (sem sugestão,
    conflito, ilegível e W16) continuam sem escrituração depois da confirmação inteira.
    A mutação que efetiva a nota fora do lote derruba este teste."""
    _notas_padrao(escritorio_a, gestor)
    nfce(escritorio_a, gestor, numero=10, cfop="5949", csosn="102")
    nfce(escritorio_a, gestor, numero=11, cfop="5102", csosn="500")
    nfce(
        escritorio_a,
        gestor,
        numero=12,
        dets=[
            xml.det(
                1,
                cfop="5102",
                vprod="100.00",
                vdesc="0.00",
                icms_xml=xml.icms(csosn="102"),
            )
        ],
        vnf="100.00",
    )
    nfce(escritorio_a, gestor, numero=13, valor="100.00", vnf="150.00")
    previa = previa_lida(empresa, 2026, 3)
    fora = {recusa.vinculo_id for recusa in previa.fora}
    assert len(fora) == 4

    progresso = confirmar_tudo(empresa, gestor, 2026, 3, previa)

    assert progresso.efetivadas_total == 5
    assert _efetivadas(empresa).count() == 5
    assert not EscrituracaoNFe.objects.filter(vinculo_id__in=fora).exists()


def test_criacao_do_lote_e_sua_trilha_sao_atomicas(escritorio_a, gestor, empresa, monkeypatch):
    """A trilha `lote_confirmado` é gravada na MESMA transação da criação do lote (a justificativa
    do inventário em test_dl024_trilha_admin.py depende disto). Se a trilha falha, nem o lote nem as
    linhas das notas ficam gravados, e nenhuma nota é efetivada."""
    _notas_padrao(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)

    def trilha_quebrada(*_a, **_k):
        raise RuntimeError("falha simulada na trilha do lote")

    monkeypatch.setattr(lote, "registrar", trilha_quebrada)
    with pytest.raises(RuntimeError):
        lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor)

    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()
    assert not LoteEscrituracaoNFeNota.objects.filter(lote__empresa=empresa).exists()
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()
