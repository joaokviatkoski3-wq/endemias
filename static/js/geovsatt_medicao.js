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

  function create(map, calcularPopulacao) {
    const caixa = document.getElementById('geo-medicao');
    const titulo = document.getElementById('geo-medicao-titulo');
    const resultado = document.getElementById('geo-medicao-resultado');
    const desfazer = document.getElementById('geo-medicao-desfazer');
    const concluir = document.getElementById('geo-medicao-concluir');
    const limpar = document.getElementById('geo-medicao-limpar');
    const opcoesPopulacao = document.getElementById('geo-populacao');
    const incluirCondominios = document.getElementById('geo-incluir-condominios');
    const cobertura = document.getElementById('geo-populacao-cobertura');
    const botoes = [...document.querySelectorAll('[data-medida]')];
    const desenho = L.layerGroup().addTo(map);
    const estilo = {color: '#68439a', weight: 3, fillOpacity: .16, interactive: false};
    let pontos = [];
    let modo = '';
    let ativo = false;
    let versao = 0;
    let estimativa = '';

    const formatar = valor => valor.toLocaleString('pt-BR', {maximumFractionDigits: 2});
    const fechaArea = () => modo !== 'distancia';
    const minimo = () => fechaArea() ? 3 : 2;
    const medida = () => {
      if (fechaArea()) {
        const metros = area(pontos);
        return metros >= 10000 ? `${formatar(metros / 10000)} ha (${formatar(metros)} m²)` : `${formatar(metros)} m²`;
      }
      const metros = pontos.reduce((total, ponto, i) => i ? total + map.distance(pontos[i - 1], ponto) : total, 0);
      return metros >= 1000 ? `${formatar(metros / 1000)} km` : `${formatar(metros)} m`;
    };

    function atualizar() {
      desenho.clearLayers();
      for (const ponto of pontos) L.circleMarker(ponto, {...estilo, radius: 4, fillOpacity: 1}).addTo(desenho);
      if (fechaArea() && pontos.length >= 3) L.polygon(pontos, estilo).addTo(desenho);
      else if (pontos.length >= 2) L.polyline(pontos, estilo).addTo(desenho);
      const visivel = Boolean(modo);
      caixa.hidden = !visivel;
      opcoesPopulacao.hidden = modo !== 'populacao';
      map.getContainer().classList.toggle('geo-medindo', ativo);
      botoes.forEach(botao => botao.setAttribute('aria-pressed', String(ativo && botao.dataset.medida === modo)));
      if (!visivel) return;
      titulo.textContent = {area: 'Área aproximada', distancia: 'Distância', populacao: 'População por área'}[modo];
      resultado.textContent = pontos.length < minimo()
        ? `Marque pelo menos ${minimo()} pontos no mapa.`
        : `${medida()}${ativo ? ' · acrescente pontos ou conclua' : ''}`;
      desfazer.disabled = !ativo || !pontos.length;
      concluir.hidden = !ativo;
      concluir.disabled = pontos.length < minimo();
    }

    async function atualizarPopulacao() {
      const pedido = ++versao;
      estimativa = '';
      resultado.textContent = `${medida()} · Calculando população…`;
      cobertura.textContent = '';
      try {
        const dados = await calcularPopulacao(pontos.map(({lat, lng}) => [lng, lat]), incluirCondominios.checked);
        if (pedido !== versao) return;
        const pessoas = dados.populacao_estimada;
        estimativa = pessoas == null ? '' : `População estimada de ${formatar(pessoas)} ${pessoas === 1 ? 'pessoa' : 'pessoas'}`;
        resultado.textContent = `${medida()} · ${estimativa || 'Área sem dados de imóveis no RG'}`;
        const total = dados.quarteiroes_com_cadastro + dados.quarteiroes_sem_cadastro;
        if (!total) {
          cobertura.textContent = 'Nenhum quarteirão da malha cruza a área desenhada.';
          return;
        }
        const detalhes = [`RG em ${formatar(dados.quarteiroes_com_cadastro)} de ${formatar(total)} quarteirões do recorte.`];
        if (pessoas != null) {
          detalhes.push(`${formatar(dados.residencias_equivalentes)} residências equivalentes × ${formatar(dados.media_pessoas_por_residencia)} pessoas por residência (${dados.fonte_populacao.replace(/^Fonte:\s*/i, '')}).`);
          if (dados.quarteiroes_parciais) detalhes.push('Quarteirões cortados pelo contorno são ponderados pela proporção da área incluída.');
        }
        cobertura.textContent = detalhes.join(' ');
      } catch (erro) {
        if (pedido === versao) resultado.textContent = erro.message;
      }
    }

    botoes.forEach(botao => botao.addEventListener('click', () => {
      versao += 1;
      modo = botao.dataset.medida;
      pontos = [];
      ativo = true;
      estimativa = '';
      cobertura.textContent = '';
      map.closePopup();
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
      if (fechaArea() && !areaSimples(pontos)) {
        resultado.textContent = 'Desfaça um ponto para corrigir o contorno. A área precisa ser fechada sem cruzamentos.';
        return;
      }
      ativo = false;
      atualizar();
      if (modo === 'populacao') atualizarPopulacao();
    });
    incluirCondominios.addEventListener('change', () => {
      if (modo === 'populacao' && !ativo) atualizarPopulacao();
    });
    limpar.addEventListener('click', () => {
      versao += 1;
      ativo = false;
      pontos = [];
      modo = '';
      estimativa = '';
      atualizar();
    });
    return {
      active: () => ativo,
      concluida: () => Boolean(modo && !ativo && pontos.length >= minimo()),
      descricao() {
        if (!this.concluida()) return '';
        if (modo === 'populacao') return estimativa ? `${estimativa} na área de ${medida()} · Registro Geográfico / ${cobertura.textContent}` : `Área selecionada de ${medida()}`;
        return `${titulo.textContent} de ${medida()}`;
      },
      mostrar(visivel) {
        if (visivel) desenho.addTo(map);
        else desenho.remove();
      },
    };
  }

  window.GeoVSATTMedicao = {create};
})();
