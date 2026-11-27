
(() => {
  const dados = JSON.parse(document.getElementById('dados-bloqueio').textContent);
  const mapa = L.map('mapa-bloqueio', { zoomSnap: 0, fadeAnimation: false, scrollWheelZoom: false, dragging: false, zoomControl: false, doubleClickZoom: false, touchZoom: false, keyboard: false }).setView(dados.centro, 18);
  const imprimir = document.getElementById('imprimir-mapa');
  const alternar = document.getElementById('alternar-satelite');
  const estado = document.getElementById('mapa-estado');
  const servico = (nome, cred) => L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/' + nome + '/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 21, maxNativeZoom: 19, attribution: cred,
  });
  const imagem = servico('World_Imagery', 'Imagem © Esri, Maxar, Earthstar Geographics e GIS User Community');
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
  const raio = L.geoJSON(dados.circulo, {style: {color: '#ffe355', opacity: 1, weight: 3, fillColor: '#ffd657', fillOpacity: .13}}).addTo(mapa);
  if (dados.execucao) L.geoJSON(dados.execucao, {interactive: false,
    style: f => f.properties.situacao_execucao === 'Trabalhado'
      ? {color: '#008255', weight: 2, fillOpacity: .65}
      : {color: f.properties.situacao_execucao === 'Fora do raio operacional' ? '#616b70' : '#ad4d15',
         weight: 1.5, dashArray: '4 4', fillOpacity: .24}
  }).addTo(mapa);
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
  medida.font = '600 10px system-ui';

  function mostrarRotulosLegiveis() {
    rotulos.replaceChildren();
    const borda = container.getBoundingClientRect();
    const ocupados = [...container.querySelectorAll('.quadra-label, .norte, .leaflet-control')]
      .map(label => label.getBoundingClientRect());
    for (const [i, rotulo] of dados.rotulos_ruas.entries()) {
      const pontos = rotulo.linha.map(p => mapa.latLngToContainerPoint(p));
      if (pontos[0].x > pontos.at(-1).x) pontos.reverse();
      const id = 'eixo-rua-' + i;
      const eixo = svg('path', {id, d: 'M' + pontos.map(p => p.x + ',' + p.y).join(' L')});
      rotulos.append(eixo);
      if (eixo.getTotalLength() < medida.measureText(rotulo.nome).width + 8) {
        eixo.remove();
        continue;
      }
      const texto = svg('text', {dy: '-3', 'text-anchor': 'middle'});
      const trilha = svg('textPath', {href: '#' + id, startOffset: '50%'});
      trilha.textContent = rotulo.nome;
      texto.append(trilha);
      rotulos.append(texto);
      const r = texto.getBoundingClientRect();
      const corta = r.left < borda.left + 5 || r.right > borda.right - 5 ||
        r.top < borda.top + 5 || r.bottom > borda.bottom - 5;
      const cruza = ocupados.some(o => r.left < o.right && o.left < r.right && r.top < o.bottom && o.top < r.bottom);
      if (corta || cruza) {
        texto.remove();
        eixo.remove();
      } else {
        ocupados.push(r);
      }
    }
  }
  let tamanhoAnterior;
  const ajustar = () => {
    const tamanho = container.clientWidth + 'x' + container.clientHeight;
    if (tamanho === tamanhoAnterior) return;
    tamanhoAnterior = tamanho;
    mapa.invalidateSize({animate: false});
    mapa.fitBounds(raio.getBounds().pad(.095), {animate: false});
    quarteiroes.bringToBack();
    mostrarRotulosLegiveis();
  };
  L.control.scale({imperial: false}).addTo(mapa);
  imagem.addTo(mapa);
  ajustar();

  alternar.addEventListener('click', () => {
    baseRuas = !baseRuas;
    container.classList.toggle('sem-satelite', baseRuas);
    falha = false;
    alternar.setAttribute('aria-pressed', String(baseRuas));
    if (baseRuas) mapa.removeLayer(imagem);
    else imagem.addTo(mapa);
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
