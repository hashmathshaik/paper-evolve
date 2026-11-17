"""Bounded source/inference pipeline with a ledger connection per model thread.

The coordinator alone owns progress and publication. A slow source does not
block ready papers. Stop admission first, then drain already admitted work.
"""
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED


def events(rows, pending, load_source, process, ledger_factory, *, workers,
           source_workers, group_size=1, should_stop=lambda: False, admission_stop=None):
    admission_stop = admission_stop if admission_stop is not None else threading.Event()
    local = threading.local()
    connections = []
    connection_lock = threading.Lock()
    iterator = iter(rows)
    pending = deque(pending)
    ready = deque()
    exhausted = False
    source_futures = {}
    model_futures = {}
    window = max(workers * 2, source_workers * 2)

    def stopping():
        return admission_stop.is_set() or should_stop()

    def source(row):
        if stopping():return row, None
        return load_source(row)

    def model(job):
        if stopping():return {'halt': 'paused'}
        try:
            if not hasattr(local, 'ledger'):
                local.ledger = ledger_factory()
                with connection_lock:connections.append(local.ledger)
            result = process(local.ledger, job, stopping)
        except Exception as exc:
            # Any already reserved costs remain held in SQLite. Never retry an
            # unexpected paid outcome or print request data/credentials.
            result = {'halt': 'worker_error', 'error_type': type(exc).__name__}
        if result.get('halt'):admission_stop.set()
        return result

    try:
        with ThreadPoolExecutor(max_workers=source_workers) as sources, ThreadPoolExecutor(max_workers=workers) as models:
            while True:
                if stopping():
                    exhausted = True
                    ready.clear()
                    pending.clear()
                else:
                    while not exhausted and len(source_futures) < source_workers * 2 and len(ready) + len(source_futures) < window:
                        row = next(iterator, None)
                        if row is None:
                            exhausted = True
                            break
                        future = sources.submit(source, row)
                        source_futures[future] = row
                    while len(model_futures) < workers:
                        if pending:
                            job = ('verify', pending.popleft())
                        elif len(ready) >= group_size or (ready and exhausted and not source_futures):
                            job = ('propose', [ready.popleft() for _ in range(min(group_size, len(ready)))])
                        else:break
                        model_futures[models.submit(model, job)] = job[0]
                if not source_futures and not model_futures and exhausted and not ready and not pending:
                    break
                done, _ = wait(set(source_futures) | set(model_futures), timeout=1, return_when=FIRST_COMPLETED)
                for future in done:
                    if future in source_futures:
                        row = source_futures.pop(future)
                        try:
                            _, state = future.result()
                        except Exception as exc:
                            yield {'kind': 'source_error', 'error_type': type(exc).__name__}
                            continue
                        if state is not None:
                            supported = state.get('source_evidence', {}).get('status') == 'ready'
                            if supported and not stopping():ready.append((row['a'], row['b'], state))
                            yield {'kind': 'source', 'ready': supported}
                    else:
                        model_futures.pop(future)
                        yield {'kind': 'model', **future.result()}
                yield {'kind': 'heartbeat', 'active_requests': len(model_futures),
                       'active_sources': len(source_futures), 'ready_queue': len(ready)}
    finally:
        admission_stop.set()
        for connection in connections:connection.db.close()
