import { escapeHTML as esc, readableText } from './text-format.js?v=f518fc12dba0';
import { venueName } from './paper-data.js?v=f518fc12dba0';
import { renderMath } from './math.js?v=f518fc12dba0';

export function createEvolutionHome({ container, onPaper, onSearch, onBrowse }) {
  let saved = null,
    loadedAt = 0,
    pending = null;
  async function load() {
    if (saved && Date.now() - loadedAt < 60000) return saved;
    if (!pending)
      pending = fetch('evolve/generated/evolution-starters.json', { cache: 'no-cache' })
        .then(response => {
          if (!response.ok) throw new Error('Starting papers unavailable');
          return response.json();
        })
        .then(data => {
          saved = data;
          loadedAt = Date.now();
          return data;
        })
        .finally(() => {
          pending = null;
        });
    return pending;
  }
  function actions() {
    container.querySelector('[data-find-paper]').onclick = onSearch;
    container.querySelector('[data-browse-research]').onclick = onBrowse;
  }
  function shell() {
    container.innerHTML =
      '<div class="evolution-intro"><div class="intro-text"><h2>Start with a paper. Follow the idea.</h2><p>Explore what it builds on, what changes, and the evidence connecting each contribution.</p><div class="evolution-start-actions"><button class="primary-action" data-find-paper>Find a paper</button><button data-browse-research>Browse research areas →</button></div></div><img class="intro-figure" src="assets/hero.svg" alt="" aria-hidden="true"></div><div class="starter-heading"><h3>Explore a connected paper</h3><span>From the research collection</span></div><div class="evolution-starters" aria-live="polite"><p class="starter-loading"><span class="pe-loader" aria-hidden="true"><i></i><i></i><i></i></span>Loading starting papers…</p></div><p class="evolution-start-note">Connections are model-supported predictions. Select a connection to inspect its source passages. <a href="contribute.html">Help review connections →</a></p>';
    actions();
  }
  return {
    async show() {
      shell();
      try {
        const data = await load(),
          target = container.querySelector('.evolution-starters');
        if (!target) return data;
        target.innerHTML = data.starters.length
          ? data.starters
              .map(
                (p, i) =>
                  `<button class="evolution-starter" data-starter="${i}" style="--i:${i}"><span class="starter-meta">${esc(venueName(p.v))} · ${p.y}</span><h4>${esc(readableText(p.t))}</h4><p>${esc(p.topic)}</p><span class="starter-open">${p.connections} source-supported ${p.connections === 1 ? 'connection' : 'connections'} <span aria-hidden="true">→</span></span></button>`,
              )
              .join('')
          : '<p class="starter-loading">Find a paper to explore its available relationships and similar work.</p>';
        target
          .querySelectorAll('[data-starter]')
          .forEach(button => (button.onclick = () => onPaper(data.starters[+button.dataset.starter])));
        renderMath(target);
        return data;
      } catch {
        const target = container.querySelector('.evolution-starters');
        if (target) {
          target.innerHTML =
            '<div class="starter-loading">Starting papers could not be loaded. You can still search the collection. <button data-retry-starters>Try again</button></div>';
          target.querySelector('button').onclick = () => this.show();
        }
        return null;
      }
    },
  };
}
