"""DL-087 (frente A), cadastro das regras: recusas com mensagem, duplicidade (409), desativação com
fim da vigência e motivo, trilha de criação e de desativação, imutabilidade (save, update e delete)
e as CHECKs do banco. Critérios 4 (trilha) e 5 (recusas).

Dados sintéticos. Datas e horários são controlados pelo próprio teste (`agora=`), não pelo relógio.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import classificacao as cl
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import RegraClassificacaoNFe, RegraImutavel
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

FUSO = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 3, 20, 15, 0, tzinfo=FUSO)


def dados(**campos):
    base = {
        "tipo": "saida_propria",
        "cfop": "5102",
        "natureza": "revenda",
        "vigencia_inicio": date(2026, 3, 1),
        "vigencia_fim": None,
        "ncm": "",
        "ncm_modo": "",
        "cst_csosn": "",
        "id_dest": "",
    }
    base.update(campos)
    return cl.DadosDaRegra(**base)


@pytest.fixture
def gestor(escritorio_a):
    from apps.fiscal.tests.suporte_dl081 import usuario_com_papel

    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-cadastro-dl087")


@pytest.fixture
def empresa(escritorio_a):
    from apps.empresas.models import Empresa

    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa Cadastro DL087 Ltda", cnpj="12345678000195"
    )


@pytest.fixture
def outra_empresa(escritorio_a):
    from apps.empresas.models import Empresa

    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra Cadastro DL087 Ltda", cnpj="98765432000199"
    )


def criar(escritorio, usuario, empresa=None, **campos):
    return cl.criar_regra(
        escritorio=escritorio,
        empresa=empresa,
        dados=dados(**campos),
        usuario=usuario,
    )


def trilha(acao):
    return RegistroAuditoria.objects.filter(acao=acao)


# ---------------------------------------------------------------------------
# Criação e trilha
# ---------------------------------------------------------------------------


def test_cria_regra_do_escritorio_e_regra_da_empresa_com_trilha(escritorio_a, gestor, empresa):
    do_escritorio = criar(escritorio_a, gestor, cfop="5102", natureza="revenda")
    da_empresa = criar(
        escritorio_a,
        gestor,
        empresa=empresa,
        cfop="5656",
        natureza="combustivel",
        ncm="27101259",
        ncm_modo="exato",
    )

    assert do_escritorio.empresa_id is None
    assert da_empresa.empresa_id == empresa.pk
    assert do_escritorio.criada_por_id == gestor.pk
    assert trilha("classificacao_nfe.regra_criada").count() == 2
    registro = trilha("classificacao_nfe.regra_criada").get(objeto_id=str(da_empresa.pk))
    assert registro.detalhes["cfop"] == "5656"
    assert registro.detalhes["escopo"] == "empresa"


def test_detalhes_da_trilha_nao_trazem_cnpj_nem_nome(escritorio_a, gestor, empresa):
    criar(escritorio_a, gestor, empresa=empresa)
    registro = trilha("classificacao_nfe.regra_criada").get()
    texto = str(registro.detalhes)
    assert empresa.cnpj not in texto
    assert empresa.razao_social not in texto


# ---------------------------------------------------------------------------
# Recusas com mensagem (critério 5): 400, nada gravado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campos", "trecho"),
    [
        ({"tipo": "ajuste", "natureza": "ajuste"}, "ajuste"),
        ({"cfop": "5000"}, "fora da tabela oficial"),
        ({"cfop": "51"}, "exatamente 4 dígitos"),
        ({"natureza": "devolucao_venda"}, "não cabe em saída própria"),
        ({"natureza": "combustivel", "cfop": "5656"}, "exige NCM"),
        ({"natureza": "combustivel_revenda", "cfop": "5656"}, "exige NCM"),
        ({"ncm": "2710125", "ncm_modo": "exato"}, "NCM exato deve ter 8 dígitos"),
        ({"ncm": "2", "ncm_modo": "prefixo"}, "de 2 a 7 dígitos"),
        ({"ncm": "27101259"}, "Informe o modo do NCM"),
        ({"ncm_modo": "exato"}, "Modo do NCM sem NCM"),
        ({"cst_csosn": "5"}, "2 ou 3 dígitos"),
        ({"id_dest": "4"}, "idDest deve ser"),
        ({"vigencia_fim": date(2026, 2, 28)}, "anterior ao início"),
        ({"natureza": "natureza_inventada"}, "Natureza desconhecida"),
    ],
)
def test_recusa_com_mensagem_e_nada_e_gravado(escritorio_a, gestor, campos, trecho):
    with pytest.raises(servico.EntradaInvalidaNFe, match=trecho):
        criar(escritorio_a, gestor, **campos)
    assert RegraClassificacaoNFe.objects.count() == 0


def test_combustivel_com_prefixo_de_ncm_de_combustivel_e_aceito(escritorio_a, gestor):
    regra = criar(
        escritorio_a, gestor, cfop="5656", natureza="combustivel", ncm="2710", ncm_modo="prefixo"
    )
    assert regra.natureza == "combustivel"


def test_combustivel_com_prefixo_que_alcanca_lubrificante_e_aceito_com_aviso(escritorio_a, gestor):
    """Ajuste do arquiteto, item 4: a criação é aceita, e o AVISO (não bloqueio) aparece."""
    dados_da_regra = cl.validar_dados_da_regra(
        dados(cfop="5656", natureza="combustivel", ncm="2710", ncm_modo="prefixo")
    )
    avisos = cl.avisos_da_regra(dados_da_regra, cl.ESCOPO_ESCRITORIO)
    assert any("lubrificante" in aviso for aviso in avisos)
    regra = criar(
        escritorio_a, gestor, cfop="5656", natureza="combustivel", ncm="2710", ncm_modo="prefixo"
    )
    assert regra.pk is not None


def test_aviso_de_cst_de_regime_normal_so_no_escritorio(escritorio_a):
    """Ajuste do arquiteto, item 5: CST de 2 dígitos no escritório avisa que o Simples não é
    alcançado. Na empresa não há aviso (a regra é do cliente e ele decide)."""
    dados_da_regra = cl.validar_dados_da_regra(dados(cst_csosn="00"))
    assert any("CSOSN" in a for a in cl.avisos_da_regra(dados_da_regra, cl.ESCOPO_ESCRITORIO))
    assert cl.avisos_da_regra(dados_da_regra, cl.ESCOPO_EMPRESA) == ()
    csosn = cl.validar_dados_da_regra(dados(cst_csosn="102"))
    assert cl.avisos_da_regra(csosn, cl.ESCOPO_ESCRITORIO) == ()


def test_recusa_nao_grava_trilha(escritorio_a, gestor):
    with pytest.raises(servico.EntradaInvalidaNFe):
        criar(escritorio_a, gestor, cfop="5000")
    assert trilha("classificacao_nfe.regra_criada").count() == 0


# ---------------------------------------------------------------------------
# Duplicidade (409): mesmo escopo, mesmos critérios, vigências que se cruzam, ambas ativas
# ---------------------------------------------------------------------------


def test_duplicada_do_mesmo_escopo_com_vigencia_cruzada_e_recusada(escritorio_a, gestor):
    criar(escritorio_a, gestor, vigencia_inicio=date(2026, 3, 1), vigencia_fim=None)
    with pytest.raises(cl.RegraDuplicada, match="regra n.º"):
        criar(escritorio_a, gestor, vigencia_inicio=date(2026, 6, 1))
    assert RegraClassificacaoNFe.objects.count() == 1


def test_mesmos_criterios_com_vigencias_que_nao_se_cruzam_sao_aceitos(escritorio_a, gestor):
    criar(escritorio_a, gestor, vigencia_inicio=date(2026, 1, 1), vigencia_fim=date(2026, 3, 31))
    criar(escritorio_a, gestor, vigencia_inicio=date(2026, 4, 1), vigencia_fim=None)
    assert RegraClassificacaoNFe.objects.count() == 2


def test_mesmos_criterios_em_escopos_diferentes_nao_sao_duplicata(escritorio_a, gestor, empresa):
    """Escopo diferente é precedência (empresa sobre escritório), não duplicidade."""
    criar(escritorio_a, gestor)
    criar(escritorio_a, gestor, empresa=empresa, natureza="producao_propria")
    assert RegraClassificacaoNFe.objects.count() == 2


def test_regra_desativada_nao_bloqueia_nova_com_os_mesmos_criterios(escritorio_a, gestor):
    antiga = criar(escritorio_a, gestor)
    cl.desativar_regra(antiga, motivo="troca de natureza", usuario=gestor, agora=AGORA)
    criar(
        escritorio_a,
        gestor,
        vigencia_inicio=AGORA.date() - timedelta(days=0),
        natureza="producao_propria",
    )
    assert RegraClassificacaoNFe.objects.filter(desativada_em__isnull=True).count() == 1


def test_duplicata_de_regra_de_outra_empresa_nao_bloqueia(
    escritorio_a, gestor, empresa, outra_empresa
):
    criar(escritorio_a, gestor, empresa=empresa)
    criar(escritorio_a, gestor, empresa=outra_empresa)  # mesmos critérios, outra empresa: ok
    assert RegraClassificacaoNFe.objects.count() == 2


# ---------------------------------------------------------------------------
# Desativação: fim da vigência em ONTEM (SP), motivo, quem e quando, trilha, 409 na repetição
# ---------------------------------------------------------------------------


def test_desativar_fixa_fim_em_ontem_grava_quem_quando_e_motivo_e_audita(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor, vigencia_inicio=date(2026, 3, 1))
    desativada = cl.desativar_regra(regra, motivo="  regra errada  ", usuario=gestor, agora=AGORA)
    assert desativada.vigencia_fim == date(2026, 3, 19)  # ontem em São Paulo
    assert desativada.desativada_por_id == gestor.pk
    assert desativada.desativada_em == AGORA
    assert desativada.motivo_desativacao == "regra errada"
    assert not desativada.ativa
    assert trilha("classificacao_nfe.regra_desativada").count() == 1


def test_desativar_nunca_alarga_uma_vigencia_que_ja_terminava(escritorio_a, gestor):
    regra = criar(
        escritorio_a, gestor, vigencia_inicio=date(2026, 3, 1), vigencia_fim=date(2026, 3, 5)
    )
    desativada = cl.desativar_regra(regra, motivo="fim", usuario=gestor, agora=AGORA)
    assert desativada.vigencia_fim == date(2026, 3, 5)


def test_regra_criada_e_desativada_no_mesmo_dia_tem_vigencia_vazia(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor, vigencia_inicio=date(2026, 3, 20))
    desativada = cl.desativar_regra(regra, motivo="erro de digitação", usuario=gestor, agora=AGORA)
    assert desativada.vigencia_fim < desativada.vigencia_inicio


def test_desativar_duas_vezes_responde_409_e_nada_muda(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    cl.desativar_regra(regra, motivo="primeira", usuario=gestor, agora=AGORA)
    with pytest.raises(servico.EscrituracaoNFeErro, match="já está desativada"):
        cl.desativar_regra(regra, motivo="segunda", usuario=gestor, agora=AGORA)
    regra.refresh_from_db()
    assert regra.motivo_desativacao == "primeira"
    assert trilha("classificacao_nfe.regra_desativada").count() == 1


def test_desativar_sem_motivo_e_recusado(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    with pytest.raises(servico.EntradaInvalidaNFe, match="motivo"):
        cl.desativar_regra(regra, motivo="   ", usuario=gestor, agora=AGORA)
    regra.refresh_from_db()
    assert regra.ativa


def test_desativar_com_motivo_longo_e_recusado(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    with pytest.raises(servico.EntradaInvalidaNFe, match="máximo"):
        cl.desativar_regra(regra, motivo="x" * 501, usuario=gestor, agora=AGORA)


# ---------------------------------------------------------------------------
# Imutabilidade (critério 4): save(), update() e delete() não alteram a regra
# ---------------------------------------------------------------------------


def test_save_de_regra_existente_e_recusado(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    regra.natureza = "producao_propria"
    with pytest.raises(RegraImutavel):
        regra.save()


def test_update_de_criterio_e_recusado_pelo_gatilho_do_banco(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    with pytest.raises(DatabaseError, match="só pode ser alterada"):
        with transaction.atomic():
            RegraClassificacaoNFe.objects.filter(pk=regra.pk).update(natureza="producao_propria")


def test_update_de_vigencia_sem_desativar_e_recusado_pelo_gatilho(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    with pytest.raises(DatabaseError, match="só pode ser alterada para desativá-la"):
        with transaction.atomic():
            RegraClassificacaoNFe.objects.filter(pk=regra.pk).update(vigencia_fim=date(2026, 4, 1))


def test_delete_e_recusado_pelo_gatilho(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    with pytest.raises(DatabaseError, match="não pode ser excluída"):
        with transaction.atomic():
            RegraClassificacaoNFe.objects.filter(pk=regra.pk).delete()


def test_regra_desativada_nao_muda_nem_pela_desativacao_de_novo(escritorio_a, gestor):
    regra = criar(escritorio_a, gestor)
    cl.desativar_regra(regra, motivo="uma vez", usuario=gestor, agora=AGORA)
    with pytest.raises(DatabaseError, match="já desativada"):
        with transaction.atomic():
            RegraClassificacaoNFe.objects.filter(pk=regra.pk).update(
                desativada_em=AGORA + timedelta(days=1)
            )


# ---------------------------------------------------------------------------
# CHECKs do banco (registradas em apps/core/restricoes.py): gravação direta, sem o serviço
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campos",
    [
        {"tipo": "ajuste"},
        {"cfop": "51x2"},
        {"ncm": "2710", "ncm_modo": ""},
        {"ncm": "2710125", "ncm_modo": "exato"},
        {"ncm": "27101259", "ncm_modo": "prefixo"},
        {"cst_csosn": "5"},
        {"id_dest": "9"},
        {"natureza": "ajuste"},
        {"natureza": ""},
    ],
)
def test_check_do_banco_recusa_linha_fora_do_contrato(escritorio_a, gestor, campos):
    base = {
        "escritorio": escritorio_a,
        "empresa": None,
        "tipo": "saida_propria",
        "cfop": "5102",
        "natureza": "revenda",
        "vigencia_inicio": date(2026, 3, 1),
        "criada_por": gestor,
    }
    base.update(campos)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RegraClassificacaoNFe.objects.bulk_create([RegraClassificacaoNFe(**base)])


def test_check_do_banco_exige_desativacao_completa(escritorio_a, gestor):
    """Desativação sem motivo, ou com quem e quando faltando, é recusada pelo banco."""
    regra = criar(escritorio_a, gestor)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE fiscal_regraclassificacaonfe SET desativada_em = %s WHERE id = %s",
                    [AGORA, regra.pk],
                )


def test_contexto_nao_carrega_regra_de_outro_escritorio(
    escritorio_a, escritorio_b, gestor, empresa, gestor_b_dl087
):
    """Isolamento (critério 4): regra de OUTRO escritório, mesmo do escopo escritório, não entra no
    contexto da empresa daqui; e a regra de empresa de outro escritório também não."""
    from apps.empresas.models import Empresa

    criar(escritorio_a, gestor, cfop="5102")
    criar(escritorio_b, gestor_b_dl087, cfop="5102", natureza="producao_propria")
    de_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B contexto DL087", cnpj="55667788000100"
    )
    cl.criar_regra(
        escritorio=escritorio_b,
        empresa=de_b,
        dados=dados(cfop="5102", natureza="producao_propria"),
        usuario=gestor_b_dl087,
    )
    contexto = cl.contexto_da_empresa(empresa)
    assert [r.escritorio_id for r in contexto.regras] == [escritorio_a.pk]
    assert all(r.empresa_id in (None, empresa.pk) for r in contexto.regras)


@pytest.fixture
def gestor_b_dl087(escritorio_b):
    from apps.fiscal.tests.suporte_dl081 import usuario_com_papel

    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-contexto-dl087")
