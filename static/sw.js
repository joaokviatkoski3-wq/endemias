/* Somente RG offline por 24h. APIs e anexos nunca são guardados. */
const CACHE = 'endemias-formularios-v5';
const RG = '/formularios/rg-campo';
const IDENTITY = '/__endemias_offline_user';
const TTL = 24*60*60*1000;
let pageEpoch=0;
self.addEventListener('install', event => event.waitUntil(navigation(new Request(RG,{credentials:'same-origin'}),RG)));
// Uma atualização espera o usuário salvar e tocar em Atualizar aplicativo.
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('endemias-formularios-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())));
async function clearPages(cache) { pageEpoch++; await cache.delete(RG); await cache.delete(IDENTITY); }
self.addEventListener('message', event => {
  if(event.data?.type === 'ATIVAR_ATUALIZACAO') event.waitUntil(self.skipWaiting());
  if(event.data?.type === 'LIMPAR_PAGINA') event.waitUntil(caches.open(CACHE).then(clearPages));
});
async function cachePageAssets(cache,response) {
  const html=await response.clone().text();
  const urls=[...html.matchAll(/(?:src|href)=["'](\/static\/[^"']+)["']/g)].map(m => new URL(m[1].replaceAll('&amp;','&'),self.location.origin)).filter(u => u.origin === self.location.origin && u.pathname.startsWith('/static/'));
  await Promise.all(urls.map(async u => {
    if(await cache.match(u.href)) return;
    const asset=await fetch(u.href);
    if(!asset.ok || asset.redirected) throw new Error('Arquivo indisponível');
    await cache.put(u.href,asset);
  }));
}
function unavailable(logout=false) {
  return new Response(`<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Campo RG</title><body><h1>${logout?'Saída precisa de conexão':'Abra o RG com internet'}</h1><p>${logout?'A página offline foi bloqueada, mas o servidor ainda precisa confirmar sua saída.':'Entre na conta e abra o RG online para preparar ou renovar o acesso offline por 24 horas.'}</p><p>Os rascunhos continuam guardados neste navegador. Não limpe os dados do aplicativo.</p><a href="/formularios/rg-campo">Tentar novamente</a></body></html>`,{status:503,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; base-uri 'none'; frame-ancestors 'none'"}});
}
async function fallback(cache,path) {
  if(path !== RG) throw new Error('Página disponível somente online');
  const stored=await cache.match(IDENTITY), identity=stored ? await stored.json().catch(()=>null) : null;
  if(identity && /^\d+$/.test(identity.usuario) && Date.now()<identity.validade) {
    const page=await cache.match(RG); if(page) return page;
  }
  await clearPages(cache); return unavailable();
}
async function navigation(request,path) {
  const cache=await caches.open(CACHE); let response,epoch=pageEpoch;
  try {response=await fetch(request);} catch(e) {return fallback(cache,path);}
  if(response.status>=500) return path===RG ? fallback(cache,path) : response;
  if(epoch!==pageEpoch)return response;
  const user=response.headers.get('X-Endemias-User'), previous=await cache.match(IDENTITY);
  const identity=previous ? await previous.json().catch(()=>null) : null;
  if(!user || (identity && identity.usuario!==user)) {await clearPages(cache);epoch=pageEpoch;}
  if(path===RG && user && response.ok && !response.redirected) {
    try {
      await cachePageAssets(cache,response);
      if(epoch!==pageEpoch)return response;
      await cache.put(RG,response.clone());
      await cache.put(IDENTITY,new Response(JSON.stringify({usuario:user,validade:Date.now()+TTL})));
    } catch(e) { /* A página online funciona; é preciso conferir a preparação offline. */ }
  }
  return response;
}
self.addEventListener('fetch',event => {
  const url=new URL(event.request.url); if(url.origin!==self.location.origin) return;
  if(url.pathname==='/logout') {
    event.respondWith(caches.open(CACHE).then(async cache => {
      await clearPages(cache); try {return await fetch(event.request);} catch(e) {return unavailable(true);}
    }));return;
  }
  if(event.request.method!=='GET' || url.pathname.startsWith('/api/')) return;
  if(event.request.mode==='navigate') {event.respondWith(navigation(event.request,url.pathname));return;}
  if(!url.pathname.startsWith('/static/')) return;
  event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(event.request)) || fetch(event.request)));
});
