const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const codigo = fs.readFileSync(path.join(root, 'static/js/liraa_mapa_geral.js'), 'utf8');
const dados = {quarteiroes:[
  {id_localidade:1,localidade:'Sede',quarteirao:'0001',unidades_rg:30,tem_rg:true},
  {id_localidade:2,localidade:'São Venâncio',quarteirao:'0002',unidades_rg:40,tem_rg:true},
  {id_localidade:1,localidade:'Sede',quarteirao:'0003',unidades_rg:0,tem_rg:false},
], ciclos:[
  {id_ciclo:10,ano:2026,nome:'Primeiro',quarteiroes_sem_estrato:1,estratos:[
    {id_estrato:101,numero:1,tipo:'normal',imoveis_confirmados:9000,quarteiroes:['1:0001','2:0002'],
      localidades:[1,2],ausentes:0,observacoes:'Conferir',sorteio:null},
  ]},
  {id_ciclo:11,ano:2025,nome:'Anterior',quarteiroes_sem_estrato:2,estratos:[
    {id_estrato:102,numero:1,tipo:'reduzido',imoveis_confirmados:3000,quarteiroes:['1:0003'],
      localidades:[1],ausentes:0,observacoes:'',sorteio:null},
  ]},
]};
const elementos = new Map();
function elemento(id) {
  if (!elementos.has(id)) elementos.set(id, {value:'',textContent:'',innerHTML:'',style:{},children:[],dataset:{},
    events:{}, addEventListener(name, callback) { this.events[name] = callback; },
    replaceChildren(...novos) { this.children = novos; this.textContent = ''; },
    append(...novos) { this.children.push(...novos); },
    setAttribute(name, value) { this[name] = value; },
    querySelectorAll(selector) { return selector === 'button[data-estrato]' ? this.children.filter(c => c.dataset.estrato) : []; }});
  return elementos.get(id);
}
elemento('liraa-dados-json').textContent = JSON.stringify(dados);
const grupos = [];
let mapa;
const L = {
  map() { mapa = {removeLayer() {}, invalidateSize() {}, setView() { return this; },fitBounds(bounds) { this.lastBounds = bounds; }}; return mapa; },
  tileLayer() { return {addTo() { return this; }}; },
  control:{layers() { return {addTo() {}}; }},
  geoJSON(collection, options) {
    const layers = collection.features.map(feature => {
      const layer = {events:{},bindTooltip() {},on(name, cb) { this.events[name]=cb; }};
      options.onEachFeature(feature, layer);
      return layer;
    });
    const group = {features:collection.features,layers,options,addTo() {return this;},setStyle() {},
      getBounds() {return {isValid:() => collection.features.length > 0};}};
    grupos.push(group); return group;
  },
  featureGroup(layers) { return {getBounds() {return {layers};}}; },
};
const context = {window:{},document:{getElementById:elemento,createElement:() => ({style:{},dataset:{},children:[],
  append(...items) {this.children.push(...items);},setAttribute(name, value) {this[name] = value;},addEventListener(name, cb) {this[name]=cb;}})},
  location:{search:''},URLSearchParams,Intl,L,fetch() {throw Error('Não deve buscar quando a geometria já foi fornecida');}};
vm.runInNewContext(codigo, context);
const feature = (loc, q) => ({properties:{Localidade:loc,id_Q:q},geometry:{type:'Polygon',coordinates:[]}});
const geo = {type:'FeatureCollection',features:[feature('Sede',1),feature('São Venâncio',2),feature('Sede',3)]};
async function testar() {
  await context.window.LiraaMapaGeral.iniciar(geo);
  assert.equal(grupos[0].features.length, 3, 'Exibe todas as localidades no mesmo mapa');
  assert.equal(elemento('liraa-geral-atribuidos').textContent, '2');
  assert.equal(elemento('liraa-geral-livres').textContent, '1');
  assert.equal(elemento('liraa-geral-n').textContent, '9.000');
  assert.equal(grupos[0].options.style(geo.features[0]).fillColor, grupos[0].options.style(geo.features[1]).fillColor);
  assert.equal(grupos[0].options.style(geo.features[2]).fillColor, '#94a3b8');
  grupos[0].layers[1].events.click();
  assert.match(elemento('liraa-geral-detalhe').innerHTML, /São Venâncio/);
  assert.match(elemento('liraa-geral-detalhe').innerHTML, /N confirmado/);
  assert.ok(mapa.lastBounds, 'Enquadra a geometria ao abrir');
  elemento('liraa-geral-ciclo').value = '11';
  elemento('liraa-geral-ciclo').events.change();
  assert.equal(elemento('liraa-geral-n').textContent, '3.000');
  assert.equal(grupos.at(-1).options.style(geo.features[0]).fillColor, '#94a3b8', 'Não mistura ciclos');
  assert.notEqual(grupos.at(-1).options.style(geo.features[2]).fillColor, '#94a3b8');
  grupos.at(-1).layers[0].events.click();
  assert.match(elemento('liraa-geral-detalhe').innerHTML, /Sem estrato neste ciclo/);
  console.log('LIRAa: todos os estratos por ciclo, cinza para livres e consulta sem edição OK.');
}
testar().catch(error => { console.error(error); process.exitCode = 1; });
