/* IndexedDB para captura offline do formulário de RG.
 *
 * Guarda: (a) o snapshot dos quarteirões/logradouros baixados e (b) os
 * formulários preenchidos em campo, até sincronizar com o servidor.
 */
(function () {
  const DB_NAME = 'endemias_formularios';
  const DB_VERSION = 1;
  const SNAP_KEY = 'snapshot';

  function abrir() {
    return new Promise((resolve, reject) => {
      if (!('indexedDB' in window)) {
        reject(new Error('IndexedDB indisponível neste navegador.'));
        return;
      }
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains('snapshot')) db.createObjectStore('snapshot', { keyPath: 'id' });
        if (!db.objectStoreNames.contains('formularios')) db.createObjectStore('formularios', { keyPath: 'uuid' });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function put(store, valor) {
    return abrir().then((db) => new Promise((res, rej) => {
      const tx = db.transaction(store, 'readwrite');
      tx.objectStore(store).put(valor);
      tx.oncomplete = () => { db.close(); res(); };
      tx.onerror = () => { db.close(); rej(tx.error); };
    }));
  }
  function get(store, chave) {
    return abrir().then((db) => new Promise((res, rej) => {
      const tx = db.transaction(store, 'readonly');
      const rq = tx.objectStore(store).get(chave);
      rq.onsuccess = () => { db.close(); res(rq.result || null); };
      rq.onerror = () => { db.close(); rej(rq.error); };
    }));
  }
  function all(store) {
    return abrir().then((db) => new Promise((res, rej) => {
      const tx = db.transaction(store, 'readonly');
      const rq = tx.objectStore(store).getAll();
      rq.onsuccess = () => { db.close(); res(rq.result || []); };
      rq.onerror = () => { db.close(); rej(rq.error); };
    }));
  }
  function del(store, chave) {
    return abrir().then((db) => new Promise((res, rej) => {
      const tx = db.transaction(store, 'readwrite');
      tx.objectStore(store).delete(chave);
      tx.oncomplete = () => { db.close(); res(); };
      tx.onerror = () => { db.close(); rej(tx.error); };
    }));
  }

  window.RGCampoOffline = {
    disponivel: () => 'indexedDB' in window,
    salvarSnapshot: (snap) => put('snapshot', Object.assign({ id: SNAP_KEY }, snap)),
    obterSnapshot: () => get('snapshot', SNAP_KEY),
    salvarFormulario: (form) => put('formularios', form),
    listarFormularios: () => all('formularios'),
    removerFormulario: (uuid) => del('formularios', uuid),
  };
})();
