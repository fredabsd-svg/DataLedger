"""DL-082 (frente A): marca de monofásico por item (HI-128), regras de escrita, isolamento e API.

- A marca é do contador, só em rascunho (o gatilho da DL-081 recusa o resto, e o teste prova isso).
- Não vale para natureza que não é mercadoria; uma natureza incompatível com a marca é recusada.
- A API expõe a marca e o segmento da devolução, e o pré-DAS expõe avisos e bruto/deduzido.
- Dados de outra empresa não entram no pré-DAS nem na apuração (isolamento, AGENTS.md §11).
"""

import json
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import EscrituracaoNFe, NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

NF = NaturezaOperacaoNFe


@pytest.fixture
def empresa_a(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Comercio Marca DL082 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def empresa_b_mesmo_escritorio(escritorio_a):
    """Outra empresa do MESMO escritório: a NF-e dela não pode aparecer na apuração da empresa A."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra DL082 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


@pytest.fixture
def paralegal_a(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-marca-dl082")


def _revenda_em_rascunho(escritorio, usuario, empresa, numero=501, vprod="100000.00"):
    """Janela de 300.000 e uma revenda do PA em RASCUNHO. Devolve (escrituração, id do item)."""
    janela(empresa, usuario, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        itens=[{"cfop": "5102", "vprod": vprod}],
    )
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    item = esc.naturezas_dos_itens.get()
    servico_nfe.definir_natureza(esc, NF.REVENDA, [item.item_id], usuario=usuario)
    return esc, item.item_id


# ---------------------------------------------------------------------------
# Marca de monofásico (HI-128)
# ---------------------------------------------------------------------------


def test_marca_de_monofasico_vira_segmento_e_tira_pis_e_cofins(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Revenda de 100.000 com a marca. Esperado (à mão), alíquota 5,32%: PIS e Cofins saem (zero);
    IRPJ 292,60; CSLL 186,20; CPP 2.207,80; ICMS 1.808,80. Total 4.495,40."""
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa)
    servico_nfe.definir_marca_monofasico(esc, [item_id], True, usuario=usuario_gestor_a)
    servico_nfe.efetivar(esc, usuario=usuario_gestor_a)
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (segmento,) = resultado.anexos[0].segmentos
    assert segmento.segmento == "monofasico"
    valores = {linha.tributo: linha for linha in segmento.linhas}
    assert valores["PIS"].desconsiderado is True and valores["PIS"].valor == Decimal("0.00")
    assert valores["COFINS"].desconsiderado is True and valores["COFINS"].valor == Decimal("0.00")
    assert valores["IRPJ"].valor == Decimal("292.60")
    assert valores["ICMS"].valor == Decimal("1808.80")
    assert resultado.total == Decimal("4495.40")


def test_natureza_monofasico_e_marca_nao_se_somam(escritorio_a, usuario_gestor_a, empresa_a):
    """A natureza `monofasico` continua valendo. Com ela E a marca, o segmento é o mesmo (união)."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=502,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.MONOFASICO}, marcas=[1])
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (segmento,) = resultado.anexos[0].segmentos
    assert segmento.segmento == "monofasico"
    assert resultado.total == Decimal("4495.40")


def test_sem_marca_o_item_e_normal(escritorio_a, usuario_gestor_a, empresa_a):
    """Lado conservador: sem marca, o item de revenda é normal, e o PIS e a Cofins entram."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=503,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (segmento,) = resultado.anexos[0].segmentos
    assert segmento.segmento == "normal"
    assert resultado.total == Decimal("5320.00")


