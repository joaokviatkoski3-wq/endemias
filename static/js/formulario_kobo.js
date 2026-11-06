/* Piloto online. Nenhum conteúdo pessoal é gravado no armazenamento offline. */
(() => {
  'use strict';
  const root=document.getElementById('fk-app');if(!root)return;
  const $=id=>document.getElementById(id),tipo=root.dataset.tipo,owner=Number(root.dataset.usuario),review=root.dataset.revisao==='1';
  const base='/api/formularios/kobo/'+encodeURIComponent(tipo);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let schema,current,busy=false,dirty=false,seq=0,listRequest=0,geoRequest=0,geoTimer;
  const geoCache=new Map();
  function fixed(n){return (current?.payload?.responsavel||(!review&&current?.status==='novo'?schema?.responsavel:null))?.campos?.[n.path];}
  function anchor(){for(const n of all(schema.nodes)){const code=fixed(n);if(!code)continue;const raw=current.payload.values;raw[n.path]=n.kind==='select_multiple'?[...new Set([code,...String(raw[n.path]||'').split(/\s+/).filter(Boolean)])].join(' '):code;}}
  let autoTimer,autoFlight=null,pendingSave=null,pendingSerial=0,editSerial=0,saveBlocked=false;
  const saveMessage=text=>$('fk-save-status').textContent=text;
  function editable(){return current&&!review&&['novo','rascunho','devolvido'].includes(current.status);}
  function scheduleSave(delay=1800){clearTimeout(autoTimer);if(editable()&&dirty&&!busy&&!saveBlocked)autoTimer=setTimeout(()=>autoSave(),delay);}
  async function autoSave(){
    if(saveBlocked)return false;
    if(autoFlight)return autoFlight;
    if(!editable()||!dirty||busy)return true;
    if(!navigator.onLine){saveMessage('Sem conexão: alterações ainda não salvas. Mantenha a tela aberta.');return false;}
    const active=current;
    if(!pendingSave){pendingSerial=editSerial;current.payload.fim=timestamp();pendingSave={usuario:owner,uuid:current.uuid,payload:structuredClone(current.payload),status:'rascunho',captura:{versao:1,revisao:(current.captura.revisao||0)+1,dispositivo:current.captura.dispositivo}};}
    const request=pendingSave,serial=pendingSerial;saveMessage('Salvando rascunho…');
    autoFlight=(async()=>{try{
      const receipt=await api(base,'POST',request);
      if(receipt.revisao!==request.captura.revisao)throw Error('Revisão não confirmada. Confira seus envios.');
      if(current!==active)return true;
      current.id=receipt.id;current.captura.revisao=receipt.revisao;current.status='rascunho';
      history.replaceState(null,'',location.pathname+'?envio='+receipt.id);
      pendingSave=null;dirty=serial!==editSerial;
      saveMessage(dirty?'Há novas alterações aguardando gravação.':'Rascunho salvo no servidor às '+new Date().toLocaleTimeString('pt-BR'));
      return true;
    }catch(e){if(e.http&&e.http<500)pendingSave=null;if(e.http===409)saveBlocked=true;saveMessage('Não foi possível confirmar o salvamento. '+e.message);return false;}finally{autoFlight=null;if(current===active){visibility();if(dirty)scheduleSave(30000);}}})();
    return autoFlight;
  }
  const states={rascunho:'Rascunho recebido pelo sistema',enviado:'Enviado para revisão',devolvido:'Devolvido para correção',aprovado:'Aprovado; aguarda aplicação',oficializado:'Aplicado aos registros oficiais'};
  function uuid(){if(crypto.randomUUID)return crypto.randomUUID();const b=crypto.getRandomValues(new Uint8Array(16));b[6]=(b[6]&15)|64;b[8]=(b[8]&63)|128;const h=[...b].map(v=>v.toString(16).padStart(2,'0')).join('');return h.slice(0,8)+'-'+h.slice(8,12)+'-'+h.slice(12,16)+'-'+h.slice(16,20)+'-'+h.slice(20);}
  function timestamp(){const now=new Date(),offset=-now.getTimezoneOffset(),local=new Date(now.getTime()+offset*60000).toISOString().slice(0,-1);return local+(offset>=0?'+':'-')+String(Math.floor(Math.abs(offset)/60)).padStart(2,'0')+':'+String(Math.abs(offset)%60).padStart(2,'0');}
  function status(text,error=false){$('fk-status').textContent=text;$('fk-status').className=error?'rgc-error':'rgc-notice';}
  async function api(path,method='GET',body){
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),45000);
    try{
      let csrf=getCsrf();
      if(method!=='GET'){
        const session=await api(base+'/sessao');
        if(session.usuario!==owner)throw Error('A conta mudou. Preserve o trabalho e reabra esta área na conta correta.');
        $('fk-login').hidden=true;
        csrf=session.csrf;
      }
      const r=await fetch(path,{method,credentials:'same-origin',cache:'no-store',redirect:'manual',signal:abort.signal,
        headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:body===undefined?undefined:JSON.stringify(body)});
      if(r.type==='opaqueredirect'||r.status===401){$('fk-login').hidden=false;throw Error('Entre novamente na mesma conta usando outra aba e volte a esta tela para salvar. O conteúdo ainda não salvo permanece somente aqui.');}
      const data=await r.json().catch(()=>({}));if(!r.ok){const error=Error(data.erro||'O sistema não confirmou a operação. Confira seus envios antes de repetir.');error.http=r.status;throw error;}return data;
    }catch(e){if(e.name==='AbortError'||e instanceof TypeError)throw Error('Conexão indisponível. Mantenha a tela aberta; confira os envios quando a conexão voltar.');throw e;}
    finally{clearTimeout(timer);}
  }
  function evaluate(t,values,value='',choice={}){
    const op=t[0];if(op==='literal')return t[1];if(op==='ref')return t[1]==='.'?value:(choice[t[1]]??values[t[1]]??'');
    if(op==='and')return Boolean(evaluate(t[1],values,value,choice))&&Boolean(evaluate(t[2],values,value,choice));
    if(op==='or')return Boolean(evaluate(t[1],values,value,choice))||Boolean(evaluate(t[2],values,value,choice));
    if(op==='call'){
      const a=t[2].map(n=>evaluate(n,values,value,choice));
      switch(t[1]){case'true':return true;case'false':return false;case'not':return !a[0];case'selected':return String(a[0]).split(/\s+/).includes(String(a[1]));case'count-selected':return String(a[0]).trim()?String(a[0]).trim().split(/\s+/).length:0;case'string-length':return String(a[0]).length;case'normalize-space':return String(a[0]).trim().replace(/\s+/g,' ');case'date':case'string':return String(a[0]);case'number':return Number(a[0]);case'if':return a[0]?a[1]:a[2];}
    }
    if(op==='compare'){
      let a=evaluate(t[2],values,value,choice),b=evaluate(t[3],values,value,choice);
      if(t[1]==='=')return String(a)===String(b);if(t[1]==='!=')return String(a)!==String(b);
      if(typeof a==='number'||typeof b==='number'){if(a===''||b==='')return false;a=Number(a);b=Number(b);}
      switch(t[1]){case'>':return a>b;case'<':return a<b;case'>=':return a>=b;case'<=':return a<=b;}
    }throw Error('Regra do formulário não reconhecida. Avise o responsável.');
  }
  function all(nodes){return nodes.flatMap(n=>[n,...all(n.children||[])]);}
  function ctx(row){return Object.fromEntries(Object.entries({...current.payload.values,...row}).map(([p,v])=>[p.split('/').at(-1),v]));}
  function container(node,group='',index=-1){return `data-path="${esc(node.path)}" data-group="${esc(group)}" data-index="${index}"`;}
  function data(group,index){return group?current.payload.repeats[group][index]:current.payload.values;}
  function geoPair(n){
    const parent=n.path.split('/').slice(0,-1).join('/'),peers=all(schema.nodes).filter(x=>x.path.split('/').slice(0,-1).join('/')===parent);
    const q=peers.find(x=>x.geo==='quarteirao'&&x.kind==='select_one'&&JSON.stringify(x.filter).toLowerCase().includes('logradouro'));
    return q?{q,street:peers.find(x=>x.geo==='logradouro'),loc:peers.find(x=>x.geo==='localidade')}:null;
  }
  function available(n,option,context){
    const pair=geoPair(n);
    if(pair&&n===pair.q&&pair.street){const streets=pair.street.options.filter(o=>evaluate(pair.street.filter,context,'',o.attrs)).map(o=>o.value);return streets.includes(option.attrs.logradouro);}
    if(pair&&n===pair.street){const code=context[pair.q.name],chosen=pair.q.options.find(o=>o.value===String(code));if(chosen&&option.value!==chosen.attrs.logradouro)return false;}
    return evaluate(n.filter,context,'',option.attrs);
  }
  function draw(nodes,group='',index=-1){
    const ordered=[...nodes];
    const street=ordered.findIndex(n=>n.geo==='logradouro'),block=ordered.findIndex(n=>n.geo==='quarteirao'&&!n.name.toLowerCase().includes('outro'));
    if(street>=0&&block>street){const [n]=ordered.splice(block,1);ordered.splice(street,0,n);}
    return '<div class="fk-fields">'+ordered.map(n=>{
      const attrs=container(n,group,index),raw=data(group,index),value=raw[n.path]??'';
      if(n.kind==='begin_group')return `<fieldset class="fk-section fk-node" ${attrs}><legend>${esc(n.label)}</legend>${draw(n.children,group,index)}</fieldset>`;
      if(n.kind==='begin_repeat'){
        const rows=current.payload.repeats[n.path]||[];
        return `<fieldset class="fk-section fk-node" ${attrs}><legend>${esc(n.label)}</legend>${rows.map((row,i)=>`<div class="fk-row"><strong>Registro ${i+1}</strong><button type="button" class="btn btn-ghost" data-remove="${esc(n.path)}" data-row="${i}">Remover registro ${i+1}</button>${draw(n.children,n.path,i)}</div>`).join('')}<button type="button" class="btn btn-outline" data-add="${esc(n.path)}">Adicionar registro</button></fieldset>`;
      }
      const id='fk-field-'+(++seq),binding=attrs+' data-field="1"';let control;
      if(n.kind==='select_multiple')control=`<div id="${id}" role="group" aria-labelledby="${id}-label" class="fk-multiple ${n.equipe?'fk-team':''}" ${binding}>${n.options.map(o=>`<label data-option="${esc(o.value)}"><input type="checkbox" value="${esc(o.value)}" ${String(value).split(/\s+/).includes(o.value)?'checked':''}><span>${esc(o.label)}${fixed(n)===o.value?' · responsável':''}</span></label>`).join('')}</div>`;
      else if(n.kind==='select_one')control=`<select id="${id}" ${binding}><option value="">Selecione…</option>${n.options.map(o=>`<option value="${esc(o.value)}" ${String(value)===o.value?'selected':''}>${esc(o.label)}</option>`).join('')}</select>`;
      else if(n.kind==='text'&&/observ|descri|coment/i.test(n.name))control=`<textarea id="${id}" ${binding} maxlength="4000" rows="3">${esc(value)}</textarea>`;
      else{
        const suggested=n.geo&&['quarteirao','logradouro'].includes(n.geo)&&!n.kind.startsWith('select_');
        const type=suggested?'text':n.kind==='date'?'date':n.kind==='time'?'time':n.kind==='integer'||n.kind==='decimal'?'number':'text';
        control=(suggested?`<select class="fk-pick" data-suggestion="${id}" aria-label="Sugestões de ${esc(n.label)}" hidden><option value="">Selecione uma sugestão ou digite abaixo</option></select>`:'')+`<input id="${id}" ${binding} type="${type}" ${type==='number'?`min="0" step="${n.kind==='integer'?'1':'any'}"`:''} value="${esc(value)}" ${suggested?`data-geo="${n.geo}" inputmode="${n.geo==='quarteirao'?'numeric':'text'}"`:''} maxlength="4000" autocomplete="off">${suggested?'<small>Escolha uma sugestão ou digite. Se não houver opções, a digitação continua disponível.</small>':''}`;
      }
      return `<div class="fk-field fk-node" ${attrs}><label id="${id}-label" for="${id}">${esc(n.label)} <span class="fk-required" aria-label="obrigatório" hidden>*</span></label>${control}${n.hint?`<small>${esc(n.hint)}</small>`:''}${review?`<label class="fk-correction-label">Orientação de correção<textarea data-correction="${esc(n.path)}" maxlength="500" rows="2">${esc((current.payload.correcoes||[]).find(c=>c.campo===n.path)?.mensagem||'')}</textarea></label>`:(current.payload.correcoes||[]).filter(c=>c.campo===n.path).map(c=>`<p class="fk-correction">Correção solicitada: ${esc(c.mensagem)}</p>`).join('')}</div>`;
    }).join('')+'</div>';
  }
  function visibility(){
    const map=new Map(all(schema.nodes).map(n=>[n.path,n]));
    $('fk-campos').querySelectorAll('.fk-node').forEach(el=>{
      const n=map.get(el.dataset.path),row=data(el.dataset.group,Number(el.dataset.index)),context=ctx(row);
      el.hidden=n.kind==='hidden'||!evaluate(n.relevant,context);
      const required=el.querySelector(':scope > label .fk-required');if(required)required.hidden=!evaluate(n.required,context,row[n.path]??'');
      if(n.kind.startsWith('select_')){
        const control=el.querySelector('[data-field]');const options=new Map(n.options.map(o=>[o.value,o]));
        control.querySelectorAll(n.kind==='select_one'?'option[value]':'[data-option]').forEach(opt=>{
          const code=opt.value??opt.dataset.option;if(!code)return;const option=options.get(code);
          const visible=option&&available(n,option,context);
          opt.hidden=!visible;if(n.kind==='select_one')opt.disabled=!visible;
        });
      }
    });
    const locked=review?!['enviado','aprovado'].includes(current.status):['enviado','aprovado','oficializado'].includes(current.status);
    $('fk-novo').disabled=busy;$('fk-listar').disabled=busy;
    $('fk-campos').querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=locked||busy);
    $('fk-acoes').querySelectorAll('button').forEach(el=>{
      const a=el.dataset.action;el.disabled=busy||locked||review&&(a==='aplicar'?current.status!=='aprovado':!['enviado','aprovado'].includes(current.status));
    });
    $('fk-campos').querySelectorAll('[data-field]').forEach(control=>{const n=map.get(control.dataset.path),code=fixed(n);if(code){if(n.kind==='select_one')control.disabled=true;else for(const input of control.querySelectorAll('input'))if(input.value===code){input.checked=true;input.disabled=true;}}});
    const sender=current.autor||current.payload.responsavel||schema.responsavel;
    $('fk-responsavel').textContent='Responsável pelo envio: '+(sender?.nome||'Conta autenticada')+(current.payload.responsavel?.agente?' · Agente: '+current.payload.responsavel.agente:'')+(current.autor?.enviado_em?' · Enviado em '+current.autor.enviado_em:'')+(!review&&!sender?.id_agente&&!current.autor?' · Falta vincular a conta a um agente. Salve como rascunho e peça ao gestor para conferir o vínculo.':'');
    const flow=current.payload.acompanhamento||{},confirmed=flow.retorno_evento;
    for(const id of ['fk-retorno-data','fk-retorno-hora','fk-retorno-nota'])$(id).disabled=locked||busy||Boolean(confirmed);
    $('fk-retorno-situacao').textContent=confirmed?'Retorno confirmado na agenda — evento #'+confirmed:'';
    if($('fk-confirmar-retorno'))$('fk-confirmar-retorno').disabled=busy||!['aprovado','oficializado'].includes(current.status)||!flow.retorno||Boolean(confirmed);
    $('fk-desvincular').hidden=!flow.agenda||locked||busy;
    $('fk-agenda-vinculo').textContent=flow.agenda?'Atividade vinculada à agenda: #'+flow.agenda+' · '+flow.ocorrencia:'';
    $('fk-situacao').textContent=(states[current.status]||'Novo preenchimento')+(current.motivo?' · '+current.motivo:'');
  }
  function render(){anchor();const notes=current.payload.correcoes||[];$('fk-correcao-resumo').hidden=!notes.length;$('fk-correcao-resumo').innerHTML='<strong>Orientações da revisão</strong>'+notes.map(c=>`<p>${esc(all(schema.nodes).find(n=>n.path===c.campo)?.label||c.campo)}: ${esc(c.mensagem)}</p>`).join('');const proposal=current.payload.acompanhamento?.retorno||{};$('fk-retorno-data').value=proposal.data||'';$('fk-retorno-hora').value=proposal.hora||'';$('fk-retorno-nota').value=proposal.observacao||'';seq=0;$('fk-campos').innerHTML=draw(schema.nodes);$('fk-editor').hidden=false;visibility();scheduleGeo();}
  function initial(nodes,flat){for(const n of nodes){if(n.kind==='begin_repeat')continue;if(n.children)initial(n.children,flat);else if(n.default!==''&&n.default!==undefined&&!String(n.default).includes('${'))flat[n.path]=String(n.default);}}
  async function fresh(){
    if(!schema||busy||autoFlight)return;
    if(dirty&&!await confirmacaoDupla('Descartar as alterações que ainda não foram salvas?'))return;
    clearTimeout(autoTimer);pendingSave=null;saveBlocked=false;saveMessage('');
    current={uuid:uuid(),status:'novo',captura:{versao:1,revisao:0,dispositivo:uuid()},payload:{versao:schema.versao,values:{},repeats:{},responsavel:schema.responsavel,inicio:timestamp()}};
    const planned=new URL(location.href).searchParams;
    if(planned.has('agenda'))current.payload.acompanhamento={agenda:Number(planned.get('agenda')),ocorrencia:planned.get('ocorrencia')||''};
    initial(schema.nodes,current.payload.values);dirty=false;render();status('Preencha e salve o rascunho ou envie para revisão.');
    history.replaceState(null,'',location.pathname);
  }
  async function list(show=true){
    const request=++listRequest;
    const r=await api(base+(review?'?status='+encodeURIComponent($('fk-filtro').value):'?proprios=1'));
    if(request!==listRequest)return;
    $('fk-lista').innerHTML=r.itens.map(i=>`<article class="fk-list-item"><strong>#${i.id} · ${esc(states[i.status]||i.status)}</strong><p>${esc(i.autor||'')} · ${esc(i.criado_em)}</p><button class="btn btn-outline" type="button" data-open="${i.id}">Abrir</button></article>`).join('')||'<p>Nenhum envio encontrado.</p>';
    $('fk-lista').hidden=!show;
  }
  async function open(id){
    if(dirty&&!await confirmacaoDupla('Abrir outro envio e descartar as alterações ainda não salvas?'))return;
    if(autoFlight)await autoFlight;clearTimeout(autoTimer);pendingSave=null;
    saveBlocked=false;current=await api(base+'/'+id);if(!review&&['rascunho','devolvido'].includes(current.status)&&!current.payload.responsavel)current.payload.responsavel=schema.responsavel;dirty=false;render();history.replaceState(null,'',location.pathname+'?envio='+id);
    status('Envio carregado do servidor.');
  }
  async function action(name){
    if(saveBlocked){status('Reabra o envio recebido em Meus envios para conferir a situação antes de continuar.',true);return;}
    if(busy||!current)return;clearTimeout(autoTimer);if(autoFlight&&!await autoFlight)return;if(pendingSave&&!await autoSave())return;busy=true;visibility();
    try{
      if(name==='rascunho'||name==='enviado'||name==='proxima'){
        const next=name==='proxima';if(next)name='enviado';
        if(name==='enviado'&&!await confirmacaoDupla('Enviar para revisão? O gestor precisa aprovar e aplicar antes de alterar os registros oficiais.'))return;
        const revision=(current.captura.revisao||0)+1;
        current.payload.fim=timestamp();
        const receipt=await api(base,'POST',{usuario:owner,uuid:current.uuid,payload:current.payload,status:name,
          captura:{versao:1,revisao:revision,dispositivo:current.captura.dispositivo}});
        if(receipt.revisao!==revision)throw Error('Revisão não confirmada. Preserve a tela e confira os envios.');
        dirty=false;current.captura.revisao=revision;await open(receipt.id);if(next){$('fk-proxima').hidden=false;$('fk-proxima').scrollIntoView({behavior:'smooth'});}status(name==='rascunho'?'Rascunho salvo no servidor.':'Recebido para revisão; ainda não aplicado aos registros oficiais.');
      }else{
        if(!current.id)throw Error('Abra um envio recebido antes de revisar.');
        if(!await confirmacaoDupla(name==='aplicar'?'Aplicar este envio aprovado aos registros oficiais?':'Confirmar esta decisão de revisão?'))return;
        if(name==='retorno')await api(base+'/'+current.id+'/confirmar-retorno','POST',{});
        else if(name==='aplicar')await api(base+'/'+current.id+'/oficializar','POST',{});
        else{
          const motivo=name==='devolver'?prompt('Motivo da devolução:'):null;
          if(name==='devolver'&&!motivo?.trim())return;
          await api(base+'/'+current.id+'/revisar','POST',{payload:current.payload,etag:current.etag,correcoes:[...$('fk-campos').querySelectorAll('[data-correction]')].filter(el=>el.value.trim()).map(el=>({campo:el.dataset.correction,mensagem:el.value.trim()})).filter((c,i,arr)=>arr.findIndex(x=>x.campo===c.campo)===i),decisao:name==='aprovar'?'aprovado':'devolvido',motivo});
        }
        dirty=false;await open(current.id);status(name==='aplicar'?'Aplicado com confirmação do sistema.':'Revisão registrada.');
      }
      await list();
    }catch(e){if(['rascunho','enviado','proxima'].includes(name)&&(!e.http||e.http>=500||e.http===409))saveBlocked=true;status(e.message,true);}finally{busy=false;visibility();if(dirty)scheduleSave();}
  }
  function scheduleGeo(){clearTimeout(geoTimer);geoRequest++;for(const el of $('fk-campos').querySelectorAll('[data-suggestion]'))el.hidden=true;geoTimer=setTimeout(()=>loadGeo().catch(()=>{}),200);}
  async function loadGeo(){
    if(!current)return;const token=geoRequest;
    for(const input of $('fk-campos').querySelectorAll('input[data-geo]')){
      if(input.closest('[hidden]'))continue;
      const n=all(schema.nodes).find(n=>n.path===input.dataset.path),parent=n.path.split('/').slice(0,-1).join('/');
      const peers=all(schema.nodes).filter(x=>x.path.split('/').slice(0,-1).join('/')===parent);
      const loc=peers.find(x=>x.geo==='localidade');if(!loc)continue;
      const raw=data(input.dataset.group,Number(input.dataset.index)),code=raw[loc.path]||'';
      const locality=loc.options?.find(o=>o.value===String(code))?.label||code;
      const q=peers.find(x=>x.geo==='quarteirao'&& !x.name.toLowerCase().includes('outro'));
      const other=peers.find(x=>x.geo==='quarteirao'&&x.name.toLowerCase().includes('outro'));
      const block=q&&String(raw[q.path])==='outros'&&other?raw[other.path]||'':q?raw[q.path]||'':'';
      const key=JSON.stringify([locality,block]);
      let refs=geoCache.get(key);if(!refs){refs=await api(base+'/referencias?localidade='+encodeURIComponent(locality)+'&quarteirao='+encodeURIComponent(block));geoCache.set(key,refs);}
      if(token!==geoRequest)return;
      const pick=input.parentElement.querySelector('[data-suggestion]'),options=refs[input.dataset.geo==='quarteirao'?'quarteiroes':'logradouros']||[];
      pick.innerHTML='<option value="">Selecione uma sugestão ou digite abaixo</option>'+options.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');pick.hidden=!options.length;
    }
  }
  root.addEventListener('change',event=>{const pick=event.target.closest('[data-suggestion]');if(!pick||!pick.value||busy)return;const input=$(pick.dataset.suggestion);input.value=pick.value;input.dispatchEvent(new Event('input',{bubbles:true}));pick.value='';});
  root.addEventListener('input',event=>{
    if(['fk-retorno-data','fk-retorno-hora','fk-retorno-nota'].includes(event.target.id)&&current){
      current.payload.acompanhamento??={};const day=$('fk-retorno-data').value;
      current.payload.acompanhamento.retorno=day?{data:day,hora:$('fk-retorno-hora').value,observacao:$('fk-retorno-nota').value}:null;
      dirty=true;editSerial++;saveMessage('Alterações ainda não salvas.');scheduleSave();return;
    }
    if(event.target.hasAttribute('data-correction')){dirty=true;editSerial++;return;}
    const control=event.target.closest('[data-field]');if(!control||!current)return;
    const raw=data(control.dataset.group,Number(control.dataset.index));
    const changed=all(schema.nodes).find(n=>n.path===control.dataset.path);
    const previous=raw[control.dataset.path];
    raw[control.dataset.path]=control.classList.contains('fk-multiple')?[...control.querySelectorAll('input:checked')].map(el=>el.value).join(' '):control.value;
    if(changed?.geo&&previous!==raw[changed.path]){
      const parent=changed.path.split('/').slice(0,-1).join('/');
      for(const n of all(schema.nodes)){
        if(n.path===changed.path||n.path.split('/').slice(0,-1).join('/')!==parent)continue;
        const reset=changed.geo==='localidade'&&['quarteirao','logradouro'].includes(n.geo)||changed.geo==='quarteirao'&&n.geo==='logradouro'||changed.geo==='logradouro'&&n.geo==='quarteirao'&&JSON.stringify(n.filter).toLowerCase().includes('logradouro');
        if(reset){raw[n.path]='';for(const el of $('fk-campos').querySelectorAll('[data-field]'))if(el.dataset.path===n.path&&el.dataset.group===control.dataset.group)el.value='';}
      }
    }
    if(changed?.geo==='quarteirao'){const pair=geoPair(changed),chosen=pair?.q.options.find(o=>o.value===String(raw[changed.path]));if(chosen&&pair.street){raw[pair.street.path]=chosen.attrs.logradouro;for(const el of $('fk-campos').querySelectorAll('[data-field]'))if(el.dataset.path===pair.street.path&&el.dataset.group===control.dataset.group)el.value=chosen.attrs.logradouro;}}
    anchor();dirty=true;editSerial++;saveMessage('Alterações ainda não salvas.');status('Há alterações ainda não salvas.');visibility();scheduleGeo();scheduleSave();
  });
  root.addEventListener('click',event=>{
    const b=event.target.closest('button');if(!b||busy)return;
    Promise.resolve().then(async()=>{
      if(b.dataset.action)return action(b.dataset.action);
      if(b.dataset.open)return open(Number(b.dataset.open));
      if(b.dataset.add){const rows=current.payload.repeats[b.dataset.add]||=[];if(rows.length>=100)throw Error('Limite de 100 registros neste grupo.');rows.push({});dirty=true;editSerial++;render();scheduleSave();}
      if(b.dataset.remove){if(await confirmacaoDupla('Remover este registro do preenchimento?')){current.payload.repeats[b.dataset.remove].splice(Number(b.dataset.row),1);dirty=true;editSerial++;render();scheduleSave();}}
    }).catch(e=>status(e.message,true));
  });
  $('fk-novo').hidden=review;$('fk-novo').addEventListener('click',()=>fresh().catch(e=>status(e.message,true)));$('fk-listar').addEventListener('click',()=>list().catch(e=>status(e.message,true)));
  $('fk-filtro')?.addEventListener('change',()=>list().catch(e=>status(e.message,true)));
  $('fk-desvincular').addEventListener('click',()=>{delete current.payload.acompanhamento.agenda;delete current.payload.acompanhamento.ocorrencia;dirty=true;editSerial++;visibility();scheduleSave();});
  $('fk-criar-proxima')?.addEventListener('click',async()=>{const prior=structuredClone(current.payload.values);await fresh();for(const n of all(schema.nodes)){if(n.equipe&&$('fk-reusar-equipe').checked||n.geo==='localidade'&&$('fk-reusar-local').checked||n.kind==='date'&&['Data','Digite_a_data'].includes(n.name)&&$('fk-reusar-data').checked){if(prior[n.path]!==undefined)current.payload.values[n.path]=prior[n.path];}}$('fk-proxima').hidden=true;dirty=true;editSerial++;render();scheduleSave();$('fk-app').scrollIntoView({behavior:'smooth'});});
  window.addEventListener('online',()=>scheduleSave(500));
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
  window.addEventListener('offline',()=>status('Sem conexão. Mantenha esta tela aberta; estes formulários novos ainda não funcionam offline.',true));
  (async()=>{schema=await api(base+'/esquema');await list(review);$('fk-listar').disabled=false;const id=Number(new URL(location.href).searchParams.get('envio'));if(id)await open(id);else if(!review)await fresh();else status('Abra um envio para revisar.');})().catch(e=>status(e.message,true));
})();
