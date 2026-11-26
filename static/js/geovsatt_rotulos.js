(() => {
  'use strict';
  const namespace = 'http://www.w3.org/2000/svg';

  function svg(tag, atributos = {}) {
    const element = document.createElementNS(namespace, tag);
    for (const [nome, valor] of Object.entries(atributos)) element.setAttribute(nome, String(valor));
    return element;
  }

  function linhas(latlngs) {
    if (!latlngs?.length) return [];
    return Array.isArray(latlngs[0]) ? latlngs.flatMap(linhas) : [latlngs];
  }

  function maiorTrecho(map, layer, recorte) {
    let pontos = [];
    let comprimento = 0;
    for (const linha of linhas(layer.getLatLngs())) {
      let anterior;
      let trecho = [];
      let distancia = 0;
      for (const coordenada of linha) {
        const atual = map.latLngToContainerPoint(coordenada);
        const segmento = anterior && L.LineUtil.clipSegment(anterior, atual, recorte);
        anterior = atual;
        if (!segmento) {
          trecho = [];
          distancia = 0;
          continue;
        }
        const [inicio, fim] = segmento;
        if (!trecho.at(-1)?.equals(inicio)) {
          trecho = [inicio];
          distancia = 0;
        }
        trecho.push(fim);
        distancia += inicio.distanceTo(fim);
        if (distancia > comprimento) {
          pontos = trecho;
          comprimento = distancia;
        }
      }
    }
    if (!pontos.length) return null;
    return {pontos, comprimento};
  }

  function centroDaLinha(pontos, comprimento) {
    let falta = comprimento / 2;
    for (let i = 1; i < pontos.length; i += 1) {
      const de = pontos[i - 1];
      const ate = pontos[i];
      const tamanho = de.distanceTo(ate);
      if (tamanho && falta <= tamanho) return de.add(ate.subtract(de).multiplyBy(falta / tamanho));
      falta -= tamanho;
    }
    return pontos.at(-1);
  }

  function create(map) {
    const centros = [];
    const eixos = [];
    const pane = map.createPane('geo-rotulos');
    const overlay = svg('svg', {class: 'geo-rotulos', 'aria-hidden': 'true'});
    pane.append(overlay);
    let frame = null;
    let movimentando = false;

    function desenhar() {
      frame = null;
      const zoom = map.getZoom();
      overlay.replaceChildren();
      if (movimentando) return;
      const {x: largura, y: altura} = map.getSize();
      overlay.setAttribute('width', largura);
      overlay.setAttribute('height', altura);
      overlay.setAttribute('viewBox', `0 0 ${largura} ${altura}`);
      L.DomUtil.setPosition(overlay, map.containerPointToLayerPoint([0, 0]));
      const recorte = L.bounds([[16, 26], [largura - 16, altura - 22]]);
      const vista = map.getBounds();
      const ocupadas = [];
      const maximo = largura < 700 ? 12 : 24;
      const aceitar = (ponto, largura, altura) => {
        const caixa = L.bounds([ponto.subtract([largura / 2, altura / 2]), ponto.add([largura / 2, altura / 2])]);
        if (!recorte.contains(caixa) || ocupadas.some(item => item.intersects(caixa))) return false;
        ocupadas.push(caixa);
        return true;
      };
      const desenho = document.createDocumentFragment();

      let quantidade = 0;
      const porGrupo = new Map();
      for (const {layer, nome, bounds, options} of centros) {
        if (zoom < options.zoom || !map.hasLayer(layer) || !vista.intersects(bounds)) continue;
        if ((porGrupo.get(options.group) || 0) >= Math.ceil(maximo / 2)) continue;
        const centro = layer.getLatLng?.() || (layer instanceof L.Polygon ? layer.getCenter() : bounds.getCenter());
        const ponto = map.latLngToContainerPoint(centro);
        if (!aceitar(ponto, nome.length * options.size * .57 + 14, options.size + 8)) continue;
        const texto = svg('text', {x: ponto.x, y: ponto.y, class: 'geo-rotulo-quadra',
          fill: options.color || '#24362b', 'font-size': options.size,
          'text-anchor': 'middle', 'dominant-baseline': 'central'});
        texto.textContent = nome;
        desenho.append(texto);
        porGrupo.set(options.group, (porGrupo.get(options.group) || 0) + 1);
        if (++quantidade >= maximo) break;
      }

      {
        const porNome = new Map();
        for (const {layer, nome, bounds, options} of eixos) {
          if (zoom < options.zoom || !map.hasLayer(layer) || !vista.intersects(bounds)) continue;
          const trecho = maiorTrecho(map, layer, recorte);
          if (!trecho || trecho.comprimento < nome.length * options.size * .57 + 16) continue;
          const chave = `${options.group}:${nome}`;
          if (!porNome.has(chave) || porNome.get(chave).comprimento < trecho.comprimento) {
            porNome.set(chave, {...trecho, nome, options});
          }
        }
        let quantidade = 0;
        const trechos = [...porNome.values()].sort((a, b) => b.comprimento - a.comprimento);
        for (const {nome, pontos, comprimento, options} of trechos) {
          const centro = centroDaLinha(pontos, comprimento);
          if (!aceitar(centro, Math.min(nome.length * options.size * .57 + 16, 220), options.size + 15)) continue;
          if (pontos.at(-1).x < pontos[0].x) pontos.reverse();
          const id = `geovsatt-eixo-${quantidade}`;
          const path = svg('path', {
            id, d: pontos.map((ponto, i) => `${i ? 'L' : 'M'}${ponto.x},${ponto.y}`).join(' '),
            fill: 'none', stroke: 'none',
          });
          const texto = svg('text', {class: 'geo-rotulo-rua', 'text-anchor': 'middle', dy: -3,
            fill: options.color || '#24362b', 'font-size': options.size});
          const trilha = svg('textPath', {href: `#${id}`, startOffset: '50%'});
          trilha.textContent = nome;
          texto.append(trilha);
          desenho.append(path, texto);
          if (++quantidade >= maximo) break;
        }
      }
      overlay.append(desenho);
    }

    function schedule() {
      if (frame === null) frame = requestAnimationFrame(desenhar);
    }

    map.on('movestart zoomstart', () => {
      movimentando = true;
      overlay.replaceChildren();
    });
    map.on('moveend', () => {
      movimentando = false;
      schedule();
    });
    map.on('resize', schedule);
    return {
      schedule,
      clearGroup(group) {
        for (const lista of [centros, eixos]) {
          for (let i = lista.length - 1; i >= 0; i -= 1) {
            if (lista[i].options.group === group) lista.splice(i, 1);
          }
        }
      },
      add(layer, nome, options) {
        const point = layer.getLatLng?.();
        const bounds = layer.getBounds?.() || (point && L.latLngBounds([point, point]));
        if (!bounds?.isValid()) return;
        (options.along ? eixos : centros).push({layer, bounds, options, nome: String(nome).slice(0, 90)});
      },
    };
  }

  window.GeoVSATTRotulos = {create};
})();
