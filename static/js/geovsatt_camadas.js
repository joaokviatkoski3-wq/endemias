(() => {
  'use strict';
  const form = document.getElementById('gc-config');
  if (!form) return;
  const fields = document.getElementById('gc-atributos');
  const editor = form.querySelector('.gc-color-editor');
  const classification = form.elements.namedItem('atributo_cor');
  const rules = form.elements.namedItem('regras_cor');
  const value = document.getElementById('gc-valor-cor');
  const color = document.getElementById('gc-paleta');
  let attributes;

  function refresh() {
    const values = [...(attributes.get(classification.value) || [])];
    values.sort((a, b) => a.localeCompare(b, 'pt-BR', {numeric: true}));
    value.replaceChildren(...values.slice(0, 600).map(text => new Option(text, text)));
    editor.hidden = !values.length;
    selectColor();
  }

  function selectColor() {
    const index = value.value + ' = ';
    const line = rules.value.split('\n').find(text => text.startsWith(index));
    const existing = line?.slice(index.length).trim();
    color.value = /^#[\da-f]{6}$/i.test(existing || '') ? existing : '#008c30';
  }

  value.addEventListener('change', selectColor);
  document.getElementById('gc-aplicar-cor').addEventListener('click', () => {
    if (!value.value) return;
    const prefix = value.value + ' = ';
    const lines = rules.value.split('\n').filter(text => text.trim() && !text.startsWith(prefix));
    lines.push(prefix + color.value);
    const updated = lines.join('\n');
    if (updated.length <= rules.maxLength) rules.value = updated;
    else rules.reportValidity();
  });

  const request = async () => {
    if (attributes) return;
    const response = await fetch(form.dataset.feicoes, {cache: 'no-store'});
    if (!response.ok) return;
    const data = await response.json();
    attributes = new Map();
    for (const feature of data.features || []) {
      for (const [key, value] of Object.entries(feature.properties || {})) {
        if (value == null || typeof value === 'object' || key.length > 120) continue;
        if (!attributes.has(key)) attributes.set(key, new Set());
        const values = attributes.get(key);
        const text = String(value).trim();
        if (values.size < 600 && text && !text.includes('\n')) values.add(text);
      }
    }
    fields.replaceChildren(...[...attributes.keys()].sort().map(field => new Option(field, field)));
    refresh();
  };
  classification.addEventListener('input', () => { if (attributes) refresh(); });
  request().catch(() => {});
})();
