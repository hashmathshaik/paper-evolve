"""Offline nearest papers by shared wording, for papers that have no embedding yet.

BM25 (Robertson & Zaragoza 2009, k1=1.2, b=0.75) over title + abstract, standard
library only. Deviation from the textbook form: a query is a whole paper, so
only its 24 highest-weighted terms are scored, and terms found in more than a
fifth of the collection are dropped. Wording overlap is a discovery aid. It is
never evidence of influence and is replaced once real embeddings are computed.
"""
import collections
import heapq
import json
import math
import re
from array import array
from pathlib import Path

K1, B, QUERY_TERMS, COMMON = 1.2, .75, 24, .2
STOP = set('''the and for with that this from are was were which have has had been can our their its into such these those than
then also may not but all any each both more most other some only over under between within without using use used via per while
when where how what why who whom whose will would should could about above after again against among because before being
below does doing down during few further here itself just nor off once out own same too very you your they them his her she
him one two three new based show shows shown paper propose proposed present results result method methods approach model models
we in on of to a an is it as at by be or'''.split())
WORD = re.compile(r'[a-z][a-z0-9]+')


def terms(text):
    return [w for w in WORD.findall(text.lower()) if len(w) > 2 and w not in STOP]


class Index:
    """postings[term] = (paper indices, term counts); lengths[i] = number of terms in paper i."""

    def __init__(self):
        self.postings, self.lengths = {}, array('I')

    def add(self, text):
        counts = collections.Counter(terms(text))
        paper = len(self.lengths)
        self.lengths.append(sum(counts.values()))
        for term, count in counts.items():
            if term not in self.postings:
                self.postings[term] = (array('I'), array('H'))
            papers, tfs = self.postings[term]
            papers.append(paper)
            tfs.append(min(count, 65535))

    def idf(self, term):
        n, df = len(self.lengths), len(self.postings[term][0]) if term in self.postings else 0
        return math.log(1 + (n - df + .5) / (df + .5))

    def nearest(self, text, count=5):
        """[(paper index, score relative to the best possible match)], best first."""
        n = len(self.lengths)
        average = sum(self.lengths) / max(1, n)
        wanted = collections.Counter(terms(text))
        ranked = sorted(((tf * self.idf(t), t) for t, tf in wanted.items()
                         if t in self.postings and len(self.postings[t][0]) <= max(2, COMMON * n)), reverse=True)[:QUERY_TERMS]
        scores = collections.defaultdict(float)
        for _, term in ranked:
            weight = self.idf(term)
            papers, tfs = self.postings[term]
            for paper, tf in zip(papers, tfs):
                scores[paper] += weight * tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.lengths[paper] / average))
        ceiling = sum(self.idf(term) * (K1 + 1) for _, term in ranked) or 1  # every query term at saturated frequency
        return [(paper, round(score / ceiling, 3)) for score, paper in
                heapq.nlargest(count, ((s, p) for p, s in scores.items()))]


def collection_index(root):
    """Index every published paper, in collection order, from the public files."""
    root = Path(root)
    rows = json.loads((root / 'evolve/corpus.json').read_text())
    shards = root / 'evolve/generated/abstracts'
    size, index, shard, loaded = json.loads((shards / 'meta.json').read_text())['shard_size'], Index(), None, -1
    for i, row in enumerate(rows):
        if i // size != loaded:
            loaded, shard = i // size, json.loads((shards / f'{i // size:03d}.json').read_text())
        index.add(row['t'] + ' ' + shard[i % size]['abstract'])
    return index
