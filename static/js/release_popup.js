(() => {
  'use strict';
  const dialog = document.getElementById('release-dialog');
  const opener = document.getElementById('release-open');
  if (!dialog || !opener) return;
  const key = ['vsatt.release.seen', dialog.dataset.area, dialog.dataset.user].join('.');
  const version = dialog.dataset.version;
  const read = () => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const write = () => { try { localStorage.setItem(key, version); } catch (_) { /* sessão privada */ } };
  const open = () => {
    if (dialog.open) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  };
  opener.addEventListener('click', open);
  dialog.addEventListener('close', write);
  dialog.addEventListener('cancel', write);
  if (read() !== version) window.setTimeout(open, 180);
})();
