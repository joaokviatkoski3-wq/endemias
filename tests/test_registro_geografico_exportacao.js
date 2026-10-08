const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(path.join(__dirname, '..', 'templates', 'registro_geografico.html'), 'utf8');
assert.match(template, /id="rg-imp-xlsx"/);
assert.match(template, /addEventListener\('click', rgBaixarPlanilha\)/);
const codigo = template.slice(template.indexOf('async function rgBaixarPlanilha()'), template.indexOf('function rgLogradouroSuggestBox()'));
const elementos = {
  'rg-imp-localidade': {value: '1'}, 'rg-imp-xlsx': {disabled: false},
  'rg-imp-mini-mapa': {checked: true}, 'rg-imp-duplex-recto': {checked: true},
};
let selecionados = [{value: '1'}, {value: '0408.1'}];
let calls = [], status = '', downloads = 0, alerts = 0, prints = [];
let resposta = {ok: true, headers: {get: () => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}, blob: async () => ({})};
const context = {
  URLSearchParams, rgEl: id => elementos[id], rgFmt: x => String(x),
  rgSetText: (id, text) => {status = text;}, alert: () => alerts++,
  fetch: async url => {calls.push(url); assert.equal(elementos['rg-imp-xlsx'].disabled, true); return resposta;},
  URL: {createObjectURL: () => 'blob:teste', revokeObjectURL() {}}, setTimeout: fn => fn(),
  document: {querySelectorAll: () => selecionados, body: {appendChild() {}},
    createElement: () => ({click() {downloads++;}, remove() {}})},
  window: {open: (url, target) => prints.push([url, target])},
};
vm.runInNewContext(codigo, context);
(async () => {
  await context.rgBaixarPlanilha();
  assert.equal(downloads, 1);
  const url = new URL(calls[0], 'http://localhost');
  assert.deepEqual(url.searchParams.getAll('quarteirao'), ['1', '0408.1']);
  assert.equal(url.searchParams.get('localidade'), '1');
  assert.equal(url.searchParams.has('mini_mapa'), false);
  assert.equal(url.searchParams.has('duplex_recto'), false);
  assert.match(status, /Download iniciado: 2 RG/);
  assert.equal(elementos['rg-imp-xlsx'].disabled, false);
  context.rgAbrirImpressao();
  assert.match(prints[0][0], /mini_mapa=1.*duplex_recto=1/);
  resposta = {ok: false, status: 400, json: async () => ({erro: 'Seleção inválida'})};
  await context.rgBaixarPlanilha();
  assert.equal(status, 'Seleção inválida');
  assert.equal(downloads, 1);
  assert.equal(elementos['rg-imp-xlsx'].disabled, false);
  resposta = {ok: true, headers: {get: () => 'text/html'}};
  await context.rgBaixarPlanilha();
  assert.match(status, /sessão pode ter expirado/);
  selecionados = [];
  const chamadasAntes = calls.length;
  await context.rgBaixarPlanilha();
  assert.equal(calls.length, chamadasAntes);
  assert.equal(alerts, 1);
  console.log('OK: seleção múltipla, download, erros, sessão expirada e impressão preservada.');
})().catch(err => {console.error(err); process.exitCode = 1;});
