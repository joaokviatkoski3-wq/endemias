(() => {
  'use strict';
  const form = document.getElementById('gc-config');
  if (!form) return;
  const estilos = window.GeoVSATTEstilos;
  const campo = nome => form.elements.namedItem(nome);
  const modo = campo('modo_cor');
  const atributo = campo('atributo_cor');
  const regras = campo('regras_cor');
  const categorias = document.getElementById('gc-categorias');
  const categoria = document.getElementById('gc-valor-cor');
  const editorCor = document.querySelector('.gc-color-editor');
  const paleta = document.getElementById('gc-paleta');
  const coresDefinidas = document.getElementById('gc-cores-definidas');
  const painelFiltros = document.getElementById('gc-filtros-cor');
  const listaFiltros = document.getElementById('gc-filtros-cor-lista');
  const adicionarFiltro = document.getElementById('gc-adicionar-filtro-cor');
  const modeloFiltro = document.getElementById('gc-filtro-cor-modelo');
  const maxFiltros = 40;
  let ordemLista = 0;
  const faixas = document.getElementById('gc-faixas');
  const lista = document.getElementById('gc-faixas-lista');
  const estado = document.getElementById('gc-faixas-estado');
  const adicionar = document.getElementById('gc-adicionar-faixa');
  const amostra = document.getElementById('gc-amostra-valor');
  const simbolo = document.getElementById('gc-amostra-simbolo');
  const legenda = document.getElementById('gc-previa-legenda');
  const modelo = document.getElementById('gc-faixa-modelo');
  const maxFaixas = Number(lista.dataset.max || 12);
  const atributos = new Map();
  let primeira;
  let padrao = estilos.padraoDaCamada(form.dataset.camada);

  const hex = valor => /^#[0-9a-f]{6}$/i.test(valor) ? valor : '';
  const cores = () => Object.fromEntries(regras.value.split('\n').map(linha => {
    const i = linha.lastIndexOf('=');
    return i < 1 ? [] : [linha.slice(0, i).trim(), hex(linha.slice(i + 1).trim())];
  }).filter(([nome, cor]) => nome && cor));

  function lerFaixas() {
    const itens = [];
    for (const linha of lista.children) {
      const valor = chave => linha.querySelector(`[name="faixa_${chave}"]`).value.trim();
      const rawDe = valor('de');
      const rawAte = valor('ate');
      const de = estilos.numero(rawDe);
      const ate = estilos.numero(rawAte);
      if ((rawDe && de === null) || (rawAte && ate === null) || (de === null && ate === null)
          || (de !== null && ate !== null && de >= ate)) return null;
      itens.push({de, ate, cor: valor('cor'), legenda: valor('legenda')});
    }
    itens.sort((a, b) => (a.de ?? -Infinity) - (b.de ?? -Infinity));
    return itens.length && itens.every((item, i) => !i || (itens[i - 1].ate ?? Infinity) <= (item.de ?? -Infinity))
      ? itens : null;
  }

  function lerFiltros() {
    return [...listaFiltros.children].map(linha => {
      const valor = nome => linha.querySelector(`[name="filtro_cor_${nome}"]`).value.trim();
      return {campo: valor('campo'), operador: valor('operador'), valor: valor('valor'), cor: valor('cor')};
    }).filter(regra => regra.campo && regra.valor);
  }

  function lerConfig() {
    const config = Object.fromEntries(new FormData(form));
    for (const nome of ['largura', 'opacidade', 'opacidade_preenchimento', 'raio', 'rotulo_tamanho', 'rotulo_halo']) {
      const entrada = campo(nome);
      config[nome] = entrada.value && entrada.validity.valid ? entrada.valueAsNumber : null;
    }
    for (const nome of ['cor', 'cor_preenchimento', 'rotulo_cor', 'rotulo_halo_cor']) config[nome] = hex(config[nome]);
    config.cores = cores();
    config.filtros_cor = modo.value === 'filtros' ? lerFiltros() : [];
    config.faixas_cor = modo.value === 'faixas' ? lerFaixas() : [];
    estado.textContent = config.faixas_cor === null ? 'Preencha os limites das faixas e evite sobreposições.' : '';
    if (config.faixas_cor === null) {
      config.modo_cor = 'unico';
      config.faixas_cor = [];
    }
    return config;
  }

  function atualizarValores() {
    atributo.required = modo.value === 'faixas' || modo.value === 'categorias';
    categorias.hidden = ['faixas', 'unico', 'filtros'].includes(modo.value);
    faixas.hidden = modo.value !== 'faixas';
    painelFiltros.hidden = modo.value !== 'filtros';
    document.getElementById('gc-campo-cores').hidden = ['unico', 'filtros'].includes(modo.value);
    for (const entrada of listaFiltros.querySelectorAll('input, select')) {
      entrada.disabled = painelFiltros.hidden;
      entrada.required = !painelFiltros.hidden;
    }
    adicionar.disabled = lista.childElementCount >= maxFaixas;
    const campoAmostra = modo.value === 'filtros' ? lerFiltros()[0]?.campo : atributo.value || padrao.categories;
    const valores = [...(atributos.get(campoAmostra)?.keys() ?? [])]
      .sort((a, b) => a.localeCompare(b, 'pt-BR', {numeric: true}));
    for (const select of [categoria, amostra]) {
      const anterior = select.value;
      select.replaceChildren(...valores.map(valor => new Option(valor, valor)));
      if (valores.includes(anterior)) select.value = anterior;
    }
    editorCor.hidden = !valores.length || !atributo.value || categorias.hidden;
    document.getElementById('gc-amostra-campo').hidden = !valores.length || modo.value === 'unico';
    paleta.value = cores()[categoria.value] || '#008c30';
  }

  function svg(nome, atributos = {}) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', nome);
    for (const [chave, valor] of Object.entries(atributos)) node.setAttribute(chave, String(valor));
    return node;
  }

  function desenhar(config, estilo, tipo, texto, props) {
    const quadro = svg('svg', {viewBox: '0 0 360 112', 'aria-hidden': 'true'});
    const traçado = {fill: 'none', stroke: estilo.color, 'stroke-width': estilo.weight, 'stroke-opacity': estilo.opacity};
    const preenchimento = {fill: estilo.fillColor, 'fill-opacity': estilo.fillOpacity};
    const linha = 'M20 58 C75 26 118 89 184 55 S274 30 340 51';
    const aoLongo = tipo === 'linha' && config.rotulo_modo !== 'centro';
    if (tipo === 'linha') {
      if ((config.linha || padrao.line) === 'ferrovia') {
        quadro.append(svg('path', {...traçado, d: linha, 'stroke-width': estilo.weight + 5, 'stroke-dasharray': '2 9'}));
      }
      if (estilo.dashArray) traçado['stroke-dasharray'] = estilo.dashArray;
      quadro.append(svg('path', {...traçado, d: linha, id: 'gc-amostra-eixo'}));
    } else if (tipo === 'ponto') {
      const {forma, glifo, icone, raio} = estilos.marcador(form.dataset.camada, config, props);
      const desenho = svg('g', {});
      if (icone) {
        desenho.setAttribute('opacity', config.opacidade_preenchimento ?? config.opacidade ?? 1);
        traçado['stroke-width'] = config.largura ?? 1.5;
        traçado['stroke-opacity'] = preenchimento['fill-opacity'] = 1;
      }
      if (forma === 'quadrado') {
        desenho.append(svg('rect', {...traçado, ...preenchimento, x: 180 - raio, y: 43 - raio, width: 2 * raio, height: 2 * raio, rx: 3}));
      } else if (forma === 'losango' || forma === 'triangulo') {
        const y = forma === 'losango' ? 43 : 43 + raio;
        const pontos = [`180,${43 - raio}`, `${180 + raio},${y}`,
          ...(forma === 'losango' ? [`180,${43 + raio}`] : []), `${180 - raio},${y}`];
        desenho.append(svg('polygon', {...traçado, ...preenchimento, points: pontos.join(' ')}));
      } else {
        desenho.append(svg('circle', {...traçado, ...preenchimento, cx: 180, cy: 43, r: raio}));
      }
      if (glifo) {
        const marca = svg('text', {x: 180, y: 47, 'text-anchor': 'middle', fill: 'white', 'font-size': 10, 'font-weight': 800});
        marca.textContent = glifo;
        desenho.append(marca);
      }
      quadro.append(desenho);
    } else {
      if (estilo.dashArray) traçado['stroke-dasharray'] = estilo.dashArray;
      quadro.append(svg('polygon', {...traçado, ...(estilo.fill ? preenchimento : {}), points: '29,29 245,16 318,38 298,86 140,98 41,75'}));
    }
    if (texto && config.rotulo_modo !== 'oculto') {
      const etiqueta = svg('text', {x: 180, y: tipo === 'ponto' ? 83 : 61, 'text-anchor': 'middle',
        fill: config.rotulo_cor || padrao.labelColor || '#24362b', stroke: config.rotulo_halo_cor || '#fff',
        'stroke-width': config.rotulo_halo ?? 3, 'paint-order': 'stroke fill',
        'stroke-linejoin': 'round', 'font-size': config.rotulo_tamanho ?? (aoLongo ? 11 : 12), 'font-weight': 700});
      if (aoLongo) {
        etiqueta.removeAttribute('x');
        etiqueta.removeAttribute('y');
        etiqueta.setAttribute('dy', '-4');
        const caminho = svg('textPath', {href: '#gc-amostra-eixo', startOffset: '50%'});
        caminho.textContent = texto.slice(0, 90);
        etiqueta.append(caminho);
      } else {
        etiqueta.textContent = texto.slice(0, 90);
      }
      quadro.append(etiqueta);
    }
    simbolo.replaceChildren(quadro);
  }

  function atualizarPrevia() {
    const config = lerConfig();
    const campoAmostra = config.modo_cor === 'filtros' ? config.filtros_cor[0]?.campo : config.atributo_cor || padrao.categories;
    const opcoes = atributos.get(campoAmostra);
    const feicao = opcoes?.get(amostra.value) || primeira;
    const props = feicao?.properties || {};
    const tipo = feicao?.geometry?.type ? estilos.tipoDaGeometria(feicao.geometry.type) : form.dataset.tipo;
    const classificar = estilos.classificador(config, padrao, [...(opcoes?.values() || [])]);
    const principal = props[config.rotulo || padrao.label] ?? (form.dataset.camada === 'quarteiroes' && props.id_quart ? `Q. ${props.id_quart}` : '');
    desenhar(config, estilos.simbolo(config, padrao, classificar(props), tipo), tipo, estilos.textoRotulo(config, principal, props), props);
    const classes = config.modo_cor === 'faixas'
      ? config.faixas_cor.map(faixa => ({nome: estilos.textoFaixa(faixa), cor: faixa.cor}))
      : config.modo_cor === 'filtros' ? estilos.classesDosFiltros(config)
        : [...(opcoes?.values() || [])].slice(0, 16).map(exemplo => classificar(exemplo.properties)).filter(Boolean);
    legenda.replaceChildren(...classes.map(classe => {
      const item = document.createElement('li');
      const cor = document.createElement('i');
      cor.style.backgroundColor = estilos.corDoSimbolo(estilos.simbolo(config, padrao, classe, tipo), tipo);
      item.append(cor, document.createTextNode(classe.nome));
      return item;
    }));
  }

  function atualizarCoresDefinidas() {
    coresDefinidas.replaceChildren(...Object.entries(cores()).map(([nome, cor]) => {
      const linha = document.createElement('li');
      const seletor = document.createElement('input');
      seletor.type = 'color';
      seletor.value = cor;
      seletor.setAttribute('aria-label', 'Cor de ' + nome);
      seletor.addEventListener('input', () => salvarCores({...cores(), [nome]: seletor.value}, false));
      const remover = document.createElement('button');
      remover.type = 'button';
      remover.textContent = 'Remover';
      remover.addEventListener('click', () => {
        const valores = cores();
        delete valores[nome];
        salvarCores(valores);
      });
      linha.append(seletor, document.createTextNode(nome), remover);
      return linha;
    }));
  }

  function salvarCores(valores, redesenhar = true) {
    const texto = Object.entries(valores).map(([nome, cor]) => `${nome} = ${cor}`).join('\n');
    if (texto.length > regras.maxLength) {
      document.getElementById('gc-categorias-estado').textContent = 'O conjunto de cores atingiu o tamanho máximo.';
      return;
    }
    document.getElementById('gc-categorias-estado').textContent = '';
    regras.value = texto;
    if (redesenhar) atualizarCoresDefinidas();
    atualizarPrevia();
  }

  for (const escolha of form.querySelectorAll('[data-escolha-cor]')) {
    const paleta = escolha.querySelector('[data-cor-visual]');
    const automatica = escolha.querySelector('[data-cor-automatica]');
    const destino = escolha.querySelector('input[type="hidden"]');
    paleta.addEventListener('input', () => {
      automatica.checked = false;
      destino.value = paleta.value;
    });
    automatica.addEventListener('input', () => {
      destino.value = automatica.checked ? '' : paleta.value;
    });
  }

  function atualizarSugestoes(linha) {
    const campoFiltro = linha.querySelector('[name="filtro_cor_campo"]');
    const valorFiltro = linha.querySelector('[name="filtro_cor_valor"]');
    let sugestoes = linha.querySelector('datalist');
    if (!sugestoes) {
      sugestoes = document.createElement('datalist');
      sugestoes.id = 'gc-opcoes-filtro-cor-' + (++ordemLista);
      valorFiltro.setAttribute('list', sugestoes.id);
      linha.append(sugestoes);
    }
    const valores = [...(atributos.get(campoFiltro.value)?.keys() ?? [])];
    sugestoes.replaceChildren(...valores.slice(0, 100).map(valor => new Option(valor, valor)));
  }

  adicionarFiltro.addEventListener('click', () => {
    if (listaFiltros.childElementCount >= maxFiltros) return;
    const novo = modeloFiltro.content.cloneNode(true);
    listaFiltros.append(novo);
    const linha = listaFiltros.lastElementChild;
    atualizarSugestoes(linha);
    adicionarFiltro.disabled = listaFiltros.childElementCount >= maxFiltros;
    linha.querySelector('input').focus();
  });

  listaFiltros.addEventListener('click', event => {
    if (!event.target.matches('[data-remover-filtro-cor]')) return;
    event.target.closest('.gc-filtro-cor').remove();
    adicionarFiltro.disabled = false;
    adicionarFiltro.focus();
    atualizarValores();
    atualizarPrevia();
  });

  categoria.addEventListener('change', () => {
    paleta.value = cores()[categoria.value] || '#008c30';
    amostra.value = categoria.value;
    atualizarPrevia();
  });
  document.getElementById('gc-aplicar-cor').addEventListener('click', () => {
    if (!categoria.value) return;
    salvarCores({...cores(), [categoria.value]: paleta.value});
  });
  adicionar.addEventListener('click', () => {
    if (lista.childElementCount >= maxFaixas) return;
    const faixa = modelo.content.cloneNode(true);
    faixa.querySelector('[type="color"]').value = estilos.paleta[lista.childElementCount];
    lista.append(faixa);
    adicionar.disabled = lista.childElementCount >= maxFaixas;
    lista.lastElementChild.querySelector('input').focus();
    atualizarPrevia();
  });
  lista.addEventListener('click', event => {
    if (!event.target.matches('[data-remover-faixa]')) return;
    event.target.closest('.gc-faixa-cor').remove();
    adicionar.disabled = false;
    adicionar.focus();
    atualizarPrevia();
  });
  form.addEventListener('input', event => {
    if (event.target.name === 'filtro_cor_campo') atualizarSugestoes(event.target.closest('.gc-filtro-cor'));
    if (event.target === modo || event.target === atributo || event.target.name === 'filtro_cor_campo') atualizarValores();
    if (event.target.closest('fieldset')?.contains(simbolo)) atualizarPrevia();
  });
  form.addEventListener('submit', event => {
    if (modo.value === 'filtros' && listaFiltros.childElementCount === 0) {
      event.preventDefault();
      adicionarFiltro.click();
      return;
    }
    if (modo.value !== 'faixas' || lerFaixas()) return;
    event.preventDefault();
    atualizarPrevia();
    (lista.querySelector('input') || adicionar).focus();
  });

  async function carregarAmostras() {
    const response = await fetch(form.dataset.feicoes, {cache: 'no-store'});
    if (!response.ok) return;
    const data = await response.json();
    padrao = estilos.padraoDaCamada(form.dataset.camada, data.metadata);
    primeira = data.features?.[0];
    for (const feature of data.features || []) {
      for (const [nome, valor] of Object.entries(feature.properties || {})) {
        if (valor == null || typeof valor === 'object' || nome.length > 120) continue;
        if (!atributos.has(nome)) atributos.set(nome, new Map());
        const exemplos = atributos.get(nome);
        const texto = String(valor).trim();
        if (exemplos.size < 600 && texto && !texto.includes('\n') && !exemplos.has(texto)) exemplos.set(texto, feature);
      }
    }
    document.getElementById('gc-atributos').replaceChildren(...[...atributos.keys()].sort().map(nome => new Option(nome, nome)));
    for (const linha of listaFiltros.children) atualizarSugestoes(linha);
    atualizarValores();
    atualizarPrevia();
  }

  atualizarCoresDefinidas();
  atualizarValores();
  atualizarPrevia();
  carregarAmostras().catch(() => {});
})();
