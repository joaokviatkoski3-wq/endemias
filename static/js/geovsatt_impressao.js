(() => {
  'use strict';

  function create(map, seletorBase, medicao, carregandoBase, opcoesCamadas, alternarCamada, itensLegenda) {
    const botao = document.getElementById('geo-imprimir');
    const dialogo = document.getElementById('geo-composicao');
    const formulario = document.getElementById('geo-composicao-form');
    const folha = document.getElementById('geo-folha');
    const espaco = folha.parentElement;
    const rolagem = espaco.parentElement;
    const mapa = map.getContainer();
    const mapaOriginal = mapa.parentElement;
    const mapaNaFolha = folha.querySelector('.geo-folha-mapa');
    const medidaNaFolha = document.getElementById('geo-folha-medida');
    const legendaOriginal = document.getElementById('geo-legend');
    const legendaNaFolha = document.getElementById('geo-folha-legenda');
    const status = document.getElementById('geo-composicao-status');
    const listaCamadas = document.getElementById('geo-composicao-camadas');
    const escala = L.control.scale({imperial: false, maxWidth: 125, position: 'bottomleft'});
    const {titulo, orientacao, layout, base, nota, legenda, medicoes} = formulario.elements;
    const instrucao = 'Arraste ou ajuste o zoom para definir o recorte.';
    let vista;

    function ajustarPrevia() {
      if (!dialogo.open) return;
      const largura = folha.offsetWidth;
      const altura = folha.offsetHeight;
      const fator = Math.max(.28, Math.min(1, (rolagem.clientWidth - 30) / largura, (rolagem.clientHeight - 30) / altura));
      espaco.style.width = `${largura * fator}px`;
      espaco.style.height = `${altura * fator}px`;
      folha.style.transform = `scale(${fator})`;
    }

    function atualizarFolha() {
      folha.dataset.orientacao = orientacao.value;
      folha.dataset.layout = layout.value;
      document.getElementById('geo-folha-titulo').textContent = titulo.value.trim() || 'Mapa territorial';
      const observacao = document.getElementById('geo-folha-nota');
      observacao.textContent = nota.value.trim();
      observacao.hidden = !observacao.textContent;
      legendaNaFolha.replaceChildren(...(legenda.checked ? itensLegenda(map.getBounds()).map(copiarLegenda) : []));
      legendaNaFolha.hidden = !legenda.checked || !legendaNaFolha.childElementCount;
      folha.classList.toggle('geo-folha-sem-legenda', legendaNaFolha.hidden);
      medidaNaFolha.textContent = medicao.descricao();
      medidaNaFolha.hidden = !medicoes.checked || !medidaNaFolha.textContent;
      medicao.mostrar(medicoes.checked);
      map.invalidateSize({animate: false});
      ajustarPrevia();
    }

    function copiarLegenda(item) {
      const categorias = JSON.parse(item.dataset.categorias || '[]');
      if (!categorias.length) return item.cloneNode(true);
      const grupo = document.createElement('div');
      grupo.className = 'geo-legenda-grupo';
      const nome = document.createElement('strong');
      nome.textContent = item.textContent;
      grupo.append(nome);
      const limite = 24;
      for (const [valor, cor] of categorias.slice(0, limite)) {
        const entrada = document.createElement('span');
        const simbolo = item.querySelector('i').cloneNode(true);
        simbolo.style.setProperty('--legend-color', cor);
        entrada.append(simbolo, document.createTextNode(valor));
        grupo.append(entrada);
      }
      if (categorias.length > limite) {
        const mais = document.createElement('small');
        mais.textContent = `+ ${categorias.length - limite} categorias`;
        grupo.append(mais);
      }
      return grupo;
    }

    function atualizarCamadas() {
      listaCamadas.replaceChildren(...opcoesCamadas.map(camada => {
        const rotulo = document.createElement('label');
        const campo = document.createElement('input');
        campo.type = 'checkbox';
        campo.dataset.camada = camada.dataset.layer;
        campo.checked = camada.checked;
        rotulo.append(campo, document.createTextNode(camada.dataset.nome));
        campo.addEventListener('change', async () => {
          const sessao = vista;
          camada.checked = campo.checked;
          sessao.pendentes += 1;
          status.textContent = 'Atualizando camadas da folha…';
          try {
            await alternarCamada(camada);
            if (vista === sessao && dialogo.open) status.textContent = instrucao;
          } catch (erro) {
            if (vista === sessao && dialogo.open) {
              campo.checked = camada.checked = false;
              status.textContent = `${camada.dataset.nome}: ${erro.message}`;
            }
          } finally {
            sessao.pendentes -= 1;
          }
        });
        return rotulo;
      }));
    }

    function mudarBase(valor) {
      if (seletorBase.value === valor) return;
      seletorBase.value = valor;
      seletorBase.dispatchEvent(new Event('change'));
    }

    botao.addEventListener('click', () => {
      if (mapa.parentElement !== mapaOriginal) return;
      if (medicao.active()) {
        document.getElementById('geo-medicao-resultado').textContent = 'Conclua ou limpe o desenho antes de compor o mapa.';
        return;
      }
      map.stop();
      vista = {centro: map.getCenter(), zoom: map.getZoom(), limites: map.getBounds(), base: seletorBase.value,
        camadas: new Map(opcoesCamadas.map(camada => [camada, camada.checked])), pendentes: 0};
      atualizarCamadas();
      base.replaceChildren(...Array.from(seletorBase.options, opcao => opcao.cloneNode(true)));
      base.value = vista.base;
      medicoes.checked = true;
      status.textContent = instrucao;
      const data = new Date();
      const carimbo = document.getElementById('geo-folha-data');
      carimbo.dateTime = data.toISOString();
      carimbo.textContent = data.toLocaleDateString('pt-BR');
      map.closePopup();
      dialogo.showModal();
      document.body.classList.add('geo-impressao-aberta');
      mapaNaFolha.prepend(mapa);
      escala.addTo(map);
      atualizarFolha();
      map.fitBounds(vista.limites, {animate: false, maxZoom: vista.zoom});
      atualizarFolha();
    });

    document.getElementById('geo-composicao-fechar').addEventListener('click', () => dialogo.close());
    dialogo.addEventListener('close', () => {
      map.stop();
      escala.remove();
      mapaOriginal.prepend(mapa);
      document.body.classList.remove('geo-impressao-aberta');
      medicao.mostrar(true);
      mudarBase(vista.base);
      for (const [camada, selecionada] of vista.camadas) {
        if (camada.checked === selecionada) continue;
        camada.checked = selecionada;
        camada.dispatchEvent(new Event('change'));
      }
      map.invalidateSize({animate: false});
      map.setView(vista.centro, vista.zoom, {animate: false});
      botao.focus();
    });
    formulario.addEventListener('input', event => {
      if (event.target.dataset.camada) return;
      if (event.target === base) mudarBase(base.value);
      status.textContent = instrucao;
      atualizarFolha();
    });
    formulario.addEventListener('submit', event => {
      event.preventDefault();
      if (vista.pendentes) {
        status.textContent = 'Aguarde as camadas da folha terminarem de carregar.';
        return;
      }
      atualizarFolha();
      if (carregandoBase()) {
        status.textContent = 'Aguarde a imagem-base terminar de carregar e tente novamente.';
        return;
      }
      window.print();
    });
    new ResizeObserver(ajustarPrevia).observe(rolagem);
    new MutationObserver(() => { if (dialogo.open) atualizarFolha(); }).observe(legendaOriginal, {childList: true});
    map.on('dragend zoomend', () => { if (dialogo.open) atualizarFolha(); });
  }

  window.GeoVSATTImpressao = {create};
})();
