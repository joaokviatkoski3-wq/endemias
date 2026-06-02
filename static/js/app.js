/* ═══════════════════════════
   SIDEBAR MOBILE
═══════════════════════════ */
function openSidebar()  { document.getElementById('sidebar-mobile').classList.add('open'); document.getElementById('overlay').classList.add('open'); }
function closeSidebar() { document.getElementById('sidebar-mobile').classList.remove('open'); document.getElementById('overlay').classList.remove('open'); }

function setDesktopNav(open) {
  const shell = document.getElementById('app-shell');
  const btn = document.getElementById('sidebarToggle');
  if (!shell) return;
  shell.classList.toggle('sidebar-open', open);
  if (btn) {
    btn.classList.toggle('active', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.setAttribute('aria-label', open ? 'Ocultar navegacao' : 'Mostrar navegacao');
    btn.setAttribute('title', open ? 'Ocultar navegacao' : 'Mostrar navegacao');
  }
}

function toggleDesktopNav() {
  const shell = document.getElementById('app-shell');
  const open = !(shell && shell.classList.contains('sidebar-open'));
  setDesktopNav(open);
  localStorage.setItem('desktop_nav_open', open ? '1' : '0');
}
window.toggleDesktopNav = toggleDesktopNav;

document.addEventListener('DOMContentLoaded', () => {
  setDesktopNav(localStorage.getItem('desktop_nav_open') === '1');

  const overlay = document.getElementById('overlay');
  const mobileClose = document.getElementById('sidebarMobileClose');
  const mobileOpen = document.getElementById('sidebarMobileOpen');
  const desktopToggle = document.getElementById('sidebarToggle');
  const userToggle = document.getElementById('userMenuToggle');
  const themeToggle = document.getElementById('btnDark');

  if (overlay) overlay.addEventListener('click', closeSidebar);
  if (mobileClose) mobileClose.addEventListener('click', closeSidebar);
  if (mobileOpen) mobileOpen.addEventListener('click', openSidebar);
  if (desktopToggle) desktopToggle.addEventListener('click', toggleDesktopNav);
  if (userToggle) userToggle.addEventListener('click', toggleUserMenu);
  if (themeToggle) themeToggle.addEventListener('click', toggleDark);

  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      const message = form.getAttribute('data-confirm');
      if (message && !window.confirm(message)) event.preventDefault();
    });
  });
});

function toggleUserMenu() {
  const m = document.getElementById('user-menu');
  if (!m) return;
  m.style.display = m.style.display === 'none' ? 'block' : 'none';
}
document.addEventListener('click', e => {
  const wrap = document.getElementById('user-menu-wrap');
  if (wrap && !wrap.contains(e.target)) {
    const m = document.getElementById('user-menu');
    if (m) m.style.display = 'none';
  }
});

/* ═══════════════════════════
   RELÓGIO
═══════════════════════════ */
function tick() {
  const n = new Date();
  const d = n.toLocaleDateString('pt-BR',{weekday:'short',day:'2-digit',month:'short'});
  const t = n.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  document.getElementById('clock').textContent = d + ' · ' + t;
}
tick(); setInterval(tick, 30000);

/* ═══════════════════════════
   TEMA ESCURO
═══════════════════════════ */
function getSavedTheme() {
  const theme = localStorage.getItem('theme');
  if (theme === 'light' || theme === 'dark') return theme;
  return localStorage.getItem('dark') === '1' ? 'dark' : 'light';
}

let currentTheme = getSavedTheme();
let darkMode = currentTheme === 'dark';
function applyTheme() {
  darkMode = currentTheme === 'dark';
  document.documentElement.setAttribute('data-theme', currentTheme);
  localStorage.setItem('theme', currentTheme);
  localStorage.setItem('dark', darkMode ? '1' : '0');
  document.getElementById('btnDark').innerHTML = darkMode ? '<img src="/static/icons/sol.svg" alt="☀" class="icon-svg">️' : '<img src="/static/icons/lua.svg" alt="🌙" class="icon-svg">';
  // Atualiza Chart.js existente
  refreshChartsTheme();
}
function toggleDark() {
  currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
  applyTheme();
}
window.toggleDark = toggleDark;
applyTheme();

