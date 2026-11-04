/* Confirmacao leve de presenca, somente com pagina visivel e autenticada. */
(() => {
  let timer = null, busy = false, stopped = false;
  function visible() {
    return document.visibilityState === 'visible' && navigator.onLine !== false;
  }
  async function confirm() {
    clearTimeout(timer);
    if (stopped || busy || !visible()) return;
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content
      || document.querySelector('input[name="csrf_token"]')?.value;
    if (!csrf) return;
    busy = true;
    try {
      const response = await fetch('/api/presenca', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: {'X-CSRFToken': csrf}
      });
      if (response.status === 401 || response.status === 403 || response.redirected) stopped = true;
      if (response.ok && !response.redirected) window.dispatchEvent(new Event('endemias:presenca-confirmada'));
    } catch (_) {
      // Falha de presenca nao interrompe o trabalho ou os formularios offline.
    } finally {
      busy = false;
      if (!stopped && visible()) timer = setTimeout(confirm, 30000);
    }
  }
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    if (visible()) confirm();
  });
  window.addEventListener('online', confirm);
  window.addEventListener('offline', () => clearTimeout(timer));
  confirm();
})();
