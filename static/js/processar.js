// ── Estado ────────────────────────────────────────────────────────────────────
let arquivos = [];
let currentJobId = null;
let logDryRun = '';

const CORES = Object.assign({}, WORK_TYPE_COLORS, {LARVAS:'#ef4444', ESPOROTRICOSE:'#14b8a6', RECOLHIMENTO:'#f59e0b', AMOSTRA_ANIMAIS:'#8b5cf6', BRI:'#06b6d4'});
const WORK_TYPES = JSON.parse(document.getElementById('processar-work-types').textContent || '[]');

// ── Helpers de tela ───────────────────────────────────────────────────────────
function mostrar(id) {
  ['area-upload','area-log','area-confirmar','area-commit'].forEach(x =>
    document.getElementById(x).style.display = (x === id ? 'block' : 'none')
  );
}

// ── Dropzone ──────────────────────────────────────────────────────────────────
const dropzone  = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');

dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover',  e => { e.preventDefault(); dropzone.classList.add('over'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('over'));
dropzone.addEventListener('drop', e => { e.preventDefault(); dropzone.classList.remove('over'); adicionarArquivos([...e.dataTransfer.files]); });
fileInput.addEventListener('change', () => { adicionarArquivos([...fileInput.files]); fileInput.value = ''; });

function adicionarArquivos(novos) {
  const validos = novos.filter(f => f.name.endsWith('.xlsx'));
  const nomes   = new Set(arquivos.map(f => f.name));
  validos.forEach(f => { if (!nomes.has(f.name)) arquivos.push(f); });
  renderFileList();
}

function renderFileList() {
  const container = document.getElementById('file-items');
  const listDiv   = document.getElementById('file-list');
  const btnProc   = document.getElementById('btn-processar');
  const btnLimpar = document.getElementById('btn-limpar');
  container.innerHTML = '';
  if (arquivos.length === 0) {
    listDiv.style.display = 'none'; btnProc.disabled = true; btnLimpar.style.display = 'none'; return;
  }
  listDiv.style.display = 'block'; btnLimpar.style.display = 'inline-flex'; btnProc.disabled = false;
  arquivos.forEach((f, i) => {
    const prefixo = f.name.split('_')[0].toUpperCase();
    const cor = CORES[prefixo] || '#64748b';
    const el = document.createElement('div');
    el.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--surface2);border-radius:var(--radius-sm);border:1px solid var(--border);';
    el.innerHTML = `
      <span style="background:${cor}18;color:${cor};border-radius:4px;padding:2px 7px;font-size:10.5px;font-weight:700;">${prefixo}</span>
      <span style="flex:1;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${f.name}</span>
      <span style="font-size:11px;color:var(--text3);">${(f.size/1024).toFixed(0)} KB</span>
      <button type="button" data-remover-arquivo="${i}" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:16px;line-height:1;padding:0 2px;">&times;</button>`;
    container.appendChild(el);
  });
}

function removerArquivo(i) { arquivos.splice(i, 1); renderFileList(); }
function limparArquivos()   { arquivos = []; renderFileList(); }

function configurarAcoesProcessamento() {
  document.getElementById('btn-processar')?.addEventListener('click', iniciarProcessamento);
  document.getElementById('btn-limpar')?.addEventListener('click', limparArquivos);
  document.getElementById('btn-copiar-log')?.addEventListener('click', copiarLog);
  document.getElementById('btn-confirmar')?.addEventListener('click', confirmar);
  document.getElementById('btn-cancelar-processamento')?.addEventListener('click', cancelar);
  document.getElementById('btn-voltar-log')?.addEventListener('click', voltarLog);
  document.getElementById('btn-copiar-log-commit')?.addEventListener('click', copiarLogCommit);
  document.getElementById('btn-novo')?.addEventListener('click', novoProcessamento);

  document.addEventListener('click', event => {
    const removeBtn = event.target.closest('[data-remover-arquivo]');
    if (removeBtn) {
      removerArquivo(Number(removeBtn.dataset.removerArquivo));
      return;
    }
    const gerarBtn = event.target.closest('[data-gerar-consolidado]');
    if (gerarBtn && !gerarBtn.disabled) {
      gerarConsolidados(gerarBtn.dataset.gerarConsolidado);
    }
  });
}

