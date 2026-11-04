/* Lista administrativa; nenhuma sessao, credencial ou endereco de conexao. */
(() => {
  const summary = document.getElementById('presenca-resumo');
  if (!summary) return;
  const zone = 'America/Sao_Paulo';
  let busy = false;
  function dayKey(date) {
    const parts = new Intl.DateTimeFormat('en-CA', {timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(date);
    const value = type => parts.find(p => p.type === type).value;
    return `${value('year')}-${value('month')}-${value('day')}`;
  }
  function seenText(value, now) {
    if (!value) return 'Sem registro';
    const date = new Date(value);
    const today = dayKey(now);
    const yesterday = new Date(Date.parse(today + 'T00:00:00Z') - 86400000).toISOString().slice(0, 10);
    const time = new Intl.DateTimeFormat('pt-BR', {timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).format(date);
    const day = dayKey(date);
    if (day === today) return `Hoje, às ${time}`;
    if (day === yesterday) return `Ontem, às ${time}`;
    return new Intl.DateTimeFormat('pt-BR', {timeZone: zone, day: '2-digit', month: '2-digit', year: 'numeric'}).format(date) + ` às ${time}`;
  }
  function unavailable() {
    summary.textContent = 'Presença indisponível no momento';
    document.querySelectorAll('[data-presenca-status]').forEach(el => {
      el.textContent = 'Sem atualização';
      el.className = 'presenca-badge presenca-offline';
    });
  }
  async function refresh() {
    if (busy || document.visibilityState !== 'visible') return;
    if (navigator.onLine === false) { unavailable(); return; }
    busy = true;
    try {
      const response = await fetch('/admin/usuarios/presenca', {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok || response.redirected) throw new Error('indisponivel');
      const data = await response.json();
      const now = new Date(data.verificado_em);
      data.usuarios.forEach(item => {
        const row = document.getElementById(`row-${item.id_usuario}`);
        if (!row) return;
        const status = row.querySelector('[data-presenca-status]');
        const last = row.querySelector('[data-presenca-ultima]');
        status.textContent = item.online ? '● Online' : '○ Offline';
        status.className = 'presenca-badge ' + (item.online ? 'presenca-online' : 'presenca-offline');
        last.textContent = item.online ? 'Agora' : seenText(item.ultima_presenca, now);
        last.title = item.ultima_presenca
          ? new Intl.DateTimeFormat('pt-BR', {timeZone: zone, dateStyle: 'short', timeStyle: 'medium'}).format(new Date(item.ultima_presenca)) : '';
      });
      summary.textContent = `${data.online_total} ${data.online_total === 1 ? 'usuário online' : 'usuários online'}`;
    } catch (_) {
      unavailable();
    } finally {
      busy = false;
    }
  }
  document.addEventListener('visibilitychange', refresh);
  window.addEventListener('endemias:presenca-confirmada', refresh);
  window.addEventListener('online', refresh);
  window.addEventListener('offline', unavailable);
  setInterval(refresh, 30000);
  refresh();
})();
