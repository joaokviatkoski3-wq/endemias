(() => {
  'use strict';

  const paleta = ['#157157', '#365eb3', '#965331', '#713996', '#9a5821', '#237383', '#a33558', '#626d1e', '#345687',
    '#ba492f', '#0e667e', '#8f3c88', '#455d26', '#526ba0', '#a64751', '#217566', '#856515', '#56496d', '#99653a'];
  const tracejado = {tracejada: '7 5', pontilhada: '1 5'};
  const formatador = new Intl.NumberFormat('pt-BR', {maximumSignificantDigits: 16});

  const execucao = {pane: 'block-coverage', color: '#19684b', fillOpacity: .42, categories: 'situacao_execucao',
    colors: {Trabalhado: '#008255', 'Sem visita registrada': '#a75322', 'Sem dados para cruzar': '#686474', 'Fora do raio operacional': '#616b70'}};
  const indicadores = {pane: 'block-work', color: '#2d565b', fillOpacity: .43, categories: 'faixa',
    colors: {'0': '#838b8e', '1': '#53846d', '2–3': '#bd7824', '4 ou mais': '#a53436'}};
  const padroes = {
    dengue: {pane: 'localities', color: '#b33d2d', label: 'rotulo', categories: 'situacao'},
    dengue_bloqueios: {pane: 'block-radii', color: '#ab3924', weight: 2.5, noFill: true, line: 'tracejada'},
    ovitrampas_bloqueios: {pane: 'block-radii', color: '#754c98', weight: 2.5, noFill: true, line: 'tracejada'},
    esporotricose_trabalhados: execucao,
    dengue_quarteiroes: execucao,
    ovitrampas_quarteiroes: execucao,
    indicadores_endemias: indicadores,
    visitas_ambientais: indicadores,
    coletas_tubos: {pane: 'localities', color: '#527f85', label: 'rotulo', categories: 'situacao',
      colors: {Positiva: '#b32e3b', Negativa: '#25866c', 'Aguardando resultado': '#656e73'}},
    logradouros: {pane: 'streets', color: '#78857d', weight: 1.4, opacity: .78, label: 'nome'},
    quarteiroes: {pane: 'blocks', color: '#00752b', fillColor: '#e8f5eb', weight: 1, fillOpacity: .28},
    localidades: {pane: 'territory', color: '#238070', weight: 1.4, fillOpacity: .12, label: 'nome', labelZoom: 13, categories: 'nome'},
    'limite-municipal': {pane: 'territory', color: '#364850', weight: 2.5, noFill: true},
    hidrografia: {pane: 'streets', color: '#1672aa', weight: 2, label: 'NOME', labelColor: '#125783', labelZoom: 15},
    ferrovia: {pane: 'streets', color: '#54463d', weight: 2, line: 'ferrovia'},
    'suscetibilidade-inundacao': {color: '#355eb0', categories: 'Classe', colors: {Alta: '#1e4398', Media: '#3f82c9', Baixa: '#9ecbed'}},
    'suscetibilidade-movimento-massa': {color: '#af5521', categories: 'Classe', colors: {Alta: '#a93a22', Media: '#d07c21', Baixa: '#e9b652'}},
    predios_publicos: {pane: 'localities', color: '#a03d74', categories: 'tipo', label: 'nome'},
    ovitrampas: {pane: 'localities', color: '#6b5294', label: 'ovitrampa_id', categories: 'resultado',
      colors: {Positiva: '#b32e3b', Negativa: '#25866c', 'Sem contagem': '#656e73'}},
    pontos_estrategicos: {pane: 'localities', color: '#975521', label: 'nome', categories: 'tipo'},
    acoes_atendimentos: {pane: 'localities', color: '#235786', label: 'rotulo', categories: 'tipo'},
    esporotricose: {pane: 'imported', color: '#ae412e', label: 'rotulo', categories: 'posicao_cadastrada',
      colors: {'Dentro do limite municipal': '#ae412e', 'Fora do limite municipal': '#644191', 'Limite municipal indisponível': '#ae412e'}},
    esporotricose_bloqueios: {pane: 'block-radii', color: '#a74025', weight: 2.5, noFill: true, line: 'tracejada',
      label: 'rotulo', labelZoom: 18, categories: 'situacao_bloqueio',
      colors: {Realizado: '#166c62', 'Não realizado': '#ae412e', 'Não necessário': '#52698c', 'Sem informação': '#686474'}},
    esporotricose_quarteiroes: {pane: 'block-coverage', color: '#834999', fillOpacity: .22, categories: 'cobertura',
      colors: {Integral: '#834999', Parcial: '#b05e25'}},
    quarteiroes_trabalhados: {pane: 'block-work', color: '#225483', fillOpacity: .30, categories: 'atividade',
      colors: {'Mais de um tipo': '#225483'}},
  };

  function numero(valor) {
    if (typeof valor === 'number') return Number.isFinite(valor) ? valor : null;
    if (typeof valor !== 'string') return null;
    const texto = valor.trim();
    if (!/^[+-]?(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(texto)) return null;
    const n = Number(texto.replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  }

  function textoFaixa({de, ate, legenda}) {
    if (legenda) return legenda;
    if (de === null) return `Abaixo de ${formatador.format(ate)}`;
    if (ate === null) return `${formatador.format(de)} ou mais`;
    return `${formatador.format(de)} a < ${formatador.format(ate)}`;
  }

  const comparacoesCor = {igual: '=', contem: 'contém', minimo: '≥', maximo: '≤'};

  function classesDosFiltros(config) {
    return (config.filtros_cor || []).map((filtro, ordem) => ({
      ...filtro, ordem, nome: `${filtro.campo} ${comparacoesCor[filtro.operador]} ${filtro.valor}`,
      texto: String(filtro.valor).trim().toLocaleLowerCase('pt-BR'), numero: numero(filtro.valor),
    }));
  }

  function classificador(config, padrao, feicoes) {
    if (config.modo_cor === 'filtros') {
      const regras = classesDosFiltros(config);
      return props => regras.find(regra => {
        if (!Object.hasOwn(props ?? {}, regra.campo) || props[regra.campo] == null) return false;
        const valor = props[regra.campo];
        if (regra.operador === 'minimo' || regra.operador === 'maximo') {
          const n = numero(valor);
          if (n === null || regra.numero === null) return false;
          return regra.operador === 'minimo' ? n >= regra.numero : n <= regra.numero;
        }
        const texto = String(valor).trim().toLocaleLowerCase('pt-BR');
        return regra.operador === 'contem' ? texto.includes(regra.texto) : texto === regra.texto;
      }) || null;
    }
    const atributo = config.atributo_cor || padrao.categories;
    if (!atributo || config.modo_cor === 'unico') return () => null;
    const atributoEm = props => Object.hasOwn(props ?? {}, atributo) ? props[atributo] : undefined;
    if (config.modo_cor === 'faixas') {
      const faixas = config.faixas_cor.map((faixa, ordem) => ({
        ...faixa, nome: textoFaixa(faixa), ordem,
      }));
      return props => {
        const n = numero(atributoEm(props));
        return (n === null ? null : faixas.find(faixa => (faixa.de === null || faixa.de <= n)
          && (faixa.ate === null || n < faixa.ate))) || {
          nome: n === null ? 'Sem valor numérico' : 'Fora das faixas', cor: '',
          ordem: faixas.length + Number(n === null),
        };
      };
    }
    const valorDaCategoria = props => String(atributoEm(props) ?? '').trim();
    const cores = config.cores || {};
    const categorias = [...new Set(feicoes.map(feicao => valorDaCategoria(feicao.properties)).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, 'pt-BR', {numeric: true}));
    const classes = new Map(categorias.map((nome, ordem) => [
      nome, {nome, ordem, cor: Object.hasOwn(cores, nome) ? cores[nome] :
        (!config.atributo_cor || config.modo_cor === 'categorias'
          ? (Object.hasOwn(padrao.colors || {}, nome) ? padrao.colors[nome] : paleta[ordem % paleta.length])
          : '')},
    ]));
    return props => classes.get(valorDaCategoria(props)) || null;
  }

  function simbolo(config, padrao, classe, tipo) {
    const corClasse = classe?.cor || '';
    const cor = corClasse || config.cor || padrao.color;
    if (tipo === 'ponto') {
      const preenchimento = ['faixas', 'categorias', 'filtros'].includes(config.modo_cor)
        ? (corClasse || config.cor_preenchimento) : (config.cor_preenchimento || corClasse);
      return {color: config.cor || '#fff', weight: config.largura ?? 2, opacity: config.opacidade ?? 1,
        fillColor: preenchimento || cor, fillOpacity: config.opacidade_preenchimento ?? 1};
    }
    const linha = config.linha || padrao.line;
    return {color: cor, weight: config.largura ?? padrao.weight ?? 2, opacity: config.opacidade ?? padrao.opacity ?? 1,
      fill: tipo === 'poligono' && (!padrao.noFill || (config.opacidade_preenchimento ?? 0) > 0),
      fillColor: corClasse || config.cor_preenchimento || padrao.fillColor || cor,
      fillOpacity: config.opacidade_preenchimento ?? padrao.fillOpacity ?? .24,
      dashArray: Object.hasOwn(tracejado, linha) ? tracejado[linha] : null};
  }

  function textoRotulo(config, principal, props) {
    const extra = Object.hasOwn(props, config.rotulo_complemento) ? props[config.rotulo_complemento] : undefined;
    const valores = [principal, extra].map(valor => String(valor ?? '').trim()).filter(Boolean);
    if (!valores.length) return '';
    return [config.rotulo_prefixo, [...new Set(valores)].join(' · '), config.rotulo_sufixo].filter(Boolean).join(' ');
  }

  function tipoDaGeometria(tipo) {
    return /Point$/.test(tipo) ? 'ponto' : /LineString$/.test(tipo) ? 'linha' : 'poligono';
  }

  function equipamento(tipo) {
    const nome = String(tipo ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('pt-BR').trim();
    if (nome.includes('saude')) return ['quadrado', '+'];
    if (nome.includes('escola') || ['em', 'erm', 'cmei', 'conveniada'].includes(nome)) return ['quadrado', 'E'];
    if (nome === 'ponto de interesse' || nome.includes('social')) return ['losango', ''];
    if (nome.includes('administracao')) return ['quadrado', 'A'];
    if (nome.includes('cultura')) return ['triangulo', ''];
    if (nome.includes('seguranca')) return ['quadrado', 'S'];
    return ['circulo', ''];
  }

  function marcador(id, config, props) {
    const [formaPadrao, glifo] = id === 'predios_publicos' ? equipamento(props.tipo) : ['circulo', ''];
    const forma = config.ponto || formaPadrao;
    const icone = forma !== 'circulo' || Boolean(glifo);
    const animais = Math.max(0, Number(props.animais) || 0);
    const raioPadrao = id === 'esporotricose' ? 5 + Math.min(12, Math.sqrt(animais) * 2) : 6;
    return {forma, glifo, icone, raio: config.raio ?? (icone ? 8 : raioPadrao)};
  }

  function padraoDaCamada(id, metadados) {
    const base = Object.hasOwn(padroes, id) ? padroes[id] : {color: '#175cd3'};
    if (id !== 'quarteiroes_trabalhados' || !metadados?.tipos) return base;
    const cores = metadados.tipos.filter(tipo => tipo.cor).map(tipo => [tipo.nome, tipo.cor]);
    return {...base, colors: {...base.colors, ...Object.fromEntries(cores)}};
  }

  function corDoSimbolo(simbolo, tipo) {
    return tipo === 'ponto' || (simbolo.fill && simbolo.fillOpacity) ? simbolo.fillColor : simbolo.color;
  }

  window.GeoVSATTEstilos = {paleta, numero, textoFaixa, classificador, simbolo, textoRotulo,
    tipoDaGeometria, marcador, padraoDaCamada, corDoSimbolo, classesDosFiltros};
})();
