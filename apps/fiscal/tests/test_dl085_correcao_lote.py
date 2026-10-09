"""DL-085, correção da auditoria rodada 1 (2026-10-09): o serviço do lote.

Um grupo de testes por achado (A1, A4, A5, A6, A7) e as lacunas de mutação T1 a T4. Dados sintéticos
(`suporte_dl085`): CNPJ e valores são de teste, e os valores esperados estão escritos à mão.

- A1: a contagem e a trilha `lote_parte` contam só o que a chamada mudou.
- A4: repetir a primeira chamada sem `grupos`, com lote parcial, é outro ato (409).
- A5: a trava do vínculo vem antes da escrituração, como na criação individual.
- A6: cada parte (de efetivação e de leitura) para no orçamento de tempo, com relógio falso.
- A7: a lista do mês não carrega o XML.
- T1 (dois lotes), T2 (nota cancelada), T3 (duas partes em paralelo), T4 (limite acima do teto).
"""

import json
import threading

import pytest
from django.core.management import call_command
from django.db import connection, connections
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    LoteEscrituracaoNFe,
    LoteEscrituracaoNFeNota,
    VinculoNFeEmpresa,
)
from apps.fiscal.tests.suporte_dl081 import receber
from apps.fiscal.tests.suporte_dl085 import (
    CFOP_COMBUSTIVEL,
    CFOP_REVENDA,
    CNPJ_SEGUNDA_EMPRESA,
    nfce,
    previa_lida,
    usuario_gestor,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A, chave_nfe, proc_evento_xml

ANO, MES = 2026, 3
PENDENTE = "pendente"
EFETIVADA = "efetivada"
FALHOU = "falhou"

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-correcao-lote-dl085")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Correção DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def segunda(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Segunda Correção DL085 Ltda",
        cnpj=CNPJ_SEGUNDA_EMPRESA,
    )


def _notas(escritorio, usuario, quantidade, *, emitente=CNPJ_EMITENTE_A, inicio=1, **kwargs):
    """`quantidade` NFC-e (de combustível, salvo `kwargs`), numeradas a partir de `inicio`."""
    for numero in range(inicio, inicio + quantidade):
        nfce(escritorio, usuario, numero=numero, emitente=emitente, **kwargs)


def _registros(acao, lote_id):
    """Detalhes dos registros de auditoria `acao` deste lote, na ordem em que foram gravados."""
    return [
        registro.detalhes
        for registro in RegistroAuditoria.objects.filter(acao=acao).order_by("pk")
        if registro.detalhes.get("lote_id") == lote_id
    ]


def _indice_do_bloqueio(sqls, tabela):
    """Posição, na sequência de consultas com FOR UPDATE, da primeira que trava `tabela`."""
    for indice, sql in enumerate(sqls):
        if f'FROM "{tabela}"' in sql:
            return indice
    raise AssertionError(f"nenhuma consulta com FOR UPDATE sobre {tabela}")


class RelogioFalso:
    """Relógio controlado pelo teste: o tempo só anda quando o teste manda (sem tempo real)."""

    def __init__(self):
        self.segundos = 0.0

    def __call__(self):
        return self.segundos

    def avancar(self, segundos):
        self.segundos += segundos


# ---------------------------------------------------------------------------
# A1 — contagens e trilha contam só o que a chamada mudou
# ---------------------------------------------------------------------------


def test_parte_unica_registra_as_cinco_efetivadas_desta_chamada(escritorio_a, gestor, empresa):
    _notas(escritorio_a, gestor, 5)
    previa = previa_lida(empresa, ANO, MES)

    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=100)

    assert progresso.terminou
    assert progresso.efetivadas_nesta_chamada == 5
    registros = _registros("escrituracao_nfe.lote_parte", progresso.lote_id)
    assert len(registros) == 1
    assert registros[0]["efetivadas"] == 5


