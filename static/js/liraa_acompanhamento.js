(() => {
  const painel = document.getElementById('liraa-tab-acompanhamento');
  if (!painel) return;

  const form = document.getElementById('liraa-acompanhamento-filtros');
  const status = document.getElementById('liraa-acompanhamento-status');
  const dados = document.getElementById('liraa-acompanhamento-dados');
  let requisicao;

  function ajustarDiaAoCiclo() {
    const ciclo = form.elements.ciclo.selectedOptions[0];
    const dia = form.elements.dia;
    if (ciclo.dataset.inicio && dia.value < ciclo.dataset.inicio) {
      dia.value = ciclo.dataset.inicio;
    }
    if (ciclo.dataset.fim && dia.value > ciclo.dataset.fim) {
      dia.value = ciclo.dataset.fim;
    }
  }

  async function atualizar(limpar = false) {
    if (painel.hidden || document.hidden || !form.checkValidity()) return;
    if (requisicao && !limpar) return;
    requisicao?.abort();
    const atual = new AbortController();
    requisicao = atual;
    if (limpar) dados.replaceChildren();
    status.textContent = 'Consultando registros do ciclo…';

    try {
      const url = new URL(form.action);
      url.search = new URLSearchParams(new FormData(form)).toString();
      const resposta = await fetch(url, {signal: atual.signal, cache: 'no-store'});
      if (resposta.redirected) {
        throw new Error('Entre novamente para atualizar o acompanhamento.');
      }
      if (!resposta.ok) throw new Error('Não foi possível atualizar. Confira os filtros e tente novamente.');
      const html = await resposta.text();
      if (requisicao !== atual) return;
      const listaAberta = dados.querySelector('details')?.open;
      dados.innerHTML = html;
      if (listaAberta) dados.querySelector('details')?.setAttribute('open', '');
      status.textContent = '';
    } catch (erro) {
      if (erro.name !== 'AbortError' && requisicao === atual) status.textContent = erro.message;
    } finally {
      if (requisicao === atual) requisicao = null;
    }
  }

  form.addEventListener('submit', evento => {
    evento.preventDefault();
    atualizar(true);
  });
  form.addEventListener('change', evento => {
    if (evento.target === form.elements.ciclo) ajustarDiaAoCiclo();
    atualizar(true);
  });
  document.addEventListener('visibilitychange', () => atualizar());
  setInterval(() => atualizar(), 60000);
  ajustarDiaAoCiclo();
  window.LiraaAcompanhamento = {iniciar: () => atualizar(true)};
})();
