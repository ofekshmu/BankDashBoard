"""
Flask web server — replaces terminal menu interaction.

Routes
------
GET  /              serve output.html (or a splash screen when none exists)
POST /api/analysis  start general_analysis in a background thread
GET  /api/logs      SSE stream of log lines produced during analysis
GET  /api/status    return {"running": bool}
GET  /api/stale/<yyyy_mm>   return {"stale": bool}
GET  /api/stale-all         return {yyyy_mm: bool, ...} for all pages
"""

import os
import sys
import threading as _threading

# Ensure source/ siblings (AppManager, database, etc.) are importable whether
# this module is loaded via app.py or directly as a Vercel serverless function.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import queue
import threading
import time as _time
import json as _json
import builtins as _builtins

import re as _re
from flask import Flask, Response, request, jsonify, send_file, redirect
import regen_tracker as _regen_tracker

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE                  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR           = os.path.dirname(_HERE)

# Ensure CWD is always the project root so all relative paths (Personal Information/,
# ShmuelFamiliy.db, Outputs/, etc.) resolve correctly regardless of where the
# process was started (e.g. Vercel serverless, pytest, local terminal).
os.chdir(_PROJECT_DIR)

# Load .env from project root so DATABASE_URL / ADMIN_PASSWORD are available
# for _pg_conn() and other direct os.environ accesses in this module.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(_PROJECT_DIR, '.env'))
except Exception:
    pass

OUTPUT_HTML            = os.path.join(_HERE, 'html', 'output.html')
ORGANIZER_HTML         = os.path.join(_HERE, 'html', 'Organizer_Table.html')
if os.getenv('VERCEL'):  # Vercel: /var/task is read-only; use /tmp
    GENERAL_ANALYSIS_DIR  = '/tmp/general_analysis'
    CATEGORY_ANALYSIS_DIR = '/tmp/category_analysis'
else:
    GENERAL_ANALYSIS_DIR  = os.path.join(_PROJECT_DIR, 'Outputs', 'general_analysis')
    CATEGORY_ANALYSIS_DIR = os.path.join(_PROJECT_DIR, 'Outputs', 'category_analysis')
TAGGER_HTML            = os.path.join(_HERE, 'html', 'Tagger.html')
FILES_HTML             = os.path.join(_HERE, 'html', 'Files.html')

# Months that have already had auto-regeneration triggered this app session.
# A month is added the first time its HTML is missing and we show the regen page.
# Subsequent visits without the file won't trigger another auto-regen — the user
# must click the manual button.  A new deployment resets this set (fresh process).
_session_auto_triggered: set = set()
_monthly_data_cache: dict = {}
_global_data_cache: dict = {}   # keyed by yyyy_mm (most-recent) or 'global'
_accounts_cache: dict = {}      # {'data': {...}} in-memory cache for accounts panel
_housing_cache: dict = {}       # {'ts': float, 'data': dict} in-memory cache for housing panel

_ACCOUNTS_JSON = os.path.join(os.path.dirname(__file__), '..', 'Outputs', 'accounts_data.json')


def _load_accounts_disk():
    try:
        if os.path.exists(_ACCOUNTS_JSON):
            with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
                return _json.load(_f)
    except Exception:
        pass
    return None


def _compute_accounts(progress_callback=None):
    """Run get_global_data, persist accounts portion to disk, return it."""
    from datetime import datetime as _dt_a
    from AppManager import AppManager as _AM_a
    _pc = progress_callback if callable(progress_callback) else None
    gp = _AM_a(skip_parser=True).get_global_data(t=_dt_a.now(), progress_callback=_pc)
    payload = {
        'accounts':      gp.get('accounts', {}),
        'accounts_meta': gp.get('accounts_meta', {}),
    }
    # Also warm global cache so mortgage is available for monthly pages
    _global_data_cache['global'] = {'ts': _time.time(), 'data': gp}
    # Persist to disk
    try:
        os.makedirs(os.path.dirname(_ACCOUNTS_JSON), exist_ok=True)
        with open(_ACCOUNTS_JSON, 'w', encoding='utf-8') as _f:
            _json.dump(payload, _f, ensure_ascii=False)
    except Exception:
        pass
    _accounts_cache['data'] = payload
    return payload

def _make_slug(type_: str, name: str) -> str:
    """type_ = 'cat' | 'biz'"""
    import re as _re2
    safe = _re2.sub(r'[^\w\u0590-\u05FF]', '_', name).strip('_')
    return f"{type_}_{safe}"

# ── Log capture via stdout tee ────────────────────────────────────────────────
_log_queue: queue.Queue = queue.Queue()
# Per-thread queue: when set, print/log output from that thread goes here instead
# of the global _log_queue so the SSE generator (in the same Vercel invocation)
# can receive it directly — no cross-invocation shared state needed.
_thread_log_queue = threading.local()

# ── Debug broadcast — rolling buffer + multi-subscriber SSE ──────────────────
_DEBUG_BUFFER_MAX = 300
_debug_buffer: list = []
_debug_subscribers: list = []
_debug_lock = threading.Lock()

def _debug_put(line: str):
    """Append line to rolling buffer and push to every live debug subscriber."""
    with _debug_lock:
        _debug_buffer.append(line)
        if len(_debug_buffer) > _DEBUG_BUFFER_MAX:
            del _debug_buffer[:-_DEBUG_BUFFER_MAX]
        for q in list(_debug_subscribers):
            try:
                q.put_nowait(line)
            except Exception:
                pass

def _log_put(msg: str):
    """Route msg to the thread-local queue (streaming endpoint) or global queue (legacy)."""
    local_q = getattr(_thread_log_queue, 'queue', None)
    if local_q is not None:
        local_q.put(msg)
    else:
        _log_queue.put(msg)
    if msg and not msg.startswith('__'):
        _debug_put(msg)

def _log_error(exc, tb_str: str):
    """Put exception + traceback to both the analysis queue and the debug panel."""
    lines = [f'[ERROR] {exc}'] + [l for l in tb_str.splitlines() if l.strip()]
    local_q = getattr(_thread_log_queue, 'queue', None)
    for line in lines:
        if local_q is not None:
            local_q.put(line)
        else:
            _log_queue.put(line)
        _debug_put(line)

class _TeeStream:
    """Forwards every write() to the original stream *and* the SSE log queues."""
    def __init__(self, original):
        self._orig = original

    def write(self, text):
        try:
            self._orig.write(text)
            self._orig.flush()
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Terminal encoding (e.g. cp1252) can't handle Hebrew — write safe fallback
            safe = text.encode(self._orig.encoding, errors='replace').decode(self._orig.encoding)
            self._orig.write(safe)
            self._orig.flush()
        stripped = text.strip()
        if stripped:
            local_q = getattr(_thread_log_queue, 'queue', None)
            if local_q is not None:
                local_q.put(stripped)
            else:
                _log_queue.put(stripped)
            _debug_put(stripped)

    def flush(self):
        self._orig.flush()

    def fileno(self):
        return self._orig.fileno()

    def __getattr__(self, name):
        return getattr(self._orig, name)


# Install tee once on import — capture both stdout and stderr so exceptions appear in debug panel
if not isinstance(sys.stdout, _TeeStream):
    sys.stdout = _TeeStream(sys.stdout)
if not isinstance(sys.stderr, _TeeStream):
    sys.stderr = _TeeStream(sys.stderr)

# ── Dependency tracking ───────────────────────────────────────────────────────
# Each analysis thread activates thread-local tracking; the patched open()
# records every source .html file that is read during generation so we can
# build an accurate per-page dependency manifest without any hardcoded lists.

_dep_tracking = threading.local()   # .active, .source_dir, .touched
_orig_open    = _builtins.open

def _dep_open(file, *args, **kwargs):
    """Replacement for builtins.open that logs .html reads in the active thread."""
    if getattr(_dep_tracking, 'active', False) and isinstance(file, (str, bytes)):
        fp = os.path.normpath(str(file))
        sd = getattr(_dep_tracking, 'source_dir', '')
        if sd and fp.startswith(sd) and fp.endswith('.html') and os.path.exists(fp):
            _dep_tracking.touched[fp] = os.path.getmtime(fp)
    return _orig_open(file, *args, **kwargs)

_builtins.open = _dep_open


def _capture_deps_and_run(fn):
    """Run fn() and return (deps_dict, db_mtime) of files actually used.

    deps_dict maps abs-path → mtime-at-generation for every .py file loaded
    in source/ (via sys.modules scan) and every .html file opened inside
    source/ (via the _dep_open hook above).  The caller saves this as a
    manifest so future staleness checks only watch relevant files.
    """
    source_dir = os.path.normpath(os.path.join(_PROJECT_DIR, 'source'))
    touched: dict[str, float] = {}

    # Activate thread-local HTML tracking
    _dep_tracking.active     = True
    _dep_tracking.source_dir = source_dir
    _dep_tracking.touched    = touched

    try:
        fn()
    finally:
        _dep_tracking.active = False

    # Collect all source .py modules currently loaded.  Using sys.modules
    # instead of sys.settrace avoids a Python 3.10 + numpy/matplotlib
    # incompatibility where settrace causes np.finfo() to raise TypeError.
    for _mod in list(sys.modules.values()):
        try:
            _fp = getattr(_mod, '__file__', None)
            if _fp:
                _fp = os.path.normpath(_fp)
                if _fp.startswith(source_dir) and _fp.endswith('.py'):
                    touched[_fp] = os.path.getmtime(_fp)
        except OSError:
            pass

    db_mtime = 0.0
    for _db in ('ShmuelFamiliy.db', os.path.join('source', 'ShmuelFamiliy.db')):
        _db_path = os.path.join(_PROJECT_DIR, _db)
        if os.path.exists(_db_path):
            db_mtime = max(db_mtime, os.path.getmtime(_db_path))

    return touched, db_mtime


def _save_manifest(html_path: str, deps: dict, db_mtime: float):
    """Write a JSON manifest alongside html_path recording its exact deps."""
    manifest = {'generated_at': _time.time(), 'deps': deps, 'db_mtime': db_mtime}
    try:
        with _orig_open(html_path.replace('.html', '.manifest.json'), 'w', encoding='utf-8') as _f:
            _json.dump(manifest, _f)
    except Exception:
        pass


def _is_stale_manifest(html_path: str) -> bool:
    """True if any dependency recorded in the manifest has changed since generation.

    Falls back to the broad _max_source_mtime() check when no manifest exists
    yet (first run before any generation with the new system).
    """
    manifest_path = html_path.replace('.html', '.manifest.json')
    if not os.path.exists(manifest_path):
        return _max_source_mtime() > os.path.getmtime(html_path)
    try:
        with _orig_open(manifest_path, encoding='utf-8') as _f:
            data = _json.load(_f)
    except Exception:
        return True

    eps = 0.05  # 50 ms tolerance for filesystem clock skew
    for fp, rec_mt in data.get('deps', {}).items():
        try:
            if os.path.getmtime(fp) > rec_mt + eps:
                return True
        except OSError:
            pass

    db_rec = data.get('db_mtime', 0.0)
    for _db in ('ShmuelFamiliy.db', os.path.join('source', 'ShmuelFamiliy.db')):
        _db_path = os.path.join(_PROJECT_DIR, _db)
        try:
            if os.path.exists(_db_path) and os.path.getmtime(_db_path) > db_rec + eps:
                return True
        except OSError:
            pass

    return False


# ── Analysis state ────────────────────────────────────────────────────────────
_analysis_running  = False
_analysis_lock     = threading.Lock()
_active_regen_key: str | None = None   # which month key is currently regenerating

# ── Credit-card confirmation prompt (analysis thread ↔ browser) ───────────────
_cc_prompt_event  = threading.Event()
_cc_prompt_choice = False   # True = user approved, False = user skipped / timed out


def _web_cc_confirm(row_bank_dict: dict) -> bool:
    """Called from the analysis thread when a potential CC charge is found.
    Sends a __PROMPT_CC__ SSE message, blocks until the user responds (or 120 s).
    Returns True if the user approves categorising as אשראי, False otherwise.
    """
    global _cc_prompt_choice
    try:
        tx = {k: str(v) for k, v in row_bank_dict.items()}
        _cc_prompt_choice = False
        _cc_prompt_event.clear()
        _log_queue.put('__PROMPT_CC__:' + _json.dumps(tx, ensure_ascii=False))
        _cc_prompt_event.wait(timeout=120)   # default = skip (False) on timeout
    except Exception:
        pass
    return _cc_prompt_choice

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False


@app.route('/api/auth/verify', methods=['POST'])
def api_auth_verify():
    """Check password against ADMIN_PASSWORD / DASHBOARD_PASSWORD env var."""
    import hmac
    body     = request.get_json(force=True) or {}
    pw       = str(body.get('password', ''))
    expected = os.environ.get('ADMIN_PASSWORD') or os.environ.get('DASHBOARD_PASSWORD', 'ofek')
    ok = hmac.compare_digest(pw, expected)
    return jsonify({'ok': ok})


@app.errorhandler(404)
def not_found(e):
    """Redirect any 404 back to the landing page rather than showing a raw error."""
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'not found'}), 404
    # For page routes, send the user back home
    return redirect('/')


@app.route('/')
def index():
    # Check project-root index.html first (landing page with auth)
    for candidate in [
        os.path.join(_PROJECT_DIR, 'index.html'),
        os.path.join(_HERE, 'html', 'index.html'),
        '/var/task/index.html',
    ]:
        try:
            p = os.path.abspath(candidate)
            if os.path.isfile(p):
                with open(p, encoding='utf-8') as f:
                    return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
        except Exception:
            continue
    # Fallback: redirect to most recent dashboard
    default_path = None
    if os.path.isdir(GENERAL_ANALYSIS_DIR):
        files = sorted(
            f for f in os.listdir(GENERAL_ANALYSIS_DIR)
            if _re.match(r'^\d{4}_\d{2}\.html$', f)
        )
        if files:
            default_path = '/general/' + files[-1].replace('.html', '')
    if default_path is None and os.path.exists(OUTPUT_HTML):
        default_path = '/output'
    if default_path is None:
        return _splash_html()
    return redirect(default_path)


@app.route('/favicon.svg')
def serve_favicon_svg():
    svg_path = os.path.join(_HERE, 'html', 'logo.svg')
    return send_file(svg_path, mimetype='image/svg+xml')


@app.route('/favicon.ico')
def serve_favicon_ico():
    ico_path = os.path.join(_PROJECT_DIR, 'bankproject.ico')
    if os.path.isfile(ico_path):
        return send_file(ico_path, mimetype='image/x-icon')
    return serve_favicon_svg()


@app.route('/design-system.css')
def serve_design_system():
    css_path = os.path.join(_HERE, 'html', 'design-system.css')
    return send_file(css_path, mimetype='text/css')


@app.route('/outputs/<path:filename>')
def serve_outputs(filename):
    """Serve static files from the Outputs directory (e.g. mortgage PNGs)."""
    outputs_dir = os.path.join(_PROJECT_DIR, 'Outputs')
    file_path = os.path.join(outputs_dir, filename)
    if not os.path.abspath(file_path).startswith(os.path.abspath(outputs_dir)):
        return "Forbidden", 403
    if not os.path.isfile(file_path):
        return "Not found", 404
    return send_file(file_path)


@app.route('/general/<yyyy_mm>')
def serve_general(yyyy_mm):
    if not _re.match(r'^\d{4}_\d{2}$', yyyy_mm) or not (1 <= int(yyyy_mm[5:7]) <= 12):
        return "Invalid month format", 400
    template_path = os.path.join(_HERE, 'html', 'Base_template.html')
    try:
        with open(template_path, 'r', encoding='utf-8') as _f:
            _html = _f.read()
        _html = _html.replace('<body>', f'<body data-month="{yyyy_mm}">', 1)
        return Response(_html, mimetype='text/html')
    except Exception:
        return "Template not found", 500


@app.route('/api/general/<yyyy_mm>/data')
def monthly_data_api(yyyy_mm):
    import time as _time
    if not _re.match(r'^\d{4}_\d{2}$', yyyy_mm):
        return jsonify({'error': 'Invalid month format'}), 400
    month_num = int(yyyy_mm[5:7])
    if not (1 <= month_num <= 12):
        return jsonify({'error': 'Invalid month number'}), 400

    monthly_cached = _monthly_data_cache.get(yyyy_mm)
    global_cached  = _global_data_cache.get('global')

    _no_cache = {'Cache-Control': 'no-store'}

    _ACCT_KEYS = {'accounts', 'accounts_meta'}
    if monthly_cached and global_cached:
        payload = dict(monthly_cached['data'])
        payload.update({k: v for k, v in global_cached['data'].items() if k not in _ACCT_KEYS})
        return jsonify(payload), 200, _no_cache

    if not monthly_cached:
        # Cache cold — could be a different Vercel instance that missed the regen worker's write.
        # Try computing on-demand from the DB. If the month has never been generated (no DB rows),
        # AppManager will raise → we return no_data so the client triggers the regen UI.
        try:
            from datetime import datetime as _dt2
            from AppManager import AppManager
            _t = _dt2(int(yyyy_mm[:4]), month_num, 1)
            _am = AppManager(skip_parser=True)
            monthly_payload = _am.monthly_analysis(t=_t)
            _monthly_data_cache[yyyy_mm] = {'ts': _time.time(), 'data': monthly_payload}
            monthly_cached = {'data': monthly_payload}
        except Exception:
            return jsonify({'error': 'no_data', 'status': 'none'}), 404, _no_cache

    # monthly_cached is guaranteed set here.
    # Fill in global data (mortgage only — accounts served via /api/accounts/data).
    if global_cached:
        payload = dict(monthly_cached['data'])
        payload.update({k: v for k, v in global_cached['data'].items() if k not in _ACCT_KEYS})
        return jsonify(payload), 200, _no_cache

    global_payload = {}
    try:
        from datetime import datetime as _dt2
        from AppManager import AppManager
        _t = _dt2(int(yyyy_mm[:4]), month_num, 1)
        global_payload = AppManager(skip_parser=True).get_global_data(t=_t)
        _global_data_cache['global'] = {'ts': _time.time(), 'data': global_payload}
    except Exception:
        pass
    payload = dict(monthly_cached['data'])
    payload.update({k: v for k, v in global_payload.items() if k not in _ACCT_KEYS})
    return jsonify(payload), 200, _no_cache


@app.route('/api/general/<yyyy_mm>/invalidate', methods=['POST'])
def invalidate_monthly_cache(yyyy_mm):
    _monthly_data_cache.pop(yyyy_mm, None)
    _global_data_cache.pop('global', None)
    return jsonify({'ok': True})


@app.route('/api/regen-progress/<yyyy_mm>')
def regen_progress_api(yyyy_mm):
    """Return {pct: int, done: bool} for a currently-regenerating month."""
    if not _re.match(r'^\d{4}_\d{2}$', yyyy_mm):
        return jsonify({'error': 'Invalid month format'}), 400
    p = _regen_tracker.get(yyyy_mm)
    if p is None:
        return jsonify({'pct': None, 'done': False})
    pct = int(p['earned'] / p['total'] * 100) if p['total'] else 100
    return jsonify({'pct': pct, 'done': bool(p['done'])})


@app.route('/monthly')
def monthly_page():
    """Redirect to the most recent monthly analysis page (used by sidebar nav)."""
    latest_key = _get_latest_yyyy_mm()
    if latest_key:
        return redirect(f'/general/{latest_key}')
    return redirect('/')


@app.route('/accounts')
def accounts_page():
    """Redirect to the latest monthly page with ?panel=accounts."""
    latest_key = _get_latest_yyyy_mm()
    if latest_key:
        return redirect(f'/general/{latest_key}?panel=accounts')
    return redirect('/')


@app.route('/housing')
def housing_page():
    """Redirect to the latest monthly page with ?panel=housing."""
    latest_key = _get_latest_yyyy_mm()
    if latest_key:
        return redirect(f'/general/{latest_key}?panel=housing')
    return redirect('/')


@app.route('/search')
def search_page():
    """Serve the transaction search page."""
    search_html = os.path.join(_HERE, 'html', 'Search.html')
    if os.path.exists(search_html):
        return send_file(search_html)
    return "Search page not found", 404


@app.route('/api/restart', methods=['POST'])
def restart_server():
    """Restart the Flask server process."""
    import threading, subprocess
    def _do():
        import time as _t
        _t.sleep(0.35)
        subprocess.Popen([sys.executable] + sys.argv, cwd=os.getcwd())
        os._exit(0)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/search/transactions')
