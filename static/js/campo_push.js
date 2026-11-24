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
  const estadosTeste={
    agendado:'Teste agendado. Feche o app sem tocar em Sair e bloqueie a tela.',
    aceito:'O serviço de notificações aceitou o teste. Confira os avisos no Android.',
    expirado:'O serviço de notificações não confirmou o teste a tempo. Tente novamente.'
  };
  async function api(acao=null) {
    const response=await fetch(endpoint,{cache:'no-store',signal:AbortSignal.timeout(10000),
      ...(acao?{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':config.csrf},
        body:JSON.stringify({usuario,acao,endpoint:subscription?.endpoint})}:{})});
    const data=await response.json().catch(()=>({}));
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
    delete status.dataset.erro;
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
      dizer(estadosTeste[config.teste_estado]||ativos(),true);
    }else if(Notification.permission==='denied'){
      dizer('Para ativar, permita as notificações do VSATT nas configurações do Chrome.');
    }else if(subscription){
      dizer('O cadastro de avisos deste aparelho precisa ser confirmado. Toque em Ativar avisos neste aparelho.',false,true);
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
  async function executar(button, ocupado, act) {
    if(busy)return;
    busy=true;
    const original=button.textContent;
    button.textContent=ocupado;
    status.textContent=ocupado;
    delete status.dataset.erro;
    for(const button of [ativar,testar,desativar])button.disabled=true;
    try {await act();}
    catch(e){
      status.dataset.erro='1';
      status.textContent=e.name==='NotAllowedError'?'O Chrome não permitiu os avisos. Confira a permissão de notificações para o VSATT.'
        :e.name==='AbortError'?'O Chrome não concluiu o cadastro dos avisos. Confira a internet e tente de novo.'
        :e.name==='TimeoutError'||e instanceof TypeError?'A comunicação demorou. Confira a internet e tente de novo.'
        :e.message||'Não foi possível configurar os avisos.';
    }
    finally{
      busy=false;
      button.textContent=original;
      for(const button of [ativar,testar,desativar])button.disabled=false;
      status.scrollIntoView({block:'nearest'});
    }
  }
  ativar.onclick=()=>executar(ativar,'Ativando avisos…',async()=>{
    const permission=Notification.permission==='granted'?'granted':await Notification.requestPermission();
    if(permission!=='granted'){
      dizer('Os avisos dependem da sua permissão de notificações no Chrome.',false,permission!=='denied');
      return;
    }
    const encoded=config.chave.replaceAll('-','+').replaceAll('_','/');
    const key=Uint8Array.from(atob(encoded),ch=>ch.charCodeAt(0));
    const previousKey=new Uint8Array(subscription?.options?.applicationServerKey||key);
    if(subscription&&(previousKey.length!==key.length||!key.every((byte,index)=>byte===previousKey[index]))){
      await subscription.unsubscribe();
      subscription=null;
    }
    subscription??=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
    try{
      config=await api();
      await worker('PUSH_ATIVAR');
      await api('ativar');
    }catch(e){
      await Promise.allSettled([worker('PUSH_DESATIVAR'),subscription.unsubscribe()]);
      subscription=null;
      throw e;
    }
    dizer(ativos(),true);
  });
  desativar.onclick=()=>executar(desativar,'Desativando avisos…',async()=>{
    config=await api();
    await api('desativar');
    await worker('PUSH_DESATIVAR');
    subscription=null;
    dizer('Avisos desativados neste aparelho.',false,true);
  });
  testar.onclick=()=>executar(testar,'Agendando teste…',async()=>{
    config=await api();
    const data=await api('testar');
    const espera=data.segundos_para_fechar||20;
    status.textContent='Teste agendado. Você tem '+espera+' segundos para fechar o app sem tocar em Sair e bloquear a tela.';
  });
  sino.addEventListener('click',()=>carregar().catch(()=>{box.hidden=true;}));
  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden&&document.getElementById('campo-avisos')?.open)carregar().catch(()=>{box.hidden=true;});
  });
  navigator.serviceWorker.addEventListener('message',event=>{
    if(event.data?.type==='BLOQUEAR_CAMPO')box.hidden=true;
  });
  if(document.getElementById('campo-avisos')?.open)carregar().catch(()=>{box.hidden=true;});
})();
