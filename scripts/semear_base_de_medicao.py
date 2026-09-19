"""Base SINTÉTICA de medição — o que sustenta os números de densidade da direção de arte.

**Por que este arquivo existe.** O §4.8 de ``docs/projeto/direcao-de-arte.md``
publica um piso de densidade ("9 linhas no balancete com período filtrado") e
exige que o método venha escrito junto. Até a auditoria de 2026-09-18 o método
vinha — mas a **base** que produz o número morava fora do repositório, no
scratchpad de quem mediu. O achado B2 nomeou o problema: *"a medição que
sustenta o §4.8 não é reproduzível por ninguém além de mim"*, o mesmo defeito
já registrado sobre os HTML dos protótipos do gauntlet.

Medição que só uma pessoa consegue repetir não é medição do projeto. Este
script é a base versionada.

**O que ele cria**, de forma determinística (semente fixa, mesmo resultado
sempre): um escritório, uma empresa, um plano de contas realista de **73 contas
em 4 níveis** e **60 lançamentos** balanceados em março de 2026.

**Nenhum dado real de cliente.** Razão social, CNPJ e históricos são
inventados; os CNPJ são numericamente válidos mas não pertencem a ninguém.

## Como usar

```bash
export DL_SENHA_DA_BASE_DE_MEDICAO='algo que você escolhe agora'
export DL_CONFIRMO_BANCO_DESCARTAVEL='<nome exato do banco>'
python scripts/semear_base_de_medicao.py
```

## As duas travas, e por que elas existem

1. **A senha não está aqui.** Versionar credencial é proibido pelo projeto,
   mesmo a de um usuário sintético — a regra não abre exceção por "é só de
   teste", porque é assim que exceção vira hábito. A senha vem do ambiente e
   o script recusa rodar sem ela.

2. **O nome do banco tem de ser digitado.** Não basta um "sim": a variável
   precisa conter o **nome exato** do banco em uso. Um script que despeja 60
   lançamentos não pode ser executado por engano contra a base de um
   escritório. Confirmação genérica é clicada sem ler; digitar o nome do banco
   exige olhar para ele.

## Quando rodar

**Antes de fechar qualquer etapa que mexa na altura acima da primeira linha de
uma tabela** — faixa nova, bloco de filtro, aviso, título. Foi exatamente esse
tipo de mudança que derrubou a densidade de 9 para 6 linhas na rodada 2 da
DL-026 **sem nenhum teste acusar**: dependeu de alguém desconfiar de uma
captura de tela.

A contagem em si é feita pelo juiz do gauntlet
(``docs/assets/design/gauntlet/juiz.py``), que já sabe contar linha
inteiramente visível. Ele **não** roda na integração contínua, porque exige
Chromium — e essa limitação está declarada, não escondida.
"""

import os
import random
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Rodar `python scripts/semear_base_de_medicao.py` coloca `scripts/` no
# sys.path, não a raiz — sem isto, `config.settings` não é encontrado e a
# mensagem de erro fala de importação, escondendo as travas abaixo. Descoberto
# testando as duas travas, não lendo o código.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import django  # noqa: E402 — precisa vir depois de ajustar o sys.path

SEMENTE = 20260918
"""Semente fixa: a base tem de ser a mesma em qualquer máquina, ou o número
medido aqui não é o número medido lá."""

TOTAL_DE_LANCAMENTOS = 60
COMPETENCIA = (2026, 3)


def _exigir_ambiente():
    """Recusa cedo, com o motivo, em vez de estragar um banco em silêncio."""
    senha = os.environ.get("DL_SENHA_DA_BASE_DE_MEDICAO")
    if not senha:
        sys.exit(
            "Recusado: defina DL_SENHA_DA_BASE_DE_MEDICAO.\n"
            "A senha do usuário sintético NÃO é versionada — credencial em "
            "repositório é proibida neste projeto, e 'é só de teste' não é "
            "exceção, é como a exceção vira hábito."
        )
    return senha


def _exigir_banco_descartavel(nome_do_banco):
    confirmado = os.environ.get("DL_CONFIRMO_BANCO_DESCARTAVEL")
    if confirmado != nome_do_banco:
        sys.exit(
            f"Recusado: este script grava {TOTAL_DE_LANCAMENTOS} lançamentos, e "
            "DL_CONFIRMO_BANCO_DESCARTAVEL não corresponde ao banco em uso.\n"
            "Defina a variável com o nome EXATO do banco que você quer semear.\n"
            "\n"
            "O nome do banco NÃO é repetido aqui de propósito (BL-316): a "
            "mensagem anterior entregava o valor pronto para copiar, enquanto "
            "o comentário afirmava que a trava obrigava a olhar para o banco. "
            "A defesa não era a que o texto descrevia — e comentário que "
            "promete mais do que a defesa entrega é justamente o defeito que "
            "este projeto persegue em todo lugar.\n"
            "\n"
            "Para descobrir o banco em uso, consulte a configuração:\n"
            "  python manage.py shell -c "
            '"from django.conf import settings; '
            "print(settings.DATABASES['default']['NAME'])\""
        )


