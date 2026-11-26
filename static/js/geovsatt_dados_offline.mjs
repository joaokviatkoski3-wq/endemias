const normalizar = valor => String(valor ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '')
  .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const numero = valor => String(valor ?? '').trim().replace(/^0+(?=\d)/, '').toLowerCase();
const nomeDaFeicao = (props, rotulo) => props[rotulo] ?? props.nome ?? props.NOME ?? props.Name ?? props.rotulo;
const projetoNaCopia = (projeto, pacote) => {
  const dados = projeto.configuracao;
  const camadas = dados.camadas.filter(codigo => Object.hasOwn(pacote.dados, codigo));
  const baseIndisponivel = dados.base !== 'none' && !pacote.ortofotos?.some(item => item.base === dados.base);
  return {...projeto, camadas_indisponiveis: projeto.camadas_indisponiveis + dados.camadas.length - camadas.length,
    base_indisponivel: projeto.base_indisponivel || Boolean(baseIndisponivel),
    configuracao: {...dados, base: baseIndisponivel ? 'none' : dados.base, camadas,
      filtros: Object.fromEntries(Object.entries(dados.filtros || {}).filter(([id]) => camadas.includes(id)))}};
};

function buscar(pacote, entrada) {
  const termo = normalizar(entrada.q);
  if (termo.length < 2 || (entrada.sugestao && termo.length < 3)) return [];
  const limite = entrada.sugestao ? 7 : 30;
  const tokens = termo.split(' ');
  const ignoraTipo = new Set(['r', 'av', 'rod', 'trav', 'n', 'numero']);
  const blocoExplicito = termo.match(/^(?:quarteirao|q) ([\da-z ]+)$/);
  const enderecos = new Map();
  for (const [chave, bloco] of Object.entries(blocoExplicito ? {} : pacote.rg || {})) {
    const local = normalizar(bloco.localidade.nome);
    for (const item of bloco.registros) {
      const via = normalizar(item.logradouro);
      if (!via || item.tipo === 'REF') continue;
      const n = numero(item.numero);
      const palavrasDaVia = via.split(' ');
      const numericos = tokens.filter(token => /^\d+[a-z]?$/.test(token) && !palavrasDaVia.includes(token));
      const total = via + ' ' + local;
      const combina = tokens.every(token => ignoraTipo.has(token) || numericos.includes(token) || total.includes(token))
        && numericos.every(token => n && (entrada.sugestao ? n.startsWith(numero(token)) : n === numero(token)));
      if (!combina) continue;
      const porNumero = numericos.length > 0;
      const id = chave + '|' + via + '|' + (porNumero ? n : '');
      if (enderecos.has(id)) {
        if (porNumero) enderecos.get(id).imoveis.push(item.id_imovel);
        continue;
      }
      enderecos.set(id, {tipo: 'endereco', titulo: porNumero ? item.logradouro + ', ' + item.numero : item.logradouro,
        logradouro: item.logradouro, subtitulo: bloco.localidade.nome + ' · Q. ' + bloco.quarteirao + ' · RG offline',
        id_localidade: Number(chave.split(':')[0]), quarteirao: bloco.quarteirao, chave,
        imoveis: porNumero ? [item.id_imovel] : []});
      if (enderecos.size >= limite) return [...enderecos.values()];
    }
  }
  if (enderecos.size) return [...enderecos.values()].sort((a, b) => a.titulo.localeCompare(b.titulo, 'pt-BR'));

  const resultados = [];
  const blocos = new Set();
  for (const camada of pacote.camadas) {
    for (const feature of pacote.dados[camada.id].features) {
      const props = feature.properties || {};
      const nome = nomeDaFeicao(props, camada.estilo?.rotulo);
      if (camada.id === 'quarteiroes') {
        const {chave, id_quart, Localidade: id, Localidade_nome: local} = props;
        const confere = blocoExplicito ? numero(blocoExplicito[1]) === numero(id_quart)
          : normalizar([local, id_quart].join(' ')).includes(termo);
        if (!confere || (chave && blocos.has(chave))) continue;
        if (chave) blocos.add(chave);
        resultados.push({tipo: chave && Object.hasOwn(pacote.rg || {}, chave) ? 'quarteirao' : 'feicao',
          titulo: 'Quarteirão ' + id_quart, subtitulo: local,
          id_localidade: id, quarteirao: id_quart, chave, camada: camada.id, feature});
      } else if (!blocoExplicito && nome && normalizar(nome).includes(termo)) {
        resultados.push({tipo: camada.id === 'localidades' ? 'localidade' : 'feicao', titulo: nome, subtitulo: camada.nome,
          id_localidade: props.id_localidade, camada: camada.id, feature});
      }
      if (resultados.length >= limite) return resultados;
    }
  }
  return resultados;
}

