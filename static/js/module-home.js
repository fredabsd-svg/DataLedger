/* DL-049: progressive enhancement only. GETs and every authorization stay
 * on the server; no dataset, total or business state is invented here. */
'use strict';
(() => {
    const home = document.querySelector('[data-module-home]');
    if (!home) return;
    const form = home.querySelector('[data-home-filters]');
    const select = form?.querySelector('[data-home-company]');
    const search = form?.querySelector('[data-home-company-search]');
    const group = form?.querySelector('[data-home-group]');
    const announcement = home.querySelector('[data-home-announcement]');
    const loader = home.querySelector('[data-home-loading]');

    const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
    search?.addEventListener('input', () => {
        const term = normalize(search.value.trim());
        [...select.options].forEach(option => {
            // Never hide the selected company, change scope or select a
            // different customer as a side effect of typing a search.
            option.hidden = !['todas', 'grupo'].includes(option.value) &&
                !option.selected && !normalize(option.textContent).includes(term);
        });
    });
    select?.addEventListener('change', () => {
        if (select.value === 'grupo' && group) group.open = true;
    });
    form?.addEventListener('submit', () => {
        // Removing disabled group inputs keeps a single-company query
        // unambiguous. Native GET remains usable without this script.
        if (select.value !== 'grupo') {
            form.querySelectorAll('input[name="empresas"]').forEach(input => { input.disabled = true; });
        }
        home.setAttribute('aria-busy', 'true');
        if (loader) loader.hidden = false;
        if (announcement) announcement.textContent = 'Atualizando dados. A empresa e a competência serão verificadas no servidor.';
        form.querySelector('button[type="submit"]').disabled = true;
    });
    window.addEventListener('pageshow', () => {
        // bfcache restores DOM properties too: re-enable the form after
        // Back/Forward so repeated daily navigation never gets stuck.
        home.removeAttribute('aria-busy');
        if (loader) loader.hidden = true;
        form?.querySelectorAll('input[name="empresas"]').forEach(input => { input.disabled = false; });
        const submit = form?.querySelector('button[type="submit"]');
        if (submit) submit.disabled = false;
    });
    requestAnimationFrame(() => {
        if (!announcement) return;
        const unavailableStates = {
            sem_permissao: 'Seu perfil não permite consultar este módulo. Os dados não foram apurados.',
            indisponivel: 'Este módulo ainda não está disponível. Não há apuração de pendências.',
            inaplicavel: 'Esta seleção não se aplica ao módulo. O escopo foi preservado.',
            sem_empresas: 'Nenhuma empresa aplicável no módulo. Não há dados para apurar.',
            filtro_invalido: 'Não foi possível aplicar os filtros. Revise a seleção.',
        };
        const unavailable = unavailableStates[home.dataset.state];
        if (unavailable) announcement.textContent = `${home.dataset.context}. ${unavailable}`;
        else if (home.dataset.total !== undefined && home.dataset.total !== '') {
            announcement.textContent = `${home.dataset.context}. ${home.dataset.total} ${home.dataset.total === '1' ? 'registro apurado' : 'registros apurados'} na lista.`;
        } else announcement.textContent = `${home.dataset.context}. Consulte o estado da apuração.`;
    });
    document.addEventListener('pointerdown', () => { home.dataset.input = 'pointer'; });
    document.addEventListener('keydown', () => { home.dataset.input = 'keyboard'; }, true);
})();
