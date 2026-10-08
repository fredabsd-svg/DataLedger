"""DL-079, critério 9 (concorrência): duas confirmações de retenção ao mesmo tempo.

A trava é a da EMPRESA (`select_for_update` em `receita.travar_empresa`) e a da própria
confirmação. As duas threads gravam em conexões reais, por isso o teste é transacional (dados
commitados). Ao fim, exatamente UMA confirmação está ativa; a outra foi substituída, e nenhuma
corrida chega como 500.
"""

import threading
from datetime import date

import pytest
from django.db import connection

from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import ConfirmacaoRetencaoPresumido
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada


@pytest.mark.django_db(transaction=True)
def test_duas_confirmacoes_simultaneas_deixam_uma_ativa(empresa_a, usuario_gestor_a, escritorio_a):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    servico.criar_atividade(
        empresa_a,
        {
            "atividade": tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA,
            "inicio": date(2026, 1, 1),
            "padrao": True,
        },
        usuario_gestor_a,
    )
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa_a,
        usuario_gestor_a,
        sufixo=801,
        v_serv="20000.00",
        d_compet="2026-01-10",
        ret_irrf="100.00",
    )
    barreira = threading.Barrier(2)
    erros = []

    def confirmar(valor):
        try:
            barreira.wait(timeout=10)
            servico.confirmar_retencao(
                empresa_a, escrituracao.pk, valor, None, "", usuario_gestor_a
            )
        except Exception as exc:  # o teste reprova qualquer exceção que não seja a da regra
            erros.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=confirmar, args=(v,)) for v in ("100.00", "100.00")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert erros == [], f"corrida não tratada: {erros!r}"
    ativas = ConfirmacaoRetencaoPresumido.objects.filter(escrituracao=escrituracao, estado="ativa")
    substituidas = ConfirmacaoRetencaoPresumido.objects.filter(
        escrituracao=escrituracao, estado="substituida"
    )
    assert ativas.count() == 1
    assert substituidas.count() == 1
