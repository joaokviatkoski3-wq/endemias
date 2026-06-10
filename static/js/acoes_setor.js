(function(){
  const $ = (id) => document.getElementById(id);
  const camposTexto = [
    'localidade', 'local', 'endereco', 'tema', 'contexto', 'coordenadas', 'observacoes'
  ];
  const fmtData = new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC' });
  let registros = [];
  let registroAberto = null;
  const anexosPorAcao = {};

  function esc(valor){
    return String(valor ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  function normalizar(valor){
    return String(valor || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function dataBR(valor){
    if(!valor) return '-';
    const partes = String(valor).slice(0, 10).split('-');
    if(partes.length !== 3) return valor;
    return fmtData.format(new Date(Date.UTC(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]))));
  }

  function tamanhoBR(bytes){
    const n = Number(bytes || 0);
    if(n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
    if(n >= 1024) return `${Math.round(n / 1024)} KB`;
    return `${n} B`;
  }

  function horaRange(r){
    if(r.hora_inicio && r.hora_fim) return `${r.hora_inicio} - ${r.hora_fim}`;
    return r.hora_inicio || r.hora_fim || '';
  }

  function params(){
    const p = new URLSearchParams();
    if($('acoes-busca').value.trim()) p.set('busca', $('acoes-busca').value.trim());
    if($('acoes-filtro-tipo').value) p.set('tipo', $('acoes-filtro-tipo').value);
    if($('acoes-ano').value) p.set('ano', $('acoes-ano').value);
    return p.toString();
  }

  async function api(url, opts={}){
    const resp = await fetch(url, opts);
    const data = await resp.json().catch(() => ({}));
    if(!resp.ok) throw new Error(data.erro || `Erro HTTP ${resp.status}`);
    return data;
  }

  function payload(){
    const data = {
      tipo: $('acao-tipo').value,
      data: $('acao-data').value,
      hora_inicio: $('acao-hora-inicio').value,
      hora_fim: $('acao-hora-fim').value,
      publico_aproximado: $('acao-publico').value,
      agentes: Array.from(document.querySelectorAll('input[name="acao-agente"]:checked')).map(opt => opt.value),
    };
    camposTexto.forEach(campo => {
      data[campo] = $(`acao-${campo}`).value.trim();
    });
    return data;
  }

  function limparForm(){
    $('acao-id').value = '';
    $('acao-form-title').textContent = 'Nova ação';
    $('acao-tipo').value = 'educativa';
    $('acao-data').value = new Date().toISOString().slice(0, 10);
    $('acao-hora-inicio').value = '';
    $('acao-hora-fim').value = '';
    $('acao-publico').value = '';
    camposTexto.forEach(campo => { $(`acao-${campo}`).value = ''; });
    $('acao-agentes-busca').value = '';
    Array.from(document.querySelectorAll('input[name="acao-agente"]')).forEach(opt => { opt.checked = false; });
    filtrarAgentes();
    renderAnexos([]);
    atualizarEstadoAnexos();
  }

  function preencherForm(r){
    $('acao-id').value = r.id_acao;
    $('acao-form-title').textContent = 'Editar ação';
    $('acao-tipo').value = r.tipo || 'educativa';
    $('acao-data').value = r.data || '';
    $('acao-hora-inicio').value = r.hora_inicio || '';
    $('acao-hora-fim').value = r.hora_fim || '';
    $('acao-publico').value = r.publico_aproximado ?? '';
    camposTexto.forEach(campo => { $(`acao-${campo}`).value = r[campo] || ''; });
    const ids = new Set((r.agentes || []).map(a => String(a.id_agente)));
    Array.from(document.querySelectorAll('input[name="acao-agente"]')).forEach(opt => { opt.checked = ids.has(opt.value); });
    carregarAnexos(r.id_acao).catch(e => toast('Erro ao carregar anexos: ' + e.message, 'error'));
    atualizarEstadoAnexos();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function filtrarAgentes(){
    const termo = normalizar($('acao-agentes-busca').value);
    let visiveis = 0;
    document.querySelectorAll('.acoes-agent-option').forEach(label => {
      const nome = normalizar(label.textContent);
      const mostrar = !termo || nome.includes(termo);
      label.classList.toggle('hidden', !mostrar);
      if(mostrar) visiveis += 1;
    });
    $('acao-agentes-vazio').classList.toggle('show', visiveis === 0);
  }

  function detalhe(label, valor){
    if(!String(valor || '').trim()) return '';
    return `<div><strong>${label}:</strong> ${esc(valor)}</div>`;
  }

  function anexosHtml(anexos){
    if(anexos === null) return '<div class="acoes-attachments-disabled">Carregando anexos...</div>';
    return (anexos || []).map(a => {
      const ver = a.eh_previa
        ? `<a class="btn btn-icon" href="${a.url_visualizar}" target="_blank" rel="noopener" title="Visualizar"><img src="/static/icons/busca.svg" alt="" class="icon-svg"></a>`
        : '';
      return `<div class="acoes-anexo">
        <div class="acoes-anexo-main">
          <div class="acoes-anexo-name">${esc(a.nome_original)}</div>
          <div class="acoes-anexo-meta">${esc(a.mime_type || 'arquivo')} | ${esc(tamanhoBR(a.tamanho))}</div>
        </div>
        <div class="acoes-anexo-actions">
          ${ver}
          <a class="btn btn-icon" href="${a.url_download}" title="Baixar"><img src="/static/icons/importar.svg" alt="" class="icon-svg"></a>
          <button class="btn btn-icon" type="button" data-excluir-anexo="${a.id_anexo}" data-id-acao="${a.id_acao}" title="Excluir anexo"><img src="/static/icons/lixeira.svg" alt="" class="icon-svg"></button>
        </div>
      </div>`;
    }).join('') || '<div class="acoes-attachments-disabled">Nenhum anexo cadastrado.</div>';
  }

  function detalhesRegistroHtml(r){
    const detalhes = [
      detalhe('Localidade', r.localidade),
      detalhe('Local', r.local),
      detalhe('Endereço', r.endereco),
      detalhe('Agentes', r.agentes_nomes),
      detalhe('Público aprox.', r.publico_aproximado),
      detalhe('Coordenadas', r.coordenadas),
    ].join('');
    const notas = [r.contexto, r.observacoes].filter(Boolean).join('\n');
    return `<div class="acao-expanded">
      <div class="acao-details">${detalhes || '<span style="color:var(--text3);">Sem detalhes adicionais.</span>'}</div>
      ${notas ? `<div class="acao-note">${esc(notas)}</div>` : ''}
      <div class="acao-expanded-title">Anexos</div>
      <div class="acoes-anexo-list">${anexosHtml(anexosPorAcao[r.id_acao])}</div>
    </div>`;
  }

  function render(){
    $('acoes-total').textContent = `${registros.length} registro(s)`;
    $('acoes-lista').innerHTML = registros.map(r => {
      const classe = r.tipo === 'limpeza' ? 'limpeza' : '';
      const titulo = r.tipo === 'limpeza'
        ? `Mutirão de limpeza${r.local ? ` - ${r.local}` : ''}`
        : `Ação educativa${r.tema ? ` - ${r.tema}` : ''}`;
      const aberto = Number(registroAberto) === Number(r.id_acao);
      return `<article class="acao-item ${aberto ? 'open' : ''}" data-acao-item="${r.id_acao}">
        <div class="acao-item-top">
          <div>
            <span class="acao-tag ${classe}">${esc(r.tipo_label)}</span>
            <div class="acao-title">${esc(titulo)}</div>
            <div class="acao-meta">${esc(dataBR(r.data))}${horaRange(r) ? ` | ${esc(horaRange(r))}` : ''}</div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-icon" type="button" data-editar="${r.id_acao}" title="Editar"><img src="/static/icons/editar.svg" alt="" class="icon-svg"></button>
            <button class="btn btn-icon" type="button" data-excluir="${r.id_acao}" title="Excluir"><img src="/static/icons/lixeira.svg" alt="" class="icon-svg"></button>
          </div>
        </div>
        ${aberto ? detalhesRegistroHtml(r) : ''}
      </article>`;
    }).join('') || '<div class="acao-empty">Nenhuma ação encontrada.</div>';
  }

  function atualizarEstadoAnexos(){
    const temAcao = Boolean($('acao-id').value);
    $('acao-anexo-selecionar').disabled = !temAcao;
    $('acao-anexos-aviso').style.display = temAcao ? 'none' : 'block';
  }

  function renderAnexos(anexos){
    $('acao-anexos-lista').innerHTML = $('acao-id').value ? anexosHtml(anexos || []) : '';
  }

  async function carregarAnexos(idAcao){
    if(!idAcao){ renderAnexos([]); return; }
    const data = await api(`/api/acoes-setor/${idAcao}/anexos`);
    anexosPorAcao[idAcao] = data.anexos || [];
    renderAnexos(data.anexos || []);
  }

  async function alternarRegistro(idAcao){
    if(Number(registroAberto) === Number(idAcao)){
      registroAberto = null;
      render();
      return;
    }
    registroAberto = idAcao;
    if(!(idAcao in anexosPorAcao)){
      anexosPorAcao[idAcao] = null;
      render();
      const data = await api(`/api/acoes-setor/${idAcao}/anexos`);
      anexosPorAcao[idAcao] = data.anexos || [];
    }
    render();
  }

  async function carregar(){
    const data = await api('/api/acoes-setor?' + params());
    registros = data.registros || [];
    if(registroAberto && !registros.some(r => Number(r.id_acao) === Number(registroAberto))){
      registroAberto = null;
    }
    render();
  }

  function focarRegistroSalvo(registro){
    $('acoes-busca').value = '';
    $('acoes-filtro-tipo').value = '';
    $('acoes-ano').value = String(registro.data || '').slice(0, 4);
  }

  async function salvar(){
    const data = payload();
    if(!data.data){ toast('Informe a data da ação.', 'error'); return; }
    const id = $('acao-id').value;
    const resp = await api(id ? `/api/acoes-setor/${id}` : '/api/acoes-setor', {
      method: id ? 'PUT' : 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify(data),
    });
    toast('Ação salva com sucesso.', 'success');
    const salvoId = resp.id_acao || id;
    if(salvoId){
      const atualizada = await api(`/api/acoes-setor/${salvoId}`);
      focarRegistroSalvo(atualizada);
    }
    await carregar();
    limparForm();
  }

  async function enviarAnexos(){
    const id = $('acao-id').value;
    const arquivos = Array.from($('acao-anexos-arquivos').files || []);
    if(!id || !arquivos.length) return;
    const form = new FormData();
    arquivos.forEach(arq => form.append('arquivos', arq));
    const resp = await fetch(`/api/acoes-setor/${id}/anexos`, {
      method: 'POST',
      headers: {'X-CSRFToken': getCsrf()},
      body: form,
    });
    const data = await resp.json().catch(() => ({}));
    if(!resp.ok) throw new Error(data.erro || `Erro HTTP ${resp.status}`);
    $('acao-anexos-arquivos').value = '';
    anexosPorAcao[id] = data.anexos || [];
    renderAnexos(data.anexos || []);
    render();
    toast('Anexo salvo com sucesso.', 'success');
  }

  async function excluirAnexo(idAnexo){
    if(!confirm('Excluir este anexo?')) return;
    await api(`/api/acoes-setor/anexos/${idAnexo}`, {
      method: 'DELETE',
      headers: {'X-CSRFToken': getCsrf()},
    });
    const idAcaoAtual = $('acao-id').value;
    if(idAcaoAtual) await carregarAnexos(idAcaoAtual);
    if(registroAberto){
      const data = await api(`/api/acoes-setor/${registroAberto}/anexos`);
      anexosPorAcao[registroAberto] = data.anexos || [];
      render();
    }
    toast('Anexo excluído.', 'success');
  }

  async function excluir(id){
    if(!confirm('Excluir esta ação?')) return;
    await api(`/api/acoes-setor/${id}`, {
      method: 'DELETE',
      headers: {'X-CSRFToken': getCsrf()},
    });
    toast('Ação excluída.', 'success');
    if(Number(registroAberto) === Number(id)) registroAberto = null;
    await carregar();
  }

  document.addEventListener('DOMContentLoaded', () => {
    limparForm();
    $('acao-salvar').addEventListener('click', () => salvar().catch(e => toast(e.message, 'error')));
    $('acao-limpar').addEventListener('click', limparForm);
    $('acao-cancelar').addEventListener('click', limparForm);
    $('acao-agentes-busca').addEventListener('input', filtrarAgentes);
    $('acao-anexo-selecionar').addEventListener('click', () => $('acao-anexos-arquivos').click());
    $('acao-anexos-arquivos').addEventListener('change', () => enviarAnexos().catch(e => toast(e.message, 'error')));
    $('acoes-buscar').addEventListener('click', () => carregar().catch(e => toast(e.message, 'error')));
    ['acoes-busca', 'acoes-filtro-tipo', 'acoes-ano'].forEach(id => {
      $(id).addEventListener('change', () => carregar().catch(e => toast(e.message, 'error')));
    });
    $('acoes-busca').addEventListener('keydown', e => {
      if(e.key === 'Enter') carregar().catch(err => toast(err.message, 'error'));
    });
    $('acoes-lista').addEventListener('click', async e => {
      const editar = e.target.closest('[data-editar]');
      const excluirBtn = e.target.closest('[data-excluir]');
      const anexoBtn = e.target.closest('[data-excluir-anexo]');
      if(anexoBtn){
        excluirAnexo(anexoBtn.dataset.excluirAnexo).catch(err => toast(err.message, 'error'));
        return;
      }
      if(editar){
        const r = await api(`/api/acoes-setor/${editar.dataset.editar}`);
        preencherForm(r);
        return;
      }
      if(excluirBtn){
        excluir(excluirBtn.dataset.excluir).catch(err => toast(err.message, 'error'));
        return;
      }
      if(e.target.closest('a,button')) return;
      const item = e.target.closest('[data-acao-item]');
      if(item){
        alternarRegistro(item.dataset.acaoItem).catch(err => toast(err.message, 'error'));
      }
    });
    $('acao-anexos-lista').addEventListener('click', e => {
      const btn = e.target.closest('[data-excluir-anexo]');
      if(btn) excluirAnexo(btn.dataset.excluirAnexo).catch(err => toast(err.message, 'error'));
    });
    carregar().catch(e => toast('Erro ao carregar ações: ' + e.message, 'error'));
  });
})();