function refreshChartsTheme() {
  const gridColor = darkMode ? '#253552' : '#dde4f5';
  const textColor = darkMode ? '#8a9fc0' : '#4a5878';
  document.querySelectorAll('canvas').forEach(el => {
    if(el._chart) {
      const c = el._chart;
      if(c.options.scales) {
        Object.values(c.options.scales).forEach(s => {
          if(s.ticks) s.ticks.color = textColor;
          if(s.grid)  s.grid.color  = gridColor;
        });
      }
      if(c.options.plugins?.legend?.labels) {
        c.options.plugins.legend.labels.color = textColor;
      }
      c.update('none');
    }
  });
}

/* ═══════════════════════════
   FILTROS COLLAPSIBLE
═══════════════════════════ */
function toggleFilter(id) {
  const body = document.getElementById(id);
  const tog  = document.querySelector(`[data-target="${id}"] .filter-toggle`);
  if(!body) return;
  const open = body.classList.toggle('open');
  if(tog) tog.classList.toggle('open', open);
  localStorage.setItem('filter_' + id, open ? '1' : '0');
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.filter-body').forEach(b => {
    const saved = localStorage.getItem('filter_' + b.id);
    if(saved !== '0') { // default aberto
      b.classList.add('open');
      const tog = document.querySelector(`[data-target="${b.id}"] .filter-toggle`);
      if(tog) tog.classList.add('open');
    }
  });
});

/* ═══════════════════════════
   TABS
═══════════════════════════ */
function openTab(id, btn) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}

/* ═══════════════════════════
   TOAST
═══════════════════════════ */
function toast(msg, type='info', dur=3000) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icon = type==='success'?'<img src="/static/icons/check.svg" alt="✓" class="icon-svg">':type==='error'?'<img src="/static/icons/fechar.svg" alt="✕" class="icon-svg">':'ℹ';
  el.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  document.getElementById('toast-area').appendChild(el);
  setTimeout(() => el.style.opacity='0', dur - 300);
  setTimeout(() => el.remove(), dur);
}

/* ═══════════════════════════
   CHART.JS DEFAULTS
═══════════════════════════ */
Chart.defaults.font.family = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
Chart.defaults.font.size   = 11;
Chart.defaults.color       = '#4a5878';
Chart.defaults.plugins.legend.labels.boxWidth = 10;
Chart.defaults.plugins.legend.labels.padding  = 12;
Chart.defaults.plugins.tooltip.padding        = 10;
Chart.defaults.plugins.tooltip.cornerRadius   = 6;
Chart.defaults.plugins.tooltip.boxPadding     = 4;

const PAL = ['#1a4fba','#22c55e','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#10b981','#f97316','#e11d48','#7c3aed'];
const PAL2 = ['#3b82f6','#a3e635','#fbbf24','#f87171','#a78bfa','#38bdf8','#34d399','#fb923c','#fb7185','#c084fc'];

