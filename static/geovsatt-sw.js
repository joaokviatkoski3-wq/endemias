'use strict';

const versao = new URL(self.location.href).searchParams.get('v');
const prefixo = 'geovsatt-app-';
const cacheAtual = prefixo + versao;
const entradaOffline = '/geovsatt/offline';
const arquivos = new Set([
  `/static/img/geovsatt-symbol.svg?v=${encodeURIComponent(versao)}`,
  '/static/icons/geovsatt-app-192.png',
  '/static/icons/geovsatt-app-512.png',
  '/static/css/geovsatt_offline.css',
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
    return await fetch(request);
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
  if (arquivos.has(url.pathname + url.search) || url.pathname === entradaOffline) {
    event.respondWith(caches.open(cacheAtual).then(async cache => await cache.match(request) || fetch(request)));
  }
});
