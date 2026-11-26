import {addProtocol, setWorkerUrl} from 'maplibre-gl';
import {maplibreGL} from 'maplibre-leaflet';

const versao = encodeURIComponent(document.documentElement.dataset.versao);
setWorkerUrl(`/static/vendor/maplibre/maplibre-gl-worker.mjs?v=${versao}`);

const creditos = '<a href="https://openfreemap.org/">OpenFreeMap</a> · ' +
  '<a href="https://openmaptiles.org/">OpenMapTiles</a> · ' +
  '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a>';

function criarCamadaVetorial(map, opcoes) {
  const camada = maplibreGL({
    interactive: false,
    renderWorldCopies: false,
    trackResize: false,
    maxZoom: map.getMaxZoom(),
    canvasContextAttributes: {preserveDrawingBuffer: true},
    ...opcoes,
  });
  const remover = camada.onRemove;
  camada.onRemove = function (leaflet) {
    // Uma falha ao criar o WebGL pode deixar o contêiner já inserido pelo adaptador.
    if (this.getMaplibreMap()) remover.call(this, leaflet);
    else this.getContainer()?.remove();
  };
  return camada;
}

export function criarBaseVetorial(map) {
  return criarCamadaVetorial(map, {
    style: 'https://tiles.openfreemap.org/styles/positron',
    attributionControl: {customAttribution: creditos},
  });
}

export function criarBaseVetorialOffline(map, copia) {
  addProtocol('geovsatt-ofm', async parametros => {
    const url = new URL(parametros.url);
    const chave = url.hostname + decodeURIComponent(url.pathname);
    if (!Object.hasOwn(copia.recursos, chave)) {
      if (chave.startsWith('tile/') || chave.startsWith('fonte/')) return {data: new ArrayBuffer(0)};
      throw Error('Recurso do estilo ausente na cópia.');
    }
    const codificado = copia.recursos[chave];
    const dados = Uint8Array.fromBase64 ? Uint8Array.fromBase64(codificado) :
      Uint8Array.from(atob(codificado), letra => letra.charCodeAt(0));
    return {data: chave.endsWith('.json') ? JSON.parse(new TextDecoder().decode(dados)) : dados.buffer};
  });
  return criarCamadaVetorial(map, {style: copia.estilo, attributionControl: {customAttribution: creditos}});
}

export function criarMapaCalor(map, dados, raio) {
  return criarCamadaVetorial(map, {
    pane: 'heatmap',
    attributionControl: false,
    style: {
      version: 8,
      sources: {densidade: {type: 'geojson', data: dados}},
      layers: [{
        id: 'densidade', source: 'densidade', type: 'heatmap',
        paint: {
          'heatmap-weight': ['get', 'peso'],
          'heatmap-radius': raio,
          'heatmap-intensity': .85,
          'heatmap-opacity': .82,
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(49,87,182,0)',
            .2, '#3157b6', .4, '#39a9cc', .6, '#75cda0', .8, '#ffca55', 1, '#c1342f'],
        },
      }],
    },
  });
}
