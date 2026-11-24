/* Páginas de captura preparadas por conta. APIs, revisão e anexos não entram no cache HTTP. */
const CACHE = 'endemias-formularios-v6';
const FIELD_CACHE = CACHE + '-campo';
const RG = '/formularios/rg-campo';
const IDENTITY = '/__endemias_offline_user';
const FIELD_IDENTITY = '/__endemias_campo_user';
const FORMS_HOME = '/formularios';
const FIELD_HOME = '/formularios/campo-offline';
const FIELD_PAGES = [FIELD_HOME,RG,...['PE','PE_CADASTRO','TB','TBO','PVE','BRI','RECOLHIMENTO']
  .map(type=>'/formularios/kobo/'+type)];
const TTL = 24*60*60*1000;
let pageEpoch=0,fieldEpoch=0;
self.addEventListener('install', event => event.waitUntil(navigation(new Request(RG,{credentials:'same-origin'}),RG)));
// Uma atualização espera o usuário salvar e tocar em Atualizar aplicativo.
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('endemias-formularios-') && ![CACHE,FIELD_CACHE].includes(k)).map(k => caches.delete(k)))).then(() => self.clients.claim())));
async function clearPages(cache) { pageEpoch++; await cache.delete(RG); await cache.delete(IDENTITY); }
self.addEventListener('message', event => {
  if(event.data?.type === 'ATIVAR_ATUALIZACAO') event.waitUntil(self.skipWaiting());
  if(event.data?.type === 'LIMPAR_PAGINA') event.waitUntil(caches.open(CACHE).then(clearPages));
  if(event.data?.type === 'PREPARAR_CAMPO' && event.ports[0]) {
    event.waitUntil(prepareField(event.data.user).then(validade=>event.ports[0].postMessage({validade}),
      ()=>event.ports[0].postMessage({erro:'Não foi possível preparar todas as páginas. Confira a conexão e tente de novo.'})));
  }
});
async function fieldIdentity(cache) {
  const saved=await cache.match(FIELD_IDENTITY);
  return saved ? await saved.json().catch(()=>null) : null;
}
async function clearField() {
  fieldEpoch++;
  const cache=await caches.open(FIELD_CACHE);
  await cache.delete(FIELD_IDENTITY);
  await Promise.all((await cache.keys()).map(request=>cache.delete(request)));
  for(const client of await self.clients.matchAll({type:'window'}))client.postMessage({type:'BLOQUEAR_CAMPO'});
}
const fieldKey=(path,pack)=>pack ? path+'?offline='+pack : path;
let preparing;
async function prepareField(user){
  if(preparing)throw new Error('Outra preparação em andamento');
  preparing=storeField(user).finally(()=>{preparing=null;});
  return preparing;
}
async function storeField(user) {
  const epoch=fieldEpoch,cache=await caches.open(FIELD_CACHE),assets=await caches.open(CACHE);
  const previous=await fieldIdentity(cache),pack=crypto.randomUUID();
  const responses=await Promise.all(FIELD_PAGES.map(async path=>{
    const response=await fetch(path,{cache:'no-store',credentials:'same-origin',redirect:'error'});
    if(!response.ok || response.headers.get('X-Endemias-User')!==String(user) ||
       response.headers.get('X-Endemias-Campo-Offline')!=='1')throw new Error('Conta ou página indisponível');
    await cachePageAssets(assets,response);
    return response;
  }));
  const validade=Date.now()+TTL, keys=FIELD_PAGES.map(path=>fieldKey(path,pack));
  try{
    const writes = await Promise.allSettled(responses.map((response,i)=>cache.put(keys[i],response)));
    if(epoch!==fieldEpoch || writes.some(write=>write.status==='rejected'))throw new Error('Preparação interrompida');
    await cache.put(FIELD_IDENTITY,new Response(JSON.stringify({usuario:String(user),validade,pack})));
    if(epoch!==fieldEpoch){await cache.delete(FIELD_IDENTITY);throw new Error('Conta mudou');}
  }catch(error){
    await Promise.allSettled(keys.map(key=>cache.delete(key)));
    throw error;
  }
  await Promise.allSettled(FIELD_PAGES.map(path=>cache.delete(fieldKey(path,previous?.pack))));
  return validade;
}
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
  const fieldPath=path===FORMS_HOME?FIELD_HOME:path;
  if(FIELD_PAGES.includes(fieldPath)){
    const field=await caches.open(FIELD_CACHE),identity=await fieldIdentity(field);
    if(identity && Date.now()<identity.validade){
      const page=await field.match(fieldKey(fieldPath,identity.pack));
      if(page && page.headers.get('X-Endemias-User')===identity.usuario)return page;
    }
    if(path!==RG)return new Response('Conecte-se e prepare os formulários para o trabalho offline.',{status:503,
      headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}});
  }
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
  if(response.status>=500) return path===RG || path===FORMS_HOME || FIELD_PAGES.includes(path) ? fallback(cache,path) : response;
  if(epoch!==pageEpoch)return response;
  const user=response.headers.get('X-Endemias-User'), previous=await cache.match(IDENTITY);
  const field=await fieldIdentity(await caches.open(FIELD_CACHE));
  if(field && (field.usuario!==user || FIELD_PAGES.includes(path) &&
      response.headers.get('X-Endemias-Campo-Offline')!=='1'))await clearField();
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
      await Promise.all([clearPages(cache),clearField()]); try {return await fetch(event.request);} catch(e) {return unavailable(true);}
    }));return;
  }
  if(event.request.method!=='GET' || url.pathname.startsWith('/api/')) return;
  if(event.request.mode==='navigate') {event.respondWith(navigation(event.request,url.pathname));return;}
  if(!url.pathname.startsWith('/static/')) return;
  event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(event.request)) || fetch(event.request)));
});
