import assert from 'node:assert/strict';
import {existsSync, readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {test} from 'node:test';
import {runInNewContext} from 'node:vm';
import {abrirRegistro, criarRegistro, decodificarPacote, lerProjetos, protegerProjetos} from '../static/js/geovsatt_cofre.mjs';
import {criarApiLocal, estimar, exportar, lerBaseVetorial} from '../static/js/geovsatt_dados_offline.mjs';

const recortar = createRequire(import.meta.url)('../static/vendor/polygon-clipping/polygon-clipping.umd.min.js');
const retangulo = (oeste, leste, properties) => ({type: 'Feature', properties, geometry: {
  type: 'Polygon', coordinates: [[[oeste, -25.4], [leste, -25.4], [leste, -25.3], [oeste, -25.3], [oeste, -25.4]]],
}});

function pacote() {
  const dados = {
    chave: '1:1', Localidade: 1, Localidade_nome: 'Vila de ensaio', id_quart: '1',
    imoveis: 1, residencias_reais: 4, residencias_sem_condominio: 0,
  };
  return {
    formato: 1, usuario: 1, criado_em: '2026-11-26T12:00:00Z', valido_ate: '2026-12-03T12:00:00Z',
    populacao: {media: 2.93, fonte: 'IBGE'}, composicoes: [],
    rg: {'1:1': {localidade: {nome: 'Vila de ensaio'}, quarteirao: '1',
      registros: [{id_imovel: 12, logradouro: 'Rua São José', numero: '10', tipo: 'R'}]}},
    camadas: [{id: 'quarteiroes', nome: 'Quarteirões'}],
    dados: {quarteiroes: {type: 'FeatureCollection', metadata: {origem: 'QGIS de ensaio'},
      features: [retangulo(-49.4, -49.3, dados), retangulo(-49.4, -49.3, dados), retangulo(-49.3, -49.2, {})]}},
  };
}

test('a cópia possui autenticação criptográfica e mantém as composições protegidas', async () => {
  const bytes = new TextEncoder().encode(JSON.stringify(pacote()));
  const senha = 'segredo da cópia de ensaio';
  const registro = await criarRegistro(bytes, decodificarPacote(bytes), senha);
  assert.ok(!JSON.stringify(registro).includes('Rua São José'));
  await assert.rejects(abrirRegistro(registro, 'frase de senha incorreta'));
  await assert.rejects(abrirRegistro({...registro, usuario: 2}, senha));
  await assert.rejects(abrirRegistro({...registro, valido_ate: '2030-01-01T12:00:00Z'}, senha));
  const aberta = await abrirRegistro(registro, senha);
  assert.equal(aberta.dados.rg['1:1'].registros[0].numero, '10');
  const api = criarApiLocal(aberta.dados, [], async projetos => {
    registro.projetos = await protegerProjetos(registro, aberta.chave, projetos);
  }, recortar);
  const projeto = {titulo: 'Composição de ensaio', camadas: ['quarteiroes'], filtros: {}, base: 'none'};
  const novo = await api('/api/geovsatt/composicoes', {method: 'POST', body: JSON.stringify(projeto)});
  const reaberta = criarApiLocal(aberta.dados, await lerProjetos(registro, aberta.chave), () => {}, recortar);
  assert.equal((await reaberta('/api/geovsatt/composicoes/' + novo.id_composicao)).configuracao.titulo, projeto.titulo);
  assert.ok(!JSON.stringify(registro).includes(projeto.titulo));
});

test('a composição offline mantém o calor e os filtros da fonte mesmo sem desenhar os marcadores', async () => {
  const dados = pacote();
  dados.camadas.push({id: 'ovitrampas', tipo: 'ponto'});
  dados.dados.ovitrampas = {type: 'FeatureCollection', features: []};
  let projetos = [];
  const api = criarApiLocal(dados, projetos, async novos => { projetos = novos; }, recortar);
  const rota = '/api/geovsatt/composicoes';
  const calor = {camada: 'ovitrampas', raio: 48, ponderar_ovos: true};
  const composicao = {titulo: 'Densidade de ensaio', camadas: [], base: 'none', calor,
    filtros: {ovitrampas: [{field: 'ovos', match: 'gte', value: '1'}]}};
  const salvar = entrada => api(rota, {method: 'POST', body: JSON.stringify(entrada)});
  const criada = await salvar(composicao);
  assert.deepEqual((await api(rota + '/' + criada.id_composicao)).configuracao, composicao);
  await assert.rejects(salvar({...composicao, calor: {...calor, raio: 65}}), /mapa de calor inválido/);
  const pacoteRenovado = pacote();
  const novaApi = criarApiLocal(pacoteRenovado, projetos, () => {}, recortar);
  const indisponivel = await novaApi(rota + '/' + criada.id_composicao);
  assert.equal(indisponivel.calor_indisponivel, true);
  assert.equal(indisponivel.configuracao.calor, undefined);
  assert.deepEqual(indisponivel.configuracao.filtros, {});
  assert.equal(projetos[0].configuracao.calor.raio, 48);
});

test('a estimativa recorta e une quarteirões repetidos', () => {
  const selecao = [[-49.35, -25.4], [-49.2, -25.4], [-49.2, -25.3], [-49.35, -25.3]];
  const dados = estimar(pacote(), selecao, true, recortar);
  assert.equal(dados.populacao_estimada, 6);
  assert.equal(dados.residencias_equivalentes, 2);
  assert.equal(dados.quarteiroes_sem_cadastro, 1);
  assert.equal(estimar(pacote(), selecao, false, recortar).populacao_estimada, 0);
  const cruzada = [selecao[0], selecao[2], selecao[1], selecao[3]];
  assert.throws(() => estimar(pacote(), cruzada, true, recortar), /cruzamentos/);
});

test('consulta local usa apenas as feições e endereços preparados no pacote', async () => {
  const dados = pacote();
  const rg = dados.rg['1:1'];
  rg.registros.push({id_imovel: 13, logradouro: 'Rua São José', numero: '100', tipo: 'R'});
  rg.registros.push({id_imovel: 14, logradouro: 'Rua Sete de Setembro', numero: 'S/N', tipo: 'R',
    localidade: 'Bairro de ensaio'});
  dados.rg['2:9'] = {localidade: {nome: 'Vila vizinha'}, quarteirao: '9',
    registros: [{id_imovel: 15, logradouro: 'Rua São José', numero: '10', tipo: 'R'}]};
  const api = criarApiLocal(dados, [], () => {}, recortar);
  const buscar = async (q, sugestao = false) =>
    (await api('/api/geovsatt/busca', {body: JSON.stringify({q, sugestao})})).resultados;
  assert.deepEqual((await buscar('São José 10')).map(item => item.imoveis), [[12], [15]]);
  const [completo] = await buscar('R. São José, nº 0010, bairro Vila de ensaio, Almirante Tamandaré/PR, Brasil, CEP 83500-100');
  assert.equal(completo.chave, '1:1');
  assert.deepEqual(completo.imoveis, [12]);
  assert.deepEqual((await buscar('Rua São José 10', true)).map(item => item.imoveis), [[12], [15], [13]]);
  assert.deepEqual((await buscar('Rua Sete de Setembro, S/N, Bairro de ensaio, Almirante Tamandaré - PR'))
    .map(item => item.imoveis), [[14]]);
  assert.deepEqual(await buscar('R. São José, 10, Vila errada'), []);
  assert.equal((await api('/api/geovsatt/quarteiroes/1/1')).localidade.nome, 'Vila de ensaio');
  await assert.rejects(api('/api/geovsatt/quarteiroes/2/2'), /não está na cópia/);
  await assert.rejects(api('/api/geovsatt/nominatim'), /conexão/);
});

test('quarteirões trabalhados recompõe o mapa e a exportação só dentro das datas baixadas', async () => {
  const lacre = pacote();
  const id = 'quarteiroes_trabalhados';
  const primeiro = {inicio: '2026-11-01', fim: '2026-11-08', tipo: 'TB', localidade: '1'};
  const {inicio, fim} = primeiro;
  const forma = retangulo(-49.4, -49.3, {id_quart: '1', Localidade: 1, chave: '1:1'});
  const visita = (chave, localidade, tipo, dia, total, normais = 0, fechadas = 0) =>
    ({chave, localidade, tipo, dia, total, normais, fechadas, recuperadas: 0});
  const inicial = {type: 'FeatureCollection', features: [forma], metadata: {consulta: primeiro,
    tipos: [{codigo: 'TB', nome: 'Tratamento'}, {codigo: 'PE', nome: 'Ponto estratégico'}]}};
  lacre.dados[id] = inicial;
  const rota = '/api/geovsatt/camadas/' + id;
  const api = criarApiLocal(lacre, [], () => {}, recortar);
  assert.deepEqual(await api(rota + '?localidade=2'), inicial);
  lacre.historico_trabalhos = {
    periodo: {inicio, fim}, malha: {'1:1': forma}, dias: [
      visita('1:1', '1', 'TB', '2026-11-01', 2, 2),
      visita('1:1', '1', 'PE', '2026-11-05', 3, 1, 1),
      visita('2:3', '2', 'PE', '2026-11-05', 1),
    ],
  };
  assert.deepEqual(await api(rota), inicial);
  const todas = await api(rota + '?inicio=2026-11-01&fim=2026-11-08');
  assert.equal(todas.features[0].properties.atividade, 'Mais de um tipo');
  assert.equal(todas.features[0].properties.tipos_registrados, 'Ponto estratégico (3), Tratamento (2)');
  assert.equal(todas.metadata.registros_no_recorte, 6);
  const pe = await api(rota + '?inicio=2026-11-05&fim=2026-11-05&tipo=PE');
  assert.deepEqual(pe.features[0].geometry, forma.geometry);
  assert.equal(pe.features[0].properties.atividade, 'Ponto estratégico');
  assert.equal(pe.features[0].properties.ultimo_registro, '2026-11-05');
  assert.equal(pe.features[0].properties.visitas_outras_situacoes, 1);
  assert.equal(pe.metadata.registros_sem_malha, 1);
  assert.deepEqual(JSON.parse(await exportar({nome: id}, pe, 'geojson').text()), pe);
  const outra = await api(rota + '?localidade=2');
  assert.equal(outra.features.length, 0);
  assert.equal(outra.metadata.registros_no_recorte, 1);
  await assert.rejects(api(rota + '?fim=2026-11-31'), /datas válidas/);
  await assert.rejects(api(rota + '?fim=2026-11-09'), /período desta cópia/);
});

test('exporta os três formatos e escapa fórmulas e atributos XML', async () => {
  const pontos = {type: 'FeatureCollection', features: [{type: 'Feature',
    geometry: {type: 'Point', coordinates: [-49.3, -25.3]}, properties: {nome: '=2+3', descricao: 'A&B'}}]};
  const camada = {nome: 'Ensaio'};
  assert.ok((await exportar(camada, pontos, 'csv').text()).includes('"\'=2+3"'));
  assert.match(await exportar(camada, pontos, 'kml').text(), /A&amp;B/);
  assert.deepEqual(JSON.parse(await exportar(camada, pontos, 'geojson').text()), pontos);
});

test('o worker prepara só a interface pública e abre a entrada local sem conexão', async () => {
  const codigo = readFileSync(new URL('../static/geovsatt-sw.js', import.meta.url), 'utf8');
  const offline = {body: 'interface sem dados privados'};
  const origem = 'https://geo.exemplo.invalid';
  const prefixo = 'geovsatt-app-';
  const cacheAnterior = new Map([
    ['/static/js/geovsatt_vetorial.mjs?v=2.27.2', {body: 'vetorial anterior'}],
    ['/static/js/geovsatt_dados_offline.mjs', {body: 'módulo anterior'}],
  ]);
  const armazenados = new Map([['outro-app', new Map()], [prefixo + '2.27.1', new Map()],
    [prefixo + '2.27.2', cacheAnterior]]);
  let falhaInstalacao = false;
  let statusDoServidor = 200;
  const caches = {
    has: async chave => armazenados.has(chave),
    keys: async () => Array.from(armazenados.keys()),
    delete: async chave => armazenados.delete(chave),
    async open(chave) {
      if (!armazenados.has(chave)) armazenados.set(chave, new Map());
      return {async addAll(requisicoes) {
        if (falhaInstalacao) throw Error('rede interrompida');
        for (const {url} of requisicoes) {
          const resposta = url.startsWith('/geovsatt/offline?') ? offline : {body: url};
          armazenados.get(chave).set(url, resposta);
        }
      }};
    },
    async match(entrada, {cacheName}) {
      const url = new URL(entrada.url || entrada, origem);
      return armazenados.get(cacheName)?.get(url.pathname + url.search);
    },
  };
  function worker(versao) {
    const eventos = {};
    runInNewContext(codigo, {
      URL, AbortSignal, Response, Request: class Request { constructor(url) { this.url = url; } },
      caches,
      fetch: async () => {
        if (!statusDoServidor) throw Error('sem conexão');
        return {status: statusDoServidor};
      },
      self: {location: {href: origem + '/geovsatt-sw.js?v=' + versao, origin: origem},
        addEventListener: (nome, executar) => { eventos[nome] = executar; }, skipWaiting() {},
        clients: {claim() {}}},
    });
    return eventos;
  }
  function finalizar(evento) {
    let pendente;
    evento({waitUntil: tarefa => { pendente = tarefa; }});
    return pendente;
  }
  const eventos = worker('2.27.3');
  await finalizar(eventos.install);
  const atual = armazenados.get(prefixo + '2.27.3');
  assert.ok(atual.has('/geovsatt/offline?v=2.27.3'));
  assert.ok(atual.has('/static/js/geovsatt_dados_offline.mjs?v=2.27.3'));
  for (const caminho of atual.keys()) {
    assert.ok(caminho.startsWith('/static/') || ['/geovsatt/offline?v=2.27.3', '/geovsatt/manifest.webmanifest'].includes(caminho));
    if (caminho.startsWith('/static/')) assert.ok(existsSync(new URL('..' + caminho.split('?')[0], import.meta.url)));
  }
  await finalizar(eventos.activate);
  assert.deepEqual([...armazenados.keys()], ['outro-app', prefixo + '2.27.2', prefixo + '2.27.3']);
  falhaInstalacao = true;
  await assert.rejects(finalizar(worker('2.27.4').install), /rede interrompida/);
  assert.equal(armazenados.has(prefixo + '2.27.4'), false);
  function visitar(caminho, method = 'GET', mode = 'navigate') {
    let resposta;
    eventos.fetch({request: {url: origem + caminho, method, mode},
      respondWith: tarefa => { resposta = tarefa; }});
    return resposta;
  }
  for (const autorizado of [200, 401, 403]) {
    statusDoServidor = autorizado;
    assert.equal((await visitar('/geovsatt')).status, autorizado);
  }
  statusDoServidor = 503;
  assert.equal(await visitar('/geovsatt'), offline);
  statusDoServidor = 0;
  assert.equal(await visitar('/geovsatt'), offline);
  assert.equal(await visitar('/geovsatt/offline'), offline);
  assert.equal((await visitar('/static/js/geovsatt_vetorial.mjs?v=2.27.2', 'GET', 'cors')).body, 'vetorial anterior');
  assert.equal((await visitar('/static/js/geovsatt_dados_offline.mjs', 'GET', 'cors')).body, 'módulo anterior');
  assert.equal((await visitar('/static/js/geovsatt_dados_offline.mjs?v=2.27.3', 'GET', 'cors')).body,
    '/static/js/geovsatt_dados_offline.mjs?v=2.27.3');
  assert.equal(visitar('/geovsatt/admin/camadas'), undefined);
  assert.equal(visitar('/api/geovsatt/pacote-offline', 'POST'), undefined);
  assert.equal(visitar('/api/geovsatt/pacote-offline/estado?v=2.27.3'), undefined);
});

test('a base vetorial local só é aceita após receber todos os recursos', async () => {
  const recorte = [-49.31, -25.33, -49.309, -25.329];
  const eventos = [
    {preparando: true},
    {estilo: {version: 8, layers: [], sources: {}}, recorte, total: 2},
    {chave: 'tile/9/185/293', dados: 'Cgg='},
    {chave: 'fonte/Noto Sans Regular/0-255.pbf', dados: 'CgM='},
    {concluido: true},
  ];
  const fluxo = linhas => {
    const bytes = new TextEncoder().encode(linhas.map(item => JSON.stringify(item)).join('\n'));
    return new ReadableStream({start(controller) {
      for (let i = 0; i < bytes.length; i += 11) controller.enqueue(bytes.subarray(i, i + 11));
      controller.close();
    }});
  };
  const progresso = [];
  const base = await lerBaseVetorial(fluxo(eventos), 1024, (atual, total) => progresso.push([atual, total]));
  assert.deepEqual(base.recorte, recorte);
  assert.equal(base.recursos['tile/9/185/293'], 'Cgg=');
  assert.deepEqual(progresso, [[0, 2], [2, 2]]);
  await assert.rejects(lerBaseVetorial(fluxo(eventos.slice(0, -1)), 1024, () => {}), /interrompido/);
  await assert.rejects(lerBaseVetorial(fluxo(eventos), 32, () => {}), /espaço disponível/);
});
