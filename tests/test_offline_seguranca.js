const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const origin = 'https://vsatt.com.br';
const handlers = {};
const entries = new Map();
const key = r => new URL(typeof r === 'string' ? r : r.url, origin).href;
const cache = {
  match: async r => entries.get(key(r))?.clone(),
  put: async (r, response) => entries.set(key(r), response.clone()),
  delete: async r => entries.delete(key(r)),
  keys: async () => [...entries.keys()].map(url => ({url})),
  addAll: async () => {},
};
const context = vm.createContext({
  self: {location: {origin}, addEventListener: (name, fn) => handlers[name] = fn},
  caches: {open: async () => cache}, URL, Response,
  fetch: async () => new Response('pagina', {headers: {'X-Endemias-User': '21'}}),
});
vm.runInContext(fs.readFileSync('static/sw.js', 'utf8'), context);

function dispatch(path, mode = 'navigate', method = 'GET') {
  let pending;
  handlers.fetch({request: {url: origin + path, mode, method}, respondWith: p => pending = p});
  return pending;
}

(async () => {
  await dispatch('/formularios/rg-campo');
  assert(entries.has(origin + '/formularios/rg-campo'));
  await dispatch('/visitas');
  assert(!entries.has(origin + '/visitas'), 'Nao guardar prontuarios/paginas de consulta');
  assert.equal(dispatch('/acoes-setor/anexos/1/download', 'cors'), undefined);
  assert.equal(dispatch('/api/formularios', 'cors'), undefined);
  context.fetch = async () => { throw new Error('offline'); };
  assert.equal(await (await dispatch('/formularios/rg-campo')).text(), 'pagina');
  await assert.rejects(dispatch('/visitas'), /offline/);
  context.fetch = async () => new Response('outra conta', {headers: {'X-Endemias-User': '22'}});
  await dispatch('/');
  assert(!entries.has(origin + '/formularios/rg-campo'), 'Troca de conta invalida pagina anterior');
  await dispatch('/formularios/rg-campo');
  await dispatch('/logout', 'navigate', 'POST');
  assert(!entries.has(origin + '/formularios/rg-campo'), 'Sair remove pagina offline');
  assert(!entries.has(origin + '/__endemias_offline_user'));
  // Dados novos na origem externa pertencem a cada usuario.
  const dbNames = [];
  for (const owner of ['21', '22']) {
    const c = vm.createContext({window: {}, document: {querySelector: () => ({content: owner})}, indexedDB: {open: name => {dbNames.push(name); return {};}}});
    c.window.indexedDB = c.indexedDB;
    vm.runInContext(fs.readFileSync('static/js/rg_campo_offline.js', 'utf8'), c);
    c.window.RGCampoOffline.obterSnapshot();
  }
  assert.deepEqual(dbNames, ['endemias_formularios_usuario_21', 'endemias_formularios_usuario_22']);
  console.log('OK: cache restrito, offline RG, troca de conta, logout e IndexedDB por usuario.');
})().catch(error => {console.error(error); process.exitCode = 1;});
