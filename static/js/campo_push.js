(() => {
  'use strict';
  const box=document.getElementById('campo-push');
  const sino=document.getElementById('campo-avisos-abrir');
  if(!sino)return;
  if(location.pathname==='/formularios/campo-offline/avisos'){
    history.replaceState(null,'','/formularios/campo-offline');
    sino.click();
  }
  if(!box || !window.isSecureContext || !('PushManager' in window) || !('Notification' in window))return;
  const usuario=Number(document.getElementById('campo-avisos').dataset.usuario);
  const status=document.getElementById('campo-push-status');
  const ativar=document.getElementById('campo-push-ativar');
  const testar=document.getElementById('campo-push-testar');
  const desativar=document.getElementById('campo-push-desativar');
  const endpoint='/api/formularios/campo-push';
  let registration,config,subscription,busy=false;
  const ativos=()=>config.modo==='teste'?'Avisos de teste ativos neste aparelho.':'Avisos com o app fechado estão ativos neste aparelho.';
  async function api(acao=null) {
    const response=await fetch(endpoint,{cache:'no-store',signal:AbortSignal.timeout(10000),
      ...(acao?{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':config.csrf},
        body:JSON.stringify({usuario,acao,endpoint:subscription?.endpoint})}:{})});
    const data=await response.json();
    if(!response.ok || (!acao && data.usuario!==usuario)){
      throw Error(data.erro||'Entre na conta do piloto para configurar os avisos.');
    }
    return data;
  }
  async function hash(value) {
    const data=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));
    return Array.from(new Uint8Array(data),byte=>byte.toString(16).padStart(2,'0')).join('');
  }
  function dizer(text,ativo=false,permiteAtivar=false){
    status.textContent=text;
    ativar.hidden=!permiteAtivar;
    testar.hidden=desativar.hidden=!ativo;
  }
  async function carregar(){
    if(busy||!navigator.onLine)return;
    try {
      config=await api();
    } catch {
      box.hidden=true;
      return;
    }
    box.hidden=false;
    if(!navigator.userAgent.includes('Android') || !navigator.userAgent.includes('Chrome/')){
      dizer('Para participar do piloto, use o app instalado pelo Chrome no Android.');
      return;
    }
    registration=await navigator.serviceWorker.getRegistration();
    const workerVersion=registration?.active && new URL(registration.active.scriptURL).searchParams.get('v');
    if(workerVersion!==document.documentElement.dataset.versao){
      dizer('Atualize o aplicativo em Formulários de campo para ativar os avisos.');
      return;
    }
    subscription=await registration.pushManager.getSubscription();
    if(subscription&&config.aparelho===await hash(subscription.endpoint)&&Notification.permission==='granted'){
      dizer(ativos(),true);
    }else if(Notification.permission==='denied'){
      dizer('Para ativar, permita as notificações do VSATT nas configurações do Chrome.');
    }else{
      dizer(config.modo==='teste'
        ? 'Use este aparelho para testar a entrega com o app fechado.'
        : 'Receba avisos de coleta mesmo com o aplicativo fechado. O piloto usa um aparelho por conta.',false,true);
    }
  }
  function worker(type){
    return new Promise((resolve,reject)=>{
      const channel=new MessageChannel();
      const timeout=setTimeout(()=>{channel.port1.close();reject(Error('Atualize o aplicativo e tente novamente.'));},5000);
      channel.port1.onmessage=({data})=>{
        clearTimeout(timeout);channel.port1.close();
        if(data)resolve();else reject(Error('Não foi possível atualizar os avisos neste aparelho.'));
      };
      registration.active.postMessage({type,user:usuario},[channel.port2]);
    });
  }
  async function executar(act) {
    if(busy)return;
    busy=true;
    for(const button of [ativar,testar,desativar])button.disabled=true;
    try {await act();}
    catch(e){status.textContent=e.message||'Não foi possível configurar os avisos.';}
    finally{
      busy=false;
      for(const button of [ativar,testar,desativar])button.disabled=false;
    }
  }
  ativar.onclick=()=>executar(async()=>{
    const permission=await Notification.requestPermission();
    if(permission!=='granted'){
      dizer('Os avisos dependem da sua permissão de notificações no Chrome.',false,permission!=='denied');
      return;
    }
    config=await api();
    const encoded=config.chave.replaceAll('-','+').replaceAll('_','/');
    const key=Uint8Array.from(atob(encoded),ch=>ch.charCodeAt(0));
    if(subscription){
      await subscription.unsubscribe();
      subscription=null;
    }
    subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
    try{
      await worker('PUSH_ATIVAR');
      await api('ativar');
    }catch(e){
      await Promise.allSettled([worker('PUSH_DESATIVAR'),subscription.unsubscribe()]);
      subscription=null;
      throw e;
    }
    dizer(ativos(),true);
  });
  desativar.onclick=()=>executar(async()=>{
    config=await api();
    await api('desativar');
    await worker('PUSH_DESATIVAR');
    subscription=null;
    dizer('Avisos desativados neste aparelho.',false,true);
  });
  testar.onclick=()=>executar(async()=>{
    config=await api();
    await api('testar');
    status.textContent='Teste agendado. Feche o app agora e aguarde o aviso.';
  });
  sino.addEventListener('click',()=>carregar().catch(()=>{box.hidden=true;}));
  navigator.serviceWorker.addEventListener('message',event=>{
    if(event.data?.type==='BLOQUEAR_CAMPO')box.hidden=true;
  });
  if(document.getElementById('campo-avisos')?.open)carregar().catch(()=>{box.hidden=true;});
})();
