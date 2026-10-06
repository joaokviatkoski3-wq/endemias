(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const source = el('liraa-dados-json');
  if (!source) return;
  const dados = JSON.parse(source.textContent);
  const formatar = n => new Intl.NumberFormat('pt-BR').format(n);
  const escapar = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalizar = s => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
  const codigo = s => {
    const v = String(s ?? '').trim();
    return /^\d+(?:\.0+)?$/.test(v) ? String(parseInt(v, 10)).padStart(4, '0') : v;
  };
  const exibir = s => /^\d+$/.test(s) ? String(parseInt(s, 10)) : s;
  const inventario = new Map(dados.quarteiroes.map(q => [`${q.id_localidade}:${q.quarteirao}`, q]));
  const locais = new Map(dados.quarteiroes.map(q => [normalizar(q.localidade), q.id_localidade]));
  const estado = {ciclo:null, estrato:null, selecionados:new Set(), mapa:null, camada:null, geo:null, ocupados:new Map()};
  const status = (msg, erro=false) => {
    el('liraa-map-status').textContent = msg;
    el('liraa-map-status').style.color = erro ? '#b91c1c' : '';
  };
  const editar = () => !!el('liraa-map-form') && !!estado.ciclo && (!estado.estrato || !estado.estrato.sorteio);
  function cicloAtual() { return dados.ciclos.find(c => String(c.id_ciclo) === el('liraa-map-ciclo').value) || null; }
  function localAtual() { return el('liraa-map-localidade').value; }
  function codigoFeature(f) {
    const p = f.properties || {};
    const raw = p.Localidade;
    const loc = /^\d+$/.test(String(raw ?? '').trim()) ? Number(raw) : locais.get(normalizar(raw));
    return `${loc}:${codigo(p.id_quart ?? p.id_Q)}`;
  }
  function ocupado(key) { return estado.ocupados.get(key); }
  function cor(key) {
    if (estado.selecionados.has(key)) return '#f59e0b';
    const dono = ocupado(key);
    if (!dono) return '#94a3b8';
    const paleta = ['#0369a1','#7c3aed','#059669','#b45309','#be185d','#0f766e','#4f46e5','#b91c1c'];
    return paleta[Number(dono.numero) % paleta.length];
  }
  function estilo(f) {
    const key = codigoFeature(f), marcada = estado.selecionados.has(key), dono = ocupado(key);
    return {color:marcada ? '#92400e' : dono ? '#1e293b' : '#64748b', weight:marcada ? 3 : 1.3,
      fillColor:cor(key), fillOpacity:marcada ? .72 : dono ? .53 : .22};
  }
  function totais() {
    let unidades=0, semRG=0;
    for (const key of estado.selecionados) {
      const q = inventario.get(key);
      if (!q || !q.tem_rg) semRG++;
      if (q) unidades += Number(q.unidades_rg || 0);
    }
    el('liraa-total-q').textContent = formatar(estado.selecionados.size);
    el('liraa-total-rg').textContent = formatar(unidades);
    el('liraa-sem-rg').textContent = formatar(semRG);
    el('liraa-livres').textContent = formatar(estado.ciclo ? dados.quarteiroes.filter(q =>
      !estado.ocupados.has(`${q.id_localidade}:${q.quarteirao}`)).length : 0);
  }
  function atualizar() {
    estado.camada?.setStyle(estilo);
    renderLista();
    totais();
  }
  function alternar(key, force) {
    if (!editar() || !inventario.has(key)) return;
    const dono = ocupado(key);
    if (dono && dono.id_estrato !== estado.estrato?.id_estrato) {
      status(`Q. ${exibir(inventario.get(key).quarteirao)} já pertence ao estrato ${dono.numero}.`, true);
      return;
    }
    const ligar = force === undefined ? !estado.selecionados.has(key) : force;
    if (ligar) estado.selecionados.add(key); else estado.selecionados.delete(key);
    atualizar();
  }
  function renderLista() {
    const caixa = el('liraa-q-lista');
    caixa.replaceChildren();
    const loc = localAtual(), busca = normalizar(el('liraa-q-busca').value);
    if (!estado.ciclo || !loc) { caixa.textContent = 'Escolha um ciclo e uma localidade.'; return; }
    const rows = dados.quarteiroes.filter(q => String(q.id_localidade) === loc &&
      (!busca || normalizar(q.quarteirao).includes(busca) || normalizar(exibir(q.quarteirao)).includes(busca)));
    if (!rows.length) { caixa.textContent = 'Nenhum quarteirão neste filtro.'; return; }
    for (const q of rows) {
      const key = `${q.id_localidade}:${q.quarteirao}`, dono = ocupado(key);
      const label = document.createElement('label'), input = document.createElement('input');
      input.type = 'checkbox'; input.checked = estado.selecionados.has(key);
      input.disabled = !editar() || !!(dono && dono.id_estrato !== estado.estrato?.id_estrato);
      input.addEventListener('change', () => alternar(key, input.checked));
      const titulo = document.createElement('span'), detalhe = document.createElement('small');
      titulo.textContent = `Q. ${exibir(q.quarteirao)}`;
      detalhe.textContent = dono ? `Estrato ${dono.numero}` : q.tem_rg ? `${formatar(q.unidades_rg)} RG` : 'Sem RG';
      label.append(input, titulo, detalhe); caixa.append(label);
    }
  }
  function mapaRender() {
    if (!estado.mapa || !estado.geo) return;
    if (estado.camada) estado.mapa.removeLayer(estado.camada);
    const loc = localAtual();
    const features = (estado.geo.features || []).filter(f => {
      const key = codigoFeature(f);
      return key.split(':', 1)[0] === loc && inventario.has(key);
    });
    estado.camada = L.geoJSON({type:'FeatureCollection', features}, {
      style:estilo,
      onEachFeature:(f, layer) => {
        const key = codigoFeature(f), q = inventario.get(key), dono = ocupado(key);
        if (el('liraa-map-rotulos').checked) layer.bindTooltip(escapar(exibir(q.quarteirao)),
          {permanent:true, direction:'center', className:'liraa-map-label'});
        layer.bindPopup(`Q. ${escapar(exibir(q.quarteirao))} · ${escapar(q.localidade)}<br>${dono ? `Estrato ${escapar(dono.numero)}` : 'Sem estrato'}<br>${q.tem_rg ? `${formatar(q.unidades_rg)} unidades RG estimadas` : 'Sem RG'}`);
        layer.on('click', () => alternar(key));
      }
    }).addTo(estado.mapa);
    if (estado.camada.getBounds().isValid()) estado.mapa.fitBounds(estado.camada.getBounds(), {padding:[18,18]});
  }
  function carregarEstrato() {
    estado.estrato = estado.ciclo?.estratos.find(e => String(e.id_estrato) === el('liraa-map-estrato').value) || null;
    estado.selecionados = new Set(estado.estrato?.quarteiroes || []);
    const e = estado.estrato;
    if (el('liraa-map-form')) {
      el('liraa-form-id').value = e?.id_estrato || '';
      el('liraa-form-numero').value = e?.numero || '';
      el('liraa-form-tipo').value = e?.tipo || 'normal';
      el('liraa-form-n').value = e?.imoveis_confirmados || '';
      el('liraa-form-obs').value = e?.observacoes || '';
      el('liraa-map-form').hidden = !editar();
      el('liraa-map-form').action = estado.ciclo ? `/liraa/ciclos/${estado.ciclo.id_ciclo}/estratos` : '';
    }
    status(e?.sorteio ? 'Estrato sorteado: composição congelada. Selecione outro para editar.' :
      e?.ausentes ? `${e.ausentes} quarteirão(ões) salvo(s) ausente(s) da camada atual. Revise a base antes de salvar.` : '');
    atualizar(); mapaRender();
  }
  function carregarCiclo() {
    estado.ciclo = cicloAtual(); estado.ocupados.clear();
    for (const e of estado.ciclo?.estratos || []) for (const key of e.quarteiroes) estado.ocupados.set(key, e);
    const select = el('liraa-map-estrato');
    select.replaceChildren(new Option('Novo estrato', ''));
    for (const e of estado.ciclo?.estratos || []) select.add(new Option(`Estrato ${e.numero}${e.sorteio ? ' · sorteado' : ''}`, e.id_estrato));
    carregarEstrato();
  }
  async function iniciarMapa() {
    if (!estado.mapa) {
      estado.mapa = L.map('liraa-mapa').setView([-25.33,-49.29], 12);
      const ruas = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        {maxZoom:19, attribution:'Tiles © Esri — Esri, TomTom, Garmin, FAO, NOAA, USGS, © OpenStreetMap contributors, GIS User Community'});
      const satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {maxZoom:19, attribution:'© Esri, Earthstar Geographics'});
      ruas.addTo(estado.mapa);
      L.control.layers({'Mapa':ruas, 'Satélite':satelite}, {}, {collapsed:false}).addTo(estado.mapa);
    }
    estado.mapa.invalidateSize();
    if (!estado.geo) {
      try {
        const resp = await fetch('/api/registro-geografico/geojson');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        estado.geo = await resp.json();
        mapaRender();
      } catch (err) { status(`Não foi possível carregar a geometria: ${err.message}`, true); }
    }
  }
  function aba(nome) {
    for (const aba of ['plano', 'mapa', 'geral', 'importar', 'visitas']) {
      if (!el(`liraa-tab-${aba}`)) continue;
      const ativa = nome === aba;
      el(`liraa-tab-${aba}`).hidden = !ativa;
      el(`liraa-tab-${aba}-btn`).setAttribute('aria-selected', String(ativa));
    }
    if (nome === 'mapa') iniciarMapa();
    if (nome === 'geral') window.LiraaMapaGeral?.iniciar(estado.geo);
  }
  el('liraa-tab-plano-btn').addEventListener('click', () => aba('plano'));
  el('liraa-tab-mapa-btn').addEventListener('click', () => aba('mapa'));
  el('liraa-tab-geral-btn').addEventListener('click', () => aba('geral'));
  for (const nome of ['importar', 'visitas']) {
    el(`liraa-tab-${nome}-btn`)?.addEventListener('click', () => aba(nome));
  }
  if (location.hash === '#liraa-tab-visitas' && el('liraa-tab-visitas')) aba('visitas');
  if (location.hash === '#liraa-tab-importar' && el('liraa-tab-importar')) aba('importar');
  if (new URLSearchParams(location.search).has('consulta_kobo') && el('liraa-tab-importar')) aba('importar');
  el('liraa-map-ciclo').addEventListener('change', carregarCiclo);
  el('liraa-map-estrato').addEventListener('change', carregarEstrato);
  el('liraa-map-localidade').addEventListener('change', () => { renderLista(); mapaRender(); });
  el('liraa-map-rotulos').addEventListener('change', mapaRender);
  el('liraa-q-busca').addEventListener('input', renderLista);
  for (const [botao, marcar] of [['liraa-localidade-toda', true],['liraa-localidade-limpar', false]]) {
    el(botao)?.addEventListener('click', () => {
      if (!editar() || !localAtual()) return;
      for (const q of dados.quarteiroes.filter(q => String(q.id_localidade) === localAtual())) {
        const key = `${q.id_localidade}:${q.quarteirao}`, dono = ocupado(key);
        if (dono && dono.id_estrato !== estado.estrato?.id_estrato) continue;
        if (marcar) estado.selecionados.add(key); else estado.selecionados.delete(key);
      }
      atualizar();
    });
  }
  el('liraa-form-cancelar')?.addEventListener('click', () => { el('liraa-map-estrato').value = ''; carregarEstrato(); });
  el('liraa-map-form')?.addEventListener('submit', ev => {
    const form = ev.currentTarget;
    form.querySelectorAll('input[name="quarteiroes"]').forEach(input => input.remove());
    if (!estado.selecionados.size || !editar()) { ev.preventDefault(); status('Selecione ao menos um quarteirão livre.', true); return; }
    for (const key of estado.selecionados) {
      const input = document.createElement('input'); input.type = 'hidden'; input.name = 'quarteiroes'; input.value = key;
      form.append(input);
    }
  });
  const params = new URLSearchParams(location.search), editarId = params.get('editar');
  const cicloId = params.get('ciclo') || dados.ciclos.find(c => c.estratos.some(e => String(e.id_estrato) === editarId))?.id_ciclo;
  if (cicloId) el('liraa-map-ciclo').value = String(cicloId);
  carregarCiclo();
  if (editarId) { el('liraa-map-estrato').value = editarId; carregarEstrato(); }
  if (location.hash === '#mapa-estratos') aba('mapa');
  if (location.hash === '#mapa-geral-estratos') aba('geral');
})();
