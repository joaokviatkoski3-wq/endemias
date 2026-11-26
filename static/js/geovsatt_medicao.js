(() => {
  'use strict';
  const raio = 6371000;
  const radianos = Math.PI / 180;
  const limite = 120;

  function area(pontos) {
    return Math.abs(pontos.reduce((soma, atual, indice) => {
      const proximo = pontos[(indice + 1) % pontos.length];
      const diferenca = ((proximo.lng - atual.lng + 540) % 360) - 180;
      return soma + diferenca * radianos * (Math.sin(atual.lat * radianos) + Math.sin(proximo.lat * radianos));
    }, 0) * raio ** 2 / 2);
  }

  function areaSimples(pontos) {
    const giro = (a, b, c) => (b.lng - a.lng) * (c.lat - a.lat) - (b.lat - a.lat) * (c.lng - a.lng);
    const noSegmento = (a, b, c) => c.lng >= Math.min(a.lng, b.lng) && c.lng <= Math.max(a.lng, b.lng)
      && c.lat >= Math.min(a.lat, b.lat) && c.lat <= Math.max(a.lat, b.lat);
    function cruza(a, b, c, d) {
      const abC = giro(a, b, c), abD = giro(a, b, d);
      const cdA = giro(c, d, a), cdB = giro(c, d, b);
      return (abC * abD < 0 && cdA * cdB < 0) ||
        (abC === 0 && noSegmento(a, b, c)) || (abD === 0 && noSegmento(a, b, d)) ||
        (cdA === 0 && noSegmento(c, d, a)) || (cdB === 0 && noSegmento(c, d, b));
    }
    for (let i = 0; i < pontos.length - 2; i += 1) {
      for (let j = i + 2; j < pontos.length; j += 1) {
        if (i === 0 && j === pontos.length - 1) continue;
        if (cruza(pontos[i], pontos[i + 1], pontos[j], pontos[(j + 1) % pontos.length])) return false;
      }
    }
    return area(pontos) > 0.01;
  }

  function create(map) {
    const caixa = document.getElementById('geo-medicao');
    const titulo = document.getElementById('geo-medicao-titulo');
    const resultado = document.getElementById('geo-medicao-resultado');
    const desfazer = document.getElementById('geo-medicao-desfazer');
    const concluir = document.getElementById('geo-medicao-concluir');
    const limpar = document.getElementById('geo-medicao-limpar');
    const botoes = [...document.querySelectorAll('[data-medida]')];
    const desenho = L.layerGroup().addTo(map);
    const estilo = {color: '#68439a', weight: 3, fillOpacity: .16, interactive: false};
    let pontos = [];
    let modo = '';
    let ativo = false;

    const formatar = valor => valor.toLocaleString('pt-BR', {maximumFractionDigits: 2});
    const minimo = () => modo === 'area' ? 3 : 2;
    const medida = () => {
      if (modo === 'area') {
        const metros = area(pontos);
        return metros >= 10000 ? `${formatar(metros / 10000)} ha (${formatar(metros)} m²)` : `${formatar(metros)} m²`;
      }
      const metros = pontos.reduce((total, ponto, i) => i ? total + map.distance(pontos[i - 1], ponto) : total, 0);
      return metros >= 1000 ? `${formatar(metros / 1000)} km` : `${formatar(metros)} m`;
    };

    function atualizar() {
      desenho.clearLayers();
      for (const ponto of pontos) L.circleMarker(ponto, {...estilo, radius: 4, fillOpacity: 1}).addTo(desenho);
      if (modo === 'area' && pontos.length >= 3) L.polygon(pontos, estilo).addTo(desenho);
      else if (pontos.length >= 2) L.polyline(pontos, estilo).addTo(desenho);
      const visivel = Boolean(modo);
      caixa.hidden = !visivel;
      map.getContainer().classList.toggle('geo-medindo', ativo);
      botoes.forEach(botao => botao.setAttribute('aria-pressed', String(ativo && botao.dataset.medida === modo)));
      if (!visivel) return;
      titulo.textContent = modo === 'area' ? 'Área aproximada' : 'Distância';
      resultado.textContent = pontos.length < minimo()
        ? `Marque pelo menos ${minimo()} pontos no mapa.`
        : `${medida()}${ativo ? ' · acrescente pontos ou conclua' : ''}`;
      desfazer.disabled = !ativo || !pontos.length;
      concluir.hidden = !ativo;
      concluir.disabled = pontos.length < minimo();
    }

    botoes.forEach(botao => botao.addEventListener('click', () => {
      modo = botao.dataset.medida;
      pontos = [];
      ativo = true;
      atualizar();
    }));
    map.on('click', event => {
      if (!ativo) return;
      if (pontos.length >= limite) {
        resultado.textContent = `Limite de ${limite} pontos. Conclua ou desfaça um ponto.`;
        return;
      }
      if (pontos.some(ponto => ponto.equals(event.latlng))) return;
      pontos.push(event.latlng);
      atualizar();
    });
    desfazer.addEventListener('click', () => {
      pontos.pop();
      atualizar();
    });
    concluir.addEventListener('click', () => {
      if (modo === 'area' && !areaSimples(pontos)) {
        resultado.textContent = 'Desfaça um ponto para corrigir o contorno. A área precisa ser fechada sem cruzamentos.';
        return;
      }
      ativo = false;
      atualizar();
    });
    limpar.addEventListener('click', () => {
      ativo = false;
      pontos = [];
      modo = '';
      atualizar();
    });
    return {active: () => ativo};
  }

  window.GeoVSATTMedicao = {create};
})();
