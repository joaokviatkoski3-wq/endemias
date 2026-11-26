import {abrirRegistro, bloquearRegistro, criarRegistro, decodificarPacote, gravarProjetos,
  guardarRegistro, lerProjetos, lerRegistro, protegerProjetos, removerRegistro} from './geovsatt_cofre.mjs';
import {criarApiLocal, exportar, lerBaseVetorial} from './geovsatt_dados_offline.mjs';

const shell = document.querySelector('.geo-shell');
const offline = document.documentElement.dataset.offline === '1';
const URL_OFFLINE = '/geovsatt/offline';
const LIMITE_COPIA = 50 * 1024 ** 2;
const canal = 'BroadcastChannel' in window ? new BroadcastChannel('geovsatt-mapa-campo') : null;
const node = (tag, classe, texto) => {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texto !== undefined) el.textContent = texto;
  return el;
};
const data = valor => new Date(valor).toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'});
const vigente = registro => registro && !registro.bloqueado && Date.parse(registro.valido_ate) > Date.now();
const seguro = window.isSecureContext && window.crypto?.subtle && window.indexedDB;
const bloquear = () => location.replace(URL_OFFLINE);

async function revogadaNoServidor(dados) {
  let resposta;
  try {
    resposta = await fetch('/api/geovsatt/pacote-offline/estado', {
      credentials: 'same-origin', cache: 'no-store', redirect: 'manual', signal: AbortSignal.timeout(3000),
    });
  } catch {
    return false;
  }
  if (resposta.type === 'opaqueredirect' || [401, 403].includes(resposta.status)) return true;
  if (!resposta.ok) return false;
  const permissoes = await resposta.json().catch(() => null);
  return !permissoes || !Array.isArray(permissoes.camadas) || permissoes.usuario !== dados.usuario ||
    dados.camadas.some(camada => !permissoes.camadas.includes(camada.id)) ||
    Boolean(dados.ortofotos?.some(item => permissoes.ortofotos?.[item.id] !== item.versao)) ||
    Boolean(dados.esporotricose_exata && !permissoes.esporotricose_exata) ||
    Boolean((dados.rg || dados.populacao) && !permissoes.rg);
}

function montarCamadas(pacote) {
  const destino = document.getElementById('geo-campo-camadas');
  const secoes = new Map();
  for (const camada of pacote.camadas) {
    if (!secoes.has(camada.grupo)) {
      const secao = node('section', 'geo-layer-group');
      secao.append(node('h2', '', camada.grupo));
      secoes.set(camada.grupo, secao);
      destino.append(secao);
    }
    const secao = secoes.get(camada.grupo);
    const linha = node('label', 'geo-layer-row');
    linha.title = camada.descricao;
    const input = node('input');
    input.type = 'checkbox';
    input.checked = camada.visivel_inicial;
    Object.assign(input.dataset, {layer: camada.id, nome: camada.nome, tipo: camada.tipo,
      estilo: JSON.stringify(camada.estilo || {})});
    const simbolo = node('span', 'geo-layer-symbol geo-layer-symbol--' + camada.tipo);
    simbolo.setAttribute('aria-hidden', 'true');
    const texto = node('span');
    texto.append(node('strong', '', camada.nome), node('small', '', camada.descricao));
    linha.append(input, simbolo, texto);
    const lista = node('details', 'geo-layer-key');
    lista.id = 'geo-key-' + camada.id;
    lista.hidden = true;
    lista.append(node('summary', '', 'Legenda'), node('ul'));
    const filtros = node('div', 'geo-layer-filters');
    filtros.id = 'geo-filter-' + camada.id;
    filtros.hidden = true;
    if (camada.id === 'quarteiroes_trabalhados' && pacote.historico_trabalhos) {
      const {inicio, fim} = pacote.historico_trabalhos.periodo;
      const modelo = document.getElementById('geo-campo-trabalhos').content.cloneNode(true);
      for (const campo of modelo.querySelectorAll('input[type="date"]')) {
        campo.min = inicio;
        campo.max = fim;
      }
      const formatar = valor => valor.split('-').reverse().join('/');
      modelo.querySelector('[data-periodo-baixado]').textContent =
        'Período da cópia: ' + formatar(inicio) + ' a ' + formatar(fim) + '.';
      filtros.append(modelo);
    }
    secao.append(linha, lista, filtros);
    if (camada.pode_exportar) montarExportacao(secao, camada);
  }
  if (!destino.querySelector('input:checked')) {
    const primeira = destino.querySelector('input');
    if (primeira) primeira.checked = true;
  }
  const seletor = document.getElementById('geo-basemap');
  if (pacote.openfreemap) seletor.add(new Option('OpenStreetMap · OpenFreeMap (offline)', 'openfreemap'));
  if (pacote.ortofotos?.length) {
    const grupo = node('optgroup');
    grupo.label = 'Ortofotos desta cópia';
    for (const {mosaicos, mime, ...orto} of pacote.ortofotos) {
      const opcao = new Option(orto.nome, orto.base);
      opcao.dataset.ortofoto = JSON.stringify(orto);
      grupo.append(opcao);
    }
    seletor.append(grupo);
  }
}

