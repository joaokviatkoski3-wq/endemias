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
  const api = criarApiLocal(pacote(), [], () => {}, recortar);
  const busca = await api('/api/geovsatt/busca', {body: JSON.stringify({q: 'São José 10'})});
  assert.equal(busca.resultados[0].chave, '1:1');
  assert.deepEqual(busca.resultados[0].imoveis, [12]);
  assert.equal((await api('/api/geovsatt/quarteiroes/1/1')).localidade.nome, 'Vila de ensaio');
  await assert.rejects(api('/api/geovsatt/quarteiroes/2/2'), /não está na cópia/);
  await assert.rejects(api('/api/geovsatt/nominatim'), /conexão/);
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
  const eventos = {};
  const preparadas = new Set();
  const offline = {body: 'interface sem dados privados'};
  const origem = 'https://geo.exemplo.invalid';
  const cache = {
    async addAll(requisicoes) {
      for (const pedido of requisicoes) preparadas.add(pedido.url);
    },
    async match(entrada) {
      if ((entrada.url || entrada) === '/geovsatt/offline') return offline;
      return undefined;
    },
  };
  let conectado = true;
  const contexto = {
    URL, AbortSignal, Request: class Request { constructor(url) { this.url = url; } },
    caches: {open: async () => cache},
    fetch: async () => {
      if (!conectado) throw Error('sem conexão');
      return {status: 401};
    },
    self: {location: {href: origem + '/geovsatt-sw.js?v=2.26.0', origin: origem},
      addEventListener: (nome, executar) => { eventos[nome] = executar; }, skipWaiting() {}},
  };
  runInNewContext(readFileSync(new URL('../static/geovsatt-sw.js', import.meta.url), 'utf8'), contexto);
  let instalacao;
  eventos.install({waitUntil: tarefa => { instalacao = tarefa; }});
  await instalacao;
  assert.ok(preparadas.has('/geovsatt/offline'));
  for (const caminho of preparadas) {
    assert.ok(caminho.startsWith('/static/') || ['/geovsatt/offline', '/geovsatt/manifest.webmanifest'].includes(caminho));
    if (caminho.startsWith('/static/')) assert.ok(existsSync(new URL('..' + caminho.split('?')[0], import.meta.url)));
  }
  function visitar(caminho, method = 'GET') {
    let resposta;
    eventos.fetch({request: {url: origem + caminho, method, mode: 'navigate'},
      respondWith: tarefa => { resposta = tarefa; }});
    return resposta;
  }
  assert.equal((await visitar('/geovsatt')).status, 401);
  conectado = false;
  assert.equal(await visitar('/geovsatt'), offline);
  assert.equal(visitar('/geovsatt/admin/camadas'), undefined);
  assert.equal(visitar('/api/geovsatt/pacote-offline', 'POST'), undefined);
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
