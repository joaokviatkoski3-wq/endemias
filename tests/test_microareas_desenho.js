const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const arquivo = path.join(__dirname, '..', 'static', 'js', 'microareas.js');
const codigo = fs.readFileSync(arquivo, 'utf8').replace(/\}\)\(\);\s*$/,
  'globalThis.__microTeste = {estado, iniciarDesenho, cancelarDesenho, atualizarDesenho};\n})();');
const elementos = new Map();
function el(id) {
  if (!elementos.has(id)) elementos.set(id, {
    value:'', checked:true, hidden:false, style:{}, textContent:'', innerHTML:'',
    addEventListener() {}, querySelectorAll() { return []; },
  });
  return elementos.get(id);
}
const camadas = [];
function camada(options={}) {
  const obj = {options, addTo() { return this; }, getBounds() { return {isValid() { return true; }}; },
    eachLayer() {}, setStyle() {}, bindTooltip() { return this; }};
  camadas.push(obj);
  return obj;
}
const L = {
  geoJSON(_feature, options={}) { return camada(options); },
  polygon(_points, options) { return camada(options); },
  polyline(_points, options) { return camada(options); },
  circleMarker(_point, options) { return camada(options); },
  layerGroup(items) { const group = camada(); group.items = items; return group; },
};
const context = {L, Intl, URLSearchParams, console, location:{hash:''},
  localStorage:{getItem() { return null; }},
  window:{MicroareasCores:{}},
  document:{getElementById:el, querySelectorAll() { return []; }},
};
vm.runInNewContext(codigo, context, {filename:arquivo});
const {estado, iniciarDesenho, cancelarDesenho, atualizarDesenho} = context.__microTeste;
estado.mapa = {removeLayer() {}, fitBounds() {}};
estado.geo = {features:[{type:'Feature', properties:{Localidade:1, id_quart:'0007'},
  geometry:{type:'Polygon',coordinates:[[[-49.3,-25.3],[-49.29,-25.3],[-49.3,-25.31],[-49.3,-25.3]]]}}]};
estado.lista = [];
estado.parcialQ = '0007';
estado.trechos = [{logradouro:'Rua Teste', lado:'1'}];
el('micro-localidade').value = '1';

iniciarDesenho(0);
assert.equal(estado.layer.options.interactive, false,
  'Quarteirão-base não deve capturar cliques durante o desenho');
assert.equal(estado.partesLayer.options.interactive, false,
  'Partes já existentes não devem capturar cliques durante o desenho');
assert.ok(estado.desenhoLayer.items.every(item => item.options.interactive === false),
  'Traço provisório não deve capturar cliques');
estado.desenho.pontos.push({lat:-25.301,lng:-49.299});
atualizarDesenho();
assert.ok(estado.desenhoLayer.items.every(item => item.options.interactive === false),
  'Vértices provisórios não devem capturar cliques');
cancelarDesenho();
assert.equal(estado.layer.options.interactive, true,
  'Seleção normal do quarteirão deve voltar ao cancelar');
assert.equal(estado.partesLayer.options.interactive, true,
  'Camadas salvas devem voltar a ser interativas ao cancelar');
console.log('Desenho sobre o polígono-base: camadas deixam passar cliques e restauram interação.');
