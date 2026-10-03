"""Landing dashboard API: GET /api/landing/<block> → one KPI block.

Loaders are registered by name (landing_loaders.register_default_loaders() and
WebApp.py for blocks that need its internals). Each block is cached for
CACHE_TTL seconds in process memory, and one block's failure never affects
another. The global _require_auth gate in WebApp.py protects every route here.
"""
import logging
import time
from datetime import date

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)
landing_bp = Blueprint('landing', __name__)

BLOCKS = ('monthly', 'accounts', 'cards', 'housing', 'timeline', 'bills',
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


@landing_bp.route('/api/landing/<block>')
def api_landing_block(block):
    if block not in BLOCKS:
        return _json({'ok': False, 'error': 'unknown block'}, 404)
    hit = _cache.get(block)
    if hit and _now() - hit[0] < CACHE_TTL:
        return _json(hit[1])
    try:
        data = LOADERS[block](_server_today())
    except Exception:
        logger.exception('landing block failed: %s', block)
        return _json({'ok': False, 'error': 'לא זמין כרגע'}, 500)
    _cache[block] = (_now(), data)
    return _json(data)
