import { createLatestTask } from './ui-task.js?v=39205891c9e4';
import { readableText } from './text-format.js?v=39205891c9e4';
import { renderMath } from './math.js?v=39205891c9e4';
import { createViewport } from './viewport.js?v=39205891c9e4';
import { routeConnections, wireMovableCards } from './graph-layout.js?v=39205891c9e4';
import { createEvolutionHome } from './evolution-home.js?v=39205891c9e4';
import { evolutionHash, parseRoute, paperURL } from './evolution-route.js?v=39205891c9e4';
import { buildNeighbourhood } from './neighbourhood.js?v=39205891c9e4';
import { createDiscoverySearch } from './discovery-search.js?v=39205891c9e4';
import { createPaperReader } from './paper-reader.js?v=39205891c9e4';
import { CARD, STAGE } from './graph-layout.js?v=39205891c9e4';
import { createWorkspace } from './workspace.js?v=39205891c9e4';
const workspace = createWorkspace();
function engage() {
  document.body.classList.add('engaged');
  sessionStorage.setItem('paper-evolve-engaged', '1');
}
if (sessionStorage.getItem('paper-evolve-engaged')) document.body.classList.add('engaged');
document.addEventListener(
  'pointerdown',
  e => {
    if (e.target.closest('button,input,select,#graph')) engage();
  },
  true,
);
document.addEventListener('input', engage, true);
document.addEventListener('change', engage, true);
function emptyDataset() {
  return {
    papers: [],
    contributions: [],
    edges: [],
    similarities: [],
    computed: true,
    topic: 'Explore research evolution',
    width: STAGE.width,
    height: STAGE.height,
  };
}
const $ = id => document.getElementById(id);
let canvasViewport = null,
  unmappedContext = null,
  evolutionLanding = true,
  activeEvolutionRecord = null,
  homeRequested = false,
  homeSummary = null;
const evolutionTask = createLatestTask();
let data = emptyDataset(),
  selected = null,
  edgeSelected = null,
  mode = 'all',
  collapsed = new Set(),
  pathStart = null,
  similarity = false;
