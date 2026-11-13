"""Landing dashboard API: GET /api/landing/<block> → one KPI block.

Loaders are registered by name (landing_loaders.register_default_loaders() and
WebApp.py for blocks that need its internals). Each block is cached for
CACHE_TTL seconds in process memory, and one block's failure never affects
another. `?fresh=1` skips the cached copy (the page's refresh button); every
successful response carries `age`, the seconds since the data was computed.
The global _require_auth gate in WebApp.py protects every route here.
"""
import logging
import time
from datetime import date

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
landing_bp = Blueprint('landing', __name__)

BLOCKS = ('monthly', 'accounts', 'cards', 'housing', 'mona', 'timeline', 'bills',
          'spotify', 'plants', 'recurring', 'tagger', 'files')
CACHE_TTL = 300
LOADERS = {}
_cache = {}          # block -> (timestamp, data)


def register_loader(name, fn):
    LOADERS[name] = fn


def clear_cache():
    _cache.clear()


def _now():
    return time.time()


def _server_today():
    return date.today()


def _json(data, status=200):
    resp = jsonify(data)
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _with_age(data, computed_at):
    """A copy of the block data with `age` (whole seconds since it was computed)."""
    return dict(data, age=max(0, int(_now() - computed_at)))


@landing_bp.route('/api/landing/<block>')
def api_landing_block(block):
    """One KPI block: cached for CACHE_TTL unless ?fresh=1; failures are never cached."""
    if block not in BLOCKS:
        return _json({'ok': False, 'error': 'unknown block'}, 404)
    hit = _cache.get(block)
    fresh = request.args.get('fresh') == '1'
    if hit and not fresh and _now() - hit[0] < CACHE_TTL:
        return _json(_with_age(hit[1], hit[0]))
    try:
        data = LOADERS[block](_server_today())
    except Exception:
        logger.exception('landing block failed: %s', block)
        return _json({'ok': False, 'error': 'לא זמין כרגע'}, 500)
    _cache[block] = (_now(), data)
    return _json(_with_age(data, _cache[block][0]))
