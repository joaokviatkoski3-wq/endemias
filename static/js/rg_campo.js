/* Piloto de RG: salvar no aparelho primeiro; confirmar recebimento antes de limpar. */
(() => {
  'use strict';
  const root=document.getElementById('rgc-app');if(!root)return;
  const $=id=>document.getElementById(id), store=window.RGCampoOffline;
  const context=JSON.parse($('rgc-contexto').textContent), owner=Number(document.querySelector('meta[name="offline-user"]')?.content);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const key=p=>`${p.id_localidade}:${String(p.quarteirao).trim()}`;
  const state={snapshot:null,rows:[],current:null,dirty:false,saveError:false,saveTimer:null,chain:Promise.resolve(),syncing:false,csrf:'',online:false,view:'preparar',install:null,updating:false,generation:0,validade:0,saving:0};
  const newHouse=()=>({numero:'',sequencia:'',tipo:'R',condominio:0,observacao:''});
  const newRoad=()=>({logradouro:'',imoveis:[newHouse()]});
  const newSide=n=>({lado:String(n),logradouros:[newRoad()]});
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
  function renderBlocks(){
    const selections=state.snapshot?.selecoes||[];$('rgc-info').textContent=`${selections.length} quarteirão(ões)`;
    $('rgc-grid').innerHTML=selections.map((p,index)=>{
      const row=state.rows.filter(r=>key(r.payload)===key(p)).sort((a,b)=>String(b.atualizado_em||b.criado_em).localeCompare(String(a.atualizado_em||a.criado_em)))[0];
      return `<article class="rgc-card"><button type="button" data-action="abrir" data-index="${index}"><small>${esc(p.localidade)}</small><strong>Q. ${esc(p.quarteirao_exibicao||p.quarteirao)}</strong></button><span class="rgc-badge">${row?esc(label(row)):'Disponível para preencher'}</span><button class="btn btn-ghost" type="button" data-action="retirar" data-index="${index}">Retirar referências do aparelho</button></article>`;
    }).join('')||'<p>Nenhum quarteirão baixado. Use Preparar campo enquanto estiver conectado.</p>';
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
    const persistent=await store.persistencia().catch(()=>false);
    message(persistent?'Referências guardadas. Antes de sair, teste a abertura sem internet.':'Referências guardadas. O navegador não garantiu armazenamento persistente; não limpe seus dados enquanto houver pendências.');
    await view('quarteiroes');
  }
  function editorFrom(payload){
    if(payload._editor?.lados)return structuredClone(payload._editor.lados);
    const sides=[];
    for(const line of payload.linhas||[]){
      let side=sides.find(s=>s.lado===String(line.lado||'1'));if(!side){side={lado:String(line.lado||'1'),logradouros:[]};sides.push(side);}
      let road=side.logradouros.find(r=>r.logradouro===line.logradouro);if(!road){road={logradouro:line.logradouro||'',imoveis:[]};side.logradouros.push(road);}
      road.imoveis.push({...newHouse(),...line,numero:String(line.numero||''),sequencia:String(line.sequencia||''),observacao:String(line.observacao||'')});
    }
    return sides.length?sides:[newSide(1)];
  }
  async function open(index){
    if(state.current&&(state.dirty||state.saving))await flush();if(state.saveError)return;
    const ref=state.snapshot.selecoes[index];await localRows();
    const old=state.rows.filter(r=>key(r.payload)===key(ref)).sort((a,b)=>String(b.atualizado_em||b.criado_em).localeCompare(String(a.atualizado_em||a.criado_em)))[0];
    if(old&&!old.pendente_envio&&['enviado','aprovado','oficializado','em_revisao'].includes(old.servidor_status||old.status)){
      message('Este quarteirão já tem um formulário recebido para revisão. Acompanhe-o em Envios; solicite devolução para corrigir.');await view('envios');return;
    }
    state.current={ref,uuid:old?.uuid||crypto.randomUUID(),revisao:old?.revisao||0,dispositivo:old?.dispositivo,
      lados:old?editorFrom(old.payload):[newSide(1)],agentes:old?.payload.agentes_ids||[context.agente?.id_agente].filter(Boolean),
      data:old?.payload.data_atualizacao||`${new Date().getFullYear()}-${String(new Date().getMonth()+1).padStart(2,'0')}-${String(new Date().getDate()).padStart(2,'0')}`,status:'rascunho'};
    state.dirty=false;state.saveError=false;
    $('rgc-form-titulo').textContent=`${ref.localidade} · Q. ${ref.quarteirao_exibicao||ref.quarteirao}`;
    $('rgc-form-data').value=state.current.data;
    $('rgc-form-agentes').innerHTML=context.agentes.map(a=>`<label class="rgc-check"><input type="checkbox" data-agent="${a.id_agente}" ${state.current.agentes.includes(a.id_agente)?'checked':''}>${esc(a.nome)}</label>`).join('')||'<p>Peça ao gestor para conferir o vínculo de agente da sua conta.</p>';
    $('rgc-logradouros-list').innerHTML=(ref.logradouros||[]).map(r=>`<option value="${esc(r)}"></option>`).join('');
    renderEditor();await view('formulario');$('rgc-salvo').textContent=old?'Rascunho recuperado deste aparelho':'O preenchimento será salvo automaticamente neste aparelho';
  }
  function renderEditor(){
    const types=state.snapshot.tipos||[{codigo:'R',nome:'Residência'},{codigo:'C',nome:'Comércio'},{codigo:'O',nome:'Outros'},{codigo:'TB',nome:'Terreno baldio'}];
    $('rgc-lados').innerHTML=state.current.lados.map((side,li)=>`<section class="rgc-lado"><h3>Lado ${esc(side.lado)}</h3>${side.logradouros.map((road,gi)=>`<div class="rgc-logradouro"><label class="rgc-field">Logradouro<input list="rgc-logradouros-list" data-field="logradouro" data-li="${li}" data-gi="${gi}" value="${esc(road.logradouro)}" maxlength="250" placeholder="Selecione ou digite a rua" autocomplete="off"></label>${road.imoveis.map((house,ii)=>{
      const position=`data-li="${li}" data-gi="${gi}" data-ii="${ii}"`;
      return `<article class="rgc-imovel"><div class="rgc-item-heading"><strong>Imóvel ${ii+1}</strong><button class="btn btn-ghost" type="button" data-action="imovel-remover" ${position} aria-label="Remover imóvel ${ii+1}">Remover</button></div><div class="rgc-fields">
        <label class="rgc-field">Número<input data-field="numero" ${position} value="${esc(house.numero)}" maxlength="30" placeholder="Número ou SN"></label>
        <label class="rgc-field">Sequência<input data-field="sequencia" ${position} value="${esc(house.sequencia)}" maxlength="30" inputmode="numeric"></label>
        <label class="rgc-field">Tipo<select data-field="tipo" ${position}>${types.map(t=>`<option value="${esc(t.codigo)}" ${t.codigo===house.tipo?'selected':''}>${esc(t.codigo)} — ${esc(t.nome)}</option>`).join('')}</select></label>
        <label class="rgc-field">Unidades de condomínio<input data-field="condominio" ${position} type="number" min="0" max="10000" value="${Number(house.condominio)||0}" inputmode="numeric"><small>0 quando não for condomínio</small></label>
        <label class="rgc-field rgc-wide">Observação do imóvel<textarea data-field="observacao" ${position} maxlength="2000" placeholder="Sem dados pessoais de moradores">${esc(house.observacao)}</textarea></label></div></article>`;
    }).join('')}<div class="rgc-log-heading"><button class="btn btn-outline" type="button" data-action="imovel-novo" data-li="${li}" data-gi="${gi}">Novo imóvel nesta rua</button><button class="btn btn-ghost" type="button" data-action="rua-remover" data-li="${li}" data-gi="${gi}">Remover logradouro</button></div></div>`).join('')}<div class="rgc-lado-actions"><button class="btn btn-outline" type="button" data-action="rua-nova" data-li="${li}">Novo logradouro neste lado</button></div></section>`).join('');
  }
  function changed(){state.generation++;state.dirty=true;state.current.status='rascunho';$('rgc-salvo').textContent='Salvando no aparelho…';clearTimeout(state.saveTimer);state.saveTimer=setTimeout(()=>flush(),400);}
  function capture(status){
    const current=state.current,lines=[];
    for(const side of current.lados)for(const road of side.logradouros)for(const house of road.imoveis){
      if(!house.numero.trim()&&!house.observacao.trim())continue;
      lines.push({logradouro:road.logradouro.trim()||'Sem logradouro',numero:house.numero.trim()||'SN',sequencia:house.sequencia.trim()||null,
        tipo:house.tipo,lado:side.lado,condominio:Number(house.condominio)||0,observacao:house.observacao.trim()||null});
    }
    const payload={id_localidade:current.ref.id_localidade,localidade:current.ref.localidade,quarteirao:current.ref.quarteirao,
      data_atualizacao:current.data||null,agentes_ids:[...current.agentes],linhas:lines,_editor:{versao:1,lados:structuredClone(current.lados)}};
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
    if(state.current.lados.some(s=>s.logradouros.some(r=>r.imoveis.some(h=>(h.numero.trim()||h.observacao.trim())&&!r.logradouro.trim()))))throw reason('Informe a rua dos imóveis preenchidos.','validacao');
  }
  async function submit(){
    validate();if(!await confirmacaoDupla('Enviar este RG para a revisão do administrador?'))return;
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
  async function retire(index){
    const ref=state.snapshot.selecoes[index];await localRows();
    if(state.rows.some(r=>key(r.payload)===key(ref)&&r.pendente_envio))throw reason('Há um envio pendente neste quarteirão. Sincronize antes de retirar as referências.','validacao');
    if(!await confirmacaoDupla('Retirar somente as referências deste quarteirão do aparelho?'))return;
    state.snapshot.selecoes.splice(index,1);state.snapshot=await store.salvarSnapshot(state.snapshot);await summary();
  }
  root.addEventListener('input',event=>{
    if(!state.current)return;const el=event.target;
    if(el.id==='rgc-form-data'){state.current.data=el.value;changed();return;}
    if(el.dataset.agent){state.current.agentes=[...$('rgc-form-agentes').querySelectorAll('input:checked')].map(x=>Number(x.dataset.agent));changed();return;}
    if(!el.dataset.field)return;
    const road=state.current.lados[Number(el.dataset.li)].logradouros[Number(el.dataset.gi)];
    if(el.dataset.field==='logradouro')road.logradouro=el.value;else road.imoveis[Number(el.dataset.ii)][el.dataset.field]=el.value;
    changed();
  });
  async function action(button){
    if(!await checkOfflineAccess())return;
    const a=button.dataset.action,li=Number(button.dataset.li),gi=Number(button.dataset.gi),ii=Number(button.dataset.ii);
    if(a==='abrir')return open(Number(button.dataset.index));if(a==='retirar')return retire(Number(button.dataset.index));
    if(a==='voltar')return view('quarteiroes');if(a==='salvar'){await flush('rascunho');if(!state.saveError)await sync();return;}if(a==='enviar')return submit();
    if(a==='limpar-recebido'){if(await confirmacaoDupla('Apagar somente a cópia deste aparelho? O registro recebido pelo sistema será preservado.')){await store.removerFormulario(button.dataset.uuid);await summary();}return;}
    const current=state.current;if(!current)return;
    if(a==='lado-novo')current.lados.push(newSide(current.lados.length+1));
    if(a==='rua-nova')current.lados[li].logradouros.push(newRoad());
    if(a==='imovel-novo')current.lados[li].logradouros[gi].imoveis.push(newHouse());
    if(a==='imovel-remover'){if(!await confirmacaoDupla('Remover este imóvel do rascunho?'))return;const houses=current.lados[li].logradouros[gi].imoveis;houses.splice(ii,1);if(!houses.length)houses.push(newHouse());}
    if(a==='rua-remover'){if(!await confirmacaoDupla('Remover este logradouro e os imóveis dele?'))return;const roads=current.lados[li].logradouros;roads.splice(gi,1);if(!roads.length)roads.push(newRoad());}
    changed();renderEditor();
  }
  root.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    const task=button.dataset.view?()=>view(button.dataset.view):button.dataset.action?()=>action(button):null;
    if(task)Promise.resolve().then(task).catch(e=>message(e.message,true));
  });
  $('rgc-localidade').addEventListener('change',()=>chooseLocality().catch(failure));
  $('rgc-toda').addEventListener('change',()=>{$('rgc-quarteiroes').querySelectorAll('input').forEach(el=>{el.checked=$('rgc-toda').checked;});});
  $('rgc-baixar').addEventListener('click',()=>download().catch(e=>message(e.message,true)));
  $('rgc-sync').addEventListener('click',()=>sync());
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();state.install=event;$('rgc-instalar').hidden=false;});
  $('rgc-instalar').addEventListener('click',async()=>{await state.install?.prompt();state.install=null;$('rgc-instalar').hidden=true;});
  window.addEventListener('beforeunload',event=>{if(state.dirty||state.saveError||state.saving){event.preventDefault();event.returnValue='';}});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&state.dirty)flush();else if(document.visibilityState==='visible')checkOfflineAccess();});
  setInterval(()=>checkOfflineAccess(),60000);
  window.addEventListener('offline',()=>connection('Sem internet'));
  window.addEventListener('online',()=>sync()); // Nunca recarrega o formulário em andamento.
  document.addEventListener('submit',async event=>{
    const form=event.target;if(new URL(form.action,location.href).pathname!=='/logout'||form.dataset.campoSaindo)return;
    event.preventDefault();await flush();if(state.saveError)return;form.dataset.campoSaindo='1';form.requestSubmit();
  },true);
  async function worker(){
    if(!('serviceWorker'in navigator))return;
    const registration=await navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'});
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
      await store.limparRecebidos();state.snapshot=await store.obterSnapshot();await summary();
      if(state.snapshot?.selecoes?.length)await view('quarteiroes');
      worker().catch(()=>message('A preparação da página offline ainda não foi concluída. Mantenha a conexão e tente abrir novamente.'));
      if(navigator.onLine){try{await session();await options();await sync();}catch(e){failure(e);}}
      else {connection('Sem internet');await checkOfflineAccess();}
    }catch(e){message(e.message,true);connection('Armazenamento indisponível');$('rgc-sync').disabled=true;$('rgc-baixar').disabled=true;}
  }
  init();
})();