function montarExportacao(secao, camada) {
  const ferramentas = node('details', 'geo-layer-exportar');
  ferramentas.dataset.exportLayer = camada.id;
  ferramentas.append(node('summary', '', 'Exportar ' + camada.nome));
  const links = node('div');
  const estado = node('small', '', 'Exporta as feições desta cópia.');
  estado.setAttribute('role', 'status');
  for (const [formato, rotulo] of [['csv', 'CSV'], ['geojson', 'GeoJSON'], ['kml', 'KML']]) {
    const botao = node('button', '', rotulo);
    botao.type = 'button';
    botao.addEventListener('click', async () => {
      botao.disabled = true;
      try {
        const consulta = ferramentas.dataset.consulta;
        const caminho = '/api/geovsatt/camadas/' + encodeURIComponent(camada.id);
        const dados = await window.GeoVSATTCampo.api(consulta ? caminho + '?' + consulta : caminho);
        const href = URL.createObjectURL(exportar(camada, dados, formato));
        const download = node('a');
        download.href = href;
        download.download = 'geovsatt-' + camada.id + '-offline.' + formato;
        links.append(download);
        download.click();
        download.remove();
        setTimeout(() => URL.revokeObjectURL(href), 15000);
        estado.textContent = 'Exporta as feições desta cópia.';
      } catch (error) {
        estado.textContent = error.message;
      } finally {
        botao.disabled = false;
      }
    });
    links.append(botao);
  }
  ferramentas.append(links, estado);
  secao.append(ferramentas);
}

