'use strict';

const versao = new URL(self.location.href).searchParams.get('v');
const prefixo = 'geovsatt-app-';
const cacheAtual = prefixo + versao;
const entradaOffline = '/geovsatt/offline';
const versaoNaUrl = '?v=' + encodeURIComponent(versao);
const entradaVersionada = entradaOffline + versaoNaUrl;
const arquivosVersionados = new Set([
  'img/geovsatt-symbol.svg', 'img/geovsatt-logo.png',
  'css/geovsatt.css', 'css/geovsatt_impressao.css', 'css/release_popup.css',
  'vendor/leaflet/leaflet.min.css', 'vendor/leaflet/leaflet.min.js',
  'vendor/maplibre/maplibre-gl.css', 'vendor/maplibre/maplibre-gl.mjs',
  'vendor/maplibre/maplibre-gl-worker.mjs', 'vendor/maplibre/leaflet-maplibre-gl.mjs',
  'vendor/polygon-clipping/polygon-clipping.umd.min.js',
  'js/geovsatt.js', 'js/geovsatt_estilos.js', 'js/geovsatt_rotulos.js',
  'js/geovsatt_medicao.js', 'js/geovsatt_impressao.js', 'js/geovsatt_calor.js',
  'js/geovsatt_leaflet.mjs', 'js/geovsatt_vetorial.mjs', 'js/geovsatt_campo.mjs',
  'js/geovsatt_cofre.mjs', 'js/geovsatt_dados_offline.mjs',
].map(caminho => '/static/' + caminho));
const modulosAnteriores = new Set([
  '/static/js/geovsatt_cofre.mjs',
  '/static/js/geovsatt_dados_offline.mjs',
]);
const arquivosEstaveis = new Set([
  ...['menu', 'fechar', 'imprimir', 'usuarios'].map(icone => `/static/icons/${icone}.svg`),
  '/static/icons/geovsatt-app-192.png',
  '/static/icons/geovsatt-app-512.png',
  '/geovsatt/manifest.webmanifest',
]);

async function preparar() {
  const existente = await caches.has(cacheAtual);
  const cache = await caches.open(cacheAtual);
  const versionados = [...arquivosVersionados].map(caminho => caminho + versaoNaUrl);
  try {
    await cache.addAll([...versionados, ...arquivosEstaveis, entradaVersionada].map(url => new Request(url, {
      cache: 'reload', credentials: 'same-origin', redirect: 'error',
    })));
  } catch (erro) {
    if (!existente) await caches.delete(cacheAtual);
    throw erro;
  }
}

self.addEventListener('install', event => event.waitUntil(preparar().then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil((async () => {
  const anteriores = await cachesAnteriores();
  await Promise.all(anteriores.slice(0, -1).map(chave => caches.delete(chave)));
  await self.clients.claim();
})()));

async function cachesAnteriores() {
  return (await caches.keys()).filter(chave => chave.startsWith(prefixo) && chave !== cacheAtual);
}

async function abrirMapa(request) {
  let online;
  try {
    online = await fetch(request, {signal: AbortSignal.timeout(5000)});
    if (online.status < 500) return online;
  } catch { /* Consulte a interface salva no dispositivo. */ }
  return await paginaOffline() || online || Response.error();
}

function paginaOffline() {
  return caches.match(entradaVersionada, {cacheName: cacheAtual});
}

async function arquivo(request, chave) {
  return (chave && await caches.match(request, {cacheName: chave})) || fetch(request);
}

self.addEventListener('fetch', event => {
  const {request} = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate' && url.pathname === '/geovsatt') {
    event.respondWith(abrirMapa(request));
    return;
  }
  if (!url.search && url.pathname === entradaOffline) {
    event.respondWith(paginaOffline().then(pagina => pagina || fetch(request)));
  } else if (!url.search && arquivosEstaveis.has(url.pathname)) {
    event.respondWith(arquivo(request, cacheAtual));
  } else if (!url.search && modulosAnteriores.has(url.pathname)) {
    event.respondWith(cachesAnteriores().then(chaves => arquivo(request, chaves.at(-1))));
  } else if (arquivosVersionados.has(url.pathname) && /^\?v=\d+\.\d+\.\d+(?:-[\w.]+)?$/.test(url.search)) {
    event.respondWith(arquivo(request, prefixo + url.searchParams.get('v')));
  }
});