function areaAssinada(anel) {
  const [x0, y0] = anel[0];
  return anel.reduce((total, [x, y], i) => {
    const [u, v] = anel[(i + 1) % anel.length];
    return total + (x - x0) * (v - y0) - (u - x0) * (y - y0);
  }, 0) / 2;
}

const areaAnel = anel => Math.abs(areaAssinada(anel));
const area = multi => multi.reduce((total, poligono) => total + poligono.reduce((soma, anel, i) =>
  soma + (i ? -1 : 1) * areaAnel(anel), 0), 0);
const caixa = multi => {
  const limites = [Infinity, Infinity, -Infinity, -Infinity];
  for (const poligono of multi) for (const anel of poligono) for (const [x, y] of anel) {
    limites[0] = Math.min(limites[0], x);
    limites[1] = Math.min(limites[1], y);
    limites[2] = Math.max(limites[2], x);
    limites[3] = Math.max(limites[3], y);
  }
  return limites;
};

function cruza(a, b, c, d) {
  const orientacao = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  const entre = (p, q, r) => [0, 1].every(i => Math.min(p[i], q[i]) <= r[i] && r[i] <= Math.max(p[i], q[i]));
  const ac = orientacao(a, b, c), ad = orientacao(a, b, d), ca = orientacao(c, d, a), cb = orientacao(c, d, b);
  return (ac * ad < 0 && ca * cb < 0) || (!ac && entre(a, b, c)) || (!ad && entre(a, b, d))
    || (!ca && entre(c, d, a)) || (!cb && entre(c, d, b));
}

export function estimar(pacote, pontos, incluir, operacoes) {
  if (!pacote.populacao || !Array.isArray(pontos) || pontos.length < 3 || pontos.length > 120
      || pontos.some(p => !Array.isArray(p) || p.length !== 2 || !p.every(Number.isFinite)
        || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90)) throw Error('Desenhe uma área válida com 3 a 120 vértices.');
  const repetidos = new Set(pontos.map(p => p.join(','))).size !== pontos.length;
  for (let i = 0; i < pontos.length; i++) for (let j = i + 2; j < pontos.length; j++) {
    if (i === 0 && j === pontos.length - 1) continue;
    if (cruza(pontos[i], pontos[i + 1], pontos[j], pontos[(j + 1) % pontos.length])) {
      throw Error('Desenhe uma área sem cruzamentos.');
    }
  }
  if (repetidos || !areaAnel(pontos)) throw Error('Desenhe uma área com vértices distintos.');
  const anel = [...pontos, pontos[0]];
  const limite = caixa([[anel]]);
  const blocos = new Map();
  const dados = pacote.dados.quarteiroes;
  for (const [i, feature] of dados.features.entries()) {
    const props = feature.properties || {};
    const geo = feature.geometry;
    if (!geo || !['Polygon', 'MultiPolygon'].includes(geo.type)) continue;
    const chave = props.chave || i;
    const coords = geo.type === 'Polygon' ? [geo.coordinates] : geo.coordinates;
    if (!blocos.has(chave)) blocos.set(chave, {formas: [], props});
    blocos.get(chave).formas.push(coords);
  }
  let com = 0, sem = 0, parciais = 0, residencias = 0;
  for (const {formas, props} of blocos.values()) {
    if (formas.every(forma => {
      const b = caixa(forma);
      return b[0] > limite[2] || b[2] < limite[0] || b[1] > limite[3] || b[3] < limite[1];
    })) continue;
    const forma = operacoes.union(...formas);
    const ocupada = area(operacoes.intersection(forma, [anel]));
    if (ocupada <= 0) continue;
    if (!props.imoveis) {
      sem += 1;
      continue;
    }
    const proporcao = Math.min(1, ocupada / area(forma));
    com += 1;
    parciais += Number(proporcao < .999999);
    residencias += proporcao * (Number(incluir ? props.residencias_reais : props.residencias_sem_condominio) || 0);
  }
  const {media, fonte} = pacote.populacao;
  const pessoas = residencias * media;
  const arredondado = pessoas % 1 === .5 && Math.floor(pessoas) % 2 === 0 ? Math.floor(pessoas) : Math.round(pessoas);
  return {
    populacao_estimada: com ? arredondado : null, residencias_equivalentes: com ? Number(residencias.toFixed(2)) : null,
    quarteiroes_com_cadastro: com, quarteiroes_sem_cadastro: sem, quarteiroes_parciais: parciais,
    media_pessoas_por_residencia: media, fonte_populacao: fonte, origem_malha: dados.metadata.origem,
  };
}

