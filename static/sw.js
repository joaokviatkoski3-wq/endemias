/* Offline restrito ao RG de campo. Relatorios, anexos e APIs nunca sao salvos.
 * Sair remove a pagina offline; os rascunhos no IndexedDB sao preservados.
 */
const CACHE = 'endemias-formularios-v4';
const RG = '/formularios/rg-campo';
const IDENTITY = '/__endemias_offline_user';

const SHELL = [
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/js/ajuda.js',
  '/static/js/rg_campo_offline.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => navigation(new Request(RG, {credentials: 'same-origin'}), RG))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('endemias-formularios-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function clearPages(cache) {
  const keys = await cache.keys();
  await Promise.all(keys.filter(r => new URL(r.url).pathname === RG).map(r => cache.delete(r)));
  await cache.delete(IDENTITY);
}

async function cachePageAssets(cache, response) {
  const html = await response.clone().text();
  const urls = [...html.matchAll(/(?:src|href)=["'](\/static\/[^"']+)["']/g)]
    .map(m => new URL(m[1].replaceAll('&amp;', '&'), self.location.origin))
    .filter(u => u.origin === self.location.origin && u.pathname.startsWith('/static/'));
  await Promise.allSettled(urls.map(async u => {
    if (await cache.match(u.href)) return;
    const asset = await fetch(u.href);
    if (asset.ok && !asset.redirected) await cache.put(u.href, asset);
  }));
}

async function navigation(request, path) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request);
    const user = response.headers.get('X-Endemias-User');
    const previous = await cache.match(IDENTITY);
    if (!user || (previous && await previous.text() !== user)) await clearPages(cache);
    if (user && response.ok) {
      await cache.put(IDENTITY, new Response(user));
      if (path === RG && !response.redirected) {
        await cache.put(RG, response.clone());
        await cachePageAssets(cache, response);
      }
    }
    return response;
  } catch (error) {
    if (path === RG && await cache.match(IDENTITY)) {
      const page = await cache.match(RG);
      if (page) return page;
    }
    throw error;
  }
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname === '/logout') {
    event.respondWith(caches.open(CACHE).then(async cache => {
      await clearPages(cache);
      return fetch(event.request);
    }));
    return;
  }
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) return;

  if (event.request.mode === 'navigate') {
    event.respondWith(navigation(event.request, url.pathname));
    return;
  }

  if (!url.pathname.startsWith('/static/')) return;
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetch(event.request).then((resp) => {
      if (resp && resp.ok) {
        const copy = resp.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      }
      return resp;
    }))
  );
});
