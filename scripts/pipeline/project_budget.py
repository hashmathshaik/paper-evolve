"""Account for historical preparation before allocating the authorized project cap.

External jobs must be stopped before taking this snapshot. Reserves deliberately
include failed HTTP allowances; this is a conservative limit, not an invoice.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared modules live in scripts/
import argparse,json,sqlite3
import relation_core as C

def historical_allowances():
    queries={
        'voyage_reserved':('work/voyage/cache.sqlite3','SELECT COALESCE(SUM(reserved_usd),0) FROM attempts'),
        'openalex_reserved':('work/openalex/cache.sqlite3','SELECT COALESCE(SUM(amount),0) FROM attempts'),
        'legacy_jev_usage':('work/edges/jev.sqlite3','SELECT COALESCE(SUM(input_tokens),0)*0.042/1000000 FROM runs'),
    }
    result={}
    for name,(path,sql) in queries.items():
        # Missing accounting must fail closed, never become a zero estimate.
        with sqlite3.connect((C.ROOT/path).as_uri()+'?mode=ro',uri=True) as db:
            result[name]=db.execute(sql).fetchone()[0]
    return result

def configure(ledger,maximum,breakdown,contingency=2):
    import math
    amounts=[maximum,contingency,*breakdown.values()]
    if not amounts or any(not math.isfinite(x) or x<0 for x in amounts):
        raise ValueError('Budget amounts must be finite and nonnegative')
    external=sum(breakdown.values())
    with ledger.lock:
        ledger.db.execute('BEGIN IMMEDIATE')
        try:
            spent=ledger.db.execute('SELECT COALESCE(SUM(cost),0) FROM calls').fetchone()[0]
            if maximum < external+contingency+spent:raise ValueError('Maximum is below existing allowances')
            ledger.db.execute('INSERT OR REPLACE INTO project_budget VALUES (1,?,?,?,?)',
                              (maximum,external,contingency,json.dumps(breakdown)))
            ledger.db.commit()
        except BaseException:
            ledger.db.rollback();raise
    return ledger.project_snapshot()

def configure_edges(ledger,maximum=30):
    """Persist a cumulative edge ceiling, enforced by every ledger connection."""
    import math
    if not math.isfinite(maximum) or not 0 < maximum <= 30:
        raise ValueError('Authorized cumulative edge ceiling is at most $30.')
    with ledger.lock:
        ledger.db.execute('BEGIN IMMEDIATE')
        try:
            spent=ledger.db.execute('SELECT COALESCE(SUM(cost),0) FROM calls').fetchone()[0]
            if spent>maximum:raise ValueError('Ceiling is below already spent/reserved funds.')
            ledger.db.execute('INSERT OR REPLACE INTO relation_budget VALUES (1,?)',(maximum,))
            ledger.db.commit()
        except BaseException:
            ledger.db.rollback();raise
    return ledger.project_snapshot()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--maximum-usd',type=float,required=True)
    args=ap.parse_args()
    if not 0<args.maximum_usd<=50:ap.error('Authorized project maximum is $50.')
    ledger=C.Ledger(C.J.E/'relations.sqlite3',args.maximum_usd)
    print(json.dumps(configure(ledger,args.maximum_usd,historical_allowances()),indent=2))

if __name__=='__main__':main()