def search_transactions():
    """Search BankTransactions and CardTransactions with optional filters."""
    q_keyword  = (request.args.get('keyword')  or '').strip()
    q_category = (request.args.get('category') or '').strip()
    q_business = (request.args.get('business') or '').strip()
    q_min      = request.args.get('min',   type=float)
    q_max      = request.args.get('max',   type=float)
    q_exact    = request.args.get('exact', type=float)
    if q_exact is not None:          # exact overrides range — allow 0.01 tolerance
        q_min = q_exact - 0.01
        q_max = q_exact + 0.01
    q_from        = (request.args.get('from')        or '').strip()
    q_to          = (request.args.get('to')          or '').strip()
    q_charge_from = (request.args.get('charge_from') or '').strip()
    q_charge_to   = (request.args.get('charge_to')   or '').strip()
    q_type     = (request.args.get('type')     or 'all').strip()   # 'income' | 'expense' | 'all'
    q_id       = request.args.get('id',  type=int)
    q_split    = (request.args.get('split')    or 'any').strip()  # 'split' | 'nonsplit' | 'any'
    q_source   = (request.args.get('source')   or 'all').strip()  # 'bank' | 'card' | 'all'

    results = []
    conn = None
    try:
        conn = _pg_conn()

        # Pre-fetch split IDs if the filter is active
        split_ids_bank = set()
        split_ids_card = set()
        if q_split != 'any':
            for r in conn.execute(
                "SELECT Original_ID, Original_Table FROM TransactionSplits"
            ).fetchall():
                if r['original_table'] == 'BankTransactions':
                    split_ids_bank.add(r['original_id'])
                else:
                    split_ids_card.add(r['original_id'])

        # ── BankTransactions ──────────────────────────────────────────
        bank_where = []
        bank_params = []

        if q_id is not None:
            bank_where.append("ID = ?")
            bank_params.append(q_id)
        if q_keyword:
            bank_where.append("(Name LIKE ? OR Description LIKE ? OR Extra_Info LIKE ?)")
            like = f'%{q_keyword}%'
            bank_params += [like, like, like]
        if q_category:
            bank_where.append("Category = ?")
            bank_params.append(q_category)
        if q_business:
            bank_where.append("Name LIKE ?")
            bank_params.append(f'%{q_business}%')
        if q_from:
            bank_where.append("Date >= ?")
            bank_params.append(q_from)
        if q_to:
            bank_where.append("Date <= ?")
            bank_params.append(q_to)
        if q_charge_from:
            bank_where.append("Value_Date >= ?")
            bank_params.append(q_charge_from)
        if q_charge_to:
            bank_where.append("Value_Date <= ?")
            bank_params.append(q_charge_to)
        if q_type == 'income':
            bank_where.append("Income > 0")
        elif q_type == 'expense':
            bank_where.append("Out > 0")

        bank_sql = "SELECT ID, Date, Name, Category, Income, Out, Description FROM BankTransactions"
        if bank_where:
            bank_sql += " WHERE " + " AND ".join(bank_where)
        bank_sql += " ORDER BY Date DESC LIMIT 2000"

        for row in (conn.execute(bank_sql, bank_params) if q_source != 'card' else []):
            amount = float(row['income'] or 0) - float(row['out'] or 0)
            if q_min is not None and abs(amount) < q_min:
                continue
            if q_max is not None and abs(amount) > q_max:
                continue
            is_split = row['id'] in split_ids_bank
            if q_split == 'split'    and not is_split: continue
            if q_split == 'nonsplit' and     is_split: continue
            results.append({
                'tx_id':       row['id'],
                'date':        str(row['date'])[:10] if row['date'] else '',
                'name':        row['name'] or '',
                'category':    row['category'] or '',
                'amount':      amount,
                'description': row['description'] or '',
                'source':      'bank',
                'card_id':     None,
                'is_split':    is_split,
            })

        # ── CardTransactions ──────────────────────────────────────────
        card_where = []
        card_params = []

        if q_id is not None:
            card_where.append("ID = ?")
            card_params.append(q_id)
        if q_keyword:
            card_where.append("(Name LIKE ? OR Description LIKE ? OR Extra_Info LIKE ?)")
            like = f'%{q_keyword}%'
            card_params += [like, like, like]
        if q_category:
            card_where.append("Category = ?")
            card_params.append(q_category)
        if q_business:
            card_where.append("Name LIKE ?")
            card_params.append(f'%{q_business}%')
        if q_from:
            card_where.append("Executed_Date >= ?")
            card_params.append(q_from)
        if q_to:
            card_where.append("Executed_Date <= ?")
            card_params.append(q_to)
        if q_charge_from:
            card_where.append("Charge_Date >= ?")
            card_params.append(q_charge_from)
        if q_charge_to:
            card_where.append("Charge_Date <= ?")
            card_params.append(q_charge_to)
        if q_type == 'income':
            card_where.append("Transaction_Value < 0")   # negative = refund/credit = income
        elif q_type == 'expense':
            card_where.append("Transaction_Value > 0")   # positive = charge = expense

        card_sql = "SELECT ID, CardID, Executed_Date, Name, Category, Transaction_Value, Value_Currency, Description FROM CardTransactions"
        if card_where:
            card_sql += " WHERE " + " AND ".join(card_where)
        card_sql += " ORDER BY Executed_Date DESC LIMIT 2000"

        for row in (conn.execute(card_sql, card_params) if q_source != 'bank' else []):
            amount = -float(row['transaction_value'] or 0)  # negate: positive charge → negative (expense)
            if q_min is not None and abs(amount) < q_min:
                continue
            if q_max is not None and abs(amount) > q_max:
                continue
            is_split = row['id'] in split_ids_card
            if q_split == 'split'    and not is_split: continue
            if q_split == 'nonsplit' and     is_split: continue
            results.append({
                'tx_id':       row['id'],
                'date':        str(row['executed_date'])[:10] if row['executed_date'] else '',
                'name':        row['name'] or '',
                'category':    row['category'] or '',
                'amount':      amount,
                'description': row['description'] or '',
                'source':      'card',
                'card_id':     row['cardid'],
                'is_split':    is_split,
            })

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'results': []}), 500
    finally:
        if conn:
            try: conn.close()
            except Exception: pass

    # ── Apply splits: hide originals, surface split rows ─────────────────────
    split_conn = None
    try:
        split_conn = _pg_conn()
        split_rows_db = split_conn.execute(
            'SELECT ID, Original_Table, Original_ID, Amount, Description, Category FROM TransactionSplits'
        ).fetchall()
    except Exception:
        split_rows_db = []
    finally:
        if split_conn:
            try: split_conn.close()
            except Exception: pass

    if split_rows_db:
        split_orig_keys = set((r['original_table'], r['original_id']) for r in split_rows_db)
        # Remove split originals from results
        results = [r for r in results
                   if not (('bank' if r['source'] == 'bank' else 'card') == 'bank'
                           and ('BankTransactions', r['tx_id']) in split_orig_keys)
                   and not (r['source'] == 'card'
                            and ('CardTransactions', r['tx_id']) in split_orig_keys)]
        # Add split rows (using original row metadata)
        orig_meta_cache = {}
        for split_r in split_rows_db:
            orig_table = split_r['original_table']
            orig_id    = split_r['original_id']
            key        = (orig_table, orig_id)
            if key not in orig_meta_cache:
                c2 = None
                try:
                    c2 = _pg_conn()
                    if orig_table == 'BankTransactions':
                        meta = c2.execute(
                            'SELECT Name, Date FROM BankTransactions WHERE ID=%s', (orig_id,)
                        ).fetchone()
                        orig_meta_cache[key] = {
                            'name': meta['name'] if meta else '', 'source': 'bank',
                            'date': str(meta['date'])[:10] if meta and meta['date'] else '', 'card_id': None,
                        }
                    else:
                        meta = c2.execute(
                            'SELECT Name, Executed_Date, CardID FROM CardTransactions WHERE ID=%s', (orig_id,)
                        ).fetchone()
                        orig_meta_cache[key] = {
                            'name': meta['name'] if meta else '', 'source': 'card',
                            'date': str(meta['executed_date'])[:10] if meta and meta['executed_date'] else '',
                            'card_id': meta['cardid'] if meta else None,
                        }
                except Exception:
                    orig_meta_cache[key] = {'name': '', 'source': 'bank', 'date': '', 'card_id': None}
                finally:
                    if c2:
                        try: c2.close()
                        except Exception: pass

            meta = orig_meta_cache[key]
            # Apply all filters to split rows (date, keyword, category, type, amount)
            amount = float(split_r['amount'])
            if q_from and meta['date'] and meta['date'] < q_from: continue
            if q_to   and meta['date'] and meta['date'] > q_to:   continue
            if q_type == 'income' and amount <= 0: continue
            if q_type == 'expense' and amount >= 0: continue
            if q_min is not None and abs(amount) < q_min: continue
            if q_max is not None and abs(amount) > q_max: continue
            if q_keyword:
                hay = (meta['name'] + ' ' + (split_r['description'] or '')).lower()
                if q_keyword.lower() not in hay: continue
            if q_category and split_r['category'] != q_category: continue
            results.append({
                'tx_id':       split_r['id'],
                'date':        meta['date'],
                'name':        meta['name'],
                'category':    split_r['category'],
                'amount':      amount,
                'description': split_r['description'] or '',
                'source':      meta['source'],
                'card_id':     meta['card_id'],
                'is_split':    True,
                'split_id':    split_r['id'],
                'orig_id':     orig_id,
                'orig_table':  orig_table,
            })

    # Flag transactions already linked to a bill entry — the bills-page transaction
    # pickers use this to mark them "Matched" and block re-selecting them, so the
    # same real transaction can't end up linked to two different bill entries.
    try:
        bill_conn = _pg_conn()
        try:
            linked_rows = bill_conn.execute(
                "SELECT Transaction_Table, Transaction_ID FROM BillEntries WHERE Transaction_ID IS NOT NULL"
                " UNION ALL "
                "SELECT Secondary_Transaction_Table, Secondary_Transaction_ID FROM BillEntries"
                " WHERE Secondary_Transaction_ID IS NOT NULL"
            ).fetchall()
        finally:
            bill_conn.close()
        linked_bank_ids = {r[1] for r in linked_rows if r[0] == 'BankTransactions'}
        linked_card_ids = {r[1] for r in linked_rows if r[0] == 'CardTransactions'}
        for r in results:
            r['bill_matched'] = (r['tx_id'] in linked_bank_ids if r['source'] == 'bank'
                                  else r['tx_id'] in linked_card_ids)
    except Exception:
        for r in results:
            r['bill_matched'] = False

    # Sort combined results by date desc
    results.sort(key=lambda x: x['date'] or '', reverse=True)
    return jsonify({'ok': True, 'results': results[:500]})


@app.route('/api/search/categories')
def search_categories():
    """Return distinct category names for the search filter dropdown."""
    conn = None
    try:
        conn = _pg_conn()
        cats = set()
        for row in conn.execute("SELECT DISTINCT Category FROM BankTransactions WHERE Category IS NOT NULL AND Category != ''"):
            cats.add(row[0])
        for row in conn.execute("SELECT DISTINCT Category FROM CardTransactions WHERE Category IS NOT NULL AND Category != ''"):
            cats.add(row[0])
        return jsonify({'categories': sorted(cats)})
    except Exception as e:
        return jsonify({'categories': [], 'error': str(e)})
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


@app.route('/api/general/list')
def general_list():
    from datetime import datetime as _dt
    import page_status as _ps
    result = []
    # Build list from DB (always authoritative)
    try:
        if os.getenv('DATABASE_URL'):
            conn = _pg_conn()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT LEFT(CAST(Date AS TEXT), 7) as ym"
                    " FROM BankTransactions WHERE Date IS NOT NULL ORDER BY ym"
                ).fetchall()
            finally:
                conn.close()
        else:
            from database import DataBase
            rows = DataBase().cursor.execute(
                "SELECT DISTINCT substr(Date, 1, 7) as ym"
                " FROM BankTransactions WHERE Date IS NOT NULL ORDER BY ym"
            ).fetchall()
        for row in rows:
            ym = str(row[0])  # e.g. '2026-05'
            if len(ym) == 7 and ym[4] == '-':
                year, month = int(ym[:4]), int(ym[5:])
                key = f'{year:04d}_{month:02d}'
                result.append({
                    'key':    key,
                    'year':   year,
                    'month':  month,
                    'status': _ps.get_status(key),
                })
    except Exception:
        pass
    # Fallback to HTML files on disk if DB query fails
    if not result and os.path.isdir(GENERAL_ANALYSIS_DIR):
        for fname in sorted(os.listdir(GENERAL_ANALYSIS_DIR)):
            m = _re.match(r'^(\d{4})_(\d{2})\.html$', fname)
            if m:
                year  = int(m.group(1))
                month = int(m.group(2))
                key   = f'{year:04d}_{month:02d}'
                result.append({
                    'key':    key,
                    'year':   year,
                    'month':  month,
                    'status': _ps.get_status(key),
                })
    return jsonify(result)


