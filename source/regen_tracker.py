# Shared in-memory regeneration progress tracker.
# Both WebApp.py (server) and AppManager.py (analysis) import this module.
# Since both run in the same Python process, the module-level dict is shared.

_progress = {}    # {page_id: {'earned': int, 'total': int, 'done': bool}}
_callbacks = {}   # {page_id: callable(pct: int)}


def init(page_id, total=100):
    _progress[page_id] = {'earned': 0, 'total': total, 'done': False}


def set_callback(page_id, cb):
    """Register a callback invoked with the current pct on every update."""
    _callbacks[page_id] = cb


def clear_callback(page_id):
    _callbacks.pop(page_id, None)


def fire_callback(page_id):
    cb = _callbacks.get(page_id)
    if cb:
        p = _progress.get(page_id)
        if p:
            pct = int(p['earned'] / p['total'] * 100) if p['total'] else 100
            try:
                cb(pct)
            except Exception:
                pass


def update(page_id, points):
    if page_id not in _progress:
        return
    p = _progress[page_id]
    p['earned'] = min(p['earned'] + points, p['total'])
    fire_callback(page_id)


def done(page_id):
    if page_id not in _progress:
        return
    _progress[page_id]['earned'] = _progress[page_id]['total']
    _progress[page_id]['done'] = True
    fire_callback(page_id)


def get_pct(page_id):
    if page_id not in _progress:
        return None
    p = _progress[page_id]
    return int(p['earned'] / p['total'] * 100) if p['total'] else 100


def get(page_id):
    return _progress.get(page_id)


def clear(page_id):
    _progress.pop(page_id, None)
    _callbacks.pop(page_id, None)
