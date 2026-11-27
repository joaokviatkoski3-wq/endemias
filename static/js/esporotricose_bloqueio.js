
(() => {
  const dados = JSON.parse(document.getElementById('dados-bloqueio').textContent);
  const mapa = L.map('mapa-bloqueio', { zoomSnap: 0, fadeAnimation: false, scrollWheelZoom: false, dragging: false, zoomControl: false, doubleClickZoom: false, touchZoom: false, keyboard: false }).setView(dados.centro, 18);
  const imprimir = document.getElementById('imprimir-mapa');
  const alternar = document.getElementById('alternar-satelite');
  const estado = document.getElementById('mapa-estado');
  const imagem = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 21, maxNativeZoom: 18, tileSize: 128, zoomOffset: 1,
    attribution: 'Imagem © Esri, Vantor, Earthstar Geographics e GIS User Community',
  });
  let baseRuas = false;
  let falha = false;
  let espera;
  const visiveis = () => baseRuas ? [] : [imagem];

  function verificarCarregamento() {
    if (visiveis().some(l => l.isLoading())) return;
    clearTimeout(espera);
    imprimir.disabled = false;
    estado.textContent = falha ? 'Parte da base cartográfica está indisponível. O raio e os quarteirões permanecem visíveis.' : '';
  }

  function aguardar() {
    imprimir.disabled = true;
    estado.textContent = 'Carregando a base cartográfica…';
    clearTimeout(espera);
    espera = setTimeout(() => {
      estado.textContent = 'A base demorou a carregar. Confira o mapa antes de imprimir.';
      imprimir.disabled = false;
    }, 9000);
  }
  for (const l of [imagem]) {
    l.on('loading', aguardar);
    l.on('tileerror', () => { if (visiveis().includes(l)) falha = true; });
    l.on('load', verificarCarregamento);
  }

  const quarteiroes = L.geoJSON(dados.quarteiroes, {
    style: f => ({color: f.properties.atingido ? '#88ffc1' : '#c8e2d2', opacity: .9, weight: 1.5, fillOpacity: 0}),
    onEachFeature(f, layer) {
      if (!f.properties.codigo || !f.properties.atingido || !layer.getBounds().isValid()) return;
      const texto = document.createElement('span');
      texto.textContent = f.properties.codigo;
      const p = layer.getBounds().getCenter();
      L.tooltip({ permanent: true, direction: 'center', className: 'quadra-label' })
        .setLatLng(p).setContent(texto).addTo(mapa);
    },
  }).addTo(mapa);
  const raio = L.geoJSON(dados.circulo, {style: {color: '#ffe355', opacity: 1, weight: 2.5, fillColor: '#ffd657', fillOpacity: .04}}).addTo(mapa);
  const eixosRuas = L.featureGroup(dados.rotulos_ruas.flatMap(rua => rua.linhas.map(linha =>
    L.polyline(linha, {interactive: false, color: '#83958c', opacity: .65, weight: 2}))));
  L.circleMarker(dados.centro, {radius: 6, color:'#fff', weight: 2, fillColor:'#bf3119', fillOpacity: 1}).addTo(mapa);
  const container = mapa.getContainer();
  const svg = (tag, atributos = {}) => {
    const elemento = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [nome, valor] of Object.entries(atributos)) elemento.setAttribute(nome, valor);
    return elemento;
  };
  const rotulos = svg('svg', {class: 'nomes-ruas', 'aria-hidden': 'true'});
  container.append(rotulos);
  const medida = document.createElement('canvas').getContext('2d');
  const fonte = tamanho => '600 ' + tamanho + 'px system-ui';
  const abreviarVia = nome => nome.replace(/^Rua /i, 'R. ').replace(/^Avenida /i, 'Av. ')
    .replace(/^Travessa /i, 'Tv. ').replace(/\bProfessor /i, 'Prof. ').replace(/\bProfessora /i, 'Profª. ');

  const continuacao = document.getElementById('continuacao-bloqueio');
  const quadrasContinuacao = document.getElementById('quarteiroes-continuacao');
  const listaQuadras = document.getElementById('lista-quarteiroes');
  const itensQuadras = [...(listaQuadras?.children || [])];
  const cruza = (a, b) => a.left < b.right + 2 && b.left < a.right + 2 && a.top < b.bottom + 2 && b.top < a.bottom + 2;

  function organizarQuadro() {
    if (listaQuadras) listaQuadras.replaceChildren(...itensQuadras);
    const fimMapa = container.getBoundingClientRect().bottom;
    const espacoNota = (document.querySelector('.nota-quarteirao')?.offsetHeight || 0) + 24;
    const quebra = itensQuadras.findIndex(item => item.getBoundingClientRect().bottom > fimMapa - espacoNota);
    const empilhado = window.matchMedia('(max-width: 700px)').matches &&
      !document.documentElement.classList.contains('preparando-impressao') && !window.matchMedia('print').matches;
    const fora = quebra < 0 || empilhado ? [] : itensQuadras.slice(quebra);
    quadrasContinuacao.querySelector('ul').replaceChildren(...fora);
    quadrasContinuacao.hidden = continuacao.hidden = !fora.length;
  }

  function trechosVisiveis(linha, limites) {
    const pontos = linha.map(p => mapa.latLngToContainerPoint(p));
    const trechos = [];
    let trecho;
    for (let i = 1; i < pontos.length; i++) {
      const segmento = L.LineUtil.clipSegment(pontos[i - 1], pontos[i], limites);
      if (!segmento) continue;
      const [inicio, fim] = segmento;
      if (!trecho?.pontos.at(-1).equals(inicio)) {
        trecho = {pontos: [inicio], comprimento: 0};
        trechos.push(trecho);
      }
      trecho.pontos.push(fim);
      trecho.comprimento += inicio.distanceTo(fim);
    }
    return trechos;
  }

  function posicionarNaLinha(trecho, id, nome, tamanho, largura, verifica) {
    const metade = largura / 2 + 2;
    if (trecho.comprimento < metade * 2) return false;
    const linhaSvg = lista => 'M' + lista.map(p => p.x + ',' + p.y).join(' L');
    const eixo = svg('path', {id, d: linhaSvg(trecho.pontos)});
    const reverso = svg('path', {id: id + '-reverso', d: linhaSvg(trecho.pontos.slice().reverse())});
    const texto = svg('text', {'text-anchor': 'middle', 'dominant-baseline': 'central'});
    texto.style.fontSize = tamanho + 'px';
    const trilha = svg('textPath');
    trilha.textContent = nome;
    texto.append(trilha);
    rotulos.append(eixo, reverso, texto);
    const comprimento = eixo.getTotalLength();
    const passos = Math.ceil((comprimento / 2 - metade) / 6);
    for (let passo = 0; passo <= passos; passo++) {
      const distancia = passos ? (comprimento / 2 - metade) * passo / passos : 0;
      const opcoes = passo === 0 ? [comprimento / 2] : [comprimento / 2 - distancia, comprimento / 2 + distancia];
      for (const meio of opcoes) {
        const inicio = eixo.getPointAtLength(meio - largura / 2);
        const fim = eixo.getPointAtLength(meio + largura / 2);
        const dx = fim.x - inicio.x, dy = fim.y - inicio.y;
        if (Math.hypot(dx, dy) < largura * .92) continue;
        const inverter = Math.abs(dx) >= Math.abs(dy) ? dx < 0 : dy > 0;
        trilha.setAttribute('href', '#' + (inverter ? reverso.id : eixo.id));
        trilha.setAttribute('startOffset', inverter ? comprimento - meio : meio);
        if (verifica(texto)) {
          (inverter ? eixo : reverso).remove();
          return true;
        }
      }
    }
    eixo.remove();
    reverso.remove();
    texto.remove();
    return false;
  }

  function mostrarRotulosLegiveis() {
    rotulos.replaceChildren();
    const borda = container.getBoundingClientRect();
    const ocupados = [...container.querySelectorAll('.norte, .leaflet-control')]
      .map(label => label.getBoundingClientRect()).filter(r => r.width && r.height);
    const verifica = etiqueta => {
      const r = etiqueta.getBoundingClientRect();
      if (!r.width || r.left < borda.left + 5 || r.right > borda.right - 5 || r.top < borda.top + 5 ||
          r.bottom > borda.bottom - 5 || ocupados.some(o => cruza(r, o))) return false;
      ocupados.push(r);
      return true;
    };
    const limites = L.bounds([0, 0], [borda.width, borda.height]);
    const ruas = dados.rotulos_ruas.map(rua => {
      const trechos = rua.linhas.flatMap(linha => trechosVisiveis(linha, limites));
      const formatos = [{nome: rua.nome, tamanho: 10}, {nome: rua.nome, tamanho: 9.5}];
      const abreviado = abreviarVia(rua.nome);
      if (abreviado !== rua.nome) formatos.push({nome: abreviado, tamanho: 9.5});
      for (const formato of formatos) {
        medida.font = fonte(formato.tamanho);
        formato.largura = medida.measureText(formato.nome).width;
      }
      // Dentro do raio, tente primeiro as ruas com menos espaço para mover o nome.
      const margem = Math.max(0, ...trechos.map(trecho => trecho.comprimento)) - formatos.at(-1).largura - 4;
      return {...rua, trechos, formatos, margem};
    }).filter(rua => rua.margem >= 0).sort((a, b) => b.no_raio - a.no_raio || a.margem - b.margem);
    for (const [i, rua] of ruas.entries()) {
      rua.formatos.some(({nome, tamanho, largura}) => rua.trechos.some((trecho, j) =>
        posicionarNaLinha(trecho, 'eixo-rua-' + i + '-' + j, nome, tamanho, largura, verifica)));
    }
    for (const etiqueta of container.querySelectorAll('.quadra-label')) {
      etiqueta.style.visibility = 'visible';
      const r = etiqueta.getBoundingClientRect();
      if (ocupados.some(o => cruza(r, o))) etiqueta.style.visibility = 'hidden';
      else ocupados.push(r);
    }
  }
  let tamanhoAnterior;
  const ajustar = () => {
    const tamanho = container.clientWidth + 'x' + container.clientHeight;
    if (tamanho === tamanhoAnterior) {
      organizarQuadro();
      return;
    }
    tamanhoAnterior = tamanho;
    mapa.invalidateSize({animate: false});
    mapa.fitBounds(raio.getBounds().pad(.095), {animate: false});
    quarteiroes.bringToBack();
    mostrarRotulosLegiveis();
    organizarQuadro();
  };
  L.control.scale({imperial: false}).addTo(mapa);
  imagem.addTo(mapa);
  ajustar();

  alternar.addEventListener('click', () => {
    baseRuas = !baseRuas;
    container.classList.toggle('sem-satelite', baseRuas);
    falha = false;
    alternar.setAttribute('aria-pressed', String(baseRuas));
    if (baseRuas) {
      mapa.removeLayer(imagem);
      eixosRuas.addTo(mapa);
    } else {
      mapa.removeLayer(eixosRuas);
      imagem.addTo(mapa);
    }
    quarteiroes.setStyle({color: baseRuas ? '#21864b' : '#88ffc1'});
    raio.setStyle({color: baseRuas ? '#b45c11' : '#ffe355'});
    verificarCarregamento();
  });
  imprimir.addEventListener('click', async () => {
    document.documentElement.classList.add('preparando-impressao');
    ajustar();
    if (!baseRuas && imagem.isLoading()) {
      await new Promise(concluir => {
        const liberar = () => {
          clearTimeout(limite);
          imagem.off('load', liberar);
          concluir();
        };
        imagem.once('load', liberar);
        const limite = setTimeout(liberar, 9000);
      });
    }
    window.print();
  });
  window.addEventListener('resize', ajustar);
  window.addEventListener('beforeprint', ajustar);
  window.addEventListener('afterprint', () => {
    document.documentElement.classList.remove('preparando-impressao');
    ajustar();
  });
})();