export function criarApiLocal(pacote, projetos, gravar, operacoes) {
  let alterados = projetos;
  const combinados = () => new Map([...pacote.composicoes || [], ...alterados].map(item => [item.id_composicao, item]));
  return async (caminho, opcoes = {}) => {
    const url = new URL(caminho, 'https://geovsatt.invalid');
    const rota = url.pathname.split('/').slice(3);
    const carga = opcoes.body ? JSON.parse(opcoes.body) : {};
    const [recurso, id, extra] = rota.map(decodeURIComponent);
    switch (recurso) {
      case 'camadas':
        if (Object.hasOwn(pacote.dados, id)) return pacote.dados[id];
        throw Error('Esta camada não está nesta cópia.');
      case 'busca':
        return {resultados: buscar(pacote, carga)};
      case 'quarteiroes':
        if (Object.hasOwn(pacote.rg || {}, id + ':' + extra)) return pacote.rg[id + ':' + extra];
        throw Error('A ficha de endereço deste quarteirão não está na cópia.');
      case 'populacao':
        return estimar(pacote, carga.pontos, carga.incluir_condominios, operacoes);
      case 'composicoes': {
        const projetosAtuais = combinados();
        const anterior = projetosAtuais.get(Number(id));
        if (opcoes.method === 'POST' || opcoes.method === 'PUT') {
          if (id && (!anterior || anterior.atualizada_em !== carga.atualizada_em)) {
            throw Error('Abra a composição novamente antes de salvar.');
          }
          const locais = Array.from(projetosAtuais.keys()).filter(chave => chave < 0);
          const proximo = id ? Number(id) : Math.min(0, ...locais) - 1;
          delete carga.atualizada_em;
          const item = {id_composicao: proximo, atualizada_em: new Date().toISOString(),
            camadas_indisponiveis: 0, base_indisponivel: false, configuracao: carga};
          const novos = [...alterados.filter(atual => atual.id_composicao !== proximo), item];
          await gravar(novos);
          alterados = novos;
          return {id_composicao: proximo, titulo: carga.titulo, atualizada_em: item.atualizada_em};
        }
        if (id) {
          if (!anterior) throw Error('A composição não está nesta cópia.');
          return projetoNaCopia(anterior, pacote);
        }
        return [...projetosAtuais.values()].sort((a, b) => b.atualizada_em.localeCompare(a.atualizada_em))
          .map(item => ({...item, titulo: item.configuracao.titulo}));
      }
      default:
        throw Error('Esta consulta precisa de conexão.');
    }
  };
}

