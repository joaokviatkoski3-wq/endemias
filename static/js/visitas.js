const visitasConfig = JSON.parse(document.getElementById('visitas-config').textContent);
const visitasState = {
  pagina: 1,
  total: 0,
  totalPaginas: 1,
  registros: [],
  detalhes: new Map(),
  editando: null,
};

const visitasFilterIds = [
  'v_tipo', 'v_localidade', 'v_agente', 'v_resultado', 'v_imovel', 'v_deposito',
  'v_tratamento', 'v_coleta', 'v_tratado', 'v_laboratorio', 'v_agua_sanepar',
];

function visitasText(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

function visitasNum(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number : 0;
}

function visitasValue(value, fallback='-') {
  const text = String(value ?? '').trim();
  return text ? visitasText(text) : fallback;
}

function visitasSelected(id) {
  return Array.from(document.getElementById(id)?.selectedOptions || [])
    .map(option => option.value)
    .filter(Boolean);
}

function visitasParams(includePage=true) {
  const params = new URLSearchParams();
  params.set('d_ini', document.getElementById('v_d_ini').value || '');
  params.set('d_fim', document.getElementById('v_d_fim').value || '');
  const textFields = {
    busca: 'v_busca', observacoes: 'v_observacoes', coleta: 'v_coleta',
    tratado: 'v_tratado', laboratorio: 'v_laboratorio', agua_sanepar: 'v_agua_sanepar',
  };
  Object.entries(textFields).forEach(([key, id]) => {
    const value = document.getElementById(id).value.trim();
    if (value) params.set(key, value);
  });
  const multiples = {
    tipo: 'v_tipo', localidade: 'v_localidade', agente: 'v_agente', resultado: 'v_resultado',
    imovel: 'v_imovel', deposito: 'v_deposito', tratamento: 'v_tratamento',
  };
  Object.entries(multiples).forEach(([key, id]) => {
    visitasSelected(id).forEach(value => params.append(key, value));
  });
  params.set('ordem', document.getElementById('v_ordem').value);
  params.set('por_pagina', document.getElementById('v_por_pagina').value);
  if (includePage) params.set('pagina', visitasState.pagina);
  return params;
}

function atualizarContagemFiltros() {
  let count = 0;
  visitasFilterIds.forEach(id => {
    const element = document.getElementById(id);
    count += element?.multiple ? visitasSelected(id).length : (element?.value ? 1 : 0);
  });
  if (document.getElementById('v_busca').value.trim()) count += 1;
  if (document.getElementById('v_observacoes').value.trim()) count += 1;
  document.getElementById('visitas-filtros-contagem').textContent = count
    ? `${count} filtro${count === 1 ? '' : 's'} adicional${count === 1 ? '' : 'is'}`
    : 'Nenhum filtro adicional';
}

async function buscarVisitas(page=1) {
  visitasState.pagina = page;
  atualizarContagemFiltros();
  document.getElementById('visitas-lista').innerHTML = '<div class="loading-box"><div class="spinner"></div></div>';
  document.getElementById('visitas-paginacao').innerHTML = '';
  try {
    const data = await apiGet(`/api/visitas?${visitasParams()}`);
    visitasState.total = data.total || 0;
    visitasState.totalPaginas = data.total_paginas || 1;
    visitasState.pagina = data.pagina || 1;
    visitasState.registros = data.registros || [];
    renderVisitasResumo(data.resumo || {});
    renderVisitasLista(visitasState.registros);
    renderVisitasPaginacao();
  } catch (error) {
    document.getElementById('visitas-lista').innerHTML = `
      <div class="empty"><div class="empty-icon"><img src="/static/icons/alerta.svg" alt="" class="icon-svg"></div><p>${visitasText(error.message)}</p></div>`;
    document.getElementById('visitas-total-info').textContent = 'Não foi possível carregar os registros.';
  }
}

function renderVisitasResumo(summary) {
  const fields = {
    'vk-visitas': summary.visitas,
    'vk-acessados': summary.acessados,
    'vk-inspecionados': summary.depositos_inspecionados,
    'vk-eliminados': summary.depositos_eliminados,
    'vk-coletas': summary.coletas,
    'vk-positivas': summary.positivas,
  };
  Object.entries(fields).forEach(([id, value]) => {
    document.getElementById(id).textContent = fmtNum(visitasNum(value));
  });
  document.getElementById('visitas-total-info').textContent = `${fmtNum(visitasState.total)} visita${visitasState.total === 1 ? '' : 's'} no período e filtros selecionados`;
}

const visitasLabLabels = {
  positivo: 'Positivo para Aedes aegypti',
  negativo: 'Negativo para Aedes aegypti',
  pendente: 'Resultado laboratorial pendente',
  sem_coleta: 'Sem coleta',
};

function visitasStatusClass(value) {
  return String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-');
}

function renderVisitasLista(rows) {
  if (!rows.length) {
    document.getElementById('visitas-lista').innerHTML = `
      <div class="empty"><div class="empty-icon"><img src="/static/icons/prancheta.svg" alt="" class="icon-svg"></div><p>Nenhuma visita corresponde aos filtros selecionados.</p></div>`;
    return;
  }
  document.getElementById('visitas-lista').innerHTML = rows.map(row => {
    const address = [row.logradouro, row.numero].filter(Boolean).join(', ') || '-';
    const location = [row.localidade, row.quarteirao ? `Q. ${row.quarteirao}` : null].filter(Boolean).join(' · ') || '-';
    return `
      <article class="visita-registro" data-visita-id="${visitasText(row.id_visita)}">
        <div class="visita-registro-head">
          <div class="visita-identidade">
            <div class="visita-data">${fmtDate(row.data)}</div>
            <div class="visita-time">${row.hora_inicio ? visitasText(row.hora_inicio) : 'Horário não informado'}</div>
          </div>
          <div class="visita-endereco">
            <div class="visita-address-main">${visitasText(address)}</div>
            <div class="visita-address-meta">${visitasText(location)}${row.sequencia ? ` · Sequência ${visitasText(row.sequencia)}` : ''}</div>
          </div>
          <div class="visita-classificacao">
            <div class="visita-tags">
              <span class="visita-tag visita-tag-type">${visitasValue(row.tipo)}</span>
              <span class="visita-tag status-${visitasStatusClass(row.visita)}">${visitasValue(row.visita)}</span>
            </div>
            <div class="visita-property">${visitasValue(row.tipo_imovel)}</div>
          </div>
          <div class="visita-actions">
            <button class="btn btn-outline btn-sm" type="button" data-visita-action="details" data-visita-id="${visitasText(row.id_visita)}">Ver detalhes</button>
            ${visitasConfig.pode_editar ? `<button class="btn btn-ghost btn-sm" type="button" data-visita-action="edit" data-visita-id="${visitasText(row.id_visita)}"><img src="/static/icons/editar.svg" alt="" class="icon-svg"> Editar</button>` : ''}
          </div>
        </div>
        <div class="visita-registro-body">
          <div class="visita-context visita-context-agent"><span>Agente</span><strong>${visitasValue(row.agentes)}</strong></div>
          <div class="visita-context"><span>Morador</span><strong>${visitasValue(row.morador)}</strong></div>
          <div class="visita-operation-summary">
            <span><strong>${fmtNum(visitasNum(row.depositos_inspecionados))}</strong> inspecionados</span>
            <span><strong>${fmtNum(visitasNum(row.depositos_eliminados))}</strong> eliminados</span>
            <span><strong>${fmtNum(visitasNum(row.depositos_tratados))}</strong> tratados</span>
            <span><strong>${fmtNum(visitasNum(row.coletas_total))}</strong> coletas</span>
            ${row.tubos ? `<span>Tubos <strong>${visitasText(row.tubos)}</strong></span>` : ''}
          </div>
          <div class="visita-lab-status ${visitasText(row.laboratorio_status)}">${visitasLabLabels[row.laboratorio_status] || 'Sem informação laboratorial'}</div>
        </div>
        <div class="visita-detail" id="visita-detail-${visitasText(row.id_visita)}" hidden></div>
      </article>`;
  }).join('');
}

function renderVisitasPaginacao() {
  const area = document.getElementById('visitas-paginacao');
  if (visitasState.totalPaginas <= 1) {
    area.innerHTML = '';
    return;
  }
  const buttons = [];
  buttons.push(`<button class="pag-btn" type="button" data-page="${visitasState.pagina - 1}" ${visitasState.pagina <= 1 ? 'disabled' : ''}>‹</button>`);
  let ellipsis = false;
  for (let page = 1; page <= visitasState.totalPaginas; page += 1) {
    if (page === 1 || page === visitasState.totalPaginas || Math.abs(page - visitasState.pagina) <= 2) {
      buttons.push(`<button class="pag-btn ${page === visitasState.pagina ? 'active' : ''}" type="button" data-page="${page}">${page}</button>`);
      ellipsis = false;
    } else if (!ellipsis) {
      buttons.push('<span class="pag-ellipsis">...</span>');
      ellipsis = true;
    }
  }
  buttons.push(`<button class="pag-btn" type="button" data-page="${visitasState.pagina + 1}" ${visitasState.pagina >= visitasState.totalPaginas ? 'disabled' : ''}>›</button>`);
  area.innerHTML = `<div class="visitas-pagination">${buttons.join('')}<span class="pag-info">Página ${visitasState.pagina} de ${visitasState.totalPaginas}</span></div>`;
}

async function carregarDetalheVisita(id) {
  if (visitasState.detalhes.has(id)) return visitasState.detalhes.get(id);
  const detail = await apiGet(`/api/visitas/${encodeURIComponent(id)}`);
  visitasState.detalhes.set(id, detail);
  return detail;
}

async function alternarDetalheVisita(id, button) {
  const article = button.closest('.visita-registro');
  const panel = article.querySelector('.visita-detail');
  if (!panel.hidden) {
    panel.hidden = true;
    article.classList.remove('is-open');
    button.textContent = 'Ver detalhes';
    return;
  }
  panel.hidden = false;
  article.classList.add('is-open');
  button.textContent = 'Ocultar detalhes';
  panel.innerHTML = '<div class="visita-detail-loading"><div class="spinner"></div></div>';
  try {
    panel.innerHTML = renderDetalheVisita(await carregarDetalheVisita(id));
  } catch (error) {
    panel.innerHTML = `<div class="visita-empty-line">${visitasText(error.message)}</div>`;
  }
}

function detalheField(label, value, css='') {
  return `<div class="visita-detail-field ${css}"><span class="visita-field-label">${label}</span><div class="visita-field-value">${visitasValue(value)}</div></div>`;
}

function totalEspecie(row, prefix) {
  return ['larvas', 'pupas', 'exuvias', 'adulto'].reduce((total, field) => total + visitasNum(row[`${prefix}_${field}`]), 0);
}

function detalheEspecie(row, prefix, label) {
  return `<div class="visita-lab-breakdown"><strong>${label}</strong>: larvas ${fmtNum(visitasNum(row[`${prefix}_larvas`]))} · pupas ${fmtNum(visitasNum(row[`${prefix}_pupas`]))} · exúvias ${fmtNum(visitasNum(row[`${prefix}_exuvias`]))} · adultos ${fmtNum(visitasNum(row[`${prefix}_adulto`]))}</div>`;
}

function resultadoLaboratorio(row) {
  if (!row.id_resultado) return '<span class="visita-lab-status pendente">Pendente</span>';
  const aegypti = totalEspecie(row, 'aegypt');
  const status = aegypti > 0 ? '<span class="visita-lab-status positivo">Positivo para Aedes aegypti</span>' : '<span class="visita-lab-status negativo">Negativo para Aedes aegypti</span>';
  return `${status}<div class="visita-lab-details">${detalheEspecie(row, 'aegypt', 'Ae. aegypti')}${detalheEspecie(row, 'albopictus', 'Ae. albopictus')}${detalheEspecie(row, 'outra', 'Outras')}</div>`;
}

function renderDetalheVisita(detail) {
  const v = detail.visita || {};
  const deposits = detail.depositos || [];
  const treatments = detail.tratamentos || [];
  const samples = detail.coletas || [];
  const focuses = detail.focos || [];
  return `<div class="visita-detail-inner">
    <div class="visita-detail-grid">
      ${detalheField('Data', fmtDate(v.data))}
      ${detalheField('Horário', [v.hora_inicio, v.hora_fim].filter(Boolean).join(' - '))}
      ${detalheField('Tipo / ciclo', [v.tipo, v.ciclo ? `Ciclo ${v.ciclo}` : null].filter(Boolean).join(' · '))}
      ${detalheField('Resultado', v.visita)}
      ${detalheField('Localidade / quarteirão', [v.localidade_nome, v.quarteirao ? `Q. ${v.quarteirao}` : null].filter(Boolean).join(' · '), 'wide')}
      ${detalheField('Endereço', [v.logradouro, v.numero, v.sequencia ? `Seq. ${v.sequencia}` : null].filter(Boolean).join(', '), 'wide')}
      ${detalheField('Morador', v.morador)}
      ${detalheField('Tipo do imóvel', v.tipo_imovel)}
      ${detalheField('Lado', v.lado)}
      ${detalheField('Água Sanepar', v.agua_sanepar === 1 ? 'Sim' : (v.agua_sanepar === 0 ? 'Não' : null))}
      ${detalheField('Agentes', v.agentes, 'wide')}
      ${detalheField('Observações', v.observacoes, 'wide')}
      ${detalheField('Identificador da visita', v.id_visita, 'wide')}
      ${detalheField('Código / identificador do PE', [v.codigo_pe, v.id_pe].filter(Boolean).join(' · '), 'wide')}
      ${detalheField('Kobo ID / UUID', [v.kobo_id, v.kobo_uuid].filter(Boolean).join(' · '), 'wide')}
      ${detalheField('Envio Kobo / processamento', [v.submission_time, v.processado_em].filter(Boolean).join(' · '), 'wide')}
      ${detalheField('SisPNCD / Conta Ovos', [v.SISPNCD, v.CONTAOVOS_STATUS].filter(value => value !== null && value !== undefined && value !== '').join(' · '), 'wide')}
    </div>
    <section class="visita-detail-section">
      <h3><img src="/static/icons/balde.svg" alt="" class="icon-svg"> Depósitos inspecionados</h3>
      ${deposits.length ? `<div class="table-scroll"><table class="visita-detail-table"><thead><tr><th>Tipo</th><th>Inspecionados</th><th>Eliminados</th><th>Tratados</th><th>Produto</th><th>Carga</th></tr></thead><tbody>${deposits.map(row => `<tr><td>${visitasValue(row.tipo_deposito)}</td><td>${fmtNum(visitasNum(row.inspecionado))}</td><td>${fmtNum(visitasNum(row.eliminado))}</td><td>${fmtNum(visitasNum(row.tratado))}</td><td>${visitasValue(row.tipo_tratamento)}</td><td>${visitasNum(row.qtd_carga) || '-'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="visita-empty-line">Nenhum depósito registrado nesta visita.</div>'}
    </section>
    <section class="visita-detail-section">
      <h3><img src="/static/icons/borrifador.svg" alt="" class="icon-svg"> Produtos e tratamentos</h3>
      ${treatments.length ? `<div class="table-scroll"><table class="visita-detail-table"><thead><tr><th>Produto ou tratamento</th><th>Depósitos tratados</th><th>Quantidade de carga</th></tr></thead><tbody>${treatments.map(row => `<tr><td>${visitasValue(row.tipo)}</td><td>${fmtNum(visitasNum(row.qtd_depositos_tratados))}</td><td>${visitasNum(row.quantidade_carga) || '-'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="visita-empty-line">Nenhum tratamento adicional registrado.</div>'}
    </section>
    <section class="visita-detail-section">
      <h3><img src="/static/icons/tubo_ensaio.svg" alt="" class="icon-svg"> Coletas e resultados laboratoriais</h3>
      ${samples.length ? `<div class="table-scroll"><table class="visita-detail-table"><thead><tr><th>Tubo</th><th>Cód. depósito</th><th>Tipo</th><th>Eliminado</th><th>Coleta</th><th>Leitura</th><th>Resultado completo</th><th>Laboratorista</th></tr></thead><tbody>${samples.map(row => `<tr><td>${visitasValue(row.num_tubo)}</td><td>${visitasValue(row.codigo_deposito)}</td><td>${visitasValue(row.tipo_deposito)}</td><td>${row.deposito_eliminado ? 'Sim' : 'Não'}</td><td>${row.data_coleta ? fmtDate(row.data_coleta) : '-'}</td><td>${row.data_leitura ? fmtDate(row.data_leitura) : '-'}</td><td>${resultadoLaboratorio(row)}</td><td>${visitasValue(row.laboratorista)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="visita-empty-line">Nenhuma coleta registrada nesta visita.</div>'}
    </section>
    ${focuses.length ? `<section class="visita-detail-section"><h3><img src="/static/icons/alerta.svg" alt="" class="icon-svg"> Notificações relacionadas</h3><div class="table-scroll"><table class="visita-detail-table"><thead><tr><th>Código</th><th>Tubo</th><th>Gera notificação</th><th>Situação</th><th>Entrega</th><th>Observações</th></tr></thead><tbody>${focuses.map(row => `<tr><td>${visitasValue(row.codigo)}</td><td>${visitasValue(row.num_tubo)}</td><td>${row.gera_notificacao ? 'Sim' : 'Não'}</td><td>${visitasValue(row.status_notificacao)}</td><td>${row.data_entrega ? fmtDate(row.data_entrega) : '-'}</td><td>${visitasValue(row.observacoes)}</td></tr>`).join('')}</tbody></table></div></section>` : ''}
  </div>`;
}

function optionList(options, selected, blankLabel=null) {
  const values = [...options];
  if (selected && !values.includes(selected)) values.unshift(selected);
  return `${blankLabel !== null ? `<option value="">${visitasText(blankLabel)}</option>` : ''}${values.map(value => `<option value="${visitasText(value)}" ${String(value) === String(selected ?? '') ? 'selected' : ''}>${visitasText(value)}</option>`).join('')}`;
}

function inputValue(value) { return visitasText(value ?? ''); }

function depositoEditorRow(row={}) {
  return `<tr data-editor-row="deposito">
    <td><input data-field="tipo_deposito" value="${inputValue(row.tipo_deposito)}" placeholder="A1, B, D1..."></td>
    <td><input data-field="inspecionado" type="number" min="0" value="${visitasNum(row.inspecionado)}"></td>
    <td><input data-field="eliminado" type="number" min="0" value="${visitasNum(row.eliminado)}"></td>
    <td><input data-field="tratado" type="number" min="0" value="${visitasNum(row.tratado)}"></td>
    <td><input data-field="tipo_tratamento" list="visitas-tratamentos" value="${inputValue(row.tipo_tratamento)}"></td>
    <td><input data-field="qtd_carga" type="number" min="0" step="0.01" value="${visitasNum(row.qtd_carga)}"></td>
    <td class="editor-remove"><button class="btn-icon" type="button" data-remove-row title="Remover depósito"><img src="/static/icons/lixeira.svg" alt="Remover" class="icon-svg"></button></td>
  </tr>`;
}

function tratamentoEditorRow(row={}) {
  return `<tr data-editor-row="tratamento">
    <td><input data-field="tipo" list="visitas-tratamentos" value="${inputValue(row.tipo)}" placeholder="Produto utilizado"></td>
    <td><input data-field="qtd_depositos_tratados" type="number" min="0" value="${visitasNum(row.qtd_depositos_tratados)}"></td>
    <td><input data-field="quantidade_carga" type="number" min="0" step="0.01" value="${visitasNum(row.quantidade_carga)}"></td>
    <td class="editor-remove"><button class="btn-icon" type="button" data-remove-row title="Remover tratamento"><img src="/static/icons/lixeira.svg" alt="Remover" class="icon-svg"></button></td>
  </tr>`;
}

function coletaEditorRow(row={}) {
  const hasResult = Boolean(row.id_resultado);
  return `<tr data-editor-row="coleta" data-id="${inputValue(row.id_coleta)}">
    <td><input data-field="num_tubo" value="${inputValue(row.num_tubo)}"></td>
    <td><input data-field="codigo_deposito" value="${inputValue(row.codigo_deposito)}"></td>
    <td><input data-field="tipo_deposito" value="${inputValue(row.tipo_deposito)}"></td>
    <td class="text-center"><input class="editor-check" data-field="deposito_eliminado" type="checkbox" ${row.deposito_eliminado ? 'checked' : ''}></td>
    <td>${hasResult ? resultadoLaboratorio(row) : '<span class="visita-lab-status pendente">Pendente</span>'}</td>
    <td class="editor-remove">${hasResult ? '<span title="Coletas com resultado não podem ser removidas">-</span>' : '<button class="btn-icon" type="button" data-remove-row title="Remover coleta"><img src="/static/icons/lixeira.svg" alt="Remover" class="icon-svg"></button>'}</td>
  </tr>`;
}

async function abrirEditarVisita(id) {
  try {
    const detail = await carregarDetalheVisita(id);
    visitasState.editando = id;
    const v = detail.visita || {};
    document.getElementById('visita-edit-id').textContent = id;
    document.getElementById('visita-edit-body').innerHTML = `
      <section class="visitas-edit-section">
        <div class="visitas-edit-section-head"><h3>Dados da visita</h3><span class="visitas-edit-note">Os identificadores técnicos do Kobo são preservados.</span></div>
        <div class="visitas-edit-grid">
          <div class="f-g"><label>Tipo de trabalho</label><select id="edit_tipo">${optionList(visitasConfig.tipos, v.tipo, 'Selecione')}</select></div>
          <div class="f-g"><label>Data</label><input id="edit_data" type="date" value="${inputValue(v.data)}"></div>
          <div class="f-g"><label>Hora inicial</label><input id="edit_hora_inicio" type="time" value="${inputValue(v.hora_inicio)}"></div>
          <div class="f-g"><label>Hora final</label><input id="edit_hora_fim" type="time" value="${inputValue(v.hora_fim)}"></div>
          <div class="f-g"><label>Localidade</label><input id="edit_localidade" list="visitas-localidades" value="${inputValue(v.localidade_nome || v.localidade)}"></div>
          <div class="f-g"><label>Quarteirão</label><input id="edit_quarteirao" type="number" value="${inputValue(v.quarteirao)}"></div>
          <div class="f-g"><label>Ciclo</label><input id="edit_ciclo" type="number" value="${inputValue(v.ciclo)}"></div>
          <div class="f-g"><label>Lado</label><input id="edit_lado" value="${inputValue(v.lado)}"></div>
          <div class="f-g span-2"><label>Logradouro</label><input id="edit_logradouro" value="${inputValue(v.logradouro)}"></div>
          <div class="f-g"><label>Número</label><input id="edit_numero" value="${inputValue(v.numero)}"></div>
          <div class="f-g"><label>Sequência</label><input id="edit_sequencia" value="${inputValue(v.sequencia)}"></div>
          <div class="f-g span-2"><label>Morador</label><input id="edit_morador" value="${inputValue(v.morador)}"></div>
          <div class="f-g"><label>Tipo do imóvel</label><select id="edit_tipo_imovel">${optionList(visitasConfig.imoveis, v.tipo_imovel, 'Sem informação')}</select></div>
          <div class="f-g"><label>Resultado</label><select id="edit_visita">${optionList(visitasConfig.resultados, v.visita, 'Sem informação')}</select></div>
          <div class="f-g"><label>Água Sanepar</label><select id="edit_agua_sanepar"><option value="" ${v.agua_sanepar == null ? 'selected' : ''}>Sem informação</option><option value="1" ${v.agua_sanepar === 1 ? 'selected' : ''}>Sim</option><option value="0" ${v.agua_sanepar === 0 ? 'selected' : ''}>Não</option></select></div>
          <div class="f-g span-4"><label>Agentes</label><input id="edit_agentes" list="visitas-agentes" value="${inputValue(v.agentes)}" placeholder="Separe os nomes por vírgula"></div>
          <div class="f-g span-4"><label>Observações</label><textarea id="edit_observacoes">${visitasText(v.observacoes || '')}</textarea></div>
        </div>
      </section>
      <section class="visitas-edit-section">
        <div class="visitas-edit-section-head"><div><h3>Depósitos inspecionados</h3><span class="visitas-edit-note">Quantidades, eliminação e tratamento registrados na visita.</span></div><button class="btn btn-outline btn-sm" type="button" data-add-row="deposito"><img src="/static/icons/mais.svg" alt="" class="icon-svg"> Adicionar</button></div>
        <div class="visitas-edit-table-scroll"><table class="visitas-editor-table"><thead><tr><th>Tipo</th><th>Inspec.</th><th>Elimin.</th><th>Tratados</th><th>Produto</th><th>Carga</th><th></th></tr></thead><tbody id="edit-depositos-body">${(detail.depositos || []).map(depositoEditorRow).join('')}</tbody></table></div>
      </section>
      <section class="visitas-edit-section">
        <div class="visitas-edit-section-head"><div><h3>Produtos e tratamentos</h3><span class="visitas-edit-note">Registros complementares de tratamento da visita.</span></div><button class="btn btn-outline btn-sm" type="button" data-add-row="tratamento"><img src="/static/icons/mais.svg" alt="" class="icon-svg"> Adicionar</button></div>
        <div class="visitas-edit-table-scroll"><table class="visitas-editor-table"><thead><tr><th>Produto ou tratamento</th><th>Depósitos tratados</th><th>Quantidade de carga</th><th></th></tr></thead><tbody id="edit-tratamentos-body">${(detail.tratamentos || []).map(tratamentoEditorRow).join('')}</tbody></table></div>
      </section>
      <section class="visitas-edit-section">
        <div class="visitas-edit-section-head"><div><h3>Coletas</h3><span class="visitas-edit-note">Resultados laboratoriais são exibidos aqui e permanecem sob controle do laboratório.</span></div><button class="btn btn-outline btn-sm" type="button" data-add-row="coleta"><img src="/static/icons/mais.svg" alt="" class="icon-svg"> Adicionar</button></div>
        <div class="visitas-edit-table-scroll"><table class="visitas-editor-table"><thead><tr><th>Tubo</th><th>Cód. depósito</th><th>Tipo depósito</th><th>Eliminado</th><th>Resultado</th><th></th></tr></thead><tbody id="edit-coletas-body">${(detail.coletas || []).map(coletaEditorRow).join('')}</tbody></table></div>
      </section>`;
    document.getElementById('visita-edit-modal').hidden = false;
    document.body.style.overflow = 'hidden';
  } catch (error) {
    toast(`Não foi possível abrir a visita: ${error.message}`, 'error');
  }
}

function fecharEditarVisita() {
  visitasState.editando = null;
  document.getElementById('visita-edit-modal').hidden = true;
  document.body.style.overflow = '';
}

function editorRows(type) {
  return Array.from(document.querySelectorAll(`[data-editor-row="${type}"]`));
}

function editorRowData(row, fields) {
  const data = {};
  fields.forEach(field => {
    const input = row.querySelector(`[data-field="${field}"]`);
    data[field] = input?.type === 'checkbox' ? Boolean(input.checked) : (input?.value ?? '');
  });
  return data;
}

async function salvarEditarVisita() {
  if (!visitasState.editando) return;
  const saveButton = document.getElementById('visita-edit-save');
  saveButton.disabled = true;
  const payload = {
    tipo: document.getElementById('edit_tipo').value,
    data: document.getElementById('edit_data').value,
    hora_inicio: document.getElementById('edit_hora_inicio').value,
    hora_fim: document.getElementById('edit_hora_fim').value,
    localidade: document.getElementById('edit_localidade').value,
    quarteirao: document.getElementById('edit_quarteirao').value,
    ciclo: document.getElementById('edit_ciclo').value,
    lado: document.getElementById('edit_lado').value,
    logradouro: document.getElementById('edit_logradouro').value,
    numero: document.getElementById('edit_numero').value,
    sequencia: document.getElementById('edit_sequencia').value,
    morador: document.getElementById('edit_morador').value,
    tipo_imovel: document.getElementById('edit_tipo_imovel').value,
    visita: document.getElementById('edit_visita').value,
    agua_sanepar: document.getElementById('edit_agua_sanepar').value,
    agentes: document.getElementById('edit_agentes').value,
    observacoes: document.getElementById('edit_observacoes').value,
    depositos: editorRows('deposito').map(row => editorRowData(row, ['tipo_deposito', 'inspecionado', 'eliminado', 'tratado', 'tipo_tratamento', 'qtd_carga'])),
    tratamentos: editorRows('tratamento').map(row => editorRowData(row, ['tipo', 'qtd_depositos_tratados', 'quantidade_carga'])),
    coletas: editorRows('coleta').map(row => ({id_coleta: row.dataset.id || '', ...editorRowData(row, ['num_tubo', 'codigo_deposito', 'tipo_deposito', 'deposito_eliminado'])})),
  };
  try {
    const id = visitasState.editando;
    await apiPost(`/api/visitas/${encodeURIComponent(id)}/editar`, payload);
    visitasState.detalhes.delete(id);
    fecharEditarVisita();
    toast('Visita atualizada com sucesso.', 'success');
    await buscarVisitas(visitasState.pagina);
  } catch (error) {
    toast(`Erro ao salvar a visita: ${error.message}`, 'error', 5000);
  } finally {
    saveButton.disabled = false;
  }
}

function limparFiltrosVisitas() {
  document.getElementById('v_d_ini').value = visitasConfig.d_ini;
  document.getElementById('v_d_fim').value = visitasConfig.d_fim;
  ['v_busca', 'v_observacoes'].forEach(id => { document.getElementById(id).value = ''; });
  visitasFilterIds.forEach(id => {
    const element = document.getElementById(id);
    if (element.multiple) {
      Array.from(element.options).forEach(option => { option.selected = false; });
      const picker = element.nextElementSibling;
      picker?.querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = false; });
      updateMultiPickerLabel(element);
    } else {
      element.value = '';
    }
  });
  document.getElementById('v_ordem').value = 'data_desc';
  buscarVisitas(1);
}

function exportarVisitas() {
  const params = visitasParams(false);
  params.delete('ordem');
  params.delete('por_pagina');
  window.location = `/api/visitas/exportar?${params}`;
}

document.getElementById('visitas-lista').addEventListener('click', event => {
  const button = event.target.closest('[data-visita-action]');
  if (!button) return;
  const id = button.dataset.visitaId;
  if (button.dataset.visitaAction === 'details') alternarDetalheVisita(id, button);
  if (button.dataset.visitaAction === 'edit') abrirEditarVisita(id);
});

document.getElementById('visitas-paginacao').addEventListener('click', event => {
  const button = event.target.closest('[data-page]');
  if (!button || button.disabled) return;
  buscarVisitas(Number(button.dataset.page));
  document.querySelector('.visitas-results')?.scrollIntoView({behavior: 'smooth', block: 'start'});
});

document.getElementById('visita-edit-body').addEventListener('click', event => {
  const remove = event.target.closest('[data-remove-row]');
  if (remove) remove.closest('[data-editor-row]')?.remove();
  const add = event.target.closest('[data-add-row]');
  if (!add) return;
  const type = add.dataset.addRow;
  const targets = {deposito: 'edit-depositos-body', tratamento: 'edit-tratamentos-body', coleta: 'edit-coletas-body'};
  const renderers = {deposito: depositoEditorRow, tratamento: tratamentoEditorRow, coleta: coletaEditorRow};
  document.getElementById(targets[type])?.insertAdjacentHTML('beforeend', renderers[type]({}));
});

document.getElementById('visita-edit-modal').addEventListener('click', event => {
  if (event.target === event.currentTarget) fecharEditarVisita();
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !document.getElementById('visita-edit-modal').hidden) fecharEditarVisita();
});

['v_busca', 'v_observacoes'].forEach(id => {
  document.getElementById(id).addEventListener('input', atualizarContagemFiltros);
  document.getElementById(id).addEventListener('keydown', event => {
    if (event.key === 'Enter') buscarVisitas(1);
  });
});
['v_d_ini', 'v_d_fim', ...visitasFilterIds].forEach(id => {
  document.getElementById(id)?.addEventListener('change', atualizarContagemFiltros);
});
['v_ordem', 'v_por_pagina'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => buscarVisitas(1));
});

buscarVisitas();
