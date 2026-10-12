"""DL-085 (frente A), critério 7 e o item 4 do escopo: medida de volume com NFC-e sintéticas.

Roda SÓ com `DL085_MEDIR_VOLUME=1` (são minutos; sem a variável, os testes ficam pulados).
Variáveis:

- `DL085_NOTAS` (padrão 10000): NFC-e do mês, numa empresa. De 1 a 5 itens cada.
- `DL085_TAMANHO_ENVIO` (padrão 2000): arquivos por envio (ZIP) pelo fluxo de recepção (HI-22).
- `DL085_LIMITE` (padrão `LIMITE_PADRAO_DA_PARTE`): notas por parte.

Mede e imprime (use `pytest -s`): a recepção de cada envio; a prévia com as notas ainda não lidas (a
primeira leitura de itens) e depois só lidas; a primeira confirmação; cada parte; a conferência do
mês; a composição da receita; e a apuração do Presumido do trimestre. Afirma que cada parte cabe no
teto de 10 s, e que a soma da receita bate com a soma escrita pelo gerador.

Os números de uma execução estão no relatório da entrega. O teste não fixa tempo como regra: ele
registra e confere o teto com folga.
"""

import io
import os
import time
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal import receita as receita_servico
from apps.fiscal import services
from apps.fiscal.models import EscrituracaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl085 import NCM_COMBUSTIVEL, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

VOLUME = os.environ.get("DL085_MEDIR_VOLUME") == "1"
TETO_POR_CHAMADA_S = 10.0
MES = (2026, 3)

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(not VOLUME, reason="medida de volume: defina DL085_MEDIR_VOLUME=1"),
]


def _xml_da_nfce(numero: int) -> tuple[bytes, Decimal]:
    """NFC-e sintética de 1 a 5 itens. Quase todos de combustível (5656, CSOSN 500); a cada 7 notas,
    o último item é de revenda (5102, CSOSN 102), para haver mais de um grupo. Valores à mão no
    gerador: cada item é um valor fixo, e o vNF é a soma deles."""
    quantidade = 1 + numero % 5
    dets = []
    total = Decimal("0.00")
    for j in range(1, quantidade + 1):
        valor = Decimal(f"{(numero * 37 + j * 101) % 900 + 100}.{(numero + j) % 100:02d}")
        total += valor
        if numero % 7 == 0 and j == quantidade:
            dets.append(xml.det(j, cfop="5102", vprod=str(valor), icms_xml=xml.icms(csosn="102")))
        else:
            dets.append(
                xml.det(
                    j,
                    cfop="5656",
                    vprod=str(valor),
                    ncm=NCM_COMBUSTIVEL,
                    icms_xml=xml.icms(csosn="500"),
                )
            )
    dia = 1 + numero % 28
    hora = numero % 24
    return xml.nfe(
        dets=dets,
        vnf=str(total),
        totais={"vProd": str(total)},
        modelo="65",
        numero=str(numero),
        dh_emi=f"2026-03-{dia:02d}T{hora:02d}:15:00-03:00",
        emitente=("CNPJ", CNPJ_EMITENTE_A),
        destinatario=None,
    ), total


def _envio(escritorio, usuario, inicio: int, quantidade: int) -> tuple[float, Decimal]:
    """Um envio ZIP de `quantidade` NFC-e pelo fluxo de recepção. Devolve (segundos, soma dos
    vNF)."""
    arquivos = {}
    soma = Decimal("0.00")
    for numero in range(inicio, inicio + quantidade):
        conteudo, total = _xml_da_nfce(numero)
        arquivos[f"nfce_{numero:06d}.xml"] = conteudo
        soma += total
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_:
        for nome, conteudo in arquivos.items():
            zip_.writestr(nome, conteudo)
    inicio_medido = time.perf_counter()
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=buffer.getvalue(),
        nome_arquivo="envio-dl085.zip",
    )
    return time.perf_counter() - inicio_medido, soma


def _medir(rotulo: str, funcao, registro: dict):
    inicio = time.perf_counter()
    resultado = funcao()
    duracao = time.perf_counter() - inicio
    registro.setdefault(rotulo, []).append(duracao)
    print(f"[DL-085 volume] {rotulo}: {duracao:.2f} s")
    return resultado


