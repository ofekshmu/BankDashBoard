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

import re as _re
from flask import Flask, Response, request, jsonify, send_file, redirect

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE                  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HTML            = os.path.join(_HERE, 'html', 'output.html')
ORGANIZER_HTML         = os.path.join(_HERE, 'html', 'Organizer_Table.html')
_PROJECT_DIR           = os.path.dirname(_HERE)
GENERAL_ANALYSIS_DIR   = os.path.join(_PROJECT_DIR, 'Outputs', 'general_analysis')
CATEGORY_ANALYSIS_DIR  = os.path.join(_PROJECT_DIR, 'Outputs', 'category_analysis')
TAGGER_HTML            = os.path.join(_HERE, 'html', 'Tagger.html')

def _make_slug(type_: str, name: str) -> str:
    """type_ = 'cat' | 'biz'"""
    import re as _re2
    safe = _re2.sub(r'[^\w\u0590-\u05FF]', '_', name).strip('_')
    return f"{type_}_{safe}"

# ── Log capture via stdout tee ────────────────────────────────────────────────
_log_queue: queue.Queue = queue.Queue()

class _TeeStream:
    """Forwards every write() to the original stream *and* the SSE log queue."""
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

    def flush(self):
        self._orig.flush()

    def fileno(self):
        return self._orig.fileno()

    def __getattr__(self, name):
        return getattr(self._orig, name)


# Install tee once on import
if not isinstance(sys.stdout, _TeeStream):
    sys.stdout = _TeeStream(sys.stdout)

