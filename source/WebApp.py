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
_HERE                = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HTML          = os.path.join(_HERE, 'html', 'output.html')
_PROJECT_DIR         = os.path.dirname(_HERE)
GENERAL_ANALYSIS_DIR = os.path.join(_PROJECT_DIR, 'Outputs', 'general_analysis')

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

            if msg in ('__DONE__', '__ERROR__'):
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
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9;
           display: flex; align-items: center; justify-content: center;
           min-height: 100vh; margin: 0; }}
    .box {{ background: #fff; border-radius: 14px; padding: 48px 56px;
           text-align: center; box-shadow: 0 6px 20px rgba(0,0,0,.10); max-width: 460px; }}
    h2   {{ color: #1e2a4a; margin-bottom: 10px; }}
    p    {{ color: #888; font-size: .93em; margin-bottom: 28px; }}
    .badge {{ display:inline-block; background:#1e9d8b; color:#fff; border-radius:20px;
              padding:5px 18px; font-size:.85em; font-weight:600; margin-bottom:24px; }}
    .btn {{ background: #1e9d8b; color: #fff; border: none; border-radius: 10px;
           padding: 13px 36px; font-size: 1em; cursor: pointer; font-weight: 600; }}
    .btn:hover {{ background: #178878; }}
    .btn:disabled {{ opacity: 0.6; cursor: wait; }}
    #msg {{ margin-top:18px; color:#1e9d8b; display:none; font-size:.88em; }}
    .back {{ margin-top:16px; font-size:.8em; }}
    .back a {{ color:#888; text-decoration:none; }}
    .back a:hover {{ color:#1e9d8b; }}
  </style>
</head>
<body>
  <div class="box">
    <h2>ניתוח חודשי</h2>
    <div class="badge">{month_label}</div>
    <p>הקובץ עבור חודש זה טרם נוצר. לחץ כדי להפעיל את הניתוח.</p>
    <button class="btn" id="runBtn" onclick="runNow()">הפעל ניתוח</button>
    <p id="msg">מעבד נתונים, אנא המתן…</p>
    <div class="back"><a href="/">&#8592; חזרה לדף הראשי</a></div>
  </div>
  <script>
    function runNow() {{
      document.getElementById('runBtn').disabled = true;
      document.getElementById('msg').style.display = 'block';
      fetch('/api/analysis', {{method:'POST',
            headers:{{'Content-Type':'application/json'}},
            body: JSON.stringify({{month:'pick', date:'{date_str}'}})
      }})
      .then(function() {{
        var es = new EventSource('/api/logs');
        es.onmessage = function(e) {{
          if (e.data.startsWith('__DONE__')) {{
            es.close();
            location.href = '/general/{yyyy_mm}';
          }}
          if (e.data === '__ERROR__') {{
            es.close();
            alert('שגיאה בניתוח — בדוק את הטרמינל');
            document.getElementById('runBtn').disabled = false;
            document.getElementById('msg').style.display = 'none';
          }}
        }};
      }});
    }}
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
