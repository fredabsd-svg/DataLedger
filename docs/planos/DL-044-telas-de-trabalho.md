# DL-044 — Telas de trabalho com aspecto de produto profissional

**Demanda:** Fred, 2026-09-26, depois de ver as capturas da DL-042 e da DL-043:

> *"Eu ainda não gostei do layout — a landing page ficou boa, mas o layout da
> tela de trabalho tá com aspecto de vazio e os botões de clicar […] tá
> parecendo um botão de link, tá muito amador, muito cara de sistema mal
> feito. Dê mais uma revisada, pesquisa e modelos da internet."*

**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 2** — interface. Nenhuma regra contábil, cálculo, permissão
ou isolamento muda; os testes existentes de permissão, isolamento e
acessibilidade continuam valendo e não podem ser afrouxados.
**Branch:** `dl044-telas-de-trabalho`, a partir das telas da DL-043
(`06840b1`), integrada depois da DL-043.

## Problema (confirmado pelo Fred)

1. **Aspecto de vazio** nas telas de trabalho (Início, relatórios, formulários,
   fechamento): muito espaço sem função, conteúdo solto na página, sem
   agrupamento visual.
2. **Ação parece link**: a navegação entre relatórios é uma linha de links
   sublinhados; ações secundárias e de tabela não se distinguem de texto.
3. **Aspecto amador** no conjunto.

A página pública (landing) **ficou boa** e não é alvo desta etapa, exceto
pelo que for componente compartilhado.

## Hipóteses de desenho (HI-27, confirmadas pelo Fred em 2026-09-26 — RC-117)

- Tipografia de trabalho sem serifa (auto-hospedada, licença junto, DE-011);
  a serifa fica para marca, títulos da landing e documentos imprimíveis.
- Casca de aplicação com cabeçalho de página (título, contexto, ações à
  direita), conteúdo em superfícies (cartões/painéis) com borda e sombra
  sutil, fundo de trabalho neutro.
- Navegação entre relatórios da empresa **sem linha de links sublinhados**.
  Na primeira iteração virou abas; na quarta, as abas saíram por repetirem o
  menu (DE-081): a navegação é **uma só**, pela barra lateral, com um hub de
  relatórios em cartões.
- Botões com aspecto de botão em todos os tons (preenchido, contorno,
  perigoso, fantasma), com estados de foco, passagem do mouse, pressionado e
  desabilitado; ações de linha de tabela como botões compactos ou menu.
- Início com indicadores (contagens) no topo e listas agrupadas, sem área
  morta.
- Tabelas densas legíveis: cabeçalho fixo, linhas alternadas ou separadores,
  valores tabulados à direita (regra já vigente).

## Critérios de aceite

1. Pesquisa registrada: no mínimo cinco referências públicas de sistemas de
   gestão/contábeis e sistemas de design (URL e data de consulta), com o
   padrão adotado de cada uma — **inspiração de padrão, sem copiar marca,
   texto ou imagem**.
2. `direcao-de-arte.md` atualizado com a decisão (novos tokens, tipografia,
   componentes) e DE registrada em `decisoes.md`.
3. Todas as telas autenticadas passam pela nova casca; nenhuma ação clicável
   com aparência de link sublinhado solto (link de navegação em texto
   corrido é permitido).
4. Capturas antes/depois em 1440×900 e 390×844, com navegador em **pt-BR**
   (datas dd/mm/aaaa), em `docs/assets/telas/dl044/`.
5. Achados das capturas da DL-043 corrigidos: rótulo "Select an option" em
   inglês; barra lateral que termina antes do fim da página.
6. Acessibilidade mantida: contraste AA, foco visível, sem JavaScript
   obrigatório, guardas automatizadas existentes verdes.
7. Suíte completa, `ruff check`, `ruff format --check`, `manage.py check`,
   validação da documentação.
