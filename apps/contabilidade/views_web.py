"""Telas da contabilidade (DL-017, fase B).

DE-026: estas views NUNCA chamam a própria API — chamam os serviços de
`apps.contabilidade.services` diretamente e renderizam HTML no servidor. A
autorização de LEITURA vem de uma função só, compartilhada com a API
(`apps.contabilidade.permissoes.papel_pode_ler_contabilidade` — ver o
docstring daquele módulo para o contrato completo); a autorização de
ESCRITA (criar conta, lançar) reaproveita a MESMA classe de permissão que a
API já usa para escrever (`apps.contabilidade.views.PodeEscriturar`), por
indicação explícita do docstring de `permissoes.py`: não existe uma segunda
lista de papéis "só para a tela" em lugar nenhum deste arquivo.

Cada view revalida a empresa pedida contra `request.escritorio` (o
escritório ATIVO da sessão, resolvido pelo `EscritorioAtivoMiddleware` —
nunca um `empresa_id` cru): uma empresa de outro escritório sempre dá 404,
nunca dado (critério 2 do plano DL-017).

Formatação é apresentação: todo valor monetário permanece `Decimal` até o
último instante, convertido para texto pt-BR só pelas funções `_valor_ptbr`/
`_indicador_natureza` deste módulo — nunca um `float` em ponto nenhum
(AGENTS.md, seção 10; riscos do plano DL-017).
"""

import hashlib
import re
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

# BL-217/A1 (auditoria DL-020 rodada 1): cada view de função deste módulo
# DECLARA os métodos HTTP que aceita. Não é decoração cosmética — é o fato do
# objeto que a varredura de contratos lê para saber se a view é superfície de
# escrita. A classificação anterior era TEXTUAL (`"request.method" in fonte`)
# e o auditor a contornou com uma view que grava lendo `json.loads(request.
# body)` sob `@require_POST`: suíte inteira verde, lint limpo, gravação sem
# contrato. Uma view de função alcançável pelo urlconf e SEM esta declaração
# reprova a varredura — não existe mais o caminho "não consegui classificar,
# então não é escrita".
from django.utils.formats import date_format
from django.views.decorators.http import require_http_methods, require_safe

from apps.auditoria.services import registrar
from apps.contabilidade.intercambio import importacao_lancamentos as importacao_servico
from apps.contabilidade.intercambio.canonico import (
    LADO_DEBITO,
    NIVEL_AVISO,
    NIVEL_ERRO,
    IntercambioRecusado,
)
from apps.contabilidade.intercambio.formatos import (
    LEITORES,
    ecd,
    excel,
    excel_lancamentos,
    proprio,
    referencia,
)
from apps.contabilidade.intercambio.lancamentos import exportar_lancamentos
from apps.contabilidade.intercambio.leitura import TAMANHO_MAXIMO_ARQUIVO_BYTES, ler_arquivo
from apps.contabilidade.intercambio.plano import (
    ACAO_ATUALIZAR,
    ACAO_CRIAR,
    ACAO_RECUSADA,
    ACAO_SEM_MUDANCA,
    ORIGEM_ARQUIVO,
    ORIGEM_CADASTRO,
    ORIGEM_CONTA_SUPERIOR,
    ORIGEM_PREFIXO,
    ORIGEM_PRESUMIDA,
    POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME,
    POLITICA_SO_ACRESCENTAR,
    POLITICAS,
    ArquivoAlteradoDesdeAPrevia,
    ParametroInvalido,
    PlanoAlteradoDesdeAPrevia,
    PlanoRecusado,
    aplicar_plano,
    conferir_plano,
    exportar_plano,
    validar_prefixos,
)
from apps.contabilidade.models import (
    # DL-061/CTB-14: coluna da DMPL (NBC TG 51, item 111A) — quarto campo do
    # mesmo padrão. Usada pela tela `dmpl` e pela tela de classificar conta
    # (`conta_classificacao_dmpl`, opções agrupadas pelo grupo do 111A).
    GRUPO_DA_CLASSIFICACAO_DMPL,
    GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL,
    # DL-062 (BL-604): a MESMA declaração que `apurar_saldos` usa para
    # somar o total, usada aqui para apresentar o subtotal — uma fonte de
    # verdade só para o sinal de um tipo (achado A5 da auditoria).
    NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO,
    TIPO_DA_CLASSIFICACAO_PATRIMONIAL,
    # DL-048/CTB-12: linha da DLPA (art. 186) — terceiro campo do mesmo
    # padrão. Usado pela tela `dlpa` (rótulos das linhas e do formulário),
    # pela tela de classificar conta e pela humanização das pendências.
    ClassificacaoDlpa,
    ClassificacaoDmpl,
    # DL-045, fatia 3: linha da DRE (art. 187) — mesmo desenho de
    # `ClassificacaoPatrimonial`, logo abaixo. Usada pela tela da DRE
    # (`dre`/`_montar_linhas_da_dre`, mais abaixo) e pelo formulário de
    # conta (`ContaCriarForm`, campo "Linha da DRE" e a humanização das
    # pendências de classificação nas listas do veto).
    ClassificacaoDre,
    # DL-066/CTB-15: atividade do fluxo de caixa da conta (CPC 03, itens 10 e
    # 13 a 17) — o campo do meio da classificação da DFC
    # (`conta_classificacao_dfc`, opções do formulário) e os rótulos das
    # três atividades na tela da própria DFC.
    ClassificacaoFluxoCaixa,
    # DL-034: os cinco nomes abaixo (ClassificacaoPatrimonial, GrupoDaLei,
    # GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL, TIPO_DA_CLASSIFICACAO_
    # PATRIMONIAL, TipoConta) servem só a tela do Balanço — ver
    # `_montar_grupos_do_balanco`/`balanco`, mais abaixo. Nenhum é
    # redeclarado: são os MESMOS enums e os MESMOS mapas que `apurar_saldos`
    # (services.py, DL-032/DL-033) já usa para montar `totais_por_grupo`/
    # `totais_por_classificacao` — a tela só precisa deles para saber COMO
    # REPARTIR essas duas chaves em seções impressas (quatro subgrupos do
    # Ativo Não Circulante, título de cada grupo), nunca para recalcular
    # nada que o servidor já apurou.
    ClassificacaoPatrimonial,
    Competencia,
    Conta,
    EstadoCompetencia,
    EstadoImportacaoLancamentos,
    FormatoImportacaoLancamentos,
    GrupoDaDmpl,
    GrupoDaLei,
    # DL-077, fatia 3 (frente B): a importação de lançamentos com área de conferência. A tela
    # LÊ a importação e os lançamentos conferidos; quem grava é sempre o serviço
    # (`apps.contabilidade.intercambio.importacao_lancamentos`).
    ImportacaoLancamentos,
    LancamentoContabil,
    # DL-061, fatia 2 (BL-605): a marcação manual da DMPL guardada FORA do
    # livro (E15). A tela lê o conjunto atual para mostrá-lo na guia do
    # lançamento; quem GRAVA é sempre o serviço
    # (`salvar_marcacoes_da_dmpl`/`remover_marcacoes_da_dmpl`).
    MarcacaoDmpl,
    NaturezaConta,
    # DL-043 fatia 3: modelo e enum do parâmetro contábil (fatia 1) — a
    # tela LÊ `ParametroContabilEmpresa` diretamente (mesmo padrão de
    # `Competencia` acima, já lida direto por `fechamento`), e usa o enum
    # só para os `choices` do formulário de nova vigência. Nenhuma
    # validação de negócio mora aqui: quem valida é sempre o serviço
    # (`registrar_parametro_contabil`) — ver o docstring do próprio
    # modelo, em models.py, sobre por que ele não tem `clean()`.
    OrigemLancamento,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.permissoes import papel_pode_ler_contabilidade

# RC-77 (faixa de data) e RC-79 (teto de partidas) vêm de
# `apps.contabilidade.services` e NÃO são redeclarados aqui — nem a data
# mínima, nem os 30 dias, nem o 200. Declarar o mesmo número em dois
# arquivos é como o estado do projeto divergiu três vezes; e a recusa de
# verdade é do servidor (`criar_lancamento`), não desta tela. O que esta
# tela faz com eles é CONVENIÊNCIA: `min`/`max` no campo de data (DE-031 —
# o seletor nativo continua sendo o do navegador) e o teto de linhas do
# formulário. `data_maxima_lancamento` é FUNÇÃO porque "hoje + N dias" se
# move: congelá-la num import daria um formulário com teto de ontem.
from apps.contabilidade.services import (
    # DL-061: as linhas de EVENTO da DMPL (as que uma marcação pode ocupar)
    # e os títulos humanos das linhas — fonte ÚNICA no serviço, para os
    # `<select>` da guia não divergirem do documento.
    _LINHAS_DE_EVENTO_DA_DMPL,
    _TITULOS_DAS_LINHAS_DA_DMPL,
    # DL-061: títulos humanos de cada lista de pendência da DMPL — fonte
    # ÚNICA no serviço (a tela só acrescenta a AÇÃO que resolve); uma cópia
    # escrita aqui divergiria na primeira edição.
    # DL-066/CTB-15: mesma fonte única para os títulos das pendências da DFC.
    _TITULOS_DAS_PENDENCIAS_DA_DFC,
    _TITULOS_DAS_PENDENCIAS_DA_DMPL,
    DATA_MINIMA_LANCAMENTO,
    LIMITE_PARTIDAS_POR_LANCAMENTO,
    ChaveIdempotenciaConflitante,
    ClassificacaoAlteraPeriodoFechado,
    CompetenciaEncerrada,
    CompetenciaJaEntregue,
    CompetenciaOperacaoInvalida,
    CompetenciaOperacaoRecusada,
    HierarquiaInconsistente,
    LancamentoInvalido,
    # DL-061, fatia 2 (BL-605): a recusa do SERVIÇO sobre o conjunto de
    # marcações (E16/E17) — a tela a traduz para erro de formulário, nunca
    # para 500 (mesmo molde de `classificar_conta_na_dmpl`).
    MarcacaoDmplInvalida,
    # DL-043 fatia 3 (BL-474): as quatro portas de serviço da fatia 1
    # (vigência) e da fatia 2 (zeramento) — esta tela chama SÓ estas
    # funções e SÓ traduz as duas exceções abaixo para mensagem em
    # português, nunca reimplementa a validação (mesmo padrão de
    # `encerrar_competencia`/`reabrir_competencia`, já usados aqui).
    ParametroContabilInvalido,
    VigenciaParametroContabilConflitante,
    # DL-061, fatia 2 (BL-605): a guia "DMPL" do lançamento precisa mostrar
    # o EFEITO POR COLUNA exatamente como o serviço o calcula — é contra o
    # MESMO `movimento` que `salvar_marcacoes_da_dmpl` compara o Σ do
    # conjunto (E16), e uma segunda cópia do cálculo aqui mostraria um
    # número que não é o que decide a gravação. Por isso são reaproveitadas
    # as MESMAS funções de leitura que o serviço usa
    # (`_colunas_de_cada_conta` + `_atribuir_lancamento_as_linhas_da_dmpl`).
    _atribuir_lancamento_as_linhas_da_dmpl,
    _colunas_de_cada_conta,
    apurar_balancete,
    apurar_balanco_patrimonial,
    # DL-045 fatia 3: a mesma dupla apurar/avaliar que o Balanço já usa
    # (`apurar_balanco_patrimonial`/dentro dela; `avaliar_emissao_do_
    # balanco`, ver `balanco`/`_montar_grupos_do_balanco` mais abaixo),
    # agora para a DRE. `apurar_dre` passou a pagar o mesmo snapshot
    # REPEATABLE READ que `apurar_balanco_patrimonial` paga (A5, rodada 1
    # de auditoria da DL-045) — nada para esta tela fazer a respeito.
    # DL-066/CTB-15: apuração da DFC — mesmo contrato de snapshot e de
    # "quem chama verifica permissão" das irmãs abaixo.
    apurar_dfc,
    # DL-048/CTB-13: apuração da DLPA — mesma família de nome da DRE,
    # mesmo contrato de snapshot e de "quem chama verifica permissão".
    apurar_dlpa,
    # DL-061/CTB-14: apuração da DMPL — mesmo contrato de snapshot e de
    # "quem chama verifica permissão" da DLPA.
    apurar_dmpl,
    apurar_dre,
    apurar_razao,
    # DL-066: decisão de emissão da DFC, no servidor (a tela só obedece).
    avaliar_emissao_da_dfc,
    # DL-048: decisão de emissão da DLPA, no servidor (a tela só obedece).
    avaliar_emissao_da_dlpa,
    # DL-061: decisão de emissão da DMPL, no servidor (a tela só obedece).
    avaliar_emissao_da_dmpl,
    avaliar_emissao_da_dre,
    avaliar_emissao_do_balancete,
    # DL-045, correção da rodada 1 de auditoria (A7): a porta de serviço
    # que classifica (ou reclassifica, ou remove a classificação de) a
    # linha da DRE de uma conta EXISTENTE — mesma função que a API chama
    # (`ContaClassificacaoDreView`), nunca uma segunda cópia da regra
    # (todas as guardas moram em `Conta.clean()`). Ver `conta_
    # classificacao_dre`, mais abaixo.
    # DL-066/CTB-15: porta ÚNICA de gravação dos TRÊS campos da DFC de uma
    # conta existente — mesmo desenho das irmãs abaixo (guarda em
    # `Conta.clean()` + trilha na MESMA transação + recusa de período
    # fechado em `ClassificacaoAlteraPeriodoFechado`).
    classificar_conta_na_dfc,
    # DL-048/CTB-12: porta ÚNICA de gravação da classificação da DLPA —
    # mesmo desenho de `classificar_conta_na_dre` (guarda em
    # `Conta.clean()` + trilha na MESMA transação), nunca uma segunda cópia.
    classificar_conta_na_dlpa,
    # DL-061: porta ÚNICA de gravação da coluna da DMPL (guarda em
    # `Conta.clean()` + trilha na MESMA transação).
    classificar_conta_na_dmpl,
    classificar_conta_na_dre,
    criar_lancamento,
    data_maxima_lancamento,
    # DL-061: marca de adoção antecipada da NBC TG 51 (com trilha) — a tela
    # de parâmetros contábeis só chama, nunca grava a marca por conta própria.
    definir_adocao_antecipada_da_nbc_tg_51,
    encerrar_competencia,
    encerrar_vigencia_de_parametro_contabil,
    # DL-045 fatia 3: função PURA (sem consulta) que devolve o bloco de
    # identificação NBC TG 26 item 51 — mesma que `apurar_balanco_
    # patrimonial` já embute no próprio retorno (`resultado["identificacao"]`
    # em `balanco`). `apurar_dre` NÃO a embute (ver o comentário acima), então
    # a tela da DRE chama esta função DIRETO — chamada segura e sem estado,
    # nunca uma segunda cópia do dict que ela devolve.
    identificacao_da_demonstracao,
    listar_diario,
    localizar_contas_que_aceitam_lancamento_e_tem_subordinadas,
    localizar_contas_sinteticas_com_movimento,
    localizar_inconsistencias_de_hierarquia,
    localizar_lancamentos_com_data_fora_da_faixa,
    localizar_lotes_desbalanceados,
    marcar_competencia_como_entregue,
    # DL-045, correção da rodada 1 de auditoria (A7): extrai as mensagens
    # de um `django.core.exceptions.ValidationError` como lista PLANA de
    # `str` — usada por `conta_classificacao_dre` para traduzir a recusa
    # de `classificar_conta_na_dre` em `form.add_error(None, ...)`, MESMA
    # função que a API usa para o corpo 400 do DRF.
    mensagens_da_validacao_django,
    movimento_fora_do_periodo,
    pre_visualizar_zeramento,
    reabrir_competencia,
    registrar_parametro_contabil,
    # DL-061, fatia 2 (BL-605): as DUAS portas de gravação da marcação
    # manual — o CONJUNTO é gravado de uma vez (substituição atômica com
    # trilha) e limpo pelo botão "Remover marcações". A tela só chama,
    # nunca reimplementa regra (E15–E17 moram no serviço).
    remover_marcacoes_da_dmpl,
    rotulo_e_inscricao_da_empresa,
    salvar_marcacoes_da_dmpl,
    zerar_resultado,
)

# Reaproveitados de apps.contabilidade.views (API), de propósito, para não
# existir uma segunda cópia de nenhuma das regras a seguir:
# - PodeEscriturar: MESMA permissão de escrita que a API usa (indicação
#   explícita do docstring de permissoes.py — a tela de lançamento "usa a
#   regra de PodeEscriturar em views.py").
# - _saldo_absoluto_com_natureza: a conversão saldo-assinado -> (valor
#   absoluto, letra D/C) é uma regra sutil (RC-61: saldo zero não tem lado;
#   o sinal pode inverter a natureza APURADA em relação à CADASTRADA — ver o
#   docstring de origem) — exatamente o tipo de decisão que DE-026 não quer
#   duplicada em dois lugares.
# - TAMANHO_MAXIMO_HISTORICO e LIMITE_MAGNITUDE_VALOR: mesmos limites do
#   modelo (achado 1/4 da auditoria da DL-017, rodada 1) que a API já
#   verifica na fronteira ANTES de gravar — sem eles aqui, o mesmo texto
#   longo demais ou o mesmo valor grande demais que a API recusa com 400
#   chega ao INSERT do Postgres pela tela e vira 500 (`DataError`), porque
#   `criar_lancamento` (services.py) não os verifica: ele confia que quem
#   chama (API ou tela) já filtrou a entrada bruta do usuário.
# - _PADRAO_NIVEL_SIMPLES: MESMO padrão `^[0-9]+$` (não `\d`, que casaria
#   QUALQUER dígito Unicode) que a API usa para validar 'nivel' — achado
#   R2-2 da rodada 2: esta tela tinha uma cópia frouxa (`bruto.isdigit()`)
#   que aceitava dígito índico-arábico/fullwidth em silêncio. Usado só por
#   `_inteiro_de_cliente` abaixo, que preserva a MAGNITUDE de um texto
#   grande demais (ver o docstring dela para o porquê disso importar).
# - PodeFecharCompetencia (DL-016 fatia 1 / DL-031 fatia 2): MESMA permissão
#   (ADMINISTRADOR/GESTOR, RC-102) que a API já usa para fechar/reabrir/
#   entregar competência — reaproveitada aqui pelo mesmo motivo de
#   PodeEscriturar: não existe uma segunda lista de papéis "só para a tela".
from apps.contabilidade.views import (
    _FORMATOS_EM_ISO_8859_1,
    _PADRAO_NIVEL_SIMPLES,
    CAMPOS_QUERYSTRING_EXPORTACAO_PLANO,
    LIMITE_MAGNITUDE_VALOR,
    TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA,
    TAMANHO_MAXIMO_HISTORICO,
    TIPO_DE_CONTEUDO_XLSX,
    PodeEscriturar,
    PodeFecharCompetencia,
    _nome_do_arquivo_exportado,
    _saldo_absoluto_com_natureza,
)

# DataInvalida/para_data: o julgador único de "isto é uma DATA de cliente
# válida?" (BL-133, achado A9 da rodada 4). Esta tela tinha uma cópia
# PRÓPRIA (`_PADRAO_DATA_SIMPLES` + `date.fromisoformat` cru) cujo
# comentário original citava `apps.contabilidade.views._PADRAO_DATA_
# SIMPLES` como referência — símbolo que a própria BL-133 REMOVEU ao
# criar este módulo (R5-4/BL-143, rodada 5: a divergência já estava
# impressa no comentário, e três mutantes na gramática de data desta tela
# sobreviviam a 683 testes porque nada a defendia). `inicio`/`fim`
# (`_periodo_do_formulario`) e `data` do lançamento (`lancamento_novo`)
# usam `para_data` agora — a cópia privada não existe mais.
from apps.core.datas import DataInvalida, para_data
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal

# IdentificadorInvalido/para_id: o julgador único de "isto é um
# IDENTIFICADOR de banco válido?" (BL-127, achado A2 da rodada 4— e o
# gêmeo achado no mesmo módulo, `EscritorioAtivoView.post`, ao aplicar a
# lição pelo EFEITO em vez de pela linha nomeada, DE-032). `conta_id`
# (`_itens_e_totais`, abaixo) É um identificador de banco — a mesma
# invariante que `para_id` já julga para `apps.tenancy` (BL-127) **e para
# a API de contabilidade** (`apps.contabilidade.views._extrair_itens`,
# R5-3/BL-142, corrigido pelo `desenvolvedor-pleno` na mesma rodada em
# que este comentário foi revisado). BL-146: uma versão ANTERIOR deste
# comentário já afirmava "a API já usa" quando ainda não usava — foi
# exatamente essa frase que impediu de checar. Não editar esta afirmação
# sem rodar `test_comentario_sobre_julgador_partilhado_so_afirma_o_que_e_
# verificavel` (test_dl017_rodada5_frontend.py), que confere o texto
# contra `inspect.getsource(apps.contabilidade.views)` — a mesma classe
# de proteção que esta nota descreve, aplicada a si própria. Esta tela
# usa `_identificador_de_cliente` (abaixo), que delega a `para_id`, em
# vez de reimplementar o padrão e o teto de magnitude aqui.
# Isto é DIFERENTE de `_inteiro_de_cliente`: nível de hierarquia e número
# de linhas não são identificadores, são QUANTIDADES onde a regra de
# negócio local precisa ver a magnitude real de um texto grande demais
# para poder recusá-lo com uma mensagem própria (ver R3-1/BL-115 no
# docstring de `_inteiro_de_cliente`) — por isso continuam com o julgador
# PRÓPRIO desta tela, não com o teto genérico de `para_id`.
from apps.core.identificadores import IdentificadorInvalido, para_id

# BL-196/R6-2: a política dos cinco dicionários de uma requisição mora em
# `apps.core.requisicao` — UM lugar, como `dinheiro`, `datas`, `escolhas`,
# `identificadores` e `restricoes`. Esta tela tinha a política escrita à mão
# em `lancamento_novo` (três `if` seguidos) e NADA em `conta_nova`, a 40
# linhas de distância no mesmo arquivo: enviar `conta_pai` como ARQUIVO
# gravava a conta na RAIZ do plano com 302 de sucesso. Aqui ficam só as
# DECLARAÇÕES do que cada tela aceita e a RESPOSTA de tela (re-renderizar o
# formulário com 400 e tudo o que o usuário digitou); o julgamento é do
# módulo.
from apps.core.requisicao import (
    DICIONARIO_ARQUIVO,
    DICIONARIO_CABECALHO,
    DICIONARIO_QUERYSTRING,
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_campos_nao_contratados,
    recusar_dado_nao_contratado,
)
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaEmModoLivroCaixa, recusar_se_livro_caixa

# Mesmo teto de NÍVEL que a API aplica em `apps.contabilidade.views.NIVEL_
# MAXIMO` — valor repetido aqui (não importado) porque é só uma guarda de
# boa educação na fronteira HTTP desta tela (nenhum plano de contas real
# chega a esta profundidade), não uma regra de negócio contábil.
NIVEL_MAXIMO = 50

# Teto de indentação VISUAL do Plano de Contas e do Balancete (achado 6 da
# auditoria da DL-017, rodada 1): a coluna "Nível" sempre mostra o número
# REAL, então limitar a indentação a 10 níveis não esconde informação —
# nenhum plano de contas real chega lá (ver
# docs/projeto/mapa-funcional-contabil.md). Usada para escolher a classe
# CSS "nivel-N" (static/css/base.css), NUNCA um atributo `style` inline:
# o defeito original era exatamente `(nivel - 1) * 1.25`, um `float` que o
# `LANGUAGE_CODE = "pt-br"` localizava para `padding-left: 1,25rem` — CSS
# inválido, sem indentação nenhuma em nenhum nível, e sem nenhum teste ou
# erro acusando (AGENTS.md §10: nunca `float`, inclusive onde o número não
# é dinheiro).
NIVEL_INDENTACAO_MAXIMA = 10

LINHAS_INICIAIS_LANCAMENTO = 4

# RC-79/BL-207 — teto de partidas por lançamento, confirmado pelo Fred em
# 2026-09-15: **200**, com recusa explícita e NUNCA truncamento. O número
# não mora aqui: é `LIMITE_PARTIDAS_POR_LANCAMENTO`, de
# `apps.contabilidade.services`, que é quem recusa de verdade — para a tela
# e para a API ao mesmo tempo. Esta constante continua existindo com nome
# próprio porque o que ela significa NESTE arquivo é "quantas linhas o
# formulário oferece e re-exibe no máximo", e é assim que os comentários de
# R2-3/R3-2/R3-9 abaixo se referem a ela; o VALOR é um só.
LINHAS_MAXIMAS_LANCAMENTO = LIMITE_PARTIDAS_POR_LANCAMENTO


# ---------------------------------------------------------------------------
# Formatação de apresentação (critérios 4 e 5) — nunca usada para cálculo.
# ---------------------------------------------------------------------------


def _milhar_ptbr(parte_inteira):
    """Insere '.' a cada três dígitos na parte inteira (texto), preservando
    o sinal. Opera sobre STRING, não sobre número — evita qualquer resíduo
    de ponto flutuante ou dependência de locale do interpretador.
    """
    negativo = parte_inteira.startswith("-")
    digitos = parte_inteira[1:] if negativo else parte_inteira
    grupos = []
    while len(digitos) > 3:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    grupos.insert(0, digitos)
    resultado = ".".join(grupos)
    return f"-{resultado}" if negativo else resultado


def _valor_ptbr(valor):
    """Formata um Decimal monetário em pt-BR: '.' de milhar, ',' decimal,
    sempre duas casas (critério 4: `1234567.89` -> `1.234.567,89`).

    `Decimal(valor).quantize(Decimal("0.01"))` antes de qualquer formatação
    (mesmo motivo do `_como_moeda` de apps.contabilidade.views: SQLite, usado
    em desenvolvimento local, não preserva a escala de um DecimalField em
    agregações `Sum` como o PostgreSQL faz).

    Não usa o filtro `intcomma` do Django: `django.contrib.humanize` não
    está em INSTALLED_APPS, e esta etapa não tem permissão para alterar
    `config/settings.py` (arquivo do arquiteto-senior). Também não usa uma
    template tag própria, pelo mesmo motivo que impede isto em
    `apps.empresas.views._mascara_cnpj`: nenhuma permissão, nesta etapa,
    para criar `apps/contabilidade/templatetags/`. Formatação pura de
    apresentação — o valor segue `Decimal` até aqui.
    """
    quantizado = Decimal(valor).quantize(Decimal("0.01"))
    texto = str(quantizado)
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:]
    parte_inteira, parte_decimal = texto.split(".")
    resultado = f"{_milhar_ptbr(parte_inteira)},{parte_decimal}"
    return f"-{resultado}" if negativo else resultado


def _indicador_natureza(letra):
    """Empacota a letra D/C (RC-61) com o texto por extenso, para o
    template anunciar "D (devedor)"/"C (credor)" — nunca só a letra, e
    nunca só cor (critério 14). `None` quando o saldo é zero: RC-61 diz que
    zero não tem lado, e não existe letra "certa" para inventar aqui.
    """
    if letra is None:
        return None
    return {"letra": letra, "extenso": "devedor" if letra == "D" else "credor"}


# ---------------------------------------------------------------------------
# Isolamento e permissão (critérios 1, 2 e 3)
# ---------------------------------------------------------------------------


def _empresa_do_escritorio_ativo(request, empresa_id):
    """Resolve a empresa da URL, sempre restrita ao escritório ATIVO da
    sessão (critério 2) — nunca por um `empresa_id` cru. Mesma regra de
    isolamento de `apps.empresas.mixins.EmpresaEscopadaMixin` (já usada
    pela API): uma empresa de outro escritório dá 404, não 403 — não
    confirma nem a existência do registro para quem não tem acesso.

    DL-038 (R5): memorizada por REQUISIÇÃO (não entre requisições — o cache
    vive só no objeto `request`, que é novo a cada chamada). Desde que o
    decorador `_sem_contabilidade_para_livro_caixa` passou a resolver a
    empresa ANTES da view (para recusar modo livro-caixa), cada view voltou
    a resolvê-la de novo no próprio corpo — sem memoizar, isso soma uma
    consulta a mais por requisição e estourava o teto de consultas da
    DL-015/DL-019 (`test_dl019_razao_reaproveita_ids_contas.py`). Só
    memoiza o resultado feliz: se `get_object_or_404` estourar Http404,
    nada fica em cache e a próxima chamada tenta de novo (mesmo
    comportamento de antes, sem mascarar erro).
    """
    cache = getattr(request, "_dl038_cache_empresa_do_escritorio_ativo", None)
    if cache is None:
        cache = {}
        request._dl038_cache_empresa_do_escritorio_ativo = cache
    if empresa_id not in cache:
        cache[empresa_id] = get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)
    return cache[empresa_id]


def _resposta_sem_permissao(request, mensagem):
    # Critério 3: template próprio, com explicação e caminho de volta —
    # nunca texto cru, nunca 500. Reaproveita o MESMO template que
    # apps.empresas já usa (templates/erros/sem_permissao.html, da DL-009).
    return render(request, "erros/sem_permissao.html", {"mensagem": mensagem}, status=403)


def _resposta_sem_escritorio(request):
    # Reaproveita o mesmo template de apps.empresas (mesma situação: sem
    # escritório ativo não há como saber de qual contabilidade se fala).
    return render(request, "empresas/sem_escritorio.html")


def _sem_contabilidade_para_livro_caixa(request, empresa):
    """Recusa (403, com a MESMA mensagem e a MESMA regra da API) quando
    `empresa` está em modo `livro_caixa` — a contabilidade por partidas
    dobradas não está disponível para ela. Devolve a `HttpResponse` pronta
    quando recusa, ou `None` quando a empresa está livre.

    Achado B7 da auditoria rodada 1: até a rodada anterior, isto era um
    DECORADOR aplicado por FORA de cada view — o que o fazia rodar ANTES
    do escritório ativo e do papel serem checados PELO CORPO da view.
    Efeito medido: usuário SEM escritório ativo via 404 em vez da tela
    "sem escritório" (a empresa nunca chegava a ser resolvida pelo
    caminho que checa isso primeiro); e um papel SEM permissão de LEITURA
    (ex.: CLIENTE) via a MENSAGEM DE LIVRO-CAIXA em vez de "sem
    permissão" — revelando o MODO de escrituração da empresa a quem não
    tem acesso nem para ler. Agora é uma função CHAMADA por cada view,
    sempre DEPOIS do `if request.escritorio is None`/`_empresa_do_
    escritorio_ativo` e do `_pode_ler`/`_pode_escriturar` — nunca antes.

    A regra em si mora só em `apps.empresas.services.recusar_se_livro_caixa`
    (fonte única, R5); esta função só traduz para o MESMO template de "sem
    permissão" (403) que as outras recusas desta tela usam — nunca 500,
    nunca uma segunda cópia da mensagem.

    O lado API equivalente é `apps.contabilidade.views.
    EmpresaEscopadaContabilMixin.get_empresa` — as duas pontas chamam a
    mesma função de serviço, então a mensagem nunca diverge entre tela e
    API (a ORDEM relativa a escritório/papel é, por natureza, uma
    responsabilidade só da TELA — a API resolve escritório e permissão por
    outro mecanismo, o middleware e as `permission_classes`, ANTES do
    corpo da view rodar). A prova de que TODA view desta tela com
    `empresa_id` está coberta (varredura DERIVADA das rotas registradas,
    não lista escrita à mão) é `apps/contabilidade/tests/test_dl038_
    recusa_livro_caixa.py`.
    """
    try:
        recusar_se_livro_caixa(empresa)
    except EmpresaEmModoLivroCaixa as exc:
        return _resposta_sem_permissao(request, exc.mensagem)
    return None


def _pode_ler(request):
    return papel_pode_ler_contabilidade(getattr(request, "papel", None))


def _pode_escriturar(request):
    return PodeEscriturar().has_permission(request, None)


# ---------------------------------------------------------------------------
# Período e nível (critérios 7 e 9)
# ---------------------------------------------------------------------------


def _ultimo_dia_do_mes(referencia):
    proximo_mes = referencia.replace(day=28) + timedelta(days=4)
    return proximo_mes - timedelta(days=proximo_mes.day)


def _periodo_do_formulario(request):
    """Lê e valida 'inicio'/'fim' da querystring das três saídas com
    período (Diário, Razão, Balancete — critério 9).

    Ausência dos DOIS parâmetros (primeira visita à tela) usa o MÊS
    CORRENTE como valor inicial sugerido — diferente da API (DE-016), que
    RECUSA ausência: aqui é a TELA escolhendo um padrão por conveniência de
    quem vai usá-la todo dia, nunca o motor de cálculo. O padrão só é
    aplicado quando NADA foi enviado; um período enviado e malformado
    nunca "cai" no padrão silenciosamente — é reportado como erro.

    Devolve (inicio, fim, mensagem_de_erro). `mensagem_de_erro` é `None`
    quando o período é válido (default ou informado); do contrário, os dois
    primeiros valores vêm `None` e quem chama não deve apurar nada.
    """
    bruto_inicio = request.GET.get("inicio", "").strip()
    bruto_fim = request.GET.get("fim", "").strip()

    if not bruto_inicio and not bruto_fim:
        hoje = timezone.localdate()
        return hoje.replace(day=1), _ultimo_dia_do_mes(hoje), None

    if not bruto_inicio or not bruto_fim:
        return None, None, "Informe as duas datas do período (início e fim)."

    # R5-4/BL-143: `para_data` (`apps.core.datas`) é o ÚNICO julgador de
    # texto-de-cliente-para-data deste repositório (BL-133) — a cópia
    # PRÓPRIA que existia aqui (`_PADRAO_DATA_SIMPLES` + `date.
    # fromisoformat` cru) divergia da API sem que nenhum teste acusasse
    # (MX4/MX9/MX10, rodada 5): a mesma gramática, reimplementada, é
    # exatamente o que a DE-026 existe para impedir.
    try:
        inicio = para_data(bruto_inicio)
        fim = para_data(bruto_fim)
    except DataInvalida:
        return (
            None,
            None,
            "Data inválida: use o seletor de data (ou o formato AAAA-MM-DD).",
        )

    if inicio > fim:
        return None, None, "A data de início não pode ser posterior à data de fim."

    return inicio, fim, None


def _inteiro_de_cliente(texto):
    """Converte `texto` — entrada de CLIENTE — para `int`, ou devolve
    `None` se não for um inteiro ASCII simples. Nunca lança exceção, nunca
    reinterpreta em silêncio.

    Uso: QUANTIDADE de negócio (nível de hierarquia, número de linhas do
    lançamento) — nunca identificador de banco (para isso, ver
    `_identificador_de_cliente`, abaixo). A distinção importa porque uma
    quantidade absurdamente grande, mas ainda assim CONVERSÍVEL para
    `int` pelo próprio Python, precisa chegar como o `int` real na regra
    de negócio local, para que ELA decida — com a magnitude visível — se
    recusa e com que mensagem (R3-1/BL-115, abaixo). Um identificador não
    tem essa necessidade: qualquer coisa fora de um teto pequeno e fixo
    (19 dígitos, o maior `BigAutoField`) já é inválida por definição, não
    importa o valor exato.

    R2-2 (rodada 2): o guarda de formato não pode ser `isdigit()` sozinho
    — ele é `True` para QUALQUER dígito decimal Unicode, não só ASCII
    (`"٢".isdigit()` é `True`), e o `int()` do Python **aceita e converte**
    esses dígitos em silêncio: `int("７") == 7`, `int("٢") == 2`. Sem o
    guarda, um identificador em dígito Unicode passa por inteiro e é
    reinterpretado como se fosse outro — a mesma classe de reinterpretação
    silenciosa que a DE-029 proíbe para valor monetário, aqui para
    identificador.

    A1/A2 (rodada 4): nada protegia o `int()` seguinte de um texto
    absurdamente longo — `int("9" * 4301)` levanta `ValueError: Exceeds
    the limit (4300 digits) for integer string conversion`, um 500
    alcançável por qualquer POST/URL construído à mão. `nivel` do
    Balancete tinha exatamente esse defeito. `_inteiro_de_cliente` é o
    ÚNICO lugar deste arquivo que converte texto de QUANTIDADE de cliente
    para `int` — usado em TODO ponto onde isso acontece (ver
    `_nivel_do_formulario`, `_indices_de_linha_do_post` e o `num_linhas`
    de `lancamento_novo`), para que a lição não precise ser reaprendida
    campo por campo. Reaproveita `_PADRAO_NIVEL_SIMPLES` (`[0-9]+`,
    importado de `apps.contabilidade.views`) — mesmo padrão que a API já
    usa, não uma segunda cópia.

    R3-1 (rodada 3, BL-115): é exatamente esta preservação de magnitude
    que permite `lancamento_novo` recusar `num_linhas` absurdo com uma
    mensagem de NEGÓCIO ("aceita no máximo N partidas"), em vez de tratar
    um texto de 4000 dígitos como se fosse malformado e cair no padrão
    silenciosamente — só o que realmente estoura o limite de CONVERSÃO do
    interpretador (`sys.int_max_str_digits`) vira `None` aqui; o resto,
    por maior que seja, chega como `int` de verdade para a regra de
    negócio decidir.
    """
    if not texto or not _PADRAO_NIVEL_SIMPLES.fullmatch(texto):
        return None
    try:
        return int(texto)
    except ValueError:
        # Só alcançável por um texto com mais dígitos do que o limite de
        # conversão do próprio Python — o padrão acima já garante só
        # dígitos ASCII 0-9.
        return None


def _identificador_de_cliente(texto):
    """Converte `texto` — entrada de CLIENTE que deveria ser um
    IDENTIFICADOR DE BANCO (ex.: `conta_id`) — usando o julgador
    partilhado `para_id` (`apps.core.identificadores`), ou devolve `None`
    se não for um identificador válido. Nunca lança exceção.

    BL-127/A2 (rodada 4): esta tela tinha uma cópia PRÓPRIA da mesma
    invariante que `apps.core.identificadores.para_id` já julga para a
    API e para `apps.tenancy` — duas implementações da mesma regra
    divergem assim que uma for corrigida sem a outra (DE-026/DE-030).
    Delegar aqui, em vez de reimplementar o padrão e o teto de magnitude
    (19 dígitos, o maior `BigAutoField`), fecha essa divergência na raiz.

    Diferente de `_inteiro_de_cliente` (ver o docstring dela): um
    identificador de banco nunca precisa de mais de 19 dígitos, então não
    há necessidade de preservar a magnitude de um texto maior do que isso
    — é inválido de qualquer forma, e `conta_id` inválido sempre vira a
    MESMA mensagem ("conta inválida"), não importa se o texto era curto
    demais, tinha dígito Unicode, ou passava de 19 dígitos.
    """
    if not texto:
        return None
    try:
        return para_id(texto)
    except IdentificadorInvalido:
        return None


def _nivel_do_formulario(request):
    """Lê e valida o parâmetro opcional 'nivel' do Balancete.

    Ausente (ou vazio) devolve `None` — sem recorte de hierarquia, igual à
    API. Presente e malformado vira mensagem de erro, nunca um 500. A
    conversão em si é `_inteiro_de_cliente` (ver o docstring dela para o
    porquê); esta função só acrescenta o intervalo de negócio
    (1..`NIVEL_MAXIMO`) por cima.
    """
    bruto = request.GET.get("nivel", "").strip()
    if not bruto:
        return None, None
    nivel = _inteiro_de_cliente(bruto)
    if nivel is None or nivel < 1 or nivel > NIVEL_MAXIMO:
        return None, f"'Nível' deve ser um número inteiro entre 1 e {NIVEL_MAXIMO}."
    return nivel, None


_CRITERIOS_DE_APURACAO_VALIDOS = frozenset({"todas", "com_movimento"})
_TEXTO_DO_CRITERIO = {
    "todas": "todas as contas",
    "com_movimento": "movimento no período ou saldo anterior diferente de zero",
}


def _criterio_de_apuracao_do_formulario(request):
    """Lê e valida o parâmetro opcional 'criterio_de_apuracao' do Balancete
    (DL-027 Fatia B.2).

    Ausente (ou vazio) devolve `("todas", None)` — o default, que mantém o
    comportamento atual. Presente e fora do conjunto aceito vira mensagem
    de erro, nunca um 500 silencioso nem a aceitação de um valor
    desconhecido que passaria pelo service sem filtro.

    O par devolvido é `(valor_normalizado, mensagem_de_erro)` — mesmo
    contrato de `_nivel_do_formulario` e `_periodo_do_formulario`, para a
    view tratar uniformemente.
    """
    bruto = request.GET.get("criterio_de_apuracao", "").strip()
    if not bruto:
        return "todas", None
    if bruto not in _CRITERIOS_DE_APURACAO_VALIDOS:
        opcoes = ", ".join(sorted(_CRITERIOS_DE_APURACAO_VALIDOS))
        return (
            "todas",
            f"'Critério de apuração' deve ser um destes: {opcoes}.",
        )
    return bruto, None


# ---------------------------------------------------------------------------
# Plano de contas
# ---------------------------------------------------------------------------


def _linhas_hierarquicas(contas):
    """Nível ESTRUTURAL de cada conta (profundidade na árvore de
    `conta_pai`), só para indentar a listagem do Plano de Contas.

    Isto NÃO é a regra de saldo nem de consolidação — essas vivem inteiras
    em `apurar_balancete`/`apurar_razao` (services.py) e não são
    reimplementadas aqui. É só "quantos ancestrais esta conta tem", um
    fato estrutural sem julgamento contábil nenhum.

    Protegido contra ciclo (o mesmo problema que `HierarquiaInconsistente`
    nomeia em services.py): uma conta em ciclo não pode travar esta
    LISTAGEM — a conferência (tela própria, critério da DE-022/BL-64) é
    quem aponta isso; aqui o nível simplesmente degrada para `None`
    (exibido como "—"), sem exceção.
    """
    por_id = {conta.id: conta for conta in contas}
    niveis = {}

    def nivel_de(conta_id, caminho):
        if conta_id in niveis:
            return niveis[conta_id]
        if conta_id in caminho:
            return None
        conta = por_id[conta_id]
        if conta.conta_pai_id is None or conta.conta_pai_id not in por_id:
            resultado = 1
        else:
            pai_nivel = nivel_de(conta.conta_pai_id, caminho | {conta_id})
            resultado = None if pai_nivel is None else pai_nivel + 1
        niveis[conta_id] = resultado
        return resultado

    linhas = []
    for conta in contas:
        nivel = nivel_de(conta.id, frozenset())
        linhas.append(
            {
                "conta": conta,
                "nivel": nivel,
                # Inteiro, nunca `float` (achado 6) — vira a classe CSS
                # "nivel-N" no template, capada em NIVEL_INDENTACAO_MAXIMA.
                # A classe acompanha o NÍVEL: raiz é nível 1 e vira
                # "nivel-1"; só `None` (conta em ciclo, sem nível apurável)
                # cai em "nivel-0". As duas classes têm indentação zero na
                # folha de estilo, por motivos diferentes — a raiz porque é
                # raiz, o ciclo porque não há nível a representar. Nenhuma
                # classe negativa é gerada em nenhum caminho.
                "nivel_classe": min(nivel, NIVEL_INDENTACAO_MAXIMA) if nivel else 0,
            }
        )
    return linhas


@login_required
@require_safe
def plano_de_contas(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    contexto = {
        "empresa": empresa,
        "linhas": _linhas_hierarquicas(contas),
        "pode_escriturar": _pode_escriturar(request),
    }
    return render(request, "contabilidade/plano_de_contas.html", contexto)


class ContaCriarForm(forms.ModelForm):
    """Formulário de CRIAÇÃO de conta (`conta_nova`, abaixo) — a validação
    de servidor mora em `Conta.clean()`, chamada por `full_clean()` dentro
    de `is_valid()`.

    DL-045 fatia 3: `classificacao_dre` é o único campo NOVO desde a
    DL-020 — antes desta etapa, só a API expunha `classificacao_dre`/
    `classificacao_patrimonial` (`ContaSerializer`); esta é a primeira
    vez que uma das duas aparece em template. `classificacao_patrimonial`
    continua de fora do formulário (fora do escopo desta etapa — DL-045 é
    só sobre a DRE); nada aqui impede que ela entre depois pelo mesmo
    caminho.

    ⚠️ Este formulário serve SÓ à criação nesta etapa — não existe tela de
    EDIÇÃO de conta ainda (instrução do arquiteto-senior, 26/09/2026: a
    reclassificação de uma conta já existente espera um serviço próprio
    com guardas e trilha de auditoria, que o desenvolvedor-pleno ainda vai
    construir). Quando essa tela existir, é provável que reaproveite esta
    MESMA classe com `instance=conta` — mas isso ainda não está decidido
    nem implementado aqui.
    """

    class Meta:
        model = Conta
        fields = [
            "codigo",
            "nome",
            "tipo",
            "natureza",
            "conta_pai",
            "aceita_lancamento",
            "classificacao_dre",
            # DL-048/CTB-12: mesmo caminho da Linha da DRE (a conta já
            # nasce classificável nas DUAS demonstrações — o select é o
            # mesmo molde; a compatibilidade com o tipo continua sendo
            # decisão só do servidor, em `Conta.clean()`).
            "classificacao_dlpa",
            # DL-063 (BL-606): o quarto campo de classificação do mesmo
            # padrão. A conta passa a nascer classificável nas TRÊS
            # demonstrações — o select é o mesmo molde, e a compatibilidade
            # com o tipo continua sendo decisão só do servidor, em
            # `Conta.clean()`. Até 04/10/2026 o campo existia no modelo e
            # era lido pela apuração, mas não era gravável nem aqui nem pela
            # API: quem criava a conta tinha de sair daqui para classificá-la.
            "classificacao_dmpl",
        ]

    def __init__(self, *args, empresa, **kwargs):
        super().__init__(*args, **kwargs)
        # Isolamento (mesmo espírito do BL-40 / ContaSerializer.
        # validate_conta_pai na API): a lista de possíveis contas-pai nunca
        # pode incluir conta de OUTRA empresa — listar todas do banco
        # vazaria estrutura de plano de contas de outros clientes do
        # escritório.
        self.fields["conta_pai"].queryset = Conta.objects.filter(empresa=empresa).order_by("codigo")
        self.fields["conta_pai"].required = False
        # DL-044 — mesmo achado do `ParametroContabilForm` (ver o
        # comentário lá): o padrão do Django para `empty_label` é em
        # inglês. Aqui o rótulo também documenta o que a ausência de
        # conta-pai SIGNIFICA (conta raiz), não só "nenhuma".
        self.fields["conta_pai"].empty_label = "Nenhuma (conta raiz do plano)"
        # DL-045 fatia 3: rótulo "Linha da DRE" (o nome que o plano desta
        # etapa usa, e mais claro na tela que "classificação (DRE)", o
        # `verbose_name` do campo em models.py — pensado para a coluna de
        # uma tabela, não para o rótulo de um `<select>` isolado). A
        # COMPATIBILIDADE com o tipo da conta (só Receita/Despesa aceitam
        # linha da DRE — Lei 6.404/76, art. 187) é validada inteira no
        # servidor (`Conta.clean()`); o texto de ajuda só AVISA disso, nunca
        # decide sozinho o que aparece: sem JavaScript (R6), nenhum campo
        # deste formulário muda de acordo com outro — a opção fica sempre
        # visível, e quem escolhe uma linha incompatível recebe a mensagem
        # do servidor de volta em `form.non_field_errors()`.
        self.fields["classificacao_dre"].label = "Linha da DRE"
        self.fields["classificacao_dre"].help_text = (
            "Só se aplica a conta de Receita ou Despesa (Lei 6.404/76, art. 187) — o "
            "servidor recusa uma linha incompatível com o tipo desta conta. Reclassificar "
            "uma conta que já tem lançamento gravado também é recusado."
        )
        # DL-048/CTB-12: espelho da DRE acima. "Linha da DLPA" no select
        # (o `verbose_name` "classificação (DLPA)" é para coluna de
        # tabela); a ajuda NOMEIA os dois papéis do campo — conta sujeito
        # (a que a demonstração lê) e contrapartida (reserva, dividendo…) —
        # porque a mesma tela classifica os dois casos e o contador precisa
        # saber o que está escolhendo.
        self.fields["classificacao_dlpa"].label = "Linha da DLPA"
        self.fields["classificacao_dlpa"].help_text = (
            "Conta de Patrimônio Líquido ligada à Demonstração dos Lucros ou Prejuízos "
            "Acumulados (Lei 6.404/76, art. 186): classifique aqui a conta de lucros/"
            "prejuízos acumulados E as contrapartidas que movimentam ela (reserva, "
            "dividendo, resultado do exercício). O servidor recusa uma linha "
            "incompatível com o tipo desta conta."
        )
        # DL-063 (BL-063 → BL-606): espelho dos dois acima, e o terceiro dos
        # campos de classificação do mesmo padrão. "Coluna da DMPL" no select
        # (o `verbose_name` "classificação (coluna da DMPL)" é para coluna de
        # tabela). A ajuda diz o que a coluna FAZ — onde o componente entra
        # na Demonstração das Mutações do Patrimônio Líquido — e avisa que
        # ela é independente da linha da DLPA: são dois campos que o contador
        # pode precisar preencher juntos, e a regra que os amarra
        # (`divergencia_entre_dlpa_e_dmpl`, em `Conta.clean()`) é do
        # servidor, nunca do formulário.
        self.fields["classificacao_dmpl"].label = "Coluna da DMPL"
        self.fields["classificacao_dmpl"].help_text = (
            "Conta de Patrimônio Líquido ligada à Demonstração das Mutações do Patrimônio "
            "Líquido: em qual coluna o saldo dela aparece — capital, reserva, lucros "
            "acumulados, ações em tesouraria, dividendos. Só se aplica a conta de "
            "Patrimônio Líquido, e o servidor recusa uma coluna incompatível com o tipo "
            "desta conta."
        )


def _codigos_das_contas_mae(codigo):
    """Códigos das contas-mãe IMPLÍCITOS num código de conta, do mais alto
    para o mais próximo: `"4.1.1"` → `("4", "4.1")`.

    RC-80/BL-208. Só vale para plano com separador `"."`: um código sem
    ponto (`"41111"`, que alguns planos usam) não implica mãe nenhuma, e
    inventar hierarquia a partir de fatia de dígitos seria presumir regra
    contábil — o que o AGENTS.md proíbe. Parte vazia (`"4..1"`, `".1"`)
    também devolve vazio: não é hierarquia, é código malformado, e quem
    julga formato de código é o modelo.
    """
    partes = codigo.split(".")
    if len(partes) < 2 or any(not parte for parte in partes):
        return ()
    return tuple(".".join(partes[: i + 1]) for i in range(len(partes) - 1))


def _contas_mae_faltantes(empresa, codigo, conta_pai):
    """Quais contas-mãe implícitas no código NÃO existem no plano desta
    empresa — a consequência estrutural que o RC-80 manda avisar.

    Devolve vazio quando o contador escolheu uma conta-pai explicitamente:
    aí a conta não vai ficar como raiz, e o aviso ("ela ficará como raiz do
    plano") seria falso. Uma consulta só, com `codigo__in` — nunca uma por
    nível.
    """
    if conta_pai is not None:
        return ()
    codigos = _codigos_das_contas_mae(codigo or "")
    if not codigos:
        return ()
    existentes = set(
        Conta.objects.filter(empresa=empresa, codigo__in=codigos).values_list("codigo", flat=True)
    )
    return tuple(codigo_mae for codigo_mae in codigos if codigo_mae not in existentes)


@login_required
@require_http_methods(["GET", "POST"])
def conta_nova(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, "Seu papel não permite criar contas nesta empresa.")

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    if request.method == "POST":
        # BL-196/R6-2 (rodada 6) — a defesa que existia na tela vizinha
        # (`lancamento_novo`, 40 linhas abaixo) e NÃO existia aqui. Medido
        # pelo auditor: `conta_pai` enviado como ARQUIVO gravava a conta na
        # RAIZ do plano, com 302 de sucesso e sem uma palavra — muda a
        # indentação, o nível e o Balancete por nível. Querystring em POST,
        # campo desconhecido no corpo e `Idempotency-Key` por cabeçalho
        # eram igualmente aceitos e descartados em silêncio.
        #
        # A resposta é o formulário RE-RENDERIZADO com 400 e o que o
        # usuário digitou (mesma política de `_recusa_lancamento_com_erro`,
        # BL-199): recusar sem devolver o que foi digitado troca um defeito
        # por outro.
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_CONTA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return render(
                request,
                "contabilidade/conta_form.html",
                {
                    "empresa": empresa,
                    "form": ContaCriarForm(
                        request.POST, instance=Conta(empresa=empresa), empresa=empresa
                    ),
                },
                status=400,
            )

        # A empresa é atribuída à instância ANTES de is_valid() — não é um
        # campo do formulário (o cliente nunca escolhe a empresa; ela vem
        # do escopo da URL, já revalidada acima). É o que permite a
        # Conta.clean() (chamada por full_clean() dentro de is_valid())
        # comparar `conta_pai.empresa_id` contra a empresa CERTA, e não
        # contra `None`.
        instancia = Conta(empresa=empresa)
        form = ContaCriarForm(request.POST, instance=instancia, empresa=empresa)
        if form.is_valid():
            # RC-80/BL-208 — regra confirmada pelo Fred em 2026-09-15:
            # conta sem as contas-mãe **avisa e deixa criar**. Cadastrar
            # `4.1.1` num plano sem `4` e sem `4.1` é legítimo (o contador
            # pode estar montando o plano de baixo para cima), mas tem
            # consequência ESTRUTURAL que ele não pediu: sem conta-pai, a
            # conta entra como RAIZ (nível 1), muda a indentação do Plano
            # de Contas e a linha em que ela aparece no Balancete por
            # nível. Nenhuma consequência estrutural de um cadastro
            # acontece sem o usuário ser avisado — então a primeira
            # tentativa NÃO grava: ela volta a tela com o aviso, os dados
            # preenchidos e um botão que diz o que vai acontecer.
            #
            # 200 e não 400 de propósito: não é erro do usuário, é uma
            # confirmação. E o caminho de correção fica visível ao lado
            # (cadastrar as mães primeiro), que é o que o RC-80 pede
            # quando diz "avisar".
            contas_mae_faltantes = _contas_mae_faltantes(
                empresa, form.cleaned_data.get("codigo"), form.cleaned_data.get("conta_pai")
            )
            if contas_mae_faltantes and request.POST.get("confirmar_conta_sem_conta_mae") != "1":
                messages.warning(
                    request,
                    f"O código “{form.cleaned_data.get('codigo')}” sugere "
                    f"{'a conta-mãe' if len(contas_mae_faltantes) == 1 else 'as contas-mãe'} "
                    f"{', '.join(contas_mae_faltantes)}, que não "
                    f"{'existe' if len(contas_mae_faltantes) == 1 else 'existem'} neste plano. "
                    "Nada foi gravado ainda: confirme abaixo, ou cadastre as contas-mãe "
                    "primeiro.",
                )
                return render(
                    request,
                    "contabilidade/conta_form.html",
                    {
                        "empresa": empresa,
                        "form": form,
                        "contas_mae_faltantes": contas_mae_faltantes,
                        "codigo_pedido": form.cleaned_data.get("codigo"),
                    },
                )
            try:
                # 'empresa' fica FORA da lista de campos do formulário, e
                # por isso o Django exclui a UniqueConstraint
                # "codigo_unico_por_empresa" da checagem de
                # `validate_unique()` dentro de full_clean() (regra do
                # próprio Django: uma constraint composta é pulada se
                # QUALQUER campo dela estiver fora do formulário). Este
                # try/except no INSERT é, por isso, o mecanismo real que
                # detecta duplicidade aqui — não apenas defesa de corrida,
                # como é em apps.empresas (onde o formulário já cobre
                # 'cnpj' inteiro).
                #
                # BL-14 (DL-024): o `registrar()` foi MOVIDO para dentro do
                # mesmo `transaction.atomic()` que grava a Conta. Antes,
                # qualquer falha no INSERT do `RegistroAuditoria` deixava a
                # Conta gravada e a trilha silenciosamente vazia — o plano
                # de contas dizia uma coisa, a trilha dizia outra. Agora
                # ambos são uma só operação atômica; o `else:` (que só roda
                # em caso de sucesso no `try:`) garante que a auditoria
                # só é tentada se a gravação passou.
                with transaction.atomic():
                    conta = form.save()
                    registrar(acao="conta.criada", objeto=conta, request=request)
            except IntegrityError:
                form.add_error("codigo", "Já existe uma conta com este código nesta empresa.")
            else:
                messages.success(request, f"Conta “{conta}” criada com sucesso.")
                return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ContaCriarForm(empresa=empresa)

    return render(request, "contabilidade/conta_form.html", {"empresa": empresa, "form": form})


class ClassificacaoDreForm(forms.Form):
    """Formulário de UM campo só — a Linha da DRE de uma conta EXISTENTE
    (DL-045, correção da rodada 1 de auditoria, achado A7). Não é um
    `ModelForm`: a gravação nunca é `form.save()` direto — passa por
    `classificar_conta_na_dre` (services.py), a MESMA porta que a API usa
    (`ContaClassificacaoDreView`), que chama `Conta.full_clean()` e
    carrega TODAS as guardas (compatibilidade de tipo, transição com
    movimento, A6). Este formulário nunca duplica nenhuma delas — só
    coleta o valor e devolve `None` para "sem classificação" (nunca
    `""`, achado A4 — `ChoiceField` com `required=False` e a opção vazia
    já cai em `cleaned_data["classificacao_dre"] == ""`; a normalização
    para `None` acontece na VIEW, no mesmo ponto em que `classificar_
    conta_na_dre`/`Conta.clean()` já a esperam).
    """

    classificacao_dre = forms.ChoiceField(
        label="Linha da DRE",
        choices=[("", "Sem classificação")] + list(ClassificacaoDre.choices),
        required=False,
        help_text=(
            "Só se aplica a conta de Receita ou Despesa (Lei 6.404/76, art. 187) — o "
            "servidor recusa uma linha incompatível com o tipo desta conta. Reclassificar "
            "uma conta que já tem lançamento gravado também é recusado."
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def conta_classificacao_dre(request, empresa_id, conta_id):
    """Classifica (ou reclassifica, ou remove a classificação de) a Linha
    da DRE de uma conta EXISTENTE — DL-045, correção da rodada 1 de
    auditoria (A7): a porta operacional que faltava na TELA (a API já
    tinha `ContaClassificacaoDreView`, PATCH). Chamada pelo veto de
    emissão da DRE (`dre`, mais abaixo — cada conta pendente ganha um
    link direto para cá) e pelo Plano de contas (botão "Linha da DRE" em
    cada conta de resultado).

    Autorização: `_pode_escriturar` — MESMO papel que a API usa
    (`PodeEscriturar`), nunca uma permissão nova (RC-118 não criou papel
    próprio para a classificação da DRE). Isolamento: `empresa=empresa`
    no filtro — conta de outra empresa dá 404, nunca confirma a
    existência do registro.

    A GRAVAÇÃO passa inteira por `classificar_conta_na_dre` (services.py)
    — a MESMA função que a API chama —, nunca reimplementada aqui: esta
    view só traduz `django.core.exceptions.ValidationError` (qualquer
    guarda de `Conta.clean()`) para `form.add_error(None, ...)` e
    RE-renderiza o formulário com **200** — mesma convenção de `conta_
    nova` (achado `IntegrityError`) e do veto do Balanço/DRE: uma recusa
    de REGRA DE NEGÓCIO é a tela respondendo corretamente "não, e eis o
    porquê", nunca um erro de protocolo. Nunca um 500. `conta.refresh_
    from_db()` (R6, reconferência) restaura o valor REALMENTE gravado
    antes de renderizar — `classificar_conta_na_dre` muta a instância
    ANTES de `full_clean()` recusar, e sem o refresh o formulário
    mostraria o valor RECUSADO como se fosse o atual.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite classificar a linha da DRE nesta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DRE)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return render(
                request,
                "contabilidade/conta_classificacao_dre.html",
                {"empresa": empresa, "conta": conta, "form": ClassificacaoDreForm(request.POST)},
                status=400,
            )

        form = ClassificacaoDreForm(request.POST)
        if form.is_valid():
            # Achado A4: "" (opção "Sem classificação") normalizado para
            # `None` AQUI — o mesmo ponto que `classificar_conta_na_dre`/
            # `ContaClassificacaoDreView.patch` já usam (`or None`) —
            # nunca grava string vazia.
            classificacao = form.cleaned_data["classificacao_dre"] or None
            try:
                classificar_conta_na_dre(
                    conta=conta, classificacao=classificacao, usuario=request.user, request=request
                )
            except DjangoValidationError as exc:
                # R6 (reconferência DL-045): `classificar_conta_na_dre`
                # (services.py) muta `conta.classificacao_dre` no objeto
                # ANTES de `full_clean()` recusar — a exceção sobe, a
                # TRANSAÇÃO nunca comita nada, mas o objeto Python em
                # memória continua com o valor RECUSADO. Sem este
                # `refresh_from_db()`, esta view re-renderizava com a
                # MESMA instância e o template mostrava "Linha atual: <o
                # valor recusado>" — a tela afirmando um estado que o
                # banco nunca teve. `refresh_from_db()` restaura o valor
                # REALMENTE gravado antes de render.
                conta.refresh_from_db()
                for mensagem in mensagens_da_validacao_django(exc):
                    form.add_error(None, mensagem)
            else:
                messages.success(request, f"Linha da DRE de “{conta}” atualizada com sucesso.")
                return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ClassificacaoDreForm(initial={"classificacao_dre": conta.classificacao_dre or ""})

    return render(
        request,
        "contabilidade/conta_classificacao_dre.html",
        {"empresa": empresa, "conta": conta, "form": form},
    )


class ClassificacaoDlpaForm(forms.Form):
    """Formulário de UM campo só — a Linha da DLPA de uma conta EXISTENTE
    (DL-048/CTB-12: reaproveitar o padrão de `ClassificacaoDreForm`).
    Não é um `ModelForm`: a gravação passa SEMPRE por
    `classificar_conta_na_dlpa` (services.py), que chama `full_clean()` e
    carrega as guardas de `Conta.clean()` (compatibilidade de tipo, choices)
    + a trilha de auditoria. Este formulário só coleta o valor e devolve
    `None` para "Sem classificação" (nunca `""` — normalização na view,
    mesmo achado A4 da DL-045).
    """

    classificacao_dlpa = forms.ChoiceField(
        label="Linha da DLPA",
        choices=[("", "Sem classificação")] + list(ClassificacaoDlpa.choices),
        required=False,
        help_text=(
            "Lei 6.404/76, art. 186. Classifique a conta de lucros/prejuízos acumulados "
            "(a que a demonstração lê) e cada contrapartida que movimenta ela — reserva, "
            "dividendo, resultado do exercício. O servidor recusa uma linha "
            "incompatível com o tipo desta conta; conta de subconta não herda a "
            "classificação da mãe."
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def conta_classificacao_dlpa(request, empresa_id, conta_id):
    """Classifica (ou reclassifica, ou remove) a Linha da DLPA de uma conta
    EXISTENTE — DL-048/CTB-12: a porta de TELA no molde de
    `conta_classificacao_dre`. Chamada pelo veto da tela `dlpa` (cada conta
    pendente ganha link direto) e pelo Plano de contas.

    Autorização: `_pode_escriturar` (MESMO papel da API e da classificação
    da DRE — nenhuma permissão nova); filtro `empresa=empresa` — conta de
    outra empresa/escritório dá 404, nunca confirma existência.

    A GRAVAÇÃO passa inteira por `classificar_conta_na_dlpa`; esta view só
    traduz `ValidationError` para `form.add_error(None, ...)` e re-renderiza
    com 200 (recusa de regra é a tela respondendo "nunca um 500"). O
    `refresh_from_db()` em caso de recusa restaura o valor REALMENTE
    gravado — o serviço muta a instância antes do `full_clean()` recusar
    (mesmo achado R6 da reconferência da DL-045).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite classificar a linha da DLPA nesta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DLPA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return render(
                request,
                "contabilidade/conta_classificacao_dlpa.html",
                {"empresa": empresa, "conta": conta, "form": ClassificacaoDlpaForm(request.POST)},
                status=400,
            )

        form = ClassificacaoDlpaForm(request.POST)
        if form.is_valid():
            classificacao = form.cleaned_data["classificacao_dlpa"] or None
            try:
                classificar_conta_na_dlpa(
                    conta=conta, classificacao=classificacao, usuario=request.user, request=request
                )
            except ClassificacaoAlteraPeriodoFechado as exc:
                # DL-065 (BL-550): a tela responde 200 com a recusa no
                # formulário, como toda recusa de regra — nunca um 500. O
                # `refresh_from_db()` devolve o valor REALMENTE gravado, pelo
                # mesmo motivo do `DjangoValidationError` abaixo: o serviço
                # muta a instância antes de recusar.
                conta.refresh_from_db()
                form.add_error(None, str(exc))
            except DjangoValidationError as exc:
                conta.refresh_from_db()
                for mensagem in mensagens_da_validacao_django(exc):
                    form.add_error(None, mensagem)
            else:
                messages.success(request, f"Linha da DLPA de “{conta}” atualizada com sucesso.")
                return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ClassificacaoDlpaForm(initial={"classificacao_dlpa": conta.classificacao_dlpa or ""})

    return render(
        request,
        "contabilidade/conta_classificacao_dlpa.html",
        {"empresa": empresa, "conta": conta, "form": form},
    )


def _opcoes_da_coluna_da_dmpl_por_grupo():
    """Opções do `<select>` da coluna da DMPL, AGRUPADAS pelo grupo do item
    111A da NBC TG 51 (106B da R5) — `<optgroup>` nativo, sem JavaScript.

    Derivada de `GRUPO_DA_CLASSIFICACAO_DMPL` (models.py): a ordem dos grupos
    e das colunas é a do enum, e uma coluna nova entra aqui sozinha. O
    grupo é só ORGANIZAÇÃO da lista (36 rótulos soltos são mais difíceis de
    achar); o valor gravado continua sendo a coluna, nunca o grupo.
    """
    por_grupo = {}
    for coluna in ClassificacaoDmpl:
        grupo = GRUPO_DA_CLASSIFICACAO_DMPL[coluna]
        por_grupo.setdefault(grupo, []).append((coluna.value, coluna.label))
    return [("", "Sem coluna na DMPL")] + [
        (GrupoDaDmpl(grupo).label, opcoes) for grupo, opcoes in por_grupo.items()
    ]


class ClassificacaoDmplForm(forms.Form):
    """Formulário de UM campo só — a Coluna da DMPL de uma conta EXISTENTE
    (DL-061/CTB-14, no molde de `ClassificacaoDlpaForm`). Não é um
    `ModelForm`: a gravação passa SEMPRE por `classificar_conta_na_dmpl`
    (services.py), que chama `full_clean()` e carrega as guardas de
    `Conta.clean()` (só conta de Patrimônio Líquido; consistência com a
    linha da DLPA) + a trilha de auditoria. Devolve `None` para "Sem
    coluna" (nunca `""` — normalização na view, como na DLPA).
    """

    classificacao_dmpl = forms.ChoiceField(
        label="Coluna da DMPL",
        choices=_opcoes_da_coluna_da_dmpl_por_grupo,
        required=False,
        help_text=(
            "Cada conta de patrimônio líquido que a DMPL deve mostrar precisa de uma "
            "coluna (NBC TG 51, item 111A; NBC TG 26 (R5), item 106B). Reservas de "
            "lucros e lucros ou prejuízos acumulados precisam ter a mesma classificação "
            "na DLPA e na DMPL — o servidor recusa a divergência. A coluna vale para "
            "esta conta exata: subconta não herda a classificação da mãe."
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def conta_classificacao_dmpl(request, empresa_id, conta_id):
    """Classifica (ou reclassifica, ou remove) a Coluna da DMPL de uma conta
    EXISTENTE — DL-061/CTB-14: a porta de TELA no molde de
    `conta_classificacao_dlpa`. Chamada pelo veto da tela `dmpl` (cada conta
    pendente ganha link direto) e pelo Plano de contas.

    Autorização: `_pode_escriturar` (MESMO papel da classificação da DLPA e
    da DRE — nenhuma permissão nova); filtro `empresa=empresa` — conta de
    outra empresa/escritório dá 404, nunca confirma existência.

    A GRAVAÇÃO passa inteira por `classificar_conta_na_dmpl`; esta view só
    traduz `ValidationError` para `form.add_error(None, ...)` e re-renderiza
    com 200 (recusa de regra é a tela respondendo, nunca um 500). O
    `refresh_from_db()` em caso de recusa restaura o valor REALMENTE
    gravado — o serviço muta a instância antes do `full_clean()` recusar.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite classificar a coluna da DMPL nesta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DMPL)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return render(
                request,
                "contabilidade/conta_classificacao_dmpl.html",
                {"empresa": empresa, "conta": conta, "form": ClassificacaoDmplForm(request.POST)},
                status=400,
            )

        form = ClassificacaoDmplForm(request.POST)
        if form.is_valid():
            classificacao = form.cleaned_data["classificacao_dmpl"] or None
            try:
                classificar_conta_na_dmpl(
                    conta=conta, classificacao=classificacao, usuario=request.user, request=request
                )
            except ClassificacaoAlteraPeriodoFechado as exc:
                # DL-065 (BL-550): mesma tradução da porta da DLPA — recusa no
                # formulário com 200 e valor gravado restaurado.
                conta.refresh_from_db()
                form.add_error(None, str(exc))
            except DjangoValidationError as exc:
                conta.refresh_from_db()
                for mensagem in mensagens_da_validacao_django(exc):
                    form.add_error(None, mensagem)
            else:
                messages.success(request, f"Coluna da DMPL de “{conta}” atualizada com sucesso.")
                return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ClassificacaoDmplForm(initial={"classificacao_dmpl": conta.classificacao_dmpl or ""})

    return render(
        request,
        "contabilidade/conta_classificacao_dmpl.html",
        {"empresa": empresa, "conta": conta, "form": form},
    )


class ClassificacaoDfcForm(forms.Form):
    """Formulário de TRÊS campos — a classificação da DFC de uma conta
    EXISTENTE (DL-066/CTB-15, no molde de `ClassificacaoDlpaForm`). Não é um
    `ModelForm`: a gravação passa SEMPRE por `classificar_conta_na_dfc`
    (services.py), que chama `full_clean()` e carrega as guardas de
    `Conta.clean()` (caixa **e** atividade não convivem na mesma conta; item
    sem caixa só em conta de resultado; recusa de período fechado) + a
    trilha de auditoria.

    Os TRÊS campos são recebidos como ESTADO DESEJADO completo, não como
    patch (ver o docstring do serviço): por isso o formulário sempre envia
    os dois marcadores, mesmo desligados — desmarcar é decisão, não ausência
    de decisão. As opções do meio vêm do MESMO enum que o modelo usa
    (`ClassificacaoFluxoCaixa`), e o texto de ajuda vem do `help_text` do
    modelo — FONTE ÚNICA: a regra e a citação normativa já moram lá, e uma
    cópia aqui divergiria na primeira edição.
    """

    caixa_e_equivalentes = forms.BooleanField(
        label="Caixa e equivalentes",
        required=False,
        help_text=Conta._meta.get_field("caixa_e_equivalentes").help_text,
    )
    classificacao_dfc = forms.ChoiceField(
        label="Atividade do fluxo de caixa",
        choices=[("", "Sem atividade")] + list(ClassificacaoFluxoCaixa.choices),
        required=False,
        help_text=Conta._meta.get_field("classificacao_dfc").help_text,
    )
    item_de_resultado_sem_caixa = forms.BooleanField(
        label="Item de resultado que não movimenta caixa",
        required=False,
        help_text=Conta._meta.get_field("item_de_resultado_sem_caixa").help_text,
    )


@login_required
@require_http_methods(["GET", "POST"])
def conta_classificacao_dfc(request, empresa_id, conta_id):
    """Classifica (ou reclassifica) os TRÊS campos da DFC de uma conta
    EXISTENTE — DL-066/CTB-15: a porta de TELA no molde de
    `conta_classificacao_dlpa`. Chamada pelo veto da tela `dfc` (cada conta
    pendente ganha link direto) e pelo Plano de contas.

    Autorização: `_pode_escriturar` (MESMO papel das classificações irmãs —
    nenhuma permissão nova); filtro `empresa=empresa` — conta de outra
    empresa/escritório dá 404, nunca confirma existência.

    A GRAVAÇÃO passa inteira por `classificar_conta_na_dfc`; esta view só
    traduz `ClassificacaoAlteraPeriodoFechado` (DL-065/BL-550, estendida aos
    três campos na etapa 2) e `ValidationError` para `form.add_error(None,
    ...)` e re-renderiza com 200 (recusa de regra é a tela respondendo, nunca
    um 500). O `refresh_from_db()` em caso de recusa restaura o valor
    REALMENTE gravado — o serviço muta a instância antes do `full_clean()`
    recusar (mesmo achado R6 da reconferência da DL-045).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite classificar a DFC nesta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DFC)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return render(
                request,
                "contabilidade/conta_classificacao_dfc.html",
                {"empresa": empresa, "conta": conta, "form": ClassificacaoDfcForm(request.POST)},
                status=400,
            )

        form = ClassificacaoDfcForm(request.POST)
        if form.is_valid():
            try:
                classificar_conta_na_dfc(
                    conta=conta,
                    caixa_e_equivalentes=form.cleaned_data["caixa_e_equivalentes"],
                    classificacao_dfc=form.cleaned_data["classificacao_dfc"] or None,
                    item_de_resultado_sem_caixa=form.cleaned_data["item_de_resultado_sem_caixa"],
                    usuario=request.user,
                    request=request,
                )
            except ClassificacaoAlteraPeriodoFechado as exc:
                # DL-065 (BL-550), estendida aos três campos: mesma tradução
                # da porta da DLPA — recusa no formulário com 200 e valor
                # gravado restaurado, nunca um 500.
                conta.refresh_from_db()
                form.add_error(None, str(exc))
            except DjangoValidationError as exc:
                conta.refresh_from_db()
                for mensagem in mensagens_da_validacao_django(exc):
                    form.add_error(None, mensagem)
            else:
                messages.success(
                    request, f"Classificação da DFC de “{conta}” atualizada com sucesso."
                )
                return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ClassificacaoDfcForm(
            initial={
                "caixa_e_equivalentes": conta.caixa_e_equivalentes,
                "classificacao_dfc": conta.classificacao_dfc or "",
                "item_de_resultado_sem_caixa": conta.item_de_resultado_sem_caixa,
            }
        )

    return render(
        request,
        "contabilidade/conta_classificacao_dfc.html",
        {"empresa": empresa, "conta": conta, "form": form},
    )


# ---------------------------------------------------------------------------
# Lançamento (critérios 10 e 11)
# ---------------------------------------------------------------------------


# DE-029 — substitui a cláusula de tradução da DE-027, que estava ERRADA.
# A DE-027 dizia "vírgula decimal vira ponto, separador de milhar sai", mas
# o código só tirava o ponto quando havia vírgula: "1.000" (mil reais em
# pt-BR) era gravado como 1,00 — bloqueador da rodada 2 da auditoria da
# DL-017, na `main` desde o PR #18. A causa raiz não é um `if` esquecido: é
# que "1.000" é AMBÍGUO (mil reais em pt-BR; um real no formato canônico da
# API) e não existe função de tradução bem definida sobre um texto ambíguo
# — corrigir o código para "sempre tirar o ponto" resolveria "1.000" e
# quebraria "10.00" no sentido oposto (dez reais viraria mil).
#
# A saída, como em todo lugar deste módulo monetário, é NUNCA adivinhar:
# uma gramática pt-BR EXPLÍCITA, e texto fora dela é recusado — nunca
# reinterpretado. Dígitos sem separador ALGUM, ou dígitos agrupados de três
# em três por ponto (grupo de milhar bem formado: exatamente três dígitos
# após cada ponto), com centavos opcionais depois da vírgula.
#
# "10.00"/"1.00" são RECUSADOS de propósito: não são grupo de milhar bem
# formado (".00" tem só dois dígitos) — são o formato CANÔNICO DA API
# (ponto como separador DECIMAL), não uma leitura pt-BR válida. Essa
# divergência entre tela e API para textos fora da gramática pt-BR é
# intencional (ver docs/projeto/decisoes.md, DE-029).
#
# `[0-9]`, não `\d`: mesma lição já aplicada em `_PADRAO_NIVEL_SIMPLES`
# (achado R2-2 desta rodada) e em `PADRAO_VALOR_DECIMAL_SIMPLES`
# (`apps.core.dinheiro`, achado R2-7) — `\d` do Python casa QUALQUER
# dígito decimal Unicode ("０１０" fullwidth, "١٢٣" índico-arábico, "๑๐"
# tailandês), não só ASCII 0-9. Sem esta troca, a gramática desta tela
# aceitaria esses textos em silêncio; `para_decimal` (segunda camada,
# chamada depois da tradução) já recusa todos eles hoje, então não havia
# furo ativo — mas manter `\d` aqui deixaria um julgador frouxo na
# PRIMEIRA camada, quando a segunda for a única linha de defesa não
# deveria ser por acidente.
_GRAMATICA_VALOR_PTBR = re.compile(r"^[+-]?([0-9]+|[0-9]{1,3}(\.[0-9]{3})+)(,[0-9]{1,2})?$")


def _decimal_do_formulario(texto):
    """Converte o texto digitado no campo de valor (pt-BR) para `Decimal`.

    DUAS camadas, nesta ordem — DE-029 (rodada 2) sobre DE-027 (rodada 1):

    1. `_GRAMATICA_VALOR_PTBR` julga se o texto é uma representação pt-BR
       BEM FORMADA (a única coisa que só esta tela pode saber — a API não
       fala pt-BR). Texto fora da gramática é recusado AQUI, com mensagem
       que ensina o formato — nunca "corrigido" ou reinterpretado.
    2. Só o que casou a gramática é TRADUZIDO (pontos de milhar somem,
       vírgula decimal vira ponto — a única tradução de locale que esta
       tela faz, agora comprovadamente segura: a gramática já garantiu que
       cada ponto restante é um separador de milhar válido) e entregue a
       `apps.core.dinheiro.para_decimal`, que é quem julga se o resultado é
       uma representação aceitável de dinheiro em geral (mesmo módulo que a
       API usa em `_extrair_itens`, views.py) — sinal, não-finito, formato
       canônico. Continua sendo a ÚNICA função que decide isso (DE-027):
       esta view nunca constrói `Decimal` por conta própria.

    Antes da DE-027 (rodada 1), a função construía `Decimal(bruto)`
    diretamente — o construtor do Python é mais permissivo do que o
    contrato monetário do projeto (notação científica, "_" como separador
    de dígitos, não rejeita `NaN`/`Infinity`). Antes da DE-029 (rodada 2), a
    tradução só tirava o ponto quando havia vírgula, e "1.000" virava 1,00.

    Levanta `ValorMonetarioInvalido` para texto que não representa um valor
    monetário aceitável — quem chama trata isso como erro de FORMULÁRIO. A
    validação de DOMÍNIO (sinal, escala máxima — DE-010) continua sendo
    feita só por `criar_lancamento` (services.py); esta função só entende o
    formato de DIGITAÇÃO, nunca decide se o valor é aceitável contabilmente.
    """
    bruto = texto or ""
    if not _GRAMATICA_VALOR_PTBR.fullmatch(bruto):
        raise ValorMonetarioInvalido(
            f"Valor “{bruto}” não está no formato aceito. Use dígitos, ponto "
            "a cada três casas como separador de milhar (ex.: 1.000) e "
            "vírgula para os centavos (ex.: 1.000,00). Um texto ambíguo "
            "nunca é reinterpretado — é recusado."
        )
    # Seguro remover TODOS os pontos (não só quando há vírgula): a
    # gramática acima já garantiu que, se existem pontos, cada um deles é
    # um grupo de milhar de exatamente três dígitos — nunca um separador
    # decimal disfarçado (esse caso já foi recusado acima).
    traduzido = bruto.replace(".", "").replace(",", ".")
    return para_decimal(traduzido)


# R2-3 (rodada 2 da auditoria da DL-017): teto de SEGURANÇA para quantas
# linhas esta view tenta ler/exibir a partir de um único POST — bem acima
# do teto de NEGÓCIO (LINHAS_MAXIMAS_LANCAMENTO). Não é regra contábil: é
# higiene de fronteira HTTP, para que um ÚNICO campo com índice absurdo
# (ex.: "conta_999999999999") não force esta view a processar/exibir uma
# quantidade de linhas proporcional a esse índice.
#
# R3-9 (rodada 3, BL-120): os DOIS tetos precisam ficar nesta ordem para
# sempre — o de SEGURANÇA (este) estritamente maior que o de NEGÓCIO
# (LINHAS_MAXIMAS_LANCAMENTO, definido no topo do módulo) — porque hoje é
# a DESIGUALDADE entre os dois, e não o desenho de nenhuma função, que
# impede um índice fora do canônico (recusado por `_indices_de_linha_do_
# post`) de coincidir com um índice de negócio válido. Falhar cedo e
# ruidosamente (`AssertionError` na importação do módulo, não um 500 numa
# requisição) é deliberado: é uma invariante ESTRUTURAL do arquivo, não
# um dado de runtime — o mesmo motivo por que também há um teste dedicado
# (`test_teto_de_seguranca_e_estritamente_maior_que_o_teto_de_negocio`,
# em test_dl017_rodada2_frontend.py), que não depende do processo ter
# sido de fato importado com `assert` habilitado (`python -O` os
# descarta).
# RC-79/BL-207 (rodada 6): o teto de NEGÓCIO subiu de 20 para 200, e este
# teto de SEGURANÇA **subiu junto**, de 200 para 400 — que é exatamente o
# que a verificação abaixo existe para forçar. Ela REPROVOU a importação do
# módulo no instante em que o teto de negócio virou 200, com os dois em
# 200: o mecanismo da BL-120 funcionando como projetado, um ano-luz melhor
# do que a perda silenciosa que ele substituiu (com os dois iguais,
# `min(maior, 200)` voltaria a descartar em silêncio o índice 200 na
# fronteira). Mantido o dobro do teto de negócio, e não 201, para que a
# folga continue existindo sem depender de aritmética de fronteira.
LINHAS_LEITURA_TETO_DE_SEGURANCA = 400
assert LINHAS_MAXIMAS_LANCAMENTO < LINHAS_LEITURA_TETO_DE_SEGURANCA, (
    "LINHAS_MAXIMAS_LANCAMENTO (teto de NEGÓCIO) precisa ficar estritamente "
    "abaixo de LINHAS_LEITURA_TETO_DE_SEGURANCA (teto de SEGURANÇA) — R3-9/BL-120."
)

# R3-2/BL-116 (rodada 3): o padrão de BUSCA é deliberadamente amplo —
# qualquer sufixo NÃO VAZIO depois de "conta_"/"tipo_"/"valor_" — e não
# `[0-9]{1,4}` como na rodada 2. A versão antiga só CASAVA índices já bem
# formados; um índice mal formado ("conta_10000", "conta_0001",
# "conta_+3") simplesmente não casava NADA, ficava invisível para
# `_indices_de_linha_do_post` e para a leitura (`_linhas_lancamento_do_post`
# só lê pela chave CANÔNICA "conta_{i}", nunca "conta_0001") — a linha
# desaparecia em silêncio, com HTTP 302 "gravado com sucesso". Para poder
# RECUSAR uma chave malformada (em vez de ignorá-la), a busca precisa
# primeiro ENCONTRÁ-LA.
#
# A3 (rodada 4): `re.IGNORECASE` por um motivo específico — "CONTA_3" e
# "Conta_3" (prefixo em capitalização diferente da que o template emite)
# também precisam ser ENCONTRADOS para poderem ser recusados como não
# canônicos (ver o teste de capitalização em `_indices_de_linha_do_post`
# abaixo). Sem isto, ficavam invisíveis pelo mesmo motivo que o índice
# malformado ficava antes da correção da rodada 3.
_PADRAO_CHAVE_DE_LINHA = re.compile(r"^(conta|tipo|valor)_(.+)$", re.IGNORECASE)


def _indices_de_linha_do_post(post):
    """Varre o POST e devolve `(maior_indice, chaves_nao_canonicas)`.

    R2-3 (rodada 2): deriva quantas linhas o POST REALMENTE contém a
    partir do próprio conteúdo enviado — nunca do campo oculto
    `num_linhas`. O achado 5 da rodada 1 ("nunca truncar partidas em
    silêncio") só tinha sido fechado por cima: um `num_linhas` INFLADO
    já não truncava (BL-91), mas um `num_linhas` MALFORMADO, vazio ou
    menor do que o conteúdo real ainda abria a porta de baixo. A causa
    real nunca foi o teto: é a view confiar num CONTADOR ENVIADO PELO
    CLIENTE para decidir quantos campos ler. `num_linhas` continua
    existindo, mas só para a EXIBIÇÃO — nunca mais para decidir quantas
    linhas LER.

    R3-2/BL-116 (rodada 3): a correção da rodada 2 fechou o CASO medido
    (`num_linhas` malformado) e deixou aberta a CLASSE — um índice fora
    do formato canônico ainda desaparecia em silêncio, com 302 de
    sucesso. Um índice é CANÔNICO quando é um inteiro entre 1 e
    `LINHAS_LEITURA_TETO_DE_SEGURANCA`, escrito em dígitos ASCII, SEM
    zero à esquerda, sinal ou qualquer caractere que não seja dígito —
    ou seja, exatamente `str(i)` para algum `i` inteiro nesse intervalo.
    QUALQUER outra coisa ("0", "01", "0001", "10000", "+3", " 3", um
    sufixo não numérico) é NÃO CANÔNICA: esta função devolve a chave
    INTEIRA em `chaves_nao_canonicas`, e quem chama DEVE recusar o POST
    inteiro (400, nomeando as chaves) — nunca ignorar a linha e seguir
    em frente, que foi exatamente a política que produziu o achado 5.

    A conversão em si é `_inteiro_de_cliente` (ver o docstring dela): um
    sufixo com dígito Unicode fora do ASCII, ou absurdamente longo (mais
    dígitos do que o limite de conversão do próprio Python), nunca lança
    exceção — vira "chave não entendida" (não canônica), não um 500 nem
    uma reinterpretação silenciosa.
    """
    maior = 0
    chaves_nao_canonicas = []
    for chave in post:
        casamento = _PADRAO_CHAVE_DE_LINHA.match(chave)
        if not casamento:
            continue
        prefixo = casamento.group(1)
        if prefixo != prefixo.lower():
            # A3 (rodada 4): "CONTA_3"/"Conta_3" — o template NUNCA emite
            # prefixo fora de minúsculas; um POST construído à mão com
            # capitalização diferente não é uma linha "que não existe", é
            # uma linha que ninguém olhou. Recusa, não ignora.
            chaves_nao_canonicas.append(chave)
            continue
        sufixo = casamento.group(2)
        indice = _inteiro_de_cliente(sufixo)
        if (
            indice is None
            or str(indice) != sufixo
            or indice < 1
            or indice > LINHAS_LEITURA_TETO_DE_SEGURANCA
        ):
            chaves_nao_canonicas.append(chave)
            continue
        if indice > maior:
            maior = indice
    return maior, chaves_nao_canonicas


def _linhas_lancamento_do_post(post, num_linhas):
    """Extrai as linhas PREENCHIDAS do formulário de lançamento a partir do
    POST bruto. Uma linha totalmente vazia é ignorada — o contador não
    precisa preencher as N linhas oferecidas. Uma linha PARCIALMENTE
    preenchida é um erro de formulário, reportado como tal.

    `valor_texto` é devolvido SEM `.strip()` (achado 2, DE-027): espaço em
    volta do valor é uma DIGITAÇÃO que `_decimal_do_formulario`/
    `para_decimal` devem julgar, não algo que esta função pode descartar
    antes — descartar em silêncio é exatamente a reinterpretação que o
    projeto decidiu nunca fazer. `conta_id` e `tipo` continuam com
    `.strip()`: são identificadores/opções de `<select>`, não texto de
    dinheiro, e não têm um julgador de formato próprio para delegar a
    checagem. A DECISÃO de "linha em branco" usa o valor JÁ testado por
    vazio (`.strip()` só para esta comparação), não o texto guardado.

    R3-1 (rodada 3, BL-115): `num_linhas` é capado em `LINHAS_LEITURA_
    TETO_DE_SEGURANCA` DENTRO desta função, defesa em profundidade —
    além de todo chamador já ser responsável por nunca passar um número
    vindo do cliente sem antes recusá-lo (ver `lancamento_novo`), esta
    função por si só nunca deve poder ser levada a iterar um número de
    vezes proporcional a um valor arbitrário. Nenhum `range()` deste
    módulo confia sozinho no chamador para ficar seguro.
    """
    num_linhas = min(num_linhas, LINHAS_LEITURA_TETO_DE_SEGURANCA)
    linhas = []
    erros = []
    for i in range(1, num_linhas + 1):
        conta_id = (post.get(f"conta_{i}") or "").strip()
        tipo = (post.get(f"tipo_{i}") or "").strip()
        valor_bruto = post.get(f"valor_{i}") or ""
        valor_em_branco = not valor_bruto.strip()
        if not conta_id and not tipo and valor_em_branco:
            continue
        if not conta_id or not tipo or valor_em_branco:
            erros.append(f"Linha {i}: preencha conta, tipo e valor, ou deixe a linha em branco.")
            continue
        linhas.append({"indice": i, "conta_id": conta_id, "tipo": tipo, "valor_texto": valor_bruto})
    return linhas, erros


def _veredito_fechamento(
    total_debito,
    total_credito,
    linhas_excluidas_do_total,
    num_partidas_validas,
    *,
    bloqueado_por_outro_erro=False,
):
    """Decide, em `Decimal`, um de três estados — `"fecha"`, `"nao_fecha"`
    ou `"nao_conferido"` — para o rodapé "Total conferido antes de gravar"
    do formulário de lançamento.

    BL-289 (A1 da auditoria DL-026 rodada 2): o TEMPLATE decidia sozinho,
    comparando os dois valores já formatados em pt-BR
    (`total_debito_ptbr == total_credito_ptbr`) — string, não `Decimal`.
    `_valor_ptbr(Decimal("0"))` devolve `"0,00"`, que é verdadeiro em
    template Django, e `"0,00" == "0,00"` também é verdadeiro: um
    formulário em BRANCO, duas linhas com valor inválido (descartadas do
    total) ou totais NEGATIVOS caíam todos no ramo "Fecha", incluindo o
    caso em que a própria tela já tinha avisado, duas linhas acima, que o
    que foi digitado não entrou na conta. Veredito é decisão de negócio;
    o template só EXIBE a chave que esta função devolve.

    As quatro condições de `"fecha"` cobrem `totais_batem` mais
    `len(itens) >= 2`, mais abaixo nesta view — mas NÃO bastam sozinhas
    para garantir a invariante exigida pela auditoria, "se a tela diz
    Fecha, gravar com o mesmo corpo tem de devolver 302, nunca 400" (ver
    `test_bl289_veredito_fechamento.py` e `test_bl307_*.py`). `criar_
    lancamento` só é chamado quando, ALÉM de débito == crédito > 0 e duas
    ou mais partidas, TAMBÉM não há nenhum outro erro (histórico maior que
    o teto, chave de idempotência maior que o teto, data inválida) — três
    condições que não têm relação nenhuma com débito, crédito ou linha
    excluída, e por isso não podiam ser expressas pelos quatro parâmetros
    originais desta função.
    `bloqueado_por_outro_erro` é exatamente essa quinta condição (BL-307,
    A1 da auditoria DL-026 rodada 3): quando `True`, "fecha" nunca é
    devolvido, mesmo que as partidas batam — dizer "Fecha" sobre um
    formulário que `criar_lancamento` vai recusar por um motivo alheio às
    partidas seria a MESMA mentira que a ausência de `linhas_excluidas_do_
    total` produzia, só que por outra causa. O padrão default (`False`)
    preserva o comportamento do caminho "adicionar_linha", que nunca
    valida histórico, chave ou data — ali "fecha" continua descrevendo
    somente a conferência das partidas, que é a única pergunta que aquele
    botão responde.

    `"nao_fecha"` exige duas ou mais partidas válidas e NENHUMA descartada
    — sem isso, "não fecha" seria dito sobre um total que ainda pode mudar
    assim que a linha pendente for corrigida, o que é ruído, não
    conferência. `"nao_fecha"` NÃO depende de `bloqueado_por_outro_erro`:
    débito e crédito genuinamente diferentes continuam sendo uma
    divergência real, ainda que exista também um erro de histórico ou data
    — não é uma afirmação falsa, é uma afirmação incompleta (o contador vê
    o outro erro na lista de mensagens, ao lado). Todo o resto (formulário
    em branco, linha descartada, total zerado, negativo, só uma partida
    válida, ou bloqueado por outro erro) é `"nao_conferido"` — nunca
    "Fecha" nem "Não fecha".
    """
    # `total_debito`/`total_credito` chegam `None` na primeira visita (GET
    # em branco) e nos ramos de erro que nunca calculam totais — tratados
    # como zero só para ESTA decisão (nunca exibidos como "0,00": ver
    # `total_debito_ptbr`/`total_credito_ptbr` abaixo, que continuam `None`
    # nesses casos).
    debito = total_debito if total_debito is not None else Decimal("0")
    credito = total_credito if total_credito is not None else Decimal("0")
    fecha = (
        debito == credito
        and debito > 0
        and linhas_excluidas_do_total == 0
        and num_partidas_validas >= 2
        and not bloqueado_por_outro_erro
    )
    if fecha:
        return "fecha"
    nao_fecha = num_partidas_validas >= 2 and linhas_excluidas_do_total == 0 and debito != credito
    if nao_fecha:
        return "nao_fecha"
    return "nao_conferido"


def _contexto_form_lancamento(
    empresa,
    contas_disponiveis,
    num_linhas,
    *,
    data_texto,
    historico,
    chave_idempotencia,
    linhas_preenchidas=None,
    total_debito=None,
    total_credito=None,
    linhas_excluidas_do_total=0,
    num_partidas_validas=0,
    bloqueado_por_outro_erro=False,
):
    # R3-1 (BL-115): defesa em profundidade — ver o comentário equivalente
    # em `_linhas_lancamento_do_post`. Esta função monta o CONTEXTO de
    # renderização; nunca deve poder ser levada a montar uma lista
    # proporcional a um `num_linhas` arbitrário.
    num_linhas = min(num_linhas, LINHAS_LEITURA_TETO_DE_SEGURANCA)
    linhas = []
    for i in range(1, num_linhas + 1):
        if linhas_preenchidas is not None:
            conta_id = linhas_preenchidas.get(f"conta_{i}", "")
            tipo = linhas_preenchidas.get(f"tipo_{i}", "")
            valor_texto = linhas_preenchidas.get(f"valor_{i}", "")
        else:
            conta_id, tipo, valor_texto = "", "", ""
        linhas.append({"indice": i, "conta_id": conta_id, "tipo": tipo, "valor_texto": valor_texto})

    # BL-286 (rodada 3 da DL-026, corrige o M2 da rodada 1): o veredito
    # "Não fecha" precisa dizer DE QUANTO, e quem calcula é o SERVIDOR, não
    # o template — o `especialista-frontend` já tinha parado exatamente
    # aqui, porque só recebia os dois totais como TEXTO pt-BR já formatado
    # (`total_debito_ptbr`/`total_credito_ptbr`), e subtrair dois valores
    # monetários já formatados dentro do template violaria a regra do
    # AGENTS.md contra aritmética financeira fora do motor determinístico.
    #
    # A subtração abaixo acontece em `Decimal`, sobre os totais de ORIGEM
    # (`total_debito`/`total_credito`, ainda não formatados) — nunca sobre
    # `total_debito_ptbr`/`total_credito_ptbr`. Ela NÃO passa por
    # `apps.core.dinheiro.quantizar`: essa função existe para reduzir a
    # ESCALA de um valor segundo uma política de arredondamento (DE-010,
    # obrigatória quando a redução pode perder informação), e aqui não há
    # redução nenhuma — cada item já foi recusado por `criar_lancamento`/
    # `_decimal_do_formulario` se tivesse mais de
    # `ESCALA_MAXIMA_LANCAMENTO_MANUAL` (2) casas decimais, então
    # `total_debito` e `total_credito` já chegam aqui com, no máximo, 2
    # casas — a diferença de dois valores com a MESMA escala máxima é
    # EXATA, sem arredondamento a decidir (mesmo raciocínio já aplicado a
    # `_saldo_por_natureza`/`_saldo_por_natureza_item`, em services.py, que
    # também subtraem débito e crédito em `Decimal` puro, sem política).
    # `_valor_ptbr` continua sendo o ÚNICO formatador pt-BR desta tela —
    # reaproveitado aqui, não reimplementado.
    # BL-289 (A1 da auditoria DL-026 rodada 2): o veredito em si — ver o
    # docstring de `_veredito_fechamento` para a classe de defeito que isto
    # substitui. Calculado ANTES da diferença abaixo porque a diferença só
    # pode ser exibida no ramo "nao_fecha" (nunca em "nao_conferido" — um
    # formulário com linha descartada, por exemplo, também tem
    # `total_debito != total_credito` textualmente, mas mostrar "faltam X"
    # ali ensinaria um número que pode mudar assim que a linha pendente for
    # corrigida).
    # BL-307: `bloqueado_por_outro_erro` propaga a quinta condição (ver o
    # docstring de `_veredito_fechamento`) — sempre `False` no caminho
    # "adicionar_linha", que não valida histórico, chave nem data.
    veredito_fechamento = _veredito_fechamento(
        total_debito,
        total_credito,
        linhas_excluidas_do_total,
        num_partidas_validas,
        bloqueado_por_outro_erro=bloqueado_por_outro_erro,
    )

    diferenca_fechamento_ptbr = None
    lado_faltante_fechamento = None
    if veredito_fechamento == "nao_fecha":
        diferenca_fechamento = abs(total_debito - total_credito)
        diferenca_fechamento_ptbr = _valor_ptbr(diferenca_fechamento)
        # O lado que "falta" é o menor total — é ELE que precisa crescer
        # para fechar. Nunca um valor negativo exibido (critério 1 do
        # BL-286): a diferença já sai em módulo acima, e o lado vem à
        # parte, como palavra, não como sinal.
        lado_faltante_fechamento = "débito" if total_debito < total_credito else "crédito"

    return {
        "empresa": empresa,
        "contas": contas_disponiveis,
        "linhas": linhas,
        "num_linhas": num_linhas,
        "data_texto": data_texto,
        "historico": historico,
        "chave_idempotencia": chave_idempotencia,
        "pode_adicionar_linha": num_linhas < LINHAS_MAXIMAS_LANCAMENTO,
        "linhas_maximas": LINHAS_MAXIMAS_LANCAMENTO,
        # RC-77/BL-205 — faixa de data de lançamento (01/01/2000 a hoje +
        # N dias), confirmada pelo Fred em 2026-09-15. Os dois valores vêm
        # de `apps.contabilidade.services`, fonte única, e chegam ao
        # template em DUAS formas porque servem a dois propósitos
        # diferentes:
        #
        # - ISO (`*_iso`) para os atributos `min`/`max` do `<input
        #   type="date">`. É CONVENIÊNCIA, nunca defesa: o atributo é do
        #   navegador, e quem monta a requisição à mão passa por cima dele
        #   — a recusa de verdade é de `criar_lancamento` (servidor), com
        #   teste próprio. DE-031 continua valendo: o campo segue sendo o
        #   seletor nativo e o rótulo não volta a afirmar formato.
        # - pt-BR (`*_ptbr`) para o texto de apoio, porque toda data
        #   EXIBIDA por este sistema é dd/mm/aaaa (critério 7) — inclusive
        #   quando ela aparece dentro de uma frase.
        "data_minima_iso": DATA_MINIMA_LANCAMENTO.isoformat(),
        "data_maxima_iso": data_maxima_lancamento().isoformat(),
        "data_minima_ptbr": DATA_MINIMA_LANCAMENTO,
        "data_maxima_ptbr": data_maxima_lancamento(),
        "total_debito_ptbr": _valor_ptbr(total_debito) if total_debito is not None else None,
        "total_credito_ptbr": _valor_ptbr(total_credito) if total_credito is not None else None,
        # BL-289: chave ÚNICA de decisão — "fecha" / "nao_fecha" /
        # "nao_conferido" —, calculada em `Decimal` por `_veredito_
        # fechamento`. O template RAMIFICA por ela; não volta a comparar
        # `total_debito_ptbr`/`total_credito_ptbr` (texto) entre si.
        "veredito_fechamento": veredito_fechamento,
        # BL-286: `None` fora do ramo "nao_fecha" — nunca "0,00", que seria
        # ruído (critério 2). Só a variante "não fecha" do template usa
        # estas duas chaves.
        "diferenca_fechamento_ptbr": diferenca_fechamento_ptbr,
        "lado_faltante_fechamento": lado_faltante_fechamento,
        # R2-5: quantas linhas ficaram FORA da soma acima (conta/tipo/valor
        # incompletos, ou valor/conta inválidos) — a conferência precisa
        # ANUNCIAR a exclusão, nunca só mostrar um total plausível e
        # batendo que ignora, em silêncio, o que está preenchido ao lado.
        "linhas_excluidas_do_total": linhas_excluidas_do_total,
    }


def _itens_e_totais(linhas_brutas, contas_por_id):
    """Converte as linhas BRUTAS do POST (já filtradas por
    `_linhas_lancamento_do_post`) em itens prontos para `criar_lancamento`,
    somando débito e crédito no caminho.

    Compartilhada pelos dois ramos que precisam do MESMO cálculo (achado 3
    / BL-88): "adicionar_linha" (só para mostrar o total de CONFERÊNCIA,
    nunca para gravar) e "gravar" (para decidir se pode gravar). Antes
    desta correção, "adicionar_linha" reconstruía o formulário sem chamar
    nada disto, e o rodapé "Total conferido antes de gravar" mostrava
    `0,00 / 0,00` com as linhas já preenchidas ao lado — o único total que
    esta tela mostra num caminho sem erro (não há JavaScript, critério 15)
    estava sempre errado.

    Uma linha com conta/tipo/valor inválido não interrompe o cálculo: ela
    soma um erro à lista devolvida e é EXCLUÍDA da soma. Para
    "adicionar_linha" isso é a conferência PARCIAL esperada enquanto o
    contador ainda digita (uma linha isolada errada não deve zerar o total
    das demais); para "gravar", a presença de qualquer erro na lista já
    impede a gravação mais abaixo, então a soma aqui não precisa ser
    "tudo ou nada" — ela só alimenta a mensagem de conferência.

    Devolve `(itens, erros, total_debito, total_credito)`.
    """
    itens = []
    erros = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for linha in linhas_brutas:
        # A1 (rodada 4 da auditoria da DL-017): `linha["conta_id"].isdigit()`
        # sozinho aceitava dígito Unicode (`"７".isdigit()` é `True`, e o
        # `int()` seguinte reinterpretava em silêncio como a conta 7) e não
        # protegia o `int()` de um texto de mais de 4300 dígitos —
        # `ValueError` cru, 500. `conta_id` É um identificador de banco
        # (não uma quantidade de negócio), então usa `_identificador_de_
        # cliente` — o mesmo julgador (`para_id`) que a API e
        # `apps.tenancy` já usam para a idêntica invariante (ver o
        # comentário de importação de `para_id`, no topo do arquivo).
        conta_id = _identificador_de_cliente(linha["conta_id"])
        conta = contas_por_id.get(conta_id) if conta_id is not None else None
        if conta is None:
            # Também cobre o caso de um `conta_id` de OUTRA empresa (não
            # está em `contas_por_id`, que só tem contas DESTA empresa) —
            # nunca vaza para a mensagem de erro qual empresa seria, só que
            # a conta é inválida.
            erros.append(f"Linha {linha['indice']}: conta inválida.")
            continue
        try:
            valor = _decimal_do_formulario(linha["valor_texto"])
        except ValorMonetarioInvalido:
            # R2-1/DE-029: a mensagem ENSINA o formato em vez de só dizer
            # "inválido" — é a exigência da própria decisão ("recusa com
            # mensagem que ensina o formato"), no lugar onde o contador de
            # fato lê o erro (o rodapé de mensagens da tela).
            erros.append(
                f"Linha {linha['indice']}: valor “{linha['valor_texto']}” inválido. Use "
                "dígitos, ponto a cada três casas como separador de milhar "
                "(ex.: 1.000) e vírgula para os centavos (ex.: 1.000,00)."
            )
            continue
        # Mesmo teto de MAGNITUDE que a API já verifica em `_extrair_itens`
        # (views.py) antes de chamar `criar_lancamento` — achado da
        # varredura desta rodada (critério de aceite 1): `criar_lancamento`
        # (services.py) verifica sinal e ESCALA (casas decimais), mas nunca
        # magnitude; sem este limite AQUI, um valor cujo módulo não caiba
        # em `ItemLancamento.valor` (DecimalField max_digits=18,
        # decimal_places=2) passa por toda validação de domínio e só falha
        # no INSERT do Postgres com `DataError: numeric field overflow` —
        # 500, não 400, exatamente a MESMA classe de defeito dos achados 1
        # e 4, num caminho que o auditor não tinha percorrido ainda.
        if abs(valor) >= LIMITE_MAGNITUDE_VALOR:
            # A mensagem usa o TEXTO digitado, não `_valor_ptbr(valor)`: um
            # valor deste tamanho (por definição, aqui) pode ter centenas
            # de dígitos, e `_valor_ptbr` faz `.quantize(Decimal("0.01"))`
            # — que levanta `decimal.InvalidOperation` quando o resultado
            # excede a precisão do contexto decimal (28 dígitos, ver o
            # docstring de `quantizar` em apps/core/dinheiro.py). Formatar
            # o valor recusado por ser grande demais CRIARIA um 500 novo,
            # exatamente a classe de defeito que esta checagem existe para
            # fechar. `LIMITE_MAGNITUDE_VALOR` (10**16) é pequeno e seguro
            # de formatar.
            erros.append(
                f"Linha {linha['indice']}: valor “{linha['valor_texto']}” é grande demais "
                f"para um item de lançamento; o módulo deve ser menor que "
                f"{_valor_ptbr(LIMITE_MAGNITUDE_VALOR)}."
            )
            continue
        if linha["tipo"] not in (TipoPartida.DEBITO, TipoPartida.CREDITO):
            erros.append(f"Linha {linha['indice']}: tipo de partida inválido.")
            continue
        itens.append({"conta": conta, "tipo": linha["tipo"], "valor": valor})
        if linha["tipo"] == TipoPartida.DEBITO:
            total_debito += valor
        else:
            total_credito += valor
    return itens, erros, total_debito, total_credito


def _linhas_a_reexibir_do_post(post):
    """Quantas linhas um caminho de RECUSA precisa devolver à tela, derivado
    do CONTEÚDO REAL do POST — nunca um número fixo.

    R6-5/BL-199 (rodada 6): `_recusa_lancamento_com_erro` passava
    `LINHAS_INICIAIS_LANCAMENTO` (4) **fixo**, enquanto o caminho de
    gravação, 200 linhas abaixo, deriva `num_linhas_leitura` do conteúdo do
    POST justamente para não perder linha. Medido pelo auditor com 8 linhas
    preenchidas: voltavam 4, e as outras 4 o contador digitava de novo —
    numa função cujo docstring promete "o formulário RE-RENDERIZADO com o
    que já estava preenchido (nunca uma tela em branco)". Para
    `request.FILES` isso era anterior à rodada 6; para `request.GET` e para
    o cabeçalho era novo, e triplicou a exposição.

    A derivação tem a mesma FORMA do caminho de gravação, pela mesma razão
    (R2-3): o campo oculto `num_linhas` não decide quantas linhas existem —
    o CONTEÚDO decide. O teto de SEGURANÇA fecha por cima (o
    `_contexto_form_lancamento` também capa, defesa em profundidade): nem
    aqui um `num_linhas` arbitrário dimensiona a página.

    **O piso NÃO é o mesmo, e é deliberado** (resíduo do BL-199 apontado
    pelo `desenvolvedor-pleno` na varredura de afirmações; antes esta frase
    dizia "a MESMA", o que era falso): a gravação usa piso 2 porque lá
    `num_linhas_exibicao` também serve ao botão "+ linha", que precisa
    poder trabalhar com duas linhas; **um formulário RECUSADO volta com o
    piso da tela INICIAL** (`LINHAS_INICIAIS_LANCAMENTO`), para nunca
    oferecer menos linhas do que um formulário novo. A escolha não perde
    nada digitado em nenhum dos dois pisos — o piso só acrescenta linha em
    BRANCO —, e está travada por
    `test_piso_de_reexibicao_e_o_da_tela_INICIAL_e_nao_o_da_gravacao`
    (test_dl019_frontend_recusa_do_formulario_de_lancamento.py).

    `num_linhas` não entra no `max`: um campo oculto inflado (ou absurdo,
    acima do teto de segurança) faria esta função devolver uma página
    proporcional ao que o cliente mandou, exatamente o que o parágrafo
    acima diz que não acontece. Para um POST de formulário REAL isso não
    muda nada — o `<form>` emite as chaves de todas as linhas que
    renderizou, então o maior índice presente JÁ é o número de linhas
    exibidas.
    """
    maior_indice, _ = _indices_de_linha_do_post(post)
    return min(
        max(LINHAS_INICIAIS_LANCAMENTO, maior_indice),
        LINHAS_LEITURA_TETO_DE_SEGURANCA,
    )


def _recusa_lancamento_com_erro(request, empresa, contas_disponiveis, mensagem):
    """Recusa a tentativa de POST em `lancamento_novo` com `mensagem`,
    devolvendo o formulário RE-RENDERIZADO com **tudo** o que já estava
    preenchido (nunca uma tela em branco, nunca só as primeiras linhas) e
    `status=400`. Ponto único para os "dicionários da requisição" que esta
    view recusa por completo, nunca ignora em silêncio — hoje julgados por
    `apps.core.requisicao` (BL-196), antes três `if` escritos à mão aqui
    (`request.FILES`, A3/BL-128; `request.GET` e o cabeçalho
    `Idempotency-Key`, R5-6/BL-145).

    R6-5/BL-199: o número de linhas re-exibidas vem de
    `_linhas_a_reexibir_do_post` (ver o docstring dela) — era aqui que as
    linhas além da quarta se perdiam.
    """
    messages.error(request, mensagem)
    contexto = _contexto_form_lancamento(
        empresa,
        contas_disponiveis,
        _linhas_a_reexibir_do_post(request.POST),
        data_texto=request.POST.get("data", ""),
        historico=request.POST.get("historico", "").strip(),
        chave_idempotencia=request.POST.get("chave_idempotencia") or uuid.uuid4().hex,
        linhas_preenchidas=request.POST,
    )
    return render(request, "contabilidade/lancamento_form.html", contexto, status=400)


# ---------------------------------------------------------------------------
# BL-196/R6-2 — a política dos cinco dicionários aplicada às DUAS telas de
# POST deste arquivo. O julgamento é de `apps.core.requisicao`; aqui ficam
# a DECLARAÇÃO de cada contrato e a RESPOSTA de tela.
# ---------------------------------------------------------------------------


# Campos que o `<form>` de lançamento REALMENTE emite, fora as linhas
# (dinâmicas, tratadas abaixo). `csrfmiddlewaretoken` está aqui porque é
# enviado pelo `{% csrf_token %}` do próprio template: sem declará-lo, o
# contrato recusaria o formulário legítimo — o que seria a forma mais
# rápida possível de alguém "consertar" isto declarando `campos=None` e
# reabrindo o buraco.
_CAMPOS_FIXOS_DO_FORMULARIO_DE_LANCAMENTO = frozenset(
    {"csrfmiddlewaretoken", "acao", "num_linhas", "data", "historico", "chave_idempotencia"}
)


def _contrato_do_formulario_de_lancamento(post):
    """Contrato desta tela para ESTE POST.

    `campos` é declarado **explicitamente** (nunca `None`): os fixos acima,
    mais as chaves de linha presentes no POST que TÊM a forma de chave de
    linha (`conta_*`/`tipo_*`/`valor_*`, por `_PADRAO_CHAVE_DE_LINHA`).

    A divisão de trabalho com `_indices_de_linha_do_post` é deliberada e
    não é frouxidão: o contrato julga se o NOME do campo pertence ao
    vocabulário desta tela; `_indices_de_linha_do_post` julga se o ÍNDICE é
    canônico, e recusa `conta_0001`, `CONTA_3`, `conta_+3` com a mensagem
    específica que o auditor mediu como correta (R3-2/BL-116, A3/rodada 4).
    Se o contrato recusasse essas chaves primeiro, o contador passaria a
    ler "campo não reconhecido" no lugar de "índice de linha fora do
    formato esperado" — mensagem pior para o mesmo defeito, e três testes
    de texto quebrados. Nenhuma chave fica sem julgamento: o que o contrato
    deixa passar aqui, a canonicidade recusa na linha seguinte da view.
    """
    chaves_de_linha = {chave for chave in post if _PADRAO_CHAVE_DE_LINHA.match(chave)}
    return ContratoDeRequisicao(
        campos=_CAMPOS_FIXOS_DO_FORMULARIO_DE_LANCAMENTO | chaves_de_linha,
        # Esta tela nunca ofereceu upload, e não tem contrato de
        # querystring — ver `_mensagem_de_tela_para_dado_nao_contratado`
        # para a razão CERTA de recusar querystring (a razão que estava
        # escrita aqui era factualmente falsa sobre HTML).
        aceita_arquivo=False,
        aceita_querystring=False,
        # A chave de idempotência desta tela É o campo oculto do próprio
        # formulário. Quem manda `Idempotency-Key` por cabeçalho (o
        # contrato da API, não desta tela) e omite o campo do corpo recebia
        # uma chave nova a cada POST e GRAVAVA DUAS VEZES — a duplicidade
        # que a chave existe para impedir, na superfície errada
        # (R5-6/BL-145).
        cabecalhos_ignorados=("Idempotency-Key",),
        contexto="no formulário de lançamento",
    )


# Campos que o `<form>` de conta REALMENTE emite. `aceita_lancamento` é
# caixa de marcação (só vem quando marcada) e `confirmar_conta_sem_conta_
# mae` é o botão de confirmação do RC-80/BL-208 — os dois são legítimos e
# precisam estar declarados.
# DL-045 fatia 3: "classificacao_dre" entrou no conjunto — o formulário de
# `conta_nova` (único que usa este contrato nesta etapa — ver o docstring
# de `ContaCriarForm` sobre a tela de edição, ainda inexistente) passou a
# emitir esse campo a mais. DL-048/CTB-12: "classificacao_dlpa" entra pelo
# mesmo motivo e pelo mesmo caminho.
_CONTRATO_DO_FORMULARIO_DE_CONTA = ContratoDeRequisicao(
    campos=frozenset(
        {
            "csrfmiddlewaretoken",
            "codigo",
            "nome",
            "tipo",
            "natureza",
            "conta_pai",
            "aceita_lancamento",
            "classificacao_dre",
            "classificacao_dlpa",
            # DL-063 (BL-606): o formulário passou a emitir este campo, e sem
            # esta linha o POST voltaria 400 com "dado não contratado" — a
            # mesma razão dos dois acima.
            "classificacao_dmpl",
            "confirmar_conta_sem_conta_mae",
        }
    ),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de conta",
)

# DL-045, correção da rodada 1 de auditoria (A7): formulário de UM campo
# só — a Linha da DRE de uma conta existente (`conta_classificacao_dre`,
# mais abaixo). Contrato PRÓPRIO (não reaproveita `_CONTRATO_DO_
# FORMULARIO_DE_CONTA`): são telas diferentes, com campos diferentes —
# esta nunca emite "codigo"/"nome"/"tipo"/etc.
_CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DRE = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "classificacao_dre"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na classificação da linha da DRE",
)

# DL-048/CTB-12: o MESMO contrato de um campo para a tela irmã da DLPA —
# telas diferentes, campos diferentes, um contrato por tela (nunca um
# contrato reaproveitado com campo a mais, que a varredura não alcança).
_CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DLPA = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "classificacao_dlpa"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na classificação da linha da DLPA",
)


# DL-061/CTB-14: o mesmo contrato de um campo para a tela da DMPL.
_CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DMPL = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "classificacao_dmpl"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na classificação da coluna da DMPL",
)

# DL-066/CTB-15: o mesmo contrato para a tela da DFC — TRÊS campos (os dois
# marcadores são enviados mesmo desligados: desmarcar é decisão, e o serviço
# recebe estado desejado completo, nunca patch). Um contrato por tela, pelo
# mesmo motivo das irmãs acima.
_CONTRATO_DO_FORMULARIO_DE_CLASSIFICACAO_DFC = ContratoDeRequisicao(
    campos=frozenset(
        {
            "csrfmiddlewaretoken",
            "caixa_e_equivalentes",
            "classificacao_dfc",
            "item_de_resultado_sem_caixa",
        }
    ),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na classificação da DFC",
)

# DL-061, fatia 2 (BL-605): o contrato da guia "DMPL" do lançamento. Os
# campos são REPETIDOS — uma tripla `linha`/`coluna`/`valor` por marcação do
# conjunto (o mesmo conjunto que `salvar_marcacoes_da_dmpl` recebe, de uma
# vez) — mais `acao` (`salvar`/`remover`) e o `csrfmiddlewaretoken` do
# `{% csrf_token %}`. Nomes repetidos se repetem como UMA chave só em
# `request.POST` (que é o que este contrato julga); quem lê a ordem das
# triplas é `_marcacoes_do_formulario_de_marcacao`, por `getlist`.
_CONTRATO_DO_FORMULARIO_DE_MARCACAO_DMPL = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "acao", "linha", "coluna", "valor"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na marcação manual da DMPL do lançamento",
)


def _mensagem_de_tela_para_dado_nao_contratado(excecao, *, explicacao_extra=""):
    """Traduz `DadoNaoContratado` para a frase que ESTA superfície mostra.

    Decide por `excecao.dicionario` (constante estável), nunca pelo texto da
    mensagem do módulo: comparar texto amarraria a tela à redação de
    `apps.core.requisicao`, e a primeira reformulação lá quebraria o
    português daqui sem nenhum aviso.

    Por que recusar QUERYSTRING num POST, agora com a razão certa
    (R6-5/BL-199): a justificativa anterior dizia que "nenhum formulário
    renderizado por esta tela produz querystring num POST (o `<form>` não
    tem `action=`)" — e era **falsa sobre HTML**, como o auditor mediu: um
    `<form>` SEM `action` envia para a URL do próprio documento,
    querystring incluída. Quem chegasse à tela por um link com
    `?utm_source=...` não conseguia gravar. Duas mudanças fecham isso: os
    dois formulários passaram a declarar `action` explícito e sem
    querystring (ver os templates, e o teste que lê o atributo), e a razão
    escrita passou a ser a verdadeira — **esta tela não tem contrato de
    querystring**: nenhum parâmetro de URL altera o que ela grava, então um
    parâmetro presente é dado que ninguém vai ler, e dado que ninguém lê se
    recusa nomeando.
    """
    chaves = "; ".join(excecao.chaves)
    if excecao.dicionario == DICIONARIO_ARQUIVO:
        return (
            "Este formulário não aceita arquivo nenhum. Campo(s) enviados como "
            f"arquivo, recusados por completo: {chaves}. Nada foi gravado."
        )
    if excecao.dicionario == DICIONARIO_QUERYSTRING:
        return (
            "Este formulário não aceita parâmetros na URL — nenhum deles altera o "
            f"que ele grava. Parâmetro(s) recusados por completo: {chaves}. Nada "
            "foi gravado. Abra a tela pelo menu do sistema, sem parâmetros na "
            "URL, e envie de novo."
        )
    if excecao.dicionario == DICIONARIO_CABECALHO:
        return (
            f"Este formulário não usa o cabeçalho '{chaves}'. Reenvie sem esse "
            f"cabeçalho — ele não tem efeito nenhum aqui. {explicacao_extra}".strip()
        )
    return (
        f"Não reconheço o(s) campo(s) enviado(s): {chaves}. Nada foi gravado — um "
        "campo que esta tela não lê nunca é ignorado em silêncio."
    )


@login_required
@require_http_methods(["GET", "POST"])
def lancamento_novo(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, "Seu papel não permite lançar nesta empresa.")

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    # Só contas que aceitam lançamento direto e estão ativas entram na
    # lista de escolha — restringe o que a tela OFERECE para digitar, não
    # o que o Plano de Contas MOSTRA (essa tela continua listando tudo,
    # inclusive inativas: "não esconder informação contábil" é sobre
    # RELATÓRIO, não sobre a lista de opções de um formulário de entrada).
    contas_disponiveis = list(
        Conta.objects.filter(empresa=empresa, aceita_lancamento=True, ativo=True).order_by("codigo")
    )

    if request.method == "POST":
        # BL-196/R6-2 (rodada 6): UMA chamada, no lugar dos três `if`
        # escritos à mão que existiam aqui (e de nenhum em `conta_nova`).
        # A política é a de `apps.core.requisicao`, a ordem de avaliação é
        # a declarada lá (`ORDEM_DE_AVALIACAO`: arquivo, querystring,
        # cabeçalho, corpo) — a MESMA ordem em que esta view já recusava,
        # de propósito: a mensagem que o contador vê quando manda dois
        # erros de uma vez é comportamento observável, com teste em cima.
        #
        # Por que cada dicionário é recusado está no contrato
        # (`_contrato_do_formulario_de_lancamento`) e na tradução da
        # mensagem (`_mensagem_de_tela_para_dado_nao_contratado`), não
        # repetido aqui. O histórico dos achados que produziram cada um:
        # `request.FILES` = A3/BL-128 (um par de partidas completo e
        # balanceado enviado como campo de ARQUIVO sumia da tela, do total
        # e do aviso, e o resto gravava com 302 "sucesso"); `request.GET` e
        # o cabeçalho `Idempotency-Key` = R5-6/BL-145; campo desconhecido
        # no corpo = R6-2, que fechou na API e não na tela.
        try:
            recusar_dado_nao_contratado(
                request, _contrato_do_formulario_de_lancamento(request.POST)
            )
        except DadoNaoContratado as exc:
            return _recusa_lancamento_com_erro(
                request,
                empresa,
                contas_disponiveis,
                _mensagem_de_tela_para_dado_nao_contratado(
                    exc,
                    explicacao_extra=(
                        "O campo oculto do próprio formulário já garante que "
                        "reenviar a mesma tentativa não duplica o lançamento."
                    ),
                ),
            )

        acao = request.POST.get("acao")
        # A1/rodada 4 — mesma varredura: `num_linhas` é texto de
        # cliente virando `int()`, então passa por `_inteiro_de_cliente`
        # como qualquer outro campo deste arquivo (ver o docstring dela) —
        # nunca reinterpreta dígito Unicode, nunca lança exceção. Ausente
        # ou malformado cai no padrão de linhas iniciais, do mesmo jeito
        # que o `try/except` anterior já fazia — só que agora sem precisar
        # de uma cláusula `except` com mais de um tipo (a sintaxe que deu
        # origem ao R3-4/BL-118 nem chega a existir aqui).
        num_linhas_campo = _inteiro_de_cliente(request.POST.get("num_linhas", ""))
        if num_linhas_campo is None:
            num_linhas_campo = LINHAS_INICIAIS_LANCAMENTO

        data_texto = request.POST.get("data", "")
        historico = request.POST.get("historico", "").strip()
        # Idempotência (BL-43 / critério 11): o MESMO token acompanha toda
        # esta tentativa — inclusive um duplo clique, que envia duas
        # requisições com o MESMO corpo (o mesmo campo oculto), sem
        # depender de JavaScript nenhum. `criar_lancamento` (services.py)
        # já sabe devolver o MESMO lançamento em vez de duplicar quando o
        # conteúdo bate (ver o docstring de `criar_lancamento`).
        chave_idempotencia = request.POST.get("chave_idempotencia") or uuid.uuid4().hex

        # R3-1 (rodada 3, BL-115, BLOQUEADOR — "um POST prende a
        # requisição indefinidamente"): `num_linhas_campo` vem de um campo
        # OCULTO do formulário — o cliente controla o valor por completo
        # (um clique no inspetor do navegador). ANTES desta correção, um
        # `num_linhas` grande o bastante (`10**12`, `"9" * 4000`)
        # sobrevivia ao `int()` (o único limite era o de CONVERSÃO do
        # próprio Python, 4300 dígitos) e se propagava, via `max()`, para
        # `num_linhas_exibicao` e depois para `num_linhas_leitura` — SEM
        # NUNCA passar pelo teto de segurança, porque aquele teto só
        # capava o valor DERIVADO do conteúdo do POST, nunca o campo
        # oculto em si. O resultado era um `range()` dimensionado por um
        # inteiro arbitrário do cliente, nos DOIS ramos (`gravar` e
        # `adicionar_linha`) — 26 s de bloqueio medidos para 10 milhões, e
        # NENHUM retorno em 45 s para `10**12`. Com `gunicorn` sem
        # `--workers` (um único *worker* síncrono, o mesmo comando do
        # `docker-compose.yml` — o caminho pelo qual o Fred sobe o
        # sistema), um único POST autenticado deixa o sistema inteiro sem
        # resposta: não corrompe dado, **nega o serviço**.
        #
        # A classe (não só o caso): nenhum número vindo do cliente
        # dimensiona laço, alocação ou repetição nesta view — em NENHUM
        # ramo. A correção é recusar ANTES DE QUALQUER LEITURA, nos dois
        # ramos ao mesmo tempo (este `if` roda antes do `if acao ==
        # "adicionar_linha"` abaixo): nenhum valor vindo do cliente chega
        # perto de um `max()`, um `min()` ou um `range()` sem primeiro
        # passar por este teto.
        if num_linhas_campo > LINHAS_LEITURA_TETO_DE_SEGURANCA:
            messages.error(
                request,
                "'num_linhas' inválido: o formulário aceita no máximo "
                f"{LINHAS_MAXIMAS_LANCAMENTO} partidas por lançamento.",
            )
            # R6-5/BL-199, segunda rodada da DL-020: o número de linhas
            # re-exibidas vem do PONTO ÚNICO de derivação, como em toda
            # recusa desta tela. Era `LINHAS_INICIAIS_LANCAMENTO` fixo, e
            # perdia o que estivesse digitado além da quarta linha —
            # mesmo defeito do achado R6-5, no caminho vizinho. Derivar do
            # conteúdo é seguro aqui justamente porque
            # `_linhas_a_reexibir_do_post` NÃO olha o campo oculto: é o
            # `num_linhas` absurdo que acabou de ser recusado, e ele não
            # pode dimensionar a página (R3-1/BL-115).
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                _linhas_a_reexibir_do_post(request.POST),
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
            )
            return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

        # `num_linhas_campo` (o campo OCULTO do formulário) decide só
        # quantas linhas a tela EXIBE de volta a partir de agora — NUNCA
        # mais quantas linhas são LIDAS do POST (ver abaixo). Piso de 2 é
        # só para exibição, não afeta leitura. Já garantidamente dentro do
        # teto de segurança pela recusa acima.
        num_linhas_exibicao = max(2, num_linhas_campo)

        # R2-3 (rodada 2) + R3-2/BL-116 (rodada 3): a quantidade REAL de
        # linhas a LER vem do próprio CONTEÚDO do POST
        # (`_indices_de_linha_do_post`), nunca só do campo oculto — um
        # `num_linhas` malformado, vazio ou menor do que o conteúdo real
        # não pode fazer esta view ler MENOS campos do que os que o
        # cliente de fato enviou (R2-3). E QUALQUER chave
        # `conta_*`/`tipo_*`/`valor_*` fora do índice CANÔNICO (ver o
        # docstring daquela função) é RECUSADA, nunca ignorada (R3-2): era
        # assim que um par de linhas completo (débito e crédito batendo
        # entre si) desaparecia em silêncio, com HTTP 302 "gravado com
        # sucesso", quando o índice tinha zero à esquerda, sinal, espaço
        # ou 5+ dígitos.
        maior_indice, chaves_nao_canonicas = _indices_de_linha_do_post(request.POST)
        if chaves_nao_canonicas:
            messages.error(
                request,
                "Não entendi os seguintes campos do formulário — índice de "
                "linha fora do formato esperado, nunca reinterpretado nem "
                "ignorado: " + "; ".join(sorted(chaves_nao_canonicas)) + ".",
            )
            # R6-5/BL-199, segunda rodada da DL-020: era
            # `num_linhas_exibicao` — derivado do campo OCULTO, sem o maior
            # índice realmente presente —, e MEDIDO perdendo as linhas 5 a
            # 8 de um POST com oito linhas e `num_linhas=4`. É o defeito do
            # achado R6-5 no caminho vizinho de dentro da mesma view
            # (DE-034, item 1). Agora o mesmo ponto único de derivação de
            # toda recusa desta tela.
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                _linhas_a_reexibir_do_post(request.POST),
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
            )
            return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

        num_linhas_leitura = max(num_linhas_exibicao, maior_indice)

        contas_por_id = {conta.id: conta for conta in contas_disponiveis}

        if acao == "adicionar_linha":
            # Só acrescenta uma linha em branco e re-renderiza — NUNCA
            # grava nada. É a forma de a tela funcionar sem JavaScript
            # (critério 15): cada "+ linha" é um novo GET/POST normal.
            num_linhas_exibicao = min(num_linhas_exibicao + 1, LINHAS_MAXIMAS_LANCAMENTO)
            num_linhas_leitura = max(num_linhas_leitura, num_linhas_exibicao)
            # Achado 3 / BL-88 (rodada 1) + R2-3/R2-5 (rodada 2): as linhas
            # JÁ enviadas neste POST alimentam o MESMO cálculo de totais
            # que "gravar" usa (`_itens_e_totais`) — "Adicionar linha" é o
            # único botão de conferência que esta tela tem sem JavaScript.
            # Lê TODAS as linhas realmente presentes no POST
            # (`num_linhas_leitura`, não só as que serão re-exibidas): uma
            # linha preenchida além do que a página mostra de volta não
            # pode desaparecer do total sem aviso. R2-5: os erros desta
            # extração (linha incompleta, conta/valor inválidos) não são
            # mais descartados em silêncio — a CONTAGEM de quantas linhas
            # ficaram fora do total é anunciada na tela
            # (`linhas_excluidas_do_total`, no contexto e no template):
            # antes, o rodapé podia mostrar dois valores "batendo" que
            # ignoravam, sem uma palavra, uma linha preenchida ao lado —
            # e "batendo" é exatamente o sinal que convida a gravar.
            linhas_brutas, erros_incompletas = _linhas_lancamento_do_post(
                request.POST, num_linhas_leitura
            )
            itens_conf, erros_itens_conf, total_debito, total_credito = _itens_e_totais(
                linhas_brutas, contas_por_id
            )
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                num_linhas_exibicao,
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
                total_debito=total_debito,
                total_credito=total_credito,
                linhas_excluidas_do_total=len(erros_incompletas) + len(erros_itens_conf),
                # BL-289: quantas partidas VÁLIDAS entraram na soma acima —
                # o veredito "fecha"/"nao_fecha" exige pelo menos duas,
                # mesma exigência de `criar_lancamento` mais abaixo.
                num_partidas_validas=len(itens_conf),
            )
            return render(request, "contabilidade/lancamento_form.html", contexto)

        # Qualquer outro valor de 'acao' (normalmente "gravar") é tratado
        # como tentativa de gravação — nunca perde silenciosamente o que
        # foi digitado.
        if num_linhas_leitura > LINHAS_MAXIMAS_LANCAMENTO:
            # Achado 5 / BL-91 (rodada 1) + R2-3 (rodada 2): recusa o POST
            # inteiro — nunca processa só as primeiras
            # LINHAS_MAXIMAS_LANCAMENTO e descarta o resto em silêncio. A
            # comparação usa `num_linhas_leitura` (derivado do CONTEÚDO
            # real do POST) — não o campo oculto: um `num_linhas`
            # malformado ou reduzido não pode abrir, por baixo, a mesma
            # porta que um `num_linhas` inflado já não abre mais por cima.
            # Era exatamente por cima que um lote de 22 partidas (as 20
            # primeiras batendo, e as 2 últimas TAMBÉM batendo entre si)
            # fechava com "sucesso" perdendo 77,00 de débito e 77,00 de
            # crédito — perda silenciosa de fato contábil que nenhuma
            # conferência posterior aponta porque o que sobrou também
            # fecha balanceado. Em escrituração: recusa, nunca ajusta.
            #
            # R2-10 (rodada 2): a recusa não pode SOMAR uma segunda perda
            # à primeira — a tela volta a exibir só as primeiras
            # LINHAS_MAXIMAS_LANCAMENTO linhas (exibir todas as enviadas
            # deixaria esta view renderizar uma página proporcional a
            # quantas linhas um POST arbitrário mandasse), mas os valores
            # das linhas que excederam o teto são repetidos na própria
            # MENSAGEM de recusa, para que copiá-los para um segundo
            # lançamento não dependa de o contador tê-los memorizado.
            linhas_excedentes, _ = _linhas_lancamento_do_post(request.POST, num_linhas_leitura)
            linhas_excedentes = [
                linha for linha in linhas_excedentes if linha["indice"] > LINHAS_MAXIMAS_LANCAMENTO
            ]
            mensagem = (
                f"Este formulário aceita no máximo {LINHAS_MAXIMAS_LANCAMENTO} partidas "
                f"por lançamento; foram enviadas {num_linhas_leitura}. Nada foi gravado. "
                "Copie os dados abaixo para um segundo lançamento, ou peça ao "
                "administrador do escritório para avaliar um teto maior."
            )
            if linhas_excedentes:
                resumo = "; ".join(
                    f"linha {linha['indice']} ({linha['tipo'] or '?'}, "
                    f"{linha['valor_texto'] or '?'})"
                    for linha in linhas_excedentes
                )
                mensagem += f" Linhas que não couberam: {resumo}."
            messages.error(request, mensagem)
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                LINHAS_MAXIMAS_LANCAMENTO,
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
            )
            return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

        linhas_brutas, erros = _linhas_lancamento_do_post(request.POST, num_linhas_leitura)
        # BL-307 (A1 da auditoria DL-026 rodada 3): contagem separada, ANTES
        # de `erros` receber qualquer mensagem que não seja sobre uma LINHA
        # descartada (histórico grande demais, chave de idempotência grande
        # demais) — essas duas não excluem partida nenhuma do total, e
        # somá-las aqui inflaria `linhas_excluidas_do_total` com motivo que
        # não é "linha fora da soma". O aviso R2-5 ("N linha(s) … ainda NÃO
        # entram no total abaixo") e o veredito "Fecha" (`_veredito_
        # fechamento`) dependem deste número estar certo NESTA MESMA
        # resposta — não só no ramo "adicionar_linha" (ver o comentário
        # abaixo, onde o valor é finalmente passado a `_contexto_form_
        # lancamento`).
        linhas_incompletas = len(erros)

        # Achado 4 / BL-90: mesmo teto do modelo (`historico =
        # CharField(max_length=300)`) verificado AQUI, antes de qualquer
        # tentativa de gravação — sem isto, o único guarda era o
        # `maxlength="300"` do HTML (proteção de NAVEGADOR, nunca de
        # servidor — AGENTS.md §1), e um POST direto com histórico maior
        # chegava ao INSERT do Postgres como `DataError: value too long
        # for type character varying(300)`, um 500 cru. O formulário de
        # conta é `ModelForm` e o Django já cuida disto sozinho; este é o
        # único formulário escrito à mão da entrega, e por isso o único
        # que precisa desta checagem explícita.
        if len(historico) > TAMANHO_MAXIMO_HISTORICO:
            erros.append(f"O histórico não pode ter mais de {TAMANHO_MAXIMO_HISTORICO} caracteres.")

        # Mesma classe de defeito dos achados 1 e 4, encontrada na
        # varredura desta rodada (critério de aceite 1): `chave_
        # idempotencia` é um campo OCULTO do formulário (o navegador nunca
        # o alonga sozinho), mas nada nesta view impedia um POST direto com
        # um valor maior que `LancamentoContabil.chave_idempotencia`
        # (CharField max_length=255) — reproduzido e confirmado
        # (`DataError: value too long for type character varying(255)`, um
        # 500 cru) antes desta correção. A API já tem o mesmo limite
        # (`TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA`, views.py); aqui é o mesmo
        # valor, reaproveitado, não duplicado.
        if len(chave_idempotencia) > TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA:
            erros.append(
                "A chave de idempotência não pode ter mais de "
                f"{TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA} caracteres."
            )

        itens, erros_itens, total_debito, total_credito = _itens_e_totais(
            linhas_brutas, contas_por_id
        )
        erros = erros + erros_itens
        # BL-307: as duas fontes de linha EXCLUÍDA da soma — incompleta
        # (`linhas_incompletas`, capturada acima) e inválida (`erros_itens`,
        # que acabou de sair de `_itens_e_totais`) — exatamente a mesma
        # conta que "adicionar_linha" já passa (`len(erros_incompletas) +
        # len(erros_itens_conf)`, mais acima nesta view). Antes desta
        # correção este ramo não calculava nada e `_contexto_form_
        # lancamento` recebia o padrão `linhas_excluidas_do_total=0` —
        # fazendo o veredito "Fecha" aparecer numa resposta 400 sempre que
        # débito e crédito das linhas VÁLIDAS batiam, mesmo com uma linha
        # descartada ao lado (A1 da auditoria DL-026 rodada 3).
        linhas_excluidas_do_total = linhas_incompletas + len(erros_itens)

        # R5-4/BL-143: mesmo julgador partilhado do período (ver o
        # comentário de `_periodo_do_formulario`) — `para_data`, nunca a
        # cópia privada nem `date.fromisoformat` cru.
        data_lancamento = None
        try:
            data_lancamento = para_data(data_texto or "")
        except DataInvalida:
            erros.append("Informe uma data válida.")

        totais_batem = total_debito == total_credito and total_debito > 0

        # Critério 10: a tela mostra os dois totais e IMPEDE o envio
        # enquanto forem diferentes. Quem garante isto DE VERDADE é
        # `criar_lancamento` abaixo (a validação do servidor) — esta
        # checagem aqui é só conveniência, e o teste do critério 10 POSTa
        # direto para esta view com débito != crédito para provar que,
        # mesmo que ESTA checagem não existisse, nenhum lançamento seria
        # gravado.
        if not erros and len(itens) >= 2 and totais_batem and data_lancamento is not None:
            try:
                # BL-14 (DL-024): o `with transaction.atomic()` envolve
                # tanto a chamada a `criar_lancamento` quanto o `registrar()`
                # da trilha. Antes, qualquer falha no INSERT do
                # `RegistroAuditoria` deixava o lançamento gravado e a
                # trilha silenciosamente vazia — o Diário dizia uma coisa,
                # a trilha dizia outra. O `transaction.atomic()` é
                # REENTRANTE: o serviço `criar_lancamento` é
                # `@transaction.atomic` por si, e o aninhamento resulta em
                # savepoint, e a falha do `registrar()` reverte o savepoint
                # E o commit do `criar_lancamento` que ainda não subiu.
                with transaction.atomic():
                    try:
                        lancamento = criar_lancamento(
                            empresa=empresa,
                            data=data_lancamento,
                            historico=historico,
                            itens=itens,
                            criado_por=request.user,
                            chave_idempotencia=chave_idempotencia,
                        )
                    except ChaveIdempotenciaConflitante as exc:
                        erros.append(str(exc))
                    except CompetenciaEncerrada as exc:
                        # BL-457/A2 (rodada 2 de auditoria): `CompetenciaEncerrada`
                        # é subclasse direta de `Exception`, DELIBERADAMENTE não
                        # de `LancamentoInvalido` (ver o docstring dela em
                        # services.py) — e por isso o `except LancamentoInvalido`
                        # logo abaixo nunca a capturava. Pela DE-026 não há API
                        # separada atrás desta tela: ela chama `criar_lancamento`
                        # direto, então sem este `except` a exceção escapava até
                        # o middleware de erro do Django e virava HTTP 500 — uma
                        # página de erro genérica no lugar da mensagem de negócio
                        # que o serviço já produz pronta (nomeando a competência
                        # e orientando a reabrir ou lançar em mês aberto). Nada
                        # era gravado (a trava funcionava); só a APRESENTAÇÃO da
                        # recusa quebrava. Medido com controle positivo: o MESMO
                        # POST com o mês aberto grava (302); só a competência
                        # fechada produzia o 500.
                        erros.append(str(exc))
                    except LancamentoInvalido as exc:
                        erros.append(str(exc))
                    else:
                        # O serviço informa se de fato criou ou reaproveitou um
                        # lançamento existente (mesma Idempotency-Key) — a trilha
                        # de auditoria e a mensagem precisam refletir o resultado
                        # real (mesmo cuidado da API, ver views.py).
                        if lancamento.criado_agora:
                            registrar(acao="lancamento.criado", objeto=lancamento, request=request)
                            messages.success(request, "Lançamento gravado com sucesso.")
                        else:
                            registrar(
                                acao="lancamento.criacao_repetida",
                                objeto=lancamento,
                                request=request,
                                detalhes={
                                    "chave_idempotencia_hash": hashlib.sha256(
                                        chave_idempotencia.encode("utf-8")
                                    ).hexdigest()[:12]
                                },
                            )
                            messages.info(
                                request,
                                "Este lançamento já havia sido gravado (nova tentativa com o "
                                "mesmo envio, sem duplicar).",
                            )
                        return redirect(
                            "contabilidade_web:lancamento_detalhe",
                            empresa_id=empresa.id,
                            lancamento_id=lancamento.id,
                        )
            except IntegrityError:
                # Defesa residual: se uma constraint que não foi prevista
                # levantar aqui (mudança de modelo, regressão), a operação
                # inteira — `criar_lancamento` + trilha — reverte junta, e
                # o usuário vê o erro em vez de acreditar num sucesso falso.
                erros.append("Não foi possível concluir a gravação do lançamento.")
        elif not erros:
            if len(itens) < 2:
                erros.append("Informe ao menos duas partidas.")
            elif total_debito != total_credito:
                # BL-298 (M7 da auditoria DL-026 rodada 2): esta frase só
                # cabe quando os totais REALMENTE divergem — mantida como
                # estava.
                erros.append(
                    f"Débitos ({_valor_ptbr(total_debito)}) e créditos "
                    f"({_valor_ptbr(total_credito)}) precisam ser iguais antes de gravar."
                )
            else:
                # `total_debito == total_credito` mas `not totais_batem`:
                # só resta a outra metade da condição, `total_debito <= 0`
                # (zero ou negativo). A frase de divergência MENTIRIA aqui
                # — os dois lados SÃO iguais — e foi exatamente o que o
                # auditor mediu: "gravar" com 0,00/0,00 respondia "Débitos
                # (0,00) e créditos (0,00) precisam ser iguais", quando o
                # problema real é não terem valor positivo nenhum. Frase
                # própria, que diz o que fazer.
                erros.append(
                    "O total do lançamento precisa ser maior que zero antes de gravar — "
                    "informe um valor positivo nas partidas."
                )

        for erro in erros:
            messages.error(request, erro)

        # BL-307: as TRÊS condições que bloqueiam `criar_lancamento` mas não
        # têm relação com débito, crédito, partida válida nem linha
        # excluída (ver o docstring de `_veredito_fechamento`, quinta
        # condição). Sem isto, um histórico grande demais, uma chave de
        # idempotência grande demais ou uma data inválida — com as duas
        # partidas restantes batendo perfeitamente — ainda fazia o veredito
        # dizer "Fecha" nesta MESMA resposta 400 (os dois últimos casos da
        # reprodução do achado A1: "histórico de 400 caracteres" e "data
        # 'abacaxi'", nenhum dos dois descarta uma linha, então a correção
        # de `linhas_excluidas_do_total` sozinha não bastava).
        # BL-318 (A1 da rodada 4): a enumeração acima estava ERRADA DE LUGAR,
        # não de conteúdo. As três condições eram as três que ESTA VIEW checa
        # antes de chamar o serviço; `criar_lancamento` tem DEZESSETE `raise`
        # próprios — faixa de data do RC-77, escala, byte nulo, conta que não
        # aceita lançamento, teto de partidas, conflito de idempotência — e
        # nenhum deles passava por aqui. Medido pelo auditor: quatro POSTs com
        # as duas partidas batendo devolviam 400 com "Fecha" EM VERDE, e o
        # primeiro deles é a data fora da faixa: quem digita 1999 em vez de
        # 2019 lia "Fecha" por cima da mensagem que recusou a data.
        #
        # Uma sexta condição enumerada não resolve — a lista de motivos de
        # recusa cresce. A afirmação verdadeira é estrutural e não envelhece:
        #
        #     esta resposta é 400, logo NÃO GRAVOU, logo nada está conferido.
        #
        # `"nao_fecha"` não depende desta bandeira, então divergência real
        # continua sendo anunciada com o valor da diferença.
        bloqueado_por_outro_erro = True

        contexto = _contexto_form_lancamento(
            empresa,
            contas_disponiveis,
            num_linhas_leitura,
            data_texto=data_texto,
            historico=historico,
            chave_idempotencia=chave_idempotencia,
            linhas_preenchidas=request.POST,
            total_debito=total_debito,
            total_credito=total_credito,
            # BL-289: mesma contagem de partidas válidas que decidiu se
            # `criar_lancamento` seria chamado acima — o rodapé desta
            # mesma resposta (400) precisa refletir a MESMA decisão, nunca
            # uma cópia que possa divergir.
            num_partidas_validas=len(itens),
            # BL-307: idem, para a contagem de linhas EXCLUÍDAS — sem isto
            # o padrão da assinatura (`linhas_excluidas_do_total=0`) fazia
            # `_veredito_fechamento` achar que nenhuma linha tinha sido
            # descartada nesta resposta, mesmo quando `linhas_excluidas_do_
            # total` (calculada acima) fosse maior que zero.
            linhas_excluidas_do_total=linhas_excluidas_do_total,
            bloqueado_por_outro_erro=bloqueado_por_outro_erro,
        )
        return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

    # GET: formulário em branco, com uma chave de idempotência NOVA para
    # esta tentativa (critério 11 — cada visita "limpa" ao formulário é uma
    # tentativa distinta).
    contexto = _contexto_form_lancamento(
        empresa,
        contas_disponiveis,
        LINHAS_INICIAIS_LANCAMENTO,
        data_texto=timezone.localdate().isoformat(),
        historico="",
        chave_idempotencia=uuid.uuid4().hex,
    )
    return render(request, "contabilidade/lancamento_form.html", contexto)


# ---------------------------------------------------------------------------
# DL-061, fatia 2 (BL-605) — o detalhe do lançamento e a guia "DMPL" dele
# (E19): a marcação manual (linha × coluna) é a EXCEÇÃO prevista pela
# RC-151, guardada FORA do livro (E15 — nada muda no lançamento efetivado).
# Duas rotas, UMA renderização: `lancamento_detalhe` (leitura) e
# `lancamento_marcacao_dmpl` (a guia, que grava o CONJUNTO de uma vez e
# limpa com "Remover marcações") mostram o MESMO template — a guia é uma
# seção do detalhe, nunca uma tela paralela que pudesse prometer o que o
# servidor não faz.
# ---------------------------------------------------------------------------


# Quantas linhas de marcação o formulário oferece sem preenchimento nenhum.
# Cada linha é UMA célula (linha × coluna) do conjunto; 4 cobre os cenários
# reais (o par de tesouraria, o caso M3 e as quatro células do lançamento
# ambíguo do teste de identidade DLPA × DMPL) e as linhas em branco são a
# folga para a próxima marcação — o formulário nunca some com o que já está
# gravado nem com o que a pessoa acabou de digitar (arquétipo B).
_LINHAS_MINIMAS_DO_FORMULARIO_DE_MARCACAO_DMPL = 4


def _rotulo_da_coluna_da_dmpl(chave):
    """Rótulo humano da coluna da DMPL (`ClassificacaoDmpl.label`), com a
    chave crua como saída de emergência para a classificação gravada ter
    saído do enum (só por ORM/SQL direto) — nunca um 500 numa tela de
    conferência."""
    return ClassificacaoDmpl(chave).label if chave in ClassificacaoDmpl.values else chave


def _movimento_do_lancamento_por_coluna(empresa, lancamento):
    """`(movimento, problemas)` da leitura AUTOMÁTICA de um lançamento.

    `movimento` é `{coluna: efeito líquido do lançamento na coluna}` — o
    MESMO número que `salvar_marcacoes_da_dmpl` exige que o Σ do conjunto
    reproduza (E16); `problemas` é o que faz o lançamento ser EXCEÇÃO (E17:
    linha indefinida, par sem regra ou lançamento ambíguo). As duas
    funções de serviço chamadas aqui são as MESMAS, com os MESMOS
    argumentos, que `salvar_marcacoes_da_dmpl` usa para julgar a marcação —
    a tela nunca tem um segundo cálculo que pudesse divergir da gravação.
    """
    contas = {conta.id: conta for conta in Conta.objects.filter(empresa=empresa)}
    coluna_de, _contas_da_coluna, _desconhecidas = _colunas_de_cada_conta(contas)
    _celulas, movimento, problemas = _atribuir_lancamento_as_linhas_da_dmpl(
        itens=sorted(lancamento.itens.all(), key=lambda item: item.id),
        coluna_de=coluna_de,
        contas=contas,
        e_estorno=lancamento.estorno_de_id is not None,
    )
    return movimento, problemas


def _linhas_do_formulario_de_marcacao(preenchidas):
    """As linhas do formulário do conjunto: as `preenchidas` (as gravadas, no
    GET; as digitadas, quando um POST é recusado), completadas com linhas em
    branco até `_LINHAS_MINIMAS_DO_FORMULARIO_DE_MARCACAO_DMPL` e SEMPRE mais
    UMA em branco no fim — espaço para a próxima marcação, mesmo quando o
    conjunto já ocupa todas as linhas mínimas. Cada linha recebe `indice`
    só para o `for`/`<label>` do template."""
    linhas = [dict(linha) for linha in preenchidas]
    while len(linhas) < _LINHAS_MINIMAS_DO_FORMULARIO_DE_MARCACAO_DMPL:
        linhas.append({"linha": "", "coluna": "", "valor_texto": ""})
    linhas.append({"linha": "", "coluna": "", "valor_texto": ""})
    for indice, linha in enumerate(linhas, start=1):
        linha["indice"] = indice
    return linhas


def _marcacoes_do_formulario_de_marcacao(post):
    """`([erros], [linhas_digitadas], [marcacoes])` dos campos REPETIDOS
    `linha`/`coluna`/`valor` do formulário da guia.

    `marcacoes` sai no formato que `salvar_marcacoes_da_dmpl` recebe —
    `{"linha", "coluna", "valor"}`, o `valor` já em `Decimal` pela gramática
    pt-BR de `_decimal_do_formulario` (DE-029). Linha toda em branco é a
    folga do formulário e é ignorada; linha pela METADE é erro de formulário
    (a pessoa precisa ler o que falta), nunca descartada em silêncio. Erro
    aqui NÃO grava nada: quem chama só grava quando a lista de erros sai
    vazia.
    """
    linhas = post.getlist("linha")
    colunas = post.getlist("coluna")
    valores = post.getlist("valor")
    if not (len(linhas) == len(colunas) == len(valores)):
        return (
            [
                "O conjunto de marcações veio incompleto: cada marcação precisa das três "
                "partes (linha, coluna e valor). Nada foi gravado."
            ],
            [],
            [],
        )
    erros = []
    digitadas = []
    marcacoes = []
    triplas = zip(linhas, colunas, valores, strict=True)
    for indice, (linha, coluna, valor) in enumerate(triplas, start=1):
        if not any((linha.strip(), coluna.strip(), valor.strip())):
            continue
        digitadas.append({"linha": linha, "coluna": coluna, "valor_texto": valor})
        faltando = [
            nome
            for nome, campo in (("linha", linha), ("coluna", coluna), ("valor", valor))
            if not campo.strip()
        ]
        if faltando:
            erros.append(
                f"A marcação {indice} está incompleta: falta informar "
                f"{', '.join(faltando)}. Nada foi gravado."
            )
            continue
        try:
            numero = _decimal_do_formulario(valor.strip())
        except ValorMonetarioInvalido as exc:
            erros.append(f"A marcação {indice} foi recusada: {exc}")
            continue
        marcacoes.append({"linha": linha, "coluna": coluna, "valor": numero})
    return erros, digitadas, marcacoes


def _guia_da_marcacao_dmpl(empresa, lancamento, *, pode_escriturar, erros=None, digitadas=None):
    """Contexto da guia "DMPL" do lançamento — as marcações atuais, o efeito
    por coluna (o Σ que o conjunto precisa reproduzir, E16) e o formulário,
    SÓ quando o lançamento é exceção (E17: se a regra decide, a guia explica
    e não oferece o formulário — o servidor recusaria, e a tela não promete
    o que o servidor não faz)."""
    gravadas = list(MarcacaoDmpl.objects.filter(lancamento=lancamento).order_by("id"))
    movimento, problemas = _movimento_do_lancamento_por_coluna(empresa, lancamento)

    marcacoes = [
        {
            "linha_titulo": _TITULOS_DAS_LINHAS_DA_DMPL.get(marcacao.linha, marcacao.linha),
            "coluna_titulo": _rotulo_da_coluna_da_dmpl(marcacao.coluna),
            "valor": _valor_dre(marcacao.valor),
        }
        for marcacao in gravadas
    ]
    efeito_por_coluna = []
    for coluna in ClassificacaoDmpl:
        efeito = movimento.get(coluna.value, Decimal("0"))
        if efeito != 0:
            efeito_por_coluna.append(
                {
                    "coluna_titulo": _rotulo_da_coluna_da_dmpl(coluna.value),
                    "valor": _valor_dre(efeito),
                }
            )
    if digitadas is not None:
        preenchidas = digitadas
    else:
        preenchidas = [
            {
                "linha": marcacao.linha,
                "coluna": marcacao.coluna,
                "valor_texto": _valor_ptbr(marcacao.valor),
            }
            for marcacao in gravadas
        ]
    return {
        "marcacoes": marcacoes,
        "efeito_por_coluna": efeito_por_coluna,
        "pode_escriturar": pode_escriturar,
        "regra_decide": not problemas,
        "linhas_do_formulario": _linhas_do_formulario_de_marcacao(preenchidas),
        "opcoes_linha": [
            {"chave": chave, "titulo": _TITULOS_DAS_LINHAS_DA_DMPL[chave]}
            for chave in _LINHAS_DE_EVENTO_DA_DMPL
        ],
        # O primeiro item de `_opcoes_da_coluna_da_dmpl_por_grupo` é "Sem
        # coluna na DMPL" — opção da CONTA, não da marcação: a marcação sem
        # coluna não existe (o serviço recusa), então ele fica de fora.
        "opcoes_coluna": _opcoes_da_coluna_da_dmpl_por_grupo()[1:],
        "erros": list(erros or []),
    }


def _contexto_do_lancamento_detalhe(request, empresa, lancamento, *, erros=None, digitadas=None):
    """Contexto ÚNICO das duas rotas do detalhe — a tabela de partidas de
    sempre e a guia "DMPL" (BL-605), que só cresce: nenhum teste do detalhe
    muda de expectativa por causa dela."""
    itens = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for item in lancamento.itens.all():
        if item.tipo == TipoPartida.DEBITO:
            total_debito += item.valor
        else:
            total_credito += item.valor
        itens.append(
            {"conta": item.conta, "tipo": item.tipo, "valor_ptbr": _valor_ptbr(item.valor)}
        )

    return {
        "empresa": empresa,
        "lancamento": lancamento,
        "itens": itens,
        "total_debito_ptbr": _valor_ptbr(total_debito),
        "total_credito_ptbr": _valor_ptbr(total_credito),
        "origem_ptbr": OrigemLancamento(lancamento.origem).label,
        "documento_de_origem": _documento_de_origem_para_a_tela(empresa, lancamento),
        "guia_dmpl": _guia_da_marcacao_dmpl(
            empresa,
            lancamento,
            pode_escriturar=_pode_escriturar(request),
            erros=erros,
            digitadas=digitadas,
        ),
    }


def _documento_de_origem_para_a_tela(empresa, lancamento):
    """Rótulo e link do documento de origem do lançamento (DL-089), ou `None` (manual).

    O link só existe onde a tela do documento existe hoje: o lote da importação de
    lançamentos (DL-077). A escrituração fiscal ainda não tem tela de contabilidade; nesse
    caso a tela mostra o tipo e o identificador, sem link. Não se inventa URL.
    """
    if lancamento.documento_origem_tipo is None:
        return None
    tipo = lancamento.documento_origem_tipo
    identificador = lancamento.documento_origem_id
    url = None
    # `str(int(...)) == ...` recusa "0012" e "+12": o link tem de apontar exatamente para o
    # id gravado pela efetivação, e não para outro número parecido.
    if (
        tipo == TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS
        and identificador.isascii()
        and identificador.isdigit()
        and str(int(identificador)) == identificador
    ):
        url = reverse(
            "contabilidade_web:lancamentos_importacao",
            args=[empresa.id, int(identificador)],
        )
    return {
        "rotulo": TipoDocumentoOrigem(tipo).label,
        "identificador": identificador,
        "url": url,
    }


def _lancamento_da_empresa_para_o_detalhe(empresa, lancamento_id):
    # `empresa=empresa` é o isolamento: lançamento de outra empresa dá 404,
    # nunca confirma a existência (mesma regra das telas irmãs).
    return get_object_or_404(
        LancamentoContabil.objects.prefetch_related("itens__conta"),
        pk=lancamento_id,
        empresa=empresa,
    )


@login_required
@require_safe
def lancamento_detalhe(request, empresa_id, lancamento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    lancamento = _lancamento_da_empresa_para_o_detalhe(empresa, lancamento_id)
    contexto = _contexto_do_lancamento_detalhe(request, empresa, lancamento)
    return render(request, "contabilidade/lancamento_detalhe.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def lancamento_marcacao_dmpl(request, empresa_id, lancamento_id):
    """Guia "DMPL" do lançamento (DL-061, fatia 2 — BL-605, E19): a porta de
    TELA da marcação manual.

    - **GET** renderiza o MESMO template de `lancamento_detalhe`, com a guia
      — leitura segue `_pode_ler` (as permissões atuais do detalhe);
    - **POST** grava o CONJUNTO de uma vez (`acao=salvar`, campos repetidos
      `linha`/`coluna`/`valor`) ou limpa tudo (`acao=remover`); quem grava é
      quem ESCRITURA (`_pode_escriturar`, o mesmo papel das telas de
      escritura — CLIENTE recusa 403), e a regra de verdade é do serviço
      (`salvar_marcacoes_da_dmpl`/`remover_marcacoes_da_dmpl`).

    `MarcacaoDmplInvalida` vira erro de FORMULÁRIO na própria página, com o
    que falta e tudo o que foi digitado preservado (nunca 500 — o mesmo
    molde de `conta_classificacao_dmpl`). Na recusa, nada é gravado: a
    substituição atômica do serviço nem começa.

    `ClassificacaoAlteraPeriodoFechado` (DL-071, BL-655) tem o mesmo
    tratamento, em `salvar` e em `remover`: a DMPL de um período encerrado ou
    entregue não muda por marcação, e a mensagem diz qual competência barra e
    se ela pode ou não ser reaberta.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    escreve = _pode_escriturar(request)
    if request.method == "POST":
        if not escreve:
            return _resposta_sem_permissao(
                request, "Seu papel não permite marcar lançamentos da DMPL nesta empresa."
            )
    elif not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    lancamento = _lancamento_da_empresa_para_o_detalhe(empresa, lancamento_id)

    if request.method == "GET":
        contexto = _contexto_do_lancamento_detalhe(request, empresa, lancamento)
        return render(request, "contabilidade/lancamento_detalhe.html", contexto)

    try:
        recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_MARCACAO_DMPL)
    except DadoNaoContratado as exc:
        messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
        contexto = _contexto_do_lancamento_detalhe(request, empresa, lancamento)
        return render(request, "contabilidade/lancamento_detalhe.html", contexto, status=400)

    acao = request.POST.get("acao")
    if acao == "remover":
        try:
            remover_marcacoes_da_dmpl(lancamento=lancamento, usuario=request.user, request=request)
        except ClassificacaoAlteraPeriodoFechado as exc:
            # DL-071 (BL-655): remover reclassifica a leitura (o veto volta a
            # valer), então vale a mesma trava de salvar. Recusa de regra é a
            # tela respondendo na própria guia, com 200 — nunca um 500.
            contexto = _contexto_do_lancamento_detalhe(
                request, empresa, lancamento, erros=[str(exc)]
            )
            return render(request, "contabilidade/lancamento_detalhe.html", contexto)
        messages.success(
            request,
            "Marcações da DMPL removidas: este lançamento volta para a regra automática "
            "e o veto da emissão, se houver, volta a valer.",
        )
        return redirect("contabilidade_web:lancamento_detalhe", empresa.id, lancamento.id)

    erros = []
    digitadas = []
    if acao != "salvar":
        erros.append(
            "Ação não reconhecida neste formulário: use “Salvar marcações” ou “Remover "
            "marcações”. Nada foi gravado."
        )
    else:
        erros, digitadas, marcacoes = _marcacoes_do_formulario_de_marcacao(request.POST)
        if not erros and not marcacoes:
            # Conjunto VAZIO com "Salvar" limparia as marcações sem ninguém
            # pedir — a limpeza tem botão próprio ("Remover marcações"), que
            # diz o que faz no próprio rótulo (direção de arte, §8.4).
            erros.append(
                "Nenhuma marcação informada: preencha ao menos uma linha do conjunto, ou "
                "use “Remover marcações” para voltar para a regra automática. Nada foi gravado."
            )
        if not erros:
            try:
                salvar_marcacoes_da_dmpl(
                    lancamento=lancamento,
                    marcacoes=marcacoes,
                    usuario=request.user,
                    request=request,
                )
            except (MarcacaoDmplInvalida, ClassificacaoAlteraPeriodoFechado) as exc:
                # `ClassificacaoAlteraPeriodoFechado` (DL-071/BL-655): período
                # encerrado ou entregue. Vira erro de formulário como a recusa
                # de conteúdo — o que foi digitado fica na tela e nada foi
                # gravado.
                erros.append(str(exc))
            else:
                messages.success(
                    request,
                    "Marcações da DMPL gravadas: a demonstração passa a mostrar as células "
                    "marcadas deste lançamento.",
                )
                return redirect("contabilidade_web:lancamento_detalhe", empresa.id, lancamento.id)

    contexto = _contexto_do_lancamento_detalhe(
        request, empresa, lancamento, erros=erros, digitadas=digitadas
    )
    return render(request, "contabilidade/lancamento_detalhe.html", contexto)


# ---------------------------------------------------------------------------
# BL-198 (b) / R6-4 — "há movimento fora do período consultado"
#
# É o item que fez a DL-020 existir, e o único achado aberto com esta
# característica: **o usuário não consegue conferir o que não aparece.** O
# auditor mediu um lançamento de 5.000,00 datado `9999-12-31` (um `9`
# digitado no lugar de `2`) ao lado de um de 100,00 de hoje:
#
#     Diário      (período padrão): mostra 5.000,00? False | avisa? False
#     Balancete   (período padrão): mostra 5.000,00? False | avisa? False
#     Razão       (período padrão): mostra 5.000,00? False | avisa? False
#     Conferência (sem período)   : mostra 5.000,00? False
#     total real de débito na base: 10.200,00
#
# O balancete do período **concilia** — é por isso que nenhuma conferência
# aponta. Para encontrar, o contador precisava suspeitar e alargar o
# período até o ano 9999.
#
# A faixa do RC-77 (BL-205) fecha a PORTA de entrada. Este aviso é a REDE
# embaixo dela, e continua necessário depois de a porta fechar, por três
# motivos: dado já gravado antes da regra não se conserta validando a
# entrada (está fora do escopo desta etapa); a faixa permite datas
# legítimas fora do período consultado (é o caso comum — o contador olha
# setembro e existe movimento de outubro); e há portas de escrita que não
# passam pela tela (o admin do Django, por exemplo).
#
# A consulta é de `services.py` (`movimento_fora_do_periodo`), UMA fonte;
# esta função só monta a apresentação e o caminho de correção — o link que
# ALARGA o período até incluir o que está fora, preservando os outros
# parâmetros da tela (o `nivel` do Balancete, por exemplo).
# ---------------------------------------------------------------------------


def _aviso_de_movimento_fora_do_periodo(
    request, empresa, inicio, fim, *, conta=None, ids_contas=None
):
    """Contexto do aviso, ou `None` quando não há nada fora do período.

    Os dois parâmetros do Razão têm papéis DIFERENTES, e é por isso que ele
    passa os dois (BL-212):

    - `ids_contas` é o que CONSULTA: o conjunto de contas já apurado por
      `apurar_razao` (chave `ids_contas` do resultado), reaproveitado para o
      aviso recortar pelo MESMO conjunto que a tela está somando sem
      percorrer a subárvore uma segunda vez — `_descendentes_de` faz uma
      consulta por nível de profundidade, e recomputá-lo aqui dobrava esse
      custo e estourava o teto de consultas do Razão.
    - `conta` é o que APRESENTA: a chave `"conta"` do contexto é a única
      coisa que faz o parcial dizer "esta conta (incluindo as subordinadas)"
      em vez de "esta empresa". Nenhuma consulta depende dela quando
      `ids_contas` vem, e o link que alarga o período também não — ele sai de
      `request.path` mais os parâmetros da tela.

    Sem nenhum dos dois, o recorte é a empresa inteira (Diário, Balancete).
    Com `conta` sem `ids_contas`, `movimento_fora_do_periodo` ainda recorta
    pela subárvore — pagando a travessia; nenhuma tela faz isso hoje.
    """
    fora = movimento_fora_do_periodo(
        empresa=empresa, inicio=inicio, fim=fim, conta=conta, ids_contas=ids_contas
    )
    if not fora:
        return None
    anteriores = fora.get("anteriores")
    posteriores = fora.get("posteriores")
    datas_extremas = [
        lado["data_extrema"] for lado in (anteriores, posteriores) if lado is not None
    ]
    # O link precisa ALARGAR, nunca substituir: quem está vendo setembro e
    # tem movimento em outubro deve continuar vendo setembro no resultado.
    inicio_ampliado = min([inicio, *datas_extremas])
    fim_ampliado = max([fim, *datas_extremas])
    parametros = request.GET.copy()
    parametros["inicio"] = inicio_ampliado.isoformat()
    parametros["fim"] = fim_ampliado.isoformat()
    return {
        "anteriores": anteriores,
        "posteriores": posteriores,
        "conta": conta,
        "inicio_ampliado": inicio_ampliado,
        "fim_ampliado": fim_ampliado,
        "url_ampliada": f"{request.path}?{parametros.urlencode()}",
    }


# ---------------------------------------------------------------------------
# Diário
# ---------------------------------------------------------------------------


@login_required
@require_safe
def diario(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    # DL-089: filtro por origem do lançamento. Vazio = todas. Valor fora da lista é erro de
    # formulário (400), como a data: não vira "sem filtro" em silêncio.
    origem_pedida = (request.GET.get("origem") or "").strip()
    erro_origem = None
    origem_filtro = origem_pedida or None
    if origem_filtro is not None and origem_filtro not in OrigemLancamento.values:
        erro_origem = "Origem inválida. Escolha uma das opções da lista de origem."
        origem_filtro = None
    # DL-077, fatia 3: o link "Importar lançamentos" só aparece para quem escritura (o servidor
    # recusa de qualquer forma; a tela só deixa de convidar quem seria recusado).
    contexto = {
        "empresa": empresa,
        "inicio": inicio,
        "fim": fim,
        "pode_escriturar": _pode_escriturar(request),
        "origens": [("", "Todas as origens"), *OrigemLancamento.choices],
        "origem_selecionada": origem_filtro or "",
    }
    if erro_periodo or erro_origem:
        messages.error(request, erro_periodo or erro_origem)
        return render(request, "contabilidade/diario.html", contexto, status=400)

    lotes = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for lancamento in listar_diario(empresa=empresa, inicio=inicio, fim=fim, origem=origem_filtro):
        debito_lote = Decimal("0")
        credito_lote = Decimal("0")
        for item in lancamento.itens.all():
            if item.tipo == TipoPartida.DEBITO:
                debito_lote += item.valor
            else:
                credito_lote += item.valor
        total_debito += debito_lote
        total_credito += credito_lote
        lotes.append(
            {
                "lancamento": lancamento,
                "debito_ptbr": _valor_ptbr(debito_lote),
                "credito_ptbr": _valor_ptbr(credito_lote),
            }
        )

    contexto.update(
        {
            "lotes": lotes,
            "total_debito_ptbr": _valor_ptbr(total_debito),
            "total_credito_ptbr": _valor_ptbr(total_credito),
            # BL-198 (b): ver o comentário da função.
            "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                request, empresa, inicio, fim
            ),
            # BL-282: linhas do timbre do ESCRITÓRIO da empresa consultada
            # (nunca de outro — `empresa` já veio filtrada por
            # `escritorio=request.escritorio` em `_empresa_do_escritorio_
            # ativo`, então `empresa.escritorio` É o escritório ativo da
            # sessão). Sai "de graça" nesta tela pelo mesmo contrato do
            # Balancete (`Escritorio.linhas_do_timbre`), sem lógica de
            # fallback duplicada aqui — ver o docstring da property.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
        }
    )
    return render(request, "contabilidade/diario.html", contexto)


# ---------------------------------------------------------------------------
# Razão
# ---------------------------------------------------------------------------


@login_required
@require_safe
def razao(request, empresa_id, conta_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa
    conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    contexto = {"empresa": empresa, "conta": conta, "inicio": inicio, "fim": fim}
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/razao.html", contexto, status=400)

    try:
        apuracao = apurar_razao(conta=conta, empresa=empresa, inicio=inicio, fim=fim)
    except HierarquiaInconsistente as exc:
        # Ciclo ou conta_pai de outra empresa: resposta controlada,
        # nomeando a conta, nunca um 500 mudo (mesmo tratamento da API).
        messages.error(request, str(exc))
        return render(request, "contabilidade/razao.html", contexto, status=409)

    # BL-198 (b) + BL-212: DEPOIS da apuração e FORA do `try`, de propósito.
    # Esta chamada já não percorre a hierarquia — ela reaproveita o conjunto
    # de contas que a apuração acabou de percorrer (`apuracao["ids_contas"]`),
    # então não há mais `HierarquiaInconsistente` a tratar aqui; o que a
    # protege é depender de `apuracao`, que só existe quando o plano está
    # consistente. Antes da BL-212 ela recomputava `_descendentes_de` (uma
    # consulta por NÍVEL de profundidade), dobrando o custo do Razão de um
    # plano profundo e estourando o teto de consultas. `conta` continua
    # sendo passada, mas só para a APRESENTAÇÃO: é a chave "conta" do
    # contexto, e é só ela que faz o aviso dizer "esta conta (incluindo as
    # subordinadas)" em vez de "esta empresa". O link que alarga o período
    # não depende dela — ele nasce de `request.path`, que no Razão já traz o
    # `conta_id`.
    aviso_fora_do_periodo = _aviso_de_movimento_fora_do_periodo(
        request, empresa, inicio, fim, conta=conta, ids_contas=apuracao["ids_contas"]
    )

    itens = []
    for linha in apuracao["itens"]:
        saldo_abs, saldo_nat = _saldo_absoluto_com_natureza(linha["saldo"], conta.natureza)
        itens.append(
            {
                "lancamento_id": linha["lancamento_id"],
                "data": linha["data"],
                "historico": linha["historico"],
                "conta_codigo": linha["conta"],
                "conta_nome": linha["conta_nome"],
                "tipo": linha["tipo"],
                "valor_ptbr": _valor_ptbr(linha["valor"]),
                "saldo_ptbr": _valor_ptbr(saldo_abs),
                "saldo_natureza": _indicador_natureza(saldo_nat),
            }
        )

    saldo_anterior_abs, saldo_anterior_nat = _saldo_absoluto_com_natureza(
        apuracao["saldo_anterior"], conta.natureza
    )
    saldo_final_abs, saldo_final_nat = _saldo_absoluto_com_natureza(
        apuracao["saldo_final"], conta.natureza
    )

    contexto.update(
        {
            "consolidado": apuracao["consolidado"],
            "itens": itens,
            "saldo_anterior_ptbr": _valor_ptbr(saldo_anterior_abs),
            "saldo_anterior_natureza": _indicador_natureza(saldo_anterior_nat),
            "total_debito_ptbr": _valor_ptbr(apuracao["total_debito"]),
            "total_credito_ptbr": _valor_ptbr(apuracao["total_credito"]),
            "saldo_final_ptbr": _valor_ptbr(saldo_final_abs),
            "saldo_final_natureza": _indicador_natureza(saldo_final_nat),
            "movimento_fora_do_periodo": aviso_fora_do_periodo,
            # BL-282: mesmo contrato do Balancete e do Diário — ver o
            # comentário em `diario`.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
        }
    )
    return render(request, "contabilidade/razao.html", contexto)


# ---------------------------------------------------------------------------
# Balancete (critério 6)
# ---------------------------------------------------------------------------


def _veredito_balancete(total_debitos, total_creditos):
    """Decide, em `Decimal`, um de três estados — `"fecha"`, `"nao_fecha"`
    ou `"nada_a_conferir"` — para a faixa de fechamento no topo do
    balancete (`total_debitos`/`total_creditos`: as colunas "próprios" do
    PERÍODO, DE-024 §2 — as mesmas que já alimentam `total_debitos_ptbr`/
    `total_creditos_ptbr`).

    BL-290 (A2 da auditoria DL-026 rodada 2): o TEMPLATE decidia sozinho,
    comparando `total_debitos_ptbr == total_creditos_ptbr` — texto pt-BR,
    não `Decimal` (a mesma classe de defeito do BL-289/A1, só que na tela
    do balancete). Além de comparar texto, o ramo "Fecha" cobria também o
    caso `0,00 == 0,00` sem NENHUM movimento no período — o estado em que a
    tela abre no dia 1º de todo mês (BL-302/B4) —, mostrando um "Fecha"
    verde sobre nada. Um sinal que aparece sempre deixa de ser sinal.

    `"nada_a_conferir"`: os dois totais são zero — não há o que fechar
    neste período (sem movimento próprio nenhum). `"fecha"`: os totais
    batem E há movimento (pelo menos um dos dois maior que zero — na
    prática os dois, porque toda partida tem os dois lados). `"nao_fecha"`:
    os totais DIVERGEM.

    Por construção de partidas dobradas — todo lançamento EFETIVADO tem
    débito igual a crédito (`apps.contabilidade.services.criar_lancamento`)
    —, a soma de todos os débitos próprios do período sempre bate com a
    soma de todos os créditos próprios, salvo CORRUPÇÃO de dado. O ramo
    `"nao_fecha"` é, por isso, rede de segurança: hoje inalcançável em uso
    normal do produto (nenhum caminho de escrita deixa os totais
    divergirem), mas é exatamente no dia em que algo corromper o dado que
    esta tela precisa gritar — e uma rede que ninguém nunca viu funcionar
    não é rede (ver o teste que força a divergência via
    `monkeypatch.setattr(views_web, "apurar_balancete", ...)`, já que não
    existe caminho de escrita real para produzi-la).
    """
    if total_debitos == 0 and total_creditos == 0:
        return "nada_a_conferir"
    if total_debitos == total_creditos:
        return "fecha"
    return "nao_fecha"


@login_required
@require_safe
def balancete(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    nivel, erro_nivel = _nivel_do_formulario(request)
    criterio, erro_criterio = _criterio_de_apuracao_do_formulario(request)
    # DL-027 Fatia B.3: carimbo de data e hora da emissão — capturado
    # AQUI (não no template) para garantir que toda renderização da
    # mesma request use o mesmo timestamp, e que a string pt-BR seja
    # produzida uma única vez pela camada Python. `timezone.localtime()`
    # devolve o instante atual no fuso de `settings.TIME_ZONE`
    # ("America/Sao_Paulo"), não em UTC — é o que o usuário vê no
    # relógio dele.
    carimbo_de_emissao = timezone.localtime()
    contexto = {
        "empresa": empresa,
        "inicio": inicio,
        "fim": fim,
        "nivel": nivel,
        "criterio_de_apuracao": criterio,
        "criterio_de_apuracao_texto": _TEXTO_DO_CRITERIO[criterio],
        "criterio_de_apuracao_opcoes": sorted(_CRITERIOS_DE_APURACAO_VALIDOS),
        "carimbo_de_emissao": carimbo_de_emissao,
        "carimbo_de_emissao_texto": carimbo_de_emissao.strftime("%d/%m/%Y às %H:%M:%S"),
    }
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/balancete.html", contexto, status=400)
    if erro_nivel:
        messages.error(request, erro_nivel)
        return render(request, "contabilidade/balancete.html", contexto, status=400)
    if erro_criterio:
        messages.error(request, erro_criterio)
        return render(request, "contabilidade/balancete.html", contexto, status=400)

    try:
        apuracao = apurar_balancete(
            empresa=empresa,
            inicio=inicio,
            fim=fim,
            nivel=nivel,
            criterio_de_apuracao=criterio,
        )
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(
            request,
            "contabilidade/balancete_emissao_recusada.html",
            {"empresa": empresa},
            status=409,
        )

    # Necessário só para montar o link "ver Razão desta conta" (critério
    # 12): `apurar_balancete` devolve o CÓDIGO da conta (é o que o
    # contador lê), não o id interno que a URL do Razão precisa. Uma única
    # consulta, fora do laço — não é N+1.
    ids_por_codigo = dict(Conta.objects.filter(empresa=empresa).values_list("codigo", "id"))

    linhas = []
    for linha in apuracao["contas"]:
        saldo_anterior_abs, saldo_anterior_nat = _saldo_absoluto_com_natureza(
            linha["saldo_anterior"], linha["natureza"]
        )
        saldo_final_abs, saldo_final_nat = _saldo_absoluto_com_natureza(
            linha["saldo_final"], linha["natureza"]
        )
        # BL-281: `linha["natureza"]` É a natureza CADASTRADA da conta desta
        # linha (`Conta.natureza`, não o sinal computado do saldo) — provado
        # pelo comentário de origem em
        # apps/contabilidade/services.py:1088-1099 (`apurar_balancete`):
        # "Natureza CADASTRADA da conta (`Conta.natureza`) — exposta aqui só
        # para permitir à VIEW converter saldo_anterior/saldo_final [...] em
        # valor absoluto + natureza APURADA". A view já usava esse valor
        # para calcular `saldo_final_nat` acima; faltava só REPASSÁ-LO ao
        # contexto, no formato que `templates/contabilidade/_saldo.html` já
        # sabe ler (`conta.natureza`) — o parcial é reaproveitado tal como
        # está, sem mudança nele (fora do escopo desta etapa).
        #
        # Exposto como `dict`, não como o objeto `Conta`: a Django Template
        # Language resolve `conta.natureza` tentando PRIMEIRO
        # `conta["natureza"]` (lookup de dicionário) antes de tentar
        # `getattr` — `Variable._resolve_lookup`, biblioteca padrão do
        # Django — então `{"natureza": "devedora"}` resolve `conta.natureza`
        # exatamente como um objeto seria. Preferido ao objeto `Conta`
        # inteiro por dois motivos: (1) a view não tem o objeto aqui —
        # `apurar_balancete` devolve campos agregados, não instâncias de
        # `Conta`, e buscar uma consulta extra por linha para um único
        # campo já lido seria N+1 sem necessidade; (2) um dict deliberadamente
        # estreito não sugere ao template que outros atributos de `Conta`
        # (ex.: `codigo`, `nome`) estão disponíveis nesta chave — só
        # `natureza` está.
        #
        # `None` quando `linha["natureza"]` não é um dos dois valores de
        # `NaturezaConta` (defesa contra dado corrompido fora do caminho
        # validado — ex.: escrita direta no banco — já que o campo do
        # modelo é obrigatório e usa `choices`, então em dado íntegro isto
        # nunca acontece). Com `conta=None`, `_saldo.html` não marca
        # parênteses: `None.natureza` não resolve a "devedora" nem
        # "credora" em nenhum dos dois ramos do `{% if %}`, então cai no
        # `{% else %}` (mostra o valor sem parênteses) — never inventa um
        # lado para dado que o sistema não pode confirmar. Saldo ZERO já é
        # tratado sem depender disto: `_saldo.html` primeiro confere
        # `{% if natureza %}` (a natureza APURADA, `saldo_final_natureza`
        # abaixo) e `_indicador_natureza` devolve `None` para saldo zero
        # (RC-61) — o ramo de `conta.natureza` nunca é alcançado nesse caso.
        conta_natureza_cadastrada = (
            linha["natureza"] if linha["natureza"] in NaturezaConta.values else None
        )
        linhas.append(
            {
                "conta_id": ids_por_codigo.get(linha["conta"]),
                "conta": {"natureza": conta_natureza_cadastrada},
                "codigo": linha["conta"],
                "nome": linha["nome"],
                "nivel": linha["nivel"],
                # Inteiro, nunca `float` (achado 6 — mesma regra de
                # `_linhas_hierarquicas`, ver o comentário lá).
                "nivel_classe": min(linha["nivel"], NIVEL_INDENTACAO_MAXIMA)
                if linha["nivel"]
                else 0,
                "analitica": linha["analitica"],
                "saldo_anterior_ptbr": _valor_ptbr(saldo_anterior_abs),
                "saldo_anterior_natureza": _indicador_natureza(saldo_anterior_nat),
                "debitos_ptbr": _valor_ptbr(linha["debitos"]),
                "creditos_ptbr": _valor_ptbr(linha["creditos"]),
                # DE-024 §2: é sobre ESTAS duas colunas (o movimento
                # PRÓPRIO de cada linha), não sobre "debitos"/"creditos"
                # (consolidados), que a soma das linhas exibidas reconcilia
                # com o rodapé (critério 6) — em qualquer arranjo de plano
                # de contas, porque todo lançamento é próprio de
                # exatamente uma conta.
                "debitos_proprios_ptbr": _valor_ptbr(linha["debitos_proprios"]),
                "creditos_proprios_ptbr": _valor_ptbr(linha["creditos_proprios"]),
                "saldo_final_ptbr": _valor_ptbr(saldo_final_abs),
                "saldo_final_natureza": _indicador_natureza(saldo_final_nat),
            }
        )

    # DL-027 Fatia B (item 3 do plano): a trava de "Fecha / Não fecha"
    # que o produto já calculava (BL-290 / A2 da DL-026 rodada 2) vira
    # VETO aqui. A decisão mora no `services` —
    # `avaliar_emissao_do_balancete` decide em `Decimal`, nunca em texto
    # pt-BR já formatado (a mesma lição do BL-290: `_valor_ptbr`
    # arredonda, e 300,004 vs 300,00 viram o mesmo "300,00"). A view
    # pergunta e obedece (mesmo contrato de `avaliar_emissao_do_balanco`,
    # DL-034). Quando `pode_emitir` é `False`, devolvemos 409 com a
    # diferença em pt-BR e a orientação textual — o critério 9 do plano
    # proíbe veto seco. A resposta recusada não recebe contexto de
    # apuração, carimbo, timbre ou template imprimível do Balancete: um
    # HTTP 409 não pode entregar o documento que acabou de vetar.
    avaliacao = avaliar_emissao_do_balancete(apuracao)
    if not avaliacao["pode_emitir"]:
        messages.error(
            request,
            "O Balancete NÃO pode ser emitido: débitos e créditos do período "
            f"divergem em R$ {avaliacao['diferenca_ptbr']}. Verifique os "
            "lançamentos do período antes de reimprimir.",
        )
        return render(
            request,
            "contabilidade/balancete_emissao_recusada.html",
            {"empresa": empresa},
            status=409,
        )

    # Veredito calculado em `Decimal` sobre os totais de ORIGEM
    # (`apuracao["total_debitos"]`/`["total_creditos"]`) — nunca sobre
    # o texto pt-BR logo abaixo. Ver o docstring de
    # `_veredito_balancete` (mantido aqui só para o display; a
    # decisão de EMISSÃO vem de `avaliar_emissao_do_balancete`).
    veredito_balancete = avaliacao["veredito"]
    diferenca_balancete_ptbr = avaliacao["diferenca_ptbr"]

    contexto.update(
        {
            "linhas": linhas,
            "total_debitos_ptbr": _valor_ptbr(apuracao["total_debitos"]),
            "total_creditos_ptbr": _valor_ptbr(apuracao["total_creditos"]),
            # BL-290: chave ÚNICA de decisão para a faixa — "fecha" /
            # "nao_fecha" / "nada_a_conferir". O template ramifica por ela;
            # não volta a comparar `total_debitos_ptbr`/`total_creditos_
            # ptbr` (texto) entre si.
            "veredito_balancete": veredito_balancete,
            # `None` fora do ramo "nao_fecha" — nunca "0,00", que seria
            # ruído (mesma política do BL-286/BL-289 no lançamento).
            "diferenca_balancete_ptbr": diferenca_balancete_ptbr,
            # R6-9/BL-203 (rodada 6) — critério 13, texto literal: "empresa
            # sem lançamento no período mostra MENSAGEM, não tabela vazia
            # sem explicação". Diário, Razão e Conferência cumpriam; o
            # Balancete mostrava 3 linhas e 8 zeros, sem uma palavra. O
            # achado foi levantado na rodada 5 como observação, não entrou
            # no backlog, e por isso chegou intacto à rodada 6.
            #
            # A condição é "nenhum movimento NO PERÍODO" (os dois totais do
            # período em zero), não "nenhuma linha": um balancete com saldo
            # ANTERIOR e sem movimento no mês é informação legítima e
            # continua sendo exibido inteiro — a mensagem explica o que se
            # está vendo, **nunca esconde a tabela**. Esconder seria trocar
            # um defeito de explicação por um de omissão contábil.
            "sem_movimento_no_periodo": (
                bool(linhas) and apuracao["total_debitos"] == 0 and apuracao["total_creditos"] == 0
            ),
            # BL-198 (b): e é justamente no balancete zerado que o aviso
            # mais importa — ele concilia, então nada mais denuncia que
            # existe movimento fora do período.
            "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                request, empresa, inicio, fim
            ),
            # BL-282: o Balancete é a tela nomeada pelo critério 9 da DL-026
            # para sair com a identidade do ESCRITÓRIO, não a do fornecedor
            # — ver o comentário em `diario` para o contrato completo.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
        }
    )
    return render(request, "contabilidade/balancete.html", contexto)


# ---------------------------------------------------------------------------
# Balanço Patrimonial (DL-034) — nível 1: a primeira DEMONSTRAÇÃO CONTÁBIL
# que o produto emite (classe 2 de personalizacao-de-relatorio.md), não
# conferência. "O que eu vou entregar fecha, e eu sei o que ele NÃO diz":
# quem decide SE PODE emitir é o SERVIDOR
# (apps.contabilidade.services.avaliar_emissao_do_balanco) — esta view
# pergunta, obedece e explica; nunca recompõe a decisão.
# ---------------------------------------------------------------------------

# Rótulo humano de cada lista de pendência que `avaliar_emissao_do_balanco`
# pode devolver em `emissao["listas_pendentes"]` — SÓ apresentação (a
# REGRA de quando cada lista fica não vazia mora inteira em services.py,
# nunca duplicada aqui). `.get(nome, nome)` no ponto de uso cobre uma
# lista futura que `_LISTAS_DE_PENDENCIA_DO_BALANCO` (services.py) venha a
# ganhar sem que este dicionário tenha sido atualizado ainda — a tela
# nomeia a CHAVE crua em vez de quebrar ou silenciar a pendência.
NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO = {
    "contas_com_tipo_desconhecido": ("Conta com tipo gravado fora do cadastro (dado corrompido)"),
    "contas_com_tipo_divergente_da_raiz": (
        "Conta cujo tipo diverge do tipo da raiz da sua hierarquia"
    ),
    "contas_com_classificacao_aninhada": (
        "Duas contas da mesma hierarquia classificando o mesmo grupo (circulante/não circulante)"
    ),
    "contas_com_classificacao_desconhecida": (
        "Conta com classificação patrimonial gravada fora do cadastro (dado corrompido)"
    ),
    "contas_sem_classificacao_patrimonial": (
        "Conta com saldo, do Ativo ou do Passivo, sem classificação circulante/não circulante"
    ),
    # BL-516: o agrupamento desta lista abrange contas-irmãs e contas-raiz
    # do mesmo tipo (para raízes, `conta_pai` é `None`). O rótulo descreve
    # a divergência de natureza sem afirmar que existe ancestral comum ou
    # não classificado.
    # DE-070: esta lista é AVISO, não veto — o rótulo evita "corrija",
    # que era instrução IMPOSSÍVEL sempre que a classificação já estava
    # certa (ver ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA, abaixo).
    "contas_topo_classificadas_com_natureza_divergente_entre_irmas": (
        "Contas de topo do mesmo tipo (irmãs ou raízes) com natureza cadastrada "
        "diferente entre si — aviso, não impede a emissão"
    ),
    "contas_nao_folha_sem_classificacao_com_movimento_proprio": (
        "Conta que agrupa outras contas (não é folha), sem classificação "
        "própria nem de um ancestral, com movimento lançado diretamente nela"
    ),
    # DL-062 (BL-604): a lista é AVISO pelo mesmo motivo da de cima — depois
    # da correção o NÚMERO do Balanço está certo; o que se declara é que a
    # conta entrou no total com o sinal da natureza natural do tipo, e não
    # com o da natureza cadastrada dela. O rótulo diz ISSO, e não "conta
    # errada": uma retificadora na raiz não é erro de cadastro.
    "contas_retificadoras_rais": (
        "Conta-raiz com natureza contrária à natural do seu tipo — o sistema a somou com o "
        "sinal invertido, e o total saiu certo (aviso, não impede a emissão)"
    ),
}


def _data_base_do_formulario(request):
    """Lê e valida 'data_base' da querystring do Balanço — DIFERENTE de
    `_periodo_do_formulario` (Diário/Razão/Balancete, um INTERVALO): o
    Balanço é uma FOTOGRAFIA de uma única data (NBC TG 26 item 51(c), "a
    data de encerramento do período de reporte ou o período coberto").

    Ausência do parâmetro (primeira visita) usa HOJE como valor inicial
    sugerido — mesma convenção de conveniência de `_periodo_do_formulario`
    (é a TELA quem escolhe um padrão por conveniência de quem a usa todo
    dia; `apurar_saldos`/`apurar_balanco_patrimonial` não têm padrão
    próprio nenhum). Uma data enviada e malformada nunca "cai" no padrão em
    silêncio — mesma regra de `_periodo_do_formulario`.

    Devolve `(data_base, mensagem_de_erro)`.
    """
    bruto = request.GET.get("data_base", "").strip()
    if not bruto:
        return timezone.localdate(), None
    try:
        return para_data(bruto), None
    except DataInvalida:
        return None, "Data inválida: use o seletor de data (ou o formato AAAA-MM-DD)."


# `_cnpj_mascarado` (DL-034) foi REMOVIDA nesta etapa (DL-038, etapa 2):
# ela sempre lia `empresa.cnpj` direto, e uma empresa CPF em modo
# contabilidade (permitida — nada no R4 proíbe isso) tem `empresa.cnpj`
# vazio por invariante de banco, o que imprimiria o Balanço com a
# inscrição EM BRANCO. O ponto único agora é `apps.contabilidade.services.
# rotulo_e_inscricao_da_empresa` — mesma app, sem o problema de
# acoplamento que motivava a duplicação original (import de símbolo
# PRIVADO de outro app): a nova função mora no MESMO app que a consome,
# só reescreve a máscara em vez de importar de `apps.empresas` (mesma
# decisão consciente, mesmo motivo, ver a docstring dela).


# BL-508 (auditoria DL-034, achado A10): rótulo HUMANO de cada campo extra
# que uma linha de pendência do Balanço pode carregar além de "conta"/
# "nome" — nunca o NOME CRU do campo do banco (`classificacao_
# patrimonial`, `natureza`, `tipo`, `tipo_da_raiz`, `...ancestral`), que a
# tela mostrava ao contador antes desta correção. Cobre HOJE todos os
# campos extras que as SETE listas de `_LISTAS_DE_PENDENCIA_DO_BALANCO`
# (services.py) anexam — ver o comentário de `_linhas_de_pendencia` sobre
# o que acontece quando um campo NOVO aparecer sem entrar aqui.
# DL-045 fatia 3: as duas chaves "classificacao_dre"/"classificacao_dre_
# ancestral" foram ACRESCENTADAS aos dois dicts abaixo (nunca um par
# próprio da DRE) — `_linhas_de_pendencia`, a função que os lê, é
# genérica na FORMA (ver o docstring dela) e é reaproveitada INTEIRA
# pelas pendências da DRE (`_lista_de_pendencia_dre_para_contexto`, mais
# abaixo); só o "tipo" já bastava (`contas_sem_classificacao_dre_com_
# movimento`), mas `contas_com_classificacao_dre_aninhada`/`...
# desconhecida` (services.py) anexam a classificação DRE própria e a do
# ancestral, que precisam do MESMO tratamento que `classificacao_
# patrimonial`/`...ancestral` já recebem para o Balanço.
_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA = {
    "tipo": "Tipo cadastrado",
    "tipo_da_raiz": "Tipo da raiz da hierarquia",
    "classificacao_patrimonial": "Classificação cadastrada",
    "classificacao_patrimonial_ancestral": "Classificação do ancestral",
    "classificacao_dre": "Linha da DRE cadastrada",
    "classificacao_dre_ancestral": "Linha da DRE do ancestral",
    # DL-048/CTB-12: mesma dupla de chaves para a classificação da DLPA —
    # os dicts são GENÉRICOS por campo de pendência (nenhum par "só da
    # DRE" ou "só da DLPA"), e `contas_com_classificacao_dlpa_
    # desconhecida` carrega este campo cru.
    "classificacao_dlpa": "Linha da DLPA cadastrada",
    # DL-045, correção da rodada 1 de auditoria (A2): campo extra de
    # `contas_com_tipo_divergente_da_linha` (services.py) — a linha
    # EFETIVA (própria válida, ou herdada do ancestral) contra a qual o
    # `TipoConta` da conta foi julgado, diferente de "classificacao_dre"
    # (a PRÓPRIA, que pode nem existir quando a linha efetiva veio de um
    # ancestral).
    "classificacao_dre_efetiva": "Linha da DRE efetiva (própria ou herdada)",
    "natureza": "Natureza cadastrada",
    # DL-062 (BL-604): o lado contra o qual a natureza cadastrada acima
    # diverge — é o que decide se a conta entrou no total com o sinal
    # invertido. Mesmo enum de `natureza`, mesmo tratamento.
    "natureza_natural_do_tipo": "Natureza natural do tipo da conta",
}

# Os `TextChoices`/enum do modelo que guardam o VALOR desses campos —
# `EnumClasse(valor).label` é o mesmo rótulo que o CADASTRO já mostra
# (formulário de conta, DL-018/DL-020); nunca uma segunda tradução escrita
# à mão aqui (duas cópias do mesmo rótulo divergem — AGENTS.md §8).
_ENUM_DO_CAMPO_DE_PENDENCIA = {
    "tipo": TipoConta,
    "tipo_da_raiz": TipoConta,
    "classificacao_patrimonial": ClassificacaoPatrimonial,
    "classificacao_patrimonial_ancestral": ClassificacaoPatrimonial,
    "classificacao_dre": ClassificacaoDre,
    "classificacao_dre_ancestral": ClassificacaoDre,
    "classificacao_dre_efetiva": ClassificacaoDre,
    # DL-048: valor fora do enum (dado corrompido por ORM direto) cai no
    # `except ValueError` de `_humanizar_valor_de_campo_de_pendencia` e sai
    # CRU — é o próprio defeito que a lista denuncia, mesmo caminho da DRE.
    "classificacao_dlpa": ClassificacaoDlpa,
    "natureza": NaturezaConta,
    # DL-062 (BL-604): mesmo enum de `natureza`, para o valor sair como
    # "Credora"/"Devedora" e nunca como a constante gravada no banco.
    "natureza_natural_do_tipo": NaturezaConta,
}


def _humanizar_valor_de_campo_de_pendencia(chave, valor):
    """Traduz o VALOR cru de um campo extra de pendência (ex.:
    `"ativo_circulante"`, `"devedora"`) para o RÓTULO que o cadastro usa
    (ex.: "Ativo circulante", "Devedora") — via `EnumClasse(valor).label`,
    nunca uma tradução escrita à mão. As DUAS listas que existem
    exatamente para nomear DADO CORROMPIDO
    (`contas_com_tipo_desconhecido`/`contas_com_classificacao_
    desconhecida` — ver `services.py`) carregam, de propósito, um valor
    que NÃO está no enum (é o próprio defeito que a lista denuncia); para
    essas, `EnumClasse(valor)` lança `ValueError` e a função devolve o
    valor cru mesmo — não há rótulo humano possível para um valor que o
    cadastro nunca aceitaria, e mostrar o valor bruto AQUI é diferente de
    mostrar o NOME DO CAMPO cru (o defeito que o BL-508 fecha): o rótulo
    da CHAVE (`_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA`, acima) já apareceu
    antes deste valor, então a frase inteira continua legível."""
    enum_do_campo = _ENUM_DO_CAMPO_DE_PENDENCIA.get(chave)
    if enum_do_campo is None:
        return str(valor)
    try:
        return enum_do_campo(valor).label
    except ValueError:
        return str(valor)


# BL-508: a AÇÃO que resolve cada pendência — critério da correção 4 do
# auditor ("toda pendência declarada nomeia uma ação que RESOLVE", não um
# adjetivo do enunciado). Uma frase por lista, ao lado de
# `NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO` (mesmas SETE chaves —
# `test_dl034_tela_do_balanco.py` cruza as duas e reprova se uma lista
# ficar sem ação). A ÚNICA que não é imperativa
# (`contas_topo_classificadas_com_natureza_divergente_entre_irmas`) é a
# que a DE-070 tornou AVISO: ela nunca IMPEDE a emissão, então a "ação"
# certa é CONFERIR, não necessariamente CORRIGIR — ver o comentário grande
# em `avaliar_emissao_do_balanco` (services.py) sobre o motivo.
ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA = {
    "contas_com_tipo_desconhecido": (
        "Corrigir o tipo cadastrado da conta no plano de contas, escolhendo um dos tipos "
        "válidos (Ativo, Passivo, Patrimônio Líquido, Receita ou Despesa)."
    ),
    "contas_com_tipo_divergente_da_raiz": (
        "Corrigir o tipo da conta ou o da raiz da sua hierarquia no plano de contas, para "
        "que os dois coincidam."
    ),
    "contas_com_classificacao_aninhada": (
        "Remover a classificação circulante/não circulante de uma das duas contas no plano "
        "de contas — deixar só o grupo OU só as contas-folha classificadas, nunca os dois "
        "ao mesmo tempo na mesma hierarquia."
    ),
    "contas_com_classificacao_desconhecida": (
        "Corrigir a classificação patrimonial da conta no plano de contas, escolhendo uma "
        "das opções válidas de circulante/não circulante."
    ),
    "contas_sem_classificacao_patrimonial": (
        "Classificar a conta (ou um ancestral dela) como circulante ou não circulante no "
        "plano de contas."
    ),
    # BL-508 (correção 4 do auditor) + relato do arquiteto sobre o
    # contrato novo de services.py: esta é a ÚNICA ação que CONFERE, não
    # CORRIGE — a pendência não impede a emissão (DE-070), e pode ser o
    # desenho CORRETO do plano de contas (ex.: retificadora). O texto NÃO
    # afirma "o Balanço já foi emitido" — isso depende de OUTRA pendência
    # não estar bloqueando ao mesmo tempo (critério de aceite 6: o aviso
    # aparece nos DOIS desfechos, emitido ou recusado por outro motivo) —
    # quem decide "emitiu ou não" é a faixa de fechamento, não este texto.
    "contas_topo_classificadas_com_natureza_divergente_entre_irmas": (
        "Aviso, não bloqueio: esta pendência sozinha NUNCA impede a emissão do Balanço. "
        "Confira se a natureza cadastrada de cada conta abaixo está correta — é o desenho "
        "esperado quando uma delas é RETIFICADORA de propósito (ex.: “(-) Provisão para "
        "devedores duvidosos” sob o mesmo grupo de “Clientes”); se não for o caso, corrija "
        "a natureza cadastrada da conta errada no plano de contas."
    ),
    "contas_nao_folha_sem_classificacao_com_movimento_proprio": (
        "Classificar esta conta (ou um ancestral dela) como circulante/não circulante no "
        "plano de contas, ou lançar os valores numa conta-folha já classificada, em vez de "
        "lançar diretamente nesta conta-síntese."
    ),
    # DL-062 (BL-604): a ÚNICA ação que é puro CONHECIMENTO, sem correção
    # obrigatória — o sistema já somou a conta com o sinal correto e o total
    # do Balanço está certo. O que a tela informa é o FATO do sinal
    # invertido, para o contador decidir se reorganiza o plano de contas
    # (aninhar a retificadora no grupo do seu tipo). Dizer "corrija" seria
    # mandar o contador alterar um cadastro que produz o número certo.
    "contas_retificadoras_rais": (
        "Aviso, não bloqueio: o total do Balanço já saiu com o sinal correto desta conta, "
        "entrada com o contrário da natureza natural do seu tipo porque ela é uma raiz "
        "isolada. Nada precisa ser corrigido para emitir. Se quiser que o plano de contas "
        "reflita essa dedução da forma mais evidente, aninhe a conta no grupo do seu tipo "
        "(ex.: “(-) Ações em Tesouraria” dentro de “Patrimônio Líquido”); o resultado "
        "continua o mesmo."
    ),
}


# DE-070 (services.py): `avaliar_emissao_do_balanco` devolve a separação
# PRONTA — `listas_pendentes` (só o que IMPEDE) e `listas_informativas`
# (só o que AVISA, nunca impede), as duas DISJUNTAS por construção do lado
# do servidor (`_LISTAS_QUE_IMPEDEM_A_EMISSAO`/`_LISTAS_QUE_SO_AVISAM`,
# ver o comentário grande de `avaliar_emissao_do_balanco`). Esta tela NÃO
# recalcula veto nenhum nem duplica o nome de nenhuma lista específica —
# só CONSOME as duas chaves e decide em qual bloco visual cada uma
# aparece (Erro bloqueante vs. Aviso, nunca bloqueante).


def _lista_de_pendencia_para_contexto(nome, itens):
    """Uma entrada de `listas_pendentes`/`listas_apenas_aviso` do
    contexto do template — título humano (`NOMES_HUMANOS_...`), linhas
    humanizadas (`_linhas_de_pendencia`) e a AÇÃO que resolve
    (`ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA`). Extraída para as DUAS
    visões da view `balanco` (bloqueada e emitida-com-aviso) montarem a
    MESMA estrutura sem repetir os três `.get`/chamada."""
    return {
        "titulo": NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO.get(nome, nome),
        "linhas": _linhas_de_pendencia(itens),
        # BL-508 (correção 4 do auditor): "explica" tem de ser
        # VERIFICÁVEL — toda pendência declarada nomeia uma ação que
        # RESOLVE. `.get(nome, ...)` nomeia a CHAVE crua só se uma lista
        # nova aparecer sem ação cadastrada ainda — nunca quebra a tela,
        # mas fica claramente incompleto para quem lê (não finge ser uma
        # instrução de verdade).
        "acao": ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA.get(
            nome, f"Ação não cadastrada para a pendência '{nome}' — avise o suporte."
        ),
    }


def _linhas_de_pendencia(itens):
    """Uma linha por conta pendente, a partir de UMA das listas de
    `emissao["listas_pendentes"]` — genérica na FORMA (cada lista de
    `apurar_saldos` nomeia campos diferentes além de "conta"/"nome": ex.
    "tipo"/"tipo_da_raiz", "classificacao_patrimonial"/"...ancestral"),
    mas HUMANIZADA no CONTEÚDO desde o BL-508 (achado A10 da auditoria da
    DL-034): antes desta correção, o "rótulo/valor de apoio" de cada campo
    extra era o PAR CRU (`f"{chave}: {valor}"`, ex.: "classificacao_
    patrimonial: ativo_circulante"), mostrando ao contador o nome do campo
    do banco e a constante interna gravada nele. Agora cada par vira
    `_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA` (a CHAVE) +
    `_humanizar_valor_de_campo_de_pendencia` (o VALOR, via `.label` do
    enum) — uma chave NOVA que `apurar_saldos` ganhar no futuro sem entrar
    nos dois dicionários acima ainda aparece aqui (nunca quebra: cai no
    `.get(chave, chave)`/`str(valor)` cru — PIOR do que humanizado, mas
    NUNCA pior do que o comportamento anterior a esta correção), e um
    teste (`test_dl034_tela_do_balanco.py`) varre o CORPO da resposta
    procurando os nomes crus dos campos conhecidos hoje.
    """
    linhas = []
    for item in itens:
        detalhes = [
            f"{_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA.get(chave, chave)}: "
            f"{_humanizar_valor_de_campo_de_pendencia(chave, valor)}"
            for chave, valor in item.items()
            if chave not in ("conta", "nome")
        ]
        linhas.append(
            {
                "conta": item.get("conta"),
                "nome": item.get("nome"),
                "detalhe": "; ".join(detalhes) if detalhes else None,
            }
        )
    return linhas


def _linha_de_conta_do_balanco(linha):
    """Uma linha IMPRESSA do Balanço, a partir de uma linha de
    `saldos["contas"]` (apurar_saldos) — MESMA conversão saldo-assinado ->
    (valor absoluto, D/C) que o Balancete já usa
    (`_saldo_absoluto_com_natureza`), pela natureza CADASTRADA desta
    própria conta (`linha["natureza"]`) — nunca a natureza do grupo: é a
    mesma prova que RC-61/BL-77 já sustentam para o Razão e o Balancete.
    """
    saldo_abs, saldo_natureza = _saldo_absoluto_com_natureza(linha["saldo"], linha["natureza"])
    natureza_cadastrada = linha["natureza"] if linha["natureza"] in NaturezaConta.values else None
    return {
        "codigo": linha["conta"],
        "nome": linha["nome"],
        "conta": {"natureza": natureza_cadastrada},
        "saldo_ptbr": _valor_ptbr(saldo_abs),
        "saldo_natureza": _indicador_natureza(saldo_natureza),
    }


def _subtotal_do_balanco(valor, tipo_do_grupo):
    """Um subtotal/total IMPRESSO do Balanço (subgrupo, grupo ou grande
    total) — mesma conversão de `_linha_de_conta_do_balanco`, mas pela
    natureza NATURAL DO TIPO (devedora no Ativo, credora no Passivo e no
    Patrimônio Líquido — o mesmo referencial da normalização do critério 1
    do plano DL-034/`avaliar_emissao_do_balanco`), porque um subtotal soma
    VÁRIAS contas e não tem uma única "natureza cadastrada" própria para
    servir de referência. Reaproveita `_saldo_absoluto_com_natureza`
    (RC-61) passando essa natureza esperada no lugar da natureza cadastrada
    de uma conta — mesma função, argumento diferente, nenhuma regra nova.

    ⚠️ **A natureza esperada vem do MAPA, e não de um ternário escrito aqui
    (DL-062, BL-604 — achado A5 da auditoria).** O ternário
    `DEVEDORA se ATIVO senão CREDORA` concorda com o mapa em tudo que existe
    hoje, e por isso o defeito era invisível; mas ele é uma SEGUNDA fonte de
    verdade para o mesmo sinal, e um `TipoConta` novo cairia nele como
    CREDORA sem ninguém perceber. A linha IMPRESSA é nível 1 — a mesma
    verdade que `apurar_saldos` aplica ao total tem de estar na mesma
    declaration, e é a tela que mostra o número ao contador.
    """
    natureza_esperada = NATUREZA_NATURAL_PARA_O_TOTAL_DO_TIPO[tipo_do_grupo]
    valor_abs, natureza_apurada = _saldo_absoluto_com_natureza(valor, natureza_esperada)
    return {
        "valor_ptbr": _valor_ptbr(valor_abs),
        "natureza": _indicador_natureza(natureza_apurada),
        # Consumido por templates/contabilidade/_saldo_grupo.html — igual
        # em espírito a `conta.natureza` de `_saldo.html` (RC-61), mas em
        # texto puro: um SUBTOTAL não tem uma única conta cadastrada para
        # servir de referência de inversão.
        "natureza_esperada": (
            "devedora" if natureza_esperada == NaturezaConta.DEVEDORA else "credora"
        ),
    }


def _montar_grupos_do_balanco(saldos):
    """Monta as CINCO seções impressas do Balanço a partir de `saldos`
    (`apurar_saldos`, dentro de `apurar_balanco_patrimonial`) — Ativo
    Circulante, Ativo Não Circulante (com os QUATRO subgrupos do art. 178
    §1º II e o subtotal), Passivo Circulante, Passivo Não Circulante e
    Patrimônio Líquido (RC-106; escopo do plano DL-034, critério 1) — mais
    os DOIS grandes totais (Ativo; Passivo + Patrimônio Líquido) que a
    folha imprime lado a lado para o contador CONFERIR a equação a olho,
    sem precisar somar na mão.

    ⚠️ Só é chamada quando `emissao["pode_emitir"]` é `True` — quem chama
    (a view `balanco`) nunca monta esta estrutura para uma apuração
    pendente (critério "a tela não emite... mostra o que falta").

    As LINHAS de cada (sub)grupo vêm de `saldos["contas"]`, filtradas pelas
    que DEFINEM uma classificação própria (`classificacao_patrimonial` não
    `None`) — exatamente o mesmo conjunto que `totais_por_classificacao`
    soma (ver o docstring de `apurar_saldos`), nunca por prefixo de código
    nem por nível da árvore. Com `pode_emitir` verdadeiro, nenhuma conta
    está classificada em mais de um lugar (a lista de aninhamento já
    garantiu isso) — filtrar por "tem classificação própria" não duplica
    nenhuma linha.
    """
    linhas_por_classificacao = {}
    for linha in saldos["contas"]:
        classificacao = linha["classificacao_patrimonial"]
        if classificacao:
            linhas_por_classificacao.setdefault(classificacao, []).append(
                _linha_de_conta_do_balanco(linha)
            )

    def _secao(classificacao):
        tipo_do_grupo = TIPO_DA_CLASSIFICACAO_PATRIMONIAL[classificacao]
        return {
            "titulo": ClassificacaoPatrimonial(classificacao).label,
            "linhas": linhas_por_classificacao.get(classificacao, []),
            "subtotal": _subtotal_do_balanco(
                saldos["totais_por_classificacao"][classificacao], tipo_do_grupo
            ),
        }

    # Os QUATRO subgrupos do Ativo Não Circulante, na ORDEM DE DECLARAÇÃO
    # do enum (art. 178 §1º II: realizável a longo prazo, investimentos,
    # imobilizado, intangível) — derivados do MAPA da lei (BL-490), nunca
    # uma lista de strings escrita à mão: toda `ClassificacaoPatrimonial`
    # cujo grupo da lei é `ATIVO_NAO_CIRCULANTE`.
    subgrupos_ativo_nao_circulante = [
        _secao(classificacao)
        for classificacao in ClassificacaoPatrimonial.values
        if GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL[classificacao]
        == GrupoDaLei.ATIVO_NAO_CIRCULANTE
    ]

    # Patrimônio Líquido é o TERCEIRO grupo do passivo (art. 178 §2º III) —
    # não é circulante nem não circulante (RC-106) — e por isso não tem
    # `classificacao_patrimonial` nenhuma. As linhas vêm das RAÍZES de tipo
    # PATRIMONIO_LIQUIDO (mesmo conjunto que `totais_por_tipo` já soma,
    # DE-056), no molde do Balancete: cada raiz já vem CONSOLIDADA com a
    # subárvore inteira (DE-020).
    linhas_pl = [
        _linha_de_conta_do_balanco(linha)
        for linha in saldos["contas"]
        if linha["raiz"] and linha["tipo"] == TipoConta.PATRIMONIO_LIQUIDO
    ]

    return {
        "ativo_circulante": _secao(ClassificacaoPatrimonial.ATIVO_CIRCULANTE),
        "ativo_nao_circulante": {
            "titulo": GrupoDaLei.ATIVO_NAO_CIRCULANTE.label,
            "subgrupos": subgrupos_ativo_nao_circulante,
            "subtotal": _subtotal_do_balanco(
                saldos["totais_por_grupo"][GrupoDaLei.ATIVO_NAO_CIRCULANTE], TipoConta.ATIVO
            ),
        },
        "passivo_circulante": _secao(ClassificacaoPatrimonial.PASSIVO_CIRCULANTE),
        "passivo_nao_circulante": _secao(ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE),
        "patrimonio_liquido": {
            "titulo": TipoConta.PATRIMONIO_LIQUIDO.label,
            "linhas": linhas_pl,
            "subtotal": _subtotal_do_balanco(
                saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO],
                TipoConta.PATRIMONIO_LIQUIDO,
            ),
        },
        "total_ativo": _subtotal_do_balanco(
            saldos["totais_por_tipo"][TipoConta.ATIVO], TipoConta.ATIVO
        ),
        "total_passivo_e_pl": _subtotal_do_balanco(
            saldos["totais_por_tipo"][TipoConta.PASSIVO]
            + saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO],
            TipoConta.PASSIVO,
        ),
        # Informativo, NUNCA usado para gatear emissão (essa decisão é
        # inteira de `avaliar_emissao_do_balanco` — ver o cabeçalho desta
        # seção): quando não-zero, é o resultado do período que AINDA não
        # foi transferido ao Patrimônio Líquido por lançamento de
        # encerramento (RC-104) — é a diferença honesta entre "Total do
        # Ativo" e "Total do Passivo + PL" que o contador vê no papel, e
        # que a equação de `apurar_saldos` já calcula. Mostrar isto é
        # cumprir "eu sei o que ele NÃO diz" em vez de deixar duas somas
        # divergentes sem explicação no documento. Formatado em VALOR
        # ABSOLUTO com o sinal preservado só em PALAVRA ("lucro"/
        # "prejuízo") — nunca "-" na frente do número (RC-90: sinal nunca é
        # o único canal, e este projeto nem usa sinal para valor negativo
        # em lugar nenhum do documento).
        #
        # BL-501 (achado da auditoria DL-034 rodada 1): a CHAVE deste
        # dicionário NÃO termina em "_ptbr" de propósito — só o campo
        # FOLHA (`valor_ptbr`, abaixo) termina. A varredura de interface
        # (`apps/core/tests/test_dl024_varredura_de_interface.py::
        # test_todo_valor_em_celula_usa_a_classe_do_sistema`) reprova
        # QUALQUER token que termine em "_ptbr" dentro de uma célula de
        # tabela sem a classe `valor-monetario` ao redor — inclusive
        # dentro de um `{% if %}` de template, que nunca é exibido. Com a
        # chave se chamando "resultado_nao_transferido_ptbr", o PRÓPRIO
        # `{% if grupos.resultado_nao_transferido_ptbr %}` (condição, não
        # saída) contava como um valor monetário desprotegido — dois
        # falsos positivos (a condição e o acesso a `.e_prejuizo`), medido
        # rodando a suíte. Renomear a chave para "resultado_nao_
        # transferido" (sem sufixo) resolve na raiz: a condição deixa de
        # casar com o padrão, e o único token que ainda termina em
        # "_ptbr" (`.valor_ptbr`, dentro do `<span class="valor-
        # monetario">` no template) continua coberto.
        "resultado_nao_transferido": (
            {
                "valor_ptbr": _valor_ptbr(abs(saldos["equacao"]["resultado_nao_transferido"])),
                "e_prejuizo": saldos["equacao"]["resultado_nao_transferido"] < 0,
            }
            if saldos["equacao"]["resultado_nao_transferido"] != 0
            else None
        ),
    }


@login_required
@require_safe
def balanco(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    data_base, erro_data_base = _data_base_do_formulario(request)
    contexto = {"empresa": empresa, "data_base": data_base}
    if erro_data_base:
        messages.error(request, erro_data_base)
        return render(request, "contabilidade/balanco.html", contexto, status=400)

    try:
        # DE-067: a ÚNICA porta de entrada que gera o documento impresso do
        # Balanço chama `apurar_balanco_patrimonial` — nunca `apurar_saldos`
        # direto —, porque só ela paga o snapshot (REPEATABLE READ) que
        # impede o documento sair com números de dois instantes diferentes.
        resultado = apurar_balanco_patrimonial(empresa=empresa, data_base=data_base)
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(request, "contabilidade/balanco.html", contexto, status=409)

    saldos = resultado["saldos"]
    emissao = resultado["emissao"]

    # DL-038 (etapa 2, critério 7): rótulo e inscrição corretos —
    # "CNPJ 12.345.678/0001-95" para pessoa jurídica, "CPF 123.456.789-09"
    # para pessoa física — nunca CNPJ fixo, que sairia em branco para
    # empresa CPF (`empresa.cnpj` é vazio por invariante de banco nesse
    # caso). Ver `rotulo_e_inscricao_da_empresa` para o porquê deste ser o
    # ponto único da formatação.
    rotulo_inscricao, inscricao_formatada = rotulo_e_inscricao_da_empresa(empresa)

    contexto.update(
        {
            # NBC TG 26 item 51/52 (RC-95) — o bloco de identificação é
            # consumido pelo template DENTRO do `<thead>` da tabela, para
            # se repetir em TODA página impressa (critério 4 do plano
            # DL-034; mesmo mecanismo já provado pelo cabeçalho de coluna
            # do Balancete, BL-282: `display: table-header-group`).
            "identificacao": resultado["identificacao"],
            "rotulo_inscricao": rotulo_inscricao,
            "inscricao_formatada": inscricao_formatada,
            # BL-282/RC-97: mesmo timbre do escritório que Balancete/
            # Diário/Razão já usam — ver o comentário em `diario` para o
            # contrato completo. Continua só na folha 1 (não é exigência do
            # item 51, que fala da ENTIDADE cliente, não do escritório
            # emitente); o bloco que PRECISA repetir em toda folha é o de
            # `identificacao`, acima, tratado à parte no template.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
            # Estado VAZIO (critério do Balancete, B4/BL-283) — calculado
            # UMA vez, aqui, para o template nunca precisar adivinhar
            # "ausência de chave" como "vazio": a chave está SEMPRE
            # presente a partir deste ponto.
            "empresa_tem_plano_de_contas": bool(saldos["contas"]),
        }
    )

    if not saldos["contas"]:
        # Estado VAZIO: empresa sem NENHUMA conta cadastrada — mesmo
        # critério do Balancete (B4/BL-283): nada para classificar, nada
        # para recusar ainda, e mostrar uma recusa aqui confundiria "falta
        # cadastrar o plano" com "há pendência de classificação".
        return render(request, "contabilidade/balanco.html", contexto)

    # DE-070: `emissao["listas_informativas"]` já vem SEPARADA, pronta do
    # servidor — a que só AVISA, nunca impede (ver o comentário grande de
    # `avaliar_emissao_do_balanco`, services.py). A tela só monta a
    # ESTRUTURA de apresentação (título/linhas/ação); aparece tanto
    # emitindo quanto recusando, se estiver presente nos dois casos —
    # fora do `{% if/elif/else %}` do template, que decide só "monta a
    # tabela ou não".
    contexto["listas_apenas_aviso"] = [
        _lista_de_pendencia_para_contexto(nome, itens)
        for nome, itens in emissao["listas_informativas"].items()
    ]

    if not emissao["pode_emitir"]:
        # "O que eu vou entregar fecha, e eu sei o que ele NÃO diz": havendo
        # QUALQUER pendência que VETE, a tela NÃO monta a tabela do Balanço
        # — só o que falta, nomeado (critério 1 e "o momento da verdade" do
        # plano DL-034). 200, não um código de erro: a tela RESPONDEU
        # corretamente à pergunta "pode emitir?" — a resposta é "não, e eis
        # o porquê", que é sucesso da TELA, não falha de protocolo.
        contexto.update(
            {
                "pode_emitir": False,
                "residuo_pendente": [
                    {
                        "tipo_label": TipoConta(tipo).label,
                        "diferenca_ptbr": _valor_ptbr(abs(valor)),
                    }
                    for tipo, valor in emissao["residuo_pendente"].items()
                ],
                # `emissao["listas_pendentes"]` já vem só com o que
                # BLOQUEIA (DE-070/services.py) — a que só avisa está em
                # `listas_informativas`, tratada acima, nunca aqui.
                "listas_pendentes": [
                    _lista_de_pendencia_para_contexto(nome, itens)
                    for nome, itens in emissao["listas_pendentes"].items()
                ],
            }
        )
        return render(request, "contabilidade/balanco.html", contexto)

    contexto.update({"pode_emitir": True, "grupos": _montar_grupos_do_balanco(saldos)})
    return render(request, "contabilidade/balanco.html", contexto)


# ---------------------------------------------------------------------------
# DRE (DL-045 fatia 3)
# ---------------------------------------------------------------------------


def _competencia_adjacente(ano, mes, delta_meses):
    """Competência (ano, mês) deslocada por `delta_meses` — usada pela
    navegação "‹ anterior / seguinte ›" da DRE (mesma aritmética que
    qualquer calendário civil usa: o mês sempre fica entre 1 e 12, o ano
    rola sozinho nas duas pontas). Sem limite de faixa aqui: função
    PURA, só aritmética — quem decide se o resultado é uma competência
    VÁLIDA (dentro de `_ANO_MINIMO_COMPETENCIA`/`_ANO_MAXIMO_COMPETENCIA`)
    é `_ano_mes_de_competencia_valido`, chamada por quem MONTA a tela
    (`dre`, mais abaixo) para decidir se o link correspondente aparece.

    ⚠️ R10 (reconferência DL-045): a versão anterior desta função
    argumentava que "um link 'seguinte' nunca falha silenciosamente ao
    ser MONTADO, mesmo perto da borda da faixa" — e por isso a tela
    SEMPRE montava os dois links, sem checar a faixa. O auditor mediu o
    efeito: em `ano=2999&mes=12`, o link "seguinte" apontava para
    `3000/1`, e o clique devolvia 400. "Nunca falha ao ser MONTADO" era
    verdade, mas irrelevante — o link levava a um beco sem saída mesmo
    assim. Agora `dre()` decide, com `_ano_mes_de_competencia_valido`,
    se cada link aparece; esta função continua só a aritmética.
    """
    indice = (ano * 12) + (mes - 1) + delta_meses
    return indice // 12, indice % 12 + 1


def _competencia_dre_do_formulario(request):
    """Lê 'ano'/'mes' da querystring da DRE — DIFERENTE do Balanço
    (`_data_base_do_formulario`, uma FOTOGRAFIA de uma única data): a DRE
    é apurada por COMPETÊNCIA (ano + mês), a mesma gramática que o painel
    de fechamento já pede (`_competencia_pedida`, reaproveitada aqui, não
    reimplementada).

    Ausência dos DOIS parâmetros (primeira visita) usa o mês corrente
    como padrão de conveniência — mesma convenção de `_data_base_do_
    formulario`. Presença malformada, ou de só um dos dois, nunca cai no
    padrão em silêncio: `_competencia_pedida` recusa com mensagem.
    """
    if not request.GET.get("ano") and not request.GET.get("mes"):
        hoje = timezone.localdate()
        return hoje.year, hoje.month, None
    return _competencia_pedida(request.GET)


def _valor_dre(valor):
    """Formata um valor MONETÁRIO da DRE (uma linha do art. 187 ou um dos
    seis subtotais, HI-29) em pt-BR — negativo entre PARÊNTESES, nunca só
    o sinal "-" (RC-90: sinal nunca é o único canal de um valor negativo;
    ver `_saldo_grupo.html`, que aplica a mesma regra ao Balanço por um
    caminho diferente, o indicador D/C).

    Decisão de apresentação desta etapa (plano DL-045: "negativos entre
    parênteses ou com sinal — siga o que o Balanço já faz"): o Balanço
    NUNCA mostra um valor negativo no documento — ele mostra o indicador
    D/C (`_indicador_natureza`/`_saldo_grupo.html`), porque toda linha e
    todo subtotal dele têm uma NATUREZA esperada e o Balanço testa
    inversão CONTRA ela. A DRE é outra pergunta: uma LINHA (magnitude no
    lado natural da própria linha, `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE`
    em models.py) pode legitimamente vir negativa quando a conta está
    classificada nela mas o saldo caiu do lado oposto — um alerta de
    conferência; e um SUBTOTAL pode vir negativo porque o período deu
    PREJUÍZO naquele nível — o resultado normal de um mês ruim, não uma
    anomalia. As duas leituras cabem na MESMA apresentação: "este valor
    foi para o lado que REDUZ o total seguinte", que é exatamente o que
    o parêntese comunica num documento contábil brasileiro — sem inventar
    uma segunda convenção (D/C) que não faz sentido para um SUBTOTAL, que
    não é uma conta e não tem "natureza cadastrada" nenhuma.
    """
    return {"ptbr": _valor_ptbr(abs(valor)), "negativo": valor < 0}


def _linha_dre_para_contexto(classificacao, linhas_mes, linhas_acumulado):
    return {
        "titulo": ClassificacaoDre(classificacao).label,
        "mes": _valor_dre(linhas_mes[classificacao]),
        "acumulado": _valor_dre(linhas_acumulado[classificacao]),
    }


def _subtotal_dre_para_contexto(titulo, subtotais_mes, subtotais_acumulado, chave):
    return {
        "titulo": titulo,
        "mes": _valor_dre(subtotais_mes[chave]),
        "acumulado": _valor_dre(subtotais_acumulado[chave]),
    }


def _montar_linhas_da_dre(dre_apurada):
    """Monta as TREZE linhas e os SEIS subtotais IMPRESSOS da DRE (art.
    187, HI-29), na ORDEM FIXA da lei, cada um sob um NOME próprio —
    mesmo desenho de `_montar_grupos_do_balanco`: a ordem e os subtotais
    intercalados são estrutura LEGAL fixa (nunca varia por empresa), não
    um dado para percorrer num laço genérico. `⚠️` Só é chamada quando
    `emissao["pode_emitir"]` é `True` — quem chama (`dre`, abaixo) nunca
    monta esta estrutura para uma apuração com pendência.

    DL-045, reconferência (F1/DE-086): os rótulos de DUAS das seis chaves
    — "receita_liquida" continua "Receita líquida", mas "lucro_bruto" e
    "lucro_liquido" trocam de RÓTULO impresso, nunca de CHAVE (o serviço,
    services.py, continua chamando os dois campos de `"lucro_bruto"`/
    `"lucro_liquido"` — fora do meu escopo de arquivo mexer nisso, e não
    precisa: é só o TÍTULO exibido que muda):
    - "Lucro bruto" -> **"Resultado bruto"** (ITG 1000, anexo 3 — o nome
      que a norma usa para a linha logo depois do custo, neutro quanto ao
      sinal: o valor pode legitimamente sair negativo).
    - "Lucro líquido do período" -> **"Lucro (prejuízo) líquido do
      período"** (art. 187, VII, Lei 6.404/76: "demonstração do
      resultado do exercício discriminará... o lucro ou prejuízo líquido
      do exercício"). O sinal continua saindo só pelo PARÊNTESE
      (`_valor_dre`, RC-90) — o rótulo NOMEIA as duas possibilidades,
      nunca decide qual delas é o caso.
    """
    linhas_mes = dre_apurada["coluna_mes"]["linhas"]
    linhas_acumulado = dre_apurada["coluna_acumulado"]["linhas"]
    subtotais_mes = dre_apurada["coluna_mes"]["subtotais"]
    subtotais_acumulado = dre_apurada["coluna_acumulado"]["subtotais"]

    def _linha(classificacao):
        return _linha_dre_para_contexto(classificacao, linhas_mes, linhas_acumulado)

    def _subtotal(chave, titulo):
        return _subtotal_dre_para_contexto(titulo, subtotais_mes, subtotais_acumulado, chave)

    return {
        "receita_bruta": _linha(ClassificacaoDre.RECEITA_BRUTA),
        "deducoes_da_receita": _linha(ClassificacaoDre.DEDUCOES_DA_RECEITA),
        "receita_liquida": _subtotal("receita_liquida", "Receita líquida"),
        "custo": _linha(ClassificacaoDre.CUSTO),
        "lucro_bruto": _subtotal("lucro_bruto", "Resultado bruto"),
        "despesas_com_vendas": _linha(ClassificacaoDre.DESPESAS_COM_VENDAS),
        "despesas_gerais_e_administrativas": _linha(
            ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS
        ),
        "outras_receitas": _linha(ClassificacaoDre.OUTRAS_RECEITAS),
        "outras_despesas": _linha(ClassificacaoDre.OUTRAS_DESPESAS),
        "outras_despesas_operacionais": _linha(ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS),
        "resultado_equivalencia_patrimonial": _linha(
            ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL
        ),
        "resultado_antes_das_receitas_e_despesas_financeiras": _subtotal(
            "resultado_antes_das_receitas_e_despesas_financeiras",
            "Resultado antes do resultado financeiro",
        ),
        "receitas_financeiras": _linha(ClassificacaoDre.RECEITAS_FINANCEIRAS),
        "despesas_financeiras": _linha(ClassificacaoDre.DESPESAS_FINANCEIRAS),
        "resultado_financeiro": _subtotal("resultado_financeiro", "Resultado financeiro"),
        "resultado_antes_dos_tributos_sobre_o_lucro": _subtotal(
            "resultado_antes_dos_tributos_sobre_o_lucro",
            "Resultado antes dos tributos sobre o lucro",
        ),
        "provisao_irpj_csll": _linha(ClassificacaoDre.PROVISAO_IRPJ_CSLL),
        "participacoes": _linha(ClassificacaoDre.PARTICIPACOES),
        "lucro_liquido": _subtotal("lucro_liquido", "Lucro (prejuízo) líquido do período"),
    }


_TITULO_DA_COLUNA_DRE = {
    "coluna_mes": "Mês",
    "coluna_acumulado": "Acumulado do exercício",
}

# DL-045 fatia 3: título humano e ação que RESOLVE cada lista de
# pendência da DRE (`_apurar_coluna_dre`, services.py) — mesmo padrão de
# `NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO`/`ACAO_QUE_RESOLVE_A_
# PENDENCIA_POR_LISTA` (BL-508), um DICT PRÓPRIO da DRE (nomes de lista
# diferentes, nunca misturados com os do Balanço).
#
# DL-045, correção da rodada 1 de auditoria (A1/A2, DE-085): o servidor
# passou a vetar (`_LISTAS_DA_DRE_QUE_IMPEDEM_A_EMISSAO`, services.py)
# "aninhada com linha diferente" (o valor sai na linha ERRADA da DRE —
# antes só avisava) e "desconhecida" (sempre vetou, mas o texto aqui já
# estava certo), e ACRESCENTOU duas listas novas: "tipo divergente da
# linha" (veta — inclusive conta patrimonial sob linha de resultado) e
# "aninhada com a MESMA linha" (só avisa — o cadastro é redundante, mas a
# DRE sai correta, o ancestral já consolida a subárvore). A separação
# pendentes/informativas continua vindo PRONTA do servidor (DE-070) — esta
# tela nunca decide sozinha o que bloqueia.
NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DA_DRE = {
    "contas_sem_classificacao_dre_com_movimento": (
        "Conta de resultado (receita ou despesa), sem contas subordinadas, com movimento "
        "no período e sem linha da DRE — nem própria, nem herdada de um ancestral"
    ),
    "contas_nao_folha_sem_classificacao_dre_com_movimento_proprio": (
        "Conta que agrupa outras contas (não é folha), sem linha da DRE própria nem de um "
        "ancestral, com movimento lançado diretamente nela"
    ),
    "contas_com_classificacao_dre_aninhada_linha_diferente": (
        "Conta com linha da DRE própria DIFERENTE da de um ancestral também classificado — o "
        "valor sai na linha ERRADA da demonstração"
    ),
    "contas_com_classificacao_dre_aninhada_mesma_linha": (
        "Conta com linha da DRE própria IGUAL à de um ancestral também classificado — "
        "redundante no cadastro, mas a demonstração sai correta"
    ),
    "contas_com_tipo_divergente_da_linha": (
        "Conta com movimento no período cujo tipo (Ativo, Passivo, Patrimônio Líquido, "
        "Receita ou Despesa) não é aceito pela linha da DRE efetiva — própria ou herdada de "
        "um ancestral (inclusive conta patrimonial classificada, direta ou indiretamente, "
        "numa linha de resultado)"
    ),
    "contas_com_classificacao_dre_desconhecida": (
        "Conta com uma linha da DRE gravada que não existe no cadastro atual (dado fora do "
        "padrão vigente)"
    ),
}
ACAO_QUE_RESOLVE_A_PENDENCIA_DRE_POR_LISTA = {
    "contas_sem_classificacao_dre_com_movimento": (
        "Classificar a conta (ou um ancestral dela) com uma linha da DRE."
    ),
    "contas_nao_folha_sem_classificacao_dre_com_movimento_proprio": (
        "Classificar esta conta (ou um ancestral dela) com uma linha da DRE, ou lançar os "
        "valores numa conta-folha já classificada, em vez de lançar diretamente nesta "
        "conta-síntese."
    ),
    "contas_com_classificacao_dre_aninhada_linha_diferente": (
        "Corrigir a linha da DRE de uma das duas contas — deixar só o ancestral OU só a "
        "conta-folha classificados com a linha CERTA, nunca dois valores divergentes na "
        "mesma hierarquia."
    ),
    "contas_com_classificacao_dre_aninhada_mesma_linha": (
        "Aviso, não bloqueio: remover a linha da DRE de uma das duas contas, se preferir um "
        "cadastro mais enxuto — a demonstração já sai correta do jeito que está."
    ),
    "contas_com_tipo_divergente_da_linha": (
        "Corrigir o tipo da conta, ou a linha da DRE dela (ou de um ancestral), para os dois "
        "ficarem compatíveis (Lei 6.404/76, art. 187)."
    ),
    "contas_com_classificacao_dre_desconhecida": (
        "Corrigir a linha da DRE da conta, escolhendo uma das opções válidas."
    ),
}

# DL-045, correção da rodada 1 de auditoria (A3/A4, DE-085 item 4): título
# e ação da lista informativa "estornos_de_zeramento_na_coluna" —
# DIFERENTE das listas acima: não é uma chave `contas_*` (é sobre
# LANÇAMENTOS de estorno, nunca bloqueia), então tem forma de item
# própria (`{"lancamento", "data", "historico", "estorno_de_chave"}`,
# nunca `{"conta", "nome", ...}`) e uma tradução separada, fora dos dois
# dicts acima — ver `_lista_de_estornos_de_zeramento_para_contexto`.
_TITULO_DA_LISTA_DE_ESTORNOS_DE_ZERAMENTO = (
    "Lançamentos de estorno de zeramento no período — a DRE nunca os conta (nem ao "
    "lançamento de zeramento original), mas o zeramento do MÊS em que o estorno aconteceu já "
    "tinha visto o estorno como lançamento normal na hora em que rodou"
)
_ACAO_QUE_RESOLVE_A_LISTA_DE_ESTORNOS_DE_ZERAMENTO = (
    "Nenhuma correção necessária — confira se a diferença entre esta coluna da DRE e o valor "
    "que o zeramento deste mês transferiu é só o efeito do(s) estorno(s) listado(s) abaixo."
)


def _lista_de_pendencia_dre_para_contexto(nome, itens, contas_id_por_codigo):
    """Lista de pendência baseada em CONTA (todas as listas de `_apurar_
    coluna_dre` exceto "estornos_de_zeramento_na_coluna", tratada à
    parte). `linha.conta_id`, quando localizada, faz o template linkar
    direto para "classificar esta conta" (`conta_classificacao_dre`,
    mais abaixo) — critério 2 do plano: "link para classificar a conta".

    R8 (reconferência DL-045): `linha["tipo"]` (o valor CRU, ex.
    "ativo") também é copiado do item aqui, ao lado de `conta_id` —
    `_linhas_de_pendencia` (compartilhada com o Balanço) só HUMANIZA
    "tipo" dentro da string `detalhe` ("Tipo cadastrado: Ativo"), nunca
    o deixa como chave própria do dict; sem este passo, `linha.tipo` no
    template (dre.html) sempre resolveria vazio e o veto ofereceria o
    link "classificar esta conta" até para conta PATRIMONIAL sob linha
    de resultado — exatamente o link que R8 pede para SUMIR nesse caso,
    trocado por "mover a conta para o grupo patrimonial correto no
    plano de contas". Só `contas_com_tipo_divergente_da_linha` carrega
    "tipo" no item cru (services.py); as demais listas desta coluna
    (aninhada, desconhecida) devolvem `None` aqui — contas
    estruturalmente já classificadas, portanto sempre de resultado, o
    que o template trata como "mostra o link" (ausência de tipo
    patrimonial).
    """
    linhas = _linhas_de_pendencia(itens)
    for linha, item in zip(linhas, itens, strict=True):
        linha["conta_id"] = contas_id_por_codigo.get(linha["conta"])
        linha["tipo"] = item.get("tipo")
    return {
        "titulo": NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DA_DRE.get(nome, nome),
        "tipo_linha": "conta",
        "linhas": linhas,
        "acao": ACAO_QUE_RESOLVE_A_PENDENCIA_DRE_POR_LISTA.get(
            nome, f"Ação não cadastrada para a pendência '{nome}' — avise o suporte."
        ),
    }


def _lista_de_estornos_de_zeramento_para_contexto(itens):
    """Lista informativa "estornos_de_zeramento_na_coluna" — itens são
    LANÇAMENTOS (`{"lancamento", "data", "historico", "estorno_de_chave"}`),
    nunca contas; `tipo_linha="lancamento"` avisa o template para usar o
    OUTRO ramo de renderização (nunca "Conta None — None", o que
    aconteceria se estes itens passassem pelo humanizador genérico de
    conta, `_linhas_de_pendencia`, que só conhece "conta"/"nome").
    """
    return {
        "titulo": _TITULO_DA_LISTA_DE_ESTORNOS_DE_ZERAMENTO,
        "tipo_linha": "lancamento",
        "linhas": itens,
        "acao": _ACAO_QUE_RESOLVE_A_LISTA_DE_ESTORNOS_DE_ZERAMENTO,
    }


def _contas_id_por_codigo_das_pendencias_dre(empresa, emissao):
    """Mapa código -> id de TODAS as contas citadas em QUALQUER pendência
    BASEADA EM CONTA da DRE (nas duas colunas, bloqueante ou só aviso) —
    UMA consulta batelada (`codigo__in`), nunca uma por linha de
    pendência, para o template linkar direto para "classificar esta
    conta". A lista "estornos_de_zeramento_na_coluna" nunca contribui
    código nenhum aqui (seus itens não têm campo "conta"). Vazio, sem
    consulta nenhuma, quando não há pendência baseada em conta (o caso
    comum, dia a dia).
    """
    codigos = set()
    for dict_por_coluna in (emissao["listas_pendentes"], emissao["listas_informativas"]):
        for listas in dict_por_coluna.values():
            for nome, itens in listas.items():
                if nome == "estornos_de_zeramento_na_coluna":
                    continue
                codigos.update(item["conta"] for item in itens)
    if not codigos:
        return {}
    return dict(
        Conta.objects.filter(empresa=empresa, codigo__in=codigos).values_list("codigo", "id")
    )


def _colunas_de_pendencia_dre(dict_por_coluna, contas_id_por_codigo):
    """`{"coluna_mes": {nome_lista: itens}, "coluna_acumulado": {...}}` ->
    lista pronta para o template percorrer, UMA entrada por coluna que
    tem algo a reportar (a mesma forma agrupada por coluna que `avaliar_
    emissao_da_dre` já devolve, DL-045 — "as duas colunas vetam", decisão
    do arquiteto de 26/09/2026) — nunca achatada, para o veto continuar
    dizendo EM QUAL coluna cada pendência apareceu. Trata QUALQUER nome de
    lista BASEADA EM CONTA genericamente (`.get(nome, nome)` no título,
    nunca um `if` por nome específico) — só "estornos_de_zeramento_na_
    coluna" desvia para o construtor próprio, por ter forma de item
    diferente (ver o comentário da constante, acima).
    """
    return [
        {
            "titulo": _TITULO_DA_COLUNA_DRE.get(nome_coluna, nome_coluna),
            "listas": [
                _lista_de_estornos_de_zeramento_para_contexto(itens)
                if nome == "estornos_de_zeramento_na_coluna"
                else _lista_de_pendencia_dre_para_contexto(nome, itens, contas_id_por_codigo)
                for nome, itens in listas.items()
            ],
        }
        for nome_coluna, listas in dict_por_coluna.items()
    ]


@login_required
@require_safe
def dre(request, empresa_id):
    """Demonstração do Resultado do Exercício (DL-045 fatia 3 — tela e
    documento). Mesmo desenho do Balanço (`balanco`, acima): mesma
    autorização de leitura (`_pode_ler`), mesma recusa de livro-caixa,
    mesmo veto de emissão com lista de pendências nomeadas (critério 6 do
    plano), mesmo bloco de identificação NBC TG 26 item 51 repetido em
    toda página impressa (critério 7). A diferença estrutural é o
    PERÍODO: o Balanço é uma fotografia de uma DATA; a DRE é apurada por
    COMPETÊNCIA (mês e acumulado do exercício, HI-28), então o seletor
    pede ano/mês, como o painel de fechamento já pede — nunca uma segunda
    gramática de data inventada aqui.

    O achado que eu tinha reportado (`apurar_dre` sem o snapshot
    `REPEATABLE READ` que `apurar_balanco_patrimonial` paga, DE-067) foi
    corrigido na rodada 1 de auditoria do servidor (A5,
    docs/auditorias/2026-09-26-dl-045-rodada-1.md) — `apurar_dre` agora
    abre a MESMA transação de nível superior com `SET TRANSACTION
    ISOLATION LEVEL REPEATABLE READ`, degradando sem quebrar quando
    chamada de dentro de um `transaction.atomic()` já aberto (mesmo
    padrão do Balanço). Nada para esta tela fazer a respeito.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    # R8 (reconferência DL-045): "classificar esta conta" (link do veto,
    # dre.html) só aparece para quem PODE ESCRITURAR — antes, qualquer
    # papel de leitura via o link e recebia 403 ao segui-lo (medido pelo
    # auditor com o papel PARALEGAL). Calculado aqui, presente em TODOS
    # os `render()` desta view (empty state, erro, veto, sucesso) — o
    # template nunca precisa adivinhar ausência de chave como "não pode".
    contexto = {"empresa": empresa, "pode_escriturar": _pode_escriturar(request)}

    ano, mes, erro_competencia = _competencia_dre_do_formulario(request)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return render(request, "contabilidade/dre.html", contexto, status=400)

    ano_anterior, mes_anterior = _competencia_adjacente(ano, mes, -1)
    ano_seguinte, mes_seguinte = _competencia_adjacente(ano, mes, 1)
    contexto.update(
        {
            "ano": ano,
            "mes": mes,
            "data_referencia": date(ano, mes, 1),
            # R10 (reconferência DL-045): o link só aparece quando a
            # competência adjacente é VÁLIDA (dentro de `_ANO_MINIMO_
            # COMPETENCIA`/`_ANO_MAXIMO_COMPETENCIA`) — omitido perto das
            # duas bordas da faixa, em vez de sempre montado e levando a
            # um 400 ao ser seguido (o que a versão anterior fazia; ver o
            # docstring de `_competencia_adjacente`).
            "ano_anterior": ano_anterior
            if _ano_mes_de_competencia_valido(ano_anterior, mes_anterior)
            else None,
            "mes_anterior": mes_anterior,
            "ano_seguinte": ano_seguinte
            if _ano_mes_de_competencia_valido(ano_seguinte, mes_seguinte)
            else None,
            "mes_seguinte": mes_seguinte,
        }
    )

    # Estado VAZIO (mesmo critério do Balancete/Balanço, B4/BL-283):
    # empresa sem NENHUMA conta cadastrada. `apurar_dre` não devolve a
    # lista de contas (ela apura só os TOTAIS agregados — ver o docstring
    # dela), então esta consulta própria decide "vazio" ANTES de apurar
    # nada; nada para classificar, nada para recusar ainda.
    empresa_tem_plano_de_contas = Conta.objects.filter(empresa=empresa).exists()
    contexto["empresa_tem_plano_de_contas"] = empresa_tem_plano_de_contas
    if not empresa_tem_plano_de_contas:
        return render(request, "contabilidade/dre.html", contexto)

    try:
        dre_apurada = apurar_dre(empresa=empresa, ano=ano, mes=mes)
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(request, "contabilidade/dre.html", contexto, status=409)

    emissao = avaliar_emissao_da_dre(dre_apurada)

    # DL-045 fatia 3, critério 7: rótulo/inscrição e o bloco de
    # identificação NBC TG 26 item 51 — MESMAS funções que o Balanço já
    # usa (`rotulo_e_inscricao_da_empresa`/`identificacao_da_
    # demonstracao`), nenhuma segunda cópia. `identificacao_da_
    # demonstracao()` é pura (sem consulta): `apurar_balanco_patrimonial`
    # a embute no próprio retorno; `apurar_dre` não (ver o achado no
    # docstring desta view), então esta tela chama a função direto.
    rotulo_inscricao, inscricao_formatada = rotulo_e_inscricao_da_empresa(empresa)
    contexto.update(
        {
            "identificacao": identificacao_da_demonstracao(),
            "rotulo_inscricao": rotulo_inscricao,
            "inscricao_formatada": inscricao_formatada,
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
            # NBC TG 26 item 51(c) — "o período coberto": a DRE cobre DOIS
            # períodos ao mesmo tempo (mês e acumulado do exercício), então
            # o bloco de identificação (dentro do `<thead>`, ver dre.html)
            # precisa das DUAS datas-fim, não só do mês pedido.
            "data_fim_mes": dre_apurada["data_fim_mes"],
            "data_inicio_exercicio": dre_apurada["data_inicio_exercicio"],
        }
    )

    contas_id_por_codigo = _contas_id_por_codigo_das_pendencias_dre(empresa, emissao)

    # `emissao["listas_informativas"]` aparece nos DOIS desfechos (emitida
    # ou recusada por outro motivo) — mesma regra do Balanço (DE-070):
    # fica FORA do if/else que decide "monta a demonstração ou não".
    contexto["listas_apenas_aviso_por_coluna"] = _colunas_de_pendencia_dre(
        emissao["listas_informativas"], contas_id_por_codigo
    )

    if not emissao["pode_emitir"]:
        # Critério 6 do plano: havendo QUALQUER pendência que VETE (em
        # QUALQUER coluna — "as duas colunas vetam"), a tela NÃO monta a
        # DRE — só o que falta, nomeado, por coluna. 200, não um código
        # de erro: a tela respondeu corretamente à pergunta "pode
        # emitir?" — mesma leitura do veto do Balanço.
        contexto.update(
            {
                "pode_emitir": False,
                "residuo_pendente_por_coluna": [
                    {
                        "titulo": _TITULO_DA_COLUNA_DRE.get(nome_coluna, nome_coluna),
                        "itens": [
                            {
                                "tipo_label": TipoConta(tipo).label,
                                "diferenca_ptbr": _valor_ptbr(abs(valor)),
                            }
                            for tipo, valor in residuo.items()
                        ],
                    }
                    for nome_coluna, residuo in emissao["residuo_pendente"].items()
                ],
                "listas_pendentes_por_coluna": _colunas_de_pendencia_dre(
                    emissao["listas_pendentes"], contas_id_por_codigo
                ),
            }
        )
        return render(request, "contabilidade/dre.html", contexto)

    contexto.update({"pode_emitir": True, "linhas": _montar_linhas_da_dre(dre_apurada)})
    return render(request, "contabilidade/dre.html", contexto)


# ---------------------------------------------------------------------------
# DL-048 — DLPA (Demonstração dos Lucros ou Prejuízos Acumulados): tela
# irmã da DRE (`dre`, acima). Mesmo esqueleto — autorização de leitura,
# recusa de livro-caixa, veto do SERVIDOR com pendências nomeadas e link
# de correção, bloco de identificação item 51 repetido em cada página.
# ---------------------------------------------------------------------------

# Título humano e AÇÃO que resolve de cada lista de pendência da DLPA
# (chaves de `apurar_dlpa["pendencias"]`, services.py) — mesma dupla de
# dicionários que Balanço e DRE usam (BL-508: toda pendência nomeia a ação
# que resolve; `.get` com a chave crua nunca quebra a tela, só denuncia
# lista nova sem cadastro). Teste derivado em `test_dl048_dlpa.py` cruza as
# chaves das duas com `_LISTAS_DA_DLPA_QUE_IMPEDEM_A_EMISSAO`.
_TITULOS_DAS_LISTAS_DE_PENDENCIA_DA_DLPA = {
    "nenhuma_conta_de_lucros_ou_prejuizos_acumulados_classificada": (
        "Conta de lucros ou prejuízos acumulados"
    ),
    "movimentos_sem_classificacao_dlpa": "Movimento das contas de lucros acumulados",
    "contas_com_classificacao_dlpa_desconhecida": "Classificação da DLPA desconhecida",
    "diferenca_de_fechamento": "Diferença entre a DLPA e o Balanço",
}

ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DLPA_POR_LISTA = {
    "nenhuma_conta_de_lucros_ou_prejuizos_acumulados_classificada": (
        "Classifique, no plano de contas, a conta que recebe o resultado do exercício "
        "(campo “Linha da DLPA” → “Lucros ou prejuízos acumulados”)."
    ),
    "movimentos_sem_classificacao_dlpa": (
        "Classifique cada conta listada (link ao lado): o movimento delas contra os lucros "
        "acumulados não tem linha da DLPA — o produto não adivinha de que evento se trata."
    ),
    "contas_com_classificacao_dlpa_desconhecida": (
        "Reclassifique cada conta listada com uma das opções válidas do campo “Linha da "
        "DLPA” — o valor gravado não existe mais no cadastro."
    ),
    "diferenca_de_fechamento": (
        "A soma das linhas da DLPA não bate com o saldo das contas sujeito no "
        "Balanço da mesma data — confira os lançamentos dessas contas pelo Razão e, se o "
        "plano de contas mudou de estrutura (conta sujeito com subcontas movimentadas), "
        "classifique as subcontas também: isto não deveria acontecer em dado íntegro."
    ),
}

_TITULOS_DOS_AVISOS_DA_DLPA = {
    "resultado_nao_transferido": "Resultado do exercício ainda não zerado",
}


def _saldo_entre_parenteses(valor):
    """Monetário em pt-BR com o negativo entre parênteses (RC-90), como em
    toda célula assinada deste produto — inclusive nas linhas de Balanço e
    DRE que o contador vai conferir para validar o número da DLPA.

    Existe por causa do achado 4 da auditoria de 29/09/2026: o veto da
    conciliação saía com o sinal de menos solto, o que destoava do
    documento que o contador tem na mão do outro lado da tela.
    """
    if valor < 0:
        return f"({_valor_ptbr(abs(valor))})"
    return _valor_ptbr(valor)


def _lista_de_pendencia_dlpa_para_contexto(nome, itens, contas_id_por_codigo):
    """Uma entrada do veto da DLPA, pronta para o template — título humano,
    `tipo_linha` (o ramo de renderização) e a AÇÃO que resolve.

    DUAS formas de item, e o `nome` da lista decide o ramo (as listas de
    `apurar_dlpa` têm contrato próprio, diferente das da DRE — que são
    todas baseadas em conta ou em lançamento):

    - baseada em CONTA (`"conta"`/`"nome"` + campo extra) →
      `tipo_linha="conta"`, humanizada por `_linhas_de_pendencia` (mesmo
      caminho do Balanço/DRE) e com `conta_id` resolvido em UMA consulta
      batelada para o link "classificar esta conta";
    - ITEM sem conta (nenhuma conta sujeito; diferença de fechamento) →
      `tipo_linha="detalhe"`, texto pronto, sem link.
    """
    titulo = _TITULOS_DAS_LISTAS_DE_PENDENCIA_DA_DLPA.get(nome, nome)
    acao = ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DLPA_POR_LISTA.get(
        nome, f"Ação não cadastrada para a pendência '{nome}' — avise o suporte."
    )
    if nome == "nenhuma_conta_de_lucros_ou_prejuizos_acumulados_classificada":
        linhas = [{"conta": None, "nome": None, "detalhe": item["mensagem"]} for item in itens]
        return {"titulo": titulo, "tipo_linha": "detalhe", "linhas": linhas, "acao": acao}
    if nome == "diferenca_de_fechamento":
        # Achado 4 da auditoria de 29/09/2026: o veto agora NOMEIA as contas
        # sujeito com o próprio saldo (as outras três pendências já nomeavam
        # e linkavam; esta era a que menos ajudava), e o negativo sai entre
        # parênteses como no resto do documento (RC-90) — antes saía com o
        # sinal de menos, e a linha do Balanço que o contador vai conferir
        # usa parênteses.
        linhas = []
        for item in itens:
            contas_do_item = [
                {
                    "conta": conta["conta"],
                    "nome": conta["nome"],
                    # Negativo entre parênteses, como em TODA célula
                    # assinada deste produto (RC-90) — inclusive na linha do
                    # Balanço que o contador vai conferir para validar.
                    "detalhe": f"Saldo no Balanço: {_saldo_entre_parenteses(conta['saldo'])}",
                }
                for conta in item.get("contas", [])
            ]
            # `apurar_dlpa` sempre devolve as contas; o texto de total fica
            # como rede de segurança para um item vindo de base anterior.
            linhas.extend(
                contas_do_item
                or [
                    {
                        "conta": None,
                        "nome": None,
                        "detalhe": (
                            "Soma das linhas da DLPA menos o saldo das contas "
                            f"sujeito no Balanço: {_valor_ptbr(item['diferenca'])}."
                        ),
                    }
                ]
            )
        return {"titulo": titulo, "tipo_linha": "detalhe", "linhas": linhas, "acao": acao}

    linhas = _linhas_de_pendencia(itens)
    for linha in linhas:
        linha["conta_id"] = contas_id_por_codigo.get(linha["conta"])
    return {"titulo": titulo, "tipo_linha": "conta", "linhas": linhas, "acao": acao}


def _contas_id_por_codigo_das_pendencias_dlpa(empresa, emissao):
    """Mapa código → id das contas citadas em QUALQUER pendência da DLPA —
    UMA consulta batelada, nunca uma por linha (mesmo molde de
    `_contas_id_por_codigo_das_pendencias_dre`). Listas sem "conta"
    (nenhuma conta sujeito; diferença de fechamento) não contribuem código
    nenhum; vazio, sem consulta, quando não há pendência baseada em conta.
    """
    codigos = set()
    for itens in emissao["listas_pendentes"].values():
        codigos.update(item["conta"] for item in itens if "conta" in item)
    if not codigos:
        return {}
    return dict(
        Conta.objects.filter(empresa=empresa, codigo__in=codigos).values_list("codigo", "id")
    )


def _listas_de_aviso_da_dlpa_para_contexto(avisos):
    """Avisos da DLPA (nunca vetam) no mesmo formato das pendências — a
    tela mostra os DOIS desfechos (emitida com aviso, ou recusada por
    outro motivo com o aviso também presente), como Balanço e DRE fazem
    (DE-070). Sem `acao`: aviso não se resolve, se CONFERE.
    """
    listas = []
    for nome, itens in avisos.items():
        if nome == "resultado_nao_transferido":
            linhas = [
                {
                    "conta": None,
                    "nome": None,
                    "detalhe": (
                        "Ainda há resultado sem zerar: "
                        f"{_valor_ptbr(abs(item['valor']))}. A DLPA mostra o movimento "
                        "gravado — feito o zeramento da competência, o lucro do exercício "
                        "entra na linha “Lucro (prejuízo) líquido do exercício”."
                    ),
                }
                for item in itens
            ]
        else:
            # Lista de aviso nova sem cadastro nunca quebra a tela (mesmo
            # `.get` falho das pendências) — só denuncia o nome cru.
            linhas = [{"conta": None, "nome": None, "detalhe": str(item)} for item in itens]
        listas.append(
            {
                "titulo": _TITULOS_DOS_AVISOS_DA_DLPA.get(nome, nome),
                "tipo_linha": "detalhe",
                "linhas": linhas,
            }
        )
    return listas


def _lancamentos_da_dlpa_por_id(ids, empresa):
    """Os lançamentos que originaram as linhas da DLPA, indexados por id.

    **UMA consulta para todas as linhas**, nunca uma por linha: a
    rastreabilidade multiplica por N (achado 5 da auditoria de 29/09/2026)
    e consulta-por-linha é o caminho que faz uma tela ficar lenta sem o
    contador perceber. Sem lançamentos, mapa vazio e nenhuma consulta —
    uma DLPA sem movimento nenhum é caso comum.

    A descrição é data + histórico, o que basta para o contador
    localizar o lançamento no Diário/Razão; nada de conteúdo sensível
    entra no documento além do que já está nas linhas.

    DL-058/B2 — defesa em profundidade: a consulta filtra TAMBÉM pela
    `empresa` da requisição. Os ids vêm da apuração, que já é por empresa;
    mas esta função recebe uma lista de ids crua, e um id que escapasse (de
    outra empresa ou de outro escritório) traria data e histórico alheios
    para o documento impresso. Id de outra empresa é simplesmente omitido.
    """
    if not ids:
        return {}
    return {
        lancamento.id: {
            "data": lancamento.data,
            "historico": lancamento.historico,
            "descricao": f"{date_format(lancamento.data, 'd/m/Y')} — {lancamento.historico}",
        }
        for lancamento in LancamentoContabil.objects.filter(empresa=empresa, id__in=ids).order_by(
            "data", "id"
        )
    }


def _montar_linhas_da_dlpa(dlpa_apurada, empresa):
    """Linhas IMPRESSAS da DLPA, a partir da lista que `apurar_dlpa` já
    ordenou pelo art. 186 — a ordem e a estrutura vêm do SERVIÇO (é lá que
    a lei fixa os incisos); aqui só se formata valor em pt-BR (`_valor_dre`:
    negativo entre parênteses, RC-90 — a mesma regra de todas as células
    assinadas deste produto) e se marca `eh_saldo` para o template
    destacar as DUAS linhas de saldo.

    **`lancamentos` é repassado** (achado 5 da auditoria de 29/09/2026): o
    serviço já devolvia, por linha, os lançamentos que a geraram — e a
    view jogava fora. O art. 186, §1º pede que os ajustes de exercícios
    anteriores sejam *"identificados e discriminados"*; sem isto, a
    rastreabilidade morria entre a apuração e o documento entregue, e o
    contador não conseguia conferir a linha contra o Razão pela própria
    tela. Os ids vão para o contexto; a identificação legível (data,
    histórico) é montada aqui, com UMA consulta, e nunca por linha.
    """
    ids_por_linha = {
        linha["chave"]: linha.get("lancamentos", []) for linha in dlpa_apurada["linhas"]
    }
    todos_os_ids = {id_lancamento for ids in ids_por_linha.values() for id_lancamento in ids}
    lancamentos_por_id = _lancamentos_da_dlpa_por_id(todos_os_ids, empresa)
    return [
        {
            "chave": linha["chave"],
            "titulo": linha["titulo"],
            "valor": _valor_dre(linha["valor"]),
            "eh_saldo": linha["chave"] in ("saldo_inicial", "saldo_final"),
            # Descrição legível de cada origem da linha, na ordem em que a
            # apuração as viu. Lista vazia nas linhas de saldo e nas
            # rubricas sem movimento — o template não imprime sufixo.
            "origens": [
                lancamentos_por_id.get(id_lancamento, {}).get("descricao", "")
                for id_lancamento in ids_por_linha.get(linha["chave"], [])
            ],
        }
        for linha in dlpa_apurada["linhas"]
    ]


@login_required
@require_safe
def dlpa(request, empresa_id):
    """Demonstração dos Lucros ou Prejuízos Acumulados (DL-048/CTB-13) —
    tela no molde de `dre`: MESMA autorização de leitura (`_pode_ler`),
    mesma recusa de livro-caixa, mesmo veto do servidor com pendências
    nomeadas e link de correção, mesmo bloco de identificação item 51 em
    cada página impressa.

    Período: EXERCÍCIO (ano civil, HI-28) até a competência pedida — a
    navegação "‹ anterior / seguinte ›" desloca o MÊS de referência, mesma
    gramática da DRE (nunca uma segunda). O bloco de identificação cobra
    01/01(ano) → data fim, que é o período que a demonstração cobre.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    # O link "classificar esta conta" do veto só aparece para quem PODE
    # ESCRITURAR (mesmo achado R8 da reconferência da DL-045) — presente em
    # TODOS os `render()` desta view.
    contexto = {"empresa": empresa, "pode_escriturar": _pode_escriturar(request)}

    ano, mes, erro_competencia = _competencia_dre_do_formulario(request)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return render(request, "contabilidade/dlpa.html", contexto, status=400)

    ano_anterior, mes_anterior = _competencia_adjacente(ano, mes, -1)
    ano_seguinte, mes_seguinte = _competencia_adjacente(ano, mes, 1)
    contexto.update(
        {
            "ano": ano,
            "mes": mes,
            "data_referencia": date(ano, mes, 1),
            # Link só quando a competência adjacente é VÁLIDA (mesmo R10 da
            # reconferência da DRE): perto da borda da faixa some, em vez
            # de levar a um 400.
            "ano_anterior": ano_anterior
            if _ano_mes_de_competencia_valido(ano_anterior, mes_anterior)
            else None,
            "mes_anterior": mes_anterior,
            "ano_seguinte": ano_seguinte
            if _ano_mes_de_competencia_valido(ano_seguinte, mes_seguinte)
            else None,
            "mes_seguinte": mes_seguinte,
        }
    )

    # Estado VAZIO (mesmo critério do Balancete/Balanço/DRE): empresa sem
    # NENHUMA conta — nada para classificar, nada para recusar ainda.
    empresa_tem_plano_de_contas = Conta.objects.filter(empresa=empresa).exists()
    contexto["empresa_tem_plano_de_contas"] = empresa_tem_plano_de_contas
    if not empresa_tem_plano_de_contas:
        return render(request, "contabilidade/dlpa.html", contexto)

    try:
        dlpa_apurada = apurar_dlpa(empresa=empresa, ano=ano, mes=mes)
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(request, "contabilidade/dlpa.html", contexto, status=409)

    emissao = avaliar_emissao_da_dlpa(dlpa_apurada)

    rotulo_inscricao, inscricao_formatada = rotulo_e_inscricao_da_empresa(empresa)
    contexto.update(
        {
            "identificacao": identificacao_da_demonstracao(),
            "rotulo_inscricao": rotulo_inscricao,
            "inscricao_formatada": inscricao_formatada,
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
            # NBC TG 26 item 51(c) — "o período coberto": a DLPA cobre o
            # EXERCÍCIO até a competência, então o bloco de identificação
            # precisa das duas pontas, não só do mês pedido.
            "data_inicio_exercicio": dlpa_apurada["data_inicio_exercicio"],
            "data_fim": dlpa_apurada["data_fim"],
        }
    )

    # Avisos aparecem nos DOIS desfechos (fora do if/else do veto), como
    # Balanço e DRE (DE-070) — conferência de bancada, nunca documento.
    contexto["listas_apenas_aviso"] = _listas_de_aviso_da_dlpa_para_contexto(emissao["avisos"])

    if not emissao["pode_emitir"]:
        # Critério da etapa: havendo QUALQUER pendência, a tela NÃO monta
        # a demonstração — só o que falta, nomeado, com link de correção.
        # 200, não erro de protocolo: a tela respondeu "pode emitir? → não".
        contas_id_por_codigo = _contas_id_por_codigo_das_pendencias_dlpa(empresa, emissao)
        contexto.update(
            {
                "pode_emitir": False,
                "listas_pendentes": [
                    _lista_de_pendencia_dlpa_para_contexto(nome, itens, contas_id_por_codigo)
                    for nome, itens in emissao["listas_pendentes"].items()
                ],
            }
        )
        return render(request, "contabilidade/dlpa.html", contexto)

    contexto.update({"pode_emitir": True, "linhas": _montar_linhas_da_dlpa(dlpa_apurada, empresa)})
    return render(request, "contabilidade/dlpa.html", contexto)


# ---------------------------------------------------------------------------
# DL-061 — DMPL (Demonstração das Mutações do Patrimônio Líquido): tela irmã
# da DLPA (`dlpa`, acima). Mesmo esqueleto — autorização de leitura, recusa
# de livro-caixa, veto do SERVIDOR com pendências nomeadas e link de correção
# só para quem escritura, bloco de identificação repetido em cada página
# impressa (classe "demonstração", NBC TG 26 (R5) item 51 / NBC TG 51 item
# 27) — e uma diferença de forma: a DLPA tem UMA coluna de valor; a DMPL tem
# uma por componente do patrimônio líquido (item 111A / 106B), agrupadas.
# ---------------------------------------------------------------------------

# Acima deste número de colunas de componente (fora a de Total), a DMPL
# impressa sai em PAISAGEM (`body.pagina-dmpl-impressao`, base.css). Com até
# quatro, as seis colunas somadas (histórico + componentes + Total) cabem em
# A4 retrato com a tipografia de 11 px do piso de legibilidade; acima disso a
# tabela passaria da folha e o navegador CORTARIA o que sobrasse (o mesmo
# defeito medido no demonstrativo anual do carnê-leão). Número escolhido para
# a folha, não regra contábil — por isso mora na tela, não no serviço.
_COLUNAS_DA_DMPL_QUE_CABEM_EM_RETRATO = 4

# Quantos lançamentos de origem uma linha de pendência lista por extenso; o
# resto vira "e mais N" (a lista completa está no Diário). Evita um veto de
# centenas de linhas que esconda a ação que resolve.
_LANCAMENTOS_LISTADOS_POR_PENDENCIA_DA_DMPL = 5

# DL-063 (BL-625): a ação da divergência de fechamento QUANDO a apuração já
# nomeou a causa — conta de patrimônio líquido com saldo e sem coluna. Fica
# aqui, e não dentro da função, para que o teste possa citá-la em vez de
# reescrever o texto (duas cópias divergem, AGENTS.md §8).
_ACAO_DA_DIVERGENCIA_COM_CONTA_SEM_COLUNA = (
    "A diferença vem de conta do patrimônio líquido que está com saldo e SEM coluna da DMPL "
    "— ela entra no Balanço e não aparece em coluna nenhuma, e é isso que a faz não bater. "
    "Dê a coluna às contas listadas acima, as que têm link ao lado; as demais seguem a "
    "orientação própria indicada em cada uma. Depois disso, confira de novo: se a diferença "
    "continuar, aí sim o problema é a classificação de alguma conta com coluna."
)

ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA = {
    "nenhuma_coluna_classificada": (
        "Classifique, no plano de contas, as contas do patrimônio líquido que a DMPL deve "
        "mostrar (botão “Coluna da DMPL” de cada conta de patrimônio líquido)."
    ),
    "contas_do_patrimonio_liquido_sem_coluna": (
        "Dê uma coluna da DMPL a cada conta listada (link ao lado): o patrimônio líquido do "
        "Balanço inclui essas contas e a demonstração, sem coluna, não as mostraria."
    ),
    "contrapartidas_sem_classificacao": (
        "Classifique a conta listada (link ao lado) — ou, quando o evento for de fato a "
        "exceção prevista pela RC-151, marque o lançamento na guia “DMPL” dele (o link de "
        "conferência do lançamento abre o detalhe, onde a guia está): a DMPL não adivinha o "
        "evento e nunca reparte valor por presunção."
    ),
    "pares_de_colunas_sem_regra": (
        "A DMPL só atribui evento a pares de colunas conhecidos (lucros acumulados ↔ reservas "
        "de lucros, reservas ou lucros → capital social, capital e reservas → tesouraria, e "
        "lucros acumulados ↔ dividendo adicional proposto). Confira os lançamentos listados; se "
        "o movimento estiver correto e o par não for atendido, marque cada lançamento na guia "
        "“DMPL” dele (o link de conferência abre o detalhe, onde a guia está): o conjunto de "
        "marcações reparte o efeito do lançamento entre as células e libera a emissão."
    ),
    "lancamentos_ambiguos": (
        "A DMPL não rateia um valor entre eventos. O lançamento efetivado não se altera, e o "
        "estorno dele não libera esta emissão: a saída é marcar o lançamento na guia “DMPL” "
        "dele (o link de conferência abre o detalhe, onde a guia está) — o conjunto de "
        "marcações reparte o efeito do lançamento entre as células (linha × coluna) e a "
        "emissão sai com elas."
    ),
    "contas_com_classificacao_dlpa_e_dmpl_divergentes": (
        "Escolha, para cada conta listada, classificações compatíveis na DLPA e na DMPL "
        "(links ao lado): as duas demonstrações precisam concordar com o saldo da conta."
    ),
    "contas_com_classificacao_dmpl_desconhecida": (
        "Reclassifique cada conta listada com uma das opções válidas do campo “Coluna da "
        "DMPL” — o valor gravado não existe mais no cadastro."
    ),
    # DL-062 (BL-604): a causa que este texto nomeava até 04/10/2026 — a
    # conta RETIFICADORA do patrimônio líquido cadastrada FORA do grupo, que
    # o Balanço somava e a DMPL subtraía — **deixou de existir**: o total do
    # Balanço passou a aplicar a natureza natural do tipo na contribuição da
    # raiz, e as duas peças passaram a ler a conta igual. Manter a frase seria
    # mandar o contador procurar um defeito que o produto não tem mais, então
    # o texto passa a dizer o que ainda é verdade: as duas peças leram as
    # mesmas contas de formas diferentes, e a diferença nunca é ajustada para
    # fechar.
    "diferenca_de_fechamento": (
        "O saldo final da coluna não bate com o saldo das contas dela no Balanço da mesma "
        "data — as duas peças leram as mesmas contas de formas diferentes. Confira no plano "
        "de contas se cada conta da coluna está classificada na coluna que o uso que ela teve "
        "no período pede, e depois confira no Razão se alguma delas teve movimento que a "
        "classificação não descreve. A diferença é o sinal de dado inconsistente, e nenhum "
        "saldo é ajustado para fechá-la."
    ),
}

_TITULOS_DOS_AVISOS_DA_DMPL = {
    "resultado_nao_transferido": "Resultado do exercício ainda não zerado",
    "resultado_na_conta_de_passagem": (
        "Resultado do exercício na conta de passagem, ainda não transferido"
    ),
}

# Âncora do bloco de aviso (a faixa "pronta para emissão" aponta para ele).
ANCORA_DO_AVISO_DA_DMPL = "aviso-da-dmpl"

# Quando a conta de PL não aceita coluna e o servidor não trouxe orientação
# (`orientacao` ausente no item), a tela ainda diz que NÃO há ação de coluna a
# fazer — nunca devolve a pessoa a um link que o servidor recusa.
_ORIENTACAO_PADRAO_CONTA_SEM_COLUNA_POSSIVEL = (
    "Esta conta não aceita coluna na DMPL; a emissão desta competência fica "
    "impedida enquanto ela existir no patrimônio líquido."
)


def _links_de_lancamentos_da_pendencia(empresa, ids, lancamentos_por_id):
    """Links de conferência (sempre visíveis a quem lê) para os lançamentos
    de uma pendência — até `_LANCAMENTOS_LISTADOS_POR_PENDENCIA_DA_DMPL`; o
    excedente é devolvido como contagem ("e mais N"). Lançamento ausente do
    mapa (outra empresa, defesa em profundidade DL-058/B2) é omitido.
    """
    visiveis = [i for i in dict.fromkeys(ids) if i in lancamentos_por_id]
    links = [
        {
            "rotulo": f"lançamento de {lancamentos_por_id[id_lancamento]['descricao']}",
            "url": reverse(
                "contabilidade_web:lancamento_detalhe", args=[empresa.id, id_lancamento]
            ),
            "correcao": False,
        }
        for id_lancamento in visiveis[:_LANCAMENTOS_LISTADOS_POR_PENDENCIA_DA_DMPL]
    ]
    return links, len(visiveis) - len(links)


def _listas_de_pendencia_dmpl_para_contexto(emissao, empresa, pode_escriturar):
    """O veto da DMPL pronto para o template: cada lista com título humano,
    a AÇÃO que resolve e, por item, o texto, os links e (diferença de
    fechamento) as contas citadas.

    O formato de cada item é o de `apurar_dmpl["pendencias"]` (services.py).
    Link de CORREÇÃO (classificar a conta) só existe para quem escritura —
    quem só lê vê a pendência e o link de CONFERÊNCIA do lançamento, nunca um
    convite a uma ação que o servidor recusaria; a autorização de verdade é
    do servidor (`conta_classificacao_dmpl`/`_dlpa`).

    UMA consulta para os lançamentos de todas as listas e UMA para os tipos
    das contas citadas — nunca uma por linha.
    """
    listas = emissao["listas_pendentes"]
    ids_de_lancamento = set()
    ids_de_conta = set()
    for itens in listas.values():
        for item in itens:
            ids_de_lancamento.update(item.get("lancamentos", []))
            if item.get("lancamento_id"):
                ids_de_lancamento.add(item["lancamento_id"])
            if item.get("conta_id"):
                ids_de_conta.add(item["conta_id"])
    lancamentos_por_id = _lancamentos_da_dlpa_por_id(ids_de_lancamento, empresa)
    tipo_por_conta = (
        dict(Conta.objects.filter(empresa=empresa, id__in=ids_de_conta).values_list("id", "tipo"))
        if ids_de_conta
        else {}
    )

    def _link_da_coluna(conta_id):
        return {
            "rotulo": "definir a coluna da DMPL",
            "url": reverse(
                "contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, conta_id]
            ),
            "correcao": True,
        }

    def _link_da_linha_da_dlpa(conta_id):
        return {
            "rotulo": "definir a linha da DLPA",
            "url": reverse(
                "contabilidade_web:conta_classificacao_dlpa", args=[empresa.id, conta_id]
            ),
            "correcao": True,
        }

    resultado = []
    # DL-063 (BL-625): a divergência de fechamento tem a MESMA causa nomeada
    # em outra pendência — conta de patrimônio líquido com saldo e SEM
    # coluna preenchida. A dica era um dicionário estático, a mesma frase
    # para todo caso, e mandava o contador conferir a classificação mesmo
    # quando o que faltava era a coluna. Lido do `emissao` que a apuração
    # entregou, e não de um teste adivinhado: a lista abaixo É a causa
    # quando está não vazia.
    contas_de_pl_sem_coluna = listas.get("contas_do_patrimonio_liquido_sem_coluna") or []
    for nome, itens in listas.items():
        linhas = []
        tem_conta_sem_coluna_possivel = False
        tem_conta_com_coluna_possivel = False
        for item in itens:
            links = []
            contas = []
            orientacao = ""
            resto = 0
            if nome == "nenhuma_coluna_classificada":
                texto = item["mensagem"]
            elif nome == "contas_do_patrimonio_liquido_sem_coluna":
                texto = (
                    f"Conta {item['conta']} — {item['nome']}: saldo no início do exercício "
                    f"{_saldo_entre_parenteses(item['saldo_inicial'])}"
                    + (", com movimento no exercício." if item["movimento_no_exercicio"] else ".")
                )
                # N4 (auditoria DL-061, rodada 1): só há link de coluna quando
                # o SERVIDOR diz que a conta PODE receber uma (`classificavel`).
                # Conta classificada como dividendo ou ajuste de exercício
                # anterior na DLPA não admite nenhuma coluna — o servidor
                # recusa qualquer uma —, e o link levaria a uma ação sem saída.
                # Nesse caso a tela mostra a `orientacao` do servidor. Item sem
                # a chave (contrato antigo) mantém o comportamento anterior.
                if item.get("classificavel", True):
                    links.append(_link_da_coluna(item["conta_id"]))
                    tem_conta_com_coluna_possivel = True
                else:
                    orientacao = (
                        item.get("orientacao") or _ORIENTACAO_PADRAO_CONTA_SEM_COLUNA_POSSIVEL
                    )
                    tem_conta_sem_coluna_possivel = True
            elif nome == "contrapartidas_sem_classificacao":
                texto = (
                    f"Conta {item['conta']} — {item['nome']}: {item['mensagem']} "
                    f"(coluna afetada: {item['coluna_titulo']}; "
                    f"{len(set(item['lancamentos']))} lançamento(s))"
                )
                links.append(_link_da_linha_da_dlpa(item["conta_id"]))
                # A coluna só se aplica a conta de patrimônio líquido — o
                # servidor recusaria o link para qualquer outra.
                if tipo_por_conta.get(item["conta_id"]) == TipoConta.PATRIMONIO_LIQUIDO:
                    links.append(_link_da_coluna(item["conta_id"]))
                de_origem, resto = _links_de_lancamentos_da_pendencia(
                    empresa, item["lancamentos"], lancamentos_por_id
                )
                links.extend(de_origem)
            elif nome == "pares_de_colunas_sem_regra":
                texto = (
                    f"Movimento de “{item['origem_titulo']}” para “{item['destino_titulo']}” "
                    f"({len(set(item['lancamentos']))} lançamento(s))"
                )
                links, resto = _links_de_lancamentos_da_pendencia(
                    empresa, item["lancamentos"], lancamentos_por_id
                )
            elif nome == "lancamentos_ambiguos":
                data = item["data"]
                texto = (
                    f"Lançamento de {date_format(data, 'd/m/Y') if data else 'data não encontrada'}"
                    f" (colunas: {', '.join(item['colunas'])}). {item['mensagem']}"
                )
                links, resto = _links_de_lancamentos_da_pendencia(
                    empresa, [item["lancamento_id"]], lancamentos_por_id
                )
            elif nome == "contas_com_classificacao_dlpa_e_dmpl_divergentes":
                texto = f"Conta {item['conta']} — {item['nome']}: {item['mensagem']}"
                links.append(_link_da_coluna(item["conta_id"]))
                links.append(_link_da_linha_da_dlpa(item["conta_id"]))
            elif nome == "contas_com_classificacao_dmpl_desconhecida":
                texto = (
                    f"Conta {item['conta']} — {item['nome']}: a coluna gravada "
                    f"(“{item['classificacao_dmpl']}”) não existe mais no cadastro."
                )
                links.append(_link_da_coluna(item["conta_id"]))
            elif nome == "diferenca_de_fechamento":
                if item["coluna"] == "total":
                    texto = (
                        "Total do patrimônio líquido: soma das colunas na DMPL "
                        f"{_saldo_entre_parenteses(item['saldo_na_dmpl'])}, contas de "
                        "passagem (resultado do exercício) "
                        f"{_saldo_entre_parenteses(item['saldo_contas_de_passagem'])}, "
                        "patrimônio líquido no Balanço "
                        f"{_saldo_entre_parenteses(item['saldo_no_balanco'])} — diferença "
                        f"{_saldo_entre_parenteses(item['diferenca'])}."
                    )
                else:
                    texto = (
                        f"Coluna “{item['titulo']}”: saldo final na DMPL "
                        f"{_saldo_entre_parenteses(item['saldo_na_dmpl'])}, saldo no Balanço "
                        f"{_saldo_entre_parenteses(item['saldo_no_balanco'])} — diferença "
                        f"{_saldo_entre_parenteses(item['diferenca'])}."
                    )
                    contas = [
                        f"Conta {conta['conta']} — {conta['nome']}: saldo no Balanço "
                        f"{_saldo_entre_parenteses(conta['saldo'])}"
                        for conta in item.get("contas", [])
                    ]
            else:
                # Lista nova sem tratamento nunca quebra a tela: sai o dict
                # cru, que denuncia a lacuna (mesmo `.get` falho da DLPA).
                texto = str(item)
            if not pode_escriturar:
                links = [link for link in links if not link["correcao"]]
            linhas.append(
                {
                    "texto": texto,
                    "links": links,
                    "resto": resto,
                    "contas": contas,
                    "orientacao": orientacao,
                }
            )
        acao = ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA.get(
            nome, f"Ação não cadastrada para a pendência '{nome}' — avise o suporte."
        )
        if tem_conta_sem_coluna_possivel:
            # A ação padrão manda "dar uma coluna a cada conta listada": falsa
            # para a conta que não aceita nenhuma (N4). Ela passa a dizer qual
            # conta tem link e que as demais seguem a orientação própria.
            acao = (
                (
                    "Dê uma coluna da DMPL às contas que têm o link ao lado. "
                    if tem_conta_com_coluna_possivel
                    else ""
                )
                + "As contas com orientação própria não aceitam coluna: siga a orientação "
                "indicada em cada uma. O patrimônio líquido do Balanço inclui todas elas e a "
                "demonstração, sem coluna, não as mostraria."
            )
        if nome == "diferenca_de_fechamento" and contas_de_pl_sem_coluna:
            # A causa que a apuração JÁ nomeou na lista vizinha: conta de PL
            # com saldo e sem coluna. A dica genérica ("confira a
            # classificação") mandaria o contador caçar o que está certo;
            # esta manda para a conta que está sem o que preencher, e o
            # link de coluna dela está na lista de cima, com o mesmo
            # `classificavel` que o servidor decidiu.
            acao = _ACAO_DA_DIVERGENCIA_COM_CONTA_SEM_COLUNA
        resultado.append(
            {
                "titulo": _TITULOS_DAS_PENDENCIAS_DA_DMPL.get(nome, nome),
                "linhas": linhas,
                "acao": acao,
            }
        )
    return resultado


def _saldo_total_na_conta_de_passagem(avisos):
    """Soma dos itens do aviso `resultado_na_conta_de_passagem` (N3), ou `None`
    sem aviso. Contrato do servidor: lista de `{"valor": Decimal, "contas":
    [{"conta_id", "conta", "nome", "saldo"}]}`. O valor é o SALDO da(s)
    conta(s) de passagem — o mesmo que a conciliação soma ao total das
    colunas para chegar ao patrimônio líquido do Balanço.
    """
    itens = avisos.get("resultado_na_conta_de_passagem") or []
    if not itens:
        return None
    return sum((item["valor"] for item in itens), Decimal("0"))


def _nota_do_resultado_na_conta_de_passagem(avisos, data_fim):
    """A NOTA que sai NO PAPEL quando há saldo na conta de passagem (decisão
    do arquiteto-senior, reversível, sobre o achado N3 da auditoria DL-061).

    Por que no papel: o total da demonstração fica ABAIXO (ou acima) do
    patrimônio líquido do Balanço pelo valor desse saldo — a conciliação
    fecha porque soma a conta de passagem, mas o leitor do documento só tem
    a tabela na mão, e um total diferente do Balanço sem explicação parece
    erro. Sem o aviso, nada no papel (devolve `None`).
    """
    saldo = _saldo_total_na_conta_de_passagem(avisos)
    if saldo is None:
        return None
    valor = _saldo_entre_parenteses(saldo)
    return {
        "valor": valor,
        "texto": (
            f"Há saldo de R$ {valor} na conta de resultado do exercício, ainda não "
            "transferido para lucros ou prejuízos acumulados"
            + (" (valor entre parênteses é saldo devedor)" if saldo < 0 else "")
            + ". Por isso o total desta demonstração difere do patrimônio líquido do "
            f"Balanço Patrimonial de {date_format(data_fim, 'd/m/Y')} nesse valor."
        ),
    }


def _listas_de_aviso_da_dmpl_para_contexto(avisos, empresa=None):
    """Avisos da DMPL (nunca vetam), no mesmo formato das pendências e
    presentes nos DOIS desfechos da tela (emitida com aviso, ou vetada por
    outro motivo com o aviso também presente) — mesmo critério da DLPA
    (DE-070). Sem `acao`: aviso não se resolve, se CONFERE.

    `resultado_na_conta_de_passagem` (N3) mostra o valor e cada conta de
    passagem com o saldo dela, e aponta onde conferir (Diário e Fechamento).
    """
    listas = []
    for nome, itens in avisos.items():
        if nome == "resultado_nao_transferido":
            linhas = [
                {
                    "detalhe": (
                        "Ainda há resultado sem zerar: "
                        f"{_valor_ptbr(abs(item['valor']))}. A DMPL mostra o movimento "
                        "gravado — feito o zeramento da competência, o resultado do "
                        "exercício entra na linha “Resultado do exercício”, na coluna de "
                        "lucros ou prejuízos acumulados."
                    )
                }
                for item in itens
            ]
        elif nome == "resultado_na_conta_de_passagem":
            linhas = [
                {
                    "detalhe": (
                        f"Há saldo de R$ {_saldo_entre_parenteses(item['valor'])} na conta de "
                        "resultado do exercício, ainda não transferido para lucros ou "
                        "prejuízos acumulados. A DMPL não tem coluna para essa conta: o total "
                        "dela difere do patrimônio líquido do Balanço exatamente por esse "
                        "valor (a conferência abaixo mostra a conta de passagem). Confira no "
                        "Diário se a transferência foi lançada ou foi estornada, e no "
                        "Fechamento a situação do zeramento."
                    ),
                    "contas": [
                        f"Conta {conta['conta']} — {conta['nome']}: saldo "
                        f"{_saldo_entre_parenteses(conta['saldo'])}"
                        for conta in item.get("contas", [])
                    ],
                    "links": (
                        [
                            {
                                "rotulo": "abrir o Diário",
                                "url": reverse("contabilidade_web:diario", args=[empresa.id]),
                            },
                            {
                                "rotulo": "abrir o Fechamento",
                                "url": reverse("contabilidade_web:fechamento", args=[empresa.id]),
                            },
                        ]
                        if empresa is not None
                        else []
                    ),
                }
                for item in itens
            ]
        else:
            linhas = [{"detalhe": str(item)} for item in itens]
        listas.append({"titulo": _TITULOS_DOS_AVISOS_DA_DMPL.get(nome, nome), "linhas": linhas})
    return listas


def _montar_tabela_da_dmpl(dmpl, empresa):
    """A tabela IMPRESSA da DMPL (linhas × colunas), a partir do que
    `apurar_dmpl` já ordenou — a ordem das linhas (E4) e a das colunas
    (item 111A) vêm do SERVIÇO; aqui só se agrupa o cabeçalho, se formata
    (`_valor_dre`: pt-BR, negativo entre parênteses, RC-90) e se liga cada
    célula com valor aos lançamentos que a formaram.

    - **Cabeçalho em dois níveis.** Cada coluna traz o grupo do item 111A.
      Um grupo com UMA coluna de título igual ao dele ("Capital social")
      vira uma célula só, de duas linhas de altura (`fundido`); com várias
      ("Reservas de lucros"), vira um cabeçalho de grupo sobre as colunas.
    - **Célula sem lançamento de origem** (linha de evento) sai "—", não
      "0,00": o zero com que a apuração preenche as colunas sem movimento
      não é um valor apurado. As linhas de SALDO sempre trazem o valor (um
      saldo zero é informação). Uma célula com lançamentos cujo efeito
      líquido deu zero mostra "0,00" e a origem, para o contador ver de onde
      veio.
    - **Rastreabilidade por célula**: cada célula com origem recebe uma
      âncora para a lista de lançamentos de baixo (`origens`). A lista é
      conferência de BANCADA — não sai no papel.
    UMA consulta para todos os lançamentos da tabela.
    """
    colunas = dmpl["colunas"]
    grupos = []
    for coluna in colunas:
        if grupos and grupos[-1]["chave"] == coluna["grupo"]:
            grupos[-1]["colunas"].append(coluna)
        else:
            grupos.append(
                {"chave": coluna["grupo"], "titulo": coluna["grupo_titulo"], "colunas": [coluna]}
            )
    colunas_do_segundo_nivel = []
    for grupo in grupos:
        grupo["fundido"] = (
            len(grupo["colunas"]) == 1 and grupo["colunas"][0]["titulo"] == grupo["titulo"]
        )
        if not grupo["fundido"]:
            colunas_do_segundo_nivel.extend(grupo["colunas"])

    todos_os_ids = {
        id_lancamento
        for linha in dmpl["linhas"]
        for ids in linha["lancamentos"].values()
        for id_lancamento in ids
    }
    lancamentos_por_id = _lancamentos_da_dlpa_por_id(todos_os_ids, empresa)

    linhas = []
    origens = []
    for linha in dmpl["linhas"]:
        eh_saldo = linha["chave"] in ("saldo_inicial", "saldo_final")
        celulas = []
        for coluna in colunas:
            ids = [
                i for i in linha["lancamentos"].get(coluna["chave"], []) if i in lancamentos_por_id
            ]
            if not (eh_saldo or ids):
                celulas.append(None)
                continue
            valor = _valor_dre(linha["valores"][coluna["chave"]])
            ancora = f"origem-{linha['chave']}-{coluna['chave']}" if ids else None
            celulas.append(
                {
                    "valor": valor,
                    "ancora": ancora,
                    "coluna": coluna["titulo"],
                    "linha": linha["titulo"],
                }
            )
            if ids:
                origens.append(
                    {
                        "ancora": ancora,
                        "linha": linha["titulo"],
                        "coluna": coluna["titulo"],
                        "valor": valor,
                        "lancamentos": [
                            {
                                "descricao": lancamentos_por_id[i]["descricao"],
                                "url": reverse(
                                    "contabilidade_web:lancamento_detalhe", args=[empresa.id, i]
                                ),
                            }
                            for i in ids
                        ],
                    }
                )
        linhas.append(
            {
                "chave": linha["chave"],
                "titulo": linha["titulo"],
                "eh_saldo": eh_saldo,
                "celulas": celulas,
                "total": _valor_dre(linha["total"]),
            }
        )

    por_coluna = dmpl["conciliacao"]["por_coluna"]
    total = dmpl["conciliacao"]["total"]
    return {
        "colunas": colunas,
        "grupos": grupos,
        "colunas_do_segundo_nivel": colunas_do_segundo_nivel,
        # Histórico + componentes + Total: a largura do bloco de identificação.
        "quantidade_de_colunas_da_tabela": len(colunas) + 2,
        "linhas": linhas,
        "tem_movimento": len(dmpl["linhas"]) > 2,
        "origens": origens,
        "conferencia": {
            "por_coluna": [
                {
                    "titulo": coluna["titulo"],
                    "na_dmpl": _valor_dre(por_coluna[coluna["chave"]]["saldo_na_dmpl"]),
                    "no_balanco": _valor_dre(por_coluna[coluna["chave"]]["saldo_no_balanco"]),
                    "diferenca": _valor_dre(por_coluna[coluna["chave"]]["diferenca"]),
                }
                for coluna in colunas
            ],
            "total": {
                "na_dmpl": _valor_dre(total["saldo_na_dmpl"]),
                "de_passagem": _valor_dre(total["saldo_contas_de_passagem"]),
                "no_balanco": _valor_dre(total["saldo_no_balanco"]),
                "diferenca": _valor_dre(total["diferenca"]),
            },
        },
    }


@login_required
@require_safe
def dmpl(request, empresa_id):
    """Demonstração das Mutações do Patrimônio Líquido (DL-061/CTB-14) —
    tela no molde de `dlpa`: MESMA autorização de leitura (`_pode_ler`),
    mesma recusa de livro-caixa, mesmo veto do servidor com pendências
    nomeadas, mesma competência e navegação por mês, mesmo bloco de
    identificação em cada página impressa.

    Período: EXERCÍCIO (ano civil, HI-28) até a competência pedida. O
    início vem do CONTEXTO da apuração (`data_inicio_exercicio`) — nunca
    "01/01/{ano}" escrito no template. O bloco de identificação cita a norma
    escolhida pelo SERVIDOR (`norma`: R5, TG 51 ou adoção antecipada); a
    tela não compara data nenhuma.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    # O link de correção do veto só aparece para quem PODE ESCRITURAR — vale
    # para TODOS os `render()` desta view.
    pode_escriturar = _pode_escriturar(request)
    contexto = {"empresa": empresa, "pode_escriturar": pode_escriturar}

    ano, mes, erro_competencia = _competencia_dre_do_formulario(request)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return render(request, "contabilidade/dmpl.html", contexto, status=400)

    ano_anterior, mes_anterior = _competencia_adjacente(ano, mes, -1)
    ano_seguinte, mes_seguinte = _competencia_adjacente(ano, mes, 1)
    contexto.update(
        {
            "ano": ano,
            "mes": mes,
            "data_referencia": date(ano, mes, 1),
            # Link só quando a competência adjacente é VÁLIDA: perto da borda
            # da faixa some, em vez de levar a um 400 (mesmo R10 da DRE).
            "ano_anterior": ano_anterior
            if _ano_mes_de_competencia_valido(ano_anterior, mes_anterior)
            else None,
            "mes_anterior": mes_anterior,
            "ano_seguinte": ano_seguinte
            if _ano_mes_de_competencia_valido(ano_seguinte, mes_seguinte)
            else None,
            "mes_seguinte": mes_seguinte,
        }
    )

    # Estado VAZIO: empresa sem NENHUMA conta — nada para classificar ainda.
    empresa_tem_plano_de_contas = Conta.objects.filter(empresa=empresa).exists()
    contexto["empresa_tem_plano_de_contas"] = empresa_tem_plano_de_contas
    if not empresa_tem_plano_de_contas:
        return render(request, "contabilidade/dmpl.html", contexto)

    try:
        dmpl_apurada = apurar_dmpl(empresa=empresa, ano=ano, mes=mes)
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(request, "contabilidade/dmpl.html", contexto, status=409)

    emissao = avaliar_emissao_da_dmpl(dmpl_apurada)

    rotulo_inscricao, inscricao_formatada = rotulo_e_inscricao_da_empresa(empresa)
    contexto.update(
        {
            "identificacao": identificacao_da_demonstracao(),
            "rotulo_inscricao": rotulo_inscricao,
            "inscricao_formatada": inscricao_formatada,
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
            # O período coberto tem DUAS pontas e a inicial vem da apuração.
            "data_inicio_exercicio": dmpl_apurada["data_inicio_exercicio"],
            "data_fim": dmpl_apurada["data_fim"],
            "norma": dmpl_apurada["norma"],
        }
    )

    # Avisos nos DOIS desfechos (fora do if/else do veto), só na tela.
    contexto["listas_apenas_aviso"] = _listas_de_aviso_da_dmpl_para_contexto(
        emissao["avisos"], empresa
    )
    contexto["ancora_do_aviso"] = ANCORA_DO_AVISO_DA_DMPL
    # N3: saldo na conta de passagem tem, além do aviso de tela, uma NOTA no papel
    # (só no desfecho emitido — vetada, a demonstração nem é montada).
    contexto["tem_aviso_de_passagem"] = bool(
        emissao["avisos"].get("resultado_na_conta_de_passagem")
    )

    if not emissao["pode_emitir"]:
        # Havendo QUALQUER pendência a tela NÃO monta a demonstração — só o
        # que falta, nomeado, com link de correção. 200, não erro de
        # protocolo: a tela respondeu "pode emitir? → não".
        contexto.update(
            {
                "pode_emitir": False,
                "listas_pendentes": _listas_de_pendencia_dmpl_para_contexto(
                    emissao, empresa, pode_escriturar
                ),
            }
        )
        return render(request, "contabilidade/dmpl.html", contexto)

    tabela = _montar_tabela_da_dmpl(dmpl_apurada, empresa)
    contexto.update(
        {
            "pode_emitir": True,
            "tabela": tabela,
            "nota_do_resultado_na_conta_de_passagem": _nota_do_resultado_na_conta_de_passagem(
                emissao["avisos"], dmpl_apurada["data_fim"]
            ),
            "imprime_em_paisagem": len(tabela["colunas"]) > _COLUNAS_DA_DMPL_QUE_CABEM_EM_RETRATO,
        }
    )
    return render(request, "contabilidade/dmpl.html", contexto)


# ---------------------------------------------------------------------------
# DFC (DL-066/CTB-15)
# ---------------------------------------------------------------------------


# A AÇÃO que resolve cada pendência da DFC — o TÍTULO continua morando no
# serviço (`_TITULOS_DAS_PENDENCIAS_DA_DFC`), fonte única; esta é a tela
# dizendo o que fazer, no mesmo molde de `ACAO_QUE_RESOLVE_A_PENDENCIA_
# DA_DMPL_POR_LISTA`. Lista nova no serviço sem ação cadastrada aqui aparece
# na tela como "ação não cadastrada" — nunca em silêncio.
ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DFC_POR_LISTA = {
    "conta_com_dois_papeis": (
        "Cada conta tem UM papel na DFC: ou é caixa e equivalentes (o lado do caixa "
        "dos lançamentos), ou tem atividade (a contrapartida que dá o sentido do "
        "fluxo) — nunca os dois. Para cada conta listada, desmarque o papel que ela "
        "não exerce (link ao lado)."
    ),
    "lancamentos_sem_atividade": (
        "Classifique cada contrapartida listada com a atividade do fluxo em que o "
        "movimento dela entra (operacional, investimento ou financiamento) — o link "
        "de conferência abre o lançamento, onde as contas aparecem."
    ),
    "classificacao_fora_do_enum": (
        "A atividade gravada nessas contas não existe mais no cadastro. "
        "Reclassifique cada uma delas com uma das três atividades válidas no campo "
        "“Atividade do fluxo de caixa”."
    ),
    "lancamento_com_atividades_conflitantes": (
        "A DFC não rateia um lançamento entre atividades, e o lançamento efetivado "
        "não se altera. A saída prevista é a marcação manual do lançamento (etapa "
        "seguinte desta demanda), que reparte o efeito dele entre as atividades — "
        "até lá, a emissão fica impedida."
    ),
    "diferenca_de_caixa": (
        "A soma das três atividades precisa ser a variação do saldo de caixa e "
        "equivalentes (conciliação do item 45 do CPC 03). Confira no plano de "
        "contas quais contas são caixa e equivalentes e qual atividade cada "
        "contrapartida tem; nenhum saldo é ajustado para fechar a diferença."
    ),
    "indireto_nao_fecha": (
        "A conciliação do método indireto precisa reproduzir o fluxo operacional "
        "apurado pelos lançamentos (item 20A do CPC 03). Confira as marcações de "
        "item de resultado sem caixa e de atividade das contas: cada fato contábil "
        "é ajustado UMA vez. Nenhum ajuste é calibrado para fechar a diferença."
    ),
}


def _listas_de_pendencia_dfc_para_contexto(emissao, empresa, pode_escriturar):
    """O veto da DFC pronto para o template: cada lista com o título do
    SERVIÇO e, por item, o texto já humano e os links — mesmo formato das
    pendências da DMPL (`_listas_de_pendencia_dmpl_para_contexto`, que é o
    molde desta tela).

    Link de CORREÇÃO (classificar a conta) só existe para quem escritura —
    quem só lê vê a pendência e o link de CONFERÊNCIA do lançamento (leitura),
    nunca um convite a uma ação que o servidor recusaria. O id da conta vem
    de UMA consulta pelo código citado no item (`conta_com_dois_papeis`); o
    restante das listas cita conta como texto, e o caminho de correção delas
    é o Plano de contas (link fechando o bloco, no template).
    """
    listas = emissao["listas_pendentes"]
    ids_de_lancamento = {
        item["lancamento_id"]
        for itens in listas.values()
        for item in itens
        if item.get("lancamento_id")
    }
    lancamentos_por_id = _lancamentos_da_dlpa_por_id(ids_de_lancamento, empresa)
    codigos = {item["conta"] for item in listas.get("conta_com_dois_papeis", [])}
    id_por_codigo = (
        dict(Conta.objects.filter(empresa=empresa, codigo__in=codigos).values_list("codigo", "id"))
        if codigos
        else {}
    )

    resultado = []
    for nome, itens in listas.items():
        linhas = []
        for item in itens:
            links = []
            if nome == "conta_com_dois_papeis":
                texto = (
                    f"Conta {item['conta']} — {item['nome']}: marcada como caixa e "
                    "equivalentes e com atividade gravada "
                    f"(“{item['atividade']}”) — papel duplo."
                )
                conta_id = id_por_codigo.get(item["conta"])
                if conta_id:
                    links.append(
                        {
                            "rotulo": "classificar esta conta",
                            "url": reverse(
                                "contabilidade_web:conta_classificacao_dfc",
                                args=[empresa.id, conta_id],
                            ),
                            "correcao": True,
                        }
                    )
            elif nome == "lancamentos_sem_atividade":
                texto = (
                    f"Lançamento de {_data_ptbr(item['data'])} — {item['historico']}: "
                    f"contrapartida sem atividade — {item['contas']}."
                )
            elif nome == "classificacao_fora_do_enum":
                texto = (
                    f"Lançamento de {_data_ptbr(item['data'])} — {item['historico']}: "
                    f"{item['contas']}."
                )
            elif nome == "lancamento_com_atividades_conflitantes":
                texto = (
                    f"Lançamento de {_data_ptbr(item['data'])} — {item['historico']}: "
                    f"o fluxo cai em mais de uma atividade ({', '.join(item['atividades'])})."
                )
            elif nome == "diferenca_de_caixa":
                texto = (
                    "Variação apurada pelas três atividades "
                    f"{_saldo_entre_parenteses(item['variacao_pelas_atividades'])}, "
                    "variação dos saldos das contas de caixa e equivalentes "
                    f"{_saldo_entre_parenteses(item['variacao_dos_saldos'])} — diferença "
                    f"{_saldo_entre_parenteses(item['diferenca'])}."
                )
            elif nome == "indireto_nao_fecha":
                texto = (
                    f"Lucro líquido {_saldo_entre_parenteses(item['lucro_liquido'])} mais "
                    f"ajustes {_saldo_entre_parenteses(item['total_dos_ajustes'])} = "
                    f"{_saldo_entre_parenteses(item['fluxo_operacional'])} no método indireto, "
                    "contra "
                    f"{_saldo_entre_parenteses(item['fluxo_operacional_pelo_direto'])} apurado "
                    f"pelos lançamentos — diferença {_saldo_entre_parenteses(item['diferenca'])}."
                )
            else:
                # Lista nova sem tratamento nunca quebra a tela: sai o dict
                # cru, que denuncia a lacuna (mesmo molde da DMPL).
                texto = str(item)
            if item.get("lancamento_id") in lancamentos_por_id:
                links.append(
                    {
                        "rotulo": (
                            "lançamento de "
                            f"{lancamentos_por_id[item['lancamento_id']]['descricao']}"
                        ),
                        "url": reverse(
                            "contabilidade_web:lancamento_detalhe",
                            args=[empresa.id, item["lancamento_id"]],
                        ),
                        "correcao": False,
                    }
                )
            if not pode_escriturar:
                links = [link for link in links if not link["correcao"]]
            linhas.append({"texto": texto, "links": links})
        resultado.append(
            {
                "titulo": _TITULOS_DAS_PENDENCIAS_DA_DFC.get(nome, nome),
                "linhas": linhas,
                "acao": ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DFC_POR_LISTA.get(
                    nome, f"Ação não cadastrada para a pendência '{nome}' — avise o suporte."
                ),
            }
        )
    return resultado


def _data_ptbr(valor):
    """Data em pt-BR para o texto das pendências — `None` sai "data não
    encontrada", nunca exceção (o dado vem da apuração e pode ter sido
    montado fora do caminho validado)."""
    return date_format(valor, "d/m/Y") if valor else "data não encontrada"


def _montar_dfc_para_contexto(dfc):
    """A DFC pronta para o template — só FORMATAÇÃO, nenhum cálculo: o número
    vem inteiro de `apurar_dfc` (services.py) e aqui vira texto pt-BR pelo
    MESMO `_valor_dre` de todas as demonstrações (negativo entre parênteses,
    RC-90). Dinheiro nunca viaja para o template como `Decimal` cru.

    Duas seções, no molde do documento:

    - **direto** (resumido): as três atividades, a variação, o caixa inicial
      e final e a conciliação do item 45 — as nove linhas, na ordem em que o
      CPC 03 (R2) item 43 apresenta o fluxo e o item 45 pede a conciliação;
    - **indireto** (item 20/20A): lucro líquido, a tabela dos ajustes (cada
      um com item, conta, nome, descrição, sinal e valor), o total, o fluxo
      operacional e a conferência contra o direto. `None` quando a apuração
      não o devolveu (nenhuma conta de caixa marcada) — a tela NOMEIA a
      ausência em vez de inventar o número.

    Zero sai "0,00", não "—": aqui cada valor é APURADO (as irmãs DRE/DLPA
    fazem o mesmo); o "—" das células da DMPL marca célula SEM lançamento de
    origem, conceito que as linhas da DFC não têm.
    """
    direto = [
        {
            "titulo": "Fluxos de caixa das atividades operacionais",
            "valor": _valor_dre(dfc["atividades"][ClassificacaoFluxoCaixa.OPERACIONAL]),
        },
        {
            "titulo": "Fluxos de caixa das atividades de investimento",
            "valor": _valor_dre(dfc["atividades"][ClassificacaoFluxoCaixa.INVESTIMENTO]),
        },
        {
            "titulo": "Fluxos de caixa das atividades de financiamento",
            "valor": _valor_dre(dfc["atividades"][ClassificacaoFluxoCaixa.FINANCIAMENTO]),
        },
        {
            "titulo": "Variação do caixa e equivalentes de caixa no período",
            "valor": _valor_dre(dfc["caixa"]["variacao"]),
            "total": True,
        },
        {
            "titulo": "Caixa e equivalentes de caixa no início do período",
            "valor": _valor_dre(dfc["caixa"]["inicial"]),
        },
        {
            "titulo": "Caixa e equivalentes de caixa no fim do período",
            "valor": _valor_dre(dfc["caixa"]["final"]),
            "total": True,
        },
        {
            "titulo": ("Conciliação do item 45 — variação apurada pelas três atividades"),
            "valor": _valor_dre(dfc["conciliacao"]["variacao_pelas_atividades"]),
        },
        {
            "titulo": (
                "Conciliação do item 45 — variação dos saldos das contas de caixa e equivalentes"
            ),
            "valor": _valor_dre(dfc["conciliacao"]["variacao_dos_saldos"]),
        },
        {
            "titulo": "Conciliação do item 45 — diferença entre as duas variações",
            "valor": _valor_dre(dfc["conciliacao"]["diferenca"]),
        },
    ]

    indireto = dfc["operacional_indireto"]
    if indireto is None:
        return {"direto": direto, "indireto": None}

    linhas = [
        {"resumo": "Lucro líquido do período", "valor": _valor_dre(indireto["lucro_liquido"])}
    ]
    linhas.extend(
        {
            "item": ajuste["item"],
            "conta": ajuste["conta"],
            "nome": ajuste["nome"],
            "descricao": ajuste["descricao"],
            "sinal": ajuste["sinal"],
            # O serviço devolve `valor` SEM sinal e `sinal` à parte (e `efeito`
            # assinado): a tabela mostra a magnitude e o sinal, cada um na sua
            # coluna — é o contrato do item 20, e o teste de tela mede as duas.
            "valor": _valor_dre(ajuste["valor"]),
        }
        for ajuste in indireto["ajustes"]
    )
    linhas.append(
        {
            "resumo": "Total dos ajustes do método indireto",
            "valor": _valor_dre(indireto["total_dos_ajustes"]),
            "total": True,
        }
    )
    linhas.append(
        {
            "resumo": "Fluxo de caixa das atividades operacionais — método indireto",
            "valor": _valor_dre(indireto["fluxo_operacional"]),
            "total": True,
        }
    )
    linhas.append(
        {
            "resumo": "Fluxo de caixa das atividades operacionais — método direto",
            "valor": _valor_dre(indireto["fluxo_operacional_pelo_direto"]),
        }
    )
    linhas.append(
        {"resumo": "Diferença entre os dois métodos", "valor": _valor_dre(indireto["diferenca"])}
    )
    linhas.append(
        {"resumo": "Os dois métodos conferem", "texto": "Sim" if indireto["confere"] else "Não"}
    )
    return {"direto": direto, "indireto": {"linhas": linhas}}


@login_required
@require_safe
def dfc(request, empresa_id):
    """Demonstração dos Fluxos de Caixa (DL-066/CTB-15) — tela no molde de
    `dmpl`: MESMA autorização de leitura (`_pode_ler`), mesma recusa de
    livro-caixa, mesmo veto do servidor com pendências nomeadas, mesma
    competência e navegação por mês, mesmo bloco de identificação em cada
    página impressa.

    Período: EXERCÍCIO (ano civil, HI-28) até a competência pedida —
    `?ano=&mes=` por querystring (mesma gramática da DRE/DLPA/DMPL), nunca no
    caminho da URL. O início vem do CONTEXTO da apuração (`periodo.data_
    inicio`), nunca de "01/01/{ano}" escrito no template.

    **O veredito é do servidor** (`avaliar_emissao_da_dfc`) e a tela só
    OBEDECE: com QUALQUER pendência, a página de recusa não monta nada da
    demonstração — sem tabela, sem totais, sem carimbo e sem o bloco de
    identificação impresso (regra B.2/B.3 do projeto; mesmo molde do veto da
    DMPL).

    **Item 52A do CPC 03 (R2):** a DFC não apresenta campo de valor por ação
    — o produto não registra quantidade de ações, e na DFC a norma veda esse
    dado. Nenhum desfecho desta tela o monta (o teste de tela varre o HTML
    inteiro atrás do trecho).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    # O link de correção do veto só aparece para quem PODE ESCRITURAR — vale
    # para TODOS os `render()` desta view (mesmo molde da DMPL).
    pode_escriturar = _pode_escriturar(request)
    contexto = {"empresa": empresa, "pode_escriturar": pode_escriturar}

    ano, mes, erro_competencia = _competencia_dre_do_formulario(request)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return render(request, "contabilidade/dfc.html", contexto, status=400)

    ano_anterior, mes_anterior = _competencia_adjacente(ano, mes, -1)
    ano_seguinte, mes_seguinte = _competencia_adjacente(ano, mes, 1)
    contexto.update(
        {
            "ano": ano,
            "mes": mes,
            "data_referencia": date(ano, mes, 1),
            # Link só quando a competência adjacente é VÁLIDA: perto da borda
            # da faixa some, em vez de levar a um 400 (mesmo R10 da DRE).
            "ano_anterior": ano_anterior
            if _ano_mes_de_competencia_valido(ano_anterior, mes_anterior)
            else None,
            "mes_anterior": mes_anterior,
            "ano_seguinte": ano_seguinte
            if _ano_mes_de_competencia_valido(ano_seguinte, mes_seguinte)
            else None,
            "mes_seguinte": mes_seguinte,
        }
    )

    # Estado VAZIO: empresa sem NENHUMA conta — nada para classificar ainda.
    empresa_tem_plano_de_contas = Conta.objects.filter(empresa=empresa).exists()
    contexto["empresa_tem_plano_de_contas"] = empresa_tem_plano_de_contas
    if not empresa_tem_plano_de_contas:
        return render(request, "contabilidade/dfc.html", contexto)

    try:
        dfc_apurada = apurar_dfc(empresa=empresa, ano=ano, mes=mes)
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(request, "contabilidade/dfc.html", contexto, status=409)

    emissao = avaliar_emissao_da_dfc(dfc_apurada)

    rotulo_inscricao, inscricao_formatada = rotulo_e_inscricao_da_empresa(empresa)
    contexto.update(
        {
            "identificacao": identificacao_da_demonstracao(),
            "rotulo_inscricao": rotulo_inscricao,
            "inscricao_formatada": inscricao_formatada,
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
            # O período coberto tem DUAS pontas e a inicial vem da apuração.
            "data_inicio": dfc_apurada["periodo"]["data_inicio"],
            "data_fim": dfc_apurada["periodo"]["data_fim"],
        }
    )

    if not emissao["pode_emitir"]:
        # Havendo QUALQUER pendência a tela NÃO monta a demonstração — só o
        # que falta, nomeado, com link de correção. 200, não erro de
        # protocolo: a tela respondeu "pode emitir? → não".
        contexto.update(
            {
                "pode_emitir": False,
                "listas_pendentes": _listas_de_pendencia_dfc_para_contexto(
                    emissao, empresa, pode_escriturar
                ),
            }
        )
        return render(request, "contabilidade/dfc.html", contexto)

    contexto.update({"pode_emitir": True, "dfc": _montar_dfc_para_contexto(dfc_apurada)})
    return render(request, "contabilidade/dfc.html", contexto)


# ---------------------------------------------------------------------------
# Conferência
# ---------------------------------------------------------------------------


@login_required
@require_safe
def conferencia(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    lotes = []
    for lancamento in localizar_lotes_desbalanceados(empresa=empresa):
        # Linguagem de contador (a tela pede isto explicitamente), em vez
        # do rótulo técnico de três vias que a API devolve
        # ("sem_partidas"/"partida_unica"/"desbalanceado" — achado novo 12).
        if lancamento.quantidade_itens == 0:
            motivo = "Lançamento sem nenhuma partida."
        elif lancamento.quantidade_itens == 1:
            motivo = "Lançamento com uma única partida (sem contrapartida)."
        else:
            motivo = "Débitos e créditos não coincidem."
        lotes.append(
            {
                "lancamento": lancamento,
                "motivo": motivo,
                "total_debito_ptbr": _valor_ptbr(lancamento.total_debito),
                "total_credito_ptbr": _valor_ptbr(lancamento.total_credito),
                "diferenca_ptbr": _valor_ptbr(lancamento.total_debito - lancamento.total_credito),
            }
        )

    contas_sinteticas = [
        {
            "conta": conta,
            "debitos_ptbr": _valor_ptbr(conta.debitos),
            "creditos_ptbr": _valor_ptbr(conta.creditos),
        }
        for conta in localizar_contas_sinteticas_com_movimento(empresa=empresa)
    ]
    contas_com_subordinadas = localizar_contas_que_aceitam_lancamento_e_tem_subordinadas(
        empresa=empresa
    )
    hierarquia_inconsistente = localizar_inconsistencias_de_hierarquia(empresa=empresa)

    # BL-198 (b) na Conferência: aqui não existe período, então o aviso
    # equivalente é outro — lançamento com data FORA DA FAIXA do RC-77
    # (antes de 01/01/2000 ou depois de hoje + N dias). É a única tela de
    # uso normal em que um lançamento datado `9999-12-31` aparece SEM o
    # contador precisar suspeitar primeiro e alargar o período à mão.
    #
    # Vale para dado JÁ GRAVADO: a faixa do RC-77 fecha a porta de entrada,
    # e esta linha acende a luz sobre o que entrou antes dela (ou por uma
    # porta que não passa pela tela, como o admin do Django). Validar a
    # entrada não conserta o passado — e o reparo de dado gravado está
    # declarado fora do escopo desta etapa, o que torna a Conferência o
    # único lugar onde esse passado é visível.
    lancamentos_com_data_fora_da_faixa = list(
        localizar_lancamentos_com_data_fora_da_faixa(empresa=empresa)
    )

    contexto = {
        "empresa": empresa,
        "lotes": lotes,
        "contas_sinteticas": contas_sinteticas,
        "contas_com_subordinadas": contas_com_subordinadas,
        "hierarquia_inconsistente": hierarquia_inconsistente,
        "lancamentos_com_data_fora_da_faixa": lancamentos_com_data_fora_da_faixa,
        "data_minima_lancamento": DATA_MINIMA_LANCAMENTO,
        "data_maxima_lancamento": data_maxima_lancamento(),
        "tudo_certo": not (
            lotes
            or contas_sinteticas
            or contas_com_subordinadas
            or hierarquia_inconsistente
            or lancamentos_com_data_fora_da_faixa
        ),
    }
    return render(request, "contabilidade/conferencia.html", contexto)


# ---------------------------------------------------------------------------
# Fechamento de competência (DL-016 fatia 1 no servidor; DL-031 é a PORTA)
#
# NENHUMA regra contábil desta seção mora aqui — encerrar_competencia,
# reabrir_competencia e marcar_competencia_como_entregue (services.py) já
# decidem, já travam a linha sob concorrência e já gravam a trilha de
# auditoria, auditados em duas rodadas na fatia 1. Esta tela só CHAMA os
# três serviços, traduz cada exceção de negócio em mensagem de português
# (nunca 500 — a lição do BL-457, medida na tela de lançamento) e trata o
# "sem permissão" como ESTADO explicado, não como sumiço silencioso de botão
# (critério 1 do plano DL-031).
#
# Arquétipos, pela direção de arte (§2): D (painel de período) para
# `fechamento`, E (assistente com etapas) para as três telas de ação —
# cada uma mostra o que vai acontecer e o que deixa de ser possível ANTES
# do botão, e a de entrega (a única ação sem volta pelo produto, RC-101)
# exige confirmação explícita em vez de um clique só.
# ---------------------------------------------------------------------------

# Mesma faixa das duas CheckConstraint de Competencia.Meta
# ("competencia_mes_entre_1_e_12", "competencia_ano_entre_1970_e_2999") — a
# MESMA faixa que apps.contabilidade.views._validar_ano_mes já aplica na
# API, antes de chamar o serviço. Não importada de lá: aquele validador fala
# o protocolo do DRF (levanta DRFValidationError), que esta tela não usa —
# só o NÚMERO é compartilhado, por comentário, no mesmo padrão que
# NIVEL_MAXIMO (acima) já copia o teto da API em vez de importar o nome.
_MES_MINIMO_COMPETENCIA, _MES_MAXIMO_COMPETENCIA = 1, 12
_ANO_MINIMO_COMPETENCIA, _ANO_MAXIMO_COMPETENCIA = 1970, 2999


def _ano_mes_de_competencia_valido(ano, mes):
    return (
        _MES_MINIMO_COMPETENCIA <= mes <= _MES_MAXIMO_COMPETENCIA
        and _ANO_MINIMO_COMPETENCIA <= ano <= _ANO_MAXIMO_COMPETENCIA
    )


def _pode_fechar_competencia(request):
    return PodeFecharCompetencia().has_permission(request, None)


def _competencia_pedida(fonte):
    """Lê e valida 'ano'/'mes' de `fonte` (request.GET no GET das três telas
    de ação — a competência viaja por querystring, como o período do
    Diário/Razão/Balancete — e request.POST no POST, onde os dois campos
    voltam como `<input type="hidden">` do próprio formulário, no mesmo
    contrato que a tela já julga).

    Nunca lança exceção: devolve `(ano, mes, None)` quando válido, ou
    `(None, None, mensagem)` quando não — mesmo padrão de
    `_periodo_do_formulario` (erro de entrada nunca é 500, sempre mensagem
    em português). `_inteiro_de_cliente` é o mesmo julgador de QUANTIDADE de
    cliente que o resto deste arquivo já usa (nunca reinterpreta dígito
    Unicode, nunca lança exceção) — 'ano'/'mes' são quantidade de negócio,
    não identificador de banco.
    """
    ano = _inteiro_de_cliente((fonte.get("ano") or "").strip())
    mes = _inteiro_de_cliente((fonte.get("mes") or "").strip())
    if ano is None or mes is None:
        return None, None, "Informe ano e mês da competência."
    if not _ano_mes_de_competencia_valido(ano, mes):
        return (
            None,
            None,
            f"Competência inválida: o mês deve estar entre {_MES_MINIMO_COMPETENCIA} e "
            f"{_MES_MAXIMO_COMPETENCIA}, e o ano entre {_ANO_MINIMO_COMPETENCIA} e "
            f"{_ANO_MAXIMO_COMPETENCIA}.",
        )
    return ano, mes, None


# BL-196: contrato de cada ação — mesma política dos cinco dicionários que
# `lancamento_novo`/`conta_nova` já aplicam, e pelo mesmo motivo (um campo
# que a superfície não lê nunca deve ser ignorado em silêncio). As três são
# rotas de AÇÃO: sem arquivo, sem querystring no POST (o GET usa
# querystring só para MONTAR o formulário; o POST manda 'ano'/'mes' como
# campo oculto do próprio `<form>`, como qualquer outro dado do corpo) e sem
# `Idempotency-Key` (nenhuma das três usa cabeçalho para idempotência; as
# três já são seguras para reenvio — fechar e entregar são idempotentes no
# SERVIÇO, e reabrir é uma ação explícita com motivo, não um POST que se
# repete sem querer).
CONTRATO_FECHAR_COMPETENCIA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no fechamento de competência",
)
CONTRATO_REABRIR_COMPETENCIA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reabertura de competência",
)
CONTRATO_ENTREGAR_COMPETENCIA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes", "confirmar_entrega"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na entrega de competência",
)


@login_required
@require_safe
def fechamento(request, empresa_id):
    """Painel de competências da empresa (arquétipo D) — critérios 1 e 2.

    Lista os meses com estado, quem fechou, quando e se foi entregue; a
    conferência do RC-58 é checada AQUI, uma vez, para a base inteira da
    empresa — havendo lote desbalanceado, nenhum link de "Fechar" aparece
    nas linhas 'aberta' (critério 2: nunca deixar o contador clicar para
    descobrir). Quem não pode fechar/reabrir/entregar (RC-102) continua
    vendo o painel inteiro — só a coluna de ações muda, com uma explicação
    no topo em vez de sumir em silêncio (critério 1).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    # RC-58 / critério 2: mesma checagem que `encerrar_competencia`
    # (services.py) aplica antes de fechar — repetida aqui só para EXIBIR o
    # bloqueio antes do clique. A recusa de verdade continua sendo a do
    # serviço; esta lista não é usada para decidir nada além do que a tela
    # mostra.
    lotes_desbalanceados = list(localizar_lotes_desbalanceados(empresa=empresa))

    competencias = list(
        Competencia.objects.filter(empresa=empresa)
        .select_related("fechada_por", "entregue_por")
        .order_by("-ano", "-mes")
    )

    hoje = timezone.localdate()
    contexto = {
        "empresa": empresa,
        "competencias": competencias,
        "pode_fechar": _pode_fechar_competencia(request),
        "quantidade_lotes_desbalanceados": len(lotes_desbalanceados),
        "ano_sugestao": hoje.year,
        "mes_sugestao": hoje.month,
        "opcoes_mes": range(1, 13),
    }
    return render(request, "contabilidade/fechamento.html", contexto)


@login_required
@require_safe
def relatorios(request, empresa_id):
    """Hub de relatórios da empresa (DL-044, 3ª iteração — retorno do
    Fred: "os botões para abrir os relatórios [...] tá esquisito",
    referência escolhida por ele, Conta Azul — ver docs/assets/telas/
    dl044/pesquisa.md §7). Consulta de APRESENTAÇÃO só — nenhuma regra
    nova, nenhum dado que a barra lateral já não oferecesse por link
    direto (Diário/Razão via Plano de contas/Balancete/Balanço/
    Conferência): esta tela é um SEGUNDO caminho para as MESMAS cinco
    rotas, em cartão em vez de link de menu, aditivo — a barra lateral
    continua exatamente como estava, nenhum link foi removido de lá.

    Mesma permissão de leitura que as cinco telas de destino já exigem
    (`_pode_ler`) e a mesma recusa de livro-caixa (`_sem_contabilidade_
    para_livro_caixa`) — nunca uma cópia frouxa da regra: o hub só lista
    o que o papel já pode abrir de qualquer forma.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    cartoes = [
        {
            "chave": "diario",
            "icone": "diario",
            "titulo": "Diário",
            "descricao": "Todos os lançamentos da empresa, em ordem cronológica.",
            "url": reverse("contabilidade_web:diario", args=[empresa.id]),
        },
        {
            "chave": "razao",
            "icone": "razao",
            "titulo": "Razão",
            "descricao": "Movimento de uma conta específica — escolha pelo Plano de contas.",
            "url": reverse("contabilidade_web:plano_de_contas", args=[empresa.id]),
        },
        {
            "chave": "balancete",
            "icone": "balancete",
            "titulo": "Balancete",
            "descricao": "Saldo de todas as contas no período, com conferência D/C.",
            "url": reverse("contabilidade_web:balancete", args=[empresa.id]),
        },
        {
            "chave": "balanco",
            "icone": "balanco",
            "titulo": "Balanço",
            "descricao": "Demonstração patrimonial pronta para emissão.",
            "url": reverse("contabilidade_web:balanco", args=[empresa.id]),
        },
        # DL-045 fatia 3: sexto cartão — mesmo padrão dos outros cinco
        # (permissão/recusa de livro-caixa já checadas acima, ícone
        # PRÓPRIO no sprite de templates/base.html).
        {
            "chave": "dre",
            "icone": "dre",
            "titulo": "DRE",
            "descricao": "Resultado do período, por mês e acumulado do exercício.",
            "url": reverse("contabilidade_web:dre", args=[empresa.id]),
        },
        # DL-048/CTB-13: sétimo cartão — movimento dos lucros/prejuízos
        # acumulados no exercício (art. 186), mesmo molde do de cima
        # (permissão/recusa já checadas acima, ícone PRÓPRIO no sprite de
        # templates/base.html).
        {
            "chave": "dlpa",
            "icone": "dlpa",
            "titulo": "DLPA",
            "descricao": "Movimento dos lucros ou prejuízos acumulados no exercício.",
            "url": reverse("contabilidade_web:dlpa", args=[empresa.id]),
        },
        # DL-061/CTB-14: oitavo cartão — mutações de cada componente do
        # patrimônio líquido no exercício, em colunas. Mesmo molde dos
        # anteriores (permissão/recusa já checadas acima, ícone PRÓPRIO no
        # sprite de templates/base.html).
        {
            "chave": "dmpl",
            "icone": "dmpl",
            "titulo": "DMPL",
            "descricao": "Mutações de cada componente do patrimônio líquido no exercício.",
            "url": reverse("contabilidade_web:dmpl", args=[empresa.id]),
        },
        {
            "chave": "conferencia",
            "icone": "conferencia",
            "titulo": "Conferência",
            "descricao": "Lotes com débito e crédito que não batem — resolva antes de fechar.",
            "url": reverse("contabilidade_web:conferencia", args=[empresa.id]),
        },
    ]
    return render(
        request, "contabilidade/relatorios.html", {"empresa": empresa, "cartoes": cartoes}
    )


@login_required
@require_http_methods(["GET", "POST"])
def competencia_fechar(request, empresa_id):
    """Fecha uma competência (arquétipo E, etapa única) — critérios 2, 3, 5, 8.

    GET mostra o que vai ser fechado e o que deixa de ser possível ANTES do
    botão (o "momento da verdade" do plano DL-031); se houver lote
    desbalanceado (RC-58), nenhum botão aparece — só o caminho para a
    Conferência. POST chama `encerrar_competencia` (services.py), que é
    quem decide e trava de verdade: toda recusa do serviço vira mensagem em
    português nesta mesma tela, nunca 500 (BL-457).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite fechar competências desta empresa — essa ação "
            "exige administrador ou gestor (RC-102). Fale com um deles.",
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro_competencia = _competencia_pedida(fonte)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_FECHAR_COMPETENCIA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        try:
            competencia = encerrar_competencia(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except CompetenciaOperacaoRecusada as exc:
            # Critério 2/5 — RC-58 (lote desbalanceado) ou qualquer outro
            # estado que impeça o fechamento: a mensagem do próprio serviço
            # já nomeia a competência e o motivo. Nunca 500 (BL-457) — o
            # teste desta tela leva controle positivo no mesmo caso.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        # Critério 4/idempotência do serviço: reflete o resultado REAL —
        # `encerrada_agora=False` quando a competência já estava fechada
        # (duas requisições, ou o usuário voltou nesta mesma tela) nunca vira
        # "fechada agora" na mensagem.
        if competencia.encerrada_agora:
            messages.success(
                request, f"Competência {mes:02d}/{ano} de {empresa} fechada com sucesso."
            )
        else:
            messages.info(request, f"Competência {mes:02d}/{ano} de {empresa} já estava fechada.")
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    # GET: se já está encerrada, não há o que confirmar — volta ao painel
    # com o estado explicado em vez de mostrar um formulário sem sentido.
    competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
    if competencia is not None and competencia.estado == EstadoCompetencia.ENCERRADA:
        messages.info(request, f"A competência {mes:02d}/{ano} de {empresa} já está encerrada.")
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    lotes_desbalanceados = list(localizar_lotes_desbalanceados(empresa=empresa))
    contexto = {
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        "quantidade_lotes_desbalanceados": len(lotes_desbalanceados),
    }
    return render(request, "contabilidade/competencia_fechar.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def competencia_reabrir(request, empresa_id):
    """Reabre uma competência (arquétipo E, etapa única) — critérios 3, 5, 6, 8.

    Motivo é obrigatório na tela (rótulo próprio, avisando que fica na
    trilha); a recusa de verdade é do serviço (`reabrir_competencia`,
    `CompetenciaOperacaoInvalida` para motivo vazio). Mês já entregue
    (RC-101/BL-468) NUNCA oferece este formulário — nem no GET (precheck de
    conveniência) nem, se a corrida acontecer, no POST (a exceção
    `CompetenciaJaEntregue` do serviço vira mensagem, nunca 500).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite reabrir competências desta empresa — essa ação "
            "exige administrador ou gestor (RC-102). Fale com um deles.",
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro_competencia = _competencia_pedida(fonte)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_REABRIR_COMPETENCIA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        motivo = request.POST.get("motivo", "")
        try:
            reabrir_competencia(
                empresa=empresa,
                ano=ano,
                mes=mes,
                usuario=request.user,
                motivo=motivo,
                request=request,
            )
        except CompetenciaOperacaoInvalida as exc:
            # Critério 3: motivo vazio é erro de FORMULÁRIO — a tela NUNCA
            # some (o que já estava preenchido continua lá), status 400.
            messages.error(request, str(exc))
            return render(
                request,
                "contabilidade/competencia_reabrir.html",
                {"empresa": empresa, "ano": ano, "mes": mes, "motivo": motivo},
                status=400,
            )
        except CompetenciaJaEntregue as exc:
            # Critério 6/BL-468: a mensagem do serviço já nomeia a data da
            # entrega e orienta o ajuste no mês aberto (RC-101). Nunca 500
            # (BL-457) — controle positivo no mesmo caso, no teste desta tela.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)
        except CompetenciaOperacaoRecusada as exc:
            # Ex.: tentar reabrir uma competência que nunca foi encerrada.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        messages.success(request, f"Competência {mes:02d}/{ano} de {empresa} reaberta com sucesso.")
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    # GET: só oferece o formulário quando há, de fato, o que reabrir.
    competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
    if competencia is None or competencia.estado != EstadoCompetencia.ENCERRADA:
        messages.info(
            request,
            f"A competência {mes:02d}/{ano} de {empresa} não está encerrada; não há o que reabrir.",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)
    if competencia.entregue_em is not None:
        # Critério 6/BL-468 — precheck de conveniência: o servidor recusa do
        # mesmo jeito se a corrida acontecer (ver o `except
        # CompetenciaJaEntregue` acima), mas o contador nunca deveria
        # precisar clicar num formulário para descobrir isto.
        messages.error(
            request,
            f"A competência {mes:02d}/{ano} de {empresa} já foi entregue ao cliente em "
            f"{timezone.localtime(competencia.entregue_em):%d/%m/%Y %H:%M}. Depois da "
            "entrega, a competência não reabre — o ajuste vai no mês aberto.",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    contexto = {"empresa": empresa, "ano": ano, "mes": mes, "motivo": ""}
    return render(request, "contabilidade/competencia_reabrir.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def competencia_entregar(request, empresa_id):
    """Marca uma competência como entregue ao cliente (arquétipo E, etapa
    única) — critérios 4, 5, 8.

    Esta é a ÚNICA ação da fatia sem volta pelo produto (RC-101: depois de
    entregue, a competência nunca mais reabre) — por isso exige uma
    confirmação EXPLÍCITA (caixa de marcação), não um único clique.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite marcar competências desta empresa como entregues "
            "— essa ação exige administrador ou gestor (RC-102). Fale com um deles.",
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro_competencia = _competencia_pedida(fonte)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ENTREGAR_COMPETENCIA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        # Critério 4: a caixa de confirmação NÃO é regra de negócio — o
        # serviço não sabe dela e não precisa saber. É só o que impede um
        # clique não intencional de chegar ao serviço, proporcional ao
        # risco desta ação (AGENTS.md §0, item 6: ação sem volta pede
        # confirmação que identifique a operação).
        if request.POST.get("confirmar_entrega") != "1":
            messages.error(
                request,
                "Confirme a caixa de seleção para marcar esta competência como "
                "entregue — nada foi gravado.",
            )
            return render(
                request,
                "contabilidade/competencia_entregar.html",
                {"empresa": empresa, "ano": ano, "mes": mes},
                status=400,
            )

        try:
            marcar_competencia_como_entregue(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except CompetenciaOperacaoRecusada as exc:
            # Ex.: tentar entregar uma competência que ainda está aberta.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        messages.success(
            request,
            f"Competência {mes:02d}/{ano} de {empresa} marcada como entregue. Depois da "
            "entrega, ela não reabre pelo produto — qualquer ajuste vai no mês aberto "
            "(RC-101).",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    # GET: só oferece a confirmação quando a competência está encerrada —
    # entregar mês aberto não faz sentido e o serviço recusaria mesmo assim.
    competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
    if competencia is None or competencia.estado != EstadoCompetencia.ENCERRADA:
        messages.info(
            request,
            f"Só é possível marcar como entregue uma competência encerrada; feche a "
            f"competência {mes:02d}/{ano} de {empresa} primeiro.",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    contexto = {
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        # Docstring de marcar_competencia_como_entregue (services.py): a
        # entrega "pode repetir-se" — confirmar de novo apenas atualiza a
        # data/quem entregou. A tela avisa a diferença em vez de tratar como
        # se fosse a primeira vez.
        "ja_entregue_em": competencia.entregue_em,
    }
    return render(request, "contabilidade/competencia_entregar.html", contexto)


# ---------------------------------------------------------------------------
# DL-043 fatia 3 — telas de parâmetro contábil (fatia 1) e zeramento do
# resultado (fatia 2). Mesma disciplina DE-026 do resto do arquivo: esta
# tela NUNCA chama a própria API — chama `registrar_parametro_contabil`/
# `encerrar_vigencia_de_parametro_contabil`/`pre_visualizar_zeramento`/
# `zerar_resultado` (services.py) diretamente, e traduz as duas exceções do
# módulo (`ParametroContabilInvalido`, 400/mensagem; `VigenciaParametro
# ContabilConflitante`, 409/mensagem) para português — nunca 500, nunca uma
# segunda cópia de regra de negócio.
#
# Permissão (decisão do especialista-frontend, por analogia com o
# fechamento — RC-102 aplicada pelo PRÓPRIO serviço, ver o docstring de
# `registrar_parametro_contabil`): LER a LISTA de vigências exige só
# `papel_pode_ler_contabilidade` (`_pode_ler`) — o mesmo papel que já lê
# Balancete/Razão/Diário desta empresa, e renderiza a página normalmente
# (200), só sem o formulário de vigência nova e sem o botão "Encerrar
# vigência" para quem não pode geri-la. A PRÉVIA do zeramento (GET),
# REGISTRAR vigência, ENCERRAR vigência e EXECUTAR o zeramento (POST)
# exigem `PodeFecharCompetencia` (`_pode_fechar_competencia`,
# ADMINISTRADOR/GESTOR) — a MESMA classe que a API já usa nas quatro
# portas correspondentes (`ParametrosContabeisListCreateView`,
# `EncerrarVigenciaParametroContabilView`, `ZerarResultadoView` no GET e
# no POST, em views.py). ⚠️ A prévia NÃO é uma leitura franqueada a quem
# só lê, mesmo sendo um GET: corrigido pela reconferência da DL-043
# (achado R6) — a versão anterior deste comentário dizia que a prévia
# exigia só `_pode_ler`, mas o comportamento medido sempre foi
# `_pode_fechar_competencia` (o mesmo papel que grava). Um papel que só
# lê (ex. ANALISTA) recebe 403, com `erros/sem_permissao.html`
# explicando o motivo (nunca sumindo em silêncio, mesmo critério 1 do
# fechamento, e nunca um 403 cru) — testado em test_dl043_fatia3_telas.py.
# ---------------------------------------------------------------------------


class ParametroContabilForm(forms.Form):
    """Formulário de UMA vigência nova de parâmetro contábil (DL-043 fatia
    3) — `forms.Form`, nunca `ModelForm`: `ParametroContabilEmpresa` não
    tem (e não deve ganhar) uma segunda porta de escrita por
    `full_clean()`/admin, ver o docstring do próprio modelo. Este
    formulário só RECORTA o que aparece nos quatro `<select>`/campo de
    data; quem VALIDA de verdade — pertence à empresa, é analítica, é do
    grupo Patrimônio Líquido, a de prejuízos é devedora, ordem de
    vigência, sobreposição — é sempre `registrar_parametro_contabil`
    (services.py), chamado pela view.

    O recorte dos `queryset` dos três campos de conta é CONVENIÊNCIA (só
    contas que o serviço aceitaria aparecem no `<select>`, então a maior
    parte dos erros nunca chega a acontecer) — nunca a autorização de
    verdade, que continua sendo o serviço.
    """

    periodicidade_zeramento = forms.ChoiceField(
        label="Periodicidade do zeramento", choices=PeriodicidadeZeramento.choices
    )
    # DL-044 (achado das capturas da DL-043): `ModelChoiceField` sem
    # `empty_label` próprio usa o padrão do Django 6.1, EM INGLÊS mesmo com
    # `LANGUAGE_CODE = "pt-br"` — "- Select an option -" (medido
    # diretamente: `forms.ModelChoiceField(...).empty_label`), porque o
    # catálogo de tradução embutido do Django para este texto específico
    # não está carregado neste ponto do request. Os três campos abaixo
    # (e `ContaCriarForm.conta_pai`, a poucas linhas daqui) declaram
    # `empty_label` em português, explicitamente — nunca dependendo da
    # tradução automática do framework.
    conta_resultado_do_exercicio = forms.ModelChoiceField(
        label="Conta de resultado do exercício",
        queryset=Conta.objects.none(),
        empty_label="Selecione a conta",
        help_text="Conta analítica do grupo Patrimônio Líquido.",
    )
    conta_lucros_acumulados = forms.ModelChoiceField(
        label="Conta de lucros acumulados",
        queryset=Conta.objects.none(),
        empty_label="Selecione a conta",
        help_text="Conta analítica do grupo Patrimônio Líquido.",
    )
    conta_prejuizos_acumulados = forms.ModelChoiceField(
        label="Conta de (-) prejuízos acumulados",
        queryset=Conta.objects.none(),
        empty_label="Selecione a conta",
        help_text=(
            "Conta analítica do grupo Patrimônio Líquido, de natureza DEVEDORA "
            "— é retificadora (RC-61)."
        ),
    )
    vigencia_inicio = forms.DateField(
        label="Vigência (início)", widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, empresa, **kwargs):
        super().__init__(*args, **kwargs)
        # Isolamento (mesmo espírito de `ContaCriarForm.__init__`, acima):
        # os três `<select>` nunca listam conta de OUTRA empresa.
        contas_pl = Conta.objects.filter(
            empresa=empresa, tipo=TipoConta.PATRIMONIO_LIQUIDO, aceita_lancamento=True
        ).order_by("codigo")
        self.fields["conta_resultado_do_exercicio"].queryset = contas_pl
        self.fields["conta_lucros_acumulados"].queryset = contas_pl
        # RC-61: só as DEVEDORAS entram no recorte da conta de prejuízos —
        # a mesma regra que o serviço aplicaria de qualquer forma, só que
        # aqui filtra o QUE APARECE no <select>, então tentar escolher uma
        # conta credora nem é possível pela tela.
        self.fields["conta_prejuizos_acumulados"].queryset = contas_pl.filter(
            natureza=NaturezaConta.DEVEDORA
        )


CONTRATO_PARAMETRO_CONTABIL_WEB = ContratoDeRequisicao(
    campos={
        "csrfmiddlewaretoken",
        "periodicidade_zeramento",
        "conta_resultado_do_exercicio",
        "conta_lucros_acumulados",
        "conta_prejuizos_acumulados",
        "vigencia_inicio",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de parâmetro contábil",
)
# DL-061/CTB-14: a marca de adoção antecipada da NBC TG 51 é uma AÇÃO da mesma
# URL (`parametros_contabeis`, POST com `acao=adocao_antecipada_nbc_tg_51`),
# não uma rota nova: ela altera uma vigência que a tela já lista, e o
# discriminador evita uma terceira porta para a mesma permissão. Contrato
# PRÓPRIO (campos diferentes dos do registro de vigência — nunca um contrato
# reaproveitado com campo a mais, que a varredura não alcança).
ACAO_ADOCAO_ANTECIPADA_DA_NBC_TG_51 = "adocao_antecipada_nbc_tg_51"
CONTRATO_ADOCAO_ANTECIPADA_DA_NBC_TG_51_WEB = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "acao", "vigencia_id", "adota"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na marca de adoção antecipada da NBC TG 51",
)
CONTRATO_ENCERRAR_VIGENCIA_PARAMETRO_CONTABIL_WEB = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no encerramento de vigência do parâmetro contábil",
)
CONTRATO_ZERAR_RESULTADO_WEB = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes", "confirmar_zeramento"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no zeramento do resultado",
)


def _marcar_adocao_antecipada_da_nbc_tg_51(request, empresa):
    """Liga ou desliga a marca de adoção antecipada da NBC TG 51 numa
    vigência de parâmetro contábil da empresa (DL-061, E7). Chamada por
    `parametros_contabeis` DEPOIS de conferir `_pode_fechar_competencia`;
    sempre redireciona de volta à tela (PRG), com a mensagem do resultado.

    A gravação, a trilha e a recusa de livro-caixa são do serviço
    (`definir_adocao_antecipada_da_nbc_tg_51`); a vigência é buscada
    filtrando pela `empresa` da requisição — id de vigência de outra empresa
    dá 404, nunca confirma existência. A data entregue ao serviço é o INÍCIO
    da vigência: qualquer data dentro dela identifica a mesma linha, e é a
    que a tela mostra ao usuário.
    """
    destino = redirect("contabilidade_web:parametros_contabeis", empresa_id=empresa.id)
    try:
        recusar_dado_nao_contratado(request, CONTRATO_ADOCAO_ANTECIPADA_DA_NBC_TG_51_WEB)
    except DadoNaoContratado as exc:
        messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
        return destino

    vigencia_id = _identificador_de_cliente(request.POST.get("vigencia_id"))
    if vigencia_id is None:
        messages.error(request, "Vigência inválida: nada foi alterado.")
        return destino
    vigencia = get_object_or_404(ParametroContabilEmpresa, pk=vigencia_id, empresa=empresa)

    # Só "1" (marcar) e "0" (desmarcar): qualquer outro valor é recusado em
    # vez de virar "desmarcar" por omissão.
    valor = request.POST.get("adota")
    if valor not in ("0", "1"):
        messages.error(request, "Opção inválida: nada foi alterado.")
        return destino
    adota = valor == "1"
    antes = vigencia.adota_nbc_tg_51_antecipadamente
    inicio = date_format(vigencia.vigencia_inicio, "d/m/Y")

    try:
        definir_adocao_antecipada_da_nbc_tg_51(
            empresa=empresa,
            data_inicio_exercicio=vigencia.vigencia_inicio,
            adota=adota,
            usuario=request.user,
            request=request,
        )
    except (ParametroContabilInvalido, CompetenciaOperacaoRecusada) as exc:
        messages.error(request, str(exc))
        return destino

    if antes == adota:
        messages.info(
            request,
            f"A vigência iniciada em {inicio} já estava "
            f"{'marcada' if adota else 'desmarcada'}: nada foi alterado.",
        )
    elif adota:
        messages.success(
            request,
            f"Adoção antecipada da NBC TG 51 marcada na vigência iniciada em {inicio}. "
            "Efeito: as demonstrações dos exercícios que começam nesta vigência, anteriores "
            "à vigência obrigatória da norma, passam a citar a NBC TG 51 em vez da NBC TG 26 "
            "(R5). Nenhum saldo nem lançamento muda.",
        )
    else:
        messages.success(
            request,
            f"Adoção antecipada da NBC TG 51 desmarcada na vigência iniciada em {inicio}. "
            "Efeito: as demonstrações dos exercícios que começam nesta vigência, anteriores "
            "à vigência obrigatória da norma, voltam a citar a NBC TG 26 (R5). Nenhum saldo "
            "nem lançamento muda.",
        )
    return destino


@login_required
@require_http_methods(["GET", "POST"])
def parametros_contabeis(request, empresa_id):
    """Vigências de parâmetro contábil da empresa — arquétipos A (tabela)
    e B (formulário) combinados numa só tela, no mesmo molde de
    `fechamento` (tabela de competências + formulário de "fechar um mês
    ainda sem lançamento" logo abaixo, na mesma página).

    GET: qualquer papel que leia a contabilidade desta empresa vê a
    tabela de vigências inteira. POST (registrar vigência nova): exige
    `_pode_fechar_competencia` (RC-102 por analogia) — se um papel sem
    essa permissão forçar o POST, a checagem AQUI devolve 403 antes de
    chamar o serviço (o template nunca oferece o formulário a quem não
    pode, mas a autorização de verdade não depende disso).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    pode_gerir = _pode_fechar_competencia(request)
    form = None

    if request.method == "POST":
        if not pode_gerir:
            return _resposta_sem_permissao(
                request,
                "Seu papel não permite registrar parâmetro contábil desta empresa "
                "— essa ação exige administrador ou gestor (RC-102 por analogia com "
                "o fechamento de competência). Fale com um deles.",
            )
        # A permissão acima vale para as DUAS ações desta URL (registrar
        # vigência e marcar a adoção antecipada): a marca é alteração de
        # parâmetro contábil, então segue a regra da tela — administrador ou
        # gestor — e não a de classificar conta.
        if request.POST.get("acao") == ACAO_ADOCAO_ANTECIPADA_DA_NBC_TG_51:
            return _marcar_adocao_antecipada_da_nbc_tg_51(request, empresa)
        try:
            recusar_dado_nao_contratado(request, CONTRATO_PARAMETRO_CONTABIL_WEB)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:parametros_contabeis", empresa_id=empresa.id)

        form = ParametroContabilForm(request.POST, empresa=empresa)
        if form.is_valid():
            try:
                registrar_parametro_contabil(
                    empresa=empresa,
                    periodicidade_zeramento=form.cleaned_data["periodicidade_zeramento"],
                    conta_resultado_do_exercicio=form.cleaned_data["conta_resultado_do_exercicio"],
                    conta_lucros_acumulados=form.cleaned_data["conta_lucros_acumulados"],
                    conta_prejuizos_acumulados=form.cleaned_data["conta_prejuizos_acumulados"],
                    vigencia_inicio=form.cleaned_data["vigencia_inicio"],
                    usuario=request.user,
                    request=request,
                )
            except ParametroContabilInvalido as exc:
                # 400 de negócio: o formulário volta com o erro e TUDO o
                # que a pessoa digitou continua nos campos (critério do
                # arquétipo B — "o formulário não some quando dá erro").
                form.add_error(None, str(exc))
            except (VigenciaParametroContabilConflitante, CompetenciaOperacaoRecusada) as exc:
                # `CompetenciaOperacaoRecusada`: estouro da trava por empresa
                # (DE-078 item 3, `EmpresaTravadaPorOutraOperacao`).
                # 409 de estado (concorrência, sobreposição, retroatividade
                # sobre zeramento já gravado) — mesma tela, mesmo tratamento
                # visual; a DIFERENÇA entre 400 e 409 não muda nada para
                # quem está preenchendo o formulário, só para quem audita.
                form.add_error(None, str(exc))
            else:
                messages.success(request, "Vigência de parâmetro contábil registrada com sucesso.")
                return redirect("contabilidade_web:parametros_contabeis", empresa_id=empresa.id)
    elif pode_gerir:
        form = ParametroContabilForm(empresa=empresa)

    vigencias = list(
        ParametroContabilEmpresa.objects.filter(empresa=empresa)
        .select_related(
            "conta_resultado_do_exercicio",
            "conta_lucros_acumulados",
            "conta_prejuizos_acumulados",
        )
        .order_by("-vigencia_inicio", "-id")
    )
    tem_contas_pl = Conta.objects.filter(
        empresa=empresa, tipo=TipoConta.PATRIMONIO_LIQUIDO, aceita_lancamento=True
    ).exists()
    contexto = {
        "empresa": empresa,
        "vigencias": vigencias,
        "pode_gerir": pode_gerir,
        "form": form,
        "tem_contas_pl": tem_contas_pl,
    }
    status = 400 if form is not None and form.is_bound and form.errors else 200
    return render(request, "contabilidade/parametros_contabeis.html", contexto, status=status)


@login_required
@require_http_methods(["POST"])
def parametro_contabil_encerrar(request, empresa_id):
    """Encerra HOJE a vigência aberta de parâmetro contábil da empresa —
    rota de AÇÃO, só POST (mesmo desenho de `tenancy:emitir-convite`): sem
    corpo além do CSRF, sem tela de confirmação própria porque a ação é
    REVERSÍVEL (registrar uma vigência nova é sempre possível depois) —
    diferente de "marcar como entregue" (RC-101, sem volta), que por isso
    exige caixa de confirmação. O botão que dispara este POST fica na
    própria tabela de `parametros_contabeis.html`, com o rótulo "Encerrar
    vigência" — a ação que ele descreve.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite encerrar vigência de parâmetro contábil desta "
            "empresa — essa ação exige administrador ou gestor (RC-102 por analogia "
            "com o fechamento de competência). Fale com um deles.",
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    try:
        recusar_dado_nao_contratado(request, CONTRATO_ENCERRAR_VIGENCIA_PARAMETRO_CONTABIL_WEB)
    except DadoNaoContratado as exc:
        messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
        return redirect("contabilidade_web:parametros_contabeis", empresa_id=empresa.id)

    try:
        encerrar_vigencia_de_parametro_contabil(
            empresa=empresa, usuario=request.user, request=request
        )
    except (VigenciaParametroContabilConflitante, CompetenciaOperacaoRecusada) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Vigência de parâmetro contábil encerrada hoje.")
    return redirect("contabilidade_web:parametros_contabeis", empresa_id=empresa.id)


def _item_de_zeramento_para_tela(item):
    """`{"conta", "tipo", "valor"}` (services.py) -> dict pronto para o
    template: `tipo_letra` ("D"/"C", RC-61 — nunca só cor) e `valor_ptbr`
    (`_valor_ptbr`, mesma função de formatação que toda outra tela desta
    fatia usa). Nunca calcula nada — só empacota o que o serviço já
    decidiu.
    """
    return {
        "conta": item["conta"],
        "tipo_letra": "D" if item["tipo"] == TipoPartida.DEBITO else "C",
        "valor_ptbr": _valor_ptbr(item["valor"]),
    }


@login_required
@require_http_methods(["GET", "POST"])
def zeramento_do_periodo(request, empresa_id):
    """Prévia (GET) e execução (POST) do zeramento do resultado do período
    — arquétipo E ("assistente com etapas"): a última etapa mostra
    exatamente o que vai ser gravado, antes de gravar, e só grava com
    confirmação explícita (caixa de marcação + botão que nomeia a ação).

    ⚠️ Nome desta VIEW é `zeramento_do_periodo`, DIFERENTE do nome da rota
    (`contabilidade_web:zerar_resultado`, mesmo nome do CRITÉRIO do plano
    e do serviço) de propósito: uma função `def zerar_resultado(request,
    empresa_id)` neste módulo REBINDARIA o nome global `zerar_resultado`
    que o `import` do topo do arquivo já aponta para a função de SERVIÇO
    (`apps.contabilidade.services.zerar_resultado`) — a chamada dentro do
    próprio corpo desta view deixaria de alcançar o serviço e passaria a
    chamar a VIEW recursivamente (com a assinatura errada, estourando
    `TypeError` na hora). `urls_web.py` mapeia o nome de rota `zerar_
    resultado` para esta função por `path(..., zeramento_do_periodo,
    name="zerar_resultado")` — nome de rota e nome de função Python são
    namespaces INDEPENDENTES; só o SEGUNDO tem o risco de sombra aqui.

    Estados tratados, nesta ordem: sem escritório/sem permissão/livro-
    caixa (iguais a toda outra tela desta fatia); ano/mês ausente ou fora
    da faixa (`_competencia_pedida`, mesmo padrão do fechamento); sem
    parâmetro contábil vigente OU mês fora da periodicidade vigente
    (`ParametroContabilInvalido` do serviço, mesma mensagem, com link para
    cadastrar/gerir o parâmetro — as DUAS causas mostram o mesmo link,
    porque as duas se resolvem no mesmo lugar); competência encerrada
    (checada ANTES da prévia, mesmo padrão do RC-58 no fechamento — texto
    igual ao que o serviço usaria, para o "recusa" da prévia não ficar
    silencioso); nada a zerar (prévia sem nenhum item); e o caminho feliz
    (prévia com itens, ou execução).

    Sobre o estado "complemento" do critério de aceite: o serviço não
    devolve, nem na prévia nem na execução, se um dado cálculo é a
    PRIMEIRA vez que o período é zerado ou um COMPLEMENTO de uma vez
    anterior (só devolve `criado_etapa1`/`criado_etapa2` — se a chamada
    gravou algo novo ou reaproveitou um lançamento já existente por
    idempotência). Alterar o serviço para expor isso está fora do escopo
    desta etapa (não tenho permissão para editar services.py) — a tela
    cobre o critério com uma nota PERMANENTE, sempre visível na prévia,
    explicando o mecanismo (ver o template), e a tela de resultado mostra
    `criado_etapa1`/`criado_etapa2` para quem confirma saber se algo foi
    de fato gravado agora.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite zerar o resultado desta empresa — essa ação "
            "exige administrador ou gestor (RC-102 por analogia com o fechamento de "
            "competência). Fale com um deles.",
        )

    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro_competencia = _competencia_pedida(fonte)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ZERAR_RESULTADO_WEB)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        # Critério "confirmação explícita" — mesmo padrão de
        # `competencia_entregar` (caixa de marcação obrigatória): a caixa
        # não é regra de negócio, é só o que impede um clique não
        # intencional de chegar ao serviço.
        if request.POST.get("confirmar_zeramento") != "1":
            messages.error(
                request,
                "Confirme a caixa de seleção para gerar os lançamentos de "
                "zeramento — nada foi gravado.",
            )
            url_previa = reverse("contabilidade_web:zerar_resultado", args=[empresa.id])
            return redirect(f"{url_previa}?ano={ano}&mes={mes}")

        try:
            resultado = zerar_resultado(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except (
            ParametroContabilInvalido,
            LancamentoInvalido,
            ChaveIdempotenciaConflitante,
            CompetenciaEncerrada,
            CompetenciaOperacaoRecusada,
        ) as exc:
            # Mesmas recusas que a API mapeia para 400/409 (DE-078 itens 2,
            # 3, 5 e 6): na tela, todas viram mensagem de erro e voltam ao
            # fechamento sem gravar — nunca o 500 cru do achado B3.
            # `ZeramentoForaDeOrdem` é subclasse de `CompetenciaEncerrada` e
            # `EmpresaTravadaPorOutraOperacao` de `CompetenciaOperacaoRecusada`.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        contexto = {
            "empresa": empresa,
            "ano": ano,
            "mes": mes,
            "resultado": resultado,
        }
        return render(request, "contabilidade/zerar_resultado.html", contexto)

    # GET — prévia.
    try:
        calculo = pre_visualizar_zeramento(empresa=empresa, ano=ano, mes=mes)
    except ParametroContabilInvalido as exc:
        contexto = {
            "empresa": empresa,
            "ano": ano,
            "mes": mes,
            "erro_parametro": str(exc),
        }
        return render(request, "contabilidade/zerar_resultado.html", contexto)
    except CompetenciaEncerrada as exc:
        # `ZeramentoForaDeOrdem` (DE-078 item 2): a prévia também recusa
        # quando já existe zeramento posterior. Mesmo estado de tela da
        # competência encerrada — mensagem do serviço, sem botão de gravar.
        contexto = {
            "empresa": empresa,
            "ano": ano,
            "mes": mes,
            "erro_competencia_encerrada": str(exc),
        }
        return render(request, "contabilidade/zerar_resultado.html", contexto)

    # RC-57: mesmo precheck que o fechamento já aplica para o RC-58 (lote
    # desbalanceado) — mostra o bloqueio ANTES de qualquer botão, em vez
    # de deixar a pessoa preencher a prévia para só então descobrir. A
    # recusa de VERDADE é do serviço (dentro de `zerar_resultado`, sob a
    # trava de competência); esta consulta é só para EXIBIR o estado.
    competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
    if competencia is not None and competencia.estado == EstadoCompetencia.ENCERRADA:
        contexto = {
            "empresa": empresa,
            "ano": ano,
            "mes": mes,
            "erro_competencia_encerrada": (
                f"A competência {mes:02d}/{ano} de {empresa} está encerrada; não é "
                "possível zerar o resultado nela. A correção de período encerrado "
                "segue o estorno (RC-103), nunca um novo zeramento por cima."
            ),
        }
        return render(request, "contabilidade/zerar_resultado.html", contexto)

    nada_a_zerar = not calculo["itens_etapa1"] and calculo["etapa2"] is None
    itens_etapa1 = [_item_de_zeramento_para_tela(item) for item in calculo["itens_etapa1"]]
    item_resultado_etapa1 = (
        _item_de_zeramento_para_tela(calculo["item_resultado_etapa1"])
        if calculo["item_resultado_etapa1"] is not None
        else None
    )
    etapa2 = None
    if calculo["etapa2"] is not None:
        etapa2 = {
            "destino": calculo["etapa2"]["destino"],
            "item_resultado": _item_de_zeramento_para_tela(calculo["etapa2"]["item_resultado"]),
            "item_destino": _item_de_zeramento_para_tela(calculo["etapa2"]["item_destino"]),
        }

    contexto = {
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        "data_final": calculo["data_final"],
        "periodicidade_display": calculo["parametro"].get_periodicidade_zeramento_display(),
        "nada_a_zerar": nada_a_zerar,
        "itens_etapa1": itens_etapa1,
        "item_resultado_etapa1": item_resultado_etapa1,
        "etapa2": etapa2,
    }
    return render(request, "contabilidade/zerar_resultado.html", contexto)


# ---------------------------------------------------------------------------
# DL-077, fatia 1 (frente C): importar e exportar o plano de contas em arquivo.
#
# A TELA NÃO DECIDE NADA DO PLANO. Ler o arquivo, conferir contra o cadastro,
# decidir tipo e natureza, recusar, aplicar e exportar são do núcleo
# (`apps.contabilidade.intercambio`). Aqui só se lê o formulário, se chama o
# núcleo e se escolhe a resposta: página, arquivo ou recusa.
#
# O ARQUIVO NÃO FICA GUARDADO, nem no servidor nem na sessão. Para conferir de
# novo (prefixos de tipo) e para aplicar, o contador envia o arquivo outra vez.
# A aplicação recebe o SHA-256 e a assinatura da prévia que ele revisou e confere
# os dois, pelo mesmo mecanismo de `plano-importacao-aplicar` da API: se o
# arquivo ou o cadastro mudou, nada é gravado.
#
# Ordem das recusas, igual à das outras telas deste módulo: escritório ativo
# (sem escritório, outra tela), empresa do escritório (404), papel (403) e modo
# livro-caixa (403). Permissões iguais às da API: importar e aplicar exigem
# `PodeEscriturar`; exportar exige a leitura da contabilidade; o modelo da
# planilha segue a importação (`PodeEscriturar`).
# ---------------------------------------------------------------------------

# Quantas linhas "prefixo -> tipo" a prévia oferece. É limite do FORMULÁRIO, não
# da regra: o núcleo (`validar_prefixos`) aceita quantos prefixos vierem. Seis
# cobre os grupos de um plano comum; se faltar, o contador confere o arquivo.
PREFIXOS_POR_PREVIA = 6

# Rótulos da importação. As chaves são as de `LEITORES` (um teste confere).
FORMATOS_DE_IMPORTACAO = {
    ecd.FORMATO: "ECD: registros I050 do bloco I",
    referencia.FORMATO: "Sistema de referência: leiaute com separador (registros 0000 e 0200)",
    proprio.FORMATO: "DataLedger: TXT próprio, com ponto e vírgula e cabeçalho",
    excel.FORMATO: "Planilha Excel (.xlsx), no modelo da tela",
}

# Avisos fixos da exportação. O da ECD é o texto que o produto promete na tela: o
# arquivo NÃO é a ECD. O do sistema de referência diz que o código reduzido não é
# estável (o DataLedger não tem código reduzido próprio).
AVISO_DA_EXPORTACAO_ECD = (
    "Arquivo com os registros do plano no leiaute da ECD — não é a ECD: não tem os "
    "demais blocos, termos nem assinatura e não passou pelo programa da Receita."
)
AVISO_DA_EXPORTACAO_REFERENCIA = (
    "Código reduzido sequencial pela ordem do código: não é estável entre exportações. "
    "O DataLedger não tem código reduzido próprio."
)
# Chaves = `ESCRITORES` (um teste confere). Excel não exporta: só importa.
FORMATOS_DE_EXPORTACAO = {
    ecd.FORMATO: ("ECD: registros I050 do bloco I", AVISO_DA_EXPORTACAO_ECD),
    referencia.FORMATO: (
        "Sistema de referência: leiaute com separador",
        AVISO_DA_EXPORTACAO_REFERENCIA,
    ),
    proprio.FORMATO: ("DataLedger: TXT próprio, com ponto e vírgula e cabeçalho", ""),
}

FILTROS_DE_EXPORTACAO_NA_TELA = {
    "todas": "Todas as contas do plano",
    "analiticas": "Só as contas analíticas (saem junto as sintéticas que elas precisam)",
    "com_movimento": "Só as contas com movimento no período (saem junto as superiores)",
}

POLITICAS_DE_IMPORTACAO_NA_TELA = {
    POLITICA_SO_ACRESCENTAR: (
        "Só acrescentar (padrão): cria as contas que faltam e não altera as existentes"
    ),
    POLITICA_ACRESCENTAR_E_ATUALIZAR_NOME: (
        "Acrescentar e atualizar nome: além disso, troca o nome das contas existentes"
    ),
}

TEXTO_FIXO_DA_IMPORTACAO = (
    "A importação nunca apaga conta, e nunca muda tipo ou natureza de conta que já existe."
)

ACOES_NA_TELA = {
    ACAO_CRIAR: "Criar",
    ACAO_ATUALIZAR: "Atualizar nome",
    ACAO_SEM_MUDANCA: "Sem mudança",
    ACAO_RECUSADA: "Recusada",
}

ORIGENS_DO_TIPO_NA_TELA = {
    ORIGEM_ARQUIVO: "do arquivo",
    ORIGEM_CONTA_SUPERIOR: "da conta superior",
    ORIGEM_PREFIXO: "pelo prefixo informado",
    ORIGEM_CADASTRO: "do cadastro",
}

# "presumida pelo tipo" é o aviso HI-88: o contador confere as redutoras.
ORIGENS_DA_NATUREZA_NA_TELA = {
    ORIGEM_ARQUIVO: "do arquivo",
    ORIGEM_PRESUMIDA: "presumida pelo tipo: conferir",
    ORIGEM_CADASTRO: "do cadastro",
}

MENSAGEM_SEM_PERMISSAO_IMPORTAR = "Seu papel não permite importar o plano de contas desta empresa."
MENSAGEM_SEM_PERMISSAO_EXPORTAR = "Seu papel não permite ler a contabilidade desta empresa."
MENSAGEM_SEM_PERMISSAO_MODELO = (
    "Seu papel não permite baixar o modelo do plano de contas desta empresa."
)


def _nomes_das_linhas_de_prefixo():
    return [(f"prefixo_{i}", f"tipo_{i}") for i in range(1, PREFIXOS_POR_PREVIA + 1)]


def _campos_do_formulario_de_importacao(*, com_assinatura):
    campos = {"csrfmiddlewaretoken", "formato", "politica"}
    for nome_prefixo, nome_tipo in _nomes_das_linhas_de_prefixo():
        campos.update((nome_prefixo, nome_tipo))
    if com_assinatura:
        campos.update(("sha256", "assinatura"))
    return frozenset(campos)


# Contratos de requisição: a tela recusa o campo que não declara (não o ignora em
# silêncio). A prévia não grava, então não recebe SHA-256 nem assinatura; a
# aplicação recebe os dois, porque é a única que grava.
_CONTRATO_DA_PREVIA_DO_PLANO = ContratoDeRequisicao(
    campos=_campos_do_formulario_de_importacao(com_assinatura=False),
    aceita_arquivo=True,
    aceita_querystring=False,
    contexto="na conferência da importação do plano de contas",
)
_CONTRATO_DA_APLICACAO_DO_PLANO = ContratoDeRequisicao(
    campos=_campos_do_formulario_de_importacao(com_assinatura=True),
    aceita_arquivo=True,
    aceita_querystring=False,
    contexto="na aplicação da importação do plano de contas",
)


def _prefixos_do_formulario(post):
    """Converte as linhas `prefixo_N`/`tipo_N` no mapa prefixo -> tipo.

    Linha vazia é ignorada. Prefixo sem tipo, tipo sem prefixo e prefixo repetido
    são erros da própria linha. O mapa nunca guarda um prefixo "por ordem de
    chegada": quem casa com a conta é sempre o prefixo mais longo, no núcleo.
    """
    mapa = {}
    erros = []
    for indice, (nome_prefixo, nome_tipo) in enumerate(_nomes_das_linhas_de_prefixo(), start=1):
        prefixo = (post.get(nome_prefixo) or "").strip()
        tipo = (post.get(nome_tipo) or "").strip()
        if not prefixo and not tipo:
            continue
        if not prefixo or not tipo:
            erros.append(f"linha {indice} dos prefixos: informe o começo do código e o tipo.")
        elif prefixo in mapa:
            erros.append(f"o prefixo '{prefixo}' aparece mais de uma vez.")
        else:
            mapa[prefixo] = tipo
    return mapa, erros


# Campos de TEXTO da tela de importação (os de prefixo são tratados à parte). Ver A10.
_CAMPOS_DE_TEXTO_DA_TELA = ("formato", "politica", "sha256", "assinatura")


def _entrada_da_importacao(request, *, com_assinatura):
    """Lê e valida a FORMA do formulário de importação. Devolve (dados, erros).

    `erros` é um dict campo -> mensagem, vazio quando dá para ler o arquivo. Aqui
    só se confere a forma: arquivo presente, formato e política conhecidos, tamanho
    e extensão da planilha. O CONTEÚDO do arquivo quem julga é o leitor do núcleo.
    """
    post = request.POST
    arquivo = request.FILES.get("arquivo")
    erros = {}
    # A10 (BL-196): campo de TEXTO enviado como arquivo era descartado em silêncio (`post.get`
    # não lê FILES). A recusa vai no campo, antes de qualquer leitura. `prefixo_N` e `tipo_N`
    # são do formulário de prefixos, e o erro cai em "prefixos".
    formato = (post.get("formato") or "").strip()
    politica = (post.get("politica") or POLITICA_SO_ACRESCENTAR).strip()

    if arquivo is None:
        erros["arquivo"] = "Escolha o arquivo do plano de contas."
    elif arquivo.size > TAMANHO_MAXIMO_ARQUIVO_BYTES:
        # A11 (limite de corpo): checado DEPOIS de o Django receber o corpo. O proxy à frente
        # DEVE limitar o corpo antes do aplicativo (`client_max_body_size` ou equivalente, de
        # implantação; não está no repositório).
        erros["arquivo"] = (
            f"arquivo com {arquivo.size} bytes; o limite é "
            f"{TAMANHO_MAXIMO_ARQUIVO_BYTES // (1024 * 1024)} MB."
        )
    elif formato == excel.FORMATO and not arquivo.name.lower().endswith(".xlsx"):
        # O núcleo confere o conteúdo (macro, .xls, CSV renomeado). O nome é a
        # primeira barreira e a mensagem mais clara, como na API.
        erros["arquivo"] = (
            "a planilha precisa ser .xlsx, sem macros (.xlsm não é aceito). "
            "Use o modelo para baixar."
        )

    if formato not in LEITORES:
        erros["formato"] = "Escolha o formato do arquivo."
    if politica not in POLITICAS:
        erros["politica"] = "Escolha a política de importação."

    prefixos, erros_de_prefixo = _prefixos_do_formulario(post)
    if erros_de_prefixo:
        erros["prefixos"] = " ".join(erros_de_prefixo)
    else:
        try:
            prefixos = validar_prefixos(prefixos)
        except ParametroInvalido as exc:
            erros["prefixos"] = exc.mensagem

    sha256 = (post.get("sha256") or "").strip()
    assinatura = (post.get("assinatura") or "").strip()
    if com_assinatura and not (sha256 and assinatura):
        # Só acontece com formulário montado à mão: a tela sempre devolve os dois.
        erros["geral"] = (
            "Faça a conferência de novo: a aplicação precisa do resumo da prévia que você revisou."
        )

    # Por último, para não ser trocada pelas mensagens de valor acima: campo de texto que chegou
    # como arquivo é recusado no próprio campo (A10).
    for nome_enviado in request.FILES:
        if nome_enviado in _CAMPOS_DE_TEXTO_DA_TELA:
            erros[nome_enviado] = f"o campo '{nome_enviado}' é texto: não envie arquivo nele."
        elif nome_enviado.startswith(("prefixo_", "tipo_")):
            erros["prefixos"] = f"o campo '{nome_enviado}' é texto: não envie arquivo nele."

    dados = {
        "arquivo": arquivo,
        "formato": formato,
        "politica": politica,
        "prefixos": prefixos,
        "sha256": sha256,
        "assinatura": assinatura,
    }
    return dados, erros


def _previa_do_arquivo(empresa, dados):
    """Lê o arquivo com o leitor do formato e confere contra o cadastro. Não grava.

    Levanta `IntercambioRecusado` (arquivo grande demais, formato, parâmetro); quem
    chama mostra a mensagem na tela, sem 500.
    """
    resultado = ler_arquivo(
        dados["formato"], dados["arquivo"].read(), nome_arquivo=dados["arquivo"].name
    )
    return conferir_plano(empresa, resultado, dados["politica"], dados["prefixos"])


def _linha_da_previa(item, rotulos_de_tipo, rotulos_de_natureza):
    """Uma conta da prévia, já em texto para a tela (o núcleo entrega os códigos)."""
    return {
        "linha": item.linha,
        "codigo": item.codigo,
        "nome": item.nome,
        "codigo_pai": item.codigo_pai or "—",
        "analitica": "Sim" if item.analitica else "Não",
        "tipo": rotulos_de_tipo.get(item.tipo, "Sem tipo"),
        "origem_tipo": ORIGENS_DO_TIPO_NA_TELA.get(item.origem_tipo, ""),
        "natureza": rotulos_de_natureza.get(item.natureza, "—"),
        "origem_natureza": ORIGENS_DA_NATUREZA_NA_TELA.get(item.origem_natureza, ""),
        "situacao": "—" if item.ativa is None else ("Ativa" if item.ativa else "Inativa"),
        "acao": ACOES_NA_TELA[item.acao],
        "recusada": item.acao == ACAO_RECUSADA,
        "natureza_presumida": item.origem_natureza == ORIGEM_PRESUMIDA,
        "inativa": item.ativa is False,
        "ocorrencias": [
            {
                "nivel": "Erro" if o.nivel == NIVEL_ERRO else "Aviso",
                "campo": o.campo,
                "mensagem": o.mensagem,
            }
            for o in item.ocorrencias
        ],
    }


def _contexto_da_previa(empresa, previa):
    rotulos_de_tipo = dict(TipoConta.choices)
    rotulos_de_natureza = dict(NaturezaConta.choices)
    itens = [_linha_da_previa(item, rotulos_de_tipo, rotulos_de_natureza) for item in previa.itens]
    # `tipos_por_prefixo` traz o VALOR do tipo ("receita"); o rótulo é só para ler.
    prefixos_aplicados = [
        (prefixo, tipo, rotulos_de_tipo[tipo]) for prefixo, tipo in previa.tipos_por_prefixo
    ]
    # Linhas do formulário de prefixo: o que já foi aplicado nesta prévia aparece
    # preenchido, e as linhas que sobram ficam vazias.
    linhas_de_prefixo = []
    for indice, (nome_prefixo, nome_tipo) in enumerate(_nomes_das_linhas_de_prefixo(), start=1):
        prefixo, tipo = ("", "")
        if indice <= len(prefixos_aplicados):
            prefixo, tipo, _ = prefixos_aplicados[indice - 1]
        linhas_de_prefixo.append(
            {"nome_prefixo": nome_prefixo, "nome_tipo": nome_tipo, "prefixo": prefixo, "tipo": tipo}
        )
    # Os mesmos prefixos viajam como campos ocultos na aplicação: a conferência de lá
    # precisa dos MESMOS prefixos que a prévia que o contador viu.
    prefixos_ocultos = [
        {"nome_prefixo": f"prefixo_{i}", "nome_tipo": f"tipo_{i}", "prefixo": p, "tipo": t}
        for i, (p, t) in enumerate(previa.tipos_por_prefixo, start=1)
    ]
    return {
        "empresa": empresa,
        "previa": previa,
        "formato_rotulo": FORMATOS_DE_IMPORTACAO[previa.resultado.formato],
        "politica_rotulo": POLITICAS_DE_IMPORTACAO_NA_TELA[previa.politica],
        "texto_fixo": TEXTO_FIXO_DA_IMPORTACAO,
        "pode_aplicar": not previa.tem_erro,
        "erros_total": sum(1 for o in previa.ocorrencias if o.nivel == NIVEL_ERRO),
        "avisos_total": sum(1 for o in previa.ocorrencias if o.nivel != NIVEL_ERRO),
        "contagens": previa.contagens,
        "itens": itens,
        # Linha 0 é o arquivo inteiro (ex.: arquivo sem conta, documento de outra empresa).
        "ocorrencias_do_arquivo": [
            {"nivel": "Erro" if o.nivel == NIVEL_ERRO else "Aviso", "mensagem": o.mensagem}
            for o in previa.ocorrencias
            if o.linha == 0
        ],
        "prefixos_aplicados": [(prefixo, rotulo) for prefixo, _, rotulo in prefixos_aplicados],
        "contas_para_conferir_natureza": [i for i in itens if i["natureza_presumida"]],
        "contas_inativas": [i for i in itens if i["inativa"]],
        "precisa_prefixos": any(
            o.campo == "tipo" and o.nivel == NIVEL_ERRO for o in previa.ocorrencias
        ),
        "linhas_de_prefixo": linhas_de_prefixo,
        "prefixos_ocultos": prefixos_ocultos,
        "tipos": TipoConta.choices,
        "registros_ignorados": previa.resultado.registros_ignorados,
        "aviso_do_formato": (
            "O código reduzido do arquivo não é gravado no DataLedger: a conta fica com o "
            "código da coluna Código."
            if previa.resultado.formato == referencia.FORMATO
            else ""
        ),
        "politica": previa.politica,
        "formato": previa.resultado.formato,
        "nome_arquivo": previa.resultado.nome_arquivo,
        "sha256": previa.sha256,
        "assinatura": previa.assinatura,
    }


def _renderizar_importacao(request, empresa, *, erros=None, status=200):
    contexto = {
        "empresa": empresa,
        "formatos": FORMATOS_DE_IMPORTACAO,
        "politicas": POLITICAS_DE_IMPORTACAO_NA_TELA,
        "formato_escolhido": request.POST.get("formato", ""),
        "politica_escolhida": request.POST.get("politica") or POLITICA_SO_ACRESCENTAR,
        "erros": erros or {},
        "texto_fixo": TEXTO_FIXO_DA_IMPORTACAO,
    }
    return render(request, "contabilidade/plano_importar.html", contexto, status=status)


def _renderizar_previa(request, empresa, previa, *, mensagem=None, status=200):
    contexto = _contexto_da_previa(empresa, previa)
    contexto["mensagem"] = mensagem
    return render(request, "contabilidade/plano_importar_previa.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def plano_importar(request, empresa_id):
    """GET: formulário da importação. POST: prévia (lê e confere; não grava nada)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, MENSAGEM_SEM_PERMISSAO_IMPORTAR)
    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    if request.method == "GET":
        return _renderizar_importacao(request, empresa)

    try:
        recusar_dado_nao_contratado(request, _CONTRATO_DA_PREVIA_DO_PLANO)
    except DadoNaoContratado as exc:
        return _renderizar_importacao(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    dados, erros = _entrada_da_importacao(request, com_assinatura=False)
    if erros:
        return _renderizar_importacao(request, empresa, erros=erros, status=400)
    try:
        previa = _previa_do_arquivo(empresa, dados)
    except IntercambioRecusado as exc:
        return _renderizar_importacao(request, empresa, erros={"geral": exc.mensagem}, status=400)
    return _renderizar_previa(request, empresa, previa)


@login_required
@require_http_methods(["POST"])
def plano_importar_aplicar(request, empresa_id):
    """Grava o plano conferido. Recebe o arquivo de novo, o SHA-256 e a assinatura.

    409 se o arquivo ou o cadastro mudaram desde a prévia (nada gravado). Se o plano
    tiver erro, mostra a prévia com o motivo e responde 400 (nada gravado). Sucesso:
    volta ao plano de contas com a contagem.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, MENSAGEM_SEM_PERMISSAO_IMPORTAR)
    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa

    try:
        recusar_dado_nao_contratado(request, _CONTRATO_DA_APLICACAO_DO_PLANO)
    except DadoNaoContratado as exc:
        return _renderizar_importacao(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    dados, erros = _entrada_da_importacao(request, com_assinatura=True)
    if erros:
        return _renderizar_importacao(request, empresa, erros=erros, status=400)
    try:
        previa = _previa_do_arquivo(empresa, dados)
    except IntercambioRecusado as exc:
        return _renderizar_importacao(request, empresa, erros={"geral": exc.mensagem}, status=400)

    try:
        aplicado = aplicar_plano(
            empresa,
            previa,
            request.user,
            request,
            sha256_esperado=dados["sha256"],
            assinatura_esperada=dados["assinatura"],
        )
    except (ArquivoAlteradoDesdeAPrevia, PlanoAlteradoDesdeAPrevia) as exc:
        return _renderizar_importacao(
            request,
            empresa,
            erros={
                "geral": (
                    f"{exc.mensagem} Nada foi gravado: faça a prévia de novo com o "
                    "arquivo e confira o resultado."
                )
            },
            status=409,
        )
    except PlanoRecusado as exc:
        # Só chega aqui com formulário montado à mão: a prévia não mostra o botão
        # Aplicar quando há erro. Mostra a prévia com o motivo, nada gravado.
        return _renderizar_previa(request, empresa, previa, mensagem=exc.mensagem, status=400)
    except CompetenciaOperacaoRecusada as exc:
        return _renderizar_importacao(request, empresa, erros={"geral": str(exc)}, status=409)

    messages.success(
        request,
        "Plano de contas aplicado. "
        f"Contas criadas: {aplicado.criadas}. "
        f"Nomes atualizados: {aplicado.atualizadas}. "
        f"Já existiam sem mudança: {aplicado.sem_mudanca}.",
    )
    return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)


@login_required
@require_safe
def plano_modelo_excel(request, empresa_id):
    """Baixa o modelo `.xlsx` da importação por planilha (mesma permissão da importação)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, MENSAGEM_SEM_PERMISSAO_MODELO)
    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa
    try:
        recusar_campos_nao_contratados(
            request.GET, frozenset(), contexto="no modelo do plano de contas"
        )
    except DadoNaoContratado as exc:
        return _renderizar_importacao(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    resposta = HttpResponse(excel.gerar_modelo(), content_type=TIPO_DE_CONTEUDO_XLSX)
    resposta["Content-Disposition"] = 'attachment; filename="modelo-plano-de-contas.xlsx"'
    return resposta


def _valores_da_exportacao(get):
    """Valores do formulário de exportação, como texto (vazio quando não vieram)."""
    return {
        "formato": (get.get("formato") or "").strip(),
        "filtro": (get.get("filtro") or "todas").strip(),
        "inicio": (get.get("inicio") or "").strip(),
        "fim": (get.get("fim") or "").strip(),
        "data_alteracao": (get.get("data_alteracao") or "").strip(),
    }


def _renderizar_exportacao(request, empresa, *, valores=None, erros=None, status=200):
    contexto = {
        "empresa": empresa,
        "formatos": [
            {"valor": valor, "rotulo": rotulo, "aviso": aviso}
            for valor, (rotulo, aviso) in FORMATOS_DE_EXPORTACAO.items()
        ],
        "filtros": FILTROS_DE_EXPORTACAO_NA_TELA,
        "valores": valores or _valores_da_exportacao({}),
        "erros": erros or {},
    }
    return render(request, "contabilidade/plano_exportar.html", contexto, status=status)


@login_required
@require_safe
def plano_exportar(request, empresa_id):
    """Formulário da exportação (sem `formato`) ou o arquivo do plano (com `formato`).

    O arquivo sai pelo GET com os filtros na querystring, como na API. Cada
    exportação entra na trilha de auditoria com o SHA-256 do arquivo gerado.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(request, MENSAGEM_SEM_PERMISSAO_EXPORTAR)
    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa
    try:
        recusar_campos_nao_contratados(
            request.GET,
            CAMPOS_QUERYSTRING_EXPORTACAO_PLANO,
            contexto="na exportação do plano de contas",
        )
    except DadoNaoContratado as exc:
        return _renderizar_exportacao(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )

    if "formato" not in request.GET:
        return _renderizar_exportacao(request, empresa)

    valores = _valores_da_exportacao(request.GET)
    if not valores["formato"]:
        # Formulário enviado sem escolher o formato: pede a escolha, em vez da mensagem
        # técnica do núcleo ("formato '' não suportado").
        return _renderizar_exportacao(
            request,
            empresa,
            valores=valores,
            erros={"geral": "Escolha o formato do arquivo a exportar."},
            status=400,
        )
    try:
        inicio = para_data(valores["inicio"]) if valores["inicio"] else None
        fim = para_data(valores["fim"]) if valores["fim"] else None
        data_alteracao = para_data(valores["data_alteracao"]) if valores["data_alteracao"] else None
    except DataInvalida as exc:
        return _renderizar_exportacao(
            request, empresa, valores=valores, erros={"geral": str(exc)}, status=400
        )

    try:
        arquivo = exportar_plano(
            empresa=empresa,
            formato=valores["formato"],
            filtro=valores["filtro"],
            inicio=inicio,
            fim=fim,
            data_alteracao=data_alteracao,
        )
    except IntercambioRecusado as exc:
        return _renderizar_exportacao(
            request, empresa, valores=valores, erros={"geral": exc.mensagem}, status=400
        )

    registrar(
        acao="plano_de_contas.exportado",
        objeto=empresa,
        escritorio=empresa.escritorio,
        usuario=request.user,
        request=request,
        detalhes={
            "formato": arquivo.formato,
            "filtro": arquivo.filtro,
            "inicio": inicio.isoformat() if inicio else None,
            "fim": fim.isoformat() if fim else None,
            "quantidade_contas": arquivo.quantidade_contas,
            "sinteticas_incluidas": arquivo.sinteticas_incluidas,
            "sha256": arquivo.sha256,
            "avisos": list(arquivo.avisos),
        },
    )

    if arquivo.formato in _FORMATOS_EM_ISO_8859_1:
        tipo_do_conteudo = "text/plain; charset=iso-8859-1"
    else:
        tipo_do_conteudo = "text/plain; charset=utf-8"
    resposta = HttpResponse(arquivo.conteudo, content_type=tipo_do_conteudo)
    nome = _nome_do_arquivo_exportado(empresa, arquivo.formato, timezone.localdate())
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


# ---------------------------------------------------------------------------
# DL-077 (fatia 2): tela de exportação de lançamentos e saldos.
#
# DUAS ETAPAS, de propósito. A primeira (`lancamentos_exportar`) lê, confere e MOSTRA o
# relatório (contagens, somas, SHA-256, autor, data e hora, contas usadas, omitidos e
# avisos). Nada sai da tela ainda, então não entra na trilha. A segunda
# (`lancamentos_exportar_arquivo`) é o download: refaz a exportação e só entrega o arquivo
# se o SHA-256 bater com o que a conferência mostrou. Se não bater, os lançamentos mudaram,
# e a resposta é 409, pedindo nova conferência. Só o download entra na trilha
# `lancamentos.exportados`.
# ---------------------------------------------------------------------------

AVISO_DA_EXPORTACAO_DE_LANCAMENTOS_ECD = (
    "Este arquivo não é a ECD. Ele traz só os registros de lançamentos e saldos (I150, I155, "
    "I200 e I250): não tem registro 0000, bloco J, termos, assinatura nem validação do programa "
    "da Receita. Não substitui a escrituração contábil digital."
)
AVISO_DA_EXPORTACAO_DE_LANCAMENTOS_REFERENCIA = (
    "Código reduzido sequencial pela ordem do código: ele muda quando o plano muda, e o arquivo "
    "só vale com o plano desta data. O DataLedger não tem código reduzido próprio. Não é a ECD."
)
# Chaves = `FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS` do núcleo (um teste confere).
FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS_NA_TELA = {
    ecd.FORMATO: (
        "Leiaute da ECD: registros I200/I250 (e I150/I155, se marcado). Não é a ECD",
        AVISO_DA_EXPORTACAO_DE_LANCAMENTOS_ECD,
    ),
    referencia.FORMATO: (
        "Sistema de referência: leiaute com separador (6000/6100)",
        AVISO_DA_EXPORTACAO_DE_LANCAMENTOS_REFERENCIA,
    ),
    proprio.FORMATO: ("DataLedger: TXT próprio, com ponto e vírgula e cabeçalho", ""),
}
CAMPOS_DA_TELA_DE_LANCAMENTOS = frozenset(
    {
        "formato",
        "inicio",
        "fim",
        "incluir_saldos",
        "omitir_nao_representaveis",
        "normalizar_texto",
    }
)
CAMPOS_DO_DOWNLOAD_DE_LANCAMENTOS = CAMPOS_DA_TELA_DE_LANCAMENTOS | {"sha256"}
MENSAGEM_CONFERENCIA_DESATUALIZADA = (
    "Os lançamentos mudaram desde a conferência que você viu. Confira o arquivo de novo."
)


def _valores_da_exportacao_de_lancamentos(get):
    """Valores do formulário de lançamentos, como texto e booleano (vazio quando não vieram)."""

    def marcado(nome):
        return (get.get(nome) or "").strip().lower() in ("true", "on", "1")

    return {
        "formato": (get.get("formato") or "").strip(),
        "inicio": (get.get("inicio") or "").strip(),
        "fim": (get.get("fim") or "").strip(),
        "incluir_saldos": marcado("incluir_saldos"),
        "omitir_nao_representaveis": marcado("omitir_nao_representaveis"),
        "normalizar_texto": marcado("normalizar_texto"),
    }


def _exportacao_de_lancamentos_pedida(empresa, valores, usuario):
    """Chama o núcleo com os valores da tela. Levanta `DataInvalida` ou `IntercambioRecusado`."""
    inicio = para_data(valores["inicio"]) if valores["inicio"] else None
    fim = para_data(valores["fim"]) if valores["fim"] else None
    return exportar_lancamentos(
        empresa=empresa,
        formato=valores["formato"],
        data_inicial=inicio,
        data_final=fim,
        incluir_saldos=valores["incluir_saldos"],
        omitir_nao_representaveis=valores["omitir_nao_representaveis"],
        normalizar_texto=valores["normalizar_texto"],
        usuario=usuario,
    )


def _link_do_arquivo_de_lancamentos(empresa, valores, sha256):
    """URL do download com os mesmos parâmetros, e o SHA-256 que a conferência mostrou."""
    parametros = {"formato": valores["formato"], "inicio": valores["inicio"], "fim": valores["fim"]}
    if valores["incluir_saldos"]:
        parametros["incluir_saldos"] = "true"
    if valores["omitir_nao_representaveis"]:
        parametros["omitir_nao_representaveis"] = "true"
    if valores["normalizar_texto"]:
        parametros["normalizar_texto"] = "true"
    parametros["sha256"] = sha256
    destino = reverse("contabilidade_web:lancamentos_exportar_arquivo", args=[empresa.id])
    return f"{destino}?{urlencode(parametros)}"


def _relatorio_para_tela(relatorio):
    """O relatório de conferência já em texto pt-BR, para o template não fazer conta."""
    return {
        "formato_rotulo": FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS_NA_TELA[relatorio.formato][0],
        "inicio": relatorio.inicio,
        "fim": relatorio.fim,
        "incluir_saldos": relatorio.incluir_saldos,
        "quantidade_lancamentos": relatorio.quantidade_lancamentos,
        "quantidade_partidas": relatorio.quantidade_partidas,
        "quantidade_zeramentos": relatorio.quantidade_zeramentos,
        "quantidade_estornos": relatorio.quantidade_estornos,
        "soma_debitos": _valor_ptbr(relatorio.soma_debitos),
        "soma_creditos": _valor_ptbr(relatorio.soma_creditos),
        "conferem": relatorio.soma_debitos == relatorio.soma_creditos,
        "quantidade_meses": relatorio.quantidade_meses,
        "contas_usadas": relatorio.contas_usadas,
        "omitidos": relatorio.omitidos,
        "normalizar_texto": relatorio.normalizar_texto,
        "textos_normalizados": relatorio.textos_normalizados,
        "quantidade_textos_normalizados": len(relatorio.textos_normalizados),
        "sha256": relatorio.sha256,
        "nome_do_arquivo": relatorio.nome_do_arquivo,
        "autor": relatorio.autor,
        "gerado_em": relatorio.gerado_em,
        "avisos": relatorio.avisos,
    }


def _renderizar_exportacao_de_lancamentos(
    request, empresa, *, valores=None, erros=None, relatorio=None, link=None, status=200
):
    contexto = {
        "empresa": empresa,
        "formatos": [
            {"valor": valor, "rotulo": rotulo, "aviso": aviso}
            for valor, (rotulo, aviso) in FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS_NA_TELA.items()
        ],
        "valores": valores or _valores_da_exportacao_de_lancamentos({}),
        "erros": erros or {},
        "relatorio": _relatorio_para_tela(relatorio) if relatorio is not None else None,
        "link_do_arquivo": link,
    }
    return render(request, "contabilidade/lancamentos_exportar.html", contexto, status=status)


@login_required
@require_safe
def lancamentos_exportar(request, empresa_id):
    """Formulário da exportação de lançamentos, ou a conferência do arquivo (com `formato`).

    A conferência não grava nada e não entra na trilha. O arquivo sai pela rota de download.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(request, MENSAGEM_SEM_PERMISSAO_EXPORTAR)
    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa
    try:
        recusar_campos_nao_contratados(
            request.GET,
            CAMPOS_DA_TELA_DE_LANCAMENTOS,
            contexto="na exportação de lançamentos",
        )
    except DadoNaoContratado as exc:
        return _renderizar_exportacao_de_lancamentos(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )

    if "formato" not in request.GET:
        return _renderizar_exportacao_de_lancamentos(request, empresa)

    valores = _valores_da_exportacao_de_lancamentos(request.GET)
    if not valores["formato"]:
        return _renderizar_exportacao_de_lancamentos(
            request,
            empresa,
            valores=valores,
            erros={"geral": "Escolha o formato do arquivo a exportar."},
            status=400,
        )
    try:
        arquivo = _exportacao_de_lancamentos_pedida(empresa, valores, request.user)
    except (DataInvalida, IntercambioRecusado) as exc:
        mensagem = exc.mensagem if isinstance(exc, IntercambioRecusado) else str(exc)
        return _renderizar_exportacao_de_lancamentos(
            request, empresa, valores=valores, erros={"geral": mensagem}, status=400
        )
    return _renderizar_exportacao_de_lancamentos(
        request,
        empresa,
        valores=valores,
        relatorio=arquivo.relatorio,
        link=_link_do_arquivo_de_lancamentos(empresa, valores, arquivo.sha256),
    )


@login_required
@require_safe
def lancamentos_exportar_arquivo(request, empresa_id):
    """Entrega o arquivo de lançamentos, se o SHA-256 ainda bate com a conferência.

    Grava a trilha `lancamentos.exportados` (SHA-256, intervalo e contagens) só quando o
    arquivo sai. Sem `sha256`, a rota entrega do mesmo jeito, como a API.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(request, MENSAGEM_SEM_PERMISSAO_EXPORTAR)
    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return recusa_livro_caixa
    try:
        recusar_campos_nao_contratados(
            request.GET,
            CAMPOS_DO_DOWNLOAD_DE_LANCAMENTOS,
            contexto="no download da exportação de lançamentos",
        )
    except DadoNaoContratado as exc:
        return _renderizar_exportacao_de_lancamentos(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )

    valores = _valores_da_exportacao_de_lancamentos(request.GET)
    if not valores["formato"]:
        return _renderizar_exportacao_de_lancamentos(
            request,
            empresa,
            valores=valores,
            erros={"geral": "Escolha o formato do arquivo a exportar."},
            status=400,
        )
    try:
        arquivo = _exportacao_de_lancamentos_pedida(empresa, valores, request.user)
    except (DataInvalida, IntercambioRecusado) as exc:
        mensagem = exc.mensagem if isinstance(exc, IntercambioRecusado) else str(exc)
        return _renderizar_exportacao_de_lancamentos(
            request, empresa, valores=valores, erros={"geral": mensagem}, status=400
        )

    sha_conferido = (request.GET.get("sha256") or "").strip().lower()
    if sha_conferido and sha_conferido != arquivo.sha256:
        return _renderizar_exportacao_de_lancamentos(
            request,
            empresa,
            valores=valores,
            erros={"geral": MENSAGEM_CONFERENCIA_DESATUALIZADA},
            status=409,
        )

    relatorio = arquivo.relatorio
    registrar(
        acao="lancamentos.exportados",
        objeto=empresa,
        escritorio=empresa.escritorio,
        usuario=request.user,
        request=request,
        detalhes=relatorio.para_trilha(),
    )
    if relatorio.formato == proprio.FORMATO:
        tipo_do_conteudo = "text/plain; charset=utf-8"
    else:
        tipo_do_conteudo = "text/plain; charset=iso-8859-1"
    resposta = HttpResponse(arquivo.conteudo, content_type=tipo_do_conteudo)
    resposta["Content-Disposition"] = f'attachment; filename="{relatorio.nome_do_arquivo}"'
    return resposta


# ---------------------------------------------------------------------------
# DL-077, fatia 3 (frente B): telas da importação de lançamentos com área de conferência.
#
# Permissões iguais às da API (bloco "DL-077, fatia 3, frente A" de `apps.contabilidade.views`):
# receber, reconferir, definir de-para, aceitar avisos, efetivar e descartar exigem `PodeEscriturar`
# (`_pode_escriturar`). Ler a importação exige `papel_pode_ler_contabilidade` (`_pode_ler`), e isso
# inclui PARALEGAL, que lê e não age. Cada view recusa, nesta ordem: escritório ausente, empresa de
# outro escritório (404), papel e livro-caixa. Só depois lê o corpo da requisição.
#
# NENHUMA regra de conferência mora aqui. A tela mostra o que o serviço já gravou em
# `ImportacaoLancamentos` e `LancamentoImportado`, e chama o serviço para cada ação. Há duas
# leituras de APRESENTAÇÃO, marcadas no código: a contagem de "prontos" e o veredito da efetivação
# (tudo ou nada), lidos das mesmas flags que o serviço usa para decidir. O serviço continua sendo a
# autoridade: ele reconfere e recusa de novo na efetivação, e a tela só deixa de oferecer o
# botão antes disso.
# ---------------------------------------------------------------------------

AVISO_DO_FORMATO_ECD = (
    "O lançamento de encerramento (E) não entra: o zeramento do resultado é do DataLedger. "
    "Sem o registro 0000, a empresa do arquivo não é conferida, e a conferência avisa."
)
AVISO_DO_FORMATO_REFERENCIA = (
    "O código do arquivo é o reduzido, que o DataLedger não tem. Cada código precisa de um "
    "de-para para uma conta analítica antes da efetivação."
)
AVISO_DO_FORMATO_PROPRIO = (
    "Os códigos de conta precisam existir no plano desta empresa. O que não existir precisa de "
    "um de-para antes da efetivação."
)
AVISO_DO_FORMATO_EXCEL = (
    "Planilha .xlsx sem macros. A coluna conta é texto: use o modelo para baixar."
)

# Chaves = `LEITORES_DE_LANCAMENTOS` do serviço (um teste confere). O rótulo diz o leiaute; o aviso
# diz o que o contador precisa saber antes de enviar.
FORMATOS_DE_IMPORTACAO_DE_LANCAMENTOS_NA_TELA = {
    FormatoImportacaoLancamentos.ECD: ("ECD: registros I200 e I250", AVISO_DO_FORMATO_ECD),
    FormatoImportacaoLancamentos.REFERENCIA: (
        "Sistema de referência: leiaute com registros 6000 e 6100",
        AVISO_DO_FORMATO_REFERENCIA,
    ),
    FormatoImportacaoLancamentos.PROPRIO: (
        "DataLedger: TXT próprio, com ponto e vírgula e cabeçalho",
        AVISO_DO_FORMATO_PROPRIO,
    ),
    FormatoImportacaoLancamentos.EXCEL: (
        "Planilha Excel (.xlsx), no modelo para baixar",
        AVISO_DO_FORMATO_EXCEL,
    ),
}

MENSAGEM_SEM_PERMISSAO_IMPORTAR_LANCAMENTOS = (
    "Seu papel não permite importar lançamentos desta empresa."
)
MENSAGEM_SEM_PERMISSAO_LER_IMPORTACOES = "Seu papel não permite ler a contabilidade desta empresa."
MENSAGEM_SEM_PERMISSAO_AGIR_NA_IMPORTACAO = (
    "Seu papel pode ler esta importação, mas não confere, decide nem efetiva lançamentos."
)
MENSAGEM_CONFIRMACAO_DA_EFETIVACAO = (
    "Marque a confirmação antes de efetivar: os lançamentos serão gravados no Diário e não "
    "poderão ser alterados, só estornados."
)

TAMANHO_DA_PAGINA_DA_CONFERENCIA = 50
LIMITE_DA_LISTA_DE_IMPORTACOES = 200
LIMITE_DE_LANCAMENTOS_FORA_NA_TELA = 500
FILTROS_DA_CONFERENCIA = {
    "todos": "Todos os lançamentos",
    "erros": "Só com erro",
    "avisos": "Só com aviso",
}
CAMPOS_DA_CONFERENCIA = frozenset({"filtro", "pagina"})
# Só tudo ou nada: a efetivação parcial ("só os válidos") está suspensa (BL-676) e não é oferecida.
POLITICAS_DE_EFETIVACAO_NA_TELA = {
    importacao_servico.TUDO_OU_NADA: "Tudo ou nada",
}

# Contratos das superfícies de escrita da tela: o corpo que cada formulário envia, e nada mais.
CONTRATO_DO_ENVIO_DE_LANCAMENTOS = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "formato"}),
    aceita_arquivo=True,
    contexto="no envio de lançamentos",
)
CONTRATO_DO_DEPARA_DA_IMPORTACAO = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "codigo_origem", "conta"}),
    contexto="no de-para da importação",
)
CONTRATO_DOS_AVISOS_DA_IMPORTACAO = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "numeros", "todos", "aceitar_arquivo"}),
    contexto="no aceite de avisos",
)
CONTRATO_DA_RECONFERENCIA = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken"}), contexto="na reconferência"
)
CONTRATO_DA_EFETIVACAO_DA_IMPORTACAO = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "politica", "confirmar"}),
    contexto="na efetivação de lançamentos",
)
CONTRATO_DO_DESCARTE_DA_IMPORTACAO = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "motivo"}),
    contexto="no descarte da importação",
)


def _contado(quantidade, singular, plural):
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _entrada_das_importacoes(
    request, empresa_id, *, escrever, mensagem_sem_escrita=MENSAGEM_SEM_PERMISSAO_AGIR_NA_IMPORTACAO
):
    """Recusas comuns das telas de importação, na ordem das outras telas deste módulo.

    Devolve `(empresa, recusa)`: `recusa` é a resposta pronta quando a view não pode seguir, ou
    `None`. `escrever=True` exige `PodeEscriturar`; `False` exige só a leitura da contabilidade.
    """
    if request.escritorio is None:
        return None, _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if escrever and not _pode_escriturar(request):
        return None, _resposta_sem_permissao(request, mensagem_sem_escrita)
    if not escrever and not _pode_ler(request):
        return None, _resposta_sem_permissao(request, MENSAGEM_SEM_PERMISSAO_LER_IMPORTACOES)
    recusa_livro_caixa = _sem_contabilidade_para_livro_caixa(request, empresa)
    if recusa_livro_caixa is not None:
        return None, recusa_livro_caixa
    return empresa, None


def _acao_sobre_importacao(request, empresa_id, importacao_id):
    """Entrada de toda ação (POST) sobre uma importação: escrita, empresa certa e importação dela.

    A importação é buscada DENTRO da empresa da URL: a de outra empresa, mesmo do mesmo escritório,
    responde 404 e nunca é lida.
    """
    empresa, recusa = _entrada_das_importacoes(request, empresa_id, escrever=True)
    if recusa is not None:
        return None, None, recusa
    importacao = get_object_or_404(ImportacaoLancamentos, pk=importacao_id, empresa=empresa)
    return empresa, importacao, None


def _erros_do_envio(formato, arquivo):
    erros = {}
    if arquivo is None:
        erros["arquivo"] = "Escolha o arquivo de lançamentos."
    elif arquivo.size > TAMANHO_MAXIMO_ARQUIVO_BYTES:
        erros["arquivo"] = (
            f"arquivo com {arquivo.size} bytes; o limite é "
            f"{TAMANHO_MAXIMO_ARQUIVO_BYTES // (1024 * 1024)} MB."
        )
    elif formato == excel.FORMATO and not arquivo.name.lower().endswith(".xlsx"):
        erros["arquivo"] = (
            "a planilha precisa ser .xlsx, sem macros (.xlsm não é aceito). "
            "Use o modelo para baixar."
        )
    if formato not in FORMATOS_DE_IMPORTACAO_DE_LANCAMENTOS_NA_TELA:
        erros["formato"] = "Escolha o formato do arquivo."
    return erros


def _renderizar_formulario_de_importacao(
    request, empresa, *, formato_escolhido="", erros=None, existente_id=None, status=200
):
    contexto = {
        "empresa": empresa,
        "formatos": [
            {"valor": valor, "rotulo": rotulo, "aviso": aviso}
            for valor, (rotulo, aviso) in FORMATOS_DE_IMPORTACAO_DE_LANCAMENTOS_NA_TELA.items()
        ],
        "formato_escolhido": formato_escolhido,
        "erros": erros or {},
        "existente_id": existente_id,
    }
    return render(request, "contabilidade/lancamentos_importar.html", contexto, status=status)


# --- Apresentação da conferência -------------------------------------------------------------
# Tudo abaixo LÊ o que o serviço gravou. Nenhuma linha recalcula conferência.

ROTULO_DO_NIVEL = {NIVEL_ERRO: "Erro", NIVEL_AVISO: "Aviso"}
# Quantos erros do arquivo inteiro a tela lista no veredito de só os válidos (o total vem antes).
LIMITE_DE_ERROS_DO_ARQUIVO_NA_TELA = 50
ROTULO_DA_ORIGEM_DA_CONTA = {"codigo": "código do plano", "depara": "de-para"}


def _contagens_da_conferencia(importacao):
    lancamentos = importacao.lancamentos
    return {
        "total": lancamentos.count(),
        "com_erro": lancamentos.filter(tem_erro=True).count(),
        "com_aviso_a_aceitar": lancamentos.filter(tem_aviso=True, aceito_com_aviso=False).count(),
        "com_aviso_aceito": lancamentos.filter(tem_aviso=True, aceito_com_aviso=True).count(),
        # APRESENTAÇÃO: sem erro e com avisos aceitos. É informação para o contador; a efetivação
        # só aceita o todo (tudo ou nada), e o serviço recusa de novo se algo não estiver pronto.
        "prontos": lancamentos.filter(tem_erro=False)
        .exclude(tem_aviso=True, aceito_com_aviso=False)
        .count(),
    }


def _veredito_da_efetivacao(importacao, contagens):
    """O que a efetivação (tudo ou nada) precisa para gravar, e o que a impede quando não pode.

    APRESENTAÇÃO. A efetivação é possível com ao menos um lançamento, sem erro do arquivo, sem erro
    de lançamento e sem aviso por aceitar: é a condição que o serviço aplica. A efetivação parcial
    ("só os válidos") está suspensa (BL-676) e não tem veredito: a tela não a oferece. O aviso de
    empresa não declarada sem aceite também impede (A11). Sem lançamento nenhum, não há botão.
    A lista de erros do arquivo vai no veredito, para o contador ver qual linha impede a gravação.
    """
    erros_do_arquivo = importacao.quantidade_erros_do_arquivo
    aceite_pendente = importacao.exige_aceite_do_arquivo and not importacao.aceite_do_arquivo
    pendencias = []
    if erros_do_arquivo:
        pendencias.append(_contado(erros_do_arquivo, "erro do arquivo", "erros do arquivo"))
    if contagens["com_erro"]:
        pendencias.append(
            _contado(contagens["com_erro"], "lançamento com erro", "lançamentos com erro")
        )
    if contagens["com_aviso_a_aceitar"]:
        pendencias.append(
            _contado(contagens["com_aviso_a_aceitar"], "aviso a aceitar", "avisos a aceitar")
        )
    if aceite_pendente:
        pendencias.append("o aviso de empresa não declarada precisa ser aceito")
    total = contagens["total"]
    if total == 0:
        pendencias.append("não há lançamento para efetivar")
    return {
        "pode": not pendencias,
        "pendencias": pendencias,
        "quantidade": total,
        # Os erros do arquivo que impedem a gravação, para a tela listar. A lista guardada prioriza
        # os erros, então o corte de 500 não os tira de cena.
        "erros_do_arquivo": [
            _ocorrencia_na_tela(o)
            for o in importacao.ocorrencias_do_arquivo
            if o["nivel"] == NIVEL_ERRO
        ][:LIMITE_DE_ERROS_DO_ARQUIVO_NA_TELA],
    }


def _situacao_na_tela(lancamento, importacao):
    """Em que estado está o lançamento e o que falta, em texto (cor nunca é o único sinal)."""
    if lancamento.lancamento_id is not None:
        return "Efetivado no Diário"
    if importacao.estado == EstadoImportacaoLancamentos.EFETIVADA:
        # Efetivada, o motivo de ter ficado de fora é o que ainda está gravado na linha.
        if lancamento.tem_erro:
            return "Ficou de fora: com erro"
        if lancamento.tem_aviso and not lancamento.aceito_com_aviso:
            return "Ficou de fora: aviso não aceito"
        return "Ficou de fora da efetivação"
    if importacao.estado == EstadoImportacaoLancamentos.DESCARTADA:
        return "Importação descartada: nada foi gravado"
    if lancamento.tem_erro:
        return "Com erro: não entra na efetivação"
    if lancamento.tem_aviso and not lancamento.aceito_com_aviso:
        return "Falta aceitar o aviso"
    return "Pronto para efetivar"


def _partida_na_tela(partida):
    return {
        "codigo_origem": partida["codigo_origem"],
        "conta_codigo": partida.get("conta_codigo"),
        "origem_da_conta": ROTULO_DA_ORIGEM_DA_CONTA.get(partida.get("origem_da_conta"), ""),
        "lado_rotulo": "Débito" if partida["lado"] == LADO_DEBITO else "Crédito",
        "valor_ptbr": _valor_ptbr(Decimal(partida["valor"])),
    }


def _ocorrencia_na_tela(ocorrencia):
    return {
        "nivel": ROTULO_DO_NIVEL.get(ocorrencia["nivel"], ocorrencia["nivel"]),
        "campo": ocorrencia["campo"],
        "mensagem": ocorrencia["mensagem"],
    }


def _lancamento_na_tela(lancamento, importacao):
    return {
        "id": lancamento.pk,
        "numero": lancamento.numero_origem,
        "linha": lancamento.linha,
        "data": lancamento.data,
        "historico": lancamento.historico,
        "partidas": [_partida_na_tela(p) for p in lancamento.partidas],
        "ocorrencias": [_ocorrencia_na_tela(o) for o in lancamento.ocorrencias],
        "tem_erro": lancamento.tem_erro,
        "aviso_a_aceitar": lancamento.tem_aviso and not lancamento.aceito_com_aviso,
        "lancamento_id": lancamento.lancamento_id,
        "situacao": _situacao_na_tela(lancamento, importacao),
    }


def _bloqueio_na_tela(bloqueio):
    """Uma ocorrência que impede a efetivação, com o lançamento ou o arquivo inteiro."""
    return {
        "numero": bloqueio.get("numero") or "arquivo inteiro",
        "linha": bloqueio["linha"],
        "campo": bloqueio["campo"],
        "mensagem": bloqueio["mensagem"],
    }


def _lancamentos_da_pagina(importacao, filtro, numero_da_pagina):
    lancamentos = importacao.lancamentos.all()
    if filtro == "erros":
        lancamentos = lancamentos.filter(tem_erro=True)
    elif filtro == "avisos":
        lancamentos = lancamentos.filter(tem_aviso=True)
    # `get_page` aceita número fora da faixa e devolve a última página, sem 404.
    return Paginator(lancamentos, TAMANHO_DA_PAGINA_DA_CONFERENCIA).get_page(numero_da_pagina)


def _codigos_sem_conta(importacao):
    """Códigos de origem que não viraram conta (pedem de-para), com quantos lançamentos afetam."""
    afetados = defaultdict(set)
    for lancamento in importacao.lancamentos.filter(tem_erro=True):
        for partida in lancamento.partidas:
            if partida.get("conta_id") is None:
                afetados[partida["codigo_origem"]].add(lancamento.numero_origem)
    return [
        {"codigo": codigo, "quantidade_de_lancamentos": len(numeros)}
        for codigo, numeros in sorted(afetados.items())
    ]


def _lancamentos_que_ficam_de_fora(importacao):
    """Efetivada, os lançamentos que não foram para o Diário. Em conferência, não há lista.

    Sem efetivação parcial (BL-676), a conferência não separa "fica de fora": a efetivação é tudo
    ou nada, e o que impede aparece no veredito e na própria linha.
    """
    if importacao.estado == EstadoImportacaoLancamentos.EFETIVADA:
        return importacao.lancamentos.filter(lancamento__isnull=True)
    return importacao.lancamentos.none()


def _contexto_da_conferencia(
    request, empresa, importacao, *, filtro, numero_da_pagina, erros=None, bloqueios=None
):
    em_conferencia = importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    pode_escriturar = _pode_escriturar(request)
    pode_agir = em_conferencia and pode_escriturar
    contagens = _contagens_da_conferencia(importacao)
    tudo = _veredito_da_efetivacao(importacao, contagens)
    codigos = _codigos_sem_conta(importacao) if em_conferencia else []
    # A lista de contas só é montada onde há de-para a fazer: é o único uso dela.
    contas_analiticas = (
        list(
            Conta.objects.filter(empresa=empresa, aceita_lancamento=True, ativo=True)
            .order_by("codigo")
            .values_list("codigo", "nome")
        )
        if pode_agir and codigos
        else []
    )
    pagina = _lancamentos_da_pagina(importacao, filtro, numero_da_pagina)
    fora = _lancamentos_que_ficam_de_fora(importacao)
    querystring = request.GET.copy()
    querystring.pop("pagina", None)
    return {
        "empresa": empresa,
        "importacao": importacao,
        "formato_rotulo": importacao.get_formato_display(),
        "estado_rotulo": importacao.get_estado_display(),
        "em_conferencia": em_conferencia,
        "efetivada": importacao.estado == EstadoImportacaoLancamentos.EFETIVADA,
        "descartada": importacao.estado == EstadoImportacaoLancamentos.DESCARTADA,
        "pode_escriturar": pode_escriturar,
        "pode_agir": pode_agir,
        "contagens": contagens,
        "tudo_ou_nada": tudo,
        "politica_tudo_ou_nada": importacao_servico.TUDO_OU_NADA,
        "politica_rotulo": POLITICAS_DE_EFETIVACAO_NA_TELA.get(
            importacao.politica_de_efetivacao, ""
        ),
        "soma_debitos_ptbr": _valor_ptbr(importacao.soma_debitos),
        "soma_creditos_ptbr": _valor_ptbr(importacao.soma_creditos),
        "conferem": importacao.soma_debitos == importacao.soma_creditos,
        "ocorrencias_do_arquivo": [
            _ocorrencia_na_tela(o) for o in importacao.ocorrencias_do_arquivo
        ],
        "ocorrencias_do_arquivo_total": importacao.quantidade_ocorrencias_do_arquivo,
        "ocorrencias_do_arquivo_guardadas": len(importacao.ocorrencias_do_arquivo),
        "aceite_do_arquivo_pendente": importacao.exige_aceite_do_arquivo
        and not importacao.aceite_do_arquivo,
        "texto_efetivados": _contado(
            importacao.quantidade_efetivados, "lançamento gravado", "lançamentos gravados"
        ),
        "soma_debitos_efetivados_ptbr": _valor_ptbr(importacao.soma_debitos_efetivados),
        "soma_creditos_efetivados_ptbr": _valor_ptbr(importacao.soma_creditos_efetivados),
        "codigos_sem_conta": codigos,
        "contas_analiticas": contas_analiticas,
        "filtros": FILTROS_DA_CONFERENCIA,
        "filtro": filtro,
        "lancamentos": [
            _lancamento_na_tela(lancamento, importacao) for lancamento in pagina.object_list
        ],
        "pagina": pagina,
        "querystring_sem_pagina": querystring.urlencode(),
        "ficam_de_fora": [
            {
                "numero": lancamento.numero_origem,
                "linha": lancamento.linha,
                "motivo": _situacao_na_tela(lancamento, importacao),
            }
            for lancamento in fora[:LIMITE_DE_LANCAMENTOS_FORA_NA_TELA]
        ],
        "ficam_de_fora_total": fora.count(),
        "limite_de_fora": LIMITE_DE_LANCAMENTOS_FORA_NA_TELA,
        "bloqueios": [_bloqueio_na_tela(b) for b in (bloqueios or [])],
        "erros": erros or {},
    }


def _renderizar_conferencia(
    request,
    empresa,
    importacao,
    *,
    filtro="todos",
    numero_da_pagina=1,
    erros=None,
    bloqueios=None,
    status=200,
):
    contexto = _contexto_da_conferencia(
        request,
        empresa,
        importacao,
        filtro=filtro,
        numero_da_pagina=numero_da_pagina,
        erros=erros,
        bloqueios=bloqueios,
    )
    return render(request, "contabilidade/lancamentos_importacao.html", contexto, status=status)


# Exceções do serviço que a conferência traduz em mensagem na própria tela (nunca 500).
_RECUSAS_DA_CONFERENCIA = (
    IntercambioRecusado,
    LancamentoInvalido,
    CompetenciaEncerrada,
    CompetenciaOperacaoRecusada,
)


def _recusa_da_conferencia(request, empresa, importacao, exc):
    """Mostra a recusa do serviço na conferência. 409 é estado ou período; o resto é entrada (400).

    `refresh_from_db` porque a transação do serviço já foi desfeita: a tela mostra o que ficou
    gravado, não o que a ação tentou gravar.
    """
    importacao.refresh_from_db()
    de_estado = isinstance(
        exc,
        (
            importacao_servico.ImportacaoEmEstadoInvalido,
            CompetenciaEncerrada,
            CompetenciaOperacaoRecusada,
        ),
    )
    mensagem = exc.mensagem if isinstance(exc, IntercambioRecusado) else str(exc)
    return _renderizar_conferencia(
        request,
        empresa,
        importacao,
        erros={"geral": mensagem},
        bloqueios=getattr(exc, "ocorrencias", None),
        status=409 if de_estado else 400,
    )


def _redirecionar_para_conferencia(empresa, importacao):
    return redirect(
        "contabilidade_web:lancamentos_importacao",
        empresa_id=empresa.id,
        importacao_id=importacao.id,
    )


def _mensagem_da_efetivacao(resultado):
    gravados = _contado(
        resultado.criados, "lançamento gravado no Diário", "lançamentos gravados no Diário"
    )
    mensagem = f"Efetivada: {gravados}."
    if resultado.reaproveitados:
        mensagem += (
            f" {_contado(resultado.reaproveitados, 'já estava no Diário', 'já estavam no Diário')}."
        )
    if resultado.nao_efetivados:
        mensagem += (
            f" {_contado(len(resultado.nao_efetivados), 'lançamento ficou', 'lançamentos ficaram')}"
            " de fora, como você escolheu."
        )
    return mensagem


# --- Telas --------------------------------------------------------------------------------------


@login_required
@require_safe
def lancamentos_importacoes(request, empresa_id):
    """Lista as importações de lançamentos da empresa, da mais recente para a mais antiga."""
    empresa, recusa = _entrada_das_importacoes(request, empresa_id, escrever=False)
    if recusa is not None:
        return recusa
    importacoes = list(
        importacao_servico.listar_importacoes(empresa)[:LIMITE_DA_LISTA_DE_IMPORTACOES]
    )
    contexto = {
        "empresa": empresa,
        "importacoes": importacoes,
        "limite_da_lista": LIMITE_DA_LISTA_DE_IMPORTACOES,
        "pode_escriturar": _pode_escriturar(request),
    }
    return render(request, "contabilidade/lancamentos_importacoes.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def lancamentos_importar(request, empresa_id):
    """GET: formulário do envio. POST: recebe o arquivo e o deixa EM CONFERÊNCIA.

    Nada entra no Diário aqui. A decisão é da conferência, na tela seguinte.
    """
    empresa, recusa = _entrada_das_importacoes(
        request,
        empresa_id,
        escrever=True,
        mensagem_sem_escrita=MENSAGEM_SEM_PERMISSAO_IMPORTAR_LANCAMENTOS,
    )
    if recusa is not None:
        return recusa
    if request.method == "GET":
        return _renderizar_formulario_de_importacao(request, empresa)

    try:
        recusar_dado_nao_contratado(request, CONTRATO_DO_ENVIO_DE_LANCAMENTOS)
    except DadoNaoContratado as exc:
        return _renderizar_formulario_de_importacao(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    formato = (request.POST.get("formato") or "").strip()
    arquivo = request.FILES.get("arquivo")
    erros = _erros_do_envio(formato, arquivo)
    if erros:
        return _renderizar_formulario_de_importacao(
            request, empresa, formato_escolhido=formato, erros=erros, status=400
        )
    try:
        importacao = importacao_servico.receber(
            empresa=empresa,
            formato=formato,
            conteudo=arquivo.read(),
            nome_arquivo=arquivo.name,
            usuario=request.user,
            request=request,
        )
    except importacao_servico.ImportacaoJaExiste as exc:
        return _renderizar_formulario_de_importacao(
            request,
            empresa,
            formato_escolhido=formato,
            erros={"geral": exc.mensagem},
            existente_id=exc.importacao_id,
            status=409,
        )
    except IntercambioRecusado as exc:
        return _renderizar_formulario_de_importacao(
            request,
            empresa,
            formato_escolhido=formato,
            erros={"geral": exc.mensagem},
            status=400,
        )
    messages.success(
        request,
        "Arquivo recebido em conferência. Nada entrou no Diário: confira os lançamentos abaixo.",
    )
    # R2: registros que a leitura ignorou, contados e não gravados (a prévia do plano mostra igual).
    registros = importacao.registros_ignorados_da_leitura
    if registros:
        texto = ", ".join(
            f"{registro} ({quantidade})" for registro, quantidade in registros.items()
        )
        messages.info(
            request,
            f"Registros do arquivo que o DataLedger não usa (contados, não gravados): {texto}.",
        )
    return _redirecionar_para_conferencia(empresa, importacao)


@login_required
@require_safe
def lancamentos_importar_modelo_excel(request, empresa_id):
    """Baixa o modelo `.xlsx` de lançamentos (mesma permissão do envio, como o modelo do plano)."""
    empresa, recusa = _entrada_das_importacoes(
        request,
        empresa_id,
        escrever=True,
        mensagem_sem_escrita=MENSAGEM_SEM_PERMISSAO_IMPORTAR_LANCAMENTOS,
    )
    if recusa is not None:
        return recusa
    try:
        recusar_campos_nao_contratados(
            request.GET, frozenset(), contexto="no modelo de lançamentos"
        )
    except DadoNaoContratado as exc:
        return _renderizar_formulario_de_importacao(
            request,
            empresa,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    resposta = HttpResponse(excel_lancamentos.gerar_modelo(), content_type=TIPO_DE_CONTEUDO_XLSX)
    resposta["Content-Disposition"] = 'attachment; filename="modelo-lancamentos.xlsx"'
    return resposta


@login_required
@require_safe
def lancamentos_importacao(request, empresa_id, importacao_id):
    """A conferência: resumo, veredito de cada política, de-para, avisos, efetivação e descarte."""
    empresa, recusa = _entrada_das_importacoes(request, empresa_id, escrever=False)
    if recusa is not None:
        return recusa
    importacao = get_object_or_404(ImportacaoLancamentos, pk=importacao_id, empresa=empresa)
    try:
        recusar_campos_nao_contratados(
            request.GET, CAMPOS_DA_CONFERENCIA, contexto="na conferência de lançamentos"
        )
    except DadoNaoContratado as exc:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    filtro = (request.GET.get("filtro") or "todos").strip()
    if filtro not in FILTROS_DA_CONFERENCIA:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"filtro": "Escolha um dos filtros da lista."},
            status=400,
        )
    try:
        numero_da_pagina = max(1, int(request.GET.get("pagina") or 1))
    except ValueError:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"pagina": "A página precisa ser um número inteiro."},
            status=400,
        )
    return _renderizar_conferencia(
        request, empresa, importacao, filtro=filtro, numero_da_pagina=numero_da_pagina
    )


# --- Ações (só POST; cada uma chama o serviço e volta para a conferência) -----------------------


@login_required
@require_http_methods(["POST"])
def lancamentos_importacao_depara(request, empresa_id, importacao_id):
    """Grava o de-para de um código de origem e refaz a conferência, na MESMA transação."""
    empresa, importacao, recusa = _acao_sobre_importacao(request, empresa_id, importacao_id)
    if recusa is not None:
        return recusa
    try:
        recusar_dado_nao_contratado(request, CONTRATO_DO_DEPARA_DA_IMPORTACAO)
    except DadoNaoContratado as exc:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    codigo = (request.POST.get("codigo_origem") or "").strip()
    conta_codigo = (request.POST.get("conta") or "").strip()
    # A escolha vem da lista de contas analíticas ativas que a própria tela ofereceu. O serviço
    # confere a conta (empresa); a lista é a forma de escolher, não uma regra nova.
    conta = (
        Conta.objects.filter(
            empresa=empresa, codigo=conta_codigo, aceita_lancamento=True, ativo=True
        ).first()
        if conta_codigo
        else None
    )
    if conta is None:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={
                "geral": (
                    f"Escolha da lista uma conta analítica ativa desta empresa para o código "
                    f"'{codigo}'. Nada foi gravado."
                )
            },
            status=400,
        )
    try:
        with transaction.atomic():
            importacao_servico.definir_de_para(
                empresa=empresa,
                formato=importacao.formato,
                codigo_origem=codigo,
                conta=conta,
                usuario=request.user,
                request=request,
            )
            atual = importacao_servico.reconferir(importacao, usuario=request.user, request=request)
    except _RECUSAS_DA_CONFERENCIA as exc:
        return _recusa_da_conferencia(request, empresa, importacao, exc)
    messages.success(
        request,
        f"De-para salvo: {codigo} → {conta.codigo}. A conferência foi refeita: "
        f"{_contado(atual.quantidade_com_erro, 'lançamento com erro', 'lançamentos com erro')}.",
    )
    return _redirecionar_para_conferencia(empresa, importacao)


@login_required
@require_http_methods(["POST"])
def lancamentos_importacao_avisos(request, empresa_id, importacao_id):
    """Aceita os avisos de lançamentos escolhidos, ou de todos os que têm aviso por aceitar."""
    empresa, importacao, recusa = _acao_sobre_importacao(request, empresa_id, importacao_id)
    if recusa is not None:
        return recusa
    try:
        recusar_dado_nao_contratado(request, CONTRATO_DOS_AVISOS_DA_IMPORTACAO)
    except DadoNaoContratado as exc:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    aceitar_arquivo = bool(request.POST.get("aceitar_arquivo"))
    if request.POST.get("todos"):
        numeros = list(
            importacao.lancamentos.filter(tem_aviso=True, aceito_com_aviso=False).values_list(
                "numero_origem", flat=True
            )
        )
        if not numeros and not aceitar_arquivo:
            if importacao.estado != EstadoImportacaoLancamentos.EM_CONFERENCIA:
                # Fora da conferência a resposta é o estado, e não "nada a aceitar".
                return _renderizar_conferencia(
                    request,
                    empresa,
                    importacao,
                    erros={
                        "geral": (
                            f"A importação já está {importacao.get_estado_display().lower()}: "
                            "nada foi alterado."
                        )
                    },
                    status=409,
                )
            messages.info(request, "Não há avisos a aceitar: todos já foram aceitos.")
            return redirect(
                "contabilidade_web:lancamentos_importacao",
                empresa_id=empresa.id,
                importacao_id=importacao.id,
            )
    else:
        numeros = request.POST.getlist("numeros")
    try:
        quantidade = importacao_servico.aceitar_avisos(
            importacao,
            numeros,
            aceitar_arquivo=aceitar_arquivo,
            usuario=request.user,
            request=request,
        )
    except _RECUSAS_DA_CONFERENCIA as exc:
        return _recusa_da_conferencia(request, empresa, importacao, exc)
    partes = []
    if quantidade:
        partes.append(f"Avisos aceitos em {_contado(quantidade, 'lançamento', 'lançamentos')}")
    if aceitar_arquivo:
        partes.append("aceite do arquivo registrado: ele é desta empresa")
    messages.success(request, "; ".join(partes) + ". Efetive quando a conferência estiver pronta.")
    return _redirecionar_para_conferencia(empresa, importacao)


@login_required
@require_http_methods(["POST"])
def lancamentos_importacao_reconferir(request, empresa_id, importacao_id):
    """Refaz a conferência com o cadastro de agora (de-para, competências, contas)."""
    empresa, importacao, recusa = _acao_sobre_importacao(request, empresa_id, importacao_id)
    if recusa is not None:
        return recusa
    try:
        recusar_dado_nao_contratado(request, CONTRATO_DA_RECONFERENCIA)
    except DadoNaoContratado as exc:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    try:
        atual = importacao_servico.reconferir(importacao, usuario=request.user, request=request)
    except _RECUSAS_DA_CONFERENCIA as exc:
        return _recusa_da_conferencia(request, empresa, importacao, exc)
    messages.success(
        request,
        "Conferência refeita: "
        f"{_contado(atual.quantidade_lancamentos, 'lançamento', 'lançamentos')}, "
        f"{_contado(atual.quantidade_com_erro, 'com erro', 'com erro')}, "
        f"{_contado(atual.quantidade_com_aviso, 'com aviso', 'com aviso')}.",
    )
    return _redirecionar_para_conferencia(empresa, importacao)


@login_required
@require_http_methods(["POST"])
def lancamentos_importacao_efetivar(request, empresa_id, importacao_id):
    """Grava no Diário (tudo ou nada), depois de confirmação explícita.

    Nada é gravado com erro. A efetivação parcial está suspensa (BL-676): se a política pedida for
    outra, o serviço recusa com a mensagem nomeada, e a recusa volta para esta tela.
    """
    empresa, importacao, recusa = _acao_sobre_importacao(request, empresa_id, importacao_id)
    if recusa is not None:
        return recusa
    try:
        recusar_dado_nao_contratado(request, CONTRATO_DA_EFETIVACAO_DA_IMPORTACAO)
    except DadoNaoContratado as exc:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    politica = (request.POST.get("politica") or importacao_servico.TUDO_OU_NADA).strip()
    if not request.POST.get("confirmar"):
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"confirmar": MENSAGEM_CONFIRMACAO_DA_EFETIVACAO},
            status=400,
        )
    try:
        resultado = importacao_servico.efetivar(
            importacao, politica=politica, usuario=request.user, request=request
        )
    except _RECUSAS_DA_CONFERENCIA as exc:
        return _recusa_da_conferencia(request, empresa, importacao, exc)
    messages.success(request, _mensagem_da_efetivacao(resultado))
    return _redirecionar_para_conferencia(empresa, importacao)


@login_required
@require_http_methods(["POST"])
def lancamentos_importacao_descartar(request, empresa_id, importacao_id):
    """Descarta a importação em conferência, com motivo. O arquivo pode ser recebido de novo."""
    empresa, importacao, recusa = _acao_sobre_importacao(request, empresa_id, importacao_id)
    if recusa is not None:
        return recusa
    try:
        recusar_dado_nao_contratado(request, CONTRATO_DO_DESCARTE_DA_IMPORTACAO)
    except DadoNaoContratado as exc:
        return _renderizar_conferencia(
            request,
            empresa,
            importacao,
            erros={"geral": _mensagem_de_tela_para_dado_nao_contratado(exc)},
            status=400,
        )
    try:
        importacao_servico.descartar(
            importacao,
            motivo=request.POST.get("motivo"),
            usuario=request.user,
            request=request,
        )
    except _RECUSAS_DA_CONFERENCIA as exc:
        return _recusa_da_conferencia(request, empresa, importacao, exc)
    messages.success(
        request,
        "Importação descartada. Nada entrou no Diário, e o arquivo pode ser recebido de novo.",
    )
    return redirect("contabilidade_web:lancamentos_importacoes", empresa_id=empresa.id)
