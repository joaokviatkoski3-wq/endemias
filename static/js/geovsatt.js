(() => {
  'use strict';
  const mapNode = document.getElementById('geo-map');
  if (!mapNode || !window.L) return;
  const statusNode = document.getElementById('geo-status');
  const sidebar = document.getElementById('geo-sidebar');
  const backdrop = document.getElementById('geo-sidebar-backdrop');
  const detail = document.getElementById('geo-detail');
  const detailContent = document.getElementById('geo-detail-content');
  const detailTitle = document.getElementById('geo-detail-title');
  const searchResults = document.getElementById('geo-search-results');
  const podeRg = document.querySelector('.geo-shell').dataset.podeRg === '1';
  const layers = new Map();
  const options = [...document.querySelectorAll('[data-layer]:enabled')];
  const blockIndex = new Map();
  const localityIndex = new Map();
  let fullBounds = null;
  let detailSequence = 0;

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const number = value => Number(value || 0).toLocaleString('pt-BR');
  const api = async url => {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store'});
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) throw Error(data?.erro || 'Não foi possível carregar os dados do mapa.');
    return data;
  };

  const map = L.map(mapNode, {zoomControl: false, preferCanvas: true, minZoom: 10, maxZoom: 20});
  map.createPane('streets').style.zIndex = 310;
  map.createPane('blocks').style.zIndex = 330;
  map.createPane('imported').style.zIndex = 370;
  map.createPane('localities').style.zIndex = 450;
  L.control.zoom({position: 'topright'}).addTo(map);
  map.setView([-25.32, -49.30], 12);

  function openSidebar(open) {
    sidebar.classList.toggle('is-open', open);
    sidebar.setAttribute('aria-hidden', String(!open));
    backdrop.hidden = !open;
    document.getElementById('geo-menu-open').setAttribute('aria-expanded', String(open));
  }
  document.getElementById('geo-menu-open').addEventListener('click', () => openSidebar(true));
  document.getElementById('geo-menu-close').addEventListener('click', () => openSidebar(false));
  backdrop.addEventListener('click', () => openSidebar(false));

  function openDetail(open) {
    detail.classList.toggle('is-open', open);
    detail.setAttribute('aria-hidden', String(!open));
  }
  document.getElementById('geo-detail-close').addEventListener('click', () => {
    detailSequence += 1;
    openDetail(false);
  });

  const kpi = (value, label) => {
    const box = element('div', 'geo-detail-kpi');
    box.append(element('strong', '', number(value)), element('span', '', label));
    return box;
  };

  async function showBlock(idLocality, block, layer) {
    if (layer?.getBounds) map.fitBounds(layer.getBounds(), {padding: [80, 80], maxZoom: 17});
    if (!podeRg) return;
    const sequence = ++detailSequence;
    openDetail(true);
    detailTitle.textContent = `Quarteirão ${block}`;
    detailContent.replaceChildren(element('p', 'geo-detail-loading', 'Carregando dados do Registro Geográfico...'));
    try {
      const data = await api(`/api/geovsatt/quarteiroes/${encodeURIComponent(idLocality)}/${encodeURIComponent(block)}`);
      if (sequence !== detailSequence) return;
      detailTitle.textContent = `Quarteirão ${data.quarteirao} · ${data.localidade.nome}`;
      const stats = element('div', 'geo-detail-kpis');
      stats.append(
        kpi(data.resumo.total_com_condominio, 'Imóveis estimados'),
        kpi(data.resumo.residencias_com_condominio, 'Residências'),
        kpi(data.resumo.populacao_aproximada, 'População estimada'),
        kpi(data.registros.length, 'Registros do RG')
      );
      const source = element('p', 'geo-detail-note', `${data.resumo.fonte_populacao}. Atualização do quarteirão: ${data.data_atualizacao_br || 'não informada'}.`);
      const section = element('section', 'geo-detail-section');
      section.append(element('h3', '', 'Imóveis e endereços do RG'));
      const list = element('div', 'geo-rg-list');
      if (!data.registros.length) list.append(element('p', 'geo-detail-note', 'Este quarteirão ainda não possui imóveis cadastrados no RG.'));
      for (const row of data.registros) {
        const item = element('div', 'geo-rg-item');
        item.append(
          element('strong', '', [row.logradouro, row.numero].filter(Boolean).join(', ') || 'Endereço não informado'),
          element('span', '', [row.sequencia ? `Sequência ${row.sequencia}` : '', row.agentes || ''].filter(Boolean).join(' · ')),
          element('em', '', row.tipo_label || row.tipo || 'Sem tipo')
        );
        list.append(item);
      }
      section.append(list);
      detailContent.replaceChildren(stats, source, section);
    } catch (error) {
      if (sequence === detailSequence) detailContent.replaceChildren(element('p', 'geo-detail-loading', error.message));
    }
  }

  const defaults = {
    logradouros: {pane: 'streets', color: '#78857d', weight: 1.4, opacity: .78, label: 'nome'},
    quarteiroes: {pane: 'blocks', color: '#00752b', fillColor: '#e8f5eb', weight: 1, fillOpacity: .28},
    localidades: {pane: 'localities', color: '#008c30', label: 'nome'},
  };

  function buildLayer(input, data) {
    const id = input.dataset.layer;
    const config = JSON.parse(input.dataset.estilo);
    const base = Object.hasOwn(defaults, id) ? defaults[id] : {pane: 'imported', color: '#175cd3'};
    const color = feature => {
      const props = feature.properties || {};
      const value = Object.hasOwn(props, config.atributo_cor) ? String(props[config.atributo_cor] ?? '') : '';
      return Object.hasOwn(config.cores, value) ? config.cores[value] : config.cor || '';
    };
    return L.geoJSON(data, {
      pane: base.pane,
      style(feature) {
        const cor = color(feature);
        if (['Point', 'MultiPoint'].includes(feature.geometry.type)) {
          return {color: '#fff', weight: 2, fillColor: cor || base.color, fillOpacity: 1};
        }
        return {...base, color: cor || base.color, fillColor: cor || base.fillColor || base.color};
      },
      pointToLayer(_, latlng) {
        return L.circleMarker(latlng, {pane: base.pane, radius: 5});
      },
      onEachFeature(feature, layer) {
        const props = feature.properties || {};
        const attribute = config.rotulo || base.label;
        let name = Object.hasOwn(props, attribute) ? props[attribute] : null;
        if (id === 'quarteiroes') {
          blockIndex.set(String(props.chave), layer);
          if (name == null) name = `Q. ${props.id_quart}${props.Localidade_nome ? ` · ${props.Localidade_nome}` : ''}`;
          layer.on('click', () => showBlock(props.Localidade, props.id_quart, layer));
        } else if (id === 'localidades') {
          localityIndex.set(String(props.id_localidade), layer);
        }
        if (name != null) {
          const tooltipOptions = id === 'localidades'
            ? {permanent: true, direction: 'top', className: 'geo-locality-label'}
            : {sticky: true};
          layer.bindTooltip(element('span', '', name), tooltipOptions);
        }
      },
    });
  }

  function loadLayer(input) {
    const id = input.dataset.layer;
    if (!layers.has(id)) {
      const pending = api(`/api/geovsatt/camadas/${encodeURIComponent(id)}`)
        .then(data => buildLayer(input, data))
        .catch(error => {
          layers.delete(id);
          throw error;
        });
      layers.set(id, pending);
    }
    return layers.get(id);
  }

  function updateBounds() {
    fullBounds = L.latLngBounds([]);
    const legend = document.getElementById('geo-legend');
    const labels = [];
    for (const input of options) {
      const id = input.dataset.layer;
      const layer = mapLayers[id];
      if (!layer || !map.hasLayer(layer)) continue;
      if (layer.getBounds().isValid()) fullBounds.extend(layer.getBounds());
      const key = element('i', 'legend-' + input.dataset.tipo);
      const baseColor = Object.hasOwn(defaults, id) ? defaults[id].color : '#175cd3';
      const style = JSON.parse(input.dataset.estilo);
      const rules = Object.entries(style.cores);
      key.style.setProperty('--legend-color', style.cor || rules[0]?.[1] || baseColor);
      const label = element('span');
      if (rules.length) label.title = rules.map(([value, color]) => `${value}: ${color}`).join('\n');
      label.append(key, document.createTextNode(input.dataset.nome));
      labels.push(label);
    }
    legend.replaceChildren(...labels);
    legend.hidden = !labels.length;
  }

  const mapLayers = Object.create(null);
  async function toggleLayer(input) {
    const id = input.dataset.layer;
    if (input.checked) {
      const layer = await loadLayer(input);
      mapLayers[id] = layer;
      if (input.checked) layer.addTo(map);
    } else if (mapLayers[id]) {
      map.removeLayer(mapLayers[id]);
    }
    updateBounds();
  }

  function reportLayerError(input, error) {
    input.checked = false;
    statusNode.textContent = `${input.dataset.nome}: ${error.message}`;
  }

  options.forEach(input => input.addEventListener('change', () => {
    toggleLayer(input).catch(error => reportLayerError(input, error));
  }));
  document.getElementById('geo-fit').addEventListener('click', () => {
    if (fullBounds?.isValid()) map.fitBounds(fullBounds, {padding: [24, 24]});
  });

  function showSearch(items) {
    searchResults.replaceChildren();
    if (!items.length) {
      searchResults.append(element('div', 'geo-search-result', 'Nenhum resultado encontrado.'));
      searchResults.hidden = false;
      return;
    }
    for (const item of items) {
      const button = element('button', 'geo-search-result');
      button.type = 'button';
      button.append(element('strong', '', item.titulo), element('span', '', item.subtitulo));
      button.addEventListener('click', async () => {
        searchResults.hidden = true;
        const id = item.tipo === 'quarteirao' ? 'quarteiroes' : 'localidades';
        const input = options.find(option => option.dataset.layer === id);
        if (!input) return;
        input.checked = true;
        try {
          await toggleLayer(input);
        } catch (error) {
          reportLayerError(input, error);
          return;
        }
        if (item.tipo === 'quarteirao') {
          const layer = blockIndex.get(String(item.chave));
          showBlock(item.id_localidade, item.quarteirao, layer);
        } else {
          const layer = localityIndex.get(String(item.id_localidade));
          if (layer) map.setView(layer.getLatLng(), 15);
        }
      });
      searchResults.append(button);
    }
    searchResults.hidden = false;
  }

  document.getElementById('geo-search').addEventListener('submit', async event => {
    event.preventDefault();
    const query = document.getElementById('geo-search-input').value.trim();
    if (!query) return;
    searchResults.hidden = false;
    searchResults.replaceChildren(element('div', 'geo-search-result', 'Buscando...'));
    try {
      const data = await api(`/api/geovsatt/busca?q=${encodeURIComponent(query)}`);
      showSearch(data.resultados);
    } catch (error) {
      searchResults.replaceChildren(element('div', 'geo-search-result', error.message));
    }
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.geo-search')) searchResults.hidden = true;
  });

  const initial = options.filter(input => input.checked);
  Promise.allSettled(initial.map(toggleLayer)).then(results => {
    if (fullBounds?.isValid()) map.fitBounds(fullBounds, {padding: [24, 24]});
    statusNode.textContent = '';
    results.forEach((result, i) => {
      if (result.status === 'rejected') reportLayerError(initial[i], result.reason);
    });
  });
})();
