"""Generate a small, diverse entry point from the real published edge shards.

Reads public artifacts only, so the same build works on GitHub Pages CI.
No example timelines, private cache, or model/API calls are involved.
"""
import json
from pathlib import Path
from voyage_pipeline import atomic_json


def export(root, limit=6):
    root = Path(root)
    corpus = json.loads((root / 'evolve/corpus.json').read_text())
    edges = root / 'evolve/generated/edges'
    meta_path = edges / 'meta.json'
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    overlay_path = root / 'evolve/generated/community.json'
    overlay = json.loads(overlay_path.read_text()).get('entries', {}) if overlay_path.exists() else {}
    candidates = []
    edge_count = 0
    for path in sorted(edges.glob('[0-9]*.json')):
        for identity, item in json.loads(path.read_text()).items():
            index = int(identity)
            if not 0 <= index < len(corpus):continue
            extra = overlay.get(identity, {})
            connections = [row for row in item.get('c', []) if row[0] not in extra.get('overrides', [])] + extra.get('c', [])
            edge_count += sum(row[1] == 1 for row in connections)
            source_edges = [row for row in connections if len(row) >= 9 and row[-1].get('quality_tier') == 'fulltext_supported_prediction']
            if not source_edges:continue
            verified = sum(bool(row[-1].get('verification')) for row in source_edges)
            record = corpus[index]
            candidates.append(((-verified, -len(source_edges), record['t'], index),
                               {**record, 'connections': len(source_edges)}))
    candidates.sort(key=lambda item: item[0])
    chosen = []
    areas, topics, urls = set(), set(), set()
    for distinct in ('mega', 'topic', None):
        for _, record in candidates:
            if len(chosen) >= limit:break
            if record['u'] in urls:continue
            if distinct == 'mega' and record.get('mega', '') in areas:continue
            if distinct == 'topic' and record.get('topic', '') in topics:continue
            chosen.append(record)
            urls.add(record['u']);areas.add(record.get('mega', ''));topics.add(record.get('topic', ''))
    result = {'papers': len(corpus), 'edges': edge_count,
              'classified_pairs': meta.get('classified_pairs', 0), 'generated_at': meta.get('generated_at'),
              'starters': chosen}
    atomic_json(root / 'evolve/generated/evolution-starters.json', result)
    return result