@app.route('/categories')
def categories_page():
    """HTML page listing all categories and businesses with generated status."""
    from database import DataBase
    cats = DataBase().get_all_category_names() or []
    bizs = DataBase().get_all_business_names() or []

    def _item_html(name, type_, slug):
        from urllib.parse import quote as _quote
        from html import escape as _esc
        fpath = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
        has   = os.path.exists(fpath)
        dot   = f'<span style="width:8px;height:8px;border-radius:50%;background:{"#1e9d8b" if has else "#ccc"};display:inline-block;margin-left:8px;flex-shrink:0"></span>'
        label = 'קטגוריה' if type_ == 'category' else 'עסק'
        badge_color = '#1e9d8b' if type_ == 'category' else '#9b59b6'
        # Include original name as query-param so serve_category can pass it to
        # the auto-trigger without losing special chars like " and /
        name_qs = _quote(name, safe='')
        name_attr = _esc(name, quote=True)
        # data-has drives handleCatClick: generated items navigate straight through
        # (href stays as a working fallback for no-JS / middle-click-new-tab); items
        # that still need generating are intercepted and run inline via a popup on
        # this page instead of redirecting to a separate loading page.
        return (
            f'<a href="/category/{slug}?name={name_qs}" class="cat-item" data-name="{name_attr}"'
            f' data-slug="{slug}" data-type="{type_}" data-has="{1 if has else 0}"'
            f' onclick="return handleCatClick(event, this)"'
            f' style="display:flex;align-items:center;padding:12px 16px;'
            f'background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);'
            f'text-decoration:none;color:#1e2a4a;transition:box-shadow .18s,transform .18s;'
            f'gap:10px" onmouseover="this.style.transform=\'translateY(-2px)\';this.style.boxShadow=\'0 6px 18px rgba(0,0,0,.10)\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'0 2px 8px rgba(0,0,0,.06)\'">'
            f'{dot}'
            f'<span style="flex:1;font-weight:600;font-size:.9em">{name}</span>'
            f'<span class="cat-item-badge" style="font-size:.7em;font-weight:700;color:#fff;background:{badge_color};'
            f'padding:2px 8px;border-radius:10px">{label}</span>'
            f'</a>'
        )

    items_html = ''
    for c in sorted(cats):
        items_html += _item_html(c, 'category', _make_slug('cat', c))
    for b in sorted(bizs):
        items_html += _item_html(b, 'business', _make_slug('biz', b))
    total = len(cats) + len(bizs)

    return f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>ניתוח קטגוריות</title>
{_log_float_style()}
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f9;color:#1e2a4a;direction:rtl;display:flex;min-height:100vh}}
.ham-btn{{position:fixed;top:18px;right:18px;width:42px;height:42px;background:#fff;border:1.5px solid #eef0f6;border-radius:10px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:400;box-shadow:0 2px 10px rgba(0,0,0,.06);color:#1e2a4a;transition:background .15s,color .15s,border-color .15s}}
.ham-btn:hover{{background:#1e9d8b;border-color:#1e9d8b;color:#fff}}
.ham-btn.open{{opacity:0;pointer-events:none}}
.nav-overlay{{position:fixed;inset:0;background:rgba(15,22,45,.26);z-index:390;opacity:0;pointer-events:none;transition:opacity .22s ease}}
.nav-overlay.open{{opacity:1;pointer-events:all}}
.sidebar{{position:fixed;top:0;right:0;height:100vh;width:230px;background:#fff;z-index:395;transform:translate3d(100%,0,0);transition:transform .22s cubic-bezier(.4,0,.2,1);will-change:transform;box-shadow:-4px 0 24px rgba(0,0,0,.09);display:flex;flex-direction:column}}
.sidebar.open{{transform:translate3d(0,0,0)}}
.sidebar-header{{display:flex;align-items:center;padding:20px 20px 16px;border-bottom:1px solid #eef0f6;flex-shrink:0}}
.sidebar-app-name{{font-size:.95em;font-weight:700;color:#1e2a4a}}
.sidebar-close-btn{{margin-right:auto;background:none;border:none;cursor:pointer;font-size:1.1em;color:#555;line-height:1;padding:4px 6px;border-radius:6px;transition:background .12s,color .12s}}
.sidebar-close-btn:hover{{background:#e8f7f5;color:#1e9d8b}}
.sidebar-scroll{{flex:1;overflow-y:auto;overflow-x:hidden;padding:8px 0 16px}}
.nav-item{{display:flex;align-items:center;padding:10px 20px;text-decoration:none;color:#555;font-size:.875em;font-weight:500;transition:background .1s,color .1s;cursor:pointer;border:none;background:none;width:100%;text-align:right;position:relative;letter-spacing:.1px}}
.nav-item::before{{content:'';position:absolute;right:0;top:22%;height:56%;width:3px;border-radius:3px 0 0 3px;background:transparent;transition:background .1s}}
.nav-item:hover{{background:#e8f7f5;color:#1e9d8b}}
.nav-item:hover::before{{background:#1e9d8b}}
.nav-item.active{{color:#b8c0d0;cursor:default;pointer-events:none}}
.nav-sep{{height:1px;background:#eef0f6;margin:8px 16px}}
.main{{margin-right:0;flex:1;padding:32px 32px 60px}}
.page-header{{margin-bottom:24px;padding-right:62px}}
.page-header h1{{font-size:1.7em;font-weight:700}}
.section-title{{font-size:.75em;font-weight:700;color:#888;text-transform:uppercase;
  letter-spacing:.6px;margin:20px 0 10px 0;padding-right:4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}}
.search-wrap{{margin-bottom:18px;display:flex;align-items:center;gap:12px}}
.cat-search{{flex:1;padding:9px 16px;border:1.5px solid #eef0f6;border-radius:10px;
  font-size:.88em;color:#1e2a4a;background:#fff;outline:none;direction:rtl;
  transition:border-color .18s,box-shadow .18s}}
.cat-search:focus{{border-color:#1e9d8b;box-shadow:0 0 0 3px rgba(30,157,139,.12)}}
.search-count{{font-size:.78em;color:#888;white-space:nowrap;flex-shrink:0}}
.no-results{{text-align:center;padding:40px;color:#aaa;font-size:.9em;display:none}}
.cat-item.generating{{opacity:1;pointer-events:none}}
.cat-item-progress{{display:flex;align-items:center;gap:7px;flex:1;min-width:0}}
.cip-spinner{{width:13px;height:13px;border:2px solid #d8f3dc;border-top-color:#1e9d8b;
  border-radius:50%;flex-shrink:0;animation:cip-spin .7s linear infinite}}
@keyframes cip-spin{{to{{transform:rotate(360deg)}}}}
.cip-bar-track{{flex:1;height:6px;background:#eef0f6;border-radius:3px;overflow:hidden;min-width:0}}
.cip-bar-fill{{height:100%;width:0%;background:#1e9d8b;border-radius:3px;transition:width .3s ease}}
.cip-pct{{font-size:.72em;font-weight:700;color:#1e9d8b;min-width:2.8em;text-align:left;flex-shrink:0}}
</style>
</head>
<body>
<button class="ham-btn" id="ham-btn" onclick="toggleNav()" aria-label="תפריט">
  <svg width="18" height="14" viewBox="0 0 18 14" fill="none">
    <rect width="18" height="2" rx="1" fill="currentColor"/>
    <rect y="6" width="18" height="2" rx="1" fill="currentColor"/>
    <rect y="12" width="18" height="2" rx="1" fill="currentColor"/>
  </svg>
</button>
<div class="nav-overlay" id="nav-overlay" onclick="toggleNav()"></div>
<nav class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <span class="sidebar-app-name">Menu</span>
    <button class="sidebar-close-btn" onclick="closeNav()" aria-label="סגור תפריט">✕</button>
  </div>
  <div class="sidebar-scroll">
    <a class="nav-item" href="/monthly" onclick="try{{var k=localStorage.getItem('lv_month');if(k){{event.preventDefault();location.href='/general/'+k;}}}}catch(_){{}}">ניתוח חודשי</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/accounts">חשבונות</a>
    <a class="nav-item" href="/housing">דיור</a>
    <a class="nav-item" href="/organizer">ארגונית</a>
    <a class="nav-item" href="/bills">מעקב חשבונות</a>
    <a class="nav-item active" href="/categories">ניתוח קטגוריאלי</a>
    <a class="nav-item" href="/search">חיפוש</a>
    <a class="nav-item" href="/spotify">Spotify Tracker</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/tagger">תייגן</a>
    <a class="nav-item" href="/files">קבצים</a>
  </div>
  <div class="sidebar-footer" style="padding:12px 16px;border-top:1px solid #eef0f6;flex-shrink:0">
    <div id="app-version-badge-1" style="text-align:center;font-size:.7em;color:#b0bec5;margin-bottom:8px;letter-spacing:.03em;">v—</div>
    <button onclick="restartServer(this)" style="width:100%;padding:8px 12px;border:1.5px dashed #eef0f6;border-radius:8px;background:none;color:#888;font-size:.78em;font-weight:600;cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:7px;justify-content:center;transition:background .15s,color .15s,border-color .15s" onmouseover="this.style.background='#fff3f3';this.style.color='#e53935';this.style.borderColor='#e53935'" onmouseout="this.style.background='none';this.style.color='#888';this.style.borderColor='#eef0f6'">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg>
      הפעל שרת מחדש
    </button>
  </div>
</nav>
<div class="main">
  <div class="page-header"><h1>ניתוח קטגוריות ועסקים</h1></div>
  <div class="search-wrap">
    <input class="cat-search" id="cat-search" type="text" placeholder="חיפוש קטגוריה או עסק..." oninput="filterCats(this.value)">
    <span class="search-count" id="search-count">{total} פריטים</span>
  </div>
  <div class="grid" id="cat-grid">{items_html}</div>
  <div class="no-results" id="no-results">לא נמצאו תוצאות תואמות</div>
</div>
{_log_float_html()}
<script>
{_log_float_js()}
// Intercept clicks on not-yet-generated items: run the analysis inline
// instead of navigating away to a separate loading page. Progress is
// surfaced through the app's single main logger window (the same
// debug-fab/debug-panel + /api/debug-logs stream every other page uses —
// print() output from the analysis is already tee'd there automatically),
// not a bespoke popup. Already-generated items fall through to the normal
// <a href> navigation.
function openDebugPanel() {{
  var panel = document.getElementById('debug-panel');
  if (panel && !panel.classList.contains('open')) toggleDebugPanel();
}}
function _dbgLine(text, cls) {{
  var feed = document.getElementById('debug-feed');
  if (!feed) return;
  var el = document.createElement('div');
  el.className = 'debug-line' + (cls ? ' ' + cls : '');
  el.textContent = text;
  feed.appendChild(el);
  feed.scrollTop = feed.scrollHeight;
}}
function _catProgressShow(el) {{
  var badge = el.querySelector('.cat-item-badge');
  if (badge) badge.style.display = 'none';
  var prog = document.createElement('div');
  prog.className = 'cat-item-progress';
  prog.innerHTML = '<span class="cip-spinner"></span><div class="cip-bar-track"><div class="cip-bar-fill"></div></div><span class="cip-pct">0%</span>';
  el.appendChild(prog);
}}
function _catProgressSet(el, pct) {{
  var fill = el.querySelector('.cip-bar-fill');
  var pctEl = el.querySelector('.cip-pct');
  if (fill) fill.style.width = pct + '%';
  if (pctEl) pctEl.textContent = pct + '%';
}}
function _catProgressHide(el) {{
  var prog = el.querySelector('.cat-item-progress');
  if (prog) prog.remove();
  var badge = el.querySelector('.cat-item-badge');
  if (badge) badge.style.display = '';
}}
var _catStreamSlug = null;
function handleCatClick(event, el) {{
  if (el.dataset.has === '1') return true;
  event.preventDefault();
  if (_catStreamSlug) return false;  // a regen is already running client-side
  var slug = el.dataset.slug, type = el.dataset.type, name = el.dataset.name;
  _catStreamSlug = slug;
  el.classList.add('generating');
  _catProgressShow(el);
  openDebugPanel();
  _dbgLine('▸ מריץ ניתוח: ' + name + '…');
  var qs = '?slug=' + encodeURIComponent(slug) + '&type=' + encodeURIComponent(type) + '&name=' + encodeURIComponent(name);
  var es = new EventSource('/api/category/stream' + qs);
  function _stop() {{
    clearTimeout(tid); es.close(); _catStreamSlug = null;
    el.classList.remove('generating'); _catProgressHide(el);
  }}
  var tid = setTimeout(function() {{
    if (es.readyState !== EventSource.CLOSED) {{
      _stop();
      _dbgLine('✗ תם הזמן — נסה שוב', 'err');
    }}
  }}, 300000);
  es.onmessage = function(e) {{
    if (!e.data || e.data === '__CONNECTED__') return;
    if (e.data.indexOf('__PROGRESS__:') === 0) {{
      var pct = parseInt(e.data.slice('__PROGRESS__:'.length), 10);
      if (!isNaN(pct)) _catProgressSet(el, pct);
      return;
    }}
    if (e.data.indexOf('__DONE__') === 0) {{
      _catProgressSet(el, 100);
      _stop();
      _dbgLine('✓ הניתוח הסתיים — טוען…', 'ok');
      setTimeout(function() {{ location.href = '/category/' + slug; }}, 400);
      return;
    }}
    if (e.data.indexOf('__ERROR__') === 0) {{
      _stop();
      var msg = e.data === '__ERROR__:busy' ? 'ניתוח אחר כבר רץ — נסה שוב בעוד רגע'
        : e.data.length > '__ERROR__:'.length ? e.data.slice('__ERROR__:'.length)
        : 'שגיאה בניתוח — פרטים למעלה';
      _dbgLine('✗ ' + msg, 'err');
      return;
    }}
    // regular progress lines already arrive via /api/debug-logs (same tee as
    // every other page) — no need to duplicate them here.
  }};
  es.onerror = function() {{
    _stop();
    _dbgLine('✗ החיבור נותק', 'err');
  }};
  return false;
}}
function restartServer(btn){{btn.disabled=true;btn.innerHTML='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg> מפעיל מחדש…';fetch('/api/restart',{{method:'POST'}}).catch(function(){{}}).finally(function(){{var t=setInterval(function(){{fetch('/').then(function(r){{if(r.ok){{clearInterval(t);location.reload();}}}}).catch(function(){{}});}},800);}});}}
function openNav(){{var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.add('open');o.classList.add('open');b.classList.add('open');}}
function closeNav(){{var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.remove('open');o.classList.remove('open');b.classList.remove('open');}}
function toggleNav(){{document.getElementById('sidebar').classList.contains('open')?closeNav():openNav();}}
document.addEventListener('keydown',function(e){{if(e.key==='Escape')closeNav();}});
fetch('/api/version').then(function(r){{return r.json();}}).then(function(d){{var b=document.getElementById('app-version-badge-1');if(b&&d.version)b.textContent='v'+d.version;}}).catch(function(){{}});
function filterCats(q) {{
  q = q.trim().toLowerCase();
  var items = document.querySelectorAll('.cat-item');
  var visible = 0;
  items.forEach(function(el) {{
    var name = (el.dataset.name || '').toLowerCase();
    var match = !q || name.indexOf(q) !== -1;
    el.style.display = match ? '' : 'none';
    if (match) visible++;
  }});
  document.getElementById('search-count').textContent = visible + ' פריטים';
  document.getElementById('no-results').style.display = (visible === 0 && q) ? '' : 'none';
}}
</script>
</body>
</html>'''


@app.route('/category/<path:slug>')
def serve_category(slug):
    html_path = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
    if os.path.exists(html_path):
        return send_file(html_path)
    # Auto-trigger generation — pass original name (from query param) so special
    # chars (חו"ל, השקעה/חיסכון) are preserved in the analysis request
    name = request.args.get('name', '')
    return _not_generated_category_html(slug, name=name)


@app.route('/api/category/list')
def category_list():
    from database import DataBase
    from datetime import datetime as _dt
    cats = DataBase().get_all_category_names() or []
    bizs = DataBase().get_all_business_names() or []
    result = []
    for name in sorted(cats):
        slug  = _make_slug('cat', name)
        fpath = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
        has   = os.path.exists(fpath)
        result.append({
            'slug': slug, 'name': name, 'type': 'category', 'hasFile': has,
            'generated': _dt.fromtimestamp(os.path.getmtime(fpath)).strftime('%d/%m/%Y %H:%M') if has else None
        })
    for name in sorted(bizs):
        slug  = _make_slug('biz', name)
        fpath = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
        has   = os.path.exists(fpath)
        result.append({
            'slug': slug, 'name': name, 'type': 'business', 'hasFile': has,
            'generated': _dt.fromtimestamp(os.path.getmtime(fpath)).strftime('%d/%m/%Y %H:%M') if has else None
        })
    return jsonify(result)


@app.route('/api/category/run', methods=['POST'])
def run_category():
    global _analysis_running

    with _analysis_lock:
        if _analysis_running:
            return jsonify({'status': 'busy', 'message': 'ניתוח כבר רץ'}), 409
        _analysis_running = True

    while not _log_queue.empty():
        try: _log_queue.get_nowait()
        except queue.Empty: break

    body = request.get_json() or {}
    slug = body.get('slug', '')
    type_ = body.get('type', 'category')  # 'category' | 'business'

    # Derive name: prefer explicit name from client, then verify against the real DB list.
    # The slug→name fallback is lossy (special chars like " and / become spaces), so we
    # cross-check against all known names and pick an exact slug match if found.
    prefix = 'cat_' if type_ == 'category' else 'biz_'
    client_name = (body.get('name') or '').strip()
    try:
        from database import DataBase as _DB
        all_names = (_DB().get_all_category_names() if type_ == 'category'
                     else _DB().get_all_business_names()) or []
        # Find the name whose slug matches exactly
        matched = next((n for n in all_names if _make_slug(prefix.rstrip('_'), n) == slug), None)
        name = matched or client_name or (slug[len(prefix):].replace('_', ' ') if slug.startswith(prefix) else slug)
    except Exception:
        name = client_name or (slug[len(prefix):].replace('_', ' ') if slug.startswith(prefix) else slug)

    def _worker():
        global _analysis_running
        try:
            from AppManager import AppManager

            def _do():
                if type_ == 'category':
                    AppManager(skip_parser=True).category_analysis(category=name)
                else:
                    AppManager(skip_parser=True).category_analysis(business=name)

            deps, db_mtime = _capture_deps_and_run(_do)

            html_path = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
            if os.path.exists(html_path):
                _save_manifest(html_path, deps, db_mtime)

            _log_queue.put(f'__DONE__:{slug}')
        except Exception as exc:
            import traceback
            _log_error(exc, traceback.format_exc())
            _log_queue.put('__ERROR__')
        finally:
            with _analysis_lock:
                _analysis_running = False

    threading.Thread(target=_worker, daemon=True, name='cat-analysis-worker').start()
    return jsonify({'status': 'started'})


@app.route('/api/category/stream')
def run_category_stream():
    """SSE endpoint: runs category analysis inline so thread + stream share the same invocation."""
    global _analysis_running
    slug        = request.args.get('slug', '')
    type_val    = request.args.get('type', 'category')
    client_name = (request.args.get('name') or '').strip()

    with _analysis_lock:
        if _analysis_running:
            def _busy():
                yield 'data: __ERROR__:busy\n\n'
            return Response(_busy(), mimetype='text/event-stream',
                            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
        _analysis_running = True

    prefix = 'cat_' if type_val == 'category' else 'biz_'
    try:
        from database import DataBase as _DB
        all_names = (_DB().get_all_category_names() if type_val == 'category'
                     else _DB().get_all_business_names()) or []
        matched = next((n for n in all_names if _make_slug(prefix.rstrip('_'), n) == slug), None)
        name = matched or client_name or (slug[len(prefix):].replace('_', ' ') if slug.startswith(prefix) else slug)
    except Exception:
        name = client_name or (slug[len(prefix):].replace('_', ' ') if slug.startswith(prefix) else slug)

    local_q: queue.Queue = queue.Queue()
    _regen_tracker.init(slug)
    _regen_tracker.set_callback(slug, lambda pct: local_q.put(f'__PROGRESS__:{pct}'))

    def _worker():
        global _analysis_running
        _thread_log_queue.queue = local_q
        try:
            from AppManager import AppManager
            def _do():
                if type_val == 'category':
                    AppManager(skip_parser=True).category_analysis(category=name, page_id=slug)
                else:
                    AppManager(skip_parser=True).category_analysis(business=name, page_id=slug)
            deps, db_mtime = _capture_deps_and_run(_do)
            html_path = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
            if os.path.exists(html_path):
                _save_manifest(html_path, deps, db_mtime)
            _regen_tracker.done(slug)
            local_q.put(f'__DONE__:{slug}')
        except Exception as exc:
            import traceback
            _log_error(exc, traceback.format_exc())
            # Carry the exception summary on the message itself so the client can
            # show something useful immediately, instead of relying on the
            # separate /api/debug-logs stream (a different SSE connection) to have
            # already delivered the full traceback by the time this arrives.
            local_q.put(f'__ERROR__:{type(exc).__name__}: {str(exc)[:200]}')
        finally:
            with _analysis_lock:
                _analysis_running = False
            _regen_tracker.clear_callback(slug)

    threading.Thread(target=_worker, daemon=True, name='cat-stream-worker').start()

    def _generate():
        yield 'data: __CONNECTED__\n\n'
        while True:
            try:
                msg = local_q.get(timeout=25)
            except queue.Empty:
                yield 'data: \n\n'
                continue
            safe = msg.replace('\r\n', '↵').replace('\n', '↵').replace('\r', '↵')
            yield f'data: {safe}\n\n'
            if msg.startswith('__DONE__') or msg.startswith('__ERROR__'):
                break

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )



def _log_float_style() -> str:
    return """<style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0faf5;
           min-height: 100vh; display: flex; align-items: center;
           justify-content: center; padding: 16px; }
    .box { background: #fff; border-radius: 20px; padding: 28px 22px 22px;
           text-align: center; box-shadow: 0 4px 28px rgba(52,184,136,.13);
           max-width: 460px; width: 100%; }
    h2   { color: #1e2a4a; margin-bottom: 6px; font-size: 1.15em; font-weight:700; }
    p    { color: #6b8c7a; font-size: .84em; margin-bottom: 20px; }
    .badge { display:inline-block; background:#d8f3dc; color:#2d6a4f; border-radius:99px;
             padding:4px 16px; font-size:.8em; font-weight:600; margin-bottom:12px; }
    .back { margin-top:18px; font-size:.8em; }
    .back a { color:#52b788; text-decoration:none; }
    .back a:hover { color:#1e9d8b; }
    /* ── floating log panel (used by category regen page) ── */
    .log-float { position:fixed; bottom:20px; left:50%;
                 transform:translateX(-50%) translateY(16px);
                 width:460px; max-width:calc(100vw - 24px);
                 background:#fff; border:1px solid #d8f3dc;
                 border-radius:14px; padding:0;
                 opacity:0; pointer-events:none;
                 transition:opacity .3s, transform .3s;
                 z-index:9999;
                 box-shadow:0 4px 20px rgba(52,184,136,.15); }
    .log-float.visible { opacity:1; pointer-events:auto; transform:translateX(-50%) translateY(0); }
    .lf-header { padding:8px 12px; background:#f0faf5;
                 border-bottom:1px solid #d8f3dc; border-radius:14px 14px 0 0;
                 display:flex; align-items:center; gap:6px; }
    .lf-title { font-size:.72em; font-weight:600; color:#52b788; letter-spacing:.03em; }
    .lf-feed { display:flex; flex-direction:column; max-height:160px;
               overflow-y:auto; gap:1px; padding:8px 12px;
               scrollbar-width:thin; scrollbar-color:#b7e4c7 transparent; }
    .lf-feed::-webkit-scrollbar { width:3px; }
    .lf-feed::-webkit-scrollbar-thumb { background:#b7e4c7; border-radius:2px; }
    .lf-line { font-size:.74em; font-family:'Consolas','Courier New',monospace;
               padding:1px 0; white-space:pre-wrap; word-break:break-word;
               line-height:1.55; color:#3d6b55; direction:ltr; text-align:left; }
    .lf-line.warn { color:#8a6200; }
    .lf-line.err  { color:#b83232; font-weight:500; }
    .lf-line.done { color:#1e7a50; font-weight:600; }
    /* ── debug FAB + panel ── */
    .debug-fab { position:fixed; bottom:22px; right:18px; width:42px; height:42px;
                 border-radius:50%; background:#1e2a4a; color:#fff; font-size:.72em;
                 font-family:monospace; font-weight:700; border:none; cursor:pointer;
                 display:flex; align-items:center; justify-content:center;
                 box-shadow:0 4px 14px rgba(0,0,0,.3); z-index:997; letter-spacing:-.5px; }
    .debug-fab:hover { filter:brightness(1.2); }
    .debug-panel { position:fixed; bottom:72px; right:16px; width:480px;
                   max-width:calc(100vw - 32px); height:340px; background:#12121f;
                   border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,.55);
                   z-index:996; display:none; flex-direction:column; overflow:hidden;
                   font-family:monospace; }
    .debug-panel.open { display:flex; }
    .debug-hdr { display:flex; align-items:center; justify-content:space-between;
                 padding:7px 12px; background:#0a0a18; color:#7ec8e3; font-size:.7em;
                 font-weight:700; letter-spacing:.06em; flex-shrink:0;
                 border-bottom:1px solid #222; }
    .debug-hdr-btns { display:flex; gap:5px; }
    .debug-hdr-btns button { background:none; border:1px solid #333; color:#888;
                              border-radius:4px; padding:2px 8px; font-size:.9em;
                              cursor:pointer; font-family:monospace; }
    .debug-hdr-btns button:hover { background:#1e1e2e; color:#eee; }
    .debug-feed { flex:1; overflow-y:auto; padding:6px 10px; font-size:.68em;
                  line-height:1.55; color:#c8d8e4; }
    .debug-line { white-space:pre-wrap; word-break:break-all; padding:1px 0;
                  border-bottom:1px solid #1a1a2a; }
    .debug-line.err  { color:#ff6b6b; }
    .debug-line.warn { color:#ffa94d; }
    .debug-line.ok   { color:#69db7c; }
    /* ── CC-charge confirmation modal ── */
    .cc-modal-overlay { position:fixed; inset:0; background:rgba(15,22,45,.55);
                        z-index:10000; display:flex; align-items:center; justify-content:center; }
    .cc-modal { background:#fff; border-radius:14px; padding:28px 32px; max-width:420px; width:90%;
                box-shadow:0 12px 40px rgba(0,0,0,.2); text-align:right; direction:rtl; }
    .cc-modal-title { font-size:1em; font-weight:700; color:#1e2a4a; margin-bottom:12px; }
    .cc-modal-body  { font-size:.85em; color:#555; margin-bottom:18px; line-height:1.6; }
    .cc-modal-row   { display:flex; justify-content:space-between; padding:4px 0;
                      border-bottom:1px solid #eef0f6; font-size:.83em; }
    .cc-modal-row:last-child { border-bottom:none; }
    .cc-modal-label { color:#888; }
    .cc-modal-val   { font-weight:600; color:#1e2a4a; }
    .cc-modal-btns  { display:flex; gap:10px; justify-content:flex-end; margin-top:18px; }
    .cc-btn { border:none; border-radius:8px; padding:8px 22px; font-size:.88em;
              font-weight:600; cursor:pointer; transition:background .15s; font-family:inherit; }
    .cc-btn-yes { background:#1e9d8b; color:#fff; }
    .cc-btn-yes:hover { background:#189080; }
    .cc-btn-no  { background:#f0f2f6; color:#555; }
    .cc-btn-no:hover  { background:#e2e5ed; }
    </style>"""


def _log_float_html() -> str:
    return """<div class="log-float" id="log-float">
  <div class="lf-header">
    <span class="lf-title" id="lf-title">מנתח נתונים…</span>
  </div>
  <div class="lf-feed" id="lf-feed"></div>
</div>
<button class="debug-fab" id="debug-fab" onclick="toggleDebugPanel()" title="App logs">&lt;/&gt;</button>
<div class="debug-panel" id="debug-panel">
  <div class="debug-hdr">
    <span>▸ app logs</span>
    <div class="debug-hdr-btns">
      <button onclick="clearDebugPanel()">clear</button>
      <button onclick="toggleDebugPanel()">✕</button>
    </div>
  </div>
  <div class="debug-feed" id="debug-feed"></div>
</div>
<div id="cc-modal-overlay" class="cc-modal-overlay" style="display:none">
  <div class="cc-modal">
    <div class="cc-modal-title">🏦 עסקת אשראי זוהתה</div>
    <div class="cc-modal-body">האפליקציה מצאה עסקה בחשבון הבנק שעשויה להיות חיוב כרטיס אשראי. האם לסווג אותה כ&quot;אשראי&quot;?</div>
    <div id="cc-modal-rows"></div>
    <div class="cc-modal-btns">
      <button class="cc-btn cc-btn-no"  onclick="ccRespond(false)">לא — דלג</button>
      <button class="cc-btn cc-btn-yes" onclick="ccRespond(true)">כן — אשר</button>
    </div>
  </div>
</div>"""


def _log_float_js() -> str:
    return """var _LF_MAX = 80;
    function showLogFloat(title) {
      document.getElementById('lf-feed').innerHTML = '';
      document.getElementById('lf-title').textContent = title || 'מנתח נתונים…';
      document.getElementById('log-float').classList.add('visible');
    }
    function hideLogFloat(delay) {
      setTimeout(function() {
        document.getElementById('log-float').classList.remove('visible');
      }, delay || 0);
    }
    function appendLog(text, cls) {
      var feed = document.getElementById('lf-feed');
      if (!feed) return;
      var el = document.createElement('div');
      el.className = 'lf-line' + (cls ? ' ' + cls : '');
      el.textContent = text;
      feed.appendChild(el);
      while (feed.children.length > _LF_MAX) feed.removeChild(feed.firstChild);
      feed.scrollTop = feed.scrollHeight;
    }
    function showCCPrompt(txData) {
      var labels = {ID:'מזהה', Date:'תאריך', Name:'שם', Out:'סכום', Category:'קטגוריה', Description:'תיאור'};
      var rows = document.getElementById('cc-modal-rows');
      if (!rows) return;
      var html = '';
      ['Name','Date','Out','Description','ID'].forEach(function(k) {
        if (txData[k] != null && txData[k] !== '' && txData[k] !== 'nan') {
          html += '<div class="cc-modal-row"><span class="cc-modal-label">' + (labels[k]||k) + '</span>' +
                  '<span class="cc-modal-val">' + String(txData[k]).replace(/</g,'&lt;') + '</span></div>';
        }
      });
      rows.innerHTML = html;
      var ov = document.getElementById('cc-modal-overlay');
      if (ov) ov.style.display = 'flex';
    }
    function ccRespond(choice) {
      var ov = document.getElementById('cc-modal-overlay');
      if (ov) ov.style.display = 'none';
      fetch('/api/analysis/respond', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({choice: choice})
      }).catch(function(){});
    }
    /* ── debug panel ── */
    var _dbgEs = null;
    function toggleDebugPanel() {
      var panel = document.getElementById('debug-panel');
      var isOpen = panel.classList.toggle('open');
      if (isOpen && !_dbgEs) _startDebugStream();
    }
    function clearDebugPanel() {
      document.getElementById('debug-feed').innerHTML = '';
    }
    function _startDebugStream() {
      _dbgEs = new EventSource('/api/debug-logs');
      _dbgEs.onmessage = function(e) {
        if (!e.data || !e.data.trim()) return;
        var feed = document.getElementById('debug-feed');
        if (!feed) return;
        var line = document.createElement('div');
        line.className = 'debug-line';
        var t = e.data;
        if (/error|exception|traceback|critical/i.test(t)) line.classList.add('err');
        else if (/warn|warning/i.test(t)) line.classList.add('warn');
        else if (/done|success|ok|✓/i.test(t)) line.classList.add('ok');
        line.textContent = t;
        feed.appendChild(line);
        feed.scrollTop = feed.scrollHeight;
        while (feed.children.length > 600) feed.removeChild(feed.firstChild);
      };
      _dbgEs.onerror = function() {
        if (_dbgEs) { _dbgEs.close(); _dbgEs = null; }
        var panel = document.getElementById('debug-panel');
        if (panel && panel.classList.contains('open')) {
          setTimeout(_startDebugStream, 3000);
        }
      };
    }"""


def _not_generated_category_html(slug: str, name: str = '') -> str:
    import json as _json
    slug_js  = _json.dumps(slug)
    type_val = 'category' if slug.startswith('cat_') else 'business'
    type_js  = _json.dumps(type_val)
    name_js  = _json.dumps(name, ensure_ascii=False)
    return f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<title>BankApp — טוען</title>
{_log_float_style()}
</head>
<body>
<div class="box">
  <h2>ניתוח קטגוריה</h2>
  <p>מפעיל ניתוח אוטומטי…</p>
  <div class="back"><a href="/categories">&#8592; חזרה לרשימה</a></div>
</div>
{_log_float_html()}
<script>
{_log_float_js()}
  (function() {{
    showLogFloat('מנתח קטגוריה…');
    var _qs = '?slug=' + encodeURIComponent({slug_js}) +
              '&type=' + encodeURIComponent({type_js}) +
              '&name=' + encodeURIComponent({name_js});
    var es = new EventSource('/api/category/stream' + _qs);
    var _tid = setTimeout(function() {{
      if (es.readyState !== EventSource.CLOSED) {{
        es.close();
        appendLog('✗ תם הזמן — נסה לרענן', 'err');
      }}
    }}, 300000);
    es.onmessage = function(e) {{
      if (!e.data || e.data === '__CONNECTED__') return;
      if (e.data.indexOf('__PROGRESS__:') === 0) {{
        var pct = parseInt(e.data.slice('__PROGRESS__:'.length), 10);
        if (!isNaN(pct)) document.getElementById('lf-title').textContent = 'מנתח קטגוריה… ' + pct + '%';
        return;
      }}
      if (e.data.startsWith('__DONE__')) {{
        clearTimeout(_tid); es.close();
        appendLog('✓ הניתוח הסתיים — טוען…', 'done');
        hideLogFloat(900);
        setTimeout(function() {{ location.href = '/category/' + {slug_js}; }}, 1100);
        return;
      }}
      if (e.data.indexOf('__ERROR__') === 0) {{
        clearTimeout(_tid); es.close();
        var msg = e.data === '__ERROR__:busy' ? 'ניתוח אחר כבר רץ — נסה שוב בעוד רגע'
          : e.data.length > '__ERROR__:'.length ? e.data.slice('__ERROR__:'.length)
          : 'שגיאה בניתוח';
        appendLog('✗ ' + msg, 'err');
        hideLogFloat(3000);
        return;
      }}
      appendLog(e.data);
    }};
    es.onerror = function() {{
      clearTimeout(_tid); es.close();
      appendLog('✗ החיבור נותק', 'err');
      hideLogFloat(3000);
    }};
  }})();
</script>
</body>
</html>'''


_READONLY_ACCOUNTS = ["נכס שלום שבזי"]
_DB_PATH = os.path.join(_PROJECT_DIR, 'ShmuelFamiliy.db')
# When running on Vercel the project dir (/var/task) is read-only;
# direct sqlite3.connect(_DB_PATH) calls need a writable path.
if os.getenv('VERCEL'):
    _DB_PATH = '/tmp/ShmuelFamiliy.db'
    # Copy personal information files to /tmp so they are writable.
    # The project dir (/var/task) is read-only on Vercel; any json.dump to
    # personal information/*.json would raise OSError errno 30.
    import shutil as _shutil
    _TMP_PERSONAL = '/tmp/personal information'
    os.makedirs(_TMP_PERSONAL, exist_ok=True)
    for _fname in ('personal_config.json', 'categories.json', 'auto_tagger.json', 'currency.json'):
        _src = os.path.join(_PROJECT_DIR, 'personal information', _fname)
        _dst = os.path.join(_TMP_PERSONAL, _fname)
        if os.path.exists(_src) and not os.path.exists(_dst):
            _shutil.copy2(_src, _dst)
    # Patch Constants.Paths so every module reads/writes the /tmp copies.
    from Constants import Paths as _Paths
    _Paths.PERSONAL_CONFIG  = os.path.join(_TMP_PERSONAL, 'personal_config.json')
    _Paths.CATEGORY_JSON    = os.path.join(_TMP_PERSONAL, 'categories.json')
    _Paths.AUTO_TAGGER_JSON = os.path.join(_TMP_PERSONAL, 'auto_tagger.json')
    _Paths.Currency_JSON    = os.path.join(_TMP_PERSONAL, 'currency.json')
    # Redirect all generated-HTML output dirs to /tmp (project dir is read-only).
    GENERAL_ANALYSIS_DIR  = '/tmp/general_analysis'
    CATEGORY_ANALYSIS_DIR = '/tmp/category_analysis'
    OUTPUT_HTML           = '/tmp/output.html'
    os.makedirs(GENERAL_ANALYSIS_DIR, exist_ok=True)
    os.makedirs(CATEGORY_ANALYSIS_DIR, exist_ok=True)


class _PGConn:
    """Thin wrapper around psycopg2 connection that mimics sqlite3's conn.execute() API."""

    def __init__(self, raw_conn, pool=None):
        import psycopg2.extras
        self._conn = raw_conn
        self._pool = pool
        self._factory = psycopg2.extras.DictCursor

    def _sql(self, sql):
        return sql.replace('?', '%s').replace(
            'INSERT OR IGNORE INTO', 'INSERT INTO'
        ).replace('ON CONFLICT NOTHING', 'ON CONFLICT DO NOTHING')

    def execute(self, sql, params=()):
        sql = self._sql(sql)
        cur = self._conn.cursor(cursor_factory=self._factory)
        cur.execute(sql, params)
        return cur

    def commit(self):   self._conn.commit()
    def rollback(self): self._conn.rollback()

    def close(self):
        if self._pool is None:
            self._conn.close()
            return
        broken = bool(self._conn.closed)
        if not broken:
            try:
                self._conn.rollback()  # reset any open transaction before returning
            except Exception:
                broken = True
        try:
            self._pool.putconn(self._conn, close=broken)
        except Exception:
            try: self._conn.close()
            except Exception: pass

    def cursor(self):
        import psycopg2.extras
        return self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)


# ── Persistent Postgres connection pool ───────────────────────────────────────
_pg_pool      = None
_pg_pool_lock = _threading.Lock()

def _get_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    with _pg_pool_lock:
        if _pg_pool is None:
            import psycopg2.pool
            _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1, maxconn=10,
                dsn=os.environ.get('DATABASE_URL', ''),
                connect_timeout=10,
            )
    return _pg_pool


def _pg_conn():
    """Return a _PGConn backed by a pooled connection — no new TCP handshake per request."""
    import psycopg2
    pool = _get_pg_pool()
    raw  = pool.getconn()
    if raw.closed:
        # Stale slot — discard and open a fresh one
        pool.putconn(raw, close=True)
        raw = pool.getconn()
    raw.autocommit = False
    return _PGConn(raw, pool=pool)


def _get_latest_yyyy_mm():
    """Return the latest month key (e.g. '2026_05') that has data in the DB.

    Check order: (1) filesystem HTML files, (2) in-memory API cache,
    (3) DB MAX(Date) query — so this works both locally and on Vercel.
    """
    from datetime import datetime as _dt
    import logging as _log

    # 1. Filesystem (populated locally when HTML output is generated)
    if os.path.isdir(GENERAL_ANALYSIS_DIR):
        files = sorted(
            f for f in os.listdir(GENERAL_ANALYSIS_DIR)
            if _re.match(r'^\d{4}_\d{2}\.html$', f)
        )
        if files:
            return files[-1].replace('.html', '')

    # 2. In-memory API cache (populated after the first data request)
    if _monthly_data_cache:
        return max(_monthly_data_cache.keys())

    # 3. DB query fallback (works on Vercel / API-first)
    try:
        if os.getenv('DATABASE_URL'):
            conn = _pg_conn()
            try:
                row = conn.execute("SELECT MAX(Date) FROM BankTransactions").fetchone()
            finally:
                conn.close()
        else:
            from database import DataBase
            row = DataBase().cursor.execute(
                "SELECT MAX(Date) FROM BankTransactions"
            ).fetchone()
        if row and row[0]:
            d_str = str(row[0])[:10]
            d = _dt.strptime(d_str, '%Y-%m-%d')
            return f'{d.year:04d}_{d.month:02d}'
    except Exception as _e:
        _log.getLogger(__name__).warning('_get_latest_yyyy_mm DB query failed: %s', _e)

    return None


def _acct_db():
    """Open a fresh connection to the main PostgreSQL DB."""
    return _pg_conn()


def _run_acct_migrations():
    """One-time DDL migrations for OtherAccountStatus. Called once at startup."""
    try:
        conn = _pg_conn()
        try:
            conn.execute("ALTER TABLE OtherAccountStatus ADD COLUMN IF NOT EXISTS Currency TEXT NOT NULL DEFAULT 'ILS'")
            conn.commit()
        except Exception:
            conn.rollback()
        try:
            conn.execute("ALTER TABLE OtherAccountStatus ADD COLUMN IF NOT EXISTS Source TEXT")
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()
    except Exception:
        pass


def _run_tagger_migrations():
    """One-time DDL migrations for tag-timestamp tracking. Called once at startup."""
    try:
        conn = _pg_conn()
        for tbl in ('BankTransactions', 'CardTransactions'):
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS Tagged_At TIMESTAMP")
                conn.commit()
            except Exception:
                conn.rollback()
        conn.close()
    except Exception:
        pass


# ── Exchange-rate cache (background refresh, never blocks a request) ──────────
_fx_cache   = {'ILS': 1.0, 'USD': 3.72, 'EUR': 4.01, 'JPY': 0.025}  # always valid
_fx_fetched = 0.0  # epoch seconds of last successful remote fetch (0 = only fallback)

def _get_fx_rates():
    """Return cached rates instantly — never blocks."""
    return _fx_cache

def _fx_refresh_loop():
    """Background daemon: fetch fresh rates every hour, update cache on success."""
    import time, urllib.request, json as _json
    global _fx_cache, _fx_fetched
    while True:
        try:
            url = 'https://api.exchangerate-api.com/v4/latest/ILS'
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = _json.loads(resp.read())
            ils_to_x = data.get('rates', {})
            if ils_to_x:
                new_cache = {cur: 1.0 / rate for cur, rate in ils_to_x.items() if rate}
                new_cache['ILS'] = 1.0
                _fx_cache   = new_cache
                _fx_fetched = time.time()
        except Exception:
            pass  # keep whatever cache we already have
        time.sleep(3600)

_threading.Thread(target=_fx_refresh_loop, daemon=True, name='fx-refresh').start()


@app.route('/api/accounts/names')
def accounts_names():
    conn = _acct_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT AccountName FROM OtherAccountStatus"
        ).fetchall()
        names = [r[0] for r in rows if r[0] not in _READONLY_ACCOUNTS]
        return jsonify({'names': names})
    finally:
        conn.close()


@app.route('/api/accounts/status', methods=['POST'])
def accounts_add_status():
    from datetime import datetime as _dt
    body     = request.get_json() or {}
    name     = (body.get('name')     or '').strip()
    date     = (body.get('date')     or '').strip()
    value    = body.get('value')
    currency = (body.get('currency') or 'ILS').strip().upper()
    if currency not in ('ILS', 'USD', 'EUR', 'JPY'):
        currency = 'ILS'
    if not name or not date or value is None:
        return jsonify({'ok': False, 'error': 'missing fields'})
    try:
        _dt.strptime(date, '%Y-%m-%d')
        conn = _acct_db()
        try:
            conn.execute(
                "INSERT INTO OtherAccountStatus (AccountName, StatusDate, Value, TransactionID, Currency) VALUES (?, ?, ?, ?, ?)",
                (name, date, float(value), None, currency)
            )
            conn.commit()
        finally:
            conn.close()
        _compute_accounts()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/accounts/rates')
def accounts_rates():
    """Return today's FX rates (X→ILS) and per-account currencies."""
    rates = _get_fx_rates()
    # Also return what currency each account uses (latest entry)
    conn = _acct_db()
    try:
        rows = conn.execute(
            "SELECT AccountName, Currency FROM OtherAccountStatus "
            "WHERE (AccountName, StatusDate) IN ("
            "  SELECT AccountName, MAX(StatusDate) FROM OtherAccountStatus GROUP BY AccountName"
            ")"
        ).fetchall()
        acct_currencies = {r[0]: r[1] for r in rows}
    finally:
        conn.close()
    return jsonify({'rates': rates, 'currencies': acct_currencies})


@app.route('/api/accounts/delete', methods=['POST'])
def accounts_delete():
    body = request.get_json() or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'missing name'})
    try:
        conn = _acct_db()
        try:
            conn.execute("DELETE FROM OtherAccountStatus WHERE AccountName = ?", (name,))
            conn.commit()
        finally:
            conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/accounts/entries')
def accounts_entries():
    conn = _acct_db()
    try:
        rows = conn.execute(
            "SELECT ID, AccountName, StatusDate, Value, Currency FROM OtherAccountStatus WHERE Source IS NULL OR Source != 'auto' ORDER BY StatusDate DESC"
        ).fetchall()
        entries = [{'id': r[0], 'account': r[1], 'date': r[2], 'value': r[3], 'currency': r[4] or 'ILS'} for r in rows]
        return jsonify({'entries': entries})
    finally:
        conn.close()


@app.route('/api/accounts/entry/<int:entry_id>', methods=['DELETE'])
def accounts_delete_entry(entry_id):
    try:
        conn = _acct_db()
        try:
            conn.execute("DELETE FROM OtherAccountStatus WHERE ID = ?", (entry_id,))
            conn.commit()
        finally:
            conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


_cash_pie_cache = None  # invalidated whenever a cash write succeeds

def _invalidate_cash_cache():
    global _cash_pie_cache
    _cash_pie_cache = None


@app.route('/api/accounts/cash-by-currency')
def cash_by_currency():
    """Return current cash balance per currency, matching accumulate_cash_Balance():
       cash on hand = bank withdrawals (Out) + CashTransactions (Amount)
    """
    global _cash_pie_cache
    if _cash_pie_cache is not None:
        return jsonify({'ok': True, 'data': _cash_pie_cache, 'cached': True})

    import re as _re2
    conn = None
    try:
        _SYM = {'ILS': '₪', 'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥'}
        totals = {}   # currency_code → running balance

        conn = _pg_conn()

        # 1. Bank withdrawals — these represent cash that left the bank and is now on hand.
        #    They're ILS bank transactions tagged with the withdrawal category.
        bank_out = conn.execute(
            "SELECT SUM(Out) FROM BankTransactions WHERE Category = 'withdrawal'"
        ).fetchone()[0] or 0
        totals['ILS'] = totals.get('ILS', 0) + float(bank_out)

        # 2. CashTransactions — user-recorded cash income (+) and spending (-)
        for cur_raw, amount in conn.execute('SELECT Currency, SUM(Amount) FROM CashTransactions GROUP BY Currency').fetchall():
            m    = _re2.match(r'([A-Z]+)', (cur_raw or '').strip())
            code = m.group(1) if m else (cur_raw or 'ILS')
            totals[code] = totals.get(code, 0) + float(amount or 0)

        result = [
            {
                'currency': code,
                'symbol':   _SYM.get(code, code),
                'balance':  round(bal, 2),
            }
            for code, bal in sorted(totals.items(), key=lambda x: -abs(x[1]))
        ]
        _cash_pie_cache = result
        return jsonify({'ok': True, 'data': result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        if conn is not None:
            conn.close()


def _cash_balance_map():
    """Return {currency_code: balance} for the current cash on hand.
    Shared by cash_by_currency() and cash_reconcile()."""
    import re as _re2
    totals = {}
    conn = None
    try:
        conn = _pg_conn()
        bank_out = conn.execute("SELECT SUM(Out) FROM BankTransactions WHERE Category = 'withdrawal'").fetchone()[0] or 0
        totals['ILS'] = float(bank_out)
        for cur_raw, amount in conn.execute('SELECT Currency, SUM(Amount) FROM CashTransactions GROUP BY Currency').fetchall():
            m    = _re2.match(r'([A-Z]+)', (cur_raw or '').strip())
            code = m.group(1) if m else (cur_raw or 'ILS')
            totals[code] = totals.get(code, 0) + float(amount or 0)
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()
    return totals


@app.route('/api/accounts/data')
def accounts_data_api():
    """Serve cached accounts+meta payload for the חשבונות panel."""
    _no_cache = {'Cache-Control': 'no-store'}
    if _accounts_cache.get('data'):
        return jsonify({**_accounts_cache['data'], 'ok': True, 'cached': True}), 200, _no_cache
    disk = _load_accounts_disk()
    if disk:
        _accounts_cache['data'] = disk
        return jsonify({**disk, 'ok': True, 'cached': True}), 200, _no_cache
    try:
        data = _compute_accounts()
        return jsonify({**data, 'ok': True, 'cached': False}), 200, _no_cache
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500, _no_cache


@app.route('/api/accounts/regenerate', methods=['POST'])
def accounts_regenerate():
    """Invalidate accounts cache and recompute."""
    _no_cache = {'Cache-Control': 'no-store'}
    _accounts_cache.clear()
    try:
        if os.path.exists(_ACCOUNTS_JSON):
            os.remove(_ACCOUNTS_JSON)
    except Exception:
        pass
    try:
        data = _compute_accounts()
        return jsonify({**data, 'ok': True}), 200, _no_cache
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500, _no_cache


@app.route('/api/accounts/regen-stream')
def accounts_regen_stream():
    """SSE endpoint: recomputes accounts data with progress events."""
    _accounts_cache.clear()
    local_q: queue.Queue = queue.Queue()

    def _worker():
        def _pc(pct, msg=''):
            local_q.put(f'__ACCT_PROG__:{pct}:{msg}')
        try:
            _compute_accounts(progress_callback=_pc)
            local_q.put('__DONE__')
        except Exception as exc:
            import traceback
            _log_error(exc, traceback.format_exc())
            local_q.put('__ERROR__')

    threading.Thread(target=_worker, daemon=True, name='acct-regen-worker').start()

    def _generate():
        yield 'data: __CONNECTED__\n\n'
        while True:
            try:
                msg = local_q.get(timeout=25)
            except queue.Empty:
                yield 'data: \n\n'
                continue
            safe = msg.replace('\r\n', '↵').replace('\n', '↵').replace('\r', '↵')
            yield f'data: {safe}\n\n'
            if msg == '__DONE__' or msg.startswith('__ERROR__'):
                break

    return Response(_generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/cash/transaction', methods=['POST'])
def cash_add_transaction():
    """Add a manual cash transaction."""
    try:
        from database import DataBase as _DB
        from datetime import datetime as _dt
        body     = request.get_json(force=True) or {}
        name     = str(body.get('name', '')).strip()
        amount   = float(body.get('amount', 0))
        currency = str(body.get('currency', '')).strip()
        date_str = str(body.get('date', '')).strip()
        category = str(body.get('category', 'NotCategorized')).strip() or 'NotCategorized'
        desc     = str(body.get('description', '')).strip()
        if not name or not currency or not date_str:
            return jsonify({'ok': False, 'error': 'חסרים שדות חובה'})
        exec_date = _dt.strptime(date_str, '%Y-%m-%d')
        db = _DB()
        db.insert_Cash_Transaction(name, exec_date, amount, currency, category, desc)
        db.commit_changes()
        _invalidate_cash_cache()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/cash/monthly-history')
def cash_monthly_history_api():
    """Return accumulated cash balance (ILS) sampled at the first of each month."""
    conn = None
    try:
        import re as _re2, urllib.request as _ureq, json as _json_fx
        from datetime import date as _date, datetime as _dt

        # Live FX rates (currency → ILS multiplier)
        try:
            with _ureq.urlopen('https://api.exchangerate-api.com/v4/latest/ILS', timeout=5) as _r:
                _ils_to_x = _json_fx.loads(_r.read()).get('rates', {})
            _fx_to_ils = {c: 1.0 / r for c, r in _ils_to_x.items() if r}
            _fx_to_ils['ILS'] = 1.0
        except Exception:
            _fx_to_ils = {'ILS': 1.0, 'USD': 3.72, 'EUR': 4.01, 'JPY': 0.025}

        events = []  # [(date, ils_amount)]

        conn = _pg_conn()

        # Bank withdrawals (always ILS)
        for d_str, out_val in conn.execute("SELECT Date, Out FROM BankTransactions WHERE Category = 'withdrawal' AND Date IS NOT NULL").fetchall():
            try:
                d = _dt.strptime(str(d_str)[:10], '%Y-%m-%d').date()
                events.append((d, float(out_val or 0)))
            except Exception:
                pass

        # Manual CashTransactions
        for d_str, amount, cur_code in conn.execute("SELECT Execution_Date, Amount, Currency FROM CashTransactions").fetchall():
            try:
                d = _dt.strptime(str(d_str)[:10], '%Y-%m-%d').date()
                m = _re2.match(r'([A-Z]+)', (cur_code or '').strip())
                code = m.group(1) if m else 'ILS'
                rate = _fx_to_ils.get(code, 1.0)
                events.append((d, float(amount or 0) * rate))
            except Exception:
                pass

        if not events:
            return jsonify({'ok': True, 'data': []})

        events.sort(key=lambda x: x[0])

        # First-of-each-month date range
        today = _date.today()
        cur_m = events[0][0].replace(day=1)
        months = []
        while cur_m <= today:
            months.append(cur_m)
            if cur_m.month == 12:
                cur_m = cur_m.replace(year=cur_m.year + 1, month=1)
            else:
                cur_m = cur_m.replace(month=cur_m.month + 1)

        result = []
        ev_idx = 0
        cumulative = 0.0
        for m in months:
            while ev_idx < len(events) and events[ev_idx][0] < m:
                cumulative += events[ev_idx][1]
                ev_idx += 1
            result.append({'date': m.strftime('%Y-%m-%d'), 'balance': round(cumulative, 2)})

        # Final point — today's complete balance
        while ev_idx < len(events):
            cumulative += events[ev_idx][1]
            ev_idx += 1
        result.append({'date': today.strftime('%Y-%m-%d'), 'balance': round(cumulative, 2)})

        return jsonify({'ok': True, 'data': result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/cash/reconcile', methods=['POST'])
def cash_reconcile():
    """Create filler cash transactions to close the gap between recorded and actual balance."""
    try:
        from database import DataBase as _DB
        from datetime import datetime as _dt
        from Constants import ReservedNames
        body    = request.get_json(force=True) or {}
        entries = body.get('entries', [])
        totals  = _cash_balance_map()
        created = 0
        details = []
        db = _DB()
        for entry in entries:
            code   = str(entry.get('currency', '')).strip()
            actual = float(entry.get('actual_balance', 0))
            if not code:
                continue
            recorded = totals.get(code, 0.0)
            gap = round(actual - recorded, 2)
            if abs(gap) < 0.01:
                continue
            db.insert_Cash_Transaction(
                name          = f'תיקון יתרה – {code}',
                executed_date = _dt.now().replace(microsecond=0),
                amount        = gap,
                currency      = code,
                category      = ReservedNames.CASH_FILLER_CATEGORY,
                description   = f'כיול: רשום {recorded:,.0f}, בפועל {actual:,.0f}'
            )
            created += 1
            details.append({'currency': code, 'gap': gap})
        db.commit_changes()
        if created:
            _invalidate_cash_cache()
        return jsonify({'ok': True, 'created': created, 'details': details})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


import time as _time
_SERVER_START_TIME = _time.time()

@app.route('/api/status')
def status():
    return jsonify({'running': _analysis_running, 'started_at': _SERVER_START_TIME})


@app.route('/api/version')
def version():
    """Return the app version from the VERSION file at project root."""
    try:
        version_path = os.path.join(_PROJECT_DIR, 'VERSION')
        with open(version_path, encoding='utf-8') as f:
            v = f.read().strip()
    except Exception:
        v = '—'
    return jsonify({'version': v})


@app.route('/api/stale-all')
def stale_all():
    """Return {key: bool} stale status for every generated monthly page."""
    import page_status as _ps
    statuses = _ps.get_all()
    return jsonify({k: (v != 'fresh') for k, v in statuses.items()})


@app.route('/api/pages/status')
def pages_status():
    """Return {yyyy_mm: 'none'|'fresh'|'stale'} for all tracked months."""
    import page_status as _ps
    return jsonify(_ps.get_all())


@app.route('/api/global/data')
def global_data_api():
    """Return accounts + mortgage data (cached; not tied to a specific month)."""
    import time as _time
    cached = _global_data_cache.get('global')
    if cached:
        return jsonify(cached['data'])
    try:
        from datetime import datetime as _dt2
        from AppManager import AppManager
        t = _dt2.now()
        payload = AppManager(skip_parser=True).get_global_data(t=t)
        _global_data_cache['global'] = {'ts': _time.time(), 'data': payload}
        return jsonify(payload)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/housing/data')
def housing_data_api():
    """Return housing/mortgage data always computed for today's date (not month-specific)."""
    import time as _time
    cached = _housing_cache.get('data')
    if cached and (_time.time() - cached['ts']) < 1800:
        return jsonify(cached['data'])
    try:
        from datetime import datetime as _dt
        from AppManager import AppManager
        payload = AppManager(skip_parser=True).get_global_data(t=_dt.now())
        data = {'mortgage': payload.get('mortgage', {})}
        _housing_cache['data'] = {'ts': _time.time(), 'data': data}
        return jsonify(data)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/housing/invalidate', methods=['POST'])
def housing_invalidate():
    """Clear the housing data cache so the next GET recomputes from scratch."""
    _housing_cache.clear()
    return jsonify({'ok': True})


@app.route('/api/housing/regen-stream')
def housing_regen_stream():
    """SSE endpoint: recomputes housing/mortgage data with progress events."""
    _housing_cache.clear()
    local_q: queue.Queue = queue.Queue()

    def _worker():
        def _pc(pct, msg=''):
            local_q.put(f'__HOUSING_PROG__:{pct}:{msg}')
        try:
            from datetime import datetime as _dt
            from AppManager import AppManager
            data = AppManager(skip_parser=True).get_global_data(t=_dt.now(), progress_callback=_pc)
            _housing_cache['data'] = {'ts': _time.time(), 'data': data}
            local_q.put('__DONE__')
        except Exception as exc:
            import traceback
            _log_error(exc, traceback.format_exc())
            local_q.put('__ERROR__')

    threading.Thread(target=_worker, daemon=True, name='housing-regen-worker').start()

    def _generate():
        yield 'data: __CONNECTED__\n\n'
        while True:
            try:
                msg = local_q.get(timeout=25)
            except queue.Empty:
                yield 'data: \n\n'
                continue
            safe = msg.replace('\r\n', '↵').replace('\n', '↵').replace('\r', '↵')
            yield f'data: {safe}\n\n'
            if msg == '__DONE__' or msg.startswith('__ERROR__'):
                break

    return Response(_generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/regen/status')
def regen_status():
    """Return current regen state for frontend button/overlay restore on load."""
    return jsonify({
        'active_key':  _active_regen_key,
        'any_active':  _analysis_running,
    })


def _max_source_mtime() -> float:
    """Return the newest mtime across all source .py/.html files and DB files."""
    max_mt = 0.0
    source_dir = os.path.join(_PROJECT_DIR, 'source')
    _skip_html = {'output.html', 'Category_output.html'}
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__',)]
        for f in files:
            if f.endswith('.py') or (f.endswith('.html') and f not in _skip_html):
                mt = os.path.getmtime(os.path.join(root, f))
                if mt > max_mt:
                    max_mt = mt
    for db in ('ShmuelFamiliy.db', os.path.join('source', 'ShmuelFamiliy.db')):
        db_path = os.path.join(_PROJECT_DIR, db)
        if os.path.exists(db_path):
            mt = os.path.getmtime(db_path)
            if mt > max_mt:
                max_mt = mt
    return max_mt


def _source_files_mtime() -> float:
    """Newest mtime for source .py / .html files only (excludes DB)."""
    max_mt = 0.0
    source_dir = os.path.join(_PROJECT_DIR, 'source')
    _skip = {'output.html', 'Category_output.html'}
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.py') or (f.endswith('.html') and f not in _skip):
                mt = os.path.getmtime(os.path.join(root, f))
                if mt > max_mt:
                    max_mt = mt
    return max_mt

_server_start_mtime = _source_files_mtime()


@app.route('/api/server-stale')
def server_stale():
    return jsonify({'stale': _source_files_mtime() > _server_start_mtime})


@app.route('/api/stale/cat/<slug>')
def check_stale_category(slug):
    """Staleness check for a category/business analysis page."""
    if not _re.match(r'^[\w֐-׿]+$', slug):
        return jsonify({'stale': False})
    html_path = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
    if not os.path.exists(html_path):
        return jsonify({'stale': True})
    return jsonify({'stale': _is_stale_manifest(html_path)})


@app.route('/api/stale/<yyyy_mm>')
def check_stale(yyyy_mm):
    if not _re.match(r'^\d{4}_\d{2}$', yyyy_mm):
        return jsonify({'stale': False})
    import page_status as _ps
    status = _ps.get_status(yyyy_mm)
    return jsonify({'stale': status != 'fresh'})


@app.route('/api/analysis', methods=['POST'])
def run_analysis():
    global _analysis_running, _active_regen_key

    with _analysis_lock:
        if _analysis_running:
            return jsonify({'status': 'busy', 'message': 'ניתוח כבר רץ, אנא המתן'}), 409
        _analysis_running = True

    # Drain any stale messages from previous run
    while not _log_queue.empty():
        try:
            _log_queue.get_nowait()
        except queue.Empty:
            break

    body      = request.get_json() or {}
    month_sel = body.get('month', 'current')   # 'current' | 'last' | 'pick'
    date_str  = body.get('date', '')            # 'YYYY-MM-DD' when month='pick'

    def _worker():
        global _analysis_running, _active_regen_key
        key = None
        try:
            from AppManager import AppManager
            from datetime import datetime
            from dateutil.relativedelta import relativedelta
            from src_utils.utils import utils as _utils
            import page_status as _ps

            _utils._cc_confirm_hook = _web_cc_confirm

            if month_sel == 'last':
                t = datetime.now() - relativedelta(months=1)
            elif month_sel == 'pick' and date_str:
                t = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                t = datetime.now()

            key = t.strftime('%Y_%m')
            _active_regen_key = key
            _regen_tracker.init(key)
            _regen_tracker.set_callback(key, lambda pct: _log_queue.put(f'__PROGRESS__:{pct}'))

            result = AppManager(skip_parser=True).monthly_analysis(t=t, page_id=key)
            _monthly_data_cache[key] = {'ts': _time.time(), 'data': result}
            _ps.mark_generated(key)

            # Pre-warm global cache so the data endpoint returns instantly after __DONE__
            if 'global' not in _global_data_cache:
                try:
                    _gp = AppManager(skip_parser=True).get_global_data(t=t)
                    _global_data_cache['global'] = {'ts': _time.time(), 'data': _gp}
                except Exception:
                    pass

            _regen_tracker.done(key)
            _log_queue.put(f'__DONE__:{key}')

        except Exception as exc:
            import traceback
            _log_error(exc, traceback.format_exc())
            _log_queue.put('__ERROR__')

        finally:
            with _analysis_lock:
                _analysis_running = False
                _active_regen_key = None
            if key:
                _regen_tracker.clear_callback(key)
            try:
                from src_utils.utils import utils as _utils
                _utils._cc_confirm_hook = None
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True, name='analysis-worker').start()
    return jsonify({'status': 'started'})


@app.route('/api/analysis-stream')
def run_analysis_stream():
    """SSE endpoint: runs monthly analysis inline so thread + stream share the same invocation."""
    global _analysis_running, _active_regen_key
    month_sel = request.args.get('month', 'current')
    date_str  = request.args.get('date', '')

    with _analysis_lock:
        if _analysis_running:
            def _busy():
                yield 'data: __ERROR__:busy\n\n'
            return Response(_busy(), mimetype='text/event-stream',
                            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
        _analysis_running = True

    local_q: queue.Queue = queue.Queue()

    def _worker():
        global _analysis_running, _active_regen_key
        _thread_log_queue.queue = local_q
        key = None
        try:
            from AppManager import AppManager
            from datetime import datetime
            from dateutil.relativedelta import relativedelta
            from src_utils.utils import utils as _utils
            import page_status as _ps
            _utils._cc_confirm_hook = _web_cc_confirm

            if month_sel == 'last':
                t = datetime.now() - relativedelta(months=1)
            elif month_sel == 'pick' and date_str:
                t = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                t = datetime.now()

            key = t.strftime('%Y_%m')
            _active_regen_key = key
            _regen_tracker.init(key)
            _regen_tracker.set_callback(key, lambda pct: local_q.put(f'__PROGRESS__:{pct}'))

            result = AppManager(skip_parser=True).monthly_analysis(t=t, page_id=key)
            _monthly_data_cache[key] = {'ts': _time.time(), 'data': result}
            _ps.mark_generated(key)

            # Pre-warm global cache so the data endpoint returns instantly after __DONE__
            if 'global' not in _global_data_cache:
                try:
                    _gp = AppManager(skip_parser=True).get_global_data(t=t)
                    _global_data_cache['global'] = {'ts': _time.time(), 'data': _gp}
                except Exception:
                    pass

            _regen_tracker.done(key)
            local_q.put(f'__DONE__:{key}')
        except Exception as exc:
            import traceback
            _log_error(exc, traceback.format_exc())
            local_q.put('__ERROR__')
        finally:
            with _analysis_lock:
                _analysis_running = False
                _active_regen_key = None
            if key:
                _regen_tracker.clear_callback(key)
            try:
                from src_utils.utils import utils as _utils
                _utils._cc_confirm_hook = None
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True, name='analysis-stream-worker').start()

    def _generate():
        yield 'data: __CONNECTED__\n\n'
        while True:
            try:
                msg = local_q.get(timeout=25)
            except queue.Empty:
                yield 'data: \n\n'
                continue
            safe = msg.replace('\r\n', '↵').replace('\n', '↵').replace('\r', '↵')
            yield f'data: {safe}\n\n'
            if msg.startswith('__DONE__') or msg == '__ERROR__':
                break

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/logs')
def log_stream():
    """Server-Sent Events endpoint — streams log lines as they arrive."""
    def _generate():
        yield "data: __CONNECTED__\n\n"
        while True:
            try:
                msg = _log_queue.get(timeout=20)
            except queue.Empty:
                yield "data: \n\n"   # keepalive ping
                continue

            # Newlines inside SSE data lines break the protocol — replace them
            safe = msg.replace('\r\n', '↵').replace('\n', '↵').replace('\r', '↵')
            yield f"data: {safe}\n\n"

            if msg.startswith('__DONE__') or msg == '__ERROR__':
                break

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@app.route('/api/debug-logs')
def debug_log_stream():
    """Persistent SSE stream — replays rolling buffer then forwards new lines."""
    def _generate():
        sub_q: queue.Queue = queue.Queue()
        with _debug_lock:
            buffered = list(_debug_buffer)
            _debug_subscribers.append(sub_q)
        try:
            for line in buffered:
                safe = line.replace('\r\n', '↵').replace('\n', '↵').replace('\r', '↵')
                yield f'data: {safe}\n\n'
            while True:
                try:
                    msg = sub_q.get(timeout=25)
                except queue.Empty:
                    yield 'data: \n\n'
                    continue
                safe = msg.replace('\r\n', '↵').replace('\n', '↵').replace('\r', '↵')
                yield f'data: {safe}\n\n'
        finally:
            with _debug_lock:
                try:
                    _debug_subscribers.remove(sub_q)
                except ValueError:
                    pass

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/analysis/respond', methods=['POST'])
def analysis_respond():
    """Receive the user's yes/no answer to a credit-card confirmation prompt."""
    global _cc_prompt_choice
    body = request.get_json() or {}
    _cc_prompt_choice = bool(body.get('choice', False))
    _cc_prompt_event.set()
    return jsonify({'ok': True})




def _not_generated_html(year: int, month: int, yyyy_mm: str) -> str:
    import calendar
    month_label = f"{calendar.month_name[month]} {year}"
    date_str    = f"{year}-{month:02d}-01"
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BankDash — {month_label}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0faf5;
            min-height: 100vh; display: flex; align-items: center;
            justify-content: center; padding: 16px; }}
    .card {{ background: #fff; border-radius: 20px; padding: 28px 22px 22px;
             width: 100%; max-width: 460px;
             box-shadow: 0 4px 28px rgba(52,184,136,.13); }}

    /* header */
    .hdr {{ text-align: center; margin-bottom: 22px; }}
    .badge {{ display: inline-block; background: #d8f3dc; color: #2d6a4f;
              border-radius: 99px; padding: 4px 16px; font-size: .8em;
              font-weight: 600; margin-bottom: 10px; }}
    .hdr h2 {{ color: #1e2a4a; font-size: 1.15em; font-weight: 700; margin-bottom: 4px; }}
    .hdr p  {{ color: #6b8c7a; font-size: .84em; }}

    /* progress */
    .prog-wrap {{ margin-bottom: 18px; }}
    .prog-row {{ display: flex; justify-content: space-between; margin-bottom: 7px; }}
    .prog-label {{ font-size: .74em; color: #6b8c7a; }}
    .prog-pct   {{ font-size: .74em; font-weight: 700; color: #52b788; }}
    .prog-bar  {{ height: 7px; background: #d8f3dc; border-radius: 99px; overflow: hidden; }}
    .prog-fill {{ height: 100%;
                  background: linear-gradient(90deg, #74c69d 0%, #1e9d8b 50%, #34d9c3 75%, #1e9d8b 100%);
                  background-size: 200% auto;
                  border-radius: 99px; width: 0%; transition: width .4s ease;
                  animation: progShimmer 2s linear infinite; }}
    @keyframes progShimmer {{ to {{ background-position: -200% center; }} }}

    /* log panel */
    .log-panel {{ border: 1px solid #d8f3dc; border-radius: 12px; overflow: hidden; }}
    .log-hdr {{ background: #f0faf5; padding: 7px 12px; border-bottom: 1px solid #d8f3dc;
                display: flex; align-items: center; gap: 6px; }}
    .log-dot {{ width: 6px; height: 6px; border-radius: 50%; background: #52b788;
                flex-shrink: 0; animation: blink 1.2s ease-in-out infinite; }}
    @keyframes blink {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:.15; }} }}
    .log-hdr-title {{ font-size: .7em; font-weight: 600; color: #52b788;
                      letter-spacing: .04em; text-transform: uppercase; flex: 1; }}
    .copy-btn {{ background: none; border: none; border-radius: 6px;
                 padding: 3px 5px; color: #52b788; cursor: pointer;
                 line-height: 1; transition: color .15s; }}
    .copy-btn:hover {{ color: #2d6a4f; }}
    .copy-btn.copied {{ color: #2d6a4f; }}
    .log-feed {{ max-height: 210px; overflow-y: auto; padding: 10px 12px;
                 display: flex; flex-direction: column; gap: 2px;
                 scrollbar-width: thin; scrollbar-color: #b7e4c7 transparent; }}
    .log-feed::-webkit-scrollbar {{ width: 3px; }}
    .log-feed::-webkit-scrollbar-thumb {{ background: #b7e4c7; border-radius: 2px; }}
    .log-line {{ font-size: .75em; font-family: 'Consolas','Courier New',monospace;
                 line-height: 1.55; color: #3d6b55; white-space: pre-wrap;
                 word-break: break-word; direction: ltr; text-align: left; }}
    .log-line.warn {{ color: #8a6200; }}
    .log-line.err  {{ color: #b83232; font-weight: 500; }}
    .log-line.done {{ color: #1e7a50; font-weight: 600; }}

    .back {{ text-align: center; margin-top: 18px; font-size: .8em; }}
    .back a {{ color: #52b788; text-decoration: none; }}
    .back a:hover {{ color: #1e9d8b; }}

    /* CC modal */
    .cc-overlay {{ position:fixed; inset:0; background:rgba(15,40,30,.45);
                   z-index:10000; display:flex; align-items:center; justify-content:center; }}
    .cc-modal  {{ background:#fff; border-radius:16px; padding:24px 22px;
                  max-width:400px; width:90%; box-shadow:0 12px 40px rgba(0,0,0,.18);
                  text-align:right; direction:rtl; }}
    .cc-title  {{ font-size:.95em; font-weight:700; color:#1e2a4a; margin-bottom:10px; }}
    .cc-body   {{ font-size:.82em; color:#5a7a6a; margin-bottom:14px; line-height:1.6; }}
    .cc-row    {{ display:flex; justify-content:space-between; padding:4px 0;
                  border-bottom:1px solid #edf5f0; font-size:.82em; }}
    .cc-row:last-child {{ border-bottom:none; }}
    .cc-lbl    {{ color:#8aad96; }}
    .cc-val    {{ font-weight:600; color:#1e2a4a; }}
    .cc-btns   {{ display:flex; gap:8px; justify-content:flex-end; margin-top:16px; }}
    .cc-btn    {{ border:none; border-radius:8px; padding:7px 20px; font-size:.85em;
                  font-weight:600; cursor:pointer; transition:background .15s; font-family:inherit; }}
    .cc-yes    {{ background:#52b788; color:#fff; }}
    .cc-yes:hover {{ background:#3da870; }}
    .cc-no     {{ background:#edf5f0; color:#4a7060; }}
    .cc-no:hover  {{ background:#d8f3dc; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="hdr">
      <div class="badge">{month_label}</div>
      <h2>מנתח נתונים</h2>
      <p>הניתוח החודשי מופעל אוטומטית, אנא המתן…</p>
    </div>

    <div class="prog-wrap">
      <div class="prog-row">
        <span class="prog-label">התקדמות</span>
        <span class="prog-pct" id="prog-pct">0%</span>
      </div>
      <div class="prog-bar"><div class="prog-fill" id="prog-fill"></div></div>
    </div>

    <div class="log-panel">
      <div class="log-hdr">
        <div class="log-dot" id="log-dot"></div>
        <span class="log-hdr-title">יומן אירועים</span>
        <button class="copy-btn" id="copy-btn" onclick="copyLog()" title="העתק לוג">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
        </button>
      </div>
      <div class="log-feed" id="lf-feed"></div>
    </div>

    <div class="back"><a href="/">&#8592; חזרה לדף הראשי</a></div>
  </div>

  <div id="cc-overlay" class="cc-overlay" style="display:none">
    <div class="cc-modal">
      <div class="cc-title">עסקת אשראי זוהתה</div>
      <div class="cc-body">נמצאה עסקה שעשויה להיות חיוב כרטיס אשראי. האם לסווג אותה כ&quot;אשראי&quot;?</div>
      <div id="cc-rows"></div>
      <div class="cc-btns">
        <button class="cc-btn cc-no"  onclick="ccRespond(false)">לא — דלג</button>
        <button class="cc-btn cc-yes" onclick="ccRespond(true)">כן — אשר</button>
      </div>
    </div>
  </div>

  <script>
    /* ── progress ── */
    var _pct = 0, _done = false;
    var _ptimer = setInterval(function() {{
      if (_done) return;
      var step = _pct < 50 ? 1.5 : (_pct < 75 ? 0.5 : 0.15);
      _pct = Math.min(_pct + step, 89);
      _setPct(_pct);
    }}, 250);
    function _setPct(p) {{
      p = Math.min(Math.max(p, 0), 100);
      document.getElementById('prog-fill').style.width = p.toFixed(1) + '%';
      document.getElementById('prog-pct').textContent = Math.round(p) + '%';
    }}
    function _finishPct() {{
      _done = true; clearInterval(_ptimer); _setPct(100);
      var d = document.getElementById('log-dot');
      if (d) {{ d.style.animation = 'none'; d.style.background = '#52b788'; }}
    }}
    function _errorPct() {{
      _done = true; clearInterval(_ptimer);
      var d = document.getElementById('log-dot');
      if (d) {{ d.style.animation = 'none'; d.style.background = '#b83232'; }}
    }}

    /* ── log ── */
    function appendLog(text, cls) {{
      var feed = document.getElementById('lf-feed');
      if (!feed) return;
      var el = document.createElement('div');
      el.className = 'log-line' + (cls ? ' ' + cls : '');
      el.textContent = text;
      feed.appendChild(el);
      while (feed.children.length > 120) feed.removeChild(feed.firstChild);
      feed.scrollTop = feed.scrollHeight;
    }}

    /* ── CC modal ── */
    function showCCPrompt(tx) {{
      var labels = {{ID:'מזהה', Date:'תאריך', Name:'שם', Out:'סכום', Description:'תיאור'}};
      var html = '';
      ['Name','Date','Out','Description','ID'].forEach(function(k) {{
        if (tx[k] != null && tx[k] !== '' && tx[k] !== 'nan')
          html += '<div class="cc-row"><span class="cc-lbl">' + (labels[k]||k) + '</span>'
                + '<span class="cc-val">' + String(tx[k]).replace(/</g,'&lt;') + '</span></div>';
      }});
      document.getElementById('cc-rows').innerHTML = html;
      document.getElementById('cc-overlay').style.display = 'flex';
    }}
    function ccRespond(choice) {{
      document.getElementById('cc-overlay').style.display = 'none';
      fetch('/api/analysis/respond', {{method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{choice: choice}})
      }}).catch(function(){{}});
    }}

    /* ── copy log ── */
    function copyLog() {{
      var lines = document.getElementById('lf-feed').querySelectorAll('.log-line');
      var text = Array.from(lines).map(function(l) {{ return l.textContent; }}).join('\n');
      var _copyIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
      var _checkIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
      navigator.clipboard.writeText(text).then(function() {{
        var btn = document.getElementById('copy-btn');
        btn.innerHTML = _checkIcon;
        btn.classList.add('copied');
        setTimeout(function() {{ btn.innerHTML = _copyIcon; btn.classList.remove('copied'); }}, 2000);
      }}).catch(function() {{
        var btn = document.getElementById('copy-btn');
        btn.textContent = '✕';
        setTimeout(function() {{ btn.innerHTML = _copyIcon; }}, 2000);
      }});
    }}

    /* ── stream ── */
    (function() {{
      var es = new EventSource('/api/analysis-stream?month=pick&date={date_str}');
      var _tid = setTimeout(function() {{
        if (es.readyState !== EventSource.CLOSED) {{
          es.close(); _errorPct();
          appendLog('✗ תם הזמן — נסה לרענן', 'err');
        }}
      }}, 300000);
      es.onmessage = function(e) {{
        if (!e.data || e.data === '__CONNECTED__') return;
        if (e.data.startsWith('__PROMPT_CC__:')) {{
          try {{ showCCPrompt(JSON.parse(e.data.slice(14))); }} catch(_) {{}}
          return;
        }}
        if (e.data.startsWith('__DONE__')) {{
          clearTimeout(_tid); es.close();
          _finishPct();
          appendLog('✓ הניתוח הסתיים — טוען…', 'done');
          setTimeout(function() {{ location.href = '/general/{yyyy_mm}'; }}, 1100);
          return;
        }}
        if (e.data === '__ERROR__') {{
          clearTimeout(_tid); es.close();
          _errorPct();
          appendLog('✗ שגיאה בניתוח', 'err');
          return;
        }}
        appendLog(e.data);
      }};
      es.onerror = function() {{
        if (es.readyState === EventSource.CLOSED) return;
        es.close(); _errorPct();
        appendLog('✗ חיבור נותק', 'err');
      }};
    }})();
  </script>
</body>
</html>"""


def _splash_html() -> str:
    return """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>BankApp — טוען</title>
  <style>
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9;
           display: flex; align-items: center; justify-content: center;
           min-height: 100vh; margin: 0; }
    .box { background: #fff; border-radius: 14px; padding: 48px 56px;
           text-align: center; box-shadow: 0 6px 20px rgba(0,0,0,.10); max-width: 440px; }
    h2   { color: #1e2a4a; margin-bottom: 12px; }
    p    { color: #888; font-size: .93em; margin-bottom: 32px; }
    .btn { background: #1e9d8b; color: #fff; border: none; border-radius: 10px;
           padding: 13px 36px; font-size: 1em; cursor: pointer; font-weight: 600; }
    .btn:hover { background: #178878; }
  </style>
</head>
<body>
  <div class="box">
    <h2>ברוך הבא ל-BankApp</h2>
    <p>טרם נוצר דשבורד. לחץ כדי להפעיל ניתוח עבור החודש הנוכחי.</p>
    <button class="btn" id="runBtn" onclick="runNow()">הפעל ניתוח</button>
    <p id="msg" style="margin-top:18px;color:#1e9d8b;display:none;">מעבד נתונים, אנא המתן…</p>
  </div>
  <script>
    function runNow() {
      document.getElementById('runBtn').disabled = true;
      document.getElementById('msg').style.display = 'block';
      fetch('/api/analysis', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({month:'current'})})
        .then(() => {
          var es = new EventSource('/api/logs');
          es.onmessage = function(e) {
            if (e.data.startsWith('__DONE__')) { es.close(); location.reload(); }
            if (e.data === '__ERROR__') { es.close(); alert('שגיאה בניתוח — בדוק את הטרמינל'); }
          };
        });
    }
  </script>
</body>
</html>"""


# ── File Organizer ────────────────────────────────────────────────────────────

_ORGANIZER_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>ארגונית קבצים</title>
<style>
:root{
  --navy:#1e2a4a;--teal:#1e9d8b;--teal-light:#e8f7f5;--teal-glow:rgba(30,157,139,.30);
  --white:#fff;--bg:#f4f6f9;--border:#eef0f6;--text-muted:#9aa3bb;
  --radius:14px;--radius-sm:8px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--navy);direction:rtl;display:flex;min-height:100vh}
.ham-btn{position:fixed;top:18px;right:18px;width:42px;height:42px;background:var(--white);border:1.5px solid var(--border);border-radius:10px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:400;box-shadow:0 2px 10px rgba(0,0,0,.06);color:var(--navy);transition:background .15s,color .15s,border-color .15s}
.ham-btn:hover,.ham-btn.open{background:var(--teal);border-color:var(--teal);color:#fff}
.nav-overlay{position:fixed;inset:0;background:rgba(15,22,45,.26);z-index:390;opacity:0;pointer-events:none;transition:opacity .22s ease}
.nav-overlay.open{opacity:1;pointer-events:all}
.sidebar{position:fixed;top:0;right:0;height:100vh;width:230px;background:var(--white);z-index:395;transform:translate3d(100%,0,0);transition:transform .22s cubic-bezier(.4,0,.2,1);will-change:transform;box-shadow:-4px 0 24px rgba(0,0,0,.09);display:flex;flex-direction:column}
.sidebar.open{transform:translate3d(0,0,0)}
.sidebar-header{display:flex;align-items:center;padding:20px 20px 16px;border-bottom:1px solid var(--border);flex-shrink:0}
.sidebar-app-name{font-size:.95em;font-weight:700;color:var(--navy)}
.sidebar-close-btn{margin-right:auto;background:none;border:none;cursor:pointer;font-size:1.1em;color:#555;padding:4px 6px;border-radius:6px;transition:background .12s,color .12s}
.sidebar-close-btn:hover{background:var(--teal-light);color:var(--teal)}
.sidebar-scroll{flex:1;overflow-y:auto;overflow-x:hidden;padding:8px 0 16px}
.sidebar-footer{padding:12px 16px;border-top:1px solid var(--border);flex-shrink:0}
.nav-restart-btn{width:100%;padding:8px 12px;border:1.5px dashed var(--border);border-radius:8px;background:none;color:var(--text-muted);font-size:.78em;font-weight:600;cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:7px;justify-content:center;transition:background .15s,color .15s,border-color .15s}
.nav-restart-btn:hover{background:#fff3f3;color:#e53935;border-color:#e53935}
.nav-restart-btn:disabled{opacity:.5;cursor:default}
.app-version-badge{margin-top:8px;text-align:center;font-size:.72em;color:var(--text-muted);letter-spacing:.03em;opacity:.7;user-select:none}
.nav-item{display:flex;align-items:center;padding:10px 20px;text-decoration:none;color:#555;font-size:.875em;font-weight:500;transition:background .1s,color .1s;cursor:pointer;border:none;background:none;width:100%;text-align:right;position:relative;letter-spacing:.1px}
.nav-item::before{content:'';position:absolute;right:0;top:22%;height:56%;width:3px;border-radius:3px 0 0 3px;background:transparent;transition:background .1s}
.nav-item:hover{background:#e8f7f5;color:#1e9d8b}
.nav-item:hover::before{background:#1e9d8b}
.nav-item.active{color:#b8c0d0;cursor:default;pointer-events:none}
.nav-sep{height:1px;background:#eef0f6;margin:8px 16px}
.main{margin-right:0;flex:1;padding:72px 32px 60px;min-width:0;overflow-x:hidden}
.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}
.page-header h1{font-size:1.7em;font-weight:700}
.generated-label{font-size:.72em;color:var(--text-muted);white-space:nowrap}
.org-regen-fab{position:fixed;bottom:22px;right:18px;z-index:500}
.org-regen-btn{height:52px;padding:0 22px;background:var(--teal);color:#fff;border:none;border-radius:26px;font-size:.85em;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:8px;box-shadow:0 4px 18px rgba(30,157,139,.45);white-space:nowrap;transition:box-shadow .2s,opacity .2s}
.org-regen-btn:hover{box-shadow:0 6px 24px rgba(30,157,139,.65)}
.org-regen-btn:disabled{opacity:.65;cursor:wait}
.org-regen-icon{font-size:1.6em;line-height:1;display:flex;align-items:center}
.org-regen-btn.running .org-regen-icon{display:none}
.org-regen-pct{font-size:.65em;font-weight:700;color:rgba(255,255,255,.9);display:none;line-height:1;margin-top:2px;letter-spacing:.02em}
.org-regen-btn.running .org-regen-pct{display:block}
@media(max-width:768px){.org-regen-fab{bottom:14px;right:14px}.org-regen-btn{width:52px;padding:0;border-radius:50%;justify-content:center}.org-regen-label{display:none}}
.debug-fab{position:fixed;bottom:88px;right:18px;width:42px;height:42px;border-radius:50%;background:#1e2a4a;color:#fff;font-size:.72em;font-family:monospace;font-weight:700;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 14px rgba(0,0,0,.3);z-index:997;letter-spacing:-.5px}
.debug-fab:hover{filter:brightness(1.2)}
.debug-panel{position:fixed;bottom:138px;right:16px;width:480px;max-width:calc(100vw - 32px);height:340px;background:#12121f;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.55);z-index:996;display:none;flex-direction:column;overflow:hidden;font-family:monospace}
.debug-panel.open{display:flex}
.debug-hdr{display:flex;align-items:center;justify-content:space-between;padding:7px 12px;background:#0a0a18;color:#7ec8e3;font-size:.7em;font-weight:700;letter-spacing:.06em;flex-shrink:0;border-bottom:1px solid #222}
.debug-hdr-btns{display:flex;gap:5px}
.debug-hdr-btns button{background:none;border:1px solid #333;color:#888;border-radius:4px;padding:2px 8px;font-size:.9em;cursor:pointer;font-family:monospace}
.debug-hdr-btns button:hover{background:#1e1e2e;color:#eee}
.debug-feed{flex:1;overflow-y:auto;padding:6px 10px;font-size:.68em;line-height:1.55;color:#c8d8e4}
.debug-line{white-space:pre-wrap;word-break:break-all;padding:1px 0;border-bottom:1px solid #1a1a2a}
.debug-line.err{color:#ff6b6b}
.debug-line.warn{color:#ffa94d}
/* Alert panel */
.alert-panel{background:var(--white);border-radius:var(--radius);padding:20px 24px;margin-bottom:22px;box-shadow:0 2px 12px rgba(0,0,0,.07)}
.alert-section-title{font-size:.7em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:10px}
.alert-chips{display:flex;flex-wrap:wrap;gap:7px}
.alert-chip{display:inline-flex;align-items:center;gap:5px;padding:4px 11px;border-radius:20px;font-size:.77em;font-weight:600;cursor:default}
.chip-red{background:#fef2f2;color:#991b1b;border:1px solid #fecaca}
.chip-yellow{background:#fefce8;color:#854d0e;border:1px solid #fde68a}
.chip-blue{background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe}
.chip-blue2{background:#f0f9ff;color:#0c4a6e;border:1px solid #bae6fd}
.all-good{display:flex;align-items:center;gap:10px;color:#166534;font-weight:700;font-size:.95em}
.all-good-icon{font-size:1.3em}
.all-good-sub{font-size:.8em;color:var(--text-muted);font-weight:400;margin-right:4px}
.older-toggle{background:none;border:none;color:var(--teal);font-size:.78em;font-weight:600;cursor:pointer;padding:10px 0 0;display:block;text-align:right}
.older-toggle:hover{text-decoration:underline}
.older-section{display:none;margin-top:12px;padding-top:12px;border-top:1px dashed var(--border)}
.older-section.open{display:block}
/* Heatmap */
.heatmap-section{background:var(--white);border-radius:var(--radius);padding:20px 24px;box-shadow:0 2px 12px rgba(0,0,0,.07);overflow-x:auto}
.hm-table{border-collapse:separate;border-spacing:3px}
.hm-th-wrap{height:90px;vertical-align:bottom;padding-bottom:4px;text-align:center}
.hm-th{writing-mode:vertical-rl;transform:rotate(180deg);font-size:.67em;font-weight:600;color:var(--navy);white-space:nowrap;display:inline-block}
.hm-label{text-align:right;padding-right:12px;font-size:.71em;color:var(--text-muted);font-weight:500;white-space:nowrap;vertical-align:middle}
.hm-label.recent{color:var(--navy);font-weight:700}
.hm-cell{width:20px;height:20px;border-radius:4px;position:relative;cursor:crosshair}
.hm-green{background:var(--teal)}
.hm-yellow{background:#f59e0b}
.hm-red{background:#ef4444}
.hm-blue2{background:#93c5fd}
.hm-gray{background:#e5e7eb}
.hm-darkgray{background:#9ca3af}
.hm-cell.has-problem::after{content:'';position:absolute;top:2px;left:2px;width:5px;height:5px;border-radius:50%;background:rgba(255,255,255,.85)}
.hm-divider-row td{border-top:2px solid var(--border);padding-top:5px}
.hm-tooltip{position:fixed;background:#1e2a4a;color:#e8edf5;padding:8px 12px;border-radius:9px;font-size:.72em;line-height:1.6;pointer-events:none;z-index:9999;display:none;max-width:230px;box-shadow:0 4px 20px rgba(0,0,0,.4)}
.hm-tip-label{font-weight:700;font-size:1.05em;margin-bottom:2px}
.hm-tip-status{opacity:.85}
.hm-tip-date{opacity:.6;font-size:.9em}
/* Bank coverage timeline */
.bank-timeline{background:var(--white);border-radius:var(--radius);padding:20px 24px;margin-bottom:22px;box-shadow:0 2px 12px rgba(0,0,0,.07)}
.bt-title{font-size:.7em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:14px}
.bt-chart{overflow-x:auto;padding-bottom:4px}
.bt-track{display:flex;align-items:center;gap:8px;margin-bottom:4px;min-width:max-content}
.bt-track-lbl{width:76px;flex-shrink:0;font-size:.72em;font-weight:600;color:var(--navy);text-align:right;white-space:nowrap}
.bt-cells{display:flex;gap:2px}
.bt-cell{width:14px;height:22px;border-radius:3px;flex-shrink:0;cursor:crosshair}
.bt-cell.covered{background:var(--teal)}
.bt-cell.warn{background:#f59e0b}
.bt-cell.gap{background:#ef4444}
.bt-cell.na{background:#e5e7eb;opacity:.4}
.bt-lbl-cell{width:14px;height:18px;flex-shrink:0;font-size:.55em;color:var(--text-muted);position:relative;overflow:visible}
.bt-lbl-cell span{position:absolute;left:50%;transform:translateX(-50%);white-space:nowrap;top:4px}
.bt-title-row{display:flex;align-items:center;gap:8px;margin-bottom:14px}
.bt-title-row .bt-title{margin-bottom:0}
.bt-info-btn{width:17px;height:17px;border-radius:50%;background:var(--text-muted);color:#fff;font-size:.65em;font-weight:700;border:none;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;padding:0;line-height:1;position:relative}
.bt-info-btn:hover{background:var(--navy)}
.bt-info-popup{display:none;position:absolute;top:22px;right:0;background:#1e2a4a;color:#e8edf5;padding:13px 15px;border-radius:10px;font-size:.74em;line-height:1.7;z-index:1001;width:270px;box-shadow:0 6px 24px rgba(0,0,0,.45);white-space:normal;font-weight:400;text-align:right;cursor:default}
.bt-info-btn:hover .bt-info-popup,.bt-info-popup:hover{display:block}
.bt-info-popup b{color:#7ec8e3}
/* Legend collapsible */
.legend-toggle{background:none;border:none;color:var(--text-muted);font-size:.72em;cursor:pointer;padding:0;margin-top:16px;display:flex;align-items:center;gap:4px}
.legend-toggle:hover{color:var(--navy)}
.legend-body{display:none;margin-top:12px}
.legend-body.open{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:8px 32px}
.legend-item{display:flex;align-items:center;gap:8px;font-size:.78em}
.legend-dot{width:10px;height:10px;border-radius:3px;flex-shrink:0}
.ld-green{background:#22c55e}.ld-yellow{background:#f59e0b}.ld-red{background:#ef4444}
.ld-blue2{background:#93c5fd}.ld-gray{background:#e5e7eb}.ld-darkgray{background:#9ca3af}
.legend-label{font-weight:600;color:var(--navy);white-space:nowrap}
.legend-sep{color:var(--text-muted);margin:0 2px}
.legend-desc{color:var(--text-muted)}
</style>
</head>
<body data-generated="<!--GENERATED_DATE-->">
<button class="ham-btn" id="ham-btn" onclick="toggleNav()" aria-label="תפריט">
  <svg width="18" height="14" viewBox="0 0 18 14" fill="none">
    <rect width="18" height="2" rx="1" fill="currentColor"/>
    <rect y="6" width="18" height="2" rx="1" fill="currentColor"/>
    <rect y="12" width="18" height="2" rx="1" fill="currentColor"/>
  </svg>
</button>
<div class="nav-overlay" id="nav-overlay" onclick="toggleNav()"></div>
<nav class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <span class="sidebar-app-name">ניהול כספים</span>
    <button class="sidebar-close-btn" onclick="closeNav()" aria-label="סגור תפריט">✕</button>
  </div>
  <div class="sidebar-scroll">
    <a class="nav-item" href="/">ניתוח חודשי</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/accounts">חשבונות</a>
    <a class="nav-item" href="/housing">דיור</a>
    <a class="nav-item active" href="/organizer">ארגונית</a>
    <a class="nav-item" href="/bills">מעקב חשבונות</a>
    <a class="nav-item" href="/categories">ניתוח קטגוריאלי</a>
    <a class="nav-item" href="/search">חיפוש</a>
    <a class="nav-item" href="/spotify">Spotify Tracker</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/tagger">תייגן</a>
    <a class="nav-item" href="/files">קבצים</a>
  </div>
  <div class="sidebar-footer">
    <button class="nav-restart-btn" onclick="restartServer(this)">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg>
      הפעל שרת מחדש
    </button>
    <div class="app-version-badge" id="app-version-badge-2">v—</div>
  </div>
</nav>

<div id="hm-tooltip" class="hm-tooltip"></div>

<div class="main">
  <div class="page-header">
    <h1>ארגונית קבצים</h1>
    <span class="generated-label" id="generated-label"></span>
  </div>

  <div class="alert-panel">
    <!--ALERT_CONTENT-->
    <button class="legend-toggle" onclick="toggleLegend(this)">▸ מקרא</button>
    <div class="legend-body" id="legend-body">
      <div class="legend-item"><span class="legend-dot ld-green"></span><span class="legend-label">מאומת / Bank</span><span class="legend-sep">&mdash;</span><span class="legend-desc">קובץ תקין ומאומת</span></div>
      <div class="legend-item"><span class="legend-dot ld-yellow"></span><span class="legend-label">לא מאומת / ללא עסקות</span><span class="legend-sep">&mdash;</span><span class="legend-desc">קובץ קיים אך לא מאומת</span></div>
      <div class="legend-item"><span class="legend-dot ld-red"></span><span class="legend-label">קובץ חסר — עם עסקה</span><span class="legend-sep">&mdash;</span><span class="legend-desc">קובץ נדרש (נמצאה עסקה), אך לא נמצא</span></div>
      <div class="legend-item"><span class="legend-dot ld-blue2"></span><span class="legend-label">אי-התאמת ערך</span><span class="legend-sep">&mdash;</span><span class="legend-desc">סכום לא תואם לקובץ</span></div>
      <div class="legend-item"><span class="legend-dot ld-darkgray"></span><span class="legend-label">לא רשום</span><span class="legend-sep">&mdash;</span><span class="legend-desc">לא רשום לתקופה זו, אין צורך בקובץ</span></div>
      <div class="legend-item"><span class="legend-dot ld-gray"></span><span class="legend-label">לא זמין</span><span class="legend-sep">&mdash;</span><span class="legend-desc">פורמט לא תקף לתאריך</span></div>
    </div>
  </div>

  <!--BANK_TIMELINE-->

  <div class="heatmap-section">
    <table class="hm-table">
      <thead><!--HM_HEADER--></thead>
      <tbody><!--HM_ROWS--></tbody>
    </table>
  </div>
</div>

<script>
function restartServer(btn){btn.disabled=true;btn.innerHTML='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg> מפעיל מחדש…';fetch('/api/restart',{method:'POST'}).catch(function(){}).finally(function(){var t=setInterval(function(){fetch('/').then(function(r){if(r.ok){clearInterval(t);location.reload();}}).catch(function(){});},800);});}
function openNav(){var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.add('open');o.classList.add('open');b.classList.add('open');}
function closeNav(){var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.remove('open');o.classList.remove('open');b.classList.remove('open');}
function toggleNav(){document.getElementById('sidebar').classList.contains('open')?closeNav():openNav();}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeNav();});
fetch('/api/version').then(function(r){return r.json();}).then(function(d){var b=document.getElementById('app-version-badge-2');if(b&&d.version)b.textContent='v'+d.version;}).catch(function(){});
(function(){
  var genLabel = document.getElementById('generated-label');
  if (genLabel && document.body.dataset.generated)
    genLabel.textContent = 'נוצר: ' + document.body.dataset.generated;
})();
function regenerate() {
  var btn = document.getElementById('regen-btn');
  var pct = document.getElementById('regen-pct');
  btn.disabled = true;
  btn.classList.add('running');
  pct.textContent = '0%';
  var es = new EventSource('/api/organizer/regenerate');
  es.onmessage = function(e) {
    if (e.data === 'done') { es.close(); location.reload(); }
    else if (e.data === 'error') { es.close(); location.reload(); }
    else { var p = parseInt(e.data); if (!isNaN(p)) pct.textContent = p + '%'; }
  };
  es.onerror = function() { es.close(); location.reload(); };
}
var _dbgEs = null;
function toggleDebugPanel() {
  var p = document.getElementById('debug-panel');
  if (!p) return;
  var open = p.classList.toggle('open');
  if (open && !_dbgEs) _startDebugStream();
}
function _startDebugStream() {
  if (_dbgEs) return;
  _dbgEs = new EventSource('/api/debug-logs');
  _dbgEs.onmessage = function(e) {
    if (!e.data || !e.data.trim()) return;
    var feed = document.getElementById('debug-feed');
    if (!feed) return;
    var d = document.createElement('div');
    d.className = 'debug-line' + (e.data.match(/error|Error|ERROR/) ? ' err' : e.data.match(/warn|Warn|WARN/) ? ' warn' : '');
    d.textContent = e.data;
    feed.appendChild(d);
    feed.scrollTop = feed.scrollHeight;
  };
  _dbgEs.onerror = function() {
    if (_dbgEs) { _dbgEs.close(); _dbgEs = null; }
    setTimeout(_startDebugStream, 4000);
  };
}
document.addEventListener('DOMContentLoaded', function() { _startDebugStream(); });
function clearDebugPanel() { var f=document.getElementById('debug-feed'); if(f) f.innerHTML=''; }
function copyDebugPanel() { var f=document.getElementById('debug-feed'); if(f) navigator.clipboard.writeText(f.innerText).catch(function(){}); }
function toggleOlder() {
  var s = document.getElementById('older-section');
  var b = document.getElementById('older-btn');
  if (!s) return;
  s.classList.toggle('open');
  b.textContent = s.classList.contains('open') ? '▾ הסתר בעיות ישנות' : '▸ הצג בעיות ישנות';
}
function toggleLegend(btn) {
  var b = document.getElementById('legend-body');
  if (!b) return;
  b.classList.toggle('open');
  btn.textContent = b.classList.contains('open') ? '▾ מקרא' : '▸ מקרא';
}
(function(){
  var tip = document.getElementById('hm-tooltip');
  if (!tip) return;
  document.querySelectorAll('.hm-cell[data-tip], .bt-cell[data-tip]').forEach(function(c) {
    c.addEventListener('mouseenter', function(e) {
      var parts = c.dataset.tip.split('|');
      tip.innerHTML = '<div class="hm-tip-label">' + (parts[0]||'') + '</div>'
        + '<div class="hm-tip-status">' + (parts[1]||'') + '</div>'
        + (parts[2] ? '<div class="hm-tip-date">' + parts[2] + '</div>' : '');
      tip.style.display = 'block';
      moveTip(e);
    });
    c.addEventListener('mousemove', moveTip);
    c.addEventListener('mouseleave', function() { tip.style.display = 'none'; });
  });
  function moveTip(e) {
    var x = e.clientX + 14, y = e.clientY - 10;
    if (x + 230 > window.innerWidth) x = e.clientX - 244;
    if (y + 80 > window.innerHeight) y = e.clientY - 90;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
})();
</script>
<div class="org-regen-fab">
  <button class="org-regen-btn" id="regen-btn" onclick="regenerate()" title="חשב מחדש">
    <span class="org-regen-icon">&#8635;</span>
    <span class="org-regen-label">חשב מחדש</span>
    <span class="org-regen-pct" id="regen-pct"></span>
  </button>
</div>
<button class="debug-fab" id="debug-fab" onclick="toggleDebugPanel()" title="App logs">&lt;/&gt;</button>
<div class="debug-panel" id="debug-panel">
  <div class="debug-hdr">
    <span>APP LOGS</span>
    <div class="debug-hdr-btns">
      <button onclick="clearDebugPanel()">clear</button>
      <button onclick="copyDebugPanel()">copy</button>
      <button onclick="toggleDebugPanel()">&#x2715;</button>
    </div>
  </div>
  <div class="debug-feed" id="debug-feed"></div>
</div>
</body>
</html>"""



def _organizer_splash() -> str:
    return """<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
  <meta charset="UTF-8">
  <title>ארגונית קבצים</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8f9fb;display:flex;align-items:center;justify-content:center;min-height:100vh;flex-direction:column;gap:18px}
    @keyframes spin{to{transform:rotate(360deg)}}
    .spinner{width:52px;height:52px;border:4px solid #e2e8f0;border-top-color:#1e9d8b;border-radius:50%;animation:spin .8s linear infinite}
    .label{font-size:.95em;font-weight:600;color:#1a2744}
    .pct{font-size:1.8em;font-weight:700;color:#1e9d8b;min-width:4ch;text-align:center}
  </style>
</head>
<body>
  <div class="spinner"></div>
  <div class="label">מחשב נתונים\u2026</div>
  <div class="pct" id="pct">0%</div>
  <script>
    var es = new EventSource('/api/organizer/regenerate');
    es.onmessage = function(e) {
      if (e.data === 'done') { es.close(); location.reload(); }
      else if (e.data === 'error') { es.close(); }
      else { var p = parseInt(e.data); if (!isNaN(p)) document.getElementById('pct').textContent = p + '%'; }
    };
    es.onerror = function() { es.close(); location.reload(); };
  </script>
</body>
</html>"""


def _build_organizer_page(progress_callback=None):
    from html import escape as _esc
    sys.path.insert(0, _HERE)
    from src_utils.utils import utils as _utils
    from Constants import BANK_CARD_NUMBER

    try:
        df, color_coded_df = _utils.read_present_table(progress_callback=progress_callback)
    except Exception as exc:
        raise

    color_coded_df = color_coded_df.replace({1: 'Verified', 0: 'Not Verified'})

    untagged_cells = {}
    try:
        from Configurations.Formats import Formats
        from database import DataBase as _DB
        from datetime import datetime as _dt
        _untagged, _desc = _DB().get_untagged(table='BankTransactions')
        _TSEP = ' | '
        _DFMT = '%B, %Y'
        _DFMT_FULL = '%Y-%m-%d %H:%M:%S'
        _DLEN = 10
        for col in df.columns:
            try:
                fmt_name, card_num_col = col.split(_TSEP)
            except Exception:
                continue
            card_names = Formats.FORMATS.get(fmt_name, {}).get('Transaction Names', {})
            if card_num_col in card_names:
                possible = set(card_names[card_num_col])
                for idx in df.index:
                    val = df.at[idx, col]
                    sts = color_coded_df.at[idx, col] if idx in color_coded_df.index and col in color_coded_df.columns else None
                    try:
                        row_date = _dt.strptime(str(idx), _DFMT)
                    except Exception:
                        continue
                    match = _utils._find_untagged_transaction_match(
                        _untagged, _desc, possible, val, sts,
                        row_date, _DFMT_FULL, _DLEN
                    )
                    if match:
                        untagged_cells[(idx, col)] = match
    except Exception:
        pass

    cols = list(df.columns)
    # heatmap excludes bank columns (they have their own timeline)
    hm_cols = [c for c in cols if c.split(' | ')[-1] != BANK_CARD_NUMBER]

    # ── helpers ──────────────────────────────────────────────────────────────
    def _abbrev(col):
        parts = col.split(' | ')
        fmt, card = (parts[0], parts[1]) if len(parts) == 2 else (col, '')
        if card in ('Not_Relevant',):
            return 'Bank Range' if 'Date-Range' in fmt else 'Bank'
        c4 = card[-4:] if len(card) >= 4 else card
        if 'Leumi-Max'        in fmt: return f'Max {c4}'
        if 'American-Express' in fmt: return f'Amex {c4}'
        if 'Isra-Card-2026'   in fmt: return f'Isra26 {c4}'
        if 'Isra-Card'        in fmt: return f'Isra {c4}'
        if 'BeinLeumi-Bank'   in fmt: return f'Bank {c4}'
        if 'Cal'              in fmt: return f'Cal {c4}'
        return f'{fmt.split("-")[0][:5]} {c4}'

    def _classify(idx, col, value, status, is_date, card_num_col, date_str, cell_key):
        """Return (hm_class, status_label, is_problem, severity, tip_str)"""
        if 'Isra-Card-2026' in col:
            try:
                yr = str(idx).split(', ')[-1]
                if yr.isdigit() and int(yr) < 2026:
                    return 'hm-gray', 'N/A', False, 0, ''
            except Exception:
                pass
        if cell_key in untagged_cells:
            m = untagged_cells[cell_key]
            m_type = m[3] if len(m) > 3 else 'missing'
            m_name = str(m[2]) if len(m) > 2 and m[2] else '?'
            m_val  = str(m[1]) if len(m) > 1 and m[1] else '?'
            m_date = str(m[0])[:10] if m[0] else '?'
            if m_type == 'missing':
                tip = f'{_abbrev(col)}|✗ קובץ חסר ({m_name} ₪{m_val})|{m_date}'
                return 'hm-red', '✗ קובץ חסר', True, 3, tip
            else:
                tip = f'{_abbrev(col)}|⚠ אי-התאמה ({m_name} ₪{m_val})|{m_date}'
                return 'hm-blue2', '⚠ אי-התאמה', True, 2, tip
        if card_num_col == BANK_CARD_NUMBER and is_date:
            tip = f'{_abbrev(col)}|✓ Bank|{date_str}'
            return 'hm-green', 'Bank', False, 0, tip
        if status == 'Verified':
            tip = f'{_abbrev(col)}|✓ מאומת|{date_str}'
            return 'hm-green', '✓ מאומת', False, 0, tip
        if status == 'Not Verified' and card_num_col != BANK_CARD_NUMBER:
            tip = f'{_abbrev(col)}|⚠ לא מאומת|{date_str or "-"}'
            return 'hm-yellow', '⚠ לא מאומת', True, 2, tip
        if is_date and status != 'Not Verified':
            tip = f'{_abbrev(col)}|— ללא עסקאות|{date_str}'
            return 'hm-yellow', '— ללא עסקאות', True, 1, tip
        tip = f'{_abbrev(col)}|— לא רשום|-'
        return 'hm-darkgray', '— לא רשום', False, 0, tip

    # ── recency ───────────────────────────────────────────────────────────────
    from datetime import datetime as _dt2
    try:
        from dateutil.relativedelta import relativedelta as _rd
    except ImportError:
        class _rd:
            def __init__(self, months=0): self._m = months
            def __rsub__(self, other):
                import calendar
                m = other.month - self._m
                y = other.year + (m - 1) // 12
                m = (m - 1) % 12 + 1
                d = min(other.day, calendar.monthrange(y, m)[1])
                return other.replace(year=y, month=m, day=d)

    index_dates = {}
    for idx in df.index:
        try:
            index_dates[idx] = _dt2.strptime(str(idx), '%B, %Y')
        except Exception:
            index_dates[idx] = None

    valid_dates = [d for d in index_dates.values() if d]
    recent_cutoff = (max(valid_dates) - _rd(months=5)) if valid_dates else None

    # ── build chips + heatmap in one pass (reversed = recent first) ───────────
    CHIP_CLS = {'hm-red': 'chip-red', 'hm-yellow': 'chip-yellow',
                'hm-blue2': 'chip-blue2'}

    recent_chips = []   # [(severity, html)]
    older_chips  = []
    hm_row_parts = []   # [(is_recent, row_html)]

    index_list = list(df.index)
    for idx in reversed(index_list):
        idx_date = index_dates.get(idx)
        is_recent = bool(idx_date and recent_cutoff and idx_date >= recent_cutoff)
        lbl_cls = 'hm-label recent' if is_recent else 'hm-label'
        cells_html = f'<td class="{lbl_cls}">{_esc(str(idx))}</td>'

        for col in hm_cols:
            value    = df.at[idx, col]
            status   = color_coded_df.at[idx, col] if idx in color_coded_df.index and col in color_coded_df.columns else None
            is_date  = isinstance(value, str) and ('-' in value or '/' in value)
            card_num_col = col.split(' | ')[-1] if ' | ' in col else ''
            date_str = str(value)[:10] if is_date and isinstance(value, str) else (str(value) if value is not None else '')
            cell_key = (idx, col)

            hm_cls, lbl, is_problem, sev, tip = _classify(idx, col, value, status, is_date, card_num_col, date_str, cell_key)
            prob_cls = ' has-problem' if is_problem else ''
            safe_tip = tip.replace('"', '&quot;') if tip else ''
            cells_html += f'<td><div class="hm-cell {hm_cls}{prob_cls}" data-tip="{safe_tip}"></div></td>'

            if is_problem:
                abbrev = _abbrev(col)
                chip_cls = CHIP_CLS.get(hm_cls, 'chip-red')
                icon = '✗' if hm_cls == 'hm-red' else '⚠'
                chip_html = (f'<span class="alert-chip {chip_cls}" title="{_esc(tip.replace("|"," — "))}">'
                             f'{icon} {_esc(abbrev)} — {_esc(str(idx))}</span>')
                if is_recent:
                    recent_chips.append((sev, chip_html))
                else:
                    older_chips.append((sev, chip_html))

        hm_row_parts.append((is_recent, f'<tr>{cells_html}</tr>'))

    # sort chips by severity desc
    recent_chips.sort(key=lambda x: -x[0])
    older_chips.sort(key=lambda x: -x[0])

    # ── bank coverage timeline (from BankTransactions) ───────────────────────
    chrono_months = index_list  # oldest → newest

    # months that have at least one non-bank card file (gap detection)
    months_with_card_data = set()
    for _bidx in chrono_months:
        for _bcol in cols:
            if _bcol.split(' | ')[-1] == BANK_CARD_NUMBER:
                continue
            _bval = df.at[_bidx, _bcol] if _bidx in df.index and _bcol in df.columns else None
            if isinstance(_bval, str) and ('-' in _bval or '/' in _bval):
                months_with_card_data.add(_bidx)
                break

    # query actual bank coverage from BankTransactions table
    _bank_covered = {}  # 'YYYY-MM' → source_file_basename
    try:
        from database import DataBase as _DB_bt
        _bt_rows = _DB_bt().cursor.execute(
            "SELECT TO_CHAR(Date, 'YYYY-MM') AS ym, MAX(TRIM(Source_file)) AS sf "
            "FROM BankTransactions GROUP BY TO_CHAR(Date, 'YYYY-MM') ORDER BY ym"
        ).fetchall()
        for _r in _bt_rows:
            _ym, _sf = _r[0], (_r[1] or '')
            _bn = _sf.replace('\\', '/').split('/')[-1]
            _bank_covered[_ym] = _bn
    except Exception:
        pass

    # run sequential balance validation to detect months with missing transactions
    # balance is recorded once per day (last tx of the day); all txs in between accumulate
    _mismatch_details = {}  # 'YYYY-MM' → list of mismatch detail dicts
    try:
        from database import DataBase as _DB_val
        _val_rows = _DB_val().cursor.execute(
            "SELECT ID, Date, Out, Income, Balance, Name, Source_file "
            "FROM BankTransactions ORDER BY Date ASC, ID DESC"
        ).fetchall()
        _vbal = None        # running balance since last checkpoint
        _anchor = None      # last row that had a stored balance
        _span = []          # rows between anchor and current (no stored balance)
        for _vr in _val_rows:
            _vid, _vdate, _vout, _vinc, _vbs, _vname, _vsrc = _vr
            _vout_f = float(_vout or 0)
            _vinc_f = float(_vinc or 0)
            try:
                _vsb = float(str(_vbs).replace(',', '').strip()) if _vbs is not None else None
                _has_vbs = _vsb is not None and _vsb == _vsb  # excludes NaN
            except (TypeError, ValueError):
                _has_vbs = False
                _vsb = None
            _vdate_s = str(_vdate)[:10]
            _vym = str(_vdate)[:7]
            _vsrc_bn = (_vsrc or '').replace('\\', '/').split('/')[-1]
            _row = {'id': _vid, 'date': _vdate_s, 'name': str(_vname or ''),
                    'file': _vsrc_bn, 'out': _vout_f, 'income': _vinc_f}
            if _vbal is None:
                if _has_vbs:
                    _vbal = _vsb
                    _anchor = {**_row, 'balance': _vsb}
                    _span = []
            else:
                _vbal += _vinc_f - _vout_f
                if _has_vbs:
                    if abs(_vbal - _vsb) > 0.01:
                        _mismatch_details.setdefault(_vym, []).append({
                            'anchor': _anchor,
                            'span':   _span[:],
                            'current': {**_row, 'balance': _vsb},
                            'calc':   _vbal,
                            'stored': _vsb,
                            'diff':   _vsb - _vbal,
                        })
                    _vbal = _vsb
                    _anchor = {**_row, 'balance': _vsb}
                    _span = []
                else:
                    _span.append(_row)
    except Exception:
        pass
    _mismatch_months = set(_mismatch_details.keys())

    bank_timeline_html = ''
    if chrono_months:
        # year-label row
        lbl_cells = ''
        for _idx in chrono_months:
            try:
                _m = _dt2.strptime(str(_idx), '%B, %Y')
                lbl_cells += (f'<div class="bt-lbl-cell"><span>{_m.year}</span></div>'
                              if _m.month == 1 else '<div class="bt-lbl-cell"></div>')
            except Exception:
                lbl_cells += '<div class="bt-lbl-cell"></div>'

        cells_html = ''
        for _idx in chrono_months:
            try:
                _ym = _dt2.strptime(str(_idx), '%B, %Y').strftime('%Y-%m')
            except Exception:
                _ym = ''
            _covered = _ym in _bank_covered
            _has_card = _idx in months_with_card_data
            if _covered:
                _bn = _bank_covered[_ym]
                if _ym in _mismatch_months:
                    _tip = f'בנק לאומי|⚠ חוסר עסקאות אפשרי — {_esc(_bn[:35])}|{_esc(str(_idx))}'
                    _cls = 'bt-cell warn'
                    _idate = index_dates.get(_idx)
                    if _idate and recent_cutoff and _idate >= recent_cutoff:
                        _chip = (f'<span class="alert-chip chip-yellow">'
                                 f'⚠ אי-התאמה בנקאית — {_esc(str(_idx))}</span>')
                        recent_chips.append((3, _chip))
                else:
                    _tip = f'בנק לאומי|✓ מכוסה — {_esc(_bn[:35])}|{_esc(str(_idx))}'
                    _cls = 'bt-cell covered'
            elif _has_card:
                _tip = f'בנק לאומי|✗ ללא כיסוי בנק|{_esc(str(_idx))}'
                _cls = 'bt-cell gap'
                _idate = index_dates.get(_idx)
                if _idate and recent_cutoff and _idate >= recent_cutoff:
                    _chip = (f'<span class="alert-chip chip-red">'
                             f'✗ בנק לאומי — {_esc(str(_idx))}</span>')
                    recent_chips.append((4, _chip))
            else:
                _tip = f'בנק לאומי|— אין עסקאות|{_esc(str(_idx))}'
                _cls = 'bt-cell na'
            _dm = f' data-month="{_ym}"' if _cls == 'bt-cell warn' else ''
            cells_html += f'<div class="{_cls}" data-tip="{_tip}"{_dm}></div>'

        # re-sort chips after adding bank gaps
        recent_chips.sort(key=lambda x: -x[0])

        _info_popup = (
            '<div class="bt-info-popup">'
            '<b>כיצד מחושב הכיסוי?</b><br>'
            'הגרף מציג כיסוי לפי <b>עסקאות</b> שנמצאות בטבלת BankTransactions.<br><br>'
            '<b style="color:#22c55e">&#x2713; ירוק</b> — ייבאת קובץ בנק (FibiSave*.xls) '
            'לחודש זה; העמודה מציגה את שם הקובץ.<br>'
            '<b style="color:#f59e0b">&#x26A0; כתום</b> — יש עסקאות בנק אך '
            'נמצאה אי-התאמה בולנס — ייתכן שחסרות עסקאות.<br>'
            '<b style="color:#ef4444">&#x2717; אדום</b> — יש נתוני כרטיסים לחודש אך '
            'אין עסקאות בנק — קובץ לא יובא.<br>'
            '<b style="color:#9ca3af">&#x2014; אפור</b> — אין נתונים כלל לחודש זה.<br><br>'
            'עמודות ה-Bank וה-Bank Range הוסרו מהטבלה המרכזית כי לא היו מיוצגות שם כראוי '
            '— הגרף הזה מחליף אותן.'
            '</div>'
        )
        bank_timeline_html = (
            f'<div class="bank-timeline">'
            f'<div class="bt-title-row">'
            f'<span class="bt-title">כיסוי בנק לאומי</span>'
            f'<button class="bt-info-btn" tabindex="-1">i{_info_popup}</button>'
            f'</div>'
            f'<div class="bt-chart">'
            f'<div class="bt-track"><span class="bt-track-lbl"></span>'
            f'<div class="bt-cells">{lbl_cells}</div></div>'
            f'<div class="bt-track">'
            f'<span class="bt-track-lbl">עסקאות</span>'
            f'<div class="bt-cells">{cells_html}</div>'
            f'</div></div></div>'
        )
        if _mismatch_details:
            import json as _json
            _md_json = _json.dumps(_mismatch_details, ensure_ascii=False, default=str)
            bank_timeline_html += (
                '<style>'
                '#bt-detail{margin-top:10px;padding:14px 16px;background:#1a2540;'
                'border-radius:8px;border-left:3px solid #f59e0b;display:none;'
                'font-size:.82em;direction:rtl;text-align:right}'
                '#bt-detail.open{display:block}'
                '.btd-title{color:#f59e0b;font-weight:700;margin-bottom:8px;font-size:.95em}'
                '.btd-row{margin:3px 0;color:#cbd5e1;line-height:1.6}'
                '.btd-row b{color:#e2e8f0}'
                '.btd-val{font-family:monospace;color:#fbbf24}'
                '.btd-lbl{color:#94a3b8;font-size:.85em;margin:8px 0 2px}'
                '.btd-span-row{margin:2px 0 2px 1.2em;color:#94a3b8}'
                '.btd-span-row .btd-val{color:#cbd5e1}'
                '.btd-calc{margin-top:8px;padding-top:6px;border-top:1px solid #2d3748}'
                '.btd-sep{border:none;border-top:1px solid #374151;margin:12px 0}'
                '.btd-close{float:left;cursor:pointer;color:#64748b;font-size:1.1em;background:none;'
                'border:none;padding:0;line-height:1}'
                '.btd-close:hover{color:#94a3b8}'
                '</style>'
                '<div id="bt-detail" dir="rtl">'
                '<button class="btd-close" onclick="this.parentElement.classList.remove(\'open\')">✕</button>'
                '<div id="bt-detail-body"></div>'
                '</div>'
                f'<script>(function(){{'
                f'var DATA={_md_json};'
                'function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}'
                'function famt(r){return r.income>0?"+ "+r.income.toFixed(2):r.out>0?"- "+r.out.toFixed(2):"0";}'
                'function frow(r,cls){'
                'var s=\'<div class="\'+cls+\'"><b>\'+esc(r.name)+\'</b>\';'
                's+=\' &nbsp;|&nbsp; \'+famt(r);'
                'if(r.balance!==undefined)s+=\' &nbsp;|&nbsp; יתרה: <span class="btd-val">\'+r.balance.toFixed(2)+\'</span>\';'
                's+=\' &nbsp;|&nbsp; ID: <span class="btd-val">\'+r.id+\'</span>\';'
                's+=\' &nbsp;|&nbsp; \'+esc(r.date);'
                's+=\' &nbsp;|&nbsp; <span class="btd-val">\'+esc(r.file)+\'</span></div>\';'
                'return s;}'
                'document.querySelectorAll(".bt-cell.warn").forEach(function(el){'
                'el.style.cursor="pointer";'
                'el.addEventListener("click",function(){'
                'var ym=el.getAttribute("data-month");'
                'var items=DATA[ym]||[];'
                'if(!items.length)return;'
                'var h=\'<div class="btd-title">⚠ אי-התאמה בבנק לאומי — \'+esc(ym)+\'</div>\';'
                'items.forEach(function(m,i){'
                'if(i>0)h+=\'<hr class="btd-sep">\';'
                'h+=\'<div class="btd-lbl">⚓ עוגן (יתרה ידועה אחרונה):</div>\';'
                'h+=frow(m.anchor,"btd-row");'
                'if(m.span&&m.span.length){'
                'h+=\'<div class="btd-lbl">עסקאות ביניים (\'+m.span.length+\'):</div>\';'
                'm.span.forEach(function(r){h+=frow(r,"btd-span-row");});'
                '}'
                'h+=\'<div class="btd-lbl">🔸 עסקה עם אי-התאמה:</div>\';'
                'h+=frow(m.current,"btd-row");'
                'h+=\'<div class="btd-calc">יתרה מחושבת: <span class="btd-val">\'+m.calc.toFixed(2)+\'</span>\';'
                'h+=\' &nbsp;&nbsp; יתרה רשומה: <span class="btd-val">\'+m.stored.toFixed(2)+\'</span>\';'
                'h+=\' &nbsp;&nbsp; הפרש: <span class="btd-val">\'+m.diff.toFixed(2)+\'</span></div>\';'
                '});'
                'document.getElementById("bt-detail-body").innerHTML=h;'
                'var panel=document.getElementById("bt-detail");'
                'panel.classList.add("open");'
                'panel.scrollIntoView({behavior:"smooth",block:"nearest"});'
                '});'
                '});'
                f'}})();</script>'
            )

    # ── alert content ─────────────────────────────────────────────────────────
    if not recent_chips and not older_chips:
        alert_content = ('<div class="all-good"><span class="all-good-icon">✓</span>'
                         'הכל תקין — כל הקבצים מאומתים'
                         '<span class="all-good-sub">(עדכון: <!--GENERATED_DATE-->)</span></div>')
    else:
        recent_html = ''.join(h for _, h in recent_chips)
        older_html  = ''.join(h for _, h in older_chips)
        alert_content = ''
        if recent_chips:
            alert_content += (f'<div class="alert-section-title">בעיות אחרונות (6 חודשים)</div>'
                              f'<div class="alert-chips">{recent_html}</div>')
        else:
            alert_content += ('<div class="all-good" style="margin-bottom:8px"><span class="all-good-icon">✓</span>'
                              'אין בעיות בחודשים האחרונים</div>')
        if older_chips:
            alert_content += (f'<button class="older-toggle" id="older-btn" onclick="toggleOlder()">'
                              f'▸ הצג בעיות ישנות</button>'
                              f'<div class="older-section" id="older-section">'
                              f'<div class="alert-chips">{older_html}</div></div>')

    # ── heatmap header ────────────────────────────────────────────────────────
    hm_header = '<tr><th></th>'
    for col in hm_cols:
        hm_header += f'<th class="hm-th-wrap"><div class="hm-th">{_esc(_abbrev(col))}</div></th>'
    hm_header += '</tr>'

    # ── heatmap rows (add divider between recent and older) ───────────────────
    hm_rows = ''
    prev_recent = None
    for is_recent, row_html in hm_row_parts:
        if prev_recent and not is_recent:
            row_html = row_html.replace('<tr>', '<tr class="hm-divider-row">', 1)
        hm_rows += row_html + '\n'
        prev_recent = is_recent

    from datetime import datetime as _now
    html = _ORGANIZER_HTML \
        .replace('<!--ALERT_CONTENT-->', alert_content) \
        .replace('<!--BANK_TIMELINE-->', bank_timeline_html) \
        .replace('<!--HM_HEADER-->', hm_header) \
        .replace('<!--HM_ROWS-->', hm_rows) \
        .replace('<!--GENERATED_DATE-->', _now.now().strftime('%d/%m/%Y %H:%M'))

    with open(ORGANIZER_HTML, 'w', encoding='utf-8') as _f:
        _f.write(html)

    return html



@app.route('/organizer')
def organizer_page():
    if os.path.exists(ORGANIZER_HTML):
        return send_file(ORGANIZER_HTML)
    return _organizer_splash()


@app.route('/api/organizer/regenerate')
def organizer_regenerate():
    import queue as _q

    pq = _q.Queue()

    def _run():
        try:
            # read_present_table drives 0-100 internally but only covers ~75% of
            # the total work; scale it to 0-75 so the remaining stages (HTML build,
            # file write, manifest) fill the rest of the bar accurately.
            def _scaled(p):
                pq.put(int(p * 0.75))

            deps, db_mtime = _capture_deps_and_run(
                lambda: _build_organizer_page(progress_callback=_scaled)
            )
            pq.put(88)   # HTML built and written to disk
            if os.path.exists(ORGANIZER_HTML):
                _save_manifest(ORGANIZER_HTML, deps, db_mtime)
            pq.put(95)   # manifest saved
            pq.put('done')
        except Exception as exc:
            pq.put(f'error:{exc}')

    threading.Thread(target=_run, daemon=True).start()

    def _generate():
        while True:
            val = pq.get()
            if val == 'done':
                yield 'data: 100\n\n'
                yield 'data: done\n\n'
                break
            elif isinstance(val, str) and val.startswith('error:'):
                yield 'data: error\n\n'
                break
            else:
                yield f'data: {val}\n\n'

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Tagger routes ─────────────────────────────────────────────────────────────

@app.route('/tagger')
def tagger_page():
    if os.path.exists(TAGGER_HTML):
        return send_file(TAGGER_HTML)
    return "Tagger page not found", 404


@app.route('/api/tagger/untagged')
def tagger_untagged():
    from database import DataBase
    try:
        db    = DataBase()
        rows  = db.get_untagged_recent(limit=2000)
        total = db.count_untagged_total()
        return jsonify({'ok': True, 'items': rows, 'total': total})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/tagged')
def tagger_tagged():
    from database import DataBase
    try:
        rows = DataBase().get_recently_tagged(limit=30)
        return jsonify({'ok': True, 'items': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/high-value')
def tagger_high_value():
    from database import DataBase
    try:
        threshold = float(request.args.get('threshold', 500))
        rows = DataBase().get_high_value_untagged(threshold=threshold)
        return jsonify({'ok': True, 'items': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


def _read_at() -> dict:
    import json as _j
    from Constants import Paths as _Paths
    if os.path.exists(_Paths.AUTO_TAGGER_JSON):
        with open(_Paths.AUTO_TAGGER_JSON, encoding='utf-8-sig') as _f:
            return _j.load(_f)
    return {}

def _write_at(d: dict):
    import json as _j
    from Constants import Paths as _Paths
    with open(_Paths.AUTO_TAGGER_JSON, 'w', encoding='utf-8') as _f:
        _j.dump(d, _f, ensure_ascii=False)


@app.route('/api/tagger/tag', methods=['POST'])
def tagger_tag():
    """Tag a single transaction by id."""
    from database import DataBase
    body    = request.get_json() or {}
    table   = (body.get('table')    or '').strip()
    id_     = body.get('id')
    cat     = (body.get('category') or '').strip()
    is_auto = bool(body.get('auto', False))

    description = (body.get('description') or '').strip()

    if not table or id_ is None or not cat:
        return jsonify({'ok': False, 'error': 'missing fields'})
    if table not in ('CardTransactions', 'BankTransactions'):
        return jsonify({'ok': False, 'error': 'invalid table'})
    try:
        DataBase().set_category_ui(table, int(id_), cat, is_auto=is_auto)
        if description:
            DataBase().set_transaction_description(description, table, int(id_))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/tag-all-by-name', methods=['POST'])
def tagger_tag_all_by_name():
    """Tag every untagged transaction matching name (across both tables) and save json rule."""
    from database import DataBase
    body = request.get_json() or {}
    name = (body.get('name') or '').strip()
    cat  = (body.get('category') or '').strip()
    if not name or not cat:
        return jsonify({'ok': False, 'error': 'missing fields'})
    try:
        db    = DataBase()
        rows  = db.get_untagged_recent(limit=5000)
        count = 0
        for row in rows:
            if row['name'] == name:
                db.set_category_ui(row['table_name'], row['id'], cat, is_auto=False)
                count += 1
        # Save rule to auto_tagger.json
        at = _read_at()
        at[name] = cat
        _write_at(at)
        return jsonify({'ok': True, 'tagged': count})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/name-rule')
def tagger_name_rule():
    """Return the auto_tagger.json entry for a given name."""
    name = (request.args.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'missing name'})
    try:
        at     = _read_at()
        in_dict = name in at
        rule   = at.get(name)          # None / "No Match" / category string
        return jsonify({'ok': True, 'in_dict': in_dict, 'rule': rule})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/save-rule', methods=['POST'])
def tagger_save_rule():
    """Force-save a name→rule pair to auto_tagger.json (rule = category or 'No Match')."""
    body = request.get_json() or {}
    name = (body.get('name') or '').strip()
    rule = body.get('rule')           # None / "No Match" / category string
    if not name:
        return jsonify({'ok': False, 'error': 'missing name'})
    try:
        at = _read_at()
        at[name] = rule
        _write_at(at)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/categories')
def tagger_categories():
    import json as _json
    try:
        cats_path = os.path.join(_PROJECT_DIR, 'personal information', 'categories.json')
        with open(cats_path, encoding='utf-8-sig') as f:
            cats = _json.load(f)
        db = None
        try:
            from database import DataBase
            db = DataBase()
            usage = db.count_category_usages()
        except Exception:
            usage = {}
        result = [{'name': c, 'count': usage.get(c, 0)} for c in cats]
        result.sort(key=lambda x: -x['count'])
        return jsonify({'ok': True, 'categories': result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/card-colors')
def tagger_card_colors():
    """Return {card_id: hex_color}, matching the same palette assignment used
    for card_color_dict in the monthly/general analysis charts, so a card's
    color stays consistent across the whole app."""
    try:
        from database import DataBase
        from Constants import Local
        card_ids = DataBase().get_card_ids()
        color_list = Local.Colors[:len(card_ids)]
        colors = {str(cid): color for cid, color in zip(card_ids, color_list)}
        return jsonify({'ok': True, 'colors': colors})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/categories/add', methods=['POST'])
def tagger_categories_add():
    import json as _json
    body = request.get_json() or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'missing name'})
    try:
        cats_path = os.path.join(_PROJECT_DIR, 'personal information', 'categories.json')
        with open(cats_path, encoding='utf-8-sig') as f:
            cats = _json.load(f)
        if name in cats:
            return jsonify({'ok': False, 'error': 'category already exists'})
        cats.append(name)
        with open(cats_path, 'w', encoding='utf-8') as f:
            _json.dump(cats, f, ensure_ascii=False, indent=2)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/rules')
def tagger_rules():
    """Return all auto_tagger.json entries that map to a real category (not null/No Match),
    with count of auto-tagged transactions per name."""
    from database import DataBase
    try:
        at    = _read_at()
        db    = DataBase()
        usage = db.count_auto_tagged_per_name()
        rules = [
            {'name': name, 'category': cat, 'count': usage.get(name, 0)}
            for name, cat in at.items()
            if cat and cat != 'No Match'
        ]
        rules.sort(key=lambda x: -x['count'])
        return jsonify({'ok': True, 'rules': rules})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/rules/remap', methods=['POST'])
def tagger_rules_remap():
    """Change category for a business-name rule: update auto_tagger.json + all auto-tagged rows."""
    import json as _json
    from database import DataBase
    body    = request.get_json() or {}
    name    = (body.get('name')         or '').strip()
    new_cat = (body.get('new_category') or '').strip()
    if not name or not new_cat:
        return jsonify({'ok': False, 'error': 'missing fields'})
    cats_path = os.path.join(_PROJECT_DIR, 'personal information', 'categories.json')
    try:
        with open(cats_path, encoding='utf-8-sig') as f:
            cats = _json.load(f)
        if new_cat not in cats:
            return jsonify({'ok': False, 'error': 'category not found'})
        at = _read_at()
        at[name] = new_cat
        _write_at(at)
        updated = DataBase().remap_auto_tagged(name, new_cat)
        return jsonify({'ok': True, 'updated': updated})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/tagger/search-tagged')
def tagger_search_tagged():
    """Search tagged transactions by name (partial match) or exact numeric ID."""
    from database import DataBase
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'ok': False, 'error': 'missing query'})
    try:
        rows = DataBase().search_tagged(q)
        return jsonify({'ok': True, 'items': rows})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


# ── Files routes ──────────────────────────────────────────────────────────────

if os.getenv('VERCEL'):  # Vercel: /var/task is read-only; use /tmp
    _INPUT_FOLDER    = '/tmp/ShmuelFamiliy_Inputs'
    _VERIFIED_FOLDER = '/tmp/Verified_ShmuelFamiliy_Inputs'
else:
    _INPUT_FOLDER    = os.path.join(_PROJECT_DIR, 'ShmuelFamiliy_Inputs')
    _VERIFIED_FOLDER = os.path.join(_PROJECT_DIR, 'Verified_ShmuelFamiliy_Inputs')
_INSERT_LOCK = threading.Lock()  # prevent concurrent parses


@app.route('/files')
def files_page():
    if os.path.exists(FILES_HTML):
        return send_file(FILES_HTML)
    return 'Files page not found', 404


@app.route('/api/files/scan')
def files_scan():
    """Scan the input folder and classify files as recognized / unrecognized."""
    import builtins as _bt
    try:
        import sys as _sys
        if _HERE not in _sys.path:
            _sys.path.insert(0, _HERE)

        _orig_input = _bt.input
        _bt.input = lambda *a, **k: '1'
        try:
            from Parser import Parser
            from database import DataBase
            parser = Parser.getInstance(newInstance=True)
        finally:
            _bt.input = _orig_input

        recognized   = []
        unrecognized = []

        import shutil as _shutil

        # Pre-load all known filenames from the DB so we don't rely solely on
        # the parser (which can't open locked files).
        _db_known = {}   # fname -> format
        _conn = None
        try:
            _conn = _pg_conn()
            for _row in _conn.execute("SELECT File_Name, Format FROM File"):
                _db_known[_row[0]] = _row[1]
        except Exception:
            pass
        finally:
            if _conn is not None:
                _conn.close()

        if os.path.isdir(_INPUT_FOLDER):
            for fname in sorted(os.listdir(_INPUT_FOLDER)):
                fpath = os.path.join(_INPUT_FOLDER, fname)
                if not os.path.isfile(fpath):
                    continue

                # ── Already in DB? ────────────────────────────────────────
                db_fmt = _db_known.get(fname)
                if db_fmt:
                    # File was previously processed. Try to move it to Verified.
                    dst_dir  = os.path.join(_VERIFIED_FOLDER, db_fmt)
                    dst_file = os.path.join(dst_dir, fname)
                    try:
                        os.makedirs(dst_dir, exist_ok=True)
                        if os.path.isfile(dst_file):
                            # Already at destination — previous move copied but couldn't
                            # delete the source (file was open).  Remove the source now.
                            os.remove(fpath)
                        else:
                            _shutil.move(fpath, dst_file)
                        continue   # cleaned up — don't show in list
                    except Exception:
                        pass       # still locked — show as "already exists"
                    recognized.append({'name': fname, 'format': db_fmt, 'is_new': False})
                    continue

                # ── Not in DB — use parser to identify ────────────────────
                fmt = parser.name_to_type.get(fname)
                if fmt:
                    recognized.append({'name': fname, 'format': fmt, 'is_new': True})
                else:
                    reasons = parser.diagnose_identification(fname)
                    details = '; '.join(
                        f'{f}: {r}' for f, r in reasons if r != 'matched'
                    ) or None
                    unrecognized.append({'name': fname, 'details': details})

        return jsonify({'ok': True, 'recognized': recognized, 'unrecognized': unrecognized})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/files/insert', methods=['POST'])
def files_insert():
    """Parse and insert a single file — runs in background thread; logs stream via /api/logs."""
    body     = request.get_json() or {}
    filename = (body.get('filename') or '').strip()
    if not filename:
        return jsonify({'ok': False, 'error': 'missing filename'})

    if not _INSERT_LOCK.acquire(blocking=False):
        return jsonify({'ok': False, 'error': 'כבר מתבצע עיבוד, נסה שוב בעוד רגע'})

    # Drain stale messages from any previous run
    while not _log_queue.empty():
        try:
            _log_queue.get_nowait()
        except queue.Empty:
            break

    def _worker():
        import builtins as _bt
        _orig_input = _bt.input
        _bt.input = lambda *a, **k: '1'
        try:
            import sys as _sys
            if _HERE not in _sys.path:
                _sys.path.insert(0, _HERE)

            from Parser import Parser
            from Context import Context
            from Configurations.Formats import Formats, Context_class
            from Card import Card
            from Bank import Bank
            from src_utils.utils import utils

            # Reuse the Parser instance from the last scan — re-identifying files
            # from scratch can fail if the target file is transiently locked.
            parser = Parser.getInstance()
            fmt = parser.name_to_type.get(filename)
            if not fmt:
                parser = Parser.getInstance(newInstance=True)
                fmt = parser.name_to_type.get(filename)
            if not fmt:
                reasons = parser.diagnose_identification(filename)
                details = '; '.join(
                    f'{f}: {r}' for f, r in reasons if r != 'matched'
                ) or 'לא ניתן לאבחן'
                utils.log(f'קובץ לא מזוהה: {filename} — {details}', 'error')
                _log_queue.put('__ERROR__')
                return

            fmt_data   = Formats.FORMATS[fmt]
            class_type = fmt_data['Context']

            context = Context()
            Context.counter = 0

            if class_type == Context_class.Bank:
                context.setFile(Bank(filename, fmt_data))
            elif class_type == Context_class.Card:
                context.setFile(Card(filename, fmt_data))
            else:
                utils.log('סוג קובץ לא נתמך', 'error')
                _log_queue.put('__ERROR__')
                return

            Context.counter += 1
            success = context.render()

            if success:
                utils.handle_withdrawals()
                utils.handle_direct_bank_withdrawals()
                utils.tagger_refresh()

            _log_queue.put(f'__DONE__:{filename}' if success else '__ERROR__')

        except Exception as e:
            import traceback
            _log_error(e, traceback.format_exc())
            _log_queue.put('__ERROR__')
        finally:
            _bt.input = _orig_input
            _INSERT_LOCK.release()

    threading.Thread(target=_worker, daemon=True, name='insert-worker').start()
    return jsonify({'status': 'started', 'filename': filename})


@app.route('/api/files/insert-all', methods=['POST'])
def files_insert_all():
    """Parse and insert all NEW (unprocessed) files from the input folder."""
    import builtins as _bt
    if not _INSERT_LOCK.acquire(blocking=False):
        return jsonify({'ok': False, 'error': 'כבר מתבצע עיבוד, נסה שוב בעוד רגע'})

    try:
        import sys as _sys
        if _HERE not in _sys.path:
            _sys.path.insert(0, _HERE)

        _orig_input = _bt.input
        _bt.input = lambda *a, **k: '1'
        try:
            from Parser import Parser
            from Context import Context
            from Configurations.Formats import Formats, Context_class
            from Card import Card
            from Bank import Bank
            from src_utils.utils import utils

            parser = Parser.getInstance()
            results = []

            context = Context()
            Context.counter = 0

            for fname in list(parser.names):   # parser.names = new files only
                fmt      = parser.name_to_type.get(fname)
                if not fmt:
                    results.append({'filename': fname, 'ok': False, 'error': 'unrecognized'})
                    continue
                fmt_data   = Formats.FORMATS[fmt]
                class_type = fmt_data['Context']

                if class_type == Context_class.Bank:
                    context.setFile(Bank(fname, fmt_data))
                elif class_type == Context_class.Card:
                    context.setFile(Card(fname, fmt_data))
                else:
                    results.append({'filename': fname, 'ok': False, 'error': 'unsupported type'})
                    continue

                Context.counter += 1
                try:
                    ok = context.render()
                    results.append({'filename': fname, 'ok': ok, 'format': fmt})
                except Exception as ex:
                    results.append({'filename': fname, 'ok': False, 'error': str(ex)})

            if any(r['ok'] for r in results):
                utils.handle_withdrawals()
                utils.handle_direct_bank_withdrawals()
                utils.tagger_refresh()

            return jsonify({'ok': True, 'results': results})
        finally:
            _bt.input = _orig_input
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        _INSERT_LOCK.release()


@app.route('/api/files/upload', methods=['POST'])
def files_upload():
    """Accept a file upload and save it to the input folder."""
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'no file'})
    fname = os.path.basename(f.filename)
    # Strip characters invalid on Windows/most filesystems; keep Hebrew/Unicode intact
    fname = _re.sub(r'[<>:"|?*\x00-\x1f]', '_', fname).strip(' .')
    if not fname:
        return jsonify({'ok': False, 'error': 'invalid filename'})
    try:
        os.makedirs(_INPUT_FOLDER, exist_ok=True)
        dest = os.path.join(_INPUT_FOLDER, fname)
        f.save(dest)
    except OSError as e:
        return jsonify({'ok': False, 'error': f'שגיאה בשמירת הקובץ: {e}'})
    return jsonify({'ok': True, 'filename': fname})


@app.route('/api/files/db-files')
def files_db_list():
    """Return all rows from the File table (files already in the database)."""
    conn = None
    try:
        conn = _pg_conn()
        rows = conn.execute('''
            SELECT File_Name, Format, Card_Number, Date,
                   New_Transactions, Transaction_count, Last_update
            FROM File
            ORDER BY Date DESC, Last_update DESC
        ''').fetchall()

        files = []
        total_tx = 0
        for r in rows:
            card = r['card_number']
            if not card or str(card).lower() in ('not_relevant', 'none', ''):
                card = None
            files.append({
                'name':             r['file_name'],
                'format':           r['format'],
                'card':             card,
                'date':             str(r['date'] or '')[:10],
                'new_transactions': r['new_transactions'] or 0,
                'transaction_count': r['transaction_count'] or 0,
                'last_update':      str(r['last_update'] or '')[:10],
            })
            total_tx += r['transaction_count'] or 0

        return jsonify({'ok': True, 'files': files, 'total_transactions': total_tx})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/transactions/split-info')
def tx_split_info():
    """Return original transaction details + its splits."""
    tbl = (request.args.get('table') or '').strip()
    oid = request.args.get('id', type=int)
    if tbl not in ('BankTransactions', 'CardTransactions') or oid is None:
        return jsonify({'ok': False, 'error': 'invalid table or id'})
    conn = None
    try:
        conn = _pg_conn()
        # Fetch original row
        if tbl == 'BankTransactions':
            row = conn.execute(
                'SELECT ID, Name, Category, Description, Out, Income, Date FROM BankTransactions WHERE ID=%s', (oid,)
            ).fetchone()
            if not row:
                return jsonify({'ok': False, 'error': 'not found'})
            amount = float(row['income'] or 0) - float(row['out'] or 0)
            orig = {'id': row['id'], 'name': row['name'], 'category': row['category'] or '',
                    'description': row['description'] or '', 'amount': amount,
                    'date': str(row['date'] or '')[:10]}
        else:
            row = conn.execute(
                'SELECT ID, Name, Category, Description, Transaction_Value, Executed_Date FROM CardTransactions WHERE ID=%s', (oid,)
            ).fetchone()
            if not row:
                return jsonify({'ok': False, 'error': 'not found'})
            orig = {'id': row['id'], 'name': row['name'], 'category': row['category'] or '',
                    'description': row['description'] or '',
                    'amount': float(row['transaction_value'] or 0),
                    'date': str(row['executed_date'] or '')[:10]}
        # Fetch splits
        splits_rows = conn.execute(
            'SELECT ID, Amount, Description, Category FROM TransactionSplits WHERE Original_Table=%s AND Original_ID=%s ORDER BY ID',
            (tbl, oid)
        ).fetchall()
        splits = [{'id': r['id'], 'amount': float(r['amount']),
                   'description': r['description'] or '', 'category': r['category']} for r in splits_rows]
        return jsonify({'ok': True, 'original': orig, 'splits': splits})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        if conn is not None:
            conn.close()


def _regen_month_for_tx(tbl: str, tx_id: int) -> None:
    """
    Background helper: look up the transaction date, then regenerate the
    monthly HTML so split changes are reflected on the next page load.
    """
    conn = None
    try:
        col  = 'Date' if tbl == 'BankTransactions' else 'Executed_Date'
        conn = _pg_conn()
        row  = conn.execute(f'SELECT {col} FROM {tbl} WHERE ID=%s', (tx_id,)).fetchone()
        if not row or not row[0]:
            return
        from datetime import datetime as _dt2
        t = _dt2.strptime(str(row[0])[:10], '%Y-%m-%d')
        from AppManager import AppManager as _AM
        _AM(skip_parser=True).general_analysis(t=t)
    except Exception as _e:
        print(f'[split regen] {_e}')
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/transactions/split', methods=['POST'])
def tx_split_create():
    """Create split rows for a transaction."""
    body   = request.get_json(force=True) or {}
    tbl    = (body.get('table') or '').strip()
    tx_id  = body.get('id')
    splits = body.get('splits') or []
    if tbl not in ('BankTransactions', 'CardTransactions') or not tx_id or len(splits) < 2:
        return jsonify({'ok': False, 'error': 'invalid request'})
    # Validate each split
    for s in splits:
        if not s.get('category') or not s.get('amount') or float(s['amount']) <= 0:
            return jsonify({'ok': False, 'error': 'each split needs amount > 0 and category'})
    try:
        from database import DataBase as _DB3
        db = _DB3()
        # Make sure not already split
        existing = db.get_splits_for_transaction(tbl, int(tx_id))
        if existing:
            return jsonify({'ok': False, 'error': 'transaction is already split'})
        created_ids = db.create_splits(tbl, int(tx_id), splits)
        db.commit_changes()
        result_splits = [{'split_id': sid, 'amount': float(splits[i]['amount']),
                          'description': splits[i].get('description', ''),
                          'category': splits[i]['category']}
                         for i, sid in enumerate(created_ids)]
        # Regenerate the monthly HTML in the background so the split is
        # visible on next page load without a manual analysis run.
        threading.Thread(target=_regen_month_for_tx, args=(tbl, int(tx_id)),
                         daemon=True, name='split-regen').start()
        return jsonify({'ok': True, 'splits': result_splits})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/transactions/revert-split', methods=['POST'])
def tx_split_revert():
    """Remove all splits for a transaction, restoring the original."""
    body = request.get_json(force=True) or {}
    tbl  = (body.get('table') or '').strip()
    oid  = body.get('id')
    if tbl not in ('BankTransactions', 'CardTransactions') or oid is None:
        return jsonify({'ok': False, 'error': 'invalid table or id'})
    try:
        from database import DataBase as _DB4
        db = _DB4()
        deleted = db.revert_splits(tbl, int(oid))
        db.commit_changes()
        # Regenerate the monthly HTML so the revert is visible on next page load.
        threading.Thread(target=_regen_month_for_tx, args=(tbl, int(oid)),
                         daemon=True, name='revert-regen').start()
        return jsonify({'ok': True, 'deleted': deleted})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/files/delete', methods=['POST'])
def files_delete():
    """Delete a file entry and all its transactions from the database."""
    body = request.get_json(force=True) or {}
    name = (body.get('name') or '').strip()
    fmt  = (body.get('format') or '').strip()
    card = (body.get('card') or '').strip()
    if not name or not fmt:
        return jsonify({'ok': False, 'error': 'missing name or format'})
    try:
        from database import DataBase as _DB2
        db = _DB2()
        if not card:
            row = db.cursor.execute(
                'SELECT Card_Number FROM File WHERE File_Name = %s AND Format = %s',
                (name, fmt)
            ).fetchone()
            if row:
                card = row[0] or ''
        db.drop_file(name, fmt, card)
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


BILLS_HTML = os.path.join(_HERE, 'html', 'Bills.html')

# ── Bills tracker routes ───────────────────────────────────────────────────────

@app.route('/bills')
def bills_page():
    try:
        from database import DataBase
        DataBase().ensure_bill_tables()
    except Exception:
        pass
    if os.path.exists(BILLS_HTML):
        return send_file(BILLS_HTML)
    return "Bills page not found", 404


@app.route('/api/bills/types', methods=['GET', 'POST'])
def api_bills_types():
    from database import DataBase
    try:
        db = DataBase()
        if request.method == 'GET':
            return jsonify({'ok': True, 'types': db.get_bill_types()})
        body = request.get_json(force=True) or {}
        name  = (body.get('name')  or '').strip()
        color = (body.get('color') or '#1e9d8b').strip()
        if not name:
            return jsonify({'ok': False, 'error': 'Name required'})
        group = (body.get('group') or '').strip()
        tid = db.add_bill_type(name, color, group)
        db.commit_changes()
        return jsonify({'ok': True, 'id': tid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/types/<int:type_id>', methods=['PUT', 'DELETE'])
def api_bills_type(type_id):
    from database import DataBase
    try:
        db = DataBase()
        if request.method == 'PUT':
            body  = request.get_json(force=True) or {}
            name  = (body.get('name')  or '').strip()
            color = (body.get('color') or '#1e9d8b').strip()
            group = (body.get('group') or '').strip()
            if not name:
                return jsonify({'ok': False, 'error': 'Name required'})
            db.update_bill_type(type_id, name, color, group)
            db.commit_changes()
            return jsonify({'ok': True})
        db.delete_bill_type(type_id)
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/entries', methods=['GET', 'POST'])
def api_bills_entries():
    from database import DataBase
    try:
        db = DataBase()
        if request.method == 'GET':
            return jsonify({'ok': True, 'entries': db.get_bill_entries()})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    body = request.get_json(force=True) or {}
    try:
        overlap = db.check_bill_entry_overlap(
            int(body['bill_type_id']), body['start_month'], body['end_month']
        )
        if overlap:
            return jsonify({'ok': False, 'error': overlap})
        # is_filler is derived, never trusted from the client — a bar is only
        # ever "real" (colored) once it actually has a matched transaction.
        eid = db.add_bill_entry(
            bill_type_id      = int(body['bill_type_id']),
            start_month       = body['start_month'],
            end_month         = body['end_month'],
            transaction_table = body.get('transaction_table'),
            transaction_id    = body.get('transaction_id'),
            amount            = body.get('amount'),
            note              = body.get('note', ''),
            is_filler         = body.get('transaction_id') is None,
        )
        db.commit_changes()
        return jsonify({'ok': True, 'id': eid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/entries/<int:entry_id>', methods=['PUT', 'DELETE'])
def api_bills_entry(entry_id):
    from database import DataBase
    try:
        db = DataBase()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    if request.method == 'DELETE':
        try:
            db.delete_bill_entry(entry_id)
            db.commit_changes()
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})
    body = request.get_json(force=True) or {}
    try:
        current = db.cursor.execute(
            "SELECT BillType_ID, Transaction_Table, Transaction_ID, Amount, Note, "
            "Secondary_Transaction_Table, Secondary_Transaction_ID "
            "FROM BillEntries WHERE ID=%s", (entry_id,)
        ).fetchone()
        if not current:
            return jsonify({'ok': False, 'error': 'רשומה לא נמצאה'})

        # A field's absence from the request body means "leave it alone", not
        # "clear it" — editing just the note or dragging the dates must not
        # silently detach an already-linked transaction (and its amount).
        transaction_table = body['transaction_table'] if 'transaction_table' in body else current[1]
        transaction_id    = body['transaction_id']    if 'transaction_id'    in body else current[2]
        amount            = body['amount']            if 'amount'            in body else current[3]
        note              = body['note']              if 'note'             in body else current[4]
        sec_table = body['secondary_transaction_table'] if 'secondary_transaction_table' in body else current[5]
        sec_id    = body['secondary_transaction_id']    if 'secondary_transaction_id'    in body else current[6]
        # The only rule for the secondary transaction: it can't exist without a
        # primary one. If the primary is being cleared (or was never set),
        # silently drop the secondary too rather than erroring out.
        if transaction_id is None:
            sec_table, sec_id = None, None
        # is_filler is derived here, never trusted from the client — a bar is
        # only ever "real" (colored) when it actually has a matched
        # transaction; setting a price/note alone can't flip it.
        is_filler = transaction_id is None

        overlap = db.check_bill_entry_overlap(
            current[0], body['start_month'], body['end_month'], exclude_id=entry_id
        )
        if overlap:
            return jsonify({'ok': False, 'error': overlap})

        db.update_bill_entry(
            entry_id,
            start_month       = body['start_month'],
            end_month         = body['end_month'],
            note              = note,
            transaction_table = transaction_table,
            transaction_id    = transaction_id,
            amount            = amount,
            is_filler         = is_filler,
            secondary_transaction_table = sec_table,
            secondary_transaction_id    = sec_id,
        )
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/suggestions')
def api_bills_suggestions():
    conn = _pg_conn()
    try:
        from database import DataBase
        db = DataBase()
        dismissed = db.get_bill_suggestions_dismissed()

        linked = conn.execute("""
            SELECT DISTINCT b.Name FROM BillEntries e
            JOIN BankTransactions b
              ON e.Transaction_Table='BankTransactions' AND e.Transaction_ID=b.ID
            UNION
            SELECT DISTINCT c.Name FROM BillEntries e
            JOIN CardTransactions c
              ON e.Transaction_Table='CardTransactions' AND e.Transaction_ID=c.ID
        """).fetchall()
        linked_names = [r[0] for r in linked if r[0]]
        if not linked_names:
            return jsonify({'ok': True, 'suggestions': []})

        already = conn.execute(
            "SELECT Transaction_Table, Transaction_ID FROM BillEntries WHERE Transaction_Table IS NOT NULL"
            " UNION ALL "
            "SELECT Secondary_Transaction_Table, Secondary_Transaction_ID FROM BillEntries"
            " WHERE Secondary_Transaction_ID IS NOT NULL"
        ).fetchall()
        linked_bank = {r[1] for r in already if r[0] == 'BankTransactions'}
        linked_card = {r[1] for r in already if r[0] == 'CardTransactions'}

        # Filter out dismissed names upfront
        active_names = [n for n in linked_names if n not in dismissed]
        if not active_names:
            return jsonify({'ok': True, 'suggestions': []})

        # Fetch all matching rows in 2 queries (IN clause) instead of N×2 loops
        ph = ','.join(['?'] * len(active_names))
        bank_rows = conn.execute(
            f"SELECT ID, Date, Name, Out, Income FROM BankTransactions"
            f" WHERE Name IN ({ph}) ORDER BY Date DESC",
            tuple(active_names)
        ).fetchall()
        card_rows = conn.execute(
            f"SELECT ID, Executed_Date, Name, Transaction_Value FROM CardTransactions"
            f" WHERE Name IN ({ph}) ORDER BY Executed_Date DESC",
            tuple(active_names)
        ).fetchall()

        suggestions = []
        seen = set()
        for r in bank_rows:
            if r[0] in linked_bank or ('B', r[0]) in seen:
                continue
            seen.add(('B', r[0]))
            suggestions.append({
                'table': 'BankTransactions', 'id': r[0],
                'date': str(r[1] or '')[:10], 'name': r[2] or '',
                'amount': float(r[3] or 0) or float(r[4] or 0),
                'matched_name': r[2] or '',
            })
        for r in card_rows:
            if r[0] in linked_card or ('C', r[0]) in seen:
                continue
            seen.add(('C', r[0]))
            suggestions.append({
                'table': 'CardTransactions', 'id': r[0],
                'date': str(r[1] or '')[:10], 'name': r[2] or '',
                'amount': abs(float(r[3] or 0)),
                'matched_name': r[2] or '',
            })
        suggestions.sort(key=lambda x: x['date'], reverse=True)
        return jsonify({'ok': True, 'suggestions': suggestions[:100]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        conn.close()


@app.route('/api/bills/suggestions/dismiss', methods=['POST'])
def api_bills_suggestions_dismiss():
    from database import DataBase
    body = request.get_json(force=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'})
    try:
        db = DataBase()
        db.dismiss_bill_suggestion(name)
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


SPOTIFY_HTML = os.path.join(_HERE, 'html', 'SpotifyTracker.html')

# ── Spotify Tracker routes ─────────────────────────────────────────────────────

@app.route('/spotify')
def spotify_page():
    try:
        from database import DataBase
        DataBase().ensure_spotify_tables()
    except Exception:
        pass
    if os.path.exists(SPOTIFY_HTML):
        return send_file(SPOTIFY_HTML)
    return "Spotify Tracker page not found", 404


@app.route('/api/spotify/members', methods=['GET', 'POST'])
def api_spotify_members():
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        if request.method == 'GET':
            return jsonify({'ok': True, 'members': db.get_spotify_members()})
        body = request.get_json(force=True) or {}
        name = (body.get('name') or '').strip()
        if not name:
            return jsonify({'ok': False, 'error': 'name required'})
        mid = db.add_spotify_member(name, is_exempt=int(body.get('is_exempt', 0)))
        return jsonify({'ok': True, 'id': mid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/members/<int:member_id>', methods=['PUT', 'DELETE'])
def api_spotify_member(member_id):
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        if request.method == 'DELETE':
            db.delete_spotify_member(member_id)
            return jsonify({'ok': True})
        body = request.get_json(force=True) or {}
        db.update_spotify_member(
            member_id,
            name=body.get('name', '').strip(),
            is_exempt=int(body.get('is_exempt', 0)),
            is_active=int(body.get('is_active', 1)),
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/charges', methods=['GET', 'POST'])
def api_spotify_charges():
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        if request.method == 'GET':
            return jsonify({'ok': True, 'charges': db.get_spotify_charges()})
        body = request.get_json(force=True) or {}
        members = db.get_spotify_members()
        active_count = sum(1 for m in members if m['is_active'])
        month = body.get('month', '')
        total_amount = float(body.get('total_amount', 0))
        member_count = int(body.get('member_count', active_count))
        confirmed = int(body.get('confirmed', 1))
        existing = [c for c in db.get_spotify_charges() if (c.get('month') or '').startswith(month)]
        if existing:
            db.update_spotify_charge(existing[0]['id'], total_amount=total_amount, member_count=member_count, confirmed=confirmed)
            return jsonify({'ok': True, 'id': existing[0]['id']})
        cid = db.add_spotify_charge(
            month=month,
            total_amount=total_amount,
            member_count=member_count,
            tx_id=body.get('tx_id'),
            confirmed=confirmed,
        )
        return jsonify({'ok': True, 'id': cid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/charges/<int:charge_id>', methods=['PUT'])
def api_spotify_charge(charge_id):
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        body = request.get_json(force=True) or {}
        db.update_spotify_charge(
            charge_id,
            total_amount=float(body.get('total_amount', 0)),
            member_count=int(body.get('member_count', 1)),
            confirmed=int(body.get('confirmed', 1)),
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/charges/suggestions')
def api_spotify_charge_suggestions():
    try:
        import sys as _sys
        _sys.path.insert(0, _HERE)
        from SpotifyTracker import get_charge_suggestions
        from database import DataBase
        db = DataBase()
        db.ensure_spotify_tables()
        suggestions = get_charge_suggestions(db)
        return jsonify({'ok': True, 'suggestions': suggestions})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/payments', methods=['GET', 'POST'])
def api_spotify_payments():
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        if request.method == 'GET':
            member_id = request.args.get('member_id', type=int)
            return jsonify({'ok': True, 'payments': db.get_spotify_payments(member_id)})
        body = request.get_json(force=True) or {}
        tx_id = body.get('tx_id')
        if tx_id is not None:
            if int(tx_id) in db.get_spotify_assigned_tx_ids():
                return jsonify({'ok': False, 'error': 'עסקה זו כבר שויכה לחבר אחר'})
        tx_source = (body.get('tx_source') or '').strip() or None
        pid = db.add_spotify_payment(
            member_id=int(body.get('member_id', 0)),
            amount=float(body.get('amount', 0)),
            payment_date=(body.get('payment_date') or '').strip(),
            tx_id=tx_id,
            tx_source=tx_source,
            note=(body.get('note') or '').strip() or None,
        )
        return jsonify({'ok': True, 'id': pid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/payments/assigned-tx-ids')
def api_spotify_assigned_tx_ids():
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        return jsonify({'ok': True, 'tx_ids': list(db.get_spotify_assigned_tx_ids())})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'tx_ids': []})


@app.route('/api/spotify/payments/<int:payment_id>', methods=['DELETE'])
def api_spotify_payment(payment_id):
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        db.delete_spotify_payment(payment_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/unmatched')
def api_spotify_unmatched():
    try:
        import sys as _sys
        _sys.path.insert(0, _HERE)
        from SpotifyTracker import get_unmatched_payments
        from database import DataBase
        db = DataBase()
        db.ensure_spotify_tables()
        return jsonify({'ok': True, 'transactions': get_unmatched_payments(db)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/unmatched/<int:tx_id>/dismiss', methods=['POST'])
def api_spotify_dismiss_payment(tx_id):
    from database import DataBase
    db = DataBase()
    try:
        db.dismiss_spotify_unmatched(tx_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/balance')
def api_spotify_balance():
    try:
        import sys as _sys
        _sys.path.insert(0, _HERE)
        from database import DataBase
        from SpotifyTracker import compute_all_balances
        db = DataBase()
        db.ensure_spotify_tables()
        return jsonify({'ok': True, 'balances': compute_all_balances(db)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/report')
def api_spotify_report():
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from database import DataBase
    from SpotifyTracker import generate_pdf_report
    raw = request.args.get('member_id', '')
    if raw == 'all' or not raw:
        member_ids = []
    else:
        try:
            member_ids = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            return jsonify({'ok': False, 'error': 'invalid member_id'}), 400
    try:
        db = DataBase()
        db.ensure_spotify_tables()
        pdf_bytes = generate_pdf_report(member_ids, db)
        from flask import Response
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': 'attachment; filename="spotify_report.pdf"'},
        )
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/admin/upload-db', methods=['GET', 'POST'])
def admin_upload_db():
    """Upload a local ShmuelFamiliy.db to /tmp so Vercel has real data.
    Protected by UPLOAD_SECRET env var. Only meaningful when DATABASE_URL is set."""
    secret = os.getenv('UPLOAD_SECRET', '')
    if not secret:
        return "UPLOAD_SECRET env var not configured.", 403

    if request.method == 'GET':
        return '''<!doctype html><html lang="he" dir="rtl">
<head><meta charset="utf-8"><title>העלאת מסד נתונים</title>
<style>
  body{font-family:sans-serif;max-width:480px;margin:80px auto;padding:0 16px;background:#121212;color:#e0e0e0}
  h2{color:#1db954}
  input,button{width:100%;box-sizing:border-box;padding:10px;margin:8px 0;border-radius:6px;border:1px solid #333;background:#1e1e1e;color:#e0e0e0;font-size:1em}
  button{background:#1db954;color:#000;font-weight:bold;cursor:pointer;border:none}
  button:hover{background:#17a349}
  .note{font-size:.82em;color:#888;margin-top:12px}
</style></head>
<body>
<h2>העלאת מסד נתונים</h2>
<form method="post" enctype="multipart/form-data">
  <input type="password" name="password" placeholder="סיסמה" required>
  <input type="file" name="db_file" accept=".db" required>
  <button type="submit">העלה</button>
</form>
<p class="note">הקובץ יישמר ב־/tmp ויישאר זמין עד שהמכולה מתחלפת (cold start).</p>
</body></html>'''

    # POST — validate password then save file
    if request.form.get('password', '') != secret:
        return "סיסמה שגויה.", 403

    db_file = request.files.get('db_file')
    if not db_file or not db_file.filename.endswith('.db'):
        return "יש לבחור קובץ .db תקין.", 400

    dest = '/tmp/ShmuelFamiliy.db'
    db_file.save(dest)

    # Reset the DataBase singleton so the next query uses the new file.
    try:
        from database import DataBase
        with DataBase._DataBase__lock:
            inst = DataBase._DataBase__instance
            if inst is not None:
                try:
                    inst.connection.close()
                except Exception:
                    pass
            DataBase._DataBase__instance = None
    except Exception:
        pass

    size_kb = os.path.getsize(dest) // 1024
    return f"✓ מסד הנתונים הועלה בהצלחה ({size_kb} KB). <a href='/'>חזרה לדף הבית</a>"


def start(port: int = 5050, open_browser: bool = True):
    """Start the Flask server and optionally open the browser."""
    import webbrowser
    os.environ['BANKAPP_WEB'] = '1'
    _run_acct_migrations()
    _run_tagger_migrations()
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f'http://localhost:{port}')).start()
    app.run(host='127.0.0.1', port=port, threaded=True, debug=False, use_reloader=False)


if __name__ == '__main__':
    start(open_browser=False)
