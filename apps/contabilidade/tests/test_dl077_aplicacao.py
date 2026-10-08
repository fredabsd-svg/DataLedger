"""DL-077, fatia 1 (critérios 3, 4, 7): aplicação do plano — atômica, com trilha.

Prova: nada grava com erro (ponto (b) da mutação); a falha no meio não deixa conta
criada (atomicidade); conta com movimento não muda de tipo nem de natureza; a
aplicação recusa arquivo ou cadastro que mudou desde a prévia; a trilha guarda
quem, quando, SHA-256 do arquivo e contagens. Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio import plano as plano_mod
from apps.contabilidade.intercambio.leitura import ler_arquivo
from apps.contabilidade.intercambio.plano import (
    POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME,
    ArquivoAlteradoDesdeAPrevia,
    PlanoAlteradoDesdeAPrevia,
    PlanoRecusado,
    aplicar_plano,
    conferir_plano,
)
from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

CABECALHO = "codigo;nome;codigo_pai;analitica;tipo;natureza"


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório DL077 Aplicação", cnpj="22222222000122")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL077 Aplicação Ltda", cnpj="22233344000138"
    )


def _proprio(*linhas):
    conteudo = ("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("utf-8")
    return ler_arquivo("proprio", conteudo, nome_arquivo="plano-teste.txt")


PLANO_TRES_NIVEIS = (
    "1;Ativo;;N;ativo;devedora",
    "1.1;Circulante;1;N;ativo;devedora",
    "1.1.1;Caixa;1.1;S;ativo;devedora",
)


def _aplicar(empresa, previa, usuario=None):
    return aplicar_plano(
        empresa,
        previa,
        usuario,
        None,
        sha256_esperado=previa.sha256,
        assinatura_esperada=previa.assinatura,
    )


def test_aplicar_cria_na_ordem_da_superior_com_tipo_natureza_e_pai_certos(empresa):
    previa = conferir_plano(empresa, _proprio(*PLANO_TRES_NIVEIS), "so_acrescentar", {})

    resultado = _aplicar(empresa, previa)

    assert resultado.criadas == 3
    caixa = Conta.objects.get(empresa=empresa, codigo="1.1.1")
    assert (caixa.tipo, caixa.natureza, caixa.aceita_lancamento) == (
        "ativo",
        "devedora",
        True,
    )
    assert caixa.conta_pai.codigo == "1.1"
    assert Conta.objects.get(empresa=empresa, codigo="1").conta_pai is None


def test_aplicar_grava_trilha_do_plano_com_sha_nome_e_contagens(empresa):
    previa = conferir_plano(empresa, _proprio(*PLANO_TRES_NIVEIS), "so_acrescentar", {})

    _aplicar(empresa, previa)

    trilha = RegistroAuditoria.objects.get(acao="plano_de_contas.importado")
    assert trilha.objeto_tipo == "Empresa"
    assert trilha.detalhes["sha256"] == previa.sha256
    assert trilha.detalhes["assinatura"] == previa.assinatura
    assert trilha.detalhes["nome_arquivo"] == "plano-teste.txt"
    assert trilha.detalhes["formato"] == "proprio"
    assert trilha.detalhes["criadas"] == 3
    assert trilha.detalhes["atualizadas"] == 0
    # Cada conta criada também tem a sua linha, como no cadastro comum.
    assert RegistroAuditoria.objects.filter(acao="conta.criada").count() == 3


def test_sha_diferente_do_arquivo_recusa_sem_gravar_nada(empresa):
    previa = conferir_plano(empresa, _proprio(*PLANO_TRES_NIVEIS), "so_acrescentar", {})

    with pytest.raises(ArquivoAlteradoDesdeAPrevia):
        aplicar_plano(
            empresa,
            previa,
            None,
            None,
            sha256_esperado="0" * 64,
            assinatura_esperada=previa.assinatura,
        )

    assert Conta.objects.filter(empresa=empresa).count() == 0


def test_cadastro_que_mudou_desde_a_previa_recusa_sem_gravar(empresa):
    """A prévia viu '1.1' como criação. Depois, outro usuário a cadastrou com tipo
    diferente: a conferência de agora é outra, e a aplicação não grava."""
    previa = conferir_plano(empresa, _proprio(*PLANO_TRES_NIVEIS), "so_acrescentar", {})
    pai = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Circulante",
        tipo=TipoConta.PASSIVO,
        natureza=NaturezaConta.CREDORA,
        conta_pai=pai,
        aceita_lancamento=False,
    )

    with pytest.raises(PlanoAlteradoDesdeAPrevia):
        _aplicar(empresa, previa)

    assert not Conta.objects.filter(empresa=empresa, codigo="1.1.1").exists()


def test_plano_com_erro_nao_grava_nenhuma_conta_nem_as_validas(empresa):
    """Ponto (b) da mutação: um erro impede a gravação do resto. Nada entra."""
    previa = conferir_plano(
        empresa,
        _proprio(
            "1;Ativo;;N;ativo;devedora",
            "1.1;Caixa;1;S;ativo;devedora",
            "2;Receita sem tipo;;S;;",  # sem tipo e sem prefixo: erro
        ),
        "so_acrescentar",
        {},
    )
    assert previa.tem_erro

    with pytest.raises(PlanoRecusado):
        _aplicar(empresa, previa)

    assert Conta.objects.filter(empresa=empresa).count() == 0
    assert not RegistroAuditoria.objects.filter(acao="plano_de_contas.importado").exists()


def test_falha_no_meio_da_aplicacao_desfaz_as_contas_ja_criadas(empresa, monkeypatch):
    """Atomicidade: a primeira conta é criada, a segunda falha, e nenhuma fica."""
    previa = conferir_plano(empresa, _proprio(*PLANO_TRES_NIVEIS), "so_acrescentar", {})
    criar_real = plano_mod.criar_conta_pelo_plano
    chamadas = []

    def criar_que_falha_na_segunda(**kwargs):
        chamadas.append(kwargs["codigo"])
        if len(chamadas) == 2:
            raise RuntimeError("falha simulada no meio da aplicação")
        return criar_real(**kwargs)

    monkeypatch.setattr(plano_mod, "criar_conta_pelo_plano", criar_que_falha_na_segunda)

    with pytest.raises(RuntimeError, match="falha simulada"):
        _aplicar(empresa, previa)

    assert len(chamadas) == 2
    assert Conta.objects.filter(empresa=empresa).count() == 0
    assert not RegistroAuditoria.objects.filter(acao="plano_de_contas.importado").exists()


def test_reaplicar_o_mesmo_arquivo_nao_duplica_nada(empresa):
    """Idempotência: a segunda aplicação não cria duplicata; tudo vira 'sem mudança'."""
    previa = conferir_plano(empresa, _proprio(*PLANO_TRES_NIVEIS), "so_acrescentar", {})
    _aplicar(empresa, previa)

    segunda = conferir_plano(empresa, _proprio(*PLANO_TRES_NIVEIS), "so_acrescentar", {})
    resultado = _aplicar(empresa, segunda)

    assert resultado.criadas == 0
    assert resultado.sem_mudanca == 3
    assert Conta.objects.filter(empresa=empresa).count() == 3


def test_conta_com_movimento_nao_muda_de_tipo_mas_recebe_o_novo_nome(empresa):
    """Critério 4: conta com movimento nunca muda tipo nem natureza. Só o nome muda,
    e só em política 'acrescentar e atualizar nome'."""
    ativo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=ativo,
        aceita_lancamento=True,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
        aceita_lancamento=True,
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2024, 3, 10),
        historico="Aporte",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )

    # Tentativa de trocar o tipo: recusada, nada muda.
    tipo_trocado = conferir_plano(
        empresa,
        _proprio(
            "1;Ativo;;N;ativo;devedora",
            "1.1;Caixa;1;S;passivo;devedora",
        ),
        "acrescentar_e_atualizar_nome",
        {},
    )
    assert tipo_trocado.tem_erro
    with pytest.raises(PlanoRecusado):
        _aplicar(empresa, tipo_trocado)

    # Troca só o nome, em política de atualização de nome: aplica.
    so_nome = conferir_plano(
        empresa,
        _proprio(
            "1;Ativo;;N;ativo;devedora",
            "1.1;Caixa e bancos;1;S;ativo;devedora",
        ),
        POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME,
        {},
    )
    resultado = _aplicar(empresa, so_nome)

    caixa.refresh_from_db()
    assert resultado.atualizadas == 1
    assert caixa.nome == "Caixa e bancos"
    assert (caixa.tipo, caixa.natureza, caixa.aceita_lancamento) == ("ativo", "devedora", True)
    assert caixa.conta_pai_id == ativo.id
    assert ItemLancamento.objects.filter(conta=caixa).count() == 1


def test_conta_do_cadastro_que_nao_esta_no_arquivo_nao_e_apagada(empresa):
    Conta.objects.create(
        empresa=empresa,
        codigo="9",
        nome="Só no cadastro",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=True,
    )
    previa = conferir_plano(empresa, _proprio("1;Ativo;;N;ativo;devedora"), "so_acrescentar", {})

    _aplicar(empresa, previa)

    assert Conta.objects.filter(empresa=empresa, codigo="9").exists()


def test_aplicacao_com_politica_de_nome_registra_nome_anterior_na_trilha(empresa):
    Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa antigo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=True,
    )
    previa = conferir_plano(
        empresa,
        _proprio("1;Caixa novo;;S;ativo;devedora"),
        POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME,
        {},
    )

    _aplicar(empresa, previa)

    renomeio = RegistroAuditoria.objects.get(acao="conta.nome_alterado")
    assert renomeio.detalhes["nome_anterior"] == "Caixa antigo"
    assert Conta.objects.get(empresa=empresa, codigo="1").nome == "Caixa novo"
