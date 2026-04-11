"""
Flask web server — replaces terminal menu interaction.

Routes
------
GET  /              serve output.html (or a splash screen when none exists)
POST /api/analysis  start general_analysis in a background thread
GET  /api/logs      SSE stream of log lines produced during analysis
GET  /api/status    return {"running": bool}
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
_PROJECT_DIR           = os.path.dirname(_HERE)
GENERAL_ANALYSIS_DIR   = os.path.join(_PROJECT_DIR, 'Outputs', 'general_analysis')
CATEGORY_ANALYSIS_DIR  = os.path.join(_PROJECT_DIR, 'Outputs', 'category_analysis')

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
            f'<a href="/category/{slug}" style="display:flex;align-items:center;padding:12px 16px;'
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
  <div class="grid">{items_html}</div>
</div>
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


@app.route('/api/status')
def status():
    return jsonify({'running': _analysis_running})


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


def start(port: int = 5050, open_browser: bool = True):
    """Start the Flask server and optionally open the browser."""
    import webbrowser
    os.environ['BANKAPP_WEB'] = '1'
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f'http://localhost:{port}')).start()
    app.run(host='127.0.0.1', port=port, threaded=True, debug=False, use_reloader=False)
