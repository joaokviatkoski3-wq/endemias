(() => {
  'use strict';

  function create(map, seletorBase, medicao, estadoBase, opcoesCamadas, alternarCamada, itensLegenda, acesso) {
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
    const controlesCalor = document.getElementById('geo-calor');
    const lugarCalor = document.createComment('');
    controlesCalor.after(lugarCalor);
    const salvas = document.getElementById('geo-composicao-salvas');
    const abrirSalva = document.getElementById('geo-composicao-abrir');
    const criarSalva = document.getElementById('geo-composicao-nova');
    const atualizarSalva = document.getElementById('geo-composicao-atualizar');
    const endpoint = '/api/geovsatt/composicoes';
    const escala = L.control.scale({imperial: false, maxWidth: 125, position: 'bottomleft'});
    const {titulo, orientacao, layout, base, nota, legenda, medicoes} = formulario.elements;
    const instrucao = 'Arraste ou ajuste o zoom para definir o recorte.';
    let vista;
    let projetoAtual;

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

    function atualizarBotoes() {
      const ocupado = vista.ocupada;
      abrirSalva.disabled = ocupado || !salvas.value;
      criarSalva.disabled = ocupado;
      atualizarSalva.disabled = ocupado || Number(salvas.value) !== projetoAtual?.id_composicao;
    }

    async function carregarLista(sessao, selecionada = '') {
      const listagem = sessao.listagem = (sessao.listagem || 0) + 1;
      const itens = await acesso.api(endpoint);
      if (vista !== sessao || sessao.listagem !== listagem || !dialogo.open) return;
      salvas.replaceChildren(new Option('Selecione uma composição', ''),
        ...itens.map(item => new Option(item.titulo, item.id_composicao)));
      salvas.value = selecionada;
      atualizarBotoes();
    }

    function lerComposicao() {
      const centro = map.getCenter().wrap();
      const camadas = opcoesCamadas.filter(camada => camada.checked).map(camada => camada.dataset.layer);
      const calor = acesso.calor.ler();
      const fontes = new Set(camadas);
      if (calor) fontes.add(calor.camada);
      const filtros = Object.fromEntries([...fontes].map(codigo => [codigo, acesso.filtrosPorCamada.get(codigo)?.ler() || []])
        .filter(([, regras]) => regras.length));
      return {titulo: titulo.value.trim() || 'Mapa territorial', nota: nota.value.trim(), orientacao: orientacao.value,
        layout: layout.value, base: base.value, legenda: legenda.checked,
        centro: [centro.lat, centro.lng], zoom: map.getZoom(), camadas, filtros, ...(calor ? {calor} : {})};
    }

    async function salvarComposicao(nova) {
      const dados = lerComposicao();
      const caminho = nova ? endpoint : `${endpoint}/${projetoAtual.id_composicao}`;
      if (!nova) dados.atualizada_em = projetoAtual.atualizada_em;
      return acesso.api(caminho, {method: nova ? 'POST' : 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
        body: JSON.stringify(dados)});
    }

    async function aplicarComposicao(sessao, projeto) {
      const dados = projeto.configuracao;
      titulo.value = dados.titulo;
      nota.value = dados.nota;
      orientacao.value = dados.orientacao;
      layout.value = dados.layout;
      base.value = dados.base;
      legenda.checked = dados.legenda;
      medicoes.checked = false;
      mudarBase(dados.base);
      acesso.calor.restaurar(null);
      const selecionadas = new Set(dados.camadas);
      let calorIndisponivel = projeto.calor_indisponivel;
      const resultados = await Promise.allSettled(opcoesCamadas.map(async camada => {
        const codigo = camada.dataset.layer;
        const regras = dados.filtros[codigo] || [];
        const fonteCalor = codigo === dados.calor?.camada;
        camada.checked = selecionadas.has(codigo);
        try {
          await alternarCamada(camada, regras);
          if (fonteCalor && !camada.checked) await acesso.carregarCamada(camada);
        } catch (erro) {
          if (fonteCalor) calorIndisponivel = true;
          if (vista === sessao && dialogo.open) {
            camada.checked = false;
            await alternarCamada(camada);
          }
          throw erro;
        }
        if (vista !== sessao || !dialogo.open || (!camada.checked && !fonteCalor)) return 0;
        const filtros = acesso.filtrosPorCamada.get(codigo);
        return filtros?.consultar ? 0 : (filtros?.restaurar(regras) ?? regras.length);
      }));
      if (vista !== sessao || !dialogo.open) return;
      atualizarCamadas();
      map.setView(dados.centro, dados.zoom, {animate: false});
      if (dados.calor && !calorIndisponivel) await acesso.calor.restaurar(dados.calor);
      if (vista !== sessao || !dialogo.open) return;
      atualizarFolha();
      const descartados = resultados.reduce((total, resultado) => total + (resultado.value || 0), 0);
      const falhas = resultados.filter(resultado => resultado.status === 'rejected').length;
      const avisos = [];
      if (projeto.camadas_indisponiveis || falhas) avisos.push(`${projeto.camadas_indisponiveis + falhas} camada(s) indisponível(is).`);
      if (projeto.base_indisponivel) avisos.push('Use o seletor para escolher outra imagem-base.');
      if (calorIndisponivel) avisos.push('A camada de origem do mapa de calor está indisponível.');
      if (acesso.calor.estado() === 'erro') avisos.push('Não foi possível desenhar o mapa de calor.');
      if (descartados) avisos.push(`${descartados} filtro(s) indisponível(is) na versão atual.`);
      status.textContent = ['Composição aberta.', ...avisos].join(' ');
    }

    async function operarProjeto(acao, execucao) {
      if (!dialogo.open || vista.ocupada) return;
      if (camadasPendentes()) {
        status.textContent = 'Aguarde as camadas da folha terminarem de carregar.';
        return;
      }
      const sessao = vista;
      sessao.ocupada = true;
      atualizarBotoes();
      status.textContent = acao;
      try {
        await execucao(sessao);
      } catch (erro) {
        if (vista === sessao && dialogo.open) status.textContent = erro.message;
      } finally {
        sessao.ocupada = false;
        if (vista === sessao && dialogo.open) atualizarBotoes();
      }
    }

    salvas.addEventListener('change', atualizarBotoes);
    abrirSalva.addEventListener('click', () => operarProjeto('Abrindo composição…', async sessao => {
      const projeto = await acesso.api(`${endpoint}/${salvas.value}`);
      if (vista !== sessao || !dialogo.open) return;
      projetoAtual = projeto;
      await aplicarComposicao(sessao, projeto);
    }));
    for (const [botao, nova] of [[criarSalva, true], [atualizarSalva, false]]) {
      botao.addEventListener('click', () => operarProjeto('Salvando composição…', async sessao => {
        const projeto = await salvarComposicao(nova);
        if (vista !== sessao || !dialogo.open) return;
        projetoAtual = projeto;
        await carregarLista(sessao, String(projeto.id_composicao));
        if (vista === sessao && dialogo.open) {
          status.textContent = window.GeoVSATTCampo ? 'Composição salva na cópia deste aparelho.' : 'Composição salva para sua conta.';
        }
      }));
    }

    botao.addEventListener('click', () => {
      if (mapa.parentElement !== mapaOriginal) return;
      if (medicao.active()) {
        document.getElementById('geo-medicao-resultado').textContent = 'Conclua ou limpe o desenho antes de compor o mapa.';
        return;
      }
      map.stop();
      vista = {centro: map.getCenter(), zoom: map.getZoom(), limites: map.getBounds(), base: seletorBase.value,
        calor: acesso.calor.ler(),
        camadas: new Map(opcoesCamadas.map(camada => [camada, camada.checked])), pendentes: 0, ocupada: false,
        filtros: new Map([...acesso.filtrosPorCamada].map(([codigo, filtros]) => [codigo, filtros.ler()]))};
      projetoAtual = null;
      salvas.replaceChildren(new Option('Selecione uma composição', ''));
      atualizarBotoes();
      atualizarCamadas();
      base.replaceChildren(...Array.from(seletorBase.children, opcao => opcao.cloneNode(true)));
      base.value = vista.base;
      medicoes.checked = true;
      status.textContent = instrucao;
      const data = new Date();
      const carimbo = document.getElementById('geo-folha-data');
      carimbo.dateTime = data.toISOString();
      carimbo.textContent = data.toLocaleDateString('pt-BR');
      map.closePopup();
      document.getElementById('geo-composicao-calor').append(controlesCalor);
      dialogo.showModal();
      document.body.classList.add('geo-impressao-aberta');
      mapaNaFolha.prepend(mapa);
      escala.addTo(map);
      atualizarFolha();
      map.fitBounds(vista.limites, {animate: false, maxZoom: vista.zoom});
      atualizarFolha();
      const sessao = vista;
      carregarLista(sessao).catch(erro => { if (vista === sessao && dialogo.open) status.textContent = erro.message; });
    });

    document.getElementById('geo-composicao-fechar').addEventListener('click', () => dialogo.close());
    dialogo.addEventListener('close', () => {
      map.stop();
      escala.remove();
      mapaOriginal.prepend(mapa);
      lugarCalor.before(controlesCalor);
      document.body.classList.remove('geo-impressao-aberta');
      medicao.mostrar(true);
      mudarBase(vista.base);
      const alternadas = [];
      for (const [camada, selecionada] of vista.camadas) {
        if (camada.checked === selecionada) continue;
        camada.checked = selecionada;
        alternadas.push(camada);
      }
      for (const [codigo, filtros] of acesso.filtrosPorCamada) {
        const resultado = filtros.restaurar(vista.filtros.get(codigo) || []);
        resultado?.catch?.(() => {});
      }
      for (const camada of alternadas) camada.dispatchEvent(new Event('change'));
      acesso.calor.restaurar(vista.calor);
      map.invalidateSize({animate: false});
      map.setView(vista.centro, vista.zoom, {animate: false});
      botao.focus();
    });
    formulario.addEventListener('input', event => {
      if (event.target.dataset.camada || event.target === salvas) return;
      if (event.target === base) mudarBase(base.value);
      status.textContent = instrucao;
      atualizarFolha();
    });
    formulario.addEventListener('submit', event => {
      event.preventDefault();
      if (vista.ocupada || camadasPendentes()) {
        status.textContent = 'Aguarde as camadas da folha terminarem de carregar.';
        return;
      }
      atualizarFolha();
      const situacaoBase = estadoBase();
      if (situacaoBase !== 'pronta') {
        status.textContent = situacaoBase === 'erro' ? 'O mapa-base não carregou. Selecione outra base para imprimir.'
          : 'Aguarde o mapa-base terminar de carregar e tente novamente.';
        return;
      }
      const situacaoCalor = acesso.calor.estado();
      if (situacaoCalor !== 'pronta') {
        status.textContent = situacaoCalor === 'erro' ? 'A densidade não foi desenhada. Tente trocar a fonte do mapa de calor.'
          : 'Aguarde o mapa de calor terminar de carregar e tente novamente.';
        return;
      }
      window.print();
    });
    function camadasPendentes() {
      return vista.pendentes || [...acesso.filtrosPorCamada.values()].some(filtro => filtro.pendente?.());
    }
    new ResizeObserver(ajustarPrevia).observe(rolagem);
    new MutationObserver(() => { if (dialogo.open) atualizarFolha(); }).observe(legendaOriginal, {childList: true});
    map.on('dragend zoomend', () => { if (dialogo.open) atualizarFolha(); });
  }

  window.GeoVSATTImpressao = {create};
})();
