
(() => {
  const dados = JSON.parse(document.getElementById('dados-bloqueio').textContent);
  const mapa = L.map('mapa-bloqueio', { zoomSnap: 0, scrollWheelZoom: false, dragging: false, zoomControl: false, doubleClickZoom: false, touchZoom: false, keyboard: false }).setView(dados.centro, 18);
  const imprimir = document.getElementById('imprimir-mapa');
  const alternar = document.getElementById('base-ruas');
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

  L.geoJSON(dados.ruas, { style: { color: '#d9dae5', opacity: .88, weight: 2 } }).addTo(mapa);
  for (const rotulo of dados.rotulos_ruas) {
    const texto = document.createElement('span');
    texto.textContent = rotulo.nome;
    L.tooltip({ permanent: true, direction: 'center', className: 'rua-label' })
      .setLatLng(rotulo.ponto).setContent(texto).addTo(mapa);
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
  L.circleMarker(dados.centro, {radius: 6, color:'#fff', weight: 2, fillColor:'#bf3119', fillOpacity: 1}).addTo(mapa);
  const mostrarRotulosLegiveis = () => {
    const container = mapa.getContainer();
    const borda = container.getBoundingClientRect();
    const ocupados = [...container.querySelectorAll('.quadra-label')].map(label => label.getBoundingClientRect());
    for (const label of container.querySelectorAll('.rua-label')) {
      const r = label.getBoundingClientRect();
      const corta = r.left < borda.left + 5 || r.right > borda.right - 5 ||
        r.top < borda.top + 5 || r.bottom > borda.bottom - 5;
      const cruza = ocupados.some(o => r.left < o.right && o.left < r.right && r.top < o.bottom && o.top < r.bottom);
      label.style.visibility = corta || cruza ? 'hidden' : '';
      if (!corta && !cruza) ocupados.push(r);
    }
  };
  const ajustar = () => {
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
    falha = false;
    alternar.setAttribute('aria-pressed', String(baseRuas));
    if (baseRuas) mapa.removeLayer(imagem);
    else imagem.addTo(mapa);
    quarteiroes.setStyle({color: baseRuas ? '#21864b' : '#88ffc1'});
    raio.setStyle({color: baseRuas ? '#b45c11' : '#ffe355'});
    verificarCarregamento();
  });
  imprimir.addEventListener('click', () => window.print());
  window.addEventListener('resize', ajustar);
  window.addEventListener('beforeprint', ajustar);
  window.addEventListener('afterprint', ajustar);
})();
