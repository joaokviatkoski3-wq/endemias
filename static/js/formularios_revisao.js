(() => {
  const fila=document.getElementById('fila-revisao');
  const dialog=document.getElementById('fila-dialog');
  const frame=document.getElementById('fila-editor');
  const status=document.getElementById('fila-status');
  let changed=false, opener;
  fila.addEventListener('click',async event=>{
    const detail=event.target.closest('.fila-detalhe');
    if(detail && !event.ctrlKey && !event.metaKey){
      event.preventDefault();
      const url=new URL(detail.href,location.origin);
      url.searchParams.set('embutido','1');
      const id=detail.closest('.fila-card').dataset.envio;
      document.getElementById('fila-dialog-titulo').textContent='Detalhes do envio #'+id;
      opener=detail;frame.src=url.href;dialog.showModal();return;
    }
    const button=event.target.closest('[data-aceitar]');
    if(!button || button.disabled)return;
    const message=button.dataset.rg==='1'
      ?'Aceitar esta atualização? O registro substituirá os imóveis cadastrados neste quarteirão.'
      :'Aceitar este envio com os dados apresentados? Confira se a mesma atividade já entrou pelo Kobo.';
    if(!await confirmacaoDupla(message))return;
    button.disabled=true;
    try{
      const response=await fetch(button.dataset.aceitar,{method:'POST',
        headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
        body:JSON.stringify({etag:button.dataset.etag})});
      const result=await response.json().catch(()=>({}));
      if(!response.ok||!result.ok)throw Error(result.erro||'Não foi possível aceitar o envio.');
      const card=button.closest('.fila-card');
      const pending=new URLSearchParams(location.search).get('status');
      if(!pending||pending==='pendentes'||pending==='enviado')card.remove();
      else {
        const situation=card.querySelector('.fila-situacao');
        situation.textContent='Aceito';
        situation.dataset.situacao='aprovado';
        button.remove();
      }
      status.textContent='Envio aceito.';
    }catch(error){status.textContent=error.message;toast(error.message,'error');button.disabled=false;}
  });
  document.getElementById('fila-fechar').onclick=()=>dialog.close();
  window.addEventListener('message',event=>{
    if(event.origin===location.origin&&event.source===frame.contentWindow&&event.data?.type==='revisao-alterada')changed=true;
  });
  dialog.addEventListener('close',()=>{
    frame.removeAttribute('src');
    if(changed)location.reload();
    else opener?.focus();
  });
})();