const esc = s =>
  String(s ?? '').replace(
    /[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const reader = createPaperReader({
  container: $('detail-content'),
  onEvolution: context => openEvolution(context),
  onSelectPaper: p => selectGraphPaper(p.id),
  onConnection: id => {
    edgeSelected = id;
    details();
    workspace.openNotes();
  },
});
const evolutionHome = createEvolutionHome({
  container: $('evolution-start'),
  onPaper: record => openEvolution(record),
  onSearch() {
    workspace.openExplorer();
    $('search').focus();
  },
  onBrowse() {
    switchView('map');
  },
});
function selectGraphPaper(id) {
  evolutionTask.cancel();
  if (mode === 'path' && !pathStart) pathStart = id;
  selected = id;
  edgeSelected = null;
  render();
  details();
  workspace.openNotes();
  requestAnimationFrame(() =>
    document
      .querySelector(`[data-paper="${CSS.escape(id)}"]`)
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' }),
  );
}
const paper = id => data.papers.find(p => p.id === id);
const owner = cid => data.contributions.find(c => c.id === cid)?.paper_id;
const contribution = id => data.contributions.filter(c => c.paper_id === id);
const colors = {
  Extends: '#568273',
  Challenges: '#be8057',
  Combines: '#9183a4',
  Transfers: '#7291a3',
  Revives: '#a9a05e',
  Similar: '#a3a99a',
};
function reachable(id, reverse = false) {
  const set = new Set([id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const e of data.edges) {
      const a = owner(reverse ? e.target : e.source),
        b = owner(reverse ? e.source : e.target);
      if (set.has(a) && !set.has(b)) {
        set.add(b);
        changed = true;
      }
    }
  }
  return set;
}
function filtered() {
  let nodes = data.papers.filter(
    p =>
      p.year >= +$('from').value &&
      p.year <= +$('to').value &&
      ($('venue').value === 'All sources' || p.venue === $('venue').value),
  );
  for (const c of collapsed) {
    const descendants = reachable(c);
    nodes = nodes.filter(p => p.id === c || !descendants.has(p.id));
  }
  const ids = new Set(nodes.map(p => p.id));
  return {
    nodes,
    edges: data.edges.filter(
      e =>
        ids.has(owner(e.source)) &&
        ids.has(owner(e.target)) &&
        ($('relation').value === 'All relationships' ||
          e.type === $('relation').value ||
          Object.hasOwn(e.types || {}, $('relation').value)) &&
        ($('evidence').value === 'All evidence' || e.status === $('evidence').value),
    ),
  };
}
function highlighted() {
  if (mode === 'ancestors') return reachable(selected, true);
  if (mode === 'descendants') return reachable(selected);
  if (mode === 'path' && pathStart) {
    const down = reachable(pathStart),
      up = reachable(selected, true);
    return new Set([...down].filter(x => up.has(x)));
  }
  return null;
}
const positions = new Map();
let layoutKey = null;
function pos(p) {
  return positions.get(p.id) || { x: 24 + p.col * 320, y: 86 + p.lane * 278 };
}
const saveLayout = () => {
  try {
    localStorage.setItem(layoutKey, JSON.stringify([...positions]));
  } catch {}
};

function render() {
  $('evolution-start').hidden = !evolutionLanding;
  document.querySelector('.canvas-shell').hidden = evolutionLanding;
  $('change-paper').hidden = evolutionLanding;
  if (evolutionLanding) {
    $('evolution-title').textContent = 'Explore research evolution';
    $('counts').textContent = homeSummary
      ? `${homeSummary.papers.toLocaleString()} papers · ${homeSummary.edges.toLocaleString()} research connections`
      : 'Find a paper or choose a starting point below';
    for (const selector of ['.toolbar', '.evolution-filters', '.workspace-footer', '.collection'])
      document.querySelector(selector).hidden = true;
    $('graph').innerHTML = '';
    $('graph-status').hidden = true;
    if (!homeRequested) {
      homeRequested = true;
      evolutionHome.show().then(summary => {
        if (summary) {
          homeSummary = summary;
          if (evolutionLanding)
            $('counts').textContent =
              `${summary.papers.toLocaleString()} papers · ${summary.edges.toLocaleString()} research connections`;
        }
      });
    }
    return;
  }
  const changedFilters = ['venue', 'relation', 'evidence', 'from', 'to'].filter(id => $(id).selectedIndex > 0).length;
  $('filter-count').textContent = changedFilters || '';
  const width = data?.width || STAGE.width,
    height = data?.height || STAGE.height;
  $('graph').style.width = width + 'px';
  $('graph').style.minWidth = width + 'px';
  $('graph').style.height = height + 'px';
  canvasViewport?.setSize(width, height);
  const badge = document.querySelector('.collection');
  if (badge)
    badge.textContent = data?.computed
      ? data.hasCommunity
        ? 'Community + model connections'
        : 'Model predictions'
      : 'Research connections';
  const note = document.querySelector('.note');
  if (note)
    note.textContent = data?.computed
      ? 'The default view shows connections backed by source passages; each one keeps its evidence and who reviewed it. Switch to All connections to include earlier abstract-based results. Similar papers are a discovery layer, and a good place to find the next connection.'
      : 'Connections show how one paper builds on another. Similar papers are a separate discovery layer.';
  $('evolution-title').textContent = readableText(
    unmappedContext ? unmappedContext.t || unmappedContext.topic : data.topic || 'Research evolution',
  );
  renderMath($('evolution-title'));
  const unavailable = Boolean(unmappedContext);
  $('graph-scroll').hidden = unavailable;
  $('graph-notice').hidden = !unavailable;
  document.querySelector('.evolution-filters').hidden = unavailable;
  document.querySelector('.canvas-controls').hidden = unavailable;
  document.querySelector('.canvas-help').hidden = unavailable;
  document.querySelector('.toolbar').hidden = unavailable;
  document.querySelector('.workspace-footer').hidden = unavailable;
  if (badge) badge.hidden = unavailable;
  if (unavailable) {
    if (unmappedContext.loading) {
      $('graph-status').hidden = true;
      $('counts').textContent = 'Loading paper connections…';
      $('graph-notice').innerHTML =
        '<div class="evolution-notice-card"><h2>Loading this paper’s connections…</h2><p>Preparing its timeline and supporting evidence.</p></div>';
      return;
    }
    const failed = unmappedContext.loadFailed;
    $('graph-status').hidden = true;
    $('graph').innerHTML = '';
    $('counts').textContent = failed ? 'Evolution could not be loaded' : 'Waiting for its first connection';
    $('graph-notice').innerHTML =
      `<div class="evolution-notice-card"><span class="badge">${failed ? 'Could not load' : 'Not mapped yet'}</span><h2>${failed ? 'The timeline could not be loaded' : 'Be the first to connect this paper'}</h2><p>${failed ? 'Your paper and abstract are still available. Retry loading its timeline.' : 'Its timeline is still open. Read the abstract, or show which earlier work it builds on.'}</p><div class="notice-actions">${failed ? '<button id="retry-evolution">Retry timeline</button>' : /^https:\/\//.test(unmappedContext.u || unmappedContext.source_url || '') ? `<a class="notice-propose" href="contribute.html?${new URLSearchParams({ pair: unmappedContext.u || unmappedContext.source_url })}">Propose a connection →</a>` : ''}<button id="notice-read-paper">Read abstract</button><button id="notice-browse">Back to papers</button></div></div>`;
    $('retry-evolution')?.addEventListener('click', async event => {
      const button = event.currentTarget,
        context = unmappedContext;
      button.disabled = true;
      button.textContent = 'Loading…';
      try {
        await openEvolution(context);
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.textContent = 'Retry timeline';
        }
      }
    });
    $('notice-read-paper').onclick = () => {
      reader.showPaper(unmappedContext);
      workspace.openNotes();
    };
    $('notice-browse').onclick = () => document.querySelector('[data-view="browse"]').click();
    return;
  }
  const { nodes, edges } = filtered();
  if (nodes.length && !nodes.some(p => p.id === selected)) {
    selected = nodes[0].id;
    edgeSelected = null;
  }
  const hi = highlighted();
  const status = $('graph-status');
  status.hidden = mode !== 'path';
  if (mode === 'path')
    status.textContent =
      pathStart === selected
        ? 'Choose a later paper to trace a path from ' + paper(pathStart).name + '.'
        : hi?.has(pathStart) && hi?.has(selected)
          ? 'Tracing ' + paper(pathStart).name + ' → ' + paper(selected).name
          : 'These two papers aren’t linked by a path yet. Pick another later paper, or propose the connection.';
  $('counts').textContent =
    `${nodes.length} ${nodes.length === 1 ? 'paper' : 'papers'} · ${edges.length} research ${edges.length === 1 ? 'connection' : 'connections'}${similarity ? ' + similarity links' : ''} · ${
      nodes.length
        ? [...new Set(nodes.map(p => p.year))]
            .sort((a, b) => a - b)
            .filter((y, i, a) => i === 0 || i === a.length - 1)
            .join('–')
        : data.span || ''
    }${data.classificationPending ? ' · Relationships pending; similarity available' : data.computed && !edges.length ? ($('evidence').value === 'source_supported' ? ' · Passage-supported connections are still open here' : ' · ' + data.classificationChecked + ' comparisons checked so far; connections still open') : ''}`;
  const visible = new Set(nodes.map(p => p.id));
  let html = (
    data.columns || [
      ['2023', 24],
      ['2024 · early', 344],
      ['2024 · later', 664],
      ['2025', 984],
    ]
  )
    .map(([year, x]) => `<div class="year" style="left:${x}px">${year}</div>`)
    .join('');
  let lines = edges.map(e => ({ ...e, a: owner(e.source), b: owner(e.target) }));
  if (similarity) {
    lines.push(
      ...data.similarities
        .filter(
          e =>
            visible.has(e.a) &&
            visible.has(e.b) &&
            !edges.some(r => owner(r.source) === e.a && owner(r.target) === e.b),
        )
        .map(e => ({ ...e, type: 'Similar', status: 'inferred' })),
    );
  }
  const chip = e => (e.types ? Object.keys(e.types).join(' · ') : e.type),
    routed = routeConnections(
      lines.map(e => ({ a: pos(paper(e.a)), b: pos(paper(e.b)), text: chip(e) })),
      nodes.map(pos),
      { width, height },
    ),
    routes = lines.map((e, i) => ({ ...e, ...routed[i] }));
  html +=
    `<svg class="edges" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"><defs>` +
    Object.entries(colors)
      .map(
        ([k, v]) =>
          `<marker id="arrow${k}" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" viewBox="0 0 10 10" refX="9" refY="5" orient="auto"><path d="M2,1 L8,5 L2,9" fill="none" stroke="${v}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker>`,
      )
      .join('') +
    '</defs>' +
    routes
      .map(
        e =>
          `<g class="connection-line ${e.a === selected || e.b === selected ? 'nearby' : 'distant'}" data-line="${e.id}" opacity="${hi && (!hi.has(e.a) || !hi.has(e.b)) ? 0.12 : 1}"><path class="edge-halo" d="${e.d}"/><path class="edge-path" d="${e.d}" stroke="${colors[e.type]}" ${e.status === 'explicit' || e.status === 'source_supported' ? '' : 'stroke-dasharray="7 5"'} ${e.type !== 'Similar' ? `marker-end="url(#arrow${e.type})"` : ''}/><path class="edge-hit" d="${e.d}" data-edge="${e.id}"/></g>`,
      )
      .join('') +
    '</svg>';
  html += routes
    .map(
      e =>
        `<button class="edge-chip ${e.a === selected || e.b === selected ? 'nearby' : 'distant'}" style="left:${e.label.x}px;top:${e.label.y}px;--edge-color:${colors[e.type]}" data-edge="${e.id}" aria-label="Inspect ${e.type}: ${esc(paper(e.a).title)} to ${esc(paper(e.b).title)}">${esc(chip(e))}</button>`,
    )
    .join('');
  html += nodes
    .map(p => {
      const { x, y } = pos(p);
      return `<button class="paper ${selected === p.id ? 'selected' : ''} ${hi && !hi.has(p.id) ? 'dim' : ''}" style="left:${x}px;top:${y}px" data-paper="${p.id}" aria-label="${esc(readableText(p.title))}. Select to read abstract; drag to move." title="${esc(readableText(p.title))} · Select to read · Drag to move"><span class="drag-grip" aria-hidden="true">⠿</span><small>${p.year} · ${esc(p.venue || p.authors)}</small><strong>${esc(readableText(p.title))}</strong><p>${esc(contribution(p.id)[0].label)}</p><span class="branch"><span>${esc(p.branch)}</span><span>Read →</span></span></button>`;
    })
    .join('');
  if (nodes.length && !edges.length && $('relation').value !== 'All relationships')
    html += `<div class="relationship-empty">No reviewed ${esc($('relation').value.toLowerCase())} connections in this slice yet. Similarity links are a separate discovery layer.</div>`;
  if (!nodes.length)
    html = '<div class="empty">No papers match these filters.<br><button data-reset>Reset filters</button></div>';
  $('graph').innerHTML = html;
  document.querySelectorAll('#graph .paper strong').forEach(renderMath);
  document.querySelectorAll('[data-paper]').forEach(b => {
    b.onpointerenter = () => spotlight(b.dataset.paper);
    b.onpointerleave = () => spotlight(selected);
    b.onclick = () => {
      selectGraphPaper(b.dataset.paper);
    };
  });
  document.querySelectorAll('[data-edge]').forEach(b => {
    const open = () => {
      edgeSelected = b.dataset.edge;
      details();
      workspace.openNotes();
    };
    b.onclick = open;
    b.onkeydown = e => {
      if (e.key === 'Enter' || e.key === ' ') open();
    };
  });
  document.querySelector('[data-reset]')?.addEventListener('click', reset);
  spotlight(selected);
}
function details() {
  if (!data || evolutionLanding) return;
  if (unmappedContext) {
    reader.showPaper(unmappedContext);
    return;
  }
  const e = data.edges.find(edge => edge.id === edgeSelected),
    sim = data.similarities.find(edge => edge.id === edgeSelected);
  if (sim) {
    reader.showSimilarity(sim, paper(sim.a), paper(sim.b));
    return;
  }
  if (e) {
    reader.showRelation(e, paper(owner(e.source)), paper(owner(e.target)));
    return;
  }
  const p = paper(selected);
  if (!p) return;
  reader.showPaper(p, {
    contributions: p.computed ? [] : contribution(p.id).map(c => c.label),
    connections: filtered()
      .edges.filter(edge => owner(edge.source) === p.id || owner(edge.target) === p.id)
      .map(edge => ({
        ...edge,
        sourceTitle: paper(owner(edge.source)).title,
        targetTitle: paper(owner(edge.target)).title,
      })),
    branchAction: data.edges.some(edge => owner(edge.source) === p.id)
      ? {
          label: collapsed.has(p.id) ? 'Show later developments' : 'Hide later developments',
          run() {
            collapsed.has(p.id) ? collapsed.delete(p.id) : collapsed.add(p.id);
            render();
            details();
          },
        }
      : null,
  });
}
function reset() {
  unmappedContext = null;
  for (const id of ['venue', 'relation', 'evidence', 'from', 'to']) $(id).selectedIndex = 0;
  $('search').value = '';
  $('search').dispatchEvent(new Event('input'));
  collapsed.clear();
  pathStart = null;
  mode = 'all';
  document.querySelectorAll('[data-highlight]').forEach(b => {
    b.classList.toggle('active', b.dataset.highlight === 'all');
    b.setAttribute('aria-pressed', String(b.dataset.highlight === 'all'));
  });
  render();
}
for (const id of ['venue', 'relation', 'evidence', 'from', 'to'])
  $(id).onchange = () => {
    if (+$('from').value > +$('to').value) $(id === 'from' ? 'to' : 'from').value = $(id).value;
    render();
  };
$('reset').onclick = reset;
document.querySelectorAll('[data-highlight]').forEach(
  b =>
    (b.onclick = () => {
      mode = b.dataset.highlight;
      pathStart = mode === 'path' ? selected : null;
      document.querySelectorAll('[data-highlight]').forEach(c => {
        c.classList.toggle('active', c === b);
        c.setAttribute('aria-pressed', String(c === b));
      });
      render();
      if (mode === 'path') {
        reader.cancel();
        $('details-title').textContent = 'Trace a path';
        workspace.openNotes();
        $('detail-content').innerHTML =
          '<h2>Trace a path</h2><p>Starting at ' +
          esc(paper(selected).name) +
          '. Select a later paper to highlight the paths between them. If none exist, all papers fade.</p>';
      }
    }),
);
function switchView(v, { writeHistory = true, cancelTask = true } = {}) {
  if (v === 'evolution' && cancelTask && activeEvolutionRecord && unmappedContext?.loading)
    return openEvolution(activeEvolutionRecord);
  if (cancelTask) evolutionTask.cancel();
  reader.cancel();
  workspace.closeNotes();
  workspace.closeMobileExplorer();
  document.body.classList.toggle('discovery', v !== 'evolution');
  if (v !== 'evolution') {
    $('details-title').textContent = 'Paper details';
    $('detail-content').innerHTML =
      '<h2>Explore the collection</h2><p>Choose a research area, or select a paper to read its details.</p>';
  }
  document.querySelectorAll('[data-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.view === v);
    if (button.dataset.view === v) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('evolution').hidden = v !== 'evolution';
  $('library').hidden = v === 'evolution';
  const hash = v === 'evolution' ? evolutionHash(activeEvolutionRecord) : '#' + (v === 'map' ? 'landscape' : v);
  if (writeHistory && location.hash !== hash) history.pushState(null, '', hash);
  if (v !== 'evolution') openLibrary(v);
  else {
    render();
    details();
    if (!evolutionLanding && !unmappedContext) requestAnimationFrame(() => canvasViewport?.frame());
  }
}
document.querySelectorAll('[data-view]').forEach(button => (button.onclick = () => switchView(button.dataset.view)));
import { createLibrary } from './library.js?v=39205891c9e4';
const openLibrary = createLibrary({
  openEvolution,
  selectPaper(record) {
    evolutionTask.cancel();
    reader.showPaper(record);
    workspace.openNotes();
  },
});

const toggle = document.createElement('button');
toggle.id = 'similarity';
toggle.textContent = 'Similar papers';
toggle.setAttribute('aria-pressed', 'false');
toggle.title = 'Show semantic similarity links alongside evolution relationships';
toggle.onclick = () => {
  similarity = !similarity;
  toggle.setAttribute('aria-pressed', String(similarity));
  render();
};
document.querySelector('.toolbar').append(toggle);
setData(data);
render();

const relationshipGuide = {
  Similar: [
    'Related ideas',
    'Papers with closely related ideas, found by semantic similarity. A good place to look for a connection worth adding.',
  ],
  Extends: ['Adds to an existing idea', 'Retains a contribution and adds capabilities or scope.'],
  Challenges: [
    'Questions an earlier idea',
    'Identifies a failure, limitation, or assumption in an earlier contribution.',
  ],
  Combines: ['Brings branches together', 'Joins contributions from separate lines of work.'],
  Transfers: ['Takes an idea somewhere new', 'Applies a contribution in a different task, domain, or setting.'],
  Revives: [
    'An old idea, seen in a new light',
    'Reintroduces an older approach under new conditions: stronger models, better hardware, new data, or a different problem. The later contribution shows what was retained, what changed, and why it became useful again.',
  ],
};
document.querySelectorAll('[data-guide]').forEach(
  b =>
    (b.onclick = () => {
      const type = b.dataset.guide;
      const [title, body] = relationshipGuide[type];
      reader.cancel();
      $('details-title').textContent = 'Relationship guide';
      workspace.openNotes();
      $('detail-content').innerHTML =
        `<span class="badge">Relationship guide · ${type}</span><h2>${title}</h2><p>${body}</p><h3>Evidence to look for</h3><p>Source passages that identify the earlier contribution, the new conditions, and the change.</p>${type === 'Revives' ? '<h3>Forward through time</h3><p>Older contribution → later revival. The edge points to the new contribution, with the original idea preserved as its root.</p>' : ''}<button id="show-relation">Show ${type.toLowerCase()} connections</button>`;
      $('show-relation').onclick = () => {
        if (type === 'Similar') {
          similarity = true;
          $('similarity').setAttribute('aria-pressed', 'true');
        } else $('relation').value = type;
        render();
      };
    }),
);

function spotlight(id) {
  const active = new Set(
    [...data.edges.map(e => ({ ...e, a: owner(e.source), b: owner(e.target) })), ...data.similarities]
      .filter(e => e.a === id || e.b === id)
      .map(e => e.id),
  );
  document.querySelectorAll('[data-line],[data-edge]').forEach(el => {
    const key = el.dataset.line || el.dataset.edge;
    el.classList.toggle('nearby', active.has(key));
    el.classList.toggle('distant', !active.has(key));
  });
}
wireMovableCards({ graph: $('graph'), positions, position: id => pos(paper(id)), render, onSave: saveLayout });
$('reset-layout').onclick = () => {
  positions.clear();
  saveLayout();
  canvasViewport.frame();
  render();
};

function setData(d) {
  // Filters and saved positions follow the selected paper.
  data = d;
  const key = 'paper-evolve-layout-v2:' + (d.focus || 'home');
  if (key !== layoutKey) {
    layoutKey = key;
    positions.clear();
    try {
      const stored = localStorage.getItem(key);
      for (const [id, p] of JSON.parse(stored || '[]'))
        if (d.papers.some(n => n.id === id) && Number.isFinite(p.x) && Number.isFinite(p.y))
          positions.set(id, {
            x: Math.max(16, Math.min((d.width || STAGE.width) - CARD.width - 20, p.x)),
            y: Math.max(64, Math.min((d.height || STAGE.height) - CARD.height - 24, p.y)),
          });
    } catch {}
  }
  similarity = Boolean(d.papers.length && !d.edges.some(e => e.status === 'source_supported'));
  $('similarity')?.setAttribute('aria-pressed', String(similarity));
  const fill = (id, first, values) => {
    const el = $(id);
    el.innerHTML = '';
    if (first) el.add(new Option(first, ''));
    for (const [label, value] of values) el.add(new Option(label, value));
  };
  fill('venue', null, [['All venues', 'All sources'], ...[...new Set(d.papers.map(p => p.venue))].map(v => [v, v])]);
  const years = [...new Set(d.papers.map(p => p.year))].sort((a, b) => a - b),
    span = [];
  for (let y = years[0]; y <= years[years.length - 1]; y++) span.push([y, y]);
  fill('from', null, span);
  fill('to', null, [...span].reverse());
  fill('evidence', null, [
    ...(d.computed ? [['Source passages only', 'source_supported']] : []),
    ['All connections', 'All evidence'],
    ...[...new Set(d.edges.map(e => e.status))]
      .filter(s => s !== 'source_supported')
      .map(s => [
        { explicit: 'Explicit source statement', cited: 'Citation only', inferred: 'Abstract-only / inferred' }[s] || s,
        s,
      ]),
  ]);
  fill('relation', '', [
    ['All relationships', 'All relationships'],
    ...['Extends', 'Challenges', 'Combines', 'Transfers', 'Revives'].map(t => [t, t]),
  ]);
  $('timeline-venue-field').hidden = new Set(d.papers.map(p => p.venue)).size <= 1;
  collapsed.clear();
  pathStart = null;
}
async function openEvolution(context = null, { historyMode = 'push' } = {}) {
  const task = evolutionTask.begin();
  reader.cancel();
  workspace.closeNotes();
  const url = paperURL(context);
  activeEvolutionRecord = url ? { ...context, u: url, t: context.t || context.title || 'Selected paper' } : null;
  evolutionLanding = !activeEvolutionRecord;
  homeRequested = false;
  unmappedContext = activeEvolutionRecord ? { ...activeEvolutionRecord, loading: true } : null;
  setData(emptyDataset());
  selected = null;
  edgeSelected = null;
  switchView('evolution', { writeHistory: false, cancelTask: false });
  const hash = evolutionHash(activeEvolutionRecord);
  if (historyMode !== 'none' && location.hash !== hash)
    history[historyMode === 'replace' ? 'replaceState' : 'pushState'](null, '', hash);
  if (evolutionLanding) return true;
  let ego = null,
    loadFailed = false;
  try {
    ego = await buildNeighbourhood(activeEvolutionRecord);
  } catch {
    loadFailed = true;
  }
  if (!task.isCurrent()) return false;
  if (ego) {
    const focus = ego.papers.find(p => p.id === ego.focus);
    activeEvolutionRecord = { ...activeEvolutionRecord, t: focus.title };
    unmappedContext = null;
    setData(ego);
    selected = ego.focus;
    reset();
    details();
  } else {
    unmappedContext = { ...activeEvolutionRecord, loadFailed };
    render();
    details();
  }
  workspace.closeMobileExplorer();
  requestAnimationFrame(() => {
    if (unmappedContext) return;
    canvasViewport.frame();
    document
      .querySelector('#graph .paper.selected')
      ?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'instant' });
  });
  return true;
}
$('change-paper').onclick = () => openEvolution();

