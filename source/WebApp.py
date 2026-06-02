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
import queue
import threading
import time as _time
import json as _json
import builtins as _builtins

import re as _re
from flask import Flask, Response, request, jsonify, send_file, redirect

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE                  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR           = os.path.dirname(_HERE)

# Ensure CWD is always the project root so all relative paths (Personal Information/,
# ShmuelFamiliy.db, Outputs/, etc.) resolve correctly regardless of where the
# process was started (e.g. Vercel serverless, pytest, local terminal).
os.chdir(_PROJECT_DIR)

OUTPUT_HTML            = os.path.join(_HERE, 'html', 'output.html')
ORGANIZER_HTML         = os.path.join(_HERE, 'html', 'Organizer_Table.html')
GENERAL_ANALYSIS_DIR   = os.path.join(_PROJECT_DIR, 'Outputs', 'general_analysis')
CATEGORY_ANALYSIS_DIR  = os.path.join(_PROJECT_DIR, 'Outputs', 'category_analysis')
TAGGER_HTML            = os.path.join(_HERE, 'html', 'Tagger.html')
FILES_HTML             = os.path.join(_HERE, 'html', 'Files.html')

def _make_slug(type_: str, name: str) -> str:
    """type_ = 'cat' | 'biz'"""
    import re as _re2
    safe = _re2.sub(r'[^\w\u0590-\u05FF]', '_', name).strip('_')
    return f"{type_}_{safe}"

# ── Log capture via stdout tee ────────────────────────────────────────────────
_log_queue: queue.Queue = queue.Queue()

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
            _log_queue.put(stripped)
            _debug_put(stripped)

    def flush(self):
        self._orig.flush()

    def fileno(self):
        return self._orig.fileno()

    def __getattr__(self, name):
        return getattr(self._orig, name)


# Install tee once on import
if not isinstance(sys.stdout, _TeeStream):
    sys.stdout = _TeeStream(sys.stdout)

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
_analysis_running = False
_analysis_lock    = threading.Lock()

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


@app.route('/')
def index():
    # Redirect to the latest monthly file if available
    if os.path.isdir(GENERAL_ANALYSIS_DIR):
        files = sorted(
            f for f in os.listdir(GENERAL_ANALYSIS_DIR)
            if _re.match(r'^\d{4}_\d{2}\.html$', f)
        )
        if files:
            latest_key = files[-1].replace('.html', '')
            return redirect(f'/general/{latest_key}')
    if os.path.exists(OUTPUT_HTML):
        return send_file(OUTPUT_HTML)
    return _splash_html()


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
    if not _re.match(r'^\d{4}_\d{2}$', yyyy_mm):
        return "Invalid month format", 400
    html_path = os.path.join(GENERAL_ANALYSIS_DIR, f'{yyyy_mm}.html')
    if os.path.exists(html_path):
        return send_file(html_path)
    # File missing — show a "not generated yet" page
    year  = int(yyyy_mm[:4])
    month = int(yyyy_mm[5:7])
    return _not_generated_html(year, month, yyyy_mm)


@app.route('/accounts')
def accounts_page():
    """Redirect to the latest monthly page with ?panel=accounts."""
    if os.path.isdir(GENERAL_ANALYSIS_DIR):
        files = sorted(
            f for f in os.listdir(GENERAL_ANALYSIS_DIR)
            if _re.match(r'^\d{4}_\d{2}\.html$', f)
        )
        if files:
            latest_key = files[-1].replace('.html', '')
            return redirect(f'/general/{latest_key}?panel=accounts')
    return redirect('/?panel=accounts')


@app.route('/housing')
def housing_page():
    """Redirect to the latest monthly page with ?panel=housing."""
    if os.path.isdir(GENERAL_ANALYSIS_DIR):
        files = sorted(
            f for f in os.listdir(GENERAL_ANALYSIS_DIR)
            if _re.match(r'^\d{4}_\d{2}\.html$', f)
        )
        if files:
            latest_key = files[-1].replace('.html', '')
            return redirect(f'/general/{latest_key}?panel=housing')
    return redirect('/?panel=housing')


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
    import sqlite3 as _sq
    q_keyword  = (request.args.get('keyword')  or '').strip()
    q_category = (request.args.get('category') or '').strip()
    q_business = (request.args.get('business') or '').strip()
    q_min      = request.args.get('min', type=float)
    q_max      = request.args.get('max', type=float)
    q_from     = (request.args.get('from')     or '').strip()
    q_to       = (request.args.get('to')       or '').strip()
    q_type     = (request.args.get('type')     or 'all').strip()   # 'income' | 'expense' | 'all'
    q_id       = request.args.get('id',  type=int)
    q_split    = (request.args.get('split')    or 'any').strip()  # 'split' | 'nonsplit' | 'any'

    results = []
    try:
        conn = _sq.connect(_DB_PATH, check_same_thread=False)
        conn.row_factory = _sq.Row

        # Pre-fetch split IDs if the filter is active
        split_ids_bank = set()
        split_ids_card = set()
        if q_split != 'any':
            for r in conn.execute(
                "SELECT Original_ID, Original_Table FROM TransactionSplits"
            ).fetchall():
                if r['Original_Table'] == 'BankTransactions':
                    split_ids_bank.add(r['Original_ID'])
                else:
                    split_ids_card.add(r['Original_ID'])

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
        if q_type == 'income':
            bank_where.append("Income > 0")
        elif q_type == 'expense':
            bank_where.append("Out > 0")

        bank_sql = "SELECT ID, Date, Name, Category, Income, Out, Description FROM BankTransactions"
        if bank_where:
            bank_sql += " WHERE " + " AND ".join(bank_where)
        bank_sql += " ORDER BY Date DESC LIMIT 2000"

        for row in conn.execute(bank_sql, bank_params):
            amount = float(row['Income'] or 0) - float(row['Out'] or 0)
            if q_min is not None and abs(amount) < q_min:
                continue
            if q_max is not None and abs(amount) > q_max:
                continue
            is_split = row['ID'] in split_ids_bank
            if q_split == 'split'    and not is_split: continue
            if q_split == 'nonsplit' and     is_split: continue
            results.append({
                'tx_id':       row['ID'],
                'date':        (row['Date'] or '')[:10],
                'name':        row['Name'] or '',
                'category':    row['Category'] or '',
                'amount':      amount,
                'description': row['Description'] or '',
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
        if q_type == 'income':
            card_where.append("Transaction_Value < 0")   # negative = refund/credit = income
        elif q_type == 'expense':
            card_where.append("Transaction_Value > 0")   # positive = charge = expense

        card_sql = "SELECT ID, CardID, Executed_Date, Name, Category, Transaction_Value, Value_Currency, Description FROM CardTransactions"
        if card_where:
            card_sql += " WHERE " + " AND ".join(card_where)
        card_sql += " ORDER BY Executed_Date DESC LIMIT 2000"

        for row in conn.execute(card_sql, card_params):
            amount = -float(row['Transaction_Value'] or 0)  # negate: positive charge → negative (expense)
            if q_min is not None and abs(amount) < q_min:
                continue
            if q_max is not None and abs(amount) > q_max:
                continue
            is_split = row['ID'] in split_ids_card
            if q_split == 'split'    and not is_split: continue
            if q_split == 'nonsplit' and     is_split: continue
            results.append({
                'tx_id':       row['ID'],
                'date':        (row['Executed_Date'] or '')[:10],
                'name':        row['Name'] or '',
                'category':    row['Category'] or '',
                'amount':      amount,
                'description': row['Description'] or '',
                'source':      'card',
                'card_id':     row['CardID'],
                'is_split':    is_split,
            })

        conn.close()
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'results': []}), 500

    # ── Apply splits: hide originals, surface split rows ─────────────────────
    try:
        split_conn  = _sq.connect(_DB_PATH, check_same_thread=False)
        split_conn.row_factory = _sq.Row
        split_rows_db = split_conn.execute(
            'SELECT ID, Original_Table, Original_ID, Amount, Description, Category FROM TransactionSplits'
        ).fetchall()
        split_conn.close()
    except Exception:
        split_rows_db = []

    if split_rows_db:
        split_orig_keys = set((r['Original_Table'], r['Original_ID']) for r in split_rows_db)
        # Remove split originals from results
        results = [r for r in results
                   if not (('bank' if r['source'] == 'bank' else 'card') == 'bank'
                           and ('BankTransactions', r['tx_id']) in split_orig_keys)
                   and not (r['source'] == 'card'
                            and ('CardTransactions', r['tx_id']) in split_orig_keys)]
        # Add split rows (using original row metadata)
        orig_meta_cache = {}
        for split_r in split_rows_db:
            orig_table = split_r['Original_Table']
            orig_id    = split_r['Original_ID']
            key        = (orig_table, orig_id)
            if key not in orig_meta_cache:
                try:
                    c2 = _sq.connect(_DB_PATH, check_same_thread=False)
                    c2.row_factory = _sq.Row
                    if orig_table == 'BankTransactions':
                        meta = c2.execute(
                            'SELECT Name, Date FROM BankTransactions WHERE ID=?', (orig_id,)
                        ).fetchone()
                        orig_meta_cache[key] = {
                            'name': meta['Name'] if meta else '', 'source': 'bank',
                            'date': (meta['Date'] or '')[:10] if meta else '', 'card_id': None,
                        }
                    else:
                        meta = c2.execute(
                            'SELECT Name, Executed_Date, CardID FROM CardTransactions WHERE ID=?', (orig_id,)
                        ).fetchone()
                        orig_meta_cache[key] = {
                            'name': meta['Name'] if meta else '', 'source': 'card',
                            'date': (meta['Executed_Date'] or '')[:10] if meta else '',
                            'card_id': meta['CardID'] if meta else None,
                        }
                    c2.close()
                except Exception:
                    orig_meta_cache[key] = {'name': '', 'source': 'bank', 'date': '', 'card_id': None}

            meta = orig_meta_cache[key]
            # Apply all filters to split rows (date, keyword, category, type, amount)
            amount = float(split_r['Amount'])
            if q_from and meta['date'] and meta['date'] < q_from: continue
            if q_to   and meta['date'] and meta['date'] > q_to:   continue
            if q_type == 'income' and amount <= 0: continue
            if q_type == 'expense' and amount >= 0: continue
            if q_min is not None and abs(amount) < q_min: continue
            if q_max is not None and abs(amount) > q_max: continue
            if q_keyword:
                hay = (meta['name'] + ' ' + (split_r['Description'] or '')).lower()
                if q_keyword.lower() not in hay: continue
            if q_category and split_r['Category'] != q_category: continue
            results.append({
                'tx_id':       split_r['ID'],
                'date':        meta['date'],
                'name':        meta['name'],
                'category':    split_r['Category'],
                'amount':      amount,
                'description': split_r['Description'] or '',
                'source':      meta['source'],
                'card_id':     meta['card_id'],
                'is_split':    True,
                'split_id':    split_r['ID'],
                'orig_id':     orig_id,
                'orig_table':  orig_table,
            })

    # Sort combined results by date desc
    results.sort(key=lambda x: x['date'] or '', reverse=True)
    return jsonify({'ok': True, 'results': results[:500]})