// ── FASE 1 — DRY-RUN ─────────────────────────────────────────────────────────
async function iniciarProcessamento() {
  if (!arquivos.length) return;
  document.getElementById('log-linhas').innerHTML = '';
  document.getElementById('log-cursor').style.display = 'inline-block';
  document.getElementById('log-status-badge').style.display = 'none';
  document.querySelector('#area-log .chart-hd .chart-title').innerHTML =
    '<img src="/static/icons/rolar.svg" alt="📜" class="icon-svg"> Verificando planilhas…';
  mostrar('area-log');

  const formData = new FormData();
  arquivos.forEach(f => formData.append('arquivos', f));

  let jobId;
  try {
    const r = await fetch('/processar/iniciar', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: formData
    });
    const d = await r.json();
    if (!r.ok || d.erro) { appendLog('ERRO: ' + (d.erro || 'Falha no upload'), 'erro'); finalizarDryRun(false, []); return; }
    jobId = d.job_id;
    currentJobId = jobId;
    appendLog(`Upload: ${d.arquivos.length} arquivo(s) recebido(s).`, 'ok');
  } catch(e) {
    appendLog('ERRO de comunicação: ' + e.message, 'erro'); finalizarDryRun(false, []); return;
  }

  let sse;
  try {
    const response = await fetch(`/processar/stream/${jobId}`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() }
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    sse = await responseToEventSource(response);
  } catch(e) {
    appendLog('\n[ERRO] Conexão interrompida.', 'erro');
    finalizarDryRun(false, []);
    return;
  }
  sse.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.done !== undefined) {
      sse.close();
      finalizarDryRun(d.ok, d.sumario || []);
      return;
    }
    if (d.msg !== undefined) appendLog(d.msg, d.tag || 'normal');
  };
  sse.onerror = () => { sse.close(); appendLog('\n[ERRO] Conexão interrompida.', 'erro'); finalizarDryRun(false, []); };
}

function finalizarDryRun(ok, sumario) {
  document.getElementById('log-cursor').style.display = 'none';
  const badge = document.getElementById('log-status-badge');
  badge.style.display = 'inline-flex';
  if (ok) {
    badge.className = 'badge badge-entregue'; badge.textContent = 'Verificação OK';
  } else {
    badge.className = 'badge badge-naoloc'; badge.textContent = 'Verificação com erros';
  }
  document.querySelector('#area-log .chart-hd .chart-title').innerHTML =
    '<img src="/static/icons/rolar.svg" alt="📜" class="icon-svg"> Log de verificação';

  // Salvar log texto para exibição eventual
  logDryRun = document.getElementById('log-linhas').textContent;

  // Montar tela de confirmação
  document.getElementById('sumario-erros').style.display = ok ? 'none' : 'block';
  document.getElementById('sumario-ok').style.display    = ok ? 'block' : 'none';

  // Tabela sumário
  let html = '<table class="sumario-table"><thead><tr><th>Arquivo</th><th>Tipo</th><th>Registros novos</th><th>Coletas/animais/materiais</th></tr></thead><tbody>';
  if (sumario.length) {
    sumario.forEach(s => {
      const cor = CORES[s.tipo] || '#64748b';
      const label = s.tipo === 'ESPOROTRICOSE' ? 'Esporotricose' : (WORK_TYPE_LABELS[s.tipo] || s.tipo);
      const labelFinal = s.tipo === 'RECOLHIMENTO'
        ? 'Recolhimento de materiais'
        : s.tipo === 'AMOSTRA_ANIMAIS'
          ? 'Amostra de animais'
        : s.tipo === 'BRI'
          ? 'BRI'
          : label;
      const secundarios = s.tipo === 'ESPOROTRICOSE'
        ? (s.animais_novos ?? s.coletas_novas ?? 0)
        : s.tipo === 'RECOLHIMENTO'
          ? (s.materiais_novos ?? 0)
        : s.tipo === 'AMOSTRA_ANIMAIS'
          ? (s.animais_novos ?? s.coletas_novas ?? 0)
        : s.tipo === 'BRI'
          ? (s.carga_nova ?? 0)
        : (s.coletas_novas ?? s.coletas ?? 0);
      html += `<tr>
        <td style="font-size:12px;">${s.arquivo}</td>
        <td><span class="sumario-tipo" style="background:${cor}18;color:${cor};">${s.tipo} - ${labelFinal}</span></td>
        <td style="font-weight:700;">${s.visitas_novas ?? s.visitas ?? 0}</td>
        <td>${secundarios}</td>
      </tr>`;
    });
  } else {
    html += '<tr><td colspan="4" style="color:var(--text3);text-align:center;padding:16px;">Nenhum dado novo para importar</td></tr>';
  }
  html += '</tbody></table>';
  document.getElementById('sumario-tabela').innerHTML = html;

  // Ir para confirmação após pequeno delay para o usuário ver o log
  setTimeout(() => mostrar('area-confirmar'), 600);
}

