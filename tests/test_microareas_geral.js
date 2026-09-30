const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const template = fs.readFileSync(path.join(root, 'templates', 'registro_geografico.html'), 'utf8');
const pane = template.split('id="micro-pane-geral"')[1].split('id="micro-report-filters"')[0];
assert.match(pane, /id="micro-geral-mapa"/);
assert.match(pane, /id="micro-geral-detalhe"/);
assert.doesNotMatch(pane, /data-micro-edit|data-micro-delete|id="micro-salvar"|<form/i,
  'A subaba de consulta não deve expor edição ou exclusão');

const arquivo = path.join(root, 'static', 'js', 'microareas.js');
const codigo = fs.readFileSync(arquivo, 'utf8').replace(/\}\)\(\);\s*$/,
  'globalThis.__geralTeste = {estado, geralAtualizar, geralSelecionar};\n})();');
const elementos = new Map();
function el(id) {
  if (!elementos.has(id)) elementos.set(id, {value:'', checked:false, hidden:false,
    textContent:'', innerHTML:'', style:{}, options:[], addEventListener() {}, querySelectorAll() { return []; }});
  return elementos.get(id);
}
el('micro-localidade').options = [{value:'1', textContent:'Sede'}, {value:'2', textContent:'Graziela'}];
const camadas = [];
function geoJSON(collection, options={}) {
  const features = collection?.type === 'FeatureCollection' ? collection.features : [collection];
  const layers = features.map(feature => {
    const layer = {feature, events:{}, bindTooltip() { return this; }, on(name, callback) { this.events[name] = callback; }};
    options.onEachFeature?.(feature, layer);
    return layer;
  });
  const group = {features, layers, options, addTo() { return this; }, setStyle() {},
    getBounds() { return {isValid:() => features.length > 0, extend() { return this; }}; }};
  camadas.push(group);
  return group;
}
const context = {L:{geoJSON}, Intl, console, location:{hash:''}, setTimeout() {},
  localStorage:{getItem() { return null; }},
  window:{MicroareasCores:{vizinhanca() { return {}; }, atribuir() { return {}; }}, addEventListener() {}},
  document:{getElementById:el, querySelectorAll() { return []; }, querySelector() { return null; }},
};
vm.runInNewContext(codigo, context, {filename:arquivo});
const {estado, geralAtualizar, geralSelecionar} = context.__geralTeste;
const feature = (loc,q) => ({type:'Feature', properties:{Localidade:loc,id_quart:q},
  geometry:{type:'Polygon', coordinates:[[[-49.3,-25.3],[-49.29,-25.3],[-49.3,-25.31],[-49.3,-25.3]]]}});
estado.geo = {type:'FeatureCollection', features:[feature(1,'0007'),feature(1,'0008'),feature(2,'0009')]};
estado.lista = [
  {id_microarea:10,id_localidade:1,localidade:'Sede',numero:'1',acs_nome:'Maria',acs_codigo:'acs-1',
    quarteiroes:['0007'],partes:[],quarteiroes_total:1,quarteiroes_com_rg:1,
    quarteiroes_sem_geometria:[],populacao_com_condominios:70,observacoes:''},
  {id_microarea:11,id_localidade:2,localidade:'Graziela',numero:'1',acs_nome:'Ana',acs_codigo:'acs-2',
    quarteiroes:[],partes:[{quarteirao:'0009',logradouro:'Rua B',lado:'2',geometry:feature(2,'0009').geometry,
      base_desatualizada:false,lado_ausente_rg:false}],quarteiroes_total:1,quarteiroes_com_rg:1,
    quarteiroes_sem_geometria:[],populacao_com_condominios:30,observacoes:'Revisar em campo'},
];
estado.coresMapa = {'10':'#dc2626','11':'#2563eb'};
let fit = 0;
estado.geralMapa = {removeLayer() {}, fitBounds() { fit++; }};
geralAtualizar();
assert.equal(estado.geralBaseLayer.features.length, 3, 'Mapa geral inclui quarteirões de todas as localidades');
assert.equal(estado.geralPartesLayer.features.length, 1, 'Lado parcial deve aparecer no mapa geral');
assert.equal(estado.geralDonos.get('1:0007').id_microarea, 10);
assert.equal(estado.geralBaseLayer.options.style(estado.geo.features[1]).fillColor, '#94a3b8',
  'Quarteirão sem microárea permanece visível em cinza');
assert.equal(estado.geralPartesLayer.options.style(estado.geralPartesLayer.features[0]).fillColor, '#2563eb');
assert.match(el('micro-geral-lista').innerHTML, /Sede/);
assert.match(el('micro-geral-lista').innerHTML, /Graziela/);
assert.ok(fit > 0, 'Mapa geral deve enquadrar as duas localidades');
geralSelecionar(11);
assert.match(el('micro-geral-detalhe').innerHTML, /Ana/);
assert.match(el('micro-geral-detalhe').innerHTML, /Rua B/);
assert.match(el('micro-geral-detalhe').innerHTML, /Revisar em campo/);
assert.doesNotMatch(el('micro-geral-detalhe').innerHTML, /Editar|Excluir/);
estado.geralBaseLayer.layers[1].events.click();
assert.match(el('micro-geral-detalhe').innerHTML, /Sem microárea inteira/);
console.log('Mapa geral: todas as localidades, lado parcial, consulta somente leitura e detalhes OK.');
