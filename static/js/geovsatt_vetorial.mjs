import {setWorkerUrl} from 'maplibre-gl';
import {maplibreGL} from 'maplibre-leaflet';

const versao = encodeURIComponent(document.documentElement.dataset.versao);
setWorkerUrl(`/static/vendor/maplibre/maplibre-gl-worker.mjs?v=${versao}`);

const creditos = '<a href="https://openfreemap.org/">OpenFreeMap</a> · ' +
  '<a href="https://openmaptiles.org/">OpenMapTiles</a> · ' +
  '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a>';

export function criarBaseVetorial(map) {
  const camada = maplibreGL({
    style: 'https://tiles.openfreemap.org/styles/positron',
    attributionControl: {customAttribution: creditos},
    interactive: false,
    renderWorldCopies: false,
    trackResize: false,
    maxZoom: map.getMaxZoom(),
    canvasContextAttributes: {preserveDrawingBuffer: true},
  });
  const remover = camada.onRemove;
  camada.onRemove = function (leaflet) {
    // Uma falha ao criar o WebGL pode deixar o contêiner já inserido pelo adaptador.
    if (this.getMaplibreMap()) remover.call(this, leaflet);
    else this.getContainer()?.remove();
  };
  return camada;
}
