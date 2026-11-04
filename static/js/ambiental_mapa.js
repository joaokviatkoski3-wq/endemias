/* A base territorial e comum; contagens operacionais sao exclusivamente ambientais. */
(() => {
  const status = document.getElementById('mapa-status');
  const form = document.getElementById('filtros-mapa');
  const map = L.map('mapa-ambiental').setView([-25.32, -49.31], 12);
  let geometry, layer, rows = [];
  const key = (loc, q) => `${String(loc)}:${String(q || '').replace(/^0+(?=\d)/, '')}`;
  function draw() {
    if (!geometry) return;
    const source = document.getElementById('fonte').value;
    const totals = new Map();
    let total = 0, located = 0;
    for (const row of rows) {
      if (source !== 'todas' && source !== row.fonte) continue;
      total += row.registros;
      if (!row.id_localidade || !row.quarteirao) continue;
      const id = key(row.id_localidade, row.quarteirao);
      totals.set(id, (totals.get(id) || 0) + row.registros);
    }
    if (layer) map.removeLayer(layer);
    layer = L.geoJSON(geometry, {
      style: f => ({color:'#57847d',weight:1,fillColor:totals.has(key(f.properties.Localidade,f.properties.id_quart))?'#16786b':'#e3ecea',fillOpacity:.8}),
      onEachFeature(f, polygon) {
        const p = f.properties, count = totals.get(key(p.Localidade,p.id_quart)) || 0;
        located += count;
        const text = document.createElement('p');
        text.textContent = `${p.Localidade_nome || 'Localidade ' + p.Localidade} · Q ${p.id_quart}: ${count} registro(s) ambientais`;
        polygon.bindPopup(text);
      }
    }).addTo(map);
    if (layer.getBounds().isValid()) map.fitBounds(layer.getBounds(), {padding:[15,15]});
    status.textContent = `${total} registro(s) no período. ${Math.max(0,total-located)} sem correspondência na camada territorial. Quarteirões sem registros aparecem em cinza.`;
  }
  async function load() {
    status.textContent = 'Consultando registros ambientais…';
    try {
      const response = await fetch('/api/mapa?' + new URLSearchParams(new FormData(form)));
      if (!response.ok) throw new Error();
      rows = (await response.json()).linhas;
      draw();
    } catch { status.textContent = 'Não foi possível consultar os dados. Confira a conexão e o período.'; }
  }
  form.addEventListener('submit', e => {e.preventDefault();load();});
  document.getElementById('fonte').addEventListener('change', draw);
  fetch('/api/ambiental/territorio').then(r => {if (!r.ok) throw new Error();return r.json();})
    .then(data => {geometry = data;load();})
    .catch(() => {status.textContent = 'Não foi possível carregar a base territorial.';});
})();
