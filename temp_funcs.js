function renderEspResumoVisitas(rows) {
  const html = rows.length ? rows.map(r => `
    <tr>
      <td>${fmtDate(r.data)}</td>
      <td>${escapeHtml(r.localidade || '-')}</td>
      <td>${escapeHtml(r.quarteirao ?? '-')}</td>
      <td class="esporo-address">${escapeHtml([r.logradouro, r.numero].filter(Boolean).join(', ') || '-')}</td>
      <td>${escapeHtml(r.morador || '-')}</td>
      <td>${escapeHtml(r.visita || '-')}</td>
      <td><strong>${fmtNum(r.animais)}</strong></td>
    </tr>
  `).join('') : '<tr><td colspan="7" class="empty-inline">Nenhuma visita encontrada.</td></tr>';
  document.getElementById('esp-resumo-visitas-body').innerHTML = html;
}

function renderEspVisitas(rows, total) {
  document.getElementById('esp-visitas-body').innerHTML = rows.length ? rows.map(r => `
    <tr data-id="${escapeHtml(r.id_visita)}">
      <td>${fmtDate(r.data)}</td>
      <td>${escapeHtml(r.hora_inicio || '-')}</td>
      <td>${escapeHtml(r.agentes || '-')}</td>
      <td>${escapeHtml(r.localidade || '-')}</td>
      <td>${escapeHtml(r.quarteirao ?? '-')}</td>
      <td>${escapeHtml(r.tipo_imovel || '-')}</td>
      <td class="esporo-address">${escapeHtml([r.logradouro, r.numero].filter(Boolean).join(', ') || '-')}</td>
      <td>${escapeHtml(r.morador || '-')}</td>
      <td class="esporo-nowrap">${escapeHtml(r.telefone || '-')}</td>
      <td>${escapeHtml(r.visita || '-')}</td>
      <td><strong>${fmtNum(r.animais)}</strong></td>
      <td>${escapeHtml(r.deseja_cadastrar_animal || '-')}</td>
      <td><button class="btn btn-ghost btn-sm" type="button" onclick="editarVisita('${escapeHtml(r.id_visita)}')"><img src="/static/icons/editar.svg" alt="" class="icon-svg"></button></td>
    </tr>
  `).join('') : '<tr><td colspan="13" class="empty-inline">Nenhuma visita encontrada.</td></tr>';
  document.getElementById('esp-visitas-info').textContent = `${fmtNum(total)} visita(s) Â· ${fmtNum(rows.length)} exibida(s)`;
}

function renderEspAnimais(rows, total, bodyId, infoId) {
  document.getElementById(infoId).textContent = `${fmtNum(total)} animal(is) Â· ${fmtNum(rows.length)} exibido(s)`;
  document.getElementById(bodyId).innerHTML = rows.length ? rows.map(r => `
    <tr data-id="${escapeHtml(r.id_animal)}">
      <td><strong>${escapeHtml(r.nome || '-')}</strong><div class="muted">${fmtDate(r.data)} Â· ${escapeHtml(r.localidade || '-')}</div></td>
      <td>${escapeHtml(r.especie || r.outro_animal || '-')}</td>
      <td>${escapeHtml(r.raca || '-')}</td>
      <td>${escapeHtml(r.sexo || '-')}</td>
      <td>${escapeHtml(r.ambiente || '-')}</td>
      <td>${tagStatus(r.feridas, 'positiveBad')}</td>
      <td>${escapeHtml(r.regiao_ferida || '-')}</td>
      <td>${tagStatus(r.vacinado)}</td>
      <td>${tagStatus(r.castrado)}</td>
      <td>${tagStatus(r.atendimento_veterinario)}</td>
      <td>${fmtDate(r.data_atendimento) || '-'}</td>
      <td><span class="esporo-tag ${statusDoenteClass(r.evolucao_caso)}">${escapeHtml(r.evolucao_caso || 'NÃ£o informado')}</span></td>
      <td>${escapeHtml(r.morador || '-')}</td>
      <td class="esporo-address">${escapeHtml([r.logradouro, r.numero].filter(Boolean).join(', ') || '-')}</td>
      <td><button class="btn btn-ghost btn-sm" type="button" onclick="editarAnimal('${escapeHtml(r.id_animal)}')"><img src="/static/icons/editar.svg" alt="" class="icon-svg"></button></td>
    </tr>
  `).join('') : '<tr><td colspan="15" class="empty-inline">Nenhum animal encontrado.</td></tr>';
}