def test_linha_que_outra_chamada_ja_processou_nao_conta_nem_muda(escritorio_a, gestor, empresa):
    """Simula a outra chamada: a linha já está efetivada quando esta chega à trava. A resposta é o
    estado neutro, não `efetivada`: nada é criado, nada é regravado e nada é contado."""
    _notas(escritorio_a, gestor, 2)
    previa = previa_lida(empresa, ANO, MES)
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    lote_obj = LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id)
    ja_efetivada = LoteEscrituracaoNFeNota.objects.get(lote=lote_obj, estado=EFETIVADA)
    escrituracoes = EscrituracaoNFe.objects.count()

    resultado = lote._processar_nota(lote_obj, ja_efetivada.pk, gestor, None, set())

    assert resultado == ("outra_chamada", "")
    assert EscrituracaoNFe.objects.count() == escrituracoes
    ja_efetivada.refresh_from_db()
    assert (ja_efetivada.estado, ja_efetivada.motivo) == (EFETIVADA, "")
    # A gravação condicional também não sobrescreve a linha de outra chamada.
    assert (
        lote._gravar_estado(ja_efetivada.pk, lote.EstadoNotaDoLoteNFe.FALHOU, motivo="x") is False
    )
    ja_efetivada.refresh_from_db()
    assert ja_efetivada.estado == EFETIVADA


@pytest.mark.django_db(transaction=True)
def test_duas_partes_simultaneas_contam_cada_nota_uma_vez(
    escritorio_a, gestor, empresa, esquema_atual
):
    """T3. Duas threads continuam o mesmo lote de 20 notas. Cada nota é efetivada uma vez, e a soma
    do que cada chamada diz ter efetivado, e a soma da trilha, são as 20 notas (não 39)."""
    _notas(escritorio_a, gestor, 20)
    previa = previa_lida(empresa, ANO, MES)
    primeira = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    respostas = [primeira]
    erros = []
    barreira = threading.Barrier(2)

    def continuar():
        try:
            barreira.wait()
            while True:
                progresso = lote.confirmar_lote(
                    empresa, None, None, None, None, gestor, limite=4, lote_id=primeira.lote_id
                )
                respostas.append(progresso)
                if progresso.terminou:
                    break
        except Exception as exc:  # noqa: BLE001 — o teste confere a lista de erros abaixo
            erros.append(repr(exc))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=continuar) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert erros == []
    assert sum(r.efetivadas_nesta_chamada for r in respostas) == 20
    assert sum(r.ja_efetivadas_nesta_chamada for r in respostas) == 0
    assert (
        sum(r["efetivadas"] for r in _registros("escrituracao_nfe.lote_parte", primeira.lote_id))
        == 20
    )
    assert len(_registros("escrituracao_nfe.lote_concluido", primeira.lote_id)) == 1
    assert (
        EscrituracaoNFe.objects.filter(empresa=empresa, estado=EstadoEscrituracao.EFETIVADA).count()
        == 20
    )
    assert EscrituracaoNFe.objects.filter(empresa=empresa).count() == 20


# ---------------------------------------------------------------------------
# A4 — repetir a primeira chamada sem `grupos` é outro ato quando o lote é parcial
# ---------------------------------------------------------------------------


@pytest.fixture
def esquema_atual():
    """Leva o esquema de `fiscal` à última migração antes de um teste com threads.

    Os testes de migração (`test_dl083_migracao.py`) voltam o esquema para trás e deixam o banco na
    migração 0012, sem as tabelas do lote. Testes transacionais rodam depois dos não transacionais,
    e as threads abrem conexões novas: sem este passo, elas enxergam o esquema antigo. A chamada é
    idempotente (sem migração pendente, não faz nada).
    """
    call_command("migrate", "fiscal", verbosity=0)


def _chave_do_grupo_com_cfop(previa, cfop):
    for grupo in previa.grupos:
        if any(assinatura.cfop == cfop for assinatura in grupo.assinaturas):
            return grupo.chave
    raise AssertionError(f"nenhum grupo com CFOP {cfop}")


def _dois_grupos(escritorio, usuario):
    _notas(escritorio, usuario, 2)  # combustível: 1 e 2
    _notas(escritorio, usuario, 2, inicio=3, cfop=CFOP_REVENDA, csosn="102")  # revenda: 3 e 4


def test_repetir_sem_grupos_com_lote_parcial_recusa_409(escritorio_a, gestor, empresa):
    _dois_grupos(escritorio_a, gestor)
    previa = previa_lida(empresa, ANO, MES)
    combustivel = _chave_do_grupo_com_cfop(previa, CFOP_COMBUSTIVEL)
    parcial = lote.confirmar_lote(
        empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1, grupos=[combustivel]
    )
    assert not parcial.terminou
    assert parcial.total_notas == 2

    with pytest.raises(lote.LoteEmAndamento):
        lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, grupos=None)

    # A mesma repetição com os mesmos grupos continua o lote, sem duplicar nada.
    continuado = lote.confirmar_lote(
        empresa, ANO, MES, previa.assinatura, {}, gestor, limite=100, grupos=[combustivel]
    )
    assert continuado.lote_id == parcial.lote_id
    assert continuado.total_notas == 2


