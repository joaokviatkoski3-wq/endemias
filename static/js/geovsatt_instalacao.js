(() => {
  'use strict';

  const area = document.getElementById('geo-app-instalar');
  if (!area || !window.isSecureContext || !('serviceWorker' in navigator)) return;
  const botao = area.querySelector('button');
  const status = area.querySelector('[role="status"]');
  const independente = window.matchMedia('(display-mode: standalone)');
  const versao = encodeURIComponent(document.documentElement.dataset.versao);
  let convite;
  area.hidden = independente.matches;

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    convite = event;
  });
  window.addEventListener('appinstalled', () => { area.hidden = true; });
  navigator.serviceWorker.register(`/geovsatt-sw.js?v=${versao}`, {scope: '/geovsatt', updateViaCache: 'none'})
    .catch(() => {
      status.hidden = false;
      status.textContent = 'O navegador não conseguiu preparar a instalação neste endereço.';
    });

  botao.addEventListener('click', async () => {
    if (convite) {
      const este = convite;
      convite = null;
      try {
        await este.prompt();
        if ((await este.userChoice).outcome === 'accepted') {
          area.hidden = true;
          return;
        }
      } catch {
        // Também há instalação pelo menu do navegador compatível.
      }
    }
    status.hidden = false;
    status.textContent = 'No Chrome do Android, abra o menu ⋮ e escolha Instalar app ou Adicionar à tela inicial.';
  });
})();
