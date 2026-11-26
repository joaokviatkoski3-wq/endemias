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

    function remover() {
      if (camada && map.hasLayer(camada)) map.removeLayer(camada);
      camada = null;
      aguardando = null;
    }

    function aplicar(gl) {
      const fonte = gl.getSource('densidade');
      if (!fonte || !aguardando) return;
      fonte.setData(aguardando);
      gl.setPaintProperty('densidade', 'heatmap-radius', Number(raio.value));
    }

    async function redesenhar() {
      const sequencia = ++pedido;
      const codigo = seletor.value;
      const input = camadas.get(codigo);
      controles.hidden = !input;
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
          camada = criarMapaCalor(map, dados, Number(raio.value));
          camada.addTo(map);
          const gl = camada.getMaplibreMap();
          gl.once('load', () => { if (camada?.getMaplibreMap() === gl) aplicar(gl); });
        }
        const gl = camada.getMaplibreMap();
        aguardando = dados;
        aplicar(gl);
        nome = input.dataset.nome + (codigo === 'ovitrampas' && peso.checked ? ' · ponderado por ovos' : '');
        status.textContent = `${dados.features.length.toLocaleString('pt-BR')} pontos no cálculo. A intensidade é relativa.`;
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
    raio.addEventListener('input', () => {
      const gl = camada?.getMaplibreMap();
      if (gl?.getLayer('densidade')) gl.setPaintProperty('densidade', 'heatmap-radius', Number(raio.value));
    });
    return {
      atualizar(codigo) {
        if (codigo && seletor.value === codigo) redesenhar();
      },
      legenda() {
        return nome;
      },
      ler() {
        const codigo = seletor.value;
        return codigo ? {camada: codigo, raio: Number(raio.value),
          ponderar_ovos: codigo === 'ovitrampas' && peso.checked} : null;
      },
      restaurar(config) {
        seletor.value = config?.camada || '';
        raio.value = config?.raio ?? raio.defaultValue;
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
