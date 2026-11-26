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
  const layers = new Map();
  const blockIndex = new Map();
  const localityIndex = new Map();
  let fullBounds = null;

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
  document.getElementById('geo-detail-close').addEventListener('click', () => openDetail(false));

  const kpi = (value, label) => {
    const box = element('div', 'geo-detail-kpi');
    box.append(element('strong', '', number(value)), element('span', '', label));
    return box;
  };

  async function showBlock(idLocality, block, layer) {
    openDetail(true);
    detailTitle.textContent = `Quarteirão ${block}`;
    detailContent.replaceChildren(element('p', 'geo-detail-loading', 'Carregando dados do Registro Geográfico...'));
    if (layer?.getBounds) map.fitBounds(layer.getBounds(), {padding: [80, 80], maxZoom: 17});
    try {
      const data = await api(`/api/geovsatt/quarteiroes/${encodeURIComponent(idLocality)}/${encodeURIComponent(block)}`);
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
      detailContent.replaceChildren(element('p', 'geo-detail-loading', error.message));
    }
  }

  function buildLayers(streetsData, blocksData, localitiesData) {
    const streets = L.geoJSON(streetsData, {
      pane: 'streets',
      style: {color: '#78857d', weight: 1.4, opacity: .78},
      onEachFeature(feature, layer) {
        const name = feature.properties?.nome;
        if (name) layer.bindTooltip(name, {sticky: true, opacity: .92});
      },
    });
    const blocks = L.geoJSON(blocksData, {
      pane: 'blocks',
      style: {color: '#00752b', weight: 1, fillColor: '#e8f5eb', fillOpacity: .28},
      onEachFeature(feature, layer) {
        const props = feature.properties || {};
        blockIndex.set(String(props.chave), layer);
        layer.bindTooltip(`Q. ${props.id_quart}${props.Localidade_nome ? ` · ${props.Localidade_nome}` : ''}`, {sticky: true});
        layer.on('click', () => showBlock(props.Localidade, props.id_quart, layer));
      },
    });
    const localities = L.geoJSON(localitiesData, {
      pane: 'localities',
      pointToLayer: (_, latlng) => L.circleMarker(latlng, {radius: 5, color: '#fff', weight: 2, fillColor: '#008c30', fillOpacity: 1}),
      onEachFeature(feature, layer) {
        const props = feature.properties || {};
        localityIndex.set(String(props.id_localidade), layer);
        layer.bindTooltip(props.nome, {permanent: true, direction: 'top', className: 'geo-locality-label'});
      },
    });
    layers.set('logradouros', streets);
    layers.set('quarteiroes', blocks);
    layers.set('localidades', localities);
    for (const [id, layer] of layers) {
      const checkbox = document.querySelector(`[data-layer="${id}"]`);
      if (checkbox?.checked) layer.addTo(map);
    }
    fullBounds = blocks.getBounds();
    if (fullBounds.isValid()) map.fitBounds(fullBounds, {padding: [24, 24]});
  }

  document.querySelectorAll('[data-layer]').forEach(input => input.addEventListener('change', () => {
    const layer = layers.get(input.dataset.layer);
    if (!layer) return;
    if (input.checked) layer.addTo(map); else map.removeLayer(layer);
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
      button.addEventListener('click', () => {
        searchResults.hidden = true;
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

  Promise.all([
    api('/api/geovsatt/camadas/logradouros'),
    api('/api/geovsatt/camadas/quarteiroes'),
    api('/api/geovsatt/camadas/localidades'),
  ]).then(([streets, blocks, localities]) => {
    buildLayers(streets, blocks, localities);
    statusNode.textContent = `${number(blocks.features?.length)} quarteirões · ${number(streets.features?.length)} logradouros · ${number(localities.features?.length)} localidades`;
  }).catch(error => {
    statusNode.textContent = error.message;
  });
})();