def _plano_de_contas(natureza, tipo):
    """O plano realista que produz os 4 níveis e as 73 contas do §4.8."""
    d, c = natureza.DEVEDORA, natureza.CREDORA
    a, p, pl, r, de = (
        tipo.ATIVO,
        tipo.PASSIVO,
        tipo.PATRIMONIO_LIQUIDO,
        tipo.RECEITA,
        tipo.DESPESA,
    )
    return [
        ("1", "ATIVO", a, d),
        ("1.1", "ATIVO CIRCULANTE", a, d),
        ("1.1.1", "Disponível", a, d),
        ("1.1.1.01", "Caixa geral", a, d),
        ("1.1.1.02", "Banco do Brasil c/c", a, d),
        ("1.1.1.03", "Itaú c/c", a, d),
        ("1.1.1.04", "Aplicações de liquidez imediata", a, d),
        ("1.1.2", "Créditos a receber", a, d),
        ("1.1.2.01", "Clientes nacionais", a, d),
        ("1.1.2.02", "Duplicatas a receber", a, d),
        ("1.1.2.03", "(-) Perdas estimadas em créditos", a, c),
        ("1.1.2.04", "Adiantamentos a fornecedores", a, d),
        ("1.1.3", "Estoques", a, d),
        ("1.1.3.01", "Mercadorias para revenda", a, d),
        ("1.1.3.02", "Materiais de embalagem", a, d),
        ("1.1.3.03", "Mercadorias em trânsito", a, d),
        ("1.1.4", "Tributos a recuperar", a, d),
        ("1.1.4.01", "ICMS a recuperar", a, d),
        ("1.1.4.02", "PIS a recuperar", a, d),
        ("1.1.4.03", "COFINS a recuperar", a, d),
        ("1.1.4.04", "IRRF a compensar", a, d),
        ("1.2", "ATIVO NÃO CIRCULANTE", a, d),
        ("1.2.1", "Imobilizado", a, d),
        ("1.2.1.01", "Móveis e utensílios", a, d),
        ("1.2.1.02", "Equipamentos de informática", a, d),
        ("1.2.1.03", "Veículos", a, d),
        ("1.2.1.04", "(-) Depreciação acumulada", a, c),
        ("2", "PASSIVO", p, c),
        ("2.1", "PASSIVO CIRCULANTE", p, c),
        ("2.1.1", "Fornecedores", p, c),
        ("2.1.1.01", "Fornecedores nacionais", p, c),
        ("2.1.1.02", "Fornecedores de serviços", p, c),
        ("2.1.2", "Obrigações trabalhistas", p, c),
        ("2.1.2.01", "Salários a pagar", p, c),
        ("2.1.2.02", "INSS a recolher", p, c),
        ("2.1.2.03", "FGTS a recolher", p, c),
        ("2.1.2.04", "Provisão de férias", p, c),
        ("2.1.3", "Obrigações tributárias", p, c),
        ("2.1.3.01", "ICMS a recolher", p, c),
        ("2.1.3.02", "Simples Nacional a recolher", p, c),
        ("2.1.3.03", "ISS a recolher", p, c),
        ("2.2", "PASSIVO NÃO CIRCULANTE", p, c),
        ("2.2.1", "Empréstimos de longo prazo", p, c),
        ("2.2.1.01", "Financiamento de veículos", p, c),
        ("3", "PATRIMÔNIO LÍQUIDO", pl, c),
        ("3.1", "Capital social", pl, c),
        ("3.1.1", "Capital subscrito", pl, c),
        ("3.1.1.01", "Capital integralizado", pl, c),
        ("3.2", "Resultados acumulados", pl, c),
        ("3.2.1", "Lucros acumulados", pl, c),
        ("3.2.1.01", "Lucros de exercícios anteriores", pl, c),
        ("4", "RECEITAS", r, c),
        ("4.1", "Receita operacional bruta", r, c),
        ("4.1.1", "Venda de mercadorias", r, c),
        ("4.1.1.01", "Vendas no mercado interno", r, c),
        ("4.1.1.02", "Vendas a prazo", r, c),
        ("4.2", "Deduções da receita bruta", r, d),
        ("4.2.1", "Impostos sobre vendas", r, d),
        ("4.2.1.01", "ICMS sobre vendas", r, d),
        ("5", "DESPESAS", de, d),
        ("5.1", "Despesas operacionais", de, d),
        ("5.1.1", "Despesas administrativas", de, d),
        ("5.1.1.01", "Aluguel", de, d),
        ("5.1.1.02", "Energia elétrica", de, d),
        ("5.1.1.03", "Telefone e internet", de, d),
        ("5.1.1.04", "Material de escritório", de, d),
        ("5.1.1.05", "Honorários contábeis", de, d),
        ("5.1.2", "Despesas com pessoal", de, d),
        ("5.1.2.01", "Salários e ordenados", de, d),
        ("5.1.2.02", "Encargos sociais", de, d),
        ("5.2", "Custo das mercadorias vendidas", de, d),
        ("5.2.1", "CMV", de, d),
        ("5.2.1.01", "Custo das mercadorias vendidas", de, d),
    ]


