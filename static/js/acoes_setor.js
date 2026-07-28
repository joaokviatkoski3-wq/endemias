(function(){
  const $ = id => document.getElementById(id);
  const camposTexto = [
    'caso', 'localidade', 'local', 'endereco', 'tema', 'contexto',
    'resultados', 'parceiros', 'coordenadas', 'observacoes'
  ];
  const fmtNumero = new Intl.NumberFormat('pt-BR');
  const fmtMes = new Intl.DateTimeFormat('pt-BR', {month:'short', timeZone:'UTC'});
  let registros = [];
  let registroAberto = null;
  let galeriaAnexosCarregada = false;
  let inventarioHistorico = null;
  let importacaoAtiva = null;
  const anexosPorAcao = {};
  const dialog = $('acao-dialog');

  function esc(valor){
    return String(valor ?? '').replace(/[&<>"']/g, ch => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
    }[ch]));
  }

  function normalizar(valor){
    return String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function dataPartes(valor){
    const partes = String(valor || '').slice(0,10).split('-');
    if(partes.length !== 3) return {dia:'--', mes:'---', ano:''};
    const data = new Date(Date.UTC(Number(partes[0]), Number(partes[1])-1, Number(partes[2])));
    return {
      dia:String(Number(partes[2])).padStart(2,'0'),
      mes:fmtMes.format(data).replace('.',''),
      ano:partes[0],
    };
  }

  function dataBR(valor){
    const p=dataPartes(valor);
    return p.ano ? `${p.dia}/${String(new Date(`${valor}T00:00:00Z`).getUTCMonth()+1).padStart(2,'0')}/${p.ano}` : '-';
  }

  function dataHoraBR(valor){
    if(!valor)return '';
    const [data,hora=''] = String(valor).split('T');
    return `${dataBR(data)}${hora ? ` às ${hora.slice(0,5)}` : ''}`;
  }

  function tamanhoBR(bytes){
    const n=Number(bytes||0);
    if(n>=1024*1024)return `${(n/1024/1024).toFixed(1).replace('.',',')} MB`;
    if(n>=1024)return `${Math.round(n/1024)} KB`;
    return `${n} B`;
  }

  function horaRange(r){
    if(r.hora_inicio&&r.hora_fim)return `${r.hora_inicio} - ${r.hora_fim}`;
    return r.hora_inicio||r.hora_fim||'';
  }

  function checkedValues(name){
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(opt=>opt.value);
  }

  function setCheckedValues(name,values){
    const selecionados=new Set((values||[]).map(String));
    document.querySelectorAll(`input[name="${name}"]`).forEach(opt=>{
      opt.checked=selecionados.has(opt.value);
    });
  }

  function labelsLista(values){
    return (values||[]).filter(Boolean).join(', ');
  }

  function setParametro(params,id,nome){
    const valor=$(id)?.value?.trim();
    if(valor)params.set(nome,valor);
  }

  function params(){
    const p=new URLSearchParams();
    setParametro(p,'acoes-busca','busca');
    setParametro(p,'acoes-filtro-tipo','tipo');
    setParametro(p,'acoes-filtro-situacao','situacao');
    setParametro(p,'acoes-filtro-periodo','periodo');
    setParametro(p,'acoes-filtro-localidade','localidade');
    setParametro(p,'acoes-filtro-caso','caso');
    setParametro(p,'acoes-filtro-agente','id_agente');
    setParametro(p,'acoes-data-inicio','data_inicio');
    setParametro(p,'acoes-data-fim','data_fim');
    return p.toString();
  }

  function paramsAnexos(){
    const p=new URLSearchParams();
    setParametro(p,'acoes-anexos-busca','busca');
    setParametro(p,'acoes-anexos-tipo-acao','tipo_acao');
    setParametro(p,'acoes-anexos-tipo-arquivo','tipo_arquivo');
    setParametro(p,'acoes-anexos-localidade','localidade');
    setParametro(p,'acoes-anexos-caso','caso');
    setParametro(p,'acoes-anexos-agente','id_agente');
    setParametro(p,'acoes-anexos-data-inicio','data_inicio');
    setParametro(p,'acoes-anexos-data-fim','data_fim');
    return p.toString();
  }

  async function api(url,opts={}){
    const resp=await fetch(url,opts);
    const data=await resp.json().catch(()=>({}));
    if(!resp.ok)throw new Error(data.erro||`Erro HTTP ${resp.status}`);
    return data;
  }

  function payload(){
    const educativa=$('acao-tipo').value==='educativa';
    const data={
      tipo:$('acao-tipo').value,
      situacao:$('acao-situacao').value,
      data:$('acao-data').value,
      data_fim:$('acao-data-fim').value,
      periodo:document.querySelector('input[name="acao-periodo"]:checked')?.value||'',
      hora_inicio:$('acao-hora-inicio').value,
      hora_fim:$('acao-hora-fim').value,
      publico_aproximado:$('acao-publico').value,
      tipo_atividade_realizada:educativa?checkedValues('acao-tipo-atividade-realizada'):[],
      publico_alvo:educativa?checkedValues('acao-publico-alvo'):[],
      recurso_utilizado:educativa?checkedValues('acao-recurso-utilizado'):[],
      agentes:checkedValues('acao-agente'),
    };
    camposTexto.forEach(campo=>{data[campo]=$(`acao-${campo}`).value.trim();});
    return data;
  }

  function limparCamposEducativos(){
    setCheckedValues('acao-tipo-atividade-realizada',[]);
    setCheckedValues('acao-publico-alvo',[]);
    setCheckedValues('acao-recurso-utilizado',[]);
  }

  function atualizarCamposEducativos(){
    const educativa=$('acao-tipo').value==='educativa';
    document.querySelectorAll('.acoes-educativa-only').forEach(el=>{
      el.hidden=!educativa;
      el.classList.toggle('acoes-educativa-hidden',!educativa);
    });
    if(!educativa)limparCamposEducativos();
  }

  function limparForm(){
    importacaoAtiva=null;
    $('acao-id').value='';
    $('acao-form-title').textContent='Novo registro';
    $('acao-form-contexto').textContent='Cadastro da atividade';
    $('acao-salvar').innerHTML='<img src="/static/icons/salvar.svg" alt="" class="icon-svg"> Salvar';
    $('acao-tipo').value='educativa';
    $('acao-situacao').value='realizada';
    $('acao-data').value=new Date().toISOString().slice(0,10);
    $('acao-data-fim').value='';
    setCheckedValues('acao-periodo',[]);
    $('acao-hora-inicio').value='';
    $('acao-hora-fim').value='';
    $('acao-publico').value='';
    if($('acao-anexos-restritos'))$('acao-anexos-restritos').checked=false;
    limparCamposEducativos();
    camposTexto.forEach(campo=>{$(`acao-${campo}`).value='';});
    $('acao-agentes-busca').value='';
    setCheckedValues('acao-agente',[]);
    filtrarAgentes();
    renderAnexos([]);
    atualizarEstadoAnexos();
    atualizarCamposEducativos();
  }

  function abrirFormularioNovo(){
    limparForm();
    if(!dialog.open)dialog.showModal();
    setTimeout(()=>$('acao-tipo').focus(),0);
  }

  function fecharFormulario(){
    if(dialog.open)dialog.close();
  }

  function preencherForm(r,abrir=true){
    importacaoAtiva=null;
    $('acao-id').value=r.id_acao;
    $('acao-form-title').textContent='Editar registro';
    $('acao-form-contexto').textContent=`Registro ${String(r.id_acao).padStart(6,'0')} · ${dataBR(r.data)}`;
    $('acao-salvar').innerHTML='<img src="/static/icons/salvar.svg" alt="" class="icon-svg"> Salvar';
    $('acao-tipo').value=r.tipo||'educativa';
    $('acao-situacao').value=r.situacao||'realizada';
    $('acao-data').value=r.data||'';
    $('acao-data-fim').value=r.data_fim||'';
    setCheckedValues('acao-periodo',r.periodo?[r.periodo]:[]);
    $('acao-hora-inicio').value=r.hora_inicio||'';
    $('acao-hora-fim').value=r.hora_fim||'';
    $('acao-publico').value=r.publico_aproximado??'';
    setCheckedValues('acao-tipo-atividade-realizada',r.tipo_atividade_realizada||[]);
    setCheckedValues('acao-publico-alvo',r.publico_alvo||[]);
    setCheckedValues('acao-recurso-utilizado',r.recurso_utilizado||[]);
    camposTexto.forEach(campo=>{$(`acao-${campo}`).value=r[campo]||'';});
    const ids=new Set((r.agentes||[]).map(a=>String(a.id_agente)));
    document.querySelectorAll('input[name="acao-agente"]').forEach(opt=>{opt.checked=ids.has(opt.value);});
    atualizarCamposEducativos();
    atualizarEstadoAnexos();
    carregarAnexos(r.id_acao).catch(e=>toast(`Erro ao carregar anexos: ${e.message}`,'error'));
    if(abrir&&!dialog.open)dialog.showModal();
    if(abrir)setTimeout(()=>$('acao-tipo').focus(),0);
  }

  function filtrarAgentes(){
    const termo=normalizar($('acao-agentes-busca').value);
    let visiveis=0;
    document.querySelectorAll('.acoes-agent-option').forEach(label=>{
      const mostrar=!termo||normalizar(label.textContent).includes(termo);
      label.classList.toggle('hidden',!mostrar);
      if(mostrar)visiveis+=1;
    });
    $('acao-agentes-vazio').classList.toggle('show',visiveis===0);
  }

  function anexoExtensao(anexo){
    const partes=String(anexo?.nome_original||'').split('.');
    return partes.length>1?partes.pop().slice(0,8).toLowerCase():'arquivo';
  }

  function anexoEhImagem(anexo){
    return String(anexo?.mime_type||'').startsWith('image/');
  }

  function anexoEhVideo(anexo){
    const mime=String(anexo?.mime_type||'');
    return mime.startsWith('video/')||['mp4','mov','avi','mkv','webm','m4v','3gp'].includes(anexoExtensao(anexo));
  }

  function anexoTipoLabel(a){
    if(anexoEhImagem(a))return 'Imagem';
    if(anexoEhVideo(a))return 'Vídeo';
    if(String(a?.mime_type||'')==='application/pdf')return 'PDF';
    return 'Documento';
  }

  function anexoContexto(a){
    return [
      a.acao_tipo_label,
      a.acao_data?dataBR(a.acao_data):'',
      a.acao_titulo,
      a.acao_localidade,
    ].filter(Boolean).join(' · ');
  }

  function anexoCardHtml(a){
    const imagem=anexoEhImagem(a);
    const video=anexoEhVideo(a);
    const contexto=anexoContexto(a);
    return `<article class="acoes-anexo">
      <a class="acoes-anexo-preview" href="${a.url_visualizar||a.url_download}" target="_blank" rel="noopener" title="Abrir anexo">
        <span class="acoes-anexo-kind">${esc(anexoTipoLabel(a))}</span>
        ${a.restrito?'<span class="acoes-anexo-restrito">Restrito</span>':''}
        ${imagem
          ?`<img src="${a.url_visualizar}" alt="${esc(a.nome_original)}" loading="lazy">`
          :video
            ?`<video src="${a.url_visualizar}" preload="metadata" muted playsinline></video>`
            :`<span class="acoes-anexo-file">${esc(anexoExtensao(a))}</span>`}
      </a>
      <div class="acoes-anexo-main">
        <div class="acoes-anexo-name" title="${esc(a.nome_original)}">${esc(a.nome_original)}</div>
        <div class="acoes-anexo-meta">${esc(tamanhoBR(a.tamanho))}${a.criado_por?` · ${esc(a.criado_por)}`:''}</div>
        ${contexto?`<div class="acoes-anexo-context">${esc(contexto)}</div>`:''}
        ${a.criado_em?`<div class="acoes-anexo-meta">Adicionado em ${esc(dataHoraBR(a.criado_em))}</div>`:''}
      </div>
      <div class="acoes-anexo-actions">
        ${a.pode_gerenciar_restritos?`<button class="btn btn-icon" type="button" data-alternar-restrito="${a.id_anexo}" data-restrito="${a.restrito?'1':'0'}" title="${a.restrito?'Tornar anexo comum':'Restringir à administração'}"><img src="/static/icons/cadeado.svg" alt="" class="icon-svg"></button>`:''}
        ${a.eh_previa?`<a class="btn btn-icon" href="${a.url_visualizar}" target="_blank" rel="noopener" title="Visualizar"><img src="/static/icons/busca.svg" alt="" class="icon-svg"></a>`:''}
        <a class="btn btn-icon" href="${a.url_download}" title="Baixar"><img src="/static/icons/importar.svg" alt="" class="icon-svg"></a>
        <button class="btn btn-icon" type="button" data-excluir-anexo="${a.id_anexo}" data-id-acao="${a.id_acao}" title="Excluir anexo"><img src="/static/icons/lixeira.svg" alt="" class="icon-svg"></button>
      </div>
    </article>`;
  }

  function anexosHtml(anexos){
    if(anexos===null)return '<div class="acoes-attachments-disabled">Carregando anexos...</div>';
    return (anexos||[]).map(anexoCardHtml).join('')||'<div class="acoes-attachments-disabled">Nenhum anexo cadastrado.</div>';
  }

  function detalhe(label,valor){
    if(!String(valor??'').trim())return '';
    return `<div class="acao-detail"><span>${esc(label)}</span><strong>${esc(valor)}</strong></div>`;
  }

  function detalhesRegistroHtml(r){
    const detalhes=[
      detalhe('Situação',r.situacao_label),
      detalhe('Caso / acompanhamento',r.caso),
      detalhe('Data final',r.data_fim?dataBR(r.data_fim):''),
      detalhe('Tipo de atividade',labelsLista(r.tipo_atividade_realizada_labels)),
      detalhe('Público alvo',labelsLista(r.publico_alvo_labels)),
      detalhe('Recurso utilizado',labelsLista(r.recurso_utilizado_labels)),
      detalhe('Endereço',r.endereco),
      detalhe('Coordenadas',r.coordenadas),
      detalhe('Órgãos e parceiros',r.parceiros),
      detalhe('Registrado por',r.criado_por),
      detalhe('Criado em',dataHoraBR(r.criado_em)),
      detalhe('Atualizado em',dataHoraBR(r.atualizado_em)),
    ].join('');
    return `<div class="acao-details-wrap">
      <div class="acao-detail-grid">${detalhes||'<span class="acoes-toolbar-meta">Sem informações complementares.</span>'}</div>
      ${(r.contexto||r.resultados||r.observacoes)?`<div class="acao-notes">${r.contexto?`<div class="acao-note"><strong>Contexto</strong>${esc(r.contexto)}</div>`:''}${r.resultados?`<div class="acao-note"><strong>Resultados e providências</strong>${esc(r.resultados)}</div>`:''}${r.observacoes?`<div class="acao-note"><strong>Observações</strong>${esc(r.observacoes)}</div>`:''}</div>`:''}
      <div class="acao-attachments-head">
        <strong>Anexos (${Number(r.total_anexos)||0})</strong>
        ${Number(r.total_anexos)>0?`<a class="btn btn-outline btn-sm" href="/api/acoes-setor/${r.id_acao}/anexos/baixar-todos"><img src="/static/icons/importar.svg" alt="" class="icon-svg"> Baixar todos</a>`:''}
      </div>
      <div class="acoes-anexo-list">${anexosHtml(anexosPorAcao[r.id_acao])}</div>
    </div>`;
  }

  function tituloRegistro(r){
    const bases={
      educativa:'Ação educativa',
      limpeza:'Limpeza / mutirão',
      vistoria:'Vistoria / atendimento técnico',
      reuniao:'Reunião / planejamento',
      outro:'Outro registro',
    };
    const base=bases[r.tipo]||r.tipo_label||'Registro';
    const complemento=r.tema||r.local||r.caso;
    return complemento?`${base} · ${complemento}`:base;
  }

  function registrosOrdenados(){
    const ordem=$('acoes-ordem').value;
    const lista=[...registros];
    if(ordem==='antigas')return lista.sort((a,b)=>String(a.data).localeCompare(String(b.data))||a.id_acao-b.id_acao);
    if(ordem==='publico')return lista.sort((a,b)=>(Number(b.publico_aproximado)||0)-(Number(a.publico_aproximado)||0));
    if(ordem==='localidade')return lista.sort((a,b)=>String(a.localidade||'').localeCompare(String(b.localidade||''),'pt-BR'));
    return lista.sort((a,b)=>String(b.data).localeCompare(String(a.data))||b.id_acao-a.id_acao);
  }

  function atualizarResumo(){
    const totalPublico=registros.reduce((s,r)=>s+(Number(r.publico_aproximado)||0),0);
    $('acoes-stat-total').textContent=fmtNumero.format(registros.length);
    $('acoes-stat-publico').textContent=fmtNumero.format(totalPublico);
    $('acoes-stat-educativas').textContent=fmtNumero.format(registros.filter(r=>r.tipo==='educativa').length);
    $('acoes-stat-limpezas').textContent=fmtNumero.format(registros.filter(r=>r.tipo==='limpeza').length);
    $('acoes-stat-outros').textContent=fmtNumero.format(registros.filter(r=>!['educativa','limpeza'].includes(r.tipo)).length);
  }

  function render(){
    const lista=registrosOrdenados();
    atualizarResumo();
    $('acoes-total').textContent=`${fmtNumero.format(lista.length)} registro(s)`;
    $('acoes-lista').innerHTML=lista.map(r=>{
      const data=dataPartes(r.data);
      const aberto=Number(registroAberto)===Number(r.id_acao);
      const classe=r.tipo||'';
      const local=[r.localidade,r.local].filter(Boolean).join(' · ')||'Local não informado';
      const momento=[r.periodo_label,horaRange(r)].filter(Boolean).join(' · ')||'Período não informado';
      return `<article class="acao-item ${aberto?'open':''}" data-acao-item="${r.id_acao}">
        <div class="acao-row">
          <div class="acao-date"><strong>${esc(data.dia)}</strong><span>${esc(data.mes)} ${esc(data.ano)}</span></div>
          <div class="acao-main">
            <div class="acao-main-top"><span class="acao-tag ${classe}">${esc(r.tipo_label)}</span><span class="acao-subtitle">${esc(r.situacao_label||'')} · Registro ${String(r.id_acao).padStart(6,'0')}</span></div>
            <div class="acao-title">${esc(tituloRegistro(r))}</div>
            <div class="acao-subtitle">${esc([r.caso,local].filter(Boolean).join(' · '))}</div>
          </div>
          <div class="acao-info"><span>Equipe</span><strong>${esc(r.agentes_nomes||'Não informada')}</strong><span>Horário</span><strong>${esc(momento)}</strong></div>
          <div class="acao-numbers">
            <div class="acao-number"><strong>${fmtNumero.format(Number(r.publico_aproximado)||0)}</strong><span>Público</span></div>
            <div class="acao-number"><strong>${fmtNumero.format(Number(r.total_anexos)||0)}</strong><span>Anexos</span></div>
          </div>
          <div class="acao-controls">
            <button class="btn btn-ghost btn-sm" type="button" data-alternar="${r.id_acao}">${aberto?'Recolher':'Detalhes'}</button>
            <button class="btn btn-icon" type="button" data-editar="${r.id_acao}" title="Editar"><img src="/static/icons/editar.svg" alt="" class="icon-svg"></button>
            <button class="btn btn-icon" type="button" data-excluir="${r.id_acao}" title="Excluir"><img src="/static/icons/lixeira.svg" alt="" class="icon-svg"></button>
          </div>
        </div>
        ${aberto?detalhesRegistroHtml(r):''}
      </article>`;
    }).join('')||'<div class="acao-empty">Nenhum registro encontrado com os filtros informados.</div>';
  }

  function atualizarEstadoAnexos(){
    const temAcao=Boolean($('acao-id').value);
    const anexos=anexosPorAcao[$('acao-id').value];
    $('acao-anexo-selecionar').disabled=!temAcao;
    $('acao-anexos-baixar-todos').disabled=!temAcao||!Array.isArray(anexos)||anexos.length===0;
    $('acao-anexos-aviso').style.display=temAcao?'none':'block';
  }

  function renderAnexos(anexos){
    $('acao-anexos-lista').innerHTML=$('acao-id').value?anexosHtml(anexos||[]):'';
  }

  async function carregarAnexos(idAcao){
    if(!idAcao){renderAnexos([]);return;}
    const data=await api(`/api/acoes-setor/${idAcao}/anexos`);
    anexosPorAcao[idAcao]=data.anexos||[];
    if(String($('acao-id').value)===String(idAcao))renderAnexos(data.anexos||[]);
    atualizarEstadoAnexos();
    if(galeriaAnexosCarregada)carregarGaleriaAnexos().catch(()=>{});
  }

  function atualizarResumoAnexos(anexos){
    const imagens=anexos.filter(anexoEhImagem).length;
    const videos=anexos.filter(anexoEhVideo).length;
    $('acoes-anexos-stat-total').textContent=fmtNumero.format(anexos.length);
    $('acoes-anexos-stat-imagens').textContent=fmtNumero.format(imagens);
    $('acoes-anexos-stat-videos').textContent=fmtNumero.format(videos);
    $('acoes-anexos-stat-outros').textContent=fmtNumero.format(anexos.length-imagens-videos);
  }

  async function carregarGaleriaAnexos(){
    $('acoes-anexos-galeria').innerHTML='<div class="acoes-attachments-disabled"><div class="spinner"></div></div>';
    const data=await api(`/api/acoes-setor/anexos?${paramsAnexos()}`);
    const anexos=data.anexos||[];
    $('acoes-anexos-total').textContent=`${fmtNumero.format(anexos.length)} anexo(s)`;
    $('acoes-anexos-galeria').innerHTML=anexosHtml(anexos);
    atualizarResumoAnexos(anexos);
    galeriaAnexosCarregada=true;
  }

  function renderHistorico(){
    if(!$('acoes-importacao-lista'))return;
    const grupos=inventarioHistorico?.grupos||[];
    const importados=grupos.filter(g=>g.importacao).length;
    $('acoes-importacao-total').textContent=inventarioHistorico
      ?`${fmtNumero.format(grupos.length)} conjunto(s) · ${fmtNumero.format(inventarioHistorico.total_arquivos||0)} arquivo(s) · ${fmtNumero.format(importados)} importado(s)`
      :'Nenhuma pasta conferida';
    $('acoes-importacao-lista').innerHTML=grupos.map(grupo=>{
      const s=grupo.sugestao||{};
      const avisos=grupo.avisos||[];
      const status=grupo.importacao
        ?`Importado · Registro ${String(grupo.importacao.id_acao).padStart(6,'0')}`
        :'Aguardando revisão';
      const localidades=(grupo.localidades_encontradas||[]).join(', ');
      return `<article class="acoes-import-card ${grupo.importacao?'imported':''}">
        <div class="acoes-import-main">
          <div class="acoes-import-title">
            <span>${esc(grupo.titulo)}</span>
            <span class="acao-tag ${esc(s.tipo||'outro')}">${esc(status)}</span>
            ${grupo.anexos_restritos_sugeridos?'<span class="acoes-import-restricted">Documentos restritos</span>':''}
          </div>
          <div class="acoes-import-meta">
            <span>${esc(s.data?dataBR(s.data):'Data a revisar')}</span>
            <span>${esc(localidades||s.localidade||'Localidade a revisar')}</span>
            <span>${fmtNumero.format(grupo.total_arquivos||0)} arquivo(s) · ${esc(tamanhoBR(grupo.total_bytes))}</span>
          </div>
          <div class="acoes-import-files">${(grupo.arquivos||[]).map(a=>`<span class="acoes-import-file" title="${esc(a.caminho_rel)}">${esc(a.nome)}</span>`).join('')}</div>
          ${avisos.map(aviso=>`<div class="acoes-import-warning">${esc(aviso)}</div>`).join('')}
        </div>
        <div class="acoes-import-actions">
          ${grupo.importacao
            ?`<button class="btn btn-outline btn-sm" type="button" data-importacao-abrir="${grupo.importacao.id_acao}">Abrir registro</button>`
            :`<button class="btn btn-primary btn-sm" type="button" data-importacao-revisar="${esc(grupo.id_grupo)}"><img src="/static/icons/editar.svg" alt="" class="icon-svg"> Revisar</button>`}
        </div>
      </article>`;
    }).join('')||'<div class="acao-empty">Nenhum arquivo compatível foi encontrado.</div>';
  }

  async function carregarHistorico(){
    const diretorio=$('acoes-importacao-diretorio')?.value.trim();
    if(!diretorio){toast('Informe a pasta do acervo histórico.','error');return;}
    localStorage.setItem('acoesSetorHistoricoDiretorio',diretorio);
    $('acoes-importacao-lista').innerHTML='<div class="acao-empty"><div class="spinner"></div></div>';
    const dados=await api('/api/acoes-setor/importacao-historica/previa',{
      method:'POST',
      headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
      body:JSON.stringify({diretorio}),
    });
    inventarioHistorico=dados;
    renderHistorico();
  }

  function prepararImportacaoHistorica(grupo){
    limparForm();
    const s=grupo.sugestao||{};
    importacaoAtiva=grupo;
    $('acao-form-title').textContent='Revisar importação histórica';
    $('acao-form-contexto').textContent=`${grupo.total_arquivos||0} documento(s) do acervo`;
    $('acao-salvar').innerHTML='<img src="/static/icons/importar.svg" alt="" class="icon-svg"> Importar registro';
    $('acao-tipo').value=s.tipo||'outro';
    $('acao-situacao').value=s.situacao||'realizada';
    $('acao-data').value=s.data||'';
    $('acao-data-fim').value=s.data_fim||'';
    setCheckedValues('acao-periodo',[s.periodo||'nao_informado']);
    $('acao-publico').value=s.publico_aproximado??'';
    camposTexto.forEach(campo=>{$(`acao-${campo}`).value=s[campo]||'';});
    setCheckedValues('acao-agente',s.agentes||[]);
    if($('acao-anexos-restritos')){
      $('acao-anexos-restritos').checked=Boolean(grupo.anexos_restritos_sugeridos);
    }
    atualizarCamposEducativos();
    atualizarEstadoAnexos();
    if(!dialog.open)dialog.showModal();
    setTimeout(()=>(s.data?$('acao-tipo'):$('acao-data')).focus(),0);
  }

  async function alternarRegistro(idAcao){
    if(Number(registroAberto)===Number(idAcao)){
      registroAberto=null;
      render();
      return;
    }
    registroAberto=idAcao;
    if(!(idAcao in anexosPorAcao)){
      anexosPorAcao[idAcao]=null;
      render();
      const data=await api(`/api/acoes-setor/${idAcao}/anexos`);
      anexosPorAcao[idAcao]=data.anexos||[];
    }
    render();
  }

  async function carregar(){
    $('acoes-lista').innerHTML='<div class="acao-empty"><div class="spinner"></div></div>';
    const data=await api(`/api/acoes-setor?${params()}`);
    registros=data.registros||[];
    if(registroAberto&&!registros.some(r=>Number(r.id_acao)===Number(registroAberto)))registroAberto=null;
    render();
  }

  function limparFiltrosRegistros(){
    ['acoes-busca','acoes-filtro-tipo','acoes-filtro-situacao','acoes-filtro-periodo','acoes-filtro-localidade','acoes-filtro-caso','acoes-filtro-agente','acoes-data-inicio','acoes-data-fim'].forEach(id=>{$(id).value='';});
    $('acoes-ordem').value='recentes';
  }

  function limparFiltrosAnexos(){
    ['acoes-anexos-busca','acoes-anexos-tipo-acao','acoes-anexos-tipo-arquivo','acoes-anexos-localidade','acoes-anexos-caso','acoes-anexos-agente','acoes-anexos-data-inicio','acoes-anexos-data-fim'].forEach(id=>{$(id).value='';});
  }

  async function salvar(){
    const dados=payload();
    if(!dados.data){toast('Informe a data inicial.','error');return;}
    if(dados.data_fim&&dados.data_fim<dados.data){toast('A data final não pode ser anterior à data inicial.','error');return;}
    if(!dados.periodo){toast('Informe o período do registro.','error');return;}
    if(importacaoAtiva){
      if(!confirm(`Importar este registro com ${importacaoAtiva.total_arquivos||0} documento(s)?`))return;
      const diretorio=$('acoes-importacao-diretorio').value.trim();
      const resp=await api('/api/acoes-setor/importacao-historica',{
        method:'POST',
        headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
        body:JSON.stringify({
          diretorio,
          id_grupo:importacaoAtiva.id_grupo,
          registro:dados,
          anexos_restritos:Boolean($('acao-anexos-restritos')?.checked),
        }),
      });
      const idImportado=resp.id_acao;
      importacaoAtiva=null;
      fecharFormulario();
      limparFiltrosRegistros();
      await carregar();
      await carregarHistorico();
      abrirAba('registros');
      registroAberto=null;
      await alternarRegistro(idImportado);
      toast(`Registro importado com ${resp.anexos_importados||0} anexo(s).`,'success');
      return;
    }
    const id=$('acao-id').value;
    const resp=await api(id?`/api/acoes-setor/${id}`:'/api/acoes-setor',{
      method:id?'PUT':'POST',
      headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
      body:JSON.stringify(dados),
    });
    const salvoId=resp.id_acao||id;
    const atualizada=await api(`/api/acoes-setor/${salvoId}`);
    preencherForm(atualizada,false);
    registroAberto=Number(salvoId);
    limparFiltrosRegistros();
    await carregar();
    toast(id?'Registro atualizado com sucesso.':'Registro criado. Os anexos já podem ser adicionados.','success');
  }

  async function enviarAnexos(){
    const id=$('acao-id').value;
    const arquivos=Array.from($('acao-anexos-arquivos').files||[]);
    if(!id||!arquivos.length)return;
    const form=new FormData();
    arquivos.forEach(arq=>form.append('arquivos',arq));
    if($('acao-anexos-restritos')?.checked)form.append('restrito','1');
    const resp=await fetch(`/api/acoes-setor/${id}/anexos`,{
      method:'POST',
      headers:{'X-CSRFToken':getCsrf()},
      body:form,
    });
    const data=await resp.json().catch(()=>({}));
    if(!resp.ok)throw new Error(data.erro||`Erro HTTP ${resp.status}`);
    $('acao-anexos-arquivos').value='';
    anexosPorAcao[id]=data.anexos||[];
    renderAnexos(data.anexos||[]);
    atualizarEstadoAnexos();
    await carregar();
    toast(`${arquivos.length} arquivo(s) adicionado(s).`,'success');
  }

  async function alternarRestricaoAnexo(idAnexo,restritoAtual){
    const tornarRestrito=!restritoAtual;
    const mensagem=tornarRestrito
      ?'Restringir este anexo à administração?'
      :'Tornar este anexo visível aos operadores?';
    if(!confirm(mensagem))return;
    await api(`/api/acoes-setor/anexos/${idAnexo}`,{
      method:'PUT',
      headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
      body:JSON.stringify({restrito:tornarRestrito}),
    });
    const idAcaoAtual=$('acao-id').value;
    if(idAcaoAtual)await carregarAnexos(idAcaoAtual);
    if(registroAberto){
      const data=await api(`/api/acoes-setor/${registroAberto}/anexos`);
      anexosPorAcao[registroAberto]=data.anexos||[];
    }
    await carregar();
    if(galeriaAnexosCarregada)await carregarGaleriaAnexos();
    toast(tornarRestrito?'Anexo restrito à administração.':'Anexo tornado comum.','success');
  }

  async function excluirAnexo(idAnexo){
    if(!confirm('Excluir este anexo?'))return;
    await api(`/api/acoes-setor/anexos/${idAnexo}`,{
      method:'DELETE',
      headers:{'X-CSRFToken':getCsrf()},
    });
    const idAcaoAtual=$('acao-id').value;
    if(idAcaoAtual)await carregarAnexos(idAcaoAtual);
    if(registroAberto){
      const data=await api(`/api/acoes-setor/${registroAberto}/anexos`);
      anexosPorAcao[registroAberto]=data.anexos||[];
    }
    await carregar();
    if(galeriaAnexosCarregada)await carregarGaleriaAnexos();
    toast('Anexo excluído.','success');
  }

  async function excluir(id){
    if(!confirm('Excluir este registro e todos os seus anexos?'))return;
    if(!confirm('Tem certeza? Esta exclusão não pode ser desfeita.'))return;
    await api(`/api/acoes-setor/${id}`,{
      method:'DELETE',
      headers:{'X-CSRFToken':getCsrf()},
    });
    if(Number(registroAberto)===Number(id))registroAberto=null;
    await carregar();
    toast('Registro excluído.','success');
  }

  function abrirAba(tab){
    document.querySelectorAll('.acoes-tab').forEach(item=>item.classList.toggle('active',item.dataset.acoesTab===tab));
    document.querySelectorAll('.acoes-tab-panel').forEach(panel=>{panel.hidden=panel.id!==`acoes-panel-${tab}`;});
    if(tab==='anexos')carregarGaleriaAnexos().catch(e=>toast(e.message,'error'));
  }

  document.addEventListener('DOMContentLoaded',()=>{
    limparForm();
    document.querySelectorAll('.acoes-tab').forEach(btn=>btn.addEventListener('click',()=>abrirAba(btn.dataset.acoesTab)));
    $('acao-nova').addEventListener('click',abrirFormularioNovo);
    $('acao-fechar').addEventListener('click',fecharFormulario);
    $('acao-cancelar').addEventListener('click',fecharFormulario);
    $('acao-salvar').addEventListener('click',()=>salvar().catch(e=>toast(e.message,'error')));
    $('acao-tipo').addEventListener('change',atualizarCamposEducativos);
    $('acao-agentes-busca').addEventListener('input',filtrarAgentes);
    $('acao-anexos-baixar-todos').addEventListener('click',()=>{
      const id=$('acao-id').value;
      if(id)window.location.href=`/api/acoes-setor/${id}/anexos/baixar-todos`;
    });
    $('acao-anexo-selecionar').addEventListener('click',()=>$('acao-anexos-arquivos').click());
    $('acao-anexos-arquivos').addEventListener('change',()=>enviarAnexos().catch(e=>toast(e.message,'error')));
    $('acoes-buscar').addEventListener('click',()=>carregar().catch(e=>toast(e.message,'error')));
    $('acoes-limpar-filtros').addEventListener('click',()=>{
      limparFiltrosRegistros();
      carregar().catch(e=>toast(e.message,'error'));
    });
    $('acoes-ordem').addEventListener('change',render);
    $('acoes-anexos-buscar').addEventListener('click',()=>carregarGaleriaAnexos().catch(e=>toast(e.message,'error')));
    $('acoes-anexos-limpar').addEventListener('click',()=>{
      limparFiltrosAnexos();
      carregarGaleriaAnexos().catch(e=>toast(e.message,'error'));
    });
    $('acoes-busca').addEventListener('keydown',e=>{
      if(e.key==='Enter')carregar().catch(err=>toast(err.message,'error'));
    });
    $('acoes-anexos-busca').addEventListener('keydown',e=>{
      if(e.key==='Enter')carregarGaleriaAnexos().catch(err=>toast(err.message,'error'));
    });
    if($('acoes-importacao-diretorio')){
      $('acoes-importacao-diretorio').value=localStorage.getItem('acoesSetorHistoricoDiretorio')||'';
      $('acoes-importacao-escanear').addEventListener('click',()=>carregarHistorico().catch(e=>toast(e.message,'error')));
      $('acoes-importacao-diretorio').addEventListener('keydown',e=>{
        if(e.key==='Enter')carregarHistorico().catch(err=>toast(err.message,'error'));
      });
      $('acoes-importacao-lista').addEventListener('click',async e=>{
        const revisar=e.target.closest('[data-importacao-revisar]');
        const abrir=e.target.closest('[data-importacao-abrir]');
        if(revisar){
          const grupo=(inventarioHistorico?.grupos||[]).find(
            item=>item.id_grupo===revisar.dataset.importacaoRevisar
          );
          if(grupo)prepararImportacaoHistorica(grupo);
          return;
        }
        if(abrir){
          try{preencherForm(await api(`/api/acoes-setor/${abrir.dataset.importacaoAbrir}`));}
          catch(err){toast(err.message,'error');}
        }
      });
    }
    $('acoes-lista').addEventListener('click',async e=>{
      const alternar=e.target.closest('[data-alternar]');
      const editar=e.target.closest('[data-editar]');
      const excluirBtn=e.target.closest('[data-excluir]');
      const anexoBtn=e.target.closest('[data-excluir-anexo]');
      const restritoBtn=e.target.closest('[data-alternar-restrito]');
      if(restritoBtn){alternarRestricaoAnexo(restritoBtn.dataset.alternarRestrito,restritoBtn.dataset.restrito==='1').catch(err=>toast(err.message,'error'));return;}
      if(anexoBtn){excluirAnexo(anexoBtn.dataset.excluirAnexo).catch(err=>toast(err.message,'error'));return;}
      if(alternar){alternarRegistro(alternar.dataset.alternar).catch(err=>toast(err.message,'error'));return;}
      if(editar){
        try{preencherForm(await api(`/api/acoes-setor/${editar.dataset.editar}`));}
        catch(err){toast(err.message,'error');}
        return;
      }
      if(excluirBtn){excluir(excluirBtn.dataset.excluir).catch(err=>toast(err.message,'error'));}
    });
    ['acao-anexos-lista','acoes-anexos-galeria'].forEach(id=>{
      $(id).addEventListener('click',e=>{
        const restritoBtn=e.target.closest('[data-alternar-restrito]');
        if(restritoBtn){
          alternarRestricaoAnexo(restritoBtn.dataset.alternarRestrito,restritoBtn.dataset.restrito==='1').catch(err=>toast(err.message,'error'));
          return;
        }
        const btn=e.target.closest('[data-excluir-anexo]');
        if(btn)excluirAnexo(btn.dataset.excluirAnexo).catch(err=>toast(err.message,'error'));
      });
    });
    dialog.addEventListener('click',e=>{if(e.target===dialog)fecharFormulario();});
    carregar().catch(e=>toast(`Erro ao carregar ações: ${e.message}`,'error'));
  });
})();
