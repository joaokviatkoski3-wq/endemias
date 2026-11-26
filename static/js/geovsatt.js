(() => {
  'use strict';
  const mapNode = document.getElementById('geo-map');
  if (!mapNode || !window.L) return;
  const statusNode = document.getElementById('geo-status');
  const marcarEquipamento = document.getElementById('geo-marcar-equipamento');
  const sidebar = document.getElementById('geo-sidebar');
  const backdrop = document.getElementById('geo-sidebar-backdrop');
  const detail = document.getElementById('geo-detail');
  const detailContent = document.getElementById('geo-detail-content');
  const detailTitle = document.getElementById('geo-detail-title');
  const searchForm = document.getElementById('geo-search');
  const searchInput = document.getElementById('geo-search-input');
  const searchSource = document.getElementById('geo-search-source');
  const searchResults = document.getElementById('geo-search-results');
  const searchFeedback = document.getElementById('geo-search-feedback');
  const podeRg = document.querySelector('.geo-shell').dataset.podeRg === '1';
  const layers = new Map();
  const options = [...document.querySelectorAll('[data-layer]:enabled')];
  const legendasPorCamada = new WeakMap();
  const filtrosPorCamada = new Map();
  const blockIndex = new Map();
  const localityIndex = new Map();
  let fullBounds = null;
  let detailSequence = 0;
  let searchSequence = 0;
  let suggestionTimer;
  let suggestionRequest;
  let highlighted = null;
  let marcandoEquipamento = false;

  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const number = value => Number(value || 0).toLocaleString('pt-BR');
  const api = async (url, options = {}) => {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options});
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) throw Error(data?.erro || 'Não foi possível carregar os dados do mapa.');
    return data;
  };

  // Os caminhos SVG recebem eventos apenas na geometria desenhada em cada pane.
  const map = L.map(mapNode, {zoomControl: false, minZoom: 10, maxZoom: 22});
  map.createPane('territory').style.zIndex = 290;
  map.createPane('areas').style.zIndex = 300;
  map.createPane('streets').style.zIndex = 310;
  map.createPane('blocks').style.zIndex = 330;
  map.createPane('imported').style.zIndex = 370;
  map.createPane('localities').style.zIndex = 450;
  map.createPane('rg-selection').style.zIndex = 460;
  L.control.zoom({position: 'topright'}).addTo(map);
  map.setView([-25.32, -49.30], 12);
  const labels = window.GeoVSATTRotulos.create(map);
  const measure = window.GeoVSATTMedicao.create(map, (pontos, incluir_condominios) => api('/api/geovsatt/populacao', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
    body: JSON.stringify({pontos, incluir_condominios}),
  }));
  if (marcarEquipamento) {
    const alternarMarcacao = ativo => {
      marcandoEquipamento = ativo;
      marcarEquipamento.setAttribute('aria-pressed', String(ativo));
      mapNode.classList.toggle('geo-marcando-equipamento', ativo);
      statusNode.textContent = ativo ? 'Clique no local do novo equipamento. Pressione Esc para cancelar.' : '';
    };
    marcarEquipamento.addEventListener('click', () => {
      if (measure.active()) {
        statusNode.textContent = 'Conclua ou limpe a medição antes de marcar um equipamento.';
        return;
      }
      map.closePopup();
      if (detail.classList.contains('is-open')) {
        detailSequence += 1;
        clearHighlight();
        openDetail(false);
      }
      alternarMarcacao(!marcandoEquipamento);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && marcandoEquipamento) alternarMarcacao(false);
    });
    document.querySelectorAll('[data-medida], #geo-imprimir').forEach(botao => botao.addEventListener('click', () => {
      if (marcandoEquipamento) alternarMarcacao(false);
    }));
    map.on('click', event => {
      if (!marcandoEquipamento) return;
      const destino = new URL(marcarEquipamento.dataset.destino, window.location.origin);
      destino.searchParams.set('latitude', event.latlng.lat.toFixed(6));
      destino.searchParams.set('longitude', event.latlng.lng.toFixed(6));
      window.location.assign(destino.href);
    });
  }
  const basemaps = {
    sentinel: {
      title: 'Satélite Sentinel-2 (2025)',
      url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg',
      native: 14,
      credits: '<a href="https://cloudless.eox.at/">EOxCloudless</a> por <a href="https://eox.at/">EOX IT Services GmbH</a> · Dados Copernicus Sentinel 2025 modificados',
    },
    esri: {
      title: 'Satélite Esri World Imagery',
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      native: 19,
      credits: 'Esri, Vantor, Earthstar Geographics e GIS User Community',
    },
  };
  let activeBasemap;
  let vectorMap;
  let baseSequence = 0;
  let basePending = false;
  let baseFailed = false;
  const baseSelect = document.getElementById('geo-basemap');
  baseSelect.addEventListener('change', async () => {
    const sequence = ++baseSequence;
    if (activeBasemap) map.removeLayer(activeBasemap);
    activeBasemap = null;
    vectorMap = null;
    basePending = false;
    baseFailed = false;
    statusNode.textContent = '';
    const baseLabel = document.getElementById('geo-base-label');
    if (baseSelect.value === 'openfreemap') {
      baseLabel.textContent = 'OpenStreetMap · OpenFreeMap';
      statusNode.textContent = 'Carregando a base vetorial…';
      basePending = true;
      try {
        const versao = encodeURIComponent(document.documentElement.dataset.versao);
        const {criarBaseVetorial} = await import(`/static/js/geovsatt_vetorial.mjs?v=${versao}`);
        if (sequence !== baseSequence) return;
        activeBasemap = criarBaseVetorial(map);
        activeBasemap.addTo(map);
        vectorMap = activeBasemap.getMaplibreMap();
        vectorMap.once('load', () => {
          if (sequence !== baseSequence) return;
          baseFailed = false;
          if (statusNode.textContent === 'Carregando a base vetorial…') statusNode.textContent = '';
        });
        vectorMap.on('error', () => {
          if (sequence !== baseSequence) return;
          baseFailed = !vectorMap.isStyleLoaded();
          statusNode.textContent = 'Alguns dados da base OpenFreeMap não carregaram.';
        });
      } catch {
        if (sequence !== baseSequence) return;
        if (activeBasemap) map.removeLayer(activeBasemap);
        activeBasemap = null;
        baseFailed = true;
        statusNode.textContent = 'Não foi possível abrir a base OpenFreeMap neste navegador.';
      } finally {
        if (sequence === baseSequence) basePending = false;
      }
      return;
    }
    const picked = Object.hasOwn(basemaps, baseSelect.value) ? basemaps[baseSelect.value] : null;
    baseLabel.textContent = picked?.title || 'Sem imagem-base · dados institucionais';
    if (picked) {
      activeBasemap = L.tileLayer(picked.url, {
        maxNativeZoom: picked.native, maxZoom: map.getMaxZoom(), noWrap: true, attribution: picked.credits,
      }).on('tileerror', () => {
        statusNode.textContent = 'Algumas imagens de satélite não carregaram.';
      }).addTo(map);
    }
  });

  function estadoBase() {
    if (baseFailed) return 'erro';
    if (basePending || activeBasemap?.isLoading?.() || (vectorMap && !vectorMap.loaded())) return 'carregando';
    return 'pronta';
  }

  function openSidebar(open) {
    const trigger = document.getElementById('geo-menu-open');
    if (!open) trigger.focus();
    sidebar.classList.toggle('is-open', open);
    sidebar.setAttribute('aria-hidden', String(!open));
    sidebar.inert = !open;
    backdrop.hidden = !open;
    trigger.setAttribute('aria-expanded', String(open));
    if (open) document.getElementById('geo-menu-close').focus();
  }
  document.getElementById('geo-menu-open').addEventListener('click', () => openSidebar(true));
  document.getElementById('geo-menu-close').addEventListener('click', () => openSidebar(false));
  backdrop.addEventListener('click', () => openSidebar(false));

  function openDetail(open) {
    detail.classList.toggle('is-open', open);
    detail.setAttribute('aria-hidden', String(!open));
    detail.inert = !open;
  }
  document.getElementById('geo-detail-close').addEventListener('click', () => {
    detailSequence += 1;
    clearHighlight();
    openDetail(false);
  });

  const kpi = (value, label) => {
    const box = element('div', 'geo-detail-kpi');
    box.append(element('strong', '', number(value)), element('span', '', label));
    return box;
  };

  function clearHighlight() {
    if (highlighted) highlighted.remove();
    highlighted = null;
  }

  async function showBlock(idLocality, block, layer, matches = []) {
    clearHighlight();
    if (layer?.getBounds().isValid()) {
      highlighted = L.geoJSON(layer.toGeoJSON(), {
        pane: 'rg-selection', interactive: false, style: {color: '#7a4300', weight: 3, fillOpacity: .08},
      }).addTo(map);
      const wide = map.getSize().x > 820;
      map.fitBounds(layer.getBounds(), {
        paddingTopLeft: [48, 55],
        paddingBottomRight: [podeRg && wide ? detail.offsetWidth + 46 : 48, 55],
        maxZoom: 20,
      });
    }
    if (!podeRg) return;
    map.closePopup();
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
      if (matches.length) section.append(element('p', 'geo-detail-note', 'O endereço da busca está destacado abaixo.'));
      if (!layer) section.append(element('p', 'geo-detail-note', 'Este quarteirão consta no RG e ainda está sem geometria na malha ativa.'));
      const list = element('div', 'geo-rg-list');
      if (!data.registros.length) list.append(element('p', 'geo-detail-note', 'Este quarteirão ainda não possui imóveis cadastrados no RG.'));
      const found = new Set(matches.map(String));
      const registros = [...data.registros].sort((a, b) => Number(found.has(String(b.id_imovel))) - Number(found.has(String(a.id_imovel))));
      for (const row of registros) {
        const item = element('div', found.has(String(row.id_imovel)) ? 'geo-rg-item geo-rg-match' : 'geo-rg-item');
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
    localidades: {pane: 'territory', color: '#238070', weight: 1.4, fillOpacity: .12, label: 'nome', labelZoom: 13, categories: 'nome'},
    'limite-municipal': {pane: 'territory', color: '#364850', weight: 2.5, noFill: true},
    hidrografia: {pane: 'streets', color: '#1672aa', weight: 2, label: 'NOME', labelColor: '#125783', labelZoom: 15},
    ferrovia: {pane: 'streets', color: '#54463d', weight: 2, line: 'ferrovia'},
    'suscetibilidade-inundacao': {color: '#355eb0', categories: 'Classe', colors: {Alta: '#1e4398', Media: '#3f82c9', Baixa: '#9ecbed'}},
    'suscetibilidade-movimento-massa': {color: '#af5521', categories: 'Classe', colors: {Alta: '#a93a22', Media: '#d07c21', Baixa: '#e9b652'}},
    predios_publicos: {pane: 'localities', color: '#a03d74', categories: 'tipo', label: 'nome'},
    ovitrampas: {pane: 'localities', color: '#6b5294', label: 'ovitrampa_id', categories: 'resultado',
      colors: {Positiva: '#b32e3b', Negativa: '#25866c', 'Sem contagem': '#656e73'}},
    pontos_estrategicos: {pane: 'localities', color: '#975521', label: 'nome', categories: 'tipo'},
    acoes_atendimentos: {pane: 'localities', color: '#235786', label: 'rotulo', categories: 'tipo'},
    esporotricose: {pane: 'imported', color: '#ae412e', label: 'rotulo', categories: 'posicao_cadastrada',
      colors: {'Dentro do limite municipal': '#ae412e', 'Fora do limite municipal': '#644191', 'Limite municipal indisponível': '#ae412e'}},
  };

  const palette = ['#157157', '#365eb3', '#965331', '#713996', '#9a5821', '#237383', '#a33558', '#626d1e', '#345687',
    '#ba492f', '#0e667e', '#8f3c88', '#455d26', '#526ba0', '#a64751', '#217566', '#856515', '#56496d', '#99653a'];
  const propertyLabels = {id_quart: 'Quarteirão', Localidade_nome: 'Localidade', id_Q_antig: 'Número anterior',
    codigo_pe: 'Código do ponto', ovitrampa_id: 'Ovitrampa', NOME: 'Nome', Name: 'Nome',
    data_coleta: 'Data de coleta', CdFerrovia: 'Código da ferrovia', TIPO_DRENA: 'Tipo de drenagem',
    bairro_loteamento: 'Bairro ou loteamento', status_funcionamento: 'Situação', horario: 'Horário de atendimento',
    servicos_no_local: 'Serviços no local', gestao: 'Gestão', codigo_oficial: 'Código oficial', uid: 'Identificador'};
  const propertyName = key => propertyLabels[key] || key.replaceAll('_', ' ').replace(/^./, text => text.toLocaleUpperCase('pt-BR'));
  const normalText = text => String(text ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('pt-BR').trim();
  const detailKeys = props => Object.keys(props).filter(key => !['chave', 'id_localidade', 'Localidade', 'quarteirao_raw'].includes(key)
    && props[key] != null && props[key] !== '' && typeof props[key] !== 'object');

  function showFeature(input, props, name, attribute, latlng, paginaEdicao) {
    const box = element('div', 'geo-info-popup');
    const details = element('dl');
    for (const key of detailKeys(props)) {
      if (key !== attribute) details.append(element('dt', '', propertyName(key)), element('dd', '', String(props[key]).slice(0, 400)));
    }
    box.append(element('strong', '', name || input.dataset.nome), details);
    if (paginaEdicao) {
      const link = element('a', 'geo-editar-ponto', 'Editar equipamento');
      link.href = paginaEdicao;
      box.append(link);
    }
    L.popup({maxHeight: 260}).setLatLng(latlng).setContent(box).openOn(map);
  }

  function publicSymbol(tipo) {
    const nome = normalText(tipo);
    if (nome.includes('saude')) return ['quadrado', '+'];
    if (nome.includes('escola') || ['em', 'erm', 'cmei', 'conveniada'].includes(nome)) return ['quadrado', 'E'];
    if (nome === 'ponto de interesse') return ['losango', ''];
    if (nome.includes('social')) return ['losango', ''];
    if (nome.includes('administracao')) return ['quadrado', 'A'];
    if (nome.includes('cultura')) return ['triangulo', ''];
    if (nome.includes('seguranca')) return ['quadrado', 'S'];
    return ['circulo', ''];
  }

  function buildLayer(input, data) {
    const id = input.dataset.layer;
    const versaoEditavel = marcarEquipamento && id === 'predios_publicos' && Number.isInteger(data.metadata?.versao);
    const indices = versaoEditavel ? new Map(data.features.map((feature, indice) => [feature, indice])) : null;
    const config = JSON.parse(input.dataset.estilo);
    const base = Object.hasOwn(defaults, id) ? defaults[id] : {color: '#175cd3'};
    const pane = base.pane || (input.dataset.tipo === 'poligono' ? 'areas' : 'imported');
    const category = config.atributo_cor || base.categories;
    const categories = [...new Set(data.features.map(feature => String(feature.properties?.[category] ?? '')).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'pt-BR'));
    const color = (feature) => {
      const props = feature.properties || {};
      const value = Object.hasOwn(props, category) ? String(props[category] ?? '') : '';
      if (Object.hasOwn(config.cores, value)) return config.cores[value];
      if (!config.atributo_cor && value) {
        if (base.colors && Object.hasOwn(base.colors, value)) return base.colors[value];
        return palette[categories.indexOf(value) % palette.length];
      }
      return '';
    };
    const trace = config.linha || base.line;
    const group = L.geoJSON(data, {
      pane,
      style(feature) {
        const cor = color(feature) || config.cor || base.color;
        if (['Point', 'MultiPoint'].includes(feature.geometry.type)) {
          return {color: config.cor || '#fff', weight: config.largura ?? 2, opacity: config.opacidade ?? 1,
            fillColor: config.cor_preenchimento || cor, fillOpacity: config.opacidade_preenchimento ?? 1};
        }
        return {color: cor, weight: config.largura ?? base.weight ?? 2, opacity: config.opacidade ?? base.opacity ?? 1,
          fill: /Polygon$/.test(feature.geometry.type) && (!base.noFill || (config.opacidade_preenchimento ?? 0) > 0),
          fillColor: color(feature) || config.cor_preenchimento || base.fillColor || cor,
          fillOpacity: config.opacidade_preenchimento ?? base.fillOpacity ?? .24,
          dashArray: {tracejada: '7 5', pontilhada: '1 5'}[trace] || null};
      },
      pointToLayer(feature, latlng) {
        const count = Number(feature.properties?.animais || 0);
        const [shape, symbol] = id === 'predios_publicos' ? publicSymbol(feature.properties?.tipo) : ['circulo', ''];
        const point = config.ponto || shape;
        if (point !== 'circulo' || symbol) {
          const size = 2 * (config.raio ?? 8);
          const icon = element('span', `geo-point geo-point--${point}`, symbol);
          icon.style.setProperty('--point-fill', config.cor_preenchimento || color(feature) || config.cor || base.color);
          icon.style.setProperty('--point-stroke', config.cor || '#fff');
          icon.style.setProperty('--point-stroke-width', `${config.largura ?? 1.5}px`);
          return L.marker(latlng, {pane, opacity: config.opacidade_preenchimento ?? config.opacidade ?? 1,
            title: String(feature.properties?.nome || input.dataset.nome), icon: L.divIcon({
              className: 'geo-point-icon', html: icon, iconSize: [size, size],
            })});
        }
        const radius = config.raio ?? (id === 'esporotricose' ? 5 + Math.min(12, Math.sqrt(count) * 2) : 6);
        return L.circleMarker(latlng, {pane, radius});
      },
      onEachFeature(feature, layer) {
        const props = feature.properties || {};
        const attribute = config.rotulo || base.label;
        let name = Object.hasOwn(props, attribute) ? props[attribute] : null;
        let label = name;
        if (id === 'quarteiroes') {
          if (props.chave) blockIndex.set(String(props.chave), layer);
          if (name == null) name = `Q. ${props.id_quart}${props.Localidade_nome ? ` · ${props.Localidade_nome}` : ''}`;
          label ??= props.id_quart ? `Q. ${props.id_quart}` : '';
        } else if (id === 'localidades') {
          localityIndex.set(String(props.id_localidade), layer);
        }
        const isLine = /LineString$/.test(feature.geometry.type);
        const along = (config.rotulo_modo || (isLine ? 'linha' : 'centro')) === 'linha' && isLine;
        if (label != null && label !== '' && config.rotulo_modo !== 'oculto') {
          labels.add(layer, label, {along, group: id, zoom: config.rotulo_zoom ?? base.labelZoom ?? (isLine ? 17 : 16),
            color: config.rotulo_cor || base.labelColor, size: config.rotulo_tamanho ?? (along ? 11 : 12)});
          layer.bindTooltip(element('span', '', name), {sticky: true});
        }
        if (isLine && trace === 'ferrovia') {
          const sleepers = L.polyline(layer.getLatLngs(), {pane, interactive: false, color: color(feature) || config.cor || base.color,
            dashArray: '2 9', lineCap: 'butt', weight: (config.largura ?? base.weight ?? 2) + 5,
            opacity: config.opacidade ?? base.opacity ?? 1});
          layer.on('add', () => { sleepers.addTo(map).bringToBack(); });
          layer.on('remove', () => sleepers.remove());
        }
        layer.on('click', event => {
          if (measure.active() || marcandoEquipamento) return;
          if (id === 'quarteiroes' && podeRg && props.chave) showBlock(props.Localidade, props.id_quart, layer);
          else {
            const indice = indices?.get(feature);
            const edicao = Number.isInteger(indice) && feature.geometry.type === 'Point'
              ? `/geovsatt/admin/equipamentos/${data.metadata.versao}/${indice}/editar` : '';
            showFeature(input, props, name, attribute, event.latlng, edicao);
          }
        });
      },
    });
    if (category) {
      legendasPorCamada.set(group, layer => {
        const valor = String(layer.feature.properties?.[category] ?? '').trim();
        return valor ? [valor, color(layer.feature) || config.cor || base.color] : null;
      });
    }
    setupFilters(input, group);
    return group;
  }

  function setupFilters(input, group) {
    const container = document.getElementById(`geo-filter-${input.dataset.layer}`);
    const features = group.getLayers();
    const fields = [...new Set(features.flatMap(layer => detailKeys(layer.feature.properties || {})))];
    if (!container || !fields.length) return;
    fields.sort((a, b) => propertyName(a).localeCompare(propertyName(b), 'pt-BR'));
    const filter = element('details');
    const summary = element('summary', '', 'Filtros');
    const rules = element('div', 'geo-filter-rules');
    const actions = element('div', 'geo-filter-actions');
    const add = element('button', '', 'Adicionar filtro');
    const clear = element('button', '', 'Limpar');
    add.type = clear.type = 'button';
    actions.append(add, clear);
    filter.append(summary, rules, actions);
    container.replaceChildren(filter);

    const tipos = new Map();
    const iso = /^\d{4}-\d{2}-\d{2}(?:$|[T ])/;
    const operadoresTexto = [['contains', 'Contém'], ['exact', 'Igual a'], ['not_equal', 'Diferente de'],
      ['empty', 'Está vazio'], ['filled', 'Está preenchido']];
    const semValor = new Set(['empty', 'filled']);
    function tipoCampo(campo) {
      if (!tipos.has(campo)) {
        const valores = features.map(layer => layer.feature.properties?.[campo]).filter(v => v != null && v !== '');
        let tipo = 'texto';
        if (valores.every(Number.isFinite)) tipo = 'numero';
        else if (valores.every(valor => iso.test(valor))) tipo = 'data';
        tipos.set(campo, tipo);
      }
      return tipos.get(campo);
    }

    function ler() {
      return [...rules.children].flatMap(row => {
        const [field, match, value] = row.querySelectorAll('select, input');
        return value.value.trim() || semValor.has(match.value) ? [{field: field.value, match: match.value, value: value.value.trim()}] : [];
      });
    }

    function apply() {
      const active = ler().map(regra => ({...regra, tipo: tipoCampo(regra.field), normal: normalText(regra.value)}));
      let count = 0;
      for (const layer of features) {
        const show = active.every(rule => {
          const bruto = layer.feature.properties?.[rule.field];
          const value = normalText(bruto);
          switch (rule.match) {
            case 'empty': return !value;
            case 'filled': return Boolean(value);
            case 'exact': return value === rule.normal;
            case 'not_equal': return value !== rule.normal;
            case 'gte':
            case 'lte': {
              if (!value) return false;
              const atual = rule.tipo === 'data' ? String(bruto).slice(0, 10) : Number(bruto);
              const esperado = rule.tipo === 'data' ? rule.value : Number(rule.value);
              return rule.match === 'gte' ? atual >= esperado : atual <= esperado;
            }
            default: return value.includes(rule.normal);
          }
        });
        if (show) {
          count += 1;
          if (!group.hasLayer(layer)) group.addLayer(layer);
        } else if (group.hasLayer(layer)) group.removeLayer(layer);
      }
      summary.textContent = active.length ? `Filtros · ${number(count)}/${number(features.length)}` : 'Filtros';
      updateBounds();
      labels.schedule();
    }

    let serial = 0;
    function addRule(inicial = {}) {
      const row = element('div', 'geo-filter-rule');
      const field = element('select');
      field.setAttribute('aria-label', 'Campo do filtro');
      for (const name of fields) field.add(new Option(propertyName(name), name));
      if (inicial.field) field.value = inicial.field;
      const match = element('select');
      match.setAttribute('aria-label', 'Tipo de comparação');
      const value = element('input');
      value.setAttribute('aria-label', 'Valor do filtro');
      value.placeholder = 'Digite ou selecione um valor';
      value.maxLength = 400;
      const values = element('datalist');
      values.id = `${container.id}-values-${++serial}`;
      value.setAttribute('list', values.id);
      const remove = element('button', '', 'Remover');
      remove.type = 'button';
      const updateValues = () => {
        const options = new Set(features.map(layer => String(layer.feature.properties?.[field.value] ?? '')).filter(Boolean));
        values.replaceChildren(...[...options].slice(0, 100).sort((a, b) => a.localeCompare(b, 'pt-BR')).map(text => new Option(text)));
      };
      const ajustarEntrada = () => {
        const tipo = tipoCampo(field.value);
        const limite = ['gte', 'lte'].includes(match.value);
        value.hidden = semValor.has(match.value);
        value.type = limite ? (tipo === 'data' ? 'date' : 'number') : 'text';
        if (value.type === 'number') value.step = 'any';
      };
      const atualizarOperadores = () => {
        const tipo = tipoCampo(field.value);
        const operadores = [...operadoresTexto];
        if (tipo === 'numero') operadores.push(['gte', 'Maior ou igual a'], ['lte', 'Menor ou igual a']);
        if (tipo === 'data') operadores.push(['gte', 'A partir de'], ['lte', 'Até']);
        match.replaceChildren(...operadores.map(([codigo, rotulo]) => new Option(rotulo, codigo)));
      };
      field.addEventListener('change', () => {
        value.value = ''; atualizarOperadores(); ajustarEntrada(); updateValues(); apply();
      });
      match.addEventListener('change', () => { ajustarEntrada(); apply(); });
      value.addEventListener('change', apply);
      value.addEventListener('keydown', event => { if (event.key === 'Enter') apply(); });
      remove.addEventListener('click', () => { row.remove(); add.disabled = false; apply(); });
      row.append(field, match, value, values, remove);
      rules.append(row);
      add.disabled = rules.childElementCount >= 4;
      updateValues();
      atualizarOperadores();
      const aplicavel = !inicial.match || [...match.options].some(opcao => opcao.value === inicial.match);
      if (aplicavel && inicial.match) match.value = inicial.match;
      ajustarEntrada();
      if (aplicavel && inicial.value) value.value = inicial.value;
      return aplicavel;
    }
    add.addEventListener('click', () => addRule());
    clear.addEventListener('click', () => { rules.replaceChildren(); addRule(); apply(); });
    addRule();
    filtrosPorCamada.set(input.dataset.layer, {ler, restaurar(registros) {
      if (JSON.stringify(ler()) === JSON.stringify(registros)) return 0;
      let ignorados = 0;
      rules.replaceChildren();
      for (const registro of registros) {
        if (!fields.includes(registro.field) || !addRule(registro)) ignorados += 1;
      }
      if (!rules.childElementCount) addRule();
      apply();
      return ignorados;
    }});
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

  function itensLegenda(recorte = null) {
    const labels = [];
    for (const input of options) {
      const id = input.dataset.layer;
      const layer = mapLayers[id];
      if (!layer || !map.hasLayer(layer)) continue;
      const limites = layer.getBounds();
      if (recorte && (!limites.isValid() || !recorte.intersects(limites))) continue;
      const key = element('i', 'legend-' + input.dataset.tipo);
      const baseColor = Object.hasOwn(defaults, id) ? defaults[id].color : '#175cd3';
      const style = JSON.parse(input.dataset.estilo);
      const classificar = legendasPorCamada.get(layer);
      const classes = new Map();
      if (classificar) layer.eachLayer(item => {
        if (recorte) {
          const ponto = item.getLatLng?.();
          const caixa = ponto ? null : item.getBounds();
          if (ponto ? !recorte.contains(ponto) : !caixa.isValid() || !recorte.intersects(caixa)) return;
        }
        const categoria = classificar(item);
        if (categoria) classes.set(...categoria);
      });
      const rules = [...classes].sort(([a], [b]) => a.localeCompare(b, 'pt-BR', {numeric: true}));
      key.style.setProperty('--legend-color', style.cor || rules[0]?.[1] || baseColor);
      const label = element('span');
      if (rules.length) {
        label.title = rules.slice(0, 16).map(([value, color]) => `${value}: ${color}`).join('\n');
        label.dataset.categorias = JSON.stringify(rules);
      }
      label.append(key, document.createTextNode(input.dataset.nome));
      labels.push(label);
    }
    return labels;
  }

  function updateBounds() {
    fullBounds = L.latLngBounds([]);
    for (const layer of Object.values(mapLayers)) {
      const bounds = layer.getBounds();
      if (map.hasLayer(layer) && bounds.isValid()) fullBounds.extend(bounds);
    }
    const legend = document.getElementById('geo-legend');
    legend.replaceChildren(...itensLegenda());
    legend.hidden = !legend.childElementCount;
  }

  const mapLayers = Object.create(null);
  async function toggleLayer(input) {
    const id = input.dataset.layer;
    const container = document.getElementById(`geo-filter-${id}`);
    if (input.checked) {
      const layer = await loadLayer(input);
      mapLayers[id] = layer;
      if (input.checked) layer.addTo(map);
    } else if (mapLayers[id]) {
      map.removeLayer(mapLayers[id]);
      if (id === 'quarteiroes') clearHighlight();
    }
    if (container) container.hidden = !input.checked || !container.childElementCount;
    updateBounds();
    labels.schedule();
  }

  function reportLayerError(input, error) {
    input.checked = false;
    const filter = document.getElementById(`geo-filter-${input.dataset.layer}`);
    if (filter) filter.hidden = true;
    statusNode.textContent = `${input.dataset.nome}: ${error.message}`;
  }

  options.forEach(input => input.addEventListener('change', () => {
    toggleLayer(input).catch(error => reportLayerError(input, error));
  }));
  window.GeoVSATTImpressao.create(map, baseSelect, measure, estadoBase, options, toggleLayer, itensLegenda,
    {api, filtrosPorCamada});
  document.getElementById('geo-fit').addEventListener('click', () => {
    if (fullBounds?.isValid()) map.fitBounds(fullBounds, {padding: [24, 24]});
  });

  function showSearch(items, cep, suggestions = false) {
    searchResults.replaceChildren();
    const rotulo = suggestions ? ['sugestão', 'sugestões'] : ['resultado', 'resultados'];
    searchFeedback.textContent = items.length ? `${items.length} ${rotulo[Number(items.length > 1)]} do mapa.` : '';
    if (cep) {
      const referencia = [cep.logradouro, cep.complemento, cep.bairro,
        [cep.municipio, cep.uf].filter(Boolean).join(' – ')].filter(Boolean);
      const card = element('div', 'geo-search-result geo-search-info');
      card.append(element('strong', '', `CEP ${cep.cep} · ${cep.fonte || 'BrasilAPI'}`),
        element('span', '', referencia.join(' · ') || 'Endereço indisponível'));
      searchResults.append(card);
    }
    if (!items.length && suggestions) {
      searchResults.hidden = true;
      return;
    }
    if (!items.length) {
      const aviso = cep ? (cep.municipio_rg ? 'Nenhum logradouro correspondente no RG.' : 'Este CEP está fora do município do RG.')
        : 'Nenhum resultado encontrado.';
      searchResults.append(element('div', 'geo-search-result geo-search-info', aviso));
      searchFeedback.textContent = aviso;
      searchResults.hidden = false;
      return;
    }
    for (const item of items) {
      const button = element('button', 'geo-search-result');
      button.type = 'button';
      const postalSuggestion = suggestions && searchSource.value === 'logradouro';
      button.append(element('strong', '', postalSuggestion ? item.logradouro : item.titulo),
        element('span', '', postalSuggestion ? 'Usar esse logradouro na pesquisa de CEP' : item.subtitulo));
      button.addEventListener('click', async () => {
        cancelSuggestions();
        searchSequence += 1;
        searchResults.hidden = true;
        if (postalSuggestion) {
          searchInput.value = item.logradouro;
          searchInput.focus();
          searchFeedback.textContent = 'Logradouro selecionado. Acione Buscar para consultar o CEP.';
          return;
        }
        const id = item.tipo === 'localidade' ? 'localidades' : 'quarteiroes';
        const input = options.find(option => option.dataset.layer === id);
        if (!input) return;
        input.checked = true;
        try {
          await toggleLayer(input);
        } catch (error) {
          reportLayerError(input, error);
          return;
        }
        if (id === 'quarteiroes') {
          const layer = blockIndex.get(String(item.chave));
          showBlock(item.id_localidade, item.quarteirao, layer, item.imoveis);
        } else {
          clearHighlight();
          detailSequence += 1;
          openDetail(false);
          const layer = localityIndex.get(String(item.id_localidade));
          if (layer?.getBounds) map.fitBounds(layer.getBounds(), {maxZoom: 17, padding: [44, 50]});
          else if (layer?.getLatLng) map.setView(layer.getLatLng(), 15);
        }
      });
      searchResults.append(button);
    }
    searchResults.hidden = false;
  }

  const submitSearch = (url, fields, signal) => api(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name="csrf-token"]').content},
    body: JSON.stringify(fields), signal,
  });
  const searchRG = async (term, suggestion = false, signal) => {
    const data = await submitSearch('/api/geovsatt/busca',
      {q: term, sugestao: suggestion, logradouro: suggestion && searchSource.value === 'logradouro'}, signal);
    return data.resultados;
  };

  function showPostalResults(resultados) {
    searchResults.replaceChildren();
    const feedback = resultados.length ? `${resultados.length} ${resultados.length === 1 ? 'CEP encontrado' : 'CEPs encontrados'}`
      : 'Nenhum CEP encontrado para esse logradouro em Almirante Tamandaré.';
    searchFeedback.textContent = feedback;
    searchResults.append(element('div', 'geo-search-result geo-search-info', `${feedback} · ViaCEP`));
    for (const item of resultados) {
      const card = element('div', 'geo-search-result geo-search-info');
      card.append(element('strong', '', item.cep),
        element('span', '', [item.logradouro, item.complemento, item.bairro].filter(Boolean).join(' · ')));
      if (podeRg && options.some(camada => camada.dataset.layer === 'quarteiroes')) {
        const locate = element('button', 'geo-search-map-link', 'Procurar no RG');
        locate.type = 'button';
        locate.setAttribute('aria-label', `Procurar ${item.logradouro} no RG, CEP ${item.cep}`);
        locate.addEventListener('click', async () => {
          const sequence = ++searchSequence;
          locate.disabled = true;
          try {
            const cep = {...item, municipio_rg: true, fonte: 'ViaCEP'};
            const ruas = list => list.filter(result => result.tipo === 'endereco');
            let items = ruas(await searchRG([item.logradouro, item.bairro].filter(Boolean).join(', ')));
            if (item.bairro && !items.length && sequence === searchSequence) items = ruas(await searchRG(item.logradouro));
            if (sequence === searchSequence) showSearch(items, cep);
          } catch (error) {
            if (sequence === searchSequence) showSearchError(error);
          } finally {
            locate.disabled = false;
          }
        });
        card.append(locate);
      }
      searchResults.append(card);
    }
  }

  function showSearchError(error) {
    searchResults.replaceChildren(element('div', 'geo-search-result geo-search-info', error.message));
    searchFeedback.textContent = error.message;
  }

  function cancelSuggestions() {
    clearTimeout(suggestionTimer);
    suggestionRequest?.abort();
    suggestionRequest = null;
  }

  searchInput.addEventListener('input', () => {
    cancelSuggestions();
    const sequence = ++searchSequence;
    searchResults.hidden = true;
    const query = searchInput.value.trim();
    searchFeedback.textContent = '';
    if (!podeRg || searchSource.value === 'cep' || query.length < 3 || /^\d{5}-?\d*$/.test(query)) return;
    suggestionTimer = setTimeout(async () => {
      const request = new AbortController();
      suggestionRequest = request;
      try {
        const items = await searchRG(query, true, request.signal);
        if (sequence === searchSequence) showSearch(items, null, true);
      } catch {
        if (sequence === searchSequence) searchResults.hidden = true;
      } finally {
        if (suggestionRequest === request) suggestionRequest = null;
      }
    }, 380);
  });

  searchForm.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      cancelSuggestions();
      searchSequence += 1;
      searchResults.hidden = true;
      searchFeedback.textContent = '';
      searchInput.focus();
    }
    if (searchResults.hidden || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    const buttons = [...searchResults.querySelectorAll('button:enabled')];
    if (!buttons.length) return;
    event.preventDefault();
    const current = buttons.indexOf(document.activeElement);
    const next = event.key === 'ArrowDown' ? (current + 1) % buttons.length :
      (current < 1 ? buttons.length - 1 : current - 1);
    buttons[next].focus();
  });

  searchSource.addEventListener('change', () => {
    cancelSuggestions();
    const cep = searchSource.value === 'cep';
    const postalAddress = searchSource.value === 'logradouro';
    searchInput.placeholder = cep ? 'Digite o CEP (00000-000)' :
      postalAddress ? 'Informe a rua em Almirante Tamandaré' : 'Rua e número, localidade ou quarteirão';
    searchInput.inputMode = cep ? 'numeric' : 'search';
    searchInput.maxLength = cep ? 9 : 180;
    searchSequence += 1;
    searchResults.hidden = true;
    searchInput.focus();
    searchInput.select();
    searchFeedback.textContent = '';
  });

  searchForm.addEventListener('submit', async event => {
    event.preventDefault();
    cancelSuggestions();
    const query = searchInput.value.trim();
    if (!query) return;
    const sequence = ++searchSequence;
    searchResults.hidden = false;
    searchResults.replaceChildren(element('div', 'geo-search-result geo-search-info', 'Buscando...'));
    searchFeedback.textContent = 'Buscando.';
    try {
      let cep;
      let items;
      if (searchSource.value === 'logradouro') {
        const data = await submitSearch('/api/geovsatt/ceps-por-logradouro', {logradouro: query});
        if (sequence === searchSequence) showPostalResults(data.resultados);
        return;
      }
      if (searchSource.value === 'cep' || /^\d{5}-?\d{3}$/.test(query)) {
        if (!/^\d{5}-?\d{3}$/.test(query)) throw Error('Informe um CEP com oito dígitos.');
        cep = await api(`/api/geovsatt/cep/${encodeURIComponent(query)}`);
        items = cep.municipio_rg && cep.logradouro ? await searchRG(cep.logradouro) : [];
      } else {
        items = await searchRG(query);
      }
      if (sequence === searchSequence) showSearch(items, cep);
    } catch (error) {
      if (sequence === searchSequence) showSearchError(error);
    }
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.geo-search')) {
      cancelSuggestions();
      searchSequence += 1;
      searchResults.hidden = true;
    }
  });

  const initial = options.filter(input => input.checked);
  Promise.allSettled(initial.map(toggleLayer)).then(results => {
    if (fullBounds?.isValid()) map.fitBounds(fullBounds, {padding: [24, 24]});
    if (!marcandoEquipamento) statusNode.textContent = '';
    results.forEach((result, i) => {
      if (result.status === 'rejected') reportLayerError(initial[i], result.reason);
    });
  });
})();
