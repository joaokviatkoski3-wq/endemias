(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const source = el('liraa-dados-json');
  if (!source || !el('liraa-geral-mapa')) return;
  const dados = JSON.parse(source.textContent);
  const formatar = n => new Intl.NumberFormat('pt-BR').format(n);
  const escapar = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalizar = s => String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
  const codigo = s => {
    const v = String(s ?? '').trim();
    return /^\d+(?:\.0+)?$/.test(v) ? String(parseInt(v, 10)).padStart(4, '0') : v;
  };
  const exibir = s => /^\d+$/.test(String(s)) ? String(parseInt(s, 10)) : String(s);
  const inventario = new Map(dados.quarteiroes.map(q => [`${q.id_localidade}:${q.quarteirao}`, q]));
  const locais = new Map(dados.quarteiroes.map(q => [normalizar(q.localidade), q.id_localidade]));
  const nomesLocais = new Map(dados.quarteiroes.map(q => [Number(q.id_localidade), q.localidade]));
  const paleta = ['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2','#be123c','#65a30d',
    '#4f46e5','#b45309','#0d9488','#c026d3','#0369a1','#ca8a04','#15803d','#e11d48',
    '#7c3aed','#0284c7','#a21caf','#4d7c0f','#c2410c','#0f766e','#b91c1c','#6d28d9'];
  const estado = {mapa:null, camada:null, geo:null, carregando:null, ciclo:null, ocupados:new Map(),
    cores:new Map(), selecionado:null, camadasPorEstrato:new Map()};
  const chaveFeature = f => {
    const p = f.properties || {}, raw = p.Localidade;
    const loc = /^\d+$/.test(String(raw ?? '').trim()) ? Number(raw) : locais.get(normalizar(raw));
    return `${loc}:${codigo(p.id_quart ?? p.id_Q)}`;
  };
  const cor = e => estado.cores.get(e.id_estrato) || '#64748b';
  const status = (mensagem, erro=false) => {
    el('liraa-geral-status').textContent = mensagem;
    el('liraa-geral-status').style.color = erro ? '#b91c1c' : '';
  };
  function mostrarDetalhe(estrato, quarteirao=null) {
    const detalhe = el('liraa-geral-detalhe');
    if (!estrato) {
      detalhe.innerHTML = quarteirao
        ? `<h3>Q. ${escapar(exibir(quarteirao.quarteirao))} · ${escapar(quarteirao.localidade)}</h3><p>Sem estrato neste ciclo.</p><p>${quarteirao.tem_rg ? `${formatar(quarteirao.unidades_rg)} imóveis RG (COND = 1)` : 'Sem RG'}</p>`
        : 'Selecione um estrato na lista ou clique em um quarteirão no mapa.';
      return;
    }
    const ativos = estrato.quarteiroes.map(k => inventario.get(k)).filter(Boolean);
    const unidades = ativos.reduce((total, q) => total + Number(q.unidades_rg || 0), 0);
    const semRg = ativos.filter(q => !q.tem_rg).length;
    const localidades = [...new Set(estrato.localidades.map(id => nomesLocais.get(Number(id)) || `ID ${id}`))];
    const selecionados = quarteirao ? `<p><strong>Quarteirão clicado:</strong> Q. ${escapar(exibir(quarteirao.quarteirao))} · ${escapar(quarteirao.localidade)}</p>` : '';
    detalhe.innerHTML = `<h3><span class="liraa-geral-cor" style="background:${cor(estrato)};display:inline-block;vertical-align:middle"></span> Estrato ${escapar(estrato.numero)}</h3>` +
      `<p>${estrato.tipo === 'reduzido' ? 'Reduzido · 50%' : 'Normal · 20%'} · ${estrato.sorteio ? 'Sorteio registrado' : 'Sem sorteio'}</p>` +
      `<p><strong>N confirmado:</strong> ${formatar(estrato.imoveis_confirmados)} imóveis · <strong>Quarteirões:</strong> ${formatar(estrato.quarteiroes.length)}</p>` +
      `<p><strong>Localidades:</strong> ${escapar(localidades.join(', ') || 'Não informadas')}</p>` +
      `<p><strong>Referência RG:</strong> ${formatar(unidades)} imóveis (COND = 1); ${formatar(semRg)} quarteirão(ões) sem RG. Não substitui o N confirmado.</p>` +
      (estrato.ausentes ? `<p><strong>Atenção:</strong> ${formatar(estrato.ausentes)} quarteirão(ões) do estrato não aparecem na camada atual.</p>` : '') +
      (estrato.observacoes ? `<p><strong>Observações:</strong> ${escapar(estrato.observacoes)}</p>` : '') + selecionados;
  }
  function marcar(estrato, quarteirao=null, aproximar=false) {
    estado.selecionado = estrato?.id_estrato ?? null;
    mostrarDetalhe(estrato, quarteirao);
    for (const botao of el('liraa-geral-lista').querySelectorAll('button[data-estrato]'))
      botao.setAttribute('aria-pressed', String(estado.selecionado === Number(botao.dataset.estrato)));
    estado.camada?.setStyle(estilo);
    if (aproximar && estrato) {
      const camadas = estado.camadasPorEstrato.get(estrato.id_estrato) || [];
      if (camadas.length) estado.mapa.fitBounds(L.featureGroup(camadas).getBounds(), {padding:[22,22]});
      else status('Este estrato não tem geometria disponível na camada atual.', true);
    }
  }
  function estilo(f) {
    const e = estado.ocupados.get(chaveFeature(f));
    const selecionado = e && e.id_estrato === estado.selecionado;
    return {color:selecionado ? '#0f172a' : e ? '#334155' : '#64748b', weight:selecionado ? 3 : 1.2,
      fillColor:e ? cor(e) : '#94a3b8', fillOpacity:selecionado ? .78 : e ? .59 : .18};
  }
  function renderLista() {
    const caixa = el('liraa-geral-lista');
    caixa.replaceChildren();
    if (!estado.ciclo) { caixa.textContent = 'Escolha um ciclo para conferir os estratos.'; return; }
    const busca = normalizar(el('liraa-geral-busca').value);
    const estratos = estado.ciclo.estratos.filter(e => !busca || normalizar(`estrato ${e.numero} ${e.numero} ${e.localidades.map(id => nomesLocais.get(Number(id)) || '').join(' ')}`).includes(busca));
    if (!estratos.length) { caixa.textContent = estado.ciclo.estratos.length ? 'Nenhum estrato neste filtro.' : 'Nenhum estrato cadastrado neste ciclo.'; return; }
    for (const e of estratos) {
      const botao = document.createElement('button');
      botao.type = 'button'; botao.className = 'liraa-geral-item'; botao.dataset.estrato = e.id_estrato;
      botao.setAttribute('aria-pressed', String(e.id_estrato === estado.selecionado));
      const marcador = document.createElement('span'); marcador.className = 'liraa-geral-cor'; marcador.style.background = cor(e);
      const texto = document.createElement('span');
      const titulo = document.createElement('strong'); titulo.textContent = `Estrato ${e.numero} · ${e.tipo === 'reduzido' ? 'Reduzido' : 'Normal'}`;
      const complemento = document.createElement('small');
      complemento.textContent = `${formatar(e.quarteiroes.length)} quarteirões · N ${formatar(e.imoveis_confirmados)}${e.ausentes ? ` · ${e.ausentes} fora da camada` : ''}`;
      texto.append(titulo, complemento); botao.append(marcador, texto);
      botao.addEventListener('click', () => marcar(e, null, true)); caixa.append(botao);
    }
  }
  function renderMapa() {
    if (!estado.mapa || !estado.geo) return;
    const primeiro = !estado.camada;
    if (estado.camada) estado.mapa.removeLayer(estado.camada);
    estado.camadasPorEstrato.clear();
    const features = (estado.geo.features || []).filter(f => inventario.has(chaveFeature(f)));
    estado.camada = L.geoJSON({type:'FeatureCollection', features}, {style:estilo,
      onEachFeature:(f, layer) => {
        const key = chaveFeature(f), q = inventario.get(key), e = estado.ocupados.get(key);
        layer.bindTooltip(`Q. ${escapar(exibir(q.quarteirao))} · ${escapar(q.localidade)}${e ? ` · Estrato ${escapar(e.numero)}` : ' · sem estrato'}`);
        layer.on('click', () => marcar(e, q));
        if (e) {
          if (!estado.camadasPorEstrato.has(e.id_estrato)) estado.camadasPorEstrato.set(e.id_estrato, []);
          estado.camadasPorEstrato.get(e.id_estrato).push(layer);
        }
      }}).addTo(estado.mapa);
    if (primeiro && estado.camada.getBounds().isValid())
      estado.mapa.fitBounds(estado.camada.getBounds(), {padding:[18,18]});
  }
  function carregarCiclo() {
    estado.ciclo = dados.ciclos.find(c => String(c.id_ciclo) === el('liraa-geral-ciclo').value) || null;
    estado.ocupados.clear(); estado.cores.clear(); estado.selecionado = null;
    for (const [indice, e] of (estado.ciclo?.estratos || []).entries()) {
      estado.cores.set(e.id_estrato, indice < paleta.length ? paleta[indice] :
        `hsl(${Math.round((indice - paleta.length) * 137.508) % 360}, 68%, 42%)`);
      for (const key of e.quarteiroes) estado.ocupados.set(key, e);
    }
    const c = estado.ciclo, ativos = [...estado.ocupados.keys()].filter(k => inventario.has(k)).length;
    el('liraa-geral-total').textContent = c ? formatar(c.estratos.length) : '—';
    el('liraa-geral-atribuidos').textContent = c ? formatar(ativos) : '—';
    el('liraa-geral-livres').textContent = c ? formatar(c.quarteiroes_sem_estrato) : '—';
    el('liraa-geral-n').textContent = c ? formatar(c.estratos.reduce((sum, e) => sum + Number(e.imoveis_confirmados || 0), 0)) : '—';
    mostrarDetalhe(null); renderLista(); renderMapa();
    status(c ? `${c.ano} — ${c.nome}: ${formatar(c.estratos.length)} estrato(s) no mapa.` : 'Selecione um ciclo.');
  }
  async function iniciar(geoExistente=null) {
    if (!estado.mapa) {
      estado.mapa = L.map('liraa-geral-mapa').setView([-25.33,-49.29], 12);
      const ruas = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        {maxZoom:19, attribution:'Tiles © Esri — Esri, TomTom, Garmin, FAO, NOAA, USGS, © OpenStreetMap contributors, GIS User Community'});
      const satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {maxZoom:19, attribution:'© Esri, Earthstar Geographics'});
      ruas.addTo(estado.mapa);
      L.control.layers({'Mapa':ruas, 'Satélite':satelite}, {}, {collapsed:false}).addTo(estado.mapa);
    }
    estado.mapa.invalidateSize();
    if (estado.geo) { renderMapa(); return; }
    if (geoExistente) { estado.geo = geoExistente; renderMapa(); return; }
    if (!estado.carregando) estado.carregando = fetch('/api/registro-geografico/geojson')
      .then(resp => { if (!resp.ok) throw new Error(`HTTP ${resp.status}`); return resp.json(); })
      .then(geo => { estado.geo = geo; renderMapa(); })
      .catch(err => { status(`Não foi possível carregar a geometria: ${err.message}`, true); })
      .finally(() => { estado.carregando = null; });
    await estado.carregando;
  }
  el('liraa-geral-ciclo').addEventListener('change', carregarCiclo);
  el('liraa-geral-busca').addEventListener('input', renderLista);
  const params = new URLSearchParams(location.search);
  const cicloSolicitado = params.get('ciclo');
  if (cicloSolicitado && dados.ciclos.some(c => String(c.id_ciclo) === cicloSolicitado))
    el('liraa-geral-ciclo').value = cicloSolicitado;
  else if (dados.ciclos.length) el('liraa-geral-ciclo').value = String(dados.ciclos[0].id_ciclo);
  carregarCiclo();
  window.LiraaMapaGeral = {iniciar};
})();
