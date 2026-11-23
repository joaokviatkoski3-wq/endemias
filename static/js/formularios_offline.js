/* Rascunhos e fila de campo privados por conta neste navegador. */
(() => {
  'use strict';
  const root=document.getElementById('campo-offline');
  const version=new URL(document.currentScript.src).searchParams.get('v');
  let dbPromise,blocked=false;
  let syncPromise=null;
  navigator.serviceWorker?.addEventListener('message',event=>{
    if(event.data?.type==='BLOQUEAR_CAMPO'){
      blocked=true;
      window.dispatchEvent(new Event('campo-bloqueado'));
    }
  });
  function database(){
    if(!dbPromise)dbPromise=new Promise((resolve,reject)=>{
      const request=indexedDB.open('endemias-campo',1);
      request.onupgradeneeded=()=>{
        request.result.createObjectStore('pacotes',{keyPath:'usuario'});
        request.result.createObjectStore('formularios',{keyPath:['usuario','uuid']})
          .createIndex('usuario','usuario');
      };
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
    });
    return dbPromise;
  }
  async function operation(table,mode,fn){
    const db=await database();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction(table,mode);
      const request=fn(tx.objectStore(table));
      tx.oncomplete=()=>resolve(request.result);
      tx.onabort=tx.onerror=()=>reject(tx.error||Error('Não foi possível gravar neste aparelho.'));
    });
  }
  async function pacote(usuario){
    if(blocked)return null;
    const stored=await operation('pacotes','readonly',s=>s.get(usuario));
    return stored?.validade>Date.now()?stored:null;
  }
  const listar=usuario=>operation('formularios','readonly',s=>s.index('usuario').getAll(usuario));
  const obter=(usuario,id)=>operation('formularios','readonly',s=>s.get([usuario,id]));
  async function salvar(record,expected=0){
    if(blocked)throw Error('Entre novamente na conta do piloto.');
    const db=await database();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('formularios','readwrite'),store=tx.objectStore('formularios');
      const lookup=store.get([record.usuario,record.uuid]);
      let conflict=false;
      const next={...record,localVersion:expected+1};
      lookup.onsuccess=()=>{
        if((lookup.result?.localVersion||0)!==expected){conflict=true;tx.abort();}
        else store.put(next);
      };
      tx.oncomplete=()=>resolve(next);
      tx.onabort=()=>reject(Error(conflict?'Este formulário mudou em outra aba. Reabra o rascunho antes de editar.':
        'Não foi possível gravar neste aparelho. As alterações continuam na tela.'));
    });
  }
  async function json(url,body,csrf){
    const response=await fetch(url,{
      method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',redirect:'manual',
      signal:AbortSignal.timeout(25000),
      ...(body?{body:JSON.stringify(body),headers:{'Content-Type':'application/json','X-CSRFToken':csrf}}:{})
    });
    const data=await response.json().catch(()=>null);
    if(!response.ok || !data){
      const e=Error(data?.erro||'Entre novamente na conta do piloto e tente sincronizar.');
      e.http=response.status;throw e;
    }
    return data;
  }
  const endpoint=tipo=>'/api/formularios/kobo/'+encodeURIComponent(tipo);
  async function session(usuario,tipo){
    const result=await json(endpoint(tipo)+'/sessao');
    if(result.usuario!==usuario || !result.offline)throw Error('Entre na conta autorizada para este piloto.');
    return result;
  }
  async function prepare(usuario){
    if(!window.isSecureContext || !navigator.serviceWorker)throw Error('Abra o sistema pelo endereço HTTPS.');
    const script='/sw.js'+(version?'?v='+encodeURIComponent(version):'');
    const registration=await navigator.serviceWorker.register(script,{updateViaCache:'none'});
    await registration.update();
    if(registration.waiting){
      registration.waiting.postMessage({type:'ATIVAR_ATUALIZACAO'});
      await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(Error('Reabra o aplicativo para concluir a atualização.')),12000);
        navigator.serviceWorker.addEventListener('controllerchange',()=>{clearTimeout(timer);resolve();},{once:true});
      });
    }
    const active=(await navigator.serviceWorker.ready).active;
    const data=await json('/api/formularios/kobo/pacote-offline');
    if(data.usuario!==usuario)throw Error('A conta mudou durante a preparação.');
    const channel=new MessageChannel();
    const validade=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('A preparação demorou. Confira a conexão e tente novamente.')),45000);
      channel.port1.onmessage=({data:receipt})=>{
        clearTimeout(timer);channel.port1.close();
        if(receipt.erro)reject(Error(receipt.erro));else resolve(receipt.validade);
      };
      active.postMessage({type:'PREPARAR_CAMPO',user:usuario},[channel.port2]);
    });
    await session(usuario,'PE');
    blocked=false;
    await operation('pacotes','readwrite',store=>store.put({...data,validade}));
    return validade;
  }
  async function sync(usuario,uuid=null){
    if(syncPromise)return syncPromise;
    syncPromise=(async()=>{
      if(blocked)throw Error('Reabra a área offline com a conta do piloto.');
      const rows=(await listar(usuario)).filter(row=>row.status==='fila'&&(!uuid||row.uuid===uuid));
      const errors=[];
      let sent=0;
      for(const row of rows){
        const auth=await session(usuario,row.tipo);
        try{
          const receipt=await json(endpoint(row.tipo),row.request,auth.csrf);
          if(receipt.revisao!==row.request.captura.revisao || !receipt.id)throw Error('O servidor não confirmou o recebimento.');
          await salvar({...row,status:'recebido',request:null,payload:null,id:receipt.id},row.localVersion);
          sent++;
        }catch(e){
          if(e.http===400){
            await salvar({...row,status:'corrigir',erro:e.message},row.localVersion);
          }else if(e.http!==409){
            errors.push(e.message);break;
          }
          errors.push(e.message);
        }
      }
      return {sent,errors};
    })();
    try{return await syncPromise;}finally{syncPromise=null;}
  }
  window.CampoOffline={pacote,listar,obter,salvar,sync};
  if(!root)return;
  const usuario=Number(root.dataset.usuario),notice=document.getElementById('campo-offline-status');
  const actions=[...root.querySelectorAll('button')];
  let running=false;
  const homeList=document.getElementById('campo-offline-fila');
  const installButton=document.getElementById('campo-offline-instalar');
  let installPrompt;
  window.addEventListener('beforeinstallprompt',event=>{
    event.preventDefault();
    installPrompt=event;installButton.hidden=false;
  });
  installButton.onclick=async()=>{
    if(!installPrompt)return;
    await installPrompt.prompt();
    installPrompt=null;installButton.hidden=true;
  };
  async function refresh(){
    if(blocked){homeList.replaceChildren();return;}
    if(!navigator.onLine && !await pacote(usuario)){homeList.replaceChildren();return;}
    const items=(await listar(usuario)).sort((a,b)=>b.atualizado-a.atualizado);
    const label={rascunho:'Rascunho neste aparelho',fila:'Na fila para enviar',
      corrigir:'Precisa de correção',recebido:'Recebido para revisão'};
    homeList.replaceChildren(...items.map(row=>{
      const li=document.createElement('li'),link=document.createElement('a');
      link.textContent=(root.querySelector('[data-form="'+CSS.escape(row.tipo)+'"]')?.textContent||row.tipo).trim();
      if(row.status==='recebido'){
        link.href='/formularios/kobo/'+encodeURIComponent(row.tipo)+'?envio='+row.id;
        if(!navigator.onLine)link.removeAttribute('href');
      }else link.href='/formularios/kobo/'+encodeURIComponent(row.tipo)+'?local='+encodeURIComponent(row.uuid);
      li.append(link,' · '+label[row.status]+' · '+new Date(row.atualizado).toLocaleString('pt-BR'));
      if(row.erro){const detail=document.createElement('p');detail.textContent=row.erro;li.append(detail);}
      return li;
    }));
  }
  async function run(operation){
    if(running)return;
    running=true;actions.forEach(button=>button.disabled=true);
    try{await operation();}catch(e){notice.textContent=e.message;}
    finally{running=false;actions.forEach(button=>button.disabled=false);await refresh();}
  }
  document.getElementById('campo-offline-preparar').onclick=()=>run(async()=>{
    notice.textContent='Baixando formulários e listas para este aparelho…';
    const until=await prepare(usuario);
    notice.textContent='Pronto para uso offline até '+new Date(until).toLocaleString('pt-BR')+'.';
  });
  document.getElementById('campo-offline-sincronizar').onclick=()=>run(async()=>{
    notice.textContent='Enviando a fila para revisão…';
    const {sent,errors}=await sync(usuario);
    notice.textContent=sent+' recebido(s) para revisão.'+(errors.length?' '+errors[0]:'');
  });
  window.addEventListener('campo-bloqueado',()=>{homeList.replaceChildren();notice.textContent='Entre novamente na conta do piloto.';});
  window.addEventListener('online',()=>refresh().catch(e=>{notice.textContent=e.message;}));
  window.addEventListener('offline',()=>refresh().catch(e=>{notice.textContent=e.message;}));
  pacote(usuario).then(current=>{
    if(current)notice.textContent='Pronto para uso offline até '+new Date(current.validade).toLocaleString('pt-BR')+'.';
    return refresh();
  }).catch(e=>{notice.textContent=e.message;});
})();
