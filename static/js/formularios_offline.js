/* Rascunhos e fila de campo privados por conta neste navegador. */
(() => {
  'use strict';
  const root=document.getElementById('campo-offline');
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
    const stored=await pacoteSalvo(usuario);
    return stored?.validade>Date.now()?stored:null;
  }
  const pacoteSalvo=usuario=>operation('pacotes','readonly',s=>s.get(usuario));
  const listar=usuario=>operation('formularios','readonly',s=>s.index('usuario').getAll(usuario));
  const obter=(usuario,id)=>operation('formularios','readonly',s=>s.get([usuario,id]));
  const rascunhoApagavel=row=>['rascunho','corrigir'].includes(row?.status);
  async function apagarRascunho(usuario,tipo,uuid,versao){
    if(blocked)throw Error('Entre novamente na conta do piloto.');
    const db=await database();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('formularios','readwrite'),store=tx.objectStore('formularios');
      const lookup=store.get([usuario,uuid]);
      let error;
      lookup.onsuccess=()=>{
        const row=lookup.result;
        if(blocked||row?.tipo!==tipo||!rascunhoApagavel(row)||row.localVersion!==versao){
          error=Error('O lançamento mudou ou já está na fila. Reabra a lista antes de tentar apagar.');
          tx.abort();
          return;
        }
        store.delete([usuario,uuid]);
      };
      tx.oncomplete=()=>resolve();
      tx.onabort=()=>reject(error||tx.error||Error('Não foi possível apagar o rascunho.'));
    });
  }
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
    const data=await json('/api/formularios/kobo/pacote-offline');
    if(data.usuario!==usuario || !data.referencias?.rg)throw Error('Confira a conta e a versão do servidor.');
    const script='/sw.js?v='+encodeURIComponent(data.release.versao);
    const registration=await navigator.serviceWorker.register(script,{updateViaCache:'none'});
    await registration.update();
    const installing=registration.installing;
    if(installing)await new Promise((resolve,reject)=>{
      const check=()=>{
        if(['installed','activating','activated'].includes(installing.state)){
          clearTimeout(timer);resolve();
        }else if(installing.state==='redundant'){
          clearTimeout(timer);reject(Error('Não foi possível instalar a atualização. Tente novamente.'));
        }
      };
      const timer=setTimeout(()=>reject(Error('A instalação demorou. Confira a conexão e tente novamente.')),15000);
      installing.addEventListener('statechange',check);
      check();
    });
    if(registration.waiting){
      await new Promise((resolve,reject)=>{
        const changed=()=>{clearTimeout(timer);resolve();};
        const timer=setTimeout(()=>{
          navigator.serviceWorker.removeEventListener('controllerchange',changed);
          reject(Error('Reabra o aplicativo para concluir a atualização.'));
        },12000);
        navigator.serviceWorker.addEventListener('controllerchange',changed,{once:true});
        registration.waiting.postMessage({type:'ATIVAR_ATUALIZACAO'});
      });
    }
    const active=(await navigator.serviceWorker.ready).active;
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
    return {...data,validade};
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
  window.CampoOffline={pacote,listar,obter,salvar,sync,apagarRascunho};
  if(!root)return;
  const usuario=Number(root.dataset.usuario),notice=document.getElementById('campo-offline-status');
  const actions=[...root.querySelectorAll('button')];
  let running=false;
  const homeList=document.getElementById('campo-offline-fila');
  const installButton=document.getElementById('campo-offline-instalar');
  const updateButton=document.getElementById('campo-offline-ver-atualizacao');
  const updateDialog=document.getElementById('campo-offline-atualizacao');
  let versionShown=null;
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
      if(rascunhoApagavel(row)){
        const button=document.createElement('button');
        button.type='button';button.className='btn btn-ghost fk-apagar';button.textContent='Apagar rascunho';
        button.onclick=()=>run(async()=>{
          if(!await confirmacaoDupla('Apagar este rascunho deste aparelho?'))return;
          await apagarRascunho(usuario,row.tipo,row.uuid,row.localVersion);
          notice.textContent='Rascunho apagado deste aparelho.';
        });
        li.append(button);
      }
      return li;
    }));
  }
  async function run(operation){
    if(running)return;
    running=true;actions.forEach(button=>button.disabled=true);
    try{await operation();}catch(e){notice.textContent=e.message;}
    finally{running=false;actions.forEach(button=>button.disabled=false);await refresh();}
  }
  function ready(current){
    const versao=current.release?.versao;
    notice.textContent='Pronto para uso offline até '+new Date(current.validade).toLocaleString('pt-BR')
      +(versao?' · versão '+versao:'')+'.';
  }
  async function checkUpdate(){
    if(blocked||running||!navigator.onLine)return;
    try{
      const current=await pacoteSalvo(usuario);
      if(!current)return;
      const desde=current.release?.versao||'';
      const latest=await json('/api/formularios/kobo/versao-offline?desde='+encodeURIComponent(desde));
      if(latest.usuario!==usuario||blocked||running)return;
      const available=latest.versao!==current.release?.versao;
      updateButton.hidden=!available;
      if(!available)return;
      document.getElementById('campo-offline-atualizacao-versao').textContent='Versão '+latest.versao;
      const changes=latest.atualizacoes??[{versao:latest.versao,mudancas:latest.mudancas}];
      const bullet=change=>{
        const li=document.createElement('li');li.textContent=change;return li;
      };
      const items=changes.length>1?changes.map(release=>{
        const section=document.createElement('li'), title=document.createElement('strong');
        const notes=document.createElement('ul');
        title.textContent='Versão '+release.versao;
        notes.append(...release.mudancas.map(bullet));
        section.append(title,notes);
        return section;
      }):(changes[0]?.mudancas||[]).map(bullet);
      document.getElementById('campo-offline-atualizacao-resumo').replaceChildren(...items);
      if(updateDialog.open)versionShown=latest.versao;
      if(versionShown!==latest.versao&&!document.querySelector('dialog[open]')){
        versionShown=latest.versao;
        updateDialog.showModal();
      }
    }catch{ /* A preparação vigente continua disponível durante falhas de consulta. */ }
  }
  const download=()=>run(async()=>{
    if(updateDialog.open)updateDialog.close();
    notice.textContent='Baixando formulários, quarteirões e logradouros…';
    const current=await prepare(usuario);
    updateButton.hidden=true;
    ready(current);
    if(document.documentElement.dataset.versao!==current.release.versao)location.reload();
  });
  document.getElementById('campo-offline-preparar').onclick=download;
  document.getElementById('campo-offline-atualizar').onclick=download;
  updateButton.onclick=()=>updateDialog.showModal();
  document.getElementById('campo-offline-sincronizar').onclick=()=>run(async()=>{
    notice.textContent='Enviando a fila para revisão…';
    const {sent,errors}=await sync(usuario);
    notice.textContent=sent+' recebido(s) para revisão.'+(errors.length?' '+errors[0]:'');
  });
  window.addEventListener('campo-bloqueado',()=>{
    if(updateDialog.open)updateDialog.close();
    updateButton.hidden=true;homeList.replaceChildren();notice.textContent='Entre novamente na conta do piloto.';
  });
  window.addEventListener('online',()=>{refresh().catch(e=>{notice.textContent=e.message;});checkUpdate();});
  window.addEventListener('offline',()=>refresh().catch(e=>{notice.textContent=e.message;}));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkUpdate();});
  setInterval(()=>{if(!document.hidden)checkUpdate();},300000);
  pacote(usuario).then(current=>{
    if(current)ready(current);
    else notice.textContent='Prepare este aparelho com internet para abrir os formulários offline.';
    checkUpdate();
    return refresh();
  }).catch(e=>{notice.textContent=e.message;});
})();