canvasViewport = createViewport({ viewport: $('graph-scroll'), surface: $('canvas-surface'), graph: $('graph') });

createDiscoverySearch({
  input: $('search'),
  results: $('discovery-results'),
  searchAll: async query => {
    document.querySelector('[data-view="browse"]').click();
    await openLibrary('browse', { query });
  },
  clearCollectionSearch: () => {
    if (document.body.classList.contains('discovery'))
      openLibrary(document.querySelector('[data-view].active').dataset.view, { query: '', preserveFilters: true });
  },
  selectPaper: async record => {
    if (document.querySelector('[data-view="evolution"]').classList.contains('active')) {
      if (!(await openEvolution(record))) return;
    } else evolutionTask.cancel();
    reader.showPaper(record);
    workspace.openNotes();
    workspace.closeMobileExplorer();
  },
  selectTopic: async topic => {
    document.querySelector('[data-view="browse"]').click();
    await openLibrary('browse', { topic });
    $('details-title').textContent = 'Topic overview';
    $('detail-content').innerHTML =
      '<span class="badge">Research topic</span><h2>' +
      esc(topic) +
      '</h2><p>Select a paper, then open its evolution to explore its connections.</p>';
  },
});

async function restoreRoute() {
  const route = parseRoute(location.hash);
  if (route.view === 'evolution') await openEvolution(route.paper ? { u: route.paper } : null, { historyMode: 'none' });
  else switchView(route.view, { writeHistory: false });
}
await restoreRoute();
window.addEventListener('popstate', () => {
  restoreRoute().catch(error => console.error('Could not restore research view', error));
});
