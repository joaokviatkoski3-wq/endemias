// ── Estado ────────────────────────────────────────────────────────────────────
let calendario;
let editandoId = null;
const AGENDA_CONFIG = JSON.parse(document.getElementById('agenda-config').textContent || '{}');
const IS_ADMIN = Boolean(AGENDA_CONFIG.is_admin);

const TIPO_COR = JSON.parse(document.getElementById('agenda-tipo-cores').textContent || '{}');
const TIPO_LABEL = JSON.parse(document.getElementById('agenda-form-labels').textContent || '{}');

// ── Inicializar FullCalendar ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('calendario');
  calendario = new FullCalendar.Calendar(el, {
    locale:        'pt-br',
    initialView:   'dayGridMonth',
    headerToolbar: {
      left:   'prev,next today',
      center: 'title',
      right:  'dayGridMonth,timeGridWeek,listMonth',
    },
    buttonText: { today:'Hoje', month:'Mês', week:'Semana', list:'Lista' },
    height:    '100%',
    firstDay:  0,
    navLinks:  true,
    editable:  false,

    events: function(fetchInfo, successCb, failureCb) {
      fetch(`/api/agenda/eventos?start=${fetchInfo.startStr}&end=${fetchInfo.endStr}`)
        .then(r => r.json()).then(successCb).catch(failureCb);
    },

    // Clicar num dia vazio → abre modal novo (só admin)
    dateClick: function(info) {
      if (!IS_ADMIN) return;
      abrirModalNovo(info.dateStr);
    },

    // Clicar num evento → popup de detalhes
    eventClick: function(info) {
      info.jsEvent.stopPropagation();
      mostrarPopup(info.event, info.jsEvent);
    },

    eventDidMount: function(info) {
      const bg = info.event.backgroundColor || info.event.extendedProps.cor || info.event.borderColor || '#64748b';
      const border = info.event.borderColor || bg;
      const text = info.event.textColor || '#ffffff';
      info.el.style.setProperty('background-color', bg, 'important');
      info.el.style.setProperty('border-color', border, 'important');
      info.el.style.setProperty('color', text, 'important');
      info.el.querySelectorAll('.fc-event-main,.fc-event-title,.fc-event-time').forEach(node => {
        node.style.setProperty('color', text, 'important');
      });
      const orig = info.event.extendedProps.origem;
      if (orig === 'auto') {
        info.el.style.opacity = '0.85';
        info.el.title = info.event.extendedProps.descricao;
      }
    },
  });
  calendario.render();

  // Fechar popup clicando fora
  document.addEventListener('click', e => {
    const popup = document.getElementById('popup-detalhe');
    if (popup.style.display !== 'none' && !popup.contains(e.target)) fecharPopup();
  });
});