async function carregarOffline() {
  const estado = document.getElementById('geo-campo-disponibilidade');
  const form = document.getElementById('geo-campo-abrir');
  if (!seguro) {
    estado.textContent = 'Abra o GeoVSATT por HTTPS em um navegador compatível.';
    return;
  }
  const registro = await lerRegistro();
  if (!vigente(registro)) {
    estado.textContent = registro ? 'A cópia precisa ser renovada com conexão.' :
      'Entre no GeoVSATT com conexão e prepare o mapa neste aparelho.';
    return;
  }
  const mensagem = 'Cópia de ' + data(registro.criado_em) + ' · disponível até ' + data(registro.valido_ate) + '.';
  estado.textContent = mensagem;
  form.hidden = false;
  let abrindo = false;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (abrindo) return;
    abrindo = true;
    const senha = form.elements.senha.value;
    form.reset();
    form.querySelector('button').disabled = true;
    estado.textContent = 'Abrindo a cópia…';
    try {
      const {chave, dados} = await abrirRegistro(registro, senha);
      let revisao = registro.revisao || 0;
      const atual = await lerRegistro();
      if (!vigente(atual) || atual.id !== registro.id || (atual.revisao || 0) !== revisao) {
        throw Error('A cópia mudou. Reabra o aplicativo.');
      }
      if (await revogadaNoServidor(dados)) {
        await bloquearRegistro(registro.id);
        canal?.postMessage(registro.id);
        form.hidden = true;
        throw Error('Entre no GeoVSATT para renovar a autorização desta cópia.');
      }
      const projetos = await lerProjetos(registro, chave);
      const gravar = async novos => {
        if (!vigente(registro)) throw Error('A validade desta cópia terminou.');
        const fechados = await protegerProjetos(registro, chave, novos);
        await gravarProjetos(registro.id, revisao, fechados);
        revisao += 1;
      };
      const apiLocal = criarApiLocal(dados, projetos, gravar, window.polygonClipping);
      const ortos = new Map((dados.ortofotos || []).map(item => [item.id, item]));
      window.GeoVSATTCampo = {
        baseVetorial: dados.openfreemap || null,
        temHistoricoTrabalhos: Boolean(dados.historico_trabalhos),
        api(url, opcoes) {
          if (!vigente(registro)) throw Error('A validade desta cópia terminou.');
          return apiLocal(url, opcoes);
        },
        mosaico(id, {z, x, y}) {
          if (!vigente(registro)) return null;
          const orto = ortos.get(id);
          const imagem = orto?.mosaicos[z + '/' + x + '/' + y];
          return imagem ? 'data:' + orto.mime + ';base64,' + imagem : null;
        },
      };
      shell.dataset.podeRg = dados.rg ? '1' : '0';
      document.querySelector('[data-medida="populacao"]').hidden = !dados.populacao;
      montarCamadas(dados);
      document.getElementById('geo-campo-snapshot').textContent = mensagem;
      document.getElementById('geo-desbloquear').hidden = true;
      shell.hidden = false;
      document.dispatchEvent(new Event('geovsatt:pacote-aberto'));
      if (!dados.camadas.length && (dados.openfreemap || ortos.size)) {
        const seletor = document.getElementById('geo-basemap');
        seletor.value = dados.openfreemap ? 'openfreemap' : ortos.values().next().value.base;
        seletor.dispatchEvent(new Event('change'));
        if (!dados.openfreemap) document.getElementById('geo-ortofoto-enquadrar').click();
      }
      document.getElementById('geo-campo-bloquear').addEventListener('click', bloquear);
      canal?.addEventListener('message', event => { if (event.data === registro.id) bloquear(); });
      window.addEventListener('online', async () => {
        if (await revogadaNoServidor(dados)) {
          try {
            await bloquearRegistro(registro.id);
            canal?.postMessage(registro.id);
          } finally {
            bloquear();
          }
        }
      });
      document.addEventListener('visibilitychange', async () => {
        if (document.hidden) return;
        try {
          const atual = await lerRegistro();
          if (!vigente(atual) || atual.id !== registro.id) bloquear();
        } catch { bloquear(); }
      });
      setTimeout(bloquear, Math.max(0, Date.parse(registro.valido_ate) - Date.now()));
    } catch (erro) {
      estado.textContent = erro.message;
    } finally {
      form.querySelector('button').disabled = false;
      abrindo = false;
    }
  });
}

async function aguardarInterface() {
  const registro = await window.GeoVSATTPWA;
  const esperado = '/geovsatt-sw.js?v=' + encodeURIComponent(document.documentElement.dataset.versao);
  const versaoCerta = worker => worker && new URL(worker.scriptURL).pathname + new URL(worker.scriptURL).search === esperado;
  if (registro?.active?.state === 'activated' && versaoCerta(registro.active) && !registro.installing && !registro.waiting) return;
  const worker = registro?.installing || registro?.waiting || registro?.active;
  if (!versaoCerta(worker)) throw Error('O navegador ainda não preparou o aplicativo offline. Reabra a página.');
  await new Promise((resolve, reject) => {
    const limite = setTimeout(() => finalizar('O aplicativo ainda está baixando a interface. Tente novamente.'), 25000);
    function finalizar(erro) {
      clearTimeout(limite);
      worker.removeEventListener('statechange', mudou);
      if (erro) reject(Error(erro));
      else resolve();
    }
    function mudou() {
      if (worker.state === 'activated') finalizar();
      if (worker.state === 'redundant') finalizar('Não foi possível baixar a interface offline.');
    }
    worker.addEventListener('statechange', mudou);
    mudou();
  });
}

