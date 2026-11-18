import { readableText } from './text-format.js?v=388bf9ca4d5f';
import { repositoryInfo } from './contribution-repository.js?v=388bf9ca4d5f';
import { loadCorpus, venueName } from './paper-data.js?v=388bf9ca4d5f';
const $ = id => document.getElementById(id),
  fmt = n => Number(n).toLocaleString();
let catalog = null,
  selected = null,
  route = 'agent',
  access = 'repo',
  repository = null,
  mode = 'topics',
  corpus = null,
  titles = null;
const picked = [null, null];
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function topicLabel(name) {
  return name === 'Unclustered' ? 'Uncategorized research' : name;
}
function safeRelative(path, prefix, suffix) {
  return (
    typeof path === 'string' &&
    path.startsWith(prefix) &&
    path.endsWith(suffix) &&
    !path.includes('..') &&
    !/[\\?#:]/.test(path)
  );
}
function available() {
  return catalog.packs.filter(p => p.available_tasks > 0 && !p.legacy);
}
function prompt() {
  if (!selected) return;
  const name = $('contributor-name').value.trim();
  $('agent-prompt').value =
    `${access === 'repo' ? 'In my cloned Paper Evolve repository, read AGENTS.md and community/CLONE.md.' : 'Read README.md in the downloaded Paper Evolve kit.'} Prepare up to 10 tasks from pack ${selected.id} for ${name ? JSON.stringify(name) : 'my contributor name (ask me if needed)'}, using your actual tool/model version. Read the workspace PROMPT.md and community/RESEARCH.md. Download and read the full public papers, investigate methods and references, and use fetch/cite to attach new exact page excerpts when prepared passages are insufficient. Fill submission.json with supported relationships and diagnostic quotes; abstain if research still leaves insufficient evidence. Run check and pr to prepare my contribution. Preserve the original task pack, attach new evidence separately, make no paid model API requests, and do not approve, push or publish without my instruction.`;
}
function accessOptions() {
  for (const name of ['repo', 'kit']) $(name + '-access').setAttribute('aria-pressed', String(access === name));
  $('clone-instructions').hidden = access !== 'repo';
  $('kit-download').hidden = access !== 'kit';
  if (selected)
    $('clone-commands').value =
      `git clone YOUR_FORK_URL paper-evolve\ncd paper-evolve\npython paper_evolve.py start --pack ${selected.id} --name "Your name" --tool "${route === 'api' ? 'Your API model' : 'Actual tool / model version'}"${route === 'api' ? ' --method api' : ''}`;
  prompt();
}
function setAccess(next) {
  access = next;
  accessOptions();
  if (selected) choose(selected);
}
// Your own pair: any two papers from the collection, ordered by year. The commands need a clone, because a kit has no corpus.
function pair() {
  const [a, b] = picked;
  return a && b && a !== b && a.y !== b.y ? (a.y < b.y ? [a, b] : [b, a]) : null;
}
function paperLine(p) {
  return `${venueName(p.v)} · ${p.y}`;
}
function showPair() {
  const chosen = pair(),
    [a, b] = picked;
  $('pair-status').textContent = !corpus
    ? 'Loading the paper collection…'
    : a && b && a === b
      ? 'Pick two different papers.'
      : a && b && a.y === b.y
        ? `Both papers are from ${a.y}. Pick one from an earlier year so the connection has a direction.`
        : '';
  const url = new URL(location.href);
  for (const key of ['pack', 'access', 'pair']) url.searchParams.delete(key);
  for (const p of picked) if (p) url.searchParams.append('pair', p.u);
  url.searchParams.set('route', route);
  history.replaceState(null, '', url);
  $('kit-empty').hidden = !!chosen;
  $('kit-content').hidden = !chosen;
  $('kit-empty-title').textContent = 'Choose two papers to get your commands.';
  $('kit-empty-text').textContent = 'Search for a paper on the left, then for the one it builds on or leads to.';
  if (!chosen) return;
  const [earlier, later] = chosen,
    flags = `--earlier "${earlier.u}" --later "${later.u}"`,
    name = $('contributor-name').value.trim();
  $('kit-area').textContent = 'YOUR OWN PAIR';
  $('kit-title').textContent = 'Propose this connection';
  $('kit-counts').textContent = '1 task · evidence comes from both full papers';
  $('pack-label').hidden = true;
  const preview = $('pair-preview');
  preview.hidden = false;
  preview.replaceChildren(
    el('div', 'YOUR PAIR', 'pair-label'),
    el('div', readableText(earlier.t), 'pair-title'),
    el('div', paperLine(earlier), 'pair-label'),
    el('div', '↓ later work', 'pair-arrow'),
    el('div', readableText(later.t), 'pair-title'),
    el('div', paperLine(later), 'pair-label'),
  );
  $('kit-includes').textContent = 'Work from a clone of the repository. It includes the full paper collection.';
  $('access-options').hidden = true;
  $('kit-download').hidden = true;
  $('clone-instructions').hidden = false;
  $('kit-status').textContent = '';
  $('clone-commands').value =
    `git clone YOUR_FORK_URL paper-evolve\ncd paper-evolve\n` +
    (route === 'api'
      ? `python paper_evolve.py propose ${flags}\n# propose prints the pack ID to use here:\npython paper_evolve.py start --pack PROPOSAL_ID --name "Your name" --tool "Your API model" --method api`
      : `# one command: proposes the pair, reviews it with your agent, validates and exports\npython paper_evolve.py run ${flags} --name "Your name" --agent claude\n# use --agent codex for Codex`);
  $('prompt-title').textContent = 'Or give your agent this prompt';
  $('agent-prompt').value =
    `In my cloned Paper Evolve repository, read AGENTS.md and community/CLONE.md. Create the task with: python paper_evolve.py propose ${flags}. Prepare its workspace for ${name ? JSON.stringify(name) : 'my contributor name (ask me if needed)'}, using your actual tool/model version. Read the workspace PROMPT.md and community/RESEARCH.md. This pair has no prepared passages: download and read both full papers with fetch, and register exact page excerpts with cite. Fill submission.json with a supported relationship and diagnostic quotes from both papers; abstain if the papers do not establish one. Run check and pr to prepare my contribution. Make no paid model API requests, and do not approve, push or publish without my instruction.`;
}
function renderSlot(i) {
  const input = $('paper-search-' + i),
    target = $('paper-results-' + i),
    p = picked[i];
  target.replaceChildren();
  input.hidden = !!p;
  if (p) {
    const card = el('div', undefined, 'paper-picked');
    const change = el('button', 'Change', 'text-button');
    change.type = 'button';
    change.onclick = () => {
      picked[i] = null;
      renderSlot(i);
      showPair();
      input.focus();
    };
    card.append(el('span', readableText(p.t), 'topic-name'), el('span', paperLine(p), 'topic-meta'), change);
    target.append(card);
    return;
  }
  const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
  if (!corpus || !words.length) return;
  const hits = [];
  for (let n = 0; n < corpus.length && hits.length < 300; n++)
    if (words.every(w => titles[n].includes(w))) hits.push(corpus[n]);
  // Whole-word matches first ("lite" should not prefer "Satellite"), then the shortest title, which is usually the paper that was meant.
  const whole = p => {
    const tokens = new Set(p.t.toLowerCase().split(/[^a-z0-9]+/));
    return words.filter(w => tokens.has(w)).length;
  };
  hits.sort((x, y) => whole(y) - whole(x) || x.t.length - y.t.length);
  if (!hits.length) target.append(el('p', 'Nothing yet. Try fewer words from the title.', 'no-topics'));
  for (const hit of hits.slice(0, 8)) {
    const button = el('button', undefined, 'topic-card');
    button.type = 'button';
    button.append(el('span', readableText(hit.t), 'topic-name'), el('span', paperLine(hit), 'topic-meta'));
    button.onclick = () => {
      picked[i] = hit;
      input.value = '';
      renderSlot(i);
      showPair();
    };
    target.append(button);
  }
}
async function openPairs(urls = []) {
  showPair();
  if (!corpus) {
    try {
      corpus = await loadCorpus();
      titles = corpus.map(p => p.t.toLowerCase());
    } catch {
      $('pair-status').textContent =
        'The paper collection didn’t load. Reload the page, or use the find and propose commands from a clone.';
      return;
    }
  }
  urls.slice(0, 2).forEach((u, i) => {
    picked[i] = corpus.find(p => p.u === u) || null;
  });
  for (const i of [0, 1]) renderSlot(i);
  showPair();
  if (urls.length && picked.filter(Boolean).length < Math.min(urls.length, 2))
    $('pair-status').textContent = 'That paper isn’t in the collection yet. Search for another one.';
}
function setMode(next, urls) {
  mode = next;
  for (const name of ['topics', 'pair']) $(name + '-mode').setAttribute('aria-pressed', String(mode === name));
  $('topic-browser').hidden = mode !== 'topics';
  $('pair-browser').hidden = mode !== 'pair';
  if (mode === 'pair') {
    openPairs(urls);
    return;
  }
  $('kit-empty-title').textContent = 'Choose a topic to get your kit.';
  $('kit-empty-text').textContent =
    'Everything stays in one small folder, from the first prompt to the finished contribution.';
  $('kit-includes').textContent =
    'The repository includes the topic packs, prompts and tools. Fork it and contribute from a clone, or take a portable kit.';
  $('access-options').hidden = false;
  $('prompt-title').textContent = 'Then give your agent this prompt';
  const url = new URL(location.href);
  url.searchParams.delete('pair');
  history.replaceState(null, '', url);
  $('kit-empty').hidden = !!selected;
  $('kit-content').hidden = !selected;
  if (selected) choose(selected);
}
function choose(pack, { updateURL = true } = {}) {
  selected = pack;
  $('kit-empty').hidden = true;
  $('kit-content').hidden = false;
  $('kit-area').textContent = topicLabel(pack.area);
  $('kit-title').textContent = topicLabel(pack.topic);
  $('kit-counts').textContent =
    `${fmt(pack.available_tasks)} available tasks · ${fmt(pack.fulltext_tasks)} with source passages`;
  const siblings = available().filter(p => p.topic === pack.topic),
    select = $('pack-select');
  select.replaceChildren();
  siblings.forEach((p, i) => {
    const option = el('option', `Pack ${i + 1} · ${p.available_tasks} available tasks`);
    option.value = p.id;
    select.append(option);
  });
  select.value = pack.id;
  $('pack-label').hidden = siblings.length < 2;
  const preview = $('pair-preview');
  preview.replaceChildren();
  preview.hidden = pack.sample?.length !== 2;
  if (!preview.hidden)
    preview.append(
      el('div', 'EXAMPLE PAPER PAIR', 'pair-label'),
      el('div', readableText(pack.sample[0]), 'pair-title'),
      el('div', '↓ later work', 'pair-arrow'),
      el('div', readableText(pack.sample[1]), 'pair-title'),
    );
  const download = $('download-kit');
  download.href = 'community/' + pack.bundle;
  download.download = 'paper-evolve-' + pack.id + '.zip';
  $('kit-status').textContent = '';
  accessOptions();
  document
    .querySelectorAll('[data-pack]')
    .forEach(button =>
      button.setAttribute(
        'aria-pressed',
        String(available().find(p => p.id === button.dataset.pack)?.topic === pack.topic),
      ),
    );
  if (updateURL) {
    const url = new URL(location.href);
    url.searchParams.set('pack', pack.id);
    url.searchParams.set('route', route);
    url.searchParams.set('access', access);
    history.replaceState(null, '', url);
  }
}
function renderTopics() {
  const query = $('topic-search').value.trim().toLowerCase(),
    area = $('area-filter').value,
    seen = new Set();
  const packs = available().filter(p => {
    if (
      seen.has(p.topic) ||
      (area && p.area !== area) ||
      (query && !`${p.topic} ${p.area}`.toLowerCase().includes(query))
    )
      return false;
    seen.add(p.topic);
    return true;
  });
  $('topic-count').textContent = `${packs.length} ${packs.length === 1 ? 'topic' : 'topics'} available`;
  const target = $('topic-list');
  target.replaceChildren();
  if (!packs.length) {
    target.append(el('p', 'Nothing matches yet. Try a broader search or another research area.', 'no-topics'));
    return;
  }
  for (const pack of packs) {
    const siblings = available().filter(p => p.topic === pack.topic),
      count = siblings.reduce((n, p) => n + p.available_tasks, 0),
      sources = siblings.reduce((n, p) => n + p.fulltext_tasks, 0);
    const button = el('button', undefined, 'topic-card');
    button.dataset.pack = pack.id;
    button.type = 'button';
    button.setAttribute('aria-pressed', String(selected?.topic === pack.topic));
    button.append(
      el('span', topicLabel(pack.topic), 'topic-name'),
      el('span', `${fmt(count)} tasks · ${fmt(sources)} with source passages`, 'topic-meta'),
    );
    button.onclick = () => choose(pack);
    target.append(button);
  }
}
function setRoute(next) {
  route = next;
  for (const name of ['agent', 'api']) $(name + '-route').setAttribute('aria-pressed', String(next === name));
  $('agent-instructions').hidden = next !== 'agent';
  $('api-instructions').hidden = next !== 'api';
  $('route-description').textContent =
    next === 'agent'
      ? 'Use your existing agent account. The pack includes the prompt, paper evidence and submission tools.'
      : 'Run the tasks locally through your own API key, with an explicit model and spending limit.';
  if (mode === 'pair') showPair();
  else if (selected) choose(selected);
}
$('agent-route').onclick = () => setRoute('agent');
$('api-route').onclick = () => setRoute('api');
$('topic-search').oninput = renderTopics;
$('area-filter').onchange = renderTopics;
$('contributor-name').oninput = () => (mode === 'pair' ? showPair() : prompt());
$('topics-mode').onclick = () => setMode('topics');
$('pair-mode').onclick = () => setMode('pair');
for (const i of [0, 1]) $('paper-search-' + i).oninput = () => renderSlot(i);
$('repo-access').onclick = () => setAccess('repo');
$('kit-access').onclick = () => setAccess('kit');
$('pack-select').onchange = () => {
  const p = available().find(p => p.id === $('pack-select').value);
  if (p) choose(p);
};
$('copy-prompt').onclick = async () => {
  try {
    await navigator.clipboard.writeText($('agent-prompt').value);
    $('kit-status').textContent =
      access === 'repo'
        ? 'Prompt copied. Open your cloned repository and paste it into your agent.'
        : 'Prompt copied. Unzip the kit, open its folder, and paste this into your agent.';
  } catch {
    $('agent-prompt').focus();
    $('agent-prompt').select();
    $('kit-status').textContent = 'Select and copy the prompt above.';
  }
};
$('copy-clone').onclick = async () => {
  try {
    await navigator.clipboard.writeText($('clone-commands').value);
    $('kit-status').textContent = 'Commands copied. Replace YOUR_FORK_URL and contributor details before running.';
  } catch {
    $('clone-commands').focus();
    $('clone-commands').select();
    $('kit-status').textContent = 'Select and copy the commands above.';
  }
};
async function loadRepository() {
  let config = {};
  try {
    const response = await fetch('community/project.json', { cache: 'no-cache' });
    if (response.ok) config = await response.json();
  } catch {}
  repository = repositoryInfo(config, location.href);
  if (repository) {
    $('fork-repository').href = repository.forkURL;
    $('fork-repository').hidden = false;
    $('view-pull-requests').href = repository.pullsURL;
    $('view-pull-requests').hidden = false;
    $('repository-status').textContent =
      repository.repository + ' · Fork this project, then use your fork’s clone URL.';
  }
}
async function load() {
  try {
    const response = await fetch('community/task-manifest.json', { cache: 'no-cache' });
    if (!response.ok) throw new Error('Unavailable catalog');
    catalog = await response.json();
    if (
      !Array.isArray(catalog.packs) ||
      catalog.packs.some(
        p =>
          !safeRelative(p.path, 'tasks/', '.json') ||
          !safeRelative(p.bundle, 'bundles/', '.zip') ||
          !/^[a-zA-Z0-9_-]+$/.test(p.id),
      )
    )
      throw new Error('Invalid catalog');
    const stats = $('contribution-stats');
    stats.replaceChildren();
    for (const [value, label] of [
      [catalog.summary.topics, 'research topics'],
      [catalog.summary.topic_tasks, 'prepared tasks'],
      [catalog.summary.topic_fulltext_tasks, 'with source passages'],
      [catalog.topics.reduce((n, t) => n + t.papers, 0), 'papers you can pair yourself'],
    ]) {
      const item = el('span');
      item.append(el('strong', fmt(value)), document.createTextNode(' ' + label));
      stats.append(item);
    }
    $('area-filter').replaceChildren(el('option', 'All research areas'));
    $('area-filter').firstChild.value = '';
    for (const area of [...new Set(available().map(p => p.area))].sort()) {
      const option = el('option', topicLabel(area));
      option.value = area;
      $('area-filter').append(option);
    }
    $('topic-search').disabled = false;
    $('area-filter').disabled = false;
    const url = new URL(location.href);
    if (url.searchParams.get('access') === 'kit') access = 'kit';
    if (url.searchParams.get('topic')) $('topic-search').value = url.searchParams.get('topic');
    renderTopics();
    const pack =
      available().find(p => p.id === url.searchParams.get('pack')) ||
      available().find(p => p.topic === url.searchParams.get('topic'));
    if (pack) choose(pack, { updateURL: false });
    if (url.searchParams.get('route') === 'api') setRoute('api');
    if (url.searchParams.has('pair')) setMode('pair', url.searchParams.getAll('pair'));
  } catch {
    $('contribution-stats').textContent = 'The topic collection could not be loaded.';
    const target = $('topic-list');
    target.replaceChildren(el('p', 'Please retry, or use the command-line contribution guide.', 'no-topics'));
    const retry = el('button', 'Retry topic collection', 'text-button');
    retry.onclick = load;
    target.append(retry);
  }
}
load();
loadRepository();
