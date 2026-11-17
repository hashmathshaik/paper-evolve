"""Deterministic seed/community queue. Ranking is a heuristic, never edge evidence."""
import collections
import json
import relation_core as H
import relation_screen as S

VERSION = 'seed-priority-v2'


def citation_pairs(papers, cites, contexts):
    """Corpus citation links, including links outside embedding neighbours.

    Citation membership only admits a source check; it never establishes a type.
    Keep alternate source IDs mapped to every corpus record, then exclude copies
    and require an earlier publication year.
    """
    from evidence_packets import compact
    titles = {pid: compact(p['title']) for pid, p in papers.items()}
    result = set()
    for ids, graph in ((cites[0], cites[1]), (cites[2], cites[3])):
        reverse = collections.defaultdict(list)
        for pid, ident in ids.items():
            if pid in papers and ident:
                reverse[ident].append(pid)
        links = ((citing, cited) for citing, references in graph.items() for cited in references)
        if ids is cites[0]:
            import itertools
            links = itertools.chain(links, contexts)
        for citing, cited in links:
            for b in reverse.get(citing, ()):
                for a in reverse.get(cited, ()):
                    if (papers[a]['year'] < papers[b]['year'] and titles[a] != titles[b]
                            and papers[a]['source_url'] != papers[b]['source_url']):
                        result.add((a, b))
    return result


def rank_candidates(papers, pairs, cites, contexts, ledger, limit=5000, scope='priority'):
    if limit < 0 or scope not in {'priority', 'expanded'}:
        raise ValueError('Use a nonnegative candidate limit and a supported scope.')
    extra = citation_pairs(papers, cites, contexts) if scope == 'expanded' else set()
    S.setup(ledger)
    known = {(a, b) for a, b in ledger.db.execute(
        "SELECT a,b FROM calls WHERE status IN ('complete','reserved','unknown','invalid','seed_proposed')")}
    from community_edges import load_approved
    known.update(load_approved())
    screens = {(a, b): json.loads(raw) for a, b, raw in ledger.db.execute('SELECT a,b,decision FROM screens')}
    coverage = collections.Counter()
    for a, b, raw in ledger.db.execute("SELECT a,b,result FROM calls WHERE status='complete'"):
        if json.loads(raw).get('related'):
            coverage[a] += 1
            coverage[b] += 1
    documents = set()
    for path in (H.ROOT / 'work/evidence').glob('*.json'):
        doc = json.loads(path.read_text())
        if isinstance(doc, dict) and doc.get('status') == 'ready' and doc.get('source_url'):
            documents.add(doc['source_url'])
    ranked = []
    ordered_pairs = list(pairs) + sorted(extra.difference(pairs))
    for order, (a, b) in enumerate(ordered_pairs):
        if (a, b) in known:
            continue
        citation = (a, b) in extra or H.J.label(a, b, cites) == 1
        screen = screens.get((a, b), {})
        # Spend on plausible contribution links; unranked similarities stay discovery-only.
        if not citation and screen.get('score', 0) < .8:
            continue
        context = contexts.get((cites[0].get(b), cites[0].get(a)))
        has_context = bool(context and context[0])
        cached_docs = sum(papers[p]['source_url'] in documents for p in (a, b))
        influential = bool(context and context[2])
        methodology = bool(context and 'methodology' in context[1])
        rank = (-cached_docs, -int(has_context), -int(citation), -int(influential),
                -int(methodology), coverage[b], -float(screen.get('score', 0)), order, a, b)
        ranked.append((rank, {'a': a, 'b': b, 'citation_backed': citation,
                             'citing_context': has_context, 'cached_documents': cached_docs,
                             'influential_citation': influential, 'methodology_citation': methodology,
                             'jev_score': screen.get('score'), 'existing_endpoint_edges': coverage[a] + coverage[b]}))
    ranked.sort(key=lambda item: item[0])
    # First offer one parent per later paper, then a second, etc. Avoid spending
    # the seed budget entirely on a handful of popular papers.
    visits = collections.Counter()
    rounds = collections.defaultdict(list)
    for _, row in ranked:
        rounds[visits[row['b']]].append(row)
        visits[row['b']] += 1
    rows = [row for layer in sorted(rounds) for row in rounds[layer]]
    return rows[:limit] if limit else rows


def prepare(limit=5000, budget=30, scope='priority'):
    papers, pairs, cites, contexts = H.candidates()
    ledger = H.Ledger(H.J.E / 'relations.sqlite3', budget)
    rows = rank_candidates(papers, pairs, cites, contexts, ledger, limit, scope)
    return ledger, papers, cites, contexts, rows