def test_repetir_sem_grupos_com_lote_completo_continua(escritorio_a, gestor, empresa):
    """O lado bom do A4: o lote que cobre a prévia inteira não é recusado na repetição."""
    _dois_grupos(escritorio_a, gestor)
    previa = previa_lida(empresa, ANO, MES)
    primeiro = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)

    repetido = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)

    assert repetido.lote_id == primeiro.lote_id
    assert repetido.total_notas == 4
    assert LoteEscrituracaoNFe.objects.filter(empresa=empresa).count() == 1


# ---------------------------------------------------------------------------
# A5 — a trava do vínculo vem antes da escrituração (mesma ordem da criação individual)
# ---------------------------------------------------------------------------


def test_processar_nota_trava_empresa_linha_vinculo_e_so_depois_a_escrituracao(
    escritorio_a, gestor, empresa
):
    """T9, determinístico. A sequência de travas de `_processar_nota` é: empresa, linha do lote,
    vínculo e, por último, a escrituração. A criação individual trava vínculo e depois escrituração,
    então a ordem é a mesma e não há deadlock entre as duas."""
    _notas(escritorio_a, gestor, 2)
    previa = previa_lida(empresa, ANO, MES)
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    lote_obj = LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id)
    pendente = LoteEscrituracaoNFeNota.objects.get(lote=lote_obj, estado=PENDENTE)

    with CaptureQueriesContext(connection) as contexto:
        lote._processar_nota(lote_obj, pendente.pk, gestor, None, set())

    sqls = [q["sql"] for q in contexto.captured_queries if "FOR UPDATE" in q["sql"]]
    ordem = [
        _indice_do_bloqueio(sqls, Empresa._meta.db_table),
        _indice_do_bloqueio(sqls, LoteEscrituracaoNFeNota._meta.db_table),
        _indice_do_bloqueio(sqls, VinculoNFeEmpresa._meta.db_table),
        _indice_do_bloqueio(sqls, EscrituracaoNFe._meta.db_table),
    ]
    assert ordem == sorted(ordem), (
        "as travas saíram fora da ordem empresa, linha, vínculo, escrituração"
    )


@pytest.mark.django_db(transaction=True)
def test_lote_e_criacao_individual_em_paralelo_nao_levantam_erro_de_banco(
    escritorio_a, gestor, empresa, esquema_atual
):
    """T9, com threads: a efetivação pelo lote e a criação individual do rascunho da mesma nota,
    no mesmo instante. Nenhum dos dois pode levantar erro de banco (deadlock ou outro). Cada um
    termina com resultado de negócio: efetivada, ou a recusa "já escriturada"."""
    _notas(escritorio_a, gestor, 2)
    previa = previa_lida(empresa, ANO, MES)
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    lote_obj = LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id)
    pendente = LoteEscrituracaoNFeNota.objects.select_related("vinculo").get(
        lote=lote_obj, estado=PENDENTE
    )
    vinculo = pendente.vinculo
    resultados = {}
    barreira = threading.Barrier(2)

    def pelo_lote():
        try:
            barreira.wait()
            resultados["lote"] = lote._processar_nota(lote_obj, pendente.pk, gestor, None, set())
        except Exception as exc:  # noqa: BLE001
            resultados["lote"] = repr(exc)
        finally:
            connections.close_all()

    def individual():
        try:
            barreira.wait()
            servico_nfe.criar_rascunho(vinculo, usuario=gestor)
            resultados["individual"] = "criado"
        except servico_nfe.EscrituracaoNFeErro as exc:
            resultados["individual"] = f"negocio: {exc.mensagem}"
        except Exception as exc:  # noqa: BLE001
            resultados["individual"] = repr(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=pelo_lote), threading.Thread(target=individual)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert "Error" not in str(resultados), resultados
    assert "Exception" not in str(resultados), resultados
    assert EscrituracaoNFe.objects.filter(vinculo=vinculo).count() <= 1


# ---------------------------------------------------------------------------
# A6 — orçamento de tempo por parte, com relógio falso (determinístico)
# ---------------------------------------------------------------------------


