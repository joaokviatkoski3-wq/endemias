function iniciarGeoVSATT() {
  'use strict';
  const mapNode = document.getElementById('geo-map');
  if (!mapNode || !window.L) return;
  const campo = window.GeoVSATTCampo;
  const statusNode = document.getElementById('geo-status');
  const marcarEquipamento = document.getElementById('geo-marcar-equipamento');
  const sidebar = document.getElementById('geo-sidebar');
  const backdrop = document.getElementById('geo-sidebar-backdrop');
  const detail = document.getElementById('geo-detail');
  const detailContent = document.getElementById('geo-detail-content');
  const detailTitle = document.getElementById('geo-detail-title');
  const detailSource = document.getElementById('geo-detail-source');
  const searchForm = document.getElementById('geo-search');
  const searchInput = document.getElementById('geo-search-input');
  const searchSource = document.getElementById('geo-search-source');
  const searchResults = document.getElementById('geo-search-results');
  const searchFeedback = document.getElementById('geo-search-feedback');
  const podeRg = document.querySelector('.geo-shell').dataset.podeRg === '1';
  const layers = new Map();
  const options = [...document.querySelectorAll('[data-layer]:enabled')];
  const legendasPorCamada = new WeakMap();
  const periodoPorCamada = new WeakMap();
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
    if (campo) return campo.api(url, options);
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
  map.createPane('block-work').style.zIndex = 335;
  map.createPane('block-coverage').style.zIndex = 342;
  map.createPane('block-radii').style.zIndex = 348;
  map.createPane('imported').style.zIndex = 370;
  map.createPane('localities').style.zIndex = 450;
  map.createPane('rg-selection').style.zIndex = 460;
  L.control.zoom({position: 'topright'}).addTo(map);
  map.setView([-25.32, -49.30], 12);
  if (!campo) document.addEventListener('geovsatt:obter-recorte-offline', event => {
    const bounds = map.getBounds();
    event.detail.limites = [Math.max(-180, bounds.getWest()), Math.max(-90, bounds.getSouth()),
      Math.min(180, bounds.getEast()), Math.min(90, bounds.getNorth())];
  });
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
  const ortoInfo = document.getElementById('geo-ortofoto-info');
  const ortoDownload = document.getElementById('geo-ortofoto-baixar');
  const lerOrtofoto = () => JSON.parse(baseSelect.selectedOptions[0]?.dataset.ortofoto || 'null');
  const coberturaOrtofoto = ({limites: [oeste, sul, leste, norte]}) => L.latLngBounds([sul, oeste], [norte, leste]);
  document.getElementById('geo-ortofoto-enquadrar').addEventListener('click', () => {
    const orto = lerOrtofoto();
    if (orto) map.fitBounds(coberturaOrtofoto(orto), {maxZoom: orto.zoom_max, padding: [30, 30]});
  });
  baseSelect.addEventListener('change', async () => {
    const sequence = ++baseSequence;
    if (activeBasemap) map.removeLayer(activeBasemap);
    activeBasemap = null;
    vectorMap = null;
    basePending = false;
    baseFailed = false;
    statusNode.textContent = '';
    const baseLabel = document.getElementById('geo-base-label');
    const orto = lerOrtofoto();
    ortoInfo.hidden = !orto;
    ortoDownload.hidden = true;
    ortoDownload.removeAttribute('href');
    if (orto) {
      const codigo = encodeURIComponent(orto.id);
      const fonte = [orto.fonte, orto.data_referencia, orto.licenca].filter(Boolean).join(' · ');
      document.getElementById('geo-ortofoto-fonte').textContent = fonte;
      if (orto.pode_exportar && !campo) {
        ortoDownload.href = `/geovsatt/camadas/${codigo}/exportar/mbtiles`;
        ortoDownload.hidden = false;
      }
      baseLabel.textContent = orto.nome;
      const opcoes = {
        bounds: coberturaOrtofoto(orto), minNativeZoom: orto.zoom_min, maxNativeZoom: orto.zoom_max,
        maxZoom: map.getMaxZoom(), noWrap: true, attribution: element('span', '', fonte).innerHTML,
      };
      if (campo) {
        activeBasemap = L.gridLayer(opcoes);
        activeBasemap.createTile = (coordenada, pronto) => {
          const src = campo.mosaico(orto.id, coordenada);
          const tile = element(src ? 'img' : 'div');
          if (src) {
            tile.alt = '';
            tile.onload = () => pronto(null, tile);
            tile.onerror = () => pronto(Error('Mosaico indisponível na cópia.'), tile);
            tile.src = src;
          } else {
            queueMicrotask(() => pronto(null, tile));
          }
          return tile;
        };
      } else {
        activeBasemap = L.tileLayer(`/api/geovsatt/ortofotos/${codigo}/${orto.versao}/{z}/{x}/{y}`, opcoes);
      }
      activeBasemap.on('tileerror', () => {
        if (sequence !== baseSequence) return;
        baseFailed = true;
        statusNode.textContent = campo ? 'Um mosaico da cópia não carregou.' :
          'A ortofoto não carregou. Atualize a página para conferir a versão ativa.';
      }).addTo(map);
      return;
    }
    if (baseSelect.value === 'openfreemap') {
      baseLabel.textContent = 'OpenStreetMap · OpenFreeMap';
      statusNode.textContent = 'Carregando a base vetorial…';
      basePending = true;
      try {
        const versao = encodeURIComponent(document.documentElement.dataset.versao);
        const {criarBaseVetorial, criarBaseVetorialOffline} = await import(`/static/js/geovsatt_vetorial.mjs?v=${versao}`);
        if (sequence !== baseSequence) return;
        const copia = campo?.baseVetorial;
        if (copia) {
          const area = coberturaOrtofoto({limites: copia.recorte});
          if (!options.some(input => input.checked) || !area.contains(map.getCenter())) {
            map.fitBounds(area, {maxZoom: 17, padding: [24, 24]});
          }
        }
        activeBasemap = copia ? criarBaseVetorialOffline(map, copia) : criarBaseVetorial(map);
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
  function fecharDetalhe() {
    detailSequence += 1;
    clearHighlight();
    openDetail(false);
    mapNode.focus({preventScroll: true});
  }
  document.getElementById('geo-detail-close').addEventListener('click', fecharDetalhe);
  detail.addEventListener('keydown', event => {
    if (event.key === 'Escape') fecharDetalhe();
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
    detailSource.textContent = 'Registro Geográfico';
    openDetail(true);
    detailTitle.textContent = `Quarteirão ${block}`;
    detailContent.replaceChildren(element('p', 'geo-detail-loading', 'Carregando dados do Registro Geográfico...'));
    detailContent.scrollTop = 0;
    detailTitle.focus({preventScroll: true});
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


  const estilos = window.GeoVSATTEstilos;
  const propertyLabels = {id_quart: 'Quarteirão', Localidade_nome: 'Localidade', id_Q_antig: 'Número anterior',
    codigo_pe: 'Código do ponto', ovitrampa_id: 'Ovitrampa', NOME: 'Nome', Name: 'Nome',
    data_coleta: 'Data de coleta', CdFerrovia: 'Código da ferrovia', TIPO_DRENA: 'Tipo de drenagem',
    bairro_loteamento: 'Bairro ou loteamento', status_funcionamento: 'Situação', horario: 'Horário de atendimento',
    servicos_no_local: 'Serviços no local', gestao: 'Gestão', codigo_oficial: 'Código oficial', uid: 'Identificador',
    situacao_bloqueio: 'Situação do bloqueio', data_bloqueio: 'Data do bloqueio', raio_metros: 'Raio (m)',
    percentual_no_raio: 'Área do quarteirão dentro dos raios (%)', cobertura: 'Abrangência',
    casos_com_bloqueio_realizado: 'Casos com bloqueio realizado',
    casos_com_bloqueio_nao_realizado: 'Casos com bloqueio não realizado',
    casos_com_bloqueio_nao_necessario: 'Casos com bloqueio não necessário',
    casos_sem_situacao_padronizada: 'Casos sem situação padronizada', tipos_registrados: 'Registros por tipo',
    total_registros: 'Total de registros de visita', visitas_normais: 'Visitas normais',
    visitas_fechadas: 'Visitas com imóvel fechado', visitas_recuperadas: 'Visitas recuperadas',
    visitas_outras_situacoes: 'Registros com outra situação ou sem situação', ultimo_registro: 'Último registro no período'};
  const propertyName = key => propertyLabels[key] || key.replaceAll('_', ' ').replace(/^./, text => text.toLocaleUpperCase('pt-BR'));
  const normalText = text => String(text ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('pt-BR').trim();
  const detailKeys = props => Object.keys(props).filter(key => !['chave', 'id_localidade', 'Localidade', 'quarteirao_raw'].includes(key)
    && props[key] != null && props[key] !== '' && typeof props[key] !== 'object');

  function showFeature(fonte, props, name, attribute, latlng, action) {
    detailSequence += 1;
    clearHighlight();
    map.closePopup();
    detailSource.textContent = fonte;
    detailTitle.textContent = String(name ?? '').trim() || 'Detalhes da feição';
    const details = element('dl', 'geo-feature-details');
    for (const key of detailKeys(props)) {
      if (key !== attribute) details.append(element('dt', '', propertyName(key)), element('dd', '', props[key]));
    }
    detailContent.replaceChildren(details.childElementCount ? details :
      element('p', 'geo-detail-loading', 'Esta feição possui apenas a identificação acima.'));
    if (action) detailContent.append(action);
    openDetail(true);
    detailContent.scrollTop = 0;
    detailTitle.focus({preventScroll: true});
    if (map.getSize().x > 820) {
      map.panInside(latlng, {paddingTopLeft: [36, 40], paddingBottomRight: [detail.offsetWidth + 36, 44]});
    }
  }

  function buildLayer(input, data) {
    const id = input.dataset.layer;
    const versaoEditavel = marcarEquipamento && id === 'predios_publicos' && Number.isInteger(data.metadata?.versao);
    const indices = versaoEditavel ? new Map(data.features.map((feature, indice) => [feature, indice])) : null;
    const config = JSON.parse(input.dataset.estilo);
    const base = estilos.padraoDaCamada(id, data.metadata);
    const pane = base.pane || (input.dataset.tipo === 'poligono' ? 'areas' : 'imported');
    const classificar = estilos.classificador(config, base, data.features);
    const classes = new WeakMap();
    const classeDe = feature => {
      if (!classes.has(feature)) classes.set(feature, classificar(feature.properties));
      return classes.get(feature);
    };
    const simboloDaFeicao = feature => estilos.simbolo(config, base, classeDe(feature), estilos.tipoDaGeometria(feature.geometry.type));
    const trace = config.linha || base.line;
    const group = L.geoJSON(data, {
      pane,
      style: simboloDaFeicao,
      pointToLayer(feature, latlng) {
        const {forma, glifo, icone, raio} = estilos.marcador(id, config, feature.properties || {});
        if (icone) {
          const size = 2 * raio;
          const icon = element('span', `geo-point geo-point--${forma}`, glifo);
          const simbolo = simboloDaFeicao(feature);
          icon.style.setProperty('--point-fill', simbolo.fillColor);
          icon.style.setProperty('--point-stroke', simbolo.color);
          icon.style.setProperty('--point-stroke-width', `${config.largura ?? 1.5}px`);
          return L.marker(latlng, {pane, opacity: config.opacidade_preenchimento ?? config.opacidade ?? 1,
            title: String(feature.properties?.nome || input.dataset.nome), icon: L.divIcon({
              className: 'geo-point-icon', html: icon, iconSize: [size, size],
            })});
        }
        return L.circleMarker(latlng, {pane, radius: raio});
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
        } else if (id === 'esporotricose_quarteiroes' || id === 'quarteiroes_trabalhados') {
          name ??= props.rotulo;
        }
        const isLine = /LineString$/.test(feature.geometry.type);
        const along = (config.rotulo_modo || (isLine ? 'linha' : 'centro')) === 'linha' && isLine;
        label = estilos.textoRotulo(config, label, props);
        if (label && config.rotulo_modo !== 'oculto') {
          const zoomMax = config.rotulo_zoom_max ?? map.getMaxZoom();
          const zoomMin = config.rotulo_zoom ?? Math.min(zoomMax, base.labelZoom ?? (isLine ? 17 : 16));
          labels.add(layer, label, {along, group: id, zoom: zoomMin, zoomMax,
            color: config.rotulo_cor || base.labelColor, size: config.rotulo_tamanho ?? (along ? 11 : 12),
            halo: config.rotulo_halo, haloColor: config.rotulo_halo_cor});
          layer.bindTooltip(element('span', '', label), {sticky: true});
        }
        if (isLine && trace === 'ferrovia') {
          const sleepers = L.polyline(layer.getLatLngs(), {pane, interactive: false, color: simboloDaFeicao(feature).color,
            dashArray: '2 9', lineCap: 'butt', weight: (config.largura ?? base.weight ?? 2) + 5,
            opacity: config.opacidade ?? base.opacity ?? 1});
          layer.on('add', () => { sleepers.addTo(map).bringToBack(); });
          layer.on('remove', () => sleepers.remove());
        }
        layer.on('click', event => {
          if (measure.active() || marcandoEquipamento) return;
          if (id === 'quarteiroes' && podeRg && props.chave) showBlock(props.Localidade, props.id_quart, layer);
          else {
            let action;
            const indice = indices?.get(feature);
            if (Number.isInteger(indice) && feature.geometry.type === 'Point') {
              action = element('a', 'geo-feature-action', 'Editar equipamento');
              action.href = `/geovsatt/admin/equipamentos/${data.metadata.versao}/${indice}/editar`;
            } else if (mapNode.dataset.ambiental && Number.isSafeInteger(feature.id) &&
                       (id === 'esporotricose' || id === 'esporotricose_bloqueios')) {
              action = element('a', 'geo-feature-action', 'Abrir mapa de bloqueio no Ambiental');
              action.href = `${mapNode.dataset.ambiental}/esporotricose/doentes/${feature.id}/mapa-bloqueio`;
              action.target = '_blank';
              action.rel = 'noopener noreferrer';
            } else if ((id === 'esporotricose_quarteiroes' || id === 'quarteiroes_trabalhados') && podeRg && props.chave) {
              action = element('button', 'geo-feature-action', 'Abrir detalhes no RG');
              action.type = 'button';
              action.addEventListener('click', () => {
                map.closePopup();
                showBlock(props.Localidade, props.id_quart, blockIndex.get(String(props.chave)) || layer);
              });
            }
            showFeature(input.dataset.nome, props, name, attribute || (name === props.rotulo ? 'rotulo' : ''), event.latlng, action);
          }
        });
      },
    });
    const temClasses = config.modo_cor !== 'unico' && Boolean(config.atributo_cor || base.categories);
    legendasPorCamada.set(group, {
      simbolo: layer => simboloDaFeicao(layer.feature),
      classe: temClasses ? layer => {
        const classe = classeDe(layer.feature);
        if (!classe) return null;
        const cor = estilos.corDoSimbolo(simboloDaFeicao(layer.feature), estilos.tipoDaGeometria(layer.feature.geometry.type));
        return {...classe, cor};
      } : null,
    });
    if (id === 'quarteiroes_trabalhados') {
      const {inicio, fim} = data.metadata.consulta;
      const formatarData = data => data.split('-').reverse().join('/');
      periodoPorCamada.set(group, `${formatarData(inicio)} a ${formatarData(fim)}`);
    }
    if (id !== 'quarteiroes_trabalhados' || campo) {
      setupFilters(input, group);
    }
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
      calor.atualizar(input.dataset.layer);
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

  function loadLayer(input, regras) {
    const id = input.dataset.layer;
    if (id === 'quarteiroes_trabalhados' && !campo) {
      const filtros = filtrosPorCamada.get(id);
      return filtros.consultar(regras ?? filtros.ler());
    }
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

  function regrasLegenda(layer, recorte) {
    const legenda = legendasPorCamada.get(layer);
    const classes = new Map();
    if (legenda?.classe) layer.eachLayer(item => {
      if (recorte) {
        const ponto = item.getLatLng?.();
        const caixa = ponto ? null : item.getBounds();
        if (ponto ? !recorte.contains(ponto) : !caixa.isValid() || !recorte.intersects(caixa)) return;
      }
      const categoria = legenda.classe(item);
      if (categoria) classes.set(categoria.ordem, categoria);
    });
    return [...classes.values()].sort((a, b) => a.ordem - b.ordem);
  }

  function simboloDoMenu(input, layer, regras) {
    const {tipo, layer: id} = input.dataset;
    const amostra = input.parentElement.querySelector('.geo-layer-symbol');
    const legenda = document.getElementById(`geo-key-${id}`);
    const primeira = layer?.getLayers()[0];
    const config = JSON.parse(input.dataset.estilo);
    const simbolo = primeira ? legendasPorCamada.get(layer).simbolo(primeira) :
      estilos.simbolo(config, estilos.padraoDaCamada(id), null, tipo);
    amostra.style.setProperty('--layer-line', simbolo.color);
    amostra.style.setProperty('--layer-fill', estilos.corDoSimbolo(simbolo, tipo));
    const opacidade = tipo === 'linha' ? simbolo.opacity : simbolo.fillOpacity;
    amostra.style.setProperty('--layer-opacity', tipo === 'poligono' && !simbolo.fill ? 0 : opacidade);
    amostra.classList.toggle('is-classified', regras.length > 1);
    if (regras.length > 1) {
      amostra.replaceChildren(...regras.slice(0, 4).map(({cor}) => {
        const segmento = element('i');
        segmento.style.backgroundColor = cor;
        return segmento;
      }));
    } else {
      amostra.replaceChildren();
    }
    legenda.hidden = !input.checked || !regras.length;
    const linhas = regras.slice(0, 60).map(({nome, cor}) => {
      const linha = element('li');
      const corNaLegenda = element('i');
      corNaLegenda.style.backgroundColor = cor;
      linha.append(corNaLegenda, document.createTextNode(nome));
      return linha;
    });
    if (regras.length > linhas.length) linhas.push(element('li', '', `Mais ${regras.length - linhas.length} categorias`));
    legenda.querySelector('ul').replaceChildren(...linhas);
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
      const style = JSON.parse(input.dataset.estilo);
      const simboloPadrao = estilos.simbolo(style, estilos.padraoDaCamada(id), null, input.dataset.tipo);
      const classes = regrasLegenda(layer, recorte);
      if (!recorte) simboloDoMenu(input, layer, classes);
      const rules = classes.map(({nome, cor}) => [nome, cor]);
      key.style.setProperty('--legend-color', rules[0]?.[1] || estilos.corDoSimbolo(simboloPadrao, input.dataset.tipo));
      const label = element('span');
      if (rules.length) {
        label.title = rules.slice(0, 16).map(([value, color]) => `${value}: ${color}`).join('\n');
        label.dataset.categorias = JSON.stringify(rules);
      }
      const periodo = periodoPorCamada.get(layer);
      label.append(key, document.createTextNode(input.dataset.nome + (periodo ? ` · ${periodo}` : '')));
      labels.push(label);
    }
    const camadaDeCalor = calor.legenda();
    if (camadaDeCalor) {
      const label = element('span');
      label.append(element('i', 'legend-calor'), document.createTextNode(`Densidade relativa · ${camadaDeCalor}`));
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
  const calor = window.GeoVSATTCalor.criar(map, options,
    input => mapLayers[input.dataset.layer] || loadLayer(input), updateBounds);
  if (!campo) document.addEventListener('geovsatt:obter-trabalhos-offline', event => {
    const regras = filtrosPorCamada.get('quarteiroes_trabalhados')?.ler() || [];
    const campos = {data_visita: {gte: 'inicio', lte: 'fim'}, tipo_trabalho: {exact: 'tipo'}, localidade_id: {exact: 'localidade'}};
    for (const {field, match, value} of regras) {
      const chave = campos[field]?.[match];
      if (chave) event.detail[chave] = value;
    }
  });

  function configurarFiltrosDeTrabalhos() {
    const id = 'quarteiroes_trabalhados';
    const input = options.find(opcao => opcao.dataset.layer === id);
    const form = document.getElementById('geo-filtros-trabalhos');
    if (!input || !form) return;
    const feedback = form.querySelector('[role="status"]');
    const resumo = form.closest('details').querySelector('summary');
    const botao = form.querySelector('[type="submit"]');
    const campos = [['inicio', 'data_visita', 'gte'], ['fim', 'data_visita', 'lte'],
      ['tipo', 'tipo_trabalho', 'exact'], ['localidade', 'localidade_id', 'exact']];
    const links = document.querySelectorAll(`[data-export-layer="${id}"] a`);
    let aplicadas = [];
    let chaveMapa = null;
    let statusMapa = '';
    let requisicao = null;

    const lerRegras = valores => campos.filter(([chave]) => valores[chave])
      .map(([chave, field, match]) => ({field, match, value: valores[chave]}));
    const lerParametros = regras => Object.fromEntries(campos.map(([chave, field, match]) => [
      chave, regras.find(regra => regra.field === field && regra.match === match)?.value || '',
    ]));
    const query = valores => new URLSearchParams(campos
      .map(([campo]) => [campo, valores[campo]]).filter(([, value]) => value)).toString();
    const quantidade = (total, singular, plural) => `${number(total)} ${total === 1 ? singular : plural}`;
    function bloquearCampos(bloqueados) {
      botao.disabled = bloqueados;
      for (const [campo] of campos) form.elements[campo].disabled = bloqueados;
    }
    function atualizarOpcoes(select, linhas, descricao, selecionada) {
      const opcoes = linhas.map(({codigo, nome}) => new Option(nome, codigo));
      if (selecionada && !linhas.some(({codigo}) => codigo === selecionada)) opcoes.push(new Option(selecionada, selecionada));
      select.replaceChildren(new Option(descricao, ''), ...opcoes);
    }

    function atualizarLinks(parametros) {
      for (const link of links) {
        const url = new URL(link.href);
        url.search = parametros;
        link.href = url.href;
      }
    }

    function registrar(data) {
      const {consulta, tipos, localidades, registros_no_recorte, registros_sem_malha} = data.metadata;
      aplicadas = lerRegras(consulta);
      chaveMapa = query(consulta);
      atualizarOpcoes(form.elements.tipo, tipos, 'Todos os tipos', consulta.tipo);
      atualizarOpcoes(form.elements.localidade, localidades, 'Todas as localidades', consulta.localidade);
      for (const [campo] of campos) form.elements[campo].value = consulta[campo];
      atualizarLinks(chaveMapa);
      const quarteiroes = quantidade(data.features.length, 'quarteirão', 'quarteirões');
      const registros = quantidade(registros_no_recorte, 'registro', 'registros');
      resumo.textContent = `Filtros das visitas · ${quarteiroes}`;
      statusMapa = `${quarteiroes} · ${registros} · ${number(registros_sem_malha)} sem geometria`;
      feedback.textContent = statusMapa;
    }

    function consultar(regras) {
      const chave = query(lerParametros(regras));
      if (requisicao?.chave === chave) return requisicao.promise;
      requisicao?.controller.abort();
      requisicao = null;
      if (chave === chaveMapa) {
        bloquearCampos(false);
        feedback.textContent = statusMapa;
        return Promise.resolve(mapLayers[id]);
      }
      const atual = {chave, controller: new AbortController()};
      requisicao = atual;
      bloquearCampos(true);
      feedback.textContent = 'Consultando visitas…';
      atual.promise = api(`/api/geovsatt/camadas/${id}?${chave}`, {signal: atual.controller.signal})
        .then(data => {
          if (requisicao !== atual) return null;
          if (mapLayers[id]) mapLayers[id].remove();
          labels.clearGroup(id);
          const camada = buildLayer(input, data);
          mapLayers[id] = camada;
          if (input.checked) camada.addTo(map);
          registrar(data);
          updateBounds();
          labels.schedule();
          return camada;
        })
        .catch(error => {
          if (requisicao !== atual) return null;
          feedback.textContent = error.message;
          throw error;
        })
        .finally(() => {
          if (requisicao === atual) {
            requisicao = null;
            bloquearCampos(false);
          }
        });
      return atual.promise;
    }

    form.addEventListener('submit', event => {
      event.preventDefault();
      const regras = lerRegras(Object.fromEntries(new FormData(form)));
      consultar(regras).catch(() => {});
    });
    filtrosPorCamada.set(id, {
      ler: () => aplicadas.slice(),
      consultar,
      pendente: () => Boolean(requisicao),
      async restaurar(regras) {
        if (input.checked) await consultar(regras);
        else {
          requisicao?.controller.abort();
          requisicao = null;
          bloquearCampos(false);
          aplicadas = regras;
          atualizarLinks(query(lerParametros(regras)));
        }
        return 0;
      },
    });
  }

  configurarFiltrosDeTrabalhos();

  async function toggleLayer(input, regras) {
    const id = input.dataset.layer;
    const container = document.getElementById(`geo-filter-${id}`);
    if (input.checked) {
      const layer = await loadLayer(input, regras);
      if (layer) {
        mapLayers[id] = layer;
        if (input.checked) layer.addTo(map);
      }
    } else if (mapLayers[id]) {
      map.removeLayer(mapLayers[id]);
      document.getElementById(`geo-key-${id}`).hidden = true;
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

  options.forEach(input => {
    simboloDoMenu(input, null, []);
    input.addEventListener('change', () => {
      toggleLayer(input).catch(error => reportLayerError(input, error));
    });
  });
  window.GeoVSATTImpressao.create(map, baseSelect, measure, estadoBase, options, toggleLayer, itensLegenda,
    {api, filtrosPorCamada});
  document.getElementById('geo-fit').addEventListener('click', () => {
    if (fullBounds?.isValid()) map.fitBounds(fullBounds, {padding: [24, 24]});
  });

  function showSearch(items, cep, suggestions = false) {
    searchResults.replaceChildren();
    const rotulo = suggestions ? ['sugestão', 'sugestões'] : ['resultado', 'resultados'];
    searchFeedback.textContent = items.length ? `${items.length} ${rotulo[Number(items.length > 1)]} do mapa.` : '';
    if (searchSource.value === 'nominatim') {
      const fonte = element('a', 'geo-search-result geo-search-info', 'Nominatim · © OpenStreetMap');
      fonte.href = 'https://www.openstreetmap.org/copyright';
      fonte.target = '_blank';
      fonte.rel = 'noopener noreferrer';
      searchResults.append(fonte);
    }
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
        if (item.tipo === 'nominatim') {
          const posicao = L.latLng(item.latitude, item.longitude);
          map.setView(posicao, 17);
          showFeature('Nominatim · OpenStreetMap', {
            precisao: 'Posição de referência da busca externa',
          }, item.titulo, '', posicao);
          highlighted = L.circleMarker(posicao, {
            pane: 'rg-selection', interactive: false, radius: 8,
            color: '#175cd3', fillColor: '#fff', weight: 3, fillOpacity: .9,
          }).addTo(map);
          return;
        }
        if (item.tipo === 'feicao') {
          const selecao = L.geoJSON(item.feature, {
            pane: 'rg-selection', style: {color: '#7a4300', weight: 3, fillOpacity: .12},
            pointToLayer: (feature, posicao) => L.circleMarker(posicao, {
              pane: 'rg-selection', radius: 8, color: '#7a4300', fillColor: '#fff', interactive: false,
            }),
            interactive: false,
          });
          const limites = selecao.getBounds();
          if (!limites.isValid()) return;
          map.fitBounds(limites, {maxZoom: 17, padding: [44, 50]});
          showFeature(item.subtitulo || 'Cópia offline', item.feature.properties || {}, item.titulo, '',
            limites.getCenter());
          highlighted = selecao.addTo(map);
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
    if ((!podeRg && !campo) || !['rg', 'logradouro'].includes(searchSource.value)
        || query.length < 3 || (!campo && /^\d{5}-?\d*$/.test(query))) return;
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
    const nominatim = searchSource.value === 'nominatim';
    searchInput.placeholder = cep ? 'Digite o CEP (00000-000)' :
      postalAddress ? 'Informe a rua em Almirante Tamandaré' :
        nominatim ? 'Rua ou local público em Almirante Tamandaré' : 'Rua e número, localidade ou quarteirão';
    searchInput.inputMode = cep ? 'numeric' : 'search';
    searchInput.maxLength = cep ? 9 : nominatim ? 120 : 180;
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
      if (searchSource.value === 'nominatim') {
        const data = await submitSearch('/api/geovsatt/nominatim', {q: query});
        if (sequence === searchSequence) showSearch(data.resultados, null);
        return;
      }
      if (searchSource.value === 'logradouro') {
        const data = await submitSearch('/api/geovsatt/ceps-por-logradouro', {logradouro: query});
        if (sequence === searchSequence) showPostalResults(data.resultados);
        return;
      }
      if (searchSource.value === 'cep' || (!campo && /^\d{5}-?\d{3}$/.test(query))) {
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
}

if (document.documentElement.dataset.offline === '1') {
  document.addEventListener('geovsatt:pacote-aberto', iniciarGeoVSATT, {once: true});
} else {
  iniciarGeoVSATT();
}