// ── Popup de detalhes ─────────────────────────────────────────────────────────
function mostrarPopup(event, jsEvent) {
  const props = event.extendedProps;
  const popup = document.getElementById('popup-detalhe');

  document.getElementById('popup-titulo').textContent = event.title;

  let html = '';
  const cor = event.backgroundColor || '#64748b';

  // Badge tipo
  html += `<div style="margin-bottom:8px;">
    <span style="background:${cor}22;color:${cor};border:1px solid ${cor}55;
      border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700;">
      ${props.tipoLabel || props.tipo}
    </span>
    ${props.origem === 'auto' ? '<span style="font-size:10px;color:var(--text3);margin-left:6px;">automático</span>' : ''}
  </div>`;

  // Datas
  if (event.allDay) {
    const s = fmtData(event.startStr);
    html += `<div>📅 ${s}</div>`;
  } else {
    html += `<div>📅 ${fmtDT(event.startStr)}${event.end ? ' → ' + fmtDT(event.endStr) : ''}</div>`;
  }

  // Conteúdo específico
  if (props.origem === 'auto') {
    html += `<div style="margin-top:6px;padding:8px;background:var(--surface2);border-radius:6px;font-size:12px;">`;
    if (props.resumo) {
      props.resumo.split(' | ').forEach(p => { html += `<div>${escHtml(p)}</div>`; });
    }
    html += `</div>`;
    if (props.localidades && props.localidades.length > 0) {
      html += `<div style="margin-top:8px;">`;
      html += `<div style="font-size:11px;font-weight:700;color:var(--text3);margin-bottom:4px;">📍 LOCALIDADES</div>`;
      props.localidades.forEach(loc => {
        html += `<div style="font-size:12px;padding:2px 0;">${escHtml(loc.trim())}</div>`;
      });
      html += `</div>`;
    }
    if (props.agentes && props.agentes !== '—') {
      html += `<div style="margin-top:8px;">`;
      html += `<div style="font-size:11px;font-weight:700;color:var(--text3);margin-bottom:4px;">👤 AGENTES PRESENTES</div>`;
      props.agentes.split(', ').forEach(ag => {
        html += `<div style="font-size:12px;padding:2px 0;">${escHtml(ag.trim())}</div>`;
      });
      html += `</div>`;
    }
  } else {
    if (props.descricao) html += `<div style="margin-top:6px;white-space:pre-wrap;">${escHtml(props.descricao)}</div>`;
    if (props.lembrete_min > 0) {
      const labels = {0:'—',15:'15 min',30:'30 min',60:'1 hora',120:'2 horas',1440:'1 dia'};
      html += `<div style="margin-top:4px;color:var(--text3);font-size:11px;">🔔 Lembrete: ${labels[props.lembrete_min] || props.lembrete_min + ' min'} antes</div>`;
    }
    if (props.criado_por) html += `<div style="margin-top:4px;color:var(--text3);font-size:11px;">Criado por: ${escHtml(props.criado_por)}</div>`;
  }

  document.getElementById('popup-corpo').innerHTML = html;

  // Ações (só admin, só eventos manuais)
  const acoes = document.getElementById('popup-acoes');
  acoes.innerHTML = '';
  if (IS_ADMIN && props.origem === 'manual') {
    const btnEdit = document.createElement('button');
    btnEdit.className = 'btn btn-ghost btn-sm';
    btnEdit.textContent = 'Editar';
    btnEdit.onclick = () => { fecharPopup(); abrirModalEditar(event); };
    acoes.appendChild(btnEdit);
  }

  // Posicionar popup perto do clique
  popup.style.display = 'block';
  const vw = window.innerWidth, vh = window.innerHeight;
  let x = jsEvent.clientX + 12, y = jsEvent.clientY + 12;
  setTimeout(() => {
    const pw = popup.offsetWidth, ph = popup.offsetHeight;
    if (x + pw > vw - 10) x = jsEvent.clientX - pw - 12;
    if (y + ph > vh - 10) y = jsEvent.clientY - ph - 12;
    popup.style.left = Math.max(6, x) + 'px';
    popup.style.top  = Math.max(6, y) + 'px';
  }, 0);
}

function fecharPopup() {
  document.getElementById('popup-detalhe').style.display = 'none';
}

// ── Modal criar/editar ────────────────────────────────────────────────────────
function abrirModalNovo(dataStr) {
  editandoId = null;
  document.getElementById('modal-titulo-h').textContent = 'Novo evento';
  document.getElementById('btn-excluir').style.display  = 'none';
  limparModal();
  if (dataStr) {
    document.getElementById('ev-inicio-dia').value = dataStr;
    document.getElementById('ev-inicio').value     = dataStr + 'T08:00';
  }
  mostrarModal();
}

function abrirModalEditar(event) {
  editandoId = event.extendedProps.id_evento;
  document.getElementById('modal-titulo-h').textContent = 'Editar evento';
  document.getElementById('btn-excluir').style.display  = 'inline-flex';
  limparModal();

  document.getElementById('ev-titulo').value    = event.title;
  document.getElementById('ev-tipo').value      = event.extendedProps.tipo || 'outro';
  document.getElementById('ev-descricao').value = event.extendedProps.descricao || '';
  document.getElementById('ev-lembrete').value  = event.extendedProps.lembrete_min || 60;

  const allDay = event.allDay;
  document.getElementById('ev-dia-inteiro').checked = allDay;
  toggleDiaInteiro();

  if (allDay) {
    document.getElementById('ev-inicio-dia').value = event.startStr;
    document.getElementById('ev-fim-dia').value    = event.endStr ? event.endStr.slice(0,10) : '';
  } else {
    document.getElementById('ev-inicio').value = event.startStr ? event.startStr.slice(0,16) : '';
    document.getElementById('ev-fim').value    = event.endStr   ? event.endStr.slice(0,16)   : '';
  }

  mostrarModal();
}