# ── Analysis state ────────────────────────────────────────────────────────────
_analysis_running = False
_analysis_lock    = threading.Lock()

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
        fpath = os.path.join(CATEGORY_ANALYSIS_DIR, f'{slug}.html')
        has   = os.path.exists(fpath)
        dot   = f'<span style="width:8px;height:8px;border-radius:50%;background:{"#1e9d8b" if has else "#ccc"};display:inline-block;margin-left:8px;flex-shrink:0"></span>'
        label = 'קטגוריה' if type_ == 'category' else 'עסק'
        badge_color = '#1e9d8b' if type_ == 'category' else '#9b59b6'
        return (
            f'<a href="/category/{slug}" class="cat-item" data-name="{name}"'
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
.sidebar{{width:72px;background:#fff;border-left:1px solid #eef0f6;position:fixed;top:0;right:0;
  height:100vh;display:flex;flex-direction:column;align-items:center;padding:16px 0;gap:2px;z-index:200;box-shadow:-2px 0 12px rgba(0,0,0,.05)}}
.sidebar-logo{{width:44px;height:44px;margin-bottom:18px}}
.nav-btn{{width:50px;height:54px;border-radius:12px;border:none;background:transparent;color:#9aa3bb;
  cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:3px;font-size:1.3em;text-decoration:none;transition:background .18s,color .18s}}
.nav-btn:hover{{background:#f0f4ff;color:#1e2a4a}}
.nav-btn.active{{background:#1e9d8b;color:#fff;box-shadow:0 4px 14px rgba(30,157,139,.30)}}
.nav-btn .lbl{{font-size:.34em;font-weight:600}}
.main{{margin-right:72px;flex:1;padding:30px 32px 60px}}
.page-header{{margin-bottom:24px}}
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
<nav class="sidebar">
  <div class="sidebar-logo">
    <svg viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="44" height="44" rx="12" fill="#1e9d8b"/>
      <rect x="8"  y="26" width="6" height="10" rx="1.5" fill="white" opacity="0.6"/>
      <rect x="17" y="18" width="6" height="18" rx="1.5" fill="white" opacity="0.85"/>
      <rect x="26" y="10" width="6" height="26" rx="1.5" fill="white"/>
      <text x="33" y="14" font-family="Arial" font-size="9" font-weight="800" fill="#1e9d8b" opacity="0.9">₪</text>
    </svg>
  </div>
  <a class="nav-btn" href="/" title="דשבורד ראשי"><span>⊞</span><span class="lbl">ראשי</span></a>
  <a class="nav-btn active" href="/categories" title="קטגוריות"><span>🏷</span><span class="lbl">קטגוריות</span></a>
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
    # Auto-trigger generation
    return _not_generated_category_html(slug)


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

    # Derive name from slug
    prefix = 'cat_' if type_ == 'category' else 'biz_'
    name   = slug[len(prefix):].replace('_', ' ') if slug.startswith(prefix) else slug

    def _worker():
        global _analysis_running
        try:
            from AppManager import AppManager
            if type_ == 'category':
                AppManager().category_analysis(category=name)
            else:
                AppManager().category_analysis(business=name)
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
    </style>"""


def _log_float_html() -> str:
    return """<div class="log-float" id="log-float">
  <div class="lf-header">
    <div class="lf-spinner" id="lf-spinner"></div>
    <span class="lf-title" id="lf-title">מנתח נתונים…</span>
  </div>
  <div class="lf-feed" id="lf-feed"></div>
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
    }"""


def _not_generated_category_html(slug: str) -> str:
    import json as _json
    slug_js  = _json.dumps(slug)
    type_val = 'category' if slug.startswith('cat_') else 'business'
    type_js  = _json.dumps(type_val)
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
      body: JSON.stringify({{slug: {slug_js}, type: {type_js}}})
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
    return _sq.connect(_DB_PATH, check_same_thread=False)


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
    body  = request.get_json() or {}
    name  = (body.get('name')  or '').strip()
    date  = (body.get('date')  or '').strip()
    value = body.get('value')
    if not name or not date or value is None:
        return jsonify({'ok': False, 'error': 'missing fields'})
    try:
        _dt.strptime(date, '%Y-%m-%d')
        conn = _acct_db()
        try:
            conn.execute(
                "INSERT INTO OtherAccountStatus (AccountName, StatusDate, Value, TransactionID) VALUES (?, ?, ?, ?)",
                (name, date, float(value), None)
            )
            conn.commit()
        finally:
            conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


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
            "SELECT ID, AccountName, StatusDate, Value FROM OtherAccountStatus ORDER BY StatusDate DESC"
        ).fetchall()
        entries = [{'id': r[0], 'account': r[1], 'date': r[2], 'value': r[3]} for r in rows]
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


@app.route('/api/status')
def status():
    return jsonify({'running': _analysis_running})


@app.route('/api/stale-all')
def stale_all():
    """Return {key: bool} stale status for every generated monthly page."""
    result = {}
    if not os.path.isdir(GENERAL_ANALYSIS_DIR):
        return jsonify(result)
    max_src = _max_source_mtime()
    for fname in os.listdir(GENERAL_ANALYSIS_DIR):
        m = _re.match(r'^(\d{4}_\d{2})\.html$', fname)
        if m:
            key = m.group(1)
            html_mtime = os.path.getmtime(os.path.join(GENERAL_ANALYSIS_DIR, fname))
            result[key] = max_src > html_mtime
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


@app.route('/api/stale/<yyyy_mm>')
def check_stale(yyyy_mm):
    if not _re.match(r'^\d{4}_\d{2}$', yyyy_mm):
        return jsonify({'stale': False})
    html_path = os.path.join(GENERAL_ANALYSIS_DIR, f'{yyyy_mm}.html')
    if not os.path.exists(html_path):
        return jsonify({'stale': True})
    html_mtime = os.path.getmtime(html_path)
    return jsonify({'stale': _max_source_mtime() > html_mtime})


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

            if month_sel == 'last':
                t = datetime.now() - relativedelta(months=1)
            elif month_sel == 'pick' and date_str:
                t = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                t = datetime.now()

            AppManager().general_analysis(t=t)
            _log_queue.put(f'__DONE__:{t.strftime("%Y_%m")}')

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
            if (e.data === '__DONE__') { es.close(); location.reload(); }
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
.sidebar{width:72px;background:var(--white);border-left:1px solid var(--border);position:fixed;top:0;right:0;height:100vh;display:flex;flex-direction:column;align-items:center;padding:16px 0;gap:2px;z-index:200;box-shadow:-2px 0 12px rgba(0,0,0,.05)}
.sidebar-logo{width:44px;height:44px;margin-bottom:18px}
.nav-btn{width:50px;height:54px;border-radius:12px;border:none;background:transparent;color:var(--text-muted);cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:1.3em;text-decoration:none;transition:background .18s,color .18s}
.nav-btn:hover{background:#f0f4ff;color:var(--navy)}
.nav-btn.active{background:var(--teal);color:#fff;box-shadow:0 4px 14px var(--teal-glow)}
.nav-btn .lbl{font-size:.34em;font-weight:600;letter-spacing:.4px;line-height:1}
a.nav-btn{text-decoration:none}
.main{margin-right:72px;flex:1;padding:30px 32px 60px;min-width:0;overflow-x:hidden}
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
<nav class="sidebar">
  <div class="sidebar-logo">
    <svg viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="44" height="44" rx="12" fill="#1e9d8b"/>
      <rect x="8" y="26" width="6" height="10" rx="1.5" fill="white" opacity="0.6"/>
      <rect x="17" y="18" width="6" height="18" rx="1.5" fill="white" opacity="0.85"/>
      <rect x="26" y="10" width="6" height="26" rx="1.5" fill="white"/>
      <text x="33" y="14" font-family="Arial" font-size="9" font-weight="800" fill="#1e9d8b" opacity="0.9">&#8362;</text>
    </svg>
  </div>
  <a class="nav-btn" href="/" title="דשבורד ראשי"><span>&#8862;</span><span class="lbl">ראשי</span></a>
  <a class="nav-btn" href="/categories" title="ניתוח קטגוריות"><span>&#127991;</span><span class="lbl">קטגוריות</span></a>
  <a class="nav-btn active" href="/organizer" title="ארגונית קבצים"><span>&#128194;</span><span class="lbl">ארגונית</span></a>
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
            _build_organizer_page(progress_callback=lambda p: pq.put(p))
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
        rows  = db.get_untagged_recent(limit=30)
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

    if not table or id_ is None or not cat:
        return jsonify({'ok': False, 'error': 'missing fields'})
    if table not in ('CardTransactions', 'BankTransactions'):
        return jsonify({'ok': False, 'error': 'invalid table'})
    try:
        DataBase().set_category_ui(table, int(id_), cat, is_auto=is_auto)
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


def start(port: int = 5050, open_browser: bool = True):
    """Start the Flask server and optionally open the browser."""
    import webbrowser
    os.environ['BANKAPP_WEB'] = '1'
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f'http://localhost:{port}')).start()
    app.run(host='127.0.0.1', port=port, threaded=True, debug=False, use_reloader=False)
