// ── Estado ────────────────────────────────────────────────────────────────────
let calendario;
let editandoId = null;
let agendaFiltro = '';
let agendaBuscaTimer = null;
const AGENDA_CONFIG = JSON.parse(document.getElementById('agenda-config').textContent || '{}');
const IS_ADMIN = Boolean(AGENDA_CONFIG.is_admin);

const TIPO_COR = JSON.parse(document.getElementById('agenda-tipo-cores').textContent || '{}');
const TIPO_LABEL = JSON.parse(document.getElementById('agenda-form-labels').textContent || '{}');

function agendaEpiYearStart(year) {
  const jan4 = new Date(year, 0, 4);
  const start = new Date(year, 0, 4 - jan4.getDay());
  start.setHours(0, 0, 0, 0);
  return start;
}

function agendaEpiWeek(date) {
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  let year = day.getFullYear();
  let start = agendaEpiYearStart(year);
  const nextStart = agendaEpiYearStart(year + 1);
  if (day < start) {
    year -= 1;
    start = agendaEpiYearStart(year);
  } else if (day >= nextStart) {
    year += 1;
    start = nextStart;
  }
  return {
    year,
    week: Math.floor((day - start) / (7 * 24 * 60 * 60 * 1000)) + 1,
  };
}

// ── Inicializar FullCalendar ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const campoAnoBusca = document.getElementById('agenda-busca-ano');
  if (campoAnoBusca && !campoAnoBusca.value) campoAnoBusca.value = String(new Date().getFullYear());
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
    weekNumbers: true,
    weekText: 'SE',
    weekNumberCalculation: date => agendaEpiWeek(date).week,
    weekNumberContent: arg => {
      const epi = agendaEpiWeek(arg.date);
      const week = String(epi.week).padStart(2, '0');
      return { html: `<span title="Semana epidemiológica ${week} de ${epi.year}">SE ${week}/${epi.year}</span>` };
    },
    navLinks:  true,
    editable:  false,
    eventTimeFormat: {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    },

    events: function(fetchInfo, successCb, failureCb) {
      fetch(`/api/agenda/eventos?start=${fetchInfo.startStr}&end=${fetchInfo.endStr}`)
        .then(r => r.json())
        .then(eventos => successCb(filtrarEventosAgenda(eventos)))
        .catch(failureCb);
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
        info.el.style.setProperty('border-left', `4px solid ${border}`, 'important');
        info.el.title = `${info.event.extendedProps.fonteLabel || 'Atividade importada'}: ${info.event.title}`;
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
    ${props.origem === 'auto' ? `<span style="font-size:10px;color:var(--text3);margin-left:6px;">automático · ${escHtml(props.fonteLabel || 'importado')}</span>` : ''}
  </div>`;

  // Datas
  if (event.allDay) {
    html += `<div>📅 ${fmtDataRange(event.startStr, event.endStr)}</div>`;
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
    if (props.descricao) {
      html += `<div style="margin-top:6px;max-height:120px;overflow-y:auto;white-space:pre-wrap;padding-right:6px;">${escHtml(props.descricao)}</div>`;
    }
    if (props.lembrete_min > 0) {
      const labels = {0:'—',15:'15 min',30:'30 min',60:'1 hora',120:'2 horas',1440:'1 dia'};
      html += `<div style="margin-top:4px;color:var(--text3);font-size:11px;">🔔 Lembrete: ${labels[props.lembrete_min] || props.lembrete_min + ' min'} antes</div>`;
    }
    if (props.recorrencia && props.recorrencia !== 'nenhuma') {
      html += `<div style="margin-top:4px;color:var(--text3);font-size:11px;">Repete: ${escHtml(props.recorrenciaLabel || props.recorrencia)}${props.recorrencia_fim ? ' até ' + fmtData(props.recorrencia_fim) : ''}</div>`;
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
  const props = event.extendedProps;
  editandoId = event.extendedProps.id_evento;
  document.getElementById('modal-titulo-h').textContent = 'Editar evento';
  document.getElementById('btn-excluir').style.display  = 'inline-flex';
  limparModal();

  document.getElementById('ev-titulo').value    = event.title;
  document.getElementById('ev-tipo').value      = props.tipo || 'outro';
  document.getElementById('ev-descricao').value = props.descricao || '';
  document.getElementById('ev-lembrete').value  = props.lembrete_min || 60;
  document.getElementById('ev-recorrencia').value = props.recorrencia || 'nenhuma';
  document.getElementById('ev-recorrencia-fim').value = props.recorrencia_fim || '';
  toggleRecorrencia();

  const allDay = event.allDay;
  document.getElementById('ev-dia-inteiro').checked = allDay;
  toggleDiaInteiro();

  if (allDay) {
    document.getElementById('ev-inicio-dia').value = (props.data_inicio || event.startStr || '').slice(0,10);
    document.getElementById('ev-fim-dia').value    = (props.data_fim || '').slice(0,10);
  } else {
    document.getElementById('ev-inicio').value = props.data_inicio ? props.data_inicio.slice(0,16) : (event.startStr ? event.startStr.slice(0,16) : '');
    document.getElementById('ev-fim').value    = props.data_fim ? props.data_fim.slice(0,16) : '';
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
  ['ev-titulo','ev-descricao','ev-inicio','ev-fim','ev-inicio-dia','ev-fim-dia','ev-recorrencia-fim'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('ev-tipo').value      = 'reuniao';
  document.getElementById('ev-lembrete').value  = '60';
  document.getElementById('ev-recorrencia').value = 'nenhuma';
  document.getElementById('ev-dia-inteiro').checked = false;
  toggleDiaInteiro();
  toggleRecorrencia();
}

function toggleDiaInteiro() {
  const allDay = document.getElementById('ev-dia-inteiro').checked;
  document.getElementById('bloco-datas').style.display     = allDay ? 'none' : 'grid';
  document.getElementById('bloco-datas-dia').style.display = allDay ? 'grid' : 'none';
}

function atualizarCor() {
  // apenas para uso futuro — cor é definida no backend por tipo
}

function atualizarBuscaAgenda() {
  agendaFiltro = document.getElementById('agenda-busca')?.value || '';
  if (agendaBuscaTimer) clearTimeout(agendaBuscaTimer);
  agendaBuscaTimer = setTimeout(() => {
    calendario?.refetchEvents();
    if (termosBuscaAgenda().length) {
      buscarAgendaNoAno();
    } else {
      limparResultadosAno();
    }
  }, 220);
}

function limparBuscaAgenda() {
  const campo = document.getElementById('agenda-busca');
  if (!campo) return;
  campo.value = '';
  agendaFiltro = '';
  if (agendaBuscaTimer) clearTimeout(agendaBuscaTimer);
  calendario?.refetchEvents();
  campo.focus();
  limparResultadosAno();
}

function normalizarBusca(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

function termosBuscaAgenda() {
  return normalizarBusca(agendaFiltro).split(/\s+/).filter(Boolean);
}

function juntarCampoBusca(value) {
  if (Array.isArray(value)) return value.join(' ');
  return value || '';
}

function textoBuscaEvento(evento) {
  const props = evento.extendedProps || {};
  const campos = [
    evento.title,
    evento.start,
    evento.end,
    fmtData(evento.start),
    fmtData(evento.end),
    props.tipo,
    props.tipoLabel,
    props.descricao,
    props.criado_por,
    props.recorrencia,
    props.recorrenciaLabel,
    props.recorrencia_fim,
    props.fonte,
    props.fonteLabel,
    props.resumo,
    props.total,
    juntarCampoBusca(props.localidades),
    props.agentes,
    props.data_inicio,
    props.data_fim,
  ];
  return normalizarBusca(campos.filter(v => v !== null && v !== undefined).join(' '));
}

function atualizarResumoBusca(total, exibidos, ativa) {
  const el = document.getElementById('agenda-busca-status');
  if (!el) return;
  if (!ativa) {
    el.textContent = total ? `${total} evento${total === 1 ? '' : 's'}` : '';
    return;
  }
  el.textContent = `${exibidos} de ${total} evento${total === 1 ? '' : 's'}`;
}

function filtrarEventosAgenda(eventos) {
  const termos = termosBuscaAgenda();
  if (!termos.length) {
    atualizarResumoBusca(eventos.length, eventos.length, false);
    return eventos;
  }
  const filtrados = filtrarEventosPorTermos(eventos, termos);
  atualizarResumoBusca(eventos.length, filtrados.length, true);
  return filtrados;
}

function filtrarEventosPorTermos(eventos, termos) {
  if (!termos.length) return eventos;
  return eventos.filter(evento => {
    const texto = textoBuscaEvento(evento);
    return termos.every(termo => texto.includes(termo));
  });
}

function anoBuscaAgenda() {
  const campo = document.getElementById('agenda-busca-ano');
  const dataAtual = calendario && typeof calendario.getDate === 'function' ? calendario.getDate() : null;
  const fallback = dataAtual ? dataAtual.getFullYear() : new Date().getFullYear();
  const ano = parseInt(campo?.value || fallback, 10);
  if (!Number.isFinite(ano) || ano < 2020 || ano > 2099) return fallback;
  return ano;
}

function dataOrdenacaoEvento(evento) {
  return (evento.start || evento.extendedProps?.data_inicio || '').slice(0, 16);
}

function dataInicioEvento(evento) {
  return (evento.extendedProps?.data_inicio || evento.start || '').slice(0, 10);
}

function resumoEventoResultado(evento) {
  const props = evento.extendedProps || {};
  const partes = [
    props.tipoLabel || props.fonteLabel || props.tipo || props.fonte,
    props.origem === 'auto' ? 'automático' : '',
    props.recorrencia && props.recorrencia !== 'nenhuma' ? `repete ${props.recorrenciaLabel || props.recorrencia}` : '',
  ].filter(Boolean);
  return partes.join(' · ');
}

function limparResultadosAno() {
  const box = document.getElementById('agenda-resultados-ano');
  if (!box) return;
  box.hidden = false;
  box.innerHTML = '<div class="agenda-year-results-header"><span>Resultados no ano inteiro</span><span>Digite uma palavra-chave e escolha o ano.</span></div>';
}

function renderResultadosAno(eventos, ano, termos) {
  const box = document.getElementById('agenda-resultados-ano');
  if (!box) return;
  const busca = termos.join(' ');
  if (!termos.length) {
    box.hidden = false;
    box.innerHTML = '<div class="agenda-year-results-header"><span>Resultados no ano inteiro</span><span>Digite uma palavra-chave e escolha o ano.</span></div>';
    return;
  }
  const total = eventos.length;
  const header = `<div class="agenda-year-results-header"><span>${total} resultado${total === 1 ? '' : 's'} em ${ano}${busca ? ` para "${escHtml(busca)}"` : ''}</span></div>`;
  if (!eventos.length) {
    box.hidden = false;
    box.innerHTML = header + '<div style="padding:12px;color:var(--text3);font-size:12px;">Nenhum evento encontrado nesse ano.</div>';
    return;
  }
  const itens = eventos.map(evento => {
    const data = dataInicioEvento(evento);
    const descricao = evento.extendedProps?.descricao || evento.extendedProps?.resumo || '';
    return `<button type="button" class="agenda-year-result" data-agenda-date="${escHtml(data)}">
      <span class="agenda-year-result-date">${fmtData(data)}</span>
      <span>
        <span class="agenda-year-result-title">${escHtml(evento.title || 'Evento')}</span>
        <span class="agenda-year-result-meta">${escHtml(resumoEventoResultado(evento))}</span>
        ${descricao ? `<span class="agenda-year-result-meta">${escHtml(String(descricao).slice(0, 140))}</span>` : ''}
      </span>
    </button>`;
  }).join('');
  box.hidden = false;
  box.innerHTML = header + `<div class="agenda-year-results-list">${itens}</div>`;
}

async function buscarAgendaNoAno() {
  const ano = anoBuscaAgenda();
  const campoAno = document.getElementById('agenda-busca-ano');
  if (campoAno) campoAno.value = String(ano);
  agendaFiltro = document.getElementById('agenda-busca')?.value || '';
  const termos = termosBuscaAgenda();
  const box = document.getElementById('agenda-resultados-ano');
  if (box) {
    box.hidden = false;
    box.innerHTML = '<div class="agenda-year-results-header">Pesquisando...</div>';
  }
  try {
    const r = await fetch(`/api/agenda/eventos?start=${ano}-01-01&end=${ano}-12-31`);
    const eventos = await r.json();
    if (!r.ok) {
      renderResultadosAno([], ano, termos);
      toast('Erro ao pesquisar eventos do ano.', 'error');
      return;
    }
    const filtrados = filtrarEventosPorTermos(eventos, termos)
      .sort((a, b) => dataOrdenacaoEvento(a).localeCompare(dataOrdenacaoEvento(b)));
    renderResultadosAno(filtrados, ano, termos);
  } catch(e) {
    if (box) box.innerHTML = '<div class="agenda-year-results-header">Erro ao pesquisar eventos do ano.</div>';
    toast('Erro de comunicação.', 'error');
  }
}

function abrirResultadoAno(event) {
  const botao = event.target.closest?.('.agenda-year-result');
  if (!botao) return;
  const data = botao.getAttribute('data-agenda-date');
  if (!data) return;
  calendario?.gotoDate(data);
  calendario?.refetchEvents();
}

function buscarAgendaNoAnoComEnter(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    buscarAgendaNoAno();
  }
}

function atualizarAnoBuscaAgenda() {
  if (termosBuscaAgenda().length) buscarAgendaNoAno();
}

function toggleRecorrencia() {
  const recorrencia = document.getElementById('ev-recorrencia').value;
  const blocoFim = document.getElementById('bloco-recorrencia-fim');
  const fim = document.getElementById('ev-recorrencia-fim');
  const ativa = recorrencia !== 'nenhuma';
  blocoFim.style.opacity = ativa ? '1' : '.45';
  fim.disabled = !ativa;
  if (!ativa) fim.value = '';
}

async function salvarEvento() {
  const titulo    = document.getElementById('ev-titulo').value.trim();
  const tipo      = document.getElementById('ev-tipo').value;
  const allDay    = document.getElementById('ev-dia-inteiro').checked;
  const lembrete  = document.getElementById('ev-lembrete').value;
  const descricao = document.getElementById('ev-descricao').value.trim();
  const recorrencia = document.getElementById('ev-recorrencia').value;
  const recorrenciaFim = document.getElementById('ev-recorrencia-fim').value || null;

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
                    descricao: descricao || null,
                    recorrencia,
                    recorrencia_fim: recorrencia === 'nenhuma' ? null : recorrenciaFim };

  const url    = editandoId ? `/api/agenda/eventos/${editandoId}` : '/api/agenda/eventos';
  const method = editandoId ? 'PUT' : 'POST';

  try {
    const r = await fetch(url, {
      method,
      headers: {'Content-Type':'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify(payload)
    });
    const texto = await r.text();
    let d = {};
    try {
      d = texto ? JSON.parse(texto) : {};
    } catch(e) {
      d = {};
    }
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
function fmtDataRange(startIso, endIso) {
  const inicio = fmtData(startIso);
  if (!endIso) return inicio;
  const fim = new Date(endIso.slice(0,10) + 'T00:00:00');
  fim.setDate(fim.getDate() - 1);
  const p = n => String(n).padStart(2,'0');
  const fimTxt = `${p(fim.getDate())}/${p(fim.getMonth()+1)}/${fim.getFullYear()}`;
  return fimTxt && fimTxt !== inicio ? `${inicio} até ${fimTxt}` : inicio;
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
document.getElementById('agenda-busca')?.addEventListener('input', atualizarBuscaAgenda);
document.getElementById('agenda-busca')?.addEventListener('keydown', buscarAgendaNoAnoComEnter);
document.getElementById('btn-agenda-limpar-busca')?.addEventListener('click', limparBuscaAgenda);
document.getElementById('btn-agenda-buscar-ano')?.addEventListener('click', buscarAgendaNoAno);
document.getElementById('agenda-busca-ano')?.addEventListener('change', atualizarAnoBuscaAgenda);
document.getElementById('agenda-busca-ano')?.addEventListener('keydown', buscarAgendaNoAnoComEnter);
document.getElementById('agenda-resultados-ano')?.addEventListener('click', abrirResultadoAno);
document.getElementById('ev-tipo')?.addEventListener('change', atualizarCor);
document.getElementById('ev-dia-inteiro')?.addEventListener('change', toggleDiaInteiro);
document.getElementById('ev-recorrencia')?.addEventListener('change', toggleRecorrencia);