function mostrarModal() {
  const m = document.getElementById('modal-evento');
  m.style.display = 'flex';
  document.getElementById('ev-titulo').focus();
}

function fecharModal() {
  document.getElementById('modal-evento').style.display = 'none';
  editandoId = null;
}

function limparModal() {
  ['ev-titulo','ev-descricao','ev-inicio','ev-fim','ev-inicio-dia','ev-fim-dia'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('ev-tipo').value      = 'reuniao';
  document.getElementById('ev-lembrete').value  = '60';
  document.getElementById('ev-dia-inteiro').checked = false;
  toggleDiaInteiro();
}

function toggleDiaInteiro() {
  const allDay = document.getElementById('ev-dia-inteiro').checked;
  document.getElementById('bloco-datas').style.display     = allDay ? 'none' : 'grid';
  document.getElementById('bloco-datas-dia').style.display = allDay ? 'grid' : 'none';
}

function atualizarCor() {
  // apenas para uso futuro — cor é definida no backend por tipo
}

async function salvarEvento() {
  const titulo    = document.getElementById('ev-titulo').value.trim();
  const tipo      = document.getElementById('ev-tipo').value;
  const allDay    = document.getElementById('ev-dia-inteiro').checked;
  const lembrete  = document.getElementById('ev-lembrete').value;
  const descricao = document.getElementById('ev-descricao').value.trim();

  let inicio, fim;
  if (allDay) {
    inicio = document.getElementById('ev-inicio-dia').value;
    fim    = document.getElementById('ev-fim-dia').value || null;
  } else {
    inicio = document.getElementById('ev-inicio').value;
    fim    = document.getElementById('ev-fim').value || null;
  }

  if (!titulo) { toast('Informe o título do evento.', 'error'); return; }
  if (!inicio) { toast('Informe a data de início.',   'error'); return; }

  const payload = { titulo, tipo, data_inicio: inicio, data_fim: fim,
                    dia_inteiro: allDay, lembrete_min: parseInt(lembrete),
                    descricao: descricao || null };

  const url    = editandoId ? `/api/agenda/eventos/${editandoId}` : '/api/agenda/eventos';
  const method = editandoId ? 'PUT' : 'POST';

  try {
    const r = await fetch(url, {
      method,
      headers: {'Content-Type':'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if (!r.ok) { toast(d.erro || 'Erro ao salvar.', 'error'); return; }
    fecharModal();
    calendario.refetchEvents();
    toast(editandoId ? 'Evento atualizado!' : 'Evento criado!', 'success');
  } catch(e) {
    toast('Erro de comunicação.', 'error');
  }
}

async function excluirEvento() {
  if (!editandoId) return;
  if (!confirm('Excluir este evento permanentemente?')) return;
  try {
    await fetch(`/api/agenda/eventos/${editandoId}`, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrf() }
    });
    fecharModal();
    calendario.refetchEvents();
    toast('Evento excluído.', 'success');
  } catch(e) {
    toast('Erro ao excluir.', 'error');
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtData(iso) {
  if (!iso) return '';
  const [y,m,d] = iso.split('T')[0].split('-');
  return `${d}/${m}/${y}`;
}
function fmtDT(iso) {
  if (!iso) return '';
  const dt = new Date(iso);
  const p = n => String(n).padStart(2,'0');
  return `${p(dt.getDate())}/${p(dt.getMonth()+1)} ${p(dt.getHours())}:${p(dt.getMinutes())}`;
}
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Fechar modal clicando no overlay
document.getElementById('modal-evento').addEventListener('click', function(e) {
  if (e.target === this) fecharModal();
});

document.getElementById('btn-agenda-novo')?.addEventListener('click', abrirModalNovo);
document.getElementById('btn-agenda-fechar-modal')?.addEventListener('click', fecharModal);
document.getElementById('btn-agenda-cancelar')?.addEventListener('click', fecharModal);
document.getElementById('btn-agenda-salvar')?.addEventListener('click', salvarEvento);
document.getElementById('btn-excluir')?.addEventListener('click', excluirEvento);
document.getElementById('btn-agenda-fechar-popup')?.addEventListener('click', fecharPopup);
document.getElementById('ev-tipo')?.addEventListener('change', atualizarCor);
document.getElementById('ev-dia-inteiro')?.addEventListener('change', toggleDiaInteiro);

