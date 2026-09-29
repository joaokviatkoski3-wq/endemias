(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const fmt = value => new Intl.NumberFormat('pt-BR').format(Number(value || 0));
  const codigo = value => {
    const raw = String(value ?? '').trim();
    return /^\d+(?:\.0+)?$/.test(raw) ? String(parseInt(raw, 10)).padStart(4, '0') : raw;
  };
  const estado = {iniciado:false, mapa:null, layer:null, geo:null, resumo:null, lista:[], acs:[], selecionados:new Set(), editando:null};
  const cores = ['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2','#be123c','#0f766e'];
  async function json(url, options) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.erro || `Erro HTTP ${resp.status}`);
    return data;
  }
  const status = texto => { el('micro-status').textContent = texto; };
  function ativos() {
    const id = Number(el('micro-localidade').value);
    return estado.geo?.features?.filter(f => Number(f.properties?.Localidade) === id) || [];
  }
  function chave(f) { return codigo(f.properties?.id_quart); }
  function resumoQ(q) {
    const loc = el('micro-localidade').value;
    const display = /^\d+$/.test(q) ? String(parseInt(q, 10)) : q;
    return estado.resumo?.quarteiroes?.[`${loc}:${display}`] || {};
  }
  function proprietario(q) {
    const loc = Number(el('micro-localidade').value);
    return estado.lista.find(r => Number(r.id_localidade) === loc && r.quarteiroes.includes(q));
  }
  const exibirQ = q => /^\d+$/.test(q) ? String(parseInt(q, 10)) : q;
  function filtrarListaQuarteiroes() {
    const busca = el('micro-q-busca').value.trim().toLocaleLowerCase('pt-BR');
    el('micro-q-lista').querySelectorAll('.micro-q-opcao').forEach(opcao => {
      const q = opcao.querySelector('input').value;
      opcao.hidden = !!busca && !q.toLocaleLowerCase('pt-BR').includes(busca)
        && !exibirQ(q).toLocaleLowerCase('pt-BR').includes(busca);
    });
  }
  function renderListaQuarteiroes() {
    const lista = el('micro-q-lista');
    if (!el('micro-localidade').value) {
      lista.innerHTML = '<div class="micro-q-vazio">Selecione uma localidade.</div>';
      return;
    }
    const quarteiroesComGeometria = new Set(ativos().map(chave));
    const quarteiroes = new Set(quarteiroesComGeometria);
    estado.selecionados.forEach(q => quarteiroes.add(q));
    lista.innerHTML = quarteiroes.size ? [...quarteiroes]
      .sort((a,b) => a.localeCompare(b, 'pt-BR', {numeric:true}))
      .map(q => {
        const dono = proprietario(q);
        const ocupado = dono && dono.id_microarea !== estado.editando;
        const semGeometria = !quarteiroesComGeometria.has(q);
        return `<label class="micro-q-opcao"><input type="checkbox" value="${esc(q)}" ${estado.selecionados.has(q) ? 'checked' : ''} ${ocupado ? 'disabled' : ''}>
          <span>Q. ${esc(exibirQ(q))}</span><small>${ocupado ? `Microárea ${esc(dono.numero)}` : semGeometria ? 'Sem geometria' : ''}</small></label>`;
      }).join('') : '<div class="micro-q-vazio">Não há quarteirões nessa localidade.</div>';
    filtrarListaQuarteiroes();
  }
  function atualizarSelecao() {
    estado.layer?.setStyle(estilo);
    el('micro-q-lista').querySelectorAll('input[type="checkbox"]').forEach(input => {
      input.checked = estado.selecionados.has(input.value);
    });
    totais();
  }
  function cor(r) { return cores[(Number(r?.id_microarea || 0) - 1 + cores.length) % cores.length]; }
  function estilo(f) {
    const q = chave(f), dono = proprietario(q), selecionado = estado.selecionados.has(q);
    return {color:selecionado ? '#facc15' : dono ? cor(dono) : '#64748b', weight:selecionado ? 4 : 1.4,
      fillColor:dono ? cor(dono) : '#cbd5e1', fillOpacity:selecionado ? .72 : dono ? .47 : .23};
  }
  function totais() {
    let imoveis = 0, reais = 0, pop = 0;
    for (const q of estado.selecionados) {
      const r = resumoQ(q);
      imoveis += Number(r.imoveis || 0); reais += Number(r.imoveis_reais || 0); pop += Number(r.populacao_aproximada || 0);
    }
    el('micro-total-q').textContent = fmt(estado.selecionados.size);
    el('micro-total-imoveis').textContent = fmt(imoveis);
    el('micro-total-reais').textContent = fmt(reais);
    el('micro-total-pop').textContent = fmt(pop);
    el('micro-selected').innerHTML = estado.selecionados.size
      ? [...estado.selecionados].sort((a,b) => a.localeCompare(b, 'pt-BR', {numeric:true})).map(q => `<span>Q. ${esc(q)}</span>`).join(' · ')
      : 'Nenhum quarteirão selecionado.';
  }
  function renderMapa() {
    if (!estado.mapa) return;
    if (estado.layer) {
      estado.layer.eachLayer(layer => layer.unbindTooltip());
      estado.mapa.removeLayer(estado.layer);
    }
    estado.layer = L.geoJSON({type:'FeatureCollection', features:ativos()}, {
      style:estilo,
      onEachFeature: (f, layer) => {
        const q = chave(f), dono = proprietario(q), r = resumoQ(q);
        if (el('micro-map-labels').checked) layer.bindTooltip(esc(exibirQ(q)), {permanent:true, direction:'center', className:'rg-map-label'});
        layer.bindPopup(`<strong>Quarteirão ${esc(q)}</strong><br>${dono ? `Microárea ${esc(dono.numero)} · ${esc(dono.acs_nome || dono.acs_codigo || 'Sem ACS')}` : 'Sem microárea'}<br>${fmt(r.imoveis)} imóvel(is) RG · ${fmt(r.populacao_aproximada)} hab. aprox.`);
        layer.on('click', () => {
          const tipos = Object.values(r.tipos || {}).sort((a,b) => Number(b.imoveis || 0) - Number(a.imoveis || 0));
          el('micro-detalhe').innerHTML = `<h3>Q. ${esc(q)}</h3>
            <div>${dono ? `Microárea ${esc(dono.numero)} · ACS ${esc(dono.acs_nome || dono.acs_codigo || 'não atribuído')}` : 'Sem microárea'}</div>
            <div>${fmt(r.imoveis)} imóveis RG · ${fmt(r.imoveis_reais)} imóveis reais · ${fmt(r.atualizados)} atualizados</div>
            <div>População aproximada: ${fmt(r.populacao_aproximada)}</div>
            ${tipos.length ? `<div style="margin-top:5px;">${tipos.map(t => `${esc(t.label || t.codigo)}: ${fmt(t.imoveis)}`).join(' · ')}</div>` : '<div>Sem imóveis cadastrados no RG.</div>'}`;
          if (dono && dono.id_microarea !== estado.editando) {
            status(`Quarteirão ${q} pertence à microárea ${dono.numero}. Abra essa microárea na lista para editá-la.`);
            return;
          }
          if (estado.selecionados.has(q)) estado.selecionados.delete(q); else estado.selecionados.add(q);
          el('micro-q-busca').value = '';
          filtrarListaQuarteiroes();
          atualizarSelecao();
          [...el('micro-q-lista').querySelectorAll('input[type="checkbox"]')]
            .find(input => input.value === q)?.scrollIntoView({block:'nearest'});
        });
      }
    }).addTo(estado.mapa);
    if (estado.layer.getBounds().isValid()) estado.mapa.fitBounds(estado.layer.getBounds(), {padding:[15,15]});
    totais();
  }
  function filtrar() {
    const loc = el('micro-filtro-localidade').value;
    const acs = el('micro-filtro-acs').value;
    const busca = el('micro-filtro-busca').value.trim().toLocaleLowerCase('pt-BR');
    return estado.lista.filter(r => (!loc || String(r.id_localidade) === loc)
      && (!acs || (acs === 'sem' ? !r.acs_codigo : r.acs_codigo === acs))
      && (!busca || [r.numero,r.localidade,r.acs_nome,r.acs_codigo,r.observacoes,...r.quarteiroes].some(v => String(v || '').toLocaleLowerCase('pt-BR').includes(busca))));
  }
  function renderLista() {
    const rows = filtrar();
    const porLocalidade = new Map();
    rows.forEach(r => porLocalidade.set(r.localidade, (porLocalidade.get(r.localidade) || 0) + 1));
    el('micro-resumo').textContent = `${fmt(rows.length)} microárea(s) · ${fmt(rows.reduce((n,r) => n + r.quarteiroes.length,0))} quarteirão(ões) · ${fmt(rows.filter(r => !r.acs_codigo).length)} sem ACS · ${[...porLocalidade].map(([nome,n]) => `${nome}: ${n}`).join(' · ')}`;
    el('micro-tabela').innerHTML = rows.length ? rows.map(r => `<tr>
      <td>${esc(r.localidade)}</td><td><strong>${esc(r.numero)}</strong></td>
      <td>${esc(r.acs_nome || r.acs_codigo || 'Sem ACS')}</td>
      <td>${fmt(r.quarteiroes.length)}<div class="rg-muted">${r.quarteiroes.map(q => esc(q)).join(', ')}</div></td>
      <td>${r.quarteiroes_sem_geometria.length ? `<span class="rg-muted">${fmt(r.quarteiroes_sem_geometria.length)} ausente(s): ${r.quarteiroes_sem_geometria.map(esc).join(', ')}</span>` : 'Completa'}</td>
      <td>${esc(r.observacoes || '-')}</td><td><button class="btn btn-outline btn-sm" type="button" data-micro-edit="${Number(r.id_microarea)}">${el('micro-salvar') ? 'Editar / trocar ACS' : 'Ver no mapa'}</button>
      ${el('micro-salvar') ? `<button class="btn btn-ghost btn-sm" type="button" data-micro-delete="${Number(r.id_microarea)}">Excluir</button>` : ''}</td></tr>`).join('')
      : '<tr><td colspan="7">Nenhuma microárea corresponde aos filtros.</td></tr>';
    for (const [formato,id] of [['xlsx','micro-xlsx'],['geojson','micro-geojson'],['kml','micro-kml']]) {
      const link = el(id);
      const p = new URLSearchParams(); rows.forEach(r => p.append('id', r.id_microarea));
      link.href = rows.length ? `/territorializacao/microareas/exportar/${formato}?${p}` : '#';
      link.setAttribute('aria-disabled', rows.length ? 'false' : 'true');
    }
  }
  function renderACS() {
    const options = estado.acs.map(a => `<option value="${esc(a.acs_codigo)}">${esc(a.nome)} (${esc(a.acs_codigo)})</option>`).join('');
    el('micro-acs').innerHTML = '<option value="">Sem ACS</option>' + options;
    el('micro-filtro-acs').innerHTML = '<option value="">Todos</option><option value="sem">Sem ACS</option>' + options;
  }
  async function carregar() {
    const [geo, resumo, lista] = await Promise.all([
      json('/api/registro-geografico/geojson'), json('/api/registro-geografico/mapa-resumo'),
      json('/api/territorializacao/microareas')]);
    estado.geo = geo; estado.resumo = resumo; estado.lista = lista.registros || []; estado.acs = lista.acs || [];
    renderACS(); renderLista(); renderListaQuarteiroes(); renderMapa();
  }
  async function iniciar() {
    if (estado.iniciado) { setTimeout(() => estado.mapa?.invalidateSize(), 100); return; }
    estado.iniciado = true;
    try {
      estado.mapa = L.map('micro-mapa', {zoomControl:true}).setView([-25.33,-49.29], 12);
      const baseMapa = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
        attribution:'Tiles © Esri — Esri, TomTom, Garmin, FAO, NOAA, USGS, © OpenStreetMap contributors, GIS User Community', maxZoom:19
      });
      const baseSatelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution:'© Esri, Earthstar Geographics', maxZoom:19
      });
      const baseSateliteRuas = L.layerGroup([
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          attribution:'© Esri', maxZoom:19
        }),
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
          attribution:'Labels © Esri', maxZoom:19
        })
      ]);
      baseMapa.addTo(estado.mapa);
      L.control.layers({'Mapa':baseMapa, 'Satélite':baseSatelite, 'Satélite + ruas':baseSateliteRuas}, {}, {
        position:'topright', collapsed:false
      }).addTo(estado.mapa);
      await carregar();
    } catch (e) { status(e.message); el('micro-tabela').innerHTML = `<tr><td colspan="7">${esc(e.message)}</td></tr>`; estado.iniciado = false; }
  }
  function aba(nome) {
    document.querySelectorAll('[data-terr-area]').forEach(b => b.classList.toggle('active', b.dataset.terrArea === nome));
    el('terr-area-rg').hidden = nome !== 'rg'; el('terr-area-microareas').hidden = nome !== 'microareas';
    if (nome === 'microareas') iniciar(); else setTimeout(() => {
      if (typeof rgMapState !== 'undefined') rgMapState.map?.invalidateSize();
    }, 100);
  }
  function subAba(nome) {
    document.querySelectorAll('[data-micro-pane]').forEach(b => b.classList.toggle('active', b.dataset.microPane === nome));
    ['mapa','lista'].forEach(p => { el(`micro-pane-${p}`).hidden = p !== nome; });
    if (nome === 'mapa') setTimeout(() => estado.mapa?.invalidateSize(), 100);
    else renderLista();
  }
  function novo() {
    estado.editando = null; estado.selecionados.clear(); el('micro-id').value = '';
    el('micro-numero').value = ''; el('micro-acs').value = ''; el('micro-observacoes').value = '';
    el('micro-cadastro-titulo').textContent = 'Nova microárea';
    if (el('micro-salvar')) el('micro-salvar').textContent = 'Criar microárea';
    status('Nova microárea. Selecione os quarteirões.'); renderListaQuarteiroes(); renderMapa();
  }
  function abrir(id) {
    const r = estado.lista.find(item => item.id_microarea === id);
    if (!r) return;
    aba('microareas'); subAba('mapa');
    el('micro-localidade').value = r.id_localidade;
    estado.editando = r.id_microarea; estado.selecionados = new Set(r.quarteiroes);
    el('micro-id').value = r.id_microarea; el('micro-numero').value = r.numero;
    el('micro-acs').value = r.acs_codigo || ''; el('micro-observacoes').value = r.observacoes || '';
    el('micro-cadastro-titulo').textContent = `Editar microárea ${r.numero} · ${r.localidade}`;
    if (el('micro-salvar')) el('micro-salvar').textContent = 'Salvar alterações';
    status(r.quarteiroes_sem_geometria.length ? 'Atenção: há quarteirões sem geometria na camada atual.' : `Editando microárea ${r.numero}.`);
    renderListaQuarteiroes(); renderMapa();
    if (el('micro-salvar')) el('micro-cadastro').scrollIntoView({block:'nearest'});
  }
  async function salvar() {
    const loc = el('micro-localidade').value;
    if (!loc || !estado.selecionados.size) { status('Selecione a localidade e ao menos um quarteirão.'); return; }
    const payload = {id_localidade:Number(loc), numero:el('micro-numero').value,
      acs_codigo:el('micro-acs').value, observacoes:el('micro-observacoes').value,
      quarteiroes:[...estado.selecionados]};
    const id = estado.editando;
    try {
      await json(id ? `/api/territorializacao/microareas/${id}` : '/api/territorializacao/microareas', {
        method:id ? 'PUT':'POST', headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name="csrf-token"]')?.content || ''}, body:JSON.stringify(payload)});
      const numero = payload.numero; await carregar(); novo(); status(`Microárea ${numero} salva.`);
    } catch (e) { status(e.message); }
  }
  async function excluir(id) {
    const r = estado.lista.find(item => item.id_microarea === id);
    if (!r || !confirm(`Excluir microárea ${r.numero} de ${r.localidade}? Os vínculos com ${r.quarteiroes.length} quarteirão(ões) serão removidos.`)) return;
    try {
      await json(`/api/territorializacao/microareas/${id}`, {method:'DELETE', headers:{'X-CSRFToken':document.querySelector('meta[name="csrf-token"]')?.content || ''}});
      if (estado.editando === id) novo(); await carregar();
    } catch (e) { alert(e.message); }
  }
  document.querySelectorAll('[data-terr-area]').forEach(b => b.addEventListener('click', () => aba(b.dataset.terrArea)));
  document.querySelectorAll('[data-micro-pane]').forEach(b => b.addEventListener('click', () => subAba(b.dataset.microPane)));
  el('micro-localidade').addEventListener('change', () => { el('micro-q-busca').value = ''; novo(); });
  el('micro-map-labels').addEventListener('change', renderMapa);
  el('micro-q-busca').addEventListener('input', filtrarListaQuarteiroes);
  el('micro-q-lista').addEventListener('change', ev => {
    const input = ev.target.closest('input[type="checkbox"]');
    if (!input || input.disabled) return;
    if (input.checked) estado.selecionados.add(input.value); else estado.selecionados.delete(input.value);
    atualizarSelecao();
  });
  el('micro-q-selecionar').addEventListener('click', () => {
    el('micro-q-lista').querySelectorAll('.micro-q-opcao:not([hidden]) input:not(:disabled)').forEach(input => estado.selecionados.add(input.value));
    atualizarSelecao();
  });
  el('micro-q-limpar').addEventListener('click', () => { estado.selecionados.clear(); atualizarSelecao(); });
  ['micro-filtro-localidade','micro-filtro-acs','micro-filtro-busca'].forEach(id => el(id).addEventListener('input', renderLista));
  el('micro-salvar')?.addEventListener('click', salvar);
  el('micro-nova')?.addEventListener('click', novo);
  el('micro-tabela').addEventListener('click', ev => {
    const edit = ev.target.closest('[data-micro-edit]'), del = ev.target.closest('[data-micro-delete]');
    if (edit) abrir(Number(edit.dataset.microEdit));
    if (del) excluir(Number(del.dataset.microDelete));
  });
  ['micro-xlsx','micro-geojson','micro-kml'].forEach(id => el(id).addEventListener('click', ev => {
    if (ev.currentTarget.getAttribute('aria-disabled') === 'true') ev.preventDefault();
  }));
  if (location.hash === '#microareas') aba('microareas');
})();
