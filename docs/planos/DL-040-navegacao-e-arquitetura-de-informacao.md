# DL-040 — Navegação e arquitetura de informação

**Demanda:** Fred, 26/09/2026: *"a estrutura atual está confusa, o que dificulta
bastante a usabilidade e a navegação"*. Pediu a contagem exata de telas, a
identificação de duplicadas e obsoletas, a reorganização por módulos, menu
principal fixo com submenus e indicação do item ativo, trilha de navegação e
"Voltar", padrão de títulos e botões, e melhor uso do espaço.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 2** — o que o contador usa. Permissões e isolamento continuam
no servidor e não mudam. **Branch:** worktree isolada do `especialista-frontend`,
integrada em `claude/vigilant-bardeen-jo12l4` depois de o Fred ver as capturas.

## Entregas e critérios de aceite

1. **Mapa de telas** em `docs/projeto/mapa-de-telas.md`: toda tela web, com
   rota, arquétipo, ativa ou secundária, papel e de onde se chega; totais exatos;
   duplicadas, obsoletas e unificáveis **recomendadas**, sem remover rota.
2. **Menu principal** em toda tela autenticada, com submenus sem JavaScript
   obrigatório, item e módulo ativos marcados (`aria-current` e visual que não
   dependa só de cor); itens por papel, usando as mesmas funções de permissão do
   servidor.
3. **Seletor de empresa** visível, sem estado novo em sessão; empresa de outro
   escritório dá 404.
4. **Trilha de navegação** e "Voltar" em posição padrão nas telas secundárias.
5. **Padrão de cabeçalho de página e de botões** (primário, secundário,
   perigoso), registrado como seção nova da
   [direção de arte](../projeto/direcao-de-arte.md).
6. Lateral ou superior decidido por **medição** da densidade das telas de tabela
   a 1280 e 1440 px; recomendação de partida do arquiteto: superior.
7. Nada de navegação no documento impresso; job de identificação do emitente
   continua verde.
8. Celular (390 px) sem transbordo do cabeçalho; suítes de interface e
   acessibilidade verdes sem enfraquecer guarda.

Reversão: revert do commit de interface; nenhum dado ou migração.
