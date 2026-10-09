"""DL-080, critério 8: NF-e e NFC-e não entram em receita, RBT12, pré-DAS nem ISS.

Método, o mesmo de `test_dl078_nao_contaminacao`: captura os resultados dos cálculos da empresa e as
listas da NFS-e ANTES e DEPOIS de receber NF-e (nota de saída, nota de entrada, NFC-e e eventos,
inclusive um cancelamento). Os dois conjuntos têm de ser iguais.

Uma captura "recusada" não prova nada: duas recusas iguais são igualdade vazia. Por isso cada teste
afirma, antes de comparar, que os cálculos do cenário devolvem resultado ("ok"), e que há NFS-e no
acervo, para a lista não estar vazia.
"""

from decimal import Decimal

import pytest

from apps.fiscal import receita as servico_receita
from apps.fiscal import services
from apps.fiscal.escrituracao import notas_a_escriturar
from apps.fiscal.iss_municipal import (
    apuracao_iss_proprio,
    relatorio_iss_outros_municipios,
    relatorio_iss_retido_sofrido,
)
from apps.fiscal.models import (
    DocumentoFiscal,
    DocumentoNFe,
    EventoFiscal,
    EventoNFe,
    VinculoDocumentoEmpresa,
    VinculoNFeEmpresa,
)
from apps.fiscal.pre_das import pre_das
from apps.fiscal.rbt12 import rbt12
from apps.fiscal.receita import composicao_do_mes
from apps.fiscal.tests.suporte_iss_dl076 import DEVIDO, RETIDO, receber
from apps.fiscal.tests.test_dl075_suporte import (
    atividade_padrao,
    cenario_simples,
    enquadramento_iii_ou_v,
    folha_confirmada,
    folhas_dos_12_meses,
    janela_de_receitas,
)
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DE_FORA,
    CNPJ_DESTINATARIO_A,
    chave_nfe,
    proc_evento_xml,
    xml_nfe,
)
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("relogio_do_teste")]

ANO, MES = 2026, 10
D = Decimal

CALCULOS_DO_SIMPLES = ("composicao", "rbt12", "pre_das", "retido_sofrido", "outros_municipios")


def _capturar(funcao, *args, **kwargs):
    """Resultado do cálculo, ou a recusa dele. Recusa também é resultado a comparar."""
    try:
        return ("ok", funcao(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 — qualquer recusa do cálculo é um resultado
        return ("recusado", type(exc).__name__, str(exc))


def _listas_da_nfse(escritorio, empresa):
    """Tudo o que a NFS-e mostra ou calcula, reduzido a valores comparáveis."""
    return {
        "documentos": list(
            DocumentoFiscal.objects.filter(escritorio=escritorio)
            .order_by("pk")
            .values_list("pk", "identificador", "v_serv")
        ),
        "vinculos": list(
            VinculoDocumentoEmpresa.objects.filter(documento__escritorio=escritorio)
            .order_by("pk")
            .values_list("pk", "empresa_id", "papel")
        ),
        "eventos": list(
            EventoFiscal.objects.filter(escritorio=escritorio)
            .order_by("pk")
            .values_list("pk", "identificador", "codigo")
        ),
        "a_escriturar": [
            (n.vinculo.pk, n.vinculo.papel) for n in notas_a_escriturar(empresa, ANO, MES)
        ],
    }


def _capturas(escritorio, empresa):
    return {
        "composicao": _capturar(composicao_do_mes, empresa, ANO, MES),
        "rbt12": _capturar(rbt12, empresa, ANO, MES),
        "pre_das": _capturar(pre_das, empresa, ANO, MES),
        "apuracao_iss_proprio": _capturar(apuracao_iss_proprio, empresa, ANO, MES),
        "retido_sofrido": _capturar(relatorio_iss_retido_sofrido, empresa, ANO, MES),
        "outros_municipios": _capturar(relatorio_iss_outros_municipios, empresa, ANO, MES),
        "listas_nfse": _listas_da_nfse(escritorio, empresa),
    }


def _afirmar_que_executam(capturas, nomes):
    recusados = {nome: capturas[nome] for nome in nomes if capturas[nome][0] != "ok"}
    assert not recusados, f"cálculo recusado: a igualdade seria vazia: {recusados}"


def _cenario_simples(escritorio, usuario, empresa):
    """Empresa no Simples com atividade padrão, janela de receitas e folhas, NFS-e devida e retida,
    e o mês 10/2026 confirmado. Com isso, RBT12 e pré-DAS têm o que calcular."""
    cenario_simples(empresa)
    atividade_padrao(empresa, usuario, enquadramento_iii_ou_v())
    janela_de_receitas(empresa, usuario, ANO, MES, [D("10000")] * 12)
    folhas_dos_12_meses(empresa, usuario, ANO, MES, [D("3000")] * 12)
    receber(
        escritorio, usuario, 1001, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.00"
    )
    receber(escritorio, usuario, 2001, RETIDO, tp_ret_issqn="2", v_iss_qn="30.00")
    folha_confirmada(empresa, usuario, ANO, MES, remuneracao=D("3000"))
    servico_receita.confirmar_mes(empresa, ANO, MES, usuario)


def _nfes_da_empresa(escritorio, usuario, empresa):
    """NF-e de saída, NF-e de entrada, NFC-e e eventos (cancelamento, carta de correção e órfão),
    todos ligados à empresa do Simples (CNPJ 11222333000181, o de `empresa_a`)."""
    cnpj = CNPJ_PRESTADOR_PADRAO
    assert VinculoNFeEmpresa.objects.filter(empresa=empresa).count() == 0
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfe(
            emitente=("CNPJ", cnpj),
            destinatario=("CNPJ", CNPJ_DESTINATARIO_A),
            totais={"vNF": "5000.00"},
        ),
        nome_arquivo="saida.xml",
    )
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfe(
            emitente=("CNPJ", CNPJ_DE_FORA),
            destinatario=("CNPJ", cnpj),
            numero="2",
            totais={"vNF": "900.00"},
        ),
        nome_arquivo="entrada.xml",
    )
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfe(modelo="65", emitente=("CNPJ", cnpj), destinatario=None, numero="3"),
        nome_arquivo="nfce.xml",
    )
    chave_saida = chave_nfe(emitente=cnpj)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=proc_evento_xml(chave=chave_saida, c_stat="135", autor=("CNPJ", cnpj)),
        nome_arquivo="cancelamento.xml",
    )
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=proc_evento_xml(
            tp_evento="110110", chave=chave_saida, c_stat="135", autor=("CNPJ", cnpj)
        ),
        nome_arquivo="carta.xml",
    )
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=proc_evento_xml(
            chave=chave_nfe(emitente=CNPJ_DE_FORA), c_stat="135", autor=("CNPJ", CNPJ_DE_FORA)
        ),
        nome_arquivo="orfao.xml",
    )


