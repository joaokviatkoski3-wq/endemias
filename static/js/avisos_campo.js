(() => {
  'use strict';
  const dialog = document.getElementById('campo-avisos');
  if (!dialog) return;
  const usuario = Number(dialog.dataset.usuario);
  const sino = document.getElementById('campo-avisos-abrir');
  const counter = document.getElementById('campo-avisos-contagem');
  const status = document.getElementById('campo-avisos-status');
  const list = document.getElementById('campo-avisos-lista');
  const endpoint = '/api/formularios/campo-avisos';
  const species = {aegypt: 'Aedes aegypti', albopictus: 'Aedes albopictus', outra: 'Outras espécies'};
  const stages = {larvas: ['larva', 'larvas'], pupas: ['pupa', 'pupas'],
    exuvias: ['exúvia', 'exúvias'], adulto: ['adulto', 'adultos']};
  let requestId = 0;
  function element(tag, text) {
    const el = document.createElement(tag);
    el.textContent = text;
    return el;
  }
  function badge(total) {
    counter.textContent = total > 99 ? '99+' : total;
    counter.hidden = !total;
    sino.setAttribute('aria-label', total ? `Notificações de campo, ${total} não lidas` : 'Notificações de campo');
  }
  function reset(text) {
    ++requestId;
    badge(0);
    list.replaceChildren();
    status.textContent = text;
  }
  function formataData(iso) {
    return String(iso || '').slice(0, 10).split('-').reverse().join('/');
  }
  function card(item, csrf) {
    const li = document.createElement('li');
    li.dataset.novo = item.novo;
    li.append(element('h3', 'Tubo ' + item.num_tubo),
      element('p', [item.trabalho, item.localidade, 'Coleta em ' + formataData(item.data_coleta)].filter(Boolean).join(' · ')),
      element('p', 'Leitura em ' + formataData(item.data_leitura)));
    const results = Object.entries(species).flatMap(([key, name]) => {
      const quantities = Object.entries(stages).flatMap(([stage, labels]) => {
        const count = Number(item[key + '_' + stage]);
        return count > 0 ? [count + ' ' + labels[count === 1 ? 0 : 1]] : [];
      });
      return quantities.length ? [element('p', name + ' — ' + quantities.join(', '))] : [];
    });
    li.append(...(results.length ? results : [element('p', 'Nenhum exemplar registrado na leitura.')]));
    if (item.novo) {
      const read = element('button', 'Marcar como lido');
      read.type = 'button';
      read.className = 'btn btn-outline';
      read.onclick = async () => {
        read.disabled = true;
        try {
          const response = await fetch(endpoint, {method:'POST', cache:'no-store',
            headers:{'Content-Type':'application/json', 'X-CSRFToken':csrf},
            body:JSON.stringify({usuario, resultado:item.id_resultado, versao:item.versao})});
          await refresh(true);
          if (!response.ok) status.textContent = 'O aviso mudou ou a sessão venceu. Confira a lista atualizada.';
        } catch {
          status.textContent = 'Sem conexão com o sistema. Tente novamente.';
        } finally {
          read.disabled = false;
        }
      };
      li.append(read);
    }
    return li;
  }
  async function refresh(render = false) {
    const id = ++requestId;
    if (!navigator.onLine) {
      reset('Conecte-se para consultar os resultados.');
      return;
    }
    try {
      const response = await fetch(endpoint, {cache:'no-store', redirect:'error', signal:AbortSignal.timeout(10000)});
      if (!response.ok) throw Error();
      const data = await response.json();
      if (id !== requestId) return;
      if (data.usuario !== usuario) {
        reset('A conta mudou. Abra novamente o aplicativo.');
        return;
      }
      badge(data.nao_lidos);
      if (render) {
        status.textContent = !data.vinculado ? 'Sua conta precisa estar vinculada ao seu cadastro de agente.'
          : data.itens.length ? 'Resultados registrados ou atualizados nos últimos 30 dias. Até 40 avisos por vez.'
          : 'Nenhum resultado das suas coletas nos últimos 30 dias.';
        list.replaceChildren(...data.itens.map(item => card(item, data.csrf)));
      }
    } catch {
      if (id === requestId) reset('A consulta está indisponível. Confira a conexão ou entre novamente.');
    }
  }
  sino.onclick = () => {
    list.replaceChildren();
    status.textContent = 'Consultando resultados…';
    dialog.showModal();
    refresh(true);
  };
  window.addEventListener('online', () => refresh(dialog.open));
  window.addEventListener('offline', () => reset('Conecte-se para consultar os resultados.'));
  navigator.serviceWorker?.addEventListener('message', event => {
    if (event.data?.type === 'BLOQUEAR_CAMPO') reset('Entre novamente para consultar os resultados.');
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refresh(dialog.open);
  });
  setInterval(() => { if (!document.hidden) refresh(dialog.open); }, 90000);
  refresh();
})();
