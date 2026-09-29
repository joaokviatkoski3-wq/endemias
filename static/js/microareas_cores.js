/* Cores do mapa de microáreas, sem dependência de Leaflet ou do banco. */
((root) => {
  'use strict';
  const CORES = [
    '#2563eb', '#dc2626', '#16a34a', '#7c3aed', '#ea580c',
    '#0891b2', '#db2777', '#a16207', '#0f766e', '#4d7c0f',
    '#1e40af', '#be123c',
    '#0ea5e9', '#b91c1c', '#15803d', '#9333ea', '#c2410c',
    '#0d9488', '#be185d', '#ca8a04', '#4338ca', '#65a30d',
    '#0369a1', '#a21caf', '#047857', '#e11d48', '#d97706',
    '#6d28d9', '#166534', '#0e7490', '#9f1239', '#854d0e',
    '#4f46e5', '#c026d3', '#b45309', '#059669', '#1d4ed8',
  ];
  const LIMITE_METROS = 200;
  const CONTRASTE_VIZINHO = 40;
  const codigo = valor => {
    const raw = String(valor ?? '').trim();
    return /^\d+(?:\.0+)?$/.test(raw) ? String(parseInt(raw, 10)).padStart(4, '0') : raw;
  };
  function caixa(geometry) {
    const box = {minX:Infinity, minY:Infinity, maxX:-Infinity, maxY:-Infinity};
    function visitar(item) {
      if (!Array.isArray(item)) return;
      if (item.length >= 2 && Number.isFinite(item[0]) && Number.isFinite(item[1])) {
        box.minX = Math.min(box.minX, item[0]); box.maxX = Math.max(box.maxX, item[0]);
        box.minY = Math.min(box.minY, item[1]); box.maxY = Math.max(box.maxY, item[1]);
      } else item.forEach(visitar);
    }
    visitar(geometry?.coordinates);
    return Number.isFinite(box.minX) ? box : null;
  }
  function distancia(a, b) {
    const dx = Math.max(0, a.minX - b.maxX, b.minX - a.maxX);
    const dy = Math.max(0, a.minY - b.maxY, b.minY - a.maxY);
    const latitude = (a.minY + a.maxY + b.minY + b.maxY) / 4;
    return Math.hypot(dx * 111320 * Math.cos(latitude * Math.PI / 180), dy * 111320);
  }
  function vizinhanca(registros, features, limiteMetros=LIMITE_METROS) {
    const donos = new Map(), caixas = new Map(), vizinhos = new Map();
    for (const r of registros) {
      const id = String(r.id_microarea);
      caixas.set(id, []); vizinhos.set(id, new Set());
      for (const q of r.quarteiroes || []) donos.set(`${r.id_localidade}:${codigo(q)}`, id);
    }
    for (const feature of features || []) {
      const id = donos.get(`${feature.properties?.Localidade}:${codigo(feature.properties?.id_quart)}`);
      const box = caixa(feature.geometry);
      if (id && box) caixas.get(id).push(box);
    }
    const ids = [...caixas.keys()];
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = caixas.get(ids[i]), b = caixas.get(ids[j]);
        if (a.some(x => b.some(y => distancia(x, y) <= limiteMetros))) {
          vizinhos.get(ids[i]).add(ids[j]); vizinhos.get(ids[j]).add(ids[i]);
        }
      }
    }
    return vizinhos;
  }
  function lab(hex) {
    const canais = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    const [r, g, b] = canais;
    const xyz = [
      (r * .4124 + g * .3576 + b * .1805) / .95047,
      (r * .2126 + g * .7152 + b * .0722),
      (r * .0193 + g * .1192 + b * .9505) / 1.08883,
    ].map(v => v > .008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116);
    return [116 * xyz[1] - 16, 500 * (xyz[0] - xyz[1]), 200 * (xyz[1] - xyz[2])];
  }
  const LAB = new Map(CORES.map(cor => [cor, lab(cor)]));
  function diferenca(a, b) {
    const x = LAB.get(a) || lab(a), y = LAB.get(b) || lab(b);
    return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
  }
  function paleta(seed) {
    let estado = (Number(seed) >>> 0) || 1;
    const proximo = () => {
      estado = (estado + 0x6D2B79F5) >>> 0;
      let t = Math.imul(estado ^ (estado >>> 15), 1 | estado);
      t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const cores = [...CORES];
    for (let i = cores.length - 1; i > 0; i--) {
      const j = Math.floor(proximo() * (i + 1));
      [cores[i], cores[j]] = [cores[j], cores[i]];
    }
    return cores;
  }
  function atribuir(registros, features, seed=1, vizinhos=vizinhanca(registros, features)) {
    const opcoes = paleta(seed), resultado = {}, usos = new Map(CORES.map(c => [c, 0]));
    const ordem = [...vizinhos.keys()].sort((a, b) =>
      vizinhos.get(b).size - vizinhos.get(a).size || Number(a) - Number(b));
    const melhorQue = (novo, atual) => {
      if (!atual) return true;
      for (let i = 0; i < novo.length; i++) {
        if (novo[i] !== atual[i]) return novo[i] > atual[i];
      }
      return false;
    };
    for (const id of ordem) {
      let melhor = null, melhorScore = null;
      const jaColoridos = [...vizinhos.get(id)].map(outro => resultado[outro]).filter(Boolean);
      for (let i = 0; i < opcoes.length; i++) {
        const cor = opcoes[i];
        const distancias = jaColoridos.map(vizinha => diferenca(cor, vizinha));
        const minimo = distancias.length ? Math.min(...distancias) : Infinity;
        const contrastante = minimo >= CONTRASTE_VIZINHO;
        // Entre cores suficientemente distintas das vizinhas, priorizar as
        // menos usadas; a ordem embaralhada desempata e cria novas combinações.
        // Sem cor contrastante disponível, maximizar a distância possível.
        const score = [contrastante ? 1 : 0,
          contrastante ? -usos.get(cor) : minimo,
          contrastante ? -i : -usos.get(cor), -i];
        if (melhorQue(score, melhorScore)) {
          melhor = cor; melhorScore = score;
        }
      }
      resultado[id] = melhor;
      usos.set(melhor, usos.get(melhor) + 1);
    }
    return resultado;
  }
  const api = {atribuir, vizinhanca, diferenca, CORES};
  root.MicroareasCores = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window === 'undefined' ? globalThis : window);
