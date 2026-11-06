/* Piloto online. Nenhum conteúdo pessoal é gravado no armazenamento offline. */
(() => {
  'use strict';
  const root=document.getElementById('fk-app');if(!root)return;
  const $=id=>document.getElementById(id),tipo=root.dataset.tipo,owner=Number(root.dataset.usuario),review=root.dataset.revisao==='1';
  const base='/api/formularios/kobo/'+encodeURIComponent(tipo);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let schema,current,busy=false,dirty=false,seq=0,listRequest=0;
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
      const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(data.erro||'O sistema não confirmou a operação. Confira seus envios antes de repetir.');return data;
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
  function draw(nodes,group='',index=-1){
    return '<div class="fk-fields">'+nodes.map(n=>{
      const attrs=container(n,group,index),raw=data(group,index),value=raw[n.path]??'';
      if(n.kind==='begin_group')return `<fieldset class="fk-section fk-node" ${attrs}><legend>${esc(n.label)}</legend>${draw(n.children,group,index)}</fieldset>`;
      if(n.kind==='begin_repeat'){
        const rows=current.payload.repeats[n.path]||[];
        return `<fieldset class="fk-section fk-node" ${attrs}><legend>${esc(n.label)}</legend>${rows.map((row,i)=>`<div class="fk-row"><strong>Registro ${i+1}</strong><button type="button" class="btn btn-ghost" data-remove="${esc(n.path)}" data-row="${i}">Remover registro ${i+1}</button>${draw(n.children,n.path,i)}</div>`).join('')}<button type="button" class="btn btn-outline" data-add="${esc(n.path)}">Adicionar registro</button></fieldset>`;
      }
      const id='fk-field-'+(++seq),binding=attrs+' data-field="1"';let control;
      if(n.kind==='select_multiple')control=`<div id="${id}" role="group" aria-labelledby="${id}-label" class="fk-multiple" ${binding}>${n.options.map(o=>`<label data-option="${esc(o.value)}"><input type="checkbox" value="${esc(o.value)}" ${String(value).split(/\s+/).includes(o.value)?'checked':''}>${esc(o.label)}</label>`).join('')}</div>`;
      else if(n.kind==='select_one')control=`<select id="${id}" ${binding}><option value="">Selecione…</option>${n.options.map(o=>`<option value="${esc(o.value)}" ${String(value)===o.value?'selected':''}>${esc(o.label)}</option>`).join('')}</select>`;
      else if(n.kind==='text'&&/observ|descri|coment/i.test(n.name))control=`<textarea id="${id}" ${binding} maxlength="4000" rows="3">${esc(value)}</textarea>`;
      else{
        const type=n.kind==='date'?'date':n.kind==='time'?'time':n.kind==='integer'||n.kind==='decimal'?'number':'text';
        control=`<input id="${id}" ${binding} type="${type}" ${type==='number'?`min="0" step="${n.kind==='integer'?'1':'any'}"`:''} value="${esc(value)}" maxlength="4000" autocomplete="off">`;
      }
      return `<div class="fk-field fk-node" ${attrs}><label id="${id}-label" for="${id}">${esc(n.label)} <span class="fk-required" aria-label="obrigatório" hidden>*</span></label>${control}${n.hint?`<small>${esc(n.hint)}</small>`:''}</div>`;
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
          const visible=option&&evaluate(n.filter,context,'',option.attrs);
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
    $('fk-situacao').textContent=(states[current.status]||'Novo preenchimento')+(current.motivo?' · '+current.motivo:'');
  }
  function render(){seq=0;$('fk-campos').innerHTML=draw(schema.nodes);$('fk-editor').hidden=false;visibility();}
  function initial(nodes,flat){for(const n of nodes){if(n.kind==='begin_repeat')continue;if(n.children)initial(n.children,flat);else if(n.default!==''&&n.default!==undefined&&!String(n.default).includes('${'))flat[n.path]=String(n.default);}}
  async function fresh(){
    if(!schema||busy)return;
    if(dirty&&!await confirmacaoDupla('Descartar as alterações que ainda não foram salvas?'))return;
    current={uuid:uuid(),status:'novo',captura:{versao:1,revisao:0,dispositivo:uuid()},payload:{versao:schema.versao,values:{},repeats:{},inicio:timestamp()}};
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
    current=await api(base+'/'+id);dirty=false;render();history.replaceState(null,'',location.pathname+'?envio='+id);
    status('Envio carregado do servidor.');
  }
  async function action(name){
    if(busy||!current)return;busy=true;visibility();
    try{
      if(name==='rascunho'||name==='enviado'){
        if(name==='enviado'&&!await confirmacaoDupla('Enviar para revisão? O gestor precisa aprovar e aplicar antes de alterar os registros oficiais.'))return;
        const revision=(current.captura.revisao||0)+1;
        current.payload.fim=timestamp();
        const receipt=await api(base,'POST',{usuario:owner,uuid:current.uuid,payload:current.payload,status:name,
          captura:{versao:1,revisao:revision,dispositivo:current.captura.dispositivo}});
        if(receipt.revisao!==revision)throw Error('Revisão não confirmada. Preserve a tela e confira os envios.');
        dirty=false;current.captura.revisao=revision;await open(receipt.id);status(name==='rascunho'?'Rascunho salvo no servidor.':'Recebido para revisão; ainda não aplicado aos registros oficiais.');
      }else{
        if(!current.id)throw Error('Abra um envio recebido antes de revisar.');
        if(!await confirmacaoDupla(name==='aplicar'?'Aplicar este envio aprovado aos registros oficiais?':'Confirmar esta decisão de revisão?'))return;
        if(name==='aplicar')await api(base+'/'+current.id+'/oficializar','POST',{});
        else{
          const motivo=name==='devolver'?prompt('Motivo da devolução:'):null;
          if(name==='devolver'&&!motivo?.trim())return;
          await api(base+'/'+current.id+'/revisar','POST',{payload:current.payload,etag:current.etag,decisao:name==='aprovar'?'aprovado':'devolvido',motivo});
        }
        dirty=false;await open(current.id);status(name==='aplicar'?'Aplicado com confirmação do sistema.':'Revisão registrada.');
      }
      await list();
    }catch(e){status(e.message,true);}finally{busy=false;visibility();}
  }
  root.addEventListener('input',event=>{
    const control=event.target.closest('[data-field]');if(!control||!current)return;
    const raw=data(control.dataset.group,Number(control.dataset.index));
    raw[control.dataset.path]=control.classList.contains('fk-multiple')?[...control.querySelectorAll('input:checked')].map(el=>el.value).join(' '):control.value;
    dirty=true;status('Há alterações ainda não salvas.');visibility();
  });
  root.addEventListener('click',event=>{
    const b=event.target.closest('button');if(!b||busy)return;
    Promise.resolve().then(async()=>{
      if(b.dataset.action)return action(b.dataset.action);
      if(b.dataset.open)return open(Number(b.dataset.open));
      if(b.dataset.add){const rows=current.payload.repeats[b.dataset.add]||=[];if(rows.length>=100)throw Error('Limite de 100 registros neste grupo.');rows.push({});dirty=true;render();}
      if(b.dataset.remove){if(await confirmacaoDupla('Remover este registro do preenchimento?')){current.payload.repeats[b.dataset.remove].splice(Number(b.dataset.row),1);dirty=true;render();}}
    }).catch(e=>status(e.message,true));
  });
  $('fk-novo').hidden=review;$('fk-novo').addEventListener('click',()=>fresh().catch(e=>status(e.message,true)));$('fk-listar').addEventListener('click',()=>list().catch(e=>status(e.message,true)));
  $('fk-filtro')?.addEventListener('change',()=>list().catch(e=>status(e.message,true)));
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
  window.addEventListener('offline',()=>status('Sem conexão. Mantenha esta tela aberta; estes formulários novos ainda não funcionam offline.',true));
  (async()=>{schema=await api(base+'/esquema');await list(review);$('fk-listar').disabled=false;const id=Number(new URL(location.href).searchParams.get('envio'));if(id)await open(id);else if(!review)await fresh();else status('Abra um envio para revisar.');})().catch(e=>status(e.message,true));
})();