def main():
    senha = _exigir_ambiente()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from django.conf import settings
    from django.contrib.auth import get_user_model

    from apps.contabilidade.models import (
        Conta,
        LancamentoContabil,
        NaturezaConta,
        TipoConta,
        TipoPartida,
    )
    from apps.contabilidade.services import criar_lancamento
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    _exigir_banco_descartavel(settings.DATABASES["default"]["NAME"])

    usuario_modelo = get_user_model()
    usuario, _ = usuario_modelo.objects.get_or_create(
        username="medicao", defaults={"is_staff": True, "is_superuser": True}
    )
    usuario.set_password(senha)
    usuario.save()

    escritorio, _ = Escritorio.objects.get_or_create(
        cnpj="11222333000181",
        defaults={"nome": "Escritório Contábil Sintético ME"},
    )
    VinculoUsuarioEscritorio.objects.get_or_create(
        usuario=usuario,
        escritorio=escritorio,
        # BL-316: era `Papel.values[0]` — o papel dependia da ORDEM DE
        # DECLARAÇÃO do enum. Se ela mudasse, a base passaria a medir as telas
        # sob outro papel, e `cliente` recebe 403 em quase tudo: a medição
        # mudaria sem ninguém tocar na medição. Nomeado.
        defaults={"papel": Papel.ADMINISTRADOR},
    )
    empresa, _ = Empresa.objects.get_or_create(
        cnpj="44555666000199",
        defaults={
            "escritorio": escritorio,
            "razao_social": "Comércio Sintético de Materiais Ltda",
        },
    )

    plano = _plano_de_contas(NaturezaConta, TipoConta)
    criadas = {}
    for codigo, nome, tipo, natureza in plano:
        pai = criadas.get(codigo.rsplit(".", 1)[0]) if "." in codigo else None
        # Analítica é a folha do plano: 4 segmentos, isto é, 3 pontos.
        analitica = codigo.count(".") == 3
        conta, _ = Conta.objects.get_or_create(
            empresa=empresa,
            codigo=codigo,
            defaults={
                "conta_pai": pai,
                "nome": nome,
                "tipo": tipo,
                "natureza": natureza,
                "aceita_lancamento": analitica,
            },
        )
        criadas[codigo] = conta

    analiticas = [c for c in criadas.values() if c.aceita_lancamento]
    sorteio = random.Random(SEMENTE)
    ano, mes = COMPETENCIA
    # BL-316: "gravados" contava CHAMADAS, não escritas. Rodando duas vezes no
    # mesmo banco, a segunda execução gravava zero e relatava 60 — porque a
    # idempotência devolve o lançamento existente sem erro. Um instrumento
    # criado para fechar um achado de honestidade de medição não pode relatar
    # escrita que não houve. Agora o número vem da contagem real no banco.
    antes = LancamentoContabil.objects.filter(empresa=empresa).count()
    reaproveitados = 0
    recusados = []
    for i in range(TOTAL_DE_LANCAMENTOS):
        debitada, creditada = sorteio.sample(analiticas, 2)
        valor = Decimal(sorteio.randrange(1000, 900000)) / 100
        try:
            criar_lancamento(
                empresa=empresa,
                data=date(ano, mes, 1 + i % 28),
                historico=f"Lançamento sintético {i + 1:02d}",
                itens=[
                    {"conta": debitada, "tipo": TipoPartida.DEBITO, "valor": valor},
                    {"conta": creditada, "tipo": TipoPartida.CREDITO, "valor": valor},
                ],
                criado_por=usuario,
                # Idempotência: rodar de novo não duplica a base.
                chave_idempotencia=f"base-de-medicao-{i}",
            )
        except Exception as erro:  # noqa: BLE001 — o motivo é impresso, não engolido
            recusados.append(f"{i}: {erro}")

    depois = LancamentoContabil.objects.filter(empresa=empresa).count()
    gravados = depois - antes
    reaproveitados = TOTAL_DE_LANCAMENTOS - gravados - len(recusados)

    contas = Conta.objects.filter(empresa=empresa).count()
    niveis = max(codigo.count(".") for codigo, *_ in plano) + 1
    print(f"contas: {contas}  níveis: {niveis}")
    print(f"lançamentos no banco: {depois}  empresa_id: {empresa.id}  usuário: medicao")
    print(f"  gravados agora: {gravados}")
    if reaproveitados:
        # Repetição idempotente: NÃO é recusa, e não cai na lista abaixo —
        # `criar_lancamento` devolve o existente sem erro. Dizer isto em linha
        # própria é o que impede o relatório de contar como escrita o que foi
        # reaproveitamento.
        print(f"  reaproveitados por idempotência: {reaproveitados}")
    if recusados:
        # Falha visível: recusa aparece, não fica escondida num contador.
        print(f"  recusados ({len(recusados)}):")
        for linha in recusados:
            print(f"    {linha}")


if __name__ == "__main__":
    main()