function mkChart(id, cfg) {
  const el = document.getElementById(id);
  if(!el) return null;
  if(el._chart) el._chart.destroy();
  cfg.options = cfg.options || {};
  cfg.options.responsive = true;
  cfg.options.maintainAspectRatio = false;

  // ── Datalabels automáticos por tipo ──────────────────────────────────
  const tipo = cfg.type;
  const tc = darkMode ? '#c8d8f0' : '#1a2540';
  const tcLight = darkMode ? '#8a9fc0' : '#64748b';

  cfg.options.plugins = cfg.options.plugins || {};
  const dl = cfg.options.plugins.datalabels || {};

  if (tipo === 'bar' || tipo === 'horizontalBar') {
    cfg.options.plugins.datalabels = Object.assign({
      anchor: 'end', align: 'end', offset: 2,
      color: tc, font: { size: 10, weight: '600' },
      formatter: v => v > 0 ? fmtNum(v) : '',
      clip: false,
    }, dl);
  } else if (tipo === 'doughnut' || tipo === 'pie') {
    cfg.options.plugins.datalabels = Object.assign({
      color: '#fff', font: { size: 11, weight: '700' },
      formatter: (v, ctx) => {
        const total = ctx.chart.data.datasets[0].data.reduce((a,b)=>a+b,0);
        const pct = total > 0 ? Math.round(v/total*100) : 0;
        return pct >= 5 ? `${fmtNum(v)}\n${pct}%` : '';
      },
      textAlign: 'center',
    }, dl);
  } else if (tipo === 'line') {
    cfg.options.plugins.datalabels = Object.assign({
      anchor: 'top', align: 'top', offset: 3,
      color: tc, font: { size: 9, weight: '600' },
      formatter: v => v > 0 ? fmtNum(v) : '',
      backgroundColor: darkMode ? 'rgba(20,40,80,.6)' : 'rgba(255,255,255,.75)',
      borderRadius: 3, padding: { left: 3, right: 3, top: 1, bottom: 1 },
      display: ctx => ctx.dataset.data.length <= 24,  // só mostra se não for muito denso
    }, dl);
  } else {
    cfg.options.plugins.datalabels = Object.assign({ display: false }, dl);
  }

  Chart.register(ChartDataLabels);
  const c = new Chart(el, cfg);
  el._chart = c;
  return c;
}

function eixos(opts={}) {
  const gc = darkMode ? '#253552' : '#dde4f5';
  const tc = darkMode ? '#8a9fc0' : '#4a5878';
  return {
    x: { grid:{color:gc,drawBorder:false}, ticks:{color:tc,maxRotation:30}, ...(opts.x||{}) },
    y: { grid:{color:gc,drawBorder:false}, ticks:{color:tc}, beginAtZero:true, ...(opts.y||{}) },
  };
}

/* ═══════════════════════════
   UTILITÁRIOS GERAIS
═══════════════════════════ */
/* ═══════════════════════════
   FILTROS PERSISTENTES
═══════════════════════════ */
const _FILTROS_KEY = 'end_filtros_v3';
function salvarFiltros(pagina, dados) {
  try {
    const all = JSON.parse(sessionStorage.getItem(_FILTROS_KEY) || '{}');
    all[pagina] = dados;
    sessionStorage.setItem(_FILTROS_KEY, JSON.stringify(all));
  } catch(e) {}
}
function carregarFiltros(pagina) {
  try {
    const all = JSON.parse(sessionStorage.getItem(_FILTROS_KEY) || '{}');
    return all[pagina] || null;
  } catch(e) { return null; }
}
function limparFiltrosPagina(pagina) {
  try {
    const all = JSON.parse(sessionStorage.getItem(_FILTROS_KEY) || '{}');
    delete all[pagina];
    sessionStorage.setItem(_FILTROS_KEY, JSON.stringify(all));
  } catch(e) {}
}

function fmtNum(n) {
  if(n===null||n===undefined) return '—';
  return Number(n).toLocaleString('pt-BR');
}
function fmtDate(d) {
  if(!d) return '—';
  const p = String(d).substring(0,10).split('-');
  if(p.length<3) return d;
  return `${p[2]}/${p[1]}/${p[0]}`;
}
function fmtPct(v) { return (v||0).toFixed(1) + '%'; }