@app.route('/api/search/categories')
def search_categories():
    """Return distinct category names for the search filter dropdown."""
    import sqlite3 as _sq
    try:
        conn = _sq.connect(_DB_PATH, check_same_thread=False)
        cats = set()
        for row in conn.execute("SELECT DISTINCT Category FROM BankTransactions WHERE Category IS NOT NULL AND Category != ''"):
            cats.add(row[0])
        for row in conn.execute("SELECT DISTINCT Category FROM CardTransactions WHERE Category IS NOT NULL AND Category != ''"):
            cats.add(row[0])
        conn.close()
        return jsonify({'categories': sorted(cats)})
    except Exception as e:
        return jsonify({'categories': [], 'error': str(e)})


@app.route('/api/general/list')
def general_list():
    from datetime import datetime as _dt
    result = []
    if os.path.isdir(GENERAL_ANALYSIS_DIR):
        for fname in sorted(os.listdir(GENERAL_ANALYSIS_DIR)):
            m = _re.match(r'^(\d{4})_(\d{2})\.html$', fname)
            if m:
                year  = int(m.group(1))
                month = int(m.group(2))
                fpath = os.path.join(GENERAL_ANALYSIS_DIR, fname)
                mtime = os.path.getmtime(fpath)
                result.append({
                    'key':       f'{year:04d}_{month:02d}',
                    'year':      year,
                    'month':     month,
                    'generated': _dt.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M'),
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
        fpath = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
        has   = os.path.exists(fpath)
        dot   = f'<span style="width:8px;height:8px;border-radius:50%;background:{"#1e9d8b" if has else "#ccc"};display:inline-block;margin-left:8px;flex-shrink:0"></span>'
        label = 'קטגוריה' if type_ == 'category' else 'עסק'
        badge_color = '#1e9d8b' if type_ == 'category' else '#9b59b6'
        # Include original name as query-param so serve_category can pass it to
        # the auto-trigger without losing special chars like " and /
        name_qs = _quote(name, safe='')
        return (
            f'<a href="/category/{slug}?name={name_qs}" class="cat-item" data-name="{name}"'
            f' style="display:flex;align-items:center;padding:12px 16px;'
            f'background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);'
            f'text-decoration:none;color:#1e2a4a;transition:box-shadow .18s,transform .18s;'
            f'gap:10px" onmouseover="this.style.transform=\'translateY(-2px)\';this.style.boxShadow=\'0 6px 18px rgba(0,0,0,.10)\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'0 2px 8px rgba(0,0,0,.06)\'">'
            f'{dot}'
            f'<span style="flex:1;font-weight:600;font-size:.9em">{name}</span>'
            f'<span style="font-size:.7em;font-weight:700;color:#fff;background:{badge_color};'
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
    <a class="nav-item" href="/">ניתוח חודשי</a>
    <a class="nav-item" href="/">עסקאות</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/accounts">חשבונות</a>
    <a class="nav-item" href="/housing">דיור</a>
    <a class="nav-item" href="/organizer">ארגונית</a>
    <a class="nav-item active" href="/categories">ניתוח קטגוריאלי</a>
    <a class="nav-item" href="/search">חיפוש</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/tagger">תייגן</a>
    <a class="nav-item" href="/files">קבצים</a>
  </div>
  <div class="sidebar-footer" style="padding:12px 16px;border-top:1px solid #eef0f6;flex-shrink:0">
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
<script>
function restartServer(btn){{btn.disabled=true;btn.innerHTML='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg> מפעיל מחדש…';fetch('/api/restart',{{method:'POST'}}).catch(function(){{}}).finally(function(){{var t=setInterval(function(){{fetch('/').then(function(r){{if(r.ok){{clearInterval(t);location.reload();}}}}).catch(function(){{}});}},800);}});}}
function openNav(){{var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.add('open');o.classList.add('open');b.classList.add('open');}}
function closeNav(){{var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.remove('open');o.classList.remove('open');b.classList.remove('open');}}
function toggleNav(){{document.getElementById('sidebar').classList.contains('open')?closeNav():openNav();}}
document.addEventListener('keydown',function(e){{if(e.key==='Escape')closeNav();}});
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
            _log_queue.put(f'[ERROR] {exc}')
            for line in traceback.format_exc().splitlines():
                if line.strip(): _log_queue.put(line)
            _log_queue.put('__ERROR__')
        finally:
            with _analysis_lock:
                _analysis_running = False

    threading.Thread(target=_worker, daemon=True, name='cat-analysis-worker').start()
    return jsonify({'status': 'started'})


def _log_float_style() -> str:
    return """<style>
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9;
           display: flex; align-items: center; justify-content: center;
           min-height: 100vh; margin: 0; }
    .box { background: #fff; border-radius: 14px; padding: 48px 56px;
           text-align: center; box-shadow: 0 6px 20px rgba(0,0,0,.10); max-width: 460px; }
    h2   { color: #1e2a4a; margin-bottom: 10px; }
    p    { color: #888; font-size: .93em; margin-bottom: 28px; }
    .badge { display:inline-block; background:#1e9d8b; color:#fff; border-radius:20px;
             padding:5px 18px; font-size:.85em; font-weight:600; margin-bottom:24px; }
    .back { margin-top:16px; font-size:.8em; }
    .back a { color:#888; text-decoration:none; }
    .back a:hover { color:#1e9d8b; }
    /* ── floating log panel ── */
    .log-float { position:fixed; bottom:32px; left:50%;
                 transform:translateX(-50%) translateY(12px);
                 min-width:360px; max-width:520px;
                 opacity:0; pointer-events:none;
                 transition:opacity .3s, transform .3s;
                 z-index:9999; text-align:center; }
    .log-float.visible { opacity:1; pointer-events:auto; transform:translateX(-50%) translateY(0); }
    .lf-header { display:flex; align-items:center; justify-content:center; gap:8px; margin-bottom:8px; }
    .lf-spinner { width:14px; height:14px; border:2px solid rgba(30,157,139,.3);
                  border-top-color:#1e9d8b; border-radius:50%;
                  animation:lf-spin .7s linear infinite; flex-shrink:0; }
    .lf-spinner.done  { animation:none; border-color:#2ecc71; }
    .lf-spinner.error { animation:none; border-color:#c0392b; }
    @keyframes lf-spin { to { transform:rotate(360deg); } }
    .lf-title { font-size:.8em; font-weight:600; color:#1e9d8b;
                text-shadow:0 1px 6px rgba(255,255,255,.9),0 0 2px #fff; }
    .lf-feed { display:flex; flex-direction:column-reverse; max-height:120px;
               overflow:hidden; align-items:center; }
    .lf-line { font-size:.7em; padding:1px 0; white-space:nowrap;
               color:#2d3a5e; animation:lf-slide .28s ease;
               text-shadow:0 1px 4px rgba(255,255,255,.95),0 0 1px #fff; }
    .lf-line:nth-child(2) { opacity:.55; }
    .lf-line:nth-child(3) { opacity:.3; }
    .lf-line:nth-child(n+4) { opacity:.12; }
    .lf-line.warn { color:#b07000; }
    .lf-line.err  { color:#c0392b; }
    .lf-line.done { color:#1a7a45; font-weight:600; }
    @keyframes lf-slide { from { transform:translateY(10px); opacity:0; }
                          to   { transform:translateY(0); } }
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
    <div class="lf-spinner" id="lf-spinner"></div>
    <span class="lf-title" id="lf-title">מנתח נתונים…</span>
  </div>
  <div class="lf-feed" id="lf-feed"></div>
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
    return """var _LF_MAX = 7;
    function showLogFloat(title) {
      document.getElementById('lf-feed').innerHTML = '';
      document.getElementById('lf-title').textContent = title || 'מנתח נתונים…';
      var sp = document.getElementById('lf-spinner');
      if (sp) sp.className = 'lf-spinner';
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
      feed.insertBefore(el, feed.firstChild);
      while (feed.children.length > _LF_MAX) feed.removeChild(feed.lastChild);
      var sp = document.getElementById('lf-spinner');
      if (sp && cls === 'done') sp.className = 'lf-spinner done';
      if (sp && cls === 'err')  sp.className = 'lf-spinner error';
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
    fetch('/api/category/run', {{method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{slug: {slug_js}, type: {type_js}, name: {name_js}}})
    }}).then(function() {{
      var es = new EventSource('/api/logs');
      es.onmessage = function(e) {{
        if (!e.data || e.data === '__CONNECTED__') return;
        if (e.data.startsWith('__DONE__')) {{
          es.close();
          appendLog('✓ הניתוח הסתיים — טוען…', 'done');
          hideLogFloat(900);
          setTimeout(function() {{ location.href = '/category/' + {slug_js}; }}, 1100);
          return;
        }}
        if (e.data === '__ERROR__') {{
          es.close();
          appendLog('✗ שגיאה בניתוח', 'err');
          hideLogFloat(3000);
          return;
        }}
        appendLog(e.data);
      }};
    }});
  }})();