async function prepararOnline() {
  if (!seguro || !window.GeoVSATTPWA) return;
  const menu = document.getElementById('geo-campo-menu');
  const dialogo = document.getElementById('geo-campo-dialogo');
  const form = document.getElementById('geo-campo-form');
  const progresso = document.getElementById('geo-campo-progresso');
  const abrir = document.getElementById('geo-campo-visualizar');
  const fechar = document.getElementById('geo-campo-fechar');
  const excluir = document.getElementById('geo-campo-excluir');
  const preparar = document.getElementById('geo-campo-preparar');
  const conta = Number(shell.dataset.conta);
  let ocupado = false;
  let salvo = await lerRegistro();
  if (salvo && salvo.usuario !== conta && !salvo.bloqueado) {
    await bloquearRegistro(salvo.id);
    canal?.postMessage(salvo.id);
    salvo = await lerRegistro();
  }
  function mostrarSituacao() {
    abrir.hidden = !(salvo?.usuario === conta && vigente(salvo));
    excluir.hidden = !salvo;
    menu.hidden = false;
    document.getElementById('geo-campo-situacao').textContent = !salvo ? '' : !abrir.hidden
      ? 'Cópia de ' + data(salvo.criado_em) + '. Válida até ' + data(salvo.valido_ate) + '.'
      : 'A cópia deste aparelho está bloqueada ou precisa ser renovada.';
  }
  mostrarSituacao();
  function abrirDialogo() {
    progresso.textContent = '';
    dialogo.showModal();
  }
  preparar.addEventListener('click', abrirDialogo);
  fechar.addEventListener('click', () => dialogo.close());
  dialogo.addEventListener('cancel', event => { if (ocupado) event.preventDefault(); });
  excluir.addEventListener('click', async () => {
    if (!salvo || ocupado || !window.confirm('Remover a cópia e suas composições locais deste aparelho?')) return;
    try {
      await removerRegistro(salvo.id);
      canal?.postMessage(salvo.id);
      salvo = await lerRegistro();
      mostrarSituacao();
      progresso.textContent = 'Cópia removida.';
    } catch {
      progresso.textContent = 'Não foi possível remover a cópia.';
    }
  });
  if (form.elements.enderecos) {
    const atualizarEnderecos = () => {
      const disponivel = form.querySelector('[name="camadas"][value="quarteiroes"]')?.checked;
      form.elements.enderecos.disabled = !disponivel;
      if (!disponivel) form.elements.enderecos.checked = false;
    };
    form.addEventListener('change', atualizarEnderecos);
    atualizarEnderecos();
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (ocupado) return;
    const campos = new FormData(form);
    const selecionadas = campos.getAll('camadas');
    const ortos = campos.getAll('ortofotos');
    const baixarOpenFreeMap = campos.has('openfreemap');
    const senha = campos.get('senha');
    if (!(selecionadas.length || ortos.length || baixarOpenFreeMap) || senha !== campos.get('confirmacao')) {
      progresso.textContent = !(selecionadas.length || ortos.length || baixarOpenFreeMap)
        ? 'Selecione uma camada, ortofoto ou base de ruas.' : 'As senhas digitadas são diferentes.';
      return;
    }
    ocupado = true;
    for (const botao of form.querySelectorAll('button')) botao.disabled = true;
    try {
      progresso.textContent = 'Preparando a interface e as camadas…';
      const anterior = await lerRegistro();
      if (anterior && anterior.usuario !== conta) throw Error('Remova a cópia da outra conta deste aparelho antes de continuar.');
      let projetos = [];
      if (anterior?.projetos) {
        try {
          const aberto = await abrirRegistro(anterior, senha);
          projetos = await lerProjetos(anterior, aberto.chave);
        } catch {
          throw Error('Use a senha atual da cópia para preservar suas composições locais.');
        }
      }
      await aguardarInterface();
      const detalhe = {};
      const recortarOrto = ortos.length && campos.has('recortar');
      if (baixarOpenFreeMap || recortarOrto) {
        document.dispatchEvent(new CustomEvent('geovsatt:obter-recorte-offline', {detail: detalhe}));
        if (!detalhe.limites) throw Error('Abra o mapa na área que deseja baixar.');
      }
      const trabalhos = {};
      if (selecionadas.includes('quarteiroes_trabalhados')) {
        document.dispatchEvent(new CustomEvent('geovsatt:obter-trabalhos-offline', {detail: trabalhos}));
      }
      const resposta = await fetch('/api/geovsatt/pacote-offline', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name="csrf-token"]').content},
        body: JSON.stringify({camadas: selecionadas, ortofotos: ortos, recorte: recortarOrto ? detalhe.limites : undefined, trabalhos,
          openfreemap: baixarOpenFreeMap,
          enderecos: campos.has('enderecos')}),
      });
      if (!resposta.ok || resposta.redirected) {
        const erro = await resposta.json().catch(() => null);
        throw Error(erro?.erro || 'Não foi possível preparar as camadas. Confira sua sessão e a conexão.');
      }
      let bytes = await resposta.arrayBuffer();
      const pacote = decodificarPacote(bytes, baixarOpenFreeMap);
      if (pacote.usuario !== conta) throw Error('A conta mudou durante o download. Reabra o mapa.');
      if (baixarOpenFreeMap) {
        const limite = LIMITE_COPIA - bytes.byteLength;
        if (limite <= 0) throw Error('A cópia está cheia. Selecione menos camadas ou ortofotos.');
        progresso.textContent = 'Preparando o recorte da base OpenFreeMap…';
        const base = await fetch('/api/geovsatt/pacote-offline/openfreemap', {
          method: 'POST', cache: 'no-store', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name="csrf-token"]').content},
          body: JSON.stringify({recorte: detalhe.limites, limite}),
        });
        if (!base.ok || base.redirected || !base.body) {
          const erro = await base.json().catch(() => null);
          throw Error(erro?.erro || 'Não foi possível baixar a base OpenFreeMap.');
        }
        pacote.openfreemap = await lerBaseVetorial(base.body, limite, (atual, total) => {
          progresso.textContent = 'OpenFreeMap · ' + atual + ' de ' + total + ' recursos baixados.';
        });
        bytes = new TextEncoder().encode(JSON.stringify(pacote));
        if (bytes.byteLength > LIMITE_COPIA) throw Error('A base ultrapassou o tamanho disponível na cópia.');
      }
      progresso.textContent = 'Protegendo a cópia no aparelho…';
      const registro = await criarRegistro(bytes, pacote, senha, projetos);
      if (await revogadaNoServidor(pacote)) throw Error('A autorização mudou durante o download. Entre novamente.');
      await guardarRegistro(anterior?.id, anterior?.revisao || 0, registro);
      if (anterior) canal?.postMessage(anterior.id);
      salvo = registro;
      form.elements.senha.value = form.elements.confirmacao.value = '';
      mostrarSituacao();
      progresso.textContent = 'Cópia pronta. Use Abrir cópia offline para consultá-la.';
      try { await navigator.storage?.persist?.(); } catch { /* A cópia já está gravada. */ }
    } catch (erro) {
      progresso.textContent = erro.name === 'QuotaExceededError'
        ? 'Não há espaço suficiente. Selecione menos camadas.' : erro.message;
    } finally {
      for (const botao of form.querySelectorAll('button')) botao.disabled = false;
      ocupado = false;
    }
  });
  const logout = document.querySelector('form[action="/logout"]');
  logout?.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const registro = await lerRegistro();
      if (registro?.usuario === conta) {
        await bloquearRegistro(registro.id);
        canal?.postMessage(registro.id);
      }
    } finally {
      HTMLFormElement.prototype.submit.call(logout);
    }
  });
}

(offline ? carregarOffline() : prepararOnline()).catch(() => {
  const estado = document.getElementById(offline ? 'geo-campo-disponibilidade' : 'geo-campo-situacao');
  estado?.closest('[hidden]')?.removeAttribute('hidden');
  if (estado) estado.textContent = 'Não foi possível acessar o armazenamento deste aparelho.';
});
