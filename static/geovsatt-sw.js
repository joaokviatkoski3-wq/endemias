'use strict';

const versao = new URL(self.location.href).searchParams.get('v');
const prefixo = 'geovsatt-app-';
const cacheAtual = prefixo + versao;
const entradaOffline = '/geovsatt/offline';
const comVersao = caminho => `${caminho}?v=${encodeURIComponent(versao)}`;
const arquivos = new Set([
  ...[
    'img/geovsatt-symbol.svg', 'img/geovsatt-logo.png',
    'css/geovsatt.css', 'css/geovsatt_impressao.css', 'css/release_popup.css',
    'vendor/leaflet/leaflet.min.css', 'vendor/leaflet/leaflet.min.js',
    'vendor/maplibre/maplibre-gl.css', 'vendor/maplibre/maplibre-gl.mjs',
    'vendor/maplibre/maplibre-gl-worker.mjs', 'vendor/maplibre/leaflet-maplibre-gl.mjs',
    'vendor/polygon-clipping/polygon-clipping.umd.min.js',
    'js/geovsatt.js', 'js/geovsatt_estilos.js', 'js/geovsatt_rotulos.js',
    'js/geovsatt_medicao.js', 'js/geovsatt_impressao.js', 'js/geovsatt_calor.js',
    'js/geovsatt_leaflet.mjs', 'js/geovsatt_vetorial.mjs', 'js/geovsatt_campo.mjs',
  ].map(caminho => comVersao('/static/' + caminho)),
  '/static/js/geovsatt_cofre.mjs',
  '/static/js/geovsatt_dados_offline.mjs',
  ...['menu', 'fechar', 'imprimir', 'usuarios'].map(icone => `/static/icons/${icone}.svg`),
  '/static/icons/geovsatt-app-192.png',
  '/static/icons/geovsatt-app-512.png',
  '/geovsatt/manifest.webmanifest',
]);

async function preparar() {
  const cache = await caches.open(cacheAtual);
  await cache.addAll([...arquivos, entradaOffline].map(url => new Request(url, {
    cache: 'reload', credentials: 'same-origin', redirect: 'error',
  })));
}

self.addEventListener('install', event => event.waitUntil(preparar().then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil((async () => {
  const chaves = await caches.keys();
  await Promise.all(chaves.filter(chave => chave.startsWith(prefixo) && chave !== cacheAtual)
    .map(chave => caches.delete(chave)));
  await self.clients.claim();
})()));

async function abrirMapa(request) {
  try {
    return await fetch(request, {signal: AbortSignal.timeout(5000)});
  } catch {
    const cache = await caches.open(cacheAtual);
    return await cache.match(entradaOffline) || Response.error();
  }
}

self.addEventListener('fetch', event => {
  const {request} = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate' && url.pathname === '/geovsatt') {
    event.respondWith(abrirMapa(request));
    return;
  }
  if (arquivos.has(url.pathname + url.search) || (url.pathname === entradaOffline && !url.search)) {
    event.respondWith(caches.open(cacheAtual).then(async cache => await cache.match(request) || fetch(request)));
  }
});
