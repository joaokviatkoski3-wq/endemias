(() => {
  'use strict';
  let map = null, loaded = false;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const colors = ['#2563eb','#dc2626','#16a34a','#9333ea','#ea580c','#0891b2','#be123c','#65a30d'];
  // A mudança de ciclo invalida o filtro de estrato do ciclo anterior.
  document.querySelectorAll('#liraa-tab-campo form, #liraa-tab-boletins form').forEach(form => {
    form.querySelector('select[name="ciclo"]')?.addEventListener('change', () => {
      const estrato = form.querySelector('select[name="estrato"]');
      if (estrato) estrato.value = '';
    });
  });
  window.LiraaPlanoCampo = {iniciar: async () => {
    const box = document.getElementById('liraa-campo-mapa'), status = document.getElementById('liraa-campo-status');
    if (!box || !window.L) return;
    if (!map) {
      map = L.map(box).setView([-25.33,-49.29], 12);
      const street = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {attribution:'Tiles © Esri', maxZoom:19});
      const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution:'Tiles © Esri', maxZoom:19});
      street.addTo(map);
      L.control.layers({'Mapa':street,'Satélite':satellite}).addTo(map);
    }
    map.invalidateSize();
    if (loaded) return;
    loaded = true;
    status.textContent = 'Carregando quarteirões sorteados…';
    try {
      const response = await fetch(box.dataset.url);
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || `HTTP ${response.status}`);
      const layer = L.geoJSON(data, {style: f => ({color:colors[(Number(f.properties.estrato)-1)%colors.length],weight:2,fillOpacity:.4}),
        onEachFeature:(f,l) => {
          const p = f.properties;
          l.bindTooltip(esc(p.quarteirao), {permanent:true,direction:'center',className:'liraa-map-label'});
          l.bindPopup(`<strong>Q. ${esc(p.quarteirao)} — ${esc(p.Localidade)}</strong><br>Estrato ${esc(p.estrato)}<br>Imóveis RG: ${esc(p.imoveis_rg ?? 'Sem RG')}<br>Referência ${Math.round(p.fracao*100)}%: ${esc(p.meta_rg ?? 'Não disponível')}`);
        }}).addTo(map);
      if (layer.getBounds().isValid()) map.fitBounds(layer.getBounds(), {padding:[18,18]});
      status.textContent = data.features.length ? 'Clique em um quarteirão para conferir seus dados.' : 'Nenhum quarteirão sorteado neste filtro.';
    } catch (error) {
      loaded = false;
      status.textContent = `Não foi possível carregar o plano: ${error.message}`;
    }
  }};
})();