</script>
</body>
</html>'''


_READONLY_ACCOUNTS = ["נכס שלום שבזי"]
_DB_PATH = os.path.join(_PROJECT_DIR, 'ShmuelFamiliy.db')


def _acct_db():
    """Open a fresh connection to the main DB using an absolute path."""
    import sqlite3 as _sq
    conn = _sq.connect(_DB_PATH, check_same_thread=False)
    # Ensure Currency column exists (safe migration)
    try:
        conn.execute("ALTER TABLE OtherAccountStatus ADD COLUMN Currency TEXT NOT NULL DEFAULT 'ILS'")
        conn.commit()
    except Exception:
        pass  # Column already exists
    return conn


# ── Exchange-rate cache (refreshed once per hour) ─────────────────────────────
_fx_cache   = {}   # {'USD': 3.72, 'EUR': 4.01, ...}  (rate TO ILS)
_fx_fetched = 0.0  # epoch seconds

def _get_fx_rates():
    """Return a dict of currency→ILS rates, cached for 1 hour."""
    import time, urllib.request, json as _json
    global _fx_cache, _fx_fetched
    if _fx_cache and (time.time() - _fx_fetched) < 3600:
        return _fx_cache
    try:
        url = 'https://api.exchangerate-api.com/v4/latest/ILS'
        with urllib.request.urlopen(url, timeout=4) as resp:
            data = _json.loads(resp.read())
        # data['rates'] maps ILS→X, we want X→ILS
        ils_to_x = data.get('rates', {})
        _fx_cache = {cur: 1.0 / rate for cur, rate in ils_to_x.items() if rate}
        _fx_cache['ILS'] = 1.0
        _fx_fetched = time.time()
    except Exception:
        # Fallback hardcoded approximate rates
        _fx_cache = {'ILS': 1.0, 'USD': 3.72, 'EUR': 4.01, 'JPY': 0.025}
        _fx_fetched = time.time()
    return _fx_cache


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
            "SELECT ID, AccountName, StatusDate, Value, Currency FROM OtherAccountStatus ORDER BY StatusDate DESC"
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


@app.route('/api/accounts/cash-by-currency')
def cash_by_currency():
    """Return current cash balance per currency, matching accumulate_cash_Balance():
       cash on hand = bank withdrawals (Out) + CashTransactions (Amount)
    """
    import sqlite3 as _sq, re as _re2
    db_candidates = [_DB_PATH, os.path.join(_HERE, 'ShmuelFamiliy.db')]
    db_file = next((p for p in db_candidates if os.path.exists(p)), None)
    if not db_file:
        return jsonify({'ok': False, 'error': 'database not found'})
    try:
        _SYM = {'ILS': '₪', 'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥'}
        totals = {}   # currency_code → running balance

        conn = _sq.connect(db_file)
        cur  = conn.cursor()

        # 1. Bank withdrawals — these represent cash that left the bank and is now on hand.
        #    They're ILS bank transactions tagged with the withdrawal category.
        cur.execute(
            "SELECT SUM(Out) FROM BankTransactions WHERE Category = 'withdrawal'"
        )
        bank_out = cur.fetchone()[0] or 0
        totals['ILS'] = totals.get('ILS', 0) + float(bank_out)

        # 2. CashTransactions — user-recorded cash income (+) and spending (-)
        cur.execute('SELECT Currency, SUM(Amount) FROM CashTransactions GROUP BY Currency')
        for cur_raw, amount in cur.fetchall():
            m    = _re2.match(r'([A-Z]+)', (cur_raw or '').strip())
            code = m.group(1) if m else (cur_raw or 'ILS')
            totals[code] = totals.get(code, 0) + float(amount or 0)

        conn.close()

        result = [
            {
                'currency': code,
                'symbol':   _SYM.get(code, code),
                'balance':  round(bal, 2),
            }
            for code, bal in sorted(totals.items(), key=lambda x: -abs(x[1]))
        ]
        return jsonify({'ok': True, 'data': result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


def _cash_balance_map():
    """Return {currency_code: balance} for the current cash on hand.
    Shared by cash_by_currency() and cash_reconcile()."""
    import sqlite3 as _sq, re as _re2
    db_candidates = [_DB_PATH, os.path.join(_HERE, 'ShmuelFamiliy.db')]
    db_file = next((p for p in db_candidates if os.path.exists(p)), None)
    if not db_file:
        return {}
    totals = {}
    conn = _sq.connect(db_file)
    cur  = conn.cursor()
    cur.execute("SELECT SUM(Out) FROM BankTransactions WHERE Category = 'withdrawal'")
    bank_out = cur.fetchone()[0] or 0
    totals['ILS'] = float(bank_out)
    cur.execute('SELECT Currency, SUM(Amount) FROM CashTransactions GROUP BY Currency')
    for cur_raw, amount in cur.fetchall():
        m    = _re2.match(r'([A-Z]+)', (cur_raw or '').strip())
        code = m.group(1) if m else (cur_raw or 'ILS')
        totals[code] = totals.get(code, 0) + float(amount or 0)
    conn.close()
    return totals


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
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/cash/monthly-history')
def cash_monthly_history_api():
    """Return accumulated cash balance (ILS) sampled at the first of each month."""
    try:
        import sqlite3 as _sq, re as _re2, urllib.request as _ureq, json as _json_fx
        from datetime import date as _date, datetime as _dt

        db_candidates = [_DB_PATH, os.path.join(_HERE, 'ShmuelFamiliy.db')]
        db_file = next((p for p in db_candidates if os.path.exists(p)), None)
        if not db_file:
            return jsonify({'ok': False, 'error': 'database not found'})

        # Live FX rates (currency → ILS multiplier)
        try:
            with _ureq.urlopen('https://api.exchangerate-api.com/v4/latest/ILS', timeout=5) as _r:
                _ils_to_x = _json_fx.loads(_r.read()).get('rates', {})
            _fx_to_ils = {c: 1.0 / r for c, r in _ils_to_x.items() if r}
            _fx_to_ils['ILS'] = 1.0
        except Exception:
            _fx_to_ils = {'ILS': 1.0, 'USD': 3.72, 'EUR': 4.01, 'JPY': 0.025}

        events = []  # [(date, ils_amount)]

        conn = _sq.connect(db_file)
        c = conn.cursor()

        # Bank withdrawals (always ILS)
        c.execute("SELECT Date, Out FROM BankTransactions WHERE Category = 'withdrawal' AND Date IS NOT NULL")
        for d_str, out_val in c.fetchall():
            try:
                d = _dt.strptime(str(d_str)[:10], '%Y-%m-%d').date()
                events.append((d, float(out_val or 0)))
            except Exception:
                pass

        # Manual CashTransactions
        c.execute("SELECT Execution_Date, Amount, Currency FROM CashTransactions")
        for d_str, amount, cur_code in c.fetchall():
            try:
                d = _dt.strptime(str(d_str)[:10], '%Y-%m-%d').date()
                m = _re2.match(r'([A-Z]+)', (cur_code or '').strip())
                code = m.group(1) if m else 'ILS'
                rate = _fx_to_ils.get(code, 1.0)
                events.append((d, float(amount or 0) * rate))
            except Exception:
                pass

        conn.close()

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
        return jsonify({'ok': True, 'created': created, 'details': details})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/status')
def status():
    return jsonify({'running': _analysis_running})


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
    result = {}
    if not os.path.isdir(GENERAL_ANALYSIS_DIR):
        return jsonify(result)
    for fname in os.listdir(GENERAL_ANALYSIS_DIR):
        m = _re.match(r'^(\d{4}_\d{2})\.html$', fname)
        if m:
            key = m.group(1)
            result[key] = _is_stale_manifest(os.path.join(GENERAL_ANALYSIS_DIR, fname))
    return jsonify(result)


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
    html_path = os.path.join(GENERAL_ANALYSIS_DIR, f'{yyyy_mm}.html')
    if not os.path.exists(html_path):
        return jsonify({'stale': True})
    return jsonify({'stale': _is_stale_manifest(html_path)})


@app.route('/api/analysis', methods=['POST'])
def run_analysis():
    global _analysis_running

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
        global _analysis_running
        try:
            from AppManager import AppManager
            from datetime import datetime
            from dateutil.relativedelta import relativedelta
            from src_utils.utils import utils as _utils

            # Install web-mode CC prompt hook so card_charge_validation shows a
            # browser popup instead of blocking on stdin.
            _utils._cc_confirm_hook = _web_cc_confirm

            if month_sel == 'last':
                t = datetime.now() - relativedelta(months=1)
            elif month_sel == 'pick' and date_str:
                t = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                t = datetime.now()

            deps, db_mtime = _capture_deps_and_run(
                lambda: AppManager(skip_parser=True).general_analysis(t=t)
            )

            key       = t.strftime('%Y_%m')
            html_path = os.path.join(GENERAL_ANALYSIS_DIR, f'{key}.html')
            if os.path.exists(html_path):
                _save_manifest(html_path, deps, db_mtime)

            _log_queue.put(f'__DONE__:{key}')

        except Exception as exc:
            import traceback
            _log_queue.put(f'[ERROR] {exc}')
            for line in traceback.format_exc().splitlines():
                if line.strip():
                    _log_queue.put(line)
            _log_queue.put('__ERROR__')

        finally:
            with _analysis_lock:
                _analysis_running = False
            try:
                from src_utils.utils import utils as _utils
                _utils._cc_confirm_hook = None
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True, name='analysis-worker').start()
    return jsonify({'status': 'started'})


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
  <title>BankApp — {month_label}</title>
  {_log_float_style()}
</head>
<body>
  <div class="box">
    <h2>ניתוח חודשי</h2>
    <div class="badge">{month_label}</div>
    <p>מפעיל ניתוח אוטומטי…</p>
    <div class="back"><a href="/">&#8592; חזרה לדף הראשי</a></div>
  </div>
  {_log_float_html()}
  <script>
    {_log_float_js()}
    (function() {{
      showLogFloat('מנתח נתונים…');
      fetch('/api/analysis', {{method:'POST',
            headers:{{'Content-Type':'application/json'}},
            body: JSON.stringify({{month:'pick', date:'{date_str}'}})
      }})
      .then(function() {{
        var es = new EventSource('/api/logs');
        es.onmessage = function(e) {{
          if (!e.data || e.data === '__CONNECTED__') return;
          if (e.data.startsWith('__PROMPT_CC__:')) {{
            try {{ showCCPrompt(JSON.parse(e.data.slice(14))); }} catch(_) {{}}
            return;
          }}
          if (e.data.startsWith('__DONE__')) {{
            es.close();
            appendLog('✓ הניתוח הסתיים — טוען…', 'done');
            hideLogFloat(900);
            setTimeout(function() {{ location.href = '/general/{yyyy_mm}'; }}, 1100);
            return;
          }}
          if (e.data === '__ERROR__') {{
            es.close();
            appendLog('✗ שגיאה בניתוח', 'err');
            hideLogFloat(3000);
            return;
          }}
          appendLog(e.data);
        }};
      }});
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
.sidebar-scroll{flex:1;overflow-y:auto;overflow-x:hidden;padding:8px 0 16px}
.nav-item{display:flex;align-items:center;padding:10px 20px;text-decoration:none;color:#555;font-size:.875em;font-weight:500;transition:background .1s,color .1s;cursor:pointer;border:none;background:none;width:100%;text-align:right;position:relative;letter-spacing:.1px}
.nav-item::before{content:'';position:absolute;right:0;top:22%;height:56%;width:3px;border-radius:3px 0 0 3px;background:transparent;transition:background .1s}
.nav-item:hover{background:#e8f7f5;color:#1e9d8b}
.nav-item:hover::before{background:#1e9d8b}
.nav-item.active{color:#b8c0d0;cursor:default;pointer-events:none}
.nav-sep{height:1px;background:#eef0f6;margin:8px 16px}
.main{margin-right:0;flex:1;padding:72px 32px 60px;min-width:0;overflow-x:hidden}
.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}
.page-header h1{font-size:1.7em;font-weight:700}
.regen-btn{display:inline-flex;align-items:center;gap:6px;padding:5px 14px;border:1.5px solid var(--teal);border-radius:20px;background:var(--white);color:var(--teal);font-size:.78em;font-weight:600;cursor:pointer;transition:background .15s,color .15s;white-space:nowrap}
.regen-btn:hover{background:var(--teal);color:#fff}
.regen-btn:disabled{opacity:.5;cursor:not-allowed}
@keyframes _regenGlow{0%,100%{box-shadow:0 0 0 0 rgba(30,157,139,.55)}50%{box-shadow:0 0 0 7px rgba(30,157,139,0)}}
.regen-icon{font-size:1.05em;display:inline-block}
.regen-btn.spinning .regen-icon{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading-overlay{display:none;position:fixed;inset:0;background:rgba(255,255,255,.9);z-index:900;flex-direction:column;align-items:center;justify-content:center;gap:16px}
.loading-overlay.active{display:flex}
.loading-spinner{width:46px;height:46px;border:4px solid var(--border);border-top-color:var(--teal);border-radius:50%;animation:spin .8s linear infinite}
.loading-text{font-size:.95em;font-weight:600;color:var(--navy)}
.loading-pct{font-size:1.6em;font-weight:700;color:var(--teal);min-width:4ch;text-align:center}
.legend-card{background:var(--white);border-radius:14px;box-shadow:0 2px 16px rgba(0,0,0,.08),0 0 0 1px rgba(0,0,0,.04);padding:20px 26px;margin-bottom:24px}
.legend-title{font-size:.7em;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.9px;margin-bottom:16px}
.legend-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:10px 36px}
.legend-item{display:flex;align-items:flex-start;gap:9px;font-size:.83em;line-height:1.5}
.legend-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;margin-top:4px}
.legend-label{font-weight:700;color:var(--navy);white-space:nowrap;margin-left:2px}
.legend-sep{color:var(--text-muted);margin:0 1px}
.legend-desc{color:var(--text-muted)}
.ld-green{background:#22c55e}.ld-yellow{background:#f59e0b}.ld-red{background:#ef4444}
.ld-blue{background:#3b82f6}.ld-blue2{background:#93c5fd}.ld-gray{background:#9ca3af}
.table-section{background:var(--white);border-radius:var(--radius);border:1px solid var(--border);overflow:hidden}
.table-scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;white-space:nowrap}
.org-th{background:var(--navy);color:#fff;padding:13px 14px;text-align:center;font-size:.79em;font-weight:600;letter-spacing:.3px;position:sticky;top:0;z-index:10}
.org-th-date{text-align:right;min-width:150px;position:sticky;right:0;z-index:11;border-left:2px solid rgba(255,255,255,.15)}
.org-td{padding:10px 12px;text-align:center;font-size:.81em;border-bottom:1px solid var(--border);vertical-align:middle;min-width:130px}
.org-td-date{font-weight:600;color:var(--teal);text-align:right;background:var(--white) !important;position:sticky;right:0;z-index:5;border-left:2px solid var(--border);padding-right:14px}
tbody tr:hover .org-td{background:rgba(30,157,139,.04) !important}
tbody tr:hover .org-td-date{background:#f8fffd !important}
.org-cell-green{background:#f0fdf4 !important;color:#166534}
.org-cell-yellow{background:#fefce8 !important;color:#854d0e}
.org-cell-red{background:#fef2f2 !important;color:#991b1b}
.org-cell-blue-miss{background:#eff6ff !important;color:#1e40af;font-size:.78em;padding:8px 10px !important;text-align:right}
.org-cell-blue-mis2{background:#f0f9ff !important;color:#0c4a6e;font-size:.78em;padding:8px 10px !important;text-align:right}
.org-cell-gray{background:#f9fafb !important;color:#9ca3af;font-style:italic}
.org-cell-label{font-size:.78em;font-weight:700;display:block}
.org-badge-bank{color:#0369a1}
.org-cell-date{font-size:.76em;color:#6b7280;display:block;margin-top:2px}
.org-match-detail{display:flex;flex-direction:column;gap:1px;margin-top:4px;font-size:.75em;opacity:.85}
.generated-row{display:flex;align-items:center;gap:8px;flex-shrink:0}
.generated-label{font-size:.72em;color:var(--text-muted);white-space:nowrap}
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
    <span class="sidebar-app-name">FinDash</span>
  </div>
  <div class="sidebar-scroll">
    <a class="nav-item" href="/">ראשי</a>
    <div class="nav-sep"></div>
    <a class="nav-item active" href="/organizer">ארגונית</a>
    <a class="nav-item" href="/categories">קטגוריות</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/tagger">תייגן</a>
    <a class="nav-item" href="/files">קבצים</a>
  </div>
  <div class="sidebar-footer" style="padding:12px 16px;border-top:1px solid var(--border);flex-shrink:0">
    <button onclick="restartServer(this)" style="width:100%;padding:8px 12px;border:1.5px dashed var(--border);border-radius:8px;background:none;color:var(--text-muted);font-size:.78em;font-weight:600;cursor:pointer;font-family:inherit;display:flex;align-items:center;gap:7px;justify-content:center" onmouseover="this.style.background='#fff3f3';this.style.color='#e53935';this.style.borderColor='#e53935'" onmouseout="this.style.background='none';this.style.color='';this.style.borderColor=''">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg>
      הפעל שרת מחדש
    </button>
  </div>
</nav>

<div class="loading-overlay" id="loading-overlay">
  <div class="loading-spinner"></div>
  <div class="loading-text">מחדש נתונים\u2026</div>
  <div class="loading-pct" id="loading-pct">0%</div>
</div>

<div class="main">
  <div class="page-header">
    <h1>ארגונית קבצים</h1>
    <div class="generated-row">
      <span class="generated-label" id="generated-label"></span>
      <button class="regen-btn" id="regen-btn" onclick="regenerate()"><span class="regen-icon">&#8635;</span> חשב מחדש</button>
    </div>
  </div>

  <div class="legend-card">
    <div class="legend-title">מקרא</div>
    <div class="legend-grid">
      <div class="legend-item"><span class="legend-dot ld-green"></span><span class="legend-label">מאומת</span><span class="legend-sep">&mdash;</span><span class="legend-desc">הקובץ עובד ועסקאות הכרטיס התאימו לחיוב בבנק</span></div>
      <div class="legend-item"><span class="legend-dot ld-green"></span><span class="legend-label">Bank</span><span class="legend-sep">&mdash;</span><span class="legend-desc">קובץ חשבון בנק נרשם (אימות לא רלוונטי)</span></div>
      <div class="legend-item"><span class="legend-dot ld-yellow"></span><span class="legend-label">לא מאומת</span><span class="legend-sep">&mdash;</span><span class="legend-desc">הקובץ עובד אך לא נמצא חיוב תואם בבנק</span></div>
      <div class="legend-item"><span class="legend-dot ld-yellow"></span><span class="legend-label">ללא עסקות</span><span class="legend-sep">&mdash;</span><span class="legend-desc">הקובץ נרשם אך לא היו עסקות לכרטיס בחודש זה</span></div>
      <div class="legend-item"><span class="legend-dot ld-red"></span><span class="legend-label">חסר קובץ</span><span class="legend-sep">&mdash;</span><span class="legend-desc">לא נמצא קובץ לפורמט ולכרטיס בתאריך זה</span></div>
      <div class="legend-item"><span class="legend-dot ld-blue"></span><span class="legend-label">קובץ חסר + עסקה</span><span class="legend-sep">&mdash;</span><span class="legend-desc">נמצאה עסקה לא מתויגת תואמת אך ללא קובץ</span></div>
      <div class="legend-item"><span class="legend-dot ld-blue2"></span><span class="legend-label">אי-התאמת ערך</span><span class="legend-sep">&mdash;</span><span class="legend-desc">נמצאה עסקה תואמת אך הסכום שונה</span></div>
      <div class="legend-item"><span class="legend-dot ld-gray"></span><span class="legend-label">לא זמין</span><span class="legend-sep">&mdash;</span><span class="legend-desc">הפורמט אינו תקף לתאריך זה</span></div>
    </div>
  </div>

  <div class="table-section">
    <div class="table-scroll">
      <table>
        <thead><tr><!--TH_CELLS--></tr></thead>
        <tbody><!--ROWS_HTML--></tbody>
      </table>
    </div>
  </div>
</div>

<script>
function restartServer(btn){btn.disabled=true;btn.innerHTML='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg> מפעיל מחדש…';fetch('/api/restart',{method:'POST'}).catch(function(){}).finally(function(){var t=setInterval(function(){fetch('/').then(function(r){if(r.ok){clearInterval(t);location.reload();}}).catch(function(){});},800);});}
function openNav(){var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.add('open');o.classList.add('open');b.classList.add('open');}
function closeNav(){var s=document.getElementById('sidebar'),o=document.getElementById('nav-overlay'),b=document.getElementById('ham-btn');s.classList.remove('open');o.classList.remove('open');b.classList.remove('open');}
function toggleNav(){document.getElementById('sidebar').classList.contains('open')?closeNav():openNav();}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeNav();});
(function(){
  var genLabel = document.getElementById('generated-label');
  if (genLabel && document.body.dataset.generated)
    genLabel.textContent = '\u05e0\u05d5\u05e6\u05e8: ' + document.body.dataset.generated;
})();
function regenerate() {
  var btn = document.getElementById('regen-btn');
  var overlay = document.getElementById('loading-overlay');
  var pct = document.getElementById('loading-pct');
  btn.disabled = true;
  btn.classList.add('spinning');
  pct.textContent = '0%';
  overlay.classList.add('active');
  var es = new EventSource('/api/organizer/regenerate');
  es.onmessage = function(e) {
    if (e.data === 'done') {
      es.close(); location.reload();
    } else if (e.data === 'error') {
      es.close(); location.reload();
    } else {
      var p = parseInt(e.data);
      if (!isNaN(p)) pct.textContent = p + '%';
    }
  };
  es.onerror = function() { es.close(); location.reload(); };
}
</script>
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

    th_cells = '<th class="org-th org-th-date">תאריך</th>'
    for col in cols:
        th_cells += f'<th class="org-th">{_esc(col)}</th>'

    rows_html = ''
    for idx in df.index:
        tds = f'<td class="org-td org-td-date">{_esc(str(idx))}</td>'
        for col in cols:
            value    = df.at[idx, col]
            status   = color_coded_df.at[idx, col] if idx in color_coded_df.index and col in color_coded_df.columns else None
            is_date  = isinstance(value, str) and ('-' in value or '/' in value)
            card_num_col = col.split(' | ')[-1] if ' | ' in col else ''
            date_str = str(value)[:10] if is_date and isinstance(value, str) else (str(value) if value is not None else '')
            cell_key = (idx, col)

            is_invalid = False
            if 'Isra-Card-2026' in col:
                try:
                    yr = str(idx).split(', ')[-1]
                    if yr.isdigit() and int(yr) < 2026:
                        is_invalid = True
                except Exception:
                    pass

            if is_invalid:
                tds += '<td class="org-td org-cell-gray"><span class="org-cell-label">N/A</span></td>'
            elif cell_key in untagged_cells:
                m      = untagged_cells[cell_key]
                m_type = m[3] if len(m) > 3 else 'missing'
                m_name = _esc(str(m[2])) if len(m) > 2 and m[2] else '?'
                m_val  = _esc(str(m[1])) if len(m) > 1 and m[1] else '?'
                m_date = str(m[0])[:10]  if m[0] else '?'
                detail = (f'<div class="org-match-detail">'
                          f'<span>{m_name}</span><span>\u20aa{m_val}</span><span>{m_date}</span>'
                          f'</div>')
                if m_type == 'missing':
                    tds += f'<td class="org-td org-cell-blue-miss"><b>\u26a0 חסר</b>{detail}</td>'
                else:
                    tds += f'<td class="org-td org-cell-blue-mis2"><b>\u26a0 אי-התאמה</b>{detail}</td>'
            elif card_num_col == BANK_CARD_NUMBER and is_date:
                tds += (f'<td class="org-td org-cell-green">'
                        f'<span class="org-cell-label org-badge-bank">Bank</span>'
                        f'<span class="org-cell-date">{_esc(date_str)}</span></td>')
            elif status == 'Verified':
                tds += (f'<td class="org-td org-cell-green">'
                        f'<span class="org-cell-label">\u2713 מאומת</span>'
                        f'<span class="org-cell-date">{_esc(date_str)}</span></td>')
            elif status == 'Not Verified' and card_num_col != BANK_CARD_NUMBER:
                tds += (f'<td class="org-td org-cell-yellow">'
                        f'<span class="org-cell-label">\u26a0 לא מאומת</span>'
                        f'<span class="org-cell-date">{_esc(date_str)}</span></td>')
            elif is_date and status != 'Not Verified':
                tds += (f'<td class="org-td org-cell-yellow">'
                        f'<span class="org-cell-label">\u2014 ללא עסקות</span>'
                        f'<span class="org-cell-date">{_esc(date_str)}</span></td>')
            else:
                disp = date_str if date_str and date_str != 'None' else ''
                _cell_val = _esc(disp) if disp else '\u2014'
                tds += f'<td class="org-td org-cell-red">{_cell_val}</td>'

        rows_html += f'<tr>{tds}</tr>\n'

    from datetime import datetime as _now
    html = _ORGANIZER_HTML \
        .replace('<!--TH_CELLS-->', th_cells) \
        .replace('<!--ROWS_HTML-->', rows_html) \
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
            deps, db_mtime = _capture_deps_and_run(
                lambda: _build_organizer_page(progress_callback=lambda p: pq.put(p))
            )
            if os.path.exists(ORGANIZER_HTML):
                _save_manifest(ORGANIZER_HTML, deps, db_mtime)
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


_AT_PATH = os.path.join(_PROJECT_DIR, 'personal information', 'auto_tagger.json')

def _read_at() -> dict:
    import json as _j
    if os.path.exists(_AT_PATH):
        with open(_AT_PATH, encoding='utf-8') as _f:
            return _j.load(_f)
    return {}

def _write_at(d: dict):
    import json as _j
    with open(_AT_PATH, 'w', encoding='utf-8') as _f:
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
        cats_path = os.path.join(_PROJECT_DIR, 'Personal Information', 'categories.json')
        with open(cats_path, encoding='utf-8') as f:
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


@app.route('/api/tagger/categories/add', methods=['POST'])
def tagger_categories_add():
    import json as _json
    body = request.get_json() or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'missing name'})
    try:
        cats_path = os.path.join(_PROJECT_DIR, 'Personal Information', 'categories.json')
        with open(cats_path, encoding='utf-8') as f:
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
    cats_path = os.path.join(_PROJECT_DIR, 'Personal Information', 'categories.json')
    try:
        with open(cats_path, encoding='utf-8') as f:
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

_INPUT_FOLDER   = os.path.join(_PROJECT_DIR, 'ShmuelFamiliy_Inputs')
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
        import sqlite3 as _sq

        # Pre-load all known filenames from the DB so we don't rely solely on
        # the parser (which can't open locked files).
        _db_known = {}   # fname -> format
        try:
            _conn = _sq.connect(_DB_PATH, check_same_thread=False)
            for _row in _conn.execute("SELECT File_Name, Format FROM File"):
                _db_known[_row[0]] = _row[1]
            _conn.close()
        except Exception:
            pass

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
                utils.tagger_refresh()

            _log_queue.put(f'__DONE__:{filename}' if success else '__ERROR__')

        except Exception as e:
            import traceback
            _log_queue.put(f'[ERROR] {e}')
            for line in traceback.format_exc().splitlines():
                if line.strip():
                    _log_queue.put(line)
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
    if not fname:
        return jsonify({'ok': False, 'error': 'invalid filename'})
    os.makedirs(_INPUT_FOLDER, exist_ok=True)
    dest = os.path.join(_INPUT_FOLDER, fname)
    f.save(dest)
    return jsonify({'ok': True, 'filename': fname})


@app.route('/api/files/db-files')
def files_db_list():
    """Return all rows from the File table (files already in the database)."""
    import sqlite3 as _sq
    db_candidates = [
        _DB_PATH,
        os.path.join(_HERE, 'ShmuelFamiliy.db'),
    ]
    db_file = next((p for p in db_candidates if os.path.exists(p)), None)
    if not db_file:
        return jsonify({'ok': False, 'error': 'database not found'})
    try:
        conn = _sq.connect(db_file)
        conn.row_factory = _sq.Row
        cur  = conn.cursor()
        cur.execute('''
            SELECT File_Name, Format, Card_Number, Date,
                   New_Transactions, Transaction_count, Last_update
            FROM File
            ORDER BY Date DESC, Last_update DESC
        ''')
        rows = cur.fetchall()
        conn.close()

        files = []
        total_tx = 0
        for r in rows:
            card = r['Card_Number']
            if not card or card.lower() in ('not_relevant', 'none', ''):
                card = None
            files.append({
                'name':             r['File_Name'],
                'format':           r['Format'],
                'card':             card,
                'date':             (r['Date'] or '')[:10],
                'new_transactions': r['New_Transactions'] or 0,
                'transaction_count': r['Transaction_count'] or 0,
                'last_update':      (r['Last_update'] or '')[:10],
            })
            total_tx += r['Transaction_count'] or 0

        return jsonify({'ok': True, 'files': files, 'total_transactions': total_tx})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/transactions/split-info')
def tx_split_info():
    """Return original transaction details + its splits."""
    import sqlite3 as _sq
    tbl = (request.args.get('table') or '').strip()
    oid = request.args.get('id', type=int)
    if tbl not in ('BankTransactions', 'CardTransactions') or oid is None:
        return jsonify({'ok': False, 'error': 'invalid table or id'})
    try:
        conn = _sq.connect(_DB_PATH, check_same_thread=False)
        conn.row_factory = _sq.Row
        # Fetch original row
        if tbl == 'BankTransactions':
            row = conn.execute(
                'SELECT ID, Name, Category, Description, Out, Income, Date FROM BankTransactions WHERE ID=?', (oid,)
            ).fetchone()
            if not row:
                conn.close(); return jsonify({'ok': False, 'error': 'not found'})
            amount = float(row['Income'] or 0) - float(row['Out'] or 0)
            orig = {'id': row['ID'], 'name': row['Name'], 'category': row['Category'] or '',
                    'description': row['Description'] or '', 'amount': amount, 'date': (row['Date'] or '')[:10]}
        else:
            row = conn.execute(
                'SELECT ID, Name, Category, Description, Transaction_Value, Executed_Date FROM CardTransactions WHERE ID=?', (oid,)
            ).fetchone()
            if not row:
                conn.close(); return jsonify({'ok': False, 'error': 'not found'})
            orig = {'id': row['ID'], 'name': row['Name'], 'category': row['Category'] or '',
                    'description': row['Description'] or '',
                    'amount': float(row['Transaction_Value'] or 0),
                    'date': (row['Executed_Date'] or '')[:10]}
        # Fetch splits
        splits_rows = conn.execute(
            'SELECT ID, Amount, Description, Category FROM TransactionSplits WHERE Original_Table=? AND Original_ID=? ORDER BY ID',
            (tbl, oid)
        ).fetchall()
        conn.close()
        splits = [{'id': r['ID'], 'amount': float(r['Amount']),
                   'description': r['Description'] or '', 'category': r['Category']} for r in splits_rows]
        return jsonify({'ok': True, 'original': orig, 'splits': splits})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


def _regen_month_for_tx(tbl: str, tx_id: int) -> None:
    """
    Background helper: look up the transaction date, then regenerate the
    monthly HTML so split changes are reflected on the next page load.
    """
    try:
        import sqlite3 as _sq2
        col  = 'Date' if tbl == 'BankTransactions' else 'Executed_Date'
        conn = _sq2.connect(_DB_PATH, check_same_thread=False)
        row  = conn.execute(f'SELECT {col} FROM {tbl} WHERE ID=?', (tx_id,)).fetchone()
        conn.close()
        if not row or not row[0]:
            return
        from datetime import datetime as _dt2
        t = _dt2.strptime(str(row[0])[:10], '%Y-%m-%d')
        from AppManager import AppManager as _AM
        _AM(skip_parser=True).general_analysis(t=t)
    except Exception as _e:
        print(f'[split regen] {_e}')


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
        db.drop_file(name, fmt, card)
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


BILLS_HTML = os.path.join(_HERE, 'html', 'Bills.html')

# ── Bills tracker routes ───────────────────────────────────────────────────────

@app.route('/bills')
def bills_page():
    if os.path.exists(BILLS_HTML):
        return send_file(BILLS_HTML)
    return "Bills page not found", 404


@app.route('/api/bills/types', methods=['GET', 'POST'])
def api_bills_types():
    from database import DataBase
    db = DataBase()
    if request.method == 'GET':
        return jsonify({'ok': True, 'types': db.get_bill_types()})
    body = request.get_json(force=True) or {}
    name  = (body.get('name')  or '').strip()
    color = (body.get('color') or '#1e9d8b').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Name required'})
    try:
        group = (body.get('group') or '').strip()
        tid = db.add_bill_type(name, color, group)
        db.commit_changes()
        return jsonify({'ok': True, 'id': tid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/types/<int:type_id>', methods=['PUT', 'DELETE'])
def api_bills_type(type_id):
    from database import DataBase
    db = DataBase()
    if request.method == 'PUT':
        body  = request.get_json(force=True) or {}
        name  = (body.get('name')  or '').strip()
        color = (body.get('color') or '#1e9d8b').strip()
        group = (body.get('group') or '').strip()
        if not name:
            return jsonify({'ok': False, 'error': 'Name required'})
        try:
            db.update_bill_type(type_id, name, color, group)
            db.commit_changes()
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})
    try:
        db.delete_bill_type(type_id)
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/entries', methods=['GET', 'POST'])
def api_bills_entries():
    from database import DataBase
    db = DataBase()
    if request.method == 'GET':
        return jsonify({'ok': True, 'entries': db.get_bill_entries()})
    body = request.get_json(force=True) or {}
    try:
        overlap = db.check_bill_entry_overlap(
            int(body['bill_type_id']), body['start_month'], body['end_month']
        )
        if overlap:
            return jsonify({'ok': False, 'error': overlap})
        eid = db.add_bill_entry(
            bill_type_id      = int(body['bill_type_id']),
            start_month       = body['start_month'],
            end_month         = body['end_month'],
            transaction_table = body.get('transaction_table'),
            transaction_id    = body.get('transaction_id'),
            amount            = body.get('amount'),
            note              = body.get('note', ''),
            is_filler         = bool(body.get('is_filler', False)),
        )
        db.commit_changes()
        return jsonify({'ok': True, 'id': eid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/entries/<int:entry_id>', methods=['PUT', 'DELETE'])
def api_bills_entry(entry_id):
    from database import DataBase
    db = DataBase()
    if request.method == 'DELETE':
        try:
            db.delete_bill_entry(entry_id)
            db.commit_changes()
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})
    body = request.get_json(force=True) or {}
    try:
        # Need the bill_type_id of this entry to check overlap
        row = db.cursor.execute(
            "SELECT BillType_ID FROM BillEntries WHERE ID=?", (entry_id,)
        ).fetchone()
        if row:
            overlap = db.check_bill_entry_overlap(
                row[0], body['start_month'], body['end_month'], exclude_id=entry_id
            )
            if overlap:
                return jsonify({'ok': False, 'error': overlap})
        db.update_bill_entry(
            entry_id,
            start_month       = body['start_month'],
            end_month         = body['end_month'],
            note              = body.get('note'),
            transaction_table = body.get('transaction_table'),
            transaction_id    = body.get('transaction_id'),
            amount            = body.get('amount'),
            is_filler         = body.get('is_filler'),
        )
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/bills/suggestions')
def api_bills_suggestions():
    import sqlite3 as _sq
    conn = _sq.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = _sq.Row
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
        ).fetchall()
        linked_bank = {r[1] for r in already if r[0] == 'BankTransactions'}
        linked_card = {r[1] for r in already if r[0] == 'CardTransactions'}

        suggestions = []
        seen = set()
        for name in linked_names:
            if name in dismissed:
                continue
            for r in conn.execute(
                "SELECT ID, Date, Name, Out, Income FROM BankTransactions WHERE Name=? ORDER BY Date DESC LIMIT 30",
                (name,)
            ).fetchall():
                key = ('B', r[0])
                if r[0] in linked_bank or key in seen:
                    continue
                seen.add(key)
                suggestions.append({
                    'table': 'BankTransactions', 'id': r[0],
                    'date': (r[1] or '')[:10], 'name': r[2] or '',
                    'amount': float(r[3] or 0) or float(r[4] or 0),
                    'matched_name': name,
                })
            for r in conn.execute(
                "SELECT ID, Executed_Date, Name, Transaction_Value FROM CardTransactions WHERE Name=? ORDER BY Executed_Date DESC LIMIT 30",
                (name,)
            ).fetchall():
                key = ('C', r[0])
                if r[0] in linked_card or key in seen:
                    continue
                seen.add(key)
                suggestions.append({
                    'table': 'CardTransactions', 'id': r[0],
                    'date': (r[1] or '')[:10], 'name': r[2] or '',
                    'amount': abs(float(r[3] or 0)),
                    'matched_name': name,
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
    if os.path.exists(SPOTIFY_HTML):
        return send_file(SPOTIFY_HTML)
    return "Spotify Tracker page not found", 404


@app.route('/api/spotify/members', methods=['GET', 'POST'])
def api_spotify_members():
    from database import DataBase
    db = DataBase()
    if request.method == 'GET':
        return jsonify({'ok': True, 'members': db.get_spotify_members()})
    body = request.get_json(force=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'})
    try:
        mid = db.add_spotify_member(name, is_exempt=int(body.get('is_exempt', 0)))
        return jsonify({'ok': True, 'id': mid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/members/<int:member_id>', methods=['PUT', 'DELETE'])
def api_spotify_member(member_id):
    from database import DataBase
    db = DataBase()
    if request.method == 'DELETE':
        try:
            db.delete_spotify_member(member_id)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})
    body = request.get_json(force=True) or {}
    try:
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
    db = DataBase()
    if request.method == 'GET':
        return jsonify({'ok': True, 'charges': db.get_spotify_charges()})
    body = request.get_json(force=True) or {}
    try:
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
    db = DataBase()
    body = request.get_json(force=True) or {}
    try:
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
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from SpotifyTracker import get_charge_suggestions
    try:
        suggestions = get_charge_suggestions(_DB_PATH)
        return jsonify({'ok': True, 'suggestions': suggestions})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/payments', methods=['GET', 'POST'])
def api_spotify_payments():
    from database import DataBase
    db = DataBase()
    if request.method == 'GET':
        member_id = request.args.get('member_id', type=int)
        return jsonify({'ok': True, 'payments': db.get_spotify_payments(member_id)})
    body = request.get_json(force=True) or {}
    try:
        tx_id = body.get('tx_id')
        if tx_id is not None:
            if int(tx_id) in db.get_spotify_assigned_tx_ids():
                return jsonify({'ok': False, 'error': 'עסקה זו כבר שויכה לחבר אחר'})
        pid = db.add_spotify_payment(
            member_id=int(body.get('member_id', 0)),
            amount=float(body.get('amount', 0)),
            payment_date=(body.get('payment_date') or '').strip(),
            tx_id=tx_id,
            note=(body.get('note') or '').strip() or None,
        )
        return jsonify({'ok': True, 'id': pid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/payments/assigned-tx-ids')
def api_spotify_assigned_tx_ids():
    from database import DataBase
    db = DataBase()
    try:
        return jsonify({'ok': True, 'tx_ids': list(db.get_spotify_assigned_tx_ids())})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'tx_ids': []})


@app.route('/api/spotify/payments/<int:payment_id>', methods=['DELETE'])
def api_spotify_payment(payment_id):
    from database import DataBase
    db = DataBase()
    try:
        db.delete_spotify_payment(payment_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/unmatched')
def api_spotify_unmatched():
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from SpotifyTracker import get_unmatched_payments
    try:
        return jsonify({'ok': True, 'transactions': get_unmatched_payments(_DB_PATH)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/unmatched/<int:tx_id>/dismiss', methods=['POST'])
def api_spotify_dismiss_payment(tx_id):
    from database import DataBase
    db = DataBase()
    try:
        db.dismiss_spotify_payment(tx_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/balance')
def api_spotify_balance():
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from database import DataBase
    from SpotifyTracker import compute_all_balances
    try:
        db = DataBase()
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
        pdf_bytes = generate_pdf_report(member_ids, db)
        from flask import Response
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': 'attachment; filename="spotify_report.pdf"'},
        )
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


def start(port: int = 5050, open_browser: bool = True):
    """Start the Flask server and optionally open the browser."""
    import webbrowser
    os.environ['BANKAPP_WEB'] = '1'
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f'http://localhost:{port}')).start()
    app.run(host='127.0.0.1', port=port, threaded=True, debug=False, use_reloader=False)
