"""Enumerações compartilhadas do módulo `apps.documentos`.

Este módulo existe para que a enumeração de **classe de documento** tenha
um endereço canônico, do mesmo jeito que `RegimeTributario` mora em
`apps.empresas.models` e `Papel` mora em `apps.tenancy.models`. A escolha
de colocá-la em **módulo próprio** (não dentro de `models.py`) é
deliberada: a enum precisa ser importada por:

  - `apps.documentos.models` (campo `classe` do modelo `Documento`).
  - `apps.documentos.identificacao` (função pura que devolve o bloco
    obrigatório por classe).
  - Varredura de templates (a guarda do DL-027 critério 1 declara que
    todo documento imprimível **declara** a classe — a enum é o que
    precisa estar declarado).
  - Futuras views que emitam documentos (`views.py` da fatia B).

Se a enum morasse em `models.py`, qualquer um dos importadores acima
puxaria o módulo Django inteiro — incluindo todos os models, signals e
migrações — só para ler três strings. Módulo separado, só com a
`TextChoices`, é o que mantém o custo de cada importador no mínimo
necessário.
"""

from __future__ import annotations

from django.db import models


class ClasseDocumento(models.TextChoices):
    """Classe do documento imprimível — três valores, fixados pela
    `HI-11` do `docs/projeto/requisitos.md`.

    A enum é o vocabulário **mínimo** que toda tela de impressão do
    sistema precisa declarar. Sem ela, o sistema não pode distinguir um
    balancete de verificação de um balanço, e a personalização que cabe
    num estraga o outro (HI-11, `personalizacao-de-relatorio.md` §1).

    Os **valores** são `slug` em minúsculas, estáveis, usados como texto
    gravado. Os **labels** são o texto humano que vai para a interface.
    """

    CONFERENCIA = "conferencia", "Conferência"
    DEMONSTRACAO = "demonstracao", "Demonstração"
    LIVRO = "livro", "Livro"