def test_parte_de_efetivacao_para_no_orcamento_e_o_resto_fica_pendente(
    escritorio_a, gestor, empresa, monkeypatch
):
    """T10. Cada nota custa 4 s de relógio falso. Com orçamento de 10 s, a parte para depois da 3ª
    nota, com 147 pendentes. As chamadas seguintes completam o lote, sem nota perdida."""
    _notas(escritorio_a, gestor, 150)
    previa = previa_lida(empresa, ANO, MES)
    relogio = RelogioFalso()
    original = lote._processar_nota

    def nota_que_custa_quatro_segundos(*args, **kwargs):
        relogio.avancar(4.0)
        return original(*args, **kwargs)

    monkeypatch.setattr(lote, "_relogio", relogio)
    monkeypatch.setattr(lote, "_processar_nota", nota_que_custa_quatro_segundos)

    primeira = lote.confirmar_lote(
        empresa, ANO, MES, previa.assinatura, {}, gestor, limite=lote.LIMITE_MAXIMO_DA_PARTE
    )

    assert primeira.efetivadas_nesta_chamada == 3
    assert primeira.restantes == 147
    assert not primeira.terminou
    progresso, chamadas = primeira, 1
    while not progresso.terminou:
        progresso = lote.confirmar_lote(
            empresa,
            None,
            None,
            None,
            None,
            gestor,
            limite=lote.LIMITE_MAXIMO_DA_PARTE,
            lote_id=primeira.lote_id,
        )
        chamadas += 1
    assert progresso.efetivadas_total == 150
    assert chamadas == 50
    assert EscrituracaoNFe.objects.filter(empresa=empresa).count() == 150


def test_parte_de_leitura_para_no_orcamento_e_o_resto_fica_em_restam(
    escritorio_a, gestor, empresa, monkeypatch
):
    _notas(escritorio_a, gestor, 150)
    relogio = RelogioFalso()
    original = lote.ler_itens

    def leitura_que_custa_quatro_segundos(documento):
        relogio.avancar(4.0)
        return original(documento)

    monkeypatch.setattr(lote, "_relogio", relogio)
    monkeypatch.setattr(lote, "ler_itens", leitura_que_custa_quatro_segundos)

    leitura = lote.ler_notas_do_mes(empresa, ANO, MES, limite=lote.LIMITE_PADRAO_DA_LEITURA)

    assert leitura.lidas_nesta_chamada == 3
    assert leitura.restam == 147
    assert not leitura.terminou


# ---------------------------------------------------------------------------
# A7 — a lista do mês não carrega o XML
# ---------------------------------------------------------------------------


def test_lista_do_mes_nao_carrega_o_xml_e_a_leitura_carrega(escritorio_a, gestor, empresa):
    _notas(escritorio_a, gestor, 2)

    notas = servico_nfe.notas_do_mes(empresa, ANO, MES)

    assert len(notas) == 2
    assert all("xml_original" not in nota.documento.__dict__ for nota in notas)
    # A leitura precisa do XML, e o carrega na hora (o campo adiado é lido quando preciso).
    leitura = lote.ler_notas_do_mes(empresa, ANO, MES, limite=lote.LIMITE_PADRAO_DA_LEITURA)
    assert leitura.lidas_nesta_chamada == 2
    assert leitura.terminou


# ---------------------------------------------------------------------------
# T1 — dois lotes em andamento ao mesmo tempo não se tocam (mutante M33)
# ---------------------------------------------------------------------------


def test_dois_lotes_em_andamento_nao_se_tocam(escritorio_a, gestor, empresa, segunda):
    _notas(escritorio_a, gestor, 4)
    _notas(escritorio_a, gestor, 4, emitente=CNPJ_SEGUNDA_EMPRESA)
    previa_a = previa_lida(empresa, ANO, MES)
    previa_b = previa_lida(segunda, ANO, MES)
    lote_a = lote.confirmar_lote(empresa, ANO, MES, previa_a.assinatura, {}, gestor, limite=1)
    lote_b = lote.confirmar_lote(segunda, ANO, MES, previa_b.assinatura, {}, gestor, limite=1)

    progresso = lote_a
    while not progresso.terminou:
        progresso = lote.confirmar_lote(
            empresa, None, None, None, None, gestor, limite=2, lote_id=lote_a.lote_id
        )

    assert (
        EscrituracaoNFe.objects.filter(empresa=empresa, estado=EstadoEscrituracao.EFETIVADA).count()
        == 4
    )
    assert (
        EscrituracaoNFe.objects.filter(empresa=segunda, estado=EstadoEscrituracao.EFETIVADA).count()
        == 1
    )
    assert (
        LoteEscrituracaoNFeNota.objects.filter(lote_id=lote_b.lote_id, estado=PENDENTE).count() == 3
    )
    assert LoteEscrituracaoNFe.objects.get(pk=lote_b.lote_id).estado == "em_andamento"


