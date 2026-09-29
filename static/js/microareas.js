(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const fmt = value => new Intl.NumberFormat('pt-BR').format(Number(value || 0));
  const incluirCondominios = () => el('micro-incluir-condominios').checked;
  const populacaoArea = r => Number(r[incluirCondominios() ? 'populacao_com_condominios' : 'populacao_sem_condominios'] || 0);
  const codigo = value => {
    const raw = String(value ?? '').trim();
    return /^\d+(?:\.0+)?$/.test(raw) ? String(parseInt(raw, 10)).padStart(4, '0') : raw;
  };
  const chaveCor = 'endemias.microareas.cor-seed.v1';
  let seedCor = 1;
  try { seedCor = Number(localStorage.getItem(chaveCor)) || 1; } catch (_) { /* Navegação privada pode bloquear o armazenamento. */ }
  const estado = {iniciado:false, mapa:null, layer:null, geo:null, resumo:null, lista:[], acs:[], indicadores:null,
    coresMapa:{}, vizinhos:null, selecionados:new Set(), partes:[], partesLayer:null,
    desenho:null, desenhoLayer:null, trechos:[], editando:null, salvando:false};
  async function json(url, options) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.erro || `Erro HTTP ${resp.status}`);
    return data;
  }
  const status = texto => { el('micro-status').textContent = texto; };
  function ativos() {
    const id = Number(el('micro-localidade').value);
    return estado.geo?.features?.filter(f => Number(f.properties?.Localidade) === id) || [];
  }
  function chave(f) { return codigo(f.properties?.id_quart); }
  function resumoQ(q) {
    const loc = el('micro-localidade').value;
    const display = /^\d+$/.test(q) ? String(parseInt(q, 10)) : q;
    return estado.resumo?.quarteiroes?.[`${loc}:${display}`] || {};
  }
  function proprietario(q) {
    const loc = Number(el('micro-localidade').value);
    return estado.lista.find(r => Number(r.id_localidade) === loc && r.quarteiroes.includes(q)
      && (r.id_microarea !== estado.editando || estado.selecionados.has(q)));
  }
  function partesDoQ(q) {
    const loc = Number(el('micro-localidade').value);
    return estado.lista.flatMap(r => Number(r.id_localidade) === loc && r.id_microarea !== estado.editando
      ? r.partes.filter(p => p.quarteirao === q) : []).concat(estado.partes.filter(p => p.quarteirao === q));
  }
  const exibirQ = q => /^\d+$/.test(q) ? String(parseInt(q, 10)) : q;
  function filtrarListaQuarteiroes() {
    const busca = el('micro-q-busca').value.trim().toLocaleLowerCase('pt-BR');
    el('micro-q-lista').querySelectorAll('.micro-q-opcao').forEach(opcao => {
      const q = opcao.querySelector('input').value;
      opcao.hidden = !!busca && !q.toLocaleLowerCase('pt-BR').includes(busca)
        && !exibirQ(q).toLocaleLowerCase('pt-BR').includes(busca);
    });
  }
  function renderListaQuarteiroes() {
    const lista = el('micro-q-lista');
    if (!el('micro-localidade').value) {
      lista.innerHTML = '<div class="micro-q-vazio">Selecione uma localidade.</div>';
      return;
    }
    const quarteiroesComGeometria = new Set(ativos().map(chave));
    const quarteiroes = new Set(quarteiroesComGeometria);
    estado.selecionados.forEach(q => quarteiroes.add(q));
    lista.innerHTML = quarteiroes.size ? [...quarteiroes]
      .sort((a,b) => a.localeCompare(b, 'pt-BR', {numeric:true}))
      .map(q => {
        const dono = proprietario(q);
        const parcial = partesDoQ(q).length > 0;
        const ocupado = (dono && dono.id_microarea !== estado.editando) || parcial;
        const semGeometria = !quarteiroesComGeometria.has(q);
        return `<label class="micro-q-opcao"><input type="checkbox" value="${esc(q)}" ${estado.selecionados.has(q) ? 'checked' : ''} ${ocupado ? 'disabled' : ''}>
          <span>Q. ${esc(exibirQ(q))}</span><small>${parcial ? 'Com lados parciais' : ocupado ? `Microárea ${esc(dono.numero)}` : semGeometria ? 'Sem geometria' : ''}</small></label>`;
      }).join('') : '<div class="micro-q-vazio">Não há quarteirões nessa localidade.</div>';
    filtrarListaQuarteiroes();
  }
  function atualizarSelecao() {
    estado.layer?.setStyle(estilo);
    el('micro-q-lista').querySelectorAll('input[type="checkbox"]').forEach(input => {
      input.checked = estado.selecionados.has(input.value);
    });
    totais();
  }
  function cor(r) { return estado.coresMapa[String(r?.id_microarea)] || '#2563eb'; }
  function renderLegendaCores() {
    const loc = Number(el('micro-localidade').value);
    const rows = estado.lista.filter(r => Number(r.id_localidade) === loc)
      .sort((a, b) => Number(a.numero) - Number(b.numero));
    el('micro-cor-legenda').innerHTML = rows.length ? rows.map(r =>
      `<div class="micro-cor-item"><span class="micro-cor-amostra" style="background:${cor(r)}"></span>`
      + `<span>Microárea ${esc(r.numero)} · ${esc(r.acs_nome || r.acs_codigo || 'Sem ACS')}</span></div>`).join('')
      : '<span class="rg-muted">Selecione uma localidade com microáreas cadastradas.</span>';
  }
  function estilo(f) {
    const q = chave(f), dono = proprietario(q), selecionado = estado.selecionados.has(q);
    return {color:selecionado ? '#facc15' : dono ? cor(dono) : '#64748b', weight:selecionado ? 4 : dono ? 2 : 1.4,
      fillColor:dono ? cor(dono) : '#cbd5e1', fillOpacity:selecionado ? .72 : dono ? .55 : .23};
  }
  function totais() {
    let imoveis = 0, reais = 0, pop = 0;
    for (const q of estado.selecionados) {
      const r = resumoQ(q);
      imoveis += Number(r.imoveis || 0); reais += Number(r.imoveis_reais || 0); pop += Number(r.populacao_aproximada || 0);
    }
    for (const p of estado.partes) {
      const rg = p.rg || {};
      imoveis += Number(rg.imoveis || 0); reais += Number(rg.imoveis_reais || 0);
      pop += Math.round(Number(rg.residencias_reais || 0) * Number(estado.resumo?.media_pessoas_por_residencia || 2.93));
    }
    el('micro-total-q').textContent = fmt(new Set([...estado.selecionados, ...estado.partes.map(p => p.quarteirao)]).size);
    el('micro-total-imoveis').textContent = fmt(imoveis);
    el('micro-total-reais').textContent = fmt(reais);
    el('micro-total-pop').textContent = fmt(pop);
    el('micro-selected').innerHTML = estado.selecionados.size || estado.partes.length
      ? [...estado.selecionados].sort((a,b) => a.localeCompare(b, 'pt-BR', {numeric:true})).map(q => `<span>Q. ${esc(q)} inteiro</span>`)
        .concat(estado.partes.map(p => `<span>Q. ${esc(p.quarteirao)} · ${esc(p.logradouro)} · lado ${esc(p.lado)}</span>`)).join(' · ')
      : 'Nenhum quarteirão selecionado.';
  }
  function partesVisiveis() {
    const loc = Number(el('micro-localidade').value);
    const salvas = estado.lista.filter(r => Number(r.id_localidade) === loc).flatMap(r =>
      (r.id_microarea === estado.editando ? estado.partes : r.partes).map(p => ({...p, dono:r})));
    return estado.editando ? salvas : salvas.concat(estado.partes.map(p => ({...p, dono:null})));
  }
  function renderPartes() {
    if (estado.partesLayer) estado.mapa.removeLayer(estado.partesLayer);
    const features = partesVisiveis().map(p => ({type:'Feature', geometry:p.geometry,
      properties:{cor:cor(p.dono), titulo:`Q. ${p.quarteirao} · ${p.logradouro} · lado ${p.lado}`,
        desatualizada:p.base_desatualizada}}));
    estado.partesLayer = L.geoJSON({type:'FeatureCollection', features}, {
      interactive:!estado.desenho,
      style:f => ({color:f.properties.desatualizada ? '#b91c1c' : f.properties.cor,
        weight:3, fillColor:f.properties.cor, fillOpacity:.66, dashArray:f.properties.desatualizada ? '6 4' : null}),
      onEachFeature:(f, layer) => layer.bindTooltip(esc(f.properties.titulo))
    }).addTo(estado.mapa);
  }
  function renderMapa() {
    if (!estado.mapa) return;
    renderLegendaCores();
    if (estado.layer) {
      estado.layer.eachLayer(layer => layer.unbindTooltip());
      estado.mapa.removeLayer(estado.layer);
    }
    estado.layer = L.geoJSON({type:'FeatureCollection', features:ativos()}, {
      interactive:!estado.desenho,
      style:estilo,
      onEachFeature: (f, layer) => {
        const q = chave(f), dono = proprietario(q), r = resumoQ(q);
        if (el('micro-map-labels').checked) layer.bindTooltip(esc(exibirQ(q)), {permanent:true, direction:'center', className:'rg-map-label'});
        layer.bindPopup(`<strong>Quarteirão ${esc(q)}</strong><br>${dono ? `Microárea ${esc(dono.numero)} · ${esc(dono.acs_nome || dono.acs_codigo || 'Sem ACS')}` : 'Sem microárea'}<br>${fmt(r.imoveis)} imóvel(is) RG · ${fmt(r.populacao_aproximada)} hab. aprox.`);
        layer.on('click', () => {
          if (estado.desenho) return;
          el('micro-parcial-q').value = exibirQ(q);
          carregarTrechos(q);
          const tipos = Object.values(r.tipos || {}).sort((a,b) => Number(b.imoveis || 0) - Number(a.imoveis || 0));
          el('micro-detalhe').innerHTML = `<h3>Q. ${esc(q)}</h3>
            <div>${dono ? `Microárea ${esc(dono.numero)} · ACS ${esc(dono.acs_nome || dono.acs_codigo || 'não atribuído')}` : 'Sem microárea'}</div>
            <div>${fmt(r.imoveis)} imóveis RG · ${fmt(r.imoveis_reais)} imóveis reais · ${fmt(r.atualizados)} atualizados</div>
            <div>População aproximada: ${fmt(r.populacao_aproximada)}</div>
            ${tipos.length ? `<div style="margin-top:5px;">${tipos.map(t => `${esc(t.label || t.codigo)}: ${fmt(t.imoveis)}`).join(' · ')}</div>` : '<div>Sem imóveis cadastrados no RG.</div>'}`;
          if (dono && dono.id_microarea !== estado.editando) {
            status(`Quarteirão ${q} pertence à microárea ${dono.numero}. Abra essa microárea na lista para editá-la.`);
            return;
          }
          if (partesDoQ(q).length && !estado.selecionados.has(q)) {
            status(`Quarteirão ${q} já possui lados parciais. Use o editor de lados, não a seleção inteira.`);
            return;
          }
          if (estado.selecionados.has(q)) estado.selecionados.delete(q); else estado.selecionados.add(q);
          el('micro-q-busca').value = '';
          filtrarListaQuarteiroes();
          atualizarSelecao();
          [...el('micro-q-lista').querySelectorAll('input[type="checkbox"]')]
            .find(input => input.value === q)?.scrollIntoView({block:'nearest'});
        });
      }
    }).addTo(estado.mapa);
    renderPartes();
    if (estado.layer.getBounds().isValid() && !estado.mapa._microEnquadrado) {
      estado.mapa.fitBounds(estado.layer.getBounds(), {padding:[15,15]});
      estado.mapa._microEnquadrado = true;
    }
    totais();
  }
  function filtrar() {
    const loc = el('micro-filtro-localidade').value;
    const acs = el('micro-filtro-acs').value;
    const busca = el('micro-filtro-busca').value.trim().toLocaleLowerCase('pt-BR');
    return estado.lista.filter(r => (!loc || String(r.id_localidade) === loc)
      && (!acs || (acs === 'sem' ? !r.acs_codigo : r.acs_codigo === acs))
      && (!busca || [r.numero,r.localidade,r.acs_nome,r.acs_codigo,r.observacoes,...r.quarteiroes,
        ...r.partes.flatMap(p => [p.quarteirao, p.logradouro, p.lado])].some(v => String(v || '').toLocaleLowerCase('pt-BR').includes(busca))));
  }
  function barras(itens, maximo, valor, rotulo, mostrarValor=item => fmt(valor(item))) {
    return itens.length ? itens.map(item => `<div class="micro-bar-row">
      <span title="${esc(rotulo(item))}">${esc(rotulo(item))}</span>
      <div class="micro-bar-track"><span class="micro-bar-fill" style="width:${maximo && valor(item) ? Math.max(2, Math.round(valor(item) / maximo * 100)) : 0}%"></span></div>
      <strong>${esc(mostrarValor(item))}</strong></div>`).join('') : '<div class="rg-muted">Nenhum dado no recorte.</div>';
  }
  function renderPainel(rows) {
    const localidades = new Map(), agentes = new Map();
    let semACS = 0, pop = 0, popAtribuida = 0, unidadesCondominio = 0;
    const quarteiroesUnicos = new Set(), quarteiroesSemRG = new Set(), quarteiroesComRG = new Set();
    for (const r of rows) {
      const populacao = populacaoArea(r);
      semACS += !r.acs_codigo;
      (r.detalhes_quarteiroes || []).forEach(d => {
        const chave = `${r.id_localidade}:${d.quarteirao}`;
        quarteiroesUnicos.add(chave);
        (d.tem_rg ? quarteiroesComRG : quarteiroesSemRG).add(chave);
      });
      unidadesCondominio += Number(r.residencias_condominio || 0);
      pop += populacao;
      const local = localidades.get(r.id_localidade) || {nome:r.localidade, areas:0, sem:0};
      local.areas++; local.sem += !r.acs_codigo; localidades.set(r.id_localidade, local);
      if (r.acs_codigo) {
        popAtribuida += populacao;
        const acs = agentes.get(r.acs_codigo) || {nome:r.acs_nome || r.acs_codigo, areas:0, pop:0, comRG:0};
        acs.areas++; acs.pop += populacao; acs.comRG += Number(r.quarteiroes_com_rg || 0);
        agentes.set(r.acs_codigo, acs);
      }
    }
    const comRG = [...agentes.values()].filter(a => a.comRG).length;
    const quarteiroes = quarteiroesUnicos.size;
    const semRG = [...quarteiroesSemRG].filter(q => !quarteiroesComRG.has(q)).length;
    const media = comRG ? new Intl.NumberFormat('pt-BR', {maximumFractionDigits:1}).format(popAtribuida / comRG) : '—';
    const semAreaGlobal = Number(estado.indicadores?.acs_catalogo_sem_area_global || 0);
    const cards = [
      [rows.length, 'Microáreas no recorte'], [rows.length - semACS, 'Com ACS responsável'],
      [semACS, 'Sem ACS · atribuições pendentes', true], [agentes.size, 'ACS distintos no recorte'],
      [semAreaGlobal, 'ACS do catálogo sem microárea · global'], [media, 'Média da população estimada por ACS com RG'],
      [Math.max(0, semACS - semAreaGlobal), 'Diferença cadastral 1:1 · não é déficit real de pessoal'],
      [quarteiroes > semRG ? pop : '—', 'População estimada nas microáreas'], [semRG, `Quarteirões sem RG entre ${fmt(quarteiroes)}`, semRG > 0],
      [unidadesCondominio, 'Unidades residenciais em condomínios no RG'],
    ];
    el('micro-indicadores').innerHTML = cards.map(([numero, titulo, aviso]) =>
      `<div class="micro-metric${aviso ? ' warn' : ''}"><strong>${esc(numero)}</strong><span>${esc(titulo)}</span></div>`).join('');
    const locais = [...localidades.values()].sort((a,b) => b.areas - a.areas || a.nome.localeCompare(b.nome, 'pt-BR'));
    el('micro-por-localidade').innerHTML = barras(locais, Math.max(...locais.map(a => a.areas), 0), a => a.areas,
      a => `${a.nome}${a.sem ? ` · ${a.sem} sem ACS` : ''}`);
    const acs = [...agentes.values()].sort((a,b) => b.pop - a.pop || a.nome.localeCompare(b.nome, 'pt-BR'));
    el('micro-por-acs').innerHTML = barras(acs, Math.max(...acs.map(a => a.pop), 0), a => a.pop,
      a => `${a.nome} · ${a.areas} área(s)`, a => a.comRG ? fmt(a.pop) : 'Sem RG')
      + (acs.some(a => !a.comRG) ? '<div class="rg-muted">ACS sem quarteirão cadastrado no RG não têm estimativa. Confira também áreas com RG parcial no cadastro.</div>' : '');
    const vazias = rows.filter(r => !r.acs_codigo);
    el('micro-sem-acs').innerHTML = vazias.length ? `<div class="table-scroll"><table><thead><tr><th>Localidade</th><th>Microárea</th><th>Quarteirões</th><th>População estimada</th><th>Ação</th></tr></thead><tbody>${vazias.map(r => `<tr>
      <td>${esc(r.localidade)}</td><td>${esc(r.numero)}</td><td>${fmt(r.quarteiroes_total)}</td>
      <td>${r.quarteiroes_com_rg ? fmt(populacaoArea(r)) : 'Sem RG'}</td>
      <td><button class="btn btn-outline btn-sm" type="button" data-micro-edit="${Number(r.id_microarea)}">${el('micro-salvar') ? 'Atribuir ACS' : 'Ver no mapa'}</button></td></tr>`).join('')}</tbody></table></div>`
      : '<div class="rg-muted">Nenhuma microárea sem ACS neste recorte.</div>';
    el('micro-metodo').textContent = `População estimada por quarteirão a partir do RG (${estado.resumo?.media_pessoas_por_residencia || '2,93'} pessoas por residência; ${estado.resumo?.fonte_populacao || 'IBGE Censo 2022'}). Condomínios residenciais (campo condomínio > 0) estão ${incluirCondominios() ? 'incluídos' : 'excluídos integralmente'} na estimativa exibida. A média considera a população atribuída aos ${fmt(comRG)} ACS com ao menos um quarteirão com RG. Há ${fmt(semRG)} quarteirão(ões) sem RG no recorte. A diferença cadastral 1:1 compara as áreas vazias deste recorte com os ACS do catálogo sem área em todo o sistema; não mede disponibilidade ou déficit real de pessoal.`;
  }
  function renderLista() {
    const rows = filtrar();
    const porLocalidade = new Map();
    rows.forEach(r => porLocalidade.set(r.localidade, (porLocalidade.get(r.localidade) || 0) + 1));
    el('micro-resumo').textContent = `${fmt(rows.length)} microárea(s) · ${fmt(new Set(rows.flatMap(r => [...r.quarteiroes, ...r.partes.map(p => p.quarteirao)].map(q => `${r.id_localidade}:${q}`))).size)} quarteirão(ões) · ${fmt(rows.reduce((n,r) => n + r.partes.length,0))} lado(s) parcial(is) · ${fmt(rows.filter(r => !r.acs_codigo).length)} sem ACS · ${[...porLocalidade].map(([nome,n]) => `${nome}: ${n}`).join(' · ')}`;
    renderPainel(rows);
    el('micro-tabela').innerHTML = rows.length ? rows.map(r => `<tr>
      <td>${esc(r.localidade)}</td><td><strong>${esc(r.numero)}</strong></td>
      <td>${esc(r.acs_nome || r.acs_codigo || 'Sem ACS')}</td>
      <td>${fmt(r.quarteiroes_total)}<div class="rg-muted">${r.quarteiroes.map(q => `Q. ${esc(q)} inteiro`).concat(r.partes.map(p => `Q. ${esc(p.quarteirao)} · ${esc(p.logradouro)} · lado ${esc(p.lado)}${p.base_desatualizada ? ' (redesenhar)' : p.lado_ausente_rg ? ' (lado ausente do RG)' : ''}`)).join('<br>')}</div></td>
      <td>${r.quarteiroes_com_rg ? fmt(populacaoArea(r)) : 'Sem RG'}</td>
      <td>${fmt(r.quarteiroes_com_rg || 0)}/${fmt(r.quarteiroes_total)} quarteirões</td>
      <td>${r.partes.some(p => p.base_desatualizada) ? '<span class="rg-muted">Redesenhar lado parcial</span>' : r.partes.some(p => p.lado_ausente_rg) ? '<span class="rg-muted">Revisar lado ausente do RG</span>' : r.quarteiroes_sem_geometria.length ? `<span class="rg-muted">${fmt(r.quarteiroes_sem_geometria.length)} ausente(s): ${r.quarteiroes_sem_geometria.map(esc).join(', ')}</span>` : 'Completa'}</td>
      <td>${esc(r.observacoes || '-')}</td><td><button class="btn btn-outline btn-sm" type="button" data-micro-edit="${Number(r.id_microarea)}">${el('micro-salvar') ? 'Editar / trocar ACS' : 'Ver no mapa'}</button>
      ${el('micro-salvar') ? `<button class="btn btn-ghost btn-sm" type="button" data-micro-delete="${Number(r.id_microarea)}">Excluir</button>` : ''}</td></tr>`).join('')
      : '<tr><td colspan="9">Nenhuma microárea corresponde aos filtros.</td></tr>';
    for (const [formato,id] of [['xlsx','micro-xlsx'],['xlsx','micro-painel-xlsx'],['geojson','micro-geojson'],['kml','micro-kml'],['relatorio','micro-relatorio']]) {
      const link = el(id);
      const p = new URLSearchParams(); rows.forEach(r => p.append('id', r.id_microarea));
      if (!incluirCondominios() && (formato === 'xlsx' || formato === 'relatorio')) p.set('incluir_condominios', '0');
      link.href = rows.length ? (formato === 'relatorio' ? `/territorializacao/microareas/relatorio?${p}` : `/territorializacao/microareas/exportar/${formato}?${p}`) : '#';
      link.setAttribute('aria-disabled', rows.length ? 'false' : 'true');
    }
  }
  function renderACS() {
    const filtroAtual = el('micro-filtro-acs').value;
    const options = estado.acs.map(a => `<option value="${esc(a.acs_codigo)}">${esc(a.nome)} (${esc(a.acs_codigo)})</option>`).join('');
    el('micro-acs').innerHTML = '<option value="">Sem ACS</option>' + options;
    el('micro-filtro-acs').innerHTML = '<option value="">Todos</option><option value="sem">Sem ACS</option>' + options;
    el('micro-filtro-acs').value = filtroAtual;
  }
  function renderPartesSelecionadas() {
    el('micro-parcial-selecionados').innerHTML = estado.partes.length
      ? estado.partes.map((p, indice) => `<div class="micro-parcial-item"><span>Q. ${esc(exibirQ(p.quarteirao))} · ${esc(p.logradouro)} · lado ${esc(p.lado)}${p.base_desatualizada ? ' · <strong>redesenhar após alteração da geometria oficial</strong>' : p.lado_ausente_rg ? ' · <strong>lado ausente do RG; revisar cadastro</strong>' : ''}</span><button class="btn btn-outline btn-sm" type="button" data-parte-remover="${indice}">Retirar</button></div>`).join('')
      : '<div class="rg-muted">Nenhum lado parcial nesta microárea.</div>';
    totais();
  }
  async function carregarTrechos(q) {
    if (el('micro-cadastro').hidden || !el('micro-localidade').value) return;
    const chaveQ = codigo(q);
    const requisicao = `${el('micro-localidade').value}:${chaveQ}`;
    estado.parcialQ = chaveQ;
    estado.parcialRequisicao = requisicao;
    el('micro-parcial-lados').innerHTML = '<div class="rg-muted">Carregando lados do RG...</div>';
    try {
      const params = new URLSearchParams({localidade:el('micro-localidade').value, quarteirao:chaveQ});
      const dados = await json(`/api/territorializacao/microareas/trechos?${params}`);
      if (estado.parcialRequisicao !== requisicao) return;
      estado.trechos = dados.trechos || [];
      const inteiroOutro = dados.inteiro_id_microarea && dados.inteiro_id_microarea !== estado.editando;
      const microareaDona = estado.lista.find(r => r.id_microarea === dados.inteiro_id_microarea);
      const aviso = inteiroOutro && microareaDona
        ? `<div class="micro-parcial-aviso">Q. ${esc(exibirQ(chaveQ))} pertence por inteiro à microárea ${esc(microareaDona.numero)}. Abra essa microárea para converter o quarteirão em lados parciais. <button class="btn btn-outline btn-sm" type="button" data-parte-abrir="${Number(microareaDona.id_microarea)}">Editar microárea ${esc(microareaDona.numero)}</button></div>`
        : '';
      el('micro-parcial-lados').innerHTML = aviso + (estado.trechos.length ? estado.trechos.map((t, indice) => {
        const ocupado = inteiroOutro || (t.id_microarea && t.id_microarea !== estado.editando);
        const presente = estado.partes.some(p => p.quarteirao === chaveQ && p.logradouro === t.logradouro && p.lado === t.lado);
        return `<div class="micro-parcial-item"><span>${esc(t.logradouro)} · lado ${esc(t.lado)} · ${fmt(t.imoveis)} imóveis${ocupado ? ' · já atribuído' : ''}</span><button class="btn btn-outline btn-sm" type="button" data-parte-desenhar="${indice}" ${ocupado ? 'disabled' : ''}>${presente ? 'Redesenhar' : 'Desenhar'}</button></div>`;
      }).join('') : '<div class="rg-muted">O RG deste quarteirão não tem imóveis com lado preenchido. Corrija o RG antes de dividir.</div>');
      if (inteiroOutro) status(`Q. ${chaveQ} pertence por inteiro a outra microárea. Converta essa atribuição primeiro.`);
    } catch (e) { el('micro-parcial-lados').textContent = e.message; }
  }
  function atualizarDesenho() {
    if (estado.desenhoLayer) estado.mapa.removeLayer(estado.desenhoLayer);
    if (!estado.desenho) return;
    const pontos = estado.desenho.pontos;
    const layers = [pontos.length >= 3 ? L.polygon(pontos, {color:'#facc15',weight:3,fillOpacity:.25,interactive:false})
      : L.polyline(pontos, {color:'#facc15',weight:3,interactive:false})];
    pontos.forEach(p => layers.push(L.circleMarker(p, {radius:5,color:'#0f172a',fillColor:'#facc15',fillOpacity:1,interactive:false})));
    estado.desenhoLayer = L.layerGroup(layers).addTo(estado.mapa);
    el('micro-parcial-instrucao').textContent = `${estado.desenho.logradouro} · lado ${estado.desenho.lado}: ${pontos.length} vértice(s). Clique nos cantos no mapa; conclua com pelo menos três.`;
  }
  function cancelarDesenho(atualizarMapa=true) {
    const estavaDesenhando = !!estado.desenho;
    estado.desenho = null;
    if (estado.desenhoLayer) estado.mapa.removeLayer(estado.desenhoLayer);
    estado.desenhoLayer = null;
    el('micro-parcial-desenho').hidden = true;
    el('micro-mapa').style.cursor = '';
    if (estavaDesenhando && atualizarMapa) renderMapa();
  }
  function iniciarDesenho(indice) {
    const t = estado.trechos[indice], q = estado.parcialQ;
    if (!t || !q) return;
    if (t.id_microarea && t.id_microarea !== estado.editando) return;
    const dono = proprietario(q);
    if (dono && dono.id_microarea !== estado.editando) {
      status('Edite primeiro a microárea que possui esse quarteirão inteiro.'); return;
    }
    if (estado.selecionados.has(q)) {
      if (!confirm(`Converter Q. ${exibirQ(q)} de inteiro para parcial? Os lados não desenhados ficarão sem microárea.`)) return;
      estado.selecionados.delete(q); renderListaQuarteiroes(); atualizarSelecao();
    }
    cancelarDesenho(false);
    estado.desenho = {quarteirao:q, logradouro:t.logradouro, lado:t.lado, rg:t, pontos:[]};
    el('micro-parcial-desenho').hidden = false;
    el('micro-mapa').style.cursor = 'crosshair';
    renderMapa();
    const feature = ativos().find(f => chave(f) === q);
    if (feature) estado.mapa.fitBounds(L.geoJSON(feature).getBounds(), {padding:[35,35]});
    atualizarDesenho();
    status(`Desenhando ${t.logradouro} · lado ${t.lado}. Clique nos vértices no mapa.`);
  }
  async function concluirDesenho() {
    const d = estado.desenho;
    if (!d || d.pontos.length < 3) { status('Marque ao menos três vértices no mapa.'); return; }
    const anel = d.pontos.map(p => [Number(p.lng.toFixed(7)), Number(p.lat.toFixed(7))]);
    anel.push([...anel[0]]);
    const parte = {quarteirao:d.quarteirao, logradouro:d.logradouro, lado:d.lado, rg:d.rg,
      base_desatualizada:false, geometry:{type:'Polygon', coordinates:[anel]}};
    estado.partes = estado.partes.filter(p => !(p.quarteirao === parte.quarteirao && p.logradouro === parte.logradouro && p.lado === parte.lado));
    estado.partes.push(parte);
    cancelarDesenho(false); renderMapa(); renderListaQuarteiroes(); renderPartesSelecionadas();
    if (estado.editando) {
      status('Validando e salvando o lado parcial...');
      await salvar({lado:parte, manterEdicao:true});
    } else {
      carregarTrechos(parte.quarteirao);
      status('Desenho preparado, mas ainda não salvo. Preencha o número e clique em Criar microárea.');
    }
  }
  async function carregar() {
    const [geo, lista] = await Promise.all([
      json('/api/registro-geografico/geojson'), json('/api/territorializacao/microareas')]);
    estado.geo = geo; estado.resumo = lista.resumo_rg; estado.lista = lista.registros || []; estado.acs = lista.acs || [];
    estado.indicadores = lista.indicadores || null;
    estado.vizinhos = window.MicroareasCores.vizinhanca(estado.lista, estado.geo?.features || []);
    estado.coresMapa = window.MicroareasCores.atribuir(estado.lista, estado.geo?.features || [], seedCor, estado.vizinhos);
    renderACS(); renderLista(); renderListaQuarteiroes(); renderMapa();
  }
  async function iniciar() {
    if (estado.iniciado) { setTimeout(() => estado.mapa?.invalidateSize(), 100); return; }
    estado.iniciado = true;
    try {
      estado.mapa = L.map('micro-mapa', {zoomControl:true}).setView([-25.33,-49.29], 12);
      const baseMapa = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
        attribution:'Tiles © Esri — Esri, TomTom, Garmin, FAO, NOAA, USGS, © OpenStreetMap contributors, GIS User Community', maxZoom:19
      });
      const baseSatelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution:'© Esri, Earthstar Geographics', maxZoom:19
      });
      const baseSateliteRuas = L.layerGroup([
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          attribution:'© Esri', maxZoom:19
        }),
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
          attribution:'Labels © Esri', maxZoom:19
        })
      ]);
      baseMapa.addTo(estado.mapa);
      L.control.layers({'Mapa':baseMapa, 'Satélite':baseSatelite, 'Satélite + ruas':baseSateliteRuas}, {}, {
        position:'topright', collapsed:false
      }).addTo(estado.mapa);
      estado.mapa.on('click', ev => {
        if (!estado.desenho) return;
        if (estado.desenho.pontos.length >= 150) { status('Limite de 150 vértices atingido. Conclua o desenho.'); return; }
        estado.desenho.pontos.push(ev.latlng);
        atualizarDesenho();
      });
      await carregar();
    } catch (e) { status(e.message); el('micro-tabela').innerHTML = `<tr><td colspan="9">${esc(e.message)}</td></tr>`; estado.iniciado = false; }
  }
  function aba(nome) {
    document.querySelectorAll('[data-terr-area]').forEach(b => b.classList.toggle('active', b.dataset.terrArea === nome));
    el('terr-area-rg').hidden = nome !== 'rg'; el('terr-area-microareas').hidden = nome !== 'microareas';
    if (nome === 'microareas') iniciar(); else setTimeout(() => {
      if (typeof rgMapState !== 'undefined') rgMapState.map?.invalidateSize();
    }, 100);
  }
  function subAba(nome) {
    document.querySelectorAll('[data-micro-pane]').forEach(b => b.classList.toggle('active', b.dataset.microPane === nome));
    ['mapa','painel','lista'].forEach(p => { el(`micro-pane-${p}`).hidden = p !== nome; });
    el('micro-report-filters').hidden = nome === 'mapa';
    if (nome === 'mapa') setTimeout(() => estado.mapa?.invalidateSize(), 100);
    else renderLista();
  }
  function novo() {
    cancelarDesenho(false); estado.editando = null; estado.selecionados.clear(); estado.partes = []; el('micro-id').value = '';
    el('micro-numero').value = ''; el('micro-acs').value = ''; el('micro-observacoes').value = '';
    el('micro-parcial-q').value = ''; el('micro-parcial-lados').innerHTML = '';
    estado.parcialQ = null; estado.parcialRequisicao = null; estado.trechos = []; renderPartesSelecionadas();
    el('micro-cadastro-titulo').textContent = 'Nova microárea';
    if (el('micro-salvar')) el('micro-salvar').textContent = 'Criar microárea';
    el('micro-parcial-concluir').textContent = 'Concluir desenho';
    status('Nova microárea. Selecione os quarteirões.'); renderListaQuarteiroes(); renderMapa();
  }
  function abrir(id) {
    const r = estado.lista.find(item => item.id_microarea === id);
    if (!r) return;
    aba('microareas'); subAba('mapa');
    if (estado.mapa && String(r.id_localidade) !== el('micro-localidade').value) estado.mapa._microEnquadrado = false;
    el('micro-localidade').value = r.id_localidade;
    cancelarDesenho(false); estado.editando = r.id_microarea; estado.selecionados = new Set(r.quarteiroes);
    estado.partes = r.partes.map(p => ({...p})); estado.parcialQ = null; estado.parcialRequisicao = null;
    el('micro-parcial-q').value = ''; el('micro-parcial-lados').innerHTML = '';
    el('micro-id').value = r.id_microarea; el('micro-numero').value = r.numero;
    el('micro-acs').value = r.acs_codigo || ''; el('micro-observacoes').value = r.observacoes || '';
    el('micro-cadastro-titulo').textContent = `Editar microárea ${r.numero} · ${r.localidade}`;
    if (el('micro-salvar')) el('micro-salvar').textContent = 'Salvar alterações';
    el('micro-parcial-concluir').textContent = 'Concluir e salvar lado';
    status(r.partes.some(p => p.base_desatualizada) ? 'Atenção: o polígono oficial mudou. Redesenhe os lados marcados antes de salvar.'
      : r.partes.some(p => p.lado_ausente_rg) ? 'Atenção: um lado parcial deixou de existir no RG. Revise o cadastro antes de salvar.'
      : r.quarteiroes_sem_geometria.length ? 'Atenção: há quarteirões sem geometria na camada atual.' : `Editando microárea ${r.numero}.`);
    renderListaQuarteiroes(); renderMapa(); renderPartesSelecionadas();
    if (el('micro-salvar')) el('micro-cadastro').scrollIntoView({block:'nearest'});
  }
  async function salvar({lado=null, manterEdicao=false}={}) {
    if (estado.salvando) return;
    const loc = el('micro-localidade').value;
    if (!loc || !(estado.selecionados.size || estado.partes.length)) { status('Selecione um quarteirão inteiro ou desenhe um lado parcial.'); return; }
    if (estado.desenho) { status('Conclua ou cancele o desenho antes de salvar.'); return; }
    const payload = {id_localidade:Number(loc), numero:el('micro-numero').value,
      acs_codigo:el('micro-acs').value, observacoes:el('micro-observacoes').value,
      quarteiroes:[...estado.selecionados],
      partes:estado.partes.map(p => ({quarteirao:p.quarteirao, logradouro:p.logradouro,
        lado:p.lado, geometry:p.geometry, base_geometry_hash:p.base_geometry_hash}))};
    const id = estado.editando;
    estado.salvando = true;
    el('micro-salvar').disabled = true;
    let gravado = false;
    try {
      await json(id ? `/api/territorializacao/microareas/${id}` : '/api/territorializacao/microareas', {
        method:id ? 'PUT':'POST', headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name="csrf-token"]')?.content || ''}, body:JSON.stringify(payload)});
      gravado = true;
      const numero = payload.numero;
      await carregar();
      if (manterEdicao && id) {
        const registro = estado.lista.find(r => r.id_microarea === id);
        if (!registro?.partes.some(p => p.quarteirao === lado.quarteirao && p.logradouro === lado.logradouro && p.lado === lado.lado))
          throw new Error('A leitura atualizada não confirmou o lado salvo. Recarregue a página e confira antes de repetir.');
        abrir(id);
        el('micro-parcial-q').value = exibirQ(lado.quarteirao);
        await carregarTrechos(lado.quarteirao);
        status(`Lado ${lado.lado} de Q. ${exibirQ(lado.quarteirao)} salvo na microárea ${numero}.`);
      } else {
        novo(); status(`Microárea ${numero} salva.`);
      }
    } catch (e) { status(gravado ? `Gravação enviada, mas a conferência falhou: ${e.message}`
      : `Não foi salvo: ${e.message}. O desenho continua nesta tela para correção.`); }
    finally { estado.salvando = false; el('micro-salvar').disabled = false; }
  }
  async function excluir(id) {
    const r = estado.lista.find(item => item.id_microarea === id);
    if (!r || !confirm(`Excluir microárea ${r.numero} de ${r.localidade}? Os vínculos com ${r.quarteiroes_total} quarteirão(ões) e ${r.partes.length} lado(s) parcial(is) serão removidos.`)) return;
    try {
      await json(`/api/territorializacao/microareas/${id}`, {method:'DELETE', headers:{'X-CSRFToken':document.querySelector('meta[name="csrf-token"]')?.content || ''}});
      if (estado.editando === id) novo(); await carregar();
    } catch (e) { alert(e.message); }
  }
  document.querySelectorAll('[data-terr-area]').forEach(b => b.addEventListener('click', () => aba(b.dataset.terrArea)));
  document.querySelectorAll('[data-micro-pane]').forEach(b => b.addEventListener('click', () => subAba(b.dataset.microPane)));
  el('micro-localidade').addEventListener('change', () => {
    el('micro-q-busca').value = ''; el('micro-cor-aviso').textContent = '';
    if (estado.mapa) estado.mapa._microEnquadrado = false;
    novo();
  });
  el('micro-map-labels').addEventListener('change', renderMapa);
  el('micro-variar-cores').addEventListener('click', () => {
    const idsVisiveis = estado.lista.filter(r => String(r.id_localidade) === el('micro-localidade').value)
      .map(r => String(r.id_microarea));
    if (!idsVisiveis.length) {
      el('micro-cor-aviso').textContent = 'Selecione uma localidade com microáreas para variar as cores.';
      return;
    }
    const anterior = estado.coresMapa;
    let alterado = false;
    for (let tentativa = 0; tentativa < 12; tentativa++) {
      const novaSeed = Math.floor(Math.random() * 0xFFFFFFFF) || 1;
      const novasCores = window.MicroareasCores.atribuir(estado.lista, estado.geo?.features || [], novaSeed, estado.vizinhos);
      if (idsVisiveis.some(id => novasCores[id] !== anterior[id])) {
        seedCor = novaSeed; estado.coresMapa = novasCores; alterado = true; break;
      }
    }
    if (!alterado) { el('micro-cor-aviso').textContent = 'Não foi possível variar as cores agora.'; return; }
    try { localStorage.setItem(chaveCor, String(seedCor)); } catch (_) { /* A sessão atual continua funcionando. */ }
    estado.layer?.setStyle(estilo);
    renderPartes();
    renderLegendaCores();
    el('micro-cor-aviso').textContent = 'Cores variadas. Esta escolha fica neste navegador.';
  });
  el('micro-q-busca').addEventListener('input', filtrarListaQuarteiroes);
  el('micro-q-lista').addEventListener('change', ev => {
    const input = ev.target.closest('input[type="checkbox"]');
    if (!input || input.disabled) return;
    if (input.checked && partesDoQ(input.value).length) { input.checked = false; status('Este quarteirão já possui lados parciais.'); return; }
    if (input.checked) estado.selecionados.add(input.value); else estado.selecionados.delete(input.value);
    atualizarSelecao();
  });
  el('micro-q-selecionar').addEventListener('click', () => {
    el('micro-q-lista').querySelectorAll('.micro-q-opcao:not([hidden]) input:not(:disabled)').forEach(input => estado.selecionados.add(input.value));
    atualizarSelecao();
  });
  el('micro-q-limpar').addEventListener('click', () => { estado.selecionados.clear(); atualizarSelecao(); });
  el('micro-parcial-buscar').addEventListener('click', () => carregarTrechos(el('micro-parcial-q').value));
  el('micro-parcial-q').addEventListener('keydown', ev => {
    if (ev.key === 'Enter') { ev.preventDefault(); carregarTrechos(ev.currentTarget.value); }
  });
  el('micro-parcial-lados').addEventListener('click', ev => {
    const abrirMicroarea = ev.target.closest('[data-parte-abrir]');
    if (abrirMicroarea) {
      const q = estado.parcialQ;
      abrir(Number(abrirMicroarea.dataset.parteAbrir));
      el('micro-parcial-q').value = exibirQ(q);
      carregarTrechos(q);
      return;
    }
    const botao = ev.target.closest('[data-parte-desenhar]');
    if (botao && !botao.disabled) iniciarDesenho(Number(botao.dataset.parteDesenhar));
  });
  el('micro-parcial-selecionados').addEventListener('click', ev => {
    const botao = ev.target.closest('[data-parte-remover]');
    if (!botao) return;
    estado.partes.splice(Number(botao.dataset.parteRemover), 1);
    renderMapa(); renderListaQuarteiroes(); renderPartesSelecionadas();
    if (estado.parcialQ) carregarTrechos(estado.parcialQ);
  });
  el('micro-parcial-desfazer').addEventListener('click', () => {
    estado.desenho?.pontos.pop(); atualizarDesenho();
  });
  el('micro-parcial-concluir').addEventListener('click', concluirDesenho);
  el('micro-parcial-cancelar').addEventListener('click', cancelarDesenho);
  ['micro-filtro-localidade','micro-filtro-acs','micro-filtro-busca'].forEach(id => el(id).addEventListener('input', renderLista));
  el('micro-incluir-condominios').addEventListener('change', renderLista);
  el('micro-filtro-limpar').addEventListener('click', () => {
    ['micro-filtro-localidade','micro-filtro-acs','micro-filtro-busca'].forEach(id => { el(id).value = ''; });
    el('micro-incluir-condominios').checked = true;
    renderLista();
  });
  el('micro-ir-cadastro').addEventListener('click', () => subAba('lista'));
  el('micro-salvar')?.addEventListener('click', salvar);
  el('micro-nova')?.addEventListener('click', novo);
  const cliqueEditar = ev => {
    const edit = ev.target.closest('[data-micro-edit]'), del = ev.target.closest('[data-micro-delete]');
    if (edit) abrir(Number(edit.dataset.microEdit));
    if (del) excluir(Number(del.dataset.microDelete));
  };
  el('micro-tabela').addEventListener('click', cliqueEditar);
  el('micro-sem-acs').addEventListener('click', cliqueEditar);
  ['micro-xlsx','micro-painel-xlsx','micro-geojson','micro-kml','micro-relatorio'].forEach(id => el(id).addEventListener('click', ev => {
    if (ev.currentTarget.getAttribute('aria-disabled') === 'true') ev.preventDefault();
  }));
  if (location.hash === '#microareas') aba('microareas');
})();
