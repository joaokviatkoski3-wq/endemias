/**
 * emoji_icons.js
 * Substitui emojis por ícones SVG da pasta /static/icons/
 *
 * Como funciona:
 *   1. Para cada emoji mapeado abaixo, o script busca o arquivo SVG correspondente.
 *   2. O SVG é inserido inline no lugar do emoji, herdando a cor do texto via currentColor.
 *   3. Roda automaticamente ao carregar a página.
 *
 * Para substituir um ícone:
 *   - Coloque o arquivo SVG em: static/icons/<nome>.svg
 *   - O nome deve coincidir com o valor no mapa EMOJI_MAP abaixo.
 *   - O SVG precisa usar fill="currentColor" ou stroke="currentColor" para herdar a cor.
 */

const EMOJI_MAP = {
  // ── Interface geral ──────────────────────────────────
  '☀':  'sol',
  '🌙':  'lua',
  '☰':  'menu',
  '⚠':  'alerta',
  '⚡':  'raio',
  '✓':  'check',
  '✕':  'fechar',
  '✗':  'erro',
  '✏':  'editar',
  '💾':  'salvar',
  '🔑':  'chave',
  '🔒':  'cadeado',
  '🔍':  'busca',
  '🔴':  'circulo_vermelho',
  '🟡':  'circulo_amarelo',

  // ── Navegação / menu ────────────────────────────────
  '📊':  'grafico_barra',
  '📈':  'grafico_linha',
  '📋':  'prancheta',
  '📅':  'calendario',
  '📂':  'pasta',
  '📄':  'documento',
  '📝':  'nota',
  '📜':  'rolar',
  '📥':  'importar',
  '📍':  'marcador',

  // ── Pessoas ─────────────────────────────────────────
  '👤':  'usuario',
  '👥':  'usuarios',

  // ── Endemias / saúde ────────────────────────────────
  '🦟':  'mosquito',
  '🔬':  'microscopio',
  '🧪':  'tubo_ensaio',
  '💊':  'comprimido',

  // ── Imóveis / localidades ───────────────────────────
  '🏠':  'casa',
  '🏘':  'casas',
  '🚪':  'porta',
  '🗺':  'mapa',

  // ── Ações / status ──────────────────────────────────
  '🔄':  'atualizar',
  '🔔':  'sino',
  '🖨':  'imprimir',
  '🕓':  'relogio',

  // ── Depósitos ───────────────────────────────────────
  '🪣':  'balde',
  '🗑':  'lixeira',

  // ── Outros ─────────────────────────────────────────
  '🗂':  'fichario',
  '🗓':  'agenda',
};

// Tamanho padrão dos ícones (pode ajustar aqui)
const ICON_SIZE = '1.1em';

// Cache para não buscar o mesmo SVG várias vezes
const _svgCache = {};

async function _fetchSVG(name) {
  if (_svgCache[name] !== undefined) return _svgCache[name];
  try {
    const res = await fetch(`/static/icons/${name}.svg`);
    if (!res.ok) { _svgCache[name] = null; return null; }
    const text = await res.text();
    _svgCache[name] = text;
    return text;
  } catch {
    _svgCache[name] = null;
    return null;
  }
}

function _wrapSVG(svgText, emoji) {
  // Garante que o SVG use currentColor e tenha tamanho controlado
  let svg = svgText.trim();
  svg = svg.replace(/<svg/, `<svg aria-label="${emoji}" role="img" style="display:inline-block;vertical-align:-0.15em;width:${ICON_SIZE};height:${ICON_SIZE};flex-shrink:0;"`);
  // Se não tiver fill/stroke explícito, adiciona currentColor
  if (!svg.includes('fill=') && !svg.includes('stroke=')) {
    svg = svg.replace('<svg', '<svg fill="currentColor"');
  }
  return svg;
}

async function substituirEmojis() {
  // Busca todos os nós de texto que contenham emojis mapeados
  const emojiChars = Object.keys(EMOJI_MAP);
  const emojiPattern = new RegExp(emojiChars.map(e => e.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');

  // Percorre todos os nós de texto da página
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      // Ignora scripts e estilos
      const tag = node.parentElement?.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE') return NodeFilter.FILTER_REJECT;
      // Só processa se tiver algum emoji mapeado
      if (emojiPattern.test(node.textContent)) {
        emojiPattern.lastIndex = 0;
        return NodeFilter.FILTER_ACCEPT;
      }
      emojiPattern.lastIndex = 0;
      return NodeFilter.FILTER_SKIP;
    }
  });

  const nodes = [];
  let n;
  while ((n = walker.nextNode())) nodes.push(n);

  for (const node of nodes) {
    const text = node.textContent;
    if (!emojiPattern.test(text)) { emojiPattern.lastIndex = 0; continue; }
    emojiPattern.lastIndex = 0;

    // Divide o texto em partes (texto comum e emojis)
    const parts = [];
    let last = 0;
    let m;
    while ((m = emojiPattern.exec(text)) !== null) {
      if (m.index > last) parts.push({ type: 'text', value: text.slice(last, m.index) });
      parts.push({ type: 'emoji', value: m[0], name: EMOJI_MAP[m[0]] });
      last = m.index + m[0].length;
    }
    emojiPattern.lastIndex = 0;
    if (last < text.length) parts.push({ type: 'text', value: text.slice(last) });

    // Monta o fragmento substituindo emojis
    const frag = document.createDocumentFragment();
    for (const part of parts) {
      if (part.type === 'text') {
        frag.appendChild(document.createTextNode(part.value));
      } else {
        const svgText = await _fetchSVG(part.name);
        if (svgText) {
          const span = document.createElement('span');
          span.innerHTML = _wrapSVG(svgText, part.value);
          frag.appendChild(span);
        } else {
          // SVG não encontrado → mantém o emoji original
          frag.appendChild(document.createTextNode(part.value));
        }
      }
    }
    node.parentElement.replaceChild(frag, node);
  }
}

// Executa após o DOM carregar
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', substituirEmojis);
} else {
  substituirEmojis();
}

// Observa mudanças dinâmicas (conteúdo carregado via JS, ex: dashboards)
const _observer = new MutationObserver(() => substituirEmojis());
document.addEventListener('DOMContentLoaded', () => {
  _observer.observe(document.body, { childList: true, subtree: true });
});