# ---------------------------------------------------------------------------
# T2 — nota cancelada: fora da prévia, sem escrituração (mutante M26)
# ---------------------------------------------------------------------------


def test_nota_cancelada_nao_entra_nem_vira_escrituracao(escritorio_a, gestor, empresa):
    _notas(escritorio_a, gestor, 3)
    receber(
        escritorio_a,
        gestor,
        proc_evento_xml(
            tp_evento="110111",
            chave=chave_nfe(emitente=CNPJ_EMITENTE_A, modelo="65", serie="1", numero="2"),
            autor=("CNPJ", CNPJ_EMITENTE_A),
            c_stat="135",
        ),
    )

    previa = previa_lida(empresa, ANO, MES)

    assert previa.canceladas == 1
    assert "2" not in [nota.numero for grupo in previa.grupos for nota in grupo.notas]
    assert "2" not in [recusa.numero for recusa in previa.fora]
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=100)
    assert progresso.total_notas == 2
    assert progresso.efetivadas_total == 2
    assert not EscrituracaoNFe.objects.filter(
        empresa=empresa, vinculo__documento__numero="2"
    ).exists()


# ---------------------------------------------------------------------------
# T4 — limite acima do teto: 400 no domínio e na API (mutante M18)
# ---------------------------------------------------------------------------


def test_limite_acima_do_teto_e_recusado_pelo_dominio(escritorio_a, gestor, empresa):
    _notas(escritorio_a, gestor, 2)
    previa = previa_lida(empresa, ANO, MES)

    with pytest.raises(servico_nfe.EntradaInvalidaNFe):
        lote.confirmar_lote(
            empresa, ANO, MES, previa.assinatura, {}, gestor, limite=lote.LIMITE_MAXIMO_DA_PARTE + 1
        )
    with pytest.raises(servico_nfe.EntradaInvalidaNFe):
        lote.ler_notas_do_mes(empresa, ANO, MES, limite=lote.LIMITE_MAXIMO_DA_LEITURA + 1)
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_api_recusa_limite_acima_do_teto_com_400_e_sem_gravar(
    escritorio_a, gestor, empresa, client
):
    _notas(escritorio_a, gestor, 2)
    previa = previa_lida(empresa, ANO, MES)
    client.force_login(gestor)

    confirmar = client.post(
        reverse("fiscal_api:nfe_lote_confirmar", args=[empresa.pk]),
        data=json.dumps({"ano": ANO, "mes": MES, "assinatura": previa.assinatura, "limite": 151}),
        content_type="application/json",
    )
    ler = client.post(
        reverse("fiscal_api:nfe_lote_ler", args=[empresa.pk]),
        data=json.dumps({"ano": ANO, "mes": MES, "limite": 801}),
        content_type="application/json",
    )

    assert confirmar.status_code == 400
    assert "limite" in json.loads(confirmar.content)
    assert ler.status_code == 400
    assert "limite" in json.loads(ler.content)
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_criacao_individual_do_rascunho_trava_a_empresa_antes_do_vinculo(
    escritorio_a, gestor, empresa
):
    """Ajuste do arquiteto (A5, resíduo): a criação individual do rascunho segue a mesma ordem do
    lote e da efetivação, empresa antes do vínculo, para não haver deadlock entre os dois."""
    _notas(escritorio_a, gestor, 1)
    from apps.fiscal import escrituracao_nfe as servico_nfe

    vinculo_da_nota = VinculoNFeEmpresa.objects.get(empresa=empresa)
    with CaptureQueriesContext(connection) as contexto:
        servico_nfe.criar_rascunho(vinculo_da_nota, usuario=gestor)

    sqls = [q["sql"] for q in contexto.captured_queries if "FOR UPDATE" in q["sql"]]
    assert _indice_do_bloqueio(sqls, Empresa._meta.db_table) < _indice_do_bloqueio(
        sqls, VinculoNFeEmpresa._meta.db_table
    )
