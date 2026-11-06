/* Dados por origem/conta. Piloto sem senha extra: use o bloqueio do aparelho. */
(() => {
  const owner = document.querySelector('meta[name="offline-user"]')?.content;
  const DB_NAME = owner ? `endemias_formularios_usuario_${owner}` : 'endemias_formularios';
  const issue = message => new Error(message);
  function abrir() {
    return new Promise((resolve, reject) => {
      if (!owner || !/^[1-9]\d*$/.test(owner)) return reject(issue('Entre novamente para identificar os dados deste aparelho.'));
      if (!window.isSecureContext || !('indexedDB' in window)) return reject(issue('Abra o endereço HTTPS oficial para preparar o uso offline.'));
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        const db=request.result;
        for (const [store,keyPath] of [['snapshot','id'],['formularios','uuid']]) {
          if (!db.objectStoreNames.contains(store)) db.createObjectStore(store,{keyPath});
        }
      };
      request.onsuccess = () => { request.result.onversionchange=()=>request.result.close(); resolve(request.result); };
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(issue('Feche outras abas da área de campo para atualizar o armazenamento.'));
    });
  }
  async function operation(store,write,callback) {
    const db=await abrir();
    return new Promise((resolve,reject) => {
      const tx=db.transaction(store,write?'readwrite':'readonly');
      let result,error;
      const set=value=>{result=value;};
      const fail=value=>{error=value;tx.abort();};
      tx.oncomplete=()=>{db.close();resolve(result);};
      tx.onabort=tx.onerror=()=>{db.close();reject(error||tx.error||issue('Não foi possível guardar neste aparelho. Confira o espaço disponível.'));};
      try { callback(tx.objectStore(store),set,fail); } catch(e) { fail(e); }
    });
  }
  const get=(store,key)=>operation(store,false,(s,set)=>{s.get(key).onsuccess=e=>set(e.target.result||null);});
  const all=store=>operation(store,false,(s,set)=>{s.getAll().onsuccess=e=>set(e.target.result||[]);});
  const put=(store,row)=>operation(store,true,(s,set)=>{s.put(row);set(row);});
  async function dispositivo() {
    return operation('snapshot',true,(s,set)=>{s.get('meta:dispositivo').onsuccess=e=>{
      const row=e.target.result||{id:'meta:dispositivo',valor:crypto.randomUUID()};s.put(row);set(row.valor);
    };});
  }
  async function salvarFormulario(form,expected) {
    const device=form.dispositivo||await dispositivo();
    if(new TextEncoder().encode(JSON.stringify(form)).length>2*1024*1024) throw issue('Rascunho muito grande. Divida o levantamento.');
    return operation('formularios',true,(s,set,fail)=>{s.get(form.uuid).onsuccess=e=>{
      const old=e.target.result,revision=Number(old?.revisao||0);
      if(expected!==undefined&&expected!==revision) return fail(issue('Este formulário mudou em outra aba. Reabra o quarteirão antes de continuar.'));
      const row={...old,...form,dispositivo:device,revisao:revision+1,
        criado_em:old?.criado_em||new Date().toISOString(),atualizado_em:new Date().toISOString(),pendente_envio:true,erro:null};
      s.put(row);set(row);
    };});
  }
  async function marcarRecebido(id,revision,receipt) {
    return operation('formularios',true,(s,set)=>{s.get(id).onsuccess=e=>{
      const row=e.target.result;
      if(!row||row.revisao!==revision||receipt.revisao_recebida!==revision||receipt.uuid_cliente!==id||!receipt.id_formulario) return set(false);
      s.put({...row,pendente_envio:false,erro:null,recebido_em:new Date().toISOString(),servidor_id:receipt.id_formulario,servidor_status:receipt.status_atual});set(true);
    };});
  }
  async function marcarErro(id,revision,message) {
    return operation('formularios',true,s=>{s.get(id).onsuccess=e=>{
      const row=e.target.result;if(row?.revisao===revision)s.put({...row,erro:String(message).slice(0,250)});
    };});
  }
  async function atualizarRecebimento(form) {
    return operation('formularios',true,(s,set)=>{s.get(form.uuid_cliente).onsuccess=e=>{
      const row=e.target.result,meta=form.payload?._captura_campo;
      if(!row||row.pendente_envio||!meta||meta.revisao!==row.revisao||meta.dispositivo!==row.dispositivo)return set(false);
      const payload=structuredClone(form.payload);delete payload._captura_campo;
      s.put({...row,payload,servidor_status:form.status,motivo_devolucao:form.motivo_devolucao||null});set(true);
    };});
  }
  async function limparRecebidos() {
    const cutoff=Date.now()-7*86400000;
    return operation('formularios',true,s=>{s.openCursor().onsuccess=e=>{
      const cursor=e.target.result;if(!cursor)return;
      if(!cursor.value.pendente_envio&&cursor.value.servidor_status==='oficializado'&&Date.parse(cursor.value.recebido_em)<cutoff)cursor.delete();cursor.continue();
    };});
  }
  async function removerFormulario(id) {
    return operation('formularios',true,(s,set,fail)=>{s.get(id).onsuccess=e=>{
      if(e.target.result?.pendente_envio)return fail(issue('Envio pendente: sincronize antes de apagar.'));
      if(e.target.result&&e.target.result.servidor_status!=='oficializado')return fail(issue('Preserve esta cópia até a oficialização no RG.'));
      s.delete(id);set(true);
    };});
  }
  window.RGCampoOffline={
    disponivel:()=>!!owner&&window.isSecureContext&&'indexedDB'in window,
    salvarSnapshot:snap=>put('snapshot',{...snap,id:'snapshot',baixado_em:new Date().toISOString()}),
    obterSnapshot:()=>get('snapshot','snapshot'),salvarFormulario,listarFormularios:()=>all('formularios'),removerFormulario,
    marcarRecebido,marcarErro,limparRecebidos,atualizarRecebimento,
    guardarMeta:(id,valor)=>put('snapshot',{id:'meta:'+id,valor}),obterMeta:async id=>(await get('snapshot','meta:'+id))?.valor,
    async persistencia(){const storage=navigator.storage;if(!storage)return false;return await storage.persisted?.()||await storage.persist?.()||false;},
  };
})();