def test_nfe_e_nfce_nao_entram_em_receita_rbt12_pre_das_nem_em_iss(
    escritorio_a, usuario_gestor_a, empresa_a
):
    _cenario_simples(escritorio_a, usuario_gestor_a, empresa_a)
    antes = _capturas(escritorio_a, empresa_a)
    _afirmar_que_executam(antes, CALCULOS_DO_SIMPLES)
    # Sanidade: a NFS-e do cenário está lá. Sem ela, a comparação abaixo seria de listas vazias.
    assert len(antes["listas_nfse"]["documentos"]) == 2
    assert antes["composicao"][1].total("interno") == D("2000.00")

    _nfes_da_empresa(escritorio_a, usuario_gestor_a, empresa_a)
    # A recepção gravou, de fato, as notas e os eventos nas tabelas da NF-e.
    assert DocumentoNFe.objects.filter(escritorio=escritorio_a).count() == 3
    assert VinculoNFeEmpresa.objects.filter(empresa=empresa_a).exists()
    assert EventoNFe.objects.filter(escritorio=escritorio_a).count() == 3

    depois = _capturas(escritorio_a, empresa_a)
    _afirmar_que_executam(depois, CALCULOS_DO_SIMPLES)
    assert depois == antes, {k: (antes[k], depois[k]) for k in antes if antes[k] != depois[k]}


def test_nfe_nao_muda_as_listas_de_nfse_da_empresa(escritorio_a, usuario_gestor_a, empresa_a):
    _cenario_simples(escritorio_a, usuario_gestor_a, empresa_a)
    antes = _listas_da_nfse(escritorio_a, empresa_a)
    _nfes_da_empresa(escritorio_a, usuario_gestor_a, empresa_a)
    depois = _listas_da_nfse(escritorio_a, empresa_a)
    assert depois == antes
    assert len(depois["documentos"]) == 2
    assert all(papel in {"prestador", "tomador"} for (_pk, _empresa, papel) in depois["vinculos"])


def test_evento_de_nfe_nao_aparece_como_evento_de_nfse(escritorio_a, usuario_gestor_a, empresa_a):
    _cenario_simples(escritorio_a, usuario_gestor_a, empresa_a)
    antes = EventoFiscal.objects.filter(escritorio=escritorio_a).count()
    _nfes_da_empresa(escritorio_a, usuario_gestor_a, empresa_a)
    assert EventoFiscal.objects.filter(escritorio=escritorio_a).count() == antes


def test_nfe_nao_cria_vinculo_de_nfse_nem_documento_de_nfse(
    escritorio_a, usuario_gestor_a, empresa_a
):
    _nfes_da_empresa(escritorio_a, usuario_gestor_a, empresa_a)
    assert DocumentoFiscal.objects.count() == 0
    assert VinculoDocumentoEmpresa.objects.count() == 0
    assert DocumentoNFe.objects.count() == 3
    assert not notas_a_escriturar(empresa_a, ANO, MES)