def test_marca_so_vale_para_mercadoria(escritorio_a, usuario_gestor_a, empresa_a):
    """Combustível (natureza que não é mercadoria do corte) não aceita a marca: recusa nomeada."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=504,
        itens=[{"cfop": "5656", "vprod": "1000.00"}],
    )
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    item = esc.naturezas_dos_itens.get()
    servico_nfe.definir_natureza(esc, NF.COMBUSTIVEL, [item.item_id], usuario=usuario_gestor_a)

    with pytest.raises(servico_nfe.EntradaInvalidaNFe) as erro:
        servico_nfe.definir_marca_monofasico(esc, [item.item_id], True, usuario=usuario_gestor_a)
    assert "só vale para venda de mercadoria" in erro.value.mensagem


def test_natureza_incompativel_com_a_marca_e_recusada(escritorio_a, usuario_gestor_a, empresa_a):
    """Marca em revenda, depois natureza de combustível: a troca é recusada, sem gravar nada."""
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=505)
    servico_nfe.definir_marca_monofasico(esc, [item_id], True, usuario=usuario_gestor_a)

    with pytest.raises(servico_nfe.EntradaInvalidaNFe) as erro:
        servico_nfe.definir_natureza(esc, NF.COMBUSTIVEL, [item_id], usuario=usuario_gestor_a)
    assert "tire a marca" in erro.value.mensagem
    assert NaturezaItemNFe.objects.get(item_id=item_id).natureza == NF.REVENDA


def test_marca_nao_muda_depois_da_efetivacao(escritorio_a, usuario_gestor_a, empresa_a):
    """Efetivada, a marca não muda: a recusa do serviço e a do banco (gatilho da DL-081)."""
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=506)
    servico_nfe.efetivar(esc, usuario=usuario_gestor_a)

    with pytest.raises(servico_nfe.EscrituracaoNFeErro):
        servico_nfe.definir_marca_monofasico(esc, [item_id], True, usuario=usuario_gestor_a)

    with pytest.raises(IntegrityError), transaction.atomic():
        NaturezaItemNFe.objects.filter(item_id=item_id).update(monofasico=True)


def test_marca_e_segmento_sao_imutaveis_no_banco_depois_da_efetivacao(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """O gatilho da DL-081 cobre as colunas novas: qualquer UPDATE em natureza de item efetivado
    é recusado pelo banco (mesmo que o Python falhe)."""
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=507)
    servico_nfe.efetivar(esc, usuario=usuario_gestor_a)
    with pytest.raises(IntegrityError) as erro, transaction.atomic():
        NaturezaItemNFe.objects.filter(item_id=item_id).update(segmento_devolucao="revenda")
    assert "não muda" in str(erro.value)


def test_marca_desfeita_volta_a_ser_normal(escritorio_a, usuario_gestor_a, empresa_a):
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=508)
    servico_nfe.definir_marca_monofasico(esc, [item_id], True, usuario=usuario_gestor_a)
    servico_nfe.definir_marca_monofasico(esc, [item_id], False, usuario=usuario_gestor_a)
    assert NaturezaItemNFe.objects.get(item_id=item_id).monofasico is False


# ---------------------------------------------------------------------------
# Isolamento entre empresas (critério 7)
# ---------------------------------------------------------------------------


def test_nota_de_outra_empresa_nao_entra_na_mercadoria_da_empresa(
    escritorio_a, usuario_gestor_a, empresa_a, empresa_b_mesmo_escritorio
):
    """NF-e emitida pela empresa B (mesmo escritório): a apuração da empresa A não a vê."""
    empresa = cenario(empresa_a)
    documento_b = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa_b_mesmo_escritorio,
        numero=601,
        itens=[{"cfop": "5102", "vprod": "77777.00"}],
        emitente_cnpj=CNPJ_DESTINATARIO_A,
    )
    esc_b = servico_nfe.criar_rascunho(
        vinculo(documento_b, empresa_b_mesmo_escritorio), usuario=usuario_gestor_a
    )
    item_b = esc_b.naturezas_dos_itens.get()
    servico_nfe.definir_natureza(esc_b, NF.REVENDA, [item_b.item_id], usuario=usuario_gestor_a)
    servico_nfe.efetivar(esc_b, usuario=usuario_gestor_a)

    mes = servico_receita.mercadoria_do_mes(empresa, 2026, 6)
    assert mes.segmentos == ()
    assert servico_receita.composicao_do_mes(empresa, 2026, 6).interno.mercadoria == Decimal("0")


# ---------------------------------------------------------------------------
# API (critério 7 e a exposição do plano)
# ---------------------------------------------------------------------------


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def test_api_marca_monofasico_so_em_rascunho_e_por_gestor(
    client, escritorio_a, usuario_gestor_a, paralegal_a, empresa_a, escritorio_b
):
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=701)
    url = _url("nfe_escrituracao_marca_monofasico", empresa.pk, esc.pk)

    client.force_login(paralegal_a)
    assert _post(client, url, {"monofasico": True, "itens": [item_id]}).status_code == 403
    assert NaturezaItemNFe.objects.get(item_id=item_id).monofasico is False

    client.force_login(usuario_gestor_a)
    resposta = _post(client, url, {"monofasico": True, "itens": [item_id]})
    assert resposta.status_code == 200
    assert NaturezaItemNFe.objects.get(item_id=item_id).monofasico is True


def test_api_marca_de_outra_empresa_responde_404(
    client, escritorio_a, usuario_gestor_a, empresa_a, escritorio_b
):
    """Gestor de outro escritório não toca a escrituração da empresa A (404, nada gravado)."""
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=702)
    gestor_b = usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-marca-b-dl082")
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B DL082", cnpj="77888999000155"
    )
    client.force_login(gestor_b)

    resposta = _post(
        client,
        _url("nfe_escrituracao_marca_monofasico", empresa_b.pk, esc.pk),
        {"monofasico": True, "itens": [item_id]},
    )

    assert resposta.status_code == 404
    assert NaturezaItemNFe.objects.get(item_id=item_id).monofasico is False


def test_api_segmento_de_devolucao_invalido_responde_400(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=703)
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        _url("nfe_escrituracao_segmento_devolucao", empresa.pk, esc.pk),
        {"segmento": "inventado", "itens": [item_id]},
    )

    assert resposta.status_code == 400


def test_api_marca_em_escrituracao_efetivada_responde_409(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    empresa = cenario(empresa_a)
    esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=704)
    servico_nfe.efetivar(esc, usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        _url("nfe_escrituracao_marca_monofasico", empresa.pk, esc.pk),
        {"monofasico": True, "itens": [item_id]},
    )

    assert resposta.status_code == 409
    assert EscrituracaoNFe.objects.get(pk=esc.pk).estado == "efetivada"


def test_api_pre_das_expoe_avisos_e_bruto_deduzido_por_segmento(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    """Esperado (à mão): RBT12 300.000; revenda 100.000 com CSOSN 900 (aviso, não recusa);
    total 5.320,00. O segmento traz bruto 100.000,00 e deduzido 0,00."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=705,
        itens=[{"cfop": "5102", "vprod": "100000.00", "csosn": "900"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = client.get(_url("pre_das", empresa.pk) + "?ano=2026&mes=6")

    assert resposta.status_code == 200
    corpo = json.loads(resposta.content)
    assert corpo["total"] == "5320.00"
    assert any("CSOSN 900" in aviso for aviso in corpo["avisos"])
    segmento = corpo["anexos"][0]["segmentos"][0]
    assert segmento["segmento"] == "normal"
    assert segmento["bruto"] == "100000.00"
    assert segmento["deduzido"] == "0.00"


def test_api_pre_das_recusa_com_409_e_lista_os_bloqueios(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    """Combustível: a API responde 409 com a lista de bloqueios nomeados (critério 5)."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=706,
        itens=[{"cfop": "5656", "vprod": "1000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.COMBUSTIVEL})
    confirmar_pa(empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = client.get(_url("pre_das", empresa.pk) + "?ano=2026&mes=6")

    assert resposta.status_code == 409
    codigos = [b["codigo"] for b in json.loads(resposta.content)["bloqueios"]]
    assert "natureza_fora_do_corte" in codigos


def test_check_do_banco_recusa_segmento_fora_do_catalogo(escritorio_a, usuario_gestor_a, empresa_a):
    """O CHECK da migração 0014 aceita só os valores do catálogo de devolução, como a DL-081 faz com
    a natureza. Vale mesmo se o Python falhar."""
    empresa = cenario(empresa_a)
    _esc, item_id = _revenda_em_rascunho(escritorio_a, usuario_gestor_a, empresa, numero=509)

    with pytest.raises(IntegrityError), transaction.atomic():
        NaturezaItemNFe.objects.filter(item_id=item_id).update(segmento_devolucao="inventado")
