/* Piloto de RG: salvar no aparelho primeiro; confirmar recebimento antes de limpar. */
(() => {
  'use strict';
  const version=new URL(document.currentScript.src).searchParams.get('v');
  const root=document.getElementById('rgc-app');if(!root)return;
  const $=id=>document.getElementById(id), store=window.RGCampoOffline;
  const context=JSON.parse($('rgc-contexto').textContent), owner=Number(document.querySelector('meta[name="offline-user"]')?.content);
  const piloto=root.dataset.piloto==='1';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const quadra=value=>/^\d+$/.test(String(value).trim())?String(value).trim().padStart(4,'0'):String(value).trim();
  const key=p=>`${p.id_localidade}:${quadra(p.quarteirao)}`;
  const state={snapshot:null,catalog:null,refs:[],rows:[],current:null,dirty:false,saveError:false,saveTimer:null,chain:Promise.resolve(),syncing:false,csrf:'',online:false,view:'quarteiroes',install:null,updating:false,generation:0,validade:0,saving:0};
  const newHouse=(lado='1',logradouro='',manual=false)=>({lado,logradouro,manual,numero:'',sequencia:'',tipo:'R',condominio:'0',observacao:''});
  function message(text,error=false){const el=$(error?'rgc-erro':'rgc-aviso');el.textContent=text;el.hidden=!text;}
  function connection(text,ready=false){$('rgc-conexao').textContent=text;state.online=ready;}
  const reason=(text,type,status)=>Object.assign(new Error(text),{type,status});
  async function api(path,method='GET',body){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(path,{method,cache:'no-store',credentials:'same-origin',redirect:'manual',signal:controller.signal,
        headers:{'Content-Type':'application/json','X-CSRFToken':state.csrf},body:body===undefined?undefined:JSON.stringify(body)});
      if(response.type==='opaqueredirect'||response.status===401)throw reason('Entre novamente para enviar. Seus rascunhos continuam neste aparelho.','login',401);
      const data=await response.json().catch(()=>({}));
      if(!response.ok){
        if(response.status>=500)throw reason('Servidor indisponível. Os rascunhos continuam neste aparelho.','servidor',response.status);
        const type=data.codigo==='conta_alterada'?'conta':response.status===403?'permissao':response.status===409?'conflito':response.status===400&&/token.*seguran/i.test(data.erro||'')?'csrf':'validacao';
        throw reason(data.erro||'Não foi possível concluir. Confira o envio. ',type,response.status);
      }
      return data;
    }catch(e){if(e.type)throw e;throw reason(navigator.onLine?'Conexão ou servidor indisponível. O trabalho permanece no aparelho.':'Sem internet. O trabalho permanece no aparelho.','rede',0);}
    finally{clearTimeout(timer);}
  }
  async function session(){
    const result=await api('/api/formularios/campo-sessao');
    if(result.usuario_id!==owner)throw reason('A conta mudou. Abra novamente a página online. Os dados da conta anterior foram preservados.','conta',403);
    state.csrf=result.csrf;state.validade=Date.now()+24*60*60*1000;
    await store.guardarMeta('autorizacao',state.validade);root.classList.remove('rgc-bloqueado');
    connection('Conectado ao sistema',true);$('rgc-login').hidden=true;return result;
  }
  function failure(e){
    connection(e.type==='login'?'É necessário entrar novamente':e.type==='conta'?'Conta alterada':e.type==='permissao'?'Acesso precisa de conferência':navigator.onLine?'Servidor ou conexão indisponível':'Sem internet');
    if(['login','permissao'].includes(e.type))$('rgc-login').hidden=false;
    if(e.type==='conta')navigator.serviceWorker?.controller?.postMessage({type:'LIMPAR_PAGINA'});
    message(e.message,true);
  }
  async function checkOfflineAccess(){
    if(Date.now()<state.validade)return true;
    if(state.current&&(state.dirty||state.saving))await flush();
    root.classList.add('rgc-bloqueado');connection('Preparação offline vencida');
    $('rgc-login').hidden=false;message('Conecte-se e abra novamente esta página para renovar o acesso offline. Seus rascunhos foram preservados.',true);return false;
  }
  async function localRows(){state.rows=await store.listarFormularios();return state.rows;}
  function label(row){
    if(row.erro)return 'Precisa de atenção';
    if(row.pendente_envio)return row.status==='enviado'?'Aguardando envio para revisão':'Rascunho aguardando envio';
    return ({oficializado:'Aplicado ao RG',aprovado:'Aprovado',devolvido:'Devolvido para correção',enviado:'Recebido para revisão',rascunho:'Rascunho recebido'})[row.servidor_status||row.status]||'Recebido pelo sistema';
  }
  async function summary(){
    await localRows();
    const pending=state.rows.filter(r=>r.pendente_envio).length;
    $('rgc-contagem').textContent=`${state.rows.length} formulário(s) neste aparelho · ${pending} pendente(s)`;
    if(state.view==='quarteiroes')renderBlocks();if(state.view==='envios')renderQueue();
  }
  async function view(name){
    if(state.current&&state.dirty)await flush();
    if(state.saveError)return;
    state.view=name;document.querySelectorAll('.rgc-view').forEach(el=>{el.hidden=el.id!=='view-'+name;});
    root.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===name));
    if(name==='quarteiroes'||name==='envios')await summary();
  }
  function updateRefs(){
    const refs = new Map((state.snapshot?.selecoes || []).map(ref=>[key(ref),ref]));
    for(const loc of state.catalog?.rg.localidades || []){
      for(const [display,ruas] of Object.entries(state.catalog.areas[loc.chave] || {})){
        const ref={id_localidade:loc.id_localidade,localidade:loc.nome,quarteirao:quadra(display),
          quarteirao_exibicao:display,logradouros:ruas};
        refs.set(key(ref),ref);
      }
    }
    state.refs=[...refs.values()];
  }
  function renderBlocks(){
    const local=$('rgc-territorio'),selected=local.value;
    const localidades=new Map(state.refs.map(ref=>[ref.id_localidade,ref.localidade]));
    local.replaceChildren(new Option('Selecione…',''),...[...localidades.entries()]
      .sort((a,b)=>a[1].localeCompare(b[1],'pt-BR')).map(([id,name])=>new Option(name,id)));
    local.value=localidades.has(Number(selected))?selected:'';
    renderQuadras();
  }
  function renderQuadras(){
    const local=Number($('rgc-territorio').value), control=$('rgc-quadra'), selected=control.value;
    const refs=state.refs.filter(ref=>ref.id_localidade===local).sort((a,b)=>a.quarteirao_exibicao
      .localeCompare(b.quarteirao_exibicao,'pt-BR',{numeric:true}));
    control.replaceChildren(new Option(local?'Selecione…':'Selecione a localidade…',''),
      ...refs.map(ref=>new Option(ref.quarteirao_exibicao,key(ref))));
    control.value=refs.some(ref=>key(ref)===selected)?selected:'';
    control.disabled=!refs.length;
    updateBlockMessage();
  }
  function updateBlockMessage(){
    const selected=$('rgc-quadra').value;
    $('rgc-preencher').disabled=!selected;
    if($('rgc-retirar'))$('rgc-retirar').hidden=!state.snapshot?.selecoes?.some(ref=>key(ref)===selected);
    const prior=state.rows.find(row=>key(row.payload)===selected);
    $('rgc-info').textContent=prior ? label(prior)
      : !state.refs.length ? (piloto?'Prepare os formulários de campo com internet para baixar os quarteirões.'
        :'Conecte-se ao sistema ou baixe os quarteirões em Preparar campo.') : '';
  }
  function renderQueue(){
    $('rgc-envios').innerHTML=state.rows.map(row=>`<article class="rgc-envio"><strong>${esc(row.payload.localidade||'Localidade')} · Q. ${esc(row.payload.quarteirao)}</strong><p>${esc(label(row))}</p>${row.erro?`<p>${esc(row.erro)}</p>`:''}<small>Última gravação no aparelho: ${esc(new Date(row.atualizado_em||row.criado_em).toLocaleString('pt-BR'))}${row.servidor_id?' · Recebimento #'+esc(row.servidor_id):''}</small>${!row.pendente_envio&&row.servidor_status==='oficializado'?`<p><button class="btn btn-ghost" type="button" data-action="limpar-recebido" data-uuid="${esc(row.uuid)}">Apagar somente a cópia deste aparelho</button></p>`:''}</article>`).join('')||'<p>Nenhum formulário neste aparelho.</p>';
  }
  async function options(){
    const data=await api('/api/registro-geografico/opcoes');
    $('rgc-localidade').innerHTML='<option value="">Selecione…</option>'+(data.localidades||[]).map(p=>`<option value="${p.id_localidade}">${esc(p.nome)}</option>`).join('');
  }
  async function chooseLocality(){
    const id=$('rgc-localidade').value;$('rgc-quarteiroes').innerHTML='';$('rgc-toda').checked=false;if(!id)return;
    const data=await api('/api/registro-geografico/quarteiroes?localidade='+encodeURIComponent(id));
    $('rgc-quarteiroes').innerHTML=(data.registros||[]).map(p=>`<label class="rgc-check"><input type="checkbox" value="${esc(p.quarteirao_raw||p.quarteirao)}">Q. ${esc(p.quarteirao)}</label>`).join('')||'<p>Nenhum quarteirão encontrado.</p>';
  }
  async function download(){
    await session();const id=Number($('rgc-localidade').value);
    const selections=[...$('rgc-quarteiroes').querySelectorAll('input:checked')].map(el=>({id_localidade:id,quarteirao:el.value}));
    if(!id||!selections.length)throw reason('Selecione a localidade e ao menos um quarteirão.','validacao');
    if(selections.length>500)throw reason('Baixe até 500 quarteirões por vez.','validacao');
    const data=await api('/api/formularios/rg/snapshot','POST',{selecoes:selections});
    const merged=new Map((state.snapshot?.selecoes||[]).map(p=>[key(p),p]));
    (data.selecoes||[]).forEach(p=>merged.set(key(p),p));
    state.snapshot=await store.salvarSnapshot({selecoes:[...merged.values()],tipos:data.tipos});
    updateRefs();
    const persistent=await store.persistencia().catch(()=>false);
    message(persistent?'Referências guardadas. Antes de sair, teste a abertura sem internet.':'Referências guardadas. O navegador não garantiu armazenamento persistente; não limpe seus dados enquanto houver pendências.');
    await view('quarteiroes');
  }
  function editorFrom(payload){
    if(payload._editor?.versao===2)return structuredClone(payload._editor.imoveis);
    const lines=payload._editor?.lados?.flatMap(side=>side.logradouros.flatMap(road=>
      road.imoveis.map(house=>({...house,lado:side.lado,logradouro:road.logradouro})))) || payload.linhas || [];
    return lines.length?lines.map(line=>({...newHouse(), ...line,
      lado:String(line.lado||'1'),logradouro:String(line.logradouro||''),
      numero:String(line.numero??''),sequencia:String(line.sequencia??''),
      condominio:String(line.condominio??0),observacao:String(line.observacao??'')})):[newHouse()];
  }
  async function open(){
    if(state.current&&(state.dirty||state.saving))await flush();if(state.saveError)return;
    const ref=state.refs.find(item=>key(item)===$('rgc-quadra').value);
    if(!ref)return;
    await localRows();
    const old=state.rows.filter(r=>key(r.payload)===key(ref)).sort((a,b)=>String(b.atualizado_em||b.criado_em).localeCompare(String(a.atualizado_em||a.criado_em)))[0];
    if(old&&!old.pendente_envio&&['enviado','aprovado','oficializado','em_revisao'].includes(old.servidor_status||old.status)){
      message('Este quarteirão já tem um formulário recebido para revisão. Acompanhe-o em Envios; solicite devolução para corrigir.');await view('envios');return;
    }
    state.current={ref,uuid:old?.uuid||crypto.randomUUID(),revisao:old?.revisao||0,dispositivo:old?.dispositivo,
      imoveis:old?editorFrom(old.payload):[newHouse()],agentes:old?.payload.agentes_ids||[context.agente?.id_agente].filter(Boolean),
      data:old?.payload.data_atualizacao||`${new Date().getFullYear()}-${String(new Date().getMonth()+1).padStart(2,'0')}-${String(new Date().getDate()).padStart(2,'0')}`,status:'rascunho'};
    state.dirty=false;state.saveError=false;
    $('rgc-form-titulo').textContent=`${ref.localidade} · Q. ${ref.quarteirao_exibicao||ref.quarteirao}`;
    $('rgc-form-data').value=state.current.data;
    $('rgc-form-agentes').innerHTML=context.agentes.map(a=>`<label class="rgc-check"><input type="checkbox" data-agent="${a.id_agente}" ${state.current.agentes.includes(a.id_agente)?'checked':''}>${esc(a.nome)}</label>`).join('')||'<p>Peça ao gestor para conferir o vínculo de agente da sua conta.</p>';
    renderEditor();await view('formulario');$('rgc-salvo').textContent=old?'Rascunho recuperado deste aparelho':'O preenchimento será salvo automaticamente neste aparelho';
  }
  function renderEditor(){
    const streets=state.current.ref.logradouros||[];
    const types=state.catalog?.rg.tipos||state.snapshot?.tipos||[];
    $('rgc-imoveis').innerHTML=state.current.imoveis.map((house,index)=>{
      const position=`data-index="${index}"`;
      const other=house.manual||Boolean(house.logradouro&&!streets.includes(house.logradouro));
      const field=(key,label,extra='')=>`<input aria-label="${label}, imóvel ${index+1}" data-field="${key}" ${position} value="${esc(house[key])}" ${extra}>`;
      return `<tr>
        <td class="rgc-lado-celula" data-label="Lado">${field('lado','Lado','maxlength="10" inputmode="numeric"')}</td>
        <td class="rgc-rua" data-label="Logradouro"><select data-field="rua-lista" ${position} aria-label="Logradouro, imóvel ${index+1}"><option value="">Selecione…</option>
          ${streets.map((rua,i)=>`<option value="${i}" ${!other&&rua===house.logradouro?'selected':''}>${esc(rua)}</option>`).join('')}
          <option value="outro" ${other?'selected':''}>Outro logradouro</option></select>
          ${other?`<div class="rgc-rua-manual">${field('logradouro','Outro logradouro','maxlength="250" placeholder="Digite o logradouro"')}</div>`:''}</td>
        <td data-label="Número">${field('numero','Número','maxlength="30" placeholder="Número ou SN"')}</td>
        <td data-label="Sequência">${field('sequencia','Sequência','maxlength="30" inputmode="numeric"')}</td>
        <td class="rgc-tipo-celula" data-label="Tipo"><select data-field="tipo" ${position} aria-label="Tipo, imóvel ${index+1}">
          ${types.map(t=>`<option value="${esc(t.codigo)}" ${t.codigo===house.tipo?'selected':''}>${esc(t.codigo)} — ${esc(t.nome)}</option>`).join('')}
        </select></td>
        <td data-label="Unidades de condomínio">${field('condominio','Unidades de condomínio','type="number" min="0" max="10000" inputmode="numeric"')}</td>
        <td data-label="Observação"><textarea aria-label="Observação, imóvel ${index+1}" data-field="observacao" ${position} rows="2" maxlength="2000" placeholder="Sem dados pessoais">${esc(house.observacao)}</textarea></td>
        <td data-label="Ações"><button class="btn btn-ghost" type="button" data-action="imovel-remover" ${position} aria-label="Remover imóvel ${index+1}">Remover</button></td>
      </tr>`;
    }).join('');
  }
  function changed(){state.generation++;state.dirty=true;state.current.status='rascunho';$('rgc-salvo').textContent='Salvando no aparelho…';clearTimeout(state.saveTimer);state.saveTimer=setTimeout(()=>flush(),400);}
  function capture(status){
    const current=state.current;
    const lines=current.imoveis.filter(house=>house.numero.trim()||house.observacao.trim())
      .map(house=>({logradouro:house.logradouro.trim(),numero:house.numero.trim()||'SN',sequencia:house.sequencia.trim()||null,
        tipo:house.tipo,lado:house.lado.trim()||'1',condominio:Number(house.condominio)||0,observacao:house.observacao.trim()||null}));
    const payload={id_localidade:current.ref.id_localidade,localidade:current.ref.localidade,quarteirao:current.ref.quarteirao,
      data_atualizacao:current.data||null,agentes_ids:[...current.agentes],linhas:lines,
      _editor:{versao:2,imoveis:structuredClone(current.imoveis)}};
    return {uuid:current.uuid,tipo:'rg_atualizacao',payload,status,dispositivo:current.dispositivo};
  }
  async function flush(status){
    clearTimeout(state.saveTimer);if(!state.current||!state.dirty&&!status)return state.chain;
    const current=state.current,record=capture(status||'rascunho'),generation=state.generation;state.dirty=false;state.saving++;
    state.chain=state.chain.catch(()=>{}).then(async()=>{
      try{
        const saved=await store.salvarFormulario(record,current.revisao);current.revisao=saved.revisao;current.dispositivo=saved.dispositivo;
        state.saveError=false;$('rgc-salvo').classList.remove('rgc-save-failed');
        if(current===state.current&&generation===state.generation&&state.saving===1){state.dirty=false;$('rgc-salvo').textContent='Salvo neste aparelho às '+new Date(saved.atualizado_em).toLocaleTimeString('pt-BR');}
        await summary();return saved;
      }catch(e){state.saveError=true;state.dirty=true;$('rgc-salvo').classList.add('rgc-save-failed');$('rgc-salvo').textContent='Ainda não foi salvo. Mantenha esta página aberta.';message(e.message,true);throw e;}
      finally{state.saving--;}
    });
    // O erro permanece visível; não anunciar sucesso nem apagar a revisão anterior.
    return state.chain.catch(()=>null);
  }
  function validate(){
    const record=capture('enviado');if(!record.payload.linhas.length)throw reason('Preencha ao menos um imóvel antes de enviar.','validacao');
    if(!state.current.data||!state.current.agentes.length)throw reason('Confira a data e os agentes da atualização.','validacao');
    if(record.payload.linhas.some(house=>!house.logradouro))throw reason('Informe o logradouro dos imóveis preenchidos.','validacao');
    if(record.payload.linhas.some(house=>!Number.isInteger(house.condominio)||house.condominio<0||house.condominio>10000))
      throw reason('Confira o número de unidades de condomínio.','validacao');
  }
  async function submit(){
    const warning=$('rgc-envio-erro');warning.hidden=true;
    try{validate();}catch(error){warning.textContent=error.message;warning.hidden=false;return;}
    if(!await confirmacaoDupla('Enviar este RG para a revisão do administrador?'))return;
    await flush('enviado');if(state.saveError)return;await view('envios');await sync();
  }
  async function syncBody(){
    if(state.current&&(state.dirty||state.saving))await flush();if(state.saveError)return;
    if(!navigator.onLine){connection('Sem internet');message('Os rascunhos estão guardados. Sincronize quando houver conexão.');return;}
    await session();message('',true);connection('Sincronizando…',true);
    let received=0;
    for(const row of await store.listarFormularios()){
      if(!row.pendente_envio)continue;
      if(!Number.isInteger(row.revisao)){await store.marcarErro(row.uuid,row.revisao,'Rascunho anterior: reabra o quarteirão e confira antes de enviar.');continue;}
      const body={tipo:row.tipo,payload:row.payload,status:row.status,uuid_cliente:row.uuid,usuario_offline:owner,
        captura:{versao:1,revisao:row.revisao,dispositivo:row.dispositivo}};
      try{
        let receipt;try{receipt=await api('/api/formularios','POST',body);}catch(e){if(e.type!=='csrf')throw e;await session();receipt=await api('/api/formularios','POST',body);}
        if(!receipt.ok||receipt.revisao_recebida!==row.revisao||receipt.uuid_cliente!==row.uuid)throw reason('O servidor não confirmou esta revisão. O rascunho foi preservado.','servidor');
        if(await store.marcarRecebido(row.uuid,row.revisao,receipt))received++;
      }catch(e){await store.marcarErro(row.uuid,row.revisao,e.message);if(['rede','servidor','login','conta','permissao'].includes(e.type))throw e;}
    }
    const own=await api('/api/formularios?tipo=rg_atualizacao&proprios=1');
    for(const form of own.formularios||[])if(form.usuario_id===owner)await store.atualizarRecebimento(form);
    connection('Conectado ao sistema',true);message('',true);message(received?`${received} formulário(s) recebido(s) pelo sistema.`:'Conferência concluída. Consulte Envios para acompanhar as pendências.');
    await summary();
  }
  async function sync(){
    if(state.syncing)return;state.syncing=true;$('rgc-sync').disabled=true;$('rgc-sync').textContent='Sincronizando…';
    try{
      if(navigator.locks)await navigator.locks.request('endemias-campo-sync-'+owner,{ifAvailable:true},async lock=>{if(lock)await syncBody();else message('Outra aba está sincronizando. Aguarde e confira Envios.');});
      else await syncBody();
    }catch(e){failure(e);}finally{state.syncing=false;$('rgc-sync').disabled=false;$('rgc-sync').textContent='Sincronizar agora';await summary().catch(()=>{});}
  }
  root.addEventListener('input',event=>{
    if(!state.current)return;const el=event.target;
    if(el.id==='rgc-form-data'){state.current.data=el.value;changed();return;}
    if(el.dataset.agent){state.current.agentes=[...$('rgc-form-agentes').querySelectorAll('input:checked')].map(x=>Number(x.dataset.agent));changed();return;}
    if(!el.dataset.field)return;
    const house=state.current.imoveis[Number(el.dataset.index)];
    if(el.dataset.field==='rua-lista'){
      house.manual=el.value==='outro';
      house.logradouro=el.value===''||house.manual?'':state.current.ref.logradouros[Number(el.value)];
      renderEditor();
      $('rgc-imoveis').querySelector(`[data-field="${house.manual?'logradouro':'rua-lista'}"][data-index="${el.dataset.index}"]`)?.focus();
    }else house[el.dataset.field]=el.value;
    changed();
  });
  async function action(button){
    if(!await checkOfflineAccess())return;
    const a=button.dataset.action;
    if(a==='abrir')return open();
    if(a==='retirar'){
      const selected=$('rgc-quadra').value;
      await localRows();
      if(state.rows.some(row=>key(row.payload)===selected&&row.pendente_envio))
        throw reason('Há um envio pendente neste quarteirão. Sincronize antes de retirar as referências.','validacao');
      if(!await confirmacaoDupla('Retirar somente as referências deste quarteirão do aparelho?'))return;
      state.snapshot.selecoes=state.snapshot.selecoes.filter(ref=>key(ref)!==selected);
      state.snapshot=await store.salvarSnapshot(state.snapshot);
      updateRefs();await summary();return;
    }
    if(a==='voltar'){await view('quarteiroes');return;}
    if(a==='salvar'){await flush('rascunho');if(!state.saveError)await sync();return;}
    if(a==='enviar')return submit();
    if(a==='limpar-recebido'){if(await confirmacaoDupla('Apagar somente a cópia deste aparelho? O registro recebido pelo sistema será preservado.')){await store.removerFormulario(button.dataset.uuid);await summary();}return;}
    const houses=state.current?.imoveis;if(!houses)return;
    if(a==='imovel-novo'){
      if(houses.length>=3000)throw reason('O RG comporta até 3.000 imóveis por quarteirão.','validacao');
      const last=houses.at(-1);
      houses.push(newHouse(last?.lado,last?.logradouro,last?.manual));
    }
    if(a==='imovel-remover'){
      if(!await confirmacaoDupla('Remover este imóvel do rascunho?'))return;
      houses.splice(Number(button.dataset.index),1);if(!houses.length)houses.push(newHouse());
    }
    changed();renderEditor();
    if(a==='imovel-novo')$('rgc-imoveis').querySelector(`[data-field="numero"][data-index="${houses.length-1}"]`)?.focus();
  }
  root.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    const task=button.dataset.view?()=>view(button.dataset.view):button.dataset.action?()=>action(button):null;
    if(task)Promise.resolve().then(task).catch(e=>message(e.message,true));
  });
  $('rgc-territorio').addEventListener('change',renderQuadras);
  $('rgc-quadra').addEventListener('change',updateBlockMessage);
  $('rgc-localidade')?.addEventListener('change',()=>chooseLocality().catch(failure));
  $('rgc-toda')?.addEventListener('change',()=>{$('rgc-quarteiroes').querySelectorAll('input').forEach(el=>{el.checked=$('rgc-toda').checked;});});
  $('rgc-baixar')?.addEventListener('click',()=>download().catch(e=>message(e.message,true)));
  $('rgc-sync').addEventListener('click',()=>sync());
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();state.install=event;$('rgc-instalar').hidden=false;});
  $('rgc-instalar').addEventListener('click',async()=>{await state.install?.prompt();state.install=null;$('rgc-instalar').hidden=true;});
  window.addEventListener('beforeunload',event=>{if(state.dirty||state.saveError||state.saving){event.preventDefault();event.returnValue='';}});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&state.dirty)flush();else if(document.visibilityState==='visible')checkOfflineAccess();});
  setInterval(()=>checkOfflineAccess(),60000);
  window.addEventListener('campo-bloqueado',()=>{
    state.validade=0;
    checkOfflineAccess();
  });
  window.addEventListener('offline',()=>connection('Sem internet'));
  window.addEventListener('online',()=>sync()); // Nunca recarrega o formulário em andamento.
  document.addEventListener('submit',async event=>{
    const form=event.target;if(new URL(form.action,location.href).pathname!=='/logout'||form.dataset.campoSaindo)return;
    event.preventDefault();await flush();if(state.saveError)return;form.dataset.campoSaindo='1';form.requestSubmit();
  },true);
  async function worker(){
    if(piloto||!('serviceWorker'in navigator))return;
    const script='/sw.js'+(version?'?v='+encodeURIComponent(version):'');
    const registration=await navigator.serviceWorker.register(script,{updateViaCache:'none'});
    const ready=()=>{$('rgc-atualizar').hidden=!registration.waiting;};ready();
    registration.addEventListener('updatefound',()=>registration.installing?.addEventListener('statechange',ready));
    $('rgc-atualizar').addEventListener('click',async()=>{await flush();if(state.saveError)return;state.updating=true;registration.waiting?.postMessage({type:'ATIVAR_ATUALIZACAO'});});
    navigator.serviceWorker.addEventListener('controllerchange',()=>{if(state.updating)location.reload();});
    await registration.update();
  }
  async function init(){
    try{
      if(!store?.disponivel())throw new Error('Para usar o RG neste aparelho, entre no endereço HTTPS oficial em um navegador com armazenamento local disponível.');
      state.validade=await store.obterMeta('autorizacao')||0;
      const pacote=piloto?await window.CampoOffline.pacote(owner):null;
      if(pacote?.referencias?.rg){
        state.catalog=pacote.referencias;
        state.validade=Math.max(state.validade,pacote.validade);
      }
      await store.limparRecebidos();state.snapshot=await store.obterSnapshot();updateRefs();await summary();
      worker().catch(()=>message('A preparação da página offline ainda não foi concluída. Mantenha a conexão e tente abrir novamente.'));
      if(navigator.onLine){
        try{
          await session();
          state.catalog=await api('/api/formularios/rg/referencias');
          updateRefs();await summary();
          if(!piloto)await options();
          await sync();
        }catch(e){failure(e);}
      }else {connection('Sem internet');await checkOfflineAccess();}
    }catch(e){
      message(e.message,true);connection('Armazenamento indisponível');$('rgc-sync').disabled=true;
      if($('rgc-baixar'))$('rgc-baixar').disabled=true;
    }
  }
  init();
})();