function badgeStatus(st) {
  const map = {
    'pendente':               ['badge-pendente',  '⏳ pendente'],
    'impressa':               ['badge-impressa',  '<img src="/static/icons/imprimir.svg" alt="🖨" class="icon-svg">️ impressa'],
    'entregue':               ['badge-entregue',  '<img src="/static/icons/check.svg" alt="✓" class="icon-svg"> entregue'],
    'morador não localizado': ['badge-naoloc',    '<img src="/static/icons/alerta.svg" alt="⚠" class="icon-svg"> não localizado'],
    'dados inconsistentes':   ['badge-inconsist', '<img src="/static/icons/alerta.svg" alt="⚠" class="icon-svg"> inconsistente'],
    'arquivada':              ['badge-arquivada', '— arquivada'],
  };
  const [cls, txt] = map[st] || ['badge-sc', st || 'sem status'];
  return `<span class="badge ${cls}">${txt}</span>`;
}

function tagTipo(tipo) {
  const c = WORK_TYPE_COLORS[tipo] || '#64748b';
  return `<span class="tag-tipo" style="background:${c}20;color:${c}">${tipo}</span>`;
}

function buildQS(form) {
  const fd = new FormData(form);
  const p  = new URLSearchParams();
  for(const [k,v] of fd.entries()) { if(v) p.append(k,v); }
  return p.toString();
}

/* API helper */
async function apiGet(url) {
  const r = await fetch(url);
  if(!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

/* SEC-03: helper para obter token CSRF da meta tag */
function getCsrf() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

/* Helper para fetch POST com CSRF automático */
async function apiPost(url, body, isJson=true) {
  const headers = { 'X-CSRFToken': getCsrf() };
  let fetchBody;
  if (isJson) {
    headers['Content-Type'] = 'application/json';
    fetchBody = JSON.stringify(body);
  } else {
    fetchBody = body; // FormData — não setar Content-Type
  }
  const r = await fetch(url, { method: 'POST', headers, body: fetchBody });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ erro: `HTTP ${r.status}` }));
    throw new Error(err.erro || `HTTP ${r.status}`);
  }
  return r.json();
}

// ── Lembretes de agenda ──────────────────────────────────────────────────────
(function() {
  const STORAGE_KEY = 'agenda_notif_visto';

  function padZero(n){ return String(n).padStart(2,'0'); }
  function fmtDT(iso){
    if (!iso) return '';
    const d = new Date(iso);
    return `${padZero(d.getDate())}/${padZero(d.getMonth()+1)} ${padZero(d.getHours())}:${padZero(d.getMinutes())}`;
  }

  async function verificarLembretes() {
    try {
      const r = await fetch('/api/agenda/lembretes');
      const eventos = await r.json();
      if (!eventos.length) return;

      // Badge na nav
      const badges = [document.getElementById('badge-agenda'), document.getElementById('badge-agenda-mobile')];
      badges.forEach(b => { if(b){ b.textContent = eventos.length; b.style.display = 'inline'; }});

      // Notificação do browser (só uma vez por sessão por conjunto)
      const vistoKey = eventos.map(e=>e.id_evento).join(',');
      if (localStorage.getItem(STORAGE_KEY) === vistoKey) return;

      if ('Notification' in window) {
        const perm = await Notification.requestPermission();
        if (perm === 'granted') {
          eventos.forEach(ev => {
            const n = new Notification('📅 Agenda — ' + ev.titulo, {
              body: (AGENDA_TYPE_LABELS[ev.tipo]||ev.tipo) + ' · ' + fmtDT(ev.data_inicio),
              icon: '/static/img/logo_endemias.png',
              tag:  'agenda_' + ev.id_evento,
            });
            n.onclick = () => { window.focus(); window.location.href = '/agenda'; n.close(); };
            setTimeout(() => n.close(), 10000);
          });
          localStorage.setItem(STORAGE_KEY, vistoKey);
        }
      }
    } catch(e) { /* silencioso */ }
  }

  // Verificar após 2s (aguarda page load) e depois a cada 15min
  setTimeout(verificarLembretes, 2000);
  setInterval(verificarLembretes, 15 * 60 * 1000);
})();
