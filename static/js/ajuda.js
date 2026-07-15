(() => {
  const launcher = document.getElementById('help-launcher');
  const panel = document.getElementById('help-panel');
  const closeButton = document.getElementById('help-close');
  const backdrop = document.getElementById('help-backdrop');
  const searchInput = document.getElementById('help-search-input');
  const categories = document.getElementById('help-categories');
  const contextSection = document.getElementById('help-context');
  const contextList = document.getElementById('help-context-list');
  const results = document.getElementById('help-results');
  const resultsTitle = document.getElementById('help-results-title');
  const pageLabel = document.getElementById('help-page-label');
  if (!launcher || !panel || !searchInput || !results) return;

  let artigos = [];
  let contexto = [];
  let categoriaAtiva = '';
  let buscaTimer = null;

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));

  function artigoHtml(artigo) {
    const passos = (artigo.passos || []).map(passo => `<li>${escapeHtml(passo)}</li>`).join('');
    return `<article class="help-article" data-help-id="${escapeHtml(artigo.id)}">
      <button type="button" class="help-article-toggle" aria-expanded="false">
        <span class="help-article-title">${escapeHtml(artigo.titulo)}</span>
        <span class="help-article-category">${escapeHtml(artigo.categoria)}</span>
      </button>
      <div class="help-article-body">
        <p>${escapeHtml(artigo.resumo)}</p>
        ${passos ? `<ol>${passos}</ol>` : ''}
        ${artigo.link ? `<a class="help-article-link" href="${escapeHtml(artigo.link)}">${escapeHtml(artigo.link_label || 'Abrir página')}</a>` : ''}
      </div>
    </article>`;
  }

  function artigosFiltrados(lista) {
    if (!categoriaAtiva) return lista;
    return lista.filter(artigo => artigo.categoria === categoriaAtiva);
  }

  function renderCategorias() {
    if (!categories) return;
    const nomes = [...new Set(artigos.map(artigo => artigo.categoria))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
    categories.innerHTML = ['Todas', ...nomes].map(nome => {
      const ativa = (nome === 'Todas' && !categoriaAtiva) || nome === categoriaAtiva;
      return `<button type="button" class="help-category ${ativa ? 'active' : ''}" data-category="${escapeHtml(nome === 'Todas' ? '' : nome)}">${escapeHtml(nome)}</button>`;
    }).join('');
  }

  function renderArtigos() {
    const contextuais = artigosFiltrados(contexto);
    const contextIds = new Set(contextuais.map(artigo => artigo.id));
    const lista = artigosFiltrados(artigos).filter(artigo => searchInput.value.trim() || !contextIds.has(artigo.id));
    contextSection.hidden = contextuais.length === 0 || Boolean(searchInput.value.trim());
    contextList.innerHTML = contextuais.map(artigoHtml).join('');
    resultsTitle.textContent = searchInput.value.trim() ? 'Resultados da busca' : 'Outros tópicos';
    results.innerHTML = lista.length
      ? lista.map(artigoHtml).join('')
      : '<div class="help-empty">Nenhum tópico corresponde à busca.</div>';
  }

  function abrirArtigo(button) {
    const article = button.closest('.help-article');
    if (!article) return;
    const aberto = article.classList.toggle('open');
    button.setAttribute('aria-expanded', aberto ? 'true' : 'false');
  }

  async function carregarAjuda() {
    const params = new URLSearchParams({
      rota: window.location.pathname,
      q: searchInput.value.trim(),
      limite: '20',
    });
    try {
      const response = await fetch(`/api/ajuda?${params.toString()}`);
      if (!response.ok) throw new Error('Falha ao carregar ajuda');
      const payload = await response.json();
      artigos = payload.artigos || [];
      contexto = payload.contexto || [];
      renderCategorias();
      renderArtigos();
    } catch (error) {
      contextSection.hidden = true;
      resultsTitle.textContent = 'Tópicos de ajuda';
      results.innerHTML = '<div class="help-empty">A ajuda não pôde ser carregada agora.</div>';
    }
  }

  function abrirAjuda() {
    panel.classList.add('open');
    panel.setAttribute('aria-hidden', 'false');
    launcher.setAttribute('aria-expanded', 'true');
    backdrop.hidden = false;
    carregarAjuda().then(() => searchInput.focus());
  }

  function fecharAjuda() {
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
    if (buscaTimer) window.clearTimeout(buscaTimer);
    buscaTimer = window.setTimeout(carregarAjuda, 180);
  });
  categories?.addEventListener('click', event => {
    const button = event.target.closest('[data-category]');
    if (!button) return;
    categoriaAtiva = button.dataset.category || '';
    renderCategorias();
    renderArtigos();
  });
  panel.addEventListener('click', event => {
    const button = event.target.closest('.help-article-toggle');
    if (button) abrirArtigo(button);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && panel.classList.contains('open')) fecharAjuda();
  });

  const title = document.querySelector('.topbar-brand-txt .t1')?.textContent?.trim();
  if (title) pageLabel.textContent = `Ajuda para: ${title}`;
})();
