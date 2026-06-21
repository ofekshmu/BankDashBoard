"""Per-month page generation status tracker with dirty-flag support.

Persists to Outputs/page_status.json:
  { "last_db_change": float, "months": { "yyyy_mm": { "generated_at": float } } }

Status values:
  'none'  — never generated
  'fresh' — generated_at >= last_db_change (data is current)
  'stale' — generated_at < last_db_change (DB changed since last regen)
"""
import os
import json
import time
import threading

_HERE = os.path.dirname(__file__)
_STATUS_FILE = os.path.join(_HERE, '..', 'Outputs', 'page_status.json')
_STATUS_FILE = os.path.normpath(_STATUS_FILE)

_lock = threading.Lock()
_state = {
    'last_db_change': 0.0,
    'months': {},       # yyyy_mm → {'generated_at': float}
}


def _load():
    try:
        with open(_STATUS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _state['last_db_change'] = float(data.get('last_db_change', 0.0))
        _state['months'] = {k: dict(v) for k, v in data.get('months', {}).items()}
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        pass


def _save():
    try:
        os.makedirs(os.path.dirname(_STATUS_FILE), exist_ok=True)
        with open(_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_state, f)
    except Exception:
        pass


_load()


def mark_db_changed():
    """Call after any DB commit. Marks all previously-generated months as stale."""
    with _lock:
        _state['last_db_change'] = time.time()
        _save()


def mark_generated(yyyy_mm: str):
    """Call after a successful monthly regen. Marks the month as fresh."""
    with _lock:
        _state['months'][yyyy_mm] = {'generated_at': time.time()}
        _save()


def get_status(yyyy_mm: str) -> str:
    """Return 'none', 'fresh', or 'stale' for the given month key."""
    with _lock:
        entry = _state['months'].get(yyyy_mm)
        if entry is None:
            return 'none'
        gen_at = float(entry.get('generated_at', 0.0))
        last_db = float(_state['last_db_change'])
        return 'fresh' if gen_at >= last_db else 'stale'


def get_all() -> dict:
    """Return {yyyy_mm: status} for all tracked months."""
    with _lock:
        keys = list(_state['months'].keys())
    return {k: get_status(k) for k in keys}


def all_known_keys() -> list:
    """Return sorted list of all yyyy_mm keys that have been generated at least once."""
    with _lock:
        return sorted(_state['months'].keys())
