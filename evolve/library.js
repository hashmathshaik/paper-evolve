import { loadCorpus, readPaper, venueName } from './paper-data.js?v=39205891c9e4';
import { escapeHTML as esc, readableText } from './text-format.js?v=39205891c9e4';
import { renderMath } from './math.js?v=39205891c9e4';
const groupLabel = name => (name === 'Unclustered' ? 'Uncategorized research' : name);
import { createLandscapeTimeline, areaColor, AREA_ORDER, HUES, NEUTRAL } from './landscape-timeline.js?v=39205891c9e4';
const scattered = new Set(['Unclustered', 'Specialized / Niche Topics']); // catch-all groups, not real topics
export function createLibrary({ selectPaper, openEvolution }) {
  let records = null,
    timeline = null,
    partial = null,
    view = 'map',
    area = '',
    topic = '',
    page = 0,
    selectedURL = '',
    revision = 0,
    openRevision = 0;
  const bandCache = new Map();
  const $ = id => document.getElementById(id),
    pageSize = 20;
  function filtered(skip = '') {
    const words = $('library-search').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return records.filter(
      p =>
        (skip.includes('year') || !$('library-year').value || p.y === +$('library-year').value) &&
        (!$('library-venue').value || p.v === $('library-venue').value) &&
        (skip.includes('area') || ((!area || p.mega === area) && (!topic || p.topic === topic))) &&
        words.every(word => `${p.t} ${p.topic} ${p.leaf} ${p.mega}`.toLowerCase().includes(word)),
    );
  }
  function openGroup(name) {
    if (area) topic = name;
    else area = name;
    page = 0;
    render();
    document.querySelector('main').scrollTop = 0;
  }
  // Which band each group is drawn in. Fixed by overall size, so a filter never repaints a group.
  function bands() {
    if (!bandCache.has(area)) {
      const of = new Map(),
        order = [];
      if (!area)
        for (const name of [...AREA_ORDER, ...new Set(records.map(p => p.mega))])
          if (!of.has(name)) {
            of.set(name, { name, color: areaColor(name) });
            order.push(of.get(name));
          }
      if (area) {
        const size = new Map();
        for (const p of records) if (p.mega === area) size.set(p.topic, (size.get(p.topic) || 0) + 1);
        const named = [...size]
          .filter(([name]) => !scattered.has(name))
          .sort((a, b) => b[1] - a[1])
          .map(([name]) => name);
        // Past eight hues more colours stop being readable, so smaller topics share one grey band and catch-alls another.
        const other = { name: 'Other topics', color: '#888780', folded: true },
          loose = { name: named.length ? 'Niche and uncategorized' : area, color: NEUTRAL, folded: true };
        for (const name of size.keys()) {
          const i = named.indexOf(name);
          of.set(name, i < 0 ? loose : i < HUES.length ? { name, color: HUES[i] } : other);
        }
        order.push(...named.slice(0, HUES.length).map(name => of.get(name)), other, loose);
      }
      bandCache.set(area, { of, order });
    }
    return bandCache.get(area);
  }
  function clearSearch() {
    $('search').value = '';
    $('search').dispatchEvent(new Event('input'));
  }
  function changePage(next) {
    page = next;
    render();
    document.querySelector('main').scrollTop = 0;
  }
  function pagination(target, count) {
    const pages = Math.max(1, Math.ceil(count / pageSize));
    if (pages === 1) {
      target.innerHTML = '';
      return;
    }
    target.innerHTML = `<span class="pagination-range">${(page * pageSize + 1).toLocaleString()}–${Math.min((page + 1) * pageSize, count).toLocaleString()} of ${count.toLocaleString()}</span><div class="pagination-actions"><button data-page="${page - 1}" ${page === 0 ? 'disabled' : ''} aria-label="Previous page">← Previous</button><span>Page ${page + 1} / ${pages.toLocaleString()}</span><button data-page="${page + 1}" ${page + 1 >= pages ? 'disabled' : ''} aria-label="Next page">Next →</button></div>`;
    target.querySelectorAll('[data-page]').forEach(button => (button.onclick = () => changePage(+button.dataset.page)));
  }
  function render() {
    if (!records) return;
    const current = ++revision,
      all = filtered(),
      groupView = view === 'map' && !topic;
    const sort = $('library-sort').value;
    if (!groupView)
      all.sort(
        sort === 'title'
          ? (a, b) => a.t.localeCompare(b.t)
          : (a, b) => (sort === 'oldest' ? a.y - b.y : b.y - a.y) || a.t.localeCompare(b.t),
      );
    page = Math.min(page, Math.max(0, Math.ceil(all.length / pageSize) - 1));
    const query = $('library-search').value.trim();
    $('library-title').textContent = query
      ? 'Search results'
      : view === 'map'
        ? groupLabel(topic || area || 'Research landscape')
        : groupLabel(topic || area || 'Browse papers');
    const contributionLink = $('library-contribute');
    contributionLink.hidden = !topic;
    contributionLink.href = 'contribute.html?topic=' + encodeURIComponent(topic);
    const groups = new Map();
    if (groupView)
      for (const p of all) {
        const name = p[area ? 'topic' : 'mega'];
        if (!groups.has(name)) groups.set(name, []);
        groups.get(name).push(p);
      }
    $('library-count').textContent =
      `${all.length.toLocaleString()} ${all.length === 1 ? 'paper' : 'papers'} · ${query ? 'Matching “' + query + '”' : groupView ? groups.size + ' ' + (area ? (groups.size === 1 ? 'topic' : 'topics') : groups.size === 1 ? 'research area' : 'research areas') : 'Select a paper to read its abstract'}`;
    $('library-sort-field').hidden = groupView || all.length < 2;
    $('library-controls').classList.toggle('group-controls', groupView || all.length < 2);
    $('topic-trail').hidden = !area && !topic && !query && !$('library-year').value && !$('library-venue').value;
    $('topic-trail').innerHTML =
      `<button id="all-areas">All research</button>${area ? `<span class="breadcrumb-divider" aria-hidden="true">/</span><button id="current-area">${esc(groupLabel(area))}</button>` : ''}${topic ? `<span class="breadcrumb-divider" aria-hidden="true">/</span><span aria-current="page">${esc(groupLabel(topic))}</span>` : ''}`;
    $('all-areas').onclick = () => {
      area = '';
      topic = '';
      page = 0;
      for (const id of ['library-search', 'library-year', 'library-venue']) $(id).value = '';
      clearSearch();
      render();
    };
    if (area)
      $('current-area').onclick = () => {
        topic = '';
        page = 0;
        render();
      };
    if (groupView) {
      // The timeline needs every year, so it ignores the Year filter and marks the chosen year instead.
      const base = filtered('year area'),
        perYear = new Map();
      for (const p of base) perYear.set(p.y, (perYear.get(p.y) || 0) + 1);
      // A year holding only a handful of papers would swing the whole share chart, so it is left out and named in the note.
      const floor = Math.max(0, ...perYear.values()) * 0.02,
        byYear = keep =>
          [...perYear]
            .filter(([, n]) => n >= floor === keep)
            .map(([y]) => y)
            .sort((a, b) => a - b);
      const years = byYear(true),
        sparse = byYear(false),
        column = new Map(years.map((y, i) => [y, i])),
        totals = years.map(y => perYear.get(y)),
        counts = new Map(),
        { of, order } = bands();
      for (const p of base) {
        const i = column.get(p.y);
        if (i === undefined || (area && p.mega !== area)) continue;
        const name = of.get(p[area ? 'topic' : 'mega']).name;
        if (!counts.has(name))
          counts.set(
            name,
            years.map(() => 0),
          );
        counts.get(name)[i]++;
      }
      if (!timeline) timeline = createLandscapeTimeline({ onGroup: openGroup });
      timeline.update({
        years,
        totals,
        sparse,
        selectedYear: +$('library-year').value,
        partial: partial && years[years.length - 1] === partial.year ? partial : null,
        series: order
          .filter(b => counts.has(b.name))
          .map(b => ({ ...b, label: groupLabel(b.name), counts: counts.get(b.name) })),
      });
      const chips = document.createElement('div');
      chips.className = 'area-chips';
      chips.innerHTML = `<p>${area ? 'Topics in this area · select one to list its papers' : 'Research areas · select one to see its topics'}</p>${[
        ...groups,
      ]
        .sort((a, b) => b[1].length - a[1].length)
        .map(
          ([name, items]) =>
            `<button class="area-chip" data-group="${esc(name)}" data-band="${esc(of.get(name).name)}" style="--area-color:${of.get(name).color}"><i></i><span>${esc(groupLabel(name))}</span><b>${items.length.toLocaleString()}</b></button>`,
        )
        .join('')}`;
      $('library-content').replaceChildren(...(years.length > 1 ? [timeline.element] : []), chips);
      chips.querySelectorAll('[data-group]').forEach(button => {
        button.onclick = () => openGroup(button.dataset.group);
        button.onpointerenter = button.onfocus = () => timeline.highlight(button.dataset.band);
        button.onpointerleave = button.onblur = () => timeline.highlight('');
      });
      $('library-pagination').innerHTML = '';
      $('library-pagination-top').innerHTML = '';
    } else {
      const rows = all.slice(page * pageSize, (page + 1) * pageSize);
      $('library-content').innerHTML = rows
        .map(
          (p, i) =>
            `<article class="library-row ${p.u === selectedURL ? 'selected' : ''}" data-row="${i}"><button class="library-paper" data-record="${i}" aria-label="Read ${esc(p.t)}"><div class="library-paper-body"><div class="library-paper-meta">${esc(venueName(p.v))} <span>·</span> ${p.y}</div><h3>${esc(readableText(p.t))}</h3><p class="library-snippet" data-preview="${i}">Loading abstract…</p><div class="library-paper-topic">${esc(groupLabel(p.topic))} <span>Read abstract →</span></div></div></button><button class="paper-evolution-action" data-evolution="${i}" aria-label="Explore evolution of ${esc(p.t)}">Evolution <span aria-hidden="true">→</span></button></article>`,
        )
        .join('');
      function mark(i) {
        selectedURL = rows[i].u;
        $('library-content')
          .querySelectorAll('[data-row]')
          .forEach(row => row.classList.toggle('selected', +row.dataset.row === i));
      }
      $('library-content')
        .querySelectorAll('[data-record]')
        .forEach(
          button =>
            (button.onclick = () => {
              const i = +button.dataset.record;
              mark(i);
              selectPaper(rows[i]);
            }),
        );
      $('library-content')
        .querySelectorAll('[data-evolution]')
        .forEach(
          button =>
            (button.onclick = async () => {
              const i = +button.dataset.evolution;
              mark(i);
              button.disabled = true;
              button.textContent = 'Opening…';
              try {
                await openEvolution(rows[i]);
              } finally {
                if (button.isConnected) {
                  button.disabled = false;
                  button.innerHTML = 'Evolution <span aria-hidden="true">→</span>';
                }
              }
            }),
        );
      rows.forEach((p, i) =>
        readPaper(p)
          .then(full => {
            if (current !== revision) return;
            const target = $('library-content').querySelector(`[data-preview="${i}"]`);
            if (target) {
              target.textContent = readableText(full.abstract || 'Select to view this paper’s details.');
              renderMath(target);
            }
          })
          .catch(() => {
            if (current === revision) {
              const target = $('library-content').querySelector(`[data-preview="${i}"]`);
              if (target) target.textContent = 'Select to load the abstract.';
            }
          }),
      );
      renderMath($('library-content'));
      for (const id of ['library-pagination-top', 'library-pagination']) pagination($(id), all.length);
    }
    if (!all.length) {
      $('library-content').innerHTML =
        '<div class="empty"><h2>No papers found</h2><p>Try a broader title or topic, or clear your filters.</p><button id="clear-library-filters">Clear filters</button></div>';
      $('library-pagination').innerHTML = '';
      $('library-pagination-top').innerHTML = '';
      $('clear-library-filters').onclick = () => {
        for (const id of ['library-search', 'library-year', 'library-venue']) $(id).value = '';
        area = '';
        topic = '';
        page = 0;
        clearSearch();
        render();
      };
    }
  }
  for (const id of ['library-search', 'library-year', 'library-venue', 'library-sort'])
    $(id).addEventListener(id === 'library-search' ? 'input' : 'change', () => {
      page = 0;
      render();
    });
  return async function open(v, selection = null) {
    const opening = ++openRevision;
    view = v;
    if (!records) {
      $('library-content').innerHTML = '<div class="empty" role="status">Loading the research collection…</div>';
      try {
        const loaded = await loadCorpus();
        if (!records) {
          records = loaded;
          for (const y of [...new Set(records.map(p => p.y))].sort((a, b) => b - a))
            $('library-year').add(new Option(y, y));
          for (const venue of [...new Set(records.map(p => p.v))].sort())
            $('library-venue').add(new Option(venueName(venue), venue));
          // The newest year is partial while some venues have not published yet.
          const venuesIn = y => [...new Set(records.filter(p => p.y === y).map(p => p.v))].sort(),
            last = Math.max(...records.map(p => p.y));
          if (venuesIn(last).length < venuesIn(last - 1).length)
            partial = { year: last, venues: venuesIn(last).map(venueName) };
        }
      } catch {
        if (opening === openRevision) {
          $('library-count').textContent = 'Collection unavailable';
          $('library-content').innerHTML =
            '<div class="empty"><h2>Collection unavailable</h2><p>The collection didn’t load. Please try again.</p><button id="retry-library">Retry collection</button></div>';
          $('retry-library').onclick = () => open(v, selection);
        }
        return;
      }
    }
    if (opening !== openRevision) return;
    if (selection) {
      area = '';
      topic = selection.topic || '';
      page = 0;
      if (!selection.preserveFilters) for (const id of ['library-year', 'library-venue']) $(id).value = '';
      $('library-search').value = selection.query || '';
    }
    render();
  };
}