// ── FASE 2 — CONFIRMAÇÃO / CANCELAMENTO ──────────────────────────────────────
function voltarLog() { mostrar('area-log'); }

async function cancelar() {
  if (currentJobId) {
    fetch(`/processar/cancelar/${currentJobId}`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() }
    }).catch(()=>{});
    currentJobId = null;
  }
  novoProcessamento();
  toast('Processamento cancelado. Nenhum dado foi gravado.', 'info');
}

async function confirmar() {
  if (!currentJobId) return;
  document.getElementById('commit-log-linhas').innerHTML = '';
  document.getElementById('commit-cursor').style.display = 'inline-block';
  document.getElementById('commit-badge').style.display  = 'none';
  document.getElementById('btn-novo').style.display      = 'none';
  mostrar('area-commit');

  const jobId = currentJobId;
  const response = await fetch(`/processar/confirmar/${jobId}`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf() }
  });
  if (!response.ok) {
    appendCommitLog('\n[ERRO] Conexão interrompida.', 'erro');
    document.getElementById('commit-cursor').style.display = 'none';
    document.getElementById('btn-novo').style.display = 'inline-flex';
    return;
  }
  const sse = await responseToEventSource(response);
  sse.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.done !== undefined) {
      sse.close();
      document.getElementById('commit-cursor').style.display = 'none';
      document.getElementById('btn-novo').style.display      = 'inline-flex';
      const badge = document.getElementById('commit-badge');
      badge.style.display = 'inline-flex';
      if (d.ok) {
        badge.className = 'badge badge-entregue'; badge.textContent = 'Gravado com sucesso';
        toast('Dados gravados no banco com sucesso!', 'success');
        document.getElementById('card-downloads').style.display = 'block';
        carregarStatusConsolidados();
      } else {
        badge.className = 'badge badge-naoloc'; badge.textContent = 'Concluído com erros';
        toast('Importação concluída com erros.', 'error');
      }
      currentJobId = null;
      return;
    }
    if (d.msg !== undefined) appendCommitLog(d.msg, d.tag || 'normal');
  };
  sse.onerror = () => {
    sse.close();
    appendCommitLog('\n[ERRO] Conexão interrompida.', 'erro');
    document.getElementById('commit-cursor').style.display = 'none';
    document.getElementById('btn-novo').style.display = 'inline-flex';
  };
}

// ── Helpers de log ────────────────────────────────────────────────────────────
async function carregarStatusConsolidados() {
  try {
    const resp = await fetch('/saida/consolidados/status');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    renderConsolidados(data.tipos || []);
  } catch (e) {
    renderConsolidados([]);
  }
}

