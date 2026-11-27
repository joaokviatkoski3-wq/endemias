(() => {
  'use strict';

  function pontosParaCalor(grupo, codigo, porOvos) {
    const features = [];
    grupo.eachLayer(({feature}) => {
      const {geometry, properties = {}} = feature;
      const peso = codigo === 'ovitrampas' && porOvos ? Number(properties.ovos || 0) :
        codigo === 'esporotricose' ? Number(properties.animais || 1) : 1;
      if (!Number.isFinite(peso) || peso < 1) return;
      const pontos = geometry.type === 'Point' ? [geometry.coordinates] :
        geometry.type === 'MultiPoint' ? geometry.coordinates : [];
      for (const coordinates of pontos) {
        features.push({type: 'Feature', geometry: {type: 'Point', coordinates}, properties: {peso}});
      }
    });
    return {type: 'FeatureCollection', features};
  }

  function criar(map, opcoes, obterCamada, atualizarLegenda) {
    const versao = encodeURIComponent(document.documentElement.dataset.versao);
    const secao = document.getElementById('geo-calor');
    const seletor = document.getElementById('geo-calor-camada');
    const controles = document.getElementById('geo-calor-opcoes');
    const raio = document.getElementById('geo-calor-raio');
    const intensidade = document.getElementById('geo-calor-intensidade');
    const opacidade = document.getElementById('geo-calor-opacidade');
    const filtros = document.getElementById('geo-calor-filtros');
    const rotuloPeso = document.getElementById('geo-calor-peso');
    const peso = rotuloPeso.querySelector('input');
    const status = document.getElementById('geo-calor-status');
    const camadas = new Map(opcoes.filter(input => input.dataset.tipo === 'ponto')
      .map(input => [input.dataset.layer, input]));
    for (const [codigo, input] of camadas) seletor.add(new Option(input.dataset.nome, codigo));
    secao.hidden = !camadas.size;
    map.createPane('heatmap').style.zIndex = 385;
    let camada;
    let aguardando;
    let pedido = 0;
    let nome = '';
    let calculando = false;
    let erroNoDesenho = false;
    let painelDeOrigem;

    function mostrarFiltros(input) {
      if (painelDeOrigem?.input === input) return;
      if (painelDeOrigem) {
        const {container, link, input: anterior} = painelDeOrigem;
        delete container.dataset.noCalor;
        link.replaceWith(container);
        container.hidden = !anterior.checked || !container.childElementCount;
        painelDeOrigem = null;
      }
      const container = input && document.getElementById('geo-filter-' + input.dataset.layer);
      if (!container?.childElementCount) return;
      const link = document.createElement('a');
      link.className = 'geo-calor-atalho';
      link.textContent = 'Filtros no painel do mapa de calor';
      link.href = '#geo-calor-filtros';
      container.before(link);
      filtros.append(container);
      container.dataset.noCalor = '1';
      container.hidden = false;
      const detalhe = container.querySelector('details');
      if (detalhe) detalhe.open = true;
      painelDeOrigem = {container, link, input};
    }

    function visual() {
      return {raio: Number(raio.value), intensidade: Number(intensidade.value), opacidade: Number(opacidade.value)};
    }

    function escreverVisual(gl) {
      const opcoes = visual();
      for (const controle of [raio, intensidade, opacidade]) {
        const unidade = controle === raio ? ' px' : '%';
        controles.querySelector(`output[for="${controle.id}"]`).value = controle.value + unidade;
      }
      if (!gl?.getLayer('densidade')) return;
      gl.setPaintProperty('densidade', 'heatmap-radius', opcoes.raio);
      gl.setPaintProperty('densidade', 'heatmap-intensity', opcoes.intensidade / 100);
      gl.setPaintProperty('densidade', 'heatmap-opacity', opcoes.opacidade / 100);
    }

    function remover() {
      if (camada && map.hasLayer(camada)) map.removeLayer(camada);
      camada = null;
      aguardando = null;
    }

    function aplicar(gl) {
      const fonte = gl.getSource('densidade');
      if (!fonte || !aguardando) return;
      fonte.setData(aguardando);
      escreverVisual(gl);
    }

    async function redesenhar() {
      const sequencia = ++pedido;
      const codigo = seletor.value;
      const input = camadas.get(codigo);
      if (painelDeOrigem?.input !== input) mostrarFiltros();
      controles.hidden = !input;
      escreverVisual();
      rotuloPeso.hidden = codigo !== 'ovitrampas';
      nome = '';
      calculando = Boolean(input);
      erroNoDesenho = false;
      if (!input) {
        remover();
        atualizarLegenda();
        return;
      }
      status.textContent = 'Calculando a densidade…';
      try {
        const grupo = await obterCamada(input);
        if (sequencia !== pedido || !grupo) return;
        mostrarFiltros(input);
        const dados = pontosParaCalor(grupo, codigo, peso.checked);
        if (!dados.features.length) {
          remover();
          status.textContent = 'Nenhum ponto para os filtros e o peso selecionados.';
          atualizarLegenda();
          return;
        }
        if (!camada) {
          const {criarMapaCalor} = await import(`/static/js/geovsatt_vetorial.mjs?v=${versao}`);
          if (sequencia !== pedido) return;
          camada = criarMapaCalor(map, dados, visual());
          camada.addTo(map);
          const gl = camada.getMaplibreMap();
          gl.once('load', () => { if (camada?.getMaplibreMap() === gl) aplicar(gl); });
        }
        const gl = camada.getMaplibreMap();
        aguardando = dados;
        aplicar(gl);
        nome = input.dataset.nome + (codigo === 'ovitrampas' && peso.checked ? ' · ponderado por ovos' : '');
        const total = dados.features.length;
        status.textContent = `${total.toLocaleString('pt-BR')} ${total === 1 ? 'ponto' : 'pontos'} no cálculo. A intensidade é relativa.`;
      } catch (erro) {
        if (sequencia !== pedido) return;
        remover();
        erroNoDesenho = true;
        status.textContent = erro.message || 'Não foi possível desenhar o mapa de calor neste aparelho.';
      } finally {
        if (sequencia === pedido) calculando = false;
      }
      atualizarLegenda();
    }

    seletor.addEventListener('change', redesenhar);
    peso.addEventListener('change', redesenhar);
    for (const controle of [raio, intensidade, opacidade]) {
      controle.addEventListener('input', () => escreverVisual(camada?.getMaplibreMap()));
    }
    return {
      atualizar(codigo) {
        if (codigo && seletor.value === codigo) redesenhar();
      },
      legenda() {
        return nome;
      },
      ler() {
        const codigo = seletor.value;
        return codigo ? {camada: codigo, ...visual(),
          ponderar_ovos: codigo === 'ovitrampas' && peso.checked} : null;
      },
      restaurar(config) {
        seletor.value = config?.camada || '';
        raio.value = config?.raio ?? raio.defaultValue;
        intensidade.value = config?.intensidade ?? intensidade.defaultValue;
        opacidade.value = config?.opacidade ?? opacidade.defaultValue;
        peso.checked = Boolean(config?.ponderar_ovos);
        return redesenhar();
      },
      estado() {
        if (erroNoDesenho) return 'erro';
        const gl = camada?.getMaplibreMap();
        if (calculando || (gl && (!gl.getSource('densidade') || !gl.isSourceLoaded('densidade')))) return 'carregando';
        return 'pronta';
      },
    };
  }

  window.GeoVSATTCalor = {criar};
})();
