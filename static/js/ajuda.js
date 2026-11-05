(() => {
  const launcher = document.getElementById('help-launcher');
  const panel = document.getElementById('help-panel');
  const closeButton = document.getElementById('help-close');
  const backdrop = document.getElementById('help-backdrop');
  const searchInput = document.getElementById('help-search-input');
  const searchClear = document.getElementById('help-search-clear');
  const categorySelect = document.getElementById('help-category-select');
  const resultsCount = document.getElementById('help-results-count');
  const contextSection = document.getElementById('help-context');
  const contextList = document.getElementById('help-context-list');
  const results = document.getElementById('help-results');
  const resultsTitle = document.getElementById('help-results-title');
  const pageLabel = document.getElementById('help-page-label');
  if (!launcher || !panel || !searchInput || !results) return;

  let artigos = [];
  let contexto = [];
  let categorias = [];
  let categoriaAtiva = '';
  let buscaTimer = null;
  let requestSequence = 0;
  let requestController = null;
  let escopoAtual = null;
  let mostrarTodos = false;

  function limparConteudo() {
    artigos = []; contexto = []; categorias = []; categoriaAtiva = ''; mostrarTodos = false;
    contextSection.hidden = true; contextList.replaceChildren(); results.replaceChildren();
    if (resultsCount) resultsCount.textContent = '';
    if (categorySelect) categorySelect.replaceChildren(new Option('Todos os tópicos', ''));
  }

  function invalidarAjuda() {
    ++requestSequence;
    requestController?.abort();
    if (buscaTimer) window.clearTimeout(buscaTimer);
    limparConteudo();
  }

  function contextoAtivo() {
    const seletor = [
      '.rg-tab.active', '.ovi-tab.active', '.esporo-tab-btn.active', '.acoes-tab.active',
      '.module-tab-btn.active', '.tab-btn.active', '.tab-button.active',
      '[role="tab"][aria-selected="true"]',
    ].join(',');
    const ativos = Array.from(document.querySelectorAll(seletor))
      .filter(elemento => elemento.offsetParent !== null)
      .map(elemento => elemento.textContent?.trim())
      .filter(Boolean);
    return [...new Set(ativos)].join(' > ');
  }

  function atualizarRotuloPagina() {
    const title = document.querySelector('.topbar-brand-txt .t1')?.textContent?.trim();
    const contextoAtual = contextoAtivo();
    if (title) pageLabel.textContent = `Ajuda para: ${title}${contextoAtual ? ` - ${contextoAtual}` : ''}`;
  }

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  function artigoHtml(artigo) {
    const passos = (artigo.passos || []).map(passo => `<li>${escapeHtml(passo)}</li>`).join('');
    const atencao = (artigo.atencao || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
    return `<article class="help-article" data-help-id="${escapeHtml(artigo.id)}">
      <button type="button" class="help-article-toggle" aria-expanded="false">
        <span class="help-article-heading">
          <span class="help-article-title">${escapeHtml(artigo.titulo)}</span>
          <span class="help-article-category">${escapeHtml(artigo.categoria)}</span>
        </span>
        <span class="help-article-chevron" aria-hidden="true">›</span>
      </button>
      <div class="help-article-body">
        <p>${escapeHtml(artigo.resumo)}</p>
        ${passos ? `<ol>${passos}</ol>` : ''}
        ${atencao ? `<div class="help-article-warn"><strong>Atenção</strong><ul>${atencao}</ul></div>` : ''}
        ${artigo.link ? `<a class="help-article-link" href="${escapeHtml(artigo.link)}">${escapeHtml(artigo.link_label || 'Abrir página')}</a>` : ''}
      </div>
    </article>`;
  }

  function artigosFiltrados(lista) {
    if (!categoriaAtiva) return lista;
    return lista.filter(artigo => artigo.categoria === categoriaAtiva);
  }

  function renderCategorias() {
    if (!categorySelect) return;
    categorySelect.innerHTML = '<option value="">Todos os tópicos</option>' + categorias.map(item => (
      `<option value="${escapeHtml(item.nome)}">${escapeHtml(item.nome)} (${Number(item.total || 0)})</option>`
    )).join('');
    const disponivel = Array.from(categorySelect.options).some(option => option.value === categoriaAtiva);
    if (!disponivel) categoriaAtiva = '';
    categorySelect.value = categoriaAtiva;
  }

  function renderArtigos() {
    const contextuais = artigosFiltrados(contexto);
    const contextIds = new Set(contextuais.map(artigo => artigo.id));
    const disponiveis = artigosFiltrados(artigos).filter(artigo => searchInput.value.trim() || !contextIds.has(artigo.id));
    const lista = !mostrarTodos && !categoriaAtiva && !searchInput.value.trim() ? disponiveis.slice(0, 6) : disponiveis;
    contextSection.hidden = contextuais.length === 0 || Boolean(searchInput.value.trim());
    contextList.innerHTML = contextuais.map(artigoHtml).join('');
    resultsTitle.textContent = searchInput.value.trim()
      ? 'Resultados da busca'
      : (categoriaAtiva || (contextuais.length ? 'Outros tópicos' : 'Todos os tópicos'));
    results.innerHTML = lista.length
      ? lista.map(artigoHtml).join('')
      : '<div class="help-empty">Nenhum tópico corresponde à busca.</div>';
    if (lista.length < disponiveis.length) {
      const more = document.createElement('button'); more.type = 'button'; more.className = 'btn btn-ghost';
      more.dataset.helpShowAll = 'true'; more.textContent = 'Mostrar os demais tópicos'; results.append(more);
    }
    const totalVisivel = lista.length + (contextSection.hidden ? 0 : contextuais.length);
    if (resultsCount) resultsCount.textContent = `${totalVisivel} ${totalVisivel === 1 ? 'tópico' : 'tópicos'}`;
  }

  function abrirArtigo(button) {
    const article = button.closest('.help-article');
    if (!article) return;
    panel.querySelectorAll('.help-article.open').forEach(aberto => {
      if (aberto === article) return;
      aberto.classList.remove('open');
      aberto.querySelector('.help-article-toggle')?.setAttribute('aria-expanded', 'false');
    });
    const aberto = article.classList.toggle('open');
    button.setAttribute('aria-expanded', aberto ? 'true' : 'false');
  }

  async function carregarAjuda() {
    const sequence = ++requestSequence;
    requestController?.abort();
    requestController = new AbortController();
    const savedCategory = categoriaAtiva;
    limparConteudo(); categoriaAtiva = savedCategory;
    results.innerHTML = '<div class="help-empty">Carregando orientações...</div>';
    const params = new URLSearchParams({
      rota: window.location.pathname,
      q: searchInput.value.trim(),
      contexto: contextoAtivo(),
      limite: '120',
    });
    try {
      const response = await fetch(`/api/ajuda?${params.toString()}`, {
        cache: 'no-store', credentials: 'same-origin', redirect: 'error', signal: requestController.signal,
      });
      if (!response.ok) throw new Error('Falha ao carregar ajuda');
      const payload = await response.json();
      if (sequence !== requestSequence) return;
      if (escopoAtual && escopoAtual !== payload.escopo) {
        escopoAtual = payload.escopo; searchInput.value = ''; categoriaAtiva = '';
        if (searchClear) searchClear.hidden = true;
        return carregarAjuda();
      }
      escopoAtual = payload.escopo;
      artigos = payload.artigos || [];
      contexto = payload.contexto || [];
      categorias = payload.categorias || [];
      atualizarRotuloPagina();
      renderCategorias();
      renderArtigos();
    } catch (error) {
      if (sequence !== requestSequence) return;
      limparConteudo();
      contextSection.hidden = true;
      resultsTitle.textContent = 'Tópicos de ajuda';
      results.innerHTML = '<div class="help-empty">A ajuda não pôde ser carregada. Confira se sua sessão continua ativa.</div>';
      if (resultsCount) resultsCount.textContent = '';
    }
  }

  function abrirAjuda() {
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    launcher.setAttribute('aria-expanded', 'true');
    backdrop.hidden = false;
    results.innerHTML = '<div class="help-empty">Carregando orientações...</div>';
    carregarAjuda().then(() => searchInput.focus());
  }

  function fecharAjuda() {
    invalidarAjuda();
    panel.classList.remove('open');
    panel.setAttribute('aria-hidden', 'true');
    launcher.setAttribute('aria-expanded', 'false');
    backdrop.hidden = true;
    launcher.focus();
  }

  launcher.addEventListener('click', () => {
    if (panel.classList.contains('open')) fecharAjuda();
    else abrirAjuda();
  });
  closeButton?.addEventListener('click', fecharAjuda);
  backdrop?.addEventListener('click', fecharAjuda);
  searchInput.addEventListener('input', () => {
    invalidarAjuda();
    if (searchClear) searchClear.hidden = !searchInput.value;
    if (buscaTimer) window.clearTimeout(buscaTimer);
    buscaTimer = window.setTimeout(carregarAjuda, 180);
  });
  searchClear?.addEventListener('click', () => {
    searchInput.value = '';
    searchClear.hidden = true;
    carregarAjuda().then(() => searchInput.focus());
  });
  categorySelect?.addEventListener('change', () => {
    categoriaAtiva = categorySelect.value || '';
    mostrarTodos = false;
    renderArtigos();
  });
  panel.addEventListener('click', event => {
    if (event.target.closest('[data-help-show-all]')) { mostrarTodos = true; renderArtigos(); return; }
    const button = event.target.closest('.help-article-toggle');
    if (button) abrirArtigo(button);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && panel.classList.contains('open')) fecharAjuda();
  });
  document.addEventListener('click', event => {
    if (!panel.classList.contains('open')) return;
    if (!event.target.closest('.rg-tab, .ovi-tab, .esporo-tab-btn, .acoes-tab, .module-tab-btn, .tab-btn, .tab-button, [role="tab"]')) return;
    window.setTimeout(carregarAjuda, 0);
  });
  window.addEventListener('hashchange', () => {
    if (panel.classList.contains('open')) carregarAjuda();
  });
  window.addEventListener('pagehide', invalidarAjuda);
  window.addEventListener('pageshow', () => {
    invalidarAjuda();
    if (panel.classList.contains('open')) carregarAjuda();
  });
  window.addEventListener('focus', () => {
    if (panel.classList.contains('open')) carregarAjuda();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) invalidarAjuda();
    else if (panel.classList.contains('open')) carregarAjuda();
  });

  atualizarRotuloPagina();
})();