function renderConsolidados(tipos) {
  const porTipo = new Map((tipos || []).map(t => [t.tipo, t]));
  const html = `<div class="consolidado-grid">${WORK_TYPES.map(tipo => {
    const info = porTipo.get(tipo) || {tipo, existe:false, gerado_em:null};
    const cor = WORK_TYPE_COLORS[tipo] || '#64748b';
    const status = info.existe
      ? `Gerado em ${info.gerado_em || '-'}`
      : 'Ainda não gerado';
    const download = info.existe
      ? `<a href="/saida/download/${tipo}" class="btn btn-outline btn-sm" style="border-color:${cor};color:${cor};"><img src="/static/icons/importar.svg" alt="" class="icon-svg"> Baixar</a>`
      : `<button class="btn btn-outline btn-sm" disabled>Baixar</button>`;
    return `<div class="consolidado-item">
      <div class="consolidado-top">
        <div>
          <div class="consolidado-codigo">${tipo}_consolidado.xlsx</div>
          <div class="consolidado-meta">Abas: Visitas e Coletas<br>${status}</div>
        </div>
        <span class="sumario-tipo" style="background:${cor}18;color:${cor};">${tipo}</span>
      </div>
      <div class="consolidado-actions">
        <button class="btn btn-ghost btn-sm" type="button" data-gerar-consolidado="${tipo}">Gerar</button>
        ${download}
      </div>
    </div>`;
  }).join('')}</div>`;
  document.querySelectorAll('.consolidados-list').forEach(el => { el.innerHTML = html; });
}

async function gerarConsolidados(tipo) {
  const btnTodos = document.getElementById('btn-gerar-todos');
  if (btnTodos) btnTodos.disabled = true;
  toast(tipo === 'TODOS' ? 'Gerando consolidados...' : `Gerando consolidado ${tipo}...`, 'info');
  try {
    const resp = await fetch('/saida/gerar-consolidados', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify({tipo})
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.erro || `HTTP ${resp.status}`);
    renderConsolidados(data.tipos || []);
    const gerados = (data.resultados || []).filter(r => r.caminho).length;
    toast(gerados ? 'Consolidados atualizados.' : 'Não há dados para gerar consolidados.', gerados ? 'success' : 'info');
  } catch (e) {
    toast('Erro ao gerar consolidados: ' + e.message, 'error');
  } finally {
    if (btnTodos) btnTodos.disabled = false;
  }
}

async function responseToEventSource(response) {
  const stream = { onmessage: null, onerror: null, close() {} };
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  setTimeout(async () => {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';
        for (const event of events) {
          const line = event.split('\n').find(item => item.startsWith('data: '));
          if (line && stream.onmessage) {
            stream.onmessage({ data: line.slice(6) });
          }
        }
      }
    } catch (e) {
      if (stream.onerror) stream.onerror(e);
    }
  }, 0);
  return stream;
}

function appendLog(msg, tag) {
  _addLogLine('log-linhas', 'log-container', msg, tag);
}
function appendCommitLog(msg, tag) {
  _addLogLine('commit-log-linhas', 'commit-log-container', msg, tag);
}
function _addLogLine(linesId, containerId, msg, tag) {
  const span = document.createElement('span');
  span.className = 'log-' + ({'titulo':'titulo','ok':'ok','erro':'erro','aviso':'aviso'}[tag]||'normal');
  span.textContent = msg + '\n';
  document.getElementById(linesId).appendChild(span);
  const box = document.getElementById(containerId);
  box.scrollTop = box.scrollHeight;
}

function copiarLog() {
  navigator.clipboard.writeText(document.getElementById('log-linhas').textContent)
    .then(() => toast('Log copiado!', 'success'));
}
function copiarLogCommit() {
  navigator.clipboard.writeText(document.getElementById('commit-log-linhas').textContent)
    .then(() => toast('Log copiado!', 'success'));
}

function novoProcessamento() {
  arquivos = []; currentJobId = null;
  renderFileList();
  mostrar('area-upload');
}

configurarAcoesProcessamento();
carregarStatusConsolidados();