function wkt(geo) {
  if (!geo) return '';
  const tupla = p => p.join(' ');
  const grupo = (p, serializar) => '(' + p.map(serializar).join(', ') + ')';
  const linha = p => grupo(p, tupla);
  const area = p => grupo(p, linha);
  const tipos = {Point: p => '(' + tupla(p) + ')', MultiPoint: linha, LineString: linha,
    MultiLineString: area, Polygon: area, MultiPolygon: p => grupo(p, area)};
  return Object.hasOwn(tipos, geo.type) ? geo.type.toUpperCase() + ' ' + tipos[geo.type](geo.coordinates) : '';
}

const valor = item => item == null ? '' : typeof item === 'object' ? JSON.stringify(item) : String(item);
const csv = item => {
  let texto = valor(item);
  if (typeof item !== 'number' && (/^[\t\r\n]/.test(texto) || /^\s*[=+@-]/.test(texto))) texto = "'" + texto;
  return '"' + texto.replaceAll('"', '""') + '"';
};
const xml = item => valor(item).replace(/[^\u0009\u000a\u000d\u0020-\uD7FF\uE000-\uFFFD\u{10000}-\u{10FFFF}]/gu, '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const kmlCoord = pontos => '<coordinates>' + pontos.map(p => p.join(',')).join(' ') + '</coordinates>';

function kmlGeo(geo) {
  if (!geo) return '';
  const {type, coordinates} = geo;
  if (type.startsWith('Multi')) return '<MultiGeometry>' + coordinates.map(p =>
    kmlGeo({type: type.slice(5), coordinates: p})).join('') + '</MultiGeometry>';
  if (type === 'Point') return '<Point>' + kmlCoord([coordinates]) + '</Point>';
  if (type === 'LineString') return '<LineString>' + kmlCoord(coordinates) + '</LineString>';
  if (type === 'Polygon') {
    return '<Polygon>' + coordinates.map((anel, i) => {
      const tipo = i ? 'innerBoundaryIs' : 'outerBoundaryIs';
      const orientado = (areaAssinada(anel) > 0) === (i === 0) ? anel : [...anel].reverse();
      return '<' + tipo + '><LinearRing>' + kmlCoord(orientado) + '</LinearRing></' + tipo + '>';
    }).join('') + '</Polygon>';
  }
  return '';
}

export function exportar(camada, dados, formato) {
  if (formato === 'geojson') return new Blob([JSON.stringify(dados)], {type: 'application/geo+json'});
  if (formato === 'csv') {
    const campos = [...new Set(dados.features.flatMap(f => Object.keys(f.properties || {})))].sort();
    let geometria = 'geometria_wkt_epsg4326';
    while (campos.includes(geometria)) geometria += '_';
    const linhas = [campos.concat(geometria).map(csv).join(';')];
    for (const f of dados.features) linhas.push([...campos.map(campo => f.properties?.[campo]), wkt(f.geometry)].map(csv).join(';'));
    return new Blob(['\uFEFF', linhas.join('\r\n')], {type: 'text/csv;charset=utf-8'});
  }
  const itens = dados.features.map((f, i) => {
    const props = f.properties || {};
    const titulo = nomeDaFeicao(props, camada.estilo?.rotulo) ?? 'Feição ' + (i + 1);
    const atributos = Object.entries(props).filter(([, v]) => v != null)
      .map(([k, v]) => '<Data name="' + xml(k) + '"><value>' + xml(v) + '</value></Data>').join('');
    return '<Placemark><name>' + xml(titulo) + '</name><ExtendedData>' + atributos + '</ExtendedData>'
      + kmlGeo(f.geometry) + '</Placemark>';
  });
  return new Blob(['<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>',
    xml(camada.nome), '</name>', ...itens, '</Document></kml>'], {type: 'application/vnd.google-earth.kml+xml'});
}