def test_medida_de_volume_do_mes_de_nfce(escritorio_a):
    """Critério 7. Recepção em envios de 2.000 (fluxo real), prévia, partes, conferência, composição
    e apuração do Presumido, num mês de NFC-e numa empresa."""
    notas = int(os.environ.get("DL085_NOTAS", "10000"))
    tamanho_envio = int(os.environ.get("DL085_TAMANHO_ENVIO", "2000"))
    limite = int(os.environ.get("DL085_LIMITE", str(lote.LIMITE_PADRAO_DA_PARTE)))
    usuario = usuario_gestor(escritorio_a, "gestor-volume-dl085")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Volume DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    presumido_servico.definir_criterio(empresa, 2026, "competencia", usuario)
    presumido_servico.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": True},
        usuario,
    )
    registro: dict[str, list[float]] = {}
    soma_geral = Decimal("0.00")

    envios = []
    for inicio in range(1, notas + 1, tamanho_envio):
        quantidade = min(tamanho_envio, notas - inicio + 1)
        segundos, soma = _envio(escritorio_a, usuario, inicio, quantidade)
        envios.append(segundos)
        soma_geral += soma
        print(f"[DL-085 volume] envio de {quantidade} NFC-e: {segundos:.2f} s")

    # 1) A prévia de um mês sem nenhuma leitura: não lê XML, e todas as notas ficam em "a ler".
    previa_sem_leitura = _medir(
        "previa (notas nunca lidas: nao le XML)",
        lambda: lote.previa_do_lote(empresa, *MES),
        registro,
    )
    assert len(previa_sem_leitura.a_ler) == notas
    assert previa_sem_leitura.grupos == ()

    # 2) A leitura em partes, pelo mesmo caminho do endpoint: uma chamada por parte.
    limite_leitura = int(os.environ.get("DL085_LIMITE_LEITURA", str(lote.LIMITE_PADRAO_DA_LEITURA)))
    leitura = None
    while leitura is None or not leitura.terminou:
        leitura = _medir(
            "leitura (parte)",
            lambda: lote.ler_notas_do_mes(empresa, *MES, limite=limite_leitura),
            registro,
        )
        assert not leitura.falhas_nesta_chamada, leitura.falhas_nesta_chamada

    # 3) A prévia com as notas já lidas.
    previa_primeira = _medir(
        "previa (notas ja lidas)",
        lambda: lote.previa_do_lote(empresa, *MES),
        registro,
    )
    assert sum(g.quantidade_notas for g in previa_primeira.grupos) == notas
    assert previa_primeira.fora == () and previa_primeira.a_ler == ()

    primeira = _medir(
        "confirmacao (primeira parte)",
        lambda: lote.confirmar_lote(
            empresa, *MES, previa_primeira.assinatura, {}, usuario, limite=limite
        ),
        registro,
    )
    partes = [primeira]
    while not partes[-1].terminou:
        proxima = _medir(
            "parte",
            lambda: lote.confirmar_lote(
                empresa, None, None, None, None, usuario, limite=limite, lote_id=primeira.lote_id
            ),
            registro,
        )
        partes.append(proxima)
        assert len(partes) < notas, "o lote não terminou"

    progresso = partes[-1]
    assert progresso.efetivadas_total == notas
    assert progresso.falhas_total == 0
    soma_efetivada = sum(
        (e.receita_bruta for e in EscrituracaoNFe.objects.filter(empresa=empresa)),
        Decimal("0.00"),
    )
    assert soma_efetivada == soma_geral

    _medir("conferencia do mes", lambda: servico.conferencia_do_mes(empresa, *MES), registro)
    composicao = _medir(
        "composicao da receita do mes",
        lambda: receita_servico.composicao_do_mes(empresa, *MES),
        registro,
    )
    assert composicao.de("interno").mercadoria == soma_geral
    _medir(
        "apuracao do Presumido (1o trimestre)",
        lambda: presumido_servico.apurar_trimestre(empresa, 2026, 1),
        registro,
    )

    tempos_leitura = registro["leitura (parte)"]
    print(
        f"[DL-085 volume] LEITURA: {len(tempos_leitura)} partes de {limite_leitura} notas; "
        f"min {min(tempos_leitura):.2f} s, max {max(tempos_leitura):.2f} s, "
        f"media {sum(tempos_leitura) / len(tempos_leitura):.2f} s; "
        f"total {sum(tempos_leitura):.1f} s"
    )
    assert max(tempos_leitura) < TETO_POR_CHAMADA_S
    # A maior chamada de confirmação: a primeira (prévia + parte) ou uma parte seguinte.
    chamadas = registro["parte"] + registro["confirmacao (primeira parte)"]
    maior = max(chamadas)
    print(
        f"[DL-085 volume] RESUMO: {notas} NFC-e, envios de {tamanho_envio}, parte de {limite}"
        f"notas, "
        f"{len(chamadas)} chamadas de confirmação; maior chamada {maior:.2f} s "
        f"(teto {TETO_POR_CHAMADA_S:.0f} s); envios {[round(e, 2) for e in envios]}"
    )
    assert maior < TETO_POR_CHAMADA_S
