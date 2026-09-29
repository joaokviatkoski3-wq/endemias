const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const arquivo = path.join(__dirname, '..', 'static', 'js', 'microareas.js');
const codigo = fs.readFileSync(arquivo, 'utf8').replace(/\}\)\(\);\s*$/,
  'globalThis.__microTeste = {estado, iniciarDesenho, cancelarDesenho, atualizarDesenho, carregarTrechos, concluirDesenho, abrir};\n})();');
const elementos = new Map();
function el(id) {
  if (!elementos.has(id)) elementos.set(id, {
    value:'', checked:true, hidden:false, style:{}, textContent:'', innerHTML:'',
    addEventListener() {}, querySelectorAll() { return []; }, scrollIntoView() {}, setAttribute() {},
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
const context = {L, Intl, URLSearchParams, console, location:{hash:''}, setTimeout() {}, confirm() { return true; },
  localStorage:{getItem() { return null; }},
  window:{MicroareasCores:{vizinhanca() { return {}; }, atribuir() { return {}; }}},
  document:{getElementById:el, querySelectorAll() { return []; }, querySelector() { return {content:'csrf-teste'}; }},
};
vm.runInNewContext(codigo, context, {filename:arquivo});
const {estado, iniciarDesenho, cancelarDesenho, atualizarDesenho, carregarTrechos, concluirDesenho, abrir} = context.__microTeste;
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

async function testarPersistencia() {
  const registro = {id_microarea:52, id_localidade:1, localidade:'Sede', numero:'10',
    acs_codigo:null, acs_nome:null, observacoes:'', quarteiroes:['0007'], partes:[],
    quarteiroes_sem_geometria:[], quarteiroes_com_rg:1, quarteiroes_total:1,
    populacao_com_condominios:0, populacao_sem_condominios:0};
  let gravacoes = 0;
  context.fetch = async (url, options={}) => {
    if (options.method === 'PUT') {
      const payload = JSON.parse(options.body);
      assert.equal(url, '/api/territorializacao/microareas/52');
      assert.deepEqual(payload.quarteiroes, [], 'Converter para parcial retira o vínculo inteiro');
      assert.equal(payload.partes.length, 1);
      assert.equal(payload.partes[0].lado, '1');
      gravacoes++;
      registro.quarteiroes = [];
      registro.partes = payload.partes;
      return {ok:true, json:async() => ({ok:true})};
    }
    if (url.startsWith('/api/territorializacao/microareas/trechos'))
      return {ok:true, json:async() => ({inteiro_id_microarea:gravacoes ? null : 52,
        trechos:[{logradouro:'Rua Teste', lado:'1', imoveis:1, id_microarea:gravacoes ? 52 : null}]})};
    if (url === '/api/registro-geografico/geojson')
      return {ok:true, json:async() => estado.geo};
    if (url === '/api/territorializacao/microareas')
      return {ok:true, json:async() => ({registros:[registro], acs:[], indicadores:{}, resumo_rg:{quarteiroes:{}}})};
    throw new Error(`URL inesperada: ${url}`);
  };
  estado.iniciado = true;
  estado.lista = [registro];
  estado.desenho = null;
  estado.partes = [];
  estado.selecionados = new Set();
  el('micro-parcial-q').value = '7';
  await carregarTrechos('7');
  assert.match(el('micro-parcial-lados').innerHTML, /Editar microárea 10/,
    'Quarteirão ocupado deve oferecer acesso direto à edição');
  abrir(52);
  await carregarTrechos('7');
  assert.doesNotMatch(el('micro-parcial-lados').innerHTML, /disabled/,
    'Na edição da dona, o lado deve ficar disponível');
  assert.equal(el('micro-parcial-concluir').textContent, 'Concluir e salvar lado');
  iniciarDesenho(0);
  estado.desenho.pontos = [
    {lng:-49.2999,lat:-25.3001}, {lng:-49.298,lat:-25.3001}, {lng:-49.2999,lat:-25.303},
  ];
  await concluirDesenho();
  assert.equal(gravacoes, 1, 'Concluir deve gravar no banco imediatamente');
  assert.equal(estado.selecionados.has('0007'), false);
  assert.equal(estado.partes.length, 1, 'O lado salvo deve continuar visível após recarregar');
  assert.match(el('micro-status').textContent, /salvo na microárea 10/);
  assert.match(el('micro-parcial-lados').innerHTML, /Redesenhar/);
}
testarPersistencia().then(() => console.log('Conversão inteiro→parcial gravada e visível após recarregar.'),
  erro => { console.error(erro); process.exitCode = 1; });
