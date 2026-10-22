/* Service Worker do hub de Formulários (captura offline).
 *
 * Estratégia:
 * - navegação: rede primeiro, com fallback para o cache (offline);
 * - estáticos (/static/): cache primeiro, preenchendo conforme usa;
 * - /api/: sempre rede (dados offline ficam no IndexedDB, não no SW).
 */
const CACHE = 'endemias-formularios-v3';

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
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((resp) => {
          if (resp.ok && !resp.redirected) {
            const copy = resp.clone();
            caches.open(CACHE).then((cache) => cache.put(event.request, copy));
          }
          return resp;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

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
